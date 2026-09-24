"""Port of `.ci/scripts/test/gates/test-nightly-status-report.sh`, retired in W7 P5.

WHAT BROKE, kept from the twin because it is the reason the module exists. Nothing reported the nightly's verdict anywhere. A scheduled run that fails at 01:00 UTC notifies nobody, appears in no PR, and blocks nothing, and the nightly is the ONLY suite validating main, because ci.yml sets
`full_suite: github.event_name != 'push'`. Measured 2026-07-27: twelve
consecutive red nights, zero successes, back to 2026-07-16, unnoticed.

WHY BEHAVIOURAL. The claims worth testing are about API CALLS ("opens exactly one issue", "comments instead of opening a second", "closes on green"), so this drives the real module with a mocked GitHub client and asserts on the call trace. A pure-function test would only cover isGreen.

THE NODE HARNESS IS THE TWIN'S, BYTE FOR BYTE. It is a CommonJS file that the twin heredocs into its scratch directory and this module writes from a string literal; nothing about it was translated, because translating the mock would change what the subject is driven with and the two sides would then be comparing different runs. The only Python here is the argv marshalling and the
assertions, which is exactly the seam the twin implements in `sed -n 's/^TRACE=//p'`
and this implements with `str.startswith`. They agree because the harness emits
one `TRACE=` line and at most one `BODY=` line, both on their own line and both
last; `sed -n s///p` prints the remainder of every matching line and the Python form takes the remainder of the first matching line, which is the same string
while there is one match, and the harness JSON-encodes the body onto ONE line
precisely so that stays true.

NO `xdist_group`. Every case writes only into pytest's own `tmp_path`, reads `.ci/scripts/ci/report-nightly-status.cjs` and `.github/workflows/nightly-status.yml` without writing either, binds no port and mutates no module global. Two copies of this file running at once would not collide.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

REPORTER = paths.from_root(".ci", "scripts", "ci", "report-nightly-status.cjs")
WORKFLOW = paths.from_root(".github", "workflows", "nightly-status.yml")

RUN_ID = "30237524399"
RUN_URL = "https://github.com/rediacc/console/actions/runs/30237524399"

# Lifted verbatim from the twin's HARNESS heredoc. See the module docstring for why it is not translated.
HARNESS_CJS = r"""
const report = require(process.argv[2]);
const openIssues = JSON.parse(process.argv[3]);   // e.g. [] or [{number: 7}]
const labelExists = process.argv[4] === '1';
const existingComments = JSON.parse(process.argv[5] || '[]');
// JOBS SHAPE. `github.paginate` does not always hand back flattened job
// objects: for listJobsForWorkflowRun it can yield the RESPONSE objects
// ({total_count, jobs}) instead. The original fixture only ever produced the
// flat shape, which is why this suite stayed green while production reported
// "no job reported a non-success conclusion" for a nightly with NINE failures
// (run 30327872124). The shape is now a parameter so both are exercised.
const jobsShape = process.argv[6] || 'flat';

