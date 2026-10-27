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
  storageKeyInUseElsewhere,
  storeHandoffCredentials,
} from './config-remote-enable.js';
import { runRelayHandoff, tryOpenBrowser } from './config-remote-relay.js';

/** Default output format when parent program is unavailable */
const DEFAULT_OUTPUT_FORMAT: OutputFormat = 'table';

// ─── Enable Flow ───────────────────────────────────────────────────────── (finalizeEnable / applyHandoff / storeHandoffCredentials live in config-remote-enable.ts; the relay transport lives in config-remote-relay.ts.)

async function enableRelay(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean; configId?: string } = {}
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
  // a disable may not. The local-only unlink is its own command (`--local`,
  // config-remote-unlink.ts), named here only when the server path is closed
  // for good, never for a server that is merely unreachable.
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
    const { closedServerPath } = await import('./config-remote-unlink.js');
    throw closedServerPath(error, configName, remote) ?? error;
  }

  // Write the full config to the local file without the remote pointer. The pull carries no host-local sections, so they come from the decrypted local copy through the one overlay: saving the pull as is dropped state.repos networkIds, renetPath, the master-password verifier and unknown keys, and wrote a master-password config back in plaintext (F3/F4/F18 sibling, PLAN-config-sync-hardening T3).
  // `defaults.language` comes from the store like the rest of `defaults` (operator ruling D3, all synced): a remote config
  // holds no device-only language, so preferring the local copy here only brought back a stale cached value.
  const { overlayDeviceLocal } = await import('../services/config/remote-cache.js');
  await configFileStorage.update(configName, (local) => {
    const restored: RdcConfig = overlayDeviceLocal(fullConfig, local);
    delete restored.remote;
    return restored;
  });

  // Clean up credentials. The slot secret belongs to the (store, user) enrollment, which another local config may
  // share: it goes only when no other config names it (F17 sibling).
  await remoteTokenStorage.delete(configName);
  if (!(await storageKeyInUseElsewhere(remote.storageKeyId, configName))) {
    await secureStorage.delete(remote.storageKeyId);
  }

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

  // Outside the try: a device with no usable secure storage is told so, with the remedy, instead of reading "error".
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();

  try {
    const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
    const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
    const adapter = new RemoteConfigAdapter(remote, configName, remoteTokenStorage, secureStorage);
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

  const { pullOrPurge, writeRemoteCache } = await import('../services/config/remote-cache.js');
  const { config: pulledConfig, version } = await withSpinner(
    t('commands.config.remote.refresh.pulling'),
    () => pullOrPurge(adapter, configName),
    t('commands.config.remote.refresh.pulled')
  );

  await writeRemoteCache(configName, pulledConfig, version);

  outputService.success(t('commands.config.remote.refresh.success', { version: String(version) }));
}

// ─── Versions and Restore (T16) ─────────────────────────────────────────

/** The active config's remote adapter; refuses a config that is not remote. */
async function activeRemoteAdapter() {
  const adapter = await configService.getActiveRemoteAdapter();
  if (!adapter) throw new ValidationError(t('commands.config.remote.refresh.notEnabled'));
  return adapter;
}

async function showVersions(
  configName: string,
  format: OutputFormat,
  explain = false
): Promise<void> {
  const adapter = await activeRemoteAdapter();
  const { listRemoteVersions } = await import('../services/config/remote-restore.js');
  const versions = await listRemoteVersions(adapter);
  if (explain && versions.length > 0) {
    const { explainVersions } = await import('../services/config/push-visibility.js');
    const rows = await explainVersions(adapter, versions);
    // A machine-readable run keeps the raw fields (`changes` null, `unreadable` the reason); the
    // localized placeholders are for the table.
    if (format === 'json') {
      outputService.print(rows, format);
      return;
    }
    outputService.print(
      rows.map(({ unreadable, ...row }) => ({
        ...row,
        changes: unreadable
          ? t('commands.config.remote.versions.explainUnreadable', { reason: unreadable })
          : (row.changes ?? t('commands.config.remote.versions.explainFirst')),
      })),
      format
    );
    return;
  }
  if (versions.length === 0 && format === DEFAULT_OUTPUT_FORMAT) {
    outputService.info(t('commands.config.remote.versions.empty', { config: configName }));
    return;
  }
  outputService.print(versions, format);
}

