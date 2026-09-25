#!/usr/bin/env tsx
/**
 * No source file may quietly grow past the line-count budget eslint's
 * `max-lines` rule enforces today (`eslint.config/typescript.js:184`, `max:
 * 512, skipBlankLines: true, skipComments: true`) -- this is the Phase 1 "S"
 * (scripts/gates) replacement the biome-only-lint plan's Rule map names for
 * that row, one of the four rules Biome cannot express because
 * `noExcessiveLinesPerFile` has no `skipComments` option (PLAN-biome-only-lint.md
 * Finding 5).
 *
 * WHY OXC AND NOT A REGEX ON `//`/`/* `. A regex over raw text cannot tell a
 * `//` inside a string or template literal from a real comment, and cannot
 * find the end of a block comment that itself contains the two characters
 * `* /` split by other text. oxc-parser already parses the file into an AST
 * for its own purposes elsewhere in this repo's tooling (Rule map, Finding 4)
 * and hands back every comment's exact `[start, end)` character offsets
 * (UTF-16 code-unit offsets, the same units a JS string index already uses --
 * confirmed empirically against a source string containing a combining
 * accent and an astral emoji before writing this). Removing exactly those
 * ranges from each line and checking what is left is then a plain string
 * operation, no hand-rolled nesting tracker required.
 *
 * THE COUNTING RULE, reduced from eslint's actual implementation
 * (`node_modules/eslint/lib/rules/max-lines.js`, read for this file). eslint
 * runs two independent filters in sequence: drop lines whose trimmed text is
 * empty (`skipBlankLines`), then drop any line a comment covers ENTIRELY --
 * a comment sharing a line with real code on either side does not remove
 * that line, only a comment's interior lines and a comment's own line when
 * nothing but the comment sits on it. Both filters collapse to one
 * predicate: a line counts if, after blanking out every character any
 * comment's range covers, something other than whitespace remains. Traced
 * through eslint's four cases by hand (code-then-comment, comment-then-code,
 * a lone comment line, and a multi-line block comment with code on its first
 * and last lines) and each produces the same verdict as this reduction --
 * see the "REDUCTION, VERIFIED" cases in the self-test below, which are
 * exactly those four.
 *
 * ONE DELIBERATE GAP: line splitting here recognizes `\r\n`, `\r` and `\n`
 * only. eslint's own line splitter additionally treats U+2028/U+2029 (the
 * ECMAScript line/paragraph separators) as breaks, but no file in this repo's
 * scanned scope contains one -- `check:ci-control-in-string`'s own AST walk
 * would have a much stranger time of it long before this gate did -- so the
 * gap is named rather than chased.
 *
 * SCOPE PARITY. This does not re-derive eslint's config resolution; it
 * carries forward, as data, the exact set the Rule map's `max-lines` row
 * names: the roots `check:lint`'s four shards actually pass (not the wider
 * `packages/json` swept only by the developer-convenience `lint` script --
 * see `.ci/scripts/quality/check_lint_scope_coverage.py`'s `ROOT_UNMEASURABLE`
 * and its sibling comment on `LINT_CI_SCRIPT`), eslint's global ignores
 * restricted to the extensions this rule ever sees, and the four config
 * blocks and two file-level directives the Rule map's `max-lines` row cites
 * (`tooling.js:37-44`, `i18n.js:370-378`, `tests.js:50`, `packages.js:22-52`,
 * `license.ts:1`, `local-executor.ts:1`). Measured parity: `npx eslint` over
 * the same four shards, filtered to `ruleId === "max-lines"`, returns zero
 * findings across 2793 linted files on this HEAD; this gate returns zero
 * findings over its own scope on the same HEAD. See the plan for the exact
 * commands.
 *
 * ---- gate ----
 * step: No source file exceeds the line-count budget
 * needs: none
 * selftest: true
 * lane: quality-code
 * why: A file that quietly crosses 512 non-blank, non-comment lines is a
 *      sign the module is doing more than one job; eslint's `max-lines` rule
 *      caught this until the biome-only-lint cut, and Biome's own line-count
 *      rule cannot reproduce `skipComments` (see the file banner).
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';
import { parseSync } from 'oxc-parser';
import { GREEN, RED, NC } from '../lib/console.js';
import { reportFindings } from '../lib/findings-report.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

export const MAX_LINES = 512;

// The roots `check:lint`'s four CI shards actually pass, unioned (package.json:322-325). Deliberately narrower than the `lint`/`fix:lint` developer scripts, which also sweep `packages/json` -- data templates that have never been under any eslint root, per `check_lint_scope_coverage.py`'s `ESLINT_EXEMPT["packages/json/"]`.
const LINT_ROOTS = [
  'packages/cli',
  'packages/www',
  'packages/provisioning',
  'workers',
  'packages/shared',
  'packages/locales',
  'packages/e2e-tests',
  'scripts',
  'eslint-rules',
  '.ci',
  '.github/actions',
  'private/account',
];

const EXTENSIONS = ['js', 'jsx', 'ts', 'tsx'];

// eslint's global ignores (`eslint.config/ignores.js:13-64`), kept to the entries that could ever match one of the extensions above -- the JSON/CSS-only entries there (translation hash sidecars, search-index bundles) are omitted because no glob below can match one anyway. Directory-shaped source patterns are broadened to `**/` (e.g. `bin/` -> `**/bin/**`): eslint's own ignore matcher already treats those recursively (there is no top-level-only `bin/` elsewhere in the tree to lose), so widening them cannot drop a file eslint still lints. The three `*.config.{js,ts,cjs}` entries are the opposite case and are kept EXACTLY as eslint wrote them, with no `**/` prefix: eslint's flat-config `ignores` matches a slash-free pattern only at the root (minimatch, one path segment), so `*.config.ts` ignores root-level configs like `vite.config.ts` but leaves nested ones -- `packages/cli/vitest.config.ts`, `packages/shared/vitest.config.ts`, `packages/www/vitest.config.ts`, `workers/www/vitest.config.ts` -- linted. A `**/*.config.ts` here previously widened past that and silently dropped those 4 files from scope (measured: 653 scanned vs. eslint's 659-file max-lines-enabled set from phase0-config-snapshot.jsonl). Widening a FILE pattern is not "the safe direction" the way widening a directory pattern is: it shrinks this gate's scope below eslint's rather than growing it, which is exactly backwards for a "zero findings on HEAD" parity claim -- a file eslint still enforces max-lines on could cross the budget with this gate silent.
const GLOBAL_IGNORE = [
  '**/dist/**',
  '**/dist-typecheck/**',
  '**/node_modules/**',
  '**/bin/**',
  '**/*.tmp/**',
  '.ci/cache/**',
  '**/*.d.ts',
  'packages/*/src/**/*.js',
  'packages/*/tests/**/*.js',
  'packages/www/public/**',
  'packages/e2e-tests/reports/**',
  'private/account/dist/**',
  'private/account/web/dist/**',
  'private/account/e2e/**',
  'workers/account/dist/**',
  'packages/www/.astro/**',
  'packages/cli/templates/**',
  '*.config.js',
  '*.config.ts',
  '*.config.cjs',
];

