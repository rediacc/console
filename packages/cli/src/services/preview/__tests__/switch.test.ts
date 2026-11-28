import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UpdateManifest } from '../../../types/index.js';
import type { PreviewLeaveDeps, PreviewUseDeps } from '../switch.js';

const { out } = vi.hoisted(() => ({
  out: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../core/output.js', () => ({ outputService: out }));

// The config dir is captured at module load (config-file-storage), so the scratch XDG_CONFIG_HOME is set before any import.
const configHome = mkdtempSync(join(tmpdir(), 'rdc-preview-switch-'));
process.env.XDG_CONFIG_HOME = configHome;
const configDir = join(configHome, 'rediacc');

const { configFileStorage } = await import('../../../adapters/config-file-storage.js');
const { setConfigNameOverride } = await import('../../config/config-name.js');
const { readPreviewOverlay, recordPreviewTouch } = await import('../state.js');
const { leavePreviewFlow, previewBanner, previewStatusLines, switchToPreview } = await import(
  '../switch.js'
);

const CONFIG = 'customer';
const NAME = 'pv-amber-river-stone';
const SHA = 'c'.repeat(64);
const KEPT_SHA = 'a'.repeat(64);
const KEPT_PATH = join(configHome, 'kept', 'rdc.pre-preview');

function manifest(overrides: Partial<{ version: string; sha256: string }> = {}): UpdateManifest {
  return {
    version: overrides.version ?? '1.4.0-preview.abc1234',
    releaseDate: '2026-11-22',
    releaseNotesUrl: '',
    binaries: {
      'linux-x64': {
        url: `https://releases.example/cli/${NAME}/rdc-linux-x64`,
        sha256: overrides.sha256 ?? SHA,
      },
    },
  };
}

function useDeps(overrides: Partial<PreviewUseDeps> = {}): PreviewUseDeps {
  return {
    fetchServerInfo: vi.fn(() =>
      Promise.resolve({
        previewBuild: { version: '1.4.0-preview.abc1234', sha256: { 'linux-x64': SHA } },
      })
    ),
    fetchManifest: vi.fn(() => Promise.resolve(manifest())),
    platformKey: () => 'linux-x64',
    canReplaceBinary: () => true,
    keepCurrentBinary: vi.fn(() =>
      Promise.resolve({ installPath: '/usr/local/bin/rdc', sha256: KEPT_SHA })
    ),
    installBinary: vi.fn(() => Promise.resolve()),
    confirmFormatChange: vi.fn(() => Promise.resolve(true)),
    current: () => ({ version: '1.3.9', updateChannel: 'stable' }),
    realServer: () => WK_ACCOUNT_DEFAULT_ORIGIN,
    now: () => new Date('2026-11-23T10:00:00.000Z'),
    ...overrides,
  };
}

const FORMAT = { formats: ['vault'], reason: 'the vault schema gains a field' };

function leaveDeps(overrides: Partial<PreviewLeaveDeps> = {}): PreviewLeaveDeps {
  return {
    confirm: vi.fn(() => Promise.resolve(true)),
    currentRenetVersion: vi.fn(() => Promise.resolve('1.4.0-preview.abc1234')),
    switchBack: vi.fn(() => Promise.resolve({ status: 'switched' as const })),
    fetchPreviousManifest: vi.fn(() => Promise.resolve(manifest({ version: '1.3.9' }))),
    platformKey: () => 'linux-x64',
    installBinaryAt: vi.fn(() => Promise.resolve()),
    restoreKeptCopy: vi.fn(() => Promise.resolve()),
    relicense: vi.fn(() => Promise.resolve()),
    realServer: () => WK_ACCOUNT_DEFAULT_ORIGIN,
    ...overrides,
  };
}

const touched = {
  slot: '/usr/lib/rediacc/renet/1.3.9',
  version: '1.3.9',
  sha256: 'b'.repeat(64),
  touchedAt: '2026-11-23T10:05:00.000Z',
};

function accountText(): string {
  return JSON.stringify(
    (JSON.parse(readFileSync(join(configDir, `${CONFIG}.json`), 'utf8')) as { account: unknown })
      .account
  );
}

describe('rdc preview use', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    rmSync(configDir, { recursive: true, force: true });
    mkdirSync(configDir, { recursive: true });
    writeFileSync(
      join(configDir, `${CONFIG}.json`),
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-0000000000c2',
        version: 1,
        encryption: { mode: 'plaintext' },
        account: { accountServer: WK_ACCOUNT_DEFAULT_ORIGIN, updateChannel: 'stable' },
      })
    );
    configFileStorage.clearCache();
    setConfigNameOverride(CONFIG);
    await configFileStorage.update(CONFIG, (c) => c);
  });

  afterAll(() => {
    setConfigNameOverride(null);
    rmSync(configHome, { recursive: true, force: true });
  });

  it('refuses a hash the preview server and the manifest disagree on, before any file or the config changes', async () => {
    const deps = useDeps({
      fetchManifest: vi.fn(() => Promise.resolve(manifest({ sha256: 'd'.repeat(64) }))),
    });
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, deps, CONFIG)).rejects.toThrow(
      /checksum in the release manifest differs/
    );
    expect(deps.keepCurrentBinary).not.toHaveBeenCalled();
    expect(deps.installBinary).not.toHaveBeenCalled();
    expect(readPreviewOverlay(CONFIG)).toBeUndefined();
  });

  it('refuses a version the two origins disagree on and a server that sends no build', async () => {
    const stale = useDeps({
      fetchManifest: vi.fn(() => Promise.resolve(manifest({ version: '1.4.0-preview.0000000' }))),
    });
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, stale, CONFIG)).rejects.toThrow(
      /manifest says/
    );
    const none = useDeps({ fetchServerInfo: vi.fn(() => Promise.resolve({})) });
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, none, CONFIG)).rejects.toThrow(
      /answers no build/
    );
    expect(stale.installBinary).not.toHaveBeenCalled();
    expect(none.keepCurrentBinary).not.toHaveBeenCalled();
  });

  it('refuses a format-change preview without confirmation, and runs it with --accept-format-change', async () => {
    const build = {
      version: '1.4.0-preview.abc1234',
      sha256: { 'linux-x64': SHA },
      formatChange: FORMAT,
    };
    const declined = useDeps({
      fetchServerInfo: vi.fn(() => Promise.resolve({ previewBuild: build })),
      confirmFormatChange: vi.fn(() => Promise.resolve(false)),
    });
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, declined, CONFIG)).rejects.toThrow(
      /on-disk format change was not accepted/
    );
    expect(out.warn).toHaveBeenCalledWith(expect.stringContaining('vault schema gains a field'));
    expect(declined.keepCurrentBinary).not.toHaveBeenCalled();
    expect(readPreviewOverlay(CONFIG)).toBeUndefined();

    const scripted = useDeps({
      fetchServerInfo: vi.fn(() => Promise.resolve({ previewBuild: build })),
      confirmFormatChange: vi.fn(() => Promise.resolve(false)),
    });
    const overlay = await switchToPreview(
      NAME,
      { keptPath: KEPT_PATH, acceptFormatChange: true },
      scripted,
      CONFIG
    );
    expect(scripted.confirmFormatChange).not.toHaveBeenCalled();
    expect(overlay.formatChange).toEqual(FORMAT);
  });

  it('keeps the CLI before replacing it, records the way back, and prints the message and the emergency exit', async () => {
    const order: string[] = [];
    const deps = useDeps({
      keepCurrentBinary: vi.fn(() => {
        order.push('keep');
        return Promise.resolve({ installPath: '/usr/local/bin/rdc', sha256: KEPT_SHA });
      }),
      installBinary: vi.fn(() => {
        order.push('install');
        expect(readPreviewOverlay(CONFIG)?.name).toBe(NAME);
        return Promise.resolve();
      }),
    });
    const accountBefore = accountText();
    const overlay = await switchToPreview(NAME, { keptPath: KEPT_PATH }, deps, CONFIG);

    expect(order).toEqual(['keep', 'install']);
    expect(overlay.previous).toEqual({
      cliVersion: '1.3.9',
      cliSha256: KEPT_SHA,
      binaryPath: '/usr/local/bin/rdc',
      updateChannel: 'stable',
    });
    expect(overlay.licenceEndsAt).toBe('2026-11-30T10:00:00.000Z');
    expect(accountText()).toBe(accountBefore);
    const infos = out.info.mock.calls.map((c) => String(c[0]));
    expect(infos.some((m) => m.includes('running apps keep running'))).toBe(true);
    expect(infos.some((m) => m.includes(`${KEPT_PATH} preview leave`))).toBe(true);
  });

  it('removes the state again when the install fails, so a failed use changes nothing', async () => {
    const deps = useDeps({ installBinary: vi.fn(() => Promise.reject(new Error('disk full'))) });
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, deps, CONFIG)).rejects.toThrow(
      'disk full'
    );
    expect(readPreviewOverlay(CONFIG)).toBeUndefined();
  });

  it('refuses a second preview, and an install that cannot replace its binary', async () => {
    await switchToPreview(NAME, { keptPath: KEPT_PATH }, useDeps(), CONFIG);
    await expect(
      switchToPreview('pv-other-river-stone', { keptPath: KEPT_PATH }, useDeps(), CONFIG)
    ).rejects.toThrow(/already on preview/);
    const npm = useDeps({ canReplaceBinary: () => false });
    await leavePreviewFlow({}, leaveDeps(), CONFIG);
    await expect(switchToPreview(NAME, { keptPath: KEPT_PATH }, npm, CONFIG)).rejects.toThrow(
      /packaged rdc/
    );
  });
});

