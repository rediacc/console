/**
 * Embedded Assets - SEA asset extraction utilities
 *
 * Provides utilities for working with embedded assets in Node.js
 * Single Executable Applications (SEA). Used to extract renet binaries
 * for provisioning to remote Linux machines.
 */

import * as crypto from 'node:crypto';
import { createRequire } from 'node:module';

/** Supported Linux architectures for renet */
export type LinuxArch = 'amd64' | 'arm64';

/** Metadata for embedded renet binaries */
export interface RenetMetadata {
  version: string;
  generatedAt: string;
  binaries: Record<LinuxArch, { size: number; sha256: string }>;
}

/** SEA module interface for type safety */
interface SEAModule {
  getAsset(key: string): ArrayBuffer;
}

/**
 * Try to load the node:sea module for SEA asset access
 * Returns null if not running as SEA
 */
function tryLoadSEA(): SEAModule | null {
  try {
    const require = createRequire(import.meta.url);
    const sea = require('node:sea') as SEAModule;
    if (typeof sea.getAsset === 'function') {
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
 * Get an embedded renet binary for a specific Linux architecture
 *
 * @param arch - Target architecture (amd64 or arm64)
 * @returns Binary data as Buffer
 * @throws Error if not running as SEA or asset not found
 */
export function getEmbeddedRenetBinary(arch: LinuxArch): Buffer {
  const sea = tryLoadSEA();
  if (!sea) {
    throw new Error('Not running as SEA - embedded assets not available');
  }

  // Note: getAsset throws if the asset is not found, no need for a falsy check
  const asset = sea.getAsset(`renet-linux-${arch}`);
  return Buffer.from(asset);
}

/**
 * Validate that parsed data conforms to RenetMetadata interface
 *
 * @param data - Parsed JSON data to validate
 * @returns true if data is valid RenetMetadata
 */
function isValidRenetMetadata(data: unknown): data is RenetMetadata {
  if (typeof data !== 'object' || data === null) {
    return false;
  }

  const obj = data as Record<string, unknown>;

  if (typeof obj.version !== 'string' || typeof obj.generatedAt !== 'string') {
    return false;
  }

  if (typeof obj.binaries !== 'object' || obj.binaries === null) {
    return false;
  }

  const binaries = obj.binaries as Record<string, unknown>;
  const requiredArchs: LinuxArch[] = ['amd64', 'arm64'];

  for (const arch of requiredArchs) {
    const binary = binaries[arch];
    if (typeof binary !== 'object' || binary === null) {
      return false;
    }
    const binaryObj = binary as Record<string, unknown>;
    if (typeof binaryObj.size !== 'number' || typeof binaryObj.sha256 !== 'string') {
      return false;
    }
  }

  return true;
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
