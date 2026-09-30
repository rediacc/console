import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `publicFileExists` decides at import time whether to memoize (`import.meta.env.PROD`),
 * so each test imports a FRESH copy of the module through vi.resetModules() after setting
 * the env it wants to exercise.
 */
async function loadFresh() {
  vi.resetModules();
  return import('../media-url.ts');
}

const KEY = 'videos/solutions/en/home.mp4';
const LOCAL = `/assets/${KEY}`;

let publicDir: string;
const savedCdn = process.env.PUBLIC_VIDEO_CDN_BASE_URL;

beforeEach(() => {
  publicDir = fs.mkdtempSync(path.join(os.tmpdir(), 'www-public-'));
  delete process.env.PUBLIC_VIDEO_CDN_BASE_URL;
  vi.stubEnv('PROD', false);
});

afterEach(() => {
  fs.rmSync(publicDir, { recursive: true, force: true });
  if (savedCdn === undefined) delete process.env.PUBLIC_VIDEO_CDN_BASE_URL;
  else process.env.PUBLIC_VIDEO_CDN_BASE_URL = savedCdn;
  vi.unstubAllEnvs();
});

function plant(rel: string): void {
  const abs = path.join(publicDir, rel);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, 'x');
}

describe('cdnBaseUrl', () => {
  it('uses the manifest base when the env var is unset', async () => {
    const { cdnBaseUrl } = await loadFresh();
    expect(cdnBaseUrl('https://media.rediacc.com')).toBe('https://media.rediacc.com');
  });

  it('lets PUBLIC_VIDEO_CDN_BASE_URL override the manifest base', async () => {
    process.env.PUBLIC_VIDEO_CDN_BASE_URL = 'https://staging.example';
    const { cdnBaseUrl } = await loadFresh();
    expect(cdnBaseUrl('https://media.rediacc.com')).toBe('https://staging.example');
  });

  it('strips a trailing slash from either source', async () => {
    const { cdnBaseUrl } = await loadFresh();
    expect(cdnBaseUrl('https://media.rediacc.com/')).toBe('https://media.rediacc.com');
    process.env.PUBLIC_VIDEO_CDN_BASE_URL = 'https://staging.example//';
    const fresh = await loadFresh();
    expect(fresh.cdnBaseUrl('ignored')).toBe('https://staging.example');
  });

  it('treats an empty env var as unset', async () => {
    process.env.PUBLIC_VIDEO_CDN_BASE_URL = '';
    const { cdnBaseUrl } = await loadFresh();
    expect(cdnBaseUrl('https://media.rediacc.com')).toBe('https://media.rediacc.com');
  });
});

describe('resolveMediaUrl', () => {
  it('returns the local path when the file is checked out', async () => {
    plant(LOCAL);
    const { resolveMediaUrl } = await loadFresh();
    expect(
      resolveMediaUrl({
        localPath: LOCAL,
        cdnKey: KEY,
        cdnBase: 'https://media.rediacc.com',
        publicDir,
      })
    ).toBe(LOCAL);
  });

  it('falls back to the CDN when the file is absent', async () => {
    const { resolveMediaUrl } = await loadFresh();
    expect(
      resolveMediaUrl({
        localPath: LOCAL,
        cdnKey: KEY,
        cdnBase: 'https://media.rediacc.com',
        publicDir,
      })
    ).toBe(`https://media.rediacc.com/${KEY}`);
  });

  it('does not let a directory of the same name count as a file', async () => {
    fs.mkdirSync(path.join(publicDir, LOCAL), { recursive: true });
    const { resolveMediaUrl } = await loadFresh();
    expect(
      resolveMediaUrl({
        localPath: LOCAL,
        cdnKey: KEY,
        cdnBase: 'https://media.rediacc.com',
        publicDir,
      })
    ).toBe(`https://media.rediacc.com/${KEY}`);
  });

  it('tolerates a leading slash on the cdn key', async () => {
    const { resolveMediaUrl } = await loadFresh();
    expect(
      resolveMediaUrl({ localPath: LOCAL, cdnKey: `/${KEY}`, cdnBase: 'https://cdn', publicDir })
    ).toBe(`https://cdn/${KEY}`);
  });
});

describe('publicFileExists memo', () => {
  it('stays live outside production so a freshly written file is seen', async () => {
    const { publicFileExists } = await loadFresh();
    expect(publicFileExists(LOCAL, publicDir)).toBe(false);
    plant(LOCAL);
    expect(publicFileExists(LOCAL, publicDir)).toBe(true);
  });

  it('memoizes in a production build (import.meta.env.PROD)', async () => {
    vi.stubEnv('PROD', true);
    const { publicFileExists } = await loadFresh();
    expect(publicFileExists(LOCAL, publicDir)).toBe(false);
    plant(LOCAL);
    expect(publicFileExists(LOCAL, publicDir)).toBe(false);
  });
});

describe('WWW_PUBLIC_DIR', () => {
  it('points at packages/www/public regardless of cwd', async () => {
    const { WWW_PUBLIC_DIR } = await loadFresh();
    expect(WWW_PUBLIC_DIR.endsWith(path.join('packages', 'www', 'public'))).toBe(true);
    expect(fs.existsSync(WWW_PUBLIC_DIR)).toBe(true);
  });
});
