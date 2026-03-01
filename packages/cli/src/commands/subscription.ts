import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { Command } from 'commander';
import { DEFAULTS, SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { clearMachineLicenseCache, ensureMachineLicense } from '../services/license.js';
import { outputService } from '../services/output.js';
import { readSSHKey } from '../services/renet-execution.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

// Paths
const CONFIG_DIR = join(homedir(), '.config', 'rediacc');
const TOKEN_FILE = join(CONFIG_DIR, 'api-token.json');

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
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        const serverUrl =
          options.server ??
          process.env.REDIACC_ACCOUNT_SERVER ??
          SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL;

        let token: string;

        if (options.token) {
          // Direct token mode (fallback)
          token = options.token;
        } else {
          // Device code flow (default)
          token = await deviceCodeLogin(serverUrl);
        }

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

  // subscription status
  sub
    .command('status')
    .description(t('commands.subscription.status.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        // Show remote account status
        await displayRemoteStatus();

        // If machine specified, show remote machine license
        if (options.machine) {
          await displayMachineLicense(options.machine);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // subscription refresh
  sub
    .command('refresh')
    .description(t('commands.subscription.refresh.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await withSpinner(
          t('commands.subscription.refresh.refreshing'),
          async () => {
            const localConfig = await configService.getLocalConfig();
            const machine = await configService.getLocalMachine(options.machine);
            const sshPrivateKey =
              localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

            // Clear cache to force re-issue
            clearMachineLicenseCache(machine);
            await ensureMachineLicense(machine, sshPrivateKey);
          },
          t('commands.subscription.refresh.refreshed')
        );

        outputService.success(t('commands.subscription.refresh.success'));
      } catch (error) {
        handleError(error);
      }
    });
}

async function deviceCodeLogin(serverUrl: string): Promise<string> {
  // 1. Request a device code
  const initResp = await fetch(`${serverUrl}/account/api/v1/device-codes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!initResp.ok) {
    throw new ValidationError(t('commands.subscription.login.initFailed'));
  }

  const { deviceCode, verificationUrl, interval, expiresIn } = (await initResp.json()) as {
    deviceCode: string;
    verificationUrl: string;
    interval: number;
    expiresIn: number;
  };

  // 2. Print URL and try to open browser
  outputService.info('');
  outputService.info(t('commands.subscription.login.openBrowser'));
  outputService.info(`  ${verificationUrl}`);
  outputService.info('');
  await tryOpenBrowser(verificationUrl);

  // 3. Poll for completion
  outputService.info(t('commands.subscription.login.polling'));
  const pollInterval = interval * 1000;
  const maxAttempts = Math.ceil(expiresIn / interval);

  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));

    const pollResp = await fetch(`${serverUrl}/account/api/v1/device-codes/${deviceCode}`);
    if (!pollResp.ok) continue;

    const result = (await pollResp.json()) as {
      status: string;
      token?: string;
    };

    if (result.status === 'complete' && result.token) {
      return result.token;
    }
    if (result.status === 'expired') {
      throw new ValidationError(t('commands.subscription.login.expired'));
    }
  }

  throw new ValidationError(t('commands.subscription.login.expired'));
}

async function displayRemoteStatus(): Promise<void> {
  if (!existsSync(TOKEN_FILE)) {
    outputService.info(t('errors.subscription.notLoggedIn'));
    return;
  }

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

async function displayMachineLicense(machineName: string): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const content = await sftp.exec(
      'sudo cat /var/lib/rediacc/license/license.json 2>/dev/null || echo ""'
    );

    if (!content.trim()) {
      outputService.info(t('commands.subscription.status.noLicense'));
      return;
    }

    const data = JSON.parse(content.trim());
    const payload = JSON.parse(Buffer.from(data.payload, 'base64').toString('utf-8'));

    outputService.info(`\n${t('commands.subscription.status.localLicense')} (${machineName})`);
    outputService.info(t('commands.subscription.status.plan', { plan: payload.planCode }));
    outputService.info(t('commands.subscription.status.statusLabel', { status: payload.status }));
    outputService.info(t('commands.subscription.status.machine', { machineId: payload.machineId }));
    outputService.info(t('commands.subscription.status.issued', { issuedAt: payload.issuedAt }));
    outputService.info(t('commands.subscription.status.expires', { expiresAt: payload.expiresAt }));
    outputService.info(
      t('commands.subscription.status.sequence', { sequenceNumber: payload.sequenceNumber })
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
  } finally {
    sftp.close();
  }
}

async function tryOpenBrowser(url: string): Promise<void> {
  try {
    const { execFile } = await import('node:child_process');
    const cmd = process.platform === 'darwin' ? 'open' : 'xdg-open';
    execFile(cmd, [url]);
  } catch {
    outputService.info(t('commands.subscription.login.browserFailed'));
  }
}

function loadToken(): StoredToken {
  if (!existsSync(TOKEN_FILE)) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  return JSON.parse(readFileSync(TOKEN_FILE, 'utf-8'));
}
