import { describe, expect, it } from 'vitest';
import type { PathLookupOptions } from '../../services/tools/path-lookup.js';
import { checkTools } from '../doctor.js';

const RSYNC_BANNER = 'rsync  version 3.2.7  protocol version 31\nCopyright (C) 1996-2022';
const RSYNC_PRESENT: PathLookupOptions = {
  env: { PATH: '/usr/bin' },
  platform: 'linux',
  isExecutable: (c) => c === '/usr/bin/rsync',
};
const RSYNC_ABSENT: PathLookupOptions = { env: { PATH: '' }, platform: 'linux' };

describe('doctor Tools section', () => {
  it('warns when tofu is missing and names rdc tools install tofu', async () => {
    const section = await checkTools({
      resolveTofu: async () => ({ ok: false, reason: 'missing' }),
      pathLookup: RSYNC_PRESENT,
      rsyncVersion: () => RSYNC_BANNER,
    });
    expect(section.title).toBe('Tools');
    const tofu = section.checks[0];
    expect(tofu).toMatchObject({ name: 'OpenTofu', value: 'not installed', status: 'warn' });
    expect(tofu.hint).toBe('Run: rdc tools install tofu');
  });

  it('shows the tofu version and its source, and the rsync version, when present', async () => {
    const section = await checkTools({
      resolveTofu: async () => ({
        ok: true,
        engine: { engine: 'tofu', version: '1.10.6', path: '/x/tofu', source: 'rdc' },
      }),
      pathLookup: RSYNC_PRESENT,
      rsyncVersion: () => RSYNC_BANNER,
    });
    expect(section.checks).toEqual([
      { name: 'OpenTofu', value: '1.10.6 (installed by rdc)', status: 'ok' },
      { name: 'rsync', value: '3.2.7', status: 'ok' },
    ]);
  });

  it('labels a PATH terraform as terraform', async () => {
    const section = await checkTools({
      resolveTofu: async () => ({
        ok: true,
        engine: {
          engine: 'terraform',
          version: '1.5.7',
          path: '/usr/bin/terraform',
          source: 'path',
        },
      }),
      pathLookup: RSYNC_ABSENT,
    });
    expect(section.checks[0].value).toBe('terraform 1.5.7 (system PATH)');
  });

  it('warns on an engine below its floor, with the install hint', async () => {
    const section = await checkTools({
      resolveTofu: async () => ({
        ok: false,
        reason: 'belowFloor',
        engine: {
          engine: 'terraform',
          version: '1.4.0',
          path: '/usr/bin/terraform',
          source: 'path',
        },
      }),
      pathLookup: RSYNC_ABSENT,
    });
    expect(section.checks[0]).toMatchObject({
      status: 'warn',
      hint: 'Run: rdc tools install tofu',
    });
    expect(section.checks[0].value).toContain('older than the minimum 1.5.0');
  });

  it('warns when rsync is missing', async () => {
    const section = await checkTools({
      resolveTofu: async () => ({ ok: false, reason: 'missing' }),
      pathLookup: RSYNC_ABSENT,
    });
    expect(section.checks[1]).toEqual({
      name: 'rsync',
      value: 'not installed',
      status: 'warn',
      hint: 'Install rsync with the system package manager',
    });
  });
});

describe('doctor Tools section on Windows', () => {
  it('finds rsync.exe through PATH and PATHEXT, without which', async () => {
    const seen: string[] = [];
    const section = await checkTools({
      resolveTofu: async () => ({ ok: false, reason: 'missing' }),
      pathLookup: {
        env: { Path: 'C:\\Windows;C:\\msys64\\usr\\bin', PATHEXT: '.COM;.EXE' },
        platform: 'win32',
        isExecutable: (c) => c === 'C:\\msys64\\usr\\bin\\rsync.exe',
      },
      rsyncVersion: (p) => {
        seen.push(p);
        return RSYNC_BANNER;
      },
    });
    expect(seen).toEqual(['C:\\msys64\\usr\\bin\\rsync.exe']);
    expect(section.checks[1]).toEqual({ name: 'rsync', value: '3.2.7', status: 'ok' });
  });
});
