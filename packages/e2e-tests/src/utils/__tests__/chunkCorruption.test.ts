import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  chunkKeys,
  flipByteScript,
  lineageChunkKeys,
  parseListKeys,
  storeAccessFromEnv,
} from '../backup/chunkCorruption';

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

describe('store listing helpers', () => {
  it('decodes keys out of a ListObjectsV2 body', () => {
    const xml = `<ListBucketResult><Contents><Key>t/a&amp;b/${HASH}</Key></Contents><Contents><Key>m.json</Key></Contents></ListBucketResult>`;
    expect(parseListKeys(xml)).toEqual([`t/a&b/${HASH}`, 'm.json']);
  });

  it('keeps only the chunks of the named lineage', () => {
    const keys = [`t/x/l/L1/c/${HASH}`, `t/x/l/L2/c/${HASH}`, 't/x/l/L1/m/manifest'];
    expect(lineageChunkKeys(keys, 'L1')).toEqual([`t/x/l/L1/c/${HASH}`]);
  });

  it('needs both credentials and defaults the endpoint', () => {
    expect(storeAccessFromEnv({ E2E_BACKUP_S3_KEY: 'k' })).toBeUndefined();
    expect(storeAccessFromEnv({ E2E_BACKUP_S3_KEY: 'k', E2E_BACKUP_S3_SECRET: 's' })).toMatchObject(
      {
        endpoint: 'http://127.0.0.1:9100',
        accessKey: 'k',
      }
    );
  });
});
