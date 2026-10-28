/**
 * Shapes the renet provisioner passes around: the provision result and options, the host cache entry,
 * the local-hash memo and the per-run context.
 */

import type { RenetArch } from '../core/embedded-assets.js';

/** Result of a provisioning operation */
export interface ProvisionResult {
  /** Whether provisioning succeeded */
  success: boolean;
  /** Action taken: uploaded new binary, verified existing, or failed */
  action: 'uploaded' | 'verified' | 'failed' | 'version_rejected';
  /** Detected architecture (undefined if detection failed) */
  arch?: RenetArch;
  /** Error message if failed */
  error?: string;
  /** Whether running services were restarted after binary update */
  servicesRestarted?: boolean;
  /**
   * The router refresh this provision owed and did not run because the caller
   * asked to defer it (`deferRouterRefresh`); the caller runs
   * {@link RenetProvisionerService.refreshRouter} once its own work is done.
   */
  routerRefreshDue?: boolean;
  /** Exact remote binary path that was verified or installed */
  remotePath: string;
}

/** Cache entry for a provisioned host */
export interface CacheEntry {
  hash: string;
  arch: RenetArch;
  provisionedAt: number;
}

/** Memoized SHA256 of a local binary, keyed by file identity */
export interface LocalHashMemo {
  mtimeMs: number;
  size: number;
  hash: string;
}

export interface InstallResult {
  binaryUpdated: boolean;
  currentUpdated: boolean;
}

/** Options for {@link RenetProvisionerService.provision}. */
export interface ProvisionOptions {
  localBinaryPath?: string;
  /** Restart running services after binary update. Default: false. */
  restartServices?: boolean;
  /**
   * With `restartServices`, report the owed router refresh as
   * `routerRefreshDue` instead of running it. The executor defers it past the
   * runtime converge pass, so the router switches to the new socket layout only
   * after the repo daemons moved there (agent/plans/PLAN-renet-runtime-converge.md,
   * decision 2).
   */
  deferRouterRefresh?: boolean;
  debug?: boolean;
  /**
   * Called only when the remote hash differs from the local one, immediately
   * before the binary is staged. A throw aborts the provision before anything
   * reaches the machine.
   */
  uploadGuard?: () => void | Promise<void>;
}

export interface ProvisionContext {
  arch: RenetArch;
  binary: Buffer;
  localHash: string;
  cacheKey: string;
  remoteInstallPath: string;
}
