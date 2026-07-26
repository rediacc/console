/**
 * ResourceState interface and implementations.
 *
 * ResourceState abstracts access to machines, storages, repositories, and SSH
 * keys. It presents repositories as a FLAT map keyed by the legacy composite
 * `name` / `name:tag` string, with the on-disk v3 spec record (RepoRecord under
 * `resources.repositories[name].tags[tag]`) merged with its runtime status
 * (`state.repos[name][tag]`). Command consumers therefore compile unchanged;
 * the structural-tag command reshape is P4.
 *
 * Encryption-at-rest is NOT handled here in v3 — it is a storage-layer transform
 * (adapters/config-field-crypto.ts, applied by ConfigFileStorage). LocalResource
 * State is a typed view that reads a decrypted config and persists plaintext
 * through the single `configFileStorage.update()` chokepoint, which re-encrypts
 * per field. This is what makes the R2-F3 compound-blob data-loss impossible.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { Placement, RdcConfig, RepoFamily, RepoRecord } from '@rediacc/shared/config-schema';
import { stripStateForPush } from '../../adapters/config-field-crypto.js';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import {
  type RemoteConfigAdapter,
  RemoteUnreachableError,
  RemoteVersionConflictError,
} from '../../adapters/remote-config-adapter.js';
import { t } from '../../i18n/index.js';
import type {
  ArchivedRepository,
  MachineConfig,
  RepositoryConfig,
  SSHContent,
  StorageConfig,
} from '../../types/index.js';
import { mergeRemoteIntoCache } from './remote-cache.js';

// =============================================================================
// Flatten / decompose: v3 families + state.repos  <->  flat composite view
// =============================================================================

type RepoRuntime = NonNullable<NonNullable<RdcConfig['state']>['repos']>[string][string];

const REPO_RECORD_KEYS = [
  'repositoryGuid',
  'credential',
  'grandGuid',
  'parentGuid',
  'immutable',
  'sshPrivateKey',
  'sshPublicKey',
  'secrets',
] as const;

const REPO_RUNTIME_KEYS = [
  'networkId',
  'registryPort',
  'pushState',
  'headCommit',
  'commitMessage',
  'commitAuthor',
  'commitParent',
  'head',
  'branches',
  'reflog',
] as const;

function splitKey(key: string): { base: string; tag?: string } {
  const idx = key.indexOf(':');
  if (idx === -1) return { base: key };
  return { base: key.slice(0, idx), tag: key.slice(idx + 1) };
}

function pickKeys<T extends object>(source: Record<string, unknown>, keys: readonly string[]): T {
  const out: Record<string, unknown> = {};
  for (const k of keys) {
    if (source[k] !== undefined) out[k] = source[k];
  }
  return out as T;
}

/** Build the flat `Record<'base:tag', RepositoryConfig>` view from the config. */
function flattenRepositories(
  families: Record<string, RepoFamily> | undefined,
  stateRepos: Record<string, Record<string, RepoRuntime>> | undefined
): Record<string, RepositoryConfig> {
  const flat: Record<string, RepositoryConfig> = {};
  for (const [base, family] of Object.entries(families ?? {})) {
    for (const [tag, record] of Object.entries(family.tags)) {
      const key = `${base}:${tag}`;
      const runtime = stateRepos?.[base]?.[tag] ?? {};
      flat[key] = {
        ...record,
        tag,
        ...(family.placement ? { placement: family.placement } : {}),
        ...runtime,
      };
    }
  }
  return flat;
}

/** Which tag is the production (grand) line: grandGuid unset or self-referential. */
function deriveGrand(tags: Record<string, RepoRecord>): string {
  const keys = Object.keys(tags).sort();
  const grands = keys.filter((t) => {
    const g = tags[t].grandGuid;
    return !g || g === tags[t].repositoryGuid;
  });
  if (grands.includes('latest')) return 'latest';
  return grands[0] ?? keys[0];
}

