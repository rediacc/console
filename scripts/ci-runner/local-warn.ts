/**
 * LOCAL ADVISORY GATES (agent/plans/PLAN-ciquick-green-then-batch.md box G2).
 *
 * A gate whose verdict depends on the network is a warning in the local `--quick` lane and stays blocking in CI. `check:ci-external-links` failed 13 of 34 ci:quick receipts on branch 1104-1 from flaky outbound requests (latest finding `link:www.ppc.go.jp`), and a local red the session cannot fix costs a 19-minute rerun.
 *
 * WHY A TABLE HERE AND NOT A GateSpec FIELD. The manifest region holding the gate is generated (scripts/gen/gen-manifest.ts drops an entry carrying a field its HAND_ONLY list does not name) and gates.lock.json is generated from it, so a new field would ripple through two generators for one gate. The table is keyed by gate id and pinned to the real manifest by `localWarnSelftest`, so an id that stops existing, or stops being a CI step, fails the runner's own selftest.
 *
 * WHAT CHANGES. Only when the run is `--quick` (the local lane): a non-zero outcome of a listed gate is rewritten to exit 0 with a `WARN (local advisory)` line on stderr, naming the real exit code and the reason. The receipt gate entry carries verdict `ok` plus `warned: <text>`, because the push guard (.claude/rediacc_hooks/guards/block_unverified_push.py `V2_VERDICTS`) admits only ok, fail and blocked: a new verdict would be refused as "no judged verdict". Every other run (`npm run ci`, `--lane`, the CI workflow steps, which call the npm script directly) is untouched, so the gate still blocks there.
 */
import fs from 'node:fs';
import path from 'node:path';

import type { ExecOutcome } from './exec';
import type { GateSpec } from './gate-spec';

/** Gate id to the reason it is advisory in the local quick lane. */
export const LOCAL_WARN: Readonly<Record<string, string>> = {
  'check:ci-external-links':
    'outbound HTTP to third-party sites is flaky from a developer machine (13 of 34 ci:quick receipts on 1104-1 failed on it); CI still blocks on it in the ci-quality.yml External links step',
};

/** Gate id to the `warned` text of this run, filled by `softenLocalWarn` and read when the receipt is written. */
export const warnedThisRun = new Map<string, string>();

/** Gate id to the REAL exit code (null when killed) of a softened run: the lane sees exit 0, so a reader of the receipt's `exitCode` would otherwise see a pass. */
export const warnedCodesThisRun = new Map<string, number | null>();

/** The real exit code to record beside `warned` for `id`: a number, null for a kill, undefined when the gate was not softened. */
export function warnedExitCodeFor(
  id: string,
  codes: ReadonlyMap<string, number | null> = warnedCodesThisRun
): number | null | undefined {
  return codes.get(id);
}

/** The reason `spec` is advisory in the local quick lane, or undefined. */
function localWarnReason(spec: Pick<GateSpec, 'id'>, quick: boolean): string | undefined {
  return quick ? LOCAL_WARN[spec.id] : undefined;
}

/**
 * `outcome` as the lane should see it. A listed gate in the quick lane that did not exit 0 becomes exit 0 with the warning appended to stderr and recorded in `warned`; everything else comes back as it was. PURE apart from `warned`, which the caller owns.
 */
export function softenLocalWarn(
  spec: Pick<GateSpec, 'id'>,
  quick: boolean,
  outcome: ExecOutcome,
  warned: Map<string, string> = warnedThisRun,
  codes: Map<string, number | null> = warnedCodesThisRun
): ExecOutcome {
  const reason = localWarnReason(spec, quick);
  if (reason === undefined || outcome.code === 0) return outcome;
  const how = outcome.code === null ? 'was killed' : `exited ${outcome.code}`;
  const text = `${spec.id} ${how}; ${reason}`;
  warned.set(spec.id, text);
  codes.set(spec.id, outcome.code);
  return {
    ...outcome,
    code: 0,
    timedOutMs: undefined,
    stderr: `${outcome.stderr}${outcome.stderr.endsWith('\n') || outcome.stderr === '' ? '' : '\n'}WARN (local advisory, blocking in CI): ${text}\n`,
  };
}

/** The `warned` text to record for `id` in a receipt, or undefined. */
export function warnedFor(
  id: string,
  warned: ReadonlyMap<string, string> = warnedThisRun
): string | undefined {
  return warned.get(id);
}

const CHECK_OUT = (outcome: Partial<ExecOutcome>): ExecOutcome => ({
  code: 0,
  stdout: '',
  stderr: '',
  ms: 1,
  ...outcome,
});

/**
 * The named step of a workflow file: its text up to the next step or job (so the last step of a job never runs on into a later job), the `run:` part of it with comment and `if:` lines dropped, and the head of its job (the keys before `steps:`), where a job-level `continue-on-error` lives.
 */
