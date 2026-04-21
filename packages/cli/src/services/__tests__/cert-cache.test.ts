import { describe, expect, it } from 'vitest';

import {
  compressAndChunk,
  decompressFromCache,
  isCertCacheStale,
  mergeAcmeJson,
  pruneExpiredCerts,
  pruneStaleAcmeCerts,
} from '../cert-cache.js';

/**
 * Build a minimal acme.json-shaped fixture.
 *
 * We do NOT generate real X.509 certs here. The expiry-based pruner accepts
 * an injected parser as its final arg, so tests control the (domain → expiry)
 * decision without needing actual PEMs. The `certificate` field value is
 * used only as a lookup key in the injected parser.
 */
function buildAcme(
  resolver: string,
  certs: { domain: string; key: string }[]
): Record<string, { Certificates: unknown[] }> {
  // Use `unknown` here so we don't have to re-declare the full AcmeCertEntry
  // shape in the test file — the cert-cache functions accept the wider JSON.
  const result: Record<string, { Certificates: unknown[] }> = {
    [resolver]: {
      Certificates: certs.map((c) => ({
        domain: { main: c.domain },
        certificate: c.key, // arbitrary opaque string — we key the fake parser off it
        key: 'irrelevant',
      })),
    },
  };
  return result;
}

describe('pruneStaleAcmeCerts', () => {
  it('removes network-id-tagged auto-route certs', () => {
    const acme = buildAcme('letsencrypt', [
      { domain: 'plausible-db-3200.rediacc.io', key: 'k1' },
      { domain: 'marketing.rediacc.io', key: 'k2' },
      { domain: 'observability-app-12345.rediacc.io', key: 'k3' },
    ]);

    // Types on cert-cache module accept AcmeJson; the fixture shape matches.
    const { removedCount } = pruneStaleAcmeCerts(acme as never);

    expect(removedCount).toBe(2);
    expect(acme.letsencrypt.Certificates as { domain: { main: string } }[]).toHaveLength(1);
    expect((acme.letsencrypt.Certificates as { domain: { main: string } }[])[0].domain.main).toBe(
      'marketing.rediacc.io'
    );
  });

  it('preserves empty resolvers', () => {
    const acme = buildAcme('letsencrypt', []);
    const { removedCount } = pruneStaleAcmeCerts(acme as never);
    expect(removedCount).toBe(0);
    expect(acme.letsencrypt.Certificates).toHaveLength(0);
  });
});

describe('pruneExpiredCerts', () => {
  const now = new Date('2026-05-01T00:00:00Z');
  const expiries: Record<string, string> = {
    'long-expired': '2026-01-01T00:00:00Z', // 120 days ago
    'just-expired': '2026-04-29T00:00:00Z', // 2 days ago — inside 7-day grace
    'barely-past-grace': '2026-04-23T00:00:00Z', // 8 days ago — just past grace
    future: '2026-07-01T00:00:00Z', // 2 months from now
    'no-parse': '', // will signal unparseable
  };
  const fakeParser = (key: string): string | undefined =>
    expiries[key] === '' ? undefined : expiries[key];

  it('removes certs whose expiry is past (now - graceDays)', () => {
    const acme = buildAcme('letsencrypt', [
      { domain: 'a.rediacc.io', key: 'long-expired' },
      { domain: 'b.rediacc.io', key: 'barely-past-grace' },
      { domain: 'c.rediacc.io', key: 'future' },
    ]);

    const { removedCount } = pruneExpiredCerts(acme as never, 7, now, fakeParser);

    expect(removedCount).toBe(2);
    const kept = (acme.letsencrypt.Certificates as { domain: { main: string } }[]).map(
      (c) => c.domain.main
    );
    expect(kept).toEqual(['c.rediacc.io']);
  });

  it('keeps certs inside the grace window even if expired', () => {
    const acme = buildAcme('letsencrypt', [
      { domain: 'a.rediacc.io', key: 'just-expired' },
      { domain: 'b.rediacc.io', key: 'future' },
    ]);

    const { removedCount } = pruneExpiredCerts(acme as never, 7, now, fakeParser);

    expect(removedCount).toBe(0);
    expect(acme.letsencrypt.Certificates).toHaveLength(2);
  });

  it('keeps certs with unparseable expiry (unknown is safer than wrong)', () => {
    const acme = buildAcme('letsencrypt', [{ domain: 'a.rediacc.io', key: 'no-parse' }]);
    const { removedCount } = pruneExpiredCerts(acme as never, 7, now, fakeParser);
    expect(removedCount).toBe(0);
    expect(acme.letsencrypt.Certificates).toHaveLength(1);
  });

  it('respects a custom graceDays value', () => {
    const acme = buildAcme('letsencrypt', [
      { domain: 'a.rediacc.io', key: 'just-expired' }, // 2 days ago
    ]);
    // graceDays=1 → cutoff is 1 day ago → just-expired (2d) IS past grace → removed.
    const { removedCount } = pruneExpiredCerts(acme as never, 1, now, fakeParser);
    expect(removedCount).toBe(1);
    expect(acme.letsencrypt.Certificates).toHaveLength(0);
  });

  it('composes with pruneStaleAcmeCerts — order-independent removal', () => {
    const acme = buildAcme('letsencrypt', [
      { domain: 'plausible-db-3200.rediacc.io', key: 'long-expired' }, // stale AND expired
      { domain: 'marketing.rediacc.io', key: 'long-expired' }, // expired only
      { domain: 'live.rediacc.io', key: 'future' }, // kept
    ]);

    const stale = pruneStaleAcmeCerts(acme as never);
    const expired = pruneExpiredCerts(stale.cleaned, 7, now, fakeParser);

    expect(stale.removedCount).toBe(1); // plausible-db-3200
    expect(expired.removedCount).toBe(1); // marketing (long-expired)
    const kept = (acme.letsencrypt.Certificates as { domain: { main: string } }[]).map(
      (c) => c.domain.main
    );
    expect(kept).toEqual(['live.rediacc.io']);
  });
});

