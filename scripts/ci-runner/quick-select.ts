/**
 * `--quick` diff selection: a slow gate joins the quick lane when the change set since the last push touches it, inside a p90 wall budget.
 *
 * WHY. The quick lane deferred every `slow: true` gate unconditionally, so a slow gate whose own inputs had just changed was the one gate guaranteed not to judge them before the push. On 2026-10-01 that let a TS2322 reach CI through the deferred `check:types`.
 *
 * WHAT "TOUCHED" MEANS, in the inclusive direction on purpose (a false touch costs seconds and is bounded by the budget; a missed one is a deferral nobody sees):
 *   1. any declared `paths` glob matches a changed file;
 *   2. a `leaves` entry that is a repo file changed, or any file it imports, followed transitively (TS/JS relative specifiers, Python `rediacc_ci.*` and relative imports). Command leaves (`tsc`, `biome`, `knip`) name no file and add nothing;
 *   3. package.json changed AND the gate's npm script text differs from the base, following `npm run <x>` references, which is how parity resolves a `run` to its leaves;
 *   4. the gate declares NO `paths` and the change set is not empty: the `--changed` contract (select.ts), fail open on scope. Leaves name the gate's CODE, not what it reads: a corpus gate (prose style, python types, lint, the dist checks) reads files no leaf imports, so on 2026-10-01 a push that deleted files check:ci-prose-style scans passed this lane as "deferred, untouched" and CI went red on the stale baseline it left. Rules 1-3 still run first, because their reason is the more specific one to print.
 *
 * WHAT "THE LAST PUSH" MEANS: the merge-base of HEAD with the first ref that resolves among `@{push}`, `origin/<branch>`, `@{upstream}`, then `origin/main` (a branch never pushed has everything since main unpushed). `@{push}` and `@{upstream}` count only when they name THIS branch: on 2026-10-03 a push clone's branch tracked the already merged `origin/0930-1`, and the diff against that merge-base held 244 files. A tracking ref named for another branch is skipped and the skip is printed as a WARNING. The change set is that merge-base against the WORKTREE plus untracked files, since the quick lane judges the worktree. When none resolves, no slow gate is selected and the run SAYS so with the refs it tried: the quick lane is still the whole fast lane, so refusing it outright would punish a fresh clone for a question the fast gates do not need answered.
 *
 * THE TREE: a slow gate that declares a tree write (`writesTree`, or a `tree:` claim in `mutex`) is not admitted in a shared checkout, and is named as dropped. The quick lane did not run tracked-file writers before this selection existed, and a pre-push check that appends to a tracked ledger in a shared worktree changes the tree it is judging. In a clean, disposable clone (a `--receipt-out` outside the checkout, and an empty `git status` at selection) nobody else reads that tree, so a writer is admitted inside the budget like any other gate.
 *
 * EVERY TOUCHED GATE THAT IS DROPPED reaches the push receipt as `droppedTouched`, each with its kind (`tree`, `budget`, `unpriced`) and the exact command that runs it. The push guard refuses while any of them lacks a passing entry in `droppedVerified`, which a `--only` run of that gate writes into the same receipt.
 *
 * THE BUDGET: projected wall = max(base p90 + sum(cpu_i) / C, max(wall_i)), where the base p90 is the nearest-rank p90 of recorded quick walls that selected no slow gate, C the core budget, and wall_i/cpu_i a candidate's cost including any slow prerequisite it pulls in. Candidates are admitted cheapest first while the projection stays at or under the budget; every candidate left out is NAMED with its cost and the command that runs it. A candidate with no duration sample cannot be priced, and is dropped by name with the command that prices it, never admitted on a guess and never dropped silently.
 */
import fs from 'node:fs';
import path from 'node:path';

