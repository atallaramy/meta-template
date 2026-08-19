#!/usr/bin/env python3
"""Tests for scripts/build_index.py — the validator that gates every commit.

Zero external dependencies (stdlib `unittest`), mirroring build_index.py's
no-PyYAML ethos. Run from the meta repo root:

    python3 scripts/test_build_index.py

Ticket IDs in fixtures use the fictional epic `EX` on purpose — no real
project's IDs belong in a template. The GOVERNANCE §15.3 enforcement must fail
CLOSED; the §18 snapshot cap must exclude the Pending Verifications ledger from
its measurement WITHOUT that exclusion becoming a cap-evasion route.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path

# `python3 scripts/test_build_index.py` puts scripts/ on sys.path[0], so this
# imports the sibling module under test.
import build_index as bi


# A ledger file in the PENDING-VERIFICATIONS.md shape: a `## Pending
# Verifications` H2 followed by a table whose first column is the ticket ID
# (backtick-wrapped or bare — both must parse).
LEDGER_WITH_ROWS = """\
# Pending Verifications

> banner text (§15.3) — uncapped ledger.

## Pending Verifications

| Ticket   | AC          | Trigger      | Verification | Status  |
| -------- | ----------- | ------------ | ------------ | ------- |
| `EX-10`  | nightly rows | cron fires  | `some-cli`   | pending |
| EX-24  | bare-id row  | staging walk | manual       | pending |
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _make_done_ticket(
    tmp: Path,
    tid: str = "EX-1",
    *,
    updated: str = "2026-07-01",
    unchecked_ac: bool = True,
) -> bi.Ticket:
    """Create a fully-valid done ticket file on disk and return its Ticket.

    Valid on every OTHER axis (filename, id match, folder, required fields) so
    that any error surfaced by validate() can only be the §15.3 one under test.
    """
    ac_line = "- [ ] verify the thing later" if unchecked_ac else "- [x] verified"
    folder = tmp / "tickets" / "done"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{tid}-example.md"
    _write(
        path,
        f"""\
---
id: {tid}
title: Example
epic: EX
status: done
created: 2026-06-01
updated: {updated}
sensitive: false
---

## Acceptance criteria

{ac_line}
""",
    )
    fm = {
        "id": tid,
        "title": "Example",
        "epic": "EX",
        "status": "done",
        "created": "2026-06-01",
        "updated": updated,
        "sensitive": "false",
        "parent": None,
        "discovered_from": None,
        "children": [],
        "blocks": [],
        "blocked_by": [],
        "repos": [],
    }
    return bi.Ticket(path=path, frontmatter=fm)


class _UnreadableLedger:
    """Stand-in for PENDING_VERIFICATIONS_MD that exists but can't be read
    (perms / transient IO) — portable, avoids chmod-and-root-skip flakiness."""

    def is_file(self) -> bool:
        return True

    def read_text(self, encoding: str = "utf-8") -> str:
        raise OSError("simulated read failure")


class DiscoverTickets(unittest.TestCase):
    def test_a_folder_readme_is_not_a_ticket(self):
        # The template ships hotfix/README.md as a folder doc. Without the
        # skip, it is parsed as a frontmatter-less ticket and fails validation
        # on a fresh clone — a template that cannot pass its own gate.
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "hotfix"
            folder.mkdir(parents=True)
            _write(folder / "README.md", "# What lives here\n")
            original = bi.REPO_ROOT
            bi.REPO_ROOT = Path(d)
            try:
                self.assertEqual(bi.discover_tickets(Path(d)), [])
            finally:
                bi.REPO_ROOT = original

    def test_a_readme_with_frontmatter_is_a_ticket_and_fails_loudly(self):
        # The skip is gated on the ABSENCE of frontmatter. An unconditional
        # name-skip silently hid a fully-valid ticket saved as README.md from
        # the INDEX, duplicate-ID detection and every gate (measured) — where
        # the pre-port behavior was a loud filename-convention reject. The
        # loud reject IS the guard; pin it.
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "tickets" / "active"
            folder.mkdir(parents=True)
            _write(folder / "README.md", (
                "---\nid: EX-1\ntitle: T\nepic: EX\nstatus: active\n"
                "priority: P2\ncreated: 2026-06-01\nupdated: 2026-06-01\n"
                "next_action: Do it.\n---\n"
            ))
            original = bi.REPO_ROOT
            bi.REPO_ROOT = Path(d)
            try:
                found = bi.discover_tickets(Path(d))
                self.assertEqual(len(found), 1, "a frontmatter README IS a ticket")
                bi.validate(found, epic_codes={"EX"}, synonyms={})
                self.assertTrue(
                    any("does not match convention" in e for e in found[0].errors),
                    msg=f"expected the loud filename reject, got: {found[0].errors}",
                )
            finally:
                bi.REPO_ROOT = original


