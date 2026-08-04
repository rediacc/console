/**
 * Machine-slot pre-flight for multi-machine placement.
 *
 * A repo license claims a machine slot the first time a repository is issued
 * on a machine. Infrastructure provisioning itself is free, so a cluster can be
 * built past the slot limit and only discover it later, one repo at a time,
 * on whichever node happens to be placed last. That failure arrives after the
 * VMs exist and the bill has started, which is the worst possible moment to
 * learn about a limit.
 *
 * So placement that spans machines asks first. The check is advisory in
 * direction only: it reads the same numbers the server enforces, and when they
 * say the placement cannot fit, it refuses BEFORE anything is provisioned.
 */

import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { accountServerFetch } from './account-client.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

interface LicenseSlotStatus {
  maxMachines: number;
  activeMachineCount: number;
  overLimitCount?: number;
}

/**
 * The message the operator gets when a placement cannot fit, and the same one
 * the server's MAX_MACHINES_REACHED refusal is aligned to: what the limit is,
 * that slots free themselves on the 5-hour float, and that a bigger ceiling is
 * a plan upgrade or a negotiated Enterprise/partner deal rather than a support
 * ticket.
 */
export function machineSlotLimitMessage(input: {
  needed: number;
  active: number;
  max: number;
}): string {
  return t('errors.license.machineSlotLimit', {
    needed: input.needed,
    active: input.active,
    max: input.max,
    free: Math.max(0, input.max - input.active),
  });
}

/**
 * Read live slot state. Returns null when it cannot be read at all — nobody
 * signed in, server unreachable, an older server without the field. A
 * pre-flight that cannot see the numbers must not invent a refusal: the server
 * still enforces the cap at issuance, so an unavailable check costs a later
 * error, while a fabricated one costs a provisioning run that would have
 * succeeded.
 */
export async function readMachineSlotStatus(): Promise<LicenseSlotStatus | null> {
  if (getSubscriptionTokenState().kind !== 'ready') return null;
  try {
    const status = await accountServerFetch<Partial<LicenseSlotStatus>>(
      '/account/api/v1/licenses/status'
    );
    if (typeof status.maxMachines !== 'number' || typeof status.activeMachineCount !== 'number') {
      return null;
    }
    return {
      maxMachines: status.maxMachines,
      activeMachineCount: status.activeMachineCount,
      overLimitCount: status.overLimitCount,
    };
  } catch {
    return null;
  }
}

export interface MachineSlotPreflightOptions {
  /** How many machines this operation will place repositories on. */
  machineCount: number;
  /**
   * Machines that already hold a slot and therefore cost nothing new. Passing
   * them keeps a re-run of a partially completed placement from being refused
   * for slots it already owns.
   */
  alreadyActive?: number;
}

/**
 * Refuse a multi-machine placement that cannot fit in the subscription's
 * machine slots, before any of it runs.
 *
 * Throws ValidationError with the limit, the 5-hour window and the upgrade path
 * named. Silent (returns) when the numbers are unavailable or the placement
 * fits.
 */
export async function assertMachineSlotsAvailable(
  options: MachineSlotPreflightOptions
): Promise<void> {
  if (options.machineCount <= 0) return;
  const status = await readMachineSlotStatus();
  if (!status) return;

  const alreadyActive = Math.min(options.alreadyActive ?? 0, options.machineCount);
  const newMachines = options.machineCount - alreadyActive;
  if (newMachines <= 0) return;

  if (status.activeMachineCount + newMachines <= status.maxMachines) return;

  throw new ValidationError(
    machineSlotLimitMessage({
      needed: newMachines,
      active: status.activeMachineCount,
      max: status.maxMachines,
    })
  );
}

/**
 * Recognize the server's own cap refusal so the CLI answers it with the same
 * words its pre-flight uses. Without this the operator gets one wording when
 * the check fires early and a different one when it fires at issuance, for the
 * identical condition.
 */
export function isMachineSlotLimitError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { code?: unknown }).code === 'MAX_MACHINES_REACHED'
  );
}

/**
 * What is left behind when a multi-machine placement stops at the slot wall,
 * and what to run next.
 *
 * The state is deliberately not rolled back. Machines that were placed before
 * the wall keep their repositories and their slots; the ones after it were
 * never touched. Rolling the successful ones back would destroy working
 * deployments to tidy up an accounting failure, and would itself need slots to
 * undo. So the contract is: the placement is PARTIAL, it is inspectable, and
 * finishing it is a re-run once a slot is free.
 */
export function partialPlacementGuidance(input: {
  placed: string[];
  remaining: string[];
  command: string;
}): string {
  return t('errors.license.partialPlacement', {
    placed: input.placed.length,
    placedNames: input.placed.join(', ') || '-',
    remaining: input.remaining.length,
    remainingNames: input.remaining.join(', ') || '-',
    command: input.command,
  });
}
