#!/usr/bin/env node
/**
 * Post-injection integrity gate. Re-parses the injected binary from scratch,
 * locates the embedded NODE_SEA_BLOB by the SAME path node's runtime uses for
 * each format, streams its bytes back out and SHA256-compares them against the
 * source blob. Also confirms the sentinel fuse reads `:1`.
 *
 * Why this exists as a separate check (#525): the build's runtime smoke test can
 * only run the binary on its NATIVE platform, and even there `--version`/doctor
 * exercise the SEA *main script* but not the asset bytes — a blob whose main is
 * intact but whose asset payload is corrupt or truncated passes them. This gate
 * runs on EVERY platform (it only parses the container, never executes it) and
 * compares the entire embedded blob, so a bad injection cannot ship green.
 *
 * Streams the embedded blob in fixed-size chunks, so it holds bounded memory on
 * the ~561MB blob just like the injector does.
 *
 *   node verify.mjs <binary> <blob> --sentinel-fuse <fuse>
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';
import { detectFormat } from './index.mjs';

const CHUNK = 8 * 1024 * 1024;

function fail(msg) {
    console.error(`sea-inject verify: FAIL: ${msg}`);
    process.exit(1);
}

function readAt(fd, length, position) {
    const buf = Buffer.alloc(length);
    let done = 0;
    while (done < length) {
        const got = fs.readSync(fd, buf, done, length - done, position + done);
        if (got <= 0) throw new Error(`short read at ${position + done}`);
        done += got;
    }
    return buf;
}

/** Locate [offset,size) of the NODE_SEA_BLOB payload inside an ELF64. */
function findElf(fd, resourceName) {
    const eh = readAt(fd, 64, 0);
    const phoff = Number(eh.readBigUInt64LE(0x20));
    const phentsize = eh.readUInt16LE(0x36);
    const phnum = eh.readUInt16LE(0x38);
    const phdrs = readAt(fd, phentsize * phnum, phoff);
    const want = Buffer.from(`${resourceName}\0`, 'latin1');
    for (let i = 0; i < phnum; i++) {
        const e = phdrs.subarray(i * phentsize);
        if (e.readUInt32LE(0) !== 4) continue; // PT_NOTE
        const off = Number(e.readBigUInt64LE(0x08));
        const size = Number(e.readBigUInt64LE(0x20));
        const notes = readAt(fd, size, off);
        let p = 0;
        while (p + 12 <= notes.length) {
            const namesz = notes.readUInt32LE(p);
            const descsz = notes.readUInt32LE(p + 4);
            const name = notes.subarray(p + 12, p + 12 + namesz);
            const descOff = p + 12 + (Math.ceil(namesz / 4) * 4);
            if (name.equals(want)) return { offset: off + descOff, size: descsz };
            p = descOff + Math.ceil(descsz / 4) * 4;
        }
    }
    return null;
}

/** Locate the __NODE_SEA_BLOB section payload inside a Mach-O 64. */
function findMacho(fd, resourceName) {
    const hdr = readAt(fd, 32, 0);
    const ncmds = hdr.readUInt32LE(16);
    const lc = readAt(fd, hdr.readUInt32LE(20), 32);
    const wantSect = `__${resourceName}`;
    let off = 0;
    for (let i = 0; i < ncmds; i++) {
        const cmd = lc.readUInt32LE(off);
        const cmdsize = lc.readUInt32LE(off + 4);
        if (cmd === 0x19) {
            const seg = lc.toString('latin1', off + 8, off + 24).replace(/\0.*/, '');
            const nsects = lc.readUInt32LE(off + 64);
            let so = off + 72;
            for (let s = 0; s < nsects; s++) {
                const sect = lc.toString('latin1', so, so + 16).replace(/\0.*/, '');
                if (seg === 'NODE_SEA' && sect === wantSect) {
                    return { offset: lc.readUInt32LE(so + 48), size: Number(lc.readBigUInt64LE(so + 40)) };
                }
                so += 80;
            }
        }
        off += cmdsize;
    }
    return null;
}

