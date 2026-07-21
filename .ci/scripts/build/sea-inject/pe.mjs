/**
 * PE32+ SEA injector (win-x64; the same container serves win-arm64).
 *
 * What node looks for at runtime (postject-api.h, _WIN32 branch, the authority):
 *
 *     FindResourceA(NULL, "NODE_SEA_BLOB", MAKEINTRESOURCEA(10) // RT_RCDATA)
 *
 * FindResource walks the PE resource *tree*, so a bare appended section is not
 * enough: node will not find it. The blob must sit in a genuine resource entry
 * reachable as Type ID 10 (RT_RCDATA) -> string name "NODE_SEA_BLOB" -> a
 * language leaf whose IMAGE_RESOURCE_DATA_ENTRY.RVA points at the bytes.
 *
 * node.exe already ships resources (icon, version info, manifest). Those must be
 * preserved, so we do not replace the tree, we rebuild it: parse the existing
 * tree, add our RT_RCDATA/NODE_SEA_BLOB entry, and re-serialize the whole thing
 * into a fresh section appended at end-of-file. The existing resources are tiny
 * (well under 1MB) so tree + their payload bytes are buffered in memory; only
 * the ~600MB blob ever streams (via streamBlob).
 *
 * Layout produced, appended at file-aligned EOF with original bytes untouched
 * except for three surgical header edits and the fuse flip:
 *
 *   [ original file ][ pad ][ new .rsrc: dir tree | strings | data-entries |
 *                             small payloads | pad | BLOB ]
 *
 * The blob lives at the very end of the new section so the serialized tree stays
 * small and buffered while the blob streams in after it.
 *
 * Three header edits: (1) the original `.rsrc` is renamed `.rdata2` so there are
 * not two sections named `.rsrc` (a known packer/AV heuristic) - its bytes stay
 * put, just unreferenced; (2) a new IMAGE_SECTION_HEADER for `.rsrc` is written
 * into the slack after the section table (we verify the slack exists first, and
 * fail loudly rather than clobber code if it does not); (3) DataDirectory[2]
 * (Resource Table) is repointed at the new section. SizeOfImage,
 * SizeOfInitializedData, NumberOfSections and the PE CheckSum follow.
 *
 * node.exe ships Authenticode-signed; appending to the image necessarily breaks
 * that signature (postject does this too, so it is not a regression). We go one
 * step further and zero the Certificate Table directory (dir[4]) so the result
 * reads as honestly unsigned rather than "signature present but invalid".
 *
 * The CheckSum is recomputed by streaming the whole file. Windows verifies it
 * for signed images and drivers, and a stale checksum is a red flag to signing
 * tooling and some AV; we cannot leave the pre-injection value in place. It is
 * summed with the CheckSum field itself treated as zero, then the file size is
 * added - the classic imagehlp CheckSumMappedFile algorithm.
 */
import fs from 'node:fs';
import { Buffer } from 'node:buffer';
import { alignUp, findSentinelFuse, readAt, streamBlob, writeAll, writeZeros } from './common.mjs';

const RT_RCDATA = 10;
const SEC_HDR_SIZE = 40;
const DATA_ENTRY_SIZE = 16; // IMAGE_RESOURCE_DATA_ENTRY
const DIR_SIZE = 16; // IMAGE_RESOURCE_DIRECTORY
const DIR_ENTRY_SIZE = 8; // IMAGE_RESOURCE_DIRECTORY_ENTRY
const HIGH_BIT = 0x80000000;
const SCN_INITIALIZED_READ = 0x40000040; // CNT_INITIALIZED_DATA | MEM_READ

/**
 * Parse the resource tree rooted at `base` (a byte offset within `rsrc`, which
 * is the raw bytes of the section that DataDirectory[2] points into). All
 * subdirectory/string offsets in the tree are relative to that section base,
 * which is exactly `rsrc` offset 0. Data-entry RVAs are absolute image RVAs, so
 * we subtract `sectionRva` to reach back into `rsrc`.
 */
