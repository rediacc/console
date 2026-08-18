#!/usr/bin/env tsx
/**
 * Em dashes in the www surfaces that no gate was looking at.
 *
 * WHY THIS EXISTS. `.ci/scripts/quality/check-content-quality.sh` bans U+2014, and it has
 * banned it for a long time. It scans `packages/www/src/content/{docs,blog}` for `*.md`
 * and `*.mdx` and nothing else (see its CONTENT_DIRS). Every other surface the site
 * renders text from was outside it: the 13 locale catalogs, and every `.astro` and `.tsx`
 * component. The measured hole is 2,401 locale values carrying an em dash (ru 374,
 * ar 251, de 243, tr 243, en 84), which is roughly two orders of magnitude more than the
 * markdown gate has ever had to report. A ban that covers the smallest surface and misses
 * the largest is not a ban, and nothing in the output said so: the markdown scan was
 * genuinely clean, so the gate printed a checkmark that was true about the files it read
 * and false about the site.
 *
 * WHY A SEPARATE FILE RATHER THAN A WIDER CONTENT_DIRS. Two reasons, both practical.
 * The markdown gate is a line-oriented bash scanner with a `<!-- slop-ok -->` inline
 * suppression and a per-file allowlist; a JSON catalog has neither lines worth naming nor
 * anywhere to put a comment, so its findings need KEY PATHS, and its backlog needs a
 * shrink-only baseline rather than an allowlist that can grow. Bolting a baseline onto
 * the bash gate would have given this repo a second suppression mechanism inside a file
 * that already has two.
 *
 * THE BASELINE ONLY SHRINKS, exactly as in scripts/check-locale-de-contamination.ts.
 * Known findings are recorded so the gate lands green over the backlog and fails on
 * anything NEW; a baselined finding that has been fixed must be REMOVED, or the gate
 * fails too. Baselining a fresh finding is not the fix and the diagnostic says so.
 *
 * Usage:
 *   tsx scripts/check-em-dash-surfaces.ts [--root <dir>] [--baseline <file>]
 *   tsx scripts/check-em-dash-surfaces.ts --write-baseline   (drain/reseed)
 *   tsx scripts/check-em-dash-surfaces.ts --selftest
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { flatten } from './lib/language-detect.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_BASELINE = 'scripts/data/em-dash-surfaces-baseline.json';

/** U+2014. Deliberately just this one: the en dash U+2013 is a different argument. */
const EM_DASH = '—';

/**
 * The surfaces scanned, and the shape each one reports findings in.
 *
 * `catalog` -- a locale JSON file. Findings are KEY PATHS, which survive reformatting and
 *   reordering, so a baseline entry does not churn when a neighbouring key changes.
 * `source`  -- an `.astro` or `.tsx` file. Findings are the file plus a short hash of the
 *   offending line's trimmed text. A LINE NUMBER would have been the obvious id and is
 *   the wrong one: inserting a paragraph above shifts every id below it, and a baseline
 *   that churns on unrelated edits gets regenerated wholesale, which silently re-absorbs
 *   fresh findings. Hashing the text means an entry survives a move and dies when the
 *   text is actually rewritten, which is exactly when it should be re-examined.
 */
interface Surface {
  dir: string;
  kind: 'catalog' | 'source' | 'markdown';
  exts: string[];
  /** Per-surface floor. See PER-SURFACE FLOORS below for why one global floor is not enough. */
  minFiles: number;
}

const SURFACES: readonly Surface[] = [
  // 13 locales today; the floor sits below that so it catches a collapsed glob, not a
  // deliberate locale change. The two `.`-prefixed hash sidecars in this directory are
  // skipped by the walker, which is why the real count is 13 and not the 15 `find` reports.
  { dir: 'packages/www/src/i18n/translations', kind: 'catalog', exts: ['.json'], minFiles: 10 },
  { dir: 'packages/www/src', kind: 'source', exts: ['.astro', '.tsx'], minFiles: 50 },
  { dir: '.claude/commands', kind: 'markdown', exts: ['.md'], minFiles: 3 },
  { dir: '.claude/agents', kind: 'markdown', exts: ['.md'], minFiles: 8 },
  { dir: '.claude/hooks', kind: 'source', exts: ['.sh', '.py'], minFiles: 20 },
];

