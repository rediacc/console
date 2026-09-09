/**
 * The `scripts/` layout partition, enforced. W9 P2.0.
 *
 * WHY THIS EXISTS, AND WHAT IT IS NOT. `scripts/data/domains.json` classifies every file
 * under `scripts/` into 18 domains and says where each domain belongs; `scripts/lib/domains.ts`
 * can answer "who owns this path". Until this gate, NOTHING IMPORTED THAT MODULE and nothing
 * read that JSON, which is the state its own header names in one line: a JSON file nobody
 * executes is a document, not a partition. W9 P2 then moves 148 files on the strength of it.
 * A 148-file move guided by an unenforced document is a move whose first error is discovered
 * by whatever breaks next week.
 *
 * THE RISK IS THE OPPOSITE WAY ROUND FROM THE ONE THAT WAS WRITTEN DOWN. The worry on
 * record was that a set-equality gate would red during the move. There was no such gate:
 * nothing could red, in either direction, and six of the nine move rules are `incoming-*`
 * rules that map `.ci/scripts/**` into `scripts/**` and have not moved a file yet. The
 * classification is DONE. Enforcement is what was missing.
 *
 * THE THREE CLAUSES, and the split between them is the whole design.
 *
 *   1. TOTAL CLASSIFICATION, ENFORCING from day one. Every tracked file under `scripts/`
 *      matches a rule. Measured on the day this landed: 228 files, 0 unclassified, so this
 *      clause costs nothing today and refuses the 229th file that belongs to no domain.
 *      That is the clause that makes P2 safe: a file nobody classified is a file the move
 *      has no destination for, and the move is the moment that stops being theoretical.
 *
 *   2. IN PLACE, SHRINK-ONLY rather than blocking. 148 of those 228 are not yet in the home
 *      their rule names, because P2 has not run. Blocking on 148 files on day one gets a
 *      gate suppressed within a day, so the existing 148 are BASELINED and printed in full
 *      every run. What is refused is the 149th. `--write-baseline` REFUSES TO ADD, so the
 *      set can only fall, and it reaches zero in the same commit as P2's last move.
 *
 *   3. THE PARTITION IS A PARTITION, ENFORCING. No dead rule (a rule matching no file moves
 *      nothing and is a lie about the tree), no shadowing (first-match-wins means inserting
 *      a rule silently re-homes everything below it that it also matches), and every
 *      `stays: true` home exists on disk. The nine homes that do NOT exist are exactly the
 *      nine `stays: false` destinations P2 will create, and that is the difference the
 *      clause keys on.
 *
 * ANTI-VACUITY. The scope is enumerated INDEPENDENTLY of the rules -- `git ls-files scripts`
 * -- because a scope derived from the rules would make clause 1 a tautology: only files a
 * rule matched would ever be looked at, and nothing could be unclassified. A scope below its
 * floor is a broken enumeration and refuses rather than reporting clean. Rule liveness is
 * the same guarantee from the other side: an enumeration that returned nothing would leave
 * all 18 rules dead and clause 3 would say so.
 *
 * ---- gate ----
 * step: scripts/ domain partition
 * needs: node
 * lane: quality-code
 * selftest: true
 * why: scripts/data/domains.json classifies 228 files and scripts/lib/domains.ts can
 *      answer who owns a path, and until this gate nothing imported either. W9 P2
 *      moves 148 files on the strength of that partition, so it has to be enforced
 *      BEFORE the move rather than trusted during it
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import {
  type Classification,
  classify,
  type DomainPartition,
  type DomainRule,
  loadPartition,
} from '../lib/domains.js';
import { envRoot } from '../lib/repo-root.js';
import { commitBaseline, sharedSelftestCases } from '../lib/shrink-only-baseline.js';

/** Redirectable so the selftest drives a fixture tree rather than the tree being judged. */
const ROOT = envRoot('DOMAIN_PARTITION_ROOT');

const BASELINE = 'scripts/data/domain-layout-baseline.json';
const BASELINE_KEY = 'outOfPlace';

/**
 * A floor on the INDEPENDENT scope. 228 tracked files under `scripts/` today; the floor sits
 * far below that so it catches an enumeration that collapsed rather than a directory someone
 * legitimately pruned. Zero files is the case this exists for: `git ls-files` run outside a
 * repository exits 0 and prints nothing, and every clause below would then pass on nothing.
 */
