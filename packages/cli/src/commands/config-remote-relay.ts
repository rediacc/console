/**
 * The server relay: the one way config keys reach the CLI (`config remote enable`, `config rotate-cek`).
 *
 * CLI, account server and browser; the browser never talks to the CLI directly:
 *   1. The CLI mints an ephemeral X25519 key pair, a nonce N and a poll secret S, and creates a
 *      `config-handoff` device code with its login token. The server binds the code to that user and
 *      stores only H(spki) and H(S).
 *   2. It prints a link whose FRAGMENT carries the device code, the public key and N (browsers never send a
 *      fragment to a server or in Referer), plus a pairing code derived from H(spki) that the user types
 *      on the page. A swapped key in the link fails both the server's hash check and the typed code.
 *   3. The page seals `{..., handoffNonce: N}` to the key and posts it to the relay; the CLI claims it with S
 *      (one shot), decrypts it, and refuses a plaintext whose nonce is not N.
 *
 * The page trusts the JavaScript the account origin serves, as every CEK-handling portal page does; the
 * pairing code defends against link tampering and relay-side swaps, not a compromised origin.
 */

import { timingSafeEqual } from 'node:crypto';
import type { CekHandoffBlob } from '@rediacc/shared/config-crypto';
import {
  fromBase64,
  handoffKeyHash,
  handoffPairingCode,
  handoffPollVerifier,
  randomBytes,
} from '@rediacc/shared/config-crypto';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import { ValidationError } from '../utils/errors.js';
import { stopSpinner, withSpinner } from '../utils/spinner.js';
import {
  decryptHandoff,
  exportPublicKeyBase64,
  generateX25519KeyPair,
  type HandoffPayload,
} from './config-remote-handoff.js';

const DEVICE_CODES_PATH = '/account/api/v1/device-codes';
/** Backoff ceiling for network errors and 5xx, and the wait on a 429 that names no Retry-After. */
export const MAX_BACKOFF_MS = 30_000;
/** Consecutive transport failures before the one "still retrying" warning. */
const WARN_AFTER_FAILURES = 3;
/** Ctrl+C sends a best-effort cancel and waits at most this long before exiting. */
const CANCEL_TIMEOUT_MS = 2_000;
/** Exit code for SIGINT (128 + 2). */
const SIGINT_EXIT_CODE = 130;

export interface RelayHandoff {
  url: string;
  pairingCode: string;
  deviceCode: string;
  /** Epoch milliseconds; the claim loop runs until this moment. */
  expiresAt: number;
  /** Poll interval the server asked for, in milliseconds. */
  intervalMs: number;
  privateKey: CryptoKey;
  nonce: string;
  pollSecret: string;
}

interface CreateResponse {
  deviceCode: string;
  interval: number;
  expiresIn: number;
  expiresAt?: string | number;
}

interface ClaimResponse {
  status?: string;
  configHandoff?: string;
}

interface FetchError extends Error {
  status?: number;
  /** Seconds, when the transport can surface a Retry-After. */
  retryAfter?: number;
}

function base64Url(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString('base64url');
}

/**
 * The link the user opens. Everything sits in the fragment (section 4.1 of the relay plan): no query string,
 * so the code, key and nonce stay out of server logs and Referer.
 * Portal route: private/account/web/src/pages/ConfigRemote.tsx at /account/config-remote.
 */
export function relayUrl(
  apiUrl: string,
  deviceCode: string,
  publicKeyB64: string,
  nonce: string
): string {
  const base = apiUrl.replace(/\/+$/, '');
  const fragment = [
    `code=${encodeURIComponent(deviceCode)}`,
    `key=${encodeURIComponent(publicKeyB64)}`,
    `nonce=${encodeURIComponent(nonce)}`,
  ].join('&');
  return `${base}/account/config-remote#${fragment}`;
}

/**
 * The sealed handoff as the relay returns it: a JSON string. A ValidationError here ends the claim loop at
 * once instead of polling until the code expires.
 */
export function parseHandoff(raw: string): CekHandoffBlob {
  try {
    return JSON.parse(raw) as CekHandoffBlob;
  } catch {
    throw new ValidationError(t('commands.config.remote.enable.handoffUnreadable'));
  }
}