function parseDir(rsrc, off, sectionRva) {
    const named = rsrc.readUInt16LE(off + 12);
    const ids = rsrc.readUInt16LE(off + 14);
    const entries = [];
    let e = off + DIR_SIZE;
    for (let i = 0; i < named + ids; i++) {
        const nameField = rsrc.readUInt32LE(e);
        const offField = rsrc.readUInt32LE(e + 4);
        const key = {};
        if (nameField & HIGH_BIT) {
            const so = nameField & ~HIGH_BIT;
            const len = rsrc.readUInt16LE(so);
            key.name = rsrc.toString('utf16le', so + 2, so + 2 + len * 2);
        } else {
            key.id = nameField;
        }
        let child;
        if (offField & HIGH_BIT) {
            child = parseDir(rsrc, offField & ~HIGH_BIT, sectionRva);
        } else {
            const dataRva = rsrc.readUInt32LE(offField);
            const size = rsrc.readUInt32LE(offField + 4);
            const codepage = rsrc.readUInt32LE(offField + 8);
            const start = dataRva - sectionRva;
            child = { isDir: false, codepage, bytes: rsrc.subarray(start, start + size) };
        }
        entries.push({ ...key, child });
        e += DIR_ENTRY_SIZE;
    }
    return { isDir: true, entries };
}

/** Get (creating if absent) the child directory reached by an id/name key. */
function childDir(dir, key) {
    let entry = dir.entries.find((x) => (key.id != null ? x.id === key.id : x.name === key.name));
    if (!entry) {
        entry = { ...key, child: { isDir: true, entries: [] } };
        dir.entries.push(entry);
    }
    if (!entry.child.isDir) throw new Error('resource path collides with an existing leaf');
    return entry.child;
}

/**
 * Windows requires each directory's entries sorted: named entries first, ordered
 * by UTF-16 code units, then id entries ascending. FindResource relies on it
 * (binary search), and llvm-readobj/the loader assume it. We sort every level.
 */
function sortDir(node) {
    if (!node.isDir) return;
    node.entries.sort((a, b) => {
        const an = a.name != null;
        const bn = b.name != null;
        if (an !== bn) return an ? -1 : 1;
        if (an) return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
        return a.id - b.id;
    });
    for (const en of node.entries) sortDir(en.child);
}

/**
 * Two-pass serializer. Pass 1 assigns a byte offset (relative to section start)
 * to every directory, name string, data-entry struct and payload; the blob's
 * payload is placed last so everything before it can be written from one small
 * buffer while the blob streams. Pass 2 writes that buffer. Returns the small
 * buffer plus the blob's in-section offset and the section's virtual size.
 */
function serializeTree(root, sectionRva, blobLeaf, blobSize) {
    const dirs = [];
    const leaves = [];
    const named = [];
    (function walk(node) {
        if (node.isDir) {
            dirs.push(node);
            for (const en of node.entries) {
                if (en.name != null) named.push(en);
                walk(en.child);
            }
        } else {
            leaves.push(node);
        }
    })(root);

    let cur = 0;
    for (const d of dirs) {
        d._off = cur;
        cur += DIR_SIZE + DIR_ENTRY_SIZE * d.entries.length;
    }
    cur = alignUp(cur, 4);
    for (const en of named) {
        en._nameOff = cur;
        cur += 2 + en.name.length * 2;
        cur = alignUp(cur, 2);
    }
    cur = alignUp(cur, 8);
    for (const lf of leaves) {
        lf._deOff = cur;
        cur += DATA_ENTRY_SIZE;
    }
    cur = alignUp(cur, 8);
    for (const lf of leaves) {
        if (lf === blobLeaf) continue;
        lf._dataOff = cur;
        cur += lf.bytes.length;
        cur = alignUp(cur, 8);
    }
    const blobOff = alignUp(cur, 8);
    blobLeaf._dataOff = blobOff;
    const virtualSize = blobOff + blobSize;

    const treeBuf = Buffer.alloc(blobOff);
    for (const d of dirs) {
        let namedCount = 0;
        for (const en of d.entries) if (en.name != null) namedCount++;
        treeBuf.writeUInt16LE(namedCount, d._off + 12);
        treeBuf.writeUInt16LE(d.entries.length - namedCount, d._off + 14);
        let e = d._off + DIR_SIZE;
        for (const en of d.entries) {
            const nameField = en.name != null ? HIGH_BIT | en._nameOff : en.id;
            const offField = en.child.isDir ? HIGH_BIT | en.child._off : en.child._deOff;
            treeBuf.writeUInt32LE(nameField >>> 0, e);
            treeBuf.writeUInt32LE(offField >>> 0, e + 4);
            e += DIR_ENTRY_SIZE;
        }
    }
    for (const en of named) {
        treeBuf.writeUInt16LE(en.name.length, en._nameOff);
        treeBuf.write(en.name, en._nameOff + 2, 'utf16le');
    }
    for (const lf of leaves) {
        const size = lf === blobLeaf ? blobSize : lf.bytes.length;
        treeBuf.writeUInt32LE((sectionRva + lf._dataOff) >>> 0, lf._deOff);
        treeBuf.writeUInt32LE(size >>> 0, lf._deOff + 4);
        treeBuf.writeUInt32LE(lf.codepage >>> 0, lf._deOff + 8);
        treeBuf.writeUInt32LE(0, lf._deOff + 12); // Reserved
        if (lf !== blobLeaf) lf.bytes.copy(treeBuf, lf._dataOff);
    }
    return { treeBuf, blobOff, virtualSize };
}

