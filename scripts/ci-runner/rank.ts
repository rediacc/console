/**
 * THE LEARNED ORDER (agent/plans/PLAN-gate-scheduling-learned.md section 5): which gates start first, from what the outcome ledger has seen, so a cheap red is found in the first minutes rather than the last.
 *
 * PURE, AND IT NAMES NO GATE. Every decision here is derived from `model.json` (written by `.ci/rediacc_ci/ci/gate_model.py`, contract v1 in the plan's section 9), the gate lock's declared inputs and the diff. A gate id written into this file would be a static list, which the plan forbids; the runner's selftest (`learnedSelftest`, T9) reads this file and fails on any id the lock declares.
 *
 * WHAT IT RETURNS: {pinned, preflight, stage1, value}. The pool (pool.ts `planAdmission`) ranks pinned gates first by today's priority, then preflight in its admission order, then everything else by value = p_red / max(wall, 1 s), with today's priority breaking ties. Ordering only: the selected set is never changed, so a full receipt still runs every gate.
 *
 * WALL IS NEVER LENGTHENED. `planRanking` simulates today's order and the proposed one through the pool's own admission rule (sim.ts `predictMakespan`); when the proposal is more than WALL_SLACK_MS slower it pins the gate whose start moved latest and simulates again, up to PIN_ITERATIONS times, and otherwise turns ranking OFF for the run and says by how much.
 *
 * COLD START. Fewer than MIN_LEDGER_RUNS whole runs in the model, or fewer than MIN_COVERAGE of the selected gates with MIN_GATE_OBS observations: ranking is OFF, today's order runs, and the reason is printed. A gate thin on data takes a Beta prior at the model's global red rate.
 */
import { GLOBAL_INPUTS, matchGlob } from './input-hash';
import type { ScheduleOrder } from './pool';

// ---------------------------------------------------------------- tunables (plan section 8)

/** About one working day of pre-push runs (2026-10-08 had 11); below it the model has not seen a normal day. */
const MIN_LEDGER_RUNS = 8;
/** Below 5 observations a gate's recency-weighted rate is noise. */
const MIN_GATE_OBS = 5;
/** At least half the selected gates must clear MIN_GATE_OBS, or the order is mostly prior. */
const MIN_COVERAGE = 0.5;
/** The brief's 2-minute cap on preflight. */
const PREFLIGHT_TARGET_MS = 120_000;
/** Admits a 63 s dependency-freshness gate; a gate longer than this cannot share the 2-minute cap. */
const PREFLIGHT_MAX_GATE_MS = 90_000;
/** 2026-10-08's long gates were at least 0.30 of T*, the next tier 0.14: 0.25 separates the two. */
const LONG_FRACTION = 0.25;
/** The simulation is deterministic, so one second covers rounding and nothing else. */
export const WALL_SLACK_MS = 1000;
/** Bounds the safety search: five pins and the order is no longer a learned order. */
const PIN_ITERATIONS = 5;
/** Stage 1 should hold most of the expected reds. */
const STAGE1_MASS = 0.9;
/** A one-in-five association is worth a preflight slot under the 2-minute cap. */
export const ASSOC_MIN_P = 0.2;
/** The plan's "p_red / max(wall, 1 s)": a gate measured at a few ms would otherwise outrank everything on noise. */
const MIN_VALUE_WALL_MS = 1000;
/** The Beta prior's weight in pseudo-observations: MIN_GATE_OBS, so a gate's own rate outweighs the global rate exactly when it has enough observations to clear the coverage bar. */
const PRIOR_STRENGTH = MIN_GATE_OBS;

// ---------------------------------------------------------------- model.json v1

/** One gate's line in model.json v1. */
interface ModelGate {
  obs: number;
  p_red: number;
  p_red_by_class: Record<string, number>;
  wall_ms: number | null;
  class: string;
}

/** model.json v1 as the runner reads it. Fields the runner does not use (findings, companions) are not validated. */
export interface ModelV1 {
  v: 1;
  built_at: string;
  cold_start: { on: boolean; reason: string };
  runs: number;
  gates: Record<string, ModelGate>;
  clock_set: string[];
  clusters: string[][];
  associations: Record<string, Record<string, number>>;
}

const isObj = (x: unknown): x is Record<string, unknown> =>
  x !== null && typeof x === 'object' && !Array.isArray(x);
