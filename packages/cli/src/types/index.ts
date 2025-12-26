// CLI-specific types

// ============================================================================
// Multi-Context Configuration
// ============================================================================

/**
 * A named context containing all configuration for a specific environment.
 * Each context has its own API endpoint, credentials, and default team/region.
 */
export interface NamedContext {
  /** Unique name for this context (e.g., "production", "local", "staging") */
  name: string;
  /** API endpoint URL */
  apiUrl: string;
  /** Authentication token for this endpoint */
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
}

/**
 * Root configuration containing multiple named contexts.
 */
export interface CliConfig {
  /** Name of the currently active context */
  currentContext: string;
  /** Map of context names to their configurations */
  contexts: Record<string, NamedContext>;
}

/**
 * Create an empty config with no contexts.
 */
export function createEmptyConfig(): CliConfig {
  return {
    currentContext: '',
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
} as const;

export type ExitCode = (typeof EXIT_CODES)[keyof typeof EXIT_CODES];

// Storage provider interface (matches console/src/core/types/storage.ts)
export interface IStorageProvider {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  clear?(): Promise<void>;
}

export type { ICryptoProvider } from '@rediacc/shared/encryption';
