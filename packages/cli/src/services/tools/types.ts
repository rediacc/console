/** The platforms a pinned tool carries a build for, in the release's own os-arch naming. */
export type ToolPlatform =
  | 'linux-amd64'
  | 'linux-arm64'
  | 'darwin-amd64'
  | 'darwin-arm64'
  | 'windows-amd64'
  | 'windows-arm64';

export interface ToolAsset {
  readonly url: string;
  readonly sha256: string;
}

/** A tool release pinned to one exact version, with a checksummed archive per platform. */
export interface ToolPin {
  readonly version: string;
  readonly assets: Readonly<Record<ToolPlatform, ToolAsset>>;
}
