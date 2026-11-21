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

/**
 * Total bytes from rsync `--progress` output: the sum over files of the size on each file's final line
 * (`<bytes> 100% <speed> <eta> (xfr#N, ...)`). Intermediate lines (under 100%) belong to a file still
 * running, and the last line seen is only the last file's size, so neither is the total. Keyed by xfr#,
 * a line seen twice through the chunk carry counts once.
 */
// The digits end at `,` or `)`: a chunk that stops inside the number must not store a prefix of it as the file's key.
const FINAL_LINE_PATTERN = /(\d[\d,]*)\s+100%\s+\S+\s+\S+\s+\(xf(?:e)?r#(\d+)[,)]/g;
/** Longest final line worth carrying: bytes, percent, speed, eta and the xfr token. */
const BYTES_CARRY_LENGTH = 96;

export interface RsyncBytesState {
  perFile: Map<number, number>;
  carry: string;
}

export function newRsyncBytesState(): RsyncBytesState {
  return { perFile: new Map(), carry: '' };
}

/** Fold one stdout chunk into the running state; returns the total bytes of every finished file. */
export function updateRsyncBytes(state: RsyncBytesState, chunk: string): number {
  const scan = state.carry + chunk;
  for (const match of scan.matchAll(FINAL_LINE_PATTERN)) {
    state.perFile.set(
      Number.parseInt(match[2], 10),
      Number.parseInt(match[1].replaceAll(',', ''), 10)
    );
  }
  state.carry = scan.slice(-BYTES_CARRY_LENGTH);
  let total = 0;
  for (const bytes of state.perFile.values()) total += bytes;
  return total;
}
