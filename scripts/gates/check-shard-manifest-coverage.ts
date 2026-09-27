#!/usr/bin/env tsx
/**
 * Every committed shard manifest (`.ci/config/shards/<lane>.json`) must cover its lane's
 * REAL unit set exactly: every unit in one leg, no leg naming a unit that does not exist.
 *
 * WHY THIS EXISTS. `packages/e2e-tests/tests/25-backup-chunk-store.test.ts` was a real
 * Playwright project (`playwright.config.ts`, `test-25`, listed by `playwright test
 * --list`), and the hand-authored `test-e2e-workers.json` never named it. A sharded CI leg
 * runs ONLY the ids its manifest leg holds, so suite 25 ran in no CI job at all, and
 * every leg was green, because a leg cannot report on a file it was never handed
 * (found 2026-09-27).
 *
 * WHAT IT COMPARES. For each manifest, the lane's units come from the SAME source CI's
 * shard plan uses:
 *   - a lane with a `LANE_ENUMERATORS` entry (`scripts/ci-runner/unit-enumerators.ts`):
 *     that enumerator, called exactly as `run.ts --list-units` calls it;
 *   - a check-gate lane (today `quality-code`, written by `gate-bind --write`): the
 *     `gates.lock.json` entries whose `ci` is a step in that job, which is what
 *     `shardPlan` filters on (`laneJobOf`).
 * A lane with neither is UN-ENUMERABLE and reds. It is never skipped: a manifest this
 * gate cannot check is a manifest nothing checks.
 *
 * `#<bucket>` SUFFIXES. `run-e2e.sh` splits one spec file into describe-group buckets
 * (`13-postgres-fork-isolation.test.ts#part1/2/3`), resolving each bucket name through
 * its `E2E_SHARD_GREP_BUCKETS` map. An id `<file>#<bucket>` counts toward the unit
 * `<file>`, and a bucketed file must carry EVERY bucket that map declares: a missing
 * bucket is that bucket's describe groups running in no CI job, the same defect as a
 * missing file. A bucket suffix on any other lane reds, because no other runner resolves
 * one.
 *
 * THE ENVIRONMENT IS PINNED, NOT INHERITED. `playwright.config.ts` gates projects on `CI`,
 * `FULL_INTEGRATION`, `CLI_SUITE` and `BACKUP_STORAGE_SUITE`, and it loads the untracked
 * `packages/e2e-tests/.env`, which sets `CI` on at least one dev box. The sharded E2E
 * Workers legs run with `CI` set and those three flags unset (the full-integration suites
 * ride `--also`, not the manifest), so this gate sets exactly that before enumerating, and
 * dotenv does not override a variable that is already present. The verdict therefore
 * does not depend on whose `.env` it runs beside.
 *
 * ANTI-VACUITY. Zero manifests, a lane whose unit set is empty, and a manifest holding
 * zero ids are failures. Every real run also plants two violations per lane in memory
 * (one real unit dropped, one phantom id added) against the REAL enumerated set and the
 * REAL manifest, and refuses a green if either plant fails to red.
 *
 * Usage:
 *   npx tsx scripts/gates/check-shard-manifest-coverage.ts              the real run
 *   npx tsx scripts/gates/check-shard-manifest-coverage.ts --selftest   prove it can fail
 *   npx tsx scripts/gates/check-shard-manifest-coverage.ts --shards-dir <dir>
 *       check the manifests in <dir> instead of `.ci/config/shards` (a scratch-copy plant)
 *
 * Exit codes: 0 every manifest covers its lane exactly; 1 a finding, an un-enumerable
 * lane, or a vacuous input.
 *
 * ---- gate ----
 * step: Shard manifest coverage
 * needs: node, go, private/renet, private/account
 * lane: quality-go
 * selftest: true
 * why: a shard leg runs only the ids its committed manifest names, so a unit the
 *   manifest omits runs in no CI job while every leg stays green; suite 25 of E2E
 *   Workers did exactly that until 2026-09-27
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { parseShardManifest, type ShardManifestFile } from '../ci-runner/shard-manifest.js';
import { LANE_ENUMERATORS } from '../ci-runner/unit-enumerators.js';
import { GREEN, NC, RED } from '../lib/console.js';
import { refused } from '../lib/controls.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const DEFAULT_SHARDS_DIR = path.join(ROOT, '.ci', 'config', 'shards');
const LOCK = path.join(ROOT, 'scripts', 'ci-runner', 'gates.lock.json');
const RUN_E2E = path.join(ROOT, '.ci', 'scripts', 'test', 'run-e2e.sh');

/** Lanes whose runner resolves a `#<bucket>` suffix, and where its bucket map lives. */
const BUCKET_LANES: Readonly<Record<string, string>> = {
  'test-e2e-workers': '.ci/scripts/test/run-e2e.sh (E2E_SHARD_GREP_BUCKETS)',
};

