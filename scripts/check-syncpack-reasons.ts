#!/usr/bin/env node
/**
 * Enforce that every versionGroup in .syncpackrc.json carries a substantive
 * reason in the sidecar .syncpackrc-reasons.json.
 *
 * Syncpack's config schema rejects unknown fields, so we keep rationale in
 * a sidecar keyed by each group's `label`. This file enforces both that
 * every versionGroup's label is present in the sidecar AND that each reason
 * passes the shared BLOCKER quality rules (see scripts/lib/blocker-validator.ts).
 *
 * Exit codes:
 *   0 - every versionGroup has a valid reason in the sidecar
 *   1 - at least one group is missing a label, a reason, or has a low-effort reason
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateBlockerQuality } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const SYNCPACKRC = path.join(CONSOLE_ROOT, '.syncpackrc.json');
const REASONS_FILE = path.join(CONSOLE_ROOT, '.syncpackrc-reasons.json');

interface SyncpackConfig {
  versionGroups?: Array<{
    label?: string;
    pinVersion?: string;
    policy?: string;
  }>;
}

function main(): number {
  if (!fs.existsSync(SYNCPACKRC)) {
    console.log(`✓ No .syncpackrc.json to validate`);
    return 0;
  }

  const cfg = JSON.parse(fs.readFileSync(SYNCPACKRC, 'utf-8')) as SyncpackConfig;
  const groups = cfg.versionGroups ?? [];
  const failures: string[] = [];

  // Load sidecar reasons
  if (!fs.existsSync(REASONS_FILE)) {
    console.error(`✗ ${REASONS_FILE} is missing.`);
    console.error(
      `  Action: create ${REASONS_FILE} as a JSON object keyed by each versionGroup's "label" field.`,
    );
    return 1;
  }
  const reasons = JSON.parse(fs.readFileSync(REASONS_FILE, 'utf-8')) as Record<string, unknown>;

  const labels = new Set<string>();
  for (let i = 0; i < groups.length; i++) {
    const g = groups[i]!;
    const label = g.label;
    if (!label) {
      failures.push(
        `.syncpackrc.json: versionGroup[${i}] has no "label" field. A label is required so the reasons sidecar can reference it.`,
      );
      continue;
    }
    labels.add(label);
    const reason = reasons[label];
    if (typeof reason !== 'string' || !reason) {
      failures.push(
        `.syncpackrc-reasons.json: missing entry for "${label}".\n` +
          `  Action: add a "${label}" key with a substantive "BLOCKER: ..." reason.`,
      );
      continue;
    }
    const validation = validateBlockerQuality(label, reason, '.syncpackrc-reasons.json');
    if (validation) {
      failures.push(validation.message);
    }
  }

  // Flag orphaned sidecar entries (drift)
  for (const key of Object.keys(reasons)) {
    if (key.startsWith('$')) continue; // JSON metadata like $comment, $schema
    if (!labels.has(key)) {
      failures.push(
        `.syncpackrc-reasons.json: "${key}" has no matching versionGroup in .syncpackrc.json — remove the stale reason.`,
      );
    }
  }

  if (failures.length > 0) {
    console.error('✗ syncpack reason validation failed:');
    for (const f of failures) console.error(f);
    console.error('');
    console.error('✗ Every syncpack versionGroup needs a substantive reason — strict gate enforced');
    return 1;
  }

  console.log(`✓ All ${groups.length} syncpack versionGroups have valid reasons`);
  return 0;
}

process.exit(main());
