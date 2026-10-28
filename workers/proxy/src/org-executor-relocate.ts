/**
 * The identity checks and the relocation call of `OrgExecutor` (src/org-executor.ts): who a pin or an egress-unreachable report may come from, and the issuer call that moves an org off its placement. Each takes the instance's state as arguments and holds none.
 */

import type { ExecutorSize } from './capacity';
import {
  bounded,
  type OrgExecutorEnv,
  type PinnedExecutor,
  type RelocateAnswer,
} from './org-executor-support';
import { executorName, placementOf } from './placement';

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
