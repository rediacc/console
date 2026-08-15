/**
 * Disaster-recovery nudge for the chunk-store backup path.
 *
 * The DR story for these backups reduces to config-storage enrollment (spec/02
 * decision 14): a repo's `credential` field IS its LUKS slot-0 passphrase, and it
 * only survives a bare-metal restore if it syncs inside the CEK-encrypted config
 * blob. Back up the data without enrolling config storage and the ciphertext is
 * safe but unopenable — the passphrase died with the host.
 *
 * So when a backup is enabled or a restore lands into a config that has NO remote
 * config store, we print a one-line stderr nudge (the `formatStaleCacheWarning`
 * warn-pattern: informational, never a prompt, never fatal). It reads the config
 * OFFLINE via `configFileStorage.load` — deliberately NOT `configService
 * .getCurrent()`, which would pull the network.
 */

import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import { hasRemoteConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';

/** Warn if the active config has no config-storage enrollment (offline check). */
export async function warnIfConfigStorageUnenrolled(): Promise<void> {
  // Fail-safe: only nudge when we can PROVE there is no enrollment. Any error
  // reading the config (missing file, locked, mocked away in a test) leaves the
  // operation it decorates untouched — a DR nudge must never break a backup or
  // a restore.
  let enrolled = true;
  try {
    const name = configService.getEffectiveConfigName();
    const config = await configFileStorage.load(name);
    enrolled = hasRemoteConfig(config);
  } catch {
    return;
  }
  if (!enrolled) outputService.warn(t('commands.backup.drNudge'));
}
