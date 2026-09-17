"""Port of `.ci/scripts/test/gates/test-autopilot-guide-comment.sh`.

Structurally a mirror of the label-guide port, because the module is a mirror of that poster: same marker discipline, same bot-only ownership, same create/update/no-op contract driven against a fake GitHub client and asserted on the call trace. What differs is the CONTENT half, where every documented fact is re-derived from the file it came from, so a rename in `autopilot.yml`,
`autopilot-gate.sh` or `resolve-model-args.sh` turns this red instead of leaving a wrong comment sitting on every PR.

THE NODE HARNESS IS THE TWIN'S, BYTE FOR BYTE, `@@RENDER@@` sentinel included. See the label-guide port's docstring for why a mock is never translated.

WHERE THIS REIMPLEMENTS sed, grep AND awk, AND WHY THE ANSWERS AGREE:

  * `slice_job()` is the twin's awk one-liner written out. Same claim as in the
    label-guide port, same reasoning.
  * The three NUMBERS (round cap, and the two `--max-turns` values) come from
    `sed -n 's/.../\\1/p' | head -1` in the twin and from `re.search` here. sed
    prints every match and the twin then takes the first; `re.search` returns the
    first. Same string while the sources carry one such assignment each, and this
    module REFUSES when the pattern matches nothing rather than comparing against
    an empty string, which is what the twin's `[ -n "$cap" ]` guard does.
  * `grep -c -F "$MARKER"` counts matching LINES, not occurrences, so the marker
    uniqueness check here counts LINES containing the marker. Stated because the
    two are different numbers for a body that repeated the marker twice on one
    line, and the twin's claim is the line one.
  * `wc -c` counts BYTES, so the size comparison encodes to UTF-8 before
    measuring rather than using `len()` on a str, which would count code points
    and silently disagree the first time a non-ASCII character entered either
    guide.

NO `xdist_group`. The harness is written into pytest's own `tmp_path`; every
other file this touches is read and never written. Nothing is bound and no module global is mutated.
"""

import json
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-autopilot-guide-comment.sh"

MODULE = paths.from_root(".ci", "scripts", "ci", "autopilot-guide-comment.cjs")
LABEL_MODULE = paths.from_root(".ci", "scripts", "ci", "label-guide-comment.cjs")
AUTOPILOT_WF = paths.from_root(".github", "workflows", "autopilot.yml")
GATE_SH = paths.from_root(".ci", "scripts", "autopilot", "autopilot-gate.sh")
MODEL_ARGS_SH = paths.from_root(".ci", "scripts", "autopilot", "resolve-model-args.sh")
LABELS_FILE = paths.from_root(".github", "labels.yml")
CI_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")

REQUIRED_INPUTS = (MODULE, AUTOPILOT_WF, GATE_SH, MODEL_ARGS_SH, LABELS_FILE, CI_WORKFLOW)

