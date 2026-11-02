import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { AGG_INSTALL_HINT, assertAggAvailable, resolveAggPath } from '../agg-preflight.ts';

describe('agg preflight', () => {
  it('resolves like the renderer: AGG_BIN first, else ~/.local/bin/agg', () => {
    expect(resolveAggPath({ AGG_BIN: '/x/agg', HOME: '/h' })).toBe('/x/agg');
    expect(resolveAggPath({ HOME: '/h' })).toBe('/h/.local/bin/agg');
  });

  it('accepts an executable file', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'agg-'));
    try {
      const bin = path.join(dir, 'agg');
      writeFileSync(bin, '#!/bin/sh\n');
      chmodSync(bin, 0o755);
      expect(assertAggAvailable({ AGG_BIN: bin })).toBe(bin);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('CONTROL: refuses a missing agg and names the install command', () => {
    expect(() => assertAggAvailable({ HOME: '/nonexistent-home' })).toThrow(AGG_INSTALL_HINT);
  });

  it('CONTROL: refuses a file that is not executable', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'agg-'));
    try {
      const bin = path.join(dir, 'agg');
      writeFileSync(bin, 'x');
      chmodSync(bin, 0o644);
      expect(() => assertAggAvailable({ AGG_BIN: bin })).toThrow(AGG_INSTALL_HINT);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
