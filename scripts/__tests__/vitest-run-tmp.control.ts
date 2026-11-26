/**
 * Control for scripts/lib/vitest-run-tmp.ts, the `globalSetup` every vitest config lists (PLAN-host-temp-disposal HT7).
 *
 * A fixture project whose one test leaks `mkdtempSync(tmpdir())` is run by a REAL `vitest run` under a fresh outer TMPDIR:
 *   - WITH the globalSetup the outer TMPDIR holds nothing afterwards (the leak went under the removed run dir);
 *   - WITHOUT it (the planted defect) the outer TMPDIR holds the leak, which proves the "holds nothing" verdict could fail;
 *   - a repo vitest config that drops the globalSetup is caught by the config scan.
 *
 *   npx tsx scripts/__tests__/vitest-run-tmp.control.ts
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { ramFilesystemIn, removeTree, shared } from '../lib/runtmp.js';

const REPO = path.resolve(import.meta.dirname, '../..');
const SETUP = path.join(REPO, 'scripts/lib/vitest-run-tmp.ts');
const VITEST = path.join(REPO, 'node_modules/.bin/vitest');

let bad = 0;
function check(ok: boolean, what: string): void {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) bad += 1;
}

/** True when the config source, comments removed, has a `globalSetup: [...]` array that names the setup file. */
function listsGlobalSetup(src: string): boolean {
  // Strings are matched first and kept, so a glob such as 'src/*.ts' never opens a block comment and `//` inside a URL never opens a line comment.
  const code = src.replace(
    /('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)|\/\*[\s\S]*?\*\/|\/\/[^\n]*/g,
    (_m, str: string | undefined) => str ?? ''
  );
  return /globalSetup\s*:\s*\[[^\]]*scripts\/lib\/vitest-run-tmp\.ts/.test(code);
}

/** Runs the leaking fixture under a fresh outer TMPDIR; returns the entries left there and vitest's exit code. */
function runFixture(withSetup: boolean): { left: string[]; rc: number | null; out: string } {
  const root = fs.mkdtempSync(path.join(shared('vitest-run-tmp-ctl-'), 'case-'));
  const outer = path.join(root, 'outer');
  const proj = path.join(root, 'proj');
  fs.mkdirSync(outer, { mode: 0o700 });
  fs.mkdirSync(proj);
  fs.writeFileSync(
    path.join(proj, 'vitest.config.mjs'),
    `export default { test: { globals: true, include: ['leak.test.mjs']${
      withSetup ? `, globalSetup: [${JSON.stringify(SETUP)}]` : ''
    } } };\n`
  );
  fs.writeFileSync(
    path.join(proj, 'leak.test.mjs'),
    "import fs from 'node:fs';\nimport os from 'node:os';\nimport path from 'node:path';\n" +
      "test('leaks a temp dir', () => { fs.mkdtempSync(path.join(os.tmpdir(), 'leaky-')); });\n"
  );
  const res = spawnSync(
    VITEST,
    ['run', '--root', proj, '--config', path.join(proj, 'vitest.config.mjs')],
    { cwd: proj, env: { ...process.env, TMPDIR: outer }, encoding: 'utf8' }
  );
  const left = fs.readdirSync(outer);
  removeTree(root);
  return { left, rc: res.status, out: `${res.stdout}${res.stderr}` };
}

function main(): void {
  const guarded = runFixture(true);
  check(
    guarded.rc === 0,
    `fixture passes under vitest run with the globalSetup (rc ${guarded.rc})`
  );
  if (guarded.rc !== 0) console.log(guarded.out);
  check(
    guarded.left.length === 0,
    `with the globalSetup the outer TMPDIR holds nothing (left: ${JSON.stringify(guarded.left)})`
  );
  const planted = runFixture(false);
  check(planted.rc === 0, `fixture passes without the globalSetup (rc ${planted.rc})`);
  check(
    planted.left.some((n) => n.startsWith('leaky-')),
    `without the globalSetup the leak lands in the outer TMPDIR (planted-defect control; left: ${JSON.stringify(planted.left)})`
  );

  const configs = [
    ...fs.readdirSync(path.join(REPO, 'packages')).map((d) => `packages/${d}`),
    ...fs.readdirSync(path.join(REPO, 'workers')).map((d) => `workers/${d}`),
  ].flatMap((dir) =>
    ['vitest.config.ts', 'vitest.config.mjs']
      .map((f) => path.join(REPO, dir, f))
      .filter((f) => fs.existsSync(f))
  );
  // A scan that finds no config checks nothing; 10 configs on 2026-11-26, and the floor only catches a broken walk. A config that drops its globalSetup is the per-config check below, not the count.
  const MIN_VITEST_CONFIGS = 10;
  check(
    configs.length >= MIN_VITEST_CONFIGS,
    `the config scan found ${configs.length} vitest configs (at least ${MIN_VITEST_CONFIGS})`
  );
  const live =
    "globalSetup: [fileURLToPath(new URL('../../scripts/lib/vitest-run-tmp.ts', import.meta.url))],";
  check(
    listsGlobalSetup(`export default { test: { ${live} } };`),
    'CONTROL (scan): a live globalSetup line is accepted'
  );
  check(
    !listsGlobalSetup(`export default { test: { // ${live}\n } };`),
    'CONTROL (scan): a line-commented globalSetup is refused'
  );
  check(
    !listsGlobalSetup(`export default { test: { /* ${live} */ } };`),
    'CONTROL (scan): a block-commented globalSetup is refused'
  );
  check(
    listsGlobalSetup(
      `export default { test: { include: ['src/*.ts'], ${live} exclude: ['test/**/x.ts'] } };`
    ),
    'CONTROL (scan): globs holding a comment opener do not swallow a live globalSetup line (review 4ac9adcd.2)'
  );
  check(
    !listsGlobalSetup("const p ='scripts/lib/vitest-run-tmp.ts';\nexport default { test: {} };"),
    'CONTROL (scan): the path outside a globalSetup array is refused'
  );
  // CONTROL (runtmp.ts onRamFilesystem, review aca7dc2d.1): a fabricated mount table drives the longest-mount ranking and the octal unescape.
  const table = [
    'rootfs / ext4 rw 0 0',
    'tmpfs /tmp tmpfs rw 0 0',
    'ext4 /tmp/disk ext4 rw 0 0',
    'tmpfs /mnt/my\\040ram tmpfs rw 0 0',
    'ramfs /mnt/rf ramfs rw 0 0',
  ].join('\n');
  check(
    ramFilesystemIn(table, '/tmp/x'),
    'CONTROL (ram): a path under a tmpfs /tmp is on a RAM filesystem'
  );
  check(
    !ramFilesystemIn(table, '/tmp/disk/x'),
    'CONTROL (ram): the longer ext4 mount under a tmpfs /tmp wins'
  );
  check(
    !ramFilesystemIn(table, '/var/tmp/x'),
    'CONTROL (ram): a path outside every tmpfs falls to the root mount'
  );
  check(
    ramFilesystemIn(table, '/mnt/my ram/x'),
    'CONTROL (ram): an octal-escaped mount point is unescaped before matching'
  );
  check(
    ramFilesystemIn(table, '/mnt/rf'),
    'CONTROL (ram): ramfs counts and the mount point itself is inside'
  );
  check(
    !ramFilesystemIn(table, '/tmpfoo/x'),
    'CONTROL (ram): a sibling sharing a name prefix is not under the mount'
  );
  for (const cfg of configs) {
    check(
      listsGlobalSetup(fs.readFileSync(cfg, 'utf8')),
      `${path.relative(REPO, cfg)} lists the globalSetup`
    );
  }
  console.log(
    bad === 0 ? 'vitest-run-tmp controls: all passed' : `vitest-run-tmp controls: ${bad} failed`
  );
  process.exitCode = bad === 0 ? 0 : 1;
}

main();
