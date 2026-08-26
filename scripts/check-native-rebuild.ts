#!/usr/bin/env tsx
/**
 * check:ci-native-rebuild -- the other half of the .npmrc bargain.
 *
 * `.npmrc` sets `ignore-scripts=true` for supply-chain hardening, and
 * `check:ci-npmrc` guards that it stays set. Nothing guarded the CONSEQUENCE:
 * with lifecycle scripts blocked, `npm install` alone leaves ssh2,
 * cpu-features and esbuild uncompiled, so every root-workspace installer must
 * pair it with `npm run install:natives`.
 *
 * WHY THIS GATE EXISTS. `./run.sh setup` shipped a bare `npm install` and
 * nothing caught it: a fresh machine finished setup "successfully" with
 * unbuilt natives and failed much later at runtime, which reads as a broken
 * CLI rather than a broken install. Found 2026-08-26 on a real fresh machine.
 * The CI workflows all pair the two correctly; the DEVELOPER path was the
 * blind spot, which is exactly why no existing gate saw it.
 *
 * SCOPE: the local entrypoints that install the ROOT workspace -- `run.sh` and
 * `.ci/lib/*.sh`. Sub-project installs (`cd private/account && npm install`)
 * are NOT in scope: ssh2/cpu-features/esbuild are root devDependencies and a
 * sub-project install neither provides nor needs them.
 *
 * ANTI-VACUITY. Root installs are KNOWN to exist in these files, so finding
 * zero means the detector broke, not that the repo got clean. That case fails
 * loudly rather than printing a green nobody earned.
 *
 * COVERAGE, demonstrated rather than asserted (2026-08-26): re-planting the
 * original `./run.sh setup` defect (dropping its `npm run install:natives`)
 * turns this gate RED on `run.sh:1841`, and restoring the line turns it green.
 * `setup()` lives in `run.sh`, which is the first entry of SCANNED, so the
 * `setup` workflow is covered by construction and not by a special case.
 *
 * NOT AN INTEGRATION TEST, on purpose. A test that actually RAN `./run.sh setup`
 * and inspected the compiled binding would need a full `npm install` per run --
 * minutes of CI, a compiler toolchain, and a network -- to catch a defect whose
 * entire shape is "the rebuild line is missing from the script". The cheap
 * static pairing check catches that shape at its source, in milliseconds, on
 * every PR. `npm run install:natives` itself is already exercised for real by
 * every CI job that installs (`.github/actions/setup-workspace`), so the
 * compile step is not what is unguarded here; the CALL SITE was.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Files that install the root workspace for a developer. */
export const SCANNED = ['run.sh', ...fsSafeList('.ci/lib')];

function fsSafeList(dir: string): string[] {
  try {
    return fs
      .readdirSync(path.join(REPO, dir))
      .filter((f) => f.endsWith('.sh'))
      .map((f) => `${dir}/${f}`);
  } catch {
    return [];
  }
}

/** How far after an install we still accept the rebuild. */
export const WINDOW = 20;

const INSTALL_RE = /\bnpm\s+(install|ci)\b/;
const NATIVES_RE = /npm\s+run\s+install:natives/;
/** `cd $ROOT_DIR` / `cd "$LOCAL_ROOT_DIR"` -- but NOT `cd "$ROOT_DIR/sub"`. */
const ROOT_CD_RE = /\bcd\s+"?\$\{?(?:LOCAL_)?ROOT_DIR\}?"?(?=\s|\)|&|;|$)/;

/**
 * Is this line a ROOT-workspace install?
 *
 * Excluded, each for a different reason:
 *  - comments: prose about installing is not installing.
 *  - `npm install -g <url>`: installs a published artifact, not this workspace.
 *  - a `cd` to somewhere that is not the repo root: a sub-project install.
 *    `ROOT_DIR`/`LOCAL_ROOT_DIR` are how this repo spells "the root", so a cd
 *    naming one of those is still a root install.
 */
export const isRootInstall = (line: string): boolean => {
  const code = line.trim();
  if (code.startsWith('#')) return false;
  if (!INSTALL_RE.test(code)) return false;
  if (/npm\s+(install|ci)[^|;&]*\s-g\b/.test(code)) return false;
  // A cd counts as root-scoped ONLY when it lands ON the root, not inside it.
  // `cd "$ROOT_DIR/workers/www"` merely CONTAINS the root variable and is a
  // sub-project install -- the first version of this test matched the variable
  // anywhere and produced two false positives on the real tree.
  if (/\bcd\s/.test(code) && !ROOT_CD_RE.test(code)) return false;
  return true;
};

