/**
 * Mach-O 64 SEA injector (mac-x64, mac-arm64).
 *
 * What node looks for at runtime (postject-api.h, __APPLE__ branch): it calls
 * getsectdata(segment, section) for segment "NODE_SEA", section "__NODE_SEA_BLOB"
 * (the build passes --macho-segment-name NODE_SEA; postject prepends "__" to the
 * resource name to form the section name). So we must add a real LC_SEGMENT_64
 * named NODE_SEA carrying one section __NODE_SEA_BLOB.
 *
 * Two hard constraints from build-cli-executables.sh:
 *   - mac binaries are NOT stripped (macOS strip corrupts node's __LINKEDIT).
 *   - the signature is removed before injection (`codesign --remove-signature`)
 *     and the binary is re-signed after (`codesign -s -`). For the ad-hoc
 *     signature to cover our segment — mandatory on Apple Silicon or the binary
 *     SIGSEGVs — __LINKEDIT must stay the LAST thing in the file, because
 *     codesign appends the signature to __LINKEDIT and grows it in place.
 *
 * Therefore the new segment is inserted in FILE order between the last real
 * segment (__DATA) and __LINKEDIT, and __LINKEDIT (a ~26MB tail) is slid up.
 * This is exactly what postject/LIEF produces; verified against a real
 * postject-injected node.
 *
 *   file:  [ __TEXT | __DATA_CONST | __DATA ][ NODE_SEA (blob) ][ __LINKEDIT ]
 *   vm:    ... __DATA end == NODE_SEA vmaddr, __LINKEDIT vmaddr bumped up ...
 *
 * Sliding __LINKEDIT means every load command that points INTO it (symbol/string
 * tables, dyld info, function starts, data-in-code, chained fixups, the old code
 * signature) has its file offset relocated by the same amount. Any existing
 * LC_CODE_SIGNATURE is dropped (postject does this; it is re-signed afterward).
 *
 * The load-command region grows, so we assert it still fits before the first
 * section's file data rather than overrunning code.
 *
 * Only the blob streams. The 26MB __LINKEDIT tail is moved chunked; the load
 * commands (a few KB) are the only thing fully buffered.
 */
import fs from 'node:fs';
import { Buffer } from 'node:buffer';
import { alignUp, findSentinelFuse, moveRange, readAt, streamBlob, writeAll, writeZeros } from './common.mjs';

const MH_MAGIC_64 = 0xfeedfacf;
const LC_SEGMENT_64 = 0x19;
const LC_SYMTAB = 0x02;
const LC_DYSYMTAB = 0x0b;
const LC_CODE_SIGNATURE = 0x1d;
// LC_REQ_DYLD is bit 31. `x | LC_REQ_DYLD` in JS is a SIGNED 32-bit op and
// yields a negative number, but readUInt32LE returns unsigned — so the combined
// command ids must be coerced back to unsigned with `>>> 0` or they never match
// what we read from the file. (This bug silently skipped dyld-info relocation
// until llvm-objdump caught the resulting overlap.)
const req = (x) => (x | 0x80000000) >>> 0;
const CPU_TYPE_ARM64 = 0x0100000c;
const VM_PROT_READ = 1;

// dyld_info_command offset fields (rebase/bind/weak/lazy/export), all in __LINKEDIT.
const LC_DYLD_INFO = 0x22;
const LC_DYLD_INFO_ONLY = req(0x22);

// linkedit_data_command: a single {dataoff,datasize} pair pointing into __LINKEDIT.
const LINKEDIT_DATA_CMDS = new Set([
    0x1e, // LC_SEGMENT_SPLIT_INFO
    0x26, // LC_FUNCTION_STARTS
    0x29, // LC_DATA_IN_CODE
    0x2b, // LC_DYLIB_CODE_SIGN_DRS
    0x2e, // LC_LINKER_OPTIMIZATION_HINT
    0x1d, // LC_CODE_SIGNATURE (relocated too, then removed)
    req(0x33), // LC_DYLD_EXPORTS_TRIE
    req(0x34), // LC_DYLD_CHAINED_FIXUPS
    0x36, // LC_ATOM_INFO
]);

function writeCString(buf, str, off, len) {
    buf.fill(0, off, off + len);
    buf.write(str, off, len, 'latin1');
}