describe('compressAndChunk / decompressFromCache', () => {
  it('round-trips small payloads as a single string', () => {
    const raw = Buffer.from('hello world', 'utf8');
    const { data, rawSize } = compressAndChunk(raw);
    expect(typeof data).toBe('string');
    expect(rawSize).toBe(raw.length);

    const back = decompressFromCache({
      baseDomain: 'x',
      updatedAt: '',
      sourceMachine: '',
      certCount: 0,
      certs: {},
      data,
      rawSize,
    });
    expect(back.toString('utf8')).toBe('hello world');
  });

  it('chunks large payloads and re-joins on decompress', () => {
    // Build something bigger than one chunk but not repetitive so gzip can't
    // collapse it below the chunk boundary.
    const chunks: string[] = [];
    for (let i = 0; i < 10000; i++) {
      chunks.push(`line-${i}-${Math.random()}`);
    }
    const raw = Buffer.from(chunks.join('\n'), 'utf8');
    const { data, rawSize } = compressAndChunk(raw);
    expect(Array.isArray(data)).toBe(true);

    const back = decompressFromCache({
      baseDomain: 'x',
      updatedAt: '',
      sourceMachine: '',
      certCount: 0,
      certs: {},
      data,
      rawSize,
    });
    expect(back.toString('utf8')).toBe(raw.toString('utf8'));
  });
});

describe('isCertCacheStale', () => {
  const now = new Date('2026-05-01T12:00:00Z');

  it('returns true when updatedAt is absent', () => {
    expect(isCertCacheStale(undefined, now)).toBe(true);
  });

  it('returns true when updatedAt is unparseable', () => {
    expect(isCertCacheStale('not a date', now)).toBe(true);
  });

  it('returns false when cache was updated within the default 6h window', () => {
    const updated = new Date(now.getTime() - 5 * 60 * 60 * 1000).toISOString(); // 5h ago
    expect(isCertCacheStale(updated, now)).toBe(false);
  });

  it('returns true when cache was updated beyond the default 6h window', () => {
    const updated = new Date(now.getTime() - 7 * 60 * 60 * 1000).toISOString(); // 7h ago
    expect(isCertCacheStale(updated, now)).toBe(true);
  });

  it('respects a custom minIntervalHours', () => {
    const updated = new Date(now.getTime() - 2 * 60 * 60 * 1000).toISOString(); // 2h ago
    expect(isCertCacheStale(updated, now, 1)).toBe(true);
    expect(isCertCacheStale(updated, now, 3)).toBe(false);
  });
});

describe('mergeAcmeJson', () => {
  // mergeAcmeJson uses the real parseCertExpiry via buildCertMap. Tests that
  // cover merge semantics with real certs belong in an integration suite —
  // here we verify that merging an empty secondary is a no-op, which is
  // the critical safety property.
  it('is a no-op when secondary has no resolvers', () => {
    const primary = buildAcme('letsencrypt', [{ domain: 'a', key: 'k' }]);
    const { mergedFromSecondary } = mergeAcmeJson(primary as never, {});
    expect(mergedFromSecondary).toBe(0);
  });

  it('copies resolver entries that exist only in secondary', () => {
    const primary: Record<string, unknown> = {};
    const secondary = buildAcme('letsencrypt', [{ domain: 'a', key: 'k' }]);
    const { mergedFromSecondary } = mergeAcmeJson(primary as never, secondary as never);
    // Without real parseable certs, the secondary's expiry parses to '' and
    // still wins over missing primary — so we expect exactly one merge.
    expect(mergedFromSecondary).toBe(1);
    expect((primary.letsencrypt as { Certificates: unknown[] }).Certificates).toHaveLength(1);
  });
});
