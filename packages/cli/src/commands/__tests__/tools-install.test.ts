import { createHash } from 'node:crypto';
import { mkdtemp, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { buildZip } from '../../services/tools/__tests__/zip-fixture.js';
import {
  installTofu,
  listInstalledTofu,
  tofuInstallPath,
  toolPlatform,
} from '../../services/tools/install.js';
import type { ToolPin, ToolPlatform } from '../../services/tools/types.js';
import { listZipEntries, readZipEntry, ZipError } from '../../services/tools/zip.js';

const dirs: string[] = [];
afterEach(async () => {
  await Promise.all(dirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
});

async function tempDir(): Promise<string> {
  const d = await mkdtemp(join(tmpdir(), 'rdc-tools-'));
  dirs.push(d);
  return d;
}

const BINARY = Buffer.from('#!/bin/sh\necho "OpenTofu v1.10.6"\n');
const PLATFORMS: ToolPlatform[] = [
  'linux-amd64',
  'linux-arm64',
  'darwin-amd64',
  'darwin-arm64',
  'windows-amd64',
  'windows-arm64',
];

function sha(buf: Buffer): string {
  return createHash('sha256').update(buf).digest('hex');
}

function pinFor(
  archive: Buffer,
  overrides: Partial<{ sha256: string; url: string }> = {}
): ToolPin {
  const asset = {
    url: overrides.url ?? 'https://example.invalid/tofu.zip',
    sha256: overrides.sha256 ?? sha(archive),
  };
  return {
    version: '1.10.6',
    assets: Object.fromEntries(PLATFORMS.map((p) => [p, asset])) as ToolPin['assets'],
  };
}

/** A downloader that writes `bytes` to the destination, the way a completed HTTPS fetch would. */
function serve(bytes: Buffer) {
  return async (_url: string, dest: string) => {
    await writeFile(dest, bytes);
  };
}

/** Everything left under the tools dir, relative, so a test can prove nothing was placed. */
async function tree(root: string): Promise<string[]> {
  try {
    return (await readdir(root, { recursive: true })).map(String).sort();
  } catch {
    return [];
  }
}

describe('toolPlatform', () => {
  it('maps Node platform and arch to the release naming', () => {
    expect(toolPlatform('linux', 'x64')).toBe('linux-amd64');
    expect(toolPlatform('linux', 'arm64')).toBe('linux-arm64');
    expect(toolPlatform('darwin', 'arm64')).toBe('darwin-arm64');
    expect(toolPlatform('win32', 'x64')).toBe('windows-amd64');
    expect(toolPlatform('win32', 'arm64')).toBe('windows-arm64');
  });

  it('has no build for other platforms or architectures', () => {
    expect(toolPlatform('freebsd', 'x64')).toBeNull();
    expect(toolPlatform('linux', 'ia32')).toBeNull();
  });
});

describe('installTofu', () => {
  it('verifies the checksum, extracts the binary and places it under opentofu/<version>', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([
      { name: 'LICENSE', data: Buffer.from('MPL-2.0') },
      { name: 'tofu', data: BINARY },
    ]);
    const result = await installTofu(
      {},
      { pin: pinFor(archive), toolsDir, platform: 'linux', arch: 'x64', download: serve(archive) }
    );

    expect(result).toMatchObject({ version: '1.10.6', alreadyInstalled: false });
    expect(result.path).toBe(join(toolsDir, 'opentofu', '1.10.6', 'tofu'));
    expect(await readFile(result.path)).toEqual(BINARY);
    if (process.platform !== 'win32') {
      expect((await stat(result.path)).mode & 0o111).not.toBe(0);
    }
    // The staging directory is gone; only the placed binary remains.
    expect(await tree(toolsDir)).toEqual(['opentofu', 'opentofu/1.10.6', 'opentofu/1.10.6/tofu']);
  });

  it('refuses a checksum mismatch, deletes the download and places nothing', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'tofu', data: BINARY }]);
    const tampered = buildZip([{ name: 'tofu', data: Buffer.from('evil') }]);

    await expect(
      installTofu(
        {},
        {
          pin: pinFor(archive),
          toolsDir,
          platform: 'linux',
          arch: 'x64',
          download: serve(tampered),
        }
      )
    ).rejects.toThrow(/Checksum mismatch.*nothing was installed/);
    expect(await tree(toolsDir)).toEqual([]);
  });

  it('leaves no binary when the download is interrupted', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'tofu', data: BINARY }]);
    const interrupted = async (_url: string, dest: string) => {
      await writeFile(dest, archive.subarray(0, archive.length >> 1));
      throw new Error('socket hang up');
    };

    await expect(
      installTofu(
        {},
        { pin: pinFor(archive), toolsDir, platform: 'linux', arch: 'x64', download: interrupted }
      )
    ).rejects.toThrow('socket hang up');
    expect(await tree(toolsDir)).toEqual([]);
  });

  it('leaves no binary when a truncated download completes without an error', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'tofu', data: BINARY }]);
    await expect(
      installTofu(
        {},
        {
          pin: pinFor(archive),
          toolsDir,
          platform: 'linux',
          arch: 'x64',
          download: serve(archive.subarray(0, archive.length - 10)),
        }
      )
    ).rejects.toThrow(/Checksum mismatch/);
    expect(await tree(toolsDir)).toEqual([]);
  });

  it('installs tofu.exe on Windows, from the windows asset', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([
      { name: 'tofu', data: Buffer.from('not this one') },
      { name: 'tofu.exe', data: BINARY },
    ]);
    const pin = pinFor(archive);
    const seen: string[] = [];
    const result = await installTofu(
      {},
      {
        pin: {
          ...pin,
          assets: { ...pin.assets, 'linux-amd64': { url: 'https://x/linux', sha256: 'f' } },
        },
        toolsDir,
        platform: 'win32',
        arch: 'x64',
        download: async (url, dest) => {
          seen.push(url);
          await writeFile(dest, archive);
        },
      }
    );
    expect(seen).toEqual(['https://example.invalid/tofu.zip']);
    expect(result.path).toBe(join(toolsDir, 'opentofu', '1.10.6', 'tofu.exe'));
    expect(await readFile(result.path)).toEqual(BINARY);
    expect(tofuInstallPath('1.10.6', { toolsDir: 'C:\\t', platform: 'win32' })).toMatch(
      /tofu\.exe$/
    );
  });

  it('refuses an archive without the binary, placing nothing', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'README.md', data: Buffer.from('x') }]);
    await expect(
      installTofu(
        {},
        { pin: pinFor(archive), toolsDir, platform: 'linux', arch: 'x64', download: serve(archive) }
      )
    ).rejects.toThrow(/archive cannot be used: no tofu entry/);
    expect(await tree(toolsDir)).toEqual([]);
  });

  it('refuses a non-HTTPS URL before downloading', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'tofu', data: BINARY }]);
    let called = false;
    await expect(
      installTofu(
        {},
        {
          pin: pinFor(archive, { url: 'http://example.invalid/tofu.zip' }),
          toolsDir,
          platform: 'linux',
          arch: 'x64',
          download: () => {
            called = true;
            return Promise.resolve();
          },
        }
      )
    ).rejects.toThrow(/non-HTTPS/);
    expect(called).toBe(false);
  });

  it('is idempotent, and --force reinstalls', async () => {
    const toolsDir = await tempDir();
    const archive = buildZip([{ name: 'tofu', data: BINARY }]);
    let downloads = 0;
    const deps = {
      pin: pinFor(archive),
      toolsDir,
      platform: 'linux' as const,
      arch: 'x64',
      download: async (_u: string, dest: string) => {
        downloads++;
        await writeFile(dest, archive);
      },
    };
    await installTofu({}, deps);
    expect((await installTofu({}, deps)).alreadyInstalled).toBe(true);
    expect(downloads).toBe(1);
    expect((await installTofu({ force: true }, deps)).alreadyInstalled).toBe(false);
    expect(downloads).toBe(2);
    expect(await listInstalledTofu({ toolsDir, platform: 'linux' })).toEqual([
      { version: '1.10.6', path: join(toolsDir, 'opentofu', '1.10.6', 'tofu') },
    ]);
  });

  it('refuses a platform with no pinned build', async () => {
    await expect(
      installTofu({}, { toolsDir: await tempDir(), platform: 'freebsd', arch: 'x64' })
    ).rejects.toThrow(/No pinned OpenTofu build exists for freebsd\/x64/);
  });
});

