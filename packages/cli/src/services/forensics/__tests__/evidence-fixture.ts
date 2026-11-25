/**
 * An evidence directory built the way the account Worker lays it out (compaction day files):
 * gzip and Ed25519 come from node:crypto and node:zlib, so nothing under test produced the
 * bytes it checks.
 */
import { generateKeyPairSync, sign } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { gzipSync } from 'node:zlib';
import {
  type BatchHeader,
  batchHash,
  encodeHeader,
  encodeSignature,
  GENESIS_HASH,
  sha256Hex,
} from '@rediacc/shared/forensics';

export const ORG = 'org-1';
export const MACHINE = 'machine-1';
export const GUID = '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b';
const SUBSCRIPTION = 'sub-1';
const RECORDS = new Uint8Array(Buffer.from('records-bytes'));

const gz = (text: string) => new Uint8Array(gzipSync(Buffer.from(text)));
const ndjson = (lines: unknown[]) => lines.map((l) => `${JSON.stringify(l)}\n`).join('');

function put(root: string, key: string, bytes: Uint8Array): void {
  const full = join(root, key);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, bytes);
}

export function auditKey(day: string): string {
  return `audit/${ORG}/days/${day}.ndjson.gz`;
}

export function repoKey(day: string): string {
  return `f/${SUBSCRIPTION}/${MACHINE}/days/${day}/repo-${GUID}.ndjson.gz`;
}

function auditDay(day: string, prev: { day: string; sha256: string } | null): Uint8Array {
  const header = {
    v: 1,
    org: ORG,
    day,
    prevDay: prev?.day ?? null,
    prevSha256: prev?.sha256 ?? GENESIS_HASH,
    count: 1,
  };
  return gz(ndjson([header, { id: `${day}-0` }]));
}

export interface Fixture {
  /** The raw 32 byte public key of the machine, as the 64 hex characters `--machine-key` takes. */
  publicKeyHex: string;
}

/** Two audit days and three signed batches of one machine on `2026-11-02`, written under `root`. */
export async function writeFixture(root: string): Promise<Fixture> {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const jwk = publicKey.export({ format: 'jwk' });
  const publicKeyHex = Buffer.from(jwk.x ?? '', 'base64url').toString('hex');

  let prev: { day: string; sha256: string } | null = null;
  for (const day of ['2026-11-01', '2026-11-02']) {
    const bytes = auditDay(day, prev);
    put(root, auditKey(day), bytes);
    prev = { day, sha256: await sha256Hex(bytes) };
  }

  const day = '2026-11-02';
  const lines: unknown[] = [];
  const sections: unknown[] = [];
  let prevHash = GENESIS_HASH;
  for (let seq = 0; seq < 3; seq++) {
    const header: BatchHeader = {
      schema: 1,
      machine_id: MACHINE,
      seq,
      prev_hash: prevHash,
      cut_at: `2026-11-02T10:00:${String(seq).padStart(2, '0')}Z`,
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
    const signature = new Uint8Array(sign(null, headerBytes, privateKey));
    const hash = await batchHash(headerBytes, signature);
    lines.push({
      seq,
      hash,
      header: encodeSignature(headerBytes),
      signature: encodeSignature(signature),
      gap: false,
    });
    sections.push({ seq, section: encodeSignature(RECORDS) });
    prevHash = hash;
  }
  put(
    root,
    `f/${SUBSCRIPTION}/${MACHINE}/days/${day}/headers.ndjson.gz`,
    gz(
      ndjson([
        { v: 1, machine: MACHINE, day, prevDay: null, prevSha256: null, repoFiles: {}, gaps: [] },
        ...lines,
      ])
    )
  );
  put(root, repoKey(day), gz(ndjson(sections)));
  return { publicKeyHex };
}

/** Replace a file's bytes with a well-formed but different gzip body. */
export function rewrite(root: string, key: string, text: string): void {
  put(root, key, gz(text));
}
