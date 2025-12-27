/**
 * VS Code Executable Detection and Launching
 * Ported from desktop/src/cli/core/vscode_shared.py
 */

import { spawn, execSync } from 'child_process';
import { existsSync } from 'fs';
import { join } from 'path';
import { getPlatform, commandExists } from '../utils/platform.js';
import type { VSCodeInfo, VSCodeLaunchOptions } from './types.js';

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
 * Finds VS Code installation on the system
 * Checks standard VS Code, Insiders, code-oss, and codium variants
 *
 * @returns VS Code info if found, null otherwise
 */
export async function findVSCode(): Promise<VSCodeInfo | null> {
  const platform = getPlatform();

  // Check environment variable first (allows user override)
  const vscodePath = process.env.REDIACC_VSCODE_PATH;
  if (vscodePath) {
    if (existsSync(vscodePath) || (await commandExists(vscodePath))) {
      const isInsiders = vscodePath.toLowerCase().includes('insiders');
      return {
        path: vscodePath,
        isInsiders,
      };
    }
  }

  // Try all command variants in order of preference
  for (const cmd of VSCODE_COMMANDS) {
    if (await commandExists(cmd)) {
      try {
        const version = execSync(`${cmd} --version`, { encoding: 'utf8', timeout: 5000 }).split(
          '\n'
        )[0];
        return {
          path: cmd,
          version,
          isInsiders: cmd === 'code-insiders',
        };
      } catch {
        // Continue to next command
      }
    }
  }

  // Check known paths
  const paths = VSCODE_PATHS[platform];
  for (const vscodePath of paths) {
    if (existsSync(vscodePath)) {
      const isInsiders = vscodePath.toLowerCase().includes('insiders');
      return {
        path: vscodePath,
        isInsiders,
      };
    }
  }

  return null;
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
  const encodedPath = encodeURIComponent(remotePath).replace(/%2F/g, '/');
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
    const proc = spawn(vscodeInfo.path, args, {
      detached: !options?.waitForClose,
      stdio: 'ignore',
    });

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
    const { readdirSync } = await import('fs');
    const extensions = readdirSync(extensionsPath);
    return extensions.some((ext) => ext.startsWith('ms-vscode-remote.remote-ssh-'));
  } catch {
    return false;
  }
}
