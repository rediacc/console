import * as path from 'node:path';
import { getRenetResolver } from './RenetResolver';

// Cached monorepo root (can be overridden)
let cachedMonorepoRoot: string | undefined;

/**
 * Set the monorepo root directory.
 * Call this if the auto-detection doesn't work for your environment.
 */
export function setMonorepoRoot(root: string): void {
  cachedMonorepoRoot = root;
}

/**
 * Get the monorepo root directory.
 *
 * Resolution order:
 * 1. Cached override (set via setMonorepoRoot)
 * 2. RENET_ROOT environment variable
 * 3. Auto-detected from __dirname (works in most cases)
 */
export function getMonorepoRoot(): string {
  if (cachedMonorepoRoot) {
    return cachedMonorepoRoot;
  }

  if (process.env.RENET_ROOT) {
    return process.env.RENET_ROOT;
  }

  // Default: try to detect from this file's location
  // Path from this file to monorepo root varies by package location
  // This is a fallback - prefer setting RENET_ROOT or using setMonorepoRoot
  return path.resolve(__dirname, '../../../../..');
}

/**
 * Get path to renet binary built from source.
 * Internal helper for getRenetBinaryPath fallback.
 */
function getRenetSourceBinaryPath(): string {
  return path.join(getMonorepoRoot(), 'renet', 'bin', 'renet');
}

/**
 * Get the path to the local renet binary (synchronous).
 *
 * For async code with auto-build support, use RenetResolver.ensureBinary() instead.
 * This function is useful for synchronous initialization (e.g., in constructors).
 *
 * Resolution order when resolver not initialized:
 * 1. RENET_BINARY_PATH env var (CI mode)
 * 2. Source binary path (local development)
 *
 * @returns Resolved path to renet binary
 */
export function getRenetBinaryPath(): string {
  try {
    return getRenetResolver().getPath();
  } catch {
    // Resolver not initialized yet, check env var first (for CI mode)
    const envPath = process.env.RENET_BINARY_PATH;
    if (envPath) {
      return envPath;
    }
    // Fall back to source binary path for local development
    return getRenetSourceBinaryPath();
  }
}

/**
 * Get the renet root directory.
 *
 * Resolution order:
 * 1. RENET_ROOT env var
 * 2. Auto-detected monorepo root
 */
export function getRenetRoot(): string {
  if (process.env.RENET_ROOT) {
    return process.env.RENET_ROOT;
  }
  return getMonorepoRoot();
}
