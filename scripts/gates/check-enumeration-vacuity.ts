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
 * Usage: npx tsx scripts/gates/check-enumeration-vacuity.ts [--write-baseline] [--selftest]
 *
 * ---- gate ----
 * step: Enumeration vacuity
 * needs: node
 * why: A gate that scans and finds nothing prints a tick indistinguishable from a
 *      clean tree. Seeded shrink-only: 47 enumerating checks carry no vacuity guard
 *      today, and a wall of 47 is a gate somebody disables.
 * ---- end gate ----
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

import { commitBaseline } from '../lib/shrink-only-baseline.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const BASELINE = path.join(ROOT, 'scripts/data/enumeration-vacuity-baseline.json');

/**
 * Scripts this gate judges: EVERY tracked script under the two roots, any language.
 *
 * This was `/\/(check|test)[-_][\w-]+\.(py|sh|ts)$/` -- a NAMING heuristic standing in
 * for a role, and scripts/gate-bind.ts carries a note about removing the identical
 * pattern for the identical reason. Measured 2026-09-04: it hid 234 of the 610 tracked
 * scripts under `.ci/scripts` and `scripts`; 21 of those enumerate and 16 carried no
 * vacuity guard, while this gate printed "376 scanned ... all baselined".
 *
 * The sharpest case was this file's own WHY block, which cites
 * `retire-shadowed-secrets.py` as a script that went blind and reported "already
 * retired?". It is named `retire-`, so the pattern could not see the example the gate
 * was written from. It has a MIN_WORKFLOWS floor now.
 *
 * All 16 were guarded before this widened, so the baseline did NOT grow -- which
 * matters, because the shrink-only module refuses a reseed that absorbs findings, and
 * it refused this one when it was tried the other way round. Of the 16, five already
 * refused an empty result and only lacked the vocabulary to say so (autopilot-push.sh,
 * update-homebrew-tap.sh, validate-stage-artifacts.sh, collect-drill-diagnostics.sh --
 * whose zero is deliberately non-fatal in an `if: always()` step -- and the per-name
 * check in the tap script); eleven got a real floor.
 *
 * A vacuity guard is owed by anything that ENUMERATES, which is a property of the code
 * and not of its filename. `enumerates()` already decides that; the corpus must not
 * second-guess it.
 */
const SUBJECT_RE = /\.(py|sh|ts)$/;

/**
 * Does this source ENUMERATE a corpus? Deliberately narrow: a script that reads one named
 * config file has no enumeration to be empty, and demanding a floor of it would be noise.
 */
export const enumerates = (src: string): boolean =>
  ENUMERATION_RE.test(stripComments(stripHeredocs(src)));

/**
 * THE ARGV-ARRAY ALTERNATIVE IS THE ONE THAT WAS MISSING, and its absence made this
 * gate blind to every TypeScript enumerator in the repository, ITSELF INCLUDED.
 *
 * `git\s+ls-files` wants whitespace between the two words. TypeScript does not write it
 * that way: `execFileSync('git', ['-C', ROOT, 'ls-files', ...])` puts a comma, a quote
 * and often other argv elements between them. Measured 2026-09-06: 19 tracked scripts
 * enumerate in a form the old predicate could not see, six of them with no guard at all,
 * and this file, gate-bind.ts and check-dead-bash.ts were three of the nineteen. This
 * file's own floor block opened "THIS GATE ENUMERATES TOO, so it obeys its own rule",
 * which was false in the only sense that could be checked.
 *
 * The added branch matches `'ls-files'` as a QUOTED ARGV ELEMENT: quote, the literal,
 * quote, then a comma or a closing bracket. That is narrow on purpose. Matching a bare
 * `ls-files` anywhere would fire on this very comment, and matching `'git'` alone would
 * fire on every `git rev-parse` in the tree, neither of which enumerates anything.
 */
