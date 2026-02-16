import { spawn, spawnSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { dirname, join } from 'node:path';
import { t } from '../i18n/index.js';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  releaseUpdateLock,
  STAGED_UPDATE_DIR,
} from '../utils/platform.js';
import type { CliUpdateState } from '@rediacc/shared/update';
import { isCooldownExpired } from '@rediacc/shared/update';
import { VERSION } from '../version.js';
import { telemetryService } from './telemetry.js';
import {
  cleanupStaleStagedFiles,
  getStagedBinaryPath,
  readUpdateState,
  writeUpdateState,
} from './update-state.js';
import { compareVersions, computeSha256, downloadFile, fetchManifest } from './updater.js';

const WORKER_TIMEOUT_MS = 30_000;
const RENAME_RETRIES = 2;
const RENAME_RETRY_DELAY_MS = 500;
const MAX_APPLY_ATTEMPTS = 5;

/**
 * Rename with retry for transient EBUSY/EPERM (Windows Defender, antivirus scanners).
 */
async function renameWithRetry(src: string, dst: string): Promise<void> {
  for (let i = 0; i <= RENAME_RETRIES; i++) {
    try {
      await fs.rename(src, dst);
      return;
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if ((code === 'EBUSY' || code === 'EPERM' || code === 'ETXTBSY') && i < RENAME_RETRIES) {
        await new Promise((resolve) => setTimeout(resolve, RENAME_RETRY_DELAY_MS));
        continue;
      }
      throw err;
    }
  }
}

// ============================================================================
// A. Background Update Worker
// ============================================================================

/**
 * Entry point when `--background-update` is detected. Runs in a detached process.
 * Fetches manifest, downloads binary, verifies SHA256, stages for next launch.
 */
export async function runBackgroundUpdateWorker(): Promise<void> {
  // Safety kill — prevent zombie processes
  const safetyTimer = setTimeout(() => process.exit(1), WORKER_TIMEOUT_MS);
  safetyTimer.unref();

  try {
    const locked = await acquireUpdateLock();
    if (!locked) return;

    try {
      const state = await readUpdateState();

      // Double-check cooldown (race protection against multiple spawns)
      if (!isCooldownExpired(state)) return;

      const platformKey = getPlatformKey();
      if (!platformKey) return;

      const manifest = await fetchManifest(10_000);

      if (compareVersions(VERSION, manifest.version) >= 0) {
        // Already up to date — record successful check
        state.lastCheckAt = new Date().toISOString();
        state.lastAttemptAt = new Date().toISOString();
        state.consecutiveFailures = 0;
        state.lastError = null;
        await writeUpdateState(state);
        return;
      }

      const binaryInfo = manifest.binaries[platformKey];
      if (!binaryInfo?.url || !binaryInfo?.sha256) {
        throw new Error(`No binary available for ${platformKey}`);
      }

      // Download to temp file
      await fs.mkdir(STAGED_UPDATE_DIR, { recursive: true });
      const stagedPath = getStagedBinaryPath(manifest.version);
      const tmpPath = `${stagedPath}.tmp`;

      await downloadFile(binaryInfo.url, tmpPath);

      // Verify SHA256
      const actualHash = await computeSha256(tmpPath);
      if (actualHash !== binaryInfo.sha256) {
        await fs.unlink(tmpPath).catch(() => {});
        throw new Error('SHA256 checksum mismatch after download');
      }

      // Rename temp to staged
      await fs.rename(tmpPath, stagedPath);
      if (process.platform !== 'win32') {
        await fs.chmod(stagedPath, 0o755);
      }

      // Update state with pending update
      state.lastCheckAt = new Date().toISOString();
      state.lastAttemptAt = new Date().toISOString();
      state.consecutiveFailures = 0;
      state.lastError = null;
      state.pendingUpdate = {
        version: manifest.version,
        stagedPath,
        sha256: binaryInfo.sha256,
        platformKey,
        downloadedAt: new Date().toISOString(),
        releaseNotesUrl: manifest.releaseNotesUrl,
      };
      await writeUpdateState(state);
      await cleanupStaleStagedFiles(state);
    } finally {
      await releaseUpdateLock();
    }
  } catch (err) {
    // Increment failure counter
    try {
      const state = await readUpdateState();
      state.lastAttemptAt = new Date().toISOString();
      state.consecutiveFailures += 1;
      state.lastError = err instanceof Error ? err.message : String(err);
      await writeUpdateState(state);
    } catch {
      // Cannot even write state — give up silently
    }
  }
}

// ============================================================================
// B. Spawn Background Update
// ============================================================================

/**
 * Called from normal startup. Spawns a detached background process to check
 * for and download updates if cooldown has expired.
 */
export async function maybeSpawnBackgroundUpdate(): Promise<void> {
  if (!isSEA() || isUpdateDisabled()) return;

  try {
    const state = await readUpdateState();
    if (!isCooldownExpired(state)) return;

    telemetryService.trackEvent('update.spawn');
    spawn(process.execPath, ['--background-update'], {
      detached: true,
      stdio: 'ignore',
    }).unref();
  } catch {
    // Never interfere with CLI operation
  }
}

