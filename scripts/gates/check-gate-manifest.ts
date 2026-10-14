#!/usr/bin/env tsx
/**
 * check:ci-gate-manifest -- the ci-runner manifest describes itself honestly.
 *
 * Four oracles (three over `scripts/ci-runner/manifest.ts`, one over the tree), all mechanical, all
 * offline. They exist because the pre-push lane's whole value rests on the
 * manifest being true about two things nobody re-reads: which gates are cheap,
 * and which files select them.
 *
 * 1. TIER HONESTY, BOTH DIRECTIONS. `slow: true` is a claim about cost. For a
 *    gate the lock runs as its OWN named CI workflow step (`ci.kind ===
 *    'step'`), the measurement is `.ci/config/lane-durations.json`'s
 *    `gate_step_p90_seconds` -- CI-representative, checkout-independent, and
 *    written by `budget_report.py --refresh` from the SAME PR-full sample
 *    `job_p90_minutes` already walks. `.ci/cache/gate-durations.json` (a local
 *    run's own timings) is the fallback for a gate with no CI step to time at
 *    all (`local-only`, or a `test`-kind gate a battery drives) -- NEVER for a
 *    step gate, because the local cache depends on the checkout: MEASURED
 *    2026-09-28, `check:ci-embed-asset-versions` read ~1.2s in a clean clone
 *    and 38-86s in a tree carrying large gitignored assets, giving the
 *    identical code contradictory verdicts depending on which tree asked. A
 *    gate marked slow that is in fact cheap fails just as loudly as a fast one
 *    that is expensive -- and it is the FIRST direction that needs a gate,
 *    because it is invisible: the push stays fast while the lane quietly
 *    covers less. The other direction announces itself by making every push
 *    slower.
 *
 *    WHICH LOCAL NUMBER, UNDER LOAD. The cache records per run the wall
 *    (`recent`), the process tree's user+sys CPU (`cpu`), peak RSS and, for an
 *    elastic gate only, cpu / wall / grant (`perCore`). It records nothing
 *    about the MACHINE during the run. Mark-slow reads the FLOOR of `recent`,
 *    since load only adds wall and one quiet run in the window is enough;
 *    drop-slow reads the median (see `median`). CPU was weighed as a
 *    load-free substitute and rejected on measured data: it inflates under the
 *    same load (the 1007-1 push clone's build:cli read 37.7-56.8 s of CPU
 *    while concurrent pytest -n 8 ran), and an I/O-bound gate's CPU is
 *    near zero however long it blocks the push, so judging on CPU would
 *    acquit exactly the slow gates the rule exists for. The clone's floor run
 *    was NOT load-inflated: its 37.7 s of CPU matches the working tree's own
 *    cold build (24.3 s wall, 37.7 s CPU) to within 0.2%. It was convicted
 *    because nothing fast needed it any more, which `tierFindings` now
 *    reads as "not in the lane". The residual is five consecutive contended
 *    runs (see MIN_SAMPLES_TO_TIER); closing it needs a per-run machine-load
 *    field from the cache writer, which is not recorded today.
 *
 * 2. LEAF SELF-INCLUSION. A gate that declares `paths` but does not include its
 *    OWN implementation cannot be selected by editing itself. Found live: eight
 *    gates, including two whose entire job is testing a script that does not
 *    select them. Mechanical, free, and monotone-safe -- the fix only ever
 *    widens a selection.
 *
 * 3. NON-EMPTY GLOBS. A declared glob matching zero tracked files is dead: it
 *    can only ever exclude. Deliberately NOT the stronger "the regex agrees
 *    with `git ls-files <glob>`" check, because the two genuinely disagree and
 *    the stronger form would assert the wrong side. Measured 2026-08-27:
 *    `**\/*.sh` matches 518 tracked files under the runner's matcher and 516
 *    under git's pathspec, differing on root-level `run.sh` and `rdc.sh`. The
 *    runner's answer is the one that matches what check-shell-size.sh actually
 *    scans (`git ls-files '*.sh'`), so pinning it to git's would be pinning it
 *    to the wrong semantics. Recorded here so the next reader does not
 *    "strengthen" this into a false gate.
 *
 * 4. NO DEAD GATE ID IN PROSE OR COMMENTS. The `gate-test` namespace is retired: the bash battery
 *    became pytest modules under `.ci/rediacc_ci/tests/gates/`, collected by `check:ci-pytest`, and
 *    the lock holds no id in it. About forty such ids stayed in docs, code comments and guard
 *    messages anyway, so a reader told to run one found nothing (`npm run <id>` exits 1 with zero
 *    bytes on both streams, which reads as a gate failing for cause). A mention is a finding unless
 *    it names an id the manifest registers, or it is marked as a HISTORICAL RECORD: a comment that
 *    starts with the record marker (RECORD_MARKER below) on the same line or the line above, or the
 *    file-level form (RECORD_FILE_MARKER) which covers a whole dated log. Both need a reason, and a
 *    marker that covers no mention is itself a finding, so a record cannot outlive its mention.
 *    Scope: tracked text files outside `agent/` (plans, ledgers and reviews are dated records by
 *    construction) and outside `.json`/`.jsonl` data, which cannot carry a comment.
 *
 * ---- gate ----
 * step: Gate manifest self-consistency
 * emit: false
 * blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
 * needs: node
 * selftest: true
 * why: The manifest is the pre-push lane's only source of truth about which
 *      gates are cheap and which files select them, and nothing re-reads it.
 *      Three oracles, each with both directions in --selftest: a `slow` claim
 *      must agree with the measured cache BOTH ways (a cheap gate marked slow
 *      is the invisible direction -- the push stays fast while coverage
 *      shrinks); a gate declaring paths must include its own leaves, or editing
 *      the gate does not select the gate; and a declared glob must match at
 *      least one tracked file. Found eight live leaf violations and one
 *      mis-tiered gate on its first run.
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { GATES, type GateSpec } from '../ci-runner/manifest';
import { refused } from '../lib/controls';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/** The lane's budget. A gate at or above this belongs in the slow tier. */
const BUDGET_MS = 10_000;
/** Hysteresis, so a gate hovering at the line does not flip the gate red on
 *  every measurement. Only a gate that is wrong by a factor is reported. */