// The `max-lines` row of the Rule map (PLAN-biome-only-lint.md), as data: every place eslint's config turns `max-lines` off, or excludes a file from the rule-bearing block entirely, or silences it with a file-level directive. Each pattern below is commented with the config site it carries forward.
const MAX_LINES_EXEMPT = [
  // typescript.js:84-85 -- the ONE block that ever sets `max-lines` to "error" is scoped to `**/*.{js,jsx,ts,tsx}` with `ignores: ['scripts/**/*.ts']`. Root `scripts/` was never in the rule's `files` match, so this is a base-scope exclusion, not an override.
  'scripts/**/*.ts',
  // tests.js:17-23,50 -- every test-file convention in the repo turns `max-lines` off outright.
  'packages/e2e-tests/**/*.ts',
  'packages/shared/src/**/__tests__/**/*.ts',
  'packages/shared/src/**/__tests__/**/*.tsx',
  'packages/cli/src/**/__tests__/**/*.ts',
  // tooling.js:37-44 -- the three P4 command-layer files kept over budget on purpose until the command-tree freshness gate makes splitting them safe (see the block comment at that site).
  'packages/cli/src/config/command-metadata.ts',
  'packages/cli/src/commands/datastore.ts',
  'packages/cli/src/commands/machine/status.ts',
  // i18n.js:369-378 -- generated files nothing hand-edits.
  '**/*.generated.ts',
  '**/*.generated.tsx',
  '**/api-schema.zod.ts',
  '**/renet-contract/data/*.schema.ts',
  // packages.js:22-52 -- the account package's general rules (this one included) are off in eslint; Biome is account's linter for everything but the three i18n rules eslint still carries there.
  'private/account/**/*.ts',
  'private/account/**/*.tsx',
  // Rule map, max-lines row: the two files whose own first line silences eslint's max-lines specifically for that file (license.ts:1, local-executor.ts:1). Left exactly as they are -- removing a per-file silencing comment is a later, differently-owned Phase 1 box, not this one.
  'packages/cli/src/services/account/license.ts',
  'packages/cli/src/services/executor/local-executor.ts',
  // tooling.js:46-51 -- a dedicated BLOCKER block turns `max-lines` off for this one file: it is the host-side scope analyzer standing in for `@typescript-eslint/no-unused-vars` during the Biome cutover, and it is deleted at the same cutover that deletes eslint.config itself, so its size is not worth enforcing against. Found live on this HEAD (587 code lines): `npx eslint eslint-rules/no-unused-underscore-var.js --max-warnings 0` exits 0 with `max-lines` resolving to `off` there (`calculateConfigForFile`), while this gate initially had no matching entry and turned red on it -- a real scope-parity gap, not a hypothetical one.
  'eslint-rules/no-unused-underscore-var.js',
];

