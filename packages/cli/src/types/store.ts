// ============================================================================
// Store Types — External backends for syncing config files
// ============================================================================

/** Supported store backend types */
export type StoreType = 's3' | 'local-file' | 'bitwarden' | 'git' | 'vault';

/**
 * A store entry representing a remote location where config files can be synced.
 * Stored in ~/.rediacc/.credentials.json.
 */
export interface StoreEntry {
  /** Unique name for this store (e.g., "backup-s3", "team-shared") */
  name: string;
  /** Store backend type */
  type: StoreType;
  /** Encryption key for this store (optional, per-store encryption) */
  encryptionKey?: string;

  // S3 store fields
  /** S3 endpoint URL */
  s3Endpoint?: string;
  /** S3 bucket name */
  s3Bucket?: string;
  /** S3 region (e.g., 'auto' for Cloudflare R2) */
  s3Region?: string;
  /** S3 access key ID */
  s3AccessKeyId?: string;
  /** S3 secret access key */
  s3SecretAccessKey?: string;
  /** S3 key prefix within the bucket */
  s3Prefix?: string;

  // Local file store fields
  /** Local filesystem path for file-based store */
  localPath?: string;

  // Bitwarden store fields
  /** Bitwarden folder ID to organize config items (optional) */
  bwFolderId?: string;

  // Git store fields
  /** Git repository URL */
  gitUrl?: string;
  /** Git branch name (default: main) */
  gitBranch?: string;
  /** Path within the git repo to store config files */
  gitPath?: string;

  // Vault store fields
  /** Vault server address (e.g., http://127.0.0.1:8200) */
  vaultAddr?: string;
  /** Vault authentication token */
  vaultToken?: string;
  /** KV v2 mount path (default: secret) */
  vaultMount?: string;
  /** Path prefix within the KV engine (default: rdc/configs) */
  vaultPrefix?: string;
  /** Vault namespace (enterprise only, optional) */
  vaultNamespace?: string;
}
