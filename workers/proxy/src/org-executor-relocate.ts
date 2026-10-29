/**
 * The identity checks and the relocation call of `OrgExecutor` (src/org-executor.ts): who a pin or an egress-unreachable report may come from, and the issuer call that moves an org off its placement. Each takes the instance's state as arguments and holds none, except `ReachabilityGate`, which keeps one instance's probe cache and cap in memory.
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
export const PROBE_CACHE_MS = 60_000;
/** At most this many probes run per instance inside UNREACHABLE_WINDOW_MS; past it a report is `skipped` and does not count. */
export const PROBE_CAP = 6;

/**
 * The count gate of `recordEgressUnreachable` (operator ruling ASKED:2026-10-29T05:18Z): a report counts toward relocation only when the Worker itself reaches the reported machine's SSH banner, so a machine that is down or has a closed port never moves the executor. Verdicts are cached per host and port for PROBE_CACHE_MS, and probes are capped at PROBE_CAP per window, so a container cannot drive the Worker into a probe storm. In memory only: a restarted instance starts with an empty cache, which costs at most one probe more.
 *
 * The log line names the verdict, the reason and the placement, never the address.
 */
export class ReachabilityGate {
  private readonly cache = new Map<string, { verdict: ProbeVerdict; at: number }>();
  private probes: number[] = [];

  constructor(
    private readonly probe: (target: ProbeTarget) => Promise<ProbeResult> = probeSshBanner
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
    let result: ProbeResult;
    try {
      result = await this.probe(target);
    } catch {
      result = { verdict: 'target-unreachable', reason: 'error' };
    }
    this.cache.set(key, { verdict: result.verdict, at: now });
    return logged(result.verdict, result.reason, placement);
  }
}

function logged(verdict: ProbeVerdict, reason: string, placement: number): ProbeVerdict {
  console.warn(`proxy: org executor reachability probe ${verdict} (${reason}) at p${placement}`);
  return verdict;
}
