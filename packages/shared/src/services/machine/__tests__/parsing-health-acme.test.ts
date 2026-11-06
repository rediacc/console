/**
 * The ACME shared-CNAME detector (G6, D-certs, F17): a name whose `_acme-challenge.` chain ends at a name not beginning
 * `_acme-challenge.`, or two names sharing one end, is `acme.challenge.cname-shared`. Deliberate delegations stay
 * silent.
 */
import { describe, expect, it } from 'vitest';
import { checkAcmeChallengeCnames } from '../parsing-health.js';

const section = (challenges: { name: string; cname?: string }[], delegated_names?: string[]) => ({
  status: 'ok',
  certificates: [{ main: challenges[0]?.name ?? 'x', challenges }],
  ...(delegated_names ? { delegated_names } : {}),
});

describe('checkAcmeChallengeCnames', () => {
  it("F17's shape: two names whose challenge ends at www.example is one finding naming both", () => {
    const findings = checkAcmeChallengeCnames(
      section([
        { name: 'a.example', cname: 'www.example' },
        { name: 'b.example', cname: 'www.example' },
      ])
    );
    expect(findings).toEqual([
      expect.objectContaining({
        code: 'acme.challenge.cname-shared',
        subject: 'www.example',
        names: ['a.example', 'b.example'],
      }),
    ]);
  });

  it('a single name ending at a non-challenge name is a finding too', () => {
    expect(
      checkAcmeChallengeCnames(section([{ name: '*.example.com', cname: 'www.example.com' }]))
    ).toEqual([expect.objectContaining({ names: ['example.com'] })]);
  });

  it('a deliberate delegation to another _acme-challenge name raises nothing', () => {
    expect(
      checkAcmeChallengeCnames(
        section([{ name: 'mail.example.com', cname: '_acme-challenge.mail.example.io' }])
      )
    ).toEqual([]);
  });

  it('a shared end whose names are listed in delegated_names raises nothing', () => {
    expect(
      checkAcmeChallengeCnames(
        section(
          [
            { name: 'a.example', cname: 'www.example' },
            { name: 'b.example', cname: 'www.example' },
          ],
          ['a.example', 'b.example']
        )
      )
    ).toEqual([]);
  });

  it('names with no CNAME, and an absent or unreadable section, raise nothing (control)', () => {
    expect(
      checkAcmeChallengeCnames(section([{ name: 'a.example' }, { name: 'b.example' }]))
    ).toEqual([]);
    expect(checkAcmeChallengeCnames(undefined)).toEqual([]);
    expect(checkAcmeChallengeCnames({ status: 'unknown', certificates: null })).toEqual([]);
  });
});

describe('checkAcmeChallengeCnames with an unreadable chain (renet ChallengeInfo.unknown)', () => {
  const withUnknown = (
    challenges: { name: string; cname?: string; unknown?: boolean }[],
    delegated_names?: string[]
  ) => ({
    status: 'ok',
    certificates: [{ main: 'a.example', challenges }],
    ...(delegated_names ? { delegated_names } : {}),
  });

  it('reports a name whose chain could not be resolved as unknown, never as clean', () => {
    const findings = checkAcmeChallengeCnames(withUnknown([{ name: 'a.example', unknown: true }]));
    expect(findings).toEqual([
      expect.objectContaining({
        code: 'acme.challenge.unknown',
        severity: 'warning',
        names: ['a.example'],
      }),
    ]);
  });

  it('does not count an unknown name toward a shared end, and keeps the real collision', () => {
    const findings = checkAcmeChallengeCnames(
      withUnknown([
        { name: 'a.example', cname: 'www.example' },
        { name: 'b.example', cname: 'www.example' },
        { name: 'c.example', cname: 'www.example', unknown: true },
      ])
    );
    expect(findings.map((f) => [f.code, f.names])).toEqual([
      ['acme.challenge.cname-shared', ['a.example', 'b.example']],
      ['acme.challenge.unknown', ['c.example']],
    ]);
  });

  it('leaves a delegated unknown name silent (control)', () => {
    expect(
      checkAcmeChallengeCnames(
        withUnknown([{ name: 'mail.example', unknown: true }], ['mail.example'])
      )
    ).toEqual([]);
  });
});

describe('checkAcmeChallengeCnames detail text', () => {
  const one = (name: string, cname: string) =>
    checkAcmeChallengeCnames({
      status: 'ok',
      certificates: [{ main: name, challenges: [{ name, cname }] }],
    });

  it('does not say renewals collide for a single name ending outside _acme-challenge', () => {
    const [finding] = one('a.example', 'www.other.example');
    expect(finding.detail).not.toContain('collide');
    expect(finding.detail).toContain('www.other.example');
  });

  it('says renewals collide when several names share one end (control)', () => {
    const findings = checkAcmeChallengeCnames({
      status: 'ok',
      certificates: [
        {
          main: 'a.example',
          challenges: [
            { name: 'a.example', cname: '_acme-challenge.x.example' },
            { name: 'b.example', cname: '_acme-challenge.x.example' },
          ],
        },
      ],
    });
    expect(findings[0].detail).toContain('renewals there collide');
  });
});
