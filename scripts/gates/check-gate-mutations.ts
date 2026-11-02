#!/usr/bin/env tsx
/**
 * check:ci-gate-mutations - each registered gate must go RED on a planted copy of the
 * regression it exists to catch, and GREEN on the real tree.
 *
 * WHY THIS EXISTS (testing-surface-audit F6, agent/plans/PLAN-backup-program.md A4b).
 * Every gate in this repo proves its own DETECTOR with an in-process control: a synthetic
 * string, a fake layer, a temp file. That proves the helper fires on the fixture its author
 * wrote. It does not prove the gate fires on the REAL file when the REAL code regresses,
 * which is the claim a green tick makes. The two diverge whenever the spelling the gate
 * matches drifts from the spelling the code uses: check-retention-knob-parity records two
 * such drafts in its own comments (a bare `includes(knob)` that stayed green when the sweep
 * stopped honouring keepWeekly, and a `policy.keepLast` match that survived disabling the
 * slice). Each was found by hand. This gate makes the hand check a standing one.
 *
 * WHAT A REGISTRY ENTRY IS. One per gate: the files the gate reads, and an exact
 * find/replace in ONE of them that re-creates the gate's headline defect. Three gate runs
 * (1-3) and one check of the mutant's output (4) decide the verdict, and only one
 * combination is a pass:
 *
 *   1. the gate on the REAL tree              must exit 0   (else: baseline-red)
 *   2. the gate copied into a pristine sandbox must exit 0   (else: sandbox-red; the
 *      `inputs` list is short and the copy is missing a file the gate reads)
 *   3. the same sandbox with the mutant applied must exit non-zero (else: UNSEEN, the
 *      verdict this gate exists for: a regression the gate cannot see)
 *   4. and that red output must carry `expect` (else: wrong-reason; red for a crash or
 *      an unrelated finding proves nothing about the defect)
 *
 * Run 2 is what makes run 3 mean anything. A sandbox missing one input makes the gate red
 * for "cannot read", which reads exactly like a caught mutant; the pristine run is the
 * baseline that catches a broken fixture, the same reason .ci/scripts/test/mutate-check.sh
 * insists on both directions.
 *
 * WHY THE GATE IS COPIED, NOT POINTED. The registered gates resolve their root from their
 * own location (`join(<script dir>, '..', '..')`). A copy at `<sandbox>/scripts/gates/`
 * therefore reads `<sandbox>/...` with no seam added to the gate under test, so the code
 * that runs in the sandbox is byte-identical to the code CI runs. The mutation never touches
 * the working tree, which other sessions share.
 *
 * WHY THE REGISTRY LIVES HERE AND NOT ON GateSpec. A `mutation` field on GateSpec would be
 * a hand-only manifest field (gen-manifest.ts HAND_ONLY) carrying multi-line source text into
 * gates.lock.json. Kept here, it is selftested with the harness that reads it, and
 * `registryProblems` ties every entry back to the lock: an id the lock does not carry, or a
 * leaf that is no longer the gate's leaf, fails this gate rather than going stale.
 *
 * ADDING AN ENTRY: append to REGISTRY. `find` must occur exactly once in `file`, `file` must
 * be one of the expanded `inputs`, and the mutant must be a regression a reviewer would
 * recognise, never a deletion of the whole file.
 *
 * Run: npx tsx scripts/gates/check-gate-mutations.ts [--selftest]
 *
 * ---- gate ----
 * step: Gate mutations
 * needs: node, submodules
 * selftest: true
 * ---- end gate ----
 */
import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { globSync } from 'glob';
import { GREEN, NC, RED } from '../lib/console.js';
import { type ControlCase, refuse, refused, summarizeControls } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { REPO_ROOT } from '../lib/repo-root.js';

const LOCK = 'scripts/ci-runner/gates.lock.json';
/** Probed before any run, so a missing loader is a named failure rather than every gate "red". */
const TSX_PKG = join(REPO_ROOT, 'node_modules/tsx/package.json');

export interface GateMutation {
  /** The gate's npm id; must be a `gate: true` entry in gates.lock.json. */
  gate: string;
  /** The script that IS the gate; must be that lock entry's only leaf. */
  leaf: string;
  /** Repo-relative files or globs the gate reads. Copied into the sandbox. */
  inputs: string[];
  /** The one file the mutant edits; must be among the expanded inputs. */
  file: string;
  /** Exact text, present exactly once in `file`. */
  find: string;
  /** What the code looks like once the defect is back. */
  replace: string;
  /** A substring the mutant's red output must carry. */
  expect: string;
  /** The regression the mutant re-creates, in one line. */
  defect: string;
}

