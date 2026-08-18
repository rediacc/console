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
export function getFileAtCommit(repoRoot: string, commit: string, filePath: string): string | null {
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
export function getLatestCommitForFile(repoRoot: string, filePath: string): string | null {
  return gitExec(`log -1 --format=%H -- ${filePath}`, repoRoot);
}

// ─── JSON Diff ──────────────────────────────────────────────────────

/**
 * Flatten nested JSON object to dot-notation keys with string values.
 */
export function flattenJson(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
  const result: Record<string, string> = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        const itemPath = `${fullPath}.${i}`;
        const item = value[i];
        if (typeof item === 'string') {
          result[itemPath] = item;
        } else if (item !== null && typeof item === 'object') {
          Object.assign(result, flattenJson(item as Record<string, unknown>, itemPath));
        }
      }
    } else if (value !== null && typeof value === 'object') {
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
