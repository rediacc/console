/**
 * Read-only view of the renet binary on a remote machine.
 *
 * Everything here only READS: one exec probes the versioned slot and `current`
 * for hash and version, and the rest is pure classification. The provisioner's
 * `inspect()` is the only caller; it supplies the local hash and the two paths.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { VERSION } from '../../version.js';
import type { RenetArch } from '../core/embedded-assets.js';

/**
 * How the remote renet relates to the local one.
 * `missing`: neither the versioned slot nor `current` holds a binary.
 * `version`: the remote reports a different version. `hash`: same version,
 * different bytes (a dev rebuild).
 */
export type RenetDrift = 'none' | 'hash' | 'version' | 'missing';

/** Result of a read-only inspection of the remote renet. */
export interface RenetInspectResult {
  arch: RenetArch;
  /** The binary to run: the versioned slot if present, else `current`; null when missing. */
  remotePath: string | null;
  remoteHash: string | null;
  remoteVersion: string | null;
  localHash: string;
  localVersion: string;
  drift: RenetDrift;
}

interface RemoteSlotProbe {
  hash: string | null;
  version: string | null;
}

/** The two remote locations a renet binary can be run from. */
export interface RenetSlotPaths {
  /** The versioned install slot for this CLI's VERSION. */
  slot: string;
  /** The `current` symlink target path. */
  current: string;
}

const SEMVER = /\d+\.\d+\.\d+/;

/** The numeric core of this CLI's version: the probe extracts x.y.z, and a dev VERSION may carry a suffix. */
const LOCAL_VERSION_CORE = SEMVER.exec(VERSION)?.[0] ?? VERSION;

function probeCommand(tag: string, remotePath: string): string {
  const q = shellQuote(remotePath);
  return (
    `if [ -e ${q} ]; then ` +
    `echo "${tag}_HASH $( (${q} hash 2>/dev/null || sha256sum ${q} | cut -d' ' -f1) 2>/dev/null | head -n1)"; ` +
    `echo "${tag}_VERSION $(${q} version 2>/dev/null | tr '\\n' ' ')"; ` +
    `else echo ${tag}_ABSENT; fi`
  );
}

function parseProbe(output: string, tag: string): RemoteSlotProbe {
  let hash: string | null = null;
  let version: string | null = null;
  for (const line of output.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith(`${tag}_HASH `)) {
      const [first] = trimmed.slice(`${tag}_HASH `.length).trim().split(/\s+/);
      hash = first || null;
    } else if (trimmed.startsWith(`${tag}_VERSION`)) {
      version = SEMVER.exec(trimmed.slice(`${tag}_VERSION`.length))?.[0] ?? null;
    }
  }
  return { hash, version };
}

/**
 * One exec, two slots. Each slot prints `<TAG>_HASH <hash>` and
 * `<TAG>_VERSION <text>` when its binary exists, or `<TAG>_ABSENT`.
 * A failed exec reads as both slots absent.
 */
export async function probeRemoteSlots(
  sftp: SFTPClient,
  paths: RenetSlotPaths
): Promise<{ slot: RemoteSlotProbe; current: RemoteSlotProbe }> {
  let output = '';
  try {
    output = await sftp.exec(
      `${probeCommand('SLOT', paths.slot)}; ${probeCommand('CURRENT', paths.current)}`
    );
  } catch {
    output = '';
  }
  return { slot: parseProbe(output, 'SLOT'), current: parseProbe(output, 'CURRENT') };
}

function classifyDrift(chosen: RemoteSlotProbe | null, localHash: string): RenetDrift {
  if (chosen === null) return 'missing';
  if (chosen.hash === localHash) return 'none';
  if (chosen.version === LOCAL_VERSION_CORE) return 'hash';
  return 'version';
}

/**
 * Classify a probe against the local binary. `bothMatch` is true when the slot
 * AND `current` hold the local bytes: exactly the state a successful provision
 * leaves behind, and the only state safe to record as verified.
 */
export function classifyInspect(
  arch: RenetArch,
  localHash: string,
  probes: { slot: RemoteSlotProbe; current: RemoteSlotProbe },
  paths: RenetSlotPaths
): { result: RenetInspectResult; bothMatch: boolean } {
  const { slot, current } = probes;
  let chosen: RemoteSlotProbe | null = null;
  let remotePath: string | null = null;
  if (slot.hash) {
    chosen = slot;
    remotePath = paths.slot;
  } else if (current.hash) {
    chosen = current;
    remotePath = paths.current;
  }
  return {
    result: {
      arch,
      remotePath,
      remoteHash: chosen?.hash ?? null,
      remoteVersion: chosen?.version ?? null,
      localHash,
      localVersion: VERSION,
      drift: classifyDrift(chosen, localHash),
    },
    bothMatch: slot.hash === localHash && current.hash === localHash,
  };
}

/** The result for a host already proven current (cache hit): no SSH was needed. */
export function matchedInspect(
  arch: RenetArch,
  hash: string,
  slotPath: string
): RenetInspectResult {
  return {
    arch,
    remotePath: slotPath,
    remoteHash: hash,
    remoteVersion: VERSION,
    localHash: hash,
    localVersion: VERSION,
    drift: 'none',
  };
}
