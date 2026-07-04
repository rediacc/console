/**
 * Backup credentials env-file helpers.
 *
 * Systemd units are world-readable, so OAuth tokens and API keys cannot
 * live in ExecStart=. Instead we write them to /etc/rediacc/backup-*.env
 * at mode 0600 and reference the file via EnvironmentFile=. Rclone then
 * picks them up natively via its RCLONE_<OPTION> env-var convention.
 */

/** Rclone's native env-var naming: `--onedrive-token` -> `RCLONE_ONEDRIVE_TOKEN`. */
export function rcloneEnvName(flagKey: string): string {
  return `RCLONE_${flagKey.replaceAll('-', '_').toUpperCase()}`;
}

/** Path of the per-strategy EnvironmentFile= sidecar. */
export function envFilePath(strategyName: string): string {
  return `/etc/rediacc/backup-${strategyName}.env`;
}

/** Merge per-destination env-vars, throwing on same-key/different-value conflicts. */
export function mergeEnvVars(into: Record<string, string>, add: Record<string, string>): void {
  for (const [key, value] of Object.entries(add)) {
    if (key in into && into[key] !== value) {
      throw new Error(
        `Conflicting env var "${key}" across destinations: one systemd unit cannot carry two ` +
          `values for the same key. Split into separate strategies or align the credentials.`
      );
    }
    into[key] = value;
  }
}

/**
 * EnvironmentFile= body: every value is double-quoted and C-escaped so
 * JSON tokens round-trip through systemd's parser untouched.
 */
export function generateEnvFile(envVars: Record<string, string>): string {
  const escape = (v: string): string => v.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  const lines = Object.entries(envVars).map(([k, v]) => `${k}="${escape(v)}"`);
  return lines.length > 0 ? `${lines.join('\n')}\n` : '';
}
