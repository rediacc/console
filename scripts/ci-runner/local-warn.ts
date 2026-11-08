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
  warned: Map<string, string> = warnedThisRun
): ExecOutcome {
  const reason = localWarnReason(spec, quick);
  if (reason === undefined || outcome.code === 0) return outcome;
  const how = outcome.code === null ? 'was killed' : `exited ${outcome.code}`;
  const text = `${spec.id} ${how}; ${reason}`;
  warned.set(spec.id, text);
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
    const at = text.indexOf(`- name: ${spec.ci.step}\n`);
    check(at >= 0, `${id}: no step named "${spec.ci.step}" in ${spec.ci.workflow}`);
    if (at < 0) continue;
    const rest = text.slice(at + 1);
    const next = rest.search(/\n {6}- name: /);
    const body = next < 0 ? rest : rest.slice(0, next);
    check(
      body.includes(spec.run) || body.includes(id),
      `${id}: the CI step "${spec.ci.step}" does not run the gate`
    );
    check(
      !/continue-on-error/.test(body),
      `${id}: the CI step "${spec.ci.step}" has continue-on-error, so CI would not block`
    );
  }
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
