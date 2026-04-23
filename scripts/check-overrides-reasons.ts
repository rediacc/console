#!/usr/bin/env node
/**
 * Enforce that every entry in package.json `overrides` has a matching
 * entry in `_overridesReasons` whose value passes the BLOCKER quality gate.
 *
 * This is the JSON-safe sibling of the BLOCKER convention used in every
 * other suppression mechanism in the repo. JSON does not allow inline
 * comments, so we carry rationale in a parallel object keyed identically
 * to the override itself.
 *
 * Exit codes:
 *   0 - every override has a valid BLOCKER reason
 *   1 - at least one override is missing or has a low-effort reason
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateBlockerQuality } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const PACKAGE_JSON = path.join(CONSOLE_ROOT, 'package.json');

interface PackageJson {
  overrides?: Record<string, unknown>;
  _overridesReasons?: Record<string, string>;
}

function flattenOverrideKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  // overrides allows nested scoping: { "some-pkg": { "nested": "1.0.0" } }
  // For reason parity, we key by the top-level override only — nested overrides
  // inherit the top-level reason.
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string') {
      keys.push(prefix ? `${prefix}>${k}` : k);
    } else if (v !== null && typeof v === 'object') {
      // Treat as nested — top-level key is enough
      keys.push(prefix ? `${prefix}>${k}` : k);
    }
  }
  return keys;
}

function main(): number {
  if (!fs.existsSync(PACKAGE_JSON)) {
    console.error(`package.json not found at ${PACKAGE_JSON}`);
    return 1;
  }

  const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON, 'utf-8')) as PackageJson;
  const overrides = pkg.overrides ?? {};
  const reasons = pkg._overridesReasons ?? {};

  const overrideKeys = flattenOverrideKeys(overrides);
  const failures: string[] = [];

  for (const key of overrideKeys) {
    const topKey = key.split('>')[0]!;
    const reason = reasons[topKey];
    if (!reason) {
      failures.push(
        `package.json: override "${topKey}" has no matching _overridesReasons entry.\n` +
          `  Action: add _overridesReasons["${topKey}"] with a substantive "BLOCKER: ..." reason.`,
      );
      continue;
    }
    const validation = validateBlockerQuality(topKey, reason, 'package.json:_overridesReasons');
    if (validation) {
      failures.push(validation.message);
    }
  }

  // Also flag _overridesReasons entries that have no matching override (drift).
  for (const key of Object.keys(reasons)) {
    if (!Object.hasOwn(overrides, key)) {
      failures.push(
        `package.json: _overridesReasons["${key}"] has no matching override — remove the stale reason.`,
      );
    }
  }

  if (failures.length > 0) {
    console.error('✗ package.json override reasons failed validation:');
    for (const f of failures) console.error(f);
    console.error('');
    console.error(
      '✗ Every package.json override must have a substantive _overridesReasons entry — strict gate enforced',
    );
    return 1;
  }

  console.log(`✓ All ${overrideKeys.length} package.json overrides have valid BLOCKER reasons`);
  return 0;
}

process.exit(main());