interface FamilyGroup {
  tags: Record<string, RepoRecord>;
  runtime: Record<string, RepoRuntime>;
  placement?: Placement;
}

/** Group flat composite-keyed records by base name into (tags, runtime). */
function groupFlatRepos(flat: Record<string, RepositoryConfig>): Map<string, FamilyGroup> {
  const grouped = new Map<string, FamilyGroup>();
  for (const [key, cfg] of Object.entries(flat)) {
    const { base, tag: keyTag } = splitKey(key);
    const tag = cfg.tag ?? keyTag ?? DEFAULTS.REPOSITORY.TAG;
    const group = grouped.get(base) ?? { tags: {}, runtime: {} };
    group.tags[tag] = pickKeys<RepoRecord>(cfg, REPO_RECORD_KEYS);
    const runtime = pickKeys<RepoRuntime>(cfg, REPO_RUNTIME_KEYS);
    if (Object.keys(runtime).length > 0) group.runtime[tag] = runtime;
    if (cfg.placement && !group.placement) group.placement = cfg.placement;
    grouped.set(base, group);
  }
  return grouped;
}

/** Decompose the flat view back into v3 families + state.repos. */
function decomposeRepositories(flat: Record<string, RepositoryConfig>): {
  families: Record<string, RepoFamily>;
  stateRepos: Record<string, Record<string, RepoRuntime>>;
} {
  const grouped = groupFlatRepos(flat);
  const families: Record<string, RepoFamily> = {};
  const stateRepos: Record<string, Record<string, RepoRuntime>> = {};
  for (const [base, group] of grouped) {
    families[base] = {
      grand: deriveGrand(group.tags),
      tags: group.tags,
      ...(group.placement ? { placement: group.placement } : {}),
    };
    if (Object.keys(group.runtime).length > 0) stateRepos[base] = group.runtime;
  }
  return { families, stateRepos };
}

function sshContentFrom(config: RdcConfig): SSHContent | null {
  const sshCred = config.credentials?.ssh;
  return sshCred
    ? {
        privateKey: sshCred.privateKey,
        publicKey: sshCred.publicKey,
        knownHosts: sshCred.knownHosts,
      }
    : null;
}

function nonEmpty<T extends object>(rec: T): T | undefined {
  return Object.keys(rec).length > 0 ? rec : undefined;
}

// =============================================================================
// ResourceState Interface
// =============================================================================

export interface ResourceState {
  getMachines(): Record<string, MachineConfig>;
  setMachines(machines: Record<string, MachineConfig>): Promise<void>;
  getStorages(): Record<string, StorageConfig>;
  setStorages(storages: Record<string, StorageConfig>): Promise<void>;
  getRepositories(): Record<string, RepositoryConfig>;
  setRepositories(repos: Record<string, RepositoryConfig>): Promise<void>;
  getDeletedRepositories(): ArchivedRepository[];
  setDeletedRepositories(repos: ArchivedRepository[]): Promise<void>;
  getSSH(): SSHContent | null;
  setSSH(ssh: SSHContent): Promise<void>;
}

interface LocalState {
  machines: Record<string, MachineConfig>;
  storages: Record<string, StorageConfig>;
  repositories: Record<string, RepositoryConfig>;
  deletedRepositories: ArchivedRepository[];
  sshContent: SSHContent | null;
}

function loadLocalState(config: RdcConfig): LocalState {
  return {
    machines: config.resources?.machines ?? {},
    storages: config.resources?.storages ?? {},
    repositories: flattenRepositories(config.resources?.repositories, config.state?.repos),
    deletedRepositories: config.resources?.deletedRepositories ?? [],
    sshContent: sshContentFrom(config),
  };
}

