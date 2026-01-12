import * as path from 'node:path';

/**
 * Get the path to the local renet binary.
 *
 * Resolution order:
 * 1. RENET_BINARY_PATH env var (CI mode - pre-extracted binary)
 * 2. RENET_BIN env var (deprecated, backwards compatibility)
 * 3. RENET_ROOT/bin/renet (if RENET_ROOT is set)
 * 4. Auto-detected {monorepo}/bin/renet
 *
 * @param renetRoot Optional override for renet root directory
 * @returns Resolved path to renet binary (may not exist)
 */
export function getRenetBinaryPath(renetRoot?: string): string {
  // 1. CI mode: RENET_BINARY_PATH takes precedence
  const ciPath = process.env.RENET_BINARY_PATH;
  if (ciPath) {
    return ciPath;
  }

  // 2. Deprecated: RENET_BIN for backwards compatibility
  const legacyPath = process.env.RENET_BIN;
  if (legacyPath) {
    return legacyPath;
  }

  // 3. Use provided or env RENET_ROOT
  const root = renetRoot ?? process.env.RENET_ROOT;
  if (root) {
    return path.join(root, 'bin', 'renet');
  }

  // 4. Auto-detect from current location
  // Path: packages/bridge-tests/src/utils -> monorepo root
  const autoRoot = path.resolve(__dirname, '../../../..');
  return path.join(autoRoot, 'bin', 'renet');
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
  // Path: packages/bridge-tests/src/utils -> monorepo root
  return path.resolve(__dirname, '../../../..');
}
