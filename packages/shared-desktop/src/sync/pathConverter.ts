import { isAbsolute } from 'node:path';
import { getPlatform, windowsToUnixPath } from '../utils/platform.js';

/**
 * Checks if a path is a remote rsync path (user@host:path)
 *
 * @param path - Path to check
 * @returns true if path is remote
 */
export function isRemotePath(path: string): boolean {
  if (!path) return false;
  // Remote paths contain @ and : after the @ (e.g., user@host:/path)
  if (path.includes('@')) {
    const afterAt = path.split('@')[1];
    return afterAt ? afterAt.includes(':') : false;
  }
  return false;
}

/**
 * Converts a local Windows path to MSYS2 format for rsync
 * e.g., C:\Users\foo\bar -> /c/Users/foo/bar
 *
 * @param localPath - Local path to convert
 * @returns Converted path suitable for MSYS2 rsync
 */
export function convertLocalPathForRsync(localPath: string): string {
  if (!localPath) return localPath;

  // Don't convert remote paths
  if (isRemotePath(localPath)) {
    return localPath;
  }

  // On non-Windows platforms, just ensure forward slashes
  if (getPlatform() !== 'windows') {
    return localPath;
  }

  // Handle relative paths - just replace backslashes
  if (!isAbsolute(localPath)) {
    return localPath.replaceAll('\\', '/');
  }

  // Convert Windows absolute path to MSYS2/Cygwin format
  // MSYS2 rsync expects local Windows paths in /c/Users/... format
  return windowsToUnixPath(localPath);
}

/**
 * Prepares rsync source and destination paths for the current platform
 *
 * @param source - Source path
 * @param dest - Destination path
 * @returns Tuple of [convertedSource, convertedDest]
 */
export function prepareRsyncPaths(source: string, dest: string): [string, string] {
  if (getPlatform() !== 'windows') {
    return [source, dest];
  }

  const convertedSource = isRemotePath(source) ? source : convertLocalPathForRsync(source);
  const convertedDest = isRemotePath(dest) ? dest : convertLocalPathForRsync(dest);

  return [convertedSource, convertedDest];
}

/**
 * Ensures a path ends with a trailing slash (for directory sync)
 *
 * @param path - Path to modify
 * @returns Path with trailing slash
 */
export function ensureTrailingSlash(path: string): string {
  if (!path) return path;
  if (path.endsWith('/') || path.endsWith('\\')) {
    return path;
  }
  return `${path}/`;
}

/**
 * Removes trailing slash from a path
 *
 * @param path - Path to modify
 * @returns Path without trailing slash
 */
export function removeTrailingSlash(path: string): string {
  if (!path) return path;
  return path.replace(/[/\\]+$/, '');
}

/**
 * Joins a remote destination with a path
 * e.g., user@host + /path/to/dir -> user@host:/path/to/dir
 *
 * @param destination - SSH destination (user@host)
 * @param remotePath - Remote path
 * @returns Combined remote rsync path
 */
export function joinRemotePath(destination: string, remotePath: string): string {
  return `${destination}:${remotePath}`;
}

/**
 * Extracts the host and path from a remote rsync path
 *
 * @param remotePath - Remote rsync path (user@host:/path)
 * @returns Object with host and path, or null if not a remote path
 */
export function parseRemotePath(remotePath: string): { host: string; path: string } | null {
  if (!isRemotePath(remotePath)) {
    return null;
  }

  const colonIndex = remotePath.indexOf(':');
  if (colonIndex === -1) {
    return null;
  }

  return {
    host: remotePath.substring(0, colonIndex),
    path: remotePath.substring(colonIndex + 1),
  };
}
