import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockExecSync } = vi.hoisted(() => ({ mockExecSync: vi.fn() }));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  execSync: mockExecSync,
}));

const { resolveRenetPath } = await import('../renet/renet-execution.js');

describe('resolveRenetPath PATH lookup', () => {
  beforeEach(() => mockExecSync.mockReset());

  it('runs where/which once per process for a binary name', () => {
    mockExecSync.mockReturnValue('/usr/local/bin/renet-cache-a\n');
    expect(resolveRenetPath('renet-cache-a')).toBe('/usr/local/bin/renet-cache-a');
    expect(resolveRenetPath('renet-cache-a')).toBe('/usr/local/bin/renet-cache-a');
    expect(mockExecSync).toHaveBeenCalledTimes(1);
  });

  it('does not cache a miss', () => {
    mockExecSync.mockImplementation(() => {
      throw new Error('not found');
    });
    expect(() => resolveRenetPath('renet-cache-b')).toThrow(/not found at/);
    mockExecSync.mockReturnValue('/opt/renet-cache-b\n');
    expect(resolveRenetPath('renet-cache-b')).toBe('/opt/renet-cache-b');
    expect(mockExecSync).toHaveBeenCalledTimes(2);
  });
});
