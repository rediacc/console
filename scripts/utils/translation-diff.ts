/**
 * Translation Diff Engine
 *
 * Shared utilities for computing structured diffs between English source
 * content and translated content. Used by both JSON hash checkers and
 * markdown freshness validators to produce actionable error messages.
 *
 * Supports:
 * - Git-based retrieval of old English content via sourceCommit
 * - JSON key-level diffing (added/removed/modified keys with old/new values)
 * - Markdown section-level diffing (by ## headings)
 * - Frontmatter field diffing
 */

import { execSync } from 'node:child_process';

// ─── Types ──────────────────────────────────────────────────────────

export interface TranslationChange {
  /** JSON: "auth.login.email", MD: "## Section Name" or frontmatter field name */
  key: string;
  type: 'added' | 'removed' | 'modified';
  /** Previous English text (from git) */
  oldValue?: string;
  /** Current English text */
  newValue?: string;
}

export interface TranslationDiffResult {
  sourceFile: string;
  sourceCommit: string;
  currentCommit: string;
  changes: TranslationChange[];
  /** false when sourceCommit is unavailable or git history is unreachable */
  hasDiff: boolean;
}

export interface MarkdownSection {
  heading: string;
  body: string;
}

// ─── Git Helpers ────────────────────────────────────────────────────

function gitExec(args: string, repoRoot: string): string | null {
  try {
    return execSync(`git ${args}`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }
}

/**
 * Get file content at a specific git commit.
 * Returns null if commit is unreachable (shallow clone, etc.).
 */
export function getFileAtCommit(
  repoRoot: string,
  commit: string,
  filePath: string
): string | null {
  // Try directly first
  const result = gitExec(`show ${commit}:${filePath}`, repoRoot);
  if (result !== null) return result;

  // Try deepening the clone
  gitExec('fetch --deepen=100', repoRoot);
  return gitExec(`show ${commit}:${filePath}`, repoRoot);
}

/**
 * Get the latest commit SHA that touched a file.
 */
export function getLatestCommitForFile(
  repoRoot: string,
  filePath: string
): string | null {
  return gitExec(`log -1 --format=%H -- ${filePath}`, repoRoot);
}

/**
 * Walk git history to find the commit where a file produced a specific hash.
 * Used by the backfill script to retroactively find sourceCommit for files
 * that only have sourceHash.
 *
 * @param maxDepth Maximum number of commits to walk (default 50)
 */
export function findCommitByHash(
  repoRoot: string,
  filePath: string,
  targetHash: string,
  computeHash: (content: string) => string,
  maxDepth = 50
): string | null {
  const logOutput = gitExec(
    `log --format=%H -${maxDepth} -- ${filePath}`,
    repoRoot
  );
  if (!logOutput) return null;

  const commits = logOutput.split('\n').filter(Boolean);
  for (const commit of commits) {
    const content = getFileAtCommit(repoRoot, commit, filePath);
    if (content === null) continue;

    const hash = computeHash(content);
    if (hash === targetHash) return commit;
  }

  return null;
}

// ─── JSON Diff ──────────────────────────────────────────────────────

/**
 * Flatten nested JSON object to dot-notation keys with string values.
 */
export function flattenJson(
  obj: Record<string, unknown>,
  prefix = ''
): Record<string, string> {
  const result: Record<string, string> = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flattenJson(value as Record<string, unknown>, fullPath));
    } else if (typeof value === 'string') {
      result[fullPath] = value;
    }
  }

  return result;
}

/**
 * Compare two flattened JSON translation objects.
 * Returns a list of added, removed, and modified keys with old/new values.
 */
export function diffJsonTranslations(
  oldFlat: Record<string, string>,
  newFlat: Record<string, string>
): TranslationChange[] {
  const changes: TranslationChange[] = [];

  // Added keys
  for (const key of Object.keys(newFlat)) {
    if (!(key in oldFlat)) {
      changes.push({ key, type: 'added', newValue: newFlat[key] });
    }
  }

  // Removed keys
  for (const key of Object.keys(oldFlat)) {
    if (!(key in newFlat)) {
      changes.push({ key, type: 'removed', oldValue: oldFlat[key] });
    }
  }

  // Modified keys
  for (const key of Object.keys(newFlat)) {
    if (key in oldFlat && oldFlat[key] !== newFlat[key]) {
      changes.push({
        key,
        type: 'modified',
        oldValue: oldFlat[key],
        newValue: newFlat[key],
      });
    }
  }

  return changes;
}

// ─── Markdown Section Diff ──────────────────────────────────────────

/**
 * Split markdown body into sections by ## headings.
 * The content before the first ## heading is assigned heading "(intro)".
 */
