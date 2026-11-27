#!/usr/bin/env tsx
/**
 * check:ci-pin-freshness -- every registry leaf that has an upstream source and no
 * freshness gate of its own is compared with that upstream, and a stale one is red
 * (agent/plans/PLAN-pins-command.md Design 5, box T10).
 *
 * WHY. Before this gate the toolchain pins (Go, npm, ruff, mypy, uv, shfmt, shellcheck,
 * actionlint, nfpm, wrangler, the Python test tools) and the devcontainer ARGs outside
 * check:ci-devcontainer-pins' list (staticcheck, goimports, codex, gemini-cli, bottom,
 * agent-browser, openvscode-server) had agreement gates and nothing else: every copy of a
 * pin could agree with every other copy for a year while upstream moved on. The last Go
 * patch move surfaced only through govulncheck reds, and its sha256 lines were copied by hand.
 * The registry already knows each of these pins, its sites and its source, and the pins
 * drivers already know how to read the source; this gate asks them.
 *
 * WHICH LEAVES. A leaf of .ci/config/pins.json whose `source` is not `none` and whose
 * `gates` name none of FAMILY_GATES below. Those gates compare their own pins with upstream
 * (or, for breakpoint, own the vendored copy the pins live in), so judging their leaves here
 * too would be two verdicts for one pin. A leaf with `source: none` carries a BLOCKER reason
 * in the registry, and check:ci-pin-registry validates it; it is counted here, by name.
 *
 * THE VERDICT, per leaf, is `npm run pins -- status <id>`'s (scripts/lib/pins/status.ts viewOf,
 * the code the CLI calls, run in this process):
 *   bumpable      STALE, red. A release past the release-age window is waiting, and the
 *                 failure line is `npm run pins -- bump <id>` (scripts/lib/pins/remedy.ts).
 *   not-compared  red. The upstream did not answer, answered unusably, or no driver serves
 *                 the leaf. Unknown is unchecked, never fine (operator answer: fail closed).
 *   deferred      reported. The newest release is inside the window, or the driver's own
 *                 rule holds it; `pins when <id>`
 *                 names the instant.
 *   major-only    reported, with its `--major --reason` line, unless the major is past its
 *                 grace (below).
 *   held          reported, with the hold file and its reason.
 *   current       counted.
 * Every non-current line is printed on every run, green or red.
 *
 * NEWER MAJORS (operator ruling 2026-10-14T20:56Z, "Red after a grace period (40 days)").
 * Whatever the state, every version line above a judged pin is aged from the first release on
 * that line (status.ts newerMajors, dated by the driver: a docker line by the instant its tags
 * prove it had begun by, see scripts/lib/pins/drivers/docker.ts). A LINE is the first `depth`
 * parts of a version (scripts/lib/pins/lines.ts): the `lines` table of .ci/config/pins.json
 * names the depth per source (python 2, so 3.9 sits below the 3.10 line; node 1), a 0.x version
 * reads at least depth 2, and a source with no row reads 1 (plan #ef324e18; keyed by the first
 * number alone, python 3.9 below 3.15 never aged). A move inside the pinned line is no line: a
 * `major only` leaf whose candidates all sit on its own line says `same line X, never aged`, and
 * the summary counts those leaves. Under the grace in
 * .ci/config/pin-major-grace.json the line is printed with the instant it turns red, and
 * passes. At or past the grace it is RED, and so is a line whose first release cannot be
 * dated (fail closed), until the pin is bumped (`bump <id> --major --reason "<why>"`) or held
 * through `npm run pins -- hold <id> --reason "<why>" --expires YYYY-MM-DD`. Only a DATED,
 * unexpired hold excuses an aged major; it is printed, naming the hold, on every run. An
 * undated hold would excuse the major forever, so it does not.
 *
 * HOLD LIVENESS. Each hold file a judged leaf reads is checked here: a line whose key no leaf
 * of that file answers to holds nothing and is red, and so is a key two leaves answer to.
 *
 * A PINS TRANSACTION'S RUN (worklist #2144097d). `npm run pins -- bump|hold|unhold` runs this gate inside its transaction with
 * PINS_TXN_SCOPE set to the pins it moves or holds (scripts/lib/pins/txn.ts SCOPE_ENV). Every leaf is still compared, and
 * every finding still printed, but only a finding about a pin in the scope is red; any other finding is printed as
 * `outside this transaction:` and appended to the file PINS_TXN_OUTSIDE names, so a red the transaction did not make and does
 * not touch never refuses it, and is never silent. Without the scope two pins that aged together deadlocked: the hold of
 * one was refused on the other's red, and the bump of the other on the first's. A scope naming a pin the registry does not
 * hold is red (a typo would otherwise judge nothing). CI never sets the variable, so its run judges every pin.
 *
 * Red at once, on every cadence (operator answer): the step runs unwrapped, and the
 * no-external-quality label on a pull request is its one hold, named by the job's announcer.
 *
 * ---- gate ----
 * step: Pin upstream freshness
 * needs: node
 * lane: quality-code
 * when: inputs.external_quality != 'skip'
 * env-GITHUB_TOKEN: ${{ github.token }}
 * selftest: true
 * why: a toolchain or devcontainer pin with only agreement gates can be stale for a year
 *      with every copy agreeing; this asks the pin's own source through the pins drivers
 * slow: true
 * ---- end gate ----
 *
 * Usage:
 *   npx tsx scripts/gates/check-pin-freshness.ts             # the check, network
 *   npx tsx scripts/gates/check-pin-freshness.ts --selftest  # fixture controls and mutants, offline
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { createHubReader, hubReader } from '../lib/docker-hub.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { driverFor, type PinDriver, registerDrivers } from '../lib/pins/driver.js';
import { hubDeps } from '../lib/pins/drivers/docker.js';
import { realDrivers } from '../lib/pins/drivers/table.js';
import { FAMILY_GATES } from '../lib/pins/family-gates.js';
import { lineSubject } from '../lib/pins/lines.js';
import {
  lineRowProblems,
  loadRegistry,
  type PinEntry,
  type PinRegistry,
} from '../lib/pins/registry.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { iso } from '../lib/pins/soak.js';
import {
  contextOf,
  getMajorGraceMs,
  type Hold,
  type LineDatedRelease,
  MAJOR_GRACE_CONFIG,
  type NewerMajor,
  type StatusWorld,
  viewOf,
} from '../lib/pins/status.js';
import { readTemplateFiles, scanTemplates } from '../lib/pins/templates.js';
import { OUTSIDE_ENV, SCOPE_ENV } from '../lib/pins/txn.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs } from '../lib/release-age.js';
import { REPO_ROOT } from '../lib/repo-root.js';

interface Selection {
  judged: PinEntry[];
  /** A leaf left to its own freshness gate, with the gate. */
  byFamily: Array<{ id: string; gate: string }>;
  /** A leaf whose registry source is `none` (its BLOCKER reason is check:ci-pin-registry's to validate). */
  noSource: string[];
}

/** Which leaves this gate judges. Pure. */
function selectLeaves(reg: PinRegistry): Selection {
  const out: Selection = { judged: [], byFamily: [], noSource: [] };
  for (const e of reg.entries) {
    if (e.kind !== 'leaf') continue;
    const family = e.gates.find((g) => g in FAMILY_GATES);
    if (family) out.byFamily.push({ id: e.id, gate: family });
    else if (e.source.type === 'none') out.noSource.push(e.id);
    else out.judged.push(e);
  }
  return out;
}

/** One leaf's answer from `pins status <id> --json` (the fields this gate reads). */
interface LeafView {
  id: string;
  state: 'current' | 'bumpable' | 'deferred' | 'held' | 'major-only' | 'not-compared';
  current: string | null;
  detail: string;
  /** The release the window is holding back, with the instant it clears (null when the driver's own rule holds it). */
  deferred?: { clearsAt: number | null } | null;
  /** The version lines above the pin (status.ts newerMajors). */
  majors?: NewerMajor[];
  /** The line of the pinned version (status.ts currentLineOf). */
  currentLine?: string | null;
  hold?: Hold | null;
}

