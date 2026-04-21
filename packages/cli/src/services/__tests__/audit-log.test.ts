/**
 * Audit log tests — append, chain verification, tamper detection.
 */

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { auditLog, readAuditLog, verifyChain } from '../audit-log.js';

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
    try {
      auditLog(dir, { command: 'x', paths: [], outcome: 'ok' });
      const entries = readAuditLog(logPath);
      expect(entries[0].actor.kind).toBe('agent');
      expect(entries[0].actor.agentSignals).toContain('CLAUDECODE');
    } finally {
      if (prev === undefined) delete process.env.CLAUDECODE;
      else process.env.CLAUDECODE = prev;
    }
  });

  it('readAuditLog returns empty array when file does not exist', () => {
    expect(readAuditLog(logPath)).toEqual([]);
  });
});
