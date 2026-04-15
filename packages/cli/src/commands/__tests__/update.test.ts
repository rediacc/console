import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockOutputService = vi.hoisted(() => ({
  outputService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}));

vi.mock('../../services/output.js', () => mockOutputService);

// Route the CLI's getConfigDir() to a scratch directory so we can assert on the
// actual file we write, using the production saveServerConfig/loadServerConfig.
// Module-load-time imports call getConfigDir() eagerly, so we must set a root
// scratch directory synchronously before importing anything that touches it.
const scratchRoot = mkdtempSync(join(tmpdir(), 'rdc-update-test-root-'));
let scratch = scratchRoot;

vi.mock('@rediacc/shared/paths', async () => {
  const actual =
    await vi.importActual<typeof import('@rediacc/shared/paths')>('@rediacc/shared/paths');
  return {
    ...actual,
    getConfigDir: () => scratch,
  };
});

const { handleChannelSwitch } = await import('../update.js');

describe('handleChannelSwitch', () => {
  beforeEach(() => {
    scratch = mkdtempSync(join(tmpdir(), 'rdc-update-test-'));
    mockOutputService.outputService.success.mockReset();
    mockOutputService.outputService.error.mockReset();
  });

  afterEach(() => {
    rmSync(scratch, { recursive: true, force: true });
  });

  it('creates server.json with default accountServer when none exists', async () => {
    const result = await handleChannelSwitch('edge', {});
    const serverJsonPath = join(scratch, 'server.json');

    expect(existsSync(serverJsonPath)).toBe(true);
    const parsed = JSON.parse(readFileSync(serverJsonPath, 'utf-8'));
    expect(parsed).toEqual({
      accountServer: 'https://www.rediacc.com',
      updateChannel: 'edge',
    });
    expect(result).toBe(true);
    expect(mockOutputService.outputService.success).toHaveBeenCalled();
  });

  it('merges updateChannel into an existing server.json without clobbering other fields', async () => {
    const existing = {
      accountServer: 'https://edge.rediacc.com',
      e2ePublicKey: 'MEIwBQYDK2VwAzkA...',
      region: 'eu',
      releasesUrl: 'https://releases.rediacc.com',
    };
    writeFileSync(join(scratch, 'server.json'), JSON.stringify(existing));

    await handleChannelSwitch('stable', {});

    const parsed = JSON.parse(readFileSync(join(scratch, 'server.json'), 'utf-8'));
    expect(parsed).toEqual({
      ...existing,
      updateChannel: 'stable',
    });
  });

  it('writes server.json with mode 0o600', async () => {
    await handleChannelSwitch('edge', {});
    const mode = statSync(join(scratch, 'server.json')).mode & 0o777;
    expect(mode).toBe(0o600);
  });

  it('returns false when called with --force (skip subsequent update)', async () => {
    const result = await handleChannelSwitch('edge', { force: true });
    expect(result).toBe(false);
  });

  it('returns false when called with --check-only', async () => {
    const result = await handleChannelSwitch('edge', { checkOnly: true });
    expect(result).toBe(false);
  });

  it('overwrites an existing updateChannel in place', async () => {
    writeFileSync(
      join(scratch, 'server.json'),
      JSON.stringify({ accountServer: 'https://www.rediacc.com', updateChannel: 'edge' })
    );
    await handleChannelSwitch('stable', {});
    const parsed = JSON.parse(readFileSync(join(scratch, 'server.json'), 'utf-8'));
    expect(parsed.updateChannel).toBe('stable');
  });
});