export function splitIntoSections(body: string): MarkdownSection[] {
  const lines = body.split('\n');
  const sections: MarkdownSection[] = [];
  let currentHeading = '(intro)';
  let currentLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith('## ')) {
      // Save previous section
      sections.push({ heading: currentHeading, body: currentLines.join('\n').trim() });
      currentHeading = line.trim();
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }

  // Save last section
  sections.push({ heading: currentHeading, body: currentLines.join('\n').trim() });

  // Filter out empty intro sections
  return sections.filter((s) => s.body || s.heading !== '(intro)');
}

/**
 * Compare old vs new markdown sections.
 * Returns changes at the section level.
 */
export function diffMarkdownSections(
  oldContent: string,
  newContent: string
): TranslationChange[] {
  const oldSections = splitIntoSections(oldContent);
  const newSections = splitIntoSections(newContent);

  const oldMap = new Map(oldSections.map((s) => [s.heading, s.body]));
  const newMap = new Map(newSections.map((s) => [s.heading, s.body]));

  const changes: TranslationChange[] = [];

  // Added sections
  for (const [heading, body] of newMap) {
    if (!oldMap.has(heading)) {
      changes.push({ key: heading, type: 'added', newValue: body });
    }
  }

  // Removed sections
  for (const [heading, body] of oldMap) {
    if (!newMap.has(heading)) {
      changes.push({ key: heading, type: 'removed', oldValue: body });
    }
  }

  // Modified sections
  for (const [heading, newBody] of newMap) {
    const oldBody = oldMap.get(heading);
    if (oldBody !== undefined && oldBody !== newBody) {
      changes.push({
        key: heading,
        type: 'modified',
        oldValue: oldBody,
        newValue: newBody,
      });
    }
  }

  return changes;
}

/**
 * Compare frontmatter fields that are relevant to translations.
 */
export function diffFrontmatter(
  oldData: Record<string, unknown>,
  newData: Record<string, unknown>
): TranslationChange[] {
  const fieldsToCompare = ['title', 'description', 'category', 'author'];
  const changes: TranslationChange[] = [];

  for (const field of fieldsToCompare) {
    const oldVal = String(oldData[field] ?? '');
    const newVal = String(newData[field] ?? '');
    if (oldVal !== newVal) {
      changes.push({
        key: `frontmatter.${field}`,
        type: oldVal ? (newVal ? 'modified' : 'removed') : 'added',
        oldValue: oldVal || undefined,
        newValue: newVal || undefined,
      });
    }
  }

  return changes;
}

// ─── Formatting ─────────────────────────────────────────────────────

/**
 * Format a TranslationChange into a human-readable (and AI-parseable) string.
 */
export function formatChange(change: TranslationChange, indent = '    '): string {
  const lines: string[] = [];

  switch (change.type) {
    case 'added':
      lines.push(`${indent}+ ${change.key}`);
      if (change.newValue) {
        const preview = truncate(change.newValue, 120);
        lines.push(`${indent}  new: ${JSON.stringify(preview)}`);
      }
      break;
    case 'removed':
      lines.push(`${indent}- ${change.key}`);
      if (change.oldValue) {
        const preview = truncate(change.oldValue, 120);
        lines.push(`${indent}  was: ${JSON.stringify(preview)}`);
      }
      break;
    case 'modified':
      lines.push(`${indent}~ ${change.key}`);
      if (change.oldValue) {
        lines.push(`${indent}  old: ${JSON.stringify(truncate(change.oldValue, 120))}`);
      }
      if (change.newValue) {
        lines.push(`${indent}  new: ${JSON.stringify(truncate(change.newValue, 120))}`);
      }
      break;
  }

  return lines.join('\n');
}

/**
 * Format a list of changes grouped by type.
 */
export function formatChanges(
  changes: TranslationChange[],
  indent = '    '
): string {
  if (changes.length === 0) return '';

  const added = changes.filter((c) => c.type === 'added');
  const removed = changes.filter((c) => c.type === 'removed');
  const modified = changes.filter((c) => c.type === 'modified');

  const lines: string[] = [];

  if (added.length > 0) {
    lines.push(`${indent}Added (translate and add):`);
    for (const c of added) {
      lines.push(formatChange(c, indent + '  '));
    }
  }

  if (removed.length > 0) {
    lines.push(`${indent}Removed (delete from translation):`);
    for (const c of removed) {
      lines.push(formatChange(c, indent + '  '));
    }
  }

  if (modified.length > 0) {
    lines.push(`${indent}Modified (update translation):`);
    for (const c of modified) {
      lines.push(formatChange(c, indent + '  '));
    }
  }

  return lines.join('\n');
}

function truncate(str: string, maxLen: number): string {
  const oneLine = str.replace(/\n/g, ' ').trim();
  if (oneLine.length <= maxLen) return oneLine;
  return oneLine.slice(0, maxLen - 3) + '...';
}