class DateFieldValidation(unittest.TestCase):
    """created/updated must be real ISO dates — an unsubstituted `YYYY-MM-DD`
    placeholder and a US-format date both passed --validate and surfaced only
    in the monthly --health report (measured during review)."""

    def test_us_format_updated_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P3")
            t.frontmatter["updated"] = "07/30/2026"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(any("ISO date" in e for e in t.errors), msg=str(t.errors))

    def test_unsubstituted_placeholder_created_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P3")
            t.frontmatter["created"] = "YYYY-MM-DD"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(any("ISO date" in e for e in t.errors), msg=str(t.errors))

    def test_valid_iso_dates_pass(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P3")
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertFalse([e for e in t.errors if "ISO date" in e], msg=str(t.errors))


class ReposConfigCoherence(unittest.TestCase):
    """SIBLING_REPOS / VALID_REPOS coherence — a repos: typo must not silently
    blind the §15.1 ship gate (measured: with the gate armed and no allow-list,
    `repos: [backened]` + `branch: null` produced zero errors and the ticket
    was permanently invisible to the gate)."""

    def setUp(self):
        self._repos = bi.SIBLING_REPOS
        self._valid = bi.VALID_REPOS
        self.addCleanup(setattr, bi, "SIBLING_REPOS", self._repos)
        self.addCleanup(setattr, bi, "VALID_REPOS", self._valid)

    def test_template_default_is_clean(self):
        bi.SIBLING_REPOS, bi.VALID_REPOS = (), set()
        self.assertEqual(bi.validate_repos_config(), [])

    def test_armed_gate_without_allowlist_is_an_error(self):
        bi.SIBLING_REPOS, bi.VALID_REPOS = ("backend",), set()
        errs = bi.validate_repos_config()
        self.assertTrue(errs and "VALID_REPOS is empty" in errs[0], msg=str(errs))

    def test_sibling_outside_allowlist_is_an_error(self):
        bi.SIBLING_REPOS, bi.VALID_REPOS = ("backend",), {"frontend", "meta"}
        errs = bi.validate_repos_config()
        self.assertTrue(errs and "not in VALID_REPOS" in errs[0], msg=str(errs))

    def test_aligned_tunables_are_clean(self):
        bi.SIBLING_REPOS, bi.VALID_REPOS = ("backend",), {"backend", "meta"}
        self.assertEqual(bi.validate_repos_config(), [])


class ParsePendingVerificationIds(unittest.TestCase):
    def test_parses_backtick_and_bare_ids_from_ledger(self):
        ids = bi.parse_pending_verification_ids(LEDGER_WITH_ROWS)
        self.assertEqual(ids, {"EX-10", "EX-24"})

    def test_header_and_separator_only_table_yields_no_ids(self):
        # A table with header + separator but NO data rows must parse to the
        # empty set — proves neither the header cell ("Ticket") nor the dashes
        # row is mistaken for a ticket ID.
        text = (
            "## Pending Verifications\n\n"
            "| Ticket | AC | Trigger | Verification | Status |\n"
            "| ------ | -- | ------- | ------------ | ------ |\n"
        )
        self.assertEqual(bi.parse_pending_verification_ids(text), set())

    def test_empty_when_no_section(self):
        self.assertEqual(bi.parse_pending_verification_ids("# no ledger here\n"), set())

    def test_unions_rows_across_multiple_pv_sections(self):
        # A ledger that grew a second `## Pending Verifications` heading must
        # still surface rows under BOTH (else those tickets false-block).
        text = (
            "## Pending Verifications\n\n| `EX-10` | a | b | c | pending |\n\n"
            "## Pending Verifications\n\n| `EX-3` | a | b | c | pending |\n"
        )
        self.assertEqual(bi.parse_pending_verification_ids(text), {"EX-10", "EX-3"})


class Section153Enforcement(unittest.TestCase):
    """GOVERNANCE §15.3 — a done ticket with a `[ ]` AC must be listed in the
    ledger, else the commit is refused."""

    def test_fails_when_unchecked_ac_absent_from_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            bi.validate_done_unchecked_criteria([t], pending_verification_ids={"EX-10"})
            self.assertTrue(
                any("PENDING-VERIFICATIONS.md" in e for e in t.errors),
                msg=f"expected a §15.3 error naming the ledger, got: {t.errors}",
            )

    def test_passes_when_unchecked_ac_present_in_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            bi.validate_done_unchecked_criteria([t], pending_verification_ids={"EX-1"})
            self.assertEqual(t.errors, [])

    def test_all_criteria_checked_needs_no_ledger_row(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1", unchecked_ac=False)
            bi.validate_done_unchecked_criteria([t], pending_verification_ids=set())
            self.assertEqual(t.errors, [])

    def test_default_effective_date_is_none_so_everything_enforces(self):
        # A fresh template project has no legacy corpus to grandfather.
        self.assertIsNone(bi.SECTION_15_3_EFFECTIVE_DATE)

    def test_pre_effective_date_ticket_is_grandfathered_when_date_is_set(self):
        # A project adopting the template into an existing corpus sets the
        # constant; tickets updated strictly BEFORE it are grandfathered.
        original = bi.SECTION_15_3_EFFECTIVE_DATE
        bi.SECTION_15_3_EFFECTIVE_DATE = "2026-05-26"
        self.addCleanup(setattr, bi, "SECTION_15_3_EFFECTIVE_DATE", original)
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1", updated="2026-05-01")
            bi.validate_done_unchecked_criteria([t], pending_verification_ids=set())
            self.assertEqual(t.errors, [])

    def test_effective_date_boundary_enforces(self):
        # The grandfather comparison is strict `<`, so a ticket updated exactly
        # ON the effective date IS enforced (not grandfathered).
        original = bi.SECTION_15_3_EFFECTIVE_DATE
        bi.SECTION_15_3_EFFECTIVE_DATE = "2026-05-26"
        self.addCleanup(setattr, bi, "SECTION_15_3_EFFECTIVE_DATE", original)
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1", updated="2026-05-26")
            bi.validate_done_unchecked_criteria([t], pending_verification_ids=set())
            self.assertTrue(t.errors, "boundary date must enforce, not grandfather")

    def test_a_malformed_updated_date_fails_closed_not_grandfathered(self):
        # Lexicographic comparison silently grandfathered `07/30/2026` (US
        # format) because '0' < '2' — a compliance gate failing OPEN on a
        # malformed date (measured). Parsed comparison, malformed → enforce.
        original = bi.SECTION_15_3_EFFECTIVE_DATE
        bi.SECTION_15_3_EFFECTIVE_DATE = "2026-05-26"
        self.addCleanup(setattr, bi, "SECTION_15_3_EFFECTIVE_DATE", original)
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1", updated="07/30/2026")
            bi.validate_done_unchecked_criteria([t], pending_verification_ids=set())
            self.assertTrue(t.errors, "a malformed date must ENFORCE, never grandfather")


class Section153FileRouting(unittest.TestCase):
    """Integration: validate() must consult PENDING-VERIFICATIONS.md (not
    STATUS.md), and must FAIL CLOSED when that ledger is absent or unreadable."""

    def setUp(self):
        self._orig_status = bi.STATUS_MD
        self._orig_ledger = bi.PENDING_VERIFICATIONS_MD

    def tearDown(self):
        bi.STATUS_MD = self._orig_status
        bi.PENDING_VERIFICATIONS_MD = self._orig_ledger

    def test_ledger_missing_row_still_fails_even_if_status_has_it(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            # STATUS lists EX-1; if validate() still consulted STATUS this would
            # (wrongly) suppress the error. It must not.
            bi.STATUS_MD = _write(
                Path(d) / "STATUS.md",
                "## Pending Verifications\n\n| `EX-1` | x | y | z | pending |\n",
            )
            bi.PENDING_VERIFICATIONS_MD = _write(
                Path(d) / "PENDING-VERIFICATIONS.md", "## Pending Verifications\n\n(no rows)\n"
            )
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(
                any("PENDING-VERIFICATIONS.md" in e for e in t.errors),
                msg=f"a STATUS row must not satisfy §15.3; errors: {t.errors}",
            )

    def test_ledger_with_row_passes(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            bi.PENDING_VERIFICATIONS_MD = _write(
                Path(d) / "PENDING-VERIFICATIONS.md",
                "## Pending Verifications\n\n| `EX-1` | x | y | z | pending |\n",
            )
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertEqual(t.errors, [])

    def test_absent_ledger_fails_closed(self):
        # Ledger deleted/renamed → treat as empty, still enforce → done ticket
        # with a `[ ]` AC fails LOUD (never silently switches enforcement off).
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            bi.PENDING_VERIFICATIONS_MD = Path(d) / "does-not-exist.md"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(
                any("PENDING-VERIFICATIONS.md" in e for e in t.errors),
                msg=f"absent ledger must fail closed, got: {t.errors}",
            )

    def test_unreadable_ledger_raises_loud(self):
        # Ledger exists but can't be read → hard error, NOT silently coerced to
        # an empty ledger (which would fail every ticket with a phantom cause).
        with tempfile.TemporaryDirectory() as d:
            t = _make_done_ticket(Path(d), tid="EX-1")
            bi.PENDING_VERIFICATIONS_MD = _UnreadableLedger()
            with self.assertRaises(SystemExit):
                bi.validate([t], epic_codes={"EX"}, synonyms={})


class StatusSnapshotCap(unittest.TestCase):
    """GOVERNANCE §18 — the snapshot cap excludes `## Pending Verifications`
    from the measurement, but bounds that excluded region so the exclusion
    can't be abused to smuggle content past the cap."""

    def setUp(self):
        self._orig_status = bi.STATUS_MD

    def tearDown(self):
        bi.STATUS_MD = self._orig_status

    def _set_status(self, tmp: Path, text: str) -> None:
        bi.STATUS_MD = _write(tmp / "STATUS.md", text)

    def test_split_extracts_and_removes_section(self):
        text = (
            "## Current State\n\nsnapshot\n\n"
            "## Pending Verifications\n\n| a | b |\n| c | d |\n\n"
            "## Known Issues\n\nkept\n"
        )
        without, section = bi._split_pending_verifications(text)
        self.assertNotIn("Pending Verifications", without)
        self.assertIn("## Current State", without)
        self.assertIn("## Known Issues", without)
        self.assertIsNotNone(section)
        self.assertIn("Pending Verifications", section)

    def test_small_pointer_stub_excluded_from_main_cap(self):
        # Real snapshot AT the line cap + a small pointer stub. The whole file
        # exceeds the cap; excluding the stub brings it back under → passes.
        # Proves the exclusion works (regression guard against re-counting it).
        with tempfile.TemporaryDirectory() as d:
            main = "\n".join(f"x{i}" for i in range(bi.STATUS_MAX_LINES))  # exactly cap lines
            stub = "\n## Pending Verifications\n\n> pointer to PENDING-VERIFICATIONS.md\n"
            self._set_status(Path(d), main + stub)
            self.assertEqual(bi.validate_status_snapshot(), [])

    def test_ledger_pasted_back_is_flagged_by_stub_guard(self):
        # The anti-evasion case: a big `## Pending Verifications` section
        # in STATUS (ledger pasted back / history parked under the heading,
        # even as the LAST section) must be FLAGGED, not silently excluded.
        with tempfile.TemporaryDirectory() as d:
            rows = "\n".join(f"| EX-{i} | x | y | z | pending |" for i in range(500))
            text = (
                "# Status\n\n## Current State\n\ntiny snapshot\n\n"
                "## Pending Verifications\n\n" + rows + "\n"
            )
            self._set_status(Path(d), text)
            errors = bi.validate_status_snapshot()
            self.assertTrue(errors, "pasted-back ledger must be flagged")
            self.assertTrue(
                any("one-line pointer" in e for e in errors),
                msg=f"expected the stub-guard message, got: {errors}",
            )

    def test_oversized_snapshot_still_caught(self):
        # Genuine snapshot bloat (no PV section) must still fail — the anti-diary
        # failure mode the cap exists to catch.
        with tempfile.TemporaryDirectory() as d:
            bloat = "\n".join(f"line {i}" for i in range(bi.STATUS_MAX_LINES + 50))
            self._set_status(Path(d), "## Current State\n\n" + bloat + "\n")
            errors = bi.validate_status_snapshot()
            self.assertTrue(errors, "oversized snapshot should be rejected")
            self.assertTrue(any("lines" in e for e in errors))

    def test_byte_cap_only(self):
        # Few lines, but over the byte cap (giant single-line paragraphs) — the
        # n_bytes branch must fire independently of the line branch.
        with tempfile.TemporaryDirectory() as d:
            big_line = "z" * (bi.STATUS_MAX_BYTES + 100)
            self._set_status(Path(d), "## Current State\n\n" + big_line + "\n")
            errors = bi.validate_status_snapshot()
            self.assertTrue(any("bytes" in e for e in errors), msg=str(errors))

    def test_multibyte_utf8_roundtrips_byte_identical(self):
        # validate_status_snapshot decodes bytes → strips → re-encodes for the
        # byte count; that must not mis-measure valid multibyte UTF-8.
        raw = "① — § café 中文\n## Current State\nx\n".encode("utf-8")
        self.assertEqual(raw.decode("utf-8", errors="replace").encode("utf-8"), raw)
        with tempfile.TemporaryDirectory() as d:
            # A small multibyte snapshot is well under both caps → clean.
            _write(Path(d) / "STATUS.md", raw.decode("utf-8"))
            bi.STATUS_MD = Path(d) / "STATUS.md"
            self.assertEqual(bi.validate_status_snapshot(), [])

    def test_absent_status_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            bi.STATUS_MD = Path(d) / "does-not-exist.md"
            self.assertEqual(bi.validate_status_snapshot(), [])


def _prompt(
    recent_bullets: int = 3,
    extra: str = "",
    marker: str = "-",
    diary_body: str = "",
) -> str:
    """A minimal §20-shaped session prompt. Built from NEW_SESSION_SECTIONS so a
    rename of a required heading breaks the helper, not just the assertions.

    `marker` writes the session entries with any list marker; `diary_body` puts
    arbitrary content under `## Where we got to` instead. Both exist because the
    cap must count SESSIONS, not one bullet syntax — see
    test_every_entry_form_counts_toward_the_diary_cap."""
    parts = ["# SESSION PROMPT\n"]
    for heading in bi.NEW_SESSION_SECTIONS:
        parts.append(f"## {heading}\n")
        if heading == bi.NEW_SESSION_RECENT_HEADING:
            if diary_body:
                parts.append(diary_body)
            for i in range(recent_bullets):
                parts.append(f"{marker} **s{i}** — a session.\n")
        else:
            parts.append("body\n")
    return "\n".join(parts) + extra


class NewSessionPromptCap(unittest.TestCase):
    """GOVERNANCE §20 — the session prompt is a fixed-shape snapshot. The
    targeted check is the bullet cap on `## Where we got to`: that list is what
    grew to 28 entries and took the file to 439 lines, and it is NOT covered by
    the size caps (a 4th bullet adds 2 lines and passes both)."""

    def setUp(self):
        self._orig = bi.NEW_SESSION_PROMPT

    def tearDown(self):
        bi.NEW_SESSION_PROMPT = self._orig

    def _set(self, tmp: Path, text: str) -> None:
        bi.NEW_SESSION_PROMPT = _write(tmp / "new_session.md", text)

    def test_wellformed_prompt_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            self._set(Path(d), _prompt())
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_at_the_bullet_cap_is_clean(self):
        # Boundary: exactly the cap passes; cap+1 fails (next test). Guards the
        # off-by-one that would make the check either useless or unusable.
        with tempfile.TemporaryDirectory() as d:
            self._set(Path(d), _prompt(recent_bullets=bi.NEW_SESSION_RECENT_MAX_BULLETS))
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_one_extra_session_bullet_is_caught_by_the_bullet_cap_alone(self):
        # THE regression guard. An appended session bullet adds ~1 line, so both
        # size caps pass; only the bullet count can see it. Asserted explicitly:
        # if a future edit deletes the bullet check, the size caps do NOT cover.
        with tempfile.TemporaryDirectory() as d:
            text = _prompt(recent_bullets=bi.NEW_SESSION_RECENT_MAX_BULLETS + 1)
            self.assertLessEqual(bi._count_lines(text), bi.NEW_SESSION_MAX_LINES)
            self.assertLessEqual(len(text.encode("utf-8")), bi.NEW_SESSION_MAX_BYTES)
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(errors, "a 4th session bullet must be rejected")
            self.assertTrue(
                any("lists 4 sessions" in e for e in errors),
                msg=f"expected the diary-cap message, got: {errors}",
            )

    def test_every_entry_form_counts_toward_the_diary_cap(self):
        # The cap must count SESSIONS, not one bullet syntax. Each form below
        # was MEASURED passing a 28-session diary against a cap of 3, under
        # every size cap, on an earlier version of this check. A numbered list
        # and a table are the likeliest reformats of a dated list, so they are
        # the likeliest silent evasions — not exotic ones.
        cap = bi.NEW_SESSION_RECENT_MAX_BULLETS
        forms = {
            "dash": "".join(f"- **s{i}** — x\n" for i in range(cap + 1)),
            "star": "".join(f"* **s{i}** — x\n" for i in range(cap + 1)),
            "plus": "".join(f"+ **s{i}** — x\n" for i in range(cap + 1)),
            "dash+TAB": "".join(f"-\t**s{i}** — x\n" for i in range(cap + 1)),
            "one leading space": "".join(f" - **s{i}** — x\n" for i in range(cap + 1)),
            "numbered 1.": "".join(f"{i}. **s{i}** — x\n" for i in range(cap + 1)),
            "ordered 1)": "".join(f"{i}) **s{i}** — x\n" for i in range(cap + 1)),
            "table": "| session | what |\n|---|---|\n"
            + "".join(f"| s{i} | x |\n" for i in range(cap + 1)),
        }
        for name, body in forms.items():
            with self.subTest(form=name), tempfile.TemporaryDirectory() as d:
                text = _prompt(recent_bullets=0, diary_body=body)
                # Prove the size caps do NOT cover this form, so the assertion
                # below can only be satisfied by the entry count itself.
                self.assertLessEqual(bi._count_lines(text), bi.NEW_SESSION_MAX_LINES)
                self.assertLessEqual(len(text.encode("utf-8")), bi.NEW_SESSION_MAX_BYTES)
                self._set(Path(d), text)
                errors = bi.validate_new_session_prompt()
                self.assertTrue(
                    any(f"lists {cap + 1} sessions" in e for e in errors),
                    msg=f"a {cap + 1}th session as `{name}` must be rejected, got: {errors}",
                )

    def test_a_horizontal_rule_is_not_a_session(self):
        # False-positive guard: `- - -` matches a naive bullet regex. The rules
        # here must OUTNUMBER the cap on their own — with only one or two, the
        # count stays under the cap even when they are miscounted, and the
        # mutant that deletes THEMATIC_BREAK_RE survives (measured).
        with tempfile.TemporaryDirectory() as d:
            body = "- **s1** — x\n\n" + "\n\n".join(["- - -"] * (bi.NEW_SESSION_RECENT_MAX_BULLETS + 1)) + "\n"
            self._set(Path(d), _prompt(recent_bullets=0, diary_body=body))
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_masking_a_fence_preserves_the_line_count(self):
        # The mask must be index-preserving — the diary slice is computed from
        # line numbers, so a mask that adds or drops a line silently shifts the
        # counted region. Asserted directly because no end-to-end fixture sees it.
        src = ["a", "```", "hidden", "```", "b"]
        masked = bi._mask_fenced_blocks(src)
        self.assertEqual(len(masked), len(src))
        self.assertEqual(masked, ["a", "", "", "", "b"])

    def test_entries_in_the_NEXT_section_are_not_counted(self):
        # Boundary of the slice: it must end at the next heading. Extending it
        # by one heading would count `## This session`'s bullets as sessions.
        with tempfile.TemporaryDirectory() as d:
            text = _prompt(recent_bullets=bi.NEW_SESSION_RECENT_MAX_BULLETS)
            after = "".join(f"- item {i}\n" for i in range(6))
            text = text.replace("## This session\n\nbody\n", f"## This session\n\n{after}")
            self._set(Path(d), text)
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_an_entry_on_the_line_immediately_after_the_heading_counts(self):
        # The slice starts at heading+1. Starting at heading+2 skips the first
        # entry whenever no blank line follows the heading — and every fixture
        # in this class has one, so nothing else would see it.
        with tempfile.TemporaryDirectory() as d:
            body = "".join(f"- **s{i}** — x\n" for i in range(bi.NEW_SESSION_RECENT_MAX_BULLETS + 1))
            text = _prompt(recent_bullets=0).replace(
                f"## {bi.NEW_SESSION_RECENT_HEADING}\n\n", f"## {bi.NEW_SESSION_RECENT_HEADING}\n{body}"
            )
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("lists 4 sessions" in e for e in errors), msg=str(errors))

    def test_a_one_space_sub_bullet_is_still_nested_not_a_new_session(self):
        # Nesting is resolved against the open item's CONTENT column, not a
        # fixed indent. `- x` opens content at column 2, so a ` - y` at column 1
        # is a sibling, while `  - y` at column 2 is its child. The tight case.
        with tempfile.TemporaryDirectory() as d:
            body = "- **s1** — a\n  - child\n   - grandchild\n- **s2** — b\n- **s3** — c\n"
            self._set(Path(d), _prompt(recent_bullets=0, diary_body=body))
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_size_caps_fire_at_cap_plus_one_not_at_the_cap(self):
        # Boundary. Without this, `>` → `>=` survives on both caps: a file
        # sitting exactly ON the cap would be rejected and nobody would notice
        # until the day a legitimate prompt hit it exactly.
        for label, pad in (("lines", "x\n"), ("bytes", "x")):
            with self.subTest(cap=label), tempfile.TemporaryDirectory() as d:
                base = _prompt()
                limit = bi.NEW_SESSION_MAX_LINES if label == "lines" else bi.NEW_SESSION_MAX_BYTES
                size = bi._count_lines(base) if label == "lines" else len(base.encode("utf-8"))
                at_cap = base + pad * (limit - size)
                self._set(Path(d), at_cap)
                self.assertEqual(bi.validate_new_session_prompt(), [], f"exactly at the {label} cap must pass")
                self._set(Path(d), at_cap + pad)
                self.assertTrue(
                    any(label in e for e in bi.validate_new_session_prompt()),
                    f"one over the {label} cap must fail",
                )

    def test_indented_continuation_lines_do_not_count_as_bullets(self):
        # A wrapped bullet is indented; the cap is on HOW MANY sessions are
        # listed, not how much is said about each. Without this, a 3-entry list
        # with wrapped text would false-positive.
        with tempfile.TemporaryDirectory() as d:
            wrapped = _prompt(recent_bullets=0).replace(
                f"## {bi.NEW_SESSION_RECENT_HEADING}\n",
                f"## {bi.NEW_SESSION_RECENT_HEADING}\n\n"
                "- **s1** — first line\n  continued\n  - nested\n"
                "- **s2** — x\n- **s3** — y\n",
            )
            self._set(Path(d), wrapped)
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_missing_section_is_caught(self):
        # Assert on the `missing required section(s): …` SEGMENT, not on the
        # whole message: the message also prints the full §20 shape, so
        # `dropped in e` was satisfied by that list no matter which heading the
        # validator actually reported. Hardcoding `missing = [SECTIONS[0]]`
        # passed every test in this class before this was narrowed.
        with tempfile.TemporaryDirectory() as d:
            dropped = bi.NEW_SESSION_SECTIONS[2]
            self._set(Path(d), _prompt().replace(f"## {dropped}\n", f"**{dropped}**\n"))
            errors = bi.validate_new_session_prompt()
            reported = [e.split("missing required section(s): ")[1].split(".")[0]
                        for e in errors if "missing required section(s): " in e]
            self.assertEqual(reported, [dropped], msg=str(errors))
            # ONE error, not two: the order check must not also fire on a list
            # it already knows is incomplete (`and` → `or` in that guard adds a
            # spurious "out of order" and survives an `any()` assertion).
            self.assertEqual(len(errors), 1, msg=str(errors))

    def test_heading_named_only_in_prose_does_not_satisfy_the_shape(self):
        # The fixture must contain a literal `## <Heading>` that is NOT at line
        # start, or the test cannot fail for its stated reason: the previous
        # fixture wrote `> overwrite \`State\` every session`, which has no `## `
        # substring at all, so a naive `f"## {h}" in text` implementation passed
        # it too (mutant run: that swap left this test green).
        with tempfile.TemporaryDirectory() as d:
            dropped = bi.NEW_SESSION_SECTIONS[-1]
            text = _prompt().replace(f"## {dropped}\n", "")
            text = f"> see the ## {dropped} section below for SHAs\n\n" + text
            self.assertIn(f"## {dropped}", text)  # the substring IS present
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(
                any(f"missing required section(s): {dropped}" in e for e in errors),
                msg=str(errors),
            )

    def test_a_fenced_code_block_does_not_satisfy_the_shape(self):
        # Measured on the first parser: a file whose ONLY content was a fence
        # listing the six headings passed the entire shape check with zero real
        # sections. A fence is an example, not structure.
        with tempfile.TemporaryDirectory() as d:
            fenced = "# P\n\n```\n" + "\n".join(f"## {h}" for h in bi.NEW_SESSION_SECTIONS) + "\n```\n"
            self._set(Path(d), fenced)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(
                any("missing required section(s)" in e for e in errors), msg=str(errors)
            )

    def test_a_fence_does_not_truncate_the_counted_diary_section(self):
        # The mirror of the above: a fenced `## example` inside the diary ended
        # the counted region early, so 15 entries passed a cap of 3.
        with tempfile.TemporaryDirectory() as d:
            hidden = "```\n## example\n```\n" + "".join(
                f"- **s{i}** — x\n" for i in range(bi.NEW_SESSION_RECENT_MAX_BULLETS + 1)
            )
            self._set(Path(d), _prompt(recent_bullets=0, diary_body=hidden))
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("lists 4 sessions" in e for e in errors), msg=str(errors))

    def test_a_fence_quoting_headings_out_of_order_is_not_a_false_positive(self):
        # The false-positive half of fence-blindness: quoting the shape inside a
        # fence raised "sections are out of order" on a VALID file. With
        # `always_run: true` that would block every commit in this repo.
        with tempfile.TemporaryDirectory() as d:
            quoted = "```\n## State\n## Boot\n```\n\n"
            self._set(Path(d), quoted + _prompt())
            self.assertEqual(bi.validate_new_session_prompt(), [])

    def test_prose_naming_the_diary_heading_does_not_move_the_counted_section(self):
        # THE silent killer. The section slice was a bare `text.index("## Where
        # we got to")`, so one banner line containing that literal moved the
        # measured region onto the banner and the cap read zero entries forever.
        # The prompt's own banner already writes other headings in that style.
        with tempfile.TemporaryDirectory() as d:
            text = f"> OVERWRITE `## {bi.NEW_SESSION_RECENT_HEADING}` every session\n\n" + _prompt(
                recent_bullets=bi.NEW_SESSION_RECENT_MAX_BULLETS + 1
            )
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("lists 4 sessions" in e for e in errors), msg=str(errors))

    def test_a_duplicate_diary_section_is_rejected(self):
        # Appending a second `## Where we got to` at EOF is literally the
        # append-instead-of-overwrite failure §20 exists to stop, and it was
        # invisible to both the cap and the order check (both took the FIRST
        # occurrence). 3 + 5 entries, 125 lines, zero errors.
        with tempfile.TemporaryDirectory() as d:
            extra = "".join(f"- **n{i}** — x\n" for i in range(5))
            text = _prompt() + f"\n## {bi.NEW_SESSION_RECENT_HEADING}\n\n{extra}"
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("repeats section(s)" in e for e in errors), msg=str(errors))

    def test_a_non_section_20_heading_is_rejected(self):
        # §20 calls the shape FIXED. A new section must cost a code edit plus a
        # GOVERNANCE amendment — the same friction as raising a cap — otherwise
        # "fixed shape" is enforced only for the headings someone remembered.
        with tempfile.TemporaryDirectory() as d:
            self._set(Path(d), _prompt() + "\n## Open threads\n\nunbounded\n")
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("non-§20 section(s): Open threads" in e for e in errors), msg=str(errors))

    def test_two_spaces_after_the_hashes_does_not_crash(self):
        # `##  Where we got to` was tolerated by the shape check (`line[3:]`)
        # and fatal to the slice (exact-literal `str.index`) — an uncaught
        # ValueError traceback out of the pre-commit hook, naming no file.
        with tempfile.TemporaryDirectory() as d:
            text = _prompt(recent_bullets=bi.NEW_SESSION_RECENT_MAX_BULLETS + 1).replace(
                f"## {bi.NEW_SESSION_RECENT_HEADING}\n", f"##  {bi.NEW_SESSION_RECENT_HEADING}\n"
            )
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()  # must not raise
            self.assertTrue(any("lists 4 sessions" in e for e in errors), msg=str(errors))

    def test_the_six_section_names_are_pinned_independently(self):
        # Every other test in this class builds its fixture FROM
        # NEW_SESSION_SECTIONS, so all of them pass if a heading is deleted from
        # the constant (measured: dropping one to five left 12/12 green). The
        # §20 contract is a literal, so pin it as one.
        self.assertEqual(
            bi.NEW_SESSION_SECTIONS,
            ("Boot", "First message", "Which ticket", "Where we got to", "This session", "State"),
        )
        self.assertEqual(bi.NEW_SESSION_RECENT_HEADING, "Where we got to")
        # The caps are POLICY (GOVERNANCE §20), so pin the literals: every
        # other assertion derives its fixture from these constants and so
        # cannot see the value itself drift. Changing one must break a test
        # AND cost a §20 amendment — that is the whole design.
        self.assertEqual(bi.NEW_SESSION_RECENT_MAX_BULLETS, 3)
        self.assertEqual(bi.NEW_SESSION_MAX_LINES, 140)
        self.assertEqual(bi.NEW_SESSION_MAX_BYTES, 12 * 1024)

    def test_a_marker_shallower_than_the_content_column_is_a_new_session(self):
        # The other side of nesting: `- x` opens content at column 2, so a
        # marker at column 1 is a SIBLING, not a child. Without this the
        # content-column arithmetic can be off by one and every fixture above
        # still passes — nested and sibling only diverge at exactly this depth.
        with tempfile.TemporaryDirectory() as d:
            body = "- **s1** — a\n - **s2** — b\n - **s3** — c\n - **s4** — d\n"
            self._set(Path(d), _prompt(recent_bullets=0, diary_body=body))
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("lists 4 sessions" in e for e in errors), msg=str(errors))

    def test_out_of_order_sections_are_caught(self):
        # Present but reordered: a cold session would read its instructions in
        # the wrong sequence, which presence alone cannot see.
        with tempfile.TemporaryDirectory() as d:
            first, last = bi.NEW_SESSION_SECTIONS[0], bi.NEW_SESSION_SECTIONS[-1]
            text = _prompt().replace(f"## {first}\n", "## __TMP__\n")
            text = text.replace(f"## {last}\n", f"## {first}\n")
            text = text.replace("## __TMP__\n", f"## {last}\n")
            self._set(Path(d), text)
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("out of order" in e for e in errors), msg=str(errors))

    def test_line_cap_catches_prose_bloat(self):
        with tempfile.TemporaryDirectory() as d:
            filler = "\n".join(f"line {i}" for i in range(bi.NEW_SESSION_MAX_LINES + 20))
            self._set(Path(d), _prompt(extra="\n" + filler + "\n"))
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("lines" in e for e in errors), msg=str(errors))

    def test_byte_cap_fires_independently_of_the_line_cap(self):
        # Few lines, over the byte cap — history smuggled into giant paragraphs.
        with tempfile.TemporaryDirectory() as d:
            self._set(Path(d), _prompt(extra="\n" + "z" * (bi.NEW_SESSION_MAX_BYTES + 100) + "\n"))
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("bytes" in e for e in errors), msg=str(errors))

    def test_absent_prompt_is_an_ERROR_not_a_skip(self):
        # Unlike STATUS.md (fresh-clone bootstrap allowance): this file is
        # committed, so absent means deleted — the one difference between the
        # two validators, and the one a copy-paste of §18 would get wrong.
        with tempfile.TemporaryDirectory() as d:
            bi.NEW_SESSION_PROMPT = Path(d) / "does-not-exist.md"
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("missing" in e for e in errors), msg=str(errors))

    def test_invalid_utf8_is_reported_as_an_encoding_failure_not_a_shape_error(self):
        # `decode(errors="replace")` turned a corrupt byte inside `## Boot` into
        # "missing required section(s): Boot" — telling the reader to add a
        # heading that is already there — and a corrupt byte in body prose
        # passed CLEAN while the file a cold session reads held U+FFFD.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "new_session.md"
            p.write_bytes(_prompt().encode("utf-8").replace(b"## Boot", b"## Bo\xffot"))
            bi.NEW_SESSION_PROMPT = p
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("not valid UTF-8" in e for e in errors), msg=str(errors))
            self.assertFalse(
                any("missing required section" in e for e in errors),
                msg=f"an encoding failure must not be dressed as a §20 violation: {errors}",
            )

    def test_an_unreadable_prompt_is_not_reported_as_a_governance_violation(self):
        # A directory at the path stands in for any OSError that is not
        # "absent": `is_file()` swallowed these (pathlib returns False), so a
        # permission-denied read printed "is missing … Restore it from git" —
        # the wrong remediation for the wrong diagnosis.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "new_session.md"
            p.mkdir()
            bi.NEW_SESSION_PROMPT = p
            errors = bi.validate_new_session_prompt()
            self.assertTrue(any("could not be READ" in e for e in errors), msg=str(errors))
            self.assertFalse(any("Restore it from git" in e for e in errors), msg=str(errors))

    def test_the_committed_prompt_passes_its_own_gate(self):
        # Not a tautology with the tests above: those use a synthetic fixture.
        # This asserts the REAL file in the repo is §20-clean, so a hand edit
        # that breaks the shape fails CI even if nobody runs --validate locally.
        self.assertEqual(bi.validate_new_session_prompt(), [])