export function ciStepBlock(
  text: string,
  stepName: string
): { body: string; runText: string; jobHead: string } | null {
  const at = text.indexOf(`- name: ${stepName}\n`);
  if (at < 0) return null;
  const rest = text.slice(at + 1);
  const next = rest.search(/\n {6}- name: |\n {0,2}[A-Za-z_][\w-]*:/);
  const body = next < 0 ? rest : rest.slice(0, next);
  const live = body
    .split('\n')
    .filter((l) => !/^\s*#/.test(l) && !/^\s*if:/.test(l))
    .join('\n');
  const runAt = live.search(/\n\s*run:/);
  const runText = runAt < 0 ? '' : live.slice(runAt);
  let jobStart = 0;
  for (const m of text.slice(0, at).matchAll(/\n {2}[A-Za-z_][\w-]*:[ \t]*(?=\n)/g)) {
    jobStart = m.index ?? 0;
  }
  const stepsAt = text.indexOf('\n    steps:', jobStart);
  const jobHead = text
    .slice(jobStart, stepsAt < 0 || stepsAt > at ? at : stepsAt)
    .split('\n')
    .filter((l) => !/^\s*#/.test(l))
    .join('\n');
  return { body, runText, jobHead };
}

/**
 * Both directions, against the real manifest and the real workflow file. `gates` is the manifest's GATES, passed in so this file imports no manifest.
 */
export function localWarnSelftest(
  root: string,
  gates: readonly GateSpec[]
): { failures: string[]; assertions: number } {
  const failures: string[] = [];
  let assertions = 0;
  const check = (cond: boolean, message: string): void => {
    assertions++;
    if (!cond) failures.push(message);
  };
  const byId = new Map(gates.map((g) => [g.id, g]));
  check(
    Object.keys(LOCAL_WARN).length > 0,
    'LOCAL_WARN is empty: the selftest would prove nothing'
  );
  for (const id of Object.keys(LOCAL_WARN)) {
    const spec = byId.get(id);
    check(spec?.gate === true, `LOCAL_WARN names ${id}, which is not a manifest gate`);
    if (spec === undefined) continue;
    // CI STILL BLOCKS: the gate has a CI step in a workflow, that step really exists with the manifest's name, and the step carries no continue-on-error.
    check(
      spec.ci.kind === 'step',
      `${id} is advisory locally, so it must stay a blocking CI step; its ci.kind is ${spec.ci.kind}`
    );
    if (spec.ci.kind !== 'step') continue;
    const wf = path.join(root, spec.ci.workflow);
    const text = fs.existsSync(wf) ? fs.readFileSync(wf, 'utf8') : '';
    const block = ciStepBlock(text, spec.ci.step);
    check(block !== null, `${id}: no step named "${spec.ci.step}" in ${spec.ci.workflow}`);
    if (block === null) continue;
    check(
      block.runText.includes(spec.run) || block.runText.includes(id),
      `${id}: the CI step "${spec.ci.step}" does not run the gate`
    );
    check(
      !/continue-on-error/.test(block.body),
      `${id}: the CI step "${spec.ci.step}" has continue-on-error, so CI would not block`
    );
    check(
      !/continue-on-error/.test(block.jobHead),
      `${id}: the job holding the CI step "${spec.ci.step}" has continue-on-error, so CI would not block`
    );
  }
  // THE STEP READER, both directions, on a fixture workflow.
  const fixture = [
    'jobs:',
    '  first:',
    '    runs-on: x',
    '    steps:',
    '      - name: Gate step',
    '        # run: npm run fixture-gate  (a comment is no run)',
    '        if: always() && inputs.fixture-gate',
    '        run: npm run other',
    '      - name: Real step',
    '        run: npm run fixture-gate',
    '  second:',
    '    continue-on-error: true',
    '    steps:',
    '      - name: Later step',
    '        run: npm run later',
    '',
  ].join('\n');
  const gateStep = ciStepBlock(fixture, 'Gate step');
  const realStep = ciStepBlock(fixture, 'Real step');
  const laterStep = ciStepBlock(fixture, 'Later step');
  check(
    gateStep !== null && !gateStep.runText.includes('fixture-gate'),
    'step reader: a comment or an if: line must not count as the step running the gate'
  );
  check(
    realStep !== null && realStep.runText.includes('fixture-gate') && !/continue-on-error/.test(realStep.body + realStep.jobHead),
    'step reader: the real run line counts and a later job continue-on-error is not attributed to an earlier step'
  );
  check(
    laterStep !== null && /continue-on-error/.test(laterStep.jobHead),
    'step reader: a job-level continue-on-error is found for a step in that job'
  );
  // LOCAL QUICK LANE: a failing listed gate is a warning with exit 0, the real code named, and recorded.
  const id = Object.keys(LOCAL_WARN)[0] ?? '';
  const warned = new Map<string, string>();
  const soft = softenLocalWarn({ id }, true, CHECK_OUT({ code: 7, stderr: 'ENOTFOUND' }), warned);
  check(soft.code === 0, `quick lane: a failing ${id} must be exit 0, got ${String(soft.code)}`);
  check(
    soft.stderr.includes('ENOTFOUND') && soft.stderr.includes('WARN (local advisory'),
    'quick lane: the gate output stays and the warning is appended'
  );
  check((warned.get(id) ?? '').includes('exited 7'), 'quick lane: the real exit code is recorded');
  const killed = softenLocalWarn({ id }, true, CHECK_OUT({ code: null, timedOutMs: 5 }), new Map());
  check(
    killed.code === 0 && killed.timedOutMs === undefined,
    'quick lane: a hang is a warning too'
  );
  // CONTROLS: nothing else is softened.
  const w2 = new Map<string, string>();
  check(
    softenLocalWarn({ id }, false, CHECK_OUT({ code: 7 }), w2).code === 7 && w2.size === 0,
    'outside the quick lane (npm run ci, --lane) a failing listed gate must stay exit 7'
  );
  check(
    softenLocalWarn({ id: 'check:format' }, true, CHECK_OUT({ code: 7 }), w2).code === 7,
    'an unlisted gate must keep its failure in the quick lane'
  );
  check(
    softenLocalWarn({ id }, true, CHECK_OUT({ code: 0 }), w2).code === 0 && w2.size === 0,
    'a passing listed gate records no warning'
  );
  return { failures, assertions };
}
