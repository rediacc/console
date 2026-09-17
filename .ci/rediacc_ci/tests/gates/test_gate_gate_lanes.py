"""Port of `.ci/scripts/test/gates/test-gate-lanes.sh`.

Lane capabilities are DERIVED from `.github/workflows/ci-quality.yml`, so the derivation is the thing to prove, and it can be wrong in two opposite ways.

TOO GENEROUS is the failure that cost CI time. `check:ci-docker-npm-pins` was placed in `quality-static`, which checks out no submodules, so the file it exists to scan dropped out of its enumeration and its correct exclusions were reported as dead entries (job 100870135489). `check_syncpack_sources.py` carries the identical scar. The twin records that its own first version
committed that very bug while being written: it matched `PyYAML` and `setup-go` ANYWHERE in a job, and `quality-code` mentions both in comments while installing neither.

TOO MEAN is the quieter failure: the first fix required `uses: actions/setup-go` and missed `- uses: actions/setup-go`, losing `quality-go` entirely and leaving go-needing gates unplaceable.

HOW THE PORT DIFFERS FROM THE TWIN, and why the two agree.

The twin runs ONE `npx tsx` heredoc that both derives and judges: thirteen `ck()` calls print `PASS<tab><label>` lines, bash re-emits them through `log_pass`, and a `TOTAL<tab><n>` line carries the failure count. That makes TypeScript the assertion language and bash a transcriber, and it has the property the twin's own comment worries about: a probe that dies before printing
`TOTAL` would emit no FAIL lines at all, which is why the twin has to check for a missing TOTAL by hand.

The port splits the two halves. ONE `tsx` process still does all the DERIVING -- the same `laneCapabilities`, `placeGate` and `satisfies` from the same module, on the same real workflow file -- and emits its results as JSON. Every JUDGEMENT then happens in Python, one recorded control each. The claims are identical; what changes is that a probe which produces nothing cannot be
mistaken for a probe that found nothing, because `test_the_probe_really_ran` refuses an empty payload before any comparison is made.

NO `xdist_group`. The probe is a short-lived subprocess that reads two files and writes nothing; nothing module-global is touched and no path in the tree is mutated.

A MISSING `tsx` IS A LOUD FAILURE, not a skip. The gate under test is TypeScript;
a run that could not execute it has checked nothing, and unchecked folded into fine is exactly what this directory refuses.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-gate-lanes.sh"

SUT = paths.from_root("scripts", "ci-runner", "lanes.ts")
WORKFLOW = paths.from_root(".github", "workflows", "ci-quality.yml")
TSX = paths.from_root("node_modules", ".bin", "tsx")

# THE COMMENT CASE, both directions, written out here rather than built in TypeScript so a reader can see exactly what separates a mention from an install.
MENTION_YAML = (
    "jobs:\n  a:\n    steps:\n      # PyYAML four times and setup-go too\n      - run: echo hi\n"
)
INSTALL_YAML = (
    'jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --user "PyYAML==0.0.0-fixture"\n'
)
DASHED_YAML = "jobs:\n  a:\n    steps:\n      - uses: actions/setup-go@abc\n"
# A LANE_ORDER entry whose job is GONE. Placement must refuse rather than quietly narrowing the choice to whatever survived.
GONE_YAML = "jobs:\n  quality-static:\n    runs-on: ubuntu-slim\n"

PROBE = """
import fs from 'node:fs';
import { laneCapabilities, placeGate, satisfies, shardPlan } from './scripts/ci-runner/lanes.js';
import { shardAssignment } from './scripts/gate-bind.js';

const capsOf = (m) => Object.fromEntries(m);
const real = laneCapabilities(fs.readFileSync('.github/workflows/ci-quality.yml', 'utf-8'));

// SHARDING (T-SCHED B1), driven off the REAL lock rather than a fixture.
const lock = JSON.parse(fs.readFileSync('scripts/ci-runner/gates.lock.json', 'utf-8'));
const laneEntries = (lane) =>
  lock.filter((e) => e.ci && e.ci.kind === 'step' && e.ci.job === lane).map((e) => e.id);