def _make_queued_ticket(
    tmp: Path,
    tid: str = "EX-1",
    *,
    status: str = "backlog",
    priority: object = "P2",
    priority_because: object = None,
) -> bi.Ticket:
    """A ticket valid on every axis EXCEPT the §19 one under test.

    Written to disk with the matching filename + folder so the only error
    validate() can surface is the priority rule being exercised.
    """
    folder = tmp / "tickets" / status
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{tid}-example.md"
    _write(path, "---\nid: %s\n---\n\n## Acceptance criteria\n\n- [x] done\n" % tid)
    fm: dict[str, object] = {
        "id": tid, "title": "Example", "epic": "EX", "status": status,
        "created": "2026-06-01", "updated": "2026-08-12", "sensitive": "false",
        "parent": None, "discovered_from": None, "children": [], "blocks": [],
        "blocked_by": [], "repos": [], "next_action": "Do the next thing.",
        "parked_until": None,
        "priority": priority, "priority_because": priority_because,
    }
    return bi.Ticket(path=path, frontmatter=fm)


def _priority_errors(t: bi.Ticket, *extra: bi.Ticket) -> list[str]:
    """Run the real validate() and return only its priority-related errors.

    Pass companion tickets so a fixture's `discovered_from`/`blocked_by`
    references resolve — otherwise every assertion here is green on top of an
    unrelated cross-ref error the substring filter hides."""
    bi.validate([t, *extra], epic_codes={"EX"}, synonyms={})
    return [e for e in t.errors if "priority" in e]


