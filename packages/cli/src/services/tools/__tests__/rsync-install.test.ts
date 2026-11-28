import { createHash } from 'node:crypto';
import { mkdtemp, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { zstdCompressSync } from 'node:zlib';
import { afterEach, describe, expect, it } from 'vitest';
import { MSYS2_REPO, MSYS2_RSYNC_PIN } from '../pins.js';
import {
  findInstalledRsync,
  installRsync,
  MSYS2_FSTAB,
  MSYS2_NSSWITCH,
  type Msys2RsyncPin,
  msys2PackageUrl,
  rsyncInstallDir,
  rsyncPinKey,
  rsyncStatus,
} from '../rsync.js';
import { readTarEntries, TarError } from '../tar.js';
import { buildTar, paxPathRecord } from './tar-fixture.js';

const dirs: string[] = [];
afterEach(async () => {
  await Promise.all(dirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
});

async function tempDir(): Promise<string> {
  const d = await mkdtemp(join(tmpdir(), 'rdc-rsync-'));
  dirs.push(d);
  return d;
}

const sha = (buf: Buffer): string => createHash('sha256').update(buf).digest('hex');

const RSYNC_EXE = Buffer.from('MZ fake rsync.exe');
const RUNTIME = Buffer.from('MZ fake msys-2.0.dll');
const ZSTD_DLL = Buffer.from('MZ fake msys-zstd-1.dll');

/** A .pkg.tar.zst the way MSYS2 lays one out: metadata at the root, files under usr/. */
function pkgArchive(files: Record<string, Buffer>): Buffer {
  return zstdCompressSync(
    buildTar([
      { name: '.PKGINFO', data: Buffer.from('pkgname = x\n') },
      { name: 'usr/', type: '5' },
      { name: 'usr/bin/', type: '5' },
      ...Object.entries(files).map(([name, data]) => ({ name, data })),
    ])
  );
}

/** Three packages standing in for the real set, with their archives and a pin whose sha256 values match. */
function fixture() {
  const archives = {
    rsync: pkgArchive({
      'usr/bin/rsync.exe': RSYNC_EXE,
      'usr/bin/rsync-ssl': Buffer.from('#!/bin/sh'),
      'usr/share/man/man1/rsync.1.gz': Buffer.from('man'),
    }),
    'msys2-runtime': pkgArchive({
      'usr/bin/msys-2.0.dll': RUNTIME,
      'usr/bin/cygpath.exe': Buffer.from('MZ cygpath'),
    }),
    libzstd: pkgArchive({ 'usr/bin/msys-zstd-1.dll': ZSTD_DLL }),
  };
  const pin: Msys2RsyncPin = {
    packages: [
      { name: 'rsync', version: '3.5.2-2', sha256: sha(archives.rsync) },
      { name: 'msys2-runtime', version: '3.6.12-1', sha256: sha(archives['msys2-runtime']) },
      { name: 'libzstd', version: '1.5.7-1', sha256: sha(archives.libzstd) },
    ],
  };
  const byUrl = new Map(
    pin.packages.map((p) => [msys2PackageUrl(p), archives[p.name as keyof typeof archives]])
  );
  const fetched: string[] = [];
  const download = async (url: string, dest: string) => {
    fetched.push(url);
    const bytes = byUrl.get(url);
    if (!bytes) throw new Error(`unexpected URL ${url}`);
    await writeFile(dest, bytes);
  };
  return { pin, archives, download, fetched };
}

async function tree(root: string): Promise<string[]> {
  try {
    return (await readdir(root, { recursive: true })).map(String).sort();
  } catch {
    return [];
  }
}

describe('readTarEntries', () => {
  it('returns regular files only, honouring a pax path record', () => {
    const tar = buildTar([
      { name: 'usr/', type: '5' },
      { name: 'usr/bin/a.dll', data: Buffer.from('A') },
      { name: 'usr/bin/link', type: '2', linkname: '/etc/passwd' },
      { name: 'PaxHeader', type: 'x', data: paxPathRecord('usr/bin/long-name.dll') },
      { name: 'truncated-nam', data: Buffer.from('B') },
    ]);
    expect(readTarEntries(tar).map((e) => [e.name, e.data.toString()])).toEqual([
      ['usr/bin/a.dll', 'A'],
      ['usr/bin/long-name.dll', 'B'],
    ]);
  });

  it('refuses a header whose checksum does not match', () => {
    const tar = buildTar([{ name: 'usr/bin/a.dll', data: Buffer.from('A') }]);
    tar[0] = 'x'.charCodeAt(0);
    expect(() => readTarEntries(tar)).toThrow(TarError);
  });

  it('refuses an entry cut short', () => {
    const tar = buildTar([{ name: 'usr/bin/a.dll', data: Buffer.alloc(2000, 1) }]);
    expect(() => readTarEntries(tar.subarray(0, 1024))).toThrow(/truncated/);
  });
});

describe('the generated MSYS2 rsync pin', () => {
  it('names rsync, the MSYS2 runtime and only https archives with a 64-hex sha256', () => {
    const names = MSYS2_RSYNC_PIN.packages.map((p) => p.name);
    expect(names).toContain('rsync');
    expect(names).toContain('msys2-runtime');
    for (const p of MSYS2_RSYNC_PIN.packages) {
      expect(p.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(msys2PackageUrl(p)).toBe(`${MSYS2_REPO}/${p.name}-${p.version}-x86_64.pkg.tar.zst`);
      expect(msys2PackageUrl(p).startsWith('https://')).toBe(true);
    }
  });
});

describe('installRsync', () => {
  it('verifies each archive, keeps rsync.exe plus every usr/bin DLL, and places them under msys2-rsync/<key>/usr/bin', async () => {
    const toolsDir = await tempDir();
    const { pin, download, fetched } = fixture();
    const result = await installRsync({}, { pin, toolsDir, platform: 'win32', download });

    const dir = rsyncInstallDir({ pin, toolsDir });
    expect(dir).toBe(join(toolsDir, 'msys2-rsync', rsyncPinKey(pin)));
    expect(rsyncPinKey(pin)).toMatch(/^3\.5\.2-2-[0-9a-f]{12}$/);
    expect(result).toMatchObject({ tool: 'rsync', version: '3.5.2-2', alreadyInstalled: false });
    expect(result.path).toBe(join(dir, 'usr', 'bin', 'rsync.exe'));
    expect(result.files).toEqual(['msys-2.0.dll', 'msys-zstd-1.dll', 'rsync.exe']);
    expect(await readFile(result.path)).toEqual(RSYNC_EXE);
    expect(await readFile(join(dir, 'usr', 'bin', 'msys-2.0.dll'))).toEqual(RUNTIME);
    expect(fetched).toEqual(pin.packages.map((p) => msys2PackageUrl(p)));
    // No staging directory, no archive, no man page, no other exe.
    const key = rsyncPinKey(pin);
    expect(await tree(toolsDir)).toEqual(
      [
        'msys2-rsync',
        `msys2-rsync/${key}`,
        `msys2-rsync/${key}/dev`,
        `msys2-rsync/${key}/etc`,
        `msys2-rsync/${key}/etc/fstab`,
        `msys2-rsync/${key}/etc/nsswitch.conf`,
        `msys2-rsync/${key}/tmp`,
        `msys2-rsync/${key}/usr`,
        `msys2-rsync/${key}/usr/bin`,
        `msys2-rsync/${key}/usr/bin/msys-2.0.dll`,
        `msys2-rsync/${key}/usr/bin/msys-zstd-1.dll`,
        `msys2-rsync/${key}/usr/bin/rsync.exe`,
      ].sort((a, b) => a.localeCompare(b))
    );
    expect(findInstalledRsync({ pin, toolsDir })).toBe(result.path);
  });

  it('refuses a wrong sha256, deletes the download and places nothing', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    const tampered: Msys2RsyncPin = {
      packages: pin.packages.map((p) =>
        p.name === 'libzstd' ? { ...p, sha256: 'a'.repeat(64) } : p
      ),
    };
    await expect(
      installRsync({}, { pin: tampered, toolsDir, platform: 'win32', download })
    ).rejects.toThrow(/Checksum mismatch for .*libzstd-1\.5\.7-1-x86_64\.pkg\.tar\.zst/);
    expect(await tree(toolsDir)).toEqual([]);
    expect(findInstalledRsync({ pin: tampered, toolsDir })).toBeNull();
  });

  it('refuses a pin whose archives carry no rsync.exe', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    // The rsync package's archive holds only a man page; its pinned sha256 matches it.
    const empty = pkgArchive({ 'usr/share/man/man1/rsync.1.gz': Buffer.from('man') });
    const pinned: Msys2RsyncPin = {
      packages: pin.packages.map((p) => (p.name === 'rsync' ? { ...p, sha256: sha(empty) } : p)),
    };
    const serve = async (url: string, dest: string) => {
      if (url.includes('/rsync-')) await writeFile(dest, empty);
      else await download(url, dest);
    };
    await expect(
      installRsync({}, { pin: pinned, toolsDir, platform: 'win32', download: serve })
    ).rejects.toThrow(/no usr\/bin\/rsync\.exe/);
    expect(await tree(toolsDir)).toEqual([]);
  });

  it('leaves a present tree alone unless forced', async () => {
    const toolsDir = await tempDir();
    const { pin, download, fetched } = fixture();
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    const again = await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(again.alreadyInstalled).toBe(true);
    expect(fetched).toHaveLength(pin.packages.length);
    const forced = await installRsync(
      { force: true },
      { pin, toolsDir, platform: 'win32', download }
    );
    expect(forced.alreadyInstalled).toBe(false);
    expect(fetched).toHaveLength(pin.packages.length * 2);
  });

  it('creates the MSYS2 root directories etc, tmp and dev beside usr, and repairs a tree installed without them', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    const dir = rsyncInstallDir({ pin, toolsDir });
    for (const d of ['etc', 'tmp', 'dev'])
      expect((await stat(join(dir, d))).isDirectory()).toBe(true);
    await rm(join(dir, 'tmp'), { recursive: true });
    const again = await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(again.alreadyInstalled).toBe(true);
    expect((await stat(join(dir, 'tmp'))).isDirectory()).toBe(true);
  });

  it('writes etc/fstab with the cygdrive-prefix-/ line and nsswitch.conf at install', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    const dir = rsyncInstallDir({ pin, toolsDir });
    expect(await readFile(join(dir, 'etc', 'fstab'), 'utf8')).toBe(
      'none / cygdrive binary,posix=0,noacl,user 0 0\n'
    );
    expect(await readFile(join(dir, 'etc', 'nsswitch.conf'), 'utf8')).toBe(MSYS2_NSSWITCH);
  });

  it('adds fstab to an existing tree without one and keeps an edited one', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    const fstab = join(rsyncInstallDir({ pin, toolsDir }), 'etc', 'fstab');
    await rm(fstab);
    const again = await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(again.alreadyInstalled).toBe(true);
    expect(await readFile(fstab, 'utf8')).toBe(MSYS2_FSTAB);
    await writeFile(fstab, 'custom\n');
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(await readFile(fstab, 'utf8')).toBe('custom\n');
  });

  it('adds nsswitch.conf to an existing tree without one and keeps an edited one', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    const nsswitch = join(rsyncInstallDir({ pin, toolsDir }), 'etc', 'nsswitch.conf');
    await rm(nsswitch);
    const again = await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(again.alreadyInstalled).toBe(true);
    expect(await readFile(nsswitch, 'utf8')).toBe(MSYS2_NSSWITCH);
    await writeFile(nsswitch, 'custom\n');
    await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(await readFile(nsswitch, 'utf8')).toBe('custom\n');
  });

  it('refuses anywhere but Windows, naming the system package manager, and downloads nothing', async () => {
    const toolsDir = await tempDir();
    const { pin, download, fetched } = fixture();
    for (const platform of ['linux', 'darwin'] as const) {
      await expect(installRsync({}, { pin, toolsDir, platform, download })).rejects.toThrow(
        /only on Windows.*package manager/
      );
    }
    expect(fetched).toEqual([]);
    expect(await tree(toolsDir)).toEqual([]);
  });
});

describe('rsyncStatus', () => {
  it('reports the pinned version, and the path once the tree is installed', async () => {
    const toolsDir = await tempDir();
    const { pin, download } = fixture();
    expect(rsyncStatus({ pin, toolsDir })).toEqual({
      pinned: '3.5.2-2',
      installed: false,
      path: null,
    });
    const result = await installRsync({}, { pin, toolsDir, platform: 'win32', download });
    expect(rsyncStatus({ pin, toolsDir })).toEqual({
      pinned: '3.5.2-2',
      installed: true,
      path: result.path,
    });
  });
});