const MIN_SCOPE = 120;

/**
 * The independent scope: what the partition claims to govern, asked of git rather than of the
 * rules.
 *
 * UNTRACKED-BUT-NOT-IGNORED FILES ARE IN IT, and that is not a detail. `git ls-files` alone
 * reports the INDEX, so a brand new script is invisible to this gate until somebody commits
 * it -- which is the one moment a reviewer could still be told it belongs to no domain.
 * `check:ci-python-lint` shipped that exact hole and its header records the cost: "27 files,
 * All checks passed!" while the newest and second-largest module in the program was
 * untracked and had never once been linted. `--exclude-standard` keeps gitignored build
 * output and caches out, which is what stops `__pycache__` becoming 200 findings.
 */
export function scopeOf(root: string): string[] {
  const out = execFileSync(
    'git',
    ['ls-files', '--cached', '--others', '--exclude-standard', 'scripts'],
    { cwd: root, encoding: 'utf-8' }
  )
    .split('\n')
    .filter(Boolean);
  return [...new Set(out)].sort();
}

/** Everything the incoming-* rules point at, which lives outside `scripts/` until P2 runs. */
export function incomingOf(root: string, partition: DomainPartition): string[] {
  const tracked = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
    cwd: root,
    encoding: 'utf-8',
  })
    .split('\n')
    .filter(Boolean);
  const out = new Set<string>();
  for (const file of tracked) {
    if (file.startsWith('scripts/')) continue;
    if (classify(partition, file).rule !== null) out.add(file);
  }
  return [...out].sort();
}

export interface Report {
  /** Files in scope that no rule owns. Clause 1. */
  unclassified: string[];
  /** `<file>: <ruleA> and <ruleB> disagree about its home`. Clause 3. */
  shadowed: string[];
  /** Rule ids matching no tracked file at all. Clause 3. */
  dead: string[];
  /** `<id>: <home>` for a `stays: true` rule whose home is not on disk. Clause 3. */
  missingHomes: string[];
  /** Files not yet in the home their rule names. Clause 2, baselined. */
  outOfPlace: string[];
  /** Files already home. Printed, so a reader sees the denominator. */
  inPlace: number;
}

/**
 * The whole judgement, pure over its inputs.
 *
 * `exists` is injected rather than reaching for `fs`, so the home check is drivable against
 * a hypothetical tree. Every clause here is exercised by the selftest with synthetic files
 * and a synthetic partition, which is the only way to see clause 1 fire: the real tree has
 * been at zero unclassified since the partition was written.
 */
export function judge(
  partition: DomainPartition,
  scope: readonly string[],
  incoming: readonly string[],
  exists: (relPath: string) => boolean
): Report {
  const unclassified: string[] = [];
  const outOfPlace: string[] = [];
  let inPlace = 0;
  const matchedBy = new Map<string, string[]>();

  const all = [...scope, ...incoming];
  for (const file of all) {
    const owners = partition.rules.filter((r) => classify({ ...partition, rules: [r] }, file).rule);
    if (owners.length > 0)
      matchedBy.set(
        file,
        owners.map((r) => r.id)
      );
    const c: Classification = classify(partition, file);
    if (c.rule === null) {
      // Only the INDEPENDENT half can be unclassified: the incoming half was enumerated by
      // asking the rules, so a miss there is not a finding, it is arithmetic.
      if (scope.includes(file)) unclassified.push(file);
      continue;
    }
    if (c.inPlace) inPlace++;
    else outOfPlace.push(file);
  }

  const homeOf = new Map(partition.rules.map((r) => [r.id, r.home]));
  const shadowed: string[] = [];
  for (const [file, ids] of matchedBy) {
    const homes = [...new Set(ids.map((id) => homeOf.get(id)))];
    if (homes.length > 1)
      shadowed.push(`${file}: ${ids.join(' and ')} disagree (${homes.join(' vs ')})`);
  }

  const anyMatch = (rule: DomainRule): boolean =>
    all.some((f) => classify({ ...partition, rules: [rule] }, f).rule !== null);
  const dead = partition.rules.filter((r) => !anyMatch(r)).map((r) => r.id);

  const missingHomes = partition.rules
    .filter((r) => r.stays && !exists(r.home))
    .map((r) => `${r.id}: ${r.home}`);

  return {
    unclassified: unclassified.sort(),
    shadowed: shadowed.sort(),
    dead: dead.sort(),
    missingHomes: missingHomes.sort(),
    outOfPlace: outOfPlace.sort(),
    inPlace,
  };
}

