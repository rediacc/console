/**
 * `rdc server install --offline --bundle <dir>` and `rdc server licence mint`
 * (PLAN-enterprise-tenants C11) against a scripted box: the verified bundle, the offline
 * preflight, the proxy image, no upstream call, the stop at the licence request and the resume
 * with the minted cert.
 */

import { rmSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  machines: [] as { name: string; config: { ip: string; user: string } }[],
  repos: new Map<string, { repositoryGuid: string; networkId?: number }>(),
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    listMachines: () => Promise.resolve(m.machines),
    getLocalMachine: (name: string) =>
      Promise.resolve(m.machines.find((x) => x.name === name)?.config),
    getLocalConfig: () => Promise.resolve({ machines: {}, certEmail: undefined }),
    getRepository: (name: string) => Promise.resolve(m.repos.get(name)),
  },
}));
vi.mock('../../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: () => Promise.resolve(undefined),
}));
vi.mock('../../machine/add-existing.js', () => ({ addExistingMachine: vi.fn() }));

import type { ServerPrompts } from '../../../utils/server-prompts.js';
import { serverBundle } from '../bundle/build.js';
import { licenceMint } from '../bundle/offline.js';
import { ServerInstall } from '../install.js';
import { requestFile, serverStateDir } from '../state.js';
import type { ServerDeps } from '../types.js';
import { BOX_KEY, certFor, type Fake, type FakeOptions, makeFake } from './fakes.js';

const DOMAIN = 'acme.example.com';
const BUNDLE = '/bundles/acme';
const BASE = {
  machine: 'm1',
  domain: DOMAIN,
  owner: 'owner@example.com',
  offline: true,
  bundle: BUNDLE,
  tls: 'byo' as const,
  tlsCert: '/pki/host.crt',
  tlsKey: '/pki/host.key',
  tlsCa: '/pki/ca.crt',
};
const NO_PROMPTS = {} as ServerPrompts;

/** A fake whose local files hold a bundle written by the real bundler, plus the TLS pair and a cert. */
async function offlineFake(
  opts: FakeOptions = {},
  certText?: string,
  arch: 'amd64' | 'arm64' = 'amd64'
): Promise<Fake> {
  const maker = makeFake();
  await serverBundle(maker.deps, { out: BUNDLE, tag: '1.2', arch });
  const fake = makeFake({
    ...opts,
    files: {
      ...maker.files,
      '/pki/host.crt': 'CERT',
      '/pki/host.key': 'KEY',
      '/pki/ca.crt': 'CA',
      ...(certText ? { '/certs/box.json': certText } : {}),
      ...opts.files,
    },
  });
  const rdc = fake.deps.rdc;
  fake.deps.rdc = (argv) => {
    if (argv[0] === 'repo' && argv[1] === 'create') {
      m.repos.set(argv[2], { repositoryGuid: 'guid-1', networkId: 2816 });
    }
    return rdc(argv);
  };
  return fake;
}

const install = (fake: Fake, opts: Record<string, unknown> = {}) =>
  new ServerInstall({ ...BASE, ...opts }, fake.deps, NO_PROMPTS).run();

const boxCert = () => Buffer.from(certFor(BOX_KEY), 'base64').toString('utf-8');

beforeEach(() => {
  vi.clearAllMocks();
  m.machines = [{ name: 'm1', config: { ip: '192.168.111.12', user: 'admin' } }];
  m.repos = new Map();
  rmSync(serverStateDir(), { recursive: true, force: true });
});