const SLACK = 2;

function globToRegExp(glob: string): RegExp {
  const body = glob.replace(/\*\*\/|\*\*|[*?.+^${}()|[\]\\]/g, (token) => {
    if (token === '**/') return '(?:.*/)?';
    if (token === '**') return '.*';
    if (token === '*') return '[^/]*';
    if (token === '?') return '.';
    return `\\${token}`;
  });
  return new RegExp(`^${body}$`);
}

export interface Finding {
  oracle: string;
  text: string;
}

/**
 * How many raw measurements a gate needs before its cost is allowed to accuse it.
 *
 * FIVE FALSE REDS FROM ONE CAUSE, which makes it a defect in this oracle rather than
 * five accidents. Invariant 13 says no timing from a feature worktree is admissible and
 * that a 4.5s gate has been measured at 21s under two concurrent writers. The floor
 * below already takes the CHEAPEST of `recent` for exactly that reason -- but min-of-N
 * is only honest when at least one of the N was taken on a quiet machine, and after the
 * samples for a gate are cleared the next few runs can all land under load. On
 * 2026-09-06 the docs-gen and media-args gate tests each held THREE samples, all
 * contended (33.0s and 20.7s against an uncontended 0.9-7.1s), and this oracle read the
 * floor of three bad numbers as a verdict.
 *
 * RECENT_KEEP in the runner is 5, so requiring 5 means a gate must have been measured a
 * full window before it can be accused, and a single quiet run in that window is enough
 * to bring the floor back down. It does not make contention impossible -- five
 * consecutive contended runs would still convict -- and that residual is named here
 * rather than hidden. The real cure is the designated quiesced reference worktree the
 * driver contract calls for; this is what stops the oracle lying until that exists.
 */
export const MIN_SAMPLES_TO_TIER = 5;

/**
 * THE FLOOR IS THE RIGHT STATISTIC IN ONE DIRECTION ONLY, and that asymmetry is the
 * whole reason this takes two maps.
 *
 * "Is this gate too SLOW for the fast lane" is judged on the CHEAPEST recent run,
 * because contention only ever adds time: if a gate managed 4.5s once, 4.5s is what it
 * costs, and the 21s reading was the machine, not the gate.
 *
 * "Is this gate too CHEAP to be marked slow" cannot use the same number, and using it
 * shipped a real near-miss. The dead-bash gate test measured 349.8s, 297.1s, 318.4s, 264.8s
 * and 4.675s. The floor is 4.675s, so this oracle demanded `slow: true` be dropped from
 * a gate that takes FIVE MINUTES four runs out of five -- moving it into the pre-push
 * lane on the strength of one anomalous run that plainly did not do the work. A single
 * fast outlier is how a slow gate gets promoted; a single slow outlier is only how a
 * fast gate gets left alone. So the cheap direction reads the MEDIAN, where one outlier
 * of five cannot carry the verdict.
 */
const median = (xs: readonly number[]): number => {
  const a = [...xs].sort((x, y) => x - y);
  const m = Math.floor(a.length / 2);
  return a.length % 2 === 0 ? (a[m - 1] + a[m]) / 2 : a[m];
};

/**
 * `{gate id: CI step p90 MS}`, from `.ci/config/lane-durations.json`'s
 * `gate_step_p90_seconds` (`budget_report.py --refresh` writes it, SECONDS;
 * this file's own budget is MS, so the caller converts once on read).
 */
type CiDur = Record<string, number>;

/**
 * The gates whose cost is not judged yet: a thin window, a local timing, no CI timing.
 * Only ids the manifest declares count, because the local timing cache keeps entries for gates since retired.
 */
function unjudgedTier(
  declared: ReadonlySet<string>,
  samples: Record<string, number>,
  dur: Record<string, number>,
  ciDur: CiDur
): [string, number][] {
  return Object.entries(samples).filter(
    ([id, n]) =>
      declared.has(id) &&
      n < MIN_SAMPLES_TO_TIER &&
      typeof dur[id] === 'number' &&
      typeof ciDur[id] !== 'number'
  );
}

