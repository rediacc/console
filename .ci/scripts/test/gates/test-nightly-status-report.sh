#!/bin/bash
# Behavioural test for .ci/scripts/ci/report-nightly-status.cjs.
#
# WHAT BROKE. Nothing reported the nightly's verdict anywhere. A scheduled run
# that fails at 01:00 UTC notifies nobody, appears in no PR, and blocks nothing
# -- and the nightly is the ONLY suite validating main, because ci.yml sets
# `full_suite: github.event_name != 'push'`. Measured 2026-07-27: twelve
# consecutive red nights, zero successes, back to 2026-07-16, unnoticed.
#
# WHY BEHAVIOURAL. The claims worth testing are about API CALLS -- "opens
# exactly one issue", "comments instead of opening a second", "closes on green"
# -- so this drives the real module with a mocked GitHub client and asserts on
# the call trace. A pure-function test would only cover isGreen.
#
# The workflow wiring itself (nightly-status.yml) cannot be tested pre-merge:
# `workflow_run` always executes the DEFAULT BRANCH's copy of a workflow. That
# is precisely why the logic lives in a testable module instead of inline YAML.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPORTER="$REPO_ROOT/.ci/scripts/ci/report-nightly-status.cjs"
WORKFLOW="$REPO_ROOT/.github/workflows/nightly-status.yml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat >"$WORK/harness.cjs" <<'HARNESS'
const report = require(process.argv[2]);
const openIssues = JSON.parse(process.argv[3]);   // e.g. [] or [{number: 7}]
const labelExists = process.argv[4] === '1';
const existingComments = JSON.parse(process.argv[5] || '[]');

const trace = [];
const github = {
  paginate: async (fn, params) => {
    // Three paginated endpoints: listForRepo (open issues), listComments (the
    // run-id dedupe) and listJobsForWorkflowRun (the failed-job roster).
    if (params && params.labels) { trace.push(`list-issues:${params.labels}`); return openIssues; }
    if (params && params.issue_number) { trace.push(`list-comments:${params.issue_number}`); return existingComments; }
    trace.push('list-jobs');
    return [
      { name: 'Stage Artifacts / Stage Artifacts', conclusion: 'failure', html_url: 'u1' },
      { name: 'Quality / Workflows', conclusion: 'failure', html_url: 'u2' },
      { name: 'Build (CLI) / Linux', conclusion: 'success', html_url: 'u3' },
      { name: 'Tests + Infra / E2E Ceph', conclusion: 'skipped', html_url: 'u4' },
    ];
  },
  rest: {
    issues: {
      listForRepo: () => {}, listComments: () => {}, create: async (p) => { trace.push(`create:${p.title}:${(p.labels||[]).join('+')}`); global.__body = p.body; return { data: { number: 99 } }; },
      createComment: async (p) => { trace.push(`comment:${p.issue_number}`); global.__body = p.body; return {}; },
      update: async (p) => { trace.push(`update:${p.issue_number}:${p.state}`); return {}; },
      getLabel: async () => { if (!labelExists) throw new Error('404'); trace.push('label-exists'); return {}; },
      createLabel: async (p) => { trace.push(`create-label:${p.name}`); return {}; },
    },
    actions: { listJobsForWorkflowRun: () => {} },
  },
};
const core = { warning: (m) => trace.push(`warning:${String(m).slice(0, 24)}`) };
const context = { repo: { owner: 'rediacc', repo: 'console' } };

report({ github, context, core })
  // The body is multi-line; emit it JSON-escaped on ONE line so the shell can
  // grep it. (The first draft printed it raw and `sed` matched only its first
  // line, so the body assertions were reading a header and nothing else.)
  .then(() => { console.log('TRACE=' + trace.join('|')); if (global.__body) console.log('BODY=' + JSON.stringify(global.__body)); })
  .catch((e) => { console.log('THREW:' + e.message); process.exitCode = 3; });
HARNESS

# run <conclusion> <event> <open-issues-json> [label-exists 0|1] [comments-json]
run_report() {
    NIGHTLY_RUN_ID=30237524399 NIGHTLY_CONCLUSION="$1" NIGHTLY_EVENT="$2" \
        NIGHTLY_URL='https://github.com/rediacc/console/actions/runs/30237524399' \
        node "$WORK/harness.cjs" "$REPORTER" "$3" "${4:-1}" "${5:-[]}" 2>/dev/null
}
trace_of() { run_report "$@" | sed -n 's/^TRACE=//p'; }

