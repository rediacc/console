/**
 * The preview overlay of a config (PLAN-preview-signer.md D8).
 *
 * `rdc preview use <name>` adds a `preview` block beside the config's `account` section, and
 * `readAccountPointer` answers the preview's host, channel and token file while the block exists.
 * Every write here touches `preview` alone, so the `account` section stays byte-identical, and
 * removing the block puts the real server, key and token back in force by construction.
 */

import { readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_RELEASES_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import {
  PREVIEW_NAME_PATTERN,
  type PreviewOverlay,
  PreviewOverlaySchema,
  type RdcConfig,
} from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { parseJsonText } from '../../utils/json-text.js';
import { previewTokenFile } from '../account/account-pointer.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { updateConfigAtPointer } from '../config/synced-write.js';

export type { PreviewOverlay };
export type PreviewTouchedServer = NonNullable<PreviewOverlay['touched']>[string];

/** The preview's public host: the name is the Worker name on the shared workers.dev certificate (D5). */
export function previewHostFor(name: string): string {
  return `https://${name}.rediacc.workers.dev`;
}

function assertPreviewName(name: string): void {
  if (!PREVIEW_NAME_PATTERN.test(name)) {
    throw new ValidationError(t('errors.preview.invalidName', { name }));
  }
}

/**
 * The preview block of a config, read synchronously from the file; `undefined` when the config has
 * none, the file is missing, or the block is malformed (the strict config parse refuses that one).
 */
export function readPreviewOverlay(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): PreviewOverlay | undefined {
  try {
    const parsed = parseJsonText(readFileSync(join(configDir, `${configName}.json`), 'utf8')) as {
      preview?: unknown;
    };
    if (parsed.preview === undefined) return undefined;
    const result = PreviewOverlaySchema.safeParse(parsed.preview);
    return result.success ? result.data : undefined;
  } catch {
    return undefined;
  }
}

/**
 * The server the config names in its `account` section, which a preview overlay hides from the account
 * pointer: the one `leave` returns to, read straight from the file. The default origin when the section names none.
 */
export function readRealAccountServer(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): string {
  try {
    const parsed = parseJsonText(readFileSync(join(configDir, `${configName}.json`), 'utf8')) as {
      account?: { accountServer?: unknown };
    };
    const server = parsed.account?.accountServer;
    return typeof server === 'string' && server !== '' ? server : WK_ACCOUNT_DEFAULT_ORIGIN;
  } catch {
    return WK_ACCOUNT_DEFAULT_ORIGIN;
  }
}

/**
 * The releases base (`.../cli`) of the config's real account section: the on-prem `releasesUrl` it names, else
 * the public origin. A preview overlay hides the section from the account pointer, so the way back reads it here.
 */
export function readRealReleasesBase(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): string {
  try {
    const parsed = parseJsonText(readFileSync(join(configDir, `${configName}.json`), 'utf8')) as {
      account?: { releasesUrl?: unknown };
    };
    const url = parsed.account?.releasesUrl;
    if (typeof url === 'string' && url !== '') return `${url.replace(/\/+$/, '')}/cli`;
  } catch {
    // an unreadable config names no on-prem releases server: the public one answers
  }
  return `${WK_RELEASES_ORIGIN}/cli`;
}

function withPreview(config: RdcConfig, preview: PreviewOverlay | undefined): RdcConfig {
  const rest: RdcConfig = { ...config };
  delete rest.preview;
  return preview === undefined ? rest : { ...rest, preview };
}

/**
 * Add the preview block. Refuses a malformed block and a config already on a preview; the `account`
 * section is not read or written.
 */
export async function enterPreview(
  overlay: PreviewOverlay,
  configName = getEffectiveConfigName()
): Promise<PreviewOverlay> {
  assertPreviewName(overlay.name);
  // The pointer answers this host beside the preview token file, so the name fixes it (D5), whatever host the caller passed.
  const preview = PreviewOverlaySchema.parse({ ...overlay, host: previewHostFor(overlay.name) });
  await updateConfigAtPointer(configName, '/preview', (config) => {
    if (config.preview) {
      throw new ValidationError(t('errors.preview.alreadyActive', { name: config.preview.name }));
    }
    return withPreview(config, preview);
  });
  return preview;
}

/**
 * Record the first renet replacement on `machine` (D9). A machine already listed keeps its first
 * record, which names the pre-preview slot; a later touch adds nothing. Returns whether it was added.
 */
export async function recordPreviewTouch(
  machine: string,
  entry: PreviewTouchedServer,
  configName = getEffectiveConfigName()
): Promise<boolean> {
  let added = false;
  await updateConfigAtPointer(configName, '/preview', (config) => {
    const preview = config.preview;
    if (!preview || preview.touched?.[machine]) return config;
    added = true;
    return withPreview(config, {
      ...preview,
      touched: { ...(preview.touched ?? {}), [machine]: entry },
    });
  });
  return added;
}

/** Drop `machine` from the touched list once its renet is switched back (D9). */
export async function clearPreviewTouch(
  machine: string,
  configName = getEffectiveConfigName()
): Promise<void> {
  await updateConfigAtPointer(configName, '/preview', (config) => {
    const preview = config.preview;
    if (!preview?.touched?.[machine]) return config;
    const touched = { ...preview.touched };
    delete touched[machine];
    return withPreview(config, {
      ...preview,
      touched: Object.keys(touched).length > 0 ? touched : undefined,
    });
  });
}

/**
 * Remove the preview block and the preview's token file. Refuses while any touched server still runs
 * the preview renet: the overlay is the only record of the slot to switch back to (D9). Returns the
 * removed block, or `undefined` when the config was not on a preview.
 */
export async function leavePreview(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): Promise<PreviewOverlay | undefined> {
  let removed: PreviewOverlay | undefined;
  await updateConfigAtPointer(configName, '/preview', (config) => {
    const preview = config.preview;
    if (!preview) return config;
    const pending = Object.keys(preview.touched ?? {});
    if (pending.length > 0) {
      throw new ValidationError(
        t('errors.preview.serversPending', {
          name: preview.name,
          count: pending.length,
          machines: pending.join(', '),
        })
      );
    }
    // The token file goes before the block does: a failed delete leaves the overlay, so a retry still finds the name.
    rmSync(previewTokenFile(configName, preview.name, configDir), { force: true });
    removed = preview;
    return withPreview(config, undefined);
  });
  return removed;
}
