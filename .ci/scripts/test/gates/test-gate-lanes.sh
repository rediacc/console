#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: node
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# Lane capabilities are DERIVED from ci-quality.yml, so the derivation is the thing to
# prove -- twice over, because it can be wrong in two opposite ways.
#
# TOO GENEROUS is the failure that cost CI time. check:ci-docker-npm-pins was placed in
# quality-static, which checks out no submodules, so the file it exists to scan dropped
# out of its enumeration and its correct exclusions were reported as dead entries (job
# 100870135489). check_syncpack_sources.py carries the identical scar.
#
# AND THIS MODULE COMMITTED THAT VERY BUG WHILE BEING WRITTEN. Its first version matched
# `PyYAML` and `setup-go` anywhere in a job, and quality-code MENTIONS both in comments
# while installing neither -- so it would have placed a yaml-needing gate in a job with
# no PyYAML. Caught by checking the derived table against the file rather than trusting
# it, which is why the comment case is pinned below.
#
# TOO MEAN is the quieter failure: the first fix required `uses: actions/setup-go` and
# missed `- uses: actions/setup-go`, losing quality-go entirely and leaving go-needing
# gates unplaceable.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

OUT="$(
    cd "$REPO_ROOT" && npx tsx - <<'TS' 2>&1
import fs from 'node:fs';
import { laneCapabilities, placeGate, satisfies, shardPlan } from './scripts/ci-runner/lanes.js';
import { shardAssignment } from './scripts/gate-bind.js';

let bad = 0;
const ck = (label: string, ok: boolean, detail?: unknown): void => {
  console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
  if (!ok) {
    bad += 1;
    console.log(`\t\t${JSON.stringify(detail)}`);
  }
};

const caps = laneCapabilities(fs.readFileSync('.github/workflows/ci-quality.yml', 'utf-8'));

// LANE_ORDER is module-private; placeGate refuses outright when any entry is absent from
// the workflow (the `gone` case below), so a lane coming back is the proof it is complete.
ck('every lane in LANE_ORDER exists in the workflow', !('error' in placeGate(caps, [])),
   placeGate(caps, []));
ck('the slim lanes have no node', !caps.get('quality-static')?.node && !caps.get('quality-branch')?.node);
ck('quality-static takes NO submodules -- the mis-placement that cost CI',
   caps.get('quality-static')?.submodules.length === 0);
ck('quality-i18n takes ONLY private/account, not all of them',
   JSON.stringify(caps.get('quality-i18n')?.submodules) === '["private/account"]',
   caps.get('quality-i18n')?.submodules);
ck('quality-go really provides go', caps.get('quality-go')?.tools.includes('go'));

// THE COMMENT CASE, both directions.
const mention = 'jobs:\n  a:\n    steps:\n      # PyYAML four times and setup-go too\n      - run: echo hi\n';
ck('a job that MENTIONS PyYAML in a comment does not provide it',
   (laneCapabilities(mention).get('a')?.tools ?? []).length === 0,
   laneCapabilities(mention).get('a')?.tools);
const install = 'jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --user "PyYAML==0.0.0-fixture"\n';
ck('CONTROL: a job that INSTALLS it does',
   laneCapabilities(install).get('a')?.tools.includes('python-yaml'),
   laneCapabilities(install).get('a')?.tools);
const dashed = 'jobs:\n  a:\n    steps:\n      - uses: actions/setup-go@abc\n';
ck('a `- uses:` line counts, not only a bare `uses:`',
   laneCapabilities(dashed).get('a')?.tools.includes('go'));

ck('placement: needs nothing -> the cheapest lane', JSON.stringify(placeGate(caps, [])) === '{"lane":"quality-static"}',
   placeGate(caps, []));
ck('placement: needs submodules -> never a lane without them',
   !['quality-static', 'quality-branch'].includes((placeGate(caps, ['submodules']) as { lane?: string }).lane ?? ''),
   placeGate(caps, ['submodules']));
ck('placement: needs go -> quality-go', JSON.stringify(placeGate(caps, ['go'])) === '{"lane":"quality-go"}',
   placeGate(caps, ['go']));
ck('placement: an unprovidable need is an ERROR, not a silent lane',
   'error' in placeGate(caps, ['a-toolchain-nobody-installs']));

// A LANE ROW WHOSE JOB IS GONE must refuse, never narrow the choice quietly.
const gone = laneCapabilities('jobs:\n  quality-static:\n    runs-on: ubuntu-slim\n');
ck('a LANE_ORDER entry missing from the workflow refuses placement',
   'error' in placeGate(gone, []), placeGate(gone, []));

ck('satisfies() is a superset test, not equality',
   satisfies({ job: 'x', runsOn: '', timeoutMinutes: null, submodules: ['*'], node: true, tools: ['go'] }, ['node']));

