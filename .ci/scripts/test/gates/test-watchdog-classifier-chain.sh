#!/bin/bash
# Behavioural test for the failure-classifier PROVIDER CHAIN in
# .ci/scripts/ci/watchdog-monitor.cjs.
#
# WHAT THIS IS FOR. The watchdog's verdict decides whether to spend a retry,
# which is roughly 500 machine-minutes. There is now a three-tier chain:
#
#   1. Cloudflare / DeepSeek V4 Pro
#   2. Anthropic / Claude
#   3. the known-flaky allowlist
#
# Tier 3 is NOT a classifier. It is a safety net that cannot tell a real break
# in an E2E job from a flake in one, and before tier 2 existed every failure
# reached it, because tier 1 has been returning HTTP 402 continuously. So the
# property under test is an ORDERING property across providers, and the thing
# most worth pinning is that a provider which does not answer is skipped rather
# than believed.
#
# WHY NOT A UNIT TEST. The chain lives inside monitor()'s closure, and the claim
# is about what gets CALLED, not just what gets returned. So this drives the
# REAL monitor() with a mocked GitHub client and a mocked global.fetch, then
# asserts on the sequence of URLs actually requested.
#
# Both directions matter throughout:
#   - Too eager: tier 2 gets called even when tier 1 already answered, paying
#     twice and, worse, discarding a verdict that was already made.
#   - Too lazy: tier 1 declining ends the chain, so tier 2 never runs and the
#     allowlist decides after all, which is the bug this whole change removes.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The harness. Mocks github/core/context AND global.fetch, runs the real
# monitor once, and prints the fetch trace so the ORDER of providers is
# observable rather than inferred.
cat >"$WORK/harness.cjs" <<'HARNESS'
const monitor = require(process.argv[2]);
const cfMode = process.argv[3];      // ok | http402 | offcontract | absent
const claudeMode = process.argv[4];  // ok | http402 | absent

const LOG_BODY = [
  'Run some/step@v1',
  '##[error]transfer failed: failed to finalize transfer: exit status 23',
  '##[error]Process completed with exit code 1.',
].join('\n');

const fetched = [];

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    // A real Response exposes text(), and the non-2xx path reads it to report
    // WHY a tier declined. A stub without text() makes that path log
    // "(body unreadable)" and the assertion below vacuous, so it stays.
    text: async () => JSON.stringify(payload),
  };
}

// Real provider error bodies, not {}. Both tiers went dark in production behind
// a bare "HTTP 402" / "HTTP 400", and the whole point of reading the body is
// that these two say completely different things about what to fix.
const CF_402_BODY = { errors: [{ code: 10000, message: 'quota exceeded for account' }] };
const CLAUDE_400_BODY = { type: 'error', error: { type: 'invalid_request_error', message: 'model: unknown model id' } };

global.fetch = async (url) => {
  const u = String(url);
  if (u.includes('api.cloudflare.com')) {
    fetched.push('cloudflare');
    if (cfMode === 'http402') return jsonResponse(402, CF_402_BODY);
    if (cfMode === 'offcontract') {
      // Parses as JSON but violates the verdict contract: an unknown
      // classification. Must count as NO ANSWER, not as a weak answer.
      return jsonResponse(200, { choices: [{ message: { content: '{"classification":"maybe","confidence":0.9}' } }] });
    }
    return jsonResponse(200, {
      choices: [{ message: { content: '{"classification":"code-change","confidence":0.95,"reason":"cf said so"}' } }],
    });
  }
  if (u.includes('api.anthropic.com')) {
    fetched.push('anthropic');
    if (claudeMode === 'http402') return jsonResponse(400, CLAUDE_400_BODY);
    return jsonResponse(200, {
      content: [{ type: 'text', text: '{"classification":"code-change","confidence":0.93,"reason":"claude said so"}' }],
    });
  }
  fetched.push('unexpected:' + u);
  return jsonResponse(500, {});
};

const siblings = [
  { id: 1, name: 'Quality / Code', status: 'completed', conclusion: 'success' },
  { id: 2, name: 'Quality / Static', status: 'completed', conclusion: 'success' },
];
const startMs = Date.parse('2026-07-28T06:00:00Z');
const job = {
  id: 4242, name: 'Tests + Infra / E2E Migrate', status: 'completed', conclusion: 'failure',
  started_at: new Date(startMs).toISOString(),
  completed_at: new Date(startMs + 5 * 60_000).toISOString(),
};

