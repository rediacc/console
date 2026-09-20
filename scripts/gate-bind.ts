/**
 * check:ci-gate-bind -- a gate's four registrations must match what its own header says.
 *
 * WHY. Registering a gate means editing package.json, scripts/ci-runner/manifest.ts and
 * .github/workflows/ci-quality.yml by hand, and each has a convention that only ever
 * announces itself as a red gate: a Python gate must be the BARE path in package.json
 * (a `python3` prefix makes check:ci-parity resolve its leaves to `[python3]`), the
 * manifest's leaves must equal what the npm script resolves to and be git-tracked, and
 * the workflow step name must match `ci.step` exactly. The JOB is worse, because it is
 * silent: check:ci-docker-npm-pins landed in quality-static, which checks out no
 * submodules, so the file it exists to scan dropped out of its enumeration and its
 * correct exclusions were reported as dead (CI job 100870135489).
 *
 * All four are derivable from the gate's own header plus lane capabilities read out of
 * the workflow. This is the CHECK half: it re-derives and compares. Nothing is emitted
 * yet, so a mismatch is reported rather than silently rewritten -- the migration is
 * coexist-and-drain, and a gate with no header is simply not this gate's business.
 *
 * ---- gate ----
 * step: Gate binding
 * needs: node
 * selftest: true
 * why: four hand-written registrations per gate, each with a convention that only
 *      announces itself as a red gate. The binder declares itself through the same
 *      header it reads, so the first thing it verifies is that IT is registered right
 * ---- end gate ----
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import {
  SHARD_COUNTS,
  SHARD_REPLICATED_MAX,
  laneCapabilities,
  placeGate,
  satisfies,
  shardPlan,
} from './ci-runner/lanes.js';
import type { GateKind } from './lib/gate-header.js';
import {
  derivedId,
  derivedRun,
  headerError,
  inferredNeeds,
  parseGateHeader,
} from './lib/gate-header.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WORKFLOW = '.github/workflows/ci-quality.yml';
/**
 * EVERY tracked script, not just conventionally-named ones.
 *
 * This was `/(check|test)[-_][\w-]+\.(py|sh|ts)$/`, a naming heuristic standing in for
 * correctness. `--extract check:ci-shell-format` wrote a valid header into
 * .ci/scripts/security/shfmt.sh -- which matches no such name -- and this gate then
 * reported "2 declared gate(s)" and a clean bill of health while ignoring the third
 * entirely. A declaration that is silently not read is worse than one that is rejected.
 *
 * `bind()` returns null for a file with no header, so the filter costs a read per file
 * and buys the guarantee that a header anywhere is a header that counts.
 */
const SUBJECT = /\.(py|sh|ts)$/;

/**
 * ...and the gate-test tree is NO LONGER EXCLUDED. It was, for two reasons, and W2.3
 * retired both of them on 2026-09-06. The history is kept because a future reader who
 * finds a fixture parsing as a declaration will want to know this was tried once.
 *
 *   1. WAS: .ci/scripts/test/gates/test-gate-header.sh carries sample headers as FIXTURE
 *      data, quoted array elements it feeds to the parser, and widening SUBJECT read one
 *      as a real declaration for `step: Dockerfile npm pins',` (trailing quote included).
 *      NOW: that file carries a REAL header of its own at the top, and the parser takes
 *      the first block, so the quoted elements below it are never reached. Re-measured:
 *      it parses as kind battery riding "Quality-gate unit tests", which is true of it.
 *   2. WAS: all gate-tests share the single step 'Quality-gate unit tests' and none owns
 *      it, so none could legitimately declare one, and excluding the tree said that once
 *      instead of per file.
 *      NOW: `kind: battery` says exactly that, per file, in the file. All 148 declare it.
 *
 * WHY THIS MATTERED ENOUGH TO CHANGE. While the exclusion stood, every header in that
 * tree was invisible to the only instrument that checks headers. Proved by planting a
 * malformed block in one of them and watching `--dry-run` exit 0 without naming the
 * file. 148 headers that nothing reads are 148 claims nobody verifies.
 */
const NOT_SUBJECT = /^$/;

const read = (rel: string): string => fs.readFileSync(path.join(ROOT, rel), 'utf-8');

/**
 * Tracked subjects that are ACTUALLY PRESENT, plus the ones that are not.
 *
 * `git ls-files` reports the INDEX, and this gate then reads the WORKTREE. In a shared
 * checkout those disagree the moment another session deletes a tracked file: on
 * 2026-09-06 a peer ran this mid-way through a batch that removed docker-compose.yml,
 * Rediaccfile and others, and readFileSync threw ENOENT out of node:fs. A stack trace is
 * not a verdict -- the reader cannot tell "your gates are mis-registered" from "a file
 * moved under me". Absent files are collected and REFUSED by name instead.
 */
const trackedSubjects = (): { present: string[]; missing: string[] } => {
  const listed = execFileSync(
    'git',
    ['-C', ROOT, 'ls-files', '.ci/scripts', '.ci/rediacc_ci', 'scripts'],
    {
      encoding: 'utf-8',
    }
  )
    .split('\n')
    .filter((f) => f !== '' && SUBJECT.test(f) && !NOT_SUBJECT.test(f));
  const present: string[] = [];
  const missing: string[] = [];
  for (const f of listed) {
    (fs.existsSync(path.join(ROOT, f)) ? present : missing).push(f);
  }
  return { present, missing };
};

/** One extraction attempt: every guard, no I/O decision. `next` is null when refused. */
export function planExtract(
  manifestText: string,
  id: string,
  readFile: (f: string) => string,
  pkgRun: string,
  caps: ReturnType<typeof laneCapabilities>,
  strip: boolean
): { file: string; next: string; step: string; job: string } | { error: string } {
  const reg = registered(manifestText, id);
  if ('error' in reg) return { error: reg.error };
  if (!inScope(reg.file)) {
    return {
      error: `${reg.file} is outside the scan (.ci/scripts, scripts); stays hand-registered`,
    };
  }
  const sharers = (
    manifestText.match(
      new RegExp(`step: '${reg.step.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}'`, 'g')
    ) ?? []
  ).length;
  if (sharers > 1) {
    return { error: `step "${reg.step}" is shared by ${sharers} entries; no one gate owns it` };
  }
  reg.run = pkgRun;
  let src: string;
  try {
    src = readFile(reg.file);
  } catch {
    return { error: `${reg.file} could not be read` };
  }
  if (strip) src = stripHeader(src);
  const needs = inferredNeeds(src);
  const placed = placeGate(caps, needs);
  const pinLane = !('lane' in placed) || placed.lane !== reg.job;
  const next = insertHeader(reg.file, src, headerLines(reg, needs, pinLane, id));
  if (typeof next !== 'string') return { error: `${reg.file}: ${next.error}` };
  const rb = bind(reg.file, next);
  const runOk = reg.run === '' || rb?.run === reg.run;
  if (rb === null || rb.id !== id || rb.step !== reg.step || !runOk) {
    const got = rb === null ? 'nothing' : `${rb.id} / "${rb.step}" / ${rb.run}`;
    return { error: `${reg.file}: header re-derives ${got}, not ${id} / "${reg.step}"` };
  }
  // THE WRITE MODE NOW RUNS THE VERIFIER'S OWN CHECK. Everything above proves the header re-derives the right id, step and run; NONE of it proved the lane can provide what the file needs, which is precisely what the verifier asserts a moment later. So --extract happily wrote headers that gate-bind then rejected, and on 2026-09-06 two of them reddened check:ci-gate-bind mid-wave
  // and had to be stripped by hand. A tool whose write mode does not run its own verify is how a green plan produces a red tree.
  //
  // Refusing HERE turns that into a named refusal the caller can act on, which is the difference between "this gate cannot be declared, and here is why" and a broken tree someone else has to diagnose. The two known causes are a genuine lane mismatch (check-editorconfig.sh needs submodules its lane does not check out) and a false positive in inferredNeeds (its npx probe has no
  // command position check, so it matches a parameter expansion). Both deserve a refusal rather than a write.
  const extractLane = caps.get(reg.job);
  if (extractLane === undefined) {
    return { error: `${reg.file}: lane '${reg.job}' is not a job of ${WORKFLOW}` };
  }
  if (!satisfies(extractLane, needs)) {
    return {
      error:
        `${reg.file}: lane '${reg.job}' does not provide all of ` +
        `${JSON.stringify(needs)}, so a header here would not bind. ` +
        'Either the lane genuinely lacks it, or inferredNeeds read a mention as an invocation.',
    };
  }
  return { file: reg.file, next, step: reg.step, job: reg.job };
}