// -------------------------------------------------------------------------
// SHARDING (T-SCHED B1). Driven off the REAL lock, not fixtures: twelve
// selftest controls passed elsewhere in this programme while the feature did
// nothing, because every control called the helper directly and nothing
// populated the object it read.
// -------------------------------------------------------------------------
const lock = JSON.parse(fs.readFileSync('scripts/ci-runner/gates.lock.json', 'utf-8'));
const laneEntries = (lane: string): string[] =>
  lock.filter((e: any) => e.ci?.kind === 'step' && e.ci.job === lane).map((e: any) => e.id);
const stepIds = (lane: string, step: string): string[] =>
  lock
    .filter((e: any) => e.ci?.kind === 'step' && e.ci.job === lane && e.ci.step === step)
    .map((e: any) => e.id);
const planned = (lane: string, n: number) => {
  const r = shardPlan(lock, caps, { [lane]: n });
  return 'error' in r ? null : r.lanes[0];
};
const refusal = (lane: string, n: number): string => {
  const r = shardPlan(lock, caps, { [lane]: n });
  return 'error' in r ? r.error : '';
};

ck('the lock the sharder reads is not empty (anti-vacuity, and it comes first)',
   lock.length > 100 && laneEntries('quality-security').length > 100,
   { lock: lock.length, security: laneEntries('quality-security').length });

const sec = planned('quality-security', 4);
const secIds = sec ? sec.shards.flatMap((s: { ids: string[] }) => s.ids) : [];
ck('union of the shards equals the lane gate set, on the REAL lock',
   JSON.stringify([...secIds].sort()) === JSON.stringify([...laneEntries('quality-security')].sort()),
   { shards: secIds.length, lane: laneEntries('quality-security').length });
ck('shards are pairwise disjoint', new Set(secIds).size === secIds.length,
   { ids: secIds.length, distinct: new Set(secIds).size });
ck('no shard is empty', sec !== null && sec.shards.every((s: { ids: string[] }) => s.ids.length > 0),
   sec?.shards.map((s: { ids: string[] }) => s.ids.length));

// T-SCHED B2 D1 MOVED THIS EXAMPLE OFF quality-security. Before the step-merge,
// quality-security's 149-id `Quality-gate unit tests` step was NOT one unit, so the
// packer could spread its ids across shards for an even weight -- a plan real CI could
// never run, since gate-bind attaches one conjunct per STEP, not per id. After the
// merge the 149 ids are correctly one unit and quality-security is (correctly)
// unbalanceable. quality-code divides on real step boundaries and balances for real;
// it is D1/D2's own worked example of a lane the mechanism suits.
const code = planned('quality-code', 8);
ck('the shard weights are BALANCED, not first-fit (quality-code, which genuinely divides)',
   (() => {
     if (!code) return false;
     const w = code.shards.map((s: { weight: number }) => s.weight);
     return Math.max(...w) - Math.min(...w) <= 2;
   })(), code?.shards.map((s: { weight: number }) => s.weight));
ck('quality-security correctly stays LOPSIDED: its dominant 149-id step is one unit',
   (() => {
     if (!sec) return false;
     const w = sec.shards.map((s: { weight: number }) => s.weight);
     return Math.max(...w) - Math.min(...w) > 2;
   })(), sec?.shards.map((s: { weight: number }) => s.weight));

// A MUTEX GROUP NEVER SPLITS. build-artifacts holds check:types and
// check:ci-command-tree in quality-code; ignoring the union puts them in
// different shards, which is how this control was proved to fire.
const homeOf = (lane: { shards: { index: number; ids: string[] }[] }, id: string): number =>
  lane.shards.find((s) => s.ids.includes(id))?.index ?? -1;
ck('a mutex group never splits across shards (quality-code build-artifacts)',
   code !== null && homeOf(code, 'check:types') === homeOf(code, 'check:ci-command-tree'),
   code && [homeOf(code, 'check:types'), homeOf(code, 'check:ci-command-tree')]);
ck('heavy is capped at one per shard', code !== null && code.shards.every((s: { heavy: number }) => s.heavy <= 1),
   code?.shards.map((s: { heavy: number }) => s.heavy));

// A WITHIN-LANE `needs` EDGE IS A CO-LOCATION CONSTRAINT, and the box does not
// say so. Twelve quality-www-build entries need build:www, a step in the same
// lane; a plan honouring only mutex would put a gate in a runner that never
// built the thing it validates.
const www = planned('quality-www-build', 3);
ck('a within-lane `needs` target shares its dependent\'s shard (build:www)',
   www !== null && homeOf(www, 'build:www') === homeOf(www, 'check:ci-seo'),
   www && [homeOf(www, 'build:www'), homeOf(www, 'check:ci-seo')]);