const isProb = (x: unknown): x is number =>
  typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= 1;
const isStrList = (x: unknown): x is string[] =>
  Array.isArray(x) && x.every((s) => typeof s === 'string');

/** model.json's text parsed against contract v1, or the sentence saying why it cannot be used. A malformed model turns ranking off; it never fails the run. */
export function parseModel(text: string): { model: ModelV1 } | { error: string } {
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch (e) {
    return { error: `model.json is not JSON (${(e as Error).message})` };
  }
  if (!isObj(doc)) return { error: 'model.json is not an object' };
  if (doc.v !== 1) return { error: `model.json is v${String(doc.v)}; this runner reads v1` };
  const cs = doc.cold_start;
  if (!isObj(cs) || typeof cs.on !== 'boolean')
    return { error: 'model.json has no cold_start {on, reason}' };
  if (typeof doc.runs !== 'number' || !Number.isFinite(doc.runs))
    return { error: 'model.json has no numeric runs' };
  if (!isObj(doc.gates)) return { error: 'model.json has no gates object' };
  const gates: Record<string, ModelGate> = {};
  for (const [id, raw] of Object.entries(doc.gates)) {
    if (!isObj(raw) || typeof raw.obs !== 'number' || !isProb(raw.p_red))
      return { error: `model.json gates[${id}] needs numeric obs and p_red in [0, 1]` };
    const byClass: Record<string, number> = {};
    if (isObj(raw.p_red_by_class))
      for (const [c, p] of Object.entries(raw.p_red_by_class)) if (isProb(p)) byClass[c] = p;
    gates[id] = {
      obs: Math.max(0, raw.obs),
      p_red: raw.p_red,
      p_red_by_class: byClass,
      wall_ms:
        typeof raw.wall_ms === 'number' && Number.isFinite(raw.wall_ms) && raw.wall_ms >= 0
          ? raw.wall_ms
          : null,
      class: typeof raw.class === 'string' ? raw.class : 'none',
    };
  }
  const associations: Record<string, Record<string, number>> = {};
  if (isObj(doc.associations))
    for (const [c, row] of Object.entries(doc.associations)) {
      if (!isObj(row)) continue;
      associations[c] = {};
      for (const [id, p] of Object.entries(row)) if (isProb(p)) associations[c][id] = p;
    }
  return {
    model: {
      v: 1,
      built_at: typeof doc.built_at === 'string' ? doc.built_at : '',
      cold_start: { on: cs.on, reason: typeof cs.reason === 'string' ? cs.reason : '' },
      runs: doc.runs,
      gates,
      clock_set: isStrList(doc.clock_set) ? doc.clock_set : [],
      clusters: Array.isArray(doc.clusters) ? doc.clusters.filter(isStrList) : [],
      associations,
    },
  };
}

// ---------------------------------------------------------------- path classes (plan section 2)

/** What the lock contributes to the anchors; a structural subset of a gates.lock.json entry. */
export interface AnchorSource {
  paths?: readonly string[];
  leaves?: readonly string[];
  ci?: { kind?: string; test?: string };
}

/** One anchor as gate_model.py's `Anchor`: its name (the class it names), whether it is a glob, and its weight, the name's length with a trailing `/**` dropped, so the most specific anchor wins. */
export interface Anchor {
  name: string;
  glob: boolean;
  weight: number;
}

/**
 * The anchors, gate_model.py `anchors` exactly: every declared `paths` entry, every leaf that names a repo file (it holds a `/` and `isFile` says so; a command leaf does not), every `ci.test` path, and GLOBAL_INPUTS; sorted heaviest first, ties by name. The class a file falls in therefore means the same thing here and in model.json's `associations` and `p_red_by_class` keys.
 */
export function anchorsFrom(
  lock: readonly AnchorSource[],
  isFile: (rel: string) => boolean
): Anchor[] {
  const out = new Map<string, Anchor>();
  const add = (name: string): void => {
    if (name === '' || out.has(name)) return;
    out.set(name, {
      name,
      glob: name.includes('*'),
      weight: (name.endsWith('/**') ? name.slice(0, -3) : name).length,
    });
  };
  for (const e of lock) {
    for (const g of e.paths ?? []) add(g);
    for (const l of e.leaves ?? []) if (l.includes('/') && isFile(l)) add(l);
    if (typeof e.ci?.test === 'string') add(e.ci.test);
  }
  for (const g of GLOBAL_INPUTS) add(g);
  return [...out.values()].sort(
    (a, b) => b.weight - a.weight || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
  );
}

