import { existsSync } from 'fs';
import { homedir, tmpdir, platform as osPlatform } from 'os';
import { join } from 'path';
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
    const fs = require('fs') as typeof import('fs');
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
  const home = getHomePath();
  return join(home, '.rediacc');
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
    return windowsPath.replace(/\\/g, '/');
  }

  // Handle drive letters: C:\path -> /c/path
  const driveMatch = windowsPath.match(/^([A-Za-z]):/);
  if (driveMatch) {
    const driveLetter = driveMatch[1].toLowerCase();
    const rest = windowsPath.slice(2).replace(/\\/g, '/');
    return `/${driveLetter}${rest}`;
  }

  // Just replace backslashes
  return windowsPath.replace(/\\/g, '/');
}

/**
 * Converts a MSYS2/Cygwin path to Windows path format
 * e.g., /c/Users/foo -> C:\Users\foo
 */
export function unixToWindowsPath(unixPath: string): string {
  if (!unixPath) return unixPath;

  // Handle drive letters: /c/path -> C:\path
  const driveMatch = unixPath.match(/^\/([a-zA-Z])\//);
  if (driveMatch) {
    const driveLetter = driveMatch[1].toUpperCase();
    const rest = unixPath.slice(3).replace(/\//g, '\\');
    return `${driveLetter}:\\${rest}`;
  }

  return unixPath;
}

/**
 * Checks if a command exists in PATH
 */
export async function commandExists(command: string): Promise<boolean> {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
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
