import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import matter from 'gray-matter';

import {
  computeSourceHash,
  validateTranslationFreshness,
} from './validate-translation-freshness.js';

const LANGS = ['de', 'es'];

function writeDoc(repoRoot, lang, slug, frontmatter, body) {
  const file = path.join(repoRoot, 'src', 'content', 'docs', lang, `${slug}.md`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, matter.stringify(body, frontmatter), 'utf-8');
  return file;
}

function setupFixture() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'translation-freshness-'));
  const repoRoot = path.join(temp, 'packages', 'www');
  fs.mkdirSync(repoRoot, { recursive: true });
  return { temp, repoRoot };
}

test('fails when english changed but locales are not updated', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'Guide', description: 'desc', category: 'Guides', language: 'en' };
  writeDoc(repoRoot, 'en', 'sample', enFrontmatter, 'Body v2');

  for (const lang of LANGS) {
    writeDoc(repoRoot, lang, 'sample', {
      title: 'Guide',
      description: 'desc',
      category: 'Guides',
      language: lang,
      sourceHash: 'oldhash',
    }, 'Old body');
  }

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: ['packages/www/src/content/docs/en/sample.md'],
    languages: LANGS,
  });

  assert.ok(result.errors.some((e) => e.rule === 'translation-not-updated'));
  assert.ok(result.errors.some((e) => e.rule === 'translation-source-hash-mismatch'));
});

test('passes when locale files are updated with matching sourceHash', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'Fresh', description: 'desc', category: 'Guides', language: 'en' };
  const enBody = 'Fresh body\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\nline 8\nline 9\nline 10';
  writeDoc(repoRoot, 'en', 'fresh-doc', enFrontmatter, enBody);

  const hash = computeSourceHash(enFrontmatter, enBody);

  for (const lang of LANGS) {
    writeDoc(repoRoot, lang, 'fresh-doc', {
      title: 'Fresh localized',
      description: 'localized desc',
      category: 'Guides',
      language: lang,
      sourceHash: hash,
    }, `Localized body ${lang}\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\nline 8\nline 9\nline 10`);
  }

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: [
      'packages/www/src/content/docs/en/fresh-doc.md',
      'packages/www/src/content/docs/de/fresh-doc.md',
      'packages/www/src/content/docs/es/fresh-doc.md',
    ],
    languages: LANGS,
  });

  assert.equal(result.errors.length, 0);
});

test('translation-missing error includes section summary', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'Sections', description: 'desc', category: 'Guides', language: 'en' };
  const enBody = '## Getting Started\n\nIntro text.\n\n## Configuration\n\nConfig details.';
  writeDoc(repoRoot, 'en', 'sections-doc', enFrontmatter, enBody);

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: ['packages/www/src/content/docs/en/sections-doc.md'],
    languages: LANGS,
  });

  const missingErrors = result.errors.filter((e) => e.rule === 'translation-missing');
  assert.ok(missingErrors.length > 0, 'should have translation-missing errors');
  // Suggestion should include section headings
  assert.ok(missingErrors[0].suggestion.includes('## Getting Started'));
  assert.ok(missingErrors[0].suggestion.includes('## Configuration'));
});

test('hash mismatch without sourceCommit gives fallback suggestion', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'Changed', description: 'new desc', category: 'Guides', language: 'en' };
  writeDoc(repoRoot, 'en', 'changed-doc', enFrontmatter, 'New body content');

  const hash = computeSourceHash(enFrontmatter, 'New body content');

  for (const lang of LANGS) {
    writeDoc(repoRoot, lang, 'changed-doc', {
      title: 'Old title',
      description: 'old desc',
      category: 'Guides',
      language: lang,
      sourceHash: 'stale-hash',
      // no sourceCommit — should get fallback message
    }, 'Old body');
  }

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: [
      'packages/www/src/content/docs/en/changed-doc.md',
      'packages/www/src/content/docs/de/changed-doc.md',
      'packages/www/src/content/docs/es/changed-doc.md',
    ],
    languages: LANGS,
  });

  const mismatchErrors = result.errors.filter((e) => e.rule === 'translation-source-hash-mismatch');
  assert.ok(mismatchErrors.length > 0);
  // Without sourceCommit, suggestion should mention adding sourceCommit
  assert.ok(mismatchErrors[0].suggestion.includes('sourceCommit'));
  assert.ok(mismatchErrors[0].suggestion.includes(hash));
});

test('missing sourceHash gives suggestion with sourceHash value', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'NoHash', description: 'desc', category: 'Guides', language: 'en' };
  writeDoc(repoRoot, 'en', 'no-hash', enFrontmatter, 'Body');

  const hash = computeSourceHash(enFrontmatter, 'Body');

  for (const lang of LANGS) {
    writeDoc(repoRoot, lang, 'no-hash', {
      title: 'Translated',
      language: lang,
      // no sourceHash at all
    }, 'Translated body');
  }

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: [
      'packages/www/src/content/docs/en/no-hash.md',
      'packages/www/src/content/docs/de/no-hash.md',
      'packages/www/src/content/docs/es/no-hash.md',
    ],
    languages: LANGS,
  });

  const missingHash = result.errors.filter((e) => e.rule === 'translation-source-hash-missing');
  assert.ok(missingHash.length > 0);
  assert.ok(missingHash[0].suggestion.includes(hash));
});

test('orphaned translations detected in strict-all mode', () => {
  const { repoRoot } = setupFixture();

  // Create a translated file with no English source
  writeDoc(repoRoot, 'de', 'deleted-doc', {
    title: 'Gelöscht',
    language: 'de',
    sourceHash: 'abc123',
  }, 'Orphaned content');

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: [],
    strictAll: true,
    languages: ['de'],
  });

  const orphanErrors = result.errors.filter((e) => e.rule === 'translation-orphaned');
  assert.ok(orphanErrors.length > 0, 'should detect orphaned translation');
  assert.ok(orphanErrors[0].file.includes('deleted-doc.md'));
});
