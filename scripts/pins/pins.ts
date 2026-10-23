#!/usr/bin/env tsx
/**
 * `npm run pins -- <verb>`: one command for every pinned version in .ci/config/pins.json
 * (agent/plans/PLAN-pins-command.md Design 3).
 *
 *   status [<id>] [--json]                 what each pin is, and what it could move to
 *   when <id> [--json]                     when the newest too-new release clears the window,
 *                                          with a ready worklist DEFAULT line
 *   plan <id>|--all [--json]               the rewrite a bump would make; writes nothing
 *   bump <id> [<id>...] [--to <v>]... [--major --reason "<why>"] [--task <id>] [--json] [--out <dir>]
 *                                          one --reason covers every major the run's --to names,
 *                                          since the run is one transaction with one commit subject
 *                                          `bump npm --major` with no --to takes every pending held
 *                                          major with the in-range set, since check:deps judges all
 *                                          several ids plan into ONE transaction: one gate run, one commit draft;
 *                                          a duplicate or unknown id is refused by name
 *   bump --all [--task <id>] [--json] [--out <dir>]
 *   apply-soaked [--task <id>] [--json] [--out <dir>]
 *                                          bump --all limited to patches and in-range minors
 *   hold <id> --reason "<why>" [--expires YYYY-MM-DD] [--task <id>]
 *   remove <pkg> [--task <id>]             npm uninstall from every declaring manifest and drop
 *                                          every policy, override, syncpack and knip line for it
 *   lockfiles [<dir>] [--task <id>]        the canonical lockfile pass over every npm project
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
 * After the writes it runs `npx tsx scripts/gen/gen-docs.ts --write` and lists the generated files that
 * moved (a hold changes the blocklist row counts in two docs) in the commit line, and the drafts take
 * their `PR-TASK:` trailer from --task, else from the one epic of agent/pr/<branch>.md.
 *
 * THE DRIVERS are scripts/lib/pins/driver.ts's seam. The npm driver (T4/T6) has landed; T7 (embed,
 * devcontainer, toolchain) and T8 (actions, go-mod, the ceph pins, real-provider, docker)
 * register as they land. Until then an entry whose driver is absent reads as NOT COMPARED, and
 * every verb that needs a driver refuses it, fail closed.
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
  driverFor,
  type FileWrite,
  type Fixture,
  keyOf,
  leafCurrent,
  MUTANTS,
  type Mutant,
  type PinPlan,
  PlanRefused,
  readFixture,
  registerDrivers,
  withManifestGates,
} from '../lib/pins/driver.js';
import { lockDrift, planLockfiles, planRemove } from '../lib/pins/drivers/npm.js';
import {
  movedPinGroups,
  planManifestPins,
  predictManifests,
  sourceManifests,
} from '../lib/pins/drivers/pin-manifests.js';
import { realDrivers } from '../lib/pins/drivers/table.js';
import { familyGateOf } from '../lib/pins/family-gates.js';
import { ranLine } from '../lib/pins/ran-line.js';
import { loadRegistry, type PinEntry, type RepoPath, siteMatches } from '../lib/pins/registry.js';
import { iso, soakClearsAt } from '../lib/pins/soak.js';
import {
  contextOf,
  declaredSubmodules,
  holdOf,
  type PinView,
  type SelectOpts,
  type StatusWorld,
  viewOf,
} from '../lib/pins/status.js';
import {
  type CommandRecord,
  fixtureRunner,
  openJournals,
  type RepoChange,
  RestoreRefused,
  type Runner,
  realRunner,
  recordLateWrites,
  restoreJournal,
  runTransaction,
  type TxnResult,
  takeLock,
} from '../lib/pins/txn.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import { REPO_ROOT } from '../lib/repo-root.js';

// ---- the run's world ------------------------------------------------------------------------

interface World extends StatusWorld {
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

function pick(w: World, idOrAll: string | undefined, all: boolean): PinEntry[] {
  if (all) return w.reg.entries;
  if (!idOrAll) throw new Usage('name a pin id, or pass --all');
  const e = w.reg.entries.find((x) => x.id === idOrAll);
  if (!e) throw new Usage(`no pin ${idOrAll} in .ci/config/pins.json`);
  return [e];
}

/** The pins a verb names, in order: one transaction's selection. A duplicate or unknown id is refused by name, before any plan. */
function pickMany(w: World, ids: readonly string[], all: boolean): PinEntry[] {
  if (all) return w.reg.entries;
  if (ids.length === 0) throw new Usage('name a pin id, or pass --all');
  const dup = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
  if (dup.length > 0) throw new Usage(`pin id named twice: ${dup.join(', ')}`);
  const unknown = ids.filter((id) => !w.reg.entries.some((x) => x.id === id));
  if (unknown.length > 0) throw new Usage(`no pin ${unknown.join(', ')} in .ci/config/pins.json`);
  return ids.map((id) => w.reg.entries.find((x) => x.id === id) as PinEntry);
}

// ---- drafts ---------------------------------------------------------------------------------

interface RepoDraft extends RepoChange {
  draft: string;
  lines: string[];
}

const slug = (repo: string): string => (repo === '.' ? 'console' : repo.replace(/[^\w.-]+/g, '-'));

/** The repository a site line or a command directory belongs to: the longest submodule path its leading path token is, or lies under; the console otherwise. A label such as `private/account (update)` carries no slash after the repository, so a `${repo}/` prefix test alone misses it. Pure. */
export function repoOfPath(token: string, subs: readonly string[]): string {
  const head = /^[^\s:]+/.exec(token)?.[0] ?? '';
  const hit = [...subs]
    .sort((a, b) => b.length - a.length)
    .find((s) => head === s || head.startsWith(`${s}/`));
  return hit ?? '.';
}

export interface DraftInput {
  repo: string;
  /** The run's subject, which the console draft carries as is. */
  subject: string;
  /** Every plan of the run, with its release line and its site lines. */
  plans: Array<{ id: string; name: string; pinLine: string; changes: string[] }>;
  commands: CommandRecord[];
  gates: { ids: string[]; rc: number } | null;
  ungated: string[];
  /** The submodules whose commits the console commit moves the pointer of. */
  pointers: string[];
  /** Every scanned submodule path, for attributing site lines and command directories. */
  submodules: string[];
  /** The repository's own changed paths, for a subject when it carries no site line. */
  paths: string[];
  stamp: string;
  task: string | null;
  /** The shared-message mutant: the drafting before 2026-10-15, one change list for every repository. */
  shared?: boolean;
}

/**
 * One repository's drafted commit message. Each draft lists only what that repository's own commit changes: its own site lines and the commands run in it. A submodule's subject names the repository and its own changes, and the run's release lines appear in a submodule draft only for a plan whose every site lies in that submodule. The console draft carries the run's subject and release lines, and one pointer line per submodule naming that submodule's own commit. Pure.
 */
