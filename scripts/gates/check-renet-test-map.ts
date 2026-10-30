/**
 * check:renet-test-map -- a renet change runs the Go tests that exercise it, chosen by one map.
 *
 * WHY. Before this gate the only renet Go tests a local run asked for were the chunk store's
 * (`go test ./pkg/chunkstore/...`, the gate this one replaced); a change in pkg/license or
 * pkg/functions was committed and pushed with no `go test` at all, and the first full run was
 * CI's test-renet-go after the push (agent/plans/PLAN-renet-change-test-triggers.md, box M1/M2).
 *
 * THE MAP, `.ci/config/renet-test-map.json`, is the single source. Each entry is a renet path
 * glob (`<dir>/**` or an exact path), the Go packages that glob claims (`packages`), the in-repo
 * packages that import one of them, test imports included (`dependents`), and the vm:check areas
 * the path belongs to (`areas`, read by the vm:check side). A path belongs to its MOST SPECIFIC
 * glob, so `pkg/infra/ceph/**` takes its files from `pkg/infra/**`. `whole` names paths that
 * reach every package (go.mod, go.sum); `always` names packages whose tests read every Go source
 * as text (the i18n baseline scan), which no import graph shows, so they run on any Go change.
 *
 * WHAT THIS GATE PROVES, in order:
 *   1. The map is the import graph. Every package under private/renet/{pkg,cmd} is claimed by
 *      a glob, no entry claims nothing, and each entry's `packages` and `dependents` equal what
 *      `go list -json` says today. `--write` refreshes those two lists; it never adds an entry,
 *      because a new package needs a human to say which areas it belongs to.
 *   2. The renet diff since the console's merge-base with origin/main (the gitlink there against
 *      the renet working tree, untracked files included) selects packages through the map, and
 *      `go test -json` on exactly those passes. A path under pkg/ or cmd/ that no glob claims,
 *      or a base commit missing from the checkout, selects EVERY package: unknown is never "none".
 *   3. A passing run writes a receipt keyed on the renet tree it tested (HEAD^{tree} when the
 *      checkout is clean, else the tree of the working files written through a throwaway index),
 *      recording the console HEAD^{tree} beside it. The receipt lives outside the checkout
 *      (`$RENET_TEST_RECEIPT_DIR`, else `$XDG_CACHE_HOME/rediacc/renet-tests`, else
 *      `~/.cache/rediacc/renet-tests`), so a push clone's run serves the pushing checkout: a renet
 *      tree's test result does not depend on which console checkout ran it.
 *      `block_renet_untested_push` and the Stop hook's `wl_renettests` read the same receipts.
 *
 * A PASS MUST HAVE RUN WHAT IT SELECTED. `go test` exits 0 for a package with no test files,
 * so every selected package must report a verdict, and a selection holding test files must
 * show at least one passing test. A missing `go` is a loud failure with the install hint.
 *
 * ---- gate ----
 * step: Renet test map and mapped Go tests
 * needs: node, go, submodules
 * lane: quality-go
 * selftest: true
 * ---- end gate ----
 */

