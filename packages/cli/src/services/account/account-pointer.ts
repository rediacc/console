import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { getEffectiveConfigName } from '../config/config-name.js';

/**
 * The account section of a config file, read synchronously.
 *
 * Every `/account/*` leaf is kind `public`/`identifier`/`pii` in the
 * sensitivity registry, and `encryptAtRest` defaults to true only for
 * `secret`/`credential`, so the account section is always plaintext on disk.
 * That is what lets us read it synchronously here, feeding the synchronous
 * server-URL/channel/releases resolvers (updater, telemetry, subscription-auth)
 * without decrypting the whole config.
 */
export interface AccountPointer {
  accountServer?: string;
  e2ePublicKey?: string;
  updateChannel?: string;
  releasesUrl?: string;
}

/**
 * Read the `account` section of the active config file (or a named one).
 *
 * Returns `{}` on ANY error (missing file, malformed JSON, no account section).
 * No caching: reads are rare and tiny, and cache invalidation after
 * resolveAndSyncServer / `update --channel` writes would be a bug farm.
 */
export function readAccountPointer(configName = getEffectiveConfigName()): AccountPointer {
  try {
    const raw = readFileSync(join(getConfigDir(), `${configName}.json`), 'utf8');
    const parsed = JSON.parse(raw) as { account?: AccountPointer };
    return parsed.account ?? {};
  } catch {
    return {};
  }
}
