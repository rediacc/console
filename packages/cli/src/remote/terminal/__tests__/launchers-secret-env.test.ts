/**
 * External terminals: no launcher hands a secret to the terminal (argv or
 * environment), whatever the caller passes, and every launcher quotes the
 * session's argv for the language it hands it to, so an argument holding a
 * quote, a space and a backslash arrives intact. A fake spawn records each
 * launch; the POSIX command lines and the WSL launch script are run for real.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TerminalType } from '../../types/index.js';

interface Spawned {
  file: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}

const spawned: Spawned[] = [];

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: (file: string, args: string[], options: { env: NodeJS.ProcessEnv }) => {
    spawned.push({ file, args, env: options.env });
    return { unref: () => undefined };
  },
}));

let wsl = true;
vi.mock('../../utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/platform.js')>()),
  isWSL: () => wsl,
}));

vi.mock('../detector.js', () => ({ findMSYS2Installation: () => '/msys64' }));

const {
  appleScriptString,
  buildBashExports,
  cmdEscape,
  launchTerminal,
  posixCommandLine,
  powershellEncodedCommand,
  windowsCommandLine,
  windowsQuoteArg,
} = await import('../launchers.js');

const SECRET = 'term-secret-value-3K';
const ENV = { REDIACC_REPOSITORY: 'app', REDIACC_SECRET_TOKEN: SECRET };
/** A remote command holding a quote, a space and a backslash. */
const TRICKY = `echo "it's a \\ test" && cd '/a b'`;
const ARGV = ['ssh', '-p', '22', 'repo@h', TRICKY];

const ALL: TerminalType[] = [
  'gnome-terminal',
  'konsole',
  'xfce4-terminal',
  'xterm',
  'mate-terminal',
  'terminator',
  'terminal-app',
  'iterm2',
  'windows-terminal',
  'powershell',
  'cmd',
  'mintty',
  'wsl',
];

/** Runs a POSIX command line with `printf` standing in for ssh; returns the argv it saw. */
function argvSeenBy(commandLine: string): string[] {
  const probe = commandLine.replace(/^'ssh'/, `'printf' '%s\\0'`);
  return execFileSync('bash', ['-c', probe]).toString().split('\0').slice(0, -1);
}

