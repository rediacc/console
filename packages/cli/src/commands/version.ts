import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import { resolveChannel } from '../services/update/updater.js';
import { handleError } from '../utils/errors.js';
import { VERSION } from '../version.js';

const LICENSE_STATUS_PATH = '/account/api/v1/licenses/status';

/** How the active licence was determined: a plan from the account server, no login at all, or a login whose server could not be asked. */
export type LicenseKind = 'account' | 'anonymous' | 'unknown';

export interface VersionInfo {
  version: string;
  platform: string;
  arch: string;
  channel: string;
  license: { kind: LicenseKind; tier?: string };
}

/** The active licence: the tier from the account server when logged in, anonymous (FREE per repository) without a login, unknown when the server cannot answer. */
async function activeLicense(): Promise<VersionInfo['license']> {
  if (getSubscriptionTokenState().kind !== 'ready') return { kind: 'anonymous' };
  try {
    const status = await accountServerFetch<{ planCode?: string }>(LICENSE_STATUS_PATH);
    return status.planCode ? { kind: 'account', tier: status.planCode } : { kind: 'unknown' };
  } catch {
    return { kind: 'unknown' };
  }
}

export async function collectVersionInfo(): Promise<VersionInfo> {
  return {
    version: VERSION,
    platform: process.platform,
    arch: process.arch,
    channel: resolveChannel(),
    license: await activeLicense(),
  };
}

function licenseText(license: VersionInfo['license']): string {
  if (license.kind === 'account') return license.tier ?? '';
  return license.kind === 'anonymous'
    ? t('commands.version.license.anonymous')
    : t('commands.version.license.unknown');
}

export function renderVersion(info: VersionInfo): string {
  return [
    `rdc ${info.version}`,
    t('commands.version.platform', { platform: info.platform, arch: info.arch }),
    t('commands.version.channel', { channel: info.channel }),
    t('commands.version.license.label', { license: licenseText(info.license) }),
  ].join('\n');
}

export function registerVersionCommand(program: Command): void {
  program
    .command('version')
    .summary(t('commands.version.descriptionShort'))
    .description(t('commands.version.description'))
    .option('--json', t('options.json'))
    .action(async (options: { json?: boolean }) => {
      try {
        const info = await collectVersionInfo();
        const json = options.json === true || program.opts().output === 'json';
        outputService.print(json ? JSON.stringify(info, null, 2) : renderVersion(info));
      } catch (error) {
        handleError(error);
      }
    });
}
