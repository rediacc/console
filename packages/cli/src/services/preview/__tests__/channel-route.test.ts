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

  it('names the manifest of a channel keyed by the preview name, the layout N2 moves to', () => {
    expect(
      previewChannelManifestUrl(
        manifest({ 'linux-x64': `${ORIGIN}/cli/${NAME}/rdc-linux-x64` }),
        ORIGIN,
        NAME
      )
    ).toBe(`${ORIGIN}/cli/${NAME}/manifest.json`);
  });

  it('refuses binaries hosted outside the release origin, naming their directory', () => {
    expect(() =>
      previewChannelManifestUrl(
        manifest({ 'linux-x64': 'https://evil.example/cli/pr-512/rdc-linux-x64' }),
        ORIGIN,
        NAME
      )
    ).toThrow(
      'Preview pv-amber-river-stone publishes its builds at https://evil.example/cli/pr-512, which is not a preview channel under the release origin.'
    );
  });

  // Review 507abc69.3: the host's manifest picks the channel, so it may only pick a preview channel.
  it.each([
    ['the edge channel', `${ORIGIN}/cli/edge/rdc-linux-x64`],
    ['the stable channel', `${ORIGIN}/cli/stable/rdc-linux-x64`],
    ['another preview name', `${ORIGIN}/cli/pv-other-word-set/rdc-linux-x64`],
    ['a pr channel with no number', `${ORIGIN}/cli/pr-/rdc-linux-x64`],
    ['the cli directory itself', `${ORIGIN}/cli/rdc-linux-x64`],
  ])('refuses binaries staged under %s', (_label, url) => {
    expect(() => previewChannelManifestUrl(manifest({ 'linux-x64': url }), ORIGIN, NAME)).toThrow(
      /is not a preview channel under the release origin/
    );
  });

  it('refuses the name branch when the name is no preview name', () => {
    expect(() =>
      previewChannelManifestUrl(
        manifest({ 'linux-x64': `${ORIGIN}/cli/edge/rdc-linux-x64` }),
        ORIGIN,
        'edge'
      )
    ).toThrow(/is not a preview channel under the release origin/);
  });

  // Review 507abc69.4: a dot segment, a deeper path or a query under cli/ is no single channel segment.
  it.each([
    ['a dot segment', `${ORIGIN}/cli/../x/rdc-linux-x64`],
    ['a dot segment after the channel', `${ORIGIN}/cli/pr-512/../rdc-linux-x64`],
    ['a deeper path', `${ORIGIN}/cli/pr-512/nested/rdc-linux-x64`],
    ['a query', `${ORIGIN}/cli/pr-512?x=/rdc-linux-x64`],
  ])('refuses a binary URL with %s', (_label, url) => {
    expect(() => previewChannelManifestUrl(manifest({ 'linux-x64': url }), ORIGIN, NAME)).toThrow(
      /is not a preview channel under the release origin/
    );
  });

  // Review 507abc69.1: two directories, both under the origin, are reported as two directories, not as off-origin.
  it('refuses binaries that sit in two channels, naming both', () => {
    expect(() =>
      previewChannelManifestUrl(
        manifest({
          'linux-x64': `${ORIGIN}/cli/pr-512/rdc-linux-x64`,
          'linux-arm64': `${ORIGIN}/cli/pr-513/rdc-linux-arm64`,
        }),
        ORIGIN,
        NAME
      )
    ).toThrow(
      `Preview pv-amber-river-stone serves binaries from more than one directory (${ORIGIN}/cli/pr-512, ${ORIGIN}/cli/pr-513), so no single channel can be read from it.`
    );
  });

  it('refuses a manifest with no binary with its own message, not an empty URL', () => {
    expect(() => previewChannelManifestUrl(manifest({}), ORIGIN, NAME)).toThrow(
      'Preview pv-amber-river-stone serves a CLI manifest with no binary, so no channel can be read from it.'
    );
  });
});
