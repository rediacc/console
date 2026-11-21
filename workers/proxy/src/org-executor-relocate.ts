/**
 * The identity checks and the relocation call of `OrgExecutor` (src/org-executor.ts): who a pin, an egress-unreachable report or an outside probe may come from, and the issuer call that moves an org off its placement. Each takes the instance's state as arguments and holds none, except `ReachabilityGate`, which keeps one instance's probe cache and cap in memory.
 *
 * The outside vantage (finding 60c7b83e, production asia 2026-11-10). The reachability probe first runs inside the org's own `OrgExecutor`, which the `durable_object` scheduling policy runs beside the container it serves. When that colo cannot reach the machine, the in-object probe fails the same way the container does, every report reads `target-unreachable`, and the executor never moves: org d0c9dce0 failed twice on 72.61.137.225:22 while that host answered SSH from the internet and from another org on the same proxy. So a probe that fails in the object is asked again from a second vantage: an `OrgExecutor` instance named `vantageName(hint)` in the same ORG_EXECUTOR namespace, created with the Durable Object `locationHint` of another continent (`vantageHint`, by the proxy's REGION). It reuses the existing binding, so it needs no new class, migration or paid resource, and it never pins, so it never starts a container. A call through the ISSUER or ACCOUNT service binding to the account Worker was not chosen: a bound Worker runs in the caller's colo by default, so it would share the failing network position, and it would need a new account entrypoint besides. Reachable from the vantage means the machine is up and the executor's position is the broken one, so the report counts; unreachable from both means the machine is down, so nothing moves.
 */

import type { ExecutorSize } from './capacity';
import {
  bounded,
  type EgressReportAnswer,
  type OrgExecutorEnv,
  type PinnedExecutor,
  type RelocateAnswer,
} from './org-executor-support';
import { executorName, placementOf, UNREACHABLE_THRESHOLD, unreachableRecent } from './placement';
import {
  type ProbeResult,
  type ProbeTarget,
  type ProbeVerdict,
  probeSshBanner,
  probeTarget,
} from './reachability';

/** The instance state the identity checks read: its own id, the namespace that names it, and its pin. */
export interface ExecutorIdentity {
  id: DurableObjectId;
  env: Pick<OrgExecutorEnv, 'ORG_EXECUTOR'>;
  pinned: PinnedExecutor | undefined;
}

/** Why `pin(orgId, placement, size)` is refused, or undefined when it is admitted. */
export function pinRefusal(
  self: ExecutorIdentity,
  orgId: string,
  placement: number,
  size: ExecutorSize
): string | undefined {
  if (typeof orgId !== 'string' || orgId === '') return 'pin-org-invalid';
  if (placementOf(placement) === undefined) return 'pin-placement-invalid';
  if (!self.id.equals(self.env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)))) {
    return 'pin-id-mismatch';
  }
  const pinned = self.pinned;
  if (pinned !== undefined && (pinned.orgId !== orgId || pinned.placement !== placement)) {
    return 'pin-org-conflict';
  }
  if (size !== 'light' && size !== 'heavy') return 'pin-size-invalid';
  return undefined;
}

/** Why a report for `orgId` at `placement` is refused, or undefined when it is admitted. */
export function reportRefusal(
  self: ExecutorIdentity,
  orgId: string,
  placement: number
): string | undefined {
  if (typeof orgId !== 'string' || orgId === '') return 'report-org-invalid';
  if (placementOf(placement) === undefined) return 'report-placement-invalid';
  if (!self.id.equals(self.env.ORG_EXECUTOR.idFromName(executorName(orgId, placement)))) {
    return 'report-id-mismatch';
  }
  const pinned = self.pinned;
  if (pinned !== undefined && (pinned.orgId !== orgId || pinned.placement !== placement)) {
    return 'report-org-conflict';
  }
  return undefined;
}

/** The vantage location per proxy REGION: a hint on another continent, so the vantage is placed away from the region's colos. */
const VANTAGE_HINT_BY_REGION: Readonly<Record<string, DurableObjectLocationHint>> = {
  asia: 'weur',
  eu: 'enam',
  us: 'weur',
};
/** The vantage of a REGION the table does not name (and of an unset one, which the proxy reads as `eu`). */
const DEFAULT_VANTAGE_HINT: DurableObjectLocationHint = 'enam';
/** Every hint a vantage may be named for. */
const VANTAGE_HINTS: ReadonlySet<string> = new Set([
  ...Object.values(VANTAGE_HINT_BY_REGION),
  DEFAULT_VANTAGE_HINT,
]);
/** The outside probe waits this long for the vantage: the probe's own PROBE_TIMEOUT_MS plus the vantage object's first start. */
export const OUTSIDE_PROBE_TIMEOUT_MS = 8_000;

/** The location hint of the outside vantage for a proxy deployed to `region`. */
export function vantageHint(region: string | undefined): DurableObjectLocationHint {
  return VANTAGE_HINT_BY_REGION[region ?? ''] ?? DEFAULT_VANTAGE_HINT;
}

/** The ORG_EXECUTOR name of the vantage at `hint`. It never ends in `:p<digits>`, so it can never be an `executorName`, and `pin` refuses it. */
export function vantageName(hint: string): string {
  return `reachability-vantage:v1:${hint}`;
}

