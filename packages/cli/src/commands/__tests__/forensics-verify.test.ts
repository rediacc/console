import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  setExitCode: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: vi.fn(), success: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: m.setExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));

import {
  auditKey,
  type Fixture,
  repoKey,
  rewrite,
  writeFixture,
} from '../../services/forensics/__tests__/evidence-fixture.js';
import { runForensicsVerify } from '../forensics.js';

let dir: string;
let fixture: Fixture;

beforeEach(async () => {
  vi.clearAllMocks();
  m.format.current = 'table';
  dir = mkdtempSync(join(tmpdir(), 'rdc-forensics-verify-'));
  fixture = await writeFixture(dir);
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

const printed = () => m.print.mock.calls.map((c) => String(c[0])).join('\n');
const key = (machine = 'machine-1') => [`${machine}=${fixture.publicKeyHex}`];

describe('forensics verify', () => {
  it('passes an intact fixture and leaves the exit code alone', async () => {
    await runForensicsVerify({ dir, machineKey: key() });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(printed()).toContain('forensics.verifyClean');
  });

  it('exits 1 and names the day when an audit day file is edited', async () => {
    rewrite(
      dir,
      auditKey('2026-11-01'),
      `${JSON.stringify({ v: 1, org: 'org-1', day: '2026-11-01', prevDay: null, prevSha256: 'genesis', count: 2 })}\n{"id":"a"}\n{"id":"b"}\n`
    );
    await runForensicsVerify({ dir, machineKey: key() });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('2026-11-01');
    expect(printed()).toContain('forensics.verifyFailed');
  });

  it('exits 1 when a forensics section no longer matches its signed hash', async () => {
    rewrite(
      dir,
      repoKey('2026-11-02'),
      `${JSON.stringify({ seq: 1, section: Buffer.from('tampered').toString('base64') })}\n`
    );
    await runForensicsVerify({ dir, machineKey: key() });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('machine-1#1');
  });

  it('exits 1 for a machine whose public key was not given', async () => {
    await runForensicsVerify({ dir });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('no public key');
  });

  it('takes the machine key from raw-manifest.json, and a --machine-key entry replaces it', async () => {
    writeFileSync(
      join(dir, 'raw-manifest.json'),
      JSON.stringify({
        files: [],
        bytes: 0,
        tooLarge: false,
        machineKeys: [
          { machineId: 'machine-1', subscriptionId: 'sub-1', publicKey: fixture.publicKeyHex },
        ],
      })
    );
    await runForensicsVerify({ dir });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(printed()).toContain('forensics.verifyClean');

    m.print.mockClear();
    await runForensicsVerify({ dir, machineKey: [`machine-1=${'ab'.repeat(32)}`] });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('signature does not verify');
  });

  it('refuses a raw-manifest.json that is not JSON', async () => {
    writeFileSync(join(dir, 'raw-manifest.json'), '{not json');
    await expect(runForensicsVerify({ dir })).rejects.toThrow('forensics.badManifest');
  });

  it('prints the stamped report as JSON', async () => {
    m.format.current = 'json';
    await runForensicsVerify({ dir, machineKey: key() });
    const [report, format] = m.print.mock.calls[0] ?? [];
    expect(format).toBe('json');
    expect(report).toMatchObject({
      clean: true,
      verifier: 'rdc forensics verify',
      heads: { batches: [{ machineId: 'machine-1', seq: 2 }] },
    });
  });

  it('refuses a malformed --machine-key and an empty directory', async () => {
    await expect(runForensicsVerify({ dir, machineKey: ['machine-1=zz'] })).rejects.toThrow(
      'forensics.badMachineKey'
    );
    const empty = mkdtempSync(join(tmpdir(), 'rdc-forensics-empty-'));
    try {
      writeFileSync(join(empty, 'note.txt'), readFileSync(join(dir, auditKey('2026-11-01'))));
      await expect(runForensicsVerify({ dir: empty })).rejects.toThrow('forensics.noEvidence');
    } finally {
      rmSync(empty, { recursive: true, force: true });
    }
  });
});
