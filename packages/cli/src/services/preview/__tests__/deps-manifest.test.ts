/**
 * The real `fetchManifest` of `rdc preview use` (review 507abc69.2): it reads the preview host's
 * `/cli/manifest.json`, takes the channel from that manifest's binary URLs, and reads the channel's
 * manifest from the release origin. A wiring back to `cli/<name>/manifest.json`, or one that returns
 * the host's own manifest as the R2 one, fails here.
 */
import { WK_RELEASES_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UpdateManifest } from '../../../types/index.js';
import { realPreviewUseDeps } from '../deps.js';
import { previewHostFor } from '../state.js';

const NAME = 'pv-amber-river-stone';
const HOST_MANIFEST = `${previewHostFor(NAME)}/cli/manifest.json`;
const CHANNEL_MANIFEST = `${WK_RELEASES_ORIGIN}/cli/pr-512/manifest.json`;

function manifest(version: string, url: string): UpdateManifest {
  return {
    version,
    releaseDate: '2026-11-26',
    releaseNotesUrl: '',
    binaries: { 'linux-x64': { url, sha256: 'a'.repeat(64) } },
  };
}

function serve(routes: Record<string, UpdateManifest>): string[] {
  const asked: string[] = [];
  vi.stubGlobal('fetch', (input: string | URL) => {
    const url = String(input);
    asked.push(url);
    const body = routes[url];
    return Promise.resolve(
      body
        ? new Response(JSON.stringify(body), { status: 200 })
        : new Response('not found', { status: 404 })
    );
  });
  return asked;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('realPreviewUseDeps().fetchManifest', () => {
  it('reads the host manifest, then the R2 manifest of the channel its binaries name', async () => {
    const r2 = manifest('1.4.0-preview.abc1234', `${WK_RELEASES_ORIGIN}/cli/pr-512/rdc-linux-x64`);
    const asked = serve({
      [HOST_MANIFEST]: manifest('host-copy', `${WK_RELEASES_ORIGIN}/cli/pr-512/rdc-linux-x64`),
      [CHANNEL_MANIFEST]: r2,
    });
    await expect(realPreviewUseDeps().fetchManifest(NAME)).resolves.toEqual(r2);
    expect(asked).toEqual([HOST_MANIFEST, CHANNEL_MANIFEST]);
    expect(asked).not.toContain(`${WK_RELEASES_ORIGIN}/cli/${NAME}/manifest.json`);
  });

  it('refuses a host manifest that points at a non-preview channel, fetching nothing from R2', async () => {
    const asked = serve({
      [HOST_MANIFEST]: manifest('host-copy', `${WK_RELEASES_ORIGIN}/cli/stable/rdc-linux-x64`),
    });
    await expect(realPreviewUseDeps().fetchManifest(NAME)).rejects.toThrow(
      /is not a preview channel under the release origin/
    );
    expect(asked).toEqual([HOST_MANIFEST]);
  });
});
