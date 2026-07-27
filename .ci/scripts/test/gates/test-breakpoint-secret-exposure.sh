#!/bin/bash
# Gate: breakpoint must never route an access credential through a step `env:`.
#
# WHY THIS GATE EXISTS -- it is a regression test for a live leak, not a
# hypothetical. Run 30254567365 (public repo, email channel, 2026-07-27) sent
# the access email correctly AND published the tunnel URL in cleartext:
#
#   09:39:32.5205053Z   BP_URL: https://program-explore-lucia-graduated.trycloudflare.com
#   09:39:36.1644525Z ✓ access details emailed to muhammed@rediacc.com
#
# The runner prints a step's `env:` block BEFORE the step's script runs, and
# `::add-mask::` only redacts occurrences that appear AFTER it registers. So
# `env: BP_URL: ${{ steps.tunnel.outputs.url }}` published the URL roughly four
# seconds before publish-endpoints.sh could mask it. The email channel is the
# DEFAULT precisely because a quick-mode URL is a bearer credential to a box
# holding the repo source and (with debug-shell) an interactive shell -- so the
# leak defeated the entire control while every step still reported success.
#
# No other gate can see this: it is a property of the workflow YAML's data flow,
# invisible to shellcheck, shfmt, check-commands and the drift manifest (which
# proves the file is UNCHANGED, not that it is CORRECT).
#
# The fix, which this gate pins: credentials reach publish-endpoints.sh through
# the session state file, which never touches the log.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"
BP="$REPO_ROOT/.ci/breakpoint"
WORKFLOW="$BP/workflow/breakpoint.yml"
LIVE_WORKFLOW="$REPO_ROOT/.github/workflows/breakpoint.yml"

# The expressions that resolve to an access credential. Each one is a value a
# human can use to reach the running box.
CREDENTIAL_EXPRESSIONS=(
    "steps.tunnel.outputs.url"
    "steps.shell.outputs.ssh-connection"
    "steps.shell.outputs.web-url"
    "steps.shell.outputs.ssh-ro-connection"
    "steps.shell.outputs.web-ro-url"
)

# =============================================================================
# a) no credential expression appears anywhere in the workflow
# =============================================================================
# Deliberately whole-file rather than scoped to `env:` blocks. A credential has
# no legitimate use in workflow text at all: `run:` interpolation is already
# banned as script injection, and `env:` is this leak. Whole-file is both
# stricter and simpler to reason about than a YAML-aware env-block parse.
# The detector, factored out so the gate can be pointed at a deliberately
# broken copy of itself. Returns 1 when a credential expression is present.
detect_credential_exposure() {
    local file="$1" expr hits found=0
    for expr in "${CREDENTIAL_EXPRESSIONS[@]}"; do
        hits="$(grep -n -F "$expr" "$file" || true)"
        if [[ -n "$hits" ]]; then
            printf 'ERROR: %s\n' "credential expression '$expr' appears in $WORKFLOW:" >&2
            printf 'ERROR: %s\n' "$hits" >&2
            printf 'ERROR: %s\n' "the runner prints env: blocks BEFORE the step runs, so this" >&2
            printf 'ERROR: %s\n' "value is published to the log before it can be masked." >&2
            printf 'ERROR: %s\n' "pass it through the session state file instead (bp_state_set/get)." >&2
            found=1
        fi
    done
    return "$found"
}

test_no_credential_expression_in_workflow() {
    [[ -f "$WORKFLOW" ]] || log_fail "workflow template is missing: $WORKFLOW"
    detect_credential_exposure "$WORKFLOW" || log_fail "workflow routes access credentials through the log"
    log_pass "no access credential is interpolated into the workflow (${#CREDENTIAL_EXPRESSIONS[@]} expressions checked)"
}

# =============================================================================
# b) prove the detector FIRES (anti-vacuity, by mutation not by assertion)
# =============================================================================
# A gate that has only ever been seen to pass has not been verified. This
# reconstructs the exact line that leaked in run 30254567365, points the
# detector at it, and asserts it trips. If someone weakens the expression list
# or the grep, THIS check goes red rather than the gate going quietly blind.
#
# It also removes the trap the first version of this check fell into: asserting
# the guarded output names still exist in the scripts. After the fix they
# legitimately do not exist -- the whole point is that nothing emits them any
# more -- so that check failed on a correct tree and would have been "fixed" by
# deleting it.
test_detector_fires_on_the_real_leak() {
    local temp="$1"
    local broken="$temp/leaky-breakpoint.yml"

    cp "$WORKFLOW" "$broken"
    # verbatim shape of the line that leaked, reinstated
    printf '          BP_URL: ${{ steps.tunnel.outputs.url }}\n' >>"$broken"

    if detect_credential_exposure "$broken" 2>/dev/null; then
        log_fail "detector did NOT fire on a workflow containing the exact line that leaked in run 30254567365 -- this gate is blind"
    fi
    log_pass "detector fires on the reinstated leak line (proven by mutation, not asserted)"
}

