import { describe, expect, it } from 'vitest';

import { loadTargets, parseTargetFile, regionEndpoints } from '../targets';

const valid = {
  version: 1,
  probes: [
    { id: 'smtps', kind: 'banner-465', host: 'mail.example.test' },
    { id: 'imaps', kind: 'tls', host: 'mail.example.test', port: 993 },
    { id: 'web', kind: 'https', host: 'app.example.test', path: '/' },
  ],
  dnsbl: { ip: '192.0.2.10', zones: ['bl.example.test', 'zen.spamhaus.org'] },
};

describe('loadTargets', () => {
  it('an absent OPS_HEALTH_TARGETS is the targets probe unknown', () => {
    const load = loadTargets(undefined);
    expect(load.status.state).toBe('unknown');
    expect(load.probes).toEqual([]);
  });

  it('an unparseable OPS_HEALTH_TARGETS is the targets probe unknown', () => {
    expect(loadTargets('{not json').status.state).toBe('unknown');
    expect(loadTargets(JSON.stringify({ version: 2, probes: [] })).status.state).toBe('unknown');
  });

  it('a valid file is green and expands dnsbl zones into probes', () => {
    const load = loadTargets(JSON.stringify(valid));
    expect(load.status.state).toBe('green');
    expect(load.probes.map((p) => p.id)).toEqual([
      'smtps',
      'imaps',
      'web',
      'dnsbl:bl.example.test',
      'dnsbl:zen.spamhaus.org',
    ]);
    expect(load.probes[3]).toMatchObject({ kind: 'dnsbl-over-DoH', ip: '192.0.2.10' });
  });

  it('an unknown kind is kept so its probe can answer unknown', () => {
    const load = loadTargets(
      JSON.stringify({
        version: 1,
        probes: [{ id: 'x', kind: 'smtp-25', host: 'mail.example.test' }],
      })
    );
    expect(load.status.state).toBe('green');
    expect(load.probes[0].kind).toBe('smtp-25');
  });
});

describe('parseTargetFile refusals', () => {
  const cases: [string, unknown][] = [
    [
      'duplicate id',
      {
        version: 1,
        probes: [
          { id: 'a', kind: 'tls', host: 'h.test' },
          { id: 'a', kind: 'tls', host: 'h.test' },
        ],
      },
    ],
    ['reserved id', { version: 1, probes: [{ id: 'mailer', kind: 'tls', host: 'h.test' }] }],
    [
      'region id',
      { version: 1, probes: [{ id: 'health:account-eu', kind: 'tls', host: 'h.test' }] },
    ],
    ['bad port', { version: 1, probes: [{ id: 'a', kind: 'tls', host: 'h.test', port: 70000 }] }],
    ['host with a path', { version: 1, probes: [{ id: 'a', kind: 'tls', host: 'h.test/x' }] }],
    ['bad dnsbl ip', { version: 1, probes: [], dnsbl: { ip: '999.1.1.1', zones: [] } }],
    ['probes missing', { version: 1 }],
  ];
  for (const [name, doc] of cases) {
    it(name, () => {
      expect(() => parseTargetFile(JSON.stringify(doc))).toThrow();
    });
  }
});

describe('regionEndpoints', () => {
  it('builds the account and proxy health endpoint of every region', () => {
    const endpoints = regionEndpoints([{ id: 'eu', domain: 'eu.example.test' }]);
    expect(endpoints).toEqual([
      {
        id: 'health:account-eu',
        kind: 'health-endpoint',
        host: 'eu.example.test',
        path: '/account/api/v1/health',
      },
      {
        id: 'health:proxy-eu',
        kind: 'health-endpoint',
        host: 'proxy.eu.example.test',
        path: '/v1/health',
      },
    ]);
  });

  it('covers all of regions.json, two endpoints per region', () => {
    const endpoints = regionEndpoints();
    expect(endpoints.length).toBeGreaterThanOrEqual(6);
    expect(endpoints.length % 2).toBe(0);
  });
});
