/**
 * The P7 BACKLOG BASELINE — shared by every validator that scans the marketing docs for
 * stale CLI usage.
 *
 * BLOCKER: the P4 CLI reshape renamed the command surface (positional refs, the config
 * exodus, `repo takeover` -> `repo promote`, `machine query` -> `machine status`, …) and left
 * a large backlog of dead examples across the docs in all 13 locales:
 *
 *     validate-docs-cli-usage    3289 violations across 312 files
 *     validate-content-accuracy  1534 violations across 299 files
 *     check-cli-docs              425 violations across  50 files
 *     ------------------------------------------------------------
 *     TOTAL                      5248
 *
 * ★ Those numbers are read from the baseline files themselves, not remembered. This program
 * has had to correct five counts that were quoted from memory (the renet baseline, the "408"
 * orphan keys, the stale-key delta, and the "379" that was one narrower validator's total and
 * got mistaken for all three). A wrong number in a BLOCKER is worse than a wrong number in a
 * chat message: this is the one place a future reader will look.
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
 * ★ THE RATCHET ONLY TURNS DOWN. A count that FALLS is also RED — the fix is to lower the
 * entry, and an entry whose file has no violations left must be DELETED. A baseline that
 * silently keeps a fixed file's old number is not a debt record, it is a pre-authorisation for
 * the next N breakages in that file. The entry must shrink as the debt shrinks, in a commit, on
 * purpose. (Ported from `.ci/scripts/quality/check-workflows.sh`, which has enforced this shape
 * on the workflow-inline baseline since it was introduced.)
 *
 * ★ SELF-DESTRUCT. Every entry MUST vanish when P7 rewrites these docs. A count that outlives
 * the rewrite is a BUG, not a deferral. This is a debt record, not an accepted state — and the
 * ratchet above is what MAKES the self-destruct a build failure rather than a comment nobody
 * reads.
 */

import fs from 'node:fs';

// The repo-wide composition guard. Imported as `.ts` DELIBERATELY: three of this module's
// four consumers run under plain `node`, not tsx, and Node 22.18+ strips types natively,
// so `.ts` is the only specifier that resolves under BOTH runners. A `.js` specifier
// resolves under tsx and throws ERR_MODULE_NOT_FOUND under node.
import {
  countAdditions,
  renderRefusal,
  writeBaselineVerdict,
} from '../../../../scripts/lib/shrink-only-baseline.ts';

/** Load a frozen per-file baseline. A missing file means "nothing is deferred". */
export function loadBacklog(baselinePath) {
  if (!fs.existsSync(baselinePath)) return {};
  return JSON.parse(fs.readFileSync(baselinePath, 'utf-8'));
}

/**
 * Compare this run to the frozen backlog. The comparison is a RATCHET: it is RED in BOTH
 * directions, because a baseline entry that outlives its violations is a standing budget for
 * future breakage.
 *
 * RED when:
 *   - a file NOT in the backlog has any violation at all (a new ${noun});
 *   - a file EXCEEDS its recorded count (the debt grew);
 *   - a file is BELOW its recorded count (the debt shrank — lower the entry);
 *   - an entry matches NO violation in this run at all (the debt is gone — delete the entry).
 *
 * Every message starts `<file>: ` so callers can recover the path with `split(':')[0]`.
 * Returns the human-readable regressions; empty means "exactly on budget".
 */
export function findRegressions(errors, backlog, fileOf = (e) => e.file, noun = 'doc') {
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
        `${file}: ${count} violation(s) — NOT in the backlog (a new ${noun}, or one that was clean)`
      );
    } else if (count > allowed) {
      regressions.push(
        `${file}: ${count} violations, backlog allows ${allowed} — the backlog GREW`
      );
    } else if (count < allowed) {
      regressions.push(
        `${file}: only ${count} violation(s) remain but the backlog records ${allowed} — ` +
          `lower the entry to ${count} (ratchet down)`
      );
    }
  }

  // An entry with NO matching violation this run. Reported separately from the count cases
  // above because the file may be clean OR gone entirely; either way the entry is dead weight
  // and, left in place, silently re-authorises ${allowed} future violations in that path.
  for (const [file, allowed] of Object.entries(backlog)) {
    if (!byFile.has(file)) {
      regressions.push(
        `${file}: 0 violations remain but the backlog records ${allowed} — ` +
          `delete this stale entry (ratchet down; the ${noun} is clean or gone)`
      );
    }
  }

  return regressions.sort();
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

  // COMPOSITION, ENFORCED AT THE CHOKE POINT.
  //
  // The ratchet above is RED in both directions on the READ path, and this function was an
  // unconditional re-freeze on the WRITE path. Those are different claims: the read path
  // stops the table drifting between runs, and nothing at all stopped a `--write-baseline`
  // from retiring three drained files while silently enshrining a fourth that had just
  // broken. It prints a smaller number while doing it, so it reads as progress.
  //
  // Guarded HERE rather than in each caller because this is the single point all four
  // share, and because one of them was under another session's hand when this was written.
  // Growth in a COUNT table wears two faces and a set-only check catches one: a file absent
  // from the old table, and a file whose allowance goes UP.
  //
  // WHY process.exit RATHER THAN A THROW OR A RETURN CODE. Callers destructure the return
  // value and log it; none of them can act on a refusal, and none should have to learn to.
  // A throw would surface as an unhandled stack trace, which reads as a flake rather than
  // as a decision. Exiting non-zero with the reason printed is the behaviour every other
  // gate in this repo already has, and it needs no change in any caller.
  const had = fs.existsSync(baselinePath);
  const previous = had ? loadBacklog(baselinePath) : {};
  const verdict = writeBaselineVerdict({
    baselineExists: had,
    firstSeedFlag: process.argv.includes('--first-seed'),
    additions: had ? countAdditions(previous, sorted) : [],
  });
  if (verdict !== null) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${renderRefusal(verdict, {
        baselineLabel: baselinePath,
        noun: 'backlogged file',
        previousCount: Object.keys(previous).length,
        newCount: Object.keys(sorted).length,
      })}`
    );
    process.exit(1);
  }

  fs.writeFileSync(baselinePath, `${JSON.stringify(sorted, null, 2)}\n`);
  return { files: Object.keys(sorted).length, violations: errors.length };
}