describe('terminal launchers', () => {
  beforeEach(() => {
    spawned.length = 0;
    wsl = true;
  });

  it('buildBashExports exports only the non-secret variables', () => {
    expect(buildBashExports(ENV)).toBe("export REDIACC_REPOSITORY='app' && ");
  });

  for (const type of ALL) {
    it(`${type}: no secret in the arguments or the environment it spawns with`, () => {
      launchTerminal(type, { argv: ARGV, environmentVariables: ENV, title: 'T' });
      expect(spawned.length).toBeGreaterThan(0);
      for (const { args, env } of spawned) {
        for (const arg of args) expect(arg).not.toContain(SECRET);
        expect(Object.keys(env).filter((k) => k.startsWith('REDIACC_SECRET'))).toEqual([]);
        expect(env.WSLENV ?? '').not.toContain('REDIACC_SECRET');
      }
    });
  }

  it('a POSIX command line hands each argument over intact', () => {
    expect(argvSeenBy(posixCommandLine(ARGV))).toEqual(ARGV.slice(1));
  });

  for (const type of ['gnome-terminal', 'konsole', 'xfce4-terminal', 'xterm'] as const) {
    it(`${type}: bash -c receives the argv quoted`, () => {
      launchTerminal(type, { argv: ARGV });
      const args = spawned[0].args;
      expect(args.slice(-3, -1)).toEqual(['bash', '-c']);
      expect(argvSeenBy(args.at(-1) as string)).toEqual(ARGV.slice(1));
    });
  }

  for (const type of ['mate-terminal', 'terminator'] as const) {
    it(`${type}: the -e string splits back into bash -c and the quoted argv`, () => {
      launchTerminal(type, { argv: ARGV });
      const line = spawned[0].args.at(-1) as string;
      const words = execFileSync('bash', ['-c', `printf '%s\\0' ${line}`])
        .toString()
        .split('\0')
        .slice(0, -1);
      expect(words.slice(0, 2)).toEqual(['bash', '-c']);
      expect(argvSeenBy(words[2])).toEqual(ARGV.slice(1));
    });
  }

  it('an AppleScript string literal escapes backslashes and double quotes', () => {
    const text = `a "b" \\ c'd`;
    const literal = appleScriptString(text);
    expect(literal).toBe(`"a \\"b\\" \\\\ c'd"`);
    // Undo AppleScript's escapes: the shell command comes back exactly.
    expect(literal.slice(1, -1).replaceAll(/\\(.)/g, '$1')).toBe(text);
  });

  it('terminal-app and iterm2 embed the POSIX line as an AppleScript string', () => {
    launchTerminal('terminal-app', { argv: ARGV, keepOpen: true });
    launchTerminal('iterm2', { argv: ARGV });
    const literal = appleScriptString(posixCommandLine(ARGV));
    expect(spawned[0].args[1]).toBe(`tell application "Terminal" to do script ${literal}`);
    expect(spawned[1].args[1]).toContain(`write text ${literal}`);
  });

  it('Windows quoting follows the CommandLineToArgvW rules', () => {
    expect(windowsQuoteArg('plain')).toBe('plain');
    expect(windowsQuoteArg('a\\b')).toBe('a\\b');
    expect(windowsQuoteArg('')).toBe('""');
    expect(windowsQuoteArg('a b')).toBe('"a b"');
    expect(windowsQuoteArg('a"b')).toBe('"a\\"b"');
    expect(windowsQuoteArg('a\\"b')).toBe('"a\\\\\\"b"');
    expect(windowsQuoteArg('a b\\')).toBe('"a b\\\\"');
    expect(windowsQuoteArg(`it's a \\ "x"`)).toBe(`"it's a \\ \\"x\\""`);
    expect(windowsCommandLine(['ssh', 'a b'])).toBe('ssh "a b"');
  });

  it('cmd.exe escaping carets every metacharacter', () => {
    expect(cmdEscape('"a & b" | (c) %X% <d> !e! ^')).toBe(
      '^"a ^& b^" ^| ^(c^) ^%X^% ^<d^> ^!e^! ^^'
    );
  });

  it('cmd and windows-terminal pass the escaped line verbatim', () => {
    launchTerminal('cmd', { argv: ARGV });
    launchTerminal('windows-terminal', { argv: ARGV, title: 'Rediacc - m' });
    const line = cmdEscape(windowsCommandLine(ARGV));
    expect(spawned[0].args).toEqual(['/k', line]);
    expect(spawned[1].args).toEqual([
      '--title',
      '"Rediacc - m"',
      'cmd.exe',
      '/k',
      line.replaceAll(';', '\;'),
    ]);
  });

  it('powershell runs the argv through the stop-parsing token', () => {
    const script = Buffer.from(powershellEncodedCommand(ARGV, true), 'base64').toString('utf16le');
    expect(script).toBe(`& 'ssh' --% ${windowsCommandLine(ARGV.slice(1))}`);
    launchTerminal('powershell', { argv: ARGV, keepOpen: true });
    expect(spawned[0].args).toEqual([
      '-NoExit',
      '-EncodedCommand',
      powershellEncodedCommand(ARGV, true),
    ]);
  });

  it('wsl inside WSL passes only a launch script path, and the script runs the argv', () => {
    const argv = ['printf', '%s\\0', TRICKY, `$REDIACC_REPOSITORY`];
    launchTerminal('wsl', { argv, environmentVariables: ENV });
    const { file, args } = spawned[0];
    expect(file).toBe('cmd.exe');
    const scriptPath = args.at(-1) as string;
    expect(args).toEqual([
      '/c',
      'wt.exe',
      '--maximized',
      'new-tab',
      'wsl.exe',
      '-e',
      'bash',
      scriptPath,
    ]);
    expect(scriptPath).toMatch(/^[A-Za-z0-9/._-]+$/);
    const script = readFileSync(scriptPath, 'utf8');
    expect(script).not.toContain(SECRET);
    const out = execFileSync('bash', [scriptPath]).toString().split('\0').slice(0, -1);
    expect(out).toEqual([TRICKY, '$REDIACC_REPOSITORY']);
    // The script removed its own directory as it started.
    expect(existsSync(dirname(scriptPath))).toBe(false);
  });

  it('wsl on Windows hands bash the quoted argv', () => {
    wsl = false;
    launchTerminal('wsl', { argv: ARGV });
    const { file, args } = spawned[0];
    expect(file).toBe('wsl.exe');
    expect(args.slice(0, 3)).toEqual(['-e', 'bash', '-c']);
    expect(argvSeenBy(args[3])).toEqual(ARGV.slice(1));
  });
});
