import { createHash } from 'node:crypto';
import { chmod, rename, writeFile } from 'node:fs/promises';
import https from 'node:https';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  type PlatformKey,
  releaseUpdateLock,
} from '../utils/platform.js';

const MANIFEST_URL = 'https://www.rediacc.com/cli/manifest.json';
const CHECK_TIMEOUT = 3000;

export interface ManifestAsset {
  url: string;
  sha256: string;
}

export interface UpdateManifest {
  version: string;
  assets: Partial<Record<PlatformKey, ManifestAsset>>;
}

export interface CheckUpdateResult {
  updateAvailable: boolean;
  currentVersion: string;
  latestVersion?: string;
  manifest?: UpdateManifest;
}

export type UpdateErrorReason =
  | 'notSEA'
  | 'unsupportedPlatform'
  | 'lockFailed'
  | 'alreadyUpToDate'
  | 'checksumMismatch'
  | 'downloadFailed'
  | 'networkError';

export interface UpdateResult {
  success: boolean;
  error?: UpdateErrorReason;
  version?: string;
}

/**
 * Compare two semver-like version strings.
 * Returns -1 if a < b, 0 if a == b, 1 if a > b.
 */
export function compareVersions(a: string, b: string): -1 | 0 | 1 {
  const normalize = (v: string) =>
    v
      .replace(/^v/, '')
      .split('.')
      .map((n) => Number.parseInt(n, 10) || 0);

  const partsA = normalize(a);
  const partsB = normalize(b);
  const maxLen = Math.max(partsA.length, partsB.length);

  for (let i = 0; i < maxLen; i++) {
    const numA = partsA[i] ?? 0;
    const numB = partsB[i] ?? 0;
    if (numA < numB) return -1;
    if (numA > numB) return 1;
  }
  return 0;
}

/**
 * Fetch the update manifest from the remote server.
 */
async function fetchManifest(): Promise<UpdateManifest | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), CHECK_TIMEOUT);

    const req = https.get(MANIFEST_URL, (res) => {
      if (res.statusCode !== 200) {
        clearTimeout(timer);
        res.resume();
        resolve(null);
        return;
      }

      let data = '';
      res.on('data', (chunk: Buffer) => {
        data += chunk.toString();
      });
      res.on('end', () => {
        clearTimeout(timer);
        try {
          resolve(JSON.parse(data) as UpdateManifest);
        } catch {
          resolve(null);
        }
      });
    });

    req.on('error', () => {
      clearTimeout(timer);
      resolve(null);
    });

    req.on('timeout', () => {
      req.destroy();
      clearTimeout(timer);
      resolve(null);
    });
  });
}

/**
 * Check if an update is available.
 * Returns immediately with updateAvailable=false if not a SEA binary or updates are disabled.
 */
export async function checkForUpdate(currentVersion: string): Promise<CheckUpdateResult> {
  if (!isSEA()) {
    return { updateAvailable: false, currentVersion };
  }

  if (isUpdateDisabled()) {
    return { updateAvailable: false, currentVersion };
  }

  const manifest = await fetchManifest();
  if (!manifest) {
    return { updateAvailable: false, currentVersion };
  }

  const updateAvailable = compareVersions(currentVersion, manifest.version) < 0;
  return {
    updateAvailable,
    currentVersion,
    latestVersion: manifest.version,
    manifest,
  };
}

/**
 * Download a binary from the given URL as a Buffer.
 */
async function downloadBinary(url: string): Promise<Buffer | null> {
  return new Promise((resolve) => {
    const req = https.get(url, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        const redirectUrl = res.headers.location;
        if (redirectUrl) {
          res.resume();
          downloadBinary(redirectUrl)
            .then(resolve)
            .catch(() => resolve(null));
          return;
        }
      }
      if (res.statusCode !== 200) {
        res.resume();
        resolve(null);
        return;
      }

      const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => chunks.push(chunk));
      res.on('end', () => resolve(Buffer.concat(chunks)));
    });

    req.on('error', () => resolve(null));
  });
}

/**
 * Perform a self-update of the CLI binary.
 */
export async function performUpdate(
  currentVersion: string,
  options?: { force?: boolean }
): Promise<UpdateResult> {
  if (!isSEA()) {
    return { success: false, error: 'notSEA' };
  }

  const platformKey = getPlatformKey();
  if (!platformKey) {
    return { success: false, error: 'unsupportedPlatform' };
  }

  const locked = await acquireUpdateLock();
  if (!locked) {
    return { success: false, error: 'lockFailed' };
  }

  try {
    const manifest = await fetchManifest();
    if (!manifest) {
      return { success: false, error: 'networkError' };
    }

    if (!options?.force && compareVersions(currentVersion, manifest.version) >= 0) {
      return { success: true, version: currentVersion, error: 'alreadyUpToDate' };
    }

    const asset = manifest.assets[platformKey];
    if (!asset) {
      return { success: false, error: 'unsupportedPlatform' };
    }

    const binary = await downloadBinary(asset.url);
    if (!binary) {
      return { success: false, error: 'downloadFailed' };
    }

    // Verify checksum
    const hash = createHash('sha256').update(binary).digest('hex');
    if (hash !== asset.sha256) {
      return { success: false, error: 'checksumMismatch' };
    }

    // Self-replace: rename current → old, write new
    const execPath = process.execPath;
    const oldPath = getOldBinaryPath(execPath);
    await cleanupOldBinary(oldPath);
    await rename(execPath, oldPath);
    await writeFile(execPath, binary);
    if (process.platform !== 'win32') {
      await chmod(execPath, 0o755);
    }

    return { success: true, version: manifest.version };
  } finally {
    await releaseUpdateLock();
  }
}
