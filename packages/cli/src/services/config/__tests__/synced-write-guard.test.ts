/**
 * Guard: nothing writes the synced part of a config around `updateSyncedConfig`
 * (PLAN-config-sync-hardening T18).
 *
 * A remote config's local file is a cache that the next pull overwrites, so a command that edits
 * it with `configFileStorage.update/save/updateCache` loses the edit silently. This test scans
 * packages/cli/src for those calls and fails on any file not listed below, or on a listed file
 * that gained one. A new writer of a synced section goes through `updateSyncedConfig` /
 * `updateConfigAtPointer` (services/config/synced-write.ts) instead.
 *
 * Scope, stated so a green run is not read as more than it is: the scan matches the literal
 * `configFileStorage.<method>(` spelling (an alias or a destructured method escapes it), and
 * `updateState` writes are not scanned, because the `state` bucket's sync model belongs to T17.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = join(import.meta.dirname, '..', '..', '..');

const WRITE_CALL = /configFileStorage\s*\.\s*(update|save|updateCache)\s*\(/g;

/** Files allowed to write the config file directly: path (relative to src) -> call count and why. */
const ALLOWED: Record<string, { count: number; reason: string }> = {
  'services/config/synced-write.ts': {
    count: 3,
    reason: 'the synced write path itself: local configs, device-local pointers, request scope',
  },
  'services/config/resource-state.ts': {
    count: 2,
    reason: 'LocalResourceState.persist (local configs) and the cache write after a push',
  },
  'services/config/remote-cache.ts': {
    count: 2,
    reason:
      'writeRemoteCache (stores a pulled server copy) and purgeRemoteCache (drops a config the account lost access to)',
  },
  'services/config/config-base.ts': {
    count: 1,
    reason:
      'setMasterPassword (the device-local verifier); updateSyncedSection delegates to updateSyncedConfig',
  },
  'commands/config-remote.ts': {
    count: 1,
    reason: 'remote disable: writes the pulled server copy as the new local config',
  },
  'commands/config-remote-enable.ts': {
    count: 1,
    reason: 'remote enable: seeds the cache from the store',
  },
  'commands/config.ts': {
    count: 1,
    reason: 'config init on a new or local config (a remote one goes through updateSyncedConfig)',
  },
};

function listSources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      out.push(...listSources(path));
    } else if (entry.name.endsWith('.ts') && !entry.name.endsWith('.test.ts')) {
      out.push(path);
    }
  }
  return out;
}

/** Strip comments so a doc comment naming a call does not count as one. */
function stripComments(source: string): string {
  return source.replaceAll(/\/\*[\s\S]*?\*\//g, '').replaceAll(/(^|[^:])\/\/.*$/gm, '$1');
}

/** Every direct config-file write, per file. */
function countWrites(files: Map<string, string>): Map<string, number> {
  const counts = new Map<string, number>();
  for (const [file, source] of files) {
    const n = stripComments(source).match(WRITE_CALL)?.length ?? 0;
    if (n > 0) counts.set(file, n);
  }
  return counts;
}

/** The violations: files not allowed to write, or writing more often than allowed. */
function violations(counts: Map<string, number>): string[] {
  const found: string[] = [];
  for (const [file, n] of counts) {
    const allowed = ALLOWED[file] as { count: number } | undefined;
    if (!allowed) {
      found.push(`${file}: ${n} direct config write(s); use updateSyncedConfig (synced-write.ts)`);
    } else if (n > allowed.count) {
      found.push(`${file}: ${n} direct config writes, ${allowed.count} allowed`);
    }
  }
  return found;
}

function readTree(): Map<string, string> {
  const files = new Map<string, string>();
  for (const path of listSources(SRC_ROOT)) {
    files.set(relative(SRC_ROOT, path).split(sep).join('/'), readFileSync(path, 'utf8'));
  }
  return files;
}

describe('synced-write guard', () => {
  it('no file writes a config around updateSyncedConfig', () => {
    expect(violations(countWrites(readTree()))).toEqual([]);
  });

  it('every allow-list entry is still exact (a removed writer shrinks its entry)', () => {
    const counts = countWrites(readTree());
    const stale = Object.entries(ALLOWED)
      .filter(([file, { count }]) => (counts.get(file) ?? 0) !== count)
      .map(([file, { count }]) => `${file}: allowed ${count}, found ${counts.get(file) ?? 0}`);
    expect(stale).toEqual([]);
  });

  it('control: a planted bypassing writer is reported', () => {
    const files = readTree();
    expect(files.size).toBeGreaterThan(100);
    const planted = 'services/config/config-datastores.ts';
    files.set(
      planted,
      `${files.get(planted) ?? ''}\nawait configFileStorage.update(name, (cfg) => cfg);\n`
    );
    files.set(
      'services/config/synced-write.ts',
      `${files.get('services/config/synced-write.ts') ?? ''}\nconfigFileStorage.save(cfg, name);\n`
    );
    expect(violations(countWrites(files)).sort()).toEqual([
      `${planted}: 1 direct config write(s); use updateSyncedConfig (synced-write.ts)`,
      'services/config/synced-write.ts: 4 direct config writes, 3 allowed',
    ]);
  });

  it('control: a call named only in a comment is not a writer', () => {
    const files = new Map([
      ['x.ts', '// configFileStorage.update(name)\n/* configFileStorage.save( */'],
    ]);
    expect(countWrites(files).size).toBe(0);
  });
});
