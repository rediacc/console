/**
 * `console.recipes` in the config (PLAN-console-command-line.md D7, box CL9).
 *
 * Team recipes live in the team's encrypted config, keyed by name, and the
 * whole record is one committed identifier leaf, like `/access`: a push that
 * edits any recipe without knowing the current value changes the commitment.
 */

import { describe, expect, it } from 'vitest';
import { computeSchemaCoverage } from '../coverage.js';
import {
  CONSOLE_RECIPE_BODY_MAX_CHARS,
  parseConfig,
  type RdcConfig,
  RdcConfigSchema,
} from '../schemas.js';
import { listSensitivityTemplates, SENSITIVITY_REGISTRY } from '../sensitivity.js';
import { pathsToCommit } from '../walker.js';

const RECIPE = {
  description: 'Fork a repo and start it',
  body: '$repo = required "Repository"\nrdc repo fork $repo --tag t1\nrdc repo up $repo:t1',
  updatedAt: '2026-11-24T18:00:00.000Z',
};

function configWith(recipes: Record<string, unknown>): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    encryption: { mode: 'plaintext' },
    console: { recipes },
  } as RdcConfig;
}

describe('console.recipes in the config', () => {
  it('parses a recipe record keyed by name', () => {
    const parsed = parseConfig(RdcConfigSchema, configWith({ 'fork-up': RECIPE }), 'test config');
    expect(parsed.console?.recipes?.['fork-up']).toEqual(RECIPE);
  });

  it('refuses a recipe name that is not a resource name', () => {
    const result = RdcConfigSchema.safeParse(configWith({ 'Fork Up': RECIPE }));
    expect(result.success).toBe(false);
  });

  it('refuses an empty body, an oversized body and a non-ISO updatedAt', () => {
    for (const bad of [
      { ...RECIPE, body: '' },
      { ...RECIPE, body: 'x'.repeat(CONSOLE_RECIPE_BODY_MAX_CHARS + 1) },
      { ...RECIPE, updatedAt: 'yesterday' },
    ]) {
      expect(RdcConfigSchema.safeParse(configWith({ r: bad })).success).toBe(false);
    }
  });

  it('control: a config without console still parses', () => {
    const rest: Record<string, unknown> = { ...configWith({}) };
    delete rest.console;
    expect(RdcConfigSchema.safeParse(rest).success).toBe(true);
  });

  it('is one committed identifier leaf in the sensitivity registry', () => {
    expect(listSensitivityTemplates()).toContain('/console/recipes');
    const meta = SENSITIVITY_REGISTRY.get('/console/recipes');
    expect(meta?.kind).toBe('identifier');
    expect(meta?.commit).toBe(true);
  });

  it('commits the whole record as one pointer, not one per recipe', () => {
    const config = configWith({ a: RECIPE, b: { ...RECIPE, description: 'second' } });
    expect(pathsToCommit(config).filter((p) => p.startsWith('/console'))).toEqual([
      '/console/recipes',
    ]);
  });

  it('every console leaf is covered by the registry', () => {
    const report = computeSchemaCoverage(RdcConfigSchema, listSensitivityTemplates());
    expect(report.uncovered.filter((p) => p.startsWith('/console'))).toEqual([]);
    expect(report.stale).not.toContain('/console/recipes');
  });
});