export interface Finding {
  file: string;
  lines: number;
}

/**
 * Every character offset a comment covers, as a sorted, non-overlapping list of `[start, end)` ranges. oxc-parser's comments already arrive sorted and non-overlapping (comments cannot nest), so this is just the pass-through shape the line scanner wants.
 */
function commentRanges(source: string, filename: string): [number, number][] {
  const { comments } = parseSync(filename, source);
  return comments.map((c) => [c.start, c.end] as [number, number]);
}

/**
 * The eslint `max-lines` count for one file's text: lines that are neither blank nor entirely comment, reduced to one predicate as the file banner derives. `ranges` must be sorted by `start`.
 */
export function countCodeLines(source: string, ranges: [number, number][]): number {
  const rawLines = source.split(/\r\n|\r|\n/);
  // eslint drops a trailing synthetic empty line produced by a final linebreak before it ever filters (max-lines.js:144-149). Doing the same here is a no-op given skipBlankLines is always true in this repo's config, since that empty string is filtered out either way -- kept for the reader tracing this against eslint's source line by line.
  if (rawLines.length > 1 && rawLines.at(-1) === '') rawLines.pop();

  let offset = 0;
  let r = 0; // pointer into `ranges`, which only ever advances
  let count = 0;

  for (const line of rawLines) {
    const lineStart = offset;
    const lineEnd = offset + line.length;
    offset = lineEnd + 1; // +1 for the stripped line-break character

    // Advance past any comment that ended before this line starts.
    while (r < ranges.length && ranges[r][1] <= lineStart) r++;

    let visible = line;
    // Blank out every comment range overlapping this line, working through ranges in order (a line can hold more than one comment: code, a comment, more code, another comment). Indices are local to `visible`/`line`, which share length and offsets throughout since blanking never changes string length.
    for (let i = r; i < ranges.length && ranges[i][0] < lineEnd; i++) {
      const start = Math.max(ranges[i][0], lineStart) - lineStart;
      const end = Math.min(ranges[i][1], lineEnd) - lineStart;
      if (start < end) {
        visible = visible.slice(0, start) + ' '.repeat(end - start) + visible.slice(end);
      }
    }

    if (visible.trim() !== '') count++;
  }

  return count;
}

/** `countCodeLines`, from a file's own text and name. */
export function countFile(source: string, filename: string): number {
  return countCodeLines(source, commentRanges(source, filename));
}

function toPosix(p: string): string {
  return p.split(path.sep).join('/');
}

/**
 * Every file this gate's scope reaches, relative to the repo root, POSIX-separated, deduplicated and sorted -- the file-discovery half of scope parity with eslint's `max-lines` (see the file banner).
 */
export function scanScope(): string[] {
  const found = new Set<string>();
  for (const root of LINT_ROOTS) {
    if (!fs.existsSync(path.join(REPO_ROOT, root))) continue;
    // Globbed from REPO_ROOT, not from `root` itself, so every GLOBAL_IGNORE
    // entry means the same repo-root-relative path it names in
    // eslint.config/ignores.js -- a per-root `cwd` would silently turn
    // `.ci/cache/**` into `cache/**` while scanning the `.ci` root, which is
    // exactly the bug this comment is here to stop from coming back.
    const pattern = `${root}/**/*.{${EXTENSIONS.join(',')}}`;
    for (const f of globSync(pattern, {
      cwd: REPO_ROOT,
      ignore: GLOBAL_IGNORE,
      nodir: true,
      dot: false,
    })) {
      found.add(toPosix(f));
    }
  }
  const exempt = new Set<string>();
  for (const pat of MAX_LINES_EXEMPT) {
    for (const f of globSync(pat, { cwd: REPO_ROOT, nodir: true, dot: false })) {
      exempt.add(toPosix(f));
    }
  }
  return [...found].filter((f) => !exempt.has(f)).sort();
}

