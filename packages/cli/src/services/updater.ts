import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { get as httpsGet } from 'node:https';
import { get as httpGet } from 'node:http';
import { dirname, join } from 'node:path';
import { VERSION } from '../version.js';
import type { UpdateManifest } from '../types/index.js';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  releaseUpdateLock,
} from '../utils/platform.js';

const MANIFEST_URL = 'https://www.rediacc.com/cli/manifest.json';
const GITHUB_API_FALLBACK = 'https://api.github.com/repos/rediacc/console/releases/latest';
const CHECK_TIMEOUT_MS = 3000;
const DOWNLOAD_TIMEOUT_MS = 120_000;

export interface UpdateCheckResult {
  updateAvailable: boolean;
  currentVersion: string;
  latestVersion?: string;
  releaseNotesUrl?: string;
  manifest?: UpdateManifest;
}

export interface UpdateResult {
  success: boolean;
  fromVersion: string;
  toVersion: string;
  error?: string;
}

/**
 * Fetch JSON from a URL with a timeout.
 */
function fetchJson<T>(url: string, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const getter = url.startsWith('https://') ? httpsGet : httpGet;
    const req = getter(url, { headers: { 'User-Agent': `rdc/${VERSION}` } }, (res) => {
      // Follow redirects
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        fetchJson<T>(res.headers.location, timeoutMs).then(resolve, reject);
        return;
      }

      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => chunks.push(chunk));
      res.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString('utf-8')));
        } catch (e) {
          reject(new Error('Invalid JSON response'));
        }
      });
      res.on('error', reject);
    });

    req.on('error', reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
  });
}

/**
 * Download a binary file from a URL to a local path with progress callback.
 */
function downloadFile(
  url: string,
  destPath: string,
  onProgress?: (downloaded: number, total: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const getter = url.startsWith('https://') ? httpsGet : httpGet;
    const req = getter(url, { headers: { 'User-Agent': `rdc/${VERSION}` } }, (res) => {
      // Follow redirects
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        downloadFile(res.headers.location, destPath, onProgress).then(resolve, reject);
        return;
      }

      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      const total = parseInt(res.headers['content-length'] ?? '0', 10);
      let downloaded = 0;

      const writeStream = fs.open(destPath, 'w', 0o755).then(async (fh) => {
        try {
          for await (const chunk of res) {
            await fh.write(chunk as Buffer);
            downloaded += (chunk as Buffer).length;
            onProgress?.(downloaded, total);
          }
        } finally {
          await fh.close();
        }
      });

      writeStream.then(resolve, reject);
    });

    req.on('error', reject);
    req.setTimeout(DOWNLOAD_TIMEOUT_MS, () => {
      req.destroy();
      reject(new Error('Download timeout'));
    });
  });
}

/**
 * Compute SHA256 hash of a file.
 */
async function computeSha256(filePath: string): Promise<string> {
  const hash = createHash('sha256');
  const content = await fs.readFile(filePath);
  hash.update(content);
  return hash.digest('hex');
}

/**
 * Compare two semantic versions. Returns:
 *  -1 if a < b
 *   0 if a == b
 *   1 if a > b
 */
export function compareVersions(a: string, b: string): number {
  const pa = a.replace(/^v/, '').split('.').map(Number);
  const pb = b.replace(/^v/, '').split('.').map(Number);

  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] ?? 0;
    const nb = pb[i] ?? 0;
    if (na < nb) return -1;
    if (na > nb) return 1;
  }
  return 0;
}

/**
 * Fetch the update manifest (Pages primary, GitHub API fallback).
 */
async function fetchManifest(timeoutMs: number = CHECK_TIMEOUT_MS): Promise<UpdateManifest> {
  try {
    return await fetchJson<UpdateManifest>(MANIFEST_URL, timeoutMs);
  } catch {
    // Fallback: GitHub Releases API
    const release = await fetchJson<{ tag_name: string; html_url: string; published_at: string; assets: Array<{ name: string; browser_download_url: string }> }>(
      GITHUB_API_FALLBACK,
      timeoutMs
    );

    // Build manifest from release data
    const version = release.tag_name.replace(/^v/, '');
    const manifest: UpdateManifest = {
      version,
      releaseDate: release.published_at,
      releaseNotesUrl: release.html_url,
      binaries: {},
    };

    // Parse assets to find CLI binaries and their checksums
    const checksums = new Map<string, string>();
    for (const asset of release.assets) {
      if (asset.name.endsWith('.sha256')) {
        // Will need to download checksum content - skip for now, use empty
        const baseName = asset.name.replace('.sha256', '');
        checksums.set(baseName, '');
      }
    }

    for (const asset of release.assets) {
      const match = asset.name.match(/^rdc-(linux|mac|win)-(x64|arm64)(\.exe)?$/);
      if (match) {
        const key = `${match[1]}-${match[2]}` as keyof UpdateManifest['binaries'];
        manifest.binaries[key] = {
          url: asset.browser_download_url,
          sha256: checksums.get(asset.name) ?? '',
        };
      }
    }

    return manifest;
  }
}

