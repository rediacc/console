/**
 * `rdc server bundle --with-cli` (PLAN-enterprise-tenants C11): the CLI binaries of the bundle's own
 * version come from the release host, are checked against its `.sha256` file, and land under
 * `cli/<platform>/` with a sum line and a manifest entry each. The host is the fake in fakes.ts.
 */

import { createHash } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ version: '1.0.0' }));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../../version.js', () => ({
  get VERSION() {
    return m.version;
  },
}));
vi.mock('../../config/config-resources.js', () => ({ configService: {} }));

import { serverBundle } from '../bundle/build.js';
import { BundleError, parseManifest, parseSums } from '../bundle/manifest.js';
import { verifyBundle } from '../bundle/verify.js';
import { FAKE_RELEASE_BASE, makeFake, signerOf } from './fakes.js';

const OUT = '/bundles/acme';
const sha = (text: string) => createHash('sha256').update(text).digest('hex');

/** A release host serving `rdc-<platform>` and its `.sha256` for each name; `lie` serves a wrong sum. */
function release(version: string, names: string[], lie?: string): Record<string, string> {
  const served: Record<string, string> = {};
  for (const name of names) {
    const url = `${FAKE_RELEASE_BASE}/v${version}/${name}`;
    served[url] = `bytes-of-${name}`;
    served[`${url}.sha256`] =
      `${name === lie ? '0'.repeat(64) : sha(`bytes-of-${name}`)}  ${name}\n`;
  }
  return served;
}

function bundleWith(withCli: string | undefined, served: Record<string, string>) {
  const fake = makeFake({ release: served });
  return { fake, run: () => serverBundle(fake.deps, { out: OUT, tag: '1', withCli }) };
}

describe('server bundle --with-cli', () => {
  it('downloads each platform, verifies it and records it in the sums and the manifest', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith(
      'linux-x64,win-arm64',
      release('1.0.0', ['rdc-linux-x64', 'rdc-win-arm64.exe'])
    );
    const manifest = await run();
    expect(manifest.cli).toEqual([
      { platform: 'linux-x64', file: 'cli/linux-x64/rdc', sha256: sha('bytes-of-rdc-linux-x64') },
      {
        platform: 'win-arm64',
        file: 'cli/win-arm64/rdc.exe',
        sha256: sha('bytes-of-rdc-win-arm64.exe'),
      },
    ]);
    expect(fake.files[`${OUT}/cli/linux-x64/rdc`]).toBe('bytes-of-rdc-linux-x64');
    expect(fake.files[`${OUT}/cli/win-arm64/rdc.exe`]).toBe('bytes-of-rdc-win-arm64.exe');
    expect(fake.calls).toContain(`release GET ${FAKE_RELEASE_BASE}/v1.0.0/rdc-win-arm64.exe`);
    expect(parseSums(fake.files[`${OUT}/SHA256SUMS`]).map((s) => s.file)).toEqual(
      expect.arrayContaining(['cli/linux-x64/rdc', 'cli/win-arm64/rdc.exe'])
    );
    expect(parseManifest(fake.files[`${OUT}/manifest.json`]).cli).toEqual(manifest.cli);
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).resolves.toEqual(
      manifest
    );
  });

  it('verify refuses a CLI binary changed after bundling', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith('mac-arm64', release('1.0.0', ['rdc-mac-arm64']));
    await run();
    fake.files[`${OUT}/cli/mac-arm64/rdc`] = 'tampered';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*cli\/mac-arm64\/rdc/s
    );
  });

  it('refuses a download whose sha256 differs from the release checksum, and writes no records', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith(
      'linux-x64,mac-x64',
      release('1.0.0', ['rdc-linux-x64', 'rdc-mac-x64'], 'rdc-mac-x64')
    );
    await expect(run()).rejects.toThrow(/cliSha256Mismatch.*mac-x64/s);
    expect(fake.files[`${OUT}/manifest.json`]).toBeUndefined();
    expect(fake.files[`${OUT}/SHA256SUMS`]).toBeUndefined();
  });

  it('refuses a dev build, before docker or the release host is touched', async () => {
    m.version = '0.0.0-dev';
    const { fake, run } = bundleWith('linux-x64', release('0.0.0-dev', ['rdc-linux-x64']));
    await expect(run()).rejects.toThrow(/cliDevBuild/);
    expect(fake.calls).toEqual([]);
  });

  it('refuses an unknown platform by name, before docker or the release host is touched', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith('linux-x64,beos-x64', release('1.0.0', ['rdc-linux-x64']));
    await expect(run()).rejects.toThrow(/cliUnknownPlatform.*beos-x64/s);
    expect(fake.calls).toEqual([]);
  });

  it('names a checksum file that holds no sha256', async () => {
    m.version = '1.0.0';
    const served = release('1.0.0', ['rdc-linux-x64']);
    served[`${FAKE_RELEASE_BASE}/v1.0.0/rdc-linux-x64.sha256`] = '<html>not found</html>';
    await expect(bundleWith('linux-x64', served).run()).rejects.toThrow(/cliChecksumFile/);
  });

  it('fails with the release host answer instead of writing a partial bundle', async () => {
    m.version = '1.0.0';
    await expect(bundleWith('linux-x64', {}).run()).rejects.toThrow(/cliDownloadFailed.*404/s);
  });

  it('CONTROL: without --with-cli the manifest has no cli entry and only the models are fetched from the host', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith(undefined, {});
    const manifest = await run();
    expect(manifest.cli).toBeUndefined();
    expect(fake.calls.some((c) => c.startsWith('release') && !c.includes('/models/'))).toBe(false);
    expect(JSON.parse(fake.files[`${OUT}/manifest.json`])).not.toHaveProperty('cli');
  });

  it('refuses a cli or models entry that is not a list, naming the field', async () => {
    m.version = '1.0.0';
    const { fake, run } = bundleWith(undefined, {});
    await run();
    const good = JSON.parse(fake.files[`${OUT}/manifest.json`]);
    // CONTROL: the unchanged manifest parses, so the refusals below are about the field.
    expect(() => parseManifest(JSON.stringify(good))).not.toThrow();
    for (const field of ['cli', 'models']) {
      const refused = () => parseManifest(JSON.stringify({ ...good, [field]: 'not-a-list' }));
      // A BundleError naming the field, not the TypeError an unchecked `.map` would throw.
      expect(refused).toThrow(BundleError);
      expect(refused).toThrow(field);
    }
  });
});
