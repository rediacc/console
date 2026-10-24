import { describe, expect, it } from 'vitest';
import type { SFTPClient } from '../../../remote/sftp/index.js';
import type { AutoConvergeDeps } from '../../renet/runtime-converge.js';
import { readConvergeStatus } from '../session-converge.js';

function deps(error: Error): { sftp: SFTPClient; deps: AutoConvergeDeps } {
  const sftp = { exec: () => Promise.reject(error) } as unknown as SFTPClient;
  return {
    sftp,
    deps: {
      sftp,
      remoteRenetPath: '/usr/bin/renet',
      machineName: 'hostinger',
      datastore: '/mnt/rediacc',
      buildBaseVault: () => '',
      run: () => Promise.reject(new Error('unused')),
      refreshRouter: () => Promise.resolve(false),
    },
  };
}

describe('readConvergeStatus on a dry run', () => {
  it('rewraps a too-old renet with the original error as cause', async () => {
    const original = new Error('Error: unknown command "runtime" for "renet"');
    const { sftp, deps: d } = deps(original);
    const thrown = await readConvergeStatus(sftp, d, true).catch((e: unknown) => e);
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toContain('rdc machine setup hostinger');
    expect((thrown as Error).cause).toBe(original);
  });

  it('rethrows any other failure unchanged', async () => {
    const original = new Error('sftp: unknown command status 255 from the remote shell');
    const { sftp, deps: d } = deps(original);
    await expect(readConvergeStatus(sftp, d, true)).rejects.toBe(original);
  });
});
