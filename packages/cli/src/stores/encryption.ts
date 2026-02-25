import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';

/**
 * Wraps a store adapter with transparent AES-256-GCM encryption.
 * Encrypts the full config JSON before push, decrypts after pull.
 * The config's `id` and `version` remain readable (stored alongside the ciphertext).
 */
export class EncryptedStoreAdapter implements IStoreAdapter {
  private readonly inner: IStoreAdapter;
  private readonly encryptionKey: string;

  constructor(inner: IStoreAdapter, encryptionKey: string) {
    this.inner = inner;
    this.encryptionKey = encryptionKey;
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    const { nodeCryptoProvider } = await import('../adapters/crypto.js');
    const plaintext = JSON.stringify(config);
    const ciphertext = await nodeCryptoProvider.encrypt(plaintext, this.encryptionKey);

    // Store as a wrapper with readable id/version for conflict checks
    const envelope: RdcConfig = {
      id: config.id,
      version: config.version,
      encrypted: true,
      encryptedResources: ciphertext,
    };

    return this.inner.push(envelope, configName);
  }

  async pull(configName: string): Promise<PullResult> {
    const result = await this.inner.pull(configName);
    if (!result.success || !result.config) return result;

    const envelope = result.config;
    if (!envelope.encryptedResources) {
      // Not encrypted — pass through
      return result;
    }

    try {
      const { nodeCryptoProvider } = await import('../adapters/crypto.js');
      const plaintext = await nodeCryptoProvider.decrypt(
        envelope.encryptedResources,
        this.encryptionKey
      );
      const config = JSON.parse(plaintext) as RdcConfig;
      return { success: true, config };
    } catch {
      return { success: false, error: 'Failed to decrypt config. Check your encryption key.' };
    }
  }

  async list(): Promise<string[]> {
    return this.inner.list();
  }

  async delete(configName: string): Promise<PushResult> {
    return this.inner.delete(configName);
  }

  async verify(): Promise<boolean> {
    return this.inner.verify();
  }
}
