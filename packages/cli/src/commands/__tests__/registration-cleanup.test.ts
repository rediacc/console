import { beforeEach, describe, expect, it, vi } from 'vitest';

const removeRepository = vi.fn();
const warn = vi.fn();

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { removeRepository: (...a: unknown[]) => removeRepository(...a) },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { warn: (...a: unknown[]) => warn(...a) },
}));

const { dropRegistrationAfterFailure } = await import('../registration-cleanup.js');

describe('dropRegistrationAfterFailure', () => {
  beforeEach(() => {
    removeRepository.mockReset();
    warn.mockReset();
  });

  it('removes the latest registration and stays quiet when that works', async () => {
    removeRepository.mockResolvedValue(undefined);
    await dropRegistrationAfterFailure('web');
    expect(removeRepository).toHaveBeenCalledWith('web:latest');
    expect(warn).not.toHaveBeenCalled();
  });

  it('never throws, and warns with the name and the cause when the cleanup fails', async () => {
    removeRepository.mockRejectedValue(new Error('config write refused'));
    await expect(dropRegistrationAfterFailure('web')).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledTimes(1);
    const line = String(warn.mock.calls[0]?.[0]);
    expect(line).toContain('web');
    expect(line).toContain('config write refused');
  });
});
