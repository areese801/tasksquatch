# tasksquatch

> An offline-first, local-only todo tracker. The tracker that hunts down your tasks.

This document is a build specification intended as the primary input to a Claude Code implementation session. It captures the agreed design decisions, the data model, the architecture, the surface areas (CLI, TUI, Web UI, REST API, MCP), and the explicit non-goals for v1. Read the "Notes for the implementer" section at the end before writing code.

---

## 1. Summary

tasksquatch is a single-user, offline, open-source todo application inspired by Todoist, but with no SaaS dependency and no requirement for any always-on server. It is published publicly on GitHub under the MIT license and distributed on PyPI as a single installable package.

It exposes five surfaces over one shared core:

1. **CLI** for fast terminal interaction.
2. **TUI** for an interactive terminal app.
3. **Web UI** for a lightweight local dashboard.
4. **REST API** for the Web UI and for general local automation and integration.
5. **MCP server** so Claude Code (and other MCP clients) can manage tasks.

The design goal is that the basic tool works with nothing running in the background. The REST server, the Web UI, the MCP server, and desktop notifications are all optional surfaces layered on top of a core library, not prerequisites for it.

---

## 2. Core principles

- **Offline-first and local-only.** No network calls are required for any core operation. No cloud, no account, no sync.
- **Core library is the single source of truth.** All data model definitions and business logic live in one `core` package. Every surface (CLI, TUI, Web UI, REST API, MCP) is a thin consumer of `core` and talks to the same SQLite database directly. No surface is a hard dependency of another.
- **No daemon required for basic use.** The CLI, TUI, and MCP server call `core` in-process. Nothing needs to be running for them to work.
- **Idempotency and failure resilience.** Operations should be safe to retry. A crash mid-operation should never corrupt state. The fact that something runs is not evidence that it works.

---

## 3. Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.12+ (hard floor: 3.12) |
| ORM | SQLAlchemy 2.x |
| Database | SQLite, single file, WAL mode enabled |
| CLI framework | Typer |
| TUI framework | Textual |
| REST API framework | FastAPI |
| MCP | Official Python MCP SDK |
| Primary keys | UUIDv7 (internal), plus a friendly globally sequential numeric id (user-facing) |

The implementer chooses the test stack, the linter/formatter/type-checker, the CI setup, and supporting libraries (RRULE parsing, desktop notification, fuzzy matching, etc.). See "Notes for the implementer."

---

## 4. Architecture

```
                       +-------------------+
                       |    core (lib)     |
                       |  data model +     |
                       |  business logic   |
                       +---------+---------+
                                 |
            +----------+----------+----------+-----------+
            |          |          |          |           |
          CLI        TUI       REST API     MCP      cron / notify
        (Typer)   (Textual)   (FastAPI)   (MCP SDK)   (CLI entry)
            |          |          |          |           |
            +----------+----------+----------+-----------+
                                 |
                       +---------v---------+
                       |   SQLite (WAL)    |
                       |  single .db file  |
                       +-------------------+
                              ^
                              | (read-only inspection)
                          DataGrip
```

- All surfaces import `core` and operate on the same SQLite file directly. The REST API and MCP server are **siblings** of the CLI, not layers the CLI sits on top of.
- The MCP server wraps `core` in-process. It does **not** call the REST API. This keeps it fully offline with nothing else running.
- WAL mode is required so that multiple independent processes (TUI open, a cron notify run, an MCP call from Claude Code, a DataGrip read) can touch the file concurrently without lock contention. WAL-mode SQLite is readable by DataGrip.

### Database location

Follow the XDG Base Directory convention. Default to `$XDG_DATA_HOME/tasksquatch/tasksquatch.db`, falling back to `~/.local/share/tasksquatch/tasksquatch.db` when `XDG_DATA_HOME` is unset. Allow an override via an environment variable and/or a CLI flag. Create the directory on first run.

---

## 5. Data model

