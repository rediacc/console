/**
 * Whether a renet acquire may upload the machine's renet. Kept apart from renet-execution so a caller
 * that announces "Provisioning renet" reads the same decision `acquireRemoteRenet` acts on.
 */

import { isDevBuild } from '../../utils/platform.js';
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

/** Why a mutating verb does not replace the machine's renet: the environment, or a development build. */
export type RenetHold = 'env' | 'dev' | null;

/**
 * Which hold applies. REDIACC_NO_PROVISION=1 holds the machine's renet explicitly. A development build
 * (CLI version 0.0.0-dev: a checkout, including ./rdc.sh) holds it by default, because an unrelated
 * mutating verb (`repo sync upload`, a file copy) replaced the machine's renet with the checkout's build
 * (2026-11-05: hostinger would have received a renet 82 commits ahead of production's). Release builds
 * keep their auto-sync. REDIACC_NO_PROVISION=0 lifts the development default. Only an explicit setup
 * (`explicitSetup`: `rdc machine setup`, a cluster bootstrap, a machine provision) or an interactive
 * confirmation replaces it.
 */
export function renetHold(): RenetHold {
  const setting = process.env.REDIACC_NO_PROVISION;
  if (setting === '1') return 'env';
  if (setting !== '0' && isDevBuild()) return 'dev';
  return null;
}

/** True when any hold applies ({@link renetHold}). */
export function provisionHeld(): boolean {
  return renetHold() !== null;
}

/**
 * True when `acquireRemoteRenet(access, ...)` may upload renet: false for a read-only access, inside an
 * executor, or while a hold applies ({@link renetHold}). Callers announce "Provisioning renet" only when true.
 */
export function renetMayUpload(
  access: 'read-only' | 'provision',
  explicitSetup?: boolean
): boolean {
  const held = provisionHeld() && explicitSetup !== true;
  return access !== 'read-only' && !inExecutor() && !held;
}

/**
 * True when a held mutating verb may ask the operator whether to replace the machine's renet: only the
 * development-build hold (an explicit REDIACC_NO_PROVISION=1 is never overridden by a prompt), never
 * inside an executor, never for an explicit setup (which uploads anyway), and only on a terminal that can
 * answer. REDIACC_YES=1 does not confirm a replacement: a scripted run holds.
 */
export function mayOfferReplacement(
  access: 'read-only' | 'provision',
  explicitSetup?: boolean
): boolean {
  return (
    access === 'provision' &&
    explicitSetup !== true &&
    renetHold() === 'dev' &&
    !inExecutor() &&
    process.env.REDIACC_YES !== '1' &&
    process.stdin.isTTY === true &&
    process.stderr.isTTY === true
  );
}
