// CLI-specific types — re-exports from the v2 Zod schema plus
// non-config-shape enums/interfaces that remain hand-written.

import type { PlatformKey } from '../utils/platform.js';

// ============================================================================
// Config types (derived from Zod v2 schema — single source of truth)
// ============================================================================

import type { RdcConfig } from '../schema/schemas.js';

export type {
  RdcConfig,
  MachineConfig,
  StorageConfig,
  RepositoryConfig,
  ArchivedRepository,
  SecretEntry,
  SecretMode,
  InfraConfig,
  BackupDestination,
  BackupDestination as BackupStrategyDestination,
  BackupStrategyConfig,
  CloudProviderConfig,
  AcmeCertCache,
  RemoteConfig,
  EncryptedBlob,
  EncryptionState,
} from '../schema/schemas.js';

export {
  createEmptyRdcConfig,
  hasCloudCredentials,
  hasCloudIntent,
  hasRemoteConfig,
} from '../schema/schemas.js';

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
}

export interface CephConfig {
  pool: string;
  image: string;
  clusterName?: string;
}
