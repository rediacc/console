/**
 * Move a first-use API token to the caller's new IP after a TOTP check
 * (PLAN-token-ip-rebind.md, section 4.2).
 *
 * The account server binds a first-use token to the address of its first
 * caller and refuses it from any other with 403 TOKEN_IP_MISMATCH. On an
 * interactive terminal this asks for the token creator's authenticator code and
 * POSTs it to the rebind route; everywhere else it explains both remedies.
 *
 * `accountServerFetch` is the only caller. It passes the rebind request in as
 * `rebind`, bound to the same token and server as the refused request, so this
 * module never imports the client and the refusal, the move and the retry all
 * carry one token.
 */

import { createHash } from 'node:crypto';
import {
  API_TOKEN_IP_REBIND_ERROR_CODES,
  type ApiTokenIpRebindResponse,
  TOKEN_IP_MISMATCH,
  type TokenIpRebindHint,
} from '@rediacc/shared/subscription/types';
import { t } from '../../i18n/index.js';
import { askInput } from '../../utils/prompt.js';
import { suspendSpinner } from '../../utils/spinner.js';
import { writeStderr } from '../core/request-context.js';
import type { AccountFetchError } from './account-client.js';

/** Code entries allowed per process before giving up; the server's own lock sits at 5 failures. */
const MAX_CODE_ENTRIES = 3;

const TOTP_PATTERN = /^\d{6}$/;

interface EnsureReboundInput {
  /** The bearer token the server refused. */
  token: string;
  /** The `rebind` field of the 403: what can clear it. */
  hint: TokenIpRebindHint;
  /** POST the code to the rebind route with the same token and server. */
  rebind: (code: string) => Promise<ApiTokenIpRebindResponse>;
}

/**
 * One outcome per token per process. Parallel callers (license batch refresh,
 * relay polling) share one prompt and one POST; a failed or declined outcome
 * stays cached, so later 403s fail at once without prompting again.
 */
const inflight = new Map<string, Promise<void>>();

export function ensureRebound(input: EnsureReboundInput): Promise<void> {
  const key = createHash('sha256').update(input.token).digest('hex');
  let pending = inflight.get(key);
  if (!pending) {
    pending = runRebind(input);
    inflight.set(key, pending);
  }
  return pending;
}

/** Test-only: forget cached outcomes. Each CLI invocation is a fresh process in production. */
export function resetTokenIpRebindState(): void {
  inflight.clear();
}

async function runRebind({ hint, rebind }: EnsureReboundInput): Promise<void> {
  if (hint === 'relogin') {
    throw mismatchError(t('errors.subscription.ipRebind.reloginOnly'));
  }
  if (process.stdin.isTTY !== true || process.stderr.isTTY !== true) {
    throw mismatchError(t('errors.subscription.ipRebind.nonInteractive'));
  }

  await suspendSpinner(async () => {
    for (let entry = 1; entry <= MAX_CODE_ENTRIES; entry++) {
      const code = await askInput(t('errors.subscription.ipRebind.prompt'), TOTP_PATTERN);
      try {
        const result = await rebind(code);
        writeStderr(`${t('errors.subscription.ipRebind.moved', { ip: result.boundIp })}\n`);
        return;
      } catch (error) {
        const retryable = describeRebindFailure(error);
        if (retryable === null) throw error;
        writeStderr(`${retryable}\n`);
      }
    }
    throw mismatchError(t('errors.subscription.ipRebind.attemptsExhausted'));
  });
}

/**
 * For a wrong or reused code, the line to print before asking again. Every
 * other refusal is final and is thrown from here with its localized message;
 * an error this module does not recognise (401, CLIENT_IP_UNKNOWN, a network
 * failure) is rethrown as the server or transport reported it.
 */
function describeRebindFailure(error: unknown): string | null {
  const e = error as Partial<AccountFetchError>;
  const details = e.details ?? {};
  switch (e.code) {
    case API_TOKEN_IP_REBIND_ERROR_CODES.TOTP_INVALID:
      return t('errors.subscription.ipRebind.wrongCode', {
        remaining: String(details.attemptsRemaining ?? '?'),
      });
    case API_TOKEN_IP_REBIND_ERROR_CODES.TOTP_REPLAYED:
      return t('errors.subscription.ipRebind.replayed');
    case API_TOKEN_IP_REBIND_ERROR_CODES.IP_REBIND_LOCKED: {
      const retryAfter = Number(details.retryAfter);
      const minutes = Number.isFinite(retryAfter) ? Math.max(1, Math.ceil(retryAfter / 60)) : 1;
      throw refusal(e, t('errors.subscription.ipRebind.locked', { minutes: String(minutes) }));
    }
    case API_TOKEN_IP_REBIND_ERROR_CODES.IP_REBIND_DISABLED:
      throw refusal(e, t('errors.subscription.ipRebind.disabled'));
    case API_TOKEN_IP_REBIND_ERROR_CODES.IP_REBIND_UNAVAILABLE:
      throw refusal(
        e,
        details.reason === 'not_first_use'
          ? t('errors.subscription.ipRebind.notFirstUse')
          : t('errors.subscription.ipRebind.reloginOnly')
      );
    default:
      return null;
  }
}

/** The refused request's own status and code, so call sites that check either keep working. */
function mismatchError(message: string): AccountFetchError {
  return Object.assign(new Error(message), { status: 403, code: TOKEN_IP_MISMATCH });
}

/**
 * A final refusal from the rebind route, localized. It keeps the ORIGINAL
 * request's 403 TOKEN_IP_MISMATCH, so call sites see one failure whatever the
 * move ran into; the route's own code and body stay in `details`.
 */
function refusal(source: Partial<AccountFetchError>, message: string): AccountFetchError {
  return Object.assign(mismatchError(message), {
    details: { ...source.details, rebindStatus: source.status, rebindCode: source.code },
  });
}
