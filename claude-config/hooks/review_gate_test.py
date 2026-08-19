#!/usr/bin/env python3
"""Tests for review_gate.py — the commit + claim gates.

Zero external dependencies (stdlib `unittest`), mirroring `scripts/test_build_index.py`. Run from the
meta repo root:

    python3 claude-config/hooks/review_gate_test.py

Every case is a shape measured in the transcript corpus or one that broke an earlier version. The
fail-closed paths are asserted to BLOCK and the genuinely-clear paths asserted NOT to — a gate whose
red state is unreachable would be this ticket's own defect shipped as its fix.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import review_gate as rg  # noqa: E402

SESSION = "abcdef1234567890"


class CommitDetection(unittest.TestCase):
    COMMIT_PRODUCING = (
        "git commit -m x",
        "git commit --no-verify -q -F -",
        "git -C /x/y commit -q -m z",
        'git -c user.name="$(git config user.name)" commit -q -m a',
        "git add -A && git commit -q -m b",
        'cd meta && git add -A && git -c user.name="$(git config user.name)" commit -q -m c',
        r"git com\mit -m x",
        'g"it" com"mit" -m x',
        "git commit -a -m x",
        "/usr/bin/git commit -m x",
        "git merge --no-ff topic",
        "git merge --squash x",
        "git cherry-pick abc123",
        "git rebase --continue",
        "git am patch.mbox",
        "git revert HEAD",
        "git commit-tree HEAD^{tree}",
        "git pull --rebase",
    )
    NOT_COMMIT_PRODUCING = (
        "git add -- new_session.md .pre-commit-config.yaml",
        "git diff GOVERNANCE.md .pre-commit-config.yaml",
        "git log --oneline -1",
        "git log --format=%H -- .pre-commit-config.yaml",
        "git rev-parse HEAD",
        "git status --porcelain",
        "git push origin develop",
        "git stash",
        "pre-commit run --all-files",
        'echo "=== git: was additional_information touched by the reorder commit?"',
        "echo git commit",
    )

    def test_commit_producing_detected(self) -> None:
        for command in self.COMMIT_PRODUCING:
            with self.subTest(command=command):
                self.assertTrue(rg.commit_ops(command), command)

    def test_non_commit_not_detected(self) -> None:
        for command in self.NOT_COMMIT_PRODUCING:
            with self.subTest(command=command):
                self.assertEqual(rg.commit_ops(command), [], command)

    WRAPPED = ("env FOO=bar git commit -m x", "sudo git commit -m x", "nohup git commit -m x",
               "time git commit -m x", "/usr/bin/env git commit -m x")

    def test_transparent_wrappers_do_not_hide_a_commit(self) -> None:
        """`env`/`sudo`/`nohup`/`time` all waved the commit through. Second-model review, this diff."""
        for command in self.WRAPPED:
            with self.subTest(command=command):
                self.assertTrue(rg.commit_ops(command), command)

    def test_pathspec_naming_another_repo_is_gated(self) -> None:
        self.assertEqual(
            rg.resolve_repos("git commit -m x ../backend/file.py", "/repo/meta"), {"meta", "backend"},
        )

    def test_meta_paths_do_not_widen_the_repo_set(self) -> None:
        self.assertEqual(rg.resolve_repos("git commit -m x tickets/a.md", "/repo/meta"), {"meta"})

    NESTED_BYPASSES = ('bash -c "git commit -m x"', "sh -c 'git commit -m x'",
                       'eval "git commit -m x"', "xargs git commit -m x",
                       "gh pr merge 117 --repo x --merge")

    REPRODUCED_BYPASSES = (
        # Every one of these walked through the gate as a real commit
        # (reproduced in review, with controls). Each names its cause.
        "for r in a b; do git -C $r commit -m x; done",          # keywords cleared position
        'git add . && if [ -n "x" ]; then git commit -m x; fi',  # `then` cleared position
        "eval git commit -m x",                                   # eval took only the first word
        "sudo -u me git commit -m x",                             # wrapper option VALUE cleared position
        "nice -n 10 git commit -m x",
        "env -i git commit -m x",
        'bash -o errexit -c "git commit -m x"',                   # first non-option was an option VALUE
        "timeout 120 git commit -m x",                            # wrapper missing from the set
        "sed -i s#a#b# f.txt && git commit -am x",                # shlex comment ate the joined line
        'echo a#b && git commit -m x',
        "builtin git commit -m x",                                # sibling of command/exec
        "builtin eval git commit -m x",
        "runuser -u me git commit -m x",                          # sibling of sudo/doas
        # whitespace_split=False splits `$`,`,`,`:` into their own tokens (they
        # are neither wordchars nor punctuation_chars), so the -C scan eats the
        # wrong token — this form pins the flag WITHOUT shell-variable syntax:
        "git -C /tmp/a,b commit -m x",
    )

    def test_reproduced_bypasses_are_now_caught(self) -> None:
        for command in self.REPRODUCED_BYPASSES:
            with self.subTest(command=command):
                self.assertTrue(rg.commit_ops(command), command)

    def test_keywords_and_comment_handling_do_not_over_block(self) -> None:
        # The anti-over-block half: prose `git`, a `#` in arguments, and loops
        # without commits stay clear.
        for command in ("for f in a b; do echo $f; done",
                        'echo "git: the reorder commit?" # commit later',
                        "sed -i s#a#b# f.txt && git status"):
            with self.subTest(command=command):
                self.assertEqual(rg.commit_ops(command), [], command)

    def test_nested_shells_and_gh_merge_are_detected(self) -> None:
        """All five walked straight through the tokeniser; `gh pr merge` is a documented merge path."""
        for command in self.NESTED_BYPASSES:
            with self.subTest(command=command):
                self.assertTrue(rg.commit_ops(command), command)

    def test_a_short_gh_pr_merge_is_detected(self) -> None:
        """The window width had no test: with a narrower slice the LONG form still matched, so the
        existing case masked a fail-open on the short one. Found by --triage, not by review."""
        for command in ("gh pr merge 1 --merge", "gh pr merge 1", "gh pr merge"):
            with self.subTest(command=command):
                self.assertTrue(rg.commit_ops(command), command)

    def test_other_gh_subcommands_are_not_commits(self) -> None:
        for command in ("gh pr view 1", "gh run list", "gh pr checks 1"):
            with self.subTest(command=command):
                self.assertEqual(rg.commit_ops(command), [], command)

    def test_a_nested_shell_without_a_commit_is_not_blocked(self) -> None:
        """The anti-over-block guard: `bash -lc` is used constantly for things that are not commits."""
        for command in ('bash -lc "pytest -q"', 'docker compose run app bash -lc "lint-check ."'):
            with self.subTest(command=command):
                self.assertEqual(rg.commit_ops(command), [], command)

    def test_a_backslash_continuation_is_detected(self) -> None:
        """3 of 3 real corpus cases were missed: the `\\`+newline left the token `\\ngit`."""
        self.assertTrue(rg.commit_ops("git add x && \\\n git commit -m y"))

    def test_an_unterminated_heredoc_is_unparseable_not_truncated(self) -> None:
        with self.assertRaises(ValueError):
            rg.commit_ops("cat <<EOF\nbody\ngit commit -m x")

    def test_the_repo_root_wins_over_an_inner_component(self) -> None:
        """`/repo/backend/meta` and `node_modules/ajv/meta` both resolved to meta and were ungated."""
        self.assertEqual(rg.resolve_repos("git commit -m x", "/repo/backend/meta"), {"backend"})
        self.assertEqual(
            rg.resolve_repos("git commit -m x", "/repo/frontend/node_modules/ajv/meta"), {"frontend"},
        )

    def test_multiline_block(self) -> None:
        """The shape that lost 77 of 432 real commits before `mark_line_breaks`."""
        command = "cd /repo/meta\ngit add -A\ngit commit -q -F - <<'MSG'\nchore: hi\nMSG"
        self.assertTrue(rg.commit_ops(command))

    def test_line_continuation_not_split(self) -> None:
        self.assertNotIn(";", rg.mark_line_breaks("git \\\n  commit -m x"))

    def test_heredoc_body_is_data(self) -> None:
        """Body UNQUOTED on purpose: quoting alone already defends the quoted case, so a quoted
        body cannot feel the heredoc guard being removed. This input can."""
        command = "cat > /tmp/n.md <<'EOF'\nThen run:\ngit commit -m x\nEOF"
        self.assertNotIn("git commit", rg.strip_heredocs(command))
        self.assertEqual(rg.commit_ops(command), [])

    def test_subcommands_in_order(self) -> None:
        ops = rg.commit_ops("git cherry-pick a && git commit -m b && git merge c")
        self.assertEqual([op[0] for op in ops], ["cherry-pick", "commit", "merge"])

    def test_unbalanced_quote_raises(self) -> None:
        with self.assertRaises(ValueError):
            rg.commit_ops('git commit -m "unterminated')

    def test_repo_resolution_prefers_dash_c(self) -> None:
        self.assertEqual(rg.resolve_repos("git -C /repo/frontend commit -m x", "/repo/meta"), {"frontend"})

    def test_repo_resolution_unknown_path_is_none(self) -> None:
        self.assertEqual(rg.resolve_repos("git commit -m x", "/somewhere/else"), {None})


LEAD_CONFIG = {
    "leadSessionId": SESSION,
    "members": [
        {"agentId": f"team-lead@session-{SESSION[:8]}", "name": "team-lead", "agentType": "team-lead"},
        {"agentId": f"rev-code@session-{SESSION[:8]}", "name": "rev-code", "agentType": "best-practices"},
    ],
}


class _Mailbox(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.teams = Path(self._tmp.name) / "teams"
        self.team_dir = self.teams / f"session-{SESSION[:8]}"
        self.inbox = self.team_dir / "inboxes"
        self.inbox.mkdir(parents=True)
        (self.team_dir / "config.json").write_text(json.dumps(LEAD_CONFIG))
        self.addCleanup(self._tmp.cleanup)
        for name in (rg.OVERRIDE_ENV, "REVIEW_GATE_TEAMS_ROOT"):
            os.environ.pop(name, None)

    def write(self, content: str) -> None:
        (self.inbox / "team-lead.json").write_text(content)

    def blocks(self) -> bool:
        pending, _why, undetermined = rg.pending_reports(self.teams, SESSION)
        return bool(pending) or undetermined


class PendingDetection(_Mailbox):
    def test_no_inbox_is_clear(self) -> None:
        """Lazily created: teammates exist, nobody has sent yet. Genuinely nothing pending."""
        self.assertFalse(self.blocks())

    def test_a_teammate_session_still_resolves_the_lead_team(self) -> None:
        """A teammate has its own session id and no team dir. Keying on session_id alone made every
        teammate — including the documented `committer` commit path — invisible to the gate."""
        self.write(json.dumps([{"from": "rev-code", "summary": "3 critical"}]))
        pending, _why, _u = rg.pending_reports(
            self.teams, "aaaabbbbccccdddd", f"rev-code@session-{SESSION[:8]}",
        )
        self.assertEqual(pending, ["rev-code: 3 critical"])

    def test_a_teammate_of_an_unrelated_team_is_not_governed(self) -> None:
        self.write(json.dumps([{"from": "rev-code", "summary": "3 critical"}]))
        pending, _why, undetermined = rg.pending_reports(
            self.teams, "aaaabbbbccccdddd", "who@session-99999999",
        )
        self.assertEqual(pending, [])
        self.assertFalse(undetermined)

    def test_the_lead_inbox_name_comes_from_config(self) -> None:
        """The doc guarantees the lead's agentType, not its mailbox FILENAME."""
        renamed = dict(LEAD_CONFIG)
        renamed["members"] = [{"agentId": "x", "name": "the-boss", "agentType": "team-lead"}]
        (self.team_dir / "config.json").write_text(json.dumps(renamed))
        (self.inbox / "the-boss.json").write_text(json.dumps([{"from": "r", "summary": "s"}]))
        resolved, problem = rg._lead_inbox(self.team_dir)
        self.assertEqual(problem, "")
        self.assertEqual(resolved, self.inbox / "the-boss.json")
        self.assertTrue(self.blocks())

    def test_an_unreadable_config_is_undeterminable(self) -> None:
        (self.team_dir / "config.json").write_text("{corrupt")
        pending, _why, undetermined = rg.pending_reports(self.teams, SESSION)
        self.assertEqual(pending, [])
        self.assertTrue(undetermined)

    def test_a_config_naming_no_lead_is_undeterminable(self) -> None:
        (self.team_dir / "config.json").write_text(json.dumps({"members": []}))
        self.assertTrue(rg.pending_reports(self.teams, SESSION)[2])

    def test_empty_list_is_clear(self) -> None:
        self.write("[]")
        self.assertFalse(self.blocks())

    def test_idle_notification_alone_is_clear(self) -> None:
        self.write(json.dumps([{"type": "idle_notification", "from": "rev", "idleReason": "available"}]))
        self.assertFalse(self.blocks())

    def test_idle_nested_as_json_string_is_clear(self) -> None:
        inner = json.dumps({"type": "idle_notification", "from": "rev"})
        self.write(json.dumps([{"content": inner}]))
        self.assertFalse(self.blocks())

    def test_report_blocks_and_is_described(self) -> None:
        self.write(json.dumps([{"from": "rev-code", "summary": "3 critical, 7 important"}]))
        pending, _why, _u = rg.pending_reports(self.teams, SESSION)
        self.assertEqual(pending, ["rev-code: 3 critical, 7 important"])

    def test_idle_marker_with_an_unexpected_key_still_blocks(self) -> None:
        """A report wearing an idle badge: marker present, no summary, findings in a body."""
        self.write(json.dumps([{"type": "idle_notification", "from": "r", "body": "CRITICAL x3"}]))
        self.assertTrue(self.blocks())

    def test_a_real_idle_notification_is_still_recognised(self) -> None:
        """The over-block guard: tightening idle detection must not block every idle notice."""
        self.write(json.dumps([
            {"type": "idle_notification", "from": "r", "timestamp": "t", "idleReason": "available"},
        ]))
        self.assertFalse(self.blocks())

    def test_a_summary_outside_a_clean_idle_payload_still_blocks(self) -> None:
        """The marked node looks like a textbook idle notice, so the key check passes it — the summary
        sits on the WRAPPER. That is the shape the all-nodes summary scan exists for."""
        inner = json.dumps({"type": "idle_notification", "from": "r", "timestamp": "t",
                            "idleReason": "available"})
        self.write(json.dumps([{"summary": "2 ship-blockers", "content": inner}]))
        self.assertTrue(self.blocks())

    def test_unrecognised_entry_blocks(self) -> None:
        self.write(json.dumps(["a bare string"]))
        self.assertTrue(self.blocks())

    def test_invalid_json_blocks(self) -> None:
        self.write("{not json")
        self.assertTrue(self.blocks())

    def test_non_list_json_blocks(self) -> None:
        self.write(json.dumps({"messages": []}))
        self.assertTrue(self.blocks())

    def test_report_without_summary_blocks(self) -> None:
        self.write(json.dumps([{"from": "rev-code", "body": "findings"}]))
        self.assertTrue(self.blocks())

    def test_unrecognised_session_id_is_undeterminable_not_clear(self) -> None:
        """A `session_id` of "../.." built a path that does not exist, which read as "nothing
        pending" and ALLOWED the commit. Found in the manual security pass on this diff."""
        for bad in ("../..", "/etc/passwd", "", "....//x", "session-../../x"):
            with self.subTest(session_id=bad):
                pending, _why, undetermined = rg.pending_reports(self.teams, bad)
                self.assertEqual(pending, [])
                self.assertTrue(undetermined, bad)

    def test_a_real_session_id_is_accepted(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "s"}]))
        pending, _why, undetermined = rg.pending_reports(self.teams, SESSION)
        self.assertTrue(pending)
        self.assertFalse(undetermined)

    def test_session_id_truncated_to_eight(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "s"}]))
        self.assertTrue(self.blocks())
        pending, _why, undetermined = rg.pending_reports(self.teams, "99999999aaaabbbb")
        self.assertFalse(bool(pending) or undetermined)


