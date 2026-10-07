#!/usr/bin/env tsx
/**
 * `npm run shard:place -- <lane>`: put every unit a committed shard manifest
 * (`.ci/config/shards/<lane>.json`) is missing onto a leg, and drop every id that names no
 * unit, WITHOUT moving anything already placed.
 *
 * WHY THIS EXISTS. `check-shard-manifest-coverage.ts` reds a new test file that no leg names
 * ("runs in no CI job"), and until 2026-10-07 the only fix was a hand edit of a 600-line JSON
 * file, choosing a leg by eye (agent/reports/consolidation-investigation-2026-10-04.md
 * section 1: "nothing rebalances"). This is the verb that red now names.
 *
 * WHAT IT DOES, in order, and nothing else:
 *   1. enumerates the lane's units with the same `LANE_ENUMERATORS` entry the coverage gate
 *      and CI's shard plan use;
 *   2. drops every manifest id whose unit no longer exists (a phantom: a deleted file);
 *   3. groups the missing units into blocks that must share a leg: one enumerator `mutex`
 *      group (`shardPlan` merges a group into one unit, so two members on two legs is the
 *      race `.ci/rediacc_ci/xdist_groups.py` describes), one `together` rule from
 *      lane-durations.json's `rebalanceConstraints`, or a `needs` edge;
 *   4. sends a block whose group already has a home to that leg, and every other block,
 *      heaviest first, to the LIGHTEST allowed leg by the lane-durations estimate (a unit's
 *      p90 from `units`, else the lane's `defaultUnitMs`; a leg running N units at once,
 *      `unitParallelism`, costs max(serial / N, its largest mutex group), the arithmetic
 *      `check-lane-budget.ts` `parallelLegMs` applies);
 *   5. writes the file only when something changed. A run with nothing to place or drop
 *      leaves the file byte-identical, `generatedAt` included.
 * It is not a rebalance: placed ids never move. When the legs drift apart,
 * `npx tsx scripts/gates/check-lane-budget.ts --rebalance <lane> --write` re-plans the lane,
 * and `check-lane-budget.ts` stays the verdict on whether the result fits the budget.
 *
 * REFUSED LANES. `test-e2e-workers` (its manifest splits files into `#<bucket>` ids and its
 * legs are priced per distro: `check-lane-budget.ts --rebalance test-e2e-workers --write`
 * places a unit there) and `quality-code` (written by `gate-bind --write` from the gate lock;
 * a hand placement would be overwritten). `placeHint` names the right verb for each, and the
 * coverage gate's "missing" message prints it.
 *
 * REFUSALS, never a guess: a manifest holding a duplicate id or a `#<bucket>` id, a missing
 * unit with no cost (no `units` entry and no lane `defaultUnitMs`), a group whose committed
 * members already sit on two legs, an existing unit that `needs` a missing one (it would have
 * to move), and a block no leg is allowed to hold.
 *
 * Usage:
 *   npm run shard:place -- <lane>                               place and write (the script passes --write)
 *   npx tsx scripts/ci-runner/shard-place.ts <lane>             print what would change, write nothing
 *   npx tsx scripts/ci-runner/shard-place.ts <lane> --write     place and write
 *   npx tsx scripts/ci-runner/shard-place.ts --selftest         prove it can fail
 * The write is gated on `--write`, the repo's convention for a tree writer
 * (`check-lane-budget.ts --rebalance --write`, `gate-bind --write`), because
 * `check-shard-manifest-coverage.ts` imports `placeHint` from here and must never reach a
 * write (check:ci-gate-tree-writes).
 * Exit codes: 0 placed, or nothing to place; 1 a refusal.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { GREEN, NC, RED } from '../lib/console.js';
import {
  parseShardManifest,
  shardManifestPath,
  type ShardManifestFile,
} from './shard-manifest.js';
import { LANE_ENUMERATORS, type Unit } from './unit-enumerators.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const DURATIONS = path.join(ROOT, '.ci', 'config', 'lane-durations.json');
const LANE_BUDGET = path.join(ROOT, 'scripts', 'gates', 'check-lane-budget.ts');

/** Lanes this verb will not place into, each with the verb that does. */
export const PLACE_REFUSED: Readonly<Record<string, { why: string; verb: string }>> = {
  'test-e2e-workers': {
    why: 'its manifest splits files into #<bucket> ids and prices every leg per distro',
    verb: 'npx tsx scripts/gates/check-lane-budget.ts --rebalance test-e2e-workers --write',
  },
  'quality-code': {
    why: 'gate-bind --write generates it from scripts/ci-runner/gates.lock.json',
    verb: 'npx tsx scripts/gate-bind.ts --write',
  },
};

