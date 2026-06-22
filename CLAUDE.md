# CLAUDE.md — tasksquatch

This file orients Claude Code (and any other AI assistant) working in this
repository. The canonical design lives in [`docs/spec.md`](docs/spec.md);
this file captures the conventions and guardrails the implementation
should follow on top of that design.

> **Read [`docs/spec.md`](docs/spec.md) before making non-trivial
> changes.** It is the source of truth for what tasksquatch is and what
> v1 deliberately is not.

---

## 1. Project overview

`tasksquatch` is an offline-first, local-only, single-user todo tracker
inspired by Todoist but with no SaaS dependency and no always-on server.
A single Python package exposes five surfaces over one shared `core`
library backed by SQLite (WAL):

1. **CLI** (Typer) — fast terminal interaction.
2. **TUI** (Textual) — interactive terminal app with native fuzzy filter.
3. **Web UI** — lightweight server-rendered local dashboard.
4. **REST API** (FastAPI) — local CRUD surface for the Web UI and for
   user automation.
5. **MCP server** — exposes core to Claude Code and other MCP clients.

The defining trait — and the **key deviation from kanbaroo** (the prior
project this draws shape from) — is that there is **no always-on server.**
The REST API exists only while the user runs `tasksquatch web`; the MCP
runs only when launched as `tasksquatch-mcp`; the CLI, TUI, and the
`tasksquatch notify` cron entry each open their own short-lived session
against the SQLite file directly. WAL mode lets these processes coexist
safely. Nothing depends on any other surface being up.

---

## 2. Principles

These are non-negotiable. If a change conflicts with one of these,
escalate before implementing it.

- **Offline-first, local-only.** No network calls in any core operation.
  No cloud, no account, no sync, no SaaS dependency, no daemon required
  for basic use.
- **`core` is the single source of truth.** All data model and business
  logic lives in `src/tasksquatch/core/`. Every surface is a thin
  consumer of `core`. Surfaces are **siblings**, not layers — the REST
  API and MCP do not call the CLI, and the MCP does not call the REST
  API. Each surface opens its own in-process session against `core`.
- **SQLite (WAL) + SQLAlchemy 2.x.** Concurrency across CLI, TUI, cron
  notify, MCP, and a passive DataGrip reader must be safe. WAL mode is
  required.
- **UUIDv7 internal primary keys**, plus a globally sequential
  user-facing `number` (see `spec.md` §5).
- **No always-on server.** The REST and MCP surfaces are launched on
  demand. CLI/TUI/notify each open their own short-lived session. This
  is the **explicit deviation from kanbaroo**, which used a central
  server everything else talked to.
- **Hard delete.** Deleting a task removes its row. Its `number` is
  retired forever via a counter and is never reused, so `#42` remains a
  stable reference in shell history and notes even after deletion.
- **No optimistic concurrency.** No ETag, no `If-Match`, no version
  column on entities in v1. A single user across surfaces does not need
  it; if you find a need, raise it as an explicit design change.
- **No token auth on the REST API.** It binds to loopback only and is
  not exposed off the machine. Do not add a token, an API key, or auth
  middleware "just in case."
- **Append-only activity log on every mutation.** Every state-changing
  operation in `core` must emit an `ActivityLog` row. The log is never
  edited or deleted by application logic.
- **Recurrence stored as RRULE strings** (RFC 5545) with a
  `recurrence_anchor` of `fixed` or `relative`. Advance-in-place on
  completion — recurring tasks keep the same row and same `id`.
- **Idempotency and crash safety.** Operations should be safe to retry.
  A crash mid-operation must not corrupt state.

---

## 3. Build / dev commands

Common loops are wrapped in `Makefile` targets:

| Command          | What it does                                         |
| ---------------- | ---------------------------------------------------- |
| `make install`   | Editable install with `dev` extra (prefers `uv`)     |
| `make test`      | `pytest -q`                                          |
| `make lint`      | `ruff check .`                                       |
| `make format`    | `ruff format .`                                      |
| `make typecheck` | `mypy src` (strict)                                  |
| `make run`       | `tasksquatch --help`                                 |
| `make clean`     | Remove build artifacts and tool caches               |

Pre-commit hooks (run `pre-commit install` once, then automatic) cover
ruff lint, ruff format, mypy, trailing whitespace, EOF newline, and
YAML/TOML validity.

CI runs on Python 3.12 only on `ubuntu-latest` (see
`.github/workflows/ci.yml`). The CI pipeline is the same checks that
`make lint format typecheck test` run locally.

---

## 4. Repository structure