HARNESS_CJS = r"""
const mod = require(process.argv[2]);
const comments = JSON.parse(process.argv[3]);

// A fixture body of "@@RENDER@@" means "byte-identical to what the module would
// render right now". Hand-copying the expected body into the fixture would make
// the no-op case pass for the wrong reason the moment the renderer changed.
for (const c of comments) if (c.body === '@@RENDER@@') c.body = mod.renderBody();

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
MARKER = "<!-- rediacc:autopilot-guide -->"

DISPATCH_INPUTS = ("pr_number", "model", "max_rounds", "effort", "debug-shell")
ROUND_ACTIONS = ("fix", "ready-flip", "review-response", "done")
STOP_LABELS = ("autopilot", "autopilot-blocked")

# The twin's `[ ... -ge 10 ]` floor on the documented variable roster.
MIN_VARIABLES = 10

JOB_KEY_RE = re.compile(r"^  [a-z][a-z0-9-]*:$")
CAP_RE = re.compile(r'^MAX_ROUNDS="\$\{AUTOPILOT_MAX_ROUNDS:-([0-9]*)\}"', re.MULTILINE)
TURNS_OTHER_RE = re.compile(r"^turns=([0-9]+)$", re.MULTILINE)
TURNS_FIX_RE = re.compile(r'"fix" \]\] && turns=([0-9]+)')


class Guide:
    """The scratch harness plus the twin's `run_guide` / `trace_of` / `rendered_body`."""

    def __init__(self, gate, tmp_path: pathlib.Path) -> None:
        self.gate = gate
        self.node = harness.require_tool(
            "node",
            "install Node 22 (the lane's setup-workspace step does this in CI)",
        )
        # The twin's load-time loop: every input must be readable, because this test verifies the guide AGAINST its sources and cannot run without them.
        for path in REQUIRED_INPUTS:
            if not path.is_file():
                gate.log_fail(
                    "missing input: %s (this test verifies the guide against its sources; "
                    "it cannot run without them)" % paths.relative_to_root(path)
                )
        self.script = tmp_path / "harness.cjs"
        self.script.write_text(HARNESS_CJS, encoding="utf-8")

    def run(self, comments: object) -> str:
        """`run_guide`. Exit code deliberately unread: several cases expect the
        module to throw, and the harness reports that on stdout as `THREW=`."""
        return harness.run([self.node, str(self.script), str(MODULE), json.dumps(comments)]).out

    def _line(self, out: str, prefix: str) -> str:
        for line in out.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""

    def trace_of(self, comments: object) -> str:
        return self._line(self.run(comments), "TRACE=")

    def verdict_of(self, comments: object) -> str:
        return self._line(self.run(comments), "VERDICT=")

    def rendered_body(self) -> str:
        """The rendered body, UNESCAPED, for the content assertions."""
        result = harness.run(
            [
                self.node,
                "-e",
                "process.stdout.write(require(process.argv[1]).renderBody())",
                str(MODULE),
            ]
        )
        if result.rc != 0:
            self.gate.log_fail(
                "renderBody() did not run (rc=%d, stderr: %s)" % (result.rc, result.err.strip())
            )
        if not result.out.strip():
            self.gate.log_fail(
                "renderBody() produced an EMPTY body, so every content assertion below "
                "would be judging nothing"
            )
        return result.out


def slice_job(text: str, key: str) -> str:
    """The twin's awk program: `key`'s block, up to the next top-level job key."""
    opening = "  %s:" % key
    out: list[str] = []
    started = False
    for line in text.splitlines():
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
    trace = guide.trace_of([])
    verdict = guide.verdict_of([])
    gate.assert_eq(
        trace, "list-comments:5|create:5", "an absent guide is created, with no update call"
    )
    gate.assert_eq(verdict, "created", "and says so")
    gate.log_pass("no guide yet => exactly one createComment")


