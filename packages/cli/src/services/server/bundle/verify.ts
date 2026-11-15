/**
 * Checking a bundle before anything is installed from it (Q16): every file in `SHA256SUMS` matches
 * its sum, the manifest's own records agree with the sums, the bundle was built by this CLI, and its
 * renet is the renet this CLI carries.
 */

import { join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { VERSION } from '../../../version.js';
import type { ServerDeps } from '../types.js';
import {
  BundleError,
  type BundleManifest,
  MANIFEST_FILE,
  parseManifest,
  parseSums,
  SUMS_FILE,
} from './manifest.js';

async function readOrFail(deps: ServerDeps, dir: string, file: string): Promise<string> {
  try {
    return await deps.readFile(join(dir, file));
  } catch {
    throw new BundleError(t('commands.server.bundle.errors.unreadable', { file, dir }));
  }
}

/** Every summed file must hash to its sum. */
async function verifySums(deps: ServerDeps, dir: string): Promise<Map<string, string>> {
  const sums = parseSums(await readOrFail(deps, dir, SUMS_FILE));
  const known = new Map<string, string>();
  for (const { file, sha256 } of sums) {
    let actual: string;
    try {
      actual = await deps.sha256File(join(dir, file));
    } catch {
      throw new BundleError(t('commands.server.bundle.errors.unreadable', { file, dir }));
    }
    if (actual !== sha256)
      throw new BundleError(t('commands.server.bundle.errors.tampered', { file }));
    known.set(file, sha256);
  }
  return known;
}

/** The manifest's per-file hashes must be the summed ones: a hand-edited manifest does not pass. */
function checkRecords(manifest: BundleManifest, known: Map<string, string>): void {
  const claims = [
    ...manifest.images.map((i) => ({ file: i.file, sha256: i.sha256 })),
    { file: manifest.renet.file, sha256: manifest.renet.sha256 },
    ...(manifest.cli ?? []).map((c) => ({ file: c.file, sha256: c.sha256 })),
  ];
  for (const { file, sha256 } of claims) {
    if (known.get(file) !== sha256) {
      throw new BundleError(t('commands.server.bundle.errors.tampered', { file }));
    }
  }
}

export async function verifyBundle(deps: ServerDeps, dir: string): Promise<BundleManifest> {
  const known = await verifySums(deps, dir);
  if (!known.has(MANIFEST_FILE)) {
    throw new BundleError(t('commands.server.bundle.errors.notSummed', { file: MANIFEST_FILE }));
  }
  const manifest = parseManifest(await readOrFail(deps, dir, MANIFEST_FILE));
  checkRecords(manifest, known);
  if (manifest.cliVersion !== VERSION) {
    throw new BundleError(
      t('commands.server.bundle.errors.cliMismatch', {
        bundle: manifest.cliVersion,
        cli: VERSION,
      })
    );
  }
  const own = await deps.renetAsset(manifest.renet.arch);
  if (own.sha256 !== manifest.renet.sha256) {
    throw new BundleError(
      t('commands.server.bundle.errors.renetMismatch', { arch: manifest.renet.arch })
    );
  }
  return manifest;
}
