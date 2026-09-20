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
 * COVERAGE VIA A TEST IS DECLARED, NEVER INFERRED. run-all.sh runs every
 * test-*.sh under .ci/scripts/test/gates/ (the glob is the live count), and
 * grepping them for a script name is precisely how #549 would have
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
 * Usage: npx tsx scripts/gates/check-ci-parity.ts
 *
 * ---- gate ----
 * step: Validate parity between the local gate set and the CI quality surface
 * needs: node
 * id: check:ci-parity
 * lane: quality-content
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type CiCoverage, GATES, type GateSpec, paritySurface } from '../ci-runner/manifest.js';
import {
  type BlockeredEntry,
  parseBlockeredList,
  validateBlockerQuality,
} from '../lib/blocker-validator.js';
import { policyPath } from '../lib/policy-paths.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.CI_PARITY_ROOT || path.resolve(__dirname, '..', '..');
// Repo-relative for display; the absolute path comes from the same seam, so a message and the file it names can never drift apart.
const EXEMPT_PATH = policyPath('.ci-parity-exempt', ROOT);
const EXEMPT_FILE = path.relative(ROOT, EXEMPT_PATH);
const BATTERY_DIR = '.ci/scripts/test/gates';
const BATTERY_RUNNER = '.ci/rediacc_ci/battery.py';

/**
 * Widened from the predecessor's `.ci/scripts/(quality|security)/check-*.sh`.
 * That pattern could not see test-write-once-guard.sh or test-install-script.sh,
 * which ran in Quality/Static and nowhere else (plan finding F3).
 */
// EXTENSION-SHAPED ONCE, AND IT COST A CUTOVER. This read `check-[\w.-]+\.sh`, so the moment W7 P4 repointed a gate at its Python port the leaf stopped being gate-shaped and rules R2/R3 quietly stopped judging it -- the same class as a `paths:` glob of `**/*.sh` that stops selecting its own gate once the leaf is a `.py`. Both spellings are matched now: the bash twins are
// `check-name.sh`, the ports are `check_name.py`, and a gate is a gate under either.
const GATE_SHAPED =
  /^(?:\.ci\/scripts\/(?:quality|security)\/check[-_][\w.-]+\.(?:sh|py)|\.ci\/scripts\/test\/test[-_][\w.-]+\.(?:sh|py))$/;

const RED = '[31m';
const GREEN = '[32m';
const NC = '[0m';

// --------------------------------------------------------------------------- Command resolution ---------------------------------------------------------------------------

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
  /**
   * Every tracked repo-relative path, so `python3 -m <module>` can resolve to a FILE.
   *
   * Derived from `git ls-files`, never a glob: a module that resolves to an untracked
   * file is not a leaf CI can run, and answering from the filesystem would make a
   * scratch file look like a registered gate.
   */
  tracked: Set<string>;
}

/**
 * Is this program word the external-gate wrapper, in either of its spellings? The bash path and the dotted Python module name the same transparent wrapper, and the resolver has to see through both: a step that moves from one to the other changes the failure POLICY and not the command, so the leaf on either side is the wrapped command.
 */