# ---------------------------------------------------------------------------

test_cancelled_is_not_green() {
    # THE LOAD-BEARING ASSERTION. Treating `cancelled` as green is the exact
    # conflation that hid twelve red nights: the watchdog cancelled each failing
    # run, so its conclusion read `cancelled`, and every reader took that for
    # "superseded, ignore". If this ever returns true the whole reporter is inert.
    local out
    out="$(node -e '
const r = require(process.argv[1]);
process.stdout.write([["success",r.isGreen("success")],["cancelled",r.isGreen("cancelled")],["failure",r.isGreen("failure")],["",r.isGreen("")]].map(([k,v])=>k+"="+v).join(","));
' "$REPORTER")"
    assert_eq "$out" "success=true,cancelled=false,failure=false,=false" \
        "only 'success' is green; cancelled must NOT be"
    log_pass "cancelled is not green ($out)"
}

test_non_schedule_event_is_a_no_op() {
    # The second lock behind the workflow's own `if:`. A future trigger change
    # must not silently start opening an issue for every PR run.
    assert_eq "$(trace_of failure pull_request '[]')" "" \
        "a pull_request run must produce no API calls at all"
    assert_eq "$(trace_of failure push '[]')" "" "a push run must produce no API calls at all"
    log_pass "only scheduled runs are reported on; every other event is inert"
}

test_first_red_night_opens_one_issue() {
    local t
    t="$(trace_of cancelled schedule '[]' 1)"
    assert_contains "$t" "create:Nightly CI is red:bug+automated+nightly-red" \
        "the first red night opens one issue with the triage labels"
    assert_not_contains "$t" "comment:" "nothing to comment on yet"
    log_pass "the first red night opens exactly one labelled issue ($t)"
}

test_second_red_night_comments_instead_of_opening_another() {
    # The anti-spam claim. Twelve red nights must produce ONE issue with twelve
    # comments, not twelve issues -- a wall of identical issues is its own kind
    # of invisible.
    local t
    t="$(trace_of cancelled schedule '[{"number":7}]')"
    assert_contains "$t" "comment:7" "a subsequent red night comments on the open issue"
    assert_not_contains "$t" "create:" "it must NOT open a second issue"
    log_pass "consecutive red nights accumulate on one issue ($t)"
}

test_green_closes_the_open_issue() {
    local t
    t="$(trace_of success schedule '[{"number":7}]')"
    assert_contains "$t" "comment:7" "the recovery is recorded on the issue"
    assert_contains "$t" "update:7:closed" "a green nightly closes the issue automatically"
    log_pass "a green nightly closes the rolling issue ($t)"
}

test_green_with_nothing_open_is_a_no_op() {
    local t
    t="$(trace_of success schedule '[]')"
    assert_not_contains "$t" "create:" "a green nightly with no open issue creates nothing"
    assert_not_contains "$t" "comment:" "and comments nowhere"
    log_pass "the steady green state is silent"
}

test_missing_label_is_created_before_use() {
    # createIssue with an unknown label fails the ENTIRE call, so the label must
    # be ensured first. `nightly-red` does not exist in the repo yet, so this is
    # the path the very first red night will actually take.
    local t
    t="$(trace_of cancelled schedule '[]' 0)"
    assert_contains "$t" "create-label:nightly-red" "the missing label is created"
    assert_contains "$t" "create:Nightly CI is red" "and the issue is still opened"
    log_pass "a missing nightly-red label is created before the issue uses it ($t)"
}

test_body_names_the_failed_jobs() {
    # "The nightly failed" is not actionable: a 90-job run means opening it to
    # find the two that matter. Successes and skips must be filtered out.
    local body
    body="$(run_report cancelled schedule '[]' | sed -n 's/^BODY=//p')"
    assert_contains "$body" "Stage Artifacts" "the failing job is named"
    assert_contains "$body" "Quality / Workflows" "every failing job is named"
    assert_not_contains "$body" "Build (CLI) / Linux" "successful jobs are not listed"
    assert_not_contains "$body" "E2E Ceph" "skipped jobs are not listed"
    assert_contains "$body" "30237524399" "the run id is linked for triage"
    log_pass "the issue body names exactly the failing jobs"
}

