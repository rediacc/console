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