async function restoreVersion(
  configName: string,
  rawVersion: string,
  opts: { yes?: boolean }
): Promise<void> {
  const { parseVersionArgument, restoreRemoteVersion } = await import(
    '../services/config/remote-restore.js'
  );
  const version = parseVersionArgument(rawVersion);
  const adapter = await activeRemoteAdapter();
  const confirm = async (current: number) =>
    opts.yes === true ||
    askConfirm(
      t('commands.config.remote.restore.confirm', {
        version: String(version),
        config: configName,
        current: String(current),
      }),
      false
    );
  const result = await restoreRemoteVersion(adapter, configName, version, confirm);
  if (!result) {
    outputService.info(t('prompts.cancelled'));
    return;
  }
  outputService.success(
    t('commands.config.remote.restore.success', {
      restored: String(result.restoredFrom),
      config: configName,
      version: String(result.version),
    })
  );
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
/** How long `rotate-cek` waits for the browser wizard, and how often it asks the server. */
const ROTATION_WAIT_MS = 30 * 60 * 1000;
const ROTATION_POLL_MS = 5000;

/**
 * Poll the store's CEK generation until it passes `before`: true once the rotation is done, false when the wait
 * runs out with nothing rotated. Exported for its test.
 */
export async function waitForGeneration(
  read: () => Promise<number | undefined>,
  before: number,
  options: { timeoutMs?: number; intervalMs?: number; sleep?: (ms: number) => Promise<void> } = {}
): Promise<boolean> {
  const timeoutMs = options.timeoutMs ?? ROTATION_WAIT_MS;
  const intervalMs = options.intervalMs ?? ROTATION_POLL_MS;
  const sleep = options.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  for (let waited = 0; waited < timeoutMs; waited += intervalMs) {
    await sleep(intervalMs);
    if (((await read()) ?? 0) > before) return true;
  }
  return false;
}

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

  // THE SERVER SAYS WHEN THE ROTATION IS DONE, not the user. This used to ask "Did the browser report the rotation as complete?", and both wrong answers lied: a yes before the rotation re-linked the old key and printed "now encrypted under the new key"; a no after it printed "nothing changed" to a device whose key was already stale (operator, 2026-09-26).
  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const current = new RemoteConfigAdapter(
    config.remote,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );
  const before = (await current.storeGeneration()) ?? 0;

  const wizardUrl = `${apiUrl}/account/config-storage/rotate-key`;
  outputService.info(t('commands.config.rotateCek.openWizard'));
  outputService.info(`  ${wizardUrl}`);
  outputService.info('');
  await tryOpenBrowser(wizardUrl);

  const rotated = await withSpinner(
    t('commands.config.rotateCek.waiting'),
    () => waitForGeneration(() => current.storeGeneration(), before),
    t('commands.config.rotateCek.detected')
  );
  if (!rotated) {
    throw new ValidationError(t('commands.config.rotateCek.timedOut'));
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

/** The finalize options the `enable` flags carry. */
function enableOptions(options: { force?: boolean; configId?: string }): {
  force: boolean;
  configId?: string;
} {
  return {
    force: Boolean(options.force),
    ...(options.configId ? { configId: options.configId } : {}),
  };
}

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
    .option('--config-id <id>', t('commands.config.remote.enable.optionConfigId'))
    .action(async (options) => {
      try {
        const configName = configService.getEffectiveConfigName();
        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const config = await configFileStorage.load(configName);

        // Before any portal link or password prompt: an enrollment ends by storing this device's slot secret, so a device with nowhere to keep it is refused here and not after the browser ceremony.
        const { getSecureStorage } = await import('../utils/secure-storage.js');
        getSecureStorage();

        // A linked config is refused only while this device can still open it. Once its credentials are gone (the keyring that held the slot secret did not outlive a reboot, the token chain died with no login to renew it, the key was rotated), enable enrolls THIS device again against the same store: `disable` needs those same credentials, so it was never a way out.
        if (hasRemoteConfig(config)) {
          const { enrollmentUsable, reenroll } = await import('./config-remote-reenroll.js');
          if (await enrollmentUsable(config.remote, configName)) {
            throw new ValidationError(
              t('commands.config.remote.enable.alreadyEnabled', { name: configName })
            );
          }
          await reenroll(configName, config.remote, {
            password: Boolean(options.password),
            apiUrl: options.apiUrl,
            configId: options.configId,
          });
          return;
        }

        const apiUrl = options.apiUrl ?? getSubscriptionServerUrl();
        const opts = enableOptions(options);

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
    .option('--local', t('commands.config.remote.disable.optionLocal'))
    .option('-y, --yes', t('options.yes'))
    .action(async (options: { local?: boolean; yes?: boolean }) => {
      try {
        const configName = configService.getEffectiveConfigName();
        if (options.local) {
          const { disableLocal } = await import('./config-remote-unlink.js');
          await disableLocal(configName, { yes: options.yes });
          return;
        }
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

  // remote versions
  remote
    .command('versions')
    .description(t('commands.config.remote.versions.description'))
    .option('--explain', t('commands.config.remote.versions.optionExplain'))
    .action(async (options: { explain?: boolean }) => {
      try {
        const configName = configService.getEffectiveConfigName();
        const program = configCommand.parent;
        const format = (program?.opts().output ?? DEFAULT_OUTPUT_FORMAT) as OutputFormat;
        await showVersions(configName, format, options.explain === true);
      } catch (error) {
        handleError(error);
      }
    });

  // remote restore
  remote
    .command('restore')
    .description(t('commands.config.remote.restore.description'))
    .argument('<version>', t('commands.config.remote.restore.argVersion'))
    .option('-y, --yes', t('options.yes'))
    .action(async (version: string, options: { yes?: boolean }) => {
      try {
        const configName = configService.getEffectiveConfigName();
        await restoreVersion(configName, version, options);
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
