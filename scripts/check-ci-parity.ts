#!/usr/bin/env node
/**
 * Bidirectional parity between the local gate set and the CI quality surface.
 *
 * WHY ONE GATE AND NOT THREE. There are three relations between the three sets
 * K (`check:ci-*` keys defined in package.json), C (what a local run executes)
 * and W (what the CI quality surface executes):
 *
 *   R1  K -> C   a defined gate must actually run          (was check-gate-reachability.ts)
 *   R2  W -> C   a CI-run gate must run locally too        (was check-ci-chain-parity.ts)
 *   R3  C -> W   a locally-run gate must run in CI         (was NOBODY, which is #549)
 *
 * Patching a third script in would leave three tools disagreeing about how to
 * resolve a gate, and the resolution logic is exactly where the bugs live. So
 * this file subsumes and replaces both predecessors: one resolver, seven
 * assertions, all evaluated before exiting so one run reports everything.
 *
 * C IS THE MANIFEST, NOT A STRING. Both predecessors parsed the `&&` chain at
 * package.json `scripts.ci` as their input. Once that key becomes a runner
 * invocation the chain is empty and both would have passed over everything --
 * manufacturing #549 at scale. scripts/ci-runner/manifest.ts is the input now.
 *
 * THE MEASUREMENT TRAP THIS EXISTS TO AVOID. The first version of the analysis
 * behind this gate reported ZERO findings because it regexed whole workflow
 * FILE TEXT for `npm run <key>`, and ci-quality.yml carried a step whose NAME
 * contained the literal `npm run ci`. Expanding that as an invocation made the
 * whole chain "CI-executed" and the reverse direction vacuously empty. Hence:
 *
 *   1. Parse `run:` blocks, never whole-file text. A step `name:`, an `env:`
 *      value, an `if:` expression and a YAML comment are not invocations.
 *   2. `npm run ci` / `npm run quality` inside the surface is an ERROR, never
 *      coverage -- it would make every other assertion vacuous.
 *   3. The control below runs before the real check on EVERY invocation.
 *
 * COVERAGE VIA A TEST IS DECLARED, NEVER INFERRED. run-all.sh runs 57 gate
 * tests, and grepping them for a script name is precisely how #549 would have
 * been greenwashed: check-jq-boolean-default.ts is NAMED by
 * test-gate-anti-vacuity.sh:104 and that test ran green in CI for weeks while
 * the real scan never executed once. Mentioning a script is not executing it.
 * So `ci.kind: 'test'` carries a BLOCKER naming the line that proves the real
 * scan runs against the real tree.
 *
 * TEST SEAMS. CI_PARITY_ROOT overrides the repo root; CI_PARITY_MANIFEST reads
 * the gate list from a JSON file instead of the compiled manifest, so a fixture
 * can drive both inputs without touching a tracked file.
 * ESCAPE HATCH. .ci-parity-exempt, direction-tagged and BLOCKER-gated.
 *
 * Usage: npx tsx scripts/check-ci-parity.ts
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type CiCoverage, GATES, type GateSpec, paritySurface } from './ci-runner/manifest.js';
import {
  type BlockeredEntry,
  parseBlockeredList,
  validateBlockerQuality,
} from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.CI_PARITY_ROOT || path.resolve(__dirname, '..');
const EXEMPT_FILE = '.ci-parity-exempt';
const BATTERY_DIR = '.ci/scripts/test/gates';
const BATTERY_RUNNER = '.ci/scripts/test/run-all.sh';

/**
 * Widened from the predecessor's `.ci/scripts/(quality|security)/check-*.sh`.
 * That pattern could not see test-write-once-guard.sh or test-install-script.sh,
 * which ran in Quality/Static and nowhere else (plan finding F3).
 */
const GATE_SHAPED =
  /^(?:\.ci\/scripts\/(?:quality|security)\/check-[\w.-]+\.sh|\.ci\/scripts\/test\/test-[\w.-]+\.sh)$/;

const RED = '[31m';
const GREEN = '[32m';
const NC = '[0m';

// ---------------------------------------------------------------------------
// Command resolution
// ---------------------------------------------------------------------------

/** Words that prefix a command without being one. */
const NOISE = new Set(['sudo', 'time', 'env', 'exec']);

