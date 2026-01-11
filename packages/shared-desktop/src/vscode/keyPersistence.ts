/**
 * SSH Key Persistence for VS Code Remote SSH
 * Persists SSH keys for long-running VS Code sessions
 */

import { existsSync, writeFileSync, unlinkSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { getPlatform } from '../utils/platform.js';
import type { KeyPersistencePaths } from './types.js';

/**
 * Normalizes a path for SSH config usage
 * Converts Windows backslashes to forward slashes
 */
function normalizePathForSSH(path: string): string {
  if (getPlatform() === 'windows') {
    return path.replaceAll('\\', '/');
  }
  return path;
}

/**
 * Gets the directory for persisted rediacc keys
 */
function getKeysDirectory(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';
  return join(home, '.ssh', 'rediacc_keys');
}

/**
 * Generates a key name from connection info
 */
function generateKeyName(team: string, machine: string, repository?: string): string {
  const sanitize = (s: string) => s.replaceAll(/[^a-zA-Z0-9_-]/g, '_');

  if (repository) {
    return `${sanitize(team)}_${sanitize(machine)}_${sanitize(repository)}`;
  }
  return `${sanitize(team)}_${sanitize(machine)}`;
}

/**
 * Persists an SSH private key for VS Code usage
 *
 * @param teamName - Team name
 * @param machineName - Machine name
 * @param repositoryName - Optional repository name
 * @param privateKey - SSH private key content
 * @returns Path to the persisted key file
 */
export function persistSSHKey(
  teamName: string,
  machineName: string,
  repositoryName: string | undefined,
  privateKey: string
): string {
  const keysDir = getKeysDirectory();
  const keyName = generateKeyName(teamName, machineName, repositoryName);
  const keyPath = join(keysDir, keyName);

  // Ensure directory exists with proper permissions
  if (!existsSync(keysDir)) {
    mkdirSync(keysDir, { recursive: true, mode: 0o700 });
  }

  // Write key with proper permissions
  writeFileSync(keyPath, privateKey, { mode: 0o600 });

  // Return normalized path for SSH config compatibility on Windows
  return normalizePathForSSH(keyPath);
}

/**
 * Persists a known hosts file for VS Code usage
 *
 * @param teamName - Team name
 * @param machineName - Machine name
 * @param known_hosts - Host key entry
 * @returns Path to the persisted known hosts file
 */
export function persistKnownHosts(
  teamName: string,
  machineName: string,
  known_hosts: string
): string {
  const keysDir = getKeysDirectory();
  const sanitize = (s: string) => s.replaceAll(/[^a-zA-Z0-9_-]/g, '_');
  const hostsName = `${sanitize(teamName)}_${sanitize(machineName)}_known_hosts`;
  const hostsPath = join(keysDir, hostsName);

  // Ensure directory exists
  if (!existsSync(keysDir)) {
    mkdirSync(keysDir, { recursive: true, mode: 0o700 });
  }

  // Write known hosts
  writeFileSync(hostsPath, `${known_hosts}\n`, { mode: 0o644 });

  // Return normalized path for SSH config compatibility on Windows
  return normalizePathForSSH(hostsPath);
}

/**
 * Gets paths for persisted key files
 *
 * @param teamName - Team name
 * @param machineName - Machine name
 * @param repositoryName - Optional repository name
 * @returns Paths object or null if not persisted
 */
export function getPersistedKeyPaths(
  teamName: string,
  machineName: string,
  repositoryName?: string
): KeyPersistencePaths | null {
  const keysDir = getKeysDirectory();
  const keyName = generateKeyName(teamName, machineName, repositoryName);
  const keyPath = join(keysDir, keyName);

  const sanitize = (s: string) => s.replaceAll(/[^a-zA-Z0-9_-]/g, '_');
  const hostsName = `${sanitize(teamName)}_${sanitize(machineName)}_known_hosts`;
  const hostsPath = join(keysDir, hostsName);

  if (existsSync(keyPath) && existsSync(hostsPath)) {
    // Return normalized paths for SSH config compatibility on Windows
    return {
      keyPath: normalizePathForSSH(keyPath),
      knownHostsPath: normalizePathForSSH(hostsPath),
    };
  }

  return null;
}

/**
 * Removes persisted keys for a connection
 *
 * @param teamName - Team name
 * @param machineName - Machine name
 * @param repositoryName - Optional repository name
 */
export function removePersistedKeys(
  teamName: string,
  machineName: string,
  repositoryName?: string
): void {
  const keysDir = getKeysDirectory();
  const keyName = generateKeyName(teamName, machineName, repositoryName);
  const keyPath = join(keysDir, keyName);

  const sanitize = (s: string) => s.replaceAll(/[^a-zA-Z0-9_-]/g, '_');
  const hostsName = `${sanitize(teamName)}_${sanitize(machineName)}_known_hosts`;
  const hostsPath = join(keysDir, hostsName);

  try {
    if (existsSync(keyPath)) {
      unlinkSync(keyPath);
    }
    if (existsSync(hostsPath)) {
      unlinkSync(hostsPath);
    }
  } catch {
    // Ignore cleanup errors
  }
}

/**
 * Lists all persisted key connections
 *
 * @returns Array of key file names
 */
export function listPersistedKeys(): string[] {
  const keysDir = getKeysDirectory();

  if (!existsSync(keysDir)) {
    return [];
  }

  try {
    return readdirSync(keysDir).filter((f) => !f.endsWith('_known_hosts'));
  } catch {
    return [];
  }
}

/**
 * Cleans up all persisted rediacc keys
 */
export function cleanupAllPersistedKeys(): void {
  const keysDir = getKeysDirectory();

  if (!existsSync(keysDir)) {
    return;
  }

  try {
    const files = readdirSync(keysDir);
    for (const file of files) {
      try {
        unlinkSync(join(keysDir, file));
      } catch {
        // Ignore individual file errors
      }
    }
  } catch {
    // Ignore directory errors
  }
}
