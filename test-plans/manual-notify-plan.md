# Manual test plan — desktop notifications

**Goal.** Confirm `tsq notify` fires a real desktop banner for a due
task, dedups on re-run, and stops firing when the task is rescheduled
into the future.

**Platform.** macOS only for this plan (Linux/Windows banners use the
same code path but the OS-side authorization story differs — eyeball
them separately if you're shipping for those).

**Time budget.** ~5 minutes.

**Setup.**

- [ ] Build a fresh scratch DB:
      ```bash
      export TASKSQUATCH_DB=/tmp/tsq-manual-notify.db
      rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
      ```

## Steps

- [ ] Add a task due right now:
      ```bash
      tsq add "banner test" -d today -t "$(date +%H:%M)"
      ```
- [ ] Fire the notifier:
      ```bash
      tsq notify
      ```
      A real banner appears, labelled `#1 banner test`.
- [ ] Re-run `tsq notify`. The CLI reports
      `fired 0 notification(s)` (dedup via `last_notified_at`).
- [ ] Push the due date out by a day:
      ```bash
      tsq edit 1 --due tomorrow
      ```
      Running `tsq notify` now fires zero banners (not yet due).
- [ ] Reset the due date back to today and re-run notify; the banner
      fires again.

## Troubleshooting

- No banner appears at all → open **System Settings → Notifications**
  and confirm Terminal (or whichever shell host you launched from)
  is allowed to post notifications.
- The banner shows but immediately disappears → that's a macOS
  banner-vs-alert distinction; `tsq notify` posts banners. Change
  the style in System Settings if you want alerts that stay until
  dismissed.

**Cleanup.**

```bash
rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
```
