import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { askConfirm } from '../prompt.js';

describe('utils/prompt askConfirm', () => {
  const originalYes = process.env.REDIACC_YES;
  const originalIsTTY = process.stdin.isTTY;

  beforeEach(() => {
    delete process.env.REDIACC_YES;
  });

  afterEach(() => {
    if (originalYes === undefined) {
      delete process.env.REDIACC_YES;
    } else {
      process.env.REDIACC_YES = originalYes;
    }
    Object.defineProperty(process.stdin, 'isTTY', {
      value: originalIsTTY,
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  it('returns true immediately when REDIACC_YES=1, even without a TTY', async () => {
    process.env.REDIACC_YES = '1';
    Object.defineProperty(process.stdin, 'isTTY', { value: undefined, configurable: true });
    await expect(askConfirm('Delete?')).resolves.toBe(true);
  });

  it('exits with INVALID_ARGUMENTS when stdin is not a TTY and REDIACC_YES is unset', async () => {
    Object.defineProperty(process.stdin, 'isTTY', { value: undefined, configurable: true });
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('process.exit called');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(askConfirm('Delete?')).rejects.toThrow('process.exit called');
    expect(exitSpy).toHaveBeenCalledWith(2);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Use --yes to auto-confirm'));
  });
});