class Section19Priority(unittest.TestCase):
    """GOVERNANCE §19 — priority is required where work WAITS, and a P0/P1 must
    name its trigger as fact.

    These exist because `priority` is only load-bearing if something refuses a
    ticket without one; an unenforced field is metadata nothing keeps true.
    """

    def test_backlog_without_priority_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="backlog", priority=None)
            self.assertTrue(
                any("priority required" in e for e in _priority_errors(t)),
                msg=f"expected a §19 missing-priority error, got: {t.errors}",
            )

    def test_active_without_priority_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="active", priority=None)
            self.assertTrue(any("priority required" in e for e in _priority_errors(t)))

    def test_done_needs_no_priority(self):
        # done/ is finished and parked/ is gated on a dated external trigger —
        # neither is waiting on us, so neither carries a priority (§19).
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="done", priority=None)
            self.assertEqual(_priority_errors(t), [])

    def test_unknown_level_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="HIGH")
            self.assertTrue(any("must be one of" in e for e in _priority_errors(t)))

    def test_p0_without_justification_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P0", priority_because=None)
            self.assertTrue(
                any("priority_because required" in e for e in _priority_errors(t)),
                msg=f"expected the §19.4 anti-inflation error, got: {t.errors}",
            )

    def test_p1_without_justification_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P1", priority_because="null")
            self.assertTrue(any("priority_because required" in e for e in _priority_errors(t)))

    def test_p0_with_justification_passes(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(
                Path(d), priority="P0",
                priority_because="Reproducible broken path on shipped code.",
            )
            self.assertEqual(_priority_errors(t), [])

    def test_block_scalar_marker_is_not_a_justification(self):
        # `priority_because: >-` with the sentence on the next line: this parser
        # is single-line, so the value IS ">-" and the reason is dropped. The
        # plain non-empty check passes on it. Caught in the wild the day §19 shipped.
        for marker in (">-", "|", ">", "|-"):
            with tempfile.TemporaryDirectory() as d:
                t = _make_queued_ticket(Path(d), priority="P1", priority_because=marker)
                self.assertTrue(
                    any("block-scalar" in e for e in _priority_errors(t)),
                    msg=f"{marker!r} must be refused as a justification, got: {t.errors}",
                )

    def test_p2_needs_no_justification(self):
        # P2 is the default. Requiring a justification for it would make every
        # filed ticket argue for itself, which is the friction §19 removes.
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P2", priority_because=None)
            self.assertEqual(_priority_errors(t), [])


@contextlib.contextmanager
def _sibling_repo_fixture(
    tid: str,
    *,
    branch_on_remote: bool,
    commit_id: str | None = None,
    local_branch_commit: str | None = None,
    break_trunk: bool = False,
):
    """Build a real meta + backend + bare-origin layout and yield (root, ticket).

    A fixture this heavy is warranted because the gate's whole claim is about
    git state — merged-and-cleaned-up vs still-in-flight — and that claim cannot
    be observed without a remote to delete a branch from. Patching REPO_ROOT to
    an empty temp dir only ever exercises the "unavailable" early return, which
    is how an earlier version of these tests stayed green while the code under
    them was broken.
    """
    branch = f"feat/{tid}-example"
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "meta").mkdir()
        origin = root / "origin-backend.git"
        subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
        work = root / "backend"
        git = ["git", "-c", "user.email=t@t.t", "-c", "user.name=t",
               "-c", "commit.gpgsign=false", "-C", str(work)]
        subprocess.run(["git", "init", "-q", "-b", "develop", str(work)], check=True)
        (work / "f.txt").write_text("x")
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", f"feat(x): the thing ({commit_id or tid})"],
                       check=True)
        subprocess.run([*git, "remote", "add", "origin", str(origin)], check=True)
        subprocess.run([*git, "push", "-q", "origin", "develop"], check=True)
        # ALWAYS push the branch, then delete it on the remote when the case
        # under test is "merged and cleaned up". Deleting leaves a STALE local
        # `refs/remotes/origin/<branch>` behind — which is the exact condition
        # that made an earlier version of the gate unable to fire. Never
        # creating the branch would skip that condition entirely.
        subprocess.run([*git, "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], check=True)
        subprocess.run([*git, "fetch", "-q", "origin"], check=True)
        if not branch_on_remote:
            # Delete INSIDE the bare repo, not via `git push --delete` from this
            # clone — `push --delete` also drops the local remote-tracking ref,
            # so the clone would learn about the deletion and the stale-ref
            # condition would never exist. Deleting server-side (as another
            # developer, or `gh pr merge --delete-branch`, does) leaves this
            # clone holding `refs/remotes/origin/<branch>` for a branch that is
            # gone. That is the exact state that made an earlier version of the
            # gate unable to fire, so the fixture has to reproduce it.
            subprocess.run(["git", "-C", str(origin), "update-ref", "-d",
                            f"refs/heads/{branch}"], check=True)
        if local_branch_commit is not None:
            # A LOCAL feature head carrying a commit off trunk. The fixture above
            # only ever creates the branch on the REMOTE, so without this the
            # never-pushed / in-flight exemption is unreachable and its tests
            # would be vacuous (measured — a second-model review found exactly
            # that gap).
            subprocess.run([*git, "checkout", "-q", "-b", branch], check=True)
            (work / "wip.txt").write_text("wip")
            subprocess.run([*git, "add", "-A"], check=True)
            subprocess.run(
                [*git, "commit", "-qm", f"feat(x): work in progress ({local_branch_commit})"],
                check=True,
            )
            subprocess.run([*git, "checkout", "-q", "develop"], check=True)
        if break_trunk:
            # Drop the remote-tracking trunk refs so no trunk resolves. The gate
            # then has no commit evidence at all and must say UNAVAILABLE, not
            # return an empty (== clean) finding list.
            for ref in ("origin/develop", "origin/main"):
                subprocess.run([*git, "update-ref", "-d", f"refs/remotes/{ref}"], check=False)
        original_root, original_repos = bi.REPO_ROOT, bi.SIBLING_REPOS
        bi.REPO_ROOT = root / "meta"
        # The template ships SIBLING_REPOS empty (unconfigured); the fixture
        # stands in for a project that configured its one code repo.
        bi.SIBLING_REPOS = ("backend",)
        try:
            t = _make_queued_ticket(root, tid=tid, status="active")
            t.frontmatter["branch"] = branch
            yield root, t
        finally:
            bi.REPO_ROOT = original_root
            bi.SIBLING_REPOS = original_repos


class Section151ShipGate(unittest.TestCase):
    """GOVERNANCE §15.1 — merged work ships, it does not pause.

    The gate reads sibling sub-repos that do NOT exist in meta-only CI. It must
    report itself UNAVAILABLE there rather than returning a clean pass, because
    a check that silently no-ops reads exactly like a check that found nothing.
    """

    def test_unconfigured_sibling_repos_report_unavailable_not_pass(self):
        # The template ships SIBLING_REPOS empty. Unconfigured must be
        # REPORTED, never a silent pass — a gate that silently no-ops reads
        # exactly like a gate that found nothing.
        self.assertEqual(bi.SIBLING_REPOS, ())
        errors, unavailable = bi.validate_shipped_but_active([])
        self.assertEqual(errors, [])
        self.assertIsNotNone(
            unavailable,
            msg="unconfigured SIBLING_REPOS must be REPORTED, never silently passed",
        )
        self.assertIn("did NOT run", unavailable)

    def test_absent_sibling_repos_report_unavailable_not_pass(self):
        original_root, original_repos = bi.REPO_ROOT, bi.SIBLING_REPOS
        try:
            with tempfile.TemporaryDirectory() as d:
                # Configured repos, but none of them beside this meta root.
                bi.REPO_ROOT = Path(d) / "meta"
                bi.REPO_ROOT.mkdir()
                bi.SIBLING_REPOS = ("backend", "frontend", "infra")
                errors, unavailable = bi.validate_shipped_but_active([])
                self.assertEqual(errors, [])
                self.assertIsNotNone(
                    unavailable,
                    msg="absent sibling repos must be REPORTED, never silently passed",
                )
                self.assertIn("did NOT run", unavailable)
        finally:
            bi.REPO_ROOT = original_root
            bi.SIBLING_REPOS = original_repos

    def test_merged_and_deleted_branch_is_reported(self):
        with _sibling_repo_fixture("EX-1", branch_on_remote=False) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable, msg="fixture should make the gate runnable")
            self.assertTrue(
                any("EX-1" in e and "still" in e for e in errors),
                msg=f"merged + deleted branch must be reported, got: {errors}",
            )

    def test_live_branch_is_not_reported(self):
        # The signal is NOT "has commits on trunk": a project that merges a
        # feature branch to trunk repeatedly (to exercise staging) has
        # mid-flight tickets with trunk commits. Only branch-gone + commits fires.
        with _sibling_repo_fixture("EX-1", branch_on_remote=True) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertEqual(
                errors, [],
                msg="a ticket whose branch is still on the remote is IN FLIGHT",
            )

    def test_ticket_without_branch_is_skipped(self):
        # branch: null carries no signal to test against — it must not be
        # guessed at in either direction. Uses the real fixture: with no sibling
        # repos the function returns before this code, so the assertion would be
        # unfalsifiable (measured — an earlier version of this test stayed green
        # when the skip was replaced with an invented branch name).
        with _sibling_repo_fixture("EX-1", branch_on_remote=False) as (root, t):
            t.frontmatter["branch"] = None
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertEqual(errors, [])

    def test_never_pushed_branch_with_own_commits_is_in_flight(self):
        # `git ls-remote` reports an ABSENCE, not a history, so it cannot
        # tell DELETED-AFTER-MERGE from NEVER-PUSHED. Every ticket sits in the second
        # state between /ticket-start and its first push, and the gate used to fire
        # `exit 1` on all of them — blocking every meta commit, which is how a hook
        # gets --no-verify'd.
        with _sibling_repo_fixture(
            "EX-99", branch_on_remote=False, local_branch_commit="EX-99"
        ) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertEqual(
                errors, [],
                msg="a local branch carrying THIS ticket's unmerged commits is IN FLIGHT",
            )

    def test_shared_increment_branch_does_not_hide_a_merged_ticket(self):
        # The regression the first version of the exemption introduced, caught by a
        # second-model review before it shipped. GOVERNANCE §7 puts several tickets on
        # ONE increment branch on purpose. If the exemption
        # asks "does this branch have ANY unmerged commit" rather than "any unmerged
        # commit FOR THIS TICKET", then one later ticket-B commit exempts the already
        # merged ticket A — the gate silently passing on the exact state it exists to
        # catch, which is strictly worse than the false positive it was removing.
        with _sibling_repo_fixture(
            "EX-99", branch_on_remote=False, local_branch_commit="EX-98"
        ) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertTrue(
                any("EX-99" in e for e in errors),
                msg=(
                    "EX-99's own commit is on trunk and only EX-98 has unmerged work — "
                    f"EX-99 has MERGED and must still be reported, got: {errors}"
                ),
            )

    def test_body_cross_reference_does_not_exempt_a_merged_ticket(self):
        # Round-2 counterexample, constructed and confirmed in the source project: while the
        # exemption matched subject+body, an unrelated WIP commit whose BODY said
        # "See EX-99" was enough to exempt a MERGED EX-99 as "in flight" — the same
        # ambiguity as predicate 2 (EX-23), re-entering through the exemption.
        # The exemption now matches SUBJECTS only, because its safe failure
        # direction is the opposite of predicate 2's.
        with _sibling_repo_fixture(
            "EX-99", branch_on_remote=False,
            local_branch_commit="EX-98)\n\nSee EX-99 for the background",
        ) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertTrue(
                any("EX-99" in e for e in errors),
                msg=(
                    "a BODY mention of EX-99 in someone else's commit is a cross-reference, "
                    f"not EX-99's own unmerged work — it must not exempt. Got: {errors}"
                ),
            )

    def test_unreadable_local_heads_report_unavailable_not_merged(self):
        # A failed `for-each-ref` used to collapse to an empty set, i.e. "no local
        # branches" — which makes every in-flight ticket look MERGED. Claiming a
        # merge on a failed git command is the loudest way to be wrong.
        with _sibling_repo_fixture("EX-99", branch_on_remote=False) as (root, t):
            real_git = bi._git

            def fake_git(repo, *args):
                if args and args[0] == "for-each-ref":
                    return 1, "<git unavailable: constructed>"
                return real_git(repo, *args)

            bi._git = fake_git
            try:
                errors, unavailable = bi.validate_shipped_but_active([t])
            finally:
                bi._git = real_git
            self.assertEqual(errors, [], msg="a failed git call must not produce a MERGED finding")
            self.assertIsNotNone(unavailable)
            self.assertIn("enumerate local branches", unavailable)

    def test_failed_git_log_reports_unavailable_not_merged(self):
        # The OTHER git-failure path. `test_unreadable_local_heads_...` exits at the
        # `for-each-ref` guard and never reaches `_branch_holds_unmerged_work`, so
        # without this test the helper's `return None` had no red state — measured:
        # reverting it to `return False` left the suite green.
        with _sibling_repo_fixture(
            "EX-99", branch_on_remote=False, local_branch_commit="EX-99"
        ) as (root, t):
            real_git = bi._git
            branch = t.frontmatter["branch"]

            def fake_git(repo, *args):
                if args[:2] == ("log", branch):
                    return 1, "<git unavailable: constructed>"
                return real_git(repo, *args)

            bi._git = fake_git
            try:
                errors, unavailable = bi.validate_shipped_but_active([t])
            finally:
                bi._git = real_git
            self.assertEqual(
                errors, [],
                msg="a failed `git log` must not be reported as a MERGED ticket",
            )
            self.assertIsNotNone(unavailable)
            self.assertIn("git log failed", unavailable)
            self.assertIn("EX-99", unavailable)

    def test_no_resolvable_trunk_reports_unavailable_not_clean(self):
        # §Step 0d, the local half. With no trunk ref there is no commit evidence, so
        # every ticket is skipped — and an empty finding list is the same output as
        # "graded them all, none merged". The remote half of this was already guarded;
        # the local half was not.
        with _sibling_repo_fixture("EX-99", branch_on_remote=False, break_trunk=True) as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertEqual(errors, [])
            self.assertIsNotNone(
                unavailable, msg="no readable trunk must be reported, never clean"
            )
            # Name the TICKET, not just the condition — a generic "something was
            # unavailable" is the same output whether one ticket or all of them went
            # ungraded, which is the shape this check exists to refuse.
            self.assertIn("UNVERIFIED, not clean", unavailable)
            self.assertIn("EX-99", unavailable)

    def test_grandfather_list_covers_only_its_own_ids(self):
        # SHIP_GATE_GRANDFATHERED is a bypass. A bypass that swallowed every
        # ticket would read exactly like a gate that found nothing, so pin both
        # directions: a listed id is skipped, an unlisted one still blocks.
        # The template ships the list empty, so a synthetic entry stands in.
        original = bi.SHIP_GATE_GRANDFATHERED
        bi.SHIP_GATE_GRANDFATHERED = frozenset({"EX-7"})
        self.addCleanup(setattr, bi, "SHIP_GATE_GRANDFATHERED", original)
        with _sibling_repo_fixture("EX-7", branch_on_remote=False) as (root, t):
            errors, _ = bi.validate_shipped_but_active([t])
            self.assertEqual(errors, [], msg="EX-7 is grandfathered — must not block")
        with _sibling_repo_fixture("EX-99", branch_on_remote=False) as (root, t):
            errors, _ = bi.validate_shipped_but_active([t])
            self.assertTrue(errors, "an UNLISTED merged-but-active ticket must still block")

    def test_grandfather_list_only_shrinks(self):
        # Pins the SET, not its size. Pinning only a length lets any N ids
        # pass, so swapping the whole list for different tickets stays green —
        # the invariant it claims to hold would not be constrained at all.
        # The template ships the list EMPTY. If your adoption sweep added ids,
        # write them into BASELINE once — afterwards the list may only shrink.
        BASELINE: frozenset[str] = frozenset()
        added = bi.SHIP_GATE_GRANDFATHERED - BASELINE
        self.assertEqual(added, set(), msg=f"ids ADDED to the grandfather list: {added}")

    def test_id_match_is_word_bounded(self):
        # A substring grep would let EX-1's gate fire on a EX-12 commit and
        # attribute one ticket's merge to another.
        with _sibling_repo_fixture("EX-1", branch_on_remote=False,
                                   commit_id="EX-12") as (root, t):
            errors, unavailable = bi.validate_shipped_but_active([t])
            self.assertIsNone(unavailable)
            self.assertEqual(
                errors, [],
                msg="EX-1 must not match a commit naming EX-12",
            )



class Section93SpawnedDefault(unittest.TestCase):
    """GOVERNANCE §9.3 — a SPAWNED backlog P2 must say who is hurt and when,
    or it is a P3. Exists because a universal P2 default once made 164 of 166
    open tickets equal (measured in the source project)."""

    def test_spawned_backlog_p2_without_because_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P2")
            t.frontmatter["discovered_from"] = "EX-0"
            ref = _make_queued_ticket(Path(d), tid="EX-0", priority="P3")
            self.assertTrue(
                any("spawned backlog P2" in e for e in _priority_errors(t, ref)),
                msg=f"expected the amended §9.3 spawned-P2 error, got: {t.errors}",
            )

    def test_spawned_backlog_p2_with_because_passes(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(
                Path(d), priority="P2",
                priority_because="Launch — a real client hits X during Y.",
            )
            t.frontmatter["discovered_from"] = "EX-0"
            ref = _make_queued_ticket(Path(d), tid="EX-0", priority="P3")
            self.assertEqual(_priority_errors(t, ref), [])
            self.assertEqual(t.errors, [], msg="fixture must be valid on EVERY axis")

    def test_root_backlog_p2_needs_no_because(self):
        # A root ticket (customer / roadmap / business plan) defaults P2 and
        # carries no obligation — the flipped default is for SPAWNED work only.
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P2")
            self.assertEqual(_priority_errors(t), [])

    def test_spawned_active_p2_is_grandfathered(self):
        # Scoped to backlog on purpose — birth happens at filing; an active
        # ticket was promoted through /ticket-start's queue gate already.
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="active", priority="P2")
            t.frontmatter["discovered_from"] = "EX-0"
            ref = _make_queued_ticket(Path(d), tid="EX-0", priority="P3")
            self.assertEqual(_priority_errors(t, ref), [])

    def test_bogus_proposed_priority_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P3")
            t.frontmatter["proposed_priority"] = "P9"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(
                any("proposed_priority" in e for e in t.errors),
                msg=f"expected the §9.2 proposed_priority error, got: {t.errors}",
            )


class Section92QueueCap(unittest.TestCase):
    """GOVERNANCE §9.2 — the Execution queue holds at most
    QUEUE_CAP live items, and a MISSING marker is an error, never a silent
    pass (a format drift that disables a check is the guard-that-cannot-fail)."""

    def _run(self, roadmap_text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "ROADMAP.md", roadmap_text)
            original = bi.REPO_ROOT
            bi.REPO_ROOT = root
            try:
                return bi.validate_queue_cap()
            finally:
                bi.REPO_ROOT = original

    @staticmethod
    def _queue(n: int) -> str:
        items = "\n".join(f"{i}. item {i}" for i in range(1, n + 1))
        return f"# R\n\n<!-- queue:begin -->\n{items}\n<!-- queue:end -->\n"

    def test_cap_items_pass(self):
        self.assertEqual(self._run(self._queue(bi.QUEUE_CAP)), [])

    def test_over_cap_fails(self):
        errs = self._run(self._queue(bi.QUEUE_CAP + 1))
        self.assertTrue(errs and f"cap is {bi.QUEUE_CAP}" in errs[0],
                        msg=f"expected the queue-cap error, got: {errs}")

    def test_struck_items_do_not_count(self):
        text = self._queue(bi.QUEUE_CAP).replace(
            f"{bi.QUEUE_CAP}. item {bi.QUEUE_CAP}",
            f"{bi.QUEUE_CAP}. ~~shipped~~\n{bi.QUEUE_CAP + 1}. item live",
        )
        self.assertEqual(self._run(text), [])

    def test_two_marker_pairs_is_an_error_not_an_undercount(self):
        # find()-first-occurrence counted only the first section (executed
        # during review: 5+5 items, cap 7, no error). Duplicates are
        # named, never skipped.
        text = self._queue(5) + self._queue(5)
        errs = self._run(text)
        self.assertTrue(errs and "exactly once" in errs[0],
                        msg=f"expected the duplicate-marker error, got: {errs}")

    def test_inline_struck_fragment_still_counts_as_live(self):
        # `6. ~~EX-86~~ EX-44 — remaining half` is a live promise. Only a
        # FULLY-struck entry is exempt.
        items = "\n".join(f"{i}. ~~old~~ item {i}" for i in range(1, bi.QUEUE_CAP + 2))
        text = f"# R\n\n<!-- queue:begin -->\n{items}\n<!-- queue:end -->\n"
        errs = self._run(text)
        self.assertTrue(errs and f"cap is {bi.QUEUE_CAP}" in errs[0],
                        msg=f"inline fragments must count as live, got: {errs}")

    def test_missing_marker_is_an_error_not_a_pass(self):
        errs = self._run("# R\n\n1. item\n")
        self.assertTrue(errs and "missing" in errs[0],
                        msg=f"expected the missing-marker error, got: {errs}")



class HealthGauge(unittest.TestCase):
    """GOVERNANCE §19.8 — the monthly gauge. These exist because a review
    round found three shipped defects that were each one assertion away: an
    absolute-zero tripwire silent at 95.5%% spawned, a malformed date silently
    dropped toward "healthy", and a proposals reader scoped narrower than its
    validator."""

    TODAY = bi._dt.date(2026, 8, 19)

    @staticmethod
    def _t(tmp, tid, status="backlog", **extra):
        t = _make_queued_ticket(Path(tmp), tid=tid, status=status)
        t.frontmatter.update(extra)
        return t

    def test_tripwire_fires_on_ratio_not_absolute_zero(self):
        # 9 spawned + 1 ROOT = 90% spawned, 10 created vs 0 closed. The old
        # `n_root == 0` predicate stays silent here; the ratio must fire.
        with tempfile.TemporaryDirectory() as d:
            ts = [self._t(d, f"EX-{i}", created="2026-08-10", discovered_from="EX-0")
                  for i in range(1, 10)]
            ts.append(self._t(d, "EX-99", created="2026-08-10"))
            out = bi.health_report(ts, self.TODAY)
            self.assertIn("TRIPWIRE", out, msg=out)

    def test_tripwire_silent_when_root_share_is_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            ts = [self._t(d, f"EX-{i}", created="2026-08-10", discovered_from="EX-0")
                  for i in range(1, 6)]
            ts += [self._t(d, f"EX-{i}", created="2026-08-10") for i in range(6, 11)]
            out = bi.health_report(ts, self.TODAY)
            self.assertNotIn("TRIPWIRE", out, msg=out)

    def test_malformed_created_is_counted_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            ts = [self._t(d, "EX-1", created="2026-08-10"),
                  self._t(d, "EX-2", created="2026-08-1", discovered_from="EX-1")]
            out = bi.health_report(ts, self.TODAY)
            self.assertIn("MALFORMED DATES: 1", out, msg=out)

    def test_blocked_ticket_proposal_is_listed(self):
        # A proposal must resurface from EVERY waiting status, or silence
        # becomes "gone" — the exact failure the field exists to prevent.
        with tempfile.TemporaryDirectory() as d:
            t = self._t(d, "EX-3", status="blocked", created="2026-08-10",
                        proposed_priority="P1")
            out = bi.health_report([t], self.TODAY)
            self.assertIn("UNANSWERED PROPOSALS (1)", out, msg=out)
            self.assertIn("EX-3 [blocked]", out, msg=out)

    def test_valid_proposed_priority_passes_validation(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P3")
            t.frontmatter["proposed_priority"] = "P2"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertFalse([e for e in t.errors if "proposed_priority" in e],
                             msg=f"valid proposal must pass, got: {t.errors}")

    def test_proposed_priority_on_done_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="done", priority=None)
            t.frontmatter["proposed_priority"] = "P1"
            bi.validate([t], epic_codes={"EX"}, synonyms={})
            self.assertTrue(any("proposed_priority must be absent" in e for e in t.errors),
                            msg=f"expected the done-proposal error, got: {t.errors}")

    def test_spawned_p2_block_scalar_marker_is_rejected(self):
        # The §19.4 branch rejected ">-" from day one; the §9.3 branch shipped
        # without the marker check. One shared helper now.
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), priority="P2", priority_because=">-")
            t.frontmatter["discovered_from"] = "EX-0"
            ref = _make_queued_ticket(Path(d), tid="EX-0", priority="P3")
            self.assertTrue(
                any("spawned backlog P2" in e for e in _priority_errors(t, ref)),
                msg=f"a block-scalar marker is not a reason; got: {t.errors}",
            )