describe('zip reader', () => {
  it('reads stored and deflated entries by exact name', () => {
    const zip = buildZip([
      { name: 'a', data: Buffer.from('stored'), store: true },
      { name: 'dir/tofu', data: Buffer.from('nested') },
      { name: 'tofu', data: Buffer.from('deflated'.repeat(100)) },
    ]);
    expect(listZipEntries(zip)).toEqual(['a', 'dir/tofu', 'tofu']);
    expect(readZipEntry(zip, 'a')?.toString()).toBe('stored');
    expect(readZipEntry(zip, 'tofu')?.toString()).toBe('deflated'.repeat(100));
    expect(readZipEntry(zip, 'missing')).toBeNull();
  });

  it('refuses an entry whose CRC-32 does not match', () => {
    const zip = buildZip([{ name: 'tofu', data: Buffer.from('payload'), store: true }]);
    // Flip a byte of the stored payload (after the 30-byte local header and the 4-byte name).
    zip[34] ^= 0xff;
    expect(() => readZipEntry(zip, 'tofu')).toThrow(ZipError);
  });

  it('refuses something that is not a zip', () => {
    expect(() => readZipEntry(Buffer.from('not a zip at all, just text'), 'tofu')).toThrow(
      /end-of-central-directory/
    );
  });
});
