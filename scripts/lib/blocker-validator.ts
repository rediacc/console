/**
 * The BLOCKER contract, for TypeScript gates. A CLIENT of the canonical
 * implementation, not a second copy of it.
 *
 * WHAT CHANGED, 2026-09-09. This file used to be an independent PORT of
 * `.ci/scripts/lib/blocker-validator.sh`: its own 54-phrase banned list, its own
 * 7-phrase substring list, its own 30-character floor, its own four message
 * bodies, and its own copy of the list grammar, under a comment asking the next
 * author to "keep .ci/scripts/lib/blocker-validator.sh in sync". That comment was
 * the only thing holding two implementations together, and nothing in the tree
 * asserted that it had been obeyed. The rule now lives in exactly one place,
 * `.ci/rediacc_ci/core/allowlist.py`, and this file reads it from there.
 *
 * THE SPLIT, and why it is not "shell out for everything":
 *
 *   parseBlockeredList   one subprocess PER FILE. `records` in the canonical
 *                        returns the same projection this function always did
 *                        (one row per entry LINE, with the line number), and a
 *                        gate parses one to three lists, so the cost is a few
 *                        tens of milliseconds.
 *   validateBlockerQuality
 *                        NO subprocess. It is called in a loop, once per entry,
 *                        and a list with fifty entries would pay fifty
 *                        interpreter starts. Instead the tables and the message
 *                        TEMPLATES arrive once per process from `contract`, and
 *                        the rendering happens here. There is still only one
 *                        place the phrases and the words are written down.
 *
 * A MISSING python3 IS A LOUD FAILURE WITH THE FIX IN IT, never a fallback. A
 * fallback would be a second implementation, which is the thing this change
 * exists to delete, and a suppression validator that silently stops validating
 * is indistinguishable from a tree with no bad suppressions in it.
 *
 * WHAT IS DELIBERATELY PRESERVED, because callers depend on it: a file that does
 * not exist parses to `[]` rather than throwing. The canonical calls that
 * `missing_ok=True` and makes it explicit at the call site; here the call site is
 * this function, and the reason it stays permissive is that thirteen gates pass
 * an optional allowlist path and treat absence as "no suppressions".
 */

import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * REDIACC_CI_ROOT is the package's single environment override
 * (`.ci/rediacc_ci/paths.py`), honoured here for the reason
 * `.ci/scripts/lib/age-check.sh` honours it: a planted-defect control has to be
 * able to point this client at a scratch tree holding a DELIBERATELY BROKEN
 * canonical, and prove that the verdicts move. Without it the only way to test
 * that the delegation is live would be to edit the real module.
 *
 * The fallback resolves from THIS FILE, not from cwd, so a gate invoked from a
 * subdirectory still finds the package.
 */
const ROOT =
  process.env.REDIACC_CI_ROOT ??
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const CI_DIR = path.join(ROOT, '.ci');
const MODULE = 'rediacc_ci.core.allowlist';

/**
 * The shape `contract` returns. `version` is checked rather than assumed: a
 * client that read a future shape and found `phrases` absent would treat every
 * low-effort reason as acceptable, which is a green that means nothing.
 */
interface BlockerContract {
  version: number;
  minLength: number;
  emdash: string;
  phrases: readonly string[];
  substrings: readonly string[];
  templates: Record<string, readonly string[]>;
}

const SUPPORTED_CONTRACT_VERSION = 1;

