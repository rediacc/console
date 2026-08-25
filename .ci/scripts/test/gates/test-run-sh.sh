#!/usr/bin/env bash
# Controls for ./run.sh -- the entry point every other command goes through.
#
# It had no test of its own, and two defects lived in it because of that:
#
#   1. `quality all` logged a warning and returned SUCCESS when shfmt was
#      missing, so on any machine without shfmt -- every non-Debian host, and
#      this one until someone hand-installed it -- the command reported green
#      having run no shell gate at all.
#   2. `fix shell` formatted with whatever shfmt was on PATH while the gate
#      verified with the pinned one, so the fixer could produce a state the
#      checker rejects.
#
# HERMETIC BY CONSTRUCTION: no docker, no network, no submodules. Every case is
# either a dispatch assertion or a source-level invariant, so this runs in the
# bare-checkout CI lane. What it deliberately does NOT do is run a real gate --
# that is what the gates themselves are for.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
RUN="$ROOT/run.sh"

fails=0
count=0
ok() {
    count=$((count + 1))
    echo "PASS: $1"
}
no() {
    count=$((count + 1))
    fails=$((fails + 1))
    echo "FAIL: $1" >&2
}
exits() { # exits <label> <want> <args...>
    local label="$1" want="$2"
    shift 2
    local got
    (cd "$ROOT" && "$RUN" "$@" >/dev/null 2>&1)
    got=$?
    if [[ "$got" == "$want" ]]; then ok "$label (exit $got)"; else no "$label (exit $got, want $want)"; fi
}

# --- 1. dispatch: an unknown verb must not look like success -----------------
exits "an unknown verb fails" 1 definitely-not-a-verb
exits "an unknown devbox subcommand fails" 1 devbox not-a-real-subcommand
exits "help succeeds" 0 help
exits "devbox exec with no command fails" 1 devbox exec --

# --- 2. THE VACUOUS GREEN. A gate that cannot run must not report success. ----
# CODE ONLY. An earlier draft grepped a fixed window and matched the word
# `log_warn` inside the COMMENT that explains the old behaviour -- the test
# failed on correct code, which is the wrong direction for a control to fail in.
body() { # body <file> <function-name>  -> the function's body, comments stripped
    awk -v fn="$2" '
        $0 ~ "^" fn "\\(\\) \\{" { inside = 1; next }
        inside && /^}/ { exit }
        inside { sub(/^[[:space:]]*#.*$/, ""); print }
    ' "$1"
}

QA="$(body "$RUN" quality_all)"
if printf '%s' "$QA" | grep -q 'log_warn'; then
    no "CONTROL: quality_all warns and falls through when shfmt is absent (the vacuous green is back)"
else
    ok "quality_all does not warn-and-continue when shfmt is unusable"
fi
if printf '%s' "$QA" | grep -q 'return 1'; then
    ok "quality_all returns non-zero when the shell gates cannot run"
else
    no "quality_all has no failure path when the shell gates cannot run"
fi

# --- 3. fix and check must use the SAME binary -------------------------------
if grep -A 12 '^fix_shell()' "$RUN" | grep -q 'toolchain_acquire shfmt'; then
    ok "fix shell formats with the pinned binary, the one the gate verifies with"
else
    no "fix shell takes shfmt from PATH; it can format into a state the gate rejects"
fi
if grep -A 20 '^fix_shell()' "$RUN" | grep -qE '^\s+(find [^|]*-exec |")shfmt'; then
    no "CONTROL: fix_shell still calls a bare shfmt somewhere"
else
    ok "CONTROL: no bare shfmt invocation survives in fix_shell"
fi

# --- 4. the gate lane ---------------------------------------------------------
# shellcheck source=/dev/null
. "$ROOT/.ci/config/constants.sh" 2>/dev/null
# shellcheck source=/dev/null
. "$ROOT/.ci/lib/local-common.sh" 2>/dev/null

lane() { (cd "$ROOT" && env "$@" bash -c '. .ci/config/constants.sh; . .ci/scripts/lib/toolchain.sh; . .ci/lib/local-common.sh; gate_lane_decide') 2>/dev/null; }

[[ "$(lane REDIACC_IN_DEVBOX=1)" == host ]] &&
    ok "inside the container the lane is 'host' (breaks the re-exec recursion)" ||
    no "REDIACC_IN_DEVBOX did not force the host lane -- routing would recurse"
[[ "$(lane REDIACC_LANE=host)" == host ]] &&
    ok "REDIACC_LANE=host is honoured (the documented opt-out)" ||
    no "the host opt-out is not honoured"
[[ "$(lane REDIACC_LANE=devbox)" == devbox ]] &&
    ok "REDIACC_LANE=devbox is honoured" ||
    no "an explicit devbox lane is not honoured"

# A routed verb must not silently degrade: if it cannot route, it says so.
if body "$ROOT/.ci/lib/local-common.sh" gate_lane_should_route | grep -qE 'log_warn|log_error'; then
    ok "a lane that cannot route reports it rather than degrading silently"
else
    no "CONTROL: routing can fail silently, which is the failure this design exists to prevent"
fi

# --- 5. run.sh must be runnable at all ----------------------------------------
if bash -n "$RUN" 2>/dev/null; then ok "run.sh parses"; else no "run.sh does not parse"; fi
if [[ -x "$RUN" ]]; then ok "run.sh is executable"; else no "run.sh is not executable"; fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "✓ run.sh: $count control(s) passed"
    exit 0
fi
echo "✗ run.sh: $fails of $count control(s) failed" >&2
exit 1