import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { WK_GO_DL_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { dispatchSelftest, selftestFailer } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

export const MAP_REL = '.ci/config/renet-test-map.json';
export const RENET_REL = 'private/renet';
export const RECEIPT_SCHEMA = 1;
/** Directories whose packages the map must cover. */
export const GO_ROOTS = ['pkg', 'cmd'];

export interface Entry {
  glob: string;
  areas: string[];
  packages: string[];
  dependents: string[];
}
export interface TestMap {
  schema: number;
  module: string;
  areaNames: string[];
  whole: { glob: string; why: string }[];
  always: { package: string; why: string }[];
  entries: Entry[];
}
export interface GoPkg {
  rel: string;
  /** In-repo packages this one needs to build or test, test imports and their deps included. */
  deps: string[];
  hasTests: boolean;
}
export interface Required {
  all: boolean;
  packages: string[];
  /** Why `all` was chosen, or empty. */
  allWhy: string[];
  /** Changed paths the map claimed, for the shape line. */
  mapped: number;
}

// --------------------------------------------------------------------------- the map

/** Code-unit order, the order Python's `sorted` gives, so the two readers of the map agree byte for byte. */
export const byText = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export function globOk(glob: string): boolean {
  return /^[^*]+\/\*\*$/.test(glob) || !glob.includes('*');
}

export function globMatches(glob: string, p: string): boolean {
  if (glob.endsWith('/**')) {
    const base = glob.slice(0, -3);
    return p === base || p.startsWith(`${base}/`);
  }
  return p === glob;
}

/** The entry that claims `p`: the longest matching glob. */
export function ownerOf(map: TestMap, p: string): Entry | undefined {
  let best: Entry | undefined;
  for (const e of map.entries) {
    if (globMatches(e.glob, p) && (best === undefined || e.glob.length > best.glob.length))
      best = e;
  }
  return best;
}

/** A path whose change can alter a Go test outcome even with no glob claiming it. */
export function goRelevant(p: string): boolean {
  return p.endsWith('.go') || GO_ROOTS.some((r) => p.startsWith(`${r}/`));
}

export function requiredFor(
  map: TestMap,
  changed: readonly string[],
  all: readonly string[]
): Required {
  const pk = new Set<string>();
  const allWhy: string[] = [];
  let mapped = 0;
  for (const p of changed) {
    const w = map.whole.find((x) => globMatches(x.glob, p));
    if (w) {
      allWhy.push(`${p} (${w.why})`);
      mapped += 1;
      continue;
    }
    const e = ownerOf(map, p);
    if (e) {
      mapped += 1;
      for (const x of [...e.packages, ...e.dependents]) pk.add(x);
    } else if (goRelevant(p)) {
      allWhy.push(`${p} (no glob in ${MAP_REL} claims it)`);
    }
  }
  if (allWhy.length > 0) return { all: true, packages: [...all].sort(byText), allWhy, mapped };
  if (pk.size > 0) for (const a of map.always) pk.add(a.package);
  return { all: false, packages: [...pk].sort(byText), allWhy, mapped };
}

// --------------------------------------------------------------------------- the import graph

/** Fold the `go list -json` stream (concatenated objects) into in-repo packages with test-closed deps. */
export function parseGoList(stream: string, module: string): GoPkg[] {
  const raw: {
    ImportPath: string;
    Deps?: string[];
    TestImports?: string[];
    XTestImports?: string[];
    TestGoFiles?: string[];
    XTestGoFiles?: string[];
  }[] = [];
  let depth = 0;
  let start = -1;
  let inStr = false;
  let esc = false;
  for (let i = 0; i < stream.length; i++) {
    const c = stream[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === '{') {
      if (depth === 0) start = i;
      depth += 1;
    } else if (c === '}') {
      depth -= 1;
      if (depth === 0) raw.push(JSON.parse(stream.slice(start, i + 1)));
    }
  }
  const pre = `${module}/`;
  const rel = (ip: string): string | undefined =>
    ip.startsWith(pre) ? ip.slice(pre.length) : undefined;
  const own = new Map<string, string[]>();
  for (const r of raw) {
    const k = rel(r.ImportPath);
    if (k !== undefined)
      own.set(
        k,
        (r.Deps ?? []).map(rel).filter((x): x is string => x !== undefined)
      );
  }
  return raw
    .filter((r) => rel(r.ImportPath) !== undefined)
    .map((r) => {
      const k = rel(r.ImportPath) as string;
      const deps = new Set(own.get(k) ?? []);
      for (const t of [...(r.TestImports ?? []), ...(r.XTestImports ?? [])]) {
        const tk = rel(t);
        if (tk === undefined || !own.has(tk)) continue;
        deps.add(tk);
        for (const d of own.get(tk) ?? []) deps.add(d);
      }
      deps.delete(k);
      return {
        rel: k,
        deps: [...deps].sort(byText),
        hasTests: (r.TestGoFiles?.length ?? 0) + (r.XTestGoFiles?.length ?? 0) > 0,
      };
    })
    .sort((a, b) => byText(a.rel, b.rel));
}

/** What each entry's two generated lists must be, and the packages no glob claims. */
export function expected(
  map: TestMap,
  pkgs: readonly GoPkg[]
): { lists: Map<string, { packages: string[]; dependents: string[] }>; uncovered: string[] } {
  const lists = new Map<string, { packages: string[]; dependents: string[] }>();
  for (const e of map.entries) lists.set(e.glob, { packages: [], dependents: [] });
  const uncovered: string[] = [];
  for (const p of pkgs) {
    const e = ownerOf(map, `${p.rel}/x.go`);
    if (e) lists.get(e.glob)?.packages.push(p.rel);
    else uncovered.push(p.rel);
  }
  for (const [, v] of lists) {
    const mine = new Set(v.packages);
    v.dependents = pkgs
      .filter((q) => !mine.has(q.rel) && q.deps.some((d) => mine.has(d)))
      .map((q) => q.rel)
      .sort(byText);
    v.packages.sort(byText);
  }
  return { lists, uncovered };
}

const same = (a: readonly string[], b: readonly string[]): boolean =>
  a.length === b.length && a.every((x, i) => x === b[i]);

/** Every way the map disagrees with the tree, each line naming the fix. */
export function validate(map: TestMap, pkgs: readonly GoPkg[]): string[] {
  const out: string[] = [];
  if (pkgs.length === 0)
    out.push(
      'go list found 0 packages under pkg/ and cmd/; the gate is not seeing the tree, so its green would mean nothing'
    );
  const names = new Set(pkgs.map((p) => p.rel));
  const seen = new Set<string>();
  for (const e of map.entries) {
    if (seen.has(e.glob)) out.push(`${e.glob}: listed twice; keep one entry`);
    seen.add(e.glob);
    if (!globOk(e.glob)) out.push(`${e.glob}: a glob is "<dir>/**" or an exact path`);
    for (const a of e.areas)
      if (!map.areaNames.includes(a))
        out.push(`${e.glob}: area "${a}" is not one of ${map.areaNames.join(', ')}`);
  }
  for (const w of map.whole)
    if (!globOk(w.glob)) out.push(`whole ${w.glob}: a glob is "<dir>/**" or an exact path`);
  for (const a of map.always)
    if (!names.has(a.package))
      out.push(`always ${a.package}: no such package; delete the row or fix the name`);
  const { lists, uncovered } = expected(map, pkgs);
  for (const u of uncovered)
    out.push(
      `${u}: no glob claims this package. Add {"glob": "${u}/**", "areas": [...]} to ${MAP_REL}, then run --write`
    );
  for (const e of map.entries) {
    const want = lists.get(e.glob);
    if (!want) continue;
    if (want.packages.length === 0) {
      out.push(
        `${e.glob}: claims no package (a more specific glob took them, or the package is gone); delete the entry`
      );
      continue;
    }
    if (!same(e.packages, want.packages))
      out.push(
        `${e.glob}: packages ${JSON.stringify(e.packages)} != go list ${JSON.stringify(want.packages)}; run --write`
      );
    if (!same(e.dependents, want.dependents))
      out.push(
        `${e.glob}: dependents drifted from go list (${want.dependents.length} expected, ${e.dependents.length} recorded); run --write`
      );
  }
  return out;
}

export function refreshed(map: TestMap, pkgs: readonly GoPkg[]): TestMap {
  const { lists } = expected(map, pkgs);
  return {
    ...map,
    entries: map.entries.map((e) => ({
      ...e,
      ...(lists.get(e.glob) ?? { packages: [], dependents: [] }),
    })),
  };
}

// --------------------------------------------------------------------------- the test run

export interface Verdict {
  passed: number;
  failed: string[];
  skipped: number;
  verdicts: Set<string>;
}

/** Fold `go test -json` lines; package-level events carry no `Test`. */
export function judge(jsonLines: string, module: string): Verdict {
  const v: Verdict = { passed: 0, failed: [], skipped: 0, verdicts: new Set() };
  const pre = `${module}/`;
  for (const line of jsonLines.split('\n')) {
    if (line.trim() === '') continue;
    let e: { Action?: string; Package?: string; Test?: string };
    try {
      e = JSON.parse(line);
    } catch {
      continue;
    }
    const pkg = (e.Package ?? '').startsWith(pre)
      ? (e.Package ?? '').slice(pre.length)
      : (e.Package ?? '?');
    if (e.Test) {
      if (e.Action === 'pass') v.passed += 1;
      else if (e.Action === 'fail') v.failed.push(`${pkg}.${e.Test}`);
      else if (e.Action === 'skip') v.skipped += 1;
    } else if (e.Action === 'pass' || e.Action === 'fail' || e.Action === 'skip') {
      v.verdicts.add(pkg);
      if (e.Action === 'fail') v.failed.push(`${pkg} (package)`);
    }
  }
  return v;
}

export function refusals(v: Verdict, selected: readonly string[], withTests: number): string[] {
  const out: string[] = [];
  if (v.failed.length > 0)
    out.push(`${v.failed.length} failing: ${v.failed.slice(0, 12).join(', ')}`);
  const silent = selected.filter((p) => !v.verdicts.has(p));
  if (silent.length > 0)
    out.push(
      `${silent.length} selected package(s) reported no verdict: ${silent.slice(0, 8).join(', ')}`
    );
  if (withTests > 0 && v.passed === 0)
    out.push(
      `${withTests} selected package(s) hold tests and 0 tests passed; the run tested nothing`
    );
  return out;
}

// --------------------------------------------------------------------------- receipts

export function receiptDir(env: NodeJS.ProcessEnv = process.env): string {
  if (env.RENET_TEST_RECEIPT_DIR) return env.RENET_TEST_RECEIPT_DIR;
  const cache = env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
  return path.join(cache, 'rediacc', 'renet-tests');
}

export interface Receipt {
  schema: number;
  renetTree: string;
  renetHead: string;
  dirty: boolean;
  all: boolean;
  packages: string[];
  consoleTrees: string[];
  base: string;
  passed: number;
  finishedAt: string;
}

/** Union a new passing run into the receipt already on file for the same tree. */
export function merged(old: Receipt | undefined, now: Receipt): Receipt {
  if (!old || old.schema !== RECEIPT_SCHEMA || old.renetTree !== now.renetTree) return now;
  return {
    ...now,
    all: old.all || now.all,
    packages: [...new Set([...old.packages, ...now.packages])].sort(byText),
    consoleTrees: [...new Set([...old.consoleTrees, ...now.consoleTrees])],
  };
}

function writeReceipt(r: Receipt): string {
  const dir = receiptDir();
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${r.renetTree}.json`);
  let old: Receipt | undefined;
  try {
    old = JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    old = undefined;
  }
  const out = merged(old, r);
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(out, null, 2)}\n`);
  fs.renameSync(tmp, file);
  return file;
}

