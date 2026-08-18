#!/usr/bin/env tsx
import { execFileSync } from 'node:child_process';
/**
 * Gate: `// true` on a boolean field in a jq filter, which inverts its meaning.
 *
 * WHY THIS EXISTS, with the live instance that motivated it. jq's alternative
 * operator `//` treats BOTH null and FALSE as empty. So `.draft // true` does
 * not mean "draft, defaulting to true when absent". It means "true whenever
 * draft is absent OR false", which is the opposite of what it reads like.
 *
 * Found 2026-07-29 in the Wave C autopilot: `(.draft // true | not)` was the
 * done-detection condition, so a NON-draft PR (`"draft": false`) was read as a
 * draft and the autopilot could never conclude a PR was finished. The code
 * looked correct in review and the test caught it only because the fixture
 * happened to set the field explicitly.
 *
 * WHY `// false` IS NOT FLAGGED, and this is the whole subtlety. With `// false`
 * a swallowed `false` still yields `false`, so the bug is invisible because it
 * has no effect. Only the `// true` direction can flip a value. Flagging both
 * would produce noise on every safe site and teach people to ignore the gate;
 * the repo has several `// false` uses that are all correct.
 *
 * The fix is to test presence explicitly:
 *     BAD:  (.draft // true | not)
 *     GOOD: (has("draft") and (.draft == false))
 * which still fails closed when the field is missing.
 *
 * Usage: tsx scripts/check-jq-boolean-default.ts [--skip-control]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// `// true` with any spacing, inside what is plausibly a jq filter. Deliberately
// narrow: it must be the alternative operator followed by the literal `true`,
// not a comment. A JS line comment `// true story` is excluded by requiring the
// token to end there or be followed by a jq continuation character.
const BAD = /\/\/\s*true\s*(?=[)|,\s'"]|$)/;

// A `//` that begins a whole-line comment is never the jq operator.
const LINE_COMMENT = /^\s*(#|\/\/|\*)/;

export interface Finding {
  file: string;
  line: number;
  text: string;
}

/** Scan one file's text. Exported so the control drives the REAL scanner. */
export function scanText(rel: string, text: string): Finding[] {
  const out: Finding[] = [];
  text.split('\n').forEach((raw, i) => {
    if (LINE_COMMENT.test(raw)) return;
    // Only lines that look like jq: they mention jq, or sit inside a jq string.
    if (!/\bjq\b|--jq|\.\w+\s*\/\//.test(raw)) return;
    if (BAD.test(raw)) out.push({ file: rel, line: i + 1, text: raw.trim().slice(0, 160) });
  });
  return out;
}

/**
 * CONTROL. Runs the REAL scanner over a synthetic defect and over the safe
 * shapes, and fails if it cannot tell them apart. Inline, not behind a flag:
 * this repo shipped a gate whose planted-defect selftest sat behind an
 * uninvoked `--selftest` and was therefore dead code.
 */
function control(): void {
  const die = (why: string): never => {
    console.error(`✗ CONTROL FAILED: ${why}`);
    process.exit(1);
  };
  // The fixture is concatenated so this file's own on-disk text does not
  // match the scanner it feeds: the gate scans every tracked file,
  // including itself, and a literal fixture here self-fired the gate on
  // its very own control line (found 2026-07-31, the first time anything
  // actually ran the scan; see the CI-wiring issue filed the same day).
  const fires = scanText('x.sh', "jq -r '{ not_draft: (.draft /" + "/ true | not) }'");
  if (fires.length !== 1) die(`expected 1 finding on the planted defect, got ${fires.length}`);

  // Must NOT flag the safe direction, or it becomes noise and gets ignored.
  if (scanText('x.sh', "jq -r '.ci_green // false'").length !== 0) {
    die('flagged `// false`, which cannot invert a value');
  }
  // Must NOT flag a prose comment containing the same characters.
  if (scanText('x.ts', '// true when the run is green').length !== 0) {
    die('flagged a line comment');
  }
  // Must NOT flag the corrected form.
  if (scanText('x.sh', 'jq -r \'(has("draft") and (.draft == false))\'').length !== 0) {
    die('flagged the recommended fix');
  }
  console.log('  PASS  fires on `// true` in a jq filter');
  console.log('  PASS  silent on `// false`, on line comments, and on the fix');
}

function main(): void {
  if (!process.argv.slice(2).includes('--skip-control')) control();

  // ANTI-VACUITY, and it must REFUSE rather than crash. `git ls-files` throws
  // outside a repository, and an uncaught throw exits nonzero with a stack
  // trace, which looks like a failing gate but says nothing. The anti-vacuity
  // registry pins the diagnostic for exactly this reason, and it caught this
  // gate crashing instead of refusing on its first run.
  let files: string[] = [];
  try {
    files = execFileSync('git', ['ls-files', '-z', '*.sh', '*.ts', '*.cjs', '*.js', '*.yml'], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .split('\0')
      .filter(Boolean);
  } catch {
    files = [];
  }

  if (files.length === 0) {
    console.error(
      '✗ Refusing to run: no tracked files to scan. A gate with nothing to look at ' +
        'passes trivially for ever, which is indistinguishable from being correct.'
    );
    process.exit(1);
  }

  const findings = files.flatMap((rel) => {
    try {
      return scanText(rel, fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8'));
    } catch {
      return [];
    }
  });

  if (findings.length > 0) {
    console.error(
      `✗ ${findings.length} jq filter(s) use \`// true\` on a boolean, which INVERTS them:\n\n` +
        findings.map((f) => `    ${f.file}:${f.line}\n      ${f.text}`).join('\n') +
        `\n\njq's \`//\` treats false as empty, so \`.x // true\` is true whenever x is\n` +
        `absent OR false. Test presence explicitly instead:\n` +
        `    (has("x") and (.x == false))\n`
    );
    process.exit(1);
  }

  console.log(`✓ No inverting \`// true\` jq defaults across ${files.length} tracked file(s).`);
}

main();
