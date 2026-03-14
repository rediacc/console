// CLI-specific types
import { randomUUID } from 'node:crypto';
import type { PlatformKey } from '../utils/platform.js';

// ============================================================================
// Config File Types
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
  /** Ceph RBD datastore configuration */
  ceph?: CephConfig;
}

/**
 * Ceph RBD configuration for a machine's datastore.
 * When set, the machine uses Ceph RBD as the datastore backend instead of local loop device.
 */
export interface CephConfig {
  /** Ceph pool name (e.g., "rbd") */
  pool: string;
  /** RBD image name (e.g., "datastore-prod1") */
  image: string;
  /** Ceph cluster name (default: "ceph") */
  clusterName?: string;
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
  /** Additional TCP ports to forward (e.g., [25, 143, 465, 587, 993]) */
  tcpPorts?: number[];
  /** Additional UDP ports to forward (e.g., [53]) */
  udpPorts?: number[];
}

// ============================================================================
// Cloud Provider Types (OpenTofu-based VM provisioning)
// ============================================================================

/** SSH key injection mechanism for cloud providers. */
export interface ProviderSSHKeyConfig {
  /** Resource attribute name for SSH keys */
  attr: string;
  /** How keys are injected: 'inline_list' (raw key in array) or 'resource_id' (separate SSH key resource) */
  format: 'inline_list' | 'resource_id';
  /** If format='resource_id', the OpenTofu resource type for SSH keys (e.g., "hcloud_ssh_key") */
  keyResource?: string;
}

/** Firewall configuration in provider registry. */
export interface ProviderFirewallConfig {
  /** Firewall resource type (e.g., "linode_firewall") */
  resource: string;
  /** Attribute that links firewall to instance (e.g., "linodes") */
  linkAttr?: string;
  /** Reference expression for the link (e.g., "${linode_instance.machine.id}") */
  linkRef?: string;
  /** Separate attachment resource (e.g., "hcloud_firewall_attachment") */
  attachResource?: string;
}

/** Provider mapping — describes how to generate .tf.json for a specific cloud provider. */
export interface ProviderMapping {
  /** OpenTofu provider source (e.g., "linode/linode") */
  source: string;
  /** Provider version constraint (e.g., "~> 3.0") */
  version?: string;
  /** Provider config attribute name for the API token */
  tokenAttr: string;
  /** Resource type for the VM (e.g., "linode_instance") */
  resource: string;
  /** Attribute name for the VM label/name */
  labelAttr: string;
  /** Attribute name for region/location */
  regionAttr: string;
  /** Attribute name for instance type/size */
  sizeAttr: string;
  /** Attribute name for OS image */
  imageAttr: string;
  /** Output attribute path for IPv4 */
  ipv4Output: string;
  /** Output attribute path for IPv6 (optional) */
  ipv6Output?: string;
  /** SSH key injection config */
  sshKey: ProviderSSHKeyConfig;
  /** Firewall configuration (optional) */
  firewall?: ProviderFirewallConfig;
  /** Default values for provider-specific attributes */
  defaults?: Record<string, string>;
}

/** Cloud provider configuration stored in rediacc.json. */
export interface CloudProviderConfig {
  /** For known providers: matches a key in provider-registry.json (e.g., "linode/linode") */
  provider?: string;
  /** For custom providers: full OpenTofu source (e.g., "vultr/vultr"). Presence triggers custom mode. */
  source?: string;
  /** API token for the cloud provider */
  apiToken: string;
  /** Default region */
  region?: string;
  /** Default instance type/size */
  instanceType?: string;
  /** Default OS image */
  image?: string;
  /** SSH username for created VMs (default: "root") */
  sshUser?: string;

  // --- Custom provider fields (only when source is set) ---
  /** Provider version constraint */
  version?: string;
  /** Provider attribute name for the API token */
  tokenAttr?: string;
  /** Resource type for the VM */
  resource?: string;
  /** Attribute name for the VM label */
  labelAttr?: string;
  /** Attribute name for region */
  regionAttr?: string;
  /** Attribute name for instance type */
  sizeAttr?: string;
  /** Attribute name for OS image */
  imageAttr?: string;
  /** Output attribute for IPv4 */
  ipv4Output?: string;
  /** Output attribute for IPv6 */
  ipv6Output?: string;
  /** SSH key config */
  sshKey?: ProviderSSHKeyConfig;
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
  /** GUID of the grand (parent) repository. Present on forks; absent on grand repos. */
  grandGuid?: string;
  /** Per-repo SSH private key (OpenSSH format). Used for sandbox-isolated connections. */
  sshPrivateKey?: string;
  /** Per-repo SSH public key. Deployed to remote authorized_keys with sandbox gateway command= prefix. */
  sshPublicKey?: string;
}

/**
 * Archived repository entry. Preserved when a repo is deleted via `rdc repo delete`
 * so the LUKS credential can be restored if the same repo exists on other machines.
 */
