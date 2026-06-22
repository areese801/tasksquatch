# Manual test plan — Claude Code MCP integration

**Goal.** Confirm that the `tasksquatch-mcp` server, wired into a real
Claude Code session via `~/.claude/settings.json`, can create and
complete tasks — and that the no-delete policy is enforced when the
model is asked to remove one.

**Prereq.** Claude Code installed.

**Time budget.** ~10 minutes.

**Setup.**

- [ ] Paste the `mcpServers` block from `docs/mcp-setup.md` into
      `~/.claude/settings.json`. The minimal entry is:
      ```json
      {
        "mcpServers": {
          "tasksquatch": {
            "command": "tasksquatch-mcp"
          }
        }
      }
      ```
- [ ] Optional: set a dedicated DB so this session doesn't pollute
      your day-to-day store. Add an `env` block to the entry:
      ```json
      "env": { "TASKSQUATCH_DB": "/tmp/tsq-manual-mcp.db" }
      ```
      Mirror it in your host shell so `tsq` reads the same file:
      ```bash
      export TASKSQUATCH_DB=/tmp/tsq-manual-mcp.db
      ```
- [ ] Restart Claude Code so it re-reads `settings.json`.

## Steps

- [ ] In a Claude Code session, ask:
      > Add a task to buy milk.
- [ ] On the host, run `tsq list` and confirm a new task with the
      title "buy milk" (or similar) is present.
- [ ] Ask Claude:
      > Delete that task.
- [ ] Claude reports that the MCP refused the call (no-delete policy
      — the surface advertises no `delete_task` tool, so the model
      should either say so or attempt and surface the error).
- [ ] Ask Claude:
      > Mark it complete.
- [ ] On the host, run `tsq list --completed done` and confirm the
      task is now in the completed view.

## Cleanup

- [ ] If you used a scratch DB: `rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm`.
- [ ] Remove or revert the `mcpServers.tasksquatch` block in
      `~/.claude/settings.json` if you don't want it active outside
      this test.
