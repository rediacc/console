#!/usr/bin/env tsx
/**
 * The Nth copy of a shape is a finding. This counts them.
 *
 * THE QUESTION NOBODY ASKS. The stop-gate judge asks "did you sweep the class?" and "is
 * there a gate?". Neither asks "is this the third copy of something you already have?", so
 * every finding correctly answers "add a script + a manifest entry + a workflow step", and
 * nothing is ever pointed at the accumulated surface.
 *
 * This repo reached that conclusion twice by hand and wrote it down both times --
 * `scripts/lib/shrink-only-baseline.ts:25-31` ("a class, not an instance… seven chances to
 * drift") and `.claude/hooks/pre-bash/block-adhoc-sanctioned.sh:4-8` (a new class is "a row
 * rather than a 22nd copy of this file"). Both were noticed by a person.
 *
 * SEEDED, AND THAT IS THE WHOLE DESIGN -- decisively so, once it was measured. The plan
 * estimated ~9 pre-existing shapes past three copies, from the nine LARGEST spans a survey
 * had named. Run unseeded over the four families this gate scans, the real number is
 * **219 spans** (336 raw windows before coalescing), the biggest at 21 copies.
 *
 * A gate reporting 219 findings on its first run is not a gate, it is a wall, and it would
 * be 219 blocks of the "inexhaustible supply of hook-satisfying non-work" this repo already
 * has a scar from. So today's fingerprints are SEEDED into a baseline and stay silent; the
 * gate fires only when a shape that was NOT already here reaches its Nth copy.
 *
 * The 219 are a real and much larger backlog than the plan assumed, and that is worth
 * saying plainly rather than burying: draining them is its own measured piece of work, and
 * the number should decide how much of it is worth doing.
 *
 * The same trick is already in the tree: `wl_reggate.py:130` hashes every existing check
 * script at marker init "so only new ones count".
 *
 * WHAT IS DELIBERATELY NOT COUNTED, each forced by a measurement:
 *
 *   - COMMENTS. Family C (`block-*.sh`) is 52% comments, and those comments are the
 *     incident histories the guards exist for. Any raw-similarity metric ranks prose first
 *     and creates pressure to delete exactly the lines that make a green mean something.
 *   - THE FINDINGS REPORT. Measured across ten gates: ten distinct shapes. The sentence
 *     telling a reader what failed and why IS the gate's value. Duplication is counted in
 *     the scaffolding, never in the reasons.
 *   - ONE-LINERS. The repo-root resolution appears in 79 files with 18 spellings. At a
 *     window of 1 it drowns every real signal; the 5-line window excludes it by
 *     construction, and a fix there would be churn across 79 files for no drift risk.
 *   - IMPORT BLOCKS. Three files importing the same helper is ADOPTION, not duplication:
 *     an import statement IS the consolidation. This gate caught itself on this within an
 *     hour of landing -- moving five gates onto `lib/console.js` created a shared
 *     import preamble in three of them and the gate reported it, which would have
 *     discouraged exactly the consolidation it exists to encourage.
 *   - WRITTEN DECISIONS. `block-ci-polling.sh:19` says "NOT ROUTED THROUGH
 *     lib/command-scan.sh, and that is a decision". A counter that fires on a recorded
 *     decision is noise, so an opt-out marker excludes the file.
 *
 * DEVIATION FROM THE APPROVED PLAN, stated rather than buried. The plan said to normalise
 * identifiers to their kind. This does NOT: it strips comments and string literals and
 * collapses whitespace, and stops there. The measured clusters this gate is calibrated
 * against -- 8, 9 and 8 byte-identical instances -- were found WITHOUT identifier
 * normalisation, so shipping without it matches the evidence. Identifier normalisation is
 * strictly more aggressive and would need its own calibration before it could be trusted;
 * it can be added later behind the same seed.
 *
 * Usage:
 *   npx tsx scripts/gates/check-shape-duplication.ts [--selftest]
 *   npx tsx scripts/gates/check-shape-duplication.ts --seed    # rewrite the baseline
 *
 * ---- gate ----
 * step: Shape duplication
 * needs: node
 * selftest: true
 * ---- end gate ----
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readSync, renameSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { validateBlockerQuality } from '../lib/blocker-validator.js';
import { GREEN, NC, RED } from '../lib/console.js';
import { refuseIfEmpty, runControls } from '../lib/controls.js';

// THE ROOT IS A BINDING RATHER THAN A CONSTANT, and the probe is the reason. `--emit-index` bundles this same file into `probe.mjs`, and inside that bundle `import.meta.dirname` is the CACHE directory rather than `scripts/gates`, so a constant computed at module load would resolve the seed and every corpus read against a path that does not exist. The probe sets the root from its
// request and the gate sets it from `--root`; the default below is what a plain run has always used.
let ROOT = path.resolve(import.meta.dirname, '..', '..');
let SEED_FILE = path.join(ROOT, 'scripts/data/shape-duplication-seed.json');

function setRoot(root: string): void {
  ROOT = path.resolve(root);
  SEED_FILE = path.join(ROOT, 'scripts/data/shape-duplication-seed.json');
  // The tracked-path cache is keyed on nothing, so a root change has to drop it or the next resolution answers about the previous tree.
  TRACKED_CACHE = null;
}

/** The Nth copy. Justified from the measured distribution, not from tradition. */
export const N = 3;
/** Below 5 the 79-file one-liner dominates; above 8 two real spans vanish entirely. */
export const WINDOW = 5;
/** A file saying it deliberately stands apart is not a copy to collapse. */
const OPT_OUT = 'NOT ROUTED THROUGH';

// THE PYTHON HALF IS MISSING, MEASURED, AND DELIBERATELY NOT ADDED HERE YET. On 2026-09-08 `.ci/scripts/quality/` held 77 `check-*.sh` and 120 `check_*.py`, and 45 of those gates existed ONLY as Python -- no `.sh` twin left to catch their shape by proxy -- so a ported gate can be the third or twenty-first copy of a scaffold and this counter never sees it. Silent by construction,
// too: `refuseIfEmpty` in `tracked()` is satisfied forever by the ~150-file `scripts/gates/check-*.ts` family, so an empty `.ci` half never refuses.
//
// WIDENING IS A WAVE, NOT A LINE. Adding `.ci/scripts/quality/check_*.py` and `.ci/rediacc_ci/tests/gates/test_gate_*.py` was driven that day and the counter reported 62 NEW shapes at 3+ copies -- one of them 16 copies of the same five lines, across every ported gate, which is the shared `sys.path` hop and entry-point scaffold rather than 62 separate defects. Landing that red on a
// tree several sessions share, or seeding 62 hashes into the baseline in one go, are both worse than tracking it: the drain is the work, and the widening lands with it. A FAMILY CARRIES ITS OWN FLOOR, and per-family non-emptiness is not enough. Measured 2026-09-08: `.claude/hooks/pre-bash/block-*.sh` had fallen to ONE tracked file while `.claude/rediacc_hooks/guards/block_*.py`
// held 42, because W5 ported the guards and this list still named only the bash spelling. That family is the one the docstring above calls 52% comments carrying the incident histories the guards exist for, and the gate scanned 1 of 43 and printed a confident tick every run. `refuseIfEmpty` in `tracked()` could not see it: it guards the WHOLE corpus, which the ~150-file
// `scripts/gates/check-*.ts` family satisfies forever. One file is not empty and was still a dead family, so the floor is a COUNT.
//
// W7 P5 will delete the 77 `check-*.sh`, which is 6709 windows. With a floor on that family the deletion must update this table in the same change or go red; without one it leaves silently, exactly as family D did. THE QUALITY AND GATE-TEST PYTHON FAMILIES ARE NOT HERE YET, deliberately and with the cost measured. Adding `.ci/scripts/quality/check_*.py` and
// `.ci/rediacc_ci/tests/gates/test_gate_*.py` on 2026-09-08, once the coordinate fix made the corpus visible, reported 76 new shapes -- headed by a FORTY-FOUR copy span that is the shared `sys.path` hop every ported entry point carries. That is one scaffold to extract, not 76 defects, and extracting it before widening is what makes the widening land at about eleven rather than
// seventy-six. The sequence is written down in `agent/PLAN-extension-shaped-matchers.md`; this table gains those two rows in its commit 3, after the extraction.
interface Family {
  readonly pathspec: string;
  readonly floor: number;
}

const FAMILIES: readonly Family[] = [
  { pathspec: 'scripts/gates/check-*.ts', floor: 100 },
  { pathspec: '.ci/scripts/quality/check-*.sh', floor: 36 },
  { pathspec: '.ci/scripts/test/gates/test-*.sh', floor: 52 },
  // FLOOR 1 IS A SCAR, NOT A TARGET. This family held 43 guards; W5 ported 42 of them to `.claude/rediacc_hooks/guards/block_*.py` and one bash file remains, so the gate has been scanning 1 of 43. Adding the Python spelling on 2026-09-08 reported 26 new shapes -- the guards carry a shared scaffold of their own -- so the widening is an extraction job like the quality half above,
  // not a line, and it belongs in the same commit 3. What this row buys TODAY is that the number is written down where the next reader sees it, instead of being a silent 1.
  { pathspec: '.claude/hooks/pre-bash/block-*.sh', floor: 1 },
];

/** Exported for the index: the probe must scan the corpus this gate scans, and one list says so. */
export const FAMILY_PATHSPECS = FAMILIES.map((f) => f.pathspec);

/**
 * Which language's lexical rules a corpus path is read under.
 *
 * Factored out of `scan` because the probe normalises a STAGED file, which is bytes with no entry in `perFile`, and a second `endsWith` ladder there would be a second answer to one question -- the class this gate exists to count.
 */
export function kindFor(file: string): 'ts' | 'sh' | 'py' {
  return file.endsWith('.ts') ? 'ts' : file.endsWith('.py') ? 'py' : 'sh';
}

/** A file declaring it deliberately stands apart. Exported for the same reason as `kindFor`: the probe sees staged bytes, never the tracked file. */
export function isOptedOut(src: string): boolean {
  return src.includes(OPT_OUT);
}

/**
 * What a reader is asked to do about a finding, in one place.
 *
 * The gate prints it, and `--emit-index` copies it into the cached index so the pre-commit probe says the SAME words without transcribing them into a second language. An advisory that paraphrased the gate would be two answers to "what now", which is the shape of defect this file counts.
 */
export const ADVICE =
  '\n  Either extract the shared piece, or say which DIVERGENCE makes them not one' +
  '\n  thing (the way `run_gate()` has three incompatible return contracts).' +
  '\n  To accept one, put its FINGERPRINT (printed above, beside the copy count) into' +
  '\n  scripts/data/shape-duplication-seed.json under "accepted", with a BLOCKER: reason' +
  '\n  naming the divergence. The fingerprint used to be absent from this message, which' +
  '\n  left the documented escape hatch unusable without reading the source.' +
  '\n  Triage it: .claude/hooks/stop/worklist.py --triage <you> "<the finding>"';

/**
 * Comments and string literals out, whitespace collapsed, blanks dropped.
 *
 * Exported so the controls exercise the SAME function the tree goes through. A control
 * that runs a reimplementation proves nothing.
 */
export interface NormLine {
  /** The line's number in the ORIGINAL file, 1-based. */
  line: number;
  text: string;
}

/**
 * Words after which a `/` opens a REGEX LITERAL rather than dividing.
 *
 * `return /^(echo|printf)\b/.test(line)` is the spelling this repo actually uses -- it is
 * two lines above, in `isMessageish` -- so a heuristic that only looked at punctuation
 * would read that slash as division and then tokenise the quote inside the pattern.
 */
const REGEX_PRECEDING_WORDS = new Set([
  'return',
  'typeof',
  'case',
  'in',
  'of',
  'delete',
  'void',
  'instanceof',
  'new',
  'do',
  'else',
  'yield',
  'await',
  'throw',
]);

/** Does a `/` at this point open a regex literal, given the code emitted before it? */
export function opensRegex(before: string): boolean {
  const t = before.replace(/\s+$/, '');
  if (t === '') return true;
  const last = t[t.length - 1];
  // A value ended here, so the slash divides it.
  if (last === ')' || last === ']') return false;
  if (/[A-Za-z0-9_$]/.test(last)) {
    return REGEX_PRECEDING_WORDS.has(/[A-Za-z_$][A-Za-z0-9_$]*$/.exec(t)?.[0] ?? '');
  }
  return true;
}

/**
 * The end index of the regex literal starting at `i`, or -1 if it does not terminate on
 * its own line. `/` inside a `[...]` class is literal, which is why this is a walk and
 * not a pattern.
 */
