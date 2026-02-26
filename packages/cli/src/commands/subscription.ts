import { execSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askText } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';

// Paths
const CONFIG_DIR = join(homedir(), '.config', 'rediacc');
const TOKEN_FILE = join(CONFIG_DIR, 'api-token.json');
const LICENSE_DIR = '/var/lib/rediacc/license';
const LICENSE_FILE = join(LICENSE_DIR, 'license.json');

interface StoredToken {
  token: string;
  serverUrl: string;
  subscriptionId?: string;
}

export function registerSubscriptionCommands(program: Command): void {
  const sub = program.command('subscription').description(t('commands.subscription.description'));

  // subscription login
  sub
    .command('login')
    .description(t('commands.subscription.login.description'))
    .option('-t, --token <token>', t('options.apiToken'))
    .option('--server <url>', t('options.serverUrl'), 'https://account.rediacc.com')
    .action(async (options) => {
      try {
        const token =
          options.token ??
          (await askText(t('commands.subscription.login.tokenPrompt'), {
            validate: (input) =>
              input.startsWith('rdt_') || t('commands.subscription.login.tokenInvalid'),
          }));

        const serverUrl = options.server;

        // Validate token by calling license status
        const status = await withSpinner(
          t('commands.subscription.login.validating'),
          async () => {
            const resp = await fetch(`${serverUrl}/account/api/v1/licenses/status`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (!resp.ok) {
              const body = await resp.json().catch(() => ({ error: 'Unknown error' }));
              throw new ValidationError(
                (body as { error?: string }).error ?? `HTTP ${resp.status}`
              );
            }
            return resp.json();
          },
          t('commands.subscription.login.validated')
        );

        // Save token
        mkdirSync(CONFIG_DIR, { recursive: true, mode: 0o700 });
        const stored: StoredToken = {
          token,
          serverUrl,
          subscriptionId: (status as { subscriptionId?: string }).subscriptionId,
        };
        writeFileSync(TOKEN_FILE, JSON.stringify(stored, null, 2), {
          mode: 0o600,
        });

        const s = status as {
          planCode?: string;
          activeMachineCount?: number;
          maxMachines?: number;
        };
        outputService.success(t('commands.subscription.login.success'));
        outputService.info(
          t('commands.subscription.login.plan', {
            plan: s.planCode ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_PLAN,
          })
        );
        outputService.info(
          t('commands.subscription.login.machines', {
            active: s.activeMachineCount ?? 0,
            max: s.maxMachines ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_QUOTA,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // subscription activate
  sub
    .command('activate')
    .description(t('commands.subscription.activate.description'))
    .action(async () => {
      try {
        const { token, serverUrl } = loadToken();
        const machineId = getMachineId();

        const result = await withSpinner(
          t('commands.subscription.activate.activating'),
          async () => {
            const resp = await fetch(`${serverUrl}/account/api/v1/licenses/issue`, {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ machineId }),
            });
            if (!resp.ok) {
              const body = await resp.json().catch(() => ({ error: 'Unknown error' }));
              throw new ValidationError(
                (body as { error?: string }).error ?? `HTTP ${resp.status}`
              );
            }
            return resp.json();
          },
          t('commands.subscription.activate.activated')
        );

        // Save license file (requires sudo for /var/lib/rediacc)
        const license = (result as { license: unknown }).license;
        saveLicenseFile(license);

        outputService.success(t('commands.subscription.activate.installed'));
        outputService.info(
          t('commands.subscription.activate.licenseFile', {
            path: LICENSE_FILE,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // subscription status
  sub
    .command('status')
    .description(t('commands.subscription.status.description'))
    .action(async () => {
      try {
        displayLocalLicense();
        await displayRemoteStatus();
      } catch (error) {
        handleError(error);
      }
    });

  // subscription refresh
  sub
    .command('refresh')
    .description(t('commands.subscription.refresh.description'))
    .action(async () => {
      try {
        const { token, serverUrl } = loadToken();
        const machineId = getMachineId();

        const result = await withSpinner(
          t('commands.subscription.refresh.refreshing'),
          async () => {
            const resp = await fetch(`${serverUrl}/account/api/v1/licenses/issue`, {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ machineId }),
            });
            if (!resp.ok) {
              const body = await resp.json().catch(() => ({ error: 'Unknown error' }));
              throw new ValidationError(
                (body as { error?: string }).error ?? `HTTP ${resp.status}`
              );
            }
            return resp.json();
          },
          t('commands.subscription.refresh.refreshed')
        );

        const license = (result as { license: unknown }).license;
        saveLicenseFile(license);

        outputService.success(t('commands.subscription.refresh.success'));
      } catch (error) {
        handleError(error);
      }
    });
}

function displayLocalLicense(): void {
  if (!existsSync(LICENSE_FILE)) {
    outputService.info(t('commands.subscription.status.noLicense'));
    return;
  }

  outputService.info(t('commands.subscription.status.localLicense'));
  try {
    const data = JSON.parse(readFileSync(LICENSE_FILE, 'utf-8'));
    const payload = JSON.parse(Buffer.from(data.payload, 'base64').toString('utf-8'));
    outputService.info(t('commands.subscription.status.plan', { plan: payload.planCode }));
    outputService.info(t('commands.subscription.status.statusLabel', { status: payload.status }));
    outputService.info(
      t('commands.subscription.status.machine', {
        machineId: payload.machineId,
      })
    );
    outputService.info(t('commands.subscription.status.issued', { issuedAt: payload.issuedAt }));
    outputService.info(
      t('commands.subscription.status.expires', {
        expiresAt: payload.expiresAt,
      })
    );
    outputService.info(
      t('commands.subscription.status.sequence', {
        sequenceNumber: payload.sequenceNumber,
      })
    );

    const expiresAt = new Date(payload.expiresAt);
    if (expiresAt < new Date()) {
      outputService.warn(t('commands.subscription.status.expired'));
    } else {
      const mins = Math.round((expiresAt.getTime() - Date.now()) / 60000);
      outputService.success(t('commands.subscription.status.valid', { mins }));
    }
  } catch {
    outputService.warn(t('commands.subscription.status.parseFailed'));
  }
}

async function displayRemoteStatus(): Promise<void> {
  if (!existsSync(TOKEN_FILE)) return;

  const { token, serverUrl } = loadToken();
  try {
    const resp = await fetch(`${serverUrl}/account/api/v1/licenses/status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;

    const status = (await resp.json()) as {
      planCode: string;
      status: string;
      activeMachineCount: number;
      maxMachines: number;
      machines: { machineId: string; lastSeenAt: string }[];
    };

    outputService.info(t('commands.subscription.status.remote'));
    outputService.info(t('commands.subscription.status.remotePlan', { plan: status.planCode }));
    outputService.info(t('commands.subscription.status.remoteStatus', { status: status.status }));
    outputService.info(
      t('commands.subscription.status.remoteMachines', {
        active: status.activeMachineCount,
        max: status.maxMachines,
      })
    );
    for (const m of status.machines) {
      outputService.info(
        t('commands.subscription.status.remoteMachine', {
          id: m.machineId.slice(0, 12),
          lastSeen: m.lastSeenAt,
        })
      );
    }
  } catch {
    // Remote status is optional
  }
}

function loadToken(): StoredToken {
  if (!existsSync(TOKEN_FILE)) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  return JSON.parse(readFileSync(TOKEN_FILE, 'utf-8'));
}

function getMachineId(): string {
  try {
    // Try renet machine-id first
    const result = execSync('renet machine-id', {
      encoding: 'utf-8',
      timeout: 5000,
    });
    return result.trim();
  } catch {
    // Fallback: read /etc/machine-id
    try {
      return readFileSync('/etc/machine-id', 'utf-8').trim();
    } catch {
      throw new ValidationError(t('errors.subscription.noMachineId'));
    }
  }
}

function saveLicenseFile(license: unknown): void {
  try {
    mkdirSync(LICENSE_DIR, { recursive: true, mode: 0o755 });
    writeFileSync(LICENSE_FILE, JSON.stringify(license, null, 2), {
      mode: 0o640,
    });
  } catch {
    // If direct write fails (no root), try with sudo
    try {
      const json = JSON.stringify(license, null, 2);
      execSync(`sudo mkdir -p ${LICENSE_DIR} && sudo tee ${LICENSE_FILE} > /dev/null`, {
        input: json,
        encoding: 'utf-8',
        timeout: 10000,
      });
      execSync(`sudo chmod 640 ${LICENSE_FILE}`, { timeout: 5000 });
    } catch {
      throw new ValidationError(t('errors.subscription.writeFailed', { path: LICENSE_DIR }));
    }
  }
}

/**
 * Check if the local license needs refresh (>50 minutes old).
 * Called as a background hook from other commands.
 */
export async function autoRefreshLicense(): Promise<void> {
  if (!existsSync(LICENSE_FILE) || !existsSync(TOKEN_FILE)) return;

  try {
    const data = JSON.parse(readFileSync(LICENSE_FILE, 'utf-8'));
    const payload = JSON.parse(Buffer.from(data.payload, 'base64').toString('utf-8'));
    const issuedAt = new Date(payload.issuedAt);
    const ageMs = Date.now() - issuedAt.getTime();
    const fiftyMinutes = 50 * 60 * 1000;

    if (ageMs < fiftyMinutes) return; // Still fresh

    const { token, serverUrl } = loadToken();
    const machineId = getMachineId();

    const resp = await fetch(`${serverUrl}/account/api/v1/licenses/issue`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ machineId }),
    });

    if (resp.ok) {
      const result = (await resp.json()) as { license: unknown };
      saveLicenseFile(result.license);
    }
  } catch {
    // Auto-refresh is best-effort, never blocks the user
  }
}
