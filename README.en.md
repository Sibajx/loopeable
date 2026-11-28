# 🔁 loopeable

**English** · [Español](README.md)

**Leave Claude Code working.** A loop that orchestrates loops: give it a goal and information, and loopeable turns it
into tasks, runs one loop per task (several in parallel, each with its own agents and subagents), verifies, reviews,
integrates, and keeps going until it's done or hits a limit. It pings your phone when it needs you.

```
ORCHESTRATOR (code, not the model: limits, brakes, git, state)
  ├─ planner ── subagents: explorer ×N, researcher → tasks with criteria, priority, dependencies → 📝 await your OK
  ├─ loop T01 (own worktree) ┐
  ├─ loop T02 (own worktree) ┼ in parallel
  └─ loop T03 …              ┘
       implementer (+ explorer, researcher, tester) → verify (your tests, no AI) → security gate (security-suite,
       optional) → reviewer (+ correctness · security · consistency in parallel, only for big diffs) → fix … →
       commit → integrator
       ↳ finds something missing → subtask → another loop
  watcher: proposes a new approach when a loop repeats the same error; records a lesson at the end
```

- **Control lives in code.** Budget, time, attempts, depth, forbidden paths and dangerous commands are enforced by
  loopeable through an Agent SDK `PreToolUse` hook — an agent cannot talk its way past them.
- **"Done" is decided by your tests,** not by the model saying so. The (expensive) reviewer only runs after tests
  pass, in a fresh session that didn't write the code.
- **Clean history.** Each loop works in its own `git worktree`; passing tasks become one commit each on
  `loopeable/<date>`; failures are discarded. `main` is never touched.
- **Learns.** `LOOPEABLE-APRENDIZAJES.md` keeps one lesson per hard task, read by the next run.
- **Resumable.** SQLite state in `.loopeable/estado.db`.
- **Budget-aware.** `[limites] usd_minimo_sesion` (0.25): no session starts with less left than that, and only
  `margen_saldo` (0.75) of what's left is split across the running loops, since the SDK's per-session cap isn't
  hard (background subagents keep spending). Diffs up to `diff_chico_lineas` (40) lines and `diff_chico_archivos` (3)
  files get a cheap review (implementer's model, no subagents); root Markdown and `docs/**` don't count
  (`diff_chico_ignorar`). Every rejected attempt is logged with its reason
  (`loopeable ver T03`, web board).

## Install & use

```bash
uv tool install git+https://github.com/Sibajx/loopeable
```
As a Claude Code plugin: `/plugin marketplace add Sibajx/loopeable` then `/plugin install loopeable@loopeable`, and
run **`/loopeable`** inside your project: it interviews you (folder, goal, work source, definition of done, limits,
paths not to touch, gates, notifications), writes `loopeable.toml`, shows the plan and launches it.

CLI: `iniciar` (template) · `planear` · `aprobar todas` · `correr` · `estado` · `ver T03` · `responder T03 "..."` ·
`reintentar` · `parar` · `pruebas`. New information? Drop another `.md` in `.loopeable/bandeja/` and run again.
Commit your project before creating `.loopeable/bandeja/` (if `.loopeable/` ends up in git, loopeable removes it
with a commit on its own branch, never on `main`).

Needs git, Python ≥ 3.11 and Claude credentials (`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` from
`claude setup-token`). Run agents inside Docker (`docker/`, sandboxed, optional egress firewall) when anything
valuable is nearby — agents have Bash. For 24/7 on a server with systemd and phone notifications, see
[`despliegue/SERVER.md`](despliegue/SERVER.md).

Tests: `uv run --extra dev pytest` exercises the whole orchestrator with a fake AI — no cost.

> ⚠️ loopeable automates; it doesn't guarantee. Review the branch before merging. MIT licensed.
