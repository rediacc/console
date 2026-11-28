/**
 * `POST /internal/revoke` (agent/plans/PLAN-rmcp-remote-worker.md Design 4): the account's pushed revocation (PLAN-rmcp-agent-grants.md AG-S5) purges this isolate's grant cache, so the next call of a revoked grant reaches the account and is refused.
 *
 * The route sits on the public host, so it needs a credential: the shared secret `INTERNAL_REVOKE_TOKEN` as `Authorization: Bearer`. A Worker deployed without the secret answers 404 for the path, as if it did not exist. The body is `{"grantId": "<id>"}`; the answer is 204 and carries no detail.
 */
import type { GrantResolver } from './resolve.js';

export const REVOKE_PATH = '/internal/revoke';

/** A grant id as the route table of the transport accepts it. */
const GRANT_ID = /^[A-Za-z0-9_-]{1,64}$/;

async function digest(text: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
}

/** Constant-time comparison of two secrets, over their digests so the lengths do not leak. */
async function sameSecret(a: string, b: string): Promise<boolean> {
  const [x, y] = await Promise.all([digest(a), digest(b)]);
  let diff = 0;
  for (let i = 0; i < x.length; i += 1) diff |= x[i] ^ y[i];
  return diff === 0;
}

function status(code: number, body?: string): Response {
  return new Response(body ?? null, { status: code, headers: { 'content-type': 'text/plain' } });
}

export async function handleRevoke(
  request: Request,
  options: { token: string | undefined; resolver: GrantResolver }
): Promise<Response> {
  if (!options.token) return status(404, 'Not found');
  if (request.method !== 'POST') return status(405, 'Method not allowed');
  const match = /^Bearer\s+(\S+)\s*$/i.exec(request.headers.get('authorization')?.trim() ?? '');
  if (!match || !(await sameSecret(match[1], options.token))) return status(401, 'Unauthorized');
  let grantId: unknown;
  try {
    grantId = ((await request.json()) as { grantId?: unknown } | null)?.grantId;
  } catch {
    return status(400, 'Bad request');
  }
  if (typeof grantId !== 'string' || !GRANT_ID.test(grantId)) return status(400, 'Bad request');
  options.resolver.purge(grantId);
  return status(204);
}
