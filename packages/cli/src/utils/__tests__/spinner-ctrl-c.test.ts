/**
 * Ctrl-C must stop a spinner. ora's default `discardStdin: true` puts stdin in RAW mode and listens for 0x03 with
 * `prependListener('data')`, which never starts a stream that has not flowed yet, so the byte was swallowed and
 * `rdc config remote enable` could only be killed by closing the terminal (2026-09-25). Reproduced in a pty against
 * the built bundle: without the option the CLI survived Ctrl-C for 8s, with it the CLI exits at once.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { oraOptions } from '../spinner.js';

describe('spinners keep Ctrl-C a signal', () => {
  it('never let ora discard stdin', () => {
    expect(oraOptions('waiting')).toEqual({ text: 'waiting', discardStdin: false });
  });

  it('every ora call site goes through oraOptions', () => {
    for (const rel of ['../spinner.ts', '../../commands/repo-sync.ts']) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
      const calls = src.match(/\bora\(/g) ?? [];
      const routed = src.match(/\bora\(\s*(?:\{ \.\.\.)?oraOptions\(/g) ?? [];
      expect(calls.length, rel).toBeGreaterThan(0);
      expect(routed.length, rel).toBe(calls.length);
    }
  });
});
