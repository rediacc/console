import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  resolveRepoRefLocal: vi.fn(),
  getRepository: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../utils/repo-ref-local.js', () => ({ resolveRepoRefLocal: m.resolveRepoRefLocal }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: m.getRepository },
}));

import { configRepo } from '../incident.js';

beforeEach(() => vi.resetAllMocks());

describe('incident declare repository lookup', () => {
  it('resolves through resolveRepoRefLocal and keys a tagged ref by name:tag', async () => {
    m.resolveRepoRefLocal.mockResolvedValue({ name: 'mail', repoKey: 'mail:t1', tag: 't1' });
    m.getRepository.mockResolvedValue({ repositoryGuid: 'guid-1' });
    await expect(configRepo('mail:t1')).resolves.toEqual({ guid: 'guid-1', name: 'mail' });
    expect(m.resolveRepoRefLocal).toHaveBeenCalledWith('mail:t1');
    expect(m.getRepository).toHaveBeenCalledWith('mail:t1');
  });

  it('passes the not-in-config refusal of resolveRepoRefLocal through unchanged', async () => {
    const refusal = new Error('repository "mail" is not in this config.');
    m.resolveRepoRefLocal.mockRejectedValue(refusal);
    await expect(configRepo('mail')).rejects.toBe(refusal);
    expect(m.getRepository).not.toHaveBeenCalled();
  });

  it('refuses a repository without a GUID', async () => {
    m.resolveRepoRefLocal.mockResolvedValue({ name: 'mail', repoKey: 'mail' });
    m.getRepository.mockResolvedValue({});
    await expect(configRepo('mail')).rejects.toThrow('forensics.noRepoGuid');
  });
});
