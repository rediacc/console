/**
 * Evidence verification (D5 of PLAN-forensics-investigation), in Node and the
 * browser through WebCrypto and the stream codecs.
 *
 * Two chains are recomputed from raw bytes the server hands over:
 * - audit-r2 day files: each file's first line names the previous day and the
 *   SHA-256 of that file's bytes, so a changed file shows up as an edit at its own
 *   day when the next file's link no longer matches, and a removed file as a gap;
 * - plan 2 batches: Ed25519-signed headers chained by `prev_hash`, per machine.
 *
 * The report is what an export stamps: the window, the chain heads, every gap and
 * edit, and who verified with which tool version. A reader other than the writer
 * can rerun it over the same bytes and must reach the same report.
 */
import {
  batchHash,
  type ChainPoint,
  decodeHeader,
  GENESIS_HASH,
  sha256Hex,
  verifyBatch,
} from './batch.js';

/** Largest evidence set the page verifies in the browser; above it the CLI runs the same module. */
export const BROWSER_VERIFY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024;

export interface AuditDayInput {
  /** `yyyy-mm-dd`. */
  day: string;
  /** The gzip bytes exactly as the bucket serves them. */
  bytes: Uint8Array;
}

export interface BatchInput {
  headerBytes: Uint8Array;
  signature: Uint8Array;
  /** Section bytes by `sectionKey`; an absent `pii` entry is a redaction. */
  sections: ReadonlyMap<string, Uint8Array>;
}

export type EvidenceSource = 'audit' | 'forensics';

export interface EvidenceFinding {
  source: EvidenceSource;
  /** The day (`2026-11-01`) or the batch (`machine-1#7`) the finding is about. */
  ref: string;
  reason: string;
}

export interface VerifyHeads {
  audit: { day: string; sha256: string } | null;
  batches: { machineId: string; seq: number; hash: string }[];
}

export interface VerificationReport {
  window: { from: string; to: string };
  heads: VerifyHeads;
  gaps: EvidenceFinding[];
  edits: EvidenceFinding[];
  verifiedAt: string;
  verifier: string;
  toolVersion: string;
  /** True when no gap and no edit was found. */
  clean: boolean;
}

export interface VerifyWindowInput {
  org: string;
  window: { from: string; to: string };
  /** Day files in the window, with the file before it when one exists so the first link has something to compare against. */
  auditDays: readonly AuditDayInput[];
  batches: readonly BatchInput[];
  /** The Ed25519 public key of a machine's spool; null when the machine is unknown. */
  publicKeyFor: (machineId: string) => Promise<CryptoKey | null>;
  verifier: string;
  toolVersion: string;
  now?: () => Date;
}

interface DayHeader {
  v: number;
  org: string;
  day: string;
  prevDay: string | null;
  prevSha256: string;
  count: number;
}

async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as Uint8Array<ArrayBuffer>])
    .stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Check the audit day files in day order. */
export async function verifyAuditDays(
  org: string,
  files: readonly AuditDayInput[]
): Promise<{ head: VerifyHeads['audit']; gaps: EvidenceFinding[]; edits: EvidenceFinding[] }> {
  const gaps: EvidenceFinding[] = [];
  const edits: EvidenceFinding[] = [];
  const sorted = [...files].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
  let previous: { day: string; sha256: string } | null = null;
  let head: VerifyHeads['audit'] = null;

  for (const file of sorted) {
    const sha256 = await sha256Hex(file.bytes);
    let header: DayHeader | null = null;
    try {
      const lines = new TextDecoder()
        .decode(await gunzip(file.bytes))
        .trim()
        .split('\n');
      header = JSON.parse(lines[0] ?? '') as DayHeader;
      if (header.org !== org || header.day !== file.day) {
        edits.push({ source: 'audit', ref: file.day, reason: 'header names another org or day' });
      }
      if (header.count !== lines.length - 1) {
        edits.push({
          source: 'audit',
          ref: file.day,
          reason: `header count ${header.count} but ${lines.length - 1} event lines`,
        });
      }
    } catch {
      edits.push({ source: 'audit', ref: file.day, reason: 'file does not decode' });
    }

    if (header !== null) {
      if (previous === null) {
        if (header.prevDay === null && header.prevSha256 !== GENESIS_HASH) {
          edits.push({ source: 'audit', ref: file.day, reason: 'first file does not start from genesis' });
        }
      } else if (header.prevDay !== previous.day) {
        gaps.push({
          source: 'audit',
          ref: header.prevDay ?? 'genesis',
          reason: `day file missing between ${previous.day} and ${file.day}`,
        });
      } else if (header.prevSha256 !== previous.sha256) {
        edits.push({
          source: 'audit',
          ref: previous.day,
          reason: `file changed after ${file.day} recorded its hash`,
        });
      }
    }
    previous = { day: file.day, sha256 };
    head = previous;
  }
  return { head, gaps, edits };
}

