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
 *
 * State lives in the CONFIG (`state.licenseRefresh`), not in a sidecar file.
 * A separate `license-refresh-state.json` under the user's state dir made the
 * CLI's behaviour depend on machine-local litter that nothing else knew about,
 * and it leaked straight into the test suite: `local-executor.test.ts` passed on
 * a developer box that had run `rdc` recently and failed in CI, because the
 * sidecar's mere presence decided which code path executed. Config state is
 * already mocked, versioned, inspectable, and travels with the config it
 * describes.
 *
 * Written through `updateState`, so cooldown churn never bumps the config's
 * version counter (R2-F2) — the same treatment `state.networkIds` gets.
 */

import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from '../config/config-resources.js';

/**
 * How long to wait between refresh attempts for a given machine.
 *
 * Licence soft-windows (`refreshRecommendedAt`) run to days, so checking twice a
 * day leaves ample margin to act before one expires while keeping the cost per
 * command at zero for all but the first invocation in a window.
 */
export const LICENSE_REFRESH_COOLDOWN_MS = 12 * 60 * 60 * 1000;

/** Whether enough time has passed to attempt a refresh for this machine. */
export async function isRefreshDue(machineName: string, now = Date.now()): Promise<boolean> {
  const config = await configService.getCurrent();
  const last = config?.state?.licenseRefresh?.[machineName];

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
  const configName = configService.getEffectiveConfigName();
  await configFileStorage.updateState(configName, (config) => ({
    ...config,
    state: {
      ...(config.state ?? {}),
      licenseRefresh: {
        ...(config.state?.licenseRefresh ?? {}),
        [machineName]: now,
      },
    },
  }));
}
