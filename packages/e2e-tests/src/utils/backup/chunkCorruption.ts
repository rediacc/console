import type { StorageTestHelper } from '../storage/StorageTestHelper';

/**
 * Corruption-injection fixture for the chunk store: flips one byte of a stored chunk so a restore
 * must refuse it and a deep verify must report it (plan box K11), and later suites can reuse it.
 *
 * Chunk objects are named by their SHA-256 (64 lowercase hex characters), and that is the only
 * property read here. The key layout is the server's to name, so this module never composes a
 * prefix: it lists the bucket and recognizes chunks by the hash-named last segment.
 */

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

export interface CorruptedChunk {
  bucket: string;
  key: string;
  offset: number;
  /** The byte before the flip, two-digit hex. */
  before: string;
  /** The byte after the flip, two-digit hex. */
  after: string;
}

/**
 * Flip one byte of one stored chunk in `bucket` and write the object back under the same key.
 * `key` pins a specific chunk; by default the first chunk object in the listing is used.
 * Throws when the bucket holds no chunk or any step fails, so a suite never reads a "refused"
 * result off a corruption that was never applied.
 */
export async function corruptStoredChunk(
  storage: StorageTestHelper,
  bucket: string,
  options: { key?: string; offset?: number } = {}
): Promise<CorruptedChunk> {
  const offset = options.offset ?? 0;
  const key = options.key ?? chunkKeys(await storage.listObjects(bucket))[0];
  if (!key) throw new Error(`corruptStoredChunk: no chunk object in bucket ${bucket}`);

  const work = `/tmp/chunk-corrupt-${Date.now()}`;
  const download = await storage.downloadFile(bucket, key, work);
  if (!download.success) {
    throw new Error(`corruptStoredChunk: download of ${key} failed: ${download.stderr}`);
  }
  try {
    const flipped = await storage.runOnBridge(flipByteScript(work, offset));
    const [before, after] = flipped.stdout.trim().split(/\s+/);
    if (!flipped.success || !before || !after) {
      throw new Error(
        `corruptStoredChunk: no byte at offset ${offset} of ${key}: ${flipped.stderr}`
      );
    }
    const upload = await storage.uploadFile(bucket, work, key);
    if (!upload.success) {
      throw new Error(`corruptStoredChunk: upload of ${key} failed: ${upload.stderr}`);
    }
    return { bucket, key, offset, before, after };
  } finally {
    await storage.runOnBridge(`rm -f '${work}'`);
  }
}
