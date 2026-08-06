/**
 * ELF64 SEA injector (linux-x64, linux-arm64, linux-musl-*).
 *
 * Architecture does not matter here: ELF64 little-endian is the same container
 * on x64 and arm64, and nothing below touches instruction encodings.
 *
 * What node looks for at runtime (postject-api.h, __linux__ branch): it calls
 * dl_iterate_phdr for the main program, walks every PT_NOTE *program header*,
 * and scans notes for one named NODE_SEA_BLOB. Two consequences drive the
 * design:
 *   - the blob must live in a PT_NOTE that is inside a PT_LOAD. A section
 *     header is not enough; sections are not mapped, and a section-only
 *     injection segfaults (measured).
 *   - the note must be a well-formed ElfW(Nhdr) chain, because the scanner
 *     walks it sequentially.
 *
 * Layout produced, appended at page-aligned EOF with original bytes untouched:
 *
 *   [ original file ][ pad ][ phdr table (n+1) ][ original notes ][ SEA note ]
 *
 * plus a new PT_LOAD (R) covering the region, PT_NOTE repointed into it,
 * PT_PHDR + e_phoff repointed at the relocated table. The phdr table must move
 * because there is no slack after the original one.
 *
 * The original notes are copied verbatim because the single PT_NOTE gets
 * repointed, and glibc still expects to find NT_GNU_BUILD_ID / NT_GNU_ABI_TAG
 * through it.
 *
 * Some builds ship with NO PT_NOTE at all (the unofficial musl-arm64 node is one
 * — it has 9 program headers and not a single PT_NOTE). There is nothing to
 * repoint there, so we instead APPEND a fresh PT_NOTE segment: e_phnum grows by
 * two (one PT_LOAD + one PT_NOTE) instead of one. node's runtime lookup walks
 * every PT_NOTE, so an added one is found the same way a repointed one is. This
 * is invisible when testing only on x64 / glibc-arm64 (both have a PT_NOTE), so
 * the guard used to fail closed here with "no PT_NOTE segment to repoint".
 *
 * The region's vaddr is chosen so (vaddr - offset) equals the first PT_LOAD's
 * delta. That keeps the relocated phdr table correct both for kernels that
 * trust PT_PHDR and for the older AT_PHDR computation derived from the first
 * PT_LOAD. postject picks an unrelated vaddr and relies on PT_PHDR alone.
 */
import fs from 'node:fs';
import { Buffer } from 'node:buffer';
import { alignUp, findSentinelFuse, readAt, streamBlob, writeAll, writeZeros } from './common.mjs';

const PT_LOAD = 1;
const PT_NOTE = 4;
const PT_PHDR = 6;
const PF_R = 4;

const EHDR_SIZE = 64;
const PHDR_SIZE = 56;
const PAGE = 0x1000;

/** Build the NODE_SEA_BLOB note header: everything preceding the blob bytes. */
function buildNoteHeader(noteName, blobSize) {
  const name = Buffer.from(`${noteName}\0`, 'latin1');
  const header = Buffer.alloc(12 + alignUp(name.length, 4));
  header.writeUInt32LE(name.length, 0); // n_namesz, unpadded per spec
  header.writeUInt32LE(blobSize, 4); // n_descsz
  header.writeUInt32LE(0, 8); // n_type
  name.copy(header, 12);
  return header;
}

function setSegment(buf, off, { type, flags, offset, vaddr, size, align }) {
  buf.writeUInt32LE(type, off + 0x00);
  buf.writeUInt32LE(flags, off + 0x04);
  buf.writeBigUInt64LE(BigInt(offset), off + 0x08);
  buf.writeBigUInt64LE(BigInt(vaddr), off + 0x10);
  buf.writeBigUInt64LE(BigInt(vaddr), off + 0x18); // p_paddr mirrors p_vaddr
  buf.writeBigUInt64LE(BigInt(size), off + 0x20);
  buf.writeBigUInt64LE(BigInt(size), off + 0x28);
  buf.writeBigUInt64LE(BigInt(align), off + 0x30);
}