export function injectMacho({ binaryPath, resourceName, blobPath, fuse }) {
    const origSize = fs.statSync(binaryPath).size;
    const blobSize = fs.statSync(blobPath).size;
    const fd = fs.openSync(binaryPath, 'r+');
    try {
        const hdr = readAt(fd, 32, 0);
        const magic = hdr.readUInt32LE(0);
        if (magic === 0xcafebabe || magic === 0xbebafeca) {
            throw new Error('fat/universal Mach-O not supported; CI builds thin per-arch binaries');
        }
        if (magic !== MH_MAGIC_64) throw new Error(`not a 64-bit little-endian Mach-O (magic 0x${magic.toString(16)})`);
        const cpuType = hdr.readInt32LE(4);
        const ncmds = hdr.readUInt32LE(16);
        const sizeofcmds = hdr.readUInt32LE(20);
        const pageSize = cpuType === CPU_TYPE_ARM64 ? 0x4000 : 0x1000;

        const lcRegion = readAt(fd, sizeofcmds, 32);

        // --- parse load commands --------------------------------------------
        const relocFields = []; // absolute file offsets of u32 fields to slide
        let linkedit = null; // { cmdOff, vmaddr, fileoff }
        let codeSigRange = null; // [start,end) within lcRegion, to excise
        let linkeditCmdStart = -1; // start of __LINKEDIT command within lcRegion
        let firstSectionOffset = Infinity;
        let lastMappedSegEnd = 0; // max (vmaddr+vmsize) over file-backed segments
        let off = 0;
        for (let i = 0; i < ncmds; i++) {
            const cmd = lcRegion.readUInt32LE(off);
            const cmdsize = lcRegion.readUInt32LE(off + 4);
            const push = (fieldOff) => {
                if (lcRegion.readUInt32LE(fieldOff) !== 0) relocFields.push(32 + fieldOff);
            };
            if (cmd === LC_SEGMENT_64) {
                const segname = lcRegion.toString('latin1', off + 8, off + 24).replace(/\0.*$/, '');
                const vmaddr = Number(lcRegion.readBigUInt64LE(off + 24));
                const vmsize = Number(lcRegion.readBigUInt64LE(off + 32));
                const fileoff = Number(lcRegion.readBigUInt64LE(off + 40));
                const filesize = Number(lcRegion.readBigUInt64LE(off + 48));
                const nsects = lcRegion.readUInt32LE(off + 64);
                if (segname === '__LINKEDIT') {
                    linkedit = { cmdOff: off, vmaddr, vmsize, fileoff, filesize };
                    linkeditCmdStart = off;
                } else if (filesize > 0) {
                    lastMappedSegEnd = Math.max(lastMappedSegEnd, vmaddr + vmsize);
                }
                let so = off + 72;
                for (let s = 0; s < nsects; s++) {
                    const secOffset = lcRegion.readUInt32LE(so + 48);
                    if (secOffset > 0) firstSectionOffset = Math.min(firstSectionOffset, secOffset);
                    so += 80;
                }
            } else if (cmd === LC_SYMTAB) {
                push(off + 8); // symoff
                push(off + 16); // stroff
            } else if (cmd === LC_DYSYMTAB) {
                for (const d of [32, 40, 48, 56, 64, 72]) push(off + d);
            } else if (cmd === LC_DYLD_INFO || cmd === LC_DYLD_INFO_ONLY) {
                for (const d of [8, 16, 24, 32, 40]) push(off + d);
            } else if (LINKEDIT_DATA_CMDS.has(cmd)) {
                push(off + 8); // dataoff
                if (cmd === LC_CODE_SIGNATURE) codeSigRange = [off, off + cmdsize];
            }
            off += cmdsize;
        }
        if (!linkedit) throw new Error('no __LINKEDIT segment');
        if (linkeditCmdStart < 0) throw new Error('could not locate __LINKEDIT command');
        if (linkedit.fileoff % pageSize !== 0) {
            throw new Error(`__LINKEDIT fileoff ${linkedit.fileoff} not page-aligned`);
        }
        if (linkedit.fileoff + linkedit.filesize !== origSize) {
            throw new Error('__LINKEDIT is not the last thing in the file; refusing to inject');
        }

        // Fail before mutating anything if the sentinel is missing/ambiguous.
        const fuseOffset = findSentinelFuse(fd, origSize, fuse);

        // --- compute the new layout -----------------------------------------
        const segFileOff = linkedit.fileoff; // blob goes where __LINKEDIT was
        const segVmAddr = linkedit.vmaddr; // ...taking its vm slot too
        const segVmSize = alignUp(blobSize, pageSize);
        const newLinkeditFileOff = alignUp(segFileOff + blobSize, pageSize);
        const newLinkeditVmAddr = alignUp(segVmAddr + segVmSize, pageSize);
        const fileSlide = newLinkeditFileOff - segFileOff;

        // sanity: NODE_SEA vm slot must not collide with a mapped segment.
        if (segVmAddr < lastMappedSegEnd) throw new Error('NODE_SEA vmaddr would overlap a mapped segment');

        // --- rebuild the load-command region --------------------------------
        // slide every __LINKEDIT-referencing offset
        for (const abs of relocFields) {
            const rel = abs - 32;
            lcRegion.writeUInt32LE(lcRegion.readUInt32LE(rel) + fileSlide, rel);
        }
        // repoint the __LINKEDIT segment itself
        lcRegion.writeBigUInt64LE(BigInt(newLinkeditVmAddr), linkedit.cmdOff + 24);
        lcRegion.writeBigUInt64LE(BigInt(newLinkeditFileOff), linkedit.cmdOff + 40);

        // build the NODE_SEA segment command (one section)
        const segCmd = Buffer.alloc(72 + 80);
        segCmd.writeUInt32LE(LC_SEGMENT_64, 0);
        segCmd.writeUInt32LE(72 + 80, 4);
        writeCString(segCmd, 'NODE_SEA', 8, 16);
        segCmd.writeBigUInt64LE(BigInt(segVmAddr), 24);
        segCmd.writeBigUInt64LE(BigInt(segVmSize), 32);
        segCmd.writeBigUInt64LE(BigInt(segFileOff), 40);
        segCmd.writeBigUInt64LE(BigInt(blobSize), 48);
        segCmd.writeInt32LE(VM_PROT_READ, 56); // maxprot
        segCmd.writeInt32LE(VM_PROT_READ, 60); // initprot
        segCmd.writeUInt32LE(1, 64); // nsects
        segCmd.writeUInt32LE(0, 68); // flags
        writeCString(segCmd, `__${resourceName}`, 72, 16); // sectname __NODE_SEA_BLOB
        writeCString(segCmd, 'NODE_SEA', 88, 16); // segname
        segCmd.writeBigUInt64LE(BigInt(segVmAddr), 104); // addr
        segCmd.writeBigUInt64LE(BigInt(blobSize), 112); // size
        segCmd.writeUInt32LE(segFileOff, 120); // offset
        segCmd.writeUInt32LE(0, 124); // align (2^0; getsectdata does not care)
        // reloff/nreloc/flags/reserved1..3 already zero

        // Rebuild the region command-by-command: insert NODE_SEA right before the
        // __LINKEDIT command (keeps segments in address order) and skip the
        // code-signature command's bytes.
        const rebuilt = [];
        for (let i = 0, p = 0; i < ncmds; i++) {
            const cmdsize = lcRegion.readUInt32LE(p + 4);
            if (p === linkeditCmdStart) rebuilt.push(segCmd);
            if (!(codeSigRange && p === codeSigRange[0])) {
                rebuilt.push(lcRegion.subarray(p, p + cmdsize));
            }
            p += cmdsize;
        }
        const newLc = Buffer.concat(rebuilt);
        const newNcmds = ncmds + 1 - (codeSigRange ? 1 : 0);
        const newSizeofcmds = newLc.length;
        if (32 + newSizeofcmds > firstSectionOffset) {
            throw new Error(
                `load commands (${32 + newSizeofcmds}) would overrun first section data (${firstSectionOffset}); no header slack`
            );
        }

        // --- perform the file surgery ---------------------------------------
        // 1) move __LINKEDIT up to its new offset (chunked; disjoint for large blobs)
        moveRange(fd, linkedit.fileoff, newLinkeditFileOff, linkedit.filesize);
        // 2) zero the alignment gap between the blob and the moved __LINKEDIT
        writeZeros(fd, newLinkeditFileOff - (segFileOff + blobSize), segFileOff + blobSize);
        // 3) stream the blob into the freed gap
        streamBlob(fd, blobPath, segFileOff, blobSize);
        // 4) truncate any stale bytes past the new EOF (none expected, but be exact)
        const newEof = newLinkeditFileOff + linkedit.filesize;
        fs.ftruncateSync(fd, newEof);
        // 5) write the rebuilt load commands + patched header
        writeAll(fd, newLc, 32);
        if (newSizeofcmds < sizeofcmds) writeZeros(fd, sizeofcmds - newSizeofcmds, 32 + newSizeofcmds);
        hdr.writeUInt32LE(newNcmds, 16);
        hdr.writeUInt32LE(newSizeofcmds, 20);
        writeAll(fd, hdr, 0);
        // 6) flip the fuse (offset is in __TEXT, unaffected by the surgery)
        writeAll(fd, Buffer.from('1', 'latin1'), fuseOffset);
        fs.fsyncSync(fd);

        return {
            format: 'macho',
            blobSize,
            blobOffset: segFileOff,
            detail:
                `NODE_SEA seg fileoff=${segFileOff} vmaddr=0x${segVmAddr.toString(16)} size=${blobSize}, ` +
                `__LINKEDIT ${linkedit.fileoff} -> ${newLinkeditFileOff} (slide ${fileSlide}), ` +
                `${ncmds} -> ${newNcmds} cmds${codeSigRange ? ', dropped LC_CODE_SIGNATURE' : ''}`,
        };
    } finally {
        fs.closeSync(fd);
    }
}
