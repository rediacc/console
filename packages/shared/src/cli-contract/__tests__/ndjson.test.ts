import { describe, expect, it } from 'vitest';
import { LineTooLongError, readLines, readNdjson } from '../ndjson.js';

/** A ReadableStream over the given byte chunks. */
function streamOf(...chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(c);
      controller.close();
    },
  });
}

const enc = new TextEncoder();

describe('readLines', () => {
  it('yields complete lines and the trailing newline-less line', async () => {
    const lines: string[] = [];
    for await (const l of readLines(streamOf(enc.encode('a\nb\nc')))) lines.push(l);
    expect(lines).toEqual(['a', 'b', 'c']);
  });

  it('carries a line across a chunk boundary', async () => {
    const lines: string[] = [];
    for await (const l of readLines(streamOf(enc.encode('hel'), enc.encode('lo\nworld\n')))) {
      lines.push(l);
    }
    expect(lines).toEqual(['hello', 'world']);
  });

  it('skips blank lines', async () => {
    const lines: string[] = [];
    for await (const l of readLines(streamOf(enc.encode('a\n\n  \nb\n')))) lines.push(l);
    expect(lines).toEqual(['a', 'b']);
  });

  it('refuses a newline-free flood instead of buffering it unboundedly', async () => {
    // A hostile machine emitting 2 MiB with no newline. The reader must throw
    // rather than allocate all of it.
    const flood = enc.encode('x'.repeat(2 * 1024 * 1024));
    const iterate = async () => {
      for await (const line of readLines(streamOf(flood))) {
        void line; // draining; the flood throws before any line is yielded
      }
    };
    await expect(iterate()).rejects.toBeInstanceOf(LineTooLongError);
  });

  it('accepts a large-but-bounded line under the cap', async () => {
    const big = 'y'.repeat(512 * 1024);
    const lines: string[] = [];
    for await (const l of readLines(streamOf(enc.encode(`${big}\n`)))) lines.push(l);
    expect(lines).toEqual([big]);
  });
});

describe('readNdjson', () => {
  it('parses JSON objects and routes a garbage line to onMalformed without aborting', async () => {
    const seen: unknown[] = [];
    const bad: string[] = [];
    const body = `${JSON.stringify({ a: 1 })}\nnot json\n${JSON.stringify({ b: 2 })}\n`;
    for await (const obj of readNdjson(streamOf(enc.encode(body)), (line) => bad.push(line))) {
      seen.push(obj);
    }
    expect(seen).toEqual([{ a: 1 }, { b: 2 }]);
    expect(bad).toEqual(['not json']);
  });
});
