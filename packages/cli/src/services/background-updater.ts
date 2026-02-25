import { spawn, spawnSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { dirname, join } from 'node:path';
import type { CliUpdateState } from '@rediacc/shared/update';
import { isCooldownExpired } from '@rediacc/shared/update';
import { t } from '../i18n/index.js';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  STAGED_UPDATE_DIR,
  type PlatformKey,
} from '../utils/platform.js';
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
 * Record a successful check timestamp and reset failure counters.
 */
function markSuccessfulCheck(state: CliUpdateState): void {
  state.lastCheckAt = new Date().toISOString();
  state.lastAttemptAt = new Date().toISOString();
  state.consecutiveFailures = 0;
  state.lastError = null;
}

/**
 * Download, verify, and stage a new binary for the given manifest.
 */
async function downloadAndStage(
  state: CliUpdateState,
  manifest: Awaited<ReturnType<typeof fetchManifest>>,
  platformKey: PlatformKey
): Promise<void> {
  const binaryInfo = manifest.binaries[platformKey];
  if (!binaryInfo?.url || !binaryInfo.sha256) {
    throw new Error(`No binary available for ${platformKey}`);
  }

  await fs.mkdir(STAGED_UPDATE_DIR, { recursive: true });
  const stagedPath = getStagedBinaryPath(manifest.version);
  const tmpPath = `${stagedPath}.tmp`;

  await downloadFile(binaryInfo.url, tmpPath);

  const actualHash = await computeSha256(tmpPath);
  if (actualHash !== binaryInfo.sha256) {
    await fs.unlink(tmpPath).catch(() => {});
    throw new Error('SHA256 checksum mismatch after download');
  }

  await fs.rename(tmpPath, stagedPath);
  if (process.platform !== 'win32') {
    await fs.chmod(stagedPath, 0o755);
  }

  markSuccessfulCheck(state);
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
}

/**
 * Entry point when `--background-update` is detected. Runs in a detached process.
 * Fetches manifest, downloads binary, verifies SHA256, stages for next launch.
 */