/** One file's finding, or `undefined` if it is within budget. */
export function checkFile(relPath: string): Finding | undefined {
  const abs = path.join(REPO_ROOT, relPath);
  const source = fs.readFileSync(abs, 'utf-8');
  const lines = countFile(source, relPath);
  return lines > MAX_LINES ? { file: relPath, lines } : undefined;
}

// A floor below which "zero findings" is indistinguishable from "the scope walk is broken" -- the same shape of control `check-control-in-string.ts` uses for the same reason (`MIN_SUBJECTS`). This gate's scope is much narrower than eslint's 2793-file `max-lines` universe: `private/account` (819 files), root `scripts/**/*.ts` (182) and every test directory are all exempt by design (see MAX_LINES_EXEMPT), which is most of what eslint's four shards lint. `scanScope()` measured 653 files on the HEAD this gate was written against; the floor sits well under that so a real, smaller-but-still-substantial future scope does not need to keep chasing this number, while an empty or near-empty glob still trips it.
const MIN_SUBJECTS = 500;

function selftest(): boolean {
  let bad = 0;
  const check = (label: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${label}`);
    else {
      console.error(`  FAIL  ${label}${detail ? `\n        ${detail}` : ''}`);
      bad++;
    }
  };

  const countText = (source: string, filename = 'x.ts') => countFile(source, filename);

  // A file at exactly the cap is clean; one line over is not. This is the control the plan calls for: "a planted 513-code-line file turns it red, reverted green".
  const atCap = Array.from({ length: MAX_LINES }, (_, i) => `const line${i} = ${i};`).join('\n');
  check('exactly 512 code lines is clean', countText(atCap) === MAX_LINES);
  check('...and does not exceed the cap', countText(atCap) <= MAX_LINES);

  const overCap = Array.from({ length: MAX_LINES + 1 }, (_, i) => `const line${i} = ${i};`).join(
    '\n'
  );
  check('513 code lines exceeds the cap', countText(overCap) === MAX_LINES + 1);
  check('...and is reported as such', countText(overCap) > MAX_LINES);

  const reverted = overCap.split('\n').slice(0, MAX_LINES).join('\n');
  check('reverting the 513th line back to 512 is clean again', countText(reverted) === MAX_LINES);

  // skipBlankLines: interleaved blank lines are never counted, however many there are.
  const withBlanks = Array.from({ length: MAX_LINES }, (_, i) => `const l${i} = ${i};\n`).join(
    '\n'
  );
  check(
    'blank lines between code lines are not counted',
    countText(withBlanks) === MAX_LINES,
    `got ${countText(withBlanks)}`
  );

  // REDUCTION, VERIFIED: the four cases eslint's own getLinesWithoutCode branches on (file banner), each checked against the exact count eslint's algorithm would produce by hand-tracing max-lines.js.
  check(
    'code then a trailing comment counts as one code line',
    countText('const x = 1; // trailing\nconst y = 2;') === 2
  );
  check(
    'a comment then code on the same line counts as one code line',
    countText('/* leading */ const x = 1;\nconst y = 2;') === 2
  );
  check(
    'a comment alone on its line is not counted',
    countText('const x = 1;\n// alone\nconst y = 2;') === 2
  );
  check(
    'a multi-line block comment with code on its first and last line counts only those two',
    countText('const x = 1; /* start\nmiddle\nend */ const y = 2;\nconst z = 3;') === 3
  );

  // A comment containing multi-byte characters must not desynchronize the offsets that follow it (file banner: oxc-parser's offsets are UTF-16 code-unit offsets, verified empirically before relying on it here).
  check(
    'a comment holding multi-byte characters does not corrupt later line counts',
    countText('// café 😀 done\nconst after = 1;\nconst also = 2;') === 2
  );

  // A file entirely made of comments and blank lines, however long, is clean: this is what distinguishes the gate from a raw `wc -l` cap.
  const allComments = Array.from({ length: MAX_LINES + 200 }, (_, i) => `// comment ${i}`).join(
    '\n\n'
  );
  check(
    'a file of nothing but comments and blank lines, well past the raw line count, is clean',
    countText(allComments) === 0,
    `got ${countText(allComments)}`
  );

  // A .tsx fixture, since JSX syntax is part of this gate's scope.
  const tsx = Array.from(
    { length: MAX_LINES + 1 },
    (_, i) => `const c${i} = () => <div>{${i}}</div>;`
  ).join('\n');
  check('the cap applies identically to .tsx sources', countText(tsx, 'x.tsx') === MAX_LINES + 1);

  // Scope: the two live per-file silenced files, and one of the generated files, must be exempt end to end, not merely present in the static pattern list -- this walks the real repo tree.
  const scope = new Set(scanScope());
  check(
    'license.ts (its own max-lines silencing comment) is exempt from the scan',
    !scope.has('packages/cli/src/services/account/license.ts')
  );
  check(
    'local-executor.ts (its own max-lines silencing comment) is exempt from the scan',
    !scope.has('packages/cli/src/services/executor/local-executor.ts')
  );
  check(
    'a generated renet-contract file is exempt from the scan',
    !scope.has('packages/shared/src/renet-contract/data/functions.generated.ts')
  );
  check(
    'root scripts/*.ts is out of scope entirely',
    !scope.has('scripts/gates/check-max-lines.ts')
  );
  check(
    'private/account sources are out of scope for max-lines',
    ![...scope].some((f) => f.startsWith('private/account/'))
  );
  check(
    `scope clears the ${MIN_SUBJECTS}-file floor (a real walk, not an empty glob)`,
    scope.size >= MIN_SUBJECTS,
    `got ${scope.size}`
  );

  // A real, currently-in-scope, comment-heavy file that sits well over 512 RAW lines (765) but under 512 CODE lines -- this is the case a plain `wc -l` cap would get wrong, which is why the eslint rule, and this gate, count comments and blanks out first.
  const certCache = 'packages/cli/src/services/account/cert-cache.ts';
  if (scope.has(certCache)) {
    const finding = checkFile(certCache);
    check(
      `${certCache} (765 raw lines, heavily commented) is clean under the code-line count`,
      finding === undefined,
      finding ? JSON.stringify(finding) : ''
    );
  } else {
    check(`${certCache} is in the scanned scope`, false, 'selftest fixture assumption changed');
  }

  if (bad > 0) {
    console.error(`\n${RED}✗ ${bad} self-test failure(s)${NC}`);
    return false;
  }
  console.log(`${GREEN}✓ max-lines detector: self-test passed${NC}`);
  return true;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest() ? 0 : 1;
  if (!selftest()) {
    console.error(`${RED}✗ CONTROL FAILED: refusing to report on the tree.${NC}`);
    return 1;
  }

  const files = scanScope();
  if (files.length < MIN_SUBJECTS) {
    console.error(
      `${RED}✗ Refusing to run: only ${files.length} file(s) in scope, below the floor of ` +
        `${MIN_SUBJECTS}. Zero findings over an empty glob reads exactly like a clean tree.${NC}`
    );
    return 1;
  }

  const findings: Finding[] = [];
  for (const f of files) {
    const finding = checkFile(f);
    if (finding) findings.push(finding);
  }

  if (findings.length > 0) {
    return reportFindings({
      header: `${RED}✗ ${findings.length} file(s) exceed the ${MAX_LINES}-line budget (blank and comment lines excluded):${NC}`,
      items: findings,
      limit: 30,
      format: (f) => `${f.file}  (${f.lines} lines)`,
      remedy: [
        '  Split the file, or add it to MAX_LINES_EXEMPT in scripts/gates/check-max-lines.ts with the',
        '  same kind of reason the existing entries carry -- never a bare bypass.',
      ],
    });
  }

  console.log(`${GREEN}✓ ${files.length} file(s): none exceed the ${MAX_LINES}-line budget${NC}`);
  return 0;
}

// Guarded so a caller can `import { checkFile, scanScope, countFile }` (the
// planted-fixture control under `.ci/cache/biome-parity/maxlines/` does
// exactly this) without also running the whole gate as a side effect of the
// import.
if (import.meta.url === `file://${process.argv[1]}`) {
  process.exit(main(process.argv.slice(2)));
}