const ENUMERATION_RE =
  /git\s+ls-files|['"`]ls-files['"`]\s*[,\]]|\.glob\(|\.rglob\(|globSync\(|readdirSync\(|find\s+\S+\s+-(name|type)\b/;

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
 * A COMMENT IS PROSE, NOT CODE, and this gate's own header already said so about
 * heredocs while reading comments as source anyway.
 *
 * Caught 2026-09-06 on `.ci/scripts/quality/check_regions_sync.py`, a 33-line import shim
 * that enumerates nothing. Its docstring EXPLAINS that `scripts/gate-bind.ts` enumerates
 * its subjects with `git ls-files`, and the mention was read as the act. The file was
 * then owed a floor it has no corpus for, and the only way to satisfy that demand would
 * have been to write a floor over nothing, which is the vacuity this gate exists to
 * refuse. A gate that can be satisfied by a lie is worse than one that misses a case.
 *
 * DELIBERATELY CONSERVATIVE, in the direction that keeps findings rather than drops them:
 *
 *   - a `#` comment is stripped only when it OPENS the line, so `cmd # note` keeps its
 *     code and a `#` inside a quoted string is never touched. The observed class is a
 *     whole-line comment or a docstring, and reaching further would risk blinding the
 *     scan to a real call.
 *   - Python triple-quoted blocks go entirely: a module docstring is the single most
 *     likely place for a file to DESCRIBE an enumeration it does not perform.
 *   - `//` is stripped only at line start, and block comments wholly, for the same reason.
 *
 * The opposite bug, silently exempting a file whose only `git ls-files` sat behind a `#`,
 * is covered by the controls: a real call on a code line is still found.
 */
export const stripComments = (src: string): string => {
  const TRIPLE_D = new RegExp('"'.repeat(3) + '[\\s\\S]*?' + '"'.repeat(3), 'g');
  const TRIPLE_S = new RegExp("'".repeat(3) + '[\\s\\S]*?' + "'".repeat(3), 'g');
  const noBlocks = src
    .replace(TRIPLE_D, '')
    .replace(TRIPLE_S, '')
    .replace(/\/\*[\s\S]*?\*\//g, '');
  return noBlocks
    .split('\n')
    .filter((line) => !/^\s*(#|\/\/|\*)/.test(line))
    .join('\n');
};

/**
 * Does it carry a vacuity guard? Any of the three shapes this repo already uses, because
 * the point is that SOMETHING refuses an empty corpus, not that it is spelled one way.
 */
export const hasVacuityGuard = (src: string): boolean =>
  /\bMIN_[A-Z][A-Z0-9_]*\b/.test(src) ||
  /VACUOUS|vacuous/.test(src) ||
  /\bfloor\b/.test(src) ||
  // `refuseIfEmpty` from scripts/lib/controls.ts. Added 2026-09-06 with the six conversions it exists for. This is a NARROWING of trust rather than a widening: the helper's only behaviour is to refuse an empty corpus, so a call to it cannot be a guard that does nothing, which is more than the three patterns above can promise. `MIN_X` satisfies the first line whether or not
  // anything compares it, and this file's own output says so under "Blind spot".
  /\brefuseIfEmpty\s*\(/.test(src) ||
  // An explicit empty-corpus refusal written in the repo's older words. Anchored on "Refusing to run" plus "to scan" so a stray "refusing" in prose cannot satisfy it.
  /Refusing to run:[^\n]*to scan/.test(src) ||
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
    'a script the OLD name pattern hid is in scope: role is code, not filename',
    SUBJECT_RE.test('.ci/scripts/housekeeping/retire-shadowed-secrets.py') &&
      SUBJECT_RE.test('.ci/scripts/security/shfmt.sh')
  );
  check(
    'CONTROL: a conventionally-named gate is still in scope',
    SUBJECT_RE.test('.ci/scripts/quality/check_environment_names.py')
  );
  check(
    'CONTROL: a non-script is still out of scope',
    !SUBJECT_RE.test('.ci/config/thing.json') && !SUBJECT_RE.test('docs/x.md')
  );
  check(
    'CONTROL: reading ONE named config is not enumeration',
    !enumerates('data = json.load(open(".ci/config/thing.json"))')
  );

  // THE ARGV-ARRAY CONTROLS. The first is the shape that was invisible; the second and
  // third are what stop the widening from becoming a match-anything rule.
  check(
    'the argv-array form of git ls-files is an enumeration',
    enumerates("execFileSync('git', ['-C', ROOT, 'ls-files', 'scripts'])")
  );
  check(
    'CONTROL: a bare mention of ls-files in prose is NOT, so this file does not flag itself',
    !enumerates('// we should also handle ls-files one day\nconst x = 1;\n')
  );
  check(
    'CONTROL: another git subcommand in argv form is not an enumeration',
    !enumerates("execFileSync('git', ['rev-parse', 'HEAD'])")
  );
  // THE CLAIM THAT WAS FALSE, now checked on the line that carries it rather than on the whole file. Feeding this file's entire source to `enumerates` does NOT work, and the reason is worth keeping: `stripComments` removes `/* ... */` blocks, and this file's source contains the literal regex `/\/\*[\s\S]*?\*\//g` inside that very
  // function, so a self-scan opens a block comment at that regex and swallows the code
  // after it. That is the "a quoted body is data, not code" class this gate already knows, arriving from the other direction: here a piece of CODE reads as the opening of a comment. It is harmless against the real corpus, where `/*` inside a string literal is rare and only ever HIDES an enumeration from a gate that would then report it as guardless rather than as absent, but it is
  // a real edge and it belongs written down instead of discovered again.
  check(
    'THE CLAIM THAT WAS FALSE: this gate enumerates in the form it could not see',
    enumerates(
      readFileSync(new URL(import.meta.url), 'utf8')
        .split('\n')
        .filter((l) => l.includes('ls-files'))
        .join('\n')
    )
  );
  check(
    'refuseIfEmpty counts as a guard, because refusing is all it does',
    hasVacuityGuard('return refuseIfEmpty(files, "tracked .sh", "hint");')
  );
  check(
    'CONTROL: the word refuse alone does NOT satisfy the guard test',
    !hasVacuityGuard('// this gate refuses a bad pin\nconst x = 1;\n')
  );
  check(
    'an explicit empty-corpus refusal in the older words counts',
    hasVacuityGuard("console.error('Refusing to run: no tracked files to scan.');")
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
  // THE COMMENT CONTROLS, and the second is the one that matters. Stripping prose can
  // only be safe if a real call on a code line is still found; a strip that swallowed
  // both would make this gate quieter and blinder at the same time.
  const Q3 = '"'.repeat(3);
  check(
    'a `git ls-files` named only in a PYTHON DOCSTRING is prose, not an enumeration',
    findings(
      () => `x = 1\n${Q3}gate-bind enumerates with git ls-files.${Q3}\ny = 2\n`,
      ['x/check-a.py']
    ).length === 0
  );
  check(
    'CONTROL: the same call on a CODE line is still found',
    findings(() => 'out = run("git ls-files")\n', ['x/check-a.py']).length === 1
  );
  check(
    'a whole-line `#` comment naming .glob( is prose',
    findings(() => '# files = root.glob("*.py") would enumerate\nx = 1\n', ['x/check-a.py'])
      .length === 0
  );
  check(
    'CONTROL: a TRAILING `#` does NOT blind the scan -- the code before it still counts',
    findings(() => 'files = root.glob("*.py")  # note\n', ['x/check-a.py']).length === 1
  );
  check(
    'a `//` line comment in TypeScript is prose too',
    findings(() => '// we call globSync() elsewhere\nconst x = 1;\n', ['x/check-a.ts']).length === 0
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
  // THIS GATE ENUMERATES TOO, so it obeys its own rule -- BY HAND, not by its own detector, and the difference was measured on 2026-09-06 rather than assumed. Feed this file's own source to `enumerates()` and the answer is FALSE. The predicate wants `git\s+ls-files`, and every TypeScript enumerator in this repo writes the argv-array form instead: `execFileSync('git', ['-C', ROOT,
  // 'ls-files', ...])`, where
  // a comma stands between the two words. The floor below is real and wired; the claim
  // that the gate is inside its own scope was not.
  //
  // MEASURED BLIND SPOT: 19 tracked scripts enumerate in a form this predicate cannot see, and 6 of them carry no vacuity guard, so widening the regex adds 6 findings to a baseline that may only SHRINK. That makes the widening a CLUSTER (one regex plus six corpus-derived floors) rather than a one-line fix, and it is tracked as such.
  // Reproduce the count with the probe recorded in that item; do not re-derive it by
  // eye, because the narrow and wide sets differ by more than the unguarded six.
  //
  // Measured 2026-09-04: 67 enumerating scripts out of a wider check/gate-test population. A floor well under that catches a broken `git ls-files` without pinning the number to today's tree.
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
    // The shared plumbing, not a fourth hand-rolled copy: check:ci-shape-duplication refused this file the first time precisely because the read/verdict/refuse/write sequence had reached three copies across the consumers.
    const ok = commitBaseline({
      path: BASELINE,
      label: path.relative(ROOT, BASELINE),
      noun: 'unguarded enumerating check',
      key: 'unguarded',
      note: 'shrink-only; see scripts/gates/check-enumeration-vacuity.ts. Drain by adding a vacuity guard, never by reseeding.',
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
    // Printed line by line rather than as one concatenated block: the concat form is an idiom two other gates already use, and a third copy is what check:ci-shape-duplication refuses. Reading better is a bonus, not the reason.
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
  console.log(
    '  Nor that it is WIRED. A `MIN_X` that nothing compares refuses nothing and still ' +
      'satisfies the detector. A static check for that was written and DISCARDED on ' +
      '2026-09-04: it was wrong on all six it flagged -- names inside string literals and ' +
      'comments, an env var compared by a different script, and one floor wired ' +
      'indirectly (`needed = observed * MIN_HEADROOM`, and `needed` is what is compared). ' +
      'The eleven floors added that day were each confirmed wired by hand instead.'
  );
}

main(process.argv.slice(2));
