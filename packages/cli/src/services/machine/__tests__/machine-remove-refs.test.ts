/** `machine remove` reference checks: cluster member, datastore-routed repos, bound strategies. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RepositoryConfig } from '../../../types/index.js';
import { CliExitError } from '../../../utils/cli-exit-error.js';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const m = vi.hoisted(() => ({ listRepositories: vi.fn(), getCurrent: vi.fn(), warn: vi.fn() }));
vi.mock('../../config/config-resources.js', () => ({
  configService: { listRepositories: m.listRepositories, getCurrent: m.getCurrent },
}));
vi.mock('../../core/output.js', () => ({ outputService: { warn: m.warn } }));

import { guardMachineRemoval } from '../machine-remove-guard.js';

const GUID = '00000000-0000-0000-0000-000000000000';
function repo(name: string, placement?: RepositoryConfig['placement']) {
  return { name, config: { repositoryGuid: GUID, placement } as RepositoryConfig };
}

function config(over: {
  machine?: Record<string, unknown>;
  attached?: Record<string, { attachedTo?: string }>;
}) {
  return {
    resources: { machines: { m1: { ip: '1.1.1.1', user: 'u', ...over.machine } } },
    state: { datastores: over.attached ?? {} },
  };
}

async function thrown(p: Promise<void>): Promise<CliExitError> {
  return (await p.then(
    () => undefined,
    (e: unknown) => e
  )) as CliExitError;
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listRepositories.mockResolvedValue([]);
  m.getCurrent.mockResolvedValue(config({}));
});

describe('machine remove references', () => {
  it('refuses a cluster member and points to the cluster verb, even with --force', async () => {
    m.getCurrent.mockResolvedValue(config({ machine: { cluster: { cluster: 'c1', pool: 'p' } } }));
    const err = await thrown(guardMachineRemoval('m1', true));
    expect(err.exitCode).toBe(12);
    expect(err.next?.options?.map((o) => o.run)).toContain('rdc cluster evict m1');
  });

  it('refuses repos on a datastore attached to the machine; --force warns and proceeds', async () => {
    m.getCurrent.mockResolvedValue(config({ attached: { ds1: { attachedTo: 'm1' } } }));
    m.listRepositories.mockResolvedValue([
      repo('web', { datastore: 'ds1' }),
      repo('other', { datastore: 'ds2' }),
    ]);
    const err = await thrown(guardMachineRemoval('m1', false));
    expect(err.exitCode).toBe(12);
    expect(err.details).toEqual(['web']);
    await expect(guardMachineRemoval('m1', true)).resolves.toBeUndefined();
    expect(m.warn).toHaveBeenCalledOnce();
  });

  it('refuses while strategies are bound; --force warns naming them', async () => {
    m.getCurrent.mockResolvedValue(
      config({ machine: { backupStrategies: ['nightly', 'weekly'] } })
    );
    const err = await thrown(guardMachineRemoval('m1', false));
    expect(err.exitCode).toBe(12);
    expect(err.details).toEqual(['nightly', 'weekly']);
    await expect(guardMachineRemoval('m1', true)).resolves.toBeUndefined();
    expect(String(m.warn.mock.calls[0][0])).toContain('nightly, weekly');
  });

  it('is silent when nothing references the machine', async () => {
    await expect(guardMachineRemoval('m1', false)).resolves.toBeUndefined();
    expect(m.warn).not.toHaveBeenCalled();
  });
});