/**
 * The backup gates (A4b names these four). Each mutant re-creates the incident its gate's
 * header describes, in the file that incident lived in.
 */
export const REGISTRY: GateMutation[] = [
  {
    gate: 'check:ci-no-client-key-composition',
    leaf: 'scripts/gates/check-no-client-key-composition.ts',
    inputs: ['private/renet/pkg/chunkstore/**/*.go', 'private/renet/cmd/renet/**/*.go'],
    file: 'private/renet/pkg/chunkstore/session.go',
    find: 'if w.ChunkPrefix == "" {\n\t\treturn "", fmt.Errorf(\n\t\t\t"grant carried no chunkPrefix',
    replace:
      'if w.ChunkPrefix == "" {\n\t\treturn w.Prefix + "c/", nil\n\t}\n\tif false {\n\t\treturn "", fmt.Errorf(\n\t\t\t"grant carried no chunkPrefix',
    expect: 'the client composes object keys',
    defect: 'the write grant falls back to composing `prefix + "c/"` when chunkPrefix is absent',
  },
  {
    gate: 'check:ci-backup-protocol-conformance',
    leaf: 'scripts/gates/check-backup-protocol-conformance.ts',
    inputs: [
      'private/account/src/routes/backups.ts',
      'private/account/src/dto/backup.dto.ts',
      'private/renet/pkg/chunkstore/session.go',
      'private/renet/pkg/chunkstore/repair.go',
    ],
    file: 'private/renet/pkg/chunkstore/session.go',
    find: 'Existing []string `json:"existing"`',
    replace: 'Missing []string `json:"missing"`',
    expect: '/exists field "existing"',
    defect: 'the /exists client decodes `missing` again, so a nil list reads as "upload nothing"',
  },
  {
    gate: 'check:ci-backup-manifest-shape-parity',
    leaf: 'scripts/gates/check-backup-manifest-shape-parity.ts',
    inputs: [
      'private/renet/pkg/chunkstore/manifest.go',
      'private/account/src/services/backup-gc.service.ts',
    ],
    file: 'private/renet/pkg/chunkstore/manifest.go',
    find: 'type Manifest struct {\n',
    replace: 'type Manifest struct {\n\tExtents []string `json:"extents,omitempty"`\n',
    expect: 'extents',
    defect: "renet's Manifest grows a field the account parser was never told about",
  },
  {
    gate: 'check:ci-retention-knob-parity',
    leaf: 'scripts/gates/check-retention-knob-parity.ts',
    inputs: [
      'package.json',
      'packages/shared/src/config-schema/schemas.ts',
      'private/account/src/dto/backup.dto.ts',
      'private/account/src/services/backup-gc.service.ts',
      'packages/cli/src/commands/backup-retention-commands.ts',
    ],
    file: 'private/account/src/services/backup-gc.service.ts',
    find: "  { knob: 'keepWeekly', key: (c) => isoWeekKey(new Date(c)) },\n",
    replace: '',
    expect: 'missing: keepWeekly',
    defect: 'the sweep stops honouring keepWeekly while the schema, DTO and CLI still accept it',
  },
];

// ── Pure helpers (exported for the selftest) ───────────────────────────────

/** Apply `find` -> `replace` exactly once, or say why it cannot be applied. */
export function applyMutation(
  source: string,
  find: string,
  replace: string
): { ok: true; text: string } | { ok: false; why: string } {
  if (find === '') return { ok: false, why: '`find` is empty' };
  if (find === replace)
    return { ok: false, why: '`replace` equals `find`, so the mutant is the source' };
  const hits = source.split(find).length - 1;
  if (hits !== 1) {
    return {
      ok: false,
      why: `\`find\` occurs ${hits} time(s), expected exactly 1; the code moved, so update the entry to match it`,
    };
  }
  return { ok: true, text: source.replace(find, () => replace) };
}

export interface RunResult {
  code: number | null;
  output: string;
}

export type Verdict = 'ok' | 'baseline-red' | 'sandbox-red' | 'unseen' | 'wrong-reason';

