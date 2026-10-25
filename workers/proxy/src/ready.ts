/**
 * `GET /v1/ready`: whether this deployed Worker can act as the executor right now.
 *
 * Unauthenticated, so a deploy smoke can poll it. It obtains the issued token and introspects that token itself over ACCOUNT (`{ self: true }`), which proves the ISSUER binding mints, the ACCOUNT binding answers, and the token carries the scopes the executor needs. It answers 200 `{ ready: true, workerVersion }` with the `[version_metadata]` id, which is how the smoke tells the new version from an old one still rolling out, or 503 `{ ready: false, reason }` with a reason code.
 *
 * The answer, ready or not, is cached for READY_CACHE_MS and computed once per isolate at a time, so polling the endpoint cannot drive the issuer into a mint storm.
 */

import { type EgressEnv } from './egress';
import { IssuerError, issuedToken } from './issued-token';

export const READY_CACHE_MS = 30_000;

/** The scopes an issued executor token must carry. */
const REQUIRED_SCOPES = ['proxy:exec', 'audit:write'] as const;

export interface ReadyEnv extends EgressEnv {
  CF_VERSION_METADATA?: WorkerVersionMetadata;
}

export type ReadyAnswer =
  | { status: 200; body: { ready: true; workerVersion: string } }
  | { status: 503; body: { ready: false; reason: string } };

let cachedAnswer: { at: number; answer: ReadyAnswer } | undefined;
let inflightAnswer: Promise<ReadyAnswer> | undefined;

/** Forget the cached answer. Tests only. */
export function resetReadyCache(): void {
  cachedAnswer = undefined;
  inflightAnswer = undefined;
}

function notReady(reason: string): ReadyAnswer {
  console.warn(`proxy: not ready: ${reason}`);
  return { status: 503, body: { ready: false, reason } };
}

async function computeReady(env: ReadyEnv): Promise<ReadyAnswer> {
  const workerVersion = env.CF_VERSION_METADATA?.id;
  if (!workerVersion) return notReady('no-version-metadata');

  let token: string;
  try {
    token = await issuedToken(env.ISSUER);
  } catch (error) {
    return notReady(error instanceof IssuerError ? error.reason : 'issuer-refused');
  }
  const reason = await selfIntrospectionFailure(env, token);
  return reason === undefined
    ? { status: 200, body: { ready: true, workerVersion } }
    : notReady(reason);
}

/** Introspect the issued token itself over ACCOUNT: undefined when it is active with every required scope, otherwise the reason code. */
async function selfIntrospectionFailure(env: ReadyEnv, token: string): Promise<string | undefined> {
  const url = `${env.ACCOUNT_URL}/account/api/v1/proxy/introspect`;
  const init: RequestInit = {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ token, self: true }),
  };
  let body: { active?: boolean; scopes?: string[] };
  try {
    const response = env.ACCOUNT ? await env.ACCOUNT.fetch(url, init) : await fetch(url, init);
    if (!response.ok) return `introspect-http-${response.status}`;
    body = await response.json<{ active?: boolean; scopes?: string[] }>();
  } catch {
    return 'introspect-unreachable';
  }
  if (!body.active) return 'inactive';
  const missing = REQUIRED_SCOPES.find((scope) => !body.scopes?.includes(scope));
  return missing === undefined ? undefined : `no-${missing.replace(':', '-')}-scope`;
}

/** The cached readiness answer, recomputed at most once per READY_CACHE_MS per isolate. */
export function readiness(env: ReadyEnv, now: () => number = Date.now): Promise<ReadyAnswer> {
  if (cachedAnswer && now() - cachedAnswer.at < READY_CACHE_MS) {
    return Promise.resolve(cachedAnswer.answer);
  }
  inflightAnswer ??= computeReady(env)
    .then((answer) => {
      cachedAnswer = { at: now(), answer };
      return answer;
    })
    .finally(() => {
      inflightAnswer = undefined;
    });
  return inflightAnswer;
}