// --------------------------------------------------------------------------- git

function git(cwd: string, args: string[], env?: NodeJS.ProcessEnv): string | undefined {
  const r = spawnSync('git', args, { cwd, encoding: 'utf-8', env: env ?? process.env });
  return r.status === 0 ? r.stdout.trim() : undefined;
}

/** The renet commit the console's merge-base with origin/main pins, or why there is none. */
export function renetBase(console: string): { base?: string; why?: string } {
  const mb = git(console, ['merge-base', 'HEAD', 'origin/main']);
  if (!mb) return { why: 'no merge-base of HEAD and origin/main' };
  const link = git(console, ['rev-parse', `${mb}:${RENET_REL}`]);
  if (!link)
    return { why: `origin/main merge-base ${mb.slice(0, 12)} has no ${RENET_REL} gitlink` };
  return { base: link };
}

/** The tree of the renet working files: HEAD^{tree} when clean, else written through a throwaway index. */
function workingTree(renet: string): { tree?: string; dirty: boolean } {
  const status = git(renet, ['status', '--porcelain', '--untracked-files=all']);
  if (status === undefined) return { dirty: true };
  if (status === '') return { tree: git(renet, ['rev-parse', 'HEAD^{tree}']), dirty: false };
  const idx = path.join(os.tmpdir(), `renet-test-index-${process.pid}-${crypto.randomUUID()}`);
  const env = { ...process.env, GIT_INDEX_FILE: idx };
  try {
    if (git(renet, ['read-tree', 'HEAD'], env) === undefined) return { dirty: true };
    if (git(renet, ['add', '-A'], env) === undefined) return { dirty: true };
    return { tree: git(renet, ['write-tree'], env), dirty: true };
  } finally {
    fs.rmSync(idx, { force: true });
  }
}