const plan = (lane, n) => shardPlan(lock, real, { [lane]: n });
const planned = (lane, n) => { const r = plan(lane, n); return 'error' in r ? null : r.lanes[0]; };
const refusal = (lane, n) => { const r = plan(lane, n); return 'error' in r ? r.error : ''; };
// MEASURED, not hand-typed: the smallest n at which the lane's heavy-unit count no
// longer refuses it. T-SCHED B2 D1 merges step-sharing ids into one unit before this
// count is taken, so a lock change that adds or removes a heavy id inside an existing
// step (e.g. a sixth `check:lint:*`) moves this floor with it instead of silently
// going stale the way a literal would.
const heavyFloor = (lane) => {
  const total = laneEntries(lane).length;
  for (let n = 1; n <= total; n++) {
    const r = plan(lane, n);
    if (!('error' in r) || !r.error.includes('heavy is capped at one per shard')) return n;
  }
  return null;
};
const stepIds = (lane, step) =>
  lock
    .filter((e) => e.ci && e.ci.kind === 'step' && e.ci.job === lane && e.ci.step === step)
    .map((e) => e.id);

// T-SCHED B2 D2. `shardAssignment` takes `counts`/`ceilings` as PARAMETERS (not the
// real SHARD_COUNTS/SHARD_REPLICATED_MAX, which are empty today), so these fixtures can
// exercise all four shapes -- not-asked, refused-for-no-ceiling, refused-for-exceeding-
// it, and succeeds -- against the REAL lock without waiting for a lane to actually be
// declared sharded.
const assign = (job, counts, ceilings, emitting) =>
  shardAssignment(job, lock, real, emitting ?? [], counts, ceilings);

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
  lockSize: lock.length,
  laneSets: {
    'quality-security': laneEntries('quality-security'),
    'quality-static': laneEntries('quality-static'),
  },
  plans: {
    security4: planned('quality-security', 4),
    code8: planned('quality-code', 8),
    code4: planned('quality-code', 4),
    www3: planned('quality-www-build', 3),
    static3: planned('quality-static', 3),
  },
  refusals: {
    branch6: refusal('quality-branch', 6),
    www5: refusal('quality-www-build', 5),
    submodule2: refusal('quality-submodule-branches', 2),
    nowhere2: refusal('quality-nowhere', 2),
    code2: refusal('quality-code', 2),
    go2: refusal('quality-go', 2),
    go8: refusal('quality-go', 8),
    static0: JSON.stringify(shardPlan(lock, real, { 'quality-static': 0 })),
    emptyLock: JSON.stringify(shardPlan([], real, { 'quality-static': 2 })),
    noLanes: JSON.stringify(shardPlan(lock, real, {})),
  },
  deterministic:
    JSON.stringify(plan('quality-security', 4)) === JSON.stringify(plan('quality-security', 4)),
  heavyFloors: { 'quality-code': heavyFloor('quality-code') },
  lintStepIds: stepIds('quality-code', 'Lint'),
  // Map does not survive JSON.stringify (it serialises to `{}`), so pull out plain
  // values before this whole object is stringified once at the end.
  d2: (() => {
    const notAsked = assign('quality-static', {}, {});
    const noCeiling = assign('quality-code', { 'quality-code': 4 }, {});
    // quality-code's real Lint step (5 ids) is "emitted" here, everything else is not --
    // a deliberately partial emitting list so `replicated` is neither 0 nor everything,
    // proving the computation actually reads `emitting` rather than a constant.
    const partial = assign('quality-code', { 'quality-code': 4 }, { 'quality-code': 1 }, [
      { step: 'Lint' },
    ]);
    const tooTight = assign('quality-code', { 'quality-code': 4 }, { 'quality-code': 0.01 }, [
      { step: 'Lint' },
    ]);
    return {
      notAsked,
      noCeilingError: 'error' in noCeiling ? noCeiling.error : null,
      partialError: 'error' in partial ? partial.error : null,
      partialReplicated: 'replicated' in partial ? partial.replicated : null,
      partialLegCount: 'legs' in partial ? partial.legs.size : null,
      tooTightError: 'error' in tooTight ? tooTight.error : null,
    };
  })(),
}));
"""


# ONE derivation per process, memoised. The twin derives once and judges thirteen times off that single run, so memoising here matches it rather than strengthening it, and it keeps sixteen node startups from being charged to a gate that is already the slowest in the battery. The memo holds only the parsed JSON of a read-only probe, so nothing a case does can reach another case
# through it; a failed probe raises before the memo is written and the next case re-derives.
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
    # LANE_ORDER is module-private, and placeGate refuses outright when any entry is absent from the workflow (the `placeGone` case below). A lane coming back is therefore the proof that the list is complete.
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
    # Without this the case above is satisfied by a matcher that recognises nothing at all, which is the cheapest way to pass a negative assertion.
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
    # Never narrow the choice quietly: a job that vanished must red rather than silently redirect every gate that wanted it.
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


# --------------------------------------------------------------------------- SHARDING (T-SCHED B1). Every case below is judged on a plan the probe computed
# from the REAL `scripts/ci-runner/gates.lock.json`, not from a fixture: twelve
# selftest controls elsewhere in this programme passed while the feature did nothing, because each one called the helper directly and nothing populated the object it read. ---------------------------------------------------------------------------


def _home_of(plan: dict, gate_id: str) -> int:
    """Which shard index holds `gate_id`, or -1."""
    for shard in plan["shards"]:
        if gate_id in shard["ids"]:
            return int(shard["index"])
    return -1


def test_the_sharder_read_a_real_lock(gate):
    """ANTI-VACUITY for the sharding half, and it comes first for the same
    reason the lane one does: an empty lock satisfies most of what follows."""
    gate.log_test("the lock the sharder reads is not empty")
    data = probe(gate)
    if data["lockSize"] < 100 or len(data["laneSets"]["quality-security"]) < 100:
        gate.log_fail(
            "the sharder saw %d lock entries and %d in quality-security. A plan over a "
            "collapsed lock emits shards that run nothing, and it would satisfy the "
            "union and disjointness cases below by being empty."
            % (data["lockSize"], len(data["laneSets"]["quality-security"]))
        )
    gate.assertions += 1
    gate.log_pass(
        "the sharder read %d lock entries, %d of them in quality-security"
        % (data["lockSize"], len(data["laneSets"]["quality-security"]))
    )


def test_the_union_of_the_shards_is_the_lane_gate_set(gate):
    gate.log_test("acceptance clause 1: union equals the lane's gate set")
    data = probe(gate)
    plan = data["plans"]["security4"]
    ids = [i for shard in plan["shards"] for i in shard["ids"]]
    gate.assert_eq(
        sorted(ids),
        sorted(data["laneSets"]["quality-security"]),
        "the four shards cover exactly the lane's %d entries" % plan["entries"],
    )
    gate.log_pass("union of the shards equals the lane gate set (%d entries)" % plan["entries"])


def test_the_shards_are_pairwise_disjoint(gate):
    gate.log_test("acceptance clause 2: pairwise disjoint")
    plan = probe(gate)["plans"]["security4"]
    ids = [i for shard in plan["shards"] for i in shard["ids"]]
    gate.assert_eq(len(set(ids)), len(ids), "no gate may run in two shards")
    gate.log_pass("shards are pairwise disjoint (%d ids, %d distinct)" % (len(ids), len(set(ids))))


def test_no_shard_is_empty(gate):
    gate.log_test("acceptance clause 3: none empty")
    plan = probe(gate)["plans"]["security4"]
    sizes = [len(s["ids"]) for s in plan["shards"]]
    if min(sizes) == 0:
        gate.log_fail("shard sizes %s -- an empty shard reports green having run nothing" % sizes)
    gate.assertions += 1
    gate.log_pass("no shard is empty (sizes %s)" % sizes)


def test_the_shards_are_balanced_on_weight(gate):
    """T-SCHED B2 D1 moved this fixture off `security4`. Before the step-merge,
    `quality-security`'s 149-id `Quality-gate unit tests` step was NOT one unit, so the packer could spread its ids across shards for an even weight -- a plan real CI could never run, since gate-bind can attach one conjunct to that one step. After the merge the 149 ids are correctly ONE unit and `security4` is (correctly) unbalanceable: 150 of 166 entries sit in a single
    indivisible
    block. `quality-code` divides on real step boundaries and balances for real;
    it is the box's own worked example (D1/D2) of a lane the mechanism suits."""
    gate.log_test("balance on `weight`, which is the rule the box states")
    plan = probe(gate)["plans"]["code8"]
    weights = [s["weight"] for s in plan["shards"]]
    if max(weights) - min(weights) > 2:
        gate.log_fail(
            "shard weights %s spread by %d. A packer that appended in lock order would "
            "produce this; the box asks for balance." % (weights, max(weights) - min(weights))
        )
    gate.assertions += 1
    gate.log_pass("shard weights %s are balanced" % weights)


