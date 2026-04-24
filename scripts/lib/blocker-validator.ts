/**
 * TypeScript port of .ci/scripts/lib/blocker-validator.sh.
 *
 * Shared BLOCKER validator for every suppression-gated check implemented
 * in TypeScript (check-deps.ts, check-actions.ts, etc.). Keeps behaviour
 * identical to the bash version so CI and local runs enforce the same rules.
 *
 * When this file changes, keep .ci/scripts/lib/blocker-validator.sh in sync —
 * the banned-phrase list and the 30-char floor are the contract.
 */

import * as fs from 'node:fs';

export const LOW_EFFORT_BLOCKER_PATTERNS: readonly string[] = [
  // npm-audit ack-tier phrases
  'no fix', 'no fix available', 'no fix yet', 'no upstream fix', 'no fix published',
  'no patch', 'no patch yet', 'no patch available',
  'none', 'n/a', 'na', 'empty', '-',
  // scheduling ack-tier
  'tbd', 'wip', 'fixme', 'todo', 'later', 'fix later', 'will fix', 'pending',
  'skip', 'skipping', 'skipped', 'ignore', 'ignoring', 'ignored',
  'unknown', 'unknown reason', 'idk', 'dunno', 'whatever',
  // review-gate-style ack phrases
  'ok', 'okay', 'ack', 'acknowledged', 'noted', 'done', 'fixed', 'applied',
  'addressed', 'updated', 'changed', 'understood',
  // explicit escape-hatch attempts
  'escape', 'escape hatch', 'suppressed', 'suppress', 'bypass', 'override',
  'upstream issue', 'transitive', 'dev dep', 'dev only',
];

export const BLOCKER_MIN_LENGTH = 30;

function normalize(reason: string): string {
  return reason
    .toLowerCase()
    .trim()
    .replace(/[.!?,;:]+$/, '');
}

export interface BlockerValidationFailure {
  kind: 'low-effort' | 'too-short';
  normalized: string;
  message: string;
}

/**
 * Validate a BLOCKER reason against the shared quality rules.
 * Returns null on success, or a failure record describing why the reason
 * is rejected. The message is AI-navigable and includes a concrete example
 * of a good BLOCKER.
 */
export function validateBlockerQuality(
  id: string,
  reason: string,
  file: string,
): BlockerValidationFailure | null {
  const normalized = normalize(reason);

  for (const pattern of LOW_EFFORT_BLOCKER_PATTERNS) {
    if (normalized === pattern) {
      return {
        kind: 'low-effort',
        normalized,
        message: [
          `Allowlist ${file}: BLOCKER for entry ${id} is a low-effort placeholder ("${reason}")`,
          `  Rejected because: "${normalized}" matches the banned-phrase list — this adds no information beyond 'we suppressed it'`,
          `  Action: write a specific reason. Good BLOCKERs cite the upstream pin, the package chain, OR why runtime isn't affected.`,
          `  Example: 'electron-builder 26.x pins plist > xmldom 0.8.x; build-time only, requires major electron migration'`,
        ].join('\n'),
      };
    }
  }

  if (normalized.length < BLOCKER_MIN_LENGTH) {
    return {
      kind: 'too-short',
      normalized,
      message: [
        `Allowlist ${file}: BLOCKER for entry ${id} is too short (${normalized.length} chars, minimum ${BLOCKER_MIN_LENGTH})`,
        `  Current: "${reason}"`,
        `  Action: a BLOCKER must explain WHO pins what, WHY the fix cannot be taken now, and ideally WHEN to revisit.`,
        `  Example: 'axios 1.15.0 pins follow-redirects <1.16.0; not runtime-exposed in CLI auth path; revisit when axios bumps'`,
      ].join('\n'),
    };
  }

  return null;
}

export interface BlockeredEntry {
  entry: string;
  blocker: string;
  line: number;
}

/**
 * Parse a BLOCKER-gated list file. Supports both:
 *   - numeric-ID-per-line with preceding # BLOCKER: block (audit allowlists)
 *   - package-name-per-line with inline # BLOCKER: reason (deps blocklist)
 *
 * A blank line resets the tracked BLOCKER so a single comment can cover a
 * grouped list of related entries. Returns one record per entry.
 */
export function parseBlockeredList(filePath: string, commentChar = '#'): BlockeredEntry[] {
  if (!fs.existsSync(filePath)) return [];

  const results: BlockeredEntry[] = [];
  const blockerRegex = new RegExp(`^\\s*${commentChar}\\s*BLOCKER:\\s*(.+)$`);
  const commentRegex = new RegExp(`^\\s*${commentChar}`);
  const inlineBlockerRegex = new RegExp(`${commentChar}\\s*BLOCKER:\\s*(.+)$`);

  const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
  let currentBlocker = '';
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i] ?? '';
    const stripped = raw.trim();

    if (stripped === '') {
      currentBlocker = '';
      continue;
    }
    const blockerMatch = stripped.match(blockerRegex);
    if (blockerMatch) {
      currentBlocker = blockerMatch[1]!.trim();
      continue;
    }
    if (commentRegex.test(stripped)) {
      continue; // plain comment — preserve currentBlocker
    }

    // Entry line — take first whitespace-separated token before any inline comment
    let entry = stripped.split(/\s/)[0] ?? '';
    const commentIdx = entry.indexOf(commentChar);
    if (commentIdx >= 0) entry = entry.slice(0, commentIdx);
    entry = entry.trim();
    if (!entry) continue;

    // Inline-form precedence: "package  # BLOCKER: <reason>" captures the inline reason
    let blocker = currentBlocker;
    const inlineMatch = stripped.match(inlineBlockerRegex);
    if (inlineMatch && !blocker) {
      blocker = inlineMatch[1]!.trim();
    } else if (inlineMatch) {
      // Prefer block-level blocker when both present — matches bash behavior
    }

    results.push({ entry, blocker, line: i + 1 });
  }

  return results;
}

/**
 * Validate every entry in a parsed blockered list. Returns an array of
 * failure messages (empty array = all valid). Each failure is formatted
 * for direct echo to stderr.
 */
export function verifyAllBlockers(entries: BlockeredEntry[], file: string): string[] {
  const failures: string[] = [];
  for (const { entry, blocker } of entries) {
    if (!blocker) {
      failures.push(
        [
          `Allowlist ${file}: entry ${entry} is missing a '# BLOCKER: <reason>' comment above it`,
          `  Action: add a line like '# BLOCKER: <who pins what / why we cannot take the fix>' immediately above ${entry} in ${file}`,
        ].join('\n'),
      );
      continue;
    }
    const validation = validateBlockerQuality(entry, blocker, file);
    if (validation) {
      failures.push(validation.message);
    }
  }
  return failures;
}
