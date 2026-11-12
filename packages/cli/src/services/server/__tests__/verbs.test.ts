/**
 * `rdc server status|backup|upgrade|licence` (PLAN-enterprise-tenants C7) against a scripted box.
 */

import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_IMAGE_REGISTRY } from '@rediacc/shared/config/well-known.generated';
import { delegationCertId } from '@rediacc/shared/subscription';
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

import { outputService } from '../../core/output.js';
import { liveServerDeps } from '../deps.js';
import { serverBackup, serverLicence, serverStatus, serverUpgrade } from '../verbs.js';
import { BOX_KEY, certFor, makeFake } from './fakes.js';

const LOC = { domain: 'acme.example.com', machine: 'm1' };

/** The id the server computes for a `certFor` cert. */
function idOf(certBase64: string): Promise<string> {
  return delegationCertId(JSON.parse(Buffer.from(certBase64, 'base64').toString()));
}

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

  it("reports the live cert's id, plan and subscription once licensed", async () => {
    const live = certFor(BOX_KEY, 'sub-9', 'ELITE');
    const fake = makeFake({ liveCert: live, freeProbe: 409 });
    const status = await serverStatus(fake.deps, LOC);
    expect(status).toMatchObject({
      tier: 'ELITE',
      bootstrapMode: false,
      certId: await idOf(live),
      subscriptionId: 'sub-9',
      certIssuedAt: '2026-11-12T00:00:00Z',
      freeTierRelay: false,
    });
    expect(fake.calls).toContain('ssh m1 read-live-cert');
  });

  it('ignores a DELEGATION_CERT_BASE64 left in secrets.env: only the live file counts', async () => {
    const fake = makeFake({ secrets: { DELEGATION_CERT_BASE64: certFor(BOX_KEY) } });
    const status = await serverStatus(fake.deps, LOC);
    expect(status).toMatchObject({ tier: 'free', bootstrapMode: true });
    expect(status.certId).toBeUndefined();
  });

  it('reports certRefused and the free tier, and no live cert, when the box refused its cert at boot', async () => {
    const fake = makeFake({
      liveCert: certFor(BOX_KEY, 'sub-9', 'ELITE'),
      bootRejected: { reason: 'bad-signature', detail: 'x', at: '2026-11-12T19:58:00Z' },
    });
    const status = await serverStatus(fake.deps, LOC);
    expect(status).toMatchObject({
      tier: 'free',
      bootstrapMode: true,
      certRefused: { reason: 'bad-signature', detail: 'x', at: '2026-11-12T19:58:00Z' },
    });
    expect(status.certId).toBeUndefined();
    expect(status.planCode).toBeUndefined();
    expect(fake.calls).not.toContain('ssh m1 read-live-cert');
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
    const result = await serverUpgrade(fake.deps, LOC, {
      image: `${WK_IMAGE_REGISTRY}/server:2.0`,
    });
    const rdc = fake.calls.filter((c) => c.startsWith('rdc '));
    expect(rdc[0]).toMatch(/^rdc repo fork elite@m1 --tag pre-upgrade-\d{8}t\d{6}$/);
    expect(rdc.some((c) => c.includes('template apply'))).toBe(false);
    expect(rdc.at(-1)).toBe('rdc repo up elite@m1');
    expect(fake.setEnv.at(-1)).toEqual({
      ELITE_IMAGE: `${WK_IMAGE_REGISTRY}/server:2.0`,
      TAG: '2.0',
    });
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

  it('moves a DELEGATION_CERT_BASE64 into the inbox before the restart when no live file exists, and deletes the key', async () => {
    const old = certFor(BOX_KEY, 'sub-7');
    const fake = makeFake({ secrets: { DELEGATION_CERT_BASE64: old } });
    await serverUpgrade(fake.deps, LOC, {});
    expect(fake.drops).toHaveLength(1);
    expect(fake.drops[0].cert.payload).toBe(
      JSON.parse(Buffer.from(old, 'base64').toString()).payload
    );
    const order = [
      'ssh m1 migrate-cert',
      'rdc repo up elite@m1',
      'https GET /health',
      'ssh m1 inbox-result',
    ];
    const at = order.map((c) => fake.calls.indexOf(c));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
    expect(fake.secrets.DELEGATION_CERT_BASE64).toBeUndefined();
    expect(outputService.info).toHaveBeenCalledWith('commands.server.upgrade.migratingCert');
    expect(fake.live()).toBe(Buffer.from(old, 'base64').toString());
  });

  it('only deletes the key when a live cert file already exists', async () => {
    const fake = makeFake({
      liveCert: certFor(BOX_KEY),
      secrets: { DELEGATION_CERT_BASE64: certFor(BOX_KEY, 'sub-7') },
    });
    await serverUpgrade(fake.deps, LOC, {});
    expect(fake.drops).toHaveLength(0);
    expect(fake.calls).not.toContain('ssh m1 inbox-result');
    expect(fake.secrets.DELEGATION_CERT_BASE64).toBeUndefined();
  });

  it('fails when the migrated cert is rejected at boot', async () => {
    const fake = makeFake({
      secrets: { DELEGATION_CERT_BASE64: certFor(BOX_KEY) },
      inbox: { reason: 'expired', detail: 'The cert expired' },
    });
    await expect(serverUpgrade(fake.deps, LOC, {})).rejects.toThrow(/licence\.rejected.*expired/);
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
  const STATUS = '/account/api/v1/onprem/cert-status';

  it('drops the cert into the inbox, reads applied by its request id, confirms the certId, restarts nothing', async () => {
    const fake = makeFake({ boxReplies: { '/auth/login': { cookie: 'access_token=own' } } });
    const result = await serverLicence(fake.deps, LOC);
    const issued = certFor(BOX_KEY);
    expect(result).toEqual({
      domain: 'acme.example.com',
      subscriptionId: 'sub-1',
      tier: 'ENTERPRISE',
      certId: await idOf(issued),
      via: 'inbox',
    });
    expect(fake.drops).toHaveLength(1);
    expect(fake.drops[0].cert).toEqual(JSON.parse(Buffer.from(issued, 'base64').toString()));
    expect(fake.drops[0].requestId).toMatch(/^[0-9a-f-]{36}$/);
    const status = fake.boxRequests.find((r) => r.path === STATUS);
    expect(status?.cookie).toBe('access_token=own');
    expect(fake.calls.indexOf('ssh m1 inbox-result')).toBeLessThan(
      fake.calls.indexOf(`https GET ${STATUS}`)
    );
    expect(fake.calls.some((c) => c.startsWith('rdc repo up'))).toBe(false);
    expect(fake.boxRequests.some((r) => r.path === UPLOAD)).toBe(false);
    // secrets.env takes only the auto-renew settings, never the cert.
    expect(fake.setEnv).toEqual([
      { UPSTREAM_URL: 'https://bench.example', UPSTREAM_API_KEY: 'renew-token' },
    ]);
    expect(outputService.info).toHaveBeenCalledWith('commands.server.licence.viaInbox');
    expect(Object.values(fake.written).some((v) => v.includes('"licence": "cert"'))).toBe(true);
  });

  it('fails with the reason when the server rejects the cert, and writes no record', async () => {
    const fake = makeFake({
      liveCert: certFor(BOX_KEY, 'sub-1', 'ENTERPRISE', '2026-11-12T06:00:00Z'),
      inbox: { reason: 'not-newer', detail: 'issued before the current cert' },
    });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(
      /licence\.rejected.*not-newer.*issued before the current cert/
    );
    expect(Object.values(fake.written).some((v) => v.includes('"licence": "cert"'))).toBe(false);
    expect(fake.setEnv).toEqual([]);
  });

  it('#eeedba13: fails with confirmMismatch when cert-status still reports the old cert after applied', async () => {
    const old = certFor(BOX_KEY, 'sub-1', 'ENTERPRISE', '2026-10-01T00:00:00Z');
    const fake = makeFake({
      liveCert: old,
      boxReplies: { [STATUS]: { body: { cert: { certId: await idOf(old) } } } },
    });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(
      new RegExp(`confirmMismatch.*"actual":"${await idOf(old)}"`)
    );
    expect(outputService.info).not.toHaveBeenCalledWith('commands.server.licence.viaInbox');
    expect(Object.values(fake.written).some((v) => v.includes('"licence": "cert"'))).toBe(false);
  });

  it('fails with confirmMismatch when the saved owner login is refused', async () => {
    const fake = makeFake({ boxReplies: { '/auth/login': { status: 401, cookie: undefined } } });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/confirmMismatch/);
  });

  it('stops at already-current when the box holds the same cert, and drops nothing', async () => {
    const fake = makeFake({ liveCert: certFor(BOX_KEY) });
    const result = await serverLicence(fake.deps, LOC);
    expect(result.via).toBe('already-current');
    expect(result.certId).toBe(await idOf(certFor(BOX_KEY)));
    expect(fake.drops).toHaveLength(0);
    expect(fake.calls).not.toContain('ssh m1 inbox-drop');
    expect(outputService.info).toHaveBeenCalledWith(
      `commands.server.licence.alreadyCurrent ${JSON.stringify({ certId: result.certId })}`
    );
  });

  describe('a box that refused its cert at boot', () => {
    const marker = { reason: 'bad-signature', detail: 'sig does not verify' };

    it('warns with the reason, skips already-current, drops, confirms, and sees the marker gone', async () => {
      const fake = makeFake({ liveCert: certFor(BOX_KEY), bootRejected: marker });
      const result = await serverLicence(fake.deps, LOC);
      expect(result.via).toBe('inbox');
      expect(outputService.warn).toHaveBeenCalledWith(
        expect.stringMatching(/^commands\.server\.licence\.bootRefused .*bad-signature/)
      );
      expect(fake.drops).toHaveLength(1);
      expect(fake.calls.filter((c) => c === 'ssh m1 read-boot-rejected')).toHaveLength(2);
      expect(fake.calls.indexOf(`https GET ${STATUS}`)).toBeLessThan(
        fake.calls.lastIndexOf('ssh m1 read-boot-rejected')
      );
      expect(outputService.info).not.toHaveBeenCalledWith(expect.stringMatching(/alreadyCurrent/));
    });

    it('fails when the marker is still there after the apply, and writes no record', async () => {
      const fake = makeFake({ bootRejected: marker, markerSticks: true });
      await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(
        /bootRefusalStays.*bad-signature/
      );
      expect(Object.values(fake.written).some((v) => v.includes('"licence": "cert"'))).toBe(false);
    });

    it('refuses no-upstream-key without minting or dropping a cert', async () => {
      const fake = makeFake({ bootRejected: { reason: 'no-upstream-key' } });
      await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/noUpstreamKey/);
      expect(fake.drops).toHaveLength(0);
      expect(fake.calls).not.toContain('issue');
    });
  });

  it('surfaces a busy inbox', async () => {
    const fake = makeFake({ inbox: 'busy' });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/inboxBusy/);
    expect(fake.calls).not.toContain('ssh m1 inbox-result');
  });

  it('names the wait when the server never answers', async () => {
    const fake = makeFake({ inbox: 'none' });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/noResult.*"seconds":60/);
  });

  it('without saved owner credentials warns confirmSkipped and trusts applied.json', async () => {
    m.owner = undefined;
    const fake = makeFake();
    const result = await serverLicence(fake.deps, LOC);
    expect(result.via).toBe('inbox');
    expect(outputService.warn).toHaveBeenCalledWith(
      expect.stringMatching(/^commands\.server\.licence\.confirmSkipped /)
    );
    expect(fake.boxRequests.some((r) => r.path === STATUS)).toBe(false);
  });

  it('refuses when no cert can be had', async () => {
    const fake = makeFake({ issue: { kind: 'no-login' } });
    await expect(serverLicence(fake.deps, LOC)).rejects.toThrow(/noCertForUpgrade/);
  });

  it('refuses a --cert for another key', async () => {
    const fake = makeFake({ files: { '/c': certFor('other') } });
    await expect(serverLicence(fake.deps, LOC, '/c')).rejects.toThrow(/keyMismatch/);
  });

  it('takes a --cert for the box key through the inbox, with no auto-renew settings', async () => {
    const fake = makeFake({ files: { '/c': certFor(BOX_KEY, 'sub-3') } });
    const result = await serverLicence(fake.deps, LOC, '/c');
    expect(result).toMatchObject({ subscriptionId: 'sub-3', via: 'inbox' });
    expect(fake.calls).not.toContain('issue');
    expect(fake.setEnv).toEqual([]);
  });
});
