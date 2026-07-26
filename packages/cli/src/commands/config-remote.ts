import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import type { CekHandoffBlob } from '@rediacc/shared/config-crypto';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { getSubscriptionServerUrl } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat, RdcConfig, RemoteConfig } from '../types/index.js';
import { hasRemoteConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';
import { applyHandoff, storeHandoffCredentials } from './config-remote-enable.js';
import {
  decryptHandoff,
  exportPublicKeyBase64,
  generateX25519KeyPair,
} from './config-remote-handoff.js';

/** Default output format when parent program is unavailable */
const DEFAULT_OUTPUT_FORMAT: OutputFormat = 'table';

// ─── Browser Open ────────────────────────────────────────────────────────

async function tryOpenBrowser(url: string): Promise<void> {
  try {
    const { execFile } = await import('node:child_process');
    const cmd = process.platform === 'darwin' ? 'open' : 'xdg-open';
    execFile(cmd, [url]);
  } catch {
    // Browser open is best-effort
  }
}

// ─── Localhost Callback Server ───────────────────────────────────────────

function startCallbackServer(): Promise<{
  port: number;
  waitForPayload: () => Promise<CekHandoffBlob>;
  close: () => void;
}> {
  return new Promise((resolve, reject) => {
    let payloadResolve: (value: CekHandoffBlob) => void;
    let payloadReject: (reason: Error) => void;
    const payloadPromise = new Promise<CekHandoffBlob>((res, rej) => {
      payloadResolve = res;
      payloadReject = rej;
    });

    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      // CORS preflight
      if (req.method === 'OPTIONS') {
        res.writeHead(204, {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        });
        res.end();
        return;
      }

      if (req.method !== 'POST') {
        res.writeHead(405);
        res.end();
        return;
      }

      const chunks: Buffer[] = [];
      req.on('data', (chunk: Buffer) => chunks.push(chunk));
      req.on('end', () => {
        try {
          const body = JSON.parse(Buffer.concat(chunks).toString('utf-8')) as CekHandoffBlob;
          res.writeHead(200, {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json',
          });
          res.end(JSON.stringify({ ok: true }));
          payloadResolve(body);
        } catch (error) {
          res.writeHead(400);
          res.end();
          payloadReject(error instanceof Error ? error : new Error('Invalid payload'));
        }
      });
    });

    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      if (!addr || typeof addr === 'string') {
        reject(new Error('Failed to bind callback server'));
        return;
      }
      resolve({
        port: addr.port,
        waitForPayload: () => payloadPromise,
        close: () => server.close(),
      });
    });

    server.on('error', reject);
  });
}

// ─── Enable Flow ─────────────────────────────────────────────────────────
// (finalizeEnable / applyHandoff / storeHandoffCredentials live in
// config-remote-enable.ts; this file keeps the transports.)

async function enableBrowser(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  const keyPair = await generateX25519KeyPair();
  const pubBase64 = await exportPublicKeyBase64(keyPair.publicKey);

  const { port, waitForPayload, close } = await startCallbackServer();

  const callbackUrl = `http://localhost:${port}`;
  // Portal route: private/account/web/src/pages/ConfigRemote.tsx, registered as
  // /account/config-remote in web/src/router.tsx. Renaming that route strands
  // this URL (and its two siblings below) — change them together.
  const browserUrl = `${apiUrl}/account/config-remote?callback=${encodeURIComponent(callbackUrl)}&key=${encodeURIComponent(pubBase64)}`;

  outputService.info(t('commands.config.remote.enable.openBrowser'));
  outputService.info(`  ${browserUrl}`);
  outputService.info('');

  await tryOpenBrowser(browserUrl);

  try {
    const encryptedBlob = await withSpinner(
      t('commands.config.remote.enable.waiting'),
      () => waitForPayload(),
      t('commands.config.remote.enable.received')
    );

    const payload = await decryptHandoff(encryptedBlob, keyPair.privateKey);
    await applyHandoff(payload, configName, opts);

    outputService.success(
      t('commands.config.remote.enable.success', { name: configName, apiUrl: payload.apiUrl })
    );
  } finally {
    close();
  }
}

async function pollOnce(deviceCode: string, apiUrl: string): Promise<CekHandoffBlob | null> {
  try {
    const result = await accountServerFetch<{
      status: string;
      configHandoff?: CekHandoffBlob;
    }>(`/account/api/v1/device-codes/${deviceCode}`, {
      noAuth: true,
      serverUrl: apiUrl,
    });

    if (result.status === 'complete' && result.configHandoff) {
      return result.configHandoff;
    }
    if (result.status === 'expired') {
      throw new ValidationError(t('commands.config.remote.enable.expired'));
    }
  } catch (error) {
    if (error instanceof ValidationError) throw error;
    // Polling errors are expected while pending
  }
  return null;
}

