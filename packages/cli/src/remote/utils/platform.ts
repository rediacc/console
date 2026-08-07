import { execSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { platform as osPlatform, tmpdir } from 'node:os';
import type { Platform } from '../types/index.js';

/**
 * Detects if running under Windows Subsystem for Linux
 */
export function isWSL(): boolean {
  if (osPlatform() !== 'linux') return false;

  try {
    if (existsSync('/proc/version')) {
      const version = readFileSync('/proc/version', 'utf8').toLowerCase();
      return version.includes('microsoft') || version.includes('wsl');
    }
  } catch {
    return false;
  }
  return false;
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
 * Gets the current platform
 */
export function getPlatform(): Platform {
  const p = osPlatform();
  if (p === 'win32') return 'windows';
  if (p === 'darwin') return 'macos';
  return 'linux';
}

/**
 * Gets the Windows user home directory from within WSL.
 * Returns the WSL-accessible path (e.g., /mnt/c/Users/username).
 * Caches the result for performance since it shells out to cmd.exe.
 * Returns null if not in WSL or if detection fails.
 */
let _windowsHomeCache: string | null | undefined;

export function getWindowsHomeInWSL(): string | null {
  if (_windowsHomeCache !== undefined) return _windowsHomeCache;

  if (!isWSL()) {
    _windowsHomeCache = null;
    return null;
  }

  // Try multiple cmd.exe locations — it may not be in PATH inside WSL
  const cmdPaths = ['cmd.exe', '/mnt/c/Windows/System32/cmd.exe'];

  for (const cmdPath of cmdPaths) {
    try {
      const result = execSync(`"${cmdPath}" /C "echo %USERPROFILE%" 2>/dev/null`, {
        encoding: 'utf8',
        timeout: 5000,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      const winPath = result.trim().replaceAll('\r', '');
      if (winPath && !winPath.includes('%USERPROFILE%')) {
        _windowsHomeCache = windowsPathToWSL(winPath);
        return _windowsHomeCache;
      }
    } catch {
      // Try next path
    }
  }

  _windowsHomeCache = null;
  return null;
}

/**
 * Gets the home directory for SSH-related files.
 * In WSL, returns the Windows user home (accessible as /mnt/c/Users/...)
 * so that SSH config and keys are accessible to Windows VS Code/SSH.
 *
 * The WSL branch is deliberate and must stay: Windows-side VS Code Remote SSH
 * reads remote.SSH.configFile (see vscode/settings.ts getSSHConfigFileSetting),
 * and it cannot resolve a path inside the Linux $HOME. Consequence for callers:
 * this is NOT $HOME on WSL, so never print a hardcoded "~/.ssh/..." to the user.
 * Interpolate the resolved path instead.
 */
export function getSSHHome(): string {
  if (isWSL()) {
    const winHome = getWindowsHomeInWSL();
    if (winHome) return winHome;
  }
  return process.env.HOME ?? process.env.USERPROFILE ?? '';
}

/**
 * Gets the system temp directory
 */
export function getTempPath(): string {
  return tmpdir();
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