describe('rdc preview leave', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    rmSync(configDir, { recursive: true, force: true });
    mkdirSync(configDir, { recursive: true });
    writeFileSync(
      join(configDir, `${CONFIG}.json`),
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-0000000000c3',
        version: 1,
        encryption: { mode: 'plaintext' },
        account: { accountServer: WK_ACCOUNT_DEFAULT_ORIGIN, updateChannel: 'stable' },
      })
    );
    configFileStorage.clearCache();
    setConfigNameOverride(CONFIG);
    await configFileStorage.update(CONFIG, (c) => c);
    await switchToPreview(NAME, { keptPath: KEPT_PATH }, useDeps(), CONFIG);
    vi.clearAllMocks();
  });

  it('restores the previous channel build with the preview host and channel gone, never reading them', async () => {
    const deps = leaveDeps();
    const result = await leavePreviewFlow({}, deps, CONFIG);

    expect(result).toEqual({ left: true, switched: [], remaining: [] });
    expect(readPreviewOverlay(CONFIG)).toBeUndefined();
    expect(deps.fetchPreviousManifest).toHaveBeenCalledWith('stable');
    expect(deps.installBinaryAt).toHaveBeenCalledWith('/usr/local/bin/rdc', {
      version: '1.3.9',
      sha256: SHA,
      url: expect.stringContaining('rdc-linux-x64'),
    });
    expect(deps.restoreKeptCopy).not.toHaveBeenCalled();
    // The deps carry no preview host or channel reader at all: `leave` cannot depend on either.
    expect(Object.keys(deps)).not.toContain('fetchServerInfo');
  });

  it('falls back to the kept copy when the previous channel is unreachable (leave from the kept copy)', async () => {
    const deps = leaveDeps({
      fetchPreviousManifest: vi.fn(() => Promise.reject(new Error('HTTP 404'))),
    });
    const result = await leavePreviewFlow({}, deps, CONFIG);

    expect(result.left).toBe(true);
    expect(deps.installBinaryAt).not.toHaveBeenCalled();
    expect(deps.restoreKeptCopy).toHaveBeenCalledWith('/usr/local/bin/rdc', KEPT_SHA);
    expect(out.info).toHaveBeenCalledWith(expect.stringContaining('HTTP 404'));
  });

  it('says so loudly when neither the channel nor the kept copy restores the binary', async () => {
    const deps = leaveDeps({
      fetchPreviousManifest: vi.fn(() => Promise.reject(new Error('HTTP 404'))),
      restoreKeptCopy: vi.fn(() => Promise.reject(new Error('no longer matches'))),
    });
    await leavePreviewFlow({}, deps, CONFIG);
    expect(out.warn).toHaveBeenCalledWith(expect.stringContaining('rdc was not restored'));
  });

  it('does not run the re-licensing (which runs the restored CLI) when the binary was not restored', async () => {
    await recordPreviewTouch('vm1', touched, CONFIG);
    const deps = leaveDeps({
      fetchPreviousManifest: vi.fn(() => Promise.reject(new Error('HTTP 404'))),
      restoreKeptCopy: vi.fn(() => Promise.reject(new Error('no longer matches'))),
    });
    const result = await leavePreviewFlow({}, deps, CONFIG);
    expect(result).toMatchObject({ left: true, switched: ['vm1'] });
    expect(deps.relicense).not.toHaveBeenCalled();
  });

  it('switches back exactly the confirmed touched servers, keeps an unreachable one, and keeps the overlay', async () => {
    await recordPreviewTouch('vm1', touched, CONFIG);
    await recordPreviewTouch('vm2', { ...touched, slot: '/usr/lib/rediacc/renet/1.3.8' }, CONFIG);
    const deps = leaveDeps({
      switchBack: vi.fn((machine: string) =>
        Promise.resolve(
          machine === 'vm2'
            ? { status: 'unreachable' as const, detail: 'timeout' }
            : { status: 'switched' as const }
        )
      ),
    });

    const result = await leavePreviewFlow({}, deps, CONFIG);

    expect(result).toEqual({ left: false, switched: ['vm1'], remaining: ['vm2'] });
    expect(Object.keys(readPreviewOverlay(CONFIG)?.touched ?? {})).toEqual(['vm2']);
    expect(deps.installBinaryAt).not.toHaveBeenCalled();
    expect(deps.relicense).not.toHaveBeenCalled();
    expect(out.warn).toHaveBeenCalledWith(
      expect.stringContaining('rdc preview leave --machine vm2')
    );

    // --machine finishes the one that was left, then the overlay goes and the switched servers are re-licensed.
    const finish = leaveDeps();
    const done = await leavePreviewFlow({ machine: 'vm2' }, finish, CONFIG);
    expect(finish.switchBack).toHaveBeenCalledTimes(1);
    expect(done.left).toBe(true);
    expect(finish.relicense).toHaveBeenCalledWith(['vm2']);
    expect(readPreviewOverlay(CONFIG)).toBeUndefined();
  });

  it('moves nothing when the touched list is not confirmed, and refuses a machine that was never touched', async () => {
    await recordPreviewTouch('vm1', touched, CONFIG);
    const declined = leaveDeps({ confirm: vi.fn(() => Promise.resolve(false)) });
    await expect(leavePreviewFlow({}, declined, CONFIG)).rejects.toThrow(/was not confirmed/);
    expect(declined.switchBack).not.toHaveBeenCalled();
    expect(readPreviewOverlay(CONFIG)?.touched).toBeDefined();

    const other = leaveDeps();
    await expect(leavePreviewFlow({ machine: 'vm9' }, other, CONFIG)).rejects.toThrow(
      /vm9 is not on the renet/
    );
    expect(other.switchBack).not.toHaveBeenCalled();
    // The list shown to the operator names each server with its recorded and current renet version.
    const shown = out.info.mock.calls.map((c) => String(c[0])).join('\n');
    expect(shown).toContain('vm1: renet v1.4.0-preview.abc1234 now, v1.3.9 before the preview');
  });

  it('never switches a server back when none was touched', async () => {
    const deps = leaveDeps();
    await leavePreviewFlow({}, deps, CONFIG);
    expect(deps.switchBack).not.toHaveBeenCalled();
    expect(deps.confirm).not.toHaveBeenCalled();
  });

  it('is a no-op outside a preview', async () => {
    await leavePreviewFlow({}, leaveDeps(), CONFIG);
    const deps = leaveDeps();
    const result = await leavePreviewFlow({}, deps, CONFIG);
    expect(result).toEqual({ left: false, switched: [], remaining: [] });
    expect(deps.installBinaryAt).not.toHaveBeenCalled();
  });
});

