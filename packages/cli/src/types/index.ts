// CLI-specific types

// ============================================================================
// Multi-Context Configuration
// ============================================================================

/**
 * Machine configuration. Defines SSH connection details for a machine.
 * Used by both local and S3 modes (stored in config.json or state.json).
 */
export interface MachineConfig {
  /** Machine IP address or hostname */
  ip: string;
  /** SSH username */
  user: string;
  /** SSH port (default: 22) */
  port?: number;
  /** Datastore path on the machine */
  datastore?: string;
  /** SSH host key(s) for this machine (from ssh-keyscan) */
  knownHosts?: string;
  /** Infrastructure configuration (public IPs, domain, TLS, ports) */
  infra?: InfraConfig;
}

/**
 * Infrastructure configuration for a machine.
 * Stores public networking, domain, TLS, and port forwarding settings.
 * Used by `renet proxy configure` to generate proxy/router config on remote machines.
 */
export interface InfraConfig {
  /** Public IPv4 address for external access (binds Traefik entrypoints) */
  publicIPv4?: string;
  /** Public IPv6 address for external access (binds Traefik entrypoints) */
  publicIPv6?: string;
  /** Base domain for applications (e.g., "example.com") */
  baseDomain?: string;
  /** Email address for TLS certificate notifications (Let's Encrypt) */
  certEmail?: string;
  /** Cloudflare DNS API token for ACME DNS-01 challenge */
  cfDnsApiToken?: string;
  /** Additional TCP ports to forward (e.g., [25, 143, 465, 587, 993]) */
  tcpPorts?: number[];
  /** Additional UDP ports to forward (e.g., [53]) */
  udpPorts?: number[];
}

/**
 * Storage configuration. Stores rclone-imported storage vault data.
 * Used by both local and S3 modes.
 */
export interface StorageConfig {
  /** Storage provider type (s3, b2, drive, etc.) */
  provider: string;
  /** Full vault content (provider, bucket, credentials, etc.) */
  vaultContent: Record<string, unknown>;
}

/**
 * Repository configuration. Maps a human-readable name to its GUID.
 * Used by both local and S3 modes.
 */
export interface RepositoryConfig {
  /** Repository GUID (the UUID used as filename in storage backups) */
  repositoryGuid: string;
  /** Repository tag (default: 'latest') */
  tag?: string;
  /** Repository credential (encryption passphrase for the backup) */
  credential?: string;
  /** Network ID for Docker isolation (2816 + n*64). Auto-assigned if omitted. */
  networkId?: number;
}

/**
 * SSH configuration. Points to local SSH key files.
 * Used by both local and S3 modes (always stored in config.json).
 */
export interface SSHConfig {
  /** Path to SSH private key file (e.g., ~/.ssh/id_rsa) */
  privateKeyPath: string;
  /** Path to SSH public key file (optional) */
  publicKeyPath?: string;
}

/**
 * S3/R2 configuration for S3 mode.
 * Stores connection details for an S3-compatible bucket.
 */
export interface S3Config {
  /** S3 endpoint URL (e.g., https://<accountId>.r2.cloudflarestorage.com) */
  endpoint: string;
  /** Bucket name */
  bucket: string;
  /** AWS region ('auto' for R2) */
  region: string;
  /** Access key ID */
  accessKeyId: string;
  /** Secret access key (encrypted via masterPassword if set, plaintext otherwise) */
  secretAccessKey: string;
  /** Optional key prefix/namespace within the bucket */
  prefix?: string;
}

/**
 * Backup schedule configuration for a context.
 * Defines the default storage destination and cron schedule for automated backups.
 * Used by `rdc backup schedule set|show|push` to configure systemd timers on remote machines.
 */
export interface BackupConfig {
  /** Storage name to use as backup destination (e.g., "microsoft") */
  defaultDestination: string;
  /** Cron expression for backup schedule (e.g., "0 2 * * *") */
  schedule?: string;
  /** Whether the schedule is enabled (default: true) */
  enabled?: boolean;
}

/**
 * Context mode: 'cloud' uses middleware API, 'local' uses direct renet execution,
 * 's3' uses S3-compatible storage for state with local renet execution.
 */
export type ContextMode = 'cloud' | 'local' | 's3';

/**
 * A named context containing all configuration for a specific environment.
 * Each context has its own API endpoint, credentials, and default team/region.
 */
export interface NamedContext {
  /** Unique name for this context (e.g., "production", "local", "staging") */
  name: string;
  /** Context mode: 'cloud' (default) or 'local' */
  mode?: ContextMode;
  /** API endpoint URL (required for cloud mode) */
  apiUrl: string;
  /** Authentication token for this endpoint (cloud mode) */
  token?: string;
  /** Encrypted master password for vault operations */
  masterPassword?: string;
  /** User email address */
  userEmail?: string;
  /** Default team for this context */
  team?: string;
  /** Default region for this context */
  region?: string;
  /** Default bridge for this context */
  bridge?: string;
  /** Default machine for this context */
  machine?: string;
  /** Preferred language code (en, de, es, fr, ja, ar, ru, tr, zh) */
  language?: string;

