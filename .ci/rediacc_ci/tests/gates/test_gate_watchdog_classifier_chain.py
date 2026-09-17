"""Port of `.ci/scripts/test/gates/test-watchdog-classifier-chain.sh`.

The failure-classifier PROVIDER CHAIN in `.ci/scripts/ci/watchdog-monitor.cjs`.

WHAT THIS IS FOR. The watchdog's verdict decides whether to spend a retry, which
is roughly 500 machine-minutes. There is a three-tier chain:

  1. Cloudflare / Workers AI
  2. Anthropic / Claude
  3. the known-flaky allowlist

Tier 3 is NOT a classifier. It is a safety net that cannot tell a real break in
an E2E job from a flake in one, and before tier 2 existed every failure reached
it, because tier 1 has been returning HTTP 402 continuously. So the property
under test is an ORDERING property across providers, and the thing most worth
pinning is that a provider which does not answer is SKIPPED rather than believed.

WHY NOT A UNIT TEST. The chain lives inside monitor()'s closure, and the claim is
about what gets CALLED, not just what gets returned. So this drives the REAL
monitor() with a mocked GitHub client and a mocked global.fetch, then asserts on
the sequence of URLs actually requested.

Both directions matter throughout:
  - Too eager: tier 2 gets called even when tier 1 already answered, paying twice
    and, worse, discarding a verdict that was already made.
  - Too lazy: tier 1 declining ends the chain, so tier 2 never runs and the
    allowlist decides after all, which is the bug this change removes.

The runs happen with cwd at the repo root because the classifier prompt is read
by relative path. Nothing is written to the tree: the harness lives in `tmp_path`
and no network call leaves the process, because `global.fetch` is replaced.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-classifier-chain.sh"

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
PROMPT = paths.from_root(".ci", "prompts", "ci-failure-classifier.md")

# The harness. Mocks github/core/context AND global.fetch, runs the real monitor once, and prints the fetch trace so the ORDER of providers is observable rather than inferred.
HARNESS_CJS = r"""
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
  setFailed: () => actions.push('setFailed'),
  warning: (m) => actions.push('warning:' + String(m).slice(0, 160)),
  error: () => {},
  setOutput: () => {},
  info: () => {},
};
const context = { repo: { owner: 'rediacc', repo: 'console' }, runId: 1, payload: {} };

monitor({ github, context, core })
  .then(() => console.log('FETCHED=' + fetched.join(',') + ' ACTIONS=' + actions.join('|')))
  .catch((e) => { console.log('THREW:' + e.message); process.exitCode = 3; });
