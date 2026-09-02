/**
 * check:ci-backup-bucket-conformance — the bucket a region's Worker SIGNS for
 * must be the bucket its R2 binding READS.
 *
 * THE DEFECT CLASS, and this one was live. The account Worker's backup plane
 * has two halves that must name the same bucket:
 *
 *   1. the native R2 binding `BACKUP_BUCKET`, declared per deployment in
 *      workers/account/wrangler.<channel><region>.toml — this is what the
 *      Worker reads, lists and GCs;
 *   2. the presign signer built in
 *      private/account/src/services/backup-chunk-store.ts:977-985 from
 *      ACCOUNT_BACKUP_S3_BUCKET — this is what every presigned PUT URL
 *      points at.
 *
 * Until 2026-09-02 half 2 came from ONE global GitHub secret while half 1 was
 * per region and per channel, six buckets in all. So in us and asia the Worker
 * GC'd `rediacc-backups-us` while handing clients upload URLs for whatever
 * single bucket the global secret named. Chunks would land in one bucket and be
 * swept from another — a silent data-loss shape, not a crash. It never shipped
 * (docs/backup-storage/CHECKLIST.md:49 leaves w8 open), which is the only
 * reason this is a gate rather than an incident.
 *
 * The fix made the bucket a DERIVED value: regions.json now carries
 * `backupR2` / `edgeBackupR2` beside the existing `r2` / `edgeR2`, the deploy
 * matrix hands it to .ci/scripts/deploy/set-account-worker-secrets.sh, and no
 * secret holds a bucket name any more. This gate is what stops the two sources
 * drifting apart again, since nothing else compares them.
 *
 * IT ALSO GATES JURISDICTION, which is the half that is easy to miss. The EU
 * buckets are jurisdiction-locked (`jurisdiction = "eu"` in the toml) and are
 * reachable ONLY at https://<account>.eu.r2.cloudflarestorage.com. A correct
 * bucket name against the default host still fails, so regions.json's
 * `r2Jurisdiction` must agree with the toml exactly: set where the binding is
 * restricted, null where it is not.
 *
 * WHY NO EXISTING CHECK SEES IT. check:ci-regions-sync proves regions.json and
 * packages/shared/src/regions/data.json are copies of each other, and says
 * nothing about whether either matches reality. No check in this repo reads a
 * wrangler .toml at all — verified 2026-09-02. So the binding side had no
 * reader and the drift had nowhere to be noticed.
 *
 * Run: npx tsx scripts/check-backup-bucket-conformance.ts
 *
 * Control-first: every run first proves the .toml extractor BOTH ways against
 * synthetic input — a planted mismatch must be reported and a matching pair
 * must not — and refuses to pass if fewer than the expected number of
 * deployments were found. A gate that reads zero files cannot fail.
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/** The binding whose bucket the presign signer must agree with. */
const BINDING = 'BACKUP_BUCKET';

interface RegionRecord {
  id: string;
  backupR2?: { name?: string };
  edgeBackupR2?: { name?: string };
  r2Jurisdiction?: string | null;
}

interface Deployment {
  /** Human label used in failure text. */
  label: string;
  /** wrangler config, relative to repo root. */
  toml: string;
  /** What regions.json says this deployment's backup bucket is called. */
  declared: string | undefined;
  /** What regions.json says this region's R2 jurisdiction is. */
  declaredJurisdiction: string | null;
}

/**
 * Pull `bucket_name` and `jurisdiction` out of the `[[r2_buckets]]` block whose
 * `binding` is BINDING.
 *
 * Deliberately a small hand parser rather than a TOML dependency: the shape is
 * fixed and the gate must not gain a dependency that could itself go stale. It
 * walks blocks so a second `[[r2_buckets]]` entry (CONFIG_BUCKET, which sits
 * immediately above in every file) cannot be mistaken for this one — the exact
 * mistake a naive `grep -A2 bucket_name` would make.
 */
export function extractBinding(
  tomlText: string,
  binding: string
): { bucket: string | null; jurisdiction: string | null } {
  const lines = tomlText.split('\n');
  let inBlock = false;
  let sawBinding = false;
  let bucket: string | null = null;
  let jurisdiction: string | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith('[')) {
      // A new table ends the previous one. If it was ours, we are done.
      if (sawBinding) break;
      inBlock = line === '[[r2_buckets]]';
      sawBinding = false;
      continue;
    }
    if (!inBlock) continue;
    const m = /^(\w+)\s*=\s*"([^"]*)"/.exec(line);
    if (!m) continue;
    if (m[1] === 'binding') sawBinding = m[2] === binding;
    if (sawBinding && m[1] === 'bucket_name') bucket = m[2];
    if (sawBinding && m[1] === 'jurisdiction') jurisdiction = m[2];
  }
  return { bucket: sawBinding || bucket !== null ? bucket : null, jurisdiction };
}

