import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { get as httpGet } from 'node:http';
import { get as httpsGet } from 'node:https';
import { dirname, join } from 'node:path';
import { type UpdateManifest } from '../types/index.js';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  releaseUpdateLock,
} from '../utils/platform.js';
import { VERSION } from '../version.js';

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

interface GitHubRelease {
  tag_name: string;
  html_url: string;
  published_at: string;
  assets: { name: string; browser_download_url: string }[];
}

/**
 * Select the appropriate HTTP getter for the URL scheme.
 */
function getHttpGetter(url: string) {
  return url.startsWith('https://') ? httpsGet : httpGet;
}

/**
 * Make an HTTP request and collect response body as a Buffer.
 * Handles redirects, status codes, and timeouts.
 */
function httpRequestBuffer(url: string, timeoutMs: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const getter = getHttpGetter(url);
    const req = getter(url, { headers: { 'User-Agent': `rdc/${VERSION}` } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        httpRequestBuffer(res.headers.location, timeoutMs).then(resolve, reject);
        return;
      }

      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => chunks.push(chunk));
      res.on('end', () => resolve(Buffer.concat(chunks)));
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
 * Fetch raw text from a URL with a timeout.
 */
async function fetchText(url: string, timeoutMs: number): Promise<string> {
  const buffer = await httpRequestBuffer(url, timeoutMs);
  return buffer.toString('utf-8');
}

/**
 * Fetch JSON from a URL with a timeout.
 */
async function fetchJson<T>(url: string, timeoutMs: number): Promise<T> {
  const text = await fetchText(url, timeoutMs);
  return JSON.parse(text) as T;
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
    const getter = getHttpGetter(url);
    const req = getter(url, { headers: { 'User-Agent': `rdc/${VERSION}` } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        downloadFile(res.headers.location, destPath, onProgress).then(resolve, reject);
        return;
      }

      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      const contentLength = res.headers['content-length'];
      const total = contentLength ? Number.parseInt(contentLength, 10) : 0;
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
 * Parse a GitHub release response into an UpdateManifest.
 */
async function parseGitHubRelease(
  release: GitHubRelease,
  timeoutMs: number
): Promise<UpdateManifest> {
  const version = release.tag_name.replace(/^v/, '');
  const manifest: UpdateManifest = {
    version,
    releaseDate: release.published_at,
    releaseNotesUrl: release.html_url,
    binaries: {},
  };

  // Build a map of checksum asset URLs keyed by binary name
  const checksumAssets = new Map<string, string>();
  for (const asset of release.assets) {
    if (asset.name.endsWith('.sha256')) {
      const baseName = asset.name.replace('.sha256', '');
      checksumAssets.set(baseName, asset.browser_download_url);
    }
  }

  const binaryPattern = /^rdc-(linux|mac|win)-(x64|arm64)(\.exe)?$/;

  // Find CLI binaries and fetch their checksums
  for (const asset of release.assets) {
    const match = binaryPattern.exec(asset.name);
    if (!match) continue;

    const key = `${match[1]}-${match[2]}` as keyof UpdateManifest['binaries'];
    const sha256 = await fetchChecksumForAsset(asset.name, checksumAssets, timeoutMs);

    manifest.binaries[key] = {
      url: asset.browser_download_url,
      sha256,
    };
  }

  return manifest;
}

/**
 * Fetch the SHA256 checksum for a given binary asset.
 */
async function fetchChecksumForAsset(
  assetName: string,
  checksumAssets: Map<string, string>,
  timeoutMs: number
): Promise<string> {
  const checksumUrl = checksumAssets.get(assetName);
  if (!checksumUrl) return '';

  try {
    const content = await fetchText(checksumUrl, timeoutMs);
    // Format: "hash  filename" or just "hash"
    return content.trim().split(/\s+/)[0] ?? '';
  } catch {
    // If checksum can't be fetched, leave empty (update will be refused)
    return '';
  }
}

/**
 * Fetch the update manifest (Pages primary, GitHub API fallback).
 */
async function fetchManifest(timeoutMs: number = CHECK_TIMEOUT_MS): Promise<UpdateManifest> {
  try {
    return await fetchJson<UpdateManifest>(MANIFEST_URL, timeoutMs);
  } catch {
    // Fallback: GitHub Releases API
    const release = await fetchJson<GitHubRelease>(GITHUB_API_FALLBACK, timeoutMs);
    return parseGitHubRelease(release, timeoutMs);
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
 * Download, verify checksum, and atomically replace the current binary.
 */
async function downloadVerifyAndReplace(
  binaryUrl: string,
  expectedSha256: string,
  onProgress?: (downloaded: number, total: number) => void
): Promise<void> {
  const execPath = process.execPath;
  const execDir = dirname(execPath);
  const tempPath = join(execDir, `.rdc-update-${Date.now()}.tmp`);

  try {
    await downloadFile(binaryUrl, tempPath, onProgress);

    // Verify SHA256 checksum
    const actualHash = await computeSha256(tempPath);
    if (actualHash !== expectedSha256) {
      throw new Error('update.errors.checksumMismatch');
    }

    // Self-replace: rename current -> .old, rename new -> current
    const oldPath = getOldBinaryPath();
    await fs.unlink(oldPath).catch(() => {});
    await fs.rename(execPath, oldPath);
    await fs.rename(tempPath, execPath);

    // Set executable permission (no-op on Windows)
    if (process.platform !== 'win32') {
      await fs.chmod(execPath, 0o755);
    }
  } catch (err) {
    await fs.unlink(tempPath).catch(() => {});
    throw err;
  }
}

/**
 * Create an error UpdateResult.
 */
function errorResult(error: string, toVersion: string = VERSION): UpdateResult {
  return { success: false, fromVersion: VERSION, toVersion, error };
}

/**
 * Perform the self-update.
 */
export async function performUpdate(
  options: { force?: boolean; onProgress?: (downloaded: number, total: number) => void } = {}
): Promise<UpdateResult> {
  const { force = false, onProgress } = options;

  if (!isSEA()) return errorResult('update.errors.notSEA');

  const platformKey = getPlatformKey();
  if (!platformKey) return errorResult('update.errors.unsupportedPlatform');

  const locked = await acquireUpdateLock();
  if (!locked) return errorResult('update.errors.lockFailed');

  try {
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
    if (!binaryInfo) return errorResult('update.errors.noBinary', manifest.version);
    if (!binaryInfo.sha256) return errorResult('update.errors.noChecksum', manifest.version);

    await downloadVerifyAndReplace(binaryInfo.url, binaryInfo.sha256, onProgress);

    return { success: true, fromVersion: VERSION, toVersion: manifest.version };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'update.errors.unknown';
    return errorResult(message);
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
