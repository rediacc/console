#!/usr/bin/env node
/**
 * Enforce that every suppression in biome.json has a BLOCKER-quality reason
 * in `.ci/config/biome-reasons.md`. Biome 2.4.13+ rejects unknown top-level
 * keys in `biome.json` itself, so rationale lives in a sibling doc using
 * the same HTML-comment pattern as `.ci/config/tsconfig-exceptions.md`.
 *
 * Suppressions checked:
 *   - top-level `linter.enabled: false`
 *   - per-override `linter.rules.<cat>.<rule>: "off"`
 *   - per-override `assist.actions.source.<fam>.level: "off"`
 *
 * Exit codes:
 *   0 — every suppression has a valid BLOCKER reason
 *   1 — at least one suppression missing or with a low-effort reason
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateBlockerQuality } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const BIOME_JSON = path.join(CONSOLE_ROOT, 'biome.json');
const REASONS_MD = path.join(CONSOLE_ROOT, '.ci/config/biome-reasons.md');

interface BiomeOverride {
  includes?: string[];
  linter?: {
    enabled?: boolean;
    rules?: Record<string, Record<string, string | unknown>>;
  };
  assist?: {
    actions?: {
      source?: Record<string, { level?: string }>;
    };
  };
}

interface BiomeConfig {
  linter?: { enabled?: boolean };
  overrides?: BiomeOverride[];
}

// Build the canonical key for a suppression site.
function keyForGlobs(globs: string[] | undefined): string {
  if (!globs || globs.length === 0) return '*';
  return globs.join(',');
}

function collectSuppressionKeys(cfg: BiomeConfig): string[] {
  const keys: string[] = [];

  if (cfg.linter?.enabled === false) {
    keys.push('linter.enabled=false');
  }

  for (const ov of cfg.overrides ?? []) {
    const globKey = keyForGlobs(ov.includes);

    // Rule-level linter disables: "off" values inside linter.rules.<cat>.<rule>
    const rules = ov.linter?.rules ?? {};
    for (const [cat, ruleSet] of Object.entries(rules)) {
      if (!ruleSet || typeof ruleSet !== 'object') continue;
      for (const [rule, value] of Object.entries(ruleSet as Record<string, unknown>)) {
        if (value === 'off') {
          keys.push(`overrides[${globKey}].linter.rules.${cat}.${rule}=off`);
        }
      }
    }

    // Assist source-level disables
    const source = ov.assist?.actions?.source ?? {};
    for (const [fam, spec] of Object.entries(source)) {
      if (spec && typeof spec === 'object' && 'level' in spec && spec.level === 'off') {
        keys.push(`overrides[${globKey}].assist.source.${fam}=off`);
      }
    }
  }

  return keys;
}

function parseReasonsSidecar(): Record<string, string> {
  if (!fs.existsSync(REASONS_MD)) return {};
  const raw = fs.readFileSync(REASONS_MD, 'utf-8');
  const out: Record<string, string> = {};
  const re = /<!--\s*biome-suppression:\s*([\s\S]*?)\s*-->/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    const body = m[1]!;
    const record: Record<string, string> = {};
    for (const line of body.split('\n')) {
      const mm = line.match(/^\s*(key|blocker)\s*:\s*(.+?)\s*$/);
      if (mm) record[mm[1]!] = mm[2]!;
    }
    if (record.key && record.blocker) {
      // Skip placeholder rows from the doc header.
      if (/[<>]/.test(record.key) || /[<>]/.test(record.blocker)) continue;
      out[record.key] = record.blocker;
    }
  }
  return out;
}

function main(): number {
  if (!fs.existsSync(BIOME_JSON)) {
    console.error(`biome.json not found at ${BIOME_JSON}`);
    return 1;
  }

  const cfg = JSON.parse(fs.readFileSync(BIOME_JSON, 'utf-8')) as BiomeConfig;
  const reasons = parseReasonsSidecar();
  const suppressions = collectSuppressionKeys(cfg);
  const failures: string[] = [];

  for (const key of suppressions) {
    const reason = reasons[key];
    if (!reason) {
      failures.push(
        `biome.json: suppression "${key}" has no matching row in .ci/config/biome-reasons.md\n` +
          `  Action: add a <!-- biome-suppression: key: ${key}\\nblocker: BLOCKER: <reason>\\n--> block (>= 30 chars, no banned phrases).`,
      );
      continue;
    }
    const validation = validateBlockerQuality(key, reason, '.ci/config/biome-reasons.md');
    if (validation) {
      failures.push(validation.message);
    }
  }

  // Drift: sidecar rows without a matching live suppression.
  const suppressionSet = new Set(suppressions);
  for (const key of Object.keys(reasons)) {
    if (!suppressionSet.has(key)) {
      failures.push(
        `.ci/config/biome-reasons.md: row for key="${key}" has no matching suppression — remove the stale row.`,
      );
    }
  }

  if (failures.length > 0) {
    console.error('✗ biome.json suppression reasons failed validation:');
    for (const f of failures) console.error(f);
    console.error('');
    console.error(
      '✗ Every biome.json suppression must have a substantive row in .ci/config/biome-reasons.md — strict gate enforced',
    );
    return 1;
  }

  console.log(`✓ All ${suppressions.length} biome.json suppression(s) have valid BLOCKER reasons`);
  return 0;
}

process.exit(main());