```
.
├── docs/
│   ├── spec.md                 # Canonical design — read first
│   └── architecture.md         # Architecture notes (grows as we build)
├── src/tasksquatch/
│   ├── __init__.py             # __version__
│   ├── core/                   # Data model + business logic (Epic 1+)
│   ├── cli/                    # Typer surface (Epic 2)
│   ├── tui/                    # Textual surface (Epic 5)
│   ├── rest/                   # FastAPI surface (Epic 6)
│   ├── web/                    # Server-rendered dashboard (Epic 7)
│   ├── mcp/                    # MCP server surface (Epic 8)
│   └── notify/                 # Desktop notification entry (Epic 9)
├── tests/                      # pytest suite, mirrors src layout
├── pyproject.toml              # Build, deps, tool config
├── Makefile                    # Common dev tasks
├── .pre-commit-config.yaml     # Pre-commit hooks
├── .github/workflows/ci.yml    # CI: lint + format + mypy + pytest
├── CLAUDE.md                   # This file
├── README.md                   # Human intro
└── LICENSE                     # MIT
```

Each surface lives under `src/tasksquatch/<surface>/` and imports from
`tasksquatch.core`. Surfaces never import each other.

---

## 5. Code conventions

- **Python 3.12+ only.** Use 3.12 stdlib (`tomllib`, modern typing
  syntax, etc.). Do not vendor backports.
- **Formatting and linting:** `ruff` (line length 88, target `py312`,
  rules `E F W I UP B SIM`). Run `ruff format` and `ruff check --fix`
  before pushing.
- **Type checking:** `mypy --strict` on `src/` and `tests/`. New code
  must type-check cleanly. No `# type: ignore` without a comment
  explaining why.
- **Imports:** stdlib, third-party, local — separated and sorted (ruff
  `I` handles this). All imports at the **top** of the file. No
  `from x import *`. No lazy/inline imports.
- **Docstrings:** PEP 257 multi-line style. Document params, returns,
  raised exceptions, and side effects for public APIs.
  ```python
  def f() -> None:
      """
      One-line summary.

      Longer prose if needed.
      """
  ```
- **Naming:** snake_case for functions and variables, PascalCase for
  classes, UPPER_SNAKE_CASE for module-level constants.
- **Errors:** raise specific exception types. No bare `except:`. Log
  errors with context where caught.
