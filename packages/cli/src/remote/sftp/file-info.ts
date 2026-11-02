/**
 * Conversion of ssh2 directory entries and stats into the CLI's FileInfo shape.
 */

import type { FileEntry, Stats } from 'ssh2';
import type { FileInfo } from '../types/index.js';

/**
 * Convert ssh2 FileEntry to our FileInfo type
 */
export function fileEntryToFileInfo(parentPath: string, entry: FileEntry): FileInfo {
  const fullPath = parentPath.endsWith('/')
    ? `${parentPath}${entry.filename}`
    : `${parentPath}/${entry.filename}`;

  // Check file type from mode bits
  // S_IFMT = 0o170000 (file type mask)
  // S_IFDIR = 0o040000 (directory)
  // S_IFREG = 0o100000 (regular file)
  // S_IFLNK = 0o120000 (symbolic link)
  const mode = entry.attrs.mode;
  const fileTypeMask = mode & 0o170000;
  const isDirectory = fileTypeMask === 0o040000;
  const isFile = fileTypeMask === 0o100000;
  const isSymlink = fileTypeMask === 0o120000;

  return {
    name: entry.filename,
    path: fullPath,
    isDirectory,
    isFile,
    isSymlink,
    size: entry.attrs.size,
    modifiedAt: new Date(entry.attrs.mtime * 1000),
    permissions: formatPermissions(mode),
    owner: entry.attrs.uid.toString(),
    group: entry.attrs.gid.toString(),
  };
}

/**
 * Convert ssh2 Stats to our FileInfo type
 */
export function statsToFileInfo(path: string, stats: Stats): FileInfo {
  const name = path.split('/').pop() ?? '';

  return {
    name,
    path,
    isDirectory: stats.isDirectory(),
    isFile: stats.isFile(),
    isSymlink: stats.isSymbolicLink(),
    size: stats.size,
    modifiedAt: new Date(stats.mtime * 1000),
    permissions: formatPermissions(stats.mode),
    owner: stats.uid.toString(),
    group: stats.gid.toString(),
  };
}

/**
 * Format mode number to permission string (e.g., "755")
 */
function formatPermissions(mode: number): string {
  return (mode & 0o777).toString(8);
}