/** The quick lane's p90 wall ceiling, operator spec 2026-10-01. */
export const QUICK_BUDGET_MS = 90_000;
/** Assumed base p90 until enough base runs are recorded: the top of the 45-70 s range measured for ci:quick on 2026-10-01. */
export const BASE_FALLBACK_MS = 70_000;
/** Base runs needed before the recorded p90 replaces the fallback. */
export const MIN_BASE_SAMPLES = 3;
/** How many recent quick walls the history keeps. */
export const HISTORY_KEEP = 30;

export interface SlowCandidate {
  readonly id: string;
  readonly run: string;
  readonly paths?: readonly string[];
  readonly leaves: readonly string[];
}

export interface Touch {
  readonly id: string;
  /** Human reason: the first changed file and how it reached the gate. */
  readonly why: string;
}

/** `npm run <id>` with nothing else, the shape of every manifest `run`. */
function npmScriptOf(run: string): string | undefined {
  return /^npm run (\S+)$/.exec(run.trim())?.[1];
}

/** The script text of `id` and of every `npm run <x>` it reaches, joined in visit order. Undefined when `id` is absent. */
export function scriptClosure(
  scripts: Readonly<Record<string, string>>,
  id: string
): string | undefined {
  if (scripts[id] === undefined) return undefined;
  const seen = new Set<string>();
  const out: string[] = [];
  const visit = (name: string): void => {
    if (seen.has(name)) return;
    seen.add(name);
    const body = scripts[name];
    if (body === undefined) {
      out.push(`${name}=<absent>`);
      return;
    }
    out.push(`${name}=${body}`);
    for (const m of body.matchAll(/npm run (?:-s |--silent )?([\w:.-]+)/g)) visit(m[1]);
  };
  visit(id);
  return out.join('\n');
}

const TS_EXT = ['.ts', '.tsx', '.mts', '.cts', '.js', '.mjs', '.cjs'];

function resolveTs(root: string, fromFile: string, spec: string): string | undefined {
  const base = path.posix.normalize(path.posix.join(path.posix.dirname(fromFile), spec));
  const stem = base.replace(/\.(m|c)?js$/, '');
  const tries = [base, ...TS_EXT.map((e) => stem + e), ...TS_EXT.map((e) => `${base}/index${e}`)];
  return tries.find(
    (t) => fs.existsSync(path.join(root, t)) && fs.statSync(path.join(root, t)).isFile()
  );
}

function resolvePy(root: string, fromFile: string, mod: string): string[] {
  const out: string[] = [];
  let parts: string[];
  if (mod.startsWith('.')) {
    const dots = /^\.+/.exec(mod)?.[0].length ?? 1;
    let dir = path.posix.dirname(fromFile);
    for (let i = 1; i < dots; i += 1) dir = path.posix.dirname(dir);
    parts = [dir, ...mod.slice(dots).split('.').filter(Boolean)];
  } else if (mod.startsWith('rediacc_ci')) {
    parts = ['.ci', ...mod.split('.')];
  } else {
    return out;
  }
  const p = parts.join('/');
  for (const t of [`${p}.py`, `${p}/__init__.py`]) {
    if (fs.existsSync(path.join(root, t))) out.push(t);
  }
  return out;
}

/**
 * The repo files a gate's file leaves reach through imports, leaves included. Bounded by `cap` so a pathological graph cannot stall the lane; hitting the cap is reported by the caller as a touch on the leaf itself, which is the inclusive answer.
 */
