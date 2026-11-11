import { t } from '../../i18n/index.js';
import { authorizationExpired, CliExitError } from '../../utils/cli-exit-error.js';
import { ValidationError } from '../../utils/errors.js';
import { outputService } from '../core/output.js';
import { accountServerFetch } from './account-client.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  type StoredSubscriptionToken,
  saveStoredSubscriptionToken,
} from './subscription-auth.js';

interface LicenseStatusResponse {
  subscriptionId?: string;
  orgId?: string;
  orgName?: string;
  planCode?: string;
  activeMachineCount?: number;
  maxMachines?: number;
  /** Active machines soft-claimed beyond maxMachines by a renewal. */
  overLimitCount?: number;
  teamId?: string;
  teamName?: string;
}

/** The Terms standing the device-code claim reports: the accepted version (null when none), the latest version and where to read it. */
export interface ClaimTerms {
  accepted: string | null;
  latest: string;
  url: string;
  /** The portal page where the account accepts; absent from an older server. */
  acceptUrl?: string;
}

export interface DeviceCodeAuthorizationResult {
  storedToken: StoredSubscriptionToken;
  status: LicenseStatusResponse;
  /** From the claim response; absent when the server sent none. */
  terms?: ClaimTerms;
}

interface PolledClaim {
  token: string;
  terms?: ClaimTerms;
}

interface DeviceCodeLoginOptions {
  interactive?: boolean;
  announceIntro?: boolean;
  teamName?: string;
  /** Registration handoff: pre-fills the portal's sign-up form. Only a pre-fill, never a verified address. */
  email?: string;
}

/** The verification URL with the registration email pre-filled (URL-encoded); the portal never trusts it as verified. */
export function withEmailPrefill(verificationUrl: string, email: string | undefined): string {
  if (!email) return verificationUrl;
  const url = new URL(verificationUrl);
  url.searchParams.set('email', email);
  return url.toString();
}

export async function authorizeSubscriptionViaDeviceCode(
  preferredServerUrl?: string,
  options: DeviceCodeLoginOptions = {}
): Promise<DeviceCodeAuthorizationResult> {
  const serverUrl = getSubscriptionServerUrl(preferredServerUrl);

  const initResult = await accountServerFetch<{
    deviceCode: string;
    verificationUrl: string;
    interval: number;
    expiresIn: number;
  }>('/account/api/v1/device-codes', {
    method: 'POST',
    noAuth: true,
    serverUrl,
  });

  const { deviceCode, verificationUrl, interval, expiresIn } = initResult;

  if (options.announceIntro) {
    outputService.warn(t('commands.subscription.login.waitingApproval'));
  }
  outputService.info('');
  outputService.info(t('commands.subscription.login.openBrowser'));
  outputService.info(`  ${withEmailPrefill(verificationUrl, options.email)}`);
  outputService.info('');

  const interactive = options.interactive ?? (process.stdin.isTTY && process.stdout.isTTY);
  if (!interactive) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }

  outputService.info(t('commands.subscription.login.polling'));

  const { token, terms } = await pollForDeviceCodeToken(serverUrl, deviceCode, interval, expiresIn);
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

  return { storedToken, status, terms };
}

/** Single poll attempt. Returns token string on success, null to continue polling. */
async function attemptDeviceCodePoll(
  serverUrl: string,
  deviceCode: string
): Promise<PolledClaim | null> {
  try {
    const result = await accountServerFetch<{ status: string; token?: string; terms?: ClaimTerms }>(
      `/account/api/v1/device-codes/${deviceCode}`,
      { noAuth: true, serverUrl }
    );
    if (result.status === 'complete' && result.token) {
      return { token: result.token, terms: result.terms };
    }
    if (result.status === 'expired') {
      throw authorizationExpired(
        t('commands.subscription.login.expired'),
        'rdc subscription login'
      );
    }
  } catch (error) {
    if (error instanceof ValidationError || error instanceof CliExitError) throw error;
    // Non-OK responses during polling are expected (pending state)
  }
  return null;
}

async function pollForDeviceCodeToken(
  serverUrl: string,
  deviceCode: string,
  interval: number,
  expiresIn: number
): Promise<PolledClaim> {
  const pollInterval = interval * 1000;
  const maxAttempts = Math.ceil(expiresIn / interval);

  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));
    const claim = await attemptDeviceCodePoll(serverUrl, deviceCode);
    if (claim) return claim;
  }

  throw authorizationExpired(t('commands.subscription.login.expired'), 'rdc subscription login');
}

function fetchLicenseStatus(serverUrl: string, token: string): Promise<LicenseStatusResponse> {
  return accountServerFetch<LicenseStatusResponse>('/account/api/v1/licenses/status', {
    token,
    serverUrl,
  });
}