// --------------------------------------------------------------------------- selftest

function selftest(): void {
  const fail = selftestFailer((m) => `${RED}selftest FAIL: ${m}${NC}`);
  const ok = (cond: boolean, what: string): void => {
    if (!cond) fail(what);
    console.log(`  PASS  ${what}`);
  };
  const map: TestMap = {
    schema: 1,
    module: 'm',
    areaNames: ['license', 'ceph'],
    whole: [{ glob: 'go.mod', why: 'module graph' }],
    always: [{ package: 'pkg/i18n', why: 'scans sources' }],
    entries: [
      { glob: 'pkg/a/**', areas: ['license'], packages: ['pkg/a'], dependents: ['cmd/r'] },
      { glob: 'pkg/infra/**', areas: [], packages: ['pkg/infra'], dependents: [] },
      {
        glob: 'pkg/infra/ceph/**',
        areas: ['ceph'],
        packages: ['pkg/infra/ceph'],
        dependents: ['pkg/infra'],
      },
      { glob: 'pkg/i18n/**', areas: [], packages: ['pkg/i18n'], dependents: [] },
      { glob: 'cmd/r/**', areas: [], packages: ['cmd/r'], dependents: [] },
    ],
  };
  const pkgs: GoPkg[] = [
    { rel: 'cmd/r', deps: ['pkg/a'], hasTests: true },
    { rel: 'pkg/a', deps: [], hasTests: true },
    { rel: 'pkg/i18n', deps: [], hasTests: true },
    { rel: 'pkg/infra', deps: ['pkg/infra/ceph'], hasTests: false },
    { rel: 'pkg/infra/ceph', deps: [], hasTests: true },
  ];
  const all = pkgs.map((p) => p.rel);
  ok(validate(map, pkgs).length === 0, 'CONTROL: a map equal to the graph validates clean');
  ok(
    validate(map, [...pkgs, { rel: 'pkg/planted', deps: [], hasTests: true }]).some((f) =>
      f.startsWith('pkg/planted:')
    ),
    'a package no glob claims is refused'
  );
  ok(validate(map, []).length > 0, 'zero packages is refused (no vacuous green)');
  ok(
    validate(
      map,
      pkgs.map((p) => (p.rel === 'cmd/r' ? { ...p, deps: [] } : p))
    ).some((f) => f.includes('dependents drifted')),
    'a dependent the graph no longer has is refused'
  );
  ok(
    ownerOf(map, 'pkg/infra/ceph/x.go')?.glob === 'pkg/infra/ceph/**',
    'the most specific glob claims a path'
  );
  const lic = requiredFor(map, ['pkg/a/x.go'], all);
  ok(
    !lic.all && same(lic.packages, ['cmd/r', 'pkg/a', 'pkg/i18n']),
    'a mapped change selects the package, its dependents and the always set'
  );
  ok(
    requiredFor(map, ['README.md', 'docs/x.md'], all).packages.length === 0,
    'CONTROL: a docs-only change selects nothing'
  );
  ok(requiredFor(map, ['go.mod'], all).all, 'a whole-module path selects everything');
  ok(
    requiredFor(map, ['pkg/new/x.go'], all).all,
    'an unmapped Go path selects everything (unknown is never none)'
  );
  ok(
    requiredFor(map, ['tools/gen.go'], all).all,
    'a .go file outside pkg/ and cmd/ selects everything'
  );
  const ev = (a: string, p: string, t?: string): string =>
    JSON.stringify({ Action: a, Package: `m/${p}`, ...(t ? { Test: t } : {}) });
  const green = [ev('pass', 'pkg/a', 'T1'), ev('pass', 'pkg/a'), ev('skip', 'pkg/infra')].join(
    '\n'
  );
  ok(
    refusals(judge(green, 'm'), ['pkg/a', 'pkg/infra'], 1).length === 0,
    'CONTROL: a run with a verdict per package passes'
  );
  ok(
    refusals(judge(`${green}\n${ev('fail', 'pkg/a', 'T2')}`, 'm'), ['pkg/a', 'pkg/infra'], 1)
      .length > 0,
    'a failing test is refused'
  );
  ok(
    refusals(judge(green, 'm'), ['pkg/a', 'pkg/infra', 'cmd/r'], 1).length > 0,
    'a selected package with no verdict is refused'
  );
  ok(
    refusals(judge(ev('pass', 'pkg/a'), 'm'), ['pkg/a'], 1).length > 0,
    'zero passing tests over packages with tests is refused'
  );
  const r = (pk: string[], a = false): Receipt => ({
    schema: 1,
    renetTree: 't',
    renetHead: 'h',
    dirty: false,
    all: a,
    packages: pk,
    consoleTrees: ['c'],
    base: 'b',
    passed: 1,
    finishedAt: 'x',
  });
  ok(
    same(merged(r(['pkg/a']), r(['cmd/r'])).packages, ['cmd/r', 'pkg/a']),
    'two runs on one tree union their packages'
  );
  ok(
    same(merged({ ...r(['pkg/a']), renetTree: 'other' }, r(['cmd/r'])).packages, ['cmd/r']),
    'CONTROL: a receipt for another tree is not merged'
  );
}

