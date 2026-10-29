import { mkdtemp, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { TofuExecutor } from '../executor.js';

const dirs: string[] = [];

afterEach(async () => {
  await Promise.all(dirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
});

describe.skipIf(process.platform === 'win32')('TofuExecutor.writeConfig', () => {
  it('writes the token-bearing config 0600 in a 0700 directory, tightening an existing loose file', async () => {
    const root = await mkdtemp(join(tmpdir(), 'tofu-modes-'));
    dirs.push(root);
    const work = join(root, 'machine');
    const exec = new TofuExecutor(work);
    await exec.writeConfig({ provider: { linode: { token: 'x' } } });
    expect((await stat(work)).mode & 0o777).toBe(0o700);
    expect((await stat(join(work, 'main.tf.json'))).mode & 0o777).toBe(0o600);

    // A file left world-readable by an older rdc is tightened on the next write.
    await writeFile(join(work, 'main.tf.json'), '{}', { mode: 0o644 });
    const { chmod } = await import('node:fs/promises');
    await chmod(join(work, 'main.tf.json'), 0o644);
    await exec.writeConfig({ provider: {} });
    expect((await stat(join(work, 'main.tf.json'))).mode & 0o777).toBe(0o600);
  });
});
