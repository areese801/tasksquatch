# Manual test plan — Web UI

**Goal.** Eyeball the HTMX dashboard end-to-end: confirm partial
swaps land without a full reload, the form flow round-trips, and the
auto-generated `/docs` OpenAPI page renders.

**Time budget.** ~10 minutes.

**Setup.**

- [ ] Build a fresh scratch DB and start the server:
      ```bash
      export TASKSQUATCH_DB=/tmp/tsq-manual-web.db
      rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
      tsq web --port 18000
      ```
- [ ] Open <http://127.0.0.1:18000/ui> in a real browser.

## Dashboard

- [ ] Sidebar lists Inbox plus any other seeded projects.
- [ ] Clicking a project name updates the task list without a full
      page reload (no flash; address bar unchanged or only the query
      string changes).
- [ ] Clicking a task title populates the detail panel on the right
      without a full reload.
- [ ] Submitting the new-task form adds a row to the task list
      immediately.
- [ ] Clicking the complete-toggle button on a row visually marks it
      completed (strikethrough or similar).
- [ ] Clicking the delete button triggers the `hx-confirm` dialog;
      confirming removes the row.
- [ ] Opening the edit form on a row pre-fills the current values;
      saving reflects them in the row.

## OpenAPI

- [ ] <http://127.0.0.1:18000/docs> renders the FastAPI Swagger UI.
- [ ] The endpoints under `tasks`, `projects`, `labels`, `comments`,
      and `activity` are all visible.

## Accessibility spot-check

- [ ] `Tab` walks through the page in a sensible focus order.
- [ ] Every input has a visible (or `<label>`-associated) label.

**Cleanup.** Stop the server (`Ctrl-C`) and remove the scratch DB:

```bash
rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
```
