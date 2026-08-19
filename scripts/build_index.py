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
               their commit. Loud on any sub-step failure.

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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
GOVERNANCE = REPO_ROOT / "GOVERNANCE.md"
PROD_READINESS = REPO_ROOT / "PROD-READINESS.md"
STATUS_MD = REPO_ROOT / "STATUS.md"
# GOVERNANCE §15.3 tracked surface, deliberately OUTSIDE the STATUS snapshot:
# an uncapped ledger of time-deferred acceptance criteria from done tickets.
# §15.3 enforcement reads THIS file; the §18 snapshot cap deliberately
# excludes it (see validate_status_snapshot).
PENDING_VERIFICATIONS_MD = REPO_ROOT / "PENDING-VERIFICATIONS.md"

# =============================================================================
# TUNABLES — tune per project. Every policy number lives HERE, grouped, never
# buried in a function. Deliberately NOT CLI flags: raising a cap must cost a
# code edit + a GOVERNANCE amendment, so "I hit the cap" forces the question
# "what am I appending that belongs elsewhere?" rather than a reflexive bump.
# =============================================================================

# GOVERNANCE §18 — STATUS.md is a fixed-shape SNAPSHOT, not a history log.
# A hard size cap is the forcing function: a session that tries to PREPEND a
# new dated state block (instead of overwriting the single `## Current State`
# section) blows the cap and the commit is refused. History — SHAs, traps,
# root causes, lessons — belongs in ticket retrospectives. In the source
# project this file had grown to 440 lines / 120 KB across 22 stacked dated
# blocks before the cap existed; a trimmed honest snapshot is ~45 lines.
#
# The `## Pending Verifications` LEDGER used to live in STATUS and share this
# budget; it only grows (rows gate on triggers that keep not firing), so it
# starved the snapshot. It now lives in its own uncapped
# PENDING-VERIFICATIONS.md, and validate_status_snapshot() excludes any
# `## Pending Verifications` section from the measurement — while bounding that
# excluded region to a one-line pointer stub (STATUS_PV_STUB_MAX_*), so the
# exclusion can't be abused to smuggle unbounded content past the cap.
STATUS_MAX_LINES = 120
STATUS_MAX_BYTES = 16 * 1024

# The STATUS `## Pending Verifications` section must be ONLY a one-line
# pointer to PENDING-VERIFICATIONS.md. validate_status_snapshot strips it before
# measuring the snapshot cap; without a bound on the excluded region that strip
# would be an unlimited blind spot (history parked under the heading, or the
# ledger table pasted back into STATUS, would escape the §18 cap entirely). This
# stub cap flags the section the moment it grows past a pointer, so the
# exclusion can never become a cap-evasion route.
STATUS_PV_STUB_MAX_LINES = 12
STATUS_PV_STUB_MAX_BYTES = 1024

# GOVERNANCE §9.2 — the ROADMAP.md Execution queue is a PROMISE list, capped so
# it stays readable in one screen. A promise list that contains everything
# promises nothing: in the source project, before the cap, the queue section
# had grown to ~805 of the roadmap's 1049 lines.
QUEUE_CAP = 7

# GOVERNANCE §19.8 — the monthly health gauge (--health). The tripwire is a
# RATIO with a FLOOR, not an absolute zero: over a 30-day window a handful of
# root tickets always exists, so `n_root == 0` stayed silent in the source
# project at 95.5% spawned with creation 2.5x closure. The floor keeps a quiet
# month (n=1, trivially 100%) from crying wolf and training the reader to skip
# the line.
HEALTH_WINDOW_DAYS = 30
HEALTH_TRIPWIRE_SPAWNED_RATIO = 0.9
HEALTH_TRIPWIRE_MIN_CREATED = 10

# GOVERNANCE §20 — the session prompt. Same disease as §18, different file: it
# is a SNAPSHOT of how to start a session. In the source project it grew to
# 439 lines / 36 KB because two of its "keep verbatim" sections were
# append-only lists (a 28-entry session diary and a ~30-entry "deliberately
# not done" list); only ~38 lines were standing instructions.
#
# It lives HERE, tracked, with a `new_session` symlink at the project root so
# the reader's path does not change. Leaving it untracked was tried and cost
# real things: no history, no recovery, absent from a fresh clone, and
# invisible to CI (the "tracking costs a churn commit per session" premise was
# measured false — the meta repo takes commits daily anyway, so the prompt's
# diff rides one that already happens). Tracked, it gets all four back.
#
# Absent is an ERROR, not a skip (unlike STATUS_MD's bootstrap allowance): the
# file is committed, so a clone always has it, and "missing" means someone
# deleted the thing every session boots from.
NEW_SESSION_PROMPT = REPO_ROOT / "new_session.md"

# The global caps are the BACKSTOP against prose bloat. The targeted check is
# NEW_SESSION_RECENT_MAX_BULLETS: the section that actually grew was the session
# diary, and a global line cap alone would let it creep back by squeezing
# elsewhere. The caps sit far enough above an honest overwrite that it fits
# and a returning history log does not. As with §18 the caps are deliberately
# NOT CLI flags — raising one must cost a code edit plus a GOVERNANCE §20
# amendment.
NEW_SESSION_MAX_LINES = 140
NEW_SESSION_MAX_BYTES = 12 * 1024
NEW_SESSION_RECENT_MAX_BULLETS = 3

# The fixed shape (§20). Order is asserted, not just presence: the prompt is
# read top-to-bottom by a cold session, and "what am I doing" after "what is the
# state" is a different instruction than the reverse.
NEW_SESSION_SECTIONS = (
    "Boot",
    "First message",
    "Which ticket",
    "Where we got to",
    "This session",
    "State",
)
NEW_SESSION_RECENT_HEADING = "Where we got to"

# --- Markdown shapes the §20 checks parse ------------------------------------
#
# These exist because the first version of this guard matched GLYPHS, not
# markdown. Every one of the following was measured passing a file with 8-28
# session entries against a cap of 3, under every size cap: `* `, `+ `, `-<TAB>`,
# ` - ` (one leading space), `1. `, `1) `, and a 28-row TABLE. The cap counts
# SESSIONS, so it must recognise every way markdown expresses "an entry".
#
# A fenced code block is masked out before any of this runs: a fenced `## Boot`
# is not a section (it satisfied the whole shape check), and a fenced `## x`
# inside the diary is not a section boundary (it truncated the counted region).
FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
# CommonMark: bullet (`-`/`*`/`+`) or ordered (`1.`/`1)`) marker, up to three
# leading spaces, then a space or TAB. `\S` after it keeps an empty marker line
# from counting.
LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+\S")
# `- - -` / `***` / `___` is a horizontal rule, NOT a list item — matching it
# would report a separator as a session and reject a legitimate file.
THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
# A table's `|---|---|` delimiter row, and any pipe row. Body rows after the
# delimiter are entries; the header and the delimiter itself are not.
TABLE_DELIM_RE = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$")
TABLE_ROW_RE = re.compile(r"^ {0,3}\|")

VALID_STATUSES = {"backlog", "active", "blocked", "parked", "done"}

