import { describe, expect, it } from 'vitest';
import { IncidentReportSchema } from '../report.js';
import {
  parseReportFieldMap,
  REPORT_FIELD_MAP,
  REPORT_FIELD_PATHS,
  regimeMapping,
} from '../report-field-map.js';

type Raw = { regimes: Record<string, unknown>[]; fields: Record<string, Record<string, unknown>> };

function clone(): Raw {
  return JSON.parse(JSON.stringify(REPORT_FIELD_MAP));
}

/** Leaf paths of the final stage, which holds every field; header and dataImpact are expanded. */
function modelPaths(): string[] {
  const final = IncidentReportSchema.options.find((o) => o.shape.stage.value === 'final');
  if (!final) throw new Error('no final stage');
  const out: string[] = [];
  for (const [key, schema] of Object.entries(final.shape)) {
    if (key === 'stage') continue;
    if (key === 'header' || key === 'dataImpact') {
      const inner = (schema as unknown as { shape: Record<string, unknown> }).shape;
      for (const k of Object.keys(inner)) out.push(`${key}.${k}`);
    } else {
      out.push(key);
    }
  }
  return out;
}

describe('report field map', () => {
  it('lists exactly the fields of the report model', () => {
    expect([...REPORT_FIELD_PATHS].sort()).toEqual(modelPaths().sort());
  });

  it('maps every report field for every regime or says why not', () => {
    for (const path of REPORT_FIELD_PATHS) {
      for (const regime of REPORT_FIELD_MAP.regimes) {
        expect(regimeMapping(path, regime.id), `${path} / ${regime.id}`).toBeDefined();
      }
    }
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
