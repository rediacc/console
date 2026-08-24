#!/usr/bin/env tsx
/**
 * check:ci-skill-size -- the cap that makes a self-improving skill sharpen instead of grow.
 *
 * A skill an agent may edit will get longer on every pass, because appending is always
 * easier than rewriting. Long skill docs are the failure this closes: the operator asked
 * for "dedicated skills and sharper texts" precisely because accreted prose stops being
 * read, and a skill nobody reads routes nobody.
 *
 * The cap is the mechanism, not a style note. At 60 lines an addition REQUIRES removing or
 * tightening something else, which is the editing pass that would otherwise never happen.
 *
 * WHICH SKILLS. Only those whose SKILL.md frontmatter declares `self-improving: true`. A
 * hardcoded list of skill names was the first design and it is the same rot as a hardcoded
 * list of CI surfaces: the next self-improving skill is added and nobody remembers the
 * list. The declaration travels with the skill.
 *
 * NOT capped: `rdc/reference.md` and its kin, which are generated from the CLI and are
 * reference material rather than routing knowledge. They are not self-improving and no
 * agent edits them by hand.
 *
 * ANTI-VACUITY. Zero declared skills is a pass with a stated reason, not a silent one --
 * the count prints either way, so a declaration that stops being found is visible.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKILLS = path.join(REPO, '.claude/skills');

export const MAX_LINES = 60;

/** Does this SKILL.md opt into the cap? Frontmatter only: a mention in prose is not a flag. */
export const declaresSelfImproving = (source: string): boolean => {
  if (!source.startsWith('---')) return false;
  const end = source.indexOf('\n---', 3);
  if (end < 0) return false;
  return /^self-improving:\s*true\s*$/m.test(source.slice(0, end));
};

export const countLines = (source: string): number => {
  // A trailing newline ends the last line; it does not start another.
  const body = source.endsWith('\n') ? source.slice(0, -1) : source;
  return body === '' ? 0 : body.split('\n').length;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };

  check(
    'frontmatter with the flag is detected',
    declaresSelfImproving('---\nname: x\nself-improving: true\n---\nbody\n')
  );
  check(
    'a skill without the flag is not capped',
    !declaresSelfImproving('---\nname: x\n---\nbody\n')
  );
  // THE CONTROL THAT MATTERS: the flag must be frontmatter, or any skill that merely
  // discusses self-improvement would opt itself in.
  check(
    'the same text in the BODY does not opt in',
    !declaresSelfImproving('---\nname: x\n---\nself-improving: true\n')
  );
  check('a file with no frontmatter does not opt in', !declaresSelfImproving('# just a doc\n'));
  check('an unterminated frontmatter block does not opt in', !declaresSelfImproving('---\nself-improving: true\n'));

  check('line counting ignores the trailing newline', countLines('a\nb\n') === 2);
  check('and counts a file with no trailing newline', countLines('a\nb') === 2);
  check('an empty file is zero lines, not one', countLines('') === 0);
  check(`the cap is ${MAX_LINES}`, MAX_LINES === 60);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  let dirs: string[];
  try {
    dirs = fs
      .readdirSync(SKILLS, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    console.error(`✗ cannot read ${path.relative(REPO, SKILLS)}; a green here would mean nothing.`);
    return 1;
  }

  const over: string[] = [];
  let capped = 0;
  let files = 0;
  for (const dir of dirs) {
    const skillMd = path.join(SKILLS, dir, 'SKILL.md');
    let head: string;
    try {
      head = fs.readFileSync(skillMd, 'utf8');
    } catch {
      continue;
    }
    if (!declaresSelfImproving(head)) continue;
    capped += 1;
    for (const name of fs.readdirSync(path.join(SKILLS, dir)).filter((f) => f.endsWith('.md'))) {
      files += 1;
      const n = countLines(fs.readFileSync(path.join(SKILLS, dir, name), 'utf8'));
      if (n > MAX_LINES) over.push(`.claude/skills/${dir}/${name}: ${n} lines (cap ${MAX_LINES})`);
    }
  }

  if (over.length) {
    console.error(`✗ ${over.length} self-improving skill file(s) over the line cap:\n`);
    for (const o of over) console.error(`  ${o}`);
    console.error('\n  The cap is the sharpening mechanism, not a style note: an addition at the');
    console.error('  cap means tightening or removing something else. Do not raise it to fit a');
    console.error('  new paragraph -- that is the accretion it exists to prevent.');
    return 1;
  }

  if (capped === 0) {
    console.log(
      '✓ no skill declares `self-improving: true`, so nothing is capped. If that is a surprise, the declaration was lost.'
    );
    return 0;
  }
  console.log(`✓ ${files} file(s) across ${capped} self-improving skill(s) are within ${MAX_LINES} lines.`);
  return 0;
};

process.exit(main());
