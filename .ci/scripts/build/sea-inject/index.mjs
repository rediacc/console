/**
 * Streaming SEA-blob injector — a from-scratch replacement for `npx postject`.
 *
 * Why this exists (rediacc/console#525): postject's binary surgery is LIEF
 * compiled to wasm32, so the executable AND the blob must fit in a 4GB address
 * space, and it amplifies the blob roughly 11.6x in memory. Our SEA blob is
 * ~561MB, which needs ~7.4GB — unreachable. Upstream is dead (last release
 * 2023-05) and its wasm memory is already at the architectural maximum, so this
 * cannot be fixed there. Every backend here streams the blob in fixed-size
 * chunks, so peak RSS is a small constant independent of blob size.
 *
 * This module only dispatches on the container format, detected from magic
 * bytes. The per-format surgery lives in elf.mjs / macho.mjs / pe.mjs; the
 * shared streaming/alignment primitives live in common.mjs.
 */
import fs from 'node:fs';
import { injectElf } from './elf.mjs';
import { injectMacho } from './macho.mjs';
import { injectPe } from './pe.mjs';

/** Detect the executable format from the first bytes. */
export function detectFormat(binaryPath) {
  const fd = fs.openSync(binaryPath, 'r');
  try {
    const magic = Buffer.alloc(4);
    fs.readSync(fd, magic, 0, 4, 0);
    if (magic.toString('latin1') === '\x7fELF') return 'elf';
    const u32 = magic.readUInt32LE(0);
    // Mach-O thin (both endiannesses) and fat/universal.
    if (u32 === 0xfeedfacf || u32 === 0xcffaedfe || u32 === 0xfeedface || u32 === 0xcefaedfe)
      return 'macho';
    if (u32 === 0xcafebabe || u32 === 0xbebafeca) return 'macho'; // fat; backend rejects
    if (magic.toString('latin1', 0, 2) === 'MZ') return 'pe';
    throw new Error(`unrecognized executable format (magic ${magic.toString('hex')})`);
  } finally {
    fs.closeSync(fd);
  }
}

/**
 * Inject `blobPath` into `binaryPath` under resource name `resourceName`
 * (NODE_SEA_BLOB) and flip the SEA sentinel `fuse`. Mutates the binary in place.
 */
export function inject({ binaryPath, resourceName, blobPath, fuse }) {
  const args = { binaryPath, resourceName, blobPath, fuse };
  switch (detectFormat(binaryPath)) {
    case 'elf':
      return injectElf(args);
    case 'macho':
      return injectMacho(args);
    case 'pe':
      return injectPe(args);
    default:
      throw new Error('unreachable');
  }
}
