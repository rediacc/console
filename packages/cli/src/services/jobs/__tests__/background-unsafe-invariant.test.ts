/**
 * The J22 invariant (PLAN-detached-jobs): a verb leaves BACKGROUND_UNSAFE in the same change that converts it.
 *
 * BACKGROUND_UNSAFE (packages/cli/src/services/executor/proxy-command.ts) lists the verbs `--background` must refuse
 * until each runs as one job. CONVERTED lists the verbs whose conversion box has landed. A verb in both is a converted
 * verb still refused, or a refused verb claimed converted; either is a box ticked against the wrong state.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { assertDetachable, BACKGROUND_UNSAFE } from '../../executor/proxy-command.js';
import type { ExecuteOptions } from '../../executor/types.js';
import { runCommandJob, setCommandJobDeps } from '../command-job.js';
import { CONVERTED, JOB_PLANS } from '../plans.js';
import { planStep } from '../steps.js';
import { TicketStore } from '../ticket-store.js';

const contract = new Map(CLI_CONTRACT.commands.map((c) => [c.pathKey, c]));
const unsafe = Object.keys(BACKGROUND_UNSAFE).sort((a, b) => a.localeCompare(b));

describe('BACKGROUND_UNSAFE and CONVERTED', () => {
  it('each of the ten J0 verbs is either still refused or converted, and nothing else is refused', () => {
    const ten = [
      'backup restore',
      'backup snapshot',
      'backup verify',
      'repo checkout',
      'repo commit',
      'repo fork',
      'repo migrate',
      'repo pull',
      'repo push',
      'repo up',
    ];
    expect(ten.filter((verb) => !(verb in BACKGROUND_UNSAFE) && !CONVERTED.has(verb))).toEqual([]);
    expect(unsafe.filter((verb) => !ten.includes(verb))).toEqual([]);
  });

  it('no verb is both refused and converted', () => {
    expect(unsafe.filter((verb) => CONVERTED.has(verb))).toEqual([]);
  });

  it('every refused verb is a detachable machine-plane command with a job plan', () => {
    for (const verb of unsafe) {
      const entry = contract.get(verb);
      expect(entry, `${verb} is not in the contract`).toBeDefined();
      expect(entry?.plane, verb).toBe('machine');
      expect(entry?.detachable, `${verb} is not detachable, so the entry is dead`).toBe(true);
      expect(JOB_PLANS[verb], `${verb} has no job plan`).toBeDefined();
    }
  });

  it('every refused verb is refused with its reason', () => {
    for (const verb of unsafe) {
      expect(() => assertDetachable(verb, contract.get(verb)), verb).toThrow(
        BACKGROUND_UNSAFE[verb]
      );
    }
  });

  it('every converted verb has a job plan and is no longer refused', () => {
    for (const verb of CONVERTED) {
      expect(JOB_PLANS[verb], `${verb} has no job plan`).toBeDefined();
      expect(BACKGROUND_UNSAFE[verb], verb).toBeUndefined();
    }
  });
});

type Placement = 'unsafe' | 'converted' | 'both' | 'neither';

/** Which of the two states a verb is in. The invariant is that every detachable verb is `unsafe` or `converted`. */
function placement(
  verb: string,
  refused: ReadonlySet<string>,
  converted: ReadonlySet<string>
): Placement {
  const a = refused.has(verb);
  const b = converted.has(verb);
  if (a && b) return 'both';
  if (a) return 'unsafe';
  return b ? 'converted' : 'neither';
}

describe('every detachable verb is in exactly one of BACKGROUND_UNSAFE or CONVERTED', () => {
  const refused = new Set(Object.keys(BACKGROUND_UNSAFE));
  const detachable = CLI_CONTRACT.commands.filter((c) => c.detachable).map((c) => c.pathKey);

  it('holds for the whole contract', () => {
    const offenders = detachable.filter((verb) => {
      const where = placement(verb, refused, CONVERTED);
      return where !== 'unsafe' && where !== 'converted';
    });
    expect(offenders).toEqual([]);
  });

  it('control: a verb planted in both sets, and one planted in neither, are both caught', () => {
    expect(placement('repo up', new Set(['repo up']), new Set(['repo up']))).toBe('both');
    expect(placement('repo up', new Set(), new Set())).toBe('neither');
    expect(placement('repo up', new Set(['repo up']), new Set())).toBe('unsafe');
    expect(placement('repo up', new Set(), new Set(['repo up']))).toBe('converted');
  });
});

describe('under --background every converted verb records its steps in the spool and on the ticket', () => {
  let dir: string;
  let store: TicketStore;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'invariant-bg-'));
    store = new TicketStore('test', dir);
    setCommandJobDeps({
      store: () => store,
      stepDeps: () =>
        Promise.resolve({
          observer: { configName: 'test' },
          warn: () => undefined,
          claim: ({ steps }) =>
            Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
        }),
    });
  });

  afterEach(() => {
    setCommandJobDeps();
    rmSync(dir, { recursive: true, force: true });
  });

  const stepped = [...CONVERTED].filter((verb) => (JOB_PLANS[verb]?.steps ?? []).length > 0);

  it('covers every converted verb that plans steps, and there are many', () => {
    expect(stepped.length).toBeGreaterThan(40);
  });

  it.each(stepped)(
    '%s: the ticket comes back running with its planned steps recorded',
    async (verb) => {
      const planned = [...(JOB_PLANS[verb].steps ?? [])];
      const starts: ExecuteOptions[] = [];
      setCommandJobDeps({
        executor: () => ({
          execute(options) {
            starts.push(options);
            return Promise.resolve({
              success: true,
              exitCode: 0,
              durationMs: 0,
              state: 'running' as const,
              jobId: 'job-1',
              attached: false,
            });
          },
        }),
      });

      const outcome = await runCommandJob(
        verb,
        { functionName: JOB_PLANS[verb].fn ?? 'x', machineName: 'm1', attachWindowMs: 0 },
        planned.map((name) => planStep(name))
      );

      expect(outcome.kind).toBe('pending');
      expect(starts).toHaveLength(1);
      expect(starts[0].jobSteps?.map((st) => st.name)).toEqual(planned);
      expect(outcome.ticket.steps.map((st) => st.name)).toEqual(planned);
      expect(outcome.ticket.stepsDone).toEqual([]);
    }
  );
});
