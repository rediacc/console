/**
 * Local filesystem walking + source expansion for SFTP-fallback uploads.
 */

import * as fsPromises from 'node:fs/promises';
import * as path from 'node:path';
import { isExcluded } from './sftp-patterns.js';

export interface SftpUploadSource {
  /** Absolute path to a local file or directory. */
  path: string;
  /** True if path is a file (not a directory). */
  isFile: boolean;
}

export interface SftpFileEntry {
  remoteRelative: string;
  absolutePath: string;
  size: number;
  /** Octal mode bits (rwxrwxrwx) — preserved on the remote via chmod. */
  mode: number;
}

export interface SftpSymlinkEntry {
  remoteRelative: string;
  /** Target as recorded by readlink — may be relative or absolute. */
  target: string;
}

export interface ExpandedSources {
  files: SftpFileEntry[];
  symlinks: SftpSymlinkEntry[];
}

interface WalkedFile {
  relativePath: string;
  absolutePath: string;
  size: number;
  mode: number;
}

interface WalkedSymlink {
  relativePath: string;
  target: string;
}

interface WalkResult {
  files: WalkedFile[];
  symlinks: WalkedSymlink[];
}

async function readSymlink(absolutePath: string, relativePath: string): Promise<WalkedSymlink> {
  const target = await fsPromises.readlink(absolutePath);
  return { relativePath, target };
}

async function readFileEntry(absolutePath: string, relativePath: string): Promise<WalkedFile> {
  const stat = await fsPromises.stat(absolutePath);
  return { relativePath, absolutePath, size: stat.size, mode: stat.mode & 0o777 };
}

interface DirEntryCtx {
  basePath: string;
  exclude: string[];
  result: WalkResult;
}

async function visitEntry(
  absolutePath: string,
  isSym: boolean,
  isDir: boolean,
  isFile: boolean,
  ctx: DirEntryCtx
): Promise<void> {
  const relativePath = path.relative(ctx.basePath, absolutePath).replaceAll('\\', '/');
  if (isSym) {
    if (isExcluded(relativePath, false, ctx.exclude)) return;
    ctx.result.symlinks.push(await readSymlink(absolutePath, relativePath));
    return;
  }
  if (isDir) {
    if (isExcluded(relativePath, true, ctx.exclude)) return;
    const sub = await walkLocalDir(absolutePath, ctx.basePath, ctx.exclude);
    ctx.result.files.push(...sub.files);
    ctx.result.symlinks.push(...sub.symlinks);
    return;
  }
  if (isFile) {
    if (isExcluded(relativePath, false, ctx.exclude)) return;
    ctx.result.files.push(await readFileEntry(absolutePath, relativePath));
  }
}

export async function walkLocalDir(
  dirPath: string,
  basePath: string,
  exclude: string[]
): Promise<WalkResult> {
  const result: WalkResult = { files: [], symlinks: [] };
  const ctx: DirEntryCtx = { basePath, exclude, result };
  const entries = await fsPromises.readdir(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const absolutePath = path.join(dirPath, entry.name);
    await visitEntry(
      absolutePath,
      entry.isSymbolicLink(),
      entry.isDirectory(),
      entry.isFile(),
      ctx
    );
  }
  return result;
}

/** Collect every parent directory referenced by a list of relative paths. */
export function collectSubdirs(paths: string[]): string[] {
  const subdirs = new Set<string>();
  for (const p of paths) {
    let dir = path.posix.dirname(p);
    while (dir && dir !== '.' && dir !== '/') {
      subdirs.add(dir);
      const next = path.posix.dirname(dir);
      if (next === dir) break;
      dir = next;
    }
  }
  return [...subdirs].sort();
}

async function expandFileSource(absolutePath: string): Promise<SftpFileEntry> {
  const stat = await fsPromises.stat(absolutePath);
  return {
    remoteRelative: path.basename(absolutePath),
    absolutePath,
    size: stat.size,
    mode: stat.mode & 0o777,
  };
}

export async function expandSftpSources(
  sources: SftpUploadSource[],
  exclude: string[]
): Promise<ExpandedSources> {
  const files: SftpFileEntry[] = [];
  const symlinks: SftpSymlinkEntry[] = [];
  for (const src of sources) {
    const normalized = src.path.replace(/[/\\]+$/, '');
    if (src.isFile) {
      files.push(await expandFileSource(normalized));
      continue;
    }
    const walked = await walkLocalDir(normalized, normalized, exclude);
    for (const f of walked.files) {
      files.push({
        remoteRelative: f.relativePath,
        absolutePath: f.absolutePath,
        size: f.size,
        mode: f.mode,
      });
    }
    for (const s of walked.symlinks) {
      symlinks.push({ remoteRelative: s.relativePath, target: s.target });
    }
  }
  return { files, symlinks };
}