function canonical(args: string[], input?: string): string {
  try {
    return execFileSync('python3', ['-m', MODULE, ...args], {
      encoding: 'utf8',
      input,
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH ? `${CI_DIR}:${process.env.PYTHONPATH}` : CI_DIR,
      },
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (err) {
    const e = err as { status?: number; stderr?: Buffer | string; code?: string };
    const stderr = typeof e.stderr === 'string' ? e.stderr : (e.stderr?.toString() ?? '');
    throw new Error(
      [
        `blocker-validator: the canonical BLOCKER validator could not be run.`,
        `  Command: python3 -m ${MODULE} ${args.join(' ')}`,
        `  PYTHONPATH: ${CI_DIR}`,
        e.code === 'ENOENT'
          ? `  python3 is not on PATH. Install it, or run the gate inside the devbox.`
          : `  exit ${String(e.status)}`,
        stderr.trim() ? `  stderr: ${stderr.trim()}` : '',
        `  There is deliberately no TypeScript fallback: a fallback is a second`,
        `  implementation of the rule, and this file exists to not be one.`,
      ]
        .filter(Boolean)
        .join('\n')
    );
  }
}

let cachedContract: BlockerContract | null = null;

/** The tables and the message text, fetched once per process. */
function blockerContract(): BlockerContract {
  if (cachedContract) return cachedContract;
  const parsed = JSON.parse(canonical(['contract'])) as BlockerContract;
  if (parsed.version !== SUPPORTED_CONTRACT_VERSION) {
    throw new Error(
      `blocker-validator: ${MODULE} speaks contract version ${parsed.version}, ` +
        `this client understands ${SUPPORTED_CONTRACT_VERSION}. Update scripts/lib/blocker-validator.ts.`
    );
  }
  if (parsed.phrases.length === 0 || parsed.substrings.length === 0) {
    throw new Error(
      `blocker-validator: ${MODULE} returned an EMPTY banned-phrase table ` +
        `(${parsed.phrases.length} phrase(s), ${parsed.substrings.length} substring(s)). ` +
        `Every low-effort reason would pass, so this is refused rather than trusted.`
    );
  }
  cachedContract = parsed;
  return parsed;
}

/**
 * Render one message from the canonical template. ONE PASS over the template,
 * so a value containing `{entry}` is never rescanned; see the note in
 * `.ci/rediacc_ci/core/allowlist.py` beside MESSAGE_TEMPLATES.
 */
function render(kind: string, fields: Record<string, string>): string {
  const c = blockerContract();
  const lines = c.templates[kind];
  if (!lines) throw new Error(`blocker-validator: no template for kind '${kind}'`);
  const values: Record<string, string> = { ...fields, emdash: c.emdash };
  return lines
    .map((line) =>
      line.replace(/\{([a-z]+)\}/g, (_m, name: string) => {
        if (!(name in values)) {
          throw new Error(`blocker-validator: template '${kind}' wants {${name}}, unsupplied`);
        }
        return values[name] as string;
      })
    )
    .join('\n');
}

function normalize(reason: string): string {
  return reason
    .toLowerCase()
    .trim()
    .replace(/[.!?,;:]+$/, '');
}

export interface BlockerValidationFailure {
  kind: 'low-effort' | 'deferral' | 'too-short';
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
  file: string
): BlockerValidationFailure | null {
  const c = blockerContract();
  const normalized = normalize(reason);

  for (const pattern of c.phrases) {
    if (normalized === pattern) {
      return {
        kind: 'low-effort',
        normalized,
        message: render('low-effort', { file, entry: id, reason, normalized }),
      };
    }
  }

  for (const pattern of c.substrings) {
    if (normalized.includes(pattern)) {
      return {
        kind: 'deferral',
        normalized,
        message: render('deferral', { file, entry: id, reason, pattern }),
      };
    }
  }

  if (normalized.length < c.minLength) {
    return {
      kind: 'too-short',
      normalized,
      message: render('too-short', {
        file,
        entry: id,
        reason,
        length: String(normalized.length),
        min: String(c.minLength),
      }),
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
 *
 * The grammar itself is `rediacc_ci.core.allowlist.parse_text`. The transport is
 * `<line>\t<entry>\t<reason>`, which is unambiguous because the entry key is the
 * first WHITESPACE-separated token and therefore cannot contain a TAB: only the
 * reason can, and it is everything after the second one.
 */
export function parseBlockeredList(filePath: string, commentChar = '#'): BlockeredEntry[] {
  if (!fs.existsSync(filePath)) return [];

  const out = canonical(['records', filePath, commentChar]);
  const results: BlockeredEntry[] = [];
  for (const row of out.split('\n')) {
    if (row === '') continue;
    const firstTab = row.indexOf('\t');
    const secondTab = row.indexOf('\t', firstTab + 1);
    if (firstTab < 0 || secondTab < 0) {
      throw new Error(
        `blocker-validator: ${MODULE} records emitted a row with fewer than two TABs: ${JSON.stringify(row)}`
      );
    }
    results.push({
      line: Number(row.slice(0, firstTab)),
      entry: row.slice(firstTab + 1, secondTab),
      blocker: row.slice(secondTab + 1),
    });
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
      failures.push(render('missing', { file, entry }));
      continue;
    }
    const validation = validateBlockerQuality(entry, blocker, file);
    if (validation) {
      failures.push(validation.message);
    }
  }
  return failures;
}