const actions = [];
const github = {
  hook: { before: () => {} },
  paginate: async () => [job, ...siblings],
  request: async (route) => {
    actions.push(route.includes('rerun') ? 'rerun' : route.includes('force-cancel') ? 'force-cancel' : 'req');
    return {};
  },
  rest: {
    actions: {
      getWorkflowRun: async () => ({ data: { status: 'completed', conclusion: null, run_attempt: 1, event: 'pull_request' } }),
      listJobsForWorkflowRun: () => {},
      downloadJobLogsForWorkflowRun: async () => ({ data: LOG_BODY }),
      cancelWorkflowRun: async () => { actions.push('cancel'); return {}; },
    },
    issues: { listLabelsOnIssue: async () => ({ data: [] }) },
  },
};
const core = {
  setFailed: (m) => actions.push('setFailed'),
  warning: (m) => actions.push('warning:' + String(m).slice(0, 160)),
  error: () => {},
  setOutput: () => {},
  info: () => {},
};
const context = { repo: { owner: 'rediacc', repo: 'console' }, runId: 1, payload: {} };

monitor({ github, context, core })
  .then(() => console.log('FETCHED=' + fetched.join(',') + ' ACTIONS=' + actions.join('|')))
  .catch((e) => { console.log('THREW:' + e.message); process.exitCode = 3; });
HARNESS

# run <cf-mode> <claude-mode> -> prints "FETCHED=... ACTIONS=..."
# Runs from the repo root because the classifier prompt is read by relative path.
run_chain() {
    local cf="$1" claude="$2"
    local cf_env=() claude_env=()
    if [[ "$cf" == "absent" ]]; then
        cf_env=(CLOUDFLARE_API_TOKEN= CLOUDFLARE_ACCOUNT_ID=)
    else
        cf_env=(CLOUDFLARE_API_TOKEN=t CLOUDFLARE_ACCOUNT_ID=a)
    fi
    if [[ "$claude" == "absent" ]]; then
        claude_env=(ANTHROPIC_API_KEY= CLAUDE_CODE_OAUTH_TOKEN=)
    else
        claude_env=(ANTHROPIC_API_KEY= CLAUDE_CODE_OAUTH_TOKEN=oauth-tok)
    fi
    (cd "$REPO_ROOT" && env "${cf_env[@]}" "${claude_env[@]}" \
        WATCHDOG_EXCLUDE_PATTERNS='Watchdog,CI Complete' \
        WATCHDOG_NO_RETRY_PATTERNS='Quality,Review Gate' \
        WATCHDOG_RETRY_ALLOWLIST_PATTERNS='E2E,OPS,Fork Isolation' \
        WATCHDOG_INSTALL_VALIDATION_PATTERNS='Validate Install Methods / Linux' \
        WATCHDOG_DEADLINE_SECONDS=480 \
        node "$WORK/harness.cjs" "$WATCHDOG" "$cf" "$claude" 2>/dev/null | tail -1)
}

# Same run, but the WHOLE stdout instead of the last line. run_chain's `tail -1`
# keeps only the FETCHED= trace, which is right for the ordering assertions and
# useless for anything the chain reports on its way there.
run_chain_full() {
    local cf="$1" claude="$2"
    (cd "$REPO_ROOT" && env CLOUDFLARE_API_TOKEN=t CLOUDFLARE_ACCOUNT_ID=a \
        ANTHROPIC_API_KEY= CLAUDE_CODE_OAUTH_TOKEN=oauth-tok \
        WATCHDOG_EXCLUDE_PATTERNS='Watchdog,CI Complete' \
        WATCHDOG_NO_RETRY_PATTERNS='Quality,Review Gate' \
        WATCHDOG_RETRY_ALLOWLIST_PATTERNS='E2E,OPS,Fork Isolation' \
        WATCHDOG_INSTALL_VALIDATION_PATTERNS='Validate Install Methods / Linux' \
        WATCHDOG_DEADLINE_SECONDS=480 \
        node "$WORK/harness.cjs" "$WATCHDOG" "$cf" "$claude" 2>&1)
}

# ---------------------------------------------------------------------------

test_prompt_file_exists() {
    # Anti-vacuity. Every provider returns null when the prompt cannot be read,
    # so a missing prompt file would make the whole chain "work" by never
    # calling anybody, and each ordering assertion below would pass for the
    # wrong reason.
    assert_eq "$(test -f "$REPO_ROOT/.ci/prompts/ci-failure-classifier.md" && echo yes)" "yes" \
        "the shared classifier prompt exists, so a null verdict means the provider declined"
    log_pass "the classifier prompt is present (chain results are not vacuous)"
}

test_tier1_answers_and_tier2_is_never_called() {
    local out
    out="$(run_chain ok ok)"
    assert_contains "$out" "FETCHED=cloudflare " "tier 1 is asked first"
    assert_not_contains "$out" "anthropic" \
        "tier 2 must NOT be called once tier 1 has answered (paying twice, and discarding a real verdict)"
    log_pass "a tier-1 answer ends the chain: Claude is never called"
}

test_tier1_402_falls_through_to_tier2() {
    # THE CASE THIS CHANGE EXISTS FOR. Tier 1 has returned HTTP 402 continuously,
    # so before tier 2 existed this went straight to the allowlist.
    local out
    out="$(run_chain http402 ok)"
    assert_contains "$out" "cloudflare,anthropic" "tier 1 is tried first, then tier 2, in that order"
    assert_not_contains "$out" "warning:Failure classifier unavailable" \
        "with tier 2 answering, the allowlist warning must NOT fire"
    log_pass "tier 1 returning 402 falls through to Claude, and the allowlist is not reached"
}