export function draftMessage(d: DraftInput): string {
  const cmdLine = (c: CommandRecord): string => ranLine(c);
  const gateLines = (): string[] =>
    d.ungated.length > 0
      ? [
          `Gates: none ran for ${d.ungated.join(', ')}; the registry entry names no gate (.ci/config/pins.json).`,
        ]
      : [];
  const tail = (lines: string[]): string =>
    [...lines, ...(d.task ? ['', `PR-TASK: ${d.task}`] : [])]
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  if (d.shared) {
    const subs = d.pointers;
    return tail([
      d.subject,
      '',
      ...d.plans.flatMap((p) => [p.pinLine, '']),
      ...d.plans
        .flatMap((p) =>
          p.changes.filter((ch) =>
            d.repo === '.' ? !ch.startsWith('private/') : ch.startsWith(`${d.repo}/`)
          )
        )
        .map((ch) => `Site: ${ch}`),
      '',
      ...d.commands.map(cmdLine),
      ...(d.repo === '.' && subs.length > 0
        ? [
            '',
            `Pointer: ${subs.join(', ')} moves to its own pins commit, committed in that repository first (submodule-first) and pushed before this one.`,
          ]
        : []),
    ]);
  }
  const mine = (ch: string): boolean => repoOfPath(ch, d.submodules) === d.repo;
  const sites = d.plans.flatMap((p) => p.changes.filter(mine));
  const ran = d.commands.filter((c) => repoOfPath(c.cwd, d.submodules) === d.repo);
  if (d.repo === '.')
    return tail([
      d.subject,
      '',
      ...d.plans.flatMap((p) => [p.pinLine, '']),
      ...sites.map((ch) => `Site: ${ch}`),
      '',
      ...ran.map(cmdLine),
      '',
      ...gateLines(),
      ...(d.pointers.length > 0
        ? [
            '',
            ...d.pointers.map(
              (s) =>
                `Pointer: ${s} moves to the ${s} pins commit, committed in ${s} first (submodule-first) and pushed before this one.`
            ),
          ]
        : []),
    ]);
  const verb = /^chore\(pins\): (\S+)/.exec(d.subject)?.[1] ?? 'update';
  const owners = d.plans.filter((p) => p.changes.some(mine));
  const items = sites.map((ch) => ch.replace(/^[^:]*:\s*/, ''));
  const what =
    items.length > 0
      ? `${items.slice(0, 2).join(', ')}${items.length > 2 ? ` and ${items.length - 2} more` : ''}`
      : `${d.paths.length} file(s)`;
  // A repository with changed paths but no owning site names no pin rather than every pin of the run (review f56ddcde.2).
  const names = owners.length > 0 ? `${owners.map((p) => p.name).join(', ')} ` : '';
  return tail([
    `chore(pins): ${verb} ${names}in ${d.repo}: ${what}`,
    '',
    `The ${d.repo} part of pins run ${d.stamp} (${d.plans.map((p) => p.id).join(', ')}); the console commit carries the run's release lines and the console's own sites.`,
    '',
    ...owners.filter((p) => p.changes.every(mine)).flatMap((p) => [p.pinLine, '']),
    ...sites.map((ch) => `Site: ${ch}`),
    '',
    ...ran.map(cmdLine),
    ...(d.gates
      ? [
          '',
          `Gates: npm run ci -- --only ${d.gates.ids.join(',')} rc=${d.gates.rc}, run from the console over this tree.`,
        ]
      : []),
    '',
    ...gateLines(),
  ]);
}

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
  const pinLineOf = (p: PinPlan): string => {
    if (p.from === p.to.version) return `${p.entry.id}: held at ${p.from}.`;
    const v = views.get(p.entry.id);
    const pub =
      p.to.publishedMs === null ? 'publish time unknown' : `published ${iso(p.to.publishedMs)}`;
    const clear =
      p.to.publishedMs === null
        ? ''
        : `, soak cleared ${iso(soakClearsAt(p.to.publishedMs, w.windowMs) ?? p.to.publishedMs)}`;
    return `${p.entry.id}: ${p.from ?? '?'} -> ${p.to.version}, ${pub}${clear}${v?.verdict ? ` (${v.verdict.why})` : ''}.`;
  };
  const drafted = plans.map((p) => ({
    id: p.entry.id,
    name: p.entry.name,
    pinLine: pinLineOf(p),
    changes: p.changes,
  }));
  return repos.map((c) => {
    const paths = c.repo === '.' ? [...c.paths, ...subs] : c.paths;
    const body = draftMessage({
      repo: c.repo,
      subject,
      plans: drafted,
      commands: res.commands,
      gates: res.gates,
      ungated: res.ungated,
      pointers: subs,
      submodules: [...new Set([...w.reg.submodules.scanned, ...subs])],
      paths: c.paths,
      stamp: res.stamp,
      task,
      shared: w.mutant === 'shared-message',
    });
    const draft = path.join(res.dir, `${slug(c.repo)}.msg`);
    fs.writeFileSync(draft, `${body}\n`);
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

// ---- generated docs and the epic trailer ---------------------------------------------------

const REGEN_CMD = 'npx tsx scripts/gen/gen-docs.ts --write';

/** Dirty files of the console repo with a content hash and whether git sees them as new; null when git cannot answer. */
function dirtyState(root: string): Map<string, { hash: string; added: boolean }> | null {
  const r = spawnSync(
    'git',
    ['-C', root, 'status', '--porcelain=v1', '--untracked-files=all', '-z'],
    {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    }
  );
  if (r.status !== 0) return null;
  const out = new Map<string, { hash: string; added: boolean }>();
  const parts = (r.stdout ?? '').split('\0');
  for (let i = 0; i < parts.length; i++) {
    const e = parts[i];
    if (e.length < 4) continue;
    const code = e.slice(0, 2);
    const file = e.slice(3);
    if (/[RC]/.test(code)) i++;
    const abs = path.join(root, file);
    if (file.endsWith('/') || !fs.existsSync(abs) || fs.statSync(abs).isDirectory()) continue;
    out.set(file, {
      hash: crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex'),
      added: code === '??' || code[0] === 'A',
    });
  }
  return out;
}

/** The files a `gen-docs.ts --write` run reports writing, from its `wrote <file> (<providers>)` lines. Pure. */
export function generatorWrote(out: string): Set<string> {
  const files = new Set<string>();
  for (const l of out.replace(/\x1b\[[0-9;]*m/g, '').split('\n')) {
    const m = /^wrote (\S+) \(/.exec(l.trim());
    if (m) files.add(m[1]);
  }
  return files;
}

/**
 * Regenerates the generated doc regions after a verb's writes landed. A hold moves the row counts in .ci/policy/README.md and scripts/data/doc-registry.md, and a bump can move any region that quotes a version, so the regeneration runs after every verb that wrote; a no-op when nothing moved. Returns the files the run changed that were clean beforehand (they belong in the commit), the files it changed that already held another session's edits (they do not), and the command record. A file this run itself wrote (`written`) is never foreign, whatever it held before; one of those that regeneration moved again is returned in `late`, as is every file it added to the commit, because the gates ran before it. A tree without the generator, or a fixture without a matching command, skips it.
 *
 * ONLY A FILE THE GENERATOR REPORTS WRITING IS ATTRIBUTED. The tree diff around the run sees every writer in the tree, not this one alone: on 2026-10-15 the per-commit reviewer wrote agent/reviews/1008-1/7a32b551...md while gen-docs ran, and the 01:18Z `bump --all` drafted a `git add` and a commit pathspec for it. A file the diff shows and the generator's `wrote` lines do not name is returned in `unclaimed` and stays out of the commit.
 */
function regenDocs(
  w: World,
  written: ReadonlySet<string>
): {
  record: CommandRecord | null;
  changed: string[];
  added: string[];
  foreign: string[];
  late: string[];
  unclaimed: string[];
  failure: string | null;
} {
  const none = {
    record: null,
    changed: [],
    added: [],
    foreign: [],
    late: [],
    unclaimed: [],
    failure: null,
  };
  const has = w.fixture
    ? w.fixture.commands.some((c) => new RegExp(c.match).test(REGEN_CMD))
    : fs.existsSync(path.join(w.root, 'scripts/gen/gen-docs.ts'));
  if (!has) return none;
  const before = dirtyState(w.root);
  if (before === null)
    return { ...none, failure: 'git status failed; the generated docs were not regenerated' };
  const r = w.runner(REGEN_CMD, w.root);
  const record: CommandRecord = { cmd: REGEN_CMD, cwd: '.', rc: r.rc };
  if (r.rc !== 0)
    return {
      ...none,
      record,
      failure: `${REGEN_CMD} failed (rc=${r.rc}); run it by hand before committing: ${r.out.slice(-400)}`,
    };
  const after = dirtyState(w.root) ?? new Map<string, { hash: string; added: boolean }>();
  const changed: string[] = [];
  const added: string[] = [];
  const foreign: string[] = [];
  const late: string[] = [];
  const unclaimed: string[] = [];
  const claimed = generatorWrote(r.out);
  for (const [file, now] of after) {
    const was = before.get(file);
    if (was?.hash === now.hash) continue;
    if (w.mutant !== 'tree-diff-attribution' && !claimed.has(file) && !written.has(file))
      unclaimed.push(file);
    else if (was && written.has(file)) late.push(file);
    else if (was) foreign.push(file);
    else {
      changed.push(file);
      late.push(file);
      if (now.added) added.push(file);
    }
  }
  return { record, changed, added, foreign, late, unclaimed, failure: null };
}

/** The epic id a commit on this branch carries: the one `PR-TASK:` id of agent/pr/<branch>.md, the snapshot block_untagged_commit validates a trailer against. Null when the branch has none or several (the caller then names the ids and asks for --task). */
function branchTask(root: string): { task: string | null; ids: string[] } {
  const b = spawnSync('git', ['-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'], {
    encoding: 'utf8',
  });
  const branch = (b.stdout ?? '').trim();
  const snap = path.join(root, 'agent/pr', `${branch}.md`);
  if (b.status !== 0 || !branch || branch === 'HEAD' || !fs.existsSync(snap))
    return { task: null, ids: [] };
  const ids = [
    ...new Set(
      [...fs.readFileSync(snap, 'utf8').matchAll(/^`?PR-TASK:\s*([0-9a-f]{6,32})`?\s*$/gm)].map(
        (m) => m[1]
      )
    ),
  ];
  return { task: ids.length === 1 ? ids[0] : null, ids };
}

// ---- verbs ----------------------------------------------------------------------------------

interface Flags {
  json: boolean;
  all: boolean;
  /** Every `--to` given, a comma list counting as several; more than one is taken in one transaction. */
  to: string[];
  major: boolean;
  reason?: string;
  expires?: string;
  task: string | null;
  out?: string;
  restore?: string;
  /** Files a killed step had in flight that `verify --restore` may give their before-bytes back, once the operator has inspected them. */
  inflight: string[];
  /** Paths whose uncommitted bytes this run adopts as the caller's own hand step (`--adopt <path>`, repeatable); see TxnOptions.adopt. */
  adopt: string[];
  pos: string[];
}

function parseFlags(argv: string[]): Flags {
  const f: Flags = {
    json: false,
    all: false,
    to: [],
    major: false,
    task: null,
    inflight: [],
    adopt: [],
    pos: [],
  };
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
    else if (a === '--to') {
      const named = val(i++, a)
        .split(',')
        .filter((x) => x !== '');
      // An empty value (an unset shell variable) names nothing, and taking it as absent would turn the run into a plain bump.
      if (named.length === 0)
        throw new Usage('--to needs a version or key; an empty value names none');
      f.to.push(...named);
    } else if (a === '--reason') f.reason = val(i++, a);
    else if (a === '--expires') f.expires = val(i++, a);
    else if (a === '--task') f.task = val(i++, a);
    else if (a === '--out') f.out = val(i++, a);
    else if (a === '--restore') f.restore = val(i++, a);
    else if (a === '--inflight') f.inflight.push(val(i++, a));
    else if (a === '--adopt') f.adopt.push(val(i++, a));
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
  /** Pins that could not be compared because a submodule they read is not checked out: reported, never counted toward the exit code. */
  notChecked: Array<{ id: string; submodules: string[]; why: string }>;
}

/** Inspect and plan every selected pin over one overlay, so two pins sharing a file compose. */
async function selectAndPlan(
  w: World,
  entries: PinEntry[],
  sel: SelectOpts,
  explicit: boolean
): Promise<Selected> {
  const ctx = contextOf(w);
  const out: Selected = {
    plans: [],
    views: new Map(),
    refused: [],
    skipped: [],
    notChecked: [],
  };
  for (const entry of entries) {
    const v = await viewOf(w, ctx, entry, sel);
    out.views.set(entry.id, v);
    if (v.state !== 'bumpable' || !v.target) {
      const why = v.state === 'not-compared' ? v.detail : `${v.state}: ${v.detail}`;
      if (!explicit && v.state === 'not-compared' && v.notChecked.length > 0) {
        out.notChecked.push({ id: entry.id, submodules: v.notChecked, why });
        continue;
      }
      // AN UNNAMED SELECTION (`bump --all`, `apply-soaked`) skips a pin it could never compare for a reason already on record: a `source: none` leaf (its BLOCKER is in the registry, as check:ci-pin-freshness counts it) and a leaf no driver serves whose own family gate judges it (check:ci-pin-freshness leaves every family-gated leaf to its gate; a family-gated leaf a driver serves is compared, so it never reaches this branch as not-compared). Unknown upstream stays a refusal (fail closed); a pin named on the command line is always refused when not compared.
      if (!explicit && v.state === 'not-compared') {
        const family = familyGateOf(entry.gates);
        if (entry.source.type === 'none' || (family && !driverFor(entry, ctx))) {
          out.skipped.push({
            id: entry.id,
            why:
              entry.source.type === 'none'
                ? `no upstream source (BLOCKER in the registry): ${v.detail}`
                : `owned by ${family}: ${v.detail}`,
          });
          continue;
        }
      }
      if (explicit || v.state === 'not-compared') out.refused.push({ id: entry.id, why });
      else out.skipped.push({ id: entry.id, why });
      continue;
    }
    const drv = driverFor(entry, ctx);
    try {
      const plan = await (drv as NonNullable<typeof drv>).plan(entry, v.target, ctx, v.also);
      // --MAJOR NAMES A MAJOR. A run given --major whose selection takes none (a family lists its in-range batch first, so the first eligible release is that batch) is refused before any write, with the --to line that names the majors; the first-eligible mutant lets it through (2026-10-15: `bump npm --major` planned only the in-range batch).
      if (sel.allowMajor && !v.takesMajor && ctx.mutant !== 'first-eligible') {
        out.refused.push({
          id: entry.id,
          why: `--major was given but the selection takes no major (${v.target.version}); ${
            v.eligibleMajors.length > 0
              ? `name the major(s) to take: npm run pins -- bump ${entry.id} ${v.eligibleMajors.map((k) => `--to ${k}`).join(' ')} --major --reason "<why now>"`
              : 'no eligible major is pending, so drop --major'
          }`,
        });
        continue;
      }
      for (const wr of plan.writes) ctx.overlay.set(keyOf(wr), wr.after);
      out.plans.push(withManifestGates(plan, ctx.mutant));
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
          not_checked: s.notChecked,
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
    noteNotChecked(w, s);
  }
  return s.refused.length ? 1 : 0;
}

/** The human lines for the pins no submodule checkout let the run compare; they never change the exit code. */
function noteNotChecked(w: World, s: Selected): void {
  for (const n of s.notChecked)
    w.err.push(`NOT-CHECKED ${n.id}: ${n.submodules.join(', ')} not checked out (${n.why})`);
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
    not_checked: s.notChecked,
    failure: res?.failure ?? null,
    commands: res?.commands ?? [],
    gates: res?.gates ?? null,
    ungated: res?.ungated ?? [],
    restored: res?.restored ?? [],
    resynced: res?.resynced ?? [],
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
      noteNotChecked(w, s);
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
      registry: w.reg.entries,
      adopt: f.adopt,
    });
  } finally {
    release();
  }
  let regenFailure: string | null = null;
  let foreignDocs: string[] = [];
  let lateDocs: string[] = [];
  let unclaimedDocs: string[] = [];
  if (res.ok) {
    const g = regenDocs(
      w,
      new Set(res.changes.filter((c) => c.repo === '.').flatMap((c) => c.paths))
    );
    regenFailure = g.failure;
    foreignDocs = g.foreign;
    lateDocs = g.late;
    unclaimedDocs = g.unclaimed;
    if (g.record) res.commands.push(g.record);
    recordLateWrites(
      w.root,
      res.stamp,
      g.late.map((file) => ({ repo: '.', file }))
    );
    if (g.changed.length > 0) {
      const home = res.changes.find((c) => c.repo === '.');
      if (home) {
        home.paths.push(...g.changed.filter((p) => !home.paths.includes(p)));
        home.added.push(...g.added);
      } else res.changes.push({ repo: '.', paths: g.changed, added: g.added });
    }
  }
  const derived = f.task ? { task: f.task, ids: [] as string[] } : branchTask(w.root);
  f.task = derived.task;
  const drafts =
    res.ok && regenFailure === null ? writeDrafts(w, res, s.plans, s.views, f.task, subject) : [];
  const rep = report(w, f, s, res, drafts);
  if (f.out) writeOut(w, path.resolve(f.out), rep, drafts);
  if (f.json) {
    w.out.push(JSON.stringify(rep, null, 2));
    return res.ok && s.refused.length === 0 ? 0 : 1;
  }
  for (const r of s.refused) w.err.push(`REFUSED ${r.id}: ${r.why}`);
  noteNotChecked(w, s);
  if (regenFailure !== null) {
    w.err.push(`FAILED: ${regenFailure}`);
    w.err.push(`journal: ${res.dir}`);
    return 1;
  }
  for (const d of foreignDocs)
    w.err.push(
      `note: ${d} was regenerated but already held another session's edits, so it is not in the commit line`
    );
  for (const d of unclaimedDocs)
    w.err.push(
      `note: ${d} changed while the generated docs were regenerated, but the generator did not report writing it (another writer in the tree), so it is not in the commit line`
    );
  if (res.ok && res.gates)
    for (const d of lateDocs)
      w.err.push(
        `note: ${d} was regenerated after the gates ran, so the gate run did not see its final bytes`
      );
  if (!res.ok) {
    w.err.push(`FAILED: ${res.failure}`);
    if (res.restored.length) w.err.push(`restored: ${res.restored.join(', ')}`);
    if (res.resynced.length)
      w.err.push(
        `reinstalled to match the restored lockfiles (npm ci): ${res.resynced.join(', ')}`
      );
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
  if (res.ungated.length > 0)
    w.out.push(
      `gates: none ran for ${res.ungated.join(', ')}; the registry entry names no gate (.ci/config/pins.json gates)`
    );
  if (!f.task)
    w.out.push(
      derived.ids.length > 1
        ? `note: the branch carries ${derived.ids.length} epics (${derived.ids.join(', ')}), so pass --task <id>; the drafts carry no PR-TASK trailer`
        : 'note: no --task given and the branch snapshot names no epic, so the drafts carry no PR-TASK trailer'
    );
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
    throw new Usage(
      '--major needs --reason "<why the major is safe now>", one reason covering every major the run moves'
    );
  const all = soakedOnly || f.all;
  if (all && f.to.length > 0)
    throw new Usage('--to names releases of one pin; it does not combine with --all');
  const entries = pickMany(w, f.pos, all);
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
  // An expired hold is RENEWED in place: a second line for the key would leave the file holding two verdicts for one pin.
  const after = existing
    ? text
        .split('\n')
        .map((l, i) => (i === existing.line - 1 ? line : l))
        .join('\n')
    : `${text}${text === '' || text.endsWith('\n\n') ? '' : text.endsWith('\n') ? '\n' : '\n\n'}${line}\n`;
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
    notChecked: [],
  };
  return apply(w, f, s, `chore(pins): hold ${entry.name} at ${cur}`);
}

/** `remove <pkg>` and `lockfiles [<dir>]`: the npm driver's two plans that are not a version move (scripts/lib/pins/drivers/npm.ts). */
function cmdNpmPlan(w: World, f: Flags, verb: 'remove' | 'lockfiles'): number {
  const entry = w.reg.entries.find((e) => e.driver === 'npm');
  if (!entry) throw new Usage('no npm entry in .ci/config/pins.json');
  const arg = f.pos[0];
  if (verb === 'remove' && !arg) throw new Usage('remove needs a package name');
  const ctx = contextOf(w);
  let plan: PinPlan;
  try {
    plan = withManifestGates(
      verb === 'remove' ? planRemove(entry, ctx, arg) : planLockfiles(entry, ctx, arg),
      ctx.mutant
    );
  } catch (err) {
    if (!(err instanceof PlanRefused)) throw err;
    w.err.push(`REFUSED ${verb}: ${err.message}`);
    return 1;
  }
  const s: Selected = {
    plans: [plan],
    views: new Map(),
    refused: [],
    skipped: [],
    notChecked: [],
  };
  return apply(
    w,
    f,
    s,
    verb === 'remove'
      ? `chore(deps): remove ${arg}`
      : `chore(deps): canonical lockfiles${arg ? ` (${arg})` : ''}`
  );
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
    if (f.inflight.length > 0 && !(verb === 'verify' && f.restore))
      throw new Usage('--inflight only goes with `verify --restore <stamp>`');
    let rc: number;
    if (verb === 'status') rc = await cmdStatus(w, f);
    else if (verb === 'when') rc = await cmdWhen(w, f);
    else if (verb === 'plan') rc = await cmdPlan(w, f);
    else if (verb === 'bump') rc = await cmdBump(w, f, false);
    else if (verb === 'apply-soaked') rc = await cmdBump(w, f, true);
    else if (verb === 'hold') rc = await cmdHold(w, f);
    else if (verb === 'verify') rc = cmdVerify(w, f);
    else if (verb === 'remove') rc = cmdNpmPlan(w, f, 'remove');
    else if (verb === 'lockfiles') rc = cmdNpmPlan(w, f, 'lockfiles');
    else
      throw new Usage(
        `unknown verb ${verb ?? '(none)'}; verbs: status, when, plan, bump, apply-soaked, hold, remove, lockfiles, verify`
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

/** Two takers judge the same dead-pid lock stale; the second one wins the window and holds a fresh lock before the first clears. The first must then stand down and leave the fresh lock in place, not remove it and take the lock too. */
function lockRaceCase(root: string): { name: string; ok: boolean; detail: string } {
  const lock = path.join(root, '.ci/cache/pins/.lock');
  fs.mkdirSync(path.dirname(lock), { recursive: true });
  fs.rmSync(lock, { force: true });
  fs.writeFileSync(lock, '999999999\n');
  const fresh = `${process.ppid}\n`;
  const release = takeLock(root, {
    afterStaleVerdict: () => {
      fs.rmSync(lock, { force: true });
      fs.writeFileSync(lock, fresh);
    },
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

/** A taker moves a fresh live lock aside by mistake and a third taker links its own lock before the first can put it back: the third taker's lock stays, and the moved one stays named in its tomb file instead of being deleted. */
function lockMisMoveCase(root: string): { name: string; ok: boolean; detail: string } {
  const dir = path.join(root, '.ci/cache/pins');
  const lock = path.join(dir, '.lock');
  fs.mkdirSync(dir, { recursive: true });
  fs.rmSync(lock, { force: true });
  fs.writeFileSync(lock, '999999999\n');
  const mine = `${process.pid}\n`;
  const owner = `${process.ppid}\n`;
  const release = takeLock(root, {
    afterStaleVerdict: () => {
      fs.rmSync(lock, { force: true });
      fs.writeFileSync(lock, owner);
    },
    afterMove: () => fs.writeFileSync(lock, mine),
  });
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  const tombs = fs.readdirSync(dir).filter((n) => n.startsWith('.lock.stale.'));
  const kept = tombs.map((n) => fs.readFileSync(path.join(dir, n), 'utf8'));
  for (const n of tombs) fs.rmSync(path.join(dir, n), { force: true });
  fs.rmSync(lock, { force: true });
  return {
    name: 'lock: a mis-moved live lock whose slot a third taker filled stays named in its tomb, not deleted',
    ok: release === null && held === mine && kept.length === 1 && kept[0] === owner,
    detail:
      tombs.length === 0
        ? `VACUOUS: ${dir} lists no .lock.stale.* tomb, so the tomb this case reads was never written and "kept" proves nothing`
        : `took=${release !== null} lock=${JSON.stringify(held)} tombs=${JSON.stringify(kept)}`,
  };
}

/** A filesystem that refuses hard links (EPERM) still yields a lock, by an exclusive create. */
function lockNoHardLinkCase(root: string): { name: string; ok: boolean; detail: string } {
  const lock = path.join(root, '.ci/cache/pins/.lock');
  fs.mkdirSync(path.dirname(lock), { recursive: true });
  fs.rmSync(lock, { force: true });
  const real = fs.linkSync;
  fs.linkSync = (): void => {
    throw Object.assign(new Error('operation not permitted'), { code: 'EPERM' });
  };
  let release: (() => void) | null = null;
  let threw = '';
  try {
    release = takeLock(root);
  } catch (err) {
    threw = (err as Error).message;
  } finally {
    fs.linkSync = real;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  if (release) release();
  fs.rmSync(lock, { force: true });
  return {
    name: 'lock: a filesystem that refuses hard links still takes the lock, by an exclusive create',
    ok: release !== null && held === `${process.pid}\n`,
    detail: `threw=${threw} lock=${JSON.stringify(held)}`,
  };
}

/** A fixture console with a nested private/renet repo, both committed; `tune` edits the fixture JSON, and `family` adds an `npm` family entry the fixture family driver answers from `fixture.families`. */
function fixtureTree(tune: (fx: Fixture) => void = () => {}, family = false): Fx {
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
  if (family)
    reg.entries.push({
      id: 'npm',
      kind: 'family',
      name: 'npm trees',
      driver: 'npm',
      source: { type: 'npm-registry', package: '*' },
      safety: { mode: 'release-age', major: 'allow-file' },
      holds: ['.ci/policy/.fixture-blocklist'],
      gates: ['check:fixture-deps'],
      scope: [{ scanner: 'npm-lockfile', repo: '.', files: ['package-lock.json'] }],
      sites: [],
      derive: [],
      literals: [],
    } as unknown as (typeof reg.entries)[number]);
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
  async multito(m) {
    const fx = fixtureTree();
    const r = await runCli(
      ['bump', 'embed:tool', '--to', '1.1.0', '--to', '1.2.0', '--json'],
      withMutant(fx, m)
    );
    const one = await runCli(['plan', 'embed:tool', '--to', '1.1.0,1.1.0'], withMutant(fx, m));
    const absent = await runCli(['plan', 'embed:tool', '--to', '9.9.9'], withMutant(fx, m));
    return [
      {
        name: 'plan: a --to the source never answered names the releases it did answer, so it cannot read as a registry outage',
        ok:
          absent.rc === 1 &&
          /9\.9\.9 is not among the releases newer than 1\.0\.0 the source answered \(it answered \d+: 1\./.test(
            `${absent.out}${absent.err}`
          ),
        detail: `rc=${absent.rc} ${absent.err} ${absent.out.slice(0, 600)}`,
      },
      {
        name: 'bump: several --to are refused for a driver that cannot take them as a set, and nothing is written',
        ok:
          r.rc === 1 &&
          /several --to are taken together only by the npm driver/.test(`${r.out}${r.err}`) &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.0.0'),
        detail: `rc=${r.rc} ${r.err} ${r.out.slice(0, 600)}`,
      },
      {
        name: 'plan: a comma list of two names is parsed as two (the same name twice is still two requests)',
        ok: one.rc === 1 && /several --to/.test(`${one.out}${one.err}`),
        detail: `rc=${one.rc} ${one.err} ${one.out.slice(0, 600)}`,
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
        name: 'bump: the gates run once as `npm run ci -- --only <ids> --events <journal>/gates.jsonl`',
        ok:
          cmds.filter((c) => c.startsWith('npm run ci -- ')).length === 1 &&
          cmds.some((c) =>
            /^npm run ci -- --only check:fixture-tool --events \/\S+\/gates\.jsonl$/.test(c)
          ),
        detail: cmds.join(' | '),
      },
      {
        name: 'bump: the draft names versions, publish time, soak clearance, gate rc and PR-TASK',
        ok:
          /^chore\(pins\): bump tool 1\.0\.0 to 1\.1\.0$/m.test(draft) &&
          draft.includes('published 2026-10-01T00:00:00Z, soak cleared 2026-10-03T00:00:00Z') &&
          /npm run ci -- --only check:fixture-tool --events \S+ \(in \.\) rc=0/.test(draft) &&
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
  async ledger(m) {
    const bumpTwice = async (peer: boolean) => {
      const fx = fixtureTree();
      const a = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
      if (peer) fx.write('Dockerfile', `${fx.read('Dockerfile')}# a peer session's note\n`);
      const mid = snap(fx, TOOL_FILES);
      const rel = fx.fixture.releases['embed:tool'];
      rel[0].published = '2026-10-02T00:00:00Z';
      fs.writeFileSync(path.join(fx.root, 'fixture.json'), JSON.stringify(fx.fixture));
      const b = await runCli(['bump', 'embed:tool'], withMutant(fx, m));
      return { fx, a, b, mid };
    };
    const seq = await bumpTwice(false);
    const peer = await bumpTwice(true);
    const lock = (dirtyManifest: boolean) => {
      const fx = fixtureTree((x) => {
        x.commands.unshift({
          match:
            '^npx -y npm@11\\.20\\.0 install --package-lock-only --ignore-scripts --loglevel=notice$',
          rc: 0,
        });
      }, true);
      fx.write('package-lock.json', '{ "lockfileVersion": 3, "manual": true }\n');
      if (dirtyManifest)
        fx.write('package.json', '{ "name": "pins-fixture", "private": true, "x": 1 }\n');
      return { fx, mid: snap(fx, ['package-lock.json', 'package.json']) };
    };
    const clean = lock(false);
    const lockClean = await runCli(['lockfiles'], withMutant(clean.fx, m));
    const adopted = lock(false);
    const lockAdopted = await runCli(
      ['lockfiles', '--adopt', './sub/../package-lock.json'],
      withMutant(adopted.fx, m)
    );
    // The other spellings the normalisation claims: a backslash path, a doubled slash and an interior `/./` segment.
    const spelled: Array<{ spelling: string; rc: number; kept: boolean }> = [];
    for (const spelling of [
      '.\\package-lock.json',
      './/package-lock.json',
      'sub/./../package-lock.json',
    ]) {
      const fx = lock(false);
      const r = await runCli(['lockfiles', '--adopt', spelling], withMutant(fx.fx, m));
      spelled.push({
        spelling,
        rc: r.rc,
        kept: fx.fx.read('package-lock.json').includes('"manual": true'),
      });
    }
    const stray = lock(false);
    const lockStray = await runCli(['lockfiles', '--adopt', 'nope.json'], withMutant(stray.fx, m));
    const empty = lock(false);
    const lockEmpty = await runCli(['lockfiles', '--adopt', ''], withMutant(empty.fx, m));
    const dirtyM = lock(true);
    const lockDirty = await runCli(['lockfiles'], withMutant(dirtyM.fx, m));
    return [
      {
        name: 'bump: a second run over the files the first run left uncommitted is accepted and both edits are present',
        ok:
          seq.a.rc === 0 &&
          seq.b.rc === 0 &&
          seq.fx.read('Dockerfile').includes('TOOL_VERSION=1.2.0'),
        detail: `a=${seq.a.rc} b=${seq.b.rc} ${seq.b.err}`,
      },
      {
        name: "bump: a peer's line added after the first run's write is refused by name, the file byte-identical",
        ok:
          peer.a.rc === 0 &&
          peer.b.rc === 1 &&
          /refused: Dockerfile already hold/.test(peer.b.err) &&
          same(peer.mid, snap(peer.fx, TOOL_FILES)),
        detail: `a=${peer.a.rc} b=${peer.b.rc} ${peer.b.err}`,
      },
      {
        name: 'lockfiles: a hand-changed lockfile nobody adopted is refused, byte-identical, even beside a clean manifest',
        ok:
          lockClean.rc === 1 &&
          /refused: package-lock\.json already hold/.test(lockClean.err) &&
          same(clean.mid, snap(clean.fx, ['package-lock.json', 'package.json'])),
        detail: `rc=${lockClean.rc} ${lockClean.err}`,
      },
      {
        name: 'lockfiles: the same lockfile named with --adopt (as ./sub/../package-lock.json) is accepted, its hand edit still on disk',
        ok: lockAdopted.rc === 0 && adopted.fx.read('package-lock.json').includes('"manual": true'),
        detail: `rc=${lockAdopted.rc} ${lockAdopted.err}`,
      },
      {
        name: 'lockfiles: --adopt as .\\package-lock.json, .//package-lock.json and sub/./../package-lock.json is accepted too (the backslash, doubled-slash and dot-segment spellings)',
        ok: spelled.every((x) => x.rc === 0 && x.kept),
        detail: JSON.stringify(spelled),
      },
      {
        name: 'lockfiles: an --adopt naming no file this run writes is refused by name, nothing written',
        ok:
          lockStray.rc === 1 &&
          /--adopt nope\.json names no file this run writes/.test(lockStray.err) &&
          same(stray.mid, snap(stray.fx, ['package-lock.json', 'package.json'])),
        detail: `rc=${lockStray.rc} ${lockStray.err}`,
      },
      {
        name: "lockfiles: an empty --adopt is refused naming '' as typed, not the '.' normalize makes of it",
        ok:
          lockEmpty.rc === 1 &&
          /--adopt '' names no file this run writes/.test(lockEmpty.err) &&
          same(empty.mid, snap(empty.fx, ['package-lock.json', 'package.json'])),
        detail: `rc=${lockEmpty.rc} ${lockEmpty.err}`,
      },
      {
        name: 'lockfiles: a changed lockfile beside a changed manifest is refused, both byte-identical',
        ok:
          lockDirty.rc === 1 &&
          /refused: package-lock\.json already hold/.test(lockDirty.err) &&
          same(dirtyM.mid, snap(dirtyM.fx, ['package-lock.json', 'package.json'])),
        detail: `rc=${lockDirty.rc} ${lockDirty.err}`,
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
  async npmbump(m) {
    const fx = fixtureTree((f) => {
      f.steps = {
        'embed:tool': [
          {
            label: 'move the pinned npm and relock',
            run: 'relock-new-npm',
            cwd: '.',
            writes: [
              { repo: '.', file: 'package-lock.json' },
              { repo: '.', file: '.devcontainer/toolchain.env' },
            ],
          },
        ],
      };
      f.commands.push({ match: '^npx -y npm@11\\.21\\.0 ', rc: 0 });
      f.commands.push({
        match: '^relock-new-npm$',
        rc: 0,
        writes: {
          'package-lock.json': '{ "lockfileVersion": 3, "x": 2 }\n',
          '.devcontainer/toolchain.env': 'NPM_VERSION=11.21.0\n',
        },
      });
    });
    const r = await runCli(['bump', 'embed:tool', '--json'], withMutant(fx, m));
    const cmds =
      r.rc === 0
        ? (JSON.parse(r.out) as { commands: CommandRecord[] }).commands.map((c) => c.cmd)
        : [];
    return [
      {
        name: 'bump: a run that moves NPM_VERSION canonicalises, installs and runs install:natives under the NEW npm, never the one read at startup',
        ok:
          cmds.includes('npx -y npm@11.21.0 install --package-lock-only --ignore-scripts') &&
          cmds.includes('npx -y npm@11.21.0 ci') &&
          cmds.includes('npx -y npm@11.21.0 run install:natives') &&
          !cmds.some((c) => c.includes('npm@11.20.0')),
        detail: `rc=${r.rc} ${r.err} ${r.out.slice(0, 2500).replace(/\s+/g, ' ')} ${cmds.join(' | ')}`,
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
    // A step that rewrites a file the plan itself already wrote (dirty before and after the step) is still caught, by its bytes; the rewritten file no longer holds the bytes the run wrote, so compare-and-restore names it and leaves it, and restores the other sites.
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
    // A step that deletes a file the plan wrote hashes it as absent rather than throwing: the undeclared deletion fails the run by name, and a declared one is counted as the step's.
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
  async restoreEdges(m) {
    const fx = fixtureTree();
    const jroot = path.join(fx.root, '.ci/cache/pins');
    const before = (rel: string): string => Buffer.from(fx.read(rel)).toString('base64');
    const sha256 = (t: string): string => crypto.createHash('sha256').update(t).digest('hex');
    const journal = (state: string, files: object): string =>
      JSON.stringify({ stamp: 'x', state, pins: ['embed:tool'], files });
    // A journal with one file the run wrote and one a killed step had in flight.
    const dockerBefore = before('Dockerfile');
    const creditsBefore = before('credits.json');
    const orig = fx.read('Dockerfile');
    fx.write('Dockerfile', 'half-written\n');
    fx.write('credits.json', '{ "edited": 1 }\n');
    fs.mkdirSync(path.join(jroot, 'replay'), { recursive: true });
    fs.writeFileSync(
      path.join(jroot, 'replay', 'journal.json'),
      journal('writing', {
        Dockerfile: {
          repo: '.',
          file: 'Dockerfile',
          before: dockerBefore,
          wrote: sha256('half-written\n'),
        },
        'credits.json': {
          repo: '.',
          file: 'credits.json',
          before: creditsBefore,
          wrote: null,
          inflight: true,
        },
      })
    );
    const first = await runCli(['verify', '--restore', 'replay'], withMutant(fx, m));
    const second = await runCli(
      ['verify', '--restore', 'replay', '--inflight', 'credits.json'],
      withMutant(fx, m)
    );
    // A live run's lock: its stamp is not a killed run's to restore.
    fx.write('Dockerfile', 'live step output\n');
    fs.mkdirSync(path.join(jroot, 'livejob'), { recursive: true });
    fs.writeFileSync(
      path.join(jroot, 'livejob', 'journal.json'),
      journal('writing', {
        Dockerfile: {
          repo: '.',
          file: 'Dockerfile',
          before: dockerBefore,
          wrote: null,
          inflight: true,
        },
      })
    );
    fs.writeFileSync(path.join(jroot, '.lock'), `${process.ppid}\n`);
    const live = await runCli(['verify', '--restore', 'livejob'], withMutant(fx, m));
    const liveBytes = fx.read('Dockerfile');
    fs.rmSync(path.join(jroot, '.lock'), { force: true });
    // '..' is not a stamp: it would read journal.json from the journal root's parent.
    fs.writeFileSync(path.join(fx.root, '.ci/cache/journal.json'), journal('writing', {}));
    const dots = await runCli(['verify', '--restore', '..'], withMutant(fx, m));
    const dot = await runCli(['verify', '--restore', '.'], withMutant(fx, m));
    // A stray entry beside the journals is not a layout the reader no longer knows.
    const clean = fixtureTree();
    fs.mkdirSync(path.join(clean.root, '.ci/cache/pins'), { recursive: true });
    fs.writeFileSync(path.join(clean.root, '.ci/cache/pins/.DS_Store'), 'x');
    const stray = await runCli(['verify'], withMutant(clean, m));
    return [
      {
        name: 'verify --restore: a replayed journal does not list files its earlier pass restored as changed since',
        ok:
          first.rc === 1 &&
          second.rc === 0 &&
          !second.out.includes('left alone') &&
          fx.read('credits.json') === '{}\n' &&
          orig.length > 0,
        detail: `first ${first.rc} ${first.out} ${first.err} | second ${second.rc} ${second.out} ${second.err}`,
      },
      {
        name: 'verify --restore: a stamp whose run still holds the lock is refused, its files untouched',
        ok: live.rc === 1 && live.err.includes('holds') && liveBytes === 'live step output\n',
        detail: `${live.rc} ${live.err} ${liveBytes}`,
      },
      {
        name: "verify --restore: '.' and '..' are refused as stamps",
        ok:
          dots.rc === 1 &&
          dot.rc === 1 &&
          dots.err.includes('no journal ..') &&
          dot.err.includes('no journal .'),
        detail: `${dots.rc} ${dots.err} | ${dot.rc} ${dot.err}`,
      },
      {
        name: 'verify: a stray file in the journal root is skipped, not read as an unknown layout',
        ok: stray.rc === 0,
        detail: `${stray.rc} ${stray.err}`,
      },
    ];
  },
  async majorWording(m) {
    const major = [{ version: '2.0.0', published: '2026-09-01T00:00:00Z' }];
    const refuse = fixtureTree((fx) => {
      fx.releases['embed:tool'] = major;
    });
    const reg = JSON.parse(refuse.read('.ci/config/pins.json')) as {
      entries: Array<{ safety: { major: string } }>;
    };
    reg.entries[0].safety.major = 'refuse';
    refuse.write('.ci/config/pins.json', `${JSON.stringify(reg, null, 2)}\n`);
    const assisted = fixtureTree((fx) => {
      fx.releases['embed:tool'] = major;
    });
    const a = await runCli(['status', 'embed:tool', '--json'], withMutant(refuse, m));
    const b = await runCli(['status', 'embed:tool', '--json'], withMutant(assisted, m));
    const va = (JSON.parse(a.out) as { pins: PinView[] }).pins[0];
    const vb = (JSON.parse(b.out) as { pins: PinView[] }).pins[0];
    return [
      {
        name: 'status: a major-only pin that refuses majors says it moves by hand, with no --major hint',
        ok:
          va.state === 'major-only' &&
          va.detail.includes('refuses a major bump') &&
          !va.detail.includes('--major'),
        detail: JSON.stringify(va),
      },
      {
        name: 'status: a major-only pin that allows an assisted major names the `bump --major --reason` line',
        ok: vb.state === 'major-only' && vb.detail.includes('--major --reason'),
        detail: JSON.stringify(vb),
      },
    ];
  },
  // A release a driver marks BREAKING (a Go minor line: same leading number, another `go` directive in every go.mod) is a major everywhere.
  async breaking(m) {
    const brk = {
      line: '2.1',
      why: 'Fixture 2.1 is another minor line; it changes the go directive of every go.mod',
    };
    const mixed = fixtureTree((fx) => {
      fx.releases['embed:zed'] = [
        { version: '2.1.0', published: '2026-10-01T00:00:00Z', breaking: brk },
        { version: '2.0.1', published: '2026-10-01T00:00:00Z' },
        { version: '2.0.0', published: '2026-09-01T00:00:00Z' },
      ];
    });
    const only = fixtureTree((fx) => {
      fx.releases['embed:zed'] = [
        { version: '2.1.0', published: '2026-10-01T00:00:00Z', breaking: brk },
        { version: '2.0.0', published: '2026-09-01T00:00:00Z' },
      ];
    });
    type PlanJson = { plans: Array<{ id: string; to: string }> };
    const plain = await runCli(['plan', 'embed:zed', '--json'], withMutant(mixed, m));
    const named = await runCli(['plan', 'embed:zed', '--to', '2.1.0'], withMutant(mixed, m));
    const major = await runCli(
      ['plan', 'embed:zed', '--major', '--reason', 'operator ruling', '--json'],
      withMutant(only, m)
    );
    const st = await runCli(['status', 'embed:zed', '--json'], withMutant(mixed, m));
    const so = await runCli(['status', 'embed:zed', '--json'], withMutant(only, m));
    const soaked = await runCli(
      ['apply-soaked', '--json', '--out', path.join(only.root, 'out')],
      withMutant(only, m)
    );
    const toOf = (r: { rc: number; out: string }): string | undefined =>
      r.rc === 0
        ? (JSON.parse(r.out) as PlanJson).plans.find((p) => p.id === 'embed:zed')?.to
        : undefined;
    const vs = st.rc === 0 ? (JSON.parse(st.out) as { pins: PinView[] }).pins[0] : null;
    const vo = so.rc === 0 ? (JSON.parse(so.out) as { pins: PinView[] }).pins[0] : null;
    return [
      {
        // Red under breaking-is-minor: the plain plan takes 2.1.0.
        name: 'breaking: a plain plan takes the same-line patch, never the breaking line above it',
        ok: toOf(plain) === '2.0.1',
        detail: `rc=${plain.rc} ${plain.err} ${plain.out.slice(0, 400)}`,
      },
      {
        // Red under breaking-is-minor: --to 2.1.0 plans without --major.
        name: 'breaking: a plain bump naming the breaking release is refused, naming --major and the driver why',
        ok:
          named.rc === 1 &&
          named.err.includes('REFUSED embed:zed') &&
          named.err.includes('--major --reason') &&
          named.err.includes('changes the go directive of every go.mod'),
        detail: `rc=${named.rc} ${named.err}`,
      },
      {
        // Red under breaking-is-minor: isMajor false makes takesMajor false, and --major is refused as taking no major.
        name: 'breaking: --major --reason plans the breaking line',
        ok: toOf(major) === '2.1.0',
        detail: `rc=${major.rc} ${major.err} ${major.out.slice(0, 400)}`,
      },
      {
        // Red under breaking-unlisted (majors empty) and breaking-is-minor (2.1.0 is the target, no eligible major).
        name: 'breaking: status reports the breaking line as a pending major beside the plain patch',
        ok:
          vs !== null &&
          vs.state === 'bumpable' &&
          vs.target?.version === '2.0.1' &&
          vs.eligibleMajors.join() === '2.1.0' &&
          vs.majors.length === 1 &&
          vs.majors[0].line === '2.1' &&
          vs.majors[0].newest === '2.1.0',
        detail: JSON.stringify(vs),
      },
      {
        // Red under breaking-is-minor: the pin reads as bumpable.
        name: 'breaking: with only the breaking line newer, status says major-only with the --major line and the why, not eligible',
        ok:
          vo !== null &&
          vo.state === 'major-only' &&
          vo.target === null &&
          vo.detail.includes('--major --reason') &&
          vo.detail.includes('changes the go directive of every go.mod'),
        detail: JSON.stringify(vo),
      },
      {
        // Red under breaking-is-minor: inRange reads 2.0 -> 2.1 as an in-range minor and apply-soaked moves it.
        name: 'breaking: apply-soaked leaves the breaking line',
        ok: soaked.rc === 0 && only.read('private/renet/Dockerfile').includes('ZED_VERSION=2.0.0'),
        detail: `rc=${soaked.rc} ${soaked.err} ${only.read('private/renet/Dockerfile')}`,
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
      lockMisMoveCase(fx.root),
      lockNoHardLinkCase(fx.root),
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
          rep.commands.some((c) =>
            c.cmd.startsWith('npm run ci -- --only check:fixture-tool,check:fixture-zed --events ')
          ),
        detail: `rc=${r.rc} ${r.err}`,
      },
    ];
  },
  async multi(m) {
    const fx = fixtureTree();
    const r = await runCli(['bump', 'embed:tool', 'embed:zed', '--json'], withMutant(fx, m));
    const rep =
      r.rc === 0
        ? (JSON.parse(r.out) as { pins: Array<{ id: string }>; commands: CommandRecord[] })
        : null;
    const dup = await runCli(['bump', 'embed:tool', 'embed:tool'], withMutant(fixtureTree(), m));
    const unk = await runCli(['bump', 'embed:tool', 'embed:nope'], withMutant(fixtureTree(), m));
    const one = await runCli(['bump', 'embed:tool', '--json'], withMutant(fixtureTree(), m));
    return [
      {
        // Red when only the first positional id is read.
        name: 'bump <id> <id>: both pins plan into one transaction, one gate run',
        ok:
          rep !== null &&
          rep.pins.length === 2 &&
          rep.commands.filter((c) => c.cmd.startsWith('npm run ci -- --only ')).length === 1,
        detail: `rc=${r.rc} ${r.err}`,
      },
      {
        // Red when duplicates collapse silently.
        name: 'bump: a duplicate id is refused by name',
        ok: dup.rc !== 0 && dup.err.includes('embed:tool'),
        detail: `rc=${dup.rc} ${dup.err}`,
      },
      {
        // Red when an unknown trailing id is skipped.
        name: 'bump: an unknown id among several is refused by name',
        ok: unk.rc !== 0 && unk.err.includes('no pin embed:nope'),
        detail: `rc=${unk.rc} ${unk.err}`,
      },
      {
        name: 'bump: the single-id form still plans exactly one pin',
        ok: one.rc === 0 && (JSON.parse(one.out) as { pins: unknown[] }).pins.length === 1,
        detail: `rc=${one.rc} ${one.err}`,
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
  async onrecord(m) {
    // A pin an unnamed run could never compare for a reason already on record: a `source: none` leaf and a family-gated leaf no driver serves. apply-soaked skips both and stays green; naming either still refuses (fail closed).
    const build = (): Fx => {
      const fx = fixtureTree();
      const file = path.join(fx.root, '.ci/config/pins.json');
      const reg = JSON.parse(fs.readFileSync(file, 'utf8')) as {
        entries: Record<string, unknown>[];
      };
      const base = reg.entries.find((e) => e.id === 'embed:tool') as Record<string, unknown>;
      reg.entries.push({
        ...base,
        id: 'embed:nosource',
        name: 'nosource',
        source: {
          type: 'none',
          reason: 'BLOCKER: the upstream publishes on a host no pins source type reads',
        },
        gates: ['check:fixture-nosource'],
        sites: [
          { repo: '.', file: 'Dockerfile', role: 'version', expect: 1, arg: 'NOSRC_VERSION' },
        ],
      });
      reg.entries.push({
        ...base,
        id: 'breakpoint:copy',
        name: 'copy',
        driver: 'breakpoint',
        gates: ['check:ci-breakpoint-drift'],
        sites: [{ repo: '.', file: 'Dockerfile', role: 'version', expect: 1, arg: 'COPY_VERSION' }],
      });
      fs.writeFileSync(file, `${JSON.stringify(reg, null, 2)}\n`);
      fs.appendFileSync(
        path.join(fx.root, 'Dockerfile'),
        'ARG NOSRC_VERSION=1.0.0\nARG COPY_VERSION=1.0.0\n'
      );
      // Committed, so the run's transaction sees a clean tree rather than changes it did not make.
      sh(
        fx.root,
        '-c',
        'user.email=fx@example.invalid',
        '-c',
        'user.name=fx',
        'commit',
        '-qam',
        'on-record pins'
      );
      return fx;
    };
    const all = build();
    const r = await runCli(['apply-soaked', '--json'], withMutant(all, m));
    const j = JSON.parse(r.out || '{}') as {
      refused?: Array<{ id: string }>;
      skipped?: Array<{ id: string }>;
    };
    const skippedIds = (j.skipped ?? []).map((x) => x.id);
    const refusedIds = (j.refused ?? []).map((x) => x.id);
    const named = await runCli(['bump', 'embed:nosource', '--json'], withMutant(build(), m));
    return [
      {
        name: 'apply-soaked: a source-none leaf and a driverless family-gated leaf are skipped, not refused, so the run stays green',
        ok:
          r.rc === 0 &&
          skippedIds.includes('embed:nosource') &&
          skippedIds.includes('breakpoint:copy') &&
          !refusedIds.includes('embed:nosource') &&
          !refusedIds.includes('breakpoint:copy'),
        detail: `rc=${r.rc} skipped=${skippedIds.join(',')} refused=${refusedIds.join(',')} ${r.err}`,
      },
      {
        name: 'bump <id>: a source-none pin named on the command line is still refused',
        ok: named.rc === 1,
        detail: `rc=${named.rc} ${named.err}`,
      },
    ];
  },
  async notchecked(m) {
    // The npm family has no fixture entry, so it is NOT COMPARED; whether that is a refusal or NOT-CHECKED turns on private/renet, which its scope now reaches, being checked out.
    const build = (declared = 'private/renet'): Fx => {
      const fx = fixtureTree(() => {}, true);
      const file = path.join(fx.root, '.ci/config/pins.json');
      const reg = JSON.parse(fs.readFileSync(file, 'utf8')) as {
        entries: Array<{ id: string; scope?: object[] }>;
      };
      reg.entries = reg.entries.filter((e) => e.id !== 'embed:zed');
      reg.entries
        .find((e) => e.id === 'npm')
        ?.scope?.push({
          scanner: 'npm-lockfile',
          repo: 'private/renet',
          files: ['package-lock.json'],
        });
      fs.writeFileSync(file, `${JSON.stringify(reg, null, 2)}\n`);
      fs.writeFileSync(
        path.join(fx.root, '.gitmodules'),
        `[submodule "${declared}"]\n\tpath = ${declared}\n\turl = x\n`
      );
      return fx;
    };
    const present = build();
    const absent = build();
    const human = build();
    // An undeclared registry path is a plain empty directory, not an absent submodule.
    const undeclared = build('private/other');
    const named = build();
    for (const t of [absent, human, undeclared, named]) {
      fs.rmSync(path.join(t.root, 'private/renet'), { recursive: true });
      fs.mkdirSync(path.join(t.root, 'private/renet'));
    }
    const rh = await runCli(['apply-soaked'], withMutant(human, m));
    const rp = await runCli(['apply-soaked', '--json'], withMutant(present, m));
    const ra = await runCli(['apply-soaked', '--json'], withMutant(absent, m));
    const parse = (o: string) =>
      JSON.parse(o) as {
        refused: Array<{ id: string }>;
        not_checked?: Array<{ id: string; submodules: string[] }>;
      };
    const jp = parse(rp.out);
    const ja = parse(ra.out);
    const ru = await runCli(['apply-soaked', '--json'], withMutant(undeclared, m));
    const ju = parse(ru.out);
    const rn = await runCli(['bump', 'npm'], withMutant(named, m));
    // A declared submodule path may contain a space: `path = <value>` is read whole, not up to the first blank.
    const spacedRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-gitmodules-'));
    fs.writeFileSync(
      path.join(spacedRoot, '.gitmodules'),
      '[submodule "a"]\n\tpath = private/re net\n\turl = x\n[submodule "b"]\n\tpath = private/other\n\turl = y\n'
    );
    const spaced = [...declaredSubmodules(spacedRoot)].sort();
    fs.rmSync(spacedRoot, { recursive: true });
    return [
      {
        // Red when the `path =` pattern stops at the first whitespace, cutting `private/re net` to `private/re`.
        name: 'gitmodules: a declared submodule path containing a space is read whole',
        ok: JSON.stringify(spaced) === JSON.stringify(['private/other', 'private/re net']),
        detail: JSON.stringify(spaced),
      },
      {
        // Red when a registry path .gitmodules does not declare is treated as an absent submodule.
        name: 'apply-soaked: a pin reading an empty directory that .gitmodules does not declare is refused, not not_checked',
        ok:
          ru.rc !== 0 &&
          ju.refused.some((r) => r.id === 'npm') &&
          (ju.not_checked ?? []).length === 0,
        detail: `rc=${ru.rc} ${ru.err}`,
      },
      {
        // Red when an explicitly named pin on an absent submodule is reported not-checked instead of refused.
        name: 'bump: an explicitly named pin reading an absent submodule is refused and fails the run',
        ok: rn.rc !== 0 && !/NOT-CHECKED/.test(rn.err),
        detail: `rc=${rn.rc} ${rn.err}`,
      },
      {
        // Red when an absent submodule still fails the run, or leaves the pin out of the report.
        name: 'apply-soaked: a pin reading an absent submodule is not_checked and leaves the exit code alone',
        ok:
          ra.rc === 0 &&
          ja.refused.length === 0 &&
          ja.not_checked?.length === 1 &&
          ja.not_checked[0].id === 'npm' &&
          ja.not_checked[0].submodules[0] === 'private/renet',
        detail: `rc=${ra.rc} ${ra.err} ${JSON.stringify([ja.refused, ja.not_checked])}`,
      },
      {
        name: 'apply-soaked: the human output names the NOT-CHECKED pin and its submodule, and exits 0',
        ok: rh.rc === 0 && /NOT-CHECKED npm: private\/renet not checked out/.test(rh.err),
        detail: `rc=${rh.rc} ${rh.err}`,
      },
      {
        // Red when the submodule being present stops mattering: the same refusal must still fail the run.
        name: 'apply-soaked: the same pin with its submodule checked out is still refused and fails the run',
        ok:
          rp.rc !== 0 &&
          jp.refused.some((r) => r.id === 'npm') &&
          (jp.not_checked ?? []).length === 0,
        detail: `rc=${rp.rc} ${rp.err}`,
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
    // An expired hold renewed: the line is replaced, not followed by a second one the reader would never reach.
    const fx2 = fixtureTree();
    const header = fx2.read('.ci/policy/.fixture-blocklist');
    fx2.write(
      '.ci/policy/.fixture-blocklist',
      `${header}tool  # BLOCKER: tool 1.1 changes the archive layout the installer unpacks (expires 2026-10-01)\n`
    );
    sh(fx2.root, 'add', '-A');
    sh(
      fx2.root,
      '-c',
      'user.email=fx@example.invalid',
      '-c',
      'user.name=fx',
      'commit',
      '-qm',
      'expired hold'
    );
    const renew = await runCli(
      [
        'hold',
        'embed:tool',
        '--reason',
        'tool 1.1 still changes the archive layout the installer unpacks',
        '--expires',
        '2026-12-01',
      ],
      withMutant(fx2, m)
    );
    const st2 = await runCli(['status', 'embed:tool', '--json'], withMutant(fx2, m));
    const v2 = st2.rc === 0 ? (JSON.parse(st2.out) as { pins: PinView[] }).pins[0] : null;
    const held = fx2.read('.ci/policy/.fixture-blocklist');
    return [
      {
        name: 'hold: an expired hold is renewed in place, one line for the key, and status reads it held',
        ok:
          renew.rc === 0 &&
          held.split('\n').filter((l) => l.startsWith('tool ')).length === 1 &&
          held.includes('(expires 2026-12-01)') &&
          v2?.state === 'held' &&
          v2.hold?.expires === '2026-12-01',
        detail: `${renew.rc} ${renew.err} | ${v2?.state} | ${held}`,
      },
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
  async regen(m) {
    const regenCmd = {
      match: 'gen-docs\\.ts --write$',
      rc: 0,
      writes: { 'docs/generated.md': 'rows: 6\n' } as Record<string, string>,
      out: 'wrote docs/generated.md (fixture-rows)\n',
    };
    const branchOf = (fx: Fx): string =>
      (
        spawnSync('git', ['-C', fx.root, 'rev-parse', '--abbrev-ref', 'HEAD'], { encoding: 'utf8' })
          .stdout ?? ''
      ).trim();
    const snapshot = (fx: Fx, ids: string[]): void => {
      fs.mkdirSync(path.join(fx.root, 'agent/pr'), { recursive: true });
      fs.writeFileSync(
        path.join(fx.root, 'agent/pr', `${branchOf(fx)}.md`),
        ids.map((i) => `\`PR-TASK: ${i}\``).join('\n\n') + '\n'
      );
    };
    const hold = (fx: Fx) =>
      runCli(
        [
          'hold',
          'embed:tool',
          '--reason',
          'tool 1.1 changes the archive layout the installer unpacks',
        ],
        withMutant(fx, m)
      );
    const draftOf = (out: string): string => {
      const f = /commit -F (\S+)/.exec(out)?.[1];
      return f ? fs.readFileSync(f, 'utf8') : '';
    };

    const fx = fixtureTree((x) => x.commands.push(regenCmd));
    snapshot(fx, ['cafe1234']);
    const r = await hold(fx);
    const msg = draftOf(r.out);

    const two = fixtureTree((x) => x.commands.push(regenCmd));
    snapshot(two, ['cafe1234', 'beef5678']);
    const rTwo = await hold(two);

    // A region file another session already edited is regenerated too, but is not this commit's to carry.
    const peer = fixtureTree((x) => x.commands.push(regenCmd));
    peer.write('docs/generated.md', 'rows: 5, and a peer is mid-edit\n');
    const rPeer = await hold(peer);

    // A file this run wrote is the run's own even when regeneration moves it again.
    const own = fixtureTree((x) =>
      x.commands.push({
        ...regenCmd,
        writes: { '.ci/policy/.fixture-blocklist': 'regenerated\n' },
        out: 'wrote .ci/policy/.fixture-blocklist (fixture-rows)\n',
      })
    );
    const rOwn = await hold(own);

    // Another writer in the tree adds a file while the generator runs (the per-commit reviewer's record, 2026-10-15): the tree diff sees it, the generator's `wrote` lines do not name it, so it is not the run's.
    const stray = fixtureTree((x) =>
      x.commands.push({
        ...regenCmd,
        writes: {
          'docs/generated.md': 'rows: 6\n',
          'agent/reviews/1008-1/abc.md': 'a review another process wrote\n',
        },
      })
    );
    const rStray = await hold(stray);

    const late = fixtureTree((x) => x.commands.push(regenCmd));
    const rLate = await runCli(['bump', 'embed:tool', '--task', 'cafe1234'], withMutant(late, m));
    const lateBase = fixtureTree();
    const rLateBase = await runCli(
      ['bump', 'embed:tool', '--task', 'cafe1234'],
      withMutant(lateBase, m)
    );

    const bad = fixtureTree((x) => x.commands.push({ ...regenCmd, rc: 1 }));
    const rBad = await hold(bad);

    const plain = fixtureTree();
    const rPlain = await hold(plain);

    return [
      {
        name: 'hold: the generated docs it moves are regenerated, listed in the commit line and the draft, and the epic of the branch is the trailer',
        ok:
          r.rc === 0 &&
          fx.read('docs/generated.md') === 'rows: 6\n' &&
          r.out.includes('add -- docs/generated.md') &&
          /commit -F \S+ -- .*docs\/generated\.md/.test(r.out) &&
          /commit -F \S+ -- .*\.fixture-blocklist/.test(r.out) &&
          msg.includes('Ran: npx tsx scripts/gen/gen-docs.ts --write') &&
          msg.trimEnd().endsWith('PR-TASK: cafe1234') &&
          !r.out.includes('no --task given'),
        detail: `rc=${r.rc} ${r.err} ${r.out}\n${msg}`,
      },
      {
        name: 'hold: a branch snapshot naming two epics gives no trailer and the note names both ids',
        ok:
          rTwo.rc === 0 &&
          rTwo.out.includes('cafe1234, beef5678') &&
          !draftOf(rTwo.out).includes('PR-TASK:'),
        detail: `rc=${rTwo.rc} ${rTwo.err} ${rTwo.out}`,
      },
      {
        name: 'hold: a regenerated file that already held a peer session edit is reported and kept out of the commit line',
        ok:
          rPeer.rc === 0 &&
          rPeer.err.includes('docs/generated.md was regenerated but already held') &&
          !/commit -F \S+ -- .*docs\/generated\.md/.test(rPeer.out),
        detail: `rc=${rPeer.rc} ${rPeer.err} ${rPeer.out}`,
      },
      {
        name: 'hold: a file the run wrote itself is not reported as holding another session edit, and stays in the commit line',
        ok:
          rOwn.rc === 0 &&
          !rOwn.err.includes('already held') &&
          /commit -F \S+ -- .*\.fixture-blocklist/.test(rOwn.out),
        detail: `rc=${rOwn.rc} ${rOwn.err} ${rOwn.out}`,
      },
      {
        name: 'hold: a file another writer adds during the regeneration is named and kept out of the add and commit lines, while the generated doc stays in',
        ok:
          rStray.rc === 0 &&
          !rStray.out.includes('agent/reviews') &&
          /commit -F \S+ -- .*docs\/generated\.md/.test(rStray.out) &&
          rStray.err.includes(
            'note: agent/reviews/1008-1/abc.md changed while the generated docs were regenerated, but the generator did not report writing it'
          ),
        detail: `rc=${rStray.rc} ${rStray.err} ${rStray.out}`,
      },
      {
        name: 'bump: a doc regenerated after the gates ran is named as unseen by them',
        ok:
          rLate.rc === 0 &&
          rLate.err.includes('docs/generated.md was regenerated after the gates ran') &&
          rLateBase.rc === 0 &&
          !rLateBase.err.includes('after the gates ran'),
        detail: `rc=${rLate.rc} ${rLate.err} | plain bump rc=${rLateBase.rc} ${rLateBase.err}`,
      },
      {
        name: 'hold: a failing regeneration fails the run loudly and drafts no commit line',
        ok:
          rBad.rc === 1 &&
          rBad.err.includes('gen-docs.ts --write failed') &&
          !rBad.out.includes('commit -F'),
        detail: `rc=${rBad.rc} ${rBad.err} ${rBad.out}`,
      },
      {
        name: 'hold: a tree with no generator skips the regeneration and still drafts the blocklist commit',
        ok:
          rPlain.rc === 0 &&
          /commit -F \S+ -- \.ci\/policy\/\.fixture-blocklist$/m.test(rPlain.out),
        detail: `rc=${rPlain.rc} ${rPlain.err} ${rPlain.out}`,
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
  async setmajor(m) {
    // The 2026-10-15 deadlock in fixture form: a held major (`held`, what check:deps reds on as awaiting a decision) and the in-range batch pending in the npm family at once, beside a blocklisted major that is held on purpose.
    const OLD = '2026-10-01T00:00:00Z';
    type Rel = { version: string; published: string | null; held?: boolean };
    const world = (releases: Rel[], inRange: string | null = '1.2') =>
      fixtureTree((f) => {
        f.commands.unshift({ match: '^npm run ci -- --only check:fixture-deps ', rc: 0 });
        f.families = { npm: { current: '1.0', inRange, releases } };
      }, true);
    const IN: Rel = { version: '1.2', published: OLD };
    const OXC: Rel = { version: 'oxc@0.154', published: OLD, held: true };
    const VITE: Rel = { version: 'vite@8', published: OLD, held: true };
    const TYPES: Rel = { version: 'types@26', published: OLD };
    const moved = (fx: Fx): string | null =>
      fs.existsSync(path.join(fx.root, 'families/npm.txt')) ? fx.read('families/npm.txt') : null;
    const reason = ['--reason', 'oxc-parser 0.154 is a parser-only release the lint tree absorbs'];
    const toLine = (...keys: string[]): string =>
      `npm run pins -- bump npm ${keys.map((k) => `--to ${k}`).join(' ')} --major --reason`;

    // (1) --to <held major> --major: one run, the in-range batch rides it, and it writes nothing else (no allow entry).
    const both = world([IN, OXC, TYPES]);
    const rBoth = await runCli(
      ['bump', 'npm', '--to', 'oxc@0.154', '--major', ...reason, '--json'],
      withMutant(both, m)
    );
    const bothRep =
      rBoth.rc === 0 ? (JSON.parse(rBoth.out) as { repos: Array<{ paths: string[] }> }) : null;
    // (2) --major with no --to: refused before any write, with the --to line.
    const bare = world([IN, OXC, TYPES]);
    const rBare = await runCli(['bump', 'npm', '--major', ...reason], withMutant(bare, m));
    // (3) a plain bump with a held major pending: refused before any write.
    const plain = world([IN, OXC, TYPES]);
    const rPlain = await runCli(['bump', 'npm'], withMutant(plain, m));
    // (4) CONTROL: a blocklisted major alone never forces the refusal; the in-range batch applies.
    const blocked = world([IN, TYPES]);
    const rBlocked = await runCli(['bump', 'npm'], withMutant(blocked, m));
    // (5) two held majors: naming one is refused with both; naming both moves both.
    const two = world([IN, OXC, VITE]);
    const rOne = await runCli(
      ['bump', 'npm', '--to', 'oxc@0.154', '--major', ...reason],
      withMutant(two, m)
    );
    const movedAfterOne = moved(two);
    const rTwo = await runCli(
      ['bump', 'npm', '--to', 'oxc@0.154', '--to', 'vite@8', '--major', ...reason],
      withMutant(two, m)
    );
    // (6) bump --all: the other pins move, npm is REFUSED by name.
    const all = world([IN, OXC]);
    const rAll = await runCli(['bump', '--all'], withMutant(all, m));
    // (7) a family of [1.N, 2.M] with no held mark: --major must not exit 0 having planned only 1.N.
    const fam = world([IN, { version: '2.1', published: OLD }]);
    const rFam = await runCli(['bump', 'npm', '--major', ...reason], withMutant(fam, m));
    // The same rule for a leaf: --major whose newest eligible release is a minor.
    const leaf = fixtureTree();
    const rLeaf = await runCli(['bump', 'embed:tool', '--major', ...reason], withMutant(leaf, m));
    return [
      {
        name: 'bump npm --to <held major> --major: one run takes the major AND the in-range batch, writes no allow entry, and its gates pass',
        ok:
          rBoth.rc === 0 &&
          moved(both) === '1.2\noxc@0.154\n' &&
          bothRep !== null &&
          JSON.stringify(bothRep.repos.map((r) => r.paths)) === '[["families/npm.txt"]]',
        detail: `rc=${rBoth.rc} moved=${JSON.stringify(moved(both))} ${rBoth.err} ${rBoth.out.slice(0, 600)}`,
      },
      {
        name: 'bump npm --major with no --to is refused before any write, printing the --to line of the held major',
        ok: rBare.rc === 1 && rBare.err.includes(toLine('oxc@0.154')) && moved(bare) === null,
        detail: `rc=${rBare.rc} moved=${JSON.stringify(moved(bare))} ${rBare.err}`,
      },
      {
        name: 'bump npm with a held major pending is refused before any write, naming the line that clears it',
        ok:
          rPlain.rc === 1 &&
          rPlain.err.includes('REFUSED npm') &&
          rPlain.err.includes(toLine('oxc@0.154')) &&
          moved(plain) === null,
        detail: `rc=${rPlain.rc} ${rPlain.err}`,
      },
      {
        name: 'CONTROL: a blocklisted major alone does not block the in-range batch, which applies',
        ok: rBlocked.rc === 0 && moved(blocked) === '1.2\n',
        detail: `rc=${rBlocked.rc} moved=${JSON.stringify(moved(blocked))} ${rBlocked.err}`,
      },
      {
        name: 'two held majors: naming one is refused with the line naming both, naming both moves both with the batch',
        ok:
          rOne.rc === 1 &&
          rOne.err.includes(toLine('oxc@0.154', 'vite@8')) &&
          movedAfterOne === null &&
          rTwo.rc === 0 &&
          moved(two) === '1.2\noxc@0.154\nvite@8\n',
        detail: `one rc=${rOne.rc} ${rOne.err} | two rc=${rTwo.rc} moved=${JSON.stringify(moved(two))} ${rTwo.err}`,
      },
      {
        name: 'bump --all with a held npm major moves every other pin and reports npm REFUSED',
        ok:
          rAll.rc === 1 &&
          rAll.err.includes('REFUSED npm') &&
          rAll.err.includes(toLine('oxc@0.154')) &&
          moved(all) === null &&
          all.read('Dockerfile').includes('TOOL_VERSION=1.1.0') &&
          all.read('private/renet/Dockerfile').includes('ZED_VERSION=2.1.0'),
        detail: `rc=${rAll.rc} ${rAll.err} ${rAll.out}`,
      },
      {
        name: 'a family of [1.N, 2.M] given --major never exits 0 having planned only 1.N; the refusal names --to 2.1',
        ok: rFam.rc !== 0 && moved(fam) === null && rFam.err.includes(toLine('2.1')),
        detail: `rc=${rFam.rc} moved=${JSON.stringify(moved(fam))} ${rFam.err}`,
      },
      {
        name: 'a leaf given --major whose newest eligible release is a minor is refused, and nothing is written',
        ok:
          rLeaf.rc === 1 &&
          rLeaf.err.includes('selection takes no major') &&
          leaf.read('Dockerfile').includes('TOOL_VERSION=1.0.0'),
        detail: `rc=${rLeaf.rc} ${rLeaf.err}`,
      },
    ];
  },
  async gatenames(m) {
    // RED comes from the runner's event rows; the text carries an ok line for the passing gate, and the failed gate's own stdout holds a verdict-shaped line that must not count.
    const runnerOut = [
      '  ok    check:fixture-zed       49.8s',
      '\x1b[31mFAIL\x1b[0m  check:fixture-tool      62.4s   exit 1',
      '  --- stdout ---',
      '  ok    check:fixture-tool  (a line the gate itself printed)',
      'FAILED:',
      '  check:fixture-tool      npm run check:fixture-tool',
    ].join('\n');
    const red = (gate: string): string =>
      JSON.stringify({ ev: 'gate-red', run: 'r', gate, t_ms: 1, rerun: `npm run ${gate}` });
    const fx = fixtureTree((f) => {
      f.commands[0] = {
        match: '^npm run ci -- --only ',
        rc: 1,
        out: runnerOut,
        events: [JSON.stringify({ ev: 'run-start' }), red('check:fixture-tool')],
      };
    });
    const r = await runCli(['bump', '--all', '--json'], withMutant(fx, m));
    // zed's registry entry also names check:fixture-tool, so a single-id bump of tool that turns it red names zed and the joint command.
    const shared = fixtureTree((f) => {
      f.commands[0] = {
        match: '^npm run ci -- --only ',
        rc: 1,
        out: runnerOut,
        events: [JSON.stringify({ ev: 'run-start' }), red('check:fixture-tool')],
      };
    });
    const regFile = path.join(shared.root, '.ci/config/pins.json');
    const regJson = JSON.parse(fs.readFileSync(regFile, 'utf8')) as {
      entries: Array<{ id: string; gates: string[] }>;
    };
    regJson.entries.find((e) => e.id === 'embed:zed')?.gates.push('check:fixture-tool');
    fs.writeFileSync(regFile, `${JSON.stringify(regJson, null, 2)}\n`);
    const rs = await runCli(['bump', 'embed:tool'], withMutant(shared, m));
    const rjoint = await runCli(['bump', '--all'], withMutant(shared, m));
    const rep = JSON.parse(r.out) as {
      failure: string;
      gates: { failed: string[] };
      commands: CommandRecord[];
    };
    // CONTROL: a red run whose event stream carries no red row blames no gate.
    const quiet = fixtureTree((f) => {
      f.commands[0] = { match: '^npm run ci -- --only ', rc: 1, out: runnerOut, events: [] };
    });
    const rq = await runCli(['bump', '--all'], withMutant(quiet, m));
    return [
      {
        name: 'bump: the FAILED line names only the gate the runner reported red, the passing one as ok, and gates.failed carries it',
        ok:
          r.rc === 1 &&
          rep.failure === 'gates failed (rc=1): check:fixture-tool (ok: check:fixture-zed)' &&
          JSON.stringify(rep.gates.failed) === '["check:fixture-tool"]' &&
          rep.commands.some((c) => / --events \/\S+\/gates\.jsonl$/.test(c.cmd)),
        detail: `rc=${r.rc} failure=${rep.failure} failed=${JSON.stringify(rep.gates?.failed)}`,
      },
      {
        // Red when siblingHint is dropped, reads gate output instead of the registry, or loses its --to / --major --reason guidance.
        name: 'bump: a red gate shared with a pin the run did not move names that sibling and the joint command shape',
        ok:
          rs.rc === 1 &&
          rs.err.includes('check:fixture-tool also judges embed:zed') &&
          rs.err.includes('npm run pins -- bump embed:tool <each behind sibling>') &&
          rs.err.includes("(with the run's --to, and --major --reason when a move is a major)"),
        detail: rs.err,
      },
      {
        // Red when the hint ignores which pins were moved (names pins the run already moved).
        name: 'CONTROL: when the run moved every pin sharing the red gate, no sibling line is added',
        ok: rjoint.rc === 1 && !/also judge/.test(rjoint.err),
        detail: rjoint.err,
      },
      {
        name: 'CONTROL: a red run with no gate-red row says no gate reported red, and names none as failed',
        ok:
          rq.rc === 1 &&
          rq.err.includes(
            'gates failed (rc=1): no gate reported red; see commands.log (ok: check:fixture-zed; no verdict: check:fixture-tool)'
          ) &&
          !rq.err.includes('check:fixture-tool,') &&
          !/: check:fixture-tool[ ,]/.test(rq.err),
        detail: rq.err,
      },
    ];
  },
  async drift() {
    const lock = JSON.stringify({
      packages: {
        '': { name: 'x' },
        'node_modules/a': { version: '1.0.0' },
        'node_modules/b': { version: '2.0.0' },
        'node_modules/@esbuild/win32-x64': { version: '0.25.0', optional: true },
        'node_modules/@rediacc/cli': { resolved: 'packages/cli', link: true },
        'packages/cli/node_modules/c': { version: '3.0.0' },
      },
    });
    const same = JSON.stringify({
      packages: {
        'node_modules/a': { version: '1.0.0' },
        'node_modules/b': { version: '2.0.0' },
        'node_modules/@rediacc/cli': { resolved: 'packages/cli', link: true },
        'packages/cli/node_modules/c': { version: '3.0.0' },
      },
    });
    const moved = JSON.stringify({
      packages: {
        'node_modules/a': { version: '1.0.0' },
        'node_modules/b': { version: '2.1.0' },
        'packages/cli/node_modules/c': { version: '3.0.1' },
      },
    });
    const clean = lockDrift(lock, same, [
      'node_modules/a',
      'node_modules/b',
      'node_modules/@rediacc/cli',
    ]);
    const found = lockDrift(lock, moved);
    // A package a failed run installed and the restore took out of the lockfile: listed by the hidden lockfile, or (after a lockfile-only pass rewrote that) present only on disk.
    const extra = JSON.stringify({
      packages: {
        'node_modules/a': { version: '1.0.0' },
        'node_modules/zz': { version: '9.0.0' },
        'node_modules/@rediacc/shared': { resolved: 'packages/shared', link: true },
      },
    });
    const extraFound = lockDrift(lock, extra);
    const diskFound = lockDrift(lock, same, ['node_modules/a', 'node_modules/@x/stale']);
    return [
      {
        name: 'drift: an installed version the lockfile does not name is found, nested ones too',
        ok:
          found.length === 2 &&
          found.includes('b installed 2.1.0, locked 2.0.0') &&
          found.includes('c installed 3.0.1, locked 3.0.0'),
        detail: JSON.stringify(found),
      },
      {
        name: 'drift: an installed package the lockfile does not name is extraneous, from the hidden lockfile and from node_modules on disk; a workspace link the lockfile omits is not',
        ok:
          extraFound.length === 1 &&
          extraFound[0] === 'zz installed 9.0.0, not in the lockfile' &&
          diskFound.length === 1 &&
          diskFound[0] === '@x/stale present in node_modules, not in the lockfile',
        detail: `${JSON.stringify(extraFound)} ${JSON.stringify(diskFound)}`,
      },
      (() => {
        // Review f56ddcde.1: a lockfileVersion 1 file has no packages map, which read every installed package as extraneous.
        const v1 = lockDrift(JSON.stringify({ lockfileVersion: 1, dependencies: {} }), same, [
          'node_modules/a',
        ]);
        const nul = lockDrift(JSON.stringify({ lockfileVersion: 3, packages: null }), same);
        const arr = lockDrift(JSON.stringify({ lockfileVersion: 3, packages: [] }), same);
        return {
          name: 'drift: a lockfile with no packages map (absent or null) is one finding naming the rewrite, and a packages value of the wrong type (an array) is one finding calling it malformed, not one per installed package',
          ok:
            v1.length === 1 &&
            v1[0].includes('no packages map (lockfileVersion 1)') &&
            nul.length === 1 &&
            nul[0].includes('no packages map') &&
            arr.length === 1 &&
            arr[0].includes('packages map is malformed') &&
            !arr[0].includes('no packages map'),
          detail: `${JSON.stringify(v1)} ${JSON.stringify(nul)} ${JSON.stringify(arr)}`,
        };
      })(),
      {
        name: 'CONTROL: drift: a tree installed from its lockfile, with another platform optional package absent and a workspace link, is clean',
        ok: clean.length === 0,
        detail: JSON.stringify(clean),
      },
    ];
  },
  async resync(m) {
    // A red run that restored the root lockfile puts the installed tree back to it (npm ci and install:natives AFTER the gates), so the next plan reads the versions the lockfile names.
    const fx = fixtureTree((f) => {
      f.commands[0].rc = 1;
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
    const lock = fx.read('package-lock.json');
    const r = await runCli(['bump', 'embed:tool', '--json'], withMutant(fx, m));
    const rep = JSON.parse(r.out) as { commands: CommandRecord[]; resynced: string[] };
    const cmds = rep.commands.map((c) => c.cmd);
    const gate = cmds.findIndex((c) => c.startsWith('npm run ci -- --only'));
    const after = gate < 0 ? [] : cmds.slice(gate + 1);
    return [
      {
        name: 'bump: a red run that restored the root lockfile reinstalls the tree from it (npm ci, install:natives) after the restore',
        ok:
          r.rc === 1 &&
          fx.read('package-lock.json') === lock &&
          after[0] === 'npx -y npm@11.20.0 ci' &&
          after[1] === 'npx -y npm@11.20.0 run install:natives' &&
          rep.resynced.includes('.'),
        detail: `rc=${r.rc} after-gate=${after.join(' | ')} resynced=${rep.resynced}`,
      },
    ];
  },
  async refusals(m) {
    const fx = fixtureTree();
    const live = await runCli(['status'], { PINS_MUTANT: 'no-restore' });
    const major = await runCli(['bump', 'embed:tool', '--major'], withMutant(fx, m));
    const verb = await runCli(['frobnicate'], withMutant(fx, m));
    const emptyTo = await runCli(['bump', 'embed:tool', '--to', ''], withMutant(fx, m));
    const commaTo = await runCli(['bump', 'embed:tool', '--to', ','], withMutant(fx, m));
    const strayVerify = await runCli(['verify', '--inflight', 'credits.json'], withMutant(fx, m));
    const strayBump = await runCli(
      ['bump', 'embed:tool', '--inflight', 'credits.json'],
      withMutant(fx, m)
    );
    return [
      {
        name: 'a mutant outside a fixture is refused',
        ok: live.rc === 2 && live.err.includes('refused'),
        detail: live.err,
      },
      { name: '--major without --reason is refused', ok: major.rc === 2, detail: major.err },
      { name: 'an unknown verb is a usage error', ok: verb.rc === 2, detail: verb.err },
      {
        name: 'an empty --to ("" or ",") is a usage error, not a plain bump, and nothing is written',
        ok:
          emptyTo.rc === 2 &&
          commaTo.rc === 2 &&
          emptyTo.err.includes('--to needs a version') &&
          fx.read('Dockerfile').includes('TOOL_VERSION=1.0.0'),
        detail: `${emptyTo.rc} ${emptyTo.err} ${emptyTo.out.slice(0, 300)} | ${commaTo.rc} ${commaTo.err}`,
      },
      {
        name: '--inflight outside `verify --restore` is a usage error, not a silently plain run',
        ok:
          strayVerify.rc === 2 &&
          strayBump.rc === 2 &&
          strayBump.err.includes('--inflight only goes with'),
        detail: `${strayVerify.rc} ${strayVerify.err} | ${strayBump.rc} ${strayBump.err}`,
      },
    ];
  },
  async drafts(m) {
    // The 2026-10-15 npm run, as its plan reported it: root, a submodule labelled without a slash after its path, and a project inside it.
    const npm = {
      id: 'npm',
      name: 'npm trees',
      pinLine:
        'npm: oxc-parser 0.153.0 -> oxc-parser 0.154.0 with 3 in-range package(s), publish time unknown (major 0.153.0 -> 0.154.0 in root).',
      changes: [
        'root: oxc-parser 0.153.0 -> 0.154.0',
        'root: @videojs/react 10.0.1 -> 10.1.0',
        'private/account (update): @hono/node-server 2.1.4 -> 2.1.5',
        'private/account/web (update): @testing-library/user-event 14.6.7 -> 14.6.8',
      ],
    };
    const zed = {
      id: 'embed:zed',
      name: 'zed',
      pinLine: 'embed:zed: 2.0.0 -> 2.1.0, published 2026-10-01T00:00:00.000Z.',
      changes: ['private/renet/Dockerfile: version 2.0.0 -> 2.1.0'],
    };
    const base = {
      subject: 'chore(pins): bump 2 pins (npm trees, zed)',
      plans: [npm, zed],
      commands: [
        { cmd: 'npm install oxc-parser@0.154.0', cwd: '.', rc: 0 },
        { cmd: 'npm update @hono/node-server', cwd: 'private/account', rc: 0 },
        { cmd: 'npm update @testing-library/user-event', cwd: 'private/account/web', rc: 0 },
        { cmd: 'npm run ci -- --only check:deps', cwd: '.', rc: 0 },
      ],
      gates: { ids: ['check:deps'], rc: 0 },
      ungated: [],
      pointers: ['private/account', 'private/renet'],
      submodules: ['private/account', 'private/renet'],
      stamp: '20261015T011423Z-aa4994',
      task: 'cafe1234',
      shared: m === 'shared-message',
    };
    const acct = draftMessage({
      ...base,
      repo: 'private/account',
      paths: ['package-lock.json', 'web/package-lock.json'],
    });
    const renet = draftMessage({ ...base, repo: 'private/renet', paths: ['Dockerfile'] });
    const con = draftMessage({ ...base, repo: '.', paths: ['package-lock.json'] });
    // Review f56ddcde.2: a repository with changed paths but no owning site names no pin from another repository.
    const orphan = draftMessage({ ...base, repo: 'private/elite', paths: ['notes.txt'] });
    const subj = (t: string): string => t.split('\n')[0];
    const pointers = con.split('\n').filter((l) => l.startsWith('Pointer: '));

    // The same property end to end: `bump --all` over the fixture moves a console pin and a private/renet pin in one run.
    const fx = fixtureTree();
    const r = await runCli(['bump', '--all', '--task', 'cafe1234'], withMutant(fx, m));
    const subDraft = /git -C private\/renet commit -F (\S+)/.exec(r.out)?.[1];
    const renetMsg = subDraft ? fs.readFileSync(subDraft, 'utf8') : '';
    return [
      {
        name: 'drafts: a submodule draft lists only its own sites and commands, its subject names the repository and its own changes',
        ok:
          subj(acct) ===
            'chore(pins): bump npm trees in private/account: @hono/node-server 2.1.4 -> 2.1.5, @testing-library/user-event 14.6.7 -> 14.6.8' &&
          acct.includes('Site: private/account (update): @hono/node-server 2.1.4 -> 2.1.5') &&
          acct.includes('Site: private/account/web (update): @testing-library/user-event') &&
          !/oxc-parser|@videojs\/react|in root/.test(acct) &&
          !acct.includes('(in .)') &&
          acct.includes('Ran: npm update @hono/node-server (in private/account) rc=0') &&
          acct.includes('Gates: npm run ci -- --only check:deps rc=0') &&
          acct.trimEnd().endsWith('PR-TASK: cafe1234'),
        detail: acct,
      },
      {
        name: 'drafts: a plan whose every site lies in the submodule keeps its release line there, and the console draft keeps only its own sites',
        ok:
          renet.includes('embed:zed: 2.0.0 -> 2.1.0') &&
          !renet.includes('npm:') &&
          subj(renet) === 'chore(pins): bump zed in private/renet: version 2.0.0 -> 2.1.0' &&
          con.includes('Site: root: oxc-parser 0.153.0 -> 0.154.0') &&
          !con.includes('Site: private/') &&
          !con.includes('(in private/account)'),
        detail: `${renet}\n----\n${con}`,
      },
      {
        name: 'drafts: the console draft names each moved submodule pointer on its own line, with that repository own commit',
        ok:
          pointers.length === 2 &&
          pointers[0] ===
            'Pointer: private/account moves to the private/account pins commit, committed in private/account first (submodule-first) and pushed before this one.' &&
          pointers[1].startsWith('Pointer: private/renet moves to the private/renet pins commit'),
        detail: pointers.join(' | '),
      },
      {
        name: 'drafts: a repository with changed paths and no site of its own names no other repository pin in its subject',
        ok: subj(orphan) === 'chore(pins): bump in private/elite: 1 file(s)',
        detail: subj(orphan),
      },
      {
        name: 'drafts: bump --all over a console pin and a submodule pin gives the submodule draft none of the console pin',
        ok:
          r.rc === 0 &&
          renetMsg.startsWith('chore(pins): bump zed in private/renet: version 2.0.0 -> 2.1.0') &&
          !/embed:tool: |TOOL_VERSION|tool\.lock|gen-credits|Site: (?!private\/renet\/)/.test(
            renetMsg
          ),
        detail: `rc=${r.rc} ${r.err}\n${renetMsg}`,
      },
    ];
  },
  async ungated(m) {
    // An entry with `gates: []` is judged by no gate; the run says so in its output, its draft and its commands.log (2026-10-15: `bump --all` moved three such pins and printed nothing about gates).
    const ungate = (fx: Fx): void => {
      const reg = JSON.parse(fx.read('.ci/config/pins.json')) as {
        entries: Array<{ id: string; gates: string[] }>;
      };
      for (const e of reg.entries) if (e.id === 'embed:tool') e.gates = [];
      fx.write('.ci/config/pins.json', `${JSON.stringify(reg, null, 2)}\n`);
      sh(
        fx.root,
        '-c',
        'user.email=fx@example.invalid',
        '-c',
        'user.name=fx',
        'commit',
        '-qam',
        'ungate'
      );
    };
    const fx = fixtureTree();
    ungate(fx);
    const r = await runCli(
      ['bump', 'embed:tool', '--task', 'cafe1234', '--json'],
      withMutant(fx, m)
    );
    const rep = r.out.startsWith('{')
      ? (JSON.parse(r.out) as {
          ungated?: string[];
          journal: string;
          repos: Array<{ draft: string }>;
        })
      : null;
    const log = rep ? path.join(rep.journal, 'commands.log') : '';
    const logText = log && fs.existsSync(log) ? fs.readFileSync(log, 'utf8') : '';
    const draft = rep?.repos[0] ? fs.readFileSync(rep.repos[0].draft, 'utf8') : '';
    const fx2 = fixtureTree();
    ungate(fx2);
    const plain = await runCli(['bump', 'embed:tool'], withMutant(fx2, m));
    // CONTROL: a gated pin runs its gates and claims no ungated pin.
    const gated = fixtureTree();
    const g = await runCli(['bump', 'embed:tool'], withMutant(gated, m));
    return [
      {
        name: 'ungated: a bump of a pin whose entry names no gate prints, journals and drafts that no gate ran for it',
        ok:
          r.rc === 0 &&
          JSON.stringify(rep?.ungated) === '["embed:tool"]' &&
          logText.includes('# no gate ran for embed:tool') &&
          draft.includes('Gates: none ran for embed:tool') &&
          plain.rc === 0 &&
          plain.out.includes('gates: none ran for embed:tool; the registry entry names no gate'),
        detail: `rc=${r.rc} ${r.err} ungated=${JSON.stringify(rep?.ungated)} log=${JSON.stringify(logText)} | ${plain.out}`,
      },
      {
        name: 'CONTROL: ungated: a gated pin prints its gate line and no ungated line',
        ok:
          g.rc === 0 &&
          g.out.includes('gates: npm run ci -- --only check:fixture-tool rc=0') &&
          !g.out.includes('none ran'),
        detail: `rc=${g.rc} ${g.out} ${g.err}`,
      },
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

  /**
   * Worklist #3fc8b8cb, the 394935a1f shape: a bump moves i18next 26.4.4 -> 26.5.2, the sync step moves the "Pin i18next" group's pinVersion, and every manifest the group covers must declare the new pin too (npm update never rewrites a range); the plan that declares those writes must run check:version. Mutants: `no-manifest-pin` (the sync leaves the manifests on ^26.4.4, so the "ranges follow" control goes red) and `no-version-gate` (the plan keeps check:deps alone, so the gate-list control goes red).
   */
  async pinmanifests(m) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-selftest-'));
    FIXTURE_ROOTS.push(root);
    const json = (o: unknown): string => `${JSON.stringify(o, null, 2)}\n`;
    const rcBefore = json({
      source: ['package.json', 'packages/*/package.json'],
      versionGroups: [
        {
          label: 'Pin i18next for CLI',
          packages: ['**'],
          dependencies: ['i18next'],
          pinVersion: '^26.4.4',
        },
        {
          label: 'Pin vite-tsconfig-paths',
          packages: ['**'],
          dependencies: ['vite-tsconfig-paths'],
          pinVersion: '^6.0.3',
        },
      ],
    });
    const files: Record<string, string> = {
      '.syncpackrc.json': rcBefore,
      'package.json': json({
        name: 'root',
        private: true,
        devDependencies: { 'vite-tsconfig-paths': '^6.0.3' },
      }),
      'package-lock.json': '{ "lockfileVersion": 3 }\n',
      'packages/cli/package.json': json({ name: '@fx/cli', dependencies: { i18next: '^26.4.4' } }),
      'packages/www/package.json': json({
        name: '@fx/web',
        devDependencies: { i18next: '^26.4.4' },
      }),
      'packages/shared/package.json': json({
        name: '@fx/plain',
        dependencies: { other: '^1.0.0' },
      }),
    };
    for (const [rel, text] of Object.entries(files)) {
      fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
      fs.writeFileSync(path.join(root, rel), text);
    }
    const step = {
      cwd: root,
      args: ['update', '-w=packages/cli', 'i18next'],
      label: 'root (update)',
      packages: [{ name: 'i18next', current: '26.4.4', latest: '26.5.2', wanted: '26.5.2' }],
      checks: [],
    };
    const r = spawnSync(
      process.execPath,
      [
        ...process.execArgv,
        path.join(REPO_ROOT, 'scripts/lib/pins/drivers/npm-steps.ts'),
        'sync',
        Buffer.from(JSON.stringify([step])).toString('base64'),
      ],
      {
        encoding: 'utf8',
        env: {
          ...process.env,
          CHECK_DEPS_ROOT: root,
          CHECK_DEPS_MUTANT: '',
          PINS_MUTANT: m === 'no-manifest-pin' ? m : '',
        },
      }
    );
    const read = (rel: string): string => fs.readFileSync(path.join(root, rel), 'utf8');
    const range = (rel: string, field: string): unknown =>
      (JSON.parse(read(rel)) as Record<string, Record<string, unknown>>)[field]?.i18next;
    const rcAfter = read('.syncpackrc.json');
    const manifests = sourceManifests(root, rcBefore).map((file) => ({
      file,
      text: files[file],
    }));
    const predicted = predictManifests(rcBefore, new Set(['i18next']), manifests);

    // The gate list of a plan shaped like the npm driver's: its sync step declares the rc file and the predicted manifests.
    const npmEntry: PinEntry = {
      id: 'npm',
      kind: 'family',
      name: 'npm trees',
      driver: 'npm',
      source: { type: 'npm-registry', package: '*' },
      safety: { mode: 'release-age', major: 'allow-file' },
      holds: [],
      gates: ['check:deps', 'check:ci-lockfile'],
      sites: [],
      derive: [],
      literals: [],
    } as unknown as PinEntry;
    const planOf = (writes: RepoPath[]): PinPlan => ({
      entry: npmEntry,
      from: '1.0',
      to: { version: '1 package(s)', publishedMs: null },
      writes: [],
      steps: [{ label: 'syncpack pin groups', run: 'true', cwd: '.', writes }],
      changes: [],
    });
    const synced = withManifestGates(
      planOf([
        { repo: '.', file: '.syncpackrc.json' },
        ...predicted.map((file) => ({ repo: '.', file })),
      ]),
      m === 'no-version-gate' ? m : null
    );
    const dockerOnly = withManifestGates(planOf([{ repo: '.', file: 'Dockerfile' }]), null);
    // The bad-range control: a covered manifest whose range is not plain is refused by name and nothing is written.
    const refused = planManifestPins(
      movedPinGroups(rcBefore, rcBefore.replace('^26.4.4', '^26.5.2')),
      [
        {
          file: 'packages/cli/package.json',
          text: json({ name: '@fx/odd', dependencies: { i18next: 'file:../vendored' } }),
        },
      ]
    );
    return [
      {
        name: 'pin manifests: the sync moves the group pin and every covered manifest range to it (dependencies and devDependencies), and leaves an uncovered manifest byte-identical',
        ok:
          r.status === 0 &&
          JSON.parse(rcAfter).versionGroups[0].pinVersion === '^26.5.2' &&
          range('packages/cli/package.json', 'dependencies') === '^26.5.2' &&
          range('packages/www/package.json', 'devDependencies') === '^26.5.2' &&
          read('packages/shared/package.json') === files['packages/shared/package.json'] &&
          read('package.json') === files['package.json'],
        detail: `rc=${r.status}\n${r.stdout}\n${r.stderr}\n${rcAfter}`,
      },
      {
        name: 'pin manifests: the plan declares exactly the manifests that declare a member of a group holding a moved package',
        ok: predicted.join(',') === 'packages/cli/package.json,packages/www/package.json',
        detail: predicted.join(','),
      },
      {
        name: 'pin manifests: a plan whose step writes a manifest or .syncpackrc.json runs check:version beside its entry gates',
        ok:
          synced.entry.gates.join(',') === 'check:deps,check:ci-lockfile,check:version' &&
          npmEntry.gates.length === 2,
        detail: synced.entry.gates.join(','),
      },
      {
        name: 'pin manifests: CONTROL: a plan that touches no manifest keeps its own gates (check:version is not added unconditionally)',
        ok: dockerOnly.entry.gates.join(',') === 'check:deps,check:ci-lockfile',
        detail: dockerOnly.entry.gates.join(','),
      },
      {
        name: 'pin manifests: a covered range that is not plain is refused by name and nothing is written',
        ok:
          refused.writes.length === 0 &&
          refused.errors.length === 1 &&
          refused.errors[0].includes('packages/cli/package.json') &&
          refused.errors[0].includes('not a plain range'),
        detail: JSON.stringify(refused),
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
  'ledger-off': 'ledger',
  'ledger-by-path': 'ledger',
  'no-restore': 'restore',
  'blind-restore': 'compare',
  'first-eligible': 'setmajor',
  'no-resync': 'resync',
  'all-gates': 'gatenames',
  'silent-ungated': 'ungated',
  'tree-diff-attribution': 'regen',
  'shared-message': 'drafts',
  'no-manifest-pin': 'pinmanifests',
  'no-version-gate': 'pinmanifests',
  'breaking-is-minor': 'breaking',
  'breaking-unlisted': 'breaking',
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
  registerDrivers(realDrivers());
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