class OwnerPromptDetection(unittest.TestCase):
    """`_is_owner_prompt` had 0 tests and 0 mutations, and it sets the stop gate's turn boundary."""

    def test_meta_entries_are_not_owner_prompts(self) -> None:
        self.assertFalse(rg._is_owner_prompt({"type": "user", "isMeta": True,
                                              "message": {"content": "hi"}}))

    def test_non_external_user_types_are_not_owner_prompts(self) -> None:
        self.assertFalse(rg._is_owner_prompt({"type": "user", "userType": "internal",
                                              "message": {"content": "hi"}}))

    def test_an_empty_entry_is_not_an_owner_prompt(self) -> None:
        self.assertFalse(rg._is_owner_prompt({"type": "user", "message": {"content": "   "}}))

    def test_a_tool_result_is_not_an_owner_prompt(self) -> None:
        self.assertFalse(rg._is_owner_prompt({
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "ok"}]},
        }))

    def test_an_assistant_entry_is_not_an_owner_prompt(self) -> None:
        self.assertFalse(rg._is_owner_prompt({"type": "assistant", "message": {"content": "hi"}}))

    def test_a_plain_human_prompt_is_one(self) -> None:
        self.assertTrue(rg._is_owner_prompt({"type": "user", "userType": "external",
                                             "message": {"content": "do the thing"}}))

    def test_list_form_content_is_read(self) -> None:
        """19 real deliveries use list-form content; every stop fixture used a string."""
        entry = {"type": "user", "message": {"content": [
            {"type": "text", "text": '<teammate-message teammate_id="r">b</teammate-message>'}]}}
        self.assertFalse(rg._is_owner_prompt(entry))


