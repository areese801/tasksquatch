#!/usr/bin/env bash
# End-to-end smoke for the tasksquatch CLI surface.
#
# Drives the installed `tsq` console script against a scratch SQLite
# database, asserting that every advertised subcommand works and that
# the friendlier error paths (e.g. ProjectNotEmptyError) surface a
# helpful message rather than a traceback.

# The tsq CLI uses `done` and `undo` as task-lifecycle subcommand
# names; shellcheck mistakes the literal `done` argument for a shell
# loop terminator and emits spurious SC1010 warnings. The names are
# part of the user-facing UX, so disable that single check
# script-wide rather than rewriting every invocation.
# shellcheck disable=SC1010

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/smoke-helpers.sh
source "${_HERE}/lib/smoke-helpers.sh"

DB="$(_scratch_db cli)"
export TASKSQUATCH_DB="$DB"
rm -f "$DB" "$DB-wal" "$DB-shm"
trap 'rm -f "$DB" "$DB-wal" "$DB-shm"' EXIT

printf '%sCLI smoke against%s %s\n\n' "$BOLD" "$RESET" "$DB"

# 1. version
out="$(tsq version 2>&1)"
_expect_eq "$out" "0.1.0" "tsq version returns 0.1.0"

# 2. project ls (fresh DB seeds Inbox lazily)
out="$(tsq project ls 2>&1)"
_expect_contains "$out" "Inbox" "tsq project ls shows the Inbox"

# 3. add a priority/dated task
out="$(tsq add "Buy milk" -d 2026-07-01 -P P1 2>&1)"
_expect_contains "$out" "#1" "tsq add returns the new task number"
_expect_contains "$out" "Buy milk" "tsq add echoes the task title"

# 4. add a recurring relative task (no due is fine for RELATIVE)
out="$(tsq add "Water plants" -r 'FREQ=DAILY;INTERVAL=3' -a relative 2>&1)"
_expect_contains "$out" "#2" "tsq add creates a recurring task"

# 5. add a task with a description
out="$(tsq add "Write report" --desc "Q3 numbers" 2>&1)"
_expect_contains "$out" "#3" "tsq add accepts --desc"

# 6. list — should carry all three titles
out="$(tsq list 2>&1)"
_expect_contains "$out" "Buy milk" "tsq list shows task #1"
_expect_contains "$out" "Water plants" "tsq list shows task #2"
_expect_contains "$out" "Write report" "tsq list shows task #3"

# 7. list --completed=open hides the completed column
out="$(tsq list --completed open 2>&1)"
if [[ "$out" != *completed* ]]; then
    _pass "tsq list --completed=open drops the completed column"
else
    _fail "tsq list --completed=open still shows the completed column"
fi

# 8. show
out="$(tsq show 1 2>&1)"
_expect_contains "$out" "Buy milk" "tsq show #1 carries the title"
_expect_contains "$out" "P1" "tsq show #1 carries the priority"
_expect_contains "$out" "2026-07-01" "tsq show #1 carries the due date"

# 9. done
out="$(tsq done 1 2>&1)"
_expect_contains "$out" "completed" "tsq done reports completion"

# 10. list --completed=done now contains the task
out="$(tsq list --completed done 2>&1)"
_expect_contains "$out" "Buy milk" "tsq list --completed=done includes #1"

# 11. list --completed=open no longer contains it
out="$(tsq list --completed open 2>&1)"
if [[ "$out" != *"Buy milk"* ]]; then
    _pass "tsq list --completed=open hides completed task"
else
    _fail "tsq list --completed=open still shows completed task"
fi

# 12. undo
out="$(tsq undo 1 2>&1)"
_expect_contains "$out" "#1" "tsq undo reopens task #1"

# 13. recurring complete advances in place
out="$(tsq done 2 2>&1)"
if [[ "$out" == *"advanced to"* ]] || [[ "$out" == *"-"* && "$out" == *":"* ]]; then
    _pass "tsq done on recurring task advances to the next occurrence"
else
    _fail "tsq done on recurring task should mention the next occurrence (got: $out)"
fi

# 14. comment
out="$(tsq comment 3 "remember to forecast" 2>&1)"
_expect_contains "$out" "#3" "tsq comment confirms the target task"

# 15. show carries the comment
out="$(tsq show 3 2>&1)"
_expect_contains "$out" "remember to forecast" "tsq show surfaces the comment"

# 16. project add / ls
out="$(tsq project add Personal 2>&1)"
_expect_contains "$out" "Personal" "tsq project add reports the new project"
out="$(tsq project ls 2>&1)"
_expect_contains "$out" "Personal" "tsq project ls includes the new project"

# 17. move
out="$(tsq move 3 Personal 2>&1)"
_expect_contains "$out" "Personal" "tsq move reports the destination project"

# 18. project rm fails with friendly error while not empty
set +e
out="$(tsq project rm Personal --yes 2>&1)"
status=$?
set -e
if (( status != 0 )) && [[ "$out" == *"still has"* || "$out" == *"not empty"* ]]; then
    _pass "tsq project rm refuses non-empty projects with a friendly message"
else
    _fail "tsq project rm should refuse non-empty projects (status=$status, out=$out)"
fi

# 19. move back to Inbox then rm again
out="$(tsq move 3 Inbox 2>&1)"
_expect_contains "$out" "Inbox" "tsq move accepts the Inbox as a destination"
out="$(tsq project rm Personal --yes 2>&1)"
_expect_contains "$out" "Personal" "tsq project rm succeeds once the project is empty"

# 20. labels
out="$(tsq label add Home 2>&1)"
_expect_contains "$out" "Home" "tsq label add reports the new label"
out="$(tsq label ls 2>&1)"
_expect_contains "$out" "Home" "tsq label ls includes the new label"
out="$(tsq label rm Home --yes 2>&1)"
_expect_contains "$out" "Home" "tsq label rm confirms the deletion"

# 21. reschedule-overdue
out="$(tsq add "ancient" -d 2020-01-01 2>&1)"
_expect_contains "$out" "ancient" "tsq add seeds an overdue task"
ancient_number="${out##*#}"
ancient_number="${ancient_number%%:*}"

out="$(tsq reschedule-overdue --dry-run --yes 2>&1)"
_expect_contains "$out" "ancient" "tsq reschedule-overdue --dry-run mentions the overdue task"
_expect_contains "$out" "would bump" "tsq reschedule-overdue --dry-run announces no writes"

out="$(tsq show "$ancient_number" 2>&1)"
_expect_contains "$out" "2020-01-01" "tsq reschedule-overdue --dry-run did not write to the DB"

out="$(tsq reschedule-overdue --yes 2>&1)"
_expect_contains "$out" "bumped" "tsq reschedule-overdue --yes confirms the bump"

today="$(date +%Y-%m-%d)"
out="$(tsq show "$ancient_number" 2>&1)"
_expect_contains "$out" "$today" "tsq reschedule-overdue moved the overdue task to today"

_report
