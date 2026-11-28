/**
 * deleteRepoImageByGuid, the one delete of `machine prune` and `repo admin orphan delete`: a deleted image's licence
 * is retired on the account server, so it does not stay tracked and hard-expire there (worklist #32096ded).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mocks = vi.hoisted(() => ({
  execute: vi.fn(),
  fetch: vi.fn(),
  warn: vi.fn(),
  tokenKind: { value: 'ready' },
}));

vi.mock('../../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: mocks.fetch }));
vi.mock('../../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: mocks.tokenKind.value, token: {} }),
}));
vi.mock('../../core/output.js', () => ({ outputService: { warn: mocks.warn } }));
vi.mock('../../config/config-resources.js', () => ({ configService: {} }));

import { deleteRepoImageByGuid } from '../orphan-repos.js';

const GUID = '9a8b7c6d-1111-4222-8333-444455556666';
const retirePath = `/account/api/v1/licenses/repos/${GUID}/retire`;

describe('deleteRepoImageByGuid', () => {
  beforeEach(() => {
    mocks.execute.mockReset().mockResolvedValue({ success: true, exitCode: 0 });
    mocks.fetch.mockReset().mockResolvedValue({ repositoryGuid: GUID, retired: true });
    mocks.warn.mockReset();
    mocks.tokenKind.value = 'ready';
  });

  it('deletes by GUID through repository_delete, then retires that GUID', async () => {
    const result = await deleteRepoImageByGuid('m1', GUID);
    expect(result.success).toBe(true);
    expect(mocks.execute).toHaveBeenCalledWith(
      expect.objectContaining({
        functionName: 'repository_delete',
        machineName: 'm1',
        params: { repository: GUID },
      })
    );
    expect(mocks.fetch).toHaveBeenCalledWith(retirePath, { method: 'POST' });
  });

  it('retires nothing when the delete failed: the image, and its licence, are still there', async () => {
    mocks.execute.mockResolvedValue({ success: false, exitCode: 1, error: 'busy' });
    const result = await deleteRepoImageByGuid('m1', GUID);
    expect(result.success).toBe(false);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('keeps the delete a success and warns by GUID when the account server refuses the retire', async () => {
    mocks.fetch.mockRejectedValue(new Error('503 unavailable'));
    const result = await deleteRepoImageByGuid('m1', GUID);
    expect(result.success).toBe(true);
    expect(mocks.warn).toHaveBeenCalledTimes(1);
    expect(String(mocks.warn.mock.calls[0][0])).toContain('licenseRetireFailed');
    expect(String(mocks.warn.mock.calls[0][0])).toContain(GUID);
    expect(String(mocks.warn.mock.calls[0][0])).toContain('503 unavailable');
  });

  it('posts nothing without an account token (control)', async () => {
    mocks.tokenKind.value = 'missing';
    await deleteRepoImageByGuid('m1', GUID);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });
});
