import { beforeEach, describe, expect, it, vi } from 'vitest';

// R2: reading never writes. `config remote status|versions` are driven through the real command tree; every other read verb (machine status/list, repo list, config show, backup status, subscription status) reads through RemoteResourceState's getters and configService, so those are proven at that entry point: the read surface is exercised against a RemoteConfigAdapter whose push is a spy, and none may call it.

const { push, storage, mockService } = vi.hoisted(() => ({
  push: vi.fn(),
  storage: {
    load: vi.fn(),
    loadDecrypted: vi.fn(),
    updateCache: vi.fn(),
    update: vi.fn(),
    save: vi.fn(),
  },
  mockService: {
    getEffectiveConfigName: () => 'ro',
    getActiveRemoteAdapter: vi.fn(),
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({ configFileStorage: storage }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: mockService }));
// `config remote status` asks for the device's secure storage; the host's keyring is not what this test is about, and a CI runner may have none.
vi.mock('../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: vi.fn(), info: vi.fn(), error: vi.fn(), warn: vi.fn(), success: vi.fn() },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/errors.js')>();
  return {
    ...actual,
    handleError: vi.fn((e: unknown) => {
      throw e instanceof Error ? e : new Error(String(e));
    }),
  };
});

const remote = {
  apiUrl: 'https://account.example.com',
  storeId: '11111111-1111-4111-8111-111111111111',
  configId: '22222222-2222-4222-8222-222222222222',
  storageKeyId: 'rdc:pk:key-1',
};
const doc = {
  schemaVersion: 3,
  id: 'cfg-id',
  version: 1,
  remote,
  resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } }, repositories: {} },
};

const { Command } = await import('commander');
const { registerConfigCommands } = await import('../config.js');
const { RemoteResourceState } = await import('../../services/config/resource-state.js');

function adapter() {
  return {
    push,
    pull: vi.fn().mockResolvedValue({ config: doc, version: 1, sdkEpoch: 1 }),
    testConnection: vi.fn().mockResolvedValue(true),
    listVersions: vi.fn().mockResolvedValue([{ version: 1, archivedAt: 't', sdkEpoch: 1 }]),
    pullVersion: vi.fn().mockResolvedValue({ config: doc, version: 1 }),
  };
}

describe('read-only verbs never push', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storage.load.mockResolvedValue(structuredClone(doc));
    storage.loadDecrypted.mockResolvedValue(structuredClone(doc));
    mockService.getActiveRemoteAdapter.mockResolvedValue(adapter());
  });

  async function run(...argv: string[]) {
    const program = new Command();
    program.option('-o, --output <format>', 'format', 'table');
    registerConfigCommands(program);
    await program.parseAsync(argv, { from: 'user' });
  }

  it.each([
    [['config', 'remote', 'status']],
    [['config', 'remote', 'versions']],
    [['config', 'remote', 'versions', '--explain']],
  ])('config %j', async (argv) => {
    await run(...argv);
    expect(push).not.toHaveBeenCalled();
    expect(storage.update).not.toHaveBeenCalled();
  });

  it('the state read surface behind machine/repo/backup/subscription reads pushes nothing', async () => {
    const state = RemoteResourceState.load(
      structuredClone(doc) as never,
      'ro',
      adapter() as never,
      1,
      1
    );
    state.getMachines();
    state.getRepositories();
    state.getDeletedRepositories();
    state.getSSH();
    // A write that changes nothing is a read as far as the server is concerned.
    await state.setMachines({ m1: { ip: '10.0.0.1', user: 'root' } });
    await state.setRepositories({});
    expect(push).not.toHaveBeenCalled();
  });
});
