#!/usr/bin/env bash
# REST + Web UI smoke test against a freshly launched tasksquatch server.
#
# Boots `tasksquatch web` on a scratch DB and an isolated port, polls
# `/healthz` until it responds, then exercises a representative slice
# of the REST and HTMX endpoints. The server is torn down on exit.

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/smoke-helpers.sh
source "${_HERE}/lib/smoke-helpers.sh"

PORT="${PORT:-18080}"
BASE="http://127.0.0.1:${PORT}"
DB="$(_scratch_db web)"
export TASKSQUATCH_DB="$DB"
rm -f "$DB" "$DB-wal" "$DB-shm"

LOG="$(mktemp -t tsq-smoke-web-XXXX.log)"
tasksquatch web --port "$PORT" >"$LOG" 2>&1 &
PID=$!

cleanup() {
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
    rm -f "$DB" "$DB-wal" "$DB-shm" "$LOG"
}
trap cleanup EXIT

printf '%sWeb smoke against%s %s (db=%s)\n\n' "$BOLD" "$RESET" "$BASE" "$DB"

# Poll /healthz until the server answers or we time out.
deadline=$((SECONDS + 10))
ready=0
while (( SECONDS < deadline )); do
    if curl -sf "${BASE}/healthz" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.2
done
if (( ready != 1 )); then
    _fail "server failed to come up within 10s"
    printf '%sServer log:%s\n' "$YELLOW" "$RESET" >&2
    cat "$LOG" >&2
    _report
    exit 1
fi
_pass "server is reachable on $BASE"

# /healthz
body="$(curl -s "${BASE}/healthz")"
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/healthz")"
_expect_status "$status" "200" "GET /healthz"
_expect_contains "$body" '"status":"ok"' "/healthz body matches"

# /api/v1/projects
body="$(curl -s "${BASE}/api/v1/projects")"
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/api/v1/projects")"
_expect_status "$status" "200" "GET /api/v1/projects"
_expect_contains "$body" "Inbox" "projects list includes Inbox"
INBOX_ID="$(printf '%s' "$body" | jq -r '.items[] | select(.is_inbox==true) | .id')"
if [[ -n "$INBOX_ID" && "$INBOX_ID" != "null" ]]; then
    _pass "extracted Inbox id ($INBOX_ID)"
else
    _fail "could not extract Inbox id from /api/v1/projects"
fi

# POST /api/v1/tasks
tmp_out="$(mktemp)"
status="$(curl -s -o "$tmp_out" -w "%{http_code}" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"title":"from curl"}' \
    "${BASE}/api/v1/tasks")"
body="$(cat "$tmp_out")"
rm -f "$tmp_out"
_expect_status "$status" "201" "POST /api/v1/tasks"
_expect_contains "$body" "from curl" "created task echoes title"
TASK_ID="$(printf '%s' "$body" | jq -r '.id')"
if [[ -n "$TASK_ID" && "$TASK_ID" != "null" ]]; then
    _pass "extracted new task id"
else
    _fail "could not extract new task id"
fi

# GET /api/v1/tasks/by-number/1
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/api/v1/tasks/by-number/1")"
body="$(curl -s "${BASE}/api/v1/tasks/by-number/1")"
_expect_status "$status" "200" "GET /api/v1/tasks/by-number/1"
_expect_contains "$body" "from curl" "by-number lookup returns the task"

# PATCH /api/v1/tasks/<id>
tmp_out="$(mktemp)"
status="$(curl -s -o "$tmp_out" -w "%{http_code}" -X PATCH \
    -H 'Content-Type: application/json' \
    -d '{"priority":"P2"}' \
    "${BASE}/api/v1/tasks/${TASK_ID}")"
body="$(cat "$tmp_out")"
rm -f "$tmp_out"
_expect_status "$status" "200" "PATCH /api/v1/tasks/<id>"
_expect_contains "$body" '"P2"' "patched task carries the new priority"

# POST /api/v1/tasks/<id>/complete
tmp_out="$(mktemp)"
status="$(curl -s -o "$tmp_out" -w "%{http_code}" -X POST \
    -H 'Content-Type: application/json' \
    -d '{}' \
    "${BASE}/api/v1/tasks/${TASK_ID}/complete")"
body="$(cat "$tmp_out")"
rm -f "$tmp_out"
_expect_status "$status" "200" "POST /api/v1/tasks/<id>/complete"
_expect_contains "$body" '"completed":true' "task reports completed=true"

# GET /api/v1/activity
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/api/v1/activity")"
body="$(curl -s "${BASE}/api/v1/activity")"
_expect_status "$status" "200" "GET /api/v1/activity"
_expect_contains "$body" '"completed"' "activity log has a completed event"

# GET /ui
ui_headers="$(mktemp)"
status="$(curl -sL -o "$ui_headers" -w "%{http_code}" "${BASE}/ui")"
content_type="$(curl -sL -o /dev/null -D - "${BASE}/ui" | awk 'tolower($1)=="content-type:" {print $2}' | tr -d '\r' | head -n 1)"
ui_body="$(cat "$ui_headers")"
rm -f "$ui_headers"
_expect_status "$status" "200" "GET /ui"
_expect_contains "$content_type" "text/html" "/ui content-type is text/html"
_expect_contains "$ui_body" "<html" "/ui body looks like a full HTML page"

# GET /ui/projects/<inbox_id> — partial, no <html>
partial="$(curl -sL "${BASE}/ui/projects/${INBOX_ID}")"
status="$(curl -sL -o /dev/null -w "%{http_code}" "${BASE}/ui/projects/${INBOX_ID}")"
_expect_status "$status" "200" "GET /ui/projects/<inbox_id>"
if [[ "$partial" != *"<html"* ]]; then
    _pass "project partial is a fragment (no <html>)"
else
    _fail "project partial unexpectedly carries <html>"
fi

# Static assets
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/static/htmx.min.js")"
_expect_status "$status" "200" "GET /static/htmx.min.js"
status="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/static/style.css")"
_expect_status "$status" "200" "GET /static/style.css"

_report
