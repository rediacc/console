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

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import {
  auditKey,
  type Fixture,
  GUID,
  MACHINE,
  repoKey,
  rewrite,
  writeFixture,
} from '../../services/forensics/__tests__/evidence-fixture.js';
import { ForensicsClient } from '../../services/forensics/client.js';
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

const INCIDENT = {
  id: 'inc-aaaa1111',
  scopeKind: 'repo',
  scopeRef: GUID,
  windowFrom: '2026-11-01T00:00:00.000Z',
  windowTo: '2026-11-03T00:00:00.000Z',
};

/** A client a test must never reach: a call fails the test. */
const noServer = (): ForensicsClient => {
  throw new Error('the server must not be called');
};

/** The account server, which pinned `publicKey` for machine-1 of the incident's scope. */
function server(publicKey: string): ForensicsClient {
  return new ForensicsClient(<T>(path: string) => {
    if (path.endsWith('/incidents')) return Promise.resolve({ incidents: [INCIDENT] } as T);
    if (path.endsWith('/investigations')) return Promise.resolve({ id: 'inv-1' } as T);
    if (path.includes('/raw?')) {
      return Promise.resolve({
        files: [],
        bytes: 0,
        tooLarge: false,
        machineKeys: [{ machineId: MACHINE, subscriptionId: 'sub-1', publicKey }],
      } as T);
    }
    return Promise.reject(new Error(`unexpected ${path}`));
  });
}

function writeManifest(publicKey: string): void {
  writeFileSync(
    join(dir, 'raw-manifest.json'),
    JSON.stringify({
      files: [],
      bytes: 0,
      tooLarge: false,
      machineKeys: [{ machineId: MACHINE, subscriptionId: 'sub-1', publicKey }],
    })
  );
}

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

  it('never trusts a key the directory lists in raw-manifest.json', async () => {
    writeManifest(fixture.publicKeyHex);
    await runForensicsVerify({ dir }, { client: noServer });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('no public key');
  });

  it('fails a directory whose batches were re-signed under a key swapped into its manifest', async () => {
    const pinned = fixture.publicKeyHex;
    // The forger regenerates every file under a key of its own and writes that key into the manifest.
    const forged = await writeFixture(dir);
    writeManifest(forged.publicKeyHex);
    writeFileSync(join(dir, 'export.json'), JSON.stringify({ incident: INCIDENT.id }));

    await runForensicsVerify({ dir }, { client: () => server(pinned) });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('signature does not verify');
    expect(printed()).toContain('forensics.verifyFailed');
  });

  it('verifies an export directory under the key the server pinned for its incident', async () => {
    writeManifest('ab'.repeat(32));
    writeFileSync(join(dir, 'export.json'), JSON.stringify({ incident: INCIDENT.id }));
    await runForensicsVerify({ dir }, { client: () => server(fixture.publicKeyHex) });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(printed()).toContain('forensics.verifyClean');

    // A --machine-key entry is used instead of the pinned key, with no server call.
    m.print.mockClear();
    await runForensicsVerify(
      { dir, machineKey: [`machine-1=${'ab'.repeat(32)}`] },
      { client: noServer }
    );
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(printed()).toContain('signature does not verify');
  });

  it('names --machine-key when the pinned keys cannot be read', async () => {
    writeFileSync(join(dir, 'incident.json'), JSON.stringify({ id: INCIDENT.id }));
    const offline = new ForensicsClient(() => Promise.reject(new Error('offline')));
    await expect(runForensicsVerify({ dir }, { client: () => offline })).rejects.toThrow(
      'forensics.trustedKeysUnavailable'
    );
  });

  it('refuses an export.json that is not JSON', async () => {
    writeFileSync(join(dir, 'export.json'), '{not json');
    await expect(runForensicsVerify({ dir }, { client: noServer })).rejects.toThrow(
      'forensics.badManifest'
    );
  });

  it('refuses an export.json or incident.json holding JSON null as a bad manifest, not a TypeError', async () => {
    writeFileSync(join(dir, 'export.json'), 'null');
    await expect(runForensicsVerify({ dir }, { client: noServer })).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: /forensics.badManifest/,
    });
    rmSync(join(dir, 'export.json'));
    writeFileSync(join(dir, 'incident.json'), '[1]');
    await expect(runForensicsVerify({ dir }, { client: noServer })).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: /forensics.badManifest/,
    });
  });

  it('never opens export.json when every machine has a --machine-key', async () => {
    writeFileSync(join(dir, 'export.json'), '{not json');
    await runForensicsVerify({ dir, machineKey: key() }, { client: noServer });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(printed()).toContain('forensics.verifyClean');
  });

  it('keeps a classified refusal of the pinned-key read instead of calling it a network error', async () => {
    writeFileSync(join(dir, 'export.json'), JSON.stringify({ incident: 'inc-gone' }));
    await expect(
      runForensicsVerify({ dir }, { client: () => server('ab'.repeat(32)) })
    ).rejects.toMatchObject({ code: 'NOT_FOUND', message: /forensics.trustedKeysUnavailable/ });
    const offline = new ForensicsClient(() => Promise.reject(new Error('offline')));
    await expect(runForensicsVerify({ dir }, { client: () => offline })).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
    });
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

  it('sets exit 1 BEFORE printing a failed JSON report, so its envelope says success:false', async () => {
    m.format.current = 'json';
    await runForensicsVerify({ dir });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    // The JSON envelope derives `success` from the exit code set when it is written; a code set after the print leaves a success:true envelope on a failed run.
    expect(m.setExitCode.mock.invocationCallOrder[0]).toBeLessThan(
      m.print.mock.invocationCallOrder[0] ?? 0
    );
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
