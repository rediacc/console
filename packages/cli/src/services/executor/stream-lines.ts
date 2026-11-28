import { StringDecoder } from 'node:string_decoder';

/** Splits a chunked byte stream into lines; `flush` hands over a final line that never got its newline. */
export interface LineSplitter {
  push(chunk: Buffer): void;
  flush(): void;
}

/**
 * The one line reader for renet's streamed stdout (events, step lines, passthrough output, job logs).
 *
 * Lines have no length cap: a `backup browse -o json` listing is one record of several MiB. Bytes go through one StringDecoder, so a multi-byte character split across two chunks is decoded whole (a per-chunk `toString()` turned it into U+FFFD). Each chunk is searched for newlines on its own while the partial line accumulates as pieces joined once at its newline, so a large record costs linear time rather than a re-split of the whole buffered line per chunk.
 *
 * `onLine` receives the line without its `\n`; a `\r` is left in place for the caller's own trimming.
 */
export function createLineSplitter(onLine: (line: string) => void): LineSplitter {
  const decoder = new StringDecoder('utf8');
  let pending: string[] = [];

  const consume = (text: string): void => {
    let start = 0;
    let newline = text.indexOf('\n');
    while (newline >= 0) {
      pending.push(text.slice(start, newline));
      const line = pending.join('');
      pending = [];
      onLine(line);
      start = newline + 1;
      newline = text.indexOf('\n', start);
    }
    if (start < text.length) pending.push(text.slice(start));
  };

  return {
    push(chunk) {
      consume(decoder.write(chunk));
    },
    flush() {
      consume(decoder.end());
      if (pending.length === 0) return;
      const tail = pending.join('');
      pending = [];
      if (tail) onLine(tail);
    },
  };
}
