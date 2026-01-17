import * as path from 'node:path';
import { getRenetResolver } from './RenetResolver';

// Path from this file to monorepo root: src/utils -> bridge-tests -> packages -> console -> monorepo
const MONOREPO_ROOT = path.resolve(__dirname, '../../../../..');

/**
 * Get path to renet binary built from source.
 * Internal helper for getRenetBinaryPath fallback.
 */
function getRenetSourceBinaryPath(): string {
  return path.join(MONOREPO_ROOT, 'renet', 'bin', 'renet');
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
 * 2. Auto-detected from current location
 */
export function getRenetRoot(): string {
  if (process.env.RENET_ROOT) {
    return process.env.RENET_ROOT;
  }
  return MONOREPO_ROOT;
}
