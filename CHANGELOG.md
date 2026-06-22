# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-22

### Added
- Core: SQLAlchemy 2.x data model + Alembic migrations + activity
  log + RRULE recurrence (fixed + relative anchors).
- CLI: 14 commands (add/list/show/done/undo/edit/rm/move/comment +
  project + label sub-apps + find via fzf + tui + web + notify +
  version).
- TUI: project list, task list with rapidfuzz filter, task detail,
  create/edit form, global search.
- REST API (FastAPI): full CRUD over tasks/projects/labels/comments
  + activity log read, mounted at /api/v1, loopback-only.
- Web UI: server-rendered HTMX dashboard at /ui (no SPA).
- MCP server: tasksquatch-mcp stdio server with 17 coarse-grained
  tools and a no-entity-delete permission guard.
- Notifications: tasksquatch notify, with desktop-notifier wrapper,
  last_notified_at dedup, configurable lead time + day_of_time,
  cron/launchd/systemd recipes in docs/notifications.md.

[0.1.0]: https://github.com/areese801/tasksquatch/releases/tag/v0.1.0