/** The four-run decision described in the header. Only one combination is `ok`. */
export function verdict(
  baseline: RunResult,
  pristine: RunResult,
  mutant: RunResult,
  expect: string
): Verdict {
  if (baseline.code !== 0) return 'baseline-red';
  if (pristine.code !== 0) return 'sandbox-red';
  if (mutant.code === 0) return 'unseen';
  if (!mutant.output.includes(expect)) return 'wrong-reason';
  return 'ok';
}

interface LockEntry {
  id: string;
  gate: boolean;
  leaves: string[];
}

/** Static problems with the registry itself, checked against the lock before anything runs. */
export function registryProblems(registry: GateMutation[], lock: LockEntry[]): string[] {
  const out: string[] = [];
  if (registry.length === 0)
    out.push('VACUOUS: the registry is empty, so this gate would verify nothing');
  const seen = new Set<string>();
  for (const m of registry) {
    if (seen.has(m.gate)) out.push(`${m.gate}: registered twice`);
    seen.add(m.gate);
    const entry = lock.find((e) => e.id === m.gate);
    if (!entry) {
      out.push(
        `${m.gate}: not in ${LOCK}; the gate was renamed or removed, so update or drop the entry`
      );
    } else {
      if (!entry.gate) out.push(`${m.gate}: the lock entry is not \`gate: true\``);
      if (entry.leaves.length !== 1 || entry.leaves[0] !== m.leaf) {
        out.push(
          `${m.gate}: leaf ${m.leaf} is not the lock entry's only leaf (${entry.leaves.join(', ')})`
        );
      }
    }
    if (m.inputs.length === 0) out.push(`${m.gate}: no inputs declared`);
    if (m.expect.trim() === '') out.push(`${m.gate}: empty \`expect\`, so any red would count`);
  }
  return out;
}

