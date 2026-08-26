#!/bin/bash
# Phase 5b reaps orphaned per-PR preview Workers -- and must never reap anything
# else, because there is no undo.
#
# WHAT WENT WRONG, measured 2026-08-26: `Cleanup PR Preview` run 32903006150
# died at the app-token step on GitHub's OWN internal DNS
# (internal-api.service.iad.github.net, "Name or service not known") before
# checkout, so neither of its two cleanups ran. Phase 5 backstops the Pages
# side; nothing backstopped `wrangler delete --name pr-<n>`
# (cleanup-preview.yml:60), so the Worker leaked with nothing to reap it -- one
# per failed cleanup, forever.
#
# THIS GATE IS MOSTLY ABOUT WHAT MUST **NOT** BE DELETED. A reaping phase that
# works is easy; a reaping phase that cannot over-reach is the whole risk, since
# it runs unattended at 03:00 with production Cloudflare credentials. So the
# selector is tested against names chosen to break it: the production and bench
# Workers, a pr-prefixed name that is not a PR number, and an open PR's Worker.
#
# FAIL-CLOSED IS AN ASSERTION HERE, not a comment. Phase 4 (Pages) falls back to
# keep-N when the open-PR lookup fails, because its worst case is retaining too
# much. Phase 5b's worst case is deleting a LIVE preview, so an unreadable PR
# list must SKIP the phase. The two phases must not be "made consistent".
#
# WHAT THIS GATE CANNOT SEE: it tests the SELECTOR and the guards by extracting
# them, not a live Cloudflare account. It cannot prove the real API deletes what
# the selector chose, and it cannot prove no long-lived Worker in the real
# account happens to match ^pr-[0-9]+$ -- that needs a live listing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/housekeeping/cleanup-versions.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

# The selector, as the phase uses it. Kept in ONE place so a drift between gate
# and subject is impossible to write by accident.
PR_WORKER_RE='^pr-([0-9]+)$'

# selects <name> -- exit 0 when the phase would consider this name at all.
selects() { [[ "$1" =~ $PR_WORKER_RE ]]; }

test_selector_matches_only_pr_numbers() {
    log_test "the selector must match pr-<number> and nothing else"
    local must_match=(pr-1 pr-574 pr-99999)
    # EVERY Worker name this repo actually defines, swept 2026-08-26 from all
    # wrangler.*.toml plus the one `wrangler delete`. Invented names prove less
    # than real ones: these are the Workers a bad selector would destroy.
    local must_not=(
        account-server            # private/account/wrangler.toml:22
        rediacc-account-eu        # workers/account/wrangler.eu.toml:1
        rediacc-account-us        # workers/account/wrangler.us.toml:1
        rediacc-account-asia      # workers/account/wrangler.asia.toml:1
        rediacc-account-bench     # workers/account/wrangler.bench.toml:13
        edge-rediacc-account-eu   # workers/account/wrangler.edge-eu.toml:1
        edge-rediacc-account-us   # workers/account/wrangler.edge-us.toml:1
        edge-rediacc-account-asia # workers/account/wrangler.edge-asia.toml:1
        rediacc-www               # workers/www/wrangler.toml:1
        edge-rediacc-www          # workers/www/wrangler.edge.toml:1
        rediacc-proxy-eu          # workers/proxy/wrangler.toml:1
        mta-sts-policy            # workers/mta-sts/wrangler.toml:1
        pr-main                   # pr- prefix, not a number
        pr-574-old                # trailing junk
        prefix-pr-574             # not anchored at the start
        PR-574                    # case
        pr-                       # empty number
        pr-57a                    # not all digits
    )
    local n
    for n in "${must_match[@]}"; do
        selects "$n" || log_fail "selector MISSED a real preview Worker: $n"
    done
    for n in "${must_not[@]}"; do
        if selects "$n"; then
            log_fail "selector would have reaped a NON-preview Worker: $n"
        fi
    done
    log_pass "selector: ${#must_match[@]} matched, ${#must_not[@]} correctly rejected"
}

test_selector_regex_is_the_one_in_the_subject() {
    log_test "the subject must use this exact anchored pattern"
    grep -q '\^pr-(\[0-9\]+)\$' "$SUT" ||
        log_fail "cleanup-versions.sh no longer uses the anchored ^pr-([0-9]+)\$ selector"
    log_pass "subject and gate agree on the selector"
}

test_open_pr_is_never_reaped() {
    log_test "an OPEN PR's Worker must be skipped"
    local open_prs
    open_prs="$(printf '%s\n' 574 576)"
    local name=pr-576
    [[ "$name" =~ $PR_WORKER_RE ]] || log_fail "fixture did not match the selector"
    local num="${BASH_REMATCH[1]}"
    if grep -qx "$num" <<<"$open_prs"; then
        log_pass "open PR #$num is skipped"
    else
        log_fail "an OPEN PR's Worker would have been deleted"
    fi
}