describe('an offline install from a bundle', () => {
  it('runs the whole install with a cert file and calls nothing upstream', async () => {
    const fake = await offlineFake({ preflight: { renet: '0' } }, boxCert());
    const out = await install(fake, { cert: '/certs/box.json' });
    expect(out).toMatchObject({ domain: DOMAIN, tier: 'licensed', tls: 'byo' });
    expect(out.image).toMatch(/server:1\.2$/);
    for (const forbidden of ['issue', 'resolve', 'docker pull', 'ssh m1 pull']) {
      expect(fake.calls.some((c) => c.includes(forbidden))).toBe(false);
    }
    expect(fake.dnsWrites).toEqual([]);
    expect(fake.bwsWrites).toEqual([]);
  });

  it('loads the proxy image before `machine setup --offline`, then sets up offline', async () => {
    const fake = await offlineFake({ preflight: { renet: '0' } }, boxCert());
    await install(fake, { cert: '/certs/box.json' });
    const load = fake.calls.findIndex((c) => c === 'ssh m1 proxy-load');
    const setup = fake.calls.indexOf('rdc machine setup m1 --offline');
    expect(load).toBeGreaterThan(-1);
    expect(setup).toBeGreaterThan(load);
    expect(fake.uploads).toHaveLength(1);
    expect(fake.uploads[0]).toMatch(/^m1:\/tmp\/rdc-\d+-traefik\.tar$/);
  });

  it('skips the proxy upload when the machine already holds the image (control)', async () => {
    const fake = await offlineFake({ proxyImage: 'present' }, boxCert());
    await install(fake, { cert: '/certs/box.json' });
    expect(fake.uploads).toEqual([]);
    expect(fake.calls).not.toContain('ssh m1 proxy-load');
  });

  it('uploads the server and RustFS tars and their list through repo sync, and marks the box offline', async () => {
    const fake = await offlineFake({}, boxCert());
    await install(fake, { cert: '/certs/box.json' });
    const uploads = fake.calls.filter((c) => c.startsWith('rdc repo sync upload'));
    expect(uploads.map((c) => c.split('--remote-file ')[1].split(' ')[0])).toEqual([
      'images/server.tar',
      'images/rustfs.tar',
      'images/manifest.txt',
    ]);
    expect(uploads.every((c) => c.includes(`--local ${BUNDLE}/images/`))).toBe(true);
    const settings = fake.setEnv.find((e) => e.ELITE_DOMAIN);
    expect(settings).toMatchObject({ ELITE_OFFLINE: '1', ELITE_TLS: 'provided' });
    expect(settings?.ELITE_IMAGE).toMatch(/server:1\.2$/);
    expect(settings?.TAG).toBe('1.2');
  });

  it('prints the LAN records and never waits for DNS', async () => {
    const fake = await offlineFake({}, boxCert());
    await install(fake, { cert: '/certs/box.json', dnsWait: true });
    expect(fake.calls.some((c) => c.startsWith('resolve'))).toBe(false);
  });

  it('records the CA for the health checks (the box is probed over it)', async () => {
    const fake = await offlineFake({}, boxCert());
    await install(fake, { cert: '/certs/box.json' });
    const record = JSON.parse(fake.written[`${serverStateDir()}/${DOMAIN}.json`]);
    expect(record.tlsCa).toBe('/pki/ca.crt');
  });
});

describe('the licence trip', () => {
  it('stops at the licence step, writing delegation-request.json with the box key and asking no one', async () => {
    const fake = await offlineFake();
    await expect(install(fake)).rejects.toThrow(/licence: .*awaitingCert/s);
    const request = JSON.parse(fake.written[requestFile(DOMAIN)]);
    expect(request).toMatchObject({ schema: 1, domain: DOMAIN, delegatedPublicKey: BOX_KEY });
    expect(fake.calls).not.toContain('issue');
    expect(fake.calls).not.toContain('rdc repo up elite@m1');
  });

  it('resumes with --cert from the finished steps, up to the end', async () => {
    const fake = await offlineFake({}, boxCert());
    await expect(install(fake)).rejects.toThrow(/awaitingCert/);
    const before = fake.calls.length;
    const out = await install(fake, { cert: '/certs/box.json' });
    expect(out.tier).toBe('licensed');
    const second = fake.calls.slice(before);
    expect(second).not.toContain('rdc repo create elite -m m1 --size 10G');
    expect(second).toContain('rdc repo up elite@m1');
  });

  it('refuses a cert for another key', async () => {
    const other = Buffer.from(certFor('MCowBQYDK2VwAyEAotherkey'), 'base64').toString('utf-8');
    const fake = await offlineFake({}, other);
    await expect(install(fake, { cert: '/certs/box.json' })).rejects.toThrow(/keyMismatch/);
    expect(fake.calls).not.toContain('rdc repo up elite@m1');
  });

  it('round-trips: the request mint answers is the cert the resume accepts', async () => {
    const first = await offlineFake();
    await expect(install(first)).rejects.toThrow(/awaitingCert/);
    const online = makeFake();
    online.files['/rdc-mint/req.json'] = first.written[requestFile(DOMAIN)];
    const minted = await licenceMint(online.deps, '/rdc-mint/req.json', '/certs/box.json');
    expect(minted.subscriptionId).toBe('sub-1');
    const second = await offlineFake({}, online.written['/certs/box.json']);
    const out = await install(second, { cert: '/certs/box.json' });
    expect(out.subscriptionId).toBe('sub-1');
  });
});

