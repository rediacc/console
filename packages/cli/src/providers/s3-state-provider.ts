/**
 * S3StateProvider - stores state as JSON files in an S3/R2 bucket.
 * Execution still happens locally via renet subprocess (same as local mode).
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { authService } from '../services/auth.js';
import { S3ClientService } from '../services/s3-client.js';
import { S3QueueService, type S3QueueItem } from '../services/s3-queue.js';
import { S3VaultService } from '../services/s3-vault.js';
import type {
  IStateProvider,
  MachineProvider,
  MachineWithVaultStatusData,
  MutationResult,
  QueueProvider,
  RepositoryProvider,
  ResourceRecord,
  StorageProvider,
  VaultData,
  VaultItem,
  VaultProvider,
} from './types.js';
import type { NamedContext } from '../types/index.js';

interface MachineRecord {
  machineName: string;
  ip?: string;
  user?: string;
  port?: number;
  datastore?: string;
  bridgeName?: string;
  vaultContent?: string;
  createdAt: string;
  updatedAt: string;
}

interface StorageRecord {
  storageName: string;
  teamName: string;
  vaultContent?: string;
  createdAt: string;
  updatedAt: string;
}

interface RepositoryRecord {
  repositoryName: string;
  repositoryTag?: string;
  teamName: string;
  vaultContent?: string;
  createdAt: string;
  updatedAt: string;
}

class S3MachineProvider implements MachineProvider {
  constructor(
    private readonly s3: S3ClientService,
    private readonly vaultService: S3VaultService
  ) {}

  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const keys = await this.s3.listKeys('machines/');
    const machines: ResourceRecord[] = [];
    for (const key of keys) {
      if (!key.endsWith('.json')) continue;
      const data = await this.s3.getJson<MachineRecord>(key);
      if (data) machines.push(data as unknown as ResourceRecord);
    }
    return machines;
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.machineName as string;
    const now = new Date().toISOString();
    const record: MachineRecord = {
      machineName: name,
      ip: params.ip as string | undefined,
      user: params.user as string | undefined,
      port: params.port as number | undefined,
      datastore: params.datastore as string | undefined,
      bridgeName: params.bridgeName as string | undefined,
      vaultContent: params.vaultContent as string | undefined,
      createdAt: now,
      updatedAt: now,
    };
    await this.s3.putJson(`machines/${name}.json`, record);
    return { success: true };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    const oldName = (params.currentMachineName ?? params.oldMachineName) as string;
    const newName = (params.newMachineName ?? params.newName) as string;
    const existing = await this.s3.getJson<MachineRecord>(`machines/${oldName}.json`);
    if (!existing) return { success: false, message: `Machine "${oldName}" not found` };

    existing.machineName = newName;
    existing.updatedAt = new Date().toISOString();
    await this.s3.putJson(`machines/${newName}.json`, existing);
    await this.s3.deleteObject(`machines/${oldName}.json`);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.machineName as string;
    await this.s3.deleteObject(`machines/${name}.json`);
    return { success: true };
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    // Return all vault-like data — for S3, machine vaults are stored encrypted
    const keys = await this.s3.listKeys('vaults/machines/');
    const vaults: VaultItem[] = [];
    for (const key of keys) {
      if (!key.endsWith('.json.enc')) continue;
      const machineName = key.replace('vaults/machines/', '').replace('.json.enc', '');
      const data = await this.vaultService.getMachineVault(machineName);
      if (data) {
        vaults.push({ vaultType: 'Machine', machineName, ...data });
      }
    }
    return vaults;
  }

  async updateVault(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.machineName as string;
    const content = params.vaultContent as string;
    const data = JSON.parse(content) as Record<string, unknown>;
    await this.vaultService.setMachineVault(name, data);
    return { success: true };
  }

  async getWithVaultStatus(params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null> {
    const data = await this.s3.getJson<MachineRecord>(`machines/${params.machineName}.json`);
    if (!data) return null;
    return {
      machineName: data.machineName,
      vaultStatus: null, // S3 mode does not yet store vaultStatus
      vaultContent: data.vaultContent ?? null,
    };
  }
}

class S3QueueProvider implements QueueProvider {
  constructor(private readonly queueService: S3QueueService) {}

  async list(params: { teamName: string; maxRecords?: number }): Promise<ResourceRecord[]> {
    const items = await this.queueService.list({ limit: params.maxRecords });
    return items as unknown as ResourceRecord[];
  }

  async create(params: Record<string, unknown>): Promise<{ taskId?: string }> {
    const taskId = await this.queueService.create({
      functionName: params.functionName as string,
      machineName: params.machineName as string | undefined,
      bridgeName: params.bridgeName as string | undefined,
      teamName: params.teamName as string,
      vaultContent: params.vaultContent as string,
      priority: (params.priority as number | undefined) ?? DEFAULTS.PRIORITY.QUEUE_PRIORITY,
      params: params.params as Record<string, unknown> | undefined,
    });
    return { taskId };
  }

  async trace(taskId: string): Promise<ResourceRecord | null> {
    const item = await this.queueService.trace(taskId);
    if (!item) return null;
    return this.toTraceFormat(item);
  }

  async cancel(taskId: string): Promise<void> {
    await this.queueService.cancel(taskId);
  }

  async retry(taskId: string): Promise<void> {
    await this.queueService.retry(taskId);
  }

  async delete(taskId: string): Promise<void> {
    await this.queueService.delete(taskId);
  }

  private toTraceFormat(item: S3QueueItem): ResourceRecord {
    const createdTime = item.createdAt ? new Date(item.createdAt).getTime() : undefined;
    const ageInMinutes = createdTime ? Math.floor((Date.now() - createdTime) / 60000) : undefined;

    return {
      summary: {
        taskId: item.taskId,
        status: item.status,
        progress: item.status === 'ACTIVE' ? 'In progress' : undefined,
        consoleOutput: item.consoleOutput,
        errorMessage: item.errorMessage,
        lastFailureReason: item.errorMessage,
        priority: item.priority,
        retryCount: item.retryCount,
        ageInMinutes,
        hasResponse: item.status === 'COMPLETED' || item.status === 'FAILED',
        teamName: item.teamName,
        machineName: item.machineName,
        bridgeName: item.bridgeName,
        createdTime: item.createdAt,
        updatedTime: item.updatedAt,
      },
      queueDetails: null,
    };
  }
}

class S3StorageProvider implements StorageProvider {
  constructor(
    private readonly s3: S3ClientService,
    private readonly vaultService: S3VaultService
  ) {}

  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const keys = await this.s3.listKeys('storages/');
    const items: ResourceRecord[] = [];
    for (const key of keys) {
      if (!key.endsWith('.json')) continue;
      const data = await this.s3.getJson<StorageRecord>(key);
      if (data) items.push(data as unknown as ResourceRecord);
    }
    return items;
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.storageName as string;
    const now = new Date().toISOString();
    const record: StorageRecord = {
      storageName: name,
      teamName: params.teamName as string,
      createdAt: now,
      updatedAt: now,
    };
    await this.s3.putJson(`storages/${name}.json`, record);
    return { success: true };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    const oldName = (params.currentStorageName ?? params.oldStorageName) as string;
    const newName = (params.newStorageName ?? params.newName) as string;
    const existing = await this.s3.getJson<StorageRecord>(`storages/${oldName}.json`);
    if (!existing) return { success: false, message: `Storage "${oldName}" not found` };

    existing.storageName = newName;
    existing.updatedAt = new Date().toISOString();
    await this.s3.putJson(`storages/${newName}.json`, existing);
    await this.s3.deleteObject(`storages/${oldName}.json`);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.storageName as string;
    await this.s3.deleteObject(`storages/${name}.json`);
    return { success: true };
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    // S3 mode doesn't have separate vault storage for storages; return empty
    return Promise.resolve([]);
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.resolve({ success: true });
  }
}

class S3RepositoryProvider implements RepositoryProvider {
  constructor(private readonly s3: S3ClientService) {}

  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const keys = await this.s3.listKeys('repositories/');
    const items: ResourceRecord[] = [];
    for (const key of keys) {
      if (!key.endsWith('.json')) continue;
      const data = await this.s3.getJson<RepositoryRecord>(key);
      if (data) items.push(data as unknown as ResourceRecord);
    }
    return items;
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.repositoryName as string;
    const now = new Date().toISOString();
    const record: RepositoryRecord = {
      repositoryName: name,
      repositoryTag: params.repositoryTag as string | undefined,
      teamName: params.teamName as string,
      createdAt: now,
      updatedAt: now,
    };
    await this.s3.putJson(`repositories/${name}.json`, record);
    return { success: true };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    const oldName = (params.currentRepositoryName ?? params.oldRepositoryName) as string;
    const newName = (params.newRepositoryName ?? params.newName) as string;
    const existing = await this.s3.getJson<RepositoryRecord>(`repositories/${oldName}.json`);
    if (!existing) return { success: false, message: `Repository "${oldName}" not found` };

    existing.repositoryName = newName;
    existing.updatedAt = new Date().toISOString();
    await this.s3.putJson(`repositories/${newName}.json`, existing);
    await this.s3.deleteObject(`repositories/${oldName}.json`);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    const name = params.repositoryName as string;
    await this.s3.deleteObject(`repositories/${name}.json`);
    return { success: true };
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.resolve([]);
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.resolve({ success: true });
  }
}

class S3VaultProvider implements VaultProvider {
  constructor(private readonly vaultService: S3VaultService) {}

  async getTeamVault(_teamName: string): Promise<VaultData | null> {
    return this.vaultService.getTeamVault();
  }

  async getMachineVault(_teamName: string, machineName: string): Promise<VaultData | null> {
    return this.vaultService.getMachineVault(machineName);
  }

  async getOrganizationVault(): Promise<VaultData | null> {
    return this.vaultService.getOrganizationVault();
  }

  async getConnectionVaults(
    _teamName: string,
    machineName: string,
    _repositoryName?: string
  ): Promise<{ machineVault: VaultData; teamVault: VaultData; repositoryVault?: VaultData }> {
    const teamVault = (await this.vaultService.getTeamVault()) ?? {};
    const machineVault = (await this.vaultService.getMachineVault(machineName)) ?? {};
    return { machineVault, teamVault };
  }
}

export class S3StateProvider implements IStateProvider {
  readonly mode = 's3' as const;
  readonly machines: MachineProvider;
  readonly queue: QueueProvider;
  readonly storage: StorageProvider;
  readonly repositories: RepositoryProvider;
  readonly vaults: VaultProvider;

  private constructor(
    s3Client: S3ClientService,
    vaultService: S3VaultService,
    queueService: S3QueueService
  ) {
    this.machines = new S3MachineProvider(s3Client, vaultService);
    this.queue = new S3QueueProvider(queueService);
    this.storage = new S3StorageProvider(s3Client, vaultService);
    this.repositories = new S3RepositoryProvider(s3Client);
    this.vaults = new S3VaultProvider(vaultService);
  }

  /**
   * Factory: creates an S3StateProvider from a named context.
   * If a master password is configured, decrypts the S3 secret access key
   * and enables vault encryption. Otherwise uses plaintext.
   */
  static async create(context: NamedContext): Promise<S3StateProvider> {
    if (!context.s3) {
      throw new Error(`Context "${context.name}" has no S3 configuration`);
    }

    let decryptedSecret: string;
    let masterPassword: string | null = null;

    if (context.masterPassword) {
      // Encrypted mode: decrypt the stored S3 secret
      masterPassword = await authService.requireMasterPassword();
      decryptedSecret = await nodeCryptoProvider.decrypt(
        context.s3.secretAccessKey,
        masterPassword
      );
    } else {
      // Plaintext mode: secretAccessKey is stored as-is
      decryptedSecret = context.s3.secretAccessKey;
    }

    const s3Client = new S3ClientService({
      ...context.s3,
      secretAccessKey: decryptedSecret,
    });

    const vaultService = new S3VaultService(s3Client, masterPassword);
    const queueService = new S3QueueService(s3Client);

    return new S3StateProvider(s3Client, vaultService, queueService);
  }
}
