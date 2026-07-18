/**
 * NDJSON stream reader.
 *
 * The proxy streams one JSON object per line. Both consumers, the `rdc --proxy`
 * thin client and the web console job view, read it with plain `fetch` and this
 * splitter, which is why neither needs SSE or WebSocket machinery.
 *
 * Works anywhere `ReadableStream` and `TextDecoder` exist: Node 18+, Cloudflare
 * Workers, and browsers.
 */

/**
 * The largest single line this reader will buffer before giving up on it.
 *
 * The stream comes from a machine, and a machine is untrusted here: a
 * compromised renet could emit an unbounded run of bytes with no newline, and
 * an unguarded accumulator would allocate all of it and OOM the reader (the CLI
 * in `--proxy`, or the console following a job). One megabyte is orders of
 * magnitude above any real NDJSON event, so the cap only ever trips on hostile
 * or corrupt input. The Go-side replayer (pkg/jobs/logs.go) uses the same 1 MiB
 * ceiling; the two must stay in step.
 */
const MAX_LINE_BYTES = 1024 * 1024;

/** Raised when a single line exceeds MAX_LINE_BYTES. */
export class LineTooLongError extends Error {
  constructor() {
    super(
      `A single stream line exceeded ${MAX_LINE_BYTES} bytes without a newline. ` +
        `The source may be compromised or corrupt; refusing to buffer it.`
    );
    this.name = 'LineTooLongError';
  }
}

/**
 * Iterate the complete lines of a byte stream.
 *
 * Handles the two things a naive split gets wrong: a chunk boundary that lands
 * mid-line (the partial is carried into the next chunk), and a final line with
 * no trailing newline (still yielded). Bounds the pending buffer at
 * MAX_LINE_BYTES so an untrusted source cannot exhaust memory with a
 * newline-free flood.
 */
/**
 * Yield every complete (newline-terminated, non-blank) line already in `buffer`
 * and return the unconsumed remainder. Split out of readLines so the outer read
 * loop stays under the cognitive-complexity budget; behaviour is identical.
 */
function* drainCompleteLines(buffer: string): Generator<string, string> {
  let newlineIndex = buffer.indexOf('\n');
  while (newlineIndex !== -1) {
    const line = buffer.slice(0, newlineIndex);
    buffer = buffer.slice(newlineIndex + 1);
    if (line.trim() !== '') yield line;
    newlineIndex = buffer.indexOf('\n');
  }
  return buffer;
}

export async function* readLines(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = yield* drainCompleteLines(buffer);

      // No newline arrived and the pending line is already oversized: this is
      // the flood case. Stop before the next chunk doubles the allocation.
      if (buffer.length > MAX_LINE_BYTES) throw new LineTooLongError();
    }

    // Flush any multi-byte character left in the decoder, then the last line.
    buffer += decoder.decode();
    if (buffer.length > MAX_LINE_BYTES) throw new LineTooLongError();
    if (buffer.trim() !== '') yield buffer;
  } finally {
    reader.releaseLock();
  }
}

/**
 * Iterate the parsed JSON objects of an NDJSON stream.
 *
 * A line that is not valid JSON is passed to `onMalformed` and skipped rather
 * than aborting the stream. Renet writes its events to the same stdout that
 * carries occasional unstructured output, so a stray non-JSON line must never
 * kill an otherwise healthy operation.
 */
export async function* readNdjson<T = unknown>(
  stream: ReadableStream<Uint8Array>,
  onMalformed?: (line: string, error: unknown) => void
): AsyncGenerator<T> {
  for await (const line of readLines(stream)) {
    let parsed: T;
    try {
      parsed = JSON.parse(line) as T;
    } catch (error) {
      onMalformed?.(line, error);
      continue;
    }
    yield parsed;
  }
}
