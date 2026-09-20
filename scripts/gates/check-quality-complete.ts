#!/usr/bin/env node
/**
 * The `quality-complete` aggregator: every declared quality SHARD must have reported.
 *
 * WHY A SECOND AGGREGATOR, when `ci-complete` already exists. `ci-complete` aggregates
 * top-level jobs in `ci.yml`, and `.ci/rediacc_ci/quality/ci_job_aggregation.py` keeps its
 * wiring honest in four ways. Neither can see inside `ci-quality.yml`, and neither can see
 * a MATRIX at all: a matrix job produces ONE roll-up result for every leg, so a leg that
 * was never created is indistinguishable from a leg that passed. Drop half the entries out
 * of the `include:` list and the job still reports success, having run half the gates.
 *
 * That is the failure this file exists for, and it is the same one the whole estate is
 * built against: a green that means nothing because the work never ran.
 *
 * TWO HALVES, and they are not interchangeable.
 *
 *   STATIC (the default invocation). The declared shard counts live in ONE place,
 *   `SHARD_COUNTS` in scripts/ci-runner/lanes.ts, and both the matrix emitter and this
 *   aggregator read it. This half asserts the workflow AGREES with that constant, in both
 *   directions: a sharded lane must have an aggregator job that `needs:` it, and an
 *   aggregator job must not exist while nothing is sharded. It also asserts the declared
 *   counts are REALISABLE, by running the same `shardPlan` the emitter runs; a plan the
 *   emitter would refuse must not sit in the constant looking wired.
 *
 *   RUNTIME (`--receipts <dir>`). Each shard writes a receipt naming itself and its own
 *   result; CI collects them as artifacts and hands the directory here. This half is the
 *   box's acceptance: the received shard SET equals the declared shard set, no result is
 *   anything other than success, and the declared list was not empty.
 *
 * WHY A SET AND NOT A COUNT, on clause 1. "Four receipts for four declared shards" is
 * satisfied by four copies of shard 1. The key is `<lane>#<index>/<of>`, so a duplicate is
 * a duplicate and a gap is a gap, and the message names which.
 *
 * WHY A RECEIPT CARRIES ITS OWN `of` AND GATE COUNT. A shard that ran against a DIFFERENT
 * plan than the aggregator read is the composition failure in miniature: the totals agree
 * and the contents do not. A receipt saying `2 of 3` when the aggregator expects `of: 4`
 * is refused, and so is one that ran 41 gates where the plan says 43.
 *
 * ANYTHING OTHER THAN `success` IS A FAILURE, including a value this file has never seen.
 * `failure` and `cancelled` are what the box names; `skipped`, `` and a typo are UNKNOWN,
 * and unknown folded into fine is the exact defect the estate refuses.
 *
 * TEST SEAM. `QUALITY_COMPLETE_ROOT` points the lock and workflow reads at another tree,
 * so a plant can damage a COPY rather than a generated artifact nobody may hand-edit.
 *
 * NOT YET REGISTERED, deliberately, and there is no `---- gate ----` header for the same
 * reason `.ci/rediacc_ci/check_pytest.py` carries none: a header whose id no manifest entry
 * holds makes `check:ci-gate-bind` refuse by name ("no manifest entry with id ..."), which
 * would be a declaration that reads as wired and is not. Registration is the root driver's,
 * via package.json, scripts/ci-runner/manifest.ts and the workflow step.
 *
 * T-SCHED B2 D5, second clause -- CLOSED, and the lane below is the answer. The gate
 * used to declare `lane: quality-code`, which is the box's own named trap: once
 * `quality-code` is sharded, gate-bind ANDs `matrix.shard == N` onto every step of that
 * lane's region, including this gate's own, so the aggregator would run on ONE leg and
 * skip on the rest -- watching a matrix from inside a leg of it, and reporting green on
 * every leg where it never ran.
 *
 * WHY THE OBVIOUS MOVE WAS REFUSED, having been attempted and reverted once already.
 * `quality-branch` hosts the other hand-registered structural gates
 * (`check_plan_boxes.py`, `check_resprofile.py`) and is unshardable, because it has no
 * `- id: setup` and invariant 11 therefore forbids a region there at all. It
 * also runs on ubuntu-slim, which has no node, and node is this gate's declared need.
 * `quality-submodule-branches` is the same shape. Every OTHER lane has node and is a
 * live `SHARD_COUNTS` candidate. No existing lane answers both halves.
 *
 * SO THE LANE IS A NEW ONE. `quality-wiring` (ci-quality.yml, the last job in the file)
 * is node and nothing else, holds no gate-bind region, and hand-writes the step this
 * header names. Unshardable is ASSERTED rather than intended: `partitionFindings`
 * below refuses this lane appearing in `SHARD_COUNTS`, so the trap is not re-entered by
 * populating a constant in another file.
 *
 * THE COMPLETENESS CLAUSE, and why a partition needs three sets rather than two. A job
 * of this workflow is one of: region-bearing (gate-bind owns its steps), declared
 * hand-written (`DECLARED_HAND_WRITTEN_LANES`, each with the reason recorded beside it),
 * or UNDECIDED (`UNDECIDED_LANES`) -- setup-having and region-less, hand-written by
 * omission rather than by design. A two-set partition inferring "hand-written" from "has
 * no region today" would grandfather in every future lane that simply never got a gate
 * registered, which is the drift the clause exists to catch. The third set makes that
 * gap a NAMED, printed decision instead, and its members are deliberately not decided
 * here.
 *
 * Usage:
 *   npx tsx scripts/gates/check-quality-complete.ts                 the static wiring half
 *   npx tsx scripts/gates/check-quality-complete.ts --receipts DIR  the runtime half
 *   npx tsx scripts/gates/check-quality-complete.ts --selftest      prove it can fail
 *
 * ---- gate ----
 * step: Quality shard aggregation
 * lane: quality-wiring
 * needs: node
 * selftest: true
 * why: a matrix job reports ONE result for every leg, so a leg that was never created is
 *   indistinguishable from a leg that passed; this asserts the declared shard SET reported
 * ---- end gate ----
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { type Shard, SHARD_COUNTS, laneCapabilities, shardPlan } from '../ci-runner/lanes.js';
import { laneCanEmit, rewriteStrategyRegions } from '../gate-bind.js';
import { GREEN, NC, RED } from '../lib/console.js';
import { runControls } from '../lib/controls.js';
import { envRoot } from '../lib/repo-root.js';

const ROOT = envRoot('QUALITY_COMPLETE_ROOT');
const LOCK = 'scripts/ci-runner/gates.lock.json';
const WORKFLOW = '.github/workflows/ci-quality.yml';

/** The job that aggregates the shards. Named once so a rename reds loudly. */
export const AGGREGATOR_JOB = 'quality-complete';