/**
 * Standard PE CheckSum: a 16-bit ones-complement running sum over the whole
 * file, with the 4-byte CheckSum field treated as zero, folded, then the file
 * size added. Streamed in chunks (never buffer the file) with a carry byte so a
 * 16-bit word straddling a chunk boundary is summed intact.
 */
function computeChecksum(fd, fileSize, checksumFieldOff) {
    const CHUNK = 8 * 1024 * 1024;
    const buf = Buffer.allocUnsafe(CHUNK);
    let sum = 0;
    let carry = -1; // low byte of a word split across a chunk boundary
    let pos = 0;
    while (pos < fileSize) {
        const want = Math.min(CHUNK, fileSize - pos);
        let got = 0;
        while (got < want) {
            const r = fs.readSync(fd, buf, got, want - got, pos + got);
            if (r <= 0) throw new Error(`short read at ${pos + got}`);
            got += r;
        }
        // Zero the CheckSum field wherever it lands in this chunk.
        for (let k = 0; k < 4; k++) {
            const fo = checksumFieldOff + k;
            if (fo >= pos && fo < pos + got) buf[fo - pos] = 0;
        }
        let i = 0;
        if (carry >= 0) {
            const word = carry | (buf[0] << 8);
            sum += word;
            sum = (sum & 0xffff) + (sum >>> 16);
            carry = -1;
            i = 1;
        }
        for (; i + 1 < got; i += 2) {
            const word = buf[i] | (buf[i + 1] << 8);
            sum += word;
            sum = (sum & 0xffff) + (sum >>> 16);
        }
        if (i < got) carry = buf[i]; // odd trailing byte -> low byte of next word
        pos += got;
    }
    if (carry >= 0) {
        sum += carry; // final odd byte, high byte implicitly zero
        sum = (sum & 0xffff) + (sum >>> 16);
    }
    sum = (sum & 0xffff) + (sum >>> 16);
    return ((sum & 0xffff) + fileSize) >>> 0;
}

