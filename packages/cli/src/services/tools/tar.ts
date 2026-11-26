/**
 * Reads regular files out of a tar archive held in memory, with no archive dependency.
 *
 * MSYS2 package archives (`.pkg.tar.zst`) are ustar written by bsdtar; node:zlib decompresses the zstd layer and this walks the 512-byte headers. It handles ustar and old-GNU headers, the ustar `prefix` field, a pax extended header's `path` and GNU long names, and checks every header checksum. Only regular files are returned: links, directories and devices are skipped, so an entry never becomes a filesystem path on its own (the caller picks the destination by name, no tar-slip).
 */

const BLOCK = 512;

export class TarError extends Error {}

export interface TarEntry {
  /** The archive path, `/`-separated, without a leading `./`. */
  name: string;
  data: Buffer;
}

function field(header: Buffer, start: number, length: number): string {
  const raw = header.subarray(start, start + length);
  const nul = raw.indexOf(0);
  return raw.subarray(0, nul === -1 ? raw.length : nul).toString('utf8');
}

function octal(header: Buffer, start: number, length: number, what: string): number {
  const first = header[start];
  // GNU base-256: the high bit of the first byte set, the rest a big-endian magnitude.
  if (first !== undefined && first & 0x80) {
    let value = first & 0x7f;
    for (let i = start + 1; i < start + length; i++) value = value * 256 + (header[i] ?? 0);
    return value;
  }
  const text = field(header, start, length).trim();
  if (text === '') return 0;
  if (!/^[0-7]+$/.test(text)) throw new TarError(`bad ${what} field ${JSON.stringify(text)}`);
  return Number.parseInt(text, 8);
}

function checksumOk(header: Buffer): boolean {
  const stored = octal(header, 148, 8, 'checksum');
  let sum = 0;
  for (let i = 0; i < BLOCK; i++) sum += i >= 148 && i < 156 ? 0x20 : (header[i] ?? 0);
  return sum === stored;
}

/** The `path` record of a pax extended header body, or null when it carries none. */
function paxPath(body: Buffer): string | null {
  let path: string | null = null;
  let at = 0;
  while (at < body.length) {
    const space = body.indexOf(0x20, at);
    if (space === -1) break;
    const length = Number.parseInt(body.subarray(at, space).toString('ascii'), 10);
    if (!Number.isFinite(length) || length <= 0) throw new TarError('bad pax record length');
    const record = body.subarray(space + 1, at + length - 1).toString('utf8');
    const eq = record.indexOf('=');
    if (eq !== -1 && record.slice(0, eq) === 'path') path = record.slice(eq + 1);
    at += length;
  }
  return path;
}

const normalize = (name: string): string => name.replace(/^(\.\/)+/, '');

interface RawEntry {
  header: Buffer;
  type: string;
  body: Buffer;
  /** Offset of the next header. */
  next: number;
}

/** The header at `offset` and its body, or null at the end-of-archive block. */
function rawEntryAt(archive: Buffer, offset: number): RawEntry | null {
  const header = archive.subarray(offset, offset + BLOCK);
  if (header.every((b) => b === 0)) return null;
  if (!checksumOk(header)) throw new TarError(`header checksum mismatch at offset ${offset}`);
  const size = octal(header, 124, 12, 'size');
  const bodyStart = offset + BLOCK;
  if (bodyStart + size > archive.length) {
    throw new TarError(`entry at offset ${offset} is truncated`);
  }
  return {
    header,
    type: String.fromCharCode(header[156] || 0x30),
    body: archive.subarray(bodyStart, bodyStart + size),
    next: bodyStart + Math.ceil(size / BLOCK) * BLOCK,
  };
}

/** The path a header names on its own: `prefix/name` for ustar, `name` otherwise. */
function headerName(header: Buffer): string {
  const prefix = field(header, 257, 6).startsWith('ustar') ? field(header, 345, 155) : '';
  const base = field(header, 0, 100);
  return prefix ? `${prefix}/${base}` : base;
}

/** Apply one raw entry: a pax or GNU long-name header sets the next name, a regular file is collected. */
function applyEntry(raw: RawEntry, nextName: string | null, entries: TarEntry[]): string | null {
  if (raw.type === 'x') return paxPath(raw.body) ?? nextName;
  if (raw.type === 'L') return field(raw.body, 0, raw.body.length);
  if (raw.type === 'g') return nextName;
  if (raw.type === '0' || raw.type === '7') {
    entries.push({
      name: normalize(nextName ?? headerName(raw.header)),
      data: Buffer.from(raw.body),
    });
  }
  return null;
}

/** Every regular file in `archive`, in archive order. */
export function readTarEntries(archive: Buffer): TarEntry[] {
  const entries: TarEntry[] = [];
  let offset = 0;
  let nextName: string | null = null;
  while (offset + BLOCK <= archive.length) {
    const raw = rawEntryAt(archive, offset);
    if (!raw) return entries;
    offset = raw.next;
    nextName = applyEntry(raw, nextName, entries);
  }
  if (offset === archive.length) return entries;
  throw new TarError(`archive ends inside a header at offset ${offset}`);
}