function resolveExpiry(created: CreateResponse, now: number): number {
  let fromServer = Number.NaN;
  if (typeof created.expiresAt === 'number') fromServer = created.expiresAt;
  else if (typeof created.expiresAt === 'string') fromServer = Date.parse(created.expiresAt);
  return Number.isFinite(fromServer) ? fromServer : now + created.expiresIn * 1000;
}

/** Create the key pair, nonce and poll secret, and register a user-bound `config-handoff` code. */
export async function startRelayHandoff(apiUrl: string, loginToken: string): Promise<RelayHandoff> {
  const keyPair = await generateX25519KeyPair();
  const publicKeyB64 = await exportPublicKeyBase64(keyPair.publicKey);
  const spki = fromBase64(publicKeyB64);
  const nonce = base64Url(randomBytes(32));
  // S is 32 raw bytes, sent as 43-char base64url; the server stores base64url(SHA-256(raw S)).
  const pollSecretRaw = randomBytes(32);
  const pollSecret = base64Url(pollSecretRaw);

  const created = await accountServerFetch<CreateResponse>(DEVICE_CODES_PATH, {
    method: 'POST',
    serverUrl: apiUrl,
    token: loginToken,
    body: {
      purpose: 'config-handoff',
      keyHash: await handoffKeyHash(spki),
      pollVerifier: await handoffPollVerifier(pollSecretRaw),
    },
  });

  return {
    url: relayUrl(apiUrl, created.deviceCode, publicKeyB64, nonce),
    pairingCode: await handoffPairingCode(spki),
    deviceCode: created.deviceCode,
    expiresAt: resolveExpiry(created, Date.now()),
    intervalMs: Math.max(1, created.interval) * 1000,
    privateKey: keyPair.privateKey,
    nonce,
    pollSecret,
  };
}

