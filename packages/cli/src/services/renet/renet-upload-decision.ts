/**
 * Whether a renet acquire may upload the machine's renet. Kept apart from renet-execution so a caller
 * that announces "Provisioning renet" reads the same decision `acquireRemoteRenet` acts on.
 */

import { currentRequestContext } from '../core/request-context.js';

/**
 * True inside a served request (`rdc serve`, either tier): the dispatch binds a request context,
 * which a laptop's `rdc` and the local daemon never have. An executor never replaces a machine's
 * renet: its binary is whatever its image was built with, and the image outlives the machine's upgrades
 * (2026-11-04: a six-day-old bench image replaced hostinger's renet during a proxied `repo up`).
 */
export function inExecutor(): boolean {
  return currentRequestContext() !== undefined;
}

/**
 * True when REDIACC_NO_PROVISION=1 holds the machine's renet: a mutating verb then runs the installed
 * binary as-is, like an executor, and only an explicit setup (`explicitSetup`: `rdc machine setup`, a
 * cluster bootstrap, a machine provision) uploads. Without it, a mutating verb run from a branch checkout
 * replaces the machine's renet with that branch's build (2026-11-05: every mutating verb against
 * hostinger would have installed a renet 82 commits ahead of the one production ran).
 */
export function provisionHeld(): boolean {
  return process.env.REDIACC_NO_PROVISION === '1';
}

/**
 * True when `acquireRemoteRenet(access, ...)` may upload renet: false for a read-only access, inside an
 * executor, or while REDIACC_NO_PROVISION=1 holds it. Callers announce "Provisioning renet" only when true.
 */
export function renetMayUpload(
  access: 'read-only' | 'provision',
  explicitSetup?: boolean
): boolean {
  const held = provisionHeld() && explicitSetup !== true;
  return access !== 'read-only' && !inExecutor() && !held;
}