/** The command that puts a missing unit of `lane` onto a leg; the coverage gate prints it. */
export function placeHint(lane: string): string {
  return PLACE_REFUSED[lane]?.verb ?? `npm run shard:place -- ${lane}`;
}

export class PlaceError extends Error {}

/** The same declaration `check-lane-budget.ts` reads (its `XDIST_DECL_RE`); the selftest pins the two equal. */
export const XDIST_DECL_RE =
  /^XDIST_GROUP\s*=\s*(?:["']([^"']+)["']|xdist_groups\.REAL_TREE_GROUP)/m;

export interface Constraints {
  together?: { units: string[] }[];
  onLeg?: { unit: string; leg: number }[];
  notOnLeg?: { unit: string; leg: number }[];
}

export interface Pricing {
  /** A unit's p90 in ms, or undefined when neither `units` nor the lane default prices it. */
  costMs: (id: string) => number | undefined;
  workers: number;
  /** The xdist/mutex group a unit runs in, for PRICING only (single-file groups included). */
  priceGroupOf: (id: string) => string | undefined;
  constraints: Constraints;
}

export interface Placement {
  id: string;
  leg: number;
  why: string;
}

export interface PlaceResult {
  file: ShardManifestFile;
  placed: Placement[];
  dropped: { id: string; leg: number }[];
  /** Estimated unit ms per leg after placement, in leg order. */
  legMs: number[];
}

/** One leg's unit time: max(serial / workers, its largest group), `parallelLegMs`'s rule. */
export function legPriceMs(ids: readonly string[], pricing: Pricing): number {
  let serial = 0;
  const groups = new Map<string, number>();
  for (const id of ids) {
    const ms = pricing.costMs(id) ?? 0;
    serial += ms;
    const g = pricing.priceGroupOf(id);
    if (g !== undefined) groups.set(g, (groups.get(g) ?? 0) + ms);
  }
  if (pricing.workers <= 1) return serial;
  return Math.max(serial / pricing.workers, ...groups.values());
}

const isSorted = (ids: readonly string[]): boolean =>
  ids.every((id, i) => i === 0 || (ids[i - 1] as string) <= id);

