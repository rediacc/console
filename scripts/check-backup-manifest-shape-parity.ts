/**
 * check:ci-backup-manifest-shape-parity — the account's manifest parser must
 * keep up with renet's manifest writer.
 *
 * The class this catches, paid for in full on 2026-08-14: renet's chunkstore
 * grew a DELTA manifest shape ({parent, changedCells}, with `cells` omitempty
 * and therefore absent), while the account's extractManifestHashes still
 * accepted only `cells` and `chunks`. Anything else throws, and the GC treats a
 * throw as "lineage unreadable" and skips it FAIL-SAFE. So every backup run
 * after the seed made its lineage permanently invisible to chunk GC: storage
 * grew without bound while the per-subscription byte quota kept charging for
 * dead chunks. Nothing failed. No test went red. The two sides simply drifted.
 *
 * Why no existing gate could see it: the seam is cross-repo (Go struct in a
 * submodule vs a TypeScript function in another submodule) and the failure is
 * silent by design, because fail-safe means "do nothing", which looks exactly
 * like "nothing to do". A parser that silently stops reclaiming is the worst
 * shape of bug: correct-looking, quiet, and expensive.
 *
 * The rule enforced: every JSON field on renet's chunkstore.Manifest struct is
 * classified here as either INVENTORY (it carries chunk references, so the
 * account parser MUST handle it by name) or METADATA (it carries none). A field
 * that is neither fails the gate, which forces a human decision at the moment
 * the shape changes rather than months later via a storage bill.
 *
 * Run: npx tsx scripts/check-backup-manifest-shape-parity.ts
 *
 * Control-first: every run first proves the detector on a synthetic unclassified
 * field that MUST be reported, and refuses to pass on an empty scan. A gate that
 * cannot fire is worse than no gate, because it also removes the suspicion that
 * would have caught the defect by hand.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const MANIFEST_GO = 'private/renet/pkg/chunkstore/manifest.go';
const PARSER_TS = 'private/account/src/services/backup-gc.service.ts';

/**
 * Fields carrying chunk references. Each MUST be named in the account parser.
 * Adding one here without teaching extractManifestHashes about it fails below.
 */
const INVENTORY: Record<string, string> = {
  cells: 'full manifest: one entry per cell, ZeroCell or a hash',
  changedCells: 'delta manifest: cell index -> ZeroCell or a hash',
};

/**
 * Fields carrying no chunk references. Each needs a reason, so that classifying
 * a new field as harmless is a deliberate act with a sentence behind it.
 */
const METADATA: Record<string, string> = {
  version: 'format version integer',
  snapshotId: 'identity, not content',
  repositoryGuid: 'identity, not content',
  lineage: 'grand guid; namespaces object keys but references no chunk',
  datastoreId: 'placement hint',
  cellBytes: 'grid geometry',
  imageBytes: 'grid geometry',
  createdAt: 'timestamp',
  parent:
    'parent SNAPSHOT id, not a chunk hash; the parent manifest is itself indexed, which is why no parent-chain walk is needed',
};

/** JSON tag names on the Go Manifest struct, in declaration order. */
function manifestJsonFields(source: string): string[] {
  const start = source.indexOf('type Manifest struct {');
  if (start === -1) throw new Error(`Manifest struct not found in ${MANIFEST_GO}`);
  const end = source.indexOf('\n}', start);
  if (end === -1) throw new Error(`Manifest struct never closes in ${MANIFEST_GO}`);
  const body = source.slice(start, end);
  const names: string[] = [];
  for (const m of body.matchAll(/`json:"([^",]+)[^"]*"`/g)) names.push(m[1]);
  return names;
}

/** Unclassified fields: the whole point of the gate. */
function unclassified(fields: string[]): string[] {
  return fields.filter((f) => !(f in INVENTORY) && !(f in METADATA));
}

// ── Control: the detector must report a planted unclassified field ──────────
const CONTROL_FIELD = 'controlUnclassifiedField';
if (unclassified([CONTROL_FIELD]).length !== 1) {
  console.error(
    `✗ instrument control did not fire: a planted unclassified field (${CONTROL_FIELD}) was not reported.\n` +
      '  The detector cannot see new manifest fields, so a green run below would mean nothing.'
  );
  process.exit(1);
}

// ── Real run ────────────────────────────────────────────────────────────────
let goSource: string;
let tsSource: string;
try {
  goSource = readFileSync(join(ROOT, MANIFEST_GO), 'utf8');
  tsSource = readFileSync(join(ROOT, PARSER_TS), 'utf8');
} catch (err) {
  console.error(
    `✗ cannot read the seam: ${(err as Error).message}\n` +
      '  Both sides must be present for this gate to mean anything; a missing\n' +
      '  submodule is an UNRUN check, not a pass.'
  );
  process.exit(1);
}

const fields = manifestJsonFields(goSource);
if (fields.length === 0) {
  console.error(
    `✗ nothing scanned: no json tags found on the Manifest struct in ${MANIFEST_GO}.\n` +
      '  A zero here means the parser broke, not that the struct is empty.'
  );
  process.exit(1);
}

const problems: string[] = [];

for (const field of unclassified(fields)) {
  problems.push(
    `    ${field}\n` +
      `      New field on renet's Manifest, unclassified here. Decide: does it\n` +
      `      carry chunk references? If yes, add it to INVENTORY and teach\n` +
      `      extractManifestHashes to read it. If no, add it to METADATA with a\n` +
      `      reason. Guessing silently is how delta manifests went unparsed.`
  );
}

for (const field of Object.keys(INVENTORY)) {
  if (!fields.includes(field)) {
    problems.push(
      `    ${field}\n` +
        `      Classified INVENTORY here but no longer emitted by renet's Manifest.\n` +
        `      Either the field was renamed (update both sides) or it is gone.`
    );
    continue;
  }
  if (!tsSource.includes(field)) {
    problems.push(
      `    ${field}\n` +
        `      Carries chunk references but ${PARSER_TS} never names it, so a\n` +
        `      manifest of that shape parses to an empty hash set or throws. A\n` +
        `      throw makes GC skip the lineage FOREVER while the byte quota keeps\n` +
        `      charging: silent, unbounded storage growth.`
    );
  }
}

if (problems.length > 0) {
  console.error(
    `✗ backup manifest shape parity (${problems.length}):\n${problems.join('\n')}\n\n` +
      '  renet owns the manifest wire format; the account only reads the chunk\n' +
      '  hashes out of it. When the two drift, nothing fails loudly, which is\n' +
      '  exactly why this gate exists.'
  );
  process.exit(1);
}

console.log(
  `✓ backup manifest shape parity ` +
    `(${fields.length} manifest fields: ${Object.keys(INVENTORY).length} inventory handled by the ` +
    `account parser, ${fields.length - Object.keys(INVENTORY).length} metadata; control fired)`
);
