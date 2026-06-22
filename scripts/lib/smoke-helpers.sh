#!/usr/bin/env bash
# Shared helpers for the scripts/smoke-*.sh suite.
#
# Sourced by each smoke script. Provides PASS/FAIL counters, color-coded
# output (auto-disabled when stdout is not a TTY), tiny assertion
# helpers, and a final tally printer that exits non-zero if any
# assertion failed.

set -euo pipefail

if [[ -t 1 ]]; then
    RED=$'\033[31m'
    GREEN=$'\033[32m'
    YELLOW=$'\033[33m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
else
    RED=""
    GREEN=""
    YELLOW=""
    BOLD=""
    RESET=""
fi

SMOKE_PASS=0
SMOKE_FAIL=0
SMOKE_FAILURES=()

_pass() {
    local msg="$1"
    SMOKE_PASS=$((SMOKE_PASS + 1))
    printf '%s[PASS]%s %s\n' "$GREEN" "$RESET" "$msg"
}

_fail() {
    local msg="$1"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
    SMOKE_FAILURES+=("$msg")
    printf '%s[FAIL]%s %s\n' "$RED" "$RESET" "$msg" >&2
}

_expect_eq() {
    local actual="$1"
    local expected="$2"
    local msg="$3"
    if [[ "$actual" == "$expected" ]]; then
        _pass "$msg"
    else
        _fail "$msg"
        printf '       expected: %q\n' "$expected" >&2
        printf '       actual:   %q\n' "$actual" >&2
    fi
}

_expect_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        _pass "$msg"
    else
        _fail "$msg"
        printf '       expected to contain: %q\n' "$needle" >&2
        printf '       got: %q\n' "${haystack:0:200}" >&2
    fi
}

_expect_status() {
    local actual="$1"
    local expected="$2"
    local msg="$3"
    if [[ "$actual" == "$expected" ]]; then
        _pass "$msg ($actual)"
    else
        _fail "$msg (got $actual, expected $expected)"
    fi
}

_report() {
    local total=$((SMOKE_PASS + SMOKE_FAIL))
    printf '\n%s──────────────────────────────────────%s\n' "$BOLD" "$RESET"
    printf '%sSmoke summary:%s %s%d passed%s, %s%d failed%s (%d total)\n' \
        "$BOLD" "$RESET" \
        "$GREEN" "$SMOKE_PASS" "$RESET" \
        "$RED" "$SMOKE_FAIL" "$RESET" \
        "$total"
    if (( SMOKE_FAIL > 0 )); then
        printf '%sFailures:%s\n' "$BOLD" "$RESET"
        local f
        for f in "${SMOKE_FAILURES[@]}"; do
            printf '  - %s\n' "$f"
        done
        return 1
    fi
    return 0
}

_scratch_db() {
    local name="$1"
    printf '/tmp/tsq-smoke-%s-%d.db' "$name" "$$"
}
