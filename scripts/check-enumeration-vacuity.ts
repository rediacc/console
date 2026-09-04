/**
 * check:ci-enumeration-vacuity -- a check that enumerates a corpus must refuse an EMPTY one.
 *
 * WHY THIS EXISTS. A gate that scans the tree and finds nothing prints a tick. The tick is
 * indistinguishable from a clean tree, and it is the single most common way a gate here has
 * gone quietly blind:
 *
 *   check_syncpack_sources.py     ran in a job with no submodules, lost the manifests it
 *                                 exists for, and reported correct exclusions as dead.
 *   check_docker_npm_pins.py      counted files-with-findings and printed "0 with an npm
 *                                 install" beside a pass, on its FIRST run.
 *   check_bws_map.py              assertion 13 could have passed a tree where the cutover
 *                                 had been reverted, because zero reads is not zero
 *                                 problems, it is no subject.
 *   retire-shadowed-secrets.py    located every edit by one literal step name; a rename
 *                                 made it a no-op that reported "already retired?".
 *
 * Each was fixed by hand, and each fix was invisible to every other gate. That is the i18n
 * lesson exactly: the class returns because nothing watches the class.
 *
 * THE RULE. A tracked check or gate-test script that ENUMERATES (git ls-files, a glob, a
 * recursive walk) must also carry a VACUITY GUARD: a named floor (`MIN_*`), an explicit
 * refusal on an empty result, or the word VACUOUS in a failure path. What the guard says is
 * the author's business; that there IS one is this gate's.
 *
 * SEEDED, AND THAT IS THE DESIGN. Measured 2026-09-04: 67 enumerating checks, 36 already
 * guarded, 31 not. A gate that opens with 31 findings is a wall, and this repo has written
 * down twice what walls become. The 31 are frozen as a baseline that may only SHRINK, so no
 * NEW enumerating check may skip its floor while the backlog drains at whatever pace it
 * drains. Growth is refused on the write path as well as the read path, via the shared
 * composition module -- a reseed that drains ten and absorbs one prints a smaller number and
 * is still a violation.
 *
 * Usage: npx tsx scripts/check-enumeration-vacuity.ts [--write-baseline] [--selftest]
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

import { commitBaseline } from './lib/shrink-only-baseline.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const BASELINE = path.join(ROOT, 'scripts/data/enumeration-vacuity-baseline.json');

/** Scripts this gate judges: the check and gate-test families, any language. */
const SUBJECT_RE = /\/(check|test)[-_][\w-]+\.(py|sh|ts)$/;

/**
 * Does this source ENUMERATE a corpus? Deliberately narrow: a script that reads one named
 * config file has no enumeration to be empty, and demanding a floor of it would be noise.
 */
export const enumerates = (src: string): boolean =>
  /git\s+ls-files|\.glob\(|\.rglob\(|globSync\(|readdirSync\(|find\s+\S+\s+-(name|type)\b/.test(
    stripHeredocs(src)
  );

/**
 * A shell heredoc body is DATA, not code this file executes.
 *
 * Caught by this gate on its own author: a gate-test whose heredoc carries fixture text
 * containing `.glob(` was reported as an unguarded enumerating check. It enumerates
 * nothing -- the string is an argument to a probe. Reading a quoted body as source is
 * the same class of mistake as reading a comment as code, which this repo already has
 * a trap written down for.
 *
 * Only `<<'TAG'` and `<<"TAG"` are stripped: an UNQUOTED heredoc is interpolated by the
 * shell and can legitimately carry a command, so leaving it in is the safe direction.
 */
export const stripHeredocs = (src: string): string => {
  const out: string[] = [];
  let tag: string | null = null;
  for (const line of src.split('\n')) {
    if (tag === null) {
      const open = /<<-?\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]/.exec(line);
      out.push(line);
      if (open) tag = open[1];
      continue;
    }
    if (line.trim() === tag) tag = null;
  }
  return out.join('\n');
};

/**
 * Does it carry a vacuity guard? Any of the three shapes this repo already uses, because
 * the point is that SOMETHING refuses an empty corpus, not that it is spelled one way.
 */
export const hasVacuityGuard = (src: string): boolean =>
  /\bMIN_[A-Z][A-Z0-9_]*\b/.test(src) ||
  /VACUOUS|vacuous/.test(src) ||
  /\bfloor\b/.test(src) ||
  /refusing to pass|proved nothing|lost its subject|lost the corpus/.test(src);

const tracked = (): string[] =>
  execFileSync('git', ['-C', ROOT, 'ls-files', '.ci/scripts', 'scripts'], { encoding: 'utf8' })
    .split('\n')
    .filter((f) => f && SUBJECT_RE.test(f));

export const findings = (read: (f: string) => string, files: string[]): string[] =>
  files.filter((f) => {
    const src = read(f);
    return enumerates(src) && !hasVacuityGuard(src);
  });

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean, detail?: unknown): void => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) {
      bad += 1;
      if (detail !== undefined) console.log(`        ${JSON.stringify(detail)}`);
    }
  };

  check('a git ls-files scan counts as enumeration', enumerates('out = git ls-files .ci'));
  check('a python glob counts', enumerates('for p in root.glob("*.yml"):'));
  check('a shell find counts', enumerates('find .ci/scripts -name "*.sh"'));
  check(
    'a QUOTED heredoc body is data, not an enumeration',
    !enumerates(["cat <<'TS'", 'files = root.glob("*.py")', 'TS', 'echo done'].join('\n'))
  );
  check(
    'CONTROL: the same call OUTSIDE a heredoc still counts',
    enumerates(["cat <<'TS'", 'x', 'TS', 'files = root.glob("*.py")'].join('\n'))
  );
  check(
    'CONTROL: an UNQUOTED heredoc is left alone, because the shell interpolates it',
    enumerates(['cat <<TS', 'files = root.glob("*.py")', 'TS'].join('\n'))
  );
  check(
    'CONTROL: reading ONE named config is not enumeration',
    !enumerates('data = json.load(open(".ci/config/thing.json"))')
  );

  check('a MIN_ floor is a guard', hasVacuityGuard('MIN_MANIFESTS = 8'));
  check('the word VACUOUS is a guard', hasVacuityGuard('print("VACUOUS INPUT: ...")'));
  check(
    'CONTROL: a script with neither is a finding',
    findings(() => 'files = root.glob("*.py")\nprint("ok")', ['x/check-a.py']).length === 1
  );
  check(
    'CONTROL: the same script WITH a floor is not',
    findings(() => 'MIN_X = 3\nfiles = root.glob("*.py")', ['x/check-a.py']).length === 0
  );
  check(
    'CONTROL: a non-enumerating script is out of scope entirely',
    findings(() => 'print("hello")', ['x/check-a.py']).length === 0
  );
  return bad;
}

