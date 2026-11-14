/**
 * `machine health` folds the proxy's certificate expiry (G5): a certificate under 21 days raises the exit code to 1,
 * under 7 days to 2, with a `cert.expiry.near` finding naming it. A machine without the proxy is unchanged.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyCertificates } = await import('../health-folds.js');

const NOW = new Date('2026-11-06T12:00:00Z');
const inDays = (d: number) => new Date(NOW.getTime() + d * 86_400_000).toISOString();
const clean = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [] as string[],
  findings: [],
};
const certs = (...c: [string, number][]) => ({
  status: 'ok',
  certificates: c.map(([main, days]) => ({ main, sans: [], not_after: inDays(days) })),
});

describe('applyCertificates', () => {
  it('a certificate 20 days from expiry is a warning naming it', () => {
    const h = applyCertificates(clean, certs(['*.example.com', 20], ['a.example.com', 60]), NOW);
    expect(h.exitCode).toBe(1);
    expect(h.findings).toEqual([
      expect.objectContaining({ code: 'cert.expiry.near', subject: '*.example.com' }),
    ]);
    expect(h.issues.join('\n')).toMatch(/\*\.example\.com/);
  });

  it('a certificate 6 days from expiry is an error', () => {
    expect(applyCertificates(clean, certs(['mail.example.org', 6]), NOW).exitCode).toBe(2);
  });

  it("F17's shared challenge CNAME is a warning naming the end (G6)", () => {
    const section = {
      status: 'ok',
      certificates: [
        {
          main: 'a.example',
          sans: [],
          not_after: inDays(60),
          challenges: [
            { name: 'a.example', cname: 'www.example' },
            { name: 'b.example', cname: 'www.example' },
          ],
        },
      ],
    };
    const h = applyCertificates(clean, section, NOW);
    expect(h.exitCode).toBe(1);
    expect(h.findings).toEqual([
      expect.objectContaining({ code: 'acme.challenge.cname-shared', subject: 'www.example' }),
    ]);
  });

  it('22 days left and a machine without the proxy leave the verdict clean (control)', () => {
    expect(applyCertificates(clean, certs(['a.example.com', 22]), NOW)).toEqual(clean);
    expect(applyCertificates(clean, undefined, NOW)).toEqual(clean);
  });
});
