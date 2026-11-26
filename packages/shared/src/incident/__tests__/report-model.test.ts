import { describe, expect, it } from 'vitest';
import { omitKey } from '../../utils/omit-key.js';
import { IncidentReportSchema, REPORT_DISCLAIMERS } from '../report.js';

const obs = <T>(value: T) => ({ basis: 'observed' as const, value });
const header = {
  incidentId: 'inc-1',
  orgId: 'org-1',
  generatedAt: '2026-11-21T09:00:00.000Z',
  awareAt: '2026-11-20T09:30:00.000Z',
  windowFrom: '2026-11-19T00:00:00.000Z',
  windowTo: '2026-11-20T09:00:00.000Z',
  disclaimers: [...REPORT_DISCLAIMERS],
};
const early = {
  stage: 'early-warning' as const,
  header,
  timeline: [
    { ts: '2026-11-20T08:00:00.000Z', kind: 'flow', summary: obs('Large upload to 203.0.113.9') },
  ],
  iocs: [
    {
      type: 'ipv4' as const,
      value: '203.0.113.9',
      firstSeen: '2026-11-20T08:00:00.000Z',
      lastSeen: '2026-11-20T08:05:00.000Z',
      evidence: obs('flow record'),
    },
  ],
  suspectedMalicious: { basis: 'customer' as const, value: true },
  crossBorderImpact: { basis: 'customer' as const, value: false },
};
const notification = {
  ...early,
  stage: 'notification' as const,
  assessment: { text: obs('Initial assessment') },
  dataImpact: {
    categories: [
      { name: 'customers', approximateCount: { basis: 'customer' as const, value: 120 } },
    ],
    memberStates: ['DE'],
  },
  techniques: [],
};
const final = {
  ...notification,
  stage: 'final' as const,
  rootCause: { text: obs('Leaked token') },
  mitigation: [{ at: '2026-11-20T10:00:00.000Z', action: obs('Rotated secret') }],
};

describe('IncidentReportSchema', () => {
  it('accepts each stage with exactly its sections', () => {
    expect(IncidentReportSchema.safeParse(early).success).toBe(true);
    expect(IncidentReportSchema.safeParse(notification).success).toBe(true);
    expect(IncidentReportSchema.safeParse(final).success).toBe(true);
  });

  it('refuses a header that drops or replaces a fixed disclaimer and admits an added one', () => {
    const withDisclaimers = (disclaimers: string[]) =>
      IncidentReportSchema.safeParse({ ...early, header: { ...header, disclaimers } }).success;
    expect(withDisclaimers([REPORT_DISCLAIMERS[0]])).toBe(false);
    expect(withDisclaimers(['Something else entirely.'])).toBe(false);
    expect(withDisclaimers([REPORT_DISCLAIMERS[0], 'Another text.'])).toBe(false);
    expect(withDisclaimers([...REPORT_DISCLAIMERS, 'Customer note.'])).toBe(true);
    expect(withDisclaimers([...REPORT_DISCLAIMERS])).toBe(true);
  });

  it('rejects an early warning carrying a final-only section', () => {
    expect(IncidentReportSchema.safeParse({ ...early, rootCause: final.rootCause }).success).toBe(
      false
    );
    expect(
      IncidentReportSchema.safeParse({ ...notification, rootCause: final.rootCause }).success
    ).toBe(false);
  });

  it('rejects a stage that lacks a required section', () => {
    const missing = omitKey(notification, 'assessment');
    expect(IncidentReportSchema.safeParse(missing).success).toBe(false);
  });

  it('requires confidence and a reason on an inferred fact', () => {
    const inferred = (extra: object) => ({
      ...early,
      suspectedMalicious: { basis: 'inferred', value: true, ...extra },
    });
    expect(IncidentReportSchema.safeParse(inferred({})).success).toBe(false);
    expect(IncidentReportSchema.safeParse(inferred({ confidence: 'high' })).success).toBe(false);
    expect(
      IncidentReportSchema.safeParse(
        inferred({ confidence: 'medium', reason: 'exfiltration over C2' })
      ).success
    ).toBe(true);
  });

  it('rejects confidence on an observed fact and an unknown basis', () => {
    expect(
      IncidentReportSchema.safeParse({
        ...early,
        suspectedMalicious: { basis: 'observed', value: true, confidence: 'low' },
      }).success
    ).toBe(false);
    expect(
      IncidentReportSchema.safeParse({
        ...early,
        suspectedMalicious: { basis: 'guess', value: true },
      }).success
    ).toBe(false);
  });
});
