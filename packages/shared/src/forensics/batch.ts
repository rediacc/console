/**
 * Forensics batch format (D1 of PLAN-forensics-shipping), mirrored in Go by
 * renet's netaudit shipper; both read `__fixtures__/batch-vectors.json`.
 *
 * A batch is a signed header plus sections. The header names each section by repo
 * and kind with its SHA-256 and byte length; each section is compressed on its own
 * and stored as opaque bytes. The header is Ed25519-signed with the machine's
 * spool key. Hash chain: `batch hash = SHA-256(headerBytes || signature)`, and the
 * next batch carries it as `prev_hash` (`genesis` for the first).
 *
 * Because the signature covers only the header, a section can be removed later
 * without breaking it: a `pii` section dropped after 30 days still has its hash in
 * the signed header, so the verifier reports `redacted` instead of a broken chain.
 * A `records` section that is gone is `missing`, never `redacted`.
 *
 * Header bytes are canonical, and canonical means what renet's `spool.Encode`
 * writes through `encoding/json` (private/renet/pkg/netaudit/spool/batch.go):
 * compact JSON, keys in the order `encodeHeader` writes them, strings restricted
 * to characters that need no escaping, integers without fraction or exponent, and
 * `cut_at` in Go's RFC 3339 nanosecond form (UTC, fraction only when non-zero,
 * trailing zeros trimmed). A decoder re-encodes and refuses bytes that differ, so
 * one header has exactly one byte form and Go and TypeScript agree on what was
 * signed. A section with an empty `repo_guid` holds machine-level records (the
 * spool's gap records), and the header `level` is `off` when no repo records.
 */
import { z } from 'zod';
import { fromBase64, toBase64 } from '../config-crypto/aes.js';
import { FORENSICS_LEVELS } from './claim.js';

/** The header schema version, `spool.SchemaVersion` in Go. */
export const BATCH_SCHEMA = 1;
export const GENESIS_HASH = 'genesis';
/** Most bytes a batch may hold across all sections (D3). */
export const MAX_BATCH_BYTES = 4 * 1024 * 1024;
/** Most sections one header may list. */
export const MAX_SECTIONS = 512;

export const SECTION_KINDS = ['records', 'pii'] as const;
export type SectionKind = (typeof SECTION_KINDS)[number];

/** A header's level: the highest effective level of any repo in the batch, `off` when none records. */
export const BATCH_LEVELS = ['off', ...FORENSICS_LEVELS] as const;
export type BatchLevel = (typeof BATCH_LEVELS)[number];

/** The `repo_guid` of a machine-level section. */
export const MACHINE_SECTION = '';

const HEX64 = /^[0-9a-f]{64}$/;
const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
/** Go's time.RFC3339Nano for a UTC instant: a fraction only when non-zero, without trailing zeros. */
const CUT_AT = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d{0,8}[1-9])?Z$/;

const SectionSchema = z.strictObject({
  repo_guid: z
    .string()
    .refine(
      (s) => s === MACHINE_SECTION || GUID.test(s),
      'repo_guid must be a lowercase UUID, or empty for machine-level records'
    ),
  kind: z.enum(SECTION_KINDS),
  sha256: z.string().regex(HEX64, 'sha256 must be 64 lowercase hex characters'),
  bytes: z.number().int().min(0).max(MAX_BATCH_BYTES),
});
type BatchSection = z.infer<typeof SectionSchema>;

export type { BatchSection };

export const BatchHeaderSchema = z
  .strictObject({
    schema: z.literal(BATCH_SCHEMA),
    machine_id: z
      .string()
      .regex(/^[A-Za-z0-9._:-]{1,128}$/, 'machine_id has a character outside A-Za-z0-9._:-'),
    seq: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
    prev_hash: z.union([z.literal(GENESIS_HASH), z.string().regex(HEX64)]),
    cut_at: z
      .string()
      .regex(CUT_AT, 'cut_at must be UTC in Go RFC 3339 nanosecond form, as 2026-01-02T03:04:05.5Z')
      .refine((s) => {
        const seconds = CUT_AT.exec(s)?.[1];
        if (seconds === undefined) return false;
        const t = Date.parse(`${seconds}Z`);
        return !Number.isNaN(t) && new Date(t).toISOString().slice(0, 19) === seconds;
      }, 'cut_at is not a real date'),
    level: z.enum(BATCH_LEVELS),
    sections: z.array(SectionSchema).max(MAX_SECTIONS),
  })
  .superRefine((header, ctx) => {
    const seen = new Set<string>();
    let total = 0;
    for (const [i, section] of header.sections.entries()) {
      const key = sectionKey(section.repo_guid, section.kind);
      if (seen.has(key)) {
        ctx.addIssue({
          code: 'custom',
          path: ['sections', i],
          message: `duplicate section ${key}`,
        });
      }
      seen.add(key);
      total += section.bytes;
    }
    if (total > MAX_BATCH_BYTES) {
      ctx.addIssue({
        code: 'custom',
        path: ['sections'],
        message: `sections total ${total} bytes, over the ${MAX_BATCH_BYTES} byte limit`,
      });
    }
  });
