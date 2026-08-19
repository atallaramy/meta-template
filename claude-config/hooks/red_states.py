#!/usr/bin/env python3
"""Prove every guard in review_gate.py has a reachable red state.

Hand-written flips (for what a mutation tool cannot express — a whole guard removed) carry two
load-bearing VALIDITY checks, because a bad mutation is worse than no mutation:

  1. the anchor must occur EXACTLY once — `replace(.., 1)` on an ambiguous anchor patches the wrong
     code and the test correctly stays green, which then reads as "the test is fake";
  2. a mutation must not ADD control flow — inserting a branch proves the test detects a shape
     production does not have.

Each entry names the test that MUST go red. A mutation whose test stays green is a hole, not a pass.

    python claude-config/hooks/red_states.py            # the named flips
    python claude-config/hooks/red_states.py --sweep    # mechanical mutant sweep
    python claude-config/hooks/red_states.py --triage   # survivors bucketed by direction
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path

META = Path(__file__).resolve().parent.parent.parent  # the meta repo root
TARGET = META / "claude-config" / "hooks" / "review_gate.py"
SUITE = META / "claude-config" / "hooks" / "review_gate_test.py"

_BRANCH_TOKENS = ("if ", "elif ", "else:", "for ", "while ", "try:", "except", "and ", "or ")


@dataclass(frozen=True)
class Flip:
    label: str
    old: str
    new: str
    must_red: str


FLIPS = (
    Flip(
        "merge dropped from the commit-producing set",
        '"commit", "commit-tree", "merge", "cherry-pick"',
        '"commit", "commit-tree", "cherry-pick"',
        "CommitDetection.test_commit_producing_detected",
    ),
    Flip(
        "newline no longer separates commands (the 77-lost-commits bug)",
        "mark_line_breaks(strip_heredocs(command))",
        "strip_heredocs(command)",
        "CommitDetection.test_multiline_block",
    ),
    Flip(
        "heredoc bodies read as shell (the prose false-positive bug)",
        "mark_line_breaks(strip_heredocs(command))",
        "mark_line_breaks(command)",
        "CommitDetection.test_heredoc_body_is_data",
    ),
    Flip(
        "git no longer has to be at a command position",
        'if at_command_position and name == "git":',
        'if name == "git":',
        "CommitDetection.test_non_commit_not_detected",
    ),
    Flip(
        "anything without an idle marker treated as idle",
        "if not marked:\n        return False",
        "if not marked:\n        return True",
        "PendingDetection.test_report_blocks_and_is_described",
    ),
    Flip(
        "idle marker beside a summary waves the report through",
        'return not any(str(node.get("summary") or "").strip() for node in nodes)',
        "return True",
        "PendingDetection.test_a_summary_outside_a_clean_idle_payload_still_blocks",
    ),
    Flip(
        "an unreadable inbox stops being undeterminable (§Step 0d)",
        'return [], f"lead inbox unreadable ({exc}) — cannot determine", True',
        'return [], f"lead inbox unreadable ({exc}) — cannot determine", False',
        "PendingDetection.test_invalid_json_blocks",
    ),
    Flip(
        "a non-list inbox stops being undeterminable",
        'expected list — cannot determine", True',
        'expected list — cannot determine", False',
        "PendingDetection.test_non_list_json_blocks",
    ),
    Flip(
        "transparent wrappers hide a commit again (env/sudo/nohup/time)",
        'if _ENV_ASSIGNMENT.match(token) or token.rsplit("/", 1)[-1] in _WRAPPERS:',
        "if _ENV_ASSIGNMENT.match(token):",
        "CommitDetection.test_transparent_wrappers_do_not_hide_a_commit",
    ),
    Flip(
        "a report wearing an idle badge is treated as idle again",
        "if any(set(node) - _IDLE_KEYS for node in marked):\n        return False",
        "if False:\n        return False",
        "PendingDetection.test_idle_marker_with_an_unexpected_key_still_blocks",
    ),
    Flip(
        "the inline override is no longer read from the command",
        "inline = _INLINE_OVERRIDE.search(command)",
        'inline = _INLINE_OVERRIDE.search("")',
        "CommitGate.test_inline_override_in_the_command_works",
    ),
    Flip(
        "the transcript byte budget is removed",
        "            budget -= len(line)\n            if budget <= 0:\n                break",
        "            budget -= len(line)",
        "StopGate.test_the_byte_budget_stops_an_endless_file",
    ),
    Flip(
        "a pathspec in another repo stops widening the gated set",
        '            if "/" in token:',
        "            if False:",
        "CommitDetection.test_pathspec_naming_another_repo_is_gated",
    ),
    Flip(
        "a teammate session no longer resolves its lead team (the committer bypass)",
        '            member.get("agentId") == agent_id for member in data.get("members") or []',
        '            False for member in data.get("members") or []',
        "PendingDetection.test_a_teammate_session_still_resolves_the_lead_team",
    ),
    Flip(
        "the lead inbox name is hardcoded again instead of read from config",
        'if member.get("agentType") == "team-lead" and member.get("name"):',
        'if member.get("agentType") == "team-lead" and member.get("nickname"):',
        "PendingDetection.test_the_lead_inbox_name_comes_from_config",
    ),
    Flip(
        "an unreadable team config stops being undeterminable",
        'return None, f"{config} unreadable ({exc}) — cannot name the lead\'s inbox"',
        'return team_dir / "inboxes" / "team-lead.json", ""',
        "PendingDetection.test_an_unreadable_config_is_undeterminable",
    ),
    Flip(
        "the stop block message names the agents again (self-satisfying guard)",
        'f"review-gate: BLOCKED — {len(delivered)} teammate report(s) from {count} agent(s) landed"',
        'f"review-gate: BLOCKED — {delivered} landed"',
        "StopGate.test_the_block_message_does_not_name_the_agents",
    ),
    Flip(
        "the gh window narrows, so a SHORT `gh pr merge` is missed (the one fail-open of 55)",
        "    words = [t for t in tokens[start : start + 4] if not t.startswith(\"-\")]",
        "    words = [t for t in tokens[start : start - 4] if not t.startswith(\"-\")]",
        "CommitDetection.test_a_short_gh_pr_merge_is_detected",
    ),
    Flip(
        "nested shells stop being analysed (bash -c / eval bypass)",
        "if at_command_position and name in _NESTED_SHELLS:",
        "if False:",
        "CommitDetection.test_nested_shells_and_gh_merge_are_detected",
    ),
    Flip(
        "a nested shell is blanket-blocked instead of analysed (over-block)",
        "                    found.extend(commit_ops(nested))",
        '                    found.append(("x", ()))',
        "CommitDetection.test_a_nested_shell_without_a_commit_is_not_blocked",
    ),
    Flip(
        "the backslash continuation is left in, so the next command is invisible again",
        "        text = stripped[:-1] if ends_with_continuation else line",
        "        text = line",
        "CommitDetection.test_a_backslash_continuation_is_detected",
    ),
    Flip(
        "an unterminated heredoc silently truncates the command again",
        '            raise ValueError(f"unterminated heredoc <<{match.group(2)} — command cannot be parsed")',
        "            pass",
        "CommitDetection.test_an_unterminated_heredoc_is_unparseable_not_truncated",
    ),
    Flip(
        "the innermost path component wins again, so node_modules/**/meta is ungated",
        "    return next((p for p in Path(path).parts if p in KNOWN_REPOS), None)",
        "    return next((p for p in reversed(Path(path).parts) if p in KNOWN_REPOS), None)",
        "CommitDetection.test_the_repo_root_wins_over_an_inner_component",
    ),
    Flip(
        "the dismissal check is removed, so a name check passes the sentence again",
        "    if dismissed:",
        "    if False:",
        "StopGate.test_a_dismissal_blocks_even_when_it_names_the_agent",
    ),
    Flip(
        "the turn boundary trusts a synthetic entry again (slash command blinds the gate)",
        "    return not any(marker in text for text in texts for marker in _SYNTHETIC)",
        "    return True",
        "StopGate.test_a_synthetic_entry_does_not_reset_the_turn",
    ),
    Flip(
        "a real owner prompt stops resetting the turn (over-block)",
        '    if entry.get("type") != "user":',
        "    if True:",
        "StopGate.test_a_real_owner_prompt_still_resets_the_turn",
    ),
    Flip(
        "meta's own code is ungated again",
        "        if not code:",
        "        if True:",
        "CommitGate.test_meta_commit_staging_code_is_gated",
    ),
    Flip(
        "an unreadable staged set is treated as docs-only",
        "        if code is None:",
        "        if False:",
        "CommitGate.test_meta_commit_with_an_unreadable_staged_set_is_gated",
    ),
    Flip(
        "an unrecognised session id treated as clear instead of undeterminable",
        "if not _SESSION_ID.match(session_id):",
        "if False:",
        "PendingDetection.test_unrecognised_session_id_is_undeterminable_not_clear",
    ),
    Flip(
        "an unresolvable repo treated as ungated",
        'UNGATED_REPOS = frozenset({"meta"})',
        'UNGATED_REPOS = frozenset({"meta", None})',
        "CommitGate.test_unresolvable_repo_is_gated",
    ),
    Flip(
        "a whitespace-only override counts as an override",
        'return (os.environ.get(OVERRIDE_ENV) or "").strip() or None',
        'return (os.environ.get(OVERRIDE_ENV) or "") or None',
        "CommitGate.test_blank_override_does_not_count",
    ),
    Flip(
        "the agent-type alias is dropped, so substance-acknowledgement is refused again",
        "accepted = names | {(aliases or {}).get(name, \"\") for name in names} - {\"\"}",
        "accepted = names",
        "StopGate.test_an_agent_type_also_counts_as_acknowledgement",
    ),
    Flip(
        "the stop gate's name check made vacuous",
        "if any(token and token in last_assistant_message for token in accepted):",
        "if delivered:",
        "StopGate.test_blocks_a_summary_ignoring_a_delivered_report",
    ),
    Flip(
        "the stop gate stops scoping to the current turn",
        "            if _is_owner_prompt(entry):\n                entries = []",
        "            if False:\n                entries = []",
        "StopGate.test_only_looks_at_the_current_turn",
    ),
    Flip(
        "the stop gate stops filtering idle notifications",
        'if agent == "team-lead" or \'"type":"idle_notification"\' in body.replace(" ", ""):',
        'if agent == "team-lead" or \'"type":"NEVER_MATCHES"\' in body.replace(" ", ""):',
        "StopGate.test_ignores_an_idle_notification",
    ),
)


def _validate(flip: Flip, source: str) -> list[str]:
    problems: list[str] = []
    count = source.count(flip.old)
    if count == 0:
        problems.append("anchor not found — the mutation would silently do nothing")
    elif count > 1:
        problems.append(f"anchor is AMBIGUOUS ({count} occurrences) — it would patch the wrong one")
    added = [t for t in _BRANCH_TOKENS if flip.new.count(t) > flip.old.count(t)]
    if added:
        problems.append(f"mutation ADDS control flow ({', '.join(t.strip() for t in added)})")
    return problems


_RAN_ONE = re.compile(r"^Ran (\d+) test", re.MULTILINE)


def _probe(suite: Path, node: str) -> None:
    """Refuse a node that does not resolve, BEFORE any mutation.

    unittest reports `Ran 1 test ... FAILED (errors=1)` for a typo'd method AND for a missing class, so
    the old `"Ran 0 tests" in stderr` check was DEAD CODE and a misspelled node scored "green -> RED".
    Verified in the source project: a nonexistent test method scored as evidence.
    """
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(suite), node],
        cwd=META, capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        raise SystemExit(
            f"node does not resolve or is already red BEFORE mutation: {node}\n"
            f"{result.stderr.strip()[-400:]}",
        )


def _run(suite: Path, node: str) -> bool:
    """True when the named test PASSED.

    `PYTHONDONTWRITEBYTECODE` is not optional. CPython invalidates a `.pyc` on (mtime, size), and two
    consecutive mutations that both add one character produce the SAME size inside the same mtime
    second — so the second run silently executed the FIRST mutation's bytecode and its test passed.
    That reported a real guard as a survivor. Found while chasing exactly that.
    """
    argv = [sys.executable, str(suite)] + ([node] if node else [])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        result = subprocess.run(  # noqa: S603
            argv, cwd=META, capture_output=True, text=True, check=False, env=env, timeout=120,
        )
    except subprocess.TimeoutExpired:
        # A mutant that hangs the suite is killed, not waited on — otherwise one bad mutation stalls
        # the whole sweep.
        return False
    if node:
        # A mutation is only evidence if the named test RAN and then failed. An error (bad node, import
        # break, SyntaxError from the mutation) also exits non-zero and would otherwise be scored red.
        ran = _RAN_ONE.search(result.stderr)
        if not ran or int(ran.group(1)) < 1:
            raise SystemExit(f"no test ran for {node} — cannot be evidence\n{result.stderr[-400:]}")
        if "errors=" in result.stderr and "failures=" not in result.stderr:
            raise SystemExit(
                f"{node} ERRORED rather than failed — that is not a reachable red state\n"
                f"{result.stderr[-400:]}",
            )
    return result.returncode == 0


# --- generic sweep -----------------------------------------------------------------------------
# House rule: "generate the breakages with a tool and act on the survivors; do not hand-pick the
# mutations." meta has no third-party deps by policy, so this is the stdlib equivalent: mechanical
# operators applied one at a time, via `tokenize` so a string literal or comment is never mutated.
# The hand-written FLIPS above stay for what an operator cannot express (a whole guard removed).

_OPERATOR_SWAPS = {
    "==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<",
    "+": "-", "and": "or", "or": "and", "in": "not in", "True": "False", "False": "True",
    "continue": "pass", "break": "pass",
}


def _mutants(source: str) -> list[tuple[int, str, str, str]]:
    """(lineno, before, after, mutated_source) for every mechanical mutation, strings/comments excluded."""
    import io
    import tokenize

    out: list[tuple[int, str, str, str]] = []
    lines = source.splitlines(keepends=True)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return out
    for tok in toks:
        if tok.type not in (tokenize.OP, tokenize.NAME):
            continue
        replacement = _OPERATOR_SWAPS.get(tok.string)
        if replacement is None:
            continue
        row, start, end = tok.start[0], tok.start[1], tok.end[1]
        mutated = list(lines)
        line = mutated[row - 1]
        mutated[row - 1] = line[:start] + replacement + line[end:]
        out.append((row, tok.string, replacement, "".join(mutated)))
    return out


def sweep() -> int:
    original = TARGET.read_text()
    sandbox = Path(tempfile.mkdtemp(prefix="review-gate-sweep-"))
    shutil.copytree(TARGET.parent, sandbox / "hooks")
    target, suite = sandbox / "hooks" / TARGET.name, sandbox / "hooks" / SUITE.name
    mutants = _mutants(original)
    print(f"generic sweep: {len(mutants)} mechanical mutants over {TARGET.name}\n")
    survivors: list[tuple[int, str, str]] = []
    try:
        for lineno, before, after, mutated in mutants:
            target.write_text(mutated)
            shutil.rmtree(sandbox / "hooks" / "__pycache__", ignore_errors=True)
            if _run(suite, ""):
                survivors.append((lineno, before, after))
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    killed = len(mutants) - len(survivors)
    print(f"killed {killed} of {len(mutants)}; {len(survivors)} SURVIVED\n")
    for lineno, before, after in survivors:
        text = original.splitlines()[lineno - 1].strip()
        print(f"  L{lineno:<4} {before!r} -> {after!r}   {text[:88]}")
    return 1 if survivors else 0


# --- triage --------------------------------------------------------------------------------------
# A surviving mutant is not automatically a hole. What matters is its DIRECTION: a mutation that makes
# the gate BLOCK something it should allow is noise; one that makes it ALLOW something it should block
# is the defect this whole ticket exists to remove. These scenarios are the gate's contract, run
# in-process against each mutated module, and compared to the unmutated baseline.

_SCENARIOS = """
import json, os, tempfile
from pathlib import Path

