import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../update/updater.js', () => ({
  computeSha256: vi.fn(() => Promise.resolve('sum')),
  downloadFile: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../../utils/platform.js', () => ({
  acquireUpdateLock: vi.fn(() => Promise.resolve(() => Promise.resolve())),
}));

const { installBinaryAtPath } = await import('../install-binary.js');

const binary = { url: 'https://example.invalid/rdc', sha256: 'sum' };

describe('installBinaryAtPath swap', () => {
  let dir: string;
  let target: string;

  beforeEach(async () => {
    dir = await fs.mkdtemp(join(tmpdir(), 'install-binary-'));
    target = join(dir, 'rdc');
    await fs.writeFile(target, 'old');
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await fs.rm(dir, { recursive: true, force: true });
  });

  it('puts the previous binary back and reports the install error when the swap fails', async () => {
    // control: the staged file is absent, so the second rename fails and the first is undone
    await expect(installBinaryAtPath(target, binary)).rejects.toThrow(/ENOENT/);
    expect(await fs.readFile(target, 'utf8')).toBe('old');
  });

  it('names the restore failure too when the previous binary cannot be put back', async () => {
    const real = fs.rename.bind(fs);
    let calls = 0;
    vi.spyOn(fs, 'rename').mockImplementation((from, to) => {
      calls += 1;
      if (calls === 1) return real(from, to);
      return Promise.reject(new Error(`rename ${calls} refused`));
    });
    await expect(installBinaryAtPath(target, binary)).rejects.toThrow(
      /could not be installed \(rename 2 refused\).*could not be put back.*\(rename 3 refused\)/
    );
  });
});