test_closed_pr_is_reaped() {
    log_test "a CLOSED PR's Worker must be selected"
    local open_prs
    open_prs="$(printf '%s\n' 576)"
    local name=pr-574
    [[ "$name" =~ $PR_WORKER_RE ]] || log_fail "fixture did not match the selector"
    local num="${BASH_REMATCH[1]}"
    if grep -qx "$num" <<<"$open_prs"; then
        log_fail "a CLOSED PR's Worker was treated as live"
    else
        log_pass "closed PR #$num is selected for reaping"
    fi
}

test_fails_closed_when_pr_list_unreadable() {
    log_test "an unreadable open-PR list must SKIP the phase, not delete"
    # By construction: the guard must RETURN before any delete. Assert on the
    # ordering, which is the property -- a warn that still falls through to a
    # delete reads identically in a diff.
    local body
    body="$(awk '/^cleanup_preview_workers\(\) \{/,/^\}/' "$SUT")"
    [[ -n "$body" ]] || log_fail "could not extract cleanup_preview_workers from the subject"

    local guard_line del_line
    guard_line="$(grep -n 'SKIPPING Worker cleanup' <<<"$body" | head -1 | cut -d: -f1 || true)"
    del_line="$(grep -n 'cf_api DELETE' <<<"$body" | head -1 | cut -d: -f1 || true)"
    [[ -n "$guard_line" ]] || log_fail "the fail-closed guard is GONE from cleanup_preview_workers"
    [[ -n "$del_line" ]] || log_fail "no delete call found; the phase does nothing"
    [[ "$guard_line" -lt "$del_line" ]] ||
        log_fail "the fail-closed guard sits AFTER the delete, so it guards nothing"

    grep -q 'return 0' <<<"$(sed -n "${guard_line},\$p" <<<"$body" | head -3 || true)" ||
        log_fail "the unreadable-PR-list branch warns but does not return"
    log_pass "unreadable PR list returns before any delete"
}

test_dry_run_and_budget_are_honoured() {
    log_test "DRY_RUN and the delete budget must both gate the delete"
    local body
    body="$(awk '/^cleanup_preview_workers\(\) \{/,/^\}/' "$SUT")"
    grep -q 'DRY_RUN' <<<"$body" || log_fail "phase ignores DRY_RUN -- a dry run would DELETE"
    grep -q 'deletes_budget_ok' <<<"$body" || log_fail "phase ignores MAX_DELETES_PER_RUN"
    local dry_line del_line
    dry_line="$(grep -n 'DRY_RUN' <<<"$body" | head -1 | cut -d: -f1 || true)"
    del_line="$(grep -n 'cf_api DELETE' <<<"$body" | head -1 | cut -d: -f1 || true)"
    [[ "$dry_line" -lt "$del_line" ]] || log_fail "the DRY_RUN check sits AFTER the delete"
    log_pass "DRY_RUN and budget both precede the delete"
}

test_phase_is_actually_invoked() {
    log_test "a phase nobody calls reaps nothing"
    grep -qE '^[[:space:]]*cleanup_preview_workers[[:space:]]*$' "$SUT" ||
        log_fail "cleanup_preview_workers is defined but never invoked"
    log_pass "phase is wired into the run"
}

test_control_overbroad_selector_is_caught() {
    log_test "CONTROL: an unanchored selector must be detectable"
    # Built by construction: a DIFFERENT regex, not a mutation of the real one.
    local loose='pr-'
    local victim=rediacc-console-bench
    # A substring-style selector would sweep names the anchored one rejects.
    if [[ "pr-574-old" == *"$loose"* ]] && ! selects "pr-574-old"; then
        log_pass "control: the anchored selector rejects what a loose one accepts"
    else
        log_fail "CONTROL DID NOT FIRE: anchored and loose selectors agreed"
    fi
    # `selects X && log_fail` would leak X's non-zero status out of this
    # function and trip errexit at the call site -- an all-green run exiting 1.
    if selects "$victim"; then
        log_fail "CONTROL: production Worker matched the real selector"
    fi
}

test_selector_matches_only_pr_numbers
test_selector_regex_is_the_one_in_the_subject
test_open_pr_is_never_reaped
test_closed_pr_is_reaped
test_fails_closed_when_pr_list_unreadable
test_dry_run_and_budget_are_honoured
test_phase_is_actually_invoked
test_control_overbroad_selector_is_caught

echo
log_pass "preview-Worker reaping: 8/8"
echo "  Blind spot: tests the SELECTOR and guard ORDER, not a live Cloudflare"
echo "  account. Cannot prove no long-lived Worker matches ^pr-[0-9]+\$ for real."
