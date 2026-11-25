import { describe, expect, it } from 'vitest';
import { IncidentReportSchema } from '../report.js';
import {
  parseReportFieldMap,
  REPORT_FIELD_MAP,
  REPORT_FIELD_PATHS,
  regimeMapping,
} from '../report-field-map.js';
import rawData from '../report-field-map.json' with { type: 'json' };

type Raw = { regimes: Record<string, unknown>[]; fields: Record<string, Record<string, unknown>> };

function clone(): Raw {
  return JSON.parse(JSON.stringify(REPORT_FIELD_MAP));
}

const NESTED = ['header', 'dataImpact'];

function innerKeys(schema: unknown): string[] {
  return Object.keys((schema as { shape: Record<string, unknown> }).shape);
}

/** Leaf paths of the final stage, which holds every field; header and dataImpact are expanded. */
function modelPaths(): string[] {
  const final = IncidentReportSchema.options.find((o) => o.shape.stage.value === 'final');
  if (!final) throw new Error('no final stage');
  return Object.entries(final.shape)
    .filter(([key]) => key !== 'stage')
    .flatMap(([key, schema]) =>
      NESTED.includes(key) ? innerKeys(schema).map((k) => `${key}.${k}`) : [key]
    );
}

const byText = (a: string, b: string) => a.localeCompare(b);

describe('report field map', () => {
  it('lists exactly the fields of the report model', () => {
    expect([...REPORT_FIELD_PATHS].sort(byText)).toEqual(modelPaths().sort(byText));
  });

  it('maps every report field for every regime in the raw file, not only in the parsed map', () => {
    const raw = rawData as Raw;
    for (const path of REPORT_FIELD_PATHS) {
      for (const regime of raw.regimes) {
        expect(raw.fields[path]?.[regime.id as string], `${path} / ${regime.id}`).toBeDefined();
      }
    }
  });

  it('looks a mapping up by field and regime, and answers undefined for a regime it lacks', () => {
    expect(regimeMapping('timeline', 'nis2')).toEqual(REPORT_FIELD_MAP.fields.timeline.nis2);
    expect(regimeMapping('timeline', 'no-such-regime')).toBeUndefined();
  });

  it('refuses a map that leaves one regime out of one field', () => {
    const map = clone();
    delete map.fields.timeline['gdpr-33'];
    expect(() => parseReportFieldMap(map)).toThrow(/timeline has no entry for regime gdpr-33/);
  });

  it('refuses a map that names a regime it does not declare', () => {
    const map = clone();
    map.fields.timeline.unknown = { notApplicable: 'x' };
    expect(() => parseReportFieldMap(map)).toThrow(/timeline names unknown regime unknown/);
  });

  it('gives every regime a URL and a retrieval date', () => {
    for (const regime of REPORT_FIELD_MAP.regimes) {
      expect(regime.url).toMatch(/^https:\/\//);
      expect(regime.retrievedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it('refuses a map missing a control field', () => {
    const map = clone();
    delete map.fields['header.awareAt'];
    expect(() => parseReportFieldMap(map)).toThrow(/header\.awareAt is not mapped/);
  });

  it('refuses a regime row without a URL or date', () => {
    const noUrl = clone();
    noUrl.regimes[0].url = 'nope';
    expect(() => parseReportFieldMap(noUrl)).toThrow();
    const noDate = clone();
    delete noDate.regimes[0].retrievedAt;
    expect(() => parseReportFieldMap(noDate)).toThrow();
  });

  it('refuses a not-applicable entry without a reason', () => {
    const map = clone();
    map.fields.timeline.nis2 = { notApplicable: '' };
    expect(() => parseReportFieldMap(map)).toThrow();
  });
});
