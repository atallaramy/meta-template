#!/usr/bin/env python3
"""Review gate — stop a commit landing while a teammate's findings sit undelivered.

Measured cause (in a source project's transcript corpus): a named subagent becomes a mailbox
*teammate*, and its report is injected into the lead's context only when the lead's turn ENDS
(66 of 68 deliveries observed). A commit is a Bash call inside that turn, so no in-turn instruction
can wait for the report — 68 of 89 arrived after the commit.

Two gates, two harms:
  * `--mode pretooluse` — refuse a commit-producing git command while the lead's inbox holds an
    undelivered report, and say to end the turn. The block IS what creates the turn boundary that
    delivers it.
  * `--mode stop` — refuse a closing message that ignores reports which landed in this turn. It must
    NOT block merely on an open round: delivery is what the turn boundary does, so that deadlocks.

Stdlib only, to match `scripts/`' zero-dependency policy. Exit 2 blocks; exit 0 allows.

**The COMMIT gate fails closed**: an unreadable inbox, an unparseable command, an unreadable staged set
or an exception inside the gate all block and say so. **The STOP gate does not, and the claim that it
did was once wrong** — a missing or unparseable transcript, or a transcript whose lines all fail to
parse, yields "nothing was delivered" and allows. That is deliberate (blocking there deadlocks:
delivery is what the turn boundary does) but it means the stop gate is a best-effort claim check, not a
guarantee.

KNOWN LIMITATION (upstream, unfixed at port time): the stop gate keeps no record of an already-
acknowledged report, so in a long autonomous stretch every later close must re-name a reporting
agent or be re-blocked; and cross-session peer messages are invisible to it. Fix upstream first
or accept occasional false blocks. The deliver-mode gate and dismissal branch are sound.

RESIDUAL KNOWN GAPS (documented, not hidden): `_repo_of` picks the OUTERMOST path component named
in KNOWN_REPOS, not the actual git toplevel — an ancestor directory that happens to carry one of
those names mis-attributes every commit under it (a real fix needs `git rev-parse --show-toplevel`
per call, with the latency that implies); and a nested shell invoked with a value-taking option but
WITHOUT `-c` (`bash -o errexit script.sh`) analyses the option value instead of the script. Both
fail toward analysis of the wrong token; neither has been observed to fail open on a real commit
form, unlike the six classes fixed above.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

OVERRIDE_ENV = "REVIEW_GATE_OVERRIDE"


def _override_log() -> Path:
    """Env-overridable so `main()` is testable — it was once hardcoded to the operator's real home,
    which left `main()` with zero tests and the "an internal exception must block" claim unproven."""
    return Path(
        os.environ.get("REVIEW_GATE_LOG") or (Path.home() / ".claude" / "review-gate-overrides.log"),
    )

# Over-inclusive on purpose: `cherry-pick -n` / `revert --no-commit` / `merge --squash` are NOT
# excused, because over-blocking costs a re-run and under-blocking costs an unreviewed commit.
COMMIT_SUBCOMMANDS = frozenset(
    {"commit", "commit-tree", "merge", "cherry-pick", "revert", "rebase", "am", "pull"},
)
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
_OPERATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", "{", "}"})
# Transparent wrappers: the NEXT word is still a command. Without this, `env FOO=1 git commit`,
# `sudo git commit`, `nohup git commit` and `time git commit` all walked straight through the gate.
_WRAPPERS = frozenset(
    {"env", "sudo", "nohup", "time", "command", "exec", "nice", "stdbuf", "doas", "xargs",
     "caffeinate", "watch", "timeout", "flock", "setsid", "ionice"},
)
# Shell KEYWORDS: the next word after these is still a command. Without them,
# `do` and `then` CLEARED the command position, so `for r in a b; do git commit
# -m x; done` and `if [ -n x ]; then git commit -m x; fi` both walked through
# the gate (reproduced in review, with controls).
_KEYWORDS = frozenset(
    {"if", "then", "elif", "else", "fi", "for", "while", "until", "do", "done",
     "in", "case", "esac", "!"},
)
# `bash -c "git commit …"` hid the commit inside a quoted string, which the tokeniser cannot see. The
# string is analysed RECURSIVELY rather than blanket-blocked, because `bash -lc` is used constantly for
# things that are not commits and gating all of them would be pure override fatigue.
_NESTED_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "eval"})
# `gh pr merge` creates a merge commit. Many projects name it as THE merge procedure; the source
# corpus held 19 real invocations, and the first version matched none of them.
_GH_COMMIT_VERBS = frozenset({"merge"})
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Session ids are uuid-shaped. Anything else is undeterminable, not clear (see pending_reports).
_SESSION_ID = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,}$")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# TUNE PER PROJECT. `meta` is tickets and docs; reviewers are briefed on code diffs. In the source
# corpus, 76 of 257 broad-gate blocks were meta-only — override fatigue, no safety gained.
# KNOWN_REPOS: the repo directory names commits can land in (used to resolve which repo a command
# targets); UNGATED_REPOS: the subset whose docs-only commits skip the gate.
UNGATED_REPOS = frozenset({"meta"})
KNOWN_REPOS = ("backend", "frontend", "infra", "meta")

_TEAMMATE_TAG = re.compile(
    r'<teammate-message teammate_id="([^"]+)"([^>]*)>(.*?)</teammate-message>', re.DOTALL,
)
_SUMMARY_ATTR = re.compile(r'summary="([^"]*)"')

# The harm is "the owner was told the round produced nothing". The natural way to write that sentence
# NAMES the agents — so a name check passes precisely the message it exists to refuse (verified:
# "Spawned rev-code and rev-silent: 0 findings, round clean." was ALLOWED). These
# match the dismissal itself, which naming cannot satisfy. Deliberately review-specific: "suite clean"
# and "tests pass" must not trip it.
_DISMISSALS = (
    "0 reported", "zero reported", "none reported", "no findings", "0 findings", "nothing to report",
    "reported nothing", "produced nothing", "round clean", "round was clean", "were silent",
    "stayed silent", "was silent", "no issues found", "nothing new", "no new findings",
)


# --- is this command going to create a commit? ------------------------------------------------
# Tokenised, not substring-matched. A regex version failed both ways: 7 commit-producing
# subcommands read as safe, and 4 of 432 corpus positives were prose (`echo "... reorder commit?"`).


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies — they are data, and our own commit messages contain "git commit"."""
    lines = command.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        out.append(lines[index])
        match = _HEREDOC.search(lines[index])
        index += 1
        if not match:
            continue
        found_terminator = False
        while index < len(lines):
            if lines[index].strip() == match.group(2):
                found_terminator = True
                break
            index += 1
        if not found_terminator:
            # No terminator: the rest of the command was being dropped, silently, in the direction the
            # module comment calls the expensive one. Say so instead.
            raise ValueError(f"unterminated heredoc <<{match.group(2)} — command cannot be parsed")
        index += 1
    return "\n".join(out)


