/**
 * The import side of the helper protocol: the `--adopt-sha256` argv, and the staging-token check
 * that a `placed` ready line (an image already at its final path, nothing staged) skips.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it, vi } from 'vitest';
import type { ExecSessionHandle } from '../../../remote/sftp/client.js';
import { buildImportCommand, startImportSession } from '../session.js';

const SHA = 'a'.repeat(64);
const base = {
  renetPath: '/usr/bin/renet',
  guid: 'guid-1',
  datastore: WK_DATASTORE_PATH,
  allocatedBytes: 10,
};

function handle(readyLine: string): ExecSessionHandle {
  const lines = [readyLine];
  return {
    write: vi.fn(),
    end: vi.fn(),
    nextLine: async () => lines.shift() ?? null,
    exit: Promise.resolve(0),
    isClosed: () => false,
  };
}

const open = (readyLine: string) =>
  startImportSession({
    handle: handle(readyLine),
    stderrTail: () => '',
    transport: { sshCommand: 'ssh', userHost: 'u@h' },
    pingMs: 3_600_000,
  });

const ready = (extra: Record<string, unknown>) => JSON.stringify({ event: 'ready', ...extra });

describe('buildImportCommand --adopt-sha256', () => {
  it('emits the flag with the digest when adoptSha256 is set', () => {
    expect(buildImportCommand({ ...base, adoptSha256: SHA })).toMatch(
      new RegExp(`--adopt-sha256 '?${SHA}'? --allocated-bytes`)
    );
  });

  it('emits no flag without adoptSha256 (control)', () => {
    expect(buildImportCommand(base)).not.toContain('--adopt-sha256');
  });

  it('refuses a digest that is not a safe token', () => {
    expect(() => buildImportCommand({ ...base, adoptSha256: `${SHA}; rm -rf /` })).toThrow();
    expect(() => buildImportCommand({ ...base, adoptSha256: `${SHA}$(id)` })).toThrow();
  });
});

describe('startImportSession staging check', () => {
  it('accepts a placed reply with no staging path', async () => {
    const session = await open(ready({ placed: true, fresh: false }));
    expect(session.ready.placed).toBe(true);
    expect(session.ready.staging).toBe('');
    await session.quit();
  });

  it('refuses an unplaced reply whose staging path is unsafe (control)', async () => {
    await expect(open(ready({ placed: false, staging: '/mnt/x y;id' }))).rejects.toThrow();
  });

  it('refuses an unplaced reply with no staging path (control)', async () => {
    await expect(open(ready({ fresh: true }))).rejects.toThrow();
  });

  it('accepts an unplaced reply with a safe staging path (control)', async () => {
    const session = await open(ready({ staging: `${WK_DATASTORE_PATH}/staging/g1`, fresh: true }));
    expect(session.ready.placed).toBe(false);
    await session.quit();
  });
});
