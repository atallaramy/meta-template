# Review-gate hooks

Two gates that stop the classic multi-agent review failure: a teammate's findings sit undelivered
in the lead's inbox while the lead commits and declares the round clean.

- `review_gate.py --mode pretooluse` — refuses a commit-producing git/gh command while a teammate
  report sits undelivered. Ending the turn is what delivers the report; the block forces that.
- `review_gate.py --mode stop` — refuses a closing message that dismisses a round ("0 findings",
  "agents were silent") when reports actually landed in this turn.
- `review_gate_test.py` — the unit suite (stdlib only). Run: `python3 claude-config/hooks/review_gate_test.py`.
- `red_states.py` — proves every guard has a reachable red state (named flips + a mechanical
  mutant sweep). Run: `python3 claude-config/hooks/red_states.py` (`--sweep`, `--triage`).

**KNOWN LIMITATION (upstream, unfixed at port time):** the stop gate keeps no record of an
already-acknowledged report, so in a long autonomous stretch every later close must re-name a
reporting agent or be re-blocked; and cross-session peer messages are invisible to it. Fix
upstream first or accept occasional false blocks. The deliver-mode gate and dismissal branch are
sound.

**Escape hatch:** `REVIEW_GATE_OVERRIDE='<why>' git commit …` — the reason is logged to
`~/.claude/review-gate-overrides.log` (path overridable via `REVIEW_GATE_LOG`).

**Tune per project:** `KNOWN_REPOS` / `UNGATED_REPOS` at the top of `review_gate.py` (which repo
names commits resolve to, and which repos' docs-only commits skip the gate). `bootstrap.sh` does
NOT substitute these — edit them by hand when your repo layout differs.

**Environment variables** (all three affect gate behavior — document any use):
- `REVIEW_GATE_OVERRIDE='<why>'` — one-shot bypass, logged.
- `REVIEW_GATE_LOG` — where bypasses are logged.
- `REVIEW_GATE_TEAMS_ROOT` — redirects the team-inbox root; **this disables both gates against the
  real inboxes**, so setting it is itself logged as a bypass.

**Requires Python ≥ 3.9** (`str.removeprefix`).

**Residual known gaps** (also in the module docstring): repo attribution picks the outermost
path component named in `KNOWN_REPOS`, not the git toplevel — an ancestor directory named e.g.
`meta` mis-attributes commits under it; a nested shell invoked with a value-taking option but
without `-c` (`bash -o errexit script.sh`) analyses the wrong token; and command substitution in
command position (`$(echo git commit -m x)`) is opaque to any static tokeniser — only LITERAL
`git`/`gh` tokens are caught. All three are documented rather than hidden.

## Enabling (ships disabled)

The hooks are inert until wired into your Claude Code settings. To enable, merge this fragment
into your project root's `.claude/settings.json` (adjust the path if your meta folder is named
differently):

**Verify the install** — a mis-wired path or missing `python3` exits non-2, and the hook runner
treats that as NON-blocking, i.e. a broken install fails OPEN and silent. After wiring, prove the
gate actually bites (expect exit 2 and a BLOCKED message when a report is pending, exit 0 with a
"gate stood down" note otherwise):

```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"},"cwd":"'$PWD'","session_id":"selftest0"}' \
  | python3 meta/claude-config/hooks/review_gate.py --mode pretooluse; echo "exit: $?"
```

```jsonc
// .claude/settings.json — hooks fragment (copy into your existing "hooks" key)
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/meta/claude-config/hooks/review_gate.py --mode pretooluse",
            "timeout": 15,
            "statusMessage": "review-gate: checking for undelivered teammate reports..."
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/meta/claude-config/hooks/review_gate.py --mode stop",
            "timeout": 15,
            "statusMessage": "review-gate: checking the closing message against delivered reports..."
          }
        ]
      }
    ]
  }
}
```