/** One changed file's class, gate_model.py `path_class`: the first anchor in weight order that matches (a glob by the input-hash grammar, `**` any run with `/` and `*` any run without; anything else by equality), else `~<first two path segments>`. */
export function classOf(file: string, anchors: readonly Anchor[]): string {
  for (const a of anchors) if (a.glob ? matchGlob(a.name, file) : file === a.name) return a.name;
  return `~${file.split('/').slice(0, 2).join('/')}`;
}

/** The diff's classes, sorted and deduplicated. */
export function classesOf(files: readonly string[], anchors: readonly Anchor[]): string[] {
  return [...new Set(files.map((f) => classOf(f, anchors)))].sort(
    (a, b) => Number(a > b) - Number(a < b)
  );
}

// ---------------------------------------------------------------- cold start and probabilities

/** Whether the model may order this run, and why not. */
export function coldStart(
  model: ModelV1,
  selectedGates: readonly string[]
): { on: true } | { on: false; reason: string } {
  if (model.cold_start.on)
    return { on: false, reason: `cold start (model: ${model.cold_start.reason || 'no reason'})` };
  if (model.runs < MIN_LEDGER_RUNS)
    return {
      on: false,
      reason: `cold start: the ledger holds ${model.runs} whole run(s), fewer than ${MIN_LEDGER_RUNS}`,
    };
  if (selectedGates.length === 0) return { on: false, reason: 'no gate selected' };
  const covered = selectedGates.filter((id) => (model.gates[id]?.obs ?? 0) >= MIN_GATE_OBS).length;
  if (covered / selectedGates.length < MIN_COVERAGE)
    return {
      on: false,
      reason: `cold start: ${covered} of ${selectedGates.length} selected gate(s) have >= ${MIN_GATE_OBS} observations, under ${Math.round(MIN_COVERAGE * 100)}%`,
    };
  return { on: true };
}

/** The global red rate the Beta prior centres on: observations-weighted mean of every gate's p_red. */
function globalRate(model: ModelV1): number {
  let reds = 0;
  let obs = 0;
  for (const g of Object.values(model.gates)) {
    reds += g.p_red * g.obs;
    obs += g.obs;
  }
  return obs > 0 ? reds / obs : 0;
}

/** p_red for one gate on this diff: its own rate under the Beta prior, raised to the strongest class-conditioned rate or association the diff's classes carry. */
function pRed(model: ModelV1, id: string, classes: readonly string[], prior: number): number {
  const g = model.gates[id];
  const own =
    g === undefined ? prior : (g.p_red * g.obs + prior * PRIOR_STRENGTH) / (g.obs + PRIOR_STRENGTH);
  let p = own;
  for (const c of classes) {
    p = Math.max(p, g?.p_red_by_class[c] ?? 0, model.associations[c]?.[id] ?? 0);
  }
  return p;
}

// ---------------------------------------------------------------- the order

/** What the order is built from; every field is about the graph this run schedules. */
export interface RankInput {
  model: ModelV1;
  /** Every node of the graph, gates and prerequisites, in manifest order. */
  ids: readonly string[];
  /** The nodes that are gates (`gate: true`); a prerequisite carries no p_red of its own. */
  gates: ReadonlySet<string>;
  /** `needs` within the graph. */
  needs: ReadonlyMap<string, readonly string[]>;
  /** Exclusive claims (`mutex`); holders run one after another. */
  mutex: ReadonlyMap<string, readonly string[]>;
  /** The planning wall, ms: this machine's timing or the CI step p90. Undefined when unknown, which the model's own wall then stands in for. */
  wallMs: (id: string) => number | undefined;
  /** Cores the gate takes at launch, for the cores free at t = 0. */
  width: (id: string) => number;
  /** The core budget C. */
  cores: number;
  /** The diff's classes (`classesOf`). */
  classes: readonly string[];
  /** T*: today's order, simulated. */
  makespanMs: number;
}

