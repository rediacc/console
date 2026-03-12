import { t } from '../i18n/index.js';
import { ValidationError } from '../utils/errors.js';
import { outputService } from './output.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  saveStoredSubscriptionToken,
  type StoredSubscriptionToken,
} from './subscription-auth.js';

interface LicenseStatusResponse {
  subscriptionId?: string;
  orgId?: string;
  orgName?: string;
  planCode?: string;
  activeMachineCount?: number;
  maxMachines?: number;
  teamId?: string;
  teamName?: string;
}

export interface DeviceCodeAuthorizationResult {
  storedToken: StoredSubscriptionToken;
  status: LicenseStatusResponse;
}

interface DeviceCodeLoginOptions {
  interactive?: boolean;
  announceIntro?: boolean;
  teamName?: string;
}

export async function authorizeSubscriptionViaDeviceCode(
  preferredServerUrl?: string,
  options: DeviceCodeLoginOptions = {}
): Promise<DeviceCodeAuthorizationResult> {
  const serverUrl = getSubscriptionServerUrl(preferredServerUrl);
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

  if (options.announceIntro) {
    outputService.warn(t('commands.subscription.login.waitingApproval'));
  }
  outputService.info('');
  outputService.info(t('commands.subscription.login.openBrowser'));
  outputService.info(`  ${verificationUrl}`);
  outputService.info('');

  const interactive = options.interactive ?? (process.stdin.isTTY && process.stdout.isTTY);
  if (!interactive) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }

  await tryOpenBrowser(verificationUrl);
  outputService.info(t('commands.subscription.login.polling'));

  const token = await pollForDeviceCodeToken(serverUrl, deviceCode, interval, expiresIn);
  const status = await fetchLicenseStatus(serverUrl, token);
  const storedToken: StoredSubscriptionToken = {
    token,
    serverUrl,
    subscriptionId: status.subscriptionId,
    orgId: status.orgId,
    orgName: status.orgName,
    teamId: status.teamId,
    teamName: status.teamName ?? options.teamName,
  };
  const mismatch = getSubscriptionScopeMismatch(storedToken, options.teamName);
  if (mismatch) {
    throw new ValidationError(mismatch);
  }
  saveStoredSubscriptionToken(storedToken);

  return { storedToken, status };
}

async function pollForDeviceCodeToken(
  serverUrl: string,
  deviceCode: string,
  interval: number,
  expiresIn: number
): Promise<string> {
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

async function fetchLicenseStatus(
  serverUrl: string,
  token: string
): Promise<LicenseStatusResponse> {
  const resp = await fetch(`${serverUrl}/account/api/v1/licenses/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: 'Unknown error' }));
    throw new ValidationError((body as { error?: string }).error ?? `HTTP ${resp.status}`);
  }
  return (await resp.json()) as LicenseStatusResponse;
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
