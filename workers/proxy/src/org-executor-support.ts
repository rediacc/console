/**
 * The constants, types and stateless helpers of `OrgExecutor` (src/org-executor.ts), which re-exports the public ones. Nothing here holds Durable Object state.
 */

import type { AcquireAnswer, ExecutorCapacity, ExecutorSize } from './capacity';
import { EXECUTOR_TOKEN_PLACEHOLDER } from './egress';
import type { ExecutorIssuerRpc } from './issued-token';
import { executorName, placementOf } from './placement';
import type { ProbeVerdict } from './reachability';

/** The host the container addresses the account server by; `interceptOutboundHttp` routes it to the `AccountEgress` entrypoint. A container's own public egress is outside Cloudflare's ranges: on bench (2026-10-24) every introspection, executor-token request, config pull and audit post a container made to ACCOUNT_URL got 403 "outside Cloudflare ranges" while the Worker's own binding calls answered 200. The name resolves nowhere, so an egress that somehow escaped interception fails at DNS rather than reaching the internet. */
export const ACCOUNT_EGRESS_HOST = 'account.internal';
/** The main-module export the intercept binds, through `ctx.exports` (Design A: per-instance props). */
const ACCOUNT_EGRESS_ENTRYPOINT = 'AccountEgress';
/** `rdc serve` listens here. */
export const EXECUTOR_PORT = 8080;
/** The image key under `[containers.images]` in the wrangler config. */
export const EXECUTOR_IMAGE_KEY = 'executor';
/** Readiness: poll every READY_POLL_MS for at most READY_TIMEOUT_MS. */
export const READY_POLL_MS = 100;
export const READY_TIMEOUT_MS = 20_000;
/** A request renews the lease at most this often; the idle alarm renews while a request is in flight. */
export const RENEW_THROTTLE_MS = 30_000;
/** A coordinator or issuer call that takes longer than this counts as failed, and a failed coordinator refuses a start (fail closed). */
export const COORDINATOR_TIMEOUT_MS = 5_000;
/** An OOM-killed process exits with 128 + SIGKILL. */
const OOM_EXIT_CODE = 137;

const DEFAULT_REGION = 'eu';
export const RECORD_KEY = 'executor';
export const ORG_KEY = 'org';
export const OOM_KEY = 'oomAt';
/** When an exit out of memory happened on a HEAVY container, the case with no larger size to escalate to. */
export const OOM_HEAVY_KEY = 'oomHeavyAt';
/** The epoch-ms times of the egress-unreachable reports still inside UNREACHABLE_WINDOW_MS. */
export const UNREACHABLE_KEY = 'egressUnreachable';
/** The time of the latest egress-unreachable report, which the pin answer reads as `egressUnreachableRecent`. */
export const UNREACHABLE_AT_KEY = 'egressUnreachableAt';
/** Set once the issuer moved the org to another placement: `{ to }`, the placement it moved to. */
export const RETIRED_KEY = 'retired';

/** The props the egress entrypoint receives: set only here, by Durable Object code, never by the container or the caller. The egress cross-checks `containerId === env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)).toString()`. */
export interface ExecutorEgressProps {
  orgId: string;
  placement: number;
  containerId: string;
}

/** What the issuer's `relocate(orgId, fromPlacement)` answers (workers/account/src/index.ts, the `ExecutorIssuer` entrypoint). */
export type RelocateAnswer =
  | { ok: true; placement: number }
  | { ok: false; reason: 'stale' | 'budget'; placement: number }
  | { ok: false; reason: 'unknown-org' };

/** The env slice OrgExecutor reads. */
export interface OrgExecutorEnv {
  ORG_EXECUTOR: { idFromName(name: string): DurableObjectId };
  EXECUTOR_CAPACITY: DurableObjectNamespace<ExecutorCapacity>;
  /** The account Worker's `ExecutorIssuer`, called only by `recordEgressUnreachable` at the threshold. Without it a report never relocates. */
  ISSUER?: Pick<ExecutorIssuerRpc, 'relocate'>;
  /** Region label, handed to the executor as REDIACC_REGION; `eu` when unset or empty. */
  REGION?: string;
}

