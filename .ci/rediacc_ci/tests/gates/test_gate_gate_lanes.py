"""Port of `.ci/scripts/test/gates/test-gate-lanes.sh`.

Lane capabilities are DERIVED from `.github/workflows/ci-quality.yml`, so the
derivation is the thing to prove, and it can be wrong in two opposite ways.

TOO GENEROUS is the failure that cost CI time. `check:ci-docker-npm-pins` was
placed in `quality-static`, which checks out no submodules, so the file it exists
to scan dropped out of its enumeration and its correct exclusions were reported as
dead entries (job 100870135489). `check_syncpack_sources.py` carries the identical
scar. The twin records that its own first version committed that very bug while
being written: it matched `PyYAML` and `setup-go` ANYWHERE in a job, and
`quality-code` mentions both in comments while installing neither.

TOO MEAN is the quieter failure: the first fix required `uses: actions/setup-go`
and missed `- uses: actions/setup-go`, losing `quality-go` entirely and leaving
go-needing gates unplaceable.

HOW THE PORT DIFFERS FROM THE TWIN, and why the two agree.

The twin runs ONE `npx tsx` heredoc that both derives and judges: thirteen `ck()`
calls print `PASS<tab><label>` lines, bash re-emits them through `log_pass`, and a
`TOTAL<tab><n>` line carries the failure count. That makes TypeScript the
assertion language and bash a transcriber, and it has the property the twin's own
comment worries about: a probe that dies before printing `TOTAL` would emit no
FAIL lines at all, which is why the twin has to check for a missing TOTAL by hand.

The port splits the two halves. ONE `tsx` process still does all the DERIVING --
the same `laneCapabilities`, `placeGate` and `satisfies` from the same module, on
the same real workflow file -- and emits its results as JSON. Every JUDGEMENT then
happens in Python, one recorded control each. The claims are identical; what
changes is that a probe which produces nothing cannot be mistaken for a probe that
found nothing, because `test_the_probe_really_ran` refuses an empty payload before
any comparison is made.

NO `xdist_group`. The probe is a short-lived subprocess that reads two files and
writes nothing; nothing module-global is touched and no path in the tree is
mutated.

A MISSING `tsx` IS A LOUD FAILURE, not a skip. The gate under test is TypeScript;
a run that could not execute it has checked nothing, and unchecked folded into
fine is exactly what this directory refuses.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-gate-lanes.sh"

SUT = paths.from_root("scripts", "ci-runner", "lanes.ts")
WORKFLOW = paths.from_root(".github", "workflows", "ci-quality.yml")
TSX = paths.from_root("node_modules", ".bin", "tsx")

# THE COMMENT CASE, both directions, written out here rather than built in
# TypeScript so a reader can see exactly what separates a mention from an install.
MENTION_YAML = (
    "jobs:\n  a:\n    steps:\n      # PyYAML four times and setup-go too\n      - run: echo hi\n"
)
INSTALL_YAML = (
    'jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --user "PyYAML==0.0.0-fixture"\n'
)
DASHED_YAML = "jobs:\n  a:\n    steps:\n      - uses: actions/setup-go@abc\n"
# A LANE_ORDER entry whose job is GONE. Placement must refuse rather than quietly
# narrowing the choice to whatever survived.
GONE_YAML = "jobs:\n  quality-static:\n    runs-on: ubuntu-slim\n"

PROBE = """
import fs from 'node:fs';
import { laneCapabilities, placeGate, satisfies } from './scripts/ci-runner/lanes.js';

const capsOf = (m) => Object.fromEntries(m);
const real = laneCapabilities(fs.readFileSync('.github/workflows/ci-quality.yml', 'utf-8'));