/** Expand `inputs` against `root`. A literal that is absent, or a glob matching nothing, is a problem. */
export function expandInputs(
  root: string,
  inputs: string[]
): { files: string[]; problems: string[] } {
  const files = new Set<string>();
  const problems: string[] = [];
  for (const pattern of inputs) {
    if (/[*?[{]/.test(pattern)) {
      const hits = globSync(pattern, { cwd: root, nodir: true });
      if (hits.length === 0) problems.push(`VACUOUS: glob ${pattern} matches no file`);
      for (const h of hits) files.add(h);
    } else if (existsSync(join(root, pattern)) && statSync(join(root, pattern)).isFile()) {
      files.add(pattern);
    } else {
      problems.push(`input ${pattern} does not exist`);
    }
  }
  return { files: [...files].sort((a, b) => a.localeCompare(b)), problems };
}

// ── The harness ────────────────────────────────────────────────────────────

/** `node --import tsx <script>`: the loader resolves from `cwd`, which is the repo or a sandbox linking its node_modules. */
function runGate(script: string, cwd: string): RunResult {
  const r = spawnSync(process.execPath, ['--import', 'tsx', script], {
    cwd,
    encoding: 'utf8',
    env: process.env,
    timeout: 120_000,
  });
  if (r.error) return { code: null, output: `spawn failed: ${r.error.message}` };
  return { code: r.status, output: `${r.stdout ?? ''}${r.stderr ?? ''}` };
}

/** A fresh sandbox holding the gate script and its inputs, at their repo-relative paths. */
function buildSandbox(m: GateMutation, files: string[]): string {
  const box = mkdtempSync(join(tmpdir(), `gate-mutations-${process.pid}-`));
  // The gates import npm packages (`glob`); node resolves them by walking up from the copy.
  symlinkSync(join(REPO_ROOT, 'node_modules'), join(box, 'node_modules'), 'dir');
  for (const rel of [m.leaf, ...files]) {
    mkdirSync(dirname(join(box, rel)), { recursive: true });
    copyFileSync(join(REPO_ROOT, rel), join(box, rel));
  }
  return box;
}

const sandboxes = new Set<string>();
function dropSandbox(box: string): void {
  // tree-write: safe every `box` comes from buildSandbox's mkdtempSync under os.tmpdir(), never the tree
  rmSync(box, { recursive: true, force: true });
  sandboxes.delete(box);
}

export interface Outcome {
  verdict: Verdict;
  detail: string;
}

/** Run the four legs for one entry. Throws only on a harness defect (unappliable mutant). */
export function evaluate(m: GateMutation): Outcome {
  const { files, problems } = expandInputs(REPO_ROOT, m.inputs);
  if (problems.length > 0) {
    return { verdict: 'sandbox-red', detail: problems.join('; ') };
  }
  if (!files.includes(m.file)) {
    return { verdict: 'sandbox-red', detail: `${m.file} is not among the expanded inputs` };
  }
  const baseline = runGate(join(REPO_ROOT, m.leaf), REPO_ROOT);
  const box = buildSandbox(m, files);
  sandboxes.add(box);
  try {
    const pristine = runGate(join(box, m.leaf), box);
    const target = join(box, m.file);
    const applied = applyMutation(readFileSync(target, 'utf8'), m.find, m.replace);
    if (!applied.ok)
      return { verdict: 'sandbox-red', detail: `mutant not applied: ${applied.why}` };
    writeFileSync(target, applied.text);
    const mutant = runGate(join(box, m.leaf), box);
    const v = verdict(baseline, pristine, mutant, m.expect);
    const tail = (r: RunResult): string =>
      r.output.trim().split('\n').slice(0, 6).join('\n        ');
    const detail =
      v === 'baseline-red'
        ? `the gate is red on the real tree (exit ${baseline.code}):\n        ${tail(baseline)}`
        : v === 'sandbox-red'
          ? `the UNMUTATED sandbox is red (exit ${pristine.code}); an input is missing from \`inputs\`:\n        ${tail(pristine)}`
          : v === 'unseen'
            ? `the gate stayed GREEN with the defect planted (${m.defect}):\n        ${tail(mutant)}`
            : v === 'wrong-reason'
              ? `red (exit ${mutant.code}) but the output never says "${m.expect}":\n        ${tail(mutant)}`
              : `red then green (mutant exit ${mutant.code}, ${files.length} input file(s))`;
    return { verdict: v, detail };
  } finally {
    dropSandbox(box);
  }
}

function readLock(): LockEntry[] {
  const raw: unknown = JSON.parse(readFileSync(join(REPO_ROOT, LOCK), 'utf8'));
  if (!Array.isArray(raw)) refuse(`✗ ${LOCK} is not a JSON array; cannot tie the registry to it.`);
  return raw as LockEntry[];
}

function preflight(): void {
  if (!existsSync(TSX_PKG)) {
    refuse(
      `✗ ${TSX_PKG} is missing, so no registered gate can be run.`,
      '  Fix: npm install && npm run install:natives'
    );
  }
}

// ── Selftest ───────────────────────────────────────────────────────────────

function selftest(): number {
  preflight();
  const green: RunResult = { code: 0, output: '✓ fine' };
  const red = (o: string): RunResult => ({ code: 1, output: o });
  const lock: LockEntry[] = REGISTRY.map((m) => ({ id: m.gate, gate: true, leaves: [m.leaf] }));
  const knob = REGISTRY.find((m) => m.gate === 'check:ci-retention-knob-parity');
  if (!knob) refuse('✗ selftest: the retention entry the end-to-end controls use is gone.');

  const once = applyMutation('a b c', 'b', 'X');
  const cases: ControlCase[] = [
    { name: 'applyMutation: exactly one hit is applied', ok: once.ok && once.text === 'a X c' },
    { name: 'applyMutation: zero hits is refused', ok: !applyMutation('a b c', 'z', 'X').ok },
    { name: 'applyMutation: two hits is refused', ok: !applyMutation('b b', 'b', 'X').ok },
    { name: 'applyMutation: replace == find is refused', ok: !applyMutation('a b', 'b', 'b').ok },
    {
      name: 'applyMutation: `$&` in replace is literal, not a pattern',
      ok: (() => {
        const r = applyMutation('a b', 'b', '$&$&');
        return r.ok && r.text === 'a $&$&';
      })(),
    },
    {
      name: 'verdict: red mutant with the needle is ok',
      ok: verdict(green, green, red('x NEEDLE'), 'NEEDLE') === 'ok',
    },
    {
      name: 'verdict: green mutant is UNSEEN',
      ok: verdict(green, green, green, 'NEEDLE') === 'unseen',
    },
    {
      name: 'verdict: red mutant without the needle is wrong-reason',
      ok: verdict(green, green, red('crash'), 'NEEDLE') === 'wrong-reason',
    },
    {
      name: 'verdict: red pristine sandbox is sandbox-red',
      ok: verdict(green, red('x'), red('NEEDLE'), 'NEEDLE') === 'sandbox-red',
    },
    {
      name: 'verdict: red real tree is baseline-red',
      ok: verdict(red('x'), green, red('NEEDLE'), 'NEEDLE') === 'baseline-red',
    },
    {
      name: 'verdict: a spawn failure (null code) is never ok',
      ok: verdict({ code: null, output: '' }, green, red('NEEDLE'), 'NEEDLE') !== 'ok',
    },
    {
      name: 'registryProblems: the real registry against a matching lock is clean',
      ok: registryProblems(REGISTRY, lock).length === 0,
    },
    {
      name: 'registryProblems: an empty registry is a problem',
      ok: registryProblems([], lock).length > 0,
    },
    {
      name: 'registryProblems: a gate missing from the lock is a problem',
      ok: registryProblems(REGISTRY, lock.slice(1)).length === 1,
    },
    {
      name: 'registryProblems: a leaf that drifted is a problem',
      ok: registryProblems([{ ...knob, leaf: 'scripts/gates/elsewhere.ts' }], lock).length === 1,
    },
    {
      name: 'registryProblems: a duplicate entry is a problem',
      ok: registryProblems([knob, knob], lock).length === 1,
    },
    {
      name: 'expandInputs: an absent literal is a problem',
      ok: expandInputs(REPO_ROOT, ['no/such/file.ts']).problems.length === 1,
    },
    {
      name: 'expandInputs: a glob matching nothing is a problem',
      ok: expandInputs(REPO_ROOT, ['no/such/**/*.zz']).problems.length === 1,
    },
  ];

  // END TO END, on the real harness and a real gate, both directions. These are the
  // controls that matter: the pure cases above prove the helpers, these prove the gate.
  const real = evaluate(knob);
  cases.push({
    name: `end to end: the registered retention mutant is red-then-green (${real.verdict})`,
    ok: real.verdict === 'ok',
    detail: real.detail,
  });
  const invisible = evaluate({
    ...knob,
    replace: knob.find.replace('},\n', '}, /* behaviour-neutral */\n'),
    defect: 'CONTROL: a comment-only edit the gate must not see',
  });
  cases.push({
    name: `end to end: a mutant the gate cannot see is reported UNSEEN (${invisible.verdict})`,
    ok: invisible.verdict === 'unseen',
    detail: invisible.detail,
  });
  const broken = evaluate({ ...knob, inputs: knob.inputs.filter((i) => i !== 'package.json') });
  cases.push({
    name: `end to end: a sandbox missing an input is sandbox-red, never a caught mutant (${broken.verdict})`,
    ok: broken.verdict === 'sandbox-red',
    detail: broken.detail,
  });
  return summarizeControls(cases);
}

// ── Real run ───────────────────────────────────────────────────────────────

function main(): number {
  preflight();
  const problems = registryProblems(REGISTRY, readLock());
  if (problems.length > 0) {
    return refused(
      `✗ the mutation registry is out of step with ${LOCK} (${problems.length}):`,
      ...problems.map((p) => `    ${p}`)
    );
  }
  let failed = 0;
  for (const m of REGISTRY) {
    const o = evaluate(m);
    if (o.verdict === 'ok') {
      console.log(`  ${GREEN}PASS${NC}  ${m.gate}: ${o.detail}`);
    } else {
      failed += 1;
      console.error(`  ${RED}FAIL${NC}  ${m.gate} [${o.verdict}]\n        ${o.detail}`);
    }
  }
  if (failed > 0) {
    return refused(
      `\n✗ ${failed}/${REGISTRY.length} registered gate(s) did not go red-then-green.`,
      '  UNSEEN means the gate passes with its own headline defect planted: sharpen what',
      '  the gate matches until the mutant turns it red. sandbox-red means `inputs` is',
      '  missing a file the gate reads. baseline-red means the gate is red on the tree',
      '  already; fix that first. Never weaken the mutant to make this pass.'
    );
  }
  console.log(
    `✓ ${REGISTRY.length} gate(s) red on their planted defect and green on the tree ` +
      `(${REGISTRY.length * 3} gate runs, 0 unseen)`
  );
  return 0;
}

if (isEntryPoint(import.meta.filename)) {
  for (const sig of ['SIGINT', 'SIGTERM'] as const) {
    process.on(sig, () => {
      for (const box of [...sandboxes]) dropSandbox(box);
      process.exit(130);
    });
  }
  process.exit(process.argv.includes('--selftest') ? selftest() : main());
}
