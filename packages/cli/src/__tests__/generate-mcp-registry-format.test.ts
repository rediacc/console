/**
 * Review 723bbcdf.1: the registry generator must not leave an unformatted file on disk when biome fails. `--check` compares parsed JSON, so an unformatted write would read as current and only the failed run's exit code would show it.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const cliRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const target = path.resolve(cliRoot, '../shared/src/mcp/tools.generated.json');
const script = path.join(cliRoot, 'scripts/generate-mcp-registry.ts');
const tsx = path.resolve(cliRoot, '../../node_modules/.bin/tsx');

function run(biome?: string) {
  return spawnSync(tsx, [script], {
    cwd: cliRoot,
    encoding: 'utf-8',
    env: { ...process.env, ...(biome ? { REDIACC_BIOME_BIN: biome } : {}) },
  });
}

describe('generate-mcp-registry formatter failure', () => {
  it('leaves the committed file byte-identical when biome fails, and rewrites it when biome works', () => {
    const before = fs.readFileSync(target, 'utf-8');
    try {
      // Plant a stale tail so a write on the failing path is visible even when the registry is current.
      fs.writeFileSync(target, `${before}\n\n`, 'utf-8');
      const planted = fs.readFileSync(target, 'utf-8');

      const failed = run('/bin/false');
      expect(failed.status).toBe(1);
      expect(failed.stderr).toContain('biome format failed');
      expect(fs.readFileSync(target, 'utf-8')).toBe(planted);

      // Control: the real formatter rewrites the planted file back to the formatted bytes.
      const ok = run();
      expect(ok.status).toBe(0);
      expect(fs.readFileSync(target, 'utf-8')).toBe(before);
    } finally {
      fs.writeFileSync(target, before, 'utf-8');
    }
  }, 120_000);
});
