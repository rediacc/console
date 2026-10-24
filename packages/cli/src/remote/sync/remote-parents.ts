import { chmodSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import * as path from 'node:path';

/**
 * rsync creates the destination's missing parents (`--mkpath`) or only its last component, and under a privileged receive (`sudo rsync`) it does so as root. Entries outside the transfer list are never mapped by `--chown`, so those directories stay root:root and the universal user cannot modify them. These helpers find the missing segments so a skeleton rsync, which goes through the verified directory-upload shape, creates exactly those with the universal user's ownership. Directories that already exist are never part of the skeleton, so they are never re-owned.
 *
 * Known race, accepted: another writer that creates the same new segment between the probe and the skeleton keeps its own owner for it, since the skeleton then finds it existing and only re-applies the mapping.
 *
 * rsync version floor: the skeleton adds no flag beyond the directory upload's own (`-av --inplace --chown ...`), so it needs nothing newer than that path already does. Neither the CLI nor renet states a minimum rsync version for target machines (renet's tests drive 3.4.1, Ubuntu 24.04 ships 3.2.7); the only version-gated flag in this code is `--mkpath` (3.2.3+), which the skeleton does not use.
 */

export interface MissingParents {
  /** Deepest ancestor the probe found (or the base path itself). */
  existingAncestor: string;
  /** Segment names below existingAncestor that do not exist, top-down. */
  missing: string[];
}

/** Splits a sub path into clean segments (no empty, `.` or leading/trailing slashes). */
function segmentsOf(subPath: string): string[] {
  return subPath.split('/').filter((s) => s !== '' && s !== '.');
}

/**
 * Probes the parent chain of `remoteSubPath` top-down from `baseRemotePath`. The sub path's own last component is NOT probed: pass the file's (or the destination directory's) path and its dirname is checked. Stops at the first missing segment, since everything below is missing too. A probe that throws ends the walk with nothing planned (a later clean miss would otherwise plan a skeleton under an ancestor that may not exist), so the transfer proceeds as before. A sub path with a `..` segment plans nothing either: its ancestors cannot be named lexically, and a skeleton would try to create a `..` directory.
 */
export async function planMissingParents(
  baseRemotePath: string,
  remoteSubPath: string,
  exists: (remotePath: string) => Promise<boolean>
): Promise<MissingParents> {
  const base = baseRemotePath.replace(/\/+$/, '');
  const segments = segmentsOf(remoteSubPath);
  if (segments.includes('..')) return { existingAncestor: base, missing: [] };
  const parents = segments.slice(0, -1);
  let ancestor = base;
  for (let i = 0; i < parents.length; i++) {
    const candidate = `${ancestor}/${parents[i]}`;
    let present: boolean;
    try {
      present = await exists(candidate);
    } catch {
      return { existingAncestor: ancestor, missing: [] };
    }
    if (!present) {
      return { existingAncestor: ancestor, missing: parents.slice(i) };
    }
    ancestor = candidate;
  }
  return { existingAncestor: ancestor, missing: [] };
}

export interface Skeleton {
  /** Local directory to upload with a trailing slash. */
  source: string;
  cleanup: () => void;
}

/**
 * Builds a local temp tree for `missing`. The first segment is the upload destination itself (rsync creates that one level), so the tree holds segments 1.. nested, every directory 0775.
 */
export function writeSkeleton(missing: string[]): Skeleton {
  const root = mkdtempSync(path.join(tmpdir(), 'rdc-skeleton-'));
  const cleanup = (): void => rmSync(root, { recursive: true, force: true });
  try {
    chmodSync(root, 0o775);
    let dir = root;
    for (const seg of missing.slice(1)) {
      dir = path.join(dir, seg);
      mkdirSync(dir, { mode: 0o775 });
      chmodSync(dir, 0o775);
    }
  } catch (err) {
    cleanup();
    throw err;
  }
  return { source: `${root}/`, cleanup };
}

/** The skeleton's rsync destination: the first missing segment under its existing ancestor, with a trailing slash. */
export function skeletonDestination(
  userHost: string,
  existingAncestor: string,
  missing: string[]
): string {
  return `${userHost}:${existingAncestor}/${missing[0]}/`;
}
