/**
 * A `secret-tool lookup` that hits its time limit (a locked keyring waiting on a desktop prompt) is a failed read,
 * never an absent item: `null` would send deriveCek() through re-enrolment of a device whose key is stored
 * (review 0159ab0f.1). The tool is a stand-in behind a mocked execFileSync, so the limit can be hit without waiting it out.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const stand = vi.hoisted(() => ({
  items: new Map<string, string>(),
  hang: false,
}));

/** `lookup` of the stand-in: the stored text, exit 1 for an item never stored, and a timeout for the stored key while the keyring "hangs". The selection probe's own throwaway key always answers. */
function lookup(account: string): string {
  if (stand.hang && !account.startsWith('rdc:probe:')) {
    throw Object.assign(new Error('spawnSync secret-tool ETIMEDOUT'), { code: 'ETIMEDOUT' });
  }
  const found = stand.items.get(account);
  if (found === undefined) throw Object.assign(new Error('exit 1'), { status: 1 });
  return found;
}

vi.mock('node:child_process', () => ({
  execFileSync: (tool: string, args: string[], options: { input?: string }) => {
    if (tool !== 'secret-tool') throw Object.assign(new Error('not stubbed'), { code: 'ENOENT' });
    const [command, ...rest] = args;
    const account = rest[rest.indexOf('account') + 1];
    if (command === 'lookup') return lookup(account);
    if (command === 'store') stand.items.set(account, options.input ?? '');
    else stand.items.delete(account);
    return '';
  },
}));

const { getSecureStorage } = await import('../secure-storage.js');

const KEY = 'rdc:device-key';

describe('SecretToolStorage.read on a timed-out lookup (review 0159ab0f.1)', () => {
  beforeEach(() => {
    stand.items.clear();
    stand.hang = false;
    vi.stubEnv('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/nonexistent/bus');
    vi.stubEnv('REDIACC_SECRET_STORE', '');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.skipIf(process.platform !== 'linux')(
    'rejects instead of reporting the item absent, and an absent item still reads null',
    async () => {
      const storage = getSecureStorage();
      expect(storage.type).toBe('secret-service');
      await storage.set(KEY, 'the-secret');
      // Control: a stored item reads back, and one never stored is null.
      expect(await storage.get(KEY)).toBe('the-secret');
      expect(await storage.get('rdc:other')).toBeNull();

      stand.hang = true;
      await expect(storage.get(KEY)).rejects.toThrow(/timed out/);
    }
  );
});
