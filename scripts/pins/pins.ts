#!/usr/bin/env tsx
/**
 * `npm run pins -- <verb>`: one command for every pinned version in .ci/config/pins.json
 * (agent/plans/PLAN-pins-command.md Design 3).
 *
 *   status [<id>] [--json]                 what each pin is, and what it could move to
 *   when <id> [--json]                     when the newest too-new release clears the window,
 *                                          with a ready worklist DEFAULT line
 *   plan <id>|--all [--json]               the rewrite a bump would make; writes nothing
 *   bump <id> [--to <v>] [--major --reason "<why>"] [--task <id>] [--json] [--out <dir>]
 *   bump --all [--task <id>] [--json] [--out <dir>]
 *   apply-soaked [--task <id>] [--json] [--out <dir>]
 *                                          bump --all limited to patches and in-range minors
 *   hold <id> --reason "<why>" [--expires YYYY-MM-DD] [--task <id>]
 *   verify [--restore <stamp> [--inflight <file>]...] [--json]
 *                                          every leaf site matches its count and agrees;
 *                                          no run was killed mid-write
 *   --selftest                             the fixture controls and their mutants
 *
 * WHAT IT NEVER DOES: commit, push, or pick a release inside the release-age window. A bump
 * is one transaction (scripts/lib/pins/txn.ts): planned in full first, refused whole when a
 * site does not match its `expect` count or a site file holds another session's changes,
 * journaled, written, derived, canonicalised, gated, and restored by comparison on any
 * failure. A finished run prints, per repo and submodules first, the exact `git add` and
 * `git commit -F <draft> -- <paths>` lines, with the drafts under .ci/cache/pins/<stamp>/.
 *
 * THE DRIVERS are scripts/lib/pins/driver.ts's seam. They land with T4/T6 (npm), T7 (embed,
 * devcontainer, toolchain) and T8 (actions, go-mod, the ceph pins, real-provider, docker);
 * until then an entry whose driver is absent reads as NOT COMPARED, and every verb that
 * needs a driver refuses it, fail closed.
 *
 * THE FIXTURE SEAM: PINS_ROOT moves the root to a fixture tree; PINS_FIXTURE (honoured only
 * with PINS_ROOT) supplies the releases, the clock and a stub runner for every command;
 * PINS_MUTANT (honoured only under a fixture) disables one safety property, and `--selftest`
 * proves each one's case goes red.
 */
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { validateBlockerQuality } from '../lib/blocker-validator.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import {
  type DriverContext,
  driverFor,
  type FileWrite,
  type Fixture,
  type Inspection,
  keyOf,
  leafCurrent,
  MUTANTS,
  type Mutant,
  type PinPlan,
  PlanRefused,
  type Release,
  readFixture,
} from '../lib/pins/driver.js';
import {
  loadRegistry,
  type PinEntry,
  type PinRegistry,
  siteMatches,
} from '../lib/pins/registry.js';
import { inRange, iso, judge, majorOf, soakClearsAt, type Verdict } from '../lib/pins/soak.js';
import {
  type CommandRecord,
  fixtureRunner,
  openJournals,
  type RepoChange,
  RestoreRefused,
  type Runner,
  realRunner,
  restoreJournal,
  runTransaction,
  type TxnResult,
  takeLock,
} from '../lib/pins/txn.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import { REPO_ROOT } from '../lib/repo-root.js';

// ---- the run's world ------------------------------------------------------------------------

interface World {
  root: string;
  reg: PinRegistry;
  fixture: Fixture | null;
  mutant: Mutant | null;
  nowMs: number;
  windowMs: number;
  npmVersion: string | null;
  runner: Runner;
  out: string[];
  err: string[];
}

class Usage extends Error {}

function makeWorld(env: NodeJS.ProcessEnv): World {
  const override = env.PINS_ROOT;
  const root = override ? path.resolve(override) : REPO_ROOT;
  const fixture = override && env.PINS_FIXTURE ? readFixture(env.PINS_FIXTURE) : null;
  let mutant: Mutant | null = null;
  if (env.PINS_MUTANT) {
    if (!fixture || !(MUTANTS as readonly string[]).includes(env.PINS_MUTANT))
      throw new Usage(
        `PINS_MUTANT=${env.PINS_MUTANT} refused: the mutants are ${MUTANTS.join(', ')}, honoured only under PINS_ROOT and PINS_FIXTURE`
      );
    mutant = env.PINS_MUTANT as Mutant;
  }
  const tc = path.join(root, '.devcontainer/toolchain.env');
  const npm = fs.existsSync(tc) ? /^NPM_VERSION=(\S+)$/m.exec(fs.readFileSync(tc, 'utf8')) : null;
  return {
    root,
    reg: loadRegistry(path.join(root, '.ci/config/pins.json')),
    fixture,
    mutant,
    nowMs: fixture ? Date.parse(fixture.now) : Date.now(),
    windowMs: getMinReleaseAgeMs(path.join(root, '.ci/config/release-age.json')),
    npmVersion: npm ? npm[1] : null,
    runner: fixture ? fixtureRunner(root, fixture) : realRunner,
    out: [],
    err: [],
  };
}

function contextOf(w: World): DriverContext & { overlay: Map<string, string> } {
  const overlay = new Map<string, string>();
  return {
    root: w.root,
    reg: w.reg,
    fixture: w.fixture,
    mutant: w.mutant,
    overlay,
    read(p) {
      const hit = overlay.get(keyOf(p));
      if (hit !== undefined) return hit;
      const abs = path.join(w.root, p.repo, p.file);
      return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
    },
  };
}

// ---- holds ----------------------------------------------------------------------------------

interface Hold {
  file: string;
  key: string;
  reason: string;
  expires: string | null;
  expired: boolean;
}

