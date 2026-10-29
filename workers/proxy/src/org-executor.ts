/**
 * `OrgExecutor`: one org's executor container under the `durable_object` scheduling policy (agent/plans/PLAN-executor-durable-object-policy.md Design items 2 and 5, box W1).
 *
 * The frozen @cloudflare/containers `Container` class cannot run under the new policy, so this class drives `this.ctx.container` directly and imports nothing from that library. It rebuilds the helpers the proxy took from it: the start with per-instance env and outbound interception, the port readiness check, request proxying, and the `sleepAfter` idle timer. It adds what the policy moves into code: the lease on the target's cap (src/capacity.ts), the per-start instance size, the image-drift restart, and recovery after the Durable Object restarts under a running container.
 *
 * The Worker calls `pin(orgId, placement, size)` with the org and placement `ExecutorIssuer.route` named, then forwards the request with `fetch`. Every refusal is an answer with a code, never error text for the Worker to guess at.
 *
 * Relocation (agent/plans/PLAN-org-executor-connect-timeout-relocate.md Design item 5): the executor reports a machine it cannot reach through `recordEgressUnreachable`, which counts the report only when the Worker itself reaches that machine's SSH banner (src/reachability.ts). At UNREACHABLE_THRESHOLD counted reports within UNREACHABLE_WINDOW_MS the instance asks the issuer to bump the org's placement, and on success it retires: `pin` refuses with `EXECUTOR_RELOCATED`, the lease is never re-acquired, and the container stops once nothing is in flight. The retired instance never touches the new name, so the new instance is placed the way a fresh org's is.
 */

import { DurableObject } from 'cloudflare:workers';
import { capacityStub, type ExecutorCapacity, type ExecutorSize } from './capacity';
import {
  type ExecutorIdentity,
  pinRefusal,
  ReachabilityGate,
  recentCount,
  relocateOrg,
  reportAnswer,
  reportRefusal,
} from './org-executor-relocate';
import {
  acquireLease,
  bounded,
  containerRequest,
  durationMs,
  type EgressReportAnswer,
  EXECUTOR_IMAGE_KEY,
  EXECUTOR_PORT,
  type ExecutorRecord,
  type ExitResult,
  errorSummary,
  executorEnv,
  healthy,
  isOomExit,
  OOM_HEAVY_KEY,
  OOM_KEY,
  ORG_KEY,
  type OrgExecutorEnv,
  type PinAnswer,
  type PinnedExecutor,
  pinnedFrom,
  READY_POLL_MS,
  READY_TIMEOUT_MS,
  RECORD_KEY,
  RENEW_THROTTLE_MS,
  RETIRED_KEY,
  refusal,
  refusalResponse,
  registerEgress,
  releaseLease,
  type StartAnswer,
  trackBody,
  UNREACHABLE_AT_KEY,
  UNREACHABLE_KEY,
  wait,
} from './org-executor-support';
import { executorName, placementOf, UNREACHABLE_THRESHOLD, unreachableRecent } from './placement';
import type { ProbeTarget } from './reachability';
import { INSTANCE_BY_SIZE } from './sizing';

export {
  ACCOUNT_EGRESS_HOST,
  COORDINATOR_TIMEOUT_MS,
  durationMs,
  type EgressReportAnswer,
  type ExecutorEgressProps,
  type ExecutorRecord,
  type ExecutorRefusalCode,
  executorEnv,
  isOomExit,
  type OrgExecutorEnv,
  type PinAnswer,
  READY_TIMEOUT_MS,
  RENEW_THROTTLE_MS,
  type RelocateAnswer,
} from './org-executor-support';

