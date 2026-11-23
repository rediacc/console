/**
 * The preview's build, checked against two origins (PLAN-preview-signer.md D6). The deploy writes the
 * channel manifest's version and per-platform sha256 into the preview Worker (`previewBuild` of
 * server-info), and the R2 manifest carries them again beside the binary URL. `rdc preview use` installs
 * a binary only when both agree, so a tampered bucket object or a stale channel is caught before anything
 * runs.
 */
import { type PreviewBuild, PreviewBuildSchema } from '@rediacc/shared/config-schema';
import { t } from '../../i18n/index.js';
import type { UpdateManifest } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import type { PlatformKey } from '../../utils/platform.js';

export type { PreviewBuild };

/** The binary `use` installs: its URL from the R2 manifest and the sha256 both origins named. */
export interface PreviewBinary {
  version: string;
  sha256: string;
  url: string;
}

/** The `previewBuild` of a server-info body; a server that sends none, or a malformed one, is not a preview this CLI can switch to. */
export function parsePreviewBuild(raw: unknown, name: string): PreviewBuild {
  if (raw === undefined || raw === null) {
    throw new ValidationError(t('errors.preview.noBuild', { name }));
  }
  const parsed = PreviewBuildSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ValidationError(
      t('errors.preview.badBuild', { name, detail: parsed.error.issues[0]?.message ?? '' })
    );
  }
  return parsed.data;
}

/**
 * The binary for `platformKey`, or a refusal. Nothing here touches a file: every check runs before the
 * first byte is downloaded, so a mismatch leaves the machine as it was.
 */
export function selectPreviewBinary(
  manifest: UpdateManifest,
  build: PreviewBuild,
  platformKey: PlatformKey,
  name: string
): PreviewBinary {
  const entry = manifest.binaries[platformKey];
  const expected = build.sha256[platformKey];
  if (!entry || !expected) {
    throw new ValidationError(t('errors.preview.noBinary', { name, platform: platformKey }));
  }
  if (manifest.version !== build.version) {
    throw new ValidationError(
      t('errors.preview.versionMismatch', {
        name,
        manifest: manifest.version,
        server: build.version,
      })
    );
  }
  if (entry.sha256 !== expected) {
    throw new ValidationError(t('errors.preview.hashMismatch', { name, platform: platformKey }));
  }
  return { version: build.version, sha256: expected, url: entry.url };
}
