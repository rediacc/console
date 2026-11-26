import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  execute: vi.fn(),
  resolve: vi.fn(),
  setExitCode: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: vi.fn(), info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: m.setExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => 'table',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
vi.mock('../../utils/repo-executor.js', () => ({ executeRepoFunction: m.execute }));
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRef: m.resolve }));

import { runForensicsLevel } from '../forensics.js';

beforeEach(() => {
  vi.clearAllMocks();
  m.resolve.mockResolvedValue({ name: 'shop', repoKey: 'shop', machineName: 'm1' });
  m.execute.mockResolvedValue({ success: true, exitCode: 0 });
});

describe('forensics level', () => {
  it('calls the forensics_level renet function once on the machine the ref resolves to', async () => {
    await runForensicsLevel('shop@m1', 'full');
    expect(m.resolve).toHaveBeenCalledWith('shop@m1');
    expect(m.execute).toHaveBeenCalledTimes(1);
    expect(m.execute.mock.calls[0]?.slice(0, 5)).toEqual([
      'forensics_level',
      'shop',
      'm1',
      { level: 'full' },
      { job: { verb: 'forensics level', steps: [] } },
    ]);
    expect(m.setExitCode).not.toHaveBeenCalled();
  });

  it('passes the cluster of a kubernetes-world repo', async () => {
    m.resolve.mockResolvedValue({
      name: 'shop',
      repoKey: 'shop:t',
      machineName: 'm1',
      kubeCluster: 'k1',
    });
    await runForensicsLevel('shop:t', 'basic');
    expect(m.execute.mock.calls[0]?.slice(0, 5)).toEqual([
      'forensics_level',
      'shop:t',
      'm1',
      { level: 'basic' },
      { kubeCluster: 'k1', job: { verb: 'forensics level', steps: [] } },
    ]);
  });

  it('refuses a level that is not basic, standard or full before resolving anything', async () => {
    await expect(runForensicsLevel('shop', 'max')).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: /forensics.badLevel/,
    });
    expect(m.resolve).not.toHaveBeenCalled();
    expect(m.execute).not.toHaveBeenCalled();
  });

  it('exits non-zero when the function fails and the failure was not rendered as an exit', async () => {
    m.execute.mockResolvedValue({ success: false, exitCode: 7 });
    await runForensicsLevel('shop', 'standard');
    expect(m.setExitCode).toHaveBeenCalledWith(7);
  });
});