export function regexEnd(s: string, i: number): number {
  let inClass = false;
  for (let j = i + 1; j < s.length; j++) {
    const c = s[j];
    if (c === '\\') {
      j++;
      continue;
    }
    if (c === '\n') return -1;
    if (c === '[') inClass = true;
    else if (c === ']') inClass = false;
    else if (c === '/' && !inClass) {
      let k = j + 1;
      while (k < s.length && /[a-z]/.test(s[k])) k++;
      return k;
    }
  }
  return -1;
}

/**
 * Comments AND string literals to one token, in ONE left-to-right pass.
 *
 * WHY THEY CANNOT BE SEPARATE PASSES, which is the whole finding. This function used to be
 * four independent regex sweeps run in a fixed order -- block comments, line comments, then
 * `'`, `"` and `` ` `` -- and source code is not written in that order. Each sweep saw the
 * WHOLE file, including the regions the other three own, so the first `'` in the file opened
 * a literal wherever that apostrophe actually lived, and `[^'\\]` matches a NEWLINE, so the
 * match ran to the next apostrophe anywhere at all. Everything between became one token and
 * was then dropped by the blank-line filter in `normalise`.
 *
 * MEASURED 2026-09-09 over the four families, with the old arms in place: 5957 multi-line
 * literal matches swallowing 36582 newlines across 237 of the 352 files the family globs
 * match, and 53174 normalised lines where this single pass yields 68274. The named case in
 * the finding is an apostrophe in a double-quoted message; the worst real case is a REGEX.
 * `scripts/gates/check-unverified-downloads.ts:60` is
 * `/\b(?:curl|wget)\b[^\n]*?(https?:\/\/[^\s"'\\]+)/g`, whose character class holds one
 * apostrophe 243 lines from the next one, and that 318-line file normalised to TWENTY-ONE
 * lines. It now yields 203. A duplication counter under-reporting because its own tokenizer
 * ate the corpus.
 *
 * The comment sweeps carried the identical hole in the other direction, and it only became
 * visible once the quote arms stopped hiding it: `scripts/gates/check-e2e-coverage.ts:233` is
 * `const DEFAULT_TEST_MATCH = '**\/*.@(spec|test).?(c|m)[jt]s?(x)';`, and the `*` `/` inside
 * that GLOB closed a `/*` opened by a `/**` inside a template literal 27 lines earlier. The
 * block-comment sweep blanked all 27 lines, which left the template literal itself
 * unterminated, which then ate the rest: that 579-line file yielded 260 normalised lines and
 * now yields 367. A comment marker inside a string is not a comment, and only a single
 * ordered pass can know that.
 *
 * Four rules, each bought by that measurement:
 *
 *   - ONE PASS. Whichever construct opens FIRST owns the region and every marker inside it
 *     is an ordinary character, which is what all three of these languages do.
 *   - `'` AND `"` STOP AT A NEWLINE, in shell too. TypeScript and Python cannot cross one;
 *     shell can, and this refuses to follow it there on purpose. Failing to join a genuine
 *     multi-line shell string fragments that one string into a few unique text lines, which
 *     UNDER-counts duplication. Following a stray apostrophe eats the rest of the file.
 *     Those costs are not comparable, so the conservative reading wins.
 *   - A BACKTICK CROSSES A NEWLINE ONLY IN TYPESCRIPT. Once `'` stopped eating the file the
 *     next-widest swallower took over: `.ci/scripts/quality/check-trap-registry.sh:140` is
 *     `match(line, /^[ \t]*(```+|~~~+)/)` inside an awk program inside a shell single-quoted
 *     string, so its THIRD backtick opened a literal running hundreds of lines. Measured with
 *     the quote arms already fixed and this one not: 296 of that file's 394 normalised lines
 *     gone, where it yields 514 today. In shell a backtick is legacy command
 *     substitution, which this tree spells `$(...)`; in TypeScript it is a template literal,
 *     where the multi-line spelling is normal and every other construct is consumed before a
 *     stray one could be met.
 *   - A REGEX LITERAL IS CODE, skipped verbatim rather than tokenised. Two gates matching
 *     different patterns are not the same scaffolding, and collapsing `/"[a-z]+"/` and
 *     `/"[0-9]+"/` to one `/"S"/` would invent duplication that is not there.
 *
 * EVERY REPLACEMENT KEEPS ITS NEWLINES, and their loss has been a real bug at three separate
 * layers of this function. `normalise` reports the line number a reader is asked to open, so
 * a construct that swallows the rows it spans renumbers the whole rest of the file. Measured
 * 2026-09-08 before the arms preserved them: `import pathlib` sits at
 * `.ci/scripts/quality/check_npmrc.py:66` and this function reported it at line 4, a 62-line
 * drift, with 275 of 348 files off by more than two and the worst at 814.
 *
 * An UNTERMINATED literal is abandoned -- the quote is emitted as an ordinary character and
 * the scan resumes after it -- so the blast radius of a guess this cannot make correctly is
 * one line rather than one file.
 */
export function stripNoise(s: string, kind: 'ts' | 'sh' | 'py'): string {
  const out: string[] = [];
  // The code emitted so far on THIS line, for the regex heuristic. Kept short on purpose: only the last token matters, and carrying the whole prefix would be quadratic.
  let tail = '';
  // Whether any non-blank character has been emitted on this line, for the `#` rule.
  let code = false;
  const emit = (t: string) => {
    out.push(t);
    tail = (tail + t).slice(-24);
    const nl = tail.lastIndexOf('\n');
    if (nl >= 0) tail = tail.slice(nl + 1);
  };
  /** Erase a span but keep the rows it spans, so nothing after it is renumbered. */
  const blank = (t: string) => emit(t.replace(/[^\n]/g, ''));
  const toEol = (from: number) => {
    const j = s.indexOf('\n', from);
    return j < 0 ? s.length : j;
  };
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '\n') {
      code = false;
      emit(c);
      i++;
      continue;
    }
    if (kind === 'ts' && c === '/' && s[i + 1] === '/' && s[i - 1] !== ':') {
      // `s[i - 1] !== ':'` is the old `(^|[^:])` guard, kept: a `://` in bare code (a URL in
      // an unquoted position) is not a comment. Inside a string it can no longer reach here at all, which is one more thing the single pass fixes for free.
      const j = toEol(i);
      blank(s.slice(i, j));
      i = j;
      continue;
    }
    if (kind === 'ts' && c === '/' && s[i + 1] === '*') {
      const close = s.indexOf('*/', i + 2);
      const j = close < 0 ? s.length : close + 2;
      blank(s.slice(i, j));
      i = j;
      continue;
    }
    if (kind !== 'ts' && c === '#' && !code) {
      // A LEADING-HASH LINE ONLY, and that is deliberate rather than lazy. A trailing `# ...` in shell can live inside a string or a regex, and guessing wrong changes the code rather than the comment. The single pass has already consumed the strings it can see, but shell quoting is context-sensitive enough that this stays cautious.
      const j = toEol(i);
      blank(s.slice(i, j));
      i = j;
      continue;
    }
    if (kind === 'py' && (s.startsWith('"""', i) || s.startsWith("'''", i))) {
      // PYTHON'S TRIPLE-QUOTED LITERAL IS A LITERAL, and until 2026-09-08 this function did not know it -- which meant the gate's FIRST stated exclusion did not apply to Python at all. The docstring at the top of this file says comments are deliberately not counted, because "any raw-similarity metric ranks prose first and creates pressure to delete exactly the lines that make a
      // green mean something". For shell and TypeScript the marker is `#` and `//` and both are stripped. Python's documentation idiom is the DOCSTRING, which is a string literal, so it reached the one-quote arms and was chewed into fragments: `.ci/scripts/quality/check_gate_id_convention.py` is 126 lines of which 115 are one docstring, and the gate reported five entry points as
      // sharing a shape whose content was their gate headers.
      //
      // It must be consumed WHOLE and BEFORE the one-quote arm, which would otherwise match the empty string `""` and then walk into the body.
      const q = s.slice(i, i + 3);
      const close = s.indexOf(q, i + 3);
      const j = close < 0 ? s.length : close + 3;
      emit(`${q[0]}S${q[0]}${s.slice(i, j).replace(/[^\n]/g, '')}`);
      i = j;
      code = true;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') {
      const allowNewline = c === '`' && kind === 'ts';
      // SHELL SINGLE QUOTES TAKE NO ESCAPES: inside them a backslash is a backslash and the only terminator is the next quote. Treating `\` as an escape there turns the `'\''` idiom into an unterminated literal.
      const escapes = !(kind === 'sh' && c === "'");
      let closed = -1;
      for (let j = i + 1; j < s.length; j++) {
        const d = s[j];
        if (escapes && d === '\\') {
          j++;
          continue;
        }
        if (d === '\n' && !allowNewline) break;
        if (d === c) {
          closed = j;
          break;
        }
      }
      if (closed < 0) {
        emit(c);
        code = true;
        i++;
        continue;
      }
      emit(`${c}S${c}${s.slice(i, closed + 1).replace(/[^\n]/g, '')}`);
      i = closed + 1;
      code = true;
      continue;
    }
    if (kind === 'ts' && c === '/' && opensRegex(tail)) {
      const end = regexEnd(s, i);
      if (end > 0) {
        emit(s.slice(i, end));
        i = end;
        code = true;
        continue;
      }
    }
    emit(c);
    if (!/\s/.test(c)) code = true;
    i++;
  }
  return out.join('');
}

export function normalise(src: string, kind: 'ts' | 'sh' | 'py'): NormLine[] {
  const s = stripNoise(src, kind);
  // THE LINE NUMBER IS CARRIED, and its absence was a real bug rather than a nicety. Comment-stripping blanks a line and the filter below then DROPS it, so the index into this array is not the index into the file -- every earlier `file:line` this gate emitted was a normalised-array position wearing a file line's clothes. Measured 2026-09-01 on
  // `.ci/scripts/test/gates/test-watchdog-log-capture.sh` (retired in W7 P5): a finding reported at `:17` actually sat at file line 46. A finding whose coordinate points somewhere else is a finding nobody can act on.
  //
  // Comment-stripping must therefore preserve the LINE COUNT, so a multi-line `/* */` block cannot swallow the newlines that separate the code after it from the code before it.
  return s
    .split('\n')
    .map(
      (l, i): NormLine => ({
        line: i + 1,
        text: l.replace(/\s+/g, ' ').trim(),
      })
    )
    .filter((l) => l.text.length > 0);
}

const hash = (s: string) => createHash('sha1').update(s).digest('hex').slice(0, 12);