type BatchHeader = z.infer<typeof BatchHeaderSchema>;

export type { BatchHeader };

/** The map key of a section: `<repo_guid>/<kind>`. */
export function sectionKey(repoGuid: string, kind: SectionKind): string {
  return `${repoGuid}/${kind}`;
}

export class BatchFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BatchFormatError';
  }
}

const text = new TextEncoder();

/** `JSON.stringify` of a string the schema already restricted to characters JSON leaves as they are. */
function str(value: string): string {
  return `"${value}"`;
}

/** Canonical header bytes. Throws BatchFormatError when the header does not satisfy the schema. */
export function encodeHeader(header: BatchHeader): Uint8Array {
  const checked = BatchHeaderSchema.safeParse(header);
  if (!checked.success) {
    throw new BatchFormatError(
      checked.error.issues.map((i) => `${i.path.join('.') || 'header'}: ${i.message}`).join('; ')
    );
  }
  const h = checked.data;
  // `schema` is a number, written as Go's encoding/json writes an int.
  const sections = h.sections.map(
    (s) =>
      `{"repo_guid":${str(s.repo_guid)},"kind":${str(s.kind)},"sha256":${str(s.sha256)},"bytes":${s.bytes}}`
  );
  return text.encode(
    `{"schema":${h.schema},"machine_id":${str(h.machine_id)},"seq":${h.seq},` +
      `"prev_hash":${str(h.prev_hash)},"cut_at":${str(h.cut_at)},"level":${str(h.level)},` +
      `"sections":[${sections.join(',')}]}`
  );
}

export type HeaderDecode = { ok: true; header: BatchHeader } | { ok: false; error: string };

/** Parse header bytes. Refuses invalid JSON, a schema violation and any byte form other than the canonical one. */
export function decodeHeader(bytes: Uint8Array): HeaderDecode {
  let source: string;
  try {
    source = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    return { ok: false, error: 'header is not valid UTF-8' };
  }
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    return { ok: false, error: 'header is not valid JSON' };
  }
  const parsed = BatchHeaderSchema.safeParse(value);
  if (!parsed.success) {
    return {
      ok: false,
      error: parsed.error.issues
        .map((i) => `${i.path.join('.') || 'header'}: ${i.message}`)
        .join('; '),
    };
  }
  if (new TextDecoder().decode(encodeHeader(parsed.data)) !== source) {
    return { ok: false, error: 'header is not in canonical form' };
  }
  return { ok: true, header: parsed.data };
}

/** Copy into a fresh ArrayBuffer-backed array, the form Web Crypto's types accept. */
function plain(bytes: Uint8Array): Uint8Array<ArrayBuffer> {
  return new Uint8Array(bytes);
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('');
}

export function sha256Hex(bytes: Uint8Array): Promise<string> {
  return crypto.subtle.digest('SHA-256', plain(bytes)).then(hex);
}

/** The batch hash the next batch chains to: SHA-256 of the header bytes followed by the signature bytes. */
export function batchHash(headerBytes: Uint8Array, signature: Uint8Array): Promise<string> {
  const joined = new Uint8Array(headerBytes.length + signature.length);
  joined.set(headerBytes, 0);
  joined.set(signature, headerBytes.length);
  return sha256Hex(joined);
}

/** Import a machine's spool public key: the raw 32 bytes of an Ed25519 key. */
export function importSpoolPublicKey(raw: Uint8Array): Promise<CryptoKey> {
  if (raw.length !== 32) {
    return Promise.reject(
      new BatchFormatError(`an Ed25519 public key is 32 bytes, got ${raw.length}`)
    );
  }
  return crypto.subtle.importKey('raw', plain(raw), { name: 'Ed25519' }, false, ['verify']);
}

/** True when `signature` is a valid Ed25519 signature of `headerBytes` under `publicKey`. A malformed signature is false. */
export function verifyHeaderSignature(
  publicKey: CryptoKey,
  headerBytes: Uint8Array,
  signature: Uint8Array
): Promise<boolean> {
  if (signature.length !== 64) return Promise.resolve(false);
  return crypto.subtle.verify({ name: 'Ed25519' }, publicKey, plain(signature), plain(headerBytes));
}

export function encodeSignature(signature: Uint8Array): string {
  return toBase64(signature);
}

export function decodeSignature(encoded: string): Uint8Array | null {
  try {
    return fromBase64(encoded);
  } catch {
    return null;
  }
}

