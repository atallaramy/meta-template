#!/usr/bin/env python3
"""Build INDEX.md + INDEX.json from ticket frontmatter.

Walks `tickets/` and `hotfix/`, parses YAML frontmatter from each markdown
file, validates against the schema and the epic registry in GOVERNANCE.md,
and emits two artifacts at the repo root:

- `INDEX.md`  — human-readable, one table per status plus cross-links
- `INDEX.json` — machine-readable array for agent queries

Flags:
  --validate   run all checks and exit non-zero on any violation; skip write.
               Also detects stale `blocked_by:` entries (references to
               status=done tickets) and reports them as errors. Used by CI.
  --check      regenerate and diff against committed INDEX.{md,json}; exit
               non-zero if drift (used by CI).
  --fix        clear stale `blocked_by:` entries that reference done tickets,
               then write INDEX.{md,json} as usual. Used by the pre-commit
               hook so stale entries get cleaned at commit time. Auto-stages
               touched ticket files via `git add` so the human sees them in
               their commit. Loud on any sub-step failure (DX-5).

Zero external dependencies: stdlib `re` parses the frontmatter block so
we don't pull in PyYAML. The schema is simple (no nested structures).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
GOVERNANCE = REPO_ROOT / "GOVERNANCE.md"
PROD_READINESS = REPO_ROOT / "PROD-READINESS.md"

VALID_STATUSES = {"backlog", "active", "blocked", "done"}

ID_RE = re.compile(r"^(?P<prefix>[A-Z]{2,8})-(?P<num>\d+(?:\.\d+)?)$")
HOTFIX_ID_RE = re.compile(r"^HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)

# Filename conventions
# - Tickets:  <ID>-<slug>.md    e.g. EMAIL-1-dns-architecture.md
# - Hotfixes: <ID>.md           e.g. HF-2026-04-18-auth-bypass.md  (ID already contains slug)
FILENAME_TICKET_RE = re.compile(r"^(?P<id>[A-Z]{2,8}-\d+(?:\.\d+)?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
FILENAME_HOTFIX_RE = re.compile(r"^(?P<id>HF-\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

# Fields that are lists (comma/YAML-list) — normalize to Python list
LIST_FIELDS = {"children", "blocks", "blocked_by", "repos"}
REQUIRED_FIELDS = {"id", "title", "epic", "status", "created"}
VALID_REPOS = {"backend", "frontend", "infra", "meta"}


@dataclass
class Ticket:
    path: Path
    frontmatter: dict[str, object]
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.frontmatter.get("id", ""))

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status", ""))

    @property
    def epic(self) -> str:
        return str(self.frontmatter.get("epic", ""))


def parse_epic_registry(governance_text: str) -> set[str]:
    """Extract epic codes from GOVERNANCE.md section 3.

    The registry is a markdown table; each epic code is in the first
    column in bold (`**CODE**`). Reserved codes (section 3.Reserved)
    are collected too because they're valid even if not yet in use.
    """
    codes: set[str] = set()
    # Table rows like: | **AUTH** | ... | ... |
    for match in re.finditer(r"^\|\s*\*\*([A-Z]{2,8})\*\*\s*\|", governance_text, re.MULTILINE):
        codes.add(match.group(1))
    # Reserved line: `DATA`, `COMPL` — picked up too
    reserved_block = re.search(
        r"### Reserved.*?\n\n(.*?)(?:\n\n|\n###)", governance_text, re.DOTALL
    )
    if reserved_block:
        for code_match in re.finditer(r"`([A-Z]{2,8})`", reserved_block.group(1)):
            codes.add(code_match.group(1))
    return codes


def parse_synonyms(governance_text: str) -> dict[str, str]:
    """Extract synonym-alias → canonical-epic mapping from GOVERNANCE.md."""
    synonyms: dict[str, str] = {}
    block = re.search(
        r"### Synonym aliases.*?\n(.*?)(?:\n---|\n## )", governance_text, re.DOTALL
    )
    if not block:
        return synonyms
    for line in block.group(1).splitlines():
        # Lines: - `AUTHZ`, `AUTHN`, ... → use **AUTH**
        m = re.match(r"-\s+(?P<aliases>.+?)\s+→\s+use\s+\*\*(?P<canonical>[A-Z]+)\*\*", line)
        if not m:
            continue
        canonical = m.group("canonical")
        for alias in re.findall(r"`([A-Z]+)`", m.group("aliases")):
            synonyms[alias] = canonical
    return synonyms


def parse_frontmatter(text: str) -> dict[str, object] | None:
    """Parse the YAML-ish frontmatter block at the start of a ticket file.

    Intentionally minimal: scalar strings/nums, null, bracket lists. We
    control the schema, so we don't need a full YAML parser.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    out: dict[str, object] = {}
    for line in match.group("body").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        # Strip trailing inline comments
        raw = re.sub(r"\s+#.*$", "", raw)
        if raw in {"", "null"}:
            out[key] = None
            continue
        # Bracket list
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            out[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
            continue
        # Strip surrounding quotes if any
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            raw = raw[1:-1]
        out[key] = raw
    # Normalize list fields even if missing
    for lf in LIST_FIELDS:
        out.setdefault(lf, [])
        if not isinstance(out[lf], list):
            out[lf] = []
    return out


def _detect_multiline_list_fields(text: str) -> list[str]:
    """Return the names of LIST_FIELDS that use multi-line YAML list form.

    Bracket-list form (`field: [A, B]` or `field: []`) is the project
    convention and is what `parse_frontmatter` understands. A multi-line
    form (`field:` on one line, `  - A` on the next) would be silently
    parsed as empty, making stale-entry detection blind to those refs.
    Reject the shape repo-wide at validate-time so `--fix` never has to
    operate on a partially-visible state.
    """
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return []
    body = fm_match.group("body")
    offending: list[str] = []
    list_field_pattern = "|".join(re.escape(f) for f in LIST_FIELDS)
    # Lines like `field:` (nothing or only-whitespace after the colon)
    # followed (on the very next line) by `  - <item>`. We don't need to
    # walk the entire block — one matching pair is enough to flag.
    pattern = re.compile(
        rf"^[ \t]*(?P<field>{list_field_pattern})[ \t]*:[ \t]*\n[ \t]+-[ \t]+",
        re.MULTILINE,
    )
    for m in pattern.finditer(body):
        offending.append(m.group("field"))
    return offending


def discover_tickets(root: Path) -> list[Ticket]:
    tickets: list[Ticket] = []
    # Files that may legitimately live in ticket folders without being tickets.
    NON_TICKET_FILES = {"README.md"}
    for sub in ("tickets/backlog", "tickets/active", "tickets/blocked", "tickets/done", "hotfix"):
        folder = root / sub
        if not folder.is_dir():
            continue
        for md in sorted(folder.glob("*.md")):
            if md.name in NON_TICKET_FILES:
                continue
            text = md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                tickets.append(Ticket(path=md, frontmatter={}, errors=["missing frontmatter"]))
                continue
            t = Ticket(path=md, frontmatter=fm)
            # Surface multi-line YAML list form (silent-parse footgun).
            for offending in _detect_multiline_list_fields(text):
                t.errors.append(
                    f"{offending!r} uses multi-line YAML list form; "
                    f"convert to bracket-list (`{offending}: []` or `{offending}: [ID1, ID2]`)"
                )
            tickets.append(t)
    return tickets


def validate(tickets: list[Ticket], epic_codes: set[str], synonyms: dict[str, str]) -> int:
    """Populate ticket.errors; return total error count."""
    seen_ids: dict[str, Path] = {}
    for t in tickets:
        fm = t.frontmatter
        for field_name in REQUIRED_FIELDS:
            if field_name not in fm or fm[field_name] in {None, ""}:
                t.errors.append(f"missing required field: {field_name}")
        tid = str(fm.get("id", ""))
        if tid:
            if tid in seen_ids:
                t.errors.append(f"duplicate id: {tid} (also in {seen_ids[tid]})")
            else:
                seen_ids[tid] = t.path
            if not (ID_RE.match(tid) or HOTFIX_ID_RE.match(tid)):
                t.errors.append(f"id does not match regex: {tid}")
            else:
                m = ID_RE.match(tid)
                if m:
                    prefix = m.group("prefix")
                    if prefix in synonyms:
                        t.errors.append(
                            f"id prefix {prefix!r} is a synonym alias; use canonical {synonyms[prefix]!r}"
                        )
                    elif prefix not in epic_codes:
                        t.errors.append(f"id prefix {prefix!r} not in epic registry")
        # Filename format + filename ID must match frontmatter id
        fname = t.path.name
        is_hotfix = tid.startswith("HF-") if tid else fname.startswith("HF-")
        fm_match = FILENAME_HOTFIX_RE.match(fname) if is_hotfix else FILENAME_TICKET_RE.match(fname)
        if not fm_match:
            expected = "HF-YYYY-MM-DD-<slug>.md" if is_hotfix else "<EPIC>-<N>-<slug>.md"
            t.errors.append(f"filename {fname!r} does not match convention {expected}")
        elif tid and fm_match.group("id") != tid:
            t.errors.append(
                f"filename id {fm_match.group('id')!r} does not match frontmatter id {tid!r}"
            )
        epic = str(fm.get("epic", ""))
        if epic and epic not in epic_codes:
            t.errors.append(f"epic {epic!r} not in epic registry")
        status = str(fm.get("status", ""))
        if status and status not in VALID_STATUSES:
            t.errors.append(f"status {status!r} not one of {sorted(VALID_STATUSES)}")
        # status ↔ folder (hotfixes live in hotfix/ regardless of internal status — see HOTFIX.md template)
        expected_folder = {"backlog": "tickets/backlog", "active": "tickets/active",
                           "blocked": "tickets/blocked", "done": "tickets/done"}
        if status in expected_folder and not is_hotfix:
            if expected_folder[status] not in str(t.path):
                t.errors.append(f"status {status!r} does not match folder {t.path.parent.name!r}")
        # next_action required on active tickets (session hygiene — GOVERNANCE §15.1).
        # Skipped for hotfixes: hotfix files are short-lived single-fix records, not session-resumed work.
        if status == "active" and not is_hotfix:
            next_action = fm.get("next_action")
            if not next_action or str(next_action).strip().lower() in {"", "null", "none"}:
                t.errors.append("next_action required when status == active (GOVERNANCE §5 + §15.1)")
        # repos values must be a subset of VALID_REPOS
        repos = fm.get("repos") or []
        if isinstance(repos, list):
            for r in repos:
                if r not in VALID_REPOS:
                    t.errors.append(f"repos entry {r!r} not in {sorted(VALID_REPOS)}")
    # Second pass: cross-refs (repos is a list field but its values are repo names, not ticket ids)
    cross_ref_list_fields = LIST_FIELDS - {"repos"}
    all_ids = {t.id for t in tickets if t.id}
    for t in tickets:
        for ref_field in ("parent", "discovered_from"):
            val = t.frontmatter.get(ref_field)
            if val and val not in all_ids and val != "null":
                t.errors.append(f"{ref_field} references unknown id: {val}")
        for list_field in cross_ref_list_fields:
            for ref in t.frontmatter.get(list_field, []) or []:
                if ref not in all_ids:
                    t.errors.append(f"{list_field} references unknown id: {ref}")
    return sum(len(t.errors) for t in tickets)


def render_index_md(tickets: list[Ticket]) -> str:
    by_status: dict[str, list[Ticket]] = {s: [] for s in ("active", "blocked", "backlog", "done")}
    hotfixes: list[Ticket] = []
    for t in tickets:
        if t.id.startswith("HF-"):
            hotfixes.append(t)
        elif t.status in by_status:
            by_status[t.status].append(t)
    lines: list[str] = []
    lines.append("# Ticket index")
    lines.append("")
    lines.append("> Auto-generated by `scripts/build_index.py`. **Do not hand-edit.**")
    lines.append("> Regenerate with `python scripts/build_index.py`. CI fails on drift.")
    lines.append("")
    status_titles = {
        "active": "Active",
        "blocked": "Blocked",
        "backlog": "Backlog",
        "done": "Done",
    }
    for status in ("active", "blocked", "backlog", "done"):
        items = sorted(by_status[status], key=lambda t: t.id)
        lines.append(f"## {status_titles[status]} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_No tickets._")
            lines.append("")
            continue
        lines.append("| ID | Title | Epic | Parent | Blocked by | Path |")
        lines.append("|---|---|---|---|---|---|")
        for t in items:
            fm = t.frontmatter
            parent = fm.get("parent") or "—"
            blocked_by = ", ".join(fm.get("blocked_by", []) or []) or "—"
            rel = t.path.relative_to(REPO_ROOT)
            lines.append(
                f"| `{t.id}` | {fm.get('title', '')} | `{fm.get('epic', '')}` | "
                f"{parent} | {blocked_by} | [`{rel}`]({rel}) |"
            )
        lines.append("")
    lines.append(f"## Hotfixes ({len(hotfixes)})")
    lines.append("")
    if hotfixes:
        lines.append("| ID | Title | Epic | Severity | Path |")
        lines.append("|---|---|---|---|---|")
        for t in sorted(hotfixes, key=lambda t: t.id):
            fm = t.frontmatter
            rel = t.path.relative_to(REPO_ROOT)
            lines.append(
                f"| `{t.id}` | {fm.get('title', '')} | `{fm.get('epic', '')}` | "
                f"{fm.get('severity', '—')} | [`{rel}`]({rel}) |"
            )
    else:
        lines.append("_No hotfixes._")
    # Exactly one trailing newline — matches end-of-file-fixer expectations.
    return "\n".join(lines) + "\n"


# =============================================================================
# PROD-READINESS auto-tick (DX-4) — derive checkbox state from ticket frontmatter
# =============================================================================
#
# Two anchor rules, evaluated in order:
#   1. Subsection-scoped — checkboxes under `### ... <dash> `<TICKET-ID>`` headings
#      auto-tick when <TICKET-ID> has status=done.
#   2. Path-anchored — checkboxes outside such a subsection that contain a
#      `tickets/.../<ID>-...md` reference auto-tick when <ID> is done.
# Anything else stays manual. Body-text ticket mentions don't trigger.
# Subsection-heading dash is widened to em-dash / en-dash / hyphen so a future
# contributor's ASCII `-` between title and `<ID>` doesn't silently fall through
# to path-anchor-only mode.
PROD_SUBSECTION_TICKET_RE = re.compile(r"^### .* [—–-] `([A-Z]{2,8}-\d+)`")
PROD_TICKET_PATH_RE = re.compile(r"tickets/[a-z]+/([A-Z]{2,8}-\d+)-")
PROD_CHECKBOX_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>[ xX])\] (?P<body>.*)$")