# =============================================================================
# c) publish-endpoints.sh sources the URL from state
# =============================================================================
test_publish_reads_state() {
    local script="$BP/scripts/publish-endpoints.sh"
    [[ -f "$script" ]] || log_fail "missing $script"

    assert_contains "$(cat "$script")" 'bp_state_get BP_PUBLIC_URL' \
        "publish-endpoints.sh must read the URL from session state, not from env"
    log_pass "publish-endpoints.sh reads the URL from the session state file"
}

# =============================================================================
# d) start-shell.sh does not mask unconditionally
# =============================================================================
# The first version of this feature masked the tmate strings the moment they
# were created. Masking is irreversible within a run, so on the logs channel the
# operator got "SSH: ***" -- a shell nobody could reach. Same rule as the URL,
# opposite direction: never mask without a working alternative channel, and
# never publish without one either. publish-endpoints.sh owns both decisions
# because it is the only thing that knows which channel is live.
test_shell_does_not_mask_unconditionally() {
    local script="$BP/scripts/start-shell.sh"
    [[ -f "$script" ]] || log_fail "missing $script"

    if grep -qE '^\s*\[\[ -n "\$s" \]\] && bp_gha_mask' "$script"; then
        log_fail "start-shell.sh masks connection strings unconditionally; the logs channel then prints '***' and the session is unreachable"
    fi
    log_pass "start-shell.sh leaves the masking decision to publish-endpoints.sh"
}

# =============================================================================
# e) template and live workflow agree
# =============================================================================
# The leak was fixed in the template; if the copy under .github/workflows/ is
# stale, the fix is not deployed and the next dispatch leaks again.
test_live_workflow_matches_template() {
    if [[ ! -f "$LIVE_WORKFLOW" ]]; then
        log_pass "no live workflow copy in this repo (template-only checkout)"
        return
    fi
    if ! cmp -s "$WORKFLOW" "$LIVE_WORKFLOW"; then
        printf 'ERROR: %s\n' "$(diff "$WORKFLOW" "$LIVE_WORKFLOW" || true)" >&2
        log_fail ".github/workflows/breakpoint.yml differs from the template; the fix may not be deployed"
    fi
    log_pass "live workflow is byte-identical to the template"
}

# =============================================================================
# f) workflow commands must never touch STDOUT
# =============================================================================
# bp_gha_mask/bp_gha_warning emit `::add-mask::` / `::warning::` lines. Several
# scripts here have a stdout DATA CONTRACT (start-tunnel.sh prints exactly one
# line, the URL, and the workflow does `URL=$(start-tunnel.sh ...)`), so a
# workflow command on stdout is CAPTURED INTO the value. That killed the first
# real named-mode run after it had already created the tunnel, DNS record and
# Access app:
#
#   ##[error]Invalid format 'https://rdc-ci-30258284234.rediacc.io'
#
# GITHUB_ACTIONS=true is the load-bearing part of this test. Both helpers no-op
# without it, so the identical check run locally passes while the bug is fully
# present -- which is exactly how it reached CI.
test_workflow_commands_never_hit_stdout() {
    local temp="$1" out err
    local lib="$BP/lib/breakpoint-common.sh"

    out="$temp/out"
    err="$temp/err"
    (
        set +e
        # shellcheck source=/dev/null
        GITHUB_ACTIONS=true bash -c "source '$lib'; bp_gha_mask 'sup3rs3cret'; bp_gha_warning 'careful'" \
            >"$out" 2>"$err"
    )

    if [[ -s "$out" ]]; then
        printf 'ERROR: %s\n' "stdout was: $(cat "$out")" >&2
        log_fail "bp_gha_mask/bp_gha_warning wrote to STDOUT; any \$(...) capture of a script using them is corrupted"
    fi
    log_pass "workflow commands stay off stdout under GITHUB_ACTIONS=true"

    # ...and they must still be EMITTED, or masking silently stops protecting
    # the per-tunnel connector token (which is not a repo secret, so the runner
    # does not mask it for us). Off-stdout must not become not-at-all.
    grep -q '::add-mask::sup3rs3cret' "$err" ||
        log_fail "bp_gha_mask emitted no ::add-mask:: at all -- masking is silently dead"
    grep -q '::warning::careful' "$err" ||
        log_fail "bp_gha_warning emitted no ::warning:: at all"
    log_pass "workflow commands are still emitted (on stderr), so masking keeps working"
}

test_no_credential_expression_in_workflow
with_temp_dir test_detector_fires_on_the_real_leak
with_temp_dir test_workflow_commands_never_hit_stdout
test_publish_reads_state
test_shell_does_not_mask_unconditionally
test_live_workflow_matches_template
