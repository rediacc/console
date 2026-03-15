#!/usr/bin/env node
/**
 * One-time migration script to add sourceCommit to:
 * 1. Translated markdown files (frontmatter)
 * 2. JSON hash manifests ($meta.sourceCommit)
 *
 * For markdown: walks git history to find the commit where the English file
 * produced the sourceHash stored in the translation's frontmatter.
 *
 * For JSON: uses the latest commit that touched the English source files.
 *
 * Usage:
 *   npx tsx scripts/i18n-backfill-commits.ts [--dry-run]
 */

import { execSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getFileAtCommit, getLatestCommitForFile } from './utils/translation-diff.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const DRY_RUN = process.argv.includes('--dry-run');

const SUPPORTED_LANGUAGES = ['de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];
const COLLECTIONS = ['docs', 'blog'];
const WWW_ROOT = path.join(REPO_ROOT, 'packages/www');

// ─── Simple frontmatter parser (avoids gray-matter dependency) ──────

interface ParsedMarkdown {
  data: Record<string, unknown>;
  content: string;
  raw: string;
}

function parseMarkdownFrontmatter(raw: string): ParsedMarkdown {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) {
    return { data: {}, content: raw, raw };
  }

  const yamlBlock = match[1];
  const content = match[2];
  const data: Record<string, unknown> = {};

  // Simple YAML key-value parser (handles strings, numbers, booleans, arrays)
  for (const line of yamlBlock.split('\n')) {
    const kvMatch = line.match(/^(\w[\w-]*):\s*(.*)$/);
    if (!kvMatch) continue;

    const [, key, rawValue] = kvMatch;
    let value: unknown = rawValue;

    // Handle quoted strings
    const quotedMatch = rawValue.match(/^["'](.*)["']$/);
    if (quotedMatch) {
      value = quotedMatch[1];
    } else if (rawValue === 'true') {
      value = true;
    } else if (rawValue === 'false') {
      value = false;
    } else if (/^\d+$/.test(rawValue)) {
      value = Number(rawValue);
    } else if (rawValue.startsWith('[') && rawValue.endsWith(']')) {
      // Simple inline array
      value = rawValue
        .slice(1, -1)
        .split(',')
        .map((s) => s.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean);
    }

    data[key] = value;
  }

  return { data, content, raw };
}

function serializeMarkdownWithSourceCommit(raw: string, sourceCommit: string): string {
  // Insert sourceCommit after sourceHash in the frontmatter
  return raw.replace(
    /^(---\r?\n[\s\S]*?)(sourceHash:\s*["'][^"']*["'])\r?\n/m,
    `$1$2\nsourceCommit: "${sourceCommit}"\n`,
  );
}

// ─── Source hash computation (must match validate-translation-freshness.js) ──

function normalizeText(input: string): string {
  return (
    String(input ?? '')
      .replace(/\r\n/g, '\n')
      .trimEnd() + '\n'
  );
}

function computeSourceHash(frontmatter: Record<string, unknown>, body: string): string {
  const payload = {
    title: (frontmatter.title as string) ?? '',
    description: (frontmatter.description as string) ?? '',
    category: (frontmatter.category as string) ?? '',
    author: (frontmatter.author as string) ?? '',
    tags: Array.isArray(frontmatter.tags) ? frontmatter.tags : [],
    body: normalizeText(body),
  };

  const digest = crypto.createHash('sha256').update(JSON.stringify(payload)).digest('hex');
  return digest.slice(0, 16);
}

// ─── Markdown backfill ──────────────────────────────────────────────

interface BackfillResult {
  file: string;
  status: 'added' | 'skipped' | 'not-found';
  commit?: string;
}

function backfillMarkdownDocs(): BackfillResult[] {
  const results: BackfillResult[] = [];

  for (const collection of COLLECTIONS) {
    for (const lang of SUPPORTED_LANGUAGES) {
      const langDir = path.join(WWW_ROOT, 'src', 'content', collection, lang);
      if (!fs.existsSync(langDir)) continue;

      const files = walkDir(langDir, '.md');
      for (const file of files) {
        const relFromLang = path.relative(langDir, file);
        const enFile = path.join(WWW_ROOT, 'src', 'content', collection, 'en', relFromLang);

        if (!fs.existsSync(enFile)) {
          results.push({ file: path.relative(REPO_ROOT, file), status: 'skipped' });
          continue;
        }

        const raw = fs.readFileSync(file, 'utf-8');
        const parsed = parseMarkdownFrontmatter(raw);

        // Skip if already has sourceCommit
        if (parsed.data.sourceCommit) {
          results.push({ file: path.relative(REPO_ROOT, file), status: 'skipped' });
          continue;
        }

        const sourceHash = String(parsed.data.sourceHash ?? '').trim();
        if (!sourceHash) {
          results.push({ file: path.relative(REPO_ROOT, file), status: 'skipped' });
          continue;
        }

        // Walk git history of the English file to find the commit that produced this hash
        const enRel = path.relative(REPO_ROOT, enFile).replaceAll('\\', '/');
        const commit = findCommitForHash(enRel, sourceHash);

        if (commit) {
          if (!DRY_RUN) {
            const updated = serializeMarkdownWithSourceCommit(raw, commit);
            fs.writeFileSync(file, updated, 'utf-8');
          }
          results.push({ file: path.relative(REPO_ROOT, file), status: 'added', commit });
        } else {
          results.push({ file: path.relative(REPO_ROOT, file), status: 'not-found' });
        }
      }
    }
  }

  return results;
}

function findCommitForHash(enRelPath: string, targetHash: string, maxDepth = 50): string | null {
  let logOutput: string;
  try {
    logOutput = execSync(`git log --format=%H -${maxDepth} -- ${enRelPath}`, {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }

  if (!logOutput) return null;

  const commits = logOutput.split('\n').filter(Boolean);
  for (const commit of commits) {
    const content = getFileAtCommit(REPO_ROOT, commit, enRelPath);
    if (content === null) continue;

    try {
      const parsed = parseMarkdownFrontmatter(content);
      const hash = computeSourceHash(parsed.data, parsed.content);
      if (hash === targetHash) return commit;
    } catch {
      // skip unparseable
    }
  }

  return null;
}

// ─── JSON hash manifest backfill ────────────────────────────────────

interface ManifestBackfillResult {
  file: string;
  status: 'added' | 'skipped';
  commit?: string;
}

interface HashManifest {
  $meta: {
    algorithm: string;
    sourceLanguage: string;
    keyCount: number;
    sourceCommit?: string;
  };
  hashes: Record<string, string>;
}

interface ManifestConfig {
  name: string;
  dir: string;
  flatFiles: boolean;
}

const MANIFEST_CONFIGS: ManifestConfig[] = [
  { name: 'web', dir: 'packages/web/src/i18n/locales', flatFiles: false },
  { name: 'cli', dir: 'packages/cli/src/i18n/locales', flatFiles: false },
  { name: 'www', dir: 'packages/www/src/i18n/translations', flatFiles: true },
  { name: 'account-web', dir: 'private/account/web/src/i18n/locales', flatFiles: false },
  { name: 'account-emails', dir: 'private/account/src/i18n/locales', flatFiles: false },
];

function backfillJsonManifests(): ManifestBackfillResult[] {
  const results: ManifestBackfillResult[] = [];

  for (const config of MANIFEST_CONFIGS) {
    const absDir = path.join(REPO_ROOT, config.dir);
    const hashFile = path.join(absDir, '.translation-hashes.json');

    if (!fs.existsSync(hashFile)) {
      results.push({ file: config.dir, status: 'skipped' });
      continue;
    }

    const manifest = JSON.parse(fs.readFileSync(hashFile, 'utf-8')) as HashManifest;

    if (manifest.$meta?.sourceCommit) {
      results.push({ file: config.dir, status: 'skipped' });
      continue;
    }

    // Find latest commit that touched the English source
    const englishPath = config.flatFiles ? `${config.dir}/en.json` : `${config.dir}/en`;
    const commit = getLatestCommitForFile(REPO_ROOT, englishPath);

    if (commit) {
      if (!DRY_RUN) {
        manifest.$meta.sourceCommit = commit;
        fs.writeFileSync(hashFile, JSON.stringify(manifest, null, 2) + '\n');
      }
      results.push({ file: config.dir, status: 'added', commit: commit.slice(0, 8) });
    } else {
      results.push({ file: config.dir, status: 'skipped' });
    }
  }

  return results;
}

// ─── Helpers ────────────────────────────────────────────────────────

function walkDir(dir: string, ext: string): string[] {
  const results: string[] = [];
  const stack = [dir];

  while (stack.length > 0) {
    const current = stack.pop()!;
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (entry.name.endsWith(ext)) {
        results.push(full);
      }
    }
  }

  return results;
}

// ─── Main ───────────────────────────────────────────────────────────

function main(): void {
  console.log(DRY_RUN ? 'DRY RUN — no files will be modified\n' : '');
  console.log('Backfilling sourceCommit...');
  console.log(''.padEnd(60, '='));

  // Markdown docs
  console.log('\n1. Markdown documentation files:');
  const mdResults = backfillMarkdownDocs();
  const mdAdded = mdResults.filter((r) => r.status === 'added');
  const mdNotFound = mdResults.filter((r) => r.status === 'not-found');

  for (const r of mdAdded) {
    console.log(`  + ${r.file} -> ${r.commit?.slice(0, 8)}`);
  }
  for (const r of mdNotFound) {
    console.log(`  x ${r.file} -- could not find matching commit`);
  }
  console.log(
    `  Total: ${mdAdded.length} added, ${mdNotFound.length} not found, ${mdResults.filter((r) => r.status === 'skipped').length} skipped`,
  );

  // JSON manifests
  console.log('\n2. JSON hash manifests:');
  const jsonResults = backfillJsonManifests();
  for (const r of jsonResults) {
    if (r.status === 'added') {
      console.log(`  + ${r.file} -> ${r.commit}`);
    } else {
      console.log(`  - ${r.file} (skipped)`);
    }
  }

  console.log('\n' + ''.padEnd(60, '='));
  console.log(DRY_RUN ? 'Dry run complete. Run without --dry-run to apply changes.' : 'Backfill complete.');
}

main();
