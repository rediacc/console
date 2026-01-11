/**
 * VS Code Executable Detection and Launching
 * Ported from desktop/src/cli/core/vscode_shared.py
 */

import { spawn, execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  getPlatform,
  commandExists,
  isWSLAvailable,
  getDefaultWSLDistro,
  commandExistsInWSL,
  execInWSL,
} from '../utils/platform.js';
import type { VSCodeInfo, VSCodeInstallations, VSCodeLaunchOptions } from './types.js';

/**
 * Common VS Code installation paths by platform
 * Includes code-oss and codium variants
 */
const VSCODE_PATHS = {
  windows: [
    join(process.env.LOCALAPPDATA ?? '', 'Programs', 'Microsoft VS Code', 'Code.exe'),
    join(
      process.env.LOCALAPPDATA ?? '',
      'Programs',
      'Microsoft VS Code Insiders',
      'Code - Insiders.exe'
    ),
    join(process.env.PROGRAMFILES ?? '', 'Microsoft VS Code', 'Code.exe'),
    join(process.env['PROGRAMFILES(X86)'] ?? '', 'Microsoft VS Code', 'Code.exe'),
    // VSCodium on Windows
    join(process.env.LOCALAPPDATA ?? '', 'Programs', 'VSCodium', 'VSCodium.exe'),
    join(process.env.PROGRAMFILES ?? '', 'VSCodium', 'VSCodium.exe'),
  ],
  macos: [
    '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
    '/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code-insiders',
    join(
      process.env.HOME ?? '',
      'Applications',
      'Visual Studio Code.app',
      'Contents',
      'Resources',
      'app',
      'bin',
      'code'
    ),
    // VSCodium on macOS
    '/Applications/VSCodium.app/Contents/Resources/app/bin/codium',
    join(
      process.env.HOME ?? '',
      'Applications',
      'VSCodium.app',
      'Contents',
      'Resources',
      'app',
      'bin',
      'codium'
    ),
  ],
  linux: [
    '/usr/bin/code',
    '/usr/local/bin/code',
    '/snap/bin/code',
    '/var/lib/flatpak/exports/bin/com.visualstudio.code',
    join(process.env.HOME ?? '', '.local', 'bin', 'code'),
    // code-oss (Arch Linux package, etc.)
    '/usr/bin/code-oss',
    '/usr/local/bin/code-oss',
    // VSCodium
    '/usr/bin/codium',
    '/usr/local/bin/codium',
    '/snap/bin/codium',
    '/var/lib/flatpak/exports/bin/com.vscodium.codium',
    join(process.env.HOME ?? '', '.local', 'bin', 'codium'),
  ],
};

/**
 * VS Code variant command names to check
 */
const VSCODE_COMMANDS = ['code', 'code-insiders', 'code-oss', 'codium'] as const;

/**
 * Common VS Code installation paths inside WSL (Linux paths)
 */
const VSCODE_PATHS_WSL = [
  '/usr/bin/code',
  '/usr/local/bin/code',
  '/snap/bin/code',
  '/usr/bin/code-insiders',
  '/usr/bin/code-oss',
  '/usr/bin/codium',
  '/snap/bin/codium',
] as const;

/**
 * Checks environment variable for VS Code path override
 */
async function checkEnvVSCodePath(isWSL = false): Promise<VSCodeInfo | null> {
  const vscodePath = process.env.REDIACC_VSCODE_PATH;
  if (!vscodePath) return null;

  if (existsSync(vscodePath) || (await commandExists(vscodePath))) {
    const isInsiders = vscodePath.toLowerCase().includes('insiders');
    return { path: vscodePath, isInsiders, isWSL };
  }
  return null;
}

/**
 * Gets VS Code version from a command
 */
function getVSCodeVersion(cmd: string): string | undefined {
  try {
    return execSync(`${cmd} --version`, { encoding: 'utf8', timeout: 5000 }).split('\n')[0];
  } catch {
    return undefined;
  }
}

/**
 * Checks VS Code commands for availability
 */
async function findVSCodeByCommand(isWSL = false): Promise<VSCodeInfo | null> {
  for (const cmd of VSCODE_COMMANDS) {
    if (await commandExists(cmd)) {
      const version = getVSCodeVersion(cmd);
      if (version !== undefined) {
        return { path: cmd, version, isInsiders: cmd === 'code-insiders', isWSL };
      }
    }
  }
  return null;
}

/**
 * Checks known paths for VS Code installation
 */
function findVSCodeByPath(paths: readonly string[], isWSL = false): VSCodeInfo | null {
  for (const vscodePath of paths) {
    if (existsSync(vscodePath)) {
      const isInsiders = vscodePath.toLowerCase().includes('insiders');
      return { path: vscodePath, isInsiders, isWSL };
    }
  }
  return null;
}

/**
 * Finds VS Code installation on the system
 * Checks standard VS Code, Insiders, code-oss, and codium variants
 *
 * @returns VS Code info if found, null otherwise
 */
export async function findVSCode(): Promise<VSCodeInfo | null> {
  const platform = getPlatform();

  // Check environment variable first (allows user override)
  const envResult = await checkEnvVSCodePath();
  if (envResult) return envResult;

  // Try all command variants in order of preference
  const cmdResult = await findVSCodeByCommand();
  if (cmdResult) return cmdResult;

  // Check known paths
  const paths = VSCODE_PATHS[platform];
  return findVSCodeByPath(paths);
}

/**
 * Finds VS Code installation on Windows only (not WSL)
 * This is a helper for findAllVSCodeInstallations
 */
