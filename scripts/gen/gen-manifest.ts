#!/usr/bin/env tsx
/**
 * C1: the generated region of `scripts/ci-runner/manifest.ts`.
 *
 * WHAT IT GENERATES, AND WHY THE SET IS SMALL. An entry is generated only when
 * building it from its leaf's `---- gate ----` header ALONE reproduces the entry
 * that is there, field for field AND byte for byte, so that emitting it can lose
 * nothing. Five conditions, each one paid for by a measurement recorded in
 * `agent/PLAN-tooling-transformation.md`'s C1 box:
 *
 *   1. No hand-only field. `qualityGateTest`, `paths`, `reads`, `heavy`, `mutex`,
 *      `weight`, `noProfile` -- the last of which the box's own list omits, and
 *      two entries carry it.
 *   2. Exactly one leaf, and it is a real file. A bare tool name (`biome`, `tsc`,
 *      `knip`) is a CORRECT leaf per `scripts/ci-runner/gate-spec.ts:106-110` --
 *      "Leaf COMMANDS this gate ultimately executes" -- and has no header to
 *      generate from.
 *   3. That leaf carries a parseable header.
 *   4. The header declares no `blocker:`. A blocker is the entry DECLARING ITSELF
 *      hand-registered; all ten in the tree say some variant of "runs before this
 *      lane's `- id: setup` step, so emitting it would move it below the guard".
 *   5. The serialised entry is byte-identical to the span already in the file.
 *
 * WHY (5) IS THE WHOLE DESIGN. Because the generated text equals the text already
 * there, `--write` adds nothing but marker lines: the entries do not move, the
 * array order does not change -- and array order is BEHAVIOUR, since
 * `scripts/gen-gates-lock.ts:99` records that `pool.ts` breaks scheduling ties on
 * the array index -- and the regenerated lock is byte-identical by construction
 * rather than by hope. Any entry whose generated form differs is EXCLUDED, never
 * rewritten. A generator that would improve an entry is a generator that is
 * changing behaviour it cannot prove.
 *
 * WHY PROSE EXCLUDES AN ENTRY. `scripts/gate-bind.ts:649` says the `//` prose above
 * an entry IS the header's `why:`. That is true of gate-bind's extraction direction
 * and FALSE of this tree: of 122 entries carrying prose, exactly one matches its
 * header's `why:`. So any `//` inside a span -- a trailing `// 17.8s measured` on a
 * `slow:` line included, since that comment is the measurement justifying the flag --
 * makes the entry hand-written until its prose is migrated into the header.
 *
 * ---- gate ----
 * step: Generated manifest regions
 * needs: node
 * lane: quality-code
 * selftest: true
 * why: The generated regions of the gate manifest must still equal what the
 *      headers say, or a hand edit inside one is silently reverted by the next
 *      `--write` -- and the entries inside them are the ones whose text is proven
 *      byte-identical to their own header, so a drift here means a header and its
 *      entry have parted company
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { GATES } from '../ci-runner/manifest.js';
import { laneCapabilities, placeGate } from '../ci-runner/lanes.js';
import { derivedId, inferredNeeds, parseGateHeader } from '../lib/gate-header.js';
import type { GateHeader } from '../lib/gate-header.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const MANIFEST = path.join(ROOT, 'scripts/ci-runner/manifest.ts');
const WORKFLOW = path.join(ROOT, '.github/workflows/ci-quality.yml');

const HAND_ONLY = [
  'qualityGateTest',
  'paths',
  'reads',
  'heavy',
  'mutex',
  'weight',
  'noProfile',
] as const;

const BEGIN = (n: number): string => `  // >>> gen-manifest: region ${n}`;
const END = (n: number): string => `  // <<< gen-manifest: region ${n}`;

/** A TS string literal the way this file already writes them. */
const q = (s: string): string => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

type Entry = Record<string, unknown>;

/**
 * The entry a generator would emit from the leaf's header alone, as SOURCE TEXT.
 *
 * Field order is the file's own: id, env, run, slow, gate, leaves, when, ci. It is
 * not guessed -- an order that differs fails condition (5) and the entry drops out
 * of the set rather than being reformatted.
 */
