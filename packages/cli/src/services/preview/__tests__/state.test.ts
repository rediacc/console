import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../core/output.js', () => ({
  outputService: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

// The config dir is captured at module load (config-file-storage), so the scratch XDG_CONFIG_HOME is set before any import.
const configHome = mkdtempSync(join(tmpdir(), 'rdc-preview-state-'));
process.env.XDG_CONFIG_HOME = configHome;
const configDir = join(configHome, 'rediacc');

const { configFileStorage } = await import('../../../adapters/config-file-storage.js');
const { readAccountPointer, previewTokenFile } = await import('../../account/account-pointer.js');
const { setConfigNameOverride } = await import('../../config/config-name.js');
const {
  clearPreviewTouch,
  enterPreview,
  leavePreview,
  previewHostFor,
  readPreviewOverlay,
  recordPreviewTouch,
} = await import('../state.js');

const CONFIG = 'customer';
const NAME = 'pv-amber-river-stone';
const REAL_ACCOUNT = {
  userEmail: 'ops@example.com',
  accountServer: 'https://eu.rediacc.cloud',
  e2ePublicKey: 'MCowBQYDK2VuAyEAexamplekeyexamplekeyexamplekeyexamplekey=',
  updateChannel: 'stable',
  releasesUrl: 'https://releases.example.com/cli',
};
const REAL_TOKEN = JSON.stringify({ token: 'rdt_real', serverUrl: REAL_ACCOUNT.accountServer });

function configPath(): string {
  return join(configDir, `${CONFIG}.json`);
}

/** The exact text of the file's `account` member, braces included, as it sits on disk. */
function accountBytes(): string {
  const text = readFileSync(configPath(), 'utf8');
  const start = text.indexOf('"account": {');
  expect(start).toBeGreaterThanOrEqual(0);
  let depth = 0;
  for (let i = text.indexOf('{', start); i < text.length; i++) {
    if (text[i] === '{') depth++;
    if (text[i] === '}' && --depth === 0) return text.slice(start, i + 1);
  }
  throw new Error('unterminated account section');
}

function overlay(name = NAME) {
  return {
    name,
    host: previewHostFor(name),
    enteredAt: '2026-11-22T15:30:00.000Z',
    channel: name,
    previous: { cliVersion: '0.9.4', cliSha256: 'a'.repeat(64), updateChannel: 'stable' },
  };
}

const touch = {
  slot: '/usr/lib/rediacc/renet/0.9.4',
  version: '0.9.4',
  sha256: 'b'.repeat(64),
  touchedAt: '2026-11-22T15:31:00.000Z',
};