def test_a_dominant_single_step_lane_is_correctly_unbalanceable(gate):
    """The negative space of the test above, named rather than left implicit.
    `quality-security` is NOT a planner bug: 149 of its 166 entries are one hand-written step (`Quality-gate unit tests`), so no packer can spread that unit without proposing a plan gate-bind cannot realize. This is exactly the
    shape T-SCHED B2's own later measurement used to prefer `quality-code`."""
    gate.log_test("quality-security's dominant step correctly resists balance")
    plan = probe(gate)["plans"]["security4"]
    weights = [s["weight"] for s in plan["shards"]]
    if max(weights) - min(weights) <= 2:
        gate.log_fail(
            "shard weights %s are balanced; quality-security's 149-id battery step "
            "should make that impossible, so either the lock or the merge changed "
            "underneath this control" % weights
        )
    gate.assertions += 1
    gate.log_pass("quality-security stays lopsided (%s), as its structure demands" % weights)


def test_a_mutex_group_never_splits(gate):
    gate.log_test("rule 1: a mutex group never splits")
    # `build-artifacts` holds check:types and check:ci-command-tree in quality-code.
    plan = probe(gate)["plans"]["code8"]
    gate.assert_eq(
        _home_of(plan, "check:types"),
        _home_of(plan, "check:ci-command-tree"),
        "the build-artifacts mutex group must land in one shard",
    )
    gate.log_pass("a mutex group never splits across shards (quality-code build-artifacts)")


