/**
 * Evidence verification (D5 of agent/plans/PLAN-forensics-investigation.md).
 * Day files are gzipped here with node:zlib and batches are signed with
 * node:crypto, so nothing under test produced the bytes it checks.
 */
import { generateKeyPairSync, sign } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import {
  type BatchHeader,
  batchHash,
  encodeHeader,
  GENESIS_HASH,
  importSpoolPublicKey,
  sha256Hex,
} from '../batch.js';
import {
  type AuditDayInput,
  type BatchInput,
  verifyAuditDays,
  verifyBatchChains,
  verifyWindow,
} from '../verify.js';

const ORG = 'org-1';

function dayFile(
  day: string,
  prev: { day: string; sha256: string } | null,
  events = 2,
  org = ORG
): Uint8Array {
  const header = {
    v: 1,
    org,
    day,
    prevDay: prev?.day ?? null,
    prevSha256: prev?.sha256 ?? GENESIS_HASH,
    count: events,
  };
  const lines = [JSON.stringify(header)];
  for (let i = 0; i < events; i++) lines.push(JSON.stringify({ id: `${day}-${i}` }));
  return new Uint8Array(gzipSync(Buffer.from(`${lines.join('\n')}\n`)));
}

async function chainOfDays(days: string[]): Promise<AuditDayInput[]> {
  const out: AuditDayInput[] = [];
  let prev: { day: string; sha256: string } | null = null;
  for (const day of days) {
    const bytes = dayFile(day, prev);
    out.push({ day, bytes });
    prev = { day, sha256: await sha256Hex(bytes) };
  }
  return out;
}

describe('verifyAuditDays', () => {
  it('passes an intact three day chain and reports its head', async () => {
    const files = await chainOfDays(['2026-11-01', '2026-11-02', '2026-11-03']);
    const result = await verifyAuditDays(ORG, files);
    expect(result.gaps).toEqual([]);
    expect(result.edits).toEqual([]);
    expect(result.head?.day).toBe('2026-11-03');
  });

  it('reports an edit at the day whose bytes changed after the next file recorded them', async () => {
    const files = await chainOfDays(['2026-11-01', '2026-11-02', '2026-11-03']);
    // A different but well-formed file for day 2: only the chain can tell.
    files[1] = { day: '2026-11-02', bytes: dayFile('2026-11-02', null, 3) };
    const result = await verifyAuditDays(ORG, files);
    expect(result.edits.map((e) => e.ref)).toContain('2026-11-02');
    expect(result.edits.find((e) => e.ref === '2026-11-02')?.reason).toMatch(/changed/);
  });

  it('reports a flipped byte as an edit at that day', async () => {
    const files = await chainOfDays(['2026-11-01', '2026-11-02']);
    const corrupt = new Uint8Array(files[1]?.bytes ?? []);
    corrupt[corrupt.length - 6] = (corrupt[corrupt.length - 6] ?? 0) ^ 0xff;
    files[1] = { day: '2026-11-02', bytes: corrupt };
    const result = await verifyAuditDays(ORG, files);
    expect(result.edits.map((e) => e.ref)).toContain('2026-11-02');
  });

  it('reports a removed day file as a gap', async () => {
    const files = await chainOfDays(['2026-11-01', '2026-11-02', '2026-11-03']);
    const result = await verifyAuditDays(ORG, [files[0], files[2]] as AuditDayInput[]);
    expect(result.gaps).toEqual([
      { source: 'audit', ref: '2026-11-02', reason: expect.stringContaining('missing') },
    ]);
  });

  it('refuses a first file that does not start from genesis', async () => {
    const forged = dayFile('2026-11-01', { day: '2026-10-31', sha256: 'a'.repeat(64) });
    const result = await verifyAuditDays(ORG, [{ day: '2026-11-01', bytes: forged }]);
    // A named predecessor that is not in the input is the caller's anchor, not an edit.
    expect(result.edits).toEqual([]);
    const dishonest = new Uint8Array(
      gzipSync(
        Buffer.from(
          `${JSON.stringify({ v: 1, org: ORG, day: '2026-11-01', prevDay: null, prevSha256: 'f'.repeat(64), count: 0 })}\n`
        )
      )
    );
    const flagged = await verifyAuditDays(ORG, [{ day: '2026-11-01', bytes: dishonest }]);
    expect(flagged.edits[0]?.reason).toMatch(/genesis/);
  });

  it('refuses a file filed under another org', async () => {
    const result = await verifyAuditDays(ORG, [
      { day: '2026-11-01', bytes: dayFile('2026-11-01', null, 1, 'org-2') },
    ]);
    expect(result.edits[0]?.reason).toMatch(/another org/);
  });
});

const GUID = '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b';

function signer() {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const jwk = publicKey.export({ format: 'jwk' });
  return {
    key: importSpoolPublicKey(new Uint8Array(Buffer.from(jwk.x ?? '', 'base64url'))),
    sign: (bytes: Uint8Array) => new Uint8Array(sign(null, bytes, privateKey)),
  };
}

const RECORDS = new Uint8Array(Buffer.from('records-bytes'));