/** Does a rebuild follow within WINDOW lines? */
export const pairedWithNatives = (lines: string[], idx: number, window = WINDOW): boolean =>
  lines
    .slice(idx + 1, idx + 1 + window)
    .some((l) => !l.trim().startsWith('#') && NATIVES_RE.test(l));

export interface Finding {
  file: string;
  line: number;
  text: string;
}

export const scanSource = (file: string, source: string): Finding[] => {
  const lines = source.split('\n');
  const out: Finding[] = [];
  lines.forEach((line, i) => {
    if (!isRootInstall(line)) return;
    if (pairedWithNatives(lines, i)) return;
    out.push({ file, line: i + 1, text: line.trim() });
  });
  return out;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  };

  // The planted defect: an unpaired root install must be caught.
  check(
    'an unpaired root install is flagged',
    scanSource('x.sh', 'log "hi"\nnpm install\necho done\n').length === 1
  );
  // The control: the same install, paired, must NOT be flagged. Without this,
  // a gate that flags everything would also "pass" its defect test.
  check(
    'a paired root install is clean',
    scanSource('x.sh', 'npm install\nnpm run install:natives\n').length === 0
  );
  check(
    'pairing is accepted anywhere inside the window',
    scanSource(
      'x.sh',
      ['npm install', ...Array(15).fill('echo x'), 'npm run install:natives'].join('\n')
    ).length === 0
  );
  check(
    'but NOT beyond it',
    scanSource(
      'x.sh',
      ['npm install', ...Array(40).fill('echo x'), 'npm run install:natives'].join('\n')
    ).length === 1
  );
  check(
    'a sub-project install is out of scope',
    scanSource('x.sh', '(cd "$ACCOUNT_DIR" && npm install)\n').length === 0
  );
  check(
    'a root-named cd IS in scope',
    scanSource('x.sh', '(cd "$LOCAL_ROOT_DIR" && npm install)\n').length === 1
  );
  // The false positive the real tree exposed: a path UNDER the root is a
  // sub-project, even though the line mentions ROOT_DIR.
  check(
    'a subdirectory of the root is out of scope',
    scanSource('x.sh', '(cd "$ROOT_DIR/workers/www" && npm install)\n').length === 0
  );
  check(
    'and so is a nested sub-project with extra commands',
    scanSource('x.sh', '(cd "$ROOT_DIR/private/account/web" && npm install && npx vite build)\n')
      .length === 0
  );
  check(
    'a global install is out of scope',
    scanSource('x.sh', 'npm install -g "$url"\n').length === 0
  );
  check(
    'a comment is not an install',
    scanSource('x.sh', '# npm install then rebuild\n').length === 0
  );
  check(
    'a commented rebuild does not count as pairing',
    scanSource('x.sh', 'npm install\n# npm run install:natives\n').length === 1
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  // The premise. If ignore-scripts is gone, this gate is guarding nothing and
  // must say so rather than pass quietly.
  let npmrc = '';
  try {
    npmrc = fs.readFileSync(path.join(REPO, '.npmrc'), 'utf8');
  } catch {
    console.error('✗ .npmrc unreadable; this gate cannot know whether its premise holds.');
    return 1;
  }
  if (!/^\s*ignore-scripts\s*=\s*true\s*$/m.test(npmrc)) {
    console.error('✗ .npmrc no longer sets ignore-scripts=true.');
    console.error('  This gate exists only because that flag blocks native builds.');
    console.error('  Re-justify or remove it; do not leave it asserting a dead premise.');
    return 1;
  }

  const findings: Finding[] = [];
  let installs = 0;
  let scanned = 0;
  for (const rel of SCANNED) {
    let src: string;
    try {
      src = fs.readFileSync(path.join(REPO, rel), 'utf8');
    } catch {
      continue;
    }
    scanned += 1;
    installs += src.split('\n').filter(isRootInstall).length;
    findings.push(...scanSource(rel, src));
  }

  if (scanned === 0 || installs === 0) {
    console.error(`✗ scanned ${scanned} file(s) and found ${installs} root install(s).`);
    console.error('  These files are known to install the root workspace, so zero means the');
    console.error('  detector broke. Failing rather than reporting a green nobody earned.');
    return 1;
  }

  if (findings.length > 0) {
    console.error(`✗ ${findings.length} root-workspace install(s) never rebuild native modules:`);
    for (const f of findings) console.error(`    ${f.file}:${f.line}  ${f.text}`);
    console.error('');
    console.error('  .npmrc sets ignore-scripts=true, so npm install leaves ssh2, cpu-features');
    console.error('  and esbuild uncompiled. Add after the install:');
    console.error('      npm run install:natives');
    return 1;
  }

  console.log(
    `✓ all ${installs} root-workspace install(s) across ${scanned} file(s) rebuild native modules`
  );
  return 0;
};

process.exit(main());
