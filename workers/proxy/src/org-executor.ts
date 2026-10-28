/**
 * `OrgExecutor`: one org's executor container under the `durable_object` scheduling policy (agent/plans/PLAN-executor-durable-object-policy.md Design items 2 and 5, box W1).
 *
 * The frozen @cloudflare/containers `Container` class cannot run under the new policy, so this class drives `this.ctx.container` directly and imports nothing from that library. It rebuilds the helpers the proxy took from it: the start with per-instance env and outbound interception, the port readiness check, request proxying, and the `sleepAfter` idle timer. It adds what the policy moves into code: the lease on the target's cap (src/capacity.ts), the per-start instance size, the image-drift restart, and recovery after the Durable Object restarts under a running container.
 *
 * The Worker calls `pin(orgId, size)` with the org `ExecutorIssuer.route` named, then forwards the request with `fetch`. Every refusal is an answer with a code, never error text for the Worker to guess at.
 */

import { DurableObject } from 'cloudflare:workers';
import {
  type AcquireAnswer,
  capacityStub,
  type ExecutorCapacity,
  type ExecutorSize,
} from './capacity';
import { EXECUTOR_TOKEN_PLACEHOLDER } from './egress';

/** The host the container addresses the account server by; the intercept routes it to the egress entrypoint (src/index.ts ACCOUNT_EGRESS_HOST says why). */
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
/** A coordinator call that takes longer than this counts as failed, and a failed coordinator refuses a start (fail closed). */
export const COORDINATOR_TIMEOUT_MS = 5_000;
/** An OOM-killed process exits with 128 + SIGKILL. */
const OOM_EXIT_CODE = 137;

const DEFAULT_REGION = 'eu';
const RECORD_KEY = 'executor';
const ORG_KEY = 'org';
const OOM_KEY = 'oomAt';

/**
 * The instance each size class starts on. Each `instance:` value is a literal, which the cost guard (box G1) reads: LIGHT is the basic-equivalent custom size S1 chose (Spike record, DU3), HEAVY is `standard-1`.
 */
const INSTANCE_BY_SIZE = {
  light: { instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000 } },
  heavy: { instance: 'standard-1' },
} as const satisfies Record<ExecutorSize, Pick<ContainerStartupOptions, 'instance'>>;

/** The props the egress entrypoint receives: set only here, by Durable Object code, never by the container or the caller. The egress cross-checks `containerId === env.ORG_EXECUTOR.idFromName(orgId).toString()`. */
export interface ExecutorEgressProps {
  orgId: string;
  containerId: string;
}

/** The env slice OrgExecutor reads. */
export interface OrgExecutorEnv {
  ORG_EXECUTOR: { idFromName(name: string): DurableObjectId };
  EXECUTOR_CAPACITY: DurableObjectNamespace<ExecutorCapacity>;
  /** Region label, handed to the executor as REDIACC_REGION; `eu` when unset or empty. */
  REGION?: string;
}

/** What a running container was started with, kept in Durable Object storage so a restarted instance can recover it. */
export interface ExecutorRecord {
  orgId: string;
  size: ExecutorSize;
  image: string;
  startedAt: number;
}

/** The refusal codes the Worker relays: `EXECUTOR_CAPACITY` is a 503 with `Retry-After: 30`, `EXECUTOR_START_FAILED` a plain 503. */
export type ExecutorRefusalCode = 'EXECUTOR_CAPACITY' | 'EXECUTOR_START_FAILED';

/** The answer to `pin`. `size` is the size the container runs on, which stays the started size while it runs. */
export type PinAnswer =
  | { ok: true; size: ExecutorSize }
  | { ok: false; code: ExecutorRefusalCode; reason: string };

type EgressFactory = (options: { props: ExecutorEgressProps }) => Fetcher;

type ExitResult = { clean: true } | { clean: false; error: unknown };

