#!/usr/bin/env node
/**
 * Bidirectional parity between a registered step's `env:` block in the workflow and the
 * `env` its gate declares in `scripts/ci-runner/gates.lock.json`.
 *
 * WHY THIS EXISTS, and it is a receipt rather than a hypothesis. `scripts/gate-bind.ts`
 * REWRITES the steps inside a `# >>> gate-bind` region from each gate's header. Until box
 * A1 landed, `GateSpec` had no `env` field at all, so a step that carried `env:` was
 * re-emitted WITHOUT it and `gate-bind --write` reported a tidy `rewrote N region(s)`.
 * Measured on a scratch copy: strip `DOCKERHUB_TOKEN` from the `Docker image freshness`
 * step and run the whole battery -- NOTHING reds. The gate then runs in CI with an unset
 * token, hits the anonymous Docker Hub rate limit, and the failure reads as flake.
 *
 * A1 gave the header an `env-<KEY>:` grammar and taught `emitStep` to write it. That makes
 * the round trip POSSIBLE; it does not make it TRUE. Nothing yet asserts that what the
 * workflow says and what the lock says are the same thing, in both directions:
 *
 *   workflow-only  the step carries a key no gate declares. `gate-bind --write` drops it
 *                  the moment that step is folded into a region.
 *   lock-only      a gate declares a key the step does not carry. The declaration is a
 *                  lie, and a reader of the lock is told the gate has a secret it does
 *                  not get.
 *   value-drift    both carry the key with different values, which is the shape that
 *                  survives longest because both halves look populated.
 *
 * SHARED STEPS TAKE THE UNION, and that is a deliberate weakening with a reason. One step
 * -- `Quality-gate unit tests` -- is ridden by 150 lock entries and OWNED by none, which
 * is what `kind: battery` means. Demanding `env` on all 150 would be 150 copies of one
 * fact and 150 chances to drift. So the expectation for a step is the UNION of every
 * claimant's `env`, and two claimants declaring the SAME key with DIFFERENT values is
 * itself a finding. For the 249 single-claimant steps the union is that entry's own map,
 * so nothing is lost where nothing is shared.
 *
 * A COMMENT IS NOT AN ENV KEY. Four `env:` blocks in the two workflows this reads open
 * with prose (ci-quality.yml:943, :1690, :1900 and ci-build-renet.yml:136 as of
 * 2026-09-08), and a parser that read `# Sibling of the same gap: the script itself` as a
 * key/value pair would invent findings faster than it found real ones. `#` lines are
 * dropped. A BLOCK SCALAR is the opposite call: `KEY: |` is not used in either file today,
 * and rather than guess at a folded value this REFUSES the run and names the line, because
 * a value it cannot read is UNKNOWN and unknown is a failure.
 *
 * TEST SEAM. `CI_STEP_ENV_PARITY_ROOT` points the lock and workflow reads at another tree,
 * which is what makes a REAL-TREE plant possible at all: the lock and the workflows are
 * both generated artifacts nobody may hand-edit, so the only honest way to watch this gate
 * go red for each of its five reasons is to copy the real bytes somewhere and damage the
 * copy. `envRoot` is the shared helper for exactly this (`scripts/lib/repo-root.ts:105`),
 * and it deliberately falls back to the file-anchored root rather than to `process.cwd()`.
 *
 * Usage: npx tsx scripts/gates/check-ci-step-env-parity.ts [--selftest]
 *
 * ---- gate ----
 * id: check:ci-step-env-parity
 * step: Step env parity
 * lane: quality-code
 * needs: node
 * selftest: true
 * why: a gate-bind region rewrites steps from headers, so an env the lock does not know about is an env the next --write silently drops
 * ---- end gate ----
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { GREEN, NC, RED } from '../lib/console.js';
import { runControls } from '../lib/controls.js';
import { envRoot } from '../lib/repo-root.js';

const ROOT = envRoot('CI_STEP_ENV_PARITY_ROOT');
const LOCK = 'scripts/ci-runner/gates.lock.json';

// --------------------------------------------------------------------------- The workflow side: step `env:` blocks, and nothing else ---------------------------------------------------------------------------

/** One step's `env:` block, as the workflow really writes it. */
export interface StepEnv {
  job: string;
  /** The step `name:`, which is the only handle the lock has on a step. */
  name: string;
  env: Record<string, string>;
  /** 1-based line of the step's leading `- `, so a finding points somewhere. */
  line: number;
}