class Section195Inversion(unittest.TestCase):
    """GOVERNANCE §19.5 — a blocker inherits its dependents' urgency; a P2
    blocked_by a P3 is a promise the system has already decided never to keep.
    Live instance in the source project: three P2s blocked_by one P3,
    --validate green."""

    def _pair(self, d, upper, lower):
        a = _make_queued_ticket(Path(d), tid="EX-1", priority=upper,
                                priority_because="Launch — someone hits X at Y.")
        b = _make_queued_ticket(Path(d), tid="EX-2", priority=lower,
                                priority_because="Launch — someone hits X at Y.")
        a.frontmatter["blocked_by"] = ["EX-2"]
        bi.validate([a, b], epic_codes={"EX"}, synonyms={})
        return a

    def test_p2_blocked_by_p3_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._pair(d, "P2", "P3")
            self.assertTrue(any("priority inversion" in e for e in a.errors),
                            msg=f"expected the inversion error, got: {a.errors}")

    def test_equal_priorities_pass(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._pair(d, "P3", "P3")
            self.assertFalse([e for e in a.errors if "inversion" in e])

    def test_blocker_stronger_than_dependent_passes(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._pair(d, "P3", "P1")
            self.assertFalse([e for e in a.errors if "inversion" in e])


class Section92QueueMembership(unittest.TestCase):
    """GOVERNANCE §9.2 + §19.5 — a P0/P1 is a promise by definition, so it
    must APPEAR in the queue; otherwise the filed-but-invisible failure stays
    reproducible for exactly the tickets that matter most."""

    def _run(self, roadmap_text, tickets):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "ROADMAP.md", roadmap_text)
            original = bi.REPO_ROOT
            bi.REPO_ROOT = root
            try:
                return bi.validate_queue_cap(tickets)
            finally:
                bi.REPO_ROOT = original

    def test_unslotted_p1_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), tid="EX-9", priority="P1",
                                    priority_because="Trigger 3 — broken path.")
            text = "# R\n\n<!-- queue:begin -->\n1. other work\n<!-- queue:end -->\n"
            errs = self._run(text, [t])
            self.assertTrue(errs and "appears nowhere" in errs[0],
                            msg=f"expected the membership error, got: {errs}")

    def test_slotted_p1_passes(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), tid="EX-9", priority="P1",
                                    priority_because="Trigger 3 — broken path.")
            text = "# R\n\n<!-- queue:begin -->\n1. **EX-9** — fix it\n<!-- queue:end -->\n"
            self.assertEqual(self._run(text, [t]), [])

    def test_p2_needs_no_slot(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), tid="EX-9", priority="P2")
            text = "# R\n\n<!-- queue:begin -->\n1. other work\n<!-- queue:end -->\n"
            self.assertEqual(self._run(text, [t]), [])



