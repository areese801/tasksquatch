# Notifications

`tasksquatch` ships a single short-lived command — `tasksquatch notify`
— that scans the database for tasks that are due, fires one desktop
notification per task, and stamps `last_notified_at` so the next pass
deduplicates correctly. There is no daemon, no background loop, and no
always-on service: the user is expected to schedule `tasksquatch
notify` through the host's native scheduler (cron, launchd, or
systemd). This matches the project's offline-first, no-server design
(see [`spec.md`](spec.md) §6).

The command exits 0 with a one-line summary on success:

```
$ tasksquatch notify
fired 0 notification(s).
```

## Configuration

Two knobs control timing. Both have safe defaults and need not be set.

| Field          | Default | What it does                                                                                   |
| -------------- | ------- | ---------------------------------------------------------------------------------------------- |
| `lead_seconds` | `0`     | Seconds before the scheduled moment that a notification may fire. `0` fires at or after only. |
| `day_of_time`  | `09:00` | Wall-clock time used for date-only tasks. A date-only task never silently fires at midnight.   |

Precedence (highest first): environment variables → `[notify]` section
in the TOML config → defaults.

### TOML config file

`~/.config/tasksquatch/config.toml` (or
`$XDG_CONFIG_HOME/tasksquatch/config.toml` when set):

```toml
[notify]
lead_seconds = 900
day_of_time = "08:30"
```

A missing file is **not** an error — defaults apply.

### Environment variables

```sh
export TASKSQUATCH_NOTIFY_LEAD_SECONDS=900
export TASKSQUATCH_NOTIFY_DAY_OF_TIME=08:30
```

Invalid values (a non-integer lead, an `HH:MM` string that does not
parse) cause the command to fail with a validation error instead of
firing notifications with surprising semantics.

## Scheduling recipes

The recipes below all run the notifier every five minutes. Use any
interval that suits you — every minute is fine; every hour is fine —
but match `lead_seconds` to the interval so a notification has time to
fire before its scheduled moment slides past.

### macOS — cron

```cron
*/5 * * * * /Users/you/.local/bin/tasksquatch notify >> ~/.tasksquatch/notify.log 2>&1
```

> **Permissions:** modern macOS does not grant cron access to the
> Notification Center by default. Either give `cron` Full Disk Access in
> *System Settings → Privacy & Security → Full Disk Access*, or — far
> easier — use the launchd recipe below.

### macOS — launchd (recommended)

Drop the following at
`~/Library/LaunchAgents/com.areese.tasksquatch.notify.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.areese.tasksquatch.notify</string>
    <key>ProgramArguments</key>
    <array>
      <string>/Users/you/.local/bin/tasksquatch</string>
      <string>notify</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/you/.tasksquatch/notify.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/you/.tasksquatch/notify.log</string>
  </dict>
</plist>
```

Install it:

```sh
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.areese.tasksquatch.notify.plist
```

To stop the agent later:

```sh
launchctl bootout gui/$UID/com.areese.tasksquatch.notify
```

### Linux — systemd user timer

`~/.config/systemd/user/tasksquatch-notify.service`:

```ini
[Unit]
Description=tasksquatch desktop notification pass

[Service]
Type=oneshot
ExecStart=%h/.local/bin/tasksquatch notify
```

`~/.config/systemd/user/tasksquatch-notify.timer`:

```ini
[Unit]
Description=Fire tasksquatch notifications every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=tasksquatch-notify.service

[Install]
WantedBy=timers.target
```

Enable and start:

```sh
systemctl --user daemon-reload
systemctl --user enable --now tasksquatch-notify.timer
```

## Verifying it works

Create a task due one minute from now and run the command by hand:

```sh
tasksquatch add "ping" --due-date "$(date +%Y-%m-%d)" --due-time "$(date -d '+1 minute' +%H:%M)"
sleep 60
tasksquatch notify
```

The desktop should show one notification and the command should print
`fired 1 notification(s).` A second invocation in the same minute
prints `fired 0 notification(s).` — the per-occurrence dedup is
working.
