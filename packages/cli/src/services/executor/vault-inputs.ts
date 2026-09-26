/**
 * The config-side inputs `buildLocalVault` needs besides the machine itself:
 * known hosts, storages, and every repository's credential and vault entry.
 */

import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import type { RepositoryConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';

export function resolveKnownHosts(machineKnownHosts: string | undefined): Promise<string> {
  const hosts = machineKnownHosts ?? '';
  if (hosts) return Promise.resolve(hosts);
  const knownHostsPath = path.join(os.homedir(), '.ssh', 'known_hosts');
  return fs.readFile(knownHostsPath, 'utf-8').catch(() => '');
}

export async function loadContextStorages(): Promise<
  Record<string, { vaultContent: Record<string, unknown> }> | undefined
> {
  try {
    const storageList = await configService.listStorages();
    if (storageList.length === 0) return undefined;
    const storages: Record<string, { vaultContent: Record<string, unknown> }> = {};
    for (const s of storageList) {
      storages[s.name] = { vaultContent: s.config.vaultContent };
    }
    return storages;
  } catch {
    return undefined;
  }
}

interface LoadedRepoEntry {
  guid: string;
  name: string;
  networkId?: number;
  secretFiles?: { name: string; value: string }[];
}

/**
 * Build a single LoadedRepoEntry. Extracts file-mode secrets only;
 * env-mode rides the shell prefix (resolveEnvSecrets), not the vault.
 */
function buildLoadedRepoEntry(name: string, config: RepositoryConfig): LoadedRepoEntry {
  const secretFiles: { name: string; value: string }[] = [];
  for (const [secretName, entry] of Object.entries(config.secrets ?? {})) {
    if (entry.mode === 'file') secretFiles.push({ name: secretName, value: entry.value });
  }
  return {
    guid: config.repositoryGuid,
    name,
    networkId: config.networkId,
    ...(secretFiles.length > 0 ? { secretFiles } : {}),
  };
}

/**
 * Alias each family's bare name to its GRAND so lookups by bare name work,
 * whatever tag the grand is stored under (getRepositoryKey follows the
 * family's grand pointer rather than assuming `:latest`).
 */
async function aliasBareNamesToGrands(configs: Record<string, LoadedRepoEntry>): Promise<void> {
  for (const base of new Set(Object.keys(configs).map((key) => key.split(':')[0]))) {
    if (base in configs) continue;
    const grandKey = await configService.getRepositoryKey(base);
    if (grandKey && grandKey in configs) configs[base] = configs[grandKey];
  }
}

export async function loadContextRepositories(): Promise<{
  credentials: Record<string, string> | undefined;
  configs: Record<string, LoadedRepoEntry> | undefined;
}> {
  try {
    const repoList = await configService.listRepositories();
    if (repoList.length === 0) return { credentials: undefined, configs: undefined };
    const credentials: Record<string, string> = {};
    const configs: Record<string, LoadedRepoEntry> = {};
    for (const r of repoList) {
      if (r.config.credential) {
        credentials[r.config.repositoryGuid] = r.config.credential;
      }
      configs[r.name] = buildLoadedRepoEntry(r.name, r.config);
    }
    await aliasBareNamesToGrands(configs);
    return { credentials, configs };
  } catch {
    return { credentials: undefined, configs: undefined };
  }
}
