/**
 * The live release host of `rdc server bundle --with-cli` (deps-offline.ts), driven through a stubbed global
 * fetch so the real timeout, body-less and stream paths run; every other server test injects fakes.ts, which
 * replaces the whole ReleaseHost. Also pins `--with-cli`'s refusal of an empty value.
 */

import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../machine/machine-connection.js', () => ({ machineConnections: {} }));
vi.mock('../../update/updater.js', () => ({ getReleasesBaseUrl: () => 'https://rel.test' }));
vi.mock('../../../utils/platform.js', () => ({ isDevBuild: () => false }));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

import { parseCliPlatforms } from '../bundle/cli-binaries.js';
import { release } from '../deps-offline.js';

const URL = 'https://rel.test/v1.0.0/rdc-linux-x64';
let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'rdc-release-host-'));
});
afterEach(() => {
  vi.unstubAllGlobals();
  rmSync(dir, { recursive: true, force: true });
});

/** A body that yields `first`, then errors, like a connection dropped mid-download. */
function brokenBody(first: string): ReadableStream<Uint8Array> {
  let sent = false;
  return new ReadableStream({
    pull(controller) {
      if (!sent) {
        sent = true;
        controller.enqueue(new TextEncoder().encode(first));
        return;
      }
      controller.error(new Error('socket hang up'));
    },
  });
}

describe('release host', () => {
  it('reads the text of a 200 reply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('abc  rdc')));
    await expect(release.fetchText(`${URL}.sha256`)).resolves.toBe('abc  rdc');
  });

  it('streams a 200 body to the destination', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('binary-bytes')));
    const dest = join(dir, 'rdc');
    await release.download(URL, dest);
    expect(readFileSync(dest, 'utf8')).toBe('binary-bytes');
  });

  it('names the url and the status of a non-ok reply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 404 })));
    await expect(release.fetchText(URL)).rejects.toThrow(/cliDownloadFailed.*HTTP 404/);
  });

  it('refuses a reply without a body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(release.download(URL, join(dir, 'rdc'))).rejects.toThrow(/cliDownloadFailed/);
  });

  it('names the url when fetch itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNRESET')));
    await expect(release.fetchText(URL)).rejects.toThrow(/cliDownloadFailed.*ECONNRESET/);
  });

  it('bounds every request by the 600 s timeout and names the url when it fires', async () => {
    const timeout = vi
      .spyOn(AbortSignal, 'timeout')
      .mockReturnValue(
        AbortSignal.abort(new DOMException('timed out after 600000 ms', 'TimeoutError'))
      );
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        init?.signal?.aborted
          ? Promise.reject(init.signal.reason)
          : Promise.resolve(new Response('late'))
      )
    );
    try {
      await expect(release.fetchText(URL)).rejects.toThrow(
        /cliDownloadFailed.*timed out after 600000 ms/
      );
      expect(timeout).toHaveBeenCalledWith(600_000);
    } finally {
      timeout.mockRestore();
    }
    // Control: without the abort the same stub answers.
    await expect(release.fetchText(URL)).resolves.toBe('late');
  });

  it('names the url and removes the partial file when the body fails mid-stream', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(brokenBody('part'))));
    const dest = join(dir, 'rdc');
    await expect(release.download(URL, dest)).rejects.toThrow(
      /cliDownloadFailed.*rdc-linux-x64.*socket hang up/
    );
    expect(existsSync(dest)).toBe(false);
  });
});

describe('parseCliPlatforms', () => {
  it.each(['', ' ', ',', ' , ,'])('refuses the empty value %j', (value) => {
    expect(() => parseCliPlatforms(value)).toThrow(/cliUnknownPlatform/);
  });

  it('control: a named platform parses and a repeat collapses', () => {
    expect(parseCliPlatforms('linux-x64, linux-x64,mac-arm64')).toEqual(['linux-x64', 'mac-arm64']);
  });
});