def _read_utf8(path: Path) -> str:
    """Read a file as UTF-8 with a clear error message on decode failure."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise SystemExit(
            f"ERROR: {path.relative_to(REPO_ROOT)} is not valid UTF-8 ({e}). "
            f"Re-save the file as UTF-8 (no BOM) before re-running."
        )


def autotick_prod_readiness(
    tickets: Iterable[Ticket],
) -> tuple[str | None, int, list[tuple[int, str, str]]]:
    """Return (new_text, count_changed, change_log).

    change_log is a list of (line_no, ticket_id, new_mark) for every flipped
    checkbox — surfaced in --check mode so CI failures point at the cause.
    new_text is None if PROD-READINESS doesn't exist (treated as "nothing to
    sync", neither write nor drift).
    """
    if not PROD_READINESS.is_file():
        return (None, 0, [])
    status_by_id = {t.id: t.status for t in tickets if t.id}
    text = _read_utf8(PROD_READINESS)
    section_ticket: str | None = None
    changed = 0
    change_log: list[tuple[int, str, str]] = []
    out_lines: list[str] = []
    for line_no, raw in enumerate(text.splitlines(keepends=True), start=1):
        line = raw.rstrip("\n")
        nl = raw[len(line):]  # preserve trailing newline (or absence)
        # Reset section scope on any heading less-deep than `### ` (currently
        # `# ` and `## `; `#### ` would also reset if it ever appears).
        if (line.startswith("# ") or line.startswith("## ")) and not line.startswith("### "):
            section_ticket = None
        if line.startswith("### "):
            m = PROD_SUBSECTION_TICKET_RE.match(line)
            section_ticket = m.group(1) if m else None
        cb = PROD_CHECKBOX_RE.match(line)
        if cb:
            indent = cb.group("indent")
            mark = cb.group("mark").lower()
            body = cb.group("body")
            target_id: str | None = None
            if section_ticket:
                target_id = section_ticket
            else:
                pm = PROD_TICKET_PATH_RE.search(body)
                if pm:
                    target_id = pm.group(1)
            if target_id and target_id in status_by_id:
                desired = "x" if status_by_id[target_id] == "done" else " "
                if desired != mark:
                    line = f"{indent}- [{desired}] {body}"
                    changed += 1
                    change_log.append((line_no, target_id, desired))
        out_lines.append(line + nl)
    new_text = "".join(out_lines)
    return (new_text, changed, change_log)


# =============================================================================
# DX-5 — Auto-unblock dependent tickets when blocker ships
# =============================================================================
#
# When a blocker moves to tickets/done/, dependents listing it in `blocked_by:`
# should have that entry removed so the dependent doesn't sit misrepresented
# as un-startable. Two modes share the detection logic:
#
#   --validate : reports stale entries as errors (no writes)
#   --fix      : rewrites the dependent's frontmatter to drop the stale entry,
#                bumps `updated:` to today, auto-stages via `git add`
#
# Fidelity strategy — surgical regex line-edit, not YAML round-trip:
# only the `blocked_by:` and `updated:` lines in the frontmatter are touched.
# No bytes outside those two lines are written, so whitespace/comment/ordering
# drift is structurally impossible. See DX-5 §Decisions 2026-05-11.

# Match a single frontmatter key+value line (anchored to ^ in MULTILINE).
# Captures: indent, key, optional whitespace-before-colon, separator
# (": " or just ":"), value, trailing whitespace. The trail group used to
# also capture inline `# comment` text, but that's a footgun: a value
# containing `#` (e.g. `next_action: see #issue42`) was being split into
# `value="see"` + `trail=" #issue42"`, and rewriting that line would have
# materialized a YAML comment that wasn't there. Loop 1 silent-failure
# review surfaced this. Now `trail` is whitespace-only; full-line comments
# (anchored at column 0 or only-whitespace before `#`) are skipped by the
# parser separately.
#
# Only used by `_replace_key` to rewrite a strict allowlist of keys.
_FRONTMATTER_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)[ \t]*:(?P<sep>[ \t]*)"
    r"(?P<value>.*?)(?P<trail>[ \t]*)$",
    re.MULTILINE,
)

# Keys that `_replace_key` is allowed to rewrite. Belt-and-braces guard
# against a future caller passing in a key whose value semantics differ
# (e.g. multi-line strings, quoted booleans) and silently corrupting it.
_REWRITABLE_KEYS = {"blocked_by", "updated"}


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def find_stale_blocked_by(tickets: list[Ticket]) -> list[tuple[Ticket, list[str], list[str]]]:
    """Return tuples of (ticket, stale_ids, remaining_ids).

    A `blocked_by:` entry is stale when it references a ticket whose status
    is `done`. The dependent ticket itself must not be done (no point
    cleaning a frozen ticket's frontmatter).
    """
    done_ids = {t.id for t in tickets if t.status == "done" and t.id}
    stale: list[tuple[Ticket, list[str], list[str]]] = []
    for t in tickets:
        if t.status == "done" or not t.id:
            continue
        bb = t.frontmatter.get("blocked_by") or []
        if not isinstance(bb, list):
            continue
        stale_here = [ref for ref in bb if ref in done_ids]
        if stale_here:
            remaining = [ref for ref in bb if ref not in done_ids]
            stale.append((t, stale_here, remaining))
    return stale


def _format_blocked_by_yaml(values: list[str]) -> str:
    """Render the blocked_by value in YAML bracket-list form.

    Matches the existing convention seen across `tickets/` — `[]` or
    `[ID1, ID2]`. Quoting is unnecessary: ticket IDs are bare tokens.
    """
    return "[]" if not values else "[" + ", ".join(values) + "]"


def rewrite_blocked_by_and_updated(text: str, new_blocked_by: list[str], today: str) -> str:
    """Surgically replace the `blocked_by:` and `updated:` lines.

    Touches ONLY those two lines inside the frontmatter block. Indentation,
    inline comments, surrounding lines, and every other field stay byte-
    identical. If a target line is absent (shouldn't happen — required
    field), the function raises rather than silently appending.

    Refuses to operate on multi-line YAML list form (`blocked_by:\\n  - X`):
    the regex would match only the bare key line and silently leave the
    list items intact, producing a malformed file. `validate()` rejects
    that shape repo-wide, so this is defense in depth.
    """
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        raise ValueError("missing frontmatter block")
    body_start = fm_match.start("body")
    body_end = fm_match.end("body")
    body = text[body_start:body_end]

    new_bb_value = _format_blocked_by_yaml(new_blocked_by)

    def _replace_key(yaml: str, key: str, new_value: str) -> str:
        """Replace the first occurrence of `<key>: ...` in `yaml`.

        Only keys in `_REWRITABLE_KEYS` are accepted — guard against a
        future caller asking us to rewrite a field whose value semantics
        we haven't audited.
        """
        if key not in _REWRITABLE_KEYS:
            raise ValueError(
                f"_replace_key refuses to rewrite {key!r}: not in allowlist "
                f"{sorted(_REWRITABLE_KEYS)}. Audit the value shape (quoting, "
                f"multi-line, special chars) before widening the allowlist."
            )
        replaced = {"done": False}

        def repl(m: re.Match[str]) -> str:
            if replaced["done"] or m.group("key") != key:
                return m.group(0)
            # Guard: refuse to rewrite if the existing value already opens
            # a multi-line block scalar (`|`, `>`) — surgical edit would
            # leave block contents below dangling.
            existing = m.group("value").strip()
            if existing.startswith(("|", ">")):
                raise ValueError(
                    f"{key} uses multi-line block-scalar form ({existing[:1]!r}); "
                    f"surgical rewrite refused. Convert to bracket-list / scalar first."
                )
            # If value looks like the start of a multi-line list (just key:
            # with nothing after), the next line is "  - <item>" — also refuse.
            if existing == "" and key == "blocked_by":
                # Look ahead: is the next line a YAML list item under us?
                # We need the original text not just the matched line. Use
                # the match's position in `yaml` to peek.
                tail_after_match = yaml[m.end():]
                next_line_match = re.match(r"\n[ \t]*-[ \t]+", tail_after_match)
                if next_line_match:
                    raise ValueError(
                        f"{key} uses multi-line YAML list form (next line is `-`); "
                        f"surgical rewrite refused. Convert to bracket-list first."
                    )
            replaced["done"] = True
            sep = m.group("sep") or " "
            # `trail` is now whitespace-only (no comment capture); preserve verbatim.
            trail = m.group("trail")
            return f"{m.group('indent')}{key}:{sep}{new_value}{trail}"

        out = _FRONTMATTER_LINE_RE.sub(repl, yaml)
        if not replaced["done"]:
            raise ValueError(f"frontmatter key not found (canonical form): {key}")
        return out

    new_body = _replace_key(body, "blocked_by", new_bb_value)
    new_body = _replace_key(new_body, "updated", today)
    return text[:body_start] + new_body + text[body_end:]


def _verify_round_trip(
    new_text: str, original_id: str, original_epic: str, original_status: str
) -> None:
    """Re-parse the rewritten file and confirm key invariants round-trip.

    Raises ValueError on any drift. The caller is responsible for restoring
    from backup if this raises.
    """
    fm = parse_frontmatter(new_text)
    if fm is None:
        raise ValueError("frontmatter no longer parseable after rewrite")
    for field_name, expected in (
        ("id", original_id),
        ("epic", original_epic),
        ("status", original_status),
    ):
        actual = fm.get(field_name)
        if str(actual) != str(expected):
            raise ValueError(
                f"value drift on {field_name}: was {expected!r}, now {actual!r}"
            )


def _backup_then_write(path: Path, new_text: str) -> Path:
    """Write new_text to path atomically, after first backing up the original.

    Returns the backup path. On any failure during the write, attempts to
    restore from backup. If restore itself fails, raises an exception
    that names BOTH the backup path and the corrupted target path so the
    human can `cp <backup> <target>` manually (no silent "tried to restore
    but couldn't" path).
    """
    fd, backup_name = tempfile.mkstemp(
        prefix=f".bak-{path.name}-", suffix=".tmp", dir=path.parent
    )
    backup_path = Path(backup_name)
    # Close the fd we won't use (mkstemp opens it); shutil.copy2 will reopen.
    import os as _os
    _os.close(fd)
    try:
        shutil.copy2(path, backup_path)
    except OSError as e:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"backup-write failed for {path}: {e}") from e

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        # Write failed — try to restore. The backup is still pristine.
        try:
            shutil.copy2(backup_path, path)
        except OSError as restore_err:
            raise RuntimeError(
                f"write failed for {path} AND restore from backup failed.\n"
                f"  Backup preserved at: {backup_path}\n"
                f"  Corrupted target:    {path}\n"
                f"  Manual recovery:     cp {backup_path} {path}\n"
                f"  Original write error: {e}\n"
                f"  Restore error:        {restore_err}"
            ) from restore_err
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"write failed for {path}; restored from backup: {e}") from e

    return backup_path


def _git_add(paths: list[Path]) -> None:
    """Stage paths via `git add`. Raises RuntimeError on any failure.

    Loud-fail per DX-5 spec: a non-zero exit from git, OR any path that
    doesn't show up as staged after the call, aborts the run with the full
    failed-path list — never a partial success. The post-add `git diff
    --cached --name-only` cross-check catches sparse-checkout / gitignore /
    path-filter edge cases that can let `git add` exit 0 while silently
    skipping files.
    """
    if not paths:
        return
    rel_paths = [str(p.relative_to(REPO_ROOT)) for p in paths]
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add", "--", *rel_paths],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        raise RuntimeError(f"git add invocation failed: {e}") from e
    if result.returncode != 0:
        raise RuntimeError(
            "git add failed:\n"
            f"  paths: {rel_paths}\n"
            f"  stderr: {result.stderr.strip()}\n"
            f"  stdout: {result.stdout.strip()}"
        )
    # Post-stage verify: confirm each path appears in `git diff --cached`.
    # Belt-and-braces against the silent-skip cases above.
    try:
        check = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        raise RuntimeError(f"git diff --cached invocation failed: {e}") from e
    if check.returncode != 0:
        raise RuntimeError(
            f"git diff --cached failed (rc={check.returncode}): {check.stderr.strip()}"
        )
    staged_now = set(check.stdout.splitlines())
    missing = [p for p in rel_paths if p not in staged_now]
    if missing:
        raise RuntimeError(
            "git add appeared to succeed but the following paths are NOT staged "
            "(possible sparse-checkout, .gitignore, or path filter):\n"
            + "\n".join(f"  - {p}" for p in missing)
        )


def _format_surviving_backups(backups: list[Path]) -> str:
    """Render a human-readable list of backup paths that may need cleanup."""
    if not backups:
        return ""
    lines = ["  Surviving backups from earlier iterations of this run:"]
    for b in backups:
        lines.append(f"    - {b}")
    lines.append("  Inspect with `ls -la _archive/../.bak-*` (or your editor).")
    return "\n".join(lines)


def apply_unblock_fix(tickets: list[Ticket]) -> tuple[int, list[tuple[str, list[str]]]]:
    """Apply --fix logic: clear stale blocked_by entries.

    Returns (count_cleared, [(ticket_id, cleared_refs), ...]).
    Raises RuntimeError on any sub-step failure (backup, write, re-parse,
    git add) — caller is expected to surface the failure and exit non-zero.

    Note: caller is also responsible for ensuring no malformed `done/` tickets
    are present (run validate() first). If any ticket has empty frontmatter
    (parse-failed), `find_stale_blocked_by` simply ignores it (the entry's
    `blocked_by` is empty), but validate() will already have reported the
    parse failure.
    """
    stale = find_stale_blocked_by(tickets)
    if not stale:
        return (0, [])

    today = _today_iso()
    touched_paths: list[Path] = []
    cleared: list[tuple[str, list[str]]] = []
    backups: list[Path] = []

    try:
        for t, stale_refs, remaining in stale:
            original_text = t.path.read_text(encoding="utf-8")
            new_text = rewrite_blocked_by_and_updated(original_text, remaining, today)
            if new_text == original_text:
                # Should not happen — `find_stale_blocked_by` only yields
                # rows that need a change — but defensive guard against a
                # quietly-no-op rewrite.
                raise RuntimeError(
                    f"--fix would no-op on {t.path.relative_to(REPO_ROOT)} despite "
                    f"detected stale entries {stale_refs}; refusing to claim success"
                )
            backup = _backup_then_write(t.path, new_text)
            backups.append(backup)
            try:
                _verify_round_trip(
                    new_text,
                    original_id=t.id,
                    original_epic=t.epic,
                    original_status=t.status,
                )
            except ValueError as e:
                # Round-trip drift — restore from backup before raising.
                try:
                    shutil.copy2(backup, t.path)
                except OSError as restore_err:
                    raise RuntimeError(
                        f"post-write re-parse FAILED for {t.path} AND restore from "
                        f"backup failed.\n"
                        f"  Backup preserved at: {backup}\n"
                        f"  Corrupted target:    {t.path}\n"
                        f"  Manual recovery:     cp {backup} {t.path}\n"
                        f"  Round-trip error:    {e}\n"
                        f"  Restore error:       {restore_err}\n"
                        + _format_surviving_backups(backups[:-1])
                    ) from restore_err
                raise RuntimeError(
                    f"post-write re-parse failed for {t.path}; restored from backup: {e}\n"
                    + _format_surviving_backups(backups[:-1])
                ) from e
            touched_paths.append(t.path)
            cleared.append((t.id, stale_refs))

        _git_add(touched_paths)
    except Exception as e:
        # On any failure mid-flight, augment the exception with the list
        # of backup paths that survived earlier-iteration writes so the
        # operator can find them without `ls .bak-*`. Backups stay on disk
        # on failure — only success path cleans them up.
        if backups and isinstance(e, RuntimeError) and "Backup preserved at:" not in str(e):
            # Inline the surviving-backups list into the error message.
            raise RuntimeError(
                f"{e}\n" + _format_surviving_backups(backups)
            ) from e
        raise

    # Success: clean up backups.
    for backup in backups:
        backup.unlink(missing_ok=True)

    return (len(cleared), cleared)


def render_index_json(tickets: list[Ticket]) -> str:
    out = []
    for t in sorted(tickets, key=lambda t: t.id):
        fm = dict(t.frontmatter)
        fm["path"] = str(t.path.relative_to(REPO_ROOT))
        out.append(fm)
    return json.dumps(out, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build INDEX.md + INDEX.json from tickets/.")
    ap.add_argument("--validate", action="store_true",
                    help="validate only, no file output; exit 1 on any error "
                         "(includes stale blocked_by detection — DX-5)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate and diff vs committed INDEX files; exit 1 on drift")
    ap.add_argument("--fix", action="store_true",
                    help="auto-clear stale blocked_by entries (refs to done tickets), "
                         "bump updated:, auto-stage via git add, then regenerate INDEX. "
                         "Used by pre-commit (DX-5).")
    args = ap.parse_args()

    if args.fix and args.validate:
        print("ERROR: --fix and --validate are mutually exclusive", file=sys.stderr)
        return 2
    if args.fix and args.check:
        # --fix mutates ticket frontmatter and writes new INDEX files; --check
        # compares the freshly-rendered INDEX against the on-disk INDEX (which
        # may also be updated by --fix). Combining them would produce
        # confusing drift errors that don't reflect the real state.
        print("ERROR: --fix and --check are mutually exclusive", file=sys.stderr)
        return 2

    if not GOVERNANCE.is_file():
        print(f"ERROR: {GOVERNANCE} not found", file=sys.stderr)
        return 2
    governance_text = GOVERNANCE.read_text(encoding="utf-8")
    epic_codes = parse_epic_registry(governance_text)
    synonyms = parse_synonyms(governance_text)
    if not epic_codes:
        print("ERROR: could not parse epic registry from GOVERNANCE.md", file=sys.stderr)
        return 2

    tickets = discover_tickets(REPO_ROOT)
    errors_total = validate(tickets, epic_codes, synonyms)
    if errors_total:
        print(f"Validation: {errors_total} error(s) across {sum(1 for t in tickets if t.errors)} ticket(s)", file=sys.stderr)
        for t in tickets:
            if not t.errors:
                continue
            rel = t.path.relative_to(REPO_ROOT)
            print(f"  {rel}:", file=sys.stderr)
            for err in t.errors:
                print(f"    - {err}", file=sys.stderr)
        if args.validate or args.fix:
            # Refuse to --fix while structural validation errors exist; a
            # malformed `done/` ticket could break done_ids construction.
            return 1

    # DX-5: detect stale blocked_by entries (references to done tickets).
    stale = find_stale_blocked_by(tickets)

    if args.fix:
        if stale:
            try:
                count, cleared = apply_unblock_fix(tickets)
            except RuntimeError as e:
                print(f"ERROR (--fix): {e}", file=sys.stderr)
                return 1
            print(f"Cleared {count} stale blocked_by entr{'y' if count == 1 else 'ies'}:")
            for tid, refs in cleared:
                print(f"  {tid}: no longer blocked by {', '.join(refs)}")
            # Re-discover: frontmatter has changed; INDEX must reflect it.
            tickets = discover_tickets(REPO_ROOT)
            # Re-validate to catch any post-fix oddity (should never trigger).
            post_errors = validate(tickets, epic_codes, synonyms)
            if post_errors:
                print(f"ERROR (--fix): {post_errors} validation error(s) appeared after fix — "
                      f"this should be impossible; inspect manually", file=sys.stderr)
                return 1
        else:
            print("Cleared 0 stale blocked_by entries (nothing to do).")

    index_md = render_index_md(tickets)
    index_json = render_index_json(tickets)
    md_path = REPO_ROOT / "INDEX.md"
    json_path = REPO_ROOT / "INDEX.json"

    if args.validate:
        # --validate treats stale entries as errors so commits that bypass
        # pre-commit (e.g. `--no-verify`, force-pushes) get caught in CI.
        if stale:
            print(f"Validation: {sum(len(refs) for _, refs, _ in stale)} stale blocked_by "
                  f"entr{'y' if sum(len(refs) for _, refs, _ in stale) == 1 else 'ies'} "
                  f"across {len(stale)} ticket(s)", file=sys.stderr)
            for t, stale_refs, _ in stale:
                rel = t.path.relative_to(REPO_ROOT)
                refs = ", ".join(stale_refs)
                print(f"  {rel}: blocked_by references done ticket(s): {refs}", file=sys.stderr)
            print("  Run `python scripts/build_index.py --fix` to auto-clear.", file=sys.stderr)
            return 1
        return 0 if errors_total == 0 else 1

    # DX-4: derive PROD-READINESS checkbox state from ticket frontmatter.
    pr_new_text, pr_changed, pr_changes = autotick_prod_readiness(tickets)

    if args.check:
        stale = []
        if not md_path.is_file() or _read_utf8(md_path) != index_md:
            stale.append("INDEX.md")
        if not json_path.is_file() or _read_utf8(json_path) != index_json:
            stale.append("INDEX.json")
        if pr_new_text is not None and _read_utf8(PROD_READINESS) != pr_new_text:
            stale.append("PROD-READINESS.md")
        if stale:
            label = "is" if len(stale) == 1 else "are"
            print(f"DRIFT: {', '.join(stale)} {label} stale. Run `python scripts/build_index.py`.", file=sys.stderr)
            # Surface which tickets caused the PROD-READINESS drift so CI logs
            # point at the cause without forcing a local re-run to learn.
            if pr_changes and "PROD-READINESS.md" in stale:
                print("  PROD-READINESS.md changes that would apply:", file=sys.stderr)
                for line_no, tid, mark in pr_changes:
                    flip = "→ [x]" if mark == "x" else "→ [ ]"
                    print(f"    line {line_no}: {tid} {flip}", file=sys.stderr)
            return 1
        print("INDEX.md + INDEX.json + PROD-READINESS.md are up-to-date.")
        return 0 if errors_total == 0 else 1

    md_path.write_text(index_md, encoding="utf-8")
    json_path.write_text(index_json, encoding="utf-8")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)} and {json_path.relative_to(REPO_ROOT)} "
          f"({len(tickets)} tickets)")
    if pr_new_text is None:
        pass  # PROD-READINESS.md missing — nothing to sync.
    elif pr_changed > 0:
        PROD_READINESS.write_text(pr_new_text, encoding="utf-8")
        print(f"Auto-ticked {pr_changed} PROD-READINESS checkbox(es)")
    else:
        print("PROD-READINESS.md in sync (0 changes)")
    # Plain mode (no --fix): warn about stale entries but don't fail.
    if not args.fix and stale:
        print(f"NOTE: {sum(len(refs) for _, refs, _ in stale)} stale blocked_by "
              f"entr{'y' if sum(len(refs) for _, refs, _ in stale) == 1 else 'ies'} "
              f"detected — run with --fix to auto-clear:")
        for t, stale_refs, _ in stale:
            rel = t.path.relative_to(REPO_ROOT)
            refs = ", ".join(stale_refs)
            print(f"  {rel}: blocked_by references done ticket(s): {refs}")
    return 0 if errors_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