function main(argv: string[]): void {
  if (argv.includes('--selftest')) {
    const n = selftest();
    console.log(`${n === 0 ? '✓' : '✗'} enumeration-vacuity selftest: ${n} failure(s)`);
    process.exit(n === 0 ? 0 : 1);
  }

  console.log('enumeration vacuity: controls first, then the verdict');
  if (selftest() !== 0) {
    console.error('✗ instrument control failed; every verdict below would be meaningless');
    process.exit(2);
  }

  const files = tracked();
  // THIS GATE ENUMERATES TOO, so it obeys its own rule. Measured 2026-09-04: 67 enumerating
  // scripts out of a wider check/gate-test population. A floor well under that catches a
  // broken `git ls-files` without pinning the number to today's tree.
  const MIN_SUBJECTS = Number(process.env.ENUM_VACUITY_MIN ?? 40);
  if (files.length < MIN_SUBJECTS) {
    console.error(
      `✗ VACUOUS: git listed ${files.length} check/gate-test script(s), floor ${MIN_SUBJECTS}. ` +
        'The enumeration lost the corpus; refusing a verdict.'
    );
    process.exit(1);
  }

  const read = (f: string): string => readFileSync(path.join(ROOT, f), 'utf8');
  const current = findings(read, files).sort();

  if (argv.includes('--write-baseline')) {
    // The shared plumbing, not a fourth hand-rolled copy: check:ci-shape-duplication
    // refused this file the first time precisely because the read/verdict/refuse/write
    // sequence had reached three copies across the consumers.
    const ok = commitBaseline({
      path: BASELINE,
      label: path.relative(ROOT, BASELINE),
      noun: 'unguarded enumerating check',
      key: 'unguarded',
      note: 'shrink-only; see scripts/check-enumeration-vacuity.ts. Drain by adding a vacuity guard, never by reseeding.',
      current,
      firstSeed: argv.includes('--first-seed'),
      read: (f) => (existsSync(f) ? readFileSync(f, 'utf8') : null),
      write: (f, body) => writeFileSync(f, body),
    });
    process.exit(ok ? 0 : 1);
  }

  const baseline: string[] = existsSync(BASELINE)
    ? JSON.parse(readFileSync(BASELINE, 'utf8')).unguarded
    : [];
  const known = new Set(baseline);
  const added = current.filter((f) => !known.has(f));
  const fixed = baseline.filter((f) => !current.includes(f));

  if (added.length > 0) {
    console.error(`✗ ${added.length} enumerating check(s) with no vacuity guard:`);
    for (const f of added) console.error(`    ${f}`);
    // Printed line by line rather than as one concatenated block: the concat form is
    // an idiom two other gates already use, and a third copy is what
    // check:ci-shape-duplication refuses. Reading better is a bonus, not the reason.
    for (const line of [
      '',
      '  A check that scans a corpus and finds nothing prints a tick, and that tick is',
      '  indistinguishable from a clean tree. Add a named floor (MIN_*), or refuse',
      '  explicitly on an empty result and say VACUOUS in the message.',
      `  The backlog in ${path.relative(ROOT, BASELINE)} may only SHRINK; it is not a`,
      '  place to add a new one.',
    ]) {
      console.error(line);
    }
    process.exit(1);
  }

  console.log(
    `✓ enumeration vacuity: ${files.length} check/gate-test script(s) scanned, ` +
      `${current.length} enumerate without a guard (all baselined, ${fixed.length} drained ` +
      'since the last write)'
  );
  console.log(
    '  Blind spot: this proves a guard EXISTS, never that its floor is high enough. A floor ' +
      'of 1 passes here and still reports a clean tree for a corpus of one.'
  );
}

main(process.argv.slice(2));