export interface ArchivedRepository extends RepositoryConfig {
  /** Original friendly name of the repository */
  name: string;
  /** ISO 8601 timestamp when the repository was deleted */
  deletedAt: string;
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
 * A single backup destination within the backup strategy.
 * Each destination targets a named storage and can override the global schedule.
 */
export interface BackupStrategyDestination {
  /** Storage name (e.g., "my-s3") */
  storage: string;
  /** Per-destination cron override (falls back to global schedule) */
  schedule?: string;
  /** Per-destination enable/disable (falls back to global enabled) */
  enabled?: boolean;
}

/**
 * Backup strategy configuration for a config.
 * Defines one or more storage destinations and cron schedules for automated backups.
 * Used by `rdc config backup-strategy set|show` and `rdc machine deploy-backup` to configure systemd timers on remote machines.
 */
export interface BackupStrategyConfig {
  /** Backup destinations */
  destinations: BackupStrategyDestination[];
  /** Global default cron expression (e.g., "0 2 * * *") */
  schedule?: string;
  /** Global enable/disable (default: true) */
  enabled?: boolean;
}

/**
 * Cached ACME certificate data from Traefik's acme.json.
 * Stored at config level keyed by baseDomain (shared across machines).
 * Compressed with gzip + base64. Chunked into 48KB pieces for backends with size limits.
 */
export interface AcmeCertCache {
  /** Base domain this cache applies to (e.g., "rediacc.io") */
  baseDomain: string;
  /** ISO 8601 timestamp of last cache update */
  updatedAt: string;
  /** Machine name the cache was downloaded from */
  sourceMachine: string;
  /** Number of certificates in the cache */
  certCount: number;
  /** Certificate inventory: domain → expiry date (ISO 8601) */
  certs: Record<string, string>;
  /** gzip + base64 encoded acme.json. Array of 48KB chunks if large. */
  data: string | string[];
  /** Original uncompressed size in bytes */
  rawSize: number;
}

/**
 * A flat config file (e.g., rediacc.json, production.json).
 * Each file is an independent, self-contained unit with a unique GUID
 * and version number for conflict detection during store sync.
 *
 * Adapter detection is automatic:
 * - Has apiUrl + token → Cloud adapter (experimental)
 * - Otherwise → Local adapter (default)
 * - Has s3 config → S3 resource state (with local adapter)
 */
export interface RdcConfig {
  /** UUID v4 — unique identifier for this config file. Never changes. Unencrypted, always visible. */
  id: string;
  /** Monotonically increasing version number. Incremented on every write. */
  version: number;

  // ============================================================================
  // Cloud (experimental — requires REDIACC_EXPERIMENTAL=1)
  // ============================================================================

  /** API endpoint URL (cloud mode only) */
  apiUrl?: string;
  /** Authentication token (cloud mode only) */
  token?: string;
  /** User email address (cloud mode only) */
  userEmail?: string;
  /** Default team (cloud mode only) */
  team?: string;
  /** Default region (cloud mode only) */
  region?: string;
  /** Default bridge (cloud mode only) */
  bridge?: string;

  // ============================================================================
  // Self-Hosted (local adapter)
  // ============================================================================

  /** Machine configurations (name -> config) */
  machines?: Record<string, MachineConfig>;
  /** Storage configurations (name -> config) */
  storages?: Record<string, StorageConfig>;
  /** Repository name-to-GUID mappings (name -> config) */
  repositories?: Record<string, RepositoryConfig>;
  /** Archived repository credentials from deleted repos */
  deletedRepositories?: ArchivedRepository[];
  /** SSH configuration */
  ssh?: SSHConfig;
  /** Inline SSH key content for portability */
  sshContent?: SSHContent;
  /** Path to renet binary (default: 'renet' in PATH) */
  renetPath?: string;
  /** Backup strategy configuration */
  backupStrategy?: BackupStrategyConfig;
  /** Cloudflare DNS API token for ACME DNS-01 challenge (shared across machines) */
  cfDnsApiToken?: string;
  /** Cached Cloudflare DNS zone ID (auto-resolved from baseDomain) */
  cfDnsZoneId?: string;
  /** Email address for TLS certificate notifications (shared across machines) */
  certEmail?: string;
  /** When true, resources are encrypted in encryptedResources blob */
  encrypted?: boolean;
  /** Encrypted blob of {machines, storages, repositories, sshContent} */
  encryptedResources?: string;
  /** Encrypted master password for vault operations */
  masterPassword?: string;
  /** Cloud provider configurations for automated VM provisioning (name -> config) */
  cloudProviders?: Record<string, CloudProviderConfig>;
  /** Cached ACME certificate data, keyed by baseDomain (shared across machines) */
  acmeCertCache?: Record<string, AcmeCertCache>;

  // ============================================================================
  // S3 Resource State (used when config.s3 is populated)
  // ============================================================================

  /** S3/R2 bucket configuration for remote resource state */
  s3?: S3Config;

  // ============================================================================
  // Defaults & Global Settings
  // ============================================================================

  /** Default machine for commands */
  machine?: string;
  /** Preferred language code (en, de, es, fr, ja, ar, ru, tr, zh) */
  language?: string;
  /** Network ID counter. Monotonically increasing. */
  nextNetworkId?: number;
  /** Override the default universal user ("rediacc") for command execution */
  universalUser?: string;
}

/**
 * Create a new empty config with a fresh UUID and version 1.
 */
export function createEmptyRdcConfig(): RdcConfig {
  return {
    id: randomUUID(),
    version: 1,
  };
}

/**
 * Detect if a config has cloud credentials (apiUrl + token).
 * Used for adapter-based detection instead of an explicit mode field.
 */
export function hasCloudCredentials(config: RdcConfig | null | undefined): boolean {
  return Boolean(config?.apiUrl && config.token);
}

/**
 * Detect if a config has cloud intent (apiUrl present, token may be absent).
 * Used by the mode guard to allow pre-authentication commands (auth register/login)
 * to run before a token is obtained.
 */
export function hasCloudIntent(config: RdcConfig | null | undefined): boolean {
  return Boolean(config?.apiUrl);
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
  deletedRepositories?: ArchivedRepository[] | string;
  ssh?: SSHContent | string;
}

// ============================================================================
// Auto-Update Types
// ============================================================================

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
