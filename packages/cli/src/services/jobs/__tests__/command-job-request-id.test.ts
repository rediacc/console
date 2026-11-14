/**
 * The request id of a converted command's job (PLAN-detached-jobs section 17, J6b). `runCommandJob` asks the
 * invocation's minter, so a served request's body id reaches the machine and a local run stays fresh, and the ticket
 * records the id the executor was given.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { installJobDeps } from '../../../commands/__tests__/job-deps.js';
import type { ExecuteOptions } from '../../executor/types.js';
import { RequestIdMinter, resetInvocationMinter, withInvocationMinter } from '../attach.js';
import { runCommandJob } from '../command-job.js';

const FINISHED = { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' as const };
const call = (machineName: string): ExecuteOptions => ({
  functionName: 'repository_up',
  machineName,
  params: {},
});
const UUID_PREFIX = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';

describe('runCommandJob request ids', () => {
  let seen: (string | undefined)[];
  let restore: () => void;

  beforeEach(() => {
    seen = [];
    resetInvocationMinter();
    restore = installJobDeps((options) => {
      seen.push(options.requestId);
      return Promise.resolve(FINISHED);
    });
  });

  afterEach(() => {
    restore();
    resetInvocationMinter();
  });

  it('mints per machine and per call from a served invocation, and the ticket records that id', async () => {
    await withInvocationMinter(new RequestIdMinter('inv-1'), async () => {
      const first = await runCommandJob('repo up', call('m1'), []);
      await runCommandJob('repo up', call('m2'), []);
      await runCommandJob('repo up', call('m1'), []);
      expect(first.ticket.requestId).toBe('inv-1:m1:1');
    });

    expect(seen).toEqual(['inv-1:m1:1', 'inv-1:m2:1', 'inv-1:m1:2']);
  });

  it('a retried invocation mints the ids the first attempt did', async () => {
    const attempt = () =>
      withInvocationMinter(new RequestIdMinter('inv-1'), () =>
        runCommandJob('repo up', call('m1'), [])
      );
    await attempt();
    await attempt();

    expect(seen).toEqual(['inv-1:m1:1', 'inv-1:m1:1']);
  });

  it('two invocations in flight in one process keep their ids apart', async () => {
    await Promise.all(
      ['inv-a', 'inv-b'].map((id) =>
        withInvocationMinter(new RequestIdMinter(id), () =>
          runCommandJob('repo up', call('m1'), [])
        )
      )
    );

    expect([...seen].sort((a, b) => String(a).localeCompare(String(b)))).toEqual([
      'inv-a:m1:1',
      'inv-b:m1:1',
    ]);
  });

  it('control: a local invocation with no body id keeps fresh ids, new in each run', async () => {
    await runCommandJob('repo up', call('m1'), []);
    await runCommandJob('repo up', call('m1'), []);
    resetInvocationMinter();
    await runCommandJob('repo up', call('m1'), []);

    expect(seen[0]).toMatch(new RegExp(`^${UUID_PREFIX}:m1:1$`));
    expect(seen[1]).toMatch(new RegExp(`^${UUID_PREFIX}:m1:2$`));
    expect(seen[2]).toMatch(new RegExp(`^${UUID_PREFIX}:m1:1$`));
    expect(String(seen[2]).split(':')[0]).not.toBe(String(seen[0]).split(':')[0]);
  });

  it('a refused start acknowledges the ticket under the id it minted', async () => {
    restore();
    const refused: (string | undefined)[] = [];
    restore = installJobDeps((options) => {
      refused.push(options.requestId);
      return Promise.reject(new Error('BUSY'));
    });

    await expect(
      withInvocationMinter(new RequestIdMinter('inv-1'), () =>
        runCommandJob('repo up', call('m1'), [])
      )
    ).rejects.toThrow('BUSY');

    expect(refused).toEqual(['inv-1:m1:1']);
  });
});