/** Build the resources/credentials/state buckets a persist writes, from state. */
function persistPatch(state: LocalState, cfg: RdcConfig): RdcConfig {
  const { families, stateRepos } = decomposeRepositories(state.repositories);
  const sshContent = state.sshContent;
  return {
    ...cfg,
    resources: {
      ...(cfg.resources ?? {}),
      machines: nonEmpty(state.machines),
      storages: nonEmpty(state.storages),
      repositories: nonEmpty(families),
      deletedRepositories:
        state.deletedRepositories.length > 0 ? state.deletedRepositories : undefined,
    },
    credentials: {
      ...(cfg.credentials ?? {}),
      ssh: sshContent
        ? {
            privateKey: sshContent.privateKey,
            publicKey: sshContent.publicKey,
            knownHosts: sshContent.knownHosts,
          }
        : undefined,
    },
    state: {
      ...(cfg.state ?? {}),
      repos: nonEmpty(stateRepos),
    },
  };
}

// =============================================================================
// LocalResourceState
// =============================================================================

export class LocalResourceState implements ResourceState {
  private readonly configName: string;
  private readonly state: LocalState;

  private constructor(configName: string, state: LocalState) {
    this.configName = configName;
    this.state = state;
  }

  /**
   * @param config a DECRYPTED config (encrypted leaves already materialized).
   *   Config-base resolves the master password and hands us plaintext; we never
   *   touch ciphertext ourselves.
   */
  static load(config: RdcConfig, configName: string): LocalResourceState {
    return new LocalResourceState(configName, loadLocalState(config));
  }

  getMachines(): Record<string, MachineConfig> {
    return this.state.machines;
  }

  getStorages(): Record<string, StorageConfig> {
    return this.state.storages;
  }

  getRepositories(): Record<string, RepositoryConfig> {
    return this.state.repositories;
  }

  getDeletedRepositories(): ArchivedRepository[] {
    return this.state.deletedRepositories;
  }

  getSSH(): SSHContent | null {
    return this.state.sshContent;
  }

  async setMachines(machines: Record<string, MachineConfig>): Promise<void> {
    this.state.machines = machines;
    await this.persist();
  }

  async setStorages(storages: Record<string, StorageConfig>): Promise<void> {
    this.state.storages = storages;
    await this.persist();
  }

  async setRepositories(repos: Record<string, RepositoryConfig>): Promise<void> {
    this.state.repositories = repos;
    await this.persist();
  }

  async setDeletedRepositories(repos: ArchivedRepository[]): Promise<void> {
    this.state.deletedRepositories = repos;
    await this.persist();
  }

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.sshContent = ssh;
    await this.persist();
  }

  /**
   * Single persist path (R2-F3). Writes the whole state view through
   * `configFileStorage.update`, spreading the loaded config so sibling buckets
   * (clusters, cloudProviders, backupStrategies, datastores, and other
   * `state.*`) survive untouched. The storage layer re-encrypts per field.
   */
  private async persist(): Promise<void> {
    await configFileStorage.update(this.configName, (cfg) => persistPatch(this.state, cfg));
  }
}

// =============================================================================
// RemoteResourceState
// =============================================================================

/** Bounded 409-replay attempts before surfacing the conflict to the user. */
const REMOTE_PUSH_MAX_ATTEMPTS = 3;

/**
 * ResourceState backed by the remote encrypted config store. Mutations push the
 * REAL on-disk config with `state` stripped (spec 04 §1.3) — never a
 * reconstructed subset, so no bucket can be dropped.
 *
 * Writes fail CLOSED when the server is unreachable (no local write, no queue
 * — a queued write would silently diverge from the server), and replay a 409
 * up to 3 times by re-pulling and re-applying ONLY the mutated bucket
 * (bucket-level last-write-wins; cross-bucket concurrent writes survive).
 */
export class RemoteResourceState implements ResourceState {
  private readonly adapter: RemoteConfigAdapter;
  private readonly configName: string;
  private version: number;
  private state: LocalState;

  private constructor(
    adapter: RemoteConfigAdapter,
    configName: string,
    version: number,
    state: LocalState
  ) {
    this.adapter = adapter;
    this.configName = configName;
    this.version = version;
    this.state = state;
  }