/** The size named in the out-of-memory log line when the container never reported one. */
const UNKNOWN_SIZE = 'unknown';

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
  /** Decides whether a report counts: the Worker's own probe of the reported machine (src/reachability.ts). */
  private readonly reachability = new ReachabilityGate();
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
    const refused = pinRefusal(this.identity(), orgId, placement, size);
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
   * Count one egress-unreachable report from this instance's container, once the Worker itself has reached `target`'s SSH banner (src/reachability.ts): a machine that is down or has a closed port is not this executor's problem, so its report answers `counted: false` with the probe verdict and leaves the stored count alone. Below UNREACHABLE_THRESHOLD counted reports within UNREACHABLE_WINDOW_MS it only counts. At the threshold it asks the issuer to move the org to the next placement: on `ok` or `stale` (another caller moved it already) the instance retires and drains; on `budget` or a failure the org stays where it is.
   *
   * Refused for an org or placement that is not this instance's. An undefined target is never probed, so it never counts.
   */
  async recordEgressUnreachable(
    orgId: string,
    placement: number,
    target?: ProbeTarget
  ): Promise<EgressReportAnswer> {
    const refused = reportRefusal(this.identity(), orgId, placement);
    if (refused !== undefined) {
      console.warn(`proxy: org executor egress report refused: ${refused}`);
      return { ok: false, reason: refused };
    }
    while (this.reporting !== undefined) {
      await this.reporting.catch(() => undefined);
    }
    const reporting = this.countReport(orgId, placement, target).finally(() => {
      if (this.reporting === reporting) this.reporting = undefined;
    });
    this.reporting = reporting;
    return reporting;
  }

  /** Probe the target, and only on `reachable` append the report, prune the window, and relocate at the threshold. */
  private async countReport(
    orgId: string,
    placement: number,
    target: ProbeTarget | undefined
  ): Promise<EgressReportAnswer> {
    const stored = (await this.ctx.storage.get<number[]>(UNREACHABLE_KEY)) ?? [];
    if (this.isRetired()) return reportAnswer(recentCount(stored, Date.now()), true, 'skipped');
    const probe = await this.reachability.verdict(target, placement);
    const now = Date.now();
    if (probe !== 'reachable') return reportAnswer(recentCount(stored, now), false, probe);
    const recent = [...stored, now].filter((at) => unreachableRecent(at, now));
    this.unreachableAt = now;
    await this.ctx.storage.put(UNREACHABLE_KEY, recent);
    await this.ctx.storage.put(UNREACHABLE_AT_KEY, now);
    const count = recent.length;
    console.warn(
      `proxy: org executor egress unreachable ${count}/${UNREACHABLE_THRESHOLD} at p${placement}`
    );
    if (count < UNREACHABLE_THRESHOLD) return reportAnswer(count, false, probe);

    const moved = await relocateOrg(this.env.ISSUER, orgId, placement);
    if (moved === undefined) return reportAnswer(count, false, probe);
    await this.retire(moved);
    return reportAnswer(count, true, probe);
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
    const lease = await acquireLease(
      this.capacity(),
      running.orgId,
      running.placement,
      running.size
    );
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor image restart deferred: no lease');
      return { ok: true, size: running.size };
    }
    this.lastRenew = Date.now();
    await this.stopContainer('image-drift');
    return this.startLeased(running.orgId, running.placement, running.size);
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
    // Which step threw, so a storage or lease error is not logged as a failed forward (review
    // 2b65e8c7.2). The caller's answer is the same either way, a 502; only a failure at 'touch' or 'lease' proves nothing reached the executor, while 'forward' can throw after the request was delivered (reading the response), so the executor may have run the command.
    let stage: 'touch' | 'lease' | 'forward' = 'touch';
    try {
      await this.touch();
      stage = 'lease';
      if (!(await this.holdLease())) {
        done();
        return refusalResponse('EXECUTOR_CAPACITY');
      }
      stage = 'forward';
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
      // The message stays the fixed forward-failure string any alert matches; the stage rides as a field.
      console.warn('proxy: org executor forward failed', { stage, ...errorSummary(error) });
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
      await releaseLease(this.capacity(), orgId, placement);
      return;
    }
    await this.ctx.storage.setAlarm(this.lastActivity + idleMs);
  }

  /** The image the deployed version names for the executor. */
  private currentImage(): string | undefined {
    return this.ctx.container?.images[EXECUTOR_IMAGE_KEY];
  }

  /** What the identity checks of src/org-executor-relocate.ts read, at the moment of the call. */
  private identity(): ExecutorIdentity {
    return { id: this.ctx.id, env: this.env, pinned: this.pinned };
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
      if (record) await releaseLease(this.capacity(), record.orgId, record.placement);
    } else {
      await this.stopContainer('lease-lost');
    }
    this.draining = false;
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
    const again = await acquireLease(this.capacity(), record.orgId, record.placement, record.size);
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

    const lease = await acquireLease(this.capacity(), orgId, placement, size);
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
      await releaseLease(this.capacity(), orgId, placement);
      return refusal('EXECUTOR_START_FAILED', 'no-container');
    }
    const image = this.currentImage();
    if (image === undefined) {
      await releaseLease(this.capacity(), orgId, placement);
      return refusal('EXECUTOR_START_FAILED', 'no-image');
    }
    const failure = await this.launch(container, { orgId, placement, size, image });
    if (failure === undefined) return { ok: true, size };
    await this.stopContainer(failure.reason);
    // A container that exited on its own during readiness has had its slot released by `onExit` already.
    if (!failure.releasedByExit) await releaseLease(this.capacity(), orgId, placement);
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
      await registerEgress(this.ctx, container, orgId, placement);
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
        console.warn(`proxy: org executor out of memory on ${wasSize ?? UNKNOWN_SIZE}`);
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
    await releaseLease(this.capacity(), owner?.orgId, owner?.placement);
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
        await releaseLease(this.capacity(), record?.orgId, record?.placement);
      }
      return;
    }
    if (!record) {
      await this.stopContainer('unrecorded');
      return;
    }
    if (this.isRetired()) {
      await this.stopContainer('relocated');
      await releaseLease(this.capacity(), record.orgId, record.placement);
      return;
    }
    this.record = record;
    this.generation += 1;
    this.exited = undefined;
    try {
      await registerEgress(this.ctx, container, record.orgId, record.placement);
    } catch {
      console.warn('proxy: org executor intercept not re-registered');
    }
    this.attachMonitor(container);
    const lease = await acquireLease(this.capacity(), record.orgId, record.placement, record.size);
    if (lease === 'failed' || !lease.ok) {
      console.warn('proxy: org executor lease refused after restart; destroying');
      await this.stopContainer('lease-refused');
      return;
    }
    this.lastRenew = Date.now();
    await this.touch();
  }
}