function isExternalGateWrapper(prog: string): boolean {
  return prog.endsWith('run-external-gate.sh') || prog.endsWith('.run_external_gate');
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
      // `--workspace` TAKES A NAME OR A DIRECTORY, and resolving only the name made a
      // real leaf invisible. `npm run typecheck --workspace packages/www` fell through
      // `nameToDir` (which has no such key) to `curScope`, so it resolved against the
      // ROOT manifest and `astro` -- a leaf check:types genuinely executes -- never
      // reached the parity surface. A silent fallback to the root is the worst answer
      // available here: it produces a plausible leaf set for the wrong package.
      const nextScope = ws ? (u.nameToDir.get(ws) ?? (u.byDir.has(ws) ? ws : curScope)) : curScope;
      const sig = `${nextScope}\0${key}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      const body = (u.byDir.get(nextScope) ?? {})[key];
      if (body === undefined) out.push(`missing-script:${ws ?? (nextScope || 'root')}:${key}`);
      else out.push(...resolveLeaves(body, u, nextScope, seen));
      continue;
    }

    // `python3 -m <module>` RESOLVES TO THE MODULE'S FILE, not to `python3`.
    //
    // Without this arm the tokenizer took the program word and stopped, so every
    // `-m` invocation resolved to the bare leaf `python3` and its `leaves:` could never
    // match a tracked path. That is why the whole W7 estate registers gates as bare FILE
    // paths instead: `scripts/lib/gate-header.ts:derivedRun` records the trap by name.
    // The registration shape is not being changed here -- this only stops the resolver
    // lying about a form the repo may legitimately use.
    //
    // A DOTTED MODULE IS A PATH WITH THE DOTS SWAPPED, and the package root has to come
    // from the tree rather than a constant: `rediacc_ci.quality.npmrc` lives under `.ci`,
    // which no other Python root in this repo shares. Both spellings are tried and the
    // TRACKED one wins; a module resolving to nothing tracked is reported as
    // `missing-module:<name>` rather than silently becoming `python3`, because a leaf
    // nobody can find is the failure this gate exists to catch.
    if (prog === 'python3' || prog === 'python') {
      const mIdx = rest.findIndex((a) => a === '-m');
      if (mIdx >= 0) {
        const mod = rest[mIdx + 1] ?? '';
        // THE TRANSPARENT WRAPPER IS TRANSPARENT IN BOTH LANGUAGES. The `-m` arm
        // below stops at the module's file, which is right for a gate and wrong
        // for the external-gate wrapper: that module executes its arguments and
        // changes only what a FAILURE means, never what runs. Reporting the
        // wrapper would make every external gate's CI pointer "run something
        // else" the moment the step moved from the bash spelling to this one,
        // which is exactly what it did (six R3 findings, W7P4-W).
        if (isExternalGateWrapper(mod)) {
          out.push(...resolveLeaves(rest.slice(mIdx + 2).join(' '), u, curScope, seen));
          continue;
        }
        const rel = mod.replace(/\./g, '/');
        const cands = [`.ci/${rel}.py`, `.ci/${rel}/__main__.py`, `${rel}.py`];
        const hit = cands.find((c) => u.tracked.has(c));
        out.push(hit ?? `missing-module:${mod}`);
        continue;
      }
      // No `-m`: the first non-flag argument is a script path, same as `node`.
      const script = rest.find((a) => !a.startsWith('-'));
      out.push(script ?? prog);
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

    // Transparent wrapper: run-external-gate.sh executes its arguments and only changes what a FAILURE means (soft on schedule vs hard on a PR), never what runs. The leaf is the wrapped command; reporting the wrapper itself would make every external gate's CI pointer "run something else" the moment it adopted the wrapper.
    if (isExternalGateWrapper(prog)) {
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

/** A gate-path exemption covers any script key whose body invokes that path.
 *
 * `.py` IS HERE BECAUSE OF W7 P4. The test was `endsWith('.sh')`, which meant an
 * exemption naming a file stopped covering its package.json key the instant the
 * cutover repointed that key at the Python port -- so a gate that genuinely
 * cannot run locally (this one needs R2 release credentials) reported as an
 * unregistered gate instead. Measured 2026-09-08 on `check:ci-release-state`.
 * A path exemption is about WHICH GATE is excused, never about what it is
 * written in.
 */
function exemptNames(inp: Inputs): Set<string> {
  const out = new Set<string>();
  const root = inp.scripts.byDir.get('') ?? {};
  for (const e of inp.exempt) {
    out.add(e.entry);
    if (!e.entry.endsWith('.sh') && !e.entry.endsWith('.py')) continue;
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
  // THREE WAYS THE OLD PATTERN MISSED, all measured. It was
  // `/npm run (ci|quality)(?=\s|$)/`, and:
  //   * `npm run ci:quick` (383 gates) and `npm run ci:serial` (the whole set
  //     serially) both ran straight past it -- the lookahead sees `:`.
  //   * ANY npm flag between `run` and the key defeated it outright, so even the
  //     plain case it was written for slipped through as `npm run --silent ci`.
  // A guard that the thing it guards against can walk past by adding `--silent`
  // is not a narrow guard, it is an inert one.
  //
  // AND THE OTHER DIRECTION MATTERS JUST AS MUCH, which is why the keys are
  // ENUMERATED rather than matched as `ci(:\w+)?`: `ci:list` and
  // `ci:quick -- --list` PLAN the lane and execute nothing, so flagging them
  // would red the ci-quick job for doing exactly the harmless thing it exists to
  // do -- and a gate that reds correct work is the shape that gets suppressed.
  const AGGREGATE_RUN = /npm run\s+(?:--\S+\s+)*(ci|ci:quick|ci:serial|quality)(?=\s|$)/g;
  for (const r of runs) {
    const raw = stripQuoted(r.raw);
    for (const m of raw.matchAll(AGGREGATE_RUN)) {
      // `--list` turns any of these into a plan. Scoped to the matched LINE so a
      // `--list` elsewhere in a multi-line script cannot excuse a real run.
      const lineStart = raw.lastIndexOf('\n', m.index ?? 0) + 1;
      const lineEnd = raw.indexOf('\n', m.index ?? 0);
      const line = raw.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);
      if (line.includes('--list')) continue;
      add(
        'tautology',
        `${r.file} ${r.job} / "${r.step}" invokes \`npm run ${m[1]}\`. That collapses the ten quality lanes into one serial job AND makes every parity assertion vacuous, because the whole gate set would count as CI-executed. Run the individual gates instead, or add \`--list\` if you meant to plan the lane rather than execute it.`
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
    // The 57 battery entries all point at the single check:ci-quality-gates step, which resolves to run-all.sh rather than to any one test. Verifying the pointer reaches the battery RUNNER is what proves run-all.sh executes in CI, which is the fact those entries depend on.
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
    // An id is either an npm key, or a direct repo-relative script path that exists. The second form is what F3's two Static-lane gates need: the Static lane is a bare checkout with no node_modules, so they are invoked by path and carry no npm key.
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
  // Cycle detection: a cycle is a manifest bug and must fail loudly rather than deadlock the scheduler at run time.
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

  // --- 7. Flattened-battery equality -------------------------------------- Without this, flattening run-all.sh would recreate #549 fifty-seven times over: a new test would run in CI via the battery and never locally, or be listed locally and silently dropped.
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

// --------------------------------------------------------------------------- CONTROL. Prove the instrument can FIRE before trusting its green. ---------------------------------------------------------------------------

function universeOf(
  byDir: Record<string, Record<string, string>>,
  names: Record<string, string> = {},
  tracked: readonly string[] = []
): ScriptUniverse {
  return {
    byDir: new Map(Object.entries(byDir)),
    nameToDir: new Map(Object.entries(names)),
    tracked: new Set(tracked),
  };
}

/**
 * Runs the REAL analyze() against a synthetic fixture carrying one planted
 * asymmetry in each direction, and fails if either is not reported. Modelled on
 * the control the predecessor check-gate-reachability.ts:104-136 carried, and
 * on scripts/gates/check-schema-coverage.ts:34-44.
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

  // --- PRE-A0: `python3 -m` resolves to a FILE, both directions -------------- Before this arm every `-m` invocation resolved to the bare token `python3`, so a `leaves:` naming the real module could never match and the mismatch read as a registration error rather than a resolver gap.
  {
    const u = universeOf({ '': {} }, {}, [
      '.ci/rediacc_ci/quality/npmrc.py',
      '.ci/rediacc_ci/tests/__main__.py',
      'tools/solo.py',
    ]);
    const leaves = (cmd: string): string[] => resolveLeaves(cmd, u);

    if (leaves('python3 -m rediacc_ci.quality.npmrc')[0] !== '.ci/rediacc_ci/quality/npmrc.py') {
      fail('a dotted `-m` module does not resolve to its tracked file');
    }
    if (leaves('python3 -m rediacc_ci.tests')[0] !== '.ci/rediacc_ci/tests/__main__.py') {
      fail('a package `-m` does not fall through to its __main__.py');
    }
    // THE ANTI-VACUITY DIRECTION: nothing may resolve to the bare interpreter, which is the exact symptom this box exists to remove.
    if (leaves('python3 -m rediacc_ci.quality.npmrc').includes('python3')) {
      fail('`-m` still resolves to the bare `python3` token');
    }
    // A module nobody tracks is NAMED, not silently swallowed. Reporting it as `python3` would be the old bug wearing a new coat.
    if (leaves('python3 -m no.such.module')[0] !== 'missing-module:no.such.module') {
      fail('an untracked `-m` module is not reported by name');
    }
    // CONTROL: a plain script invocation is unchanged, so the arm cannot eat that form.
    if (leaves('python3 tools/solo.py')[0] !== 'tools/solo.py') {
      fail('a plain `python3 <script>` invocation stopped resolving to its script');
    }
  }

  // --- W7P4-W: the external-gate wrapper is transparent in BOTH spellings ---- The bash arm already saw through `run-external-gate.sh`; flipping the six CI steps to the Python port made every one of them resolve to the wrapper and report "runs something else". The leaf has to stay the WRAPPED command whichever spelling carries it.
  {
    const u = universeOf({ '': { 'check:x': 'tsx scripts/gates/check-x.ts' } }, {}, [
      '.ci/rediacc_ci/quality/run_external_gate.py',
      '.ci/rediacc_ci/quality/npmrc.py',
      '.ci/scripts/quality/run-external-gate.sh',
      'scripts/gates/check-x.ts',
    ]);
    const leaves = (cmd: string): string[] => resolveLeaves(cmd, u);

    const wrapped = 'scripts/gates/check-x.ts';
    if (leaves('.ci/scripts/quality/run-external-gate.sh npm run check:x')[0] !== wrapped) {
      fail('the bash external-gate wrapper stopped resolving to the command it wraps');
    }
    if (leaves('python3 -m rediacc_ci.quality.run_external_gate npm run check:x')[0] !== wrapped) {
      fail('the Python external-gate wrapper does not resolve to the command it wraps');
    }
    // THE ANTI-VACUITY DIRECTION: the wrapper's own file must never BE the leaf, which is the exact symptom the six findings had.
    if (
      leaves('python3 -m rediacc_ci.quality.run_external_gate npm run check:x').includes(
        '.ci/rediacc_ci/quality/run_external_gate.py'
      )
    ) {
      fail('the Python external-gate wrapper still reports itself as the leaf');
    }
    // CONTROL: a NON-wrapper module in the same package still resolves to its own file, so the arm cannot swallow every `-m`.
    if (leaves('python3 -m rediacc_ci.quality.npmrc')[0] !== '.ci/rediacc_ci/quality/npmrc.py') {
      fail('the wrapper arm ate a plain `-m` module invocation');
    }
  }

  const workflows: Record<string, string> = {
    '.github/workflows/w.yml': [
      'jobs:',
      '  lane:',
      '    steps:',
      '      - name: npm run check:ci-planted-chain-only',
      '        run: npm run check:ci-covered',
      '      - name: Orphan',
      '        run: .ci/scripts/quality/check-planted-orphan.sh',
      // THE PORTED SHAPE, planted alongside the bash one so the two are judged by the same run of the same matcher. A W7 P4 cutover turns exactly this step into exactly this line, and GATE_SHAPED did not match it.
      '      - name: Ported orphan',
      '        run: .ci/scripts/quality/check_planted_ported_orphan.py',
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
  // 3. The name-field trap from the plan's section 1.4, both halves. The covered gate's step NAME contains `npm run check:ci-planted-chain-only`
  //    while its `run:` invokes check:ci-covered. Leg 1 above is the half that
  //    catches a whole-file matcher (the chain-only gate would look covered);
  // this half catches the opposite error, a gate that IS genuinely run being reported anyway because its step name confused the resolver.
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
  // NEEDLE-SCOPED, not `rule === 'R2'`: the fixture now plants a SECOND orphan
  // (the ported one, leg 4b) whose own R2 finding is expected to survive this exemption. A rule-wide test would read that as a failure to silence.
  if (silenced.some((f) => f.message.includes('check-planted-orphan.sh')))
    fail('an exempted CI-only gate was still reported');

  // 4b. THE PORTED HALF OF BOTH, and it is the half that was broken. A cutover leaves a `.py` where the `.sh` was, in the workflow step and in the
  //     package.json value; if either matcher is spelled `.sh` the gate goes
  // unjudged and its exemption stops covering its key -- silently, since a matcher that stops matching reports nothing at all.
  if (!has('R2', 'check_planted_ported_orphan.py')) {
    fail(
      'a CI-only PORTED gate absent from the manifest was NOT reported: GATE_SHAPED is extension-shaped again'
    );
  }
  const silencedPy = analyze({
    ...base,
    exempt: [
      {
        direction: 'ci-only',
        entry: '.ci/scripts/quality/check_planted_ported_orphan.py',
        blocker: 'planted control entry, never read from disk',
        line: 1,
      },
    ],
  });
  if (silencedPy.some((f) => f.message.includes('check_planted_ported_orphan.py'))) {
    fail('an exempted CI-only PORTED gate was still reported');
  }
  // And the exemption must reach the package.json KEY, not just the path: that is the expansion `endsWith('.sh')` used to gate, and the reason `check:ci-release-state` reported as unregistered the moment it was ported.
  const keyed = analyze({
    ...base,
    scripts: universeOf({
      '': {
        'check:ci-covered': '.ci/scripts/quality/check-covered.sh',
        'check:ci-planted-chain-only': '.ci/scripts/quality/check-planted-chain-only.sh',
        'check:ci-planted-ported': '.ci/scripts/quality/check_planted_ported_orphan.py',
      },
    }),
    exempt: [
      {
        direction: 'ci-only',
        entry: '.ci/scripts/quality/check_planted_ported_orphan.py',
        blocker: 'planted control entry, never read from disk',
        line: 1,
      },
    ],
  });
  if (keyed.some((f) => f.message.includes('check:ci-planted-ported'))) {
    fail('a `.py` path exemption did not expand to the package.json key that invokes it');
  }

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
  console.log('  PASS  a CI-run PORTED (.py) gate with no manifest entry is reported');
  console.log('  PASS  a .py path exemption silences its own finding');
  console.log('  PASS  a .py path exemption expands to the package.json key that invokes it');
  console.log('  PASS  `npm run ci` inside a run: block is an error, not coverage');
}

// --------------------------------------------------------------------------- Disk inputs ---------------------------------------------------------------------------

function loadScripts(): ScriptUniverse {
  const byDir = new Map<string, Record<string, string>>();
  const nameToDir = new Map<string, string>();
  const tracked = new Set(
    execFileSync('git', ['-C', ROOT, 'ls-files'], { encoding: 'utf-8' }).split('\n').filter(Boolean)
  );
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
  return { byDir, nameToDir, tracked };
}

/**
 * The exempt file's entry lines carry a direction column, so the shared
 * parseBlockeredList (which takes the FIRST whitespace-separated token) would
 * read "ci-only" as the entry. The BLOCKER association and validation stay with
 * the shared pair; only the two-column split is done here.
 */
function loadExempt(): ExemptEntry[] {
  const p = EXEMPT_PATH;
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

  // --- 1. Preflight, anti-vacuity ----------------------------------------- Each of these makes some assertion below assert nothing, and "measured nothing" must never read as "found nothing".
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

  // Ordered rules first, then anything else. The trailing set is not decoration: grouping by a fixed list alone would let a rule added later count toward the exit code while never being printed, which is a finding measured and not reported -- the same silent-drop class this gate exists to catch.
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
