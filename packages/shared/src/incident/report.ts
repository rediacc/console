/**
 * The incident report model (D1 of PLAN-forensics-reports): one shape with three
 * stages. Each stage lists the sections it requires and no others, so a section a
 * stage does not call for is omitted rather than blank. Every fact says how it is
 * known (`basis`), and an inferred fact carries a confidence and the detector's reason.
 */
import { z } from 'zod';

export const REPORT_STAGES = ['early-warning', 'notification', 'final'] as const;
export type ReportStage = (typeof REPORT_STAGES)[number];

export const REPORT_CONFIDENCES = ['low', 'medium', 'high'] as const;

/** Fixed text printed in every stage (D2). */
export const REPORT_DISCLAIMERS = [
  'Flow records prove volume and destination, not content.',
  'Whether the incident is significant or reportable is the customer’s judgement.',
] as const;

/** A value together with how it is known; inferred values must say how sure and why. */
export function fact<T extends z.ZodType>(value: T) {
  return z.discriminatedUnion('basis', [
    z.strictObject({ basis: z.enum(['observed', 'customer']), value }),
    z.strictObject({
      basis: z.literal('inferred'),
      confidence: z.enum(REPORT_CONFIDENCES),
      reason: z.string().min(1).max(500),
      value,
    }),
  ]);
}

const instant = z.iso.datetime();
const text = (max: number) => z.string().min(1).max(max);

const header = z.strictObject({
  incidentId: text(100),
  orgId: text(200),
  generatedAt: instant,
  awareAt: instant,
  windowFrom: instant,
  windowTo: instant,
  contactPoint: text(300).optional(),
  disclaimers: z.array(text(300)).min(1).max(10),
});

const timelineEntry = z.strictObject({
  ts: instant,
  kind: text(50),
  summary: fact(text(500)),
});

export const IOC_TYPES = ['ipv4', 'ipv6', 'domain', 'port', 'sha256'] as const;
export type IocType = (typeof IOC_TYPES)[number];

export const IocSchema = z.strictObject({
  type: z.enum(IOC_TYPES),
  value: text(300),
  firstSeen: instant,
  lastSeen: instant,
  /** Present for an address when the flow record names its autonomous system. */
  asn: z.number().int().min(0).max(4294967295).optional(),
  evidence: fact(text(500)),
});
type Ioc = z.infer<typeof IocSchema>;
export type { Ioc };

const technique = z.strictObject({
  id: z.string().regex(/^T\d{4}(\.\d{3})?$/, 'an ATT&CK technique id such as T1041'),
  name: text(200),
  evidence: fact(text(500)),
});

const textSection = z.strictObject({ text: fact(text(5000)) });

const dataImpact = z.strictObject({
  categories: z
    .array(z.strictObject({ name: text(200), approximateCount: fact(z.number().int().min(0)) }))
    .max(100),
  memberStates: z.array(z.string().regex(/^[A-Z]{2}$/, 'an ISO 3166-1 alpha-2 code')).max(40),
});

const earlyWarning = {
  header,
  timeline: z.array(timelineEntry).max(2000),
  iocs: z.array(IocSchema).max(2000),
  suspectedMalicious: fact(z.boolean()),
  crossBorderImpact: fact(z.boolean()),
};

const notification = {
  ...earlyWarning,
  assessment: textSection,
  dataImpact,
  techniques: z.array(technique).max(50),
};

const final = {
  ...notification,
  rootCause: textSection,
  mitigation: z.array(z.strictObject({ at: instant, action: fact(text(500)) })).max(200),
};

export const IncidentReportSchema = z.discriminatedUnion('stage', [
  z.strictObject({ stage: z.literal('early-warning'), ...earlyWarning }),
  z.strictObject({ stage: z.literal('notification'), ...notification }),
  z.strictObject({ stage: z.literal('final'), ...final }),
]);
type IncidentReport = z.infer<typeof IncidentReportSchema>;
export type { IncidentReport };
