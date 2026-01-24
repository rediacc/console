// CLI-specific types

// ============================================================================
// Multi-Context Configuration
// ============================================================================

/**
 * Machine configuration for local mode.
 * Defines SSH connection details for a machine.
 */
export interface LocalMachineConfig {
  /** Machine IP address or hostname */
  ip: string;
  /** SSH username */
  user: string;
  /** SSH port (default: 22) */
  port?: number;
  /** Datastore path on the machine */
  datastore?: string;
}

/**
 * SSH configuration for local mode.
 * Points to local SSH key files.
 */
export interface LocalSSHConfig {
  /** Path to SSH private key file (e.g., ~/.ssh/id_rsa) */
  privateKeyPath: string;
  /** Path to SSH public key file (optional) */
  publicKeyPath?: string;
}

/**
 * Context mode: 'cloud' uses middleware API, 'local' uses direct renet execution.
 */
export type ContextMode = 'cloud' | 'local';

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
  // Local Mode Configuration (only used when mode === 'local')
  // ============================================================================

  /** Machine configurations for local mode (name -> config) */
  machines?: Record<string, LocalMachineConfig>;
  /** SSH configuration for local mode */
  ssh?: LocalSSHConfig;
  /** Path to renet binary (default: 'renet' in PATH) */
  renetPath?: string;
}

/**
 * Root configuration containing multiple named contexts.
 * Note: No currentContext field - context is always specified explicitly via
 * --context flag, or defaults to "default".
 */
export interface CliConfig {
  /** Map of context names to their configurations */
  contexts: { [name: string]: NamedContext | undefined };
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
