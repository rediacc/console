import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getSubscriptionServerUrl } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat, RdcConfig, RemoteConfig } from '../types/index.js';
import { hasRemoteConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';
import {
  applyHandoff,
  checkEnablePrerequisites,
  requireLoginToken,
  storeHandoffCredentials,
} from './config-remote-enable.js';
import { runRelayHandoff, tryOpenBrowser } from './config-remote-relay.js';

/** Default output format when parent program is unavailable */
const DEFAULT_OUTPUT_FORMAT: OutputFormat = 'table';

// ─── Enable Flow ───────────────────────────────────────────────────────── (finalizeEnable / applyHandoff / storeHandoffCredentials live in config-remote-enable.ts; the relay transport lives in config-remote-relay.ts.)

async function enableRelay(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  // Before any portal link: no login token, or a missing 2FA, refuses here instead of mid-flow in the browser.
  const { token, email } = await checkEnablePrerequisites(apiUrl);
  const payload = await runRelayHandoff(apiUrl, token, email);
  await applyHandoff(payload, configName, opts);

  outputService.success(
    t('commands.config.remote.enable.success', { name: configName, apiUrl: payload.apiUrl })
  );
}

// ─── Disable Flow ────────────────────────────────────────────────────────

async function disableRemote(configName: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const localConfig = await configFileStorage.load(configName);

  if (!hasRemoteConfig(localConfig)) {
    throw new ValidationError(t('commands.config.remote.disable.notEnabled'));
  }

  const remote = localConfig.remote;

  // Pull latest to get full config
  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();

  const adapter = new RemoteConfigAdapter(remote, configName, remoteTokenStorage, secureStorage);

  // Disable is deliberately SERVER-ONLY: restoring from the offline cache
  // could silently lose another device's newer writes. Reads may cache-serve;
  // a disable may not.
  let fullConfig: RdcConfig;
  try {
    ({ config: fullConfig } = await adapter.pull());
  } catch (error) {
    const { RemoteUnreachableError } = await import('../adapters/remote-config-adapter.js');
    if (error instanceof RemoteUnreachableError) {
      throw new ValidationError(
        t('commands.config.remote.disable.serverRequired', { server: remote.apiUrl })
      );
    }
    throw error;
  }

  // Write full decrypted config to local file, removing remote pointer
  const restored: RdcConfig = {
    ...fullConfig,
    defaults: {
      ...(fullConfig.defaults ?? {}),
      language: localConfig.defaults?.language ?? fullConfig.defaults?.language,
    },
  };
  delete restored.remote;
  await configFileStorage.save(restored, configName);

  // Clean up credentials
  await remoteTokenStorage.delete(configName);
  await secureStorage.delete(remote.storageKeyId);

  outputService.success(t('commands.config.remote.disable.success', { name: configName }));
}

// ─── Status Flow ─────────────────────────────────────────────────────────

async function showStatus(configName: string, format: OutputFormat): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const config = await configFileStorage.load(configName);

  if (!hasRemoteConfig(config)) {
    outputService.print({ config: configName, status: 'disconnected' }, format);
    return;
  }

  const remote = config.remote;
  let connected = false;

  try {
    const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
    const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
    const { getSecureStorage } = await import('../utils/secure-storage.js');
    const adapter = new RemoteConfigAdapter(
      remote,
      configName,
      remoteTokenStorage,
      getSecureStorage()
    );
    connected = await adapter.testConnection();
  } catch {
    // Connection test failed
  }

  outputService.print(
    {
      config: configName,
      status: connected ? 'connected' : 'error',
      apiUrl: remote.apiUrl,
      storeId: remote.storeId,
      configId: remote.configId,
      teamId: remote.teamId ?? '-',
      cachedVersion: remote.cachedVersion ?? '-',
      cachedAt: remote.cachedAt ?? '-',
    },
    format
  );
}

// ─── Refresh Flow ────────────────────────────────────────────────────────

async function refreshRemote(configName: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const config = await configFileStorage.load(configName);

  if (!hasRemoteConfig(config)) {
    throw new ValidationError(t('commands.config.remote.refresh.notEnabled'));
  }

  // Clear cached remote config in configService
  configService.setRuntimeConfig(configService.getCurrentName());

  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');

  const adapter = new RemoteConfigAdapter(
    config.remote,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );

  const { config: pulledConfig, version } = await withSpinner(
    t('commands.config.remote.refresh.pulling'),
    () => adapter.pull(),
    t('commands.config.remote.refresh.pulled')
  );

  const { writeRemoteCache } = await import('../services/config/remote-cache.js');
  await writeRemoteCache(configName, pulledConfig, version);

  outputService.success(t('commands.config.remote.refresh.success', { version: String(version) }));
}

// ─── CEK Rotation ────────────────────────────────────────────────────────