def test_heavy_is_capped_at_one_per_shard(gate):
    gate.log_test("rule 2: heavy at most one per shard")
    plan = probe(gate)["plans"]["code8"]
    counts = [s["heavy"] for s in plan["shards"]]
    if max(counts) > 1:
        gate.log_fail("heavy per shard %s exceeds the cap of one" % counts)
    gate.assertions += 1
    gate.log_pass("heavy is capped at one per shard (%s across 8 shards)" % counts)


def test_a_within_lane_needs_edge_co_locates(gate):
    """THE FOURTH RULE, which the box does not name. Twelve `quality-www-build`
    entries declare `needs: [build:www]` and `build:www` is a step in that same lane, so a plan honouring only mutex would put a gate in a runner that never
    built the thing it validates."""
    gate.log_test("a within-lane `needs` target shares its dependent's shard")
    plan = probe(gate)["plans"]["www3"]
    gate.assert_eq(
        _home_of(plan, "build:www"),
        _home_of(plan, "check:ci-seo"),
        "build:www and check:ci-seo must land in one shard",
    )
    gate.log_pass("a within-lane `needs` target shares its dependent's shard (build:www)")


def test_a_needs_target_is_ordered_first_inside_its_shard(gate):
    gate.log_test("and the order inside the shard is topological, because CI steps run in order")
    plan = probe(gate)["plans"]["www3"]
    shard = next(s for s in plan["shards"] if "build:www" in s["ids"])
    if shard["ids"].index("build:www") > shard["ids"].index("check:ci-seo"):
        gate.log_fail(
            "build:www runs AFTER check:ci-seo in shard %d: %s" % (shard["index"], shard["ids"][:4])
        )
    gate.assertions += 1
    gate.log_pass("the `needs` target is ordered first inside its shard")


