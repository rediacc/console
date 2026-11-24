/**
 * Batch format and licence claim (D1 and D9 of agent/plans/PLAN-forensics-shipping.md).
 *
 * The vectors file is read twice: through the module under test, and through
 * node:crypto, which shares no code with it, so a vector cannot pass merely
 * because the encoder and the verifier agree with each other.
 */
import { createHash, createPrivateKey, createPublicKey, sign, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  BATCH_SCHEMA,
  type BatchHeader,
  batchHash,
  checkChain,
  decodeHeader,
  decodeSignature,
  encodeHeader,
  encodeSignature,
  GENESIS_HASH,
  importSpoolPublicKey,
  MAX_BATCH_BYTES,
  sectionKey,
  sha256Hex,
  verifyBatch,
  verifyHeaderSignature,
} from '../batch.js';
import {
  clampLevel,
  effectiveLevel,
  ForensicsClaimSchema,
  levelRank,
  levelWithinClaim,
} from '../claim.js';

interface VectorCase {
  name: string;
  header: BatchHeader;
  headerBytesHex: string;
  signatureHex: string;
  batchHashHex: string;
  sections: { repo_guid: string; kind: 'records' | 'pii'; bytesHex: string }[];
}
interface Vectors {
  seedHex: string;
  publicKeyHex: string;
  cases: VectorCase[];
}

const vectors = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../__fixtures__/batch-vectors.json', import.meta.url)),
    'utf-8'
  )
) as Vectors;

const fromHex = (hex: string): Uint8Array => new Uint8Array(Buffer.from(hex, 'hex'));
const nodeSha = (...parts: Uint8Array[]): string =>
  createHash('sha256').update(Buffer.concat(parts)).digest('hex');

function sectionMap(c: VectorCase): Map<string, Uint8Array> {
  return new Map(c.sections.map((s) => [sectionKey(s.repo_guid, s.kind), fromHex(s.bytesHex)]));
}

const publicKey = await importSpoolPublicKey(fromHex(vectors.publicKeyHex));
const [genesis, heartbeat, chained, machineGap] = vectors.cases;

describe('Ed25519 control (RFC 8032 section 7.1, test 1)', () => {
  const pub = fromHex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a');
  const sig = fromHex(
    'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'
  );

  it('verifies the published signature of the empty message', async () => {
    const key = await importSpoolPublicKey(pub);
    expect(await verifyHeaderSignature(key, new Uint8Array(0), sig)).toBe(true);
  });

  it('rejects a changed message, a flipped signature byte and a short signature', async () => {
    const key = await importSpoolPublicKey(pub);
    expect(await verifyHeaderSignature(key, new Uint8Array([0]), sig)).toBe(false);
    const flipped = sig.slice();
    flipped[10] ^= 1;
    expect(await verifyHeaderSignature(key, new Uint8Array(0), flipped)).toBe(false);
    expect(await verifyHeaderSignature(key, new Uint8Array(0), sig.slice(0, 63))).toBe(false);
  });

  it('refuses a public key that is not 32 bytes', async () => {
    await expect(importSpoolPublicKey(pub.slice(0, 31))).rejects.toThrow(/32 bytes/);
  });
});