export function leafClosure(
  root: string,
  leaves: readonly string[],
  cap = 4000
): { files: Set<string>; capped: boolean } {
  const files = new Set<string>();
  const queue = leaves.filter((l) => {
    const abs = path.join(root, l);
    return !path.isAbsolute(l) && fs.existsSync(abs) && fs.statSync(abs).isFile();
  });
  while (queue.length > 0) {
    const file = queue.shift() as string;
    if (files.has(file)) continue;
    files.add(file);
    if (files.size >= cap) return { files, capped: true };
    let text: string;
    try {
      text = fs.readFileSync(path.join(root, file), 'utf-8');
    } catch {
      continue;
    }
    if (/\.(m|c)?[jt]sx?$/.test(file)) {
      const specs = [
        ...text.matchAll(/(?:import|export)\s[^'"`;]*?from\s*['"](\.{1,2}\/[^'"]+)['"]/g),
        ...text.matchAll(/(?:import|require)\s*\(\s*['"](\.{1,2}\/[^'"]+)['"]\s*\)/g),
        ...text.matchAll(/^\s*import\s+['"](\.{1,2}\/[^'"]+)['"]/gm),
      ].map((m) => m[1]);
      for (const s of specs) {
        const hit = resolveTs(root, file, s);
        if (hit !== undefined && !files.has(hit)) queue.push(hit);
      }
    } else if (file.endsWith('.py')) {
      for (const m of text.matchAll(
        /^\s*from\s+(\.+[\w.]*|rediacc_ci[\w.]*)\s+import\s+([\w, ()]+)/gm
      )) {
        const mod = m[1];
        for (const hit of resolvePy(root, file, mod)) if (!files.has(hit)) queue.push(hit);
        // `from rediacc_ci.quality import foo` may name a MODULE foo, not a symbol.
        for (const name of m[2]
          .replace(/[()]/g, '')
          .split(',')
          .map((s) => s.trim().split(/\s+/)[0])) {
          if (name === '') continue;
          const sub = mod.endsWith('.') ? `${mod}${name}` : `${mod}.${name}`;
          for (const hit of resolvePy(root, file, sub)) if (!files.has(hit)) queue.push(hit);
        }
      }
      for (const m of text.matchAll(/^\s*import\s+(rediacc_ci[\w.]*)/gm)) {
        for (const hit of resolvePy(root, file, m[1])) if (!files.has(hit)) queue.push(hit);
      }
    }
  }
  return { files, capped: false };
}

export interface TouchInputs {
  readonly root: string;
  readonly changed: readonly string[];
  readonly matches: (file: string, globs: readonly string[]) => boolean;
  /** package.json scripts now and at the base; base undefined when it could not be read, which counts every npm script as changed if package.json changed. */
  readonly scriptsNow: Readonly<Record<string, string>>;
  readonly scriptsBase: Readonly<Record<string, string>> | undefined;
}

/** Which candidates the change set touches, each with the reason. Order follows `candidates`. */
export function touchedSlow(candidates: readonly SlowCandidate[], input: TouchInputs): Touch[] {
  const changed = new Set(input.changed);
  const pkgChanged = changed.has('package.json');
  const touches: Touch[] = [];
  for (const c of candidates) {
    if (c.paths !== undefined) {
      const hit = input.changed.find((f) => input.matches(f, c.paths ?? []));
      if (hit !== undefined) {
        touches.push({ id: c.id, why: `${hit} matches its paths` });
        continue;
      }
    }
    const closure = leafClosure(input.root, c.leaves);
    const leafHit = [...closure.files].find((f) => changed.has(f));
    if (leafHit !== undefined) {
      const direct = c.leaves.includes(leafHit);
      touches.push({
        id: c.id,
        why: `${leafHit} ${direct ? 'is a leaf' : 'is imported by a leaf'}`,
      });
      continue;
    }
    if (closure.capped) {
      touches.push({
        id: c.id,
        why: 'its leaf import graph exceeded the walk cap, counted as touched',
      });
      continue;
    }
    const script = npmScriptOf(c.run);
    if (pkgChanged && script !== undefined) {
      const now = scriptClosure(input.scriptsNow, script);
      const before =
        input.scriptsBase === undefined ? undefined : scriptClosure(input.scriptsBase, script);
      if (input.scriptsBase === undefined || now !== before) {
        touches.push({ id: c.id, why: `its npm script '${script}' changed in package.json` });
        continue;
      }
    }
    if (c.paths === undefined && input.changed.length > 0) {
      touches.push({
        id: c.id,
        why: 'it declares no paths, so any change may reach what it reads (the --changed fail-open rule)',
      });
    }
  }
  return touches;
}

export interface Cost {
  /** Wall of the candidate including the slow prerequisites it pulls in. */
  readonly wallMs: number;
  /** CPU of the same set. */
  readonly cpuMs: number;
  readonly source: string;
}

/** Why a touched candidate left the lane: refused at any price (`tree`), no duration sample (`unpriced`), or over the wall budget (`budget`). */
export type DropKind = 'tree' | 'budget' | 'unpriced';

export interface Dropped {
  readonly id: string;
  readonly reason: string;
  readonly kind: DropKind;
}

export interface BudgetVerdict {
  readonly admitted: readonly string[];
  readonly dropped: readonly Dropped[];
  readonly projectedMs: number;
}

/** Nearest-rank percentile. Undefined on no samples. */
export function percentile(xs: readonly number[], p: number): number | undefined {
  if (xs.length === 0) return undefined;
  const sorted = [...xs].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil((p / 100) * sorted.length));
  return sorted[rank - 1];
}

