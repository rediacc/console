#!/usr/bin/env tsx
/**
 * check:ci-shell-declared-commands -- a .ci script must declare the non-baseline
 * binaries it executes, so a missing one is a sentence rather than a silent 127.
 *
 * THE DEFECT THIS CLOSES, 2026-08-26. `.ci/scripts/review/review-status.sh`
 * read a workflow artifact with `unzip`, which nothing declared. Under
 * `set -euo pipefail` a command-not-found inside a command substitution exits
 * 127 IMMEDIATELY, so on any host without unzip the script died at that line:
 * before the two log_error calls that exist to explain that exact failure, and
 * before it could post its check-run. The symptom was a review status that
 * never appeared, and the diagnosis chased the cancelled-run branch for a while
 * because the branch that "failed" was simply never reached.
 *
 * `require_cmd` already existed and already prints the right sentence
 * ("Required command 'X' is not available"). It was called for `gh` and `jq`
 * and nothing else. So this is not a new mechanism; it is a gate on using the
 * one that was already there.
 *
 * WHY A GATE RATHER THAN A FIX. The fix was to stop using unzip, and that is
 * done -- unzip appears in no non-test script now. But nothing stops the next
 * script from reaching for `yq`, `gpg` or `xmllint`, and the failure mode is
 * specifically invisible: exit 127, no message, and on a host that HAS the
 * binary (every developer laptop, most CI images) the script works perfectly,
 * so the defect ships and waits for a leaner runner. review-status.yml runs on
 * `ubuntu-slim`.
 *
 * SCOPE, deliberately narrow in three ways, because an over-matching gate here
 * would flag hundreds of lines and get disabled:
 *
 *   1. Only scripts that SOURCE lib/common.sh, because only those have
 *      require_cmd available. A script without it cannot satisfy this gate and
 *      would be an unfixable finding.
 *   2. Only a fixed list of NON-BASELINE binaries. sed, awk, grep and their
 *      coreutils siblings are on every POSIX host; demanding a declaration for
 *      them is ceremony that buys nothing and trains people to ignore the rule.
 *   3. Only COMMAND POSITION, after comment lines are removed. This gate exists
 *      because a mention was mistaken for an execution four separate times in
 *      the session that wrote it (a deny-list flagged itself, a log_warn string
 *      read as code, prose about a rule read as the rule being broken, and a
 *      heredoc body read as a command). Anchoring on execution is the whole
 *      difference between a gate and a nuisance.
 *
 * THE BASELINE ONLY SHRINKS, the same contract as
 * scripts/check-em-dash-surfaces.ts. 55 findings existed when this was written;
 * they are real (jq undeclared in a dozen autopilot scripts is the same latent
 * mute death, just on a binary that is usually present), and fixing them all
 * here would bury a removal commit under an unrelated sweep. New findings fail
 * at zero. A baseline entry that no longer fires must be REMOVED, so the file
 * cannot rot into a permanent excuse.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import {
  baselineAdditions,
  renderRefusal,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

/** Binaries that are NOT on a minimal POSIX host and can therefore be absent. */
export const RISKY = [
  'unzip',
  'zip',
  'yq',
  'gpg',
  'xmllint',
  'rsync',
  'python3',
  'curl',
  'wget',
  'jq',
  'gh',
  'docker',
  'aws',
  'wrangler',
  'shellcheck',
] as const;

const DEFAULT_BASELINE = 'scripts/data/shell-declared-commands-baseline.json';

/** Lines whose first non-space character is `#` are prose, never execution. */
export const stripComments = (src: string): string =>
  src
    .split('\n')
    .filter((l) => !l.trimStart().startsWith('#'))
    .join('\n');

export const declared = (src: string): Set<string> =>
  new Set([...src.matchAll(/require_cmd\s+([A-Za-z0-9_-]+)/g)].map((m) => m[1]));

/**
 * Command position: the start of a line, or immediately after a separator that
 * begins a new command. `echo "curl this"` is not an execution of curl, and
 * neither is `--url=curl`.
 */
export const executes = (code: string, cmd: string): boolean =>
  new RegExp(String.raw`(?:^|[|;&]|\$\(|\`|\bthen\b|\bdo\b|\belse\b)\s*${cmd}\s`, 'm').test(code);

export interface Finding {
  file: string;
  cmd: string;
}

export const scan = (root: string, files: string[]): Finding[] => {
  const out: Finding[] = [];
  for (const f of files) {
    const src = fs.readFileSync(path.join(root, f), 'utf8');
    if (!src.includes('lib/common.sh')) continue;
    const has = declared(src);
    const code = stripComments(src);
    for (const cmd of RISKY) {
      if (has.has(cmd)) continue;
      if (executes(code, cmd)) out.push({ file: f, cmd });
    }
  }
  return out;
};

