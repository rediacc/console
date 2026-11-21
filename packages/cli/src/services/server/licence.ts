/**
 * The licence step (R6). In order of preference:
 *
 *   --cert <file>   an offline cert; it must name the key the box generated (Q13).
 *   auto            the logged-in config mints the cert and its auto-renew token through
 *                   `POST /delegation/issue`. With no login, or a plan without delegation, the
 *                   server starts on the free tier. An older login without `delegation:issue` is
 *                   told to log in again, or offered the free tier on a terminal.
 *   --licence free  no cert: the server reports `tier: free` and serves each repo licence through
 *                   its `/onprem/free-license` relay.
 *
 * A cert reaches the box through its cert inbox (box-scripts.ts `INBOX_DROP`), the one path the
 * account server validates and applies every new cert by (private/account
 * `delegation-cert-apply.service.ts`). The server's answer is read back by request id, and the
 * owner's `GET /onprem/cert-status` must then report the new cert's id: an `applied.json` alone is
 * not taken as proof while that check can be made.
 */

import { randomUUID } from 'node:crypto';
import {
  type DelegationCert,
  delegationCertId,
  type SignedDelegationCert,
} from '@rediacc/shared/subscription';
import { t } from '../../i18n/index.js';
import type { ServerPrompts } from '../../utils/server-prompts.js';
import { outputService } from '../core/output.js';
import { type RepoOnBox, runOnBox, ServerError } from './box.js';
import {
  INBOX_DROP,
  INBOX_RESULT,
  INBOX_RESULT_SECONDS,
  MIGRATE_ENV_CERT,
  parseEnvLines,
  READ_BOOT_REJECTED,
  READ_LIVE_CERT,
} from './box-scripts.js';
import { assertCertKey, CertError, decodeCert, parseSignedCert } from './cert.js';
import { API, loginOwner } from './http.js';
import { loadOwner, ownerFile } from './state.js';
import type { BoxTarget, IssuedCert, IssueOutcome, LicenceMode, ServerDeps } from './types.js';

export type LicenceResult =
  | {
      kind: 'cert';
      subscriptionId: string;
      signed: SignedDelegationCert;
      /** The auto-renew settings for secrets.env (`UPSTREAM_URL`, `UPSTREAM_API_KEY`); may be empty. */
      env: Record<string, string>;
    }
  | { kind: 'free'; reason: 'asked' | 'no-login' | 'plan' | 'declined-relogin' };

export interface LicenceOptions {
  mode: LicenceMode;
  certFile?: string;
  boxPublicKey: string;
  /** Whether a terminal is there to offer the free tier on a login without the scope. */
  interactive: boolean;
  prompts?: ServerPrompts;
}

/** A cert from a file, checked against the box's key. */
async function certFromFile(
  deps: ServerDeps,
  file: string,
  boxPublicKey: string
): Promise<LicenceResult> {
  let text: string;
  try {
    text = await deps.readFile(file);
  } catch {
    throw new ServerError(t('commands.server.licence.certUnreadable', { file }));
  }
  try {
    const signed = parseSignedCert(text);
    const payload = decodeCert(signed);
    assertCertKey(payload, boxPublicKey);
    return { kind: 'cert', subscriptionId: payload.subscriptionId, signed, env: {} };
  } catch (error) {
    if (error instanceof CertError && error.message === 'key-mismatch') {
      throw new ServerError(t('commands.server.licence.keyMismatch', { file }));
    }
    if (error instanceof CertError) {
      throw new ServerError(
        t('commands.server.licence.certInvalid', { file, error: error.message })
      );
    }
    throw error;
  }
}

export async function obtainLicence(
  deps: ServerDeps,
  opts: LicenceOptions
): Promise<LicenceResult> {
  if (opts.certFile) return certFromFile(deps, opts.certFile, opts.boxPublicKey);
  if (opts.mode === 'free') return { kind: 'free', reason: 'asked' };
  return fromIssue(await deps.issueCert(opts.boxPublicKey), opts);
}

