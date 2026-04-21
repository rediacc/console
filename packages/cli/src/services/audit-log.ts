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
import { appendFileSync, existsSync, readFileSync, renameSync, statSync } from 'node:fs';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { isAgentEnvironment } from '../utils/agent-guard.js';

const ROTATE_BYTES = 10 * 1024 * 1024; // 10 MB
const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI', 'CURSOR_TRACE_ID'] as const;

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

function readLastHash(logPath: string): string {
  if (!existsSync(logPath)) return 'sha256:0';
  const text = readFileSync(logPath, 'utf8');
  const lines = text.trim().split('\n').filter(Boolean);
  if (lines.length === 0) return 'sha256:0';
  try {
    const last = JSON.parse(lines[lines.length - 1]) as { prevHash?: string };
    const thisLineHash = sha256(lines[lines.length - 1]);
    return `sha256:${thisLineHash}`;
  } catch {
    return 'sha256:corrupt';
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