/**
 * Anti-vacuity floor on the lock. `ci-quality.yml` has carried hundreds of registered
 * steps for its whole life; a read that returns fewer than this found a layout it does
 * not understand, and every "no shard is missing" verdict below would be computed from
 * nothing.
 */
export const MIN_LOCK_ENTRIES = 100;

// --------------------------------------------------------------------------- Receipts ---------------------------------------------------------------------------

/** What one shard writes about itself when it finishes. */
export interface ShardReceipt {
  lane: string;
  index: number;
  of: number;
  /** The leg's own conclusion. Only `success` is acceptable. */
  result: string;
  /** How many gates the leg actually ran, so a re-planned shard cannot hide. */
  gates: number;
  /** Where it was read from, for the message. */
  source: string;
}

export const shardKey = (lane: string, index: number, of: number): string =>
  `${lane}#${index}/${of}`;

/** Every `*.json` in `dir` or one level below it: download-artifact makes a dir per leg. */
export function readReceipts(dir: string): { receipts: ShardReceipt[]; problems: string[] } {
  const receipts: ShardReceipt[] = [];
  const problems: string[] = [];
  const files: string[] = [];
  const walk = (at: string, depth: number): void => {
    let names: string[];
    try {
      names = readdirSync(at).sort();
    } catch (e) {
      problems.push(`${at}: cannot be listed (${String(e)})`);
      return;
    }
    for (const name of names) {
      const full = path.join(at, name);
      if (statSync(full).isDirectory()) {
        if (depth > 0) walk(full, depth - 1);
        continue;
      }
      if (name.endsWith('.json')) files.push(full);
    }
  };
  walk(dir, 1);
  for (const file of files) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(file, 'utf-8'));
    } catch (e) {
      problems.push(`${file}: not readable as JSON (${String(e)})`);
      continue;
    }
    const r = parsed as Partial<ShardReceipt>;
    if (
      typeof r.lane !== 'string' ||
      typeof r.index !== 'number' ||
      typeof r.of !== 'number' ||
      typeof r.result !== 'string' ||
      typeof r.gates !== 'number'
    ) {
      problems.push(
        `${file}: a receipt needs lane, index, of, result and gates; got ${JSON.stringify(parsed)}`
      );
      continue;
    }
    receipts.push({ ...(r as ShardReceipt), source: file });
  }
  return { receipts, problems };
}

/**
 * The box's three acceptance clauses, plus the two that keep clause 1 from being
 * satisfiable by the wrong four receipts.
 */
export function judgeReceipts(
  declared: readonly Shard[],
  received: readonly ShardReceipt[]
): string[] {
  const findings: string[] = [];

  // CLAUSE 3 FIRST, because it is the one that makes the other two mean anything.
  if (declared.length === 0) {
    findings.push(
      'the declared shard list is EMPTY, so "every declared shard reported" is vacuously ' +
        'true. An include list that generated nothing is a matrix that ran nothing.'
    );
    return findings;
  }
  if (received.length === 0) {
    findings.push(
      `${declared.length} shard(s) declared and ZERO receipts found. Either no leg ran or ` +
        'the receipts were not collected; both mean this aggregator judged nothing.'
    );
    return findings;
  }

  // CLAUSE 1, as a SET. A count would be satisfied by four copies of shard 1.
  const want = new Map(declared.map((s) => [shardKey(s.lane, s.index, s.of), s]));
  const got = new Map<string, ShardReceipt[]>();
  for (const r of received) {
    const key = shardKey(r.lane, r.index, r.of);
    got.set(key, [...(got.get(key) ?? []), r]);
  }
  for (const key of [...want.keys()].sort()) {
    if (!got.has(key)) findings.push(`shard ${key} was declared and NEVER reported`);
  }
  for (const key of [...got.keys()].sort()) {
    if (!want.has(key)) {
      findings.push(
        `shard ${key} reported but is not in the declared plan. The leg ran against a ` +
          'different plan than this aggregator read.'
      );
    }
    const copies = got.get(key) ?? [];
    if (copies.length > 1) {
      findings.push(
        `shard ${key} reported ${copies.length} times: ${copies.map((c) => c.source).join(', ')}`
      );
    }
  }

  // CLAUSE 2, and anything that is not `success` counts, including a value nobody has seen before. Unknown is a failure.
  for (const r of received) {
    if (r.result !== 'success') {
      findings.push(
        `shard ${shardKey(r.lane, r.index, r.of)} reported result "${r.result}" (${r.source}); ` +
          'only "success" is acceptable'
      );
    }
  }

  // THE COMPOSITION CLAUSE. Totals that agree over different contents is the failure shape this programme keeps paying for.
  for (const r of received) {
    const declaredShard = want.get(shardKey(r.lane, r.index, r.of));
    if (declaredShard && declaredShard.ids.length !== r.gates) {
      findings.push(
        `shard ${shardKey(r.lane, r.index, r.of)} ran ${r.gates} gate(s) but the plan gives it ` +
          `${declaredShard.ids.length}. The leg and the aggregator read different plans.`
      );
    }
  }
  return findings;
}

