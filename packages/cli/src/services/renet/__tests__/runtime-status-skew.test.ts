import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { readRuntimeStatus } from '../runtime-converge.js';

const failing = (message: string) => ({
  exec: () => Promise.reject(new Error(message)),
});

describe('readRuntimeStatus on a renet older than the CLI (C12)', () => {
  it('answers the version-skew message when the remote renet rejects a flag', async () => {
    const sftp = failing(
      'Command exited with code 1: Error: unknown flag: --policy\nUsage: renet runtime status'
    );
    await expect(
      readRuntimeStatus(sftp, '/usr/bin/renet', WK_DATASTORE_PATH, 'epoch', 'server-1')
    ).rejects.toThrow('renet on server-1 is older than this CLI; run machine setup');
  });

  it('keeps any other failure as it was', async () => {
    const sftp = failing('Command exited with code 1: disk full');
    await expect(
      readRuntimeStatus(sftp, '/usr/bin/renet', WK_DATASTORE_PATH, undefined, 'server-1')
    ).rejects.toThrow('disk full');
  });

  it('keeps the raw error when no machine is named', async () => {
    const sftp = failing('Error: unknown flag: --policy');
    await expect(readRuntimeStatus(sftp, '/usr/bin/renet', WK_DATASTORE_PATH)).rejects.toThrow(
      'unknown flag'
    );
  });
});