/** Out-of-place entries grouped by owning rule, for an advisory a person can read. */
export function groupByRule(partition: DomainPartition, files: readonly string[]): string[] {
  const byRule = new Map<string, string[]>();
  for (const f of files) {
    const c = classify(partition, f);
    const id = c.rule?.id ?? '(none)';
    byRule.set(id, [...(byRule.get(id) ?? []), f]);
  }
  return [...byRule.entries()]
    .sort()
    .map(([id, fs_]) => `${id}: ${fs_.length} file(s) -> ${classify(partition, fs_[0]).home}`);
}

const readBaseline = (root: string): string[] | null => {
  const file = path.join(root, BASELINE);
  if (!fs.existsSync(file)) return null;
  return (JSON.parse(fs.readFileSync(file, 'utf-8'))[BASELINE_KEY] ?? []) as string[];
};

function selftest(): boolean {
  let ok = true;
  const check = (label: string, cond: boolean, detail = ''): void => {
    if (cond) console.log(`  PASS  ${label}`);
    else {
      ok = false;
      console.error(`  FAIL  ${label}${detail ? ` -- ${detail}` : ''}`);
    }
  };

  const fixture: DomainPartition = {
    version: 1,
    onUnclassified: 'error',
    rules: [
      { id: 'lib', paths: ['scripts/lib/**'], home: 'scripts/lib', stays: true, why: 'x' },
      { id: 'gates', paths: ['scripts/check-*.ts'], home: 'scripts/gates', stays: false, why: 'x' },
    ],
  };
  const yes = (): boolean => true;

  // Clause 1, both directions. This is the one that cannot be seen to fire on the real
  // tree, because the real tree has been at zero unclassified since the day it was written.
  check(
    'an unclassified file in scope is a finding',
    judge(fixture, ['scripts/stray.ts'], [], yes).unclassified.length === 1
  );
  check(
    'CONTROL: a classified file is not',
    judge(fixture, ['scripts/lib/a.ts'], [], yes).unclassified.length === 0
  );
  check(
    'CONTROL: an unmatched file in the INCOMING half is arithmetic, not a finding',
    judge(fixture, [], ['.ci/whatever.sh'], yes).unclassified.length === 0
  );

  // Clause 2, both directions.
  check(
    'a file outside its home is out of place',
    judge(fixture, ['scripts/check-x.ts'], [], yes).outOfPlace.length === 1
  );
  check(
    'CONTROL: the same file inside its home is not',
    judge(fixture, ['scripts/gates/check-x.ts'], [], yes).outOfPlace.length === 0,
    JSON.stringify(judge(fixture, ['scripts/gates/check-x.ts'], [], yes).outOfPlace)
  );

  // Clause 3, all three, both directions.
  const shadowing: DomainPartition = {
    ...fixture,
    rules: [
      ...fixture.rules,
      { id: 'other', paths: ['scripts/check-*.ts'], home: 'scripts/ops', stays: false, why: 'x' },
    ],
  };
  check(
    'two rules claiming one file with different homes is reported as shadowing',
    judge(shadowing, ['scripts/check-x.ts'], [], yes).shadowed.length === 1
  );
  check(
    'CONTROL: the live partition shadows nothing',
    judge(fixture, ['scripts/check-x.ts', 'scripts/lib/a.ts'], [], yes).shadowed.length === 0
  );
  check(
    'a rule matching no file in the tree is reported as dead',
    judge(fixture, ['scripts/lib/a.ts'], [], yes).dead.join() === 'gates'
  );
  check(
    'CONTROL: a rule with one match is not dead',
    judge(fixture, ['scripts/lib/a.ts', 'scripts/check-x.ts'], [], yes).dead.length === 0
  );
  check(
    'a stays:true home that is not on disk is reported',
    judge(fixture, ['scripts/lib/a.ts'], [], () => false).missingHomes.join() === 'lib: scripts/lib'
  );
  check(
    'CONTROL: a stays:FALSE home that is not on disk is not, because P2 creates it',
    !judge(fixture, ['scripts/check-x.ts'], [], (h) => h !== 'scripts/gates').missingHomes.some(
      (m) => m.startsWith('gates:')
    )
  );

  // The real partition must load and be structurally valid, or every clause above is
  // exercised only against a fixture.
  let live: DomainPartition | null = null;
  try {
    live = loadPartition(path.join(ROOT, 'scripts', 'data', 'domains.json'));
  } catch (e) {
    check('the live partition loads', false, String(e));
  }
  check(
    'the live partition has rules',
    (live?.rules.length ?? 0) >= 10,
    String(live?.rules.length)
  );

  for (const c of sharedSelftestCases()) check(c.name, c.ok, c.detail);
  return ok;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest() ? 0 : 1;
  if (!selftest()) {
    console.error("REFUSING to report on the tree: this gate's own controls failed.");
    return 2;
  }

  const partition = loadPartition(path.join(ROOT, 'scripts', 'data', 'domains.json'));
  const scope = scopeOf(ROOT);
  if (scope.length < MIN_SCOPE) {
    console.error(
      `only ${scope.length} tracked file(s) under scripts/, floor ${MIN_SCOPE}. The enumeration ` +
        'is broken, not the tree; every clause below would pass on nothing.'
    );
    return 1;
  }
  const incoming = incomingOf(ROOT, partition);
  const report = judge(partition, scope, incoming, (h) => fs.existsSync(path.join(ROOT, h)));

  if (argv.includes('--write-baseline')) {
    const wrote = commitBaseline({
      path: path.join(ROOT, BASELINE),
      label: BASELINE,
      noun: 'out-of-place file',
      key: BASELINE_KEY,
      note:
        'W9 P2.0. Files whose domain rule names a home they are not in yet. SHRINK ONLY: ' +
        'W9 P2 drains this to empty as it moves them, and --write-baseline refuses to add.',
      current: report.outOfPlace,
      firstSeed: argv.includes('--first-seed'),
      read: (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf-8') : null),
      write: (p, body) => fs.writeFileSync(p, body),
    });
    return wrote ? 0 : 1;
  }

  const hard: string[] = [];
  for (const f of report.unclassified)
    hard.push(`UNCLASSIFIED ${f} -- no rule in scripts/data/domains.json owns it`);
  hard.push(...report.shadowed.map((s) => `SHADOWED ${s}`));
  hard.push(
    ...report.dead.map(
      (id) =>
        `DEAD RULE ${id} -- it matches no tracked file, so it moves nothing and describes nothing`
    )
  );
  hard.push(
    ...report.missingHomes.map(
      (m) => `MISSING HOME ${m} -- a stays:true rule must name a directory that exists`
    )
  );

  const baseline = readBaseline(ROOT);
  if (baseline === null) {
    console.error(
      `${BASELINE} does not exist. Seed it once with --write-baseline --first-seed, ` +
        'or clause 2 is unenforced and its green means nothing.'
    );
    return 1;
  }
  const known = new Set(baseline);
  const grew = report.outOfPlace.filter((f) => !known.has(f));
  const fixed = baseline.filter((f) => !report.outOfPlace.includes(f));

  if (grew.length > 0) {
    hard.push(
      ...grew.map(
        (f) =>
          `NEW OUT OF PLACE ${f} -- put it in ${classify(partition, f).home}. Do not add it to the baseline.`
      )
    );
  }
  if (fixed.length > 0) {
    hard.push(
      `${fixed.length} baselined file(s) are now in place. Drain them: ` +
        `tsx scripts/gates/check-domain-partition.ts --write-baseline`
    );
  }

  if (hard.length > 0) {
    console.error('');
    for (const line of hard) console.error(`  ${line}`);
    console.error('');
    return 1;
  }

  console.log(
    `scripts/ domain partition: ${scope.length} tracked file(s) in scope + ${incoming.length} incoming, ` +
      `${partition.rules.length} rule(s), 0 unclassified, 0 shadowed, 0 dead`
  );
  console.log(
    `  in place ${report.inPlace}, awaiting W9 P2 ${report.outOfPlace.length} (baselined, shrink-only):`
  );
  for (const line of groupByRule(partition, report.outOfPlace)) console.log(`    ${line}`);
  console.log(
    '  Clause 2 is ADVISORY on the baselined set and BLOCKING on any addition. It reaches ' +
      "zero in the same commit as P2's last move."
  );
  return 0;
}

process.exitCode = main(process.argv.slice(2));
