import { EncryptedStoreAdapter } from './encryption.js';
import type { IStoreAdapter } from './types.js';
import type { StoreEntry } from '../types/store.js';

/**
 * Factory: create the appropriate store adapter for a store entry.
 * Wraps with encryption if the store has an encryptionKey.
 */
export async function createStoreAdapter(entry: StoreEntry): Promise<IStoreAdapter> {
  let adapter: IStoreAdapter;

  switch (entry.type) {
    case 's3': {
      const { S3StoreAdapter } = await import('./s3-store-adapter.js');
      adapter = new S3StoreAdapter(entry);
      break;
    }
    case 'local-file': {
      const { LocalFileStoreAdapter } = await import('./local-file-store-adapter.js');
      adapter = new LocalFileStoreAdapter(entry);
      break;
    }
    case 'bitwarden': {
      const { BitwardenStoreAdapter } = await import('./bitwarden-store-adapter.js');
      adapter = new BitwardenStoreAdapter(entry);
      break;
    }
    case 'git': {
      const { GitStoreAdapter } = await import('./git-store-adapter.js');
      adapter = new GitStoreAdapter(entry);
      break;
    }
    case 'vault': {
      const { VaultStoreAdapter } = await import('./vault-store-adapter.js');
      adapter = new VaultStoreAdapter(entry);
      break;
    }
    default:
      throw new Error(`Unknown store type: ${entry.type}`);
  }

  // Wrap with encryption if key is provided
  if (entry.encryptionKey) {
    adapter = new EncryptedStoreAdapter(adapter, entry.encryptionKey);
  }

  return adapter;
}

export { storeRegistry } from './registry.js';
export type { IStoreAdapter, PushResult, PullResult, ConflictError } from './types.js';