def test_ignores_unrelated_comments(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    trace = guide.trace_of(
        [
            {"id": 1, "user": BOT, "body": "CI failed on this one"},
            {"id": 2, "user": HUMAN, "body": "looks good"},
        ]
    )
    gate.assert_eq(
        trace, "list-comments:5|create:5", "ordinary chatter is not mistaken for the guide"
    )
    gate.log_pass("unrelated comments are ignored, the guide is still created")


def test_updates_when_the_body_differs(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    stale = [{"id": 77, "user": BOT, "body": "%s\nan old, stale guide" % MARKER}]
    gate.assert_eq(
        guide.trace_of(stale),
        "list-comments:5|update:77|info:Autopilot gu",
        "a stale guide is UPDATED in place, never re-created",
    )
    gate.assert_eq(guide.verdict_of(stale), "updated", "and says so")
    gate.log_pass("stale guide => updateComment on the existing id, no duplicate")


def test_identical_body_performs_no_write_at_all(gate, tmp_path):
    # THE LOAD-BEARING CASE, and the one PR #555 proved for the label guide: a PR gets a CI run per push, so a poster that wrote unconditionally would bury the conversation. Asserted as an EXACT trace: "no create" alone would be satisfied by a module that called updateComment on every single run.
    guide = Guide(gate, tmp_path)
    current = [{"id": 77, "user": BOT, "body": "@@RENDER@@"}]
    gate.assert_eq(
        guide.trace_of(current), "list-comments:5", "an unchanged guide performs ZERO writes"
    )
    gate.assert_eq(guide.verdict_of(current), "unchanged", "and reports itself as unchanged")
    gate.log_pass("identical body => read-only run (no create, no update, idempotent)")


def test_a_non_bot_marker_comment_cannot_suppress_the_guide(gate, tmp_path):
    # Otherwise anyone who can comment could silence the guide forever by posting an empty comment carrying the marker.
    guide = Guide(gate, tmp_path)
    gate.assert_eq(
        guide.trace_of([{"id": 9, "user": HUMAN, "body": MARKER}]),
        "list-comments:5|create:5",
        "a human's marker comment is not THE guide",
    )
    gate.log_pass("only a bot-authored comment counts as the guide")


def test_newest_bot_guide_wins_and_none_are_deleted(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    trace = guide.trace_of(
        [
            {"id": 10, "user": BOT, "body": "%s\nold one" % MARKER},
            {"id": 20, "user": BOT, "body": "%s\nnewer one" % MARKER},
        ]
    )
    gate.assert_eq(
        trace,
        "list-comments:5|update:20|info:Autopilot gu",
        "the newest duplicate is the one kept current",
    )
    gate.assert_not_contains(
        trace, "delete", "deleting a comment is not reversible; this module never does it"
    )
    gate.log_pass("a duplicate guide is resolved by updating the newest, deleting nothing")


def test_all_three_arming_paths_are_documented(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.rendered_body()
    workflow = AUTOPILOT_WF.read_text(encoding="utf-8")
    gate.assert_contains(body, "apply `autopilot`", "the label path")
    gate.assert_contains(
        body, "gh workflow run Autopilot", "the dispatch path, as a runnable command"
    )
    gate.assert_contains(
        body, "dispatch IS the arming act", "and what makes the dispatch different"
    )
    gate.assert_contains(body, "campaign in the state comment", "the campaign path")
    for name in DISPATCH_INPUTS:
        gate.assert_contains(body, name, "the dispatch input '%s' is named" % name)
        if not re.search(r"^      %s:" % re.escape(name), workflow, re.MULTILINE):
            gate.log_fail(
                "the guide names dispatch input '%s', which autopilot.yml does not declare" % name
            )
    gate.log_pass(
        "all three arming paths documented, and every dispatch input named exists in autopilot.yml"
    )


def test_every_variable_is_documented_and_real(gate, tmp_path):
    # The pinning that replaces "rendered from a source of truth". A variable renamed in autopilot.yml and not here would leave the guide instructing people to set something that does nothing.
    guide = Guide(gate, tmp_path)
    body = guide.rendered_body()
    workflow = AUTOPILOT_WF.read_text(encoding="utf-8")
    listing = harness.run(
        [
            guide.node,
            "-e",
            "for (const [n] of require(process.argv[1]).VARIABLES) console.log(n)",
            str(MODULE),
        ]
    )
    gate.assert_exit_code(0, listing.rc, "the VARIABLES roster must be readable")
    names = [line for line in listing.out.splitlines() if line.strip()]
    if len(names) < MIN_VARIABLES:
        gate.log_fail(
            "the guide documents fewer than %d variables (%d); the roster in autopilot.yml "
            "lists more" % (MIN_VARIABLES, len(names))
        )
    for name in names:
        gate.assert_contains(body, name, "the rendered table names %s" % name)
        if name not in workflow:
            gate.log_fail("the guide documents '%s', which appears nowhere in autopilot.yml" % name)
    # The two whose WRONG value is a known trap, per the roster comment.
    gate.assert_contains(
        body, "Empty allows NOBODY", "the author allowlist's fail-closed behaviour is stated"
    )
    gate.assert_contains(
        body, "never a model name", "AUTOPILOT_ALLOW_MODEL's documented trap is repeated"
    )
    gate.log_pass(
        "every documented variable exists in autopilot.yml, and both known traps are called out"
    )


def test_stop_switches_are_documented_with_their_scopes(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.rendered_body()
    gate_sh = GATE_SH.read_text(encoding="utf-8")
    labels = LABELS_FILE.read_text(encoding="utf-8")
    gate.assert_contains(
        body, "cancel the run (one round)", "the smallest scope, and that it is only one round"
    )
    gate.assert_contains(body, "autopilot-blocked", "the loop latch")
    gate.assert_contains(body, "LATCHES", "and that it needs a human to clear")
    gate.assert_contains(body, "AUTOPILOT_ENABLED", "the repo-wide switch")
    # THE PRECISE CLAIM. Removing the arming label does NOT stop a campaign: the gate's arming chain accepts an open campaign with no label present. A guide that said otherwise would send someone to remove a label and walk away.
    gate.assert_contains(body, "only the label path", "removing the label is scoped honestly")
    if 'ARMED_BY="campaign"' not in gate_sh:
        gate.log_fail(
            "the guide claims a campaign survives label removal, but the gate has no "
            "campaign arming path"
        )
    for label in STOP_LABELS:
        if not re.search(r"^- name: %s$" % re.escape(label), labels, re.MULTILINE):
            gate.log_fail(
                "the guide names the '%s' label, which .github/labels.yml does not declare" % label
            )
    gate.log_pass(
        "all three stop scopes documented, label removal scoped honestly, both labels declared"
    )


def test_the_loop_and_its_bounds_match_the_gate(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.rendered_body()
    gate_sh = GATE_SH.read_text(encoding="utf-8")
    model_args = MODEL_ARGS_SH.read_text(encoding="utf-8")
    for action in ROUND_ACTIONS:
        gate.assert_contains(body, "`%s`" % action, "the round action '%s' is named" % action)
        if '"%s"' % action not in gate_sh:
            gate.log_fail(
                "the guide names round action '%s', which autopilot-gate.sh never emits" % action
            )
    gate.assert_contains(body, "stuck-signature", "the stuck-signature bound")
    if "stuck-signature" not in gate_sh:
        gate.log_fail("autopilot-gate.sh has no stuck-signature bound")

    # The NUMBERS, each read back out of its own source. A pattern that matches nothing is a REFUSAL and not an empty comparison, which is what the twin's `[ -n "$cap" ]` guard buys.
    cap_match = CAP_RE.search(gate_sh)
    if not cap_match or not cap_match.group(1):
        gate.log_fail("could not read the default round cap out of autopilot-gate.sh")
    cap = cap_match.group(1)
    gate.assert_contains(body, "default %s" % cap, "the documented round cap matches the gate")

    other_match = TURNS_OTHER_RE.search(model_args)
    fix_match = TURNS_FIX_RE.search(model_args)
    if not other_match or not fix_match:
        gate.log_fail("could not read the --max-turns values out of resolve-model-args.sh")
    turns_other = other_match.group(1)
    turns_fix = fix_match.group(1)
    gate.assert_contains(
        body,
        "%s fixing, %s otherwise" % (turns_fix, turns_other),
        "the documented turn caps match resolve-model-args.sh",
    )
    gate.log_pass(
        "round actions, stuck-signature, round cap (%s) and turn caps (%s/%s) all match their "
        "sources" % (cap, turns_fix, turns_other)
    )


def test_the_guide_is_shorter_than_the_label_guide(gate, tmp_path):
    # An operator requirement, and a real one: this comment sits on every PR under a guide that is already long. A reference manual nobody reads is worse than the discoverability problem it was meant to fix.
    guide = Guide(gate, tmp_path)
    mine = len(guide.rendered_body().encode("utf-8"))
    theirs_run = harness.run(
        [
            guide.node,
            "-e",
            (
                "const m = require(process.argv[1]);"
                'const fs = require("node:fs");'
                "process.stdout.write(m.renderBody("
                'm.parseLabels(fs.readFileSync(process.argv[2], "utf8"), "real")));'
            ),
            str(LABEL_MODULE),
            str(LABELS_FILE),
        ]
    )
    gate.assert_exit_code(
        0, theirs_run.rc, "the label guide must render for the comparison to mean anything"
    )
    theirs = len(theirs_run.out.encode("utf-8"))
    if theirs <= 0:
        gate.log_fail(
            "the label guide rendered 0 bytes, so 'shorter than' below would be a "
            "comparison against nothing"
        )
    if mine >= theirs:
        gate.log_fail(
            "the autopilot guide is %d bytes, the label guide %d; it must be the shorter "
            "of the two" % (mine, theirs)
        )
    gate.log_pass("the autopilot guide is %d bytes against the label guide's %d" % (mine, theirs))


def test_the_trailer_is_present_and_readable(gate, tmp_path):
    # The footer is LOAD-BEARING: it is the only line telling a reader that hand-edits are overwritten and which file to change instead. Both halves are asserted, because each fails differently.
    body = Guide(gate, tmp_path).rendered_body()
    gate.assert_contains(
        body, "edits here are overwritten", "the trailer says hand-edits do not survive"
    )
    gate.assert_contains(
        body, "autopilot-guide-comment.cjs</code>", "and names the file to change instead"
    )
    gate.assert_not_contains(body, "<sub>", "it must not render as tiny subscript text")
    gate.assert_contains(body, "> Posted by", "it renders as a normal-size blockquote footer")
    gate.log_pass("the trailer exists, names its source, and renders at readable size")


def test_marker_is_the_first_bytes_and_unique(gate, tmp_path):
    guide = Guide(gate, tmp_path)
    body = guide.rendered_body()
    if not body.startswith(MARKER):
        gate.log_fail(
            "the marker must be the FIRST bytes of the body, or a prefix test cannot find it"
        )
    # LINES containing the marker, which is what `grep -c -F` counts.
    hits = len([line for line in body.splitlines() if MARKER in line])
    if hits != 1:
        gate.log_fail("the marker appears on %d lines; a quoted copy would match the finder" % hits)
    # And it must not collide with the label guide's, or the two posters would fight over one comment forever.
    collision = harness.run(
        [
            guide.node,
            "-e",
            (
                "const a = require(process.argv[1]).MARKER;"
                "const b = require(process.argv[2]).MARKER;"
                'if (a === b) { console.error("the two guides share a marker"); process.exit(1); }'
            ),
            str(MODULE),
            str(LABEL_MODULE),
        ]
    )
    if collision.rc != 0:
        gate.log_fail("the autopilot and label guides must not share a marker")
    gate.log_pass("the marker leads the body, appears once, and differs from the label guide's")


def test_ci_yml_wires_the_step_in_the_existing_grant(gate, tmp_path):
    # The module is inert unless ci.yml calls it. It rides the label-guide job deliberately: that job already holds `pull-requests: write` and the `.ci/scripts` sparse checkout.
    Guide(gate, tmp_path)
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(workflow, "autopilot-guide-comment.cjs", "ci.yml calls this module")
    job = slice_job(workflow, "label-guide")
    if not job:
        gate.log_fail(
            "the label-guide job block came out EMPTY, so every assertion below would pass "
            "or fail for the wrong reason"
        )
    gate.assert_contains(
        job, "autopilot-guide-comment.cjs", "the step is inside the job that has the grant"
    )
    gate.assert_contains(job, "pull-requests: write", "which is the write it needs")
    gate.assert_contains(job, "label-guide-comment.cjs", "and the label guide still runs beside it")
    gate.log_pass(
        "ci.yml runs the autopilot guide as a step of the label-guide job, reusing its grant"
    )
