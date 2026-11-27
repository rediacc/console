/**
 * Large records through renet-output's stdout handlers. A `backup browse -o json` listing is one line of several MiB, and SSH delivers it in many chunks: each chunk used to be decoded on its own, so a multi-byte character split across a boundary came out as U+FFFD.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const written = vi.hoisted(() => ({ stdout: [] as string[] }));

vi.mock('../../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/request-context.js')>()),
  writeStdout: (data: string | Buffer) => {
    written.stdout.push(data.toString());
  },
}));

import { createJobOutputCollector } from '../job-output-collector.js';
import { createStdoutHandler } from '../renet-output.js';
import type { ExecuteOptions } from '../types.js';

const BIG = 'é'.repeat(3 * 512 * 1024); // 3 MiB of 2-byte characters

/** Feed bytes in an odd chunk size, so boundaries land inside the 2-byte characters. */
function feed(handler: (data: Buffer) => void, bytes: Buffer, chunkSize = 16 * 1024 + 1): void {
  for (let off = 0; off < bytes.length; off += chunkSize) {
    handler(bytes.subarray(off, off + chunkSize));
  }
}

beforeEach(() => {
  written.stdout = [];
});

describe('renet-output stdout handlers with a multi-MiB line', () => {
  it('events mode reconstructs a 3 MiB output event whole across split characters', () => {
    const collector = createJobOutputCollector();
    const handler = createStdoutHandler({} as ExecuteOptions, collector);
    const stream = `${JSON.stringify({ type: 'output', msg: BIG })}\n${JSON.stringify({ type: 'output', msg: 'after' })}\n`;

    feed(handler, Buffer.from(stream));

    expect(collector.stdout.length).toBe(BIG.length + 'after'.length + 2);
    expect(collector.stdout === `${BIG}\nafter\n`).toBe(true);
  });

  it('passthrough mode prints a 3 MiB line whole and flushes an unterminated tail', () => {
    const handler = createStdoutHandler({
      passthroughOutput: true,
      quietSpinners: true,
    } as ExecuteOptions);

    feed(handler, Buffer.from(`${BIG}\ntail-without-newline`));
    handler.flush?.();

    const out = written.stdout.join('');
    expect(out.length).toBe(BIG.length + 1 + 'tail-without-newline'.length + 1);
    expect(out === `${BIG}\ntail-without-newline\n`).toBe(true);
  });
});
