import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  chunkKeys,
  corruptStoredChunk,
  type StoreAccess,
  type StoreCurl,
  flipByteScript,
  lineageChunkKeys,
  parseListKeys,
  parseNextToken,
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

describe('parseNextToken', () => {
  it('returns the token of a truncated page', () =>
    expect(
      parseNextToken(
        '<IsTruncated>true</IsTruncated><NextContinuationToken>a&amp;b</NextContinuationToken>'
      )
    ).toBe('a&b'));
  it('returns undefined on the last page', () =>
    expect(parseNextToken('<IsTruncated>false</IsTruncated>')).toBeUndefined());
  it('decodes entities in one pass, so `&amp;lt;` stays the text `&lt;`', () => {
    expect(
      parseNextToken(
        '<IsTruncated>true</IsTruncated><NextContinuationToken>x&amp;lt;y</NextContinuationToken>'
      )
    ).toBe('x&lt;y');
    expect(parseListKeys('<Key>k&amp;gt;</Key>')).toEqual(['k&gt;']);
  });
});

describe('corruptStoredChunk', () => {
  const access: StoreAccess = {
    endpoint: 'http://s',
    bucket: 'b',
    accessKey: 'k',
    secretKey: 's',
  };
  const key = `lin/${HASH}`;
  const page = (keys: string[], next?: string) =>
    Buffer.from(
      keys.map((k) => `<Key>${k}</Key>`).join('') +
        (next
          ? `<IsTruncated>true</IsTruncated><NextContinuationToken>${next}</NextContinuationToken>`
          : '<IsTruncated>false</IsTruncated>')
    );

  /** A fake store: two listing pages (the lineage chunk only on page two), one object, recorded PUTs. */
  function fakeStore(failTamperedPut = false) {
    const puts: Buffer[] = [];
    const listTokens: (string | undefined)[] = [];
    const list = (args: string[]): Buffer => {
      const second = args.includes('continuation-token=p2');
      listTokens.push(second ? 'p2' : undefined);
      return second ? page([key]) : page(['lin/manifest.json'], 'p2');
    };
    const put = (args: string[]): Buffer => {
      puts.push(readFileSync(args[args.indexOf('-T') + 1]));
      if (failTamperedPut && puts.length === 1) throw new Error('put response lost');
      return Buffer.alloc(0);
    };
    const curl: StoreCurl = (_access, args, url) => {
      if (args.includes('-G')) return list(args);
      if (args.includes('PUT')) return put(args);
      expect(url).toBe(`http://s/b/${key}`);
      return Buffer.from([1, 2, 3]);
    };
    return { curl, puts, listTokens };
  }

  it('follows the continuation token to the page that holds the lineage chunk', () => {
    const store = fakeStore();
    const corrupted = corruptStoredChunk(access, 'lin', 0, store.curl);
    expect(store.listTokens).toEqual([undefined, 'p2']);
    expect(corrupted.key).toBe(key);
    expect([...store.puts[0]]).toEqual([254, 2, 3]);
    corrupted.restore();
    expect([...store.puts[1]]).toEqual([1, 2, 3]);
  });

  it('puts the original back when the tampered PUT fails', () => {
    const store = fakeStore(true);
    expect(() => corruptStoredChunk(access, 'lin', 0, store.curl)).toThrow('put response lost');
    expect(store.puts).toHaveLength(2);
    expect([...store.puts[1]]).toEqual([1, 2, 3]);
  });
});
