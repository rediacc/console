#!/usr/bin/env tsx
/**
 * C1: the generated region of `scripts/ci-runner/manifest.ts`.
 *
 * WHAT IT GENERATES, AND WHY THE SET IS SMALL. An entry is generated only when
 * building it from its leaf's `---- gate ----` header ALONE reproduces the entry
 * that is there, field for field AND byte for byte, so that emitting it can lose
 * nothing. Five conditions, each one paid for by a measurement recorded in
 * `agent/plans/PLAN-tooling-transformation.md`'s C1 box:
 *
 *   1. No hand-only field. `paths`, `reads`, `heavy`, `mutex`,
 *      `writesTree`, `cores`, `noProfile` -- the last of which the box's own list
 *      omits, and two entries carry it. `cores` (the elastic width range) replaced
 *      `weight` on 2026-10-05 (agent/plans/PLAN-prepush-full-cpu.md PF1).
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
 * `scripts/gen/gen-gates-lock.ts:99` records that `pool.ts` breaks scheduling ties on
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
 * id: check:ci-gen-gates
 * step: Gate declarations agree
 * run: tsx scripts/gen/gen-manifest.ts --gates --check
 * needs: node
 * lane: quality-code
 * why: ONE check over every copy a gate's declaration is written into (agent/plans/
 *      PLAN-tooling-code-reduction.md D2): the manifest regions, the lock, the
 *      workflow regions and shards, the header bindings, the CI parity surface, the
 *      manifest rules, the doc regions, the step env and the orphan step keys, each
 *      leg's own selftest first. It replaced eight gates that each held one copy.
 * ---- end gate ----
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import type { GateHeader, GateSpec } from '../ci-runner/gate-spec.js';
import { derivedId, headerSpec, inferredNeeds, parseGateHeader } from '../ci-runner/gate-spec.js';
import { laneCapabilities, placeGate } from '../ci-runner/lanes.js';
import { GATES } from '../ci-runner/manifest.js';
import {
  type Bound,
  directRun,
  jobsWithStep,
  scanDeclarations,
  trackedSubjects,
} from '../gate-bind.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const MANIFEST = path.join(ROOT, 'scripts/ci-runner/manifest.ts');
const WORKFLOW_REL = '.github/workflows/ci-quality.yml';
const WORKFLOW = path.join(ROOT, WORKFLOW_REL);

const HAND_ONLY = [
  'paths',
  'reads',
  'heavy',
  'mutex',
  'writesTree',
  'cores',
  'ciOnly',
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
  const id = h.id ?? derivedId(leaf);
  const needs: string[] =
    h.needs.length > 0
      ? h.needs
      : inferredNeeds(src).filter((n: string) => !h.needsNot.includes(n));
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
  L.push(`    run: ${q(entryRun(id, leaf, packageScripts()))},`);
  if (h.slow) L.push('    slow: true,');
  L.push('    gate: true,', `    leaves: [${q(leaf)}],`);
  if (h.when) L.push(`    when: ${q(h.when as string)},`);

  // A `shared-step` header RIDES a shared step, which the manifest records as `step`.
  const kind = h.kind === 'shared-step' ? 'step' : (h.kind as string);
  L.push('    ci: {', `      kind: ${q(kind)},`);
  if (h.kind === 'step' || h.kind === 'shared-step') {
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

/**
 * The `run` an entry takes: an `npm run <id>` hop while package.json still defines the key, else the module run directly (`directRun`), the D2 form of a gate whose key was retired.
 */
export function entryRun(
  id: string,
  leaf: string,
  scripts: Readonly<Record<string, string>>
): string {
  return Object.hasOwn(scripts, id) ? `npm run ${id}` : directRun(leaf);
}

let scriptsCache: Record<string, string> | undefined;
function packageScripts(): Record<string, string> {
  scriptsCache ??= (
    JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf-8')) as {
      scripts: Record<string, string>;
    }
  ).scripts;
  return scriptsCache;
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

/* ------------------------------------------- gates declared by their header alone (D2) */

/**
 * THE `gen-gates` REGION: one manifest entry per gate whose header is its ONLY declaration (agent/plans/PLAN-tooling-code-reduction.md D2). A gate the hand entries already register is left alone, whatever its header says; a header whose id no hand entry carries is emitted here, run DIRECTLY (`directRun`, no npm key), and from here `--gates --write` carries it into the lock, the workflow region, the shard manifest and the doc tables. So a new gate is its module (carrying the header) plus its test: the other files are outputs.
 *
 * The region sits at the END of `GATES` and is sorted by id. Array order is scheduling behaviour (pool.ts breaks ties on the index), so appending cannot move a hand entry, and sorting makes the output independent of `git ls-files` order.
 */
