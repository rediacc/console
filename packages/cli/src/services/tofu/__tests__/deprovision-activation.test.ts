import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  tokenKind: 'ready',
  readId: vi.fn(),
  fetch: vi.fn(),
  warn: vi.fn(),
  destroy: vi.fn(),
  order: [] as string[],
}));

vi.mock('node:fs', () => ({ existsSync: () => true }));
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: h.fetch }));
vi.mock('../../account/license-machine.js', () => ({ readRemoteMachineId: h.readId }));
vi.mock('../../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: h.tokenKind }),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: async () => ({
      sshPrivateKey: 'key',
      ssh: {},
      machines: { box: { ip: '1.2.3.4', user: 'u', port: 22 } },
    }),
    removeMachine: vi.fn(),
  },
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), warn: h.warn, success: vi.fn() },
}));
vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: async () => ({ sftp: {}, release: () => undefined }),
  },
}));
vi.mock('../../provision/infra-provision.js', () => ({
  pushInfraConfig: vi.fn(),
  removeMachineDnsRecords: vi.fn(async () => 0),
}));
vi.mock('../../renet/machine-bootstrap.js', () => ({}));
vi.mock('../../renet/renet-execution.js', () => ({ readSSHKey: vi.fn() }));
vi.mock('../executor.js', () => ({
  TofuExecutor: class {
    destroy = h.destroy;
    cleanup = vi.fn();
    static resolveBinary = vi.fn();
  },
}));

import { destroyCloudMachine } from '../provision.js';

const ID = 'b'.repeat(64);

describe('destroyCloudMachine releases the account activation slot', () => {
  beforeEach(() => {
    h.tokenKind = 'ready';
    h.order.length = 0;
    h.readId.mockReset().mockImplementation(() => {
      h.order.push('read');
      return Promise.resolve(ID);
    });
    h.fetch.mockReset().mockImplementation(() => {
      h.order.push('fetch');
      return Promise.resolve({ machineId: ID, deactivated: true });
    });
    h.destroy.mockReset().mockImplementation(() => {
      h.order.push('destroy');
      return Promise.resolve();
    });
    h.warn.mockClear();
  });

  it('reads the id before destroy and deactivates after it', async () => {
    await destroyCloudMachine('box');
    expect(h.order).toEqual(['read', 'destroy', 'fetch']);
    expect(h.fetch).toHaveBeenCalledWith(`/account/api/v1/licenses/machines/${ID}/deactivate`, {
      method: 'POST',
    });
    expect(h.warn).not.toHaveBeenCalled();
  });

  it('treats a 404 not-activated as done', async () => {
    h.fetch.mockRejectedValue(
      Object.assign(new Error('Machine is not activated'), { status: 404, code: 'NOT_FOUND' })
    );
    await destroyCloudMachine('box');
    expect(h.warn).not.toHaveBeenCalled();
  });

  it('warns on a code-less 404: the server lacks the route, the slot stays held', async () => {
    h.fetch.mockRejectedValue(
      Object.assign(
        new Error('Account server returned HTTP 404 with a non-JSON body: 404 Not Found'),
        {
          status: 404,
        }
      )
    );
    await destroyCloudMachine('box');
    expect(h.warn).toHaveBeenCalledTimes(1);
  });

  it('warns on any other failure and the deprovision still succeeds', async () => {
    h.fetch.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    await expect(destroyCloudMachine('box')).resolves.toBeUndefined();
    expect(h.warn).toHaveBeenCalledTimes(1);
    expect(String(h.warn.mock.calls[0][0])).toContain('boom');
  });

  it('skips the call when the id cannot be read', async () => {
    h.readId.mockRejectedValue(new Error('ssh down'));
    await destroyCloudMachine('box');
    expect(h.fetch).not.toHaveBeenCalled();
  });

  it('skips the call when no account token exists (no activation was made)', async () => {
    h.tokenKind = 'none';
    await destroyCloudMachine('box');
    expect(h.readId).not.toHaveBeenCalled();
    expect(h.fetch).not.toHaveBeenCalled();
  });
});
