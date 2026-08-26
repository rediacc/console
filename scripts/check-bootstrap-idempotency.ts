#!/usr/bin/env tsx
/**
 * check:ci-bootstrap-idempotency -- every bootstrap path installs THROUGH the stamp.
 *
 * `./run.sh setup` is expected to be run repeatedly, so a second run must do no
 * work. `ensure_deps` in .ci/lib/local-common.sh is what makes that true: it
 * hashes package.json, package-lock.json and .npmrc and skips when the stamp
 * matches.
 *
 * THE DEFECT THIS CLOSES, found by the operator on 2026-08-26. `setup()` called
 * `npm install` and `npm run install:natives` DIRECTLY instead of going through
 * ensure_deps, so every single invocation re-ran npm and recompiled cpu-features
 * through node-gyp: tens of seconds and a screen of gyp output on a machine
 * where nothing had changed. `dev()` had the same duplication with a weaker
 * mtime test.
 *
 * WHY NO EXISTING GATE SAW IT. The pattern was already correct at eight call
 * sites, which is exactly what made it invisible: coverage was assumed universal
 * once the helper existed, and nothing cross-checked the entry points that
 * matter most. `check:ci-native-rebuild` is a DIFFERENT question -- it asserts
 * that an install is PAIRED with a native rebuild, not that it is GUARDED by a
 * stamp -- so a bare, unguarded, correctly-paired install passes it cleanly.
 *
 * WHAT COUNTS AS A VIOLATION: a shell function, other than ensure_deps itself,
 * that invokes a ROOT-workspace npm install. Sub-project installs
 * (`cd "$ROOT_DIR/workers/www" && npm install`) are out of scope, exactly as in
 * check-native-rebuild: they install a different package.json that this stamp
 * does not cover.
 *
 * ANTI-VACUITY. ensure_deps must exist, must itself contain the install, and
 * setup() must call it. If any of those is false the scan has lost its subject
 * and this fails loudly rather than printing a green nobody earned.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export const SCANNED = ['run.sh', '.ci/lib/setup.sh'];
export const HELPER_FILE = '.ci/lib/local-common.sh';
export const HELPER = 'ensure_deps';

/** The helper legitimately contains the install; it IS the guard. */
export const EXEMPT = new Set([HELPER]);

const INSTALL_RE = /\bnpm\s+(install|ci)\b|\bnpm\s+run\s+install:natives\b/;
/** `cd $ROOT_DIR` counts as root; `cd "$ROOT_DIR/workers/www"` does not. */
const ROOT_CD_RE = /\bcd\s+"?\$\{?(?:LOCAL_)?ROOT_DIR\}?"?(?=\s|\)|&|;|$)/;

/**
 * A line that only PRINTS the words is not running them.
 *
 * The first version flagged a log_warn whose message text explains what
 * install:natives does, which is prose about the danger rather than the danger.
 * Same lesson as check-git-tool-safety: a gate that cannot tell "runs npm" from
 * "describes npm" is unusable, and a false positive on an explanatory message
 * teaches people to route around the gate.
 */
const OUTPUT_RE = /^(log_[a-z]+|echo|printf|cat)\b/;

export const isRootInstall = (line: string): boolean => {
  const code = line.trim();
  if (code.startsWith('#')) return false;
  if (OUTPUT_RE.test(code)) return false;
  if (!INSTALL_RE.test(code)) return false;
  if (/npm\s+(install|ci)[^|;&]*\s-g\b/.test(code)) return false;
  if (/\bcd\s/.test(code) && !ROOT_CD_RE.test(code)) return false;
  return true;
};

export interface Fn {
  name: string;
  start: number;
  body: string[];
}

/** Split a shell file into top-level `name() { ... }` blocks. */
export const shellFunctions = (source: string): Fn[] => {
  const lines = source.split('\n');
  const out: Fn[] = [];
  let cur: Fn | null = null;
  lines.forEach((line, i) => {
    const open = /^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{\s*$/.exec(line);
    if (open && !cur) {
      cur = { name: open[1], start: i + 1, body: [] };
      return;
    }
    if (cur) {
      if (/^\}\s*$/.test(line)) {
        out.push(cur);
        cur = null;
        return;
      }
      cur.body.push(line);
    }
  });
  return out;
};

export interface Finding {
  file: string;
  fn: string;
  line: number;
  text: string;
}

