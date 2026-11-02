/**
 * Argv and version-gate contract of remote/sync/image-rsync.ts (Design 3, 6).
 * Red until C1 creates the module; it is loaded with a runtime path so tsc does not need it yet.
 */

import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

interface ImageRsyncModule {
  buildImageRsyncArgs(opts: {
    direction: 'download' | 'upload';
    freshDest: boolean;
    sshCommand: string;
    bwlimitKiBps?: number;
    remoteRsyncPath?: string;
  }): string[];
  assertRsyncCapable(deps?: {
    versionText?: () => Promise<string>;
    platform?: NodeJS.Platform;
  }): Promise<void>;
  parseRsyncStats(text: string): { literalBytes: number; matchedBytes: number };
}

const load = (): Promise<ImageRsyncModule> =>
  import(/* @vite-ignore */ fileURLToPath(new URL('../image-rsync.ts', import.meta.url)));

const base = { sshCommand: 'ssh -o ServerAliveInterval=15' } as const;

describe('buildImageRsyncArgs', () => {
  it('adds --sparse only when the destination does not exist yet', async () => {
    const m = await load();
    expect(m.buildImageRsyncArgs({ ...base, direction: 'download', freshDest: true })).toContain(
      '--sparse'
    );
    expect(
      m.buildImageRsyncArgs({ ...base, direction: 'download', freshDest: false })
    ).not.toContain('--sparse');
    expect(m.buildImageRsyncArgs({ ...base, direction: 'upload', freshDest: false })).not.toContain(
      '--sparse'
    );
  });

  it('always carries the resume and convergence flags, never -a or --times', async () => {
    const m = await load();
    for (const direction of ['download', 'upload'] as const) {
      for (const freshDest of [true, false]) {
        const args = m.buildImageRsyncArgs({ ...base, direction, freshDest });
        for (const flag of [
          '--inplace',
          '--partial',
          '--no-whole-file',
          '--ignore-times',
          '--stats',
        ]) {
          expect(args).toContain(flag);
        }
        expect(args).not.toContain('-a');
        expect(args).not.toContain('--times');
        expect(args).not.toContain('--archive');
        expect(args.some((a) => a.startsWith('--chown'))).toBe(false);
      }
    }
  });

  it('passes the ssh command through -e and the bandwidth cap as --bwlimit', async () => {
    const m = await load();
    const args = m.buildImageRsyncArgs({
      ...base,
      direction: 'download',
      freshDest: false,
      bwlimitKiBps: 12500,
    });
    expect(args[args.indexOf('-e') + 1]).toBe(base.sshCommand);
    expect(args).toContain('--bwlimit=12500');
  });

  it('upload leaves ownership and mode to the import helper', async () => {
    const m = await load();
    const up = m.buildImageRsyncArgs({ ...base, direction: 'upload', freshDest: false });
    for (const flag of ['--no-owner', '--no-group', '--no-perms']) expect(up).toContain(flag);
    const down = m.buildImageRsyncArgs({ ...base, direction: 'download', freshDest: false });
    expect(down).not.toContain('--no-owner');
  });
});

describe('assertRsyncCapable', () => {
  const text = (s: string) => ({ versionText: async () => s, platform: 'linux' as const });

  it('refuses openrsync', async () => {
    const m = await load();
    await expect(
      m.assertRsyncCapable(text('openrsync: protocol version 29\nrsync version 2.6.9 compatible'))
    ).rejects.toThrow(/openrsync/i);
  });

  it('refuses rsync 2.6.9', async () => {
    const m = await load();
    await expect(
      m.assertRsyncCapable(text('rsync  version 2.6.9  protocol version 29'))
    ).rejects.toThrow(/3\.1\.3/);
  });

  it('refuses 3.1.2 and accepts 3.1.3 and 3.2.7', async () => {
    const m = await load();
    await expect(
      m.assertRsyncCapable(text('rsync  version 3.1.2  protocol version 31'))
    ).rejects.toThrow();
    await expect(
      m.assertRsyncCapable(text('rsync  version 3.1.3  protocol version 31'))
    ).resolves.toBeUndefined();
    await expect(
      m.assertRsyncCapable(text('rsync  version 3.2.7  protocol version 31'))
    ).resolves.toBeUndefined();
  });

  it('names an install hint for macOS', async () => {
    const m = await load();
    await expect(
      m.assertRsyncCapable({
        versionText: async () => 'rsync  version 2.6.9  protocol version 29',
        platform: 'darwin',
      })
    ).rejects.toThrow(/brew install rsync/);
  });
});

describe('parseRsyncStats', () => {
  it('reads literal and matched data from --stats output', async () => {
    const m = await load();
    const out = 'Literal data: 1,234,567 bytes\nMatched data: 8,000 bytes\nFile list size: 0\n';
    expect(m.parseRsyncStats(out)).toEqual({ literalBytes: 1234567, matchedBytes: 8000 });
  });
});
