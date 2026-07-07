import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../services/config/config-resources.js';
import { localExecutorService } from '../../services/executor/local-executor.js';
import { executeRepoFunction } from '../repo-executor.js';

afterEach(() => vi.restoreAllMocks());

const msgs = { starting: 's', completed: 'c', failed: 'f' };

describe('executeRepoFunction threads the cluster target into execute()', () => {
  it('passes kubeCluster + the resolved control-node machine to localExecutorService.execute', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(configService, 'ensureRepositoryNetworkId').mockResolvedValue(undefined as never);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await executeRepoFunction(
      'repository_up',
      'shop',
      'prod-k8s-1',
      { foo: 'bar' },
      { kubeCluster: 'prod', debug: true },
      msgs
    );

    expect(exec).toHaveBeenCalledTimes(1);
    const arg = exec.mock.calls[0][0];
    expect(arg.functionName).toBe('repository_up');
    expect(arg.machineName).toBe('prod-k8s-1');
    expect(arg.kubeCluster).toBe('prod');
    expect(arg.params).toMatchObject({ repository: 'shop', foo: 'bar' });
  });

  it('leaves kubeCluster undefined for a plain machine target', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(configService, 'ensureRepositoryNetworkId').mockResolvedValue(undefined as never);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await executeRepoFunction('repository_status', 'shop', 'server-1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].kubeCluster).toBeUndefined();
    expect(exec.mock.calls[0][0].machineName).toBe('server-1');
  });
});
