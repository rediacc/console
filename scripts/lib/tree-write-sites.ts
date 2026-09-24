#!/usr/bin/env node
/**
 * The TS/JS half of `check:ci-gate-tree-writes`: every place a gate module WRITES a path, and whether that path is the real tree.
 *
 * The orchestrator is `.ci/rediacc_ci/quality/gate_tree_writes.py`; this file is the part that needs a JS parser (`oxc-parser`, the exact devDep `scripts/gates/check-control-in-string.ts` already uses). agent/plans/PLAN-ci-gate-write-taint-scanners.md §3 is the design and §4 the controls.
 *
 * WHAT IT RETURNS, per group of entry files (one group per lock entry):
 *   - the module CLOSURE: relative `import`, `export ... from`, `require()` and `import()` with a literal specifier, `.js -> .ts` mapped. `import type` and `export type` edges are erased at runtime and are NOT followed, so a type import cannot pull in a writer (the `update-video-manifest.ts` `saveManifest` shape). Workspace product source, `<packages|private|workers>/<pkg>/src/**`, is a declared boundary: not entered, and counted so the boundary stays visible.
 *   - REACHABILITY per top-level definition: module top-level code runs at import; a definition is live when live code of its module references it, or a live importer imports it by name, namespace or default.
 *   - the write SITES in live code, each with an ORIGIN and the GUARD clauses (flags whose absence keeps the site from running).
 *   - SPAWN edges: a script path literal (`.py/.mjs/.cjs/.js/.ts/.sh`) inside a child_process call's arguments, or inside a binding those arguments name. A spawned JS/TS file joins this group's closure; a spawned `.py`/`.sh` goes back to the orchestrator.
 *
 * THE ORIGIN LATTICE (§3.4). TEMP (and OUTSIDE: `os.homedir()`, an absolute literal outside /tmp) beats SCRATCH beats TREE beats UNRESOLVED: any temp component makes a path temp, the rule `pool_writer_safety.py` `_reftype` settled for bash. A relative literal is neutral inside a join and TREE when it IS the target, because `scripts/ci-runner/run.ts` runs every gate with `cwd: REPO_ROOT`. SCRATCH is a tree path under `.ci/cache/`, which is gitignored.
 *
 * HOW FAR THE TAINT GOES (§3.4 steps 1-3). Flow-insensitive per scope (every binding of a name is combined) with enclosing-scope lookup; module-local parameter flow (a parameter takes the combined origin of its arguments at every call in the module, the default for an omitted one, and a callback `k: (p) => ...` takes the arguments of `x.k(...)`); module-local return values; module constants across ONE import hop. Nothing deeper: the rest is UNRESOLVED, and the orchestrator asks for a pragma.
 *
 * Usage:
 *   tsx scripts/lib/tree-write-sites.ts --json <file...>                  one group; prints its sites
 *   tsx scripts/lib/tree-write-sites.ts --batch < request.json           {root, groups: {id: [files]}} -> per-group results
 *   tsx scripts/lib/tree-write-sites.ts --invocations --lock <lock> [--pkg <package.json>] [--root <dir>]
 *   tsx scripts/lib/tree-write-sites.ts --selftest
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseSync } from 'oxc-parser';
import { loadScripts, resolveInvocations, type ScriptUniverse } from '../gates/check-ci-parity.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_ROOT = path.resolve(HERE, '..', '..');
const MUTATORS_REL = '.ci/config/tree-write-mutators.json';

// --------------------------------------------------------------------------- AST access

/** An ESTree node from oxc, walked structurally. Fields are read through the accessors below, never assumed. */
interface Node {
  type: string;
  start: number;
  end: number;
  [key: string]: unknown;
}

function isNode(v: unknown): v is Node {
  return typeof v === 'object' && v !== null && typeof (v as { type?: unknown }).type === 'string';
}
/** A child node, or null. */
function c(n: Node | null | undefined, k: string): Node | null {
  const v = n?.[k];
  return isNode(v) ? v : null;
}
/** A child node list, holes kept as null so positions still line up with arguments. */
function cs(n: Node | null | undefined, k: string): (Node | null)[] {
  const v = n?.[k];
  return Array.isArray(v) ? v.map((x: unknown) => (isNode(x) ? x : null)) : [];
}
function csn(n: Node | null | undefined, k: string): Node[] {
  return cs(n, k).filter((x): x is Node => x !== null);
}
function s(n: Node | null | undefined, k: string): string | null {
  const v = n?.[k];
  return typeof v === 'string' ? v : null;
}

const SKIP_KEYS = new Set([
  'typeAnnotation',
  'returnType',
  'typeParameters',
  'typeArguments',
  'superTypeArguments',
  'decorators',
  'parent',
]);

function children(n: Node): Node[] {
  const out: Node[] = [];
  for (const k of Object.keys(n)) {
    if (SKIP_KEYS.has(k)) continue;
    const v = n[k];
    if (Array.isArray(v)) {
      for (const x of v) if (isNode(x)) out.push(x);
    } else if (isNode(v)) out.push(v);
  }
  return out;
}

const WRAPPERS = new Set([
  'ParenthesizedExpression',
  'TSAsExpression',
  'TSSatisfiesExpression',
  'TSNonNullExpression',
  'TSTypeAssertion',
  'ChainExpression',
  'AwaitExpression',
]);

function unwrap(e: Node | null | undefined): Node | null {
  let x = e ?? null;
  while (x && WRAPPERS.has(x.type)) x = c(x, 'expression') ?? c(x, 'argument');
  return x;
}

function strLit(e: Node | null | undefined): string | null {
  const x = unwrap(e);
  if (!x) return null;
  if (x.type === 'Literal') return s(x, 'value');
  if (x.type === 'TemplateLiteral' && csn(x, 'expressions').length === 0) {
    return s(c(csn(x, 'quasis')[0], 'value'), 'cooked');
  }
  return null;
}

function propName(p: Node | null): string | null {
  if (!p) return null;
  if (p.type === 'Identifier' || p.type === 'PrivateIdentifier') return s(p, 'name');
  if (p.type === 'Literal') return s(p, 'value');
  return null;
}

function nameOf(n: Node | null): string | null {
  return n?.type === 'Identifier' ? s(n, 'name') : null;
}

const FN_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);

// --------------------------------------------------------------------------- origins

type Origin = 'NONE' | 'REL' | 'UNRES' | 'TREE' | 'SCRATCH' | 'TEMP' | 'OUTSIDE';
const RANK: Record<Origin, number> = {
  NONE: 0,
  REL: 1,
  UNRES: 2,
  TREE: 3,
  SCRATCH: 4,
  TEMP: 5,
  OUTSIDE: 5,
};

/** An origin plus, when it is known, the repo-relative path it names (REL/TREE/SCRATCH). */
interface Val {
  o: Origin;
  rel: string | null;
}
const NONE: Val = { o: 'NONE', rel: null };
const UNRES: Val = { o: 'UNRES', rel: null };
const TEMP: Val = { o: 'TEMP', rel: null };
const OUTSIDE: Val = { o: 'OUTSIDE', rel: null };

function isTreeish(v: Val): boolean {
  return v.o === 'TREE' || v.o === 'SCRATCH';
}

/** A repo-relative path, classified: `..` leaves the tree, `.ci/cache` is scratch, the rest is tree. */
function treeAt(rel: string): Val {
  const n = path.posix.normalize(rel === '' ? '.' : rel).replace(/\/$/, '');
  if (n === '..' || n.startsWith('../')) return OUTSIDE;
  const r = n === '.' ? '' : n;
  if (r === '.ci/cache' || r.startsWith('.ci/cache/')) return { o: 'SCRATCH', rel: r };
  return { o: 'TREE', rel: r };
}

/** The higher-ranked origin; an equal-ranked path is kept only when both sides agree on it. */
function combine(a: Val, b: Val): Val {
  if (RANK[a.o] > RANK[b.o]) return a;
  if (RANK[b.o] > RANK[a.o]) return b;
  if (a.o === b.o && a.rel === b.rel) return a;
  return { o: a.o, rel: null };
}

function literal(v: string): Val {
  if (v === '/tmp' || v.startsWith('/tmp/')) return TEMP;
  if (v.startsWith('/') || v.startsWith('~')) return OUTSIDE;
  if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return UNRES;
  return { o: 'REL', rel: v };
}

/** `path.join` / `path.resolve`: the combined origin, with the path carried when a tree base is followed by literals. */
function joinVals(vals: Val[], resolve: boolean): Val {
  if (vals.length === 0) return resolve ? treeAt('') : NONE;
  const out = vals.reduce(combine, NONE);
  if (out.o === 'REL') {
    if (vals.every((v) => v.rel !== null)) {
      const joined = path.posix.join(...vals.map((v) => v.rel ?? ''));
      return resolve ? treeAt(joined) : { o: 'REL', rel: joined };
    }
    return resolve ? { o: 'TREE', rel: null } : { o: 'REL', rel: null };
  }
  if (!isTreeish(out)) return out;
  let base = -1;
  for (let i = vals.length - 1; i >= 0; i--) {
    const v = vals[i];
    if (v && isTreeish(v)) {
      base = i;
      break;
    }
  }
  const b = vals[base];
  const tail = vals.slice(base + 1);
  if (b && b.rel !== null && tail.every((v) => v.o === 'REL' && v.rel !== null)) {
    return treeAt(path.posix.join(b.rel, ...tail.map((v) => v.rel ?? '')));
  }
  return { o: out.o, rel: null };
}

export type FinalOrigin = 'TEMP' | 'OUTSIDE' | 'SCRATCH' | 'TREE' | 'UNRESOLVED';

/** The value at a WRITE: a relative path lands under the gate's cwd, which is the repo root. */
export function finalOrigin(v: Val): FinalOrigin {
  if (v.o === 'REL') return v.rel !== null && treeAt(v.rel).o === 'SCRATCH' ? 'SCRATCH' : 'TREE';
  if (v.o === 'NONE' || v.o === 'UNRES') return 'UNRESOLVED';
  return v.o;
}

// --------------------------------------------------------------------------- the module model

type Clause = string[];

type Binding =
  | { kind: 'expr'; expr: Node; scope: Scope }
  | { kind: 'elem'; expr: Node; scope: Scope }
  | { kind: 'elemAt'; expr: Node; scope: Scope; index: number }
  | { kind: 'param'; fn: Fn; index: number; dflt: Node | null; scope: Scope }
  | { kind: 'import'; source: string | null; spec: string; imported: string }
  | { kind: 'fn'; fn: Fn }
  | { kind: 'unknown' };

interface Scope {
  id: number;
  parent: Scope | null;
  isFn: boolean;
  names: Map<string, Binding[]>;
}

interface Fn {
  id: number;
  name: string | null;
  /** The object-property key this function is the value of, for callback matching. */
  key: string | null;
  scope: Scope;
  returns: { expr: Node; scope: Scope }[];
  /** The guard clauses at every reference to this function. */
  /** The guard at every reference to this function, with the functions enclosing that reference. */
  refGuards: { guard: Clause[]; fnPath: Fn[] }[];
}

interface CallSite {
  callee: Node | null;
  args: (Node | null)[];
  scope: Scope;
  guard: Clause[];
  fnPath: Fn[];
}