- **Spelling:** American English in code, comments, docs, and commit
  messages (per the user's global preference), **except** where a
  stdlib API name forces British (`asyncio.CancelledError`,
  `Future.cancelled()`, etc.). Match the surrounding API rather than
  fighting it.
- **Comments:** default to none. Only add a comment when the *why* is
  non-obvious. Don't restate what the code already says.

---

## 6. SQLAlchemy 2.x + Pydantic patterns

- Use **SQLAlchemy 2.x declarative** mapped classes (`Mapped[...]`,
  `mapped_column(...)`) rather than the legacy `Column(...)` style.
- Primary keys are **UUIDv7** (use `uuid-utils`), stored as `String(36)`
  for portability across SQLite tooling (DataGrip, the `sqlite3` CLI).
  The friendly `number` is a separate column populated from a counter
  that **never decrements** — retired numbers are gone forever.
- Timestamps are timezone-aware UTC (`datetime` with `tzinfo=UTC`). Do
  not store naive datetimes.
- Use a single `engine` per process (SQLite + WAL) constructed in
  `core`. Surfaces ask `core` for a session via a context manager;
  surfaces do not construct sessions themselves.
- Pydantic v2 is used for DTOs at surface boundaries (CLI args/output,
  REST request/response, MCP tool I/O). ORM rows do not leak into the
  REST or MCP layer — convert through Pydantic models.
- Schema migrations live in `alembic/` (added in Epic 1, not in this
  scaffold). Mypy excludes `alembic/` because generated migration files
  are not worth strictly typing.

---

## 7. FastAPI patterns (when Epic 6 lands)

- Routers live in `src/tasksquatch/rest/routers/` and group by resource
  (`tasks`, `projects`, `labels`, `comments`, `activity`).
- **Endpoint functions are thin.** They parse input via Pydantic, call
  a function in `core/services/`, and serialize the result. No
  business logic in routers.
- Bind to **127.0.0.1 only** by default. No CORS-open-to-the-world, no
  token auth, no API key. This is a local automation surface, not a
  multi-tenant service.
- Dependency injection via `Depends` is fine for session handling, but
  keep the dependency graph shallow — this is not enterprise software.

---

## 8. Testing

- `pytest` with `asyncio_mode = "auto"`. Test layout mirrors `src/`.
- `core` carries the bulk of the unit tests (data model invariants,
  recurrence math, activity log emission, number retirement, etc.).
- Surfaces get **thinner** tests:
  - CLI: invoke the Typer app with `CliRunner`, assert on output and
    on the resulting database state.
  - REST: spin a `TestClient` and contract-test endpoint shapes.
  - TUI: `pytest-textual-snapshot` for screen snapshots.
  - MCP: unit-test the tool implementations directly against `core`;
    do not stand up a real MCP server in tests.
- Tests run against a fresh temporary SQLite file (or `:memory:` where
  WAL is not in play). Do not share state between tests.
- New behavior in `core` requires a test. New surface behavior requires
  at least a smoke test that exercises the path end-to-end.

---

## 9. Key architectural patterns

- **`core` is in-process and synchronous** (except where SQLAlchemy
  async sessions are explicitly chosen for a surface). Async lives at
  the FastAPI and MCP boundary, not inside `core`.
- **Activity log emission is centralized.** Mutating service functions
  in `core/services/` emit log entries themselves — surfaces do not
  log mutations on their behalf. This keeps the log complete regardless
  of which surface caused the change.
- **Numbering is a counter, not `MAX(number) + 1`.** The counter
  monotonically increases and is never decremented when a task is
  deleted, so numbers are permanently retired.
- **Recurrence advances in place.** Completing a recurring task updates
  its row (new `due_date`, `completed=False` re-armed for the next
  occurrence) and emits both `completed` and `recurrence_advanced`
  events to the activity log.
- **Notifications are pull-based.** `tasksquatch notify` is a one-shot
  command the user runs from cron / launchd / systemd. `core` exposes
  the due-checking; `notify/` calls a cross-platform desktop notifier.
  `last_notified_at` de-duplicates within a due occurrence.

---

## 10. Git workflow

- **Never commit directly to `main`.** Always create a feature branch
  and open a PR. Branch naming: `feature/<slug>`, `fix/<slug>`,
  `chore/<slug>`, or — when working off an issue — `<issue>_<slug>`.
- Commits are atomic actions; **do not commit without confirmation**
  from the human driving the session.
- Pre-commit hooks must pass before commit. Do not bypass with
  `--no-verify` to push through a failing hook — fix the underlying
  issue.
- Pull requests should describe the *why* and the user-visible change.
  Link to the relevant Epic/story.

---

## 11. Release workflow

- Releases are tags on `main` of the form `vX.Y.Z`. The version in
  `pyproject.toml` and `src/tasksquatch/__init__.py` must match the
  tag.
- Build with `python -m build`; publish to PyPI via the standard
  `twine upload`. Releases happen from a clean main with CI green;
  there is no separate release branch in v1.

---

## 12. Versioning

Follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- `MAJOR` for breaking changes to the CLI, REST, MCP, or DB schema
  surface contracts.
- `MINOR` for new features that are backwards-compatible.
- `PATCH` for bug fixes and internal refactors.

Pre-1.0 (which is where this lives now), the API is still in flux and
minor breakage in `0.x.0` releases is acceptable; document any breaks
in the release notes.

---

## 13. Working with the spec

`docs/spec.md` is the canonical design.

- Treat it as the source of truth for **what** tasksquatch is.
- If an implementation question is not answered there, treat it as an
  open design decision and surface it explicitly before guessing.
- If you have to deviate from the spec, write down why in
  `docs/architecture.md`, raise it with the user, and update the spec
  before merging the deviation.
- The non-goals in `spec.md` §13 are real. Do not quietly build any of
  them.

---

## 14. Documentation sync

- Update `CLAUDE.md` when conventions or guardrails change.
- Update `docs/architecture.md` as the architecture solidifies — the
  spec describes the design; architecture notes describe the
  realization.
- Keep `README.md` accurate for human readers: status, install,
  quickstart, and links to spec/CLAUDE/LICENSE.

---

## 15. Things NOT to do

These are the recurring traps. Read this list before you start, and
again before you commit.

- **No commits directly to `main`.** Feature branches and PRs only.
- **No hard-coded API tokens, credentials, or secrets.** Anywhere. Use
  environment variables for any local config that genuinely needs to
  vary.
- **No `from x import *`.** No lazy / inline / function-local imports.
  Imports go at the top of the file.
- **No business logic inside endpoints, CLI commands, or TUI screens.**
  Those layers parse input, call into `core/services/`, and format
  output. State changes live in `core`.
- **No deletes from the MCP surface.** The MCP may create, read,
  update, complete, uncomplete, comment, and edit comments — but it
  **may not delete** tasks, projects, labels, or comments. Destructive
  deletion is reserved for CLI and TUI.
- **No live cross-process refresh / WebSocket push in v1.** Surfaces
  refresh on user action, not on external change.
- **No optimistic concurrency** (ETag, `If-Match`, version columns).
  Single-user app; if you ever need this, escalate.
- **No token auth on the REST API.** Bind loopback only.
- **No always-on server.** Do not introduce a background daemon as a
  prerequisite for the CLI, TUI, MCP, or notifications.
- **No natural-language date parsing** (e.g. "tomorrow 5pm"). Lean on
  the LLM via MCP for that; v1 takes structured fields only.
- **No British-spelling drift** in your own prose just because a
  nearby stdlib name uses one. American English in our text; let
  `asyncio.CancelledError` etc. be British where the API is.
- **No backwards-compat shims for code that never shipped.** This is a
  pre-1.0 codebase; delete dead code instead of working around it.