/**
 * The selftest's mutants, each disabling one property; the selftest proves the case that
 * relies on it goes red:
 *   no-compare          every leaf reads as current (the comparison is off)
 *   unknown-is-fine     a leaf that was not compared passes
 *   empty-passes        a run that judged no leaf passes
 *   majors-never-red    the grace rule is off: an aged or undatable major only prints
 *   no-major-age        the age is not read: every newer major is red at once
 *   undatable-is-young  a major whose first release has no date passes
 *   ignore-holds        a dated hold does not excuse an aged major
 *   undated-hold-excuses an undated hold excuses an aged major
 *   expired-excuses     an expired dated hold still excuses an aged major
 *   no-hold-liveness    a hold line no leaf answers to passes
 *   first-number-only   a version line is its first number alone, so python 3.9 below 3.10 is one line
 *   zero-is-major       a 0.x version's line is its 0, so otel 0.111 below 0.166 is one line
 *                       (both are scripts/lib/pins/lines.ts LINE_MUTANTS, passed through StatusWorld)
 *   no-line-rows        a dockerhub leaf with no `lines` row passes, judged at depth 1
 *   scope-ignored       a transaction's scope is ignored: a red about a pin outside it is red
 *   scope-hides-all     a scoped run is never red, even on a finding about a pin inside the scope
 *   scope-silent        a red outside the scope is dropped instead of printed
 */
const MUTANTS = [
  'no-compare',
  'unknown-is-fine',
  'empty-passes',
  'majors-never-red',
  'no-major-age',
  'undatable-is-young',
  'ignore-holds',
  'undated-hold-excuses',
  'expired-excuses',
  'no-hold-liveness',
  'first-number-only',
  'zero-is-major',
  'no-line-rows',
  'scope-ignored',
  'scope-hides-all',
  'scope-silent',
] as const;
type Mutant = (typeof MUTANTS)[number];

interface Report {
  rc: number;
  out: string[];
  err: string[];
  /** Under a transaction's scope, the findings about pins outside it: printed, never red. */
  outside?: string[];
}

const DAY_MS = 86_400_000;

/** How one major line above a pin stands against the grace. */
interface MajorAge {
  line: NewerMajor;
  kind: 'aged' | 'undatable' | 'young';
  /** Whole days since the line's first dated release; null when it has none. */
  days: number | null;
}

/** Each newer major line of a view against the grace. Pure. */
function majorAges(v: LeafView, nowMs: number, graceMs: number, mutant?: Mutant): MajorAge[] {
  return (v.majors ?? []).map((line) => {
    const days = line.firstMs === null ? null : Math.floor((nowMs - line.firstMs) / DAY_MS);
    if (mutant === 'no-major-age') return { line, kind: 'aged' as const, days };
    if (line.firstMs !== null && nowMs - line.firstMs >= graceMs)
      return { line, kind: 'aged' as const, days };
    if ((line.firstMs === null || line.partial) && mutant !== 'undatable-is-young')
      return { line, kind: 'undatable' as const, days };
    return { line, kind: 'young' as const, days };
  });
}

const describeLine = (a: MajorAge): string => {
  const what = `${a.line.newest} (line ${a.line.line})`;
  if (a.line.firstMs === null) return `${what}: no release on the line carries a date`;
  const first = `first released ${iso(a.line.firstMs)}, ${a.days} day(s) ago`;
  return a.line.partial
    ? `${what}: ${first}, and a release on it carries no date`
    : `${what}: ${first}`;
};

/** One hold-file problem, with the pins it concerns (none for a line no leaf answers to), so a transaction's scope can place it. */
interface HoldProblem {
  text: string;
  ids: string[];
}

/** The hold-file problems of the judged leaves, given each claimant's hold key. Pure. */
function holdFindings(
  files: Map<string, string | null>,
  claimants: Map<string, Array<{ id: string; key: string | null }>>
): HoldProblem[] {
  const out: HoldProblem[] = [];
  for (const [file, text] of files) {
    const owners = claimants.get(file) ?? [];
    const byKey = new Map<string, string[]>();
    for (const o of owners) {
      if (o.key === null) {
        out.push({
          text: `${file}: ${o.id} names it as its hold file, but its driver gives no hold key`,
          ids: [o.id],
        });
        continue;
      }
      byKey.set(o.key, [...(byKey.get(o.key) ?? []), o.id]);
    }
    for (const [key, ids] of byKey)
      if (ids.length > 1)
        out.push({ text: `${file}: key ${key} is answered by ${ids.join(' and ')}`, ids });
    if (text === null) continue;
    for (const [i, line] of text.split('\n').entries()) {
      const t = line.trim();
      if (t === '' || t.startsWith('#')) continue;
      const key = t.split(/\s+/)[0];
      if (!byKey.has(key))
        out.push({
          text: `${file}:${i + 1}: holds ${key}, which no leaf naming this hold file answers to; delete the line`,
          ids: [],
        });
    }
  }
  return out;
}

/** The clock, the grace on newer majors, the hold-file findings and the missing `lines` rows a verdict is given. */
interface Judging {
  nowMs: number;
  graceMs: number;
  holdProblems: HoldProblem[];
  /** registry.ts lineRowProblems().missing: a dockerhub leaf whose line depth nobody named. */
  missingLines?: string[];
  /** A pins transaction's scope (PINS_TXN_SCOPE): only a finding about one of these pins is red; null judges every pin. */
  scope?: ReadonlySet<string> | null;
}

