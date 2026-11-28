import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  setExitCode: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: m.info, success: m.success, warn: m.warn },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: m.setExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import { canonicalBytes } from '@rediacc/shared/incident';
import {
  ForensicsClient,
  type ForensicsFetch,
  type IncidentRecord,
} from '../../services/forensics/client.js';
import { runForensicsVerify } from '../forensics.js';
import { runIncidentExport } from '../incident.js';

const NOW = new Date('2026-11-25T12:00:00.000Z');
const REPORT_ID = '0b8f3c2a-1d4e-4f6a-9b7c-5e2d1a3c4b6f';
// Every byte value, so a text-only path would corrupt it, closed by the end-of-file marker `decodeReportPdf` demands.
const PDF = Uint8Array.from([
  ...Buffer.from('%PDF-1.7\n'),
  ...Array.from({ length: 256 }, (_, i) => i),
  ...Buffer.from('\n%%EOF\n'),
]);
const REPORT = { header: { generatedAt: '2026-11-25T11:00:00.000Z' }, facts: [{ id: 'a', n: 1 }] };

const incident: IncidentRecord = {
  id: 'inc-aaaa1111',
  scopeKind: 'repo',
  scopeRef: '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b',
  windowFrom: '2026-11-24T00:00:00.000Z',
  windowTo: '2026-11-25T00:00:00.000Z',
  status: 'declared',
  declaredBy: 'user-1',
  declaredAt: '2026-11-24T10:00:00.000Z',
  awareAt: '2026-11-24T09:00:00.000Z',
  notifiedAt: null,
  containedAt: null,
  closedAt: null,
  closedBy: null,
  forkRef: null,
  steps: [],
  releaseAt: null,
};

const toHex = (bytes: Uint8Array) =>
  Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

/** A fake account server holding one real Ed25519 key pair and the report signed under it. */
async function server() {
  const pair = (await crypto.subtle.generateKey({ name: 'Ed25519' }, true, [
    'sign',
    'verify',
  ])) as CryptoKeyPair;
  const spki = new Uint8Array(await crypto.subtle.exportKey('spki', pair.publicKey));
  const keyId = toHex(
    new Uint8Array(await crypto.subtle.digest('SHA-256', spki as Uint8Array<ArrayBuffer>))
  ).slice(0, 16);
  const signed = canonicalBytes(REPORT);
  const sha256 = toHex(
    new Uint8Array(await crypto.subtle.digest('SHA-256', signed as Uint8Array<ArrayBuffer>))
  );
  const signature = Buffer.from(
    await crypto.subtle.sign('Ed25519', pair.privateKey, signed as Uint8Array<ArrayBuffer>)
  ).toString('base64');
  const calls: string[] = [];
  const routes: [string, (body: unknown) => unknown][] = [
    ['/incidents', () => ({ incidents: [incident] })],
    [
      `/incidents/${incident.id}/reports`,
      (body) => ({
        id: REPORT_ID,
        incidentId: incident.id,
        stage: (body as { stage: string }).stage,
        sha256,
        keyId,
        generatedAt: REPORT.header.generatedAt,
        generatedBy: 'user-1',
      }),
    ],
    ['/json', () => REPORT],
    ['/stix', () => ({ type: 'bundle', objects: [] })],
    ['/pdf-base64', () => ({ fileName: 'r.pdf', base64: Buffer.from(PDF).toString('base64') })],
    [
      `/reports/verify/${REPORT_ID}`,
      () => ({ id: REPORT_ID, stage: 'notification', generatedAt: '', sha256, signature, keyId }),
    ],
    [
      '/reports/keys',
      () => ({ algorithm: 'Ed25519', publicKey: Buffer.from(spki).toString('base64'), keyId }),
    ],
  ];
  const fetchFn: ForensicsFetch = <T>(
    path: string,
    options?: { method?: string; body?: unknown }
  ) => {
    calls.push(`${options?.method ?? 'GET'} ${path}`);
    const route = routes.find(([suffix]) => path.endsWith(suffix));
    if (!route) return Promise.reject(Object.assign(new Error('not found'), { status: 404 }));
    return Promise.resolve(route[1](options?.body) as T);
  };
  return { client: new ForensicsClient(fetchFn), calls };
}

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'incident-report-'));
  m.format.current = 'table';
  vi.clearAllMocks();
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

