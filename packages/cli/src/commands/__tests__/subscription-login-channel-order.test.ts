import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  events: [] as string[],
  fetchServerInfo: vi.fn(),
  update: vi.fn(),
  authorize: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  exists: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: vi.fn(),
  fetchServerInfo: h.fetchServerInfo,
}));
vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: () => ({ accountServer: 'http://gateway.test:4800' }),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  deleteStoredSubscriptionToken: vi.fn(),
  getSubscriptionScopeMismatch: vi.fn(),
  getSubscriptionServerUrl: () => 'http://gateway.test:4800',
  normalizeServerUrl: (s: string) => s,
  saveStoredSubscriptionToken: vi.fn(),
}));
vi.mock('../../services/account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: h.authorize,
}));
vi.mock('../../services/config/config-name.js', () => ({ getEffectiveConfigName: () => 'drill' }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getTeam: async () => undefined },
}));
vi.mock('../../services/config/synced-write.js', () => ({ updateConfigAtPointer: h.update }));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists: h.exists, setRemoteStateWriter: vi.fn() },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: h.info, warn: h.warn, success: vi.fn(), error: vi.fn() },
}));
vi.mock('../subscription-output.js', () => ({ outputSubscriptionScope: vi.fn() }));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

import { registerSubscriptionCommands } from '../subscription.js';

async function runCommand(...args: string[]): Promise<void> {
  const program = new Command();
  registerSubscriptionCommands(program);
  await program.parseAsync(['node', 'rdc', 'subscription', ...args]);
}

const runLogin = () => runCommand('login');

function channelAnnouncements(): number {
  return h.info.mock.calls.filter((c) => c[0] === 'commands.subscription.login.channelSynced')
    .length;
}

describe('subscription login: the update channel is written after the new token', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.events.length = 0;
    h.exists.mockResolvedValue(true);
    h.fetchServerInfo.mockResolvedValue({ updateChannel: 'edge' });
    h.update.mockImplementation((_n: string, pointer: string) => {
      h.events.push(`write:${pointer}`);
      return Promise.resolve();
    });
    h.authorize.mockImplementation(() => {
      h.events.push('device-flow');
      return Promise.resolve({
        status: { subscriptionId: 's', planCode: 'p', teamName: 'team', machines: [] },
        terms: { accepted: '1' },
      });
    });
  });

  it('runs no channel write before the device flow, and exactly one after it', async () => {
    await runLogin();
    const flow = h.events.indexOf('device-flow');
    expect(flow).toBeGreaterThanOrEqual(0);
    expect(h.events.slice(0, flow)).not.toContain('write:/account/updateChannel');
    expect(h.events.filter((e) => e === 'write:/account/updateChannel')).toHaveLength(1);
    expect(h.events.indexOf('write:/account/updateChannel')).toBeGreaterThan(flow);
  });

  it('does not announce the channel when the write was dropped', async () => {
    h.update.mockImplementation((_n: string, pointer: string) =>
      pointer === '/account/updateChannel'
        ? Promise.reject(new Error('Lock file is already being held'))
        : Promise.resolve()
    );
    await runLogin();
    expect(h.warn).toHaveBeenCalledWith(
      'update channel not saved: Lock file is already being held'
    );
    expect(channelAnnouncements()).toBe(0);
  });

  it('control: a landed write is announced once and nothing is warned', async () => {
    await runLogin();
    expect(channelAnnouncements()).toBe(1);
    expect(h.warn).not.toHaveBeenCalled();
  });

  it('a failed device flow leaves the update channel unwritten (the channel follows a good login only)', async () => {
    h.authorize.mockRejectedValue(new Error('device flow cancelled'));
    await expect(runLogin()).rejects.toThrow('device flow cancelled');
    expect(h.events).not.toContain('write:/account/updateChannel');
    expect(channelAnnouncements()).toBe(0);
  });

  it('says so when the channel is not saved because the config does not exist yet', async () => {
    h.exists.mockResolvedValue(false);
    await runLogin();
    expect(h.warn).toHaveBeenCalledWith(
      'update channel not saved: config "drill" does not exist yet'
    );
    expect(channelAnnouncements()).toBe(0);
  });

  it('register refuses a malformed email before any server work', async () => {
    await expect(runCommand('register', '--email', 'not-an-email')).rejects.toThrow(
      'commands.subscription.register.invalidEmail'
    );
    expect(h.fetchServerInfo).not.toHaveBeenCalled();
    expect(h.authorize).not.toHaveBeenCalled();
  });

  it('register passes a valid email to the device flow', async () => {
    await runCommand('register', '--email', 'a@b.co');
    expect(h.authorize.mock.calls[0][1]).toMatchObject({ email: 'a@b.co' });
  });

  describe('the login summary terms line', () => {
    const summaryFor = async (terms: Record<string, unknown>) => {
      h.authorize.mockResolvedValue({
        status: { subscriptionId: 's', planCode: 'p', teamName: 'team', machines: [] },
        terms,
      });
      await runLogin();
      return h.info.mock.calls.map((c) => String(c[0]));
    };

    it('prints the accepted version', async () => {
      expect(await summaryFor({ accepted: '2026-11-11', url: 'u' })).toContain(
        'commands.subscription.login.termsAccepted'
      );
    });

    it('prints the accept-at URL when acceptance is pending with one', async () => {
      expect(await summaryFor({ url: 'u', acceptUrl: 'a' })).toContain(
        'commands.subscription.login.termsPendingAccept'
      );
    });

    it('prints the plain pending line when there is no accept URL', async () => {
      const lines = await summaryFor({ url: 'u' });
      expect(lines).toContain('commands.subscription.login.termsPending');
      expect(lines).not.toContain('commands.subscription.login.termsPendingAccept');
    });
  });
});