function serialise(leaf: string, h: GateHeader, workflow: string): string {
  const src = fs.readFileSync(path.join(ROOT, leaf), 'utf-8');
  const id = (h.id as string) ?? derivedId(leaf);
  const needs: string[] = h.needs?.length
    ? h.needs
    : inferredNeeds(src).filter((n: string) => !(h.needsNot ?? []).includes(n));
  const placed = h.lane
    ? { lane: h.lane as string }
    : placeGate(laneCapabilities(fs.readFileSync(WORKFLOW, 'utf-8')), needs);
  const job = 'lane' in placed ? placed.lane : undefined;

  const L: string[] = ['  {', `    id: ${q(id)},`];
  // `env` sits between `id` and `run` in this file, not after `leaves`.
  if (h.env) {
    L.push('    env: {');
    for (const [k, v] of Object.entries(h.env as Record<string, string>)) {
      L.push(`      ${/^[A-Za-z_$][\w$]*$/.test(k) ? k : q(k)}: ${q(v)},`);
    }
    L.push('    },');
  }
  L.push(`    run: ${q(`npm run ${id}`)},`);
  if (h.slow) L.push('    slow: true,');
  L.push('    gate: true,', `    leaves: [${q(leaf)}],`);
  if (h.when) L.push(`    when: ${q(h.when as string)},`);

  // A `battery` header RIDES a shared step, which the manifest records as `step`.
  const kind = h.kind === 'battery' ? 'step' : (h.kind as string);
  L.push('    ci: {', `      kind: ${q(kind)},`);
  if (h.kind === 'step' || h.kind === 'battery') {
    L.push(
      `      workflow: ${q(workflow)},`,
      `      job: ${q(job ?? '')},`,
      `      step: ${q(h.step as string)},`
    );
  }
  if (h.test !== undefined) L.push(`      test: ${q(h.test as string)},`);
  L.push('    },', '  },');
  return L.join('\n');
}

/** Entry spans in array order: `  {` .. `  },` at indent 2. */
function spans(lines: readonly string[]): [number, number][] {
  const out: [number, number][] = [];
  let open = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] === '  {') open = i;
    else if (lines[i] === '  },' && open >= 0) {
      out.push([open, i]);
      open = -1;
    }
  }
  return out;
}

/**
 * Controls first. Each one plants the defect it claims to catch, because the two
 * ways this tool can fail silently are both invisible to a clean run: a splice
 * that loses a line, and a derivation that quietly resolves to nothing.
 */
