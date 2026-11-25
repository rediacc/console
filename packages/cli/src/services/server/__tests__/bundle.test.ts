/**
 * `rdc server bundle` and the bundle checks (PLAN-enterprise-tenants C11): what is written, the
 * pinned proxy image, and the refusals (tampered file, hand-edited manifest, another CLI's bundle,
 * another renet).
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
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
import { bundleImages, rustfsRef, serverRef, TRAEFIK_REF } from '../bundle/images.js';
import { parseSums, sumsText } from '../bundle/manifest.js';
import { verifyBundle } from '../bundle/verify.js';
import { FAKE_MODELS, makeFake, signerOf } from './fakes.js';

const OUT = '/bundles/acme';
const here = dirname(fileURLToPath(import.meta.url));

async function built(opts: Parameters<typeof serverBundle>[1] = { out: OUT, tag: '1.2' }) {
  m.version = '1.0.0';
  const fake = makeFake();
  const manifest = await serverBundle(fake.deps, opts);
  return { fake, manifest };
}

describe('the pinned proxy image', () => {
  it("equals the image: line of renet's proxy compose file", () => {
    const compose = readFileSync(
      join(here, '../../../../../../private/renet/proxy/docker-compose.yml'),
      'utf-8'
    );
    const line = compose.split('\n')[20];
    expect(line.trim()).toBe(`image: ${TRAEFIK_REF}`);
  });

  it('the line the pin is read from still names an image (control)', () => {
    const compose = readFileSync(
      join(here, '../../../../../../private/renet/proxy/docker-compose.yml'),
      'utf-8'
    );
    expect(compose.split('\n')[20]).toMatch(/^\s*image: \S+:\S+$/);
  });

  it('RustFS comes from the built-in template as a digest-pinned ref', () => {
    expect(rustfsRef()).toMatch(/^rustfs\/rustfs@sha256:[0-9a-f]{64}$/);
  });

  it('the bundle holds the server, RustFS and proxy images in that order', () => {
    expect(bundleImages('ghcr.io/x/server:1').map((i) => [i.name, i.file])).toEqual([
      ['server', 'images/server.tar'],
      ['rustfs', 'images/rustfs.tar'],
      ['traefik', 'images/traefik.tar'],
    ]);
  });

  it('--tag swaps the default image tag, and a ref given as --image wins', () => {
    expect(serverRef({ tag: '1.2' })).toMatch(/\/server:1\.2$/);
    expect(serverRef({ tag: '1.2', image: 'local:dev' })).toBe('local:dev');
    expect(serverRef({})).toMatch(/\/server:latest$/);
  });
});

describe('server bundle', () => {
  it('pulls and saves each image for the target platform, then writes the records', async () => {
    const { fake, manifest } = await built({ out: OUT, tag: '1.2', arch: 'arm64', models: false });
    const pulls = fake.calls.filter((c) => c.startsWith('local docker pull'));
    expect(pulls).toHaveLength(3);
    expect(pulls.every((c) => c.includes('--platform linux/arm64'))).toBe(true);
    const saves = fake.calls.filter((c) => c.startsWith('local docker save'));
    expect(saves.map((c) => c.split(' -o ')[1])).toEqual([
      `${OUT}/images/server.tar ${manifest.images[0].ref}`,
      `${OUT}/images/rustfs.tar ${manifest.images[1].ref}`,
      `${OUT}/images/traefik.tar ${TRAEFIK_REF}`,
    ]);
    expect(saves.every((c) => c.includes('--platform linux/arm64'))).toBe(true);
    expect(Object.keys(fake.files).sort((a, b) => Number(a > b) - Number(a < b))).toEqual(
      [
        'SHA256SUMS',
        'images/manifest.txt',
        'images/rustfs.tar',
        'images/server.tar',
        'images/traefik.tar',
        'manifest.json',
        'manifest.sig',
        'renet/renet-linux-arm64',
        'signer.pub',
      ].map((f) => `${OUT}/${f}`)
    );
  });

  it('writes the manifest the plan names, and sums for every file', async () => {
    const { fake, manifest } = await built({ out: OUT, tag: '1.2', models: false });
    expect(manifest).toMatchObject({
      schema: 1,
      cliVersion: '1.0.0',
      template: { name: 'elite', sha256: expect.stringMatching(/^[0-9a-f]{64}$/) },
      renet: { version: 'v-test', arch: 'amd64', sha256: expect.stringMatching(/^[0-9a-f]{64}$/) },
      createdAt: '2026-11-12T12:00:00.000Z',
    });
    expect(manifest.images.map((i) => i.digest)).toEqual(
      manifest.images.map((i) => `sha256:id-of-${i.ref}`)
    );
    const sums = parseSums(fake.files[`${OUT}/SHA256SUMS`]);
    expect(sums.map((s) => s.file)).toEqual([
      'images/manifest.txt',
      'images/rustfs.tar',
      'images/server.tar',
      'images/traefik.tar',
      'manifest.json',
      'renet/renet-linux-amd64',
    ]);
    expect(JSON.parse(fake.files[`${OUT}/manifest.json`])).toEqual(manifest);
  });

  it("lists the template's tars in images/manifest.txt, never the proxy's", async () => {
    const { fake, manifest } = await built();
    expect(fake.files[`${OUT}/images/manifest.txt`]).toBe(
      `server.tar ${manifest.images[0].ref}\nrustfs.tar ${manifest.images[1].ref}\n`
    );
  });

  it('ships a local --image as it is, and still pulls the others', async () => {
    const { fake } = await built({ out: OUT, image: 'registry.local/server:dev' });
    const pulls = fake.calls.filter((c) => c.startsWith('local docker pull'));
    expect(pulls).toHaveLength(2);
    expect(pulls.some((c) => c.includes('registry.local/server:dev'))).toBe(false);
    expect(
      fake.calls.some((c) => c.endsWith('registry.local/server:dev') && c.includes('save'))
    ).toBe(true);
  });

  it('refuses --tag together with --image, before touching docker', async () => {
    const fake = makeFake();
    await expect(serverBundle(fake.deps, { out: OUT, tag: '1', image: 'x:y' })).rejects.toThrow(
      /tagAndImage/
    );
    expect(fake.calls).toEqual([]);
  });

  it('names the image whose pull failed', async () => {
    const fake = makeFake();
    fake.deps.local = (command, args) => {
      fake.calls.push(`local ${command} ${args.join(' ')}`);
      return Promise.resolve(args[0] === 'pull' ? 1 : 0);
    };
    await expect(serverBundle(fake.deps, { out: OUT, tag: '1' })).rejects.toThrow(
      /pullFailed.*server:1/s
    );
  });
});

describe('verifyBundle', () => {
  it('accepts the bundle it just wrote', async () => {
    const { fake, manifest } = await built();
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).resolves.toEqual(
      manifest
    );
  });

  it('refuses a tar changed after bundling, naming it', async () => {
    const { fake } = await built();
    fake.files[`${OUT}/images/server.tar`] = 'tampered';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*images\/server\.tar/s
    );
  });

  it('refuses a changed renet binary', async () => {
    const { fake } = await built();
    fake.files[`${OUT}/renet/renet-linux-amd64`] = 'tampered';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*renet-linux-amd64/s
    );
  });

  it('refuses a manifest edited after bundling', async () => {
    const { fake } = await built();
    fake.files[`${OUT}/manifest.json`] = fake.files[`${OUT}/manifest.json`].replace(
      '1.0.0',
      '9.9.9'
    );
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*manifest\.json/s
    );
  });

  it('refuses a manifest whose records disagree with the sums, even when the sums were redone', async () => {
    const { fake } = await built();
    const manifest = JSON.parse(fake.files[`${OUT}/manifest.json`]);
    manifest.images[0].sha256 = '0'.repeat(64);
    const text = `${JSON.stringify(manifest, null, 2)}\n`;
    fake.files[`${OUT}/manifest.json`] = text;
    // Redo every sum, the manifest's own included, so only the record-versus-sum check can object.
    const rehashed = await Promise.all(
      parseSums(fake.files[`${OUT}/SHA256SUMS`]).map(async (s) => ({
        ...s,
        sha256: await fake.deps.sha256File(`${OUT}/${s.file}`),
      }))
    );
    fake.files[`${OUT}/SHA256SUMS`] = sumsText(rehashed);
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*images\/server\.tar/s
    );
  });

  it('refuses a bundle another CLI version made', async () => {
    const { fake } = await built();
    m.version = '2.0.0';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /cliMismatch.*"bundle":"1\.0\.0".*"cli":"2\.0\.0"/s
    );
  });

  it('refuses a bundle whose renet is not the renet this CLI carries', async () => {
    const { fake } = await built();
    const other = makeFake({ files: fake.files, renetSha: 'f'.repeat(64) });
    await expect(verifyBundle(other.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /renetMismatch.*amd64/s
    );
  });

  it('names a bundle directory with no SHA256SUMS', async () => {
    const fake = makeFake({
      files: {
        '/empty/manifest.sig': 'x',
        '/empty/signer.pub': Buffer.alloc(32).toString('base64'),
      },
    });
    const fingerprint = signerOf(fake.files, '/empty');
    await expect(verifyBundle(fake.deps, '/empty', fingerprint)).rejects.toThrow(
      /unreadable.*SHA256SUMS/s
    );
  });

  it('refuses sums that leave the manifest unprotected', async () => {
    const { fake } = await built();
    const without = parseSums(fake.files[`${OUT}/SHA256SUMS`]).filter(
      (s) => s.file !== 'manifest.json'
    );
    fake.files[`${OUT}/SHA256SUMS`] = sumsText(without);
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /notSummed/
    );
  });
});

describe('the bundle signature (D12)', () => {
  const signer = (fake: { files: Record<string, string> }) => signerOf(fake.files, OUT);

  it('writes manifest.sig and signer.pub, and the fingerprint is the hash of the key', async () => {
    const { fake } = await built();
    expect(fake.files[`${OUT}/manifest.sig`]).toBeTruthy();
    expect(signer(fake)).toMatch(/^[0-9a-f]{64}$/);
  });

  it('accepts the fingerprint in upper case, with a sha256: label or with colons', async () => {
    const { fake, manifest } = await built();
    const hex = signer(fake);
    const colons = hex.match(/../g)?.join(':') ?? '';
    for (const form of [hex.toUpperCase(), `sha256:${hex}`, colons]) {
      await expect(verifyBundle(fake.deps, OUT, form)).resolves.toEqual(manifest);
    }
  });

  it('refuses a tampered image even when the manifest record and every sum were redone', async () => {
    const { fake } = await built();
    fake.files[`${OUT}/images/server.tar`] = 'tampered';
    const hash = await fake.deps.sha256File(`${OUT}/images/server.tar`);
    const manifest = JSON.parse(fake.files[`${OUT}/manifest.json`]);
    manifest.images[0].sha256 = hash;
    fake.files[`${OUT}/manifest.json`] = `${JSON.stringify(manifest, null, 2)}\n`;
    const redone = await Promise.all(
      parseSums(fake.files[`${OUT}/SHA256SUMS`]).map(async (s) => ({
        ...s,
        sha256: await fake.deps.sha256File(`${OUT}/${s.file}`),
      }))
    );
    fake.files[`${OUT}/SHA256SUMS`] = sumsText(redone);
    await expect(verifyBundle(fake.deps, OUT, signer(fake))).rejects.toThrow(/badSignature/);
  });

  it('refuses a fingerprint that is not the bundle signer', async () => {
    const { fake } = await built();
    await expect(verifyBundle(fake.deps, OUT, 'b'.repeat(64))).rejects.toThrow(
      /signerMismatch.*"actual":"[0-9a-f]{64}"/s
    );
  });

  it('refuses a bundle re-signed by another key when the fingerprint is the original', async () => {
    const { fake } = await built();
    const fingerprint = signer(fake);
    const other = await built({ out: OUT, tag: '1.2' });
    fake.files[`${OUT}/manifest.sig`] = other.fake.files[`${OUT}/manifest.sig`];
    fake.files[`${OUT}/signer.pub`] = other.fake.files[`${OUT}/signer.pub`];
    await expect(verifyBundle(fake.deps, OUT, fingerprint)).rejects.toThrow(/signerMismatch/);
  });

  it('refuses a bundle without manifest.sig', async () => {
    const { fake } = await built();
    const fingerprint = signer(fake);
    delete fake.files[`${OUT}/manifest.sig`];
    await expect(verifyBundle(fake.deps, OUT, fingerprint)).rejects.toThrow(
      /unsigned.*manifest\.sig/s
    );
  });

  it('refuses a bundle without signer.pub', async () => {
    const { fake } = await built();
    const fingerprint = signer(fake);
    delete fake.files[`${OUT}/signer.pub`];
    await expect(verifyBundle(fake.deps, OUT, fingerprint)).rejects.toThrow(
      /unsigned.*signer\.pub/s
    );
  });

  it('refuses a manifest.sig that is not the signer signature', async () => {
    const { fake } = await built();
    fake.files[`${OUT}/manifest.sig`] = Buffer.alloc(64).toString('base64');
    await expect(verifyBundle(fake.deps, OUT, signer(fake))).rejects.toThrow(/badSignature/);
  });
});

describe('the models in the bundle (D12)', () => {
  it('writes the stable pointer, manifest and objects with their signatures, summed and recorded', async () => {
    const { fake, manifest } = await built();
    const files = (manifest.models ?? []).map((f) => f.file);
    expect(files).toEqual(
      expect.arrayContaining([
        'models/channels/stable.json',
        'models/channels/stable.json.sig',
        'models/manifests/7.json',
        'models/manifests/7.json.sig',
      ])
    );
    const objects = files.filter((f) => /^models\/objects\/[0-9a-f]{64}$/.test(f));
    expect(objects).toHaveLength(2);
    for (const object of objects) expect(files).toContain(`${object}.sig`);
    expect(files).toHaveLength(8);
    const summed = parseSums(fake.files[`${OUT}/SHA256SUMS`]).map((s) => s.file);
    for (const file of files) expect(summed).toContain(file);
  });

  it('refuses a model object changed after bundling', async () => {
    const { fake, manifest } = await built();
    const object = (manifest.models ?? []).find((f) => f.file.startsWith('models/objects/'));
    fake.files[`${OUT}/${object?.file}`] = 'tampered';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*models\/objects/s
    );
  });

  it('refuses a model object signature changed after bundling', async () => {
    const { fake, manifest } = await built();
    const sig = (manifest.models ?? []).find((f) => /objects\/[0-9a-f]{64}\.sig$/.test(f.file));
    expect(sig).toBeDefined();
    fake.files[`${OUT}/${sig?.file}`] = 'tampered';
    await expect(verifyBundle(fake.deps, OUT, signerOf(fake.files, OUT))).rejects.toThrow(
      /tampered.*models\/objects/s
    );
  });

  it('--no-models leaves models/ out', async () => {
    const { manifest } = await built({ out: OUT, tag: '1.2', models: false });
    expect(manifest.models).toBeUndefined();
  });

  it('refuses an object whose hash differs from the manifest list, writing no records', async () => {
    m.version = '1.0.0';
    const fake = makeFake({
      release: Object.fromEntries(
        Object.entries(FAKE_MODELS).map(([url, body]) => [
          url,
          url.includes('/objects/') ? 'swapped' : body,
        ])
      ),
    });
    await expect(serverBundle(fake.deps, { out: OUT, tag: '1' })).rejects.toThrow(
      /modelsSha256Mismatch/
    );
    expect(fake.files[`${OUT}/manifest.json`]).toBeUndefined();
  });
});