ck('and it is ORDERED first, because CI steps run in file order',
   (() => {
     const shard = www?.shards.find((s: { ids: string[] }) => s.ids.includes('build:www'));
     return shard !== undefined && shard.ids.indexOf('build:www') < shard.ids.indexOf('check:ci-seo');
   })(), www?.shards.find((s: { ids: string[] }) => s.ids.includes('build:www'))?.ids.slice(0, 3));

ck('runs-on and timeout come from the LANE, never re-derived',
   sec !== null && sec.shards.every((s: { runsOn: string; timeoutMinutes: number | null }) =>
     s.runsOn === caps.get('quality-security')?.runsOn &&
     s.timeoutMinutes === caps.get('quality-security')?.timeoutMinutes),
   [caps.get('quality-security')?.runsOn, caps.get('quality-security')?.timeoutMinutes]);
ck('the plan is DETERMINISTIC: two calls on one lock agree byte for byte',
   JSON.stringify(shardPlan(lock, caps, { 'quality-security': 4 })) ===
     JSON.stringify(shardPlan(lock, caps, { 'quality-security': 4 })));

// THE REFUSALS, every one of them driven on the real lock. A refusal nobody has
// watched fire is not a refusal.
ck('MORE SHARDS THAN GATES REFUSES, and says the ceiling',
   refusal('quality-branch', 6).includes('Ask for at most 5'), refusal('quality-branch', 6));
ck('the ceiling is UNITS, not entries: 16 www entries are 4 units',
   refusal('quality-www-build', 5).includes('only 4 indivisible unit(s) (16 entries'),
   refusal('quality-www-build', 5));
ck('a lane with ZERO lock entries refuses (quality-submodule-branches is real)',
   refusal('quality-submodule-branches', 2).includes('ZERO entries in the lock'),
   refusal('quality-submodule-branches', 2));
ck('a lane the workflow does not define refuses',
   refusal('quality-nowhere', 2).includes('not a job in the workflow'), refusal('quality-nowhere', 2));
// T-SCHED B2 D1 MOVED THIS NUMBER. Before the step-merge, quality-code counted 8 heavy
// IDS -- check:lint five times over (all one step) plus three more -- and refused any
// count under 8. After it, the five check:lint* ids are one unit with one heavy peak,
// so the real floor is the number of heavy UNITS, measured here rather than hand-typed
// so a future lock change cannot make this assertion stale silently.
const heavyFloor = (lane: string): number => {
  const total = laneEntries(lane).length;
  for (let n = 1; n <= total; n += 1) {
    if (!refusal(lane, n).includes('heavy is capped at one per shard')) return n;
  }
  return -1;
};
const codeHeavyFloor = heavyFloor('quality-code');
ck('more heavy gates than shards refuses, naming the corrected minimum',
   refusal('quality-code', codeHeavyFloor - 1).includes(`Ask for at least ${codeHeavyFloor} shards`),
   { floor: codeHeavyFloor, refusal: refusal('quality-code', codeHeavyFloor - 1) });
// THE POINT OF D1. Before the step-merge this exact count refused outright -- 8 heavy
// ids could not fit in 4 shards -- which was the wrong answer: the five check:lint* ids
// are one process, one runner, one heavy peak. This proves the fix, not just its
// arithmetic.
const code4 = planned('quality-code', 4);
ck('quality-code now shards at 4 (was an unconditional refusal before D1)',
   code4 !== null && code4.shards.every((s: { heavy: number }) => s.heavy <= 1),
   code4?.shards.map((s: { heavy: number }) => s.heavy));
// check:lint and its four siblings all ride ONE emitted step, so a plan cannot split
// them across legs: gate-bind attaches exactly one conjunct to that one `run:` block.
ck('ids sharing one emitted step (Lint) land in the same shard',
   (() => {
     if (!code) return false;
     const lintIds = lock
       .filter((e: any) => e.ci?.kind === 'step' && e.ci.job === 'quality-code' && e.ci.step === 'Lint')
       .map((e: any) => e.id);
     const homes = new Set(lintIds.map((id: string) => homeOf(code, id)));
     return homes.size === 1;
   })());
// CORRECTED 2026-09-09: this asserted the OPPOSITE and was encoding a bug as a rule.
// quality-go's account-vitest mutex group holds two heavy gates, and refusing the lane
// at every shard count was refusing arithmetic: gate-spec.ts:44 defines mutex as "no two
// gates sharing a group overlap", and heavy bounds CONCURRENT heap, so two heavies that
// can never run together peak at one. A needs-merged unit is the opposite case and still
// refuses, which is the second half below.
ck('two heavies in ONE MUTEX GROUP shard, because mutex means they never coexist',
   !JSON.stringify(shardPlan(lock, caps, { 'quality-go': 2 })).includes('No shard count satisfies'),
   refusal('quality-go', 2));