ID_RE = re.compile(r"^(?P<prefix>[A-Z]{2,8})-(?P<num>\d+(?:\.\d+)?)$")
HOTFIX_ID_RE = re.compile(r"^HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)

# Filename conventions
# - Tickets:  <ID>-<slug>.md    e.g. EX-1-example-feature.md
# - Hotfixes: <ID>.md           e.g. HF-YYYY-MM-DD-broken-deploy.md  (ID already contains slug)
FILENAME_TICKET_RE = re.compile(r"^(?P<id>[A-Z]{2,8}-\d+(?:\.\d+)?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
FILENAME_HOTFIX_RE = re.compile(r"^(?P<id>HF-\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

# Fields that are lists (comma/YAML-list) — normalize to Python list
LIST_FIELDS = {"children", "blocks", "blocked_by", "repos"}
REQUIRED_FIELDS = {"id", "title", "epic", "status", "created"}
# TUNE PER PROJECT: the allow-list for the `repos:` frontmatter field. Name
# your sub-repos here (e.g. {"backend", "frontend", "infra", "meta"}). Empty =
# free-form, no validation of repos entries.
VALID_REPOS: set[str] = set()

# GOVERNANCE §19 — priority answers "when do we do this", not "how bad is it".
# Only work that WAITS carries one: done/ is finished and parked/ is gated on a
# dated external trigger, so neither is waiting on us.
VALID_PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_REQUIRED_STATUSES = {"backlog", "active"}
# P0/P1 must name which of §19.4's five triggers applies, as fact. The validator
# can only check the line is non-empty — it cannot check the line is TRUE. That
# half is the owner confirming every P0/P1 (§19.4). This field raises the cost of
# inflating a priority and leaves a record; it does not make inflation impossible.
PRIORITY_JUSTIFIED = {"P0", "P1"}

# GOVERNANCE §19.4 + §9.3 — a `priority_because` that is empty, null, or a YAML
# block-scalar marker carries no information: parse_frontmatter is single-line
# by design, so a block scalar stores the MARKER as the value and the real
# sentence below it is silently dropped (caught in the wild in the source
# project the day §19 shipped). ONE helper, called from BOTH branches — a
# review round found one copy accepting ">-" while the other rejected it,
# the classic two-copies-disagree failure.
# The full family, not six literals: YAML block scalars admit indentation
# indicators (`>2`, `|2-`), which a hardcoded six-member set silently accepted
# as a "justification".
YAML_BLOCK_SCALAR_RE = re.compile(r"[>|][0-9]*[+-]?")


def because_problem(value: object) -> str | None:
    """Classify a priority_because value: 'missing' | 'marker' | None (usable)."""
    s = str(value).strip() if value is not None else ""
    if not s or s.lower() in {"null", "none"}:
        return "missing"
    if YAML_BLOCK_SCALAR_RE.fullmatch(s):
        return "marker"
    return None

# TUNE PER PROJECT: your CODE sub-repos, as sibling directory names relative to
# the meta repo's parent. Empty = the §15.1 merged-but-active ship gate reports
# itself UNAVAILABLE (never a silent pass) — name your repos to arm it. The
# gate also cannot run where the siblings are absent (e.g. meta-only CI); it
# says so there too. See validate_shipped_but_active().
SIBLING_REPOS: tuple[str, ...] = ()
# TUNE PER PROJECT: the trunk refs a merge can land on, in your branch model.
TRUNK_REFS = ("origin/develop", "origin/main")

# Ship-gate grandfather list. SHIPS EMPTY. A project adds entries ONLY via the
# documented adoption sweep — the one-time pass that adjudicates tickets which
# were already merged-but-active BEFORE the gate existed (each needs judgement
# per GOVERNANCE §15.3: tick with evidence · ledger row · drop with a /decide,
# not a bare file move).
#
# Why a grandfather list exists at all: without it the gate blocks `--fix`,
# i.e. the pre-commit hook, i.e. EVERY commit in the repo until the old debt is
# resolved. A hook that refuses unrelated work is a hook that gets
# `--no-verify`'d, which is precisely the bypass this gate exists to catch.
# Enforce forward, name the known debt.
#
# THIS LIST ONLY SHRINKS. Never add to it after the adoption sweep — a NEW
# merged-but-active ticket must block. When it is empty again, delete it and
# the branch that reads it.
SHIP_GATE_GRANDFATHERED: frozenset[str] = frozenset()


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
    column in bold (`**CODE**`). If the file also carries an OPTIONAL
    `### Reserved` section (codes pre-approved but not yet in use), its
    backticked codes are collected as valid too. The template's
    "Suggested-but-unseeded codes" section is deliberately NOT matched:
    a suggestion must pass the §10 add-epic gate before it is valid.
    """
    codes: set[str] = set()
    # Table rows like: | **AUTH** | ... | ... |
    for match in re.finditer(r"^\|\s*\*\*([A-Z]{2,8})\*\*\s*\|", governance_text, re.MULTILINE):
        codes.add(match.group(1))
    # Optional `### Reserved` block: backticked codes are valid-but-unused.
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
    for sub in ("tickets/backlog", "tickets/active", "tickets/blocked", "tickets/parked", "tickets/done", "hotfix"):
        folder = root / sub
        if not folder.is_dir():
            continue
        for md in sorted(folder.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                if md.name == "README.md":
                    # A frontmatter-less README is a folder doc, not a ticket —
                    # the template ships one in hotfix/. The skip is gated on
                    # the ABSENCE of frontmatter on purpose: a README that
                    # carries frontmatter is somebody's ticket saved under the
                    # wrong name, and it must fall through to fail the filename
                    # convention LOUDLY. An unconditional name-skip silently
                    # hid a fully-valid ticket from the INDEX, duplicate-ID
                    # detection and every gate (measured during review).
                    continue
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


# GOVERNANCE §15.3 — done tickets with unchecked acceptance criteria must
# carry a tracked-surface entry in `PENDING-VERIFICATIONS.md` (a dedicated,
# uncapped ledger, kept out of STATUS.md so the §18 snapshot cap
# can't starve it). Without that surface the verification trigger never reaches
# a future session: done tickets are invisible to session-start scans. This
# heading regex is reused BOTH to find the section in the ledger file and to
# strip it from STATUS.md before the §18 cap measurement.
PENDING_VERIFICATIONS_HEADING_RE = re.compile(
    r"^##\s+Pending Verifications\s*$", re.MULTILINE
)
# Capture ticket IDs cited in the first column of the `## Pending Verifications`
# table. Accepts both bare `EX-10` and backtick-wrapped `` `EX-10` `` forms.
PENDING_VERIFICATION_ROW_RE = re.compile(
    r"^\|\s*`?(?P<id>[A-Z]{2,8}-\d+(?:\.\d+)?|HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+)`?\s*\|",
    re.MULTILINE,
)
ACCEPTANCE_HEADING_RE = re.compile(r"^##\s+Acceptance criteria\s*$", re.MULTILINE)
# GOVERNANCE §17 — per-ticket compliance gate. A `sensitive: true` ticket must
# carry this section (the compliance impact assessment). `\b` after "Impact"
# lets the heading carry a parenthetical (e.g. "## Compliance Impact (SOC2)").
COMPLIANCE_HEADING_RE = re.compile(r"^##\s+Compliance Impact\b", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
UNCHECKED_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[\s\]", re.MULTILINE)


def parse_pending_verification_ids(ledger_text: str) -> set[str]:
    """Return the set of ticket IDs that appear in the first column of the
    `## Pending Verifications` table(s) in PENDING-VERIFICATIONS.md. Empty set
    if no such section exists (e.g. a fresh repo before any deferred AC ships).

    Unions across EVERY `## Pending Verifications` section, not just the first,
    so a ledger that ever grows a second heading (a split/pasted table) can't
    silently drop the rows under the later heading and false-block those
    tickets."""
    ids: set[str] = set()
    for heading in PENDING_VERIFICATIONS_HEADING_RE.finditer(ledger_text):
        section_start = heading.end()
        next_h2 = NEXT_H2_RE.search(ledger_text, section_start)
        section_end = next_h2.start() if next_h2 else len(ledger_text)
        section = ledger_text[section_start:section_end]
        ids.update(m.group("id") for m in PENDING_VERIFICATION_ROW_RE.finditer(section))
    return ids


def find_unchecked_criteria(ticket_text: str) -> list[str]:
    """Return the list of unchecked AC lines (raw text) in the ticket's
    `## Acceptance criteria` section. Empty list if the section is
    absent OR has no `[ ]` boxes."""
    heading_match = ACCEPTANCE_HEADING_RE.search(ticket_text)
    if not heading_match:
        return []
    section_start = heading_match.end()
    next_h2 = NEXT_H2_RE.search(ticket_text, section_start)
    section_end = next_h2.start() if next_h2 else len(ticket_text)
    section = ticket_text[section_start:section_end]
    return [m.group(0).strip() for m in UNCHECKED_CHECKBOX_RE.finditer(section)]


# TUNE PER PROJECT (only when adopting into an EXISTING ticket corpus):
# forward-only effective dates. A fresh project leaves these None — every
# ticket is enforced. If you import a corpus that predates a rule, set the
# ISO date you adopted it; tickets whose `updated:` predates it are
# grandfathered rather than bulk-backfilled dishonestly.
SECTION_15_3_EFFECTIVE_DATE: str | None = None   # GOVERNANCE §15.3 (deferred acceptance criteria)
COMPLIANCE_GATE_EFFECTIVE_DATE: str | None = None  # GOVERNANCE §17 (sensitive-data gate)


def _grandfathered(updated: str, effective_date: str | None) -> bool:
    """True only when BOTH dates parse as ISO and `updated` is strictly older.

    PARSED comparison, never lexicographic, and malformed input fails CLOSED
    (enforce): with an effective date set, a raw string compare silently
    grandfathered a done ticket whose `updated` was `07/30/2026` — US date
    format — because '0' < '2' (measured during review). A compliance gate
    that fails open on a malformed date is the §Step-0d guard-returns-nothing
    failure wearing a calendar.
    """
    if not effective_date or not updated:
        return False
    try:
        return _dt.date.fromisoformat(updated) < _dt.date.fromisoformat(effective_date)
    except ValueError:
        return False


def validate_done_unchecked_criteria(
    tickets: list[Ticket],
    pending_verification_ids: set[str],
) -> None:
    """GOVERNANCE §15.3 enforcement. For each done ticket with `[ ]` acceptance criteria
    that was updated on/after SECTION_15_3_EFFECTIVE_DATE: reject unless
    the ticket's ID is named in `PENDING-VERIFICATIONS.md`.
    Mutates ticket.errors in place."""
    for t in tickets:
        if str(t.frontmatter.get("status", "")) != "done":
            continue
        updated = str(t.frontmatter.get("updated", "")).strip()
        if _grandfathered(updated, SECTION_15_3_EFFECTIVE_DATE):
            # Pre-adoption legacy ticket. Skip silently — operator may
            # bulk-tick as a separate cleanup pass.
            continue
        try:
            text = t.path.read_text(encoding="utf-8")
        except OSError as exc:
            t.errors.append(f"could not re-read ticket for AC scan: {exc}")
            continue
        unchecked = find_unchecked_criteria(text)
        if not unchecked:
            continue
        if t.id not in pending_verification_ids:
            t.errors.append(
                f"done ticket has {len(unchecked)} unchecked acceptance "
                f"criteri{'a' if len(unchecked) > 1 else 'on'} but no entry "
                f"in `PENDING-VERIFICATIONS.md` (GOVERNANCE §15.3 — migrate "
                f"deferred acceptance criteria to the tracked ledger before ship, or tick them)"
            )


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Run git in `repo`; return (returncode, stdout). Never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"<git unavailable: {exc}>"
    return proc.returncode, proc.stdout


def _branch_holds_unmerged_work(
    repo: Path,
    branch: str,
    local_heads: set[str],
    trunk_refs: list[str],
    id_re: re.Pattern[str],
) -> bool | None:
    """True when `branch` holds a commit whose SUBJECT names this ticket, off trunk.

    Tri-state. `None` means UNANSWERABLE — a git command failed — and the caller
    must report the run unavailable rather than fall through to "merged". Without
    that, a broken local git turns every active ticket into a false MERGED finding,
    which is the loudest possible way to be wrong (found by a second-model review).

    SUBJECT, not subject+body, and the asymmetry is deliberate. The two predicates
    fail in opposite directions:
      - predicate 2 ("does it look merged") too narrow -> a real merge is MISSED,
        silently. So it stays broad (subject+body).
      - this exemption ("is it still in flight") too broad -> a real merge is
        EXEMPTED, silently. So it stays narrow.
    A body cross-reference (`See EX-99`) in someone else's WIP commit was enough
    to exempt a merged EX-99 while this matched bodies — constructed and
    confirmed in the source project. Matching subjects only costs a false
    POSITIVE for a non-primary ticket on a shared branch whose commits name it
    only in bodies, and a false positive here is loud, arguable, and safe.

    Tells NEVER-PUSHED from DELETED-AFTER-MERGE, which `git ls-remote` structurally
    cannot (it reports an absence, not a history). See `validate_shipped_but_active`
    docstring hole 1.

    IT MUST BE THIS TICKET'S COMMITS, NOT ANY COMMIT — the first version of this
    helper asked only "does the branch have unmerged commits", and that HID REAL
    FINDINGS. GOVERNANCE §7 puts several tickets on one increment branch on
    purpose. So after ticket A merged, a single later ticket-B commit on the
    shared branch would have exempted A — the gate silently passing on exactly
    the state it exists to catch, which is worse than the false positive it was
    written to remove. Caught by a second-model review of this diff before it
    shipped in the source project.

    Returns False when no trunk resolved: with nothing to diff against, "unmerged"
    is unanswerable, and answering True would exempt every ticket — a gate that
    cannot fail. The caller reports the whole run unavailable in that case rather
    than treating it as clean.
    """
    if not trunk_refs or branch not in local_heads:
        return False
    rc, out = _git(
        repo, "log", branch, *[f"^{ref}" for ref in trunk_refs], "--format=%s"
    )
    if rc != 0:
        return None  # unanswerable — never silently "not in flight"
    return bool(id_re.search(out))


def validate_shipped_but_active(tickets: list[Ticket]) -> tuple[list[str], str | None]:
    """GOVERNANCE §15.1 + §19 — a ticket whose work has MERGED must not be `active`.

    Returns (errors, unavailable_reason). `unavailable_reason` is non-None when
    the check could not run; callers must SAY SO rather than treat it as a pass.

    Why this check exists: in the source project, `active/` accumulated 32
    tickets whose code had all merged — the work shipped and only the paperwork
    was behind. The pre-existing validator could not see it, because
    `status: active` + a `next_action` is a legal state with no expiry. This is
    the missing expiry.

    The signal is deliberately NOT "has commits on trunk". A project that merges
    a feature branch to trunk repeatedly (to exercise staging) has mid-flight
    tickets with trunk commits, legitimately. The tight signal is the pair:

        the ticket's `branch:` is GONE from the remote   (merge-then-delete)
      AND commits naming its ID exist on trunk           (it really did land)

    CORRECTED in the source project — BOTH halves of that pair were satisfiable
    by a non-merge, and the two holes were invisible in each half alone. The gate
    fired `exit 1` on a ticket with ZERO commits anywhere near trunk, blocking
    every meta commit — which is how a hook gets `--no-verify`'d, the exact
    failure mode this gate exists to prevent.

      1. "GONE from the remote" could not distinguish DELETED-AFTER-MERGE from
         NEVER-PUSHED. `ls-remote` sees an absence, not a history. So the
         docstring's own safety argument — "a ticket still in flight keeps its
         remote branch, so it never trips" — was FALSE for every ticket between
         `/ticket-start` and its first push, i.e. for the normal opening state of
         all work, not an edge case.
         Fix: a branch that exists LOCALLY and holds commits on no trunk is in
         flight, whatever the remote says. Note this cannot weaken the gate — after
         a normal merge the branch's commits ARE on trunk, so the exemption is
         empty and the finding still fires (verified below).

    HOLE 2 — REAL, MEASURED IN THE SOURCE PROJECT, AND DELIBERATELY *NOT* FIXED
    HERE. "commits naming its ID" matches the ID anywhere in subject OR body, so
    a MENTION counts as a merge.

    The obvious fix — match `%s` only — was implemented, measured, and REVERTED
    the same hour. GOVERNANCE §8 reads in full: "PRs that touch multiple tickets:
    list all IDs in the body, **primary ID in title**." Combined with §7 ("one
    branch carries an INCREMENT, which may be several tickets"), a non-primary
    ticket's ID legitimately appears ONLY in a body. Measured against the five
    then-known merged-but-active tickets: three had **zero** subject hits and
    body hits only — all three shipped as non-primary members of a shared
    increment branch. Subject-only matching made the gate blind to 3 of 5, i.e.
    it traded a false POSITIVE for a false NEGATIVE in the majority of real
    cases. Strictly worse: this gate's whole purpose is catching what `active/`
    hides.

    A cross-reference and a secondary-ownership claim are the same bytes in the
    same field, so no regex separates them. Fixing hole 2 needs a different
    signal (an explicit `tickets:` commit trailer, or matching against the
    branch's own commit set) — real work, file a ticket rather than guess.

    A second round of the same review then found the hole-1 fix incomplete twice
    more, and both are closed above: the exemption matched subject+body (so a
    body cross-reference exempted a merged ticket), and a failed git command fell
    through to a MERGED finding instead of reporting unavailable.

    WHERE THIS RUNS: the working tree where the SIBLING_REPOS directories are
    siblings of this meta repo. A meta-only CI checkout has no siblings, so the
    check reports itself unavailable there rather than passing silently. Closing
    that gap needs a cross-repo CI job with a token to read meta from the
    sub-repos — real work, file it rather than pretend.
    """
    if not SIBLING_REPOS:
        return [], (
            "SIBLING_REPOS is empty — name your code repos at the top of "
            "scripts/build_index.py to arm the merged-but-active ship gate. "
            "The gate did NOT run (unconfigured is reported, never a silent "
            "pass), and the branch-required check on active tickets is inert "
            "until it is configured too."
        )
    parent = REPO_ROOT.parent
    repos = {name: parent / name for name in SIBLING_REPOS}
    present = {name: path for name, path in repos.items() if (path / ".git").exists()}
    if not present:
        return [], (
            f"sibling repos {list(SIBLING_REPOS)} not found next to {REPO_ROOT.name}/ "
            f"— the merged-but-active gate did NOT run (expected in meta-only CI; "
            f"it runs in the working tree where the sibling repos are present)"
        )

    # One log read AND one branch listing per repo, then match in Python. Both
    # are per-REPO, never per-ticket: `ls-remote` is a network round-trip, and
    # this runs in a pre-commit hook — measured in the source project, dozens of
    # tickets times repos of round-trips turned a sub-second validator into a
    # multi-minute one, and a slow hook is a hook that gets `--no-verify`'d,
    # which is the failure mode this gate exists to catch. A handful of calls is
    # affordable; a hundred is not.
    #
    # It MUST be `ls-remote` and not the local `refs/remotes/origin/*` tracking
    # refs. `git fetch` without `--prune` keeps a tracking ref for a branch that
    # was deleted on the server, so the local view still lists merged branches
    # as alive — measured in the source project: 12 local tracking refs against
    # 9 real branches. Reading them made this gate report ZERO findings against
    # 32 real ones: a check that cannot fail.
    trunk_log: dict[str, str] = {}
    remote_branches: dict[str, set[str]] = {}
    local_branches: dict[str, set[str]] = {}
    resolved_trunks: dict[str, list[str]] = {}
    unreachable: list[str] = []
    unreadable_heads: list[str] = []
    stale_trunk: list[str] = []
    for name, path in present.items():
        # Read EVERY trunk that resolves, not just the first. A repo can hold
        # both `develop` and `main`; stopping at `develop` misses a ticket whose
        # work landed on `main` (hotfix, or a meta-style single-trunk sub-repo).
        logs: list[str] = []
        local_trunk: dict[str, str] = {}
        for ref in TRUNK_REFS:
            rc, sha = _git(path, "rev-parse", "--verify", "--quiet", ref)
            if rc != 0:
                continue
            local_trunk[ref.split("/", 1)[1]] = sha.strip()
            resolved_trunks.setdefault(name, []).append(ref)
            # Subject AND body. Narrowing to `%s` was TRIED and REVERTED — see
            # docstring §"Hole 2 … not fixed here"; GOVERNANCE §8 puts secondary
            # ticket IDs in the body on purpose.
            rc, out = _git(path, "log", ref, "--format=%s%n%b")
            if rc == 0:
                logs.append(out)
        if logs:
            trunk_log[name] = "\n".join(logs)
        # Local heads, one listing per repo — used to tell NEVER-PUSHED from
        # DELETED-AFTER-MERGE (docstring hole 1). Local and cheap; no round-trip.
        rc, out = _git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads")
        if rc != 0:
            # An empty set here reads as "no local branches", which makes every
            # in-flight ticket look MERGED. Unanswerable is UNAVAILABLE.
            # Do NOT `continue` — skipping the ls-remote below makes the repo look
            # UNREACHABLE instead, which reports the wrong cause (measured).
            unreadable_heads.append(name)
        else:
            local_branches[name] = {
                line.strip() for line in out.splitlines() if line.strip()
            }
        rc, out = _git(path, "ls-remote", "--heads", "origin")
        if rc != 0:
            unreachable.append(name)
            continue
        heads: set[str] = set()
        remote_sha: dict[str, str] = {}
        for line in out.splitlines():
            if "refs/heads/" not in line:
                continue
            sha, _, ref = line.partition("\t")
            head = ref.split("refs/heads/", 1)[1].strip()
            heads.add(head)
            remote_sha[head] = sha.strip()
        remote_branches[name] = heads
        # The branch list comes from the server, but the COMMIT evidence comes
        # from the local trunk ref, which is only as fresh as the last fetch.
        # Staleness there can only DELAY a finding (a commit not yet fetched is
        # a commit we don't see) — unlike the branch list, where staleness was a
        # permanent miss. Say so rather than assume it.
        for tname, lsha in local_trunk.items():
            if tname in remote_sha and remote_sha[tname] != lsha:
                stale_trunk.append(f"{name}/{tname}")
    if unreadable_heads:
        return [], (
            f"could not enumerate local branches for {sorted(unreadable_heads)} — the "
            f"merged-but-active gate is UNAVAILABLE rather than clean. An unreadable head "
            f"list reads as 'no local branches', which would make every in-flight ticket "
            f"look merged."
        )
    if not remote_branches:
        return [], (
            f"could not reach the remote for any of {sorted(present)} — the "
            f"merged-but-active gate did NOT run (offline? no `origin`?). It reads "
            f"`git ls-remote`, because local remote-tracking refs go stale and would "
            f"make this check silently pass"
        )
    if unreachable:
        # A PARTIAL outage is not a pass. Tickets whose work lives in an
        # unreachable repo cannot be judged, and saying nothing about them reads
        # exactly like judging them clean.
        return [], (
            f"remote unreachable for {sorted(unreachable)} (reached: "
            f"{sorted(remote_branches)}) — the merged-but-active gate is INCOMPLETE "
            f"and its result is being discarded rather than reported as a partial pass"
        )
    if stale_trunk:
        print(f"NOTE: local trunk ref behind the remote for {sorted(stale_trunk)} — "
              f"the merged-but-active gate may miss a recent merge until you fetch",
              file=sys.stderr)
    # A repo whose trunk we could not read contributes NO commit evidence, so every
    # ticket scoped to it is skipped at `log is None` below — which returns the same
    # empty list as "graded them all, none merged". That is the guard-returns-nothing
    # failure this file already guards for the REMOTE half, and it was missing for
    # the LOCAL half (found by a second-model review). Unanswerable is UNAVAILABLE.
    # Scoped PER TICKET below, not globally: a repo with no readable trunk that no
    # ticket declares is irrelevant, and discarding every finding because of it would
    # be its own silent pass (found by a second-model review of the first version,
    # which computed this over every present sibling).
    no_trunk = set(present) - set(trunk_log)

    errors: list[str] = []
    grandfathered: list[str] = []
    unanswerable: list[str] = []
    for t in tickets:
        if t.status != "active" or t.id.startswith("HF-"):
            continue
        branch = t.frontmatter.get("branch")
        if not branch or str(branch).strip().lower() in {"", "null", "none"}:
            continue  # no branch declared — nothing to test against
        branch = str(branch).strip()
        # `(?![0-9])` alone lets EX-1 match an EX-1.1 commit — the ID scheme
        # permits historical decimal IDs (ID_RE: `\d+(?:\.\d+)?`), so one
        # ticket's merge would be attributed to another. Forbid a
        # following digit AND a following `.digit`, while still allowing a
        # sentence-ending "EX-1." to match.
        id_re = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(t.id)}(?![0-9]|\.[0-9])")
        # Scope to the repos the ticket DECLARES. Scanning every present repo
        # lets a backend commit that happens to name the ID force-ship a ticket
        # whose frontend half is unfinished. `repos: []` (undeclared) falls back
        # to all present repos — the pre-existing behaviour, and the reason
        # `repos:` should be filled.
        declared = [r for r in (t.frontmatter.get("repos") or []) if r in present]
        scope = declared or list(present)
        # A repo IN THIS TICKET'S SCOPE whose trunk we could not read contributes no
        # commit evidence, so the loop below would skip it and the ticket would come
        # out clean — indistinguishable from "graded, not merged" (§Step 0d).
        blind = sorted(no_trunk.intersection(scope))
        if blind:
            unanswerable.append(f"{t.id} (no readable trunk in {', '.join(blind)})")
            continue
        for name in scope:
            log = trunk_log.get(name)
            if log is None or not id_re.search(log):
                continue
            heads = remote_branches.get(name)
            if heads is None:
                continue  # remote unreachable for this repo — don't guess
            if branch in heads:
                continue  # branch still on the remote → genuinely in flight
            in_flight = _branch_holds_unmerged_work(
                present[name], branch, local_branches.get(name, set()),
                resolved_trunks.get(name, []), id_re,
            )
            if in_flight is None:
                # git failed. Claiming MERGED on a failed command is the loudest
                # possible way to be wrong; withhold and report.
                unanswerable.append(f"{t.id} (git log failed on {branch!r} in {name})")
                break
            if in_flight:
                continue  # a commit SUBJECT on this branch names the ticket, off trunk
            if t.id in SHIP_GATE_GRANDFATHERED:
                grandfathered.append(t.id)
                break
            errors.append(
                f"{t.id}: branch {branch!r} is gone from {name}'s remote and commits "
                f"naming {t.id} are on trunk — the work MERGED but the ticket is still "
                f"`active`. Run /ticket-ship (GOVERNANCE §15.1: merged work ships, "
                f"it does not pause)."
            )
            break
    if grandfathered:
        print(f"NOTE: {len(grandfathered)} merged-but-active ticket(s) GRANDFATHERED "
              f"(adoption-sweep remainder, unticked acceptance criteria pending §15.3 adjudication): "
              f"{', '.join(sorted(grandfathered))}", file=sys.stderr)
    if unanswerable:
        # Findings for the tickets we COULD grade are still returned — dropping them
        # would be a second silent pass. What must not happen is the ungraded ones
        # reading as clean.
        return errors, (
            f"{len(unanswerable)} ticket(s) could not be graded by the merged-but-active "
            f"gate and are reported UNVERIFIED, not clean: {'; '.join(sorted(unanswerable))}"
        )
    return errors, None


def validate_repos_config() -> list[str]:
    """SIBLING_REPOS / VALID_REPOS coherence (see the tunables block).

    A `repos:` typo must not silently blind the §15.1 ship gate: the gate
    scopes to the repos a ticket DECLARES, and the branch-required check
    derives from SIBLING_REPOS ∩ repos — so with no allow-list, a one-letter
    typo (`repos: [backened]`) makes a ticket permanently invisible to both,
    with no error anywhere (measured during review of this port). Arming the
    gate therefore requires the allow-list, and the gate's repo names must be
    inside it.
    """
    errors: list[str] = []
    if SIBLING_REPOS and not VALID_REPOS:
        errors.append(
            "SIBLING_REPOS is configured but VALID_REPOS is empty — without the "
            "allow-list a repos: typo silently hides a ticket from the §15.1 "
            "merged-but-active gate and the branch-required check. Set "
            "VALID_REPOS to your full repo set (code repos + meta) in "
            "scripts/build_index.py."
        )
    elif VALID_REPOS:
        unknown = set(SIBLING_REPOS) - VALID_REPOS
        if unknown:
            errors.append(
                f"SIBLING_REPOS entr{'y' if len(unknown) == 1 else 'ies'} "
                f"{sorted(unknown)} not in VALID_REPOS — the ship gate would scope "
                f"to repo names the allow-list rejects; align the two tunables."
            )
    return errors


GATE_MARKER_RE = re.compile(r"^>\s*#+\s*`>>> CURRENT GATE <<<`", re.MULTILINE)


def validate_current_gate() -> list[str]:
    """GOVERNANCE §19.1 — ROADMAP.md names EXACTLY ONE current gate.

    Every P1 is defined as "blocks the current gate". Two gates make P1
    ambiguous; zero makes it undefined — and in both cases the level still
    validates, so nothing else would ever notice. The pointer is the whole
    reason the levels survive a change of vertical, so it needs a check.
    """
    roadmap = REPO_ROOT / "ROADMAP.md"
    if not roadmap.is_file():
        return ["ROADMAP.md not found — the §19.1 current gate has no home"]
    n = len(GATE_MARKER_RE.findall(roadmap.read_text(encoding="utf-8")))
    if n == 1:
        return []
    return [
        f"ROADMAP.md declares {n} `>>> CURRENT GATE <<<` block(s), expected exactly 1 "
        f"(GOVERNANCE §19.1 — every P1 points at it; {'ambiguous' if n > 1 else 'undefined'} otherwise)"
    ]


# GOVERNANCE §9.2 markers — QUEUE_CAP itself lives in the tunables block above.
QUEUE_BEGIN = "<!-- queue:begin"
QUEUE_END = "<!-- queue:end"


def validate_queue_cap(tickets: list[Ticket] | None = None) -> list[str]:
    """GOVERNANCE §9.2 — the Execution queue holds at most QUEUE_CAP live items.

    Counts numbered entries (`N. ...`) between the queue:begin / queue:end
    markers. Missing markers are an ERROR, not a pass — a format drift that
    silently disabled this check would be the classic guard-that-cannot-fail.
    """
    roadmap = REPO_ROOT / "ROADMAP.md"
    if not roadmap.is_file():
        return ["ROADMAP.md not found — the §9.2 queue cap has no home"]
    text = roadmap.read_text(encoding="utf-8")
    # Exactly ONE pair, in order. find()-first-occurrence would silently count
    # only the first of two sections (a real undercount, executed during
    # review) and would blame a "missing" marker when a prose mention sat
    # above the real block — so duplicates are named, not skipped.
    n_begin = text.count(QUEUE_BEGIN)
    n_end = text.count(QUEUE_END)
    if n_begin != 1 or n_end != 1:
        return [
            f"ROADMAP.md must contain the queue:begin / queue:end markers exactly once "
            f"each (found begin x{n_begin}, end x{n_end}) — a duplicate or missing marker "
            f"would make this check count the wrong region, which is a failure, not a "
            f"pass (GOVERNANCE §9.2)"
        ]
    begin = text.find(QUEUE_BEGIN)
    end = text.find(QUEUE_END)
    if end < begin:
        return [
            "ROADMAP.md queue markers are out of order — queue:end appears before "
            "queue:begin (GOVERNANCE §9.2)"
        ]
    section = text[begin:end]
    # Exempt ONLY a BARE fully-struck entry: strip every ~~…~~ span; if anything
    # but the item number survives, the line is a LIVE promise. Closes, in
    # order: the whole-line `"~~" in ln` escape (first review), the greedy
    # `~~.*~~` both-ends-struck-live-middle hole (re-review N1), and it makes
    # the repo's historical annotated strike (`N. ~~X~~ **DONE …** — #PR`)
    # count live BY DESIGN — the cap then forces the same-day move to
    # QUEUE-LOG.md instead of letting annotated corpses pile up in place.
    def _is_live(ln: str) -> bool:
        if not re.match(r"^\d+\.\s", ln):
            return False
        if "~~" not in ln:
            return True
        remainder = re.sub(r"~~.*?~~", "", ln)
        remainder = re.sub(r"^\d+\.\s*", "", remainder).strip()
        return remainder != ""

    live = [ln for ln in section.splitlines() if _is_live(ln)]
    errors: list[str] = []
    if len(live) > QUEUE_CAP:
        errors.append(
            f"Execution queue holds {len(live)} live items; the cap is {QUEUE_CAP} "
            f"(GOVERNANCE §9.2 — adding an item names the item it displaces; "
            f"shipped entries move to QUEUE-LOG.md)"
        )
    # §9.2 membership: a P0/P1 is a promise by definition ("P1 becomes next"),
    # so it must APPEAR in the promise list. Without this, the failure §9.2 was
    # written to stop — filed, indexed, validator-green, absent from the only
    # document that says what happens next — stays reproducible for exactly
    # the tickets that matter most.
    for t in tickets or []:
        if t.status not in {"backlog", "active", "blocked"}:
            continue
        tid = t.id or ""
        if tid.startswith("HF-"):
            continue
        pri = str(t.frontmatter.get("priority") or "").strip()
        if pri in {"P0", "P1"} and tid and not re.search(rf"\b{re.escape(tid)}\b", section):
            errors.append(
                f"{tid} is {pri} but appears nowhere in the Execution queue — a P0/P1 "
                f"is a promise and must be slotted (GOVERNANCE §9.2 + §19.5)"
            )
    return errors


def validate_compliance_section(tickets: list[Ticket]) -> None:
    """GOVERNANCE §17 enforcement. A ticket flagged `sensitive: true` (updated
    on/after COMPLIANCE_GATE_EFFECTIVE_DATE, when set) must carry a
    `## Compliance Impact` section — the per-ticket assessment that records the
    regulated-data surface + the controls touched. Forward-only grandfather
    mirrors §15.3. Mutates ticket.errors in place."""
    for t in tickets:
        if str(t.frontmatter.get("sensitive", "")).strip().lower() != "true":
            continue
        updated = str(t.frontmatter.get("updated", "")).strip()
        if _grandfathered(updated, COMPLIANCE_GATE_EFFECTIVE_DATE):
            continue
        try:
            text = t.path.read_text(encoding="utf-8")
        except OSError as exc:
            t.errors.append(f"could not re-read ticket for compliance scan: {exc}")
            continue
        if not COMPLIANCE_HEADING_RE.search(text):
            t.errors.append(
                "sensitive:true ticket missing '## Compliance Impact' section "
                "(GOVERNANCE §17 — assess compliance impact before ship)"
            )


def _count_lines(text: str) -> int:
    """Count lines the way `wc -l` does, plus a trailing partial line if any."""
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def _split_pending_verifications(text: str) -> tuple[str, str | None]:
    """Split out the FIRST `## Pending Verifications` section (its heading
    through to the next `## ` heading, or EOF).

    Returns (text_without_that_section, the_section_text_or_None). Used by
    validate_status_snapshot so the §18 snapshot cap measures genuine snapshot
    content only — the Pending Verifications LEDGER lives in its own uncapped
    PENDING-VERIFICATIONS.md, so its STATUS footprint should be nothing
    more than a one-line pointer. The caller separately bounds the returned
    section (STATUS_PV_STUB_MAX_*) so this exclusion can't become a blind spot.

    Only the first section is split: a second `## Pending Verifications` heading
    (unusual) is left in `text_without`, so it still counts toward the cap —
    the safe direction (bloat is caught, not hidden)."""
    m = PENDING_VERIFICATIONS_HEADING_RE.search(text)
    if not m:
        return text, None
    next_h2 = NEXT_H2_RE.search(text, m.end())
    end = next_h2.start() if next_h2 else len(text)
    return text[: m.start()] + text[end:], text[m.start() : end]


def validate_status_snapshot() -> list[str]:
    """GOVERNANCE §18 enforcement. STATUS.md is a fixed-shape snapshot, not a
    history log — enforce a hard line + byte cap so a session physically cannot
    prepend a new dated block instead of overwriting the single
    `## Current State` section.

    The `## Pending Verifications` ledger is EXCLUDED from the snapshot
    measurement (it is a legitimately-growing tracked surface that now lives in
    its own uncapped PENDING-VERIFICATIONS.md), BUT the excluded section
    is separately bounded to a one-line pointer stub (STATUS_PV_STUB_MAX_*), so
    the exclusion cannot be abused to smuggle unbounded content past the cap.

    Repo-level, unlike the sibling validators: validate_done_unchecked_criteria /
    validate_compliance_section mutate each ticket's .errors and return None;
    this returns its own list of error strings (empty = clean) because the cap
    is a property of one file, not of any ticket."""
    # Absent STATUS.md is fine (fresh-clone bootstrap) — skip silently. A file
    # that exists but won't read is a hard error (returned below, not swallowed).
    if not STATUS_MD.is_file():
        return []
    try:
        raw = STATUS_MD.read_bytes()
    except OSError as exc:
        return [f"STATUS.md could not be read: {exc}"]
    # STATUS.md is authored as UTF-8; decode/split/re-encode round-trips
    # byte-for-byte for valid input (invalid bytes only ever grow via U+FFFD, so
    # the byte cap stays conservative — an oversized file can't be shrunk under).
    measured, pv_section = _split_pending_verifications(raw.decode("utf-8", errors="replace"))
    # Line cap forces overwrite-not-append; byte cap stops a few giant
    # paragraph-lines from smuggling the history back under the line cap. The
    # two checks are independent — a file can blow one, both, or neither.
    errors: list[str] = []
    n_bytes = len(measured.encode("utf-8"))
    n_lines = _count_lines(measured)
    if n_lines > STATUS_MAX_LINES:
        errors.append(
            f"STATUS.md is {n_lines} lines excluding Pending Verifications "
            f"(cap {STATUS_MAX_LINES}). It is a snapshot, not a history log — "
            f"OVERWRITE the `## Current State` section, do not prepend a new "
            f"dated block. Move history to the shipping ticket's "
            f"`## Retrospective` (GOVERNANCE §18)."
        )
    if n_bytes > STATUS_MAX_BYTES:
        errors.append(
            f"STATUS.md is {n_bytes} bytes excluding Pending Verifications "
            f"(cap {STATUS_MAX_BYTES}). Trim to the current snapshot; history → "
            f"ticket retrospectives (GOVERNANCE §18)."
        )
    # Stub guard: the excluded section must be a pointer, not the ledger.
    # Catches the ledger table pasted back into STATUS, or history parked under
    # the `## Pending Verifications` heading — either would otherwise ride free
    # inside the excluded region.
    if pv_section is not None:
        pv_bytes = len(pv_section.encode("utf-8"))
        pv_lines = _count_lines(pv_section)
        if pv_lines > STATUS_PV_STUB_MAX_LINES or pv_bytes > STATUS_PV_STUB_MAX_BYTES:
            errors.append(
                f"STATUS.md `## Pending Verifications` is {pv_lines} lines / "
                f"{pv_bytes} bytes — it must be only a one-line pointer to "
                f"PENDING-VERIFICATIONS.md (stub cap {STATUS_PV_STUB_MAX_LINES} "
                f"lines / {STATUS_PV_STUB_MAX_BYTES} bytes). The ledger lives in "
                f"PENDING-VERIFICATIONS.md — move any rows there (GOVERNANCE §18 / §15.3)."
            )
    return errors


def _mask_fenced_blocks(lines: list[str]) -> list[str]:
    """Blank out every line inside a fenced code block, keeping line count.

    Nothing inside a fence is structure: a fenced `## Boot` is an EXAMPLE of a
    heading, not a heading. Measured on the unmasked parser — a file whose only
    content was a fence listing the six §20 headings passed the entire shape
    check with zero real sections, and a fence containing `## x` inside the
    diary truncated the counted region so 15 session entries passed a cap of 3.
    The same blindness produced a FALSE POSITIVE: a fence quoting the headings
    in a different order raised "sections are out of order" on a valid file,
    which with `always_run: true` would block every commit in this repo.

    Indices are preserved (masked lines become "") so callers can map a match
    back to its line number."""
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group("fence")
                out.append("")
                continue
            out.append(line)
            continue
        out.append("")
        # A fence closes on the same character, at least as long as the opener.
        if m and m.group("fence")[0] == fence[0] and len(m.group("fence")) >= len(fence):
            fence = None
    return out


def _session_entries(lines: list[str]) -> int:
    """Count the SESSIONS a `## Where we got to` section lists.

    The cap is on how many sessions are listed, not on how much is said about
    each, so a wrapped bullet's indented continuation lines and nested
    sub-bullets are not entries.

    It counts ENTRIES, not one bullet syntax. The first version matched `- `
    alone and every one of these passed a 28-session diary against a cap of 3,
    under every size cap (each measured, not reasoned): `* `, `+ `, `-<TAB>`,
    ` - ` (one leading space, still a top-level list in CommonMark), `1. `,
    `1) `, and a 28-row markdown TABLE. Reformatting a dated list as a table is
    an ordinary edit, which made it the likeliest silent evasion of them all.

    A `- - -` horizontal rule is NOT an entry — counting it would report a
    separator as a session and reject a legitimate file.

    Nesting is resolved by CommonMark's rule, not by an indent guess: an item
    indented to at least the open item's CONTENT column belongs to that item;
    anything shallower starts a new top-level entry. A fixed `^ {0,3}` test
    cannot express this — it counted the live file's own `  - nested` line as a
    fourth session while still needing to accept ` - ` (one space) as top-level
    when no item is open."""
    n = 0
    in_table_body = False
    content_col: int | None = None  # content column of the open top-level item
    for line in lines:
        if TABLE_DELIM_RE.match(line) and "|" in line:
            # The `|---|---|` row: everything after it is body until the table
            # ends. The header row above it is not an entry.
            in_table_body = True
            continue
        if in_table_body:
            if TABLE_ROW_RE.match(line):
                n += 1
                continue
            in_table_body = False
        if THEMATIC_BREAK_RE.match(line):
            continue
        m = LIST_ITEM_RE.match(line)
        if not m:
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if content_col is not None and indent >= content_col:
            continue  # a sub-bullet of the open entry, not a new session
        n += 1
        content_col = m.end() - 1  # the column the item's own content starts at
    return n


def validate_new_session_prompt() -> list[str]:
    """GOVERNANCE §20 enforcement for `new_session.md` (symlinked to the
    project root as `new_session`, which is how a session actually opens it).

    Three checks, in increasing specificity:

    1. SHAPE — the six §20 headings, each exactly ONCE, in order, and no others.
       A missing heading means a session rewrote the file freehand; a reordered
       one means the cold session reads its instructions out of sequence; a
       DUPLICATE is the append-instead-of-overwrite failure mode itself, which
       is why it is rejected rather than tolerated (a second `## Where we got
       to` at EOF was measured invisible to both the cap and the order check).
       Extra sections are rejected too: §20 calls the shape FIXED, so adding one
       must cost a code edit plus a GOVERNANCE amendment — the same deliberate
       friction as raising a cap.
    2. THE DIARY — `## Where we got to` may list at most
       NEW_SESSION_RECENT_MAX_BULLETS sessions. This is the targeted check: the
       file's 439-line bloat was 28 append-only session entries, and a global
       size cap alone lets that creep back by squeezing prose elsewhere.
    3. SIZE — global line + byte caps as the backstop for everything else.

    All parsing runs on a fence-masked, LINE-ANCHORED view. Both matter, and
    both were measured: the original slice used a bare `text.index`, so one
    banner line containing the literal `## Where we got to` — the style that
    banner already uses for other headings — silently moved the counted region
    off the real section and disabled the cap; `##  Two spaces` crashed it with
    an uncaught ValueError out of the pre-commit hook.

    Returns its own error list (empty = clean) rather than mutating ticket
    state, like validate_status_snapshot: the caps are a property of one file,
    not of any ticket.

    Absent is an ERROR here, where STATUS.md's absence is a silent skip: STATUS
    can legitimately not exist yet (fresh-clone bootstrap), but this file is
    committed, so a clone always has it and "missing" means it was deleted. An
    I/O or encoding failure is reported AS one — never dressed up as a §20
    violation, which would send the reader to fix governance over a bad disk."""
    try:
        raw = NEW_SESSION_PROMPT.read_bytes()
    except FileNotFoundError:
        return [
            f"{NEW_SESSION_PROMPT.name} is missing. It is the tracked session "
            f"prompt every session boots from, symlinked to the project root as "
            f"`new_session` (GOVERNANCE §20). Restore it from git."
        ]
    except OSError as exc:
        return [
            f"{NEW_SESSION_PROMPT.name} could not be READ — an I/O failure, not a "
            f"§20 violation: {exc}"
        ]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Never decode with errors="replace" here: a corrupt byte inside a
        # heading became U+FFFD and the file was reported as "missing required
        # section(s): Boot" — telling the reader to add a heading that is
        # already there — while a corrupt byte in body prose passed CLEAN.
        return [
            f"{NEW_SESSION_PROMPT.name} is not valid UTF-8 — an encoding failure, "
            f"not a §20 violation: {exc}"
        ]
    errors: list[str] = []

    # Fenced blocks are examples, not structure; mask them before any parsing.
    lines = _mask_fenced_blocks(text.splitlines())
    headings = [(i, m.group("title")) for i, line in enumerate(lines) if (m := H2_RE.match(line))]
    titles = [t for _, t in headings]

    # 1. Shape: each required heading exactly once, in order, and nothing else.
    counts = Counter(titles)
    missing = [h for h in NEW_SESSION_SECTIONS if counts[h] == 0]
    duplicated = [h for h in NEW_SESSION_SECTIONS if counts[h] > 1]
    extra = list(dict.fromkeys(t for t in titles if t not in NEW_SESSION_SECTIONS))
    if missing:
        errors.append(
            f"new_session is missing required section(s): {', '.join(missing)}. "
            f"The §20 shape is: {' → '.join(NEW_SESSION_SECTIONS)}."
        )
    if duplicated:
        errors.append(
            f"new_session repeats section(s): {', '.join(duplicated)}. A second "
            f"copy of a section IS the append-instead-of-overwrite failure §20 "
            f"exists to stop — OVERWRITE the existing one (GOVERNANCE §20)."
        )
    if extra:
        errors.append(
            f"new_session has non-§20 section(s): {', '.join(extra)}. The shape is "
            f"FIXED: {' → '.join(NEW_SESSION_SECTIONS)}. Fold the content into one "
            f"of those, or amend GOVERNANCE §20 + NEW_SESSION_SECTIONS together."
        )
    if not missing and not duplicated:
        required_order = [t for t in titles if t in NEW_SESSION_SECTIONS]
        if required_order != list(NEW_SESSION_SECTIONS):
            errors.append(
                f"new_session sections are out of order. Required: "
                f"{' → '.join(NEW_SESSION_SECTIONS)} (GOVERNANCE §20)."
            )

    # 2. The diary cap — the specific thing that bloated the file. Bounds come
    #    from the anchored heading scan above, never a substring search.
    for pos, (line_no, title) in enumerate(headings):
        if title != NEW_SESSION_RECENT_HEADING:
            continue
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        n_entries = _session_entries(lines[line_no + 1 : end])
        if n_entries > NEW_SESSION_RECENT_MAX_BULLETS:
            errors.append(
                f"new_session `## {NEW_SESSION_RECENT_HEADING}` lists {n_entries} "
                f"sessions (cap {NEW_SESSION_RECENT_MAX_BULLETS}). OVERWRITE the "
                f"oldest — do not append. This list is what grew to 28 entries "
                f"and took the file to 439 lines; the durable record of a session "
                f"is the shipping ticket's `## Retrospective` (GOVERNANCE §20 / §13)."
            )

    # 3. Size backstop. Line + byte caps are independent — a file can blow one,
    #    both, or neither; a few giant paragraph-lines evade the line cap alone.
    n_lines = _count_lines(text)
    n_bytes = len(raw)
    if n_lines > NEW_SESSION_MAX_LINES:
        errors.append(
            f"new_session is {n_lines} lines (cap {NEW_SESSION_MAX_LINES}). It is "
            f"a snapshot, not a log — OVERWRITE `Where we got to` / `This session` "
            f"/ `State`. Detail belongs in the ticket, not here. Trim it; do not "
            f"raise the cap (GOVERNANCE §20)."
        )
    if n_bytes > NEW_SESSION_MAX_BYTES:
        errors.append(
            f"new_session is {n_bytes} bytes (cap {NEW_SESSION_MAX_BYTES}). Trim "
            f"to the standing rules plus the current snapshot (GOVERNANCE §20)."
        )
    return errors


def validate(tickets: list[Ticket], epic_codes: set[str], synonyms: dict[str, str]) -> int:
    """Populate ticket.errors; return total error count.

    Raises SystemExit if the §15.3 enforcement ledger (PENDING-VERIFICATIONS.md)
    exists but cannot be read — an unreadable gate is a hard stop, not a
    countable per-ticket error. All other problems accrue to ticket.errors and
    are returned as a count."""
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
                           "blocked": "tickets/blocked", "parked": "tickets/parked",
                           "done": "tickets/done"}
        if status in expected_folder and not is_hotfix:
            if expected_folder[status] not in str(t.path):
                t.errors.append(f"status {status!r} does not match folder {t.path.parent.name!r}")
        # next_action required on active tickets (session hygiene — GOVERNANCE §15.1).
        # Skipped for hotfixes: hotfix files are short-lived single-fix records, not session-resumed work.
        if status == "active" and not is_hotfix:
            next_action = fm.get("next_action")
            if not next_action or str(next_action).strip().lower() in {"", "null", "none"}:
                t.errors.append("next_action required when status == active (GOVERNANCE §5 + §15.1)")
        # parked_until required on parked tickets — names the activation trigger so
        # parked tickets don't become invisible technical debt. Symmetric to the
        # next_action invariant for active tickets. Hotfixes never use the parked
        # status, so the skip is unconditional here too.
        if status == "parked" and not is_hotfix:
            parked_until = fm.get("parked_until")
            if not parked_until or str(parked_until).strip().lower() in {"", "null", "none"}:
                t.errors.append("parked_until required when status == parked (GOVERNANCE §5)")
        # An active ticket that touches a CODE repo must declare its branch —
        # otherwise it is permanently invisible to the §15.1 merged-but-active
        # gate, which has nothing to test against. meta-only tickets are exempt
        # (meta is single-trunk `main`; there is no feature branch to name).
        if status == "active" and not is_hotfix:
            code_repos = {r for r in (fm.get("repos") or []) if r in SIBLING_REPOS}
            branch_val = fm.get("branch")
            if code_repos and (not branch_val
                               or str(branch_val).strip().lower() in {"", "null", "none"}):
                t.errors.append(
                    f"branch required when status == 'active' and repos includes "
                    f"{sorted(code_repos)} — without it the GOVERNANCE §15.1 "
                    f"merged-but-active gate can never see this ticket"
                )
        # priority (GOVERNANCE §19) — required on the statuses that WAIT.
        # Hotfixes are skipped for the same reason next_action/parked_until skip
        # them: a hotfix is an out-of-band single-fix record, never queued work.
        priority = fm.get("priority")
        priority_str = str(priority).strip() if priority is not None else ""
        if status in PRIORITY_REQUIRED_STATUSES and not is_hotfix:
            if not priority_str:
                t.errors.append(
                    f"priority required when status == {status!r} "
                    f"(GOVERNANCE §19; spawned tickets are born P3, root tickets default P2)"
                )
        if priority_str and priority_str not in VALID_PRIORITIES:
            t.errors.append(
                f"priority must be one of {list(VALID_PRIORITIES)}, got {priority_str!r} "
                f"(GOVERNANCE §19.2)"
            )
        # §19 says done/ and parked/ carry NO priority — done is finished and
        # parked is gated on a dated external trigger, so neither is waiting on
        # us. Enforce the absence, or the contract is prose the code contradicts
        # and `--priority` starts answering with work nobody is waiting on.
        if status in {"done", "parked"} and priority_str and not is_hotfix:
            t.errors.append(
                f"priority must be absent when status == {status!r}, got {priority_str!r} "
                f"(GOVERNANCE §19 — only work that WAITS carries one)"
            )
        # §19.4 — a P0/P1 must name its trigger as fact. An empty justification
        # is the inflation route this field exists to close.
        if priority_str in PRIORITY_JUSTIFIED and not is_hotfix:
            problem = because_problem(fm.get("priority_because"))
            if problem == "missing":
                t.errors.append(
                    f"priority_because required when priority == {priority_str} "
                    f"(GOVERNANCE §19.4 — name which of the five triggers applies, as fact)"
                )
            elif problem == "marker":
                t.errors.append(
                    f"priority_because is the YAML block-scalar marker "
                    f"{str(fm.get('priority_because')).strip()!r}, not a "
                    f"reason — this frontmatter parser is single-line, so the text below it was "
                    f"DROPPED. Put the justification on one line (GOVERNANCE §19.4)"
                )
        # §9.3 — a SPAWNED backlog P2 must say who is hurt and when, or it is a
        # P3. In the source project a universal P2 default made 164 of 166 open
        # tickets carry the same label — a default everything takes
        # discriminates nothing; this is the split default's mechanical tooth.
        # Scoped to BACKLOG: birth happens at filing, and active tickets were
        # promoted through /ticket-start's queue gate already.
        if (
            status == "backlog"
            and priority_str == "P2"
            and not is_hotfix
            and str(fm.get("discovered_from") or "").strip().lower() not in {"", "null", "none"}
        ):
            # because_problem covers the block-scalar marker too — the same
            # ">-" that §19.4 rejects must not pass here.
            if because_problem(fm.get("priority_because")) is not None:
                t.errors.append(
                    "priority_because required for a spawned backlog P2 "
                    "(discovered_from is set) — one factual line naming who is "
                    "hurt and when, ON ONE LINE (a YAML block-scalar marker is "
                    "dropped by this parser), or the ticket is P3 "
                    "(GOVERNANCE §9.3)"
                )
        # proposed_priority (GOVERNANCE §9.2) — a session's promotion/queue
        # proposal awaiting the owner's word. Silence means NOT YET, never
        # "gone": --health lists every unanswered proposal.
        proposed = fm.get("proposed_priority")
        proposed_str = str(proposed).strip() if proposed is not None else ""
        if proposed_str and proposed_str.lower() not in {"null", "none"}:
            if proposed_str not in VALID_PRIORITIES:
                t.errors.append(
                    f"proposed_priority must be one of {list(VALID_PRIORITIES)} or null, "
                    f"got {proposed_str!r} (GOVERNANCE §9.2)"
                )
            elif status == "done" and not is_hotfix:
                # Nothing is waiting on a done ticket, so no proposal on it can
                # ever be answered — and --health's reader scans non-done only.
                # A field nothing reads is metadata nothing keeps true.
                t.errors.append(
                    "proposed_priority must be absent on a done ticket — nothing is "
                    "waiting, so the proposal could never be answered (GOVERNANCE §9.2)"
                )
        # created/updated must be real ISO dates when present. Everything else
        # in the schema is value-checked; these two were not, so an
        # unsubstituted `YYYY-MM-DD` template placeholder — and the US-format
        # date the _grandfathered docstring cites — sailed through --validate
        # and only surfaced in the monthly --health report (found by review).
        for date_field in ("created", "updated"):
            raw_date = fm.get(date_field)
            date_str = str(raw_date).strip() if raw_date is not None else ""
            if date_str and date_str.lower() not in {"null", "none"}:
                try:
                    _dt.date.fromisoformat(date_str)
                except ValueError:
                    t.errors.append(
                        f"{date_field} must be an ISO date (YYYY-MM-DD), got {date_str!r}"
                    )
        # sensitive flag (GOVERNANCE §17) must be a literal bool when present.
        sensitive = fm.get("sensitive")
        if sensitive is not None and str(sensitive).strip().lower() not in {"true", "false"}:
            t.errors.append(f"sensitive must be true|false, got {sensitive!r}")
        # repos values must be a subset of VALID_REPOS (skipped when the
        # allow-list is unconfigured — see the tunables block).
        repos = fm.get("repos") or []
        if isinstance(repos, list) and VALID_REPOS:
            for r in repos:
                if r not in VALID_REPOS:
                    t.errors.append(f"repos entry {r!r} not in {sorted(VALID_REPOS)}")
    # §19.5 ordering sanity: a blocker inherits its dependents' urgency. A P2
    # "before launch" blocked by a P3 "someday" is a promise the system has
    # already decided never to keep — measured live in the source project:
    # three P2s sat blocked_by one P3 and --validate was green. Raise the
    # blocker or demote the dependent.
    _rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    _by_id = {t.id: t for t in tickets if t.id}
    _waiting = {"backlog", "active", "blocked"}
    for t in tickets:
        if t.status not in _waiting:
            continue
        pt = str(t.frontmatter.get("priority") or "").strip()
        if pt not in _rank:
            continue
        for b in t.frontmatter.get("blocked_by") or []:
            bt = _by_id.get(str(b))
            if bt is None or bt.status not in _waiting:
                continue
            pb = str(bt.frontmatter.get("priority") or "").strip()
            if pb in _rank and _rank[pb] > _rank[pt]:
                t.errors.append(
                    f"priority inversion: {t.id} ({pt}) is blocked_by {bt.id} ({pb}) — "
                    f"a blocker inherits its dependents' urgency; raise {bt.id} or "
                    f"demote {t.id} (GOVERNANCE §19.5)"
                )
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
    # GOVERNANCE §15.3 — done tickets with `[ ]` acceptance criteria must be listed in
    # PENDING-VERIFICATIONS.md (the dedicated uncapped ledger, kept out
    # of STATUS.md). FAIL CLOSED: the ledger is a *tracked* file, so a real
    # checkout always has it. If it is ABSENT (deleted / renamed / dropped by a
    # bad merge) we do NOT skip the check — that would silently switch off a
    # compliance gate. Treat absent as an EMPTY ledger and still run the scan:
    # any done ticket with a `[ ]` AC then fails loudly, and a genuine
    # fresh-bootstrap repo (no such done tickets) still passes cleanly. If the
    # file EXISTS but can't be read, that is a hard error — surface it, never
    # coerce to "" (which would fail every ticket with a misleading "no entry"
    # message and send the operator chasing a phantom).
    ledger_text = ""
    if PENDING_VERIFICATIONS_MD.is_file():
        try:
            ledger_text = PENDING_VERIFICATIONS_MD.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(
                f"ERROR: PENDING-VERIFICATIONS.md exists but could not be read "
                f"({exc}). This is the GOVERNANCE §15.3 enforcement ledger — "
                f"refusing to validate against an unreadable gate. Fix the "
                f"file's readability and re-run."
            )
    validate_done_unchecked_criteria(tickets, parse_pending_verification_ids(ledger_text))
    # GOVERNANCE §17 — sensitive:true tickets must carry a `## Compliance
    # Impact` section. Independent of STATUS.md (reads each ticket directly).
    validate_compliance_section(tickets)
    return sum(len(t.errors) for t in tickets)


def render_index_md(tickets: list[Ticket]) -> str:
    # Render order: active (current focus) → blocked (waiting on tickets) → backlog
    # (ready to pick) → parked (waiting on external trigger) → done. Parked sits
    # after backlog because they're conceptually "later than backlog": you'd pick
    # from backlog first, only unparking when the named trigger fires.
    status_order = ("active", "blocked", "backlog", "parked", "done")
    by_status: dict[str, list[Ticket]] = {s: [] for s in status_order}
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
    lines.append("> Regenerate with `python3 scripts/build_index.py`. CI fails on drift.")
    lines.append("")
    status_titles = {
        "active": "Active",
        "blocked": "Blocked",
        "backlog": "Backlog",
        "parked": "Parked",
        "done": "Done",
    }
    for status in status_order:
        items = sorted(by_status[status], key=lambda t: t.id)
        lines.append(f"## {status_titles[status]} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_No tickets._")
            lines.append("")
            continue
        # Parked tickets surface their activation trigger instead of `blocked_by`
        # (parked tickets cannot have internal blockers — that would be `blocked`).
        if status == "parked":
            lines.append("| ID | Title | Epic | Parent | Parked until | Path |")
            lines.append("|---|---|---|---|---|---|")
            for t in items:
                fm = t.frontmatter
                parent = fm.get("parent") or "—"
                parked_until = fm.get("parked_until") or "—"
                rel = t.path.relative_to(REPO_ROOT)
                lines.append(
                    f"| `{t.id}` | {fm.get('title', '')} | `{fm.get('epic', '')}` | "
                    f"{parent} | `{parked_until}` | [`{rel}`]({rel}) |"
                )
            lines.append("")
            continue
        # Priority (GOVERNANCE §19) is shown only where work WAITS — done/ has
        # none by design, so rendering the column there would print a wall of
        # em-dashes and imply the field went missing.
        show_priority = status != "done"
        if show_priority:
            lines.append("| ID | Pri | Title | Epic | Parent | Blocked by | Path |")
            lines.append("|---|---|---|---|---|---|---|")
        else:
            lines.append("| ID | Title | Epic | Parent | Blocked by | Path |")
            lines.append("|---|---|---|---|---|---|")
        for t in items:
            fm = t.frontmatter
            parent = fm.get("parent") or "—"
            blocked_by = ", ".join(fm.get("blocked_by", []) or []) or "—"
            rel = t.path.relative_to(REPO_ROOT)
            pri = f"`{fm.get('priority')}` | " if show_priority and fm.get("priority") else (
                "— | " if show_priority else ""
            )
            lines.append(
                f"| `{t.id}` | {pri}{fm.get('title', '')} | `{fm.get('epic', '')}` | "
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
# PROD-READINESS auto-tick — derive checkbox state from ticket frontmatter
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
# Auto-unblock dependent tickets when blocker ships
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
# drift is structurally impossible.

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

    Loud-fail on purpose: a non-zero exit from git, OR any path that
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


def health_report(tickets: list[Ticket], today: _dt.date) -> str:
    """GOVERNANCE §9.2 + §19.8 — the monthly gauge, pure so it is testable.

    Closure is APPROXIMATE by design (the `updated` date of done/ tickets — a
    paperwork sweep inflates it) and labelled as such in the output.
    """
    cutoff = today - _dt.timedelta(days=HEALTH_WINDOW_DAYS)
    malformed: set[str] = set()

    def _iso(v: object) -> _dt.date | None:
        try:
            return _dt.date.fromisoformat(str(v).strip())
        except ValueError:
            return None

    def _spawned(t: Ticket) -> bool:
        df = str(t.frontmatter.get("discovered_from") or "").strip().lower()
        return df not in {"", "null", "none"}

    created30: list[Ticket] = []
    for t in tickets:
        d = _iso(t.frontmatter.get("created"))
        if d is None:
            malformed.add(t.id or str(t.path))
        elif d >= cutoff:
            created30.append(t)
    n_spawned = sum(1 for t in created30 if _spawned(t))
    n_root = len(created30) - n_spawned
    closed30 = 0
    for t in tickets:
        if t.status != "done":
            continue
        d = _iso(t.frontmatter.get("updated"))
        if d is None:
            malformed.add(t.id or str(t.path))
        elif d >= cutoff:
            closed30 += 1
    open_ts = [t for t in tickets if t.status in PRIORITY_REQUIRED_STATUSES]
    pri = Counter(str(t.frontmatter.get("priority") or "—") for t in open_ts)
    # Proposals live wherever work WAITS — a proposal on a ticket that later
    # moved to blocked/ or parked/ must still resurface, or silence becomes
    # "gone" (the exact failure the field exists to prevent; a review once
    # found this reader scoped narrower than the validator).
    proposals = [
        t for t in tickets
        if t.status != "done"
        and str(t.frontmatter.get("proposed_priority") or "").strip().lower()
        not in {"", "null", "none"}
    ]
    lines = [
        f"Ticket-system health — trailing {HEALTH_WINDOW_DAYS} days as of {today} "
        f"(GOVERNANCE §19.8 gauge)",
        f"  created: {len(created30)}  (root {n_root} · spawned {n_spawned})",
        f"  closed:  {closed30}  (approx — the `updated` date of done/ tickets)",
        "  open (backlog+active) " + str(len(open_ts)) + " by priority:  "
        + "  ".join(f"{k} {v}" for k, v in sorted(pri.items())),
        f"  parked (date-gated, no priority): "
        f"{sum(1 for t in tickets if t.status == 'parked')}",
    ]
    if malformed:
        # Direction per field: a bad `created` hides intake and reads
        # HEALTHIER; a bad `updated` on a done ticket hides closure and
        # reads LOUDER. The count is TICKETS, not occurrences — one ticket
        # with two bad dates is one broken ticket.
        lines.append(
            f"  MALFORMED DATES: {len(malformed)} ticket(s) EXCLUDED from the window "
            f"counts — fix the frontmatter (a bad `created` hides intake and reads "
            f"HEALTHIER; a bad `updated` on done hides closure and reads LOUDER)"
        )
    if proposals:
        lines.append(f"  UNANSWERED PROPOSALS ({len(proposals)}) — owner word owed "
                     f"(silence = not yet, never gone):")
        for t in sorted(proposals, key=lambda t: t.id):
            lines.append(f"    {t.id} [{t.status}]  proposed "
                         f"{t.frontmatter.get('proposed_priority')} — "
                         f"{t.frontmatter.get('priority_because') or 'no argued fact'}")
    else:
        lines.append("  unanswered proposals: none")
    # Ratio + floor semantics are documented at the tunables block
    # (HEALTH_TRIPWIRE_*).
    if len(created30) >= HEALTH_TRIPWIRE_MIN_CREATED and len(created30) > closed30 \
            and n_spawned >= HEALTH_TRIPWIRE_SPAWNED_RATIO * len(created30):
        lines.append(
            f"  TRIPWIRE (GOVERNANCE §19.8): {n_spawned} of {len(created30)} created "
            f"tickets this window are spawned "
            f"(>={HEALTH_TRIPWIRE_SPAWNED_RATIO:.0%}) AND creation ({len(created30)}) "
            f"outpaced closure ({closed30}) — the machine is feeding itself; "
            f"schedule the owner review."
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build INDEX.md + INDEX.json from tickets/.")
    ap.add_argument("--validate", action="store_true",
                    help="validate only, no file output; exit 1 on any error "
                         "(includes stale blocked_by detection)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate and diff vs committed INDEX files; exit 1 on drift")
    ap.add_argument("--fix", action="store_true",
                    help="auto-clear stale blocked_by entries (refs to done tickets), "
                         "bump updated:, auto-stage via git add, then regenerate INDEX. "
                         "Used by pre-commit.")
    ap.add_argument("--priority", metavar="LEVEL", choices=VALID_PRIORITIES,
                    help="list tickets at this priority and exit (GOVERNANCE §19). "
                         "Deterministic query — 'list all P0 tickets' is a script, "
                         "never a judgement call.")
    ap.add_argument("--health", action="store_true",
                    help="30-day intake gauge: created vs closed, root vs spawned, "
                         "priority histogram, unanswered proposals, and the §19.8 "
                         "self-feeding tripwire. Read-only; the monthly review reads this.")
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
    if args.health and args.priority:
        print("ERROR: --health and --priority are separate read-only queries — run one "
              "at a time (combined, one would silently not run)", file=sys.stderr)
        return 2
    if (args.health or args.priority) and (args.validate or args.check or args.fix):
        # The query flags return BEFORE the validation gate runs. Combining
        # them would exit 0 without validating — executed during review:
        # `--validate --health` returned 0 on a tree where `--validate` alone
        # returned 1. Someone WILL try to add --health to the CI validate line
        # to get the gauge into the log; refuse loudly.
        which = "--health" if args.health else "--priority"
        print(f"ERROR: {which} is a read-only query — run it on its own "
              f"(combined with --validate/--check/--fix the gate would silently not run)",
              file=sys.stderr)
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

    # --priority is a pure query: no validation gate, no file output. It answers
    # "what is P0 right now" from committed frontmatter (GOVERNANCE §19.7).
    if args.priority:
        # Scoped to the statuses that WAIT (§19). A done or parked ticket must
        # not carry a priority at all; if one somehow does, this query is not
        # where that gets surfaced — `--validate` refuses it.
        hits = sorted(
            (t for t in tickets
             if str(t.frontmatter.get("priority") or "") == args.priority
             and t.status in PRIORITY_REQUIRED_STATUSES),
            key=lambda t: t.id,
        )
        for t in hits:
            because = t.frontmatter.get("priority_because") or "—"
            print(f"{t.id}\t{t.status}\t{t.frontmatter.get('title', '')}\n\t\t{because}")
        print(f"\n{len(hits)} ticket(s) at {args.priority}")
        return 0

    if args.health:
        print(health_report(tickets, _dt.date.today()))
        return 0

    errors_total = validate(tickets, epic_codes, synonyms)
    status_errors = validate_status_snapshot()
    prompt_errors = validate_new_session_prompt()
    # GOVERNANCE §15.1 — merged work ships, it does not pause. Reported (never
    # silently skipped) when the sibling repos are absent, e.g. meta-only CI.
    ship_errors, ship_unavailable = validate_shipped_but_active(tickets)
    gate_errors = validate_current_gate()
    # Tunable coherence is graded like the gate marker: a misconfiguration is
    # an ERROR, never a silent narrowing of what the other checks can see.
    config_errors = validate_repos_config()
    queue_errors = validate_queue_cap(tickets)
    if config_errors:
        for err in config_errors:
            print(f"CONFIG: {err}", file=sys.stderr)
    if gate_errors:
        for err in gate_errors:
            print(f"ROADMAP: {err}", file=sys.stderr)
    if queue_errors:
        for err in queue_errors:
            print(f"ROADMAP: {err}", file=sys.stderr)
    if ship_unavailable:
        print(f"NOTE: merged-but-active gate NOT RUN — {ship_unavailable}", file=sys.stderr)
    if ship_errors:
        print(f"Ship gate: {len(ship_errors)} ticket(s) merged but still `active` "
              f"(GOVERNANCE §15.1):", file=sys.stderr)
        for err in ship_errors:
            print(f"    - {err}", file=sys.stderr)
    if status_errors:
        print(f"STATUS.md: {len(status_errors)} snapshot-cap violation(s) "
              f"(GOVERNANCE §18):", file=sys.stderr)
        for err in status_errors:
            print(f"    - {err}", file=sys.stderr)
    if prompt_errors:
        print(f"new_session: {len(prompt_errors)} session-prompt violation(s) "
              f"(GOVERNANCE §20):", file=sys.stderr)
        for err in prompt_errors:
            print(f"    - {err}", file=sys.stderr)
    if errors_total:
        print(f"Validation: {errors_total} error(s) across {sum(1 for t in tickets if t.errors)} ticket(s)", file=sys.stderr)
        for t in tickets:
            if not t.errors:
                continue
            rel = t.path.relative_to(REPO_ROOT)
            print(f"  {rel}:", file=sys.stderr)
            for err in t.errors:
                print(f"    - {err}", file=sys.stderr)
    # queue_errors/gate_errors — and ship_errors, which rides the same
    # asymmetry — deliberately do NOT gate --check's success exit (parity with
    # the pre-existing gate_errors handling): --check answers "is INDEX stale",
    # and all of them still print to stderr + red --validate, which CI runs
    # first. Recorded here so the asymmetry reads as chosen.
    if (errors_total or status_errors or prompt_errors or ship_errors or gate_errors or config_errors or queue_errors) and (args.validate or args.fix):
        # Refuse to --fix while structural validation errors exist; a
        # malformed `done/` ticket could break done_ids construction. The
        # STATUS cap (GOVERNANCE §18) blocks on the same path.
        return 1

    # Detect stale blocked_by entries (references to done tickets).
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
        return 0 if errors_total == 0 and not status_errors and not prompt_errors and not ship_errors and not gate_errors and not config_errors else 1

    # Derive PROD-READINESS checkbox state from ticket frontmatter.
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
        # INDEX files match, but only report success if validation + the
        # STATUS cap + the §20 session-prompt shape are also clean — otherwise
        # the "up-to-date" line would contradict the non-zero exit and bury the
        # real errors printed above.
        if errors_total == 0 and not status_errors and not prompt_errors:
            # Name only the files that actually exist — claiming an absent
            # PROD-READINESS.md is "up-to-date" reads as a check that ran.
            synced = ["INDEX.md", "INDEX.json"]
            if pr_new_text is not None:
                synced.append("PROD-READINESS.md")
            print(f"{' + '.join(synced)} are up-to-date.")
            return 0
        print("INDEX files match, but validation/STATUS-cap/new_session errors "
              "above — see stderr.", file=sys.stderr)
        return 1

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
    if args.fix:
        # The pre-commit hook's contract is "the hook stages what it touched, so
        # the human sees it in their commit". apply_unblock_fix stages the
        # rewritten tickets; the regenerated INDEX files (and an autoticked
        # PROD-READINESS) were written but never staged, so every ticket-state
        # commit failed once with "files were modified by this hook" and had to
        # be retried by hand (measured by review with pre-commit 4.5.1).
        #
        # Stage only what actually CHANGED: _git_add's post-stage cross-check
        # reads `git diff --cached`, where a file regenerated byte-identical to
        # HEAD never appears — passing one in reads as a silent skip and fails
        # the whole run (measured on this repo's own empty INDEX).
        candidates = [md_path, json_path]
        if pr_new_text is not None and pr_changed > 0:
            candidates.append(PROD_READINESS)
        rel = [str(c.relative_to(REPO_ROOT)) for c in candidates]
        try:
            proc = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", *rel],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            print(f"ERROR (--fix): could not read git status for {rel}: {e}", file=sys.stderr)
            return 1
        if proc.returncode != 0:
            print(f"ERROR (--fix): git status failed for {rel}: {proc.stderr.strip()}",
                  file=sys.stderr)
            return 1
        dirty = {line[3:].strip() for line in proc.stdout.splitlines() if line.strip()}
        to_stage = [c for c, r in zip(candidates, rel) if r in dirty]
        if to_stage:
            try:
                _git_add(to_stage)
            except RuntimeError as e:
                print(f"ERROR (--fix): {e}", file=sys.stderr)
                return 1
    # Plain mode (no --fix): warn about stale entries but don't fail.
    if not args.fix and stale:
        print(f"NOTE: {sum(len(refs) for _, refs, _ in stale)} stale blocked_by "
              f"entr{'y' if sum(len(refs) for _, refs, _ in stale) == 1 else 'ies'} "
              f"detected — run with --fix to auto-clear:")
        for t, stale_refs, _ in stale:
            rel = t.path.relative_to(REPO_ROOT)
            refs = ", ".join(stale_refs)
            print(f"  {rel}: blocked_by references done ticket(s): {refs}")
    return 0 if errors_total == 0 and not status_errors and not prompt_errors else 1


if __name__ == "__main__":
    sys.exit(main())
