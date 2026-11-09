#!/usr/bin/env tsx
/**
 * Control harness for scripts/gates/check-docs-frontmatter.ts.
 *
 * The selftest proves the helpers; this proves the GATE, as invoked, on a full copy of the
 * real content tree, through its DOCS_FRONTMATTER_CONTENT_DIR seam (so nothing is written
 * into real source). Both directions:
 *
 *   1. the unchanged copy -> exit 0 (a gate that fails on everything gets switched off);
 *   2. the ru backup-destinations page with its tags written with en dashes, the exact
 *      shape fixed in 10eae6293b -> non-zero, naming that file and `tags`;
 *   3. the same page with its required `title` removed -> non-zero, naming `title`;
 *   4. an empty content root -> non-zero. Zero entries is "did not run", never "fine";
 *   5. the same empty root, the gate launched through a symlinked directory -> non-zero. Node reports
 *      the real path as the module's filename while argv[1] keeps the symlink, and a gate that
 *      compared the two literally skipped main() and exited 0 having checked nothing.
 *
 * Run: npx tsx scripts/__tests__/check-docs-frontmatter.control.ts
 */

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const GATE = path.join(REPO, 'scripts/gates/check-docs-frontmatter.ts');
const CONTENT = path.join(REPO, 'packages/www/src/content');
const TARGET = path.join('docs', 'ru', 'backup-destinations.md');

const run = (root: string, gate: string = GATE): { code: number; out: string } => {
  const r = spawnSync(process.execPath, ['--import', 'tsx', gate], {
    cwd: REPO,
    env: { ...process.env, DOCS_FRONTMATTER_CONTENT_DIR: root },
    encoding: 'utf8',
  });
  return { code: r.status ?? 1, out: `${r.stdout}${r.stderr}` };
};

let pass = 0;
let fail = 0;
const check = (name: string, ok: boolean, detail: string): void => {
  if (ok) {
    pass += 1;
    console.log(`  PASS  ${name}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name}\n${detail}`);
  }
};

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'docs-fm-control-'));
try {
  const root = path.join(tmp, 'content');
  fs.cpSync(CONTENT, root, { recursive: true });
  const target = path.join(root, TARGET);
  const original = fs.readFileSync(target, 'utf8');
  if (!/^tags:\n {2}- /m.test(original)) {
    throw new Error(
      `${TARGET} no longer carries a block tags list; repoint this control at a doc that does`
    );
  }

  const clean = run(root);
  check('the unchanged content tree passes', clean.code === 0, clean.out);

  fs.writeFileSync(
    target,
    original.replace(/^(tags:\n(?: {2}- [^\n]*\n)+)/m, (b) => b.replaceAll('  - ', '  \u2013 '))
  );
  const dash = run(root);
  check(
    'en-dash tags fail, naming the file and tags',
    dash.code !== 0 && dash.out.includes(TARGET) && dash.out.includes('tags: '),
    dash.out
  );

  fs.writeFileSync(target, original.replace(/^title: [^\n]*\n/m, ''));
  const noTitle = run(root);
  check(
    'a missing title fails, naming title',
    noTitle.code !== 0 && noTitle.out.includes(`${TARGET}: title:`),
    noTitle.out
  );

  const empty = path.join(tmp, 'empty');
  fs.mkdirSync(empty);
  const none = run(empty);
  check(
    'an empty content root fails as unseen, not as clean',
    none.code !== 0 && none.out.includes('below the floor'),
    none.out
  );

  const link = path.join(tmp, 'gates-link');
  fs.symlinkSync(path.dirname(GATE), link);
  const viaLink = run(empty, path.join(link, path.basename(GATE)));
  check(
    'a launch through a symlinked directory still runs the gate and reports',
    viaLink.code !== 0 && viaLink.out.includes('below the floor'),
    viaLink.out
  );
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log(`\ncontrol: ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