  static load(
    config: RdcConfig,
    configName: string,
    adapter: RemoteConfigAdapter,
    version: number,
    _sdkEpoch: number
  ): RemoteResourceState {
    return new RemoteResourceState(adapter, configName, version, loadLocalState(config));
  }

  getMachines(): Record<string, MachineConfig> {
    return this.state.machines;
  }

  getStorages(): Record<string, StorageConfig> {
    return this.state.storages;
  }

  getRepositories(): Record<string, RepositoryConfig> {
    return this.state.repositories;
  }

  getDeletedRepositories(): ArchivedRepository[] {
    return this.state.deletedRepositories;
  }

  getSSH(): SSHContent | null {
    return this.state.sshContent;
  }

  async setMachines(machines: Record<string, MachineConfig>): Promise<void> {
    this.state.machines = machines;
    await this.persist('machines');
  }

  async setStorages(storages: Record<string, StorageConfig>): Promise<void> {
    this.state.storages = storages;
    await this.persist('storages');
  }

  async setRepositories(repos: Record<string, RepositoryConfig>): Promise<void> {
    this.state.repositories = repos;
    await this.persist('repositories');
  }

  async setDeletedRepositories(repos: ArchivedRepository[]): Promise<void> {
    this.state.deletedRepositories = repos;
    await this.persist('deletedRepositories');
  }

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.sshContent = ssh;
    await this.persist('sshContent');
  }

  /**
   * Push the mutation, replaying version conflicts per the class doc. On
   * success the on-disk offline cache follows the push (merged carries the
   * updated `state`, so the runtime half is preserved locally even though the
   * push strips it).
   */
  private async persist(mutated: keyof LocalState): Promise<void> {
    let conflict: Error | null = null;
    for (let attempt = 1; attempt <= REMOTE_PUSH_MAX_ATTEMPTS; attempt++) {
      const result = await this.pushOnce();
      if (result === null) return;
      conflict = result;
      if (attempt < REMOTE_PUSH_MAX_ATTEMPTS) await this.rebaseOnFreshPull(mutated);
    }
    throw new Error(
      t('commands.config.remote.conflictRetryExhausted', { config: this.configName }),
      { cause: conflict }
    );
  }

  /**
   * One push attempt from the current on-disk config + in-memory view. On
   * success writes the cache and returns null; a version conflict is RETURNED
   * (not thrown) so the replay loop stays flat; anything else is thrown, with
   * unreachable servers converted to the fail-closed error.
   */
  private async pushOnce(): Promise<RemoteVersionConflictError | null> {
    const base = await configFileStorage.loadDecrypted(this.configName);
    const merged = persistPatch(this.state, base);
    const pushDoc = stripStateForPush(merged);
    try {
      const result = await this.adapter.push(pushDoc, this.version);
      this.version = result.version;
      await configFileStorage.updateCache(this.configName, () =>
        mergeRemoteIntoCache(merged, pushDoc, result.version)
      );
      return null;
    } catch (error) {
      if (error instanceof RemoteVersionConflictError) return error;
      throw this.toWriteError(error);
    }
  }

  /**
   * Another device pushed since our snapshot: re-pull, rebuild the view from
   * the fresh config, and re-apply ONLY this mutation's bucket. An unreachable
   * server during the re-pull fails closed the same way as the push.
   */
  private async rebaseOnFreshPull(mutated: keyof LocalState): Promise<void> {
    let fresh: Awaited<ReturnType<RemoteConfigAdapter['pull']>>;
    try {
      fresh = await this.adapter.pull();
    } catch (error) {
      throw this.toWriteError(error);
    }
    this.state = { ...loadLocalState(fresh.config), [mutated]: this.state[mutated] };
    this.version = fresh.version;
  }

  /** Convert an unreachable-server error into the fail-closed user error. */
  private toWriteError(error: unknown): unknown {
    if (error instanceof RemoteUnreachableError) {
      return new Error(
        t('commands.config.remote.writeFailedClosed', {
          config: this.configName,
          server: error.apiUrl,
        }),
        { cause: error }
      );
    }
    return error;
  }
}