test_offcontract_answer_counts_as_no_answer() {
    # A reply that parses as JSON but violates the verdict contract is NOT a
    # weak verdict. Believing it would let a malformed answer decide a retry.
    local out
    out="$(run_chain offcontract ok)"
    assert_contains "$out" "cloudflare,anthropic" \
        "an off-contract classification is treated as no answer, so tier 2 is tried"
    log_pass "an off-contract reply is discarded, not downgraded to a low-confidence verdict"
}

test_both_tiers_down_reaches_the_allowlist() {
    local out
    out="$(run_chain http402 http402)"
    assert_contains "$out" "cloudflare,anthropic" "both tiers are attempted before giving up"
    assert_contains "$out" "warning:Failure classifier unavailable" \
        "exhausting the chain warns loudly rather than deciding silently"
    assert_contains "$out" "rerun" \
        "and the allowlist still governs: E2E Migrate is allowlisted, so it is retried"
    log_pass "with every provider down the allowlist decides, and says so"
}

test_absent_credentials_skip_a_tier_without_breaking() {
    # A missing secret must make a tier ABSENT, never fatal. This is what keeps
    # the change safe to land before any credential is configured.
    local out
    out="$(run_chain http402 absent)"
    assert_not_contains "$out" "THREW" "a missing Claude credential must not throw"
    assert_contains "$out" "warning:Failure classifier unavailable" \
        "an unconfigured tier degrades to the allowlist, exactly as before this change"
    log_pass "an absent credential skips its tier instead of breaking the watchdog"
}

test_tier1_absent_still_reaches_tier2() {
    local out
    out="$(run_chain absent ok)"
    assert_not_contains "$out" "cloudflare" "an unconfigured tier 1 is not called at all"
    assert_contains "$out" "anthropic" "and the chain still reaches tier 2"
    log_pass "an unconfigured tier 1 is skipped without ending the chain"
}

test_provider_order_is_declared_not_incidental() {
    # The order is a cost decision (cheapest capable first), so it is pinned
    # against the source rather than left to whichever function was defined
    # first.
    local src
    src="$(cat "$WATCHDOG")"
    assert_contains "$src" "CLASSIFIER_PROVIDERS" "the chain is an explicit ordered list"
    local cf_idx claude_idx
    cf_idx="$(grep -n "name: 'cloudflare/deepseek-v4-pro'" "$WATCHDOG" | head -1 | cut -d: -f1)"
    claude_idx="$(grep -n "name: 'anthropic/claude'" "$WATCHDOG" | head -1 | cut -d: -f1)"
    assert_eq "$([ -n "$cf_idx" ] && [ -n "$claude_idx" ] && [ "$cf_idx" -lt "$claude_idx" ] && echo ordered)" "ordered" \
        "Cloudflare is declared before Claude in the provider list"
    log_pass "the provider order is declared explicitly, cheapest capable first"
}

test_declining_tier_reports_why_not_just_the_status() {
    # REGRESSION. Both tiers went dark in production simultaneously and the run
    # log said only "HTTP 402" and "HTTP 400". Those are different problems with
    # different fixes (a quota versus a malformed request), and neither status
    # alone says which. Worse, "both tiers declined" is indistinguishable from
    # "both tiers are unconfigured" when the reason is missing, so the chain
    # looks absent rather than broken and nobody goes looking.
    local out
    out="$(run_chain_full http402 http402)"

    assert_contains "$out" "quota exceeded for account" \
        "a declining tier 1 reports the provider's own explanation, not just 402"
    assert_contains "$out" "invalid_request_error" \
        "a declining tier 2 reports the provider's own explanation, not just 400"

    # The control. The assertions above pass trivially if the body is echoed
    # from somewhere other than the error path, and they pass VACUOUSLY if
    # errorBody() silently falls back. Pin that neither happened.
    assert_not_contains "$out" "(body unreadable)" \
        "the response body is actually read, not swallowed by errorBody's catch"
    assert_not_contains "$out" "(empty body)" \
        "the stubbed error bodies are non-empty, so a fallback here means the read path is wrong"
    log_pass "a tier that declines says WHY, so a dark chain is diagnosable from the run log"
}

log_test "test-watchdog-classifier-chain"

test_prompt_file_exists
test_tier1_answers_and_tier2_is_never_called
test_tier1_402_falls_through_to_tier2
test_offcontract_answer_counts_as_no_answer
test_both_tiers_down_reaches_the_allowlist
test_absent_credentials_skip_a_tier_without_breaking
test_tier1_absent_still_reaches_tier2
test_provider_order_is_declared_not_incidental
test_declining_tier_reports_why_not_just_the_status

log_pass "all tests passed"