function tierFindings(
  specs: readonly GateSpec[],
  dur: Record<string, number>,
  samples: Record<string, number> = {},
  typical: Record<string, number> = {},
  ciDur: CiDur = {},
  localSource = 'local .ci/cache/gate-durations.json'
): Finding[] {
  const out: Finding[] = [];
  // A GATE IS ALSO SLOW BY CLOSURE, and without this the two oracles here contradict each other. check:ci-client-bundle-budget costs 0.8s ITSELF and 132s through `needs: build:www`: the closure oracle says mark it, the tier oracle then says it is too cheap to be marked. Both are right about different costs, so tier defers to closure -- the number that decides lane membership is
  // what the gate costs to RUN, prerequisites included.
  const slowByClosure = slowByClosureSet(specs);
  // A BUILD NODE A FAST GATE NEEDS IS THE LANE'S FLOOR, NOT A GATE THAT COULD MOVE TIER. build:packages is a `gate: false` prerequisite of the quick lane's fast gates (build:cli was too, until f55bb1d3 made check:types:incremental slow); marking one slow would defer every fast gate that needs it, and the lane's total is bounded by the quick lane's p90 budget instead (scripts/ci-runner/quick-select.ts). A push clone builds them cold on every checkout (35-51 s against 12-20 s warm, 2026-10-01), which convicted them here on a load the rule was never about.
  // AND A BUILD NODE NO FAST GATE NEEDS IS NOT IN THE LANE AT ALL. ci-runner's select() never chooses a `gate: false` node on its own; it enters a run only through the needs-closure of a chosen gate. With every dependent slow, the node runs only when a slow gate is admitted, and marking it slow moves nothing, so "is in the pre-push lane" is simply false of it. That is the case which convicted build:cli in the 1007-1 push clone once f55bb1d3 made check:types:incremental, its last fast dependent, slow: a 23.1 s floor whose own CPU (37.7 s) matches the working tree's cold build, judged against a lane it no longer belonged to. So the MARK-SLOW direction never applies to a non-gate node. The DROP-SLOW direction still does, because a slow node demotes every gate that needs it.
  for (const spec of specs) {
    if (spec.gate === false && spec.slow !== true) continue;
    const ci = ciDur[spec.id];
    if (typeof ci === 'number') {
      // CI wins OUTRIGHT over a contradicting local cache, and judges BOTH directions off the one p90 -- no floor/median split, because this p90 is already a stable statistic over real CI runs, not a number a contended local checkout can skew. `continue` below means a step gate NEVER falls through to `dur`/local cache, even when one happens to hold an entry for it.
      if (spec.slow === true && ci < BUDGET_MS / SLACK && !slowByClosure.has(spec.id)) {
        out.push({
          oracle: 'tier',
          text: `${spec.id} is marked slow but its CI step measures ${(ci / 1000).toFixed(1)}s, cheap enough for the pre-push lane (source: CI step timing). Drop \`slow: true\`.`,
        });
      }
      if (spec.slow !== true && ci > BUDGET_MS * SLACK) {
        out.push({
          oracle: 'tier',
          text: `${spec.id} is in the pre-push lane but its CI step measures ${(ci / 1000).toFixed(1)}s (source: CI step timing). Mark \`slow: true\` with a one-line reason, or make it faster.`,
        });
      }
      continue;
    }
    // A gate that DOES run as its own CI step but has no CI sample yet (freshly added, or `--refresh` has not landed one) is left UNJUDGED here, never silently re-judged from the checkout-dependent local cache -- exactly the contradiction this box exists to close.
    if (spec.ci.kind === 'step') continue;
    const ms = dur[spec.id];
    if (typeof ms !== 'number') continue;
    // An unjudgeable cost is not a passing one; it is counted and reported below.
    const n = samples[spec.id];
    if (n !== undefined && n < MIN_SAMPLES_TO_TIER) continue;
    // The CHEAP direction reads the median, never the floor. See `median` above.
    const mid = typical[spec.id] ?? ms;
    if (spec.slow === true && mid < BUDGET_MS / SLACK && !slowByClosure.has(spec.id)) {
      out.push({
        oracle: 'tier',
        text: `${spec.id} is marked slow but typically measures ${(mid / 1000).toFixed(1)}s, cheap enough for the pre-push lane (source: ${localSource}). Drop \`slow: true\`.`,
      });
    }
    if (spec.slow !== true && ms > BUDGET_MS * SLACK) {
      out.push({
        oracle: 'tier',
        text: `${spec.id} is in the pre-push lane but measures ${(ms / 1000).toFixed(1)}s (source: ${localSource}). Mark \`slow: true\` with a one-line reason, or make it faster.`,
      });
    }
  }
  return out;
}

/**
 * TIER CONSISTENCY ALONG `needs`, which is the direction the tier oracle above
 * cannot see. `slow` PROPAGATES: a gate is only as cheap as its prerequisites,
 * because buildGraph pulls them in transitively. So `slow` on B and not-slow on
 * A-needs-B is not two independent claims, it is one claim contradicting
 * itself.
 *
 * The runner already handles this at RUNTIME -- select() computes a fixpoint
 * and demotes A -- but a runtime demotion is discovered by running, and the
 * manifest goes on asserting that A is in the lane. Seven gates were being
 * demoted this way (all needing `build:www`, 131.9s) with nothing in the
 * manifest saying so, and marking a NEW prerequisite slow would silently pull
 * more gates out of the lane with no diff to review.
 *
 * Asserting it here turns the runner's demotion list into an invariant: after
 * this, a demotion at runtime means the manifest and the graph have diverged,
 * which is exactly the condition worth a red.
 */
/**
 * Ids whose `needs` closure reaches a gate marked slow, IGNORING the gate's own
 * marking but honouring its prerequisites'.
 *
 * The first draft derived this by re-running closureFindings over specs with
 * `slow` stripped from ALL of them -- which made nothing slow, so the set came
 * back empty and the interaction control failed. It also parsed the id back out
 * of a human-readable sentence with `.text.split(' ')[0]`, which would have
 * broken silently the first time anyone reworded the message. One traversal,
 * shared by both callers, returning ids.
 */
function slowByClosureSet(specs: readonly GateSpec[]): Set<string> {
  const byId = new Map(specs.map((s) => [s.id, s]));
  const slow = new Set(specs.filter((s) => s.slow === true).map((s) => s.id));
  const out = new Set<string>();
  const walk = (id: string, seen: Set<string>): string | undefined => {
    for (const need of byId.get(id)?.needs ?? []) {
      if (seen.has(need)) continue;
      seen.add(need);
      if (slow.has(need)) return need;
      const deeper = walk(need, seen);
      if (deeper !== undefined) return deeper;
    }
    return undefined;
  };
  for (const spec of specs) if (walk(spec.id, new Set()) !== undefined) out.add(spec.id);
  return out;
}

function closureFindings(specs: readonly GateSpec[]): Finding[] {
  const byId = new Map(specs.map((s) => [s.id, s]));
  const slow = new Set(specs.filter((s) => s.slow === true).map((s) => s.id));
  const via_ = (id: string, seen: Set<string>): string | undefined => {
    for (const need of byId.get(id)?.needs ?? []) {
      if (seen.has(need)) continue;
      seen.add(need);
      if (slow.has(need)) return need;
      const deeper = via_(need, seen);
      if (deeper !== undefined) return deeper;
    }
    return undefined;
  };
  const out: Finding[] = [];
  for (const spec of specs) {
    if (spec.slow === true) continue;
    const via = via_(spec.id, new Set());
    if (via !== undefined) {
      out.push({
        oracle: 'closure',
        text: `${spec.id} is in the pre-push lane but its needs closure reaches slow gate ${via}; it costs that gate's time, so the lane is not what the manifest claims. Mark it \`slow: true\` (the runner already demotes it at runtime).`,
      });
    }
  }
  return out;
}