/** Where a machine's chain stands: the last batch the verifier or the server accepted. */
export interface ChainPoint {
  seq: number;
  hash: string;
}

export type ChainCheck =
  | { kind: 'first' }
  | { kind: 'linked' }
  | { kind: 'gap'; seqSkipped: boolean; prevMismatch: boolean; expectedSeq: number | null };

/**
 * How a header links to the previous batch. A first batch has `prev_hash`
 * `genesis`. A later one links when its seq is `prev.seq + 1` and its `prev_hash`
 * is `prev.hash`. Anything else is a `gap`: visible, recorded, never hidden (D3).
 */
export function checkChain(prev: ChainPoint | null, header: BatchHeader): ChainCheck {
  if (prev === null) {
    return header.prev_hash === GENESIS_HASH
      ? { kind: 'first' }
      : { kind: 'gap', seqSkipped: false, prevMismatch: true, expectedSeq: null };
  }
  const seqSkipped = header.seq !== prev.seq + 1;
  const prevMismatch = header.prev_hash !== prev.hash;
  if (!seqSkipped && !prevMismatch) return { kind: 'linked' };
  return { kind: 'gap', seqSkipped, prevMismatch, expectedSeq: prev.seq + 1 };
}

export type SectionStatus = 'ok' | 'redacted' | 'missing' | 'mismatch';

export interface SectionVerdict {
  key: string;
  repo_guid: string;
  kind: SectionKind;
  status: SectionStatus;
  reason?: string;
}

export interface BatchVerdict {
  /** The signature verifies, the header is canonical and every section is intact or redacted. The chain is separate. */
  ok: boolean;
  signature: 'valid' | 'invalid';
  header: BatchHeader | null;
  /** Why the header could not be read, when it could not. */
  headerError: string | null;
  /** The batch hash, present when the header decoded and the signature verified. */
  hash: string | null;
  chain: ChainCheck | null;
  sections: SectionVerdict[];
  /** Section keys supplied but not listed in the signed header. */
  unexpected: string[];
}

export interface VerifyBatchInput {
  headerBytes: Uint8Array;
  signature: Uint8Array;
  publicKey: CryptoKey;
  /** Section bytes by `sectionKey`. An absent `pii` entry is a redaction, an absent `records` entry is missing. */
  sections: ReadonlyMap<string, Uint8Array>;
  /** The previous accepted batch; null for a machine's first. Omit to skip the chain check. */
  prev?: ChainPoint | null;
}

/** Check one listed section against the bytes supplied for it (undefined when none were). */
async function verifySection(
  section: BatchSection,
  bytes: Uint8Array | undefined
): Promise<SectionVerdict> {
  const entry = {
    key: sectionKey(section.repo_guid, section.kind),
    repo_guid: section.repo_guid,
    kind: section.kind,
  };
  if (bytes === undefined) {
    return section.kind === 'pii'
      ? { ...entry, status: 'redacted' }
      : { ...entry, status: 'missing', reason: 'records section is absent' };
  }
  if (bytes.length !== section.bytes) {
    return {
      ...entry,
      status: 'mismatch',
      reason: `length ${bytes.length}, header says ${section.bytes}`,
    };
  }
  return (await sha256Hex(bytes)) === section.sha256
    ? { ...entry, status: 'ok' }
    : { ...entry, status: 'mismatch', reason: 'sha256 differs from the signed header' };
}

/** Verify one batch end to end: signature, canonical header, every section against its signed hash, and the chain link. */
export async function verifyBatch(input: VerifyBatchInput): Promise<BatchVerdict> {
  const verdict: BatchVerdict = {
    ok: false,
    signature: 'invalid',
    header: null,
    headerError: null,
    hash: null,
    chain: null,
    sections: [],
    unexpected: [],
  };

  const signed = await verifyHeaderSignature(input.publicKey, input.headerBytes, input.signature);
  verdict.signature = signed ? 'valid' : 'invalid';

  const decoded = decodeHeader(input.headerBytes);
  if (!decoded.ok) {
    verdict.headerError = decoded.error;
    return verdict;
  }
  verdict.header = decoded.header;
  if (!signed) return verdict;

  verdict.hash = await batchHash(input.headerBytes, input.signature);
  if (input.prev !== undefined) verdict.chain = checkChain(input.prev, decoded.header);

  verdict.sections = await Promise.all(
    decoded.header.sections.map((section) =>
      verifySection(section, input.sections.get(sectionKey(section.repo_guid, section.kind)))
    )
  );
  const listed = new Set(verdict.sections.map((s) => s.key));
  verdict.unexpected = [...input.sections.keys()].filter((key) => !listed.has(key));
  verdict.ok =
    verdict.sections.every((s) => s.status === 'ok' || s.status === 'redacted') &&
    verdict.unexpected.length === 0;
  return verdict;
}
