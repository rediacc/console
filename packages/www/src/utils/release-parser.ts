import type { Platform } from '../config/install';
import { formatBytes } from './format';

export interface DownloadFile {
  platform: Platform;
  arch: 'x64' | 'arm64' | 'armv7l';
  type: 'exe' | 'dmg' | 'AppImage' | 'deb';
  url: string;
  size: string;
  name: string;
}

export interface CLIFile {
  platform: Platform;
  arch: 'x64' | 'arm64';
  url: string;
  size: string;
  name: string;
}

export interface ReleaseData {
  version: string;
  publishedAt: string;
  desktopFiles: DownloadFile[];
  cliFiles: CLIFile[];
}

function detectFilePlatform(filename: string): Platform {
  if (filename.includes('-win-')) return 'windows';
  if (filename.includes('-mac-')) return 'macos';
  return 'linux';
}

function detectArch(filename: string): 'x64' | 'arm64' | 'armv7l' {
  if (filename.includes('-arm64')) return 'arm64';
  if (filename.includes('-armv7l')) return 'armv7l';
  return 'x64';
}

function detectType(filename: string): 'exe' | 'dmg' | 'AppImage' | 'deb' {
  if (filename.endsWith('.exe')) return 'exe';
  if (filename.endsWith('.dmg')) return 'dmg';
  if (filename.endsWith('.AppImage')) return 'AppImage';
  if (filename.endsWith('.deb')) return 'deb';
  return 'AppImage';
}

function detectCLIPlatform(filename: string): Platform {
  if (filename.includes('-win-')) return 'windows';
  if (filename.includes('-mac-')) return 'macos';
  return 'linux';
}

function detectCLIArch(filename: string): 'x64' | 'arm64' {
  if (filename.includes('-arm64')) return 'arm64';
  return 'x64';
}

interface GitHubAsset {
  name: string;
  browser_download_url: string;
  size: number;
}

interface GitHubRelease {
  tag_name: string;
  published_at: string;
  assets: GitHubAsset[];
}

export function parseGitHubRelease(release: GitHubRelease, lang: string): ReleaseData {
  const desktopFiles: DownloadFile[] = release.assets
    .filter(
      (asset) =>
        asset.name.startsWith('rediacc-desktop-') && /\.(exe|dmg|AppImage|deb)$/.test(asset.name)
    )
    .map((asset) => ({
      platform: detectFilePlatform(asset.name),
      arch: detectArch(asset.name),
      type: detectType(asset.name),
      url: asset.browser_download_url,
      size: formatBytes(asset.size),
      name: asset.name,
    }));

  const cliFiles: CLIFile[] = release.assets
    .filter((asset) => asset.name.startsWith('rdc-') && !asset.name.endsWith('.sha256'))
    .map((asset) => ({
      platform: detectCLIPlatform(asset.name),
      arch: detectCLIArch(asset.name),
      url: asset.browser_download_url,
      size: formatBytes(asset.size),
      name: asset.name,
    }));

  return {
    version: release.tag_name.replace('v', ''),
    publishedAt: new Date(release.published_at).toLocaleDateString(lang === 'en' ? 'en-US' : lang, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }),
    desktopFiles,
    cliFiles,
  };
}