class Describe(unittest.TestCase):
    """`describe()` builds the text the operator reads; none of it was asserted."""

    def test_summary_and_sender(self) -> None:
        self.assertEqual(rg.describe({"from": "rev", "summary": "3 critical"}), "rev: 3 critical")

    def test_teammate_id_is_used_when_from_is_absent(self) -> None:
        self.assertEqual(rg.describe({"teammate_id": "rev", "summary": "s"}), "rev: s")

    def test_sender_without_a_summary(self) -> None:
        self.assertEqual(rg.describe({"from": "rev", "body": "x"}), "rev: (no summary)")

    def test_a_summary_with_no_identifiable_sender(self) -> None:
        self.assertEqual(rg.describe({"summary": "3 critical"}), "?: 3 critical")

    def test_a_wholly_unrecognised_entry(self) -> None:
        self.assertEqual(rg.describe("a bare string"), "(unrecognised inbox entry)")


class Tokeniser(unittest.TestCase):
    """Pins tokeniser OUTPUT shapes. `whitespace_split=True` IS independently
    observable (a review differential harness measured five verdict changes
    when flipped): `punctuation_chars=True` extends wordchars only by
    `*-./=?~`, so `$`, `,` and `:` become standalone tokens without it and
    `git -C $r commit` / `git -C /tmp/a,b commit` degrade to MISS. The flip
    is red-stated via REPRODUCED_BYPASSES' `$r` and `/tmp/a,b` forms."""

    def test_quoting_is_honoured(self) -> None:
        """Without posix quote handling, a quoted string stops being one token and prose matches."""
        self.assertEqual(rg._tokenise('echo "git: the reorder commit?"'),
                         ["echo", "git: the reorder commit?"])

    def test_paths_stay_whole(self) -> None:
        """Paths must stay single tokens, whichever flag provides it."""
        self.assertIn("/repo/backend/file.py", rg._tokenise("git add /repo/backend/file.py"))


