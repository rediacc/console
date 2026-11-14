import { describe, expect, it } from 'vitest';

import { covers, type CtAnswer, lookupCt, type ProbeDeps, runProbe } from '../probes';
import type { ProbeTarget } from '../targets';
import { fakeFetch, fakeSocket, T0 } from './helpers';

const DAY = 86_400_000;

function deps(overrides: Partial<ProbeDeps> = {}): ProbeDeps {
  return {
    fetch: fakeFetch(() => {
      throw new Error('no fetch expected');
    }).fn,
    connect: () => fakeSocket({ handshake: 'ok' }),
    now: () => T0,
    ct: async (): Promise<CtAnswer> => ({
      notAfter: new Date(T0 + 60 * DAY).toISOString(),
      source: 'certspotter',
    }),
    ...overrides,
  };
}

const tls: ProbeTarget = { id: 'tls-a', kind: 'tls', host: 'mail.example.test', port: 465 };

describe('tls', () => {
  it('an expired certificate (failed handshake) is red', async () => {
    const r = await runProbe(
      tls,
      deps({ connect: () => fakeSocket({ handshake: new Error('certificate has expired') }) })
    );
    expect(r.state).toBe('red');
    expect(r.detail).toContain('certificate has expired');
  });

  it('CT at 20 days is red (under the 21-day warning)', async () => {
    const r = await runProbe(
      tls,
      deps({
        ct: async () => ({
          notAfter: new Date(T0 + 20 * DAY + 3_600_000).toISOString(),
          source: 'certspotter',
        }),
      })
    );
    expect(r.state).toBe('red');
    expect(r.detail).toContain('20 day(s)');
    expect(r.detail).toContain('warning');
  });

  it('CT at 6 days is red and critical', async () => {
    const r = await runProbe(
      tls,
      deps({
        ct: async () => ({ notAfter: new Date(T0 + 6 * DAY).toISOString(), source: 'crt.sh' }),
      })
    );
    expect(r.state).toBe('red');
    expect(r.detail).toContain('critical');
  });

  it('CT at 60 days with a good handshake is green', async () => {
    const r = await runProbe(tls, deps());
    expect(r.state).toBe('green');
  });

  it('an unreadable CT source is unknown, never green', async () => {
    const r = await runProbe(
      tls,
      deps({
        ct: async () => ({ notAfter: null, source: 'none', detail: 'certspotter answered 429' }),
      })
    );
    expect(r.state).toBe('unknown');
  });
});

describe('banner-465', () => {
  const banner: ProbeTarget = { id: 'smtps', kind: 'banner-465', host: 'mail.example.test' };

  it('a 220 banner is green by default', async () => {
    const r = await runProbe(
      banner,
      deps({
        connect: () => fakeSocket({ handshake: 'ok', reads: ['220 mail.example.test ESMTP\r\n'] }),
      })
    );
    expect(r.state).toBe('green');
  });

  it('a banner that does not match the target expect is red', async () => {
    const r = await runProbe(
      { ...banner, expect: '^220 mail\\.example\\.test' },
      deps({ connect: () => fakeSocket({ handshake: 'ok', reads: ['220 other.host ESMTP\r\n'] }) })
    );
    expect(r.state).toBe('red');
    expect(r.detail).toContain('does not match');
  });

  it('a banner split across reads is joined', async () => {
    const r = await runProbe(
      banner,
      deps({ connect: () => fakeSocket({ handshake: 'ok', reads: ['22', '0 ok\r\n'] }) })
    );
    expect(r.state).toBe('green');
  });

  it('a closed connection with no banner is red', async () => {
    const r = await runProbe(
      banner,
      deps({ connect: () => fakeSocket({ handshake: 'ok', reads: [] }) })
    );
    expect(r.state).toBe('red');
  });

  it('connects on 465 with TLS on', async () => {
    const seen: [SocketAddress, SocketOptions | undefined][] = [];
    await runProbe(
      banner,
      deps({
        connect: (address, options) => {
          seen.push([address, options]);
          return fakeSocket({ handshake: 'ok', reads: ['220 x\r\n'] });
        },
      })
    );
    expect(seen[0][0]).toEqual({ hostname: 'mail.example.test', port: 465 });
    expect(seen[0][1]?.secureTransport).toBe('on');
  });
});