/**
 * Rotate the org-wide config encryption key.
 *
 * The rotation itself CANNOT run headlessly. It re-encrypts every config in the
 * organization, so the server gates it behind a 2FA-backed, freshly
 * re-authenticated (elevated) portal session, and the CLI holds config tokens,
 * never a portal session. So this command drives the browser, exactly as
 * `config remote enable` already does for the other session-gated config steps.
 *
 * Two browser trips, and both are load-bearing:
 *   1. The wizard, which performs the rotation.
 *   2. The credential handoff over the server relay (config-remote-relay.ts),
 *      because the rotation deliberately revokes this device's wrapped CEK.
 *      Without step 2 the local config still holds the OLD key and every
 *      subsequent pull would fail to decrypt.
 */
export async function rotateCek(configName: string, apiUrl: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const config = await configFileStorage.load(configName);

  if (!hasRemoteConfig(config)) {
    throw new ValidationError(t('commands.config.rotateCek.notEnabled', { name: configName }));
  }
  // The re-link in step 2 needs the login token; refuse before the rotation, not after it revoked this device.
  const loginToken = requireLoginToken(apiUrl);

  outputService.warn(t('commands.config.rotateCek.warning'));
  const confirmed = await askConfirm(t('commands.config.rotateCek.confirm'), false);
  if (!confirmed) {
    outputService.info(t('commands.config.rotateCek.cancelled'));
    return;
  }

  const wizardUrl = `${apiUrl}/account/config-storage/rotate-key`;
  outputService.info(t('commands.config.rotateCek.openWizard'));
  outputService.info(`  ${wizardUrl}`);
  outputService.info('');
  await tryOpenBrowser(wizardUrl);

  const proceed = await askConfirm(t('commands.config.rotateCek.confirmDone'), false);
  if (!proceed) {
    outputService.info(t('commands.config.rotateCek.cancelled'));
    return;
  }

  // The rotation revoked this device's key. Re-acquire it over the same relay `config remote enable` uses; the pointer file is already correct, so only the stored token + wrapped CEK are replaced.
  outputService.info(t('commands.config.rotateCek.resync'));
  const payload = await runRelayHandoff(apiUrl, loginToken, undefined);
  const stored = await storeHandoffCredentials(payload, configName);
  // The pointer file is already correct; a re-handoff may omit configId, so fall back to the enrolled pointer's.
  const remote: RemoteConfig = {
    ...stored,
    configId: stored.configId ?? config.remote.configId,
  };

  // Prove the new key actually decrypts the freshly rotated blob before declaring success, a silent stale key is the whole failure mode here.
  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const adapter = new RemoteConfigAdapter(
    remote,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );
  const { config: verifiedConfig, version } = await withSpinner(
    t('commands.config.rotateCek.verifying'),
    () => adapter.pull(),
    t('commands.config.rotateCek.verified')
  );

  // The rotation rewrote every blob server-side; the offline cache must follow, or a later offline read would serve pre-rotation content.
  const { writeRemoteCache } = await import('../services/config/remote-cache.js');
  await writeRemoteCache(configName, verifiedConfig, version);

  outputService.success(
    t('commands.config.rotateCek.success', { name: configName, version: String(version) })
  );
}

// ─── Command Registration ────────────────────────────────────────────────

export function registerRemoteCommands(configCommand: Command): void {
  const remote = configCommand
    .command('remote')
    .description(t('commands.config.remote.description'));

  // remote enable
  remote
    .command('enable')
    .description(t('commands.config.remote.enable.description'))
    .option('--password', t('commands.config.remote.enable.optionPassword'))
    .option('--api-url <url>', t('commands.config.remote.enable.optionApiUrl'))
    .option('--force', t('commands.config.remote.enable.optionForce'))
    .action(async (options) => {
      try {
        const configName = configService.getEffectiveConfigName();
        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const config = await configFileStorage.load(configName);

        if (hasRemoteConfig(config)) {
          throw new ValidationError(
            t('commands.config.remote.enable.alreadyEnabled', { name: configName })
          );
        }

        const apiUrl = options.apiUrl ?? getSubscriptionServerUrl();
        const opts = { force: Boolean(options.force) };

        if (options.password) {
          const { enablePassword } = await import('./config-remote-password.js');
          await enablePassword(apiUrl, configName, opts);
        } else {
          await enableRelay(apiUrl, configName, opts);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // remote disable
  remote
    .command('disable')
    .description(t('commands.config.remote.disable.description'))
    .action(async () => {
      try {
        const configName = configService.getEffectiveConfigName();
        await disableRemote(configName);
      } catch (error) {
        handleError(error);
      }
    });

  // remote status
  remote
    .command('status')
    .description(t('commands.config.remote.status.description'))
    .action(async () => {
      try {
        const configName = configService.getEffectiveConfigName();
        const program = configCommand.parent;
        const format = (program?.opts().output ?? DEFAULT_OUTPUT_FORMAT) as OutputFormat;
        await showStatus(configName, format);
      } catch (error) {
        handleError(error);
      }
    });

  // remote refresh
  remote
    .command('refresh')
    .description(t('commands.config.remote.refresh.description'))
    .action(async () => {
      try {
        const configName = configService.getEffectiveConfigName();
        await refreshRemote(configName);
      } catch (error) {
        handleError(error);
      }
    });
}