export function projectWall(baseMs: number, costs: readonly Cost[], cores: number): number {
  const cpu = costs.reduce((s, c) => s + c.cpuMs, 0);
  const longest = costs.reduce((m, c) => Math.max(m, c.wallMs), 0);
  return Math.max(baseMs + cpu / Math.max(1, cores), longest);
}

const s1 = (ms: number): string => `${(ms / 1000).toFixed(1)}s`;

/**
 * Cheapest first (by the wall it would add, then id), admitted while the projection stays within budget. `refuse` names a candidate the lane will not run at any price, with the reason; it is dropped by name before pricing.
 */
export function admitWithinBudget(
  touched: readonly string[],
  costOf: (id: string) => Cost | undefined,
  baseMs: number,
  cores: number,
  budgetMs: number = QUICK_BUDGET_MS,
  refuse: (id: string) => string | undefined = () => undefined
): BudgetVerdict {
  const dropped: Dropped[] = [];
  const priced: { id: string; cost: Cost; added: number }[] = [];
  for (const id of touched) {
    const refusal = refuse(id);
    if (refusal !== undefined) {
      dropped.push({ id, reason: refusal, kind: 'tree' });
      continue;
    }
    const cost = costOf(id);
    if (cost === undefined) {
      dropped.push({
        id,
        reason: `no duration sample to price it; measure once with \`npx tsx scripts/ci-runner/run.ts --only ${id}\``,
        kind: 'unpriced',
      });
      continue;
    }
    priced.push({ id, cost, added: projectWall(baseMs, [cost], cores) - baseMs });
  }
  priced.sort((a, b) => a.added - b.added || a.id.localeCompare(b.id));
  const admitted: { id: string; cost: Cost }[] = [];
  for (const p of priced) {
    const next = projectWall(baseMs, [...admitted.map((a) => a.cost), p.cost], cores);
    if (next <= budgetMs) {
      admitted.push(p);
    } else {
      dropped.push({
        id: p.id,
        reason: `projected wall ${s1(next)} with it exceeds the ${s1(budgetMs)} budget (its wall ${s1(p.cost.wallMs)}, cpu ${s1(p.cost.cpuMs)}, ${p.cost.source})`,
        kind: 'budget',
      });
    }
  }
  return {
    admitted: admitted.map((a) => a.id),
    dropped,
    projectedMs: projectWall(
      baseMs,
      admitted.map((a) => a.cost),
      cores
    ),
  };
}

export interface BaseResolution {
  readonly ref?: string;
  readonly via?: string;
  readonly mergeBase?: string;
  readonly tried: readonly string[];
  /** Tracking refs skipped because they name another branch, one sentence each. Empty when none was skipped. */
  readonly warnings: readonly string[];
}

/** `origin/0930-1` -> `0930-1`: the branch a tracking ref names, remote prefix stripped. */
function branchOfRef(name: string): string {
  const slash = name.indexOf('/');
  return slash < 0 ? name : name.slice(slash + 1);
}

