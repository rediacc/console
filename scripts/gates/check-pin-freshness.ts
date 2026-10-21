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
 * Whatever the state, every major line above a judged pin is aged from the first release on
 * that line (status.ts newerMajors, dated by the driver: a docker line by the instant its tags
 * prove it had begun by, see scripts/lib/pins/drivers/docker.ts). Under the grace in
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
import { driverFor, type PinDriver, registerDrivers } from '../lib/pins/driver.js';
import { realDrivers } from '../lib/pins/drivers/table.js';
import { FAMILY_GATES } from '../lib/pins/family-gates.js';
import { loadRegistry, type PinEntry, type PinRegistry } from '../lib/pins/registry.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { iso } from '../lib/pins/soak.js';
import {
  contextOf,
  getMajorGraceMs,
  type Hold,
  MAJOR_GRACE_CONFIG,
  type NewerMajor,
  type StatusWorld,
  viewOf,
} from '../lib/pins/status.js';
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
  /** The major lines above the pin (status.ts newerMajors). */
  majors?: NewerMajor[];
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
 *   no-hold-liveness    a hold line no leaf answers to passes
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
  'no-hold-liveness',
] as const;
type Mutant = (typeof MUTANTS)[number];

interface Report {
  rc: number;
  out: string[];
  err: string[];
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
  const what = `${a.line.newest} (major ${a.line.major ?? '?'})`;
  if (a.line.firstMs === null) return `${what}: no release on the line carries a date`;
  const first = `first released ${iso(a.line.firstMs)}, ${a.days} day(s) ago`;
  return a.line.partial
    ? `${what}: ${first}, and a release on it carries no date`
    : `${what}: ${first}`;
};

/** The hold-file problems of the judged leaves, given each claimant's hold key. Pure. */
function holdFindings(
  files: Map<string, string | null>,
  claimants: Map<string, Array<{ id: string; key: string | null }>>
): string[] {
  const out: string[] = [];
  for (const [file, text] of files) {
    const owners = claimants.get(file) ?? [];
    const byKey = new Map<string, string[]>();
    for (const o of owners) {
      if (o.key === null) {
        out.push(`${file}: ${o.id} names it as its hold file, but its driver gives no hold key`);
        continue;
      }
      byKey.set(o.key, [...(byKey.get(o.key) ?? []), o.id]);
    }
    for (const [key, ids] of byKey)
      if (ids.length > 1) out.push(`${file}: key ${key} is answered by ${ids.join(' and ')}`);
    if (text === null) continue;
    for (const [i, line] of text.split('\n').entries()) {
      const t = line.trim();
      if (t === '' || t.startsWith('#')) continue;
      const key = t.split(/\s+/)[0];
      if (!byKey.has(key))
        out.push(
          `${file}:${i + 1}: holds ${key}, which no leaf naming this hold file answers to; delete the line`
        );
    }
  }
  return out;
}

/** The clock, the grace on newer majors and the hold-file findings a verdict is given. */
interface Judging {
  nowMs: number;
  graceMs: number;
  holdProblems: string[];
}