def build(mod, inbox, command, cwd, session="abcdef1234567890", agent=""):
    td = tempfile.mkdtemp()
    teams = Path(td) / "teams"
    tdir = teams / "session-abcdef12"
    (tdir / "inboxes").mkdir(parents=True)
    (tdir / "config.json").write_text(json.dumps({
        "leadSessionId": "abcdef1234567890",
        "members": [{"agentId": "team-lead@session-abcdef12", "name": "team-lead",
                     "agentType": "team-lead"},
                    {"agentId": "rev-code@session-abcdef12", "name": "rev-code",
                     "agentType": "pr-review-toolkit:code-reviewer"}]}))
    (tdir / "inboxes" / "team-lead.json").write_text(inbox)
    return mod.decide_commit(command=command, cwd=cwd, session_id=session,
                             agent_id=agent, teams_root=teams)[0]

def transcript(delivered=True, extra=None):
    td = tempfile.mkdtemp()
    p = Path(td) / "t.jsonl"
    rows = [{"type": "user", "userType": "external", "message": {"content": "go"}}]
    if delivered:
        rows.append({"type": "user", "message": {"content":
            '<teammate-message teammate_id="rev-code" summary="3 critical">b</teammate-message>'}})
    if extra:
        rows.append({"type": "user", "userType": "external", "message": {"content": extra}})
    p.write_text("".join(json.dumps(r) + chr(10) for r in rows))
    return p