describe('preview overlay state', () => {
  beforeEach(async () => {
    rmSync(configDir, { recursive: true, force: true });
    mkdirSync(configDir, { recursive: true });
    writeFileSync(
      configPath(),
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-0000000000c1',
        version: 1,
        encryption: { mode: 'plaintext' },
        account: REAL_ACCOUNT,
      })
    );
    writeFileSync(join(configDir, `api-token-${CONFIG}.json`), REAL_TOKEN);
    configFileStorage.clearCache();
    setConfigNameOverride(CONFIG);
    // Normalize the file to the CLI's own serialization, so the before/after comparison is of bytes the CLI wrote.
    await configFileStorage.update(CONFIG, (c) => c);
  });

  afterAll(() => {
    setConfigNameOverride(null);
    rmSync(configHome, { recursive: true, force: true });
  });

  it('leaves the account section byte-identical from before use to after leave', async () => {
    const before = accountBytes();

    await enterPreview(overlay(), CONFIG);
    expect(accountBytes()).toBe(before);
    await recordPreviewTouch('vm1', touch, CONFIG);
    await clearPreviewTouch('vm1', CONFIG);
    expect(accountBytes()).toBe(before);

    const removed = await leavePreview(CONFIG, configDir);
    expect(removed?.name).toBe(NAME);
    expect(accountBytes()).toBe(before);
    expect(readPreviewOverlay(CONFIG, configDir)).toBeUndefined();
    expect(readFileSync(configPath(), 'utf8')).not.toContain('"preview"');
  });

  it('answers the preview host, channel and token file while the overlay exists', async () => {
    expect(readAccountPointer(CONFIG)).toEqual(REAL_ACCOUNT);

    await enterPreview(overlay(), CONFIG);
    const pointer = readAccountPointer(CONFIG);
    expect(pointer).toEqual({
      accountServer: `https://${NAME}.rediacc.workers.dev`,
      updateChannel: NAME,
      preview: NAME,
      tokenFile: join(configDir, `api-token-${CONFIG}.preview-${NAME}.json`),
    });
    // The real server's key and on-prem releases URL never leak into the preview.
    expect(pointer.e2ePublicKey).toBeUndefined();
    expect(pointer.releasesUrl).toBeUndefined();

    await leavePreview(CONFIG, configDir);
    expect(readAccountPointer(CONFIG)).toEqual(REAL_ACCOUNT);
  });

  it('passes the strict config parse with the overlay in place', async () => {
    await enterPreview(overlay(), CONFIG);
    configFileStorage.clearCache();
    const loaded = await configFileStorage.load(CONFIG);
    expect(loaded.preview?.name).toBe(NAME);
    expect(loaded.account).toEqual(REAL_ACCOUNT);
  });

  it('deletes the preview token on leave and never touches the real one', async () => {
    await enterPreview(overlay(), CONFIG);
    const tokenFile = previewTokenFile(CONFIG, NAME, configDir);
    writeFileSync(tokenFile, JSON.stringify({ token: 'rdt_preview', serverUrl: 'x' }));

    await leavePreview(CONFIG, configDir);
    expect(existsSync(tokenFile)).toBe(false);
    expect(readFileSync(join(configDir, `api-token-${CONFIG}.json`), 'utf8')).toBe(REAL_TOKEN);
  });

  it('refuses a name outside the preview namespace', async () => {
    await expect(enterPreview(overlay('pr-605'), CONFIG)).rejects.toThrow(/not a preview name/);
    await expect(enterPreview(overlay('pv-two-words'), CONFIG)).rejects.toThrow(
      /not a preview name/
    );
    expect(readPreviewOverlay(CONFIG, configDir)).toBeUndefined();
  });

  it('refuses a second use while on a preview', async () => {
    await enterPreview(overlay(), CONFIG);
    await expect(enterPreview(overlay('pv-other-blue-lake'), CONFIG)).rejects.toThrow(
      /already on preview pv-amber-river-stone/
    );
    expect(readPreviewOverlay(CONFIG, configDir)?.name).toBe(NAME);
  });

  it('records a server once and keeps its first slot', async () => {
    await enterPreview(overlay(), CONFIG);
    expect(await recordPreviewTouch('vm1', touch, CONFIG)).toBe(true);
    expect(
      await recordPreviewTouch('vm1', { ...touch, version: '0.9.5-preview.abc1234' }, CONFIG)
    ).toBe(false);
    expect(readPreviewOverlay(CONFIG, configDir)?.touched).toEqual({ vm1: touch });
  });

  it('records nothing when the config is not on a preview', async () => {
    expect(await recordPreviewTouch('vm1', touch, CONFIG)).toBe(false);
    expect(readPreviewOverlay(CONFIG, configDir)).toBeUndefined();
  });

  it('keeps the overlay while a touched server is not switched back', async () => {
    await enterPreview(overlay(), CONFIG);
    await recordPreviewTouch('vm1', touch, CONFIG);
    await recordPreviewTouch('vm2', touch, CONFIG);

    await expect(leavePreview(CONFIG, configDir)).rejects.toThrow(/2 server\(s\).*vm1, vm2/);
    expect(readPreviewOverlay(CONFIG, configDir)?.name).toBe(NAME);

    await clearPreviewTouch('vm1', CONFIG);
    await clearPreviewTouch('vm2', CONFIG);
    expect(readPreviewOverlay(CONFIG, configDir)?.touched).toBeUndefined();
    expect((await leavePreview(CONFIG, configDir))?.name).toBe(NAME);
  });

  it('leaves a config that is not on a preview unchanged', async () => {
    const before = accountBytes();
    expect(await leavePreview(CONFIG, configDir)).toBeUndefined();
    expect(accountBytes()).toBe(before);
  });
});