/** The verdict over every judged leaf's view. Pure. */
function verdict(sel: Selection, views: LeafView[], majors: Judging, mutant?: Mutant): Report {
  const out: string[] = [];
  const err: string[] = [];
  const seen =
    mutant === 'no-compare' ? views.map((v) => ({ ...v, state: 'current' as const })) : views;
  const of = (s: LeafView['state']) => seen.filter((v) => v.state === s);
  const stale = of('bumpable');
  const blind = mutant === 'unknown-is-fine' ? [] : of('not-compared');

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
    out.push(`  major only  ${v.id}: ${v.detail}`);
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
    const live = v.state === 'held' && h && !h.expired;
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
    overdue.push({ v, ages: due });
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
  const holdRed = mutant === 'no-hold-liveness' ? [] : majors.holdProblems;
  if (holdRed.length > 0) {
    err.push(`✗ ${holdRed.length} hold line(s) or hold key(s) are wrong:`);
    for (const p of holdRed) err.push(`  ${p}`);
  }
  if (stale.length > 0 || blind.length > 0 || majorRed.length > 0 || holdRed.length > 0)
    return { rc: 1, out, err };
  const newer = seen.reduce((n, v) => n + (v.majors?.length ?? 0), 0);
  out.push(
    `✓ ${seen.length} of ${sel.judged.length} leaf(s) compared with upstream: ${of('current').length} current, ${of('deferred').length} deferred, ${of('major-only').length} major only, ${of('held').length} held; ${newer} newer major line(s), none past the ${graceDays}-day grace unexcused`
  );
  return { rc: 0, out, err };
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
function holdProblemsOf(world: StatusWorld, sel: Selection): string[] {
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

/** The run over `root` (the console's, or the selftest's fixture), with the root's release-age window and major grace. */
async function check(root: string, mutant?: Mutant, nowMs: number = Date.now()): Promise<Report> {
  const reg = loadRegistry(path.join(root, '.ci/config/pins.json'));
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
  };
  const sel = selectLeaves(reg);
  const views = await viewsOf(world, sel.judged);
  return verdict(sel, views, { nowMs, graceMs, holdProblems: holdProblemsOf(world, sel) }, mutant);
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
const HOLDS = policyPath('.pins-upgrade-blocklist', '.');
/** The key the toolchain driver writes for a leaf: its id after the colon, as registry.ts names it. */
const holdKeyOf = (id: string): string => id.slice(id.indexOf(':') + 1);

/** A fixture root holding a registry of the named real entries, the files their sites read, the two configs, and `extra` files. */
function fixtureRoot(ids: string[], extra: Record<string, string> = {}): string {
  const real = loadRegistry(path.join(REPO_ROOT, '.ci/config/pins.json'));
  const pick = (id: string): PinEntry => {
    const e = real.entries.find((x) => x.id === id);
    if (!e)
      throw new Error(`the selftest's fixture names ${id}, which the registry no longer holds`);
    return e;
  };
  const entries = ids.map(pick);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pin-freshness-'));
  const reg: PinRegistry = {
    version: 1,
    submodules: { scanned: [], unscanned: [] },
    literalExclude: [],
    entries: entries.map((e) => ({ ...e, sites: e.sites.filter((s) => s.repo === '.') })),
    ignores: [],
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
        .sort()
        .join(',') === [DEFERRED, STALE, DOWN].sort().join(','),
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

    const run = async (m?: Mutant, at: string = root) => {
      const r = await check(at, m, NOW);
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
          l.startsWith(`  new major   ${YOUNG}: 2.1.0 (major 2): first released`) &&
          l.includes(`${UNDER} day(s) ago`) &&
          l.includes(`red from ${iso(NOW + DAY_MS)}`)
      ) && errOf(YOUNG).length === 0,
      mj.all
    );
    add(
      `GRACE ${PAST} days: a newer major past the grace is red, with the bump and the dated hold lines`,
      errOf(AGED).some(
        (l) => l.includes('aged, 2.1.0 (major 2)') && l.includes(`${PAST} day(s) ago`)
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
      mjGreen.rc === 0 && mjGreen.out.some((l) => l.includes('2 newer major line(s)')),
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
      ).some((p) => p.includes('key x is answered by a:x and b:x'))
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
      'no-hold-liveness': async () =>
        (await run('no-hold-liveness', dead)).err.some((l) => l.includes('holds not-a-pin')),
    };
    for (const m of MUTANTS)
      add(
        `MUTANT ${m}: the case relying on it goes green, so the control tests that property`,
        !(await caseFor[m]()),
        'the case still caught the defect with its property disabled'
      );
  } finally {
    for (const r of roots) fs.rmSync(r, { recursive: true, force: true });
  }
  return summarizeControls(cases);
}

async function main(): Promise<number> {
  if (process.argv.includes('--selftest')) return selftest();
  registerDrivers(realDrivers());
  const r = await check(REPO_ROOT);
  for (const l of r.out) console.log(l);
  for (const l of r.err) console.error(l);
  return r.rc;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  process.exit(await main());
}
