#!/usr/bin/env node

import { execSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

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

function countMatchingLines(body, pattern) {
  const normalized = normalizeText(body).replace(/\n$/, '');
  if (!normalized) return 0;
  return normalized.split('\n').filter((line) => pattern.test(line)).length;
}

function countPaddingCommentLines(body) {
  return countMatchingLines(body, /^<!--\s*pad:[^>]+-->$/);
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

function tryFetchBaseRef(repoRoot, baseRef) {
  if (!baseRef) {
    return;
  }

  try {
    execSync(
      `git fetch --no-tags --depth=50 origin +refs/heads/${baseRef}:refs/remotes/origin/${baseRef}`,
      {
        cwd: repoRoot,
        stdio: ['ignore', 'ignore', 'ignore'],
      }
    );
  } catch {
    // Best effort only. Local/dev environments may not have network access.
  }
}

export function detectChangedFiles(repoRoot, baseRefArg) {
  const fromEnv = getEnvChangedFiles();
  if (fromEnv) {
    return fromEnv;
  }

  const baseRef = baseRefArg || process.env.GITHUB_BASE_REF || 'main';
  tryFetchBaseRef(repoRoot, baseRef);
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
    const staged = git(['diff', '--name-only', '--cached'], repoRoot);
    const unstaged = git(['diff', '--name-only'], repoRoot);
    return Array.from(new Set([...staged, ...unstaged]));
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

// ─── Git-based diff helpers ─────────────────────────────────────────

/**
 * Get file content at a specific git commit.
 */
function getFileAtCommit(repoRoot, commit, filePath) {
  try {
    return execSync(`git show ${commit}:${filePath}`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    // Try deepening clone
    try {
      execSync('git fetch --deepen=100', { cwd: repoRoot, stdio: 'ignore' });
      return execSync(`git show ${commit}:${filePath}`, {
        cwd: repoRoot,
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      });
    } catch {
      return null;
    }
  }
}

/**
 * Get the latest commit that touched a file.
 */
function getLatestCommitForFile(repoRoot, filePath) {
  try {
    return execSync(`git log -1 --format=%H -- ${filePath}`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }
}

/**
 * Split markdown body into sections by ## headings.
 */
function splitIntoSections(body) {
  const lines = body.split('\n');
  const sections = [];
  let currentHeading = '(intro)';
  let currentLines = [];

  for (const line of lines) {
    if (line.startsWith('## ')) {
      sections.push({ heading: currentHeading, body: currentLines.join('\n').trim() });
      currentHeading = line.trim();
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }

  sections.push({ heading: currentHeading, body: currentLines.join('\n').trim() });
  return sections.filter((s) => s.body || s.heading !== '(intro)');
}

/**
 * Compute a structured diff between old and new English content.
 * Returns null if sourceCommit is unavailable or git history is unreachable.
 */
function computeEnglishDiff(repoRoot, sourceCommit, enRel, currentParsed) {
  if (!sourceCommit) return null;

  const oldRaw = getFileAtCommit(repoRoot, sourceCommit, enRel);
  if (!oldRaw) return null;

  let oldParsed;
  try {
    const parsed = matter(oldRaw);
    oldParsed = { data: parsed.data ?? {}, content: parsed.content ?? '' };
  } catch {
    return null;
  }

  const diff = { frontmatter: [], sections: [] };

  // Frontmatter diff
  for (const field of ['title', 'description', 'category', 'author']) {
    const oldVal = String(oldParsed.data[field] ?? '');
    const newVal = String(currentParsed.data[field] ?? '');
    if (oldVal !== newVal) {
      diff.frontmatter.push({ field, old: oldVal, new: newVal });
    }
  }

  // Section diff
  const oldSections = splitIntoSections(oldParsed.content);
  const newSections = splitIntoSections(currentParsed.content);
  const oldMap = new Map(oldSections.map((s) => [s.heading, s.body]));
  const newMap = new Map(newSections.map((s) => [s.heading, s.body]));

  for (const [heading, body] of newMap) {
    if (!oldMap.has(heading)) {
      const lineCount = body.split('\n').length;
      diff.sections.push({ heading, type: 'added', lineCount, newValue: body });
    }
  }

  for (const [heading, body] of oldMap) {
    if (!newMap.has(heading)) {
      diff.sections.push({ heading, type: 'removed', oldValue: body });
    }
  }

  for (const [heading, newBody] of newMap) {
    const oldBody = oldMap.get(heading);
    if (oldBody !== undefined && oldBody !== newBody) {
      // Generate a brief summary of what changed
      const oldLines = oldBody.split('\n');
      const newLines = newBody.split('\n');
      const changedSnippets = [];
      // Show first few differing lines
      for (
        let i = 0;
        i < Math.max(oldLines.length, newLines.length) && changedSnippets.length < 3;
        i++
      ) {
        const ol = oldLines[i] ?? '';
        const nl = newLines[i] ?? '';
        if (ol !== nl) {
          if (ol) changedSnippets.push(`  - ${truncate(ol, 100)}`);
          if (nl) changedSnippets.push(`  + ${truncate(nl, 100)}`);
        }
      }
      diff.sections.push({ heading, type: 'modified', snippets: changedSnippets });
    }
  }

  return diff;
}

function truncate(str, maxLen) {
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen - 3) + '...';
}

/**
 * Format the diff into human/AI-readable suggestion text.
 */
function formatDiffSuggestion(diff, expectedHash, latestCommit) {
  const lines = [];

  if (diff.frontmatter.length > 0) {
    lines.push('  Frontmatter changes:');
    for (const f of diff.frontmatter) {
      lines.push(`    ${f.field}:`);
      lines.push(`      old: ${JSON.stringify(f.old)}`);
      lines.push(`      new: ${JSON.stringify(f.new)}`);
    }
  }

  const added = diff.sections.filter((s) => s.type === 'added');
  const removed = diff.sections.filter((s) => s.type === 'removed');
  const modified = diff.sections.filter((s) => s.type === 'modified');

  if (added.length > 0) {
    lines.push('  Sections added (translate and add these):');
    for (const s of added) {
      lines.push(`    + ${s.heading} (${s.lineCount} lines)`);
    }
  }

  if (removed.length > 0) {
    lines.push('  Sections removed (remove from translation):');
    for (const s of removed) {
      lines.push(`    - ${s.heading}`);
    }
  }

  if (modified.length > 0) {
    lines.push('  Sections modified (update translation for these):');
    for (const s of modified) {
      lines.push(`    ~ ${s.heading}`);
      if (s.snippets) {
        for (const snip of s.snippets) {
          lines.push(`      ${snip}`);
        }
      }
    }
  }

  lines.push(`  → Update the listed sections, then set:`);
  lines.push(`    sourceHash: "${expectedHash}"`);
  if (latestCommit) {
    lines.push(`    sourceCommit: "${latestCommit}"`);
  }

  return lines.join('\n');
}

// ─── Orphan detection ───────────────────────────────────────────────

/**
 * Find translated files whose English source no longer exists.
 */
function findOrphanedTranslations(repoRoot, languages) {
  const orphans = [];

  for (const collection of COLLECTIONS) {
    for (const lang of languages) {
      const langDir = path.join(repoRoot, 'src', 'content', collection, lang);
      if (!fs.existsSync(langDir)) continue;

      const stack = [''];
      while (stack.length > 0) {
        const rel = stack.pop();
        const abs = path.join(langDir, rel);
        let entries;
        try {
          entries = fs.readdirSync(abs, { withFileTypes: true });
        } catch {
          continue;
        }
        for (const entry of entries) {
          const nextRel = rel ? path.join(rel, entry.name) : entry.name;
          if (entry.isDirectory()) {
            stack.push(nextRel);
            continue;
          }
          if (!entry.name.endsWith('.md')) continue;

          const enPath = path.join(repoRoot, 'src', 'content', collection, 'en', nextRel);
          if (!fs.existsSync(enPath)) {
            const langRel = `packages/www/src/content/${collection}/${lang}/${nextRel.replaceAll('\\', '/')}`;
            orphans.push({
              rule: 'translation-orphaned',
              file: langRel,
              message: `English source file no longer exists — this translation is orphaned`,
              suggestion: `Delete ${langRel} or investigate if the English source was renamed`,
            });
          }
        }
      }
    }
  }

  return orphans;
}

// ─── Main validation ────────────────────────────────────────────────

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

  // Resolve the repo root for git operations (monorepo root, not www root)
  const gitRepoRoot = path.resolve(repoRoot, '..', '..');

  const englishCandidates = strictAll
    ? getAllEnglishContentPaths(repoRoot)
    : discovered.filter((p) => SOURCE_PREFIX_RE.test(p));

  const englishFiles = englishCandidates
    .filter((p) => !isExcludedEnglishPath(p))
    .filter((p) => fs.existsSync(path.join(gitRepoRoot, p)));

  for (const enRel of englishFiles) {
    const enAbs = path.join(gitRepoRoot, enRel);
    const enParsed = parseMarkdown(enAbs);

    const expectedHash = computeSourceHash(enParsed.data, enParsed.content);
    const enLineCount = countBodyLines(enParsed.content);
    const latestEnCommit = getLatestCommitForFile(gitRepoRoot, enRel);

    for (const lang of languages) {
      const langRel = enRel.replace('/en/', `/${lang}/`);
      const langAbs = path.join(gitRepoRoot, langRel);
      const langChanged = changedSet.has(langRel);

      if (!fs.existsSync(langAbs)) {
        // Provide section summary for AI to translate
        const sections = splitIntoSections(enParsed.content);
        const sectionList = sections.map((s) => s.heading).filter((h) => h !== '(intro)');
        errors.push({
          rule: 'translation-missing',
          file: langRel,
          message: `Missing translation for changed English source ${enRel}`,
          suggestion:
            `Create ${langRel} with translated content.\n` +
            `  English doc has ${enLineCount} lines, sections: ${sectionList.join(', ')}\n` +
            `  Set sourceHash: "${expectedHash}"` +
            (latestEnCommit ? ` and sourceCommit: "${latestEnCommit}"` : ''),
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
      const localePaddingCount = countPaddingCommentLines(langParsed.content);
      const minimumLineCount = Math.max(10, Math.floor(enLineCount * 0.4));

      if (localeLineCount < minimumLineCount) {
        errors.push({
          rule: 'translation-line-count-too-low',
          file: langRel,
          message: `Translated content for ${enRel} is unusually short (${lang}=${localeLineCount}, expected at least ${minimumLineCount} from en=${enLineCount})`,
          suggestion:
            'Expand the translation so it covers the full source content, not only a shortened summary',
        });
      }

      if (localePaddingCount > 0) {
        errors.push({
          rule: 'translation-padding-comments-forbidden',
          file: langRel,
          message: `Padding comments detected in ${langRel} (${localePaddingCount} line(s))`,
          suggestion:
            'Remove synthetic padding comments and keep translations structurally aligned with real content',
        });
      }

      const actualHash = String(langParsed.data.sourceHash ?? '').trim();
      if (!actualHash) {
        errors.push({
          rule: 'translation-source-hash-missing',
          file: langRel,
          message: `Missing sourceHash for translation of ${enRel}`,
          suggestion:
            `Set sourceHash: "${expectedHash}"` +
            (latestEnCommit ? ` and sourceCommit: "${latestEnCommit}"` : '') +
            ' in frontmatter',
        });
        continue;
      }

      if (actualHash !== expectedHash) {
        const sourceCommit = String(langParsed.data.sourceCommit ?? '').trim();

        // Compute structured diff if sourceCommit is available
        const diff = computeEnglishDiff(gitRepoRoot, sourceCommit, enRel, enParsed);

        let suggestion;
        if (diff && (diff.frontmatter.length > 0 || diff.sections.length > 0)) {
          suggestion =
            `English source changed since last translation sync.\n` +
            formatDiffSuggestion(diff, expectedHash, latestEnCommit);
        } else if (sourceCommit) {
          suggestion =
            `Update translation and set sourceHash: "${expectedHash}"` +
            (latestEnCommit ? ` and sourceCommit: "${latestEnCommit}"` : '') +
            `\n  (Could not compute diff — sourceCommit ${sourceCommit} may be unreachable)`;
        } else {
          suggestion =
            `Update translation and set sourceHash: "${expectedHash}"` +
            (latestEnCommit ? ` and sourceCommit: "${latestEnCommit}"` : '') +
            `\n  (Add sourceCommit to frontmatter to enable diff-based sync suggestions)`;
        }

        errors.push({
          rule: 'translation-source-hash-mismatch',
          file: langRel,
          message: `sourceHash (${actualHash}) does not match English source hash (${expectedHash})`,
          suggestion,
        });
      }
    }
  }

  // Check for orphaned translations (English deleted, translation remains)
  if (strictAll) {
    errors.push(...findOrphanedTranslations(repoRoot, languages));
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
