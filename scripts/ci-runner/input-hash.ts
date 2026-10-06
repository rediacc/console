/**
 * Input hashing for the incremental pre-push receipt (agent/plans/PLAN-fast-loop.md, "Hash contract").
 *
 * The contract is frozen: the Python guard (block_unverified_push.py) and the parity test implement exactly the same bytes, so a change here is a change to three files. Pure functions over a git tree object: nothing reads the worktree, which is what makes a hash a statement about the judged tree rather than about whatever is on disk.
 *
 * A gate's `inputHash` is null (the gate always runs) when it cannot be carried: it declares no `paths`, carries an `env` entry, is listed in carry-exempt.json, has a leaf closure at its cap, has a `needs` node that is itself null, or has a glob this grammar does not define. `reason` names which.
 *
 * `ls-tree` is read with `-z` so a path is never quoted; for every path git does not quote the bytes are the same as the plain form.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { policyPath } from '../lib/policy-paths.js';

export const SCHEMA = 2;
export const FORBIDDEN_GLOB_CHARS = ['?', '[', '{'] as const;
export const GLOBAL_INPUTS: readonly string[] = [
  '**/package-lock.json',
  '**/uv.lock',
  '.devcontainer/toolchain.env',
  'pyproject.toml',
  'scripts/ci-runner/**',
];

