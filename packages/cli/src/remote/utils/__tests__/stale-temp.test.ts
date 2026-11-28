/**
 * The stale sweep collects the key, known_hosts and launch-script temp files a
 * closed terminal window left behind: only this tool's own names, only past
 * the age limit, only regular files.
 */
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  utimesSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { STALE_TEMP_MAX_AGE_MS, sweepStaleTermTempFiles } from '../stale-temp.js';

const HEX = '0123456789abcdef';
let dir: string;

function make(name: string, ageMs: number): string {
  const path = join(dir, name);
  writeFileSync(path, 'x');
  const when = new Date(Date.now() - ageMs);
  utimesSync(path, when, when);
  return path;
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'rdc-sweep-'));
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe('sweepStaleTermTempFiles', () => {
  const old = STALE_TEMP_MAX_AGE_MS + 60_000;

  it('is 12 hours', () => {
    expect(STALE_TEMP_MAX_AGE_MS).toBe(12 * 3_600_000);
  });

  it('removes old ssh-key, known_hosts and launch-script files', () => {
    const files = [
      make(`ssh-key-${HEX}.pem`, old),
      make(`known_hosts-${HEX}`, old),
      make(`rdc-term-${HEX}.cmd`, old),
    ];
    expect(sweepStaleTermTempFiles(dir).sort((a, b) => a.localeCompare(b))).toEqual(
      [...files].sort((a, b) => a.localeCompare(b))
    );
    for (const f of files) expect(existsSync(f)).toBe(false);
  });

  it('keeps fresh files of the same names', () => {
    const files = [
      make(`ssh-key-${HEX}.pem`, 60_000),
      make(`known_hosts-${HEX}`, 3_600_000),
      make(`rdc-term-${HEX}.cmd`, 0),
    ];
    expect(sweepStaleTermTempFiles(dir)).toEqual([]);
    for (const f of files) expect(existsSync(f)).toBe(true);
  });

  it('keeps old files that are not this tool names', () => {
    const files = [
      make('ssh-key-mine.pem', old),
      make('id_ed25519', old),
      make('known_hosts', old),
      make(`ssh-key-${HEX}.pem.bak`, old),
      make(`other-${HEX}.cmd`, old),
    ];
    expect(sweepStaleTermTempFiles(dir)).toEqual([]);
    for (const f of files) expect(existsSync(f)).toBe(true);
  });

  it('keeps a directory and a symlink under an own name', () => {
    mkdirSync(join(dir, `known_hosts-${HEX}`));
    const target = make('target', old);
    symlinkSync(target, join(dir, `ssh-key-${HEX}.pem`));
    expect(sweepStaleTermTempFiles(dir)).toEqual([]);
    expect(existsSync(target)).toBe(true);
  });

  it('answers a missing directory with nothing removed', () => {
    expect(sweepStaleTermTempFiles(join(dir, 'absent'))).toEqual([]);
  });
});