const GBEGIN =
  '  // >>> gen-gates: header-declared gates (npm run gen:gates -- --write; do not edit)';
const GEND = '  // <<< gen-gates';

/** A TS string literal the way biome writes one: single quotes, unless the text holds more single quotes than double. */
function lit(s: string): string {
  const sq = (s.match(/'/g) ?? []).length;
  const dq = (s.match(/"/g) ?? []).length;
  if (sq > dq) return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
  return q(s);
}

/** `key: value,` at `indent`, broken after the colon the way biome breaks a property over 100 columns. */
function prop(indent: string, key: string, value: string): string[] {
  const one = `${indent}${key}: ${value},`;
  return one.length <= 100 ? [one] : [`${indent}${key}:`, `${indent}  ${value},`];
}

/** One header-declared spec as manifest source, in the field order the hand entries use (id, env, run, slow, gate, leaves, when, ci). */
export function serialiseSpec(g: GateSpec): string {
  const L: string[] = ['  {', ...prop('    ', 'id', lit(g.id))];
  if (g.env !== undefined) {
    L.push('    env: {');
    for (const [k, v] of Object.entries(g.env)) {
      L.push(...prop('      ', /^[A-Za-z_$][\w$]*$/.test(k) ? k : lit(k), lit(v)));
    }
    L.push('    },');
  }
  L.push(...prop('    ', 'run', lit(g.run)));
  if (g.slow === true) L.push('    slow: true,');
  L.push('    gate: true,');
  const leaves = `    leaves: [${g.leaves.map(lit).join(', ')}],`;
  if (leaves.length <= 100) L.push(leaves);
  else L.push('    leaves: [', ...g.leaves.map((l) => `      ${lit(l)},`), '    ],');
  if (g.when !== undefined) L.push(...prop('    ', 'when', lit(g.when)));
  L.push('    ci: {', ...prop('      ', 'kind', lit(g.ci.kind)));
  if (g.ci.kind === 'step') {
    L.push(
      ...prop('      ', 'workflow', lit(g.ci.workflow)),
      ...prop('      ', 'job', lit(g.ci.job)),
      ...prop('      ', 'step', lit(g.ci.step))
    );
  } else if (g.ci.kind === 'test') {
    L.push(
      ...prop('      ', 'test', lit(g.ci.test)),
      ...prop('      ', 'blocker', lit(g.ci.blocker))
    );
  } else {
    L.push(...prop('      ', 'blocker', lit(g.ci.blocker)));
  }
  L.push('    },', '  },');
  return L.join('\n');
}

/** The file's lines with the `gen-gates` region cut out, and the region's own lines; refused when only one marker is present, because a half region would splice the hand entries into it. */
export function cutRegion(
  lines: readonly string[]
): { hand: string[]; region: string[] } | { error: string } {
  const b = lines.indexOf(GBEGIN);
  const e = lines.indexOf(GEND);
  if (b === -1 && e === -1) return { hand: [...lines], region: [] };
  if (b === -1 || e === -1 || e < b) {
    return {
      error:
        'the `gen-gates` region in scripts/ci-runner/manifest.ts is broken (one marker without the other, or out of order); restore both marker lines and rerun `npm run gen:gates -- --write`',
    };
  }
  return { hand: [...lines.slice(0, b), ...lines.slice(e + 1)], region: lines.slice(b + 1, e) };
}

/** `lines` with the region (markers plus `body`) placed just before the `];` closing `GATES`. */
export function placeRegion(lines: readonly string[], body: readonly string[]): string[] | null {
  const start = lines.findIndex((l) => l.startsWith('export const GATES'));
  const close = start === -1 ? -1 : lines.findIndex((l, i) => i > start && l === '];');
  if (close === -1) return null;
  return [...lines.slice(0, close), GBEGIN, ...body, GEND, ...lines.slice(close)];
}

/**
 * The specs of every declared gate the hand entries do not register, sorted by id, plus a named problem for each that cannot be placed. `readSrc` reads a repo-relative file; `workflow` is the workflow text placement is resolved against.
 */
export function headerDeclared(
  declared: readonly Bound[],
  handIds: ReadonlySet<string>,
  readSrc: (rel: string) => string,
  workflow: string
): { specs: GateSpec[]; problems: string[] } {
  const specs: GateSpec[] = [];
  const problems: string[] = [];
  const seen = new Map<string, string>();
  for (const b of declared) {
    if (handIds.has(b.id)) continue;
    const prior = seen.get(b.id);
    if (prior !== undefined) {
      problems.push(`${b.file}: id '${b.id}' is also declared by ${prior}; one id, one header`);
      continue;
    }
    seen.set(b.id, b.file);
    const h = parseGateHeader(readSrc(b.file));
    if (h === null) {
      problems.push(`${b.file}: bound, yet its header no longer parses; rerun after fixing it`);
      continue;
    }
    let job = '';
    if (b.kind === 'shared-step') {
      const owners = jobsWithStep(workflow, b.step ?? '');
      if (owners.length !== 1) {
        problems.push(
          `${b.file}: rides step "${b.step}", which ${owners.length === 0 ? 'no job holds' : `${owners.length} jobs hold`}; a shared-step header needs exactly one`
        );
        continue;
      }
      job = owners[0];
    } else if (b.kind === 'step') {
      const placed =
        b.lane !== undefined ? { lane: b.lane } : placeGate(laneCapabilities(workflow), b.needs);
      if ('error' in placed) {
        problems.push(`${b.file}: ${placed.error}`);
        continue;
      }
      job = placed.lane;
    }
    specs.push(headerSpec(b.file, b.id, { ...h, run: b.run }, job, WORKFLOW_REL));
  }
  specs.sort((x, y) => Number(x.id > y.id) - Number(x.id < y.id));
  return { specs, problems };
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

  // The header-declared region (D2). A fixture header, a fixture workflow with one setup-guarded lane, and the two directions: a header no hand entry registers MUST become an entry, one a hand entry registers must NOT.
  const fxWorkflow = [
    'jobs:',
    '  quality-static:',
    '    steps:',
    '      - id: setup',
    '        run: true',
  ].join('\n');
  const fxSrc = [
    '"""Fixture.',
    '',
    '---- gate ----',
    'step: Probe gate',
    'lane: quality-static',
    'why: fixture',
    '---- end gate ----',
    '"""',
  ].join('\n');
  const fxBound: Bound = {
    file: '.ci/rediacc_ci/quality/probe_gate.py',
    id: 'check:ci-probe-gate',
    run: 'PYTHONPATH=.ci python3 -m rediacc_ci.quality.probe_gate',
    kind: 'step',
    step: 'Probe gate',
    needs: [],
    lane: 'quality-static',
  };
  const fresh = headerDeclared([fxBound], new Set(), () => fxSrc, fxWorkflow);
  const spec = fresh.specs[0];
  check(
    fresh.specs.length === 1 &&
      spec.id === 'check:ci-probe-gate' &&
      spec.run === fxBound.run &&
      spec.leaves.join() === fxBound.file &&
      spec.ci.kind === 'step' &&
      spec.ci.job === 'quality-static' &&
      spec.ci.step === 'Probe gate',
    'CONTROL: a header no hand entry registers becomes one entry, run directly, its file the leaf'
  );
  const held = headerDeclared([fxBound], new Set([fxBound.id]), () => fxSrc, fxWorkflow);
  check(
    held.specs.length === 0 && held.problems.length === 0,
    'CONTROL (silent): a header whose id a hand entry registers is left to that entry'
  );
  const twice = headerDeclared(
    [fxBound, { ...fxBound, file: '.ci/rediacc_ci/quality/probe_gate_copy.py' }],
    new Set(),
    () => fxSrc,
    fxWorkflow
  );
  check(
    twice.specs.length === 1 && twice.problems.some((p) => p.includes('also declared by')),
    'CONTROL: two headers claiming one id are refused by name, never both emitted'
  );
  const unplaced = headerDeclared(
    [{ ...fxBound, kind: 'shared-step', step: 'No such step' }],
    new Set(),
    () => fxSrc,
    fxWorkflow
  );
  check(
    unplaced.specs.length === 0 && unplaced.problems.some((p) => p.includes('no job holds')),
    'CONTROL: a shared-step header riding a step no job holds is a named problem, not an entry'
  );
  check(
    directRun('.ci/rediacc_ci/quality/probe_gate.py') ===
      'PYTHONPATH=.ci python3 -m rediacc_ci.quality.probe_gate' &&
      directRun('scripts/gates/check-probe.ts', true) ===
        'tsx scripts/gates/check-probe.ts --selftest && tsx scripts/gates/check-probe.ts' &&
      directRun('.ci/scripts/quality/check_probe.py') === '.ci/scripts/quality/check_probe.py',
    'CONTROL: a .ci/rediacc_ci module runs as `python3 -m`, a .ts through tsx, any other path as itself'
  );
  check(
    entryRun('check:ci-probe', '.ci/rediacc_ci/quality/probe.py', { 'check:ci-probe': 'x' }) ===
      'npm run check:ci-probe' &&
      entryRun('check:ci-probe', '.ci/rediacc_ci/quality/probe.py', {}) ===
        'PYTHONPATH=.ci python3 -m rediacc_ci.quality.probe',
    'CONTROL: an entry with a package.json key hops through it, one without runs its module directly'
  );
  const text1 = serialiseSpec(spec);
  check(
    text1.includes("    run: 'PYTHONPATH=.ci python3 -m rediacc_ci.quality.probe_gate',") &&
      !text1.includes('npm run'),
    'the serialised entry runs the module itself, with no npm hop'
  );
  const long = serialiseSpec({
    ...spec,
    ci: { kind: 'local-only', blocker: `BLOCKER: ${'x'.repeat(120)}` },
  });
  check(
    long.includes('      blocker:\n        ') && !long.includes("blocker: 'BLOCKER"),
    'CONTROL: a property over 100 columns breaks after the colon, the way biome writes it'
  );
  check(
    lit("it's") === `"it's"` && lit('plain') === "'plain'",
    'CONTROL: a literal holding a single quote takes double quotes, as biome would rewrite it'
  );
  const half = cutRegion(['export const GATES = [', GBEGIN, '];']);
  check('error' in half, 'CONTROL: a region with one marker is refused, never spliced');
  const placed = placeRegion(
    ['x', 'export const GATES = [', '  {', '  },', '];', 'y'],
    ['  {', '  },']
  );
  const back = placed === null ? null : cutRegion(placed);
  check(
    placed !== null &&
      placed.indexOf(GBEGIN) === 4 &&
      back !== null &&
      !('error' in back) &&
      back.hand.join('\n') === ['x', 'export const GATES = [', '  {', '  },', '];', 'y'].join('\n'),
    'CONTROL: the region lands just before `];` and cutting it restores the hand text byte for byte'
  );

  const bindLeg: Leg = { label: 'b', args: ['scripts/gate-bind.ts', '--write'] };
  const lockLeg: Leg = { label: 'l', args: ['scripts/gen/gen-gates-lock.ts', '--write'] };
  const argv = ['--gates', '--write', '--allow-drop', 'Old step'];
  check(
    withAllowDrops(bindLeg, argv).args.join(' ') ===
      'scripts/gate-bind.ts --write --allow-drop Old step' &&
      withAllowDrops(lockLeg, argv) === lockLeg &&
      withAllowDrops(bindLeg, ['--gates', '--write']) === bindLeg,
    'CONTROL: --allow-drop reaches the binder leg only, and nothing is added without it'
  );

  const sLegs = selftestLegs([
    { label: 'a', args: ['scripts/gate-bind.ts', '--dry-run'] },
    { label: 'b', args: ['scripts/gate-bind.ts'] },
    { label: 'c', args: ['scripts/gates/check-ci-parity.ts'] },
    { label: 'd', args: ['scripts/gen/gen-docs.ts'] },
  ]);
  check(
    sLegs.map((l) => l.args.join(' ')).join('|') ===
      'scripts/gate-bind.ts --selftest|scripts/gen/gen-docs.ts --selftest',
    'CONTROL: one selftest leg per distinct leg script, none for a NO_SELFTEST script'
  );
  check(
    CHECK_LEGS.every(
      (l) =>
        NO_SELFTEST.has(l.args[0]) || selftestLegs(CHECK_LEGS).some((s) => s.args[0] === l.args[0])
    ) && [...NO_SELFTEST].every((f) => CHECK_LEGS.some((l) => l.args[0] === f)),
    'CONTROL: every check-leg script has its selftest leg, and NO_SELFTEST names only leg scripts'
  );
  check(
    checkVerdict([
      ['x', 0],
      ['y', 0],
    ]) === 0 &&
      checkVerdict([
        ['x', 0],
        ['y', 3],
      ]) === 1 &&
      checkVerdict([]) === 1,
    'CONTROL: one red leg reds --check, and a run with no legs is red, never a pass'
  );

  return bad === 0 ? 0 : 1;
}

/** The controls over the concurrent leg runner, which is async and so cannot ride `selftest()`. */
async function asyncSelftest(): Promise<number> {
  let bad = 0;
  const check = (ok: boolean, name: string): void => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
    if (!ok) bad++;
  };
  check(
    legWidth({ CI_RUNNER_CORES: '3' }, 24) === 3 &&
      legWidth({}, 24) === 24 &&
      legWidth({ CI_RUNNER_CORES: 'x' }, 6) === 6 &&
      legWidth({ CI_RUNNER_CORES: '0' }, 0) === 1,
    'CONTROL: the granted cores set the width, a missing or malformed grant falls to the machine, never below 1'
  );
  const fx: Leg[] = [10, 1, 5, 0, 3].map((ms, i) => ({ label: String(i), args: [String(ms)] }));
  let live = 0;
  let peak = 0;
  const got = await runPool(fx, 2, async (leg) => {
    live++;
    peak = Math.max(peak, live);
    await new Promise((r) => setTimeout(r, Number(leg.args[0])));
    live--;
    return leg.label;
  });
  check(
    got.join('') === '01234' && peak === 2,
    'CONTROL: the pool returns results in leg order whatever order they finish in, and never runs more than its width'
  );
  const none = await runPool([], 4, async () => 1);
  check(none.length === 0, 'CONTROL: an empty leg list yields no results (checkVerdict reds it)');
  const ran: Leg[] = [];
  const legsFx: Leg[] = [
    { label: 'a', args: ['scripts/gate-bind.ts', '--write'] },
    { label: 'b', args: ['scripts/other.ts'] },
  ];
  const quiet = console.log;
  const quietErr = console.error;
  console.log = () => undefined;
  console.error = () => undefined;
  const stopped = writeLegs(legsFx, [], (leg) => {
    ran.push(leg);
    return leg.label === 'a' ? 3 : 0;
  });
  const wrote: Leg[] = [];
  const clean = writeLegs(legsFx, ['--allow-drop', 'step-x'], (leg) => {
    wrote.push(leg);
    return 0;
  });
  console.log = quiet;
  console.error = quietErr;
  check(
    stopped === 3 && ran.length === 1 && clean === 0 && wrote.length === 2,
    'CONTROL: the write legs stop at the first red one and return its rc, and run every leg when none is red (review 9969e4f0.2)'
  );
  check(
    wrote[0].args.includes('step-x') && !wrote[1].args.includes('step-x'),
    'CONTROL: writeLegs hands --allow-drop to the binder leg and to no other (review 6c817142.1)'
  );
  const hintOf = (labels: string[]): string => redHints(labels).join('|');
  check(
    /regenerating does not help/.test(hintOf(['selftest: x'])) &&
      !/Regenerate with/.test(hintOf(['selftest: x'])) &&
      /Regenerate with/.test(hintOf(['scripts/x.ts'])) &&
      !/regenerating does not help/.test(hintOf(['scripts/x.ts'])) &&
      redHints(['selftest: x', 'scripts/x.ts']).length === 2 &&
      redHints([]).length === 0,
    'CONTROL: a red selftest leg prints the selftest hint only, any other red leg the regenerate hint only (review f4d9c4bf.1)'
  );
  return bad === 0 ? 0 : 1;
}

/** The manifest pass: the `gen-manifest` marker regions over the hand entries, then the `gen-gates` region of header-declared gates. Writes when `write`, else verifies. */
function manifestPass(write: boolean): number {
  const text = fs.readFileSync(MANIFEST, 'utf-8');
  // The `gen-gates` region is OUTPUT too, so it is cut before anything is measured, and its entries leave the imported array with it: what remains is the hand text and the hand entries, which the span scanner below must still pair one to one.
  const cut = cutRegion(text.split('\n'));
  if ('error' in cut) {
    console.error(`gen-manifest: ${cut.error}`);
    return 1;
  }
  const regionIds = new Set(
    cut.region.flatMap((l) => {
      const m = /^ {4}id: '([^']+)',$/.exec(l) ?? /^ {4}id: "([^"]+)",$/.exec(l);
      return m === null ? [] : [m[1]];
    })
  );
  const raw = cut.hand;
  // The markers are the OUTPUT, so they are stripped before anything is measured: otherwise the second run compares the file against a version of itself that already contains its own answer, and could never report drift.
  const isMarker = (l: string): boolean =>
    l.startsWith('  // >>> gen-manifest') || l.startsWith('  // <<< gen-manifest');
  const lines = raw.filter((l) => !isMarker(l));
  const hadMarkers = raw.length !== lines.length;
  const sp = spans(lines);
  const all = (GATES as unknown as Entry[]).filter((g) => !regionIds.has(String(g.id)));

  // The header-declared gates, from every tracked header the binder reads. A scan that finds no header at all is a broken scan (gate-bind refuses the same), and a malformed header would silently drop its gate out of the region, so both refuse.
  const { present, missing } = trackedSubjects();
  if (missing.length > 0) {
    console.error(
      `gen-manifest: ${missing.length} tracked file(s) are absent from the working tree (${missing.slice(0, 3).join(', ')}); refusing to derive the region from a tree the index disagrees with`
    );
    return 1;
  }
  const readRel = (rel: string): string => fs.readFileSync(path.join(ROOT, rel), 'utf-8');
  const scan = scanDeclarations(present, readRel);
  if (scan.malformed.length > 0) {
    for (const m of scan.malformed) console.error(`gen-manifest: malformed header: ${m}`);
    return 1;
  }
  if (scan.declared.length === 0) {
    console.error(
      'gen-manifest: VACUOUS: no tracked file carries a `---- gate ----` header, so the header-declared region cannot be derived; the scan is broken, not empty'
    );
    return 1;
  }
  const handIds = new Set(all.map((g) => String(g.id)));
  const { specs, problems } = headerDeclared(
    scan.declared,
    handIds,
    readRel,
    fs.readFileSync(WORKFLOW, 'utf-8')
  );
  if (problems.length > 0) {
    for (const p of problems) console.error(`gen-manifest: ${p}`);
    return 1;
  }
  const regionBody = specs.flatMap((s) => serialiseSpec(s).split('\n'));

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

  console.log(
    `gen-manifest: ${n} generated, ${all.length - n} hand, ${regions} region(s); ` +
      `${specs.length} gate(s) declared by their header alone, of ${scan.declared.length} header(s) read`
  );
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
  const withRegion = placeRegion(out, regionBody);
  if (withRegion === null) {
    console.error(
      'gen-manifest: no `];` closes `export const GATES` in scripts/ci-runner/manifest.ts, so the header-declared region has nowhere to go'
    );
    return 1;
  }
  const want = withRegion.join('\n');
  if (!write) {
    if (want === text) {
      console.log('gen-manifest: scripts/ci-runner/manifest.ts already matches');
      return 0;
    }
    console.error(
      hadMarkers
        ? 'gen-manifest: the regions in scripts/ci-runner/manifest.ts no longer match what the\n' +
            '  headers derive. An entry inside a region was hand-edited, a header moved, or a\n' +
            '  header-declared gate was added or removed.\n' +
            '  Regenerate with: npm run gen:gates -- --write'
        : 'gen-manifest: scripts/ci-runner/manifest.ts carries no generated regions.\n' +
            '  Emit them with: npm run gen:gates -- --write'
    );
    return 1;
  }
  fs.writeFileSync(MANIFEST, want);
  console.log(
    `gen-manifest: wrote ${r} region(s) and ${specs.length} header-declared entr${specs.length === 1 ? 'y' : 'ies'} into scripts/ci-runner/manifest.ts`
  );
  return 0;
}

/**
 * `gen:gates`: ONE generator and ONE check over every file a gate's declaration is copied into (agent/plans/PLAN-tooling-code-reduction.md D2).
 *
 * `--write` runs the producers in dependency order, each in its own process because each imports the manifest the step before it rewrote: the manifest regions (in this process, before anything imported a stale copy matters), the lock (gen-gates-lock.ts), the workflow regions and shard manifests (gate-bind.ts), the doc tables (gen-docs.ts). The first failure stops the chain, because every later producer reads what the failed one should have written.
 *
 * `--check` (the default) runs every consistency check over those copies and reports EACH leg, so one red leg cannot hide another. A leg's verdict is its exit code; its own output says why.
 */
interface Leg {
  label: string;
  args: string[];
}

const WRITE_LEGS: readonly Leg[] = [
  { label: 'lock', args: ['scripts/gen/gen-gates-lock.ts', '--write'] },
  { label: 'workflow regions and shards', args: ['scripts/gate-bind.ts', '--write'] },
  { label: 'doc tables', args: ['scripts/gen/gen-docs.ts', '--write'] },
];

const CHECK_LEGS: readonly Leg[] = [
  { label: 'lock matches the manifest', args: ['scripts/gen/gen-gates-lock.ts'] },
  {
    label: 'workflow regions and shards match the headers',
    args: ['scripts/gate-bind.ts', '--dry-run', '--fail-on-drift'],
  },
  { label: 'every header binds to its registrations', args: ['scripts/gate-bind.ts'] },
  { label: 'manifest and CI surface agree', args: ['scripts/gates/check-ci-parity.ts'] },
  { label: 'manifest rules', args: ['scripts/gates/check-gate-manifest.ts'] },
  { label: 'doc tables match the lock', args: ['scripts/gen/gen-docs.ts'] },
  { label: 'doc regions', args: ['scripts/gates/check-doc-region-parity.ts'] },
  { label: 'step env', args: ['scripts/gates/check-ci-step-env-parity.ts'] },
  { label: 'no orphan step keys', args: ['scripts/gates/check-workflow-orphan-step-keys.ts'] },
];

/**
 * Leg scripts with no `--selftest` mode, by name. Every other script a check leg runs has its selftest run as its own leg: the gates `--check` replaces each ran `<script> --selftest && <script>`, so a check without the selftests would drop the proof that each leg can fail.
 */
export const NO_SELFTEST: ReadonlySet<string> = new Set(['scripts/gates/check-ci-parity.ts']);

/** One `--selftest` leg per distinct check-leg script, in first-seen order, minus NO_SELFTEST. */
export function selftestLegs(legs: readonly Leg[]): Leg[] {
  const seen = new Set<string>();
  const out: Leg[] = [];
  for (const leg of legs) {
    const script = leg.args[0];
    if (seen.has(script) || NO_SELFTEST.has(script)) continue;
    seen.add(script);
    out.push({ label: `selftest: ${script}`, args: [script, '--selftest'] });
  }
  return out;
}

/** The `--check` verdict: red when any leg is red, and a zero-leg run is red too (nothing was checked). */
export function checkVerdict(verdicts: readonly (readonly [string, number])[]): number {
  if (verdicts.length === 0) return 1;
  return verdicts.some(([, rc]) => rc !== 0) ? 1 : 0;
}

function runLeg(leg: Leg): number {
  const r = spawnSync(process.execPath, [...process.execArgv, ...leg.args], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (r.error !== undefined) {
    console.error(`gen:gates: could not start ${leg.args[0]}: ${r.error.message}`);
    return 1;
  }
  return r.status ?? 1;
}

/**
 * How many `--check` legs run at once: the cores the runner granted (`CI_RUNNER_CORES`, which the pool exports to every gate it admits), else the machine's parallelism, never below 1. The legs only read, so the order they finish in changes nothing but the wall clock: run one after another they cost about 43 s, which priced the check out of the fast lane the eight gates it replaced sat in.
 */
export function legWidth(env: NodeJS.ProcessEnv, machine: number): number {
  const granted = Number.parseInt(env.CI_RUNNER_CORES ?? '', 10);
  const n = Number.isInteger(granted) && granted > 0 ? granted : machine;
  return Math.max(1, Math.floor(n));
}

/** One leg in a child process with its output captured, so concurrent legs never interleave; the caller prints it whole. A leg that cannot start is rc 1 with the reason as its output. */
function runLegCaptured(leg: Leg): Promise<{ rc: number; out: string }> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    const child = spawn(process.execPath, [...process.execArgv, ...leg.args], {
      cwd: ROOT,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.stdout.on('data', (b: Buffer) => chunks.push(b));
    child.stderr.on('data', (b: Buffer) => chunks.push(b));
    child.on('error', (e) =>
      resolve({ rc: 1, out: `gen:gates: could not start ${leg.args[0]}: ${e.message}\n` })
    );
    child.on('close', (code, signal) =>
      resolve({
        rc: code ?? 1,
        out: Buffer.concat(chunks).toString('utf-8') + (signal ? `killed by ${signal}\n` : ''),
      })
    );
  });
}

/** Run `legs` at most `width` at a time, results in leg order whatever order they finish in. */
export async function runPool<T>(
  legs: readonly Leg[],
  width: number,
  run: (leg: Leg) => Promise<T>
): Promise<T[]> {
  const out: T[] = new Array(legs.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    while (next < legs.length) {
      const i = next++;
      out[i] = await run(legs[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, width), legs.length) }, worker));
  return out;
}

