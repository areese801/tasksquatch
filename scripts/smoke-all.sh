#!/usr/bin/env bash
# Run every scripts/smoke-*.sh in sequence.
#
# By default, exits on the first failing script so the operator can dig
# in immediately. Set SMOKE_KEEP_GOING=1 to run the whole suite even
# when individual scripts fail (useful when triaging a release before
# tagging).

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/smoke-helpers.sh
source "${_HERE}/lib/smoke-helpers.sh"

KEEP_GOING="${SMOKE_KEEP_GOING:-0}"
SCRIPTS=(
    "${_HERE}/smoke-cli.sh"
    "${_HERE}/smoke-web.sh"
    "${_HERE}/smoke-mcp.sh"
)

TOTAL_PASS=0
TOTAL_FAIL=0
FAILED_SCRIPTS=()

for script in "${SCRIPTS[@]}"; do
    name="$(basename "$script")"
    printf '\n%s================ %s ================%s\n' "$BOLD" "$name" "$RESET"
    if "$script"; then
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
        FAILED_SCRIPTS+=("$name")
        if [[ "$KEEP_GOING" != "1" ]]; then
            printf '\n%s[abort]%s %s failed; rerun with SMOKE_KEEP_GOING=1 to continue.\n' \
                "$RED" "$RESET" "$name" >&2
            exit 1
        fi
    fi
done

printf '\n%s──────────────────────────────────────%s\n' "$BOLD" "$RESET"
printf '%sAll-suite summary:%s %d script(s) passed, %d failed\n' \
    "$BOLD" "$RESET" "$TOTAL_PASS" "$TOTAL_FAIL"
if (( TOTAL_FAIL > 0 )); then
    for s in "${FAILED_SCRIPTS[@]}"; do
        printf '  - %s\n' "$s"
    done
    exit 1
fi
