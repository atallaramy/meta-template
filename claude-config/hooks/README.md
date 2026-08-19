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
`~/.claude/review-gate-overrides.log`.

**Tune per project:** `KNOWN_REPOS` / `UNGATED_REPOS` at the top of `review_gate.py` (which repo
names commits resolve to, and which repos' docs-only commits skip the gate).

## Enabling (ships disabled)

The hooks are inert until wired into your Claude Code settings. To enable, merge this fragment
into your project root's `.claude/settings.json` (adjust the path if your meta folder is named
differently):

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
