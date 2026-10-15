import { Readable } from 'node:stream';
import { afterEach, describe, expect, it } from 'vitest';
import { readStdinValue } from '../stdin.js';

const realStdin = Object.getOwnPropertyDescriptor(process, 'stdin');

function feedStdin(...chunks: (string | Buffer)[]): void {
  Object.defineProperty(process, 'stdin', {
    configurable: true,
    value: Readable.from(chunks),
  });
}

describe('readStdinValue', () => {
  afterEach(() => {
    if (realStdin) Object.defineProperty(process, 'stdin', realStdin);
  });

  it('joins every chunk and drops exactly one trailing newline', async () => {
    feedStdin(Buffer.from('rdt_'), Buffer.from('abc\n\n'));
    await expect(readStdinValue()).resolves.toBe('rdt_abc\n');
  });

  it('keeps internal newlines, as a multi-line PEM needs', async () => {
    feedStdin('line one\nline two\n');
    await expect(readStdinValue()).resolves.toBe('line one\nline two');
  });

  it('reads an empty stdin as the empty string', async () => {
    feedStdin();
    await expect(readStdinValue()).resolves.toBe('');
  });
});
