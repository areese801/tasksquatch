# Manual test plan — TUI

**Goal.** Confirm every Textual screen renders cleanly, every advertised
keybinding fires the expected action, and the fixes tracked under
TSQ-37 (task detail opening, new-task form completeness, undo cursor
position) stay fixed.

**Time budget.** ~15 minutes.

**Setup.**

- [ ] Build a fresh scratch DB:
      ```bash
      export TASKSQUATCH_DB=/tmp/tsq-manual-tui.db
      rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
      ```
- [ ] Seed a few tasks via the CLI so the screens have content:
      ```bash
      tsq add "Write spec"     -d 2026-07-01 -P P1
      tsq add "Review PR"      -d 2026-07-02 -P P2
      tsq add "Water plants"   -r 'FREQ=DAILY;INTERVAL=3' -a relative
      tsq project add Personal
      tsq add "Buy stamps" -p Personal
      ```
- [ ] Launch the TUI: `tasksquatch tui`

## ProjectListScreen

- [ ] `j` / `k` move the cursor up and down the project list.
- [ ] `enter` opens TaskListScreen for the highlighted project.
- [ ] `n` opens the "create project" prompt; submitting a name adds
      the project to the list.
- [ ] `r` opens the rename prompt; submitting updates the row.
- [ ] `d` on a project that still has tasks raises a friendly
      `ProjectNotEmptyError` (no traceback in the footer).
- [ ] `s` opens SearchScreen.
- [ ] `q` quits the TUI.

## TaskListScreen

- [ ] `enter` opens TaskDetailScreen (regression: see TSQ-37).
- [ ] `/` focuses the filter input.
- [ ] Typing in the filter narrows the visible rows in real time.
- [ ] `esc` clears the filter and restores the full list.
- [ ] `j` / `k` navigate rows.
- [ ] `d` marks the highlighted task done; the row reflects it.
- [ ] `u` reopens it. Cursor stays on the same row (regression: see
      TSQ-37).
- [ ] `x` opens the delete-confirmation dialog; declining leaves the
      row alone; accepting removes it.
- [ ] `c` opens the comment prompt; submitting attaches the comment.
- [ ] `n` opens the new-task form and the form shows **all** fields:
      title, description, project, priority, due date, due time,
      recurrence, anchor, labels (regression: see TSQ-37).
- [ ] `e` opens the edit form pre-populated with the current values.
- [ ] `q` returns to ProjectListScreen.

## TaskDetailScreen

- [ ] Every populated field renders: title, project, priority, due,
      labels, completion state, description, comments.
- [ ] `e` opens the edit modal.
- [ ] `c` opens the comment prompt; the new comment appears in the
      detail panel without re-navigating.
- [ ] `d` toggles complete; `u` reopens; both round-trip cleanly.
- [ ] `x` opens the delete-confirmation dialog.

## TaskEditScreen

- [ ] Title input is editable.
- [ ] Description textarea is editable and accepts newlines.
- [ ] Project select is populated with every project (Inbox + the
      ones seeded above).
- [ ] Priority select carries P1 / P2 / P3 / P4.
- [ ] Due date input accepts `YYYY-MM-DD`.
- [ ] Due time input accepts `HH:MM`.
- [ ] Recurrence input accepts a raw RRULE string.
- [ ] Anchor select carries `fixed` and `relative`.
- [ ] Labels input accepts a comma-separated list of label names.
- [ ] `Tab` walks every field in a sensible order.
- [ ] Save persists changes (re-open the detail to confirm).
- [ ] Cancel discards changes (re-open the detail to confirm).

## SearchScreen

- [ ] Typing a query narrows the results as you type.
- [ ] `enter` on a result opens TaskDetailScreen.

## Pass criteria

- [ ] Zero unexpected tracebacks anywhere in the run.
- [ ] No rendering glitches (overlapping widgets, garbled tables,
      truncated columns without an ellipsis).
- [ ] Every keypress feels instant — response < 1 second.
