/**
 * Cooldown bookkeeping for opportunistic repo-licence refresh.
 *
 * Refreshing is not free: it opens an SSH session, scans every repo's licence on
 * the machine, and posts the set to the account server. Doing that on each
 * command would add latency to routine work and hammer the server for nothing,
 * so a refresh is attempted at most once per cooldown per machine.
 *
 * The cooldown is the whole rate-limiting mechanism. It is deliberately NOT a
 * check of "is any licence due" — answering that requires the same remote scan
 * a refresh performs, so probing first would cost what it saves. The server
 * already decides per repo whether to issue, refresh, or leave alone
 * (`/account/api/v1/licenses/activate-repo-batch`), so calling it on a slow
 * cadence IS the age-based policy; this file only bounds how often we ask.
 */

import {
  readUpdateState as readState,
  writeUpdateState as writeState,
} from '@rediacc/shared/update';
import { LICENSE_REFRESH_STATE_FILE } from '../../utils/platform.js';

/**
 * How long to wait between refresh attempts for a given machine.
 *
 * Licence soft-windows (`refreshRecommendedAt`) run to days, so checking twice a
 * day leaves ample margin to act before one expires while keeping the cost per
 * command at zero for all but the first invocation in a window.
 */
export const LICENSE_REFRESH_COOLDOWN_MS = 12 * 60 * 60 * 1000;

/**
 * The on-disk shape. `lastAttemptAt` is optional because the reader casts
 * untrusted JSON (`parsed as T`) without validating it — a hand-edited or
 * half-written file can satisfy the schemaVersion check and still be missing
 * the map. Declaring it required here would make the type lie about data this
 * process does not control.
 */
interface StoredLicenseRefreshState {
  schemaVersion: 1;
  lastAttemptAt?: Record<string, number>;
}

/** The shape after `read()` has filled in anything the file omitted. */
interface LicenseRefreshState extends StoredLicenseRefreshState {
  lastAttemptAt: Record<string, number>;
}

const DEFAULT_STATE: LicenseRefreshState = {
  schemaVersion: 1,
  lastAttemptAt: {},
};

async function read(): Promise<LicenseRefreshState> {
  const state = await readState<StoredLicenseRefreshState>(
    LICENSE_REFRESH_STATE_FILE,
    DEFAULT_STATE
  );
  // Normalise here so every caller downstream can rely on the map existing;
  // refusing to refresh because bookkeeping is malformed would be the wrong
  // failure.
  return { ...state, lastAttemptAt: state.lastAttemptAt ?? {} };
}

/** Whether enough time has passed to attempt a refresh for this machine. */
export async function isRefreshDue(machineName: string, now = Date.now()): Promise<boolean> {
  const state = await read();
  const last = state.lastAttemptAt[machineName];
  if (typeof last !== 'number' || Number.isNaN(last)) return true;
  // A timestamp in the future means a clock change, not a recent refresh.
  // Treating it as recent would suppress refreshes until the clock caught up.
  if (last > now) return true;
  return now - last >= LICENSE_REFRESH_COOLDOWN_MS;
}

/**
 * Record that a refresh was attempted, successful or not.
 *
 * Failures count: a machine that is unreachable, or a server that is refusing,
 * must not be retried on every subsequent command. The reactive path
 * (LICENSE_REQUIRED recovery) still fires immediately when a licence is actually
 * blocking work, so a failed opportunistic refresh never strands anyone.
 */
export async function markRefreshAttempted(machineName: string, now = Date.now()): Promise<void> {
  const state = await read();
  state.lastAttemptAt[machineName] = now;
  await writeState(LICENSE_REFRESH_STATE_FILE, state);
}