/**
 * WHY `.claude/` JOINED, AND WHY AT ZERO RATHER THAN ON A BASELINE.
 *
 * The no-em-dash rule is a standing instruction to every session, and the two surfaces
 * that instruct sessions were outside the only gate enforcing it: `.claude/commands`
 * carried 57 and `.claude/hooks` carried 20. A rule whose own statement breaks the rule
 * teaches the opposite of what it says, and nothing reported it because the gate's
 * surface table stopped at packages/www.
 *
 * Both were fixed to zero before joining, deliberately. Baselining 77 findings would have
 * inverted the gate's purpose here: on a surface this small the backlog IS the content,
 * so a baseline would have recorded "these instructions may break the rule" permanently.
 *
 * NOT JOINED, and each for a measured reason:
 *   `.claude/agents`   JOINED, also at zero. Its single finding sits inside a fenced code
 *                      block, so fence-aware scanning made it free. It is the surface
 *                      where the rule matters most: these files instruct future sessions,
 *                      and an instruction that breaks the rule it states teaches the
 *                      opposite of what it says.
 *   `.claude/skills`   103 prose findings once fenced blocks are excluded, down from 627
 *                      before the generator fix below. Still not zero, so it waits. Of the
 *                      original count, 516 came from `rdc/reference.md`, which is
 *                      AUTO-GENERATED by packages/cli/scripts/generate-skill-reference.ts.
 *                      The fix there is the generator's option-description template, not
 *                      the file; joining the surface before fixing the generator would
 *                      bake a generated artifact into a hand-drained baseline.
 *   `agent/programs`   704 findings across PEER SESSIONS' directories, which this session
 *                      reads and never writes.
 */

/**
 * PER-SURFACE FLOORS, replacing the single global floor this gate used to carry.
 *
 * The old floor was one number over the sum of every surface. That works while all the
 * surfaces are the same order of magnitude and silently stops working the moment a small
 * one joins: `.claude/commands` holds 4 files, so if its glob broke to zero the total
 * would still be ~180 and the gate would report a clean scan of a directory it never
 * opened. That is this gate's own founding defect, one level up, which is why the floor
 * is now per surface and is asserted in the selftest rather than trusted.
 */

/**
 * THE CATALOG SURFACE IS `translations/` AND MUST NOT BE WIDENED TO `src/i18n/`.
 *
 * Wave 1 added `src/i18n/client/` and `src/i18n/client-route/` -- thirteen JSON catalogs
 * each, GENERATED from `translations/` and committed as build artifacts. They are siblings
 * of the source catalogs, so widening the surface by one directory level is a one-character
 * edit that looks like better coverage and is not: every finding would be counted two or
 * three times, and `--write-baseline` would then bake those duplicates in, where
 * shrink-only draining can never fully clear them (fixing one source value would retire
 * three baseline ids at once and the arithmetic stops meaning anything).
 *
 * The coverage is not lost by staying narrow. A generated catalog can only carry an em
 * dash that its source carries -- today `client/et.json` and `client/ru.json` do, copied
 * verbatim -- so fixing the value in `translations/` clears every copy at once. Freshness
 * of the generated copies is `check:ci-client-i18n`'s job, not this gate's.
 *
 * This is enforced rather than remembered, in the selftest below.
 */
const GENERATED_CATALOG_DIRS = ['client', 'client-route'];

/**
 * Surfaces that joined the gate at ZERO. No id from one of these may EVER enter the
 * baseline.
 *
 * Without this the zero-join is only a comment. `--write-baseline` rewrites every finding
 * from every surface, so a session that reintroduced an em dash into `.claude/commands`
 * and then reseeded the baseline for an unrelated reason would bake the regression in
 * silently, and the prose above would go on claiming the surface was at zero. A property
 * asserted only in a comment is not a property, it is a hope, which is the exact failure
 * class this gate exists to end.
 *
 * A surface belongs here when its backlog was DRAINED before it joined, so "zero" is its
 * real state rather than an aspiration. `packages/www` is not and cannot be on this list:
 * it joined with 1,924 known findings.
 */
