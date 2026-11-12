/**
 * `rdc server status|backup|upgrade|licence` (PLAN-enterprise-tenants C7) against a scripted box.
 */

import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  builtinVersion: '' as string,
  owner: undefined as { email: string; password: string } | undefined,
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../state.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../state.js')>()),
  loadOwner: () => m.owner,
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
vi.mock('../../../templates/embedded.generated.js', () => ({
  TEMPLATES: {
    get elite() {
      return {
        name: 'elite',
        description: '',
        files: m.builtinVersion ? { VERSION: m.builtinVersion } : {},
      };
    },
  },
}));

import { liveServerDeps } from '../deps.js';
import { serverBackup, serverLicence, serverStatus, serverUpgrade } from '../verbs.js';
import { BOX_KEY, certFor, makeFake } from './fakes.js';

const LOC = { domain: 'acme.example.com', machine: 'm1' };

beforeEach(() => {
  vi.clearAllMocks();
  m.builtinVersion = '';
  m.owner = { email: 'owner@example.com', password: 'pw-1' };
});

describe('status', () => {
  it('reports the free tier and bootstrap mode for a box with no cert', async () => {
    const fake = makeFake();
    const status = await serverStatus(fake.deps, LOC);
    expect(status).toMatchObject({ tier: 'free', bootstrapMode: true, health: 200 });
    expect(status.freeTierRelay).toBe(true);
  });

  it("reports the cert's plan and subscription once licensed", async () => {
    const fake = makeFake({
      secrets: { DELEGATION_CERT_BASE64: certFor(BOX_KEY, 'sub-9', 'ELITE') },
      freeProbe: 409,
    });
    const status = await serverStatus(fake.deps, LOC);
    expect(status).toMatchObject({
      tier: 'ELITE',
      bootstrapMode: false,
      subscriptionId: 'sub-9',
      freeTierRelay: false,
    });
  });

  it('refuses a domain with no record and no --machine', async () => {
    await expect(serverStatus(makeFake().deps, { domain: 'nowhere.example' })).rejects.toThrow(
      /noRecord/
    );
  });
});

