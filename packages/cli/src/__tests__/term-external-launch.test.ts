/**
 * `rdc term connect <repo> --external`: the repo's working directory is a path
 * on the MACHINE, so it never reaches the local terminal launch (spawn's cwd
 * for wt.exe and cmd.exe, --working-directory for the Linux terminals). A
 * missing local cwd made Node report ENOENT on the executable, and the session
 * silently went inline. A failed launch is a warning with the reason, or a
 * refusal when `--external` was passed. Spawn is a recording fake.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

interface Spawned {
  file: string;
  args: string[];
  options: { cwd?: string };
}

const spawned: Spawned[] = [];

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: (file: string, args: string[], options: { cwd?: string }) => {
    spawned.push({ file, args, options });
    return { unref: () => undefined, once: () => undefined };
  },
}));

let platform: 'windows' | 'linux' = 'windows';
vi.mock('../remote/utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../remote/utils/platform.js')>()),
  getPlatform: () => platform,
  isWSL: () => false,
}));

import { launchExternalTerminal, reportExternalLaunchFailure } from '../commands/term.js';
import { SSHConnection } from '../remote/ssh/connection.js';
import { outputService } from '../services/core/output.js';

const REMOTE_PATH = `${WK_DATASTORE_PATH}/mounts/0f0e0d0c-aaaa-bbbb-cccc-111122223333`;
const details = { environment: {}, workingDirectory: REMOTE_PATH } as never;

function fakeConnection() {
  const conn = new SSHConnection('k', 'h', { preferAgent: false });
  Object.assign(conn, {
    setupResult: {
      sshOptions: ['-o', 'X=1'],
      knownHostsPath: '/tmp/kh',
      connectionMethod: 'file-based',
    },
    isSetup: true,
  });
  return conn;
}

describe('external terminal launch for a repo target', () => {
  beforeEach(() => {
    spawned.length = 0;
  });

  it.each([
    ['windows', 'wt.exe'],
    ['linux', 'gnome-terminal'],
  ] as const)('never passes the remote repo path to the local terminal on %s', async (p, file) => {
    platform = p;
    await launchExternalTerminal(fakeConnection(), 'u@h', 'cd /x; bash', 't', details);
    expect(spawned).toHaveLength(1);
    expect(spawned[0].file).toBe(file);
    expect(spawned[0].options.cwd).toBeUndefined();
    expect(spawned[0].args).not.toContain(REMOTE_PATH);
    expect(spawned[0].args).not.toContain('--working-directory');
  });
});

describe('external terminal launch failure', () => {
  const failure = new Error('Failed to launch terminal: spawn wt.exe ENOENT');

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('warns with the reason and returns, so the session goes inline, without --external', () => {
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    expect(() => reportExternalLaunchFailure(failure, false)).not.toThrow();
    expect(warn).toHaveBeenCalledOnce();
    expect(String(warn.mock.calls[0][0])).toContain('spawn wt.exe ENOENT');
  });

  it('refuses with the reason when --external was passed', () => {
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    expect(() => reportExternalLaunchFailure(failure, true)).toThrow(
      /--external.*spawn wt\.exe ENOENT/s
    );
    expect(warn).not.toHaveBeenCalled();
  });
});