/** `git` answers stdout trimmed, or undefined on any failure. */
export function resolvePushBase(
  git: (args: readonly string[]) => string | undefined,
  branch: string | undefined
): BaseResolution {
  const named = branch !== undefined && branch !== '';
  const candidates: [string, string][] = [['@{push}', '@{push}']];
  if (named) candidates.push([`origin/${branch}`, 'origin/<branch>']);
  candidates.push(['@{upstream}', '@{upstream}']);
  candidates.push(['origin/main', 'origin/main (never pushed: everything since main)']);
  const tried: string[] = [];
  // A tracking ref named for ANOTHER branch is not this branch's last push (2026-10-03: an upstream of origin/0930-1, already merged, widened the diff to 244 files). Judged up front, so the skip is reported even when origin/<branch> wins first.
  const warnings: string[] = [];
  const foreign = new Set<string>();
  for (const ref of ['@{push}', '@{upstream}']) {
    if (git(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]) === undefined) continue;
    const name = git(['rev-parse', '--abbrev-ref', ref]) ?? ref;
    if (named && branchOfRef(name) === branch) continue;
    foreign.add(ref);
    if (!warnings.some((w) => w.includes(` is ${name},`)))
      warnings.push(`${ref} is ${name}, not origin/${named ? branch : '<branch>'}; ignored`);
  }
  for (const [ref, via] of candidates) {
    tried.push(ref);
    if (foreign.has(ref)) continue;
    if (git(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]) === undefined) continue;
    const name = ref.startsWith('@') ? (git(['rev-parse', '--abbrev-ref', ref]) ?? ref) : ref;
    const mergeBase = git(['merge-base', 'HEAD', ref]);
    if (mergeBase === undefined || mergeBase === '') continue;
    return { ref: name, via, mergeBase, tried, warnings };
  }
  return { tried, warnings };
}

export interface WallSample {
  readonly at: string;
  readonly wallMs: number;
  readonly slowAdmitted: readonly string[];
}

export function readHistory(file: string): WallSample[] {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(file, 'utf-8'));
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (s): s is WallSample =>
        s !== null &&
        typeof s === 'object' &&
        typeof (s as WallSample).wallMs === 'number' &&
        Number.isFinite((s as WallSample).wallMs) &&
        (s as WallSample).wallMs > 0 &&
        Array.isArray((s as WallSample).slowAdmitted)
    );
  } catch {
    return [];
  }
}

export function appendHistory(file: string, sample: WallSample): void {
  try {
    const next = [...readHistory(file), sample].slice(-HISTORY_KEEP);
    // tree-write: safe the caller passes .ci/cache/quick-walls.json, a gitignored runner cache beside gate-durations.json
    fs.mkdirSync(path.dirname(file), { recursive: true });
    // tree-write: safe the same gitignored .ci/cache file as the line above
    fs.writeFileSync(file, `${JSON.stringify(next, null, 2)}\n`);
  } catch {
    // A scheduling statistic: a failed write costs accuracy on the next projection, never a verdict.
  }
}

/**
 * The base p90: recorded quick walls that admitted no slow gate, when there are enough of them; else EVERY recorded quick wall, which over-states the base by whatever those runs admitted and so errs toward admitting less; else the assumed fallback. The middle rung is what stops a branch whose every run admits something from never earning a base.
 */
export function baseP90(history: readonly WallSample[]): { ms: number; note: string } {
  const recent = history.slice(-20);
  const pure = recent.filter((s) => s.slowAdmitted.length === 0).map((s) => s.wallMs);
  if (pure.length >= MIN_BASE_SAMPLES) {
    const p = percentile(pure, 90) as number;
    return {
      ms: p,
      note: `base p90 ${s1(p)} over ${pure.length} recorded run(s) with no slow gate`,
    };
  }
  const all = recent.map((s) => s.wallMs);
  if (all.length >= MIN_BASE_SAMPLES) {
    const p = percentile(all, 90) as number;
    return {
      ms: p,
      note: `base p90 ${s1(p)} over ALL ${all.length} recorded quick run(s), slow admissions included (only ${pure.length} without), so it over-states the base`,
    };
  }
  return {
    ms: BASE_FALLBACK_MS,
    note: `base p90 ASSUMED ${s1(BASE_FALLBACK_MS)}: ${all.length} of ${MIN_BASE_SAMPLES} quick run(s) recorded`,
  };
}