interface RawSite {
  line: number;
  sink: string;
  node: Node;
  value: (ev: Evaluator) => Val;
  scope: Scope;
  guard: Clause[];
  fnPath: Fn[];
  unit: string;
}

interface Spawn {
  file: string;
  argv: string[];
  unit: string;
}

interface ImportEdge {
  source: string | null;
  /** local name -> imported name ('*' for a namespace, 'default'). */
  locals: Map<string, string>;
  /** `require()`/`import()`: everything the module exports is reachable. */
  all: boolean;
  unit: string;
}

interface Module {
  file: string;
  src: string;
  error: string | null;
  /** unit name -> identifiers it references. `<top>` is the module's top-level code. */
  units: Map<string, Set<string>>;
  exports: Map<string, string>;
  reexports: Map<string, { source: string | null; imported: string }>;
  stars: (string | null)[];
  imports: ImportEdge[];
  sites: RawSite[];
  spawns: Spawn[];
  top: Scope;
  fns: Fn[];
  calls: CallSite[];
}

export interface Site {
  file: string;
  line: number;
  sink: string;
  target: string;
  origin: FinalOrigin;
  guard: Clause[];
}

export interface GroupResult {
  modules: string[];
  product: string[];
  spawns: { file: string; argv: string[] }[];
  sites: Site[];
  errors: string[];
}

interface Mutators {
  git: { subcommands: string[] };
  in_place: Record<string, string>;
  pair: string[];
  list: string[];
  output_flag: Record<string, { subcommand: string; flag: string }>;
  install: Record<string, string[]>;
  write_flag: Record<string, string[]>;
  extract: Record<string, { flag: string; dest: string }>;
}

const FAMILIES: [Set<string>, string][] = [
  [new Set(['fs', 'node:fs']), 'fs'],
  [new Set(['fs/promises', 'node:fs/promises']), 'fs.promises'],
  [new Set(['path', 'node:path', 'path/posix', 'node:path/posix']), 'path'],
  [new Set(['os', 'node:os']), 'os'],
  [new Set(['url', 'node:url']), 'url'],
  [new Set(['child_process', 'node:child_process']), 'cp'],
  [new Set(['process', 'node:process']), 'process'],
];

/** fs write sinks and which arguments are write targets. `rename` loses its source too. */
const FS_SINKS: Record<string, number[]> = {
  writeFile: [0],
  appendFile: [0],
  mkdir: [0],
  mkdtemp: [0],
  rm: [0],
  rmdir: [0],
  unlink: [0],
  rename: [0, 1],
  copyFile: [1],
  cp: [1],
  symlink: [1],
  link: [1],
  truncate: [0],
  chmod: [0],
  lchmod: [0],
  utimes: [0],
  createWriteStream: [0],
  open: [0],
};

const SCRIPT_EXT = /\.(py|mjs|cjs|js|ts|sh)$/;
const ROOT_FN_NAMES = new Set(['findRepoRoot', 'repoRoot', 'getRepoRoot']);
const STRING_METHODS = new Set([
  'toString',
  'replace',
  'replaceAll',
  'slice',
  'trim',
  'trimEnd',
  'concat',
  'normalize',
]);

/** The product boundary: workspace product source is not a gate module. */
function isProduct(rel: string): boolean {
  return /^(packages|private|workers)\/[^/]+\/src\//.test(rel);
}

// --------------------------------------------------------------------------- the analyzer

class Analyzer {
  readonly root: string;
  readonly mutators: Mutators;
  private readonly cache = new Map<string, Module>();
  private readonly finished = new Map<string, { unit: string; site: Site }[]>();
  private seq = 0;

  constructor(root: string) {
    this.root = root;
    const mp = path.join(root, MUTATORS_REL);
    const source = fs.existsSync(mp) ? mp : path.join(DEFAULT_ROOT, MUTATORS_REL);
    this.mutators = JSON.parse(fs.readFileSync(source, 'utf-8')) as Mutators;
  }

  next(): number {
    this.seq += 1;
    return this.seq;
  }

  rel(abs: string): string {
    return path.relative(this.root, abs).split(path.sep).join('/');
  }

  private firstFile(cands: string[]): string | null {
    for (const cand of cands) {
      try {
        if (fs.statSync(cand).isFile()) {
          const r = this.rel(cand);
          if (!r.startsWith('..')) return r;
        }
      } catch {
        /* the next candidate */
      }
    }
    return null;
  }

  /** A relative specifier to a repo-relative file, `.js -> .ts` mapped; null when it is a package or nothing exists. */
  resolveSpec(fromRel: string, spec: string): string | null {
    if (!spec.startsWith('.')) return null;
    const base = path.resolve(this.root, path.dirname(fromRel), spec);
    const cands = [base];
    if (/\.[cm]?js$/.test(base))
      cands.push(base.replace(/\.([cm]?)js$/, '.$1ts'), base.replace(/\.js$/, '.tsx'));
    for (const ext of ['.ts', '.tsx', '.mts', '.js', '.mjs', '.cjs']) cands.push(base + ext);
    for (const idx of ['index.ts', 'index.js', 'index.mjs']) cands.push(path.join(base, idx));
    return this.firstFile(cands);
  }

  /** A script path named in a spawn, against the module's directory and then the repo root. */
  resolveScript(fromRel: string, name: string): string | null {
    if (!SCRIPT_EXT.test(name)) return null;
    if (path.isAbsolute(name)) return this.firstFile([name]);
    return this.firstFile([
      path.resolve(this.root, path.dirname(fromRel), name),
      path.resolve(this.root, name),
    ]);
  }

  module(rel: string): Module {
    const hit = this.cache.get(rel);
    if (hit) return hit;
    const m = this.build(rel);
    this.cache.set(rel, m);
    return m;
  }

  scope(parent: Scope | null, isFn: boolean): Scope {
    return { id: this.next(), parent, isFn, names: new Map() };
  }

  private build(rel: string): Module {
    const m: Module = {
      file: rel,
      src: '',
      error: null,
      units: new Map([
        ['<top>', new Set<string>()],
        ['<main>', new Set<string>()],
      ]),
      exports: new Map(),
      reexports: new Map(),
      stars: [],
      imports: [],
      sites: [],
      spawns: [],
      top: this.scope(null, true),
      fns: [],
      calls: [],
    };
    try {
      m.src = fs.readFileSync(path.join(this.root, rel), 'utf-8');
    } catch (e) {
      m.error = `unreadable: ${String(e)}`;
      return m;
    }
    const lang = rel.endsWith('.tsx') ? 'x.tsx' : /\.[cm]?ts$/.test(rel) ? 'x.ts' : 'x.js';
    const res = parseSync(lang, m.src, { sourceType: 'module' });
    const program = res.program as unknown as Node;
    if (res.errors.length > 0 && csn(program, 'body').length === 0) {
      m.error = `parse error: ${res.errors[0]?.message ?? 'unknown'}`;
      return m;
    }
    new ModuleWalker(this, m).walkProgram(program);
    return m;
  }

  sitesOf(m: Module): { unit: string; site: Site }[] {
    const hit = this.finished.get(m.file);
    if (hit) return hit;
    // ONE SITE PER CALLING CONTEXT of its innermost function: a write whose target is a parameter is judged per call, so a selftest call with a temp root and a reseed-flag call with the repo root are a TEMP write plus a gated TREE write, not one ungated TREE write. A reference that is not a call keeps the combined verdict.
    const ev = new Evaluator(this, m);
    const res: { unit: string; site: Site }[] = [];
    for (const raw of m.sites) {
      const target = m.src.slice(raw.node.start, raw.node.end).replace(/\s+/g, ' ').slice(0, 100);
      const local = ev.resolveGuard(raw.guard);
      const seen = new Set<string>();
      const emit = (origin: FinalOrigin, guard: Clause[]): void => {
        const key = JSON.stringify([origin, guard]);
        if (seen.has(key)) return;
        seen.add(key);
        res.push({
          unit: raw.unit,
          site: { file: m.file, line: raw.line, sink: raw.sink, target, origin, guard },
        });
      };
      const inner = raw.fnPath[raw.fnPath.length - 1];
      const calls = inner ? m.calls.filter((cl) => ev.callTargets(cl).includes(inner)) : [];
      if (!inner || calls.length === 0) {
        emit(finalOrigin(raw.value(ev)), [...local, ...ev.fnGuard(raw.fnPath)]);
        continue;
      }
      const outer = raw.fnPath.slice(0, -1);
      for (const call of calls) {
        const cev = new Evaluator(this, m, new Map([[inner.id, call]]));
        emit(finalOrigin(raw.value(cev)), [
          ...local,
          ...ev.resolveGuard(call.guard),
          ...ev.fnGuard([...outer, ...call.fnPath]),
        ]);
      }
      if (inner.refGuards.length > calls.length || ev.isExported(inner))
        emit(finalOrigin(raw.value(ev)), [...local, ...ev.fnGuard(raw.fnPath)]);
    }
    this.finished.set(m.file, res);
    return res;
  }

  /** The closure, reachability, live sites and foreign spawns of one group of entry files. */
  analyzeGroup(entries0: string[]): GroupResult {
    let entries = [...entries0];
    for (let round = 0; round < 8; round++) {
      const r = new GroupWalk(this).run(entries);
      const more = r.spawns.filter(
        (sp) => /\.([cm]?js|ts)$/.test(sp.file) && !r.modules.includes(sp.file)
      );
      if (more.length === 0) {
        r.spawns = r.spawns.filter((sp) => !/\.([cm]?js|ts)$/.test(sp.file));
        return r;
      }
      entries = [...entries, ...more.map((sp) => sp.file)];
    }
    return new GroupWalk(this).run(entries);
  }
}

/** One group's reachability walk over the cached module models. */
class GroupWalk {
  private readonly a: Analyzer;
  private readonly live = new Map<string, Set<string>>();
  private readonly all = new Set<string>();
  private readonly queue: [string, string | null][] = [];
  private readonly seenReq = new Set<string>();
  private readonly entries = new Set<string>();
  private readonly out: GroupResult = {
    modules: [],
    product: [],
    spawns: [],
    sites: [],
    errors: [],
  };

  constructor(a: Analyzer) {
    this.a = a;
  }

  private enter(file: string, name: string | null): void {
    const k = `${file}\0${name ?? ''}`;
    if (this.seenReq.has(k)) return;
    this.seenReq.add(k);
    this.queue.push([file, name]);
  }

  private mark(m: Module, unit: string, work: string[]): void {
    let set = this.live.get(m.file);
    if (!set) {
      set = new Set<string>();
      this.live.set(m.file, set);
    }
    if (!set.has(unit)) {
      set.add(unit);
      work.push(unit);
    }
  }

  private request(m: Module, name: string, work: string[]): void {
    if (name === '*') {
      for (const u of m.units.keys()) if (u !== '<main>') this.mark(m, u, work);
      for (const r of m.reexports.values()) if (r.source) this.enter(r.source, r.imported);
      for (const st of m.stars) if (st) this.enter(st, '*');
      return;
    }
    const local = m.exports.get(name);
    if (local !== undefined) {
      if (m.units.has(local)) this.mark(m, local, work);
      return;
    }
    const re = m.reexports.get(name);
    if (re) {
      if (re.source) this.enter(re.source, re.imported);
      return;
    }
    for (const st of m.stars) if (st) this.enter(st, name);
  }

