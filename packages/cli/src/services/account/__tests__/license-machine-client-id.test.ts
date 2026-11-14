import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { readLinuxClientMachineId } from '../license-machine.js';

const dirs: string[] = [];
function tmp(): string {
  const d = mkdtempSync(join(tmpdir(), 'client-id-'));
  dirs.push(d);
  return d;
}
afterEach(() => {
  for (const d of dirs.splice(0)) {
    chmodSync(d, 0o700);
    rmSync(d, { recursive: true, force: true });
  }
});

// A proxied command runs in the executor container, which has no /etc/machine-id.
describe('readLinuxClientMachineId without a host machine id', () => {
  it('uses a generated id and keeps it stable across calls', async () => {
    const dir = tmp();
    const sources = {
      hostPaths: [join(dir, 'missing-1'), join(dir, 'missing-2')],
      installIdPath: join(dir, 'cfg', 'client-machine-id'),
    };
    const first = await readLinuxClientMachineId(sources);
    expect(first).toMatch(/^[a-f0-9]{64}$/);
    expect(await readLinuxClientMachineId(sources)).toBe(first);
  });

  it('two first runs racing report the one id that was persisted', async () => {
    const dir = tmp();
    const sources = {
      hostPaths: [join(dir, 'missing')],
      installIdPath: join(dir, 'cfg', 'client-machine-id'),
    };
    const ids = await Promise.all(
      Array.from({ length: 8 }, () => readLinuxClientMachineId(sources))
    );

    expect(new Set(ids).size).toBe(1);
    expect(await readLinuxClientMachineId(sources)).toBe(ids[0]);
  });

  it('replaces a corrupt leftover id file instead of failing on it', async () => {
    const dir = tmp();
    const installIdPath = join(dir, 'client-machine-id');
    writeFileSync(installIdPath, 'garbage\n');
    const sources = { hostPaths: [join(dir, 'missing')], installIdPath };

    const id = await readLinuxClientMachineId(sources);

    expect(id).toMatch(/^[a-f0-9]{64}$/);
    expect(await readLinuxClientMachineId(sources)).toBe(id);
  });

  it('two first runs racing over a corrupt leftover still report one id', async () => {
    const dir = tmp();
    const installIdPath = join(dir, 'client-machine-id');
    writeFileSync(installIdPath, 'garbage\n');
    const sources = { hostPaths: [join(dir, 'missing')], installIdPath };

    const ids = await Promise.all(
      Array.from({ length: 8 }, () => readLinuxClientMachineId(sources))
    );

    expect(new Set(ids).size).toBe(1);
    expect(await readLinuxClientMachineId(sources)).toBe(ids[0]);
  });

  it('names an unreadable host id file instead of quietly reporting a generated id', async () => {
    const dir = tmp();
    // A directory where the id file should be: readFile fails with EISDIR, not ENOENT.
    const hostPath = join(dir, 'machine-id');
    mkdirSync(hostPath);
    const err = await readLinuxClientMachineId({
      hostPaths: [hostPath],
      installIdPath: join(dir, 'cfg', 'client-machine-id'),
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CliExitError);
    expect((err as Error).message).toContain(hostPath);
  });

  it('reads a later host id path when an earlier one is unreadable', async () => {
    const dir = tmp();
    const unreadable = join(dir, 'machine-id');
    mkdirSync(unreadable);
    writeFileSync(join(dir, 'dbus-id'), 'dbus123\n');
    const id = await readLinuxClientMachineId({
      hostPaths: [unreadable, join(dir, 'dbus-id')],
      installIdPath: join(dir, 'x'),
    });
    expect(id).toBe('dbus123');
  });

  it('does not overwrite a corrupt file under a fresh replace lock held by a slow run', async () => {
    const dir = tmp();
    const installIdPath = join(dir, 'client-machine-id');
    writeFileSync(installIdPath, 'garbage\n');
    writeFileSync(`${installIdPath}.replace`, '');
    const holderId = 'a'.repeat(64);
    // The slow holder finishes its write after the racer started waiting.
    setTimeout(() => {
      writeFileSync(installIdPath, `${holderId}\n`);
      rmSync(`${installIdPath}.replace`, { force: true });
    }, 300);
    const id = await readLinuxClientMachineId({
      hostPaths: [join(dir, 'missing')],
      installIdPath,
    });
    expect(id).toBe(holderId);
  });

  it('prefers the host id when present', async () => {
    const dir = tmp();
    writeFileSync(join(dir, 'machine-id'), 'abc123\n');
    const id = await readLinuxClientMachineId({
      hostPaths: [join(dir, 'machine-id')],
      installIdPath: join(dir, 'x'),
    });
    expect(id).toBe('abc123');
  });

  it('fails with a named code, not a raw ENOENT, when nothing can be saved', async () => {
    const dir = tmp();
    writeFileSync(join(dir, 'blocker'), '');
    const err = await readLinuxClientMachineId({
      hostPaths: [join(dir, 'missing')],
      installIdPath: join(dir, 'blocker', 'client-machine-id'),
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CliExitError);
    expect((err as CliExitError).code).toBe('PRECONDITION_MISMATCH');
    expect((err as Error).message).toContain('No client machine id');
  });
});
