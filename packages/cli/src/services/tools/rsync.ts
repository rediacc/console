/**
 * Installs a pinned MSYS2 rsync for Windows into rdc's tools directory (`rdc tools install rsync`).
 *
 * rsync has no native Windows build; the MSYS2 one runs on the msys-2.0.dll POSIX layer and imports a handful of msys-*.dll libraries. Every package archive in MSYS2_RSYNC_PIN (rsync plus each package whose DLL rsync.exe imports, directly or through another of them) is downloaded from the official MSYS2 repository into a private staging directory, its SHA-256 checked against the pin compiled into rdc, the zstd layer opened with node:zlib and the tar read in-process (tar.ts). Only `usr/bin/rsync.exe` and each package's `usr/bin/*.dll` are kept, under `usr/bin` so msys-2.0.dll finds its root two levels up, and the tree reaches `<toolsDir>/msys2-rsync/<key>/` by one rename. The key names the rsync version plus a digest of the whole pin, so moving any one DLL pin installs a fresh tree beside the old one. Any failure removes the staging directory.
 */

import { createHash } from 'node:crypto';
import { existsSync, promises as fs } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { zstdDecompressSync } from 'node:zlib';
import { getStateDir } from '@rediacc/shared/paths';
import { t } from '../../i18n/index.js';
import { computeSha256, downloadFile } from '../update/updater.js';
import { MSYS2_REPO, MSYS2_RSYNC_PIN } from './pins.js';
import { readTarEntries, TarError } from './tar.js';

export interface Msys2Package {
  readonly name: string;
  readonly version: string;
  readonly sha256: string;
}

export interface Msys2RsyncPin {
  readonly packages: readonly Msys2Package[];
}

/** The files without which the installed tree cannot run rsync. */
const RSYNC_EXE = 'rsync.exe';
const RUNTIME_DLL = 'msys-2.0.dll';
/** Directories the MSYS2 runtime expects beside `usr` in its root; the extracted tree has none, and rsync then exits non-zero after printing its banner. */
const MSYS2_ROOT_DIRS = ['etc', 'tmp', 'dev'] as const;
const SAFE_NAME = /^[A-Za-z0-9][A-Za-z0-9._+-]*$/;

/** The archive URL of one pinned package, in the repository's `<name>-<version>-x86_64.pkg.tar.zst` naming. */
export function msys2PackageUrl(pkg: Msys2Package, repo: string = MSYS2_REPO): string {
  return `${repo}/${pkg.name}-${pkg.version}-x86_64.pkg.tar.zst`;
}

function rsyncPackage(pin: Msys2RsyncPin): Msys2Package {
  const rsync = pin.packages.find((p) => p.name === 'rsync');
  if (!rsync) throw new Error('the MSYS2 rsync pin names no rsync package');
  return rsync;
}

/** `<rsync version>-<first 12 hex of sha256 over every package digest>`: one directory per exact pin. */
export function rsyncPinKey(pin: Msys2RsyncPin = MSYS2_RSYNC_PIN): string {
  const rsync = rsyncPackage(pin);
  const digest = createHash('sha256')
    .update(pin.packages.map((p) => `${p.name}=${p.version}:${p.sha256}`).join('\n'))
    .digest('hex');
  return `${rsync.version}-${digest.slice(0, 12)}`;
}

function defaultToolsDir(): string {
  return join(getStateDir(), 'tools');
}

/** Where the rdc-managed rsync tree of `pin` lives (whether or not it is installed). */
export function rsyncInstallDir(options: { pin?: Msys2RsyncPin; toolsDir?: string } = {}): string {
  return join(options.toolsDir ?? defaultToolsDir(), 'msys2-rsync', rsyncPinKey(options.pin));
}

/** The rsync.exe of the pinned tree (whether or not it is installed). */
function rsyncInstallPath(options: { pin?: Msys2RsyncPin; toolsDir?: string } = {}): string {
  return join(rsyncInstallDir(options), 'usr', 'bin', RSYNC_EXE);
}

