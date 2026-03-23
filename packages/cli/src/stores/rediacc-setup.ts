/**
 * Rediacc Config Store Setup
 *
 * Handles the interactive setup flow for `rdc store add --type rediacc`:
 * - Desktop mode: Opens browser, starts local callback server
 * - Headless mode: Device code flow with ephemeral X25519 handoff
 */

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { execFile } from 'node:child_process';
import { randomBytes, toBase64 } from '@rediacc/shared/config-crypto';
import { getSecureStorage } from '../utils/secure-storage.js';
import { outputService } from '../services/output.js';
import { t } from '../i18n/index.js';

export interface SetupResult {
  apiUrl: string;
  storeId: string;
  storageKeyId: string;
  token: string;
  wrappedCek: string;
}

interface CallbackData {
  passkey_secret: string;
  token: string;
  storageKeyId: string;
  wrappedCek: string;
  storeId: string;
  apiUrl: string;
}

export interface SetupOptions {
  serverUrl: string;
  headless: boolean;
}

/**
 * Run the config store setup flow.
 * Desktop: opens browser → passkey + PRF → localhost callback
 * Headless: device code flow → server relay → X25519 decrypt
 */
export async function setupRediacStore(options: SetupOptions): Promise<SetupResult> {
  if (options.headless) {
    return headlessSetup(options.serverUrl);
  }
  return desktopSetup(options.serverUrl);
}

// ─── Desktop Setup ────────────────────────────────────────────────────

async function desktopSetup(serverUrl: string): Promise<SetupResult> {
  outputService.info(t('stores.rediaccSetup.startingSetup'));
  outputService.info(t('stores.rediaccSetup.browserWillOpen'));

  // Start local callback server
  const { port, waitForCallback, close } = await startCallbackServer();
  const nonce = toBase64(randomBytes(16));

  // Open browser
  const setupUrl = `${serverUrl}/account/config-setup?callback=http://127.0.0.1:${port}/callback&nonce=${nonce}`;
  outputService.info(`Opening: ${setupUrl}`);
  tryOpenBrowser(setupUrl);

  outputService.info(t('stores.rediaccSetup.waitingForPasskey'));
  outputService.info(t('stores.rediaccSetup.browserFallback'));

  try {
    // Wait for callback from browser
    const data = await Promise.race([
      waitForCallback(),
      timeout(300000, 'Setup timed out after 5 minutes. Try again.'),
    ]);

    // Store passkey_secret in native secure storage
    const storage = getSecureStorage();
    await storage.set(data.storageKeyId, data.passkey_secret);

    outputService.success(t('stores.rediaccSetup.setupComplete'));

    return {
      apiUrl: data.apiUrl || serverUrl,
      storeId: data.storeId,
      storageKeyId: data.storageKeyId,
      token: data.token,
      wrappedCek: data.wrappedCek,
    };
  } finally {
    close();
  }
}

// ─── Headless Setup ───────────────────────────────────────────────────

async function headlessSetup(serverUrl: string): Promise<SetupResult> {
  outputService.info(t('stores.rediaccSetup.startingHeadlessSetup'));
  outputService.info(t('stores.rediaccSetup.headlessInstructions'));

  // Generate ephemeral X25519 key pair for encrypted handoff
  const keyPairRaw = await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);
  const keyPair = keyPairRaw as unknown as {
    publicKey: Parameters<typeof crypto.subtle.exportKey>[1];
    privateKey: Parameters<typeof crypto.subtle.exportKey>[1];
  };

  const pubSpki = new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey));
  const handoffPubB64 = toBase64(pubSpki);

  // Request device code from server
  const initRes = await fetch(`${serverUrl}/account/api/v1/device-codes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'config-setup' }),
  });

  if (!initRes.ok) {
    throw new Error(`Failed to initiate device code flow: ${initRes.status}`);
  }

  const { deviceCode, interval, expiresIn } = (await initRes.json()) as {
    deviceCode: string;
    verificationUrl: string;
    interval: number;
    expiresIn: number;
  };

  // Show URL with handoff key embedded
  const deviceUrl = `${serverUrl}/account/device-config?code=${deviceCode}&key=${encodeURIComponent(handoffPubB64)}`;
  outputService.info('');
  outputService.info(t('stores.rediaccSetup.openUrl'));
  outputService.info(`  ${deviceUrl}`);
  outputService.info('');
  outputService.info(t('stores.rediaccSetup.waitingForCompletion'));

  // Poll for encrypted blob
  const pollInterval = (interval || 5) * 1000;
  const maxAttempts = Math.ceil((expiresIn || 600) / (interval || 5));

  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, pollInterval));

    const pollRes = await fetch(`${serverUrl}/account/api/v1/device-codes/${deviceCode}`, {
      headers: { 'Content-Type': 'application/json' },
    });

    if (!pollRes.ok) continue;

    const pollData = (await pollRes.json()) as { status: string; configHandoff?: unknown };

    if (pollData.status === 'expired') {
      throw new Error('Device code expired. Try again.');
    }

    if (pollData.status === 'complete' && pollData.configHandoff) {
      // Decrypt the handoff blob with our ephemeral private key
      const { cekHandoffDecrypt } = await import('@rediacc/shared/config-crypto');
      const handoffBlob =
        pollData.configHandoff as import('@rediacc/shared/config-crypto').CekHandoffBlob;
      const decryptedBytes = await cekHandoffDecrypt(handoffBlob, keyPair.privateKey);
      const data = JSON.parse(new TextDecoder().decode(decryptedBytes)) as CallbackData;

      // Store passkey_secret in native secure storage
      const storage = getSecureStorage();
      await storage.set(data.storageKeyId, data.passkey_secret);

      outputService.success(t('stores.rediaccSetup.setupComplete'));

      return {
        apiUrl: data.apiUrl || serverUrl,
        storeId: data.storeId,
        storageKeyId: data.storageKeyId,
        token: data.token,
        wrappedCek: data.wrappedCek,
      };
    }
  }

  throw new Error('Setup timed out. Try again.');
}

// ─── Helpers ──────────────────────────────────────────────────────────

function startCallbackServer(): Promise<{
  port: number;
  waitForCallback: () => Promise<CallbackData>;
  close: () => void;
}> {
  return new Promise((resolve) => {
    let callbackResolve: (data: CallbackData) => void;
    const callbackPromise = new Promise<CallbackData>((r) => {
      callbackResolve = r;
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

      if (req.method === 'POST' && req.url?.startsWith('/callback')) {
        let body = '';
        req.on('data', (chunk: Buffer) => {
          body += chunk.toString();
        });
        req.on('end', () => {
          res.writeHead(200, {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
          });
          res.end(JSON.stringify({ received: true }));

          try {
            callbackResolve(JSON.parse(body) as CallbackData);
          } catch {
            // Invalid JSON — ignore
          }
        });
        return;
      }

      res.writeHead(404);
      res.end('Not found');
    });

    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      resolve({
        port: addr.port,
        waitForCallback: () => callbackPromise,
        close: () => server.close(),
      });
    });
  });
}

function tryOpenBrowser(url: string): void {
  try {
    const platform = process.platform;
    if (platform === 'darwin') {
      execFile('open', [url]);
    } else if (platform === 'win32') {
      execFile('cmd', ['/c', 'start', '', url]);
    } else {
      execFile('xdg-open', [url]);
    }
  } catch {
    // Browser launch failed — user will copy URL manually
  }
}

function timeout(ms: number, message: string): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error(message)), ms);
  });
}
