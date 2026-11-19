/**
 * Input hashing for the incremental pre-push receipt (agent/plans/PLAN-fast-loop.md, "Hash contract").
 *
 * The contract is frozen: the Python guard (block_unverified_push.py) and the parity test implement exactly the same bytes, so a change here is a change to three files. Pure functions over a git tree object: nothing reads the worktree, which is what makes a hash a statement about the judged tree rather than about whatever is on disk.
 *
 * A gate's `inputHash` is null (the gate always runs) when it cannot be carried: it carries an `env` entry, is listed in carry-exempt.json, has a leaf closure at its cap, has a `needs` node whose hash is null, or has a glob this grammar does not define. `reason` names which. A `needs` node that is a producer (`gate: false`) contributes its `artifactHash`, which an `env` or exempt producer still has, so build:www's GITHUB_TOKEN no longer makes its 14 dependents uncarriable (PLAN-ciquick-cpu A4). The guard never recomputes `inputHash` (it recomputes `defHash` and `filesHash` and compares `inputHash` with the archived origin receipt), so the artifact edge has no Python twin to move.
 *
 * CARRY READS EVERY ARCHIVED RECEIPT (A1). `planCarry` takes the receipts under `.ci/cache/receipts/` newest first and, per gate, the newest one that judged that exact inputHash ok or fail decides: ok carries, fail re-runs. A red then a one-line fix keeps every gate the fix does not reach, from whichever receipt last judged it.
 *
 * A GATE THAT DECLARES NO `paths`, `lists` OR `names` READS THE WHOLE TREE (`paths: []` counts as none), so its input glob is `**` and its hash moves on any tracked change: it carries only across an identical tree. That is what no scoping input has always meant to `--changed` and to quick-select's rule 4 (any change may reach it). The guard needs no second rule, because it recomputes `filesHash` from the recorded `inputs` at the pushed tree, `**` included. 343 of 392 gates declare no paths, so before this a re-run at an unchanged HEAD carried 31 gates and re-ran the rest.
 *
 * `ls-tree` is read with `-z` so a path is never quoted; for every path git does not quote the bytes are the same as the plain form.
 *
 * NAME-SHAPED INPUTS (PLAN-ciquick-cpu W2.4). A gate may declare three optional fields beside `paths`, each read without file content:
 *   - `lists`: tracked directories ('' is the root). Each immediate tracked child contributes `list\t<dir>\t<child>\t<kind>`, kind being the blob mode (`100644|100755|120000`), `tree` for a subdirectory, or `commit` for a gitlink. An add, a removal, a rename or a mode flip moves the hash; an edit to a child's content does not.
 *   - `names`: globs in the `paths` grammar. Each matching tracked entry contributes `name\t<mode>\t<path>`: the set of names, not their bytes.
 *   - `refs`: ref names (`HEAD`, `origin/main`). Each contributes `ref\t<name>\t<sha>`, the commit it resolves to in the checkout; a ref that resolves to nothing makes the hash null (`ref-unresolved:<name>`), never a quiet empty line.
 * These EXTRA lines are deduplicated, sorted by their whole UTF-8 bytes, and appended to the files preimage after an `extra\n` marker (`filesHash`). A gate declaring none of the three has no extra lines, so its preimage, and every hash built on it, is byte-identical to the contract before W2.4. A gate that declares `lists` or `names` and no `paths` is NOT whole-tree: it reads those names plus the GLOBAL_INPUTS. `refs` alone does not scope a gate, because a ref is not a tree read. block_unverified_push.py (`v2_extra_lines`, `v2_files_hash`) implements the same bytes.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { isEntryPoint } from '../lib/entry-point.js';
import { policyPath } from '../lib/policy-paths.js';

export const SCHEMA = 2;
export const FORBIDDEN_GLOB_CHARS = ['?', '[', '{'] as const;
// `**/` needs a `/` before the name, so it never matches at the root: the root lockfiles are listed bare beside the nested form (the shared glob grammar pins `**/*.sh` not matching `run.sh`).
export const GLOBAL_INPUTS: readonly string[] = [
  'package-lock.json',
  '**/package-lock.json',
  'uv.lock',
  '**/uv.lock',
  '.devcontainer/toolchain.env',
  'pyproject.toml',
  'scripts/ci-runner/**',
];
/** The input of a gate that declares no `paths`: every tracked path, gitlinks included. */
export const WHOLE_TREE_GLOB = '**';

function sortKeys(x: unknown): unknown {
  if (Array.isArray(x)) return x.map(sortKeys);
  if (x !== null && typeof x === 'object') {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(x as Record<string, unknown>).sort(
      (a, b) => Number(a > b) - Number(a < b)
    )) {
      out[k] = sortKeys((x as Record<string, unknown>)[k]);
    }
    return out;
  }
  return x;
}

/** JSON with keys sorted at every depth, no whitespace, non-ASCII left as UTF-8. */
export function canon(x: unknown): string {
  return JSON.stringify(sortKeys(x));
}

/** Lowercase hex sha256 of the UTF-8 bytes. */
export function sha(s: string): string {
  return createHash('sha256').update(s, 'utf8').digest('hex');
}

export type LsEntry = { mode: string; type: string; oid: string; path: string };