/**
 * `--allow-drop <step>` reaches the binder's write leg and no other. Retiring a header-declared gate removes its step from a region, and gate-bind refuses an unnamed removal (a dropped step takes its `env:` and secrets with it, invisibly); without this the generator could add a gate and never retire one.
 */
export function withAllowDrops(leg: Leg, argv: readonly string[]): Leg {
  if (leg.args[0] !== 'scripts/gate-bind.ts') return leg;
  const drops = argv.flatMap((a, i) =>
    a === '--allow-drop' && argv[i + 1] !== undefined ? ['--allow-drop', argv[i + 1]] : []
  );
  return drops.length === 0 ? leg : { ...leg, args: [...leg.args, ...drops] };
}

/** The `--write` legs in order, stopping at the first red one: its rc, or 0 when every leg ran clean. The binder leg receives `--allow-drop` through withAllowDrops. `run` is the seam the selftest drives (review 9969e4f0.2, 6c817142.1). */
export function writeLegs(
  legs: readonly Leg[],
  argv: readonly string[],
  run: (leg: Leg) => number
): number {
  for (const leg of legs) {
    console.log(`gen:gates --write: ${leg.label}`);
    const rc = run(withAllowDrops(leg, argv));
    if (rc !== 0) {
      console.error(`gen:gates --write: STOPPED at "${leg.label}" (rc=${rc}); later legs not run`);
      return rc;
    }
  }
  return 0;
}