export function injectPe({ binaryPath, resourceName, blobPath, fuse }) {
    const origSize = fs.statSync(binaryPath).size;
    const blobSize = fs.statSync(blobPath).size;
    const fd = fs.openSync(binaryPath, 'r+');
    try {
        const dos = readAt(fd, 64, 0);
        if (dos.toString('latin1', 0, 2) !== 'MZ') throw new Error('not a PE image (no MZ)');
        const peOff = dos.readUInt32LE(0x3c);
        const sig = readAt(fd, 4, peOff);
        if (sig.toString('latin1', 0, 4) !== 'PE\0\0') throw new Error('bad PE signature');

        const coff = readAt(fd, 20, peOff + 4);
        const numSections = coff.readUInt16LE(2);
        const optSize = coff.readUInt16LE(16);
        const optOff = peOff + 24;
        const opt = readAt(fd, optSize, optOff);
        if (opt.readUInt16LE(0) !== 0x20b) throw new Error('only PE32+ (0x20b) is supported');

        const fileAlignment = opt.readUInt32LE(36);
        const sectionAlignment = opt.readUInt32LE(32);
        const sizeOfHeaders = opt.readUInt32LE(60);
        const numRvaAndSizes = opt.readUInt32LE(108);
        const resDirRva = opt.readUInt32LE(128); // DataDirectory[2].RVA
        if (resDirRva === 0) throw new Error('binary has no resource directory to merge into');

        // Section table.
        const secTableOff = optOff + optSize;
        const secTable = readAt(fd, numSections * SEC_HDR_SIZE, secTableOff);
        const sections = [];
        let minRawPtr = Infinity;
        let maxSectionEndRva = 0;
        let rsrcSecIdx = -1;
        for (let i = 0; i < numSections; i++) {
            const o = i * SEC_HDR_SIZE;
            const s = {
                idx: i,
                name: secTable.toString('latin1', o, o + 8).replace(/\0+$/, ''),
                virtualSize: secTable.readUInt32LE(o + 8),
                virtualAddress: secTable.readUInt32LE(o + 12),
                rawSize: secTable.readUInt32LE(o + 16),
                rawPtr: secTable.readUInt32LE(o + 20),
            };
            sections.push(s);
            if (s.rawPtr > 0) minRawPtr = Math.min(minRawPtr, s.rawPtr);
            maxSectionEndRva = Math.max(maxSectionEndRva, s.virtualAddress + s.virtualSize);
            if (resDirRva >= s.virtualAddress && resDirRva < s.virtualAddress + s.virtualSize) {
                rsrcSecIdx = i;
            }
        }
        if (rsrcSecIdx < 0) throw new Error('DataDirectory[2] does not fall inside any section');
        const rsrcSec = sections[rsrcSecIdx];

        // Room for one more IMAGE_SECTION_HEADER before headers/code begin. Bail
        // loudly rather than overwrite the first section's raw data or code.
        const newHdrEnd = secTableOff + (numSections + 1) * SEC_HDR_SIZE;
        if (newHdrEnd > sizeOfHeaders || newHdrEnd > minRawPtr) {
            throw new Error(
                `no slack for a new section header: need ${newHdrEnd} <= ` +
                    `min(SizeOfHeaders ${sizeOfHeaders}, firstRawPtr ${minRawPtr})`,
            );
        }

        // Fail before mutating anything if the sentinel is missing/ambiguous, so a
        // bad input leaves the file byte-identical. The fuse write happens LAST.
        const fuseOffset = findSentinelFuse(fd, origSize, fuse);

        // Buffer the whole original resource section (tree + its small payloads),
        // relative to the resource RVA, then parse the tree.
        const rsrcRaw = readAt(fd, rsrcSec.rawSize, rsrcSec.rawPtr);
        const root = parseDir(rsrcRaw, resDirRva - rsrcSec.virtualAddress, rsrcSec.virtualAddress);

        // New section RVA sits after every existing section.
        const newRva = alignUp(maxSectionEndRva, sectionAlignment);

        // Splice in RT_RCDATA(10) -> "NODE_SEA_BLOB" -> lang 0 -> blob leaf.
        const typeDir = childDir(root, { id: RT_RCDATA });
        const nameDir = childDir(typeDir, { name: resourceName });
        const blobLeaf = { isDir: false, codepage: 0, bytes: null, isBlob: true };
        nameDir.entries.push({ id: 0, child: blobLeaf });
        sortDir(root);

        const { treeBuf, blobOff, virtualSize } = serializeTree(root, newRva, blobLeaf, blobSize);

        const newRawPtr = alignUp(origSize, fileAlignment);
        const newRawSize = alignUp(virtualSize, fileAlignment);

        // --- Everything above is read-only; from here we mutate the file. ---

        // Pad any gap between EOF and the file-aligned raw pointer.
        if (newRawPtr > origSize) writeZeros(fd, newRawPtr - origSize, origSize);

        // Write the serialized tree + small payloads, then stream the blob.
        writeAll(fd, treeBuf, newRawPtr);
        streamBlob(fd, blobPath, newRawPtr + blobOff, blobSize);
        // Zero-pad the section's raw slack up to SizeOfRawData.
        const tail = newRawPtr + virtualSize;
        writeZeros(fd, newRawPtr + newRawSize - tail, tail);

        // Rename the original `.rsrc` -> `.rdata2` (avoid duplicate section names).
        const renameOff = secTableOff + rsrcSecIdx * SEC_HDR_SIZE;
        const renameName = Buffer.alloc(8);
        renameName.write('.rdata2', 0, 'latin1');
        writeAll(fd, renameName, renameOff);

        // Append the new `.rsrc` section header into the header slack.
        const hdr = Buffer.alloc(SEC_HDR_SIZE);
        hdr.write('.rsrc', 0, 'latin1');
        hdr.writeUInt32LE(virtualSize, 8);
        hdr.writeUInt32LE(newRva, 12);
        hdr.writeUInt32LE(newRawSize, 16);
        hdr.writeUInt32LE(newRawPtr, 20);
        hdr.writeUInt32LE(SCN_INITIALIZED_READ, 36);
        writeAll(fd, hdr, secTableOff + numSections * SEC_HDR_SIZE);

        // COFF: NumberOfSections += 1.
        const coffPatch = Buffer.alloc(2);
        coffPatch.writeUInt16LE(numSections + 1, 0);
        writeAll(fd, coffPatch, peOff + 4 + 2);

        // Optional header: SizeOfInitializedData, SizeOfImage, DataDirectory[2].
        const sizeOfImage = alignUp(newRva + virtualSize, sectionAlignment);
        const initData = opt.readUInt32LE(8) + newRawSize;
        const optPatch = Buffer.from(opt); // patch a copy, write the touched fields
        optPatch.writeUInt32LE(initData >>> 0, 8);
        optPatch.writeUInt32LE(sizeOfImage >>> 0, 56);
        optPatch.writeUInt32LE(newRva, 128); // Resource Table RVA
        optPatch.writeUInt32LE(virtualSize, 132); // Resource Table Size
        optPatch.writeUInt32LE(0, 64); // zero CheckSum before we recompute
        // Zero the Certificate Table directory (dir[4]): appending to the image
        // necessarily invalidated any Authenticode signature (its bytes are no
        // longer at the recorded offset), so clearing the pointer makes the file
        // read as honestly unsigned to SmartScreen/AV rather than "signature
        // present but invalid". Windows ignores a stale dir[4] at load time, so
        // this changes nothing at runtime.
        if (numRvaAndSizes > 4) {
            optPatch.writeUInt32LE(0, 144); // Certificate Table offset
            optPatch.writeUInt32LE(0, 148); // Certificate Table size
        }
        writeAll(fd, optPatch, optOff);

        // Flip the fuse before the checksum pass. Ordering discipline is about the
        // fuse *lookup* (findSentinelFuse ran before any mutation, so bad input
        // aborts byte-clean); the one-byte '0'->'1' write, however, must precede
        // the checksum computation or it invalidates the sum we just wrote. A
        // flipped fuse with no findable resource segfaults, but by here the
        // resource is already in place, so this is the last content byte to move.
        writeAll(fd, Buffer.from('1', 'latin1'), fuseOffset);

        // Recompute CheckSum over the now-final file (checksum field already 0).
        // The field excludes itself from the sum, so writing it back last is safe.
        const finalSize = newRawPtr + newRawSize;
        fs.fsyncSync(fd);
        const checksum = computeChecksum(fd, finalSize, optOff + 64);
        const ckBuf = Buffer.alloc(4);
        ckBuf.writeUInt32LE(checksum, 0);
        writeAll(fd, ckBuf, optOff + 64);
        fs.fsyncSync(fd);

        const blobOffset = newRawPtr + blobOff;
        return {
            format: 'pe',
            blobSize,
            blobOffset,
            detail:
                `new .rsrc RVA=0x${newRva.toString(16)} rawPtr=${newRawPtr} vsize=${virtualSize}, ` +
                `blob@0x${(newRva + blobOff).toString(16)} (file ${blobOffset}), ` +
                `${numSections} -> ${numSections + 1} sections, checksum=0x${checksum.toString(16)}`,
        };
    } finally {
        fs.closeSync(fd);
    }
}
