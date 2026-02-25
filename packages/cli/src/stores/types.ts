// ============================================================================
// Store Adapter Interface — Implemented by each store backend
// ============================================================================

import type { RdcConfig } from '../types/index.js';

/** Result of a push operation */
export interface PushResult {
  success: boolean;
  error?: string;
  /** Remote version after push */
  remoteVersion?: number;
}

/** Result of a pull operation */
export interface PullResult {
  success: boolean;
  config?: RdcConfig;
  error?: string;
}

/** Conflict details when push fails due to version/GUID mismatch */
export interface ConflictError {
  type: 'version_conflict' | 'guid_mismatch';
  localVersion: number;
  remoteVersion: number;
  localId: string;
  remoteId: string;
}

/**
 * Store adapter interface. Each store backend (S3, local-file, bitwarden, git) implements this.
 * Sync unit is always the full config file.
 */
export interface IStoreAdapter {
  /**
   * Push a config file to the store.
   * Validates: remote GUID must match local GUID, remote version must be <= local version.
   * On conflict, returns { success: false, error: "..." }.
   */
  push(config: RdcConfig, configName: string): Promise<PushResult>;

  /**
   * Pull a config file from the store by name.
   * Returns the full config or null if not found.
   */
  pull(configName: string): Promise<PullResult>;

  /** List config file names available in this store */
  list(): Promise<string[]>;

  /** Delete a config file from the store */
  delete(configName: string): Promise<PushResult>;

  /** Verify connectivity and access to the store */
  verify(): Promise<boolean>;
}