/** What each enumerator needs from the job it runs in; printed whenever one cannot run, so a missing tool reads as a missing tool and not as flake. */
const LANE_NEEDS: Readonly<Record<string, string>> = {
  'test-e2e-workers':
    'node plus the root `npm ci` (packages/e2e-tests resolves @playwright/test); runs `npx playwright test --list`',
  'test-account-e2e': 'the private/account submodule checked out (reads private/account/e2e/tests)',
  'test-renet-go':
    '`go` on PATH (actions/setup-go, go-version-file: private/renet/go.mod) and the private/renet submodule; runs `go list ./pkg/... ./cmd/...`',
  'test-renet-integration':
    'the private/renet submodule checked out (reads private/renet/tests/integration)',
};

/** What the sharded E2E Workers legs run under; see the header. `''` means unset-but-present, so dotenv leaves it alone. */
export const PINNED_ENV: Readonly<Record<string, string>> = {
  CI: 'true',
  FULL_INTEGRATION: '',
  CLI_SUITE: '',
  BACKUP_STORAGE_SUITE: '',
};

export interface Finding {
  lane: string;
  kind: 'missing' | 'phantom' | 'duplicate' | 'bucket' | 'leg' | 'empty';
  message: string;
}

/** `e2e-workers:13-x.test.ts#part2` -> base `e2e-workers:13-x.test.ts`, bucket `part2`. */
export function splitId(id: string): { base: string; bucket: string | null } {
  const at = id.indexOf('#');
  return at < 0 ? { base: id, bucket: null } : { base: id.slice(0, at), bucket: id.slice(at + 1) };
}