async function pollForDeviceCode(
  deviceCode: string,
  apiUrl: string,
  pollInterval: number,
  maxAttempts: number
): Promise<CekHandoffBlob> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));
    const blob = await pollOnce(deviceCode, apiUrl);
    if (blob) return blob;
  }

  throw new ValidationError(t('commands.config.remote.enable.expired'));
}

async function enableHeadless(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  const keyPair = await generateX25519KeyPair();
  const pubBase64 = await exportPublicKeyBase64(keyPair.publicKey);

  const initResult = await accountServerFetch<{
    deviceCode: string;
    userCode: string;
    verificationUrl: string;
    interval: number;
    expiresIn: number;
  }>('/account/api/v1/device-codes', {
    method: 'POST',
    noAuth: true,
    serverUrl: apiUrl,
  });

  const { deviceCode, userCode, interval, expiresIn } = initResult;

  // Portal route: /account/config-remote (ConfigRemote.tsx) — the device-code
  // leg of the same page enableBrowser drives; see the comment there.
  const remoteUrl = `${apiUrl}/account/config-remote?code=${encodeURIComponent(userCode)}&key=${encodeURIComponent(pubBase64)}`;

  outputService.info(t('commands.config.remote.enable.openBrowser'));
  outputService.info(`  ${remoteUrl}`);
  outputService.info('');

  await tryOpenBrowser(remoteUrl);
  outputService.info(t('commands.config.remote.enable.polling'));

  const pollInterval = interval * 1000;
  const maxAttempts = Math.ceil(expiresIn / interval);

  const encryptedBlob = await pollForDeviceCode(deviceCode, apiUrl, pollInterval, maxAttempts);

  const payload = await decryptHandoff(encryptedBlob, keyPair.privateKey);
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
 * re-authenticated (elevated) portal session — and the CLI holds config tokens,
 * never a portal session. So this command drives the browser, exactly as
 * `config remote enable` already does for the other session-gated config steps.
 *
 * Two browser trips, and both are load-bearing:
 *   1. The wizard, which performs the rotation.
 *   2. The credential handoff, because the rotation deliberately revokes this
 *      device's wrapped CEK. Without step 2 the local config still holds the OLD
 *      key and every subsequent pull would fail to decrypt.
 */
export async function rotateCek(configName: string, apiUrl: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const config = await configFileStorage.load(configName);

  if (!hasRemoteConfig(config)) {
    throw new ValidationError(t('commands.config.rotateCek.notEnabled', { name: configName }));
  }

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

  // The rotation revoked this device's key. Re-acquire it over the same X25519
  // handoff `config remote enable` uses; the pointer file is already correct, so
  // only the stored token + wrapped CEK are replaced.
  const keyPair = await generateX25519KeyPair();
  const pubBase64 = await exportPublicKeyBase64(keyPair.publicKey);
  const { port, waitForPayload, close } = await startCallbackServer();

  const callbackUrl = `http://localhost:${port}`;
  // Portal route: /account/config-remote (ConfigRemote.tsx) — the existing-store
  // re-handoff leg; see the comment in enableBrowser.
  const handoffUrl = `${apiUrl}/account/config-remote?callback=${encodeURIComponent(callbackUrl)}&key=${encodeURIComponent(pubBase64)}`;

  outputService.info(t('commands.config.rotateCek.resync'));
  outputService.info(`  ${handoffUrl}`);
  outputService.info('');
  await tryOpenBrowser(handoffUrl);

  try {
    const encryptedBlob = await withSpinner(
      t('commands.config.rotateCek.waiting'),
      () => waitForPayload(),
      t('commands.config.rotateCek.received')
    );

    const payload = await decryptHandoff(encryptedBlob, keyPair.privateKey);
    const stored = await storeHandoffCredentials(payload, configName);
    // The pointer file is already correct; a re-handoff may omit configId, so
    // fall back to the enrolled pointer's.
    const remote: RemoteConfig = {
      ...stored,
      configId: stored.configId ?? config.remote.configId,
    };

    // Prove the new key actually decrypts the freshly rotated blob before
    // declaring success — a silent stale key is the whole failure mode here.
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

    // The rotation rewrote every blob server-side; the offline cache must
    // follow, or a later offline read would serve pre-rotation content.
    const { writeRemoteCache } = await import('../services/config/remote-cache.js');
    await writeRemoteCache(configName, verifiedConfig, version);

    outputService.success(
      t('commands.config.rotateCek.success', { name: configName, version: String(version) })
    );
  } finally {
    close();
  }
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
    .option('--headless', t('commands.config.remote.enable.optionHeadless'))
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
        } else if (options.headless) {
          await enableHeadless(apiUrl, configName, opts);
        } else {
          await enableBrowser(apiUrl, configName, opts);
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
