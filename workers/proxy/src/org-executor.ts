/**
 * `OrgExecutor`: one org's executor container under the `durable_object` scheduling policy (agent/plans/PLAN-executor-durable-object-policy.md Design items 2 and 5, box W1).
 *
 * The frozen @cloudflare/containers `Container` class cannot run under the new policy, so this class drives `this.ctx.container` directly and imports nothing from that library. It rebuilds the helpers the proxy took from it: the start with per-instance env and outbound interception, the port readiness check, request proxying, and the `sleepAfter` idle timer. It adds what the policy moves into code: the lease on the target's cap (src/capacity.ts), the per-start instance size, the image-drift restart, and recovery after the Durable Object restarts under a running container.
 *
 * The Worker calls `pin(orgId, placement, size)` with the org and placement `ExecutorIssuer.route` named, then forwards the request with `fetch`. Every refusal is an answer with a code, never error text for the Worker to guess at.
 *
 * Relocation (agent/plans/PLAN-org-executor-connect-timeout-relocate.md Design item 5): the executor reports a machine it cannot reach through `recordEgressUnreachable`. At UNREACHABLE_THRESHOLD reports within UNREACHABLE_WINDOW_MS the instance asks the issuer to bump the org's placement, and on success it retires: `pin` refuses with `EXECUTOR_RELOCATED`, the lease is never re-acquired, and the container stops once nothing is in flight. The retired instance never touches the new name, so the new instance is placed the way a fresh org's is.
 */

import { DurableObject } from 'cloudflare:workers';
import {
  type AcquireAnswer,
  capacityStub,
  type ExecutorCapacity,
  type ExecutorSize,
} from './capacity';
import { EXECUTOR_TOKEN_PLACEHOLDER } from './egress';
import type { ExecutorIssuerRpc } from './issued-token';
import { executorName, placementOf, UNREACHABLE_THRESHOLD, unreachableRecent } from './placement';
import { INSTANCE_BY_SIZE } from './sizing';

/** The host the container addresses the account server by; the intercept routes it to the egress entrypoint (src/index.ts, the `ExecutorContainer` comment, says why). */
export const ACCOUNT_EGRESS_HOST = 'account.internal';
/** The main-module export the intercept binds, through `ctx.exports` (Design A: per-instance props). */
export const ACCOUNT_EGRESS_ENTRYPOINT = 'AccountEgress';
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
const RECORD_KEY = 'executor';
const ORG_KEY = 'org';
const OOM_KEY = 'oomAt';
/** When an exit out of memory happened on a HEAVY container, the case with no larger size to escalate to. */
const OOM_HEAVY_KEY = 'oomHeavyAt';
/** The epoch-ms times of the egress-unreachable reports still inside UNREACHABLE_WINDOW_MS. */
const UNREACHABLE_KEY = 'egressUnreachable';
/** The time of the latest egress-unreachable report, which the pin answer reads as `egressUnreachableRecent`. */
const UNREACHABLE_AT_KEY = 'egressUnreachableAt';
/** Set once the issuer moved the org to another placement: `{ to }`, the placement it moved to. */
const RETIRED_KEY = 'retired';

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

type Refusal = { ok: false; code: ExecutorRefusalCode; reason: string };

/** A start's answer, before the pin adds the report flag. */
type StartAnswer = { ok: true; size: ExecutorSize } | Refusal;

/** The answer to `pin`. `size` is the size the container runs on, which stays the started size while it runs. `egressUnreachableRecent` is true while an egress-unreachable report is inside UNREACHABLE_WINDOW_MS, so the Worker needs no extra call to name the outcome. */
export type PinAnswer =
  | { ok: true; size: ExecutorSize; egressUnreachableRecent: boolean }
  | Refusal;

/** The answer to `recordEgressUnreachable`: the count inside the window and whether the org moved, or a refusal with its reason. */
export type EgressReportAnswer =
  | { ok: true; count: number; threshold: number; relocated: boolean }
  | { ok: false; reason: string };

