import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { chunkKeys, flipByteScript } from '../backup/chunkCorruption';

const HASH = 'a'.repeat(64);

describe('chunkKeys', () => {
  it('keeps hash-named objects and drops manifests, indexes and short names', () => {
    const keys = [
      `x/y/${HASH}`,
      'x/y/manifest.json',
      `${HASH}`,
      `x/${'b'.repeat(63)}`,
      `x/${HASH}.tmp`,
    ];
    expect(chunkKeys(keys)).toEqual([`x/y/${HASH}`, HASH]);
  });
});

describe('flipByteScript', () => {
  const run = (file: string, offset: number) =>
    execFileSync('bash', ['-c', flipByteScript(file, offset)]).toString();

  it('flips exactly one byte and reports before and after', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'flip-'));
    try {
      const file = path.join(dir, 'obj');
      writeFileSync(file, Buffer.from([0x00, 0x41, 0x7f, 0xff]));
      expect(run(file, 1).trim()).toBe('41 be');
      expect([...readFileSync(file)]).toEqual([0x00, 0xbe, 0x7f, 0xff]);
      expect(run(file, 3).trim()).toBe('ff 00');
      expect([...readFileSync(file)]).toEqual([0x00, 0xbe, 0x7f, 0x00]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('fails when the file is shorter than the offset', () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'flip-'));
    try {
      const file = path.join(dir, 'obj');
      writeFileSync(file, Buffer.from([1]));
      expect(() => run(file, 5)).toThrow();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('rejects a negative offset', () => {
    expect(() => flipByteScript('/tmp/x', -1)).toThrow(/non-negative/);
  });
});
