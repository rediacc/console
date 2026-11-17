/**
 * `rdc server bundle --with-cli <platform,...>`: the SEA binaries of this CLI's own version, for the
 * machines an air-gapped install reaches that have no `rdc`. Each one is fetched from the release
 * channel (`<base>/v<version>/rdc-<platform>`, checksum beside it at `<url>.sha256`, the layout
 * install.sh reads), checked against that checksum, and written to `cli/<platform>/rdc` (`rdc.exe` on Windows).
 * The checksum comes from the same release host as the binary, so the check catches corruption in transit, not a binary the host itself substituted.
 */

import { join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { isDevBuild, type PlatformKey } from '../../../utils/platform.js';
import { VERSION } from '../../../version.js';
import { outputService } from '../../core/output.js';
import { ServerError } from '../box.js';
import type { ServerDeps } from '../types.js';
import type { ManifestCli } from './manifest.js';

const CLI_PLATFORMS: readonly PlatformKey[] = [
  'linux-x64',
  'linux-arm64',
  'mac-x64',
  'mac-arm64',
  'win-x64',
  'win-arm64',
] as const;

/** Split `--with-cli`'s value; an empty list, an unknown name or a dev build is refused before any download. */
export function parseCliPlatforms(value: string): PlatformKey[] {
  if (isDevBuild()) throw new ServerError(t('commands.server.bundle.errors.cliDevBuild'));
  const names = value
    .split(',')
    .map((n) => n.trim())
    .filter(Boolean);
  if (names.length === 0) {
    throw new ServerError(
      t('commands.server.bundle.errors.cliUnknownPlatform', {
        platform: value,
        known: CLI_PLATFORMS.join(', '),
      })
    );
  }
  for (const name of names) {
    if (!CLI_PLATFORMS.includes(name as PlatformKey)) {
      throw new ServerError(
        t('commands.server.bundle.errors.cliUnknownPlatform', {
          platform: name,
          known: CLI_PLATFORMS.join(', '),
        })
      );
    }
  }
  return [...new Set(names as PlatformKey[])];
}

/** The first field of a `.sha256` file: `<hash>` or `<hash>  <name>`. */
function checksumOf(text: string, url: string): string {
  const first = text.trim().split(/\s+/)[0]?.toLowerCase() ?? '';
  if (!/^[0-9a-f]{64}$/.test(first)) {
    throw new ServerError(t('commands.server.bundle.errors.cliChecksumFile', { url }));
  }
  return first;
}

async function fetchOne(
  deps: ServerDeps,
  out: string,
  platform: PlatformKey
): Promise<ManifestCli> {
  const windows = platform.startsWith('win-');
  const url = `${deps.release.baseUrl()}/v${VERSION}/rdc-${platform}${windows ? '.exe' : ''}`;
  const file = `cli/${platform}/${windows ? 'rdc.exe' : 'rdc'}`;
  outputService.info(t('commands.server.bundle.downloadingCli', { platform, version: VERSION }));
  const expected = checksumOf(await deps.release.fetchText(`${url}.sha256`), `${url}.sha256`);
  await deps.makeDir(join(out, 'cli', platform));
  await deps.release.download(url, join(out, file));
  const actual = await deps.sha256File(join(out, file));
  if (actual !== expected) {
    throw new ServerError(
      t('commands.server.bundle.errors.cliSha256Mismatch', { platform, url, expected, actual })
    );
  }
  return { platform, file, sha256: actual };
}

export async function fetchCliBinaries(
  deps: ServerDeps,
  out: string,
  platforms: PlatformKey[]
): Promise<ManifestCli[]> {
  const entries: ManifestCli[] = [];
  for (const platform of platforms) entries.push(await fetchOne(deps, out, platform));
  return entries;
}
