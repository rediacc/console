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
 */

import { t } from '../../i18n/index.js';
import type { ServerPrompts } from '../../utils/server-prompts.js';
import { outputService } from '../core/output.js';
import { ServerError } from './box.js';
import { assertCertKey, CertError, certToBase64, decodeCert, parseSignedCert } from './cert.js';
import type { IssuedCert, IssueOutcome, LicenceMode, ServerDeps } from './types.js';

export type LicenceResult =
  | { kind: 'cert'; subscriptionId: string; env: Record<string, string> }
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
    return {
      kind: 'cert',
      subscriptionId: payload.subscriptionId,
      env: { DELEGATION_CERT_BASE64: certToBase64(signed) },
    };
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
  const payload = decodeCert(parseSignedCert(cert.certBase64));
  if (payload.delegatedPublicKey !== boxPublicKey) {
    throw new ServerError(t('commands.server.licence.issuedKeyMismatch'));
  }
  const env: Record<string, string> = { DELEGATION_CERT_BASE64: cert.certBase64 };
  if (cert.autoRenewToken && cert.upstreamUrl) {
    env.UPSTREAM_URL = cert.upstreamUrl;
    env.UPSTREAM_API_KEY = cert.autoRenewToken;
  }
  return { kind: 'cert', subscriptionId: payload.subscriptionId, env };
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