describe('backup', () => {
  it('streams the bundle to stdout', async () => {
    const fake = makeFake();
    await serverBackup(fake.deps, LOC);
    const text = fake.stdout.join('');
    for (const key of [
      'ACCOUNT_ED25519_PRIVATE_KEY',
      'ACCOUNT_CONFIG_SERVER_KEY',
      'RUSTFS_ACCESS_KEY',
      'RUSTFS_SECRET_KEY',
    ]) {
      expect(text).toMatch(new RegExp(`^${key}=`, 'm'));
    }
  });

  it('writes --out at mode 0600 through the live writer', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'rdc-server-backup-'));
    try {
      const fake = makeFake();
      const out = join(dir, 'bundle.env');
      fake.deps.writePrivate = liveServerDeps().writePrivate;
      await serverBackup(fake.deps, LOC, out);
      expect(statSync(out).mode & 0o777).toBe(0o600);
      expect(readFileSync(out, 'utf-8')).toContain('ACCOUNT_ED25519_PRIVATE_KEY=edpriv');
      expect(fake.stdout).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe('upgrade', () => {
  it('forks first, and leaves the template alone when the built-in one is not newer', async () => {
    m.builtinVersion = '';
    const fake = makeFake({ templateVersion: 0 });
    const result = await serverUpgrade(fake.deps, LOC, { image: 'ghcr.io/rediacc/server:2.0' });
    const rdc = fake.calls.filter((c) => c.startsWith('rdc '));
    expect(rdc[0]).toMatch(/^rdc repo fork elite@m1 --tag pre-upgrade-\d{8}t\d{6}$/);
    expect(rdc.some((c) => c.includes('template apply'))).toBe(false);
    expect(rdc.at(-1)).toBe('rdc repo up elite@m1');
    expect(fake.setEnv.at(-1)).toEqual({ ELITE_IMAGE: 'ghcr.io/rediacc/server:2.0', TAG: '2.0' });
    expect(result.templateReapplied).toBe(false);
    expect(fake.calls.indexOf('ssh m1 pull')).toBeGreaterThan(
      fake.calls.findIndex((c) => c.startsWith('rdc repo fork'))
    );
  });

  it('applies the template again only when the built-in VERSION is newer', async () => {
    m.builtinVersion = '3\n';
    const older = makeFake({ templateVersion: 2 });
    const r1 = await serverUpgrade(older.deps, LOC, {});
    expect(r1).toMatchObject({ templateReapplied: true, templateVersion: 3 });
    expect(older.calls).toContain('rdc repo admin template apply elite@m1 --template elite');

    const same = makeFake({ templateVersion: 3 });
    const r2 = await serverUpgrade(same.deps, LOC, {});
    expect(r2.templateReapplied).toBe(false);
  });

  it('ships a saved image instead of pulling when given one', async () => {
    const fake = makeFake();
    await serverUpgrade(fake.deps, LOC, { imageFile: '/srv/server.tar' });
    expect(fake.calls).toContain(
      'rdc repo sync upload elite@m1 --local /srv/server.tar --remote-file images/server.tar --verify'
    );
    expect(fake.calls).not.toContain('ssh m1 pull');
  });
});

describe('licence', () => {
  const UPLOAD = '/account/api/v1/onprem/cert-upload';

  it('uploads the mapped cert as the owner and restarts nothing', async () => {
    const fake = makeFake({
      freeProbe: 409,
      boxReplies: { '/auth/login': { cookie: 'access_token=own' } },
    });
    const result = await serverLicence(fake.deps, LOC);
    expect(result).toMatchObject({ subscriptionId: 'sub-1', via: 'upload' });
    const upload = fake.boxRequests.find((r) => r.path === UPLOAD);
    expect(upload).toEqual({
      method: 'POST',
      path: UPLOAD,
      body: {
        payload: JSON.parse(Buffer.from(certFor(BOX_KEY), 'base64').toString()).payload,
        signature: 'sig',
        publicKeyId: 'k1',
      },
      cookie: 'access_token=own',
    });
    expect(fake.calls).not.toContain('rdc repo up elite@m1');
    expect(fake.setEnv[0].DELEGATION_CERT_BASE64).toBe(certFor(BOX_KEY));
  });

  it.each([
    ['401', { [UPLOAD]: { status: 401 } }],
    ['404', { [UPLOAD]: { status: 404 } }],
    ['a login the box refuses', { '/auth/login': { status: 401 } }],
  ])('falls back to secrets.env and a restart on %s', async (_name, replies) => {
    const fake = makeFake({
      freeProbe: 409,
      boxReplies: { '/auth/login': { cookie: 'access_token=own' }, ...replies },
    });
    const result = await serverLicence(fake.deps, LOC);
    expect(result.via).toBe('restart');
    expect(fake.setEnv[0].DELEGATION_CERT_BASE64).toBe(certFor(BOX_KEY));
    expect(fake.calls).toContain('rdc repo up elite@m1');
  });

  it('falls back when no owner credentials were saved', async () => {
    m.owner = undefined;
    const fake = makeFake({ freeProbe: 409 });
    const result = await serverLicence(fake.deps, LOC);
    expect(result.via).toBe('restart');
    expect(fake.boxRequests.some((r) => r.path === UPLOAD)).toBe(false);
    expect(fake.calls).toContain('rdc repo up elite@m1');
  });

  it('refuses when no cert can be had', async () => {
    const fake = makeFake({ issue: { kind: 'no-login' } });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/noCertForUpgrade/);
  });

  it('refuses a --cert for another key', async () => {
    const fake = makeFake({ files: { '/c': certFor('other') } });
    await expect(serverLicence(fake.deps, LOC, '/c')).rejects.toThrow(/keyMismatch/);
  });
});