function leafFindings(specs: readonly GateSpec[]): Finding[] {
  const out: Finding[] = [];
  for (const spec of specs) {
    if (spec.paths === undefined) continue; // no paths = always selected = fine
    for (const leaf of spec.leaves) {
      if (!leaf.includes('/')) continue; // an npm key, not a file
      if (!spec.paths.some((g) => globToRegExp(g).test(leaf))) {
        out.push({
          oracle: 'leaf',
          text: `${spec.id} declares paths but not its own leaf ${leaf}: editing the gate does not select the gate.`,
        });
      }
    }
  }
  return out;
}

/** A leaf CI cannot see is a gate CI cannot run.
 *
 * `globFindings` proves a gate's PATHS match tracked files; nothing proved the same of
 * its LEAVES, and a spec with no `paths` skipped the leaf oracle entirely. So a manifest
 * entry could name a script under a gitignored directory: the CI step would invoke a file
 * absent from the runner and either error or, worse, pass having checked nothing.
 *
 * Found 2026-08-28 while being asked three times to wire a gate living in
 * `private/growth`, which is a separate repository ignored at `.gitignore:69` with zero
 * tracked files. This oracle makes that mistake impossible to land rather than something
 * each session has to notice.
 */
function leafTrackedFindings(specs: readonly GateSpec[], tracked: readonly string[]): Finding[] {
  const known = new Set(tracked);
  const out: Finding[] = [];
  for (const spec of specs) {
    for (const leaf of spec.leaves) {
      if (!leaf.includes('/')) continue; // an npm key, not a file
      if (!known.has(leaf)) {
        out.push({
          oracle: 'leaf-tracked',
          text: `${spec.id} declares leaf \`${leaf}\`, which git does not track. CI checks out only tracked files, so that step would run against a file that is not there.`,
        });
      }
    }
  }
  return out;
}

function globFindings(specs: readonly GateSpec[], tracked: readonly string[]): Finding[] {
  const out: Finding[] = [];
  for (const spec of specs) {
    for (const g of spec.paths ?? []) {
      const re = globToRegExp(g);
      if (!tracked.some((f) => re.test(f))) {
        out.push({
          oracle: 'glob',
          text: `${spec.id} declares \`${g}\`, which matches no tracked file. A glob that matches nothing can only exclude.`,
        });
      }
    }
  }
  return out;
}

/**
 * The retired id namespace, built from parts so this file never carries a mention of its own
 * and the oracle below has nothing to exempt here.
 */
const DEAD_PREFIX = ['gate', 'test'].join('-') + ':';
/** `<prefix><name>`; a placeholder (`<name>`) or a glob (`*`) does not start with an alphanumeric. */
const DEAD_ID_RE = new RegExp(
  `(?<![\\w:-])${DEAD_PREFIX}([A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]|[A-Za-z0-9])`,
  'g'
);
const RECORD_MARKER = ['gate-id', 'record'].join('-') + ':';
const RECORD_FILE_MARKER = ['gate-id', 'record', 'file'].join('-') + ':';
const MIN_REASON = 12;
/** Data files cannot carry a comment, so they cannot carry the marker either. */
const DATA_FILE = /\.(json|jsonl)$/;
/** A marker is the START of a comment, so prose that merely names the marker is not one. */
const markerRe = (m: string): RegExp =>
  new RegExp(`(?:^|\\s)(?:\\/\\/|#|\\*|\\/\\*|<!--)\\s*${m.replace(/[-:]/g, '\\$&')}\\s*(.*)$`);

export interface TextFile {
  path: string;
  text: string;
}

/**
 * Dead-id oracle over files already read. Pure, so the selftest drives it on fixture text.
 * `registered` is the set of manifest ids; a mention of a registered id is fine.
 */
export function deadGateIdFindings(
  registered: ReadonlySet<string>,
  files: readonly TextFile[]
): Finding[] {
  const out: Finding[] = [];
  const lineMarker = markerRe(RECORD_MARKER);
  const fileMarker = markerRe(RECORD_FILE_MARKER);
  const reasonOk = (r: string | undefined): boolean =>
    (r ?? '').replace(/-->|\*\/\s*$/g, '').trim().length >= MIN_REASON;
  for (const f of files) {
    const lines = f.text.split('\n');
    const fileLevel = lines.map((l) => fileMarker.exec(l)).find((m) => m !== null) ?? null;
    let fileCovered = 0;
    if (fileLevel !== null && !reasonOk(fileLevel[1])) {
      out.push({
        oracle: 'dead-id',
        text: `${f.path}: a file-level record marker needs a reason of at least ${MIN_REASON} characters.`,
      });
    }
    const coveredMarkers = new Set<number>();
    lines.forEach((line, i) => {
      DEAD_ID_RE.lastIndex = 0;
      const ids = [...line.matchAll(DEAD_ID_RE)].map((m) => DEAD_PREFIX + m[1]);
      if (ids.length === 0) return;
      const live = ids.filter((id) => !registered.has(id));
      if (live.length === 0) return;
      if (fileLevel !== null && reasonOk(fileLevel[1])) {
        fileCovered += 1;
        return;
      }
      for (const at of [i, i - 1]) {
        if (at < 0) continue;
        const m = lineMarker.exec(lines[at]);
        if (m !== null && reasonOk(m[1])) {
          coveredMarkers.add(at);
          return;
        }
      }
      out.push({
        oracle: 'dead-id',
        text:
          `${f.path}:${i + 1} names ${[...new Set(live)].join(', ')}, which no manifest entry registers; ` +
          'the retired namespace now lives in pytest modules under .ci/rediacc_ci/tests/gates/, run by check:ci-pytest. ' +
          'Name the module (or the real gate id) instead. A genuine historical record keeps the id with a comment ' +
          `starting with ${RECORD_MARKER} <reason> on the same line or the line above, or ${RECORD_FILE_MARKER} <reason> for a whole log. ` +
          'Do not add a path allowlist.',
      });
    });
    lines.forEach((line, i) => {
      if (!lineMarker.test(line) || coveredMarkers.has(i)) return;
      DEAD_ID_RE.lastIndex = 0;
      if (DEAD_ID_RE.test(line)) return; // same-line marker whose mention was judged above
      out.push({
        oracle: 'dead-id',
        text: `${f.path}:${i + 1} carries a record marker with no dead id on its line or the next, so it exempts nothing; delete it.`,
      });
    });
    if (fileLevel !== null && reasonOk(fileLevel[1]) && fileCovered === 0) {
      out.push({
        oracle: 'dead-id',
        text: `${f.path} carries a file-level record marker but names no dead id; delete the marker.`,
      });
    }
  }
  return out;
}

