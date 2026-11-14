import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  configName: 'eu-edge-asia',
  accountServer: undefined as string | undefined,
  exists: vi.fn(),
  update: vi.fn(),
  saveToken: vi.fn(),
  authorize: vi.fn(),
  discover: vi.fn(),
  promptRegion: vi.fn(),
  fetchServerInfo: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, string>) => (vars?.name ? `${key}:${vars.name}` : key),
}));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: vi.fn(),
  fetchServerInfo: h.fetchServerInfo,
}));
vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: () => ({ accountServer: h.accountServer }),
}));
vi.mock('../../services/account/subscription-auth.js', async () => {
  const { WK_ACCOUNT_DEFAULT_ORIGIN: fallback } = await import(
    '@rediacc/shared/config/well-known.generated'
  );
  return {
    deleteStoredSubscriptionToken: vi.fn(),
    getSubscriptionScopeMismatch: vi.fn(),
    getSubscriptionServerUrl: (preferred?: string) => preferred ?? h.accountServer ?? fallback,
    normalizeServerUrl: (s: string) => s,
    saveStoredSubscriptionToken: h.saveToken,
  };
});
vi.mock('../../services/account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: h.authorize,
}));
vi.mock('../../services/config/config-name.js', () => ({
  getEffectiveConfigName: () => h.configName,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getTeam: async () => undefined },
}));
vi.mock('../../services/config/synced-write.js', () => ({ updateConfigAtPointer: h.update }));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists: h.exists, setRemoteStateWriter: vi.fn() },
}));
vi.mock('../../services/provision/region-discovery.js', () => ({ discoverRegions: h.discover }));
vi.mock('../../utils/region-prompt.js', () => ({ promptRegionSelection: h.promptRegion }));
vi.mock('../../utils/spinner.js', () => ({
  withSpinner: (_label: string, fn: () => unknown) => fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), warn: vi.fn(), success: vi.fn(), error: vi.fn() },
}));
vi.mock('../subscription-output.js', () => ({ outputSubscriptionScope: vi.fn() }));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

import { registerSubscriptionCommands } from '../subscription.js';

async function run(...args: string[]): Promise<void> {
  const program = new Command();
  registerSubscriptionCommands(program);
  await program.parseAsync(['node', 'rdc', 'subscription', ...args]);
}

const ASIA_REGION = BAKED_IN_REGIONS.find((r) => r.id === 'asia');
if (!ASIA_REGION) throw new Error('regions.json has no asia region');
const ASIA = { region: { label: ASIA_REGION.label }, domain: ASIA_REGION.domain };
const ASIA_ORIGIN = `https://${ASIA_REGION.domain}`;

describe('subscription login/register on a config that does not exist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.configName = 'eu-edge-asia';
    h.accountServer = undefined;
    h.exists.mockResolvedValue(false);
    h.discover.mockResolvedValue([]);
    h.promptRegion.mockResolvedValue(ASIA);
    h.fetchServerInfo.mockResolvedValue({});
    h.update.mockImplementation((_n: string, pointer: string, edit: (c: object) => object) => {
      if (pointer === '/account/accountServer') {
        h.accountServer = (
          edit({}) as { account: { accountServer: string } }
        ).account.accountServer;
      }
      return Promise.resolve();
    });
    h.authorize.mockResolvedValue({
      status: { subscriptionId: 's', planCode: 'p', teamName: 'team', machines: [] },
      terms: { accepted: '1' },
    });
  });

  it('login refuses a missing named config: no prompt, no network, no token', async () => {
    await expect(run('login')).rejects.toThrow('errors.config.missingNamed:eu-edge-asia');
    expect(h.discover).not.toHaveBeenCalled();
    expect(h.promptRegion).not.toHaveBeenCalled();
    expect(h.fetchServerInfo).not.toHaveBeenCalled();
    expect(h.authorize).not.toHaveBeenCalled();
    expect(h.saveToken).not.toHaveBeenCalled();
    expect(h.update).not.toHaveBeenCalled();
  });

  it('login with --server and --token refuses the same way', async () => {
    await expect(run('login', '--server', ASIA_ORIGIN, '--token', 'x')).rejects.toThrow(
      'errors.config.missingNamed:eu-edge-asia'
    );
    expect(h.update).not.toHaveBeenCalled();
    expect(h.saveToken).not.toHaveBeenCalled();
  });

  it('register refuses a missing named config: no prompt, no network, no token', async () => {
    await expect(run('register', '--email', 'a@b.co')).rejects.toThrow(
      'errors.config.missingNamed:eu-edge-asia'
    );
    expect(h.promptRegion).not.toHaveBeenCalled();
    expect(h.fetchServerInfo).not.toHaveBeenCalled();
    expect(h.authorize).not.toHaveBeenCalled();
    expect(h.saveToken).not.toHaveBeenCalled();
    expect(h.update).not.toHaveBeenCalled();
  });

  it('control: an existing named config proceeds and the chosen region becomes the server', async () => {
    h.exists.mockResolvedValue(true);
    await run('login');
    expect(h.promptRegion).toHaveBeenCalledTimes(1);
    expect(h.authorize.mock.calls[0][0]).toBe(ASIA_ORIGIN);
  });

  it('control: the default config (auto-created) is never refused', async () => {
    h.configName = 'rediacc';
    await run('login');
    expect(h.promptRegion).toHaveBeenCalledTimes(1);
  });
});