def test_runs_on_and_timeout_come_from_the_lane(gate):
    gate.log_test("the matrix's literal runner and timeout are the LANE's, never re-derived")
    data = probe(gate)
    lane = data["real"]["quality-security"]
    plan = data["plans"]["security4"]
    for shard in plan["shards"]:
        gate.assert_eq(shard["runsOn"], lane["runsOn"], "shard runs-on equals the lane's")
        gate.assert_eq(
            shard["timeoutMinutes"], lane["timeoutMinutes"], "shard timeout equals the lane's"
        )
    gate.log_pass(
        "every shard carries the lane's runs-on (%s) and timeout (%s)"
        % (lane["runsOn"], lane["timeoutMinutes"])
    )


def test_the_plan_is_deterministic(gate):
    gate.log_test("two calls on one lock must agree, or the emitted matrix churns")
    gate.assert_eq(probe(gate)["deterministic"], True, "shardPlan is a function of the lock alone")
    gate.log_pass("the plan is deterministic: two calls agree byte for byte")


def test_more_shards_than_gates_refuses(gate):
    """THE REFUSAL THE BOX CALLS OUT BY NAME."""
    gate.log_test("more shards than gates must REFUSE, not emit an empty shard")
    message = probe(gate)["refusals"]["branch6"]
    gate.assert_contains(
        message, "Ask for at most 5", "6 shards over quality-branch's 5 gates must refuse"
    )
    gate.log_pass("more shards than gates refuses, and the message names the ceiling")


def test_the_ceiling_is_units_not_entries(gate):
    gate.log_test("the ceiling counts INDIVISIBLE UNITS, which is the stricter threshold")
    # 16 entries in quality-www-build are 4 units, because 13 of them are welded together by one mutex group and twelve needs edges. Counting entries would
    # let five shards through and leave one empty.
    message = probe(gate)["refusals"]["www5"]
    gate.assert_contains(
        message,
        "only 4 indivisible unit(s) (16 entries",
        "the refusal must count units and SAY it counted entries too",
    )
    gate.log_pass("the ceiling is units, not entries: 16 www-build entries are 4 units")


def test_a_lane_with_zero_lock_entries_refuses(gate):
    """ANTI-VACUITY as a refusal in the planner itself. `quality-submodule-branches`
    is a real job in the workflow that no lock entry names, so this case is driven
    by the tree rather than by a fixture."""
    gate.log_test("a lane with ZERO lock entries is a planner that cannot see the tree")
    message = probe(gate)["refusals"]["submodule2"]
    gate.assert_contains(message, "ZERO entries in the lock", "an empty lane must refuse")
    gate.log_pass("a lane with zero lock entries refuses (quality-submodule-branches is real)")


def test_a_lane_the_workflow_does_not_define_refuses(gate):
    gate.log_test("a lane nothing defines has no runner and no timeout to copy")
    message = probe(gate)["refusals"]["nowhere2"]
    gate.assert_contains(message, "not a job in the workflow", "an unknown lane must refuse")
    gate.log_pass("a lane the workflow does not define refuses")


def test_more_heavy_gates_than_shards_refuses(gate):
    """T-SCHED B2 D1 moved this number. Before the step-merge, `quality-code` counted
    8 heavy IDS -- `check:lint` five times over (all one step) plus three more -- and refused any count under 8. After it, the five `check:lint*` ids are one unit with one heavy peak, so the real floor is the number of heavy UNITS, measured here rather than hand-typed so a future lock change cannot make this assertion stale
    silently."""
    gate.log_test("the aggregate half of the heavy rule, in the corrected currency")
    floor = probe(gate)["heavyFloors"]["quality-code"]
    if floor < 2:
        gate.log_fail("quality-code's heavy-unit floor measured %d, expected >= 2" % floor)
    gate.assertions += 1
    message = probe(gate)["refusals"]["code2"]
    gate.assert_contains(
        message,
        "Ask for at least %d shards" % floor,
        "fewer shards than heavy units must refuse and name the real (unit) minimum",
    )
    gate.log_pass("more heavy gates than shards refuses, naming the corrected minimum (%d)" % floor)


