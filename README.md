# tasksquatch

> An offline-first, local-only todo tracker. The tracker that hunts down your tasks.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#)

`tasksquatch` is a single-user, offline todo tracker inspired by Todoist —
with **no SaaS dependency** and **no always-on server.** Five surfaces (CLI,
TUI, Web UI, REST API, MCP) share one `core` library backed by SQLite in
WAL mode, so every surface opens its own short-lived session against the
same database file and nothing requires a daemon to be running.

## Install

```bash
pipx install tasksquatch  # (when published)
```

For development:

```bash
git clone https://github.com/areese801/tasksquatch
cd tasksquatch && make install
```

## Quickstart

### CLI

Use `tasksquatch` or the short alias `tsq`.

```bash
tasksquatch add "Buy milk" -d today
tasksquatch list
tsq done 1
```

### TUI

```bash
tasksquatch tui
```

### Web UI

```bash
tasksquatch web
```

Then open <http://127.0.0.1:8000/ui>.

### REST API

```bash
tasksquatch web
```

The OpenAPI docs live at <http://127.0.0.1:8000/docs> and the API itself is
mounted at `/api/v1`.

### MCP (Claude Code)

Add this block to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "tasksquatch": {
      "command": "tasksquatch-mcp"
    }
  }
}
```

Restart Claude Code. See [`docs/mcp-setup.md`](docs/mcp-setup.md) for the
full tool catalog and the no-entity-delete permission guard.

### Notifications

`tasksquatch notify` is a one-shot command meant to be scheduled by your
host's native scheduler. See [`docs/notifications.md`](docs/notifications.md)
for cron, launchd, and systemd recipes.

## Threat model

The REST API and Web UI bind to `127.0.0.1` only and carry **no auth**.
That is intentional — `tasksquatch` is a local-only, single-user tool. Do
not expose either surface to a network. If you need remote access, use SSH
port-forwarding (`ssh -L 8000:127.0.0.1:8000 host`) rather than binding to
a public interface or adding ad-hoc auth.

## Docs

- [Build spec (canonical design)](docs/spec.md)
- [CLAUDE.md (working conventions)](CLAUDE.md)
- [MCP setup](docs/mcp-setup.md)
- [Notifications](docs/notifications.md)
- [Release procedure](docs/release.md)
- [Architecture notes](docs/architecture.md)

## Develop

Common loops are wrapped in `Makefile` targets — `make help` lists them.

```bash
make install     # editable install with dev extras
make test        # pytest -q
make lint        # ruff check .
make format      # ruff format .
make typecheck   # mypy src (strict)
```

Pre-commit hooks cover ruff lint, ruff format, mypy, and the usual
trailing-whitespace / EOF / YAML / TOML checks. Run `pre-commit install`
once.

## Testing

### Unit + contract tests

```bash
make test    # pytest -q — the in-process suite
```

### External smoke (recommended pre-release)

The `scripts/smoke-*.sh` suite drives the installed `tsq`, `tasksquatch
web`, and `tasksquatch-mcp` surfaces against scratch databases. Run
them all in sequence:

```bash
make smoke
```

Or pick one:

```bash
make smoke-cli   # CLI end-to-end against a scratch DB
make smoke-web   # REST + Web UI against a scratch server (port 18080)
make smoke-mcp   # MCP JSON-RPC over stdio
```

Each script exits non-zero on the first failed assertion and prints a
colour-coded PASS/FAIL tally at the end.

### Manual verification

`test-plans/README.md` indexes the human-driven checklists for the
surfaces automation can't reasonably cover: the TUI screens, real
desktop notifications, a wheel install on a clean machine, and the
Claude Code MCP integration.

## License

[MIT](LICENSE).
