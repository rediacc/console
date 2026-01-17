/**
 * SSH Config Management for VS Code Remote SSH
 * Ported from desktop/src/cli/core/vscode_shared.py
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  buildMachineEnvironment,
  buildRemoteCommand,
  buildRepositoryEnvironment,
} from './envCompose.js';
import { getPlatform } from '../utils/platform.js';
import type { SSHConfigEntry } from './types.js';

/**
 * Normalizes a path for SSH config usage
 * Converts Windows backslashes to forward slashes
 */
function normalizePathForSSH(path: string): string {
  const platform = getPlatform();
  if (platform === 'windows') {
    return path.replaceAll('\\', '/');
  }
  return path;
}

/**
 * Default SSH config file path for rediacc connections
 */
export function getSSHConfigPath(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';
  const sshPath = join(home, '.ssh', 'config_rediacc');
  // Normalize for Windows - SSH expects forward slashes
  return normalizePathForSSH(sshPath);
}

/**
 * Generates a unique connection name for VS Code
 *
 * @param team - Team name
 * @param machine - Machine name
 * @param repository - Optional repository name
 * @returns Sanitized connection name
 */
export function generateConnectionName(team: string, machine: string, repository?: string): string {
  // Sanitize names for SSH config host
  const sanitize = (s: string) => s.replaceAll(/[^a-zA-Z0-9_-]/g, '-');

  if (repository) {
    return `rediacc-${sanitize(team)}-${sanitize(machine)}-${sanitize(repository)}`;
  }
  return `rediacc-${sanitize(team)}-${sanitize(machine)}`;
}

/**
 * Formats an SSH config entry as a config block
 */
function formatConfigEntry(entry: SSHConfigEntry): string {
  const lines: string[] = [
    `Host ${entry.host}`,
    `  HostName ${entry.hostname}`,
    `  User ${entry.user}`,
    `  Port ${entry.port}`,
    `  IdentityFile ${entry.identityFile}`,
    `  UserKnownHostsFile ${entry.userKnownHostsFile}`,
    '  IdentitiesOnly yes',
    '  PasswordAuthentication no',
    '  PubkeyAuthentication yes',
  ];

  // SSH keepalive settings to prevent disconnection during long sessions
  const serverAliveInterval = entry.serverAliveInterval ?? DEFAULTS.SSH.SERVER_ALIVE_INTERVAL;
  const serverAliveCountMax = entry.serverAliveCountMax ?? DEFAULTS.SSH.SERVER_ALIVE_COUNT_MAX;
  lines.push(`  ServerAliveInterval ${serverAliveInterval}`);
  lines.push(`  ServerAliveCountMax ${serverAliveCountMax}`);

  if (entry.remoteCommand) {
    lines.push(`  RemoteCommand ${entry.remoteCommand}`);
  }

  if (entry.requestTTY) {
    lines.push(`  RequestTTY ${entry.requestTTY}`);
  }

  // SetEnv directives for environment variables
  // Quote values containing spaces (matching Python CLI behavior)
  if (entry.setEnv) {
    for (const [key, value] of Object.entries(entry.setEnv)) {
      // Quote the value if it contains spaces
      const quotedValue = value.includes(' ') ? `"${value}"` : value;
      lines.push(`  SetEnv ${key}=${quotedValue}`);
    }
  }

  return lines.join('\n');
}

/**
 * Parses SSH config file into host blocks
 */
function parseSSHConfig(content: string): Map<string, string> {
  const hosts = new Map<string, string>();
  const lines = content.split('\n');
  let currentHost = '';
  let currentBlock: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (
      trimmed.toLowerCase().startsWith('host ') &&
      !trimmed.toLowerCase().startsWith('hostname')
    ) {
      // Save previous block
      if (currentHost) {
        hosts.set(currentHost, currentBlock.join('\n'));
      }
      // Start new block
      currentHost = trimmed.substring(5).trim().split(/\s+/)[0];
      currentBlock = [line];
    } else if (currentHost) {
      currentBlock.push(line);
    }
  }

  // Save last block
  if (currentHost) {
    hosts.set(currentHost, currentBlock.join('\n'));
  }

  return hosts;
}

/**
 * Adds or updates an SSH config entry
 *
 * @param entry - SSH config entry to add
 */
export function addSSHConfigEntry(entry: SSHConfigEntry): void {
  const configPath = getSSHConfigPath();
  const configDir = dirname(configPath);

  // Ensure directory exists
  if (!existsSync(configDir)) {
    mkdirSync(configDir, { recursive: true, mode: 0o700 });
  }

  let existingContent = '';
  if (existsSync(configPath)) {
    existingContent = readFileSync(configPath, 'utf8');
  }

  // Parse existing config
  const hosts = parseSSHConfig(existingContent);

  // Add/update entry
  hosts.set(entry.host, formatConfigEntry(entry));

  // Write back
  const newContent = `${Array.from(hosts.values()).join('\n\n')}\n`;
  writeFileSync(configPath, newContent, { mode: 0o600 });
}

