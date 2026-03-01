/**
 * Remote license auto-activation service.
 *
 * Automatically ensures remote machines have a valid floating license
 * before any machine-targeting operation. Called from pre-flight hooks
 * in local-executor.ts and machine-status.ts.
 *
 * The CLI fetches from the account API and delivers both the machine
 * license and signed subscription blob to the remote via SSH/SFTP,
 * since renet cannot make HTTP calls.
 */

import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS } from '@rediacc/shared/config';
import type { MachineConfig } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.config', 'rediacc');
const TOKEN_FILE = join(CONFIG_DIR, 'api-token.json');

const LICENSE_DIR = '/var/lib/rediacc/license';
const LICENSE_FILE = `${LICENSE_DIR}/license.json`;
const SUBSCRIPTION_FILE = `${LICENSE_DIR}/subscription.json`;

/** Cache: "host:port" -> timestamp of last successful license check */
const licenseCache = new Map<string, number>();
const LICENSE_CACHE_TTL_MS = 50 * 60 * 1000; // 50 minutes

interface StoredToken {
  token: string;
  serverUrl: string;
}

function isLicenseExpired(content: string): boolean {
  if (!content) return true;
  try {
    const data = JSON.parse(content);
    const payload = JSON.parse(Buffer.from(data.payload, 'base64').toString('utf-8'));
    const ageMs = Date.now() - new Date(payload.issuedAt).getTime();
    return ageMs >= LICENSE_CACHE_TTL_MS;
  } catch {
    return true;
  }
}

function loadToken(): StoredToken | null {
  if (!existsSync(TOKEN_FILE)) return null;
  try {
    return JSON.parse(readFileSync(TOKEN_FILE, 'utf-8'));
  } catch {
    return null;
  }
}

/**
 * Ensure the remote machine has a valid floating license.
 *
 * - Silent on failure (API unreachable, no token, etc.)
 * - Uses 50-minute in-memory cache to avoid SSH round-trips
 * - Delivers both license.json and subscription.json to remote
 * - Auto-activates new machines (no separate activate step)
 */
export async function ensureMachineLicense(
  machine: MachineConfig,
  sshPrivateKey: string
): Promise<void> {
  const stored = loadToken();
  if (!stored) return;

  const cacheKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
  const cached = licenseCache.get(cacheKey);
  if (cached && Date.now() - cached < LICENSE_CACHE_TTL_MS) return;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();

    // Check existing license on remote
    const content = await sftp.exec(`sudo cat ${LICENSE_FILE} 2>/dev/null || echo ""`);

    const needsActivation = isLicenseExpired(content.trim());

    if (needsActivation) {
      // Get remote machine ID
      const machineId = (
        await sftp.exec('sudo renet machine-id 2>/dev/null || cat /etc/machine-id')
      ).trim();

      if (!machineId) {
        licenseCache.set(cacheKey, Date.now());
        return;
      }

      const resp = await fetch(`${stored.serverUrl}/account/api/v1/licenses/issue`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${stored.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ machineId }),
      });

      if (resp.ok) {
        const { license, signedBlob } = (await resp.json()) as {
          license: unknown;
          signedBlob: unknown;
        };

        await sftp.exec(`sudo mkdir -p ${LICENSE_DIR}`);
        await sftp.execStreaming(`sudo tee ${LICENSE_FILE} > /dev/null`, {
          stdin: JSON.stringify(license, null, 2),
        });
        await sftp.execStreaming(`sudo tee ${SUBSCRIPTION_FILE} > /dev/null`, {
          stdin: JSON.stringify(signedBlob, null, 2),
        });
        await sftp.exec(`sudo chmod 640 ${LICENSE_FILE} ${SUBSCRIPTION_FILE}`);
      }
    }

    licenseCache.set(cacheKey, Date.now());
  } catch {
    // License check is best-effort, never blocks the user
  } finally {
    sftp.close();
  }
}

/** Clear the license cache (used for force-refresh). */
export function clearLicenseCache(): void {
  licenseCache.clear();
}

/** Clear cache for a specific machine. */
export function clearMachineLicenseCache(machine: MachineConfig): void {
  const cacheKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
  licenseCache.delete(cacheKey);
}