describe('rdc incident export --stage', () => {
  it('writes the signed JSON under its report id and the file verifies', async () => {
    const { client } = await server();
    await runIncidentExport(
      incident.id,
      { stage: 'notification', format: 'json', out: dir },
      { client, now: () => NOW }
    );
    const file = join(dir, `${REPORT_ID}.json`);
    expect(readFileSync(file)).toEqual(Buffer.from(canonicalBytes(REPORT)));
    await runForensicsVerify({ report: file }, { client: () => client });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(m.print).toHaveBeenLastCalledWith(expect.stringContaining('forensics.reportValid'));
  });

  it('writes a STIX bundle under the .stix.json suffix', async () => {
    const { client } = await server();
    await runIncidentExport(
      incident.id,
      { stage: 'final', format: 'stix', out: dir },
      { client, now: () => NOW }
    );
    expect(JSON.parse(readFileSync(join(dir, `${REPORT_ID}.stix.json`), 'utf8'))).toEqual({
      type: 'bundle',
      objects: [],
    });
  });

  it('writes the PDF bytes intact through the base64 route', async () => {
    const { client } = await server();
    await runIncidentExport(
      incident.id,
      { stage: 'final', format: 'pdf', out: dir },
      { client, now: () => NOW }
    );
    expect(readFileSync(join(dir, `${REPORT_ID}.pdf`))).toEqual(Buffer.from(PDF));
  });

  it('refuses an unknown stage and format before any report is generated', async () => {
    const { client, calls } = await server();
    const deps = { client, now: () => NOW };
    await expect(
      runIncidentExport(incident.id, { stage: 'draft', out: dir }, deps)
    ).rejects.toThrow('incident.badStage');
    await expect(
      runIncidentExport(incident.id, { stage: 'final', format: 'docx', out: dir }, deps)
    ).rejects.toThrow('incident.badFormat');
    expect(calls.filter((c) => c.startsWith('POST'))).toEqual([]);
  });

  it('refuses --format without --stage', async () => {
    const { client } = await server();
    await expect(
      runIncidentExport(incident.id, { format: 'json', out: dir }, { client, now: () => NOW })
    ).rejects.toThrow('incident.formatNeedsStage');
  });
});

describe('rdc forensics verify --report', () => {
  it('exits 1 on an edited value and names the hash', async () => {
    const { client } = await server();
    const file = join(dir, `${REPORT_ID}.json`);
    writeFileSync(file, JSON.stringify({ ...REPORT, facts: [{ id: 'a', n: 2 }] }));
    await runForensicsVerify({ report: file }, { client: () => client });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(m.print).toHaveBeenLastCalledWith(expect.stringContaining('reportInvalid_hash'));
  });

  it('still verifies a copy that differs only in whitespace and key order', async () => {
    const { client } = await server();
    const file = join(dir, `${REPORT_ID}.json`);
    writeFileSync(
      file,
      JSON.stringify({ facts: [{ n: 1, id: 'a' }], header: REPORT.header }, null, 4)
    );
    await runForensicsVerify({ report: file }, { client: () => client });
    expect(m.setExitCode).not.toHaveBeenCalled();
  });

  it('exits 1 when the file is not JSON, and names the id for a renamed file', async () => {
    const { client } = await server();
    const file = join(dir, 'my report.json');
    writeFileSync(file, 'not json');
    await expect(runForensicsVerify({ report: file }, { client: () => client })).rejects.toThrow(
      'forensics.reportIdUnknown'
    );
    await runForensicsVerify({ report: file, id: REPORT_ID }, { client: () => client });
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    expect(m.print).toHaveBeenLastCalledWith(expect.stringContaining('reportInvalid_unreadable'));
  });

  it('reports an unknown report id as not found', async () => {
    const { client } = await server();
    const file = join(dir, 'ffffffff-0000-4000-8000-000000000000.json');
    writeFileSync(file, JSON.stringify(REPORT));
    await expect(runForensicsVerify({ report: file }, { client: () => client })).rejects.toThrow(
      'forensics.noSuchReport'
    );
  });

  it('needs exactly one of --dir and --report', async () => {
    const { client } = await server();
    await expect(runForensicsVerify({}, { client: () => client })).rejects.toThrow(
      'forensics.verifyNeedsOne'
    );
    await expect(
      runForensicsVerify({ dir, report: 'x.json' }, { client: () => client })
    ).rejects.toThrow('forensics.verifyNeedsOne');
  });
});