  private drain(m: Module, work: string[]): void {
    while (work.length > 0) {
      const unit = work.pop() ?? '<top>';
      const refs = m.units.get(unit) ?? new Set<string>();
      for (const r of refs) if (m.units.has(r)) this.mark(m, r, work);
      for (const edge of m.imports) {
        if (!edge.source) continue;
        if (edge.unit === unit) this.enter(edge.source, edge.all ? '*' : null);
        for (const [local, imported] of edge.locals)
          if (refs.has(local)) this.enter(edge.source, imported);
      }
    }
  }

  run(entries: string[]): GroupResult {
    for (const e of entries) this.entries.add(e);
    for (const e of entries) this.enter(e, null);
    while (this.queue.length > 0) {
      const [file, name] = this.queue.shift() ?? ['', null];
      if (isProduct(file)) {
        if (!this.out.product.includes(file)) this.out.product.push(file);
        continue;
      }
      const m = this.a.module(file);
      if (!this.all.has(file)) {
        this.all.add(file);
        if (m.error) this.out.errors.push(`${file}: ${m.error}`);
      }
      const work: string[] = [];
      this.mark(m, '<top>', work);
      if (this.entries.has(file)) this.mark(m, '<main>', work);
      if (name !== null) this.request(m, name, work);
      this.drain(m, work);
    }
    for (const file of [...this.all].sort()) {
      const m = this.a.module(file);
      const units = this.live.get(file) ?? new Set<string>();
      this.out.modules.push(file);
      for (const sp of m.spawns) {
        if (units.has(sp.unit) && !this.out.spawns.some((x) => x.file === sp.file)) {
          this.out.spawns.push({ file: sp.file, argv: sp.argv });
        }
      }
      for (const x of this.a.sitesOf(m)) if (units.has(x.unit)) this.out.sites.push(x.site);
    }
    return this.out;
  }
}

// --------------------------------------------------------------------------- the walk

class ModuleWalker {
  private readonly a: Analyzer;
  private readonly m: Module;
  private unit = '<top>';
  private readonly pendingAssign: { scope: Scope; name: string; b: Binding }[] = [];
  private readonly fnRefs: { name: string; scope: Scope; guard: Clause[]; fnPath: Fn[] }[] = [];
  private readonly lineStarts: number[] = [0];

  constructor(a: Analyzer, m: Module) {
    this.a = a;
    this.m = m;
    for (let i = 0; i < m.src.length; i++)
      if (m.src.charCodeAt(i) === 10) this.lineStarts.push(i + 1);
  }

