/**
 * HTTPS to the installed server: the health wait, the free-tier probe and the owner account.
 */

import { ONPREM_FREE_TIER_LOCAL_PATH } from '@rediacc/shared/subscription/onprem-free-tier';
import { t } from '../../i18n/index.js';
import { ServerError } from './box.js';
import type { BoxTarget, ServerDeps } from './types.js';

export const API = '/account/api/v1';
const HEALTH_TRIES = 60;
const HEALTH_INTERVAL_MS = 5_000;

/** Whether a certificate's names cover `host` (exactly, or by a one-label wildcard). */
export function covers(sans: string[], host: string): boolean {
  return sans.some((san) => {
    if (san === host) return true;
    if (!san.startsWith('*.')) return false;
    const rest = host.slice(host.indexOf('.') + 1);
    return san.slice(2) === rest;
  });
}

/** Wait for `/health` to answer 200 over a certificate that covers the domain. */
export async function waitHealthy(
  deps: ServerDeps,
  target: BoxTarget,
  tries = HEALTH_TRIES
): Promise<void> {
  let reply = { status: 0, sans: [] as string[] };
  for (let attempt = 0; attempt < tries; attempt++) {
    reply = await deps.box(target, 'GET', '/health');
    if (reply.status === 200) break;
    if (attempt + 1 < tries) await deps.sleep(HEALTH_INTERVAL_MS);
  }
  if (reply.status !== 200) {
    throw new ServerError(
      t('commands.server.health.failed', {
        domain: target.domain,
        status: reply.status || t('commands.server.health.noAnswer'),
      })
    );
  }
  if (!covers(reply.sans, target.domain)) {
    throw new ServerError(
      t('commands.server.health.certMismatch', {
        domain: target.domain,
        sans: reply.sans.join(', ') || '-',
      })
    );
  }
}

/**
 * Whether the server runs the free tier: its relay refuses an empty request as invalid (400),
 * where a server holding a cert answers 409 NOT_FREE. Undefined when the answer says neither.
 */
export async function probeFreeTier(
  deps: ServerDeps,
  target: BoxTarget
): Promise<boolean | undefined> {
  const reply = await deps.box(target, 'POST', `${API}${ONPREM_FREE_TIER_LOCAL_PATH}`, {});
  if (reply.status === 409) return false;
  if (reply.status === 400) return true;
  return undefined;
}

/**
 * Wait until the server answers as a cert holder (409), so a cert that was just handed over has
 * taken effect. An indeterminate reply (a 503 during a restart) keeps polling. When no definite cert
 * answer arrives within the health wait's bounds it throws `stillFree` when the last answer was the
 * free tier, and `certUnconfirmed` naming the last status otherwise.
 */
export async function waitCertTier(
  deps: ServerDeps,
  target: BoxTarget,
  tries = HEALTH_TRIES
): Promise<void> {
  let lastStatus = 0;
  for (let attempt = 0; attempt < tries; attempt++) {
    const reply = await deps.box(target, 'POST', `${API}${ONPREM_FREE_TIER_LOCAL_PATH}`, {});
    if (reply.status === 409) return;
    lastStatus = reply.status;
    if (attempt + 1 < tries) await deps.sleep(HEALTH_INTERVAL_MS);
  }
  if (lastStatus === 400) {
    throw new ServerError(t('commands.server.licence.stillFree', { domain: target.domain }));
  }
  throw new ServerError(
    t('commands.server.licence.certUnconfirmed', {
      domain: target.domain,
      status: String(lastStatus),
    })
  );
}

/** The owner's session cookie, or undefined when the box does not log them in. */
export async function loginOwner(
  deps: ServerDeps,
  target: BoxTarget,
  creds: { email: string; password: string }
): Promise<string | undefined> {
  const login = await deps.box(target, 'POST', `${API}/auth/login`, creds);
  return login.status === 200 ? login.cookie : undefined;
}

interface OwnerResult {
  subscriptionId: string;
}

function errorOf(body: unknown): string {
  const b = body as { error?: string; code?: string } | null;
  return b?.error ?? b?.code ?? '';
}

/**
 * Register the owner, log in, accept the current Terms and read the subscription. With a cert, the
 * subscription must be the cert's: anything else means another account registered first.
 */
export async function createOwner(
  deps: ServerDeps,
  target: BoxTarget,
  creds: { email: string; password: string },
  certSubscription?: string
): Promise<OwnerResult> {
  const step = async (method: string, path: string, body?: unknown, cookie?: string) => {
    const reply = await deps.box(target, method, `${API}${path}`, body, cookie);
    if (reply.status === 0 || reply.status >= 400) {
      throw new ServerError(
        t('commands.server.owner.stepFailed', {
          step: `${method} ${path}`,
          status: reply.status,
          error: errorOf(reply.body),
        })
      );
    }
    return reply;
  };
  const registered = await deps.box(target, 'POST', `${API}/auth/register`, creds);
  const exists = registered.status === 409;
  if (!exists && (registered.status === 0 || registered.status >= 400)) {
    throw new ServerError(
      t('commands.server.owner.stepFailed', {
        step: 'POST /auth/register',
        status: registered.status,
        error: errorOf(registered.body),
      })
    );
  }
  const login = await step('POST', '/auth/login', creds);
  const cookie = login.cookie;
  const terms = (await step('GET', '/portal/terms', undefined, cookie)).body as {
    satisfied?: boolean;
    current?: { version?: string; sha256?: string };
  };
  if (terms.satisfied === false && terms.current?.version && terms.current.sha256) {
    await step(
      'POST',
      '/portal/terms/accept',
      {
        version: terms.current.version,
        sha256: terms.current.sha256,
        locale: 'en',
        method: 'web-checkbox',
      },
      cookie
    );
  }
  const sub = (await step('GET', '/portal/subscription', undefined, cookie)).body as {
    id?: string;
  };
  const subscriptionId = String(sub.id ?? '');
  if (certSubscription && subscriptionId !== certSubscription) {
    throw new ServerError(
      t('commands.server.owner.raced', { box: subscriptionId || '-', cert: certSubscription })
    );
  }
  return { subscriptionId };
}
