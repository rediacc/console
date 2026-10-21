import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockFetchServerInfo, mockUpdateConfigAtPointer, mockExists, mockWarn, mockInfo } =
  vi.hoisted(() => ({
    mockFetchServerInfo: vi.fn(),
    mockUpdateConfigAtPointer: vi.fn(),
    mockExists: vi.fn(),
    mockWarn: vi.fn(),
    mockInfo: vi.fn(),
  }));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: vi.fn(),
  fetchServerInfo: mockFetchServerInfo,
}));
vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: () => ({}),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  deleteStoredSubscriptionToken: vi.fn(),
  getSubscriptionScopeMismatch: vi.fn(),
  getSubscriptionServerUrl: () => 'http://gateway.test:4800',
  normalizeServerUrl: (s: string) => s,
  saveStoredSubscriptionToken: vi.fn(),
}));
vi.mock('../../services/config/config-name.js', () => ({ getEffectiveConfigName: () => 'drill' }));
vi.mock('../../services/config/synced-write.js', () => ({
  updateConfigAtPointer: mockUpdateConfigAtPointer,
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists: mockExists, setRemoteStateWriter: vi.fn() },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: mockInfo, warn: mockWarn, success: vi.fn(), error: vi.fn() },
}));

import { resolveAndSyncServer } from '../subscription.js';

const INFO = { updateChannel: 'stable', e2e: { keys: [{ publicKeySpki: 'DEV-KEY' }] } };

function writtenPointers(): string[] {
  return mockUpdateConfigAtPointer.mock.calls.map((call) => call[1] as string);
}

describe('resolveAndSyncServer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExists.mockResolvedValue(true);
    mockUpdateConfigAtPointer.mockResolvedValue(undefined);
    mockFetchServerInfo.mockResolvedValue(INFO);
  });

  it('persists the server, the channel and the e2e key from server-info', async () => {
    await expect(resolveAndSyncServer({})).resolves.toBe('http://gateway.test:4800');
    expect(writtenPointers()).toEqual([
      '/account/accountServer',
      '/account/updateChannel',
      '/account/e2ePublicKey',
    ]);
  });

  it('fails the login when the e2e key cannot be persisted, rather than falling back to the production key', async () => {
    mockUpdateConfigAtPointer.mockImplementation((_name: string, pointer: string) =>
      pointer === '/account/e2ePublicKey'
        ? Promise.reject(new Error('lock timeout on drill.json'))
        : Promise.resolve()
    );
    await expect(resolveAndSyncServer({})).rejects.toThrow('lock timeout on drill.json');
  });

  it('keeps going, and says so, when server-info cannot be fetched', async () => {
    mockFetchServerInfo.mockRejectedValue(new Error('offline'));
    await expect(resolveAndSyncServer({})).resolves.toBe('http://gateway.test:4800');
    expect(writtenPointers()).toEqual(['/account/accountServer']);
    expect(mockWarn).toHaveBeenCalledWith(
      'server-info unreachable at http://gateway.test:4800; the saved channel and e2e key are kept: offline'
    );
  });

  it('saves the channel and skips the key when server-info carries no e2e block', async () => {
    mockFetchServerInfo.mockResolvedValue({ updateChannel: 'stable' });
    await expect(resolveAndSyncServer({})).resolves.toBe('http://gateway.test:4800');
    expect(writtenPointers()).toEqual(['/account/accountServer', '/account/updateChannel']);
  });

  it('warns and continues when only the synced channel cannot be saved', async () => {
    mockUpdateConfigAtPointer.mockImplementation((_name: string, pointer: string) =>
      pointer === '/account/updateChannel'
        ? Promise.reject(new Error('remote config offline'))
        : Promise.resolve()
    );
    await expect(resolveAndSyncServer({})).resolves.toBe('http://gateway.test:4800');
    expect(mockWarn).toHaveBeenCalledWith('update channel not saved: remote config offline');
    expect(writtenPointers()).toContain('/account/e2ePublicKey');
  });

  it('keeps the cause of a rejection that is not an Error in both warnings', async () => {
    mockFetchServerInfo.mockRejectedValueOnce('socket hang up');
    await resolveAndSyncServer({});
    expect(mockWarn).toHaveBeenCalledWith(
      'server-info unreachable at http://gateway.test:4800; the saved channel and e2e key are kept: socket hang up'
    );
    mockUpdateConfigAtPointer.mockImplementation((_name: string, pointer: string) =>
      pointer === '/account/updateChannel' ? Promise.reject('quota') : Promise.resolve()
    );
    await resolveAndSyncServer({});
    expect(mockWarn).toHaveBeenCalledWith('update channel not saved: quota');
  });

  it('skips the writes for a config that does not exist yet', async () => {
    mockExists.mockResolvedValue(false);
    await expect(resolveAndSyncServer({})).resolves.toBe('http://gateway.test:4800');
    expect(mockUpdateConfigAtPointer).not.toHaveBeenCalled();
  });
  it('drops the saved e2e key in the same write that moves the config to another server', async () => {
    mockFetchServerInfo.mockRejectedValue(new Error('offline'));
    await resolveAndSyncServer({});
    const [, pointer, edit] = mockUpdateConfigAtPointer.mock.calls[0] as [
      string,
      string,
      (cfg: { account?: Record<string, unknown> }) => { account?: Record<string, unknown> },
    ];
    expect(pointer).toBe('/account/accountServer');

    const moved = edit({
      account: { accountServer: 'https://eu.example.com', e2ePublicKey: 'EU-KEY' },
    });
    expect(moved.account).toEqual({ accountServer: 'http://gateway.test:4800' });

    const same = edit({
      account: { accountServer: 'http://gateway.test:4800', e2ePublicKey: 'DEV-KEY' },
    });
    expect(same.account).toEqual({
      accountServer: 'http://gateway.test:4800',
      e2ePublicKey: 'DEV-KEY',
    });
  });
});