function issued(cert: IssuedCert, boxPublicKey: string): LicenceResult {
  const signed = parseSignedCert(cert.certBase64);
  const payload = decodeCert(signed);
  if (payload.delegatedPublicKey !== boxPublicKey) {
    throw new ServerError(t('commands.server.licence.issuedKeyMismatch'));
  }
  const env: Record<string, string> = {};
  if (cert.autoRenewToken && cert.upstreamUrl) {
    env.UPSTREAM_URL = cert.upstreamUrl;
    env.UPSTREAM_API_KEY = cert.autoRenewToken;
  }
  return { kind: 'cert', subscriptionId: payload.subscriptionId, signed, env };
}

/** A login without `delegation:issue`: the free tier when a terminal accepts it, else the relogin refusal. */
async function missingScope(opts: LicenceOptions): Promise<LicenceResult> {
  if (opts.interactive && opts.prompts) {
    outputService.warn(t('commands.server.licence.missingScope'));
    if (await opts.prompts.confirm(t('commands.server.licence.offerFree'), true)) {
      return { kind: 'free', reason: 'declined-relogin' };
    }
  }
  throw new ServerError(t('commands.server.licence.missingScope'));
}

function fromIssue(
  outcome: IssueOutcome,
  opts: LicenceOptions
): Promise<LicenceResult> | LicenceResult {
  switch (outcome.kind) {
    case 'issued':
      return issued(outcome.cert, opts.boxPublicKey);
    case 'no-login':
      outputService.info(t('commands.server.licence.noLogin'));
      return { kind: 'free', reason: 'no-login' };
    case 'plan-disallows':
      outputService.warn(t('commands.server.licence.planDisallows', { error: outcome.message }));
      return { kind: 'free', reason: 'plan' };
    case 'other-key':
      throw new ServerError(
        t('commands.server.licence.otherKey', { certId: outcome.certId, error: outcome.message })
      );
    case 'missing-scope':
      return missingScope(opts);
  }
}

// ── the cert inbox ──────────────────────────────────────────────────────────────────────────

export interface LiveCert {
  signed: SignedDelegationCert;
  decoded: DelegationCert;
  certId: string;
}

/** The cert in force on the box (its live file), or undefined when it holds none or an unreadable one. */
export async function readLiveCert(
  deps: ServerDeps,
  where: RepoOnBox
): Promise<LiveCert | undefined> {
  const text = (await runOnBox(deps, where, READ_LIVE_CERT)).stdout.trim();
  if (!text) return undefined;
  try {
    const signed = parseSignedCert(text);
    return { signed, decoded: decodeCert(signed), certId: await delegationCertId(signed) };
  } catch {
    return undefined;
  }
}

/** Why the box refused its cert at boot (the server's `boot-rejected.json`). */
export interface BootRejected {
  reason: string;
  detail: string;
  certId: string | null;
  at: string;
}

/** The boot-refusal marker, or undefined when the box holds none. An unreadable marker still counts as a refusal. */
export async function readBootRejected(
  deps: ServerDeps,
  where: RepoOnBox
): Promise<BootRejected | undefined> {
  const text = (await runOnBox(deps, where, READ_BOOT_REJECTED)).stdout.trim();
  if (!text) return undefined;
  let raw: Record<string, unknown> = {};
  try {
    raw = JSON.parse(text) as Record<string, unknown>;
  } catch {
    raw = {};
  }
  return {
    reason: typeof raw.reason === 'string' ? raw.reason : 'unknown',
    detail: typeof raw.detail === 'string' ? raw.detail : '',
    certId: typeof raw.certId === 'string' ? raw.certId : null,
    at: typeof raw.at === 'string' ? raw.at : '',
  };
}

/** A drop waiting for its answer: the request id the answer names, and the cert id it carries. */
export interface PendingDrop {
  requestId: string;
  certId: string;
}

