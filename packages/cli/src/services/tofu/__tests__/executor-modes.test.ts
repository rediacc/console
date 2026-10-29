import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  stat,
  symlink,
  writeFile,
} from 'node:fs/promises';
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

    // A file left world-readable by an older rdc is replaced by a 0600 one on the next write.
    // The file already exists, so only chmod can loosen it (a writeFile mode applies on creation).
    await chmod(join(work, 'main.tf.json'), 0o644);
    await exec.writeConfig({ provider: {} });
    expect((await stat(join(work, 'main.tf.json'))).mode & 0o777).toBe(0o600);
    expect(JSON.parse(await readFile(join(work, 'main.tf.json'), 'utf8'))).toEqual({
      provider: {},
    });
    // No temp file is left behind.
    expect(await readdir(work)).toEqual(['main.tf.json']);
  });

  it('replaces a symlinked main.tf.json instead of writing or chmodding its target', async () => {
    const root = await mkdtemp(join(tmpdir(), 'tofu-modes-'));
    dirs.push(root);
    const work = join(root, 'machine');
    await mkdir(work, { recursive: true });
    const outside = join(root, 'outside.json');
    await writeFile(outside, 'untouched');
    await chmod(outside, 0o644);
    await symlink(outside, join(work, 'main.tf.json'));

    await new TofuExecutor(work).writeConfig({ provider: { linode: { token: 'x' } } });

    expect(await readFile(outside, 'utf8')).toBe('untouched');
    expect((await stat(outside)).mode & 0o777).toBe(0o644);
    const written = await lstat(join(work, 'main.tf.json'));
    expect(written.isSymbolicLink()).toBe(false);
    expect(written.mode & 0o777).toBe(0o600);
  });
});
