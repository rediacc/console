/** A minimal ustar writer for fixture archives, so the tests need no archive dependency. */

const BLOCK = 512;

export interface TarFixtureEntry {
  name: string;
  data?: Buffer;
  /** `0` file (default), `5` directory, `2` symlink, `x` pax extended header. */
  type?: string;
  linkname?: string;
}

function header(name: string, size: number, type: string, linkname = ''): Buffer {
  const h = Buffer.alloc(BLOCK);
  h.write(name, 0, 100, 'utf8');
  h.write('0000644\0', 100, 'ascii');
  h.write('0000000\0', 108, 'ascii');
  h.write('0000000\0', 116, 'ascii');
  h.write(`${size.toString(8).padStart(11, '0')}\0`, 124, 'ascii');
  h.write('00000000000\0', 136, 'ascii');
  h.write('        ', 148, 'ascii');
  h.write(type, 156, 'ascii');
  h.write(linkname, 157, 100, 'utf8');
  h.write('ustar\u000000', 257, 'ascii');
  let sum = 0;
  for (const b of h) sum += b;
  h.write(`${sum.toString(8).padStart(6, '0')}\0 `, 148, 'ascii');
  return h;
}

/** The tar bytes of `entries`, closed by the two zero blocks. */
export function buildTar(entries: TarFixtureEntry[]): Buffer {
  const parts: Buffer[] = [];
  for (const e of entries) {
    const data = e.data ?? Buffer.alloc(0);
    parts.push(header(e.name, data.length, e.type ?? '0', e.linkname));
    parts.push(data);
    const pad = (BLOCK - (data.length % BLOCK)) % BLOCK;
    parts.push(Buffer.alloc(pad));
  }
  parts.push(Buffer.alloc(BLOCK * 2));
  return Buffer.concat(parts);
}

/** One pax `path` record, sized the way the format counts it (the length includes itself). */
export function paxPathRecord(path: string): Buffer {
  const body = ` path=${path}\n`;
  let n = body.length + 1;
  while (`${n}${body}`.length !== n) n = `${n}${body}`.length;
  return Buffer.from(`${n}${body}`, 'utf8');
}