/** The learned order plus what the stream reports: stage 1 and each gate's p_red. */
export interface RankOrder extends ScheduleOrder {
  stage1: readonly string[];
  pRed: ReadonlyMap<string, number>;
}

/** The plan's LPT makespan: each wall onto the least-loaded of k cores, longest first. */
function lptMs(walls: readonly number[], k: number): number {
  const loads = new Array<number>(Math.max(1, Math.floor(k))).fill(0);
  for (const w of [...walls].sort((a, b) => b - a)) {
    let i = 0;
    for (let j = 1; j < loads.length; j += 1) if (loads[j] < loads[i]) i = j;
    loads[i] += w;
  }
  return Math.max(...loads);
}

/** Build the order. `extraPins` are the safety search's pins on top of the long-gate rule; `longPins` false turns that rule off (the property test's control only). */
export function buildOrder(
  input: RankInput,
  extraPins: ReadonlySet<string> = new Set(),
  longPins = true
): RankOrder {
  const { model, ids, gates, needs } = input;
  const prior = globalRate(model);
  const wall = (id: string): number | undefined =>
    input.wallMs(id) ?? model.gates[id]?.wall_ms ?? undefined;
  const w0 = (id: string): number => wall(id) ?? 0;

  // Chains: up = longest `needs` path ending at a node, down = longest starting at it (both including the node), so a node sits on a chain of up + down - own.
  const dependents = new Map<string, string[]>();
  for (const id of ids)
    for (const n of needs.get(id) ?? []) dependents.set(n, [...(dependents.get(n) ?? []), id]);
  const memoUp = new Map<string, number>();
  const memoDown = new Map<string, number>();
  const up = (id: string, seen = new Set<string>()): number => {
    const hit = memoUp.get(id);
    if (hit !== undefined) return hit;
    if (seen.has(id)) return w0(id);
    seen.add(id);
    let best = 0;
    for (const n of needs.get(id) ?? []) best = Math.max(best, up(n, seen));
    const v = best + w0(id);
    memoUp.set(id, v);
    return v;
  };
  const down = (id: string, seen = new Set<string>()): number => {
    const hit = memoDown.get(id);
    if (hit !== undefined) return hit;
    if (seen.has(id)) return w0(id);
    seen.add(id);
    let best = 0;
    for (const d of dependents.get(id) ?? []) best = Math.max(best, down(d, seen));
    const v = best + w0(id);
    memoDown.set(id, v);
    return v;
  };
  const serial = new Map<string, number>();
  for (const id of ids)
    for (const r of input.mutex.get(id) ?? []) serial.set(r, (serial.get(r) ?? 0) + w0(id));
  const threshold = LONG_FRACTION * input.makespanMs;
  const pinned = new Set<string>(extraPins);
  for (const id of ids) {
    const chain = up(id) + down(id) - w0(id);
    let group = 0;
    for (const r of input.mutex.get(id) ?? []) group = Math.max(group, serial.get(r) ?? 0);
    if (longPins && Math.max(w0(id), chain, group) >= threshold && threshold > 0) pinned.add(id);
  }

  // Value: p_red / max(wall, 1 s); a prerequisite takes the largest value among the gates that need it, transitively, so it is never what holds a high-value gate back.
  const p = new Map<string, number>();
  const value = new Map<string, number>();
  for (const id of ids) {
    const pr = gates.has(id) ? pRed(model, id, input.classes, prior) : 0;
    p.set(id, pr);
    value.set(id, pr / Math.max(w0(id), MIN_VALUE_WALL_MS));
  }
  const lifted = new Map<string, number>();
  const lift = (id: string, seen = new Set<string>()): number => {
    const hit = lifted.get(id);
    if (hit !== undefined) return hit;
    if (seen.has(id)) return value.get(id) ?? 0;
    seen.add(id);
    let v = value.get(id) ?? 0;
    for (const d of dependents.get(id) ?? []) v = Math.max(v, lift(d, seen));
    lifted.set(id, v);
    return v;
  };
  for (const id of ids) lifted.set(id, lift(id));
  const byValue = (a: string, b: string): number =>
    (lifted.get(b) ?? 0) - (lifted.get(a) ?? 0) || ids.indexOf(a) - ids.indexOf(b);

  // Preflight: the clock set plus the change-associated gates, admitted by value while the LPT makespan on the cores free at t = 0 stays under the target. A gate that waits on another, has no wall estimate, or is longer than PREFLIGHT_MAX_GATE_MS is never preflight.
  const associated = new Set<string>();
  for (const c of input.classes)
    for (const [id, pa] of Object.entries(model.associations[c] ?? {}))
      if (pa >= ASSOC_MIN_P) associated.add(id);
  const inGraph = new Set(ids);
  const candidates = [...new Set([...model.clock_set, ...associated])]
    .filter(
      (id) =>
        inGraph.has(id) &&
        gates.has(id) &&
        !pinned.has(id) &&
        (needs.get(id) ?? []).length === 0 &&
        wall(id) !== undefined &&
        w0(id) <= PREFLIGHT_MAX_GATE_MS
    )
    .sort(byValue);
  let pinnedWidth = 0;
  for (const id of pinned) if (inGraph.has(id)) pinnedWidth += input.width(id);
  const freeCores = Math.max(1, Math.floor(input.cores - pinnedWidth));
  const preflight: string[] = [];
  for (const id of candidates) {
    const trial = [...preflight, id];
    if (lptMs(trial.map(w0), freeCores) <= PREFLIGHT_TARGET_MS) preflight.push(id);
  }

  // Stage 1: the next gates by value until STAGE1_MASS of the unpinned gates' total p_red is covered, preflight's included.
  const unpinnedGates = ids.filter((id) => gates.has(id) && !pinned.has(id));
  const total = unpinnedGates.reduce((s, id) => s + (p.get(id) ?? 0), 0);
  let mass = preflight.reduce((s, id) => s + (p.get(id) ?? 0), 0);
  const stage1: string[] = [];
  const inPreflight = new Set(preflight);
  for (const id of [...unpinnedGates].sort(byValue)) {
    if (total <= 0 || mass >= STAGE1_MASS * total) break;
    if (inPreflight.has(id)) continue;
    stage1.push(id);
    mass += p.get(id) ?? 0;
  }
  return { pinned, preflight, stage1, value: lifted, pRed: p };
}