export async function runBackgroundUpdateWorker(): Promise<void> {
  const safetyTimer = setTimeout(() => process.exit(1), WORKER_TIMEOUT_MS);
  safetyTimer.unref();

  try {
    const releaseLock = await acquireUpdateLock();
    if (!releaseLock) return;

    try {
      const state = await readUpdateState();
      if (!isCooldownExpired(state)) return;

      const platformKey = getPlatformKey();
      if (!platformKey) return;

      const manifest = await fetchManifest(10_000);

      if (compareVersions(VERSION, manifest.version) >= 0) {
        markSuccessfulCheck(state);
        await writeUpdateState(state);
        return;
      }

      await downloadAndStage(state, manifest, platformKey);
    } finally {
      await releaseLock();
    }
  } catch (err) {
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
 * Validate staged binary: existence, SHA256, and warmup check.
 * Returns null on success, or an error string on failure.
 */
async function validateStagedBinary(stagedPath: string, sha256: string): Promise<string | null> {
  try {
    await fs.access(stagedPath);
  } catch {
    return 'Staged binary missing';
  }

  try {
    const actualHash = await computeSha256(stagedPath);
    if (actualHash !== sha256) {
      await fs.unlink(stagedPath).catch(() => {});
      return 'SHA256 verification failed before apply';
    }
  } catch {
    return 'SHA256 computation failed';
  }

  const warmupResult = spawnSync(stagedPath, ['--warmup'], {
    timeout: 10_000,
    stdio: 'ignore',
  });
  if (warmupResult.status !== 0) {
    await fs.unlink(stagedPath).catch(() => {});
    return 'Staged binary failed warmup validation';
  }

  return null;
}

/**
 * Perform the atomic binary swap: current → old, staged copy → current.
 */
async function atomicBinarySwap(stagedPath: string): Promise<void> {
  const execPath = process.execPath;
  const execDir = dirname(execPath);
  const tempPath = join(execDir, `.rdc-apply-${Date.now()}.tmp`);

  await fs.copyFile(stagedPath, tempPath);
  const oldPath = getOldBinaryPath();
  await fs.unlink(oldPath).catch(() => {});
  await renameWithRetry(execPath, oldPath);
  try {
    await renameWithRetry(tempPath, execPath);
  } catch (renameErr) {
    await fs.rename(oldPath, execPath).catch((restoreErr: unknown) => {
      const msg = restoreErr instanceof Error ? restoreErr.message : String(restoreErr);
      process.stderr.write(
        `CRITICAL: Failed to restore original binary during update. CLI may be broken — please reinstall. Error: ${msg}\n`
      );
    });
    throw renameErr;
  }

  if (process.platform !== 'win32') {
    await fs.chmod(execPath, 0o755);
  }
}

/**
 * Clear pending update from state and clean up staged files.
 */
async function clearPendingUpdate(state: CliUpdateState, error?: string): Promise<void> {
  state.pendingUpdate = null;
  if (error) state.lastError = error;
  await writeUpdateState(state).catch(() => {});
  await cleanupStaleStagedFiles(state).catch(() => {});
}

/**
 * Pre-flight checks for applying a pending update.
 * Returns the state if ready to apply, or null if not applicable.
 */
async function prepareApply(): Promise<CliUpdateState | null> {
  if (!isSEA() || isUpdateDisabled()) return null;

  let state: CliUpdateState;
  try {
    state = await readUpdateState();
  } catch {
    return null;
  }

  await cleanupOldBinary();
  if (!state.pendingUpdate) return null;

  // Downgrade protection
  if (compareVersions(VERSION, state.pendingUpdate.version) >= 0) {
    await clearPendingUpdate(state);
    return null;
  }

  const validationError = await validateStagedBinary(
    state.pendingUpdate.stagedPath,
    state.pendingUpdate.sha256
  );
  if (validationError) {
    if (validationError.includes('warmup')) {
      telemetryService.trackEvent('update.apply.validation_failed', {
        version: state.pendingUpdate.version,
      });
    }
    await clearPendingUpdate(state, validationError);
    return null;
  }

  return state;
}

/**
 * Handle swap failure: track telemetry and optionally clear pending state.
 */
async function handleSwapError(
  state: CliUpdateState,
  err: unknown,
  version: string,
  attempts: number
): Promise<void> {
  const errCode = (err as NodeJS.ErrnoException).code;
  const isTransient = errCode === 'EBUSY' || errCode === 'EPERM' || errCode === 'ETXTBSY';
  const detailedMsg = err instanceof Error ? err.message : String(err);
  const errorMsg = isTransient ? errCode : detailedMsg;

  telemetryService.trackEvent('update.apply.failed', {
    version,
    error: errorMsg,
    attempts,
    code: errCode,
  });

  if (!isTransient) {
    state.pendingUpdate = null;
    state.lastError = errorMsg!;
    await writeUpdateState(state).catch(() => {});
  }
}

/**
 * Called at startup before CLI runs. If a staged binary exists and passes
 * SHA256 verification, atomically replaces the current binary.
 * Returns true if an update was applied.
 */
export async function applyPendingUpdate(): Promise<boolean> {
  const state = await prepareApply();
  if (!state?.pendingUpdate) return false;

  const { version, stagedPath } = state.pendingUpdate;
  const attempts = (state.pendingUpdate.applyAttempts ?? 0) + 1;
  state.pendingUpdate.applyAttempts = attempts;
  await writeUpdateState(state).catch(() => {});

  if (attempts > MAX_APPLY_ATTEMPTS) {
    telemetryService.trackEvent('update.apply.skipped_max_retries', { version, attempts });
    await clearPendingUpdate(state, `Update apply failed after ${MAX_APPLY_ATTEMPTS} attempts`);
    return false;
  }

  const releaseLock = await acquireUpdateLock();
  if (!releaseLock) return false;

  try {
    await atomicBinarySwap(stagedPath);

    state.pendingUpdate = null;
    await writeUpdateState(state).catch(() => {});
    await cleanupStaleStagedFiles(state).catch(() => {});

    telemetryService.trackEvent('update.apply.success', { from: VERSION, to: version });
    process.stderr.write(`${t('commands.update.autoApplied', { version, from: VERSION })}\n`);
    return true;
  } catch (err) {
    await handleSwapError(state, err, version, attempts);
    return false;
  } finally {
    await releaseLock();
  }
}