describe('known-answer vectors', () => {
  const seed = fromHex(vectors.seedHex);
  const privateKey = createPrivateKey({
    key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), seed]),
    format: 'der',
    type: 'pkcs8',
  });

  it('the file holds a genesis batch, an empty heartbeat, a later batch and a machine-level gap batch', () => {
    expect(vectors.cases.map((c) => c.name)).toEqual([
      'genesis-records-and-pii',
      'chained-heartbeat-no-sections',
      'chained-two-repos-full',
      'chained-machine-gap-standard',
    ]);
    expect(genesis.header.sections.map((s) => s.kind)).toEqual(['records', 'pii']);
    expect(heartbeat.header.sections).toEqual([]);
    expect(heartbeat.header.level).toBe('off');
    expect(machineGap.header.level).toBe('standard');
    expect(machineGap.header.sections[0].repo_guid).toBe('');
  });

  it('the public key is the one the seed derives', () => {
    const derived = createPublicKey(privateKey)
      .export({ format: 'der', type: 'spki' })
      .subarray(-32);
    expect(Buffer.from(derived).toString('hex')).toBe(vectors.publicKeyHex);
  });

  it.each(vectors.cases.map((c) => [c.name, c] as const))(
    '%s: bytes, signature, hash and sections agree with node:crypto',
    async (_name, c) => {
      const headerBytes = fromHex(c.headerBytesHex);
      const signature = fromHex(c.signatureHex);
      // Independent of the module under test.
      const spki = Buffer.concat([
        Buffer.from('302a300506032b6570032100', 'hex'),
        Buffer.from(vectors.publicKeyHex, 'hex'),
      ]);
      expect(
        verify(
          null,
          headerBytes,
          createPublicKey({ key: spki, format: 'der', type: 'spki' }),
          signature
        )
      ).toBe(true);
      expect(sign(null, headerBytes, privateKey).toString('hex')).toBe(c.signatureHex);
      expect(nodeSha(headerBytes, signature)).toBe(c.batchHashHex);
      for (const section of c.header.sections) {
        const body = fromHex(
          c.sections.find((s) => s.repo_guid === section.repo_guid && s.kind === section.kind)
            ?.bytesHex ?? ''
        );
        expect(nodeSha(body)).toBe(section.sha256);
        expect(body.length).toBe(section.bytes);
      }
      // Through the module.
      expect(Buffer.from(encodeHeader(c.header)).toString('hex')).toBe(c.headerBytesHex);
      const decoded = decodeHeader(headerBytes);
      expect(decoded).toEqual({ ok: true, header: c.header });
      expect(await batchHash(headerBytes, signature)).toBe(c.batchHashHex);
      expect(await sha256Hex(headerBytes)).toBe(nodeSha(headerBytes));
      expect(await verifyHeaderSignature(publicKey, headerBytes, signature)).toBe(true);
    }
  );

  it('chains: each case names the hash of the one before, the first is genesis', () => {
    expect(genesis.header.prev_hash).toBe(GENESIS_HASH);
    expect(heartbeat.header.prev_hash).toBe(genesis.batchHashHex);
    expect(chained.header.prev_hash).toBe(heartbeat.batchHashHex);
    expect(machineGap.header.prev_hash).toBe(chained.batchHashHex);
    expect(vectors.cases.map((c) => c.header.seq)).toEqual([0, 1, 2, 3]);
  });

  it('every vector verifies through verifyBatch with its chain link', async () => {
    let prev: { seq: number; hash: string } | null = null;
    for (const c of vectors.cases) {
      const verdict = await verifyBatch({
        headerBytes: fromHex(c.headerBytesHex),
        signature: fromHex(c.signatureHex),
        publicKey,
        sections: sectionMap(c),
        prev,
      });
      expect(verdict.ok).toBe(true);
      expect(verdict.signature).toBe('valid');
      expect(verdict.hash).toBe(c.batchHashHex);
      expect(verdict.chain?.kind).toBe(prev === null ? 'first' : 'linked');
      expect(verdict.sections.every((s) => s.status === 'ok')).toBe(true);
      prev = { seq: c.header.seq, hash: c.batchHashHex };
    }
  });

  it('encodes the genesis header as the exact bytes Go spool.Encode produces', () => {
    const text = Buffer.from(genesis.headerBytesHex, 'hex').toString('utf-8');
    expect(text.startsWith('{"schema":1,"machine_id":"machine-7","seq":0,')).toBe(true);
    expect(text).toContain(
      '"prev_hash":"genesis","cut_at":"2026-11-23T10:00:00Z","level":"basic","sections":[{"repo_guid":'
    );
    expect(text).not.toMatch(/\s(?=[{"[])|: /);
  });

  it('keeps cut_at in Go RFC 3339 nanosecond form', () => {
    expect(vectors.cases.map((c) => c.header.cut_at)).toEqual([
      '2026-11-23T10:00:00Z',
      '2026-11-23T10:00:30.000123Z',
      '2026-11-23T10:01:00.5Z',
      '2026-11-23T10:01:30.123456789Z',
    ]);
  });
});

function verifyCase(
  c: VectorCase,
  patch: {
    headerBytes?: Uint8Array;
    signature?: Uint8Array;
    sections?: Map<string, Uint8Array>;
    prev?: { seq: number; hash: string } | null;
  } = {}
) {
  return verifyBatch({
    headerBytes: patch.headerBytes ?? fromHex(c.headerBytesHex),
    signature: patch.signature ?? fromHex(c.signatureHex),
    publicKey,
    sections: patch.sections ?? sectionMap(c),
    ...(patch.prev === undefined ? {} : { prev: patch.prev }),
  });
}

describe('tampering', () => {
  it('a flipped header byte fails the signature (header still readable)', async () => {
    const bytes = fromHex(genesis.headerBytesHex);
    // Flip one hex digit inside the first section's sha256 so the JSON stays valid.
    const at = Buffer.from(bytes).indexOf(Buffer.from(genesis.header.sections[0].sha256)) + 3;
    const flipped = bytes.slice();
    flipped[at] = flipped[at] === 0x61 ? 0x62 : 0x61;
    const verdict = await verifyCase(genesis, { headerBytes: flipped });
    expect(verdict.signature).toBe('invalid');
    expect(verdict.header).not.toBeNull();
    expect(verdict.ok).toBe(false);
    expect(verdict.hash).toBeNull();
  });

  it('a header byte flip that breaks the JSON reports why', async () => {
    const flipped = fromHex(genesis.headerBytesHex);
    flipped[0] = 0x5b;
    const verdict = await verifyCase(genesis, { headerBytes: flipped });
    expect(verdict.ok).toBe(false);
    expect(verdict.header).toBeNull();
    expect(verdict.headerError).toMatch(/JSON/);
  });

  it('every single-byte flip of a header is caught: invalid signature or unreadable header', async () => {
    const original = fromHex(heartbeat.headerBytesHex);
    for (let i = 0; i < original.length; i++) {
      const flipped = original.slice();
      flipped[i] ^= 0x01;
      const verdict = await verifyCase(heartbeat, { headerBytes: flipped });
      expect(verdict.ok, `byte ${i}`).toBe(false);
    }
  });

  it('a flipped signature byte fails', async () => {
    const signature = fromHex(genesis.signatureHex);
    signature[5] ^= 1;
    expect((await verifyCase(genesis, { signature })).signature).toBe('invalid');
  });

  it('a swapped section fails its signed hash', async () => {
    const sections = sectionMap(chained);
    const a = sectionKey(chained.sections[0].repo_guid, chained.sections[0].kind);
    const b = sectionKey(chained.sections[1].repo_guid, chained.sections[1].kind);
    const swapped = new Map(sections);
    swapped.set(a, sections.get(b) as Uint8Array);
    swapped.set(b, sections.get(a) as Uint8Array);
    const verdict = await verifyCase(chained, { sections: swapped });
    expect(verdict.signature).toBe('valid');
    expect(verdict.ok).toBe(false);
    expect(verdict.sections.map((s) => s.status)).toEqual(['mismatch', 'mismatch']);
  });

  it('a section of the right length but other content fails on the hash, one of another length on the length', async () => {
    const records = genesis.sections[0];
    const key = sectionKey(records.repo_guid, records.kind);
    const sameLength = fromHex(records.bytesHex);
    sameLength[0] ^= 1;
    const a = await verifyCase(genesis, {
      sections: new Map(sectionMap(genesis)).set(key, sameLength),
    });
    expect(a.sections[0]).toMatchObject({
      status: 'mismatch',
      reason: expect.stringContaining('sha256'),
    });
    const b = await verifyCase(genesis, {
      sections: new Map(sectionMap(genesis)).set(key, new Uint8Array([1, 2, 3])),
    });
    expect(b.sections[0]).toMatchObject({
      status: 'mismatch',
      reason: expect.stringContaining('length'),
    });
  });

  it('a section the header does not list is reported and fails the batch', async () => {
    const extra = new Map(sectionMap(heartbeat)).set(
      sectionKey('11111111-1111-4111-8111-111111111111', 'records'),
      new Uint8Array([1])
    );
    const verdict = await verifyCase(heartbeat, { sections: extra });
    expect(verdict.unexpected).toEqual(['11111111-1111-4111-8111-111111111111/records']);
    expect(verdict.ok).toBe(false);
  });

  it('a wrong prev_hash is a gap with prevMismatch, a wrong seq a gap with seqSkipped', async () => {
    const wrongHash = await verifyCase(heartbeat, {
      prev: { seq: 0, hash: 'f'.repeat(64) },
    });
    expect(wrongHash.chain).toEqual({
      kind: 'gap',
      seqSkipped: false,
      prevMismatch: true,
      expectedSeq: 1,
    });
    expect(wrongHash.ok).toBe(true);
    const skipped = await verifyCase(heartbeat, { prev: { seq: 5, hash: genesis.batchHashHex } });
    expect(skipped.chain).toEqual({
      kind: 'gap',
      seqSkipped: true,
      prevMismatch: false,
      expectedSeq: 6,
    });
  });

  it('control: the right prev links', async () => {
    const verdict = await verifyCase(heartbeat, { prev: { seq: 0, hash: genesis.batchHashHex } });
    expect(verdict.chain).toEqual({ kind: 'linked' });
  });

  it('a first batch must be genesis; a later batch must not claim genesis', () => {
    expect(checkChain(null, genesis.header)).toEqual({ kind: 'first' });
    expect(checkChain(null, heartbeat.header)).toMatchObject({ kind: 'gap', prevMismatch: true });
    const claimsGenesis = { ...heartbeat.header, prev_hash: GENESIS_HASH };
    expect(checkChain({ seq: 0, hash: genesis.batchHashHex }, claimsGenesis)).toMatchObject({
      kind: 'gap',
      prevMismatch: true,
    });
  });

  it('a batch signed by another key does not verify', async () => {
    const other = await importSpoolPublicKey(
      fromHex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
    );
    const verdict = await verifyBatch({
      headerBytes: fromHex(genesis.headerBytesHex),
      signature: fromHex(genesis.signatureHex),
      publicKey: other,
      sections: sectionMap(genesis),
    });
    expect(verdict.signature).toBe('invalid');
    expect(verdict.ok).toBe(false);
  });
});

describe('redaction', () => {
  it('a pii section removed with its hash kept verifies as redacted, and the batch hash is unchanged', async () => {
    const sections = sectionMap(genesis);
    sections.delete(sectionKey(genesis.sections[1].repo_guid, 'pii'));
    const verdict = await verifyCase(genesis, { sections });
    expect(verdict.ok).toBe(true);
    expect(verdict.sections.map((s) => s.status)).toEqual(['ok', 'redacted']);
    expect(verdict.hash).toBe(genesis.batchHashHex);
  });

  it('control: a records section that is gone is missing, not redacted', async () => {
    const sections = sectionMap(genesis);
    sections.delete(sectionKey(genesis.sections[0].repo_guid, 'records'));
    const verdict = await verifyCase(genesis, { sections });
    expect(verdict.ok).toBe(false);
    expect(verdict.sections.map((s) => s.status)).toEqual(['missing', 'ok']);
  });

  it('a pii section present with the wrong bytes is a mismatch, not a redaction', async () => {
    const key = sectionKey(genesis.sections[1].repo_guid, 'pii');
    const verdict = await verifyCase(genesis, {
      sections: new Map(sectionMap(genesis)).set(key, new Uint8Array(22)),
    });
    expect(verdict.sections[1].status).toBe('mismatch');
    expect(verdict.ok).toBe(false);
  });
});

describe('header encoding', () => {
  const header: BatchHeader = {
    schema: BATCH_SCHEMA,
    machine_id: 'm-1',
    seq: 3,
    prev_hash: GENESIS_HASH,
    cut_at: '2026-11-23T10:00:00Z',
    level: 'basic',
    sections: [],
  };

  it('control: a valid header round-trips', () => {
    expect(decodeHeader(encodeHeader(header))).toEqual({ ok: true, header });
  });

  it.each([
    ['a fraction of seconds', { cut_at: '2026-11-23T10:00:00.5Z' }],
    ['nanoseconds', { cut_at: '2026-11-23T10:00:00.123456789Z' }],
    ['the standard level', { level: 'standard' as const }],
    ['the off level of a batch no repo records into', { level: 'off' as const }],
  ])('control: accepts %s', (_name, patch) => {
    const h = { ...header, ...patch };
    expect(decodeHeader(encodeHeader(h))).toEqual({ ok: true, header: h });
  });

  it('refuses a non-canonical byte form of a valid header', () => {
    const spaced = new TextEncoder().encode(JSON.stringify(header, null, 1));
    expect(decodeHeader(spaced)).toEqual({ ok: false, error: 'header is not in canonical form' });
    const { seq, ...rest } = header;
    const reordered = new TextEncoder().encode(JSON.stringify({ seq, ...rest, sections: [] }));
    expect(decodeHeader(reordered).ok).toBe(false);
  });

  it('refuses bytes that are not UTF-8 and not an object', () => {
    expect(decodeHeader(new Uint8Array([0xff, 0xfe]))).toEqual({
      ok: false,
      error: 'header is not valid UTF-8',
    });
    expect(decodeHeader(new TextEncoder().encode('[]')).ok).toBe(false);
  });

  const bad: [string, Partial<BatchHeader>][] = [
    ['a real date is required', { cut_at: '2026-02-30T00:00:00Z' }],
    ['a fraction with a trailing zero is refused', { cut_at: '2026-11-23T10:00:00.50Z' }],
    ['an all-zero fraction is refused', { cut_at: '2026-11-23T10:00:00.0Z' }],
    ['a fraction past nanoseconds is refused', { cut_at: '2026-11-23T10:00:00.1234567891Z' }],
    ['a zone offset is refused', { cut_at: '2026-11-23T10:00:00+01:00' }],
    ['a negative seq is refused', { seq: -1 }],
    ['a fractional seq is refused', { seq: 1.5 }],
    ['a short prev_hash is refused', { prev_hash: 'abc' }],
    ['an uppercase prev_hash is refused', { prev_hash: 'A'.repeat(64) }],
    ['an unknown level is refused', { level: 'verbose' as never }],
    ['a machine id with a quote is refused', { machine_id: 'a"b' }],
    ['an empty machine id is refused', { machine_id: '' }],
    ['another schema is refused', { schema: 2 as never }],
    ['a string schema is refused', { schema: '1' as never }],
  ];
  it.each(bad)('%s', (_name, patch) => {
    expect(() => encodeHeader({ ...header, ...patch })).toThrow();
  });

  const section = {
    repo_guid: '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b',
    kind: 'records' as const,
    sha256: 'a'.repeat(64),
    bytes: 10,
  };

  it('refuses a duplicate section, an uppercase GUID and a total over the batch limit', () => {
    expect(() => encodeHeader({ ...header, sections: [section, section] })).toThrow(/duplicate/);
    expect(() =>
      encodeHeader({
        ...header,
        sections: [{ ...section, repo_guid: section.repo_guid.toUpperCase() }],
      })
    ).toThrow(/UUID/);
    expect(() =>
      encodeHeader({
        ...header,
        sections: [
          { ...section, bytes: MAX_BATCH_BYTES },
          { ...section, kind: 'pii', bytes: 1 },
        ],
      })
    ).toThrow(/limit/);
  });

  it('accepts an empty repo_guid for machine-level records and still refuses a malformed one', () => {
    const machine = { ...section, repo_guid: '' };
    expect(decodeHeader(encodeHeader({ ...header, sections: [machine, section] })).ok).toBe(true);
    expect(() => encodeHeader({ ...header, sections: [{ ...section, repo_guid: 'x' }] })).toThrow(
      /UUID/
    );
    expect(() => encodeHeader({ ...header, sections: [machine, machine] })).toThrow(/duplicate/);
  });

  it('control: a total exactly at the limit is accepted', () => {
    expect(() =>
      encodeHeader({ ...header, sections: [{ ...section, bytes: MAX_BATCH_BYTES }] })
    ).not.toThrow();
  });

  it('refuses an extra field', () => {
    const extra = new TextEncoder().encode(
      new TextDecoder().decode(encodeHeader(header)).replace('"sections"', '"note":"x","sections"')
    );
    expect(decodeHeader(extra).ok).toBe(false);
  });
});

describe('signature text', () => {
  it('round-trips base64 and reports a malformed value as null', () => {
    const sig = fromHex(genesis.signatureHex);
    expect(decodeSignature(encodeSignature(sig))).toEqual(sig);
    expect(decodeSignature('***')).toBeNull();
  });
});

describe('forensics claim', () => {
  it('accepts level up to maxLevel and refuses level above it', () => {
    expect(
      ForensicsClaimSchema.safeParse({ enabled: true, level: 'basic', maxLevel: 'full' }).success
    ).toBe(true);
    expect(
      ForensicsClaimSchema.safeParse({ enabled: true, level: 'full', maxLevel: 'full' }).success
    ).toBe(true);
    expect(
      ForensicsClaimSchema.safeParse({ enabled: true, level: 'full', maxLevel: 'basic' }).success
    ).toBe(false);
  });

  it('refuses a missing field and an unknown field', () => {
    expect(ForensicsClaimSchema.safeParse({ enabled: true, level: 'basic' }).success).toBe(false);
    expect(
      ForensicsClaimSchema.safeParse({ enabled: true, level: 'basic', maxLevel: 'full', x: 1 })
        .success
    ).toBe(false);
  });

  it('orders and clamps levels', () => {
    expect(levelRank('basic')).toBeLessThan(levelRank('standard'));
    expect(levelRank('standard')).toBeLessThan(levelRank('full'));
    expect(clampLevel('full', 'standard')).toBe('standard');
    expect(levelWithinClaim('standard', { enabled: true, level: 'full', maxLevel: 'full' })).toBe(
      true
    );
    expect(levelWithinClaim('full', { enabled: true, level: 'standard', maxLevel: 'full' })).toBe(
      false
    );
    expect(clampLevel('full', 'basic')).toBe('basic');
    expect(clampLevel('basic', 'full')).toBe('basic');
    expect(clampLevel('full', 'full')).toBe('full');
  });

  it('effectiveLevel is null without a claim or when disabled, and honours the cap', () => {
    const claim = { enabled: true, level: 'full', maxLevel: 'full' } as const;
    expect(effectiveLevel(undefined)).toBeNull();
    expect(effectiveLevel({ ...claim, enabled: false })).toBeNull();
    expect(effectiveLevel(claim)).toBe('full');
    expect(effectiveLevel(claim, 'basic')).toBe('basic');
  });

  it('levelWithinClaim allows a batch at or below the claim level only while enabled', () => {
    const claim = { enabled: true, level: 'basic', maxLevel: 'full' } as const;
    expect(levelWithinClaim('basic', claim)).toBe(true);
    expect(levelWithinClaim('full', claim)).toBe(false);
    expect(levelWithinClaim('basic', { ...claim, enabled: false })).toBe(false);
    expect(levelWithinClaim('basic', undefined)).toBe(false);
  });
});
