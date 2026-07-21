/**
 * Shared machinery for "is this suppression entry still load-bearing?".
 *
 * The BLOCKER convention (see docs/agent/suppressions.md) validates that every allowlist /
 * blocklist / override entry HAS a substantive reason. It does not validate
 * that the reason is still TRUE, or that the thing being suppressed still
 * exists. That gap is not theoretical: Electron was removed from the product,
 * and 101 suppression entries justified by electron dependency chains stayed
 * behind — 18 in .audit-allowlist (the entire file) and 83 in
 * .audit-prod-allowlist — because the gate that was supposed to notice
 * (`check_stale_entries` in .ci/scripts/security/audit.sh) skipped any advisory
 * that had vanished from the audit report entirely.
 *
 * A "probe" pairs one suppression file with the ORACLE that decides whether an
 * entry is still load-bearing: the fact whose disappearance makes the entry
 * inert. Every oracle here is a fact about the current checkout — a declared
 * dependency, a go.mod require, a Dockerfile ARG, a `uses:` reference, a
 * lockfile node. None of them touch the network.
 *
 * That is deliberate. This repo already engineered away upstream-cadence
 * flakiness (scripts/lib/release-age.ts defers releases younger than
 * .npmrc's minimum-release-age so a fresh publish cannot redden CI). A gate
 * whose verdict can flip overnight without a commit re-creates exactly that
 * problem, so no probe may consult a registry, a publish date, or a version
 * comparison. A verdict changes only when the repo changes, in the same commit
 * that changes it.
 */

import { existsSync as fsExistsSync, readFileSync } from 'node:fs';
import { DIM, GREEN, NC, RED, YELLOW } from '../utils/console.js';

const readFileUtf8 = (p: string): string => readFileSync(p, 'utf-8');
import { type BlockeredEntry, parseBlockeredList } from './blocker-validator.js';

/** The set of facts that keep entries alive, plus enough context to explain it. */
export interface Universe {
  /** Normalized names of everything that currently exists. */
  names: Set<string>;
  /** Human label for the oracle, e.g. "121 declared names across 11 manifests". */
  source: string;
}

type Tier = 'fail' | 'warn';

export interface Probe {
  id: string;
  /** Repo-relative path of the suppression file, for display. */
  file: string;
  tier: Tier;
  /**
   * Minimum universe size before this probe is willing to condemn anything.
   *
   * This is the generalization of the `total_vulns > 0` guard in
   * .ci/scripts/security/audit.sh: a floor on the ORACLE'S OWN OUTPUT, so a
   * broken or empty oracle skips loudly instead of declaring every entry dead.
   *
   * Deliberately NOT a ratio over the suppression list ("all entries condemned
   * ⇒ suspicious"): that heuristic would have suppressed the electron cleanup,
   * which was correct for 101 of 101 entries.
   */
  minUniverse: number;
  /** Entries to check. Defaults to parseBlockeredList over an absolute path. */
  entries(root: string): BlockeredEntry[];
  /** null ⇒ the oracle is unavailable (missing submodule, unparseable input) ⇒ SKIP. */
  universe(root: string): Universe | null;
  /** Candidate keys for one entry; the entry is live if ANY is in the universe. */
  normalize?(entry: string): string[];
  /**
   * Override the default exact-match liveness test. Needed where entries are
   * not names but PATTERNS over the universe — .cli-i18n-orphan-allowlist holds
   * key PREFIXES, so "live" means "some leaf key starts with this".
   */
  isLive?(entry: string, u: Universe): boolean;
  /** One sentence saying why the entry looks dead, citing the oracle. */
  why(entry: string, u: Universe): string;
  /** Exact command(s) that resolve the finding. */
  fix(entry: string, e: BlockeredEntry): string[];
}

interface Finding {
  probe: string;
  file: string;
  entry: string;
  line: number;
  tier: Tier;
  why: string;
  fix: string[];
}

interface Skip {
  probe: string;
  file: string;
  reason: string;
  uncheckedEntries: number;
}

export interface RunResult {
  findings: Finding[];
  skips: Skip[];
  probesRun: number;
  entriesChecked: number;
}

/** Convenience for probes whose entries are a plain BLOCKER-gated list. */
export function blockeredEntries(absPath: string): BlockeredEntry[] {
  return parseBlockeredList(absPath);
}

export function runProbes(probes: Probe[], root: string): RunResult {
  const findings: Finding[] = [];
  const skips: Skip[] = [];
  let probesRun = 0;
  let entriesChecked = 0;

  for (const probe of probes) {
    const entries = probe.entries(root);
    const universe = probe.universe(root);

    if (universe === null) {
      skips.push({
        probe: probe.id,
        file: probe.file,
        reason: 'oracle unavailable (source of truth missing or unparseable)',
        uncheckedEntries: entries.length,
      });
      continue;
    }
    if (universe.names.size < probe.minUniverse) {
      skips.push({
        probe: probe.id,
        file: probe.file,
        reason: `oracle returned only ${universe.names.size} name(s) (${universe.source}); floor is ${probe.minUniverse} — refusing to condemn entries against a suspect oracle`,
        uncheckedEntries: entries.length,
      });
      continue;
    }

    probesRun++;
    for (const e of entries) {
      entriesChecked++;
      if (probe.isLive) {
        if (probe.isLive(e.entry, universe)) continue;
      } else {
        const candidates = probe.normalize ? probe.normalize(e.entry) : [e.entry];
        if (candidates.some((c) => universe.names.has(c))) continue;
      }
      findings.push({
        probe: probe.id,
        file: probe.file,
        entry: e.entry,
        line: e.line,
        tier: probe.tier,
        why: probe.why(e.entry, universe),
        fix: probe.fix(e.entry, e),
      });
    }
  }

  return { findings, skips, probesRun, entriesChecked };
}

