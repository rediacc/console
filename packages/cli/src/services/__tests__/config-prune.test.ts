import { gunzipSync, gzipSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import type { ArchivedRepository, RdcConfig } from '../../schema/schemas.js';
import { buildConfigAnchors, classifyArchives, pruneCertCacheBuckets } from '../config-prune.js';

/** Build the same compressed-base64 shape the cert-cache writer uses. */
function packAcme(acme: object): string {
  const raw = Buffer.from(JSON.stringify(acme), 'utf8');
  return gzipSync(raw, { level: 9 }).toString('base64');
}

/** Synthesize an acme.json with `Certificates[]` of the given names. */
function fakeAcme(domains: string[]): object {
  return {
    letsencrypt: {
      Account: { Email: 'ops@example.com' },
      Certificates: domains.map((d) => ({
        domain: { main: d },
        certificate: 'CERTBASE64==',
        key: 'KEYBASE64==',
      })),
    },
  };
}

describe('buildConfigAnchors', () => {
  it('includes both live and archived repository GUIDs', () => {
    const cfg: RdcConfig = {
      schemaVersion: 2,
      id: '00000000-0000-0000-0000-000000000000',
      version: 1,
      resources: {
        machines: { hostinger: { ip: '1.2.3.4', user: 'root' } },
        repositories: {
          'gitlab:latest': { repositoryGuid: '11111111-1111-1111-1111-111111111111' },
        },
        deletedRepositories: [
          {
            name: 'mail:latest',
            repositoryGuid: '22222222-2222-2222-2222-222222222222',
            deletedAt: new Date().toISOString(),
          },
        ],
      },
    };

    const anchors = buildConfigAnchors(cfg);
    expect(anchors.guids.has('11111111-1111-1111-1111-111111111111')).toBe(true);
    expect(anchors.guids.has('22222222-2222-2222-2222-222222222222')).toBe(true);
    expect(anchors.repoNames.has('gitlab')).toBe(true);
    expect(anchors.repoNames.has('mail')).toBe(true);
    expect(anchors.machines.has('hostinger')).toBe(true);
  });
});

describe('classifyArchives', () => {
  const NOW = new Date('2026-05-04T00:00:00Z');

  it('splits at the grace boundary', () => {
    const archives: ArchivedRepository[] = [
      // 10 days ago — expired (grace = 7)
      {
        name: 'old:latest',
        repositoryGuid: '11111111-1111-1111-1111-111111111111',
        deletedAt: '2026-04-24T00:00:00Z',
      },
      // 3 days ago — still in grace
      {
        name: 'recent:latest',
        repositoryGuid: '22222222-2222-2222-2222-222222222222',
        deletedAt: '2026-05-01T00:00:00Z',
      },
    ];

    const { expired, inGrace } = classifyArchives(archives, 7, NOW);
    expect(expired.map((e) => e.name)).toEqual(['old:latest']);
    expect(inGrace).toHaveLength(1);
    expect(inGrace[0].name).toBe('recent:latest');
    expect(inGrace[0].daysAgo).toBe(3);
    expect(inGrace[0].daysRemaining).toBe(4);
  });

  it('skips entries with unparseable deletedAt', () => {
    const archives: ArchivedRepository[] = [
      {
        name: 'bogus:latest',
        repositoryGuid: '33333333-3333-3333-3333-333333333333',
        deletedAt: 'not-a-date',
      },
    ];
    const { expired, inGrace } = classifyArchives(archives, 7, NOW);
    expect(expired).toHaveLength(0);
    expect(inGrace).toHaveLength(0);
  });
});

describe('pruneCertCacheBuckets — round-trip through gzip/base64', () => {
  const liveGuid = '11111111-1111-1111-1111-111111111111';
  const deadGuid = '22222222-2222-2222-2222-222222222222';

  function buildConfigWithCacheBucket(domains: string[]): RdcConfig {
    return {
      schemaVersion: 2,
      id: '00000000-0000-0000-0000-000000000000',
      version: 1,
      resources: {
        machines: { hostinger: { ip: '1.2.3.4', user: 'root' } },
        repositories: { 'gitlab:latest': { repositoryGuid: liveGuid } },
      },
      infra: {
        acmeCertCache: {
          'rediacc.io': {
            baseDomain: 'rediacc.io',
            updatedAt: '2026-01-01T00:00:00Z',
            sourceMachine: 'hostinger',
            certCount: domains.length,
            certs: Object.fromEntries(domains.map((d) => [d, '2027-01-01T00:00:00Z'])),
            data: packAcme(fakeAcme(domains)),
            rawSize: 0,
          },
        },
      },
    };
  }

  it('drops only the unknown-anchor entries and keeps the rest', () => {
    const cfg = buildConfigWithCacheBucket([
      `*.${liveGuid}.hostinger.rediacc.io`,
      `*.${deadGuid}.hostinger.rediacc.io`, // <- should be dropped
      '*.hostinger.rediacc.io', // <- machine-level wildcard, kept
      '*.unknown-machine.rediacc.io', // <- should be dropped
      'cloud.rediacc.io', // <- top-level subdomain, kept
    ]);
    const anchors = buildConfigAnchors(cfg);

    const removed = pruneCertCacheBuckets(cfg, anchors);

    expect(removed.map((r) => r.name).sort()).toEqual(
      [`*.${deadGuid}.hostinger.rediacc.io`, '*.unknown-machine.rediacc.io'].sort()
    );

    const bucket = cfg.infra!.acmeCertCache!['rediacc.io'];
    // Derived metadata must follow the cert filtering.
    expect(bucket.certCount).toBe(3);
    expect(Object.keys(bucket.certs).sort()).toEqual(
      [`*.${liveGuid}.hostinger.rediacc.io`, '*.hostinger.rediacc.io', 'cloud.rediacc.io'].sort()
    );

    // The data blob should round-trip back to a parseable acme.json with the
    // same kept domains. This is the bit that the dry-run path never
    // exercises — gzip → filter → gzip → base64 must not corrupt the chain.
    const data = Array.isArray(bucket.data) ? bucket.data.join('') : bucket.data;
    const raw = gunzipSync(Buffer.from(data, 'base64')).toString('utf8');
    const parsed = JSON.parse(raw) as {
      letsencrypt: { Certificates: { domain: { main: string } }[] };
    };
    const finalDomains = parsed.letsencrypt.Certificates.map((c) => c.domain.main).sort();
    expect(finalDomains).toEqual(
      [`*.${liveGuid}.hostinger.rediacc.io`, '*.hostinger.rediacc.io', 'cloud.rediacc.io'].sort()
    );
  });

  it('is a no-op when every cert anchor is live', () => {
    const cfg = buildConfigWithCacheBucket([
      `*.${liveGuid}.hostinger.rediacc.io`,
      '*.hostinger.rediacc.io',
    ]);
    const beforeData = cfg.infra!.acmeCertCache!['rediacc.io'].data;
    const before = JSON.stringify(cfg);

    const removed = pruneCertCacheBuckets(cfg, buildConfigAnchors(cfg));
    expect(removed).toHaveLength(0);

    // Bucket left untouched (data, certs, certCount all unchanged).
    expect(cfg.infra!.acmeCertCache!['rediacc.io'].data).toBe(beforeData);
    expect(JSON.stringify(cfg)).toBe(before);
  });

  it('skips a bucket whose data field is corrupt rather than throwing', () => {
    const cfg = buildConfigWithCacheBucket([`*.${deadGuid}.hostinger.rediacc.io`]);
    cfg.infra!.acmeCertCache!['rediacc.io'].data = 'not-real-base64-or-gzip';
    const before = JSON.stringify(cfg);

    const removed = pruneCertCacheBuckets(cfg, buildConfigAnchors(cfg));
    // Corrupt cache is left alone — better than risking data loss on a bug
    // we don't understand.
    expect(removed).toHaveLength(0);
    expect(JSON.stringify(cfg)).toBe(before);
  });
});
