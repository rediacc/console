import * as fs from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  assertCephHostVersion,
  CEPH_IMAGE_PIN_PATH,
  parseCephVersion,
  readCephHostVersion,
} from '../bridge-global-setup';

const CEPH = '192.168.111.21';
const WORKER = '192.168.111.11';
const line = (v: string) =>
  `ceph version ${v} (c92aebb279828e9c3c1f5d24613efca272649e62) squid (stable)\n`;

const executeOnVM =
  vi.fn<
    (ip: string, command: string) => Promise<{ stdout: string; stderr: string; code: number }>
  >();

function answers(byIp: Record<string, { stdout: string; stderr?: string; code?: number }>) {
  executeOnVM.mockImplementation((ip: string) => {
    const entry = byIp[ip];
    return Promise.resolve({
      stdout: entry.stdout,
      stderr: entry.stderr ?? '',
      code: entry.code ?? 0,
    });
  });
}

describe('readCephHostVersion', () => {
  it('reads host-version and ignores the host.* lines', () => {
    expect(
      readCephHostVersion('# c\nimage=x\nhost-version=19.2.3\nhost.el10=2:19.2.3-1.el10s\n')
    ).toBe('19.2.3');
  });

  it('throws when the line is absent', () => {
    expect(() => readCephHostVersion('host.el10=2:19.2.3-1.el10s\n')).toThrow(
      'no host-version line'
    );
  });

  it('resolves the real pin file', () => {
    expect(readCephHostVersion(fs.readFileSync(CEPH_IMAGE_PIN_PATH, 'utf8'))).toMatch(
      /^\d+\.\d+\.\d+$/
    );
  });
});

describe('parseCephVersion', () => {
  it('takes the release, not the build hash', () => {
    expect(parseCephVersion(line('19.2.3'))).toBe('19.2.3');
    expect(parseCephVersion('bash: ceph: command not found')).toBe('');
  });
});

describe('assertCephHostVersion', () => {
  beforeEach(() => {
    executeOnVM.mockReset();
  });

  it('passes when every VM reports host-version', async () => {
    answers({ [CEPH]: { stdout: line('19.2.3') }, [WORKER]: { stdout: line('19.2.3') } });
    await expect(
      assertCephHostVersion({ executeOnVM }, [CEPH, WORKER], '19.2.3')
    ).resolves.toBeUndefined();
    expect(executeOnVM).toHaveBeenCalledWith(CEPH, 'ceph --version');
    expect(executeOnVM).toHaveBeenCalledWith(WORKER, 'ceph --version');
  });

  it('fails naming the VM and the version it found', async () => {
    answers({ [CEPH]: { stdout: line('19.2.3') }, [WORKER]: { stdout: line('19.2.6') } });
    const run = assertCephHostVersion({ executeOnVM }, [CEPH, WORKER], '19.2.3');
    await expect(run).rejects.toThrow(`${WORKER}: ceph 19.2.6, expected 19.2.3`);
    await expect(run).rejects.not.toThrow(`${CEPH}:`);
  });

  it('fails naming a VM where ceph is missing', async () => {
    answers({
      [CEPH]: { stdout: '', stderr: 'bash: ceph: command not found', code: 127 },
      [WORKER]: { stdout: line('19.2.3') },
    });
    await expect(assertCephHostVersion({ executeOnVM }, [CEPH, WORKER], '19.2.3')).rejects.toThrow(
      `${CEPH}: ceph --version gave no version (bash: ceph: command not found)`
    );
  });

  // Control: with the comparison disabled the same mismatch passes, so the rejection above comes from the
  // version comparison and not from the probe or the parse.
  it('control: a disabled comparison lets the mismatch through', async () => {
    answers({ [CEPH]: { stdout: line('19.2.3') }, [WORKER]: { stdout: line('19.2.6') } });
    await expect(
      assertCephHostVersion({ executeOnVM }, [CEPH, WORKER], '19.2.3', () => true)
    ).resolves.toBeUndefined();
  });
});
