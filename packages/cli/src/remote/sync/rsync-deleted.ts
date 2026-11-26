/**
 * Counts the deletions of a `--mirror` run from rsync's stdout. A mirror run is itemized (`--itemize-changes`), which prints each as
 * `*deleting   <name>` and every transferred file as `<flags> <name>`; the bare `deleting <name>` of a plain verbose run is not
 * counted, since a transferred file whose name starts `deleting ` prints identically. The stream arrives in chunks and progress lines end in `\r`, so a line
 * split across chunks is joined before it is read.
 */
const DELETE_LINE = /^\*deleting\s/;

/** The longest unterminated tail kept; a deletion line is a path and a short prefix. */
const DELETE_SCAN_MAX_LINE = 8192;

export function createDeleteCounter(): { push(chunk: string): void; count(): number } {
  let total = 0;
  let carry = '';
  return {
    push(chunk: string): void {
      const lines = `${carry}${chunk}`.split(/[\r\n]/);
      carry = lines.pop() ?? '';
      if (carry.length > DELETE_SCAN_MAX_LINE) carry = '';
      for (const line of lines) if (DELETE_LINE.test(line)) total++;
    },
    count(): number {
      return total + (DELETE_LINE.test(carry) ? 1 : 0);
    },
  };
}
