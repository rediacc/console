/**
 * check:ci-schema-coverage — fail closed on unclassified config fields.
 *
 * Every leaf the RdcConfig Zod schema can produce must be covered by a
 * SENSITIVITY_REGISTRY template (packages/shared/src/config-schema/
 * sensitivity.ts). An unregistered leaf is an UNCLASSIFIED field: it is
 * silently excluded from redaction, field commitments, and encryption-at-rest
 * — exactly how the backupStrategies and clusters.kvm sections shipped
 * unregistered and caused config data loss. The reverse direction is enforced
 * too: a registry template that matches nothing the schema can produce is rot
 * that commits/encrypts/redacts nothing.
 *
 * Run: npx tsx scripts/check-schema-coverage.ts
 *
 * Every run first proves the instrument on a control schema (the real schema
 * plus one deliberately unregistered leaf) — a gate that cannot fire is worse
 * than no gate.
 */

// Source imports (not @rediacc/shared dist) so the gate always judges the
// CURRENT registry/schema, even when packages/shared has not been rebuilt.
import {
  COVERAGE_CONTROL_POINTER,
  computeSchemaCoverage,
  coverageControlSchema,
} from '../packages/shared/src/config-schema/coverage.js';
import { RdcConfigSchema } from '../packages/shared/src/config-schema/schemas.js';
import { listSensitivityTemplates } from '../packages/shared/src/config-schema/sensitivity.js';

const REGISTRY_FILE = 'packages/shared/src/config-schema/sensitivity.ts';

const templates = listSensitivityTemplates();

// ── Control: the gate must be able to FIRE before its green means anything ──
const control = computeSchemaCoverage(coverageControlSchema(), templates);
if (!control.uncovered.includes(COVERAGE_CONTROL_POINTER)) {
  console.error(
    `FAIL: schema-coverage control did not fire — an unregistered control leaf ` +
      `(${COVERAGE_CONTROL_POINTER}) was not reported as uncovered. The walker or ` +
      `template matching is broken; do not trust this gate.`
  );
  process.exit(1);
}
console.log(`Control: unregistered leaf ${COVERAGE_CONTROL_POINTER} fires as uncovered — OK`);

// ── The real check ──────────────────────────────────────────────────────────
const report = computeSchemaCoverage(RdcConfigSchema, templates);
let failed = false;

if (report.uncovered.length > 0) {
  failed = true;
  console.error(`\nFAIL: ${report.uncovered.length} schema leaf/leaves have no registry entry:`);
  for (const pointer of report.uncovered) {
    console.error(`  ${pointer}`);
  }
  console.error(
    `\nEvery config field must declare its sensitivity. Add an entry for each ` +
      `pointer above to RAW_REGISTRY in ${REGISTRY_FILE} ` +
      `(kind: secret | credential | pii | identifier | public).`
  );
}

if (report.stale.length > 0) {
  failed = true;
  console.error(`\nFAIL: ${report.stale.length} registry template(s) match nothing in the schema:`);
  for (const pointer of report.stale) {
    console.error(`  ${pointer}`);
  }
  console.error(
    `\nThese entries in ${REGISTRY_FILE} point at fields RdcConfigSchema no ` +
      `longer has — they silently commit/encrypt/redact nothing. Remove them ` +
      `(or fix the template to match the current schema shape).`
  );
}

if (failed) process.exit(1);

console.log(
  `Schema coverage OK: ${report.leafCount} leaves checked ` +
    `(${report.covered.length} registered, 0 unclassified), ` +
    `${templates.length} registry templates, 0 stale. ` +
    `Envelope exclusions: ${report.excluded.join(', ')}.`
);
