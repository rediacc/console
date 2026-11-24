/**
 * `GET /v1/ready`: whether this deployed Worker can act as the executor right now.
 *
 * Unauthenticated, so a deploy smoke can poll it. There is no org-less token to introspect, so it asks the issuer's `probe()` (writes nothing and mints nothing: the issuer env parses, D1 answers, and the scopes an issued token would carry are listed) and then `GET server-info` over ACCOUNT, which together prove the ISSUER binding answers, the ACCOUNT binding answers, and a token would carry the scopes the executor needs. It answers 200 `{ ready: true, workerVersion }` with the `[version_metadata]` id, which is how the smoke tells the new version from an old one still rolling out, or 503 `{ ready: false, reason }` with a reason code.
 *
 * The public answer carries no occupancy, for every caller (D52, PLAN-rmcp-executor-hardening.md Design 8). Executor occupancy (`total`, `heavy` and the caps in force) is readable only through `GET /v1/internal/occupancy`, which answers the account Worker alone: the request must carry an internal credential that the account Worker mints and the ISSUER binding verifies (`verifyInternal`), and every other caller, with no credential, a forged one or an expired one, gets the same 404 as an unknown path. The account server's root-only `GET /admin/executor-occupancy` is the one consumer. This replaces the earlier unauthenticated count (review 900c1e14.2), whose series told any poller when load rose and when heavy-tier runs started.
 *
 * Each upstream call (the issuer probe, server-info, the internal occupancy count) is bounded by COORDINATOR_TIMEOUT_MS: a call that stalls instead of failing would otherwise hold the shared in-flight answer forever, so /v1/ready would never answer (review 900c1e14.1).
 *
 * The answer, ready or not, is cached for READY_CACHE_MS and computed once per isolate at a time, so polling the endpoint cannot drive the issuer into a mint storm, nor the coordinator into one request per poll.
 */

import { type CapacityCount, capacityStub, type ExecutorCapacity } from './capacity';
import type { ForwardEnv } from './egress';
import { bounded } from './org-executor-support';

export const READY_CACHE_MS = 30_000;

/** The scopes an issued executor token must carry. */
const REQUIRED_SCOPES = ['proxy:exec', 'audit:write'] as const;

/** The header the account Worker attaches to its internal occupancy request. */
const INTERNAL_CREDENTIAL_HEADER = 'x-rediacc-internal';

export interface ReadyEnv extends ForwardEnv {
  CF_VERSION_METADATA?: WorkerVersionMetadata;
  EXECUTOR_CAPACITY?: DurableObjectNamespace<ExecutorCapacity>;
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
  if (reason !== undefined) return notReady(reason);
  return { status: 200, body: { ready: true, workerVersion } };
}

/** The coordinator's live count with only its four integers copied out, or undefined without the binding or when the coordinator cannot answer. */
async function executorCount(env: ReadyEnv): Promise<CapacityCount | undefined> {
  if (!env.EXECUTOR_CAPACITY) return undefined;
  try {
    const { total, heavy, cap, heavyCap } = await bounded(
      capacityStub(env.EXECUTOR_CAPACITY).count()
    );
    return { total, heavy, cap, heavyCap };
  } catch {
    console.warn('proxy: occupancy: executor count unavailable');
    return undefined;
  }
}

/** Ask the issuer's `probe()`: undefined when it answers ok with every required scope, otherwise the reason code. */
async function issuerProbeFailure(env: ReadyEnv): Promise<string | undefined> {
  if (!env.ISSUER) return 'no-issuer';
  let answer: { ok?: unknown; scopes?: unknown } | undefined;
  try {
    answer = await bounded(env.ISSUER.probe());
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
    const response = await bounded(env.ACCOUNT ? env.ACCOUNT.fetch(url) : fetch(url));
    return response.ok ? undefined : `server-info-http-${response.status}`;
  } catch {
    return 'server-info-unreachable';
  }
}

function notFound(): Response {
  return new Response('Not Found', { status: 404 });
}

/**
 * `GET /v1/internal/occupancy`: the coordinator's count, to the account Worker only. A wrong method, a missing credential and one the issuer does not verify (forged, expired, or an issuer that cannot answer) all answer the same bare 404 as an unknown path, so the route cannot be told from one that does not exist. A verified caller gets `{ executors }`, or a 503 when the coordinator cannot answer.
 */
export async function internalOccupancy(request: Request, env: ReadyEnv): Promise<Response> {
  if (request.method !== 'GET') return notFound();
  const credential = request.headers.get(INTERNAL_CREDENTIAL_HEADER);
  if (!credential || !env.ISSUER) return notFound();
  let verified: unknown;
  try {
    verified = await bounded(env.ISSUER.verifyInternal(credential));
  } catch {
    return notFound();
  }
  if (verified !== true) return notFound();
  const executors = await executorCount(env);
  if (executors === undefined) {
    return Response.json({ error: 'occupancy unavailable' }, { status: 503 });
  }
  return Response.json({ executors });
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
