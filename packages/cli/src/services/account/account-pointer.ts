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
 * `accountServer` is per device (DEVICE_LOCAL_POINTERS), so a device that has not logged in yet
 * holds none even when its config is a remote one pulled from a store. Such a config already names
 * its account server: `remote.apiUrl`, the server the store lives on (`config remote enable` takes
 * it from the same resolver as login). It stands in until the device logs in, so `rdc subscription
 * login` on a new device, or after `logout`, talks to the store's server instead of asking for a
 * region.
 *
 * Returns `{}` on ANY error (missing file, malformed JSON, no account section).
 * No caching: reads are rare and tiny, and cache invalidation after
 * resolveAndSyncServer / `update --channel` writes would be a bug farm.
 */
export function readAccountPointer(configName = getEffectiveConfigName()): AccountPointer {
  try {
    const raw = readFileSync(join(getConfigDir(), `${configName}.json`), 'utf8');
    const parsed = JSON.parse(raw) as { account?: AccountPointer; remote?: { apiUrl?: string } };
    const account = { ...(parsed.account ?? {}) };
    account.accountServer ??= parsed.remote?.apiUrl;
    if (account.accountServer === undefined) delete account.accountServer;
    return account;
  } catch {
    return {};
  }
}
