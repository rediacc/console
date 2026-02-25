import { DEFAULTS } from '@rediacc/shared/config';
import { S3ClientService } from '../services/s3-client.js';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';
import type { StoreEntry } from '../types/store.js';

/**
 * S3 store adapter. Stores config files as JSON objects in an S3/R2 bucket.
 * Config file "production" is stored at key "configs/production.json" in the bucket.
 */
export class S3StoreAdapter implements IStoreAdapter {
  private readonly s3: S3ClientService;

  constructor(entry: StoreEntry) {
    if (!entry.s3Endpoint || !entry.s3Bucket || !entry.s3AccessKeyId || !entry.s3SecretAccessKey) {
      throw new Error('S3 store requires endpoint, bucket, accessKeyId, and secretAccessKey');
    }
    this.s3 = new S3ClientService({
      endpoint: entry.s3Endpoint,
      bucket: entry.s3Bucket,
      region: entry.s3Region ?? DEFAULTS.STORE.S3_REGION,
      accessKeyId: entry.s3AccessKeyId,
      secretAccessKey: entry.s3SecretAccessKey,
      prefix: entry.s3Prefix,
    });
  }

  private configKey(configName: string): string {
    return `configs/${configName}.json`;
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    const key = this.configKey(configName);

    // Check remote for conflict
    const remote = await this.s3.getJson<RdcConfig>(key);
    if (remote) {
      if (remote.id !== config.id) {
        return {
          success: false,
          error: `GUID mismatch: local config id "${config.id}" does not match remote "${remote.id}". Configs with different IDs cannot be synced.`,
        };
      }
      if (remote.version > config.version) {
        return {
          success: false,
          error: `Version conflict: remote version ${remote.version} is newer than local version ${config.version}. Run "rdc store pull" first.`,
        };
      }
    }

    await this.s3.putJson(key, config);
    return { success: true, remoteVersion: config.version };
  }

  async pull(configName: string): Promise<PullResult> {
    const key = this.configKey(configName);
    const config = await this.s3.getJson<RdcConfig>(key);
    if (!config) {
      return { success: false, error: `Config "${configName}" not found in store` };
    }
    return { success: true, config };
  }

  async list(): Promise<string[]> {
    const keys = await this.s3.listKeys('configs/');
    return keys
      .filter((k) => k.endsWith('.json'))
      .map((k) => k.replace(/^configs\//, '').replace(/\.json$/, ''));
  }

  async delete(configName: string): Promise<PushResult> {
    const key = this.configKey(configName);
    await this.s3.deleteObject(key);
    return { success: true };
  }

  async verify(): Promise<boolean> {
    try {
      await this.s3.verifyAccess();
      return true;
    } catch {
      return false;
    }
  }
}
