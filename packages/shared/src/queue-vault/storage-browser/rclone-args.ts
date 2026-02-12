/**
 * Build rclone CLI arguments from storage vault content.
 *
 * Converts the provider credentials stored in the vault to the
 * inline remote syntax + parameter flags that rclone expects.
 *
 * Mirrors the logic in renet's Go `appendStorageConfig()` (backup.go)
 * and `listFromStorage()` (backup_list.go) but in TypeScript.
 */

/** Rclone command-line arguments for an inline remote. */
export interface RcloneArgs {
  /** Inline remote path, e.g. `:s3:mybucket/path` or `:drive:path` */
  remote: string;
  /** Parameter flags, e.g. `["--s3-access-key-id=AKIA...", "--s3-endpoint=..."]` */
  params: string[];
}

/** Fields extracted as top-level remote path components (not passed as flags). */
const PATH_FIELDS = new Set(['provider', 'bucket', 'folder']);

/** Fields that use a dedicated `--{backend}-{key}=` flag. */
const DEDICATED_FIELDS = new Set(['region']);

/**
 * Fields that map to a different rclone flag name.
 * e.g. `sub_provider` → `--{backend}-provider` (rclone S3 sub-provider like "DigitalOcean").
 */
const RENAMED_FIELDS: Record<string, string> = {
  sub_provider: 'provider',
};

function buildCredentialFlags(vaultContent: Record<string, unknown>, backend: string): string[] {
  const params: string[] = [];
  for (const [key, value] of Object.entries(vaultContent)) {
    if (PATH_FIELDS.has(key) || DEDICATED_FIELDS.has(key)) continue;
    if (value === undefined || value === null || value === '') continue;
    const rcloneKey = RENAMED_FIELDS[key] ?? key;
    const flag = `--${backend}-${rcloneKey.replaceAll('_', '-')}`;
    const flagValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
    params.push(`${flag}=${flagValue}`);
  }
  return params;
}

/**
 * Build rclone CLI arguments from storage vault content.
 *
 * @param vaultContent - The storage vault content (provider, credentials, etc.)
 * @param subPath - Optional subdirectory path to append
 * @returns Inline remote string and parameter flags
 */
export function buildRcloneArgs(
  vaultContent: Record<string, unknown>,
  subPath?: string
): RcloneArgs {
  const backend = String(vaultContent.provider ?? '');
  const bucket = vaultContent.bucket ? String(vaultContent.bucket) : '';
  const folder = vaultContent.folder ? String(vaultContent.folder) : '';

  const pathSegments = [bucket, folder, subPath ?? ''].filter(Boolean);
  const remote = `:${backend}:${pathSegments.join('/')}`;

  const params: string[] = [];

  if (vaultContent.region) {
    params.push(`--${backend}-region=${String(vaultContent.region)}`);
  }

  params.push(...buildCredentialFlags(vaultContent, backend));

  if (backend === 's3') {
    params.push('--s3-force-path-style=true');
  }

  return { remote, params };
}