function sortKeys(x: unknown): unknown {
  if (Array.isArray(x)) return x.map(sortKeys);
  if (x !== null && typeof x === 'object') {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(x as Record<string, unknown>).sort()) {
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

/** `lines` are `<mode> <oid>\t<path>`; sorted by path bytes, each terminated by `\n`. */
export function filesHash(lines: string[]): string {
  const keyed = lines.map((l) => ({ l, k: Buffer.from(l.slice(l.indexOf('\t') + 1), 'utf8') }));
  keyed.sort((a, b) => Buffer.compare(a.k, b.k));
  return sha(`files\n${keyed.map((x) => `${x.l}\n`).join('')}`);
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
  return sha(`input\n${def}\n${files}\n${salt}\n${[...needs].sort().join('\n')}`);
}

export interface GateHash {
  id: string;
  inputHash: string | null;
  defHash: string;
  filesHash: string;
  inputs: { globs: string[]; files: string[]; scripts: string[] };
  reason: string | null;
}

export type LockEntry = {
  id: string;
  paths?: string[];
  needs?: string[];
  env?: Record<string, unknown>;
  [k: string]: unknown;
};

export interface HashOpts {
  exempt: Set<string>;
  scriptsOf: (id: string) => Record<string, string>;
  leafFilesOf: (id: string) => { files: string[]; capped: boolean };
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

  const compute = (id: string): GateHash => {
    const done = result.get(id);
    if (done) return done;
    const entry = lock[id];
    const paths = entry?.paths ?? [];
    const globs = [...paths, ...GLOBAL_INPUTS];
    const scripts = opts.scriptsOf(id);
    const leaf = opts.leafFilesOf(id);
    const rawGlobs = globs;
    const res = rawGlobs.map(globRe);
    const files = [...new Set(leaf.files)];
    const fileSet = new Set(files);
    const lines = entries
      .filter((e) => fileSet.has(e.path) || entryMatches(res, rawGlobs, e))
      .map((e) => `${e.mode} ${e.oid}\t${e.path}`);
    const def = defHash(entry, scripts);
    const fh = filesHash(lines);
    const gh: GateHash = {
      id,
      inputHash: null,
      defHash: def,
      filesHash: fh,
      inputs: { globs, files, scripts: Object.keys(scripts).sort() },
      reason: null,
    };
    result.set(id, gh);
    if (!entry) {
      gh.reason = 'no-lock-entry';
      return gh;
    }
    if (paths.some((p) => FORBIDDEN_GLOB_CHARS.some((c) => p.includes(c)))) {
      gh.reason = 'forbidden-glob';
    } else if (hasFloat(entry)) {
      gh.reason = 'float-in-entry';
    } else if (paths.length === 0) {
      gh.reason = 'no-paths';
    } else if (entry.env !== undefined && Object.keys(entry.env).length > 0) {
      gh.reason = 'env';
    } else if (opts.exempt.has(id)) {
      gh.reason = 'exempt';
    } else if (leaf.capped) {
      gh.reason = 'leaf-cap';
    } else if (inProgress.has(id)) {
      gh.reason = 'needs-cycle';
    } else {
      inProgress.add(id);
      const needHashes: string[] = [];
      for (const n of [...(entry.needs ?? [])].sort()) {
        const nh = compute(n);
        if (nh.inputHash === null) {
          gh.reason = `needs-null:${n}`;
          break;
        }
        needHashes.push(nh.inputHash);
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

/** Which selected gates keep the prior verdict and which run. A carried `fail` stays `fail`. */
export function planCarry(
  prior: PriorReceipt | null,
  current: Map<string, GateHash>,
  selected: string[],
  salt: string
): { carry: Map<string, PriorGate>; run: string[] } {
  const carry = new Map<string, PriorGate>();
  const run: string[] = [];
  const usable =
    prior !== null &&
    prior.schema === SCHEMA &&
    prior.whole === true &&
    prior.headTree !== '' &&
    prior.saltHash === salt;
  for (const id of selected) {
    const pg = usable ? prior.gates[id] : undefined;
    const cur = current.get(id);
    if (
      usable &&
      pg !== undefined &&
      cur !== undefined &&
      cur.inputHash !== null &&
      pg.inputHash === cur.inputHash &&
      (pg.verdict === 'ok' || pg.verdict === 'fail')
    ) {
      carry.set(id, {
        ...pg,
        carriedFrom: pg.carriedFrom ?? {
          headTree: prior.headTree,
          head: prior.head,
          finishedAt: prior.finishedAt,
        },
      });
    } else {
      run.push(id);
    }
  }
  return { carry, run };
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
    must(!matchGlob('src/a.ts', 'src/aXts'), '. must be literal');
    must(matchGlob('a(b).ts', 'a(b).ts'), 'regex metacharacters are literal');

    const lock: Record<string, LockEntry> = {
      'g:src': { id: 'g:src', run: 'npm run g:src', paths: ['src/**'] },
      'g:nopaths': { id: 'g:nopaths', run: 'npm run g:nopaths' },
      'g:env': { id: 'g:env', run: 'x', paths: ['src/**'], env: { K: 'v' } },
      'g:exempt': { id: 'g:exempt', run: 'x', paths: ['src/**'] },
      'g:forbid': { id: 'g:forbid', run: 'x', paths: ['src/{a,b}.ts'] },
      'g:float': { id: 'g:float', run: 'x', paths: ['src/**'], n: 1.5 },
      'g:needsnull': { id: 'g:needsnull', run: 'x', paths: ['src/**'], needs: ['g:nopaths'] },
      'g:needsok': { id: 'g:needsok', run: 'x', paths: ['src/**'], needs: ['g:src'] },
      'g:gitlink': { id: 'g:gitlink', run: 'x', paths: ['private/x'] },
      'g:gitlink2': { id: 'g:gitlink2', run: 'x', paths: ['private/x/**'] },
    };
    const mk = (r: string, scripts: Record<string, string> = {}) => ({
      exempt: new Set(['g:exempt']),
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
      get(h1, 'g:nopaths').reason === 'no-paths' && get(h1, 'g:nopaths').inputHash === null,
      'no-paths is null'
    );
    must(get(h1, 'g:env').reason === 'env' && get(h1, 'g:env').inputHash === null, 'env is null');
    must(
      get(h1, 'g:exempt').reason === 'exempt' && get(h1, 'g:exempt').inputHash === null,
      'exempt is null'
    );
    must(get(h1, 'g:forbid').reason === 'forbidden-glob', 'a { glob is forbidden');
    must(get(h1, 'g:float').reason === 'float-in-entry', 'a float entry is null');
    must(get(h1, 'g:needsnull').reason === 'needs-null:g:nopaths', 'a null needs hash propagates');
    must(get(h1, 'g:needsok').inputHash !== null, 'a needs on a carriable gate stays carriable');
    must(
      get(h1, 'g:gitlink').filesHash === get(h1, 'g:gitlink2').filesHash &&
        get(h1, 'g:gitlink').filesHash !== get(h1, 'g:nopaths').filesHash,
      'a glob naming a gitlink, bare or /**, reaches the gitlink entry'
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
    const okPlan = planCarry(mkPrior('ok'), h3, sel, salt);
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
    const failPlan = planCarry(mkPrior('fail'), h3, sel, salt);
    must(failPlan.carry.get('g:src')?.verdict === 'fail', 'an equal-hash fail carries as fail');
    const blocked = planCarry(mkPrior('blocked'), h3, sel, salt);
    must(!blocked.carry.has('g:src'), 'a blocked verdict never carries');
    const saltPlan = planCarry(mkPrior('ok', { saltHash: 'different' }), h3, sel, salt);
    must(
      saltPlan.carry.size === 0 && saltPlan.run.length === sel.length,
      'a salt mismatch re-runs everything'
    );
    must(
      planCarry(mkPrior('ok', { whole: false }), h3, sel, salt).carry.size === 0,
      'a partial prior never carries'
    );
    must(
      planCarry(mkPrior('ok', { schema: 1 }), h3, sel, salt).carry.size === 0,
      'a v1 prior never carries'
    );
    must(planCarry(null, h3, sel, salt).run.length === sel.length, 'no prior runs everything');
    const prior2 = mkPrior('ok');
    prior2.gates['g:src'].carriedFrom = { headTree: 'orig', head: 'o', finishedAt: 'f' };
    must(
      planCarry(prior2, h3, sel, salt).carry.get('g:src')?.carriedFrom?.headTree === 'orig',
      'an existing carriedFrom is kept'
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

/**
 * The exempt gate ids from carry-exempt.json's text, `{"schema": 1, "exempt": [{"id", "reason"}]}`; an absent file is the empty set.
 * One shape, read one way by the corpus printer and the runner, so the two can never disagree about what is exempt. Any other shape throws.
 */
export function exemptIdsOf(text: string | null): Set<string> {
  if (text === null) return new Set();
  const doc = JSON.parse(text) as { schema?: unknown; exempt?: unknown };
  if (doc.schema !== 1 || !Array.isArray(doc.exempt))
    throw new Error(`${CARRY_EXEMPT_REL}: expected {"schema": 1, "exempt": [...]}`);
  const ids = new Set<string>();
  for (const row of doc.exempt as Array<{ id?: unknown }>) {
    if (typeof row?.id !== 'string' || row.id === '')
      throw new Error(`${CARRY_EXEMPT_REL}: every exempt row needs a string "id"`);
    ids.add(row.id);
  }
  return ids;
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
    exempt: exemptIdsOf(showAt(tree, CARRY_EXEMPT_REL)),
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
    };
  }
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)
) {
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
  } else {
    process.stderr.write('usage: input-hash.ts --selftest | --print-corpus <tree>\n');
    process.exit(2);
  }
}
