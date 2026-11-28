/** On Windows with no rsync installed, the error names `rdc tools install rsync` and still reads as "rsync not found" to the SFTP fallback. */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../utils/platform.js', () => ({
  commandExists: async () => false,
  getPlatform: () => 'windows',
}));
vi.mock('../../msys2/paths.js', () => ({
  getRsyncPath: () => 'rsync',
  getSshPath: () => 'ssh',
  getMsys2Environment: () => ({}),
}));

import { isRsyncNotFoundError } from '../../../commands/repo-sync-helpers.js';
import { getRsyncCommand } from '../rsync.js';

describe('getRsyncCommand on Windows without rsync', () => {
  it('names rdc tools install rsync and keeps the SFTP-fallback marker', async () => {
    const error = await getRsyncCommand().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Error);
    const message = (error as Error).message;
    expect(message).toContain('rdc tools install rsync');
    expect(message).not.toContain('desktop app');
    expect(isRsyncNotFoundError(error)).toBe(true);
  });
});