/** The pure placement. Throws `PlaceError` on every refusal named in the header. */
export function placeUnits(
  file: ShardManifestFile,
  units: readonly Unit[],
  pricing: Pricing,
  now: string
): PlaceResult {
  const lane = file.lane;
  const refusedLane = PLACE_REFUSED[lane];
  if (refusedLane !== undefined) {
    throw new PlaceError(
      `lane ${lane} is not placed by shard:place: ${refusedLane.why}. Use: ${refusedLane.verb}`
    );
  }
  const legOf = new Map<string, number>();
  for (const leg of file.legs) {
    for (const id of leg.ids) {
      if (id.includes('#')) {
        throw new PlaceError(
          `${lane} leg ${leg.index}: "${id}" is a #<bucket> id, which only test-e2e-workers resolves; fix it by hand.`
        );
      }
      const prior = legOf.get(id);
      if (prior !== undefined) {
        throw new PlaceError(
          `${lane}: "${id}" is on legs ${prior} and ${leg.index}; keep it on one by hand, then re-run.`
        );
      }
      legOf.set(id, leg.index);
    }
  }
  const byId = new Map(units.map((u) => [u.id, u]));
  const dropped = file.legs.flatMap((l) =>
    l.ids.filter((id) => !byId.has(id)).map((id) => ({ id, leg: l.index }))
  );
  const missing = units.filter((u) => !legOf.has(u.id)).map((u) => u.id);

  const legs = new Map<number, string[]>(
    file.legs.map((l) => [l.index, l.ids.filter((id) => byId.has(id))])
  );
  for (const d of dropped) legOf.delete(d.id);

  // An existing unit that needs a missing one would have to run after it, on its leg: that is a move, not a placement.
  const missingSet = new Set(missing);
  for (const u of units) {
    if (!legOf.has(u.id)) continue;
    const need = (u.needs ?? []).find((n) => missingSet.has(n));
    if (need !== undefined) {
      throw new PlaceError(
        `${lane}: placed unit "${u.id}" needs the missing "${need}", so "${need}" must run before it on leg ${legOf.get(u.id)}; place it there by hand, ahead of "${u.id}".`
      );
    }
  }

  // Blocks: missing ids linked by mutex group, a together rule, or a needs edge; each link to a placed id is a home.
  const parent = new Map<string, string>(missing.map((id) => [id, id]));
  const find = (x: string): string => {
    let r = x;
    while (parent.get(r) !== r) r = parent.get(r) as string;
    return r;
  };
  // Home legs, keyed by a missing id; a block's home is the union over its members.
  const homes = new Map<string, Set<number>>();
  const linkSet = (ids: readonly string[]): void => {
    const miss = ids.filter((id) => missingSet.has(id));
    const first = miss[0];
    if (first === undefined) return;
    for (const m of miss.slice(1)) {
      const [ra, rb] = [find(first), find(m)];
      if (ra !== rb) parent.set(rb, ra);
    }
    for (const id of ids) {
      const leg = legOf.get(id);
      if (leg !== undefined) homes.set(first, (homes.get(first) ?? new Set()).add(leg));
    }
  };
  const byGroup = new Map<string, string[]>();
  for (const u of units) {
    if (u.mutex !== undefined) byGroup.set(u.mutex, [...(byGroup.get(u.mutex) ?? []), u.id]);
  }
  for (const members of byGroup.values()) linkSet(members);
  for (const t of pricing.constraints.together ?? []) linkSet(t.units);
  for (const id of missing) linkSet([id, ...(byId.get(id)?.needs ?? [])]);

  const blocks = new Map<string, string[]>();
  for (const id of missing) blocks.set(find(id), [...(blocks.get(find(id)) ?? []), id]);

  const allowedLegs = (ids: readonly string[]): number[] =>
    file.legs
      .map((l) => l.index)
      .filter((leg) =>
        ids.every(
          (id) =>
            !(pricing.constraints.notOnLeg ?? []).some((c) => c.unit === id && c.leg === leg) &&
            !(pricing.constraints.onLeg ?? []).some((c) => c.unit === id && c.leg !== leg)
        )
      );

  const costOf = (id: string): number => {
    const ms = pricing.costMs(id);
    if (ms === undefined) {
      throw new PlaceError(
        `${lane}: "${id}" has no cost: no units entry and no defaultUnitMs.${lane} in .ci/config/lane-durations.json, so "lightest leg" cannot be judged.`
      );
    }
    return ms;
  };
  const planned = [...blocks.values()].map((ids) => {
    const home = new Set<number>();
    for (const id of ids) for (const h of homes.get(id) ?? []) home.add(h);
    return {
      ids: [...ids].sort(),
      ms: ids.reduce((a, id) => a + costOf(id), 0),
      home: [...home].sort((a, b) => a - b),
    };
  });
  planned.sort((a, b) => b.ms - a.ms || (a.ids[0] as string).localeCompare(b.ids[0] as string));

  const placed: Placement[] = [];
  const homed = planned.filter((b) => b.home.length > 0);
  const free = planned.filter((b) => b.home.length === 0);
  const put = (ids: string[], leg: number, why: string): void => {
    const held = legs.get(leg) as string[];
    const appendOnly = !isSorted(held) || ids.some((id) => (byId.get(id)?.needs ?? []).length > 0);
    const ordered = [...ids].sort(
      (a, b) =>
        (byId.get(a)?.needs ?? []).length - (byId.get(b)?.needs ?? []).length || a.localeCompare(b)
    );
    legs.set(leg, appendOnly ? [...held, ...ordered] : [...held, ...ordered].sort());
    for (const id of ordered) {
      placed.push({ id, leg, why });
      legOf.set(id, leg);
    }
  };
  for (const b of homed) {
    if (b.home.length > 1) {
      throw new PlaceError(
        `${lane}: ${b.ids.join(' + ')} belong with units already split over legs ${b.home.join(', ')}; ` +
          `the committed plan breaks its own group. Re-plan it: npx tsx scripts/gates/check-lane-budget.ts --rebalance ${lane} --write`
      );
    }
    const leg = b.home[0] as number;
    if (!allowedLegs(b.ids).includes(leg)) {
      throw new PlaceError(
        `${lane}: ${b.ids.join(' + ')} must join leg ${leg} (its group's leg), which an onLeg/notOnLeg rule forbids.`
      );
    }
    put(b.ids, leg, `with its group on leg ${leg}`);
  }
  for (const b of free) {
    const allowed = allowedLegs(b.ids);
    if (allowed.length === 0) {
      throw new PlaceError(`${lane}: no leg may hold ${b.ids.join(' + ')} (onLeg/notOnLeg rules).`);
    }
    let best = allowed[0] as number;
    let bestMs = Number.POSITIVE_INFINITY;
    for (const leg of allowed) {
      const ms = legPriceMs(legs.get(leg) as string[], pricing);
      if (ms < bestMs) [best, bestMs] = [leg, ms];
    }
    put(b.ids, best, `lightest leg (${(bestMs / 60_000).toFixed(2)}m before)`);
  }

  const changed = placed.length > 0 || dropped.length > 0;
  return {
    file: changed
      ? {
          ...file,
          generatedAt: now,
          legs: file.legs.map((l) => ({ ...l, ids: legs.get(l.index) as string[] })),
        }
      : file,
    placed,
    dropped,
    legMs: file.legs.map((l) => legPriceMs(legs.get(l.index) as string[], pricing)),
  };
}

