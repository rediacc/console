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
  // Cache management
  clearPathCache,
  findSystemMsys2Path,
  // Path resolution functions
  getBundledMsys2Path,
  // Environment setup
  getMsys2Environment,
  getMsys2Status,
  getRsyncPath,
  getSshKeygenPath,
  getSshPath,
  // Status and verification
  isMsys2Available,
  // Constants
  REQUIRED_BINARIES,
  REQUIRED_DLLS,
  verifyBundleIntegrity,
} from './paths.js';