/** The selftest, run from `run.ts --selftest`. Fixtures only; nothing here reads the real tree except a temp directory it creates. */
export function quickSelectSelftest(
  tmpRoot: string,
  matches: (file: string, globs: readonly string[]) => boolean
): { failures: string[]; assertions: number } {
  const failures: string[] = [];
  let assertions = 0;
  const check = (cond: boolean, message: string): void => {
    assertions += 1;
    if (!cond) failures.push(message);
  };
  // tree-write: safe the only caller passes os.tmpdir(), so the fixture lives outside the repository
  const root = fs.mkdtempSync(path.join(tmpRoot, 'quick-select-'));
  try {
    fs.mkdirSync(path.join(root, 'g', 'lib'), { recursive: true });
    fs.mkdirSync(path.join(root, '.ci', 'rediacc_ci', 'quality'), { recursive: true });
    fs.writeFileSync(
      path.join(root, 'g', 'touched.ts'),
      "import { x } from './lib/helper';\nexport const y = x;\n"
    );
    fs.writeFileSync(path.join(root, 'g', 'lib', 'helper.ts'), 'export const x = 1;\n');
    fs.writeFileSync(path.join(root, 'g', 'untouched.ts'), 'export const z = 2;\n');
    fs.writeFileSync(path.join(root, '.ci', 'rediacc_ci', '__init__.py'), '');
    fs.writeFileSync(path.join(root, '.ci', 'rediacc_ci', 'quality', '__init__.py'), '');
    fs.writeFileSync(path.join(root, '.ci', 'rediacc_ci', 'quality', 'core.py'), 'X = 1\n');
    fs.writeFileSync(path.join(root, '.ci', 'gate.py'), 'from rediacc_ci.quality import core\n');
    const cands: SlowCandidate[] = [
      // Every leaf-tracked fixture DECLARES paths: rule 4 selects a gate without them on any change, which would mask the leaf rules this selftest proves.
      {
        id: 'slow:touched',
        run: 'npm run slow:touched',
        paths: ['src/**'],
        leaves: ['g/touched.ts', 'tsc'],
      },
      {
        id: 'slow:untouched',
        run: 'npm run slow:untouched',
        paths: ['other/**'],
        leaves: ['g/untouched.ts'],
      },
      { id: 'slow:paths', run: 'npm run slow:paths', paths: ['docs/**'], leaves: ['biome'] },
      { id: 'slow:py', run: 'npm run slow:py', paths: ['py/**'], leaves: ['.ci/gate.py'] },
    ];
    const corpus: SlowCandidate = {
      id: 'slow:corpus',
      run: 'npm run slow:corpus',
      leaves: ['g/untouched.ts'],
    };
    const scripts = { 'slow:touched': 'a', 'slow:untouched': 'b && npm run inner', inner: 'c' };
    const pick = (
      changed: string[],
      m = matches,
      base: Record<string, string> | undefined = scripts
    ): string[] =>
      touchedSlow(cands, { root, changed, matches: m, scriptsNow: scripts, scriptsBase: base }).map(
        (t) => t.id
      );

    // A TOUCHED slow gate is selected and an UNTOUCHED one stays deferred.
    const direct = pick(['g/touched.ts']);
    check(direct.includes('slow:touched'), 'a slow gate whose leaf changed must be selected');
    check(!direct.includes('slow:untouched'), 'a slow gate nothing touched must stay deferred');
    // Through an import, and through a Python module named in `from pkg import module`.
    check(
      pick(['g/lib/helper.ts']).join() === 'slow:touched',
      'a change to a file a leaf imports must select it'
    );
    check(
      pick(['.ci/rediacc_ci/quality/core.py']).join() === 'slow:py',
      'a change to a Python module a leaf imports must select it'
    );
    check(pick(['docs/a.md']).join() === 'slow:paths', 'a declared paths glob must still select');
    // The npm script half, both directions.
    check(
      pick(['package.json'], matches, { ...scripts, inner: 'c-old' }).join() === 'slow:untouched',
      'a changed npm script reached through `npm run` must select its gate, and only that gate'
    );
    check(
      pick(['package.json']).length === 0,
      'CONTROL: package.json changed elsewhere must select nothing'
    );

    // CONTROL, THE MUTANT: a selector that ignores the diff. If this fixture could not tell it apart from the real one, the two assertions above would pass on a broken selector.
    const mutant = pick(['g/touched.ts'], () => true);
    check(
      mutant.includes('slow:paths'),
      'CONTROL: under a matcher that ignores the diff the untouched path-scoped gate must be selected, or the fixture cannot see a broken selector'
    );
    check(pick([]).length === 0, 'CONTROL: an empty change set must select no slow gate');

    // RULE 4: a gate that declares no paths is selected by a change no leaf reaches (its corpus), and an empty change set still selects nothing.
    const withCorpus = (changed: string[]): string[] =>
      touchedSlow([corpus], {
        root,
        changed,
        matches,
        scriptsNow: scripts,
        scriptsBase: scripts,
      }).map((t) => t.id);
    check(
      withCorpus(['docs/deleted.md']).join() === 'slow:corpus',
      'a slow gate that declares no paths must be selected by any change (the --changed fail-open rule)'
    );
    check(
      withCorpus([]).length === 0,
      'CONTROL: an empty change set must not select a gate without paths'
    );

    // THE BUDGET. Base 70 s on 10 cores: +10 s fits, +15 s on top does not; the dropped one is named; a wall alone over budget and an unpriced gate are both dropped by name.
    const costs: Record<string, Cost> = {
      cheap: { wallMs: 20_000, cpuMs: 100_000, source: 'fixture' },
      dear: { wallMs: 30_000, cpuMs: 150_000, source: 'fixture' },
      huge: { wallMs: 120_000, cpuMs: 120_000, source: 'fixture' },
    };
    const v = admitWithinBudget(
      ['dear', 'cheap', 'huge', 'unpriced'],
      (id) => costs[id],
      70_000,
      10
    );
    check(
      v.admitted.join() === 'cheap',
      `the budget must admit only the cheapest fit, admitted ${v.admitted.join()}`
    );
    check(
      v.dropped
        .map((d) => d.id)
        .sort()
        .join() === 'dear,huge,unpriced',
      `every left-out candidate must be NAMED, got ${v.dropped.map((d) => d.id).join()}`
    );
    check(v.projectedMs === 80_000, `projected wall must be 80 s, got ${v.projectedMs}`);
    const refused = admitWithinBudget(
      ['cheap'],
      (id) => costs[id],
      70_000,
      10,
      200_000,
      (id) => (id === 'cheap' ? 'writes the tracked tree' : undefined)
    );
    check(
      refused.admitted.length === 0 && refused.dropped[0]?.reason === 'writes the tracked tree',
      'a refused candidate must be dropped BY NAME with its reason even when it fits the budget'
    );
    // THE KIND of each drop, all three, so a hard-coded kind fails two of them.
    const kindOf = (id: string): string | undefined => v.dropped.find((d) => d.id === id)?.kind;
    check(refused.dropped[0]?.kind === 'tree', 'a refused candidate must drop with kind tree');
    check(
      kindOf('dear') === 'budget' && kindOf('huge') === 'budget',
      'a candidate over budget must drop with kind budget'
    );
    check(
      kindOf('unpriced') === 'unpriced',
      'a candidate with no cost must drop with kind unpriced'
    );
    check(
      admitWithinBudget(['dear', 'cheap'], (id) => costs[id], 70_000, 10, 200_000).admitted
        .length === 2,
      'CONTROL: a generous budget must admit both, or the drop above proves nothing about the budget'
    );

    // THE BASE: ordered fallback, and unresolved names what it tried.
    const answers = (ok: Record<string, string>) => (args: readonly string[]) => {
      if (args[0] === 'rev-parse' && args[1] === '--verify')
        return ok[args[3].replace('^{commit}', '')];
      if (args[0] === 'merge-base') return ok[args[2]] === undefined ? undefined : `mb-${args[2]}`;
      if (args[0] === 'rev-parse' && args[1] === '--abbrev-ref')
        return ok[`name:${args[2]}`] ?? 'origin/b';
      return undefined;
    };
    check(
      resolvePushBase(answers({ '@{push}': 'x', 'origin/main': 'y' }), 'b').via === '@{push}',
      '@{push} must win when it resolves'
    );
    check(
      resolvePushBase(answers({ 'origin/main': 'y' }), 'b').mergeBase === 'mb-origin/main',
      'with no upstream the base must fall back to origin/main'
    );
    // AN UPSTREAM NAMED FOR ANOTHER BRANCH is skipped and said, whether origin/<branch> exists or only origin/main does.
    const foreign = resolvePushBase(
      answers({
        '@{upstream}': 'x',
        'name:@{upstream}': 'origin/0930-1',
        'origin/b': 'z',
        'origin/main': 'y',
      }),
      'b'
    );
    check(
      foreign.via === 'origin/<branch>' &&
        foreign.warnings.some((w) => w.includes('origin/0930-1')),
      `an upstream named for another branch must lose to origin/<branch>, with a warning naming it; got ${foreign.via} ${foreign.warnings.join('; ')}`
    );
    const foreignOnly = resolvePushBase(
      answers({ '@{upstream}': 'x', 'name:@{upstream}': 'origin/0930-1', 'origin/main': 'y' }),
      'b'
    );
    check(
      foreignOnly.ref === 'origin/main' &&
        foreignOnly.warnings.some((w) => w.includes('origin/0930-1')),
      `with no origin/<branch>, a foreign upstream must fall to origin/main with the same warning; got ${foreignOnly.ref}`
    );
    const own = resolvePushBase(
      answers({ '@{upstream}': 'x', 'name:@{upstream}': 'origin/b', 'origin/main': 'y' }),
      'b'
    );
    check(
      own.via === '@{upstream}' && own.warnings.length === 0,
      `CONTROL: an upstream named origin/<branch> must win with no warning; got ${own.via} ${own.warnings.join('; ')}`
    );
    const none = resolvePushBase(answers({}), 'b');
    check(
      none.mergeBase === undefined && none.tried.length === 4,
      'with nothing resolvable the base must be undefined and name all four refs tried'
    );
    check(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) === 9, 'nearest-rank p90 of 1..10 is 9');
    check(
      baseP90([{ at: '', wallMs: 50_000, slowAdmitted: [] }]).ms === BASE_FALLBACK_MS,
      'one base sample must fall back to the assumed base, not trust one run'
    );
    check(
      baseP90([
        { at: '', wallMs: 50_000, slowAdmitted: [] },
        { at: '', wallMs: 60_000, slowAdmitted: [] },
        { at: '', wallMs: 55_000, slowAdmitted: [] },
        { at: '', wallMs: 200_000, slowAdmitted: ['x'] },
      ]).ms === 60_000,
      'a run that admitted a slow gate must not inflate the base p90'
    );
    check(
      baseP90([
        { at: '', wallMs: 50_000, slowAdmitted: ['x'] },
        { at: '', wallMs: 60_000, slowAdmitted: ['x'] },
        { at: '', wallMs: 80_000, slowAdmitted: ['x'] },
      ]).ms === 80_000,
      'with too few runs free of slow gates the base must fall back to ALL runs, conservatively, not to the assumed value'
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
  return { failures, assertions };
}