const key = (f: Finding) => `${f.file}\t${f.cmd}`;

const tracked = (root: string): string[] =>
  execFileSync('git', ['ls-files', '.ci/scripts'], { cwd: root, encoding: 'utf8' })
    .split('\n')
    .filter((f) => f.endsWith('.sh') && !f.includes('/test/'));

const selftest = (): number => {
  let bad = 0;
  const ok = (label: string, cond: boolean) => {
    console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${label}`);
    if (!cond) bad = 1;
  };
  ok('an executed risky binary is a finding', executes('unzip -p a.zip b', 'unzip'));
  ok(
    'CONTROL: the same word in a comment is not',
    !executes(stripComments('# we used to unzip here\necho hi'), 'unzip')
  );
  ok(
    'CONTROL: the same word inside a string is not command position',
    !executes('echo "run unzip first"', 'unzip')
  );
  ok('after a pipe IS command position', executes('cat x | jq .a', 'jq'));
  ok('inside a command substitution IS command position', executes('v="$(curl -s url)"', 'curl'));
  ok('a declaration silences it', declared('require_cmd unzip\nunzip -p a b').has('unzip'));
  ok('CONTROL: a near-miss declaration does not', !declared('require_cmds unzip').has('unzip'));
  ok('CONTROL: an undeclared script yields an empty set', declared('echo hi').size === 0);
  return bad;
};

const main = (): number => {
  const root = process.cwd();
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const baseFile = path.join(root, DEFAULT_BASELINE);
  const base: string[] = fs.existsSync(baseFile)
    ? JSON.parse(fs.readFileSync(baseFile, 'utf8'))
    : [];

  if (process.argv.slice(2).includes('--write-baseline')) {
    const found = scan(root, tracked(root)).map(key).sort();
    // REFUSE BEFORE WRITING, through the shared composition guard rather than a
    // private copy of the rule. An unconditional reseed can drain thirty
    // findings, absorb one brand-new one, and print a SMALLER number while
    // doing it -- the shrink-only baseline's whole point defeated by the
    // command that maintains it. gate-test:shrink-only-composition caught this
    // file bypassing the guard on the day it was written.
    const verdict = writeBaselineVerdict({
      baselineExists: fs.existsSync(baseFile),
      firstSeedFlag: process.argv.includes('--first-seed'),
      additions: fs.existsSync(baseFile) ? baselineAdditions(base, found) : [],
    });
    if (verdict !== null) {
      console.error(
        `\n\x1b[31m✗\x1b[0m ${renderRefusal(verdict, {
          baselineLabel: DEFAULT_BASELINE,
          noun: 'undeclared-binary finding',
          previousCount: base.length,
          newCount: found.length,
        })}\n`
      );
      return 1;
    }
    fs.mkdirSync(path.dirname(baseFile), { recursive: true });
    fs.writeFileSync(baseFile, `${JSON.stringify(found, null, 2)}\n`);
    console.log(`wrote ${found.length} baselined finding(s) to ${DEFAULT_BASELINE}`);
    return 0;
  }

  const found = scan(root, tracked(root));
  const seen = new Set(found.map(key));
  const baseSet = new Set(base);
  const fresh = found.filter((f) => !baseSet.has(key(f)));
  const stale = base.filter((b) => !seen.has(b));

  if (fresh.length) {
    console.error(`✗ ${fresh.length} undeclared non-baseline binar(y|ies) in .ci scripts:\n`);
    for (const f of fresh) console.error(`    ${f.file}  executes '${f.cmd}' with no require_cmd`);
    console.error(`
Under 'set -euo pipefail' a missing binary inside a command substitution exits
127 with NO message, before any log_error and before the script can report
anything. On a host that has the binary this reads as working code, so the
defect ships and waits for a leaner runner.

Add one line near the top of the script:

    require_cmd <name>

or stop using the binary. review-status.sh took the second route: it read a zip
member with python3, which was already declared.`);
    return 1;
  }

  if (stale.length) {
    console.error(
      `✗ ${stale.length} baseline entr(y|ies) no longer fire. The baseline SHRINKS ONLY;`
    );
    console.error('  remove these so it cannot rot into a permanent excuse:\n');
    for (const b of stale) console.error(`    ${b.replace('\t', '  ')}`);
    console.error(
      '\n  Regenerate with: npx tsx scripts/check-shell-declared-commands.ts --write-baseline'
    );
    return 1;
  }

  console.log(`✓ no undeclared non-baseline binaries (${base.length} finding(s) still baselined)`);
  return 0;
};

process.exit(main());