"""

# Stand-in credential values. Named constants rather than literals at the
# assignment site: ruff's S105 reads `env["..._TOKEN"] = "t"` as a hardcoded
# secret, which it is not -- global.fetch is mocked and no request leaves the process. Naming them also says which knob each case is turning.
CF_PRESENT = "t"
CF_ACCOUNT_PRESENT = "a"
CLAUDE_PRESENT = "oauth-tok"
TIER_ABSENT = ""

CHAIN_ENV = {
    "WATCHDOG_EXCLUDE_PATTERNS": "Watchdog,CI Complete",
    "WATCHDOG_NO_RETRY_PATTERNS": "Quality,Review Gate",
    "WATCHDOG_RETRY_ALLOWLIST_PATTERNS": "E2E,OPS,Fork Isolation",
    "WATCHDOG_INSTALL_VALIDATION_PATTERNS": "Validate Install Methods / Linux",
    "WATCHDOG_DEADLINE_SECONDS": "480",
}


def subject(gate):
    # The four lines this used to hold were byte-identical in three watchdog gate tests;
    # they live in `harness` now. See harness.watchdog_subject for why this one is extractable where an assertion message is not.
    return harness.watchdog_subject(gate, WATCHDOG)


def harness_script(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "harness.cjs"
    path.write_text(HARNESS_CJS, encoding="utf-8")
    subject(gate)
    return path


def drive(gate, tmp_path, cf: str, claude: str) -> harness.RunResult:
    env = dict(CHAIN_ENV)
    absent = cf == "absent"
    env["CLOUDFLARE_API_TOKEN"] = TIER_ABSENT if absent else CF_PRESENT
    env["CLOUDFLARE_ACCOUNT_ID"] = TIER_ABSENT if absent else CF_ACCOUNT_PRESENT
    env["ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN"] = TIER_ABSENT if claude == "absent" else CLAUDE_PRESENT
    return harness.run(
        ["node", str(harness_script(gate, tmp_path)), str(subject(gate)), cf, claude],
        cwd=paths.repo_root(),
        env=env,
        timeout=300,
    )


def run_chain(gate, tmp_path, cf: str, claude: str) -> str:
    """The LAST stdout line: "FETCHED=... ACTIONS=..."."""
    result = drive(gate, tmp_path, cf, claude)
    lines = [ln for ln in result.out.splitlines() if ln.strip()]
    if not lines:
        gate.log_fail(
            "the chain printed no trace at all (rc=%d), so no ordering claim could be "
            "made. stderr: %s" % (result.rc, result.err.strip()[:400])
        )
    return lines[-1]


def run_chain_full(gate, tmp_path, cf: str, claude: str) -> str:
    """The WHOLE output. `run_chain`'s last-line rule keeps only the FETCHED=
    trace, which is right for the ordering cases and useless for anything the
    chain reports on its way there."""
    result = drive(gate, tmp_path, cf, claude)
    return result.combined


def test_prompt_file_exists(gate):
    """Anti-vacuity. Every provider returns null when the prompt cannot be read,
    so a missing prompt file would make the whole chain "work" by never calling
    anybody, and each ordering assertion below would pass for the wrong reason."""
    gate.assert_eq(
        "yes" if PROMPT.is_file() else "no",
        "yes",
        "the shared classifier prompt exists, so a null verdict means the provider declined",
    )
    gate.log_pass("the classifier prompt is present (chain results are not vacuous)")


def test_tier1_answers_and_tier2_is_never_called(gate, tmp_path):
    out = run_chain(gate, tmp_path, "ok", "ok")
    gate.assert_contains(out, "FETCHED=cloudflare ", "tier 1 is asked first")
    gate.assert_not_contains(
        out,
        "anthropic",
        "tier 2 must NOT be called once tier 1 has answered (paying twice, and "
        "discarding a real verdict)",
    )
    gate.log_pass("a tier-1 answer ends the chain: Claude is never called")


def test_tier1_402_falls_through_to_tier2(gate, tmp_path):
    """THE CASE THIS CHANGE EXISTS FOR. Tier 1 has returned HTTP 402
    continuously, so before tier 2 existed this went straight to the allowlist."""
    out = run_chain(gate, tmp_path, "http402", "ok")
    gate.assert_contains(
        out, "cloudflare,anthropic", "tier 1 is tried first, then tier 2, in that order"
    )
    gate.assert_not_contains(
        out,
        "warning:Failure classifier unavailable",
        "with tier 2 answering, the allowlist warning must NOT fire",
    )
    gate.log_pass("tier 1 returning 402 falls through to Claude, and the allowlist is not reached")


def test_offcontract_answer_counts_as_no_answer(gate, tmp_path):
    """A reply that parses as JSON but violates the verdict contract is NOT a
    weak verdict. Believing it would let a malformed answer decide a retry."""
    out = run_chain(gate, tmp_path, "offcontract", "ok")
    gate.assert_contains(
        out,
        "cloudflare,anthropic",
        "an off-contract classification is treated as no answer, so tier 2 is tried",
    )
    gate.log_pass("an off-contract reply is discarded, not downgraded to a low-confidence verdict")


def test_both_tiers_down_reaches_the_allowlist(gate, tmp_path):
    out = run_chain(gate, tmp_path, "http402", "http402")
    gate.assert_contains(out, "cloudflare,anthropic", "both tiers are attempted before giving up")
    gate.assert_contains(
        out,
        "warning:Failure classifier unavailable",
        "exhausting the chain warns loudly rather than deciding silently",
    )
    gate.assert_contains(
        out,
        "rerun",
        "and the allowlist still governs: E2E Migrate is allowlisted, so it is retried",
    )
    gate.log_pass("with every provider down the allowlist decides, and says so")


def test_absent_credentials_skip_a_tier_without_breaking(gate, tmp_path):
    """A missing secret must make a tier ABSENT, never fatal. This is what keeps
    the change safe to land before any credential is configured."""
    out = run_chain(gate, tmp_path, "http402", "absent")
    gate.assert_not_contains(out, "THREW", "a missing Claude credential must not throw")
    gate.assert_contains(
        out,
        "warning:Failure classifier unavailable",
        "an unconfigured tier degrades to the allowlist, exactly as before this change",
    )
    gate.log_pass("an absent credential skips its tier instead of breaking the watchdog")


def test_tier1_absent_still_reaches_tier2(gate, tmp_path):
    out = run_chain(gate, tmp_path, "absent", "ok")
    gate.assert_not_contains(out, "cloudflare", "an unconfigured tier 1 is not called at all")
    gate.assert_contains(out, "anthropic", "and the chain still reaches tier 2")
    gate.log_pass("an unconfigured tier 1 is skipped without ending the chain")


def test_provider_order_is_declared_not_incidental(gate):
    """The order is a cost decision (cheapest capable first), so it is pinned
    against the source rather than left to whichever function was defined first.

    Anchored on the CALL, not on the model name. This assertion used to grep for
    a literal model string, which coupled an ordering test to a display string
    and is exactly why the label could go stale unnoticed. The call target is the
    tier's real identity and cannot drift with the model.
    """
    lines = subject(gate).read_text(encoding="utf-8").splitlines()
    gate.assert_contains(
        "\n".join(lines), "CLASSIFIER_PROVIDERS", "the chain is an explicit ordered list"
    )
    cf_index = next(
        (i for i, ln in enumerate(lines, start=1) if "call: callCloudflareClassifier" in ln), 0
    )
    claude_index = next(
        (i for i, ln in enumerate(lines, start=1) if "call: callClaudeClassifier" in ln), 0
    )
    gate.assert_eq(
        "ordered" if cf_index and claude_index and cf_index < claude_index else "not-ordered",
        "ordered",
        "Cloudflare is declared before Claude in the provider list",
    )
    gate.log_pass("the provider order is declared explicitly, cheapest capable first")


def test_tier1_label_is_derived_from_the_model_it_calls(gate):
    """THE ROT THIS PREVENTS, observed on watchdog run 30541558539: the log said
    "[AI] verdict from cloudflare/deepseek-v4-pro" while the request actually went
    to /ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast. The label is the only
    record of which model produced a verdict that decides whether to spend ~500
    machine-minutes on a retry, and the 402 that broke this tier was diagnosed BY
    MODEL IDENTITY, so a label that lies sends the next investigation to the wrong
    provider.

    Asserting the SHAPE (interpolated from AI_MODEL) rather than the current model
    string, because pinning the string would rebuild the same trap.
    """
    text = subject(gate).read_text(encoding="utf-8")
    entry = next((ln for ln in text.splitlines() if "call: callCloudflareClassifier" in ln), "")
    if not entry:
        gate.log_fail("the tier-1 provider entry could not be located, so its label is unchecked")
    gate.assert_contains(
        entry, "AI_MODEL", "the tier-1 label must interpolate AI_MODEL, never hardcode a model name"
    )
    # And the constant it interpolates has to exist, or the label renders empty.
    gate.assert_contains(
        text, "const AI_MODEL", "AI_MODEL must be declared for the tier-1 label to derive from it"
    )
    gate.log_pass("the tier-1 provider label is derived from AI_MODEL, so it cannot go stale")


def test_declining_tier_reports_why_not_just_the_status(gate, tmp_path):
    """REGRESSION. Both tiers went dark in production simultaneously and the run
    log said only "HTTP 402" and "HTTP 400". Those are different problems with
    different fixes (a quota versus a malformed request), and neither status alone
    says which. Worse, "both tiers declined" is indistinguishable from "both tiers
    are unconfigured" when the reason is missing, so the chain looks absent rather
    than broken and nobody goes looking."""
    out = run_chain_full(gate, tmp_path, "http402", "http402")

    gate.assert_contains(
        out,
        "quota exceeded for account",
        "a declining tier 1 reports the provider's own explanation, not just 402",
    )
    gate.assert_contains(
        out,
        "invalid_request_error",
        "a declining tier 2 reports the provider's own explanation, not just 400",
    )

    # The control. The assertions above pass trivially if the body is echoed from somewhere other than the error path, and they pass VACUOUSLY if errorBody() silently falls back. Pin that neither happened.
    gate.assert_not_contains(
        out,
        "(body unreadable)",
        "the response body is actually read, not swallowed by errorBody's catch",
    )
    gate.assert_not_contains(
        out,
        "(empty body)",
        "the stubbed error bodies are non-empty, so a fallback here means the read path is wrong",
    )
    gate.log_pass("a tier that declines says WHY, so a dark chain is diagnosable from the run log")
