import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const spawnMock = vi.hoisted(() => vi.fn());

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: spawnMock,
}));

import { launchVSCode } from '../executable.js';

const CODE_CMD = 'C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd';
const URI = 'vscode-remote://ssh-remote+rediacc-m1/mnt/my repo';

function fakeProc() {
  return { unref: vi.fn(), on: vi.fn() };
}

describe('launchVSCode native spawn wiring', () => {
  const platform = Object.getOwnPropertyDescriptor(process, 'platform')!;

  beforeEach(() => {
    spawnMock.mockReset();
    spawnMock.mockReturnValue(fakeProc());
    vi.useFakeTimers();
  });

  afterEach(() => {
    Object.defineProperty(process, 'platform', platform);
    vi.useRealTimers();
  });

  it('on win32 runs code.cmd through cmd.exe with verbatim arguments and no shell', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    const done = launchVSCode({ path: CODE_CMD, isInsiders: false }, URI);
    await vi.advanceTimersByTimeAsync(500);
    await done;
    const [command, args, options] = spawnMock.mock.calls[0]!;
    expect(String(command).toLowerCase()).toContain('cmd');
    expect(args.slice(0, 3)).toEqual(['/d', '/s', '/c']);
    expect(options.windowsVerbatimArguments).toBe(true);
    expect(options).not.toHaveProperty('shell');
  });

  it('off win32 spawns the path directly without verbatim arguments', async () => {
    Object.defineProperty(process, 'platform', { value: 'linux' });
    const done = launchVSCode({ path: '/usr/bin/code', isInsiders: false }, URI);
    await vi.advanceTimersByTimeAsync(500);
    await done;
    const [command, args, options] = spawnMock.mock.calls[0]!;
    expect(command).toBe('/usr/bin/code');
    expect(args).toEqual(['--folder-uri', URI]);
    expect(options.windowsVerbatimArguments).toBe(false);
    expect(options).not.toHaveProperty('shell');
  });
});