  private lineOf(off: number): number {
    let lo = 0;
    let hi = this.lineStarts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if ((this.lineStarts[mid] ?? 0) <= off) lo = mid;
      else hi = mid - 1;
    }
    return lo + 1;
  }

  private declare(scope: Scope, name: string, b: Binding): void {
    const list = scope.names.get(name) ?? [];
    list.push(b);
    scope.names.set(name, list);
  }

  private declarePattern(scope: Scope, p: Node | null, b: Binding | null): void {
    if (!p) return;
    if (p.type === 'Identifier') this.declare(scope, s(p, 'name') ?? '', b ?? { kind: 'unknown' });
    else if (p.type === 'ObjectPattern') {
      for (const pr of csn(p, 'properties')) {
        this.declarePattern(
          scope,
          pr.type === 'RestElement' ? c(pr, 'argument') : c(pr, 'value'),
          null
        );
      }
    } else if (p.type === 'ArrayPattern')
      for (const el of csn(p, 'elements')) this.declarePattern(scope, el, null);
    else if (p.type === 'AssignmentPattern') this.declarePattern(scope, c(p, 'left'), b);
    else if (p.type === 'RestElement') this.declarePattern(scope, c(p, 'argument'), null);
  }

  private fnScope(scope: Scope): Scope {
    let sc: Scope = scope;
    while (!sc.isFn && sc.parent) sc = sc.parent;
    return sc;
  }

  private ref(name: string): void {
    this.m.units.get(this.unit)?.add(name);
  }

  /** The top-level names a declaration defines as FUNCTIONS or CLASSES: one unit each. */
  private defNames(d: Node): string[] {
    if (d.type === 'FunctionDeclaration' || d.type === 'ClassDeclaration') {
      const n = nameOf(c(d, 'id'));
      return n ? [n] : [];
    }
    if (d.type === 'VariableDeclaration') {
      const out: string[] = [];
      for (const x of csn(d, 'declarations')) {
        const id = nameOf(c(x, 'id'));
        const init = unwrap(c(x, 'init'));
        if (id && init && FN_TYPES.has(init.type)) out.push(id);
      }
      return out;
    }
    return [];
  }

  walkProgram(program: Node): void {
    for (const st of csn(program, 'body')) {
      const exported =
        st.type === 'ExportNamedDeclaration' || st.type === 'ExportDefaultDeclaration';
      const d = exported ? c(st, 'declaration') : st;
      if (!d) continue;
      for (const name of this.defNames(d)) {
        this.m.units.set(name, new Set<string>());
        if (exported)
          this.m.exports.set(st.type === 'ExportDefaultDeclaration' ? 'default' : name, name);
      }
      if (st.type === 'ExportDefaultDeclaration' && d.type === 'Identifier')
        this.m.exports.set('default', s(d, 'name') ?? '');
    }
    for (const st of csn(program, 'body')) this.topStatement(st);
    for (const p of this.pendingAssign) {
      let sc: Scope | null = p.scope;
      while (sc && !sc.names.has(p.name)) sc = sc.parent;
      this.declare(sc ?? this.m.top, p.name, p.b);
    }
    // Resolved AFTER the walk: a function defined below its caller is not bound yet when the caller is walked.
    for (const r of this.fnRefs)
      for (const fn of this.lookupFns(r.name, r.scope))
        fn.refGuards.push({ guard: r.guard, fnPath: r.fnPath });
  }

  private importDecl(st: Node): void {
    if (s(st, 'importKind') === 'type') return;
    const spec = s(c(st, 'source'), 'value') ?? '';
    const source = this.a.resolveSpec(this.m.file, spec);
    const specs = csn(st, 'specifiers');
    const valueSpecs = specs.filter((x) => s(x, 'importKind') !== 'type');
    if (specs.length > 0 && valueSpecs.length === 0) return;
    const locals = new Map<string, string>();
    for (const x of valueSpecs) {
      let imported = 'default';
      if (x.type === 'ImportNamespaceSpecifier') imported = '*';
      else if (x.type === 'ImportSpecifier') imported = propName(c(x, 'imported')) ?? 'default';
      const local = nameOf(c(x, 'local')) ?? '';
      locals.set(local, imported);
      this.declare(this.m.top, local, { kind: 'import', source, spec, imported });
    }
    this.m.imports.push({ source, locals, all: false, unit: '<top>' });
  }

  private reexport(st: Node): void {
    if (s(st, 'exportKind') === 'type') return;
    const source = this.a.resolveSpec(this.m.file, s(c(st, 'source'), 'value') ?? '');
    if (st.type === 'ExportAllDeclaration') {
      const as = propName(c(st, 'exported'));
      if (as) this.m.reexports.set(as, { source, imported: '*' });
      else this.m.stars.push(source);
    } else {
      for (const x of csn(st, 'specifiers')) {
        if (s(x, 'exportKind') === 'type') continue;
        this.m.reexports.set(propName(c(x, 'exported')) ?? '', {
          source,
          imported: propName(c(x, 'local')) ?? '',
        });
      }
    }
    this.m.imports.push({ source, locals: new Map(), all: false, unit: '<top>' });
  }

  private topStatement(st: Node): void {
    const top = this.m.top;
    if (st.type === 'ImportDeclaration') return this.importDecl(st);
    if (
      (st.type === 'ExportNamedDeclaration' && c(st, 'source')) ||
      st.type === 'ExportAllDeclaration'
    ) {
      return this.reexport(st);
    }
    const exported = st.type === 'ExportNamedDeclaration' || st.type === 'ExportDefaultDeclaration';
    if (st.type === 'ExportNamedDeclaration' && !c(st, 'declaration')) {
      for (const x of csn(st, 'specifiers'))
        this.m.exports.set(propName(c(x, 'exported')) ?? '', propName(c(x, 'local')) ?? '');
      return;
    }
    const d = exported ? c(st, 'declaration') : st;
    if (!d) return;
    if (st.type === 'ExportDefaultDeclaration' && this.defNames(d).length === 0)
      this.m.exports.set('default', '<top>');
    if (d.type === 'VariableDeclaration') {
      for (const x of csn(d, 'declarations')) {
        const id = nameOf(c(x, 'id'));
        const init = unwrap(c(x, 'init'));
        if (id && init && FN_TYPES.has(init.type)) {
          this.unit = id;
          const fn = this.walkFunction(init, id, null, top, []);
          this.declare(top, id, { kind: 'fn', fn });
          this.unit = '<top>';
          continue;
        }
        if (id && exported) this.m.exports.set(id, '<top>');
        const initNode = c(x, 'init');
        this.declarePattern(
          top,
          c(x, 'id'),
          initNode ? { kind: 'expr', expr: initNode, scope: top } : null
        );
        if (initNode) this.expr(initNode, top, [], []);
      }
      return;
    }
    const id = nameOf(c(d, 'id'));
    if ((d.type === 'FunctionDeclaration' || d.type === 'ClassDeclaration') && id) {
      this.unit = id;
      if (d.type === 'FunctionDeclaration') {
        const fn = this.walkFunction(d, id, null, top, []);
        this.declare(top, id, { kind: 'fn', fn });
      } else {
        this.declare(top, id, { kind: 'unknown' });
        this.generic(d, top, [], []);
      }
      this.unit = '<top>';
      return;
    }
    // `if (<argv[1] is this file>) main();` runs only when the module is the ENTRY, never when a gate imports it.
    if (d.type === 'IfStatement' && this.isMainGuard(c(d, 'test'))) {
      this.unit = '<main>';
      this.statementList([d], top, [], []);
      this.unit = '<top>';
      return;
    }
    this.statementList([d], top, [], []);
  }

  /** A function body starts under the guard at its DEFINITION: a closure defined inside `if (write)` cannot run unless that branch did. */
  private isMainGuard(test: Node | null): boolean {
    if (!test) return false;
    const src = this.m.src.slice(test.start, test.end);
    return (
      /import\.meta\.(url|filename|main)|require\.main\s*===\s*module/.test(src) &&
      /process\.argv|import\.meta\.main|require\.main/.test(src)
    );
  }

  private walkFunction(
    node: Node,
    name: string | null,
    key: string | null,
    scope: Scope,
    fnPath: Fn[],
    guard: Clause[] = []
  ): Fn {
    const inner = this.a.scope(scope, true);
    const fn: Fn = { id: this.a.next(), name, key, scope: inner, returns: [], refGuards: [] };
    this.m.fns.push(fn);
    const path2 = [...fnPath, fn];
    cs(node, 'params').forEach((p0, i) => {
      const p = p0?.type === 'TSParameterProperty' ? c(p0, 'parameter') : p0;
      const id = p?.type === 'AssignmentPattern' ? c(p, 'left') : p;
      const dflt = p?.type === 'AssignmentPattern' ? c(p, 'right') : null;
      const pname = nameOf(id);
      if (pname) this.declare(inner, pname, { kind: 'param', fn, index: i, dflt, scope: inner });
      else this.declarePattern(inner, id, null);
      if (dflt) this.expr(dflt, inner, [], path2);
    });
    const self = nameOf(c(node, 'id'));
    if (self && node.type === 'FunctionExpression') this.declare(inner, self, { kind: 'fn', fn });
    const body = c(node, 'body');
    if (!body) return fn;
    if (body.type === 'BlockStatement') this.statementList(csn(body, 'body'), inner, guard, path2);
    else {
      fn.returns.push({ expr: body, scope: inner });
      this.expr(body, inner, guard, path2);
    }
    return fn;
  }

  private tests(test: Node | null, scope: Scope): { t: Clause[]; f: Clause[] } {
    return new Evaluator(this.a, this.m).testClauses(test, scope, 0);
  }

  /** A statement list, carrying the early-exit guard: after `if (!write) return;` the rest runs only under `--write`. */
  private statementList(list: Node[], scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    let g = guard;
    for (const st of list) {
      this.statement(st, scope, g, fnPath);
      if (st.type === 'IfStatement' && !c(st, 'alternate') && this.exits(c(st, 'consequent'))) {
        g = [...g, ...this.tests(c(st, 'test'), scope).f];
      }
    }
  }

  private exits(st: Node | null): boolean {
    if (!st) return false;
    if (
      ['ReturnStatement', 'ThrowStatement', 'ContinueStatement', 'BreakStatement'].includes(st.type)
    )
      return true;
    if (st.type === 'BlockStatement') {
      const body = csn(st, 'body');
      return body.length > 0 && this.exits(body[body.length - 1] ?? null);
    }
    if (st.type === 'ExpressionStatement') {
      const e = unwrap(c(st, 'expression'));
      const callee = c(e, 'callee');
      return (
        e?.type === 'CallExpression' &&
        !!callee &&
        this.m.src.slice(callee.start, callee.end) === 'process.exit'
      );
    }
    return false;
  }

  private varDecl(st: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    const fsc = this.fnScope(scope);
    for (const x of csn(st, 'declarations')) {
      const id = nameOf(c(x, 'id'));
      const init = unwrap(c(x, 'init'));
      if (id && init && FN_TYPES.has(init.type)) {
        const fn = this.walkFunction(init, id, null, scope, fnPath, guard);
        this.declare(fsc, id, { kind: 'fn', fn });
        continue;
      }
      const initNode = c(x, 'init');
      this.declarePattern(
        fsc,
        c(x, 'id'),
        initNode ? { kind: 'expr', expr: initNode, scope } : null
      );
      if (initNode) this.expr(initNode, scope, guard, fnPath);
    }
  }

  private forOf(st: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    const leftN = c(st, 'left');
    const right = c(st, 'right');
    const isDecl = leftN?.type === 'VariableDeclaration';
    const left = isDecl ? c(csn(leftN, 'declarations')[0], 'id') : leftN;
    const b: Binding =
      st.type === 'ForOfStatement' && right
        ? { kind: 'elem', expr: right, scope }
        : { kind: 'unknown' };
    const lname = nameOf(left);
    if (lname && !isDecl) this.pendingAssign.push({ scope, name: lname, b });
    else if (left?.type === 'ArrayPattern' && right && st.type === 'ForOfStatement') {
      // `for (const [dir, en] of [[asymmetric, ...], ...])`: `dir` is element 0 of each row.
      cs(left, 'elements').forEach((el, index) => {
        const n = nameOf(el);
        if (n) this.declare(this.fnScope(scope), n, { kind: 'elemAt', expr: right, scope, index });
      });
    } else this.declarePattern(this.fnScope(scope), left, b);
    if (right) this.expr(right, scope, guard, fnPath);
    const body = c(st, 'body');
    if (body) this.statement(body, scope, guard, fnPath);
  }

  private statement(st: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    switch (st.type) {
      case 'IfStatement': {
        const test = c(st, 'test');
        if (test) this.expr(test, scope, guard, fnPath);
        const tc = this.tests(test, scope);
        const cons = c(st, 'consequent');
        const alt = c(st, 'alternate');
        if (cons) this.statement(cons, scope, [...guard, ...tc.t], fnPath);
        if (alt) this.statement(alt, scope, [...guard, ...tc.f], fnPath);
        return;
      }
      case 'BlockStatement':
        return this.statementList(csn(st, 'body'), scope, guard, fnPath);
      case 'VariableDeclaration':
        return this.varDecl(st, scope, guard, fnPath);
      case 'FunctionDeclaration': {
        const id = nameOf(c(st, 'id'));
        const fn = this.walkFunction(st, id, null, scope, fnPath, guard);
        if (id) this.declare(this.fnScope(scope), id, { kind: 'fn', fn });
        return;
      }
      case 'ForOfStatement':
      case 'ForInStatement':
        return this.forOf(st, scope, guard, fnPath);
      case 'ReturnStatement': {
        const arg = c(st, 'argument');
        const fn = fnPath[fnPath.length - 1];
        if (arg && fn) fn.returns.push({ expr: arg, scope });
        if (arg) this.expr(arg, scope, guard, fnPath);
        return;
      }
      case 'TryStatement': {
        const handler = c(st, 'handler');
        for (const k of ['block', 'finalizer']) {
          const b = c(st, k);
          if (b) this.statement(b, scope, guard, fnPath);
        }
        if (handler) {
          this.declarePattern(this.fnScope(scope), c(handler, 'param'), null);
          const hb = c(handler, 'body');
          if (hb) this.statement(hb, scope, guard, fnPath);
        }
        return;
      }
      case 'SwitchStatement': {
        const disc = c(st, 'discriminant');
        if (disc) this.expr(disc, scope, guard, fnPath);
        for (const sc of csn(st, 'cases')) {
          const t = c(sc, 'test');
          if (t) this.expr(t, scope, guard, fnPath);
          this.statementList(csn(sc, 'consequent'), scope, guard, fnPath);
        }
        return;
      }
      case 'ClassDeclaration': {
        const id = nameOf(c(st, 'id'));
        if (id) this.declare(this.fnScope(scope), id, { kind: 'unknown' });
        return this.generic(st, scope, guard, fnPath);
      }
      case 'ExpressionStatement': {
        const e = c(st, 'expression');
        if (e) this.expr(e, scope, guard, fnPath);
        return;
      }
      default:
        return this.generic(st, scope, guard, fnPath);
    }
  }

  /** Descent for anything not modelled: statements go through `statement`, the rest through `expr`. */
  private generic(n: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    for (const ch of children(n)) {
      if (ch.type.endsWith('Statement') || ch.type.endsWith('Declaration'))
        this.statement(ch, scope, guard, fnPath);
      else this.expr(ch, scope, guard, fnPath);
    }
  }

  private lookupFns(name: string, scope: Scope): Fn[] {
    let sc: Scope | null = scope;
    while (sc) {
      const bs = sc.names.get(name);
      if (bs) return bs.flatMap((b) => (b.kind === 'fn' ? [b.fn] : []));
      sc = sc.parent;
    }
    return [];
  }

  private property(e: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    const key = c(e, 'key');
    const v = unwrap(c(e, 'value'));
    if (e['computed'] === true && key) this.expr(key, scope, guard, fnPath);
    if (v && FN_TYPES.has(v.type)) this.walkFunction(v, null, propName(key), scope, fnPath, guard);
    else if (v) this.expr(v, scope, guard, fnPath);
  }

  private expr(e: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    const t = e.type;
    if (FN_TYPES.has(t)) {
      this.walkFunction(e, nameOf(c(e, 'id')), null, scope, fnPath, guard);
      return;
    }
    switch (t) {
      case 'Identifier': {
        const name = s(e, 'name') ?? '';
        this.ref(name);
        this.fnRefs.push({ name, scope, guard, fnPath });
        return;
      }
      case 'MemberExpression': {
        const o = c(e, 'object');
        const p = c(e, 'property');
        if (o) this.expr(o, scope, guard, fnPath);
        if (e['computed'] === true && p) this.expr(p, scope, guard, fnPath);
        return;
      }
      case 'Property':
      case 'MethodDefinition':
      case 'PropertyDefinition':
        return this.property(e, scope, guard, fnPath);
      case 'AssignmentExpression': {
        const left = c(e, 'left');
        const right = c(e, 'right');
        const lname = nameOf(left);
        if (lname && right) {
          this.pendingAssign.push({ scope, name: lname, b: { kind: 'expr', expr: right, scope } });
          this.ref(lname);
        } else if (left) this.expr(left, scope, guard, fnPath);
        if (right) this.expr(right, scope, guard, fnPath);
        return;
      }
      case 'ConditionalExpression':
      case 'LogicalExpression':
        return this.branching(e, scope, guard, fnPath);
      case 'CallExpression':
      case 'NewExpression':
        this.call(e, scope, guard, fnPath);
        for (const ch of children(e)) this.expr(ch, scope, guard, fnPath);
        return;
      case 'ImportExpression': {
        const spec = strLit(c(e, 'source'));
        if (spec)
          this.m.imports.push({
            source: this.a.resolveSpec(this.m.file, spec),
            locals: new Map(),
            all: true,
            unit: this.unit,
          });
        return;
      }
      default:
        if (t.endsWith('Statement') || t.endsWith('Declaration'))
          this.statement(e, scope, guard, fnPath);
        else for (const ch of children(e)) this.expr(ch, scope, guard, fnPath);
    }
  }

  private branching(e: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    if (e.type === 'ConditionalExpression') {
      const test = c(e, 'test');
      if (test) this.expr(test, scope, guard, fnPath);
      const tc = this.tests(test, scope);
      const cons = c(e, 'consequent');
      const alt = c(e, 'alternate');
      if (cons) this.expr(cons, scope, [...guard, ...tc.t], fnPath);
      if (alt) this.expr(alt, scope, [...guard, ...tc.f], fnPath);
      return;
    }
    const left = c(e, 'left');
    const right = c(e, 'right');
    if (left) this.expr(left, scope, guard, fnPath);
    const extra = s(e, 'operator') === '&&' ? this.tests(left, scope).t : [];
    if (right) this.expr(right, scope, [...guard, ...extra], fnPath);
  }

  private call(e: Node, scope: Scope, guard: Clause[], fnPath: Fn[]): void {
    const callee = c(e, 'callee');
    const args = cs(e, 'arguments');
    this.m.calls.push({ callee, args, scope, guard, fnPath });
    const ev = new Evaluator(this.a, this.m);
    // `xs.push(v)` is a binding of `xs`: a later `for (const x of xs)` takes v's origin.
    const u = unwrap(callee);
    const obj = u?.type === 'MemberExpression' ? nameOf(unwrap(c(u, 'object'))) : null;
    if (obj && ['push', 'unshift'].includes(propName(c(u, 'property')) ?? '')) {
      for (const a of args)
        if (a && a.type !== 'SpreadElement')
          this.pendingAssign.push({ scope, name: obj, b: { kind: 'expr', expr: a, scope } });
    }
    if (e.type === 'CallExpression' && nameOf(unwrap(callee)) === 'require') {
      const spec = strLit(args[0]);
      if (spec)
        this.m.imports.push({
          source: this.a.resolveSpec(this.m.file, spec),
          locals: new Map(),
          all: true,
          unit: this.unit,
        });
      return;
    }
    const canon = callee ? ev.canonical(callee, scope) : null;
    if (!canon) return;
    const line = this.lineOf(e.start);
    const add = (sink: string, node: Node, value: (x: Evaluator) => Val): void => {
      this.m.sites.push({ line, sink, node, value, scope, guard, fnPath, unit: this.unit });
    };
    const fsm = /^fs\.(?:promises\.)?([A-Za-z]+?)(?:Sync)?$/.exec(canon);
    if (fsm) {
      const base = fsm[1] ?? '';
      const idx = FS_SINKS[base];
      if (!idx) return;
      if (base === 'open' && !/[wa+]/.test(strLit(args[1]) ?? '')) return;
      for (const i of idx) {
        const arg = args[i];
        if (arg) add(`fs.${base}`, arg, (x) => x.ev(arg, scope));
      }
      return;
    }
    const cpm = /^cp\.(execSync|exec|execFileSync|execFile|spawnSync|spawn|fork)$/.exec(canon);
    if (!cpm) return;
    this.spawnEdges(args, scope);
    const shell = cpm[1] === 'execSync' || cpm[1] === 'exec';
    const argList = unwrap(args[1]);
    const hasArray = !shell && argList?.type === 'ArrayExpression';
    const optsIdx = shell ? 1 : hasArray ? 2 : 1;
    const opts = args[optsIdx] ?? null;
    const run = { e, args, scope, shell, hasArray, opts };
    for (const target of this.mutatorRun(run)) add(`exec:${target.prog}`, e, target.val);
  }

  private mutatorRun(run: {
    args: (Node | null)[];
    scope: Scope;
    shell: boolean;
    hasArray: boolean;
    opts: Node | null;
  }): MutTarget[] {
    const ev = new Evaluator(this.a, this.m);
    let words = ev.words(run.args[0] ?? null, run.scope);
    if (run.hasArray)
      words = [
        ...words,
        ...csn(unwrap(run.args[1]), 'elements').map((el) => ev.word(el, run.scope)),
      ];
    const cwd = ev.optionCwd(run.opts, run.scope);
    return mutatorTargets(this.a.mutators, words, cwd);
  }

  private spawnEdges(args: (Node | null)[], scope: Scope): void {
    const strings: string[] = [];
    const flags: string[] = [];
    const seen = new Set<Node>();
    const collect = (n: Node, depth: number): void => {
      if (seen.has(n)) return;
      seen.add(n);
      const lit = n.type === 'Literal' ? s(n, 'value') : null;
      if (lit !== null) {
        strings.push(lit);
        if (lit.startsWith('--')) flags.push(lit);
      } else if (n.type === 'TemplateElement') strings.push(s(c(n, 'value'), 'cooked') ?? '');
      else if (n.type === 'Identifier' && depth < 2) {
        const name = s(n, 'name') ?? '';
        let sc: Scope | null = scope;
        while (sc && !sc.names.has(name)) sc = sc.parent;
        for (const b of sc?.names.get(name) ?? [])
          if (b.kind === 'expr') collect(b.expr, depth + 1);
      }
      for (const ch of children(n)) collect(ch, depth);
    };
    for (const a of args) if (a) collect(a, 0);
    for (const str of strings) {
      for (const tok of str.split(/\s+/)) {
        const f = this.a.resolveScript(this.m.file, tok.replace(/^['"]|['"]$/g, ''));
        if (f && f !== this.m.file) this.m.spawns.push({ file: f, argv: flags, unit: this.unit });
      }
    }
  }
}

// --------------------------------------------------------------------------- evaluation

interface Word {
  text: string | null;
  val: Val;
}

class Evaluator {
  private readonly a: Analyzer;
  private readonly m: Module;
  private readonly memo = new Map<string, Val>();
  private readonly busy = new Set<string>();

  /** One call pinned per function: that call's arguments are the parameters' values, for a per-call verdict. */
  private readonly ctx: Map<number, CallSite>;

  constructor(a: Analyzer, m: Module, ctx: Map<number, CallSite> = new Map()) {
    this.a = a;
    this.m = m;
    this.ctx = ctx;
  }

  isExported(fn: Fn): boolean {
    return fn.name !== null && new Set(this.m.exports.values()).has(fn.name);
  }

  private lookup(name: string, scope: Scope): Binding[] | null {
    let sc: Scope | null = scope;
    while (sc) {
      const bs = sc.names.get(name);
      if (bs) return bs;
      sc = sc.parent;
    }
    return null;
  }

  private importOf(
    name: string,
    scope: Scope
  ): { source: string | null; spec: string; imported: string } | null {
    for (const b of this.lookup(name, scope) ?? []) if (b.kind === 'import') return b;
    return null;
  }

  private family(source: string | null): string | null {
    for (const [set, fam] of FAMILIES) if (source && set.has(source)) return fam;
    return null;
  }

  /** `path.join`, `fs.writeFileSync`, `cp.spawnSync`, ... with the import resolved. */
  canonical(callee: Node, scope: Scope): string | null {
    const parts: string[] = [];
    let x = unwrap(callee);
    while (x?.type === 'MemberExpression') {
      const p = x['computed'] === true ? strLit(c(x, 'property')) : propName(c(x, 'property'));
      if (p === null) return null;
      parts.unshift(p);
      x = unwrap(c(x, 'object'));
    }
    const head = nameOf(x);
    if (!head) return null;
    const imp = this.importOf(head, scope);
    let lead = head;
    if (imp) {
      const fam = this.family(imp.spec);
      if (fam)
        lead = imp.imported === '*' || imp.imported === 'default' ? fam : `${fam}.${imp.imported}`;
    }
    return [lead, ...parts].join('.').replace(/^path\.(posix|win32)\./, 'path.');
  }

  private bindingVal(b: Binding): Val {
    switch (b.kind) {
      case 'expr':
        return this.ev(b.expr, b.scope);
      case 'elem': {
        const r = unwrap(b.expr);
        if (r?.type === 'ArrayExpression')
          return csn(r, 'elements')
            .map((el) => this.ev(el, b.scope))
            .reduce(combine, NONE);
        return this.ev(b.expr, b.scope);
      }
      case 'elemAt': {
        const rows = unwrap(b.expr);
        if (rows?.type !== 'ArrayExpression') return this.ev(b.expr, b.scope);
        return csn(rows, 'elements')
          .map((row) => {
            const r = unwrap(row);
            const cell = r?.type === 'ArrayExpression' ? cs(r, 'elements')[b.index] : row;
            return cell ? this.ev(cell, b.scope) : NONE;
          })
          .reduce(combine, NONE);
      }
      case 'param':
        return this.paramVal(b.fn, b.index, b.dflt, b.scope);
      case 'import':
        return this.importVal(b.source, b.imported, 0);
      case 'fn':
        return NONE;
      default:
        return UNRES;
    }
  }

  /** A module constant across one import hop (re-exports followed one more). */
  importVal(source: string | null, imported: string, depth: number): Val {
    if (source === null || depth > 1 || imported === '*' || isProduct(source)) return UNRES;
    const m = this.a.module(source);
    if (m.error) return UNRES;
    const local = m.exports.get(imported);
    const name = local === undefined || local === '<top>' ? imported : local;
    const bs = m.top.names.get(name);
    const sub = new Evaluator(this.a, m);
    if (!bs) {
      const re = m.reexports.get(imported);
      return re ? sub.importVal(re.source, re.imported, depth + 1) : UNRES;
    }
    return bs
      .map((b) =>
        b.kind === 'import' ? sub.importVal(b.source, b.imported, depth + 1) : sub.bindingVal(b)
      )
      .reduce(combine, NONE);
  }

  /** A parameter's origin: the pinned call's argument, or every call's combined -- where ANY tree argument makes it TREE (PLAN section 3.4 step 2); "temp wins" is for the components of one path, not the alternatives of many calls. */
  private paramVal(fn: Fn, index: number, dflt: Node | null, scope: Scope): Val {
    const pinned = this.ctx.get(fn.id);
    const calls = pinned
      ? [pinned]
      : this.m.calls.filter((call) => this.callTargets(call).includes(fn));
    const vals = calls.map((call) => {
      const arg = call.args[index];
      if (!arg || arg.type === 'SpreadElement') return dflt ? this.ev(dflt, scope) : NONE;
      return this.ev(arg, call.scope);
    });
    if (vals.length === 0) return dflt ? combine(UNRES, this.ev(dflt, scope)) : UNRES;
    const tree = vals.filter((v) => v.o !== 'NONE' && finalOrigin(v) === 'TREE');
    if (tree.length > 0) return tree.length === 1 && tree[0] ? tree[0] : { o: 'TREE', rel: null };
    const out = vals.reduce(combine, NONE);
    return out.o === 'NONE' ? UNRES : out;
  }

  /** The module-local functions a call may invoke: by name, or by callback property key. */
  callTargets(call: CallSite): Fn[] {
    const callee = unwrap(call.callee);
    const name = nameOf(callee);
    if (name)
      return (this.lookup(name, call.scope) ?? []).flatMap((b) => (b.kind === 'fn' ? [b.fn] : []));
    if (callee?.type === 'MemberExpression' && callee['computed'] !== true) {
      const k = propName(c(callee, 'property'));
      if (k) return this.m.fns.filter((f) => f.key === k);
    }
    return [];
  }

  ev(e: Node, scope: Scope): Val {
    const key = `${scope.id}:${e.start}:${e.end}:${e.type}`;
    const hit = this.memo.get(key);
    if (hit) return hit;
    if (this.busy.has(key)) return NONE;
    this.busy.add(key);
    const v = this.ev0(e, scope);
    this.busy.delete(key);
    this.memo.set(key, v);
    return v;
  }

  private evOpt(e: Node | null, scope: Scope): Val {
    return e ? this.ev(e, scope) : NONE;
  }

  private ev0(e0: Node, scope: Scope): Val {
    const e = unwrap(e0);
    if (!e) return NONE;
    switch (e.type) {
      case 'Literal': {
        const v = s(e, 'value');
        return v === null ? NONE : literal(v);
      }
      case 'TemplateLiteral':
        return this.concat(this.pieces(e), scope);
      case 'BinaryExpression':
        return s(e, 'operator') === '+' ? this.concat(this.pieces(e), scope) : NONE;
      case 'Identifier':
        return this.identVal(s(e, 'name') ?? '', scope);
      case 'LogicalExpression':
        return combine(this.evOpt(c(e, 'left'), scope), this.evOpt(c(e, 'right'), scope));
      case 'ConditionalExpression': {
        const both = combine(
          this.evOpt(c(e, 'consequent'), scope),
          this.evOpt(c(e, 'alternate'), scope)
        );
        // `process.env.OUT ? path.resolve(process.env.OUT) : <tracked default>`: which branch runs is the INVOKER's choice, and the invoker is often a wrapper that always overrides. Not a proven tree write: UNRESOLVED, for a pragma to say which.
        return both.o === 'TREE' && this.invocationControlled(c(e, 'test'), scope) ? UNRES : both;
      }
      case 'MemberExpression':
        return this.memberVal(e, scope);
      case 'NewExpression':
        return this.newVal(e, scope);
      case 'CallExpression':
        return this.callVal(e, scope);
      default:
        return UNRES;
    }
  }

  /** Does a test read the process's own argv or environment, directly or through a name bound once? */
  private invocationControlled(test: Node | null, scope: Scope): boolean {
    if (!test) return false;
    const src = this.m.src.slice(test.start, test.end);
    if (/process\.(env|argv)/.test(src)) return true;
    for (const id of src.match(/[A-Za-z_$][\w$]*/g) ?? []) {
      const bs = this.lookup(id, scope);
      const b = bs?.length === 1 ? bs[0] : null;
      if (
        b?.kind === 'expr' &&
        /process\.(env|argv)/.test(this.m.src.slice(b.expr.start, b.expr.end))
      )
        return true;
    }
    return false;
  }

  private identVal(name: string, scope: Scope): Val {
    if (name === '__dirname') return treeAt(path.posix.dirname(this.m.file));
    if (name === '__filename') return treeAt(this.m.file);
    if (name === 'undefined') return NONE;
    const bs = this.lookup(name, scope);
    if (!bs) return UNRES;
    return bs.map((b) => this.bindingVal(b)).reduce(combine, NONE);
  }

  private memberVal(e: Node, scope: Scope): Val {
    const o = unwrap(c(e, 'object'));
    const p = e['computed'] === true ? strLit(c(e, 'property')) : propName(c(e, 'property'));
    if (o?.type === 'MetaProperty') {
      if (p === 'dirname') return treeAt(path.posix.dirname(this.m.file));
      if (p === 'filename' || p === 'url') return treeAt(this.m.file);
      return UNRES;
    }
    if (
      o?.type === 'MemberExpression' &&
      nameOf(c(o, 'object')) === 'process' &&
      propName(c(o, 'property')) === 'env'
    ) {
      if (p === 'TMPDIR') return TEMP;
      return p === 'HOME' ? OUTSIDE : UNRES;
    }
    const head = nameOf(o);
    if (head && p) {
      const imp = this.importOf(head, scope);
      if (imp?.imported === '*') return this.importVal(imp.source, p, 0);
    }
    // A table of paths: `DIRS.client` is that property, `DIRS[k]` any of them.
    const obj = this.objectNode(o, scope, 0);
    if (obj) {
      const props = csn(obj.node, 'properties').filter((pr) => pr.type === 'Property');
      const pick = p === null ? props : props.filter((pr) => propName(c(pr, 'key')) === p);
      const vals = pick.map((pr) => {
        const v = c(pr, 'value');
        return v ? this.ev(v, obj.scope) : NONE;
      });
      if (vals.length > 0) return vals.reduce(combine, NONE);
    }
    return UNRES;
  }

  /** The object literal an expression names: a const bound to one, or a property of one. */
  private objectNode(
    e: Node | null,
    scope: Scope,
    depth: number
  ): { node: Node; scope: Scope } | null {
    const x = unwrap(e);
    if (!x || depth > 3) return null;
    if (x.type === 'ObjectExpression') return { node: x, scope };
    const name = nameOf(x);
    if (name) {
      const bs = this.lookup(name, scope);
      const b = bs?.length === 1 ? bs[0] : null;
      return b?.kind === 'expr' ? this.objectNode(b.expr, b.scope, depth + 1) : null;
    }
    if (x.type === 'CallExpression') {
      // `const big = oversizedRange()` where the function returns `{ dir, base, tip }`.
      for (const f of this.callTargets({
        callee: c(x, 'callee'),
        args: cs(x, 'arguments'),
        scope,
        guard: [],
        fnPath: [],
      })) {
        for (const r of f.returns) {
          const hit = this.objectNode(r.expr, r.scope, depth + 1);
          if (hit) return hit;
        }
      }
      return null;
    }
    if (x.type === 'MemberExpression' && x['computed'] !== true) {
      const outer = this.objectNode(c(x, 'object'), scope, depth + 1);
      const key = propName(c(x, 'property'));
      const prop = outer
        ? csn(outer.node, 'properties').find(
            (pr) => pr.type === 'Property' && propName(c(pr, 'key')) === key
          )
        : null;
      return prop && outer ? this.objectNode(c(prop, 'value'), outer.scope, depth + 1) : null;
    }
    return null;
  }

  private newVal(e: Node, scope: Scope): Val {
    const args = cs(e, 'arguments');
    if (nameOf(unwrap(c(e, 'callee'))) === 'URL' && args.length >= 2) {
      const base = this.evOpt(args[1] ?? null, scope);
      const rel = strLit(args[0]);
      if (isTreeish(base) && base.rel !== null && rel !== null)
        return treeAt(path.posix.join(path.posix.dirname(base.rel), rel));
      return combine(base, UNRES);
    }
    return UNRES;
  }

  private callVal(e: Node, scope: Scope): Val {
    const callee = c(e, 'callee');
    const canon = callee ? (this.canonical(callee, scope) ?? '') : '';
    const args = cs(e, 'arguments');
    const av = (i: number): Val => this.evOpt(args[i] ?? null, scope);
    const all = (): Val[] => args.map((a) => this.evOpt(a, scope));
    if (canon === 'path.join') return joinVals(all(), false);
    if (canon === 'path.resolve') return joinVals(all(), true);
    if (canon === 'path.normalize' || canon === 'url.fileURLToPath' || canon === 'String')
      return av(0);
    if (canon === 'path.dirname') return this.dirnameVal(av(0));
    if (canon === 'path.basename' || canon === 'path.relative' || canon === 'path.extname')
      return { o: 'REL', rel: null };
    if (canon === 'os.tmpdir') return TEMP;
    if (canon === 'os.homedir') return OUTSIDE;
    if (/^fs(\.promises)?\.mkdtemp(Sync)?$/.test(canon)) {
      const p = av(0);
      return p.o === 'TREE' || p.o === 'REL'
        ? { o: 'TREE', rel: null }
        : p.o === 'SCRATCH'
          ? { o: 'SCRATCH', rel: null }
          : TEMP;
    }
    if (/^fs(\.promises)?\.realpath(Sync)?(\.native)?$/.test(canon)) return av(0);
    if (canon === 'process.cwd') return treeAt('');
    const u = unwrap(callee);
    const name = nameOf(u);
    if (name && ROOT_FN_NAMES.has(name)) return treeAt('');
    if (u?.type === 'MemberExpression' && STRING_METHODS.has(propName(c(u, 'property')) ?? '')) {
      return this.evOpt(c(u, 'object'), scope);
    }
    const targets = this.callTargets({ callee, args, scope, guard: [], fnPath: [] });
    if (targets.length > 0) {
      let out = NONE;
      for (const f of targets)
        for (const r of f.returns) out = combine(out, this.ev(r.expr, r.scope));
      return out.o === 'NONE' ? UNRES : out;
    }
    return UNRES;
  }

  private dirnameVal(v: Val): Val {
    if (v.rel === null) return v;
    if (v.o === 'REL') return { o: 'REL', rel: path.posix.dirname(v.rel) };
    if (isTreeish(v)) return treeAt(v.rel === '' ? '..' : path.posix.dirname(v.rel));
    return v;
  }

  /** A template literal or `+` chain as literal text and expression nodes. */
  private pieces(e: Node): (string | Node)[] {
    const x = unwrap(e);
    if (x?.type === 'TemplateLiteral') {
      const exprs = csn(x, 'expressions');
      const out: (string | Node)[] = [];
      csn(x, 'quasis').forEach((q, i) => {
        out.push(s(c(q, 'value'), 'cooked') ?? '');
        const ex = exprs[i];
        if (ex) out.push(ex);
      });
      return out;
    }
    if (x?.type === 'BinaryExpression' && s(x, 'operator') === '+') {
      const l = c(x, 'left');
      const r = c(x, 'right');
      return [...(l ? this.pieces(l) : []), ...(r ? this.pieces(r) : [])];
    }
    const lit = strLit(x);
    if (lit !== null) return [lit];
    return x ? [x] : [];
  }

  private concat(ps: (string | Node)[], scope: Scope): Val {
    const nodes = ps.filter((p): p is Node => typeof p !== 'string');
    if (nodes.length === 0) return literal(ps.join(''));
    let out = nodes.map((n) => this.ev(n, scope)).reduce(combine, NONE);
    const first = ps.find((p) => p !== '');
    if (typeof first === 'string') out = combine(out, literal(first));
    // `${ROOT}/x/y`: a tree base followed only by literal text keeps its path.
    const head = nodes[0];
    if (ps[0] === '' && nodes.length === 1 && head && isTreeish(out)) {
      const base = this.ev(head, scope);
      const tail = ps
        .slice(2)
        .filter((p): p is string => typeof p === 'string')
        .join('');
      if (isTreeish(base) && base.rel !== null)
        return treeAt(path.posix.join(base.rel, tail.replace(/^\//, '')));
    }
    return out.o === 'TREE' || out.o === 'SCRATCH' || out.o === 'REL'
      ? { o: out.o, rel: null }
      : out;
  }

  word(n: Node, scope: Scope): Word {
    const lit = strLit(n);
    if (lit !== null) return { text: lit, val: literal(lit) };
    return { text: null, val: this.ev(n, scope) };
  }

  /** A command (string literal, template, `+` chain, or array) split into words, each with its value. */
  words(n: Node | null, scope: Scope): Word[] {
    const x = unwrap(n);
    if (!x) return [];
    if (x.type === 'ArrayExpression') return csn(x, 'elements').map((el) => this.word(el, scope));
    const ps = this.pieces(x);
    // A single non-literal command (a variable holding the whole string) is opaque.
    if (ps.length === 1 && typeof ps[0] !== 'string') {
      const only = ps[0];
      return only && typeof only !== 'string' && this.lookupLiteral(only, scope)
        ? this.words(this.lookupLiteral(only, scope), scope)
        : [];
    }
    const out: Word[] = [];
    let text = '';
    let nodes: Node[] = [];
    let open = false;
    const flush = (): void => {
      if (!open) return;
      const litVal = text ? literal(text) : NONE;
      out.push(
        nodes.length === 0
          ? { text, val: litVal }
          : { text: null, val: nodes.map((nn) => this.ev(nn, scope)).reduce(combine, litVal) }
      );
      text = '';
      nodes = [];
      open = false;
    };
    for (const p of ps) {
      if (typeof p !== 'string') {
        open = true;
        nodes.push(p);
        continue;
      }
      for (const tok of p.split(/(\s+)/)) {
        if (/^\s+$/.test(tok)) flush();
        else if (tok) {
          open = true;
          text += tok.replace(/^['"]|['"]$/g, '');
        }
      }
    }
    flush();
    return out;
  }

  /** An identifier bound once to a literal command string or array. */
  private lookupLiteral(n: Node, scope: Scope): Node | null {
    const name = nameOf(n);
    const bs = name ? this.lookup(name, scope) : null;
    if (bs?.length !== 1) return null;
    const b = bs[0];
    if (b?.kind !== 'expr') return null;
    const x = unwrap(b.expr);
    return x && (x.type === 'ArrayExpression' || strLit(x) !== null || x.type === 'TemplateLiteral')
      ? x
      : null;
  }

  optionCwd(opts: Node | null, scope: Scope): Val {
    const o = unwrap(opts);
    if (!o) return treeAt('');
    if (o.type !== 'ObjectExpression') return combine(UNRES, treeAt(''));
    for (const p of csn(o, 'properties')) {
      const v = c(p, 'value');
      if (p.type === 'Property' && propName(c(p, 'key')) === 'cwd' && v) return this.ev(v, scope);
    }
    return treeAt('');
  }

  // ----------------------------------------------------------------- guards

  /** The flag clauses under which a test is TRUE (t) or FALSE (f). A clause holds when ANY flag in it is passed. */
  testClauses(e0: Node | null, scope: Scope, depth: number): { t: Clause[]; f: Clause[] } {
    const e = unwrap(e0);
    const none = { t: [] as Clause[], f: [] as Clause[] };
    if (!e || depth > 3) return none;
    if (e.type === 'UnaryExpression' && s(e, 'operator') === '!') {
      const r = this.testClauses(c(e, 'argument'), scope, depth + 1);
      return { t: r.f, f: r.t };
    }
    if (e.type === 'CallExpression') {
      const callee = unwrap(c(e, 'callee'));
      if (callee?.type === 'MemberExpression' && propName(c(callee, 'property')) === 'includes') {
        const f = strLit(cs(e, 'arguments')[0]);
        if (f?.startsWith('-')) return { t: [[f]], f: [[`!${f}`]] };
      }
      return none;
    }
    if (e.type === 'BinaryExpression') {
      const op = s(e, 'operator') ?? '';
      // `argv.indexOf('--x') !== -1`, directly or through `const at = ... argv.indexOf('--x')`.
      const idx = this.indexFlags(c(e, 'left'), scope, 0);
      const bound = c(e, 'right');
      const rhs =
        bound?.type === 'UnaryExpression' && s(bound, 'operator') === '-'
          ? -Number(c(bound, 'argument')?.['value'])
          : Number(bound?.['value']);
      if (idx.length > 0 && Number.isFinite(rhs)) {
        const present =
          ((op === '!==' || op === '!=') && rhs === -1) ||
          (op === '>=' && rhs === 0) ||
          (op === '>' && rhs === -1);
        const absent = (op === '===' || op === '==') && rhs === -1;
        if (present) return { t: [idx], f: idx.map((x) => [`!${x}`]) };
        if (absent) return { t: idx.map((x) => [`!${x}`]), f: [idx] };
      }
      const f = strLit(c(e, 'left')) ?? strLit(c(e, 'right'));
      if (!f?.startsWith('--')) return none;
      if (op === '===' || op === '==') return { t: [[f]], f: [[`!${f}`]] };
      if (op === '!==' || op === '!=') return { t: [[`!${f}`]], f: [[f]] };
      return none;
    }
    if (e.type === 'LogicalExpression') {
      const a = this.testClauses(c(e, 'left'), scope, depth + 1);
      const b = this.testClauses(c(e, 'right'), scope, depth + 1);
      const one = (x: Clause[], y: Clause[]): Clause[] =>
        x.length === 1 && y.length === 1 ? [[...(x[0] ?? []), ...(y[0] ?? [])]] : [];
      if (s(e, 'operator') === '&&') return { t: [...a.t, ...b.t], f: one(a.f, b.f) };
      if (s(e, 'operator') === '||') return { t: one(a.t, b.t), f: [...a.f, ...b.f] };
      return none;
    }
    const name = nameOf(e);
    const bs = name ? this.lookup(name, scope) : null;
    if (bs?.length !== 1) return none;
    const b = bs[0];
    if (b?.kind === 'expr') return this.testClauses(b.expr, b.scope, depth + 1);
    if (b?.kind === 'param') return { t: [[`@param:${b.fn.id}:${b.index}`]], f: [] };
    return none;
  }

  /** The flags an index expression looks up: `argv.indexOf('--x')`, a ternary of two, or a name bound once to either. */
  private indexFlags(e0: Node | null, scope: Scope, depth: number): string[] {
    const e = unwrap(e0);
    if (!e || depth > 3) return [];
    if (e.type === 'CallExpression') {
      const callee = unwrap(c(e, 'callee'));
      const f = strLit(cs(e, 'arguments')[0]);
      return callee?.type === 'MemberExpression' &&
        propName(c(callee, 'property')) === 'indexOf' &&
        f?.startsWith('-')
        ? [f]
        : [];
    }
    if (e.type === 'ConditionalExpression') {
      const a = this.indexFlags(c(e, 'consequent'), scope, depth + 1);
      const b = this.indexFlags(c(e, 'alternate'), scope, depth + 1);
      return a.length > 0 && b.length > 0 ? [...a, ...b] : [];
    }
    const name = nameOf(e);
    const bs = name ? this.lookup(name, scope) : null;
    const b = bs?.length === 1 ? bs[0] : null;
    return b?.kind === 'expr' ? this.indexFlags(b.expr, b.scope, depth + 1) : [];
  }

  /** Resolve `@param` placeholders: a guard on a parameter holds when EVERY module-local call passes a flag-derived (or literal false) value. */
  resolveGuard(guard: Clause[]): Clause[] {
    const out: Clause[] = [];
    for (const clause of guard) {
      const flags = this.resolveClause(clause);
      if (flags && flags.length > 0) out.push([...new Set(flags)]);
    }
    return out;
  }

  private resolveClause(clause: Clause): string[] | null {
    const flags: string[] = [];
    for (const f of clause) {
      const m = /^@param:(\d+):(\d+)$/.exec(f);
      if (!m) {
        flags.push(f);
        continue;
      }
      const fn = this.m.fns.find((x) => x.id === Number(m[1]));
      const idx = Number(m[2]);
      const calls = fn ? this.m.calls.filter((call) => this.callTargets(call).includes(fn)) : [];
      if (calls.length === 0) return null;
      for (const call of calls) {
        const arg = unwrap(call.args[idx]);
        if (arg?.type === 'Literal' && arg['value'] === false) {
          flags.push('<never>');
          continue;
        }
        const tc = arg ? this.testClauses(arg, call.scope, 0) : { t: [] as Clause[] };
        if (tc.t.length !== 1) return null;
        flags.push(...(tc.t[0] ?? []));
      }
    }
    return flags;
  }

  /** A function every module-local reference to which is guarded is itself guarded, by the union of those flags. */
  /**
   * The clauses a function's REFERENCES impose on everything inside it: the function runs when ANY reference runs, a reference runs when ALL its clauses hold, so the guard is an OR of ANDs, distributed back into clauses (bounded; past the bound it is unguarded, the safe direction). Transitive through the functions enclosing each reference. An exported function is reachable from outside and is not guarded by its module-local calls.
   */
  fnGuard(fnPath: Fn[], visiting: Set<number> = new Set()): Clause[] {
    const exported = new Set(this.m.exports.values());
    const out: Clause[] = [];
    for (const fn of fnPath) {
      if (
        fn.refGuards.length === 0 ||
        visiting.has(fn.id) ||
        (fn.name !== null && exported.has(fn.name))
      )
        continue;
      const inner = new Set([...visiting, fn.id]);
      const perRef: Clause[][] = [];
      for (const r of fn.refGuards) {
        const clauses = [...this.resolveGuard(r.guard), ...this.fnGuard(r.fnPath, inner)];
        if (clauses.length === 0) {
          perRef.length = 0;
          break;
        }
        perRef.push(clauses);
      }
      if (perRef.length > 0) out.push(...distribute(perRef));
    }
    return out;
  }
}

/** OR over references of (AND of clauses), as AND of clauses. Empty (unguarded) past `bound`. */
function distribute(perRef: Clause[][], bound = 64): Clause[] {
  let out: Clause[] = [[]];
  for (const clauses of perRef) {
    if (out.length * clauses.length > bound) return [];
    out = out.flatMap((a) => clauses.map((cl) => [...new Set([...a, ...cl])].sort()));
  }
  return out.filter((cl) => cl.length > 0);
}

// --------------------------------------------------------------------------- mutators

interface MutTarget {
  prog: string;
  val: (ev: Evaluator) => Val;
}

/** The written words of a command, by the shared table. `cwd` is the directory the command runs in. */
function mutatorTargets(mt: Mutators, words0: Word[], cwd: Val): MutTarget[] {
  const text = (w: Word | undefined): string => w?.text ?? '';
  let words = words0;
  let prog = path.posix.basename(text(words[0]));
  if (prog === 'npx' && !(mt.install['npx'] ?? []).includes(text(words[1]))) {
    words = words.slice(1);
    while (words.length > 0 && text(words[0]).startsWith('-')) words = words.slice(1);
    prog = path.posix.basename(text(words[0]));
  }
  if (!prog) return [];
  const rest = words.slice(1);
  const nonflag = rest.filter((w) => w.text === null || !w.text.startsWith('-'));
  const last = rest[rest.length - 1];
  const at =
    (w: Word | undefined): ((ev: Evaluator) => Val) =>
    () =>
      w?.val ?? UNRES;
  if (prog === 'git') return gitTarget(mt, rest, cwd);
  if (mt.in_place[prog] !== undefined && rest.some((w) => /^-[A-Za-z]*i/.test(text(w))) && last)
    return [{ prog, val: at(last) }];
  if (mt.pair.includes(prog) && nonflag.length >= 2) return [{ prog, val: at(last) }];
  if (mt.list.includes(prog)) return nonflag.map((w) => ({ prog, val: at(w) }));
  const of = mt.output_flag[prog];
  if (of && text(rest[0]) === of.subcommand) {
    const i = rest.findIndex((w) => text(w) === of.flag);
    return i >= 0 ? [{ prog: `${prog} ${of.subcommand}`, val: at(rest[i + 1]) }] : [];
  }
  if ((mt.install[prog] ?? []).includes(text(rest[0])))
    return [{ prog: `${prog} ${text(rest[0])}`, val: () => cwd }];
  const wf = mt.write_flag[prog];
  if (wf && rest.some((w) => wf.includes(text(w).split('=')[0] ?? '')))
    return [{ prog, val: () => cwd }];
  const ex = mt.extract[prog];
  if (ex && rest.some((w) => !text(w).startsWith('--') && /^-?[A-Za-z]*x/.test(text(w)))) {
    const i = rest.findIndex((w) => text(w) === ex.dest);
    return [{ prog, val: i >= 0 ? at(rest[i + 1]) : () => cwd }];
  }
  return [];
}

function gitTarget(mt: Mutators, rest: Word[], cwd: Val): MutTarget[] {
  let i = 0;
  let target: Val = cwd;
  while (i < rest.length) {
    const t = rest[i]?.text ?? '';
    if (t === '-C') {
      target = rest[i + 1]?.val ?? UNRES;
      i += 2;
    } else if (t === '-c') i += 2;
    else if (t.startsWith('-')) i += 1;
    else break;
  }
  const sub = rest[i]?.text ?? '';
  return mt.git.subcommands.includes(sub) ? [{ prog: `git ${sub}`, val: () => target }] : [];
}

// --------------------------------------------------------------------------- invocations

/** Per lock entry, the (leaf, argv) pairs its `run` executes, by the resolver check:ci-parity uses. */
export function invocations(
  lockPath: string,
  root: string,
  pkgPath: string | null
): Record<string, { leaf: string; argv: string[] }[]> {
  const lock = JSON.parse(fs.readFileSync(lockPath, 'utf-8')) as { id: string; run: string }[];
  let u: ScriptUniverse;
  if (pkgPath) {
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8')) as {
      scripts?: Record<string, string>;
    };
    const tracked = new Set<string>();
    const walk = (d: string): void => {
      for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, ent.name);
        if (ent.isDirectory()) walk(p);
        else tracked.add(path.relative(root, p).split(path.sep).join('/'));
      }
    };
    walk(root);
    u = { byDir: new Map([['', pkg.scripts ?? {}]]), nameToDir: new Map(), tracked };
  } else u = loadScripts(root);
  const out: Record<string, { leaf: string; argv: string[] }[]> = {};
  for (const e of lock) out[e.id] = resolveInvocations(e.run, u);
  return out;
}

// --------------------------------------------------------------------------- selftest

interface Plant {
  label: string;
  files: Record<string, string>;
  entry: string;
  want: (sites: Site[], r: GroupResult) => boolean;
}

const PLANTS: Plant[] = [
  {
    label: 'C1: the lint-rule-liveness wave-2 shape is TREE at both sites',
    entry: 'a/b/c/gate.mjs',
    files: {
      'a/b/c/gate.mjs':
        "import fs from 'node:fs';\nimport path from 'node:path';\nconst HERE = import.meta.dirname;\nconst ROOT = path.resolve(HERE, '../../..');\nfor (const fx of [{ file: 'x.ts' }]) fs.appendFileSync(path.join(ROOT, fx.file), 'code');\nfs.writeFileSync(path.join(ROOT, 'private/account/src/__x.ts'), '');\n",
    },
    want: (st) =>
      st
        .filter((x) => x.origin === 'TREE')
        .map((x) => x.line)
        .join(',') === '5,6',
  },
  {
    label: "C1': the temp mirror with a decoy ROOT in the same join is TEMP",
    entry: 'g.mjs',
    files: {
      'g.mjs':
        "import fs from 'node:fs';\nimport os from 'node:os';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname, '..');\nconst mirrorRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'biome-plugin-liveness-'));\nfs.writeFileSync(path.join(mirrorRoot, ROOT, 'f'), '');\n",
    },
    want: (st) => st.length === 2 && st.every((x) => x.origin === 'TEMP'),
  },
  {
    label: 'C7: a type-only import does not pull the writer in',
    entry: 'g.ts',
    files: {
      'g.ts': "import type { T } from './lib';\nexport const x: T | null = null;\n",
      'lib.ts':
        "import fs from 'node:fs';\nexport type T = number;\nexport function save(): void { fs.writeFileSync('packages/www/src/data/m.json', ''); }\n",
    },
    want: (st, r) => st.length === 0 && !r.modules.includes('lib.ts'),
  },
  {
    label: "C7': a value import that calls the writer reports it, and only it",
    entry: 'g.ts',
    files: {
      'g.ts': "import { save } from './lib.js';\nsave();\n",
      'lib.ts':
        "import fs from 'node:fs';\nexport function save(): void { fs.writeFileSync('packages/www/src/data/m.json', ''); }\nexport function other(): void { fs.writeFileSync('other.json', ''); }\n",
    },
    want: (st) => st.length === 1 && st[0]?.origin === 'TREE' && st[0].line === 2,
  },
  {
    label: 'C9: execSync of sed -i on path.join(ROOT, f) is TREE; git status is no write',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import { execSync } from 'node:child_process';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname);\nexecSync('sed -i s/a/b/ ' + path.join(ROOT, 'f'));\nexecSync('git status');\n",
    },
    want: (st) => st.length === 1 && st[0]?.origin === 'TREE' && st[0].sink === 'exec:sed',
  },
  {
    label: 'MODE: argv.includes(--write), an alias, and the early-exit form each carry their flag',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import fs from 'node:fs';\nconst argv = process.argv.slice(2);\nconst write = argv.includes('--write');\nif (write) fs.writeFileSync('a.json', '');\nfunction f(): void {\n  if (!argv.includes('--fix')) return;\n  fs.writeFileSync('b.json', '');\n}\nf();\nfs.writeFileSync('c.json', '');\n",
    },
    want: (st) =>
      JSON.stringify(st.map((x) => [x.line, x.guard])) ===
      JSON.stringify([
        [4, [['--write']]],
        [7, [['--fix']]],
        [10, []],
      ]),
  },
  {
    label: 'CALLBACK: plant: (root) => ... takes root from c.plant(mkdtemp) and is TEMP',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import fs from 'node:fs';\nimport os from 'node:os';\nimport path from 'node:path';\nconst cases = [{ plant: (root: string) => fs.writeFileSync(path.join(root, 'x'), '') }];\nconst root = fs.mkdtempSync(path.join(os.tmpdir(), 'x-'));\nfor (const k of cases) k.plant(root);\n",
    },
    want: (st) => st.length === 2 && st[1]?.origin === 'TEMP',
  },
  {
    label:
      'C3 PARAM: a parameter called with the repo root is TREE; the same body called with mkdtemp is TEMP',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import fs from 'node:fs';\nimport os from 'node:os';\nimport path from 'node:path';\nfunction stage(root: string): void { fs.copyFileSync('a', path.join(root, 'x')); }\nfunction stage2(root: string): void { fs.copyFileSync('a', path.join(root, 'x')); }\nstage(process.cwd());\nstage2(fs.mkdtempSync(path.join(os.tmpdir(), 'y-')));\n",
    },
    want: (st) =>
      st
        .filter((x) => x.sink === 'fs.copyFile')
        .map((x) => x.origin)
        .join(',') === 'TREE,TEMP',
  },
  {
    label: 'C10 SCRATCH: .ci/cache under the root is scratch; packages/www/dist is tree',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import fs from 'node:fs';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname);\nfs.mkdirSync(path.join(ROOT, '.ci', 'cache', 'x'));\nfs.mkdirSync(path.join(ROOT, 'packages/www/dist'));\n",
    },
    want: (st) => st.map((x) => x.origin).join(',') === 'SCRATCH,TREE',
  },
  {
    label: 'BOUNDARY: product source is not entered, and is counted',
    entry: 'g.ts',
    files: {
      'g.ts': "import { w } from './packages/cli/src/w.js';\nw();\n",
      'packages/cli/src/w.ts':
        "import fs from 'node:fs';\nexport function w(): void { fs.writeFileSync('x', ''); }\n",
    },
    want: (st, r) => st.length === 0 && r.product.includes('packages/cli/src/w.ts'),
  },
  {
    label: 'SPAWN: a .py named in a spawnSync is a spawn edge, with its flags',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import { spawnSync } from 'node:child_process';\nspawnSync('python3', ['tool.py', '--x']);\n",
      'tool.py': 'print(1)\n',
    },
    want: (_st, r) =>
      r.spawns.length === 1 && r.spawns[0]?.file === 'tool.py' && r.spawns[0].argv.includes('--x'),
  },
  {
    label: 'ONE HOP: a ROOT constant imported from a sibling module is TREE',
    entry: 'g.ts',
    files: {
      'g.ts':
        "import fs from 'node:fs';\nimport path from 'node:path';\nimport { ROOT } from './paths.js';\nfs.writeFileSync(path.join(ROOT, 'f'), '');\n",
      'paths.js':
        "import path from 'node:path';\nexport const ROOT = path.resolve(import.meta.dirname);\n",
    },
    want: (st) => st.length === 1 && st[0]?.origin === 'TREE',
  },
];

