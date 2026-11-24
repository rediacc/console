/**
 * Regression guard for the deleted password key slot (D39, review finding dce21775.1).
 *
 * K1 removed derivePasswordSlotSecret, newPasswordSlotParams and PASSWORD_PBKDF2_ITERATIONS from
 * @rediacc/shared/config-crypto, and K2/K4 removed the password-enroll route and its CLI caller.
 * The barrel removal left importers in other packages that only a build caught. This test fails
 * the moment any source tree names one of them again, and proves first that the scan fires.
 *
 * The names are assembled from parts so this file never matches its own scan, nor the
 * `git grep` that K4's Accept runs over the same trees.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as configCrypto from '@rediacc/shared/config-crypto';
import { describe, expect, it } from 'vitest';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');

const REMOVED_EXPORTS = [
  ['derive', 'PasswordSlotSecret'],
  ['new', 'PasswordSlotParams'],
  ['PASSWORD_', 'PBKDF2_ITERATIONS'],
].map((parts) => parts.join(''));

const REMOVED_ROUTE = ['password', 'enroll'].join('-');

const NEEDLES = [...REMOVED_EXPORTS, REMOVED_ROUTE];

const SCANNED_TREES = [
  'packages/shared/src',
  'packages/cli/src',
  'private/account/src',
  'private/account/tests',
  'private/account/web/src',
] as const;

const SOURCE_FILE = /\.(ts|tsx|mts|cts|js|mjs)$/;

function sourceFiles(dir: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    // A tree that is absent from this checkout (a submodule not initialized) is reported, never skipped silently.
    throw new Error(`scanned tree is missing: ${relative(REPO, dir)}`);
  }
  const out: string[] = [];
  for (const name of entries) {
    if (name === 'node_modules' || name === 'dist') continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...sourceFiles(path));
    else if (SOURCE_FILE.test(name)) out.push(path);
  }
  return out;
}

/** Every `file: needle` hit in the given text set. */
function findHits(files: Array<{ path: string; text: string }>): string[] {
  const hits: string[] = [];
  for (const { path, text } of files) {
    for (const needle of NEEDLES) {
      if (text.includes(needle)) hits.push(`${path}: ${needle}`);
    }
  }
  return hits;
}

describe('the password key slot stays deleted', () => {
  it('control: the scan fires on a file that names a removed export or the removed route', () => {
    const planted = [
      { path: 'planted.ts', text: `import { ${REMOVED_EXPORTS[0]} } from 'x';` },
      { path: 'route.ts', text: `fetch('/configs/${REMOVED_ROUTE}')` },
      { path: 'clean.ts', text: "import { deriveRecoverySlotSecret } from 'x';" },
    ];
    expect(findHits(planted)).toEqual([
      `planted.ts: ${REMOVED_EXPORTS[0]}`,
      `route.ts: ${REMOVED_ROUTE}`,
    ]);
  });

  it('the shared config-crypto barrel exports none of them', () => {
    const exported = Object.keys(configCrypto);
    expect(REMOVED_EXPORTS.filter((name) => exported.includes(name))).toEqual([]);
    // Control: the barrel is the real one (a live export is visible).
    expect(exported).toContain('deriveRecoverySlotSecret');
  });

  it('no source tree names a removed export or the removed route', () => {
    const self = fileURLToPath(import.meta.url);
    const files = SCANNED_TREES.flatMap((tree) => sourceFiles(join(REPO, tree)))
      .filter((path) => path !== self)
      .map((path) => ({ path: relative(REPO, path), text: readFileSync(path, 'utf8') }));
    expect(files.length).toBeGreaterThan(1000);
    expect(findHits(files)).toEqual([]);
  });
});
