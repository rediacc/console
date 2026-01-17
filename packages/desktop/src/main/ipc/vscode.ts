/**
 * VS Code IPC Handlers
 * Provides IPC handlers for launching VS Code with SSH remote connections
 *
 * Uses shared-desktop utilities for SSH config and key management,
 * which write to ~/.ssh/config_rediacc (matching legacy Python desktop behavior)
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { windowsPathToWSL } from '@rediacc/shared-desktop/utils/platform';
import {
  addSSHConfigEntry,
  findAllVSCodeInstallations,
  findVSCode,
  generateConnectionName,
  generateRemoteUri,
  launchVSCode,
  persistKnownHosts,
  persistSSHKey,
  type SSHConfigEntry,
  type VSCodeInfo,
  type VSCodeInstallations,
  type VSCodePreference,
} from '@rediacc/shared-desktop/vscode';
import { app, ipcMain } from 'electron';
import { DEFAULTS } from '@rediacc/shared/config';

/**
 * Path to store VS Code preference
 */
function getPreferencePath(): string {
  return join(app.getPath('userData'), 'vscode-preference.json');
}

/**
 * Options for launching VS Code with SSH remote
 */
export interface VSCodeLaunchOptions {
  /** Team name */
  teamName: string;
  /** Machine name */
  machineName: string;
  /** Repository name (optional) */
  repositoryName?: string;
  /** SSH host IP or hostname */
  host: string;
  /** SSH port (default: 22) */
  port?: number;
  /** SSH user */
  user: string;
  /** SSH private key content */
  privateKey: string;
  /** SSH known hosts entry */
  known_hosts?: string;
  /** Remote path to open */
  remotePath: string;
  /** Datastore path on remote machine */
  datastore?: string;
  /** Open in new window */
  newWindow?: boolean;
  /** Preferred VS Code type (windows or wsl) - if not set, uses stored preference or auto-detect */
  preferredType?: 'windows' | 'wsl';
}

/**
 * Result of VS Code launch attempt
 */
export interface VSCodeLaunchResult {
  success: boolean;
  error?: string;
  connectionName?: string;
}

/**
 * Helper to get the VS Code installation based on preference
 */
async function getVSCodeForLaunch(preferredType?: 'windows' | 'wsl'): Promise<VSCodeInfo | null> {
  const installations = await findAllVSCodeInstallations();

  // If a specific type is requested, use that
  if (preferredType === 'wsl' && installations.wsl) {
    return installations.wsl;
  }
  if (preferredType === 'windows' && installations.windows) {
    return installations.windows;
  }

  // If preference is set but that type isn't available, fall back
  if (preferredType) {
    return installations.windows ?? installations.wsl ?? null;
  }

  // Check stored preference
  const storedPref = loadVSCodePreference();
  if (storedPref === 'wsl' && installations.wsl) {
    return installations.wsl;
  }
  if (storedPref === 'windows' && installations.windows) {
    return installations.windows;
  }

  // Default: prefer Windows if available, otherwise WSL
  return installations.windows ?? installations.wsl ?? null;
}

/**
 * Load VS Code preference from disk
 */
function loadVSCodePreference(): VSCodePreference {
  try {
    const prefPath = getPreferencePath();
    if (existsSync(prefPath)) {
      const data = JSON.parse(readFileSync(prefPath, 'utf8'));
      if (data.preference === 'windows' || data.preference === 'wsl') {
        return data.preference;
      }
    }
  } catch {
    // Ignore errors, return null
  }
  return null;
}

/**
 * Save VS Code preference to disk
 */
function saveVSCodePreference(preference: VSCodePreference): void {
  const prefPath = getPreferencePath();
  const dir = dirname(prefPath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  writeFileSync(prefPath, JSON.stringify({ preference }), 'utf8');
}

/**
 * Registers VS Code IPC handlers
 */
export function registerVSCodeHandlers(): void {
  // Launch VS Code with SSH remote connection
  ipcMain.handle(
    'vscode:launch',
    async (_event, options: VSCodeLaunchOptions): Promise<VSCodeLaunchResult> => {
      try {
        // Find VS Code installation based on preference
        const vscodeInfo = await getVSCodeForLaunch(options.preferredType);
        if (!vscodeInfo) {
          return {
            success: false,
            error:
              'VS Code not found. Please install Visual Studio Code or set REDIACC_VSCODE_PATH environment variable.',
          };
        }

        // Generate connection name
        const connectionName = generateConnectionName(
          options.teamName,
          options.machineName,
          options.repositoryName
        );

        // Persist SSH key (writes to ~/.ssh/rediacc_keys/)
        let keyPath = persistSSHKey(
          options.teamName,
          options.machineName,
          options.repositoryName,
          options.privateKey
        );

        // Persist known hosts (writes to ~/.ssh/rediacc_keys/)
        let knownHostsPath = '/dev/null';
        if (options.known_hosts) {
          knownHostsPath = persistKnownHosts(
            options.teamName,
            options.machineName,
            options.known_hosts
          );
        }

        // If using WSL VS Code, convert Windows paths to WSL paths
        if (vscodeInfo.isWSL) {
          keyPath = windowsPathToWSL(keyPath);
          if (knownHostsPath !== '/dev/null') {
            knownHostsPath = windowsPathToWSL(knownHostsPath);
          }
        }

        // Build SSH config entry
        const entry: SSHConfigEntry = {
          host: connectionName,
          hostname: options.host,
          user: options.user,
          port: options.port ?? DEFAULTS.SSH.PORT,
          identityFile: keyPath,
          userKnownHostsFile: knownHostsPath,
          serverAliveInterval: 60,
          serverAliveCountMax: 3,
        };

        // Add to SSH config (writes to ~/.ssh/config_rediacc)
        addSSHConfigEntry(entry);

        // Generate remote URI and launch
        const remoteUri = generateRemoteUri(connectionName, options.remotePath);
        await launchVSCode(vscodeInfo, remoteUri, {
          newWindow: options.newWindow,
        });

        return {
          success: true,
          connectionName,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error launching VS Code';
        console.error('Failed to launch VS Code:', error);
        return {
          success: false,
          error: message,
        };
      }
    }
  );

  // Check if VS Code is available
  ipcMain.handle('vscode:isAvailable', async (): Promise<boolean> => {
    const vscodeInfo = await findVSCode();
    return vscodeInfo !== null;
  });

  // Check if Remote SSH extension is installed (always return true for now)
  ipcMain.handle('vscode:hasRemoteSSH', (): boolean => {
    // VS Code will prompt for extension installation if needed
    return true;
  });

  // Get all available VS Code installations
  ipcMain.handle('vscode:getInstallations', (): Promise<VSCodeInstallations> => {
    return findAllVSCodeInstallations();
  });

  // Get stored VS Code preference
  ipcMain.handle('vscode:getPreference', (): VSCodePreference => {
    return loadVSCodePreference();
  });

  // Set VS Code preference
  ipcMain.handle('vscode:setPreference', (_event, preference: VSCodePreference): void => {
    saveVSCodePreference(preference);
  });
}
