import type { Platform } from '../config/install';
import { formatBytes } from './format';

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
  cliFiles: CLIFile[];
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
    cliFiles,
  };
}