/** The hold of an entry, read from its first `holds` file: a line whose first token is the driver's key. */
function holdOf(w: World, entry: PinEntry, key: string | null): Hold | null {
  const file = entry.holds[0];
  if (!file || key === null) return null;
  const abs = path.join(w.root, file);
  if (!fs.existsSync(abs)) return null;
  const lines = fs.readFileSync(abs, 'utf8').split('\n');
  for (const [i, line] of lines.entries()) {
    const t = line.trim();
    if (t === '' || t.startsWith('#') || t.split(/\s+/)[0] !== key) continue;
    const inline = /#\s*(.*)$/.exec(t)?.[1] ?? '';
    const reason =
      inline ||
      (lines[i - 1]?.trim().startsWith('#') ? lines[i - 1].trim().replace(/^#\s*/, '') : '');
    const expires = /expires (\d{4}-\d\d-\d\d)/.exec(reason)?.[1] ?? null;
    return {
      file,
      key,
      reason,
      expires,
      expired: expires !== null && Date.parse(`${expires}T00:00:00Z`) <= w.nowMs,
    };
  }
  return null;
}

// ---- status and target selection ------------------------------------------------------------

interface PinView {
  id: string;
  name: string;
  driver: string;
  state: 'current' | 'bumpable' | 'deferred' | 'held' | 'major-only' | 'not-compared';
  current: string | null;
  target: Release | null;
  /** The newest release inside the window, when one is. */
  deferred: (Release & { clearsAt: number | null }) | null;
  verdict: Verdict | null;
  hold: Hold | null;
  detail: string;
}

interface SelectOpts {
  to?: string;
  allowMajor?: boolean;
  onlyInRange?: boolean;
}

async function viewOf(
  w: World,
  ctx: DriverContext,
  entry: PinEntry,
  sel: SelectOpts = {}
): Promise<PinView> {
  const base: PinView = {
    id: entry.id,
    name: entry.name,
    driver: entry.driver,
    state: 'not-compared',
    current: entry.kind === 'leaf' ? leafCurrent(entry, ctx) : null,
    target: null,
    deferred: null,
    verdict: null,
    hold: null,
    detail: '',
  };
  const drv = driverFor(entry, ctx);
  if (!drv) {
    base.detail = `not compared: the ${entry.driver} driver has not landed (agent/plans/PLAN-pins-command.md T4-T8)`;
    return base;
  }
  let insp: Inspection;
  try {
    insp = await drv.inspect(entry, ctx);
  } catch (err) {
    base.detail = `not compared: ${(err as Error).message}`;
    return base;
  }
  base.current = insp.current;
  base.hold = holdOf(w, entry, drv.holdKey(entry));
  if (insp.releases.length === 0) return { ...base, state: 'current', detail: 'current' };
  if (base.hold && !base.hold.expired)
    return { ...base, state: 'held', detail: `held in ${base.hold.file}: ${base.hold.reason}` };

  let pool = insp.releases;
  if (sel.to !== undefined) {
    pool = pool.filter((r) => r.version === sel.to);
    if (pool.length === 0)
      return {
        ...base,
        detail: `not compared: ${sel.to} is not among the releases newer than ${insp.current} the source answered`,
      };
  }
  const isMajor = (r: Release): boolean => {
    const a = insp.current === null ? null : majorOf(insp.current);
    const b = majorOf(r.version);
    return a === null || b === null || a !== b;
  };
  const admitted = pool.filter((r) =>
    sel.onlyInRange ? inRange(insp.current, r.version) : sel.allowMajor || !isMajor(r)
  );
  for (const r of admitted) {
    const v = judge(entry, r, w.nowMs, w.windowMs, w.mutant === 'ignore-soak');
    if (v.eligible)
      return {
        ...base,
        state: 'bumpable',
        target: r,
        verdict: v,
        detail: `${insp.current} -> ${r.version} (${v.why})`,
      };
    if (!base.deferred) base.deferred = { ...r, clearsAt: v.clearsAt };
    base.verdict ??= v;
  }
  if (base.deferred)
    return {
      ...base,
      state: 'deferred',
      detail: `${insp.current} -> ${base.deferred.version} deferred: ${base.verdict?.why}`,
    };
  return {
    ...base,
    state: 'major-only',
    detail: `only a major or out-of-range release is newer (${pool[0].version}); \`bump ${entry.id} --major --reason "<why>"\``,
  };
}

function pick(w: World, idOrAll: string | undefined, all: boolean): PinEntry[] {
  if (all) return w.reg.entries;
  if (!idOrAll) throw new Usage('name a pin id, or pass --all');
  const e = w.reg.entries.find((x) => x.id === idOrAll);
  if (!e) throw new Usage(`no pin ${idOrAll} in .ci/config/pins.json`);
  return [e];
}

// ---- drafts ---------------------------------------------------------------------------------

interface RepoDraft extends RepoChange {
  draft: string;
  lines: string[];
}

const slug = (repo: string): string => (repo === '.' ? 'console' : repo.replace(/[^\w.-]+/g, '-'));

function writeDrafts(
  w: World,
  res: TxnResult,
  plans: PinPlan[],
  views: Map<string, PinView>,
  task: string | null,
  subject: string
): RepoDraft[] {
  const subs = res.changes.filter((c) => c.repo !== '.').map((c) => c.repo);
  const repos = [...res.changes];
  if (subs.length > 0 && !repos.some((c) => c.repo === '.'))
    repos.push({ repo: '.', paths: [], added: [] });
  const pinLines = plans.map((p) => {
    if (p.from === p.to.version) return `${p.entry.id}: held at ${p.from}.`;
    const v = views.get(p.entry.id);
    const pub =
      p.to.publishedMs === null ? 'publish time unknown' : `published ${iso(p.to.publishedMs)}`;
    const clear =
      p.to.publishedMs === null
        ? ''
        : `, soak cleared ${iso(soakClearsAt(p.to.publishedMs, w.windowMs) ?? p.to.publishedMs)}`;
    return `${p.entry.id}: ${p.from ?? '?'} -> ${p.to.version}, ${pub}${clear}${v?.verdict ? ` (${v.verdict.why})` : ''}.`;
  });
  const cmdLine = (c: CommandRecord): string => `${c.cmd} (in ${c.cwd}) rc=${c.rc}`;
  return repos.map((c) => {
    const paths = c.repo === '.' ? [...c.paths, ...subs] : c.paths;
    const body = [
      subject,
      '',
      ...pinLines.flatMap((l) => [l, '']),
      ...plans
        .flatMap((p) =>
          p.changes.filter((ch) =>
            c.repo === '.' ? !ch.startsWith('private/') : ch.startsWith(`${c.repo}/`)
          )
        )
        .map((ch) => `Site: ${ch}`),
      '',
      ...res.commands.map((cm) => `Ran: ${cmdLine(cm)}`),
      ...(c.repo === '.' && subs.length > 0
        ? ['', `Pointer: ${subs.join(', ')} moves to the pins commit drafted beside this one.`]
        : []),
      ...(task ? ['', `PR-TASK: ${task}`] : []),
    ]
      .join('\n')
      .replace(/\n{3,}/g, '\n\n');
    const draft = path.join(res.dir, `${slug(c.repo)}.msg`);
    fs.writeFileSync(draft, `${body.trim()}\n`);
    const g = c.repo === '.' ? 'git' : `git -C ${c.repo}`;
    const lines = [
      ...(c.added.length ? [`${g} add -- ${c.added.join(' ')}`] : []),
      `${g} commit -F ${draft} -- ${paths.join(' ')}`,
    ];
    return { ...c, paths, draft, lines };
  });
}

function writeOut(w: World, outDir: string, report: unknown, drafts: RepoDraft[]): void {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  for (const d of drafts) {
    fs.copyFileSync(d.draft, path.join(outDir, path.basename(d.draft)));
    const repoAbs = path.join(w.root, d.repo);
    const tracked = d.paths.filter((p) => !d.added.includes(p));
    let patch = '';
    if (tracked.length)
      patch +=
        spawnSync('git', ['-C', repoAbs, 'diff', '--binary', '--', ...tracked], {
          encoding: 'utf8',
        }).stdout ?? '';
    for (const a of d.added)
      patch +=
        spawnSync('git', ['-C', repoAbs, 'diff', '--no-index', '--binary', '--', '/dev/null', a], {
          encoding: 'utf8',
        }).stdout ?? '';
    fs.writeFileSync(path.join(outDir, `${slug(d.repo)}.patch`), patch);
  }
}

// ---- verbs ----------------------------------------------------------------------------------

interface Flags {
  json: boolean;
  all: boolean;
  to?: string;
  major: boolean;
  reason?: string;
  expires?: string;
  task: string | null;
  out?: string;
  restore?: string;
  /** Files a killed step had in flight that `verify --restore` may give their before-bytes back, once the operator has inspected them. */
  inflight: string[];
  pos: string[];
}

function parseFlags(argv: string[]): Flags {
  const f: Flags = { json: false, all: false, major: false, task: null, inflight: [], pos: [] };
  const val = (i: number, name: string): string => {
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) throw new Usage(`${name} needs a value`);
    return v;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') f.json = true;
    else if (a === '--all') f.all = true;
    else if (a === '--major') f.major = true;
    else if (a === '--to') f.to = val(i++, a);
    else if (a === '--reason') f.reason = val(i++, a);
    else if (a === '--expires') f.expires = val(i++, a);
    else if (a === '--task') f.task = val(i++, a);
    else if (a === '--out') f.out = val(i++, a);
    else if (a === '--restore') f.restore = val(i++, a);
    else if (a === '--inflight') f.inflight.push(val(i++, a));
    else if (a.startsWith('--')) throw new Usage(`unknown flag ${a}`);
    else f.pos.push(a);
  }
  return f;
}

const newStamp = (): string =>
  `${new Date()
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d{3}Z$/, 'Z')}-${crypto.randomBytes(3).toString('hex')}`;

async function cmdStatus(w: World, f: Flags): Promise<number> {
  const ctx = contextOf(w);
  const entries = pick(w, f.pos[0], f.pos[0] === undefined);
  const views = await Promise.all(entries.map((e) => viewOf(w, ctx, e)));
  if (f.json) w.out.push(JSON.stringify({ now: iso(w.nowMs), pins: views }, null, 2));
  else
    for (const v of views)
      w.out.push(
        `${v.id.padEnd(28)} ${(v.current ?? '-').padEnd(16)} ${v.state.padEnd(12)} ${v.detail}`
      );
  const blind = views.filter((v) => v.state === 'not-compared');
  if (!f.json && blind.length)
    w.err.push(
      `${blind.length} pin(s) not compared; a pin nobody compared is a finding, not a pass.`
    );
  return blind.length ? 1 : 0;
}

async function cmdWhen(w: World, f: Flags): Promise<number> {
  const [entry] = pick(w, f.pos[0], false);
  const v = await viewOf(w, contextOf(w), entry, { allowMajor: true });
  const d = v.deferred;
  if (!d || d.publishedMs === null || d.clearsAt === null) {
    const msg = `${entry.id}: no release is waiting on the window (${v.state}: ${v.detail})`;
    if (f.json)
      w.out.push(
        JSON.stringify({ id: entry.id, state: v.state, clearsAt: null, detail: v.detail })
      );
    else w.out.push(msg);
    return v.state === 'not-compared' ? 1 : 0;
  }
  const at = iso(d.clearsAt);
  const def = `DEFAULT: on or after ${at} run \`npm run pins -- bump ${entry.id}\` (${d.version}, published ${iso(d.publishedMs)})`;
  if (f.json)
    w.out.push(
      JSON.stringify({
        id: entry.id,
        version: d.version,
        published: iso(d.publishedMs),
        clearsAt: at,
        default: def,
      })
    );
  else w.out.push(`${entry.id} ${d.version} clears the release-age window at ${at}`, def);
  return 0;
}

interface Selected {
  plans: PinPlan[];
  views: Map<string, PinView>;
  refused: Array<{ id: string; why: string }>;
  skipped: Array<{ id: string; why: string }>;
}

/** Inspect and plan every selected pin over one overlay, so two pins sharing a file compose. */
async function selectAndPlan(
  w: World,
  entries: PinEntry[],
  sel: SelectOpts,
  explicit: boolean
): Promise<Selected> {
  const ctx = contextOf(w);
  const out: Selected = { plans: [], views: new Map(), refused: [], skipped: [] };
  for (const entry of entries) {
    const v = await viewOf(w, ctx, entry, sel);
    out.views.set(entry.id, v);
    if (v.state !== 'bumpable' || !v.target) {
      const why = v.state === 'not-compared' ? v.detail : `${v.state}: ${v.detail}`;
      if (explicit || v.state === 'not-compared') out.refused.push({ id: entry.id, why });
      else out.skipped.push({ id: entry.id, why });
      continue;
    }
    const drv = driverFor(entry, ctx);
    try {
      const plan = await (drv as NonNullable<typeof drv>).plan(entry, v.target, ctx);
      for (const wr of plan.writes) ctx.overlay.set(keyOf(wr), wr.after);
      out.plans.push(plan);
    } catch (err) {
      if (!(err instanceof PlanRefused)) throw err;
      out.refused.push({ id: entry.id, why: err.message });
    }
  }
  return out;
}

async function cmdPlan(w: World, f: Flags): Promise<number> {
  const entries = pick(w, f.pos[0], f.all);
  const s = await selectAndPlan(w, entries, { to: f.to, allowMajor: f.major }, !f.all);
  if (f.json)
    w.out.push(
      JSON.stringify(
        {
          plans: s.plans.map((p) => ({
            id: p.entry.id,
            from: p.from,
            to: p.to.version,
            changes: p.changes,
            steps: p.steps.map((x) => x.run),
            derive: p.entry.derive.map((d) => d.run),
            gates: p.entry.gates,
          })),
          refused: s.refused,
          skipped: s.skipped,
        },
        null,
        2
      )
    );
  else {
    for (const p of s.plans) {
      w.out.push(`${p.entry.id}: ${p.from} -> ${p.to.version}`);
      for (const c of p.changes) w.out.push(`  ${c}`);
      for (const st of [...p.steps.map((x) => x.run), ...p.entry.derive.map((d) => d.run)])
        w.out.push(`  then: ${st}`);
      if (p.entry.gates.length)
        w.out.push(`  gates: npm run ci -- --only ${p.entry.gates.join(',')}`);
    }
    for (const r of s.refused) w.err.push(`REFUSED ${r.id}: ${r.why}`);
  }
  return s.refused.length ? 1 : 0;
}

function report(
  w: World,
  f: Flags,
  s: Selected,
  res: TxnResult | null,
  drafts: RepoDraft[]
): object {
  return {
    ok: res?.ok ?? false,
    now: iso(w.nowMs),
    stamp: res?.stamp ?? null,
    journal: res?.dir ?? null,
    pins: s.plans.map((p) => ({
      id: p.entry.id,
      from: p.from,
      to: p.to.version,
      published: p.to.publishedMs === null ? null : iso(p.to.publishedMs),
      changes: p.changes,
    })),
    refused: s.refused,
    skipped: s.skipped,
    failure: res?.failure ?? null,
    commands: res?.commands ?? [],
    gates: res?.gates ?? null,
    restored: res?.restored ?? [],
    leftAlone: res?.leftAlone ?? [],
    repos: drafts.map((d) => ({
      repo: d.repo,
      paths: d.paths,
      added: d.added,
      draft: d.draft,
      commands: d.lines,
    })),
    task: f.task,
  };
}

/** Run a set of plans as one transaction and print its outcome. */
function apply(w: World, f: Flags, s: Selected, subject: string): number {
  if (s.plans.length === 0) {
    if (f.json) w.out.push(JSON.stringify(report(w, f, s, null, []), null, 2));
    else {
      for (const r of s.refused) w.err.push(`REFUSED ${r.id}: ${r.why}`);
      w.out.push(s.refused.length ? 'nothing written.' : 'nothing to bump.');
    }
    return s.refused.length ? 1 : 0;
  }
  const release = takeLock(w.root);
  if (!release) throw new Usage('another pins run holds .ci/cache/pins/.lock');
  let res: TxnResult;
  try {
    res = runTransaction(s.plans, {
      root: w.root,
      stamp: newStamp(),
      runner: w.runner,
      mutant: w.mutant,
      npmVersion: w.npmVersion,
      submodules: w.reg.submodules.scanned,
    });
  } finally {
    release();
  }
  const drafts = res.ok ? writeDrafts(w, res, s.plans, s.views, f.task, subject) : [];
  const rep = report(w, f, s, res, drafts);
  if (f.out) writeOut(w, path.resolve(f.out), rep, drafts);
  if (f.json) {
    w.out.push(JSON.stringify(rep, null, 2));
    return res.ok && s.refused.length === 0 ? 0 : 1;
  }
  for (const r of s.refused) w.err.push(`REFUSED ${r.id}: ${r.why}`);
  if (!res.ok) {
    w.err.push(`FAILED: ${res.failure}`);
    if (res.restored.length) w.err.push(`restored: ${res.restored.join(', ')}`);
    if (res.leftAlone.length)
      w.err.push(
        `left alone (changed after this run wrote them, so not this run's to restore): ${res.leftAlone.join(', ')}`
      );
    w.err.push(`journal: ${res.dir}`);
    return 1;
  }
  for (const p of s.plans) w.out.push(`${p.entry.id}: ${p.from} -> ${p.to.version}`);
  if (res.gates)
    w.out.push(`gates: npm run ci -- --only ${res.gates.ids.join(',')} rc=${res.gates.rc}`);
  if (!f.task) w.out.push('note: no --task given, so the drafts carry no PR-TASK trailer');
  for (const d of drafts) {
    w.out.push(`${d.repo === '.' ? 'console' : d.repo}:`);
    for (const l of d.lines) w.out.push(`  ${l}`);
  }
  return s.refused.length ? 1 : 0;
}

function subjectOf(plans: PinPlan[], verb: string): string {
  if (plans.length === 1)
    return `chore(pins): ${verb} ${plans[0].entry.name} ${plans[0].from} to ${plans[0].to.version}`;
  const names = plans.map((p) => p.entry.name);
  return `chore(pins): ${verb} ${plans.length} pins (${names.slice(0, 4).join(', ')}${names.length > 4 ? ', ...' : ''})`;
}

async function cmdBump(w: World, f: Flags, soakedOnly: boolean): Promise<number> {
  if (f.major && (!f.reason || f.reason.trim().length < 10))
    throw new Usage('--major needs --reason "<why the major is safe now>"');
  const all = soakedOnly || f.all;
  if (all && f.to) throw new Usage('--to names one pin; it does not combine with --all');
  const entries = pick(w, f.pos[0], all);
  if (f.major)
    for (const e of entries)
      if (e.safety.major === 'refuse')
        throw new Usage(`${e.id} refuses majors (safety.major: refuse)`);
  const s = await selectAndPlan(
    w,
    entries,
    { to: f.to, allowMajor: f.major, onlyInRange: soakedOnly },
    !all
  );
  const subject = subjectOf(s.plans, 'bump');
  return apply(w, f, s, f.major && f.reason ? `${subject} (major: ${f.reason})` : subject);
}

async function cmdHold(w: World, f: Flags): Promise<number> {
  const [entry] = pick(w, f.pos[0], false);
  if (!f.reason) throw new Usage('hold needs --reason "<why>"');
  if (
    f.expires &&
    (!/^\d{4}-\d\d-\d\d$/.test(f.expires) || Date.parse(`${f.expires}T00:00:00Z`) <= w.nowMs)
  )
    throw new Usage(`--expires must be a future YYYY-MM-DD, got ${f.expires}`);
  const ctx = contextOf(w);
  const drv = driverFor(entry, ctx);
  const key = drv?.holdKey(entry) ?? null;
  const file = entry.holds[0];
  if (!drv || key === null || !file) {
    w.err.push(
      `REFUSED ${entry.id}: ${!drv ? `the ${entry.driver} driver has not landed` : 'this entry has no hold file'}`
    );
    return 1;
  }
  const bad = validateBlockerQuality(key, f.reason, file);
  if (bad) {
    w.err.push(bad.message);
    return 1;
  }
  const existing = holdOf(w, entry, key);
  if (existing && !existing.expired) {
    w.err.push(`REFUSED ${entry.id}: already held in ${file}: ${existing.reason}`);
    return 1;
  }
  const text = ctx.read({ repo: '.', file }) ?? '';
  const line = `${key}  # BLOCKER: ${f.reason}${f.expires ? ` (expires ${f.expires})` : ''}`;
  const after = `${text}${text === '' || text.endsWith('\n\n') ? '' : text.endsWith('\n') ? '\n' : '\n\n'}${line}\n`;
  const write: FileWrite = { repo: '.', file, after };
  const cur = leafCurrent(entry, ctx) ?? 'its current pin';
  const plan: PinPlan = {
    entry,
    from: cur,
    to: { version: cur, publishedMs: null },
    writes: [write],
    steps: [],
    changes: [`${file}: hold ${key}`],
  };
  const s: Selected = {
    plans: [{ ...plan, entry: { ...entry, derive: [] } }],
    views: new Map(),
    refused: [],
    skipped: [],
  };
  return apply(w, f, s, `chore(pins): hold ${entry.name} at ${cur}`);
}

function cmdVerify(w: World, f: Flags): number {
  if (f.restore) {
    let r: ReturnType<typeof restoreJournal>;
    try {
      r = restoreJournal(w.root, f.restore, new Set(f.inflight));
    } catch (err) {
      if (!(err instanceof RestoreRefused)) throw err;
      w.err.push(`REFUSED: ${err.message}`);
      return 1;
    }
    w.out.push(`restored: ${r.restored.join(', ') || '(none)'}`);
    if (r.leftAlone.length)
      w.out.push(`left alone (changed since the run wrote them): ${r.leftAlone.join(', ')}`);
    if (r.inflight.length) {
      w.err.push(
        `in flight when the run was killed, and changed since (a partial write or a later edit, which the journal cannot tell apart), so kept: ${r.inflight.join(', ')}; inspect each, then \`npm run pins -- verify --restore ${f.restore} --inflight <file>\` gives its before-bytes back`
      );
      return 1;
    }
    return 0;
  }
  const findings: string[] = [];
  const ctx = contextOf(w);
  for (const e of w.reg.entries) {
    const roles = new Map<string, Set<string>>();
    for (const [i, s] of e.sites.entries()) {
      const text = ctx.read(s);
      const ms = text === null ? [] : siteMatches(s, text);
      if (ms.length !== s.expect)
        findings.push(
          `${e.id} site ${i} (${keyOf(s)}): matches ${ms.length} time(s), expects ${s.expect}`
        );
      for (const m of ms) roles.set(s.role, (roles.get(s.role) ?? new Set()).add(m.value));
    }
    for (const [role, vals] of roles)
      if (vals.size > 1)
        findings.push(`${e.id}: the ${role} sites disagree (${[...vals].join(' vs ')})`);
  }
  for (const j of openJournals(w.root))
    findings.push(
      `journal ${j.stamp} was killed mid-write (${j.files.join(', ')}); \`npm run pins -- verify --restore ${j.stamp}\``
    );
  if (f.json) w.out.push(JSON.stringify({ ok: findings.length === 0, findings }, null, 2));
  else if (findings.length) for (const x of findings) w.err.push(`FINDING ${x}`);
  else
    w.out.push(`${w.reg.entries.length} pins: every site matches its count and every role agrees`);
  return findings.length ? 1 : 0;
}

/** The CLI, with its environment and output passed in so the selftest drives it in-process. */
export async function runCli(
  argv: string[],
  env: NodeJS.ProcessEnv
): Promise<{ rc: number; out: string; err: string }> {
  let w: World | null = null;
  try {
    w = makeWorld(env);
    const f = parseFlags(argv.slice(1));
    const verb = argv[0];
    let rc: number;
    if (verb === 'status') rc = await cmdStatus(w, f);
    else if (verb === 'when') rc = await cmdWhen(w, f);
    else if (verb === 'plan') rc = await cmdPlan(w, f);
    else if (verb === 'bump') rc = await cmdBump(w, f, false);
    else if (verb === 'apply-soaked') rc = await cmdBump(w, f, true);
    else if (verb === 'hold') rc = await cmdHold(w, f);
    else if (verb === 'verify') rc = cmdVerify(w, f);
    else if (verb === 'remove' || verb === 'lockfiles')
      throw new Usage(
        `\`${verb}\` lands with the npm driver (agent/plans/PLAN-pins-command.md ${verb === 'remove' ? 'T6' : 'T4'})`
      );
    else
      throw new Usage(
        `unknown verb ${verb ?? '(none)'}; verbs: status, when, plan, bump, apply-soaked, hold, verify`
      );
    return { rc, out: w.out.join('\n'), err: w.err.join('\n') };
  } catch (err) {
    const msg =
      err instanceof Usage
        ? `pins: ${err.message}`
        : `pins: ${(err as Error).stack ?? String(err)}`;
    return {
      rc: err instanceof Usage ? 2 : 1,
      out: w?.out.join('\n') ?? '',
      err: [...(w?.err ?? []), msg].join('\n'),
    };
  }
}

// ---- selftest -------------------------------------------------------------------------------

const PUB_NEW = '2026-10-14T10:00:00Z';
const SHA = (c: string): string => c.repeat(64);

interface Fx {
  root: string;
  fixture: Fixture;
  env: (extra?: NodeJS.ProcessEnv) => NodeJS.ProcessEnv;
  read: (rel: string) => string;
  write: (rel: string, text: string) => void;
}

function sh(cwd: string, ...args: string[]): void {
  const r = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')} failed in ${cwd}: ${r.stderr}`);
}

/** Every fixture tree the selftest made, removed when it ends. */
const FIXTURE_ROOTS: string[] = [];

/** A fixture console with a nested private/renet repo, both committed; `tune` edits the fixture JSON. */
/** Two takers judge the same dead-pid lock stale; the second one wins the window and holds a fresh lock before the first clears. The first must then stand down and leave the fresh lock in place, not remove it and take the lock too. */
function lockRaceCase(root: string): { name: string; ok: boolean; detail: string } {
  const lock = path.join(root, '.ci/cache/pins/.lock');
  fs.mkdirSync(path.dirname(lock), { recursive: true });
  fs.rmSync(lock, { force: true });
  fs.writeFileSync(lock, '999999999\n');
  const fresh = `${process.ppid}\n`;
  const release = takeLock(root, () => {
    fs.rmSync(lock, { force: true });
    fs.writeFileSync(lock, fresh);
  });
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  if (release) release();
  fs.rmSync(lock, { force: true });
  return {
    name: 'lock: a taker that loses the stale-lock race stands down and leaves the winner its fresh lock',
    ok: release === null && held === fresh,
    detail: `took=${release !== null} lock=${JSON.stringify(held)}`,
  };
}

function fixtureTree(tune: (fx: Fixture) => void = () => {}): Fx {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-selftest-'));
  FIXTURE_ROOTS.push(root);
  const files: Record<string, string> = {
    'package.json': '{ "name": "pins-fixture", "private": true }\n',
    '.gitignore': 'private/\n.ci/cache/\nfixture.json\n',
    '.ci/config/release-age.json': '{ "minimum_release_age_minutes": 1440 }\n',
    '.devcontainer/toolchain.env': 'NPM_VERSION=11.20.0\n',
    '.ci/policy/.fixture-blocklist': '# Fixture blocklist. Format: name  # BLOCKER: <reason>\n',
    Dockerfile: `FROM scratch\nARG TOOL_VERSION=1.0.0\nARG TOOL_SHA256=${SHA('a')}\n`,
    'tool.lock.json': `${JSON.stringify({ tool: { version: '1.0.0' } }, null, 2)}\n`,
    'docs/tool.md': 'The embedded tool is pinned.\n\ntool v1.0.0\n',
    'credits.json': '{}\n',
    'package-lock.json': '{ "lockfileVersion": 3 }\n',
    'private/renet/Dockerfile': 'FROM scratch\nARG ZED_VERSION=2.0.0\n',
  };
  const site = (file: string, role: string, loc: Record<string, string>, repo = '.') => ({
    repo,
    file,
    role,
    expect: 1,
    ...loc,
  });
  const leaf = (id: string, sites: object[], extra: object = {}) => ({
    id,
    kind: 'leaf',
    name: id.split(':')[1],
    driver: 'embed',
    source: { type: 'github-release', repo: 'fixture/fixture' },
    safety: { mode: 'release-age', major: 'assisted' },
    holds: ['.ci/policy/.fixture-blocklist'],
    gates: [`check:fixture-${id.split(':')[1]}`],
    sites,
    derive: [],
    literals: [],
    ...extra,
  });
  const reg = {
    version: 1,
    submodules: { scanned: ['private/renet'], unscanned: [] },
    literalExclude: [],
    entries: [
      leaf('embed:tool', [
        site('Dockerfile', 'version', { arg: 'TOOL_VERSION' }),
        site('tool.lock.json', 'version', { json: '/tool/version' }),
        site('docs/tool.md', 'version', { match: '^tool v(?<value>\\S+)$' }),
        site('Dockerfile', 'sha256:amd64', { arg: 'TOOL_SHA256' }),
      ]),
      leaf('embed:zed', [site('Dockerfile', 'version', { arg: 'ZED_VERSION' }, 'private/renet')], {
        derive: [{ run: 'gen-credits', cwd: '.', writes: [{ repo: '.', file: 'credits.json' }] }],
      }),
    ],
    ignores: [],
  };
  files['.ci/config/pins.json'] = `${JSON.stringify(reg, null, 2)}\n`;
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  for (const repo of [path.join(root, 'private/renet'), root]) {
    sh(repo, 'init', '-q');
    sh(repo, 'add', '-A');
    sh(
      repo,
      '-c',
      'user.email=fx@example.invalid',
      '-c',
      'user.name=fx',
      'commit',
      '-q',
      '-m',
      'fixture'
    );
  }
  const fixture: Fixture = {
    now: '2026-10-14T12:00:00Z',
    releases: {
      'embed:tool': [
        { version: '1.2.0', published: PUB_NEW, values: { 'sha256:amd64': SHA('c') } },
        {
          version: '1.1.0',
          published: '2026-10-01T00:00:00Z',
          values: { 'sha256:amd64': SHA('b') },
        },
        { version: '1.0.0', published: '2026-09-01T00:00:00Z' },
      ],
      'embed:zed': [
        { version: '2.1.0', published: '2026-10-01T00:00:00Z' },
        { version: '2.0.0', published: '2026-09-01T00:00:00Z' },
      ],
    },
    commands: [
      { match: '^npm run ci -- --only ', rc: 0 },
      { match: '^gen-credits$', rc: 0, writes: { 'credits.json': '{ "zed": "2.1.0" }\n' } },
      { match: '^npx -y npm@11\\.20\\.0 install --package-lock-only --ignore-scripts$', rc: 0 },
      { match: '^npx -y npm@11\\.20\\.0 (ci|run install:natives)$', rc: 0 },
    ],
  };
  tune(fixture);
  const fxFile = path.join(root, 'fixture.json');
  fs.writeFileSync(fxFile, JSON.stringify(fixture));
  return {
    root,
    fixture,
    env: (extra = {}) => ({ PINS_ROOT: root, PINS_FIXTURE: fxFile, ...extra }),
    read: (rel) => fs.readFileSync(path.join(root, rel), 'utf8'),
    write: (rel, text) => fs.writeFileSync(path.join(root, rel), text),
  };
}

type Case = (mutant: Mutant | undefined) => Promise<ControlCase[]>;

const withMutant = (fx: Fx, m: Mutant | undefined): NodeJS.ProcessEnv =>
  fx.env(m ? { PINS_MUTANT: m } : {});
const snap = (fx: Fx, rels: string[]): string[] => rels.map((r) => fx.read(r));
const same = (a: string[], b: string[]): boolean => a.every((x, i) => x === b[i]);
const TOOL_FILES = ['Dockerfile', 'tool.lock.json', 'docs/tool.md'];

/** One plan over the fixture's embed:tool entry with only the given steps, for driving the transaction directly. */
function directPlans(fx: Fx, steps: PinPlan['steps']): PinPlan[] {
  const reg = loadRegistry(path.join(fx.root, '.ci/config/pins.json'));
  const entry = reg.entries.find((e) => e.id === 'embed:tool');
  if (!entry) throw new Error('fixture registry lost embed:tool');
  return [
    {
      entry: { ...entry, derive: [], gates: [] },
      from: '1.0.0',
      to: { version: '1.1.0', publishedMs: null },
      writes: [
        {
          repo: '.',
          file: 'Dockerfile',
          after: fx.read('Dockerfile').replace('TOOL_VERSION=1.0.0', 'TOOL_VERSION=1.1.0'),
        },
      ],
      steps,
      changes: [],
    },
  ];
}

const directTxn = (fx: Fx, stamp: string, runner: Runner, m: Mutant | undefined) => ({
  root: fx.root,
  stamp,
  runner,
  mutant: m ?? null,
  npmVersion: '11.20.0',
  submodules: ['private/renet'],
});

const CASES: Record<string, Case> = {
  async soak(m) {
    const fx = fixtureTree();
    const r = await runCli(['status', 'embed:tool', '--json'], withMutant(fx, m));
    const v = (JSON.parse(r.out) as { pins: PinView[] }).pins[0];
    return [
      {
        name: 'status: the newest eligible release is the target; one inside the window is deferred',
        ok: r.rc === 0 && v.state === 'bumpable' && v.target?.version === '1.1.0',
        detail: `rc=${r.rc} ${r.err} ${JSON.stringify(v)}`,
      },
    ];
  },
  async when(m) {
    const fx = fixtureTree();
    const r = await runCli(['when', 'embed:tool'], withMutant(fx, m));
    const pub = Date.parse(PUB_NEW);
    const at = Date.parse('2026-10-16T00:00:00Z');
    const rule =
      isWithinFreshnessWindow(pub, at - 1, 86_400_000) &&
      !isWithinFreshnessWindow(pub, at, 86_400_000);
    return [
      {
        name: `when: a release published ${PUB_NEW} clears at 2026-10-16T00:00:00Z, the instant isWithinFreshnessWindow turns false`,
        ok:
          r.rc === 0 &&
          rule &&
          r.out.includes('clears the release-age window at 2026-10-16T00:00:00Z'),
        detail: `rc=${r.rc} rule=${rule} ${r.out} ${r.err}`,
      },
      {
        name: 'when: prints a ready worklist DEFAULT line naming the bump',
        ok: /DEFAULT: on or after 2026-10-16T00:00:00Z run `npm run pins -- bump embed:tool`/.test(
          r.out
        ),
        detail: r.out,
      },
    ];
  },
  async bump(m) {
    const fx = fixtureTree();
    const r = await runCli(
      ['bump', 'embed:tool', '--task', 'cafe1234', '--json'],
      withMutant(fx, m)
    );
    const rep =
      r.rc === 0
        ? (JSON.parse(r.out) as { repos: Array<{ draft: string }>; commands: CommandRecord[] })
        : null;
    const draft = rep?.repos[0] ? fs.readFileSync(rep.repos[0].draft, 'utf8') : '';
    const cmds = (rep?.commands ?? []).map((c) => c.cmd);
    return [
      {
        name: 'bump: every site of the pin is rewritten to the eligible release (version x3, sha256)',
        ok:
          r.rc === 0 &&
          fx.read('Dockerfile').includes('ARG TOOL_VERSION=1.1.0') &&
          fx.read('Dockerfile').includes(`ARG TOOL_SHA256=${SHA('b')}`) &&
          fx.read('tool.lock.json').includes('"version": "1.1.0"') &&
          fx.read('docs/tool.md').includes('tool v1.1.0'),
        detail: `rc=${r.rc} ${r.err}\n${fx.read('Dockerfile')}`,
      },
      {
        name: 'bump: the gates run once as `npm run ci -- --only <ids>`',
        ok: cmds.includes('npm run ci -- --only check:fixture-tool'),
        detail: cmds.join(' | '),
      },
      {
        name: 'bump: the draft names versions, publish time, soak clearance, gate rc and PR-TASK',
        ok:
          /^chore\(pins\): bump tool 1\.0\.0 to 1\.1\.0$/m.test(draft) &&
          draft.includes('published 2026-10-01T00:00:00Z, soak cleared 2026-10-03T00:00:00Z') &&
          draft.includes('npm run ci -- --only check:fixture-tool (in .) rc=0') &&
          /\nPR-TASK: cafe1234\n$/.test(draft),
        detail: draft,
      },
    ];
  },
  async mismatch(m) {
    const fx = fixtureTree();
    fx.write('docs/tool.md', 'tool v1.0.0\n\ntool v1.0.0\n');
    sh(
      fx.root,
      '-c',
      'user.email=fx@example.invalid',
      '-c',
      'user.name=fx',
      'commit',
      '-qam',
      'dup'
    );
    const before = snap(fx, TOOL_FILES);
    const r = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'bump: a third site matching twice refuses the pin and leaves all three files byte-identical',
        ok:
          r.rc === 1 &&
          r.err.includes('docs/tool.md') &&
          r.err.includes('expects 1') &&
          same(before, snap(fx, TOOL_FILES)),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async dirty(m) {
    const fx = fixtureTree();
    fx.write('Dockerfile', `${fx.read('Dockerfile')}# a peer session's note\n`);
    const before = snap(fx, TOOL_FILES);
    const r = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: "bump: a site file holding a peer session's changes is refused by name, nothing written",
        ok:
          r.rc === 1 &&
          /refused: Dockerfile already hold/.test(r.err) &&
          same(before, snap(fx, TOOL_FILES)),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async restore(m) {
    const fx = fixtureTree((f) => (f.commands[0].rc = 1));
    const before = snap(fx, TOOL_FILES);
    const r = await runCli(['bump', 'embed:tool', '--json'], withMutant(fx, m));
    const rep = JSON.parse(r.out) as { restored: string[]; journal: string };
    const j = JSON.parse(fs.readFileSync(path.join(rep.journal, 'journal.json'), 'utf8')) as {
      state: string;
    };
    return [
      {
        name: 'bump: a red gate restores every written file from the journal, byte-identical',
        ok:
          r.rc === 1 &&
          same(before, snap(fx, TOOL_FILES)) &&
          rep.restored.length === 3 &&
          j.state === 'restored',
        detail: `rc=${r.rc} restored=${rep.restored} state=${j.state}`,
      },
    ];
  },
  async compare(m) {
    const peer = 'tool v1.1.0\n\npeer edit made while the gates ran\n';
    const fx = fixtureTree((f) => {
      f.commands[0] = { match: '^npm run ci -- --only ', rc: 1, writes: { 'docs/tool.md': peer } };
    });
    const before = snap(fx, ['Dockerfile', 'tool.lock.json']);
    const r = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'bump: compare-and-restore leaves a file changed after the run wrote it, and names it',
        ok:
          r.rc === 1 &&
          fx.read('docs/tool.md') === peer &&
          /left alone .*docs\/tool\.md/.test(r.err) &&
          same(before, snap(fx, ['Dockerfile', 'tool.lock.json'])),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async canonical(m) {
    const fx = fixtureTree((f) => {
      f.steps = {
        'embed:tool': [
          {
            label: 'relock',
            run: 'relock',
            cwd: '.',
            writes: [{ repo: '.', file: 'package-lock.json' }],
          },
        ],
      };
      f.commands.push({
        match: '^relock$',
        rc: 0,
        writes: { 'package-lock.json': '{ "lockfileVersion": 3, "x": 1 }\n' },
      });
    });
    const r = await runCli(['bump', 'embed:tool', '--json'], withMutant(fx, m));
    const cmds =
      r.rc === 0
        ? (JSON.parse(r.out) as { commands: CommandRecord[] }).commands.map((c) => c.cmd)
        : [];
    const i = cmds.indexOf('npx -y npm@11.20.0 install --package-lock-only --ignore-scripts');
    return [
      {
        name: 'bump: a touched lockfile gets the canonical pass under the pinned npm, then npm ci and install:natives',
        ok:
          i > 0 &&
          cmds[i + 1] === 'npx -y npm@11.20.0 ci' &&
          cmds[i + 2] === 'npx -y npm@11.20.0 run install:natives' &&
          cmds.at(-1)?.startsWith('npm run ci -- --only') === true,
        detail: `rc=${r.rc} ${r.err} ${cmds.join(' | ')}`,
      },
    ];
  },
  async undeclared(m) {
    const fx = fixtureTree((f) => {
      f.steps = { 'embed:tool': [{ label: 'sneaky', run: 'sneaky', cwd: '.', writes: [] }] };
      f.commands.push({ match: '^sneaky$', rc: 0, writes: { 'stray.txt': 'x\n' } });
    });
    const r = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'bump: a step that changes a file it did not declare fails the run; the file is named and left, the sites restored',
        ok:
          r.rc === 1 &&
          r.err.includes('did not declare: stray.txt') &&
          /left alone .*stray\.txt/.test(r.err) &&
          fs.existsSync(path.join(fx.root, 'stray.txt')) &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.0.0'),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async undeclaredOverPlanned(m) {
    // A step that rewrites a file the plan itself already wrote (dirty before and after the
    // step) is still caught, by its bytes; the rewritten file no longer holds the bytes the run
    // wrote, so compare-and-restore names it and leaves it, and restores the other sites.
    const sneaky = 'ARG TOOL_VERSION=6.6.6\n';
    const fx = fixtureTree((f) => {
      f.steps = { 'embed:tool': [{ label: 'sneaky', run: 'sneaky', cwd: '.', writes: [] }] };
      f.commands.push({ match: '^sneaky$', rc: 0, writes: { Dockerfile: sneaky } });
    });
    const before = snap(fx, ['tool.lock.json', 'docs/tool.md']);
    const r = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'bump: a step that rewrites a file the plan already wrote, without declaring it, fails the run and names it; that file is left as the step wrote it, the other sites restored',
        ok:
          r.rc === 1 &&
          r.err.includes('did not declare: Dockerfile') &&
          /left alone .*Dockerfile/.test(r.err) &&
          fx.read('Dockerfile') === sneaky &&
          same(before, snap(fx, ['tool.lock.json', 'docs/tool.md'])),
        detail: `rc=${r.rc} ${r.err}\n${fx.read('Dockerfile')}`,
      },
    ];
  },
  async deletedByStep(m) {
    // A step that deletes a file the plan wrote hashes it as absent rather than throwing: the
    // undeclared deletion fails the run by name, and a declared one is counted as the step's.
    const fx = fixtureTree();
    const del: Runner = (cmd, cwd) => {
      if (cmd === 'rm-dockerfile') fs.rmSync(path.join(cwd, 'Dockerfile'));
      return { rc: 0, out: '' };
    };
    const step = (declared: boolean): PinPlan[] =>
      directPlans(fx, [
        {
          label: 'rm',
          run: 'rm-dockerfile',
          cwd: '.',
          writes: declared ? [{ repo: '.', file: 'Dockerfile' }] : [],
        },
      ]);
    const bad = runTransaction(step(false), directTxn(fx, 'del-undeclared', del, m));
    const undeclaredGone = !fs.existsSync(path.join(fx.root, 'Dockerfile'));
    sh(fx.root, 'checkout', '-q', '--', '.');
    const good = runTransaction(step(true), directTxn(fx, 'del-declared', del, m));
    return [
      {
        name: 'txn: a step that deletes a planned file without declaring it fails by name, and the deletion is left',
        ok:
          !bad.ok &&
          (bad.failure ?? '').includes('did not declare: Dockerfile') &&
          bad.leftAlone.includes('Dockerfile') &&
          undeclaredGone,
        detail: `${bad.failure} left=${bad.leftAlone}`,
      },
      {
        name: 'txn: a step that deletes a file it declares finishes, with the deletion as its change',
        ok: good.ok && good.changes.some((c) => c.paths.includes('Dockerfile')),
        detail: `${good.failure} ${JSON.stringify(good.changes)}`,
      },
    ];
  },
  async killedInStep(m) {
    // A run killed while a step runs: the journal on disk at that instant already claims the step's declared files. Their bytes after the kill could be the step's partial write or a later edit, and the journal cannot tell which, so `verify --restore` names them and keeps them; `--inflight <file>` gives one its before-bytes back once inspected.
    const fx = fixtureTree();
    const jroot = path.join(fx.root, '.ci/cache/pins');
    const kill: Runner = (cmd, cwd) => {
      fs.writeFileSync(path.join(cwd, 'credits.json'), '{ "half": true\n');
      fs.mkdirSync(path.join(jroot, 'killed'), { recursive: true });
      fs.copyFileSync(
        path.join(jroot, 'live', 'journal.json'),
        path.join(jroot, 'killed', 'journal.json')
      );
      return { rc: cmd === 'gen' ? 0 : 1, out: '' };
    };
    runTransaction(
      directPlans(fx, [
        { label: 'gen', run: 'gen', cwd: '.', writes: [{ repo: '.', file: 'credits.json' }] },
      ]),
      directTxn(fx, 'live', kill, m)
    );
    fx.write('credits.json', '{ "edited": "by hand after the kill" }\n');
    const named = await runCli(['verify'], withMutant(fx, m));
    const kept = await runCli(['verify', '--restore', 'killed'], withMutant(fx, m));
    const keptBytes = fx.read('credits.json');
    const taken = await runCli(
      ['verify', '--restore', 'killed', '--inflight', 'credits.json'],
      withMutant(fx, m)
    );
    return [
      {
        name: 'verify --restore: a file a killed step had in flight and that changed since is named and kept, never overwritten',
        ok:
          named.err.includes('journal killed') &&
          kept.rc === 1 &&
          kept.err.includes('in flight when the run was killed') &&
          kept.err.includes('credits.json') &&
          keptBytes === '{ "edited": "by hand after the kill" }\n',
        detail: `rc=${kept.rc} ${kept.out} ${kept.err} | ${keptBytes}`,
      },
      {
        name: 'verify --restore --inflight: the named in-flight file gets its before-bytes back, and the journal closes',
        ok:
          taken.rc === 0 &&
          /^restored: .*\bcredits\.json\b/m.test(taken.out) &&
          fx.read('credits.json') === '{}\n' &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.0.0'),
        detail: `rc=${taken.rc} ${taken.out} ${taken.err} | ${fx.read('credits.json')}`,
      },
    ];
  },
  async restoreDone(m) {
    const fx = fixtureTree();
    const r = await runCli(['bump', 'embed:tool', '--json'], withMutant(fx, m));
    const stamp =
      r.rc === 0 ? path.basename((JSON.parse(r.out) as { journal: string }).journal) : '';
    const rest = await runCli(['verify', '--restore', stamp], withMutant(fx, m));
    const missing = await runCli(['verify', '--restore', 'no-such-run'], withMutant(fx, m));
    return [
      {
        name: "verify --restore: a finished run's journal is refused by state, and its bump stays",
        ok:
          r.rc === 0 &&
          rest.rc === 1 &&
          rest.err.includes("is 'done'") &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.1.0'),
        detail: `bump rc=${r.rc} | rc=${rest.rc} ${rest.out} ${rest.err}`,
      },
      {
        name: 'verify --restore: an unknown stamp is refused by name, not a stack trace',
        ok: missing.rc === 1 && missing.err.includes('no journal no-such-run'),
        detail: `rc=${missing.rc} ${missing.err}`,
      },
    ];
  },
  async seconds(m) {
    const fx = fixtureTree((f) => {
      f.releases['embed:tool'][0].published = '2026-10-14T10:00:30Z';
    });
    const r = await runCli(['when', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'when: a publish instant with seconds is printed to the second, the instant the registry holds',
        ok: r.rc === 0 && r.out.includes('published 2026-10-14T10:00:30Z'),
        detail: `rc=${r.rc} ${r.out} ${r.err}`,
      },
    ];
  },
  async lock(m) {
    const fx = fixtureTree();
    const lock = path.join(fx.root, '.ci/cache/pins/.lock');
    fs.mkdirSync(path.dirname(lock), { recursive: true });
    fs.writeFileSync(lock, '');
    const empty = await runCli(['plan', 'embed:tool'], withMutant(fx, m));
    const emptyBump = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    sh(fx.root, 'checkout', '-q', '--', '.');
    fs.writeFileSync(lock, 'not a pid\n');
    const junk = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    sh(fx.root, 'checkout', '-q', '--', '.');
    fs.writeFileSync(lock, `${process.pid}\n`);
    const live = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    const kept = fs.existsSync(lock) && fs.readFileSync(lock, 'utf8') === `${process.pid}\n`;
    return [
      {
        name: 'lock: an empty or non-numeric lock file is stale debris, not a live run',
        ok: empty.rc === 0 && emptyBump.rc === 0 && junk.rc === 0,
        detail: `${emptyBump.rc} ${emptyBump.err} | ${junk.rc} ${junk.err}`,
      },
      {
        name: 'lock: a lock naming a live pid is never taken, and is left in place',
        ok: live.rc === 2 && live.err.includes('holds .ci/cache/pins/.lock') && kept,
        detail: `${live.rc} ${live.err} kept=${kept}`,
      },
      lockRaceCase(fx.root),
    ];
  },
  async submodule(m) {
    const fx = fixtureTree();
    const r = await runCli(['bump', 'embed:zed', '--task', 'cafe1234'], withMutant(fx, m));
    const lines = r.out.split('\n');
    const sub = lines.findIndex((l) => l.startsWith('  git -C private/renet commit -F '));
    const con = lines.findIndex((l) => l.startsWith('  git commit -F '));
    const conDraft = /-F (\S+)/.exec(lines[con] ?? '')?.[1];
    return [
      {
        name: 'bump: a submodule pin and its derive step yield per-repo commit lines, submodule first, with the pointer',
        ok:
          r.rc === 0 &&
          fx.read('private/renet/Dockerfile').includes('ZED_VERSION=2.1.0') &&
          fx.read('credits.json').includes('2.1.0') &&
          sub >= 0 &&
          con > sub &&
          / -- credits\.json private\/renet$/.test(lines[con] ?? '') &&
          conDraft !== undefined &&
          fs.readFileSync(conDraft, 'utf8').includes('Pointer: private/renet moves'),
        detail: `rc=${r.rc} ${r.out} ${r.err}`,
      },
    ];
  },
  async all(m) {
    const fx = fixtureTree();
    const r = await runCli(['bump', '--all', '--json'], withMutant(fx, m));
    const rep =
      r.rc === 0
        ? (JSON.parse(r.out) as { pins: Array<{ id: string }>; commands: CommandRecord[] })
        : null;
    return [
      {
        name: 'bump --all: both pins in one transaction, the gates of both in one run',
        ok:
          rep !== null &&
          rep.pins.length === 2 &&
          rep.commands.some(
            (c) => c.cmd === 'npm run ci -- --only check:fixture-tool,check:fixture-zed'
          ),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async soaked(m) {
    const fx = fixtureTree((f) => {
      f.releases['embed:tool'].unshift({
        version: '2.0.0',
        published: '2026-10-02T00:00:00Z',
        values: { 'sha256:amd64': SHA('d') },
      });
    });
    const r = await runCli(
      ['apply-soaked', '--json', '--out', path.join(fx.root, 'out')],
      withMutant(fx, m)
    );
    return [
      {
        name: 'apply-soaked: takes the in-range minor, never the soaked major, and writes the report and patches',
        ok:
          r.rc === 0 &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.1.0') &&
          fs.existsSync(path.join(fx.root, 'out/report.json')) &&
          fs
            .readFileSync(path.join(fx.root, 'out/console.patch'), 'utf8')
            .includes('+ARG TOOL_VERSION=1.1.0') &&
          fs
            .readFileSync(path.join(fx.root, 'out/private-renet.patch'), 'utf8')
            .includes('+ARG ZED_VERSION=2.1.0'),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async hold(m) {
    const fx = fixtureTree();
    const short = await runCli(['hold', 'embed:tool', '--reason', 'later'], withMutant(fx, m));
    const r = await runCli(
      [
        'hold',
        'embed:tool',
        '--reason',
        'tool 1.1 changes the archive layout the installer unpacks',
        '--expires',
        '2026-11-01',
      ],
      withMutant(fx, m)
    );
    const st = await runCli(['status', 'embed:tool', '--json'], withMutant(fx, m));
    const v = st.rc === 0 ? (JSON.parse(st.out) as { pins: PinView[] }).pins[0] : null;
    const b = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
    return [
      {
        name: 'hold: a hollow reason is refused by the shared BLOCKER validator',
        ok: short.rc === 1,
        detail: short.err,
      },
      {
        name: 'hold: writes the BLOCKER line, status reads the pin as held, and bump refuses it',
        ok:
          r.rc === 0 &&
          fx.read('.ci/policy/.fixture-blocklist').includes('tool  # BLOCKER: tool 1.1 changes') &&
          v?.state === 'held' &&
          b.rc === 1 &&
          b.err.includes('held'),
        detail: `${r.rc} ${r.err} | ${v?.state} | ${b.rc} ${b.err}`,
      },
    ];
  },
  async verify(m) {
    const fx = fixtureTree();
    const clean = await runCli(['verify'], withMutant(fx, m));
    fx.write('tool.lock.json', `${JSON.stringify({ tool: { version: '9.9.9' } }, null, 2)}\n`);
    const split = await runCli(['verify'], withMutant(fx, m));
    sh(fx.root, 'checkout', '-q', '--', 'tool.lock.json');
    const jdir = path.join(fx.root, '.ci/cache/pins/killed');
    fs.mkdirSync(jdir, { recursive: true });
    const orig = fx.read('Dockerfile');
    fx.write('Dockerfile', 'half-written\n');
    const crypto2 = crypto.createHash('sha256').update('half-written\n').digest('hex');
    fs.writeFileSync(
      path.join(jdir, 'journal.json'),
      JSON.stringify({
        stamp: 'killed',
        state: 'writing',
        pins: ['embed:tool'],
        files: {
          Dockerfile: {
            repo: '.',
            file: 'Dockerfile',
            before: Buffer.from(orig).toString('base64'),
            wrote: crypto2,
          },
        },
      })
    );
    const killed = await runCli(['verify'], withMutant(fx, m));
    const rest = await runCli(['verify', '--restore', 'killed'], withMutant(fx, m));
    return [
      {
        name: 'verify: green on a tree whose sites all match',
        ok: clean.rc === 0,
        detail: clean.err,
      },
      {
        name: 'verify: red when two sites of one role disagree',
        ok: split.rc === 1 && split.err.includes('the version sites disagree'),
        detail: split.err,
      },
      {
        name: 'verify: names a run killed mid-write, and --restore puts the journaled bytes back',
        ok:
          killed.rc === 1 &&
          killed.err.includes('journal killed') &&
          rest.rc === 0 &&
          fx.read('Dockerfile') === orig,
        detail: `${killed.err} | ${rest.out}`,
      },
    ];
  },
  async refusals(m) {
    const fx = fixtureTree();
    const live = await runCli(['status'], { PINS_MUTANT: 'no-restore' });
    const major = await runCli(['bump', 'embed:tool', '--major'], withMutant(fx, m));
    const verb = await runCli(['frobnicate'], withMutant(fx, m));
    return [
      {
        name: 'a mutant outside a fixture is refused',
        ok: live.rc === 2 && live.err.includes('refused'),
        detail: live.err,
      },
      { name: '--major without --reason is refused', ok: major.rc === 2, detail: major.err },
      { name: 'an unknown verb is a usage error', ok: verb.rc === 2, detail: verb.err },
    ];
  },
  async cli(m) {
    if (m) return [];
    const fx = fixtureTree();
    const r = spawnSync(
      process.execPath,
      [...process.execArgv, import.meta.filename, 'status', '--json'],
      {
        encoding: 'utf8',
        env: { ...process.env, ...fx.env() },
      }
    );
    let n = -1;
    try {
      n = (JSON.parse(r.stdout) as { pins: unknown[] }).pins.length;
    } catch {
      n = -1;
    }
    return [
      {
        name: 'the CLI as a process: status --json over the fixture exits 0 with both pins',
        ok: r.status === 0 && n === 2,
        detail: `rc=${r.status} ${r.stderr}`,
      },
    ];
  },
};

/** Which case each mutant must turn red: the safety property it disables. */
const MUTANT_CASES: Record<Mutant, string> = {
  'skip-site': 'bump',
  'ignore-soak': 'soak',
  'no-canonical': 'canonical',
  'partial-write': 'mismatch',
  'no-dirty-check': 'dirty',
  'no-restore': 'restore',
  'blind-restore': 'compare',
};

async function selftest(env: NodeJS.ProcessEnv): Promise<number> {
  const forced = env.PINS_MUTANT as Mutant | undefined;
  if (forced !== undefined && !(MUTANTS as readonly string[]).includes(forced)) {
    console.error(`pins: PINS_MUTANT=${forced} is not one of ${MUTANTS.join(', ')}`);
    return 2;
  }
  try {
    return await selftestCases(forced);
  } finally {
    for (const r of FIXTURE_ROOTS.splice(0)) fs.rmSync(r, { recursive: true, force: true });
  }
}

async function selftestCases(forced: Mutant | undefined): Promise<number> {
  const cases: ControlCase[] = [];
  for (const [name, c] of Object.entries(CASES)) {
    try {
      cases.push(...(await c(forced)));
    } catch (err) {
      cases.push({ name: `case ${name} ran`, ok: false, detail: (err as Error).stack });
    }
  }
  if (forced === undefined)
    for (const mutant of MUTANTS) {
      const target = MUTANT_CASES[mutant];
      let red: ControlCase[] = [];
      try {
        red = (await CASES[target](mutant)).filter((x) => !x.ok);
      } catch (err) {
        red = [{ name: (err as Error).message, ok: false }];
      }
      cases.push({
        name: `MUTANT ${mutant} turns the ${target} case red`,
        ok: red.length > 0,
        detail:
          'the case stayed green with its safety property disabled, so it does not test that property',
      });
    }
  return summarizeControls(cases);
}

async function main(): Promise<number> {
  const argv = process.argv.slice(2);
  if (argv[0] === '--selftest') return selftest(process.env);
  const r = await runCli(argv, process.env);
  if (r.out) process.stdout.write(`${r.out}\n`);
  if (r.err) process.stderr.write(`${r.err}\n`);
  return r.rc;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  process.exit(await main());
}