/** Every gate id the manifest declares, in file order. */
export const manifestIds = (manifestText: string): string[] => [
  ...new Set((manifestText.match(/id: '([^']+)'/g) ?? []).map((m) => m.slice(5, -1))),
];

/** The paths this gate reads, so `--extract` can refuse to write outside them.
 *
 * `.ci/rediacc_ci` ADDED 2026-09-06, and the reason is the failure it prevents rather than
 * the convenience it buys. A gate file outside these prefixes can carry a perfectly
 * well-formed `---- gate ----` header and this binder will neither register it nor report it
 * as unregistered: it is INVISIBLE, which is strictly worse than unregistered, because the
 * absence is what nothing announces. The Python package landed its own test-runner gate and
 * that gate would have been exactly that. Widening the scan is the fix; the alternative was a
 * shim under `.ci/scripts/quality` existing only to satisfy an enumeration.
 */
export const inScope = (f: string): boolean =>
  /^(\.ci\/scripts|\.ci\/rediacc_ci|scripts)\//.test(f) && SUBJECT.test(f) && !NOT_SUBJECT.test(f);

/** Every declared gate: its path, its header, and what convention derives from them. */
export interface Bound {
  file: string;
  id: string;
  run: string;
  /**
   * Which of the four shapes. ONLY `step` is emitted into a gate-bind region; the other
   * three declare, bind and are checked, and the binder writes no workflow step for them.
   */
  kind: GateKind;
  /** The step it owns (`step`) or rides (`battery`). Absent for `test` and `local-only`. */
  step?: string;
  /** `false` when the gate owns a HAND-WRITTEN step a region must never take over. */
  emit?: boolean;
  needs: string[];
  lane?: string;
  /** Step-level `env:`, declared as `env-<KEY>:` lines in the gate header. */
  env?: Record<string, string>;
  /** An extra condition ANDed onto the standard guard. Never replaces it. */
  when?: string;
}

/** A gate a region actually writes: kind `step`, and therefore carrying one. */
export type Emitting = Bound & { kind: 'step'; step: string };

/**
 * Does this gate own a workflow step of its own, i.e. does a region emit it?
 *
 * A type guard rather than a predicate so `emitStep` cannot be reached with a gate that
 * has no step to emit. The parser already refuses that combination; this makes the
 * refusal structural instead of a second thing to remember.
 */
export const emits = (b: Bound): b is Emitting =>
  b.kind === 'step' && b.step !== undefined && b.emit !== false;

export function bind(file: string, source: string): Bound | null {
  const h = parseGateHeader(source);
  if (h === null) return null;
  // The union is the safe default: an author who forgets a need is corrected by the
  // inference. `needs-not` is the ONE way back out, and it costs a `blocker:` reason
  // (enforced in analyzeGateHeader), because the inference reads string literals and a
  // control's own description routinely names a tool it does not run. Measured
  // 2026-09-07: `ctl.check("TOOLING: an absent npx yields 127, ...")` in account_portal.py and a selftest description in check_checkout_cone.py both infer `node` for pure-Python gates. Tightening the pattern instead was REJECTED on measurement: 24 files would lose the inference and at least one of them, test_gate_policy_path.py, really does execute node_modules/.bin/tsx.
  const denied = new Set(h.needsNot);
  const needs = [...new Set([...h.needs, ...inferredNeeds(source)])]
    .filter((n) => !denied.has(n))
    .sort();
  return {
    file,
    id: h.id ?? derivedId(file),
    run: h.run ?? derivedRun(file, h.selftest === true),
    kind: h.kind,
    ...(h.step === undefined ? {} : { step: h.step }),
    ...(h.emit === false ? { emit: false } : {}),
    needs,
    ...(h.lane === undefined ? {} : { lane: h.lane }),
    // CARRIED FROM THE HEADER, and the omission of these two lines is what a real-tree plant caught after twelve selftest controls had all passed: `emitStep` handled env and `when` correctly, `Bound` declared them, and NOTHING copied them across, so a gate declaring `env-PROBE_TOKEN` bound to a step with no env and `gate-bind --dry-run` reported `already matches`. A selftest that
    // calls `emitStep` directly cannot see this, which is exactly the specialist's rule about a green that only proves the helper functions work.
    ...(h.env === undefined ? {} : { env: h.env }),
    ...(h.when === undefined ? {} : { when: h.when }),
  };
}

/** Does the workflow contain this step name, in this job? */
/**
 * Is the lane's `# >>> gate-bind` region placed AFTER that lane's `- id: setup` step?
 *
 * Every emitted step guards on `steps.setup.outcome == 'success'`. A region placed above
 * that step references a step that has not run: the expression evaluates empty, every
 * gate in the region SKIPS, and the job reports green having run none of them. That is
 * the worst shape a CI change can take, and it is invisible in a diff -- the steps are
 * all there, correctly written, in the wrong place.
 *
 * Placed once per lane by hand, so checked once per lane here.
 */
/**
 * Does this lane have an `- id: setup` step, i.e. may a region be emitted into it at all?
 *
 * INVARIANT 11, mechanised. Every emitted step guards on
 * `steps.setup.outcome == 'success'`, so a region in a lane with no such step emits gates
 * whose guard evaluates empty: they all SKIP and the job reports green having run none.
 * `quality-branch` and `quality-submodule-branches` are deliberately setup-less -- they
 * need `fetch-depth: 0` and the PR head ref -- so gates pinned there are hand-registered
 * by construction, not by omission.
 *
 * Before this existed, ONE such gate (check_plan_boxes.py, pinned to quality-branch) made
 * `--write` refuse for the entire repository, with the advice "place one by hand" that
 * invariant 11 forbids following. A correctly-placed gate must not disable the emitter.
 */
export function laneCanEmit(workflow: string, job: string): boolean {
  const lines = workflow.split('\n');
  const j = lines.findIndex((l) => /^ {2}[A-Za-z0-9_-]+:\s*$/.test(l) && l.trim() === `${job}:`);
  if (j === -1) return false;
  const nextJob = lines.findIndex((l, i) => i > j && /^ {2}[A-Za-z0-9_-]+:\s*$/.test(l));
  const end = nextJob === -1 ? lines.length : nextJob;
  return lines.slice(j, end).some((l) => l.trim() === '- id: setup');
}

export function regionAfterSetup(workflow: string, job: string): boolean {
  const lines = workflow.split('\n');
  const j = lines.findIndex((l) => l.trim() === `${job}:`);
  if (j === -1) return true;
  const nextJob = lines.findIndex((l, i) => i > j && /^  [a-z][a-z0-9-]*:$/.test(l));
  const end = nextJob === -1 ? lines.length : nextJob;
  const setup = lines.findIndex((l, i) => i > j && i < end && l.trim() === '- id: setup');
  const region = lines.findIndex(
    (l, i) => i > j && i < end && l.trim().startsWith('# >>> gate-bind')
  );
  if (setup === -1 || region === -1) return true;
  return region > setup;
}

/**
 * How many times does this step name appear in this job?
 *
 * A gate that becomes DECLARED gets its step emitted inside the lane's region -- but its
 * original hand-written step is still sitting further down the same job. `stepInJob` only
 * asks whether the step EXISTS, so both copies pass it, and the gate then runs twice per
 * CI job: silent, green, and paid for on every run. With 174 gates extractable in one
 * command, this is the difference between a migration and 174 duplicated steps.
 */
export function stepCountInJob(workflow: string, job: string, step: string): number {
  const lines = workflow.split('\n');
  const j = lines.findIndex((l) => l.trim() === `${job}:`);
  if (j === -1) return 0;
  const nextJob = lines.findIndex((l, i) => i > j && /^  [a-z][a-z0-9-]*:$/.test(l));
  const end = nextJob === -1 ? lines.length : nextJob;
  return lines.slice(j, end).filter((l) => l.trim() === `- name: ${step}`).length;
}

export function stepInJob(workflow: string, job: string, step: string): boolean {
  const lines = workflow.split('\n');
  let cur = '';
  for (const raw of lines) {
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) {
      cur = m[1];
      continue;
    }
    if (cur !== job) continue;
    const name = /^\s+-?\s*name:\s*(.+?)\s*$/.exec(raw);
    if (name && name[1].replace(/^["']|["']$/g, '') === step) return true;
  }
  return false;
}

/**
 * Every job of the workflow carrying a step with this name.
 *
 * A `battery` gate does not CHOOSE its lane -- it rides a hand-written step, and that
 * step is where it runs whatever its own needs would have preferred. Placement must
 * therefore be read out of the workflow rather than computed from `needs`, or the lane
 * check below judges a lane the gate never runs in. Returns every match so a step name
 * duplicated across jobs is reported instead of silently resolving to the first.
 */
export function jobsWithStep(workflow: string, step: string): string[] {
  const out: string[] = [];
  let cur = '';
  for (const raw of workflow.split('\n')) {
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) {
      cur = m[1];
      continue;
    }
    const name = /^\s+-?\s*name:\s*(.+?)\s*$/.exec(raw);
    if (name && name[1].replace(/^["']|["']$/g, '') === step && !out.includes(cur)) {
      out.push(cur);
    }
  }
  return out;
}

const OPEN_RE = /^\s*# >>> gate-bind\b/;
const CLOSE_RE = /^\s*# <<< gate-bind\s*$/;

/**
 * The emitted step for one gate, in the shape every hand-written gate step already has.
 *
 * The `if:` guard is not optional decoration: 189 of the 258 steps in ci-quality.yml
 * carry it, and a gate step without it runs after its own job's setup has failed and
 * reports a confusing second failure instead of the real one.
 */
/**
 * A DECLARED NEED IS ACQUIRED, not merely used to pick a lane.
 *
 * check_git_history_depth.py declares `needs: python-yaml`, and placement duly sent it to
 * quality-static -- the only lane that installs PyYAML. But that lane installs it INSIDE
 * each step's own `run` block, and the gate-bind region sits above all of them, so the
 * emitted step ran before any install existed. check:ci-python-gate-deps caught it: a
 * script importing yaml in a job whose earlier steps never name it dies with
 * ModuleNotFoundError on a clean runner and passes on any machine that happens to have
 * the module. The lane answers WHERE; this answers WITH WHAT.
 */
const ACQUIRE: Record<string, string[]> = {
  'python-yaml': [
    '          python3 -m pip install --user --disable-pip-version-check "PyYAML==${PYYAML_VERSION}"',
    '          python3 -c "import yaml; print(\'PyYAML\', yaml.__version__)"',
  ],
};

/**
 * The step whose outcome guards an emitted step, read from the region's own marker.
 *
 * `steps.setup.outcome` WAS HARDCODED, and quality-www-build is where that breaks. All
 * seven of its gates guard on `steps.build-www.outcome`, not setup, because they read the
 * `dist/` that the `- id: build-www` step produces. Emitting them with the setup guard
 * would silently re-point every one: they would run when the BUILD failed, against a
 * missing dist/, and check-landmarks.ts:89 refuses outright without it. A mass false red
 * at best, and at worst a gate that finds nothing and says so cheerfully.
 *
 * The guard is a PER-LANE FACT, like the prerequisite placement and the hold-outs before
 * it, so it is declared where the lane is: `# >>> gate-bind guard: build-www`. Absent, it
 * is `setup`, which is what every region-bearing lane but `quality-www-build` wants.
 */
const GUARD_RE = /^\s*# >>> gate-bind\b[^\n]*\bguard:\s*([A-Za-z0-9_-]+)/;

export function regionGuard(markerLine: string): string {
  return GUARD_RE.exec(markerLine)?.[1] ?? 'setup';
}

/**
 * Which shard each gate of a sharded lane belongs to, or null for an unsharded lane.
 *
 * WHY THE DRIVER COMPUTES THIS AND A HEADER CANNOT. A1 made `when` a header field, and a
 * shard conjunct is the one `when` an author must never write: it depends on how many legs
 * the lane has and on how `shardPlan` balanced them, both of which change when any OTHER
 * gate is added. A hand-written `matrix.shard == 3` is stale the moment the lane grows,
 * and stale in the silent direction -- the gate simply stops running, on a leg that still
 * reports green.
 *
 * WITHOUT THIS, A MATRIX MAKES CI SLOWER, NOT FASTER. Four legs each running all 166 of
 * `quality-security`'s steps is four times the work for the same coverage. The conjunct is
 * what turns a matrix into a split.
 *
 * The plan comes from the SAME `shardPlan` over the SAME `SHARD_COUNTS` that
 * `check:ci-quality-complete` re-runs, so the emitter and the aggregator cannot disagree
 * about which leg holds what. A lane whose plan is REFUSED yields null rather than a
 * partial assignment: emitting some steps with a conjunct and some without would leave the
 * unconjuncted ones running on every leg, which is the failure this exists to prevent.
 *
 * T-SCHED B2 D2. `legs` alone hid the `quality-security` mistake: a lock entry whose
 * `ci.step` is not one of `emitting`'s steps gets a leg from the plan and NO conjunct in
 * the file, so it runs on every leg while the plan believes it ran once. `replicated`
 * names exactly those ids, and the caller both prints them (so a quiet exemption cannot
 * become the norm) and refuses the lane outright once their share of the lane exceeds
 * `ceilings[job]` -- a null return here means "not asked to shard this lane at all" (job
 * absent from `counts`); `{ error }` means "asked, and refused".
 *
 * `counts`/`ceilings` are PARAMETERS, not `SHARD_COUNTS`/`SHARD_REPLICATED_MAX` read
 * directly, so this function is a pure function of its arguments the way `shardPlan`
 * already is -- the one real call site passes the real constants, and a control can pass
 * fixture data instead. Closing over the module consts was exactly why this function had
 * "NO selftest control ... exercises the no-shard path only", per this box's own note.
 */
export function shardAssignment(
  job: string,
  lock: readonly Parameters<typeof shardPlan>[0][number][],
  caps: Parameters<typeof shardPlan>[1],
  emitting: readonly Emitting[],
  counts: Readonly<Record<string, number>> = SHARD_COUNTS,
  ceilings: Readonly<Record<string, number>> = SHARD_REPLICATED_MAX
): { legs: Map<string, number>; replicated: string[] } | { error: string } | null {
  const want = counts[job];
  if (want === undefined) return null;
  const plan = shardPlan(lock, caps, { [job]: want });
  if ('error' in plan) return { error: plan.error };
  const legs = new Map<string, number>();
  for (const lane of plan.lanes) {
    for (const shard of lane.shards) {
      for (const id of shard.ids) legs.set(id, shard.index);
    }
  }
  const emittedSteps = new Set(emitting.map((e) => e.step));
  const laneEntries = lock.filter((e) => e.ci.kind === 'step' && e.ci.job === job);
  // `?? ''` for a step-less "step kind" entry: the type does not forbid it structurally (`ShardInput.ci.step` is optional), and an empty string never matches a real emitted step name, so such an entry correctly counts as replicated rather than type-erroring.
  const replicated = laneEntries.filter((e) => !emittedSteps.has(e.ci.step ?? '')).map((e) => e.id);
  const ceiling = ceilings[job];
  if (ceiling === undefined) {
    return {
      error:
        `lane ${job} is in SHARD_COUNTS with no matching SHARD_REPLICATED_MAX entry. ` +
        'A sharded lane needs a declared ceiling on how much of it can run replicated on ' +
        'every leg, or nothing catches the next quality-security-shaped mistake.',
    };
  }
  const share = laneEntries.length === 0 ? 0 : replicated.length / laneEntries.length;
  if (share > ceiling) {
    return {
      error:
        `lane ${job}: ${replicated.length} of ${laneEntries.length} entries ` +
        `(${(share * 100).toFixed(0)}%) run OUTSIDE any emitted region, so no conjunct can ` +
        `reach them and they would run on every leg -- a matrix that multiplies the ` +
        `dominant work is slower than no matrix. Ceiling for ${job} is ` +
        `${(ceiling * 100).toFixed(0)}%. Give the replicated steps a declaration so ` +
        'gate-bind can emit them, or drop the lane from SHARD_COUNTS.',
    };
  }
  return { legs, replicated };
}

/**
 * T-SCHED B2 D4, first clause. The deterministic id a conjuncted step needs so its own
 * receipt step (not yet built -- see the D4 note at this function's call site) can read
 * `steps.<id>.outcome` and know whether it actually ran. `gate_` prefix because a raw
 * job/step id cannot start with a digit or contain `:`/`-`, both of which every gate id
 * in this lock carries (`check:ci-foo`).
 */
export function gateStepId(id: string): string {
  return `gate_${id.replace(/[:-]/g, '_')}`;
}

/**
 * T-SCHED B2 D4, second clause. A YAML single-quoted scalar holding the JSON array,
 * emitted RAW into `env:` the way every other env value already is (`emitStep` does no
 * quoting of its own) -- single quotes because GitHub Actions env values are read as
 * plain strings regardless, and a bare `[...]` would otherwise parse as a YAML flow
 * sequence rather than the JSON text a later `JSON.parse` needs literally. YAML's own
 * escape for an embedded `'` inside a single-quoted scalar is doubling it, so ids are
 * defensively escaped that way even though no lock id in this repo contains one today.
 *
 * CORRECTION, found while designing the receipt step this was meant to feed: a step's
 * `env:` is process-local to that step and is NOT part of the `steps` context --
 * `toJSON(steps)` and every `steps.<id>.X` reference in this whole repository (checked:
 * every existing cross-step data pass in .github/workflows/*.yml uses `outputs`, via
 * `$GITHUB_OUTPUT`, never `env`) exposes only `outputs`, `outcome` and `conclusion`. A
 * later receipt step CANNOT read an earlier step's `GATE_LOCK_IDS` this way, so this
 * value is NOT what the eventual receipt step's counter reads -- see `jobLockIdMap`
 * below for the map that actually is. `GATE_LOCK_IDS` is kept for its own, narrower
 * value: a human reading the emitted YAML can see which lock id(s) a given step
 * represents without cross-referencing the lock, the same reason `id:` itself is
 * useful to a reader even before any receipt step exists to consume it.
 */
export function lockIdsEnvValue(ids: readonly string[]): string {
  return `'${JSON.stringify(ids).replace(/'/g, "''")}'`;
}

/**
 * T-SCHED B2 D4, corrected. What the eventual receipt step actually needs: the WHOLE
 * job's step-id -> lock-ids map, known entirely at COMPILE TIME (gate-bind already has
 * every conjuncted gate's id when it writes the region), so it can be embedded ONCE on
 * the receipt step's own `env:` rather than distributed across steps a later step
 * cannot read. `steps.<id>.outcome` (native to the `steps` context, unlike `env`) is
 * then the only RUNTIME fact the receipt script needs per step.
 *
 * ONE ENTRY PER GATE, NOT PER STEP, and that is a known, narrower scope than "one per
 * STEP after the D1 merge" this box's own text asks for. `rewriteRegions` itself does
 * not collapse two auto-emitted gates sharing one `.step` name into one emitted block
 * today -- keying `gateStepId` on `b.id` here matches what it actually emits, one block
 * per gate. That collapse is a separate, currently non-live gap (no header-declared
 * gate shares a step with another today; the live example, `Lint`, is hand-registered
 * via the manifest and never reaches `byLane` at all) and is not this function's or
 * D4's to fix -- recorded here rather than silently assumed away.
 */
export function jobLockIdMap(entries: readonly Emitting[]): Record<string, string[]> {
  const map: Record<string, string[]> = {};
  for (const b of entries) map[gateStepId(b.id)] = [b.id];
  return map;
}

/** Same YAML-single-quote-scalar shape as `lockIdsEnvValue`, generalised to any JSON value. */
function jsonEnvValue(value: unknown): string {
  return `'${JSON.stringify(value).replace(/'/g, "''")}'`;
}

/**
 * T-SCHED B2 D4, final clause. The step every sharded job's region ends with.
 * `if: always()` because Finding 2's whole point is catching an ALL-SKIPPED leg, which
 * needs a receipt written even then -- a driver-emitted literal would report a full leg
 * regardless, which is the exact vacuity this mechanism exists to defend against.
 *
 * The script is a heredoc to a real file, not a `node -e "..."` one-liner: GHA does its
 * OWN `${{ }}` substitution as a text replacement over the entire `run:` block BEFORE a
 * shell ever sees it, so any JS in the script must never contain that literal substring
 * (this one uses plain `process.env.X` reads and string concatenation, never a template
 * literal, specifically to keep the two `${` grammars from colliding). The heredoc
 * delimiter is single-quoted (`<<'GATERECEIPT'`) so bash does not interpolate the
 * script body either -- only GHA's own substitution touches this text, and only where
 * `${{ }}` literally appears in the `env:` values below, never inside the heredoc.
 *
 * Counts in the aggregator's currency, LOCK IDS
 * (`scripts/gates/check-quality-complete.ts:226` compares `gates` against
 * `declaredShard.ids.length`), crossing `jobLockIdMap` (built at compile time, since
 * gate-bind already knows every conjuncted gate's id when it writes the region) against
 * `steps.<id>.outcome` (native to the `steps` context, read via `toJSON(steps)` --
 * the only thing this script needs at runtime; see `lockIdsEnvValue`'s docstring for why
 * a step's OWN `env:` cannot serve this instead).
 */
export function emitReceiptStep(job: string, of: number, entries: readonly Emitting[]): string[] {
  const receiptFile = `/tmp/gate-receipt-${job}.json`;
  return [
    '      - name: Write shard receipt',
    '        if: always()',
    '        env:',
    `          GATE_STEP_LOCK_MAP: ${jsonEnvValue(jobLockIdMap(entries))}`,
    '          STEPS_JSON: ${{ toJSON(steps) }}',
    '          SHARD_INDEX: ${{ matrix.shard }}',
    `          SHARD_OF: '${of}'`,
    '          JOB_STATUS: ${{ job.status }}',
    `          RECEIPT_LANE: '${job}'`,
    `          RECEIPT_PATH: '${receiptFile}'`,
    '        run: |',
    "          cat > /tmp/gate-receipt.js <<'GATERECEIPT'",
    '          const stepsCtx = JSON.parse(process.env.STEPS_JSON);',
    '          const map = JSON.parse(process.env.GATE_STEP_LOCK_MAP);',
    '          let gates = 0;',
    '          for (const stepId of Object.keys(map)) {',
    '            const s = stepsCtx[stepId];',
    "            if (s && s.outcome !== 'skipped') gates += map[stepId].length;",
    '          }',
    '          const receipt = {',
    '            lane: process.env.RECEIPT_LANE,',
    '            index: Number(process.env.SHARD_INDEX),',
    '            of: Number(process.env.SHARD_OF),',
    '            result: process.env.JOB_STATUS,',
    '            gates: gates,',
    '          };',
    "          require('fs').writeFileSync(process.env.RECEIPT_PATH, JSON.stringify(receipt));",
    '          GATERECEIPT',
    '          node /tmp/gate-receipt.js',
    '      - name: Upload shard receipt',
    '        if: always()',
    '        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1',
    '        with:',
    `          name: quality-shard-\${{ matrix.shard }}`,
    `          path: ${receiptFile}`,
    '          retention-days: 7',
    '          if-no-files-found: error',
  ];
}

/**
 * Binaries that live in `node_modules/.bin` and NOWHERE ELSE.
 *
 * `npm run` puts that directory on PATH; a workflow `run:` does not. A step
 * emitted with the raw command therefore dies `command not found`, exit 127,
 * BEFORE the gate prints anything -- and on a developer machine with a global
 * install it works, so the defect ships.
 *
 * `tsx` was the original member and was special-cased inline. `knip` is the
 * second, added 2026-09-15 after it cost a real red: `gate-bind --write` in
 * bfb8630dd re-emitted `Unused exports (knip)` from its header's `run:`, which
 * reverted a fix (10b130a82) that had hand-edited the YAML to `npm run
 * lint:unused`. The hand edit could not survive, because the generator is the
 * source of truth and the generator did not know. Nothing caught it for two
 * runs: the watchdog kept cancelling `Quality / Code` for an unrelated failure
 * in `Quality / Static`, so the step never got far enough to report.
 *
 * The HEADER still declares the real command, because `gate-bind` requires a
 * header's `run:` to equal its package.json script -- that equality is what
 * makes `npm run <id>` and the raw command the same thing, which is what makes
 * this substitution safe rather than a second definition of the gate.
 */
export const LOCAL_BIN_COMMANDS = ['tsx', 'knip'];

/** True when `run` invokes a node_modules/.bin binary as a bare command word. */
export function usesLocalBin(run: string): boolean {
  return LOCAL_BIN_COMMANDS.some((bin) =>
    new RegExp(`(^|&&\\s*|\\|\\|\\s*|;\\s*|\\|\\s*)${bin}(\\s|$)`).test(run)
  );
}

export function emitStep(b: Emitting, guard = 'setup', stepId?: string): string[] {
  const cmd = usesLocalBin(b.run) ? `npm run ${b.id}` : b.run;
  const acquire = b.needs.flatMap((n) => ACQUIRE[n] ?? []);
  // `when` IS ANDED ON, NEVER SUBSTITUTED. The standard guard is what stops a gate running after setup failed; a field that could replace it would let a gate opt out of the ordering contract, which is invariant 11 through a side door. Parenthesised so a `when` containing `||` cannot bind looser than the `&&` and swallow the guard -- `a && b || c` is `(a && b) || c`, which would
  // run the step on a failed setup.
  const cond =
    `!cancelled() && steps.${guard}.outcome == 'success'` + (b.when ? ` && (${b.when})` : '');
  // `id:` ONLY when sharded (`stepId` passed), so every unsharded step's YAML stays byte-identical to before D4 -- an added id on a step nothing reads it from is a diff with no reader, which is how a generator trains people to stop reading its diffs at all.
  const head = [
    `      - name: ${b.step}`,
    ...(stepId !== undefined ? [`        id: ${stepId}`] : []),
    `        if: \${{ ${cond} }}`,
  ];
  // ENV BEFORE RUN, and sorted, because the map is emitted from an object whose key order is otherwise insertion order -- a generator whose output depends on parse order is a generator that produces spurious diffs and breaks the idempotency control below.
  const env =
    b.env && Object.keys(b.env).length > 0
      ? [
          '        env:',
          ...Object.keys(b.env)
            .sort()
            .map((k) => `          ${k}: ${(b.env as Record<string, string>)[k]}`),
        ]
      : [];
  if (acquire.length === 0) return [...head, ...env, `        run: ${cmd}`];
  return [...head, ...env, '        run: |', ...acquire, `          ${cmd}`];
}

/**
 * Replace each lane's gate-bind region with the steps its gates derive to.
 *
 * REGION-SCOPED, and the prose inside the opening marker is PRESERVED: the marker block
 * explains itself to whoever opens the file, and a generator that ate its own
 * explanation every run would train people to stop reading it.
 */
/**
 * Rewrite each lane's region from the declared gates.
 *
 * `dropped` NAMES EVERY STEP THE REWRITE REMOVED, and that return value is not
 * bookkeeping. On 2026-09-05 a `--write` here deleted four hand-added steps that a peer
 * had put INSIDE the quality-code region -- worklist-event-builders,
 * worklist-path-resolution, fixture-event-timestamps, gate-cwd-independence -- and
 * reported only "rewrote 3 region(s)". Their gates stopped running in CI and the only
 * symptom was check:ci-parity, one gate later, saying the manifest pointed at steps that
 * no longer existed. A destructive rewrite that does not say what it destroyed is how a
 * shared workflow loses a step silently.
 *
 * The region's own comment does warn that a hand edit inside it is overwritten. That
 * makes the deletion correct and the SILENCE the defect.
 */
/**
 * Split `dropped` into the two refusals the strip guard makes, and the silence.
 *
 * EXPORTED SO A CONTROL CAN DRIVE IT. This logic lived inline in `main`, where nothing
 * could reach it -- a refusal no test exercises is a refusal nobody has watched fire, and
 * this file's own selftest is the instrument that would have caught the gap it closes.
 *
 * `claimed` is a REGRESSION: the manifest still names the step, so removing it stops that
 * gate running in CI. `unclaimed` is merely UNEXPLAINED: it may be legitimate cleanup, but
 * a step carries `env:`, `if:`, `with:` and secrets that no gate reads, so dropping one is
 * invisible. The receipt for that, measured: strip `DOCKERHUB_TOKEN` from
 * `.github/workflows/ci-quality.yml:1159` in a scratch copy, run the whole battery, and
 * nothing reds. Hence refuse both, and keep them separate so the message can say which.
 */
export function classifyDrops(
  dropped: string[],
  emitted: Set<string>,
  allowDrop: Set<string>,
  manifest: string
): { claimed: string[]; unclaimed: string[] } {
  const stepOf = (d: string) => d.slice(d.indexOf(': ') + 2);
  const live = dropped.filter((d) => !emitted.has(d) && !allowDrop.has(stepOf(d)));
  return {
    claimed: live.filter((d) => manifest.includes(`step: '${stepOf(d)}'`)),
    unclaimed: live.filter((d) => !manifest.includes(`step: '${stepOf(d)}'`)),
  };
}

/**
 * `only` NAMES THE LANES THIS CALL MAY REWRITE. Undefined means all of them.
 *
 * A region belonging to a lane outside `only` is copied through UNTOUCHED, not rewritten
 * from an empty list. That distinction is the whole of `--lane`: the first version simply
 * narrowed the input map, which made every other region emit ZERO steps, and the
 * claimed-step refusal below correctly reported four steps about to be dropped that the
 * manifest still points at. Skipping and emptying are one word apart in the code and
 * opposite in the file.
 */
export function rewriteRegions(
  workflow: string,
  byLane: Map<string, Emitting[]>,
  only?: ReadonlySet<string>,
  /**
   * Per-lane gate -> shard-leg assignment, from `shardAssignment`. OPTIONAL and defaulting
   * to none, so every existing caller and both selftest controls keep emitting exactly the
   * steps they emitted before: an unsharded lane must not gain a conjunct, and no lane is
   * in `SHARD_COUNTS` today.
   */
  shards?: ReadonlyMap<string, ReadonlyMap<string, number>>
): { text: string; lanes: string[]; dropped: string[] } {
  const lines = workflow.split('\n');
  const out: string[] = [];
  const touched: string[] = [];
  const dropped: string[] = [];
  let job = '';
  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (m) job = m[1];
    if (!OPEN_RE.test(raw)) {
      out.push(raw);
      i += 1;
      continue;
    }
    // A LANE OUT OF SCOPE IS COPIED THROUGH, body and all.
    if (only !== undefined && !only.has(job)) {
      out.push(raw);
      i += 1;
      while (i < lines.length && !CLOSE_RE.test(lines[i])) {
        out.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) {
        out.push(lines[i]);
        i += 1;
      }
      continue;
    }
    // keep the marker and its explanatory comment lines, drop the emitted steps
    out.push(raw);
    i += 1;
    while (i < lines.length && /^\s*#/.test(lines[i]) && !CLOSE_RE.test(lines[i])) {
      out.push(lines[i]);
      i += 1;
    }
    const guard = regionGuard(raw);
    // THE SHARD CONJUNCT IS ANDED ONTO ANY HEADER `when`, NEVER SUBSTITUTED FOR IT, and the header half is parenthesised for the reason `emitStep` documents: `a || b && c` binds the wrong way and would put a gate on every leg.
    const shardOf = shards?.get(job) ?? null;
    const shardedEntries: Emitting[] = [];
    for (const b of (byLane.get(job) ?? []).slice().sort((a, z) => a.step.localeCompare(z.step))) {
      const leg = shardOf?.get(b.id);
      const step =
        leg === undefined
          ? b
          : {
              ...b,
              when: b.when ? `(${b.when}) && matrix.shard == ${leg}` : `matrix.shard == ${leg}`,
              // T-SCHED B2 D4, second clause. The eventual receipt step counts in LOCK IDS (`check-quality-complete.ts:226` compares against `declaredShard.ids.length`), but it can only see `steps.<id>.outcome`, one outcome per EMITTED STEP -- which is coarser than one per lock id the moment two ids ever share a step (D1's whole reason for merging them). This map is what lets the
              // receipt step translate "this step ran" back into "these lock ids ran", correct today (always exactly `[b.id]`, since no auto-emitted gate currently shares a step with another) and correct if that ever changes, without the receipt script itself needing to know which case it is in.
              env: { ...b.env, GATE_LOCK_IDS: lockIdsEnvValue([b.id]) },
            };
      if (leg !== undefined) shardedEntries.push(b);
      out.push(...emitStep(step, guard, leg === undefined ? undefined : gateStepId(b.id)));
    }
    // T-SCHED B2 D4, final clause. One receipt step per sharded job, emitted from the SAME `shardOf` this region already used to conjunct every gate above it -- `of` is the highest leg number `shardPlan` assigned, which is correct because `shardPlan`'s bin-packer always fills legs 1..N with none left empty (its own acceptance clause 3, "no shard is empty").
    if (shardOf !== null && shardOf.size > 0) {
      const of = Math.max(...shardOf.values());
      out.push(...emitReceiptStep(job, of, shardedEntries));
    }
    while (i < lines.length && !CLOSE_RE.test(lines[i])) {
      const step = /^\s*-\s*name:\s*(.+?)\s*$/.exec(lines[i]);
      if (step) dropped.push(`${job}: ${step[1]}`);
      i += 1;
    }
    if (i < lines.length) {
      out.push(lines[i]);
      i += 1;
    }
    touched.push(job);
  }
  return { text: out.join('\n'), lanes: touched, dropped };
}

/**
 * T-SCHED B2 D3. A `matrix.shard` conjunct means nothing without a real `strategy:`
 * block on the job -- Finding 2's vacuity: with no `strategy.matrix`, GitHub evaluates
 * `matrix.shard` as `null`, so `matrix.shard == 1` is FALSE and every conjuncted step
 * SKIPS, reporting a full leg's worth of green having run nothing.
 *
 * NOT `# >>> gate-bind ...`. The plan box that specified this drafted the marker as
 * `# >>> gate-bind strategy`, which `OPEN_RE` above (`/^\s*# >>> gate-bind\b/`, a bare
 * word boundary with no `$`) MATCHES, while its own close line, `# <<< gate-bind
 * strategy`, does NOT match `CLOSE_RE` (`/^\s*# <<< gate-bind\s*$/`, which requires
 * nothing after "gate-bind"). `rewriteRegions` above would misdetect the strategy
 * open as an ordinary region open and scan forward for a close line that never
 * matches -- silently swallowing the rest of the job block into "region body" until
 * the next real `# <<< gate-bind` from an unrelated region. Proved with the literal
 * strings against both regexes before choosing this marker instead of that one.
 *
 * A CHECK, NOT A WRITER, on purpose -- this is the one place `--write` REFUSES
 * rather than regenerates. Every other region in this file is safe to auto-rewrite
 * because it only ever changes a `run:`/`if:`/`env:` line inside a job that already
 * exists in the shape it exists in. A `strategy:` block changes what the job IS: it
 * turns one execution into N, and the box's own note names a real external
 * consequence -- if `Quality / Code` is a required branch-protection check, its
 * rendered name becomes `Quality / Code (1)`, and that rename is the operator's to
 * approve, not this function's to make silently. So a lane entering `SHARD_COUNTS`
 * or leaving it is surfaced as a refusal naming the exact YAML, never applied.
 */
export function rewriteStrategyRegions(
  workflow: string,
  counts: Readonly<Record<string, number>>
): string[] {
  const lines = workflow.split('\n');
  const findings: string[] = [];
  const wanted = new Set(Object.keys(counts));
  const seen = new Set<string>();
  let job = '';
  let region: { job: string; shards: number[] } | null = null;
  for (const raw of lines) {
    const jm = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(raw);
    if (jm) job = jm[1] as string;
    const openM = /^( {4})# >>> shard-strategy\b/.exec(raw);
    if (openM) region = { job, shards: [] };
    if (region && /^\s*shard:\s*\[([^\]]*)\]\s*$/.test(raw)) {
      const nums = /^\s*shard:\s*\[([^\]]*)\]\s*$/.exec(raw)?.[1] ?? '';
      region.shards = nums
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
        .map(Number);
    }
    if (/^ {4}# <<< shard-strategy\s*$/.test(raw) && region) {
      seen.add(region.job);
      const want = counts[region.job];
      if (want === undefined) {
        findings.push(
          `job ${region.job} carries a shard-strategy region but is not in SHARD_COUNTS -- ` +
            'remove the region (a leftover from a lane that stopped sharding is a drain, not a no-op).'
        );
      } else {
        const expected = Array.from({ length: want }, (_, k) => k + 1);
        if (JSON.stringify(region.shards) !== JSON.stringify(expected)) {
          findings.push(
            `job ${region.job}'s shard-strategy region lists [${region.shards.join(', ')}] but ` +
              `SHARD_COUNTS[${region.job}] is ${want} -- expected [${expected.join(', ')}]. Repaste ` +
              'the block (this function refuses rather than rewrites a structural job change).'
          );
        }
      }
      region = null;
    }
  }
  for (const job2 of wanted) {
    if (seen.has(job2)) continue;
    const want = counts[job2] as number;
    const shardList = Array.from({ length: want }, (_, k) => k + 1).join(', ');
    findings.push(
      `job ${job2} is in SHARD_COUNTS (${want}) with no shard-strategy region. Paste, at the job's ` +
        "4-space indent, immediately before 'steps:':\n" +
        '    # >>> shard-strategy (generated; do not edit inside)\n' +
        '    strategy:\n' +
        '      fail-fast: false\n' +
        '      matrix:\n' +
        `        shard: [${shardList}]\n` +
        '    # <<< shard-strategy'
    );
  }
  return findings;
}

/** What the manifest already says about a hand-registered gate. */
export interface Registered {
  file: string;
  step: string;
  job: string;
  /** package.json's script body -- the real command. The manifest only holds `npm run <id>`. */
  run: string;
  /** The `//` prose above the entry. This IS the `why:`, so extraction loses nothing. */
  why: string[];
}

export function registered(manifest: string, id: string): Registered | { error: string } {
  // Padded so the FIRST entry in the file is bounded like every other one: without this
  // the backward search for `\n  {` finds nothing at offset 0 and the entry reads as
  // unbounded. Caught by this gate's own fixture, which is exactly that shape.
  const text = `\n${manifest}\n`;
  const at = text.indexOf(`id: '${id}'`);
  if (at === -1) return { error: `no manifest entry with id '${id}'` };
  const start = text.lastIndexOf('\n  {\n', at);
  const end = text.indexOf('\n  },\n', at);
  if (start === -1 || end === -1) return { error: `could not bound the entry for '${id}'` };
  const block = text.slice(start, end);
  // BOTH QUOTE STYLES. This accepted single quotes only, so an entry whose value CONTAINS an apostrophe -- and is therefore written with double quotes in the manifest -- read as absent. check:ci-cli-doc-coverage's step is "CLI docs stay in sync with their scripts' real flags", so field('step') returned '' and --extract reported "entry is missing leaves, ci.step or ci.job". The
  // entry was complete; the reader was not, and every other entry needing double quotes was silently un-extractable the same way.
  const field = (k: string): string =>
    new RegExp(`\\b${k}: '([^']*)'`).exec(block)?.[1] ??
    new RegExp(`\\b${k}: "([^"]*)"`).exec(block)?.[1] ??
    '';
  const file = /leaves: \[\s*'([^']+)'/.exec(block)?.[1] ?? '';
  // Only the prose ABOVE `id:`. A comment further down explains a later field.
  const head = block.slice(0, block.indexOf('id:'));
  const why = head
    .split('\n')
    .filter((l) => /^\s*\/\//.test(l))
    .map((l) => l.replace(/^\s*\/\/\s?/, '').trimEnd());
  const out: Registered = { file, step: field('step'), job: field('job'), run: '', why };
  if (out.file === '' || out.step === '' || out.job === '') {
    return { error: `entry '${id}' is missing leaves, ci.step or ci.job` };
  }
  return out;
}

/** The header body, unprefixed. The caller decides how each language carries a comment. */
export function headerLines(
  r: Registered,
  needs: string[],
  pinLane: boolean,
  id?: string
): string[] {
  const out = [
    '---- gate ----',
    `step: ${r.step}`,
    `needs: ${needs.length ? needs.join(', ') : 'none'}`,
  ];
  // `id:` is an OVERRIDE, emitted only where the path does not imply the registered id:
  // .ci/scripts/security/shfmt.sh derives check:ci-shfmt and is registered as
  // check:ci-shell-format. 308 of 378 ids need no override, and writing one into all of
  // them would turn a convention into 378 restatements of itself.
  if (id !== undefined && derivedId(r.file) !== id) out.push(`id: ${id}`);
  // `run:` likewise. Three registered shapes do not derive: `tsx X --selftest` alone,
  // `tsx X --selftest && tsx X`, and `tsx X && tsx <a different control file>`. The
  // second is `selftest: true`; the other two are genuinely per-gate, and inventing
  // derivation rules for them would encode five gates' habits as a convention.
  const wanted = r.run ?? '';
  // `selftest: true` IS ONLY MEANINGFUL FOR .ts, because derivedRun branches on the flag only there. For a .sh or .py gate derivedRun(f, true) equals derivedRun(f), so the first arm always matched and every such header asserted a `--selftest` leg. Measured 2026-09-06 on the file this repo's briefs cite as the model: check-npmrc.sh carried `selftest: true` while containing ZERO
  // occurrences of --selftest. Roughly 30 headers claimed a leg that does not exist. Inert for binding, and a declaration that lies is worse than a missing one, because the next reader trusts it.
  const selftestIsReal = r.file.endsWith('.ts');
  if (selftestIsReal && wanted !== '' && wanted === derivedRun(r.file, true)) {
    out.push('selftest: true');
  } else if (wanted !== '' && wanted !== derivedRun(r.file)) {
    out.push(`run: ${wanted}`);
  }
  if (pinLane) out.push(`lane: ${r.job}`);
  if (r.why.length > 0) {
    out.push(`why: ${r.why[0]}`);
    for (const line of r.why.slice(1)) out.push(`     ${line}`);
  }
  out.push('---- end gate ----');
  return out;
}

/**
 * Put the header where the file already keeps its prose, so extraction reads as
 * documentation rather than as a machine stamp: a Python module docstring, a shell
 * comment block under the shebang, a TypeScript block comment. Falls back to a
 * standalone line-comment block, which the parser accepts in every one of them.
 */
/**
 * Remove a declared header, so `--rebind` can re-emit one that matches a registration
 * that has since moved. Without it the only repair for a header written wrong is a hand
 * edit, which is the thing this tool exists to stop asking for.
 */
export function stripHeader(source: string): string {
  const lines = source.split('\n');
  const open = lines.findIndex((l) => /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$/.test(l));
  if (open === -1) return source;
  const close = lines.findIndex((l, i) => i > open && /-{2,}\s*end gate\s*-{2,}\s*$/.test(l));
  if (close === -1) return source;
  const rest = lines.slice(close + 1);
  // The blank line the emitter added after the block goes with it.
  if (rest[0] === '' || rest[0]?.trim() === '*') rest.shift();
  return [...lines.slice(0, open), ...rest].join('\n');
}

export function insertHeader(
  file: string,
  source: string,
  body: string[]
): string | { error: string } {
  if (parseGateHeader(source) !== null) return { error: 'already declares a header' };
  const lines = source.split('\n');

  if (file.endsWith('.py')) {
    const open = lines.findIndex((l) => /^\s*(?:[rub]*)"""/.test(l));
    if (open !== -1) {
      const close = lines.findIndex((l, i) => i > open && l.includes('"""'));
      if (close !== -1) {
        const at = lines[close].trim() === '"""' ? close : close;
        return [...lines.slice(0, at), '', ...body, ...lines.slice(at)].join('\n');
      }
    }
  }
  // A JS/TS FILE NEVER TAKES THE `#` FALLBACK. `#` is a comment in Python and shell and
  // a SYNTAX ERROR in TypeScript, and the fallback reached eight scripts that open with
  // `#!/usr/bin/env node`: the block-comment branch wanted `/**` on line 0, the shebang
  // is on line 0, so each was written with `# ` and stopped parsing. They are all
  // `tsx`-invoked gates, so the breakage was total and immediate.
  const js = /\.(ts|js|cjs|mjs)$/.test(file);
  const after = lines[0]?.startsWith('#!') ? 1 : 0;
  if (js) {
    if (lines[after]?.startsWith('/**')) {
      const close = lines.findIndex((l, i) => i > after && l.trim() === '*/');
      if (close !== -1) {
        return [
          ...lines.slice(0, close),
          ' *',
          ...body.map((l) => ` * ${l}`),
          ...lines.slice(close),
        ].join('\n');
      }
    }
    // NO DOUBLE BLANK. The separator below used to be unconditional, so a file
    // that ALREADY had a blank line at the insertion point got two, and
    // `biome format` (which IS check:format) reds on that. It hit the one
    // subject with no leading block comment during the 2026-09-06 header wave
    // and had to be fixed by hand. A binder that writes a format-gate red is a
    // write mode failing its own verify, the same shape as planExtract above.
    return [
      ...lines.slice(0, after),
      ...body.map((l) => `// ${l}`),
      ...(lines[after] === '' ? [] : ['']),
      ...lines.slice(after),
    ].join('\n');
  }
  // The normal path for .sh, and the fallback for anything else that takes `#`.
  // Same guard as the `//` branch above, for the same reason.
  return [
    ...lines.slice(0, after),
    ...body.map((l) => `# ${l}`),
    ...(lines[after] === '' ? [] : ['']),
    ...lines.slice(after),
  ].join('\n');
}

/**
 * Bind every file, separating a declaration from a BLOCK THAT DOES NOT PARSE.
 *
 * THE IMPORT GUARD. A file whose header is malformed used to be indistinguishable from a
 * file with no header at all: both bound to null and both were skipped in silence. That
 * made a typo strictly worse than an absent declaration, because the gate stayed
 * hand-registered AND nothing said so -- the gate was not wrong, it was invisible.
 *
 * Split out of `main` so the separation itself is controllable. Inlined, the only proof
 * it worked was that a clean tree stayed green, which is the same output a loop that
 * collected nothing would produce.
 */
export function scanDeclarations(
  files: string[],
  readFile: (f: string) => string
): { declared: Bound[]; malformed: string[] } {
  const declared: Bound[] = [];
  const malformed: string[] = [];
  for (const f of files) {
    const source = readFile(f);
    const b = bind(f, source);
    if (b !== null) {
      declared.push(b);
      continue;
    }
    const why = headerError(source);
    if (why !== null) malformed.push(`${f}: ${why}`);
  }
  return { declared, malformed };
}

function selftest(): number {
  let bad = 0;
  const ck = (label: string, ok: boolean, detail?: unknown): void => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) {
      bad += 1;
      console.log(`        ${JSON.stringify(detail)}`);
    }
  };

  const py = ['# ---- gate ----', '# step: X', '# needs: none', '# ---- end gate ----'].join('\n');
  const b = bind('.ci/scripts/quality/check_a_b.py', py);
  ck(
    'id and run derive from the path',
    b?.id === 'check:ci-a-b' && b?.run === '.ci/scripts/quality/check_a_b.py',
    b
  );
  ck(
    'an INFERRED need is unioned with the declared ones',
    bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\ngit ls-files --recurse-submodules`
    )?.needs.includes('submodules') === true
  );
  // Both controls below are regressions, found by wiring ONE gate through this binder.
  // Each mis-inference is silent: it does not fail, it moves the gate to a fatter lane.
  ck(
    'CONTROL: private/account named in PROSE infers nothing (a comment is not code)',
    !bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\n# explains a defect in private/account/Dockerfile\nx = 1`
    )?.needs.includes('submodules') === true
  );
  ck(
    'CONTROL: a variable named `node` is not a node runtime',
    !bind(
      '.ci/scripts/quality/check_a.py',
      `${py}\nfor node in ast.walk(t):\n    pass`
    )?.needs.includes('node')
  );
  ck(
    'CONTROL: but an actual `node script.js` invocation still is',
    bind('.ci/scripts/quality/check_a.sh', `${py}\nnode scripts/x.js`)?.needs.includes('node') ===
      true
  );
  const MANIFEST_FIXTURE = [
    '  {',
    '    // why it exists, line one',
    '    // and line two',
    "    id: 'check:ci-a-b',",
    "    leaves: ['.ci/scripts/quality/check_a_b.py'],",
    '    ci: {',
    "      kind: 'step',",
    "      job: 'quality-static',",
    "      step: 'A B',",
    '    },',
    '  },',
    '',
  ].join('\n');
  const reg = registered(MANIFEST_FIXTURE, 'check:ci-a-b');
  ck(
    'a manifest entry yields its file, step, job and the prose above it',
    !('error' in reg) &&
      reg.file === '.ci/scripts/quality/check_a_b.py' &&
      reg.step === 'A B' &&
      reg.job === 'quality-static' &&
      reg.run === '' &&
      reg.why.join('|') === 'why it exists, line one|and line two',
    reg
  );
  ck(
    'CONTROL: an id the manifest does not carry is an error, not an empty entry',
    'error' in registered(MANIFEST_FIXTURE, 'check:ci-nope')
  );
  ck(
    'an extracted header round-trips: what it derives is what was registered',
    (() => {
      if ('error' in reg) return false;
      const doc = `"""Doc.\n\nMore.\n"""\nx = 1\n`;
      const next = insertHeader(
        '.ci/scripts/quality/check_a_b.py',
        doc,
        headerLines(reg, [], false)
      );
      if (typeof next !== 'string') return false;
      const b2 = bind('.ci/scripts/quality/check_a_b.py', next);
      return b2?.id === 'check:ci-a-b' && b2?.step === 'A B';
    })()
  );
  ck(
    'an id the path does not imply is emitted as an explicit override',
    headerLines(
      { file: '.ci/scripts/security/shfmt.sh', step: 'S', job: 'q', run: '', why: [] },
      [],
      false,
      'check:ci-shell-format'
    ).includes('id: check:ci-shell-format')
  );
  ck(
    'CONTROL: an id the path DOES imply is left to the convention',
    !headerLines(
      { file: '.ci/scripts/quality/check_a_b.py', step: 'S', job: 'q', run: '', why: [] },
      [],
      false,
      'check:ci-a-b'
    ).some((l) => l.startsWith('id:'))
  );
  ck(
    'stripHeader removes a declared block and leaves the rest intact',
    (() => {
      const withHdr = insertHeader(
        'scripts/check-a.ts',
        '#!/usr/bin/env node\nexport const x = 1;\n',
        ['---- gate ----', 'step: A', '---- end gate ----']
      );
      if (typeof withHdr !== 'string') return false;
      const back = stripHeader(withHdr);
      return parseGateHeader(back) === null && back.includes('export const x = 1;');
    })()
  );
  ck(
    'CONTROL: stripHeader leaves a file with no header alone',
    stripHeader('const x = 1;\n') === 'const x = 1;\n'
  );
  ck(
    'CONTROL: extracting into a file that already declares one is refused',
    typeof insertHeader('.ci/scripts/quality/check_a_b.py', py, ['---- gate ----']) !== 'string'
  );
  ck(
    'a shell script carries the header as # comments under its shebang',
    (() => {
      const r2 = { file: 'x', step: 'A B', job: 'quality-static', run: '', why: [] };
      const next = insertHeader(
        '.ci/scripts/quality/check-a-b.sh',
        '#!/usr/bin/env bash\nset -e\n',
        headerLines(r2, [], false)
      );
      return (
        typeof next === 'string' && next.startsWith('#!') && parseGateHeader(next)?.step === 'A B'
      );
    })()
  );
  ck(
    'a .ts file with a SHEBANG gets // comments, never #, and still parses',
    (() => {
      const r2 = { file: 'scripts/check-a.ts', step: 'A', job: 'q', run: '', why: [] };
      const next = insertHeader(
        'scripts/check-a.ts',
        '#!/usr/bin/env node\nexport const x = 1;\n',
        headerLines(r2, [], false)
      );
      return (
        typeof next === 'string' &&
        !next.includes('# ---- gate ----') &&
        next.includes('// ---- gate ----') &&
        parseGateHeader(next)?.step === 'A'
      );
    })()
  );
  ck(
    'CONTROL: a .sh file still gets # comments',
    (() => {
      const r2 = { file: '.ci/scripts/quality/check-a.sh', step: 'A', job: 'q', run: '', why: [] };
      const next = insertHeader(
        '.ci/scripts/quality/check-a.sh',
        '#!/usr/bin/env bash\nset -e\n',
        headerLines(r2, [], false)
      );
      return typeof next === 'string' && next.includes('# ---- gate ----');
    })()
  );
  // THIS CONTROL WAS INVERTED ON 2026-09-06 AND THE INVERSION IS THE POINT. It used to
  // assert that a gate-test is OUT of scope, which was true and was also the reason all
  // 148 of their headers were unread. W2.3 gave every one of them a `kind: battery`
  // declaration, so they are subjects now and this asserts the new truth.
  ck(
    'a gate-test IS in scope: it declares kind battery, so its header is read like any other',
    !NOT_SUBJECT.test('.ci/scripts/test/gates/test-gate-header.sh')
  );
  ck(
    'CONTROL: a real gate under .ci/scripts is still in scope',
    !NOT_SUBJECT.test('.ci/scripts/quality/check_environment_names.py')
  );
  ck(
    'CONTROL: and a path outside the scanned roots is still not a subject',
    !SUBJECT.test('packages/cli/src/index.tsx.snap')
  );
  ck(
    'CONTROL: a header in a file the naming convention does not cover is still bound',
    bind('.ci/scripts/security/shfmt.sh', `${py}`) !== null
  );
  ck(
    'a file with no header is not this gate’s business',
    bind('x/check-a.py', 'print(1)') === null
  );

  const wf =
    'jobs:\n  quality-code:\n    steps:\n      - name: Gate binding\n        run: x\n  other:\n    steps:\n      - name: Elsewhere\n';
  const WF_OK = [
    '  a:',
    '    steps:',
    '      - id: setup',
    '      # >>> gate-bind',
    '      # <<< gate-bind',
    '',
  ].join('\n');
  const WF_BAD = [
    '  a:',
    '    steps:',
    '      # >>> gate-bind',
    '      # <<< gate-bind',
    '      - id: setup',
    '',
  ].join('\n');
  ck('a region below `id: setup` is accepted', regionAfterSetup(WF_OK, 'a'));
  ck(
    'CONTROL: a region ABOVE `id: setup` is refused -- its steps would silently skip',
    !regionAfterSetup(WF_BAD, 'a')
  );
  ck(
    'CONTROL: a lane with no region at all is not this check’s business',
    regionAfterSetup(['  a:', '    steps:', '      - id: setup', ''].join('\n'), 'a')
  );

  // Invariant 11, both directions. ONE gate pinned to a setup-less lane used to make
  // `--write` refuse for the whole repository, advising a region that must never exist.
  const LANES = [
    '  with-setup:',
    '    steps:',
    '      - id: setup',
    '      - name: X',
    '  no-setup:',
    '    steps:',
    '      - name: Y',
    '',
  ].join('\n');
  ck('a lane with a setup step may hold a region', laneCanEmit(LANES, 'with-setup'));
  ck(
    'CONTROL: a setup-less lane may NOT, so a gate pinned there is hand-registered, not an error',
    !laneCanEmit(LANES, 'no-setup')
  );
  ck('CONTROL: a job that is not in the workflow cannot emit', !laneCanEmit(LANES, 'absent'));

  // LOCAL-BIN SUBSTITUTION, both directions. The one-directional version of this
  // -- "tsx becomes npm run" -- was already true and still let `knip` through,
  // which is exactly the shape a control that only checks the positive case
  // cannot see.
  ck('tsx is a node_modules/.bin command', usesLocalBin('tsx scripts/x.ts'));
  ck('knip is one too, even mid-command after &&', usesLocalBin('./a.sh --install && knip --x'));
  ck('knip alone, with no arguments, is still one', usesLocalBin('knip'));
  ck(
    'CONTROL: a script PATH is not a local bin, or every step would be rewritten',
    !usesLocalBin('.ci/scripts/quality/check_x.py')
  );
  ck(
    'CONTROL: a word merely CONTAINING a bin name is not one',
    !usesLocalBin('npm run check:knipple') && !usesLocalBin('./tsxwrapper.sh')
  );
  ck(
    'CONTROL: `npm run <id>` is left alone -- substituting it again would be a no-op loop',
    !usesLocalBin('npm run lint:unused')
  );
  ck(
    'a knip-invoking gate emits `npm run <id>`, which is the whole point',
    emitStep({
      file: '.ci/scripts/quality/typecheck-workers.sh',
      id: 'lint:unused',
      run: './a.sh --install && knip --treat-config-hints-as-errors',
      kind: 'step',
      step: 'Unused exports (knip)',
      needs: [],
    }).some((l) => l === '        run: npm run lint:unused')
  );

  // The guard step is a PER-LANE fact. quality-www-build's gates hang on
  // `steps.build-www.outcome`, not setup, because they read the dist/ that step
  // produces; emitting them under the setup guard would run them against a missing
  // dist/ whenever the build failed.
  ck(
    'the emitted guard defaults to setup, which is what all but one region-bearing lane wants',
    emitStep({ file: 'x.py', id: 'check:ci-x', run: 'x.py', kind: 'step', step: 'X', needs: [] })
      .join('\n')
      .includes("steps.setup.outcome == 'success'")
  );
  ck(
    'a region declaring `guard:` re-points every step it emits',
    emitStep(
      { file: 'x.py', id: 'check:ci-x', run: 'x.py', kind: 'step', step: 'X', needs: [] },
      'build-www'
    )
      .join('\n')
      .includes("steps.build-www.outcome == 'success'")
  );
  ck(
    'regionGuard reads the marker',
    regionGuard('      # >>> gate-bind (generated) guard: build-www') === 'build-www'
  );
  ck(
    'CONTROL: a marker with no guard: falls back to setup rather than to empty',
    regionGuard('      # >>> gate-bind (generated by scripts/gate-bind.ts --write)') === 'setup'
  );

  // ACQUIRABLE needs, both directions. `python-yaml` is installed BY the emitted step
  // (the ACQUIRE table above), so demanding a lane already provide it made two gates
  // unplaceable while the workflow was already installing PyYAML for them. An unknown
  // need must still refuse, or a typo in a header places a gate anywhere.
  ck(
    'an ACQUIRABLE need does not block placement, because the step installs it',
    satisfies(
      { job: 'q', runsOn: '', timeoutMinutes: null, submodules: [], node: false, tools: [] },
      ['python-yaml']
    )
  );
  ck(
    'CONTROL: an UNKNOWN need still blocks, so a header typo cannot place a gate anywhere',
    !satisfies(
      { job: 'q', runsOn: '', timeoutMinutes: null, submodules: [], node: false, tools: [] },
      ['nonsense-tool']
    )
  );
  ck(
    'CONTROL: a real structural need is still checked',
    !satisfies(
      { job: 'q', runsOn: '', timeoutMinutes: null, submodules: [], node: false, tools: [] },
      ['submodules']
    ) &&
      satisfies(
        { job: 'q', runsOn: '', timeoutMinutes: null, submodules: ['*'], node: false, tools: [] },
        ['submodules']
      )
  );
  ck(
    'a declared python-yaml need is ACQUIRED in the emitted step, at the pin',
    (() => {
      const out = emitStep({
        file: 'x.py',
        id: 'check:ci-x',
        run: 'x.py',
        kind: 'step',
        step: 'X',
        needs: ['python-yaml'],
      });
      return (
        out.includes('        run: |') &&
        out.some((l) => l.includes('PyYAML==${PYYAML_VERSION}')) &&
        out[out.length - 1] === '          x.py'
      );
    })()
  );
  ck(
    'CONTROL: a gate that needs nothing gets a one-line run, not a block',
    emitStep({
      file: 'x.py',
      id: 'check:ci-x',
      run: 'x.py',
      kind: 'step',
      step: 'X',
      needs: [],
    }).includes('        run: x.py')
  );
  const DUP = [
    '  a:',
    '    steps:',
    '      - name: X',
    '        run: x',
    '      - name: X',
    '        run: x',
    '',
  ].join('\n');
  ck(
    'two steps of the same name in one job are counted as two',
    stepCountInJob(DUP, 'a', 'X') === 2
  );
  ck(
    'CONTROL: one is one, so an ordinary emitted step is not accused',
    stepCountInJob('  a:\n    steps:\n      - name: X\n        run: x\n', 'a', 'X') === 1
  );
  ck(
    'CONTROL: a duplicate in a DIFFERENT job is not this job’s problem',
    stepCountInJob(`${DUP.replace('  a:', '  b:')}`, 'a', 'X') === 0
  );
  ck('a gate under scripts/ is in scope', inScope('scripts/gates/check-deps.ts'));
  ck(
    'a gate inside the python package is in scope, or its header would be inert',
    inScope('.ci/rediacc_ci/check_pytest.py')
  );
  ck(
    'CONTROL: packages/cli/scripts is NOT -- a header there is never read',
    !inScope('packages/cli/scripts/check-cli-i18n-help-render.ts')
  );
  ck('stepInJob finds a step in its own job', stepInJob(wf, 'quality-code', 'Gate binding'));
  ck('CONTROL: it does NOT find it in a different job', !stepInJob(wf, 'other', 'Gate binding'));
  ck('CONTROL: a step that is not there is not found', !stepInJob(wf, 'quality-code', 'Nope'));

  // --- kind discriminant (parser v2) ---------------------------------------------
  // These controls exist because the drain hit the same wall 143 times: a gate-test
  // cannot own the one battery step every gate-test rides, so under v1 it could not
  // declare at all. What must hold now is that it CAN declare and STILL not be emitted.
  const battery = [
    '# ---- gate ----',
    '# kind: battery',
    '# step: Quality-gate unit tests',
    '# ---- end gate ----',
  ].join('\n');
  const bBat = bind('.ci/scripts/test/gates/test-a.sh', battery);
  ck('a battery gate binds, carrying the step it rides', bBat?.kind === 'battery', bBat);
  ck('CONTROL: and a region never emits it', bBat !== null && !emits(bBat));
  const stepish = bind(
    '.ci/scripts/quality/check_a.py',
    '# ---- gate ----\n# step: X\n# ---- end gate ----'
  );
  ck(
    'a header with no `kind:` is still a step, and IS emitted',
    stepish !== null && emits(stepish)
  );
  const localOnly = [
    '# ---- gate ----',
    '# kind: local-only',
    '# blocker: BLOCKER: no CI step invokes this script',
    '# ---- end gate ----',
  ].join('\n');
  const bLoc = bind('.ci/scripts/quality/check_a.py', localOnly);
  ck(
    'a local-only gate binds with no step at all',
    bLoc?.kind === 'local-only' && bLoc.step === undefined,
    bLoc
  );
  ck('CONTROL: and is not emitted either', bLoc !== null && !emits(bLoc));
  ck(
    'CONTROL: a stepless kind that names a step is REFUSED, not quietly accepted',
    bind(
      '.ci/scripts/quality/check_a.py',
      localOnly.replace('# blocker:', '# step: X\n# blocker:')
    ) === null
  );
  ck(
    'CONTROL: and the refusal says why, rather than reading as "no header"',
    headerError(localOnly.replace('# blocker:', '# step: X\n# blocker:'))?.includes(
      'has no workflow step'
    ) === true
  );
  ck(
    'CONTROL: an unterminated block is an ERROR, not an absent declaration',
    headerError('# ---- gate ----\n# step: X')?.includes('never closes') === true
  );
  ck(
    'CONTROL: a file with no block at all produces no error to report',
    headerError('print("hi")') === null
  );

  const TWO_JOBS = [
    '  a:',
    '    steps:',
    '      - name: Shared',
    '  b:',
    '    steps:',
    '      - name: Shared',
    '      - name: Only here',
    '',
  ].join('\n');
  ck(
    'jobsWithStep names the one job holding a step',
    jobsWithStep(TWO_JOBS, 'Only here').join() === 'b'
  );
  ck(
    'CONTROL: a step name in two jobs returns BOTH, so a battery gate is refused rather than resolved to the first',
    jobsWithStep(TWO_JOBS, 'Shared').join() === 'a,b'
  );
  ck(
    'CONTROL: a step nowhere in the workflow returns nothing',
    jobsWithStep(TWO_JOBS, 'Nope').length === 0
  );

  // `emit: false` -- a gate that OWNS a hand-written step a region must not take over.
  // 18 gates in quality-code run BETWEEN `Setup workspace` and `- id: setup`, so their
  // steps carry no setup guard; emitting them would move them below it and silence
  // exactly the gates that explain a broken setup.
  const handWritten = [
    '# ---- gate ----',
    '# step: Toolchain pins',
    '# emit: false',
    '# blocker: BLOCKER: runs before the lane setup step, so a region would gate it on setup',
    '# ---- end gate ----',
  ].join('\n');
  const bHand = bind('.ci/scripts/quality/check-a.sh', handWritten);
  ck('an emit:false gate still BINDS, and keeps its step', bHand?.step === 'Toolchain pins', bHand);
  ck('CONTROL: but no region emits it', bHand !== null && !emits(bHand));
  ck(
    'CONTROL: emit:false without a blocker is refused, so it cannot pass for an unfinished registration',
    headerError(
      handWritten
        .split('\n')
        .filter((l) => !l.startsWith('# blocker'))
        .join('\n')
    )?.includes('blocker') === true
  );
  ck(
    'CONTROL: emit:false is meaningless on a stepless kind and is refused',
    headerError(
      [
        '# ---- gate ----',
        '# kind: local-only',
        '# emit: false',
        '# blocker: b',
        '# ---- end gate ----',
      ].join('\n')
    )?.includes('only meaningful for kind: step') === true
  );
  ck(
    'CONTROL: a non-boolean emit is refused rather than read as false',
    headerError(handWritten.replace('# emit: false', '# emit: sometimes'))?.includes(
      'not a boolean'
    ) === true
  );
  ck(
    'CONTROL: emit defaults to TRUE, so every existing declaration keeps emitting',
    emits(
      bind(
        '.ci/scripts/quality/check-a.sh',
        '# ---- gate ----\n# step: X\n# ---- end gate ----'
      ) as Bound
    )
  );

  const SCAN: Record<string, string> = {
    'a.py': '# ---- gate ----\n# step: Good\n# ---- end gate ----',
    'b.py': '# ---- gate ----\n# step: Unclosed',
    'c.py': 'x = 1',
  };
  const scan = scanDeclarations(Object.keys(SCAN), (f) => SCAN[f]);
  ck(
    'the scan collects the declaration it can parse',
    scan.declared.map((d) => d.step).join() === 'Good'
  );
  ck(
    'CONTROL: and REPORTS the block it cannot, by file, instead of skipping it',
    scan.malformed.length === 1 && scan.malformed[0].startsWith('b.py: '),
    scan.malformed
  );
  ck(
    'CONTROL: a file with no block is neither declared nor reported',
    scan.declared.length + scan.malformed.length === 2
  );

  const b2: Emitting = {
    file: 'x/check_a.py',
    id: 'check:ci-a',
    run: 'x/check_a.py',
    kind: 'step',
    step: 'A',
    needs: [],
  };
  ck(
    'an emitted step carries the if: guard 189 of 258 steps already have',
    emitStep(b2)[1].includes("!cancelled() && steps.setup.outcome == 'success'"),
    emitStep(b2)
  );
  ck(
    'a .ts gate is emitted as `npm run <id>`, a script as its bare path',
    emitStep({ ...b2, run: 'tsx x/check-a.ts' })[2].trim() === 'run: npm run check:ci-a' &&
      emitStep(b2)[2].trim() === 'run: x/check_a.py'
  );

  const region = [
    'jobs:',
    '  quality-static:',
    '    steps:',
    '      # >>> gate-bind (generated)',
    '      # explanatory prose',
    '      - name: STALE',
    '        run: old',
    '      # <<< gate-bind',
    '      - name: hand-written after',
  ].join('\n');
  const rw = rewriteRegions(region, new Map([['quality-static', [b2]]]));
  ck(
    'rewriting replaces the region body but KEEPS its prose',
    rw.text.includes('# explanatory prose') &&
      !rw.text.includes('STALE') &&
      rw.text.includes('- name: A'),
    rw.text
  );
  ck(
    'and leaves hand-written steps outside it alone',
    rw.text.includes('- name: hand-written after')
  );
  ck(
    'rewriting is IDEMPOTENT -- the second pass changes nothing',
    rewriteRegions(rw.text, new Map([['quality-static', [b2]]])).text === rw.text
  );

  // --- the strip guard (box A2) -------------------------------------------------
  // A REFUSAL NOBODY HAS WATCHED FIRE IS NOT A REFUSAL. Each of these drives
  // `classifyDrops` directly, which is why it was extracted out of `main`.
  const DROP = ['quality-static: Check X'];
  const MANIFEST_WITH = "  { id: 'check:x', step: 'Check X' },";
  const none = new Set<string>();

  ck(
    'strip guard: a drop that nothing re-emits and no manifest entry names is UNCLAIMED',
    classifyDrops(DROP, none, none, '').unclaimed.length === 1 &&
      classifyDrops(DROP, none, none, '').claimed.length === 0
  );
  ck(
    'strip guard: the same drop with the manifest still naming the step is CLAIMED, a regression',
    classifyDrops(DROP, none, none, MANIFEST_WITH).claimed.length === 1 &&
      classifyDrops(DROP, none, none, MANIFEST_WITH).unclaimed.length === 0
  );
  ck(
    'CONTROL: a step the rewrite RE-EMITS is not a drop at all, in either bucket',
    classifyDrops(DROP, new Set(DROP), none, MANIFEST_WITH).claimed.length === 0 &&
      classifyDrops(DROP, new Set(DROP), none, MANIFEST_WITH).unclaimed.length === 0
  );
  ck(
    '`--allow-drop <step>` is the ONE typed escape, and it silences both buckets',
    classifyDrops(DROP, none, new Set(['Check X']), '').unclaimed.length === 0 &&
      classifyDrops(DROP, none, new Set(['Check X']), MANIFEST_WITH).claimed.length === 0
  );
  ck(
    'CONTROL: --allow-drop matches the STEP, not a prefix of it, so it cannot over-silence',
    classifyDrops(DROP, none, new Set(['Check']), '').unclaimed.length === 1
  );
  ck(
    'CONTROL: an empty drop list is silent, so the guard cannot fire on a clean rewrite',
    classifyDrops([], none, none, MANIFEST_WITH).unclaimed.length === 0
  );

  // --- env and the `when` conjunct (box A1) --------------------------------------
  const base = {
    file: 'x.py',
    id: 'check:ci-x',
    run: 'x.py',
    kind: 'step' as const,
    step: 'X',
    needs: [],
  };
  const line = (out: string[], k: string) => out.find((l) => l.trim().startsWith(k)) ?? '';

  ck(
    'env is emitted, sorted, between the guard and the run',
    (() => {
      const out = emitStep({ ...base, env: { ZED: '1', ALPHA: '2' } });
      const i = out.findIndex((l) => l.trim() === 'env:');
      return (
        i > 0 &&
        out[i + 1].trim() === 'ALPHA: 2' &&
        out[i + 2].trim() === 'ZED: 1' &&
        out[i + 3].trim().startsWith('run:')
      );
    })()
  );
  ck(
    'CONTROL: a gate with no env emits no `env:` key at all, not an empty map',
    !emitStep(base).some((l) => l.trim() === 'env:')
  );
  ck(
    '`when` is ANDed onto the standard guard, which survives verbatim',
    (() => {
      const g = line(emitStep({ ...base, when: "github.event_name == 'push'" }), 'if:');
      return (
        g.includes("!cancelled() && steps.setup.outcome == 'success'") &&
        g.includes("&& (github.event_name == 'push')")
      );
    })()
  );
  ck(
    'a `when` containing `||` is PARENTHESISED, so it cannot bind looser and swallow the guard',
    line(emitStep({ ...base, when: 'a || b' }), 'if:').includes("outcome == 'success' && (a || b)")
  );
  ck(
    'CONTROL: no `when` leaves the guard byte-identical to what it was before A1',
    line(emitStep(base), 'if:').trim() ===
      "if: ${{ !cancelled() && steps.setup.outcome == 'success' }}"
  );

  // T-SCHED B2 D3: rewriteStrategyRegions, previously with no selftest control at all.
  const SS_JOB = [
    '  quality-code:',
    '    name: Code',
    '    runs-on: ubuntu-latest',
    '    timeout-minutes: 15',
    '    steps:',
    '      - name: x',
    '        run: echo hi',
    '',
  ].join('\n');
  const SS_JOB_WITH_REGION = (shards: string) =>
    [
      '  quality-code:',
      '    name: Code',
      '    runs-on: ubuntu-latest',
      '    timeout-minutes: 15',
      '    # >>> shard-strategy (generated; do not edit inside)',
      '    strategy:',
      '      fail-fast: false',
      '      matrix:',
      `        shard: [${shards}]`,
      '    # <<< shard-strategy',
      '    steps:',
      '      - name: x',
      '        run: echo hi',
      '',
    ].join('\n');
  ck(
    'CONTROL: no lane in SHARD_COUNTS and no region present is silent',
    rewriteStrategyRegions(SS_JOB, {}).length === 0
  );
  ck(
    'a lane in SHARD_COUNTS with no region refuses, naming the exact YAML',
    (() => {
      const f = rewriteStrategyRegions(SS_JOB, { 'quality-code': 4 });
      return (
        f.length === 1 &&
        f[0]?.includes('no shard-strategy region') &&
        f[0]?.includes('shard: [1, 2, 3, 4]')
      );
    })()
  );
  ck(
    'a region for a lane not in SHARD_COUNTS refuses as a drain',
    rewriteStrategyRegions(SS_JOB_WITH_REGION('1, 2, 3, 4'), {})[0]?.includes(
      'is a drain, not a no-op'
    ) === true
  );
  ck(
    'a region agreeing with SHARD_COUNTS is silent',
    rewriteStrategyRegions(SS_JOB_WITH_REGION('1, 2, 3, 4'), { 'quality-code': 4 }).length === 0
  );
  ck(
    'a region whose shard list disagrees with SHARD_COUNTS refuses, naming both',
    (() => {
      const f = rewriteStrategyRegions(SS_JOB_WITH_REGION('1, 2'), { 'quality-code': 4 });
      return (
        f.length === 1 && f[0]?.includes('lists [1, 2]') && f[0]?.includes('expected [1, 2, 3, 4]')
      );
    })()
  );
  ck(
    "CONTROL: the plan box's OWN proposed marker (`# >>> gate-bind strategy`) would have " +
      'collided with OPEN_RE -- proving why shard-strategy uses a different prefix, not gate-bind',
    OPEN_RE.test('    # >>> gate-bind strategy (generated; do not edit inside)') &&
      !CLOSE_RE.test('    # <<< gate-bind strategy')
  );

  // T-SCHED B2 D4, first clause: a deterministic id, only when sharded.
  ck(
    'gateStepId maps `:`/`-` to `_`, prefixed so it never starts with a digit',
    gateStepId('check:ci-foo-bar') === 'gate_check_ci_foo_bar'
  );
  ck(
    'CONTROL: an unsharded step gets no id: line at all (byte-identical to pre-D4)',
    !emitStep(base).some((l) => l.trim().startsWith('id:'))
  );
  ck(
    'a sharded step gets exactly the id gateStepId computes',
    emitStep(base, 'setup', gateStepId(base.id)).some(
      (l) => l.trim() === `id: ${gateStepId(base.id)}`
    )
  );
  ck(
    'lockIdsEnvValue is a single-quoted YAML scalar holding the JSON array',
    lockIdsEnvValue(['check:ci-foo']) === `'["check:ci-foo"]'` &&
      JSON.parse(lockIdsEnvValue(['a', 'b']).slice(1, -1))[1] === 'b'
  );
  ck(
    "CONTROL: an unsharded step's env is untouched by D4 (no GATE_LOCK_IDS key at all)",
    !emitStep(base).some((l) => l.includes('GATE_LOCK_IDS'))
  );
  ck(
    'jobLockIdMap: one gate id maps to itself, keyed by its own step id',
    (() => {
      const m = jobLockIdMap([base]);
      return Object.keys(m).length === 1 && m[gateStepId(base.id)]?.[0] === base.id;
    })()
  );
  ck(
    'rewriteRegions end to end: a sharded gate carries both id: and env: GATE_LOCK_IDS',
    (() => {
      const region = [
        '  quality-static:',
        '    # >>> gate-bind (generated; do not edit inside)',
        '    # <<< gate-bind',
      ].join('\n');
      const rw = rewriteRegions(
        region,
        new Map([['quality-static', [base]]]),
        undefined,
        new Map([['quality-static', new Map([[base.id, 1]])]])
      );
      return (
        rw.text.includes(`id: ${gateStepId(base.id)}`) &&
        rw.text.includes(`GATE_LOCK_IDS: ${lockIdsEnvValue([base.id])}`)
      );
    })()
  );

  // T-SCHED B2 D4, final clause: emitReceiptStep and its wiring.
  ck(
    'emitReceiptStep: always() guard, both steps present, the map matches jobLockIdMap',
    (() => {
      const out = emitReceiptStep('quality-code', 4, [base]);
      const text = out.join('\n');
      return (
        line(out, 'if:') === '        if: always()' &&
        text.includes('Write shard receipt') &&
        text.includes('Upload shard receipt') &&
        text.includes(`GATE_STEP_LOCK_MAP: ${jsonEnvValue(jobLockIdMap([base]))}`) &&
        text.includes("SHARD_OF: '4'") &&
        text.includes('actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a') &&
        text.includes('name: quality-shard-${{ matrix.shard }}')
      );
    })()
  );
  ck(
    'CONTROL: the receipt script never contains a literal `${{`, so GHA cannot mis-substitute inside it',
    !emitReceiptStep('quality-code', 4, [base]).some(
      (l) => l.includes('${{') && l.includes('process.env')
    )
  );
  ck(
    'rewriteRegions: a sharded job gets the receipt step, an unsharded one does not',
    (() => {
      const region = [
        '  quality-static:',
        '    # >>> gate-bind (generated; do not edit inside)',
        '    # <<< gate-bind',
      ].join('\n');
      const sharded = rewriteRegions(
        region,
        new Map([['quality-static', [base]]]),
        undefined,
        new Map([['quality-static', new Map([[base.id, 1]])]])
      );
      const unsharded = rewriteRegions(region, new Map([['quality-static', [base]]]));
      return (
        sharded.text.includes('Write shard receipt') &&
        !unsharded.text.includes('Write shard receipt')
      );
    })()
  );
  ck(
    'a lane WITH an assignment emits matrix.shard == N on exactly the steps the plan gives that leg',
    (() => {
      const other = { ...base, id: 'check:ci-other', step: 'Other', file: 'x/check_other.py' };
      const region = [
        '  quality-static:',
        '    # >>> gate-bind (generated; do not edit inside)',
        '    # <<< gate-bind',
      ].join('\n');
      const rw = rewriteRegions(
        region,
        new Map([['quality-static', [base, other]]]),
        undefined,
        new Map([
          [
            'quality-static',
            new Map([
              [base.id, 1],
              [other.id, 2],
            ]),
          ],
        ])
      );
      const conjuncts = rw.text.split('\n').filter((l) => l.includes('matrix.shard =='));
      return (
        conjuncts.length === 2 &&
        conjuncts.filter((l) => l.includes('matrix.shard == 1')).length === 1 &&
        conjuncts.filter((l) => l.includes('matrix.shard == 2')).length === 1
      );
    })()
  );
  ck(
    'a lane WITHOUT an assignment emits byte-identically to a call that passes no shard map',
    (() => {
      const region = [
        '  quality-static:',
        '    # >>> gate-bind (generated; do not edit inside)',
        '    # <<< gate-bind',
      ].join('\n');
      const byLane = new Map([['quality-static', [base]]]);
      const plain = rewriteRegions(region, byLane).text;
      const elsewhere = rewriteRegions(
        region,
        byLane,
        undefined,
        new Map([['quality-code', new Map([[base.id, 1]])]])
      ).text;
      return plain === elsewhere && !plain.includes('matrix.shard');
    })()
  );

  return bad;
}

