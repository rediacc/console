import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/output.js', () => ({
  outputService: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

// Point the config dir at a scratch XDG_CONFIG_HOME *before* importing anything
// that captures getConfigDir() (config-file-storage does so at module load).
const configHome = mkdtempSync(join(tmpdir(), 'rdc-isolation-'));
process.env.XDG_CONFIG_HOME = configHome;
const configDir = join(configHome, 'rediacc');

const { handleChannelSwitch } = await import('../../commands/update.js');
const { saveStoredSubscriptionToken } = await import('../account/subscription-auth.js');
const { setConfigNameOverride } = await import('../config/config-name.js');
const { configFileStorage } = await import('../../adapters/config-file-storage.js');

function fullConfig(id: string, account: Record<string, unknown> = {}): string {
  return JSON.stringify({
    schemaVersion: 3,
    id,
    version: 1,
    encryption: { mode: 'plaintext' },
    account,
  });
}

describe('per-config isolation', () => {
  beforeEach(() => {
    mkdirSync(configDir, { recursive: true });
    // Two full v3 configs.
    writeFileSync(
      join(configDir, 'a.json'),
      fullConfig('00000000-0000-4000-8000-00000000000a', { accountServer: 'https://a.example.com' })
    );
    writeFileSync(
      join(configDir, 'b.json'),
      fullConfig('00000000-0000-4000-8000-00000000000b', { accountServer: 'https://b.example.com' })
    );
    // A pre-existing token for config b that must not be disturbed.
    writeFileSync(
      join(configDir, 'api-token-b.json'),
      JSON.stringify({ token: 'rdt_b', serverUrl: 'https://b.example.com' })
    );
    configFileStorage.clearCache();
    setConfigNameOverride(null);
    process.env.REDIACC_CONFIG = 'a';
  });

  afterEach(() => {
    delete process.env.REDIACC_CONFIG;
    setConfigNameOverride(null);
    rmSync(configDir, { recursive: true, force: true });
  });

  afterAll(() => {
    rmSync(configHome, { recursive: true, force: true });
  });

  it('writes under config "a" never touch config "b" or create server.json', async () => {
    const bSnapshot = readFileSync(join(configDir, 'b.json'));
    const bTokenSnapshot = readFileSync(join(configDir, 'api-token-b.json'));

    // 1. Save a subscription token while REDIACC_CONFIG=a.
    saveStoredSubscriptionToken({ token: 'rdt_a', serverUrl: 'https://a.example.com' });

    // 2. Run the channel-switch writer.
    await handleChannelSwitch('edge', {});

    // 3. Simulate the resolveAndSyncServer account write (login path).
    await configFileStorage.update('a', (cfg) => ({
      ...cfg,
      account: { ...(cfg.account ?? {}), e2ePublicKey: 'seeded-by-login' },
    }));

    // Config b and its token are byte-identical to their pre-test snapshots.
    expect(readFileSync(join(configDir, 'b.json')).equals(bSnapshot)).toBe(true);
    expect(readFileSync(join(configDir, 'api-token-b.json')).equals(bTokenSnapshot)).toBe(true);

    // The token landed in a's per-config file, not b's or a bare api-token.json.
    expect(existsSync(join(configDir, 'api-token-a.json'))).toBe(true);
    expect(existsSync(join(configDir, 'api-token.json'))).toBe(false);

    // Config a actually received the channel and e2e key.
    const a = JSON.parse(readFileSync(join(configDir, 'a.json'), 'utf-8'));
    expect(a.account.updateChannel).toBe('edge');
    expect(a.account.e2ePublicKey).toBe('seeded-by-login');

    // server.json was never created.
    expect(existsSync(join(configDir, 'server.json'))).toBe(false);
  });
});
