/**
 * Append-only JSONL audit log for config mutations + edit-session events.
 *
 * One file per config at `<configdir>/audit.log.jsonl`, mode 0600, rotated
 * at 10 MB (single rotation: `audit.log.jsonl.1` overwritten). Each line is
 * a JSON object; consecutive lines form a SHA-256 hash chain — tampering
 * with any line invalidates all subsequent `prevHash` values, detectable
 * via `verifyChain`.
 *
 * Entries never contain secret values — only pointers, outcomes, actor
 * signals. The CI gate `check:ci-audit-never-logs-values` is a lint rule
 * (Step 15) that forbids plaintext in audit emissions.
 */

import { createHash } from 'node:crypto';
import {
  appendFileSync,
  closeSync,
  existsSync,
  fstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  renameSync,
  statSync,
} from 'node:fs';
import { dirname } from 'node:path';
import { isAgentEnvironment } from '../utils/agent-guard.js';

const ROTATE_BYTES = 10 * 1024 * 1024; // 10 MB
const AGENT_ENV_VARS = [
  'REDIACC_AGENT',
  'CLAUDECODE',
  'GEMINI_CLI',
  'COPILOT_CLI',
  'CURSOR_TRACE_ID',
] as const;

export type AuditOutcome =
  | 'ok'
  | 'refused'
  | 'precondition_failed'
  | 'rotate_no_knowledge'
  | 'reveal_granted'
  | 'edit_open'
  | 'edit_apply'
  | 'edit_abort';

export interface AuditEntry {
  ts: string;
  actor: { kind: 'human' | 'agent'; agentSignals: string[] };
  command: string;
  paths: string[];
  outcome: AuditOutcome;
  configId?: string;
  configVersion?: number;
  prevHash: string;
  reason?: string;
}

function detectedAgentSignals(): string[] {
  const signals: string[] = [];
  for (const v of AGENT_ENV_VARS) {
    if (process.env[v]) signals.push(v);
  }
  return signals;
}

const CHUNK_BYTES = 64 * 1024;
const LF = 0x0a;
const CR = 0x0d;

/** Seek backwards from EOF to skip any trailing newline bytes (\n or \r). */
function trimTrailingNewlines(fd: number, size: number): number {
  let end = size;
  const tail = Buffer.alloc(1);
  while (end > 0) {
    readSync(fd, tail, 0, 1, end - 1);
    if (tail[0] !== LF && tail[0] !== CR) break;
    end -= 1;
  }
  return end;
}

/** Read [start,end) from fd into a Buffer and return it. */
function readSlice(fd: number, start: number, end: number): Buffer {
  const buf = Buffer.alloc(end - start);
  readSync(fd, buf, 0, buf.length, start);
  return buf;
}

/**
 * Find the byte offset of the last LF in [start, end); if none, returns -1
 * and the caller should extend the window backwards.
 */
function findLastLineStart(fd: number, end: number): { absStart: number; line: string } {
  let start = Math.max(0, end - CHUNK_BYTES);
  for (;;) {
    const chunk = readSlice(fd, start, end);
    const lf = chunk.lastIndexOf(LF);
    if (lf !== -1) {
      const absStart = start + lf + 1;
      const line = chunk
        .subarray(lf + 1, end - start)
        .toString('utf8')
        .trim();
      return { absStart, line };
    }
    if (start === 0) {
      return {
        absStart: 0,
        line: chunk
          .subarray(0, end - start)
          .toString('utf8')
          .trim(),
      };
    }
    start = Math.max(0, start - CHUNK_BYTES);
  }
}

/**
 * Hash of the last non-empty JSONL line. Seeks from EOF backwards in
 * CHUNK_BYTES windows; avoids pulling a 10 MB rotation into memory just
 * to hash one line.
 */
function readLastHash(logPath: string): string {
  if (!existsSync(logPath)) return 'sha256:0';
  let fd: number | undefined;
  try {
    fd = openSync(logPath, 'r');
    const size = fstatSync(fd).size;
    if (size === 0) return 'sha256:0';
    const end = trimTrailingNewlines(fd, size);
    if (end === 0) return 'sha256:0';
    const { line } = findLastLineStart(fd, end);
    if (!line) return 'sha256:0';
    return `sha256:${sha256(line)}`;
  } catch {
    return 'sha256:corrupt';
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
}

function sha256(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

function rotateIfNeeded(logPath: string): void {
  if (!existsSync(logPath)) return;
  try {
    const stats = statSync(logPath);
    if (stats.size >= ROTATE_BYTES) {
      renameSync(logPath, `${logPath}.1`);
    }
  } catch {
    /* ignore — best-effort */
  }
}

export interface AuditEventDraft {
  command: string;
  paths: string[];
  outcome: AuditOutcome;
  configId?: string;
  configVersion?: number;
  reason?: string;
}

/**
 * Append an audit entry to the log for a given config directory.
 * Creates the file if missing, rotates at 10 MB, and updates the hash chain.
 */
export function auditLog(configDir: string, draft: AuditEventDraft): void {
  const logPath = `${configDir}/audit.log.jsonl`;
  mkdirSync(dirname(logPath), { recursive: true });
  rotateIfNeeded(logPath);
  const prevHash = readLastHash(logPath);
  const entry: AuditEntry = {
    ts: new Date().toISOString(),
    actor: {
      kind: isAgentEnvironment() ? 'agent' : 'human',
      agentSignals: detectedAgentSignals(),
    },
    command: draft.command,
    paths: draft.paths,
    outcome: draft.outcome,
    configId: draft.configId,
    configVersion: draft.configVersion,
    prevHash,
    reason: draft.reason,
  };
  const line = `${JSON.stringify(entry)}\n`;
  appendFileSync(logPath, line, { mode: 0o600 });
}

/**
 * Verify the integrity of an audit log's SHA-256 chain.
 * Returns the 1-based line number of the first break, or `null` if intact.
 */
export function verifyChain(logPath: string): number | null {
  if (!existsSync(logPath)) return null;
  const text = readFileSync(logPath, 'utf8');
  const lines = text.trim().split('\n').filter(Boolean);
  let expectedPrev = 'sha256:0';
  for (let i = 0; i < lines.length; i++) {
    let entry: AuditEntry;
    try {
      entry = JSON.parse(lines[i]) as AuditEntry;
    } catch {
      return i + 1;
    }
    if (entry.prevHash !== expectedPrev) return i + 1;
    expectedPrev = `sha256:${sha256(lines[i])}`;
  }
  return null;
}

/** Read and parse an audit log. Returns entries in file order. */
export function readAuditLog(logPath: string): AuditEntry[] {
  if (!existsSync(logPath)) return [];
  const text = readFileSync(logPath, 'utf8');
  const out: AuditEntry[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      out.push(JSON.parse(line) as AuditEntry);
    } catch {
      /* skip malformed lines in reader; verifyChain detects */
    }
  }
  return out;
}
