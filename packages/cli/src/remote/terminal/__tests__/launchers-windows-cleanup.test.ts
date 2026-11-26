/**
 * The Windows launchers append `& del /q "<file>"` (cmd, windows-terminal) or a
 * Remove-Item line (PowerShell) so the terminal deletes the handed-off temp
 * files when ssh ends, whatever its exit code.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

interface Spawned {
  file: string;
  args: string[];
}
const spawned: Spawned[] = [];

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: (file: string, args: string[]) => {
    spawned.push({ file, args });
    return { unref: () => undefined };
  },
}));
vi.mock('../detector.js', () => ({ findMSYS2Installation: () => undefined }));

const { cmdCleanupSuffix, launchTerminal, powershellCleanupSuffix, powershellEncodedCommand } =
  await import('../launchers.js');

const KEY = 'C:/Users/rdc/AppData/Local/Temp/ssh-key-ab12.pem';
const KH = 'C:/Users/rdc/AppData/Local/Temp/known_hosts-ab12';

describe('cmdCleanupSuffix', () => {
  it('appends a del of every file, forward slashes turned to backslashes', () => {
    expect(cmdCleanupSuffix([KEY, KH])).toBe(
      ' & del /q "C:\\Users\\rdc\\AppData\\Local\\Temp\\ssh-key-ab12.pem" "C:\\Users\\rdc\\AppData\\Local\\Temp\\known_hosts-ab12"'
    );
  });

  it('keeps spaces, ampersands and carets inside the quotes', () => {
    expect(cmdCleanupSuffix(['C:\\Users\\a b & c^d\\key.pem'])).toBe(
      ' & del /q "C:\\Users\\a b & c^d\\key.pem"'
    );
  });

  it('adds nothing for no files', () => {
    expect(cmdCleanupSuffix([])).toBe('');
  });

  it.each(['C:\\a"b\\k', 'C:\\100%\\k', 'C:\\a;b\\k', 'C:\\a\nb\\k'])('refuses %j', (path) => {
    expect(() => cmdCleanupSuffix([path])).toThrow(/cannot quote/);
  });
});

describe('Windows launchers', () => {
  beforeEach(() => {
    spawned.length = 0;
  });

  const argv = ['ssh', '-i', KEY, 'u@h'];

  it('windows-terminal appends the unescaped cleanup after the escaped ssh line', () => {
    const result = launchTerminal('windows-terminal', { argv, cleanupFiles: [KEY, KH] });
    expect(result.success).toBe(true);
    const line = spawned[0].args.at(-1) as string;
    expect(spawned[0].args.slice(-3, -1)).toEqual(['cmd.exe', '/k']);
    expect(line.startsWith('ssh -i C:/Users/rdc/')).toBe(true);
    expect(
      line.endsWith(
        ' & del /q "C:\\Users\\rdc\\AppData\\Local\\Temp\\ssh-key-ab12.pem" "C:\\Users\\rdc\\AppData\\Local\\Temp\\known_hosts-ab12"'
      )
    ).toBe(true);
  });

  it('cmd appends it too', () => {
    launchTerminal('cmd', { argv, cleanupFiles: [KEY] });
    expect(spawned[0].args[0]).toBe('/k');
    expect(spawned[0].args[1]).toContain(
      ' & del /q "C:\\Users\\rdc\\AppData\\Local\\Temp\\ssh-key-ab12.pem"'
    );
  });

  it('powershell removes the files after the command', () => {
    launchTerminal('powershell', { argv, keepOpen: true, cleanupFiles: [KEY] });
    const script = Buffer.from(spawned[0].args[2], 'base64').toString('utf16le');
    expect(script).toContain(`\nRemove-Item -LiteralPath '${KEY}' -Force`);
    expect(powershellEncodedCommand(argv, true)).not.toContain('Remove-Item');
    expect(powershellCleanupSuffix(["C:\\it's\\k"])).toContain("'C:\\it''s\\k'");
  });

  it('a path that cannot be quoted fails the launch instead of spawning', () => {
    const result = launchTerminal('windows-terminal', { argv, cleanupFiles: ['C:\\100%\\k'] });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/cannot quote/);
    expect(spawned).toHaveLength(0);
  });

  it('without cleanupFiles the line is unchanged', () => {
    launchTerminal('cmd', { argv });
    expect(spawned[0].args[1]).not.toContain('del /q');
  });
});
