/**
 * `GET /v1/ready`: whether this deployed Worker can act as the executor right now.
 *
 * Unauthenticated, so a deploy smoke can poll it. There is no org-less token to introspect, so it asks the issuer's `probe()` (writes nothing and mints nothing: the issuer env parses, D1 answers, and the scopes an issued token would carry are listed) and then `GET server-info` over ACCOUNT, which together prove the ISSUER binding answers, the ACCOUNT binding answers, and a token would carry the scopes the executor needs. It answers 200 `{ ready: true, workerVersion }` with the `[version_metadata]` id, which is how the smoke tells the new version from an old one still rolling out, or 503 `{ ready: false, reason }` with a reason code.
 *
 * The answer, ready or not, is cached for READY_CACHE_MS and computed once per isolate at a time, so polling the endpoint cannot drive the issuer into a mint storm.
 */

import { type EgressEnv } from './egress';

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

  const probeFailure = await issuerProbeFailure(env);
  if (probeFailure !== undefined) return notReady(probeFailure);
  const reason = await serverInfoFailure(env);
  return reason === undefined
    ? { status: 200, body: { ready: true, workerVersion } }
    : notReady(reason);
}

/** Ask the issuer's `probe()`: undefined when it answers ok with every required scope, otherwise the reason code. */
async function issuerProbeFailure(env: ReadyEnv): Promise<string | undefined> {
  if (!env.ISSUER) return 'no-issuer';
  let answer: { ok?: unknown; scopes?: unknown } | undefined;
  try {
    answer = await env.ISSUER.probe();
  } catch {
    return 'issuer-probe-failed';
  }
  if (answer?.ok !== true || !Array.isArray(answer.scopes)) return 'issuer-probe-failed';
  const scopes: unknown[] = answer.scopes;
  const missing = REQUIRED_SCOPES.find((scope) => !scopes.includes(scope));
  return missing === undefined ? undefined : `no-${missing.replace(':', '-')}-scope`;
}

/** `GET server-info` over ACCOUNT (the public route the executor itself uses): undefined when it answers 2xx, otherwise the reason code. */
async function serverInfoFailure(env: ReadyEnv): Promise<string | undefined> {
  const url = `${env.ACCOUNT_URL}/account/api/v1/.well-known/server-info`;
  try {
    const response = env.ACCOUNT ? await env.ACCOUNT.fetch(url) : await fetch(url);
    return response.ok ? undefined : `server-info-http-${response.status}`;
  } catch {
    return 'server-info-unreachable';
  }
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
