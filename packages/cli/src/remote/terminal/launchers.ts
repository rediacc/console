import { type ChildProcess, spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { shellQuote } from '../../utils/shell-quote.js';
import type { TerminalLaunchOptions, TerminalType } from '../types/index.js';
import { getPlatform, isWSL } from '../utils/platform.js';
import { findMSYS2Installation } from './detector.js';

/**
 * Launch result
 */
export interface LaunchResult {
  success: boolean;
  process?: ChildProcess;
  error?: string;
}

/**
 * Launcher function type
 */
type LauncherFn = (options: TerminalLaunchOptions) => LaunchResult;

/**
 * Sensitive environment variable prefixes that never reach a terminal process,
 * neither from this process's environment nor from the launch options. A
 * caller delivers secrets to a remote session by other means (term stages
 * them on the machine, see utils/secret-env.ts).
 */
const SENSITIVE_ENV_PREFIXES = ['REDIACC_TOKEN', 'REDIACC_API_KEY', 'REDIACC_SECRET'] as const;

function isSensitiveEnvName(key: string): boolean {
  return SENSITIVE_ENV_PREFIXES.some((prefix) => key.startsWith(prefix));
}

/** The environment of a spawned terminal: this process's and the options', sensitive names removed. */
function terminalEnv(options: TerminalLaunchOptions): NodeJS.ProcessEnv {
  return Object.fromEntries(
    Object.entries({ ...process.env, ...options.environmentVariables }).filter(
      ([key]) => !isSensitiveEnvName(key)
    )
  );
}

/** A POSIX shell command line that runs `argv` exactly, each element one word. */
export function posixCommandLine(argv: string[]): string {
  return argv.map(shellQuote).join(' ');
}

/** An AppleScript string literal holding `text` verbatim. */
export function appleScriptString(text: string): string {
  return `"${text.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`;
}

/** One argument quoted the way CommandLineToArgvW and the MSVC runtime split a command line. */
export function windowsQuoteArg(arg: string): string {
  if (arg !== '' && !/[\s"]/.test(arg)) return arg;
  let out = '"';
  let backslashes = 0;
  for (const ch of arg) {
    if (ch === '\\') {
      backslashes++;
      continue;
    }
    if (ch === '"') {
      out += `${'\\'.repeat(backslashes * 2 + 1)}"`;
    } else {
      out += `${'\\'.repeat(backslashes)}${ch}`;
    }
    backslashes = 0;
  }
  return `${out}${'\\'.repeat(backslashes * 2)}"`;
}

/** A Windows command line for `argv`, before any cmd.exe escaping. */
export function windowsCommandLine(argv: string[]): string {
  return argv.map(windowsQuoteArg).join(' ');
}

/** A command line escaped for cmd.exe: each metacharacter carries a caret, so cmd passes it on literally. */
export function cmdEscape(commandLine: string): string {
  return commandLine.replaceAll(/[()%!^"<>&|]/g, '^$&');
}

/** Windows Terminal splits its own command line on `;`; an escaped one passes through. */
function wtEscape(commandLine: string): string {
  return commandLine.replaceAll(';', '\\;');
}

/**
 * A PowerShell script that runs `argv` through the stop-parsing token, so the
 * Windows command line reaches the program verbatim on every PowerShell
 * version, and its `-EncodedCommand` form (UTF-16LE, base64), so the script
 * itself crosses powershell.exe's own command line without quoting.
 */
export function powershellEncodedCommand(argv: string[], keepOpen: boolean): string {
  const [program, ...args] = argv;
  const run = `& '${program.replaceAll("'", "''")}' --% ${windowsCommandLine(args)}`;
  const script = keepOpen ? run : `${run}\nRead-Host -Prompt 'Press Enter to exit'`;
  return Buffer.from(script, 'utf16le').toString('base64');
}

/**
 * Builds environment variable exports for bash. Sensitive names are left out,
 * whatever the caller passes: this text is a command line.
 */
export function buildBashExports(env?: Record<string, string>): string {
  const exports = Object.entries(env ?? {})
    .filter(([key]) => !isSensitiveEnvName(key))
    .map(([key, value]) => `export ${key}=${shellQuote(value)}`)
    .join(' && ');
  return exports ? `${exports} && ` : '';
}

/**
 * A bash script holding the WSL session's exports and command, in a private
 * 0700 directory; it deletes its directory as it starts. Whatever crosses
 * cmd.exe, wt.exe and wsl.exe is then only this path, which needs no quoting
 * on any of them, and no command text rides their argv.
 */
export function writeWslLaunchScript(options: TerminalLaunchOptions): string {
  const dir = mkdtempSync(join(tmpdir(), 'rdc-term-'));
  const path = join(dir, 'launch.sh');
  const lines = [
    '#!/bin/bash',
    `rm -rf -- ${shellQuote(dir)}`,
    `${buildBashExports(options.environmentVariables)}${posixCommandLine(options.argv)}`,
    '',
  ];
  writeFileSync(path, lines.join('\n'), { mode: 0o700 });
  return path;
}

function spawnDetached(
  file: string,
  args: string[],
  options: TerminalLaunchOptions,
  extra: { cwd?: string; windowsVerbatimArguments?: boolean } = {}
): LaunchResult {
  try {
    const proc = spawn(file, args, {
      stdio: 'ignore',
      detached: true,
      env: terminalEnv(options),
      ...extra,
    });
    proc.unref();
    return { success: true, process: proc };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Launchers for each terminal type
 */
const launchers: Record<TerminalType, LauncherFn> = {
  'gnome-terminal': (options) => {
    const args = ['--maximize', '--', 'bash', '-c', posixCommandLine(options.argv)];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    return spawnDetached('gnome-terminal', args, options);
  },

  konsole: (options) => {
    const args = ['--fullscreen', '-e', 'bash', '-c', posixCommandLine(options.argv)];
    if (options.title) {
      args.unshift('-p', `tabtitle=${options.title}`);
    }
    if (options.workingDirectory) {
      args.unshift('--workdir', options.workingDirectory);
    }
    return spawnDetached('konsole', args, options);
  },

  'xfce4-terminal': (options) => {
    const args = ['--maximize', '-x', 'bash', '-c', posixCommandLine(options.argv)];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    return spawnDetached('xfce4-terminal', args, options);
  },

  xterm: (options) => {
    const args = ['-maximized', '-e', 'bash', '-c', posixCommandLine(options.argv)];
    if (options.title) {
      args.unshift('-T', options.title);
    }
    return spawnDetached('xterm', args, options, { cwd: options.workingDirectory });
  },

  'mate-terminal': (options) => {
    // -e takes one string the terminal splits with shell rules (g_shell_parse_argv).
    const args = [
      '--maximize',
      '-e',
      posixCommandLine(['bash', '-c', posixCommandLine(options.argv)]),
    ];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    return spawnDetached('mate-terminal', args, options);
  },

  terminator: (options) => {
    const args = [
      '--maximise',
      '-e',
      posixCommandLine(['bash', '-c', posixCommandLine(options.argv)]),
    ];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    return spawnDetached('terminator', args, options);
  },

  'terminal-app': (options) => {
    // macOS Terminal.app runs the string in the user's login shell.
    const command = posixCommandLine(options.argv);
    const script = `tell application "Terminal" to do script ${appleScriptString(
      options.keepOpen ? command : `${command}; exit`
    )}`;
    return spawnDetached('osascript', ['-e', script], options);
  },

  iterm2: (options) => {
    const script = `
      tell application "iTerm"
        create window with default profile
        tell current session of current window
          write text ${appleScriptString(posixCommandLine(options.argv))}
        end tell
      end tell
    `;
    return spawnDetached('osascript', ['-e', script], options);
  },

  'windows-terminal': (options) => {
    const args: string[] = [];
    if (options.title) {
      args.push('--title', windowsQuoteArg(options.title));
    }
    args.push('cmd.exe', '/k', wtEscape(cmdEscape(windowsCommandLine(options.argv))));
    return spawnDetached('wt.exe', args, options, {
      cwd: options.workingDirectory,
      windowsVerbatimArguments: true,
    });
  },

  powershell: (options) =>
    spawnDetached(
      'powershell.exe',
      ['-NoExit', '-EncodedCommand', powershellEncodedCommand(options.argv, !!options.keepOpen)],
      options,
      { cwd: options.workingDirectory }
    ),

  cmd: (options) =>
    spawnDetached('cmd.exe', ['/k', cmdEscape(windowsCommandLine(options.argv))], options, {
      cwd: options.workingDirectory,
      windowsVerbatimArguments: true,
    }),

  mintty: (options) => {
    const msys2Path = findMSYS2Installation();
    if (!msys2Path) {
      return { success: false, error: 'MSYS2 not found' };
    }

    const minttyExe = join(msys2Path, 'usr', 'bin', 'mintty.exe');
    const bashExe = join(msys2Path, 'usr', 'bin', 'bash.exe');

    const args = ['-w', 'max'];
    if (options.title) {
      args.push('-t', options.title);
    }
    args.push('-e', bashExe, '-l', '-c', posixCommandLine(options.argv));
    return spawnDetached(minttyExe, args, options);
  },

  wsl: (options) => {
    if (!isWSL()) {
      // On Windows: wsl.exe hands the arguments to bash as an argv.
      return spawnDetached(
        'wsl.exe',
        ['-e', 'bash', '-c', posixCommandLine(options.argv)],
        options,
        {
          cwd: options.workingDirectory,
        }
      );
    }
    // Inside WSL: a new Windows Terminal tab starts a fresh WSL bash, which inherits nothing from this process, so the exports and the command travel in a launch script whose path is the only argument.
    let scriptPath: string;
    try {
      scriptPath = writeWslLaunchScript(options);
    } catch (error) {
      return { success: false, error: String(error) };
    }
    const viaWt = spawnDetached(
      'cmd.exe',
      ['/c', 'wt.exe', '--maximized', 'new-tab', 'wsl.exe', '-e', 'bash', scriptPath],
      options,
      { cwd: process.env.WINDIR ?? DEFAULTS.PLATFORM.WINDOWS_SYSTEM }
    );
    if (viaWt.success) return viaWt;
    return spawnDetached(
      'powershell.exe',
      ['-Command', 'wsl.exe', '-e', 'bash', scriptPath],
      options
    );
  },
};

/**
 * Launches a terminal with the specified options
 *
 * @param terminalType - Terminal type to launch
 * @param options - Launch options
 * @returns Launch result
 */
export function launchTerminal(
  terminalType: TerminalType,
  options: TerminalLaunchOptions
): LaunchResult {
  const launcher = launchers[terminalType];
  return launcher(options);
}

/**
 * Gets the default terminal type for the current platform
 */
export function getDefaultTerminalType(): TerminalType {
  const platform = getPlatform();

  switch (platform) {
    case 'windows':
      return 'windows-terminal';
    case 'macos':
      return 'terminal-app';
    case 'linux':
    default:
      return isWSL() ? 'wsl' : 'gnome-terminal';
  }
}
