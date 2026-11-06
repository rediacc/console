import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
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