/** What a red `--check` prints: a selftest leg red means the check cannot be trusted and regenerating does not help; any other red leg means a declaration copy drifted and regenerating does (review f4d9c4bf.1). */
export function redHints(redLabels: readonly string[]): string[] {
  const hints: string[] = [];
  if (redLabels.some((label) => label.startsWith('selftest: ')))
    hints.push(
      'gen:gates --check: a leg script failed its own selftest, so its check cannot be trusted. Run the named script with --selftest and fix the control it reports; regenerating does not help.'
    );
  if (redLabels.some((label) => !label.startsWith('selftest: ')))
    hints.push(
      'gen:gates --check: a declaration copy disagrees with its source. Regenerate with: npm run gen:gates -- --write'
    );
  return hints;
}

async function gates(argv: string[]): Promise<number> {
  const write = argv.includes('--write');
  if (write && argv.includes('--check')) {
    console.error('gen:gates: --write and --check are exclusive');
    return 2;
  }
  for (const leg of [...WRITE_LEGS, ...CHECK_LEGS]) {
    if (!fs.existsSync(path.join(ROOT, leg.args[0]))) {
      console.error(`gen:gates: leg "${leg.label}" names ${leg.args[0]}, which does not exist`);
      return 1;
    }
  }
  console.log(`gen:gates ${write ? '--write' : '--check'}: manifest`);
  const first = manifestPass(write);
  if (write) {
    if (first !== 0) return first;
    const wrote = writeLegs(WRITE_LEGS, argv, runLeg);
    if (wrote !== 0) return wrote;
    console.log(
      `gen:gates --write: ${WRITE_LEGS.length + 1} producer(s) ran; now run: npm run gen:gates -- --check`
    );
    return 0;
  }
  const verdicts: [string, number][] = [
    ['manifest regions match the headers', first],
    ['selftest: scripts/gen/gen-manifest.ts', selftest() || (await asyncSelftest())],
  ];
  const legs = [...selftestLegs(CHECK_LEGS), ...CHECK_LEGS];
  const width = legWidth(process.env, os.availableParallelism());
  console.log(`gen:gates --check: ${legs.length} leg(s), ${width} at a time`);
  const results = await runPool(legs, width, runLegCaptured);
  legs.forEach((leg, i) => {
    console.log(`gen:gates --check: ${leg.label}`);
    process.stdout.write(results[i].out);
    verdicts.push([leg.label, results[i].rc]);
  });
  const red = verdicts.filter(([, rc]) => rc !== 0);
  console.log(`\ngen:gates --check: ${verdicts.length} leg(s), ${red.length} red`);
  for (const [label, rc] of verdicts)
    console.log(`  ${rc === 0 ? 'PASS' : 'FAIL'}  ${label}${rc === 0 ? '' : ` (rc=${rc})`}`);
  if (checkVerdict(verdicts) !== 0) {
    for (const hint of redHints(red.map(([label]) => label))) console.error(hint);
    return 1;
  }
  return 0;
}

async function main(argv: string[]): Promise<number> {
  if (argv.includes('--selftest')) return (await asyncSelftest()) === 0 ? selftest() : 1;
  if (argv.includes('--gates')) return gates(argv);
  return manifestPass(argv.includes('--write'));
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (e: unknown) => {
    console.error(`gen-manifest: ${e instanceof Error ? (e.stack ?? e.message) : String(e)}`);
    process.exit(1);
  }
);
