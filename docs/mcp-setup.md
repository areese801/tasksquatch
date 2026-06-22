# Wiring tasksquatch into Claude Code (MCP)

`tasksquatch` ships an MCP server (the `tasksquatch-mcp` console script)
that exposes a curated subset of the `core` API as MCP tools. Pointing
Claude Code at it lets the model create tasks, schedule them, comment
on them, and ask the activity log what happened — all without round
tripping through a network.

The server is **launched on demand by the MCP client**. Nothing runs in
the background between sessions; restart Claude Code and the server
process is recycled.

## Default configuration

Add the entry below to your Claude Code settings (`~/.claude/settings.json`
on macOS/Linux). The default database location follows the standard
XDG fallback (`~/.local/share/tasksquatch/tasksquatch.db`), so no other
configuration is required to share state with the CLI and TUI.

```json
{
  "mcpServers": {
    "tasksquatch": {
      "command": "tasksquatch-mcp"
    }
  }
}
```

## Pointing at a custom database

To run the MCP against a non-default SQLite file (for testing or to
keep a sandbox separate from your main task list), pass
`TASKSQUATCH_DB` in the `env` block. The same variable is honored by
the CLI and TUI, so the surfaces stay in lockstep.

```json
{
  "mcpServers": {
    "tasksquatch": {
      "command": "tasksquatch-mcp",
      "env": {
        "TASKSQUATCH_DB": "/path/to/tasksquatch.db"
      }
    }
  }
}
```

After editing `settings.json`, restart Claude Code so it re-reads the
configuration and spawns a fresh MCP process.

## Permission policy — read this once

> **The MCP surface cannot delete tasks, projects, or labels.**
> Destructive deletion of those entities is reserved for the CLI and
> TUI per `docs/spec.md` §11, so a human is always in the loop for
> irreversible operations.

The MCP **can**:

- Create, read, update, complete, and uncomplete tasks.
- Attach and detach labels on tasks.
- Add, edit, and delete **its own comments** on tasks.
- Create projects and labels.
- List projects and labels.
- Read the activity log.

The MCP **cannot**:

- Delete tasks.
- Delete projects.
- Delete labels.

If you need any of those, drop to the CLI (`tasksquatch task delete
#42`, `tasksquatch project delete`, `tasksquatch label delete`) or use
the TUI.

## Available tools

The full tool set is listed at startup via `tools/list`; each tool's
JSON schema mirrors the keyword arguments documented on the handler in
[`src/tasksquatch/mcp/tools.py`](../src/tasksquatch/mcp/tools.py).

| Tool                      | What it does                                            |
| ------------------------- | ------------------------------------------------------- |
| `add_task`                | Create a task (optional project, parent, labels, RRULE) |
| `update_task`             | Apply a partial update                                  |
| `complete_task`           | Mark complete; advances recurrence in place             |
| `uncomplete_task`         | Reverse completion                                      |
| `list_tasks`              | Filter by project/label/priority/completion/due/parent  |
| `get_task`                | Fetch a task plus its subtasks and comments             |
| `search_tasks`            | Case-insensitive substring search                       |
| `add_comment`             | Attach a comment                                        |
| `edit_comment`            | Replace a comment body                                  |
| `delete_comment`          | Hard-delete a comment (allowed for MCP)                 |
| `add_label_to_task`       | Attach an existing label (by id or name)                |
| `remove_label_from_task`  | Detach a label                                          |
| `create_project`          | Create a new project                                    |
| `create_label`            | Create a new label                                      |
| `list_projects`           | Return every project                                    |
| `list_labels`             | Return every label                                      |
| `read_activity_log`       | Stream the append-only activity log                     |

Tools that accept either an `id` or a `number`/`name` follow a simple
rule: pass the id when you have one (cheaper and unambiguous); pass the
friendly key when you do not.
