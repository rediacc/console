/**
 * Count files from rsync `--progress` output.
 *
 * rsync 3.1+ prints `(xfr#N, to-chk=...)` after each file, 3.0 prints `xfer#N`.
 * One stdout chunk routinely carries several of those lines, and a chunk can
 * end mid-token, so the count is the highest N seen across the chunk joined to
 * a short carry of the previous one.
 */
const XFR_PATTERN = /xf(?:e)?r#(\d+)/g;
/** Longest partial token worth carrying: `xfer#` plus digits. */
const CARRY_LENGTH = 16;

export interface RsyncCountState {
  count: number;
  carry: string;
}

export function newRsyncCountState(): RsyncCountState {
  return { count: 0, carry: '' };
}

/** Fold one stdout chunk into the running state; returns the updated count. */
export function updateRsyncCount(state: RsyncCountState, chunk: string): number {
  const scan = state.carry + chunk;
  for (const match of scan.matchAll(XFR_PATTERN)) {
    state.count = Math.max(state.count, Number.parseInt(match[1], 10));
  }
  state.carry = scan.slice(-CARRY_LENGTH);
  return state.count;
}