/** Best-effort DELETE of the pending code, bounded to two seconds; never throws. */
async function cancelRelayHandoff(
  apiUrl: string,
  deviceCode: string,
  pollSecret: string
): Promise<void> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, CANCEL_TIMEOUT_MS);
  });
  const request = accountServerFetch(`${DEVICE_CODES_PATH}/${encodeURIComponent(deviceCode)}`, {
    method: 'DELETE',
    noAuth: true,
    serverUrl: apiUrl,
    body: { pollSecret },
  }).then(
    () => undefined,
    () => undefined
  );
  try {
    await Promise.race([request, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nonceMatches(expected: string, actual: unknown): boolean {
  if (typeof actual !== 'string') return false;
  const a = Buffer.from(expected, 'utf8');
  const b = Buffer.from(actual, 'utf8');
  return a.length === b.length && timingSafeEqual(a, b);
}

type ClaimStep = { done: CekHandoffBlob } | { waitMs: number; failed: boolean };

/**
 * A failed claim request, classified: 404/410 is expired, 429 waits for Retry-After (the ceiling when the
 * transport cannot surface one), another 4xx refuses at once with its status, and a network error or 5xx
 * backs off exponentially.
 */
function classifyClaimError(error: unknown, relay: RelayHandoff, failures: number): ClaimStep {
  if (error instanceof ValidationError) throw error;
  const { status, retryAfter, message } = error as FetchError;
  if (status === 404 || status === 410) {
    throw new ValidationError(t('commands.config.remote.enable.expired'));
  }
  if (status === 429) {
    const waitMs = typeof retryAfter === 'number' ? retryAfter * 1000 : MAX_BACKOFF_MS;
    return { waitMs, failed: false };
  }
  if (status !== undefined && status >= 400 && status < 500) {
    throw new ValidationError(
      t('commands.config.remote.enable.relayRefused', { status: String(status), error: message })
    );
  }
  return { waitMs: Math.min(relay.intervalMs * 2 ** (failures + 1), MAX_BACKOFF_MS), failed: true };
}

/** One claim attempt: the blob, or how long to wait before the next one. */
async function claimOnce(
  apiUrl: string,
  relay: RelayHandoff,
  failures: number
): Promise<ClaimStep> {
  let res: ClaimResponse;
  try {
    res = await accountServerFetch<ClaimResponse>(
      `${DEVICE_CODES_PATH}/${encodeURIComponent(relay.deviceCode)}/claim`,
      { method: 'POST', noAuth: true, serverUrl: apiUrl, body: { pollSecret: relay.pollSecret } }
    );
  } catch (error) {
    return classifyClaimError(error, relay, failures);
  }
  if (res.status === 'expired') {
    throw new ValidationError(t('commands.config.remote.enable.expired'));
  }
  if (res.status === 'complete' && res.configHandoff) {
    return { done: parseHandoff(res.configHandoff) };
  }
  return { waitMs: relay.intervalMs, failed: false };
}

/** Claim until the blob arrives or the code's `expiresAt` passes. */
async function claimUntilDeadline(apiUrl: string, relay: RelayHandoff): Promise<CekHandoffBlob> {
  let waitMs = relay.intervalMs;
  let failures = 0;
  for (;;) {
    const remaining = relay.expiresAt - Date.now();
    if (remaining <= 0) throw new ValidationError(t('commands.config.remote.enable.expired'));
    await sleep(Math.min(waitMs, remaining));
    const step = await claimOnce(apiUrl, relay, failures);
    if ('done' in step) return step.done;
    failures = step.failed ? failures + 1 : 0;
    // Once per outage: on the third consecutive transport failure, not on every retry after it.
    if (failures === WARN_AFTER_FAILURES) {
      outputService.warn(t('commands.config.remote.enable.serverUnreachableRetrying', { apiUrl }));
    }
    waitMs = step.waitMs;
  }
}

/**
 * Claim until the handoff arrives or the code's `expiresAt` passes, then decrypt and require the nonce this
 * run minted. A mismatch or a missing nonce refuses before anything is stored.
 */
export async function waitForRelayHandoff(
  apiUrl: string,
  relay: RelayHandoff
): Promise<HandoffPayload> {
  const blob = await claimUntilDeadline(apiUrl, relay);
  const payload = await decryptHandoff(blob, relay.privateKey);
  if (!nonceMatches(relay.nonce, (payload as { handoffNonce?: unknown }).handoffNonce)) {
    throw new ValidationError(t('commands.config.remote.enable.handoffNotForThisRun'));
  }
  return payload;
}

function formatExpiry(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export async function tryOpenBrowser(url: string): Promise<void> {
  try {
    const { execFile } = await import('node:child_process');
    const cmd = process.platform === 'darwin' ? 'open' : 'xdg-open';
    // execFile passes the URL as one argv entry, so `&` and `#` reach the browser intact.
    execFile(cmd, [url], () => {});
  } catch {
    // Browser open is best-effort
  }
}

/**
 * The whole CLI leg: create the code, print the link and pairing code, wait under a spinner, and honour
 * Ctrl+C with a best-effort cancel and exit 130. Returns the nonce-checked payload; the caller applies it.
 */
export async function runRelayHandoff(
  apiUrl: string,
  loginToken: string,
  approverEmail: string | undefined
): Promise<HandoffPayload> {
  const relay = await startRelayHandoff(apiUrl, loginToken);

  outputService.info(
    approverEmail
      ? t('commands.config.remote.enable.approveAs', { email: approverEmail })
      : t('commands.config.remote.enable.openRelay')
  );
  outputService.info(`  ${relay.url}`);
  outputService.info(t('commands.config.remote.enable.pairingCode', { code: relay.pairingCode }));
  outputService.info('');
  await tryOpenBrowser(relay.url);

  const onSigint = () => {
    void cancelRelayHandoff(apiUrl, relay.deviceCode, relay.pollSecret).finally(() => {
      stopSpinner(false);
      outputService.warn(t('commands.config.remote.enable.cancelled'));
      process.exit(SIGINT_EXIT_CODE);
    });
  };
  process.once('SIGINT', onSigint);
  const waiting = t('commands.config.remote.enable.waitingUntil', {
    time: formatExpiry(relay.expiresAt),
  });
  try {
    if (process.stdout.isTTY === true) {
      return await withSpinner(
        waiting,
        () => waitForRelayHandoff(apiUrl, relay),
        t('commands.config.remote.enable.received')
      );
    }
    // Without a TTY withSpinner prints nothing up front, and the expiry and Ctrl+C hint must still show.
    outputService.info(waiting);
    const payload = await waitForRelayHandoff(apiUrl, relay);
    outputService.info(t('commands.config.remote.enable.received'));
    return payload;
  } finally {
    process.removeListener('SIGINT', onSigint);
  }
}
