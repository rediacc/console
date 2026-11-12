import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import { resolveChannel } from '../services/update/updater.js';
import { handleError } from '../utils/errors.js';
import { VERSION } from '../version.js';

const LICENSE_STATUS_PATH = '/account/api/v1/licenses/status';

/** How the active licence was determined: a plan from the account server, no login at all, or a login whose server answered without a plan (unknown) or could not be asked (unreachable). */
type LicenseKind = 'account' | 'anonymous' | 'unknown' | 'unreachable';

export interface VersionInfo {
  version: string;
  platform: string;
  arch: string;
  channel: string;
  license: { kind: LicenseKind; tier?: string };
}

/** The active licence: the tier from the account server when logged in, anonymous (FREE per repository) without a login, unknown when the server answered without a plan, unreachable when it cannot answer. */
async function activeLicense(): Promise<VersionInfo['license']> {
  if (getSubscriptionTokenState().kind !== 'ready') return { kind: 'anonymous' };
  try {
    const status = await accountServerFetch<{ planCode?: string }>(LICENSE_STATUS_PATH);
    return status.planCode ? { kind: 'account', tier: status.planCode } : { kind: 'unknown' };
  } catch (error) {
    // A server that ANSWERED with an error status (an expired login's 401, a 500) is not unreachable: surface its refusal instead of labelling it a network failure.
    if (typeof (error as { status?: unknown } | null)?.status === 'number') throw error;
    return { kind: 'unreachable' };
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
  if (license.kind === 'anonymous') return t('commands.version.license.anonymous');
  return license.kind === 'unreachable'
    ? t('commands.version.license.unreachable')
    : t('commands.version.license.unknown');
}

function renderVersion(info: VersionInfo): string {
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