PENDING = json.dumps([{"from": "rev-code", "summary": "3 critical"}])

def results(mod):
    out = {}
    out["pending+commit->BLOCK"] = build(mod, PENDING, "git commit -m x", "/repo/backend")
    out["drained+commit->allow"] = build(mod, "[]", "git commit -m x", "/repo/backend")
    out["pending+nested->BLOCK"] = build(mod, PENDING, 'bash -c "git commit -m x"', "/repo/backend")
    out["pending+ghmerge->BLOCK"] = build(mod, PENDING, "gh pr merge 1 --merge", "/repo/backend")
    out["pending+wrapper->BLOCK"] = build(mod, PENDING, "sudo git commit -m x", "/repo/backend")
    out["pending+contin->BLOCK"] = build(mod, PENDING, "git add x && \\\n git commit -m y", "/repo/backend")
    out["pending+noncommit->allow"] = build(mod, PENDING, "git status", "/repo/backend")
    out["pending+prose->allow"] = build(mod, PENDING, 'echo "the reorder commit?"', "/repo/backend")
    out["corrupt+commit->BLOCK"] = build(mod, "{bad", "git commit -m x", "/repo/backend")
    out["badsession+commit->BLOCK"] = build(mod, PENDING, "git commit -m x", "/repo/backend", session="../..")
    out["teammate+commit->BLOCK"] = build(mod, PENDING, "git commit -m x", "/repo/backend",
                                          session="ffffffffeeee", agent="rev-code@session-abcdef12")
    out["idleonly+commit->allow"] = build(
        mod, json.dumps([{"type": "idle_notification", "from": "r", "timestamp": "t",
                          "idleReason": "available"}]), "git commit -m x", "/repo/backend")
    out["stop dismissal->BLOCK"] = mod.decide_stop(
        transcript_path=transcript(), last_assistant_message="0 reported, round clean.")[0]
    out["stop ack->allow"] = mod.decide_stop(
        transcript_path=transcript(), last_assistant_message="rev-code found 3 criticals; fixed.")[0]
    out["stop nothing->allow"] = mod.decide_stop(
        transcript_path=transcript(delivered=False), last_assistant_message="0 reported.")[0]
    out["stop slashcmd->BLOCK"] = mod.decide_stop(
        transcript_path=transcript(extra="<command-name>/ticket-pause</command-name>"),
        last_assistant_message="0 reported.")[0]
    return out