/** Tracked text files outside agent/ that mention the retired namespace, read once. */
function deadIdCorpus(tracked: readonly string[]): { files: TextFile[]; searched: number } {
  const candidates = tracked.filter((f) => !f.startsWith('agent/') && !DATA_FILE.test(f));
  let hits: string[] = [];
  try {
    hits = execFileSync(
      'git',
      [
        'grep',
        '-I',
        '-l',
        '-e',
        DEAD_PREFIX,
        '-e',
        RECORD_FILE_MARKER,
        '-e',
        RECORD_MARKER,
        '--',
        '.',
        ':!agent',
      ],
      { cwd: REPO, encoding: 'utf-8', maxBuffer: 64 * 1024 * 1024 }
    )
      .split('\n')
      .filter(Boolean);
  } catch (e) {
    // git grep exits 1 for "no match", which is a legitimate empty answer; anything else is the tool failing.
    const status = (e as { status?: number }).status;
    if (status !== 1) throw e;
  }
  const set = new Set(candidates);
  const files = hits
    .filter((h) => set.has(h))
    .map((h) => ({ path: h, text: fs.readFileSync(path.join(REPO, h), 'utf-8') }));
  return { files, searched: candidates.length };
}

/** CONTROL-FIRST. Each oracle is run against a planted defect and must find it,
 *  and against a clean fixture and must not. A gate whose green has never been
 *  contrasted with a red is not evidence. */
/**
 * How many controls the last `selftest()` actually ran, and a floor under it.
 *
 * COUNT-FREE ON PURPOSE. This was reported as a typed literal, "(19 controls)", and
 * adding four controls made that line a lie no gate could catch -- the same class the
 * floor policy names. The number is read back from what ran; the FLOOR is what stops the
 * suite silently shrinking to nothing, which a self-reported count never could.
 */
let CONTROLS_RUN = 0;
const MIN_CONTROLS = 33;

