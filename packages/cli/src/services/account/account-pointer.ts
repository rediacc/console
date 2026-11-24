import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PREVIEW_NAME_PATTERN } from '@rediacc/shared/config-schema';
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
  /** Set only while a preview overlay exists: the preview's name (PLAN-preview-signer.md D8). */
  preview?: string;
  /** Set only while a preview overlay exists: the preview's own token file, so the real one is never read or written. */
  tokenFile?: string;
}

/** The token file of preview `previewName` on config `configName`, beside the config's own `api-token-<config>.json`. */
export function previewTokenFile(
  configName: string,
  previewName: string,
  configDir = getConfigDir()
): string {
  return join(configDir, `api-token-${configName}.preview-${previewName}.json`);
}

interface RawPreview {
  name?: unknown;
  host?: unknown;
  channel?: unknown;
}

/**
 * While the config holds a preview block, the pointer answers the preview's host and channel and its
 * own token file, and nothing from the `account` section: the real server's E2E key belongs to the
 * real server, and an on-prem releases URL does not serve the preview channel. A block that is not a
 * well-formed preview answers nothing (readAccountPointer returns `{}`); the strict config parse refuses it on the next load.
 */
function previewPointer(
  preview: RawPreview | undefined,
  configName: string,
  configDir: string
): AccountPointer | undefined {
  if (!preview || typeof preview !== 'object') return undefined;
  const { name, host, channel } = preview;
  if (typeof name !== 'string' || !PREVIEW_NAME_PATTERN.test(name)) return undefined;
  if (typeof host !== 'string' || typeof channel !== 'string') return undefined;
  return {
    accountServer: host,
    updateChannel: channel,
    preview: name,
    tokenFile: previewTokenFile(configName, name, configDir),
  };
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
 * While a preview overlay exists (`rdc preview use`), the preview's pointer is answered instead and
 * the `account` section is left untouched on disk (previewPointer).
 *
 * Returns `{}` on ANY error (missing file, malformed JSON, no account section).
 * No caching: reads are rare and tiny, and cache invalidation after
 * resolveAndSyncServer / `update --channel` writes would be a bug farm.
 */
export function readAccountPointer(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): AccountPointer {
  try {
    const raw = readFileSync(join(configDir, `${configName}.json`), 'utf8');
    const parsed = JSON.parse(raw) as {
      account?: AccountPointer;
      remote?: { apiUrl?: string };
      preview?: RawPreview;
    };
    const overlay = previewPointer(parsed.preview, configName, configDir);
    if (overlay) return overlay;
    // A block that is present but malformed answers nothing, never the real server's pointers the config is not on.
    if (parsed.preview !== undefined) return {};
    const account = { ...(parsed.account ?? {}) };
    account.accountServer ??= parsed.remote?.apiUrl;
    if (account.accountServer === undefined) delete account.accountServer;
    return account;
  } catch {
    return {};
  }
}
