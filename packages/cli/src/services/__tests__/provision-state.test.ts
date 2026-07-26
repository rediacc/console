import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

// Same config-state-not-sidecar arrangement as license-refresh-state.test.ts.
let mockState: Record<string, unknown> = {};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    updateState: vi.fn(
      (
        _name: string,
        fn: (cfg: Record<string, unknown>) => Record<string, unknown>
      ): Promise<void> => {
        mockState = fn({ state: mockState.state });
        return Promise.resolve();
      }
    ),
  },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn(() => Promise.resolve(mockState)),
    getEffectiveConfigName: vi.fn(() => 'test'),
  },
}));

const {
  dropProvisionEntry,
  getFreshProvisionEntry,
  isSetupVerifiedFresh,
  recordProvisionVerified,
  recordSetupVerified,
  RENET_PROVISION_STATE_TTL_MS,
} = await import('../renet/provision-state.js');
const { VERSION } = await import('../../version.js');

const NOW = Date.UTC(2026, 6, 22, 12, 0, 0);
const HOST = '192.168.111.11:22';

// A real temp file: the dev-mode trust envelope is a stat fingerprint, and a
// mocked stat would test the mock.
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'provision-state-'));
const binPath = path.join(tmpDir, 'renet');
fs.writeFileSync(binPath, 'binary-v1');

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

beforeEach(() => {
  mockState = {};
});

describe('renet provision persistent cache', () => {
  it('misses when nothing was recorded', async () => {
    expect(await getFreshProvisionEntry(HOST, null, NOW)).toBeNull();
  });

  it('hits within TTL for the same version (SEA: no source path)', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    const entry = await getFreshProvisionEntry(HOST, null, NOW + 60_000);
    expect(entry).toMatchObject({ hash: 'h1', arch: 'amd64', version: VERSION });
  });

  it('misses once the TTL has elapsed', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    expect(await getFreshProvisionEntry(HOST, null, NOW + RENET_PROVISION_STATE_TTL_MS)).toBeNull();
  });

  it('misses on a future timestamp (clock change)', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW + 1e7);
    expect(await getFreshProvisionEntry(HOST, null, NOW)).toBeNull();
  });

  it('misses when the recorded version differs', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    const bucket = (mockState.state as Record<string, Record<string, Record<string, unknown>>>)
      .renetProvision;
    bucket[HOST].version = 'something-else';
    expect(await getFreshProvisionEntry(HOST, null, NOW + 1)).toBeNull();
  });

  // The dev-loop promise: a rebuilt bin/renet MUST miss, or the next rdc.sh
  // invocation would skip deploying the developer's change. Dev VERSION is a
  // constant, so only the stat fingerprint can catch this.
  it('dev mode: hits while the source binary is unchanged, misses after a rebuild', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: binPath }, NOW);
    expect(await getFreshProvisionEntry(HOST, binPath, NOW + 60_000)).not.toBeNull();

    fs.writeFileSync(binPath, 'binary-v2-rebuilt');
    expect(await getFreshProvisionEntry(HOST, binPath, NOW + 61_000)).toBeNull();
  });

  it('dev mode: misses when the source binary cannot be statted', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: binPath }, NOW);
    expect(await getFreshProvisionEntry(HOST, path.join(tmpDir, 'gone'), NOW + 1)).toBeNull();
  });

  it('drop removes the entry (provision-failure fail-open)', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    await dropProvisionEntry(HOST);
    expect(await getFreshProvisionEntry(HOST, null, NOW + 1)).toBeNull();
  });

  it('setup verification annotates an existing entry and survives re-provision', async () => {
    expect(await isSetupVerifiedFresh(HOST, NOW)).toBe(false);
    // Without a provision entry, setup verification records nothing.
    await recordSetupVerified(HOST, NOW);
    expect(await isSetupVerifiedFresh(HOST, NOW + 1)).toBe(false);

    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    await recordSetupVerified(HOST, NOW + 1);
    expect(await isSetupVerifiedFresh(HOST, NOW + 2)).toBe(true);

    // A provision refresh preserves the setup annotation.
    await recordProvisionVerified(HOST, { hash: 'h2', arch: 'amd64', sourcePath: null }, NOW + 3);
    expect(await isSetupVerifiedFresh(HOST, NOW + 4)).toBe(true);

    expect(await isSetupVerifiedFresh(HOST, NOW + 1 + RENET_PROVISION_STATE_TTL_MS)).toBe(false);
  });

  it('tracks hosts independently', async () => {
    await recordProvisionVerified(HOST, { hash: 'h1', arch: 'amd64', sourcePath: null }, NOW);
    expect(await getFreshProvisionEntry('10.0.0.9:22', null, NOW + 1)).toBeNull();
  });
});
