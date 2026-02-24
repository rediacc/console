import { existsSync } from 'node:fs';
import { homedir, platform as osPlatform, tmpdir } from 'node:os';
import { getConfigDir } from '@rediacc/shared/paths';
import type { Platform, PlatformInfo, WindowsSubsystem } from '../types/index.js';

/**
 * Detects if running under Windows Subsystem for Linux
 */
export function isWSL(): boolean {
  if (osPlatform() !== 'linux') return false;

  // Check for WSL-specific indicators
  try {
    // WSL1 and WSL2 have /proc/version containing "Microsoft" or "microsoft"
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('node:fs') as typeof import('node:fs');
    const version = fs.readFileSync('/proc/version', 'utf8').toLowerCase();
    return version.includes('microsoft') || version.includes('wsl');
  } catch {
    return false;
  }
}

/**
 * Detects if running under MSYS2
 */
export function isMSYS2(): boolean {
  return (
    typeof process.env.MSYSTEM === 'string' &&
    ['MINGW64', 'MINGW32', 'UCRT64', 'CLANG64', 'MSYS'].includes(process.env.MSYSTEM)
  );
}

/**
 * Detects if running under Cygwin
 */
export function isCygwin(): boolean {
  return (
    typeof process.env.CYGWIN !== 'undefined' ||
    (osPlatform() === 'win32' && existsSync('/cygdrive'))
  );
}

/**
 * Gets the current platform
 */
export function getPlatform(): Platform {
  const p = osPlatform();
  if (p === 'win32') return 'windows';
  if (p === 'darwin') return 'macos';
  return 'linux';
}

/**
 * Gets the Windows subsystem if applicable
 */
export function getWindowsSubsystem(): WindowsSubsystem | undefined {
  if (getPlatform() !== 'windows' && !isWSL()) return undefined;

  if (isWSL()) return 'wsl';
  if (isMSYS2()) return 'msys2';
  if (isCygwin()) return 'cygwin';
  return 'native';
}

/**
 * Gets the user's home directory
 */
export function getHomePath(): string {
  return homedir();
}

/**
 * Gets the system temp directory
 */
export function getTempPath(): string {
  return tmpdir();
}

/**
 * Gets the Rediacc config directory path
 */
export function getConfigPath(): string {
  return getConfigDir();
}

/**
 * Gets comprehensive platform information
 */
export function getPlatformInfo(): PlatformInfo {
  return {
    platform: getPlatform(),
    isWSL: isWSL(),
    isMSYS2: isMSYS2(),
    windowsSubsystem: getWindowsSubsystem(),
    homePath: getHomePath(),
    tempPath: getTempPath(),
    configPath: getConfigPath(),
  };
}

/**
 * Converts a Windows path to MSYS2/Cygwin path format
 * e.g., C:\Users\foo -> /c/Users/foo
 */
export function windowsToUnixPath(windowsPath: string): string {
  if (!windowsPath) return windowsPath;

  // Handle UNC paths: \\server\share -> //server/share
  if (windowsPath.startsWith('\\\\')) {
    return windowsPath.replaceAll('\\', '/');
  }

  // Handle drive letters: C:\path -> /c/path
  const driveMatch = /^([A-Za-z]):/.exec(windowsPath);
  if (driveMatch) {
    const driveLetter = driveMatch[1].toLowerCase();
    const rest = windowsPath.slice(2).replaceAll('\\', '/');
    return `/${driveLetter}${rest}`;
  }

  // Just replace backslashes
  return windowsPath.replaceAll('\\', '/');
}

/**
 * Converts a MSYS2/Cygwin path to Windows path format
 * e.g., /c/Users/foo -> C:\Users\foo
 */
export function unixToWindowsPath(unixPath: string): string {
  if (!unixPath) return unixPath;

  // Handle drive letters: /c/path -> C:\path
  const driveMatch = /^\/([a-zA-Z])\//.exec(unixPath);
  if (driveMatch) {
    const driveLetter = driveMatch[1].toUpperCase();
    const rest = unixPath.slice(3).replaceAll('/', '\\');
    return `${driveLetter}:\\${rest}`;
  }

  return unixPath;
}

