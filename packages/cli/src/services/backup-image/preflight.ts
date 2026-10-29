/**
 * Disk-space preflight for the local target of `rdc backup download` (Design 5).
 *
 * Pure apart from `probeSparse` (a 64 MiB probe file) and `checkSpace` (one `statfs`, injectable).
 * No i18n: callers render the result.
 */

import { closeSync, fstatSync, ftruncateSync, openSync, unlinkSync } from 'node:fs';
import { statfs } from 'node:fs/promises';
import { join } from 'node:path';

const MiB = 1024 * 1024;
const GiB = 1024 * MiB;
export const SPACE_MARGIN_MIN = 256 * MiB;
export const SPARSE_PROBE_BYTES = 64 * MiB;
/** statfs f_type of a FAT filesystem on Linux (MSDOS_SUPER_MAGIC). */
export const FAT_FS_TYPE = 0x4d44;
/** The largest file FAT32 can hold. */
export const FAT32_MAX_FILE = 4 * GiB - 1;

/** Allocated bytes of a stat result: `blocks * 512`, or the size when blocks are unknown. */
export function allocatedBytesOf(st: { size: number; blocks?: number }): number {
  return typeof st.blocks === 'number' ? st.blocks * 512 : st.size;
}

/**
 * True when a file truncated to 64 MiB in `dir` occupies fewer blocks than its size. False when the
 * probe cannot run (a missing or unwritable `dir`): not sparse is the conservative answer, and the
 * statfs of the same directory in checkSpace names the real failure.
 */
export function probeSparse(dir: string): boolean {
  const path = join(dir, `.rdc-sparse-probe-${process.pid}-${Date.now()}`);
  let fd: number;
  try {
    fd = openSync(path, 'wx', 0o600);
  } catch {
    return false;
  }
  try {
    ftruncateSync(fd, SPARSE_PROBE_BYTES);
    const st = fstatSync(fd);
    if (typeof st.blocks !== 'number') return false;
    return st.blocks * 512 < st.size;
  } finally {
    closeSync(fd);
    try {
      unlinkSync(path);
    } catch {
      // Best effort: the probe is empty.
    }
  }
}

export interface SpaceNeedInput {
  /** Remote apparent size A. */
  apparent: number;
  /** Remote allocated size U. */
  allocated: number;
  localExists: boolean;
  /** Local allocated size L, when the image exists. */
  localAllocated?: number;
  /** Whether the target filesystem keeps holes. */
  sparse: boolean;
}

export function spaceMargin(apparent: number): number {
  return Math.max(SPACE_MARGIN_MIN, Math.ceil(apparent * 0.01));
}

/**
 * Bytes the run may newly allocate, margin included.
 * Fresh: `sparse ? U : A`. Existing: `max(0, min(sparse ? U : A, A - L))`.
 */
export function computeSpaceNeed(input: SpaceNeedInput): number {
  const full = input.sparse ? input.allocated : input.apparent;
  const base = input.localExists
    ? Math.max(0, Math.min(full, input.apparent - (input.localAllocated ?? 0)))
    : full;
  return base + spaceMargin(input.apparent);
}

export type SpaceRefusal = 'insufficient-space' | 'fat32-file-limit';

export interface SpaceCheck {
  ok: boolean;
  need: number;
  free: number;
  reason?: SpaceRefusal;
}

export interface CheckSpaceInput extends SpaceNeedInput {
  dir: string;
}

export interface StatfsResult {
  type: number;
  bsize: number;
  bavail: number;
}

export interface CheckSpaceDeps {
  statfs?: (dir: string) => Promise<StatfsResult>;
  platform?: NodeJS.Platform;
}

export async function checkSpace(
  input: CheckSpaceInput,
  deps: CheckSpaceDeps = {}
): Promise<SpaceCheck> {
  const stat = deps.statfs ?? ((d: string) => statfs(d));
  const fs = await stat(input.dir);
  const free = Number(fs.bavail) * Number(fs.bsize);
  const need = computeSpaceNeed(input);
  const platform = deps.platform ?? process.platform;
  if (platform === 'linux' && fs.type === FAT_FS_TYPE && input.apparent > FAT32_MAX_FILE) {
    return { ok: false, need, free, reason: 'fat32-file-limit' };
  }
  if (need > free) return { ok: false, need, free, reason: 'insufficient-space' };
  return { ok: true, need, free };
}
