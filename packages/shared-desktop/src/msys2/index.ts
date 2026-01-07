/**
 * MSYS2 module - Windows-specific rsync/SSH bundling
 *
 * Provides utilities for locating and using MSYS2 binaries on Windows,
 * either from bundled Electron resources or system-wide installations.
 *
 * Key features:
 * - Bundled binary detection for Electron apps
 * - System-wide MSYS2 installation fallback
 * - Environment variable setup for rsync compatibility
 * - Path caching for performance
 *
 * @module msys2
 */

export {
  // Path resolution functions
  getBundledMsys2Path,
  findSystemMsys2Path,
  getRsyncPath,
  getSshPath,
  getSshKeygenPath,
  // Environment setup
  getMsys2Environment,
  // Status and verification
  isMsys2Available,
  getMsys2Status,
  verifyBundleIntegrity,
  // Cache management
  clearPathCache,
  // Constants
  REQUIRED_BINARIES,
  REQUIRED_DLLS,
} from './paths.js';
