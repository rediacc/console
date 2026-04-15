/**
 * License smoke test against a live preview Worker deployment.
 *
 * Validates the full licensing chain end-to-end:
 * 1. Worker health check
 * 2. Server-info E2E key discovery
 * 3. License status via encrypted tunnel
 * 4. Repo license issuance via encrypted tunnel
 * 5. Ed25519 signature verification of the issued license
 * 6. Payload field validation
 *
 * Required env:
 *   PREVIEW_URL               https://pr-N.rediacc.workers.dev
 *   SMOKE_TEST_TOKEN           API token seeded into preview D1
 *   ACCOUNT_ED25519_PUBLIC_KEY Ed25519 public key (SPKI base64) for signature verification
 */

import {
  type E2eResponseEnvelope,
  importX25519PublicKey,
  openResponse,
  sealRequest,
} from '@rediacc/shared/e2e';
import {
  type SignedSubscriptionBlob,
  importPublicKey,
  verifySignature,
} from '@rediacc/shared/subscription';

const PREVIEW_URL = process.env.PREVIEW_URL;
const TOKEN = process.env.SMOKE_TEST_TOKEN;
const ED25519_PUBLIC_KEY = process.env.ACCOUNT_ED25519_PUBLIC_KEY;

if (!PREVIEW_URL || !TOKEN || !ED25519_PUBLIC_KEY) {
  console.error('Missing required env: PREVIEW_URL, SMOKE_TEST_TOKEN, ACCOUNT_ED25519_PUBLIC_KEY');
  process.exit(1);
}

const TEST_MACHINE_ID = 'a'.repeat(64); // deterministic 64-char hex
const TEST_CLIENT_MACHINE_ID = 'b'.repeat(64);
const TEST_REPO_GUID = '00000000-0000-4000-8000-000000000001';

let passed = 0;
let failed = 0;

function ok(name: string): void {
  passed++;
  console.log(`  ✓ ${name}`);
}

function fail(name: string, error: unknown): void {
  failed++;
  console.error(`  ✗ ${name}: ${error instanceof Error ? error.message : String(error)}`);
}

// ── Step 1: Health check ─────────────────────────────────────────────

async function checkHealth(): Promise<void> {
  const resp = await fetch(`${PREVIEW_URL}/account/api/v1/health`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const body = (await resp.json()) as { status: string };
  if (body.status !== 'ok') throw new Error(`status: ${body.status}`);
}

// ── Step 2: Server-info ──────────────────────────────────────────────

interface ServerInfo {
  e2e?: { keys?: { keyId: string; publicKeySpki: string }[] };
  apiVersion?: number;
  environment?: string;
}

async function getServerInfo(): Promise<ServerInfo> {
  const resp = await fetch(`${PREVIEW_URL}/account/api/v1/.well-known/server-info`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as ServerInfo;
}

// ── Step 3-5: Tunnel request ─────────────────────────────────────────

async function tunnelRequest(
  serverKey: CryptoKey,
  keyId: string,
  method: string,
  path: string,
  body?: unknown
): Promise<{ status: number; data: unknown }> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${TOKEN}`,
  };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const { envelope, aesKey } = await sealRequest(serverKey, keyId, method, path, headers, body ?? null);

  const resp = await fetch(`${PREVIEW_URL}/account/api/v1/tunnel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(envelope),
  });

  if (!resp.ok) {
    const errorBody = await resp.text();
    throw new Error(`Tunnel HTTP ${resp.status}: ${errorBody}`);
  }

  const responseEnvelope = (await resp.json()) as E2eResponseEnvelope;
  const { status, body: responseBody } = await openResponse(aesKey, responseEnvelope);
  return { status, data: responseBody ? JSON.parse(responseBody) : null };
}

