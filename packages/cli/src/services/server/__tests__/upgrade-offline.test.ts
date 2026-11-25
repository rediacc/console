/**
 * `rdc server upgrade --bundle` and the template-edit guard (PLAN-enterprise-tenants C11, Q19), and
 * the cert-expiry reading of `status`, against a scripted box and the real built-in template.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getLocalMachine: () => Promise.resolve({ ip: '203.0.113.10', user: 'admin' }),
    getRepository: () => Promise.resolve({ repositoryGuid: 'guid-1', networkId: 2816 }),
  },
}));
vi.mock('../../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: () => Promise.resolve(undefined),
}));

import { outputService } from '../../core/output.js';
import { serverBundle } from '../bundle/build.js';
import { builtinTemplateVersion } from '../common.js';
import { serverStatus, serverUpgrade } from '../verbs.js';
import { BOX_KEY, certFor, type Fake, type FakeOptions, makeFake, signerOf } from './fakes.js';

const LOC = { domain: 'acme.example.com', machine: 'm1' };
const BUNDLE = '/bundles/acme';
const OLDER = builtinTemplateVersion() - 1;

const hasFork = (fake: Fake) => fake.calls.some((c) => c.startsWith('rdc repo fork'));

async function withBundle(opts: FakeOptions = {}): Promise<Fake> {
  const maker = makeFake();
  await serverBundle(maker.deps, { out: BUNDLE, tag: '2.0' });
  return makeFake({ ...opts, files: { ...maker.files, ...opts.files } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('upgrade and local template edits', () => {
  it('refuses a newer template over an edited file, before the fork, naming the file', async () => {
    const fake = makeFake({
      templateVersion: OLDER,
      templateEdits: { edited: ['docker-compose.yml'] },
    });
    await expect(serverUpgrade(fake.deps, LOC, {})).rejects.toThrow(
      /templateEdited.*docker-compose\.yml/s
    );
    expect(hasFork(fake)).toBe(false);
    expect(fake.calls.some((c) => c.includes('template apply'))).toBe(false);
  });

  it('applies it over the edit with --force', async () => {
    const fake = makeFake({ templateVersion: OLDER, templateEdits: { edited: ['Rediaccfile'] } });
    const result = await serverUpgrade(fake.deps, LOC, { force: true });
    expect(result.templateReapplied).toBe(true);
    expect(fake.calls).toContain('rdc repo admin template apply elite@m1 --template elite');
  });

  it('applies it over unedited files and records fresh sums right after', async () => {
    const fake = makeFake({ templateVersion: OLDER });
    await serverUpgrade(fake.deps, LOC, {});
    const apply = fake.calls.indexOf('rdc repo admin template apply elite@m1 --template elite');
    expect(apply).toBeGreaterThan(-1);
    expect(fake.calls.indexOf('ssh m1 template-sums')).toBeGreaterThan(apply);
  });

  it('warns and goes on when the box recorded no sums', async () => {
    const fake = makeFake({ templateVersion: OLDER, templateEdits: { baseline: false } });
    const result = await serverUpgrade(fake.deps, LOC, {});
    expect(result.templateReapplied).toBe(true);
    expect(vi.mocked(outputService.warn).mock.calls.map((c) => c[0])).toEqual([
      'commands.server.upgrade.templateNoBaseline',
    ]);
  });

  it('does not look at edits when the template is already current (control)', async () => {
    const fake = makeFake({
      templateVersion: builtinTemplateVersion(),
      templateEdits: { edited: ['docker-compose.yml'] },
    });
    const result = await serverUpgrade(fake.deps, LOC, {});
    expect(result.templateReapplied).toBe(false);
    expect(fake.calls).not.toContain('ssh m1 template-edits');
    expect(fake.calls).not.toContain('ssh m1 template-sums');
  });
});

describe('upgrade --bundle', () => {
  it('ships the bundle images through repo sync instead of pulling, and moves the image ref', async () => {
    const fake = await withBundle({ templateVersion: builtinTemplateVersion() });
    const result = await serverUpgrade(fake.deps, LOC, {
      bundle: BUNDLE,
      signer: signerOf(fake.files, BUNDLE),
    });
    expect(result.image).toMatch(/server:2\.0$/);
    const uploads = fake.calls.filter((c) => c.startsWith('rdc repo sync upload'));
    expect(uploads.map((c) => c.split('--remote-file ')[1].split(' ')[0])).toEqual([
      'images/server.tar',
      'images/rustfs.tar',
      'images/manifest.txt',
    ]);
    expect(fake.calls).not.toContain('ssh m1 pull');
    expect(fake.setEnv.at(-1)).toEqual({ ELITE_IMAGE: result.image, TAG: '2.0' });
    expect(fake.calls.indexOf('rdc repo up elite@m1')).toBeGreaterThan(
      fake.calls.findLastIndex((c) => c.startsWith('rdc repo sync upload'))
    );
  });

  it('refuses a tampered bundle before the fork', async () => {
    const fake = await withBundle();
    fake.files[`${BUNDLE}/images/server.tar`] = 'tampered';
    await expect(
      serverUpgrade(fake.deps, LOC, { bundle: BUNDLE, signer: signerOf(fake.files, BUNDLE) })
    ).rejects.toThrow(/tampered/);
    expect(hasFork(fake)).toBe(false);
  });

  it('refuses a bundle without --signer, or with the wrong one, before the fork', async () => {
    const fake = await withBundle();
    await expect(serverUpgrade(fake.deps, LOC, { bundle: BUNDLE })).rejects.toThrow(/needsSigner/);
    await expect(
      serverUpgrade(fake.deps, LOC, { bundle: BUNDLE, signer: 'c'.repeat(64) })
    ).rejects.toThrow(/signerMismatch/);
    expect(hasFork(fake)).toBe(false);
  });

  it('refuses a bundle next to --image or --image-file', async () => {
    const fake = await withBundle();
    await expect(
      serverUpgrade(fake.deps, LOC, {
        bundle: BUNDLE,
        signer: signerOf(fake.files, BUNDLE),
        image: 'x:y',
      })
    ).rejects.toThrow(/bundleAndImage/);
    await expect(
      serverUpgrade(fake.deps, LOC, {
        bundle: BUNDLE,
        signer: signerOf(fake.files, BUNDLE),
        imageFile: 'a.tar',
      })
    ).rejects.toThrow(/bundleAndImage/);
    expect(hasFork(fake)).toBe(false);
  });
});

describe('status and the cert end date', () => {
  it('reports the whole days left on the live cert', async () => {
    // The fake clock is 2026-11-12T12:00Z; the cert ends 2027-11-12T00:00Z.
    const fake = makeFake({ liveCert: certFor(BOX_KEY) });
    const status = await serverStatus(fake.deps, LOC);
    expect(status.certExpiresInDays).toBe(364);
  });

  it('reports none on the free tier (control)', async () => {
    const status = await serverStatus(makeFake().deps, LOC);
    expect(status.certExpiresInDays).toBeUndefined();
  });
});
