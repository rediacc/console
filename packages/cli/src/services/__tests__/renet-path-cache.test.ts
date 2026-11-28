import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
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
    mockExecSync.mockReturnValue(`${process.execPath}\n`);
    expect(resolveRenetPath('renet-cache-a')).toBe(process.execPath);
    expect(resolveRenetPath('renet-cache-a')).toBe(process.execPath);
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

  it('looks up again when the cached binary has gone away', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-cache-'));
    const first = path.join(dir, 'renet');
    const second = path.join(dir, 'renet2');
    fs.writeFileSync(first, '');
    fs.writeFileSync(second, '');
    mockExecSync.mockReturnValueOnce(`${first}\n`).mockReturnValueOnce(`${second}\n`);
    expect(resolveRenetPath('renet-cache-c')).toBe(first);
    fs.rmSync(first);
    expect(resolveRenetPath('renet-cache-c')).toBe(second);
    expect(mockExecSync).toHaveBeenCalledTimes(2);
    fs.rmSync(dir, { recursive: true });
  });

  // 095c22c9.1: existence alone let a file replaced at the same path be handed out as the old lookup.
  it('looks up again when a different file now sits at the cached path', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-cache-'));
    const bin = path.join(dir, 'renet');
    fs.writeFileSync(bin, 'old');
    mockExecSync.mockReturnValue(`${bin}\n`);
    expect(resolveRenetPath('renet-cache-e')).toBe(bin);
    fs.writeFileSync(bin, 'a replacement binary of another size');
    expect(resolveRenetPath('renet-cache-e')).toBe(bin);
    expect(mockExecSync).toHaveBeenCalledTimes(2);
    fs.rmSync(dir, { recursive: true });
  });

  it('does not cache an empty lookup result', () => {
    mockExecSync.mockReturnValueOnce('\n');
    expect(() => resolveRenetPath('renet-cache-d')).toThrow(/not found at/);
    mockExecSync.mockReturnValueOnce(`${process.execPath}\n`);
    expect(resolveRenetPath('renet-cache-d')).toBe(process.execPath);
    expect(mockExecSync).toHaveBeenCalledTimes(2);
  });
});
