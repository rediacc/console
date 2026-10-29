import { afterEach, describe, expect, it, vi } from 'vitest';

const removeRepoKeyIfDeployed = vi.hoisted(() => vi.fn());

vi.mock('../../services/repo/repo-key-deployment.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/repo/repo-key-deployment.js')>()),
  removeRepoKeyIfDeployed,
}));

import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { resolveStepHandler, type StepContext } from '../../services/jobs/steps.js';

function ctx(overrides: Partial<StepContext>): StepContext {
  return { jobId: 'job-1', machine: 'm1', params: {}, state: 'succeeded', ...overrides };
}

afterEach(() => {
  vi.restoreAllMocks();
  removeRepoKeyIfDeployed.mockReset();
});

describe('job step bindings', () => {
  it('recordPushBase records the base on the repo push state', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
    } as never);
    vi.spyOn(configService, 'getRepositoryKey').mockResolvedValue('key');
    const add = vi.spyOn(configService, 'addRepository').mockResolvedValue(undefined as never);

    const handler = await resolveStepHandler('recordPushBase');
    await handler(
      ctx({
        params: { repo: 'app', machine: 'target', method: 'delta', verifiedBase: 'base-1' },
        finishedAt: '2026-10-29T10:00:00.000Z',
      })
    );

    expect(add).toHaveBeenCalledWith(
      'key',
      expect.objectContaining({
        pushState: {
          target: {
            verifiedBase: 'base-1',
            lastPushAt: '2026-10-29T10:00:00.000Z',
            method: 'delta',
          },
        },
      })
    );
  });

  it('rollbackCreate removes the registration of the named repo', async () => {
    const get = vi.spyOn(configService, 'getRepository').mockResolvedValue({} as never);
    const remove = vi
      .spyOn(configService, 'removeRepository')
      .mockResolvedValue(undefined as never);
    vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);

    const handler = await resolveStepHandler('rollbackCreate');
    await handler(ctx({ state: 'failed', params: { repo: 'app' } }));

    expect(get).toHaveBeenCalledWith('app');
    expect(remove).toHaveBeenCalledWith('app');
  });

  it('rollbackFork removes the fork registration and the key deployed for machine and guid', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({} as never);
    const remove = vi
      .spyOn(configService, 'removeRepository')
      .mockResolvedValue(undefined as never);
    vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);

    const handler = await resolveStepHandler('rollbackFork');
    await handler(ctx({ state: 'failed', params: { repo: 'app:t1', machine: 'm2', guid: 'g-2' } }));

    expect(remove).toHaveBeenCalledWith('app:t1');
    expect(removeRepoKeyIfDeployed).toHaveBeenCalledWith('app:t1', 'm2', 'g-2');
  });

  it('rollbackFork leaves the key alone when the plan carried no machine or guid', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue(undefined as never);

    const handler = await resolveStepHandler('rollbackFork');
    await handler(ctx({ state: 'failed', params: { repo: 'app:t1' } }));

    expect(removeRepoKeyIfDeployed).not.toHaveBeenCalled();
  });

  it('reportRestoreStats prints the stats parsed from the job output', async () => {
    const info = vi.spyOn(outputService, 'info').mockImplementation(() => undefined);
    const print = vi.spyOn(outputService, 'print').mockImplementation(() => undefined);

    const handler = await resolveStepHandler('reportRestoreStats');
    await handler(
      ctx({
        params: {},
        output: `${JSON.stringify({ cellsTotal: 4, chunksFetched: 2, chunksReused: 1 })}\n`,
      })
    );

    expect(info.mock.calls.length + print.mock.calls.length).toBeGreaterThan(0);
  });

  it('reportRestoreStats prints nothing when the output carries no record', async () => {
    const info = vi.spyOn(outputService, 'info').mockImplementation(() => undefined);
    const print = vi.spyOn(outputService, 'print').mockImplementation(() => undefined);

    const handler = await resolveStepHandler('reportRestoreStats');
    await handler(ctx({ params: {}, output: 'no json here' }));

    expect(info).not.toHaveBeenCalled();
    expect(print).not.toHaveBeenCalled();
  });

  it('reportRestorePath reports the record parsed from the job output', async () => {
    const success = vi.spyOn(outputService, 'success').mockImplementation(() => undefined);
    const print = vi.spyOn(outputService, 'print').mockImplementation(() => undefined);
    vi.spyOn(outputService, 'info').mockImplementation(() => undefined);
    const record = {
      snapshotId: 's1',
      path: '/p',
      to: '/dest',
      files: 3,
      dirs: 1,
      symlinks: 0,
      skipped: 0,
      bytesWritten: 10,
      cellsTotal: 5,
      cellsSelected: 2,
      chunksFetched: 2,
      bytesFetched: 20,
    };

    const handler = await resolveStepHandler('reportRestorePath');
    await handler(ctx({ params: { repo: 'app', snapshot: 's1' }, output: JSON.stringify(record) }));

    expect(success.mock.calls.length + print.mock.calls.length).toBeGreaterThan(0);
  });

  it('reportRestorePath fails when the output carries no record', async () => {
    const handler = await resolveStepHandler('reportRestorePath');
    await expect(
      handler(ctx({ params: { repo: 'app', snapshot: 's1' }, output: 'nothing' }))
    ).rejects.toThrow(/no record for "app"/);
  });
});