### Hierarchy

```
Inbox (the default project)
Projects
  └── Tasks
        └── Subtasks (arbitrary depth)
Labels (cross-cutting, span projects)
```

- **Inbox** is the default project. Any task created without an explicit project lands in the Inbox.
- **Projects** are flat. There are no sub-projects in v1.
- **Tasks** belong to exactly one project.
- **Subtasks** are modeled with a self-referencing `parent_id` (adjacency list) supporting **arbitrary nesting depth**. The data model imposes no depth cap. UIs decide how deeply they render; the storage layer does not care.
- **Labels** are cross-cutting and many-to-many. A task may carry several labels, and labels span projects.

### Entities

#### Task
| Field | Notes |
|---|---|
| `id` | UUIDv7, internal primary key |
| `number` | Globally sequential integer, user-facing (e.g. `#42`). See "Numeric id semantics." |
| `title` | Required |
| `description` | Long text, markdown |
| `project_id` | FK to Project; defaults to Inbox |
| `parent_id` | FK to Task (nullable); enables arbitrary-depth subtasks |
| `priority` | Enum P1, P2, P3, P4 (mirrors Todoist exactly; P1 highest, P4 default) |
| `due_date` | Nullable date |
| `due_time` | Nullable time component (a task may have a date with no specific time) |
| `recurrence` | Nullable RRULE string (RFC 5545); see "Recurrence" |
| `recurrence_anchor` | Enum: `fixed` (from scheduled date) or `relative` (from completion date); default `fixed` |
| `position` | Ordering within its sibling set, for manual ordering |
| `completed` | Boolean flag |
| `completed_at` | Nullable timestamp |
| `last_notified_at` | Nullable timestamp; supports notification de-duplication (see "Notifications") |
| `created_at` | Timestamp |
| `updated_at` | Timestamp |

There is a **single due field** (date plus optional time). There is no separate "deadline" concept in v1.

#### Project
| Field | Notes |
|---|---|
| `id` | UUIDv7 |
| `name` | Required; Inbox is a reserved, non-deletable project |
| `position` | Ordering in the project list |
| `created_at` / `updated_at` | Timestamps |

#### Label
| Field | Notes |
|---|---|
| `id` | UUIDv7 |
| `name` | Required, unique |

Plus a join table for the Task-to-Label many-to-many relationship.

#### Comment
| Field | Notes |
|---|---|
| `id` | UUIDv7 |
| `task_id` | FK to Task |
| `body` | Markdown text |
| `created_at` / `updated_at` | Timestamps |

Comments are **text only** in v1 (no file attachments). Comments are **editable and deletable** after posting.

#### ActivityLog
A **global, append-only, queryable** log of events across all tasks. Used both by the MCP surface and for later analytical use.

| Field | Notes |
|---|---|
| `id` | UUIDv7 |
| `task_id` | FK to Task (nullable for project/label-level events if needed) |
| `event_type` | e.g. `created`, `updated`, `completed`, `rescheduled`, `recurrence_advanced`, `commented`, `comment_edited`, `comment_deleted`, `moved`, `priority_changed` |
| `detail` | Structured payload (JSON) capturing what changed |
| `created_at` | Timestamp |

The log is append-only: entries are never edited or deleted by application logic.

### Numeric id semantics

- Each task gets a friendly integer `number`, assigned in creation order.
- Numbers are **globally sequential** across the whole application (not per-project), Todoist-style.
- Numbers are **never reused.** When a task is deleted, its number is retired permanently, so `#42` always refers to the same task across your shell history and notes.
- The UUIDv7 `id` remains the internal identity used in foreign keys and the API; `number` is purely a human-facing convenience.

### Recurrence

