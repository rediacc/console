/**
 * CI freshness check for packages/www/public/search-index*.json.
 *
 * Per-locale indexes are generated at Astro build time from
 * packages/www/src/content/{blog,docs} by
 * packages/www/scripts/generate-search-index.js — and committed to git.
 * If someone edits a doc or blog post without re-running the build, the
 * committed indexes go stale and users search against outdated content.
 *
 * This check regenerates all indexes into a sandboxed copy and diffs each
 * against the committed version. Fails fast with a fix command on drift.
 *
 * Run via: `npm run check:ci-search-index`
 */
import { execFileSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const GENERATOR = path.join(REPO_ROOT, 'packages/www/scripts/generate-search-index.js');
const PUBLIC_DIR = path.join(REPO_ROOT, 'packages/www/public');
const INDEX_PATTERN = /^search-index(?:-[a-z]{2})?\.json$/;

function fail(msg: string): never {
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  ${msg}\n\n`);
  process.exit(1);
}

if (!existsSync(GENERATOR)) {
  fail(`Missing generator ${GENERATOR}. Was the script moved or renamed?`);
}

// Discover the set of committed index files. We can't hardcode locales
// because adding a new locale should "just work" once the indexer detects
// its content directory. The pattern matches search-index.json (legacy
// fallback) and search-index-<lang>.json (per-locale).
const committedFiles = readdirSync(PUBLIC_DIR)
  .filter((f) => INDEX_PATTERN.test(f))
  .sort();

if (committedFiles.length === 0) {
  fail(
    `No committed search-index*.json files in ${PUBLIC_DIR}.\n` +
      `Did packages/www build ever run?`
  );
}

// Stash committed copies so we can restore regardless of drift outcome.
// copyFileSync is portable — `cp` assumed unix.
const tmpDir = mkdtempSync(path.join(tmpdir(), 'search-index-check-'));
const committedBefore = new Map<string, string>();
const backupPaths = new Map<string, string>();
for (const file of committedFiles) {
  const src = path.join(PUBLIC_DIR, file);
  const backup = path.join(tmpDir, file);
  committedBefore.set(file, readFileSync(src, 'utf8'));
  copyFileSync(src, backup);
  backupPaths.set(file, backup);
}

const restore = () => {
  // Sweep any new index files the generator just produced (e.g. for a freshly
  // added locale) so the check is truly non-destructive in dev — otherwise
  // those files would persist after the script exits, polluting git status.
  for (const file of readdirSync(PUBLIC_DIR)) {
    if (INDEX_PATTERN.test(file) && !committedFiles.includes(file)) {
      rmSync(path.join(PUBLIC_DIR, file), { force: true });
    }
  }
  for (const file of committedFiles) {
    copyFileSync(backupPaths.get(file)!, path.join(PUBLIC_DIR, file));
  }
  rmSync(tmpDir, { recursive: true, force: true });
};

try {
  execFileSync('node', [GENERATOR], {
    cwd: path.join(REPO_ROOT, 'packages/www'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
} catch (err) {
  restore();
  fail(`Generator script failed: ${(err as Error).message}`);
}

// The generator may have created files we didn't have committed (new locale
// added) or removed ones we did (locale removed). Both are drift.
const regeneratedFiles = readdirSync(PUBLIC_DIR)
  .filter((f) => INDEX_PATTERN.test(f))
  .sort();

const allFiles = [...new Set([...committedFiles, ...regeneratedFiles])].sort();
const stale: { file: string; committedSize: number; regeneratedSize: number; reason: string }[] =
  [];

for (const file of allFiles) {
  const filePath = path.join(PUBLIC_DIR, file);
  const wasCommitted = committedFiles.includes(file);
  const exists = existsSync(filePath);

  if (!wasCommitted && exists) {
    const regenerated = readFileSync(filePath, 'utf8');
    stale.push({
      file,
      committedSize: 0,
      regeneratedSize: Buffer.byteLength(regenerated, 'utf8'),
      reason: 'new file (not committed)',
    });
    continue;
  }
  if (wasCommitted && !exists) {
    const before = committedBefore.get(file)!;
    stale.push({
      file,
      committedSize: Buffer.byteLength(before, 'utf8'),
      regeneratedSize: 0,
      reason: 'committed but no longer generated',
    });
    continue;
  }
  if (!wasCommitted && !exists) continue;

  const before = committedBefore.get(file)!;
  const regenerated = readFileSync(filePath, 'utf8');
  if (before !== regenerated) {
    stale.push({
      file,
      committedSize: Buffer.byteLength(before, 'utf8'),
      regeneratedSize: Buffer.byteLength(regenerated, 'utf8'),
      reason: 'content drift',
    });
  }
}

restore();

if (stale.length === 0) {
  process.stdout.write(
    `\x1b[32mOK\x1b[0m    ${committedFiles.length} search-index file(s) up-to-date\n`
  );
  process.exit(0);
}

const lines = stale.map((s) => {
  const delta = s.regeneratedSize - s.committedSize;
  const sign = delta >= 0 ? '+' : '';
  return `  ${s.file.padEnd(28)} ${s.reason} (${s.committedSize} → ${s.regeneratedSize} bytes, ${sign}${delta})`;
});

fail(
  `${stale.length} search-index file(s) stale:\n\n${lines.join('\n')}\n\n` +
    `Fix:\n` +
    `  cd packages/www && node scripts/generate-search-index.js\n` +
    `  git add public/search-index*.json\n\n` +
    `(The indexes are rebuilt automatically on every \`npm run build\`, so the\n` +
    ` common cause is editing blog/docs without running a build before commit.)`
);
