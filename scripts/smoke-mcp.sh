#!/usr/bin/env bash
# Smoke test for the tasksquatch-mcp JSON-RPC stdio surface.
#
# Drives the MCP server through a scripted initialize -> tools/list ->
# tools/call sequence and asserts on the protocol envelope, on the
# advertised tool catalog (including the no-delete policy), and on the
# round-trip of add_task / list_tasks.

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/smoke-helpers.sh
source "${_HERE}/lib/smoke-helpers.sh"

if ! command -v jq >/dev/null 2>&1; then
    printf '%s[FAIL]%s jq is required for smoke-mcp.sh\n' "$RED" "$RESET" >&2
    exit 1
fi

DB="$(_scratch_db mcp)"
export TASKSQUATCH_DB="$DB"
rm -f "$DB" "$DB-wal" "$DB-shm"

OUT="$(mktemp -t tsq-smoke-mcp-XXXX.out)"
trap 'rm -f "$DB" "$DB-wal" "$DB-shm" "$OUT"' EXIT

printf '%sMCP smoke against%s tasksquatch-mcp (db=%s)\n\n' "$BOLD" "$RESET" "$DB"

# Drive the MCP server. We tack a `sleep` after the JSON-RPC stream so
# the server has a chance to flush every response before EOF closes its
# stdin and asyncio cancels in-flight handlers.
{
    cat <<'JSON'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"tasksquatch-smoke","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add_task","arguments":{"title":"from mcp"}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"list_tasks","arguments":{}}}
JSON
    sleep 2
} | tasksquatch-mcp >"$OUT" 2>/dev/null

# initialize → result.protocolVersion is a non-empty string
proto="$(jq -r 'select(.id==1) | .result.protocolVersion // empty' "$OUT")"
if [[ -n "$proto" ]]; then
    _pass "initialize returns protocolVersion ($proto)"
else
    _fail "initialize missing protocolVersion"
fi

# tools/list → catalog carries the read/write tools and omits deletes.
tools_json="$(jq -c 'select(.id==2) | .result.tools' "$OUT")"
if [[ -z "$tools_json" || "$tools_json" == "null" ]]; then
    _fail "tools/list returned no tools array"
else
    _pass "tools/list returned a tools array"
    tool_names="$(printf '%s' "$tools_json" | jq -r '.[].name' | sort)"
    for required in add_task list_tasks get_task; do
        if grep -qx "$required" <<<"$tool_names"; then
            _pass "tools/list advertises $required"
        else
            _fail "tools/list missing required tool: $required"
        fi
    done
    for forbidden in delete_task delete_project delete_label; do
        if grep -qx "$forbidden" <<<"$tool_names"; then
            _fail "tools/list unexpectedly advertises $forbidden (no-delete policy violated)"
        else
            _pass "tools/list correctly omits $forbidden"
        fi
    done
fi

# add_task → content[0].text is JSON containing our title.
add_payload="$(jq -r 'select(.id==3) | .result.content[0].text // empty' "$OUT")"
if [[ -n "$add_payload" ]]; then
    add_title="$(printf '%s' "$add_payload" | jq -r '.title // empty')"
    _expect_eq "$add_title" "from mcp" "add_task created a task titled 'from mcp'"
else
    _fail "add_task returned no text content"
fi

# list_tasks → contains the new task.
list_payload="$(jq -r 'select(.id==4) | .result.content[0].text // empty' "$OUT")"
if [[ -n "$list_payload" ]]; then
    if printf '%s' "$list_payload" | jq -e '.items[] | select(.title=="from mcp")' >/dev/null; then
        _pass "list_tasks returns the freshly added task"
    else
        _fail "list_tasks response did not include 'from mcp'"
    fi
else
    _fail "list_tasks returned no text content"
fi

_report