// ── Control: the extractor, both directions, before it is trusted ──────────
{
  const fixture = [
    '[[r2_buckets]]',
    'binding = "CONFIG_BUCKET"',
    'bucket_name = "decoy-configs"',
    'jurisdiction = "eu"',
    '',
    '[[r2_buckets]]',
    `binding = "${BINDING}"`,
    'bucket_name = "real-backups"',
    'jurisdiction = "eu"',
    '',
    '[vars]',
    'bucket_name = "trailing-decoy"',
  ].join('\n');
  const got = extractBinding(fixture, BINDING);
  if (got.bucket !== 'real-backups' || got.jurisdiction !== 'eu') {
    console.error(
      `✗ instrument control: the extractor read ${JSON.stringify(got)} from a fixture whose\n` +
        `  ${BINDING} block says bucket_name="real-backups", jurisdiction="eu". It is either\n` +
        `  reading the neighbouring CONFIG_BUCKET block or running past the table. Every\n` +
        `  comparison below would be meaningless.`
    );
    process.exit(1);
  }
  const noJur = extractBinding(fixture.replace('jurisdiction = "eu"\n\n[vars]', '\n[vars]'), BINDING);
  if (noJur.jurisdiction !== null) {
    console.error('✗ instrument control: an absent jurisdiction was reported as present.');
    process.exit(1);
  }
  if (extractBinding(fixture, 'NO_SUCH_BINDING').bucket !== null) {
    console.error(
      '✗ instrument control did not fire: a binding that is NOT in the fixture was\n' +
        '  reported as found, so a green run below would mean nothing.'
    );
    process.exit(1);
  }
}

const regionsPath = join(ROOT, 'regions.json');
if (!existsSync(regionsPath)) {
  console.error(`✗ regions.json not found at ${regionsPath}; refusing to pass vacuously.`);
  process.exit(1);
}
const regions: RegionRecord[] = JSON.parse(readFileSync(regionsPath, 'utf8')).regions;
if (!Array.isArray(regions) || regions.length === 0) {
  console.error('✗ regions.json parsed to zero regions; refusing to pass vacuously.');
  process.exit(1);
}

const deployments: Deployment[] = [];
for (const r of regions) {
  const jur = r.r2Jurisdiction ?? null;
  deployments.push({
    label: `stable/${r.id}`,
    toml: `workers/account/wrangler.${r.id}.toml`,
    declared: r.backupR2?.name,
    declaredJurisdiction: jur,
  });
  deployments.push({
    label: `edge/${r.id}`,
    toml: `workers/account/wrangler.edge-${r.id}.toml`,
    declared: r.edgeBackupR2?.name,
    declaredJurisdiction: jur,
  });
}

// Anti-vacuity floor: three regions x two channels. If regions.json ever loses
// a region this trips rather than silently checking less.
const EXPECTED = 6;
if (deployments.length !== EXPECTED) {
  console.error(
    `✗ expected ${EXPECTED} deployments (3 regions x stable+edge), built ${deployments.length}.\n` +
      '  Either regions.json changed shape or this gate is out of date. Refusing to\n' +
      '  report a verdict over a set this gate does not recognise.'
  );
  process.exit(1);
}

const problems: string[] = [];
for (const d of deployments) {
  const path = join(ROOT, d.toml);
  if (!existsSync(path)) {
    problems.push(`    ${d.label}: ${d.toml} does not exist`);
    continue;
  }
  const { bucket, jurisdiction } = extractBinding(readFileSync(path, 'utf8'), BINDING);
  if (bucket === null) {
    problems.push(`    ${d.label}: ${d.toml} declares no ${BINDING} binding`);
    continue;
  }
  if (!d.declared) {
    problems.push(
      `    ${d.label}: regions.json names no backup bucket ` +
        `(backupR2/edgeBackupR2), but the binding says "${bucket}"`
    );
    continue;
  }
  if (d.declared !== bucket) {
    problems.push(
      `    ${d.label}: regions.json says "${d.declared}", ${d.toml} binds "${bucket}"`
    );
  }
  if ((jurisdiction ?? null) !== d.declaredJurisdiction) {
    problems.push(
      `    ${d.label}: regions.json r2Jurisdiction=${JSON.stringify(d.declaredJurisdiction)}, ` +
        `${d.toml} jurisdiction=${JSON.stringify(jurisdiction ?? null)}`
    );
  }
}

if (problems.length > 0) {
  console.error(
    `✗ backup bucket conformance broken (${problems.length} problem(s)):\n${problems.join('\n')}\n\n` +
      '  regions.json is what the deploy hands the presign signer; the wrangler toml\n' +
      '  is what the Worker actually reads and GCs. When they disagree, clients upload\n' +
      '  chunks to one bucket while the sweep deletes from another, and nothing errors\n' +
      '  — the backup simply is not there when someone restores.\n\n' +
      '  Fix by making regions.json match the bindings (or the bindings match\n' +
      '  regions.json), then re-run. Do NOT reintroduce a global ACCOUNT_BACKUP_S3_BUCKET secret:\n' +
      '  one global name against six bindings is the defect this gate exists for.'
  );
  process.exit(1);
}

console.log(
  `✓ backup bucket conformance: ${deployments.length} deployment(s), bucket and\n` +
    '  jurisdiction agree between regions.json and every wrangler binding\n' +
    '  (extractor control fired both ways).\n' +
    '  Blind spot, stated so a green is not read as more than it is: this proves the\n' +
    '  two DECLARATIONS agree. It does not prove either bucket exists in Cloudflare,\n' +
    '  nor that the R2 credential is scoped to reach it.'
);