function selftest(tracked: readonly string[]): number {
  let bad = 0;
  CONTROLS_RUN = 0;
  const check = (label: string, cond: boolean): void => {
    CONTROLS_RUN += 1;
    if (cond) process.stdout.write(`  PASS  ${label}\n`);
    else {
      bad += 1;
      process.stdout.write(`  FAIL  ${label}\n`);
    }
  };
  const spec = (over: Partial<GateSpec>): GateSpec =>
    ({
      id: 'x',
      run: 'true',
      gate: true,
      leaves: ['.ci/x.sh'],
      ci: { kind: 'local-only', blocker: 'BLOCKER: selftest fixture' },
      ...over,
    }) as GateSpec;

  check(
    'tier: a slow-marked gate that is cheap is caught',
    tierFindings([spec({ slow: true })], { x: 100 }).length === 1
  );
  check(
    'tier CONTROL: a slow-marked gate that IS slow passes',
    tierFindings([spec({ slow: true })], { x: 60_000 }).length === 0
  );
  // The five-false-reds fix, both directions. Without the second control the precondition could be a blanket "never tier" and the suite would not notice.
  check(
    'tier: a non-gate build node a fast gate needs is the lane floor, not convicted',
    tierFindings([spec({ id: 'b', gate: false }), spec({ id: 'g', needs: ['b'] })], { b: 60_000 })
      .length === 0
  );
  // THE 1007-1 PUSH CLONE'S build:cli WINDOW, verbatim from /home/developer/pushclone-0923/.ci/cache/gate-durations.json on 2026-10-07: wall [43.8, 43.8, 38.8, 30.9, 23.1] s, cpu [56.8, 55.3, 51.3, 39.5, 37.7] s. Its only dependents (check:types:incremental, check:ci-proxy-rdc-update) are slow, so it runs only under them and its own `slow` flag moves nothing.
  const CLONE_BUILD_CLI = [43_831, 43_776, 38_824, 30_909, 23_114];
  const window = (id: string, xs: readonly number[]) =>
    [{ [id]: Math.min(...xs) }, { [id]: xs.length }, { [id]: median(xs) }] as const;
  check(
    'tier: a non-gate node only SLOW gates need is not in the pre-push lane, so the 1007-1 clone window does not convict it',
    tierFindings(
      [spec({ id: 'b', gate: false }), spec({ id: 'g', slow: true, needs: ['b'] })],
      ...window('b', CLONE_BUILD_CLI)
    ).length === 0
  );
  check(
    'tier: a non-gate node NOTHING needs never runs, so it is not convicted either',
    tierFindings([spec({ id: 'b', gate: false })], { b: 60_000 }).length === 0
  );
  check(
    "tier CONTROL: the SAME clone window on a fast GATE still convicts (its least-contended run spent 37.7 s of CPU, as much as the tree's own cold build)",
    tierFindings([spec({ id: 'b' })], ...window('b', CLONE_BUILD_CLI)).length === 1
  );
  check(
    'tier CONTROL: a gate slow in every sample, CPU included, is convicted',
    tierFindings([spec({})], ...window('x', [61_000, 58_000, 64_000, 59_500, 62_000])).length === 1
  );
  check(
    'tier CONTROL: a cheap non-gate node marked slow is still told to drop it (that flag DOES move its dependents)',
    tierFindings(
      [spec({ id: 'b', gate: false, slow: true }), spec({ id: 'g', slow: true, needs: ['b'] })],
      ...window('b', [900, 1_000, 1_100, 950, 1_050])
    ).length === 1
  );
  // The working tree's own windows on the same day keep the verdicts they had: build:cli as a node and as a gate (floor 4.0 s), check:types:incremental marked slow (median 24.4 s).
  const TREE_BUILD_CLI = [13_904, 19_757, 17_769, 4_046, 24_346];
  const TREE_TYPES_INCR = [24_405, 40_742, 28_546, 8_358, 23_135];
  check(
    "tier CONTROL: the working tree's build:cli window convicts neither as a node nor as a gate",
    tierFindings(
      [spec({ id: 'b', gate: false }), spec({ id: 'g', slow: true, needs: ['b'] })],
      ...window('b', TREE_BUILD_CLI)
    ).length === 0 && tierFindings([spec({ id: 'b' })], ...window('b', TREE_BUILD_CLI)).length === 0
  );
  check(
    "tier CONTROL: the working tree's check:types:incremental window keeps it slow (no drop finding)",
    tierFindings([spec({ id: 't', slow: true })], ...window('t', TREE_TYPES_INCR)).length === 0
  );
  check(
    'tier CONTROL: a GATE that a fast gate needs is still convicted',
    tierFindings([spec({ id: 'b' }), spec({ id: 'g', needs: ['b'] })], { b: 60_000 }).length === 1
  );
  check(
    'tier: a thin window of measurements does NOT convict',
    tierFindings([spec({})], { x: 60_000 }, { x: 3 }).length === 0
  );
  check(
    'tier CONTROL: a full window still convicts, so the precondition is not a mute button',
    tierFindings([spec({})], { x: 60_000 }, { x: MIN_SAMPLES_TO_TIER }).length === 1
  );
  check(
    'unjudged advisory: a declared gate with a thin window is listed',
    unjudgedTier(new Set(['x']), { x: 3 }, { x: 100 }, {}).length === 1
  );
  check(
    'unjudged advisory CONTROL: an id the manifest no longer declares is NOT listed',
    unjudgedTier(new Set(['x']), { gone: 3 }, { gone: 100 }, {}).length === 0
  );
  check(
    'tier CONTROL: a gate with no recorded window at all tiers as it always did',
    tierFindings([spec({})], { x: 60_000 }, {}).length === 1
  );
  check(
    'tier CONTROL: a thin window does not suppress the OPPOSITE finding either',
    tierFindings([spec({ slow: true })], { x: 100 }, { x: 3 }).length === 0
  );
  // The near-miss this asymmetry exists for: four runs at ~300s and one at 4.7s.
  // The floor says 4.7; the median says ~297. Only the median keeps the gate slow.
  const DEAD_BASH = [349_801, 297_056, 318_402, 264_848, 4675];
  check(
    'tier: ONE fast outlier does not demote a gate that is slow four runs in five',
    tierFindings(
      [spec({ slow: true })],
      { x: Math.min(...DEAD_BASH) },
      { x: DEAD_BASH.length },
      { x: 297_056 }
    ).length === 0
  );
  check(
    'tier CONTROL: a gate that is cheap in the MEDIAN is still told to drop slow',
    tierFindings([spec({ slow: true })], { x: 100 }, { x: 5 }, { x: 100 }).length === 1
  );
  check(
    'tier CONTROL: the SLOW direction still reads the floor, not the median',
    tierFindings([spec({})], { x: 60_000 }, { x: 5 }, { x: 60_000 }).length === 1
  );
  check(
    'tier: a fast-lane gate that is expensive is caught',
    tierFindings([spec({})], { x: 60_000 }).length === 1
  );
  check(
    'tier CONTROL: a fast-lane gate that IS fast passes',
    tierFindings([spec({})], { x: 100 }).length === 0
  );
  check(
    'tier CONTROL: an unmeasured gate is not judged',
    tierFindings([spec({ slow: true })], {}).length === 0
  );

  // CI-representative gate-step timing (`budget_report.py --refresh`'s `gate_step_p90_seconds`, read as `.ci/config/lane-durations.json`'s CI source) -- item 1's fix. A `ci.kind === 'step'` gate is judged from THIS source alone, never the local `.ci/cache/gate-durations.json`, which is exactly what stopped the identical code reading "drop slow" in a clean clone and "mark slow" in a tree carrying large gitignored assets.
  const stepCi: GateSpec['ci'] = { kind: 'step', workflow: 'w.yml', job: 'j', step: 's' };
  check(
    'tier: CI source wins over a contradicting local cache (marked slow, local says fine, CI says cheap)',
    tierFindings([spec({ slow: true, ci: stepCi })], { x: 60_000 }, {}, {}, { x: 100 }).length === 1
  );
  check(
    'tier CONTROL: CI source wins the other direction too (fast lane, local says fine, CI says slow)',
    tierFindings([spec({ ci: stepCi })], { x: 100 }, {}, {}, { x: 60_000 }).length === 1
  );
  check(
    'tier: the fallback path -- a gate with no CI step (kind: test) still tiers off the local cache',
    tierFindings([spec({ slow: true, ci: { kind: 'test', test: 't', blocker: 'BLOCKER: x' } })], {
      x: 100,
    }).length === 1
  );
  check(
    'tier CONTROL: a step gate absent from BOTH sources is not judged, even when the local cache holds a contradicting entry for its id',
    tierFindings([spec({ ci: stepCi })], { x: 60_000 }).length === 0
  );

  // Closure, both directions AND transitively -- a one-hop-only check would pass the two-hop case, which is the shape that actually occurs.
  const a = spec({ id: 'a', needs: ['b'] });
  const b = spec({ id: 'b', needs: ['c'] });
  const cSlow = spec({ id: 'c', slow: true });
  const cFast = spec({ id: 'c' });
  check(
    'closure: a fast gate needing a slow gate is caught',
    closureFindings([spec({ id: 'a', needs: ['c'] }), cSlow]).length === 1
  );
  check(
    'closure: it follows the chain, not just one hop',
    closureFindings([a, b, cSlow]).length === 2
  );
  check('closure CONTROL: an all-fast chain passes', closureFindings([a, b, cFast]).length === 0);
  check(
    'closure CONTROL: a slow gate needing a slow gate is not a finding',
    closureFindings([spec({ id: 'a', needs: ['c'], slow: true }), cSlow]).length === 0
  );
  check(
    'closure CONTROL: a cycle does not hang the walk',
    closureFindings([spec({ id: 'a', needs: ['b'] }), spec({ id: 'b', needs: ['a'] })]).length === 0
  );

  // THE TWO ORACLES MUST NOT CONTRADICT EACH OTHER. This fired live: a gate costing 0.8s itself but 132s through its closure was told to mark itself slow by one oracle and unmark itself by the other.
  check(
    'tier defers to closure: a cheap gate that is slow by closure may stay marked',
    tierFindings([spec({ id: 'a', needs: ['c'], slow: true }), spec({ id: 'c', slow: true })], {
      a: 800,
    }).length === 0
  );
  check(
    'tier CONTROL: a cheap gate slow by NOTHING is still caught',
    tierFindings([spec({ id: 'a', slow: true })], { a: 800 }).length === 1
  );

  check(
    'leaf: a gate excluding its own leaf is caught',
    leafFindings([spec({ paths: ['other/**'] })]).length === 1
  );
  check(
    'leaf CONTROL: a gate including its own leaf passes',
    leafFindings([spec({ paths: ['.ci/**'] })]).length === 0
  );
  check(
    'leaf CONTROL: a gate with NO paths is out of scope',
    leafFindings([spec({})]).length === 0
  );

  check(
    'glob: a glob matching nothing is caught',
    globFindings([spec({ paths: ['no/such/dir/**'] })], tracked).length === 1
  );
  check(
    'glob CONTROL: a glob matching something passes',
    globFindings([spec({ paths: ['.ci/**'] })], tracked).length === 0
  );

  // A leaf CI cannot see. `.ci/x.sh` is the fixture leaf and is deliberately NOT tracked,
  // so the positive case needs no planted file; the control uses a leaf that really is.
  check(
    'leaf-tracked: an untracked leaf is caught',
    leafTrackedFindings([spec({})], tracked).length === 1
  );
  check(
    'leaf-tracked CONTROL: a tracked leaf passes',
    leafTrackedFindings([spec({ leaves: ['scripts/gates/check-gate-manifest.ts'] })], tracked)
      .length === 0
  );
  check(
    'leaf-tracked CONTROL: a bare npm key is not a path',
    leafTrackedFindings([spec({ leaves: ['check:ci-thing'] })], tracked).length === 0
  );
  check(
    'glob CONTROL: the tracked list is real, or every glob would look dead',
    tracked.length > 500
  );

  // Dead-id oracle. Every fixture is ASSEMBLED from DEAD_PREFIX so this file stays free of the namespace it polices.
  const dead = (name: string): string => `${DEAD_PREFIX}${name}`;
  const none = new Set<string>();
  const one = (text: string, reg: ReadonlySet<string> = none): number =>
    deadGateIdFindings(reg, [{ path: 'x.md', text }]).length;
  check(
    'dead-id: a mention of an unregistered retired id is caught',
    one(`run ${dead('docs-gen')} to verify`) === 1
  );
  check(
    'dead-id CONTROL: a mention of a REGISTERED id passes',
    one(`run ${dead('docs-gen')}`, new Set([dead('docs-gen')])) === 0
  );
  check(
    'dead-id CONTROL: a placeholder and a glob are not ids',
    one(`the ${DEAD_PREFIX}<name> convention and ${DEAD_PREFIX}* ids`) === 0
  );
  check(
    'dead-id CONTROL: the word without the colon is not a mention',
    one('a gate-test battery, and gate-test@example.invalid') === 0
  );
  check(
    'dead-id: two mentions on two lines are two findings',
    one(`${dead('a-b')}\n${dead('c-d')}`) === 2
  );
  check(
    'dead-id CONTROL: a same-line record marker with a reason passes',
    one(`${dead('docs-gen')} ran then <!-- ${RECORD_MARKER} dated measurement, id existed -->`) ===
      0
  );
  check(
    'dead-id CONTROL: a record marker on the line above passes',
    one(`// ${RECORD_MARKER} dated measurement, id existed\n${dead('docs-gen')} ran`) === 0
  );
  check(
    'dead-id: a record marker two lines above covers nothing',
    one(`// ${RECORD_MARKER} dated measurement, id existed\n\n${dead('docs-gen')} ran`) >= 1
  );
  check(
    'dead-id: a record marker with no reason does not exempt',
    one(`${dead('docs-gen')} <!-- ${RECORD_MARKER} x -->`) >= 1
  );
  check(
    'dead-id: a marker that covers no mention is itself a finding',
    one(`// ${RECORD_MARKER} dated measurement, id existed\nnothing here`) === 1
  );
  check(
    'dead-id CONTROL: prose that names the marker is not a marker',
    one(`write \`${RECORD_MARKER} reason\` to mark a record`) === 0
  );
  check(
    'dead-id CONTROL: a file-level marker covers every mention in the file',
    one(
      `<!-- ${RECORD_FILE_MARKER} execution log, ids existed then -->\n${dead('a-b')}\n\n${dead('c-d')}`
    ) === 0
  );
  check(
    'dead-id: a file-level marker over a file with no mention is a finding',
    one(`<!-- ${RECORD_FILE_MARKER} execution log, ids existed then -->\nclean`) === 1
  );
  const corpus = deadIdCorpus(tracked);
  check(
    'dead-id CONTROL: the corpus walk sees the tree, or an empty answer would look like a clean one',
    corpus.searched > 500
  );

  // The `**/` semantics this file deliberately does NOT gate on, pinned so the comment above cannot rot into a claim nobody can check.
  check(
    'the runner matcher treats **/ as zero-or-more dirs',
    globToRegExp('**/*.sh').test('run.sh')
  );
  return bad;
}

