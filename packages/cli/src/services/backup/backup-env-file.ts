/**
 * Backup credentials env-file helpers.
 *
 * Systemd units are world-readable, so OAuth tokens and API keys cannot
 * live in ExecStart=. Instead we write them to /etc/rediacc/backup-*.env
 * at mode 0600 and reference the file via EnvironmentFile=. Rclone then
 * picks them up natively via its RCLONE_<OPTION> env-var convention.
 */

/** Path of the per-strategy EnvironmentFile= sidecar. */
export function envFilePath(strategyName: string): string {
  return `/etc/rediacc/backup-${strategyName}.env`;
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
