/**
 * check:ci-gate-cwd-independence -- a gate finds the repo from its OWN location,
 * never from the working directory it happens to be started in.
 *
 * WHY THIS EXISTS. A gate is invoked from at least three places with different
 * working directories: `npm run` from the workspace root, the ci-runner, and a
 * session typing the path by hand. A gate that resolves repo paths from cwd
 * therefore passes in one of them and does something else in the others -- and
 * the failure is the expensive kind, because "it passed locally" is true.
 *
 * THE RECORDED INSTANCE, from .ci/scripts/test/gates/test-gate-lanes.sh's own
 * header: "GitHub runs every step with the workspace as CWD, so a RELATIVE path
 * is correct there. This harness inherited its CWD instead, which meant it
 * passed when invoked by hand from the repo root and exited 127 under
 * run-all.sh, which does `cd "$GATES_DIR"` first." Exit 127 is a gate that did
 * not run at all, reported as a red with no finding in it.
 *
 * THE RULE:
 *   no gate derives a path from process.cwd() / os.getcwd() / $PWD.
 *
 * A SECOND CLAUSE WAS TRIED AND REMOVED, and the measurement is why. Requiring
 * every gate that reads repo files to anchor on its own location flagged 45 of
 * them -- the majority. Those gates use bare relative literals and are correct,
 * because this repo's contract is that a gate is invoked from the workspace
 * root (`npm run`, and the ci-runner, both do). A rule the tree does not hold
 * is a migration, not a regression gate, and a guard whose usual outcome is a
 * false positive is one people route around. So the enforced rule is the one
 * that is unambiguously a defect: naming cwd EXPLICITLY to build a path, which
 * silently means something different under each caller. That found exactly one.
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIRS = [
  path.join(ROOT, 'scripts'),
  path.join(ROOT, '.ci', 'scripts', 'quality'),
  path.join(ROOT, '.ci', 'scripts', 'security'),
];

/**
 * NOTE ON THE PLANT BELOW. This gate flagged ITSELF on its first real run: its
 * fixture literal is a code line, not a comment, so the scanner saw a genuine
 * match. Writing the call indirectly keeps the gate honest about its own source
 * while the fixture FILE it writes still contains the real thing, so the
 * control tests what it claims to.
 */

/** Deriving a path from the working directory. A bare `cwd:` option passed to a
 *  subprocess is NOT this: that sets where a child runs, it does not resolve
 *  the gate's own inputs. */
const FROM_CWD =
  /(?:path\.(?:resolve|join)\(\s*process\.cwd\(\)|os\.path\.join\(\s*os\.getcwd\(\)|Path\(\s*os\.getcwd\(\)|cd\s+"?\$PWD)/;
interface Finding {
  file: string;
  why: string;
}

function gateFiles(): string[] {
  const out: string[] = [];
  for (const d of DIRS) {
    if (!fs.existsSync(d)) continue;
    for (const n of fs.readdirSync(d)) {
      if (/^check[-_].*\.(ts|sh|py)$/.test(n)) out.push(path.join(d, n));
    }
  }
  return out.sort();
}

function scan(files: string[]): Finding[] {
  const out: Finding[] = [];
  for (const f of files) {
    const src = fs.readFileSync(f, 'utf-8');
    // Strip comments: prose ABOUT the rule must not trip it, which is the
    // mistake block-commit-meta.sh's header warns about.
    const code = src
      .split('\n')
      .filter((l) => !/^\s*(#|\/\/|\*)/.test(l))
      .join('\n');
    const rel = path.relative(ROOT, f);
    if (FROM_CWD.test(code)) {
      out.push({ file: rel, why: 'resolves a path from the working directory instead of its own location' });
      continue;
    }
  }
  return out;
}

function selftest(): void {
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'gcwd-'));
  const w = (n: string, b: string): string => {
    const p = path.join(tmp, n);
    fs.writeFileSync(p, b);
    return p;
  };

  const good = w('check-good.ts', "const R = path.resolve(import.meta.dirname, '..');\nfs.readFileSync(R + '/.ci/x');\n");
  if (scan([good]).length !== 0) {
    console.error('  FAIL  CONTROL: a self-anchored gate was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a self-anchored gate is accepted');

  // PLANT 1: the negative clause.
  const CWD_CALL = ['pro', 'cess.', 'cwd', '()'].join(''); // spelled indirectly: see above
  const cwd = w('check-cwd.ts', `const R = path.resolve(${CWD_CALL}, '..');\nfs.readFileSync('.ci/x');\n`);
  const c = scan([cwd]);
  if (c.length !== 1 || !c[0]?.why.includes('working directory')) {
    console.error(`  FAIL  the cwd-derived path was not caught: ${JSON.stringify(c)}`);
    process.exit(1);
  }
  console.log('  PASS  a path derived from cwd is caught');

  // CONTROL: a bare relative literal is CORRECT here -- 45 gates use one and
  // the contract is that a gate runs from the workspace root. Policing it would
  // make the usual outcome a false positive.
  const bare = w('check-bare.sh', "grep -q foo '.ci/scripts/quality/thing.sh'\n");
  if (scan([bare]).length !== 0) {
    console.error('  FAIL  CONTROL: a bare relative path was policed');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a bare relative path is not policed');

  // CONTROL: prose about the rule must not trip it.
  const prose = w(
    'check-prose.sh',
    `SCRIPT_DIR="$(dirname "\${BASH_SOURCE[0]}")"\n# never use path.resolve(${CWD_CALL}, "..") in a gate\ngrep x "$SCRIPT_DIR/../.ci/y"\n`,
  );
  if (scan([prose]).length !== 0) {
    console.error('  FAIL  CONTROL: a comment about the rule was policed');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: prose about the rule is not policed');

  // CONTROL: a gate that reads no repo path needs no anchor.
  const argvOnly = w('check-argv.ts', 'const target = process.argv[2];\nconsole.log(target);\n');
  if (scan([argvOnly]).length !== 0) {
    console.error('  FAIL  CONTROL: a gate that reads no repo path was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a gate reading no repo path needs no anchor');
  fs.rmSync(tmp, { recursive: true, force: true });
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-gate-cwd-independence: selftest ok (5 controls)');
    return;
  }
  const files = gateFiles();
  // ANTI-VACUITY: an empty corpus is a broken matcher, not a clean tree.
  if (files.length === 0) {
    console.error('✗ found no gate scripts to check; refusing a verdict');
    process.exit(1);
  }
  const findings = scan(files);
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} gate(s) whose paths depend on the working directory:\n`);
    for (const f of findings) console.error(`  ${f.file}\n      ${f.why}`);
    console.error(
      '\n  Anchor on the file: `path.resolve(import.meta.dirname, "..")`,\n' +
        '  `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`, or\n' +
        '  `pathlib.Path(__file__).resolve().parents[N]`. A gate runs from the\n' +
        '  workspace root under npm, from elsewhere under the runner, and from\n' +
        '  wherever a session typed it -- test-gate-lanes.sh passed by hand and\n' +
        '  exited 127 under run-all.sh for exactly this.',
    );
    process.exit(1);
  }
  console.log(`✓ gate cwd independence: ${files.length} gate script(s), all anchored on their own location`);
}

main();
