/**
 * Corruption-injection fixture for the chunk store: flips one byte of a stored chunk so a restore
 * must refuse it and a deep verify must report it (plan box K11), and later suites can reuse it.
 *
 * Chunk objects are named by their SHA-256 (64 lowercase hex characters), and that is the only
 * property read here. The key layout is the server's to name, so this module never composes a
 * prefix: it lists the bucket and recognizes chunks by the hash-named last segment.
 */

import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

/** A chunk object key: the last path segment is exactly one SHA-256 in lowercase hex. */
const CHUNK_KEY = /(?:^|\/)[0-9a-f]{64}$/;

/** The keys of `keys` that are chunk objects, in input order. */
export function chunkKeys(keys: readonly string[]): string[] {
  return keys.filter((key) => CHUNK_KEY.test(key));
}

/**
 * Shell fragment that XORs byte `offset` of `file` with 0xff in place and prints
 * `<before> <after>` as two-digit hex. Exits non-zero when the file is shorter than `offset + 1`.
 */
export function flipByteScript(file: string, offset: number): string {
  if (!Number.isInteger(offset) || offset < 0) {
    throw new Error(`flipByteScript: offset must be a non-negative integer, got ${offset}`);
  }
  const quoted = `'${file.replaceAll("'", "'\\''")}'`;
  return [
    `before=$(od -An -tu1 -j ${offset} -N1 ${quoted} | tr -d ' ')`,
    '[ -n "$before" ] || exit 3',
    'after=$((before ^ 255))',
    `printf "$(printf '\\\\%03o' "$after")" | dd of=${quoted} bs=1 seek=${offset} conv=notrunc status=none`,
    'printf "%02x %02x\\n" "$before" "$after"',
  ].join('\n');
}

/** The `<Key>` values of an S3 ListObjectsV2 response, XML entities decoded. */
export function parseListKeys(xml: string): string[] {
  return [...xml.matchAll(/<Key>([^<]*)<\/Key>/g)].map((m) =>
    m[1].replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>')
  );
}

/** The continuation token of a truncated ListObjectsV2 page, or undefined on the last page. */
export function parseNextToken(xml: string): string | undefined {
  if (!/<IsTruncated>true<\/IsTruncated>/.test(xml)) return undefined;
  const token = /<NextContinuationToken>([^<]*)<\/NextContinuationToken>/.exec(xml)?.[1];
  return token?.replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>');
}

/** Chunk objects of one lineage: hash-named keys with the lineage guid as a path segment. */
export function lineageChunkKeys(keys: readonly string[], lineage: string): string[] {
  return chunkKeys(keys).filter((key) => key.split('/').includes(lineage));
}

/** The dev store's coordinates, from the same `E2E_BACKUP_S3_*` variables suite 27 reads. */
export interface StoreAccess {
  endpoint: string;
  bucket: string;
  accessKey: string;
  secretKey: string;
}

/** Store access from the environment, or undefined when the credentials are not both set. */
export function storeAccessFromEnv(env: NodeJS.ProcessEnv = process.env): StoreAccess | undefined {
  const accessKey = env.E2E_BACKUP_S3_KEY;
  const secretKey = env.E2E_BACKUP_S3_SECRET;
  if (!accessKey || !secretKey) return undefined;
  return {
    endpoint: (env.E2E_BACKUP_S3_ENDPOINT || 'http://127.0.0.1:9100').replace(/\/+$/, ''),
    bucket: env.E2E_BACKUP_S3_BUCKET || 'rediacc-backups-probe',
    accessKey,
    secretKey,
  };
}

/** An object that was corrupted in the store; `restore` puts the original bytes back. */
export interface CorruptedChunk {
  key: string;
  /** Hex pair printed by the flip, `<before> <after>`. */
  flipped: string;
  restore: () => void;
}

function storeCurl(access: StoreAccess, args: string[], url: string): Buffer {
  // Credentials ride a curl config on stdin, never argv.
  return execFileSync(
    'curl',
    ['-sS', '--fail', '--aws-sigv4', 'aws:amz:us-east-1:s3', '-K', '-', ...args, url],
    { input: `user = "${access.accessKey}:${access.secretKey}"\n`, maxBuffer: 256 * 1024 * 1024 }
  );
}

/**
 * Flip one byte of one stored chunk of `lineage` in place (K11a). The caller owns `restore()` and
 * must call it in a finally block: the store is shared, and a left-over corrupt chunk breaks every
 * later restore of that lineage.
 */
export function corruptStoredChunk(
  access: StoreAccess,
  lineage: string,
  offset = 0
): CorruptedChunk {
  const base = `${access.endpoint}/${access.bucket}`;
  const pages: string[] = [];
  const allKeys: string[] = [];
  let token: string | undefined;
  do {
    const page = storeCurl(
      access,
      [
        '-G',
        '--data-urlencode',
        'list-type=2',
        ...(token ? ['--data-urlencode', `continuation-token=${token}`] : []),
      ],
      base
    ).toString('utf8');
    pages.push(page);
    allKeys.push(...parseListKeys(page));
    token = parseNextToken(page);
  } while (token);
  const keys = lineageChunkKeys(allKeys, lineage);
  if (keys.length === 0) {
    throw new Error(
      `no chunk object of lineage ${lineage} in bucket ${access.bucket} (${pages.length} page(s), listing: ${pages[0].slice(0, 400)})`
    );
  }
  const key = keys[0];
  const dir = mkdtempSync(path.join(tmpdir(), 'chunk-corrupt-'));
  const original = path.join(dir, 'original');
  const tampered = path.join(dir, 'tampered');
  const url = `${base}/${key}`;
  try {
    writeFileSync(original, storeCurl(access, [], url));
    copyFileSync(original, tampered);
    const flipped = execFileSync('bash', ['-c', flipByteScript(tampered, offset)])
      .toString()
      .trim();
    storeCurl(access, ['-X', 'PUT', '-T', tampered], url);
    return {
      key,
      flipped,
      restore: () => {
        try {
          storeCurl(access, ['-X', 'PUT', '-T', original], url);
        } finally {
          rmSync(dir, { recursive: true, force: true });
        }
      },
    };
  } catch (error) {
    // A PUT whose response was lost may still have stored the tampered bytes: put the original back (when it was read) before giving up.
    try {
      if (existsSync(original)) storeCurl(access, ['-X', 'PUT', '-T', original], url);
    } catch {
      // The store is unreachable; the original error is the one to report.
    }
    rmSync(dir, { recursive: true, force: true });
    throw error;
  }
}
