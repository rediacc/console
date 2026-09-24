"""Port of `.ci/scripts/test/gates/test-label-guide-comment.sh`, retired in W7 P5.

WHAT IT GUARDS. The repo carries twelve labels, several of them kill switches whose effect is invisible unless you already know they exist. The module posts one comment per PR explaining them, rendered from `.github/labels.yml`, and the contract it has to keep is create/update/NO-OP: a PR gets a CI run per push, so a poster that wrote unconditionally would bury the conversation.

THE NODE HARNESS IS THE TWIN'S, BYTE FOR BYTE, including the `@@RENDER@@` sentinel that means "byte-identical to what the module would render right now". Hand-copying an expected body into a fixture would make the no-op case pass for the wrong reason the moment the renderer changed, and translating the mock would mean the two sides drive the subject differently, which is the one
thing a port must not do.

WHERE THIS REIMPLEMENTS AWK AND GREP, AND WHY THE ANSWERS AGREE:

  * The job block. The twin runs
    `awk '/^  label-guide:/{f=1} f&&/^  [a-z][a-z0-9-]*:$/&&!/^  label-guide:/{exit} f'`.
    `slice_job()` below is that program written out: start printing at the first
    line matching the opening pattern, stop at the first later line that is a
    bare top-level job key. Both are line-oriented and neither uses a regex
    feature the other lacks, so they select the same lines.
  * The row count. The twin runs `grep -o '| \\`fixture-' | wc -l`, which counts
    NON-OVERLAPPING occurrences across the whole text; `str.count` on the same
    literal is the same count, because the needle cannot overlap itself.
  * The declaration counts. `grep -cE '^- name:'` counts matching LINES, not
    matches, so the Python side counts lines rather than `re.findall` hits. On
    this corpus the two agree, and the line form is what the twin claims.

WHY `| \\`` AND NOT `|` ALONE for the real-file row count: the body escapes a pipe inside a description as `\\|`, so a bare pipe count would also count those. The backtick is what makes it a NAME cell.

NO `xdist_group`. Fixtures are written into pytest's own `tmp_path`, the tracked files (`.github/labels.yml`, `.github/workflows/ci.yml`) are read and never written, and `assert-ci-complete.sh` is driven read-only. Nothing is bound and no module global is mutated.
"""

import json
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MODULE = paths.from_root(".ci", "scripts", "ci", "label-guide-comment.cjs")
REAL_LABELS = paths.from_root(".github", "labels.yml")
CI_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")
ASSERT_CI_COMPLETE = paths.from_root(".ci", "scripts", "ci", "assert-ci-complete.sh")

# Fixture labels file with a KNOWN set. Every name here must appear in the rendered table, and the row count is asserted, so a renderer that quietly drops entries cannot pass by rendering "enough" of them.
FIXTURE_LABELS = """\
# A comment line, which the reader must skip rather than choke on.
- name: fixture-alpha
  color: "FEF2C0"
  description: "First fixture label"

# Another comment, mid-file.
- name: fixture-beta
  color: "1D76DB"
  description: "Second fixture label"

- name: fixture-gamma
  color: "B60205"
  description: "Third fixture label, with a | pipe in it"

# guide: false -- declared, reconciled by the inventory gate, NOT listed.
- name: fixture-hidden
  color: "cfd3d7"
  description: "Fourth fixture label, deliberately kept out of the guide"
  guide: false

# The explicit-true control: the field is readable in both directions, so a
# parser that treated ANY `guide:` line as "hide" would fail here.
- name: fixture-shown
  color: "0E8A16"
  description: "Fifth fixture label, explicitly opted in"
  guide: true
"""

# Guide-visible rows expected from the fixture: alpha, beta, gamma (field absent) plus fixture-shown (explicitly true). fixture-hidden is excluded.
FIXTURE_COUNT = 4
FIXTURE_DECLARED = 5