ck('CONTROL: a unit merged by within-lane NEEDS with two heavies still refuses',
   (() => {
     // A REAL LANE NAME, because shardPlan refuses a lane the workflow does not define
     // BEFORE it ever reaches the heavy rule -- a synthetic job name made this control
     // pass for the wrong reason on its first run.
     const synthetic = [
       { id: 'a', ci: { job: 'quality-static', kind: 'step', step: 'A' }, heavy: true },
       { id: 'b', ci: { job: 'quality-static', kind: 'step', step: 'B' }, heavy: true, needs: ['a'] },
       { id: 'c', ci: { job: 'quality-static', kind: 'step', step: 'C' } },
     ];
     return JSON.stringify(shardPlan(synthetic, caps, { 'quality-static': 2 })).includes(
       'No shard count satisfies'
     );
   })());
ck('zero shards is not a shard count',
   JSON.stringify(shardPlan(lock, caps, { 'quality-static': 0 })).includes('integer >= 1'));
ck('an empty lock refuses rather than planning nothing',
   JSON.stringify(shardPlan([], caps, { 'quality-static': 2 })).includes('EMPTY lock'));
ck('naming no lanes at all refuses',
   JSON.stringify(shardPlan(lock, caps, {})).includes('no lanes at all'));

// THE OTHER DIRECTION, so the refusals above cannot be satisfied by a planner
// that refuses everything.
ck('CONTROL: a shardable lane still PLANS (quality-static x3)',
   (() => {
     const st = planned('quality-static', 3);
     return st !== null && st.shards.length === 3 && st.units === st.entries;
   })(), refusal('quality-static', 3));

// T-SCHED B2 D2. shardAssignment takes counts/ceilings as PARAMETERS (not the real
// SHARD_COUNTS/SHARD_REPLICATED_MAX, which are empty today), so fixtures exercise all
// four shapes against the REAL lock without waiting for a lane to be declared sharded.
const assign = (job: string, counts: Record<string, number>, ceilings: Record<string, number>, emitting?: unknown[]) =>
  shardAssignment(job, lock as any, caps, (emitting ?? []) as any, counts, ceilings);

ck('a lane absent from counts returns null, not a refusal',
   assign('quality-static', {}, {}) === null);

ck('a lane asked to shard with no declared ceiling refuses',
   (() => {
     const r = assign('quality-code', { 'quality-code': 4 }, {});
     return r !== null && 'error' in r && r.error.includes('no matching SHARD_REPLICATED_MAX entry');
   })());

// A deliberately PARTIAL emitting list (only Lint) so replicated is neither 0 nor
// everything, proving the computation reads `emitting` rather than a constant.
const partial = assign('quality-code', { 'quality-code': 4 }, { 'quality-code': 1 }, [{ step: 'Lint' }]);
ck('replicated names ids the partial emitting set does not cover, never the ones it does',
   (() => {
     if (partial === null || 'error' in partial) return false;
     const lintIds = new Set(stepIds('quality-code', 'Lint'));
     const overlap = partial.replicated.filter((id: string) => lintIds.has(id));
     return overlap.length === 0 && partial.replicated.length > 0;
   })(), partial && !('error' in partial) ? partial.replicated : partial);
ck('a lane clearing its ceiling still returns real legs',
   partial !== null && !('error' in partial) && partial.legs.size > 0,
   partial && !('error' in partial) ? partial.legs.size : partial);

ck('a replicated share over its declared ceiling refuses, naming both numbers',
   (() => {
     const r = assign('quality-code', { 'quality-code': 4 }, { 'quality-code': 0.01 }, [{ step: 'Lint' }]);
     return r !== null && 'error' in r &&
       r.error.includes('run OUTSIDE any emitted region') &&
       r.error.includes('Ceiling for quality-code is 1%');
   })());

console.log(`TOTAL\t${bad}`);
TS
)"

echo "$OUT" | grep -E '^(PASS|FAIL)' | while IFS=$'\t' read -r verdict label; do
    if [[ "$verdict" == "PASS" ]]; then log_pass "$label"; else log_fail "$label"; fi
done

FAILURES="$(echo "$OUT" | sed -n 's/^TOTAL\t//p')"
if [[ -z "$FAILURES" ]]; then
    log_fail "the probe printed no TOTAL line, so nothing was asserted"
    echo "$OUT" | tail -5
    exit 1
fi
[[ "$FAILURES" == "0" ]] || {
    log_fail "lane derivation: $FAILURES failure(s)"
    exit 1
}
# MEASURED, not hand-typed: a hardcoded "35" here already went stale once, silently,
# when T-SCHED B2 added assertions without anyone updating this line.
ASSERTION_COUNT="$(echo "$OUT" | grep -cE '^PASS')"
log_pass "lane derivation and sharding: ${ASSERTION_COUNT} assertion(s), including the comment case both ways, nine sharding refusals, and T-SCHED B2's shard-assignment controls"