// ── Main ─────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log(`\nLicense Smoke Test: ${PREVIEW_URL}\n`);

  // Step 1: Health
  try {
    await checkHealth();
    ok('Health check (GET /health)');
  } catch (e) {
    fail('Health check', e);
    process.exit(1); // Can't continue without a healthy worker
  }

  // Step 2: Server-info + E2E key
  let serverKey: CryptoKey;
  let keyId: string;
  try {
    const info = await getServerInfo();
    if (!info.e2e?.keys?.length) throw new Error('No E2E keys in server-info');
    const key = info.e2e.keys[0];
    serverKey = await importX25519PublicKey(key.publicKeySpki);
    keyId = key.keyId;
    ok(`Server-info (E2E key: ${keyId}, env: ${info.environment})`);
  } catch (e) {
    fail('Server-info', e);
    process.exit(1);
  }

  // Step 3: License status via tunnel
  try {
    const { status, data } = await tunnelRequest(
      serverKey,
      keyId,
      'GET',
      '/account/api/v1/licenses/status'
    );
    if (status >= 400) throw new Error(`Inner HTTP ${status}: ${JSON.stringify(data)}`);
    const result = data as { subscriptionId?: string; planCode?: string; status?: string };
    if (!result.subscriptionId) throw new Error('Missing subscriptionId');
    if (!result.planCode) throw new Error('Missing planCode');
    ok(`License status (plan: ${result.planCode}, status: ${result.status})`);
  } catch (e) {
    fail('License status', e);
  }

  // Step 4: Issue repo license via tunnel
  let signedLicense: SignedSubscriptionBlob | null = null;
  try {
    const { status, data } = await tunnelRequest(
      serverKey,
      keyId,
      'POST',
      '/account/api/v1/licenses/activate-repo',
      {
        machineId: TEST_MACHINE_ID,
        clientMachineId: TEST_CLIENT_MACHINE_ID,
        repositoryGuid: TEST_REPO_GUID,
        kind: 'grand',
        requestedSizeGb: 1,
      }
    );
    if (status >= 400) throw new Error(`Inner HTTP ${status}: ${JSON.stringify(data)}`);
    const result = data as { license?: { payload: string; signature: string; publicKeyId: string } };
    if (!result.license?.payload) throw new Error('Missing license.payload');
    if (!result.license?.signature) throw new Error('Missing license.signature');
    if (!result.license?.publicKeyId) throw new Error('Missing license.publicKeyId');
    signedLicense = result.license as SignedSubscriptionBlob;
    ok(`Repo license issued (keyId: ${signedLicense.publicKeyId})`);
  } catch (e) {
    fail('Repo license issuance', e);
  }

  // Step 5: Verify Ed25519 signature
  if (signedLicense) {
    try {
      await importPublicKey(signedLicense.publicKeyId, ED25519_PUBLIC_KEY);
      const valid = await verifySignature(signedLicense);
      if (!valid) throw new Error('Signature verification returned false');
      ok('Ed25519 signature verified');
    } catch (e) {
      fail('Signature verification', e);
    }

    // Step 6: Decode and validate payload fields
    try {
      const payload = JSON.parse(atob(signedLicense.payload)) as Record<string, unknown>;
      const checks = [
        ['machineId', payload.machineId === TEST_MACHINE_ID],
        ['repositoryGuid', payload.repositoryGuid === TEST_REPO_GUID],
        ['kind', payload.kind === 'grand'],
        ['planCode', typeof payload.planCode === 'string' && (payload.planCode as string).length > 0],
        ['hardExpiresAt', typeof payload.hardExpiresAt === 'string' && new Date(payload.hardExpiresAt as string).getTime() > Date.now()],
        ['issuedAt', typeof payload.issuedAt === 'string'],
        ['maxRepositorySizeGb', typeof payload.maxRepositorySizeGb === 'number' && (payload.maxRepositorySizeGb as number) > 0],
      ] as const;
      const failures = checks.filter(([, ok]) => !ok).map(([name]) => name);
      if (failures.length > 0) throw new Error(`Invalid fields: ${failures.join(', ')}`);
      ok(`Payload fields valid (plan: ${payload.planCode}, expires: ${payload.hardExpiresAt})`);
    } catch (e) {
      fail('Payload validation', e);
    }
  }

  // ── Step 7: Channel rewrite assertions ─────────────────────────────
  // The preview worker must rewrite install.sh/install.ps1 to bake the
  // PR-N channel into the CLI defaults it hands out. Without this, users
  // visiting a PR preview download the stable CLI instead of the preview
  // build — the exact regression this test exists to catch.
  const expectedChannel = extractChannel(PREVIEW_URL);
  if (!expectedChannel) {
    fail('Channel extraction', new Error(`Could not parse channel from ${PREVIEW_URL}`));
  } else {
    await checkInstallSh(expectedChannel);
    await checkInstallPs1(expectedChannel);
    await checkMarketingHtml(expectedChannel);
  }

  // Summary
  console.log(`\n${passed} passed, ${failed} failed\n`);
  if (failed > 0) process.exit(1);
}

function extractChannel(url: string): string | null {
  const host = new URL(url).hostname;
  const m = host.match(/^([^.]+)\.rediacc\./);
  return m ? m[1] : null;
}

async function checkInstallSh(expectedChannel: string): Promise<void> {
  try {
    const resp = await fetch(`${PREVIEW_URL}/install.sh`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const body = await resp.text();
    if (!body.includes(`REDIACC_CHANNEL:-${expectedChannel}`)) {
      throw new Error(`install.sh default channel is not ${expectedChannel}`);
    }
    if (!body.includes(`REDIACC_SERVER_URL:-${PREVIEW_URL}}`)) {
      throw new Error(`install.sh default server URL is not ${PREVIEW_URL}`);
    }
    ok(`install.sh baked to channel=${expectedChannel}`);
  } catch (e) {
    fail('install.sh channel rewrite', e);
  }
}

async function checkInstallPs1(expectedChannel: string): Promise<void> {
  try {
    const resp = await fetch(`${PREVIEW_URL}/install.ps1`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const body = await resp.text();
    if (!body.includes(`} else { "${expectedChannel}" }`)) {
      throw new Error(`install.ps1 default channel is not ${expectedChannel}`);
    }
    ok(`install.ps1 baked to channel=${expectedChannel}`);
  } catch (e) {
    fail('install.ps1 channel rewrite', e);
  }
}

async function checkMarketingHtml(expectedChannel: string): Promise<void> {
  // The install page renders BINARY_COMMANDS, DOCKER_COMMANDS, and package
  // manager snippets. The worker rewrites `releases.rediacc.com/<fmt>/stable`
  // → `.../<expectedChannel>` and `elite/cli:stable` → `elite/cli:<expectedChannel>`
  // for every channel-scoped URL baked at build time.
  try {
    const resp = await fetch(`${PREVIEW_URL}/install`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const body = await resp.text();
    const stale = [
      'releases.rediacc.com/cli/stable/',
      'releases.rediacc.com/npm/stable/',
      'releases.rediacc.com/apt/stable',
      'releases.rediacc.com/rpm/stable',
      'releases.rediacc.com/apk/stable',
      'releases.rediacc.com/archlinux/stable',
      'elite/cli:stable',
    ];
    const leaked = stale.filter((s) => body.includes(s));
    if (leaked.length > 0) {
      throw new Error(`Marketing HTML still references stable: ${leaked.join(', ')}`);
    }
    ok(`Marketing /install rewritten to channel=${expectedChannel}`);
  } catch (e) {
    fail('Marketing HTML channel rewrite', e);
  }
}

main().catch((e) => {
  console.error('Smoke test crashed:', e);
  process.exit(1);
});