class CommitGate(_Mailbox):
    def pending(self) -> None:
        self.write(json.dumps([{"from": "rev-code", "summary": "3 critical"}]))

    def decide(self, command: str, cwd: str) -> tuple[bool, str]:
        return rg.decide_commit(
            command=command, cwd=cwd, session_id=SESSION, teams_root=self.teams,
        )

    def test_pending_blocks_a_backend_commit(self) -> None:
        self.pending()
        block, reason = self.decide("git commit -m x", "/repo/backend")
        self.assertTrue(block)
        self.assertIn("rev-code: 3 critical", reason)
        self.assertIn("END YOUR TURN NOW", reason)

    def test_drained_inbox_allows(self) -> None:
        self.write("[]")
        self.assertFalse(self.decide("git commit -m x", "/repo/backend")[0])

    def test_non_commit_never_blocked(self) -> None:
        self.pending()
        self.assertFalse(self.decide("git status --porcelain", "/repo/backend")[0])

    def test_meta_docs_commit_is_ungated(self) -> None:
        """76 of 257 broad-gate blocks in the corpus were meta-only — override fatigue, no safety."""
        self.pending()
        with unittest.mock.patch.object(rg, "_staged_code", return_value=[]):
            self.assertFalse(self.decide("git commit -m docs", "/repo/meta")[0])

    def test_meta_commit_staging_code_is_gated(self) -> None:
        """The meta repo's own tooling — this gate and the validator gating every commit — is code
        living in the "docs" repo. The carve-out is for tickets and docs, and it was ungating
        meta's own tooling, so a change to this gate could not have been blocked by its own rule."""
        self.pending()
        with unittest.mock.patch.object(rg, "_staged_code", return_value=["claude-config/hooks/x.py"]):
            block, reason = self.decide("git commit -m code", "/repo/meta")
        self.assertTrue(block)
        self.assertIn("stages CODE", reason)

    def test_meta_commit_with_an_unreadable_staged_set_is_gated(self) -> None:
        self.pending()
        with unittest.mock.patch.object(rg, "_staged_code", return_value=None):
            self.assertTrue(self.decide("git commit -m x", "/repo/meta")[0])

    def test_dash_c_into_backend_from_meta_is_gated(self) -> None:
        self.pending()
        self.assertTrue(self.decide("git -C /repo/backend commit -m x", "/repo/meta")[0])

    def test_unresolvable_repo_is_gated(self) -> None:
        """`_staged_code` is forced to succeed so this sees the repo comparison, not the staged check."""
        self.pending()
        with unittest.mock.patch.object(rg, "_staged_code", return_value=[]):
            self.assertTrue(self.decide("git commit -m x", "/somewhere/else")[0])

    def test_other_commit_producing_ops_are_gated(self) -> None:
        self.pending()
        for command in ("git merge topic", "git cherry-pick abc", "git rebase --continue"):
            with self.subTest(command=command):
                self.assertTrue(self.decide(command, "/repo/backend")[0])

    def test_unparseable_with_pending_blocks(self) -> None:
        self.pending()
        self.assertTrue(self.decide('git commit -m "unterminated', "/repo/backend")[0])

    def test_unparseable_when_drained_allows(self) -> None:
        self.write("[]")
        self.assertFalse(self.decide('git commit -m "unterminated', "/repo/backend")[0])

    def test_inline_override_in_the_command_works(self) -> None:
        """The hook runs in Claude Code's process, so an inline assignment never reaches os.environ.
        Reading only the environment made the documented escape hatch impossible to use."""
        self.pending()
        for command in (
            "REVIEW_GATE_OVERRIDE='reviewer died' git commit -m x",
            'REVIEW_GATE_OVERRIDE="reviewer died" git commit -m x',
            "REVIEW_GATE_OVERRIDE=reviewer-died git commit -m x",
        ):
            with self.subTest(command=command):
                block, reason = self.decide(command, "/repo/backend")
                self.assertFalse(block, command)
                self.assertTrue(reason.startswith("OVERRIDDEN: "))

    def test_a_corrupt_inbox_is_escapable(self) -> None:
        """Undeterminable + no usable override was an inescapable dead end."""
        self.write("{corrupt")
        self.assertTrue(self.decide("git commit -m x", "/repo/backend")[0])
        block, _reason = self.decide(
            "REVIEW_GATE_OVERRIDE='inbox corrupt' git commit -m x", "/repo/backend",
        )
        self.assertFalse(block)

    def test_override_allows_and_marks_itself(self) -> None:
        self.pending()
        os.environ[rg.OVERRIDE_ENV] = "reviewer process died"
        self.addCleanup(os.environ.pop, rg.OVERRIDE_ENV, None)
        block, reason = self.decide("git commit -m x", "/repo/backend")
        self.assertFalse(block)
        self.assertTrue(reason.startswith("OVERRIDDEN: "))

    def test_blank_override_does_not_count(self) -> None:
        self.pending()
        os.environ[rg.OVERRIDE_ENV] = "   "
        self.addCleanup(os.environ.pop, rg.OVERRIDE_ENV, None)
        self.assertTrue(self.decide("git commit -m x", "/repo/backend")[0])