"""


def _load(source: str, name: str):
    import importlib.util

    path = Path(tempfile.mkdtemp()) / f"{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def triage() -> int:
    import collections

    original = TARGET.read_text()
    scen: dict = {}
    exec(_SCENARIOS, scen)  # noqa: S102 — literal above, no external input
    for key in ("REVIEW_GATE_OVERRIDE", "REVIEW_GATE_TEAMS_ROOT"):
        os.environ.pop(key, None)

    baseline = scen["results"](_load(original, "rg_base"))
    expected = {name: name.endswith("BLOCK") for name in baseline}
    wrong = [n for n, v in baseline.items() if v != expected[n]]
    if wrong:
        print(f"BASELINE DISAGREES WITH THE CONTRACT on {wrong} — fix that first")
        return 1
    print(f"baseline honours all {len(baseline)} contract scenarios.\n")

    sandbox = Path(tempfile.mkdtemp(prefix="review-gate-triage-"))
    shutil.copytree(TARGET.parent, sandbox / "hooks")
    target, suite = sandbox / "hooks" / TARGET.name, sandbox / "hooks" / SUITE.name

    buckets: dict[str, list[str]] = collections.defaultdict(list)
    try:
        for lineno, before, after, mutated in _mutants(original):
            target.write_text(mutated)
            shutil.rmtree(sandbox / "hooks" / "__pycache__", ignore_errors=True)
            if not _run(suite, ""):
                continue  # killed by the suite; not a survivor
            label = f"L{lineno} {before!r}->{after!r}  {original.splitlines()[lineno-1].strip()[:60]}"
            try:
                got = scen["results"](_load(mutated, f"rg_m{lineno}_{abs(hash(after))}"))
            except Exception as exc:  # noqa: BLE001
                buckets["CRASHES (fails closed via main's guard)"].append(f"{label}  [{type(exc).__name__}]")
                continue
            opened = [n for n in baseline if expected[n] and baseline[n] and not got[n]]
            closed = [n for n in baseline if not expected[n] and not baseline[n] and got[n]]
            if opened:
                buckets["FAIL-OPEN — allows what it must block"].append(f"{label}\n{opened}")
            elif closed:
                buckets["fail-closed — blocks what it should allow (noise)"].append(f"{label}\n{closed}")
            else:
                buckets["equivalent — no contract scenario changes"].append(label)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    total = sum(len(v) for v in buckets.values())
    print(f"{total} surviving mutants, triaged by DIRECTION:\n")
    for name in ("FAIL-OPEN — allows what it must block",
                 "fail-closed — blocks what it should allow (noise)",
                 "CRASHES (fails closed via main's guard)",
                 "equivalent — no contract scenario changes"):
        rows = buckets.get(name, [])
        print(f"  {len(rows):3d}  {name}")
    for name in ("FAIL-OPEN — allows what it must block",
                 "fail-closed — blocks what it should allow (noise)"):
        rows = buckets.get(name, [])
        if rows:
            print(f"\n=== {name} ===")
            for row in rows:
                print(f"  {row}")
    return 1 if buckets.get("FAIL-OPEN — allows what it must block") else 0


def main() -> int:
    if "--triage" in sys.argv:
        return triage()
    if "--sweep" in sys.argv:
        return sweep()
    original = TARGET.read_text()
    # `.claude/settings.json` executes TARGET on every Bash call. Mutating it in place meant a
    # crash between write and restore left the production gate mutated — flip #7 leaves "an unreadable
    # inbox is not undeterminable", i.e. fail-open, on disk, silently. Work on a copy instead.
    sandbox = Path(tempfile.mkdtemp(prefix="review-gate-red-states-"))
    shutil.copytree(TARGET.parent, sandbox / "hooks")
    target = sandbox / "hooks" / TARGET.name
    suite = sandbox / "hooks" / SUITE.name
    invalid: list[str] = []
    for flip in FLIPS:
        problems = _validate(flip, original)
        if problems:
            invalid.append(f"{flip.label}: {'; '.join(problems)}")
    if invalid:
        print("REFUSED — these mutations cannot be evidence:")
        for line in invalid:
            print(f"  ✗ {line}")
        return 1

    shutil.rmtree(sandbox / "hooks" / "__pycache__", ignore_errors=True)
    if not _run(suite, ""):
        print("the suite is RED before any mutation — fix that first")
        return 1
    for flip in FLIPS:
        _probe(suite, flip.must_red)
    print(f"all {len(FLIPS)} named tests resolve and pass before mutation.")
    print(f"baseline green. {len(FLIPS)} mutations to apply.\n")

    survivors: list[Flip] = []
    try:
        for flip in FLIPS:
            target.write_text(original.replace(flip.old, flip.new, 1))
            passed = _run(suite, flip.must_red)
            status = "SURVIVED" if passed else "green -> RED"
            print(f"  {'✗' if passed else '·'} {status:12s} {flip.label}  [{flip.must_red}]")
            if passed:
                survivors.append(flip)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVOR(S) — each is an unguarded claim:")
        for flip in survivors:
            print(f"  ✗ {flip.label} did not red {flip.must_red}")
        return 1
    print(f"all {len(FLIPS)} mutations red at their named test (sandboxed copy; live hook untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
