/**
 * CI freshness check for packages/www/public/search-index.json.
 *
 * The search index is generated at Astro build time from
 * packages/www/src/content/{blog,docs} by
 * packages/www/scripts/generate-search-index.js — and then committed to git.
 * If someone edits a doc or blog post without re-running the build, the
 * committed index goes stale and users search against outdated content.
 *
 * This check regenerates the index into a tempfile and diffs against the
 * committed version. Fails fast with a fix command on drift.
 *
 * Run via: `npm run check:ci-search-index`
 */
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const GENERATOR = path.join(REPO_ROOT, 'packages/www/scripts/generate-search-index.js');
const COMMITTED = path.join(REPO_ROOT, 'packages/www/public/search-index.json');

function fail(msg: string): never {
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  ${msg}\n\n`);
  process.exit(1);
}

// Generator hardcodes its output path. Run it from a sandbox copy of
// packages/www/ ... actually it's simpler: run the generator as-is, then
// read the file it wrote and compare against git's HEAD:packages/www/public/search-index.json.
// To keep this non-destructive in dev, restore from git after comparing.
const tmpDir = mkdtempSync(path.join(tmpdir(), 'search-index-check-'));
const backupPath = path.join(tmpDir, 'backup.json');

let committedBefore: string;
try {
  committedBefore = readFileSync(COMMITTED, 'utf8');
} catch {
  fail(`Missing committed ${COMMITTED}. Did packages/www build ever run?`);
}

// Stash the working copy in tmpDir so we can restore it regardless of drift.
// copyFileSync (Node built-in) is portable — `cp` assumed unix.
copyFileSync(COMMITTED, backupPath);

try {
  execFileSync('node', [GENERATOR], {
    cwd: path.join(REPO_ROOT, 'packages/www'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
} catch (err) {
  // Restore before exiting on generator failure; otherwise CI leaves the
  // working copy potentially overwritten by a partial regeneration.
  copyFileSync(backupPath, COMMITTED);
  rmSync(tmpDir, { recursive: true, force: true });
  fail(`Generator script failed: ${(err as Error).message}`);
}

const regenerated = readFileSync(COMMITTED, 'utf8');

// Restore the committed version so this check leaves no side effects.
copyFileSync(backupPath, COMMITTED);
rmSync(tmpDir, { recursive: true, force: true });

if (committedBefore === regenerated) {
  process.stdout.write('\x1b[32mOK\x1b[0m    search-index.json is up-to-date\n');
  process.exit(0);
}

// Summarize the diff size for the failure message.
const committedSize = Buffer.byteLength(committedBefore, 'utf8');
const regeneratedSize = Buffer.byteLength(regenerated, 'utf8');
const sizeDelta = regeneratedSize - committedSize;

fail(
  `packages/www/public/search-index.json is stale.\n\n` +
    `  committed:   ${committedSize} bytes\n` +
    `  regenerated: ${regeneratedSize} bytes (${sizeDelta >= 0 ? '+' : ''}${sizeDelta})\n\n` +
    `Fix:\n` +
    `  cd packages/www && node scripts/generate-search-index.js\n` +
    `  git add public/search-index.json\n\n` +
    `(The index is rebuilt automatically on every \`npm run build\`, so the\n` +
    ` common cause is editing blog/docs without running a build before commit.)`
);
