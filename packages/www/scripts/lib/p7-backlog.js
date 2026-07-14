/**
 * The P7 BACKLOG BASELINE — shared by every validator that scans the marketing docs for
 * stale CLI usage.
 *
 * BLOCKER: the P4 CLI reshape renamed the command surface (positional refs, the config
 * exodus, `repo takeover` -> `repo promote`, `machine query` -> `machine status`, …) and left
 * a large backlog of dead examples across the docs in all 13 locales:
 *
 *     validate-docs-cli-usage    3354 violations
 *     validate-content-accuracy  1326 violations
 *     check-cli-docs              379 violations
 *
 * Fixing them means editing ~832 files (60 English + 772 locale). The P7 docs pass REWRITES
 * those documents wholesale, so doing it now means doing it twice — and would land
 * untranslated CLI prose in 12 locales in the meantime. P7 is where they get fixed.
 *
 * ★ WHY A BASELINE AND NOT AN EXCLUSION. `src/content/docs` IS these validators' entire scan
 * root. Excluding it would not scope a gate, it would DELETE one — and a deleted gate is how
 * this program accumulated twelve checks that were green because they could not fail. The
 * baseline keeps every gate alive for the only thing that matters between now and P7: a NEW
 * doc, or a NEW violation in an existing one.
 *
 * ★ COUNTS ARE PER FILE, NEVER A GLOBAL TOTAL. With a single number, a fix in one doc and a
 * regression in another cancel out silently. Per-file, they cannot.
 *
 * ★ A COUNT MAY GO DOWN. Docs improve, and a lower count passes — but it does not auto-update.
 * Improving a doc means editing the baseline deliberately, in a commit, on purpose.
 *
 * ★ SELF-DESTRUCT. Every entry MUST vanish when P7 rewrites these docs. A count that outlives
 * the rewrite is a BUG, not a deferral. This is a debt record, not an accepted state.
 */

import fs from 'node:fs';

/** Load a frozen per-file baseline. A missing file means "nothing is deferred". */
export function loadBacklog(baselinePath) {
  if (!fs.existsSync(baselinePath)) return {};
  return JSON.parse(fs.readFileSync(baselinePath, 'utf-8'));
}

/**
 * Compare this run to the frozen backlog.
 *
 * RED when a file exceeds its recorded count, or when a file that is NOT in the backlog has
 * any violation at all. Returns the human-readable regressions; empty means "within budget".
 */
export function findRegressions(errors, backlog, fileOf = (e) => e.file) {
  const byFile = new Map();
  for (const e of errors) {
    const f = fileOf(e);
    byFile.set(f, (byFile.get(f) ?? 0) + 1);
  }

  const regressions = [];
  for (const [file, count] of byFile) {
    const allowed = backlog[file];
    if (allowed === undefined) {
      regressions.push(
        `${file}: ${count} violation(s) — NOT in the P7 backlog (a new doc, or one that was clean)`
      );
    } else if (count > allowed) {
      regressions.push(
        `${file}: ${count} violations, backlog allows ${allowed} — the backlog GREW`
      );
    }
  }
  return regressions;
}

/**
 * `--write-baseline` re-freezes the table from THIS run, using the validator's OWN counts —
 * never scraped from its stdout. Ask the thing that decides.
 */
export function writeBacklog(baselinePath, errors, fileOf = (e) => e.file) {
  const byFile = {};
  for (const e of errors) {
    const f = fileOf(e);
    byFile[f] = (byFile[f] ?? 0) + 1;
  }
  const sorted = Object.fromEntries(Object.entries(byFile).sort(([a], [b]) => a.localeCompare(b)));
  fs.writeFileSync(baselinePath, `${JSON.stringify(sorted, null, 2)}\n`);
  return { files: Object.keys(sorted).length, violations: errors.length };
}
