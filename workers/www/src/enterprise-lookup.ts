/**
 * POST /api/enterprise-lookup: {domain, turnstileToken} -> {host: string | null}.
 *
 * The client sends only the domain part of an address. Every address at a domain gets the same answer, so no user's existence is exposed, and a miss, a malformed domain, a free-mail domain and an unlisted company all answer `{host: null}`. Entries live in KV under an HMAC of the domain with a server-side pepper, written by `.ci/rediacc_ci/ops/enterprise_lookup.py`, which shares `normalizeDomain` and `lookupKey` semantics.
 */

export interface LookupEnv {
  ENTERPRISE_LOOKUP?: KVNamespace;
  ENTERPRISE_LOOKUP_PEPPER?: string;
  CLOUDFLARE_TURNSTILE_SECRET_KEY?: string;
  // Optional Workers rate-limiting binding; absent means no limit is applied here.
  LOOKUP_RATE_LIMIT?: { limit(options: { key: string }): Promise<{ success: boolean }> };
}

const DOMAIN_RE = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$/;
const MAX_BODY = 2048;
const SITEVERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

const HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: HEADERS });
}

/** Lowercase, drop one trailing dot, and accept only a plain ASCII (punycode) hostname of two or more labels. */
export function normalizeDomain(input: unknown): string | null {
  if (typeof input !== 'string') return null;
  let d = input.trim().toLowerCase();
  if (d.endsWith('.')) d = d.slice(0, -1);
  if (d.length > 253 || !DOMAIN_RE.test(d)) return null;
  return d;
}

/** Hex HMAC-SHA256 of the domain under the pepper: the KV key. */
export async function lookupKey(pepper: string, domain: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(pepper),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(domain));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function turnstileOk(secret: string, token: unknown, ip: string | null): Promise<boolean> {
  if (typeof token !== 'string' || token.length === 0 || token.length > 2048) return false;
  const form = new FormData();
  form.set('secret', secret);
  form.set('response', token);
  if (ip) form.set('remoteip', ip);
  try {
    const res = await fetch(SITEVERIFY, { method: 'POST', body: form });
    const body = (await res.json()) as { success?: boolean };
    return body.success === true;
  } catch {
    return false;
  }
}

interface Payload {
  domain?: unknown;
  turnstileToken?: unknown;
}

async function readPayload(request: Request): Promise<Payload | null> {
  const text = await request.text();
  if (text.length > MAX_BODY) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed !== null && typeof parsed === 'object' ? (parsed as Payload) : null;
  } catch {
    return null;
  }
}

/** A refusal Response when the request must not reach the lookup, else null. */
async function refusal(
  request: Request,
  env: LookupEnv,
  payload: Payload
): Promise<Response | null> {
  const ip = request.headers.get('cf-connecting-ip');
  if (env.LOOKUP_RATE_LIMIT) {
    const verdict = await env.LOOKUP_RATE_LIMIT.limit({ key: ip ?? 'unknown' });
    if (!verdict.success) return json({ error: 'rate_limited' }, 429);
  }
  const secret = env.CLOUDFLARE_TURNSTILE_SECRET_KEY;
  if (secret && !(await turnstileOk(secret, payload.turnstileToken, ip))) {
    return json({ error: 'turnstile_failed' }, 403);
  }
  return null;
}

export async function handleEnterpriseLookup(request: Request, env: LookupEnv): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response(null, {
      status: 405,
      headers: { allow: 'POST', 'cache-control': 'no-store' },
    });
  }
  const { ENTERPRISE_LOOKUP: kv, ENTERPRISE_LOOKUP_PEPPER: pepper } = env;
  if (!kv || !pepper) return json({ error: 'unavailable' }, 503);

  const payload = await readPayload(request);
  if (!payload) return json({ error: 'bad_request' }, 400);
  const refused = await refusal(request, env, payload);
  if (refused) return refused;

  // A malformed domain answers like a miss: the shape never depends on the input.
  const domain = normalizeDomain(payload.domain);
  if (!domain) return json({ host: null });
  const host = await kv.get(await lookupKey(pepper, domain));
  return json({ host: host && host.length > 0 ? host : null });
}
