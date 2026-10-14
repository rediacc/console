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
 *                 rule holds it (a Go minor line is the operator's call); `pins when <id>`
 *                 names the instant.
 *   major-only    reported, with its `--major --reason` line. The registry's safety for the
 *                 pin says a major move is a judgment, and `bump` refuses it without one, so
 *                 demanding it here would leave the tree red with no command that clears it.
 *   held          reported, with the hold file and its reason.
 *   current       counted.
 * Every non-current line is printed on every run, green or red.
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
import { type PinDriver, registerDrivers } from '../lib/pins/driver.js';
import { realDrivers } from '../lib/pins/drivers/table.js';
import { loadRegistry, type PinEntry, type PinRegistry } from '../lib/pins/registry.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { contextOf, type StatusWorld, viewOf } from '../lib/pins/status.js';
import { getMinReleaseAgeMs } from '../lib/release-age.js';
import { REPO_ROOT } from '../lib/repo-root.js';

/** The gates that judge their own leaves' freshness, so a leaf naming one is not judged here. */
const FAMILY_GATES: Record<string, string> = {
  'check:ci-embed-asset-freshness': 'the embedded binaries of private/renet',
  'check:ci-devcontainer-pins': 'the devcontainer CLIs it lists',
  'check:ci-real-provider-pins': 'the real-provider lock',
  'check:ci-ceph-image-pin':
    'the Ceph image and host pins (review date and same-host-version rule)',
  'check:ci-breakpoint-drift':
    'the vendored .ci/breakpoint copy, whose pins move only with a re-vendor of the canonical repo',
};

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
}

/**
 * The selftest's mutants, each disabling one property; the selftest proves the case that
 * relies on it goes red:
 *   no-compare      every leaf reads as current (the comparison is off)
 *   unknown-is-fine a leaf that was not compared passes
 *   empty-passes    a run that judged no leaf passes
 */
const MUTANTS = ['no-compare', 'unknown-is-fine', 'empty-passes'] as const;
type Mutant = (typeof MUTANTS)[number];

interface Report {
  rc: number;
  out: string[];
  err: string[];
}

/** The verdict over every judged leaf's view. Pure. */
function verdict(sel: Selection, views: LeafView[], mutant?: Mutant): Report {
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
      typeof at === 'number' ? `, clears the window at ${new Date(at).toISOString()}` : '';
    out.push(`  deferred    ${v.id}: ${v.detail}${clears} (npm run pins -- when ${v.id})`);
  }
  for (const v of of('held')) out.push(`  held        ${v.id}: ${v.detail}`);
  for (const v of of('major-only')) {
    out.push(`  major only  ${v.id}: ${v.detail}`);
    out.push(bumpRemedy(v.id, { major: true }));
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
  if (stale.length > 0 || blind.length > 0) return { rc: 1, out, err };
  out.push(
    `✓ ${seen.length} of ${sel.judged.length} leaf(s) compared with upstream: ${of('current').length} current, ${of('deferred').length} deferred, ${of('major-only').length} major only, ${of('held').length} held`
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

/** The run over `root` (the console's, or the selftest's fixture), with the live clock and the root's release-age window. */
async function check(root: string, mutant?: Mutant): Promise<Report> {
  const reg = loadRegistry(path.join(root, '.ci/config/pins.json'));
  const world: StatusWorld = {
    root,
    reg,
    fixture: null,
    mutant: null,
    nowMs: Date.now(),
    windowMs: getMinReleaseAgeMs(path.join(root, '.ci/config/release-age.json')),
  };
  const sel = selectLeaves(reg);
  return verdict(sel, await viewsOf(world, sel.judged), mutant);
}

// ---- selftest -------------------------------------------------------------------------------

const DAY_MS = 86_400_000;
/** Real registry ids, so the fix lines the fixture produces are lines remedy.ts accepts. */
const STALE = 'toolchain:ruff';
const DEFERRED = 'toolchain:mypy';
const DOWN = 'toolchain:uv';
const FAMILY = 'devcontainer:bw';
const NO_SOURCE = 'toolchain:node';

/** A fixture root holding a registry of five real entries and the files their sites read. */
function fixtureRoot(): string {
  const real = loadRegistry(path.join(REPO_ROOT, '.ci/config/pins.json'));
  const pick = (id: string): PinEntry => {
    const e = real.entries.find((x) => x.id === id);
    if (!e)
      throw new Error(`the selftest's fixture names ${id}, which the registry no longer holds`);
    return e;
  };
  const entries = [STALE, DEFERRED, DOWN, FAMILY, NO_SOURCE].map(pick);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pin-freshness-'));
  const reg: PinRegistry = {
    version: 1,
    submodules: { scanned: [], unscanned: [] },
    literalExclude: [],
    entries: entries.map((e) => ({ ...e, sites: e.sites.filter((s) => s.repo === '.') })),
    ignores: [],
  };
  const files = new Set(reg.entries.flatMap((e) => e.sites.map((s) => s.file)));
  for (const rel of [...files, '.ci/config/release-age.json']) {
    fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
    fs.copyFileSync(path.join(REPO_ROOT, rel), path.join(root, rel));
  }
  fs.writeFileSync(path.join(root, '.ci/config/pins.json'), `${JSON.stringify(reg, null, 2)}\n`);
  return root;
}

/** One stub driver for the fixture's toolchain leaves: an aged release, a fresh one, and an outage. */
function stubDriver(): PinDriver {
  const now = Date.now();
  return {
    name: 'toolchain',
    inspect(entry) {
      if (entry.id === DOWN)
        return Promise.reject(
          new Error(
            'GET api.github.com/repos/astral-sh/uv/releases -> network error ECONNREFUSED, after 3 attempt(s)'
          )
        );
      const published = entry.id === STALE ? now - 30 * DAY_MS : now - 3_600_000;
      return Promise.resolve({
        current: '1.0.0',
        releases: [{ version: '1.0.1', publishedMs: published }],
      });
    },
    plan() {
      return Promise.reject(new Error('the selftest never plans'));
    },
    holdKey: () => null,
  };
}

async function selftest(): Promise<number> {
  const cases: ControlCase[] = [];
  const add = (name: string, ok: boolean, detail?: string) => cases.push({ name, ok, detail });
  registerDrivers({ toolchain: stubDriver() });
  const root = fixtureRoot();
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

    const run = async (m?: Mutant) => {
      const r = await check(root, m);
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

    const empty = verdict({ judged: [], byFamily: [], noSource: [] }, []);
    add('VACUITY: a run that judged no leaf is red', empty.rc === 1);

    const caseFor: Record<Mutant, () => Promise<boolean>> = {
      'no-compare': async () =>
        (await run('no-compare')).err.some((l) => l.includes(`bump ${STALE}`)),
      'unknown-is-fine': async () =>
        (await run('unknown-is-fine')).err.some((l) => l.startsWith(`  ${DOWN} `)),
      'empty-passes': async () =>
        verdict({ judged: [], byFamily: [], noSource: [] }, [], 'empty-passes').rc === 1,
    };
    for (const m of MUTANTS)
      add(
        `MUTANT ${m}: the case relying on it goes green, so the control tests that property`,
        !(await caseFor[m]()),
        'the case still caught the defect with its property disabled'
      );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
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
