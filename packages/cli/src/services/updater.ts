import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { get as httpGet } from 'node:http';
import { get as httpsGet } from 'node:https';
import { dirname, join } from 'node:path';
import { type UpdateManifest } from '../types/index.js';
import {
  acquireUpdateLock,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  STAGED_UPDATE_DIR,
} from '../utils/platform.js';
import { VERSION } from '../version.js';
import { telemetryService } from './telemetry.js';
import { getStagedBinaryPath, readUpdateState, writeUpdateState } from './update-state.js';

const MANIFEST_URL = 'https://www.rediacc.com/cli/manifest.json';
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
export function downloadFile(
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
export async function computeSha256(filePath: string): Promise<string> {
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
 * Fetch the update manifest from the primary manifest URL.
 */
export async function fetchManifest(timeoutMs: number = CHECK_TIMEOUT_MS): Promise<UpdateManifest> {
  return await fetchJson<UpdateManifest>(MANIFEST_URL, timeoutMs);
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
 * Thrown when binary replacement fails because the executable is locked (EBUSY/EPERM/ETXTBSY).
 * The downloaded binary has been staged for application on next launch.
 */
class BinaryBusyError extends Error {
  constructor(public readonly stagedVersion: string) {
    super('update.errors.binaryBusy');
  }
}

/**
 * Stage an already-downloaded binary for application on next launch.
 * Used as fallback when direct replacement fails (binary locked).
 */
async function stageDownloadedBinary(
  tempPath: string,
  sha256: string,
  version: string,
  platformKey: string,
  releaseNotesUrl?: string
): Promise<void> {
  await fs.mkdir(STAGED_UPDATE_DIR, { recursive: true });
  const stagedPath = getStagedBinaryPath(version);
  await fs.rename(tempPath, stagedPath);
  if (process.platform !== 'win32') {
    await fs.chmod(stagedPath, 0o755);
  }

  const state = await readUpdateState();
  state.pendingUpdate = {
    version,
    stagedPath,
    sha256,
    platformKey,
    downloadedAt: new Date().toISOString(),
    releaseNotesUrl,
  };
  await writeUpdateState(state);
}

/**
 * Download, verify checksum, and atomically replace the current binary.
 */
async function downloadVerifyAndReplace(
  binaryUrl: string,
  expectedSha256: string,
  stagingInfo: { version: string; platformKey: string; releaseNotesUrl?: string },
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
    try {
      await fs.rename(tempPath, execPath);
    } catch (renameErr) {
      // Rollback: restore old binary so CLI isn't broken
      await fs.rename(oldPath, execPath).catch(() => {});
      throw renameErr;
    }

    // Set executable permission (no-op on Windows)
    if (process.platform !== 'win32') {
      await fs.chmod(execPath, 0o755);
    }
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === 'EBUSY' || code === 'EPERM' || code === 'ETXTBSY') {
      // Binary is locked — stage for next launch instead
      await stageDownloadedBinary(
        tempPath,
        expectedSha256,
        stagingInfo.version,
        stagingInfo.platformKey,
        stagingInfo.releaseNotesUrl
      );
      throw new BinaryBusyError(stagingInfo.version);
    }
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
 * Handle caught errors during update — return appropriate UpdateResult.
 */
function handleUpdateError(err: unknown): UpdateResult {
  if (err instanceof BinaryBusyError) {
    telemetryService.trackEvent('update.manual.staged', { version: err.stagedVersion });
    return {
      success: true,
      fromVersion: VERSION,
      toVersion: err.stagedVersion,
      error: 'update.errors.binaryBusy',
    };
  }
  const message = err instanceof Error ? err.message : 'update.errors.unknown';
  telemetryService.trackEvent('update.manual.failed', { error: message });
  return errorResult(message);
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

  const releaseLock = await acquireUpdateLock();
  if (!releaseLock) return errorResult('update.errors.lockFailed');

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

    await downloadVerifyAndReplace(
      binaryInfo.url,
      binaryInfo.sha256,
      { version: manifest.version, platformKey, releaseNotesUrl: manifest.releaseNotesUrl },
      onProgress
    );

    telemetryService.trackEvent('update.manual.success', { from: VERSION, to: manifest.version });
    return { success: true, fromVersion: VERSION, toVersion: manifest.version };
  } catch (err) {
    return handleUpdateError(err);
  } finally {
    await releaseLock();
  }
}