/** The bucket names `run-e2e.sh` declares in `E2E_SHARD_GREP_BUCKETS`, in source order. */
export function parseBucketKeys(runE2eSource: string): string[] {
  const block = /declare -A E2E_SHARD_GREP_BUCKETS=\(([\s\S]*?)\n\s*\)/.exec(runE2eSource);
  if (block === null) return [];
  return [...(block[1] as string).matchAll(/\["([^"]+)"\]=/g)].map((m) => m[1] as string);
}

/**
 * The whole comparison, pure. `units` is the lane's enumerated id set; `buckets` is the
 * full bucket-name set when this lane's runner resolves `#<bucket>`, else null.
 */
export function compareManifest(
  file: ShardManifestFile,
  units: readonly string[],
  buckets: readonly string[] | null
): Finding[] {
  const lane = file.lane;
  const out: Finding[] = [];
  const add = (kind: Finding['kind'], message: string): void => {
    out.push({ lane, kind, message });
  };
  const unitSet = new Set(units);

  // Leg structure: a leg whose index no matrix leg asks for runs nowhere, silently.
  const seenIndex = new Set<number>();
  for (const leg of file.legs) {
    if (!Number.isInteger(leg.index) || leg.index < 1 || leg.index > file.of) {
      add(
        'leg',
        `leg index ${leg.index} is outside 1..${file.of}: no matrix leg asks for it, so its ` +
          `${leg.ids.length} id(s) run in no CI job. Move them into a leg 1..${file.of}.`
      );
    }
    if (seenIndex.has(leg.index)) {
      add('leg', `leg index ${leg.index} appears twice; a leg reads only the first one it finds.`);
    }
    seenIndex.add(leg.index);
    if (leg.ids.length === 0) {
      add(
        'empty',
        `leg ${leg.index} is EMPTY; a leg with nothing to run reports green having run nothing.`
      );
    }
  }
  for (let i = 1; i <= file.of; i++) {
    if (!seenIndex.has(i)) add('leg', `leg ${i} of ${file.of} is missing from "legs".`);
  }

  // Per id: where it sits, what it resolves to.
  const whereId = new Map<string, number[]>();
  const plainBases = new Map<string, number[]>();
  const bucketsOf = new Map<string, Map<string, number[]>>();
  let total = 0;
  for (const leg of file.legs) {
    for (const id of leg.ids) {
      total += 1;
      whereId.set(id, [...(whereId.get(id) ?? []), leg.index]);
      const { base, bucket } = splitId(id);
      if (!unitSet.has(base)) {
        add(
          'phantom',
          `leg ${leg.index}: "${id}" names a unit that does not exist (the lane's enumerator ` +
            `does not produce "${base}"). Remove it, or fix the name to the real unit.`
        );
      }
      if (bucket === null) {
        plainBases.set(base, [...(plainBases.get(base) ?? []), leg.index]);
        continue;
      }
      if (buckets === null) {
        add(
          'bucket',
          `leg ${leg.index}: "${id}" carries a "#${bucket}" suffix, but no runner for lane ` +
            `${lane} resolves one (only ${Object.keys(BUCKET_LANES).join(', ')} do). Name the whole unit.`
        );
        continue;
      }
      if (!buckets.includes(bucket)) {
        add(
          'bucket',
          `leg ${leg.index}: "${id}" names bucket "${bucket}", which ${BUCKET_LANES[lane] ?? 'the runner'} ` +
            `does not declare (declared: ${buckets.join(', ') || 'none'}). The leg would refuse to start.`
        );
      }
      const perFile = bucketsOf.get(base) ?? new Map<string, number[]>();
      perFile.set(bucket, [...(perFile.get(bucket) ?? []), leg.index]);
      bucketsOf.set(base, perFile);
    }
  }
  if (total === 0) add('empty', 'the manifest names ZERO ids; its legs would run nothing.');

  for (const [id, legs] of whereId) {
    if (legs.length > 1) {
      add(
        'duplicate',
        `"${id}" is listed ${legs.length} times (leg(s) ${legs.join(', ')}), so it runs more ` +
          'than once per CI run. Keep it in one leg; only distinct #<bucket> ids of one file may be split.'
      );
    }
  }
  for (const [base, perFile] of bucketsOf) {
    const plain = plainBases.get(base);
    if (plain !== undefined) {
      add(
        'duplicate',
        `"${base}" is listed whole (leg(s) ${plain.join(', ')}) AND as #<bucket> ids ` +
          `(${[...perFile.keys()].join(', ')}), so its describe groups run twice. Keep one form.`
      );
    }
    for (const b of buckets ?? []) {
      if (!perFile.has(b)) {
        add(
          'missing',
          `"${base}#${b}" is in no leg: "${base}" is split into buckets, and bucket "${b}"'s ` +
            'describe groups therefore run in no CI job. Add it to a leg.'
        );
      }
    }
  }

  for (const unit of units) {
    if (!plainBases.has(unit) && !bucketsOf.has(unit)) {
      add(
        'missing',
        `"${unit}" runs in no CI job: the lane's enumerator lists it and no leg names it. ` +
          'Add it to a leg (the lightest one, by the lane-durations estimate).'
      );
    }
  }
  return out;
}

interface LockEntry {
  id: string;
  ci: { kind: string; job?: string };
}

/** The unit set of a check-gate lane: lock entries whose CI home is a step in `lane`. */
export function lockUnits(lock: readonly LockEntry[], lane: string): string[] {
  return lock.filter((e) => e.ci.kind === 'step' && e.ci.job === lane).map((e) => e.id);
}

interface LaneUnits {
  units: string[];
  source: string;
}

async function enumerateLane(lane: string): Promise<LaneUnits> {
  const enumerator = LANE_ENUMERATORS[lane];
  if (enumerator !== undefined) {
    const units = await enumerator(ROOT);
    return { units: units.map((u) => u.id), source: `unit-enumerators.ts ${enumerator.name}` };
  }
  const lock = JSON.parse(fs.readFileSync(LOCK, 'utf8')) as LockEntry[];
  const units = lockUnits(lock, lane);
  if (units.length > 0) {
    return { units, source: 'gates.lock.json step entries' };
  }
  throw new Error(
    `lane ${lane} is UN-ENUMERABLE: it has no LANE_ENUMERATORS entry in ` +
      'scripts/ci-runner/unit-enumerators.ts and no step entry in scripts/ci-runner/gates.lock.json. ' +
      'Declare an enumerator for it; a manifest this gate cannot check is a manifest nothing checks.'
  );
}

/** Drop one real unit, then add a phantom; both MUST red on the real manifest and units. */
function liveControls(
  file: ShardManifestFile,
  units: readonly string[],
  buckets: readonly string[] | null
): string | null {
  const victim = units[0];
  if (victim === undefined) return 'no unit to plant against';
  const dropped: ShardManifestFile = {
    ...file,
    legs: file.legs.map((l) => ({ ...l, ids: l.ids.filter((id) => splitId(id).base !== victim) })),
  };
  const firedDrop = compareManifest(dropped, units, buckets).some(
    (f) => f.kind === 'missing' && f.message.includes(`"${victim}`)
  );
  if (!firedDrop) return `planted drop of "${victim}" did not red`;
  const phantomId = `${victim}__shard_coverage_probe__`;
  const withPhantom: ShardManifestFile = {
    ...file,
    legs: file.legs.map((l, i) => (i === 0 ? { ...l, ids: [...l.ids, phantomId] } : l)),
  };
  const firedPhantom = compareManifest(withPhantom, units, buckets).some(
    (f) => f.kind === 'phantom' && f.message.includes(phantomId)
  );
  if (!firedPhantom) return `planted phantom "${phantomId}" did not red`;
  return null;
}

async function main(): Promise<number> {
  const dirAt = process.argv.indexOf('--shards-dir');
  const shardsDir = dirAt >= 0 ? path.resolve(process.argv[dirAt + 1] ?? '') : DEFAULT_SHARDS_DIR;
  const rel = (p: string): string => path.relative(ROOT, p) || p;

  const names = fs.existsSync(shardsDir)
    ? fs
        .readdirSync(shardsDir)
        .filter((f) => f.endsWith('.json'))
        .sort()
    : [];
  if (names.length === 0) {
    return refused(
      `${RED}✗ ${rel(shardsDir)} holds ZERO shard manifests. The gate is not seeing the tree; ` +
        `its green would mean nothing.${NC}`
    );
  }

  for (const [k, v] of Object.entries(PINNED_ENV)) process.env[k] = v;
  console.log(
    `shard manifest coverage: ${names.length} manifest(s) in ${rel(shardsDir)}; enumerating with ` +
      `${Object.entries(PINNED_ENV)
        .map(([k, v]) => `${k}=${v === '' ? '(unset)' : v}`)
        .join(' ')} pinned`
  );

  const bucketKeys = parseBucketKeys(fs.readFileSync(RUN_E2E, 'utf8'));
  const findings: Finding[] = [];
  const failures: string[] = [];
  let unitTotal = 0;
  let idTotal = 0;
  for (const name of names) {
    const lane = name.replace(/\.json$/, '');
    const where = rel(path.join(shardsDir, name));
    let file: ShardManifestFile;
    try {
      file = parseShardManifest(fs.readFileSync(path.join(shardsDir, name), 'utf8'), lane);
    } catch (err) {
      failures.push(`${where}: ${(err as Error).message}`);
      continue;
    }
    let lu: LaneUnits;
    try {
      lu = await enumerateLane(lane);
    } catch (err) {
      const needs = LANE_NEEDS[lane];
      failures.push(
        `${where}: cannot enumerate lane ${lane}: ${(err as Error).message.trim()}` +
          (needs === undefined ? '' : `\n    this lane's enumerator needs: ${needs}`)
      );
      continue;
    }
    if (lu.units.length === 0) {
      failures.push(`${where}: lane ${lane} enumerated ZERO units; nothing to compare against.`);
      continue;
    }
    const buckets = lane in BUCKET_LANES ? bucketKeys : null;
    const own = compareManifest(file, lu.units, buckets);
    const control = liveControls(file, lu.units, buckets);
    if (control !== null) {
      failures.push(
        `${where}: live control failed (${control}); the comparison cannot fail, so its green is void.`
      );
    }
    const ids = file.legs.reduce((n, l) => n + l.ids.length, 0);
    const bucketIds = file.legs.reduce(
      (n, l) => n + l.ids.filter((id) => id.includes('#')).length,
      0
    );
    unitTotal += lu.units.length;
    idTotal += ids;
    const mark = own.length === 0 ? `${GREEN}✓${NC}` : `${RED}✗${NC}`;
    console.log(
      `  ${mark} ${lane}: ${lu.units.length} unit(s) from ${lu.source}; ${file.legs.length} leg(s), ` +
        `${ids} id(s)${bucketIds > 0 ? ` (${bucketIds} #bucket id(s))` : ''}; ` +
        `${own.length} finding(s); live plants red`
    );
    for (const f of own) findings.push({ ...f, message: `${where}: ${f.message}` });
  }

  for (const f of failures) console.error(`${RED}✗ ${f}${NC}`);
  for (const f of findings) console.error(`${RED}✗ [${f.kind}] ${f.message}${NC}`);
  if (failures.length > 0 || findings.length > 0) {
    return refused(
      `${RED}✗ shard manifest coverage: ${findings.length} finding(s), ${failures.length} lane(s) ` +
        `unchecked. An unchecked lane is a failure, not a pass.${NC}`
    );
  }
  console.log(
    `${GREEN}✓ shard manifest coverage: ${names.length} manifest(s), ${unitTotal} unit(s), ` +
      `${idTotal} id(s); every unit in exactly one leg, no phantom id${NC}`
  );
  return 0;
}

function selftest(): number {
  const mk = (lane: string, of: number, legs: string[][]): ShardManifestFile => ({
    lane,
    of,
    generatedAt: '2026-09-27T00:00:00.000Z',
    legs: legs.map((ids, i) => ({ index: i + 1, ids })),
  });
  const E = 'e2e-workers:';
  const units = [`${E}01.test.ts`, `${E}13.test.ts`, `${E}25.test.ts`];
  const B = ['part1', 'part2', 'part3'];
  const clean = mk('test-e2e-workers', 3, [
    [`${E}01.test.ts`, `${E}13.test.ts#part1`],
    [`${E}25.test.ts`, `${E}13.test.ts#part2`],
    [`${E}13.test.ts#part3`],
  ]);
  const kinds = (f: Finding[]): string => f.map((x) => x.kind).join(',');
  const has = (f: Finding[], kind: Finding['kind'], needle: string): boolean =>
    f.some((x) => x.kind === kind && x.message.includes(needle));
  const runE2eFixture =
    'declare -A E2E_SHARD_GREP_BUCKETS=(\n    ["part1"]="A|B"\n    ["part2"]="C|D"\n    ["part3"]="E|F"\n)\n';

  const cases: { name: string; ok: boolean; detail?: string }[] = [
    // Controls first: each planted violation must red.
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}13.test.ts#part2`],
          [`${E}13.test.ts#part3`],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: a unit no leg names (suite 25) reds as "runs in no CI job"',
        ok: f.some(
          (x) =>
            x.kind === 'missing' &&
            x.message.includes('25.test.ts') &&
            x.message.includes('runs in no CI job')
        ),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk(
          'test-e2e-workers',
          3,
          [...clean.legs.map((l) => l.ids.slice())].map((ids, i) =>
            i === 0 ? [...ids, `${E}99-gone.test.ts`] : ids
          )
        ),
        units,
        B
      );
      return {
        name: 'FIRES: a phantom id reds as "names a unit that does not exist"',
        ok: has(f, 'phantom', '99-gone') && f.length === 1,
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}25.test.ts`, `${E}13.test.ts#part2`, `${E}01.test.ts`],
          [`${E}13.test.ts#part3`],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: one id in two legs reds as a duplicate',
        ok: has(f, 'duplicate', '01.test.ts') && f.length === 1,
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}25.test.ts`, `${E}13.test.ts#part1`],
          [`${E}13.test.ts#part2`, `${E}13.test.ts#part3`],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: the SAME bucket in two legs is a duplicate',
        ok: has(f, 'duplicate', '#part1'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}25.test.ts`, `${E}13.test.ts#part2`],
          [`${E}13.test.ts`],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: a file listed whole AND bucketed is a duplicate',
        ok: has(f, 'duplicate', 'listed whole'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}25.test.ts`, `${E}13.test.ts#part2`],
          [],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: a split file missing one bucket reds (its describes run nowhere)',
        ok: has(f, 'missing', '13.test.ts#part3'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-e2e-workers', 3, [
          [`${E}01.test.ts`, `${E}13.test.ts#part1`],
          [`${E}25.test.ts`, `${E}13.test.ts#part2`],
          [`${E}13.test.ts#part3`, `${E}13.test.ts#part9`],
        ]),
        units,
        B
      );
      return {
        name: 'FIRES: a bucket run-e2e.sh does not declare reds',
        ok: has(f, 'bucket', '"part9"'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('test-account-e2e', 1, [['a:x.test.ts#part1']]),
        ['a:x.test.ts'],
        null
      );
      return {
        name: 'FIRES: a #bucket on a lane whose runner resolves none reds',
        ok: has(f, 'bucket', 'no runner'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        {
          ...clean,
          legs: [...clean.legs.slice(0, 2), { index: 4, ids: [`${E}13.test.ts#part3`] }],
        },
        units,
        B
      );
      return {
        name: 'FIRES: a leg index outside 1..of reds (no matrix leg runs it)',
        ok: has(f, 'leg', 'outside 1..3') && has(f, 'leg', 'leg 3 of 3 is missing'),
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(mk('test-renet-go', 1, [[]]), ['pkg/a'], null);
      return {
        name: 'FIRES: a manifest with zero ids is vacuous, not green',
        ok: has(f, 'empty', 'ZERO ids') && has(f, 'missing', 'pkg/a'),
        detail: kinds(f),
      };
    })(),
    // Negative controls: these must NOT red.
    (() => {
      const f = compareManifest(clean, units, B);
      return {
        name: 'MATCH: distinct #partN buckets of one file across legs is clean',
        ok: f.length === 0,
        detail: kinds(f),
      };
    })(),
    (() => {
      const f = compareManifest(
        mk('quality-code', 2, [['check:a', 'check:b'], ['check:c']]),
        ['check:c', 'check:b', 'check:a'],
        null
      );
      return {
        name: 'MATCH: order of units vs ids does not matter',
        ok: f.length === 0,
        detail: kinds(f),
      };
    })(),
    // Helpers.
    {
      name: 'splitId maps a #partN id to its base file unit',
      ok:
        splitId(`${E}13.test.ts#part2`).base === `${E}13.test.ts` &&
        splitId(`${E}13.test.ts#part2`).bucket === 'part2' &&
        splitId('check:x').bucket === null,
    },
    {
      name: 'parseBucketKeys reads the bucket names from a run-e2e.sh-shaped block',
      ok: parseBucketKeys(runE2eFixture).join(',') === 'part1,part2,part3',
    },
    {
      name: 'CONTROL: parseBucketKeys finds no bucket in a file without the map',
      ok: parseBucketKeys('echo hi\n').length === 0,
    },
    (() => {
      const real = parseBucketKeys(fs.readFileSync(RUN_E2E, 'utf8'));
      return {
        name: 'the REAL run-e2e.sh declares at least one bucket (the parser sees the file)',
        ok: real.length > 0,
        detail: real.join(','),
      };
    })(),
    {
      name: 'lockUnits takes step entries of the lane only, not local-only or other jobs',
      ok:
        lockUnits(
          [
            { id: 'a', ci: { kind: 'step', job: 'quality-code' } },
            { id: 'b', ci: { kind: 'step', job: 'quality-go' } },
            { id: 'c', ci: { kind: 'local-only' } },
          ],
          'quality-code'
        ).join(',') === 'a',
    },
    (() => {
      const msg = liveControls(clean, units, B);
      return {
        name: 'the live controls the real run applies do red on a clean fixture',
        ok: msg === null,
        detail: msg ?? '',
      };
    })(),
  ];

  let failed = 0;
  for (const c of cases) {
    if (c.ok) console.log(`  ${GREEN}PASS${NC} ${c.name}`);
    else {
      failed += 1;
      console.error(`  ${RED}FAIL${NC} ${c.name}${c.detail ? ` (${c.detail})` : ''}`);
    }
  }
  if (failed > 0) {
    console.error(`${RED}✗ selftest: ${failed} of ${cases.length} case(s) failed${NC}`);
    return 1;
  }
  console.log(`${GREEN}✓ selftest: ${cases.length} case(s) passed${NC}`);
  return 0;
}

process.exit(process.argv.includes('--selftest') ? selftest() : await main());
