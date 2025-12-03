export type VaultData = Record<string, unknown>

export interface MachineContextData extends VaultData {
  IP?: string
  USER?: string
  PORT?: number | string
  DATASTORE?: string
  HOST_ENTRY?: string
}

export interface StorageSystemContextData extends VaultData {
  RCLONE_REDIACC_BACKEND: string
  RCLONE_REDIACC_FOLDER?: unknown
  RCLONE_PARAMETERS?: unknown
}

export interface GeneralSettings extends VaultData {
  TEAM_NAME?: string
  MACHINE_NAME?: string
  COMPANY_ID?: string
  SYSTEM_API_URL?: string
  SSH_PRIVATE_KEY?: string
  SSH_PUBLIC_KEY?: string
}

export interface VaultContextData extends VaultData {
  GENERAL_SETTINGS: GeneralSettings
  MACHINES?: Record<string, MachineContextData>
  STORAGE_SYSTEMS?: Record<string, StorageSystemContextData>
  PLUGINS?: VaultData
  company?: VaultData
  repo?: VaultData
  storage?: VaultData
  bridge?: VaultData
  plugins?: VaultData
}