class Cli(_Mailbox):
    """`main()` once had zero tests, and it is the SOLE implementation of the exit-code contract
    (2 blocks, 0 allows). Testable now that the log path is env-overridable; it was hardcoded
    to the operator's real home."""

    def setUp(self) -> None:
        super().setUp()
        (self.team_dir / "config.json").write_text(json.dumps(LEAD_CONFIG))
        self.log = Path(self._tmp.name) / "log.jsonl"
        os.environ["REVIEW_GATE_TEAMS_ROOT"] = str(self.teams)
        os.environ["REVIEW_GATE_LOG"] = str(self.log)
        self.addCleanup(os.environ.pop, "REVIEW_GATE_TEAMS_ROOT", None)
        self.addCleanup(os.environ.pop, "REVIEW_GATE_LOG", None)

    def invoke(self, payload: dict, mode: str = "pretooluse") -> int:
        with unittest.mock.patch.object(sys, "stdin") as stdin:
            stdin.buffer.read.return_value = json.dumps(payload).encode()
            return rg.main(["--mode", mode])

    def bash(self, command: str, cwd: str = "/repo/backend") -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd,
                "session_id": SESSION}

    def test_a_pending_report_exits_2(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "3 critical"}]))
        self.assertEqual(self.invoke(self.bash("git commit -m x")), 2)

    def test_a_drained_inbox_exits_0(self) -> None:
        self.write("[]")
        self.assertEqual(self.invoke(self.bash("git commit -m x")), 0)

    def test_a_non_bash_tool_exits_0(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "s"}]))
        self.assertEqual(self.invoke({"tool_name": "Read", "session_id": SESSION}), 0)

    def test_a_non_object_payload_exits_2(self) -> None:
        with unittest.mock.patch.object(sys, "stdin") as stdin:
            stdin.buffer.read.return_value = b"[]"
            self.assertEqual(rg.main(["--mode", "pretooluse"]), 2)

    def test_unparseable_stdin_exits_2(self) -> None:
        with unittest.mock.patch.object(sys, "stdin") as stdin:
            stdin.buffer.read.return_value = b"{not json"
            self.assertEqual(rg.main(["--mode", "pretooluse"]), 2)

    def test_non_utf8_stdin_exits_2_not_1(self) -> None:
        """An uncaught decode error exits 1, and PreToolUse treats 1 as NON-blocking — fail open."""
        with unittest.mock.patch.object(sys, "stdin") as stdin:
            stdin.buffer.read.return_value = b"\xff\xfe"
            self.assertEqual(rg.main(["--mode", "pretooluse"]), 2)

    def test_an_internal_exception_exits_2(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "s"}]))
        with unittest.mock.patch.object(rg, "decide_commit", side_effect=RuntimeError("boom")):
            self.assertEqual(self.invoke(self.bash("git commit -m x")), 2)

    def test_an_override_is_logged_with_audit_fields(self) -> None:
        self.write(json.dumps([{"from": "rev", "summary": "s"}]))
        code = self.invoke(self.bash("REVIEW_GATE_OVERRIDE='agent hung' git commit -m x"))
        self.assertEqual(code, 0)
        entry = json.loads(self.log.read_text().strip().splitlines()[-1])
        self.assertEqual(entry["reason"], "agent hung")
        for field in ("at", "mode", "session_id", "cwd", "command"):
            self.assertIn(field, entry)

    def test_a_teams_root_redirect_is_logged_as_a_bypass(self) -> None:
        """Redirecting the teams root disables every gate; it used to do so unlogged."""
        self.write("[]")
        self.invoke(self.bash("git commit -m x"))
        self.assertIn("teams-root redirected", self.log.read_text())


