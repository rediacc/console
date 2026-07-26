import { join } from 'node:path';
import { DEFAULTS, SUBSCRIPTION_DEFAULTS, UPDATE_DEFAULTS } from '@rediacc/shared/config';
import { getConfigDir } from '@rediacc/shared/paths';
import type { Command } from 'commander';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import { readAccountPointer } from '../../services/account/account-pointer.js';
import {
  getSubscriptionTokenFile,
  getSubscriptionTokenState,
} from '../../services/account/subscription-auth.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError } from '../../utils/errors.js';

interface ResolvedSource {
  value: string;
  source: string;
}

/** Resolve a value across env > config > default, labeling which tier won. */
function resolveWithSource(
  envValue: string | undefined,
  envLabel: string,
  configValue: string | undefined,
  defaultValue: string
): ResolvedSource {
  if (envValue) return { value: envValue, source: envLabel };
  if (configValue) return { value: configValue, source: 'config' };
  return { value: defaultValue, source: 'default' };
}

/** Register `config current`: report the active config and its resolved universe. */
export function registerCurrentCommand(parent: Command, program: Command): void {
  parent
    .command('current')
    .description(t('commands.config.current.description'))
    .action(async () => {
      try {
        const format = program.opts().output as OutputFormat;
        const name = configService.getCurrentName();
        const filePath = join(getConfigDir(), `${name}.json`);
        const fileExists = await configFileStorage.exists(name);
        const pointer = readAccountPointer();

        // accountServer / updateChannel with their winning source labeled.
        const accountServer = resolveWithSource(
          process.env.REDIACC_ACCOUNT_SERVER,
          'env REDIACC_ACCOUNT_SERVER',
          pointer.accountServer,
          SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL
        );
        const updateChannel = resolveWithSource(
          process.env.REDIACC_UPDATE_CHANNEL,
          'env REDIACC_UPDATE_CHANNEL',
          pointer.updateChannel,
          UPDATE_DEFAULTS.CHANNEL
        );

        const tokenState = getSubscriptionTokenState();
        const cfg = fileExists ? await configService.getCurrent() : null;

        // A config with no remote pointer is the local adapter (CLAUDE.md: local
        // is the only adapter). Plain assignment, not `?? 'local'`, keeps both the
        // nullish-default and prefer-nullish lint rules satisfied.
        let remoteStore = 'local';
        if (cfg?.remote?.storeId) remoteStore = cfg.remote.storeId;

        const display: Record<string, unknown> = {
          name,
          filePath,
          fileExists,
          accountServer: accountServer.value,
          accountServerSource: accountServer.source,
          updateChannel: updateChannel.value,
          updateChannelSource: updateChannel.source,
          releasesUrl: pointer.releasesUrl ?? null,
          e2ePublicKey: pointer.e2ePublicKey ? 'present' : 'absent',
          tokenFile: getSubscriptionTokenFile(name),
          tokenState: tokenState.kind,
          org: tokenState.kind === 'ready' ? (tokenState.token.orgName ?? null) : null,
          team: tokenState.kind === 'ready' ? (tokenState.token.teamName ?? null) : null,
          remoteStore,
          encryption: cfg?.encryption?.mode ?? DEFAULTS.CONTEXT.CONFIG_KIND,
        };

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });
}
