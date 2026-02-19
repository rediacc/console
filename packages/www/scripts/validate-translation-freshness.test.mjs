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

test('passes when translationPending has a reason', () => {
  const { repoRoot } = setupFixture();

  writeDoc(
    repoRoot,
    'en',
    'pending-doc',
    {
      title: 'Pending',
      description: 'desc',
      category: 'Guides',
      language: 'en',
      translationPending: true,
      translationPendingReason: 'Awaiting legal review across locales',
    },
    'Pending body'
  );

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: ['packages/www/src/content/docs/en/pending-doc.md'],
    languages: LANGS,
  });

  assert.equal(result.errors.length, 0);
});

test('fails when translationPending is true but reason is missing', () => {
  const { repoRoot } = setupFixture();

  writeDoc(
    repoRoot,
    'en',
    'pending-without-reason',
    {
      title: 'Pending',
      description: 'desc',
      category: 'Guides',
      language: 'en',
      translationPending: true,
    },
    'Pending body'
  );

  const result = validateTranslationFreshness({
    repoRoot,
    changedFiles: ['packages/www/src/content/docs/en/pending-without-reason.md'],
    languages: LANGS,
  });

  assert.ok(result.errors.some((e) => e.rule === 'translation-pending-reason'));
});

test('passes when locale files are updated with matching sourceHash', () => {
  const { repoRoot } = setupFixture();

  const enFrontmatter = { title: 'Fresh', description: 'desc', category: 'Guides', language: 'en' };
  const enBody = 'Fresh body';
  writeDoc(repoRoot, 'en', 'fresh-doc', enFrontmatter, enBody);

  const hash = computeSourceHash(enFrontmatter, enBody);

  for (const lang of LANGS) {
    writeDoc(repoRoot, lang, 'fresh-doc', {
      title: 'Fresh localized',
      description: 'localized desc',
      category: 'Guides',
      language: lang,
      sourceHash: hash,
    }, `Localized body ${lang}`);
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
