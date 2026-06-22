# tasksquatch external test plans

This directory complements the in-process pytest suite with two
external surfaces:

1. **Shell-driven smoke scripts** under `scripts/smoke-*.sh` exercise
   the installed `tsq`, `tasksquatch web`, and `tasksquatch-mcp`
   surfaces against scratch databases. They produce colour-coded
   PASS/FAIL output and exit non-zero on any failure.
2. **Manual checklist plans** in this directory walk a human through
   the surfaces that automation cannot reasonably cover (live TUI
   render, real desktop notifications, a wheel install on a clean
   machine, MCP integration from inside Claude Code).

## When to run what

| Surface                              | Tool                                                       | Type      |
| ------------------------------------ | ---------------------------------------------------------- | --------- |
| CLI commands                         | `scripts/smoke-cli.sh`                                     | automated |
| REST API + Web UI HTTP layer         | `scripts/smoke-web.sh`                                     | automated |
| MCP JSON-RPC wire protocol           | `scripts/smoke-mcp.sh`                                     | automated |
| TUI screens (visual + keypress)      | [`manual-tui-plan.md`](manual-tui-plan.md)                 | manual    |
| Web UI (HTMX, in a real browser)     | [`manual-web-plan.md`](manual-web-plan.md)                 | manual    |
| Desktop notification banners         | [`manual-notify-plan.md`](manual-notify-plan.md)           | manual    |
| Claude Code MCP integration          | [`manual-mcp-plan.md`](manual-mcp-plan.md)                 | manual    |
| Wheel install on a clean machine     | [`manual-wheel-install-plan.md`](manual-wheel-install-plan.md) | manual |

Run all three automated scripts with `make smoke` (see the project
`Makefile`).

## Plan summary

- [`manual-tui-plan.md`](manual-tui-plan.md) — ~15 min, single
  terminal, scratch DB. Walks every Textual screen.
- [`manual-web-plan.md`](manual-web-plan.md) — ~10 min, one terminal
  for the server plus a browser. Confirms HTMX swaps land, the form
  flow round-trips, and `/docs` renders.
- [`manual-notify-plan.md`](manual-notify-plan.md) — ~5 min, macOS
  only. Verifies a real banner fires for a due task and that re-runs
  dedup correctly.
- [`manual-mcp-plan.md`](manual-mcp-plan.md) — ~10 min, requires
  Claude Code installed. Pastes the MCP block from
  `docs/mcp-setup.md`, runs a few prompts, and confirms the
  no-delete policy.
- [`manual-wheel-install-plan.md`](manual-wheel-install-plan.md) —
  ~10 min, needs `uv` (or `python -m build`) and `pipx`. Builds the
  wheel, inspects packaged assets, installs it in an isolated env,
  and exercises the top-level commands.
