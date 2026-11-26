/**
 * `repo create` rolls the registration back only on a definitive failure (review 9a8dc910.2): a timeout or lost
 * connection on the dispatch keeps the entry, a refused start removes it. Both create forms (--machine and
 * --datastore) are driven through their catch; reverting either to a direct rollback fails the timeout test.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { RdcConfig, RepositoryConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../services/executor/types.js';

const execute = vi.fn((_options: ExecuteOptions): Promise<unknown> => Promise.resolve({}));
const registered: { guid?: string } = {};
const addRepository = vi.fn((_name: string, config: RepositoryConfig) => {
  registered.guid = config.repositoryGuid;
  return Promise.resolve();
});
const removeRepository = vi.fn(() => Promise.resolve());
const getCurrent = vi.fn<() => Promise<RdcConfig>>();

vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute }),
  requestNetworkIdAuto: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    // A duplicate check sees nothing; the rollback check then sees the repo this create registered.
    getRepository: vi.fn(() =>
      Promise.resolve(registered.guid ? { repositoryGuid: registered.guid } : undefined)
    ),
    getLiveGrand: vi.fn(() => Promise.resolve(undefined)),
    allocateNetworkId: vi.fn(() => Promise.resolve(42)),
    removeRepository: () => removeRepository(),
    getCurrent: () => getCurrent(),
    addRepository: (name: string, config: RepositoryConfig) => addRepository(name, config),
    getRepositoryKey: (name: string) => Promise.resolve(`${name}:latest`),
    getResourceState: () =>
      Promise.resolve({ getRepositories: () => ({}), setRepositories: () => Promise.resolve() }),
  },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/agent-guard.js', () => ({ assertAgentRepoCreate: vi.fn() }));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn(() => Promise.resolve()) }));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/cluster/cluster-target.js', () => ({
  namedDatastoreMount: (d: string) => `/mnt/rediacc-ds/${d}`,
  clusterMountRemotePath: (c: string) => `/mnt/${c}`,
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: vi.fn(),
}));

import { setCommandJobDeps } from '../../services/jobs/command-job.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { handleRepoCreate } from '../repo-create-delete.js';

let ticketDir: string;
beforeEach(() => {
  vi.clearAllMocks();
  registered.guid = undefined;
  ticketDir = mkdtempSync(join(tmpdir(), 'repo-create-rollback-'));
  setCommandJobDeps({
    store: () => new TicketStore('test', ticketDir),
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
  getCurrent.mockResolvedValue({
    resources: {
      machines: {},
      datastores: { data1: { backend: { kind: 'rbd', pool: 'rbd', image: 'data1' } } },
    },
    state: { datastores: { data1: { attachedTo: 'm2' } } },
  } as unknown as RdcConfig);
});
afterEach(() => {
  setCommandJobDeps();
  rmSync(ticketDir, { recursive: true, force: true });
});

const timeout = () =>
  new CliExitError(ERROR_CODES.NETWORK_ERROR, 'proxy timed out', { retryable: true });

const forms: [string, () => Promise<void>][] = [
  ['--machine', () => handleRepoCreate('shop', { machine: 'm1', size: '5G' })],
  ['--datastore', () => handleRepoCreate('shop', { datastore: 'data1', size: '5G' })],
];

describe.each(forms)('repo create %s', (_label, run) => {
  it('keeps the registration when the dispatch times out', async () => {
    execute.mockRejectedValue(timeout());
    await run();
    expect(addRepository).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalled();
    expect(removeRepository).not.toHaveBeenCalled();
  });

  it('removes the registration when the start is refused (control)', async () => {
    execute.mockRejectedValue(new Error('refused'));
    await run();
    expect(addRepository).toHaveBeenCalledTimes(1);
    expect(removeRepository).toHaveBeenCalledTimes(1);
  });
});
