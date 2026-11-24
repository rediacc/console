"""Behavioural tests for `scripts/ci/report-budget-check.cjs`, the poster that ops-housekeeping.yml runs when the CI time budget check fails.

The mention and label cases were ported from the retired nightly-status report test (PLAN-health-checks-local R3); the nightly-only cases were deleted with the workflow.

WHAT BROKE. The nightly was red every night 2026-09-22..09-30 and each report landed on the rolling issue as a comment with no @mention and no assignee, so GitHub notified nobody for nine days. Every budget-check post mentions the `github_mentions` handles of `.ci/config/ops-health.json`.

WHY BEHAVIOURAL. The claims are about API CALLS (one issue opened, a comment instead of a second issue, the label created before use), so this drives the real module with a mocked GitHub client and asserts on the call trace.

NO `xdist_group`. Every case writes only into pytest's own `tmp_path` and reads the shipped config without writing it.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUBJECT = paths.from_root("scripts", "ci", "report-budget-check.cjs")
HEALTH_CONFIG = paths.from_root(".ci", "config", "ops-health.json")

RUN_ID = "30237524399"
PROBE = "ops-health-probe"

HARNESS_CJS = r"""
const report = require(process.argv[2]);
const openIssues = JSON.parse(process.argv[3]);
const labelExists = process.argv[4] === '1';
const existingComments = JSON.parse(process.argv[5] || '[]');

const trace = [];
const github = {
  paginate: async (fn, params) => {
    if (params && params.labels) { trace.push(`list-issues:${params.labels}`); return openIssues; }
    trace.push(`list-comments:${params.issue_number}`);
    return existingComments;
  },
  rest: {
    issues: {
      listForRepo: () => {}, listComments: () => {},
      create: async (p) => { trace.push(`create:${p.title}:${(p.labels||[]).join('+')}`); global.__body = p.body; return { data: { number: 99 } }; },
      createComment: async (p) => { trace.push(`comment:${p.issue_number}`); global.__body = p.body; return {}; },
      getLabel: async () => { if (!labelExists) throw new Error('404'); trace.push('label-exists'); return {}; },
      createLabel: async (p) => { trace.push(`create-label:${p.name}`); return {}; },
    },
  },
};
const core = { warning: (m) => trace.push(`warning:${String(m).slice(0, 24)}`) };
const context = { repo: { owner: 'rediacc', repo: 'console' } };

report({ github, context, core })
  .then(() => { console.log('TRACE=' + trace.join('|')); if (global.__body) console.log('BODY=' + JSON.stringify(global.__body)); })
  .catch((e) => { console.log('THREW:' + e.message); process.exitCode = 3; });
