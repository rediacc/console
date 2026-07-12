// CLI-specific types — re-exports from the v2 Zod schema plus
// non-config-shape enums/interfaces that remain hand-written.

import type { PlatformKey } from '../utils/platform.js';

// ============================================================================
// Config types (derived from Zod v2 schema — single source of truth)
// ============================================================================

import type { RdcConfig } from '@rediacc/shared/config-schema';

export type {
  AcmeCertCache,
  ArchivedRepository,
  BackupDestination,
  BackupDestination as BackupStrategyDestination,
  BackupStrategyConfig,
  CloudProviderConfig,
  ClusterConfig,
  ClusterKvm,
  ClusterPool,
  ClusterPoolRole,
  EncryptedBlob,
  EncryptionState,
  InfraConfig,
  MachineConfig,
  RdcConfig,
  RemoteConfig,
  RepositoryConfig,
  SecretEntry,
  SecretMode,
  StorageConfig,
} from '@rediacc/shared/config-schema';

export { createEmptyRdcConfig, hasRemoteConfig } from '@rediacc/shared/config-schema';

/**
 * SSH credentials — derived from the Zod schema's `credentials.ssh` so that
 * schema changes propagate automatically. The name `SSHContent` is retained
 * for grep-continuity with existing call sites.
 */
export type SSHContent = NonNullable<NonNullable<RdcConfig['credentials']>['ssh']>;

// ============================================================================
// Output / UI types
// ============================================================================

export interface OutputConfig {
  format: OutputFormat;
  color: boolean;
}

export type OutputFormat = 'table' | 'json' | 'yaml' | 'csv';

export interface CommandOptions {
  team?: string;
  region?: string;
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

// ============================================================================
// Exit codes (Unix-compatible)
// ============================================================================

export const EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGUMENTS: 2,
  AUTH_REQUIRED: 3,
  PERMISSION_DENIED: 4,
  NOT_FOUND: 5,
  NETWORK_ERROR: 6,
  API_ERROR: 7,
  PAYMENT_REQUIRED: 8,
  RATE_LIMITED: 9,
} as const;

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

export interface IStorageProvider {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  clear?(): Promise<void>;
}

export type { ICryptoProvider } from '@rediacc/shared/encryption';

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

// ============================================================================
// Provider sub-types (still hand-written — not part of the top-level shape)
// ============================================================================

export interface ProviderSSHKeyConfig {
  attr: string;
  format: 'inline_list' | 'resource_id';
  keyResource?: string;
}

export interface ProviderFirewallConfig {
  resource: string;
  linkAttr?: string;
  linkRef?: string;
  attachResource?: string;
}

/** Disk class a provider offers for OSD/data storage, informing pool sizing. */
export type ProviderDiskClass = 'local-nvme' | 'network-volume' | 'ephemeral';

/**
 * Private-network primitive for a multi-machine cluster. Encodes the single
 * most bite-prone field (MTU: 1500 vs 1450 vs 1400 vs 9001 silently wrecks Ceph
 * replication) plus how a private NIC attaches per provider. Absent on
 * single-machine `machine provision`; consumed only by the cluster generator.
 */
export interface ProviderNetworkConfig {
  /** Terraform resource for the private network (e.g. hcloud_network). */
  resource: string;
  /** L2 (VLAN/vSwitch) or L3 (VPC/network). */
  layer: 'l2' | 'l3';
  /** Whether the provider requires a private network to place instances. */
  mandatory?: boolean;
  /** Subnet resource, when the network is split into subnets (e.g. hcloud_network_subnet). */
  subnetResource?: string;
  /** How an instance joins the network: an inline interface block or an attach resource. */
  attachVia?: 'interface' | 'attach_resource';
  /** Attach resource name when attachVia === 'attach_resource' (e.g. hcloud_server_network). */
  attachResource?: string;
  /** Private NIC device name inside the guest (e.g. eth1). */
  nicName?: string;
  /** MTU to stamp on the private NIC. */
  mtu?: number;
  /** Maximum nodes per network segment (provider limit). */
  maxNodes?: number;
}

/**
 * How a provider attaches a dedicated block-storage volume to a cluster member
 * (e.g. Linode Block Storage for Ceph OSDs, since a vanilla instance exposes
 * only its boot disk). The cluster generator emits one volume resource per
 * pool `disks[]` entry and attaches it to the member instance. The in-guest
 * device path where the volume appears is carried by the pool's
 * `disks[].purpose` (uniform across a pool's members), consumed by the Ceph
 * install; this block is only the terraform HOW-to-create.
 */
export interface ProviderVolumeConfig {
  /** Terraform resource for a block-storage volume (e.g. linode_volume). */
  resource: string;
  /** Attribute carrying the volume size in GB (e.g. size). */
  sizeAttr: string;
  /** Attribute that attaches the volume to an instance by id (e.g. linode_id). */
  attachAttr: string;
  /** Attribute carrying the volume label (e.g. label). */
  labelAttr: string;
  /** Whether the volume resource needs an explicit region attribute stamped. */
  needsRegion?: boolean;
}

export interface ProviderMapping {
  source: string;
  version?: string;
  tokenAttr: string;
  resource: string;
  labelAttr: string;
  regionAttr: string;
  sizeAttr: string;
  imageAttr: string;
  ipv4Output: string;
  ipv6Output?: string;
  sshKey: ProviderSSHKeyConfig;
  firewall?: ProviderFirewallConfig;
  defaults?: Record<string, string>;
  /** Private-network block (cluster provisioning only). */
  network?: ProviderNetworkConfig;
  /** Disk class hint for OSD/data pools. */
  disk?: ProviderDiskClass;
  /** Block-storage volume block (cluster provisioning only; e.g. Ceph OSDs). */
  volume?: ProviderVolumeConfig;
}

export interface CephConfig {
  pool: string;
  image: string;
  clusterName?: string;
}