function main(): number {
  const tracked = execFileSync('git', ['ls-files'], {
    cwd: REPO,
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);

  if (process.argv.slice(2).includes('--selftest')) {
    const bad = selftest(tracked);
    if (bad > 0) {
      process.stderr.write('CONTROL FAILED: check-gate-manifest oracles did not fire\n');
      return 1;
    }
    if (CONTROLS_RUN < MIN_CONTROLS) {
      return refused(
        `CONTROL FAILED: only ${CONTROLS_RUN} control(s) ran, floor is ${MIN_CONTROLS}. ` +
          'Controls were removed, not merely renamed.'
      );
    }
    process.stdout.write(`check-gate-manifest: selftest ok (${CONTROLS_RUN} controls)\n`);
    return 0;
  }

  const dur: Record<string, number> = {};
  const samples: Record<string, number> = {};
  const typical: Record<string, number> = {};
  // `--durations <path>` judges another checkout's cache (a push clone's, say) against THIS manifest, so a verdict seen there can be reproduced here without copying files around. Default: this checkout's own cache.
  const argv = process.argv.slice(2);
  const durAt = argv.indexOf('--durations');
  if (durAt !== -1 && (argv[durAt + 1] === undefined || argv[durAt + 1].startsWith('--'))) {
    return refused('--durations needs a path to a gate-durations.json');
  }
  const durPath =
    durAt === -1
      ? path.join(REPO, '.ci', 'cache', 'gate-durations.json')
      : path.resolve(argv[durAt + 1]);
  if (durAt !== -1 && !fs.existsSync(durPath)) {
    return refused(`--durations ${durPath}: no such file, so nothing would be judged`);
  }
  if (durAt !== -1) process.stdout.write(`- tier oracle: local durations from ${durPath}\n`);
  try {
    const raw: Record<string, unknown> = JSON.parse(fs.readFileSync(durPath, 'utf-8'));
    // The oracle judges the FLOOR of the last few raw measurements, not the scheduling average: load only ever adds time, so the cheapest recent run is the honest cost. A full run that overlapped two other sessions on 2026-09-02 pushed a 4.5s gate's average to 21s and this oracle demanded it be marked slow. A bare number is the older cache shape.
    for (const [id, v] of Object.entries(raw)) {
      if (typeof v === 'number') dur[id] = v;
      else if (v !== null && typeof v === 'object') {
        const { ewma, recent } = v as { ewma?: number; recent?: number[] };
        const floor = Array.isArray(recent) && recent.length > 0 ? Math.min(...recent) : ewma;
        if (typeof floor === 'number') dur[id] = floor;
        // A bare number is the older cache shape and carries no window, so it is left unrecorded here and tiers as it always did.
        if (Array.isArray(recent) && recent.length > 0) {
          samples[id] = recent.length;
          typical[id] = median(recent);
        }
      }
    }
  } catch {
    // NOT fatal, and NOT silent. The cache is written by real runs, so a fresh clone has none and the tier oracle simply has nothing to say yet. Saying so is the difference between "no findings" and "did not look".
    process.stdout.write('- tier oracle: no duration cache yet, so cost claims are unjudged\n');
  }

  // CI-representative timing, for every gate the lock runs as its OWN named workflow step -- see the module doc's item 1. Committed (unlike the local cache), so this read almost never throws; a missing/empty `gate_step_p90_seconds` before `budget_report.py --refresh` has landed one is exactly the same "nothing to say yet" case as an empty local cache.
  const ciDur: CiDur = {};
  try {
    const laneDurations: { gate_step_p90_seconds?: Record<string, number> } = JSON.parse(
      fs.readFileSync(path.join(REPO, '.ci', 'config', 'lane-durations.json'), 'utf-8')
    );
    for (const [id, seconds] of Object.entries(laneDurations.gate_step_p90_seconds ?? {})) {
      if (typeof seconds === 'number') ciDur[id] = seconds * 1000;
    }
  } catch {
    process.stdout.write(
      '- tier oracle: no CI gate-step timing yet (.ci/config/lane-durations.json), CI-sourced verdicts unjudged\n'
    );
  }

  const unjudged = unjudgedTier(new Set(GATES.map((g) => g.id)), samples, dur, ciDur);
  if (unjudged.length > 0) {
    process.stdout.write(
      `- tier oracle: ${unjudged.length} gate(s) have fewer than ${MIN_SAMPLES_TO_TIER} ` +
        'measurements, so their cost is NOT judged yet: ' +
        `${unjudged
          .slice(0, 6)
          .map(([id, n]) => `${id} (${n})`)
          .join(', ')}${unjudged.length > 6 ? ', ...' : ''}\n`
    );
  }

  const corpus = deadIdCorpus(tracked);
  if (corpus.searched < 500) {
    return refused(
      `the dead-id oracle searched ${corpus.searched} tracked file(s); the tree is not being seen, so its green would mean nothing`
    );
  }

  const findings = [
    ...tierFindings(
      GATES,
      dur,
      samples,
      typical,
      ciDur,
      durAt === -1 ? undefined : `local ${durPath}`
    ),
    ...closureFindings(GATES),
    ...leafFindings(GATES),
    ...globFindings(GATES, tracked),
    ...leafTrackedFindings(GATES, tracked),
    ...deadGateIdFindings(new Set(GATES.map((g) => g.id)), corpus.files),
  ];

  if (findings.length === 0) {
    process.stdout.write(
      `✓ gate manifest: ${GATES.length} entries, ${Object.keys(dur).length} locally measured, ${Object.keys(ciDur).length} CI-measured; tiers, leaves and globs all agree; ${corpus.searched} text file(s) searched for the retired id namespace, ${corpus.files.length} still name it or a record marker\n`
    );
    return 0;
  }
  process.stderr.write(`✗ ${findings.length} gate-manifest finding(s):\n\n`);
  for (const f of findings) process.stderr.write(`  [${f.oracle}] ${f.text}\n`);
  process.stderr.write('\n');
  return 1;
}

process.exitCode = main();
