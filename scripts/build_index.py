#!/usr/bin/env python3
"""Build INDEX.md + INDEX.json from ticket frontmatter.

Walks `tickets/` and `hotfix/`, parses YAML frontmatter from each markdown
file, validates against the schema and the epic registry in GOVERNANCE.md,
and emits two artifacts at the repo root:

- `INDEX.md`  — human-readable, one table per status plus cross-links
- `INDEX.json` — machine-readable array for agent queries

Flags:
  --validate   run all checks and exit non-zero on any violation; skip write
  --check      regenerate and diff against committed INDEX.{md,json}; exit
               non-zero if drift (used by CI)

Zero external dependencies: stdlib `re` parses the frontmatter block so
we don't pull in PyYAML. The schema is simple (no nested structures).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOVERNANCE = REPO_ROOT / "GOVERNANCE.md"

VALID_STATUSES = {"backlog", "active", "blocked", "done"}

ID_RE = re.compile(r"^(?P<prefix>[A-Z]{2,8})-(?P<num>\d+(?:\.\d+)?)$")
HOTFIX_ID_RE = re.compile(r"^HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)

# Filename conventions
# - Tickets:  <ID>-<slug>.md    e.g. AUTH-1-login-flow.md
# - Hotfixes: <ID>.md           e.g. HF-2026-04-18-broken-deploy.md (ID already contains slug)
FILENAME_TICKET_RE = re.compile(r"^(?P<id>[A-Z]{2,8}-\d+(?:\.\d+)?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
FILENAME_HOTFIX_RE = re.compile(r"^(?P<id>HF-\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

# Fields that are lists (comma/YAML-list) — normalize to Python list
LIST_FIELDS = {"children", "blocks", "blocked_by", "repos"}
REQUIRED_FIELDS = {"id", "title", "epic", "status", "created"}

# Optional repos allow-list. If empty, repos field is free-form (no validation).
# To enforce a fixed set, populate this with the names of your sibling repos:
#   VALID_REPOS = {"backend", "frontend", "infra"}
VALID_REPOS: set[str] = set()


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
    column in bold (`**CODE**`).
    """
    codes: set[str] = set()
    for match in re.finditer(r"^\|\s*\*\*([A-Z]{2,8})\*\*\s*\|", governance_text, re.MULTILINE):
        codes.add(match.group(1))
    return codes


def parse_synonyms(governance_text: str) -> dict[str, str]:
    """Extract synonym-alias → canonical-epic mapping from GOVERNANCE.md."""
    synonyms: dict[str, str] = {}
    block = re.search(
        r"### Synonym aliases.*?\n(.*?)(?:\n---|\n## |\n### )", governance_text, re.DOTALL
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
            tickets.append(Ticket(path=md, frontmatter=fm))
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
        # status ↔ folder
        expected_folder = {"backlog": "tickets/backlog", "active": "tickets/active",
                           "blocked": "tickets/blocked", "done": "tickets/done"}
        if status in expected_folder:
            if expected_folder[status] not in str(t.path):
                t.errors.append(f"status {status!r} does not match folder {t.path.parent.name!r}")
        # next_action required on active tickets (session hygiene — GOVERNANCE §15.1)
        if status == "active":
            next_action = fm.get("next_action")
            if not next_action or str(next_action).strip().lower() in {"", "null", "none"}:
                t.errors.append("next_action required when status == active (GOVERNANCE §5 + §15.1)")
        # repos values must be a subset of VALID_REPOS, when VALID_REPOS is non-empty
        if VALID_REPOS:
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
                    help="validate only, no file output; exit 1 on any error")
    ap.add_argument("--check", action="store_true",
                    help="regenerate and diff vs committed INDEX files; exit 1 on drift")
    args = ap.parse_args()

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
        if args.validate:
            return 1

    index_md = render_index_md(tickets)
    index_json = render_index_json(tickets)
    md_path = REPO_ROOT / "INDEX.md"
    json_path = REPO_ROOT / "INDEX.json"

    if args.validate:
        return 0 if errors_total == 0 else 1

    if args.check:
        stale = []
        if not md_path.is_file() or md_path.read_text(encoding="utf-8") != index_md:
            stale.append("INDEX.md")
        if not json_path.is_file() or json_path.read_text(encoding="utf-8") != index_json:
            stale.append("INDEX.json")
        if stale:
            print(f"DRIFT: {', '.join(stale)} is stale. Run `python scripts/build_index.py`.", file=sys.stderr)
            return 1
        print("INDEX.md + INDEX.json are up-to-date.")
        return 0 if errors_total == 0 else 1

    md_path.write_text(index_md, encoding="utf-8")
    json_path.write_text(index_json, encoding="utf-8")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)} and {json_path.relative_to(REPO_ROOT)} "
          f"({len(tickets)} tickets)")
    return 0 if errors_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