describe('dnsbl-over-DoH', () => {
  const dnsbl: ProbeTarget = {
    id: 'dnsbl:bl.example.test',
    kind: 'dnsbl-over-DoH',
    host: 'bl.example.test',
    ip: '192.0.2.10',
  };
  const doh = (body: unknown) =>
    fakeFetch((url) => {
      expect(url.hostname).toBe('cloudflare-dns.com');
      return Response.json(body);
    });

  it('127.0.0.2 is red (listed)', async () => {
    const f = doh({ Status: 0, Answer: [{ type: 1, data: '127.0.0.2' }] });
    const r = await runProbe(dnsbl, deps({ fetch: f.fn }));
    expect(r.state).toBe('red');
    expect(new URL(f.calls[0].url).searchParams.get('name')).toBe('10.2.0.192.bl.example.test');
  });

  it('127.255.255.254 is unknown (the zone refused the resolver)', async () => {
    const r = await runProbe(
      dnsbl,
      deps({ fetch: doh({ Status: 0, Answer: [{ type: 1, data: '127.255.255.254' }] }).fn })
    );
    expect(r.state).toBe('unknown');
  });

  it('NXDOMAIN is green', async () => {
    const r = await runProbe(dnsbl, deps({ fetch: doh({ Status: 3 }).fn }));
    expect(r.state).toBe('green');
  });

  it('a Spamhaus zone without a DQS key is unknown and sends nothing', async () => {
    const f = doh({ Status: 3 });
    const r = await runProbe({ ...dnsbl, host: 'zen.spamhaus.org' }, deps({ fetch: f.fn }));
    expect(r.state).toBe('unknown');
    expect(f.calls).toHaveLength(0);
  });

  it('a Spamhaus zone with a DQS key queries dq.spamhaus.net and keeps the key out of the detail', async () => {
    const f = doh({ Status: 3 });
    const r = await runProbe(
      { ...dnsbl, host: 'zen.spamhaus.org' },
      deps({ fetch: f.fn, spamhausKey: 'dqskey123' })
    );
    expect(new URL(f.calls[0].url).searchParams.get('name')).toBe(
      '10.2.0.192.dqskey123.zen.dq.spamhaus.net'
    );
    expect(r.state).toBe('green');
    expect(r.detail).not.toContain('dqskey123');
  });

  it('a failed DoH lookup is unknown, not green', async () => {
    const f = fakeFetch(() => {
      throw new Error('network down');
    });
    const r = await runProbe(dnsbl, deps({ fetch: f.fn }));
    expect(r.state).toBe('unknown');
  });
});

describe('https and health-endpoint', () => {
  it('https under 400 is green, 502 is red', async () => {
    const ok = await runProbe(
      { id: 'h', kind: 'https', host: 'app.example.test' },
      deps({ fetch: fakeFetch(() => new Response('', { status: 302 })).fn })
    );
    expect(ok.state).toBe('green');
    const bad = await runProbe(
      { id: 'h', kind: 'https', host: 'app.example.test' },
      deps({ fetch: fakeFetch(() => new Response('', { status: 502 })).fn })
    );
    expect(bad.state).toBe('red');
  });

  it('health-endpoint needs exactly 200 and reads the path', async () => {
    const f = fakeFetch(() => new Response('{}', { status: 200 }));
    const r = await runProbe(
      { id: 'e', kind: 'health-endpoint', host: 'api.example.test', path: '/v1/health' },
      deps({ fetch: f.fn })
    );
    expect(r.state).toBe('green');
    expect(f.calls[0].url).toBe('https://api.example.test/v1/health');
    expect(f.calls[0].init?.method).toBe('GET');
    const redirect = await runProbe(
      { id: 'e', kind: 'health-endpoint', host: 'api.example.test' },
      deps({ fetch: fakeFetch(() => new Response('', { status: 301 })).fn })
    );
    expect(redirect.state).toBe('red');
  });

  it('an unreachable endpoint is red', async () => {
    const r = await runProbe(
      { id: 'e', kind: 'health-endpoint', host: 'api.example.test' },
      deps({ fetch: fakeFetch(() => Promise.reject(new Error('ECONNREFUSED'))).fn })
    );
    expect(r.state).toBe('red');
  });
});