const MAX_FINDINGS_PER_PROBE = 10;

/**
 * Output is deliberately SHARP, not comprehensive: one block per finding, one
 * file:line, one copy-pasteable fix, and a hard cap per probe followed by a
 * roll-up. The anti-pattern being avoided is scripts/check-actions.ts's old
 * `Files: a:1, b:2, …` dump, which listed 137 paths for a single action and
 * buried the one line a reader actually needed.
 */
export function formatReport(result: RunResult, opts: { ci: boolean }): string {
  const { findings, skips, probesRun, entriesChecked } = result;
  const failCount = findings.filter((f) => f.tier === 'fail').length;
  const warnCount = findings.length - failCount;
  const out: string[] = [];

  out.push('Suppression Liveness');
  out.push('='.repeat(60));
  out.push(
    `probes: ${probesRun} run, ${skips.length} skipped   entries: ${entriesChecked} checked   findings: ${findings.length} (${failCount} fail, ${warnCount} warn)`
  );
  out.push('');

  const byProbe = new Map<string, Finding[]>();
  for (const f of findings) {
    const list = byProbe.get(f.probe) ?? [];
    list.push(f);
    byProbe.set(f.probe, list);
  }

  for (const [probeId, list] of byProbe) {
    const shown = list.slice(0, MAX_FINDINGS_PER_PROBE);
    for (const f of shown) {
      const label = f.tier === 'fail' ? `${RED}FAIL${NC}` : `${YELLOW}WARN${NC}`;
      out.push(`${label}  ${f.file}:${f.line}  ${f.entry}`);
      out.push(`  DEAD: ${f.why}`);
      for (const cmd of f.fix) out.push(`  FIX:  ${cmd}`);
      out.push('');
      if (opts.ci) {
        const kind = f.tier === 'fail' ? 'error' : 'warning';
        const msg = `${f.entry}: ${f.why}`.replace(/\r?\n/g, ' ');
        out.push(`::${kind} file=${f.file},line=${f.line}::${msg}`);
      }
    }
    const hidden = list.length - shown.length;
    if (hidden > 0) {
      out.push(
        `  ${DIM}… and ${hidden} more in ${probeId} — same shape, same fix; re-run with --probe ${probeId} for the full list.${NC}`
      );
      out.push('');
    }
  }

  for (const s of skips) {
    out.push(
      `${YELLOW}SKIP${NC}  ${s.file} — ${s.reason}. ${s.uncheckedEntries} entr(ies) left unchecked; oracle unavailable, NOT proven clean.`
    );
  }
  if (skips.length > 0) out.push('');

  if (failCount > 0) {
    out.push(`${RED}✗${NC} ${failCount} stale suppression entr(ies) must be removed.`);
  } else if (warnCount > 0) {
    out.push(
      `${GREEN}✓${NC} no failing entries. ${warnCount} warning(s) need a human call — see above.`
    );
  } else {
    out.push(`${GREEN}✓${NC} every suppression entry is still load-bearing.`);
  }
  return out.join('\n');
}

/**
 * Anti-vacuity: if the run checked NO entries, it asserted nothing and must not
 * report success. One probe skipping among several is fine and expected (an
 * uninitialized submodule, for instance); checking nothing at all is not.
 */
export function isVacuous(result: RunResult, probeCount: number): boolean {
  // Keyed on ENTRIES CHECKED, not probes run. A probe can execute and still
  // assert nothing (its suppression file is absent), which is exactly what
  // happens on the anti-vacuity harness's fixture now that it copies
  // .ci/scripts in: one probe "ran" over zero entries and the gate reported
  // success. entriesChecked === 0 subsumes probesRun === 0 and closes that.
  return probeCount > 0 && result.entriesChecked === 0;
}

/**
 * A `# BLOCKER:` block with no entries beneath it.
 *
 * verifyAllBlockers() walks ENTRIES, so a reason covering nothing is invisible
 * to it — the same shape as the audit.sh bug this module exists to generalize.
 * An orphaned BLOCKER is not dangerous, but it is a lie: it documents a
 * suppression that is not in force, and it is exactly what a reader greps for
 * when deciding whether something is still allowlisted.
 */
export function findOrphanedBlockers(
  absPath: string,
  displayPath: string
): Array<{ file: string; line: number; reason: string }> {
  if (!fsExistsSync(absPath)) return [];
  const out: Array<{ file: string; line: number; reason: string }> = [];
  const lines = readFileUtf8(absPath).split('\n');
  let pending: { line: number; reason: string } | null = null;
  let sawEntry = false;

  const flush = (): void => {
    if (pending && !sawEntry) out.push({ file: displayPath, ...pending });
    pending = null;
    sawEntry = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line === '') {
      flush();
      continue;
    }
    if (line.startsWith('#')) {
      const m = line.match(/^#\s*BLOCKER:\s*(.+)$/i);
      if (m) {
        flush();
        pending = { line: i + 1, reason: m[1].slice(0, 60) };
      }
      continue;
    }
    // A bare entry line, or an entry carrying an inline BLOCKER.
    if (/^#\s*BLOCKER:/i.test(line)) continue;
    sawEntry = true;
  }
  flush();
  return out;
}
