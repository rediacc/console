import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockOutputService = vi.hoisted(() => ({
  outputService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}));

vi.mock('../../services/core/output.js', () => mockOutputService);

// Point the config dir at a scratch XDG_CONFIG_HOME *before* importing update.js
// (config-file-storage captures getConfigDir() at module load). handleChannelSwitch
// now writes the active config file (rediacc.json), not the retired server.json.
const configHome = mkdtempSync(join(tmpdir(), 'rdc-update-home-'));
process.env.XDG_CONFIG_HOME = configHome;
const configDir = join(configHome, 'rediacc');
const configPath = join(configDir, 'rediacc.json');

const { handleChannelSwitch } = await import('../update.js');
const { configFileStorage } = await import('../../adapters/config-file-storage.js');

function readConfig(): Record<string, unknown> {
  return JSON.parse(readFileSync(configPath, 'utf-8'));
}

describe('handleChannelSwitch', () => {
  beforeEach(() => {
    mkdirSync(configDir, { recursive: true });
    rmSync(configPath, { force: true });
    rmSync(`${configPath}.bak`, { force: true });
    configFileStorage.clearCache();
    delete process.env.REDIACC_CONFIG;
    mockOutputService.outputService.success.mockReset();
    mockOutputService.outputService.error.mockReset();
  });

  afterEach(() => {
    rmSync(configPath, { force: true });
    rmSync(`${configPath}.bak`, { force: true });
  });

  afterAll(() => {
    rmSync(configHome, { recursive: true, force: true });
  });

  it('creates the default config with account.updateChannel when none exists', async () => {
    const result = await handleChannelSwitch('edge', {});

    expect(existsSync(configPath)).toBe(true);
    const parsed = readConfig();
    expect((parsed.account as Record<string, unknown>).updateChannel).toBe('edge');
    expect(parsed.schemaVersion).toBe(3);
    expect(result).toBe(true);
    expect(mockOutputService.outputService.success).toHaveBeenCalled();
  });

  it('merges updateChannel into an existing config without clobbering other account fields', async () => {
    writeFileSync(
      configPath,
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-000000000001',
        version: 1,
        encryption: { mode: 'plaintext' },
        account: {
          accountServer: 'https://edge.rediacc.com',
          e2ePublicKey: 'MEIwBQYDK2VwAzkA...',
          releasesUrl: 'https://releases.rediacc.com',
        },
      })
    );

    await handleChannelSwitch('stable', {});

    const account = readConfig().account as Record<string, unknown>;
    expect(account).toMatchObject({
      accountServer: 'https://edge.rediacc.com',
      e2ePublicKey: 'MEIwBQYDK2VwAzkA...',
      releasesUrl: 'https://releases.rediacc.com',
      updateChannel: 'stable',
    });
  });

  it('overwrites an existing updateChannel in place', async () => {
    writeFileSync(
      configPath,
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-000000000002',
        version: 1,
        encryption: { mode: 'plaintext' },
        account: { accountServer: 'https://www.rediacc.com', updateChannel: 'edge' },
      })
    );

    await handleChannelSwitch('stable', {});

    const account = readConfig().account as Record<string, unknown>;
    expect(account.updateChannel).toBe('stable');
  });

  it('errors when a non-default named config does not exist', async () => {
    process.env.REDIACC_CONFIG = 'ghost';
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('exit');
    });

    await expect(handleChannelSwitch('edge', {})).rejects.toThrow('exit');
    expect(mockOutputService.outputService.error).toHaveBeenCalled();

    exitSpy.mockRestore();
  });

  it('returns false when called with --force (skip subsequent update)', async () => {
    const result = await handleChannelSwitch('edge', { force: true });
    expect(result).toBe(false);
  });

  it('returns false when called with --check-only', async () => {
    const result = await handleChannelSwitch('edge', { checkOnly: true });
    expect(result).toBe(false);
  });
});