/** The whole edit on the file's TEXT: returns the input string itself when nothing changes. */
export function placeText(
  text: string,
  lane: string,
  units: readonly Unit[],
  pricing: Pricing,
  now: string
): { text: string; result: PlaceResult } {
  const result = placeUnits(parseShardManifest(text, lane), units, pricing, now);
  if (result.placed.length === 0 && result.dropped.length === 0) return { text, result };
  return { text: `${JSON.stringify(result.file, null, 2)}\n`, result };
}

interface Durations {
  units?: Record<string, number>;
  defaultUnitMs?: Record<string, number>;
  unitParallelism?: Record<string, number>;
  rebalanceConstraints?: Record<string, Constraints>;
}

/** The lane's pricing from the real lane-durations.json and the real test files. */
export function realPricing(lane: string, units: readonly Unit[]): Pricing {
  const d = JSON.parse(fs.readFileSync(DURATIONS, 'utf8')) as Durations;
  const fallback = d.defaultUnitMs?.[lane];
  const mutex = new Map(units.filter((u) => u.mutex !== undefined).map((u) => [u.id, u.mutex]));
  const declared = new Map<string, string | undefined>();
  return {
    costMs: (id) => d.units?.[id] ?? fallback,
    workers: d.unitParallelism?.[lane] ?? 1,
    priceGroupOf: (id) => {
      const m = mutex.get(id);
      if (m !== undefined) return m;
      if (!id.startsWith('pytest:')) return undefined;
      if (!declared.has(id)) {
        const f = path.join(ROOT, id.slice('pytest:'.length));
        const hit = fs.existsSync(f) ? XDIST_DECL_RE.exec(fs.readFileSync(f, 'utf8')) : null;
        declared.set(id, hit === null ? undefined : `xdist:${hit[1] ?? 'real-tree'}`);
      }
      return declared.get(id);
    },
    constraints: d.rebalanceConstraints?.[lane] ?? {},
  };
}

