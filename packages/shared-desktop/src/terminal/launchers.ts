import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { findMSYS2Installation } from './detector.js';
import { getPlatform, isWSL } from '../utils/platform.js';
import type { TerminalType, TerminalLaunchOptions } from '../types/index.js';

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
 * Sensitive environment variable prefixes that should not be passed to child processes.
 * This prevents token leakage to spawned terminal processes.
 */
const SENSITIVE_ENV_PREFIXES = ['REDIACC_TOKEN', 'REDIACC_API_KEY', 'REDIACC_SECRET'] as const;

/**
 * Filters sensitive environment variables from being passed to child processes.
 * This is a security measure to prevent token leakage.
 *
 * @param env - Environment variables to filter
 * @returns Filtered environment variables
 */
function filterSensitiveEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return Object.fromEntries(
    Object.entries(env).filter(
      ([key]) => !SENSITIVE_ENV_PREFIXES.some((prefix) => key.startsWith(prefix))
    )
  ) as NodeJS.ProcessEnv;
}

/**
 * Escapes a command for shell execution
 */
function escapeCommand(cmd: string): string {
  // Simple escaping for shell
  return cmd.replaceAll("'", "'\\''");
}

/**
 * Builds environment variable exports for bash
 */
function buildBashExports(env?: Record<string, string>): string {
  if (!env) return '';
  const exports = Object.entries(env)
    .map(([key, value]) => `export ${key}='${escapeCommand(value)}'`)
    .join(' && ');
  return exports ? `${exports} && ` : '';
}

/**
 * Launchers for each terminal type
 */
const launchers: Record<TerminalType, LauncherFn> = {
  'gnome-terminal': (options) => {
    const args = ['--maximize', '--', 'bash', '-c', options.command];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    try {
      const proc = spawn('gnome-terminal', args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  konsole: (options) => {
    const args = ['--fullscreen', '-e', 'bash', '-c', options.command];
    if (options.title) {
      args.unshift('-p', `tabtitle=${options.title}`);
    }
    if (options.workingDirectory) {
      args.unshift('--workdir', options.workingDirectory);
    }
    try {
      const proc = spawn('konsole', args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  'xfce4-terminal': (options) => {
    const args = ['--maximize', '-x', 'bash', '-c', options.command];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    try {
      const proc = spawn('xfce4-terminal', args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  xterm: (options) => {
    const args = ['-maximized', '-e', 'bash', '-c', options.command];
    if (options.title) {
      args.unshift('-T', options.title);
    }
    try {
      const proc = spawn('xterm', args, {
        stdio: 'ignore',
        detached: true,
        cwd: options.workingDirectory,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  'mate-terminal': (options) => {
    const args = ['--maximize', '-e', `bash -c "${escapeCommand(options.command)}"`];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    try {
      const proc = spawn('mate-terminal', args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  terminator: (options) => {
    const args = ['--maximise', '-e', `bash -c "${escapeCommand(options.command)}"`];
    if (options.title) {
      args.unshift('--title', options.title);
    }
    if (options.workingDirectory) {
      args.unshift('--working-directory', options.workingDirectory);
    }
    try {
      const proc = spawn('terminator', args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  'terminal-app': (options) => {
    // macOS Terminal.app
    const script = options.keepOpen
      ? `tell application "Terminal" to do script "${escapeCommand(options.command)}"`
      : `tell application "Terminal" to do script "${escapeCommand(options.command)}; exit"`;

    try {
      const proc = spawn('osascript', ['-e', script], {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  iterm2: (options) => {
    // iTerm2 on macOS
    const script = `
      tell application "iTerm"
        create window with default profile
        tell current session of current window
          write text "${escapeCommand(options.command)}"
        end tell
      end tell
    `;

    try {
      const proc = spawn('osascript', ['-e', script], {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  'windows-terminal': (options) => {
    const args: string[] = ['wt.exe'];
    if (options.title) {
      args.push('--title', options.title);
    }
    args.push('cmd.exe', '/k', options.command);

    try {
      const proc = spawn(args[0], args.slice(1), {
        stdio: 'ignore',
        detached: true,
        cwd: options.workingDirectory,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
        shell: true,
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  powershell: (options) => {
    const psCommand = options.keepOpen
      ? options.command
      : `${options.command}; Read-Host -Prompt 'Press Enter to exit'`;

    try {
      const proc = spawn('powershell.exe', ['-NoExit', '-Command', psCommand], {
        stdio: 'ignore',
        detached: true,
        cwd: options.workingDirectory,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  cmd: (options) => {
    try {
      const proc = spawn('cmd.exe', ['/k', options.command], {
        stdio: 'ignore',
        detached: true,
        cwd: options.workingDirectory,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

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
    args.push('-e', bashExe, '-l', '-c', options.command);

    try {
      const proc = spawn(minttyExe, args, {
        stdio: 'ignore',
        detached: true,
        env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
      });
      proc.unref();
      return { success: true, process: proc };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },

  wsl: (options) => {
    // Launch from WSL context or to WSL from Windows
    if (isWSL()) {
      // We're in WSL, try to use Windows Terminal
      // Build environment exports to pass through to WSL
      const envExports = buildBashExports(options.environmentVariables);
      const fullCommand = envExports + options.command;
      const wtArgs = [
        'wt.exe',
        '--maximized',
        'new-tab',
        'wsl.exe',
        '-e',
        'bash',
        '-c',
        fullCommand,
      ];
      try {
        const proc = spawn('cmd.exe', ['/c', wtArgs.join(' ')], {
          stdio: 'ignore',
          detached: true,
          cwd: process.env.WINDIR ?? DEFAULTS.PLATFORM.WINDOWS_SYSTEM,
          env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
        });
        proc.unref();
        return { success: true, process: proc };
      } catch {
        // Fallback to PowerShell
        try {
          const proc = spawn(
            'powershell.exe',
            ['-Command', `wsl.exe -e bash -c "${fullCommand}"`],
            {
              stdio: 'ignore',
              detached: true,
              env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
            }
          );
          proc.unref();
          return { success: true, process: proc };
        } catch (error) {
          return { success: false, error: String(error) };
        }
      }
    } else {
      // We're on Windows, launch WSL
      try {
        const proc = spawn('wsl.exe', ['-e', 'bash', '-c', options.command], {
          stdio: 'ignore',
          detached: true,
          cwd: options.workingDirectory,
          env: { ...filterSensitiveEnv(process.env), ...options.environmentVariables },
        });
        proc.unref();
        return { success: true, process: proc };
      } catch (error) {
        return { success: false, error: String(error) };
      }
    }
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
 * Launches a terminal in the current TTY (for CLI use)
 * This is for when we're already in a terminal and want to run inline
 *
 * @param command - Command to run
 * @param options - Additional options
 * @returns Child process
 */
export function launchInline(
  command: string,
  options?: {
    cwd?: string;
    env?: Record<string, string>;
  }
): ChildProcess {
  const shell = getPlatform() === 'windows' ? 'cmd.exe' : '/bin/bash';
  const shellArgs = getPlatform() === 'windows' ? ['/c', command] : ['-c', command];

  return spawn(shell, shellArgs, {
    stdio: 'inherit',
    cwd: options?.cwd,
    env: { ...filterSensitiveEnv(process.env), ...options?.env },
  });
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