// --------------------------------------------------------------------------- main

function loadMap(): TestMap {
  return JSON.parse(fs.readFileSync(path.join(REPO_ROOT, MAP_REL), 'utf-8'));
}

function goList(renet: string, module: string): GoPkg[] {
  const r = spawnSync('go', ['list', '-json', ...GO_ROOTS.map((d) => `./${d}/...`)], {
    cwd: renet,
    encoding: 'utf-8',
    maxBuffer: 256 * 1024 * 1024,
  });
  if (r.status !== 0) {
    console.error(
      `${RED}✗ go list failed (exit ${r.status}):${NC}\n${(r.stderr ?? '').split('\n').slice(-20).join('\n')}`
    );
    process.exit(1);
  }
  return parseGoList(r.stdout, module);
}

function changedPaths(renet: string, base: string): string[] {
  const diff = git(renet, ['diff', '--name-only', base]) ?? '';
  const untracked = git(renet, ['ls-files', '--others', '--exclude-standard']) ?? '';
  return [...new Set([...diff.split('\n'), ...untracked.split('\n')].filter((x) => x !== ''))].sort(
    byText
  );
}

function main(): void {
  if (dispatchSelftest('check-renet-test-map', selftest)) return;
  const renet = submodulePath(RENET_REL);
  if (!requireSubmodule('renet test map', [submodulePath(RENET_REL, 'go.mod')])) return;

  const probe = spawnSync('go', ['version'], { encoding: 'utf-8' });
  if (probe.error || probe.status !== 0) {
    console.error(
      `${RED}✗ the go toolchain is not runnable (${probe.error?.message ?? `exit ${probe.status}`}). Install Go at the version in private/renet/go.mod (${WK_GO_DL_BASE}/), or on a CI job add actions/setup-go.${NC}`
    );
    process.exit(1);
  }

  const map = loadMap();
  const pkgs = goList(renet, map.module);
  if (process.argv.includes('--write')) {
    const next = refreshed(map, pkgs);
    fs.writeFileSync(path.join(REPO_ROOT, MAP_REL), `${JSON.stringify(next, null, 2)}\n`);
    const left = validate(next, pkgs);
    console.log(`wrote ${MAP_REL}: ${next.entries.length} entries over ${pkgs.length} packages`);
    for (const f of left) console.error(`${RED}  ${f}${NC}`);
    process.exit(left.length > 0 ? 1 : 0);
  }
  const findings = validate(map, pkgs);
  if (findings.length > 0) {
    console.error(
      `${RED}✗ ${MAP_REL} disagrees with the renet import graph (${findings.length}):${NC}`
    );
    for (const f of findings) console.error(`  ${f}`);
    console.error(`Do not widen a glob to hide a package: give it its own entry and areas.`);
    process.exit(1);
  }
  const shape = `${map.entries.length} entries, ${pkgs.length} packages, ${map.always.length} always, ${map.whole.length} whole-module`;

  const { base, why } = renetBase(REPO_ROOT);
  const baseOk =
    base !== undefined && git(renet, ['cat-file', '-e', `${base}^{commit}`]) !== undefined;
  const changed = baseOk ? changedPaths(renet, base as string) : [];
  const all = pkgs.map((p) => p.rel);
  const req = baseOk
    ? requiredFor(map, changed, all)
    : {
        all: true,
        packages: all,
        allWhy: [`renet base unknown: ${why ?? `${base} is not in the checkout`}`],
        mapped: 0,
      };
  if (req.packages.length === 0) {
    console.log(
      `${GREEN}✓ renet test map: ${shape}; ${changed.length} renet path(s) changed since ${(base ?? '?').slice(0, 12)}, none reaches a Go package, 0 tests selected${NC}`
    );
    return;
  }
  if (req.all)
    console.log(
      `${YELLOW}renet test map: every package selected: ${req.allWhy.slice(0, 5).join('; ')}${NC}`
    );
  const known = new Set(all);
  const selected = req.packages.filter((p) => known.has(p));
  const withTests = pkgs.filter((p) => p.hasTests && selected.includes(p.rel)).length;
  const tree = workingTree(renet);
  console.log(
    `renet test map: ${shape}; ${changed.length} changed path(s), ${req.mapped} mapped -> go test ${selected.length} package(s)`
  );
  const run = spawnSync('go', ['test', '-json', ...selected.map((p) => `./${p}`)], {
    cwd: renet,
    encoding: 'utf-8',
    maxBuffer: 1024 * 1024 * 1024,
  });
  const v = judge(run.stdout ?? '', map.module);
  const why2 = refusals(v, selected, withTests);
  if (run.status !== 0 && why2.length === 0) why2.push(`go test exited ${run.status}`);
  if (why2.length > 0) {
    console.error(`${RED}✗ renet mapped Go tests: ${why2.join('; ')}${NC}`);
    for (const l of (run.stdout ?? '').split('\n')) {
      if (
        !/"Action":"(output|build-output)"/.test(l) ||
        !/FAIL|panic|_test\.go:|error|no space/.test(l)
      )
        continue;
      try {
        process.stderr.write((JSON.parse(l) as { Output: string }).Output);
      } catch {
        // an unparsable line carries nothing to show
      }
    }
    console.error((run.stderr ?? '').split('\n').slice(-20).join('\n'));
    console.error(`Re-run one package: (cd ${RENET_REL} && go test ./<package>)`);
    process.exit(1);
  }
  // The tree is named before the run and again after it: an edit landing mid-run means the run tested neither, so it vouches for nothing.
  const after = workingTree(renet);
  let where = 'none (the renet tree could not be named)';
  if (tree.tree && after.tree !== tree.tree) {
    tree.tree = undefined;
    where = `none (the renet files changed during the run: ${(after.tree ?? '?').slice(0, 12)} after, so re-run)`;
  }
  if (tree.tree) {
    where = writeReceipt({
      schema: RECEIPT_SCHEMA,
      renetTree: tree.tree,
      renetHead: git(renet, ['rev-parse', 'HEAD']) ?? '',
      dirty: tree.dirty,
      all: req.all,
      packages: selected,
      consoleTrees: [git(REPO_ROOT, ['rev-parse', 'HEAD^{tree}']) ?? ''],
      base: base ?? '',
      passed: v.passed,
      finishedAt: new Date().toISOString(),
    });
  }
  console.log(
    `${GREEN}✓ renet mapped Go tests: ${v.passed} passed, ${v.skipped} skipped, ${v.verdicts.size}/${selected.length} package verdict(s), renet tree ${(tree.tree ?? '?').slice(0, 12)}${tree.dirty ? ' (working files)' : ''}; receipt ${where}${NC}`
  );
  const listed = selected.slice(0, 40).join(' ');
  console.log(
    `  tested: ${listed}${selected.length > 40 ? ` (+${selected.length - 40} more)` : ''}`
  );
  if (!tree.tree) process.exit(1);
}

if (isEntryPoint(import.meta.filename)) main();