export const scan = (file: string, source: string): Finding[] => {
  const out: Finding[] = [];
  for (const fn of shellFunctions(source)) {
    if (EXEMPT.has(fn.name)) continue;
    // Calling the helper is the whole point; such a function is compliant even
    // if it also mentions npm elsewhere.
    if (fn.body.some((l) => !l.trim().startsWith('#') && new RegExp(`\\b${HELPER}\\b`).test(l))) {
      continue;
    }
    fn.body.forEach((text, j) => {
      if (isRootInstall(text)) {
        out.push({ file, fn: fn.name, line: fn.start + j + 1, text: text.trim() });
      }
    });
  }
  return out;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  };

  const bare = 'setup() {\n  log_info x\n  npm install\n}\n';
  check('an unguarded root install is flagged', scan('f', bare).length === 1);
  check('and it names the function', scan('f', bare)[0]?.fn === 'setup');

  // THE CONTROL THAT MATTERS: a guarded function must NOT be flagged, or a gate
  // that flags every install would also pass its defect test.
  check(
    'a function calling ensure_deps is clean',
    scan('f', 'setup() {\n  ensure_deps\n}\n').length === 0
  );
  check(
    'ensure_deps itself is exempt: it IS the guard',
    scan('f', 'ensure_deps() {\n  npm install\n}\n').length === 0
  );
  check(
    'a sub-project install is out of scope',
    scan('f', 'build() {\n  (cd "$ROOT_DIR/workers/www" && npm install)\n}\n').length === 0
  );
  check(
    'a root-named cd IS in scope',
    scan('f', 'boot() {\n  (cd "$LOCAL_ROOT_DIR" && npm install)\n}\n').length === 1
  );
  check(
    'install:natives alone is also a root install',
    scan('f', 'boot() {\n  npm run install:natives\n}\n').length === 1
  );
  check(
    'a global install is out of scope',
    scan('f', 'x() {\n  npm install -g "$u"\n}\n').length === 0
  );
  check(
    'a comment is not an install',
    scan('f', 'x() {\n  # npm install then rebuild\n}\n').length === 0
  );
  check('code outside any function is ignored', scan('f', 'npm install\n').length === 0);
  // THE FALSE POSITIVE THE FIRST VERSION SHIPPED: a message that merely explains
  // what install:natives does is prose, not an install.
  check(
    'a log_warn mentioning the command is NOT flagged',
    scan('f', 'x() {\n  log_warn "  npm run install:natives runs node-gyp"\n}\n').length === 0
  );
  check(
    'an echoed recipe is NOT flagged',
    scan('f', 'x() {\n  echo "npm install && npm run install:natives"\n}\n').length === 0
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  // Anti-vacuity: the helper must exist and must itself do the install.
  let helperSrc: string;
  try {
    helperSrc = fs.readFileSync(path.join(REPO, HELPER_FILE), 'utf8');
  } catch {
    console.error(`✗ cannot read ${HELPER_FILE}; a green here would mean nothing.`);
    return 1;
  }
  const helperFn = shellFunctions(helperSrc).find((f) => f.name === HELPER);
  if (!helperFn || !helperFn.body.some(isRootInstall)) {
    console.error(`✗ ${HELPER_FILE}: ${HELPER}() is missing or no longer installs anything.`);
    console.error('  This gate exists to route bootstrap paths through it. Failing rather');
    console.error('  than asserting a guard that is no longer a guard.');
    return 1;
  }

  const findings: Finding[] = [];
  let scanned = 0;
  let guarded = 0;
  for (const rel of SCANNED) {
    let src: string;
    try {
      src = fs.readFileSync(path.join(REPO, rel), 'utf8');
    } catch {
      continue;
    }
    scanned += 1;
    guarded += shellFunctions(src).filter((f) =>
      f.body.some((l) => !l.trim().startsWith('#') && new RegExp(`\\b${HELPER}\\b`).test(l))
    ).length;
    findings.push(...scan(rel, src));
  }

  if (scanned === 0) {
    console.error(`✗ scanned no files; expected ${SCANNED.join(', ')}.`);
    return 1;
  }
  // setup() is the entry point this gate was written for; if it stops calling
  // the helper the gate has lost its subject.
  const runSrc = fs.readFileSync(path.join(REPO, 'run.sh'), 'utf8');
  const setupFn = shellFunctions(runSrc).find((f) => f.name === 'setup');
  if (!setupFn) {
    console.error('✗ run.sh no longer defines setup(); this gate has lost its subject.');
    return 1;
  }
  if (!setupFn.body.some((l) => new RegExp(`\\b${HELPER}\\b`).test(l))) {
    console.error(`✗ run.sh setup() does not call ${HELPER}.`);
    console.error('  Every ./run.sh setup would then re-run npm and recompile native modules');
    console.error('  even when nothing changed. That is the defect this gate exists for.');
    return 1;
  }

  if (findings.length > 0) {
    console.error(`✗ ${findings.length} bootstrap install(s) bypass ${HELPER}:`);
    for (const f of findings) {
      console.error(`    ${f.file}:${f.line}  in ${f.fn}()\n      ${f.text}`);
    }
    console.error('');
    console.error(`  Call ${HELPER} instead. It hashes package.json, package-lock.json and`);
    console.error('  .npmrc and skips when unchanged, which is what makes setup idempotent.');
    return 1;
  }

  console.log(
    `✓ ${guarded} bootstrap function(s) across ${scanned} file(s) install through ${HELPER}; none bypass it`
  );
  return 0;
};

process.exit(main());