/**
 * The environment `rdc serve --mode container` boots with: exactly these four names (the same set as src/index.ts `executorEnvVars`).
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

function refusal(code: ExecutorRefusalCode, reason: string): PinAnswer {
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
  return Response.json({ error: 'The executor could not be started.', code }, { status: 503 });
}

const wait = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** A coordinator call bounded by COORDINATOR_TIMEOUT_MS; a timeout rejects like any other coordinator failure. */
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

  /** The org this instance serves, set once by `pin` and kept in storage. */
  private pinnedOrg: string | undefined;
  /** What the running container was started with, or undefined when none runs. */
  private record: ExecutorRecord | undefined;
  /** Requests whose response body is still open. */
  private inFlight = 0;
  private lastActivity = 0;
  private lastRenew = 0;
  /** Set when the lease is lost and cannot be re-acquired: in-flight requests finish, then the container is destroyed. */
  private draining = false;
  /** Bumped on every start and deliberate destroy, so a stale `monitor()` settlement is ignored. */
  private generation = 0;
  /** How the current generation's container exited, once it has. */
  private exited: ExitResult | undefined;
  /** The start or restart in progress, which a concurrent `pin` or `fetch` waits on. */
  private startup: Promise<PinAnswer> | undefined;

  constructor(ctx: DurableObjectState, env: OrgExecutorEnv) {
    super(ctx, env);
    void ctx.blockConcurrencyWhile(() => this.recover());
  }

  /**
   * Pin this instance to `orgId` and make sure its container runs, starting it on `size` if none does. A running container keeps the size it started with.
   *
   * The instance must be the Durable Object named for `orgId`, and a second org is refused, so an instance only ever serves its own org.
   */
  async pin(orgId: string, size: ExecutorSize): Promise<PinAnswer> {
    const refused = this.pinRefusal(orgId, size);
    if (refused !== undefined) return refusal('EXECUTOR_START_FAILED', refused);
    if (this.pinnedOrg === undefined) {
      this.pinnedOrg = orgId;
      await this.ctx.storage.put(ORG_KEY, orgId);
    }
    await this.touch();

    // Wait out a start in progress, then decide with no await between the check and `serialized`, which sets `this.startup` synchronously: two pins arriving together can then never both start a container.
    while (this.startup !== undefined) {
      await this.startup.catch(() => undefined);
    }
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
    return this.serialized(() => this.start(orgId, size));
  }

  /**
   * Move a running container to the deployed image. The lease is secured before the old container is destroyed: a coordinator that refuses (or fails) leaves the old container serving and the drift is retried at a later pin, rather than leaving the org with no container. `start` then re-acquires, which the coordinator counts once per org.
   */
  private async restartOnNewImage(running: ExecutorRecord): Promise<PinAnswer> {
    const lease = await this.acquireLease(running.orgId, running.size);
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor image restart deferred: no lease');
      return { ok: true, size: running.size };
    }
    this.lastRenew = Date.now();
    await this.stopContainer('image-drift');
    return this.start(running.orgId, running.size);
  }

  /** Why `pin(orgId, size)` is refused, or undefined when it is admitted. */
  private pinRefusal(orgId: string, size: ExecutorSize): string | undefined {
    if (typeof orgId !== 'string' || orgId === '') return 'pin-org-invalid';
    if (!this.ctx.id.equals(this.env.ORG_EXECUTOR.idFromName(orgId))) return 'pin-id-mismatch';
    if (this.pinnedOrg !== undefined && this.pinnedOrg !== orgId) return 'pin-org-conflict';
    if (size !== 'light' && size !== 'heavy') return 'pin-size-invalid';
    return undefined;
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
      const response = await container.getTcpPort(EXECUTOR_PORT).fetch(request);
      if (response.body === null) {
        done();
        return response;
      }
      return new Response(trackBody(response.body, done), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch {
      done();
      console.warn('proxy: org executor forward failed');
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
      const orgId = this.record.orgId;
      await this.stopContainer('idle');
      await this.releaseLease(orgId);
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

  private serialized(run: () => Promise<PinAnswer>): Promise<PinAnswer> {
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
      if (this.isDraining() && this.inFlight === 0) {
        await this.stopContainer('lease-lost');
        this.draining = false;
      }
    } catch {
      console.warn('proxy: org executor after-request bookkeeping failed');
    }
  }

  /** Ask the coordinator for a slot, failing closed: a throw or a timeout is a refusal, never an uncounted start. */
  private async acquireLease(orgId: string, size: ExecutorSize): Promise<AcquireAnswer | 'failed'> {
    try {
      return await bounded(this.capacity().acquire(orgId, size) as Promise<AcquireAnswer>);
    } catch {
      return 'failed';
    }
  }

  private async releaseLease(orgId: string | undefined): Promise<void> {
    if (orgId === undefined) return;
    try {
      await bounded(this.capacity().release(orgId));
    } catch {
      // The lease expires on its own after LEASE_MS.
      console.warn('proxy: org executor release failed');
    }
  }

  /**
   * Keep the lease of the running container, renewing at most once per RENEW_THROTTLE_MS unless `force`. A lease the coordinator no longer holds is acquired again; when that is refused, the instance drains and answers false.
   */
  private async holdLease(force = false): Promise<boolean> {
    const record = this.record;
    if (!record) return false;
    const now = Date.now();
    if (!force && now - this.lastRenew < RENEW_THROTTLE_MS) return true;
    let held: 'held' | 'not-held' | 'failed';
    try {
      held = await bounded(this.capacity().renew(record.orgId));
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
    const again = await this.acquireLease(record.orgId, record.size);
    if (again !== 'failed' && again.ok) {
      this.lastRenew = now;
      return true;
    }
    console.warn('proxy: org executor lease lost; draining');
    this.draining = true;
    if (this.inFlight === 0) {
      await this.stopContainer('lease-lost');
      this.draining = false;
    }
    return false;
  }

  /** The start sequence of Design item 5: lease, intercept, start, record, monitor, readiness. */
  private async start(orgId: string, size: ExecutorSize): Promise<PinAnswer> {
    const container = this.ctx.container;
    if (!container) return refusal('EXECUTOR_START_FAILED', 'no-container');
    const image = this.currentImage();
    if (image === undefined) return refusal('EXECUTOR_START_FAILED', 'no-image');

    const lease = await this.acquireLease(orgId, size);
    if (lease === 'failed') return refusal('EXECUTOR_START_FAILED', 'coordinator-failed');
    if (!lease.ok) return refusal('EXECUTOR_CAPACITY', lease.reason);
    this.lastRenew = Date.now();

    const failure = await this.launch(container, orgId, size, image);
    if (failure === undefined) return { ok: true, size };
    await this.stopContainer(failure.reason);
    // A container that exited on its own during readiness has had its slot released by `onExit` already.
    if (!failure.releasedByExit) await this.releaseLease(orgId);
    return refusal('EXECUTOR_START_FAILED', failure.reason);
  }

  /** Register the intercept, start the container, record it, attach `monitor()` and wait for readiness. Answers undefined once ready, else why it failed and whether its own exit already released the slot. */
  private async launch(
    container: Container,
    orgId: string,
    size: ExecutorSize,
    image: string
  ): Promise<{ reason: string; releasedByExit: boolean } | undefined> {
    let generation: number | undefined;
    try {
      // Registered before `start`, so no egress call can escape to DNS in between.
      await this.registerEgress(container, orgId);
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
      this.record = { orgId, size, image, startedAt: Date.now() };
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
  private async registerEgress(container: Container, orgId: string): Promise<void> {
    const factory = (this.ctx.exports as unknown as Record<string, EgressFactory | undefined>)[
      ACCOUNT_EGRESS_ENTRYPOINT
    ];
    if (typeof factory !== 'function') throw new Error('egress-entrypoint-missing');
    const props: ExecutorEgressProps = { orgId, containerId: this.ctx.id.toString() };
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
    const orgId = this.record?.orgId ?? this.pinnedOrg;
    const wasSize = this.record?.size;
    this.record = undefined;
    this.draining = false;
    try {
      if (!result.clean && isOomExit(result.error)) {
        console.warn(`proxy: org executor out of memory on ${wasSize ?? 'unknown'}`);
        await this.ctx.storage.put(OOM_KEY, Date.now());
      }
      await this.ctx.storage.delete(RECORD_KEY);
    } catch {
      console.warn('proxy: org executor exit bookkeeping failed');
    }
    await this.releaseLease(orgId);
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
   * Recovery after the Durable Object restarts (a deploy, an eviction) under a running container: re-register the intercept with the stored props, re-attach `monitor()` and re-acquire the lease before serving. A container whose lease is refused, or whose record is gone, is destroyed, since it would run uncounted.
   */
  private async recover(): Promise<void> {
    this.pinnedOrg = await this.ctx.storage.get<string>(ORG_KEY);
    const record = await this.ctx.storage.get<ExecutorRecord>(RECORD_KEY);
    const container = this.ctx.container;
    if (!container?.running) {
      if (record) {
        await this.ctx.storage.delete(RECORD_KEY);
        await this.releaseLease(record.orgId);
      }
      return;
    }
    if (!record) {
      await this.stopContainer('unrecorded');
      return;
    }
    this.record = record;
    this.generation += 1;
    this.exited = undefined;
    try {
      await this.registerEgress(container, record.orgId);
    } catch {
      console.warn('proxy: org executor intercept not re-registered');
    }
    this.attachMonitor(container);
    const lease = await this.acquireLease(record.orgId, record.size);
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor lease refused after restart; destroying');
      await this.stopContainer('lease-refused');
      return;
    }
    this.lastRenew = Date.now();
    await this.touch();
  }
}
