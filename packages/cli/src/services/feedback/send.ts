/**
 * `rdc feedback report`: build the payload from a redacted ring entry, choose
 * the credential (stored API token, else an installed FREE licence blob, else a
 * refusal naming both routes) and send it to `POST /feedback`.
 */
import { createHash } from 'node:crypto';
import { arch, platform } from 'node:os';
import {
  FEEDBACK_LIMITS,
  type FeedbackReport,
  type FeedbackSubmitResponse,
  scrubText,
} from '@rediacc/shared';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { EXIT_CODES } from '../../types/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { VERSION } from '../../version.js';
import { type AccountFetchError, accountServerFetch } from '../account/account-client.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { type FreeBlob, findInstalledFreeBlob } from './free-blob.js';
import type { RingEntry } from './ring.js';

export const FEEDBACK_PATH = '/account/api/v1/feedback';
export const FEEDBACK_LIMIT_CODE = 'FEEDBACK_DAILY_LIMIT';

/** The body sent for a FREE-licence machine: the report plus the blob and the machine id it is bound to. */
export interface FreeCredentialBody {
  license: FreeBlob;
  machineId: string;
}

export type FeedbackAuth = { kind: 'token' } | { kind: 'free'; credential: FreeCredentialBody };

export interface BuildOptions {
  kind: FeedbackReport['kind'];
  message?: string;
  entry?: RingEntry;
}

/** The first 12 hex characters of the config name's digest: the config is never attached, only this. */
export function configFingerprint(name: string = getEffectiveConfigName()): string {
  return createHash('sha256').update(name).digest('hex').slice(0, 12);
}

/** A report from a ring entry (already redacted at write) plus an optional free-text message, scrubbed again. */
export function buildReport(options: BuildOptions): FeedbackReport {
  const { entry } = options;
  const message = options.message?.trim();
  return {
    kind: options.kind,
    commandPath: entry?.commandPath ?? '',
    argv: entry?.argv ?? '',
    exitCode: entry?.exitCode ?? 0,
    ...(entry?.errorCode ? { errorCode: entry.errorCode } : {}),
    ...(entry?.errorMessage ? { errorMessage: entry.errorMessage } : {}),
    ...(entry?.stderrTail ? { stderrTail: entry.stderrTail } : {}),
    ...(message ? { message: scrubText(message).slice(0, FEEDBACK_LIMITS.message) } : {}),
    cliVersion: entry?.cliVersion ?? VERSION,
    os: platform(),
    arch: arch(),
    configFingerprint: configFingerprint(),
    agent: isAgentEnvironment(),
    ci: Boolean(process.env.CI) && process.env.CI !== '0' && process.env.CI !== 'false',
  };
}

export interface AuthDeps {
  tokenReady: () => boolean;
  freeBlob: () => FreeBlob | undefined;
  machineId: () => Promise<string>;
}

async function defaultMachineId(): Promise<string> {
  const { readLocalMachineId } = await import('../account/client-machine-id.js');
  return readLocalMachineId();
}

const defaultAuthDeps: AuthDeps = {
  tokenReady: () => getSubscriptionTokenState().kind === 'ready',
  freeBlob: () => findInstalledFreeBlob(),
  machineId: defaultMachineId,
};

/** The refusal when neither route is available; its `next` names the login and the free licence. */
export function noCredentialError(): CliExitError {
  return new CliExitError(ERROR_CODES.AUTH_REQUIRED, t('feedback.noCredential'), {
    next: {
      summary: t('feedback.noCredentialSummary'),
      options: [
        { description: t('feedback.optionLogin'), run: 'rdc subscription login' },
        { description: t('feedback.optionFree'), run: 'rdc repo create --help' },
      ],
    },
  });
}

/** Token when logged in, else an installed FREE blob with this machine's id, else a refusal. */
export async function resolveFeedbackAuth(deps: AuthDeps = defaultAuthDeps): Promise<FeedbackAuth> {
  if (deps.tokenReady()) return { kind: 'token' };
  const license = deps.freeBlob();
  if (!license) throw noCredentialError();
  return { kind: 'free', credential: { license, machineId: await deps.machineId() } };
}

/** The exact object sent: the report alone for a token, the report plus the credential fields for a blob. */
export function requestBody(
  report: FeedbackReport,
  auth: FeedbackAuth
): FeedbackReport | (FeedbackReport & FreeCredentialBody) {
  return auth.kind === 'free' ? { ...report, ...auth.credential } : report;
}

export type FetchFn = <T>(
  path: string,
  options: { method: string; body: unknown; noAuth?: boolean }
) => Promise<T>;

function limitError(error: AccountFetchError): CliExitError | undefined {
  if (error.status !== 429 || (error.code ?? error.details?.code) !== FEEDBACK_LIMIT_CODE) {
    return undefined;
  }
  const resetAt = typeof error.details?.resetAt === 'string' ? error.details.resetAt : undefined;
  const subject = typeof error.details?.subjectKind === 'string' ? error.details.subjectKind : '';
  return new CliExitError(
    FEEDBACK_LIMIT_CODE,
    resetAt
      ? t('feedback.dailyLimit', { subject, resetAt })
      : t('feedback.dailyLimitNoReset', { subject }),
    { exitCode: EXIT_CODES.RATE_LIMITED, retryable: false }
  );
}

/** POST the body; a daily-limit 429 becomes a clear error carrying the reset time. */
export async function sendReport(
  body: unknown,
  auth: FeedbackAuth,
  fetchFn: FetchFn = accountServerFetch as FetchFn
): Promise<FeedbackSubmitResponse> {
  try {
    return await fetchFn<FeedbackSubmitResponse>(FEEDBACK_PATH, {
      method: 'POST',
      body,
      ...(auth.kind === 'free' ? { noAuth: true } : {}),
    });
  } catch (error) {
    const mapped = limitError(error as AccountFetchError);
    if (mapped) throw mapped;
    throw error;
  }
}
