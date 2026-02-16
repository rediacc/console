import { promises as fs } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { isCooldownExpired } from '@rediacc/shared/update';
import { applyPendingUpdate } from '../services/background-updater.js';
import { outputService } from '../services/output.js';
import { readUpdateState, writeUpdateState } from '../services/update-state.js';
import { checkForUpdate, performUpdate } from '../services/updater.js';
import { handleError } from '../utils/errors.js';
import { getOldBinaryPath, isSEA } from '../utils/platform.js';
import { VERSION } from '../version.js';

/**
 * Handle the --check-only flow.
 */
async function handleCheckOnly(): Promise<void> {
  // Show pending staged update info if present
  const state = await readUpdateState();
  if (state.pendingUpdate) {
    outputService.info(
      t('commands.update.staged', { version: state.pendingUpdate.version })
    );
  }

  const result = await checkForUpdate();
  if (result.updateAvailable) {
    outputService.info(
      t('commands.update.available', {
        version: result.latestVersion!,
        current: result.currentVersion,
      })
    );
    if (result.releaseNotesUrl) {
      outputService.info(t('commands.update.releaseNotes', { url: result.releaseNotesUrl }));
    }
  } else {
    outputService.success(t('commands.update.upToDate', { version: VERSION }));
  }
}

/**
 * Handle the update execution flow.
 */
async function handleUpdate(force: boolean): Promise<void> {
  // If a pending update exists and not forcing, apply it directly
  if (!force) {
    const state = await readUpdateState();
    if (state.pendingUpdate) {
      outputService.info(
        t('commands.update.downloading', { version: state.pendingUpdate.version })
      );
      const applied = await applyPendingUpdate();
      if (applied) {
        outputService.success(
          t('commands.update.success', { from: VERSION, to: state.pendingUpdate.version })
        );
        return;
      }
      // Apply failed — fall through to regular update
    }
  }

  outputService.info(t('commands.update.checking'));
  const checkResult = await checkForUpdate();

  if (!force && !checkResult.updateAvailable) {
    outputService.success(t('commands.update.upToDate', { version: VERSION }));
    return;
  }

  const targetVersion = checkResult.latestVersion ?? VERSION;
  outputService.info(t('commands.update.downloading', { version: targetVersion }));

  const result = await performUpdate({
    force,
    onProgress: (downloaded, total) => {
      if (total > 0) {
        const percent = Math.round((downloaded / total) * 100);
        process.stderr.write(`\r${t('commands.update.progress', { percent: percent.toString() })}`);
      }
    },
  });

  if (result.success && result.error === 'update.errors.binaryBusy') {
    // Binary was locked — staged for next launch
    process.stderr.write('\n');
    outputService.info(
      t('commands.update.stagedFallback', { version: result.toVersion })
    );
  } else if (result.success && result.fromVersion !== result.toVersion) {
    process.stderr.write('\n');
    outputService.success(
      t('commands.update.success', { from: result.fromVersion, to: result.toVersion })
    );
    // Clear pending update and reset check timestamp after manual update
    const state = await readUpdateState();
    state.pendingUpdate = null;
    state.lastCheckAt = new Date().toISOString();
    await writeUpdateState(state);
  } else if (result.success) {
    outputService.success(t('commands.update.upToDate', { version: VERSION }));
  } else {
    const errorKey = result.error ?? t('commands.update.unknownError');
    outputService.error(t('commands.update.failed', { error: errorKey }));
    process.exit(1);
  }
}

/**
 * Handle the --rollback flow.
 */
async function handleRollback(): Promise<void> {
  const oldPath = getOldBinaryPath();

  // Check if .old binary exists
  try {
    await fs.access(oldPath);
  } catch {
    outputService.error(t('commands.update.rollbackNoBackup'));
    process.exit(1);
  }

  try {
    // Optionally validate the .old binary with --warmup
    const warmupResult = spawnSync(oldPath, ['--warmup'], {
      timeout: 10_000,
      stdio: 'ignore',
    });
    if (warmupResult.status !== 0) {
      outputService.error(t('commands.update.rollbackFailed', { error: 'Previous binary failed warmup validation' }));
      process.exit(1);
    }

    const execPath = process.execPath;
    const execDir = dirname(execPath);
    const rollbackTmp = join(execDir, `.rdc-rollback-${Date.now()}.tmp`);

    // Atomic swap: current → tmp, old → current, delete tmp
    await fs.rename(execPath, rollbackTmp);
    try {
      await fs.rename(oldPath, execPath);
    } catch (err) {
      // Rollback the rollback: restore current binary
      await fs.rename(rollbackTmp, execPath).catch(() => {});
      throw err;
    }
    await fs.unlink(rollbackTmp).catch(() => {});

    if (process.platform !== 'win32') {
      await fs.chmod(execPath, 0o755);
    }

    // Clear pendingUpdate to prevent re-applying the bad version
    const state = await readUpdateState();
    state.pendingUpdate = null;
    await writeUpdateState(state);

    outputService.success(t('commands.update.rollbackSuccess'));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    outputService.error(t('commands.update.rollbackFailed', { error: message }));
    process.exit(1);
  }
}

/**
 * Handle the --status flow.
 */
async function handleStatus(): Promise<void> {
  const state = await readUpdateState();

  const lines: string[] = [];
  lines.push(`Current version: ${VERSION}`);
  lines.push(`Auto-update: ${isSEA() ? 'enabled' : 'disabled (not SEA)'}`);
  lines.push(`Last check: ${state.lastCheckAt ?? 'never'}`);
  lines.push(`Last attempt: ${state.lastAttemptAt ?? 'never'}`);
  lines.push(`Consecutive failures: ${state.consecutiveFailures}`);

  if (state.lastError) {
    lines.push(`Last error: ${state.lastError}`);
  }

  if (state.pendingUpdate) {
    lines.push('');
    lines.push('Pending update:');
    lines.push(`  Version: ${state.pendingUpdate.version}`);
    lines.push(`  Downloaded at: ${state.pendingUpdate.downloadedAt}`);
    lines.push(`  Platform: ${state.pendingUpdate.platformKey}`);
    lines.push(`  Apply attempts: ${state.pendingUpdate.applyAttempts ?? 0}`);
  }

  // Next check computation
  if (state.lastAttemptAt) {
    const cooldownExpired = isCooldownExpired(state);
    lines.push('');
    lines.push(`Next check: ${cooldownExpired ? 'now (cooldown expired)' : 'waiting for cooldown'}`);
  }

  outputService.info(lines.join('\n'));
}

export function registerUpdateCommand(program: Command): void {
  program
    .command('update')
    .description(t('commands.update.description'))
    .option('--force', t('commands.update.force'))
    .option('--check-only', t('commands.update.checkOnly'))
    .option('--rollback', t('commands.update.rollback'))
    .option('--status', t('commands.update.statusDescription'))
    .action(async (options) => {
      try {
        if (!isSEA()) {
          outputService.error(t('commands.update.notSEA'));
          process.exit(1);
        }

        if (options.rollback) {
          await handleRollback();
        } else if (options.status) {
          await handleStatus();
        } else if (options.checkOnly) {
          await handleCheckOnly();
        } else {
          await handleUpdate(options.force);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