const ZERO_SURFACES: readonly string[] = ['.claude/commands', '.claude/hooks', '.claude/agents'];

/** Is this finding's file inside a surface that is supposed to be at zero? */
const inZeroSurface = (file: string): boolean =>
  ZERO_SURFACES.some((dir) => file === dir || file.startsWith(`${dir}/`));

interface Finding {
  file: string;
  where: string;
  excerpt: string;
}

const idOf = (f: Finding): string => `${f.file}:${f.where}`;

const shortHash = (s: string): string =>
  crypto.createHash('sha1').update(s).digest('hex').slice(0, 12);

function walk(dir: string, exts: string[], out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.')) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, exts, out);
    else if (exts.some((e) => entry.name.endsWith(e))) out.push(abs);
  }
  return out;
}

const excerpt = (s: string): string => {
  const at = s.indexOf(EM_DASH);
  const from = Math.max(0, at - 40);
  const slice = s
    .slice(from, at + 40)
    .replace(/\s+/g, ' ')
    .trim();
  return `${from > 0 ? '...' : ''}${slice}${at + 40 < s.length ? '...' : ''}`;
};

export function scanSurface(
  root: string,
  surface: { dir: string; kind: 'catalog' | 'source'; exts: string[] }
): { findings: Finding[]; files: number } {
  const abs = path.join(root, surface.dir);
  const files = walk(abs, surface.exts);
  const findings: Finding[] = [];

  for (const file of files) {
    const rel = path.relative(root, file);
    const text = fs.readFileSync(file, 'utf-8');
    if (!text.includes(EM_DASH)) continue;

    if (surface.kind === 'catalog') {
      let flat: Record<string, string>;
      try {
        flat = flatten(JSON.parse(text));
      } catch (e) {
        // A malformed catalog is check-translation-completeness's problem, not this
        // gate's. Anything else is a bug HERE, and swallowing it would make this file
        // report zero findings while looking healthy.
        if (e instanceof SyntaxError) continue;
        throw e;
      }
      for (const [key, value] of Object.entries(flat)) {
        if (value.includes(EM_DASH))
          findings.push({ file: rel, where: key, excerpt: excerpt(value) });
      }
      continue;
    }

    // A fenced block in an instruction file is a transcript or a sample, and a dash inside
    // one is usually quoted from somewhere this repo does not control. Prose is the surface
    // the rule is about. The selftest proves this BOTH ways: silence inside a fence is only
    // correct if the same text outside one is still reported.
    if (surface.kind === 'markdown') {
      let inFence = false;
      for (const line of text.split('\n')) {
        if (line.trimStart().startsWith('```')) {
          inFence = !inFence;
          continue;
        }
        if (inFence || !line.includes(EM_DASH)) continue;
        findings.push({ file: rel, where: shortHash(line.trim()), excerpt: excerpt(line) });
      }
      continue;
    }

    for (const line of text.split('\n')) {
      if (!line.includes(EM_DASH)) continue;
      findings.push({ file: rel, where: shortHash(line.trim()), excerpt: excerpt(line) });
    }
  }
  return { findings, files: files.length };
}

/**
 * Surfaces whose file count came in under their own floor. Exported ONLY so the selftest
 * can drive it: a floor nothing ever exercises is a comment, not a control.
 */
export function floorViolations(root: string, surfaces: readonly Surface[] = SURFACES): string[] {
  const out: string[] = [];
  for (const s of surfaces) {
    const n = scanSurface(root, s).files;
    if (n < s.minFiles) out.push(`${s.dir}: found ${n} file(s), floor is ${s.minFiles}`);
  }
  return out;
}