// ============================================================================
// C. Apply Pending Update
// ============================================================================

/**
 * Called at startup before CLI runs. If a staged binary exists and passes
 * SHA256 verification, atomically replaces the current binary.
 * Returns true if an update was applied.
 */
export async function applyPendingUpdate(): Promise<boolean> {
  if (!isSEA() || isUpdateDisabled()) return false;

  let state: CliUpdateState;
  try {
    state = await readUpdateState();
  } catch {
    return false;
  }

  // Clean up old binary from previous update
  await cleanupOldBinary();

  if (!state.pendingUpdate) return false;

  const { version, stagedPath, sha256 } = state.pendingUpdate;

  // Downgrade protection: skip if staged version is not newer
  if (compareVersions(VERSION, version) >= 0) {
    state.pendingUpdate = null;
    await writeUpdateState(state).catch(() => {});
    await cleanupStaleStagedFiles(state).catch(() => {});
    return false;
  }

  // Verify staged binary exists
  try {
    await fs.access(stagedPath);
  } catch {
    // Staged binary missing — clear pending
    state.pendingUpdate = null;
    await writeUpdateState(state).catch(() => {});
    return false;
  }

  // Re-verify SHA256 before applying
  try {
    const actualHash = await computeSha256(stagedPath);
    if (actualHash !== sha256) {
      await fs.unlink(stagedPath).catch(() => {});
      state.pendingUpdate = null;
      state.lastError = 'SHA256 verification failed before apply';
      await writeUpdateState(state).catch(() => {});
      return false;
    }
  } catch {
    state.pendingUpdate = null;
    await writeUpdateState(state).catch(() => {});
    return false;
  }

  // Warmup validation: run staged binary with --warmup to verify it works
  const warmupResult = spawnSync(stagedPath, ['--warmup'], {
    timeout: 10_000,
    stdio: 'ignore',
  });
  if (warmupResult.status !== 0) {
    await fs.unlink(stagedPath).catch(() => {});
    state.pendingUpdate = null;
    state.lastError = 'Staged binary failed warmup validation';
    await writeUpdateState(state).catch(() => {});
    telemetryService.trackEvent('update.apply.validation_failed', { version });
    return false;
  }

  // Max apply retries: cap at MAX_APPLY_ATTEMPTS to prevent infinite retry loops
  const attempts = (state.pendingUpdate.applyAttempts ?? 0) + 1;
  state.pendingUpdate.applyAttempts = attempts;
  await writeUpdateState(state).catch(() => {});

  if (attempts > MAX_APPLY_ATTEMPTS) {
    telemetryService.trackEvent('update.apply.skipped_max_retries', { version, attempts });
    state.pendingUpdate = null;
    state.lastError = `Update apply failed after ${MAX_APPLY_ATTEMPTS} attempts`;
    await writeUpdateState(state).catch(() => {});
    await cleanupStaleStagedFiles(state).catch(() => {});
    return false;
  }

  // Acquire lock for the atomic swap
  const locked = await acquireUpdateLock();
  if (!locked) return false;

  try {
    const execPath = process.execPath;
    const execDir = dirname(execPath);
    const tempPath = join(execDir, `.rdc-apply-${Date.now()}.tmp`);

    // Copy staged → temp in exec dir, then atomic rename with rollback
    await fs.copyFile(stagedPath, tempPath);
    const oldPath = getOldBinaryPath();
    await fs.unlink(oldPath).catch(() => {});
    await renameWithRetry(execPath, oldPath);
    try {
      await renameWithRetry(tempPath, execPath);
    } catch (renameErr) {
      // Rollback: restore old binary to execPath so CLI isn't broken
      await fs.rename(oldPath, execPath).catch(() => {});
      throw renameErr;
    }

    if (process.platform !== 'win32') {
      await fs.chmod(execPath, 0o755);
    }

    // Clear pending update and clean up
    state.pendingUpdate = null;
    await writeUpdateState(state).catch(() => {});
    await cleanupStaleStagedFiles(state).catch(() => {});

    telemetryService.trackEvent('update.apply.success', { from: VERSION, to: version });
    process.stderr.write(
      `${t('commands.update.autoApplied', { version, from: VERSION })}\n`
    );
    return true;
  } catch (err) {
    const errCode = (err as NodeJS.ErrnoException).code;
    if (errCode === 'EBUSY' || errCode === 'EPERM' || errCode === 'ETXTBSY') {
      // Leave pendingUpdate for retry on next launch (common on Windows)
      telemetryService.trackEvent('update.apply.failed', { version, error: errCode, attempts, code: errCode });
      return false;
    }
    // Other errors — clear pending to avoid retry loop
    const errorMsg = err instanceof Error ? err.message : String(err);
    telemetryService.trackEvent('update.apply.failed', { version, error: errorMsg, attempts, code: errCode });
    state.pendingUpdate = null;
    state.lastError = errorMsg;
    await writeUpdateState(state).catch(() => {});
    return false;
  } finally {
    await releaseUpdateLock();
  }
}
