# tasksquatch

> An offline-first, local-only todo tracker. The tracker that hunts down your tasks.

`tasksquatch` is a single-user, offline, open-source todo application
inspired by Todoist — with **no SaaS dependency** and **no always-on
server.** A single Python package exposes five surfaces over one shared
`core` library backed by SQLite (WAL): a Typer CLI, a Textual TUI, a
lightweight server-rendered Web UI, a local FastAPI REST API, and an
MCP server so Claude Code (and other MCP clients) can manage your
tasks. No network calls are required for any core operation.

**Status:** alpha, under construction. The skeleton is in place; the
implementation lands epic by epic. The canonical design is in
[`docs/spec.md`](docs/spec.md).

## Quickstart

When published, the recommended install is via [`pipx`](https://pipx.pypa.io/):

```bash
pipx install tasksquatch
```

For development:

```bash
make install   # editable install with dev extras
make test      # run the test suite
```

Run `make help` to see all available targets.

## Links

- [Build spec (canonical design)](docs/spec.md)
- [CLAUDE.md (working conventions)](CLAUDE.md)
- [Architecture notes](docs/architecture.md)
- License: [MIT](LICENSE)