/** Locate the RT_RCDATA/<resourceName> resource payload inside a PE32+. */
function findPe(fd, resourceName) {
    const dos = readAt(fd, 64, 0);
    const peOff = dos.readUInt32LE(0x3c);
    const coff = readAt(fd, 20, peOff + 4);
    const numSections = coff.readUInt16LE(2);
    const optSize = coff.readUInt16LE(16);
    const optOff = peOff + 24;
    const opt = readAt(fd, optSize, optOff);
    const resRva = opt.readUInt32LE(128);
    const secTable = readAt(fd, numSections * 40, optOff + optSize);
    let base = -1;
    let secRva = 0;
    for (let i = 0; i < numSections; i++) {
        const o = i * 40;
        const va = secTable.readUInt32LE(o + 12);
        const vs = secTable.readUInt32LE(o + 8);
        if (resRva >= va && resRva < va + vs) {
            base = secTable.readUInt32LE(o + 20);
            secRva = va;
        }
    }
    if (base < 0) return null;
    // read the whole resource section
    let secRaw = null;
    for (let i = 0; i < numSections; i++) {
        const o = i * 40;
        const va = secTable.readUInt32LE(o + 12);
        if (va === secRva) secRaw = readAt(fd, secTable.readUInt32LE(o + 16), secTable.readUInt32LE(o + 20));
    }
    // Tree offsets in .rsrc are relative to the section base; index secRaw with
    // `secRel`, and translate a data-entry RVA to a FILE offset with `fileOff`.
    const secRel = (rva) => rva - secRva;
    const fileOff = (rva) => base + (rva - secRva);
    let hit = null;
    const walk = (dirRva, path) => {
        const o = secRel(dirRva);
        const named = secRaw.readUInt16LE(o + 12);
        const ids = secRaw.readUInt16LE(o + 14);
        for (let i = 0; i < named + ids; i++) {
            const e = o + 16 + i * 8;
            const nameField = secRaw.readUInt32LE(e);
            const offField = secRaw.readUInt32LE(e + 4);
            let k;
            if (nameField & 0x80000000) {
                const so = nameField & 0x7fffffff; // string offset, section-relative
                const len = secRaw.readUInt16LE(so);
                k = secRaw.toString('utf16le', so + 2, so + 2 + len * 2);
            } else {
                k = nameField;
            }
            const childPath = [...path, k];
            if (offField & 0x80000000) {
                walk(secRva + (offField & 0x7fffffff), childPath);
            } else if (childPath.includes(10) && childPath.includes(resourceName)) {
                // Type RT_RCDATA(10) -> name resourceName -> lang leaf.
                const deo = offField & 0x7fffffff; // data-entry offset, section-relative
                hit = { offset: fileOff(secRaw.readUInt32LE(deo)), size: secRaw.readUInt32LE(deo + 4) };
            }
        }
    };
    walk(resRva, []);
    return hit;
}

function streamSha256(fd, offset, size) {
    const h = crypto.createHash('sha256');
    const buf = Buffer.allocUnsafe(CHUNK);
    let done = 0;
    while (done < size) {
        const want = Math.min(CHUNK, size - done);
        let got = 0;
        while (got < want) {
            const r = fs.readSync(fd, buf, got, want - got, offset + done + got);
            if (r <= 0) throw new Error(`short read at ${offset + done + got}`);
            got += r;
        }
        h.update(buf.subarray(0, want));
        done += want;
    }
    return h.digest('hex');
}

function fileSha256(path) {
    const fd = fs.openSync(path, 'r');
    try {
        return streamSha256(fd, 0, fs.statSync(path).size);
    } finally {
        fs.closeSync(fd);
    }
}

function main() {
    const argv = process.argv.slice(2);
    const positional = [];
    let fuse = null;
    for (let i = 0; i < argv.length; i++) {
        if (argv[i] === '--sentinel-fuse') fuse = argv[++i];
        else positional.push(argv[i]);
    }
    const [binaryPath, blobPath] = positional;
    if (!binaryPath || !blobPath || !fuse) {
        console.error('usage: verify.mjs <binary> <blob> --sentinel-fuse <fuse>');
        process.exit(2);
    }
    const resourceName = 'NODE_SEA_BLOB';
    const fmt = detectFormat(binaryPath);
    const fd = fs.openSync(binaryPath, 'r');
    try {
        const finder = fmt === 'elf' ? findElf : fmt === 'macho' ? findMacho : findPe;
        const loc = finder(fd, resourceName);
        if (!loc) fail(`${fmt}: could not locate embedded ${resourceName}`);

        const blobSize = fs.statSync(blobPath).size;
        if (loc.size !== blobSize) fail(`embedded size ${loc.size} != source blob ${blobSize}`);

        const embeddedHash = streamSha256(fd, loc.offset, loc.size);
        const sourceHash = fileSha256(blobPath);
        if (embeddedHash !== sourceHash) fail(`sha256 mismatch: embedded ${embeddedHash} != source ${sourceHash}`);

        // Fuse must read :1 (exactly one flipped sentinel, none unflipped).
        const size = fs.statSync(binaryPath).size;
        const on = Buffer.from(`${fuse}:1`, 'latin1');
        const off = Buffer.from(`${fuse}:0`, 'latin1');
        const overlap = on.length - 1;
        const buf = Buffer.alloc(CHUNK + overlap);
        let onCount = 0;
        let offCount = 0;
        let pos = 0;
        while (pos < size) {
            const got = fs.readSync(fd, buf, 0, Math.min(buf.length, size - pos), pos);
            if (got <= 0) break;
            const w = buf.subarray(0, got);
            for (let f = 0; (f = w.indexOf(on, f)) >= 0; f++) onCount++;
            for (let f = 0; (f = w.indexOf(off, f)) >= 0; f++) offCount++;
            pos += CHUNK;
        }
        if (onCount !== 1 || offCount !== 0) fail(`sentinel fuse state wrong: ${fuse}:1 x${onCount}, ${fuse}:0 x${offCount}`);

        console.log(
            `sea-inject verify: OK ${fmt} — embedded ${resourceName} ${loc.size} bytes ` +
                `@${loc.offset}, sha256=${embeddedHash} matches source, fuse=:1`
        );
    } finally {
        fs.closeSync(fd);
    }
}

main();
