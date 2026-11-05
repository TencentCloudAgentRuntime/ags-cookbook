#!/usr/bin/env bash
set -euo pipefail

fail() { echo "ASSERT FAIL: $*" >&2; exit 1; }
assert_eq() { [[ "$1" == "$2" ]] || fail "expected '$2', got '$1'"; }
assert_contains() { grep -Fq "$2" "$1" || fail "$1 does not contain '$2'"; }
assert_not_contains() { ! grep -Fq "$2" "$1" || fail "$1 unexpectedly contains '$2'"; }
assert_matches() { grep -Eq "$2" "$1" || fail "$1 does not match '$2'"; }
assert_not_eq() { [[ "$1" != "$2" ]] || fail "values must differ: '$1'"; }