- Recurrence is stored as an **RRULE string** (RFC 5545, e.g. `FREQ=WEEKLY;BYDAY=MO`). This is the standard "traditional recurrence" representation, is inspectable as plain text in DataGrip, and gives an LLM a well-documented generation target.
- Two anchor modes are supported per task via `recurrence_anchor`:
  - `fixed`: the next due date is computed from the **original scheduled date** (e.g. rent on the 1st regardless of when paid). This is the default.
  - `relative`: the next due date is computed from the **completion date** (e.g. water plants every 3 days, measured from when last done).
- **Completion model (advance in place):** completing a recurring task does **not** spawn a new row. The same task row stays, its due date rolls forward to the next occurrence, and a `recurrence_advanced` (plus `completed`) event is written to the ActivityLog. This preserves a single stable task identity over time; the history of past completions lives in the log. Subtasks and comments stay attached to the one stable task.
- **Late tasks:** an overdue task is treated as if it is due today/now. There is no special "missed occurrence" handling beyond that.

---

## 6. Notifications

- **Goal:** desktop notifications on or around a task's due date and time. macOS is the primary platform, but keep the notification layer cross-platform where reasonable. No phone or push notifications.
- **Mechanism:** `core` exposes due-checking functions (e.g. `get_due_tasks()`), and a CLI entry point `tasksquatch notify` invokes them and fires native desktop notifications for anything currently due. The user wires this to run at a regular interval (cron is acceptable for v1; a lightweight background process is fine too).
- **De-duplication:** because the checker may run every few minutes, use `last_notified_at` to avoid notifying for the same task repeatedly. A task should notify once for a given due occurrence. If the due date/time changes, the task becomes eligible to notify again.
- **Optional daemon:** a packaged, cross-platform background component (launchd on macOS, systemd on Linux) is a **nice-to-have, optional** add-on. The core tool must work fully without it. Do not make notifications a hard dependency of anything else.

---

## 7. CLI surface

- Built with Typer. Single entry point command: `tasksquatch`.
- Subcommands cover task CRUD, completion, comments, project and label management, listing/filtering, plus:
  - `tasksquatch web` launches the Web UI server.
  - `tasksquatch tui` launches the TUI.
  - `tasksquatch notify` runs the due-check + desktop-notification pass (for cron).
  - `tasksquatch find` for fuzzy interactive selection (see fzf below).
- Tasks are referenced on the command line by their friendly `number` (e.g. `tasksquatch done 42`), not by UUID.

### fzf workflow

- **CLI:** shell out to the real `fzf` binary. `tasksquatch find` pipes tasks into `fzf` for interactive fuzzy selection, then acts on the chosen task. This adds an external runtime dependency on `fzf` being installed; detect its absence and degrade gracefully with a clear message.
- **TUI:** implement native, in-app fuzzy filtering (fzf-style behavior, no external binary).
- **Match target:** in both cases, fuzzy-match against task **title plus project plus labels**.

---

## 8. TUI surface

- Built with Textual.
- Interactive task management with native fuzzy filtering as described above.
- **Refresh-on-action** for v1. There is no live cross-process refresh. If an external writer (cron notify, an MCP call, the CLI) changes data while the TUI is open, the TUI reflects it on the next user action or manual reload, not automatically. (Live cross-process refresh is an explicit non-goal; see section 11.)

---

## 9. Web UI surface

- **Lightweight, server-rendered dashboard** for read and quick-edit. Prefer server-rendered HTML with minimal JavaScript (HTMX is a reasonable fit). This is intentionally not a full SPA.
- Talks to the local REST API.
- Launched via `tasksquatch web`.
- Refresh-on-action, consistent with the TUI. No WebSocket/SSE live-push in v1.

---

## 10. REST API surface

- Built with FastAPI. Local only.
- **Purpose:** serves both the Web UI **and** acts as a general automation/integration surface for the user's own scripts and external tools. Therefore it should be a **complete CRUD surface** over tasks, projects, labels, comments, and read access to the activity log, not just the minimum the Web UI needs.
- Wraps `core` in-process.

---

## 11. MCP surface