/**
 * Checks if a command exists in PATH
 */
export async function commandExists(command: string): Promise<boolean> {
  const { exec } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const execAsync = promisify(exec);

  const checkCommand = getPlatform() === 'windows' ? `where ${command}` : `which ${command}`;

  try {
    await execAsync(checkCommand);
    return true;
  } catch {
    return false;
  }
}

/**
 * Gets the path separator for the current platform
 */
export function getPathSeparator(): string {
  return getPlatform() === 'windows' ? ';' : ':';
}

/**
 * Gets the directory separator for the current platform
 */
export function getDirSeparator(): string {
  return getPlatform() === 'windows' ? '\\' : '/';
}

/**
 * Checks if WSL is available on the Windows system
 * This is called from Windows (not from inside WSL)
 */
export async function isWSLAvailable(): Promise<boolean> {
  if (getPlatform() !== 'windows') return false;

  const { exec } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const execAsync = promisify(exec);

  try {
    await execAsync('wsl.exe --version', { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Gets the default WSL distribution name
 * Returns null if WSL is not available or no distro is installed
 */
export async function getDefaultWSLDistro(): Promise<string | null> {
  if (getPlatform() !== 'windows') return null;

  const { exec } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const execAsync = promisify(exec);

  try {
    // Get list of distros - the default has "(Default)" marker
    const { stdout } = await execAsync('wsl.exe --list --quiet', {
      timeout: 5000,
      encoding: 'utf8',
    });

    // Parse output - first line is typically the default distro
    // Output may have UTF-16 BOM and null bytes on Windows
    const lines = stdout
      .replaceAll('\0', '') // Remove null bytes
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);

    if (lines.length > 0) {
      return lines[0];
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Checks if a command exists inside WSL
 * This is called from Windows to check if a command exists in the WSL environment
 */
export async function commandExistsInWSL(command: string, distro?: string): Promise<boolean> {
  if (getPlatform() !== 'windows') return false;

  const { exec } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const execAsync = promisify(exec);

  try {
    const distroArg = distro ? `-d ${distro} ` : '';
    await execAsync(`wsl.exe ${distroArg}which ${command}`, { timeout: 10000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Executes a command inside WSL and returns the output
 * This is called from Windows to run commands in the WSL environment
 */
export async function execInWSL(
  command: string,
  distro?: string
): Promise<{ stdout: string; stderr: string }> {
  if (getPlatform() !== 'windows') {
    throw new Error('execInWSL can only be called from Windows');
  }

  const { exec } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const execAsync = promisify(exec);

  const distroArg = distro ? `-d ${distro} ` : '';
  return execAsync(`wsl.exe ${distroArg}${command}`, {
    timeout: 30000,
    encoding: 'utf8',
  });
}

/**
 * Converts a Windows path to WSL path format
 * e.g., C:\Users\john\.ssh -> /mnt/c/Users/john/.ssh
 */
export function windowsPathToWSL(windowsPath: string): string {
  if (!windowsPath) return windowsPath;

  // Handle drive letters: C:\path -> /mnt/c/path
  const driveMatch = /^([A-Za-z]):/.exec(windowsPath);
  if (driveMatch) {
    const driveLetter = driveMatch[1].toLowerCase();
    const rest = windowsPath.slice(2).replaceAll('\\', '/');
    return `/mnt/${driveLetter}${rest}`;
  }

  // Just replace backslashes
  return windowsPath.replaceAll('\\', '/');
}

/**
 * Converts a WSL path to Windows path format
 * e.g., /mnt/c/Users/john/.ssh -> C:\Users\john\.ssh
 */
export function wslPathToWindows(wslPath: string): string {
  if (!wslPath) return wslPath;

  // Handle /mnt/c/ paths: /mnt/c/path -> C:\path
  const mntMatch = /^\/mnt\/([a-zA-Z])\//.exec(wslPath);
  if (mntMatch) {
    const driveLetter = mntMatch[1].toUpperCase();
    const rest = wslPath.slice(7).replaceAll('/', '\\');
    return `${driveLetter}:\\${rest}`;
  }

  return wslPath;
}
