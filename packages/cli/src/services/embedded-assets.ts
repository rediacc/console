/**
 * Embedded Assets - SEA asset extraction utilities
 *
 * Provides utilities for working with embedded assets in Node.js
 * Single Executable Applications (SEA). Used to extract renet binaries
 * for provisioning to remote Linux machines.
 */

import * as crypto from 'node:crypto';
import * as fsSync from 'node:fs';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { PLATFORM_DEFAULTS } from '@rediacc/shared/config/defaults';

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
    const sea = process.getBuiltinModule('node:sea') as SEAModule | undefined;
    if (!sea) {
      return null;
    }
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

/** Host platform/arch and the extraction target for the local renet binary. */
function hostRenetTarget(): {
  platform: RenetPlatform;
  arch: RenetArch;
  dir: string;
  localPath: string;
  metaKey: string;
} {
  const platformMap: Record<string, RenetPlatform> = {
    darwin: 'darwin',
    win32: 'windows',
  };
  const platform: RenetPlatform = platformMap[process.platform] ?? PLATFORM_DEFAULTS.DEFAULT_RENET;
  const arch: RenetArch = process.arch === 'arm64' ? 'arm64' : 'amd64';
  const dir = path.join(os.tmpdir(), '.rdc-local');
  const ext = platform === 'windows' ? '.exe' : '';
  return {
    platform,
    arch,
    dir,
    localPath: path.join(dir, `renet${ext}`),
    // Metadata keys (prepare-cli-assets.sh binary_to_meta_key): linux drops
    // the platform prefix ("amd64"), darwin/windows keep it ("darwin-arm64").
    metaKey: platform === 'linux' ? arch : `${platform}-${arch}`,
  };
}

/** The embedded sha256 for the host renet binary, or null if metadata lacks it. */
function expectedRenetSha(metaKey: string): string | null {
  try {
    const { binaries } = getEmbeddedMetadata();
    if (!(metaKey in binaries)) return null;
    return binaries[metaKey].sha256;
  } catch {
    return null;
  }
}

/**
 * Reuse a previously extracted binary when it hashes to the embedded sha256.
 * Avoids rewriting the large binary on every invocation, and verifies the
 * agent-writable temp file before anything spawns it.
 */
function reuseVerifiedExtraction(localPath: string, expectedSha: string | null): boolean {
  if (!expectedSha) return false;
  try {
    return computeSha256(fsSync.readFileSync(localPath)) === expectedSha;
  } catch {
    return false; // missing or unreadable — extract fresh
  }
}

/**
 * Extract the embedded renet binary to a local temp file for SEA-mode local spawning.
 * Cached per-process; reuses an on-disk extraction when its sha256 matches the
 * embedded metadata. Writes go through a temp file + atomic rename so
 * concurrent rdc processes never observe a partial binary (or ETXTBSY).
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

  const { platform, arch, dir, localPath, metaKey } = hostRenetTarget();
  if (reuseVerifiedExtraction(localPath, expectedRenetSha(metaKey))) {
    cachedLocalPath = localPath;
    return localPath;
  }

  const binary = getEmbeddedRenetBinary(platform, arch);
  await fs.mkdir(dir, { recursive: true });

  const tmpPath = path.join(dir, `renet.${process.pid}.tmp`);
  await fs.writeFile(tmpPath, binary);
  if (platform !== 'windows') {
    await fs.chmod(tmpPath, 0o755);
  }
  await fs.rename(tmpPath, localPath);

  cachedLocalPath = localPath;
  return localPath;
}

/**
 * Synchronous variant of extractRenetToLocal for callers that cannot await —
 * the agent-guard ancestry verification spawns renet with spawnSync inside a
 * synchronous guard chain. Same target path, verify-reuse, and atomic-rename
 * semantics as the async path.
 *
 * @returns Absolute path to the locally extracted renet binary
 * @throws Error if not running as SEA or extraction fails
 */
export function extractRenetToLocalSync(): string {
  if (cachedLocalPath) {
    try {
      fsSync.accessSync(cachedLocalPath);
      return cachedLocalPath;
    } catch {
      cachedLocalPath = null;
    }
  }

  const { platform, arch, dir, localPath, metaKey } = hostRenetTarget();
  if (reuseVerifiedExtraction(localPath, expectedRenetSha(metaKey))) {
    cachedLocalPath = localPath;
    return localPath;
  }

  const binary = getEmbeddedRenetBinary(platform, arch);
  fsSync.mkdirSync(dir, { recursive: true });

  const tmpPath = path.join(dir, `renet.${process.pid}.tmp`);
  fsSync.writeFileSync(tmpPath, binary);
  if (platform !== 'windows') {
    fsSync.chmodSync(tmpPath, 0o755);
  }
  fsSync.renameSync(tmpPath, localPath);

  cachedLocalPath = localPath;
  return localPath;
}