/** The verdict over every judged leaf's view. Pure. */
function verdict(sel: Selection, views: LeafView[], majors: Judging, mutant?: Mutant): Report {
  const out: string[] = [];
  const err: string[] = [];
  const seen =
    mutant === 'no-compare' ? views.map((v) => ({ ...v, state: 'current' as const })) : views;
  const of = (s: LeafView['state']) => seen.filter((v) => v.state === s);
  // A transaction's scope: a finding about a pin outside it is printed below as outside, never red.
  const scope = mutant === 'scope-ignored' ? null : (majors.scope ?? null);
  const inScope = (id: string): boolean => scope === null || scope.has(id);
  const outside: string[] = [];
  const stale = of('bumpable').filter((v) => inScope(v.id));
  const blind = mutant === 'unknown-is-fine' ? [] : of('not-compared').filter((v) => inScope(v.id));
  for (const v of of('bumpable').filter((x) => !inScope(x.id)))
    outside.push(`${v.id}: behind a release past the release-age window: ${v.detail}`);
  if (mutant !== 'unknown-is-fine')
    for (const v of of('not-compared').filter((x) => !inScope(x.id)))
      outside.push(`${v.id}: NOT compared with upstream: ${v.detail}`);

  out.push(
    `Pin freshness: ${sel.judged.length} registry leaf(s) with a source and no freshness gate of their own`
  );
  out.push(
    `  left to their own gate: ${sel.byFamily.length} (${[...new Set(sel.byFamily.map((f) => f.gate))].join(', ') || 'none'})`
  );
  out.push(`  no upstream source (BLOCKER in the registry): ${sel.noSource.join(', ') || 'none'}`);
  for (const v of of('deferred')) {
    const at = v.deferred?.clearsAt;
    const clears =
      typeof at === 'number' && !Number.isNaN(new Date(at).getTime())
        ? `, clears the window at ${new Date(at).toISOString()}`
        : '';
    out.push(`  deferred    ${v.id}: ${v.detail}${clears} (npm run pins -- when ${v.id})`);
  }
  for (const v of of('held')) out.push(`  held        ${v.id}: ${v.detail}`);
  for (const v of of('major-only')) {
    const above = v.majors?.[0];
    const tail = above
      ? `; the newest line above is ${above.line}`
      : `; same line ${v.currentLine ?? '?'}, never aged`;
    out.push(`  major only  ${v.id}: ${v.detail}${tail}`);
    out.push(bumpRemedy(v.id, { major: true }));
  }

  // The grace on newer majors: aged or undatable is red unless a dated, unexpired hold excuses it.
  const graceDays = Math.round(majors.graceMs / DAY_MS);
  const overdue: Array<{ v: LeafView; ages: MajorAge[] }> = [];
  for (const v of seen) {
    const ages = majorAges(v, majors.nowMs, majors.graceMs, mutant);
    for (const a of ages.filter((x) => x.kind === 'young'))
      out.push(
        `  new major   ${v.id}: ${describeLine(a)}; red from ${iso((a.line.firstMs as number) + majors.graceMs)} (grace ${graceDays} days)`
      );
    const due = ages.filter((a) => a.kind !== 'young');
    if (due.length === 0) continue;
    const h = v.hold;
    const expiredPasses = mutant === 'expired-excuses';
    const live = (v.state === 'held' || expiredPasses) && h && (!h.expired || expiredPasses);
    if (
      live &&
      mutant !== 'ignore-holds' &&
      (h.expires !== null || mutant === 'undated-hold-excuses')
    ) {
      for (const a of due)
        out.push(
          `  held major  ${v.id}: ${describeLine(a)}; excused by the hold in ${h.file} until ${h.expires ?? '(no date)'}: ${h.reason}`
        );
      continue;
    }
    if (inScope(v.id)) overdue.push({ v, ages: due });
    else
      for (const a of due)
        outside.push(
          `${v.id}: ${a.kind === 'aged' ? 'aged' : 'undatable'} newer line, ${describeLine(a)}`
        );
  }

  if (sel.judged.length === 0 && mutant !== 'empty-passes') {
    err.push(
      '✗ no registry leaf was selected: the gate is not seeing .ci/config/pins.json, so its green would mean nothing'
    );
    return { rc: 1, out, err };
  }
  if (blind.length > 0) {
    err.push(
      `✗ ${blind.length} pin(s) were NOT compared with upstream; unknown is unchecked, not fine:`
    );
    for (const v of blind) err.push(`  ${v.id} (pinned ${v.current ?? '?'}): ${v.detail}`);
  }
  if (stale.length > 0) {
    err.push(`✗ ${stale.length} pin(s) are behind a release past the release-age window:`);
    for (const v of stale) {
      err.push(`  ${v.id}: ${v.detail}`);
      err.push(bumpRemedy(v.id));
    }
  }
  const majorRed = mutant === 'majors-never-red' ? [] : overdue;
  if (majorRed.length > 0) {
    err.push(
      `✗ ${majorRed.length} pin(s) sit below a newer major past the ${graceDays}-day grace (${MAJOR_GRACE_CONFIG}), or one whose first release cannot be dated:`
    );
    for (const { v, ages } of majorRed) {
      for (const a of ages)
        err.push(
          `  ${v.id} (pinned ${v.current ?? '?'}): ${a.kind === 'aged' ? 'aged' : 'undatable'}, ${describeLine(a)}`
        );
      const h = v.hold;
      if (h && !h.expired && h.expires === null)
        err.push(
          `  the hold in ${h.file}:${h.line} carries no expiry, and an undated hold does not excuse an aged major`
        );
      else if (h?.expired) err.push(`  the hold in ${h.file}:${h.line} expired on ${h.expires}`);
      err.push(bumpRemedy(v.id, { major: true }));
      err.push(
        `  or hold it: npm run pins -- hold ${v.id} --reason "<why>" --expires YYYY-MM-DD${h && !h.expired ? ` (after deleting line ${h.line} of ${h.file})` : ''}`
      );
    }
  }
  const holdAll = mutant === 'no-hold-liveness' ? [] : majors.holdProblems;
  const holdRed = holdAll.filter((p) => scope === null || p.ids.some(inScope)).map((p) => p.text);
  for (const p of holdAll.filter((x) => scope !== null && !x.ids.some(inScope)))
    outside.push(`hold file: ${p.text}`);
  if (holdRed.length > 0) {
    err.push(`✗ ${holdRed.length} hold line(s) or hold key(s) are wrong:`);
    for (const p of holdRed) err.push(`  ${p}`);
  }
  // A dockerhub leaf with no `lines` row is judged at depth 1, the reading that kept python 3.9 below 3.15 un-aged: unchecked, so red.
  const lineAll = mutant === 'no-line-rows' ? [] : (majors.missingLines ?? []);
  const lineOf = (p: string): string => p.slice(0, p.indexOf(': '));
  const lineRed = lineAll.filter((p) => inScope(lineOf(p)));
  for (const p of lineAll.filter((x) => !inScope(lineOf(x)))) outside.push(`lines table: ${p}`);
  if (scope !== null && mutant !== 'scope-silent') {
    out.push(
      `  transaction scope (PINS_TXN_SCOPE): ${scope.size} pin(s)${scope.size > 0 ? ` (${[...scope].join(', ')})` : ''}; only a finding about one of them is red`
    );
    for (const o of outside) out.push(`  outside this transaction: ${o}`);
  }
  if (lineRed.length > 0) {
    err.push(
      `✗ ${lineRed.length} docker leaf(s) have no version-line row, so their newer lines cannot be aged at the right depth:`
    );
    for (const p of lineRed) err.push(`  ${p}`);
  }
  if (
    mutant !== 'scope-hides-all' || scope === null
      ? stale.length > 0 ||
        blind.length > 0 ||
        majorRed.length > 0 ||
        holdRed.length > 0 ||
        lineRed.length > 0
      : false
  )
    return { rc: 1, out, err, outside };
  const newer = seen.reduce((n, v) => n + (v.majors?.length ?? 0), 0);
  const sameLine = of('major-only').filter((v) => (v.majors?.length ?? 0) === 0).length;
  out.push(
    `✓ ${seen.length} of ${sel.judged.length} leaf(s) compared with upstream: ${of('current').length} current, ${of('deferred').length} deferred, ${of('major-only').length} major only (${sameLine} on their own line, never aged), ${of('held').length} held; ${newer} newer version line(s), none past the ${graceDays}-day grace unexcused${scope === null ? '' : ` among the ${scope.size} pin(s) of the transaction; ${outside.length} red finding(s) outside it printed above and not judged here`}`
  );
  return { rc: 0, out, err, outside };
}

/**
 * `pins status`'s answer for each judged leaf, concurrently, through the same viewOf the CLI
 * calls (scripts/lib/pins/status.ts). A view that throws is a leaf nobody compared.
 */
async function viewsOf(world: StatusWorld, entries: PinEntry[]): Promise<LeafView[]> {
  const ctx = contextOf(world);
  return Promise.all(
    entries.map(async (e) => {
      try {
        return await viewOf(world, ctx, e);
      } catch (err) {
        return {
          id: e.id,
          state: 'not-compared' as const,
          current: null,
          detail: `the status of the pin could not be computed: ${(err as Error).message}`,
        };
      }
    })
  );
}

/**
 * The hold files the judged leaves read, with every leaf (judged or not) that names the same
 * file first and the key its driver writes there. A file absent from the tree reads as null
 * (check:ci-pin-registry owns a hold file's existence).
 */
function holdProblemsOf(world: StatusWorld, sel: Selection): HoldProblem[] {
  const ctx = contextOf(world);
  const files = new Map<string, string | null>();
  for (const e of sel.judged) {
    const f = e.holds[0];
    if (!f || files.has(f)) continue;
    const abs = path.join(world.root, f);
    files.set(f, fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null);
  }
  const claimants = new Map<string, Array<{ id: string; key: string | null }>>();
  for (const e of world.reg.entries) {
    const f = e.holds[0];
    if (e.kind !== 'leaf' || !f || !files.has(f)) continue;
    const key = driverFor(e, ctx)?.holdKey(e) ?? null;
    claimants.set(f, [...(claimants.get(f) ?? []), { id: e.id, key }]);
  }
  return holdFindings(files, claimants);
}

/**
 * The instant a hold expiry and the release-age window are judged against: `REDIACC_GATE_CLOCK` (an ISO 8601 date or timestamp, the TypeScript twin of `rediacc_ci.core.gate_clock`) when set, else the wall clock.
 * A bad value throws rather than reading today, because a planted clock that silently fell back would pass without running.
 * A planted clock cannot turn a real run green (review finding 914b173e.3): it is honoured only with `REDIACC_GATE_CLOCK_TEST=1` and never under `CI=true`; anywhere else a set `REDIACC_GATE_CLOCK` throws a refusal.
 */