class ReReviewRegressions(unittest.TestCase):
    """Re-review regressions — each was one assertion away."""

    TODAY = bi._dt.date(2026, 8, 19)

    def _cap(self, items):
        text = "# R\n\n<!-- queue:begin -->\n" + "\n".join(items) + "\n<!-- queue:end -->\n"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "ROADMAP.md", text)
            original = bi.REPO_ROOT
            bi.REPO_ROOT = root
            try:
                return bi.validate_queue_cap([])
            finally:
                bi.REPO_ROOT = original

    def test_n1_struck_both_ends_live_middle_counts(self):
        items = [f"{i}. ~~EX-8{i}~~ EX-44 live half ~~429 part~~" for i in range(1, 9)]
        errs = self._cap(items)
        self.assertTrue(errs and f"cap is {bi.QUEUE_CAP}" in errs[0],
                        msg=f"8 live-middled items must breach the cap, got: {errs}")

    def test_n1_annotated_strike_counts_live_by_design(self):
        items = [f"{i}. ~~EX-10{i}~~ **DONE YYYY-MM-DD** — #116" for i in range(1, 9)]
        errs = self._cap(items)
        self.assertTrue(errs, msg="annotated strikes must count live (forces the move)")

    def test_n1_bare_strike_is_exempt(self):
        items = [f"{i}. item {i}" for i in range(1, 8)] + ["8. ~~shipped whole~~"]
        self.assertEqual(self._cap(items), [])

    def test_n2_two_bad_dates_is_one_ticket(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d), status="done", priority=None)
            t.frontmatter["created"] = "2026-08-1"
            t.frontmatter["updated"] = "2026-8-19"
            out = bi.health_report([t], self.TODAY)
            self.assertIn("MALFORMED DATES: 1", out, msg=out)

    def test_n3_tripwire_needs_ten_created(self):
        with tempfile.TemporaryDirectory() as d:
            t = _make_queued_ticket(Path(d))
            t.frontmatter["created"] = "2026-08-10"
            t.frontmatter["discovered_from"] = "EX-0"
            out = bi.health_report([t], self.TODAY)
            self.assertNotIn("TRIPWIRE", out, msg="one quiet ticket must not cry wolf")

    def test_n5_indentation_indicator_markers_rejected(self):
        for marker in (">2", "|2-", ">1+"):
            self.assertEqual(bi.because_problem(marker), "marker", msg=marker)
        self.assertIsNone(bi.because_problem("Launch — a client hits X at Y."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
