/**
 * CI freshness check for packages/www/public/search-index*.json.
 *
 * Per-locale indexes are generated from packages/www/src/content/{blog,docs} by
 * packages/www/scripts/generate-search-index.js. The build writes its own copy into
 * the build output; the committed public/ copies are what `npm run dev` serves, and
 * only `--write-public` refreshes them. A doc or blog edit without that step leaves
 * them stale, and a reader of the dev site searches outdated content.
 *
 * This check regenerates all indexes into a temp directory (`--out`) and diffs each
 * against the committed version, so it never writes the tree. Fails fast with a fix
 * command on drift.
 *
 * Run via: `npm run check:ci-search-index`
 *
 * ---- gate ----
 * step: Search index
 * needs: node
 * id: check:ci-search-index
 * lane: quality-i18n
 * ---- end gate ----
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const GENERATOR = path.join(REPO_ROOT, 'packages/www/scripts/generate-search-index.js');
const PUBLIC_DIR = path.join(REPO_ROOT, 'packages/www/public');
// Matches the legacy combined file (`search-index.json`, kept as a byte- identical copy of the English file for backward compat) plus every per-locale file (`search-index-<lang>.json`). Restricted to lowercase 2-letter codes so unrelated public/ artifacts aren't swept by mistake.
const INDEX_PATTERN = /^search-index(?:-[a-z]{2})?\.json$/;

const tmpDir = mkdtempSync(path.join(tmpdir(), 'search-index-check-'));

function fail(msg: string): never {
  rmSync(tmpDir, { recursive: true, force: true });
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  ${msg}\n\n`);
  process.exit(1);
}

if (!existsSync(GENERATOR)) {
  fail(`Missing generator ${GENERATOR}. Was the script moved or renamed?`);
}

// Discover the set of committed index files. We can't hardcode locales because adding a new locale should "just work" once the indexer detects its content directory. The pattern matches search-index.json (legacy fallback) and search-index-<lang>.json (per-locale).
const committedFiles = readdirSync(PUBLIC_DIR)
  .filter((f) => INDEX_PATTERN.test(f))
  .sort();

if (committedFiles.length === 0) {
  fail(
    `No committed search-index*.json files in ${PUBLIC_DIR}.\n` +
      `Regenerate them: cd packages/www && node scripts/generate-search-index.js --write-public`
  );
}

try {
  execFileSync('node', [GENERATOR, '--out', tmpDir], {
    cwd: path.join(REPO_ROOT, 'packages/www'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
} catch (err) {
  fail(`Generator script failed: ${(err as Error).message}`);
}

// The generator may have created files we didn't have committed (new locale added) or removed ones we did (locale removed). Both are drift.
const regeneratedFiles = readdirSync(tmpDir)
  .filter((f) => INDEX_PATTERN.test(f))
  .sort();

const allFiles = [...new Set([...committedFiles, ...regeneratedFiles])].sort(
  (a, b) => Number(a > b) - Number(a < b)
);
const stale: { file: string; committedSize: number; regeneratedSize: number; reason: string }[] =
  [];

const committedText = (file: string): string => readFileSync(path.join(PUBLIC_DIR, file), 'utf8');

for (const file of allFiles) {
  const filePath = path.join(tmpDir, file);
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
    stale.push({
      file,
      committedSize: Buffer.byteLength(committedText(file), 'utf8'),
      regeneratedSize: 0,
      reason: 'committed but no longer generated',
    });
    continue;
  }
  if (!wasCommitted && !exists) continue;

  const before = committedText(file);
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

/**
 * CONTENT ASSERTION: an index must not ship an unresolved `{{t:...}}` placeholder.
 *
 * The freshness half of this gate could never have caught this, and did not: it compares
 * the committed index against a freshly generated one, so a placeholder present in BOTH
 * is agreement, not a finding. Measured on 2026-08-18, every locale index carried 2,122 of
 * them and this gate was green. A reader searching the docs for "backup" got a result
 * titled `{{t:cli.docs.sectionTitles.backup}}`.
 *
 * The rendered pages were clean the whole time, because
 * `src/plugins/remark-resolve-translations.ts` resolves them inside Astro's markdown
 * pipeline. `scripts/generate-search-index.js` reads the markdown itself and had no idea
 * they existed. Both now share `src/plugins/translation-keys.mjs`, and this assertion is
 * what stops them drifting apart again.
 */
const countPlaceholders = (text: string): string[] =>
  text.match(/\{\{t:[a-zA-Z]+\.[a-zA-Z0-9_.]+\}\}/g) ?? [];

// CONTROL, both directions, inline on every run. A detector that matches nothing reports a clean index forever, which is precisely the failure this assertion exists to end.
if (countPlaceholders('a {{t:cli.docs.tableHeaders.flag}} b').length !== 1) {
  fail(
    'control failed: the placeholder detector did not match a known-good placeholder.\n' +
      '  Every "no unresolved placeholders" result below would have been vacuous.'
  );
}
if (countPlaceholders('a plain sentence with no keys in it').length !== 0) {
  fail('control failed: the placeholder detector matched text containing no placeholder.');
}

const unresolved: { file: string; count: number; sample: string }[] = [];
for (const file of regeneratedFiles) {
  const filePath = path.join(tmpDir, file);
  if (!existsSync(filePath)) continue;
  const hits = countPlaceholders(readFileSync(filePath, 'utf8'));
  if (hits.length > 0) {
    unresolved.push({
      file,
      count: hits.length,
      sample: [...new Set(hits)].slice(0, 3).join(', '),
    });
  }
}

rmSync(tmpDir, { recursive: true, force: true });

if (unresolved.length > 0) {
  const total = unresolved.reduce((n, u) => n + u.count, 0);
  fail(
    `${total} unresolved translation placeholder(s) in ${unresolved.length} search-index file(s):\n\n` +
      unresolved
        .map((u) => `  ${u.file.padEnd(28)} ${u.count} occurrence(s)  e.g. ${u.sample}`)
        .join('\n') +
      `\n\nThese ship to readers as literal text in search results.\n` +
      `Fix: resolution lives in packages/www/src/plugins/translation-keys.mjs and is used by\n` +
      `BOTH remark-resolve-translations.ts (rendered pages) and generate-search-index.js\n` +
      `(the index). A placeholder surviving here means the index path stopped calling it,\n` +
      `or the key is genuinely missing from packages/cli/src/i18n/locales/<lang>/.`
  );
}

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
    `  cd packages/www && node scripts/generate-search-index.js --write-public\n` +
    `  git add public/search-index*.json\n\n` +
    `(A build writes its index into dist/ and never refreshes these committed copies,\n` +
    ` so editing blog/docs without the command above leaves them stale.)`
);