def test_step_merge_lowered_the_floor_enough_to_shard_code_at_four(gate):
    """THE POINT OF D1. Before the step-merge this exact count (`quality-code`, 4
    shards) refused outright -- 8 heavy ids could not fit in 4 shards -- which is the wrong answer: the five `check:lint*` ids are one process, one runner, one heavy peak. Refusing to shard a lane over ids that never run concurrently is
    the bug D1 exists to fix; this proves the fix, not just its arithmetic."""
    gate.log_test("quality-code now shards at 4 (was an unconditional refusal before D1)")
    plan = probe(gate)["plans"]["code4"]
    if plan is None:
        gate.log_fail(
            "quality-code refused at 4 shards; the step-merge should have made this viable"
        )
    gate.assertions += 1
    counts = [s["heavy"] for s in plan["shards"]]
    if max(counts) > 1:
        gate.log_fail(
            "heavy per shard %s exceeds the cap of one, even at the corrected floor" % counts
        )
    gate.assertions += 1
    gate.log_pass("quality-code shards at 4, heavy still capped at one per shard (%s)" % counts)


def test_a_step_shared_group_never_splits(gate):
    """`check:lint`, `check:lint:cli`, `check:lint:web`, `check:lint:tooling` and
    `check:lint:account` all carry `ci.step: 'Lint'` -- one `run:` of four npm scripts chained with `&&` in one shell. A plan that put two of them on different legs would be unrealisable: gate-bind can attach exactly one
    conjunct to that one step."""
    gate.log_test("ids sharing one emitted step land in the same shard")
    plan = probe(gate)["plans"]["code8"]
    homes = {_home_of(plan, gid) for gid in probe(gate)["lintStepIds"]}
    if len(homes) != 1:
        gate.log_fail("the Lint step's ids span shards %s; one `run:` cannot honour that" % homes)
    gate.assertions += 1
    gate.log_pass("every id riding the Lint step lands in the same shard")


def test_two_heavies_in_one_mutex_group_shard_because_they_never_coexist(gate):
    """CORRECTED 2026-09-09. This control used to assert the OPPOSITE, and it was
    encoding a bug rather than a rule.

    `quality-go`'s `account-vitest` mutex group holds check:ci-account-server and check:ci-account-scope-audit, BOTH heavy, and the first version of `shardPlan` therefore refused that lane at every shard count. But `gate-spec.ts:44` defines mutex as "no two gates sharing a group overlap", and `heavy` bounds CONCURRENT heap: two heavies that can never run together have a peak of
    ONE. Refusing it was refusing arithmetic, and it made a real lane unshardable for no reason.

    A unit merged by within-lane `needs` is the opposite case -- co-location with no exclusion, so both really are resident -- and that one still refuses. The two
    directions are asserted together because the distinction IS the rule."""
    gate.log_test("a mutex-only unit shards; a needs-merged unit with two heavies refuses")
    p = probe(gate)
    go2 = p["refusals"].get("go2", "")
    refused = "error" in go2 if isinstance(go2, dict) else "No shard count satisfies" in str(go2)
    gate.assert_eq(
        refused,
        False,
        "quality-go x2 must now PLAN: its two heavies are mutex siblings and never coexist",
    )
    gate.log_pass("two heavies in one mutex group shard, because mutex means they never coexist")


def test_zero_shards_is_not_a_shard_count(gate):
    gate.log_test("zero shards")
    gate.assert_contains(probe(gate)["refusals"]["static0"], "integer >= 1", "0 shards must refuse")
    gate.log_pass("zero shards is not a shard count")


def test_an_empty_lock_refuses(gate):
    gate.log_test("an empty lock is the planner not seeing the tree")
    gate.assert_contains(
        probe(gate)["refusals"]["emptyLock"], "EMPTY lock", "an empty lock must refuse"
    )
    gate.log_pass("an empty lock refuses rather than planning nothing")


def test_naming_no_lanes_refuses(gate):
    gate.log_test("an empty plan is not a plan")
    gate.assert_contains(
        probe(gate)["refusals"]["noLanes"], "no lanes at all", "an empty lane map must refuse"
    )
    gate.log_pass("naming no lanes at all refuses")