/** What a running container was started with, kept in Durable Object storage so a restarted instance can recover it. */
export interface ExecutorRecord {
  orgId: string;
  placement: number;
  size: ExecutorSize;
  image: string;
  startedAt: number;
}

/** The refusal codes the Worker relays: `EXECUTOR_CAPACITY` is a 503 with `Retry-After: 30`, `EXECUTOR_START_FAILED` a plain 503. `EXECUTOR_RELOCATED` means this instance retired: the Worker asks the issuer for the placement again. */
export type ExecutorRefusalCode =
  | 'EXECUTOR_CAPACITY'
  | 'EXECUTOR_START_FAILED'
  | 'EXECUTOR_RELOCATED';

export type Refusal = { ok: false; code: ExecutorRefusalCode; reason: string };

/** A start's answer, before the pin adds the report flag. */
export type StartAnswer = { ok: true; size: ExecutorSize } | Refusal;

/** The answer to `pin`. `size` is the size the container runs on, which stays the started size while it runs. `egressUnreachableRecent` is true while an egress-unreachable report is inside UNREACHABLE_WINDOW_MS, so the Worker needs no extra call to name the outcome. */
export type PinAnswer =
  | { ok: true; size: ExecutorSize; egressUnreachableRecent: boolean }
  | Refusal;

/** The answer to `recordEgressUnreachable`: the count inside the window, whether the org moved, and whether this report counted with the probe verdict that decided it, or a refusal with its reason. */
export type EgressReportAnswer =
  | {
      ok: true;
      count: number;
      threshold: number;
      relocated: boolean;
      /** Whether this report was added to the count: only a `reachable` probe counts. */
      counted: boolean;
      probe: ProbeVerdict;
    }
  | { ok: false; reason: string };

/** Who this instance serves, set once by `pin` and kept in storage. */
export interface PinnedExecutor {
  orgId: string;
  placement: number;
}

type EgressFactory = (options: { props: ExecutorEgressProps }) => Fetcher;

export type ExitResult = { clean: true } | { clean: false; error: unknown };

/**
 * The environment `rdc serve --mode container` boots with: exactly these four names.
 *
 * REDIACC_TOKEN is the placeholder that authenticates nothing; the egress swaps it for the org's issued token, so no real token ever enters the container.
 */
export function executorEnv(
  env: Pick<OrgExecutorEnv, 'REGION'>,
  orgId: string
): Record<string, string> {
  return {
    REDIACC_TOKEN: EXECUTOR_TOKEN_PLACEHOLDER,
    REDIACC_ACCOUNT_SERVER: `http://${ACCOUNT_EGRESS_HOST}`,
    REDIACC_REGION: env.REGION === undefined || env.REGION === '' ? DEFAULT_REGION : env.REGION,
    REDIACC_EXECUTOR_ORG_ID: orgId,
  };
}

const UNIT_MS: Record<string, number> = {
  '': 1_000,
  s: 1_000,
  m: 60_000,
  h: 3_600_000,
};

/** A `sleepAfter` literal (`'90s'`, `'2m'`, `'1h'`, or plain seconds) in milliseconds. */
export function durationMs(value: string): number {
  const match = /^(\d+)(s|m|h|)$/.exec(value);
  if (!match) throw new Error(`invalid duration: ${value}`);
  return Number.parseInt(match[1], 10) * UNIT_MS[match[2]];
}

/** Whether a `monitor()` rejection is an out-of-memory exit: exit code 137, or an error naming OOM. */
export function isOomExit(error: unknown): boolean {
  const code = (error as { exitCode?: unknown } | null | undefined)?.exitCode;
  if (code === OOM_EXIT_CODE) return true;
  let message = '';
  if (error instanceof Error) message = error.message;
  else if (typeof error === 'string') message = error;
  return /\bOOM\b|out of memory|exit(?:ed)?(?: with)?(?: code)? 137\b/i.test(message);
}

export function refusal(code: ExecutorRefusalCode, reason: string): Refusal {
  console.warn(`proxy: org executor refused: ${reason}`);
  return { ok: false, code, reason };
}