/** Drop the cert into the box's inbox. Refuses, dropping nothing, while another drop is undecided. */
export async function dropCert(
  deps: ServerDeps,
  where: RepoOnBox,
  signed: SignedDelegationCert
): Promise<PendingDrop> {
  const requestId = randomUUID();
  const { payload, signature, publicKeyId } = signed;
  const body = `${JSON.stringify({ requestId, cert: { payload, signature, publicKeyId } })}\n`;
  const out = parseEnvLines((await runOnBox(deps, where, INBOX_DROP, body)).stdout);
  if (out.inbox !== 'dropped') throw new ServerError(t('commands.server.licence.inboxBusy'));
  return { requestId, certId: await delegationCertId(signed) };
}

/** The one-time `DELEGATION_CERT_BASE64` move (`rdc server upgrade`); a drop when one was made. */
export async function migrateEnvCert(
  deps: ServerDeps,
  where: RepoOnBox
): Promise<{ requestId: string } | undefined> {
  const requestId = randomUUID();
  const out = parseEnvLines(
    (await runOnBox(deps, where, MIGRATE_ENV_CERT, `${requestId}\n`)).stdout
  );
  if (out.migrate === 'busy') throw new ServerError(t('commands.server.licence.inboxBusy'));
  return out.migrate === 'dropped' ? { requestId } : undefined;
}

export interface InboxApplied {
  certId: string;
  issuedAt: string;
}

/** The server's answer to a drop: applied, or a `rejected` error naming its reason, or `noResult`. */
export async function awaitInboxResult(
  deps: ServerDeps,
  where: RepoOnBox,
  requestId: string
): Promise<InboxApplied> {
  const out = (await runOnBox(deps, where, INBOX_RESULT, `${requestId}\n`)).stdout;
  const newline = out.indexOf('\n');
  const head = (newline < 0 ? out : out.slice(0, newline)).trim();
  let answer: Record<string, unknown> = {};
  try {
    answer = JSON.parse(newline < 0 ? '{}' : out.slice(newline + 1)) as Record<string, unknown>;
  } catch {
    answer = {};
  }
  if (head === 'result=applied') {
    return { certId: String(answer.certId ?? ''), issuedAt: String(answer.issuedAt ?? '') };
  }
  if (head === 'result=rejected') {
    throw new ServerError(
      t('commands.server.licence.rejected', {
        reason: String(answer.reason ?? '-'),
        detail: String(answer.detail ?? ''),
      })
    );
  }
  throw new ServerError(t('commands.server.licence.noResult', { seconds: INBOX_RESULT_SECONDS }));
}

/**
 * The owner's `GET /onprem/cert-status` (the owner is the server's root, `ROOT_EMAIL`) must report
 * `certId`. Without saved owner credentials the check cannot be made: a warning says so and the
 * inbox answer stands. Saved credentials the box refuses are a failed check, not a skipped one.
 */
export async function confirmCertId(
  deps: ServerDeps,
  target: BoxTarget,
  domain: string,
  certId: string
): Promise<void> {
  const owner = loadOwner(domain);
  if (!owner) {
    outputService.warn(
      t('commands.server.licence.confirmSkipped', { ownerFile: ownerFile(domain) })
    );
    return;
  }
  const cookie = await loginOwner(deps, target, owner);
  const reply = cookie
    ? await deps.box(target, 'GET', `${API}/onprem/cert-status`, undefined, cookie)
    : { status: 0, body: null };
  const actual = (reply.body as { cert?: { certId?: unknown } } | null)?.cert?.certId;
  if (reply.status !== 200 || actual !== certId) {
    throw new ServerError(
      t('commands.server.licence.confirmMismatch', {
        expected: certId,
        actual: typeof actual === 'string' ? actual : `HTTP ${reply.status || '-'}`,
      })
    );
  }
}