function main(argv: string[]): void {
  // `--dry-run` REPORTS what `--write` would do and writes nothing.
  //
  // Added after writing the workflow twice by accident. There was no way to ask this
  // binder what it would emit without emitting it, so "let me see the hold-out set"
  // rewrote three regions and left 124 duplicate steps behind, twice. A destructive
  // generator whose only inspection mode is running it teaches you to run it.
  const dryRun = argv.includes('--dry-run');
  const write = argv.includes('--write') || dryRun;
  // `--lane <job>` STAGES THE CUTOVER ONE LANE AT A TIME, and without it the cutover
  // cannot be staged at all.
  //
  // `--write` rewrites EVERY region from the full declared set. Today 167 declared gates
  // would be emitted while their hand-written copies still exist, so a write meant to
  // convert one lane silently duplicates 46 steps in three others. That is not a
  // hypothetical: it happened twice while this tool was being built, and both times the
  // region bodies had to be restored from `git show HEAD:`.
  //
  // The emitted order inside a region is ALPHABETICAL, and a region must sit after its
  // lane's PREREQUISITE steps rather than merely after `- id: setup` -- quality-www-build
  // builds www first and check-landmarks.ts:89 refuses without dist/. Both of those are
  // per-lane judgements, which is the second reason one lane at a time is the only safe
  // shape: they cannot be made once for eight lanes.
  const laneIdx = argv.indexOf('--lane');
  const onlyLane = laneIdx >= 0 ? argv[laneIdx + 1] : undefined;
  // `--allow-drop <step>` IS THE ONE TYPED ESCAPE from the strip guard below, repeatable.
  // Typed, because the whole point is that removing a step from CI should cost a
  // deliberate keystroke naming the step, not a silent line in a summary.
  const allowDrop = new Set(
    argv.flatMap((a, i) => (a === '--allow-drop' && argv[i + 1] ? [argv[i + 1]] : []))
  );
  if (argv.includes('--selftest')) {
    const n = selftest();
    console.log(`${n === 0 ? '✓' : '✗'} gate-bind selftest: ${n} failure(s)`);
    process.exit(n === 0 ? 0 : 1);
  }

  // --extract-all: one process for the whole manifest.
  //
  // WHY THIS EXISTS AS A MODE RATHER THAN A SHELL LOOP. Extracting 20 gates with
  // `for id in ...; do npx tsx gate-bind.ts --extract $id; done` cost ~40s, and about
  // 38 of those were node and tsx starting up 20 times. The scan itself is ~1s over 603
  // files. Batching removes the only cost that mattered; nothing here is CPU-bound
  // enough for workers to beat one pass.
  if (argv.includes('--extract-all')) {
    const dry = argv.includes('--dry-run');
    const manifestText = read('scripts/ci-runner/manifest.ts');
    const pkg = (JSON.parse(read('package.json')) as { scripts: Record<string, string> }).scripts;
    const caps = laneCapabilities(read(WORKFLOW));
    const done: string[] = [];
    const refused = new Map<string, string[]>();
    for (const id of manifestIds(manifestText)) {
      const plan = planExtract(manifestText, id, read, pkg[id] ?? '', caps, false);
      if ('error' in plan) {
        // Grouped by REASON, not listed per gate: ~200 refusals of four shapes is a
        // wall, and a wall is what stops anyone reading the handful that matter.
        const key = plan.error.includes('is shared by')
          ? 'shares a step with other gates (sub-gate of an aggregate)'
          : plan.error.includes('outside the scan')
            ? 'outside .ci/scripts and scripts'
            : plan.error.includes('already declares')
              ? 'already declares a header'
              : plan.error.includes('re-derives')
                ? 'registration does not round-trip from the path'
                : 'other';
        refused.set(key, [...(refused.get(key) ?? []), id]);
        continue;
      }
      if (!dry) fs.writeFileSync(path.join(ROOT, plan.file), plan.next);
      done.push(`${id} -> ${plan.job} / "${plan.step}"`);
    }
    console.log(`${dry ? 'would extract' : 'extracted'}: ${done.length}`);
    for (const line of done) console.log(`    ${line}`);
    console.log(`refused: ${[...refused.values()].reduce((a, b) => a + b.length, 0)}`);
    for (const [why, ids] of [...refused].sort((a, b) => b[1].length - a[1].length)) {
      console.log(`    ${String(ids.length).padStart(4)}  ${why}`);
    }
    if (!dry && done.length > 0) {
      console.log('\nNow run `--write`, and place a `# >>> gate-bind` region in any lane');
      console.log('that has none. Then re-run with no flags to verify every binding.');
    }
    process.exit(0);
  }

  const rbAt = argv.indexOf('--rebind');
  const exAt = rbAt !== -1 ? rbAt : argv.indexOf('--extract');
  if (exAt !== -1) {
    const id = argv[exAt + 1];
    if (id === undefined || id.startsWith('--')) {
      console.error('✗ --extract needs a gate id, e.g. --extract check:ci-shell-format');
      process.exit(1);
    }
    const manifestText = read('scripts/ci-runner/manifest.ts');
    const reg = registered(manifestText, id);
    if ('error' in reg) {
      console.error(`✗ ${reg.error}`);
      process.exit(1);
    }
    const pkgScripts = (JSON.parse(read('package.json')) as { scripts: Record<string, string> })
      .scripts;
    reg.run = pkgScripts[id] ?? '';
    // A HEADER THE BINDER WILL NEVER READ IS WORSE THAN NO HEADER. The scan is
    // `git ls-files .ci/scripts scripts`; extraction wrote valid headers into
    // packages/cli/scripts/ and packages/www/scripts/, which sit outside it, and they
    // were simply never seen -- the same silent-ignore this gate already closed once
    // for file NAMES, returning through file PATHS.
    if (!inScope(reg.file)) {
      console.error(
        `✗ ${id}: ${reg.file} is outside this gate's scan (.ci/scripts, scripts), so a ` +
          'header there would never be read. It stays hand-registered.'
      );
      process.exit(1);
    }
    // A GATE WITH NO STEP OF ITS OWN CANNOT DECLARE ONE. 132 gate-tests share the single
    // step 'Quality-gate unit tests' and 10 i18n checks share 'i18n': they are sub-gates
    // of one aggregate command, not steps. Emitting a header for each would write the
    // same step name N times into a lane. This is the ceiling on what --extract can
    // ever cover, and it is better stated here than discovered per gate.
    const sharers = (
      manifestText.match(
        new RegExp(`step: '${reg.step.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}'`, 'g')
      ) ?? []
    ).length;
    if (sharers > 1) {
      console.error(
        `✗ ${id}: step "${reg.step}" is shared by ${sharers} manifest entries, so no one ` +
          'gate owns it. Sub-gates of an aggregate step stay hand-registered.'
      );
      process.exit(1);
    }
    const src = rbAt !== -1 ? stripHeader(read(reg.file)) : read(reg.file);
    const needs = inferredNeeds(src);
    // PIN THE LANE ONLY WHEN THE INFERENCE DISAGREES. Emitting `lane:` unconditionally
    // would freeze today's placement into 129 files and make the derivation decorative.
    const placed = placeGate(laneCapabilities(read(WORKFLOW)), needs);
    const pinLane = !('lane' in placed) || placed.lane !== reg.job;
    const next = insertHeader(reg.file, src, headerLines(reg, needs, pinLane, id));
    if (typeof next !== 'string') {
      console.error(`✗ ${reg.file}: ${next.error}`);
      process.exit(1);
    }
    // THE EXTRACTION MUST ROUND-TRIP. A header that re-derives something OTHER than what
    // is registered would move the gate silently, which is the class this tool closes.
    const rb = bind(reg.file, next);
    // RUN IS PART OF THE ROUND TRIP. Checking only id and step let six headers be
    // written whose `run` disagreed with package.json -- the gate then reported them as
    // binding problems, which is the tool creating the work it exists to remove.
    const runOk = reg.run === '' || rb?.run === reg.run;
    if (rb === null || rb.id !== id || rb.step !== reg.step || !runOk) {
      const got = rb === null ? 'nothing' : `${rb.id} / "${rb.step}" / ${rb.run}`;
      console.error(
        `✗ ${reg.file}: emitted header re-derives ${got}, not ${id} / "${reg.step}". Not written.`
      );
      process.exit(1);
    }
    fs.writeFileSync(path.join(ROOT, reg.file), next);
    console.log(`✓ ${reg.file} now declares its own binding (step "${reg.step}", lane ${reg.job})`);
    console.log('  Re-run with no flags to confirm it still matches its registration.');
    process.exit(0);
  }

  console.log('gate binding: controls first, then the verdict');
  if (selftest() !== 0) {
    console.error('✗ instrument control failed; every verdict below would be meaningless');
    process.exit(2);
  }

  const pkg = JSON.parse(read('package.json')) as { scripts: Record<string, string> };
  const manifest = read('scripts/ci-runner/manifest.ts');
  // THE LOCK, not the manifest text, decides whether an id is a gate-test. `manifest.ts`
  // is TypeScript and this file would have to re-implement a fragment of a TS parser to
  // read `qualityGateTest` out of it, which is the exact archaeology gates.lock.json was
  // committed to end.
  const lock = JSON.parse(read('scripts/ci-runner/gates.lock.json')) as {
    id: string;
    run: string;
    qualityGateTest?: boolean;
  }[];
  const lockById = new Map(lock.map((g) => [g.id, g]));
  const workflow = read(WORKFLOW);
  const caps = laneCapabilities(workflow);
  // The lock, for the shard assignment below. Read here and not inside the loop so a
  // malformed lock fails once, loudly, rather than once per sharded lane.
  const lockEntries = JSON.parse(read('scripts/ci-runner/gates.lock.json')) as Parameters<
    typeof shardAssignment
  >[1];

  const { present, missing } = trackedSubjects();
  if (missing.length > 0) {
    console.error(
      `✗ CANNOT VERIFY: ${missing.length} tracked file(s) are absent from the worktree:`
    );
    for (const f of missing.slice(0, 10)) console.error(`    ${f}`);
    console.error('');
    console.error('  The index and the worktree disagree, which in a shared checkout');
    console.error('  usually means another session is mid-change. Refusing a verdict');
    console.error('  rather than reading a tree that is moving.');
    process.exit(1);
  }

  const { declared, malformed } = scanDeclarations(present, read);

  // ANTI-VACUITY. Until the drain lands, "no gate declares a header" is what a broken
  // scan looks like and what a clean tree looks like, and they must not be the same.
  if (declared.length === 0) {
    console.error(
      '✗ VACUOUS: not one tracked gate carries a `---- gate ----` header. Either the ' +
        'parser stopped matching or the declarations were removed; refusing a verdict.'
    );
    process.exit(1);
  }

  // A MALFORMED HEADER REFUSES EVERY MODE, NOT JUST THE VERIFY ONE. This list was
  // collected here and then only ever folded into `problems`, which is reached AFTER the
  // `write` branch returns -- so `--write` and `--dry-run` both ran to completion with a
  // voided declaration in the tree and said nothing. Found 2026-09-06 by two agents who
  // planted `---- /gate ----` in a gate-test, watched `--dry-run` exit 0 without naming
  // the file, and correctly concluded their headers were unread. They were half right:
  // the tree really was out of scope, and this is the OTHER half.
  //
  // Refusing a `--write` matters more than refusing a report. A voided declaration is a
  // gate this binder cannot see, so the region it would have emitted is written WITHOUT
  // it, and `--write` owns whole regions: the gate does not become unregistered, it
  // disappears.
  if (malformed.length > 0) {
    console.error(`✗ ${malformed.length} malformed \`---- gate ----\` block(s):`);
    for (const m of malformed) console.error(`    ${m}`);
    console.error(
      '\n  A block that does not close is not a declaration and not an absent one either.\n' +
        '  Fix the header before binding: a region written now would omit these gates.'
    );
    process.exit(1);
  }

  if (write) {
    const byLane = new Map<string, Emitting[]>();
    const handRegistered: string[] = [];
    // ONLY `kind: step` IS EMITTED. A battery gate rides a hand-written step it does not
    // own, and a `test` or `local-only` gate has no step at all; emitting any of them
    // would write 143 duplicate copies of one battery step into a region.
    // HELD OUT BY THEIR OWN DECLARATION, and NAMED. `emit: false` means the gate owns a
    // hand-written step a region must not take over; not saying so would make "declared
    // and deliberately not emitted" look identical to "declared and forgotten", which is the exact confusion the import guard above exists to end.
    const declaredHoldouts = declared.filter((b) => b.kind === 'step' && b.emit === false);
    if (declaredHoldouts.length > 0) {
      console.log(
        `note: ${declaredHoldouts.length} declared gate(s) opt OUT of emission with ` +
          '`emit: false`, keeping their hand-written step:'
      );
      for (const b of declaredHoldouts) console.log(`    ${b.file} -> "${b.step}"`);
    }
    for (const b of declared.filter(emits)) {
      const placed = placeGate(caps, b.needs);
      const job = b.lane ?? ('lane' in placed ? placed.lane : '');
      if (job === '') {
        console.error(`✗ ${b.file}: ${'error' in placed ? placed.error : 'no lane'}`);
        process.exit(1);
      }
      // A LANE WITH NO `- id: setup` CANNOT HOLD A REGION (invariant 11), so a gate pinned there is hand-registered by construction. Held out of byLane and NAMED below -- never silently, because "not emitted" and "forgotten" look identical.
      if (!laneCanEmit(workflow, job)) {
        handRegistered.push(`${b.file} -> ${job} (no \`- id: setup\`, so no region may exist)`);
        continue;
      }
      byLane.set(job, [...(byLane.get(job) ?? []), b]);
    }
    if (handRegistered.length > 0) {
      console.log(
        `note: ${handRegistered.length} declared gate(s) stay hand-registered, their lane ` +
          'having no setup step to guard an emitted region:'
      );
      for (const h of handRegistered) console.log(`    ${h}`);
    }
    // Restrict to one lane when asked. Done by narrowing byLane rather than by filtering the output, so a lane with no region simply is not touched and every refusal below still speaks for the lane actually being written.
    const scoped =
      onlyLane === undefined ? byLane : new Map([...byLane].filter(([lane]) => lane === onlyLane));
    const only = onlyLane === undefined ? undefined : new Set([onlyLane]);
    if (onlyLane !== undefined && scoped.size === 0) {
      console.error(
        `✗ --lane ${onlyLane}: no declared gate places into that lane. Lanes holding ` +
          `declared gates right now: ${[...byLane.keys()].sort().join(', ')}`
      );
      process.exit(1);
    }
    // THE SHARD ASSIGNMENT, computed once per run from the SAME plan the aggregator re-runs. A lane absent from SHARD_COUNTS yields nothing and its steps emit exactly as before, which is what keeps this change inert for the nine unsharded lanes.
    const shardMap = new Map<string, ReadonlyMap<string, number>>();
    for (const job of Object.keys(SHARD_COUNTS)) {
      const assigned = shardAssignment(job, lockEntries, caps, byLane.get(job) ?? []);
      if (assigned === null) continue;
      if ('error' in assigned) {
        console.error(`✗ ${job}: ${assigned.error}`);
        process.exit(1);
      }
      // PRINTED EVERY RUN a lane is sharded, never only on refusal: a quiet exemption is how a gate stops meaning its name, and D2 exists because the quality-security mistake was silent right up until someone ran the numbers by hand.
      if (assigned.replicated.length > 0) {
        console.log(
          `note: ${job} shards with ${assigned.replicated.length} entr${assigned.replicated.length === 1 ? 'y' : 'ies'} ` +
            'running replicated on every leg (no emitted step to conjunct):'
        );
        for (const id of assigned.replicated) console.log(`    ${id}`);
      }
      shardMap.set(job, assigned.legs);
    }
    // T-SCHED B2 D3, BEFORE rewriteRegions: a shard conjunct on a job with no real `strategy:` block is Finding 2's vacuity (GitHub evaluates `matrix.shard` as `null` with no `strategy.matrix`, so every conjuncted step silently skips). A REFUSAL, not a rewrite -- see rewriteStrategyRegions's own docstring for why this one region is never auto-applied.
    const strategyFindings = rewriteStrategyRegions(workflow, SHARD_COUNTS);
    if (strategyFindings.length > 0) {
      console.error(`✗ ${strategyFindings.length} shard-strategy finding(s):`);
      for (const f of strategyFindings) console.error(`    ${f}`);
      process.exit(1);
    }
    const { text, lanes, dropped } = rewriteRegions(workflow, scoped, only, shardMap);
    // REFUSE TO SILENTLY DELETE A STEP THE MANIFEST STILL POINTS AT. A step inside the region that no declared gate emits is either stale (fine to drop) or a gate someone hand-added in the wrong place (NOT fine -- dropping it stops that gate running in CI). The manifest is the arbiter: if it names the step, the removal is a regression and this refuses rather than reporting a tidy
    // "rewrote N region(s)". Keyed by the JOB the gate was PLACED in, which is byLane's key -- not b.lane, which is the optional header override and is undefined for most gates. Keying on it made every emitted step look like an unexplained removal.
    const emitted = new Set(
      [...scoped.entries()].flatMap(([lane, gates]) => gates.map((b) => `${lane}: ${b.step}`))
    );
    // THE STRIP GUARD (box A2). The refusal below catches a drop the MANIFEST still names, which is the loudest case. It is not the only harmful one, and the gap has a receipt: strip `DOCKERHUB_TOKEN` from `.github/workflows/ci-quality.yml:1159` in a scratch copy and run the whole battery -- NOTHING reds. A step can carry `env:`, `if:`, a `with:` block or a secret that no manifest
    // entry mentions, and dropping it was reported as a tidy `rewrote N region(s)`.
    //
    // So `--write` now refuses on ANY drop the rewrite cannot re-emit, whatever the reason, and `--allow-drop <step>` is the single typed escape. The two refusals stay SEPARATE rather than merged: a manifest-claimed drop is a regression and says so,
    // while an unexplained drop may be legitimate cleanup that simply has to be named.
    const { claimed, unclaimed } = classifyDrops(dropped, emitted, allowDrop, manifest);
    if (unclaimed.length > 0) {
      console.error(`✗ refusing to write: ${unclaimed.length} step(s) would be REMOVED from a`);
      console.error('  region and re-emitted by nothing.');
      for (const c of unclaimed) console.error(`    ${c}`);
      console.error('');
      console.error('  A dropped step takes its `env:`, `if:`, `with:` and secrets with it, and');
      console.error('  no gate reads those, so the removal would be invisible: measured by');
      console.error('  stripping DOCKERHUB_TOKEN from ci-quality.yml and running the whole');
      console.error('  battery green. If the removal is intended, name it:');
      for (const c of unclaimed) {
        console.error(
          `    npx tsx scripts/gate-bind.ts --write --allow-drop '${c.slice(c.indexOf(': ') + 2)}'`
        );
      }
      process.exit(1);
    }
    if (claimed.length > 0) {
      console.error(`✗ refusing to write: ${claimed.length} step(s) inside a region are`);
      console.error('  registered in the manifest but emitted by no declared gate.');
      for (const c of claimed) console.error(`    ${c}`);
      console.error('');
      console.error('  Dropping them would stop those gates running in CI, and the only');
      console.error('  symptom would be check:ci-parity one gate later. Move them BELOW');
      console.error('  the `# <<< gate-bind` marker, where a hand-registered step belongs.');
      process.exit(1);
    }
    // EVERY LANE WITH GATES MUST HAVE A REGION. Emitting into a file that has none would silently drop the step and report success -- the vacuity shape again. THE REGION IS THE OPT-IN, which is what makes a STAGED cutover expressible.
    //
    // This used to refuse outright unless EVERY lane holding a declared gate had a region. That sounds protective and is not: 46 gates across five lanes declare headers while still being hand-registered, so `--write` refused repo-wide and no lane could go first. All-or-nothing across five lanes, each with its own step-ordering constraints, is the opposite of the one-lane pilot a
    // cutover needs.
    //
    // A lane with no region does not emit, and its gates keep running from their hand-written steps -- a state the verify path already checks per gate, since `stepInJob` demands the step exist whether a region wrote it or not. What the old refusal actually guarded, a region silently losing its steps, is caught anyway: delete a region and check:ci-parity reds on a manifest entry
    // naming a step that is no longer in the file.
    const notYet = [...scoped.keys()].filter((j) => !lanes.includes(j));
    if (notYet.length > 0) {
      console.log(
        `note: ${notYet.length} lane(s) hold declared gates and no \`# >>> gate-bind\` region, ` +
          'so those gates stay hand-registered until one is placed:'
      );
      for (const j of notYet) {
        console.log(`    ${j}: ${(scoped.get(j) ?? []).length} declared gate(s)`);
      }
      console.log(
        "  Place it after that lane's PREREQUISITE steps, not merely after `- id: setup`."
      );
      console.log(
        '  quality-www-build builds www first and check-landmarks.ts:89 refuses without dist/.'
      );
    }
    if (text === workflow) {
      console.log(`gate-bind --write: ${WORKFLOW} already matches (${declared.length} gate(s))`);
      return;
    }
    if (dryRun) {
      const before = workflow.split('\n').length;
      const after = text.split('\n').length;
      console.log(
        `gate-bind --dry-run: WOULD rewrite ${lanes.length} region(s) in ${WORKFLOW} ` +
          `(${before} lines -> ${after}). Nothing written.`
      );
      console.log(
        `  ${[...scoped.entries()].map(([l, g]) => `${l}: ${g.length}`).join(', ')} step(s) emitted.`
      );
      console.log('  Any of those whose hand-written copy still exists becomes a DUPLICATE until');
      console.log('  that copy is deleted. Run `check:ci-gate-bind` after writing.');
      return;
    }
    fs.writeFileSync(path.join(ROOT, WORKFLOW), text);
    console.log(`gate-bind --write: rewrote ${lanes.length} region(s) in ${WORKFLOW}`);
    return;
  }

  const problems: string[] = [];
  for (const b of declared) {
    // A GATE-TEST IS REGISTERED DIFFERENTLY, AND ITS ABSENCE FROM package.json IS THE RULE RATHER THAN THE DEFECT. check-gate-id-convention.sh requires a gate-test to be registered as `gate-test:<name>` whose `run` points at the script directly, with no
    // package.json entry at all: 148 keys that only ever restate a path would be 148 keys
    // against the package key budget for nothing. Checking these against package.json would therefore red all 148 the moment they became subjects, for a reason that has nothing to do with their headers. The lock's `run` is what they must agree with. THE PREDICATE IS "DOES THE LOCK RUN THIS SCRIPT DIRECTLY", not "is it flagged a gate-test". Those are the same set for the 148 under
    // .ci/scripts/test/gates, and they diverge for `test:install-script` and `test:write-once-guard`, which are registered exactly the same way (run: the .sh path, no package.json key) and carry no `qualityGateTest`. Keying on the flag refused both the moment they declared a header on 2026-09-06, for a convention they follow correctly.
    const lockEntry = lockById.get(b.id);
    const runsScriptDirectly =
      lockEntry !== undefined &&
      !lockEntry.run.startsWith('npm run ') &&
      // `.py` TOO, and for the W7 P4 reason. A gate registered as a bare path with no package.json key keeps that shape when its path is repointed at a Python port; keying on `.sh` alone meant the checks below -- run must match the header's derived run, and no package.json key may exist -- silently stopped applying to a gate the moment it was ported. Same class as the `paths:`
      // glob that stops selecting its own gate once the leaf is a `.py`.
      (lockEntry.run.endsWith('.sh') || lockEntry.run.endsWith('.py'));
    if (lockEntry?.qualityGateTest === true || runsScriptDirectly) {
      if (lockEntry.run !== b.run) {
        problems.push(
          `${b.file}: gates.lock.json runs "${lockEntry.run}" but its header derives "${b.run}"`
        );
      }
      if (pkg.scripts[b.id] !== undefined) {
        problems.push(
          `${b.file}: is a gate-test, so it must have NO package.json script, but ` +
            `'${b.id}' is registered there as "${pkg.scripts[b.id]}"`
        );
      }
    } else if (pkg.scripts[b.id] === undefined) {
      problems.push(`${b.file}: declares id '${b.id}', which package.json has no script for`);
    } else if (pkg.scripts[b.id] !== b.run) {
      problems.push(
        `${b.file}: package.json runs "${pkg.scripts[b.id]}" but its header derives "${b.run}"`
      );
    }

    const entry = new RegExp(`id: '${b.id.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}'`).test(
      manifest
    );
    if (!entry) problems.push(`${b.file}: no manifest entry with id '${b.id}'`);

    // WHERE THIS GATE ACTUALLY RUNS. For `step` and the two stepless kinds that is what placement derives from `needs`. For `battery` it is a FACT OF THE WORKFLOW: the job holding the step it rides. Deriving it from needs instead would check a lane the gate never enters, and pass.
    let job: string;
    if (b.kind === 'battery') {
      const owners = jobsWithStep(workflow, b.step as string);
      if (owners.length !== 1) {
        problems.push(
          `${b.file}: kind battery rides step "${b.step}", which ${WORKFLOW} has in ` +
            `${owners.length} job(s) (${owners.join(', ') || 'none'}). A battery step must ` +
            'exist exactly once, or "the lane it runs in" has no answer.'
        );
        continue;
      }
      job = owners[0];
      if (b.lane !== undefined && b.lane !== job) {
        problems.push(
          `${b.file}: pins lane '${b.lane}' but its battery step "${b.step}" lives in '${job}'`
        );
        continue;
      }
    } else {
      const placed = placeGate(caps, b.needs);
      job = b.lane ?? ('lane' in placed ? placed.lane : '');
      if (job === '') {
        problems.push(`${b.file}: ${'error' in placed ? placed.error : 'no lane'}`);
        continue;
      }
    }
    const lane = caps.get(job);
    if (lane === undefined) {
      problems.push(`${b.file}: pinned lane '${job}' is not a job of ${WORKFLOW}`);
      continue;
    }
    if (!satisfies(lane, b.needs)) {
      problems.push(`${b.file}: lane '${job}' does not provide all of ${JSON.stringify(b.needs)}`);
    }
    // A NON-EMITTING GATE IS CHECKED UP TO HERE AND NO FURTHER, and each of the three remaining checks says why. They are all statements about a region this gate is never written into, so applying them to a battery gate reports a defect in a step somebody else owns -- the shape that produced six false lane mismatches during the drain, once per gate, for one hand-written step.
    if (!emits(b)) continue;
    if (!regionAfterSetup(workflow, job)) {
      problems.push(
        `${b.file}: job '${job}' has its \`# >>> gate-bind\` region ABOVE its \`- id: setup\` ` +
          "step, so every emitted step's `steps.setup.outcome` guard is empty and they all skip"
      );
    }
    const step = b.step as string;
    const copies = stepCountInJob(workflow, job, step);
    if (copies > 1) {
      problems.push(
        `${b.file}: job '${job}' has ${copies} steps named "${step}" -- the emitted one ` +
          'and a hand-written leftover. Delete the hand-written copy; the region owns it now.'
      );
    }
    if (!stepInJob(workflow, job, step)) {
      problems.push(`${b.file}: ${WORKFLOW} job '${job}' has no step named "${step}"`);
    }
  }

  // BELT AND BRACES, AND IT CAN NO LONGER FIRE. A malformed block now refuses above, before the write branch, so `malformed` is always empty by here. The line stays because the refusal above is the load-bearing one and this is the safety net if the two are ever reordered; it is annotated rather than deleted so nobody reads it as the check that catches malformed headers. It is not.
  problems.push(...malformed);

  if (problems.length > 0) {
    console.error(`✗ ${problems.length} binding problem(s):`);
    for (const p of problems) console.error(`    ${p}`);
    for (const line of [
      '',
      '  A gate declares its step and its needs in its own header; the id, the run',
      '  command and the lane are derived. When they disagree with what is registered,',
      '  the registration is what drifted -- fix it there, or correct the header.',
    ]) {
      console.error(line);
    }
    process.exit(1);
  }

  console.log(
    `✓ gate binding: ${declared.length} declared gate(s), each matching its package.json ` +
      'script, its manifest entry, and a workflow step in a lane that provides its needs'
  );
  console.log(
    '  Blind spot: this checks the gates that DECLARE a header. The rest are still ' +
      'registered by hand and are check:ci-parity’s business until the drain reaches them.'
  );
}

/**
 * THE IMPORT GUARD.
 *
 * Until now this line ran unconditionally, so `import { bind } from './gate-bind.js'`
 * executed the entire binder: it scanned the tree, printed a verdict, and could
 * `process.exit(1)` inside whatever was importing it. Found by writing a five-line probe
 * that imported `bind` -- the probe's own output was 40 lines of someone else's selftest,
 * and a probe that had asserted anything would have died on the exit before reporting.
 *
 * W2.1's `gates.lock.json` generator and W2.2's shadow-gate core both import from here,
 * and neither can be written while importing the module means running the CLI.
 *
 * `process.argv[1]` is the entry script; comparing its resolved path to this module's own
 * answers "was I run, or was I loaded" without depending on a bundler or a Node version
 * (`import.meta.main` is not available under the tsx/CJS path this repo runs gates on).
 */
const invokedDirectly = (): boolean => {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  return path.resolve(entry) === path.resolve(fileURLToPath(import.meta.url));
};

if (invokedDirectly()) main(process.argv.slice(2));