class StagedCodeDirect(unittest.TestCase):
    """_staged_code had ZERO direct tests — every call site mocked it, and an
    inverted returncode check (`!=` → `==`) survived the whole suite (measured
    in review). It inverts to: a FAILING `git diff` reads as "docs only"."""

    @staticmethod
    def _repo(d: Path) -> None:
        git = ["git", "-c", "user.email=t@t.t", "-c", "user.name=t", "-C", str(d)]
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        (d / "a.py").write_text("x = 1\n")
        (d / "b.md").write_text("# doc\n")
        subprocess.run([*git, "add", "a.py", "b.md"], check=True)

    def test_lists_code_and_skips_docs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self._repo(Path(d))
            self.assertEqual(rg._staged_code(d), ["a.py"])

    def test_settings_and_hooks_paths_are_code_whatever_the_extension(self) -> None:
        # A commit staging only `.claude/settings.json` — the file that WIRES
        # this gate — rode the docs carve-out (reproduced in review).
        with tempfile.TemporaryDirectory() as d:
            git = ["git", "-c", "user.email=t@t.t", "-c", "user.name=t", "-C", d]
            subprocess.run(["git", "init", "-q", d], check=True)
            claude_dir = Path(d) / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text("{}")
            subprocess.run([*git, "add", ".claude/settings.json"], check=True)
            self.assertEqual(rg._staged_code(d), [".claude/settings.json"])

    def test_outside_a_repo_returns_none_not_docs_only(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(rg._staged_code(d))


class CommitGateTargetRepo(_Mailbox):
    """H2 — the docs carve-out must read the staged set of the repo the commit
    TARGETS (`-C`), not the cwd (reproduced in review: code staged in the -C
    target, nothing staged in cwd → 'docs only' → allowed)."""

    def test_dash_c_carveout_reads_the_target_repo(self) -> None:
        self.write(json.dumps([{"from": "rev-code", "summary": "3 critical"}]))
        with tempfile.TemporaryDirectory() as d:
            meta_repo = Path(d) / "meta"
            meta_repo.mkdir()
            git = ["git", "-c", "user.email=t@t.t", "-c", "user.name=t", "-C", str(meta_repo)]
            subprocess.run(["git", "init", "-q", str(meta_repo)], check=True)
            (meta_repo / "tool.py").write_text("x = 1\n")
            subprocess.run([*git, "add", "tool.py"], check=True)
            block, reason = rg.decide_commit(
                command=f"git -C {meta_repo} commit -m x",
                cwd=d,  # cwd is NOT a repo and has nothing staged
                session_id=SESSION, teams_root=self.teams,
            )
            self.assertTrue(block, reason)
            self.assertIn("stages CODE", reason)


class UnreadableTeamConfig(_Mailbox):
    """H3 — a corrupt team config.json blocked the lead but silently ALLOWED a
    teammate: membership was unknowable, and the fall-through read as 'no
    teammates were spawned' (reproduced in review)."""

    def test_corrupt_config_is_undeterminable_for_a_teammate_too(self) -> None:
        (self.team_dir / "config.json").write_text("{corrupt")
        pending, why, undetermined = rg.pending_reports(
            self.teams, "aaaabbbbccccdddd", f"rev-code@session-{SESSION[:8]}",
        )
        self.assertEqual(pending, [])
        self.assertTrue(undetermined, why)


class StopHookActive(unittest.TestCase):
    """H5 — without this guard, our own block re-invokes us, the block message
    deliberately names no agent, stop-mode overrides cannot be set from inside
    the session, and the turn wedges permanently."""

    def _payload(self, tmp: Path, active: bool) -> dict:
        # A REAL transcript with a delivered report + a dismissing close: the
        # un-guarded gate must BLOCK this payload, so only the guard can make
        # it pass. (A nonexistent transcript exits 0 either way and cannot
        # distinguish the guard from its absence.)
        transcript = tmp / "t.jsonl"
        transcript.write_text(
            json.dumps({"type": "user", "userType": "external",
                        "message": {"content": "go"}}) + "\n"
            + json.dumps({"type": "user", "message": {"content": (
                'Another Claude session sent a message:\n<teammate-message '
                'teammate_id="rev-code" summary="3 critical">b</teammate-message>\n'
            )}}) + "\n"
        )
        return {
            "stop_hook_active": active,
            "transcript_path": str(transcript),
            "last_assistant_message": "0 reported, round clean.",
            "session_id": SESSION,
        }

    def _invoke(self, payload: dict) -> int:
        with unittest.mock.patch.object(sys, "stdin") as stdin:
            stdin.buffer.read.return_value = json.dumps(payload).encode()
            return rg.main(["--mode", "stop"])

    def test_stop_hook_active_passes_instead_of_wedging(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._invoke(self._payload(Path(d), active=True)), 0)

    def test_without_the_flag_the_same_payload_still_blocks(self) -> None:
        # The control: the guard must not weaken the gate for a normal close.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._invoke(self._payload(Path(d), active=False)), 2)


class StopGate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        os.environ.pop(rg.OVERRIDE_ENV, None)

    def transcript(self, *entries: dict) -> Path:
        path = self.dir / "t.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        return path

    @staticmethod
    def owner(text: str = "go build it") -> dict:
        return {"type": "user", "message": {"content": text}}

    @staticmethod
    def delivery(agent: str = "rev-code", summary: str = "3 critical", body: str = "body") -> dict:
        return {
            "type": "user",
            "message": {
                "content": (
                    f'Another Claude session sent a message:\n<teammate-message '
                    f'teammate_id="{agent}" summary="{summary}">{body}</teammate-message>\n'
                ),
            },
        }

    def test_blocks_a_summary_ignoring_a_delivered_report(self) -> None:
        block, reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery()),
            last_assistant_message="Committed everything and pushed. Moving on to the next ticket.",
        )
        self.assertTrue(block)
        self.assertIn("does not acknowledge", reason)

    def test_allows_a_summary_naming_the_reporter(self) -> None:
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery()),
            last_assistant_message="Correcting: rev-code reported 3 critical findings; fixing.",
        )
        self.assertFalse(block)

    def test_does_not_block_an_open_round(self) -> None:
        """Blocking here deadlocks: delivery is what the turn boundary does."""
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner()),
            last_assistant_message="2 spawned, 0 reported so far.",
        )
        self.assertFalse(block)

    def test_ignores_an_idle_notification(self) -> None:
        idle = self.delivery(summary="", body='{"type":"idle_notification","from":"rev-code"}')
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), idle),
            last_assistant_message="0 reported",
        )
        self.assertFalse(block)

    def test_only_looks_at_the_current_turn(self) -> None:
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(
                self.owner("turn one"), self.delivery(), self.owner("turn two"),
            ),
            last_assistant_message="done, nothing pending",
        )
        self.assertFalse(block)

    def test_a_single_enormous_line_is_skipped(self) -> None:
        # The oversized line must be VALID JSON carrying a real delivery: the
        # first fixture was raw "xxx…", which json.loads drops regardless, so
        # deleting the length clause left the whole suite green (measured in
        # review) — a guard that could not fail.
        path = self.dir / "huge.jsonl"
        entry = self.delivery(body="x" * (rg._MAX_LINE_BYTES + 10))
        path.write_text(json.dumps(self.owner()) + "\n" + json.dumps(entry) + "\n")
        self.assertEqual(rg.delivered_this_turn(path), [])

    def test_the_budget_reads_the_tail_not_the_head(self) -> None:
        # The current turn is at the END of a transcript that only grows. A
        # head-consumed budget silently and permanently disabled the gate the
        # moment the file outgrew it (reproduced in review).
        pad = [self.owner(f"noise {i} " + "z" * 200) for i in range(50)]
        path = self.transcript(*pad, self.owner(), self.delivery())
        small_budget = os.path.getsize(path) // 2
        self.assertTrue(
            rg.delivered_this_turn(path, byte_budget=small_budget),
            "a delivery at the END must be seen when the budget covers the tail",
        )

    def test_the_byte_budget_stops_an_endless_file(self) -> None:
        """/dev/zero read forever before the budget existed. Budget is injectable so the test does
        not have to write 64 MB to exercise it."""
        path = self.transcript(self.owner(), self.delivery())
        self.assertTrue(rg.delivered_this_turn(path))
        self.assertEqual(rg.delivered_this_turn(path, byte_budget=1), [])

    def test_a_directory_as_transcript_path_does_not_raise(self) -> None:
        self.assertEqual(rg.delivered_this_turn(self.dir), [])

    def test_an_agent_type_also_counts_as_acknowledgement(self) -> None:
        """It blocked a message saying "best-practices reported" because the instance was
        "myproj-best-practices" — substance acknowledged, refused on a string. Found live in the source project."""
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery(agent="myproj-best-practices")),
            last_assistant_message="best-practices found the gate could not see a teammate.",
            aliases={"myproj-best-practices": "best-practices"},
        )
        self.assertFalse(block)

    def test_an_unrelated_message_still_blocks_even_with_aliases(self) -> None:
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery(agent="myproj-best-practices")),
            last_assistant_message="All committed, suite green, nothing to report.",
            aliases={"myproj-best-practices": "best-practices"},
        )
        self.assertTrue(block)

    DISMISSALS = (
        "Spawned rev-code and other: 0 findings, round clean.",
        "rev-code reported nothing. All clean, committing.",
        "See /tmp/rev-code.log for details. Round clean.",
        "3 spawned, 0 reported.",
        "The agents were silent.",
    )

    def test_a_dismissal_blocks_even_when_it_names_the_agent(self) -> None:
        """A name check PASSED every one of these — the exact sentence the ticket exists to stop."""
        path = self.transcript(self.owner(), self.delivery(agent="rev-code"))
        for message in self.DISMISSALS:
            with self.subTest(message=message):
                block, _reason = rg.decide_stop(
                    transcript_path=path, last_assistant_message=message,
                )
                self.assertTrue(block, message)

    def test_an_unrelated_clean_claim_is_not_a_dismissal(self) -> None:
        """Anti-over-block: "suite clean" must not read as dismissing the review round."""
        block, _reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery(agent="rev-code")),
            last_assistant_message="suite clean, and rev-code raised 3 criticals which I fixed.",
        )
        self.assertFalse(block)

    SYNTHETIC_ENTRIES = (
        "<command-name>/ticket-pause</command-name>",
        "<local-command-stdout>ok</local-command-stdout>",
        "<system-reminder>note</system-reminder>",
        "<task-notification><task-id>x</task-id></task-notification>",
        "Caveat: The messages below were generated by the user while running local commands.",
        "[Request interrupted by user]",
    )

    def test_a_synthetic_entry_does_not_reset_the_turn(self) -> None:
        """170 of 460 matches in the source corpus were synthetic. A slash command — which the
        workflow mandates — pushed a delivered report out of "this turn" and the gate went silent."""
        for text in self.SYNTHETIC_ENTRIES:
            with self.subTest(text=text[:30]):
                path = self.transcript(self.owner(), self.delivery(), self.owner(text))
                block, _reason = rg.decide_stop(
                    transcript_path=path, last_assistant_message="0 reported.",
                )
                self.assertTrue(block, text)

    def test_a_real_owner_prompt_still_resets_the_turn(self) -> None:
        path = self.transcript(self.owner(), self.delivery(), self.owner("now do the next thing"))
        block, _reason = rg.decide_stop(transcript_path=path, last_assistant_message="0 reported.")
        self.assertFalse(block)

    def test_the_stop_gate_honours_an_override(self) -> None:
        """The commit gate had 2 override tests; the stop gate had 0, and the sweep found the branch."""
        os.environ[rg.OVERRIDE_ENV] = "reviewer crashed"
        self.addCleanup(os.environ.pop, rg.OVERRIDE_ENV, None)
        block, reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery(agent="rev-code")),
            last_assistant_message="0 reported.",
        )
        self.assertFalse(block)
        self.assertTrue(reason.startswith("OVERRIDDEN: "))

    def test_the_block_message_does_not_name_the_agents(self) -> None:
        """Naming them let a retry satisfy the gate by echoing the block text back at it."""
        block, reason = rg.decide_stop(
            transcript_path=self.transcript(self.owner(), self.delivery(agent="rev-code")),
            last_assistant_message="Committed everything and pushed. Moving on.",
        )
        self.assertTrue(block)
        self.assertNotIn("rev-code", reason)

    def test_missing_transcript_does_not_block(self) -> None:
        block, _reason = rg.decide_stop(
            transcript_path=self.dir / "gone.jsonl", last_assistant_message="x",
        )
        self.assertFalse(block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