HARNESS_CJS = r"""
const mod = require(process.argv[2]);
const comments = JSON.parse(process.argv[3]);

// A fixture body of "@@RENDER@@" means "byte-identical to what the module would
// render right now". Hand-copying the expected body into the fixture would make
// the no-op case pass for the wrong reason the moment the renderer changed.
// Resolved LAZILY: the malformed-file cases expect the MODULE to throw, and
// pre-rendering here would throw first, outside the catch, printing nothing.
const fs = require('node:fs');
if (comments.some((c) => c.body === '@@RENDER@@')) {
  const rendered = mod.renderBody(mod.parseLabels(fs.readFileSync(process.env.LABEL_GUIDE_LABELS_FILE, 'utf8'), 'fixture'));
  for (const c of comments) if (c.body === '@@RENDER@@') c.body = rendered;
}

const trace = [];
const github = {
  paginate: async (fn, params) => { trace.push(`list-comments:${params.issue_number}`); return comments; },
  rest: {
    issues: {
      listComments: () => {},
      createComment: async (p) => { trace.push(`create:${p.issue_number}`); global.__body = p.body; return {}; },
      updateComment: async (p) => { trace.push(`update:${p.comment_id}`); global.__body = p.body; return {}; },
    },
  },
};
const core = { info: (m) => trace.push(`info:${String(m).slice(0, 12)}`) };
const context = { repo: { owner: 'rediacc', repo: 'console' }, payload: { pull_request: { number: 5 } } };

mod({ github, context, core })
  .then((verdict) => {
    console.log('TRACE=' + trace.join('|'));
    console.log('VERDICT=' + verdict);
    if (global.__body) console.log('BODY=' + JSON.stringify(global.__body));
  })
  .catch((e) => { console.log('THREW=' + e.message.replace(/\n/g, ' ')); process.exitCode = 3; });
"""

BOT = {"type": "Bot", "login": "github-actions[bot]"}
HUMAN = {"type": "User", "login": "an-outsider"}
MARKER = "<!-- rediacc:label-guide -->"

DECLARED_RE = re.compile(r"^- name:", re.MULTILINE)
HIDDEN_RE = re.compile(r"^[ \t]+guide:[ \t]*false[ \t]*$", re.MULTILINE)
JOB_KEY_RE = re.compile(r"^  [a-z][a-z0-9-]*:$")


class Guide:
    """The scratch harness, plus the twin's `run_guide` / `trace_of` / `body_of`."""

    def __init__(self, gate, tmp_path: pathlib.Path) -> None:
        self.gate = gate
        self.tmp = tmp_path
        self.node = harness.require_tool(
            "node",
            "install Node 22 (the lane's setup-workspace step does this in CI)",
        )
        if not MODULE.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(MODULE))
        self.script = tmp_path / "harness.cjs"
        self.script.write_text(HARNESS_CJS, encoding="utf-8")
        self.labels = tmp_path / "labels.yml"
        self.labels.write_text(FIXTURE_LABELS, encoding="utf-8")

    def write(self, name: str, body: str) -> pathlib.Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    def run(self, labels_file: pathlib.Path, comments: object) -> str:
        """`run_guide`. The twin drops stderr and swallows the exit code with `|| true`, because several cases EXPECT the module to throw and the
        harness reports that on stdout as `THREW=`. Same here: the return code is
        not read, only the stdout lines are."""
        result = harness.run(
            [self.node, str(self.script), str(MODULE), json.dumps(comments)],
            env={"LABEL_GUIDE_LABELS_FILE": str(labels_file)},
        )
        return result.out

    def _line(self, out: str, prefix: str) -> str:
        for line in out.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""

    def trace_of(self, labels_file: pathlib.Path, comments: object) -> str:
        return self._line(self.run(labels_file, comments), "TRACE=")

    def verdict_of(self, labels_file: pathlib.Path, comments: object) -> str:
        return self._line(self.run(labels_file, comments), "VERDICT=")

    def body_of(self, labels_file: pathlib.Path, comments: object) -> str:
        return self._line(self.run(labels_file, comments), "BODY=")


def slice_job(text: str, key: str) -> str:
    """The twin's awk program: `key`'s block, up to the next top-level job key."""
    opening = "  %s:" % key
    lines = text.splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        if not started:
            if line.startswith(opening):
                started = True
                out.append(line)
            continue
        if JOB_KEY_RE.match(line) and not line.startswith(opening):
            break
        out.append(line)
    return "\n".join(out)