/**
 * Quotes are neutralised BEFORE splitting on shell metacharacters.
 * check:ci-account-no-admin-role's body carries a `\|` alternation inside a
 * double-quoted grep pattern; splitting first tore that pattern into a bogus
 * second command. Double quotes go first because a `node -e "...'fs'..."` body
 * carries single quotes inside the double-quoted program.
 */
function stripQuoted(cmd: string): string {
  return cmd.replace(/"(?:[^"\\]|\\.)*"/g, '""').replace(/'[^']*'/g, "''");
}

function splitSegments(cmd: string): string[] {
  return cmd
    .split(/\n|&&|\|\||;|(?<!\|)\|(?!\|)/g)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** A path-shaped token is recorded repo-relative; a bare tool name is not. */
function scoped(tok: string, scope: string): string {
  const t = tok.replace(/^\.\//, '');
  if (!t.includes('/') && !/\.[cm]?[jt]sx?$/.test(t) && !t.endsWith('.sh')) return t;
  return scope ? path.posix.join(scope, t) : t;
}

interface ScriptUniverse {
  /** repo-relative dir ('' = root) -> that manifest's scripts */
  byDir: Map<string, Record<string, string>>;
  /** package name -> repo-relative dir */
  nameToDir: Map<string, string>;
}

/**
 * The leaf commands a shell command ultimately executes, with `npm run`
 * expanded transitively through root and workspace manifests.
 *
 * COMPARE LEAVES, NOT KEYS. CI runs `npm run typecheck` while the gate set
 * names `check:types`, and CI runs `npm run version:check` while the gate set
 * names `check:version` -- identical bodies, different keys. A key-level
 * comparison reports those as breaks; a leaf-level one does not.
 */
function resolveLeaves(
  cmd: string,
  u: ScriptUniverse,
  scope = '',
  seen = new Set<string>()
): string[] {
  const out: string[] = [];
  let curScope = scope;
  for (const rawSeg of splitSegments(stripQuoted(cmd))) {
    let toks = rawSeg.split(/\s+/).filter(Boolean);
    while (toks.length > 0) {
      const t = toks[0] ?? '';
      // `cd X` moves the manifest scope: `cd workers/www && npm run test:unit`
      // resolves that key in workers/www's manifest, not the root one.
      if (t === 'cd') {
        curScope = path.posix.normalize(path.posix.join(curScope, toks[1] ?? '.'));
        if (curScope === '.') curScope = '';
        toks = toks.slice(2);
        continue;
      }
      if (t === '!' || /^[A-Za-z_][A-Za-z0-9_]*=/.test(t)) {
        toks = toks.slice(1);
        continue;
      }
      if (NOISE.has(t)) {
        toks = toks.slice(1);
        continue;
      }
      break;
    }
    if (toks.length === 0) continue;
    const prog = toks[0] ?? '';
    const rest = toks.slice(1);

    if (prog === 'npm' && (rest[0] === 'run' || rest[0] === 'test')) {
      const key = rest[0] === 'test' ? 'test' : (rest[1] ?? '');
      const wsIdx = rest.findIndex((t) => t === '-w' || t === '--workspace');
      const eq = rest.find((t) => t.startsWith('--workspace='));
      const ws = eq
        ? eq.slice('--workspace='.length)
        : wsIdx >= 0
          ? (rest[wsIdx + 1] ?? undefined)
          : undefined;
      const nextScope = ws ? (u.nameToDir.get(ws) ?? curScope) : curScope;
      const sig = `${nextScope}\0${key}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      const body = (u.byDir.get(nextScope) ?? {})[key];
      if (body === undefined) out.push(`missing-script:${ws ?? (nextScope || 'root')}:${key}`);
      else out.push(...resolveLeaves(body, u, nextScope, seen));
      continue;
    }

    if (prog === 'npx' || prog === 'tsx' || prog === 'node') {
      let target: string | undefined;
      for (const a of rest) {
        if (a === '-e' || a === '--eval' || a === '-p') {
          target = prog;
          break;
        }
        if (a.startsWith('-')) continue;
        target = a;
        break;
      }
      if (target === undefined) out.push(prog);
      else if (prog === 'npx' && !target.includes('/') && !/\.[cm]?[jt]sx?$/.test(target)) {
        out.push(target); // a bare tool run through npx
      } else out.push(scoped(target, curScope));
      continue;
    }

    // Transparent wrapper: run-external-gate.sh executes its arguments and
    // only changes what a FAILURE means (soft on schedule vs hard on a PR),
    // never what runs. The leaf is the wrapped command; reporting the wrapper
    // itself would make every external gate's CI pointer "run something else"
    // the moment it adopted the wrapper.
    if (prog.endsWith('run-external-gate.sh')) {
      out.push(...resolveLeaves(rest.join(' '), u, curScope, seen));
      continue;
    }

    out.push(scoped(prog, curScope));
  }
  return [...new Set(out)];
}

// ---------------------------------------------------------------------------
// Workflow parsing -- run: blocks only
// ---------------------------------------------------------------------------

interface WorkflowStep {
  name: string;
  run?: string;
  line: number;
}
interface WorkflowJob {
  id: string;
  steps: WorkflowStep[];
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

/**
 * A deliberately small structural scan: jobs, their steps, each step's `name:`
 * and its `run:` scalar or block scalar. Nothing else in the YAML is read,
 * because everything else is where the false coverage came from.
 */
function parseWorkflow(text: string): Map<string, WorkflowJob> {
  const lines = text.split('\n');
  const jobs = new Map<string, WorkflowJob>();
  let i = lines.findIndex((l) => /^jobs:\s*$/.test(l));
  if (i < 0) return jobs;
  i++;

  const firstReal = lines.slice(i).find((l) => l.trim() && !l.trim().startsWith('#'));
  const jobIndent = firstReal ? indentOf(firstReal) : 2;
  let cur: WorkflowJob | null = null;

  for (; i < lines.length; i++) {
    const line = lines[i] ?? '';
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const ind = indentOf(line);
    if (ind === 0) break;
    if (ind === jobIndent) {
      const m = line.trim().match(/^([\w-]+):\s*$/);
      if (m) {
        cur = { id: m[1] ?? '', steps: [] };
        jobs.set(cur.id, cur);
      }
      continue;
    }
    if (!cur || ind !== jobIndent + 2 || !/^steps:\s*$/.test(line.trim())) continue;

    const firstStep = lines.slice(i + 1).find((l) => l.trim() && !l.trim().startsWith('#'));
    const stepIndent = firstStep ? indentOf(firstStep) : jobIndent + 4;
    let step: WorkflowStep | null = null;
    let j = i + 1;
    for (; j < lines.length; j++) {
      const l = lines[j] ?? '';
      if (!l.trim()) continue;
      const li = indentOf(l);
      if (li < stepIndent) break;
      if (l.trim().startsWith('#')) continue;
      if (li === stepIndent && l.trim().startsWith('- ')) {
        step = { name: `(line ${j + 1})`, line: j + 1 };
        cur.steps.push(step);
      }
      if (!step) continue;
      const body = l.trim().replace(/^- /, '');
      const km = body.match(/^(name|run):(.*)$/);
      if (!km) continue;
      const val = (km[2] ?? '').trim();
      if (km[1] === 'name') {
        step.name = val.replace(/^['"]|['"]$/g, '');
        continue;
      }
      if (!/^[|>][-+0-9]*$/.test(val)) {
        step.run = val;
        continue;
      }
      // Block scalar: consume by indentation, dropping comment lines inside it.
      const blockStart = lines.slice(j + 1).find((b) => b.trim());
      const blockIndent = blockStart ? indentOf(blockStart) : li + 2;
      const block: string[] = [];
      let k = j + 1;
      for (; k < lines.length; k++) {
        const bl = lines[k] ?? '';
        if (!bl.trim()) {
          block.push('');
          continue;
        }
        if (indentOf(bl) < blockIndent) break;
        block.push(bl.slice(blockIndent));
      }
      step.run = block.filter((b) => !b.trim().startsWith('#')).join('\n');
      j = k - 1;
    }
    i = j - 1;
  }
  return jobs;
}

// ---------------------------------------------------------------------------
// The analysis, pure over its inputs so the control can drive it synthetically
// ---------------------------------------------------------------------------

interface ExemptEntry {
  direction: 'ci-only' | 'local-only';
  entry: string;
  blocker: string;
  line: number;
}

interface Inputs {
  scripts: ScriptUniverse;
  gates: readonly GateSpec[];
  /** repo-relative workflow path, optionally `#job`, from paritySurface(). */
  surface: string[];
  workflowText: (file: string) => string | null;
  exempt: ExemptEntry[];
  /** basenames of BATTERY_DIR/test-*.sh on disk */
  battery: string[];
  fileExists: (rel: string) => boolean;
}

interface Finding {
  rule: string;
  message: string;
}

interface SurfaceRun {
  file: string;
  job: string;
  step: string;
  leaves: string[];
  raw: string;
}

function collectSurfaceRuns(inp: Inputs): SurfaceRun[] {
  const runs: SurfaceRun[] = [];
  for (const spec of inp.surface) {
    const [file = '', onlyJob] = spec.split('#');
    const text = inp.workflowText(file);
    if (text === null) continue;
    for (const job of parseWorkflow(text).values()) {
      if (onlyJob !== undefined && job.id !== onlyJob) continue;
      for (const step of job.steps) {
        if (step.run === undefined) continue;
        runs.push({
          file,
          job: job.id,
          step: step.name,
          raw: step.run,
          leaves: resolveLeaves(step.run, inp.scripts),
        });
      }
    }
  }
  return runs;
}

/** A shell-path exemption covers any script key whose body invokes that path. */
function exemptNames(inp: Inputs): Set<string> {
  const out = new Set<string>();
  const root = inp.scripts.byDir.get('') ?? {};
  for (const e of inp.exempt) {
    out.add(e.entry);
    if (!e.entry.endsWith('.sh')) continue;
    for (const [key, body] of Object.entries(root)) {
      if (body.includes(e.entry)) out.add(key);
    }
  }
  return out;
}

function analyze(inp: Inputs): Finding[] {
  const findings: Finding[] = [];
  const add = (rule: string, message: string): void => {
    findings.push({ rule, message });
  };
  const runs = collectSurfaceRuns(inp);
  const exempt = exemptNames(inp);
  const byId = new Map(inp.gates.map((g) => [g.id, g]));
  const rootScripts = inp.scripts.byDir.get('') ?? {};

  // --- 2. Tautology guard -------------------------------------------------
  // `npm run ci` inside the surface would make every assertion below vacuous:
  // it makes the entire gate set "CI-executed" by definition.
  for (const r of runs) {
    for (const m of stripQuoted(r.raw).matchAll(/npm run (ci|quality)(?=\s|$)/g)) {
      add(
        'tautology',
        `${r.file} ${r.job} / "${r.step}" invokes \`npm run ${m[1]}\`. That collapses the ten quality lanes into one serial job AND makes every parity assertion vacuous, because the whole gate set would count as CI-executed. Run the individual gates instead.`
      );
    }
  }

  // --- 3. R1: every defined check:ci-* gate is in the manifest -------------
  for (const key of Object.keys(rootScripts)) {
    if (!/^check:ci-/.test(key)) continue;
    if (byId.has(key) || exempt.has(key)) continue;
    add(
      'R1',
      `check:ci-* key "${key}" is defined in package.json but is not a manifest entry, so no local run executes it. A gate that runs nowhere is indistinguishable from one that always passes. Add it to scripts/ci-runner/manifest.ts, or add it to ${EXEMPT_FILE} with a direction and a BLOCKER reason.`
    );
  }

  // --- 4. R2: every gate-shaped leaf CI executes is in the manifest --------
  const manifestLeaves = new Set<string>();
  for (const g of inp.gates) for (const l of g.leaves) manifestLeaves.add(l);
  const reportedB = new Set<string>();
  for (const r of runs) {
    for (const leaf of r.leaves) {
      if (!GATE_SHAPED.test(leaf) || manifestLeaves.has(leaf) || exempt.has(leaf)) continue;
      if (reportedB.has(leaf)) continue;
      reportedB.add(leaf);
      add(
        'R2',
        `${leaf} runs in CI (${r.file} ${r.job} / "${r.step}") but is no manifest entry's leaf, so a local run cannot catch it. Give it a manifest entry, or add "ci-only  ${leaf}" to ${EXEMPT_FILE} with a BLOCKER saying why it cannot run on a developer machine.`
      );
    }
  }

  // --- 5. R3: every manifest entry's declared CI coverage really holds -----
  for (const g of inp.gates) {
    // Bound once: narrowing a property access does not survive the intervening
    // calls, so the step variant's fields would not typecheck through them.
    const ci: CiCoverage = g.ci;
    if (ci.kind === 'local-only' || ci.kind === 'test') {
      const label = ci.kind === 'test' ? `${ci.test} (${g.id})` : g.id;
      const v = validateBlockerQuality(
        label,
        ci.blocker.replace(/^BLOCKER:\s*/, ''),
        'manifest.ts'
      );
      if (v) add('R3', `${g.id}: ${v.message}`);
      if (ci.kind === 'test' && !inp.fileExists(ci.test)) {
        add('R3', `${g.id} declares coverage by ${ci.test}, which does not exist.`);
      }
      continue;
    }
    const text = inp.workflowText(ci.workflow);
    if (text === null) {
      add('R3', `${g.id} points at ${ci.workflow}, which does not exist.`);
      continue;
    }
    const job = parseWorkflow(text).get(ci.job);
    if (!job) {
      add('R3', `${g.id} points at job "${ci.job}" of ${ci.workflow}, which has no such job.`);
      continue;
    }
    const step = job.steps.find((s) => s.name === ci.step);
    if (!step || step.run === undefined) {
      add(
        'R3',
        `${g.id} points at step "${ci.step}" of ${ci.workflow} ${ci.job}, which has no such \`run:\` step. Either the workflow moved and the manifest is stale, or the gate stopped running in CI.`
      );
      continue;
    }
    const stepLeaves = resolveLeaves(step.run, inp.scripts);
    // The 57 battery entries all point at the single check:ci-quality-gates
    // step, which resolves to run-all.sh rather than to any one test. Verifying
    // the pointer reaches the battery RUNNER is what proves run-all.sh executes
    // in CI, which is the fact those entries depend on.
    const want = g.qualityGateTest ? [BATTERY_RUNNER] : g.leaves;
    if (!want.some((l) => stepLeaves.includes(l))) {
      add(
        'R3',
        `${g.id} points at ${ci.workflow} ${ci.job} / "${ci.step}", but that step resolves to [${stepLeaves.join(', ')}] and none of [${want.join(', ')}]. The pointer names a step that runs something else.`
      );
    }
  }

  // --- 6. Manifest hygiene ------------------------------------------------
  const seenIds = new Set<string>();
  for (const g of inp.gates) {
    if (seenIds.has(g.id)) add('hygiene', `duplicate manifest id "${g.id}".`);
    seenIds.add(g.id);
    // An id is either an npm key, or a direct repo-relative script path that
    // exists. The second form is what F3's two Static-lane gates need: the
    // Static lane is a bare checkout with no node_modules, so they are invoked
    // by path and carry no npm key.
    const isKey = g.id in rootScripts;
    const isPath = !g.run.startsWith('npm ') && inp.fileExists(g.run.split(/\s+/)[0] ?? '');
    if (!isKey && !isPath) {
      add(
        'hygiene',
        `manifest id "${g.id}" is neither a package.json script nor a runnable repo path (run: ${g.run}).`
      );
    }
    if (isKey) {
      const declared = [...g.leaves].sort().join('|');
      const actual = [...resolveLeaves(rootScripts[g.id] ?? '', inp.scripts)].sort().join('|');
      if (declared !== actual) {
        add(
          'hygiene',
          `manifest entry "${g.id}" declares leaves [${g.leaves.join(', ')}] but package.json resolves to [${actual.split('|').join(', ')}].`
        );
      }
    }
    for (const n of g.needs ?? []) {
      if (!byId.has(n)) add('hygiene', `"${g.id}" needs "${n}", which is not a manifest entry.`);
    }
    for (const l of g.leaves) {
      // Bare tool names (tsc, eslint, knip, vitest) are leaves too and are not
      // files; only path-shaped leaves are existence-checked.
      if (!l.includes('/')) continue;
      if (!inp.fileExists(l)) add('hygiene', `"${g.id}" names leaf ${l}, which does not exist.`);
    }
  }
  // Cycle detection: a cycle is a manifest bug and must fail loudly rather than
  // deadlock the scheduler at run time.
  const state = new Map<string, number>();
  const stack: string[] = [];
  const visit = (id: string): void => {
    if (state.get(id) === 2) return;
    if (state.get(id) === 1) {
      add('hygiene', `dependency cycle: ${[...stack.slice(stack.indexOf(id)), id].join(' -> ')}`);
      return;
    }
    state.set(id, 1);
    stack.push(id);
    for (const n of byId.get(id)?.needs ?? []) if (byId.has(n)) visit(n);
    stack.pop();
    state.set(id, 2);
  };
  for (const g of inp.gates) visit(g.id);

  // --- 7. Flattened-battery equality --------------------------------------
  // Without this, flattening run-all.sh would recreate #549 fifty-seven times
  // over: a new test would run in CI via the battery and never locally, or be
  // listed locally and silently dropped.
  const declared = new Set(
    inp.gates.filter((g) => g.qualityGateTest).map((g) => path.posix.basename(g.leaves[0] ?? ''))
  );
  for (const f of inp.battery) {
    if (!declared.has(f)) {
      add(
        'battery',
        `${BATTERY_DIR}/${f} exists on disk and run-all.sh runs it, but no manifest entry is tagged qualityGateTest for it, so a local run never schedules it.`
      );
    }
  }
  for (const f of declared) {
    if (!inp.battery.includes(f)) {
      add(
        'battery',
        `a manifest entry is tagged qualityGateTest for ${BATTERY_DIR}/${f}, which no longer exists.`
      );
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// CONTROL. Prove the instrument can FIRE before trusting its green.
// ---------------------------------------------------------------------------

function universeOf(
  byDir: Record<string, Record<string, string>>,
  names: Record<string, string> = {}
): ScriptUniverse {
  return {
    byDir: new Map(Object.entries(byDir)),
    nameToDir: new Map(Object.entries(names)),
  };
}

/**
 * Runs the REAL analyze() against a synthetic fixture carrying one planted
 * asymmetry in each direction, and fails if either is not reported. Modelled on
 * the control the predecessor check-gate-reachability.ts:104-136 carried, and
 * on scripts/check-schema-coverage.ts:34-44.
 *
 * The third leg exercises the escape hatch itself: an exemption that does not
 * silence a finding means the file is decorative.
 */
function control(): void {
  const fail = (why: string): never => {
    console.error(`${RED}CONTROL FAILED${NC}: ${why}`);
    console.error(
      '  This gate cannot be trusted until its own control fires, so the real check did not run.'
    );
    process.exit(1);
  };

  const workflows: Record<string, string> = {
    '.github/workflows/w.yml': [
      'jobs:',
      '  lane:',
      '    steps:',
      '      - name: npm run check:ci-planted-chain-only',
      '        run: npm run check:ci-covered',
      '      - name: Orphan',
      '        run: .ci/scripts/quality/check-planted-orphan.sh',
    ].join('\n'),
  };
  const scripts = universeOf({
    '': {
      'check:ci-covered': '.ci/scripts/quality/check-covered.sh',
      'check:ci-planted-chain-only': '.ci/scripts/quality/check-planted-chain-only.sh',
    },
  });
  const gates: GateSpec[] = [
    {
      id: 'check:ci-covered',
      run: 'npm run check:ci-covered',
      gate: true,
      leaves: ['.ci/scripts/quality/check-covered.sh'],
      ci: {
        kind: 'step',
        workflow: '.github/workflows/w.yml',
        job: 'lane',
        step: 'npm run check:ci-planted-chain-only',
      },
    },
    {
      id: 'check:ci-planted-chain-only',
      run: 'npm run check:ci-planted-chain-only',
      gate: true,
      leaves: ['.ci/scripts/quality/check-planted-chain-only.sh'],
      ci: {
        kind: 'step',
        workflow: '.github/workflows/w.yml',
        job: 'lane',
        step: 'Nonexistent step',
      },
    },
  ];
  const base: Inputs = {
    scripts,
    gates,
    surface: ['.github/workflows/w.yml'],
    workflowText: (f) => workflows[f] ?? null,
    exempt: [],
    battery: [],
    fileExists: () => true,
  };

  const findings = analyze(base);
  const has = (rule: string, needle: string): boolean =>
    findings.some((f) => f.rule === rule && f.message.includes(needle));

  // 1. Direction A (#549): a manifest gate whose declared step does not exist.
  if (!has('R3', 'check:ci-planted-chain-only')) {
    fail(
      `a manifest gate no workflow step runs was NOT reported; got ${JSON.stringify(findings.map((f) => f.rule))}`
    );
  }
  // 2. Direction B: a gate-shaped leaf CI runs with no manifest entry.
  if (!has('R2', 'check-planted-orphan.sh')) {
    fail('a CI-only shell gate absent from the manifest was NOT reported');
  }
  // 3. The name-field trap from the plan's section 1.4, both halves. The
  //    covered gate's step NAME contains `npm run check:ci-planted-chain-only`
  //    while its `run:` invokes check:ci-covered. Leg 1 above is the half that
  //    catches a whole-file matcher (the chain-only gate would look covered);
  //    this half catches the opposite error, a gate that IS genuinely run being
  //    reported anyway because its step name confused the resolver.
  if (has('R3', 'check:ci-covered')) {
    fail('a gate whose declared step really runs it was reported as uncovered');
  }

  // 4. The escape hatch must silence a finding, or the file is decorative.
  const silenced = analyze({
    ...base,
    exempt: [
      {
        direction: 'ci-only',
        entry: '.ci/scripts/quality/check-planted-orphan.sh',
        blocker: 'planted control entry, never read from disk',
        line: 1,
      },
    ],
  });
  if (silenced.some((f) => f.rule === 'R2')) fail('an exempted CI-only gate was still reported');

  // 5. The tautology guard.
  const tauto = analyze({
    ...base,
    workflowText: (f) =>
      f === '.github/workflows/w.yml'
        ? 'jobs:\n  lane:\n    steps:\n      - name: All gates\n        run: npm run ci\n'
        : null,
  });
  if (!tauto.some((f) => f.rule === 'tautology'))
    fail('`npm run ci` inside a run: block was NOT reported');

  console.log('  PASS  reports a manifest gate that no workflow step runs (the #549 direction)');
  console.log('  PASS  reports a CI-run shell gate that no manifest entry covers');
  console.log('  PASS  a step name containing an npm invocation does not count as coverage');
  console.log('  PASS  a BLOCKER-gated exemption silences a finding');
  console.log('  PASS  `npm run ci` inside a run: block is an error, not coverage');
}

// ---------------------------------------------------------------------------
// Disk inputs
// ---------------------------------------------------------------------------

function loadScripts(): ScriptUniverse {
  const byDir = new Map<string, Record<string, string>>();
  const nameToDir = new Map<string, string>();
  const add = (rel: string): void => {
    const p = path.join(ROOT, rel, 'package.json');
    if (!existsSync(p)) return;
    try {
      const pkg = JSON.parse(readFileSync(p, 'utf-8')) as {
        name?: string;
        scripts?: Record<string, string>;
      };
      byDir.set(rel, pkg.scripts ?? {});
      if (pkg.name) nameToDir.set(pkg.name, rel);
    } catch {
      /* an unparseable manifest is check:ci-lockfile's problem, not this gate's */
    }
  };
  add('');
  for (const dir of ['packages', 'private', 'workers']) {
    const base = path.join(ROOT, dir);
    if (!existsSync(base)) continue;
    for (const e of readdirSync(base)) add(path.posix.join(dir, e));
  }
  return { byDir, nameToDir };
}

/**
 * The exempt file's entry lines carry a direction column, so the shared
 * parseBlockeredList (which takes the FIRST whitespace-separated token) would
 * read "ci-only" as the entry. The BLOCKER association and validation stay with
 * the shared pair; only the two-column split is done here.
 */
function loadExempt(): ExemptEntry[] {
  const p = path.join(ROOT, EXEMPT_FILE);
  if (!existsSync(p)) return [];
  const lines = readFileSync(p, 'utf-8').split('\n');
  const parsed = parseBlockeredList(p);
  const out: ExemptEntry[] = [];
  const failures: string[] = [];
  for (const raw of parsed) {
    const cols = (lines[raw.line - 1] ?? '').trim().split(/\s+/);
    const [direction, entry] = cols;
    if (direction !== 'ci-only' && direction !== 'local-only') {
      failures.push(
        `${EXEMPT_FILE}:${raw.line}: entry must start with a direction, \`ci-only\` or \`local-only\`, then the gate. Got: ${cols.join(' ')}`
      );
      continue;
    }
    if (!entry) {
      failures.push(`${EXEMPT_FILE}:${raw.line}: direction "${direction}" with no gate after it.`);
      continue;
    }
    const corrected: BlockeredEntry = { entry, blocker: raw.blocker, line: raw.line };
    if (!corrected.blocker) {
      failures.push(
        `${EXEMPT_FILE}:${raw.line}: entry ${entry} is missing a '# BLOCKER: <reason>' comment above it.`
      );
    } else {
      const v = validateBlockerQuality(entry, corrected.blocker, EXEMPT_FILE);
      if (v) failures.push(v.message);
    }
    out.push({ direction, entry, blocker: corrected.blocker, line: raw.line });
  }
  if (failures.length > 0) {
    console.error(`${RED}✗${NC} BLOCKER validation failed for ${EXEMPT_FILE}:`);
    for (const f of failures) console.error(f);
    console.error(
      `\n${RED}✗${NC} An exemption is a hole in the promise that a local run catches CI failures. It must say why the gate genuinely cannot run on the other side.`
    );
    process.exit(1);
  }
  return out;
}

/** The gate list, from the fixture seam when set and the manifest otherwise. */
function loadGates(): readonly GateSpec[] {
  const override = process.env.CI_PARITY_MANIFEST;
  if (!override) return GATES;
  if (!existsSync(override)) return [];
  return JSON.parse(readFileSync(override, 'utf-8')) as GateSpec[];
}

function main(): void {
  control();

  // --- 1. Preflight, anti-vacuity -----------------------------------------
  // Each of these makes some assertion below assert nothing, and "measured
  // nothing" must never read as "found nothing".
  const refuse = (why: string): never => {
    console.error(`${RED}✗${NC} Refusing to run: ${why}`);
    process.exit(1);
  };
  const gates = loadGates();
  if (gates.length === 0) refuse('the gate manifest declares zero gates.');
  const wfDir = path.join(ROOT, '.github', 'workflows');
  if (!existsSync(wfDir))
    refuse(`no workflow directory at ${path.relative(ROOT, wfDir)}, so this gate is blind.`);
  if (readdirSync(wfDir).filter((f) => /\.ya?ml$/.test(f)).length === 0) {
    refuse(`${path.relative(ROOT, wfDir)} holds no workflows, so this gate is blind.`);
  }
  const surface = paritySurface(ROOT);
  if (surface.length === 0) {
    refuse('the computed parity surface is empty; ci.yml no longer reaches a quality workflow.');
  }
  const scripts = loadScripts();
  const rootScripts = scripts.byDir.get('');
  if (!rootScripts)
    refuse(`no readable package.json at ${ROOT}, so there is nothing to compare against.`);
  if (Object.keys(rootScripts ?? {}).filter((k) => k.startsWith('check:ci-')).length === 0) {
    refuse('package.json defines no check:ci-* gates.');
  }

  const batteryDir = path.join(ROOT, BATTERY_DIR);
  const inputs: Inputs = {
    scripts,
    gates,
    surface,
    workflowText: (f) => {
      const p = path.join(ROOT, f);
      return existsSync(p) ? readFileSync(p, 'utf-8') : null;
    },
    exempt: loadExempt(),
    battery: existsSync(batteryDir)
      ? readdirSync(batteryDir)
          .filter((f) => f.startsWith('test-') && f.endsWith('.sh'))
          .sort()
      : [],
    fileExists: (rel) => existsSync(path.join(ROOT, rel)),
  };

  const findings = analyze(inputs);

  console.log('');
  console.log('CI Parity');
  console.log('='.repeat(60));
  console.log(
    `${gates.length} manifest gate(s); ${surface.length} workflow scope(s) in the parity surface ` +
      `(${surface.join(', ')}); ${inputs.exempt.length} exempt; ${inputs.battery.length} battery test(s).`
  );
  console.log('');

  if (findings.length === 0) {
    console.log(
      `${GREEN}✓${NC} The local gate set and the CI quality surface agree in both directions.`
    );
    return;
  }

  // Ordered rules first, then anything else. The trailing set is not decoration:
  // grouping by a fixed list alone would let a rule added later count toward the
  // exit code while never being printed, which is a finding measured and not
  // reported -- the same silent-drop class this gate exists to catch.
  const order = ['tautology', 'R1', 'R2', 'R3', 'hygiene', 'battery'];
  const rules = [...order, ...new Set(findings.map((f) => f.rule))].filter(
    (r, i, all) => all.indexOf(r) === i
  );
  for (const rule of rules) {
    const hits = findings.filter((f) => f.rule === rule);
    if (hits.length === 0) continue;
    console.error(`${RED}✗ ${hits.length} ${rule} finding(s):${NC}`);
    for (const h of hits) console.error(`  ${h.message}`);
    console.error('');
  }
  console.error(
    `${RED}✗${NC} ${findings.length} parity finding(s). A gate that runs on only one side is a gate whose green means nothing on the other.`
  );
  process.exit(1);
}

main();
