/**
 * `GET /v1/ready`: whether this deployed Worker can act as the executor right now.
 *
 * Unauthenticated, so a deploy smoke can poll it. There is no org-less token to introspect, so it asks the issuer's `probe()` (writes nothing and mints nothing: the issuer env parses, D1 answers, and the scopes an issued token would carry are listed) and then `GET server-info` over ACCOUNT, which together prove the ISSUER binding answers, the ACCOUNT binding answers, and a token would carry the scopes the executor needs. It answers 200 `{ ready: true, workerVersion }` with the `[version_metadata]` id, which is how the smoke tells the new version from an old one still rolling out, or 503 `{ ready: false, reason }` with a reason code.
 *
 * A ready answer on a version with the EXECUTOR_CAPACITY binding also carries `executors`, the coordinator's `count()`: how many executor containers hold a live lease (`total`, of which `heavy`) and the caps in force. It is what a bench drill reads to watch a slot free or a heavy start land (agent/plans/PLAN-executor-durable-object-policy.md box L0). The count never decides readiness: a coordinator that cannot answer, or does not answer within COORDINATOR_TIMEOUT_MS, leaves `executors` out, so the deploy smoke keeps meaning what it meant.
 *
 * What the unauthenticated route discloses, weighed (review 900c1e14.2): anyone who polls learns the deployment's aggregate executor occupancy, `total` and `heavy`, at most once per READY_CACHE_MS per isolate (the cache is per isolate, so several isolates or cold starts read it more often), and from the series when load rises and when heavy-tier runs start. It names no org, executor, placement or size of any one org, and the caps are the deployed config's, so no tenant's activity can be told apart from another's; on a deployment with a single active org the series is that org's activity timing, which is the residual cost. Against that, the drill needs the count without a credential, from the same smoke that polls readiness. The trade is accepted for that reason, and a deployment that must not publish occupancy drops the EXECUTOR_CAPACITY binding from this Worker's ready path.
 *
 * Each upstream call (the issuer probe, server-info, the coordinator count) is bounded by COORDINATOR_TIMEOUT_MS: a call that stalls instead of failing would otherwise hold the shared in-flight answer forever, so /v1/ready would never answer (review 900c1e14.1).
 *
 * The answer, ready or not, is cached for READY_CACHE_MS and computed once per isolate at a time, so polling the endpoint cannot drive the issuer into a mint storm, nor the coordinator into one request per poll.
 */

import { type CapacityCount, capacityStub, type ExecutorCapacity } from './capacity';
import type { ForwardEnv } from './egress';
import { bounded } from './org-executor-support';

export const READY_CACHE_MS = 30_000;

/** The scopes an issued executor token must carry. */
const REQUIRED_SCOPES = ['proxy:exec', 'audit:write'] as const;

export interface ReadyEnv extends ForwardEnv {
  CF_VERSION_METADATA?: WorkerVersionMetadata;
  EXECUTOR_CAPACITY?: DurableObjectNamespace<ExecutorCapacity>;
}

export type ReadyAnswer =
  | { status: 200; body: { ready: true; workerVersion: string; executors?: CapacityCount } }
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
  const executors = await executorCount(env);
  return {
    status: 200,
    body:
      executors === undefined
        ? { ready: true, workerVersion }
        : { ready: true, workerVersion, executors },
  };
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
    console.warn('proxy: ready: executor count unavailable');
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
