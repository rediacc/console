/**
 * The local (per-workstation) provisioning lock: one rdc process provisions a
 * given host at a time, and a queued process says so instead of looking hung.
 * Split out of renet-provisioner.ts, which only calls withLocalProvisionLock.
 */

import * as os from 'node:os';
import * as path from 'node:path';
import { busy, type CliExitError } from '../../utils/cli-exit-error.js';
import { formatDuration } from '../../utils/format.js';
import { updateSpinnerText } from '../../utils/spinner.js';
import {
  acquireLocalLock,
  type LockHolder,
  LockTimeoutError,
  releaseLocalLock,
} from '../core/file-lock.js';
import { outputService } from '../core/output.js';

const DEFAULT_LOCAL_LOCK_TIMEOUT_MS = 2 * 60 * 1000;
const MIN_LOCAL_LOCK_TIMEOUT_MS = 1_000;
const MAX_LOCAL_LOCK_TIMEOUT_MS = 10 * 60 * 1000;
const LOCAL_LOCK_POLL_MS = 250;

/**
 * How long to queue behind another local rdc process before refusing.
 *
 * Two minutes is sized for a genuine cold provision (a binary upload plus remote
 * install), not for impatience: a shorter budget would start failing runs that
 * were about to succeed. An env override exists for unusual links; there is no
 * CLI flag, because a knob almost nobody turns is not worth 13 locales and a
 * contract regeneration.
 */
function localLockTimeoutMs(): number {
  const raw = Number(process.env.REDIACC_PROVISION_LOCK_TIMEOUT_MS);
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_LOCAL_LOCK_TIMEOUT_MS;
  return Math.min(Math.max(raw, MIN_LOCAL_LOCK_TIMEOUT_MS), MAX_LOCAL_LOCK_TIMEOUT_MS);
}

/** Describe a lock holder for a human: "pid 1234, held 2m 4s, running `rdc backup run`". */
function describeHolder(holder: LockHolder): string {
  const parts = [holder.pid === null ? 'unknown pid' : `pid ${holder.pid}`];
  if (holder.heldForMs !== null) parts.push(`held ${formatDuration(holder.heldForMs)}`);
  if (holder.command) parts.push(`running \`${holder.command}\``);
  return parts.join(', ');
}

/**
 * Tell the operator they are queued, the moment we know it.
 *
 * Prefers retitling the live spinner, so the wait replaces the misleading
 * "Provisioning renet" text rather than scrolling past it. With no TTY there is
 * no spinner to retitle, so fall back to a single stderr note (stderr keeps JSON
 * output on stdout clean).
 */
function announceLockWait(cacheKey: string, holder: LockHolder): void {
  const message = `Waiting for another rdc process to finish provisioning renet for ${cacheKey} (${describeHolder(holder)})`;
  if (!updateSpinnerText(`${message}...`)) outputService.info(message);
}

/** Turn a provisioning-lock timeout into an actionable BUSY refusal. */
function lockBusyError(cacheKey: string, error: LockTimeoutError): CliExitError {
  const { holder } = error;
  const details = [`Lock: ${error.lockPath}`];
  if (holder.command) details.push(`Holder: ${holder.command}`);

  return busy(
    `Another rdc process is still provisioning renet for ${cacheKey} (${describeHolder(holder)}).`,
    {
      details,
      next: {
        summary: 'Wait for the other run to finish, then retry. Clear the lock only if it is dead.',
        options: [
          ...(holder.pid === null
            ? []
            : [
                {
                  description: 'Inspect the process holding the lock',
                  run: `ps -p ${holder.pid} -o pid,etime,cmd`,
                },
              ]),
          {
            description: 'Remove the lock if that process is gone',
            run: `rm -rf ${error.lockPath}`,
          },
        ],
      },
    }
  );
}

export async function withLocalProvisionLock<T>(
  cacheKey: string,
  fn: () => Promise<T>
): Promise<T> {
  const lockPath = path.join(
    os.tmpdir(),
    `.rdc-renet-provision-${cacheKey.replaceAll(/[^a-zA-Z0-9_.-]/g, '_')}.lock`
  );

  try {
    await acquireLocalLock(lockPath, {
      deadline: Date.now() + localLockTimeoutMs(),
      pollMs: LOCAL_LOCK_POLL_MS,
      // Contention is INVISIBLE without this: the operator sees the "Provisioning renet" spinner sit there and reasonably concludes the CLI has hung, when in fact another local rdc run is ahead of them.
      onWait: (holder) => announceLockWait(cacheKey, holder),
    });
  } catch (error) {
    if (error instanceof LockTimeoutError) throw lockBusyError(cacheKey, error);
    throw error;
  }

  try {
    return await fn();
  } finally {
    await releaseLocalLock(lockPath);
  }
}