function loadBaseline(file: string): string[] {
  if (!fs.existsSync(file)) return [];
  const parsed: unknown = JSON.parse(fs.readFileSync(file, 'utf-8'));
  if (!Array.isArray(parsed)) throw new Error(`${file} must contain a JSON array of finding ids.`);
  return parsed.map(String);
}

/**
 * CONTROL. Plant an em dash in each surface shape and require both to be reported, then
 * plant a clean file of each shape and require silence.
 *
 * Runs inline on every invocation. The whole reason this gate exists is that another one
 * was reporting a clean scan of the wrong files; a fire-proof that only runs behind a
 * flag would be the same defect one level up.
 */
function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'em-dash-'));
  const catalogDir = path.join(root, 'packages/www/src/i18n/translations');
  const srcDir = path.join(root, 'packages/www/src/components');
  fs.mkdirSync(catalogDir, { recursive: true });
  fs.mkdirSync(srcDir, { recursive: true });

  fs.writeFileSync(
    path.join(catalogDir, 'en.json'),
    JSON.stringify({ hero: { title: 'Recovery in seconds, not hours' } })
  );
  fs.writeFileSync(path.join(srcDir, 'Hero.astro'), '<h1>Recovery in seconds, not hours</h1>\n');

  const scanAll = () => SURFACES.flatMap((s) => scanSurface(root, s).findings);
  check('a clean catalog and a clean component report nothing (control)', scanAll().length === 0);

  fs.writeFileSync(
    path.join(catalogDir, 'de.json'),
    JSON.stringify({ hero: { title: `Wiederherstellung in Sekunden ${EM_DASH} nicht in Stunden` } })
  );
  const catalogHit = scanAll();
  check(
    'an em dash in a locale catalog is reported, by key path',
    catalogHit.length === 1 && catalogHit[0].where === 'hero.title',
    JSON.stringify(catalogHit)
  );

  fs.writeFileSync(
    path.join(srcDir, 'Hero.astro'),
    `<h1>Recovery in seconds ${EM_DASH} not hours</h1>\n`
  );
  const both = scanAll();
  check('an em dash in an .astro component is reported', both.length === 2, JSON.stringify(both));

  // The id must survive a line move, or the baseline churns on unrelated edits and gets
  // regenerated wholesale, which is how a shrink-only baseline quietly stops shrinking.
  const before = scanAll().find((f) => f.file.endsWith('Hero.astro'))!;
  fs.writeFileSync(
    path.join(srcDir, 'Hero.astro'),
    `<section>\n  <p>unrelated</p>\n</section>\n<h1>Recovery in seconds ${EM_DASH} not hours</h1>\n`
  );
  const after = scanAll().find((f) => f.file.endsWith('Hero.astro'))!;
  check(
    'a source finding id survives the line moving',
    idOf(before) === idOf(after),
    `${idOf(before)} vs ${idOf(after)}`
  );

  // THE SURFACE TABLE ITSELF. If someone widens the catalog surface from `translations/`
  // to `src/i18n/`, every catalog finding is counted two or three times and the baseline
  // silently stops being drainable. That is a one-character edit, so it gets an assertion
  // rather than a comment. See GENERATED_CATALOG_DIRS above.
  const catalogSurface = SURFACES.find((s) => s.kind === 'catalog');
  check(
    'the catalog surface is the SOURCE catalogs only, not the generated siblings',
    catalogSurface?.dir === 'packages/www/src/i18n/translations',
    `catalog surface is "${catalogSurface?.dir}"; widening it to src/i18n/ would also scan ` +
      `${GENERATED_CATALOG_DIRS.join('/ and ')}/, which are generated FROM translations/, ` +
      `so every finding would be counted more than once and the shrink-only baseline could ` +
      `never be drained cleanly`
  );

  // MARKDOWN FENCE AWARENESS, proved in BOTH directions. A one-way proof ("the fenced
  // dash is ignored") is satisfied by a scanner that ignores the whole file.
  const cmdDir = path.join(root, '.claude/commands');
  fs.mkdirSync(cmdDir, { recursive: true });
  const mdSurface: Surface = {
    dir: '.claude/commands',
    kind: 'markdown',
    exts: ['.md'],
    minFiles: 1,
  };
  fs.writeFileSync(
    path.join(cmdDir, 'sample.md'),
    ['Prose is scanned.', '', '```bash', `echo "sample output ${EM_DASH} quoted"`, '```', ''].join(
      '\n'
    )
  );
  check(
    'an em dash inside a fenced block is NOT reported',
    scanSurface(root, mdSurface).findings.length === 0
  );
  fs.writeFileSync(
    path.join(cmdDir, 'sample.md'),
    [
      'Prose is scanned.',
      '',
      '```bash',
      `echo "sample output ${EM_DASH} quoted"`,
      '```',
      '',
      `And prose ${EM_DASH} here.`,
      '',
    ].join('\n')
  );
  const mdHits = scanSurface(root, mdSurface).findings;
  check(
    'the SAME text outside the fence IS reported (the fence rule is not a blanket skip)',
    mdHits.length === 1 && mdHits[0].excerpt.includes('And prose'),
    JSON.stringify(mdHits)
  );

  // A shell/python surface has no fences, so every line counts. `.claude/hooks` joined at
  // zero and its dashes lived in echo strings as often as in comments.
  const hookDir = path.join(root, '.claude/hooks/pre-bash');
  fs.mkdirSync(hookDir, { recursive: true });
  const hookSurface: Surface = {
    dir: '.claude/hooks',
    kind: 'source',
    exts: ['.sh', '.py'],
    minFiles: 1,
  };
  fs.writeFileSync(path.join(hookDir, 'guard.sh'), 'echo "BLOCKED: use rdc instead."\n');
  check(
    'a clean hook reports nothing (control)',
    scanSurface(root, hookSurface).findings.length === 0
  );
  fs.writeFileSync(path.join(hookDir, 'guard.sh'), `echo "BLOCKED ${EM_DASH} use rdc instead."\n`);
  check(
    'an em dash in a hook output string is reported',
    scanSurface(root, hookSurface).findings.length === 1
  );

  // THE FLOOR ITSELF. A surface whose glob returns nothing must REFUSE, not report clean.
  // The old single global floor could not do this: 4 command files vanishing left the
  // repo-wide total untouched.
  check(
    'a surface whose glob finds nothing trips its own floor',
    floorViolations(root, [
      { dir: '.claude/nonexistent', kind: 'markdown', exts: ['.md'], minFiles: 3 },
    ]).length === 1
  );
  check(
    'a surface at or above its floor does not trip it',
    floorViolations(root, [mdSurface]).length === 0
  );
  // THE ZERO-SURFACE INVARIANT, both directions.
  check(
    'a finding in a zero surface is recognised as one',
    inZeroSurface('.claude/commands/pr-merge.md') && inZeroSurface('.claude/hooks/stop/x.py')
  );
  check(
    'a prefix collision is NOT treated as a zero surface',
    !inZeroSurface('.claude/commands-archive/old.md') && !inZeroSurface('packages/www/src/x.tsx')
  );
  check(
    'every zero surface is actually a configured surface',
    ZERO_SURFACES.every((z) => SURFACES.some((s) => s.dir === z)),
    `zero surfaces ${JSON.stringify(ZERO_SURFACES)} vs configured ${JSON.stringify(SURFACES.map((s) => s.dir))}`
  );
  check(
    'every configured surface carries a floor above zero',
    SURFACES.every((s) => s.minFiles > 0),
    JSON.stringify(SURFACES.map((s) => [s.dir, s.minFiles]))
  );

  fs.rmSync(root, { recursive: true, force: true });
  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const baselineFile = path.resolve(arg('--baseline') ?? path.join(base, DEFAULT_BASELINE));

  let findings: Finding[] = [];
  let files = 0;
  for (const surface of SURFACES) {
    const r = scanSurface(base, surface);
    findings = findings.concat(r.findings);
    files += r.files;
  }

  // REFUSE, never report, on an input that cannot support a verdict. A glob that returns
  // nothing looks exactly like a surface with no em dashes in it, and the check is PER
  // SURFACE because a small surface collapsing is invisible in a repo-wide total.
  const thin = floorViolations(base);
  if (thin.length > 0) {
    console.error(
      `✗ Refusing to run: ${thin.length} surface(s) came in under their own file floor ` +
        `under ${base}:\n${thin.map((s) => `    ${s}`).join('\n')}\n` +
        `  A scan over an empty surface reports "no em dashes" while checking nothing.`
    );
    process.exit(1);
  }

  if (argv.includes('--write-baseline')) {
    // REFUSE to baseline a zero-surface finding. Reseeding is a bulk operation nobody
    // reads the output of, so this has to be a hard stop rather than a warning.
    const forbidden = findings.filter((f) => inZeroSurface(f.file));
    if (forbidden.length > 0) {
      console.error(
        `✗ Refusing to write the baseline: ${forbidden.length} finding(s) are in surfaces ` +
          `that joined at ZERO.\n` +
          forbidden
            .slice(0, 10)
            .map((f) => `    ${f.file}: ${f.excerpt}`)
            .join('\n') +
          `\n\n  Fix the text. These surfaces have no backlog by design, so baselining one\n` +
          `  would silently convert a regression into permanent, invisible debt.`
      );
      process.exit(1);
    }
    const ids = findings.map(idOf).sort();
    fs.mkdirSync(path.dirname(baselineFile), { recursive: true });
    fs.writeFileSync(baselineFile, `${JSON.stringify(ids, null, 2)}\n`);
    console.log(`Wrote ${ids.length} baselined finding(s) to ${path.relative(base, baselineFile)}`);
    return;
  }

  const baseline = new Set(loadBaseline(baselineFile));

  // The same invariant from the other side, in case the baseline was hand-edited or
  // written by an older build of this script.
  const smuggled = [...baseline].filter((id) => inZeroSurface(id.slice(0, id.lastIndexOf(':'))));
  if (smuggled.length > 0) {
    console.error(
      `✗ The baseline contains ${smuggled.length} id(s) from surfaces that joined at ZERO:\n` +
        smuggled.map((id) => `    ${id}`).join('\n') +
        `\n\n  Remove them and fix the text instead.`
    );
    process.exit(1);
  }
  const live = new Set(findings.map(idOf));
  const fresh = findings.filter((f) => !baseline.has(idOf(f)));
  const stale = [...baseline].filter((id) => !live.has(id));

  if (fresh.length === 0 && stale.length === 0) {
    console.log(
      `✓ No new em dashes across ${files} file(s) in ${SURFACES.length} surface(s). ` +
        `${baseline.size} known finding(s) still baselined.`
    );
    return;
  }

  if (fresh.length > 0) {
    console.error(`✗ ${fresh.length} new em dash(es) in surfaces that ship to readers:\n`);
    const byFile = new Map<string, Finding[]>();
    for (const f of fresh) byFile.set(f.file, [...(byFile.get(f.file) ?? []), f]);
    for (const [file, list] of [...byFile].sort((a, b) => b[1].length - a[1].length)) {
      console.error(`  ${file}  (${list.length})`);
      for (const f of list.slice(0, 5)) console.error(`    ${f.where}: ${f.excerpt}`);
      if (list.length > 5) console.error(`    ... and ${list.length - 5} more`);
    }
    console.error(
      `\nRestructure the sentence: a period, a comma, a colon or parentheses. Do NOT swap the\n` +
        `em dash for a spaced hyphen, and do NOT add it to ${DEFAULT_BASELINE} --\n` +
        `that file records the backlog measured on 2026-08-18, not new breakage.`
    );
  }

  if (stale.length > 0) {
    console.error(
      `\n${stale.length} baselined finding(s) are already fixed. The baseline only shrinks,\n` +
        `so remove them: npx tsx scripts/check-em-dash-surfaces.ts --write-baseline\n`
    );
    for (const id of stale.slice(0, 10)) console.error(`    ${id}`);
    if (stale.length > 10) console.error(`    ... and ${stale.length - 10} more`);
  }
  process.exit(1);
}

main();
