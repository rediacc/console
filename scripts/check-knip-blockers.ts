/**
 * Validate that every suppression entry in knip.jsonc carries a substantive
 * BLOCKER comment, per the repo-wide BLOCKER convention (see docs/agent/suppressions.md).
 *
 * Suppression contexts: the `ignore`, `ignoreDependencies`, `ignoreBinaries`
 * and `ignoreUnresolved` arrays, both top-level and per-workspace. `entry` /
 * `project` globs are configuration, not suppressions, and are exempt.
 *
 * Comment semantics mirror .ci/scripts/lib/blocker-validator.sh's
 * parse_blockered_list: a `// BLOCKER: <reason>` line covers every entry
 * after it until a blank line or the end of the array; an inline
 * `"entry", // BLOCKER: <reason>` form is also accepted. Reason quality is
 * enforced by the shared validator (30-char floor, banned-phrase list).
 *
 * Staleness (an ignore entry that no longer suppresses anything) is NOT
 * checked here — knip itself reports that as a configuration hint, and CI
 * runs knip with --treat-config-hints-as-errors.
 *
 * Usage: tsx scripts/check-knip-blockers.ts [--config <path>]
 */

import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type BlockeredEntry, verifyAllBlockers } from './lib/blocker-validator.js';

const SUPPRESSION_KEYS = new Set([
  'ignore',
  'ignoreDependencies',
  'ignoreBinaries',
  'ignoreUnresolved',
]);

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(SCRIPT_DIR, '..');

function resolveConfigPath(): string {
  const argIdx = process.argv.indexOf('--config');
  if (argIdx >= 0) {
    const given = process.argv[argIdx + 1];
    if (!given) {
      console.error('check-knip-blockers: --config requires a path argument');
      process.exit(2);
    }
    return path.resolve(given);
  }
  return path.join(CONSOLE_ROOT, 'knip.jsonc');
}

interface ParsedSuppression extends BlockeredEntry {
  context: string;
}

/**
 * Line-based JSONC walk. Tracks the nearest object key for context labels and
 * collects string entries inside suppression arrays together with the BLOCKER
 * comment (block-level, blank-line reset, or inline) that covers them.
 */
export function parseKnipSuppressions(configPath: string): ParsedSuppression[] {
  const lines = fs.readFileSync(configPath, 'utf-8').split('\n');
  const results: ParsedSuppression[] = [];

  let inSuppression = false;
  let arrayKey = '';
  let scope = 'top-level';
  let currentBlocker = '';

  const keyOpenArray = /^\s*"([^"]+)":\s*\[\s*$/;
  const keyOpenObject = /^\s*"([^"]+)":\s*\{\s*$/;
  const blockBlocker = /^\s*\/\/\s*BLOCKER:\s*(.+)$/;
  const plainComment = /^\s*\/\//;
  const arrayClose = /^\s*\]/;
  const entryLine = /^\s*"([^"]*)"\s*,?\s*(?:\/\/\s*(.*))?$/;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i] ?? '';
    const stripped = raw.trim();

    if (!inSuppression) {
      const objMatch = stripped.match(keyOpenObject);
      if (objMatch) {
        scope = objMatch[1] === 'workspaces' ? scope : (objMatch[1] as string);
        continue;
      }
      const arrMatch = stripped.match(keyOpenArray);
      if (arrMatch && SUPPRESSION_KEYS.has(arrMatch[1] as string)) {
        inSuppression = true;
        arrayKey = arrMatch[1] as string;
        currentBlocker = '';
      }
      continue;
    }

    if (arrayClose.test(stripped)) {
      inSuppression = false;
      currentBlocker = '';
      continue;
    }
    if (stripped === '') {
      currentBlocker = '';
      continue;
    }
    const blockerMatch = stripped.match(blockBlocker);
    if (blockerMatch) {
      currentBlocker = (blockerMatch[1] as string).trim();
      continue;
    }
    if (plainComment.test(stripped)) {
      continue; // plain comment — preserve the tracked BLOCKER
    }
    const entryMatch = stripped.match(entryLine);
    if (entryMatch) {
      const entry = entryMatch[1] as string;
      let blocker = currentBlocker;
      const inline = entryMatch[2]?.match(/^BLOCKER:\s*(.+)$/);
      if (!blocker && inline) blocker = (inline[1] as string).trim();
      results.push({
        entry: `${scope} ${arrayKey} "${entry}"`,
        blocker,
        line: i + 1,
        context: `${scope}.${arrayKey}`,
      });
    }
  }

  return results;
}

/**
 * In-code knip exceptions use `@public` JSDoc tags (knip skips @public-tagged
 * exports). The convention requires the BLOCKER reason on the same line:
 *   `@public BLOCKER: <reason>`. Scans the console tree and the
 * private/account submodule (git grep does not descend into submodules).
 */
export function collectPublicTagEntries(repoRoot: string): BlockeredEntry[] {
  const entries: BlockeredEntry[] = [];
  const scanRoots = [repoRoot, path.join(repoRoot, 'private/account')];
  for (const root of scanRoots) {
    if (!fs.existsSync(path.join(root, '.git'))) continue;
    let out = '';
    try {
      out = execFileSync(
        'git',
        [
          'grep',
          '-n',
          '-e',
          '@public',
          '--',
          '*.ts',
          '*.tsx',
          // This validator's own source mentions @public in patterns and docs.
          ':(exclude)scripts/check-knip-blockers.ts',
        ],
        { cwd: root, encoding: 'utf-8' },
      );
    } catch {
      continue; // git grep exits 1 when there are no matches
    }
    for (const line of out.split('\n')) {
      if (!line) continue;
      const [file, lineNo, ...rest] = line.split(':');
      const text = rest.join(':');
      const blockerMatch = text.match(/@public\s+BLOCKER:\s*(.+?)(?:\s*\*\/)?\s*$/);
      const rel = path.relative(repoRoot, path.join(root, file ?? ''));
      entries.push({
        entry: `@public tag at ${rel}:${lineNo}`,
        blocker: blockerMatch ? (blockerMatch[1] as string).trim() : '',
        line: Number(lineNo),
      });
    }
  }
  return entries;
}

function main(): void {
  const configPath = resolveConfigPath();
  if (!fs.existsSync(configPath)) {
    console.error(`check-knip-blockers: config not found: ${configPath}`);
    process.exit(1);
  }

  // Typed as the BASE shape, which is all verifyAllBlockers consumes. The
  // parsed entries carry an extra `context` label that nothing reads, so
  // requiring it here only made the public-tag entries below unassignable.
  const entries: BlockeredEntry[] = parseKnipSuppressions(configPath);
  if (!process.argv.includes('--config')) {
    entries.push(...collectPublicTagEntries(CONSOLE_ROOT));
  }
  const failures = verifyAllBlockers(entries, path.basename(configPath));

  if (failures.length > 0) {
    for (const failure of failures) console.error(failure);
    console.error(
      `\ncheck-knip-blockers: ${failures.length} suppression entr${failures.length === 1 ? 'y' : 'ies'} without a valid BLOCKER in ${configPath}`,
    );
    process.exit(1);
  }

  console.log(
    `check-knip-blockers: ${entries.length} suppression entries validated in ${path.basename(configPath)}`,
  );
}

main();