/** The target `probeFromVantage` probes, or why the call is refused: the instance must be the unpinned vantage named for a known `hint`, and the target must pass `probeTarget` again. */
export function vantageTarget(
  self: ExecutorIdentity,
  hint: string,
  target: unknown
): ProbeTarget | { refused: string } {
  if (typeof hint !== 'string' || !VANTAGE_HINTS.has(hint))
    return { refused: 'vantage-hint-invalid' };
  if (!self.id.equals(self.env.ORG_EXECUTOR.idFromName(vantageName(hint)))) {
    return { refused: 'vantage-id-mismatch' };
  }
  if (self.pinned !== undefined) return { refused: 'vantage-pinned' };
  const admitted = probeTarget(target);
  return 'refused' in admitted ? { refused: admitted.refused } : admitted;
}

/** The second vantage a `ReachabilityGate` asks when its own probe fails: the hint it runs at, for the log line, and the probe. */
export interface OutsideProbe {
  hint: string;
  probe: (target: ProbeTarget) => Promise<ProbeResult>;
}

/** The outside probe through the vantage `OrgExecutor` at `vantageHint(env.REGION)`, bounded by OUTSIDE_PROBE_TIMEOUT_MS; a timeout or failure rejects, which the gate reads as `target-unreachable (error)`. */
export function outsideProbe(env: Pick<OrgExecutorEnv, 'ORG_EXECUTOR' | 'REGION'>): OutsideProbe {
  const hint = vantageHint(env.REGION);
  return {
    hint,
    probe: (target) => {
      const namespace = env.ORG_EXECUTOR;
      const stub = namespace.get(namespace.idFromName(vantageName(hint)), { locationHint: hint });
      return deadline(stub.probeFromVantage(hint, target), OUTSIDE_PROBE_TIMEOUT_MS);
    },
  };
}

/** `call`, or a rejection once `ms` pass. */
async function deadline<T>(call: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('outside-probe-timeout')), ms);
  });
  try {
    return await Promise.race([call, expired]);
  } finally {
    clearTimeout(timer);
  }
}

/** Ask the issuer to move the org off `placement`, bounded like the coordinator calls. Answers the placement it moved to, or undefined when it stays. */
export async function relocateOrg(
  issuer: OrgExecutorEnv['ISSUER'],
  orgId: string,
  placement: number
): Promise<number | undefined> {
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

/** The ok answer to a report; it counted exactly when the probe found the target `reachable`. */
export function reportAnswer(
  count: number,
  relocated: boolean,
  probe: ProbeVerdict
): EgressReportAnswer {
  const counted = probe === 'reachable';
  return { ok: true, count, threshold: UNREACHABLE_THRESHOLD, relocated, counted, probe };
}

/** How many of the stored report times are still inside the window at `now`. */
export function recentCount(stored: number[], now: number): number {
  return stored.filter((at) => unreachableRecent(at, now)).length;
}

/** A probe verdict is reused for this long per host and port. */
const PROBE_CACHE_MS = 60_000;
/** At most this many probes run per instance inside UNREACHABLE_WINDOW_MS (one probe being the instance's own connect plus, when that fails, the vantage's); past it a report is `skipped` and does not count. */
const PROBE_CAP = 6;

/**
 * The count gate of `recordEgressUnreachable` (operator ruling ASKED:2026-10-29T05:18Z): a report counts toward relocation only when the Worker reaches the reported machine's SSH banner, so a machine that is down or has a closed port never moves the executor. The probe runs in the instance first; when that fails and an `outside` vantage is given, the vantage's verdict decides (see the module comment), so a colo that cannot reach the machine cannot hide a machine that is up. Verdicts are cached per host and port for PROBE_CACHE_MS, and probes are capped at PROBE_CAP per window, so a container cannot drive the Worker into a probe storm. In memory only: a restarted instance starts with an empty cache, which costs at most one probe more.
 *
 * The log line names the verdict, the reason (the instance's, then the vantage's hint and reason when it was asked) and the placement, never the address.
 */
export class ReachabilityGate {
  private readonly cache = new Map<string, { verdict: ProbeVerdict; at: number }>();
  private probes: number[] = [];

  constructor(
    private readonly probe: (target: ProbeTarget) => Promise<ProbeResult> = probeSshBanner,
    private readonly outside?: OutsideProbe
  ) {}

  async verdict(target: ProbeTarget | undefined, placement: number): Promise<ProbeVerdict> {
    if (target === undefined) return logged('skipped', 'no-target', placement);
    const now = Date.now();
    for (const [key, entry] of this.cache) {
      if (now - entry.at >= PROBE_CACHE_MS || now < entry.at) this.cache.delete(key);
    }
    const key = `${target.host}:${target.port}`;
    const cached = this.cache.get(key);
    if (cached !== undefined) return logged(cached.verdict, 'cached', placement);
    this.probes = this.probes.filter((at) => unreachableRecent(at, now));
    if (this.probes.length >= PROBE_CAP) return logged('skipped', 'cap', placement);
    this.probes.push(now);
    const result = await settled(this.probe, target);
    let verdict: ProbeVerdict = result.verdict;
    let reason: string = result.reason;
    if (verdict !== 'reachable' && this.outside !== undefined) {
      const far = await settled(this.outside.probe, target);
      verdict = far.verdict;
      reason = `${result.reason}, outside ${this.outside.hint} ${far.reason}`;
    }
    this.cache.set(key, { verdict, at: now });
    return logged(verdict, reason, placement);
  }
}

/** `probe(target)`, with a throw or rejection read as `target-unreachable (error)`. */
async function settled(
  probe: (target: ProbeTarget) => Promise<ProbeResult>,
  target: ProbeTarget
): Promise<ProbeResult> {
  try {
    return await probe(target);
  } catch {
    return { verdict: 'target-unreachable', reason: 'error' };
  }
}

function logged(verdict: ProbeVerdict, reason: string, placement: number): ProbeVerdict {
  console.warn(`proxy: org executor reachability probe ${verdict} (${reason}) at p${placement}`);
  return verdict;
}
