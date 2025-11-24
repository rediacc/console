// CLI-specific types

export interface CliConfig {
  version: number
  apiUrl: string
  token?: string
  masterPassword?: string
  context: CliContext
  output: OutputConfig
  aliases: Record<string, string>
}

export interface CliContext {
  team?: string
  region?: string
}

export interface OutputConfig {
  format: OutputFormat
  color: boolean
}

export type OutputFormat = 'table' | 'json' | 'yaml' | 'csv'

export interface CommandOptions {
  team?: string
  region?: string
  bridge?: string
  machine?: string
  output?: OutputFormat
  force?: boolean
  watch?: boolean
  [key: string]: unknown
}

export interface ApiCallOptions {
  endpoint: string
  data?: Record<string, unknown>
  headers?: Record<string, string>
}

// Exit codes
export const EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGUMENTS: 2,
  AUTH_REQUIRED: 3,
  PERMISSION_DENIED: 4,
  NOT_FOUND: 5,
  NETWORK_ERROR: 6,
} as const

export type ExitCode = typeof EXIT_CODES[keyof typeof EXIT_CODES]

// Storage provider interface (matches console/src/core/types/storage.ts)
export interface IStorageProvider {
  getItem(key: string): Promise<string | null>
  setItem(key: string, value: string): Promise<void>
  removeItem(key: string): Promise<void>
  clear?(): Promise<void>
}

// Crypto provider interface (matches console/src/core/types/crypto.ts)
export interface ICryptoProvider {
  encrypt(data: string, password: string): Promise<string>
  decrypt(data: string, password: string): Promise<string>
  deriveKey(password: string, salt: Uint8Array): Promise<unknown>
  generateHash(data: string): Promise<string>
}