describe('what an offline install refuses', () => {
  const refused = async (opts: Record<string, unknown>, pattern: RegExp) => {
    const fake = await offlineFake();
    await expect(install(fake, opts)).rejects.toThrow(pattern);
    // Nothing touched the box or the account server.
    expect(fake.calls).toEqual([]);
  };

  it('--licence free', () => refused({ licence: 'free' }, /errors\.licenceFreeRefused/));
  it('--offline without --bundle', () => refused({ bundle: undefined }, /offline\.needsBundle/));
  it('a Let us Encrypt or Cloudflare TLS method', () =>
    refused({ tls: 'letsencrypt' }, /offline\.tlsByoOnly/));
  it('--cf-token', () => refused({ cfToken: 'x' }, /offline\.noCfToken/));
  it('--bws-project', () => refused({ bwsProject: 'p' }, /offline\.noBws/));
  it('--image next to the bundle', () => refused({ image: 'x:y' }, /offline\.imageFromBundle/));

  it('--bundle without --offline', async () => {
    const fake = await offlineFake();
    await expect(install(fake, { offline: false })).rejects.toThrow(/bundleNeedsOffline/);
  });

  it('a tampered bundle, before any call to the box', async () => {
    const fake = await offlineFake();
    fake.files[`${BUNDLE}/images/rustfs.tar`] = 'tampered';
    await expect(install(fake)).rejects.toThrow(/tampered.*rustfs\.tar/s);
    expect(fake.calls).toEqual([]);
  });

  it('a box missing tools the offline setup assumes, naming them', async () => {
    const fake = await offlineFake({ essentialsMissing: ' cryptsetup docker-compose-plugin' });
    await expect(install(fake)).rejects.toThrow(
      /preflight.*missingEssentials.*cryptsetup docker-compose-plugin/s
    );
    expect(fake.calls).not.toContain('ssh m1 proxy-load');
  });

  it('a box of another architecture than the bundle', async () => {
    const fake = await offlineFake({ preflight: { arch: 'aarch64' } });
    await expect(install(fake)).rejects.toThrow(/archMismatch.*"box":"aarch64".*"bundle":"amd64"/s);
  });

  it('accepts an arm64 box for an arm64 bundle (control)', async () => {
    const fake = await offlineFake({ preflight: { arch: 'aarch64' } }, undefined, 'arm64');
    await expect(install(fake)).rejects.toThrow(/awaitingCert/);
  });
});

describe('licence mint', () => {
  const request = JSON.stringify({ schema: 1, domain: DOMAIN, delegatedPublicKey: BOX_KEY });

  const mint = (opts: FakeOptions, text = request): [Promise<unknown>, ServerDeps] => {
    const fake = makeFake({ ...opts, files: { '/rdc-mint/req.json': text } });
    return [licenceMint(fake.deps, '/rdc-mint/req.json', '/rdc-mint/out.json'), fake.deps];
  };

  it('writes a cert file for the request key, at the private writer', async () => {
    const fake = makeFake({ files: { '/rdc-mint/req.json': request } });
    const result = await licenceMint(fake.deps, '/rdc-mint/req.json', '/rdc-mint/out.json');
    expect(result).toMatchObject({ subscriptionId: 'sub-1', validUntil: '2027-11-12T00:00:00Z' });
    const signed = JSON.parse(fake.written['/rdc-mint/out.json']);
    expect(Object.keys(signed).sort((a, b) => Number(a > b) - Number(a < b))).toEqual([
      'payload',
      'publicKeyId',
      'signature',
    ]);
    expect(fake.calls).toContain('issue');
  });

  it('refuses a request file that is not one', async () => {
    await expect(mint({}, '{"schema":2}')[0]).rejects.toThrow(/requestInvalid/);
    await expect(mint({}, 'not json')[0]).rejects.toThrow(/requestInvalid/);
  });

  it('says so with no login, and writes nothing', async () => {
    const fake = makeFake({
      files: { '/rdc-mint/req.json': request },
      issue: { kind: 'no-login' },
    });
    await expect(
      licenceMint(fake.deps, '/rdc-mint/req.json', '/rdc-mint/out.json')
    ).rejects.toThrow(/mintNoLogin/);
    expect(fake.written['/rdc-mint/out.json']).toBeUndefined();
  });

  it('refuses a cert minted for another key than the request names', async () => {
    const fake = makeFake({
      files: { '/rdc-mint/req.json': request },
      issue: {
        kind: 'issued',
        cert: { certBase64: certFor('MCowBQYDK2VwAyEAotherkey'), subscriptionId: 'sub-1' },
      },
    });
    await expect(
      licenceMint(fake.deps, '/rdc-mint/req.json', '/rdc-mint/out.json')
    ).rejects.toThrow(/issuedKeyMismatch/);
    expect(fake.written['/rdc-mint/out.json']).toBeUndefined();
  });
});
