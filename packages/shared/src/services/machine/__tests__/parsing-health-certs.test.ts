/**
 * The certificate dimension of `machine health` (G5, D-certs): each proxy certificate under 21 days is a warning and
 * under 7 days an error, naming the certificate. No proxy on the machine raises nothing.
 */
import { describe, expect, it } from 'vitest';
import { checkCertificateExpiry } from '../parsing-health.js';

const NOW = new Date('2026-11-06T12:00:00Z');
const inDays = (d: number) => new Date(NOW.getTime() + d * 24 * 60 * 60 * 1000).toISOString();
const section = (...certs: { main: string; not_after: string }[]) => ({
  status: 'ok',
  certificates: certs.map((c) => ({ ...c, sans: [] })),
});

describe('checkCertificateExpiry', () => {
  it('22 days left raises no finding', () => {
    expect(
      checkCertificateExpiry(section({ main: 'a.example.com', not_after: inDays(22) }), NOW)
    ).toEqual([]);
  });

  it('20 days left is a warning naming the certificate', () => {
    const findings = checkCertificateExpiry(
      section({ main: '*.example.com', not_after: inDays(20) }),
      NOW
    );
    expect(findings).toEqual([
      expect.objectContaining({
        code: 'cert.expiry.near',
        severity: 'warning',
        subject: '*.example.com',
        daysLeft: 20,
      }),
    ]);
    expect(findings[0].detail).toMatch(/\*\.example\.com/);
  });

  it('6 days left is an error', () => {
    expect(
      checkCertificateExpiry(section({ main: 'mail.example.org', not_after: inDays(6) }), NOW)
    ).toEqual([expect.objectContaining({ severity: 'error', subject: 'mail.example.org' })]);
  });

  it('an expired certificate is an error', () => {
    const [f] = checkCertificateExpiry(
      section({ main: 'old.example.org', not_after: inDays(-2) }),
      NOW
    );
    expect(f).toMatchObject({ severity: 'error', daysLeft: -2 });
  });

  it('a machine without the proxy (no section) raises nothing', () => {
    expect(checkCertificateExpiry(undefined, NOW)).toEqual([]);
    expect(checkCertificateExpiry(null, NOW)).toEqual([]);
  });

  it('an unreadable acme.json is a warning, never a clean machine', () => {
    expect(
      checkCertificateExpiry(
        { status: 'unknown', certificates: null, error: 'permission denied' },
        NOW
      )
    ).toEqual([expect.objectContaining({ code: 'cert.store.unreadable', severity: 'warning' })]);
  });
});