/** A line this parser refuses to guess at. Never folded into a pass. */
export interface EnvParseProblem {
  where: string;
  error: string;
}

export interface ParsedWorkflow {
  steps: StepEnv[];
  problems: EnvParseProblem[];
  /** How many `env:` blocks were seen at STEP level, parseable or not. */
  envBlocks: number;
}

const indentOf = (line: string): number => line.length - line.trimStart().length;

/** `KEY: value`. Leading letter or underscore, which is every env key in the tree. */
const ENV_PAIR = /^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$/;

/** Strip ONE layer of matching surrounding quotes. `'0.36.0'` is the string `0.36.0`. */
const unquote = (v: string): string => (/^'.*'$/.test(v) || /^".*"$/.test(v) ? v.slice(1, -1) : v);

/**
 * Every step that carries an `env:` block, per job.
 *
 * STRUCTURAL, not a whole-file regex, for the reason `check-ci-parity.ts:24-33` records at
 * length: a step `name:` and an `if:` expression both contain text that reads like the
 * thing you are looking for, and matching file text is how a scan comes back vacuously
 * clean. Job-level and workflow-level `env:` are deliberately NOT collected -- the lock
 * describes a STEP, and hoisting a job-level key into a step's expectation would report a
 * parity the emitter cannot deliver.
 *
 * @param text The workflow file's contents.
 * @param where Repository-relative path, used only to build `file:line` in problems.
 */
export function parseWorkflowStepEnv(text: string, where = '<workflow>'): ParsedWorkflow {
  const lines = text.split('\n');
  const steps: StepEnv[] = [];
  const problems: EnvParseProblem[] = [];
  let envBlocks = 0;

  let i = lines.findIndex((l) => /^jobs:\s*$/.test(l));
  if (i < 0) return { steps, problems, envBlocks };
  i++;

  const firstReal = lines.slice(i).find((l) => l.trim() && !l.trim().startsWith('#'));
  const jobIndent = firstReal ? indentOf(firstReal) : 2;
  let job = '';

  for (; i < lines.length; i++) {
    const line = lines[i] ?? '';
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const ind = indentOf(line);
    if (ind === 0) break;
    if (ind === jobIndent) {
      const m = line.trim().match(/^([\w-]+):\s*$/);
      if (m) job = m[1] ?? '';
      continue;
    }
    if (!job || ind !== jobIndent + 2 || !/^steps:\s*$/.test(line.trim())) continue;

    const firstStep = lines.slice(i + 1).find((l) => l.trim() && !l.trim().startsWith('#'));
    const stepIndent = firstStep ? indentOf(firstStep) : jobIndent + 4;
    // `- name: X` puts `name` at stepIndent + 2, and every sibling key lines up with it.
    const keyIndent = stepIndent + 2;
    let step: StepEnv | null = null;
    let j = i + 1;

    for (; j < lines.length; j++) {
      const l = lines[j] ?? '';
      if (!l.trim()) continue;
      const li = indentOf(l);
      if (li < stepIndent) break;
      if (l.trim().startsWith('#')) continue;
      if (li === stepIndent && l.trim().startsWith('- ')) {
        step = { job, name: `(line ${j + 1})`, env: {}, line: j + 1 };
        steps.push(step);
      }
      if (!step) continue;
      if (li !== stepIndent && li !== keyIndent) continue;
      const body = l.trim().replace(/^- /, '');
      const nm = body.match(/^name:\s*(.*)$/);
      if (nm) {
        step.name = unquote((nm[1] ?? '').trim());
        continue;
      }
      if (!/^env:\s*$/.test(body)) continue;

      envBlocks += 1;
      let k = j + 1;
      for (; k < lines.length; k++) {
        const el = lines[k] ?? '';
        if (!el.trim()) continue;
        const ei = indentOf(el);
        if (ei <= keyIndent) break;
        // A COMMENT IS NOT AN ENV KEY. Four blocks in the live corpus open with prose.
        if (el.trim().startsWith('#')) continue;
        const pair = ENV_PAIR.exec(el.trim());
        if (!pair) {
          problems.push({
            where: `${where}:${k + 1}`,
            error:
              `inside the env: of step "${step.name}" (${job}) this is neither a comment ` +
              `nor a KEY: value pair: ${el.trim()}`,
          });
          continue;
        }
        const raw = (pair[2] ?? '').trim();
        if (/^[|>][-+0-9]*$/.test(raw)) {
          problems.push({
            where: `${where}:${k + 1}`,
            error:
              `${pair[1]} uses a block scalar. This parser will not guess at a folded ` +
              'value, and an unread value is UNKNOWN, never equal.',
          });
          continue;
        }
        step.env[pair[1] as string] = unquote(raw);
      }
      j = k - 1;
    }
    i = j - 1;
  }
  return { steps, problems, envBlocks };
}

