/**
 * Backup credentials env-file helpers.
 *
 * Systemd units are world-readable, so OAuth tokens and API keys cannot
 * live in ExecStart=. Instead we write them to /etc/rediacc/backup-*.env
 * at mode 0600 and reference the file via EnvironmentFile=. Rclone then
 * picks them up natively via its RCLONE_<OPTION> env-var convention.
 */

import type { SFTPClient } from '../shared-desktop/sftp/index.js';

export interface EnvFileWriteOptions {
  debug?: boolean;
}

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

/** `umask 077 && cat > file` creates the env file atomically at mode 0600. */
export async function writeEnvFile(
  sftp: SFTPClient,
  strategyName: string,
  envFileContent: string,
  options: EnvFileWriteOptions
): Promise<void> {
  const mkdir = await sftp.execStreaming('sudo install -d -m 0755 -o root -g root /etc/rediacc', {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (mkdir !== 0) {
    throw new Error(`Failed to create /etc/rediacc (exit ${mkdir})`);
  }

  const write = await sftp.execStreaming(
    `sudo sh -c 'umask 077 && cat > ${envFilePath(strategyName)}'`,
    {
      stdin: envFileContent,
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => {
        process.stderr.write(data);
      },
    }
  );
  if (write !== 0) {
    throw new Error(`Failed to write env file for strategy "${strategyName}" (exit ${write})`);
  }
}
