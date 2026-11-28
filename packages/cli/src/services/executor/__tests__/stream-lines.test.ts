import { describe, expect, it } from 'vitest';
import { createLineSplitter } from '../stream-lines.js';

function split(chunks: Buffer[], flush = true): string[] {
  const lines: string[] = [];
  const splitter = createLineSplitter((line) => lines.push(line));
  for (const chunk of chunks) splitter.push(chunk);
  if (flush) splitter.flush();
  return lines;
}

describe('createLineSplitter', () => {
  it('splits on newlines, keeps blank lines, and holds a partial line until its newline', () => {
    expect(split([Buffer.from('a\n\nb'), Buffer.from('c\nd')], false)).toEqual(['a', '', 'bc']);
  });

  it('flush hands over the unterminated tail once, and nothing for an empty tail', () => {
    expect(split([Buffer.from('a\nb')])).toEqual(['a', 'b']);
    expect(split([Buffer.from('a\n')])).toEqual(['a']);
  });

  it('decodes a multi-byte character split across chunks whole', () => {
    const bytes = Buffer.from('é€😀\n');
    // One byte per chunk splits every multi-byte character.
    const chunks = [...bytes].map((b) => Buffer.from([b]));
    expect(split(chunks)).toEqual(['é€😀']);
  });

  it('delivers a 3 MiB line whole in odd-sized chunks', () => {
    const big = 'é'.repeat(3 * 512 * 1024);
    const bytes = Buffer.from(`${big}\nnext\n`);
    const chunks: Buffer[] = [];
    for (let off = 0; off < bytes.length; off += 16 * 1024 + 1)
      chunks.push(bytes.subarray(off, off + 16 * 1024 + 1));
    const lines = split(chunks);
    expect(lines).toHaveLength(2);
    expect(lines[0] === big).toBe(true);
    expect(lines[1]).toBe('next');
  });
});
