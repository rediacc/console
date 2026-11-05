import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExecResult } from '../types';

const calls: string[] = [];
const installRepoLicence = vi.fn();

vi.mock('../../licence', () => ({
  installRepoLicence: (...args: unknown[]) => installRepoLicence(...args),
}));

import { RepositoryMethods } from '../methods/RepositoryMethods';

const ok = (): ExecResult => ({ code: 0, stdout: '', stderr: '' }) as ExecResult;

describe('RepositoryMethods.repositoryNew', () => {
  beforeEach(() => {
    calls.length = 0;
    installRepoLicence.mockReset();
  });

  it('installs the licence for the GUID before repository_create runs', async () => {
    installRepoLicence.mockImplementation(() => {
      calls.push('licence');

      return Promise.resolve(ok());
    });
    const testFunction = vi.fn((opts: { function: string }) => {
      calls.push(opts.function);

      return Promise.resolve(ok());
    });
    const methods = new RepositoryMethods(testFunction, vi.fn());

    await methods.repositoryNew('guid-1', '1G', 'pw', '/ds');

    expect(calls).toEqual(['licence', 'repository_create']);
    expect(installRepoLicence).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ repositoryGuid: 'guid-1', kind: 'grand', size: '1G' })
    );
  });

  it('returns a refused issuance as the result and never runs repository_create', async () => {
    const refused = { code: 10, stdout: '', stderr: 'LICENSE_REQUIRED' } as ExecResult;
    installRepoLicence.mockResolvedValue(refused);
    const testFunction = vi.fn();
    const methods = new RepositoryMethods(testFunction, vi.fn());

    await expect(methods.repositoryNew('guid-2', '1G')).resolves.toBe(refused);
    expect(testFunction).not.toHaveBeenCalled();
  });
});