export function refusalResponse(code: ExecutorRefusalCode): Response {
  if (code === 'EXECUTOR_CAPACITY') {
    return Response.json(
      { error: 'No executor capacity is free right now.', code },
      { status: 503, headers: { 'retry-after': '30' } }
    );
  }
  if (code === 'EXECUTOR_RELOCATED') {
    return Response.json({ error: "This org's executor has moved.", code }, { status: 503 });
  }
  return Response.json({ error: 'The executor could not be started.', code }, { status: 503 });
}

/** A stored pin, or undefined for anything that is not one. */
export function pinnedFrom(value: unknown): PinnedExecutor | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { orgId, placement } = value as Record<string, unknown>;
  const valid = placementOf(placement);
  if (typeof orgId !== 'string' || orgId === '' || valid === undefined) return undefined;
  return { orgId, placement: valid };
}

export const wait = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** A coordinator or issuer call bounded by COORDINATOR_TIMEOUT_MS; a timeout rejects like any other failure. */
export async function bounded<T>(call: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('coordinator-timeout')), COORDINATOR_TIMEOUT_MS);
  });
  try {
    return await Promise.race([call, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The incoming request re-addressed to plain `http:`, keeping its method, headers, body and signal. A container TCP port speaks HTTP, so it refuses the `https://executor.internal/...` URL the proxy routes with.
 */
export function containerRequest(request: Request): Request {
  const url = new URL(request.url);
  url.protocol = 'http:';
  return new Request(url, request);
}

/** The name and message of a caught error, for a log line. Never the request or its content. */
export function errorSummary(error: unknown): { name: string; message: string } {
  if (error instanceof Error) return { name: error.name, message: error.message };
  return { name: typeof error, message: String(error) };
}

/** Whether the executor's health route answers 2xx. A refused connection means it is not listening yet. */
export async function healthy(container: Container): Promise<boolean> {
  try {
    const response = await container.getTcpPort(EXECUTOR_PORT).fetch('http://container/v1/health');
    await response.body?.cancel();
    return response.ok;
  } catch {
    return false;
  }
}

/** The response body, byte for byte, with `done` called once when it closes, errors or is cancelled, rather than when the headers arrive. */
export function trackBody(
  body: ReadableStream<Uint8Array>,
  done: () => void
): ReadableStream<Uint8Array> {
  const reader = body.getReader();
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    done();
  };
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const chunk = await reader.read();
        if (chunk.done) {
          finish();
          controller.close();
        } else {
          controller.enqueue(chunk.value);
        }
      } catch (error) {
        finish();
        controller.error(error);
      }
    },
    cancel(reason) {
      finish();
      return reader.cancel(reason);
    },
  });
}

/** Ask the coordinator for a slot, failing closed: a throw or a timeout is a refusal, never an uncounted start. */
export async function acquireLease(
  capacity: DurableObjectStub<ExecutorCapacity>,
  orgId: string,
  placement: number,
  size: ExecutorSize
): Promise<AcquireAnswer | 'failed'> {
  try {
    return await bounded(
      capacity.acquire(executorName(orgId, placement), size) as Promise<AcquireAnswer>
    );
  } catch {
    return 'failed';
  }
}

export async function releaseLease(
  capacity: DurableObjectStub<ExecutorCapacity>,
  orgId: string | undefined,
  placement: number | undefined
): Promise<void> {
  if (orgId === undefined || placement === undefined) return;
  try {
    await bounded(capacity.release(executorName(orgId, placement)));
  } catch {
    // The lease expires on its own after LEASE_MS.
    console.warn('proxy: org executor release failed');
  }
}

/** Route `account.internal` to the egress entrypoint with the instance's props. Registering again replaces the props without dropping open connections. */
export async function registerEgress(
  ctx: DurableObjectState,
  container: Container,
  orgId: string,
  placement: number
): Promise<void> {
  const factory = (ctx.exports as unknown as Record<string, EgressFactory | undefined>)[
    ACCOUNT_EGRESS_ENTRYPOINT
  ];
  if (typeof factory !== 'function') throw new Error('egress-entrypoint-missing');
  const props: ExecutorEgressProps = { orgId, placement, containerId: ctx.id.toString() };
  await container.interceptOutboundHttp(ACCOUNT_EGRESS_HOST, factory({ props }));
}