test_workflow_is_wired_to_schedule_runs_only() {
    # Anti-vacuity against the real workflow: the module is inert for non-schedule
    # events, but the workflow must also not burn a job on every PR run.
    local wf
    wf="$(cat "$WORKFLOW")"
    assert_contains "$wf" "workflow_run" "the reporter is driven by workflow_run"
    assert_contains "$wf" "github.event.workflow_run.event == 'schedule'" \
        "the workflow filters to scheduled runs"
    assert_contains "$wf" "issues: write" "the job grants itself issues:write"
    assert_contains "$wf" "report-nightly-status.cjs" "the workflow calls this module"
    log_pass "nightly-status.yml is wired to scheduled runs with the right grant"
}

test_a_rerun_of_the_same_night_does_not_double_comment() {
    # `workflow_run: completed` fires once per ATTEMPT and a run keeps its id
    # across attempts, so a nightly whose failed jobs are re-run reaches this
    # code twice for the same night. A duplicate comment per attempt makes a
    # streak look longer than it is -- and streak length is the one number this
    # issue exists to communicate.
    local t
    t="$(trace_of cancelled schedule '[{"number":7}]' 1 '[{"body":"### 2026-07-27 -- nightly [run 30237524399](x) concluded `cancelled`"}]')"
    assert_contains "$t" "list-comments:7" "existing comments are consulted"
    assert_not_contains "$t" "comment:7" "the same run must not be reported twice"
    log_pass "a rerun of the same night does not double-comment ($t)"
}

test_a_different_night_still_comments() {
    # The control for the dedupe: it must suppress only the SAME run id, not
    # every subsequent night. Getting this wrong would silence the streak
    # entirely after night one.
    local t
    t="$(trace_of cancelled schedule '[{"number":7}]' 1 '[{"body":"### 2026-07-26 -- nightly [run 30187728271](x) concluded `cancelled`"}]')"
    assert_contains "$t" "comment:7" "a new night is still reported on the rolling issue"
    log_pass "a different night is still reported (the dedupe is per-run, not blanket)"
}

test_a_pull_request_carrying_the_label_is_ignored() {
    # GitHub's issues API returns PULL REQUESTS as issues. A PR wearing this
    # label would otherwise be adopted as the tracking issue -- commented on,
    # and CLOSED on the next green nightly.
    local t
    t="$(trace_of success schedule '[{"number":42,"pull_request":{"url":"x"}}]')"
    assert_not_contains "$t" "update:42:closed" "a PR must never be closed by this workflow"
    assert_not_contains "$t" "comment:42" "and never commented on"
    log_pass "a pull request carrying the label is filtered out"
}

test_dedupe_is_anchored_not_a_bare_substring() {
    # A LONGER run id that merely starts with these digits must not be mistaken
    # for this night. Run ids gain a digit over time, so a bare
    # `includes("run " + runId)` becomes wrong on its own schedule -- and a false
    # dedupe is SILENT, dropping a night from the streak with nothing to show.
    # The posted format is always `[run <id>](<url>)`, so the marker is anchored
    # on the closing bracket.
    local t
    t="$(trace_of cancelled schedule '[{"number":7}]' 1 '[{"body":"### earlier -- nightly [run 302375243990](x) concluded `cancelled`"}]')"
    assert_contains "$t" "comment:7" \
        "a longer run id containing this one as a prefix must NOT suppress the comment"
    log_pass "the run-id dedupe is anchored, not a bare substring"
}

log_test "test-nightly-status-report"
test_cancelled_is_not_green
test_non_schedule_event_is_a_no_op
test_first_red_night_opens_one_issue
test_second_red_night_comments_instead_of_opening_another
test_green_closes_the_open_issue
test_green_with_nothing_open_is_a_no_op
test_missing_label_is_created_before_use
test_body_names_the_failed_jobs
test_workflow_is_wired_to_schedule_runs_only
test_a_rerun_of_the_same_night_does_not_double_comment
test_a_different_night_still_comments
test_dedupe_is_anchored_not_a_bare_substring
test_a_pull_request_carrying_the_label_is_ignored
echo ""
log_pass "all tests passed"