/** An import, a require, or a shell `source` -- the line that USES a shared module. */
export function isImportish(line: string): boolean {
  // `from X import Y` IS AN IMPORT, and its absence was a gap rather than a choice. The docstring above says an import block is ADOPTION, not duplication -- files agreeing on what they depend on is the point of a shared module. That reasoning is language-neutral, but the pattern only ever knew TypeScript's `import` / `export …
  // from`, CommonJS `require`, and shell `source` / `.`. Python's other spelling went
  // uncounted, so a run of `from rediacc_ci.quality import …` lines read as copied code. Added 2026-09-08, when the corpus stopped being bash-and-TypeScript.
  return /^(import\b|from \S+ import\b|export .*\bfrom\b|const .*=\s*require\(|source |\. )/.test(
    line
  );
}

/**
 * A line whose whole content is a MESSAGE, once the string is normalised away.
 *
 * THIS GATE PROMISED THIS EXCLUSION AND DID NOT IMPLEMENT IT FOR SHELL. The docstring
 * above says the findings report is never counted -- "the sentence telling a reader what
 * failed and why IS the gate's value" -- and that held for TypeScript, where a report is
 * built from template literals inside distinguishable code. In shell the idiom is bare
 * `echo "..." >&2`, and string normalisation collapses EVERY such line to `echo "S" >&2`.
 * Four consecutive ones plus a `fi` therefore hash identically no matter what they say.
 *
 * Caught on its author, 2026-09-01, and it is the strongest possible demonstration of the
 * defect: the gate reported `check-control-vacuity.sh`, `block-untagged-commit.sh` and
 * `block-unverified-push.sh` as sharing a shape. They share nothing but the ACT of
 * printing four lines to stderr; their messages are three unrelated explanations, and
 * consolidating them would delete the only part that has value.
 *
 * Same treatment as an import preamble, for the same reason: it is a majority test, so a
 * genuine shared span that happens to contain one echo still registers.
 */
export function isMessageish(line: string): boolean {
  // The `>&2` redirect is part of the idiom, so `&` cannot be excluded wholesale -- the first cut did that and matched nothing, which is why this carries a control.
  //
  // `sys.stderr.write` AND `sys.stdout.write` ARE THE PYTHON SPELLING of `echo … >&2`, and their absence was the same language gap `isImportish` had. Probed 2026-09-08:
  // `print("S", file=sys.stderr)` already matched through the `print` alternative, but
  // `sys.stderr.write("S")` matched NOTHING -- so half the Python report idiom was excluded and half was counted as copied code. A gate that reports anything has one of these lines, so the miss was systematic rather than occasional.
  //
  // DELIBERATELY NOT WIDENED to `gate.log_fail` and its siblings: a repeated call to an already-shared helper is a different exclusion with a different argument -- the seed entry `98b21fa52e5d` states that case and says outright it is not excluded yet -- and folding it in here would silence a class this predicate was never reasoned about.
  return /^(echo|printf|print|sys\.(stderr|stdout)\.write|console\.(log|error|warn))\b[^|;]*$/.test(
    line
  );
}

/**
 * A line with NO CODE left once the normalised literals and punctuation are removed.
 *
 * THE SEED ALREADY MAKES THIS ARGUMENT BY HAND, and that is the evidence it is a
 * generalisation rather than a new silencer. `ea3b237265c0`'s BLOCKER says the
 * fingerprint "carries NO CODE" and is "reproducible as a bare sha1 with no file
 * involved" -- eleven of the accepted entries say some version of it.
 *
 * WHY SHELL DID NOT NEED IT AND PYTHON DOES. `isMessageish` above catches the shell
 * idiom, where a report is one line: `echo "..." >&2`. A formatter wraps the Python
 * equivalent across four or five, so the continuations are bare `"S",` and `f"S"` and
 * `)` and `file=sys.stderr,`. Those hash identically in every gate that reports
 * anything, which is every gate.
 *
 * Majority, exactly like the other two exclusions, so a real shared span that happens to
 * contain one continuation still registers.
 */
export function isContentFree(line: string): boolean {
  return line.replace(/["'`]S["'`]|[(){}[\],;:.=]|\bf\b|file|sys\.stderr|\s+/g, '') === '';
}

/**
 * A CALL to a helper that is already defined once and shared -- adoption, not a copy.
 *
 * THE SEED MAKES THIS ARGUMENT BY HAND AND SAYS SO. `98b21fa52e5d`'s BLOCKER is three
 * gate tests using `assert_exit_code` and four `assert_contains`/`assert_not_contains`,
 * "all defined once in .ci/scripts/test/lib/test-helpers.sh and sourced by all three
 * files", and it ends: "This gate's own docstring excludes an import preamble as
 * adoption for exactly this reason; repeated CALLS to an already-shared helper are the
 * same case and are simply not excluded yet." This is that sentence made executable.
 *
 * WHY AN IMPORT LINE WAS NOT ENOUGH. `isImportish` excludes the line that ADOPTS the
 * module. In shell the adoption is one `source` line at the top and the five lines that
 * actually repeat are the CALLS, which sit nowhere near it -- so a window over the calls
 * carries no importish line at all and the majority test never fires. The distinguishing
 * tokens in such a window are all ARGUMENTS: the three files above assert three unrelated
 * things and share only the act of asserting.
 *
 * DERIVED, NEVER TYPED. The helper names come from the corpus: a library file that two or
 * more scanned files `source` is shared BY OBSERVATION, and its `name() {` definitions are
 * the helpers. A hardcoded list of helper names would be the enumeration-drift class this
 * gate's own FAMILIES floors exist to refuse, and it would go stale on the first rename.
 *
 * PYTHON IS THE EXACT SAME ARGUMENT IN A SECOND LANGUAGE, and its absence was a gap rather
 * than a decision -- the same gap `isImportish` and `isMessageish` each carry a note about
 * one function up. A module two or more corpus files IMPORT is shared by observation, and
 * its `def name(` definitions are its helpers. Measured 2026-09-08 over the corpus widened
 * to the three Python families: 17 modules clear the two-user threshold, headed by
 * `_cipath` (91 users), `rediacc_ci.tests.gates.harness` (68) and `rediacc_hooks.hookio`
 * (42), and they contribute 279 names. Without this arm a run of
 * `gate.assert_contains(...)` / `gate.log_pass(...)` lines -- three unrelated assertions
 * whose only shared token is the ACT of asserting, which is `98b21fa52e5d`'s argument
 * verbatim -- reads as copied code.
 *
 * Majority, exactly like the other three, so a genuine shared span that happens to contain
 * one helper call still registers.
 */
export function sharedHelperNames(files: string[]): ReadonlySet<string> {
  const names = new Set<string>();
  for (const n of shellHelperNames(files)) names.add(n);
  for (const n of pythonHelperNames(files)) names.add(n);
  return names;
}

/** `name() {` in a `.sh` library two or more corpus files `source`. */
function shellHelperNames(files: string[]): Set<string> {
  // Which library each scanned file sources. Only a path is taken, never a variable: a `source "$LIB"` we cannot resolve is left out rather than guessed at, because a wrong guess here silences real code.
  const sourcedBy = new Map<string, Set<string>>();
  for (const f of files) {
    let src: string;
    try {
      src = readFileSync(path.join(ROOT, f), 'utf8');
    } catch {
      continue;
    }
    for (const m of src.matchAll(
      /^\s*(?:source|\.)\s+["']?(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\/)?([\w./-]+\.sh)["']?/gm
    )) {
      const lib = path.basename(m[1]);
      const s = sourcedBy.get(lib);
      if (s) s.add(f);
      else sourcedBy.set(lib, new Set([f]));
    }
  }
  const names = new Set<string>();
  for (const [lib, users] of sourcedBy) {
    // TWO USERS IS THE THRESHOLD, and it is the definition of "already shared" rather
    // than a tuning knob: a library one file sources is that file's private helper, and
    // excluding its calls would hide a genuine copy made inside a single file's own lib.
    if (users.size < 2) continue;
    for (const hit of execFileSync('git', ['ls-files', `*/${lib}`], {
      cwd: ROOT,
      encoding: 'utf8',
    })
      .split('\n')
      .filter(Boolean)) {
      let body: string;
      try {
        body = readFileSync(path.join(ROOT, hit), 'utf8');
      } catch {
        continue;
      }
      for (const d of body.matchAll(/^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{/gm)) {
        names.add(d[1]);
      }
    }
  }
  return names;
}

/**
 * Every dotted module a Python source imports, in the two spellings that resolve to a
 * file without knowing the interpreter's search path.
 *
 * `from A.B import c` YIELDS BOTH `A.B` AND `A.B.c`, because Python spells "import the
 * submodule" and "import the name from the module" identically and only the filesystem
 * can tell them apart. Emitting both and letting resolution decide is the conservative
 * order: an unresolvable candidate contributes nothing, whereas guessing wrong one way
 * drops a genuinely shared module and guessing wrong the other invents one.
 *
 * A RELATIVE import (`from . import x`) is deliberately dropped rather than resolved
 * against the file's directory. Measured 2026-09-08: the widened corpus contains ZERO of
 * them, so the resolution code would be untested by construction, and untested resolution
 * in a SILENCER is the wrong thing to carry.
 *
 * Exported so the controls exercise the real extractor rather than a reimplementation.
 *
 * @param src A Python source file's contents.
 */
export function importedModules(src: string): string[] {
  const out: string[] = [];
  // `[A-Za-z_][\w.]*` AND NOT `[\w.]+`, and the difference is the whole relative-import exclusion: `[\w.]+` happily matches the leading dot, so `from . import sibling` yielded the module `.` and `from .pkg import thing` yielded `.pkg`. Both are unresolvable, so nothing was silenced -- but a module list containing `.` is a parser reporting garbage and being saved by the next stage,
  // which is not the same as a parser that is right. Caught by the control below on its first run.
  for (const m of src.matchAll(/^[ \t]*import[ \t]+([A-Za-z_][\w.]*)/gm)) out.push(m[1]);
  for (const m of src.matchAll(/^[ \t]*from[ \t]+([A-Za-z_][\w.]*)[ \t]+import[ \t]+(.+)$/gm)) {
    const base = m[1];
    out.push(base);
    for (const n of m[2].replace(/[()]/g, '').split(/[,\s]+/)) {
      if (/^[A-Za-z_]\w*$/.test(n)) out.push(`${base}.${n}`);
    }
  }
  return out;
}

/** Every tracked path, read once. A per-module `git ls-files` would be 34 forks. */
let TRACKED_CACHE: string[] | null = null;
const allTracked = (): string[] => {
  if (TRACKED_CACHE === null) {
    TRACKED_CACHE = execFileSync('git', ['ls-files'], { cwd: ROOT, encoding: 'utf8' })
      .split('\n')
      .filter(Boolean);
  }
  return TRACKED_CACHE;
};

/**
 * The tracked file(s) a dotted module could be, by SUFFIX, exactly as the shell arm
 * resolves a sourced library by basename.
 *
 * @param mod A dotted module path, e.g. `rediacc_ci.tests.gates.harness`.
 * @param tracked Every tracked path.
 */
export function resolveModule(mod: string, tracked: readonly string[]): string[] {
  const p = mod.replace(/\./g, '/');
  const candidates = [`${p}.py`, `${p}/__init__.py`];
  return tracked.filter((t) => candidates.some((c) => t === c || t.endsWith(`/${c}`)));
}

/** `def name(` in a module two or more corpus files import. */
function pythonHelperNames(files: string[]): Set<string> {
  const importedBy = new Map<string, Set<string>>();
  for (const f of files) {
    if (!f.endsWith('.py')) continue;
    let src: string;
    try {
      src = readFileSync(path.join(ROOT, f), 'utf8');
    } catch {
      continue;
    }
    for (const mod of importedModules(src)) {
      const s = importedBy.get(mod);
      if (s) s.add(f);
      else importedBy.set(mod, new Set([f]));
    }
  }
  const names = new Set<string>();
  const seen = new Set<string>();
  for (const [mod, users] of importedBy) {
    // TWO USERS IS THE THRESHOLD, for the reason the shell arm states: a module one file imports is that file's private helper, and excluding its calls would hide a genuine copy made inside a single file's own library.
    if (users.size < 2) continue;
    for (const hit of resolveModule(mod, allTracked())) {
      if (seen.has(hit)) continue;
      seen.add(hit);
      let body: string;
      try {
        body = readFileSync(path.join(ROOT, hit), 'utf8');
      } catch {
        continue;
      }
      // A METHOD IS A HELPER TOO, and that is not a widening for its own sake: the shape this arm exists to excuse is `gate.assert_contains(...)`, where `gate` is an instance of a class defined in the shared module. An indented `def` inside a `class` is exactly as shared as a module-level one, so the pattern is not anchored to column zero.
      for (const d of body.matchAll(/^[ \t]*def[ \t]+([A-Za-z_]\w*)[ \t]*\(/gm)) names.add(d[1]);
    }
  }
  return names;
}

/**
 * A line whose leading expression CALLS a shared helper.
 *
 * THREE SHAPES, and the third one is why this could not stay a single leading-word test.
 * Shell calls a helper as `assert_exit_code 0 "$out"` -- a bare word then arguments.
 * Python calls the same helper as `gate.assert_exit_code(1, result.rc, "...")`, where the
 * leading word is the RECEIVER and the helper name is behind a dot. A predicate that only
 * read the first word saw `gate` and matched nothing, which is precisely why the widened
 * corpus reported six copies of `test_gate_*.py` spans that are nothing but assertions.
 *
 * AND THE FIRST-WORD TEST HAD TO TIGHTEN AT THE SAME TIME, because the two languages now
 * share one name set. `harness.py` defines `def result(...)` and `def record(...)`, so the
 * loose `^name\b` matched the Python ASSIGNMENT `result = run_gate(...)` and would have
 * excluded a real line for a reason that has nothing to do with adoption. A call is a name
 * followed by `(`, or a name followed by an argument, or a name alone on its line -- never
 * a name followed by `=`. Measured on the un-widened corpus: the tightening changes
 * nothing (347 files, 41566 windows, 0 new shapes, byte-identical report), so it is a
 * guard against the new set rather than a re-tuning of the old behaviour.
 *
 * @param line A normalised line.
 * @param helpers Names harvested by `sharedHelperNames`.
 */
export function isSharedHelperCall(line: string, helpers: ReadonlySet<string>): boolean {
  const dotted = /^[A-Za-z_]\w*(?:\.\w+)*\.([A-Za-z_]\w*)[ \t]*\(/.exec(line);
  if (dotted !== null && helpers.has(dotted[1])) return true;
  // `(?![= \t])` AND NOT `(?![=])`: with the shorter lookahead a greedy `[ \t]+` simply
  // backtracks one space, sees a space rather than the `=`, and matches anyway. The
  // negative class has to exclude whitespace or it excludes nothing.
  const first = /^([A-Za-z_]\w*)(?:[ \t]*\(|[ \t]+(?![= \t])|$)/.exec(line);
  return first !== null && helpers.has(first[1]);
}

/**
 * Every sliding WINDOW-line span, minus the ones that are mostly imports.
 *
 * A window over an import preamble is not duplicated logic; it is three files agreeing to
 * use the same module, which is the outcome this gate wants. Majority rather than any,
 * so a genuine shared span that happens to start one line into an import block still
 * registers.
 */
const NO_HELPERS: ReadonlySet<string> = new Set();

export function windows(
  lines: NormLine[],
  helpers: ReadonlySet<string> = NO_HELPERS
): { h: string; line: number }[] {
  const out: { h: string; line: number }[] = [];
  for (let i = 0; i + WINDOW <= lines.length; i++) {
    const slice = lines.slice(i, i + WINDOW);
    if (slice.filter((l) => isImportish(l.text)).length * 2 > WINDOW) continue;
    if (slice.filter((l) => isMessageish(l.text)).length * 2 > WINDOW) continue;
    if (slice.filter((l) => isContentFree(l.text)).length * 2 > WINDOW) continue;
    // DEFAULTS TO EMPTY so every existing caller -- and every control below -- keeps the behaviour it was written against. Only `scan` passes the real set, which is what makes the corpus measurement attributable to this predicate alone.
    if (slice.filter((l) => isSharedHelperCall(l.text, helpers)).length * 2 > WINDOW) continue;
    // The window's line is the REAL file line its first row came from.
    out.push({
      h: hash(slice.map((l) => l.text).join('\n')),
      line: slice[0].line,
    });
  }
  return out;
}

export interface Finding {
  shape: string;
  files: string[];
  /** How many overlapping windows were merged into this one span. */
  span: number;
}

/**
 * Overlapping windows over ONE shared span are one finding, not twenty-four.
 *
 * A 28-line span shared by four files produces 24 sliding windows, each with the same file
 * set and consecutive start lines. Reporting them separately turned a real measurement --
 * 336 windows on this tree -- into a number that describes the window size rather than the
 * duplication, and an operator reading it would have to do the division themselves.
 *
 * Two windows merge when they name the SAME files and their start lines are within one
 * window of each other in every file. Same-files is the strict half: two genuinely
 * different spans that happen to sit adjacent in one file will differ in the others.
 */
export function coalesce(findings: Finding[]): Finding[] {
  const byFileSet = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = f.files.map((x) => x.split(':')[0]).join('|');
    const g = byFileSet.get(key);
    if (g) g.push(f);
    else byFileSet.set(key, [f]);
  }
  const out: Finding[] = [];
  for (const group of byFileSet.values()) {
    const sorted = [...group].sort(
      (a, b) => Number(a.files[0].split(':')[1]) - Number(b.files[0].split(':')[1])
    );
    let cur = sorted[0];
    let merged = 1;
    for (const f of sorted.slice(1)) {
      const prev = Number(cur.files[0].split(':')[1]) + merged - 1;
      if (Number(f.files[0].split(':')[1]) - prev <= WINDOW) merged += 1;
      else {
        out.push({ ...cur, span: merged + WINDOW - 1 });
        cur = f;
        merged = 1;
      }
    }
    out.push({ ...cur, span: merged + WINDOW - 1 });
  }
  return out.sort((a, b) => b.files.length * b.span - a.files.length * a.span);
}

/**
 * Which shapes have reached N copies and were not already here.
 *
 * `seed` is the set of hashes present when the gate was installed. Exported and pure, so
 * the controls drive the real judgement.
 */
/**
 * Every shape, with the files carrying it and the FIRST line it occupies in each.
 *
 * FACTORED OUT OF `judge` FOR THE PROBE, and the extraction is the point rather than tidiness. The pre-commit probe (`--emit-index`, then `probe.mjs`) needs the same tally over a cached corpus plus one staged file, and `deadAccepted` and the `--seed` writer each build their own smaller version of it. A counter whose own counting rule existed three times would be the finding this
 * file reports.
 *
 * `seed` is skipped here rather than at the caller so a seeded shape never reaches the tally at all, which is what makes the index buildable with an EMPTY seed: the probe applies the seed it reads at probe time, so editing the seed does not stale the cache.
 */
export function countShapes(
  perFile: Map<string, { h: string; line: number }[]>,
  seed: Set<string>
): Map<string, Map<string, number>> {
  const byShape = new Map<string, Map<string, number>>();
  for (const [file, ws] of perFile) {
    for (const w of ws) {
      if (seed.has(w.h)) continue;
      let m = byShape.get(w.h);
      if (!m) byShape.set(w.h, (m = new Map()));
      // The FIRST window of this shape in this file. Every later one is the same span sliding forward, and `coalesce` merges them back anyway.
      if (!m.has(file)) m.set(file, w.line);
    }
  }
  return byShape;
}

export function judge(
  perFile: Map<string, { h: string; line: number }[]>,
  seed: Set<string>
): Finding[] {
  const byShape = countShapes(perFile, seed);
  const findings: Finding[] = [];
  for (const [h, files] of byShape) {
    if (files.size < N) continue;
    findings.push({
      shape: h,
      files: [...files].map(([f, l]) => `${f}:${l}`).sort(),
      span: WINDOW,
    });
  }
  return coalesce(findings);
}

/** Tracked files for one family, so the floor below is checked per family. */
function trackedIn(pathspec: string): string[] {
  return execFileSync('git', ['ls-files', pathspec], {
    cwd: ROOT,
    encoding: 'utf8',
  })
    .split('\n')
    .filter(Boolean);
}

function tracked(): string[] {
  // THE FLOOR IS PER FAMILY AND IT IS A COUNT, for the reason recorded at FAMILIES. A family that emptied is invisible to a whole-corpus check, and one that shrank to a single file is invisible to a non-emptiness check. Both happened here.
  const short = FAMILIES.map((f) => ({
    f,
    n: trackedIn(f.pathspec).length,
  })).filter((r) => r.n < r.f.floor);
  if (short.length > 0) {
    for (const { f, n } of short) {
      console.error(
        `${RED}✗${NC} family ${f.pathspec} has ${n} tracked file(s), below its floor of ${f.floor}`
      );
    }
    console.error(
      '  A family that shrank is a family this gate stopped scanning, and it would have ' +
        'kept reporting a confident green. Either the files moved (update FAMILIES in the ' +
        'same change that moved them) or they were ported to another extension.'
    );
    process.exit(1);
  }
  const all = refuseIfEmpty(
    execFileSync('git', ['ls-files', ...FAMILY_PATHSPECS], {
      cwd: ROOT,
      encoding: 'utf8',
    })
      .split('\n')
      .filter(Boolean),
    `tracked files matching ${FAMILIES.length} family pathspec(s)`,
    'The families moved, or this is not a repository checkout.'
  );
  return refuseIfEmpty(
    all.filter((f) => {
      const src = readFileSync(path.join(ROOT, f), 'utf8');
      return !src.includes(OPT_OUT);
    }),
    'the same corpus after the opt-out filter',
    `Every one of the ${all.length} tracked file(s) carries the ${OPT_OUT} marker, which is a corpus that opted itself out entirely rather than a clean tree.`
  );
}

/**
 * The corpus, hashed. The HELPER SET comes back too, because the index needs it.
 *
 * `windows` takes the helper set as an argument and the probe cannot derive one: "already shared" is a count of USERS across the whole corpus, and a probe that scanned one staged file would see no users at all and silence nothing. So the set the corpus scan derived is cached alongside the hashes, which is also the known gap the plan states -- a staged file that newly makes a
 * module shared changes the answer only at CI.
 */
function scan(files: string[]): {
  perFile: Map<string, { h: string; line: number }[]>;
  helpers: ReadonlySet<string>;
} {
  const m = new Map<string, { h: string; line: number }[]>();
  // Computed ONCE over the whole corpus, not per file: "already shared" is a property of the library's user count across the corpus, which no single file can see.
  const helpers = sharedHelperNames(files);
  for (const f of files) {
    // `.py` SHARES THE `#` COMMENT ARM WITH SHELL AND ADDS ONE OF ITS OWN. It was normalised as 'sh' outright until 2026-09-08, on the argument that the two languages have the same lexical shape; they do not, because Python has a triple-quoted literal and its documentation lives inside one. See the `py` arm in `normalise`. Only `.ts` needs the `//` and `/* */` handling.
    m.set(f, windows(normalise(readFileSync(path.join(ROOT, f), 'utf8'), kindFor(f)), helpers));
  }
  return { perFile: m, helpers };
}

/** Controls, each the real defect or the real non-defect, reconstructed. */
function controls(): { name: string; ok: boolean; detail?: string }[] {
  const mk = (n: number, body: string) =>
    new Map(
      Array.from({ length: n }, (_, i): [string, { h: string; line: number }[]] => [
        `f${i}.ts`,
        windows(normalise(body, 'ts')),
      ])
    );
  const SPAN = `const a = 1;\nconst b = 2;\nconst c = 3;\nconst d = 4;\nconst e = 5;`;
  const empty = new Set<string>();

  return [
    {
      name: `${N} files sharing a ${WINDOW}-line span is a finding`,
      ok: judge(mk(N, SPAN), empty).length === 1,
    },
    {
      name: `CONTROL: ${N - 1} files sharing it is not`,
      ok: judge(mk(N - 1, SPAN), empty).length === 0,
    },
    {
      name: 'CONTROL: a seeded shape stays silent however many copies it has',
      ok: (() => {
        const per = mk(N + 5, SPAN);
        const seed = new Set(windows(normalise(SPAN, 'ts')).map((w) => w.h));
        return judge(per, seed).length === 0;
      })(),
    },
    {
      name: 'the finding names every file, with a line',
      ok:
        judge(mk(N, SPAN), empty)[0]?.files.length === N &&
        /^f0\.ts:\d+$/.test(judge(mk(N, SPAN), empty)[0].files[0]),
    },
    {
      name: 'CONTROL: comments are not code, so a shared prose header is not a copy',
      ok: normalise('// a\n// b\n// c\n// d\n// e\nconst x = 1;', 'ts').length === 1,
    },
    {
      name: 'CONTROL: a shell prose header is not a copy either',
      ok: normalise('# a\n# b\n# c\n# d\n# e\nx=1', 'sh').length === 1,
    },
    {
      // The Python spelling, which nothing exercised until 2026-09-08. An import block is adoption rather than duplication, and a run of `from rediacc_ci.quality
      // import <mod>` lines used to read as copied code because isImportish only knew
      // TypeScript's and shell's forms.
      name: 'a Python `from X import Y` counts as an import, not as copied code',
      ok: isImportish('from rediacc_ci.quality import npmrc'),
    },
    {
      // The other direction, and it is not decoration: a pattern of `^from ` alone would swallow ordinary assignments, and an import exclusion that eats real code is a silencer.
      name: 'CONTROL: an identifier merely starting with `from` is not an import',
      ok: !isImportish('from_here = 1') && !isImportish('fromage = 2'),
    },
    {
      // The wrapped-report exclusion. `isMessageish` catches shell's one-line `echo …` idiom; a formatter wraps the Python equivalent, so the continuations are bare
      // `"S",` and `)` and `file=sys.stderr,` and they hash identically in every gate
      // that reports anything. Eleven of the accepted BLOCKERs already argue this by hand; this is that argument made executable.
      name: 'a wrapped report line carries no code and is not a copy',
      ok:
        isContentFree('"S"') &&
        isContentFree('"S",') &&
        isContentFree('file=sys.stderr,') &&
        isContentFree(')'),
    },
    {
      // The direction that stops it being a silencer. An exclusion that eats real code would make the whole gate vacuous, and a majority rule cannot save it.
      name: 'CONTROL: a line with actual code is never content-free',
      ok: !isContentFree('return 1') && !isContentFree('x = 1') && !isContentFree('assert_eq a b'),
    },
    {
      // The Python half of the report idiom. `echo "S" >&2` was excluded and `sys.stderr.write("S")` was not, so half of every ported gate's report counted as copied code. Same language gap isImportish had, one predicate over.
      name: 'a Python `sys.stderr.write` report is a message, not a copy',
      ok: isMessageish('sys.stderr.write("S")') && isMessageish('sys.stdout.write("S")'),
    },
    {
      // The bound. A repeated call to an already-shared helper is a DIFFERENT exclusion
      // with a different argument (seed entry 98b21fa52e5d states it and says it is not
      // excluded yet); folding it in here would silence a class this predicate was never reasoned about. This control is what stops that happening by accident.
      name: 'CONTROL: a harness helper call is not a message, and an assignment is not either',
      ok: !isMessageish('gate.log_fail("S")') && !isMessageish('x = sys.stderr'),
    },
    {
      // The coordinate fix, pinned. A multi-line string literal must not renumber the code after it -- the same property the block-comment control above asserts, and the one whose absence put `check_npmrc.py:66` at line 4.
      name: 'CONTROL: a multi-line string literal does not renumber the code after it',
      ok: normalise("x = 'a\nb\nc\nd'\ny = 1", 'sh').slice(-1)[0]?.line === 5,
    },
    {
      name: 'two gates whose only difference is their message are the same scaffolding',
      ok:
        normalise('const m = "dead css found";', 'ts')[0].text ===
        normalise('const m = "dead keys found";', 'ts')[0].text,
    },
    {
      name: `CONTROL: a ${WINDOW - 1}-line file yields no window, so a one-liner cannot fire`,
      ok: windows(normalise('a\nb\nc\nd', 'ts')).length === 0,
    },
    {
      name: 'an accepted divergence with a real BLOCKER is honoured',
      ok:
        checkAccepted({
          abc123:
            'BLOCKER: run_gate() has three incompatible return contracts (echo rc, echo PASS/FAIL, propagate); extracting it verbatim would be wrong',
        }).ok.length === 1,
    },
    {
      name: 'CONTROL: a low-effort BLOCKER buys no silence',
      ok: checkAccepted({ abc123: 'BLOCKER: tbd' }).ok.length === 0,
    },
    {
      // The reason here is deliberately LONG and substantive, so the only rule that can reject it is the prefix rule. The first version of this control used a 28-char reason, which `validateBlockerQuality` rejects for length alone -- it passed with the prefix check deleted, which is a control that cannot fail.
      name: 'CONTROL: a reason without the BLOCKER: prefix buys no silence',
      ok:
        checkAccepted({
          abc123:
            'run_gate() has three incompatible return contracts (echo rc, echo PASS/FAIL, propagate); extracting it verbatim would be wrong',
        }).ok.length === 0,
    },
    {
      // THE COORDINATE MUST BE A FILE LINE. Comment-stripping drops lines, so the index into the normalised array is not the index into the file. Before this, a finding in `test-watchdog-log-capture.sh` reported `:17` for code sitting at line 46.
      name: 'a finding names the REAL file line, not the normalised index',
      ok: (() => {
        const src =
          '// a\n// b\n// c\nconst a = 1;\nconst b = 2;\nconst c = 3;\nconst d = 4;\nconst e = 5;';
        return normalise(src, 'ts')[0].line === 4 && windows(normalise(src, 'ts'))[0].line === 4;
      })(),
    },
    {
      name: 'CONTROL: a block comment does not renumber the code after it',
      ok: normalise('/* a\n b\n c */\nconst z = 1;', 'ts')[0].line === 4,
    },
    {
      // THE `\s` THAT ATE A LINE. `^\s*#` matches a NEWLINE inside `\s*`, so a comment with a blank line above it consumed that blank line's terminator and every coordinate below shifted up by one. Measured 2026-09-08: `if __name__` sits at line 208 of `.ci/scripts/quality/check_e2e_case_blind_assertions.py` and this function reported 207. Text and hashes are unaffected, which is
      // exactly why nothing caught it.
      name: 'CONTROL: a blank line above a hash comment is not swallowed',
      ok: normalise('x=1\n\n# c\ny=2', 'sh').slice(-1)[0]?.line === 4,
    },
    {
      // PYTHON'S COMMENT IDIOM IS THE DOCSTRING, and the gate's first stated exclusion is comments. Before this arm the two single-quote arms paired quotes across the prose and emitted the middle of a docstring as though it were three lines of code, which in a tree whose entry points are 90% docstring is not an edge case.
      name: 'a Python docstring is prose: one token, and the code after it keeps its line',
      ok: (() => {
        const src =
          '"""Doc.\n\nProse with "quoted" words and an example:\n foo --selftest\n"""\nimport sys\nx = 1';
        const n = normalise(src, 'py');
        return n.length === 3 && n[0].text === '"S"' && n[1].line === 6 && n[2].line === 7;
      })(),
    },
    {
      // THE DIRECTION THAT KEEPS THE SEED VALID. The 275 seeded shapes were measured over a ts-and-sh corpus; if the triple-quote arm reached `sh` it would rewrite what those files hash to and silently re-seed the gate. Bash has no triple-quoted string, so the arm is `py` only, and this asserts it.
      name: 'CONTROL: the triple-quote arm is Python-only, so the shell corpus is untouched',
      ok: (() => {
        const src = '"""Doc.\n\nProse with "quoted" words.\n"""\nx = 1';
        return normalise(src, 'sh').length > normalise(src, 'py').length;
      })(),
    },
    {
      // THE ANTI-SILENCER DIRECTION. An arm that swallowed a triple-quoted literal's NEIGHBOURS would make every Python file look shorter than it is and hide real copies. Real code either side of a docstring is still counted, and still fires.
      name: 'CONTROL: real Python code around a docstring is still counted, and still fires',
      ok: (() => {
        const body =
          'def f():\n    """Doc.\n\n    More prose.\n    """\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    e = 5\n';
        return (
          judge(
            new Map(
              Array.from({ length: N }, (_, i): [string, { h: string; line: number }[]] => [
                `f${i}.py`,
                windows(normalise(body, 'py')),
              ])
            ),
            new Set()
          ).length === 1
        );
      })(),
    },
    {
      // THE GATE CAUGHT ITS AUTHOR ON THIS. String literals normalise to "S", so four consecutive stderr messages hash identically no matter what they SAY. It reported check-control-vacuity.sh, block-untagged-commit.sh and block-unverified-push.sh as one shape; they share only the ACT of printing, and consolidating them would delete three unrelated explanations -- the findings
      // report this gate's own docstring promises never to count.
      name: 'CONTROL: four stderr messages are a report, not a shared shape',
      ok: (() => {
        const body =
          'if [ -n "$x" ]; then\n' +
          '  echo "a" >&2\n  echo "b" >&2\n  echo "c" >&2\n  echo "d" >&2\nfi';
        const per = new Map(
          ['f1', 'f2', 'f3'].map((f): [string, { h: string; line: number }[]] => [
            f,
            windows(normalise(body, 'sh')),
          ])
        );
        return judge(per, new Set()).length === 0;
      })(),
    },
    {
      name: 'the message matcher takes a stderr redirect and rejects a pipe or plain code',
      ok:
        isMessageish('echo "S" >&2') &&
        isMessageish('printf "S"') &&
        !isMessageish('fi') &&
        !isMessageish('echo "S" | grep x') &&
        !isMessageish('const a = 1;'),
    },
    {
      // THE PREDICATE THE SEED ASKED FOR, in the shape it asked for it. `98b21fa52e5d`'s BLOCKER is five lines of `assert_exit_code` / `assert_contains` shared by three gate tests, and it ends "repeated CALLS to an already-shared helper are the same
      // case and are simply not excluded yet". Measured 2026-09-08 against an empty seed:
      // that fingerprint is reported without this predicate and gone with it.
      name: 'a window of calls to an already-shared helper is adoption, not a copy',
      ok:
        windows(
          normalise(
            [
              'assert_exit_code 0 "$out"',
              'assert_contains "$out" "a"',
              'assert_contains "$out" "b"',
              'assert_contains "$out" "c"',
              'assert_not_contains "$out" "d"',
            ].join('\n'),
            'sh'
          ),
          new Set(['assert_exit_code', 'assert_contains', 'assert_not_contains'])
        ).length === 0,
    },
    {
      // THE ANTI-SILENCER DIRECTION, and it is the half that makes the exclusion safe. An exclusion keyed on a name set must not eat code merely because it sits beside a helper call: the same five lines, with the helper set EMPTY, are still counted.
      name: 'CONTROL: the same window with no shared helper in scope is still counted',
      ok:
        windows(
          normalise(
            [
              'assert_exit_code 0 "$out"',
              'assert_contains "$out" "a"',
              'assert_contains "$out" "b"',
              'assert_contains "$out" "c"',
              'assert_not_contains "$out" "d"',
            ].join('\n'),
            'sh'
          )
        ).length > 0,
    },
    {
      // A library ONE file sources is that file's private helper, not a shared one, and excluding its calls would hide a genuine copy made inside a single file's own lib. The threshold is a definition, so it gets a control rather than a comment.
      name: 'CONTROL: a library only one corpus file sources yields no shared helpers',
      ok: sharedHelperNames(['.claude/hooks/pre-bash/block-pathspecless-git-commit.ts']).size === 0,
    },
    // --- the Python arm of the same exclusion -------------------------------------
    {
      // `from A.B import c` is ambiguous between "the name c in module A.B" and "the SUBMODULE A.B.c", and only the filesystem knows which. Both candidates are emitted; resolution decides.
      name: 'a Python `from A.B import c, d` offers A.B and both submodule candidates',
      ok:
        JSON.stringify(importedModules('from rediacc_ci.tests.gates import harness, other')) ===
        JSON.stringify([
          'rediacc_ci.tests.gates',
          'rediacc_ci.tests.gates.harness',
          'rediacc_ci.tests.gates.other',
        ]),
      detail: JSON.stringify(importedModules('from rediacc_ci.tests.gates import harness, other')),
    },
    {
      name: 'a plain `import A.B` offers A.B',
      ok: JSON.stringify(importedModules('import rediacc_ci.paths')) === '["rediacc_ci.paths"]',
    },
    {
      // Dropped rather than resolved, and the docstring says why: the widened corpus has ZERO of them, so resolution code for it would be untested by construction.
      name: 'CONTROL: a RELATIVE import offers nothing, rather than a bogus module',
      ok: importedModules('from . import sibling\nfrom .pkg import thing').length === 0,
      detail: JSON.stringify(importedModules('from . import sibling\nfrom .pkg import thing')),
    },
    {
      name: 'CONTROL: prose that merely says the word import offers nothing',
      ok: importedModules('# we import nothing here\nx = "import os"').length === 0,
    },
    {
      name: 'a module resolves to a tracked file by SUFFIX, package or plain',
      ok:
        JSON.stringify(
          resolveModule('a.b', ['x/a/b.py', 'a/b.py', 'q/a/b/__init__.py', 'other/ab.py'])
        ) === JSON.stringify(['x/a/b.py', 'a/b.py', 'q/a/b/__init__.py']),
      detail: JSON.stringify(
        resolveModule('a.b', ['x/a/b.py', 'a/b.py', 'q/a/b/__init__.py', 'other/ab.py'])
      ),
    },
    {
      // The anti-silencer half: an unresolvable module contributes NO names, so a typo or a third-party import cannot widen the exclusion set.
      name: 'CONTROL: a module with no tracked file resolves to nothing',
      ok: resolveModule('os.path', ['a/b.py']).length === 0,
    },
    {
      // The shape that motivated the whole arm: a formatter-wrapped `gate.assert_contains(...)` is a CALL to a shared helper, and the leading word is the receiver rather than the helper.
      name: 'a Python `recv.helper(` attribute call counts as a shared-helper call',
      ok: isSharedHelperCall('gate.assert_contains(', new Set(['assert_contains'])),
    },
    {
      name: 'CONTROL: an attribute call to a name NOT in the set is still counted as code',
      ok: !isSharedHelperCall('gate.something_else(', new Set(['assert_contains'])),
    },
    {
      // THE TIGHTENING'S OWN CONTROL. `harness.py` defines `def result(` and `def record(`, so once the two languages share one name set the loose leading-word test matched
      // the ASSIGNMENT `result = run_gate(...)`. An exclusion that eats an assignment is a
      // silencer, so a call must be a name followed by `(`, by an argument, or by nothing.
      name: 'CONTROL: an assignment whose LHS is a helper NAME is not a helper call',
      ok:
        !isSharedHelperCall('result = run_gate(gate, root)', new Set(['result'])) &&
        !isSharedHelperCall('result  =  1', new Set(['result'])) &&
        isSharedHelperCall('result(1)', new Set(['result'])),
    },
    {
      // CORPUS-DERIVED, not typed: two real tracked gate tests import `rediacc_ci.tests.gates.harness`, so its `def assert_contains(` is shared BY OBSERVATION. If the harness moves or the import spelling changes, this fails.
      name: 'two corpus files importing one module make its defs shared helpers',
      ok: sharedHelperNames([
        '.ci/rediacc_ci/tests/gates/test_gate_age_check.py',
        '.ci/rediacc_ci/tests/gates/test_gate_blocker_validator.py',
      ]).has('assert_contains'),
    },
    {
      // The Python half of the two-user threshold, stated as a control for the same reason the shell half is: the threshold is a definition, not a knob.
      name: 'CONTROL: ONE corpus file importing it does not make them shared',
      ok: !sharedHelperNames(['.ci/rediacc_ci/tests/gates/test_gate_age_check.py']).has(
        'assert_contains'
      ),
    },
    {
      // THE ANTI-SILENCER THAT MATTERS MOST HERE. Every Python gate defines its OWN
      // `main`, and the `if __name__ == "__main__": sys.exit(main())` tail is one of the
      // duplicated shapes this gate is supposed to REPORT. If `main` ever entered the harvested set -- because some shared module defined it and two corpus files imported that module -- the gate would silence the very class it exists to find. Measured 2026-09-08 over the widened corpus: 334 names, `main` not among them.
      name: 'CONTROL: `main` is not a harvested helper, so the entry-point tail stays visible',
      ok: !sharedHelperNames([
        '.ci/rediacc_ci/tests/gates/test_gate_age_check.py',
        '.ci/rediacc_ci/tests/gates/test_gate_blocker_validator.py',
        '.ci/scripts/quality/check_actions_allowlist.py',
        '.ci/scripts/quality/check_allowlist_key_matching.py',
      ]).has('main'),
    },
    {
      name: 'CONTROL: an import preamble is adoption, not duplication',
      ok: (() => {
        const imports = [
          "import a from 'x';",
          "import b from 'y';",
          "import c from 'z';",
          'const R = 1;',
          'const S = 2;',
        ].join('\n');
        return (
          judge(
            new Map(
              Array.from({ length: N }, (_, i): [string, { h: string; line: number }[]] => [
                `f${i}.ts`,
                windows(normalise(imports, 'ts')),
              ])
            ),
            new Set()
          ).length === 0
        );
      })(),
    },
    {
      name: 'CONTROL: but a real span next to imports still fires',
      ok: (() => {
        const mixed = [
          "import a from 'x';",
          'const p = 1;',
          'const q = 2;',
          'const r = 3;',
          'const s = 4;',
          'const t = 5;',
        ].join('\n');
        return (
          judge(
            new Map(
              Array.from({ length: N }, (_, i): [string, { h: string; line: number }[]] => [
                `f${i}.ts`,
                windows(normalise(mixed, 'ts')),
              ])
            ),
            new Set()
          ).length === 1
        );
      })(),
    },
    // THE TOKENIZER CASES, all six written from a real corpus file and all six RED under the four-regex normaliser this replaced on 2026-09-09. The old spelling is quoted in each name so a reader can tell a fixture that would have passed anyway from one that is actually holding the fix down.
    {
      // `const m = "don't";` … 243 lines … `"won't"`. The finding as written.
      name: 'an apostrophe in a double-quoted message does not eat the code after it',
      ok: (() => {
        const n = normalise(
          'const m = "don\'t";\nconst a = 1;\nconst b = 2;\nconst c = 3;\nconst d = "won\'t";',
          'ts'
        );
        // The count is the catastrophe (the old arms returned TWO rows for this input); the text is the ordering, which is what actually fixes it -- the `"` opened first, so the apostrophe inside it is a character and not a quote.
        return n.length === 5 && n[0].text === 'const m = "S";' && n[4].line === 5;
      })(),
    },
    {
      // `scripts/gates/check-unverified-downloads.ts:60`. The worst real case: the apostrophe is in a character class, and the file normalised to 21 of its 318 lines.
      name: 'a quote inside a REGEX literal does not open a string',
      ok:
        normalise(
          "const re = /[^\\s\"'\\\\]+/;\nconst a = 1;\nconst b = 2;\nconst c = 3;\nconst d = /x'y/;",
          'ts'
        ).length === 5,
    },
    {
      // `scripts/gates/check-e2e-coverage.ts:233`: the `*` `/` in a GLOB closed a `/*` opened inside a template literal 27 lines earlier, and the two together cost 139 lines.
      name: 'a comment marker inside a string is not a comment',
      ok:
        normalise(
          "const t = `x /** y`;\nconst a = 1;\nconst g = '**/*.ts';\nconst b = 2;\nconst c = 3;",
          'ts'
        ).length === 5,
    },
    {
      // `.ci/scripts/quality/check-trap-registry.sh:140`, which cost that file 296 of its 394 lines the moment the apostrophe arm stopped eating the region first.
      name: 'a backtick inside a multi-line shell single-quoted block does not eat the file',
      ok: normalise("awk '\n  /^(```+)/ { print }\n' f\na=1\nb=2\nc=`date`", 'sh').length === 6,
    },
    {
      // A LITERAL THAT NEVER CLOSES IS ABANDONED, which is the rule that bounds the blast radius to one line. Let it run past the newline and the next quote four lines down closes it over all the code between, which is the 36582 swallowed newlines.
      name: 'an unterminated quote is abandoned at the newline, not run to the next one',
      ok: normalise('echo "a\nx=1\ny=2\nz=3\necho "b"', 'sh').length === 5,
    },
    {
      // Shell is the one language here where a backslash inside single quotes is a backslash, so `'a\'` is a complete literal followed by a bare `\`. Reading the backslash as an escape swallows the closing quote and pairs it with the NEXT one, which is a different span of the line.
      name: 'a shell single-quoted string takes no escapes',
      ok: normalise("echo 'a\\' 'b'", 'sh')[0]?.text === "echo 'S' 'S'",
    },
    {
      name: 'CONTROL: a TypeScript template literal still spans newlines, as one token',
      ok: (() => {
        const n = normalise('const t = `a\nb\nc`;\nconst x = 1;', 'ts');
        return n.length === 3 && n[0].text === 'const t = `S`' && n[2].line === 4;
      })(),
    },
    {
      name: 'CONTROL: two regexes differing only in their pattern are not the same code',
      ok:
        normalise('const r = /"[a-z]+"/;', 'ts')[0].text !==
        normalise('const r = /"[0-9]+"/;', 'ts')[0].text,
    },
    {
      // The heuristic's failure mode is reading `a / b` as the start of a pattern. It has to know both spellings, because `return /re/.test(x)` is how this very file writes `isMessageish` two hundred lines up.
      name: 'CONTROL: the regex heuristic reads a division as division and a `return /re/` as a regex',
      ok:
        !opensRegex('const q = (a + b) ') &&
        !opensRegex('const q = total ') &&
        opensRegex('  return ') &&
        opensRegex('const r = '),
    },
    {
      name: 'an accepted divergence whose shape has dissolved is reported as dead',
      ok: deadAccepted(mk(N, SPAN), ['deadbeefdead']).length === 1,
    },
    {
      name: 'CONTROL: one that still reaches N copies is not',
      ok: (() => {
        const per = mk(N, SPAN);
        const live = per.get('f0.ts')?.[0]?.h;
        return live !== undefined && deadAccepted(per, [live]).length === 0;
      })(),
    },
    {
      // `--seed` used to write `{generated, files, shapes}` and drop `accepted` on the
      // floor. This asserts the committed artifact still carries both halves, and that a judged hash is never ALSO an anonymous one -- which would double-count it in the success line and hide the reason behind a silent entry.
      name: 'CONTROL: the seed keeps its accepted block, disjoint from the anonymous shapes',
      ok: (() => {
        const raw = JSON.parse(readFileSync(SEED_FILE, 'utf8')) as {
          shapes?: string[];
          accepted?: Record<string, string>;
        };
        const keys = Object.keys(raw.accepted ?? {});
        const shapes = new Set(raw.shapes ?? []);
        return keys.length > 0 && shapes.size > 0 && keys.every((h) => !shapes.has(h));
      })(),
    },
    {
      name: 'CONTROL: a file declaring it stands apart is excluded from the corpus',
      ok: !tracked().some((f) => readFileSync(path.join(ROOT, f), 'utf8').includes(OPT_OUT)),
    },
    // --- the tally and the near index the pre-commit probe reads ------------------
    {
      // `countShapes` is the loop `judge` used to carry inline, and the probe now reaches the same tally by a second entry point. What it must report is the FIRST line in each file, because that coordinate is what a reader opens and what `coalesce` merges on.
      name: 'the tally names every file carrying a shape, at its first line',
      ok: (() => {
        const per = mk(N, SPAN);
        const h = per.get('f0.ts')?.[0]?.h ?? '';
        const files = countShapes(per, new Set()).get(h);
        return files?.size === N && files.get('f0.ts') === 1;
      })(),
    },
    {
      // The seed arm, at the tally rather than at the caller: a seeded shape must not reach the index at all, which is what lets the index be built once and read under whatever seed the probe finds at probe time.
      name: 'CONTROL: a seeded shape never enters the tally',
      ok: (() => {
        const seed = new Set(windows(normalise(SPAN, 'ts')).map((w) => w.h));
        return countShapes(mk(N + 2, SPAN), seed).size === 0;
      })(),
    },
    {
      // THE SELECTION RULE THE INDEX SIZE DEPENDS ON. A staged file contributes at most one copy, so a shape carried by N-1 others is the only kind it can push over the line. Keeping more would carry the long tail of once-only shapes onto the commit path for nothing.
      name: `the near index keeps a shape at ${N - 1} copies, as file:line`,
      ok: (() => {
        const near = nearIndex(mk(N - 1, SPAN));
        const locs = Object.values(near)[0] ?? [];
        return (
          Object.keys(near).length === 1 && locs.length === N - 1 && /^f0\.ts:\d+$/.test(locs[0])
        );
      })(),
    },
    {
      // The anti-bloat direction, and the one that makes the index a fraction of the corpus: a shape ONE file carries stays two short of N with one more copy, so it is not in the index at all.
      name: `CONTROL: a shape carried by ${N - 2} file(s) is not in the near index`,
      ok: Object.keys(nearIndex(mk(N - 2, SPAN))).length === 0,
    },
    {
      // The probe's whole judgement, against a cached neighbour set: two files already agree, a staged third arrives, and the finding names all three.
      name: 'a staged file reaching the Nth copy is a probe finding naming every file',
      ok: (() => {
        const near = nearIndex(mk(N - 1, SPAN));
        const staged = new Map([['staged.ts', windows(normalise(SPAN, 'ts'))]]);
        const found = probeFindings(near, staged, new Set());
        return found.length === 1 && found[0].files.length === N;
      })(),
    },
    {
      // THE DOUBLE-COUNT THIS EXISTS TO REFUSE. A tracked file staged unchanged is ALREADY in the near index, so counting the cached copy and the staged one separately would report N-1 real copies as N. Staging every copy of a shape carried by exactly N-1 files must stay silent.
      name: 'CONTROL: a staged file does not count as a copy of itself',
      ok: (() => {
        const per = mk(N - 1, SPAN);
        const near = nearIndex(per);
        const staged = new Map([...per].map(([f]) => [f, windows(normalise(SPAN, 'ts'))]));
        return probeFindings(near, staged, new Set()).length === 0;
      })(),
    },
    {
      // The seed reaches the probe too, and by the same predicate. A shape silenced for the gate that fired on a commit would be an advisory nobody could satisfy.
      name: 'CONTROL: a seeded shape is silent for the probe as well',
      ok: (() => {
        const near = nearIndex(mk(N - 1, SPAN));
        const staged = new Map([['staged.ts', windows(normalise(SPAN, 'ts'))]]);
        const seed = new Set(windows(normalise(SPAN, 'ts')).map((w) => w.h));
        return probeFindings(near, staged, seed).length === 0;
      })(),
    },
  ];
}

/**
 * Accepted divergences that no longer occur at `N` copies, so they buy nothing.
 *
 * THE SECOND HALF OF A SHRINK-ONLY SET, and it was missing. `checkAccepted` proves the
 * REASON is well formed; nothing proved the FINDING was still there. An entry whose shape
 * was extracted, or whose window changed shape under a normalisation fix, sat on silently
 * for ever, and a set that can only be added to is not shrink-only.
 *
 * Measured on the 2026-09-07 seed while re-keying it: NINE of its 25 accepted entries had
 * ALREADY dissolved -- zero occurrences anywhere in the corpus, under the tokenizer they
 * were written against -- and four more were, by then, excluded mechanically by
 * `isSharedHelperCall`, which is the very argument three of their BLOCKERs make by hand.
 * Thirteen of 25 were buying nothing and no run said so.
 *
 * Pure and exported for the same reason as `checkAccepted`: a control that drives a
 * reimplementation proves nothing.
 */
export function deadAccepted(
  perFile: Map<string, { h: string; line: number }[]>,
  accepted: readonly string[]
): string[] {
  const copies = new Map<string, Set<string>>();
  for (const [file, ws] of perFile) {
    for (const w of ws) {
      let f = copies.get(w.h);
      if (!f) copies.set(w.h, (f = new Set()));
      f.add(file);
    }
  }
  return accepted.filter((h) => (copies.get(h)?.size ?? 0) < N);
}

/**
 * The pure half of the `accepted` check, split out so the controls drive the REAL
 * validation rather than a reimplementation of it -- the same reason `normalise`, `windows`
 * and `judge` are exported.
 */
export function checkAccepted(accepted: Record<string, string>): {
  ok: string[];
  bad: string[];
} {
  const ok: string[] = [];
  const bad: string[] = [];
  for (const [h, reason] of Object.entries(accepted)) {
    if (!/^BLOCKER:/i.test(reason)) {
      bad.push(`  ${h}: reason does not start with "BLOCKER:"`);
      continue;
    }
    const fail = validateBlockerQuality(h, reason.replace(/^BLOCKER:\s*/i, ''), SEED_FILE);
    if (fail) bad.push(fail.message);
    else ok.push(h);
  }
  return { ok, bad };
}

/**
 * The silence set: the standing backlog PLUS the shapes a person judged not one thing.
 *
 * THE SECOND HALF IS AN EXIT THIS GATE DID NOT HAVE, and its absence was a real defect
 * rather than a missing nicety. The judged rule next door (`wl_shapedup.py`) has three
 * answers -- yes, already, and `no` with a named DIVERGENCE -- because `run_gate()` really
 * is duplicated 23 times across three incompatible return contracts and extracting it
 * verbatim would be wrong. This gate had only two: consolidate, or stay red forever. The
 * only way out was re-running `--seed`, which absorbs EVERY new shape at once, so the sole
 * exit from a legitimate divergence was a command that silently suppresses the whole gate.
 *
 * So `accepted` is the repo's ordinary escape hatch, held to the ordinary rule: a
 * `BLOCKER:` reason, validated by the SAME `validateBlockerQuality` every other allowlist
 * uses (30-char minimum, banned-phrase list). Writing a second reason-checker here is the
 * exact duplication this gate exists to catch.
 *
 * `shapes` carries no reasons and should not: it is one measurement taken at install, the
 * same shape as `wl_reggate.py:130` hashing every existing check script so only new ones
 * count. `accepted` is per-entry judgement, and judgement is what needs a reason.
 */
function loadSeed(): { silent: Set<string>; accepted: string[] } {
  if (!existsSync(SEED_FILE)) return { silent: new Set(), accepted: [] };
  const raw = JSON.parse(readFileSync(SEED_FILE, 'utf8')) as {
    shapes?: string[];
    accepted?: Record<string, string>;
  };
  const silent = new Set(raw.shapes ?? []);
  const { ok, bad } = checkAccepted(raw.accepted ?? {});
  for (const h of ok) silent.add(h);
  if (bad.length > 0) {
    console.error(`${RED}✗${NC} ${bad.length} accepted divergence(s) carry no usable BLOCKER:`);
    for (const b of bad) console.error(b);
    process.exit(1);
  }
  // THE IDS, not a count, because the caller has to prove each one is still LIVE. Returning the number was enough while the only question was "how many are silent"; it is not enough to answer "is this entry still buying anything", which is the half that makes the set shrink.
  return { silent, accepted: ok };
}

// --------------------------------------------------------------------------- THE CACHED INDEX, AND THE PROBE THAT READS IT ---------------------------------------------------------------------------
//
// WHY A BUNDLE AND NOT A SECOND IMPLEMENTATION. A pre-commit probe has to hash the STAGED bytes of a file, which means running `normalise`, `stripNoise` and `windows` over them. A Python guard that reimplemented those would be a second implementation of one decision, which is the class of defect this whole file exists to count -- and `isSharedHelperCall` derives its name set from
// the WHOLE corpus, so the normalisation cannot be ported by reading a regex. So `--emit-index` bundles this file with esbuild and writes the bundle beside the index it was measured with; the guard spawns it. One implementation, two entry points, and the only thing left to disagree is the cache contents, which `.ci/rediacc_ci/tests/test_shape_probe_agreement.py` pins.
//
// WHAT THE PROBE IS ALLOWED TO ASSUME, measured rather than hoped: the full corpus scan is about 1.2s over 352 files and never belongs on a commit, while an esbuild bundle of this file starts in well under a tenth of a second. The gate fires at 3 distinct files, so the index keeps only the shapes ALREADY carried by 2 or more -- a staged file can only matter where two other
// files already agree.

/** The index format. A probe that reads an older shape must refuse rather than guess, so this is checked before anything else in it is trusted. */
export const INDEX_SCHEMA = 1;

const CACHE_REL = '.ci/cache/shape-index';

/** Where the index and its probe live. `SHAPE_PROBE_CACHE` is for a test that must not touch the real one. */
function cacheDir(): string {
  return process.env.SHAPE_PROBE_CACHE || path.join(ROOT, CACHE_REL);
}

/**
 * The shapes a STAGED file could push over the line, as `file:line` per copy.
 *
 * `N - 1` IS THE WHOLE SELECTION RULE. A finding needs N distinct files; a staged file contributes at most one of them, so a shape carried by fewer than N-1 others stays silent however the staged file is written. Keeping the rest would multiply the index by the long tail of shapes that occur exactly once, which is most of them.
 *
 * The seed is deliberately NOT applied: the probe reads the seed at probe time, so a seed edit does not have to invalidate the cache.
 */
export function nearIndex(
  perFile: Map<string, { h: string; line: number }[]>
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [h, files] of countShapes(perFile, new Set())) {
    if (files.size < N - 1) continue;
    out[h] = [...files].map(([f, l]) => `${f}:${l}`).sort();
  }
  return out;
}

/** `file:line` back into its two halves, splitting at the LAST colon so a path carrying one survives. */
function splitLoc(loc: string): { file: string; line: number } {
  const cut = loc.lastIndexOf(':');
  return { file: loc.slice(0, cut), line: Number(loc.slice(cut + 1)) };
}

/**
 * The findings a set of staged files creates against the cached corpus.
 *
 * THE STAGED FILE IS REMOVED FROM ITS OWN NEIGHBOURS, and that is what makes the answer equal the gate's. A tracked file staged unchanged already appears in `near`, so counting it twice would report a 2-copy shape as a 3-copy one. Dropping every staged path from the cached list and then adding the staged version back is the same tally `judge` computes over a corpus where that
 * file has been replaced.
 *
 * Exported and pure, so the agreement test and the controls drive the real judgement rather than a reimplementation.
 */
export function probeFindings(
  near: Record<string, string[]>,
  staged: Map<string, { h: string; line: number }[]>,
  seed: Set<string>
): Finding[] {
  const byShape = new Map<string, Map<string, number>>();
  for (const [file, ws] of staged) {
    for (const w of ws) {
      if (seed.has(w.h)) continue;
      let m = byShape.get(w.h);
      if (!m) {
        m = new Map();
        for (const loc of near[w.h] ?? []) {
          const { file: other, line } = splitLoc(loc);
          if (!staged.has(other)) m.set(other, line);
        }
        byShape.set(w.h, m);
      }
      if (!m.has(file)) m.set(file, w.line);
    }
  }
  const findings: Finding[] = [];
  for (const [h, files] of byShape) {
    if (files.size < N) continue;
    findings.push({
      shape: h,
      files: [...files].map(([f, l]) => `${f}:${l}`).sort(),
      span: WINDOW,
    });
  }
  return coalesce(findings);
}

/**
 * The silence set, read the way a PROBE has to read it: leniently.
 *
 * `loadSeed` exits the process when an `accepted` reason is malformed, which is right for a gate whose job is to refuse and wrong for an advisory that must never fail a commit. The two agree on every tree where the gate passes, which is the only tree a commit is made on; a tree where they differ is one the gate is already red on.
 */
function seedSilently(): Set<string> {
  if (!existsSync(SEED_FILE)) return new Set();
  try {
    const raw = JSON.parse(readFileSync(SEED_FILE, 'utf8')) as {
      shapes?: string[];
      accepted?: Record<string, string>;
    };
    return new Set([...(raw.shapes ?? []), ...Object.keys(raw.accepted ?? {})]);
  } catch {
    return new Set();
  }
}

interface EsbuildLike {
  build(options: Record<string, unknown>): Promise<{
    outputFiles: { path: string; text: string }[];
    metafile: { inputs: Record<string, unknown> };
  }>;
}

/**
 * esbuild, from `tsx`'s OWN dependency tree.
 *
 * NOT A NEW DEPENDENCY, and that is deliberate: `.npmrc` pins this repo's supply chain, and a bundler is already installed here because `tsx` is built on one. Resolving through `tsx/package.json` rather than through this file's own resolution is what makes that explicit -- the version that bundles the probe is the version that already runs every gate.
 */
async function resolveEsbuild(): Promise<EsbuildLike> {
  // RESOLVED FROM THIS FILE, not from `ROOT`. `--root` points the scan at another tree -- the hermetic harness builds an index over a generated corpus -- and that tree has no `node_modules`. The bundler belongs to the checkout this script lives in, which is the one that installed it.
  const fromHere = createRequire(import.meta.url);
  let tsxPkg: string;
  try {
    tsxPkg = fromHere.resolve('tsx/package.json');
  } catch {
    throw new Error(
      'tsx is not resolvable from this repository, so the probe bundle cannot be built. ' +
        'Run npm install; do not add a bundler dependency for this.'
    );
  }
  let entry: string;
  try {
    entry = createRequire(tsxPkg).resolve('esbuild');
  } catch {
    throw new Error(
      `esbuild is not resolvable from tsx's dependency tree (${tsxPkg}), so the probe ` +
        'bundle cannot be built. That is a report, not a licence to add a dependency.'
    );
  }
  const mod = (await import(pathToFileURL(entry).href)) as { default?: EsbuildLike };
  return (mod.default ?? mod) as EsbuildLike;
}

const sha256 = (s: string) => createHash('sha256').update(s).digest('hex');

/** Write through a temporary name in the same directory, so a reader never sees half a file. */
function writeAtomic(target: string, body: string): void {
  const tmp = `${target}.tmp-${process.pid}`;
  writeFileSync(tmp, body);
  renameSync(tmp, target);
}

/**
 * Write `index.json` and `probe.mjs` from the scan that just ran.
 *
 * THE TWO FILES ARE ONE ARTIFACT. The index records the sha256 of every source the bundle was built from and of the bundle itself, and the guard refuses to trust an index whose bundle or inputs have moved: an algorithm change that rewrote every hash would otherwise be read as a tree full of new duplication.
 */
async function emitIndex(
  files: string[],
  perFile: Map<string, { h: string; line: number }[]>,
  helpers: ReadonlySet<string>
): Promise<void> {
  const esbuild = await resolveEsbuild();
  const dir = cacheDir();
  const probePath = path.join(dir, 'probe.mjs');
  const built = await esbuild.build({
    entryPoints: [path.join(ROOT, 'scripts/gates/check-shape-duplication.ts')],
    absWorkingDir: ROOT,
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node22',
    metafile: true,
    write: false,
    outfile: probePath,
  });
  const code = built.outputFiles[0].text;
  const inputs: Record<string, string> = {};
  for (const rel of Object.keys(built.metafile.inputs).sort()) {
    inputs[rel] = sha256(readFileSync(path.join(ROOT, rel), 'utf8'));
  }
  // `git ls-files -s` over the family pathspecs: the blob sha of every tracked corpus path, INCLUDING the opted-out ones. A path that appears, disappears or changes content between the scan and a commit is drift, and the guard says so rather than answering from a corpus that no longer exists.
  const corpus: Record<string, string> = {};
  for (const row of execFileSync('git', ['ls-files', '-s', ...FAMILY_PATHSPECS], {
    cwd: ROOT,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean)) {
    const tab = row.indexOf('\t');
    corpus[row.slice(tab + 1)] = row.slice(0, tab).split(' ')[1];
  }
  const scanned = new Set(files);
  const index = {
    schema: INDEX_SCHEMA,
    generated: new Date().toISOString(),
    n: N,
    window: WINDOW,
    pathspecs: FAMILY_PATHSPECS,
    advice: ADVICE,
    bundle_sha: sha256(code),
    inputs,
    corpus,
    opted_out: Object.keys(corpus)
      .filter((f) => !scanned.has(f))
      .sort(),
    helpers: [...helpers].sort(),
    near: nearIndex(perFile),
  };
  mkdirSync(dir, { recursive: true });
  writeAtomic(probePath, code);
  writeAtomic(path.join(dir, 'index.json'), `${JSON.stringify(index)}\n`);
  // STDERR, because `--json` is a contract. `wl_shapedup.py` reads the LAST stdout line that starts with `{`, so a status line printed to stdout would either be parsed as the verdict or teach the next reader to filter.
  console.error(
    `${GREEN}✓${NC} shape index: ${Object.keys(index.near).length} near-shape(s) from ` +
      `${files.length} file(s) -> ${path.relative(ROOT, dir)}`
  );
}

/**
 * The bundled entry point: staged bytes in on stdin, findings out on stdout.
 *
 * The request is `{root, index, files: {path: content}, noSeed}`. The CONTENT arrives in the request rather than being read here, because the bytes a commit captures live in git's index and the guard has already had to resolve them; a probe that read the working tree would answer about a file the commit is not taking.
 */
/**
 * stdin, drained synchronously.
 *
 * `readFileSync(0)` IS NOT THIS, and the difference is a measured failure rather than a preference: when the parent hands over a pipe, node's fd 0 can be non-blocking, and the one-shot read then throws `EAGAIN: resource temporarily unavailable` before the writer has said anything. The probe saw it on its first run under the Python guard. A retry loop is what a synchronous
 * reader of a pipe has to be; `Atomics.wait` is the only sleep available to one.
 */
function readStdinSync(): string {
  const chunks: Buffer[] = [];
  const buf = Buffer.alloc(1 << 16);
  const idle = new Int32Array(new SharedArrayBuffer(4));
  for (;;) {
    let n = 0;
    try {
      n = readSync(0, buf, 0, buf.length, null);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code === 'EAGAIN') {
        Atomics.wait(idle, 0, 0, 1);
        continue;
      }
      // EOF on a tty, and the end of a pipe on some platforms, arrive as an exception rather than as a zero-length read.
      if (code === 'EOF') break;
      throw err;
    }
    if (n === 0) break;
    chunks.push(Buffer.from(buf.subarray(0, n)));
  }
  return Buffer.concat(chunks).toString('utf8');
}

function probeMain(): void {
  const req = JSON.parse(readStdinSync()) as {
    root: string;
    index: string;
    files: Record<string, string>;
    noSeed?: boolean;
  };
  setRoot(req.root);
  const index = JSON.parse(readFileSync(req.index, 'utf8')) as {
    schema: number;
    helpers: string[];
    near: Record<string, string[]>;
  };
  if (index.schema !== INDEX_SCHEMA) {
    process.stdout.write(
      JSON.stringify({
        error: `index schema ${index.schema} is not ${INDEX_SCHEMA}`,
      })
    );
    return;
  }
  const helpers = new Set(index.helpers);
  const seed = req.noSeed ? new Set<string>() : seedSilently();
  const staged = new Map<string, { h: string; line: number }[]>();
  const skipped: string[] = [];
  for (const [file, src] of Object.entries(req.files)) {
    // The opt-out is a property of the STAGED bytes, not of the tracked file: a commit that adds the marker is a commit whose file has opted out.
    if (isOptedOut(src)) {
      skipped.push(file);
      continue;
    }
    staged.set(file, windows(normalise(src, kindFor(file)), helpers));
  }
  process.stdout.write(
    JSON.stringify({ findings: probeFindings(index.near, staged, seed), skipped })
  );
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);

  // THE PROBE IS THE SAME FILE, entered before anything scans. `probe.mjs` is this module bundled, so its `import.meta` points at the cache directory and `process.argv[1]` at the bundle: the entry-point guard at the foot of this file matches, and without this branch a probe run would start a 1.2-second corpus scan on the commit path.
  if (argv.includes('--probe')) {
    probeMain();
    return;
  }

  const rootAt = argv.indexOf('--root');
  if (rootAt >= 0 && argv[rootAt + 1]) setRoot(argv[rootAt + 1]);

  if (argv.includes('--selftest')) {
    const failed = runControls(controls());
    if (failed > 0) {
      console.error(`${RED}✗${NC} a control did not behave, so this gate cannot be trusted`);
      process.exit(1);
    }
  }

  const files = tracked();
  const { perFile, helpers } = scan(files);

  // FLOORS. Either means the scan is broken, and a broken scan reports a confident green having verified nothing -- the exact failure this repo gates against.
  if (files.length < 200) {
    console.error(
      `${RED}✗${NC} only ${files.length} file(s) in the corpus; the globs are broken or the tree moved`
    );
    process.exit(1);
  }
  const totalWindows = [...perFile.values()].reduce((n, w) => n + w.length, 0);
  if (totalWindows < 5000) {
    console.error(`${RED}✗${NC} only ${totalWindows} window(s) hashed; normalisation is broken`);
    process.exit(1);
  }

  // AFTER THE FLOORS AND NOT BEFORE, which is the whole reason the cache can be trusted. The floors are what stand between a broken glob and a confident green, so an index written ahead of them would be a cache of the broken scan -- and the guard reading it would report silence with the same confidence.
  if (argv.includes('--emit-index')) await emitIndex(files, perFile, helpers);

  if (argv.includes('--seed')) {
    // RE-SEEDING IS GATE SUPPRESSION, so it is not a routine command. A second `--seed` absorbs every shape that has reached N copies since install -- including the genuine duplication this gate exists to report -- and leaves no record that it did. The exit for a shape that is legitimately not one thing is `accepted` with a BLOCKER, one entry at a time, which is reviewable. This
    // refuses rather than warns.
    if (existsSync(SEED_FILE) && !argv.includes('--force')) {
      console.error(
        `${RED}✗${NC} a seed already exists at ${SEED_FILE}.\n` +
          '    Re-seeding silences every shape that reached N copies since install, with no\n' +
          '    record of what was silenced. To accept ONE shape as legitimately divergent,\n' +
          '    add it to `accepted` with a BLOCKER reason instead. --force overrides.'
      );
      process.exit(1);
    }
    // ONLY the shapes that have ALREADY reached N copies. Seeding every hash in the tree was the first attempt and it is wrong twice over: a 708 KB artifact, and -- the part that matters -- it would suppress a line that exists ONCE today and gets copied twice tomorrow. That is new duplication, exactly what this gate is for, and it would have been silenced forever. Seeding the
    // standing backlog and nothing else keeps the 1 -> 2 -> 3 transition live.
    const shapes = new Set<string>();
    const counts = new Map<string, Set<string>>();
    for (const [file, ws] of perFile) {
      for (const w of ws) {
        let f = counts.get(w.h);
        if (!f) counts.set(w.h, (f = new Set()));
        f.add(file);
      }
    }
    for (const [h, f] of counts) if (f.size >= N) shapes.add(h);
    // `accepted` SURVIVES A RESEED, and its loss was a real defect rather than a gap in
    // this comment. The writer used to emit `{generated, files, shapes}` and nothing else,
    // so a single `--seed --force` DELETED all 25 hand-written BLOCKER reasons and folded the shapes they described into the anonymous backlog bucket -- the exact difference this file's own docstring draws between "one measurement taken at install" and "per-entry judgement". Silently, with no diff a reader would read as a loss.
    const keep = existsSync(SEED_FILE)
      ? ((JSON.parse(readFileSync(SEED_FILE, 'utf8')) as { accepted?: Record<string, string> })
          .accepted ?? {})
      : {};
    // An accepted shape must not ALSO sit in `shapes`, or the success line's `seed.size - accepted` arithmetic double-counts it and the judgement is hidden behind an anonymous entry that silences the same hash.
    for (const h of Object.keys(keep)) shapes.delete(h);
    writeFileSync(
      SEED_FILE,
      `${JSON.stringify({ generated: new Date().toISOString().slice(0, 10), files: files.length, shapes: [...shapes].sort(), accepted: keep }, null, 2)}\n`
    );
    console.log(
      `seeded ${shapes.size} shape(s) from ${files.length} file(s), ` +
        `keeping ${Object.keys(keep).length} accepted divergence(s) -> ${SEED_FILE}`
    );
    return;
  }

  // `--no-seed` IS FOR THE AGREEMENT TEST AND NOTHING ELSE, and it is not an escape hatch: it makes the gate report the 219-span standing backlog this file's docstring describes, which is a wall rather than a verdict. What it buys is a comparison -- the probe answers about a staged file against a cached corpus, and the only way to check that answer is to ask the whole-corpus scan
  // the same question with the same silence set, which for a single staged file is no silence at all.
  const noSeed = argv.includes('--no-seed');
  const { silent: seed, accepted } = noSeed
    ? { silent: new Set<string>(), accepted: [] }
    : loadSeed();
  if (!noSeed && seed.size === 0) {
    console.error(`${RED}✗${NC} no seed at ${SEED_FILE}; run --seed once, and commit it.`);
    console.error('    Without it every pre-existing shape reports as new.');
    process.exit(1);
  }

  // LIVENESS, BEFORE THE VERDICT. An accepted entry that no longer occurs at N copies is debt that was already paid, and leaving it in place is how an escape-hatch list stops shrinking. This fails rather than warns, and names the exact lines to delete.
  const dead = noSeed ? [] : deadAccepted(perFile, accepted);
  if (dead.length > 0) {
    console.error(
      `${RED}✗${NC} ${dead.length} accepted divergence(s) no longer occur at ${N} copies:`
    );
    for (const h of dead) console.error(`    ${h}`);
    console.error(
      `\n  The shape they excuse is gone, so the reason is no longer true and the entry is` +
        `\n  buying silence for nothing. DELETE those keys from` +
        `\n  scripts/data/shape-duplication-seed.json under "accepted". Do not re-seed to` +
        `\n  clear them: --seed rewrites every anonymous entry at once and would absorb any` +
        `\n  genuinely new duplication in the same stroke.`
    );
    process.exit(1);
  }

  const findings = judge(perFile, seed);

  // MACHINE-READABLE, for the stop-hook rule that asks the judged half of this question. `wl_shapedup.py` needs the file:line spans as data; parsing them back out of the human report would be a second, undeclared interface to the same answer.
  if (argv.includes('--json')) {
    console.log(JSON.stringify({ n: N, window: WINDOW, seeded: seed.size, findings }));
    return;
  }

  if (findings.length > 0) {
    console.error(`${RED}✗${NC} ${findings.length} NEW shape(s) have reached ${N} copies:\n`);
    for (const f of findings) {
      console.error(`  ~${f.span} lines x ${f.files.length} copies:  ${f.shape}`);
      for (const loc of f.files) console.error(`    ${loc}`);
    }
    console.error(ADVICE);
    process.exit(1);
  }

  console.log(
    `${GREEN}✓${NC} shape duplication: ${files.length} file(s), ${totalWindows} window(s), ` +
      `${seed.size - accepted.length} seeded + ${accepted.length} accepted shape(s); ` +
      `no NEW shape has reached ${N} copies`
  );
}

// ENTRY-POINT GUARD, and it is not decoration. This module exports `normalise`, `windows`, `judge` and `coalesce` so a consumer can drive the REAL judgement rather than a reimplementation -- and until this line existed, importing any of them ran a full 320-file scan as a side effect and printed the gate's verdict. Found by doing exactly that from the calibration replay.
//
// The other 23 `scripts/gates/check-*.ts` that both export and call `main()` bare are left alone deliberately: swept 2026-09-01, NONE of them is imported anywhere (the apparent hits in `ci-runner/manifest.ts` are script-name strings, not imports). This one is the only member of the class with a consumer, so it is the only one where the defect is live rather than latent.
if (process.argv[1] && import.meta.filename === path.resolve(process.argv[1])) {
  // `main` BECAME ASYNC when `--emit-index` did, so the rejection has to be caught here: an unhandled rejection exits non-zero with a stack and no sentence, and this gate's contract is that a failure names what broke.
  main().catch((err: unknown) => {
    console.error(`${RED}✗${NC} ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
}