describe('the preview banner and status', () => {
  const overlay = {
    name: NAME,
    host: `https://${NAME}.rediacc.workers.dev`,
    enteredAt: '2026-11-23T10:00:00.000Z',
    channel: NAME,
    licenceEndsAt: '2026-11-30T10:00:00.000Z',
    previous: { cliVersion: '1.3.9', cliSha256: KEPT_SHA },
  };

  it('is silent outside a preview and one line inside it', () => {
    expect(previewBanner(undefined, 'https://x')).toBeUndefined();
    const banner = previewBanner(overlay, 'https://x', new Date('2026-11-24T00:00:00Z'));
    expect(banner).toContain(NAME);
    expect(banner).toContain('2026-11-30');
    expect(banner).toContain('rdc preview leave');
    expect(banner?.split('\n')).toHaveLength(1);
  });

  it('adds the expiry message once fewer than 2 days of licence remain', () => {
    const banner = previewBanner(overlay, 'https://real', new Date('2026-11-29T12:00:00Z'));
    expect(banner?.split('\n')).toHaveLength(2);
    expect(banner).toContain('running apps keep running');
    expect(banner).toContain('https://real');
  });

  it('lists the touched servers and the emergency exit in status', () => {
    const lines = previewStatusLines(
      { ...overlay, touched: { vm1: touched } },
      'https://real',
      KEPT_PATH
    ).join('\n');
    expect(lines).toContain('vm1');
    expect(lines).toContain(`${KEPT_PATH} preview leave`);
  });
});
