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

export function detectFilePlatform(filename: string): Platform {
  if (filename.includes('-win-')) return 'windows';
  if (filename.includes('-mac-')) return 'macos';
  return 'linux';
}

export function detectArch(filename: string): 'x64' | 'arm64' | 'armv7l' {
  if (filename.includes('-arm64')) return 'arm64';
  if (filename.includes('-armv7l')) return 'armv7l';
  return 'x64';
}

export function detectType(filename: string): 'exe' | 'dmg' | 'AppImage' | 'deb' {
  if (filename.endsWith('.exe')) return 'exe';
  if (filename.endsWith('.dmg')) return 'dmg';
  if (filename.endsWith('.AppImage')) return 'AppImage';
  if (filename.endsWith('.deb')) return 'deb';
  return 'AppImage';
}

export function detectCLIPlatform(filename: string): Platform {
  if (filename.includes('-win-')) return 'windows';
  if (filename.includes('-mac-')) return 'macos';
  return 'linux';
}

export function detectCLIArch(filename: string): 'x64' | 'arm64' {
  if (filename.includes('-arm64')) return 'arm64';
  return 'x64';
}

export function parseGitHubRelease(release: any, lang: string): ReleaseData {
  const desktopFiles: DownloadFile[] = release.assets
    .filter((asset: any) =>
      asset.name.startsWith('rediacc-desktop-') &&
      /\.(exe|dmg|AppImage|deb)$/.test(asset.name)
    )
    .map((asset: any) => ({
      platform: detectFilePlatform(asset.name),
      arch: detectArch(asset.name),
      type: detectType(asset.name),
      url: asset.browser_download_url,
      size: formatBytes(asset.size),
      name: asset.name
    }));

  const cliFiles: CLIFile[] = release.assets
    .filter((asset: any) => asset.name.startsWith('rdc-') && !asset.name.endsWith('.sha256'))
    .map((asset: any) => ({
      platform: detectCLIPlatform(asset.name),
      arch: detectCLIArch(asset.name),
      url: asset.browser_download_url,
      size: formatBytes(asset.size),
      name: asset.name
    }));

  return {
    version: release.tag_name.replace('v', ''),
    publishedAt: new Date(release.published_at).toLocaleDateString(lang === 'en' ? 'en-US' : lang, {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    }),
    desktopFiles,
    cliFiles
  };
}