async function main(argv: string[]): Promise<number> {
  const lane = argv.find((a) => !a.startsWith('--'));
  const shardsDir = path.join(ROOT, '.ci', 'config', 'shards');
  const lanes = fs
    .readdirSync(shardsDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''))
    .sort();
  if (lane === undefined || !lanes.includes(lane)) {
    console.error(
      `${RED}✗ shard:place needs a lane with a committed manifest: ${lanes.join(', ')}` +
        `${lane === undefined ? '' : ` (got "${lane}")`}.${NC}`
    );
    return 1;
  }
  const enumerator = LANE_ENUMERATORS[lane];
  if (PLACE_REFUSED[lane] === undefined && enumerator === undefined) {
    console.error(`${RED}✗ lane ${lane} has no LANE_ENUMERATORS entry; nothing says what its units are.${NC}`);
    return 1;
  }
  const rel = shardManifestPath(lane);
  const abs = path.join(ROOT, rel);
  const text = fs.readFileSync(abs, 'utf8');
  try {
    const units = enumerator === undefined ? [] : await enumerator(ROOT);
    if (PLACE_REFUSED[lane] === undefined && units.length === 0) {
      console.error(`${RED}✗ lane ${lane} enumerated ZERO units; placing against nothing would drop every id.${NC}`);
      return 1;
    }
    const { text: next, result } = placeText(
      text,
      lane,
      units,
      realPricing(lane, units),
      new Date().toISOString()
    );
    const ids = result.file.legs.reduce((n, l) => n + l.ids.length, 0);
    console.log(
      `shard:place ${lane}: ${units.length} unit(s), ${result.file.legs.length} leg(s), ${ids} id(s) after; ` +
        `placed ${result.placed.length}, dropped ${result.dropped.length}; legs now ` +
        `${result.legMs.map((ms) => `${(ms / 60_000).toFixed(2)}m`).join(' / ')} of unit time`
    );
    for (const p of result.placed) console.log(`  + ${p.id} -> leg ${p.leg} (${p.why})`);
    for (const d of result.dropped)
      console.log(`  - ${d.id} dropped from leg ${d.leg} (no such unit any more)`);
    if (next === text) {
      console.log(`${GREEN}✓ ${rel}: nothing to place or drop; file untouched${NC}`);
      return 0;
    }
    if (!process.argv.includes('--write')) {
      console.log(`preview only: ${rel} NOT written; npm run shard:place -- ${lane} writes it`);
      return 0;
    }
    fs.writeFileSync(abs, next);
    console.log(
      `${GREEN}✓ wrote ${rel}. Check it: npm run check:ci-shard-manifest-coverage and npx tsx scripts/gates/check-lane-budget.ts${NC}`
    );
    return 0;
  } catch (err) {
    console.error(`${RED}✗ shard:place ${lane}: ${(err as Error).message}${NC}`);
    return 1;
  }
}

