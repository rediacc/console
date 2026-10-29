/**
 * Reads one file out of a zip archive with node:zlib alone.
 *
 * rdc runs on Windows, which has no `unzip`, and the CLI carries no archive dependency, so this reads the central directory itself. It handles what a release archive uses: stored and deflated entries, no encryption, no zip64. The entry is matched by its exact name, and the caller decides where the bytes go, so an entry name never becomes a filesystem path (no zip-slip). The CRC-32 of the inflated bytes is checked against the directory.
 */

import { crc32, inflateRawSync } from 'node:zlib';

const EOCD_SIG = 0x06054b50;
const CENTRAL_SIG = 0x02014b50;
const LOCAL_SIG = 0x04034b50;
const EOCD_MIN = 22;
const MAX_COMMENT = 0xffff;

export class ZipError extends Error {}

function findEndOfCentralDirectory(buf: Buffer): number {
  const stop = Math.max(0, buf.length - EOCD_MIN - MAX_COMMENT);
  for (let i = buf.length - EOCD_MIN; i >= stop; i--) {
    if (buf.readUInt32LE(i) === EOCD_SIG) return i;
  }
  throw new ZipError('no end-of-central-directory record');
}

interface CentralEntry {
  name: string;
  flags: number;
  method: number;
  crc: number;
  compressedSize: number;
  size: number;
  localOffset: number;
}

function* centralEntries(buf: Buffer): Generator<CentralEntry> {
  const eocd = findEndOfCentralDirectory(buf);
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  if (count === 0xffff || p === 0xffffffff) throw new ZipError('zip64 archives are not supported');
  for (let i = 0; i < count; i++) {
    if (p + 46 > buf.length || buf.readUInt32LE(p) !== CENTRAL_SIG) {
      throw new ZipError('corrupt central directory');
    }
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    yield {
      flags: buf.readUInt16LE(p + 8),
      method: buf.readUInt16LE(p + 10),
      crc: buf.readUInt32LE(p + 16),
      compressedSize: buf.readUInt32LE(p + 20),
      size: buf.readUInt32LE(p + 24),
      localOffset: buf.readUInt32LE(p + 42),
      name: buf.toString('utf8', p + 46, p + 46 + nameLen),
    };
    p += 46 + nameLen + extraLen + commentLen;
  }
}

/** The names of every entry in the archive. */
export function listZipEntries(buf: Buffer): string[] {
  return [...centralEntries(buf)].map((e) => e.name);
}

/** The bytes of the entry named exactly `name`, or null when the archive has no such entry. */
export function readZipEntry(buf: Buffer, name: string): Buffer | null {
  const entry = [...centralEntries(buf)].find((e) => e.name === name);
  if (!entry) return null;
  if (entry.flags & 0x1) throw new ZipError(`${name} is encrypted`);

  const lp = entry.localOffset;
  if (lp + 30 > buf.length || buf.readUInt32LE(lp) !== LOCAL_SIG) {
    throw new ZipError(`corrupt local header for ${name}`);
  }
  const start = lp + 30 + buf.readUInt16LE(lp + 26) + buf.readUInt16LE(lp + 28);
  const end = start + entry.compressedSize;
  if (end > buf.length) throw new ZipError(`${name} runs past the end of the archive`);
  const raw = buf.subarray(start, end);

  let data: Buffer;
  if (entry.method === 0) data = Buffer.from(raw);
  else if (entry.method === 8) data = inflateRawSync(raw);
  else throw new ZipError(`${name} uses unsupported compression method ${entry.method}`);

  if (data.length !== entry.size) throw new ZipError(`${name} has the wrong size`);
  if (crc32(data) >>> 0 !== entry.crc >>> 0) throw new ZipError(`${name} fails its CRC-32 check`);
  return data;
}