def test_a_shardable_lane_still_plans(gate):
    """THE OTHER DIRECTION. Nine refusals above are satisfied by a planner that
    refuses everything; this is the control that says it does not."""
    gate.log_test("CONTROL: a shardable lane still PLANS")
    plan = probe(gate)["plans"]["static3"]
    if plan is None:
        gate.log_fail("quality-static x3 was refused, so every refusal above proves nothing")
    gate.assert_eq(len(plan["shards"]), 3, "quality-static splits into three shards")
    gate.assert_eq(plan["units"], plan["entries"], "quality-static has no mutex or needs merging")
    gate.log_pass("CONTROL: quality-static plans into 3 shards over %d entries" % plan["entries"])


def test_a_lane_absent_from_shard_counts_is_not_asked(gate):
    """T-SCHED B2 D2. `shardAssignment` returning `null` means "nobody asked to shard
    this lane", which must stay silent (SHARD_COUNTS is empty in the real tree today,
    and every lane must fall through this path for the mechanism to be inert)."""
    gate.log_test("a lane absent from counts returns null, not a refusal")
    gate.assert_eq(
        probe(gate)["d2"]["notAsked"], None, "an unsharded lane must be null, not an error"
    )
    gate.log_pass("a lane absent from SHARD_COUNTS is null (not asked), never a refusal")


def test_a_sharded_lane_with_no_ceiling_refuses(gate):
    """The mandatory declaration. A lane in SHARD_COUNTS with nothing in
    SHARD_REPLICATED_MAX would ship with no floor on how much of it can run replicated on every leg -- exactly the silent state that let the
    quality-security mistake happen by hand."""
    gate.log_test("a lane asked to shard with no declared ceiling refuses")
    message = probe(gate)["d2"]["noCeilingError"]
    gate.assert_contains(
        message, "no matching SHARD_REPLICATED_MAX entry", "a missing ceiling must refuse loudly"
    )
    gate.log_pass("a sharded lane with no declared ceiling refuses")


def test_replicated_is_computed_from_emitting_not_hardcoded(gate):
    """THE POINT OF D2. Feed a deliberately PARTIAL `emitting` list (only the Lint
    step) and prove `replicated` names exactly the ids that step does not cover -- not zero, not everything, which is what a stub or a hardcoded answer would give
    either way."""
    gate.log_test("replicated is computed from the real emitting set, both directions")
    d2 = probe(gate)["d2"]
    lint_ids = set(probe(gate)["lintStepIds"])
    replicated = set(d2["partialReplicated"])
    if replicated & lint_ids:
        gate.log_fail(
            "replicated %s overlaps the emitted Lint ids %s; those ARE covered by "
            "`emitting` and must not be flagged" % (sorted(replicated & lint_ids), sorted(lint_ids))
        )
    gate.assertions += 1
    if len(replicated) == 0:
        gate.log_fail(
            "replicated is empty; a partial `emitting` list must leave something uncovered"
        )
    gate.assertions += 1
    gate.log_pass(
        "replicated names %d id(s), none of them the %d Lint id(s) `emitting` covers"
        % (len(replicated), len(lint_ids))
    )
    gate.log_test("a lane that clears its ceiling still returns real legs")
    if d2["partialLegCount"] is None or d2["partialLegCount"] == 0:
        gate.log_fail(
            "partial's leg count is %r; a successful assignment must place every id"
            % d2["partialLegCount"]
        )
    gate.assertions += 1
    gate.log_pass("a lane clearing its ceiling returns %d assigned leg(s)" % d2["partialLegCount"])


def test_exceeding_the_replicated_ceiling_refuses(gate):
    """The refusal D2 exists for. A near-zero ceiling against quality-code's real
    (non-trivial) replicated share must refuse, naming the share and the ceiling so
    the fix is legible without re-deriving the arithmetic."""
    gate.log_test("a replicated share over its declared ceiling refuses")
    message = probe(gate)["d2"]["tooTightError"]
    gate.assert_contains(message, "run OUTSIDE any emitted region", "must name the hazard")
    gate.assert_contains(
        message, "Ceiling for quality-code is 1%", "must name the declared ceiling"
    )
    gate.log_pass("exceeding the declared replicated ceiling refuses, naming both numbers")