/** Create the MSYS2 root directories (etc, tmp, dev) under an installed tree; idempotent, so a tree installed before they were created is repaired too. */
async function ensureMsys2RootDirs(root: string): Promise<void> {
  for (const dir of MSYS2_ROOT_DIRS) await fs.mkdir(join(root, dir), { recursive: true });
}

/** The pinned rdc-managed rsync.exe when it and its runtime DLL are on disk, else null. */
export function findInstalledRsync(
  options: { pin?: Msys2RsyncPin; toolsDir?: string } = {}
): string | null {
  const exe = rsyncInstallPath(options);
  const runtime = join(rsyncInstallDir(options), 'usr', 'bin', RUNTIME_DLL);
  return existsSync(exe) && existsSync(runtime) ? exe : null;
}

export interface RsyncInstallDeps {
  pin?: Msys2RsyncPin;
  repo?: string;
  toolsDir?: string;
  platform?: NodeJS.Platform;
  download?: (url: string, dest: string) => Promise<void>;
  onDownloadStart?: (info: { name: string; version: string; url: string }) => void;
}

export interface RsyncInstallResult {
  tool: 'rsync';
  version: string;
  path: string;
  alreadyInstalled: boolean;
  /** The file names placed under usr/bin, sorted. */
  files: string[];
}

/** The files one package contributes: rsync.exe from rsync, every usr/bin DLL from each package. */
function wanted(pkg: Msys2Package, entryName: string): string | null {
  const parts = entryName.split('/');
  if (parts.length !== 3 || parts[0] !== 'usr' || parts[1] !== 'bin') return null;
  const file = parts[2] ?? '';
  if (!SAFE_NAME.test(file)) return null;
  if (file.toLowerCase().endsWith('.dll')) return file;
  if (pkg.name === 'rsync' && file === RSYNC_EXE) return file;
  return null;
}

/** The kept files of one verified archive, or an i18n error when it is unusable. */
function extractPackage(pkg: Msys2Package, archive: Buffer): Map<string, Buffer> {
  let tar: Buffer;
  try {
    tar = zstdDecompressSync(archive);
  } catch (err) {
    throw new Error(
      t('commands.tools.errors.badArchive', {
        reason: `${pkg.name}: zstd: ${(err as Error).message}`,
      })
    );
  }
  const kept = new Map<string, Buffer>();
  try {
    for (const entry of readTarEntries(tar)) {
      const file = wanted(pkg, entry.name);
      if (file) kept.set(file, entry.data);
    }
  } catch (err) {
    if (err instanceof TarError) {
      throw new Error(
        t('commands.tools.errors.badArchive', { reason: `${pkg.name}: ${err.message}` })
      );
    }
    throw err;
  }
  return kept;
}

const byName = (a: string, b: string): number => a.localeCompare(b);

/** Download one package into `staging`, refuse it unless its SHA-256 is the pinned one, and return its kept files. */
async function fetchPackage(
  pkg: Msys2Package,
  staging: string,
  repo: string,
  download: (url: string, dest: string) => Promise<void>,
  onDownloadStart: RsyncInstallDeps['onDownloadStart']
): Promise<Map<string, Buffer>> {
  const url = msys2PackageUrl(pkg, repo);
  if (!url.startsWith('https://')) {
    throw new Error(t('commands.tools.errors.insecureUrl', { url }));
  }
  const archivePath = join(staging, basename(url));
  onDownloadStart?.({ name: pkg.name, version: pkg.version, url });
  await download(url, archivePath);
  const actual = await computeSha256(archivePath);
  if (actual !== pkg.sha256.toLowerCase()) {
    throw new Error(
      t('commands.tools.errors.checksumMismatch', { url, expected: pkg.sha256, actual })
    );
  }
  const kept = extractPackage(pkg, await fs.readFile(archivePath));
  await fs.rm(archivePath, { force: true });
  return kept;
}

