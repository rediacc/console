/**
 * S3VaultService - Vault read/write on S3.
 *
 * When a master password is provided, data is encrypted at rest using
 * AES-256-GCM via NodeCryptoProvider. When null, data is stored as plain JSON.
 */

import { nodeCryptoProvider } from '../adapters/crypto.js';
import type { S3ClientService } from './s3-client.js';

export class S3VaultService {
  constructor(
    private s3: S3ClientService,
    private masterPassword: string | null
  ) {}

  async readVault<T>(key: string): Promise<T | null> {
    if (this.masterPassword) {
      const encrypted = await this.s3.getRaw(key);
      if (!encrypted) return null;
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, this.masterPassword);
      return JSON.parse(decrypted) as T;
    }
    return this.s3.getJson<T>(key);
  }

  async writeVault(key: string, data: unknown): Promise<void> {
    if (this.masterPassword) {
      const json = JSON.stringify(data);
      const encrypted = await nodeCryptoProvider.encrypt(json, this.masterPassword);
      await this.s3.putRaw(key, encrypted);
    } else {
      await this.s3.putJson(key, data);
    }
  }

  async getTeamVault(): Promise<Record<string, unknown> | null> {
    return this.readVault<Record<string, unknown>>('vaults/team.json.enc');
  }

  async getMachineVault(machineName: string): Promise<Record<string, unknown> | null> {
    return this.readVault<Record<string, unknown>>(`vaults/machines/${machineName}.json.enc`);
  }

  async getOrganizationVault(): Promise<Record<string, unknown> | null> {
    return this.readVault<Record<string, unknown>>('vaults/organization.json.enc');
  }

  async setTeamVault(data: Record<string, unknown>): Promise<void> {
    await this.writeVault('vaults/team.json.enc', data);
  }

  async setMachineVault(machineName: string, data: Record<string, unknown>): Promise<void> {
    await this.writeVault(`vaults/machines/${machineName}.json.enc`, data);
  }

  async setOrganizationVault(data: Record<string, unknown>): Promise<void> {
    await this.writeVault('vaults/organization.json.enc', data);
  }
}
