import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';
import { checkForUpdate, performUpdate } from '../services/updater.js';
import { handleError } from '../utils/errors.js';
import { isSEA } from '../utils/platform.js';
import { VERSION } from '../version.js';

/**
 * Handle the --check-only flow.
 */
async function handleCheckOnly(): Promise<void> {
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

  if (result.success && result.fromVersion !== result.toVersion) {
    process.stderr.write('\n');
    outputService.success(
      t('commands.update.success', { from: result.fromVersion, to: result.toVersion })
    );
  } else if (result.success) {
    outputService.success(t('commands.update.upToDate', { version: VERSION }));
  } else {
    const errorKey = result.error ?? t('commands.update.unknownError');
    outputService.error(t('commands.update.failed', { error: errorKey }));
    process.exit(1);
  }
}

export function registerUpdateCommand(program: Command): void {
  program
    .command('update')
    .description(t('commands.update.description'))
    .option('--force', t('commands.update.force'))
    .option('--check-only', t('commands.update.checkOnly'))
    .action(async (options) => {
      try {
        if (!isSEA()) {
          outputService.error(t('commands.update.notSEA'));
          process.exit(1);
        }

        if (options.checkOnly) {
          await handleCheckOnly();
        } else {
          await handleUpdate(options.force);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