"""


class Poster:
    """The scratch harness plus a driver for one poster invocation."""

    def __init__(self, gate, tmp_path: pathlib.Path, config: pathlib.Path | None = None) -> None:
        self.gate = gate
        self.config = config
        self.node = harness.require_tool(
            "node",
            "install Node 22 (the lane's setup-workspace step does this in CI)",
        )
        if not SUBJECT.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUBJECT))
        self.script = tmp_path / "harness.cjs"
        self.script.write_text(HARNESS_CJS, encoding="utf-8")

    def run(
        self, open_issues: str, label_exists: str = "1", comments: str = "[]"
    ) -> harness.RunResult:
        env = {"GITHUB_RUN_ID": RUN_ID, "BUDGET_CHECK_SUMMARY_PATH": ""}
        if self.config is not None:
            env["OPS_HEALTH_CONFIG"] = str(self.config)
        return harness.run(
            [self.node, str(self.script), str(SUBJECT), open_issues, label_exists, comments],
            env=env,
        )

    def line(self, result: harness.RunResult, prefix: str) -> str:
        if "THREW:" in result.out:
            self.gate.log_fail(
                "the poster threw instead of running: %s (stderr: %s)"
                % (result.out.strip(), result.err.strip())
            )
        for line in result.out.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""

    def trace_of(self, *args: str) -> str:
        return self.line(self.run(*args), "TRACE=")

    def body_of(self, *args: str) -> str:
        return self.line(self.run(*args), "BODY=")


def _config(tmp_path: pathlib.Path, content: str | None) -> pathlib.Path:
    """An OPS_HEALTH_CONFIG fixture; `None` leaves the path absent."""
    cfg = tmp_path / "ops-health.json"
    if content is not None:
        cfg.write_text(content, encoding="utf-8")
    return cfg


def _probe_poster(gate, tmp_path) -> Poster:
    return Poster(gate, tmp_path, _config(tmp_path, json.dumps({"github_mentions": [PROBE]})))


def test_real_config_names_someone(gate):
    # Anti-vacuity for every mention case: the fixtures prove the mechanism, this proves the shipped file feeds it a handle.
    data = json.loads(HEALTH_CONFIG.read_text(encoding="utf-8"))
    handles = [h for h in data.get("github_mentions", []) if isinstance(h, str) and h.strip()]
    gate.assert_eq(
        bool(handles), True, "ops-health.json must list at least one github_mentions handle"
    )
    gate.log_pass("ops-health.json mentions %s" % handles)


def test_failure_mentions_on_the_open_issue(gate, tmp_path):
    body = _probe_poster(gate, tmp_path).body_of('[{"number":7}]')
    gate.assert_contains(body, "budget check failed", "the budget-check comment is the one posted")
    gate.assert_contains(body, "@" + PROBE, "a budget-check comment mentions the configured handle")
    gate.log_pass("the budget check mentions the operator on a comment")


def test_failure_mentions_on_the_issue_it_opens(gate, tmp_path):
    body = _probe_poster(gate, tmp_path).body_of("[]")
    gate.assert_contains(body, "@" + PROBE, "the issue the budget check opens mentions too")
    gate.log_pass("the budget check mentions the operator on a new issue")


def test_first_failure_opens_one_labelled_issue(gate, tmp_path):
    trace = _probe_poster(gate, tmp_path).trace_of("[]", "1")
    gate.assert_contains(
        trace,
        "create:Nightly CI is red:bug+automated+nightly-red",
        "the first failure opens one issue with the triage labels",
    )
    gate.assert_not_contains(trace, "comment:", "nothing to comment on yet")
    gate.log_pass("the first failure opens exactly one labelled issue (%s)" % trace)


def test_later_failure_comments_instead_of_opening_another(gate, tmp_path):
    trace = _probe_poster(gate, tmp_path).trace_of('[{"number":7}]')
    gate.assert_contains(trace, "comment:7", "a later failure comments on the open issue")
    gate.assert_not_contains(trace, "create:", "it must NOT open a second issue")
    gate.log_pass("consecutive failures accumulate on one issue (%s)" % trace)


def test_missing_label_is_created_before_use(gate, tmp_path):
    # createIssue with an unknown label fails the whole call, so the label is ensured first.
    trace = _probe_poster(gate, tmp_path).trace_of("[]", "0")
    gate.assert_contains(trace, "create-label:nightly-red", "the missing label is created")
    gate.assert_contains(trace, "create:Nightly CI is red", "and the issue is still opened")
    gate.log_pass("a missing nightly-red label is created before the issue uses it (%s)" % trace)


def test_same_run_is_not_commented_twice(gate, tmp_path):
    same = json.dumps(
        [
            {
                "body": "### 2026-07-27 -- CI time budget check failed ([budget-check run %s](x))"
                % RUN_ID
            }
        ]
    )
    trace = _probe_poster(gate, tmp_path).trace_of('[{"number":7}]', "1", same)
    gate.assert_contains(trace, "list-comments:7", "existing comments are consulted")
    gate.assert_not_contains(trace, "comment:7", "the same run must not be reported twice")
    gate.log_pass("a rerun of the same run does not double-comment (%s)" % trace)


def test_dedupe_is_anchored_not_a_bare_substring(gate, tmp_path):
    # A longer run id that starts with these digits must not suppress the comment.
    longer = json.dumps([{"body": "### earlier -- ([budget-check run %s0](x))" % RUN_ID}])
    trace = _probe_poster(gate, tmp_path).trace_of('[{"number":7}]', "1", longer)
    gate.assert_contains(
        trace, "comment:7", "a longer run id with this one as a prefix must not suppress"
    )
    gate.log_pass("the run-id dedupe is anchored, not a bare substring")


def _assert_degrades_loudly(gate, poster, what):
    result = poster.run('[{"number":7}]')
    gate.assert_exit(0, result, "a %s config must not crash the poster" % what)
    gate.assert_not_contains(result.out, "THREW:", "the poster must not throw")
    trace = poster.line(result, "TRACE=")
    body = poster.line(result, "BODY=")
    gate.assert_contains(trace, "comment:7", "the report still posts with a %s config" % what)
    gate.assert_not_contains(body, "@", "a %s config mentions nobody" % what)
    gate.assert_contains(result.out, "WARNING ops-health:", "a %s config is logged" % what)
    gate.assert_contains(trace, "warning:ops-health:", "and raised as a workflow warning")


def test_missing_config_warns_and_mentions_nobody(gate, tmp_path):
    _assert_degrades_loudly(gate, Poster(gate, tmp_path, _config(tmp_path, None)), "missing")
    gate.log_pass("a missing ops-health.json posts unmentioned and warns")


def test_empty_mention_list_warns_and_mentions_nobody(gate, tmp_path):
    cfg = _config(tmp_path, '{"github_mentions": []}')
    _assert_degrades_loudly(gate, Poster(gate, tmp_path, cfg), "empty")
    gate.log_pass("an empty github_mentions list posts unmentioned and warns")