// --------------------------------------------------------------------------- The static half: the constant, the plan, and the workflow must agree ---------------------------------------------------------------------------

/**
 * `needs:` per job, both spellings. Line-oriented on purpose, exactly like
 * `laneCapabilities`: this must run with no YAML dependency, and a gate that imports one
 * dies with ModuleNotFoundError on a clean runner while passing locally.
 */
export function parseJobNeeds(workflowText: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const jobRe = /^ {2}([A-Za-z0-9_-]+):\s*$/;
  let job: string | null = null;
  let inJobs = false;
  let inNeedsBlock = false;
  for (const raw of workflowText.split('\n')) {
    if (/^jobs:\s*$/.test(raw)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (raw !== '' && !/^\s/.test(raw) && !raw.startsWith('#')) break;
    const m = jobRe.exec(raw);
    if (m) {
      job = m[1] as string;
      out.set(job, []);
      inNeedsBlock = false;
      continue;
    }
    if (job === null) continue;
    if (/^\s*#/.test(raw)) continue;
    const inline = /^\s{4}needs:\s*\[(.*)\]\s*$/.exec(raw);
    if (inline) {
      out.set(
        job,
        (inline[1] as string)
          .split(',')
          .map((s) => s.trim())
          .filter((s) => s.length > 0)
      );
      inNeedsBlock = false;
      continue;
    }
    const single = /^\s{4}needs:\s*([A-Za-z0-9_-]+)\s*$/.exec(raw);
    if (single) {
      out.set(job, [single[1] as string]);
      inNeedsBlock = false;
      continue;
    }
    if (/^\s{4}needs:\s*$/.test(raw)) {
      inNeedsBlock = true;
      out.set(job, []);
      continue;
    }
    if (inNeedsBlock) {
      const item = /^\s{6}-\s*([A-Za-z0-9_-]+)\s*$/.exec(raw);
      if (item) {
        out.set(job, [...(out.get(job) ?? []), item[1] as string]);
        continue;
      }
      inNeedsBlock = false;
    }
  }
  return out;
}

/**
 * The both-directions wiring equality. Either half alone is dead: a sharded lane with no
 * aggregator is unaggregated, and an aggregator over lanes nobody sharded is a job that
 * asserts nothing on every run.
 */
export function wiringFindings(
  counts: Readonly<Record<string, number>>,
  needs: ReadonlyMap<string, string[]>
): string[] {
  const findings: string[] = [];
  const sharded = Object.keys(counts).sort();
  const hasAggregator = needs.has(AGGREGATOR_JOB);

  if (sharded.length > 0 && !hasAggregator) {
    findings.push(
      `${sharded.length} lane(s) are sharded (${sharded.join(', ')}) but ${WORKFLOW} has no ` +
        `\`${AGGREGATOR_JOB}\` job. A matrix job's result is ONE roll-up, so a leg that was ` +
        'never created is invisible without it.'
    );
  }
  if (sharded.length === 0 && hasAggregator) {
    findings.push(
      `${WORKFLOW} declares a \`${AGGREGATOR_JOB}\` job but SHARD_COUNTS is empty, so it ` +
        'aggregates nothing and would report success on every run.'
    );
  }
  if (hasAggregator) {
    const aggregatorNeeds = needs.get(AGGREGATOR_JOB) ?? [];
    for (const lane of sharded) {
      if (!aggregatorNeeds.includes(lane)) {
        findings.push(
          `${AGGREGATOR_JOB} does not \`needs:\` the sharded lane ${lane}, so it can run ` +
            'before that lane finishes and report on shards that have not reported yet.'
        );
      }
    }
  }
  return findings;
}

// --------------------------------------------------------------------------- The completeness partition: every job is region-bearing, declared hand-written, or an open decision ---------------------------------------------------------------------------

/**
 * The lane holding this gate's own step. Named once, so a rename reds by name rather
 * than by a `stepInJob` failure three gates away.
 */
export const HOST_LANE = 'quality-wiring';

/**
 * Jobs whose steps are hand-written BY DESIGN, each with the reason recorded beside it.
 *
 * EXPLICIT, NEVER INFERRED. "Hand-written" derived from "holds no region today" would
 * grandfather in every lane that merely never got a gate registered, which is the exact
 * drift the partition below exists to catch: a new job could be added, hold nothing, and
 * be reported as correct forever.
 *
 * The reason is load-bearing for a lane that HAS `- id: setup`. The two invariant-11
 * lanes cannot hold a region at all, so their entry is self-explaining; any other lane
 * in this map could have had one and does not, and that choice has to be written down
 * where the next reader finds it.
 */
export const DECLARED_HAND_WRITTEN_LANES: Readonly<Record<string, string>> = {
  'quality-branch': 'no `- id: setup`, so invariant 11 forbids a region here outright',
  'quality-submodule-branches': 'no `- id: setup`, so invariant 11 forbids a region here',
  [HOST_LANE]:
    'holds this gate, which polices the lane structure and therefore cannot run inside ' +
    'a lane an emitted region could conjunct onto one shard leg',
};

/**
 * Jobs that are setup-having, region-less and hand-written BY OMISSION -- nobody has
 * registered a manifest gate against them.
 *
 * NOT A SECOND ALLOWLIST, and the difference is the whole point. An entry here is an
 * open decision, printed on every run: either the lane earns a region by having gates
 * registered against it, or it moves into `DECLARED_HAND_WRITTEN_LANES` with its reason.
 * Deciding that is a design call this gate deliberately does not make; making the gap
 * VISIBLE instead of silent is what it does.
 */
export const UNDECIDED_LANES: readonly string[] = ['ci-quick', 'quality-packages', 'quality-go'];

/** Jobs holding a `# >>> gate-bind` region, read the same line-oriented way as the rest. */
export function regionLanes(workflowText: string): Set<string> {
  const out = new Set<string>();
  const lines = workflowText.split('\n');
  let job: string | null = null;
  let inJobs = false;
  for (const raw of lines) {
    if (/^jobs:\s*$/.test(raw)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (raw !== '' && !/^\s/.test(raw) && !raw.startsWith('#')) break;
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) {
      job = m[1] as string;
      continue;
    }
    if (job !== null && raw.trim().startsWith('# >>> gate-bind')) out.add(job);
  }
  return out;
}

/**
 * The partition, both directions, plus the two clauses that keep the allowlist honest.
 *
 * A job in NO set is the drift this exists for. A job in TWO sets is the same file
 * claiming a lane is generated and hand-written at once, and whichever answer a later
 * reader takes will be half wrong.
 */
export function partitionFindings(
  jobs: readonly string[],
  regions: ReadonlySet<string>,
  handWritten: Readonly<Record<string, string>>,
  undecided: readonly string[],
  hasSetup: (lane: string) => boolean,
  counts: Readonly<Record<string, number>>
): string[] {
  const findings: string[] = [];
  const known = new Set(jobs);
  const sets: [string, readonly string[]][] = [
    ['region-bearing', [...regions]],
    ['declared hand-written', Object.keys(handWritten)],
    ['undecided', undecided],
  ];

  // A NAME NO JOB ANSWERS TO, first: every clause below reads these lists, and a stale entry makes the union look complete while the lane it names is gone.
  for (const [what, members] of sets) {
    for (const lane of [...members].sort()) {
      if (!known.has(lane)) {
        findings.push(
          `${lane} is listed as ${what} but ${WORKFLOW} has no such job. The list and the ` +
            'workflow have drifted; fix the list, not the workflow.'
        );
      }
    }
  }

  for (const lane of [...jobs].sort()) {
    const inSets = sets.filter(([, members]) => members.includes(lane)).map(([what]) => what);
    if (inSets.length === 0) {
      findings.push(
        `${lane} is in NO set: it holds no \`# >>> gate-bind\` region, is not in ` +
          'DECLARED_HAND_WRITTEN_LANES, and is not named as an open decision. A lane ' +
          'nobody has decided about runs whatever it happens to hold, forever.'
      );
    }
    if (inSets.length > 1) {
      findings.push(`${lane} is in ${inSets.length} sets at once (${inSets.join(', ')})`);
    }
  }

  // THE ALLOWLIST CLAUSE. A lane with no setup step is hand-written by construction; one WITH a setup step chose to be, and the choice has to be recorded or the allowlist quietly absorbs lanes that should have earned a region.
  for (const [lane, why] of Object.entries(handWritten).sort()) {
    if (known.has(lane) && hasSetup(lane) && why.trim() === '') {
      findings.push(
        `${lane} is allowlisted as hand-written and HAS an \`- id: setup\` step, so it ` +
          'could hold a region, with no reason recorded for why it does not'
      );
    }
  }

  // THE SELF-REFERENCE CLAUSE. This gate's own lane being sharded is the trap D5b exists to close: its step would be conjuncted onto one leg and skip on the rest, reporting green from the legs where it never ran.
  if (Object.keys(counts).includes(HOST_LANE)) {
    findings.push(
      `${HOST_LANE} holds this gate's own step and is in SHARD_COUNTS. An emitted region ` +
        'there would conjunct this gate onto one leg of the matrix it is judging.'
    );
  }
  if (!Object.keys(handWritten).includes(HOST_LANE)) {
    findings.push(
      `${HOST_LANE} holds this gate's own step but is not in DECLARED_HAND_WRITTEN_LANES, ` +
        'so nothing keeps a region out of it.'
    );
  }
  return findings;
}

// --------------------------------------------------------------------------- The real run ---------------------------------------------------------------------------

function readOr(file: string, what: string): string | null {
  try {
    return readFileSync(path.join(ROOT, file), 'utf-8');
  } catch (e) {
    console.error(`${RED}✗${NC} ${what} could not be read at ${file}: ${String(e)}`);
    return null;
  }
}

function main(argv: readonly string[]): number {
  const lockText = readOr(LOCK, 'the gate lock');
  const workflowText = readOr(WORKFLOW, 'the quality workflow');
  if (lockText === null || workflowText === null) return 1;

  let lock: { id: string; ci: { kind: string; job?: string } }[];
  try {
    const parsed: unknown = JSON.parse(lockText);
    if (!Array.isArray(parsed)) throw new Error('the lock is not a JSON array');
    lock = parsed as typeof lock;
  } catch (e) {
    console.error(`${RED}✗${NC} ${LOCK} is not a gate array: ${String(e)}`);
    console.error('  Regenerate it with `npx tsx scripts/gen/gen-gates-lock.ts --write`.');
    return 1;
  }

  // ANTI-VACUITY, BOTH INPUTS, REFUSED SEPARATELY. An empty lock and an unparsed workflow produce the same confident "nothing is missing".
  if (lock.length < MIN_LOCK_ENTRIES) {
    console.error(
      `${RED}✗${NC} ${LOCK} holds ${lock.length} entries, under the floor of ${MIN_LOCK_ENTRIES}. ` +
        'This gate is not seeing the registry and its green would mean nothing.'
    );
    return 1;
  }
  const caps = laneCapabilities(workflowText);
  if (caps.size === 0) {
    console.error(
      `${RED}✗${NC} ${WORKFLOW} parsed to ZERO jobs, so no shard could be checked against ` +
        'anything. The reader, not the workflow, is what to fix first.'
    );
    return 1;
  }
  const needs = parseJobNeeds(workflowText);

  const sharded = Object.keys(SHARD_COUNTS).sort();
  let declared: Shard[] = [];
  if (sharded.length > 0) {
    const plan = shardPlan(lock, caps, SHARD_COUNTS);
    if ('error' in plan) {
      console.error(`${RED}✗${NC} SHARD_COUNTS is not realisable: ${plan.error}`);
      console.error('  The matrix emitter reads the same constant and would refuse the same way.');
      return 1;
    }
    declared = plan.lanes.flatMap((l) => l.shards);
  }

  const regions = regionLanes(workflowText);
  const shape =
    `${lock.length} lock entries, ${caps.size} jobs in ${path.basename(WORKFLOW)} ` +
    `(${regions.size} region-bearing, ${Object.keys(DECLARED_HAND_WRITTEN_LANES).length} ` +
    `declared hand-written, ${UNDECIDED_LANES.length} undecided), ` +
    `${sharded.length} sharded lane(s) [${sharded.join(', ') || 'none'}], ` +
    `${declared.length} declared shard(s), aggregator job ` +
    `${needs.has(AGGREGATOR_JOB) ? 'present' : 'absent'}`;

  /**
   * THE OPEN DECISION, PRINTED EVERY RUN, on the green path as loudly as on the red one.
   * These lanes have a setup step and no region: hand-written by omission, not by design.
   * A gate that only reported them when something else failed would be a gate that hides
   * the gap it was written to expose.
   */
  const openDecision = (): void => {
    if (UNDECIDED_LANES.length === 0) return;
    console.log(
      `  OPEN DECISION, ${UNDECIDED_LANES.length} lane(s) hand-written by omission rather ` +
        `than by design: ${[...UNDECIDED_LANES].sort().join(', ')}.`
    );
    console.log(
      '  Each either earns a `# >>> gate-bind` region by having gates registered against ' +
        'it, or moves into DECLARED_HAND_WRITTEN_LANES with the reason recorded.'
    );
  };

  // T-SCHED B2 D5, first clause. `rewriteStrategyRegions` re-asserted from THIS side, independently of `gate-bind --write`: a `matrix.shard` list that has drifted from `SHARD_COUNTS` (hand-edited, or left stale after a count change landed without `gate-bind --write` being re-run) is Finding 2's vacuity all over again -- a job whose real matrix does not match what this aggregator
  // believes it does. `gate-bind`'s own check is the first line of defense at write time; this is the second, independent one at judge time, so a bypass of one cannot silently defeat the other. Kept separate from `wiringFindings` (job-graph wiring) rather than merged into it, so that function's own fixtures do not need a real shard-strategy region added just to keep testing what
  // they already test.
  const findings = [
    ...wiringFindings(SHARD_COUNTS, needs),
    ...rewriteStrategyRegions(workflowText, SHARD_COUNTS),
    ...partitionFindings(
      [...caps.keys()],
      regionLanes(workflowText),
      DECLARED_HAND_WRITTEN_LANES,
      UNDECIDED_LANES,
      (lane) => laneCanEmit(workflowText, lane),
      SHARD_COUNTS
    ),
  ];

  const at = argv.indexOf('--receipts');
  if (at !== -1) {
    const dir = argv[at + 1];
    if (dir === undefined) {
      console.error(`${RED}✗${NC} --receipts needs a directory`);
      return 2;
    }
    const { receipts, problems } = readReceipts(dir);
    for (const p of problems) findings.push(p);
    findings.push(...judgeReceipts(declared, receipts));
    if (findings.length === 0) {
      console.log(
        `${GREEN}✓${NC} quality-complete: all ${declared.length} declared shard(s) reported ` +
          `success. ${shape}`
      );
      openDecision();
      return 0;
    }
  } else if (findings.length === 0) {
    console.log(`${GREEN}✓${NC} quality-complete wiring: ${shape}`);
    openDecision();
    return 0;
  }

  console.error(`${RED}✗${NC} quality-complete: ${findings.length} finding(s). ${shape}`);
  for (const f of findings) console.error(`  ${f}`);
  openDecision();
  console.error(
    '  Fix the wiring or the shard receipts. Do NOT lower the declared count to match what ' +
      'arrived: a shard that did not report is a shard whose gates did not run.'
  );
  return 1;
}

// --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

const shard = (lane: string, index: number, of: number, ids: number): Shard => ({
  lane,
  index,
  of,
  runsOn: 'ubuntu-latest',
  timeoutMinutes: 20,
  ids: Array.from({ length: ids }, (_, i) => `g${i}`),
  weight: ids,
  slow: 0,
  heavy: 0,
});

const receipt = (
  lane: string,
  index: number,
  of: number,
  gates: number,
  result = 'success'
): ShardReceipt => ({ lane, index, of, result, gates, source: `${lane}-${index}.json` });

const WF_SHARDED = [
  'jobs:',
  '  quality-security:',
  '    runs-on: ubuntu-latest',
  '  quality-complete:',
  '    needs: [quality-security]',
  '    runs-on: ubuntu-slim',
  '',
].join('\n');

// T-SCHED B2 D5, first clause: a real shard-strategy region, matching WF_SHARDED's `quality-security` job, for testing the wiring between this file and `rewriteStrategyRegions` rather than that function's own logic (already exhaustively covered by scripts/gate-bind.ts's own selftest).
const WF_SHARDED_WITH_REGION = [
  'jobs:',
  '  quality-security:',
  '    runs-on: ubuntu-latest',
  '    # >>> shard-strategy (generated; do not edit inside)',
  '    strategy:',
  '      fail-fast: false',
  '      matrix:',
  '        shard: [1, 2]',
  '    # <<< shard-strategy',
  '  quality-complete:',
  '    needs: [quality-security]',
  '    runs-on: ubuntu-slim',
  '',
].join('\n');

// T-SCHED B2, the completeness partition. Four jobs, one of each kind, plus the host lane: a region-bearing lane, a no-setup lane invariant 11 keeps hand-written, a setup-having lane nobody has decided about, and the lane this gate's own step lives in.
const WF_PARTITION = [
  'jobs:',
  '  quality-branch:',
  '    runs-on: ubuntu-slim',
  '  quality-code:',
  '    runs-on: ubuntu-latest',
  '    steps:',
  '      - id: setup',
  '      # >>> gate-bind (generated by scripts/gate-bind.ts --write; do not edit inside)',
  '      # <<< gate-bind',
  '  quality-go:',
  '    runs-on: ubuntu-latest',
  '    steps:',
  '      - id: setup',
  `  ${HOST_LANE}:`,
  '    runs-on: ubuntu-latest',
  '    steps:',
  '      - id: setup',
  '',
].join('\n');

const PART_JOBS: readonly string[] = ['quality-branch', 'quality-code', 'quality-go', HOST_LANE];
const PART_REGIONS: ReadonlySet<string> = new Set(['quality-code']);
const PART_HAND: Readonly<Record<string, string>> = {
  'quality-branch': 'no `- id: setup`, so invariant 11 forbids a region here',
  [HOST_LANE]: 'holds this gate, which must never be conjuncted onto a shard leg',
};
const PART_UNDECIDED: readonly string[] = ['quality-go'];
const PART_SETUP = (lane: string): boolean => lane !== 'quality-branch';

function selftest(): number {
  const two = [shard('quality-security', 1, 2, 40), shard('quality-security', 2, 2, 42)];
  const bothReported = [
    receipt('quality-security', 1, 2, 40),
    receipt('quality-security', 2, 2, 42),
  ];

  const cases = [
    // --- clause 1: the received SET equals the declared set -----------------
    {
      name: 'MATCH: every declared shard reported success is no finding',
      ok: judgeReceipts(two, bothReported).length === 0,
      detail: JSON.stringify(judgeReceipts(two, bothReported)),
    },
    {
      name: 'FIRES: a declared shard that never reported',
      ok: judgeReceipts(two, [bothReported[0] as ShardReceipt]).some((f) =>
        f.includes('quality-security#2/2 was declared and NEVER reported')
      ),
      detail: JSON.stringify(judgeReceipts(two, [bothReported[0] as ShardReceipt])),
    },
    {
      name: 'FIRES: a COUNT that matches while the composition does not (two copies of shard 1)',
      ok: (() => {
        const twice = [
          receipt('quality-security', 1, 2, 40),
          receipt('quality-security', 1, 2, 40),
        ];
        const f = judgeReceipts(two, twice);
        return (
          twice.length === two.length &&
          f.some((x) => x.includes('reported 2 times')) &&
          f.some((x) => x.includes('#2/2 was declared and NEVER reported'))
        );
      })(),
      detail: JSON.stringify(
        judgeReceipts(two, [
          receipt('quality-security', 1, 2, 40),
          receipt('quality-security', 1, 2, 40),
        ])
      ),
    },
    {
      name: 'FIRES: a receipt from a shard the plan does not declare',
      ok: judgeReceipts(two, [...bothReported, receipt('quality-security', 3, 3, 1)]).some((f) =>
        f.includes('is not in the declared plan')
      ),
    },
    {
      name: 'FIRES: a leg that ran against a different total (2 of 3, not 2 of 2)',
      ok: judgeReceipts(two, [
        bothReported[0] as ShardReceipt,
        receipt('quality-security', 2, 3, 42),
      ]).some((f) => f.includes('quality-security#2/3')),
    },
    // --- clause 2: no result other than success -----------------------------
    {
      name: 'FIRES: a shard whose result is failure',
      ok: judgeReceipts(two, [
        bothReported[0] as ShardReceipt,
        receipt('quality-security', 2, 2, 42, 'failure'),
      ]).some((f) => f.includes('reported result "failure"')),
    },
    {
      name: 'FIRES: a shard whose result is cancelled',
      ok: judgeReceipts(two, [
        bothReported[0] as ShardReceipt,
        receipt('quality-security', 2, 2, 42, 'cancelled'),
      ]).some((f) => f.includes('reported result "cancelled"')),
    },
    {
      name: 'FIRES: an UNKNOWN result is a failure too, not folded into fine',
      ok: judgeReceipts(two, [
        bothReported[0] as ShardReceipt,
        receipt('quality-security', 2, 2, 42, 'skipped'),
      ]).some((f) => f.includes('reported result "skipped"')),
    },
    // --- clause 3: the include list was non-empty ---------------------------
    {
      name: 'FIRES: an EMPTY declared list is a finding, never a vacuous pass',
      ok: judgeReceipts([], bothReported).some((f) => f.includes('declared shard list is EMPTY')),
    },
    {
      name: 'FIRES: zero receipts against a non-empty plan',
      ok: judgeReceipts(two, []).some((f) => f.includes('ZERO receipts found')),
    },
    // --- the composition clause ---------------------------------------------
    {
      name: 'FIRES: a leg that ran 41 gates where the plan gives it 42',
      ok: judgeReceipts(two, [
        bothReported[0] as ShardReceipt,
        receipt('quality-security', 2, 2, 41),
      ]).some((f) => f.includes('ran 41 gate(s) but the plan gives it 42')),
    },
    // --- the needs parser ----------------------------------------------------
    {
      name: 'needs: [a, b] inline form is read',
      ok:
        JSON.stringify(parseJobNeeds('jobs:\n  z:\n    needs: [a, b]\n').get('z')) ===
        JSON.stringify(['a', 'b']),
      detail: JSON.stringify(parseJobNeeds('jobs:\n  z:\n    needs: [a, b]\n').get('z')),
    },
    {
      name: 'the block list form is read too',
      ok:
        JSON.stringify(
          parseJobNeeds('jobs:\n  z:\n    needs:\n      - a\n      - b\n').get('z')
        ) === JSON.stringify(['a', 'b']),
    },
    {
      name: 'a bare `needs: a` is one dependency, not a character list',
      ok: JSON.stringify(parseJobNeeds('jobs:\n  z:\n    needs: abc\n').get('z')) === '["abc"]',
    },
    {
      name: 'CONTROL: a job with no needs: is present with an empty list, not absent',
      ok: parseJobNeeds('jobs:\n  z:\n    runs-on: x\n').get('z')?.length === 0,
    },
    {
      name: 'CONTROL: a `needs:` inside a comment is not a dependency',
      ok: parseJobNeeds('jobs:\n  z:\n    # needs: [a]\n    runs-on: x\n').get('z')?.length === 0,
    },
    // --- the wiring equality, both directions --------------------------------
    {
      name: 'MATCH: nothing sharded and no aggregator job is the state today',
      ok:
        wiringFindings({}, parseJobNeeds('jobs:\n  quality-security:\n    runs-on: x\n')).length ===
        0,
    },
    {
      name: 'FIRES: a sharded lane with NO aggregator job',
      ok: wiringFindings(
        { 'quality-security': 4 },
        parseJobNeeds('jobs:\n  quality-security:\n    runs-on: x\n')
      ).some((f) => f.includes('has no `quality-complete` job')),
    },
    {
      name: 'FIRES: an aggregator job while nothing is sharded',
      ok: wiringFindings({}, parseJobNeeds(WF_SHARDED)).some((f) =>
        f.includes('aggregates nothing')
      ),
    },
    {
      name: 'FIRES: an aggregator that does not `needs:` a sharded lane',
      ok: wiringFindings({ 'quality-code': 3 }, parseJobNeeds(WF_SHARDED)).some((f) =>
        f.includes('does not `needs:` the sharded lane quality-code')
      ),
    },
    {
      name: 'MATCH: a sharded lane the aggregator DOES need is no finding',
      ok: wiringFindings({ 'quality-security': 4 }, parseJobNeeds(WF_SHARDED)).length === 0,
      detail: JSON.stringify(wiringFindings({ 'quality-security': 4 }, parseJobNeeds(WF_SHARDED))),
    },
    // --- T-SCHED B2 D5, first clause: the strategy-shape re-assertion ---------
    {
      name: 'FIRES (via rewriteStrategyRegions): a sharded lane with no shard-strategy region',
      ok: rewriteStrategyRegions(WF_SHARDED, { 'quality-security': 2 }).some((f) =>
        f.includes('no shard-strategy region')
      ),
    },
    {
      name: 'MATCH: a shard-strategy region agreeing with SHARD_COUNTS is silent',
      ok: rewriteStrategyRegions(WF_SHARDED_WITH_REGION, { 'quality-security': 2 }).length === 0,
      detail: JSON.stringify(
        rewriteStrategyRegions(WF_SHARDED_WITH_REGION, { 'quality-security': 2 })
      ),
    },
    {
      name: 'FIRES: a shard-strategy region whose count disagrees with SHARD_COUNTS',
      ok: rewriteStrategyRegions(WF_SHARDED_WITH_REGION, { 'quality-security': 4 }).some((f) =>
        f.includes('expected [1, 2, 3, 4]')
      ),
    },
    // --- T-SCHED B2, the completeness partition ------------------------------
    {
      name: 'MATCH: a workflow whose jobs partition cleanly is no finding',
      ok:
        partitionFindings(PART_JOBS, PART_REGIONS, PART_HAND, PART_UNDECIDED, PART_SETUP, {})
          .length === 0,
      detail: JSON.stringify(
        partitionFindings(PART_JOBS, PART_REGIONS, PART_HAND, PART_UNDECIDED, PART_SETUP, {})
      ),
    },
    {
      name: 'FIRES: a lane in NEITHER set (a new job nobody decided about)',
      ok: partitionFindings(
        [...PART_JOBS, 'quality-new'],
        PART_REGIONS,
        PART_HAND,
        PART_UNDECIDED,
        PART_SETUP,
        {}
      ).some((f) => f.includes('quality-new is in NO set')),
    },
    {
      name: 'FIRES: a lane in BOTH sets (region-bearing and allowlisted at once)',
      ok: partitionFindings(
        PART_JOBS,
        PART_REGIONS,
        { ...PART_HAND, 'quality-code': 'a reason that does not make it hand-written' },
        PART_UNDECIDED,
        PART_SETUP,
        {}
      ).some((f) => f.includes('quality-code is in 2 sets at once')),
    },
    {
      name: 'FIRES: an allowlisted lane WITH `- id: setup` and no recorded reason',
      ok: partitionFindings(
        PART_JOBS,
        PART_REGIONS,
        { ...PART_HAND, 'quality-go': '   ' },
        [],
        PART_SETUP,
        {}
      ).some((f) => f.includes('quality-go is allowlisted as hand-written and HAS an')),
      detail: JSON.stringify(
        partitionFindings(
          PART_JOBS,
          PART_REGIONS,
          { ...PART_HAND, 'quality-go': '   ' },
          [],
          PART_SETUP,
          {}
        )
      ),
    },
    {
      name: 'CONTROL: a lane with NO setup step needs no recorded reason',
      ok: !partitionFindings(
        PART_JOBS,
        PART_REGIONS,
        { ...PART_HAND, 'quality-branch': '' },
        PART_UNDECIDED,
        PART_SETUP,
        {}
      ).some((f) => f.includes('quality-branch is allowlisted')),
    },
    {
      name: 'FIRES: a list naming a job the workflow no longer defines',
      ok: partitionFindings(
        PART_JOBS,
        PART_REGIONS,
        PART_HAND,
        [...PART_UNDECIDED, 'quality-gone'] as readonly string[],
        PART_SETUP,
        {}
      ).some((f) => f.includes('quality-gone is listed as undecided')),
    },
    {
      name: `FIRES: ${HOST_LANE}, which holds this gate's own step, appearing in SHARD_COUNTS`,
      ok: partitionFindings(PART_JOBS, PART_REGIONS, PART_HAND, PART_UNDECIDED, PART_SETUP, {
        [HOST_LANE]: 2,
      }).some((f) => f.includes('is in SHARD_COUNTS')),
    },
    {
      name: `FIRES: ${HOST_LANE} dropped out of the hand-written allowlist`,
      ok: partitionFindings(
        PART_JOBS,
        PART_REGIONS,
        { 'quality-branch': 'no `- id: setup`, so invariant 11 forbids a region here' },
        [...PART_UNDECIDED, HOST_LANE],
        PART_SETUP,
        {}
      ).some((f) => f.includes('is not in DECLARED_HAND_WRITTEN_LANES')),
    },
    {
      name: 'the region reader finds a region lane and not a region-less one',
      ok:
        regionLanes(WF_PARTITION).has('quality-code') &&
        !regionLanes(WF_PARTITION).has('quality-go'),
      detail: JSON.stringify([...regionLanes(WF_PARTITION)]),
    },
    {
      name: 'CONTROL: a `# >>> gate-bind` in the file header, above `jobs:`, belongs to no lane',
      ok:
        JSON.stringify([...regionLanes(`# >>> gate-bind in a file comment\n${WF_PARTITION}`)]) ===
        JSON.stringify([...regionLanes(WF_PARTITION)]),
    },
    {
      name: 'CONTROL: the live workflow really partitions, so the clause is not fixture-only',
      ok: (() => {
        const text = readOr(WORKFLOW, 'the quality workflow');
        if (text === null) return false;
        const jobs = [...laneCapabilities(text).keys()];
        return (
          jobs.length >= 10 &&
          partitionFindings(
            jobs,
            regionLanes(text),
            DECLARED_HAND_WRITTEN_LANES,
            UNDECIDED_LANES,
            (lane) => laneCanEmit(text, lane),
            SHARD_COUNTS
          ).length === 0
        );
      })(),
    },
    // --- the receipt reader ---------------------------------------------------
    {
      name: 'a receipt missing a required field is a PROBLEM, not a silent skip',
      ok: (() => {
        const dir = path.join(ROOT, 'node_modules', '.cache', 'quality-complete-selftest');
        return readReceipts(path.join(dir, 'does-not-exist')).problems.length === 1;
      })(),
    },
  ];

  const failed = runControls(cases);
  console.log(
    failed === 0
      ? `${GREEN}✓${NC} ${cases.length} controls passed`
      : `${RED}✗${NC} ${failed}/${cases.length} controls failed`
  );
  return failed === 0 ? 0 : 1;
}

process.exit(process.argv.includes('--selftest') ? selftest() : main(process.argv.slice(2)));