async function selftest(): Promise<number> {
  const NOW = '2026-10-07T00:00:00.000Z';
  const mk = (lane: string, legs: string[][]): ShardManifestFile => ({
    lane,
    of: legs.length,
    generatedAt: '2026-10-01T00:00:00.000Z',
    legs: legs.map((ids, i) => ({ index: i + 1, ids })),
  });
  const pricing = (
    costs: Record<string, number>,
    extra: Partial<Pricing> = {}
  ): Pricing => ({
    costMs: (id) => costs[id] ?? costs['*'],
    workers: 1,
    priceGroupOf: () => undefined,
    constraints: {},
    ...extra,
  });
  const u = (id: string, more: Partial<Unit> = {}): Unit => ({ id, ...more });
  const L = 'quality-pytest';
  const throwsWith = (fn: () => unknown, needle: string): boolean => {
    try {
      fn();
      return false;
    } catch (e) {
      return e instanceof PlaceError && e.message.includes(needle);
    }
  };
  const base = mk(L, [['a', 'b'], ['c'], ['d', 'e']]);
  const baseUnits = ['a', 'b', 'c', 'd', 'e'].map((id) => u(id));
  const costs = { a: 50, b: 50, c: 30, d: 40, e: 40, '*': 10 };

  const cases: { name: string; ok: boolean; detail?: string }[] = [];
  const add = (name: string, ok: boolean, detail?: string): void => {
    cases.push({ name, ok, detail });
  };

  {
    const r = placeUnits(base, [...baseUnits, u('n')], pricing(costs), NOW);
    add(
      'PLACES: a new unit goes to the lightest leg (leg 2 at 30 ms, against 100 and 80)',
      r.placed.length === 1 && r.placed[0]?.leg === 2 && r.file.legs[1]?.ids.join(',') === 'c,n',
      JSON.stringify(r.placed)
    );
    add('stamps generatedAt on a change', r.file.generatedAt === NOW);
  }
  {
    const r = placeUnits(base, [...baseUnits, u('x'), u('y')], pricing({ ...costs, x: 60, y: 45 }), NOW);
    const at = Object.fromEntries(r.placed.map((p) => [p.id, p.leg]));
    add(
      'PLACES heaviest first: x (60) takes leg 2, then y (45) the next lightest, leg 3',
      at.x === 2 && at.y === 3,
      JSON.stringify(at)
    );
  }
  {
    const units = [...baseUnits.filter((x) => x.id !== 'a'), u('a', { mutex: 'G' }), u('m', { mutex: 'G' })];
    const r = placeUnits(base, units, pricing(costs), NOW);
    add(
      'MUTEX: a new member of group G joins G on leg 1, the HEAVIEST leg, not the lightest',
      r.placed[0]?.leg === 1 && r.placed[0]?.why.includes('group'),
      JSON.stringify(r.placed)
    );
  }
  {
    const r = placeUnits(base, [...baseUnits, u('p', { mutex: 'H' }), u('q', { mutex: 'H' })], pricing(costs), NOW);
    add(
      'MUTEX: two new members of one new group land on ONE leg',
      r.placed.length === 2 && r.placed[0]?.leg === r.placed[1]?.leg,
      JSON.stringify(r.placed)
    );
  }
  {
    const units = baseUnits.map((x) => (x.id === 'a' || x.id === 'c' ? u(x.id, { mutex: 'S' }) : x));
    add(
      'REFUSES: a group whose committed members already sit on two legs',
      throwsWith(() => placeUnits(base, [...units, u('s', { mutex: 'S' })], pricing(costs), NOW), 'split over legs 1, 2'),
    );
  }
  {
    const r = placeUnits(base, baseUnits.filter((x) => x.id !== 'e'), pricing(costs), NOW);
    add(
      'DROPS: a phantom id (its unit is gone) leaves leg 3',
      r.dropped.length === 1 && r.dropped[0]?.id === 'e' && r.file.legs[2]?.ids.join(',') === 'd',
      JSON.stringify(r.dropped)
    );
  }
  add(
    'REFUSES test-e2e-workers, naming check-lane-budget --rebalance',
    throwsWith(
      () => placeUnits(mk('test-e2e-workers', [['x']]), [u('x'), u('y')], pricing(costs), NOW),
      '--rebalance test-e2e-workers --write'
    )
  );
  add(
    'REFUSES quality-code, naming gate-bind --write',
    throwsWith(() => placeUnits(mk('quality-code', [['x']]), [u('x')], pricing(costs), NOW), 'gate-bind.ts --write')
  );
  add(
    'placeHint: shard:place for a placeable lane, the owning verb for a refused one',
    placeHint('quality-pytest') === 'npm run shard:place -- quality-pytest' &&
      placeHint('test-e2e-workers').includes('--rebalance test-e2e-workers')
  );
  {
    const text = `${JSON.stringify(base, null, 2)}\n`;
    const out = placeText(text, L, baseUnits, pricing(costs), NOW);
    add('NO-OP: nothing to place or drop returns the input text itself, generatedAt untouched', out.text === text);
    const odd = text.replace(/\n {2}/g, '\n    ');
    add('NO-OP holds for formatting this tool would not write', placeText(odd, L, baseUnits, pricing(costs), NOW).text === odd);
    const once = placeText(text, L, [...baseUnits, u('n')], pricing(costs), NOW).text;
    add(
      'CONTROL: a run that places changes the text, and a second run on its output is a no-op',
      once !== text && placeText(once, L, [...baseUnits, u('n')], pricing(costs), '2099-01-01T00:00:00.000Z').text === once
    );
  }
  add(
    'REFUSES: a missing unit with no cost and no lane default',
    throwsWith(() => placeUnits(base, [...baseUnits, u('z')], pricing({ a: 1, b: 1, c: 1, d: 1, e: 1 }), NOW), 'has no cost')
  );
  add(
    'REFUSES: a duplicate id in the committed manifest',
    throwsWith(() => placeUnits(mk(L, [['a'], ['a']]), [u('a')], pricing(costs), NOW), 'on legs 1 and 2')
  );
  add(
    'REFUSES: a #bucket id outside test-e2e-workers',
    throwsWith(() => placeUnits(mk(L, [['a#part1']]), [u('a')], pricing(costs), NOW), '#<bucket>')
  );
  add(
    'REFUSES: a placed unit that needs a missing one (it would have to move)',
    throwsWith(
      () => placeUnits(base, [...baseUnits.filter((x) => x.id !== 'c'), u('c', { needs: ['n'] }), u('n')], pricing(costs), NOW),
      'needs the missing "n"'
    )
  );
  {
    const r = placeUnits(base, [...baseUnits, u('n', { needs: ['d'] })], pricing(costs), NOW);
    add(
      'NEEDS: a new unit that needs a placed one joins its leg, appended after it',
      r.placed[0]?.leg === 3 && r.file.legs[2]?.ids.join(',') === 'd,e,n',
      JSON.stringify(r.file.legs[2])
    );
  }
  {
    const r = placeUnits(base, [...baseUnits, u('n')], pricing(costs, { constraints: { notOnLeg: [{ unit: 'n', leg: 2 }] } }), NOW);
    add('CONSTRAINT: notOnLeg keeps a unit off the lightest leg', r.placed[0]?.leg === 3, JSON.stringify(r.placed));
  }
  {
    const unsorted = mk(L, [['b', 'a'], ['c'], ['d', 'e']]);
    const r = placeUnits(unsorted, [...baseUnits, u('0')], pricing({ ...costs, c: 500, d: 500 }), NOW);
    add(
      'ORDER: an unsorted leg keeps its order and gets the new id appended',
      r.file.legs[0]?.ids.join(',') === 'b,a,0',
      JSON.stringify(r.file.legs[0])
    );
    const s = placeUnits(base, [...baseUnits, u('0')], pricing({ ...costs, c: 500, d: 500 }), NOW);
    add('ORDER: a sorted leg stays sorted', s.file.legs[0]?.ids.join(',') === '0,a,b', JSON.stringify(s.file.legs[0]));
  }
  {
    const p = pricing({ g1: 400, f1: 100, f2: 100 }, { workers: 4, priceGroupOf: (id) => (id === 'g1' ? 'G' : undefined) });
    add(
      'PRICE: a 4-worker leg costs max(serial / 4, its largest group): 400, not 150',
      legPriceMs(['g1', 'f1', 'f2'], p) === 400 && legPriceMs(['f1', 'f2'], p) === 50
    );
  }
  {
    const src = fs.readFileSync(LANE_BUDGET, 'utf8');
    const m = /const XDIST_DECL_RE = (\/.*\/m);/.exec(src);
    add(
      'PIN: XDIST_DECL_RE equals check-lane-budget.ts\'s own, so both price the same groups',
      m !== null && m[1] === XDIST_DECL_RE.toString(),
      m?.[1]
    );
  }
  {
    // The real tree: placing twice is a no-op the second time, and every placement is a real unit.
    const units = await LANE_ENUMERATORS[L]?.(ROOT);
    const text = fs.readFileSync(path.join(ROOT, shardManifestPath(L)), 'utf8');
    try {
      const first = placeText(text, L, units ?? [], realPricing(L, units ?? []), NOW);
      const second = placeText(first.text, L, units ?? [], realPricing(L, units ?? []), '2099-01-01T00:00:00.000Z');
      add(
        `REAL TREE: ${L} (${units?.length ?? 0} units) placed once is a no-op placed again`,
        (units?.length ?? 0) > 0 && second.text === first.text && second.result.placed.length === 0,
        `first run placed ${first.result.placed.length}, dropped ${first.result.dropped.length}`
      );
    } catch (e) {
      add(`REAL TREE: ${L} places without a refusal`, false, (e as Error).message);
    }
  }

  let failed = 0;
  for (const c of cases) {
    if (c.ok) console.log(`  ${GREEN}PASS${NC} ${c.name}`);
    else {
      failed += 1;
      console.error(`  ${RED}FAIL${NC} ${c.name}${c.detail ? ` (${c.detail})` : ''}`);
    }
  }
  if (failed > 0) {
    console.error(`${RED}✗ shard-place selftest: ${failed} of ${cases.length} case(s) failed${NC}`);
    return 1;
  }
  console.log(`${GREEN}✓ shard-place selftest: ${cases.length} case(s) passed${NC}`);
  return 0;
}

const invoked = process.argv[1] && import.meta.url === `file://${path.resolve(process.argv[1])}`;
if (invoked) {
  const args = process.argv.slice(2);
  process.exit(args.includes('--selftest') ? await selftest() : await main(args));
}