/**
 * Removes an SSH config entry by host name
 *
 * @param host - Host name to remove
 */
export function removeSSHConfigEntry(host: string): void {
  const configPath = getSSHConfigPath();

  if (!existsSync(configPath)) {
    return;
  }

  const content = readFileSync(configPath, 'utf8');
  const hosts = parseSSHConfig(content);

  if (hosts.has(host)) {
    hosts.delete(host);
    const newContent = `${Array.from(hosts.values()).join('\n\n')}\n`;
    writeFileSync(configPath, newContent, { mode: 0o600 });
  }
}

/**
 * Gets an SSH config entry by host name
 *
 * @param host - Host name to find
 * @returns Entry content or null if not found
 */
export function getSSHConfigEntry(host: string): string | null {
  const configPath = getSSHConfigPath();

  if (!existsSync(configPath)) {
    return null;
  }

  const content = readFileSync(configPath, 'utf8');
  const hosts = parseSSHConfig(content);

  return hosts.get(host) ?? null;
}

/**
 * Lists all rediacc SSH config entries
 *
 * @returns Array of host names
 */
export function listSSHConfigEntries(): string[] {
  const configPath = getSSHConfigPath();

  if (!existsSync(configPath)) {
    return [];
  }

  const content = readFileSync(configPath, 'utf8');
  const hosts = parseSSHConfig(content);

  return Array.from(hosts.keys()).filter((h) => h.startsWith('rediacc-'));
}

/**
 * Options for building a VS Code SSH config entry
 */
export interface BuildSSHConfigOptions {
  /** Team name */
  teamName: string;
  /** Machine name */
  machineName: string;
  /** Repository name (optional - for repository connections) */
  repositoryName?: string;
  /** SSH host IP or hostname */
  host: string;
  /** SSH port */
  port: number;
  /** SSH user */
  sshUser: string;
  /** Path to identity file */
  identityFile: string;
  /** Path to known hosts file */
  knownHostsFile: string;
  /** Datastore path on remote machine */
  datastore: string;
  /** Repository path within datastore (e.g., /home/myrepo) */
  repositoryPath?: string;
  /** Universal user for switching (if different from sshUser) */
  universalUser?: string;
  /** Network ID */
  networkId?: string;
  /** Additional environment variables */
  additionalEnv?: Record<string, string>;
  /** SSH keepalive interval in seconds (default: 60) */
  serverAliveInterval?: number;
  /** Max missed keepalives before disconnect (default: 3) */
  serverAliveCountMax?: number;
}

/**
 * Builds a complete SSH config entry with environment variables and user switching
 * Matches Python CLI's VS Code SSH config generation behavior
 *
 * @param options - Build options
 * @returns SSHConfigEntry ready to be added to config
 */
export function buildVSCodeSSHConfigEntry(options: BuildSSHConfigOptions): SSHConfigEntry {
  const {
    teamName,
    machineName,
    repositoryName,
    host,
    port,
    sshUser,
    identityFile,
    knownHostsFile,
    datastore,
    repositoryPath,
    universalUser,
    networkId,
    additionalEnv,
    serverAliveInterval,
    serverAliveCountMax,
  } = options;

  // Generate connection name
  const connectionHost = generateConnectionName(teamName, machineName, repositoryName);

  // Build environment variables
  let envVars: Record<string, string>;
  if (repositoryName && repositoryPath) {
    envVars = buildRepositoryEnvironment({
      teamName,
      machineName,
      repositoryName,
      datastore,
      repositoryPath,
      universalUser: universalUser ?? sshUser,
      networkId,
      additionalEnv,
    });
  } else {
    envVars = buildMachineEnvironment({
      teamName,
      machineName,
      datastore,
      universalUser: universalUser ?? sshUser,
    });
  }

  // Build RemoteCommand for user switching
  const { remoteCommand, requestTTY } = buildRemoteCommand(sshUser, universalUser);

  const entry: SSHConfigEntry = {
    host: connectionHost,
    hostname: host,
    user: sshUser,
    port,
    identityFile,
    userKnownHostsFile: knownHostsFile,
    setEnv: envVars,
    serverAliveInterval,
    serverAliveCountMax,
  };

  // Add RemoteCommand if user switching is needed
  if (remoteCommand) {
    entry.remoteCommand = remoteCommand;
    entry.requestTTY = requestTTY as 'yes' | 'no' | 'force';
  }

  return entry;
}
