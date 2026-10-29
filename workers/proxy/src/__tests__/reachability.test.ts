/**
 * The Worker-side reachability probe (agent/plans/PLAN-org-executor-connect-timeout-relocate.md E12): `probeTarget` decides which reported addresses may be probed, and `probeSshBanner` answers `reachable` only on an SSH banner, reading and never writing.
 *
 * The sockets are fakes from src/__tests__/cloudflare-sockets-stub.ts, passed in as `connect`.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { PROBE_TIMEOUT_MS, probeSshBanner, probeTarget } from '../reachability';
import { fakeSocket, type ScriptedRead } from './cloudflare-sockets-stub';

const TARGET = { host: '203.0.113.7', port: 22 };

function probeWith(script: ScriptedRead[], options: { openedRejects?: boolean } = {}) {
  const fake = fakeSocket(script, options);
  const connect = vi.fn(() => fake.socket);
  return { fake, connect, run: () => probeSshBanner(TARGET, { connect }) };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('probeSshBanner', () => {
  it('a banner is reachable, and the socket is closed once with no writer taken', async () => {
    const { fake, connect, run } = probeWith(['SSH-2.0-OpenSSH_9.6\r\n']);
    expect(await run()).toEqual({ verdict: 'reachable', reason: 'banner' });
    expect(connect).toHaveBeenCalledWith(
      { hostname: '203.0.113.7', port: 22 },
      { secureTransport: 'off', allowHalfOpen: false }
    );
    expect(fake.closes).toBe(1);
    expect(fake.writersTaken).toBe(0);
  });

  it('a banner split over two reads is reachable', async () => {
    const { fake, run } = probeWith(['SS', 'H-2.0-x\r\n']);
    expect(await run()).toEqual({ verdict: 'reachable', reason: 'banner' });
    expect(fake.reads).toBe(2);
  });

  it('opened resolving while read() rejects is target-unreachable (workerd #1305: opened is not proof)', async () => {
    const { fake, run } = probeWith([{ reject: new Error('connection reset') }]);
    expect(await run()).toEqual({ verdict: 'target-unreachable', reason: 'error' });
    expect(fake.closes).toBe(1);
  });

  it('a stream that ends with no bytes is target-unreachable (no-banner)', async () => {
    const { run } = probeWith(['end']);
    expect(await run()).toEqual({ verdict: 'target-unreachable', reason: 'no-banner' });
  });

  it('an HTTP reply is target-unreachable (no-banner)', async () => {
    const { run } = probeWith(['HTTP/1.1 400 Bad Request\r\n\r\n']);
    expect(await run()).toEqual({ verdict: 'target-unreachable', reason: 'no-banner' });
  });

  it('a read that never settles times out at 4 s, and still closes', async () => {
    vi.useFakeTimers();
    const { fake, run } = probeWith(['hang']);
    let settled = false;
    const pending = run().then((r) => {
      settled = true;
      return r;
    });
    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS - 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toEqual({ verdict: 'target-unreachable', reason: 'timeout' });
    expect(PROBE_TIMEOUT_MS).toBe(4000);
    expect(fake.closes).toBe(1);
    expect(fake.writersTaken).toBe(0);
  });

  it('a connect that throws is target-unreachable (error)', async () => {
    const connect = vi.fn(() => {
      throw new Error('connect refused by the runtime');
    });
    expect(await probeSshBanner(TARGET, { connect })).toEqual({
      verdict: 'target-unreachable',
      reason: 'error',
    });
  });

  it('an IPv6 target connects with a bracketed hostname', async () => {
    const fake = fakeSocket(['SSH-2.0-x']);
    const connect = vi.fn(() => fake.socket);
    await probeSshBanner({ host: '2001:db8::7', port: 2222 }, { connect });
    expect(connect).toHaveBeenCalledWith(
      { hostname: '[2001:db8::7]', port: 2222 },
      expect.anything()
    );
  });
});

describe('probeTarget', () => {
  const accepted: [string, unknown, { host: string; port: number }][] = [
    ['a public IPv4', { host: '203.0.113.7', port: 22 }, { host: '203.0.113.7', port: 22 }],
    [
      'a DNS name, lowercased',
      { host: 'Machine.Example.COM', port: 2222 },
      { host: 'machine.example.com', port: 2222 },
    ],
    ['a public IPv6', { host: '2001:db8::1', port: 22 }, { host: '2001:db8::1', port: 22 }],
    [
      'a bracketed IPv6',
      { host: '[2606:4700::1111]', port: 22 },
      { host: '2606:4700::1111', port: 22 },
    ],
    [
      '172.15.x, just below 172.16/12',
      { host: '172.15.0.1', port: 22 },
      { host: '172.15.0.1', port: 22 },
    ],
    [
      '100.128.x, just above 100.64/10',
      { host: '100.128.0.1', port: 22 },
      { host: '100.128.0.1', port: 22 },
    ],
    ['port 65535', { host: '203.0.113.7', port: 65535 }, { host: '203.0.113.7', port: 65535 }],
  ];
  it.each(accepted)('admits %s', (_name, value, expected) => {
    expect(probeTarget(value)).toEqual(expected);
  });

  const refused: [string, unknown][] = [
    ['localhost', { host: 'localhost', port: 22 }],
    ['a .localhost name', { host: 'evil.localhost', port: 22 }],
    ['0/8', { host: '0.1.2.3', port: 22 }],
    ['10/8', { host: '10.0.0.1', port: 22 }],
    ['100.64/10', { host: '100.100.1.1', port: 22 }],
    ['127/8', { host: '127.0.0.53', port: 22 }],
    ['169.254/16', { host: '169.254.169.254', port: 22 }],
    ['172.16/12', { host: '172.31.255.1', port: 22 }],
    ['192.168/16', { host: '192.168.0.1', port: 22 }],
    ['::', { host: '::', port: 22 }],
    ['::1', { host: '::1', port: 22 }],
    ['fc00::/7', { host: 'fd12:3456::1', port: 22 }],
    ['fe80::/10', { host: 'fe80::1', port: 22 }],
    ['an IPv4-mapped loopback', { host: '::ffff:127.0.0.1', port: 22 }],
    ['port 25', { host: '203.0.113.7', port: 25 }],
  ];
  it.each(refused)('refuses %s as report-target-refused', (_name, value) => {
    expect(probeTarget(value)).toEqual({ refused: 'report-target-refused' });
  });

  const invalid: [string, unknown][] = [
    ['null', null],
    ['a string', '203.0.113.7:22'],
    ['a missing host', { port: 22 }],
    ['a numeric host', { host: 2130706433, port: 22 }],
    ['an empty host', { host: '', port: 22 }],
    ['port 0', { host: '203.0.113.7', port: 0 }],
    ['port 65536', { host: '203.0.113.7', port: 65536 }],
    ['a fractional port', { host: '203.0.113.7', port: 22.5 }],
    ['a string port', { host: '203.0.113.7', port: '22' }],
    ['an octet over 255', { host: '203.0.113.256', port: 22 }],
    ['a leading-zero octet', { host: '010.0.0.1', port: 22 }],
    ['a short dotted number', { host: '127.1', port: 22 }],
    ['a hex last label', { host: 'a.0x7f', port: 22 }],
    ['a name with a space', { host: 'bad host.example', port: 22 }],
    ['a malformed IPv6', { host: '2001:db8:::1', port: 22 }],
  ];
  it.each(invalid)('refuses %s as report-target-invalid', (_name, value) => {
    expect(probeTarget(value)).toEqual({ refused: 'report-target-invalid' });
  });
});