const trace = [];
const github = {
  paginate: async (fn, params) => {
    // Three paginated endpoints: listForRepo (open issues), listComments (the
    // run-id dedupe) and listJobsForWorkflowRun (the failed-job roster).
    if (params && params.labels) { trace.push(`list-issues:${params.labels}`); return openIssues; }
    if (params && params.issue_number) { trace.push(`list-comments:${params.issue_number}`); return existingComments; }
    trace.push('list-jobs');
    const flat = [
      { name: 'Stage Artifacts / Stage Artifacts', conclusion: 'failure', html_url: 'u1' },
      { name: 'Quality / Workflows', conclusion: 'failure', html_url: 'u2' },
      { name: 'Build (CLI) / Linux', conclusion: 'success', html_url: 'u3' },
      { name: 'Tests + Infra / E2E Ceph', conclusion: 'skipped', html_url: 'u4' },
    ];
    if (jobsShape === 'paged') return [{ total_count: flat.length, jobs: flat }];
    if (jobsShape === 'unreadable') return [{ total_count: 4 }, { total_count: 4 }];
    if (jobsShape === 'empty') return [];
    return flat;
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
"""


class Reporter:
    """The scratch harness plus a driver for one `report(...)` invocation."""

    def __init__(self, gate, tmp_path: pathlib.Path) -> None:
        self.gate = gate
        self.node = harness.require_tool(
            "node",
            "install Node 22 (the lane's setup-workspace step does this in CI)",
        )
        if not REPORTER.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(REPORTER))
        self.script = tmp_path / "harness.cjs"
        self.script.write_text(HARNESS_CJS, encoding="utf-8")

    def run(
        self,
        conclusion: str,
        event: str,
        open_issues: str,
        label_exists: str = "1",
        comments: str = "[]",
        jobs_shape: str = "flat",
    ) -> harness.RunResult:
        """`run_report`. The twin drops stderr; this keeps it for diagnostics.

        Keeping it changes no assertion: every assertion below reads a `TRACE=`
        or `BODY=` line off STDOUT, which is where the harness prints them, so
        stderr is available when something explodes instead of vanishing.
        """
        return harness.run(
            [
                self.node,
                str(self.script),
                str(REPORTER),
                open_issues,
                label_exists,
                comments,
                jobs_shape,
            ],
            env={
                "NIGHTLY_RUN_ID": RUN_ID,
                "NIGHTLY_CONCLUSION": conclusion,
                "NIGHTLY_EVENT": event,
                "NIGHTLY_URL": RUN_URL,
            },
        )

    def _line(self, result: harness.RunResult, prefix: str) -> str:
        if "THREW:" in result.out:
            self.gate.log_fail(
                "the reporter threw instead of running: %s (stderr: %s)"
                % (result.out.strip(), result.err.strip())
            )
        for line in result.out.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""

    def trace_of(self, *args: str) -> str:
        """`trace_of`. The `TRACE=` line, or "" when the module made no calls."""
        return self._line(self.run(*args), "TRACE=")

    def body_of(self, *args: str) -> str:
        """The `BODY=` line, still JSON-encoded, exactly as the twin greps it."""
        return self._line(self.run(*args), "BODY=")


def test_cancelled_is_not_green(gate, tmp_path):
    # THE LOAD-BEARING ASSERTION. Treating `cancelled` as green is the exact conflation that hid twelve red nights: the watchdog cancelled each failing run, so its conclusion read `cancelled`, and every reader took that for "superseded, ignore". If this ever returns true the whole reporter is inert.
    reporter = Reporter(gate, tmp_path)
    probe = (
        "const r = require(process.argv[1]);"
        'process.stdout.write([["success",r.isGreen("success")],'
        '["cancelled",r.isGreen("cancelled")],["failure",r.isGreen("failure")],'
        '["",r.isGreen("")]].map(([k,v])=>k+"="+v).join(","));'
    )
    out = harness.run([reporter.node, "-e", probe, str(REPORTER)])
    gate.assert_exit(0, out, "the isGreen probe must run")
    gate.assert_eq(
        out.out,
        "success=true,cancelled=false,failure=false,=false",
        "only 'success' is green; cancelled must NOT be",
    )
    gate.log_pass("cancelled is not green (%s)" % out.out)


def test_non_schedule_event_is_a_no_op(gate, tmp_path):
    # The second lock behind the workflow's own `if:`. A future trigger change must not silently start opening an issue for every PR run.
    reporter = Reporter(gate, tmp_path)
    gate.assert_eq(
        reporter.trace_of("failure", "pull_request", "[]"),
        "",
        "a pull_request run must produce no API calls at all",
    )
    gate.assert_eq(
        reporter.trace_of("failure", "push", "[]"),
        "",
        "a push run must produce no API calls at all",
    )
    gate.log_pass("only scheduled runs are reported on; every other event is inert")


def test_first_red_night_opens_one_issue(gate, tmp_path):
    trace = Reporter(gate, tmp_path).trace_of("cancelled", "schedule", "[]", "1")
    gate.assert_contains(
        trace,
        "create:Nightly CI is red:bug+automated+nightly-red",
        "the first red night opens one issue with the triage labels",
    )
    gate.assert_not_contains(trace, "comment:", "nothing to comment on yet")
    gate.log_pass("the first red night opens exactly one labelled issue (%s)" % trace)


def test_second_red_night_comments_instead_of_opening_another(gate, tmp_path):
    # The anti-spam claim. Twelve red nights must produce ONE issue with twelve comments, not twelve issues -- a wall of identical issues is its own kind of invisible.
    trace = Reporter(gate, tmp_path).trace_of("cancelled", "schedule", '[{"number":7}]')
    gate.assert_contains(trace, "comment:7", "a subsequent red night comments on the open issue")
    gate.assert_not_contains(trace, "create:", "it must NOT open a second issue")
    gate.log_pass("consecutive red nights accumulate on one issue (%s)" % trace)


def test_green_closes_the_open_issue(gate, tmp_path):
    trace = Reporter(gate, tmp_path).trace_of("success", "schedule", '[{"number":7}]')
    gate.assert_contains(trace, "comment:7", "the recovery is recorded on the issue")
    gate.assert_contains(trace, "update:7:closed", "a green nightly closes the issue automatically")
    gate.log_pass("a green nightly closes the rolling issue (%s)" % trace)


def test_green_with_nothing_open_is_a_no_op(gate, tmp_path):
    trace = Reporter(gate, tmp_path).trace_of("success", "schedule", "[]")
    gate.assert_not_contains(trace, "create:", "a green nightly with no open issue creates nothing")
    gate.assert_not_contains(trace, "comment:", "and comments nowhere")
    gate.log_pass("the steady green state is silent")


def test_missing_label_is_created_before_use(gate, tmp_path):
    # createIssue with an unknown label fails the ENTIRE call, so the label must be ensured first. `nightly-red` does not exist in the repo yet, so this is the path the very first red night will actually take.
    trace = Reporter(gate, tmp_path).trace_of("cancelled", "schedule", "[]", "0")
    gate.assert_contains(trace, "create-label:nightly-red", "the missing label is created")
    gate.assert_contains(trace, "create:Nightly CI is red", "and the issue is still opened")
    gate.log_pass("a missing nightly-red label is created before the issue uses it (%s)" % trace)


def test_body_names_the_failed_jobs(gate, tmp_path):
    # "The nightly failed" is not actionable: a 90-job run means opening it to find the two that matter. Successes and skips must be filtered out.
    body = Reporter(gate, tmp_path).body_of("cancelled", "schedule", "[]")
    gate.assert_contains(body, "Stage Artifacts", "the failing job is named")
    gate.assert_contains(body, "Quality / Workflows", "every failing job is named")
    gate.assert_not_contains(body, "Build (CLI) / Linux", "successful jobs are not listed")
    gate.assert_not_contains(body, "E2E Ceph", "skipped jobs are not listed")
    gate.assert_contains(body, RUN_ID, "the run id is linked for triage")
    gate.log_pass("the issue body names exactly the failing jobs")


def test_paginated_response_shape_still_names_jobs(gate, tmp_path):
    # THE REGRESSION THIS SUITE MISSED. `github.paginate` returned RESPONSE
    # objects ({total_count, jobs}) rather than flattened jobs, so every element
    # lacked `.conclusion`, the filter matched none of NINE real failures, and issue #544 told a human "no job reported a non-success conclusion". The old fixture only produced the flat shape, so the suite could not see it.
    body = Reporter(gate, tmp_path).body_of("failure", "schedule", "[]", "1", "[]", "paged")
    gate.assert_contains(
        body, "Stage Artifacts", "the failing job is named from the paginated shape"
    )
    gate.assert_contains(
        body, "Quality / Workflows", "every failing job is named from the paginated shape"
    )
    gate.assert_not_contains(body, "Build (CLI) / Linux", "successes are still filtered out")
    gate.log_pass("the paginated {total_count, jobs} shape is read as well as the flat one")


def test_unreadable_job_list_is_not_reported_as_clean(gate, tmp_path):
    # ANTI-VACUITY, and the actual lesson of #544. Zero READABLE jobs is evidence the read failed, never evidence that nothing failed. Reporting empty data as clean data is the defect class this whole programme exists to remove, so the body must say it could not tell rather than implying an all-green run.
    body = Reporter(gate, tmp_path).body_of("failure", "schedule", "[]", "1", "[]", "unreadable")
    gate.assert_contains(
        body, "could not read the job list", "an unreadable roster says so plainly"
    )
    gate.assert_not_contains(
        body,
        "none reported a non-success conclusion",
        "and must NOT imply every job passed",
    )
    gate.log_pass("an unreadable job list fails toward 'I could not tell', not 'nothing failed'")


def test_empty_job_list_is_not_reported_as_clean(gate, tmp_path):
    body = Reporter(gate, tmp_path).body_of("failure", "schedule", "[]", "1", "[]", "empty")
    gate.assert_contains(
        body, "could not read the job list", "an empty roster is treated as unreadable"
    )
    gate.log_pass("an empty job roster is also treated as a failed read")


def test_workflow_is_wired_to_schedule_runs_only(gate):
    # Anti-vacuity against the real workflow: the module is inert for non-schedule events, but the workflow must also not burn a job on every PR run.
    if not WORKFLOW.is_file():
        gate.log_fail(
            "the workflow that drives the reporter is missing: %s -- an assertion "
            "over a file nobody read is not an assertion" % paths.relative_to_root(WORKFLOW)
        )
    text = WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(text, "workflow_run", "the reporter is driven by workflow_run")
    gate.assert_contains(
        text,
        "github.event.workflow_run.event == 'schedule'",
        "the workflow filters to scheduled runs",
    )
    gate.assert_contains(text, "issues: write", "the job grants itself issues:write")
    gate.assert_contains(text, "report-nightly-status.cjs", "the workflow calls this module")
    gate.log_pass("nightly-status.yml is wired to scheduled runs with the right grant")


def test_a_rerun_of_the_same_night_does_not_double_comment(gate, tmp_path):
    # `workflow_run: completed` fires once per ATTEMPT and a run keeps its id across attempts, so a nightly whose failed jobs are re-run reaches this code twice for the same night. A duplicate comment per attempt makes a streak look longer than it is, and streak length is the one number this issue exists to communicate.
    same_night = json.dumps(
        [{"body": "### 2026-07-27 -- nightly [run %s](x) concluded `cancelled`" % RUN_ID}]
    )
    trace = Reporter(gate, tmp_path).trace_of(
        "cancelled", "schedule", '[{"number":7}]', "1", same_night
    )
    gate.assert_contains(trace, "list-comments:7", "existing comments are consulted")
    gate.assert_not_contains(trace, "comment:7", "the same run must not be reported twice")
    gate.log_pass("a rerun of the same night does not double-comment (%s)" % trace)


def test_a_different_night_still_comments(gate, tmp_path):
    # The control for the dedupe: it must suppress only the SAME run id, not every subsequent night. Getting this wrong would silence the streak entirely after night one.
    other_night = json.dumps(
        [{"body": "### 2026-07-26 -- nightly [run 30187728271](x) concluded `cancelled`"}]
    )
    trace = Reporter(gate, tmp_path).trace_of(
        "cancelled", "schedule", '[{"number":7}]', "1", other_night
    )
    gate.assert_contains(trace, "comment:7", "a new night is still reported on the rolling issue")
    gate.log_pass("a different night is still reported (the dedupe is per-run, not blanket)")


def test_dedupe_is_anchored_not_a_bare_substring(gate, tmp_path):
    # A LONGER run id that merely starts with these digits must not be mistaken
    # for this night. Run ids gain a digit over time, so a bare
    # `includes("run " + runId)` becomes wrong on its own schedule, and a false dedupe is SILENT, dropping a night from the streak with nothing to show. The posted format is always `[run <id>](<url>)`, so the marker is anchored on the closing bracket.
    longer = json.dumps(
        [{"body": "### earlier -- nightly [run %s0](x) concluded `cancelled`" % RUN_ID}]
    )
    trace = Reporter(gate, tmp_path).trace_of(
        "cancelled", "schedule", '[{"number":7}]', "1", longer
    )
    gate.assert_contains(
        trace,
        "comment:7",
        "a longer run id containing this one as a prefix must NOT suppress the comment",
    )
    gate.log_pass("the run-id dedupe is anchored, not a bare substring")


def test_a_pull_request_carrying_the_label_is_ignored(gate, tmp_path):
    # GitHub's issues API returns PULL REQUESTS as issues. A PR wearing this label would otherwise be adopted as the tracking issue: commented on, and CLOSED on the next green nightly.
    trace = Reporter(gate, tmp_path).trace_of(
        "success", "schedule", '[{"number":42,"pull_request":{"url":"x"}}]'
    )
    gate.assert_not_contains(
        trace, "update:42:closed", "a PR must never be closed by this workflow"
    )
    gate.assert_not_contains(trace, "comment:42", "and never commented on")
    gate.log_pass("a pull request carrying the label is filtered out")