// --------------------------------------------------------------------------- The lock side ---------------------------------------------------------------------------

export interface LockGate {
  id: string;
  ci?: { kind?: string; workflow?: string; job?: string; step?: string };
  env?: Record<string, string>;
}

/** Registered steps, keyed `workflow job step`, each with every gate that claims it. */
export function groupByStep(gates: readonly LockGate[]): Map<string, LockGate[]> {
  const out = new Map<string, LockGate[]>();
  for (const g of gates) {
    const ci = g.ci;
    if (!ci || ci.kind !== 'step' || !ci.workflow || !ci.job || !ci.step) continue;
    // A space-joined key is safe here because a workflow path, a job id and a step name are stored separately and re-split by index below, never by the separator.
    const key = JSON.stringify([ci.workflow, ci.job, ci.step]);
    const list = out.get(key);
    if (list) list.push(g);
    else out.set(key, [g]);
  }
  return out;
}

export interface Finding {
  kind: 'workflow-only' | 'lock-only' | 'value-drift' | 'claimant-disagreement' | 'unresolved';
  job: string;
  step: string;
  key: string;
  detail: string;
}

/**
 * Compare one step's two halves.
 *
 * `expected` is built HERE rather than passed in so the disagreement case has somewhere to
 * be reported from: a key two claimants declare differently is not resolvable into a
 * single expectation, and quietly picking one would be the tune-the-predicate move.
 *
 * @param job The job id.
 * @param step The step name.
 * @param claimants Every lock entry whose `ci` names this step.
 * @param actual The step's parsed `env`, or null when the workflow parse did not find it.
 */
export function compareStep(
  job: string,
  step: string,
  claimants: readonly LockGate[],
  actual: Record<string, string> | null
): Finding[] {
  const out: Finding[] = [];
  if (actual === null) {
    out.push({
      kind: 'unresolved',
      job,
      step,
      key: '',
      detail:
        `${claimants.length} lock entr${claimants.length === 1 ? 'y names' : 'ies name'} ` +
        `this step (${claimants.map((c) => c.id).join(', ')}) and the workflow parse did ` +
        'not find it. Unchecked is not equal.',
    });
    return out;
  }

  const expected = new Map<string, { value: string; by: string }>();
  for (const g of claimants) {
    for (const [k, v] of Object.entries(g.env ?? {})) {
      const prev = expected.get(k);
      if (prev && prev.value !== v) {
        out.push({
          kind: 'claimant-disagreement',
          job,
          step,
          key: k,
          detail:
            `${prev.by} declares ${k}: ${prev.value} and ${g.id} declares ${k}: ${v} for ` +
            'the same step. One of them loses on the next --write.',
        });
        continue;
      }
      expected.set(k, { value: v, by: g.id });
    }
  }

  const owner = claimants[0]?.id ?? '(none)';
  for (const [k, v] of Object.entries(actual).sort()) {
    const e = expected.get(k);
    if (e === undefined) {
      out.push({
        kind: 'workflow-only',
        job,
        step,
        key: k,
        detail:
          `the step sets ${k}: ${v} and no claimant declares it. Add ` +
          `env: { ${k}: '${v}' } to the ${owner} manifest entry, and env-${k}: ${v} to ` +
          'its gate header if a gate-bind region emits it.',
      });
      continue;
    }
    if (e.value !== v) {
      out.push({
        kind: 'value-drift',
        job,
        step,
        key: k,
        detail: `the step sets ${k}: ${v} and ${e.by} declares ${k}: ${e.value}.`,
      });
    }
  }
  for (const [k, e] of [...expected].sort()) {
    if (!(k in actual)) {
      out.push({
        kind: 'lock-only',
        job,
        step,
        key: k,
        detail:
          `${e.by} declares ${k}: ${e.value} and the step carries no such key. Either the ` +
          'step lost it or the declaration was never true.',
      });
    }
  }
  return out;
}

// --------------------------------------------------------------------------- The analysis, pure over its inputs so the controls can drive it synthetically ---------------------------------------------------------------------------

export interface Shape {
  workflows: number;
  registeredSteps: number;
  resolvedSteps: number;
  stepsWithEnv: number;
  envBlocks: number;
  lockEnvKeys: number;
  findings: Finding[];
  problems: EnvParseProblem[];
}