/** What a simulation of one order reports: its makespan and each gate's start, ms. */
export interface SimOutcome {
  makespanMs: number;
  starts: ReadonlyMap<string, number>;
}

/** The run's ranking decision, printed in the header and the run-start event. */
export type RankingDecision =
  | {
      on: true;
      order: RankOrder;
      baseMs: number;
      rankedMs: number;
      /** Gates the safety search pinned beyond the long-gate rule. */
      pinsAdded: string[];
    }
  | { on: false; reason: string; baseMs?: number; rankedMs?: number };

/**
 * THE SAFETY CHECK. Simulate today's order (T*), build the learned order against it, and simulate that; while it is more than `slackMs` slower, pin the gate whose simulated start moved latest against today's and simulate again, at most `iterations` times. Still slower: ranking OFF with the simulated difference. `iterations` 0 with `longPins` false is the control that shows an unpinned order can be slower.
 */
export function planRanking(
  input: Omit<RankInput, 'makespanMs'>,
  simulate: (order: RankOrder | undefined) => SimOutcome,
  opts: { slackMs?: number; iterations?: number; longPins?: boolean } = {}
): RankingDecision {
  const slack = opts.slackMs ?? WALL_SLACK_MS;
  const iterations = opts.iterations ?? PIN_ITERATIONS;
  const longPins = opts.longPins ?? true;
  const base = simulate(undefined);
  const full: RankInput = { ...input, makespanMs: base.makespanMs };
  const pins = new Set<string>();
  let order = buildOrder(full, pins, longPins);
  let ranked = simulate(order);
  for (let i = 0; i < iterations && ranked.makespanMs > base.makespanMs + slack; i += 1) {
    let worst: string | undefined;
    let moved = 0;
    for (const id of input.ids) {
      if (order.pinned.has(id)) continue;
      const delta = (ranked.starts.get(id) ?? 0) - (base.starts.get(id) ?? 0);
      if (delta > moved) {
        moved = delta;
        worst = id;
      }
    }
    if (worst === undefined) break;
    pins.add(worst);
    order = buildOrder(full, pins, longPins);
    ranked = simulate(order);
  }
  if (ranked.makespanMs > base.makespanMs + slack)
    return {
      on: false,
      reason: `simulated +${Math.round((ranked.makespanMs - base.makespanMs) / 1000)}s`,
      baseMs: base.makespanMs,
      rankedMs: ranked.makespanMs,
    };
  return {
    on: true,
    order,
    baseMs: base.makespanMs,
    rankedMs: ranked.makespanMs,
    pinsAdded: [...pins],
  };
}