  // ============================================================================
  // Local/S3 Mode Configuration (used when mode === 'local' or mode === 's3')
  // ============================================================================

  /** Machine configurations for local/s3 mode (name -> config) */
  machines?: Record<string, MachineConfig>;
  /** Storage configurations for local/s3 mode (name -> config) */
  storages?: Record<string, StorageConfig>;
  /** Repository name-to-GUID mappings for storage browse (name -> config) */
  repositories?: Record<string, RepositoryConfig>;
  /** SSH configuration for local/s3 mode */
  ssh?: SSHConfig;
  /** Path to renet binary (default: 'renet' in PATH) */
  renetPath?: string;
  /** Backup schedule configuration */
  backup?: BackupConfig;

  // ============================================================================
  // S3 Mode Configuration (only used when mode === 's3')
  // ============================================================================

  /** S3/R2 bucket configuration for S3 mode */
  s3?: S3Config;
}

/**
 * Root configuration containing multiple named contexts.
 * Note: No currentContext field - context is always specified explicitly via
 * --context flag, or defaults to "default".
 */
export interface CliConfig {
  /** Map of context names to their configurations */
  contexts: { [name: string]: NamedContext | undefined };
  /** Global network ID counter. Monotonically increasing across all contexts. */
  nextNetworkId?: number;
}

/**
 * Create an empty config with no contexts.
 */
export function createEmptyConfig(): CliConfig {
  return {
    contexts: {},
  };
}

export interface OutputConfig {
  format: OutputFormat;
  color: boolean;
}

export type OutputFormat = 'table' | 'json' | 'yaml' | 'csv';

export interface CommandOptions {
  team?: string;
  region?: string;
  bridge?: string;
  machine?: string;
  output?: OutputFormat;
  force?: boolean;
  watch?: boolean;
  [key: string]: unknown;
}

export interface ApiCallOptions {
  endpoint: string;
  data?: Record<string, unknown>;
  headers?: Record<string, string>;
}

// Exit codes (Unix-compatible)
export const EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGUMENTS: 2, // Unix convention for usage error
  AUTH_REQUIRED: 3,
  PERMISSION_DENIED: 4,
  NOT_FOUND: 5,
  NETWORK_ERROR: 6,
  API_ERROR: 7, // Server returned error
  PAYMENT_REQUIRED: 8, // HTTP 402 - edition/subscription limit reached
  RATE_LIMITED: 9, // HTTP 429 - too many requests
} as const;

/**
 * Map HTTP status codes to CLI exit codes.
 * Used for converting API responses to Unix-compatible exit codes.
 */
export function httpStatusToExitCode(httpStatus: number): number {
  switch (httpStatus) {
    case 400:
      return EXIT_CODES.INVALID_ARGUMENTS;
    case 401:
      return EXIT_CODES.AUTH_REQUIRED;
    case 402:
      return EXIT_CODES.PAYMENT_REQUIRED;
    case 403:
      return EXIT_CODES.PERMISSION_DENIED;
    case 404:
      return EXIT_CODES.NOT_FOUND;
    case 429:
      return EXIT_CODES.RATE_LIMITED;
    default:
      return httpStatus >= 400 && httpStatus < 500
        ? EXIT_CODES.API_ERROR
        : EXIT_CODES.GENERAL_ERROR;
  }
}

export type ExitCode = (typeof EXIT_CODES)[keyof typeof EXIT_CODES];

// Storage provider interface (matches console/src/core/types/storage.ts)
export interface IStorageProvider {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  clear?(): Promise<void>;
}

export type { ICryptoProvider } from '@rediacc/shared/encryption';

// ============================================================================
// S3 State Types (single state.json in bucket)
// ============================================================================

/** SSH key content stored in state.json for S3 mode portability. */
export interface SSHContent {
  /** Actual SSH private key (PEM content) */
  privateKey: string;
  /** Actual SSH public key content */
  publicKey?: string;
}

/**
 * Root shape of the S3 state document stored at `state.json` in the bucket.
 * Uses the same unified types as config.json (MachineConfig, StorageConfig, RepositoryConfig).
 * When `encrypted` is true, each section value is an AES-256-GCM ciphertext string.
 * When false, sections are plain objects.
 */
export interface S3StateData {
  version: 1;
  encrypted: boolean;
  machines: Record<string, MachineConfig> | string;
  storages: Record<string, StorageConfig> | string;
  repositories: Record<string, RepositoryConfig> | string;
  ssh?: SSHContent | string;
}

// ============================================================================
// Auto-Update Types
// ============================================================================

import type { PlatformKey } from '../utils/platform.js';

export interface BinaryInfo {
  url: string;
  sha256: string;
}

export interface UpdateManifest {
  version: string;
  releaseDate: string;
  releaseNotesUrl: string;
  binaries: Partial<Record<PlatformKey, BinaryInfo>>;
}
