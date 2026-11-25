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

type Issue = (message: string) => void;

/** One report field's row: every regime present, and no regime the map does not declare. */
function checkRow(path: string, row: Record<string, unknown>, regimeIds: string[], issue: Issue) {
  for (const id of regimeIds) {
    if (!row[id]) issue(`${path} has no entry for regime ${id}`);
  }
  for (const id of Object.keys(row)) {
    if (!regimeIds.includes(id)) issue(`${path} names unknown regime ${id}`);
  }
}

/** Every report field mapped, and no row for a path outside the report model. */
function checkFields(
  fields: Record<string, Record<string, unknown>>,
  regimeIds: string[],
  issue: Issue
) {
  for (const path of REPORT_FIELD_PATHS) {
    const row = fields[path];
    if (row) checkRow(path, row, regimeIds, issue);
    else issue(`report field ${path} is not mapped`);
  }
  const known: readonly string[] = REPORT_FIELD_PATHS;
  for (const path of Object.keys(fields)) {
    if (!known.includes(path)) issue(`${path} is not a report field`);
  }
}

const FieldMapSchema = z
  .strictObject({
    regimes: z.array(RegimeSchema).min(1),
    fields: z.record(z.string(), z.record(z.string(), MappingSchema)),
  })
  .superRefine((map, ctx) => {
    const issue: Issue = (message) => ctx.addIssue({ code: 'custom', message });
    const regimeIds = map.regimes.map((r) => r.id);
    if (new Set(regimeIds).size !== regimeIds.length) issue('duplicate regime id');
    checkFields(map.fields, regimeIds, issue);
  });

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
