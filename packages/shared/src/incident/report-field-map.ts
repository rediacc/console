/**
 * The regulatory field map (D7 of PLAN-forensics-reports): for every report field, where
 * each regime asks for it, or why the regime does not. The data lives in
 * `report-field-map.json`, one file to update when a template is revised; this loader
 * checks that file against the report model so a report field cannot go unmapped.
 */
import { z } from 'zod';
import data from './report-field-map.json' with { type: 'json' };

/** Every leaf of the report model, as a dotted path. */
export const REPORT_FIELD_PATHS = [
  'header.incidentId',
  'header.orgId',
  'header.generatedAt',
  'header.awareAt',
  'header.windowFrom',
  'header.windowTo',
  'header.contactPoint',
  'header.disclaimers',
  'timeline',
  'iocs',
  'suspectedMalicious',
  'crossBorderImpact',
  'assessment',
  'dataImpact.categories',
  'dataImpact.memberStates',
  'techniques',
  'rootCause',
  'mitigation',
] as const;
export type ReportFieldPath = (typeof REPORT_FIELD_PATHS)[number];

const RegimeSchema = z.strictObject({
  id: z.string().min(1),
  name: z.string().min(1),
  url: z.url().startsWith('https://'),
  retrievedAt: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'a YYYY-MM-DD retrieval date'),
});

const MappingSchema = z.union([
  z.strictObject({ ref: z.string().min(1), label: z.string().min(1) }),
  z.strictObject({ notApplicable: z.string().min(1) }),
]);

const FieldMapSchema = z
  .strictObject({
    regimes: z.array(RegimeSchema).min(1),
    fields: z.record(z.string(), z.record(z.string(), MappingSchema)),
  })
  .superRefine((map, ctx) => {
    for (const message of fieldMapIssues(map.regimes, map.fields)) {
      ctx.addIssue({ code: 'custom', message });
    }
  });

/** Every way a field map misses a report field or a regime, or names one that does not exist. */
function fieldMapIssues(
  regimes: readonly { id: string }[],
  fields: Record<string, Record<string, unknown>>
): string[] {
  const regimeIds = regimes.map((r) => r.id);
  const issues: string[] = [];
  if (new Set(regimeIds).size !== regimeIds.length) issues.push('duplicate regime id');
  for (const path of REPORT_FIELD_PATHS) issues.push(...rowIssues(path, fields[path], regimeIds));
  for (const path of Object.keys(fields)) {
    if (!(REPORT_FIELD_PATHS as readonly string[]).includes(path)) {
      issues.push(`${path} is not a report field`);
    }
  }
  return issues;
}

/** The issues of one report field's row: unmapped, a regime missing, or an unknown regime named. */
function rowIssues(
  path: string,
  row: Record<string, unknown> | undefined,
  regimeIds: readonly string[]
): string[] {
  if (!row) return [`report field ${path} is not mapped`];
  return [
    ...regimeIds.filter((id) => !row[id]).map((id) => `${path} has no entry for regime ${id}`),
    ...Object.keys(row)
      .filter((id) => !regimeIds.includes(id))
      .map((id) => `${path} names unknown regime ${id}`),
  ];
}

type ReportFieldMap = z.infer<typeof FieldMapSchema>;
type RegimeMapping = z.infer<typeof MappingSchema>;

export type { RegimeMapping, ReportFieldMap };

/** Parse a field map; throws with every missing or unknown entry named. */
export function parseReportFieldMap(raw: unknown): ReportFieldMap {
  return FieldMapSchema.parse(raw);
}

export const REPORT_FIELD_MAP: ReportFieldMap = parseReportFieldMap(data);

/** The regime's mapping for a report field. */
export function regimeMapping(path: ReportFieldPath, regimeId: string): RegimeMapping | undefined {
  return REPORT_FIELD_MAP.fields[path]?.[regimeId];
}
