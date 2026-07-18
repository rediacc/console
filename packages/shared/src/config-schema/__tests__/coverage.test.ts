/**
 * Schema-coverage walker tests: the instrument behind check:ci-schema-coverage.
 *
 * The firing tests matter more than the green ones — a coverage gate that
 * cannot detect an unregistered leaf is worse than no gate (that is exactly
 * how backupStrategies and clusters.kvm shipped unregistered).
 */

import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import {
  COVERAGE_CONTROL_POINTER,
  computeSchemaCoverage,
  coverageControlSchema,
} from '../coverage.js';
import { RdcConfigSchema } from '../schemas.js';
import { listSensitivityTemplates } from '../sensitivity.js';

describe('computeSchemaCoverage — firing (fail-closed)', () => {
  it('reports an unregistered leaf as uncovered', () => {
    const schema = z.object({ known: z.string(), sneaky: z.string() });
    const report = computeSchemaCoverage(schema, ['/known'], []);
    expect(report.uncovered).toEqual(['/sneaky']);
    expect(report.covered).toEqual(['/known']);
    expect(report.leafCount).toBe(2);
  });

  it('reports unregistered leaves under records and arrays with * templates', () => {
    const schema = z.object({
      machines: z.record(z.string(), z.object({ ip: z.string(), port: z.number() })),
      tags: z.array(z.object({ label: z.string() })),
    });
    const report = computeSchemaCoverage(schema, ['/machines/*/ip'], []);
    expect(report.uncovered).toContain('/machines/*/port');
    expect(report.uncovered).toContain('/tags/*/label');
  });

  it('a CONCRETE registry segment does not cover a record wildcard position', () => {
    const schema = z.object({ machines: z.record(z.string(), z.object({ ip: z.string() })) });
    // Registering one specific machine key covers one runtime key, not the record.
    const report = computeSchemaCoverage(schema, ['/machines/prod-1/ip'], []);
    expect(report.uncovered).toEqual(['/machines/*/ip']);
  });

  it('reports a registry template that matches nothing in the schema as stale', () => {
    const schema = z.object({ real: z.string() });
    const report = computeSchemaCoverage(schema, ['/real', '/ghost', '/ghost/deeper'], []);
    expect(report.stale).toEqual(expect.arrayContaining(['/ghost', '/ghost/deeper']));
    expect(report.stale).not.toContain('/real');
  });

  it('the control schema fires against the REAL registry', () => {
    const report = computeSchemaCoverage(coverageControlSchema(), listSensitivityTemplates());
    expect(report.uncovered).toEqual([COVERAGE_CONTROL_POINTER]);
  });
});

describe('computeSchemaCoverage — coverage semantics', () => {
  it('a registered ancestor container covers its whole subtree (walker prune)', () => {
    const schema = z.object({
      policy: z.object({ version: z.number(), rules: z.array(z.string()) }),
    });
    const report = computeSchemaCoverage(schema, ['/policy'], []);
    expect(report.uncovered).toEqual([]);
    expect(report.covered).toEqual(['/policy']);
    // Deeper registry templates under a pruned container are not stale: the
    // walk never enumerated them, so their absence proves nothing.
    const withDeeper = computeSchemaCoverage(schema, ['/policy', '/policy/version'], []);
    expect(withDeeper.stale).toEqual([]);
  });

  it('optional/nullable/default wrappers and unions are unwrapped', () => {
    const schema = z.object({
      backend: z
        .union([
          z.object({ kind: z.literal('local'), path: z.string() }),
          z.object({ kind: z.literal('rbd'), pool: z.string() }),
        ])
        .optional(),
      note: z.string().nullable().default(null),
    });
    const report = computeSchemaCoverage(
      schema,
      ['/backend/kind', '/backend/path', '/backend/pool', '/note'],
      []
    );
    expect(report.uncovered).toEqual([]);
    expect(report.stale).toEqual([]);
  });

  it('exclusions skip envelope machinery without registering it', () => {
    const schema = z.object({
      id: z.string(),
      encryption: z.object({ mode: z.string() }),
      data: z.string(),
    });
    const report = computeSchemaCoverage(schema, ['/data'], ['/id', '/encryption']);
    expect(report.uncovered).toEqual([]);
    expect(report.excluded).toEqual(['/encryption', '/id']);
    expect(report.leafCount).toBe(1);
  });
});

describe('the real schema against the real registry', () => {
  it('every RdcConfigSchema leaf is registered and no registry entry is stale', () => {
    const report = computeSchemaCoverage(RdcConfigSchema, listSensitivityTemplates());
    expect(report.uncovered).toEqual([]);
    expect(report.stale).toEqual([]);
    expect(report.leafCount).toBeGreaterThan(150);
  });
});