/** Who this instance serves, set once by `pin` and kept in storage. */
interface PinnedExecutor {
  orgId: string;
  placement: number;
}

type EgressFactory = (options: { props: ExecutorEgressProps }) => Fetcher;

type ExitResult = { clean: true } | { clean: false; error: unknown };

/**
 * The environment `rdc serve --mode container` boots with: exactly these four names, on both backends (src/index.ts `ExecutorContainer.pin` uses it too).
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

const UNIT_MS: Record<string, number> = { s: 1_000, m: 60_000, h: 3_600_000 };

/** A `sleepAfter` literal (`'90s'`, `'2m'`, `'1h'`, or plain seconds) in milliseconds. */
export function durationMs(value: string): number {
  const match = /^(\d+)(s|m|h)?$/.exec(value);
  if (!match) throw new Error(`invalid duration: ${value}`);
  return Number.parseInt(match[1], 10) * UNIT_MS[match[2] ?? 's'];
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

function refusal(code: ExecutorRefusalCode, reason: string): Refusal {
  console.warn(`proxy: org executor refused: ${reason}`);
  return { ok: false, code, reason };
}

function refusalResponse(code: ExecutorRefusalCode): Response {
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
function pinnedFrom(value: unknown): PinnedExecutor | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { orgId, placement } = value as Record<string, unknown>;
  const valid = placementOf(placement);
  if (typeof orgId !== 'string' || orgId === '' || valid === undefined) return undefined;
  return { orgId, placement: valid };
}

const wait = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** A coordinator or issuer call bounded by COORDINATOR_TIMEOUT_MS; a timeout rejects like any other failure. */
async function bounded<T>(call: Promise<T>): Promise<T> {
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
 * The incoming request re-addressed to plain `http:`, keeping its method, headers, body and signal. A container TCP port speaks HTTP, so it refuses the `https://executor.internal/...` URL the proxy routes with; the replaced `@cloudflare/containers` library made the same swap before its port fetch.
 */
function containerRequest(request: Request): Request {
  const url = new URL(request.url);
  url.protocol = 'http:';
  return new Request(url, request);
}

/** The name and message of a caught error, for a log line. Never the request or its content. */
function errorSummary(error: unknown): { name: string; message: string } {
  if (error instanceof Error) return { name: error.name, message: error.message };
  return { name: typeof error, message: String(error) };
}

/** Whether the executor's health route answers 2xx. A refused connection means it is not listening yet. */
async function healthy(container: Container): Promise<boolean> {
  try {
    const response = await container.getTcpPort(EXECUTOR_PORT).fetch('http://container/v1/health');
    await response.body?.cancel();
    return response.ok;
  } catch {
    return false;
  }
}

/** The response body, byte for byte, with `done` called once when it closes, errors or is cancelled, rather than when the headers arrive. */
function trackBody(body: ReadableStream<Uint8Array>, done: () => void): ReadableStream<Uint8Array> {
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

/** The per-org executor Durable Object. See the module comment. */
export class OrgExecutor extends DurableObject<OrgExecutorEnv> {
  /**
   * Idle timeout before the container stops and its slot is released.
   *
   * A literal, which the cost guard reads (check_proxy_cost_guard `sleepAfter` rule). Long enough that a session of console work reuses one warm executor, short enough that an idle org stops costing memory.
   */
  sleepAfter = '2m';

  /** The org and placement this instance serves, set once by `pin` and kept in storage. */
  private pinned: PinnedExecutor | undefined;
  /** What the running container was started with, or undefined when none runs. */
  private record: ExecutorRecord | undefined;
  /** Requests whose response body is still open. */
  private inFlight = 0;
  private lastActivity = 0;
  private lastRenew = 0;
  /** Set when the lease is lost and cannot be re-acquired, or the instance retired: in-flight requests finish, then the container is destroyed. */
  private draining = false;
  /** The placement the org moved to, once this instance retired. A retired instance never starts, never re-acquires and refuses every pin. */
  private retiredTo: number | undefined;
  /** The latest egress-unreachable report (epoch ms), mirrored from storage. */
  private unreachableAt: number | undefined;
  /** The report being counted, which a concurrent report waits on, so the issuer is asked at most once per crossing. */
  private reporting: Promise<EgressReportAnswer> | undefined;
  /** Bumped on every start and deliberate destroy, so a stale `monitor()` settlement is ignored. */
  private generation = 0;
  /** How the current generation's container exited, once it has. */
  private exited: ExitResult | undefined;
  /** The start or restart in progress, which a concurrent `pin` or `fetch` waits on. */
  private startup: Promise<StartAnswer> | undefined;

  constructor(ctx: DurableObjectState, env: OrgExecutorEnv) {
    super(ctx, env);
    void ctx.blockConcurrencyWhile(() => this.recover());
  }

  /**
   * Pin this instance to `orgId` at `placement` and make sure its container runs, starting it on `size` if none does. A running container keeps the size it started with.
   *
   * The instance must be the Durable Object named `executorName(orgId, placement)`, and a second org or placement is refused, so an instance only ever serves its own. A retired instance refuses with `EXECUTOR_RELOCATED`.
   */
  async pin(orgId: string, placement: number, size: ExecutorSize): Promise<PinAnswer> {
    const refused = this.pinRefusal(orgId, placement, size);
    if (refused !== undefined) return refusal('EXECUTOR_START_FAILED', refused);
    if (this.isRetired()) return refusal('EXECUTOR_RELOCATED', 'retired');
    if (this.pinned === undefined) {
      this.pinned = { orgId, placement };
      await this.ctx.storage.put(ORG_KEY, this.pinned);
    }
    return this.withReportFlag(await this.ensureRunning(orgId, placement, size));
  }

  /** The start half of `pin`, after the identity checks. */
  private async ensureRunning(
    orgId: string,
    placement: number,
    size: ExecutorSize
  ): Promise<StartAnswer> {
    await this.touch();

    // Wait out a start in progress, then decide with no await between the check and `serialized`, which sets `this.startup` synchronously: two pins arriving together can then never both start a container.
    while (this.startup !== undefined) {
      await this.startup.catch(() => undefined);
    }
    if (this.isRetired()) return refusal('EXECUTOR_RELOCATED', 'retired');
    if (this.isDraining()) return refusal('EXECUTOR_CAPACITY', 'draining');

    const container = this.ctx.container;
    if (container?.running && this.record) {
      const image = this.currentImage();
      // A running instance does not take application rollouts. The drift check runs on each pin, so a busy container moves to the new image at the first pin that finds nothing in flight, and an idle one either gets that pin or stops at `sleepAfter` and starts on the new image. A version that names no image is not drift: the running container keeps serving.
      if (image !== undefined && this.record.image !== image && this.inFlight === 0) {
        const running = this.record;
        return this.serialized(() => this.restartOnNewImage(running));
      }
      return { ok: true, size: this.record.size };
    }
    return this.serialized(() => this.start(orgId, placement, size));
  }

  /** Add `egressUnreachableRecent` to an ok answer. */
  private withReportFlag(answer: StartAnswer): PinAnswer {
    if (!answer.ok) return answer;
    return {
      ...answer,
      egressUnreachableRecent: unreachableRecent(this.unreachableAt, Date.now()),
    };
  }

  /**
   * Count one egress-unreachable report from this instance's container. Below UNREACHABLE_THRESHOLD reports within UNREACHABLE_WINDOW_MS it only counts. At the threshold it asks the issuer to move the org to the next placement: on `ok` or `stale` (another caller moved it already) the instance retires and drains; on `budget` or a failure the org stays where it is.
   *
   * Refused for an org or placement that is not this instance's.
   */
  async recordEgressUnreachable(orgId: string, placement: number): Promise<EgressReportAnswer> {
    const refused = this.reportRefusal(orgId, placement);
    if (refused !== undefined) {
      console.warn(`proxy: org executor egress report refused: ${refused}`);
      return { ok: false, reason: refused };
    }
    while (this.reporting !== undefined) {
      await this.reporting.catch(() => undefined);
    }
    const reporting = this.countReport(orgId, placement).finally(() => {
      if (this.reporting === reporting) this.reporting = undefined;
    });
    this.reporting = reporting;
    return reporting;
  }

  /** Why a report for `orgId` at `placement` is refused, or undefined when it is admitted. */
  private reportRefusal(orgId: string, placement: number): string | undefined {
    if (typeof orgId !== 'string' || orgId === '') return 'report-org-invalid';
    if (placementOf(placement) === undefined) return 'report-placement-invalid';
    if (!this.ctx.id.equals(this.env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)))) {
      return 'report-id-mismatch';
    }
    const pinned = this.pinned;
    if (pinned !== undefined && (pinned.orgId !== orgId || pinned.placement !== placement)) {
      return 'report-org-conflict';
    }
    return undefined;
  }

  /** Append the report, prune the window, and relocate at the threshold. */
  private async countReport(orgId: string, placement: number): Promise<EgressReportAnswer> {
    const now = Date.now();
    const stored = (await this.ctx.storage.get<number[]>(UNREACHABLE_KEY)) ?? [];
    const recent = [...stored, now].filter((at) => unreachableRecent(at, now));
    this.unreachableAt = now;
    await this.ctx.storage.put(UNREACHABLE_KEY, recent);
    await this.ctx.storage.put(UNREACHABLE_AT_KEY, now);
    const count = recent.length;
    const answer = (relocated: boolean): EgressReportAnswer => ({
      ok: true,
      count,
      threshold: UNREACHABLE_THRESHOLD,
      relocated,
    });
    if (this.isRetired()) return answer(true);
    console.warn(
      `proxy: org executor egress unreachable ${count}/${UNREACHABLE_THRESHOLD} at p${placement}`
    );
    if (count < UNREACHABLE_THRESHOLD) return answer(false);

    const moved = await this.relocate(orgId, placement);
    if (moved === undefined) return answer(false);
    await this.retire(moved);
    return answer(true);
  }

  /** Ask the issuer to move the org off `placement`, bounded like the coordinator calls. Answers the placement it moved to, or undefined when it stays. */
  private async relocate(orgId: string, placement: number): Promise<number | undefined> {
    const issuer = this.env.ISSUER;
    if (issuer === undefined) {
      console.warn('proxy: org executor relocate refused: no-issuer');
      return undefined;
    }
    let moved: RelocateAnswer;
    try {
      moved = await bounded(issuer.relocate(orgId, placement));
    } catch {
      console.warn('proxy: org executor relocate refused: failed');
      return undefined;
    }
    if (moved.ok || moved.reason === 'stale') {
      console.warn(`proxy: org executor relocated p${placement}->p${moved.placement}`);
      return moved.placement;
    }
    console.warn(`proxy: org executor relocate refused: ${moved.reason}`);
    return undefined;
  }

  /** Retire this instance: kept in storage so a restart stays retired, then drain. The request whose report caused the move still ends with its result line before the container goes. */
  private async retire(to: number): Promise<void> {
    this.retiredTo = to;
    this.draining = true;
    try {
      await this.ctx.storage.put(RETIRED_KEY, { to });
    } catch {
      console.warn('proxy: org executor retired state not stored');
    }
    if (this.inFlight === 0) await this.finishDrain();
  }

  /** Read through a method so the state is re-read after every await rather than narrowed. */
  private isRetired(): boolean {
    return this.retiredTo !== undefined;
  }

  /**
   * Move a running container to the deployed image. The lease is secured before the old container is destroyed: a coordinator that refuses (or fails) leaves the old container serving and the drift is retried at a later pin, rather than leaving the org with no container. The lease taken here is the one the new container runs on (`startLeased`), so no second acquire can fail once the old container is gone.
   */
  private async restartOnNewImage(running: ExecutorRecord): Promise<StartAnswer> {
    const lease = await this.acquireLease(running.orgId, running.placement, running.size);
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor image restart deferred: no lease');
      return { ok: true, size: running.size };
    }
    this.lastRenew = Date.now();
    await this.stopContainer('image-drift');
    return this.startLeased(running.orgId, running.placement, running.size);
  }

  /** Why `pin(orgId, placement, size)` is refused, or undefined when it is admitted. */
  private pinRefusal(orgId: string, placement: number, size: ExecutorSize): string | undefined {
    if (typeof orgId !== 'string' || orgId === '') return 'pin-org-invalid';
    if (placementOf(placement) === undefined) return 'pin-placement-invalid';
    if (!this.ctx.id.equals(this.env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)))) {
      return 'pin-id-mismatch';
    }
    const pinned = this.pinned;
    if (pinned !== undefined && (pinned.orgId !== orgId || pinned.placement !== placement)) {
      return 'pin-org-conflict';
    }
    if (size !== 'light' && size !== 'heavy') return 'pin-size-invalid';
    return undefined;
  }

  /** When this org's executor last exited out of memory (epoch ms), or undefined. The Worker reads it to size the next start (src/sizing.ts `chooseSize`). */
  async oomAt(): Promise<number | undefined> {
    return await this.ctx.storage.get<number>(OOM_KEY);
  }

  /** When this org's executor last exited out of memory while HEAVY (epoch ms), or undefined. The Worker marks a request served on a heavy container with this flag as `oom-heavy`. */
  async oomHeavyAt(): Promise<number | undefined> {
    return await this.ctx.storage.get<number>(OOM_HEAVY_KEY);
  }

  /** Wait out any start or restart in progress. */
  private async startupSettled(): Promise<void> {
    while (this.startup !== undefined) await this.startup.catch(() => undefined);
  }

  /** Read through a method so the flag is re-read after every await rather than narrowed. */
  private isDraining(): boolean {
    return this.draining;
  }

  /** Forward a request to the container and stream its response back untouched, counting it in flight until the body closes. */
  override async fetch(request: Request): Promise<Response> {
    await this.startupSettled();
    const container = this.ctx.container;
    if (this.isRetired()) return refusalResponse('EXECUTOR_RELOCATED');
    if (this.isDraining()) return refusalResponse('EXECUTOR_CAPACITY');
    if (!container?.running || !this.record) return refusalResponse('EXECUTOR_START_FAILED');

    this.inFlight += 1;
    let released = false;
    const done = () => {
      if (released) return;
      released = true;
      this.inFlight -= 1;
      void this.afterRequest();
    };
    try {
      await this.touch();
      if (!(await this.holdLease())) {
        done();
        return refusalResponse('EXECUTOR_CAPACITY');
      }
      const response = await container.getTcpPort(EXECUTOR_PORT).fetch(containerRequest(request));
      if (response.body === null) {
        done();
        return response;
      }
      return new Response(trackBody(response.body, done), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch (error) {
      done();
      console.warn('proxy: org executor forward failed', errorSummary(error));
      return Response.json(
        { error: 'The executor did not answer.', code: 'EXECUTOR_UNREACHABLE' },
        { status: 502 }
      );
    }
  }

  /**
   * The idle timer. With requests in flight it renews the lease and re-arms, so a long NDJSON stream holds its slot. With none in flight and `sleepAfter` passed since the last activity, it destroys the container and releases the slot.
   */
  override async alarm(): Promise<void> {
    const container = this.ctx.container;
    if (!container?.running || !this.record) return;
    const now = Date.now();
    const idleMs = durationMs(this.sleepAfter);
    if (this.inFlight > 0) {
      await this.holdLease(true);
      await this.ctx.storage.setAlarm(now + idleMs);
      return;
    }
    if (now - this.lastActivity >= idleMs) {
      const { orgId, placement } = this.record;
      await this.stopContainer('idle');
      await this.releaseLease(orgId, placement);
      return;
    }
    await this.ctx.storage.setAlarm(this.lastActivity + idleMs);
  }

  /** The image the deployed version names for the executor. */
  private currentImage(): string | undefined {
    return this.ctx.container?.images[EXECUTOR_IMAGE_KEY];
  }

  private capacity(): DurableObjectStub<ExecutorCapacity> {
    return capacityStub(this.env.EXECUTOR_CAPACITY);
  }

  private serialized(run: () => Promise<StartAnswer>): Promise<StartAnswer> {
    const startup = run().finally(() => {
      if (this.startup === startup) this.startup = undefined;
    });
    this.startup = startup;
    return startup;
  }

  /** Record activity and arm the idle alarm at `lastActivity + sleepAfter`. */
  private async touch(): Promise<void> {
    this.lastActivity = Date.now();
    await this.ctx.storage.setAlarm(this.lastActivity + durationMs(this.sleepAfter));
  }

  /** A request finished: count the activity, and finish a drain once nothing is in flight. */
  private async afterRequest(): Promise<void> {
    try {
      await this.touch();
      if (this.isDraining() && this.inFlight === 0) await this.finishDrain();
    } catch {
      console.warn('proxy: org executor after-request bookkeeping failed');
    }
  }

  /** End a drain with nothing in flight: stop the container. A retired instance also releases its slot, which is keyed by its own name and so never the new placement's; a lost lease has no slot left to release. */
  private async finishDrain(): Promise<void> {
    const record = this.record;
    if (this.isRetired()) {
      await this.stopContainer('relocated');
      if (record) await this.releaseLease(record.orgId, record.placement);
    } else {
      await this.stopContainer('lease-lost');
    }
    this.draining = false;
  }

  /** Ask the coordinator for a slot, failing closed: a throw or a timeout is a refusal, never an uncounted start. */
  private async acquireLease(
    orgId: string,
    placement: number,
    size: ExecutorSize
  ): Promise<AcquireAnswer | 'failed'> {
    try {
      return await bounded(
        this.capacity().acquire(executorName(orgId, placement), size) as Promise<AcquireAnswer>
      );
    } catch {
      return 'failed';
    }
  }

  private async releaseLease(
    orgId: string | undefined,
    placement: number | undefined
  ): Promise<void> {
    if (orgId === undefined || placement === undefined) return;
    try {
      await bounded(this.capacity().release(executorName(orgId, placement)));
    } catch {
      // The lease expires on its own after LEASE_MS.
      console.warn('proxy: org executor release failed');
    }
  }

  /**
   * Keep the lease of the running container, renewing at most once per RENEW_THROTTLE_MS unless `force`. A lease the coordinator no longer holds is acquired again, except by a retired instance, which drains instead; when the acquire is refused, the instance drains and answers false.
   */
  private async holdLease(force = false): Promise<boolean> {
    const record = this.record;
    if (!record) return false;
    const now = Date.now();
    if (!force && now - this.lastRenew < RENEW_THROTTLE_MS) return true;
    let held: 'held' | 'not-held' | 'failed';
    try {
      held = await bounded(this.capacity().renew(executorName(record.orgId, record.placement)));
    } catch {
      held = 'failed';
    }
    if (held === 'held') {
      this.lastRenew = now;
      return true;
    }
    if (held === 'failed') {
      // A transient coordinator failure does not cut a running container off: its lease is still live until LEASE_MS after the last renew, and the next request or alarm retries.
      return true;
    }
    if (await this.reacquire(record, now)) return true;
    console.warn('proxy: org executor lease lost; draining');
    this.draining = true;
    if (this.inFlight === 0) await this.finishDrain();
    return false;
  }

  /** Acquire again a lease the coordinator no longer holds. A retired instance never does, so it cannot take a slot back. */
  private async reacquire(record: ExecutorRecord, now: number): Promise<boolean> {
    if (this.isRetired()) return false;
    const again = await this.acquireLease(record.orgId, record.placement, record.size);
    if (again === 'failed' || !again.ok) return false;
    this.lastRenew = now;
    return true;
  }

  /** The start sequence of Design item 5: lease, intercept, start, record, monitor, readiness. */
  private async start(orgId: string, placement: number, size: ExecutorSize): Promise<StartAnswer> {
    const container = this.ctx.container;
    if (!container) return refusal('EXECUTOR_START_FAILED', 'no-container');
    const image = this.currentImage();
    if (image === undefined) return refusal('EXECUTOR_START_FAILED', 'no-image');

    const lease = await this.acquireLease(orgId, placement, size);
    if (lease === 'failed') return refusal('EXECUTOR_START_FAILED', 'coordinator-failed');
    if (!lease.ok) return refusal('EXECUTOR_CAPACITY', lease.reason);
    this.lastRenew = Date.now();
    return this.startLeased(orgId, placement, size);
  }

  /** The start sequence after the lease is held: intercept, start, record, monitor, readiness. Releases the lease when the start fails. */
  private async startLeased(
    orgId: string,
    placement: number,
    size: ExecutorSize
  ): Promise<StartAnswer> {
    const container = this.ctx.container;
    if (!container) {
      await this.releaseLease(orgId, placement);
      return refusal('EXECUTOR_START_FAILED', 'no-container');
    }
    const image = this.currentImage();
    if (image === undefined) {
      await this.releaseLease(orgId, placement);
      return refusal('EXECUTOR_START_FAILED', 'no-image');
    }
    const failure = await this.launch(container, { orgId, placement, size, image });
    if (failure === undefined) return { ok: true, size };
    await this.stopContainer(failure.reason);
    // A container that exited on its own during readiness has had its slot released by `onExit` already.
    if (!failure.releasedByExit) await this.releaseLease(orgId, placement);
    return refusal('EXECUTOR_START_FAILED', failure.reason);
  }

  /** Register the intercept, start the container, record it, attach `monitor()` and wait for readiness. Answers undefined once ready, else why it failed and whether its own exit already released the slot. */
  private async launch(
    container: Container,
    run: Omit<ExecutorRecord, 'startedAt'>
  ): Promise<{ reason: string; releasedByExit: boolean } | undefined> {
    const { orgId, placement, size, image } = run;
    let generation: number | undefined;
    try {
      // Registered before `start`, so no egress call can escape to DNS in between.
      await this.registerEgress(container, orgId, placement);
      this.generation += 1;
      this.exited = undefined;
      container.start({
        image,
        enableInternet: true,
        env: executorEnv(this.env, orgId),
        ...INSTANCE_BY_SIZE[size],
      });
      // Attached before any await, so an exit right after start is not missed.
      this.attachMonitor(container);
      generation = this.generation;
      this.record = { orgId, placement, size, image, startedAt: Date.now() };
      await this.ctx.storage.put(RECORD_KEY, this.record);
      if (await this.waitReady(container, generation)) return undefined;
      return { reason: 'not-ready', releasedByExit: this.exitedIn(generation) };
    } catch {
      return {
        reason: 'start-threw',
        releasedByExit: generation !== undefined && this.exitedIn(generation),
      };
    }
  }

  /** Whether the container of `generation` exited on its own (its `onExit` ran). */
  private exitedIn(generation: number): boolean {
    return this.generation === generation && this.exited !== undefined;
  }

  /** Route `account.internal` to the egress entrypoint with this instance's props. Registering again replaces the props without dropping open connections. */
  private async registerEgress(
    container: Container,
    orgId: string,
    placement: number
  ): Promise<void> {
    const factory = (this.ctx.exports as unknown as Record<string, EgressFactory | undefined>)[
      ACCOUNT_EGRESS_ENTRYPOINT
    ];
    if (typeof factory !== 'function') throw new Error('egress-entrypoint-missing');
    const props: ExecutorEgressProps = { orgId, placement, containerId: this.ctx.id.toString() };
    await container.interceptOutboundHttp(ACCOUNT_EGRESS_HOST, factory({ props }));
  }

  /** Watch the current container's exit. A `monitor()` promise does not survive a Durable Object restart, so `recover` attaches it again. */
  private attachMonitor(container: Container): void {
    const generation = this.generation;
    container.monitor().then(
      () => this.onExit(generation, { clean: true }),
      (error: unknown) => this.onExit(generation, { clean: false, error })
    );
  }

  /** The container stopped on its own: forget it, release its slot, and flag an out-of-memory exit for the sizing rule. */
  private async onExit(generation: number, result: ExitResult): Promise<void> {
    if (generation !== this.generation) return;
    this.exited = result;
    const owner = this.record ?? this.pinned;
    const wasSize = this.record?.size;
    this.record = undefined;
    this.draining = false;
    try {
      if (!result.clean && isOomExit(result.error)) {
        console.warn(`proxy: org executor out of memory on ${wasSize ?? 'unknown'}`);
        const now = Date.now();
        await this.ctx.storage.put(OOM_KEY, now);
        if (wasSize === 'heavy') await this.ctx.storage.put(OOM_HEAVY_KEY, now);
      }
    } catch {
      console.warn('proxy: org executor exit bookkeeping failed');
    }
    // The record is deleted whatever the OOM flags did. If this delete also fails, the stale record is harmless: `recover` finds no running container and clears it, so a dead container is never recovered as running.
    try {
      await this.ctx.storage.delete(RECORD_KEY);
    } catch {
      console.warn('proxy: org executor record delete failed');
    }
    await this.releaseLease(owner?.orgId, owner?.placement);
  }

  /** Poll the health route until it answers 2xx. An exit during the poll, or READY_TIMEOUT_MS passing, is a failed start. */
  private async waitReady(container: Container, generation: number): Promise<boolean> {
    const deadline = Date.now() + READY_TIMEOUT_MS;
    for (;;) {
      if (this.generation !== generation || this.exited !== undefined) return false;
      if (await healthy(container)) {
        return this.generation === generation && this.exited === undefined;
      }
      if (Date.now() >= deadline) return false;
      await wait(READY_POLL_MS);
    }
  }

  /** Stop the container deliberately, so its exit is not mistaken for a crash, and forget its record. The lease is the caller's. */
  private async stopContainer(reason: string): Promise<void> {
    this.generation += 1;
    this.record = undefined;
    const container = this.ctx.container;
    try {
      if (container?.running) await container.destroy(reason);
    } catch {
      console.warn(`proxy: org executor destroy failed: ${reason}`);
    }
    try {
      await this.ctx.storage.delete(RECORD_KEY);
    } catch {
      console.warn('proxy: org executor record not cleared');
    }
  }

  /**
   * Recovery after the Durable Object restarts (a deploy, an eviction) under a running container: re-register the intercept with the stored props, re-attach `monitor()` and re-acquire the lease before serving. A container whose lease is refused, or whose record is gone or names no placement, is destroyed, since it would run uncounted. A retired instance destroys its container and releases its slot rather than serving.
   */
  private async recover(): Promise<void> {
    this.pinned = pinnedFrom(await this.ctx.storage.get(ORG_KEY));
    this.unreachableAt = await this.ctx.storage.get<number>(UNREACHABLE_AT_KEY);
    const retired = await this.ctx.storage.get<{ to?: unknown }>(RETIRED_KEY);
    this.retiredTo = placementOf(retired?.to);
    const stored = await this.ctx.storage.get<ExecutorRecord>(RECORD_KEY);
    const record = stored && placementOf(stored.placement) !== undefined ? stored : undefined;
    const container = this.ctx.container;
    if (!container?.running) {
      if (stored) {
        await this.ctx.storage.delete(RECORD_KEY);
        await this.releaseLease(record?.orgId, record?.placement);
      }
      return;
    }
    if (!record) {
      await this.stopContainer('unrecorded');
      return;
    }
    if (this.isRetired()) {
      await this.stopContainer('relocated');
      await this.releaseLease(record.orgId, record.placement);
      return;
    }
    this.record = record;
    this.generation += 1;
    this.exited = undefined;
    try {
      await this.registerEgress(container, record.orgId, record.placement);
    } catch {
      console.warn('proxy: org executor intercept not re-registered');
    }
    this.attachMonitor(container);
    const lease = await this.acquireLease(record.orgId, record.placement, record.size);
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor lease refused after restart; destroying');
      await this.stopContainer('lease-refused');
      return;
    }
    this.lastRenew = Date.now();
    await this.touch();
  }
}
