/**
 * Embedded Assets - SEA asset extraction utilities
 *
 * Provides utilities for working with embedded assets in Node.js
 * Single Executable Applications (SEA). Used to extract renet binaries
 * for provisioning to remote Linux machines.
 */

import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import * as os from 'node:os';
import * as path from 'node:path';

/** Supported architectures for renet */
export type RenetArch = 'amd64' | 'arm64';

/** Supported platforms for renet */
export type RenetPlatform = 'linux' | 'darwin' | 'windows';

/** @deprecated Use RenetArch instead */
export type LinuxArch = RenetArch;

/** Binary metadata entry */
interface BinaryMeta {
  size: number;
  sha256: string;
}

/** Metadata for embedded renet binaries */
export interface RenetMetadata {
  version: string;
  generatedAt: string;
  binaries: Record<string, BinaryMeta>;
}

/** SEA module interface for type safety */
interface SEAModule {
  isSea(): boolean;
  getAsset(key: string): ArrayBuffer;
}

/**
 * Try to load the node:sea module for SEA asset access
 * Returns null if not running as SEA
 *
 * Note: On Node.js 22+, `require('node:sea')` succeeds and `sea.getAsset`
 * exists as a function even outside SEA context. We must use `sea.isSea()`
 * to reliably detect whether we're actually running inside a SEA binary.
 */
function tryLoadSEA(): SEAModule | null {
  try {
    const require = createRequire(import.meta.url);
    const sea = require('node:sea') as SEAModule;
    if (typeof sea.isSea === 'function' && sea.isSea()) {
      return sea;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Check if running as a Node.js Single Executable Application
 *
 * @returns true if running as SEA with embedded assets
 */
export function isSEA(): boolean {
  return tryLoadSEA() !== null;
}

/**
 * Get an embedded renet binary for a specific platform and architecture
 *
 * @param platform - Target platform (linux or darwin)
 * @param arch - Target architecture (amd64 or arm64)
 * @returns Binary data as Buffer
 * @throws Error if not running as SEA or asset not found
 */
export function getEmbeddedRenetBinary(platform: RenetPlatform, arch: RenetArch): Buffer {
  const sea = tryLoadSEA();
  if (!sea) {
    throw new Error('Not running as SEA - embedded assets not available');
  }

  // Note: getAsset throws if the asset is not found, no need for a falsy check
  const asset = sea.getAsset(`renet-${platform}-${arch}`);
  return Buffer.from(asset);
}

/**
 * Validate that parsed data conforms to RenetMetadata interface
 *
 * @param data - Parsed JSON data to validate
 * @returns true if data is valid RenetMetadata
 */
function isValidBinaryEntry(binary: unknown): boolean {
  if (typeof binary !== 'object' || binary === null) return false;
  const obj = binary as Record<string, unknown>;
  return typeof obj.size === 'number' && typeof obj.sha256 === 'string';
}

function isValidRenetMetadata(data: unknown): data is RenetMetadata {
  if (typeof data !== 'object' || data === null) return false;

  const obj = data as Record<string, unknown>;
  if (typeof obj.version !== 'string' || typeof obj.generatedAt !== 'string') return false;
  if (typeof obj.binaries !== 'object' || obj.binaries === null) return false;

  const binaries = obj.binaries as Record<string, unknown>;

  // All binary entries (required + optional) must have correct shape
  return Object.values(binaries).every(isValidBinaryEntry);
}

/**
 * Get the embedded renet metadata (versions, hashes, sizes)
 *
 * @returns Parsed metadata object
 * @throws Error if not running as SEA, asset not found, or metadata is invalid
 */
export function getEmbeddedMetadata(): RenetMetadata {
  const sea = tryLoadSEA();
  if (!sea) {
    throw new Error('Not running as SEA - embedded assets not available');
  }

  // Note: getAsset throws if the asset is not found, no need for a falsy check
  const asset = sea.getAsset('renet-metadata.json');
  const parsed: unknown = JSON.parse(Buffer.from(asset).toString('utf-8'));

  if (!isValidRenetMetadata(parsed)) {
    throw new Error('Embedded renet-metadata.json has invalid format');
  }

  return parsed;
}

/**
 * Compute SHA256 hash of data
 *
 * @param data - Data to hash
 * @returns Lowercase hex-encoded SHA256 hash
 */
export function computeSha256(data: Buffer): string {
  return crypto.createHash('sha256').update(data).digest('hex');
}

/** Cached local path for extracted renet binary (per-process) */
let cachedLocalPath: string | null = null;

/**
 * Extract the embedded renet binary to a local temp file for SEA-mode local spawning.
 * Cached per-process; validates the cached path still exists before reuse.
 *
 * @returns Absolute path to the locally extracted renet binary
 * @throws Error if not running as SEA or extraction fails
 */
export async function extractRenetToLocal(): Promise<string> {
  if (cachedLocalPath) {
    try {
      await fs.access(cachedLocalPath);
      return cachedLocalPath;
    } catch {
      cachedLocalPath = null;
    }
  }

  const platformMap: Record<string, RenetPlatform> = {
    darwin: 'darwin',
    win32: 'windows',
  };
  const platform: RenetPlatform = platformMap[process.platform] ?? 'linux';
  const arch: RenetArch = process.arch === 'arm64' ? 'arm64' : 'amd64';
  const binary = getEmbeddedRenetBinary(platform, arch);

  const dir = path.join(os.tmpdir(), '.rdc-local');
  await fs.mkdir(dir, { recursive: true });

  const ext = platform === 'windows' ? '.exe' : '';
  const localPath = path.join(dir, `renet${ext}`);
  await fs.writeFile(localPath, binary);
  if (platform !== 'windows') {
    await fs.chmod(localPath, 0o755);
  }

  cachedLocalPath = localPath;
  return localPath;
}