/**
 * @param gates Every lock entry.
 * @param read Workflow path to its contents. Returning '' models an unreadable file, which
 *   yields `unresolved` findings rather than a quiet pass.
 */
export function analyze(gates: readonly LockGate[], read: (workflow: string) => string): Shape {
  const groups = groupByStep(gates);
  const parsed = new Map<string, ParsedWorkflow>();
  for (const key of groups.keys()) {
    const wf = (JSON.parse(key) as string[])[0] as string;
    if (!parsed.has(wf)) parsed.set(wf, parseWorkflowStepEnv(read(wf), wf));
  }

  const findings: Finding[] = [];
  const problems: EnvParseProblem[] = [];
  let resolvedSteps = 0;
  let stepsWithEnv = 0;
  let lockEnvKeys = 0;
  let envBlocks = 0;
  for (const p of parsed.values()) {
    problems.push(...p.problems);
    envBlocks += p.envBlocks;
  }

  for (const [key, claimants] of [...groups].sort(([a], [b]) => (a < b ? -1 : 1))) {
    const [wf, job, step] = JSON.parse(key) as [string, string, string];
    const p = parsed.get(wf);
    // A parse that found the step but no `env:` yields `{}`, which is a real answer. A
    // parse that found no step at all yields null, which is not.
    const hit = p?.steps.find((s) => s.job === job && s.name === step) ?? null;
    if (hit) resolvedSteps += 1;
    const actual = hit ? hit.env : null;
    if (actual && Object.keys(actual).length > 0) stepsWithEnv += 1;
    for (const g of claimants) lockEnvKeys += Object.keys(g.env ?? {}).length;
    findings.push(...compareStep(job, step, claimants, actual));
  }

  return {
    workflows: parsed.size,
    registeredSteps: groups.size,
    resolvedSteps,
    stepsWithEnv,
    envBlocks,
    lockEnvKeys,
    findings,
    problems,
  };
}

// --------------------------------------------------------------------------- The real run ---------------------------------------------------------------------------

function main(): number {
  let gates: LockGate[];
  try {
    const parsed: unknown = JSON.parse(readFileSync(path.join(ROOT, LOCK), 'utf-8'));
    if (!Array.isArray(parsed)) throw new Error('the lock is not a JSON array');
    gates = parsed as LockGate[];
  } catch (e) {
    console.error(`✗ ${LOCK} could not be read as a gate array: ${String(e)}`);
    console.error('  Regenerate it with `npx tsx scripts/gen-gates-lock.ts --write`.');
    return 1;
  }

  // ANTI-VACUITY, BOTH CORPORA, REFUSED SEPARATELY. A populated half does not excuse an empty one: an empty lock and an unreadable workflow produce the same confident zero.
  if (gates.length === 0) {
    console.error(
      `✗ ${LOCK} holds 0 gates; this gate is not seeing the registry and its green would mean nothing`
    );
    return 1;
  }

  const shape = analyze(gates, (wf) => {
    try {
      return readFileSync(path.join(ROOT, wf), 'utf-8');
    } catch {
      return '';
    }
  });

  if (shape.registeredSteps === 0) {
    console.error(
      `✗ ${gates.length} lock entries and 0 of them are \`ci.kind: step\`; this gate is not ` +
        'seeing the CI surface and its green would mean nothing'
    );
    return 1;
  }
  // THE PARSER'S OWN LIVENESS. Every comparison below reads "the step has no env" when the env parser is broken, and every one of those comparisons then passes. So the parser must be shown to work on the REAL corpus before its silence is believed.
  if (shape.envBlocks === 0) {
    // ONE call, not three. Three wrapped `console.error`s make the tail
    // `console.error( / 'S' / ); / return 1; / }`, which is byte-identical to the same
    // tail in every other gate that reports and refuses -- `check:ci-shape-duplication` reported exactly that as fingerprint `94f3f7e6f351` the moment this file joined the
    // `scripts/gates/check-*.ts` family. The message is unchanged; only its delivery is.
    console.error(
      `✗ the step-env parser found 0 \`env:\` blocks across ${shape.workflows} workflow ` +
        'file(s). Either the parser is broken or the workflows carry none, and under ' +
        'either reading every "the step has no env" verdict is unverified. Refusing.'
    );
    return 1;
  }
  if (shape.problems.length > 0) {
    console.error(`✗ ${shape.problems.length} line(s) inside a step env: this gate cannot read:`);
    for (const p of shape.problems) console.error(`  ${p.where}: ${p.error}`);
    console.error('  An unread value is UNKNOWN, never equal. Fix the line or teach the parser.');
    return 1;
  }

  const line =
    `${shape.registeredSteps} registered steps (${shape.resolvedSteps} resolved) across ` +
    `${shape.workflows} workflow(s), ${shape.envBlocks} step env: blocks parsed, ` +
    `${shape.stepsWithEnv} registered steps carrying env, ${shape.lockEnvKeys} env keys ` +
    'declared in the lock';

  if (shape.findings.length === 0) {
    console.log(`${GREEN}✓${NC} step env parity: ${line}`);
    return 0;
  }

  console.error(`${RED}✗${NC} step env parity: ${shape.findings.length} finding(s). ${line}`);
  const byKind = new Map<string, number>();
  for (const f of shape.findings) byKind.set(f.kind, (byKind.get(f.kind) ?? 0) + 1);
  console.error(
    `  ${[...byKind]
      .sort()
      .map(([k, n]) => `${k}: ${n}`)
      .join(', ')}`
  );
  let job = '';
  for (const f of shape.findings) {
    if (f.job !== job) {
      job = f.job;
      console.error(`\n  ${job}`);
    }
    console.error(`    ${f.step} -- ${f.kind}${f.key ? ` ${f.key}` : ''}`);
    console.error(`      ${f.detail}`);
  }
  console.error(
    '\n  Do NOT baseline these and do NOT add an allowlist entry. The fix is to declare the'
  );
  console.error(
    "  env where the emitter can see it: env: { KEY: 'value' } on the manifest entry, and"
  );
  console.error('  env-KEY: value in the gate header for any gate a gate-bind region emits.');
  return 1;
}