/** Write `files` under `<staging>/root/usr/bin` and move that root to `finalDir` in one rename. */
async function placeTree(
  files: Map<string, Buffer>,
  staging: string,
  finalDir: string
): Promise<void> {
  for (const required of [RSYNC_EXE, RUNTIME_DLL]) {
    if (!files.has(required)) {
      throw new Error(
        t('commands.tools.errors.badArchive', { reason: `no usr/bin/${required} in the pin` })
      );
    }
  }
  const binDir = join(staging, 'root', 'usr', 'bin');
  await fs.mkdir(binDir, { recursive: true });
  for (const [file, data] of files) {
    await fs.writeFile(join(binDir, file), data, { mode: 0o755 });
  }
  await ensureMsys2RootDirs(join(staging, 'root'));
  await fs.mkdir(dirname(finalDir), { recursive: true });
  await fs.rm(finalDir, { recursive: true, force: true });
  await fs.rename(join(staging, 'root'), finalDir);
}

/** The injected dependencies with every default filled in. */
function resolveDeps(deps: RsyncInstallDeps) {
  return {
    platform: deps.platform ?? process.platform,
    pin: deps.pin ?? MSYS2_RSYNC_PIN,
    repo: deps.repo ?? MSYS2_REPO,
    toolsDir: deps.toolsDir ?? defaultToolsDir(),
    download: deps.download ?? downloadFile,
  };
}

/**
 * Install the pinned MSYS2 rsync on Windows. Idempotent: a present tree of this exact pin is left alone unless `force`. Anywhere but win32 it throws an i18n error naming the system package manager, and touches nothing.
 */
export async function installRsync(
  options: { force?: boolean } = {},
  deps: RsyncInstallDeps = {}
): Promise<RsyncInstallResult> {
  const { platform, pin, repo, toolsDir, download } = resolveDeps(deps);
  if (platform !== 'win32') {
    throw new Error(t('commands.tools.errors.rsyncFromSystem', { platform }));
  }
  const version = rsyncPackage(pin).version;
  const finalDir = rsyncInstallDir({ pin, toolsDir });
  const finalPath = join(finalDir, 'usr', 'bin', RSYNC_EXE);

  if (!options.force && findInstalledRsync({ pin, toolsDir })) {
    await ensureMsys2RootDirs(finalDir);
    const files = (await fs.readdir(join(finalDir, 'usr', 'bin'))).sort(byName);
    return { tool: 'rsync', version, path: finalPath, alreadyInstalled: true, files };
  }

  await fs.mkdir(toolsDir, { recursive: true, mode: 0o700 });
  // Staging sits under the tools root so the final rename never crosses a filesystem.
  const staging = await fs.mkdtemp(join(toolsDir, '.staging-'));
  try {
    const files = new Map<string, Buffer>();
    for (const pkg of pin.packages) {
      const kept = await fetchPackage(pkg, staging, repo, download, deps.onDownloadStart);
      for (const [file, data] of kept) files.set(file, data);
    }
    await placeTree(files, staging, finalDir);
    const names = [...files.keys()].sort(byName);
    return { tool: 'rsync', version, path: finalPath, alreadyInstalled: false, files: names };
  } finally {
    await fs.rm(staging, { recursive: true, force: true });
  }
}

export interface RsyncStatus {
  /** The pinned rsync version. */
  pinned: string;
  installed: boolean;
  /** The installed rsync.exe, or null when the pinned tree is absent. */
  path: string | null;
}

/** The pinned MSYS2 rsync version and whether (and where) its tree is installed, for `rdc tools list`. */
export function rsyncStatus(options: { pin?: Msys2RsyncPin; toolsDir?: string } = {}): RsyncStatus {
  const path = findInstalledRsync(options);
  return {
    pinned: rsyncPackage(options.pin ?? MSYS2_RSYNC_PIN).version,
    installed: path !== null,
    path,
  };
}
