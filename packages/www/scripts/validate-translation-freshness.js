#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import matter from 'gray-matter';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');

export const SUPPORTED_LANGUAGES = ['de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];
const COLLECTIONS = ['docs', 'blog'];
const SOURCE_PREFIX_RE = /^packages\/www\/src\/content\/(docs|blog)\/en\/.+\.md$/;
const EXCLUDED_EN_PATHS = {
  docs: ['packages/www/src/content/docs/en/cli/'],
  blog: [],
};

function normalizeText(input) {
  return (
    String(input ?? '')
      .replace(/\r\n/g, '\n')
      .trimEnd() + '\n'
  );
}

function countBodyLines(body) {
  const normalized = normalizeText(body).replace(/\n$/, '');
  if (!normalized) return 0;
  return normalized.split('\n').length;
}

function isExcludedEnglishPath(relPath) {
  for (const collection of COLLECTIONS) {
    const prefixes = EXCLUDED_EN_PATHS[collection] ?? [];
    if (prefixes.some((p) => relPath.startsWith(p))) {
      return true;
    }
  }
  return false;
}

export function computeSourceHash(frontmatter, body) {
  const payload = {
    title: frontmatter.title ?? '',
    description: frontmatter.description ?? '',
    category: frontmatter.category ?? '',
    author: frontmatter.author ?? '',
    tags: Array.isArray(frontmatter.tags) ? frontmatter.tags : [],
    body: normalizeText(body),
  };

  const digest = crypto.createHash('sha256').update(JSON.stringify(payload)).digest('hex');
  return digest.slice(0, 16);
}

function parseMarkdown(filePath) {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const parsed = matter(raw);
  return {
    data: parsed.data ?? {},
    content: parsed.content ?? '',
  };
}

function getEnvChangedFiles() {
  const raw = process.env.TRANSLATION_FRESHNESS_CHANGED_FILES;
  if (!raw) {
    return null;
  }

  return raw
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function git(args, cwd) {
  return execSync(`git ${args.join(' ')}`, {
    cwd,
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  })
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export function detectChangedFiles(repoRoot, baseRefArg) {
  const fromEnv = getEnvChangedFiles();
  if (fromEnv) {
    return fromEnv;
  }

  const baseRef = baseRefArg || process.env.GITHUB_BASE_REF || 'main';
  const candidates = [`origin/${baseRef}`, baseRef];

  for (const candidate of candidates) {
    try {
      git(['rev-parse', '--verify', candidate], repoRoot);
      const mergeBase = git(['merge-base', 'HEAD', candidate], repoRoot)[0];
      const committed = git(['diff', '--name-only', `${mergeBase}...HEAD`], repoRoot);
      const staged = git(['diff', '--name-only', '--cached'], repoRoot);
      const unstaged = git(['diff', '--name-only'], repoRoot);
      return Array.from(new Set([...committed, ...staged, ...unstaged]));
    } catch {
      // try next strategy
    }
  }

  try {
    const committed = git(['diff', '--name-only', 'HEAD^...HEAD'], repoRoot);
    const staged = git(['diff', '--name-only', '--cached'], repoRoot);
    const unstaged = git(['diff', '--name-only'], repoRoot);
    return Array.from(new Set([...committed, ...staged, ...unstaged]));
  } catch {
    // fallback below
  }

  try {
    const lastCommit = git(['show', '--pretty=', '--name-only', 'HEAD'], repoRoot);
    const staged = git(['diff', '--name-only', '--cached'], repoRoot);
    const unstaged = git(['diff', '--name-only'], repoRoot);
    return Array.from(new Set([...lastCommit, ...staged, ...unstaged]));
  } catch {
    return [];
  }
}

function getAllEnglishContentPaths(repoRoot) {
  const result = [];

  for (const collection of COLLECTIONS) {
    const base = path.join(repoRoot, 'src', 'content', collection, 'en');
    if (!fs.existsSync(base)) {
      continue;
    }

    const stack = [''];
    while (stack.length > 0) {
      const rel = stack.pop();
      const abs = path.join(base, rel);
      const entries = fs.readdirSync(abs, { withFileTypes: true });
      for (const entry of entries) {
        const nextRel = rel ? path.join(rel, entry.name) : entry.name;
        if (entry.isDirectory()) {
          stack.push(nextRel);
          continue;
        }
        if (!entry.name.endsWith('.md')) {
          continue;
        }
        result.push(`packages/www/src/content/${collection}/en/${nextRel.replaceAll('\\', '/')}`);
      }
    }
  }

  return result;
}

export function validateTranslationFreshness({
  repoRoot = ROOT_DIR,
  changedFiles,
  strictAll = false,
  baseRef,
  languages = SUPPORTED_LANGUAGES,
} = {}) {
  const errors = [];
  const warnings = [];

  const discovered = changedFiles ?? detectChangedFiles(repoRoot, baseRef);
  const changedSet = new Set(discovered);

  const englishCandidates = strictAll
    ? getAllEnglishContentPaths(repoRoot)
    : discovered.filter((p) => SOURCE_PREFIX_RE.test(p));

  const englishFiles = englishCandidates
    .filter((p) => !isExcludedEnglishPath(p))
    .filter((p) => fs.existsSync(path.join(path.resolve(repoRoot, '..', '..'), p)));

  for (const enRel of englishFiles) {
    const enAbs = path.join(path.resolve(repoRoot, '..', '..'), enRel);
    const enParsed = parseMarkdown(enAbs);

    const pending = enParsed.data.translationPending === true;
    const pendingReason = String(enParsed.data.translationPendingReason ?? '').trim();

    if (pending && pendingReason.length === 0) {
      errors.push({
        rule: 'translation-pending-reason',
        file: enRel,
        message:
          'translationPending=true requires translationPendingReason to explain why updates are deferred',
        suggestion:
          'Add translationPendingReason with a concrete justification and expected follow-up',
      });
      continue;
    }

    if (pending) {
      warnings.push({
        rule: 'translation-pending',
        file: enRel,
        message: `Translations deferred: ${pendingReason}`,
      });
      continue;
    }

    const expectedHash = computeSourceHash(enParsed.data, enParsed.content);
    const enLineCount = countBodyLines(enParsed.content);

    for (const lang of languages) {
      const langRel = enRel.replace('/en/', `/${lang}/`);
      const langAbs = path.join(path.resolve(repoRoot, '..', '..'), langRel);
      const langChanged = changedSet.has(langRel);

      if (!fs.existsSync(langAbs)) {
        errors.push({
          rule: 'translation-missing',
          file: langRel,
          message: `Missing translation for changed English source ${enRel}`,
          suggestion: `Create ${langRel} or mark ${enRel} with translationPending + translationPendingReason`,
        });
        continue;
      }

      if (!langChanged && !strictAll) {
        errors.push({
          rule: 'translation-not-updated',
          file: langRel,
          message: `English file changed but locale file was not updated in this PR (${enRel})`,
          suggestion: `Update ${langRel} and set sourceHash=${expectedHash}`,
        });
      }

      const langParsed = parseMarkdown(langAbs);
      const localeLineCount = countBodyLines(langParsed.content);
      if (localeLineCount !== enLineCount) {
        errors.push({
          rule: 'translation-line-count-mismatch',
          file: langRel,
          message: `Line count mismatch for ${enRel} (en=${enLineCount}, ${lang}=${localeLineCount})`,
          suggestion: 'Align translated markdown structure/line count with the English source',
        });
      }

      const actualHash = String(langParsed.data.sourceHash ?? '').trim();
      if (!actualHash) {
        errors.push({
          rule: 'translation-source-hash-missing',
          file: langRel,
          message: `Missing sourceHash for translation of ${enRel}`,
          suggestion: `Set sourceHash: "${expectedHash}" in frontmatter`,
        });
        continue;
      }

      if (actualHash !== expectedHash) {
        errors.push({
          rule: 'translation-source-hash-mismatch',
          file: langRel,
          message: `sourceHash (${actualHash}) does not match English source hash (${expectedHash})`,
          suggestion: `Update translation and set sourceHash: "${expectedHash}"`,
        });
      }
    }
  }

  return { errors, warnings, checkedEnglishFiles: englishFiles };
}

function printResults(result, strictAll) {
  const { errors, warnings, checkedEnglishFiles } = result;

  console.log('Translation Freshness Validation');
  console.log('============================================================');
  console.log(`Mode: ${strictAll ? 'strict-all' : 'pr-diff'}`);
  console.log(`English files checked: ${checkedEnglishFiles.length}`);

  if (warnings.length > 0) {
    console.log(`Warnings: ${warnings.length}`);
    for (const warning of warnings) {
      console.log(`  [${warning.rule}] ${warning.file}`);
      console.log(`    ${warning.message}`);
    }
  }

  if (errors.length === 0) {
    console.log('\n\x1b[32m✓ Translation freshness checks passed\x1b[0m');
    return true;
  }

  const grouped = new Map();
  for (const err of errors) {
    if (!grouped.has(err.rule)) {
      grouped.set(err.rule, []);
    }
    grouped.get(err.rule).push(err);
  }

  console.log(
    `\n\x1b[31m✗ Translation freshness failed (${errors.length} error${errors.length === 1 ? '' : 's'})\x1b[0m`
  );
  for (const [rule, issues] of grouped.entries()) {
    console.log(`\n[${rule}] (${issues.length})`);
    for (const issue of issues) {
      console.log(`  - ${issue.file}`);
      console.log(`    ${issue.message}`);
      if (issue.suggestion) {
        console.log(`    -> ${issue.suggestion}`);
      }
    }
  }

  return false;
}

function parseArgs(argv) {
  const args = { strictAll: false, baseRef: undefined };

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--strict-all') {
      args.strictAll = true;
    } else if (argv[i] === '--base-ref') {
      args.baseRef = argv[i + 1];
      i += 1;
    }
  }

  return args;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = parseArgs(process.argv.slice(2));
  const result = validateTranslationFreshness({
    strictAll: args.strictAll,
    baseRef: args.baseRef,
  });
  const ok = printResults(result, args.strictAll);
  process.exit(ok ? 0 : 1);
}