function runPlant(tmp: string, p: Plant): { ok: boolean; detail: string } {
  const dir = fs.mkdtempSync(path.join(tmp, 'p-'));
  fs.mkdirSync(path.join(dir, '.ci', 'config'), { recursive: true });
  fs.copyFileSync(path.join(DEFAULT_ROOT, MUTATORS_REL), path.join(dir, MUTATORS_REL));
  for (const [f, body] of Object.entries(p.files)) {
    fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    fs.writeFileSync(path.join(dir, f), body);
  }
  const r = new Analyzer(dir).analyzeGroup([p.entry]);
  return {
    ok: p.want(r.sites, r),
    detail: JSON.stringify({
      sites: r.sites,
      spawns: r.spawns,
      modules: r.modules,
      errors: r.errors,
    }),
  };
}

function selftest(): number {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tree-write-sites-'));
  let ok = 0;
  let bad = 0;
  try {
    for (const p of PLANTS) {
      const r = runPlant(tmp, p);
      if (r.ok) {
        ok += 1;
        console.log(`  PASS  ${p.label}`);
      } else {
        bad += 1;
        console.error(`  FAIL  ${p.label}: ${r.detail}`);
      }
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  if (ok + bad < PLANTS.length || ok + bad < 12) {
    console.error(
      `FAIL  only ${ok + bad} control(s) ran; the file is not being executed as written`
    );
    return 1;
  }
  if (bad > 0) {
    console.error(`FAIL: ${bad} of ${ok + bad} control(s) failed`);
    return 1;
  }
  console.log(`${ok} control(s) passed`);
  return 0;
}

// --------------------------------------------------------------------------- CLI

function main(argv: string[]): number {
  if (argv[0] === '--selftest') return selftest();
  const opt = (k: string): string | null => {
    const i = argv.indexOf(k);
    return i >= 0 ? (argv[i + 1] ?? null) : null;
  };
  const root = path.resolve(opt('--root') ?? DEFAULT_ROOT);
  if (argv[0] === '--invocations') {
    const lock = opt('--lock');
    if (!lock) {
      console.error('--invocations needs --lock <path>');
      return 2;
    }
    process.stdout.write(`${JSON.stringify(invocations(lock, root, opt('--pkg')))}\n`);
    return 0;
  }
  if (argv[0] === '--batch') {
    const req = JSON.parse(fs.readFileSync(0, 'utf-8')) as {
      root?: string;
      groups: Record<string, string[]>;
    };
    const a = new Analyzer(path.resolve(req.root ?? root));
    const out: Record<string, GroupResult> = {};
    for (const [id, files] of Object.entries(req.groups)) out[id] = a.analyzeGroup(files);
    process.stdout.write(`${JSON.stringify(out)}\n`);
    return 0;
  }
  if (argv[0] === '--json') {
    const files = argv.slice(1).filter((f, i, all) => f !== '--root' && all[i - 1] !== '--root');
    const a = new Analyzer(root);
    const r = a.analyzeGroup(files.map((f) => a.rel(path.resolve(f))));
    process.stdout.write(`${JSON.stringify(r.sites)}\n`);
    return r.errors.length > 0 ? 1 : 0;
  }
  console.error(
    'usage: tree-write-sites.ts --json <file...> | --batch | --invocations --lock <lock> | --selftest'
  );
  return 2;
}

if (path.resolve(process.argv[1] ?? '') === path.resolve(fileURLToPath(import.meta.url))) {
  process.exitCode = main(process.argv.slice(2));
}
