/**
 * The executor's JobCall for `runJob` (section 18): the start carries runJob's
 * request id and step plan, asks the executor to leave the ticket to runJob, and
 * maps a result past the attach window to `pending`.
 */
import { describe, expect, it } from 'vitest';
import { executorJobCall } from '../job-call.js';
import type { ExecuteOptions, ExecuteResult, Executor } from '../types.js';

function fakeExecutor(result: ExecuteResult): { calls: ExecuteOptions[]; executor: Executor } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options) {
        calls.push(options);
        return Promise.resolve(result);
      },
    },
  };
}

const options: ExecuteOptions = {
  functionName: 'repository_up',
  machineName: 'prod-1',
  params: { repository: 'mail' },
};
const steps = [{ name: 'post-repo-up', on: 'success' as const }];

describe('executorJobCall', () => {
  it("passes runJob's request id and step plan, and leaves the ticket to runJob", async () => {
    const { calls, executor } = fakeExecutor({
      success: true,
      exitCode: 0,
      durationMs: 1,
      jobId: 'j1-deadbeef',
      state: 'succeeded',
      stdout: 'ok\n',
      steps: [{ name: 'compose_up', duration_ms: 5 }],
    });
    const call = executorJobCall('repo up', options, executor);

    const outcome = await call.start({ requestId: 'r-1', steps });

    expect(call).toMatchObject({
      verb: 'repo up',
      function: 'repository_up',
      machine: 'prod-1',
      repo: 'mail',
    });
    expect(calls[0]).toMatchObject({ requestId: 'r-1', jobSteps: steps, externalTicket: true });
    expect(outcome).toMatchObject({
      kind: 'finished',
      jobId: 'j1-deadbeef',
      job: { state: 'succeeded', exitCode: 0, output: 'ok\n', markers: ['compose_up'] },
    });
  });

  it('answers pending for a job still running past the window', async () => {
    const { executor } = fakeExecutor({
      success: true,
      exitCode: 0,
      durationMs: 20_000,
      jobId: 'j1-deadbeef',
      state: 'running',
    });

    const outcome = await executorJobCall('repo up', options, executor).start({
      requestId: 'r-1',
      steps: [],
    });

    expect(outcome).toMatchObject({
      kind: 'pending',
      jobId: 'j1-deadbeef',
      job: { state: 'running' },
    });
  });
});