def test_creates_when_absent(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    trace = guide.trace_of(guide.labels, [])
    verdict = guide.verdict_of(guide.labels, [])
    gate.assert_eq(
        trace, "list-comments:5|create:5", "an absent guide is posted, after exactly one read"
    )
    gate.assert_eq(verdict, "created", "and the module says so")
    gate.log_pass("the guide is created when the PR has none (%s)" % trace)


def test_ignores_unrelated_comments(gate, tmp_path):
    # The control for the finder: ordinary PR chatter must not be mistaken for the guide, or the guide would never be posted on a busy PR.
    guide = Guide(gate, tmp_path)
    trace = guide.trace_of(
        guide.labels,
        [
            {"id": 1, "body": "looks good to me", "user": HUMAN},
            {"id": 2, "body": "rerunning CI", "user": BOT},
        ],
    )
    gate.assert_contains(trace, "create:5", "unrelated comments do not count as the guide")
    gate.log_pass("unrelated comments are ignored (%s)" % trace)


def test_updates_when_the_body_differs(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    stale = [
        {"id": 77, "body": "%s\n### Label guide\n\nstale contents" % MARKER, "user": BOT},
    ]
    trace = guide.trace_of(guide.labels, stale)
    verdict = guide.verdict_of(guide.labels, stale)
    gate.assert_contains(trace, "update:77", "a stale guide is rewritten in place")
    gate.assert_not_contains(trace, "create:", "and NOT duplicated as a second comment")
    gate.assert_eq(verdict, "updated", "and the module says so")
    gate.log_pass("a stale guide is updated in place (%s)" % trace)


def test_identical_body_performs_no_write_at_all(gate, tmp_path):
    # THE LOAD-BEARING CASE. Asserted as trace EQUALITY: "no create" alone would be satisfied by a module that calls updateComment on every run, which is the same spam wearing a different verb.
    guide = Guide(gate, tmp_path)
    current = [{"id": 77, "body": "@@RENDER@@", "user": BOT}]
    trace = guide.trace_of(guide.labels, current)
    verdict = guide.verdict_of(guide.labels, current)
    gate.assert_eq(
        trace, "list-comments:5", "a current guide must produce ZERO API writes, only the read"
    )
    gate.assert_eq(verdict, "unchanged", "and the module reports the no-op")
    gate.log_pass("an up-to-date guide is left completely alone (%s)" % trace)


def test_a_non_bot_marker_comment_cannot_suppress_the_guide(gate, tmp_path):
    # Anyone who can comment on a PR could otherwise post an empty comment carrying the marker and silence the guide forever.
    guide = Guide(gate, tmp_path)
    trace = guide.trace_of(
        guide.labels,
        [{"id": 9, "body": "%s\nnothing to see here" % MARKER, "user": HUMAN}],
    )
    gate.assert_contains(trace, "create:5", "a human-authored marker comment is not the guide")
    gate.assert_not_contains(trace, "update:9", "and is never rewritten")
    gate.log_pass("an outsider's fake guide cannot suppress the real one (%s)" % trace)


def test_body_renders_every_declared_label(gate, tmp_path):
    # Driven from the fixture so the COUNT can be asserted. A renderer that silently drops entries would otherwise stay green forever: a table with most of the labels looks exactly like a table with all of them.
    guide = Guide(gate, tmp_path)
    body = guide.body_of(guide.labels, [])
    gate.assert_contains(body, "fixture-alpha", "the first label is rendered")
    gate.assert_contains(body, "fixture-beta", "the second label is rendered")
    gate.assert_contains(body, "fixture-gamma", "the third label is rendered")
    gate.assert_contains(body, "First fixture label", "descriptions are rendered, not just names")
    rows = body.count("| `fixture-")
    gate.assert_eq(rows, FIXTURE_COUNT, "exactly one table row per guide-visible label")
    gate.log_pass("every guide-visible label reaches the table (%d rows)" % rows)


def test_guide_false_is_omitted_and_its_control_is_present(gate, tmp_path):
    # `guide: false` means "declared so the inventory gate is satisfied, but do NOT list it". THE CONTROL IS THE POINT: an assertion that fixture-hidden is absent is satisfied just as well by a renderer that dropped everything, so the two opt-IN shapes are asserted in the same breath.
    guide = Guide(gate, tmp_path)
    body = guide.body_of(guide.labels, [])
    gate.assert_not_contains(body, "fixture-hidden", "a guide:false label is not listed")
    gate.assert_not_contains(body, "deliberately kept out", "nor is its description")
    gate.assert_contains(body, "fixture-shown", "an explicitly guide:true label IS listed")
    gate.assert_contains(body, "fixture-alpha", "and so is one with no guide field at all")
    gate.log_pass("guide:false hides a label; both opt-in shapes still render")


def test_the_omitted_count_is_stated(gate, tmp_path):
    # A reader who applies `duplicate` and cannot find it in the table needs to know the omission was deliberate rather than a bug in this comment.
    guide = Guide(gate, tmp_path)
    body = guide.body_of(guide.labels, [])
    gate.assert_contains(
        body,
        "%d further label(s) exist and are deliberately left off"
        % (FIXTURE_DECLARED - FIXTURE_COUNT),
        "the body accounts for the labels it does not list",
    )
    gate.log_pass("the rendered body states how many labels it deliberately omits")


def test_a_malformed_guide_value_fails_loudly(gate, tmp_path):
    # Coercion here is the dangerous shape: `guide: no` read as a truthy string would SHOW a label meant to be hidden, and `guide: yes` under a falsy-string reading would hide one meant to be shown.
    guide = Guide(gate, tmp_path)
    bad = guide.write(
        "badguide.yml",
        '- name: ok-one\n  description: "fine"\n- name: ok-two\n  description: "fine"\n  guide: no\n',
    )
    out = guide.run(bad, [])
    gate.assert_contains(out, "THREW=", "a non-boolean guide value must throw")
    gate.assert_contains(out, "exactly 'true' or 'false'", "and say what was expected")
    gate.log_pass("a malformed guide value is a loud parse failure, never a coercion")


def test_hiding_everything_trips_the_guide_floor(gate, tmp_path):
    # The second vacuity route: a parser change that mis-read the field would mark every entry hidden while the declaration count still cleared MIN_LABELS, and the table would come out empty with nothing complaining.
    guide = Guide(gate, tmp_path)
    hidden = guide.write(
        "allhidden.yml",
        '- name: ok-one\n  description: "fine"\n  guide: false\n'
        '- name: ok-two\n  description: "fine"\n  guide: false\n'
        '- name: ok-three\n  description: "fine"\n  guide: false\n',
    )
    out = guide.run(hidden, [])
    gate.assert_contains(out, "THREW=", "an all-hidden file must throw")
    gate.assert_contains(out, "floor", "and name the guide floor")
    gate.assert_not_contains(out, "create:5", "and must NOT post an empty table")
    gate.log_pass("an empty guide set trips its own floor rather than posting a blank table")


def test_body_says_it_is_generated(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.body_of(guide.labels, [])
    gate.assert_contains(body, ".github/labels.yml", "the body names its source of truth")
    gate.assert_contains(body, "next CI run overwrites it", "and warns against hand-editing")
    # AND IT MUST BE READABLE. This trailer is the only thing that tells a reader their edits get overwritten, so rendering it as <sub> (tiny subscript text, exactly where an eye skips) defeats the one job it has.
    gate.assert_not_contains(body, "<sub>", "the trailer must not render as tiny subscript text")
    gate.assert_contains(body, "> Generated from", "it renders as a normal-size blockquote footer")
    gate.log_pass("the rendered body tells a human not to hand-edit it, at a size they can read")


def test_a_pipe_in_a_description_does_not_break_the_table(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.body_of(guide.labels, [])
    # BODY= is JSON-escaped, so the rendered `\|` reads as `\\|`.
    gate.assert_contains(body, r"\\| pipe in it", "a pipe inside a description is escaped")
    gate.log_pass("a pipe in a description is escaped rather than splitting the row")


def test_malformed_labels_file_fails_loudly(gate, tmp_path):
    # The failure mode this replaces: a grep-shaped reader that picks out the lines it recognises and silently yields a SHORT table.
    guide = Guide(gate, tmp_path)
    bad = guide.write(
        "bad.yml",
        '- name: ok-one\n  description: "fine"\n- name: ok-two\n  description: "fine"\n'
        "this line is not yaml we understand\n",
    )
    out = guide.run(bad, [])
    gate.assert_contains(out, "THREW=", "a malformed labels file must throw")
    gate.assert_not_contains(out, "create:5", "and must NOT post a partial guide")
    gate.log_pass("a malformed labels file fails loudly instead of rendering a short table")


def test_a_label_without_a_description_fails_loudly(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    bad = guide.write(
        "nodesc.yml",
        '- name: ok-one\n  description: "fine"\n- name: no-desc\n  color: "FFFFFF"\n',
    )
    out = guide.run(bad, [])
    gate.assert_contains(out, "THREW=", "a description-less label must throw")
    gate.assert_contains(out, "no-desc", "and must name the offender")
    gate.log_pass("a label with no description is refused (the guide exists to explain labels)")


def test_a_truncated_labels_file_trips_the_floor(gate, tmp_path):
    # Strict parsing rejects malformed lines but cannot notice a file truncated to something still well-formed. The floor covers that.
    guide = Guide(gate, tmp_path)
    short = guide.write("short.yml", '- name: only-one\n  description: "lonely"\n')
    out = guide.run(short, [])
    gate.assert_contains(out, "THREW=", "a one-label file must throw")
    gate.assert_contains(
        out, "floor", "and must say the read is broken, not that the file is short"
    )
    gate.log_pass("a truncated labels file trips the anti-vacuity floor")


def test_the_real_labels_file_renders_every_label(gate, tmp_path):
    # ANTI-VACUITY against the real tree: the fixture cases prove the renderer works on a file this test wrote, which says nothing about the real one. The expected count is DERIVED from the real file (declared minus guide:false), never hardcoded.
    guide = Guide(gate, tmp_path)
    if not REAL_LABELS.is_file():
        gate.log_fail("the real labels file is missing: %s" % paths.relative_to_root(REAL_LABELS))
    text = REAL_LABELS.read_text(encoding="utf-8")
    declared = len(DECLARED_RE.findall(text))
    hidden = len(HIDDEN_RE.findall(text))
    expected = declared - hidden
    body = guide.body_of(REAL_LABELS, [])
    rows = body.count("| `")
    gate.assert_eq(rows, expected, "the real guide lists exactly the guide-visible labels")

    # Anti-vacuity on the filter itself: if the real file ever stopped carrying any guide:false entry, the equality above would hold trivially and this
    # case would stop testing the filter at all.
    if hidden <= 0:
        gate.log_fail(
            "the real labels file carries no guide:false entry, so this case no longer "
            "exercises the filter"
        )

    gate.assert_contains(body, "rollback", "the rollback kill switch is explained")
    gate.assert_contains(body, "full-ci", "the scope-engine kill switch is explained")
    gate.assert_not_contains(
        body, "good first issue", "a stock GitHub default is kept out of the guide"
    )
    gate.log_pass(
        "the real labels file renders %d of %d labels (%d opted out)" % (rows, declared, hidden)
    )


def test_ci_yml_wires_the_job_with_the_narrowest_grant(gate):
    # The module is inert unless ci.yml actually calls it, and the whole reason it is its OWN job is the permission: pull-requests:write must not be added to `initialize`, which carries a 20-step surface.
    if not CI_WORKFLOW.is_file():
        gate.log_fail("ci.yml is missing: %s" % paths.relative_to_root(CI_WORKFLOW))
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(workflow, "label-guide-comment.cjs", "ci.yml calls this module")
    gate.assert_contains(workflow, "  label-guide:", "the dedicated job exists")
    gate.assert_contains(workflow, "RESULT_LABEL_GUIDE", "its result reaches ci-complete")

    job = slice_job(workflow, "label-guide")
    if not job:
        gate.log_fail(
            "the label-guide job block came out EMPTY, so every assertion below would "
            "pass or fail for the wrong reason"
        )
    gate.assert_contains(job, "pull-requests: write", "the job grants itself the write it needs")
    gate.assert_contains(job, "contents: read", "and nothing wider than read on contents")
    gate.assert_not_contains(job, "packages:", "no unrelated grant leaks in")
    gate.assert_not_contains(job, "issues:", "and no issues grant (PR comments do not need one)")
    gate.assert_contains(job, "needs: [initialize]", "it runs after initialize")
    gate.assert_contains(job, "runs-on: ubuntu-slim", "on the cheap runner")

    # ubuntu-slim has a HARD 15-minute platform cap; check-workflow-gates CHECK 3
    # requires <= 14, and a job over it is CANCELLED with no failing step.
    found = re.search(r"^ *timeout-minutes: *(\d+)", job, re.MULTILINE)
    if not found:
        gate.log_fail("the label-guide job declares no timeout-minutes")
    timeout = int(found.group(1))
    if timeout > 14:
        gate.log_fail(
            "label-guide timeout-minutes is %d; ubuntu-slim caps at 15 and the gate "
            "requires <= 14" % timeout
        )
    gate.log_pass(
        "ci.yml wires label-guide as its own job with pull-requests:write and a %dm timeout"
        % timeout
    )


def test_assert_ci_complete_judges_the_job(gate):
    # A job absent from the aggregator can go red while `CI Complete` stays green. SOFT, not HARD: the job legitimately skips on push-to-main.
    if not ASSERT_CI_COMPLETE.is_file():
        gate.log_fail("the aggregator is missing: %s" % paths.relative_to_root(ASSERT_CI_COMPLETE))
    result = harness.run(["bash", str(ASSERT_CI_COMPLETE)])
    gate.assert_exit(1, result, "the assertion script must fail when nothing is passed")
    gate.assert_contains(result.combined, "LABEL_GUIDE", "LABEL_GUIDE is one of the judged jobs")
    gate.log_pass("assert-ci-complete.sh judges LABEL_GUIDE")
