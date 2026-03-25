import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { toBase64 } from '@rediacc/shared/config-crypto';
import type { CekHandoffBlob } from '@rediacc/shared/config-crypto';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account-client.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { getSubscriptionServerUrl } from '../services/subscription-auth.js';
import type { OutputFormat, RdcConfig, RemoteConfig } from '../types/index.js';
import { hasRemoteConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

/** Default output format when parent program is unavailable */
const DEFAULT_OUTPUT_FORMAT: OutputFormat = 'table';

// ─── Handoff Payload ─────────────────────────────────────────────────────

interface HandoffPayload {
  passkey_secret: string;
  token: string;
  storageKeyId: string;
  wrappedCek: string;
  storeId: string;
  configId: string;
  apiUrl: string;
  teamId?: string;
}

// ─── X25519 Helpers ──────────────────────────────────────────────────────

async function generateX25519KeyPair() {
  return (await crypto.subtle.generateKey(
    { name: 'X25519' } as unknown as Parameters<typeof crypto.subtle.generateKey>[0],
    true,
    ['deriveBits']
  )) as unknown as { publicKey: unknown; privateKey: unknown };
}

async function exportPublicKeyBase64(publicKey: unknown): Promise<string> {
  const spki = new Uint8Array(
    await crypto.subtle.exportKey(
      'spki',
      publicKey as Parameters<typeof crypto.subtle.exportKey>[1]
    )
  );
  return toBase64(spki);
}

async function decryptHandoff(
  encryptedBlob: CekHandoffBlob,
  privateKey: unknown
): Promise<HandoffPayload> {
  const { cekHandoffDecrypt } = await import('@rediacc/shared/config-crypto');
  const plainBytes = await cekHandoffDecrypt(encryptedBlob, privateKey);
  const json = new TextDecoder().decode(plainBytes);
  return JSON.parse(json) as HandoffPayload;
}

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

// ─── Sensitive Field Stripping ───────────────────────────────────────────

/** Fields to strip from the local config when switching to remote storage */
const REMOTE_STRIPPED_FIELDS = [
  'machines',
  'repositories',
  'storages',
  'ssh',
  'sshContent',
  'encrypted',
  'encryptedResources',
  'masterPassword',
  'token',
  'apiUrl',
  'userEmail',
  'cloudProviders',
  'backupStrategy',
  'deletedRepositories',
  'cfDnsApiToken',
  'cfDnsZoneId',
  'certEmail',
  'acmeCertCache',
  'renetPath',
  'nextNetworkId',
  'universalUser',
  'pruneGraceDays',
  'datastoreSize',
] as const satisfies readonly (keyof RdcConfig)[];

function stripSensitiveFields(config: RdcConfig): RdcConfig {
  const stripped = { ...config };
  for (const field of REMOTE_STRIPPED_FIELDS) {
    delete stripped[field];
  }
  return stripped;
}

// ─── Enable Flow ─────────────────────────────────────────────────────────

async function storeHandoffCredentials(
  payload: HandoffPayload,
  configName: string
): Promise<RemoteConfig> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();
  await secureStorage.set(payload.storageKeyId, payload.passkey_secret);

  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  await remoteTokenStorage.set(configName, {
    token: payload.token,
    wrappedCek: payload.wrappedCek,
  });

  return {
    apiUrl: payload.apiUrl,
    storeId: payload.storeId,
    configId: payload.configId,
    storageKeyId: payload.storageKeyId,
    teamId: payload.teamId,
  };
}

async function finalizeEnable(remote: RemoteConfig, configName: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');

  // Validate by pulling BEFORE modifying local config.
  // If pull fails, the local config remains untouched.
  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const adapter = new RemoteConfigAdapter(
    remote,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );
  await adapter.pull();

  // Pull succeeded -- now safe to write the stripped pointer file
  const config = await configFileStorage.load(configName);
  const pointer = stripSensitiveFields(config);
  pointer.remote = remote;
  await configFileStorage.save(pointer, configName);
}

async function enableBrowser(apiUrl: string, configName: string): Promise<void> {
  const keyPair = await generateX25519KeyPair();
  const pubBase64 = await exportPublicKeyBase64(keyPair.publicKey);

  const { port, waitForPayload, close } = await startCallbackServer();

  const callbackUrl = `http://localhost:${port}`;
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
    const remote = await storeHandoffCredentials(payload, configName);
    await finalizeEnable(remote, configName);

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

async function enableHeadless(apiUrl: string, configName: string): Promise<void> {
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
  const remote = await storeHandoffCredentials(payload, configName);
  await finalizeEnable(remote, configName);

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
  const { config: fullConfig } = await adapter.pull();

  // Write full decrypted config to local file, removing remote pointer
  const restored: RdcConfig = {
    ...fullConfig,
    language: localConfig.language,
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

  const { version } = await withSpinner(
    t('commands.config.remote.refresh.pulling'),
    () => adapter.pull(),
    t('commands.config.remote.refresh.pulled')
  );

  outputService.success(t('commands.config.remote.refresh.success', { version: String(version) }));
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
    .option('--api-url <url>', t('commands.config.remote.enable.optionApiUrl'))
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

        if (options.headless) {
          await enableHeadless(apiUrl, configName);
        } else {
          await enableBrowser(apiUrl, configName);
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