export function gateNowMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env.REDIACC_GATE_CLOCK;
  if (raw === undefined || raw.trim() === '') return Date.now();
  if ((env.CI ?? '').trim().toLowerCase() === 'true')
    throw new Error(
      `REDIACC_GATE_CLOCK is set under CI=true, where no gate may run on a planted clock. Unset REDIACC_GATE_CLOCK; only a gate's --selftest or pytest may plant it.`
    );
  if ((env.REDIACC_GATE_CLOCK_TEST ?? '').trim() !== '1')
    throw new Error(
      `REDIACC_GATE_CLOCK is set outside a test harness (REDIACC_GATE_CLOCK_TEST=1 is not set), so a real gate run would be judged on a date nobody chose. Unset REDIACC_GATE_CLOCK; only a gate's --selftest or pytest may plant it.`
    );
  const text = raw.trim();
  const iso8601 =
    /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;
  // A bare date is already midnight UTC to Date.parse. A naive timestamp (`T` or space separated) would be read as host-local time, so it is spelled out as UTC, as gate_clock.parse reads it.
  const spelled = text.replace(' ', 'T');
  const ms = iso8601.test(text)
    ? Date.parse(
        /(?:Z|[+-]\d{2}:?\d{2})$/.test(text) || !spelled.includes('T') ? spelled : `${spelled}Z`
      )
    : Number.NaN;
  if (Number.isNaN(ms))
    throw new Error(
      `REDIACC_GATE_CLOCK=${JSON.stringify(raw)} is not an ISO 8601 date or timestamp (for example 2027-01-01); the gate refuses to guess, because falling back to today would make a planted clock pass without running`
    );
  console.error(
    `  NOTE: REDIACC_GATE_CLOCK=${raw} moves this gate's clock; this verdict is not today's.`
  );
  return ms;
}

/** The run over `root` (the console's, or the selftest's fixture), with the root's release-age window and major grace. */
async function check(
  root: string,
  mutant?: Mutant,
  nowMs: number = gateNowMs(),
  scope: ReadonlySet<string> | null = null
): Promise<Report> {
  const reg = loadRegistry(path.join(root, '.ci/config/pins.json'));
  const unknown = [...(scope ?? [])].filter((id) => !reg.entries.some((e) => e.id === id));
  if (unknown.length > 0)
    return {
      rc: 1,
      out: [],
      err: [
        `✗ PINS_TXN_SCOPE names ${unknown.join(', ')}, which .ci/config/pins.json does not hold; a scope with a wrong id would judge nothing`,
      ],
    };
  let graceMs: number;
  try {
    graceMs = getMajorGraceMs(path.join(root, MAJOR_GRACE_CONFIG));
  } catch (err) {
    return {
      rc: 1,
      out: [],
      err: [
        `✗ the grace on newer majors is unreadable: ${(err as Error).message}; without it every newer major would pass unjudged`,
      ],
    };
  }
  const world: StatusWorld = {
    root,
    reg,
    fixture: null,
    mutant: null,
    nowMs,
    windowMs: getMinReleaseAgeMs(path.join(root, '.ci/config/release-age.json')),
    ...(mutant === 'first-number-only' || mutant === 'zero-is-major' ? { lineMutant: mutant } : {}),
  };
  const sel = selectLeaves(reg);
  const views = await viewsOf(world, sel.judged);
  return verdict(
    sel,
    views,
    {
      nowMs,
      graceMs,
      holdProblems: holdProblemsOf(world, sel),
      missingLines: lineRowProblems(reg).missing,
      scope,
    },
    mutant
  );
}

// ---- selftest -------------------------------------------------------------------------------

/** Real registry ids, so the fix lines the fixture produces are lines remedy.ts accepts. */
const STALE = 'toolchain:ruff';
const DEFERRED = 'toolchain:mypy';
const DOWN = 'toolchain:uv';
const FAMILY = 'devcontainer:bw';
const NO_SOURCE = 'toolchain:node';
/** The grace controls: a major line one day under and one day past the grace, a held one, an undatable one, and an undated hold. */
const YOUNG = 'toolchain:pyyaml';
const AGED = 'toolchain:pytest';
const HELD = 'toolchain:pytest-xdist';
const UNDATED = 'toolchain:shfmt';
const LAZY_HOLD = 'toolchain:shellcheck';
/**
 * The version-line controls (plan #ef324e18), real docker leaves whose `lines` rows the fixture
 * carries: python (depth 2) one line below 3.10 past the grace, alpine (depth 2) one line below
 * 3.24 under it, and node (depth 1) moving 26.1 to 26.2, on its own line, 400 days ago. ZERO is
 * a toolchain leaf with no `lines` row answering otel-shaped labels: the 0.x rule alone makes
 * 0.166 a line above 0.111. Its labels carry the `<image>:` prefix so the core reads them as a
 * plain bump cannot take them, as it reads every docker candidate.
 */
const LINE_AGED = 'image:cloud-switch-python';
const LINE_YOUNG = 'image:cli-alpine';
const SAME_LINE = 'image:node-alpine';
const ZERO = 'toolchain:actionlint';
const HOLDS = policyPath('.pins-upgrade-blocklist', '.');
/** The key the toolchain driver writes for a leaf: its id after the colon, as registry.ts names it. */
const holdKeyOf = (id: string): string => id.slice(id.indexOf(':') + 1);

