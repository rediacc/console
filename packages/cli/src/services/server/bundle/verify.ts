/**
 * Checking a bundle before anything is installed from it (Q16): the bundle was signed by the key the
 * operator named, every file in `SHA256SUMS` matches its sum, the manifest's own records agree with
 * the sums and carry that signature, the bundle was built by this CLI, and its renet is the renet
 * this CLI carries.
 */

import { join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { VERSION } from '../../../version.js';
import type { ServerDeps } from '../types.js';
import {
  BundleError,
  type BundleManifest,
  IMAGE_LIST_FILE,
  MANIFEST_FILE,
  parseManifest,
  parseSums,
  SUMS_FILE,
} from './manifest.js';
import {
  fingerprintOf,
  normaliseFingerprint,
  SIGNATURE_FILE,
  SIGNER_FILE,
  signatureHolds,
} from './signing.js';

/** The fingerprint reported for a signer key that does not parse. */
const INVALID_FINGERPRINT = 'invalid';

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
    ...(manifest.models ?? []),
    { file: IMAGE_LIST_FILE, sha256: manifest.imageList },
  ];
  for (const { file, sha256 } of claims) {
    if (known.get(file) !== sha256) {
      throw new BundleError(t('commands.server.bundle.errors.tampered', { file }));
    }
  }
}

/** The signer's key must be the one `--signer` names; a bundle without its signature files is refused. */
async function readSigner(deps: ServerDeps, dir: string, signer: string): Promise<string> {
  const read = async (file: string): Promise<string> => {
    try {
      return await deps.readFile(join(dir, file));
    } catch {
      throw new BundleError(t('commands.server.bundle.errors.unsigned', { file, dir }));
    }
  };
  await read(SIGNATURE_FILE);
  const publicKey = await read(SIGNER_FILE);
  const actual = fingerprintOf(publicKey);
  if (actual !== normaliseFingerprint(signer)) {
    throw new BundleError(
      t('commands.server.bundle.errors.signerMismatch', {
        expected: normaliseFingerprint(signer),
        actual: actual ?? INVALID_FINGERPRINT,
      })
    );
  }
  return publicKey;
}

/**
 * `signer` is the fingerprint the operator took from `rdc server bundle`'s output: the bundle's
 * `signer.pub` must hash to it and `manifest.sig` must be that key's signature over `manifest.json`.
 */
export async function verifyBundle(
  deps: ServerDeps,
  dir: string,
  signer: string
): Promise<BundleManifest> {
  const publicKey = await readSigner(deps, dir, signer);
  const known = await verifySums(deps, dir);
  if (!known.has(MANIFEST_FILE)) {
    throw new BundleError(t('commands.server.bundle.errors.notSummed', { file: MANIFEST_FILE }));
  }
  const manifestText = await readOrFail(deps, dir, MANIFEST_FILE);
  const manifest = parseManifest(manifestText);
  checkRecords(manifest, known);
  const signature = await readOrFail(deps, dir, SIGNATURE_FILE);
  if (!signatureHolds(manifestText, signature, publicKey)) {
    throw new BundleError(t('commands.server.bundle.errors.badSignature'));
  }
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