def mark_line_breaks(command: str) -> str:
    """A newline starts a new command; a backslash-newline does not.

    Two measured bugs live here. shlex counts a newline as whitespace, so ``cd x`` then ``git commit``
    on the next line tokenised flat and the ``git`` stopped looking like a command -- that lost
    **77 of 432** real commits. And a backslash continuation left the token ``\\ngit``, so
    ``git add x && \\`` + newline + ``git commit`` was invisible -- **3 of 3** real corpus cases missed.
    """
    logical: list[str] = []
    continuing = False
    for line in command.split("\n"):
        stripped = line.rstrip()
        ends_with_continuation = stripped.endswith("\\")
        text = stripped[:-1] if ends_with_continuation else line
        if continuing and logical:
            logical[-1] = f"{logical[-1]} {text.lstrip()}"
        else:
            logical.append(text)
        continuing = ends_with_continuation
    return "\n;\n".join(logical)


def _tokenise(command: str) -> list[str]:
    lexer = shlex.shlex(mark_line_breaks(strip_heredocs(command)), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    # No comment handling: shlex's default `#` swallows to end-of-logical-line
    # AFTER backslash-joining, so `sed -i s#a#b# f && git commit -am x` lost the
    # commit entirely (reproduced in review). A stray `#` token can only
    # over-block, which this module's own header calls the cheap direction.
    lexer.commenters = ""
    return list(lexer)


def commit_ops(command: str) -> list[tuple[str, tuple[str, ...]]]:
    """(subcommand, tokens) for each commit-producing git invocation. Raises on unbalanced quotes."""
    tokens = _tokenise(command)
    found: list[tuple[str, tuple[str, ...]]] = []
    at_command_position = True
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _OPERATORS:
            at_command_position = True
            index += 1
            continue
        if at_command_position and token in _KEYWORDS:
            index += 1
            continue  # shell keyword — the next word is still a command
        if _ENV_ASSIGNMENT.match(token) or token.rsplit("/", 1)[-1] in _WRAPPERS:
            # A wrapper's arguments can include options WITH VALUES (`sudo -u
            # me git …`, `timeout 120 git …`). Rather than model every
            # wrapper's option table, scan this simple command for the first
            # token naming a shell/git/gh and resume there. Over-inclusive by
            # design: a bare `git` inside a wrapper's arguments re-enters
            # analysis, which can only over-block (the cheap direction).
            index += 1
            while index < len(tokens) and tokens[index] not in _OPERATORS:
                ahead = tokens[index].rsplit("/", 1)[-1]
                if (ahead in _NESTED_SHELLS or ahead in ("git", "gh")
                        or ahead in _WRAPPERS or _ENV_ASSIGNMENT.match(tokens[index])):
                    break
                index += 1
            at_command_position = True
            continue
        name = token.rsplit("/", 1)[-1]
        if at_command_position and name in _NESTED_SHELLS:
            for nested in _nested_commands(tokens, index + 1, shell=name):
                try:
                    found.extend(commit_ops(nested))
                except ValueError:
                    found.append(("<opaque-nested-shell>", (token, nested[:60])))
            index += 1
            at_command_position = False
            continue
        if at_command_position and name == "gh":
            if _gh_is_commit_producing(tokens, index + 1):
                found.append(("gh-pr-merge", tuple(tokens[index : index + 4])))
            index += 1
            at_command_position = False
            continue
        if at_command_position and name == "git":
            subcommand, end = _subcommand_after_git(tokens, index + 1)
            if subcommand in COMMIT_SUBCOMMANDS:
                found.append((subcommand, tuple(tokens[index:end])))
            index = end
            at_command_position = False
            continue
        at_command_position = False
        index += 1
    return found


def _nested_commands(tokens: list[str], start: int, shell: str = "") -> list[str]:
    """The command strings a nested shell would execute.

    `eval` concatenates ALL its arguments into one command, and the `-c` family
    takes the argument AFTER `-c` — `bash -o errexit -c "git commit"` puts an
    option VALUE (`errexit`) before the command string. The first version took
    the first non-option token and missed both (reproduced in review)."""
    words: list[str] = []
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token in _OPERATORS:
            break
        words.append(token)
    if not words:
        return []
    if shell == "eval":
        return [" ".join(words)]
    for position, word in enumerate(words):
        if word == "-c" and position + 1 < len(words):
            return [words[position + 1]]
    for word in words:
        if not word.startswith("-"):
            return [word]
    return []


def _gh_is_commit_producing(tokens: list[str], start: int) -> bool:
    words = [t for t in tokens[start : start + 4] if not t.startswith("-")]
    return len(words) >= 2 and words[0] == "pr" and words[1] in _GH_COMMIT_VERBS


def _subcommand_after_git(tokens: list[str], start: int) -> tuple[str | None, int]:
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token in _OPERATORS:
            return None, index
        if token.startswith("-"):
            index += 2 if token in _VALUE_OPTS else 1
            continue
        return token, index + 1
    return None, index


def resolve_repos(command: str, cwd: str) -> set[str | None]:
    """Which repos could this commit into? `None` = undeterminable, which is gated."""
    found: set[str | None] = set()
    for _subcommand, tokens in commit_ops(command):
        target = cwd
        for index, token in enumerate(tokens):
            if token == "-C" and index + 1 < len(tokens):
                target = tokens[index + 1]
        found.add(_repo_of(target))
    if found:
        # A path argument naming a different repo is gated too, so the `meta` carve-out cannot be used
        # as a doorway by listing a path in another repo. `commit_ops` returns tokens only up to the
        # subcommand, so the ARGUMENTS have to be re-scanned from the whole command here.
        for token in _tokenise(command):
            if "/" in token:
                named = _repo_of(token)
                if named is not None:
                    found.add(named)
    return found


def _repo_of(path: str) -> str | None:
    return next((p for p in Path(path).parts if p in KNOWN_REPOS), None)


# --- is a report sitting undelivered? ----------------------------------------------------------
# Documented mailbox: ~/.claude/teams/session-<first8>/inboxes/<agent>.json, and `SendMessage`
# success means "written to that file", not "read by the lead". Verified on disk: a JSON list,
# drained to [] on delivery. The ENTRY schema is unobserved, so classification is positive-proof
# only — anything unrecognised counts as a pending report.


def _nodes(value: object) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        found.append(value)
        for item in value.values():
            found.extend(_nodes(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_nodes(item))
    elif isinstance(value, str) and value.strip().startswith("{"):
        try:
            found.extend(_nodes(json.loads(value)))
        except ValueError:
            pass
    return found


# A real idle notification carries exactly these keys (observed in the delivered transcript form:
# {"type","from","timestamp","idleReason"}). An entry that carries the marker AND anything else may be
# a report wearing an idle badge, so it does NOT count as idle.
_IDLE_KEYS = frozenset({"type", "from", "sender", "teammate_id", "timestamp", "idleReason", "reason"})


def is_idle_notification(entry: object) -> bool:
    nodes = _nodes(entry)
    marked = [node for node in nodes if node.get("type") == "idle_notification"]
    if not marked:
        return False
    if any(set(node) - _IDLE_KEYS for node in marked):
        return False
    return not any(str(node.get("summary") or "").strip() for node in nodes)


def describe(entry: object) -> str:
    for node in _nodes(entry):
        summary = str(node.get("summary") or "").strip()
        if summary:
            sender = node.get("from") or node.get("teammate_id") or "?"
            return f"{sender}: {summary}"
    for node in _nodes(entry):
        sender = node.get("from") or node.get("teammate_id")
        if sender:
            return f"{sender}: (no summary)"
    return "(unrecognised inbox entry)"


def resolve_team(teams_root: Path, session_id: str, agent_id: str = "") -> tuple[Path | None, str]:
    """Which team's lead inbox governs this process? (dir, why).

    A TEAMMATE has its own session id and no team dir of its own, so keying the path on `session_id`
    alone made every teammate invisible to the gate — and a common commit path IS a `committer`
    teammate. `agent_id` is `<name>@session-<lead8>`, so it names the team directly; we
    also match `config.json.leadSessionId` so the lead resolves without it.
    """
    if _SESSION_ID.match(session_id):
        candidate = teams_root / f"session-{session_id[:8]}"
        if candidate.is_dir():
            return candidate, f"team {candidate.name} resolved from session_id"
    unreadable = 0
    for config in sorted(teams_root.glob("session-*/config.json")):
        try:
            data = json.loads(config.read_text())
        except (OSError, ValueError):
            unreadable += 1
            continue
        if data.get("leadSessionId") == session_id or any(
            member.get("agentId") == agent_id for member in data.get("members") or []
        ):
            return config.parent, f"team {config.parent.name} resolved from its config.json"
    if unreadable:
        # A corrupt config.json blocked the LEAD but silently ALLOWED a
        # teammate (the documented commit path): membership was unknowable,
        # yet the fall-through read as "no teammates were spawned" — a clear
        # verdict from unreadable evidence (reproduced in review).
        return None, f"{unreadable} team config.json file(s) unreadable — cannot determine membership"
    return None, "no team directory matches this session — no teammates were spawned"


def _lead_inbox(team_dir: Path) -> tuple[Path | None, str]:
    """The lead's mailbox file. Its NAME comes from config.json, which is the only thing that says so.

    The doc guarantees the lead's *agentType* is `team-lead`, not the filename. It happens to match
    today; if config.json cannot tell us, that is undeterminable, not clear.
    """
    config = team_dir / "config.json"
    try:
        data = json.loads(config.read_text())
    except (OSError, ValueError) as exc:
        return None, f"{config} unreadable ({exc}) — cannot name the lead's inbox"
    for member in data.get("members") or []:
        if member.get("agentType") == "team-lead" and member.get("name"):
            return team_dir / "inboxes" / f"{member['name']}.json", ""
    return None, f"{config} names no team-lead member — cannot name the lead's inbox"


def pending_reports(
    teams_root: Path, session_id: str, agent_id: str = "",
) -> tuple[list[str], str, bool]:
    """(pending descriptions, why, undeterminable). Blocks when pending or undeterminable."""
    team_dir, why = resolve_team(teams_root, session_id, agent_id)
    if team_dir is None:
        if not _SESSION_ID.match(session_id):
            # A `session_id` of "../.." used to build a path that did not exist, and "no inbox there"
            # read as "nothing pending". Fail-open, found in the manual security pass on this diff.
            return [], f"session id {session_id!r} is not a recognised id — cannot determine", True
        if "cannot determine" in why:
            return [], why, True
        return [], why, False

    inbox, problem = _lead_inbox(team_dir)
    if inbox is None:
        return [], f"{problem} — cannot determine", True
    if not inbox.exists():
        return [], f"no lead inbox at {inbox}", False
    try:
        entries = json.loads(inbox.read_text())
    except (OSError, ValueError) as exc:
        return [], f"lead inbox unreadable ({exc}) — cannot determine", True
    if not isinstance(entries, list):
        return [], f"lead inbox is {type(entries).__name__}, expected list — cannot determine", True
    pending = [describe(e) for e in entries if not is_idle_notification(e)]
    if pending:
        return pending, f"{len(pending)} undelivered teammate message(s)", False
    return [], f"{len(entries)} inbox entry/entries, all idle notifications", False


# --- what landed in this turn? -----------------------------------------------------------------


_TRANSCRIPT_BYTE_BUDGET = 64 * 1024 * 1024
_MAX_LINE_BYTES = 4 * 1024 * 1024


def _texts(entry: dict) -> list[str]:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


# Markers that make a `type:"user"` entry synthetic. Measured over the corpus: 170 of 460 entries the
# old denylist called "owner prompt" were not human — a slash command, a command's stdout, a
# system-reminder, a task-notification or an interrupt. Any of them reset the turn boundary and made the
# stop gate blind to a report delivered earlier in the same turn.
_SYNTHETIC = (
    "<teammate-message", "<task-notification>", "<system-reminder", "<local-command-stdout>",
    "<command-name>", "<command-message>", "<command-args>", "[Request interrupted",
    "Caveat: The messages below were generated", "Another Claude session sent a message",
)


def _is_owner_prompt(entry: dict) -> bool:
    """Allowlist, not denylist: it must LOOK like a human prompt to end the previous turn."""
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta"):
        return False
    if entry.get("userType") not in (None, "external"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    texts = _texts(entry)
    if not any(text.strip() for text in texts):
        return False
    return not any(marker in text for text in texts for marker in _SYNTHETIC)


def delivered_this_turn(path: Path, byte_budget: int | None = None) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    # Only the LAST `budget` BYTES are read: the current turn sits at the END
    # of a transcript that only grows. The first version consumed the budget
    # from the HEAD and stopped — so the moment a long-lived transcript
    # outgrew the budget, the stop gate silently and PERMANENTLY disabled
    # itself (reproduced in review). The bounded read() also keeps a
    # pathological file without newlines — /dev/zero — from being read forever.
    budget = _TRANSCRIPT_BYTE_BUDGET if byte_budget is None else byte_budget
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > budget:
                handle.seek(size - budget)
                handle.readline()  # drop the first, likely partial, line
            raw = handle.read(budget)
    except OSError:
        return []
    entries: list[dict] = []
    if raw:
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or len(line) > _MAX_LINE_BYTES:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if _is_owner_prompt(entry):
                entries = []
            entries.append(entry)

    found: list[tuple[str, str]] = []
    for entry in entries:
        for text in _texts(entry):
            for match in _TEAMMATE_TAG.finditer(text):
                agent, attrs, body = match.group(1), match.group(2), match.group(3)
                if agent == "team-lead" or '"type":"idle_notification"' in body.replace(" ", ""):
                    continue
                summary = _SUMMARY_ATTR.search(attrs)
                found.append((agent, summary.group(1) if summary else ""))
    return found


# --- the two decisions -------------------------------------------------------------------------


_INLINE_OVERRIDE = re.compile(rf"{OVERRIDE_ENV}=(?:'([^']*)'|\"([^\"]*)\"|(\S+))")


def _staged_code(cwd: str) -> list[str] | None:
    """Staged paths that are code, or None when the staged set cannot be read (→ block).

    `UNGATED_REPOS = {"meta"}` was justified as "tickets and docs", but the meta repo's own tooling —
    this gate and `scripts/build_index.py`, the validator that gates every commit — is Python living in
    that repo. The carve-out has to be decided per PATH, not per repo name.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", cwd, "diff", "--cached", "--name-only"],  # noqa: S607
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [
        line for line in result.stdout.splitlines()
        if line.strip() and (
            not line.endswith((".md", ".json", ".txt", ".lock"))
            # Settings and hooks are CODE whatever their extension — a commit
            # staging only `.claude/settings.json`, the file that WIRES this
            # gate, rode the docs carve-out (reproduced in review).
            or "/.claude/" in f"/{line}" or "/hooks/" in f"/{line}"
        )
    ]


def _override(command: str = "") -> str | None:
    """The env var OR an inline assignment in the command.

    The hook runs in Claude Code's process, so `REVIEW_GATE_OVERRIDE=x git commit` — which is what
    the block message tells the operator to type — puts the variable in the BASH command, never in the
    hook's environment. Reading only `os.environ` made the documented escape hatch impossible to use
    and turned a corrupted inbox into a dead end. Found by the second-model review of this diff.
    """
    inline = _INLINE_OVERRIDE.search(command)
    if inline:
        value = next((g for g in inline.groups() if g is not None), "").strip()
        if value:
            return value
    return (os.environ.get(OVERRIDE_ENV) or "").strip() or None


def agent_type_aliases(team_dir: Path | None) -> dict[str, str]:
    """name -> agentType, so a teammate can be acknowledged by either."""
    if team_dir is None:
        return {}
    try:
        data = json.loads((team_dir / "config.json").read_text())
    except (OSError, ValueError):
        return {}
    return {
        str(m.get("name")): str(m.get("agentType") or "")
        for m in data.get("members") or []
        if m.get("name")
    }


def decide_commit(
    *, command: str, cwd: str, session_id: str, teams_root: Path, agent_id: str = "",
) -> tuple[bool, str]:
    try:
        ops = commit_ops(command)
    except ValueError:
        pending, why, undetermined = pending_reports(teams_root, session_id, agent_id)
        if pending or undetermined:
            reason = _override(command)
            if reason:
                return False, f"OVERRIDDEN: {reason}"
            return True, f"review-gate: BLOCKED — command unparseable and a report is pending. {why}"
        return False, "unparseable command, no pending report"
    if not ops:
        return False, "not a commit-producing git command"

    pending, why, undetermined = pending_reports(teams_root, session_id, agent_id)
    if not (pending or undetermined):
        return False, why

    repos = resolve_repos(command, cwd)
    # The staged set must come from the repo the commit TARGETS: `git -C
    # <elsewhere> commit` resolved its repo from `-C` but read the staged set
    # from `cwd`, so a code commit into the ungated repo rode the docs
    # carve-out whenever cwd had nothing staged (reproduced in review).
    target_dir = cwd
    for _subcommand, op_tokens in ops:
        for position, op_token in enumerate(op_tokens):
            if op_token == "-C" and position + 1 < len(op_tokens):
                target_dir = op_tokens[position + 1]
    if repos and repos <= UNGATED_REPOS:
        code = _staged_code(target_dir)
        if code is None:
            return True, (
                "review-gate: BLOCKED — a report is pending and the staged set of this `meta` commit "
                "could not be read, so the docs-only carve-out cannot be applied."
            )
        if not code:
            return False, f"pending report(s), but this commit touches only {sorted(repos)} docs — ungated"
        return True, (
            f"review-gate: BLOCKED — a report is pending and this `meta` commit stages CODE "
            f"({', '.join(code[:3])}). The carve-out is for tickets and docs, not for meta's own "
            f"tooling — including this gate."
        )

    reason = _override(command)
    if reason:
        return False, f"OVERRIDDEN: {reason}"

    lines = [
        "review-gate: BLOCKED — a teammate has sent findings you have not received yet.",
        f"  {why}",
        *(f"  · {item}" for item in pending),
    ]
    if undetermined:
        lines.append("  · the inbox could not be read — 'cannot determine', not 'clear'.")
    lines += [
        "",
        "END YOUR TURN NOW. Teammate reports arrive only at a turn boundary, so stopping is what",
        "delivers them. Read them, fix what they found, then commit.",
        f"To commit anyway: {OVERRIDE_ENV}='<why>'. The reason is logged.",
    ]
    return True, "\n".join(lines)


def decide_stop(
    *,
    transcript_path: Path,
    last_assistant_message: str,
    aliases: dict[str, str] | None = None,
) -> tuple[bool, str]:
    delivered = delivered_this_turn(transcript_path)
    if not delivered:
        return False, "no teammate report was delivered in this turn"
    if not last_assistant_message.strip():
        # No closing text to judge. Blocking here is unsatisfiable — there is nothing the assistant can
        # change to pass — so it would deadlock the turn rather than gate a claim.
        return False, "no closing message to evaluate (cannot determine, not blocking: would deadlock)"
    reason = _override()
    if reason:
        # Checked BEFORE the dismissal branch: that branch used to return first, so the documented
        # escape hatch could not release a dismissal block at all. Found by the generic sweep.
        return False, f"OVERRIDDEN: {reason}"

    lowered = last_assistant_message.lower()
    dismissed = [phrase for phrase in _DISMISSALS if phrase in lowered]
    names = {agent for agent, _ in delivered}
    # An agent may be referred to by its instance name OR its agent type — it blocked a closing message
    # that said "best-practices reported" because the instance was "myproj-best-practices". Substance
    # acknowledged, refused on a string. Safe to widen: the block message names neither, so this can
    # still only be satisfied from the delivered report.
    accepted = names | {(aliases or {}).get(name, "") for name in names} - {""}
    if dismissed:
        return True, "\n".join(
            [
                f"review-gate: BLOCKED — {len(delivered)} teammate report(s) landed in this turn and your",
                f"closing message dismisses the round: {dismissed[0]!r}.",
                "",
                "That sentence is the harm this gate exists to prevent. Naming the agents does not make",
                "it true. Read what they sent, act on it, and correct anything already written.",
            ],
        )
    if any(token and token in last_assistant_message for token in accepted):
        return False, "closing message refers to a reporting teammate"

    count = len({agent for agent, _ in delivered})
    return True, "\n".join(
        [
            f"review-gate: BLOCKED — {len(delivered)} teammate report(s) from {count} agent(s) landed",
            "in this turn and your closing message does not acknowledge any of them.",
            "",
            "The reports are already in your context — read them there. This message deliberately",
            "does NOT name the agents: naming them let a retry satisfy this gate by echoing the",
            "block text back, which is a guard that cannot fail.",
            "",
            "Do not characterise the round as clean or finished. Act on them, and correct anything",
            "already written — the ticket, STATUS, and the owner-facing summary.",
        ],
    )


def _log(mode: str, reason: str, payload: dict) -> None:
    """Append one bypass record. Carries WHEN, WHICH SESSION and WHAT — the first version recorded only
    `{mode, reason}`, so "was the gate bypassed for commit X" was unanswerable, which is the whole point
    of keeping a log. A failed write is reported, never swallowed: the block message promises this."""
    entry = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "reason": reason,
        "session_id": str(payload.get("session_id") or ""),
        "agent_id": str(payload.get("agent_id") or ""),
        "cwd": str(payload.get("cwd") or ""),
        "command": str((payload.get("tool_input") or {}).get("command") or "")[:400],
    }
    try:
        log = _override_log()
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.is_symlink():
            raise OSError(f"{log} is a symlink — refusing to append through it")
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"review-gate: BYPASS WENT UNLOGGED ({exc})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("pretooluse", "stop"))
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise TypeError(f"payload is {type(payload).__name__}, expected object")
    except (ValueError, TypeError, OSError) as exc:
        # Not exit 1: a non-2 exit is a NON-blocking error, so a crash here would fail OPEN.
        print(f"review-gate: BLOCKED — unusable hook payload ({exc})", file=sys.stderr)
        return 2

    try:
        teams_root_override = os.environ.get("REVIEW_GATE_TEAMS_ROOT")
        teams_root = Path(teams_root_override or (Path.home() / ".claude" / "teams"))
        if teams_root_override:
            # Redirecting the teams root disables every gate, so it is logged like the override.
            _log(args.mode, f"teams-root redirected to {teams_root_override}", payload)
        if args.mode == "pretooluse":
            if payload.get("tool_name") != "Bash":
                return 0
            block, reason = decide_commit(
                command=str((payload.get("tool_input") or {}).get("command") or ""),
                cwd=str(payload.get("cwd") or Path.cwd()),
                session_id=str(payload.get("session_id") or ""),
                agent_id=str(payload.get("agent_id") or ""),
                teams_root=teams_root,
            )
        else:
            if payload.get("stop_hook_active"):
                # We are re-invoked on our own block. Blocking again wedges the
                # turn permanently: the block message deliberately names no
                # agent, and a stop-mode override cannot be set from inside the
                # session. One block is the signal; the retry passes.
                return 0
            team_dir, _why = resolve_team(
                teams_root, str(payload.get("session_id") or ""), str(payload.get("agent_id") or ""),
            )
            block, reason = decide_stop(
                transcript_path=Path(str(payload.get("transcript_path") or "")),
                last_assistant_message=str(payload.get("last_assistant_message") or ""),
                aliases=agent_type_aliases(team_dir),
            )
    except Exception as exc:  # noqa: BLE001 — fail CLOSED and name itself
        print(
            f"review-gate: BLOCKED — the gate raised {type(exc).__name__}: {exc}. That is 'cannot "
            f"determine', not 'clear'. Set {OVERRIDE_ENV}='<why>' to proceed.",
            file=sys.stderr,
        )
        return 2

    if reason.startswith("OVERRIDDEN: "):
        _log(args.mode, reason.removeprefix("OVERRIDDEN: "), payload)
        print(f"review-gate: {reason}", file=sys.stderr)
        return 0
    if block:
        print(reason, file=sys.stderr)
        return 2
    if ("pending report" in reason or "cannot determine" in reason
            or "no teammates were spawned" in reason):
        # Not a block, but the operator must be able to learn the gate stood down and why. Every "why"
        # on the allow path used to be computed and discarded, so an inert gate looked like a clear one.
        print(f"review-gate: allowed — {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        # ANY escape must exit 2. An uncaught error exits 1, and PreToolUse treats 1 as a NON-blocking
        # error — so a broken gate would wave every commit through. Measured: a NameError above main()'s
        # try produced exit 1 while a report was pending.
        print(
            f"review-gate: BLOCKED — the gate failed to run ({type(exc).__name__}: {exc}). That is "
            f"'cannot determine', not 'clear'. Set {OVERRIDE_ENV}='<why>' to proceed.",
            file=sys.stderr,
        )
        sys.exit(2)
