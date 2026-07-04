/**
 * MSYS2 path detection and bundled binary resolution for Windows
 *
 * This module provides utilities for locating MSYS2 binaries, either from:
 * 1. Bundled Electron resources (preferred for desktop app)
 * 2. System-wide MSYS2 installation (fallback)
 *
 * @module msys2/paths
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { getPlatform } from '../utils/platform.js';

/**
 * System-wide MSYS2 installation paths to check
 */
const SYSTEM_MSYS2_PATHS = [
  process.env.MSYS2_ROOT,
  'C:\\msys64',
  'C:\\msys2',
  join(process.env.USERPROFILE ?? '', 'msys64'),
  join(process.env.USERPROFILE ?? '', 'msys2'),
  join(process.env.LOCALAPPDATA ?? '', 'msys64'),
  join(process.env.LOCALAPPDATA ?? '', 'msys2'),
].filter(Boolean) as string[];

/**
 * Subdirectories to check for binaries within MSYS2 installation
 */
const MSYS2_BIN_SUBDIRS = ['usr\\bin', 'mingw64\\bin', 'mingw32\\bin'] as const;

/**
 * Cache for resolved paths to avoid repeated filesystem checks
 */
const pathCache = new Map<string, string | null>();

/**
 * Gets the path to bundled MSYS2 binaries (for Electron app)
 *
 * When running in Electron with bundled resources, this returns
 * the path to the msys2-bundle directory in the app resources.
 *
 * @returns Path to bundled MSYS2 directory, or null if not bundled/not Electron
 */
function getBundledMsys2Path(): string | null {
  if (getPlatform() !== 'windows') {
    return null;
  }

  const cacheKey = 'bundled_msys2_path';
  if (pathCache.has(cacheKey)) {
    return pathCache.get(cacheKey) ?? null;
  }

  // Check if running in Electron with bundled resources
  // process.resourcesPath is set by Electron to point to the app resources directory
  const resourcesPath = (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath;
  if (resourcesPath) {
    const bundlePath = join(resourcesPath, 'msys2-bundle');
    if (existsSync(bundlePath)) {
      pathCache.set(cacheKey, bundlePath);
      return bundlePath;
    }
  }

  // Also check relative to the app directory for development
  const devBundlePaths = [
    join(process.cwd(), 'msys2-bundle'),
    join(process.cwd(), 'packages', 'desktop', 'msys2-bundle'),
    join(__dirname, '..', '..', '..', 'msys2-bundle'),
  ];

  for (const devPath of devBundlePaths) {
    if (existsSync(devPath)) {
      pathCache.set(cacheKey, devPath);
      return devPath;
    }
  }

  pathCache.set(cacheKey, null);
  return null;
}

/**
 * Finds a system-wide MSYS2 installation
 *
 * @returns Path to MSYS2 installation, or null if not found
 */
function findSystemMsys2Path(): string | null {
  if (getPlatform() !== 'windows') {
    return null;
  }

  const cacheKey = 'system_msys2_path';
  if (pathCache.has(cacheKey)) {
    return pathCache.get(cacheKey) ?? null;
  }

  for (const msys2Path of SYSTEM_MSYS2_PATHS) {
    // Check if the MSYS2 root exists and has the usr/bin directory
    const usrBinPath = join(msys2Path, 'usr', 'bin');
    if (existsSync(usrBinPath)) {
      pathCache.set(cacheKey, msys2Path);
      return msys2Path;
    }
  }

  pathCache.set(cacheKey, null);
  return null;
}

/**
 * Helper to find a binary in bundled or system MSYS2
 * Reduces cognitive complexity by centralizing search logic
 *
 * @param binaryName - Name of the binary (with .exe extension)
 * @param cacheKey - Key for caching the result
 * @param fallback - Fallback value if not found
 * @returns Path to the binary or fallback
 */
function findMsys2Binary(binaryName: string, cacheKey: string, fallback: string): string {
  if (pathCache.has(cacheKey)) {
    return pathCache.get(cacheKey) ?? fallback;
  }

  // Check bundled first
  const bundled = getBundledMsys2Path();
  if (bundled) {
    const binaryPath = join(bundled, 'usr', 'bin', binaryName);
    if (existsSync(binaryPath)) {
      pathCache.set(cacheKey, binaryPath);
      return binaryPath;
    }
  }

  // Check system MSYS2
  const systemMsys2 = findSystemMsys2Path();
  if (systemMsys2) {
    for (const subdir of MSYS2_BIN_SUBDIRS) {
      const binaryPath = join(systemMsys2, subdir, binaryName);
      if (existsSync(binaryPath)) {
        pathCache.set(cacheKey, binaryPath);
        return binaryPath;
      }
    }
  }

  // Last resort: assume in PATH
  pathCache.set(cacheKey, fallback);
  return fallback;
}

/**
 * Gets the path to rsync executable
 *
 * Checks in order:
 * 1. Bundled MSYS2 binaries (for Electron)
 * 2. System-wide MSYS2 installation
 * 3. Falls back to 'rsync' (assumes in PATH)
 *
 * @returns Path to rsync executable
 */
export function getRsyncPath(): string {
  if (getPlatform() !== 'windows') {
    return 'rsync';
  }
  return findMsys2Binary('rsync.exe', 'rsync_path', 'rsync');
}

/**
 * Gets the path to SSH executable
 *
 * Checks in order:
 * 1. Bundled MSYS2 binaries (for Electron)
 * 2. System-wide MSYS2 installation
 * 3. Falls back to 'ssh' (assumes in PATH)
 *
 * @returns Path to SSH executable
 */
export function getSshPath(): string {
  if (getPlatform() !== 'windows') {
    return 'ssh';
  }
  return findMsys2Binary('ssh.exe', 'ssh_path', 'ssh');
}

/**
 * Gets environment variables needed for MSYS2 binaries
 *
 * Sets up PATH, HOME, and disables MSYS2 automatic path conversion
 * to prevent issues with rsync 3.3.0+ path prefixing.
 *
 * @returns Environment variables to merge with process.env
 */
export function getMsys2Environment(): Record<string, string> {
  const bundled = getBundledMsys2Path();
  const systemMsys2 = findSystemMsys2Path();

  const msys2Root = bundled ?? systemMsys2;
  if (!msys2Root) {
    return {};
  }

  const binPath = join(msys2Root, 'usr', 'bin');

  return {
    // Add MSYS2 bin to PATH (prepend so bundled binaries take priority)
    PATH: `${binPath};${process.env.PATH ?? ''}`,
    // Set HOME for SSH config and known_hosts
    HOME: process.env.USERPROFILE ?? '',
    // Disable MSYS2 automatic path conversion (we handle it ourselves)
    // This prevents rsync 3.3.0+ from prefixing target paths incorrectly
    MSYS_NO_PATHCONV: '1',
    MSYS2_ARG_CONV_EXCL: '*',
    // Ensure consistent locale
    LANG: 'C.UTF-8',
  };
}