// ---------------------------------------------------------------- selftest

/** The module's controls, each with its opposite, run from run.ts --selftest. Fixture ids only. */
export function rankSelftest(): { failures: string[]; assertions: number } {
  const failures: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };
  const gate = (obs: number, pr: number, wall: number, byClass: Record<string, number> = {}) => ({
    obs,
    p_red: pr,
    p_red_by_class: byClass,
    wall_ms: wall,
    class: 'real',
  });
  const doc = {
    v: 1,
    built_at: '2026-10-08T00:00:00Z',
    cold_start: { on: false, reason: '' },
    runs: 20,
    gates: {
      'fx:long': gate(20, 0.01, 900_000),
      'fx:cheap-red': gate(20, 0.6, 1_000),
      'fx:clock': gate(20, 0.3, 2_000),
      'fx:mid': gate(20, 0.05, 30_000),
      'fx:quiet': gate(20, 0.0, 5_000),
      'fx:assoc': gate(20, 0.01, 4_000),
    },
    clock_set: ['fx:clock', 'fx:not-selected'],
    clusters: [['fx:cheap-red', 'fx:mid']],
    associations: { 'src/lib': { 'fx:assoc': 0.5 } },
    companions: [],
  };
  const parsed = parseModel(JSON.stringify(doc));
  check('model' in parsed, `a v1 model must parse, got ${JSON.stringify(parsed)}`);
  check(
    'error' in parseModel(JSON.stringify({ ...doc, v: 2 })),
    'CONTROL: a v2 model must be refused, not read as v1'
  );
  check('error' in parseModel('{'), 'CONTROL: a torn model.json must be refused');
  if (!('model' in parsed)) return { failures, assertions };
  const model = parsed.model;

  // PATH CLASSES, as gate_model.py derives them: the heaviest matching anchor names the class by its own text, a non-glob anchor matches only itself, an unmatched file is ~<two segments>.
  const anchors = anchorsFrom(
    [
      {
        paths: ['src/**', 'src/lib/**', 'docs/one.md'],
        leaves: ['scripts/gate.ts', 'tool', 'top.ts'],
      },
      { ci: { kind: 'step', test: 'tests/test_x.py' } },
    ],
    () => true
  );
  const names = anchors.map((a) => a.name);
  check(
    names.includes('src/lib/**') &&
      names.includes('scripts/gate.ts') &&
      !names.includes('tool') &&
      !names.includes('top.ts') &&
      names.includes('tests/test_x.py'),
    `anchors must keep globs as written, file leaves with a /, every ci.test, and drop a leaf without one, got ${names.join(',')}`
  );
  check(
    classOf('src/lib/a.ts', anchors) === 'src/lib/**',
    'the HEAVIEST matching anchor names the class, as written'
  );
  check(
    classOf('src/b.ts', anchors) === 'src/**',
    'CONTROL: a file outside the heavier anchor takes the lighter'
  );
  check(
    classOf('docs/one.md', anchors) === 'docs/one.md',
    'a non-glob anchor matches its own path'
  );
  check(
    classOf('docs/one.md/x', anchors) === '~docs/one.md',
    'CONTROL: a non-glob anchor is not a directory prefix'
  );
  check(
    classOf('docs/agent-reference/x.md', anchors) === '~docs/agent-reference',
    'an unmatched file is ~<first two segments>'
  );
  check(
    classOf('pkg/a/package-lock.json', anchors) === '**/package-lock.json',
    'a GLOBAL_INPUTS glob anchors by the input-hash glob grammar'
  );

  // COLD START, both directions.
  const ids = Object.keys(doc.gates);
  check(coldStart(model, ids).on, 'a model of 20 runs covering every gate must rank');
  check(
    !coldStart({ ...model, runs: 3 }, ids).on,
    'CONTROL: 3 runs is a cold start, under MIN_LEDGER_RUNS'
  );
  check(
    !coldStart({ ...model, gates: { 'fx:long': model.gates['fx:long'] } }, ids).on,
    'CONTROL: 1 of 6 gates observed is under MIN_COVERAGE'
  );
  check(
    !coldStart({ ...model, cold_start: { on: true, reason: 'fixture' } }, ids).on,
    "CONTROL: the model's own cold_start flag turns ranking off"
  );

  // THE ORDER: the long gate is pinned, the clock gate and the associated gate are preflight, the cheap red leads stage 1, the quiet gate is in neither.
  const unsized: Omit<RankInput, 'makespanMs'> = {
    model,
    ids,
    gates: new Set(ids),
    needs: new Map(),
    mutex: new Map(),
    wallMs: () => undefined,
    width: () => 1,
    cores: 4,
    classes: ['src/lib'],
  };
  const input: RankInput = { ...unsized, makespanMs: 900_000 };
  const order = buildOrder(input);
  check(
    order.pinned.has('fx:long') && order.pinned.size === 1,
    `only the long gate pins, got ${[...order.pinned].join(',')}`
  );
  check(
    order.preflight.includes('fx:clock') && order.preflight.includes('fx:assoc'),
    `the clock set and the change-associated gate must be preflight, got ${order.preflight.join(',')}`
  );
  check(
    !order.preflight.includes('fx:not-selected'),
    'a clock gate outside the graph is never preflight'
  );
  check(
    order.stage1[0] === 'fx:cheap-red',
    `the cheap red must lead stage 1, got ${order.stage1.join(',')}`
  );
  check(!order.stage1.includes('fx:quiet'), 'a gate with no expected reds stays out of stage 1');
  const noClass = buildOrder({ ...input, classes: [] });
  check(
    !noClass.preflight.includes('fx:assoc'),
    'CONTROL: with no associated class in the diff the associated gate is not preflight'
  );
  // The Beta prior: an unobserved gate takes the global rate, never zero.
  const thin = buildOrder({
    ...input,
    ids: [...ids, 'fx:new'],
    gates: new Set([...ids, 'fx:new']),
  });
  check(
    (thin.pRed.get('fx:new') ?? 0) > 0,
    'an unobserved gate must take the Beta prior, not zero'
  );
  // A prerequisite inherits the value of the gate that needs it.
  const prereq = buildOrder({
    ...input,
    ids: [...ids, 'fx:build'],
    gates: new Set(ids),
    needs: new Map([['fx:cheap-red', ['fx:build']]]),
  });
  check(
    (prereq.value.get('fx:build') ?? 0) === (prereq.value.get('fx:cheap-red') ?? -1),
    'a prerequisite must inherit the value of the gate that needs it'
  );
  check(
    !prereq.preflight.includes('fx:cheap-red'),
    'a gate waiting on a prerequisite is never preflight'
  );

  // THE SAFETY LOOP on a toy simulator: the run ends 200 s after the mid gate starts. Today's order starts it at 0; the learned order delays it 5 s until a pin moves it back (30 s is under LONG_FRACTION of 200 s, so the long-gate rule does not pin it first). With no pins allowed the order is OFF.
  const sim = (o: RankOrder | undefined): SimOutcome => {
    const midStart = o === undefined || o.pinned.has('fx:mid') ? 0 : 5_000;
    return {
      makespanMs: midStart + 200_000,
      starts: new Map([
        ['fx:mid', midStart],
        ['fx:quiet', 0],
      ]),
    };
  };
  const safeInput: Omit<RankInput, 'makespanMs'> = { ...unsized, ids: ['fx:mid', 'fx:quiet'] };
  const pinnedOn = planRanking(safeInput, sim);
  check(
    pinnedOn.on && pinnedOn.pinsAdded.includes('fx:mid'),
    `the safety loop must pin the gate whose start moved and keep ranking on, got ${JSON.stringify(pinnedOn.on ? pinnedOn.pinsAdded : pinnedOn)}`
  );
  const unpinned = planRanking(safeInput, sim, { iterations: 0 });
  check(
    !unpinned.on && /simulated \+5s/.test(unpinned.reason),
    `CONTROL: with no pins allowed the slower order must turn ranking OFF by its simulated delta, got ${JSON.stringify(unpinned)}`
  );
  return { failures, assertions };
}
