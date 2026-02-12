/**
 * Rclone configuration file parser and provider mapping.
 *
 * Parses INI-style rclone .conf files and maps them to internal
 * storage vault format used by QueueVaultBuilder.
 *
 * Extracted from packages/web RcloneImportWizard for shared use
 * by both web app and CLI.
 */

// ============================================================================
// Types
// ============================================================================

export type RcloneConfigFieldValue =
  | string
  | number
  | boolean
  | Record<string, unknown>
  | undefined;

export type RcloneConfigFields = {
  [key: string]: RcloneConfigFieldValue;
  type?: string;
};

export interface RcloneConfig {
  name: string;
  type: string;
  config: RcloneConfigFields;
}

// ============================================================================
// Constants
// ============================================================================

/** Maps rclone backend type names to internal provider names. */
export const PROVIDER_MAPPING: Record<string, string> = {
  drive: 'drive',
  onedrive: 'onedrive',
  s3: 's3',
  b2: 'b2',
  mega: 'mega',
  dropbox: 'dropbox',
  box: 'box',
  azureblob: 'azureblob',
  swift: 'swift',
  webdav: 'webdav',
  ftp: 'ftp',
  sftp: 'sftp',
};

// ============================================================================
// Internal Helpers
// ============================================================================

function isSkippableLine(line: string): boolean {
  const trimmed = line.trim();
  return !trimmed || trimmed.startsWith('#') || trimmed.startsWith(';');
}

function parseKeyValuePair(line: string): [string, string | Record<string, unknown>] | null {
  const kvMatch = /^([^=]+)=(.*)$/.exec(line);
  if (!kvMatch) return null;

  const key = kvMatch[1].trim();
  const value = kvMatch[2].trim();

  try {
    return [key, JSON.parse(value) as Record<string, unknown>];
  } catch {
    return [key, value];
  }
}

function saveCurrentSection(
  configs: RcloneConfig[],
  section: string | null,
  config: RcloneConfigFields
): void {
  if (section && config.type) {
    configs.push({
      name: section,
      type: config.type as string,
      config: { ...config },
    });
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Parse an INI-style rclone configuration file.
 * Returns an array of named configs, each with a type and key-value fields.
 */
export function parseRcloneConfig(content: string): RcloneConfig[] {
  const configs: RcloneConfig[] = [];
  const lines = content.split('\n');
  let currentSection: string | null = null;
  let currentConfig: RcloneConfigFields = {};

  for (const line of lines) {
    if (isSkippableLine(line)) continue;

    const trimmedLine = line.trim();
    const sectionMatch = /^\[(.+)\]$/.exec(trimmedLine);

    if (sectionMatch) {
      saveCurrentSection(configs, currentSection, currentConfig);
      currentSection = sectionMatch[1];
      currentConfig = {};
      continue;
    }

    if (currentSection) {
      const parsed = parseKeyValuePair(trimmedLine);
      if (parsed) {
        currentConfig[parsed[0]] = parsed[1];
      }
    }
  }

  saveCurrentSection(configs, currentSection, currentConfig);
  return configs;
}

/**
 * Process a config value, parsing JSON tokens where appropriate.
 * Only parses values for keys named "token" or ending with "_token".
 */
export function processConfigValue(
  key: string,
  value: RcloneConfigFieldValue
): RcloneConfigFieldValue {
  if (typeof value !== 'string') return value;
  if (!(key === 'token' || key.endsWith('_token'))) return value;
  if (!value.startsWith('{')) return value;

  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

/**
 * Map a parsed rclone config to the internal storage vault format.
 * Returns null if the rclone type is not in PROVIDER_MAPPING.
 *
 * The returned object has a `provider` field and all config fields
 * (with token values parsed as JSON objects).
 */
export function mapRcloneToStorageProvider(
  rcloneConfig: RcloneConfig
): Record<string, unknown> | null {
  const { type, config } = rcloneConfig;
  const provider = PROVIDER_MAPPING[type];
  if (!provider) return null;

  const storageVault: Record<string, unknown> = { provider };

  for (const [key, value] of Object.entries(config)) {
    if (key === 'type') continue; // Skip: mapped via PROVIDER_MAPPING
    // Rclone's "provider" field (e.g. "DigitalOcean" for S3) is the sub-provider,
    // distinct from our mapped provider type (e.g. "s3"). Store it as "sub_provider"
    // so buildRcloneArgs can output it as --{backend}-provider={value}.
    if (key === 'provider') {
      if (value && value !== provider) {
        storageVault.sub_provider = value;
      }
      continue;
    }
    storageVault[key] = processConfigValue(key, value);
  }

  return storageVault;
}