/** Check batches per machine in sequence order: signature, sections, then the chain link. */
export async function verifyBatchChains(
  batches: readonly BatchInput[],
  publicKeyFor: (machineId: string) => Promise<CryptoKey | null>
): Promise<{ heads: VerifyHeads['batches']; gaps: EvidenceFinding[]; edits: EvidenceFinding[] }> {
  const gaps: EvidenceFinding[] = [];
  const edits: EvidenceFinding[] = [];
  const byMachine = new Map<string, { seq: number; input: BatchInput }[]>();

  for (const input of batches) {
    const decoded = decodeHeader(input.headerBytes);
    if (!decoded.ok) {
      edits.push({ source: 'forensics', ref: 'unreadable', reason: `header: ${decoded.error}` });
      continue;
    }
    const list = byMachine.get(decoded.header.machine_id) ?? [];
    list.push({ seq: decoded.header.seq, input });
    byMachine.set(decoded.header.machine_id, list);
  }

  const heads: VerifyHeads['batches'] = [];
  for (const [machineId, list] of [...byMachine].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    list.sort((a, b) => a.seq - b.seq);
    const key = await publicKeyFor(machineId);
    let prev: ChainPoint | null = null;
    let first = true;
    for (const { seq, input } of list) {
      const ref = `${machineId}#${seq}`;
      if (key === null) {
        edits.push({ source: 'forensics', ref, reason: 'no public key for this machine' });
        continue;
      }
      const verdict = await verifyBatch({
        headerBytes: input.headerBytes,
        signature: input.signature,
        publicKey: key,
        sections: input.sections,
        // The window's first batch has no predecessor to compare against unless it is the genesis one.
        ...(first ? {} : { prev }),
      });
      if (verdict.signature === 'invalid') {
        edits.push({ source: 'forensics', ref, reason: 'signature does not verify' });
      }
      for (const section of verdict.sections) {
        if (section.status === 'mismatch') {
          edits.push({
            source: 'forensics',
            ref,
            reason: `section ${section.key} changed: ${section.reason ?? 'hash differs'}`,
          });
        } else if (section.status === 'missing') {
          gaps.push({ source: 'forensics', ref, reason: `section ${section.key} is absent` });
        }
      }
      if (verdict.chain?.kind === 'gap') {
        if (verdict.chain.seqSkipped) {
          gaps.push({
            source: 'forensics',
            ref,
            reason: `batches ${verdict.chain.expectedSeq ?? '?'} to ${seq - 1} are missing`,
          });
        } else {
          edits.push({ source: 'forensics', ref, reason: 'prev_hash does not match the previous batch' });
        }
      }
      if (first && seq === 0 && decodeFirst(input) !== GENESIS_HASH) {
        edits.push({ source: 'forensics', ref, reason: 'first batch does not start from genesis' });
      }
      first = false;
      const hash = await batchHash(input.headerBytes, input.signature);
      prev = { seq, hash };
    }
    // The newest batch of a machine is its head.
    if (prev !== null) heads.push({ machineId, seq: prev.seq, hash: prev.hash });
  }
  return { heads, gaps, edits };
}

function decodeFirst(input: BatchInput): string | null {
  const decoded = decodeHeader(input.headerBytes);
  return decoded.ok ? decoded.header.prev_hash : null;
}

/** Verify both chains for one window and produce the report an export stamps. */
export async function verifyWindow(input: VerifyWindowInput): Promise<VerificationReport> {
  const audit = await verifyAuditDays(input.org, input.auditDays);
  const forensics = await verifyBatchChains(input.batches, input.publicKeyFor);
  const gaps = [...audit.gaps, ...forensics.gaps];
  const edits = [...audit.edits, ...forensics.edits];
  return {
    window: input.window,
    heads: { audit: audit.head, batches: forensics.heads },
    gaps,
    edits,
    verifiedAt: (input.now?.() ?? new Date()).toISOString(),
    verifier: input.verifier,
    toolVersion: input.toolVersion,
    clean: gaps.length === 0 && edits.length === 0,
  };
}