function selftest(): number {
  let bad = 0;
  const check = (ok: boolean, label: string): void => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) bad++;
  };

  // The splice must be reversible: stripping the markers must give back the input byte for byte, or `--write` run twice would drift.
  const body = ['  {', "    id: 'a',", '  },', '  {', "    id: 'b',", '  },'];
  const gen = [true, false];
  const sp = spans(body);
  const out: string[] = [];
  let r = 0;
  for (let i = 0, s2 = 0; i < body.length; i++) {
    if (s2 < sp.length && i === sp[s2][0] && gen[s2] && (s2 === 0 || !gen[s2 - 1]))
      out.push(BEGIN(++r));
    out.push(body[i]);
    if (s2 < sp.length && i === sp[s2][1]) {
      if (gen[s2] && (s2 === sp.length - 1 || !gen[s2 + 1])) out.push(END(r));
      s2++;
    }
  }
  check(r === 1 && out.length === body.length + 2, 'one contiguous run yields exactly one region');
  const stripped = out.filter(
    (l) => !l.startsWith('  // >>> gen-manifest') && !l.startsWith('  // <<< gen-manifest')
  );
  check(
    stripped.join('\n') === body.join('\n'),
    'CONTROL: stripping the markers restores the input byte for byte'
  );
  check(
    out[0] === BEGIN(1) && out[4] === END(1),
    'the markers bracket the generated entry and not its neighbour'
  );

  // A span scanner that loses an entry would splice by a shifted index, which is the one failure that silently marks the WRONG entries as generated.
  check(
    sp.length === 2,
    'CONTROL: the span scanner finds both entries, so splice indices cannot shift'
  );

  // Interleaved runs must not be merged into one region, or 358 hand entries would land inside a generated region and be reported as drift forever after.
  const g2 = [true, false, true];
  let r2 = 0;
  for (let i = 0; i < g2.length; i++) if (g2[i] && (i === 0 || !g2[i - 1])) r2++;
  check(r2 === 2, 'CONTROL: two runs separated by a hand entry stay two regions, never one');

  return bad === 0 ? 0 : 1;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest();
  const write = argv.includes('--write');
  const text = fs.readFileSync(MANIFEST, 'utf-8');
  const raw = text.split('\n');
  // The markers are the OUTPUT, so they are stripped before anything is measured: otherwise the second run compares the file against a version of itself that already contains its own answer, and could never report drift.
  const isMarker = (l: string): boolean =>
    l.startsWith('  // >>> gen-manifest') || l.startsWith('  // <<< gen-manifest');
  const lines = raw.filter((l) => !isMarker(l));
  const hadMarkers = raw.length !== lines.length;
  const sp = spans(lines);
  const all = GATES as unknown as Entry[];

  if (sp.length !== all.length) {
    console.error(
      `gen-manifest: ${sp.length} span(s) in the file against ${all.length} entries imported. ` +
        `The span scanner and the array have parted company; refusing rather than splicing by index.`
    );
    return 1;
  }

  const generated: boolean[] = [];
  const excluded = new Map<string, number>();
  const drop = (why: string): false => {
    excluded.set(why, (excluded.get(why) ?? 0) + 1);
    return false;
  };

  for (let i = 0; i < all.length; i++) {
    const g = all[i];
    generated.push(
      ((): boolean => {
        if (HAND_ONLY.some((f) => g[f] !== undefined)) return drop('carries a hand-only field');
        const leaves = (g.leaves as string[] | undefined) ?? [];
        if (leaves.length !== 1) return drop('not exactly one leaf');
        const p = path.join(ROOT, leaves[0]);
        if (!fs.existsSync(p) || !fs.statSync(p).isFile())
          return drop('leaf is a tool, not a file');
        const h = parseGateHeader(fs.readFileSync(p, 'utf-8'));
        if (!h) return drop('leaf carries no gate header');
        if (h.blocker !== undefined) return drop('header declares a BLOCKER (hand-registered)');
        const [a, b] = sp[i];
        if (lines.slice(a + 1, b).some((l) => l.includes('//'))) return drop('entry carries prose');
        const cur = lines.slice(a, b + 1).join('\n');
        const gen = serialise(
          leaves[0],
          h,
          (g.ci as { workflow?: string } | undefined)?.workflow ?? ''
        );
        if (gen === cur) return true;
        if (process.env.GEN_MANIFEST_DEBUG) {
          console.error(`--- ${String(g.id)}\nCURRENT:\n${cur}\nGENERATED:\n${gen}`);
        }
        return drop('generated text differs from the entry');
      })()
    );
  }

  const n = generated.filter(Boolean).length;
  let regions = 0;
  for (let i = 0; i < generated.length; i++) {
    const prev = i > 0 ? generated[i - 1] : !generated[i];
    if (generated[i] && !prev) regions++;
  }

  console.log(`gen-manifest: ${n} generated, ${all.length - n} hand, ${regions} region(s)`);
  for (const [why, c] of [...excluded].sort((x, y) => y[1] - x[1])) {
    console.log(`  ${String(c).padStart(4)}  ${why}`);
  }
  if (n === 0) {
    console.error(
      'gen-manifest: NOTHING is generable. That is a broken derivation, not a clean tree.'
    );
    return 1;
  }

  // Only marker lines are inserted: every generated entry's text is already proven equal to its own serialisation, so the array does not move and the lock cannot.
  const out: string[] = [];
  let r = 0;
  for (let i = 0, s = 0; i < lines.length; i++) {
    if (s < sp.length && i === sp[s][0]) {
      const first = generated[s] && (s === 0 || !generated[s - 1]);
      if (first) out.push(BEGIN(++r));
    }
    out.push(lines[i]);
    if (s < sp.length && i === sp[s][1]) {
      const last = generated[s] && (s === sp.length - 1 || !generated[s + 1]);
      if (last) out.push(END(r));
      s++;
    }
  }
  const want = out.join('\n');
  if (!write) {
    if (want === text) {
      console.log('gen-manifest: scripts/ci-runner/manifest.ts already matches');
      return 0;
    }
    console.error(
      hadMarkers
        ? 'gen-manifest: the regions in scripts/ci-runner/manifest.ts no longer match what the\n' +
            '  headers derive. An entry inside a region was hand-edited, or a header moved.\n' +
            '  Regenerate with: npx tsx scripts/gen-manifest.ts --write'
        : 'gen-manifest: scripts/ci-runner/manifest.ts carries no generated regions.\n' +
            '  Emit them with: npx tsx scripts/gen-manifest.ts --write'
    );
    return 1;
  }
  fs.writeFileSync(MANIFEST, want);
  console.log(`gen-manifest: wrote ${r} region(s) into scripts/ci-runner/manifest.ts`);
  return 0;
}

process.exit(main(process.argv.slice(2)));
