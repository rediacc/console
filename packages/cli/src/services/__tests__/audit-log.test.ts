/**
 * Audit log tests — append, chain verification, tamper detection.
 */

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { auditLog, readAuditLog, verifyChain } from '../audit-log.js';
import { _resetCache as resetAgentCache } from '../../utils/agent-guard.js';

describe('auditLog', () => {
  let dir: string;
  let logPath: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'rdc-audit-'));
    logPath = join(dir, 'audit.log.jsonl');
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('creates the file on first append', () => {
    auditLog(dir, {
      command: 'config field set',
      paths: ['/credentials/cfDnsApiToken'],
      outcome: 'ok',
      configId: 'c1',
      configVersion: 2,
    });
    const entries = readAuditLog(logPath);
    expect(entries.length).toBe(1);
    expect(entries[0].command).toBe('config field set');
    expect(entries[0].paths).toEqual(['/credentials/cfDnsApiToken']);
    expect(entries[0].outcome).toBe('ok');
    expect(entries[0].prevHash).toBe('sha256:0');
  });

  it('chains subsequent entries via prevHash', () => {
    auditLog(dir, { command: 'a', paths: [], outcome: 'ok' });
    auditLog(dir, { command: 'b', paths: [], outcome: 'ok' });
    auditLog(dir, { command: 'c', paths: [], outcome: 'ok' });
    const entries = readAuditLog(logPath);
    expect(entries.length).toBe(3);
    expect(entries[0].prevHash).toBe('sha256:0');
    expect(entries[1].prevHash).not.toBe('sha256:0');
    expect(entries[2].prevHash).not.toBe(entries[1].prevHash);
    expect(verifyChain(logPath)).toBeNull();
  });

  it('verifyChain detects tampering', () => {
    auditLog(dir, { command: 'a', paths: [], outcome: 'ok' });
    auditLog(dir, { command: 'b', paths: [], outcome: 'ok' });
    auditLog(dir, { command: 'c', paths: [], outcome: 'ok' });
    const text = readFileSync(logPath, 'utf8');
    // Tamper with line 2: change outcome from ok → refused.
    const tampered = text.replace(
      '"command":"b","paths":[],"outcome":"ok"',
      '"command":"b","paths":[],"outcome":"refused"'
    );
    writeFileSync(logPath, tampered);
    const broken = verifyChain(logPath);
    // Line 2 hash changes, so line 3's prevHash no longer matches → break at line 3.
    expect(broken).toBe(3);
  });

  it('preserves actor kind + agent signals', () => {
    const prev = process.env.CLAUDECODE;
    process.env.CLAUDECODE = '1';
    // Reset the module-level cache in agent-guard so the env change takes
    // effect. Without this, a previous test that triggered isAgentEnvironment()
    // with CLAUDECODE unset poisons the cache for the remainder of the suite.
    resetAgentCache();
    try {
      auditLog(dir, { command: 'x', paths: [], outcome: 'ok' });
      const entries = readAuditLog(logPath);
      expect(entries[0].actor.kind).toBe('agent');
      expect(entries[0].actor.agentSignals).toContain('CLAUDECODE');
    } finally {
      if (prev === undefined) delete process.env.CLAUDECODE;
      else process.env.CLAUDECODE = prev;
      resetAgentCache();
    }
  });

  it('readAuditLog returns empty array when file does not exist', () => {
    expect(readAuditLog(logPath)).toEqual([]);
  });

  it('chains correctly across a log larger than the readLastHash chunk window', () => {
    // readLastHash seeks from EOF in 64KB windows; exercise the multi-chunk
    // path by appending enough padding that the last line sits beyond the
    // first read. A real entry at the tail must still chain cleanly.
    const padding = 'x'.repeat(80_000);
    auditLog(dir, { command: 'preamble', paths: [], outcome: 'ok' });
    // Inflate the log with a long `reason` field so the next prevHash lookup
    // has to walk back more than 64KB.
    auditLog(dir, { command: 'bloat', paths: [], outcome: 'ok', reason: padding });
    auditLog(dir, { command: 'tail', paths: [], outcome: 'ok' });
    const entries = readAuditLog(logPath);
    expect(entries).toHaveLength(3);
    expect(entries[2].command).toBe('tail');
    expect(entries[2].prevHash).not.toBe('sha256:0');
    expect(verifyChain(logPath)).toBeNull();
  });
});
