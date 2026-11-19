/**
 * The installed FREE licence blob a feedback report can authenticate with when
 * no API token is stored. Renet installs blobs under
 * `<license root>/repos/<guid>/<keyId>.json` (unscoped) and
 * `<license root>/datastores/<id>/repos/<guid>/<keyId>.json` (datastore scoped);
 * a blob whose payload carries a `free:` subscription id is a FREE licence.
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const LICENSE_ROOT = '/var/lib/rediacc/license';

export interface FreeBlob {
  payload: string;
  signature: string;
  publicKeyId: string;
  chainHash?: string;
  delegationCert?: { payload: string; signature: string; publicKeyId: string };
}

function listDir(dir: string): string[] {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

/** Every `<guid>/<keyId>.json` file under one `repos` directory. */
function blobFiles(reposDir: string): string[] {
  return listDir(reposDir).flatMap((guid) =>
    listDir(path.join(reposDir, guid))
      .filter((name) => /^[0-9a-f]{16}\.json$/.test(name))
      .map((name) => path.join(reposDir, guid, name))
  );
}

function isFreePayload(payload: unknown): boolean {
  if (typeof payload !== 'string') return false;
  try {
    const decoded = JSON.parse(Buffer.from(payload, 'base64').toString('utf8')) as {
      subscriptionId?: unknown;
    };
    return typeof decoded.subscriptionId === 'string' && decoded.subscriptionId.startsWith('free:');
  } catch {
    return false;
  }
}

function asFreeBlob(file: string): FreeBlob | undefined {
  try {
    const blob = JSON.parse(readFileSync(file, 'utf8')) as Partial<FreeBlob>;
    const complete =
      typeof blob.signature === 'string' &&
      typeof blob.publicKeyId === 'string' &&
      isFreePayload(blob.payload);
    return complete ? (blob as FreeBlob) : undefined;
  } catch {
    return undefined;
  }
}

/** The first installed FREE blob under the license root, or undefined when none is installed or readable. */
export function findInstalledFreeBlob(root: string = LICENSE_ROOT): FreeBlob | undefined {
  const reposDirs = [
    path.join(root, 'repos'),
    ...listDir(path.join(root, 'datastores')).map((id) =>
      path.join(root, 'datastores', id, 'repos')
    ),
  ];
  for (const dir of reposDirs) {
    for (const file of blobFiles(dir)) {
      const blob = asFreeBlob(file);
      if (blob) return blob;
    }
  }
  return undefined;
}