function git(root: string, args: string[]): string {
  return execFileSync('git', args, {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 1 << 30,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

/** One `git ls-tree -r --full-tree <tree>`: gitlinks appear as `160000 commit <oid>`. */
export function lsTree(root: string, tree: string): LsEntry[] {
  const out = git(root, ['ls-tree', '-r', '--full-tree', '-z', tree]);
  const entries: LsEntry[] = [];
  for (const rec of out.split('\0')) {
    if (rec === '') continue;
    const tab = rec.indexOf('\t');
    const [mode, type, oid] = rec.slice(0, tab).split(' ');
    entries.push({ mode, type, oid, path: rec.slice(tab + 1) });
  }
  return entries;
}

function globRe(glob: string): RegExp {
  const body = glob.replace(/\*\*|\*|[?.+^${}()|[\]\\]/g, (t) => {
    if (t === '**') return '.*';
    if (t === '*') return '[^/]*';
    return `\\${t}`;
  });
  return new RegExp(`^${body}$`, 's');
}

/** `**` any characters including `/`, `*` any characters except `/`, everything else literal. */
export function matchGlob(glob: string, p: string): boolean {
  return globRe(glob).test(p);
}

function entryMatches(globs: RegExp[], rawGlobs: readonly string[], e: LsEntry): boolean {
  if (globs.some((re) => re.test(e.path))) return true;
  // A glob naming a gitlink directory (bare or `/**`) reaches the gitlink entry itself.
  return e.mode === '160000' && rawGlobs.some((g) => g === e.path || g === `${e.path}/**`);
}

function hasFloat(x: unknown): boolean {
  if (typeof x === 'number') return !Number.isInteger(x);
  if (Array.isArray(x)) return x.some(hasFloat);
  if (x !== null && typeof x === 'object') return Object.values(x).some(hasFloat);
  return false;
}

export function defHash(entry: unknown, scripts: Record<string, string>): string {
  return sha(`def\n${canon(entry)}\n${canon(scripts)}`);
}

/**
 * `lines` are `<mode> <oid>\t<path>`; sorted by path bytes, each terminated by `\n`. `extras` are the name-shaped lines (`list`, `name`, `ref`): deduplicated, sorted by their whole bytes, and appended after `extra\n`. With no extras the preimage is exactly the pre-W2.4 one.
 */
export function filesHash(lines: string[], extras: readonly string[] = []): string {
  const keyed = lines.map((l) => ({ l, k: Buffer.from(l.slice(l.indexOf('\t') + 1), 'utf8') }));
  keyed.sort((a, b) => Buffer.compare(a.k, b.k));
  const base = `files\n${keyed.map((x) => `${x.l}\n`).join('')}`;
  if (extras.length === 0) return sha(base);
  const sorted = [...new Set(extras)]
    .map((l) => ({ l, k: Buffer.from(l, 'utf8') }))
    .sort((a, b) => Buffer.compare(a.k, b.k));
  return sha(`${base}extra\n${sorted.map((x) => `${x.l}\n`).join('')}`);
}

/** The shape the name-shaped readers need from an entry: any lock-entry-like object. */
export type NameInputFields = {
  lists?: unknown;
  names?: unknown;
  refs?: unknown;
  [k: string]: unknown;
};

/** The three name-shaped input fields of a lock entry, each [] when absent. */
export function nameInputsOf(entry: NameInputFields | undefined): {
  lists: string[];
  names: string[];
  refs: string[];
} {
  const arr = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  return { lists: arr(entry?.lists), names: arr(entry?.names), refs: arr(entry?.refs) };
}

/** A gate reads the whole tree when it declares no `paths`, no `lists` and no `names`. `refs` does not scope it: a ref is not a tree read. */
export function isWholeTree(entry: LockEntry | undefined): boolean {
  const { lists, names } = nameInputsOf(entry);
  return (entry?.paths ?? []).length === 0 && lists.length === 0 && names.length === 0;
}

const REF_RE = /^[A-Za-z0-9_][A-Za-z0-9._/-]*$/;

/**
 * Why a lock entry's `lists`, `names` or `refs` is malformed, or null. A present field must be an array of strings. A `lists` item is '' (the root) or a relative directory: no leading or trailing `/`, no empty, `.` or `..` segment, no glob character. A `names` item is a non-empty glob with none of FORBIDDEN_GLOB_CHARS. A `refs` item is a plain ref name (`HEAD`, `origin/main`, `refs/tags/v1`), no `..`, no revision syntax. Shared by computeGateHashes (reason `bad-name-inputs`) and check-paths-origin.
 */
export function nameInputProblem(entry: NameInputFields): string | null {
  for (const field of ['lists', 'names', 'refs'] as const) {
    const v = entry[field];
    if (v === undefined) continue;
    if (!Array.isArray(v) || v.some((x) => typeof x !== 'string'))
      return `\`${field}\` must be an array of strings, got ${JSON.stringify(v)}`;
  }
  const { lists, names, refs } = nameInputsOf(entry);
  for (const d of lists) {
    if (d === '') continue;
    const segs = d.split('/');
    if (
      segs.some((s) => s === '' || s === '.' || s === '..') ||
      /[*?[{]/.test(d) ||
      d.includes('\\')
    )
      return `\`lists\` item ${JSON.stringify(d)} is not a plain relative directory ('' is the root; no leading or trailing /, no glob)`;
  }
  for (const g of names) {
    if (g === '' || FORBIDDEN_GLOB_CHARS.some((c) => g.includes(c)))
      return `\`names\` item ${JSON.stringify(g)} is empty or uses one of ${FORBIDDEN_GLOB_CHARS.join(' ')}`;
  }
  for (const r of refs) {
    if (!REF_RE.test(r) || r.includes('..') || r.endsWith('/') || r.endsWith('.lock'))
      return `\`refs\` item ${JSON.stringify(r)} is not a plain ref name (HEAD, origin/main, refs/tags/<t>)`;
  }
  return null;
}

/** The `list` lines of one tree for the listed directories: one per immediate tracked child, derived from the recursive listing (a child with a deeper path is a `tree`). */
export function listLines(entries: readonly LsEntry[], dirs: readonly string[]): string[] {
  const out: string[] = [];
  for (const dir of new Set(dirs)) {
    const prefix = dir === '' ? '' : `${dir}/`;
    const seen = new Set<string>();
    for (const e of entries) {
      if (!e.path.startsWith(prefix) || e.path.length === prefix.length) continue;
      const rest = e.path.slice(prefix.length);
      const slash = rest.indexOf('/');
      const child = slash < 0 ? rest : rest.slice(0, slash);
      if (seen.has(child)) continue;
      seen.add(child);
      const kind = slash >= 0 ? 'tree' : e.mode === '160000' ? 'commit' : e.mode;
      out.push(`list\t${dir}\t${child}\t${kind}`);
    }
  }
  return out;
}

/** The `name` lines: `name\t<mode>\t<path>` for every tracked entry a `names` glob matches. */
export function nameLines(entries: readonly LsEntry[], globs: readonly string[]): string[] {
  if (globs.length === 0) return [];
  const res = [...new Set(globs)].map(globRe);
  return entries
    .filter((e) => res.some((re) => re.test(e.path)))
    .map((e) => `name\t${e.mode}\t${e.path}`);
}

/** The commit a ref resolves to in `root`, or null. */
export function gitResolveRef(root: string, ref: string): string | null {
  try {
    const out = execFileSync('git', ['rev-parse', '--verify', '--quiet', `${ref}^{commit}`], {
      cwd: root,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    return /^[0-9a-f]{40,64}$/.test(out) ? out : null;
  } catch {
    return null;
  }
}

function cmdOut(cmd: string, args: string[]): string {
  return execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

export function saltHash(root: string, tree: string): string {
  let toolchain = '';
  try {
    toolchain = execFileSync('git', ['show', `${tree}:.devcontainer/toolchain.env`], {
      cwd: root,
      encoding: 'utf8',
      maxBuffer: 1 << 26,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    toolchain = '';
  }
  return sha(
    `salt\n${cmdOut('node', ['--version'])}\n${cmdOut('python3', ['--version'])}\n${process.platform}\n${process.arch}\n${toolchain}`
  );
}

export function inputHash(def: string, files: string, salt: string, needs: string[]): string {
  return sha(
    `input\n${def}\n${files}\n${salt}\n${[...needs].sort((a, b) => Number(a > b) - Number(a < b)).join('\n')}`
  );
}

/** `artifact\n<def>\n<files>\n<sorted producer artifact hashes>`: what a producer's output is built from. No salt: the dependent's own inputHash carries it. */
export function artifactHash(def: string, files: string, needs: string[]): string {
  return sha(
    `artifact\n${def}\n${files}\n${[...needs].sort((a, b) => Number(a > b) - Number(a < b)).join('\n')}`
  );
}

/** The kind for an exempt id, null for an exempt row naming none, undefined when the id is not exempt. */
function exemptKindOf(
  exempt: Set<string> | ReadonlyMap<string, string | null>,
  id: string
): string | null | undefined {
  if (exempt instanceof Set) return exempt.has(id) ? null : undefined;
  return exempt.has(id) ? (exempt.get(id) ?? null) : undefined;
}

export interface GateHash {
  id: string;
  inputHash: string | null;
  defHash: string;
  filesHash: string;
  /** What the hash read. `lists`, `names` and `refs` appear only when the entry declares them, so a receipt for a gate without them is unchanged. */
  inputs: {
    globs: string[];
    files: string[];
    scripts: string[];
    lists?: string[];
    names?: string[];
    refs?: string[];
  };
  reason: string | null;
  /**
   * What a DEPENDENT reads when its `needs` edge only orders an artifact (the producer is a `gate: false` build step): sha(def, files, the artifact hashes of the producer's own producers). Not nullable for `env`, `exempt` or `needs-null`: an `env` value written in the lock entry is part of `def`, so changing it moves this hash, and what the entry leaves outside the hash is a live value (a secret or token read at run time) that is not a build input; null only where the inputs themselves are unknown (no lock entry, a forbidden glob, a float, a capped leaf closure, a cycle) or a producer upstream has no artifact hash.
   */
  artifactHash: string | null;
  /** The carry-exempt.json `kind` (`clock|history|network|cache`), set only when `reason` is 'exempt' (a forbidden glob or a float is reported first and leaves it null); null when the gate is not exempt or the row names none. */
  exemptKind: string | null;
}

export type LockEntry = {
  id: string;
  paths?: string[];
  lists?: string[];
  names?: string[];
  refs?: string[];
  needs?: string[];
  env?: Record<string, unknown>;
  [k: string]: unknown;
};

export interface HashOpts {
  /** Exempt ids, or the id -> kind map `exemptRowsOf` reads (a kind of null when the row names none). */
  exempt: Set<string> | ReadonlyMap<string, string | null>;
  scriptsOf: (id: string) => Record<string, string>;
  leafFilesOf: (id: string) => { files: string[]; capped: boolean };
  /** The commit a `refs` name resolves to, null when it does not; `gitResolveRef` in `root` when absent. */
  resolveRef?: (ref: string) => string | null;
}

/** The npm scripts a gate's `run` reaches (name -> text), following `npm run <x>` references. Absent names are skipped. */
export function scriptsMapOf(
  run: string,
  scripts: Readonly<Record<string, string>>
): Record<string, string> {
  const out: Record<string, string> = {};
  const visit = (text: string): void => {
    for (const m of text.matchAll(/npm run (?:-s |--silent )?([\w:.-]+)/g)) {
      const name = m[1];
      if (name in out || scripts[name] === undefined) continue;
      out[name] = scripts[name];
      visit(scripts[name]);
    }
  };
  visit(run);
  return out;
}

export function computeGateHashes(
  root: string,
  tree: string,
  lock: Record<string, LockEntry>,
  opts: HashOpts
): Map<string, GateHash> {
  const entries = lsTree(root, tree);
  const salt = saltHash(root, tree);
  const result = new Map<string, GateHash>();
  const inProgress = new Set<string>();
  const refMemo = new Map<string, string | null>();
  const resolveRef = (r: string): string | null => {
    if (!refMemo.has(r)) refMemo.set(r, (opts.resolveRef ?? ((x) => gitResolveRef(root, x)))(r));
    return refMemo.get(r) ?? null;
  };

  const compute = (id: string): GateHash => {
    const done = result.get(id);
    if (done) return done;
    const entry = lock[id];
    const paths = entry?.paths ?? [];
    const named = nameInputsOf(entry);
    const badNames = entry ? nameInputProblem(entry) : null;
    const wholeTree = isWholeTree(entry);
    const globs = wholeTree ? [WHOLE_TREE_GLOB] : [...paths, ...GLOBAL_INPUTS];
    // THE NAME-SHAPED LINES (W2.4). Empty for a gate declaring none of lists/names/refs, which keeps its filesHash byte-identical.
    const extras: string[] = [];
    let unresolvedRef: string | null = null;
    if (badNames === null) {
      extras.push(...listLines(entries, named.lists), ...nameLines(entries, named.names));
      for (const r of named.refs) {
        const at = resolveRef(r);
        if (at === null) {
          unresolvedRef ??= r;
          continue;
        }
        extras.push(`ref\t${r}\t${at}`);
      }
    }
    const scripts = opts.scriptsOf(id);
    const leaf = opts.leafFilesOf(id);
    const rawGlobs = globs;
    const res = rawGlobs.map(globRe);
    // `**` already names every leaf, so listing them would only make each gate's hash input differ for nothing, and cost the guard one whole-tree hash per gate.
    const files = wholeTree ? [] : [...new Set(leaf.files)];
    const fileSet = new Set(files);
    const lines = entries
      .filter((e) => fileSet.has(e.path) || entryMatches(res, rawGlobs, e))
      .map((e) => `${e.mode} ${e.oid}\t${e.path}`);
    const def = defHash(entry, scripts);
    const fh = filesHash(lines, extras);
    const gh: GateHash = {
      id,
      inputHash: null,
      defHash: def,
      filesHash: fh,
      inputs: {
        globs,
        files,
        scripts: Object.keys(scripts).sort((a, b) => Number(a > b) - Number(a < b)),
        ...(named.lists.length > 0 ? { lists: named.lists } : {}),
        ...(named.names.length > 0 ? { names: named.names } : {}),
        ...(named.refs.length > 0 ? { refs: named.refs } : {}),
      },
      reason: null,
      artifactHash: null,
      exemptKind: null,
    };
    result.set(id, gh);
    if (!entry) {
      gh.reason = 'no-lock-entry';
      return gh;
    }
    const exemptKind = exemptKindOf(opts.exempt, id);
    const needs = [...(entry.needs ?? [])].sort((a, b) => Number(a > b) - Number(a < b));
    /** THE ARTIFACT EDGE (PLAN-ciquick-cpu A4). A `needs` on a producer (`gate: false`, a build step) only orders the artifact it writes, so the dependent reads the producer's artifact hash, which an `env` or carry-exempt producer still has. A `needs` on a gate keeps that gate's nullable inputHash: its verdict, not an artifact, is what the edge orders. */
    const needHash = (n: string): string | null => {
      const nh = compute(n);
      return lock[n]?.gate === false ? nh.artifactHash : nh.inputHash;
    };
    const forbidden = paths.some((p) => FORBIDDEN_GLOB_CHARS.some((c) => p.includes(c)));
    const floats = hasFloat(entry);
    const capped = !wholeTree && leaf.capped;
    // Inputs that cannot be named (a malformed lists/names/refs, a ref resolving to nothing) are unknown inputs: no artifact hash, no input hash.
    const namesUnknown = badNames !== null || unresolvedRef !== null;
    if (!forbidden && !floats && !capped && !namesUnknown) {
      // The artifact hash first: it holds for an exempt or env producer too, so it is computed whatever reason is named below.
      const artifactNeeds: string[] = [];
      for (const n of needs) {
        const ah = compute(n).artifactHash;
        if (ah === null) break;
        artifactNeeds.push(ah);
      }
      if (artifactNeeds.length === needs.length)
        gh.artifactHash = artifactHash(def, fh, artifactNeeds);
    }
    if (forbidden) {
      gh.reason = 'forbidden-glob';
    } else if (floats) {
      gh.reason = 'float-in-entry';
    } else if (badNames !== null) {
      gh.reason = 'bad-name-inputs';
    } else if (unresolvedRef !== null) {
      gh.reason = `ref-unresolved:${unresolvedRef}`;
    } else if (exemptKind !== undefined) {
      // Named in carry-exempt.json before the generic reasons: a gate that reads live state (and so declares no paths, or an env) is exempt BY NAME, and the report should say so.
      gh.reason = 'exempt';
      gh.exemptKind = exemptKind;
    } else if (entry.env !== undefined && Object.keys(entry.env).length > 0) {
      gh.reason = 'env';
    } else if (capped) {
      gh.reason = 'leaf-cap';
    } else if (inProgress.has(id)) {
      gh.reason = 'needs-cycle';
    } else {
      inProgress.add(id);
      const needHashes: string[] = [];
      for (const n of needs) {
        const nh = needHash(n);
        if (nh === null) {
          gh.reason = `needs-null:${n}`;
          break;
        }
        needHashes.push(nh);
      }
      inProgress.delete(id);
      if (gh.reason === null) gh.inputHash = inputHash(def, fh, salt, needHashes);
    }
    return gh;
  };

  for (const id of Object.keys(lock)) compute(id);
  return result;
}

export interface PriorGate {
  inputHash: string | null;
  verdict: string;
  exitCode: number | null;
  findings: string[] | null;
  judgedTree: string;
  carriedFrom: { headTree: string; head: string; finishedAt: string } | null;
}

export interface PriorReceipt {
  schema: number;
  whole: boolean;
  headTree: string;
  head: string;
  finishedAt: string;
  saltHash: string;
  gates: Record<string, PriorGate>;
}

/** A prior receipt carries only when it is schema 2, whole, names its tree, and was judged under this salt. */
function usablePrior(prior: PriorReceipt, salt: string): boolean {
  return (
    prior.schema === SCHEMA &&
    prior.whole === true &&
    prior.headTree !== '' &&
    prior.saltHash === salt
  );
}

/**
 * Which selected gates keep a prior verdict and which run.
 *
 * `priors` is every receipt the destination still holds (the latest and the archive under `.ci/cache/receipts/`), NEWEST FIRST. Per gate, the newest usable receipt holding that gate at the current inputHash with a verdict of `ok` or `fail` DECIDES: `ok` carries, `fail` re-runs and is named in `rejudged`, because an environment-caused red (a killed npm, a starved gate) must not outlive its cause, and a real red reproduces. An older green never outvotes a newer red at the same inputs. A `blocked` or `deferred` entry judged nothing, so the search goes on past it.
 *
 * A carried entry names its ORIGIN (`carriedFrom`, kept from a receipt that itself carried it). The push guard re-reads that origin from the archive and refuses unless its inputHash, verdict and findings match, so a candidate whose origin is not among `priors` (pruned, or overwritten by a later run at that tree) is passed over here rather than refused there.
 */
export function planCarry(
  priors: readonly PriorReceipt[],
  current: Map<string, GateHash>,
  selected: string[],
  salt: string
): { carry: Map<string, PriorGate>; run: string[]; rejudged: string[] } {
  const carry = new Map<string, PriorGate>();
  const run: string[] = [];
  const rejudged: string[] = [];
  const usable = priors.filter((p) => usablePrior(p, salt));
  const byTree = new Map<string, PriorReceipt>();
  for (const p of usable) if (!byTree.has(p.headTree)) byTree.set(p.headTree, p);
  /** The guard's origin check (`_carried_refusal`), run before carrying: the receipt `carriedFrom` names must be held, and agree on inputHash, verdict and findings. */
  const originHolds = (id: string, pg: PriorGate): boolean => {
    if (pg.carriedFrom === null || pg.carriedFrom === undefined) return true;
    const was = byTree.get(pg.carriedFrom.headTree)?.gates[id];
    return (
      was !== undefined &&
      was.inputHash === pg.inputHash &&
      was.verdict === pg.verdict &&
      JSON.stringify(was.findings ?? null) === JSON.stringify(pg.findings ?? null)
    );
  };
  for (const id of selected) {
    const cur = current.get(id);
    let decided: { pg: PriorGate; from: PriorReceipt } | undefined;
    if (cur !== undefined && cur.inputHash !== null) {
      for (const p of usable) {
        const pg = p.gates[id];
        if (pg === undefined || pg.inputHash !== cur.inputHash) continue;
        if (pg.verdict !== 'ok' && pg.verdict !== 'fail') continue;
        if (pg.verdict === 'ok' && !originHolds(id, pg)) continue;
        decided = { pg, from: p };
        break;
      }
    }
    if (decided?.pg.verdict === 'ok') {
      const { pg, from } = decided;
      carry.set(id, {
        ...pg,
        carriedFrom: pg.carriedFrom ?? {
          headTree: from.headTree,
          head: from.head,
          finishedAt: from.finishedAt,
        },
      });
    } else {
      run.push(id);
      if (decided?.pg.verdict === 'fail') rejudged.push(id);
    }
  }
  return { carry, run, rejudged };
}

function must(cond: boolean, message: string): void {
  if (!cond) throw new Error(`input-hash selftest: ${message}`);
}

/** Builds a scratch repo under `tmpDir` and proves the contract's behaviours. Throws on the first failed assertion. */
export function inputHashSelftest(tmpDir: string): void {
  const root = fs.mkdtempSync(path.join(tmpDir, 'input-hash-'));
  try {
    const g = (...a: string[]): string => git(root, a).trim();
    g('init', '-q');
    g('config', 'user.email', 't@example.invalid');
    g('config', 'user.name', 't');
    g('config', 'commit.gpgsign', 'false');
    fs.mkdirSync(path.join(root, 'src', 'deep'), { recursive: true });
    fs.mkdirSync(path.join(root, '.devcontainer'), { recursive: true });
    fs.writeFileSync(path.join(root, 'src', 'a.ts'), 'a1\n');
    fs.writeFileSync(path.join(root, 'src', 'deep', 'b.ts'), 'b1\n');
    fs.writeFileSync(path.join(root, 'other.txt'), 'o1\n');
    fs.writeFileSync(path.join(root, '.devcontainer', 'toolchain.env'), 'NPM_VERSION=1\n');
    g('add', '-A');
    g('commit', '-q', '-m', 'one');
    g('update-index', '--add', '--cacheinfo', `160000,${'a'.repeat(40)},private/x`);
    g('commit', '-q', '-m', 'gitlink');
    const t1 = g('rev-parse', 'HEAD^{tree}');

    // glob grammar
    must(matchGlob('src/**', 'src/deep/b.ts'), '** must cross /');
    must(matchGlob('src/*.ts', 'src/a.ts'), '* must match within a segment');
    must(!matchGlob('src/*.ts', 'src/deep/b.ts'), '* must not cross /');
    must(!matchGlob('src/*', 'src/deep/b.ts'), 'a trailing * must not cross /');
    must(matchGlob('**/package-lock.json', 'a/b/package-lock.json'), '**/ prefix matches nested');
    must(
      !matchGlob('**/package-lock.json', 'package-lock.json'),
      '**/ needs a slash, so the root lockfile is its own GLOBAL_INPUTS entry'
    );
    for (const f of ['package-lock.json', 'uv.lock', 'a/b/package-lock.json', 'a/uv.lock']) {
      must(
        GLOBAL_INPUTS.some((g) => matchGlob(g, f)),
        `GLOBAL_INPUTS must reach ${f}`
      );
    }
    must(
      !GLOBAL_INPUTS.some((g) => matchGlob(g, 'src/unrelated.ts')),
      'GLOBAL_INPUTS must not reach an unrelated file'
    );
    must(!matchGlob('src/a.ts', 'src/aXts'), '. must be literal');
    must(matchGlob('a(b).ts', 'a(b).ts'), 'regex metacharacters are literal');

    const lock: Record<string, LockEntry> = {
      'g:src': { id: 'g:src', run: 'npm run g:src', paths: ['src/**'] },
      'g:nopaths': { id: 'g:nopaths', run: 'npm run g:nopaths' },
      'g:env': { id: 'g:env', run: 'x', paths: ['src/**'], env: { K: 'v' } },
      'g:exempt': { id: 'g:exempt', run: 'x', paths: ['src/**'] },
      'g:forbid': { id: 'g:forbid', run: 'x', paths: ['src/{a,b}.ts'] },
      'g:float': { id: 'g:float', run: 'x', paths: ['src/**'], n: 1.5 },
      'g:needsnull': { id: 'g:needsnull', run: 'x', paths: ['src/**'], needs: ['g:env'] },
      'g:nopathsenv': { id: 'g:nopathsenv', run: 'x', env: { K: 'v' } },
      'g:needsok': { id: 'g:needsok', run: 'x', paths: ['src/**'], needs: ['g:src'] },
      'g:gitlink': { id: 'g:gitlink', run: 'x', paths: ['private/x'] },
      'g:gitlink2': { id: 'g:gitlink2', run: 'x', paths: ['private/x/**'] },
      // THE ARTIFACT EDGE: a producer (gate: false) with an env, and a dependent of it; a gate with an env stays a verdict edge.
      'p:build': { id: 'p:build', run: 'x', gate: false, paths: ['src/**'], env: { T: 'v' } },
      'g:onbuild': { id: 'g:onbuild', run: 'x', paths: ['other.txt'], needs: ['p:build'] },
      'p:exbuild': { id: 'p:exbuild', run: 'x', gate: false, paths: ['src/**'] },
      'g:onexbuild': { id: 'g:onexbuild', run: 'x', paths: ['other.txt'], needs: ['p:exbuild'] },
      'p:forbid': { id: 'p:forbid', run: 'x', gate: false, paths: ['src/{a}.ts'] },
      'g:onforbid': { id: 'g:onforbid', run: 'x', paths: ['other.txt'], needs: ['p:forbid'] },
    };
    const mk = (r: string, scripts: Record<string, string> = {}) => ({
      exempt: new Map<string, string | null>([
        ['g:exempt', 'clock'],
        ['p:exbuild', 'network'],
      ]),
      scriptsOf: () => scripts,
      leafFilesOf: () => ({ files: [] as string[], capped: false }),
      root: r,
    });
    const h1 = computeGateHashes(root, t1, lock, mk(root));
    const get = (m: Map<string, GateHash>, id: string): GateHash => {
      const v = m.get(id);
      must(v !== undefined, `no hash for ${id}`);
      return v as GateHash;
    };
    must(get(h1, 'g:src').inputHash !== null, 'a gate with paths is carriable');
    must(
      get(h1, 'g:nopaths').inputHash !== null &&
        get(h1, 'g:nopaths').inputs.globs.join() === WHOLE_TREE_GLOB &&
        get(h1, 'g:nopaths').inputs.files.length === 0,
      'a gate declaring no paths reads the whole tree, so that is its input'
    );
    must(get(h1, 'g:env').reason === 'env' && get(h1, 'g:env').inputHash === null, 'env is null');
    must(
      get(h1, 'g:nopathsenv').reason === 'env' && get(h1, 'g:nopathsenv').inputHash === null,
      'an env entry stays uncarriable with no paths too: it names outside state the tree does not hold'
    );
    must(
      get(h1, 'g:exempt').reason === 'exempt' && get(h1, 'g:exempt').inputHash === null,
      'exempt is null'
    );
    must(get(h1, 'g:forbid').reason === 'forbidden-glob', 'a { glob is forbidden');
    must(get(h1, 'g:float').reason === 'float-in-entry', 'a float entry is null');
    must(get(h1, 'g:needsnull').reason === 'needs-null:g:env', 'a null needs hash propagates');
    must(get(h1, 'g:needsok').inputHash !== null, 'a needs on a carriable gate stays carriable');
    must(
      get(h1, 'g:gitlink').filesHash === get(h1, 'g:gitlink2').filesHash &&
        get(h1, 'g:gitlink').filesHash !== get(h1, 'g:nopaths').filesHash,
      'a glob naming a gitlink, bare or /**, reaches the gitlink entry'
    );
    must(
      get(h1, 'p:build').reason === 'env' &&
        get(h1, 'p:build').artifactHash !== null &&
        get(h1, 'g:onbuild').inputHash !== null,
      `a needs on an env PRODUCER hashes through its artifact and stays carriable, got ${get(h1, 'g:onbuild').reason}`
    );
    must(
      get(h1, 'g:onexbuild').inputHash !== null && get(h1, 'p:exbuild').exemptKind === 'network',
      'a needs on a carry-exempt producer stays carriable, and the exempt kind is recorded'
    );
    must(
      get(h1, 'g:exempt').exemptKind === 'clock' && get(h1, 'g:src').exemptKind === null,
      'exemptKind names the row kind for an exempt gate and is null otherwise'
    );
    must(
      get(h1, 'p:forbid').artifactHash === null &&
        get(h1, 'g:onforbid').reason === 'needs-null:p:forbid',
      'CONTROL: a producer whose inputs are unknown (a forbidden glob) has no artifact hash, so its dependent stays null'
    );
    must(
      get(h1, 'g:needsnull').reason === 'needs-null:g:env',
      'CONTROL: a needs on an env GATE (not a producer) still propagates null: that edge orders a verdict'
    );
    must(
      exemptRowsOf(
        '{"schema":1,"exempt":[{"id":"a","reason":"r","kind":"cache"},{"id":"b","reason":"r"}]}'
      ).get('a') === 'cache' &&
        exemptRowsOf('{"schema":1,"exempt":[{"id":"b","reason":"r"}]}').get('b') === null,
      'exemptRowsOf reads a kind, and null for a row naming none'
    );
    let badKind = '';
    try {
      exemptRowsOf('{"schema":1,"exempt":[{"id":"a","reason":"r","kind":"weather"}]}');
    } catch (err) {
      badKind = (err as Error).message;
    }
    must(
      badKind.includes('weather'),
      'a kind outside EXEMPT_KINDS is refused, never read as no kind'
    );

    // filesHash reacts to an input file and not to a non-input file
    fs.writeFileSync(path.join(root, 'other.txt'), 'o2\n');
    g('commit', '-q', '-am', 'non-input');
    const t2 = g('rev-parse', 'HEAD^{tree}');
    const h2 = computeGateHashes(root, t2, lock, mk(root));
    must(
      get(h2, 'g:src').filesHash === get(h1, 'g:src').filesHash,
      'a non-input change must not move filesHash'
    );
    must(
      get(h2, 'g:src').inputHash === get(h1, 'g:src').inputHash,
      'a non-input change must not move inputHash'
    );
    must(
      get(h2, 'g:nopaths').inputHash !== get(h1, 'g:nopaths').inputHash,
      'any tracked change must move a whole-tree gate: it carries across an identical tree only'
    );
    must(
      computeGateHashes(root, t1, lock, mk(root)).get('g:nopaths')?.inputHash ===
        get(h1, 'g:nopaths').inputHash,
      'CONTROL: the same tree must give a whole-tree gate the same hash, or nothing ever carries'
    );
    fs.writeFileSync(path.join(root, 'src', 'a.ts'), 'a2\n');
    g('commit', '-q', '-am', 'input');
    const t3 = g('rev-parse', 'HEAD^{tree}');
    const h3 = computeGateHashes(root, t3, lock, mk(root));
    must(
      get(h3, 'g:src').filesHash !== get(h2, 'g:src').filesHash,
      'an input change must move filesHash'
    );
    must(
      get(h3, 'g:src').inputHash !== get(h2, 'g:src').inputHash,
      'an input change must move inputHash'
    );
    must(
      get(h3, 'g:needsok').inputHash !== get(h2, 'g:needsok').inputHash,
      'a needs input change must move the dependent'
    );
    must(
      get(h3, 'g:onbuild').inputHash !== get(h2, 'g:onbuild').inputHash &&
        get(h2, 'p:build').artifactHash === get(h1, 'p:build').artifactHash,
      'a change to the PRODUCER inputs (src/, not a path of the dependent) must move the dependent through the artifact hash; CONTROL: a non-input change leaves the artifact hash alone'
    );
    // A changed env VALUE in the producer's lock entry, tree unchanged: def moves, so the artifact hash and the dependent move (the artifact edge never carries `ok` across it).
    const envLock = { ...lock, 'p:build': { ...lock['p:build'], env: { T: 'changed' } } };
    const hEnv = computeGateHashes(root, t1, envLock, mk(root));
    must(
      get(hEnv, 'p:build').artifactHash !== get(h1, 'p:build').artifactHash &&
        get(hEnv, 'g:onbuild').inputHash !== get(h1, 'g:onbuild').inputHash,
      'a changed producer env value must move the artifact hash and its dependent'
    );
    must(
      get(computeGateHashes(root, t1, lock, mk(root)), 'g:onbuild').inputHash ===
        get(h1, 'g:onbuild').inputHash,
      'CONTROL: the same env leaves the dependent hash alone'
    );

    // a root lockfile is a global input: `**/package-lock.json` alone never matched it
    const hashAt = (): GateHash => {
      const t = g('rev-parse', 'HEAD^{tree}');
      return get(computeGateHashes(root, t, lock, mk(root)), 'g:src');
    };
    const before = hashAt();
    fs.writeFileSync(path.join(root, 'package-lock.json'), 'L1\n');
    g('add', '-A');
    g('commit', '-q', '-m', 'root lock');
    const rootLock1 = hashAt();
    must(
      rootLock1.inputHash !== before.inputHash,
      'a new root package-lock.json must move a gate hash'
    );
    fs.writeFileSync(path.join(root, 'package-lock.json'), 'L2\n');
    g('commit', '-q', '-am', 'root lock edit');
    const rootLock2 = hashAt();
    must(
      rootLock2.inputHash !== rootLock1.inputHash,
      'a root package-lock.json change must move a gate hash'
    );
    fs.mkdirSync(path.join(root, 'pkg'), { recursive: true });
    fs.writeFileSync(path.join(root, 'pkg', 'package-lock.json'), 'N1\n');
    g('add', '-A');
    g('commit', '-q', '-m', 'nested lock');
    const nested1 = hashAt();
    must(
      nested1.inputHash !== rootLock2.inputHash,
      'a nested package-lock.json must still move a gate hash'
    );
    fs.writeFileSync(path.join(root, 'other.txt'), 'o3\n');
    g('commit', '-q', '-am', 'unrelated');
    must(
      hashAt().inputHash === nested1.inputHash,
      'CONTROL: an unrelated file must not move the hash'
    );

    // defHash reacts to the entry's run
    const d1 = defHash(lock['g:src'], {});
    const d2 = defHash({ ...lock['g:src'], run: 'changed' }, {});
    must(d1 !== d2, 'a changed run must move defHash');
    must(defHash(lock['g:src'], { a: '1' }) !== d1, 'a changed script closure must move defHash');
    must(
      canon({ b: 1, a: { d: 1, c: 2 } }) === '{"a":{"c":2,"d":1},"b":1}',
      'canon sorts keys at every depth'
    );

    // planCarry
    const salt = saltHash(root, t3);
    const mkPrior = (verdict: string, over: Partial<PriorReceipt> = {}): PriorReceipt => ({
      schema: 2,
      whole: true,
      headTree: t2,
      head: 'h2',
      finishedAt: '2026-10-06T00:00:00Z',
      saltHash: salt,
      gates: {
        'g:src': {
          inputHash: get(h3, 'g:src').inputHash,
          verdict,
          exitCode: verdict === 'ok' ? 0 : 1,
          findings: null,
          judgedTree: t2,
          carriedFrom: null,
        },
        'g:needsok': {
          inputHash: get(h2, 'g:needsok').inputHash,
          verdict: 'ok',
          exitCode: 0,
          findings: null,
          judgedTree: t2,
          carriedFrom: null,
        },
      },
      ...over,
    });
    const sel = ['g:src', 'g:needsok', 'g:nopaths'];
    const okPlan = planCarry([mkPrior('ok')], h3, sel, salt);
    must(
      okPlan.carry.has('g:src') && okPlan.carry.get('g:src')?.verdict === 'ok',
      'an equal-hash ok carries'
    );
    must(
      okPlan.carry.get('g:src')?.carriedFrom?.headTree === t2,
      'carriedFrom names the prior receipt'
    );
    must(
      okPlan.run.includes('g:needsok') && okPlan.run.includes('g:nopaths'),
      'a changed hash and a null hash re-run'
    );
    const failPlan = planCarry([mkPrior('fail')], h3, sel, salt);
    must(
      !failPlan.carry.has('g:src') && failPlan.run.includes('g:src'),
      'an equal-hash fail re-runs, never carries'
    );
    must(
      failPlan.rejudged.join() === 'g:src' && okPlan.rejudged.length === 0,
      `rejudged names the equal-hash fail and nothing for an ok prior, got ${failPlan.rejudged.join()} / ${okPlan.rejudged.join()}`
    );
    const blocked = planCarry([mkPrior('blocked')], h3, sel, salt);
    must(!blocked.carry.has('g:src'), 'a blocked verdict never carries');
    const saltPlan = planCarry([mkPrior('ok', { saltHash: 'different' })], h3, sel, salt);
    must(
      saltPlan.carry.size === 0 && saltPlan.run.length === sel.length,
      'a salt mismatch re-runs everything'
    );
    must(
      planCarry([mkPrior('ok', { whole: false })], h3, sel, salt).carry.size === 0,
      'a partial prior never carries'
    );
    must(
      planCarry([mkPrior('ok', { schema: 1 })], h3, sel, salt).carry.size === 0,
      'a v1 prior never carries'
    );
    must(planCarry([], h3, sel, salt).run.length === sel.length, 'no prior runs everything');
    const origin = mkPrior('ok', { headTree: 'orig', head: 'o', finishedAt: 'f' });
    const prior2 = mkPrior('ok');
    prior2.gates['g:src'].carriedFrom = { headTree: 'orig', head: 'o', finishedAt: 'f' };
    must(
      planCarry([prior2, origin], h3, sel, salt).carry.get('g:src')?.carriedFrom?.headTree ===
        'orig',
      'an existing carriedFrom is kept'
    );
    must(
      !planCarry([prior2], h3, sel, salt).carry.has('g:src'),
      'a carry whose origin receipt is not held is passed over: the push guard would refuse it'
    );

    // A1: CARRY ACROSS RECEIPTS. A gate judged ok two runs back carries through a newer receipt that never judged it at this hash.
    const twoBack = mkPrior('ok', {
      headTree: 'tOld',
      head: 'hOld',
      finishedAt: '2026-10-05T00:00:00Z',
    });
    const redSince = mkPrior('fail', { headTree: 'tMid', head: 'hMid' });
    redSince.gates['g:src'] = { ...redSince.gates['g:src'], inputHash: 'other-hash' };
    const across = planCarry([redSince, twoBack], h3, sel, salt);
    must(
      across.carry.get('g:src')?.carriedFrom?.headTree === 'tOld' && across.rejudged.length === 0,
      `a gate judged ok at this inputHash two receipts back carries from that receipt, got ${JSON.stringify(across.carry.get('g:src')?.carriedFrom)}`
    );
    const movedHash = new Map(h3);
    movedHash.set('g:src', { ...get(h3, 'g:src'), inputHash: 'changed' });
    must(
      planCarry([redSince, twoBack], movedHash, sel, salt).run.includes('g:src'),
      'CONTROL: a changed inputHash carries from no receipt, however many are held'
    );
    const newerRed = mkPrior('fail', { headTree: 'tNew', head: 'hNew' });
    const outvoted = planCarry([newerRed, twoBack], h3, sel, salt);
    must(
      !outvoted.carry.has('g:src') && outvoted.rejudged.join() === 'g:src',
      'a NEWER red at the same inputHash outvotes an older green: it re-runs and is rejudged'
    );
    const newerBlocked = mkPrior('blocked', { headTree: 'tNew', head: 'hNew' });
    must(
      planCarry([newerBlocked, twoBack], h3, sel, salt).carry.get('g:src')?.carriedFrom
        ?.headTree === 'tOld',
      'a newer blocked entry judged nothing, so the older green at that hash still carries'
    );
    must(
      planCarry([mkPrior('ok', { saltHash: 'x' }), twoBack], h3, sel, salt).carry.has('g:src'),
      'a receipt under another salt is skipped, not fatal to the rest'
    );

    // W2.4: NAME-SHAPED INPUTS. lists (children, no content), names (paths, no content), refs (the sha).
    const nlock: Record<string, LockEntry> = {
      'g:plain': { id: 'g:plain', run: 'x', paths: ['src/**'] },
      'g:plainwhole': { id: 'g:plainwhole', run: 'x' },
      'g:lists': { id: 'g:lists', run: 'x', paths: ['other.txt'], lists: ['src'] },
      'g:root': { id: 'g:root', run: 'x', lists: [''] },
      'g:names': { id: 'g:names', run: 'x', names: ['src/**'] },
      'g:refs': { id: 'g:refs', run: 'x', paths: ['other.txt'], refs: ['HEAD'] },
      'g:wholerefs': { id: 'g:wholerefs', run: 'x', refs: ['HEAD'] },
      'g:noref': { id: 'g:noref', run: 'x', paths: ['other.txt'], refs: ['refs/heads/nope'] },
      'g:badlist': { id: 'g:badlist', run: 'x', lists: ['src/'] },
      'g:badname': { id: 'g:badname', run: 'x', names: ['src/{a}.ts'] },
      'g:onref': { id: 'g:onref', run: 'x', paths: ['other.txt'], needs: ['g:noref'] },
    };
    const at = (): Map<string, GateHash> =>
      computeGateHashes(root, g('rev-parse', 'HEAD^{tree}'), nlock, mk(root));
    const n0 = at();
    // An entry declaring none of the three hashes exactly as the pre-W2.4 contract did: rebuild that preimage by hand.
    const plainLines = lsTree(root, g('rev-parse', 'HEAD^{tree}'))
      .filter((e) => [...['src/**'], ...GLOBAL_INPUTS].some((gl) => matchGlob(gl, e.path)))
      .map((e) => ({ l: `${e.mode} ${e.oid}\t${e.path}`, k: Buffer.from(e.path, 'utf8') }))
      .sort((a, b) => Buffer.compare(a.k, b.k));
    must(
      get(n0, 'g:plain').filesHash ===
        sha(`files\n${plainLines.map((x) => `${x.l}\n`).join('')}`) &&
        get(n0, 'g:plain').inputs.lists === undefined &&
        get(n0, 'g:plain').inputs.refs === undefined,
      'CONTROL: a gate with no lists/names/refs keeps the pre-W2.4 files preimage byte for byte, and its recorded inputs gain no key'
    );
    must(
      get(n0, 'g:plain').inputHash ===
        get(
          computeGateHashes(
            root,
            g('rev-parse', 'HEAD^{tree}'),
            { 'g:plain': nlock['g:plain'] },
            mk(root)
          ),
          'g:plain'
        ).inputHash,
      'a gate hash does not depend on which other entries carry the new fields'
    );
    must(
      get(n0, 'g:root').inputs.globs.join() === GLOBAL_INPUTS.join() &&
        get(n0, 'g:names').inputs.globs.join() === GLOBAL_INPUTS.join() &&
        get(n0, 'g:wholerefs').inputs.globs.join() === WHOLE_TREE_GLOB,
      'lists or names without paths is not whole-tree (it reads the names plus GLOBAL_INPUTS); refs alone stays whole-tree'
    );
    must(
      get(n0, 'g:noref').reason === 'ref-unresolved:refs/heads/nope' &&
        get(n0, 'g:noref').inputHash === null &&
        get(n0, 'g:noref').artifactHash === null &&
        get(n0, 'g:onref').reason === 'needs-null:g:noref',
      `a ref that resolves to nothing is an unknown input, never an empty line, got ${get(n0, 'g:noref').reason}`
    );
    must(
      get(n0, 'g:badlist').reason === 'bad-name-inputs' &&
        get(n0, 'g:badname').reason === 'bad-name-inputs' &&
        get(n0, 'g:badlist').inputHash === null,
      'a malformed lists or names item makes the gate uncarriable by name'
    );
    must(
      nameInputProblem({
        id: 'x',
        lists: ['', 'a/b'],
        names: ['**/*.ts'],
        refs: ['HEAD', 'origin/main'],
      }) === null &&
        nameInputProblem({ id: 'x', lists: ['/a'] }) !== null &&
        nameInputProblem({ id: 'x', lists: ['a/../b'] }) !== null &&
        nameInputProblem({ id: 'x', lists: 'a' as unknown as string[] }) !== null &&
        nameInputProblem({ id: 'x', refs: ['HEAD~1'] }) !== null &&
        nameInputProblem({ id: 'x', refs: ['a..b'] }) !== null,
      'nameInputProblem accepts the plain shapes and refuses a rooted, dotted or non-array list, and revision syntax in a ref'
    );
    must(
      listLines(
        [
          { mode: '100644', type: 'blob', oid: 'o', path: 'd/f' },
          { mode: '100755', type: 'blob', oid: 'o', path: 'd/x' },
          { mode: '100644', type: 'blob', oid: 'o', path: 'd/s/deep' },
          { mode: '100644', type: 'blob', oid: 'o', path: 'd/s/deeper' },
          { mode: '160000', type: 'commit', oid: 'o', path: 'd/sub' },
          { mode: '100644', type: 'blob', oid: 'o', path: 'dd/f' },
        ],
        ['d']
      ).join('|') === 'list\td\tf\t100644|list\td\tx\t100755|list\td\ts\ttree|list\td\tsub\tcommit',
      'listLines gives one line per immediate child with its kind, and dd/ is not a child of d'
    );

    // CONTROL 1: a NEW file in a listed directory moves the hash.
    fs.writeFileSync(path.join(root, 'src', 'new.ts'), 'n1\n');
    g('add', '-A');
    g('commit', '-q', '-m', 'new child');
    const n1 = at();
    must(
      get(n1, 'g:lists').inputHash !== get(n0, 'g:lists').inputHash,
      'a new file in a listed directory must move the hash'
    );
    must(
      get(n1, 'g:names').inputHash !== get(n0, 'g:names').inputHash,
      'a new path matching a names glob must move the hash'
    );
    must(
      get(n1, 'g:root').inputHash === get(n0, 'g:root').inputHash,
      'CONTROL: a file added under an existing top-level directory does not change the root listing'
    );
    // CONTROL 2: an edit to an UNREAD file in a listed directory does not move it.
    fs.writeFileSync(path.join(root, 'src', 'new.ts'), 'n2\n');
    g('commit', '-q', '-am', 'edit child');
    const n2 = at();
    must(
      get(n2, 'g:lists').inputHash === get(n1, 'g:lists').inputHash &&
        get(n2, 'g:names').inputHash === get(n1, 'g:names').inputHash,
      'an edit to the content of a listed child, or of a names match, must not move the hash'
    );
    must(
      get(n2, 'g:plain').inputHash !== get(n1, 'g:plain').inputHash,
      'CONTROL: the same edit does move a gate that reads src/** content'
    );
    // A mode flip is a listing change.
    fs.chmodSync(path.join(root, 'src', 'new.ts'), 0o755);
    g('config', 'core.fileMode', 'true');
    g('commit', '-q', '-am', 'mode');
    must(
      at().get('g:lists')?.inputHash !== get(n2, 'g:lists').inputHash,
      'a mode change of a listed child moves the hash'
    );
    // A new top-level directory changes the root listing.
    fs.mkdirSync(path.join(root, 'top'), { recursive: true });
    fs.writeFileSync(path.join(root, 'top', 'f'), 't\n');
    g('add', '-A');
    g('commit', '-q', '-m', 'new top dir');
    const n3 = at();
    must(
      get(n3, 'g:root').inputHash !== get(n2, 'g:root').inputHash,
      'a new top-level directory must move a lists: [""] gate'
    );
    // CONTROL 3: a new HEAD sha with an identical tree moves a refs gate and nothing else.
    g('commit', '-q', '--allow-empty', '-m', 'same tree, new head');
    const n4 = at();
    must(
      get(n4, 'g:refs').inputHash !== get(n3, 'g:refs').inputHash &&
        get(n4, 'g:wholerefs').inputHash !== get(n3, 'g:wholerefs').inputHash,
      'a new HEAD sha must move a refs: [HEAD] gate'
    );
    must(
      get(n4, 'g:plain').inputHash === get(n3, 'g:plain').inputHash &&
        get(n4, 'g:plainwhole').inputHash === get(n3, 'g:plainwhole').inputHash &&
        get(n4, 'g:lists').inputHash === get(n3, 'g:lists').inputHash,
      'CONTROL: a new HEAD over the same tree moves no gate that declares no refs'
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function showAt(tree: string, file: string): string | null {
  try {
    return git(process.cwd(), ['show', `${tree}:${file}`]);
  } catch {
    return null;
  }
}

/** The policy listing gates whose verdict moves without a tracked input moving (network, clock, history, cache). */
export const CARRY_EXEMPT_REL = path.relative('.', policyPath('carry-exempt.json', '.'));

/** Why a carry-exempt gate's verdict moves with no tracked input moving (PLAN-ciquick-cpu A4): the wall clock, git history, the network, or an untracked cache. */
export const EXEMPT_KINDS = ['clock', 'history', 'network', 'cache'] as const;

/**
 * The exempt rows of carry-exempt.json's text, `{"schema": 1, "exempt": [{"id", "reason", "kind"?}]}`, as id -> kind (null where the row names none); an absent file is the empty map.
 * One shape, read one way by the corpus printer and the runner, so the two can never disagree about what is exempt. Any other shape throws, and so does a `kind` outside EXEMPT_KINDS; the guard's `_exempt_ids` (block_unverified_push.py) refuses the same rows.
 */
export function exemptRowsOf(text: string | null): Map<string, string | null> {
  const rows = new Map<string, string | null>();
  if (text === null) return rows;
  const doc = JSON.parse(text) as { schema?: unknown; exempt?: unknown };
  if (doc.schema !== 1 || !Array.isArray(doc.exempt))
    throw new Error(`${CARRY_EXEMPT_REL}: expected {"schema": 1, "exempt": [...]}`);
  for (const row of doc.exempt as Array<{ id?: unknown; kind?: unknown } | null>) {
    if (typeof row?.id !== 'string' || row.id === '')
      throw new Error(`${CARRY_EXEMPT_REL}: every exempt row needs a string "id"`);
    const kind = row.kind;
    if (kind !== undefined && !(EXEMPT_KINDS as readonly unknown[]).includes(kind))
      throw new Error(
        `${CARRY_EXEMPT_REL}: ${row.id} has kind ${JSON.stringify(kind)}; a kind is one of ${EXEMPT_KINDS.join('|')}`
      );
    rows.set(row.id, typeof kind === 'string' ? kind : null);
  }
  return rows;
}

/** The exempt gate ids alone: `exemptRowsOf`'s keys. */
export function exemptIdsOf(text: string | null): Set<string> {
  return new Set(exemptRowsOf(text).keys());
}

function printCorpus(tree: string): void {
  const root = process.cwd();
  const lockText = showAt(tree, 'scripts/ci-runner/gates.lock.json');
  const pkgText = showAt(tree, 'package.json');
  if (lockText === null || pkgText === null)
    throw new Error(`no gates.lock.json or package.json at ${tree}`);
  const lockList = JSON.parse(lockText) as LockEntry[];
  const pkgScripts = (JSON.parse(pkgText) as { scripts?: Record<string, string> }).scripts ?? {};
  const lock: Record<string, LockEntry> = {};
  for (const e of lockList) lock[e.id] = e;
  const hashes = computeGateHashes(root, tree, lock, {
    exempt: exemptRowsOf(showAt(tree, CARRY_EXEMPT_REL)),
    scriptsOf: (id) => scriptsMapOf(String(lock[id]?.run ?? ''), pkgScripts),
    leafFilesOf: () => ({ files: [], capped: false }),
  });
  const out: Record<string, unknown> = {};
  for (const [id, h] of hashes) {
    out[id] = {
      defHash: h.defHash,
      filesHash: h.filesHash,
      inputHash: h.inputHash,
      inputs: h.inputs,
      reason: h.reason,
      artifactHash: h.artifactHash,
      exemptKind: h.exemptKind,
    };
  }
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

if (isEntryPoint(import.meta.filename)) {
  const args = process.argv.slice(2);
  if (args[0] === '--selftest') {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'input-hash-st-'));
    try {
      inputHashSelftest(tmp);
      process.stdout.write('input-hash selftest: ok\n');
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  } else if (args[0] === '--print-corpus' && args[1]) {
    printCorpus(args[1]);
  } else if (args[0] === '--exempt-rows') {
    // The parity test's door to exemptRowsOf: carry-exempt.json text on stdin, `{id: kind|null}` on stdout, or exit 1 with the refusal.
    try {
      const rows = exemptRowsOf(fs.readFileSync(0, 'utf8'));
      process.stdout.write(`${JSON.stringify(Object.fromEntries(rows))}\n`);
    } catch (err) {
      process.stderr.write(`${(err as Error).message}\n`);
      process.exit(1);
    }
  } else {
    process.stderr.write(
      'usage: input-hash.ts --selftest | --print-corpus <tree> | --exempt-rows\n'
    );
    process.exit(2);
  }
}