it('an unknown kind is an unknown probe', async () => {
  const r = await runProbe({ id: 'x', kind: 'smtp-25', host: 'mail.example.test' }, deps());
  expect(r.state).toBe('unknown');
  expect(r.detail).toContain('unknown probe kind');
});

describe('lookupCt', () => {
  it('asks certspotter with match_wildcards and takes the newest covering not_after', async () => {
    const f = fakeFetch((url) => {
      expect(url.hostname).toBe('api.certspotter.com');
      expect(url.searchParams.get('match_wildcards')).toBe('true');
      return Response.json([
        { id: '1', not_after: '2026-11-09T20:28:47Z', dns_names: ['*.example.test'] },
        {
          id: '2',
          not_after: '2026-12-05T10:27:04Z',
          dns_names: ['*.example.test', 'example.test'],
        },
        { id: '3', not_after: '2027-06-01T00:00:00Z', dns_names: ['other.test'] },
      ]);
    });
    const answer = await lookupCt('app.example.test', { fetch: f.fn });
    expect(answer).toEqual({ notAfter: '2026-12-05T10:27:04.000Z', source: 'certspotter' });
  });

  it("an issuer filter ignores another CA's newer issuance for the same wildcard (the W0 measurement)", async () => {
    const rows = [
      {
        id: '1',
        not_after: '2026-12-05T10:27:04Z',
        dns_names: ['*.example.test'],
        issuer: { friendly_name: "Let's Encrypt", name: "C=US, O=Let's Encrypt, CN=YR2" },
      },
      {
        id: '2',
        not_after: '2027-01-31T22:15:26Z',
        dns_names: ['*.example.test'],
        issuer: {
          friendly_name: 'Google Trust Services',
          name: 'C=US, O=Google Trust Services, CN=WE1',
        },
      },
    ];
    const f = fakeFetch((url) => {
      expect(url.searchParams.getAll('expand')).toEqual(['dns_names', 'issuer']);
      return Response.json(rows);
    });
    expect((await lookupCt('app.example.test', { fetch: f.fn })).notAfter).toBe(
      '2027-01-31T22:15:26.000Z'
    );
    expect((await lookupCt('app.example.test', { fetch: f.fn }, "let's encrypt")).notAfter).toBe(
      '2026-12-05T10:27:04.000Z'
    );
  });

  it('the tls probe passes its expect to CT as the issuer filter', async () => {
    const seen: (string | undefined)[] = [];
    await runProbe(
      { ...tls, expect: "Let's Encrypt" },
      deps({
        ct: (_host, issuer) => {
          seen.push(issuer);
          return Promise.resolve<CtAnswer>({
            notAfter: new Date(T0 + 60 * DAY).toISOString(),
            source: 'certspotter',
          });
        },
      })
    );
    expect(seen).toEqual(["Let's Encrypt"]);
  });

  it('falls back to crt.sh, then answers null when neither can say', async () => {
    const f = fakeFetch((url) =>
      url.hostname === 'crt.sh'
        ? Response.json([{ not_after: '2026-12-01T00:00:00' }])
        : new Response('slow down', { status: 429 })
    );
    expect(await lookupCt('app.example.test', { fetch: f.fn })).toEqual({
      notAfter: '2026-12-01T00:00:00.000Z',
      source: 'crt.sh',
    });
    const dead = fakeFetch(() => new Response('', { status: 503 }));
    const none = await lookupCt('app.example.test', { fetch: dead.fn });
    expect(none.notAfter).toBeNull();
  });

  it('covers matches exact names and one-label wildcards only', () => {
    expect(covers('*.example.test', 'a.example.test')).toBe(true);
    expect(covers('*.example.test', 'a.b.example.test')).toBe(false);
    expect(covers('example.test', 'example.test')).toBe(true);
  });
});