- Built with the official Python MCP SDK.
- **Wraps `core` directly, in-process.** It does not call the REST API. Nothing else needs to be running for Claude Code to manage tasks. Fully offline.
- Separate console script entry point: `tasksquatch-mcp` (MCP clients launch servers by command, so a dedicated entry point is the convention).

### Tool design philosophy: coarse-grained

Expose a small set of high-level, ergonomic tools rather than one tool per field-level operation. The LLM is good at filling structured arguments, so lean on that (including producing RRULE strings and structured recurrence settings). A coarse tool list keeps the model's interface legible.

Suggested initial tool set (the implementer may refine names and arguments):

- `add_task` (title, description, project, parent, priority, due date/time, labels, recurrence as RRULE + anchor)
- `update_task` (any mutable field)
- `complete_task`
- `list_tasks` / a flexible query tool (filter by project, label, priority, due state, completion)
- `add_comment`
- read access to projects, labels, and the activity log

These should comfortably support workflows like "turn my code-review TODOs into tasks" and "what should I work on next."

### MCP permissions

- The MCP server **may create, read, update, and complete** tasks.
- The MCP server **may not delete** tasks (or projects/labels/comments). Destructive deletion is reserved for the CLI and TUI. Completing a task is allowed; permanent deletion is not.

---

## 12. Packaging and distribution

- **Single PyPI package**, installable via `pip`, `pipx`, or `uv`.
- One primary CLI entry point: `tasksquatch` (with `web`, `tui`, `notify`, `find`, and the CRUD subcommands).
- One separate console entry point for the MCP server: `tasksquatch-mcp`.
- Python 3.12 floor.
- MIT license. Include a `LICENSE` file and standard open-source repo scaffolding (README, etc.).

---

## 13. Explicit non-goals for v1

Do **not** build these in v1. They are deliberately out of scope to keep the surface focused:

- Natural-language date/quick-add parsing (e.g. parsing "tomorrow 5pm" out of a string). Structured fields only; lean on the LLM via MCP for any natural-language interpretation.
- A filter query DSL (Todoist-style `(today | overdue) & #Work`). The fuzzy/fzf workflow and simple structured filters replace it.
- File attachments on comments (text-only comments in v1).
- A separate "deadline" field distinct from the due date.
- Sub-projects / nested projects.
- Phone or push notifications.
- Live cross-process refresh / WebSocket push across surfaces.
- Multi-user support, authentication, accounts, or any cloud sync.

---

## 14. Notes for the implementer (Claude Code)

- **Build `core` first.** Get the data model, business logic, recurrence handling, and the activity log solid and well-tested before building any surface. Every surface depends on it.
- **Testing is yours to design.** This spec intentionally does **not** prescribe a test strategy, coverage target, or tooling. Design and implement the testing approach you judge appropriate for a public, maintainable open-source Python project: choose the test framework, decide what to unit-test in `core` versus contract-test on the REST API versus integration-test across surfaces, and set up linting, formatting, type-checking, and CI as you see fit. Build a genuinely strong, idiomatic quality bar; do not skimp here.
- **Honor the architecture boundary.** Surfaces consume `core`; the MCP server and REST API are siblings. The MCP server must not depend on the REST server running.
- **Concurrency.** Enable WAL mode and make sure concurrent access (TUI + cron + MCP + DataGrip) is safe.
- **Inspiration repos.** The user will share existing repositories at the start of the implementation session (notably a prior project, kanbaroo, with a comparable CLI/TUI/REST/MCP shape over FastAPI + SQLAlchemy + Textual). Draw on their structure and conventions, but follow the decisions in this spec where they differ. In particular, kanbaroo used a central always-on server; tasksquatch deliberately does not, so its cross-process and refresh behavior differs.
- **Open the name for find-and-replace nothing.** The name is settled: `tasksquatch` (package, CLI), `tasksquatch-mcp` (MCP entry point), data at `.../tasksquatch/tasksquatch.db`.