async function findVSCodeOnWindows(): Promise<VSCodeInfo | null> {
  if (getPlatform() !== 'windows') return null;

  // Check environment variable first (allows user override)
  const envResult = await checkEnvVSCodePath(false);
  if (envResult) return envResult;

  // Try all command variants in order of preference
  const cmdResult = await findVSCodeByCommand(false);
  if (cmdResult) return cmdResult;

  // Check known Windows paths
  return findVSCodeByPath(VSCODE_PATHS.windows, false);
}

/**
 * Finds VS Code by command in WSL
 */
async function findVSCodeByCommandInWSL(distro: string): Promise<VSCodeInfo | null> {
  for (const cmd of VSCODE_COMMANDS) {
    if (await commandExistsInWSL(cmd, distro)) {
      try {
        const { stdout } = await execInWSL(`${cmd} --version`, distro);
        const version = stdout.split('\n')[0]?.trim();
        return {
          path: cmd,
          version,
          isInsiders: cmd === 'code-insiders',
          isWSL: true,
          wslDistro: distro,
        };
      } catch {
        // Continue to next command
      }
    }
  }
  return null;
}

/**
 * Finds VS Code by known paths in WSL
 */
async function findVSCodeByPathInWSL(distro: string): Promise<VSCodeInfo | null> {
  for (const vscodePath of VSCODE_PATHS_WSL) {
    try {
      const { stdout } = await execInWSL(`test -f ${vscodePath} && echo exists`, distro);
      if (stdout.trim() === 'exists') {
        const isInsiders = vscodePath.includes('insiders');
        return { path: vscodePath, isInsiders, isWSL: true, wslDistro: distro };
      }
    } catch {
      // Continue to next path
    }
  }
  return null;
}

/**
 * Finds VS Code installation inside WSL
 * This is called from Windows to detect VS Code in the WSL environment
 */
export async function findVSCodeInWSL(): Promise<VSCodeInfo | null> {
  if (getPlatform() !== 'windows') return null;
  if (!(await isWSLAvailable())) return null;

  const distro = await getDefaultWSLDistro();
  if (!distro) return null;

  // Try command variants first
  const cmdResult = await findVSCodeByCommandInWSL(distro);
  if (cmdResult) return cmdResult;

  // Check known WSL paths
  return findVSCodeByPathInWSL(distro);
}

/**
 * Finds all VS Code installations (Windows and WSL)
 * Returns both if available, allowing the caller to choose
 */
export async function findAllVSCodeInstallations(): Promise<VSCodeInstallations> {
  const platform = getPlatform();

  if (platform !== 'windows') {
    // On non-Windows, just use the regular findVSCode
    const vscode = await findVSCode();
    return {
      windows: null,
      wsl: platform === 'linux' ? vscode : null,
    };
  }

  // On Windows, check both Windows and WSL installations in parallel
  const [windowsVSCode, wslVSCode] = await Promise.all([findVSCodeOnWindows(), findVSCodeInWSL()]);

  return {
    windows: windowsVSCode,
    wsl: wslVSCode,
  };
}

/**
 * Generates the VS Code Remote SSH URI
 *
 * @param sshHost - SSH host name (from SSH config)
 * @param remotePath - Path to open on remote
 * @returns vscode-remote:// URI
 */
export function generateRemoteUri(sshHost: string, remotePath: string): string {
  // Encode the path for URI
  const encodedPath = encodeURIComponent(remotePath).replaceAll('%2F', '/');
  return `vscode-remote://ssh-remote+${sshHost}${encodedPath}`;
}

/**
 * Launches VS Code with a remote folder
 *
 * @param vscodeInfo - VS Code installation info
 * @param uri - Remote URI to open
 * @param options - Launch options
 * @returns Promise that resolves when launched (or process exits if waitForClose)
 */
export async function launchVSCode(
  vscodeInfo: VSCodeInfo,
  uri: string,
  options?: VSCodeLaunchOptions
): Promise<void> {
  const args: string[] = [];

  if (options?.newWindow) {
    args.push('--new-window');
  }

  if (options?.waitForClose) {
    args.push('--wait');
  }

  args.push('--folder-uri', uri);

  return new Promise((resolve, reject) => {
    let proc;

    if (vscodeInfo.isWSL && vscodeInfo.wslDistro) {
      // Launch VS Code via WSL
      // We need to run: wsl.exe -d <distro> <vscode-path> <args>
      const wslArgs = ['-d', vscodeInfo.wslDistro, vscodeInfo.path, ...args];
      proc = spawn('wsl.exe', wslArgs, {
        detached: !options?.waitForClose,
        stdio: 'ignore',
      });
    } else {
      // Launch native VS Code (Windows/macOS/Linux)
      proc = spawn(vscodeInfo.path, args, {
        detached: !options?.waitForClose,
        stdio: 'ignore',
      });
    }

    if (options?.waitForClose) {
      proc.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`VS Code exited with code ${code}`));
        }
      });
    } else {
      proc.unref();
      // Give VS Code a moment to start
      setTimeout(resolve, 500);
    }

    proc.on('error', reject);
  });
}

/**
 * Checks if VS Code Remote SSH extension is likely installed
 * This is a heuristic check based on extension directory
 *
 * @returns True if extension appears to be installed
 */
export async function isRemoteSSHExtensionInstalled(): Promise<boolean> {
  const platform = getPlatform();
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';

  let extensionsPath: string;
  if (platform === 'windows') {
    extensionsPath = join(home, '.vscode', 'extensions');
  } else {
    extensionsPath = join(home, '.vscode', 'extensions');
  }

  if (!existsSync(extensionsPath)) {
    return false;
  }

  // Check for any remote-ssh extension directory
  try {
    const { readdirSync } = await import('node:fs');
    const extensions = readdirSync(extensionsPath);
    return extensions.some((ext) => ext.startsWith('ms-vscode-remote.remote-ssh-'));
  } catch {
    return false;
  }
}