// --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

const WF = [
  'name: x',
  'on: push',
  'jobs:',
  '  quality-code:',
  '    runs-on: ubuntu-latest',
  '    steps:',
  '      - name: Plain',
  '        run: echo hi',
  '      - name: Tokened',
  '        env:',
  '          # A comment is not an env key, and this block opens with one.',
  '          # Second prose line, indented exactly like a value.',
  '          GH_TOKEN: ${{ github.token }}',
  "          QUOTED: '0.36.0'",
  '        run: npm run check:ci-thing',
  '      - name: Third',
  '        run: echo hi',
  '  other-job:',
  '    env:',
  '      HOISTED: nope',
  '    steps:',
  '      - name: Bare',
  '        run: echo hi',
].join('\n');

const gate = (id: string, job: string, step: string, env?: Record<string, string>): LockGate => ({
  id,
  ci: { kind: 'step', workflow: 'wf.yml', job, step },
  ...(env ? { env } : {}),
});

function selftest(): number {
  const p = parseWorkflowStepEnv(WF, 'wf.yml');
  const byName = (n: string): StepEnv | undefined => p.steps.find((s) => s.name === n);
  const read = (): string => WF;
  const kinds = (f: Finding[]): string =>
    f
      .map((x) => `${x.kind}:${x.key}`)
      .sort()
      .join(',');
  const full = { GH_TOKEN: '${{ github.token }}', QUOTED: '0.36.0' };

  const cases = [
    {
      name: 'the parser finds every step in the fixture, by name',
      ok: p.steps.length === 4 && byName('Tokened') !== undefined && byName('Bare') !== undefined,
      detail: `saw ${p.steps.length}: ${p.steps.map((s) => s.name).join(' | ')}`,
    },
    {
      name: 'a step env: block yields its keys and their values',
      ok: JSON.stringify(byName('Tokened')?.env) === JSON.stringify(full),
      detail: JSON.stringify(byName('Tokened')?.env),
    },
    {
      name: 'PROSE CONTROL: `#` lines inside an env: block are not keys',
      ok: Object.keys(byName('Tokened')?.env ?? {}).length === 2,
      detail: JSON.stringify(Object.keys(byName('Tokened')?.env ?? {})),
    },
    {
      name: 'CONTROL: a step with no env: yields {}, and is still a step',
      ok: byName('Plain') !== undefined && Object.keys(byName('Plain')?.env ?? {}).length === 0,
    },
    {
      name: 'CONTROL: a JOB-level env: is not hoisted into the steps of that job',
      ok: Object.keys(byName('Bare')?.env ?? {}).length === 0,
      detail: JSON.stringify(byName('Bare')?.env),
    },
    {
      name: 'CONTROL: the env: block ends at the next step key, not at the next step',
      ok: byName('Tokened')?.env.run === undefined && !('run' in (byName('Tokened')?.env ?? {})),
    },
    {
      name: 'the fixture parse reports 1 step env: block and no unreadable lines',
      ok: p.envBlocks === 1 && p.problems.length === 0,
      detail: `envBlocks=${p.envBlocks} problems=${JSON.stringify(p.problems)}`,
    },
    {
      name: 'a block scalar in an env: value is a PROBLEM, never a silent skip',
      ok:
        parseWorkflowStepEnv(
          WF.replace('          GH_TOKEN: ${{ github.token }}', '          GH_TOKEN: |'),
          'wf.yml'
        ).problems.length === 1,
    },
    // --- the comparison, both directions -----------------------------------
    {
      name: 'MATCH: a declaration equal to the step is no finding',
      ok: analyze([gate('a', 'quality-code', 'Tokened', full)], read).findings.length === 0,
    },
    {
      name: 'FIRES: a step key no claimant declares is workflow-only',
      ok:
        kinds(
          analyze([gate('a', 'quality-code', 'Tokened', { QUOTED: '0.36.0' })], read).findings
        ) === 'workflow-only:GH_TOKEN',
      detail: kinds(
        analyze([gate('a', 'quality-code', 'Tokened', { QUOTED: '0.36.0' })], read).findings
      ),
    },
    {
      name: 'FIRES: a declared key the step does not carry is lock-only',
      ok:
        kinds(analyze([gate('a', 'quality-code', 'Plain', { GH_TOKEN: 'x' })], read).findings) ===
        'lock-only:GH_TOKEN',
    },
    {
      name: 'FIRES: the same key with a different value is value-drift',
      ok:
        kinds(
          analyze(
            [gate('a', 'quality-code', 'Tokened', { ...full, GH_TOKEN: '${{ secrets.OTHER }}' })],
            read
          ).findings
        ) === 'value-drift:GH_TOKEN',
    },
    {
      name: 'FIRES: two claimants declaring one key differently is claimant-disagreement',
      ok: analyze(
        [
          gate('a', 'quality-code', 'Tokened', full),
          gate('b', 'quality-code', 'Tokened', { GH_TOKEN: 'other' }),
        ],
        read
      ).findings.some((f) => f.kind === 'claimant-disagreement'),
    },
    {
      name: 'UNION: a shared step is satisfied when ONE claimant declares each key',
      ok:
        analyze(
          [
            gate('a', 'quality-code', 'Tokened', { GH_TOKEN: '${{ github.token }}' }),
            gate('b', 'quality-code', 'Tokened', { QUOTED: '0.36.0' }),
          ],
          read
        ).findings.length === 0,
    },
    {
      name: 'CONTROL: the union does not excuse a key NO claimant declares',
      ok:
        analyze(
          [
            gate('a', 'quality-code', 'Tokened', { GH_TOKEN: '${{ github.token }}' }),
            gate('b', 'quality-code', 'Tokened'),
          ],
          read
        ).findings.length === 1,
    },
    {
      name: 'FIRES: a lock entry naming a step the workflow lacks is unresolved',
      ok:
        analyze([gate('a', 'quality-code', 'No Such Step')], read).findings[0]?.kind ===
        'unresolved',
    },
    {
      name: 'FIRES: an unreadable workflow is unresolved, never a quiet pass',
      ok: analyze([gate('a', 'quality-code', 'Tokened', full)], () => '').findings.every(
        (f) => f.kind === 'unresolved'
      ),
    },
    {
      name: 'CONTROL: a non-step ci kind is not a registered step',
      ok: groupByStep([{ id: 'a', ci: { kind: 'test' } }, { id: 'b' }]).size === 0,
    },
    {
      name: 'CONTROL: two gates on one step group into ONE step, not two',
      ok: groupByStep([gate('a', 'j', 's'), gate('b', 'j', 's')]).size === 1,
    },
    {
      name: 'CONTROL: the same step name in two jobs stays two steps',
      ok: groupByStep([gate('a', 'j1', 's'), gate('b', 'j2', 's')]).size === 2,
    },
    {
      name: 'shape: an empty gate list yields 0 registered steps, which main() refuses',
      ok: analyze([], read).registeredSteps === 0,
    },
    {
      name: 'shape: a workflow with no jobs: yields 0 env blocks, which main() refuses',
      ok: parseWorkflowStepEnv('# no jobs key at all\n', 'wf.yml').envBlocks === 0,
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

process.exit(process.argv.includes('--selftest') ? selftest() : main());
