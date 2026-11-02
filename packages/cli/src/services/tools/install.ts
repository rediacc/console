/**
 * Installs pinned, checksum-verified local tools into rdc's tools directory.
 *
 * The only tool is OpenTofu. Its archive is downloaded over HTTPS into a private staging directory under the tools root, its SHA-256 is checked against the pin compiled into rdc before a single byte is extracted, the binary is read out of the zip in-process, and it reaches `<toolsDir>/opentofu/<version>/tofu(.exe)` by one rename. Any failure removes the staging directory, so an interrupted or tampered download leaves nothing behind. Terraform is never installed (BUSL); a user-installed one on PATH is only ever found, by the executor.
 */

import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { getStateDir } from '@rediacc/shared/paths';
import { t } from '../../i18n/index.js';
import { computeSha256, downloadFile } from '../update/updater.js';
import { OPENTOFU_PIN } from './pins.js';
import type { ToolPin, ToolPlatform } from './types.js';
import { readZipEntry, ZipError } from './zip.js';

export const TOOL_NAMES = ['tofu'] as const;
type ToolName = (typeof TOOL_NAMES)[number];

/** Root of rdc-managed tools: `<stateDir>/tools` (XDG state on Linux, LOCALAPPDATA on Windows). */
function getToolsDir(): string {
  return join(getStateDir(), 'tools');
}

/** The release platform for a Node platform/arch pair, or null when no build exists for it. */
export function toolPlatform(
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch
): ToolPlatform | null {
  const os = { linux: 'linux', darwin: 'darwin', win32: 'windows' }[platform as string];
  const cpu = { x64: 'amd64', arm64: 'arm64' }[arch];
  if (!os || !cpu) return null;
  return `${os}-${cpu}` as ToolPlatform;
}

/** `tofu` or `tofu.exe`. */
function tofuExecutableName(platform: NodeJS.Platform = process.platform): string {
  return platform === 'win32' ? 'tofu.exe' : 'tofu';
}

/** Where the rdc-managed OpenTofu of `version` lives (whether or not it is installed). */
export function tofuInstallPath(
  version: string = OPENTOFU_PIN.version,
  options: { toolsDir?: string; platform?: NodeJS.Platform } = {}
): string {
  return join(
    options.toolsDir ?? getToolsDir(),
    'opentofu',
    version,
    tofuExecutableName(options.platform)
  );
}

export interface InstallDeps {
  pin?: ToolPin;
  toolsDir?: string;
  platform?: NodeJS.Platform;
  arch?: string;
  download?: (url: string, dest: string) => Promise<void>;
  onDownloadStart?: (info: { version: string; platform: ToolPlatform; url: string }) => void;
}

export interface InstallResult {
  tool: ToolName;
  version: string;
  path: string;
  alreadyInstalled: boolean;
}

async function exists(path: string): Promise<boolean> {
  try {
    await fs.access(path);
    return true;
  } catch {
    return false;
  }
}

/** Refuse the archive unless its SHA-256 is the pinned one; the caller's cleanup deletes it. */
async function verifySha256(archive: string, url: string, expected: string): Promise<void> {
  const actual = await computeSha256(archive);
  if (actual !== expected.toLowerCase()) {
    throw new Error(t('commands.tools.errors.checksumMismatch', { url, expected, actual }));
  }
}

/** The bytes of `name` from the zip at `archive`, or an i18n error when it is unusable. */
async function extractEntry(archive: string, name: string): Promise<Buffer> {
  let binary: Buffer | null;
  try {
    binary = readZipEntry(await fs.readFile(archive), name);
  } catch (err) {
    if (err instanceof ZipError) {
      throw new Error(t('commands.tools.errors.badArchive', { reason: err.message }));
    }
    throw err;
  }
  if (!binary) {
    throw new Error(t('commands.tools.errors.badArchive', { reason: `no ${name} entry` }));
  }
  return binary;
}

/** Install the pinned OpenTofu. Idempotent: a present pinned version is left alone unless `force`. */
export async function installTofu(
  options: { force?: boolean } = {},
  deps: InstallDeps = {}
): Promise<InstallResult> {
  const pin = deps.pin ?? OPENTOFU_PIN;
  const platform = deps.platform ?? process.platform;
  const arch = deps.arch ?? process.arch;
  const toolsDir = deps.toolsDir ?? getToolsDir();
  const download = deps.download ?? ((url: string, dest: string) => downloadFile(url, dest));

  const key = toolPlatform(platform, arch);
  if (!key) throw new Error(t('commands.tools.errors.unsupportedPlatform', { platform, arch }));
  const asset = pin.assets[key];
  if (!asset.url.startsWith('https://')) {
    throw new Error(t('commands.tools.errors.insecureUrl', { url: asset.url }));
  }

  const exeName = tofuExecutableName(platform);
  const finalPath = tofuInstallPath(pin.version, { toolsDir, platform });
  if (!options.force && (await exists(finalPath))) {
    return { tool: 'tofu', version: pin.version, path: finalPath, alreadyInstalled: true };
  }

  await fs.mkdir(toolsDir, { recursive: true, mode: 0o700 });
  // Staging sits under the tools root so the final rename never crosses a filesystem.
  const staging = await fs.mkdtemp(join(toolsDir, '.staging-'));
  try {
    const archive = join(staging, 'download.zip');
    deps.onDownloadStart?.({ version: pin.version, platform: key, url: asset.url });
    await download(asset.url, archive);
    await verifySha256(archive, asset.url, asset.sha256);
    const binary = await extractEntry(archive, exeName);

    const staged = join(staging, exeName);
    await fs.writeFile(staged, binary, { mode: 0o755 });
    const versionDir = join(toolsDir, 'opentofu', pin.version);
    await fs.mkdir(versionDir, { recursive: true });
    await fs.rename(staged, finalPath);
  } finally {
    await fs.rm(staging, { recursive: true, force: true });
  }
  return { tool: 'tofu', version: pin.version, path: finalPath, alreadyInstalled: false };
}

/** The OpenTofu versions present in rdc's tools directory, newest directory name last. */
export async function listInstalledTofu(
  options: { toolsDir?: string; platform?: NodeJS.Platform } = {}
): Promise<{ version: string; path: string }[]> {
  const root = join(options.toolsDir ?? getToolsDir(), 'opentofu');
  let versions: string[];
  try {
    versions = await fs.readdir(root);
  } catch {
    return [];
  }
  const found: { version: string; path: string }[] = [];
  for (const version of versions.sort()) {
    const path = tofuInstallPath(version, options);
    if (await exists(path)) found.push({ version, path });
  }
  return found;
}