async function makeBatch(
  s: ReturnType<typeof signer>,
  seq: number,
  prevHash: string,
  records: Uint8Array = RECORDS
): Promise<{ input: BatchInput; hash: string }> {
  const header: BatchHeader = {
    schema: 1,
    machine_id: 'machine-1',
    seq,
    prev_hash: prevHash,
    cut_at: `2026-11-23T10:00:${String(seq).padStart(2, '0')}Z`,
    level: 'standard',
    sections: [
      {
        repo_guid: GUID,
        kind: 'records',
        sha256: await sha256Hex(RECORDS),
        bytes: RECORDS.length,
      },
    ],
  };
  const headerBytes = encodeHeader(header);
  const signature = s.sign(headerBytes);
  return {
    input: {
      headerBytes,
      signature,
      sections: new Map([[`${GUID}/records`, records]]),
    },
    hash: await batchHash(headerBytes, signature),
  };
}

async function chainOfBatches(s: ReturnType<typeof signer>, count: number) {
  const out: { input: BatchInput; hash: string }[] = [];
  let prev = GENESIS_HASH;
  for (let seq = 0; seq < count; seq++) {
    const batch = await makeBatch(s, seq, prev);
    out.push(batch);
    prev = batch.hash;
  }
  return out;
}

describe('verifyBatchChains', () => {
  it('passes an intact chain and reports the newest batch as the head', async () => {
    const s = signer();
    const batches = await chainOfBatches(s, 3);
    const result = await verifyBatchChains(
      batches.map((b) => b.input),
      async () => s.key
    );
    expect(result.gaps).toEqual([]);
    expect(result.edits).toEqual([]);
    expect(result.heads).toEqual([{ machineId: 'machine-1', seq: 2, hash: batches[2]?.hash }]);
  });

  it('reports a missing batch as a gap', async () => {
    const s = signer();
    const batches = await chainOfBatches(s, 3);
    const result = await verifyBatchChains(
      [batches[0]?.input, batches[2]?.input] as BatchInput[],
      async () => s.key
    );
    expect(result.gaps).toEqual([
      { source: 'forensics', ref: 'machine-1#2', reason: expect.stringContaining('1 to 1') },
    ]);
  });

  it('fails a batch whose signature is not the machine key', async () => {
    const s = signer();
    const other = signer();
    const batches = await chainOfBatches(s, 1);
    const result = await verifyBatchChains(
      batches.map((b) => b.input),
      async () => other.key
    );
    expect(result.edits).toEqual([
      { source: 'forensics', ref: 'machine-1#0', reason: 'signature does not verify' },
    ]);
  });

  it('reports a changed section as an edit', async () => {
    const s = signer();
    const batch = await makeBatch(
      s,
      0,
      GENESIS_HASH,
      new Uint8Array(Buffer.from('tampered-bytes'))
    );
    const result = await verifyBatchChains([batch.input], async () => s.key);
    expect(result.edits[0]?.reason).toMatch(/changed/);
  });

  it('reports a batch whose prev_hash names another predecessor as an edit', async () => {
    const s = signer();
    const first = await makeBatch(s, 0, GENESIS_HASH);
    const forged = await makeBatch(s, 1, 'b'.repeat(64));
    const result = await verifyBatchChains([first.input, forged.input], async () => s.key);
    expect(result.edits).toEqual([
      {
        source: 'forensics',
        ref: 'machine-1#1',
        reason: 'prev_hash does not match the previous batch',
      },
    ]);
  });

  it('reports a machine with no known key', async () => {
    const s = signer();
    const batches = await chainOfBatches(s, 1);
    const result = await verifyBatchChains(
      batches.map((b) => b.input),
      async () => null
    );
    expect(result.edits[0]?.reason).toMatch(/no public key/);
  });
});

describe('verifyWindow', () => {
  it('stamps the window, heads, verifier and clock, and is clean when nothing is wrong', async () => {
    const s = signer();
    const report = await verifyWindow({
      org: ORG,
      window: { from: '2026-11-01T00:00:00.000Z', to: '2026-11-03T00:00:00.000Z' },
      auditDays: await chainOfDays(['2026-11-01', '2026-11-02']),
      batches: (await chainOfBatches(s, 2)).map((b) => b.input),
      publicKeyFor: async () => s.key,
      verifier: 'browser',
      toolVersion: '1.2.3',
      now: () => new Date('2026-11-24T08:00:00.000Z'),
    });
    expect(report.clean).toBe(true);
    expect(report.verifiedAt).toBe('2026-11-24T08:00:00.000Z');
    expect(report.verifier).toBe('browser');
    expect(report.toolVersion).toBe('1.2.3');
    expect(report.heads.audit?.day).toBe('2026-11-02');
    expect(report.heads.batches).toHaveLength(1);
  });

  it('is not clean when either chain has a finding', async () => {
    const s = signer();
    const days = await chainOfDays(['2026-11-01', '2026-11-02', '2026-11-03']);
    const report = await verifyWindow({
      org: ORG,
      window: { from: '2026-11-01T00:00:00.000Z', to: '2026-11-04T00:00:00.000Z' },
      auditDays: [days[0], days[2]] as AuditDayInput[],
      batches: [],
      publicKeyFor: async () => s.key,
      verifier: 'cli',
      toolVersion: '1.2.3',
    });
    expect(report.clean).toBe(false);
    expect(report.gaps).toHaveLength(1);
  });
});