/**
 * Check for available updates (non-blocking, never throws).
 */
export async function checkForUpdate(): Promise<UpdateCheckResult> {
  const result: UpdateCheckResult = {
    updateAvailable: false,
    currentVersion: VERSION,
  };

  if (!isSEA() || isUpdateDisabled()) {
    return result;
  }

  try {
    const manifest = await fetchManifest(CHECK_TIMEOUT_MS);
    result.latestVersion = manifest.version;
    result.releaseNotesUrl = manifest.releaseNotesUrl;
    result.manifest = manifest;
    result.updateAvailable = compareVersions(VERSION, manifest.version) < 0;
  } catch {
    // Silent failure - never interfere with CLI operation
  }

  return result;
}

/**
 * Perform the self-update.
 */
export async function performUpdate(
  options: { force?: boolean; onProgress?: (downloaded: number, total: number) => void } = {}
): Promise<UpdateResult> {
  const { force = false, onProgress } = options;

  if (!isSEA()) {
    return {
      success: false,
      fromVersion: VERSION,
      toVersion: VERSION,
      error: 'update.errors.notSEA',
    };
  }

  const platformKey = getPlatformKey();
  if (!platformKey) {
    return {
      success: false,
      fromVersion: VERSION,
      toVersion: VERSION,
      error: 'update.errors.unsupportedPlatform',
    };
  }

  // Acquire lock
  const locked = await acquireUpdateLock();
  if (!locked) {
    return {
      success: false,
      fromVersion: VERSION,
      toVersion: VERSION,
      error: 'update.errors.lockFailed',
    };
  }

  try {
    // Fetch manifest with longer timeout for explicit update
    const manifest = await fetchManifest(10_000);

    if (!force && compareVersions(VERSION, manifest.version) >= 0) {
      return {
        success: true,
        fromVersion: VERSION,
        toVersion: VERSION,
        error: 'update.errors.alreadyUpToDate',
      };
    }

    const binaryInfo = manifest.binaries[platformKey];
    if (!binaryInfo) {
      return {
        success: false,
        fromVersion: VERSION,
        toVersion: manifest.version,
        error: 'update.errors.noBinary',
      };
    }

    // Download to temp file in same directory as current binary
    const execPath = process.execPath;
    const execDir = dirname(execPath);
    const tempPath = join(execDir, `.rdc-update-${Date.now()}.tmp`);

    try {
      await downloadFile(binaryInfo.url, tempPath, onProgress);

      // Verify SHA256 if provided
      if (binaryInfo.sha256) {
        const actualHash = await computeSha256(tempPath);
        if (actualHash !== binaryInfo.sha256) {
          await fs.unlink(tempPath).catch(() => {});
          return {
            success: false,
            fromVersion: VERSION,
            toVersion: manifest.version,
            error: 'update.errors.checksumMismatch',
          };
        }
      }

      // Self-replace: rename current -> .old, rename new -> current
      const oldPath = getOldBinaryPath();

      // Remove any existing old binary first
      await fs.unlink(oldPath).catch(() => {});

      // Rename current binary to .old
      await fs.rename(execPath, oldPath);

      // Rename downloaded binary to current path
      await fs.rename(tempPath, execPath);

      // Set executable permission (no-op on Windows)
      if (process.platform !== 'win32') {
        await fs.chmod(execPath, 0o755);
      }

      return {
        success: true,
        fromVersion: VERSION,
        toVersion: manifest.version,
      };
    } catch (err) {
      // Clean up temp file on error
      await fs.unlink(tempPath).catch(() => {});
      throw err;
    }
  } catch (err) {
    return {
      success: false,
      fromVersion: VERSION,
      toVersion: VERSION,
      error: err instanceof Error ? err.message : 'update.errors.unknown',
    };
  } finally {
    await releaseUpdateLock();
  }
}

/**
 * Run the startup update check. Non-blocking, prints to stderr.
 * Returns a promise that resolves when the check is done.
 */
export async function startupUpdateCheck(): Promise<void> {
  if (!isSEA() || isUpdateDisabled()) return;

  // Clean up old binary from previous update
  await cleanupOldBinary();

  // Check for updates
  const result = await checkForUpdate();
  if (result.updateAvailable && result.latestVersion) {
    process.stderr.write(
      `Update available: v${result.latestVersion} (current: v${VERSION}). Run \`rdc update\` to upgrade.\n`
    );
  }
}