/** A fixture root holding a registry of the named real entries, the files their sites read, the two configs, and `extra` files. */
function fixtureRoot(
  ids: string[],
  extra: Record<string, string> = {},
  dropLines: string[] = []
): string {
  const real = loadRegistry(path.join(REPO_ROOT, '.ci/config/pins.json'));
  const pick = (id: string): PinEntry => {
    const e = real.entries.find((x) => x.id === id);
    if (!e)
      throw new Error(`the selftest's fixture names ${id}, which the registry no longer holds`);
    return e;
  };
  const entries = ids.map(pick);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pin-freshness-'));
  // The `lines` rows the picked leaves read, and no other: a row no leaf reads is a registry error.
  const subjects = new Set(
    entries.flatMap((e) => lineSubject(e.source) ?? []).filter((k) => !dropLines.includes(k))
  );
  const reg: PinRegistry = {
    version: 1,
    submodules: { scanned: [], unscanned: [] },
    literalExclude: [],
    entries: entries.map((e) => ({ ...e, sites: e.sites.filter((s) => s.repo === '.') })),
    ignores: [],
    lines: Object.fromEntries(Object.entries(real.lines).filter(([k]) => subjects.has(k))),
  };
  const files = new Set(reg.entries.flatMap((e) => e.sites.map((s) => s.file)));
  for (const rel of [...files, '.ci/config/release-age.json', MAJOR_GRACE_CONFIG]) {
    fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
    fs.copyFileSync(path.join(REPO_ROOT, rel), path.join(root, rel));
  }
  for (const [rel, text] of Object.entries(extra)) {
    fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  fs.writeFileSync(path.join(root, '.ci/config/pins.json'), `${JSON.stringify(reg, null, 2)}\n`);
  return root;
}

/** The selftest's clock: fixed, so a line one day either side of the grace is exactly that on every run. */
const NOW = Date.parse('2026-10-14T12:00:00Z');
/** The grace, in whole days, read from the console's config: the controls sit one day either side of it, so the operator's number lives in the config alone. */
const GRACE_DAYS = getMajorGraceMs(path.join(REPO_ROOT, MAJOR_GRACE_CONFIG)) / DAY_MS;
const UNDER = GRACE_DAYS - 1;
const PAST = GRACE_DAYS + 1;

/**
 * One stub driver for the fixture's toolchain leaves: an aged release, a fresh one, an outage,
 * and, for the grace controls, a 2.0.0 major whose line began a day under or past the grace, or carries no date.
 */
function stubDriver(): PinDriver {
  const major = (firstMs: number | null) =>
    Promise.resolve({
      current: '1.0.0',
      releases: [
        { version: '2.1.0', publishedMs: firstMs === null ? null : firstMs + DAY_MS },
        { version: '2.0.0', publishedMs: firstMs },
      ],
    });
  return {
    name: 'toolchain',
    inspect(entry) {
      if (entry.id === DOWN)
        return Promise.reject(
          new Error(
            'GET api.github.com/repos/astral-sh/uv/releases -> network error ECONNREFUSED, after 3 attempt(s)'
          )
        );
      if (entry.id === YOUNG) return major(NOW - UNDER * DAY_MS);
      if (entry.id === AGED || entry.id === HELD || entry.id === LAZY_HOLD)
        return major(NOW - PAST * DAY_MS);
      if (entry.id === UNDATED) return major(null);
      if (entry.id === ZERO)
        return Promise.resolve({
          current: 'otel/opentelemetry-collector-contrib:0.111.0',
          releases: [
            {
              version: 'otel/opentelemetry-collector-contrib:0.166.0',
              publishedMs: NOW - PAST * DAY_MS,
            },
          ],
        });
      const published = entry.id === STALE ? NOW - 30 * DAY_MS : NOW - 3_600_000;
      return Promise.resolve({
        current: '1.0.0',
        releases: [{ version: '1.0.1', publishedMs: published }],
      });
    },
    plan() {
      return Promise.reject(new Error('the selftest never plans'));
    },
    holdKey: (e) => holdKeyOf(e.id),
  };
}

/**
 * A docker stub for the version-line controls: each leaf answers one candidate whose line the
 * driver dated `ageDays` ago (as the real driver dates a line, by `lineFirstMs`), with the real
 * driver's verdict, so the core reads it as major only. `ageDays` overrides per leaf.
 */
function lineStub(ageDays: Partial<Record<string, number>> = {}): PinDriver {
  const answer: Record<string, { current: string; next: string; days: number }> = {
    [LINE_AGED]: { current: 'python:3.9-slim', next: 'python:3.10-slim', days: PAST },
    [LINE_YOUNG]: { current: 'alpine:3.23', next: 'alpine:3.24', days: UNDER },
    [SAME_LINE]: { current: 'node:26.1-alpine', next: 'node:26.2-alpine', days: 400 },
  };
  return {
    name: 'docker',
    inspect(entry) {
      const a = answer[entry.id];
      if (!a) return Promise.reject(new Error(`the line stub has no answer for ${entry.id}`));
      const next: LineDatedRelease = {
        version: a.next,
        publishedMs: NOW - DAY_MS * 2,
        lineFirstMs: NOW - (ageDays[entry.id] ?? a.days) * DAY_MS,
        verdict: { eligible: true, why: 'a series move, taken only with --major --reason' },
      };
      return Promise.resolve({ current: a.current, releases: [next] });
    },
    plan() {
      return Promise.reject(new Error('the selftest never plans'));
    },
    holdKey: (e) => holdKeyOf(e.id),
  };
}

const NO_HOLDS: Judging = { nowMs: NOW, graceMs: GRACE_DAYS * DAY_MS, holdProblems: [] };

async function selftest(): Promise<number> {
  const cases: ControlCase[] = [];
  const add = (name: string, ok: boolean, detail?: string) => cases.push({ name, ok, detail });
  registerDrivers({ toolchain: stubDriver() });
  const root = fixtureRoot([STALE, DEFERRED, DOWN, FAMILY, NO_SOURCE]);
  const holdLines = [
    `${holdKeyOf(HELD)}  # BLOCKER: the 2.x line drops the plugin API the suite loads (expires 2026-12-01)`,
    `${holdKeyOf(LAZY_HOLD)}  # BLOCKER: the 2.x line changes the exit code contract the hooks read`,
    '',
  ].join('\n');
  const majorsRoot = fixtureRoot([YOUNG, AGED, HELD, UNDATED, LAZY_HOLD], { [HOLDS]: holdLines });
  const roots = [root, majorsRoot];
  try {
    const sel = selectLeaves(loadRegistry(path.join(root, '.ci/config/pins.json')));
    add(
      'selection: the three toolchain leaves are judged',
      sel.judged
        .map((e) => e.id)
        .sort((a, b) => Number(a > b) - Number(a < b))
        .join(',') ===
        [DEFERRED, STALE, DOWN].sort((a, b) => Number(a > b) - Number(a < b)).join(','),
      sel.judged.map((e) => e.id).join(',')
    );
    add(
      'selection: a leaf whose gates name a freshness gate is left to it (control)',
      sel.byFamily.some((f) => f.id === FAMILY && f.gate === 'check:ci-devcontainer-pins')
    );
    add(
      'selection: a leaf with source none is counted, not judged',
      sel.noSource.includes(NO_SOURCE)
    );

    const run = async (m?: Mutant, at: string = root, scope: ReadonlySet<string> | null = null) => {
      const r = await check(at, m, NOW, scope);
      return { ...r, all: [...r.out, ...r.err].join('\n') };
    };
    const base = await run();
    add('the fixture run is red (a stale and an unreachable pin)', base.rc === 1, base.all);
    add(
      'STALE: an aged release is red with its exact fix line',
      base.err.includes(`  fix: npm run pins -- bump ${STALE}`),
      base.all
    );
    add(
      'DEFERRED: a release inside the window is reported, not red',
      base.out.some((l) => l.startsWith(`  deferred    ${DEFERRED}:`)) &&
        !base.err.some((l) => l.includes(DEFERRED)),
      base.all
    );
    add(
      'UNREACHABLE: an upstream that did not answer is red as not compared, naming the host',
      base.err.some((l) => l.startsWith(`  ${DOWN} `) && l.includes('ECONNREFUSED')),
      base.all
    );
    add(
      'UNREACHABLE: and it is not given a bump line',
      !base.err.includes(`  fix: npm run pins -- bump ${DOWN}`),
      base.all
    );

    // The green control: the same fixture with the two red leaves bumped out of the picture by a driver that answers current.
    registerDrivers({
      toolchain: {
        ...stubDriver(),
        inspect: () => Promise.resolve({ current: '1.0.0', releases: [] }),
      },
    });
    const green = await run();
    add(
      'CONTROL: every judged leaf current is green, with the count',
      green.rc === 0 && green.out.some((l) => l.startsWith('✓ 3 of 3')),
      green.all
    );
    registerDrivers({ toolchain: stubDriver() });

    // ---- the grace on newer majors, end to end through viewOf, holdOf and the hold file ----
    const mj = await run(undefined, majorsRoot);
    const errOf = (id: string) => mj.err.filter((l) => l.startsWith(`  ${id} `));
    add(
      `GRACE ${UNDER} days: a newer major under the grace is printed with the instant it turns red, and passes`,
      mj.out.some(
        (l) =>
          l.startsWith(`  new major   ${YOUNG}: 2.1.0 (line 2): first released`) &&
          l.includes(`${UNDER} day(s) ago`) &&
          l.includes(`red from ${iso(NOW + DAY_MS)}`)
      ) && errOf(YOUNG).length === 0,
      mj.all
    );
    add(
      `GRACE ${PAST} days: a newer major past the grace is red, with the bump and the dated hold lines`,
      errOf(AGED).some(
        (l) => l.includes('aged, 2.1.0 (line 2)') && l.includes(`${PAST} day(s) ago`)
      ) &&
        mj.err.includes(`  fix: npm run pins -- bump ${AGED} --major --reason "<why>"`) &&
        mj.err.some((l) =>
          l.startsWith(
            `  or hold it: npm run pins -- hold ${AGED} --reason "<why>" --expires YYYY-MM-DD`
          )
        ),
      mj.all
    );
    add(
      'GRACE held: a dated hold excuses the aged major, and the run names the hold',
      mj.out.some(
        (l) =>
          l.startsWith(`  held major  ${HELD}:`) &&
          l.includes(`excused by the hold in ${HOLDS} until 2026-12-01`) &&
          l.includes('plugin API')
      ) && errOf(HELD).length === 0,
      mj.all
    );
    add(
      'GRACE undatable: a newer major whose first release carries no date is red (fail closed)',
      errOf(UNDATED).some(
        (l) => l.includes('undatable') && l.includes('no release on the line carries a date')
      ),
      mj.all
    );
    add(
      'GRACE undated hold: a hold with no expiry does not excuse an aged major, and says why',
      errOf(LAZY_HOLD).some((l) => l.includes('aged')) &&
        mj.err.some((l) => l.includes(`${HOLDS}:2 carries no expiry`)),
      mj.all
    );
    add('GRACE: the run with aged, undatable and undated-hold majors is red', mj.rc === 1, mj.all);

    // The same majors with the aged, undatable and lazily held leaves bumped: green, and the count names the lines.
    registerDrivers({
      toolchain: {
        ...stubDriver(),
        inspect: (e, c) =>
          [AGED, UNDATED, LAZY_HOLD].includes(e.id)
            ? Promise.resolve({ current: '2.1.0', releases: [] })
            : stubDriver().inspect(e, c),
      },
    });
    const mjGreen = await run(undefined, majorsRoot);
    add(
      'CONTROL: a young major and a dated hold alone are green, counting the newer lines',
      mjGreen.rc === 0 && mjGreen.out.some((l) => l.includes('2 newer version line(s)')),
      mjGreen.all
    );
    registerDrivers({ toolchain: stubDriver() });

    // An expired hold excuses nothing, and is named.
    const expired = fixtureRoot([HELD], {
      [HOLDS]: `${holdKeyOf(HELD)}  # BLOCKER: the 2.x line drops the plugin API the suite loads (expires 2026-10-01)\n`,
    });
    roots.push(expired);
    const ex = await run(undefined, expired);
    add(
      'GRACE expired hold: an expired hold does not excuse the aged major, and the line says so',
      ex.rc === 1 && ex.err.some((l) => l.includes(`${HOLDS}:1 expired on 2026-10-01`)),
      ex.all
    );

    // The expiry date is what ends a hold: a hold dated tomorrow still excuses its aged pin, one dated today (midnight UTC, already past at NOW) does not. The mutant 'expired-excuses' keeps an expired hold excusing, and the pair below must then disagree with the gate.
    const dayAfterNow = new Date(NOW + DAY_MS).toISOString().slice(0, 10);
    const dayOfNow = new Date(NOW).toISOString().slice(0, 10);
    const holdDated = (day: string): string =>
      fixtureRoot([HELD], {
        [HOLDS]: `${holdKeyOf(HELD)}  # BLOCKER: the 2.x line drops the plugin API the suite loads (expires ${day})\n`,
      });
    const futureRoot = holdDated(dayAfterNow);
    const todayRoot = holdDated(dayOfNow);
    roots.push(futureRoot, todayRoot);
    const future = await run(undefined, futureRoot);
    add(
      `EXPIRY future: a hold dated ${dayAfterNow} keeps its aged pin excused, and green`,
      future.rc === 0 &&
        future.out.some(
          (l) => l.startsWith(`  held major  ${HELD}:`) && l.includes(`until ${dayAfterNow}`)
        ),
      future.all
    );
    const today = await run(undefined, todayRoot);
    add(
      `EXPIRY today: a hold dated ${dayOfNow} is expired at NOW, so its aged pin is red and the line names the date`,
      today.rc === 1 &&
        today.err.some((l) => l.startsWith(`  ${HELD} `) && l.includes('aged')) &&
        today.err.some((l) => l.includes(`${HOLDS}:1 expired on ${dayOfNow}`)),
      today.all
    );
    add(
      'EXPIRY: the already-expired fixture (2026-10-01) is red on its aged pin too, not only a printed line',
      ex.err.some((l) => l.startsWith(`  ${HELD} `) && l.includes('aged')),
      ex.all
    );

    // THE CLOCK SEAM (REDIACC_GATE_CLOCK, nightly-green F1): the same fixture and the same hold, judged at a planted instant. The hold dated tomorrow is green at NOW (above) and red once the clock is planted past that date; planting NOW itself must give today's verdict back. A gate that ignored the seam, or read it as an excuse, fails one of the two.
    const clockAt = (iso: string) =>
      gateNowMs({ REDIACC_GATE_CLOCK: iso, REDIACC_GATE_CLOCK_TEST: '1' });
    const planted = await check(futureRoot, undefined, clockAt(`${dayAfterNow}T12:00:00Z`));
    add(
      'CLOCK past the deadline: the hold dated tomorrow, judged at tomorrow noon, is expired and its aged pin is red',
      planted.rc === 1 &&
        planted.err.some((l) => l.includes(`${HOLDS}:1 expired on ${dayAfterNow}`)),
      [...planted.out, ...planted.err].join('\n')
    );
    const plantedNow = await check(futureRoot, undefined, clockAt(new Date(NOW).toISOString()));
    add(
      'CLOCK at NOW: planting the fixture clock itself gives the unplanted verdict (green, hold in force)',
      plantedNow.rc === 0,
      [...plantedNow.out, ...plantedNow.err].join('\n')
    );
    add(
      'CLOCK unset or blank reads the wall clock; a bad value throws instead of reading today',
      Math.abs(gateNowMs({}) - Date.now()) < 60_000 &&
        Math.abs(gateNowMs({ REDIACC_GATE_CLOCK: '  ' }) - Date.now()) < 60_000 &&
        (() => {
          try {
            gateNowMs({ REDIACC_GATE_CLOCK: 'next tuesday', REDIACC_GATE_CLOCK_TEST: '1' });
            return false;
          } catch (e) {
            return (e as Error).message.includes('not an ISO 8601');
          }
        })()
    );
    // A naive timestamp is UTC whatever the host zone, the same reading as rediacc_ci.core.gate_clock.parse (review finding 914b173e.1): T and space separators agree, and a date-only value is midnight UTC.
    const savedTz = process.env.TZ;
    process.env.TZ = 'Asia/Kolkata';
    const naive = ['2027-01-01 06:30', '2027-01-01T06:30', '2027-01-01 06:30:00', '2027-01-01'].map(
      clockAt
    );
    if (savedTz === undefined) delete process.env.TZ;
    else process.env.TZ = savedTz;
    add(
      'CLOCK naive: a space or T separated timestamp without a zone reads as UTC on a non-UTC host, as gate_clock.parse does',
      naive[0] === Date.UTC(2027, 0, 1, 6, 30) &&
        naive[1] === naive[0] &&
        naive[2] === naive[0] &&
        naive[3] === Date.UTC(2027, 0, 1)
    );
    // A planted clock outside the harness, or under CI=true even with the marker, is a refusal and never a verdict.
    const clockRefusal = (env: NodeJS.ProcessEnv): string => {
      try {
        gateNowMs(env);
        return '';
      } catch (e) {
        return (e as Error).message;
      }
    };
    add(
      'CLOCK refused: a planted clock with no test marker, or under CI=true, throws and is never honoured',
      clockRefusal({ REDIACC_GATE_CLOCK: '2020-01-01' }).includes('outside a test harness') &&
        clockRefusal({
          REDIACC_GATE_CLOCK: '2020-01-01',
          REDIACC_GATE_CLOCK_TEST: '1',
          CI: 'true',
        }).includes('CI=true')
    );

    // Hold liveness: a line no leaf answers to is red, naming the line.
    const dead = fixtureRoot([YOUNG], {
      [HOLDS]:
        '# a comment line is not a hold\nnot-a-pin  # BLOCKER: held for a pin this registry does not carry\n',
    });
    roots.push(dead);
    const dd = await run(undefined, dead);
    add(
      'HOLD LIVENESS: a hold line whose key no leaf answers to is red, naming file and line',
      dd.rc === 1 && dd.err.some((l) => l.includes(`${HOLDS}:2: holds not-a-pin`)),
      dd.all
    );
    add(
      'HOLD LIVENESS: two leaves answering to one key is red (pure)',
      holdFindings(
        new Map([[HOLDS, '']]),
        new Map([
          [
            HOLDS,
            [
              { id: 'a:x', key: 'x' },
              { id: 'b:x', key: 'x' },
            ],
          ],
        ])
      ).some((p) => p.text.includes('key x is answered by a:x and b:x'))
    );

    // The grace is read from its config, and an unreadable one is red, not zero.
    const noGrace = fixtureRoot([YOUNG]);
    roots.push(noGrace);
    fs.rmSync(path.join(noGrace, MAJOR_GRACE_CONFIG));
    const ng = await run(undefined, noGrace);
    add(
      'GRACE config: a missing grace config is red, naming the file',
      ng.rc === 1 && ng.err.some((l) => l.includes(MAJOR_GRACE_CONFIG)),
      ng.all
    );

    // A deferred leaf whose detail carries no particular wording still names its instant and its `when` line.
    const when = verdict(
      { judged: [], byFamily: [], noSource: [] },
      [
        {
          id: DEFERRED,
          state: 'deferred',
          current: '1.0.0',
          detail: '1.0.0 -> 1.0.1 deferred: held by the driver',
          deferred: { clearsAt: Date.UTC(2030, 0, 2, 3, 4, 5) },
        },
      ],
      NO_HOLDS,
      'empty-passes'
    );
    add(
      'DEFERRED: whatever the detail says, the instant and the `pins when` line are printed',
      when.out.some(
        (l) =>
          l.startsWith(`  deferred    ${DEFERRED}:`) &&
          l.includes('2030-01-02T03:04:05.000Z') &&
          l.includes(`npm run pins -- when ${DEFERRED}`)
      ),
      when.out.join('\n')
    );

    // An unrenderable instant (NaN, or past the Date range) must not make the report itself throw.
    const bad = (at: number): string[] | null => {
      try {
        return verdict(
          { judged: [], byFamily: [], noSource: [] },
          [
            {
              id: DEFERRED,
              state: 'deferred',
              current: '1.0.0',
              detail: '1.0.0 -> 1.0.1 deferred: held by the driver',
              deferred: { clearsAt: at },
            },
          ],
          NO_HOLDS,
          'empty-passes'
        ).out;
      } catch {
        return null;
      }
    };
    const badOut = [Number.NaN, 8.64e15 + 1].map(bad);
    add(
      'DEFERRED: an unrenderable instant still prints the leaf and its `pins when` line',
      badOut.every(
        (o) =>
          o?.some(
            (l) =>
              l.includes(`npm run pins -- when ${DEFERRED}`) && !l.includes('clears the window')
          ) === true
      ),
      JSON.stringify(badOut)
    );

    const empty = verdict({ judged: [], byFamily: [], noSource: [] }, [], NO_HOLDS);
    add('VACUITY: a run that judged no leaf is red', empty.rc === 1);

    // ---- version lines (plan #ef324e18): a line is the first `depth` parts, end to end through viewOf and the fixture's `lines` rows ----
    registerDrivers({ docker: lineStub() });
    const linesRoot = fixtureRoot([LINE_AGED, LINE_YOUNG, SAME_LINE, ZERO]);
    roots.push(linesRoot);
    const fixtureLines = loadRegistry(path.join(linesRoot, '.ci/config/pins.json')).lines;
    const rowDepth = (k: string): number | undefined =>
      Object.hasOwn(fixtureLines, k) ? fixtureLines[k].depth : undefined;
    add(
      'LINES fixture: the docker leaves carry their real rows (python 2, alpine 2, node 1) and the toolchain leaf none',
      rowDepth('dockerhub:python') === 2 &&
        rowDepth('dockerhub:alpine') === 2 &&
        rowDepth('dockerhub:node') === 1 &&
        Object.keys(fixtureLines).length === 3,
      JSON.stringify(fixtureLines)
    );
    const ln = await run(undefined, linesRoot);
    const lnErr = (id: string) => ln.err.filter((l) => l.startsWith(`  ${id} `));
    add(
      `LINES red: python 3.9 below a 3.10 line first seen ${PAST} days ago is aged, naming the line`,
      lnErr(LINE_AGED).some(
        (l) => l.includes('aged, python:3.10-slim (line 3.10)') && l.includes(`${PAST} day(s) ago`)
      ),
      ln.all
    );
    add(
      'LINES red: otel 0.111 below 0.166 with no `lines` row is aged by the 0.x rule, naming the line',
      lnErr(ZERO).some((l) => l.includes('(line 0.166)') && l.includes('aged')),
      ln.all
    );
    add(
      `LINES control: alpine 3.23 below a 3.24 line ${UNDER} days old is printed as young and passes`,
      ln.out.some(
        (l) =>
          l.startsWith(`  new major   ${LINE_YOUNG}: alpine:3.24 (line 3.24)`) &&
          l.includes('red from')
      ) && lnErr(LINE_YOUNG).length === 0,
      ln.all
    );
    add(
      'LINES control: node 26.1 to 26.2 (depth 1) dated 400 days ago is no line, and says `same line 26, never aged`',
      ln.out.some(
        (l) =>
          l.startsWith(`  major only  ${SAME_LINE}:`) && l.endsWith('; same line 26, never aged')
      ) && lnErr(SAME_LINE).length === 0,
      ln.all
    );
    add('LINES: the run with an aged 3.10 and an aged 0.166 line is red', ln.rc === 1, ln.all);
    registerDrivers({ docker: lineStub({ [LINE_AGED]: UNDER }) });
    registerDrivers({
      toolchain: {
        ...stubDriver(),
        inspect: (e, c) =>
          e.id === ZERO
            ? Promise.resolve({
                current: 'otel/opentelemetry-collector-contrib:0.166.0',
                releases: [],
              })
            : stubDriver().inspect(e, c),
      },
    });
    const lnGreen = await run(undefined, linesRoot);
    add(
      `LINES control: the same python line at ${UNDER} days and otel bumped is green, counting the never-aged leaf`,
      lnGreen.rc === 0 &&
        lnGreen.out.some((l) => l.includes('3 major only (1 on their own line, never aged)')) &&
        lnGreen.out.some((l) =>
          l.startsWith(`  new major   ${LINE_AGED}: python:3.10-slim (line 3.10)`)
        ),
      lnGreen.all
    );
    registerDrivers({ docker: lineStub(), toolchain: stubDriver() });

    // A dockerhub leaf with no `lines` row is red, naming the row to add (registry.ts lineRowProblems).
    const rowless = fixtureRoot([LINE_YOUNG], {}, ['dockerhub:alpine']);
    roots.push(rowless);
    const rl = await run(undefined, rowless);
    add(
      'LINES: a docker leaf with no `lines` row is red, naming the row "dockerhub:alpine"',
      rl.rc === 1 &&
        rl.err.some((l) =>
          l.includes(`${LINE_YOUNG}: a dockerhub leaf needs a row "dockerhub:alpine"`)
        ),
      rl.all
    );

    // ---- a pins transaction's scope (worklist #2144097d): only a finding about a pin the transaction moves or holds is red ----
    const outsideOf = (r: { out: string[] }, id: string) =>
      r.out.some((l) => l.startsWith(`  outside this transaction: ${id}: `));
    const scopedGreen = await run(undefined, root, new Set([DEFERRED]));
    add(
      'SCOPE: a stale and an unreachable pin outside the transaction do not refuse it, and both are printed as outside',
      scopedGreen.rc === 0 &&
        outsideOf(scopedGreen, STALE) &&
        outsideOf(scopedGreen, DOWN) &&
        scopedGreen.err.length === 0 &&
        scopedGreen.outside?.length === 2,
      scopedGreen.all
    );
    const scopedRed = await run(undefined, root, new Set([STALE]));
    add(
      'SCOPE (control): a stale pin inside the transaction is still red with its fix line, the unreachable one outside it printed',
      scopedRed.rc === 1 &&
        scopedRed.err.includes(`  fix: npm run pins -- bump ${STALE}`) &&
        !scopedRed.err.some((l) => l.includes(DOWN)) &&
        outsideOf(scopedRed, DOWN),
      scopedRed.all
    );
    const scopedMajor = await run(undefined, majorsRoot, new Set([HELD, YOUNG]));
    add(
      'SCOPE: aged and undatable majors outside the transaction are printed as outside, and a held one inside it passes',
      scopedMajor.rc === 0 &&
        outsideOf(scopedMajor, AGED) &&
        outsideOf(scopedMajor, UNDATED) &&
        outsideOf(scopedMajor, LAZY_HOLD),
      scopedMajor.all
    );
    const scopedMajorRed = await run(undefined, majorsRoot, new Set([AGED]));
    add(
      'SCOPE (control): an aged major inside the transaction is red',
      scopedMajorRed.rc === 1 && scopedMajorRed.err.some((l) => l.startsWith(`  ${AGED} `)),
      scopedMajorRed.all
    );
    const scopedDead = await run(undefined, dead, new Set([YOUNG]));
    add(
      'SCOPE: a dead hold line no pin of the transaction answers to is printed as outside, not red',
      scopedDead.rc === 0 &&
        scopedDead.out.some(
          (l) => l.startsWith('  outside this transaction: hold file: ') && l.includes('not-a-pin')
        ),
      scopedDead.all
    );
    const scopedTypo = await run(undefined, root, new Set(['toolchain:no-such-pin']));
    add(
      'SCOPE: a scope naming a pin the registry does not hold is red, naming it',
      scopedTypo.rc === 1 && scopedTypo.err.some((l) => l.includes('toolchain:no-such-pin')),
      scopedTypo.all
    );
    add(
      'SCOPE: the variable unset judges every pin; set and empty judges none of them red, comma list split and trimmed',
      scopeOf({}) === null &&
        scopeOf({ [SCOPE_ENV]: '' })?.size === 0 &&
        [...(scopeOf({ [SCOPE_ENV]: ' a:x, b:y ,' }) ?? [])].join('|') === 'a:x|b:y'
    );

    // Each mutant disables one property; the case that relies on it must then fail.
    const mjRun = async (m: Mutant) => run(m, majorsRoot);
    const caseFor: Record<Mutant, () => Promise<boolean>> = {
      'no-compare': async () =>
        (await run('no-compare')).err.some((l) => l.includes(`bump ${STALE}`)),
      'unknown-is-fine': async () =>
        (await run('unknown-is-fine')).err.some((l) => l.startsWith(`  ${DOWN} `)),
      'empty-passes': async () =>
        verdict({ judged: [], byFamily: [], noSource: [] }, [], NO_HOLDS, 'empty-passes').rc === 1,
      'majors-never-red': async () =>
        (await mjRun('majors-never-red')).err.some((l) => l.startsWith(`  ${AGED} `)),
      'no-major-age': async () =>
        !(await mjRun('no-major-age')).err.some((l) => l.startsWith(`  ${YOUNG} `)),
      'undatable-is-young': async () =>
        (await mjRun('undatable-is-young')).err.some((l) => l.startsWith(`  ${UNDATED} `)),
      'ignore-holds': async () =>
        !(await mjRun('ignore-holds')).err.some((l) => l.startsWith(`  ${HELD} `)),
      'undated-hold-excuses': async () =>
        (await mjRun('undated-hold-excuses')).err.some((l) => l.startsWith(`  ${LAZY_HOLD} `)),
      'expired-excuses': async () =>
        (await run('expired-excuses', todayRoot)).err.some((l) => l.startsWith(`  ${HELD} `)),
      'no-hold-liveness': async () =>
        (await run('no-hold-liveness', dead)).err.some((l) => l.includes('holds not-a-pin')),
      'first-number-only': async () =>
        (await run('first-number-only', linesRoot)).err.some((l) =>
          l.startsWith(`  ${LINE_AGED} `)
        ),
      'zero-is-major': async () =>
        (await run('zero-is-major', linesRoot)).err.some((l) => l.startsWith(`  ${ZERO} `)),
      'no-line-rows': async () =>
        (await run('no-line-rows', rowless)).err.some((l) =>
          l.includes('needs a row "dockerhub:alpine"')
        ),
      'scope-ignored': async () => (await run('scope-ignored', root, new Set([DEFERRED]))).rc === 0,
      'scope-hides-all': async () =>
        (await run('scope-hides-all', root, new Set([STALE]))).rc === 1,
      'scope-silent': async () =>
        outsideOf(await run('scope-silent', root, new Set([DEFERRED])), STALE),
    };
    for (const m of MUTANTS)
      add(
        `MUTANT ${m}: the case relying on it goes green, so the control tests that property`,
        !(await caseFor[m]()),
        'the case still caught the defect with its property disabled'
      );
    // THE DOCKER HUB READ PATH. Production docker pins read through the shared reader (scripts/lib/docker-hub.ts, whose own controls run in check:ci-docker-image-freshness). Both directions: an answer reaches the driver, and a 429 reaches it as NotCompared.
    const hubUrl = 'https://hub.test/v2/repositories/library/node/tags/26-slim';
    const fakeFetch =
      (status: number, sent: string[]): typeof fetch =>
      async (input) => {
        sent.push(String(input));
        return new Response(status === 200 ? '{"digest":"x"}' : '', { status });
      };
    const okSent: string[] = [];
    const okDeps = hubDeps(root, () =>
      createHubReader({
        origin: 'https://hub.test',
        fetch: fakeFetch(200, okSent),
        cacheDir: null,
        credentials: null,
      })
    );
    const answered = (await okDeps.json(hubUrl, 'node')) as { digest?: string };
    add(
      'read path: a docker pin reads Docker Hub through the shared reader, and its answer reaches the driver',
      answered.digest === 'x' && okSent.join() === hubUrl,
      okSent.join()
    );
    const limitedDeps = hubDeps(root, () =>
      createHubReader({
        origin: 'https://hub.test',
        fetch: fakeFetch(429, []),
        cacheDir: null,
        credentials: null,
        waitBudgetMs: 0,
      })
    );
    const refused = await limitedDeps.json(hubUrl, 'node').then(
      () => 'answered',
      (e: Error) => `${e.name}: ${e.message}`
    );
    add(
      'read path (control): a 429 reaches the driver as NotCompared naming the 429, so the pin reads not compared, never current',
      refused.includes('HTTP 429') && refused !== 'answered',
      refused
    );
    add(
      'read path: a plan reads its digest past the cache (jsonFresh is wired)',
      typeof okDeps.jsonFresh === 'function'
    );
  } finally {
    for (const r of roots) fs.rmSync(r, { recursive: true, force: true });
  }
  return summarizeControls(cases);
}

/** The transaction scope PINS_TXN_SCOPE names: null when the variable is unset (every pin is judged), an empty set when it names none. Pure. */
function scopeOf(env: NodeJS.ProcessEnv): ReadonlySet<string> | null {
  const raw = env[SCOPE_ENV];
  if (raw === undefined) return null;
  return new Set(
    raw
      .split(',')
      .map((x) => x.trim())
      .filter((x) => x !== '')
  );
}

async function main(): Promise<number> {
  if (process.argv.includes('--selftest')) return selftest();
  registerDrivers(realDrivers());
  const r = await check(REPO_ROOT, undefined, gateNowMs(), scopeOf(process.env));
  for (const l of r.out) console.log(l);
  const outsideFile = process.env[OUTSIDE_ENV];
  if (outsideFile && r.outside && r.outside.length > 0)
    // tree-write: safe the append goes to the file PINS_TXN_OUTSIDE names, which only the pins transaction sets (txn.ts), to outside.txt in its journal under .ci/cache/pins (gitignored cache, never tracked tree); an unset variable writes nothing, and a caller that points it elsewhere owns that path
    fs.appendFileSync(outsideFile, r.outside.map((l) => `check:ci-pin-freshness: ${l}\n`).join(''));
  // The app templates' references that name no version are no leaf (scripts/lib/pins/templates.ts), so nothing above judges them; they are named on every run instead of passing in silence.
  const { unpinned } = scanTemplates(readTemplateFiles(REPO_ROOT));
  console.log(
    `  unpinned app template image(s), no version to compare (${unpinned.length}): ${unpinned.map(({ img, why }) => `${img.file}:${img.line} ${img.ref} (${why})`).join('; ') || 'none'}`
  );
  console.log(`  ${hubReader().summary()}`);
  const note = hubReader().credentialNote();
  if (note) console.log(`  ! ${note}`);
  for (const l of r.err) console.error(l);
  return r.rc;
}

if (isEntryPoint(import.meta.filename)) {
  process.exit(await main());
}