process.stdout.write(JSON.stringify({
  real: capsOf(real),
  placeNothing: placeGate(real, []),
  placeSubmodules: placeGate(real, ['submodules']),
  placeGo: placeGate(real, ['go']),
  placeImpossible: placeGate(real, ['a-toolchain-nobody-installs']),
  mention: capsOf(laneCapabilities(%s)),
  install: capsOf(laneCapabilities(%s)),
  dashed: capsOf(laneCapabilities(%s)),
  placeGone: placeGate(laneCapabilities(%s), []),
  supersetSatisfies: satisfies(
    { job: 'x', runsOn: '', timeoutMinutes: null, submodules: ['*'], node: true, tools: ['go'] },
    ['node'],
  ),
}));
"""


# ONE derivation per process, memoised. The twin derives once and judges thirteen
# times off that single run, so memoising here matches it rather than strengthening
# it, and it keeps sixteen node startups from being charged to a gate that is
# already the slowest in the battery. The memo holds only the parsed JSON of a
# read-only probe, so nothing a case does can reach another case through it; a
# failed probe raises before the memo is written and the next case re-derives.
_PROBE_CACHE: dict = {}


def probe(gate) -> dict:
    """The derivation, once, as JSON. A LOUD refusal if it could not run."""
    if "data" in _PROBE_CACHE:
        return _PROBE_CACHE["data"]
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not TSX.is_file():
        gate.log_fail(
            "node_modules/.bin/tsx is absent, so the lane derivation could not be executed "
            "at all -- which is a FAILURE and not a pass. Fix: npm install && "
            "npm run install:natives"
        )
    source = PROBE % (
        json.dumps(MENTION_YAML),
        json.dumps(INSTALL_YAML),
        json.dumps(DASHED_YAML),
        json.dumps(GONE_YAML),
    )
    result = harness.run([str(TSX), "-"], cwd=paths.repo_root(), stdin=source)
    if result.rc != 0:
        gate.log_fail(
            "the lane derivation probe exited %d, so every case below would be judging "
            "nothing.\n--- stdout ---\n%s\n--- stderr ---\n%s" % (result.rc, result.out, result.err)
        )
    try:
        _PROBE_CACHE["data"] = json.loads(result.out)
    except json.JSONDecodeError as exc:
        gate.log_fail(
            "the probe printed something that is not JSON (%s): %r" % (exc, result.out[:400])
        )
        raise
    return _PROBE_CACHE["data"]


def test_the_probe_really_ran(gate):
    """ANTI-VACUITY, and it comes first. Every case below reads the same payload;
    an empty or lane-less one would satisfy several of them by accident."""
    gate.log_test("the derivation produced a real lane table")
    data = probe(gate)
    lanes = data["real"]
    if not lanes:
        gate.log_fail(
            "laneCapabilities read ci-quality.yml and found ZERO jobs. Every case below "
            "would then be asserting over an empty map, and an empty map passes most of "
            "them. The reader, not the workflow, is what to fix first."
        )
    gate.assertions += 1
    gate.log_pass(
        "the derivation saw %d job(s) in ci-quality.yml: %s"
        % (len(lanes), ", ".join(sorted(lanes)))
    )


def test_every_lane_in_lane_order_exists_in_the_workflow(gate):
    gate.log_test("LANE_ORDER and the workflow still name the same jobs")
    # LANE_ORDER is module-private, and placeGate refuses outright when any entry
    # is absent from the workflow (the `placeGone` case below). A lane coming back
    # is therefore the proof that the list is complete.
    result = probe(gate)["placeNothing"]
    gate.assert_not_contains(
        json.dumps(result),
        "error",
        "every lane in LANE_ORDER exists in the workflow (got %s)" % json.dumps(result),
    )
    gate.log_pass("every lane in LANE_ORDER exists in the workflow")


def test_the_slim_lanes_have_no_node(gate):
    gate.log_test("the slim lanes are slim")
    lanes = probe(gate)["real"]
    gate.assert_eq(lanes["quality-static"]["node"], False, "quality-static must not have node")
    gate.assert_eq(lanes["quality-branch"]["node"], False, "quality-branch must not have node")
    gate.log_pass("the slim lanes have no node")


def test_quality_static_takes_no_submodules(gate):
    gate.log_test("the mis-placement that cost CI (job 100870135489)")
    lanes = probe(gate)["real"]
    gate.assert_eq(
        lanes["quality-static"]["submodules"],
        [],
        "quality-static takes NO submodules -- the mis-placement that cost CI",
    )
    gate.log_pass("quality-static takes NO submodules -- the mis-placement that cost CI")


def test_quality_i18n_takes_only_private_account(gate):
    gate.log_test("a lane's submodule list is the exact set, not 'some'")
    lanes = probe(gate)["real"]
    gate.assert_eq(
        lanes["quality-i18n"]["submodules"],
        ["private/account"],
        "quality-i18n takes ONLY private/account, not all of them",
    )
    gate.log_pass("quality-i18n takes ONLY private/account, not all of them")


def test_quality_go_really_provides_go(gate):
    gate.log_test("the lane that exists for one toolchain provides it")
    lanes = probe(gate)["real"]
    gate.assert_contains(
        json.dumps(lanes["quality-go"]["tools"]),
        "go",
        "quality-go really provides go (got %s)" % lanes["quality-go"]["tools"],
    )
    gate.log_pass("quality-go really provides go")


def test_a_job_that_only_mentions_a_tool_does_not_provide_it(gate):
    gate.log_test("THE COMMENT CASE, and it is the bug this module committed while being written")
    tools = probe(gate)["mention"]["a"]["tools"]
    gate.assert_eq(
        tools, [], "a job that MENTIONS PyYAML in a comment does not provide it (got %s)" % tools
    )
    gate.log_pass("a job that MENTIONS PyYAML in a comment does not provide it")


def test_a_job_that_installs_it_does_provide_it(gate):
    gate.log_test("THE COMMENT CASE, the other direction")
    # Without this the case above is satisfied by a matcher that recognises
    # nothing at all, which is the cheapest way to pass a negative assertion.
    tools = probe(gate)["install"]["a"]["tools"]
    gate.assert_contains(
        json.dumps(tools), "python-yaml", "CONTROL: a job that INSTALLS it does (got %s)" % tools
    )
    gate.log_pass("CONTROL: a job that INSTALLS it does")


def test_a_dashed_uses_line_counts(gate):
    gate.log_test("`- uses:` is a uses line too -- the TOO MEAN direction")
    tools = probe(gate)["dashed"]["a"]["tools"]
    gate.assert_contains(
        json.dumps(tools),
        "go",
        "a `- uses:` line counts, not only a bare `uses:` (got %s)" % tools,
    )
    gate.log_pass("a `- uses:` line counts, not only a bare `uses:`")


def test_placement_prefers_the_cheapest_lane(gate):
    gate.log_test("placement: needs nothing")
    gate.assert_eq(
        probe(gate)["placeNothing"],
        {"lane": "quality-static"},
        "placement: needs nothing -> the cheapest lane",
    )
    gate.log_pass("placement: needs nothing -> the cheapest lane")


def test_placement_never_puts_a_submodule_gate_in_a_lane_without_them(gate):
    gate.log_test("placement: needs submodules")
    lane = probe(gate)["placeSubmodules"].get("lane", "")
    if lane in ("quality-static", "quality-branch"):
        gate.log_fail("placement: needs submodules -> never a lane without them (got %r)" % lane)
    gate.assertions += 1
    gate.log_pass("placement: needs submodules -> never a lane without them")


def test_placement_sends_a_go_gate_to_quality_go(gate):
    gate.log_test("placement: needs go")
    gate.assert_eq(probe(gate)["placeGo"], {"lane": "quality-go"}, "placement: needs go")
    gate.log_pass("placement: needs go -> quality-go")


def test_an_unprovidable_need_is_an_error_not_a_silent_lane(gate):
    gate.log_test("placement: a need nobody installs")
    result = probe(gate)["placeImpossible"]
    gate.assert_contains(
        json.dumps(result),
        "error",
        "placement: an unprovidable need is an ERROR, not a silent lane (got %s)"
        % json.dumps(result),
    )
    gate.log_pass("placement: an unprovidable need is an ERROR, not a silent lane")


def test_a_lane_whose_job_is_gone_refuses_placement(gate):
    gate.log_test("a LANE_ORDER entry missing from the workflow")
    # Never narrow the choice quietly: a job that vanished must red rather than
    # silently redirect every gate that wanted it.
    result = probe(gate)["placeGone"]
    gate.assert_contains(
        json.dumps(result),
        "error",
        "a LANE_ORDER entry missing from the workflow refuses placement (got %s)"
        % json.dumps(result),
    )
    gate.log_pass("a LANE_ORDER entry missing from the workflow refuses placement")


def test_satisfies_is_a_superset_test(gate):
    gate.log_test("satisfies() is a superset test, not equality")
    gate.assert_eq(
        probe(gate)["supersetSatisfies"],
        True,
        "a lane providing MORE than asked must still satisfy the ask",
    )
    gate.log_pass("satisfies() is a superset test, not equality")


def test_the_workflow_the_derivation_reads_is_the_one_ci_runs(gate):
    """PORT-ONLY. Everything above derives from one path. If that file were gone,
    `laneCapabilities` would be handed an empty string and the anti-vacuity case
    would be the only thing standing between this module and a table of nothing."""
    gate.log_test("the derivation's input file exists where the derivation looks")
    if not WORKFLOW.is_file():
        gate.log_fail(
            "%s is missing, so the lane table is derived from nothing"
            % paths.relative_to_root(WORKFLOW)
        )
    gate.assertions += 1
    gate.log_pass("%s is present and is what was read" % paths.relative_to_root(WORKFLOW))
