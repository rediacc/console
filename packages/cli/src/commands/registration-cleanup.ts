import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { compositeKey } from '../utils/config-schema.js';

/**
 * Drop the `latest` registration of `name` after a failure that ran no job, so the job's own rollback step never will.
 *
 * A failing cleanup must not hide the error that caused it, so it never throws; but it is not silent either: the
 * config still lists the repository, and the warning says so rather than leaving a stale entry nobody was told about.
 */
export async function dropRegistrationAfterFailure(name: string): Promise<void> {
  try {
    await configService.removeRepository(compositeKey(name, 'latest'));
  } catch (error) {
    outputService.warn(
      t('commands.backup.restore.registrationCleanupFailed', {
        name,
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
}
