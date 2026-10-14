/**
 * Shared machinery for "is this suppression entry still load-bearing?".
 *
 * The BLOCKER convention (see docs/agent-reference/suppressions.md) validates that every allowlist /
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
 * the window in .ci/config/release-age.json so a fresh publish cannot redden CI). A gate
 * whose verdict can flip overnight without a commit re-creates exactly that
 * problem, so no probe may consult a registry, a publish date, or a version
 * comparison. A verdict changes only when the repo changes, in the same commit
 * that changes it.
 */

import { existsSync as fsExistsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { DIM, GREEN, NC, RED, YELLOW } from './console.js';
import { isPolicyFileName, policyPath } from './policy-paths.js';

const readFileUtf8 = (p: string): string => readFileSync(p, 'utf-8');

import {
  type BlockeredEntry,
  type LooseCondition,
  type PrCondition,
  parseBlockeredList,
  parseConditions,
} from './blocker-validator.js';

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

export interface Finding {
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
 * roll-up. The anti-pattern being avoided is scripts/gates/check-actions.ts's old
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
  // Keyed on ENTRIES CHECKED, not probes run. A probe can execute and still assert nothing (its suppression file is absent), which is exactly what happens on the anti-vacuity harness's fixture now that it copies .ci/scripts in: one probe "ran" over zero entries and the gate reported
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

// --------------------------------------------------------------------------- Every BLOCKER file, and the PR-condition clause ---------------------------------------------------------------------------

/**
 * Every list in the tree that speaks the `# BLOCKER:` grammar, by the name the
 * policy seam answers to (or a repo-relative path for the two under .ci/config).
 *
 * Moved here from check-suppression-liveness.ts on 2026-10-08 so the offline
 * `pr-conditions` probe there and the online check-pr-condition-ledger.ts read ONE
 * list. It was ten names and is now every `.ci/policy/` dotfile:
 * uncoveredPolicyLists() below fails the probe on a dotfile this array does not
 * name, so a new list cannot quietly sit outside the clause check the way the k3s
 * hold sat outside every check for sixteen days.
 */
export const BLOCKER_FILES: readonly string[] = Object.freeze([
  '.actions-upgrade-blocklist',
  '.audit-allowlist',
  '.audit-prod-allowlist',
  '.ci-parity-exempt',
  '.cli-i18n-orphan-allowlist',
  '.dead-bash-allowlist',
  '.deps-upgrade-blocklist',
  '.devcontainer-upgrade-blocklist',
  '.e2e-coverage-allowlist',
  '.embed-assets-upgrade-blocklist',
  '.go-deps-upgrade-blocklist',
  '.host-toolchain-exceptions',
  '.language-policy-allowlist',
  '.plan-housekeeping-allowlist',
  '.profiler-coverage-allowlist',
  '.runner-advice-allowlist',
  '.unverified-download-allowlist',
  '.ci/config/directive-quotes-allowlist.txt',
  'pyproject.toml',
]);

/** Absolute path and display path of one BLOCKER file, through the policy seam. */
export function blockerFileLocation(root: string, rel: string): { abs: string; display: string } {
  if (isPolicyFileName(rel)) {
    const abs = policyPath(rel, root);
    return { abs, display: path.relative(root, abs).split(path.sep).join('/') };
  }
  return { abs: path.join(root, rel), display: rel };
}

/**
 * `.ci/policy/` dotfiles BLOCKER_FILES does not name. Empty when the directory is
 * absent (a fixture root), because the presence floors elsewhere own that case.
 */
export function uncoveredPolicyLists(root: string): string[] {
  const dir = path.join(root, '.ci', 'policy');
  if (!fsExistsSync(dir)) return [];
  const covered = new Set(BLOCKER_FILES);
  return readdirSync(dir)
    .filter((n) => n.startsWith('.') && !covered.has(n))
    .sort();
}

/** The committed merged-PR ledger. Read offline; written only by check-pr-condition-ledger.ts --refresh. */
export const MERGED_PRS_REL = '.ci/config/merged-prs.json';

export interface MergedPrLedger {
  format: 1;
  refreshed_at: string;
  prs: Record<string, { mergedAt: string }>;
}

const REF_RE = /^[\w.-]+\/[\w.-]+#\d+$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

/**
 * Validate a parsed ledger. null when it is well formed, else the reason, naming
 * the field. An unknown `format` is refused rather than read: a reader that found
 * `prs` renamed would see zero merged PRs and pass every stale clause.
 */
export function ledgerProblem(raw: unknown): string | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return 'not a JSON object';
  const o = raw as Record<string, unknown>;
  if (o.format !== 1) return `format is ${JSON.stringify(o.format)}, this reader understands 1`;
  if (typeof o.refreshed_at !== 'string' || !ISO_RE.test(o.refreshed_at)) {
    return `refreshed_at ${JSON.stringify(o.refreshed_at)} is not a UTC ISO timestamp`;
  }
  if (!o.prs || typeof o.prs !== 'object' || Array.isArray(o.prs)) return 'prs is not an object';
  for (const [ref, rec] of Object.entries(o.prs as Record<string, unknown>)) {
    if (!REF_RE.test(ref)) return `prs key ${JSON.stringify(ref)} is not owner/repo#N`;
    const m = (rec as { mergedAt?: unknown } | null)?.mergedAt;
    if (typeof m !== 'string' || !ISO_RE.test(m)) {
      return `prs["${ref}"].mergedAt ${JSON.stringify(m)} is not a UTC ISO timestamp`;
    }
  }
  return null;
}

export type LedgerRead =
  | { kind: 'ok'; ledger: MergedPrLedger }
  | { kind: 'missing' }
  | { kind: 'invalid'; reason: string };

export function readMergedPrLedger(root: string): LedgerRead {
  const p = path.join(root, MERGED_PRS_REL);
  if (!fsExistsSync(p)) return { kind: 'missing' };
  let raw: unknown;
  try {
    raw = JSON.parse(readFileUtf8(p));
  } catch (err) {
    return { kind: 'invalid', reason: `not JSON (${(err as Error).message})` };
  }
  const problem = ledgerProblem(raw);
  return problem
    ? { kind: 'invalid', reason: problem }
    : { kind: 'ok', ledger: raw as MergedPrLedger };
}

export interface LocatedCondition extends PrCondition {
  file: string;
}
export interface LocatedLoose extends LooseCondition {
  file: string;
}

export interface ConditionScan {
  filesRead: number;
  filesAbsent: string[];
  conditions: LocatedCondition[];
  loose: LocatedLoose[];
}

/** Every clause and loose phrasing across BLOCKER_FILES. One subprocess per present file. */
export function scanPrConditions(root: string): ConditionScan {
  const scan: ConditionScan = { filesRead: 0, filesAbsent: [], conditions: [], loose: [] };
  for (const rel of BLOCKER_FILES) {
    const { abs, display } = blockerFileLocation(root, rel);
    if (!fsExistsSync(abs)) {
      scan.filesAbsent.push(display);
      continue;
    }
    scan.filesRead++;
    const parsed = parseConditions(abs);
    for (const c of parsed.conditions) scan.conditions.push({ ...c, file: display });
    for (const l of parsed.loose) scan.loose.push({ ...l, file: display });
  }
  return scan;
}

/**
 * The offline verdicts. PURE: the scan and the ledger in, findings out, so the
 * gate's selftest and its fixture cases exercise the same function.
 *
 *   - a clause whose PR the ledger records as merged          FAIL (the hold is over)
 *   - a loose phrasing that names a PR                        FAIL (no machine can read it)
 *   - clauses present while the ledger is missing or invalid  FAIL (cannot judge = unchecked)
 */
export function prConditionFindings(scan: ConditionScan, ledger: LedgerRead): Finding[] {
  const out: Finding[] = [];
  if (ledger.kind !== 'ok' && scan.conditions.length > 0) {
    out.push({
      probe: 'pr-conditions',
      file: MERGED_PRS_REL,
      entry: '(the merged-PR ledger)',
      line: 1,
      tier: 'fail',
      why:
        ledger.kind === 'missing'
          ? `${scan.conditions.length} PR clause(s) wait on a merge, and ${MERGED_PRS_REL} is absent, so none of them can be judged. Unchecked is not clean.`
          : `${MERGED_PRS_REL} is unreadable (${ledger.reason}), so ${scan.conditions.length} PR clause(s) cannot be judged.`,
      fix: ['npx tsx scripts/gates/check-pr-condition-ledger.ts --refresh'],
    });
  }
  const prs = ledger.kind === 'ok' ? ledger.ledger.prs : {};
  for (const c of scan.conditions) {
    const merged = prs[c.ref];
    if (!merged) continue;
    const what = c.entry ? `"${c.entry}"` : 'this comment (it covers no entry)';
    out.push({
      probe: 'pr-conditions',
      file: c.file,
      entry: c.entry || `(clause at line ${c.clauseLine})`,
      line: c.line,
      tier: 'fail',
      why: `the clause at ${c.file}:${c.clauseLine} holds ${what} until PR ${c.ref} merges, and it merged at ${merged.mergedAt} (${MERGED_PRS_REL}). The condition the hold waited on has happened.`,
      fix: [
        c.entry
          ? `lift the hold: delete "${c.entry}" and its BLOCKER block from ${c.file}, then run the gate that reads it`
          : `delete the stale clause at ${c.file}:${c.clauseLine}`,
        `or, if a NEW reason still holds it, rewrite the BLOCKER with that reason and drop the clause`,
      ],
    });
  }
  for (const l of scan.loose) {
    out.push({
      probe: 'pr-conditions',
      file: l.file,
      entry: l.entry || '(comment)',
      line: l.line,
      tier: 'fail',
      why: `"${l.text}" reads as a lift condition naming a PR, but only the spelling "REVISIT WHEN PR #<N> MERGES" (or owner/repo#N) is machine-checked; this one would sit unnoticed after the PR merged.`,
      fix: [
        `rewrite it as "REVISIT WHEN PR #<N> MERGES" at ${l.file}:${l.line}`,
        `or, if the number is an issue rather than a PR, write "issue <N>" without the #`,
      ],
    });
  }
  return out;
}
