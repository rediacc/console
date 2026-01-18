/**
 * CRC32 Hash Utility
 *
 * Provides CRC32 hash calculation using IEEE polynomial.
 * Used by translation hash generation and validation scripts.
 */

// Pre-computed CRC32 lookup table (IEEE polynomial)
const crc32Table: Uint32Array = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c;
  }
  return table;
})();

/**
 * Calculate CRC32 hash of a string (IEEE polynomial)
 * @param str - Input string to hash
 * @returns 8-character lowercase hex string
 */
function crc32(str: string): string {
  let crc = 0xffffffff;
  for (let i = 0; i < str.length; i++) {
    const byte = str.charCodeAt(i) & 0xff;
    crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return ((crc ^ 0xffffffff) >>> 0).toString(16).padStart(8, '0');
}

/**
 * Flatten a JSON object and calculate hashes for all string values
 * @param obj - Object to flatten and hash
 * @param prefix - Current key prefix (for recursion)
 * @returns Record mapping dot-notation keys to their CRC32 hashes
 */
export function flattenAndHash(
  obj: Record<string, unknown>,
  prefix = ''
): Record<string, string> {
  const hashes: Record<string, string> = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(hashes, flattenAndHash(value as Record<string, unknown>, fullPath));
    } else if (typeof value === 'string') {
      hashes[fullPath] = crc32(value);
    }
  }

  return hashes;
}