export function injectElf({ binaryPath, resourceName, blobPath, fuse }) {
  const origSize = fs.statSync(binaryPath).size;
  const blobSize = fs.statSync(blobPath).size;
  const fd = fs.openSync(binaryPath, 'r+');
  try {
    const ehdr = readAt(fd, EHDR_SIZE, 0);
    if (ehdr[4] !== 2) throw new Error('only ELF64 is supported');
    if (ehdr[5] !== 1) throw new Error('only little-endian ELF is supported');

    const ePhoff = Number(ehdr.readBigUInt64LE(0x20));
    const ePhentsize = ehdr.readUInt16LE(0x36);
    const ePhnum = ehdr.readUInt16LE(0x38);
    if (ePhentsize !== PHDR_SIZE) throw new Error(`unexpected e_phentsize ${ePhentsize}`);

    const phdrs = readAt(fd, ePhentsize * ePhnum, ePhoff);
    const entry = (i) => phdrs.subarray(i * PHDR_SIZE, (i + 1) * PHDR_SIZE);
    const pType = (e) => e.readUInt32LE(0x00);
    const pOffset = (e) => Number(e.readBigUInt64LE(0x08));
    const pVaddr = (e) => Number(e.readBigUInt64LE(0x10));
    const pFilesz = (e) => Number(e.readBigUInt64LE(0x20));
    const pMemsz = (e) => Number(e.readBigUInt64LE(0x28));

    let noteIdx = -1;
    let phdrIdx = -1;
    let firstLoadIdx = -1;
    let maxVaddrEnd = 0;
    for (let i = 0; i < ePhnum; i++) {
      const e = entry(i);
      const t = pType(e);
      if (t === PT_NOTE && noteIdx < 0) noteIdx = i;
      if (t === PT_PHDR && phdrIdx < 0) phdrIdx = i;
      if (t === PT_LOAD) {
        if (firstLoadIdx < 0) firstLoadIdx = i;
        maxVaddrEnd = Math.max(maxVaddrEnd, pVaddr(e) + pMemsz(e));
      }
    }
    if (phdrIdx < 0) throw new Error('no PT_PHDR segment to relocate');
    if (firstLoadIdx < 0) throw new Error('no PT_LOAD segment');

    // Fail before mutating anything if the sentinel is missing/ambiguous.
    const fuseOffset = findSentinelFuse(fd, origSize, fuse);

    // Repoint the existing PT_NOTE if there is one; otherwise append a fresh
    // one (musl-arm64 has none). Appending grows e_phnum by two.
    const hasNote = noteIdx >= 0;
    const origNotes = hasNote
      ? readAt(fd, pFilesz(entry(noteIdx)), pOffset(entry(noteIdx)))
      : Buffer.alloc(0);
    const loadSlot = ePhnum; // first appended slot: the covering PT_LOAD
    const noteSlot = hasNote ? noteIdx : ePhnum + 1; // repoint, or second appended slot

    const newPhnum = ePhnum + (hasNote ? 1 : 2);
    const phdrTableSize = newPhnum * PHDR_SIZE;
    const noteHeader = buildNoteHeader(resourceName, blobSize);

    const regionOff = alignUp(origSize, PAGE);
    const phdrOff = regionOff;
    const notesOff = alignUp(phdrOff + phdrTableSize, 4);
    const seaNoteOff = alignUp(notesOff + origNotes.length, 4);
    const notesSize = seaNoteOff - notesOff + noteHeader.length + blobSize;
    const regionSize = notesOff - regionOff + notesSize;

    const firstLoad = entry(firstLoadIdx);
    let delta = pVaddr(firstLoad) - pOffset(firstLoad);
    // Never overlap an existing mapping; bump by whole pages so the
    // offset/vaddr congruence PT_LOAD requires is preserved.
    const minVaddr = alignUp(maxVaddrEnd, PAGE) + PAGE;
    if (regionOff + delta < minVaddr) {
      delta += alignUp(minVaddr - (regionOff + delta), PAGE);
    }
    const regionVaddr = regionOff + delta;

    writeZeros(fd, regionOff - origSize, origSize);

    const newPhdrs = Buffer.alloc(phdrTableSize);
    phdrs.copy(newPhdrs, 0);
    setSegment(newPhdrs, phdrIdx * PHDR_SIZE, {
      type: PT_PHDR,
      flags: PF_R,
      offset: phdrOff,
      vaddr: phdrOff + delta,
      size: phdrTableSize,
      align: 8,
    });
    setSegment(newPhdrs, noteSlot * PHDR_SIZE, {
      type: PT_NOTE,
      flags: PF_R,
      offset: notesOff,
      vaddr: notesOff + delta,
      size: notesSize,
      align: 4,
    });
    setSegment(newPhdrs, loadSlot * PHDR_SIZE, {
      type: PT_LOAD,
      flags: PF_R,
      offset: regionOff,
      vaddr: regionVaddr,
      size: regionSize,
      align: PAGE,
    });
    writeAll(fd, newPhdrs, phdrOff);

    writeZeros(fd, notesOff - (phdrOff + phdrTableSize), phdrOff + phdrTableSize);
    writeAll(fd, origNotes, notesOff);
    writeZeros(fd, seaNoteOff - (notesOff + origNotes.length), notesOff + origNotes.length);
    writeAll(fd, noteHeader, seaNoteOff);

    streamBlob(fd, blobPath, seaNoteOff + noteHeader.length, blobSize);

    ehdr.writeBigUInt64LE(BigInt(phdrOff), 0x20); // e_phoff
    ehdr.writeUInt16LE(newPhnum, 0x38); // e_phnum
    writeAll(fd, ehdr, 0);

    writeAll(fd, Buffer.from('1', 'latin1'), fuseOffset);
    fs.fsyncSync(fd);

    return {
      format: 'elf',
      blobSize,
      blobOffset: seaNoteOff + noteHeader.length,
      detail:
        `${hasNote ? 'repointed' : 'appended'} PT_NOTE, region off=${regionOff} ` +
        `vaddr=0x${regionVaddr.toString(16)} size=${regionSize}, ` +
        `e_phoff ${ePhoff} -> ${phdrOff} (${ePhnum} -> ${newPhnum} segments)`,
    };
  } finally {
    fs.closeSync(fd);
  }
}
