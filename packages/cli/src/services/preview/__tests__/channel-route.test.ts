/**
 * The route from a preview's word name to the R2 channel its binaries are staged under (PLAN-preview-signer.md
 * C2, N2). A pull-request run stages to `pr-<n>`, so the name alone names no channel: the channel is read off
 * the binary URLs of the manifest the preview host serves.
 */
import { describe, expect, it } from 'vitest';
import type { UpdateManifest } from '../../../types/index.js';
import { previewChannelManifestUrl } from '../build.js';

const ORIGIN = 'https://releases.example';
const NAME = 'pv-amber-river-stone';

function manifest(urls: Record<string, string>): UpdateManifest {
  return {
    version: '1.4.0-preview.abc1234',
    releaseDate: '2026-11-26',
    releaseNotesUrl: '',
    binaries: Object.fromEntries(
      Object.entries(urls).map(([key, url]) => [key, { url, sha256: 'a'.repeat(64) }])
    ),
  };
}

describe('previewChannelManifestUrl', () => {
  it('names the manifest of the pr-<n> channel the binaries sit in, not a channel keyed by the name', () => {
    const url = previewChannelManifestUrl(
      manifest({
        'linux-x64': `${ORIGIN}/cli/pr-512/rdc-linux-x64`,
        'linux-arm64': `${ORIGIN}/cli/pr-512/rdc-linux-arm64`,
      }),
      ORIGIN,
      NAME
    );
    expect(url).toBe(`${ORIGIN}/cli/pr-512/manifest.json`);
    expect(url).not.toContain(NAME);
  });

  it('refuses binaries hosted outside the release origin', () => {
    expect(() =>
      previewChannelManifestUrl(
        manifest({ 'linux-x64': 'https://evil.example/cli/pr-512/rdc-linux-x64' }),
        ORIGIN,
        NAME
      )
    ).toThrow(/not under the release origin/);
  });

  it('refuses binaries that sit in two channels', () => {
    expect(() =>
      previewChannelManifestUrl(
        manifest({
          'linux-x64': `${ORIGIN}/cli/pr-512/rdc-linux-x64`,
          'linux-arm64': `${ORIGIN}/cli/edge/rdc-linux-arm64`,
        }),
        ORIGIN,
        NAME
      )
    ).toThrow(/not under the release origin/);
  });

  it('refuses a manifest with no binary', () => {
    expect(() => previewChannelManifestUrl(manifest({}), ORIGIN, NAME)).toThrow(
      /not under the release origin/
    );
  });
});
