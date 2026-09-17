/**
 * The row providers behind `npx tsx scripts/gen-docs.ts`.
 *
 * A PROVIDER SCANS THE TREE. It never carries a hand-written list of the things it documents,
 * because a hand-written list is exactly the artifact this phase exists to abolish. Three
 * measured examples from one session: `.dead-bash-allowlist` said "the 17 gate scripts" when
 * there are 131, scripts/gates/check-ci-parity.ts said "runs 57 gate tests", and
 * docs/agent-reference/ci-gates.md said "254 fast gates" against a live 312. Each was written
 * true and went stale in silence, because nothing re-derived it.
 *
 * THE CONSEQUENCE THAT MATTERS. Adding a gate, a hook guard, a suppression file or a `.ci`
 * directory changes what these providers emit with NO edit to this file. That is the
 * "modular and dynamic" acceptance test of docs/ci-overhaul/08-driver-contract.md section 7,
 * applied to documentation.
 *
 * NO PROVIDER IMPORTS scripts/ci-runner/manifest.ts, AND THAT IS A RULE RATHER THAN A TASTE.
 * The gate catalogue reads `scripts/ci-runner/gates.lock.json`, the committed JSON projection
 * of the manifest that `check:ci-gates-lock` keeps faithful in both directions. An earlier
 * draft of this file imported the typed `GATES` export instead. That was reversed for the
 * reason docs/ci-overhaul/08-driver-contract.md gives: `manifest.ts` is a single-writer file
 * behind the root driver's merge queue for the whole program, and every additional reader of it
 * is one more thing the registry workstream has to carry across. Two readers were drained onto
 * the lock the same day. Adding a third reader back would have widened the job this generator
 * exists to make smaller.
 *
 * The lock is also the shape a provider wants: it is data, so the anti-vacuity guard below can
 * refuse an empty or malformed file outright, where a broken TypeScript import would surface as
 * a module-load stack trace somewhere else entirely.
 *
 * ENUMERATION IS FROM `git ls-files`, i.e. the INDEX, with one guard. Section 5b of the driver
 * contract records check-shell-declared-commands.ts crashing on six unstaged deletions: the
 * index listed files the worktree no longer had. Every provider here therefore filters to paths
 * that are regular files on disk and reports the rest as `missing` rather than throwing. The
 * flip side is that an UNTRACKED new file is invisible to these providers. That is the correct
 * bias for a record other waves will diff against: an untracked file is not yet part of the
 * repository's contract.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/**
 * Byte-order comparison, NOT `localeCompare`.
 *
 * Determinism is a hard requirement here: two `--write` runs on a clean tree must be
 * byte-identical, and a later wave diffs a recorded SET against a fresh one. `localeCompare`
 * consults the host ICU collation, so the same rows can order differently on two machines and
 * produce a spurious drift red. `<`/`>` on strings is UTF-16 code-unit order, which is fixed.
 */
export const byCodePoint = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export interface ProviderRow {
  /** The set member. Unique within a provider, and what a set diff compares. */
  key: string;
  /** Rendered columns, in the order `columns` declares. */
  cells: string[];
}

export interface Provider {
  id: string;
  /** One line saying what this provider SCANS, printed in the generated region. */
  scans: string;
  columns: string[];
  rows(root: string): ProviderRow[];
  /** Paths the index claims but the worktree does not have. Reported, never thrown on. */
  missing?(root: string): string[];
}

/**
 * Tracked paths under `paths`, with SUBMODULE GITLINKS dropped.
 *
 * `git ls-files` reports a submodule as a single entry whose mode is 160000, and that entry is a
 * DIRECTORY on disk. A naive "is this a regular file" filter therefore reports `private/renet`,
 * `private/account`, `private/elite` and `private/homebrew-tap` as missing on every single run.
 * Four false alarms every run is how a report teaches its reader to skip it, so the mode is read
 * and the gitlinks are excluded before anything is judged.
 */
const lsFiles = (root: string, ...paths: string[]): string[] =>
  execFileSync('git', ['-C', root, 'ls-files', '-s', '-z', '--', ...paths], {
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\0')
    .filter((line) => line !== '')
    .flatMap((line) => {
      // "<mode> <sha> <stage>\t<path>"
      const tab = line.indexOf('\t');
      if (tab < 0) return [];
      const mode = line.slice(0, line.indexOf(' '));
      return mode === '160000' ? [] : [line.slice(tab + 1)];
    });

/** Index paths that are regular files right now, and the ones that are not. */
const presentFiles = (root: string, listed: string[]): { present: string[]; missing: string[] } => {
  const present: string[] = [];
  const missing: string[] = [];
  for (const f of listed) {
    let ok = false;
    try {
      ok = fs.statSync(path.join(root, f)).isFile();
    } catch {
      ok = false;
    }
    (ok ? present : missing).push(f);
  }
  return { present: present.sort(byCodePoint), missing: missing.sort(byCodePoint) };
};

const yn = (v: unknown): string => (v === true ? 'yes' : 'no');

/* ------------------------------------------------------------------ gates */

/** The committed JSON projection of the manifest. See the header on why this and not the TS. */
export const GATES_LOCK = 'scripts/ci-runner/gates.lock.json';

/** Exactly the fields this provider renders. The lock carries more; none of it is needed here. */
interface LockEntry {
  id: string;
  gate?: boolean;
  slow?: boolean;
  qualityGateTest?: boolean;
  ci:
    | { kind: 'step'; job?: string; step?: string }
    | { kind: 'test'; test?: string }
    | { kind: 'local-only' };
}

/**
 * The lock, or a refusal that says which part of it is wrong.
 *
 * ANTI-VACUITY IS THE WHOLE REASON THIS FUNCTION IS NOT THREE LINES. A missing file, a truncated
 * write, or a lock that parsed to `[]` would all yield zero rows, and zero rows renders as a
 * table with a header and no body -- which reads as "there are no gates" rather than as "the
 * instrument is broken". The generated region would then be REWRITTEN to that empty state, and
 * `--write` would report success having deleted the catalogue.
 *
 * NO NUMERIC FLOOR HERE, DELIBERATELY. Section 6 of the driver contract retires hand-typed
 * counts: a floor of 300 over 411 entries still passes after 111 vanish. The structural refusals
 * below (parses, is an array, is non-empty, every entry has an id and a ci kind) catch a broken
 * instrument, and the pre-port SET snapshot in scripts/data/doc-registry-preport.json is what
 * catches a silent partial drop. Those are two different jobs and neither is a count.
 */
export const readGatesLock = (root: string): LockEntry[] => {
  const abs = path.join(root, GATES_LOCK);
  let text: string;
  try {
    text = fs.readFileSync(abs, 'utf-8');
  } catch {
    throw new Error(
      `${GATES_LOCK} is missing. It is a COMMITTED file, not a build output, because readers ` +
        'that cannot parse TypeScript need it present on a fresh checkout. Regenerate it with ' +
        '`npm run gen:gates-lock`.'
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    throw new Error(`${GATES_LOCK} is not valid JSON: ${(e as Error).message}`);
  }
  if (!Array.isArray(parsed)) {
    throw new Error(
      `${GATES_LOCK} is not a JSON array. Order is load-bearing there (pool.ts breaks ` +
        'scheduling ties on the array index), so an object form is a defect, not a variant.'
    );
  }
  if (parsed.length === 0) {
    throw new Error(
      `${GATES_LOCK} holds zero entries. Rendering that would rewrite the gate catalogue to an ` +
        'empty table and report success, which is the vacuity this generator exists to refuse.'
    );
  }
  const entries = parsed as LockEntry[];
  for (const [i, g] of entries.entries()) {
    if (typeof g?.id !== 'string' || g.id === '') {
      throw new Error(`${GATES_LOCK} entry ${i} has no id`);
    }
    if (typeof g?.ci?.kind !== 'string') {
      throw new Error(`${GATES_LOCK} entry ${i} (${g.id}) has no ci.kind`);
    }
  }
  return entries;
};

/**
 * Where CI runs a gate, in one cell.
 *
 * The three `ci.kind` values are not interchangeable and the difference is the thing a reader
 * needs: `step` names the workflow lane, `test` means a gate test under .ci/scripts/test/gates/
 * drives the real scan, and `local-only` means CI does NOT run it at all. Flattening them to a
 * single "covered" boolean is how a local-only gate gets mistaken for CI coverage.
 */
const gateWhere = (g: LockEntry): string => {
  if (g.ci.kind === 'step') return `${g.ci.job ?? '(no job)'} / ${g.ci.step ?? '(no step)'}`;
  if (g.ci.kind === 'test') return `test: ${g.ci.test ?? '(no test)'}`;
  return 'local-only';
};

export const gatesProvider: Provider = {
  id: 'gates',
  scans: `${GATES_LOCK}, the committed projection of the manifest that \`check:ci-gates-lock\` keeps faithful`,
  columns: ['Gate', 'Runs in CI as', 'Is gate', 'Slow', 'Gate test'],
  rows: (root) =>
    readGatesLock(root)
      .map((g) => ({
        key: g.id,
        cells: [g.id, gateWhere(g), yn(g.gate), yn(g.slow), yn(g.qualityGateTest)],
      }))
      .sort((a, b) => byCodePoint(a.key, b.key)),
  missing: (root) => (fs.existsSync(path.join(root, GATES_LOCK)) ? [] : [GATES_LOCK]),
};

/**
 * The same catalogue folded to one row per CI lane, for documents that need the SHAPE.
 *
 * THIS EXISTS BECAUSE ALTITUDE IS A REAL CONSTRAINT, not because a second view is nice to
 * have. `gatesProvider` renders one row per gate, which is right for the reference document
 * a reader consults about a specific gate and wrong for CLAUDE.md, where four hundred rows
 * would bury the standing orders they sit next to. The alternative -- a human writing "about
 * 250 fast gates" into CLAUDE.md -- is exactly the sentence that went stale in silence and
 * that this whole generator exists to abolish: docs/agent-reference/ci-gates.md said "254
 * fast gates" against a live 312.
 *
 * SO THE SUMMARY IS DERIVED FROM THE SAME LOCK, never typed. A lane that gains a gate moves
 * this table with no edit anywhere, and a lane that loses every gate disappears from it,
 * which is the shape a reader can act on.
 *
 * THE `(all lanes)` ROW IS PART OF THE RECORD, not decoration. A per-lane table with no total
 * invites the reader to add the column up by eye, and the whole point of a generated region is
 * that no human arithmetic sits between the tree and the sentence. It sorts first because `(`
 * precedes every letter and digit in code-unit order, which is the ordering byCodePoint fixes.
 */
export const gatesSummaryProvider: Provider = {
  id: 'gates-summary',
  scans: `${GATES_LOCK}, folded to one row per CI lane`,
  // "IS a gate test", not "has one", and the distinction was got wrong once here before the table was read against the lock. `qualityGateTest` marks an entry that IS one of the on-disk gate tests -- manifest.ts says so outright, and every one of the 144 rows carrying it has an id beginning `gate-test:`, with no `gate-test:` entry lacking it. A column headed "Has a gate test" would
  // have told every reader that 86 quality-code gates are untested, which is a different and false claim.
  columns: ['Where it runs', 'Registered', '`gate: true`', 'Slow', 'Is a gate test'],
  rows: (root) => {
    const lanes = new Map<string, { n: number; gate: number; slow: number; test: number }>();
    const bump = (key: string, g: LockEntry): void => {
      const row = lanes.get(key) ?? { n: 0, gate: 0, slow: 0, test: 0 };
      row.n += 1;
      if (g.gate === true) row.gate += 1;
      if (g.slow === true) row.slow += 1;
      if (g.qualityGateTest === true) row.test += 1;
      lanes.set(key, row);
    };
    for (const g of readGatesLock(root)) {
      // The LANE, not the step. `gateWhere` renders "<job> / <step>" because a reader chasing
      // one gate needs the step; folding on that would produce a row per gate and no summary
      // at all. The job is the unit a reader schedules and reasons about.
      const kind = g.ci.kind;
      const key =
        kind === 'step'
          ? `step / ${g.ci.job ?? '(no job)'}`
          : kind === 'test'
            ? 'test (a gate test drives it)'
            : 'local-only (CI never runs it)';
      bump(key, g);
      bump('(all lanes)', g);
    }
    return [...lanes.entries()]
      .sort((a, b) => byCodePoint(a[0], b[0]))
      .map(([key, v]) => ({
        key,
        cells: [key, String(v.n), String(v.gate), String(v.slow), String(v.test)],
      }));
  },
  missing: (root) => (fs.existsSync(path.join(root, GATES_LOCK)) ? [] : [GATES_LOCK]),
};

/* ------------------------------------------------------------- hook guards */

interface WiredHook {
  event: string;
  matcher: string;
  file: string;
}

/**
 * Every hook `.claude/settings.json` actually wires, as (event, matcher, file) triples.
 *
 * DERIVED FROM THE WIRING, NOT FROM A CHAIN LIST. `.ci/scripts/quality/check-hook-integrity.sh`
 * carries `CHAINS=(pre-bash pre-edit pre-ask post-bash)` by hand, and its own comment records
 * what that costs: post-bash was MISSING from that array until 2026-08-28, so two registered
 * guards sat outside the inventory and could have been deleted with no gate noticing. Reading
 * the wiring means a new chain, or a new event, appears here the moment settings.json wires it.
 */
const wiredHooks = (root: string): WiredHook[] => {
  const settings = path.join(root, '.claude', 'settings.json');
  if (!fs.existsSync(settings)) return [];
  const parsed = JSON.parse(fs.readFileSync(settings, 'utf-8')) as {
    hooks?: Record<string, Array<{ matcher?: string; hooks?: Array<{ command?: string }> }>>;
  };
  const out: WiredHook[] = [];
  for (const [event, matchers] of Object.entries(parsed.hooks ?? {})) {
    for (const m of matchers) {
      for (const h of m.hooks ?? []) {
        // The command is a shell line: `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"` or `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/y.py" --flag`. Pull every hook path out of it rather than assuming one shape, so a wrapper that runs two guards is not silently reported as running one. BOTH hook trees, and the alternation is load-bearing rather than tidy. This pattern was
        // `\.claude\/hooks\/`, which cannot match `.claude/rediacc_hooks/`: measured 2026-09-07 it found 14 of the 15 hook paths in the wiring and missed exactly `.claude/rediacc_hooks/dispatch.py`. That one miss is the whole problem, because the dispatcher is the ONLY edge from settings.json into the 64 guard modules, so widening the FILE LIST without fixing this pattern would
        // seed the closure without its single entry point and report all 64 live guards as dead code. Captures repo-relative now, so a key names a real path from the repo root.
        for (const hit of (h.command ?? '').matchAll(
          /\.claude\/(?:hooks|rediacc_hooks)\/[A-Za-z0-9_./-]+/g
        )) {
          out.push({ event, matcher: m.matcher ?? '(any)', file: hit[0] ?? '' });
        }
      }
    }
  }
  return out;
};

/**
 * How each file under .claude/hooks/ is REACHED, computed as a closure.
 *
 * The naive column is "is this wired in settings.json", and it is wrong in a way that would make
 * the table useless: `stop/` is a wired directory holding thirty-odd `wl_*.py` MODULES that
 * worklist.py imports. Reporting every one of them as unwired reads as thirty defects and buys a
 * reader nothing.
 *
 * So reachability is transitive. Start from what settings.json wires, then repeatedly admit any
 * hook file whose module stem or basename is named by an already-reached one, to a fixpoint. The
 * residue is the interesting set: a file under .claude/hooks/ that NOTHING reaches is dead, and
 * dead code beside live guards is exactly what gets "simplified" into a hole later.
 *
 * Naming by stem is a textual test and can over-admit (a stem that happens to appear in prose).
 * That direction is the safe one: over-admitting hides a dead file, it never invents a false
 * accusation, and this table is a record rather than an enforcement gate.
 */
const reachability = (root: string, wired: Set<string>, files: string[]): Map<string, string> => {
  const text = new Map<string, string>();
  for (const rel of files) {
    try {
      // REPO-RELATIVE. This used to join `.claude/hooks` back on, which quietly made that one directory the only thing this closure could ever read.
      text.set(rel, fs.readFileSync(path.join(root, rel), 'utf-8'));
    } catch {
      text.set(rel, '');
    }
  }
  const reached = new Map<string, string>();
  for (const w of wired) reached.set(w, 'settings.json');

  // TWO KINDS OF EDGE THIS TEXTUAL CLOSURE CANNOT SEE, both of which would otherwise be reported as dead code. The comment above promises that over-admitting is the safe
  // direction and that this table "never invents a false accusation"; without these two
  // seeds it does exactly that, and the accusation lands on live guards.
  //
  // 1. GLOB DISCOVERY. `.claude/rediacc_hooks/dispatch.py` does not name a single guard. It globs `block_*.py`, `warn_*.py` and `require_*.py` under `guards/` and keeps the modules declaring a matching `CHAIN`. Measured 2026-09-07: `python3 .claude/rediacc_hooks/dispatch.py --list` prints `pre-bash warn_submodule_deletions ...`, while the closure reported that same file as reached
  // by nothing, because no reached file contains its name. 2. PYTEST COLLECTION. `pyproject.toml:237-241` names `.claude/rediacc_hooks/tests` in `testpaths`, so a `test_*.py` there is run by the suite, not by the wiring.
  for (const rel of files) {
    if (reached.has(rel)) continue;
    const base = path.basename(rel);
    if (
      /\.claude\/rediacc_hooks\/guards\//.test(rel) &&
      /^(block|warn|require)_[A-Za-z0-9_]+\.py$/.test(base) &&
      /^CHAIN\s*=/m.test(text.get(rel) ?? '')
    ) {
      reached.set(rel, 'via dispatch.py (glob)');
    } else if (/\.claude\/rediacc_hooks\/tests\//.test(rel) && /^test_.*\.py$/.test(base)) {
      reached.set(rel, 'via pytest (testpaths)');
    }
  }
  let grew = true;
  while (grew) {
    grew = false;
    for (const rel of files) {
      if (reached.has(rel)) continue;
      const stem = path.basename(rel).replace(/\.(sh|py)$/, '');
      const base = path.basename(rel);
      for (const [src, body] of text) {
        if (!reached.has(src) || src === rel) continue;
        if (
          body.includes(base) ||
          (rel.endsWith('.py') && new RegExp(`\\b${stem}\\b`).test(body))
        ) {
          reached.set(rel, `via ${src}`);
          grew = true;
          break;
        }
      }
    }
  }
  return reached;
};

export const hookGuardsProvider: Provider = {
  id: 'hook-guards',
  scans:
    'the `hooks` wiring in .claude/settings.json, closed transitively over the tracked files under .claude/hooks/ and .claude/rediacc_hooks/ (.claude/oracles/ excluded on purpose: those twins are wired to no event by design)',
  columns: ['Hook file', 'Events', 'Reached', 'Language'],
  rows: (root) => {
    const wired = wiredHooks(root);
    const events = new Map<string, Set<string>>();
    for (const w of wired) {
      const set = events.get(w.file) ?? new Set<string>();
      set.add(w.event);
      events.set(w.file, set);
    }

    // BOTH HOOK TREES, and why .claude/oracles is NOT a third.
    //
    // Until 2026-09-07 this scanned `.claude/hooks` alone, which made this region's own promise unkeepable: it says a tracked file nothing reaches is dead code sitting beside live guards, while 64 tracked modules under `.claude/rediacc_hooks` were not in the set at all, so they could never be reported in either direction. The parity gate could not catch it, because it compares
    // this generator against itself: both sides were equally blind and the document was wrong while the gate was green.
    //
    // `.claude/oracles` is excluded ON PURPOSE and must stay excluded. Those 50 files are the bash twins the Python guards are differentially compared against (`test_guards_differential`). They are deliberately wired to NO event, so a reachability closure would correctly find nothing reaching them and report all 50 as dead code. That is precisely the reading that gets a
    // differential corpus "simplified" away, which is the failure this region exists to prevent rather than to cause. Their coverage is the differential test, not the wiring.
    const { present } = presentFiles(root, lsFiles(root, '.claude/hooks', '.claude/rediacc_hooks'));
    const members = present
      .filter((f) => /\.(sh|py)$/.test(f))
      // State snapshots and byte-compiled caches are not hooks. Both are per-session litter that would make this record differ between two machines looking at the same commit.
      .filter((f) => !f.includes('/state/') && !f.includes('__pycache__'));

    const reached = reachability(root, new Set(events.keys()), members);
    const keys = new Set([...members, ...events.keys()]);

    return [...keys].sort(byCodePoint).map((f) => ({
      key: f,
      cells: [
        f,
        [...(events.get(f) ?? [])].sort(byCodePoint).join(', ') || '(none)',
        reached.get(f) ?? '(nothing)',
        path.extname(f).replace('.', '') || '(none)',
      ],
    }));
  },
  missing: (root) =>
    presentFiles(root, lsFiles(root, '.claude/hooks', '.claude/rediacc_hooks')).missing,
};

/**
 * The hook wiring folded to one row per EVENT, plus the residue.
 *
 * Same altitude argument as `gates-summary`: `hook-guards` renders a row per file, which is
 * the reference view, and CLAUDE.md needs the shape. What a reader of CLAUDE.md actually has
 * to know is which events are armed at all and roughly how much is hanging off each, because
 * a chain nobody realises exists is how post-bash sat outside the hook inventory until
 * 2026-08-28 with two registered guards inside it.
 *
 * THE LAST ROW IS THE ONE WORTH READING. A tracked file under `.claude/hooks/` that nothing
 * reaches, transitively, from the wiring is dead code sitting beside live guards, and dead
 * code beside live guards is what gets "simplified" into a hole later. It is reported as a
 * COUNT here and named file by file in the `hook-guards` region, which is the right division:
 * the summary says whether to go look, the reference says where.
 *
 * Files, not commands, is the unit. One wired command can name two hook paths, so counting
 * commands would under-report; `wiredHooks` already splits a command into every path it
 * names, for the same reason.
 */
export const hookSummaryProvider: Provider = {
  id: 'hook-summary',
  scans:
    'the `hooks` wiring in .claude/settings.json, folded to one row per event, with the unreached residue',
  columns: ['Hook event', 'Matchers', 'Hook files'],
  rows: (root) => {
    const wired = wiredHooks(root);
    const byEvent = new Map<string, { matchers: Set<string>; files: Set<string> }>();
    for (const w of wired) {
      const row = byEvent.get(w.event) ?? { matchers: new Set(), files: new Set() };
      row.matchers.add(w.matcher);
      row.files.add(w.file);
      byEvent.set(w.event, row);
    }

    // Same two trees as hook-guards, for the same reason its comment gives: this row set and that one must describe the same tree, or the summary and the reference disagree. Before 2026-09-07 both were scoped to `.claude/hooks`, so the residue count below counted the unreached files of ONE tree while calling itself "tracked hook files nothing reaches".
    const { present } = presentFiles(root, lsFiles(root, '.claude/hooks', '.claude/rediacc_hooks'));
    const members = present
      .filter((f) => /\.(sh|py)$/.test(f))
      // Identical exclusions to hook-guards, and they must stay identical: state snapshots and byte-compiled caches are per-session litter, so counting them here and not there would make the summary and the reference disagree about the same tree.
      .filter((f) => !f.includes('/state/') && !f.includes('__pycache__'));
    const reached = reachability(root, new Set(wired.map((w) => w.file)), members);
    const unreached = members.filter((f) => !reached.has(f)).length;

    const rows: ProviderRow[] = [...byEvent.entries()]
      .sort((a, b) => byCodePoint(a[0], b[0]))
      .map(([event, v]) => ({
        key: event,
        cells: [event, String(v.matchers.size), String(v.files.size)],
      }));
    rows.push({
      key: '(all events)',
      cells: [
        '(all events)',
        String(new Set(wired.map((w) => `${w.event}\u0000${w.matcher}`)).size),
        String(new Set(wired.map((w) => w.file)).size),
      ],
    });
    rows.push({
      key: '(tracked hook files nothing reaches)',
      cells: ['(tracked hook files nothing reaches)', '-', String(unreached)],
    });
    return rows;
  },
  missing: (root) =>
    presentFiles(root, lsFiles(root, '.claude/hooks', '.claude/rediacc_hooks')).missing,
};

/* ------------------------------------------------------------ suppressions */

/**
 * Extensions that are CODE or PROSE, and therefore never a suppression mechanism themselves.
 *
 * Every one of these mentions `BLOCKER:` somewhere: the validators implement the convention,
 * the gates cite it in their headers, and docs/agent-reference/suppressions.md documents it. A
 * mechanism is a file whose BLOCKER lines gate DATA that a reader consumes, so the predicate is
 * "carries BLOCKER: and is not source or prose". Stated as an extension rule rather than a name
 * list, because a name list is the thing this whole module refuses to keep.
 */
const NOT_A_MECHANISM = new Set([
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.cjs',
  '.mjs',
  '.sh',
  '.bash',
  '.py',
  '.go',
  '.rs',
  '.astro',
  '.svelte',
  '.vue',
  '.md',
  '.mdx',
]);

/**
 * The comment form a mechanism uses to carry its BLOCKER reasons.
 *
 * This is a stable, self-contained fact about the FILE, which is exactly why it is the column
 * here and "who reads this mechanism" is not.
 *
 * NO `Readers` COLUMN, AND THE REASON IS MEASURED. The obvious column -- grep the tree for each
 * mechanism's basename and list the scripts that name it -- was built, and it flipped MID-RUN on
 * 2026-09-06: a peer session staged scripts/gates/check-package-key-budget.ts between one `--write`
 * and the next verify, and `git grep` (which searches TRACKED files) began returning it, so the
 * `package.json` row changed with no change to any suppression mechanism at all. A cell derived
 * from "who mentions this string anywhere" is volatile with respect to every unrelated edit in
 * the repository, and this record exists to be diffed across waves by a program that explicitly
 * warns the checkout is shared (08-driver-contract.md section 4). A column that churns on
 * unrelated work makes the diff unreadable and trains its reader to skip it.
 *
 * The reader mapping is genuinely useful and belongs in the phase that owns
 * docs/agent-reference/suppressions.md, where it can be pinned to a stable oracle -- the probe
 * table in scripts/gates/check-suppression-liveness.ts already pairs each mechanism with its reader by
 * declaration rather than by grep. This is a deliberate omission, not an oversight; do not add
 * the grep back.
 */
const commentForm = (rel: string, text: string): string => {
  const lines = text.split('\n');
  // ORDER IS THE WHOLE ALGORITHM, and it was wrong on the first pass. A naive "does any quoted string contain BLOCKER:" test classified `.runner-advice-allowlist` and `.ci/breakpoint/.breakpoint-drift-accept` as JSON, because both are shell-comment files whose HEADER PROSE quotes the format (`a "# BLOCKER: <reason>" comment block`). Real forms are therefore tested first, from most
  // specific anchor to least, and documentation-only mentions fall through to a state that says so instead of being guessed at.
  if (lines.some((l) => /^\s*#\s*BLOCKER:/.test(l))) return '# comment';
  if (lines.some((l) => /^\s*\/\/\s*BLOCKER:/.test(l))) return '// comment';
  if (/\.jsonc?$/.test(rel) && lines.some((l) => /"[^"]*BLOCKER:/.test(l))) return 'JSON value';
  if (lines.some((l) => /^\s*[^#/\s].*#\s*BLOCKER:/.test(l))) return 'inline';
  // Every BLOCKER: in the file is in its own documentation, so nothing is suppressed through one right now. An empty allowlist is a legitimate and desirable state -- `.breakpoint-drift-accept` says outright that empty is correct for this repo -- and reporting it as a comment style would hide that.
  return 'prose only (no live entry)';
};

export const suppressionsProvider: Provider = {
  id: 'suppressions',
  scans: 'every tracked non-source, non-prose file carrying a `BLOCKER:` line',
  columns: ['Mechanism', 'BLOCKER lines', 'Comment form'],
  rows: (root) => {
    const { present } = presentFiles(root, lsFiles(root, '.'));
    const rows: ProviderRow[] = [];
    for (const f of present) {
      // A FROZEN TEST CORPUS IS NOT A SUPPRESSION MECHANISM. Goldens under a tests directory are byte copies of real allow/block lists, recorded so a port can be proved to agree with the reader it replaces, and they carry BLOCKER: for the same reason the originals do. The predicate below is "carries BLOCKER: and is not source or prose", which cannot tell a recording from the thing
      // recorded: when W1 P3's allowlist goldens landed on 2026-09-06 this census went 24 rows to 39, and all 15 additions were copies of lists already counted once. A census that double-counts its own fixtures overstates the escape hatches in the tree, which is the one number this table exists to keep honest.
      if (/(^|\/)tests\/goldens\//.test(f)) continue;
      if (NOT_A_MECHANISM.has(path.extname(f))) continue;
      let text: string;
      try {
        text = fs.readFileSync(path.join(root, f), 'utf-8');
      } catch {
        continue;
      }
      // A NUL byte means binary; `BLOCKER:` inside one is a coincidence, not a convention.
      if (text.includes('\0')) continue;
      const n = text.split('\n').filter((l) => l.includes('BLOCKER:')).length;
      if (n === 0) continue;
      rows.push({ key: f, cells: [f, String(n), commentForm(f, text)] });
    }
    return rows.sort((a, b) => byCodePoint(a.key, b.key));
  },
  missing: (root) => presentFiles(root, lsFiles(root, '.')).missing,
};

/* ----------------------------------------------------------------- ci tree */

export const ciTreeProvider: Provider = {
  id: 'ci-tree',
  scans: 'every tracked path under .ci/, grouped by directory',
  columns: ['Directory', 'Files', 'Extensions'],
  rows: (root) => {
    const { present } = presentFiles(root, lsFiles(root, '.ci'));
    const byDir = new Map<string, string[]>();
    for (const f of present) {
      const dir = f.includes('/') ? f.slice(0, f.lastIndexOf('/')) : '.';
      const bucket = byDir.get(dir);
      if (bucket === undefined) byDir.set(dir, [f]);
      else bucket.push(f);
    }
    return [...byDir.entries()]
      .sort((a, b) => byCodePoint(a[0], b[0]))
      .map(([dir, files]) => {
        const hist = new Map<string, number>();
        for (const f of files) {
          const e = path.extname(f) || '(none)';
          hist.set(e, (hist.get(e) ?? 0) + 1);
        }
        const exts = [...hist.entries()]
          // Count descending, then extension ascending: a stable total order, so two runs on the same tree render the same string even when two extensions tie.
          .sort((a, b) => b[1] - a[1] || byCodePoint(a[0], b[0]))
          .map(([e, n]) => `${e} ${n}`)
          .join(', ');
        return { key: dir, cells: [dir, String(files.length), exts] };
      });
  },
  missing: (root) => presentFiles(root, lsFiles(root, '.ci')).missing,
};

/** Every provider, keyed by the id a marker region names. */
const TS_POLICY_SEAM = 'scripts/lib/policy-paths.ts';
/** Its Python twin. Both are parsed, neither is imported; see below. */
const PY_POLICY_SEAM = '.ci/rediacc_ci/policy_paths.py';

/**
 * `POLICY_DIR` out of the TypeScript seam.
 *
 * PARSED, NOT IMPORTED, and that is not laziness. `policy-paths.ts` exports only
 * `policyPath` and `isPolicyFileName`: its own comment records that the name
 * list and the directory are deliberately NOT exported, because `lint:unused`
 * refuses an export nothing imports, and reaching them is what its `--list` /
 * `--dir` CLI is for. Shelling out to that CLI once per region would be the
 * other honest option; a regex over the constant is cheaper and keeps this
 * provider a pure read, which is what every other provider here is.
 */
const tsPolicyDir = (root: string): string => {
  const text = fs.readFileSync(path.join(root, TS_POLICY_SEAM), 'utf-8');
  return /const\s+POLICY_DIR\s*=\s*'([^']*)'/.exec(text)?.[1] ?? '';
};

const tsPolicyNames = (root: string): string[] => {
  const text = fs.readFileSync(path.join(root, TS_POLICY_SEAM), 'utf-8');
  // TERMINATED ON A LINE-ANCHORED `]`, not on the first one. Entries here are
  // annotated, and an annotation is free to contain a bracket; a non-greedy
  // `[\s\S]*?\]` stops at the first of those and silently returns a PREFIX of the
  // list. The Python twin below had exactly that defect on its first pass: its
  // tuple's comments say `policy_path()`, the scan ended at that `)`, and two
  // names came back missing from a seam that holds them.
  const block =
    /const\s+POLICY_FILES\s*=\s*Object\.freeze\(\[\n([\s\S]*?)\n\]/.exec(text)?.[1] ?? '';
  const out: string[] = [];
  for (const line of block.split('\n')) {
    // COMMENT LINES ARE SKIPPED FIRST. The array is annotated per entry, and
    // several of those comments quote a filename; a bare quote scan would read
    // the annotations back as members and report names that are not in the list.
    if (line.trim().startsWith('//')) continue;
    for (const m of line.matchAll(/'([^']+)'/g)) out.push(m[1] as string);
  }
  return out.sort(byCodePoint);
};

const pyPolicyNames = (root: string): string[] => {
  const text = fs.readFileSync(path.join(root, PY_POLICY_SEAM), 'utf-8');
  const block = /POLICY_FILES[^=\n]*=\s*\(\n([\s\S]*?)\n\)/.exec(text)?.[1] ?? '';
  const out: string[] = [];
  for (const line of block.split('\n')) {
    if (line.trim().startsWith('#')) continue;
    for (const m of line.matchAll(/"([^"]+)"/g)) out.push(m[1] as string);
  }
  return out.sort(byCodePoint);
};

/**
 * The directory's own README, which is prose about the mechanism rather than a
 * mechanism. Named here so the exemption is visible in the code and in the
 * region's own row count, rather than being a silent `filter`.
 */
const POLICY_README = 'README.md';

/** Non-blank, non-comment lines: what every name-per-line reader counts as an entry. */
const countEntries = (text: string): number =>
  text.split('\n').filter((l) => l.trim() !== '' && !l.trim().startsWith('#')).length;

export const policyProvider: Provider = {
  id: 'policy',
  scans:
    'every tracked file in the policy directory, against `POLICY_FILES` in both seams ' +
    '(`scripts/lib/policy-paths.ts`, `.ci/rediacc_ci/policy_paths.py`)',
  columns: ['File', 'Shape', 'Entries', 'BLOCKER lines', 'In POLICY_FILES'],
  rows: (root) => {
    const dir = tsPolicyDir(root);
    const ts = new Set(tsPolicyNames(root));
    const py = new Set(pyPolicyNames(root));
    const { present } = presentFiles(root, lsFiles(root, dir));
    const onDisk = new Set(
      present
        .map((f) => (f.startsWith(`${dir}/`) ? f.slice(dir.length + 1) : f))
        .filter((n) => n !== POLICY_README && !n.includes('/'))
    );

    // THE UNION, NOT THE DIRECTORY. A name in POLICY_FILES with no file behind it
    // is the failure this directory's README opens with: every one of these
    // mechanisms reads a missing file as ZERO entries, which is indistinguishable
    // from "nothing is suppressed". Rendering only what is on disk would make the
    // dangerous direction invisible in the very table that documents the set.
    const names = [...new Set([...onDisk, ...ts, ...py])].sort(byCodePoint);
    return names.map((name) => {
      const seams =
        ts.has(name) && py.has(name)
          ? 'both'
          : ts.has(name)
            ? 'ts only'
            : py.has(name)
              ? 'py only'
              : 'NEITHER';
      if (!onDisk.has(name)) {
        return { key: name, cells: [`\`${name}\``, 'NO FILE ON DISK', '-', '-', seams] };
      }
      let text = '';
      try {
        text = fs.readFileSync(path.join(root, dir, name), 'utf-8');
      } catch {
        return { key: name, cells: [`\`${name}\``, 'unreadable', '-', '-', seams] };
      }
      const blockers = text.split('\n').filter((l) => l.includes('BLOCKER:')).length;
      // A `.json` policy file holds a table, not one name per line, so the line-counting entry rule would report its punctuation. Reported as `-` rather than as a wrong number: `.ci/policy/README.md` section 5 explains why the two JSON members are shaped differently from their neighbours.
      const json = name.endsWith('.json');
      return {
        key: name,
        cells: [
          `\`${name}\``,
          json ? 'JSON table' : 'name per line',
          json ? '-' : String(countEntries(text)),
          String(blockers),
          seams,
        ],
      };
    });
  },
  missing: (root) => presentFiles(root, lsFiles(root, tsPolicyDir(root))).missing,
};

/* ------------------------------------------------------------ test-split */

/** Where the orphan gate looks for test files. Parsed, so the two cannot drift. */
const ORPHAN_GATE = '.ci/scripts/quality/check_test_file_orphans.py';
/** Where pytest collects from. `testpaths` is the ini key, in the root pyproject. */
const PYPROJECT = 'pyproject.toml';

/** `test-<x>.sh` / `test_<x>.py`: the orphan gate's own NAME_RE, in its own spelling. */
const TEST_NAME_RE = /^test[-_].*\.(py|sh|ts)$/;

const searchDirs = (root: string): string[] => {
  const text = fs.readFileSync(path.join(root, ORPHAN_GATE), 'utf-8');
  const block = /SEARCH_DIRS\s*=\s*\(\n([\s\S]*?)\n\)/.exec(text)?.[1] ?? '';
  return [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1] as string);
};

const pytestRoots = (root: string): string[] => {
  const text = fs.readFileSync(path.join(root, PYPROJECT), 'utf-8');
  const block = /testpaths\s*=\s*\[([^\]]*)\]/.exec(text)?.[1] ?? '';
  return [...block.matchAll(/"([^"]+)"/g)].map((m) => (m[1] as string).replace(/\/$/, ''));
};

/**
 * Every string anywhere in the gates lock, flattened.
 *
 * A LEAF IS THE REGISTRATION, but leaves are not the only place a path appears
 * (a `paths:` selector names files too), and for THIS table the distinction does
 * not matter: the question is "does the registry know this file exists", and any
 * mention answers it. Flattening rather than reaching into `leaves` also survives
 * the lock growing a field, which it has done twice.
 */
const lockStrings = (root: string): Set<string> => {
  const out = new Set<string>();
  const walk = (node: unknown): void => {
    if (typeof node === 'string') out.add(node);
    else if (Array.isArray(node)) for (const v of node) walk(v);
    else if (node !== null && typeof node === 'object')
      for (const v of Object.values(node)) walk(v);
  };
  walk(JSON.parse(fs.readFileSync(path.join(root, GATES_LOCK), 'utf-8')));
  return out;
};

export const testSplitProvider: Provider = {
  id: 'test-split',
  scans:
    'every tracked `test-*` / `test_*` file under the roots named by ' +
    '`.ci/scripts/quality/check_test_file_orphans.py` and `pyproject.toml`',
  columns: ['Root or file', 'Declared by', 'Test files', 'Registry', 'pytest'],
  rows: (root) => {
    const dirs = searchDirs(root);
    const pyroots = pytestRoots(root);
    const declared = [...new Set([...dirs, ...pyroots])].sort(byCodePoint);
    const lock = lockStrings(root);
    const known = (rel: string, base: string): boolean => {
      for (const s of lock) if (s === rel || s.includes(rel) || s.includes(base)) return true;
      return false;
    };

    const rows: ProviderRow[] = [];
    // THE RESIDUE IS ONE ROW PER FILE, NOT A COUNT, and that is the whole reason this provider was worth writing. A count cannot see one file leaving as another arrives -- the composition trap this program has already been bitten by once, in a baseline drain that printed a smaller total while quietly absorbing a brand-new finding. Keyed rows make a set diff possible.
    const residue: string[] = [];

    // NEAREST DECLARED ROOT WINS, because two of these roots NEST. `testpaths` names `.ci/rediacc_ci/tests` and `.ci/rediacc_ci/tests/gates` separately, and `git ls-files` on the parent returns the child's files too: the first render of this table reported 169 and 78 against a real population of 169, counting 78 files twice and inflating the split by 46%. A file is attributed to
    // the LONGEST declared root that contains it, so every row is disjoint and the column sums to the tree.
    const owner = (rel: string): string =>
      declared.filter((d) => rel.startsWith(`${d}/`)).sort((a, b) => b.length - a.length)[0] ?? '';

    for (const dir of declared) {
      const { present } = presentFiles(root, lsFiles(root, dir));
      const tests = present.filter((f) => TEST_NAME_RE.test(path.basename(f)) && owner(f) === dir);
      let inLock = 0;
      let inPytest = 0;
      for (const f of tests) {
        if (known(f, path.basename(f))) inLock += 1;
        else if (pyroots.some((r) => f.startsWith(`${r}/`))) inPytest += 1;
        else residue.push(f);
      }
      const declaredBy =
        dirs.includes(dir) && pyroots.includes(dir)
          ? 'orphan gate + pytest'
          : dirs.includes(dir)
            ? 'orphan gate'
            : 'pytest testpaths';
      rows.push({
        key: dir,
        cells: [`\`${dir}\``, declaredBy, String(tests.length), String(inLock), String(inPytest)],
      });
    }

    // A root that is DECLARED and EMPTY is rendered above with a 0, deliberately: `.ci/tests/gates` was arbitrated into existence by docs/ci-overhaul/08-driver-contract.md and holds nothing, and a table that dropped empty rows would report that as agreement.
    for (const f of residue.sort(byCodePoint)) {
      rows.push({
        key: `(unregistered) ${f}`,
        cells: [`(unregistered) \`${f}\``, '-', '1', '0', '0'],
      });
    }
    return rows;
  },
  missing: (root) =>
    [...new Set([...searchDirs(root), ...pytestRoots(root)])]
      .sort(byCodePoint)
      .flatMap((d) => presentFiles(root, lsFiles(root, d)).missing),
};

/* ------------------------------------------------------- entry points (W11 P5a) */

/**
 * A seam this file READS, with a refusal that names it.
 *
 * `fs.readFileSync` throwing ENOENT names the absolute path and nothing else, which reads as
 * a broken generator rather than as a missing seam. Every provider below goes through this,
 * so a moved file produces one sentence that says which document stops being derivable.
 */
const readSeam = (root: string, rel: string): string => {
  try {
    return fs.readFileSync(path.join(root, rel), 'utf-8');
  } catch {
    throw new Error(
      `${rel} is missing, so this provider cannot see the seam it documents. Rendering the ` +
        'region without it would report an empty subject when the instrument is what broke.'
    );
  }
};

const ROUTER_SEAM = 'run.sh';
const LEGACY_SEAM = '.ci/legacy/run-legacy.sh';
const BOOTSTRAP_SEAM = '.ci/bootstrap.sh';
const TOOLCHAIN_SEAM = '.devcontainer/toolchain.env';

/**
 * Top-level verbs served by a dispatcher's `main()`, by case-nesting DEPTH.
 *
 * DEPTH, NEVER INDENTATION, and that is not a preference. This is the algorithm
 * .ci/scripts/test/gates/test-run-sh.sh:180-206 already runs in awk, ported rather than
 * reinvented, because its comment records what an indentation rule does here: the legacy
 * dispatcher's docker-group route contains an INNER `case` whose arms sit at the same indent
 * as a real subcommand, so an indentation rule reports its numeric arms as verbs. The same
 * file is the reason `*`, `""`, a leading `-` and a bare number are dropped: they are the
 * fallback, the bare-verb default, a flag alias and an inner arm respectively.
 */
export function topVerbs(source: string): string[] {
  const lines = source.split('\n');
  const out = new Set<string>();
  let inMain = false;
  let depth = 0;
  for (const raw of lines) {
    if (!inMain) {
      if (/^main\(\) \{/.test(raw)) inMain = true;
      continue;
    }
    if (/^\}/.test(raw)) break;
    const line = raw.replace(/^[ \t]+/, '');
    if (line.startsWith('#')) continue;
    if (/^esac/.test(line)) {
      depth -= 1;
      continue;
    }
    if (/(^|[ \t;])case[ \t].*[ \t]in([ \t]|$)/.test(line)) {
      depth += 1;
      continue;
    }
    if (depth < 1) continue;
    if (!/^[a-zA-Z0-9_"*-][a-zA-Z0-9_"*|. -]*\)/.test(line)) continue;
    if (depth !== 1) continue;
    for (const part of line.replace(/\).*$/, '').split('|')) {
      const v = part.trim().replace(/"/g, '');
      if (v === '' || v === '*' || v.startsWith('-') || /^[0-9]+$/.test(v)) continue;
      out.add(v);
    }
  }
  if (!inMain) {
    throw new Error(
      'no `main() {` in the dispatcher this provider reads. The verb table is derived from ' +
        'that block, so a parse that misses it would render an EMPTY router as a fact.'
    );
  }
  return [...out].sort(byCodePoint);
}

/**
 * The `PORTED_VERBS` table, which is EMPTY today and is expected to be.
 *
 * Empty is a statement rather than a fault (run.sh:37-39 says so), so this must not refuse on
 * zero: a floor here would go red on the day the port finishes moving the last verb back out,
 * and it would have been red for the whole programme before the first one moved. The number
 * is exactly why the region exists -- it is the port's progress bar, and prose would carry a
 * stale count of it within a week.
 */
export function portedVerbs(source: string): string[] {
  const m = /^PORTED_VERBS=\(([\s\S]*?)\)\s*$/m.exec(source);
  if (m === null) {
    throw new Error(
      `${ROUTER_SEAM} has no PORTED_VERBS=( ... ) table. That table is the router's whole ` +
        'seam between bash and Python; not finding it means this scan is reading the wrong file.'
    );
  }
  const out: string[] = [];
  for (const line of (m[1] ?? '').split('\n')) {
    const body = line.replace(/#.*$/, '').trim();
    for (const tok of body.split(/\s+/)) {
      const v = tok.replace(/["']/g, '').trim();
      if (v !== '') out.push(v);
    }
  }
  return out.sort(byCodePoint);
}

/** `NAME=value` pairs from a shell env file, comments and blanks dropped. */
export function envPins(source: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const line of source.split('\n')) {
    const m = /^([A-Z][A-Z0-9_]*)=(.*)$/.exec(line.trim());
    if (m !== null) out.set(m[1] as string, (m[2] ?? '').replace(/["']/g, ''));
  }
  return out;
}

/**
 * The pinned tools `.ci/bootstrap.sh` provisions: the INTERSECTION of the `*_VERSION` names it
 * dereferences and the names `toolchain.env` defines.
 *
 * The intersection is the point. A `*_VERSION` in bootstrap.sh with no pin behind it expands
 * to nothing under `set -u`... except this file runs `set -uo pipefail` without `-e`, so the
 * failure is a download of an unpinned version rather than an abort. Naming only the pairs
 * that exist in BOTH keeps the table honest about what is actually pinned; the mismatch in
 * either direction shows up as a row that is missing, which is what a set diff is for.
 */
export function bootstrapPins(bootstrap: string, toolchain: string): [string, string][] {
  const pins = envPins(toolchain);
  const used = new Set(
    [...bootstrap.matchAll(/\$\{?([A-Z][A-Z0-9_]*_VERSION)\b/g)].map((m) => m[1] as string)
  );
  const out: [string, string][] = [];
  for (const name of [...used].sort(byCodePoint)) {
    const v = pins.get(name);
    if (v !== undefined) out.push([name, v]);
  }
  return out;
}

export const bootstrapProvider: Provider = {
  id: 'bootstrap',
  scans:
    '`run.sh`, its `PORTED_VERBS` table, the legacy dispatcher and the pins ' +
    '`.ci/bootstrap.sh` installs, folded to one row per entry point',
  columns: ['Entry point', 'Serves', 'Count', 'Names'],
  rows: (root) => {
    const router = readSeam(root, ROUTER_SEAM);
    const legacy = readSeam(root, LEGACY_SEAM);
    const pins = bootstrapPins(readSeam(root, BOOTSTRAP_SEAM), readSeam(root, TOOLCHAIN_SEAM));
    const routerArms = topVerbs(router);
    const ported = portedVerbs(router);
    const legacyArms = topVerbs(legacy).filter((v) => v !== 'help');

    // ONE ROW PER ENTRY POINT, with the members spelled out in the last cell rather than counted. A count alone cannot see one verb leaving as another arrives, which is the exact shape a port produces: `--changed` selection and the router's own gate test both key on the SET, so the document has to as well.
    const rows: ProviderRow[] = [
      {
        key: 'run.sh',
        cells: [
          `\`./${ROUTER_SEAM}\``,
          'router arms (bash, in the router itself)',
          String(routerArms.length),
          routerArms.length === 0 ? '(none)' : routerArms.map((v) => `\`${v}\``).join(', '),
        ],
      },
      {
        key: 'rediacc_ci',
        cells: [
          '`python3 -m rediacc_ci`',
          'verbs listed in `PORTED_VERBS`',
          String(ported.length),
          ported.length === 0 ? '(none yet)' : ported.map((v) => `\`${v}\``).join(', '),
        ],
      },
      {
        key: 'legacy',
        cells: [
          `\`${LEGACY_SEAM}\``,
          'every verb the router does not serve itself',
          String(legacyArms.length),
          legacyArms.length === 0 ? '(none)' : legacyArms.map((v) => `\`${v}\``).join(', '),
        ],
      },
      {
        key: 'bootstrap',
        cells: [
          `\`${BOOTSTRAP_SEAM}\``,
          `pinned tools, from \`${TOOLCHAIN_SEAM}\``,
          String(pins.length),
          pins.map(([k, v]) => `\`${k}=${v}\``).join(', '),
        ],
      },
    ];

    // THE UNION, NOT EACH ROW. Zero ported verbs is the tree's real state; zero verbs
    // ANYWHERE means the two dispatchers were both misparsed, and rendering that would publish "this repository has no entry points".
    if (routerArms.length + ported.length + legacyArms.length === 0) {
      throw new Error(
        `${ROUTER_SEAM} and ${LEGACY_SEAM} between them yielded no verbs. One dispatcher can ` +
          'legitimately be empty during the port; both cannot.'
      );
    }
    if (pins.length === 0) {
      throw new Error(
        `${BOOTSTRAP_SEAM} dereferences no *_VERSION that ${TOOLCHAIN_SEAM} defines. Either ` +
          'the pins moved or this scan is reading the wrong file; both make the row a lie.'
      );
    }
    return rows;
  },
};

/* ------------------------------------------------------------ the job graph */

const WORKFLOW_DIR = '.github/workflows';

export interface WorkflowJob {
  id: string;
  needs: string[];
  /** The reusable workflow this job calls, repo-relative, or '' for a normal job. */
  uses: string;
}

export interface WorkflowFile {
  /** Repo-relative path. */
  file: string;
  /** `on:` keys, in file order. */
  triggers: string[];
  jobs: WorkflowJob[];
}

/**
 * One workflow, read with line regexes rather than a YAML parser.
 *
 * NO YAML DEPENDENCY, DELIBERATELY. `yaml` and `js-yaml` are both in the tree only as
 * TRANSITIVE dependencies of astro, so importing one here would add a root dependency that
 * knip would then require a BLOCKER for, to read four keys. Every other workflow reader in
 * scripts/ (check-secret-scope.ts, check-actions.ts) is a line scan for the same reason, and
 * the shape being read here -- two-space job keys, `needs:` and `uses:` -- is the shape
 * actionlint already keeps well-formed in CI.
 */
export function parseWorkflow(file: string, text: string): WorkflowFile {
  const lines = text.split('\n');
  const jobs: WorkflowJob[] = [];
  const triggers: string[] = [];
  let section = '';
  let cur: WorkflowJob | null = null;
  let needsBlock = false;

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (line === '' || /^\s*#/.test(line)) continue;
    const top = /^([A-Za-z_][A-Za-z0-9_-]*):/.exec(line);
    if (top !== null) {
      section = top[1] as string;
      cur = null;
      needsBlock = false;
      continue;
    }
    const two = /^ {2}([A-Za-z_][A-Za-z0-9_-]*):(.*)$/.exec(line);
    if (two !== null) {
      const key = two[1] as string;
      if (section === 'on') triggers.push(key);
      if (section === 'jobs') {
        cur = { id: key, needs: [], uses: '' };
        jobs.push(cur);
      }
      needsBlock = false;
      continue;
    }
    if (cur === null) continue;
    const needsInline = /^ {4}needs:\s*(.*)$/.exec(line);
    if (needsInline !== null) {
      const v = (needsInline[1] ?? '').trim();
      needsBlock = v === '';
      for (const n of v.replace(/^\[|\]$/g, '').split(',')) {
        const id = n.trim().replace(/["']/g, '');
        if (id !== '') cur.needs.push(id);
      }
      continue;
    }
    if (needsBlock) {
      const item = /^ {6}-\s*(\S+)\s*$/.exec(line);
      if (item !== null) {
        cur.needs.push((item[1] ?? '').replace(/["']/g, ''));
        continue;
      }
      needsBlock = false;
    }
    const uses = /^ {4}uses:\s*\.\/(\.github\/workflows\/\S+)\s*$/.exec(line);
    if (uses !== null) cur.uses = uses[1] as string;
  }
  return { file, triggers, jobs };
}

/**
 * Topological LEVEL per job: 0 for a job with no `needs`, otherwise one past its deepest
 * dependency. This is what turns a `needs:` table back into the arrow chain a reader wants.
 *
 * A CYCLE IS A REFUSAL. GitHub rejects the workflow at startup, so a cycle here is a real
 * defect in the tree and not a shape this table has an opinion about; rendering the jobs at
 * some arbitrary level would document a pipeline that cannot run. Same for a `needs:` naming
 * a job that does not exist, which is the more common typo and the one GitHub reports as a
 * bare startup failure with no job and no log.
 */
export function jobLevels(wf: WorkflowFile): Map<string, number> {
  const byId = new Map(wf.jobs.map((j) => [j.id, j]));
  const level = new Map<string, number>();
  const visiting = new Set<string>();
  const walk = (id: string): number => {
    const cached = level.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) {
      throw new Error(`${wf.file}: job "${id}" is part of a \`needs:\` cycle`);
    }
    visiting.add(id);
    const job = byId.get(id) as WorkflowJob;
    let n = 0;
    for (const dep of job.needs) {
      if (!byId.has(dep)) {
        throw new Error(
          `${wf.file}: job "${id}" needs "${dep}", which is not a job in that workflow. ` +
            'GitHub fails such a run at startup with no job and no log.'
        );
      }
      n = Math.max(n, walk(dep) + 1);
    }
    visiting.delete(id);
    level.set(id, n);
    return n;
  };
  for (const j of wf.jobs) walk(j.id);
  return level;
}

export const jobGraphProvider: Provider = {
  id: 'job-graph',
  scans:
    'every `.github/workflows/*.yml` that calls a reusable workflow, folded to one row per ' +
    'topological stage of its `needs:` graph',
  columns: ['Workflow', 'Stage', 'Jobs', 'Calls'],
  rows: (root) => {
    const files = lsFiles(root, `${WORKFLOW_DIR}/*.yml`, `${WORKFLOW_DIR}/*.yaml`);
    const { present } = presentFiles(root, files);
    if (present.length === 0) {
      throw new Error(
        `no workflow files under ${WORKFLOW_DIR}. A pipeline table rendered from nothing ` +
          'would say this repository has no CI.'
      );
    }
    const parsed = present.map((f) => parseWorkflow(f, readSeam(root, f)));

    // THE CHAIN IS DERIVED, NOT LISTED. A hand-written "these are the pipeline workflows"
    // array is the artifact this generator exists to abolish, so the rule is structural: a
    // workflow is in the chain when it is an ENTRY (it is not `workflow_call`-only) and it
    // delegates to at least one reusable workflow. That is what makes ci.yml and cd-v2.yml
    // the lanes a reader has to know about, and it re-derives itself when one is added.
    const chain = parsed.filter(
      (w) => !w.triggers.includes('workflow_call') && w.jobs.some((j) => j.uses !== '')
    );
    if (chain.length === 0) {
      throw new Error(
        'no workflow both is an entry point and calls a reusable workflow, so the chain ' +
          'came back empty. The pipeline has that shape today, so an empty answer is a ' +
          'parse failure rather than a fact about the tree.'
      );
    }

    const rows: ProviderRow[] = [];
    for (const wf of chain.sort((a, b) => byCodePoint(a.file, b.file))) {
      const level = jobLevels(wf);
      const stages = Math.max(...[...level.values()]) + 1;
      for (let s = 0; s < stages; s++) {
        const at = wf.jobs.filter((j) => level.get(j.id) === s);
        const calls = [
          ...new Set(at.filter((j) => j.uses !== '').map((j) => path.basename(j.uses))),
        ].sort(byCodePoint);
        rows.push({
          key: `${wf.file}#${s}`,
          cells: [
            `\`${path.basename(wf.file)}\``,
            String(s),
            at
              .map((j) => j.id)
              .sort(byCodePoint)
              .map((id) => `\`${id}\``)
              .join(', '),
            calls.length === 0 ? '-' : calls.map((c) => `\`${c}\``).join(', '),
          ],
        });
      }
    }
    return rows;
  },
  missing: (root) =>
    presentFiles(root, lsFiles(root, `${WORKFLOW_DIR}/*.yml`, `${WORKFLOW_DIR}/*.yaml`)).missing,
};

/* ---------------------------------------------------------------- the media */

const MEDIA_PUSH_SEAM = '.ci/scripts/deploy/sync-media-to-r2.sh';
const MEDIA_PULL_SEAM = '.ci/scripts/deploy/sync-media-from-r2.sh';
const WWW_GITIGNORE = 'packages/www/.gitignore';
const WWW_PREFIX = 'packages/www/';

/** `<local>` -> `<r2 prefix>` pairs, from whichever argument order the script uses. */
export function mediaPairs(source: string, localFirst: boolean): Map<string, string> {
  const out = new Map<string, string>();
  const re = /^\s*(?:sync_dir|restore_dir)\s+"([^"]+)"\s+"([^"]+)"/gm;
  for (const m of source.matchAll(re)) {
    const a = (m[1] ?? '').replace('$REPO_ROOT/', '');
    const b = (m[2] ?? '').replace('$REPO_ROOT/', '');
    const local = localFirst ? a : b;
    const prefix = localFirst ? b : a;
    out.set(local.replace(/\/$/, ''), prefix.replace(/\/$/, ''));
  }
  return out;
}

/** Directory patterns `packages/www/.gitignore` excludes, as repo-relative paths. */
export function ignoredMediaDirs(source: string): string[] {
  const out: string[] = [];
  for (const line of source.split('\n')) {
    const v = line.trim();
    if (v === '' || v.startsWith('#') || v.startsWith('!') || v.includes('*')) continue;
    if (!v.endsWith('/')) continue;
    out.push(`${WWW_PREFIX}${v.replace(/\/$/, '')}`);
  }
  return out.sort(byCodePoint);
}

export const mediaProvider: Provider = {
  id: 'media',
  scans:
    'the two R2 sync scripts and `packages/www/.gitignore`, one row per media directory in ' +
    'their union',
  columns: ['Local path', 'R2 prefix', 'Push', 'Restore', 'Tracked files'],
  rows: (root) => {
    const push = mediaPairs(readSeam(root, MEDIA_PUSH_SEAM), true);
    const pull = mediaPairs(readSeam(root, MEDIA_PULL_SEAM), false);
    if (push.size === 0 || pull.size === 0) {
      throw new Error(
        `${MEDIA_PUSH_SEAM} yielded ${push.size} pair(s) and ${MEDIA_PULL_SEAM} yielded ` +
          `${pull.size}. Neither script can legitimately sync nothing, so this is the scan ` +
          'failing rather than the pipeline having been retired.'
      );
    }
    const ignored = ignoredMediaDirs(readSeam(root, WWW_GITIGNORE));
    if (ignored.length === 0) {
      throw new Error(
        `${WWW_GITIGNORE} excludes no directory. The media directories are gitignored by ` +
          'design, so an empty answer means the scan missed them.'
      );
    }

    // THE UNION OF THREE SEAMS, because the interesting rows are the ones a single seam
    // cannot show. `packages/www/public/media/` is gitignored and mirrored by NEITHER
    // script: 138 files of narration audio, captions, photos and posters that were
    // untracked with the rest in #512 and never went to R2. Rendering only what the sync
    // scripts name would make that the one directory the table cannot see, which is the
    // same as not documenting it at all.
    const keys = [...new Set([...push.keys(), ...pull.keys(), ...ignored])].sort(byCodePoint);

    // A DIRECTORY INSIDE A SYNCED ONE IS SYNCED, and saying otherwise is the false alarm
    // this table would otherwise open with: `.gitignore` excludes
    // `public/assets/videos/solutions/` while the sync scripts name its PARENT
    // `public/assets/videos/`, so a per-key lookup reports the busiest media directory in
    // the repository as mirrored nowhere. Four false rows are how a reader learns to skip a
    // generated table, and the one row that matters here -- a directory with no ancestor in
    // either script -- is then indistinguishable from the noise.
    const ancestor = (local: string, m: Map<string, string>): string =>
      [...m.keys()]
        .filter((k) => local.startsWith(`${k}/`))
        .sort((a, b) => b.length - a.length)[0] ?? '';

    return keys.map((local) => {
      const pushedBy = push.has(local) ? local : ancestor(local, push);
      const pulledBy = pull.has(local) ? local : ancestor(local, pull);
      const via = (own: boolean, by: string): string =>
        own ? 'yes' : by === '' ? 'no' : `via \`${by.slice(WWW_PREFIX.length)}/\``;
      const prefix =
        push.get(local) ??
        pull.get(local) ??
        (pushedBy === '' ? '' : `${push.get(pushedBy) ?? ''}/${local.slice(pushedBy.length + 1)}`);
      return {
        key: local,
        cells: [
          `\`${local}/\``,
          prefix === '' ? '(mirrored nowhere)' : `\`${prefix}/\``,
          via(push.has(local), pushedBy),
          via(pull.has(local), pulledBy),
          String(lsFiles(root, local).length),
        ],
      };
    });
  },
};

/* -------------------------------------------------- the plan-record grammar */

const PLANREC_SEAM = '.claude/hooks/stop/wl_planrec.py';

/** The body of a top-level `def <name>(` in a Python module, without its signature line. */
export function pyFunctionBody(source: string, name: string): string {
  const start = source.indexOf(`\ndef ${name}(`);
  if (start === -1) {
    throw new Error(
      `${PLANREC_SEAM} has no top-level \`def ${name}(\`. The record grammar is READ OUT of ` +
        'that function, so a rename has to re-point this provider rather than silently ' +
        'render a shorter grammar.'
    );
  }
  const after = source.indexOf('\ndef ', start + 1);
  return source.slice(start, after === -1 ? source.length : after);
}

/** A module-level `NAME = <value>` assignment, verbatim on the right-hand side. */
export function pyConst(source: string, name: string): string {
  const m = new RegExp(`^${name} = (.+)$`, 'm').exec(source);
  if (m === null) {
    throw new Error(
      `${PLANREC_SEAM} no longer defines ${name}. It is part of the record grammar this ` +
        'region publishes; a missing one means the document would understate the rules.'
    );
  }
  return (m[1] ?? '').trim();
}

/** `int(os.environ.get("VAR", "default"))` -> `default (env VAR)`, or the expression as-is. */
const pyBound = (rhs: string): string => {
  const m = /os\.environ\.get\(\s*"([^"]+)"\s*,\s*(.+?)\s*\)\s*\)?\s*$/.exec(rhs);
  if (m === null) return `\`${rhs}\``;
  const dflt = (m[2] ?? '').replace(/^str\((.*)\)$/, '$1').replace(/"/g, '');
  return `\`${dflt}\`, override \`${m[1]}\``;
};

export const planRecordGrammarProvider: Provider = {
  id: 'plan-record-grammar',
  scans: `the record grammar in ${PLANREC_SEAM}: its bounds, header fields, sections, trailer keys and annotation lines`,
  columns: ['Element', 'Kind', 'Rule', 'Read from'],
  rows: (root) => {
    const src = readSeam(root, PLANREC_SEAM);
    const render = pyFunctionBody(src, 'render');
    const trailer = [
      ...(/for k in \(\n([\s\S]*?)\n\s*\):/.exec(render)?.[1] ?? '').matchAll(/"([^"]+)"/g),
    ].map((m) => m[1] as string);
    if (trailer.length === 0) {
      throw new Error(`${PLANREC_SEAM}: the \`## Record\` trailer key tuple parsed to nothing`);
    }
    const rows: ProviderRow[] = [];
    const add = (group: string, name: string, kind: string, rule: string, from: string): void => {
      rows.push({ key: `${group}:${name}`, cells: [`\`${name}\``, kind, rule, `\`${from}\``] });
    };

    // 1. THE BOUNDS. Each is an env-overridable default, so the row prints BOTH: a reader
    // who sees a record over budget needs to know which variable moved it, and the
    // variable name is the half a prose copy always drops.
    const states = [...pyConst(src, 'RECORD_STATES').matchAll(/STATUS_([A-Z]+)/g)].map((m) =>
      (m[1] as string).toLowerCase()
    );
    if (states.length === 0) {
      throw new Error(`${PLANREC_SEAM}: RECORD_STATES parsed to no states`);
    }
    add(
      'bound',
      'Status values',
      'bound',
      states.map((s) => `\`${s}\``).join(' or '),
      'RECORD_STATES'
    );
    add(
      'bound',
      'header window',
      'bound',
      `first \`${pyConst(src, 'HEADER_LINES')}\` lines`,
      'HEADER_LINES'
    );
    add(
      'bound',
      'record size',
      'bound',
      pyBound(pyConst(src, 'RECORD_MAX_BYTES')),
      'RECORD_MAX_BYTES'
    );
    add(
      'bound',
      'per box',
      'bound',
      pyBound(pyConst(src, 'RECORD_PER_BOX_BYTES')),
      'RECORD_PER_BOX_BYTES'
    );
    add('bound', 'blob ratio', 'bound', pyBound(pyConst(src, 'BLOB_RATIO')), 'BLOB_RATIO');

    // 2. THE HEADER, IN RENDER ORDER AND AS A UNION with the keys the parser accepts.
    //
    // ORDER IS THE GRAMMAR HERE, so these rows are NOT sorted: `render()` states that the
    // header block must land inside the first HEADER_LINES lines or `wl_checks.plan_records`
    // cannot see the Status line, and a record whose header is out of order reads as an
    // ordinary plan with an unparseable header -- worse than not compacting it, because it
    // stays on the housekeeping clock while LOOKING like a record. Alphabetising the rows
    // would delete exactly the property the reader came for.
    //
    // And the union is the two-direction equality: a key `render()` writes that the parser
    // does not accept, or a key the parser accepts that nothing writes, are different
    // defects and both are invisible in a table that shows only one side.
    const emitted: { key: string; conditional: boolean }[] = [];
    for (const line of render.split('\n')) {
      const m = /lines\.append\("([A-Za-z][A-Za-z-]*): /.exec(line);
      if (m !== null) emitted.push({ key: m[1] as string, conditional: false });
      const inList = /^\s*lines = \["# %s".*"([A-Za-z][A-Za-z-]*): %s"/.exec(line);
      if (inList !== null) emitted.push({ key: inList[1] as string, conditional: false });
    }
    // A field appended under an `if rec.get(...)` is OPTIONAL, and which ones are optional is
    // the question a hand-written copy of this grammar gets wrong first.
    const optional = new Set(
      [
        ...render.matchAll(
          /if rec\.get\("([a-z_]+)"\)[\s\S]{0,200}?lines\.append\("([A-Za-z-]+): /g
        ),
      ].map((m) => m[2] as string)
    );
    const parserKeys = [
      ...(/HEADER_FIELD_KEYS = frozenset\(\n\s*\{([\s\S]*?)\n\s*\}/.exec(src)?.[1] ?? '').matchAll(
        /"([^"]+)"/g
      ),
    ].map((m) => m[1] as string);
    if (parserKeys.length === 0) {
      throw new Error(`${PLANREC_SEAM}: HEADER_FIELD_KEYS parsed to no keys`);
    }
    const seen = new Set<string>();
    for (const f of emitted) {
      if (seen.has(f.key)) continue;
      seen.add(f.key);
      add(
        'header',
        f.key,
        'header field',
        `${optional.has(f.key) ? 'optional' : 'always'}, ${
          parserKeys.includes(f.key) ? 'in HEADER_FIELD_KEYS' : 'NOT in HEADER_FIELD_KEYS'
        }`,
        'render()'
      );
    }
    for (const k of parserKeys.slice().sort(byCodePoint)) {
      if (seen.has(k)) continue;
      // TRAILER-AWARE, because "never written" was wrong about two of these. `Compacted-By`
      // and `Compacted-At` ARE written by `render()`, in the `## Record` trailer rather than
      // in the header block, and a row saying otherwise sends a reader looking for a bug in
      // the renderer. The parser accepting them in the header is a real second position.
      add(
        'header',
        k,
        'header field',
        trailer.includes(k)
          ? 'accepted in the header block; `render()` writes it in the `## Record` trailer'
          : 'accepted when parsing, never written by `render()`',
        'HEADER_FIELD_KEYS'
      );
    }

    // 3. THE SECTIONS, again in render order, distinguishing the ones an author fills from
    // the ones the renderer generates. `## Boxes` is generated, and a session that hand-edits
    // it is editing an attestation.
    const prose = [
      ...(/PROSE_SECTIONS = \(([^)]*)\)/.exec(src)?.[1] ?? '').matchAll(/"([^"]+)"/g),
    ].map((m) => m[1] as string);
    if (prose.length === 0) {
      throw new Error(`${PLANREC_SEAM}: PROSE_SECTIONS parsed to no sections`);
    }
    const headings = [...render.matchAll(/lines\.append\("## ([A-Za-z]+)"\)/g)].map(
      (m) => m[1] as string
    );
    for (const s of prose) {
      add(
        'section',
        `## ${s}`,
        'section',
        'authored; an empty one renders as `<FILL: ...>`',
        'PROSE_SECTIONS'
      );
    }
    for (const h of headings) {
      if (prose.includes(h)) continue;
      add('section', `## ${h}`, 'section', 'generated by `render()`, never authored', 'render()');
    }

    // 4. THE TRAILER, in the order render() writes it. Every key is conditional, so the
    // table says so rather than implying a fixed block.
    for (const k of trailer) {
      add('trailer', k, '`## Record` trailer', 'written when set, omitted when empty', 'render()');
    }

    // 5. THE ANNOTATION LINES, as their literal patterns. These are the two four-space lines
    // that ride under a box, and the difference between them is load-bearing: `(record)` is
    // an ATTESTATION the gate proves against the ledger, `(ticked)` is a NOTE nothing proves.
    for (const name of ['RECORD_LINE_RE', 'TICK_LINE_RE', 'BOX_LINE_RE']) {
      const m = new RegExp(`^${name} = re\\.compile\\(\\s*\\n?\\s*r"([^"]+)"`, 'm').exec(src);
      if (m === null) {
        throw new Error(
          `${PLANREC_SEAM} no longer defines ${name} as a raw-string regex. The annotation ` +
            'lines are the part of the grammar a human types by hand, so publishing a stale ' +
            'pattern for them is the failure this region exists to prevent.'
        );
      }
      add('line', name, 'line pattern', `\`${m[1] as string}\``, name);
    }
    return rows;
  },
};

/* ------------------------------------------------------- the .json inventory */

/**
 * Where a `.json` file is allowed to live, and what has to be true for it to stay.
 *
 * THE PREDICATE WAS PROSE AND THE PROSE WENT STALE IN ONE DAY.
 * docs/ci-overhaul/08-driver-contract.md, section "The .json inventory has a shape, so give it
 * a predicate", counts "9 at the repository root, 15 under `.ci/config`, 20 under
 * `scripts/data`". Measured the day this provider was written: 9, 16, 25, plus a fourth home
 * the prose does not count at all (`.ci/policy`, 2). Two of the three numbers were wrong
 * within a day of being written, and `scripts/data/domains.json:224` carries its own copy of
 * the same stale "20 of them" while arguing about this very predicate. That is the argument
 * for deriving the inventory instead of typing it.
 *
 * WHAT `Discovered by` MEANS HERE, STATED PRECISELY, because the honest answer is narrower
 * than the heading suggests. No tree read can establish that `tsc` opens `tsconfig.json`.
 * What it CAN establish is whether anything in this repository WRITES the path down, and in
 * what kind of file:
 *
 *   `(convention)`    nothing non-prose in the tree names it. The only thing that can be
 *                     finding it is a third-party tool's own fixed convention -- the driver
 *                     contract's KEEP case.
 *   `wiring: <path>`  a declarative file writes the path (json, jsonc, yml, toml, env, or
 *                     anything under `.vscode/`). A path that lives in configuration can be
 *                     repointed by editing configuration.
 *   `code: <path>`    only a program writes the path. Moving the file means editing code.
 *
 * A GLOB AND AN INTERPOLATION ARE NAMES TOO, and leaving them out put the answer wrong in the
 * DANGEROUS direction. The first run of this provider reported all seven
 * `scripts/data/nis2-directive-2022-2555-*.manifest.json` files as `(convention)`, i.e. as
 * KEEP-WHERE-THEY-ARE, when `scripts/gates/check-directive-quotes.ts:90` builds their names with a
 * template literal. A false `(convention)` is the reading that tells a human "no reader will
 * break if you move this", so `*`, `${...}`, `%s` and `{}` inside a `.json`-shaped token are
 * matched as wildcards rather than as literal characters.
 *
 * ONE NAMER, NOT THE SET, AND THAT IS A PAID-FOR CHOICE. `suppressionsProvider` above records
 * why it has no Readers column: a grep-derived reader set was built and observed FLIPPING
 * mid-run when a peer session staged an unrelated file, and these regions have to stay
 * diffable across waves in a shared checkout. The same hazard applies here, so the cell holds
 * the single highest-priority namer under a FIXED order rather than a set or a count. A peer
 * staging a file moves this cell only when the new file OUTRANKS the current namer, which is
 * a real change to who owns the path.
 *
 * PROSE IS NOT DISCOVERY. `git grep -l biome.json` answers with six files, four of them plans
 * and reference documents. A document that mentions a path cannot open it.
 * `.ci/rediacc_ci/quality/dead_python.py` refuses `agent/` mentions as an admission route for
 * the same reason and in the same words.
 */

/** The four homes the driver contract's predicate is about, in the order it discusses them. */
const JSON_HOMES: readonly { home: string; dir: string }[] = [
  { home: 'root', dir: '.' },
  { home: '.ci/config', dir: '.ci/config' },
  { home: 'scripts/data', dir: 'scripts/data' },
  { home: '.ci/policy', dir: '.ci/policy' },
];

/** Declarative files: a path written in one of these is DATA, and repointable as data. */
const WIRING_EXT = ['.json', '.jsonc', '.yml', '.yaml', '.toml', '.env', '.cfg', '.ini'];
/** Programs: a path written in one of these is a literal in code. */
const CODE_EXT = ['.ts', '.tsx', '.js', '.jsx', '.cjs', '.mjs', '.py', '.sh', '.bash', '.go'];

/**
 * Directories whose files may MENTION a path without DISCOVERING it.
 *
 * `agent/` and `docs/` are prose. The three data homes are the inventory's own members voting
 * on each other: `.ci/config/bws-unrequested.json` names `regions.json` and is a policy list,
 * not a thing that opens files. Root-level members are deliberately NOT excluded -- for them
 * "an inventory member" and "the repository's actual configuration" are the same nine files,
 * and dropping `package.json` from the corpus would lose the single most common true answer.
 */
const NOT_A_DISCOVERER = ['agent/', 'docs/', '.ci/config/', '.ci/policy/', 'scripts/data/'];

/**
 * `gates.lock.json` is excluded BY NAME, and the exclusion is load-bearing rather than tidy.
 *
 * It is the committed JSON projection of `scripts/ci-runner/manifest.ts`, regenerated by
 * `gen:gates-lock`, and it names 15 of the baselines in `scripts/data` through gate `paths:`
 * and `leaves:` entries. Without this line it wins the wiring tier for eighteen rows and the
 * table advises "repoint in scripts/ci-runner/gates.lock.json" -- advice that is not merely
 * unhelpful but wrong, since editing a generated file is undone by the next generate. Dropping
 * it surfaces the gate script that actually opens the baseline, which is the file a mover has
 * to change.
 */
const GENERATED_PROJECTIONS = [GATES_LOCK];

/**
 * The wiring tier's internal order, most authoritative first.
 *
 * Alphabetical order alone picked arbitrary winners: `.syncpackrc.json` resolved to
 * `.syncpackrc-reasons.json` (its own annotation sidecar) when `package.json` is the file that
 * passes it to syncpack. A prefix list is the smallest thing that fixes it and it is DATA, so
 * a reader can see the ranking rather than inferring it from a sort.
 */
const WIRING_RANK = ['.vscode/', 'package.json', '.github/', '.devcontainer/'];

const wiringRank = (f: string): number => {
  const i = WIRING_RANK.findIndex((p) => f === p || f.startsWith(p));
  return i === -1 ? WIRING_RANK.length : i;
};

/**
 * A WILDCARD TOKEN NEEDS THIS MANY LITERAL CHARACTERS BEFORE IT COUNTS AS A NAME.
 *
 * `packages/json/src/_config.yml:14` holds `"*.json"`. Treated as a name, that one line
 * "discovers" every `.json` file in the repository, and the second run of this provider
 * duly reported it as the namer for eleven rows -- one bare glob outranking `package.json`,
 * `.vscode/settings.json` and every workflow. A pattern with nothing literal in it is not a
 * reference to a file, it is a reference to a file TYPE, so the stem left after the
 * wildcards and the extension are removed has to be at least this long.
 *
 * THE STEM IS THE BASENAME'S, NOT THE WHOLE TOKEN'S, and the third run is why.
 * `.ci/scripts/quality/check_hook_integrity.py` writes `scripts/data/*.json`. Counting the
 * directory characters gave that token a stem of `scriptsdata`, eleven characters, so it
 * cleared the floor and took SEVENTEEN rows in `scripts/data` -- including all seven nis2
 * manifests, which have a real namer. A directory is not a name either.
 */
const WILDCARD_MIN_STEM = 4;

/**
 * The stand-in a wildcard is collapsed to before the token is escaped for a regex.
 *
 * NOT `\u0000`, WHICH IS WHAT THIS WAS. A NUL inside a regex literal is a control character,
 * so `no-control-regex` reported this function twice and `check:lint:tooling` was red on it.
 * The sentinel only has to be a character no repository path contains; U+E000 is the first
 * private-use code point, which nothing can legitimately claim, and it is not a control
 * character. `replaceAll` rather than a global regex for the same reason: the value never has
 * to be spelled inside a pattern at all.
 */
const HOLE = '\uE000';
/** Every `.json`/`.jsonc`-shaped token in a file, as a matcher. Wildcards stay wildcards. */
const jsonTokens = (text: string): RegExp[] => {
  const out: RegExp[] = [];
  const seen = new Set<string>();
  for (const m of text.matchAll(/[\w.$/*{}%@-]*\.jsonc?\b/g)) {
    // A LEADING `./` IS NOISE, AND DROPPING IT IS NOT COSMETIC. `.vscode/settings.json`
    // writes `./css-custom-data.json`; without this line the anchored pattern could never
    // match the repo-relative `css-custom-data.json`, and the row fell through to a code
    // file -- reporting the path as hardcoded in a program when it is configuration in the
    // editor's own settings, which is the exact distinction this column exists to draw.
    const tok = m[0].replace(/^\.\//, '');
    if (tok === '.json' || tok === '.jsonc' || seen.has(tok)) continue;
    seen.add(tok);
    // `${lang}`, `*`, `%s` and `{}` are holes a caller fills, not characters in a name.
    const holed = tok
      .replace(/\$\{[^}]*\}/g, HOLE)
      .replace(/\{[^}]*\}/g, HOLE)
      .replace(/%[sd]/g, HOLE)
      .replaceAll('*', HOLE);
    if (holed.includes(HOLE)) {
      const base = holed.slice(holed.lastIndexOf('/') + 1);
      const stem = base
        .replaceAll(HOLE, '')
        .replace(/\.jsonc?$/, '')
        .replace(/[^\w-]/g, '');
      if (stem.length < WILDCARD_MIN_STEM) continue;
    }
    const body = holed.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replaceAll(HOLE, '[^/]*');
    out.push(new RegExp(`(?:^|/)${body}$`));
  }
  return out;
};

export const jsonInventoryProvider: Provider = {
  id: 'json-inventory',
  scans:
    'every tracked `.json`/`.jsonc` file in the four homes the driver contract names (the ' +
    'repository root, `.ci/config`, `scripts/data`, `.ci/policy`), against the non-prose ' +
    'files that write its path down, globs and template literals included',
  columns: ['File', 'Home', 'Discovered by', 'Configurable path?'],
  rows: (root) => {
    // THE CORPUS, read ONCE. Every subject is matched against the same compiled token lists,
    // so the cost is one pass over the tree rather than one per row.
    const { present } = presentFiles(root, lsFiles(root, '.'));
    const wiring: { file: string; tokens: RegExp[] }[] = [];
    const code: { file: string; tokens: RegExp[] }[] = [];
    for (const f of present) {
      if (NOT_A_DISCOVERER.some((d) => f.startsWith(d))) continue;
      if (GENERATED_PROJECTIONS.includes(f)) continue;
      const ext = path.extname(f);
      const isWiring = WIRING_EXT.includes(ext) || f.startsWith('.vscode/');
      if (!isWiring && !CODE_EXT.includes(ext)) continue;
      let text = '';
      try {
        text = fs.readFileSync(path.join(root, f), 'utf-8');
      } catch {
        continue;
      }
      const tokens = jsonTokens(text);
      if (tokens.length === 0) continue;
      (isWiring ? wiring : code).push({ file: f, tokens });
    }
    if (wiring.length === 0 || code.length === 0) {
      throw new Error(
        `json-inventory: the namer corpus is ${wiring.length} wiring and ${code.length} code ` +
          'file(s). Both halves must be non-empty; an empty one would report every file in ' +
          'that tier as discovered by convention, which reads as "safe to leave where it is".'
      );
    }
    wiring.sort((a, b) => wiringRank(a.file) - wiringRank(b.file) || byCodePoint(a.file, b.file));
    code.sort((a, b) => byCodePoint(a.file, b.file));

    const rows: ProviderRow[] = [];
    for (const { home, dir } of JSON_HOMES) {
      const listed = lsFiles(root, ...(dir === '.' ? ['*.json', '*.jsonc'] : [dir]));
      const members = presentFiles(root, listed).present.filter((f) => {
        if (!f.endsWith('.json') && !f.endsWith('.jsonc')) return false;
        // ROOT MEANS DEPTH ONE. `git ls-files -- '*.json'` matches at every depth, and a
        // pathspec that quietly swept `packages/**` into the root bucket would report a
        // predicate violation for every workspace manifest in the repository.
        return dir === '.' ? !f.includes('/') : path.dirname(f) === dir;
      });
      // ANTI-VACUITY PER HOME, NOT JUST IN TOTAL. Three of these four could empty out without
      // the total reaching zero, and this table's whole claim is about WHERE files live: a
      // home that silently stopped being scanned reads as a home that has been cleaned up.
      if (members.length === 0) {
        throw new Error(
          `json-inventory: the ${home} home matched no .json file. Either it moved or the ` +
            'pathspec stopped matching; an empty home rendered as an empty section would ' +
            'read as a directory somebody had cleaned up.'
        );
      }
      for (const rel of members) {
        let namer = '';
        let tier = '';
        for (const [label, list] of [
          ['wiring', wiring],
          ['code', code],
        ] as const) {
          for (const cand of list) {
            if (cand.file === rel) continue;
            if (cand.tokens.some((re) => re.test(rel))) {
              namer = cand.file;
              tier = label;
              break;
            }
          }
          if (namer !== '') break;
        }
        rows.push({
          key: rel,
          cells: [
            `\`${rel}\``,
            home,
            namer === '' ? '(convention: nothing non-prose names it)' : `${tier}: \`${namer}\``,
            namer === ''
              ? 'no -- fixed tool convention'
              : tier === 'wiring'
                ? `yes -- repoint in \`${namer}\``
                : `no -- hardcoded in \`${namer}\``,
          ],
        });
      }
    }
    return rows;
  },
  missing: (root) =>
    JSON_HOMES.flatMap(
      ({ dir }) =>
        presentFiles(root, lsFiles(root, ...(dir === '.' ? ['*.json', '*.jsonc'] : [dir]))).missing
    ).sort(byCodePoint),
};

/* ----------------------------------------------------------- env manifest */

/**
 * The environment-variable manifest, read as DATA and never re-derived here.
 *
 * WHY THIS PROVIDER DOES NOT RECOMPUTE THE UNION. The classification is produced by
 * `.ci/rediacc_ci/quality/env_manifest.py`, which unions five sources (tracked env files,
 * workflow and action `KEY:` maps, `process.env`, `os.environ` by AST, and the Bitwarden
 * secret map) and reds when the manifest and the tree disagree in EITHER direction. A second
 * reading of those five sources, in TypeScript, would be a second answer to a question that
 * already has an enforced one, and the two would drift apart in a week. This is the argument
 * the gates provider makes for reading `scripts/ci-runner/gates.lock.json` rather than the
 * manifest module, applied one seam along: the committed projection IS the interface.
 *
 * ONE ROW PER VARIABLE, NOT ONE PER SHARD, and that is the whole reason this region is worth
 * generating. One row per shard carrying that shard's count cannot see one name leaving as
 * another arrives, and the pre-port record in `scripts/data/doc-registry-preport.json`
 * compares MEMBERSHIP, so a key set of shard names would make that instrument blind to
 * exactly the drop it exists to name. It is the argument that put one row per FILE in the
 * test-split table rather than one row per root.
 *
 * NAMES AND SHARDS ONLY. Not one value is read, printed or stored. The `secret` shard is
 * names a vault supplies, and a table of names is a map of the seams where a table of
 * values would be the leak.
 */
const ENV_MANIFEST = '.ci/config/env-manifest.json';

interface EnvCollision {
  name: string;
  dead_in: string;
  live_in: string;
}

interface EnvManifest {
  shard_definitions: Record<string, string>;
  shards: Record<string, string[]>;
  collisions: EnvCollision[];
  notes: Record<string, string>;
  tombstone_proof_sites: Record<string, string[]>;
}

/** A plain JSON object, or `null`. Arrays are not objects for this purpose. */
const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

/**
 * The manifest, or a refusal that names the part of it that is wrong.
 *
 * EVERY CLAUSE BELOW IS AN ANTI-VACUITY CLAUSE, not a schema formality. A missing file, a
 * truncated write, a shard that emptied out, or a `shards` map that lost a key its
 * `shard_definitions` twin still declares would all render as a SMALLER table and report
 * success. A smaller table of environment seams reads as "the surface shrank", which is the
 * best-looking possible result and the one most likely to be believed.
 *
 * The per-shard floor is the clause worth arguing for: the total can stay large while one
 * classification empties, and the smallest shard here is an order of magnitude below the
 * largest, so a total floor would never notice the smallest one disappearing. The same
 * reasoning put a per-home floor in the json inventory above.
 */
export const readEnvManifest = (root: string): EnvManifest => {
  const text = readSeam(root, ENV_MANIFEST);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    throw new Error(`${ENV_MANIFEST} is not valid JSON: ${(e as Error).message}`);
  }
  if (!isRecord(parsed)) {
    throw new Error(`${ENV_MANIFEST} is not a JSON object, so it carries no shards to render.`);
  }
  const defs = parsed.shard_definitions;
  const shards = parsed.shards;
  if (!isRecord(defs) || !isRecord(shards)) {
    throw new Error(
      `${ENV_MANIFEST} is missing shard_definitions or shards. Both are required: the ` +
        'definitions say who supplies a value and who may read it, and without them this ' +
        'table would render a shard name as if it explained itself.'
    );
  }
  const declared = Object.keys(defs).sort(byCodePoint);
  const populated = Object.keys(shards).sort(byCodePoint);
  const undefinedShards = populated.filter((s) => !(s in defs));
  const unpopulated = declared.filter((s) => !(s in shards));
  if (undefinedShards.length > 0 || unpopulated.length > 0) {
    throw new Error(
      `${ENV_MANIFEST}: shard_definitions and shards name different shards. Declared but ` +
        `not populated: ${unpopulated.join(', ') || '(none)'}. Populated but not declared: ` +
        `${undefinedShards.join(', ') || '(none)'}. A shard that exists on one side only is ` +
        'a whole class of variables that this table would either omit or fail to explain.'
    );
  }
  if (declared.length === 0) {
    throw new Error(
      `${ENV_MANIFEST} declares no shard at all. Rendering that is an empty table under a ` +
        'heading promising every environment variable this repository reads or supplies.'
    );
  }
  const seen = new Map<string, string>();
  for (const shard of declared) {
    const names = shards[shard];
    if (!Array.isArray(names) || names.some((n) => typeof n !== 'string' || n === '')) {
      throw new Error(`${ENV_MANIFEST}: shard ${shard} is not a list of non-empty names.`);
    }
    if (names.length === 0) {
      throw new Error(
        `${ENV_MANIFEST}: shard ${shard} holds zero names. A total floor cannot catch ` +
          'this, and an empty shard rendered as an absence reads as a class somebody ' +
          'had cleaned up.'
      );
    }
    for (const name of names as string[]) {
      const already = seen.get(name);
      if (already !== undefined) {
        throw new Error(
          `${ENV_MANIFEST}: ${name} is in both the ${already} and ${shard} shards. The ` +
            'manifest owns a pairwise-disjointness claim and this table keys its rows on the ' +
            'NAME, so a duplicate would emit two rows under one key and make every set ' +
            'comparison over this region lie.'
        );
      }
      seen.set(name, shard);
    }
  }

  const collisions = Array.isArray(parsed.collisions) ? (parsed.collisions as EnvCollision[]) : [];
  const notes = isRecord(parsed.notes) ? (parsed.notes as Record<string, string>) : {};
  const proofs = isRecord(parsed.tombstone_proof_sites)
    ? (parsed.tombstone_proof_sites as Record<string, string[]>)
    : {};

  // A RESIDUE ENTRY ABOUT A NAME NO SHARD HOLDS IS AN ANNOTATION NOTHING CAN SHOW. This table hangs the collision, the note and the proof site off the variable's own row, so a key outside the shards is not merely unrendered, it is invisible: the reader is never told the manifest had something to say. Refused by name, with the two ways out.
  const dangling: string[] = [];
  for (const c of collisions) {
    if (typeof c?.name !== 'string' || !seen.has(c.name)) dangling.push(`collisions: ${c?.name}`);
  }
  for (const n of Object.keys(notes)) if (!seen.has(n)) dangling.push(`notes: ${n}`);
  for (const [site, names] of Object.entries(proofs)) {
    if (!Array.isArray(names)) throw new Error(`${ENV_MANIFEST}: proof site ${site} is not a list`);
    for (const n of names) if (!seen.has(n)) dangling.push(`tombstone_proof_sites/${site}: ${n}`);
  }
  if (dangling.length > 0) {
    throw new Error(
      `${ENV_MANIFEST} annotates ${dangling.length} name(s) that are in no shard: ` +
        `${dangling.sort(byCodePoint).join(', ')}. Either classify the name or move the ` +
        'explanation into the file-level comment, because an annotation on an unclassified ' +
        'name is rendered nowhere and read by nobody.'
    );
  }
  return {
    shard_definitions: defs as Record<string, string>,
    shards: shards as Record<string, string[]>,
    collisions,
    notes,
    tombstone_proof_sites: proofs,
  };
};

export const envManifestProvider: Provider = {
  id: 'env-manifest',
  scans:
    'the shard classification in `.ci/config/env-manifest.json`, the committed projection ' +
    '`check:ci-env-manifest` re-derives from five sources and holds faithful in both ' +
    'directions, one row per variable NAME and never a value',
  columns: ['Variable', 'Shard', 'Also recorded'],
  rows: (root) => {
    const m = readEnvManifest(root);
    const collisionOf = new Map(m.collisions.map((c) => [c.name, c]));
    const proofsOf = new Map<string, string[]>();
    for (const [site, names] of Object.entries(m.tombstone_proof_sites)) {
      for (const n of names) proofsOf.set(n, [...(proofsOf.get(n) ?? []), site].sort(byCodePoint));
    }
    const rows: ProviderRow[] = [];
    for (const [shard, names] of Object.entries(m.shards)) {
      for (const name of names) {
        const also: string[] = [];
        const c = collisionOf.get(name);
        if (c !== undefined) also.push(`collision: dead in ${c.dead_in}, live in ${c.live_in}`);
        if (m.notes[name] !== undefined) also.push('note');
        const sites = proofsOf.get(name);
        if (sites !== undefined)
          also.push(`tombstone proof: ${sites.map((s) => `\`${s}\``).join(', ')}`);
        rows.push({
          key: name,
          cells: [`\`${name}\``, shard, also.length === 0 ? '-' : also.join('; ')],
        });
      }
    }
    return rows.sort((a, b) => byCodePoint(a.key, b.key));
  },
};

const PROSE_RULES = '.ci/config/prose-style-rules.json';

interface ProseRule {
  id: string;
  title: string;
  severity: string;
  scopes?: string[];
  patterns?: string[];
  detection?: string;
  examples?: { expect?: string }[];
}

/**
 * R1-R18, one row per rule, read from the rules file rather than typed.
 *
 * THE COLUMN THAT MATTERS IS `Detection`, AND IT EXISTS TO STOP A LIE. Nine of the eighteen
 * rules are ADVISORY: written down, agreed, and not mechanically detected, because the pattern
 * that would catch them also catches their own counter-examples. R12's bad example "The project
 * failed." and R3's good example "The build failed after the last change." are the same surface
 * shape, and separating them needs to know what kind of noun the subject is.
 *
 * A table listing eighteen rules with no such column would tell every reader that eighteen rules
 * are enforced. That is the sentence this whole generator exists to abolish -- the same shape as
 * ci-gates.md telling readers there were "254 fast gates" against a live 312 -- so the count of
 * patterns per rule is rendered, and an advisory rule says `advisory` in its own row.
 *
 * `Undetected examples` is the second half of the same honesty. A rule may ship a bad example
 * that nothing catches; the rules file declares those explicitly and this column counts them,
 * so the gap is a number in the document instead of a paragraph in a config file.
 */
export const proseStyleProvider: Provider = {
  id: 'prose-style',
  scans: `${PROSE_RULES}, one row per rule`,
  columns: ['Rule', 'Title', 'Severity', 'Scopes', 'Detection', 'Undetected examples'],
  rows: (root) => {
    const file = path.join(root, PROSE_RULES);
    if (!fs.existsSync(file)) return [];
    const doc = JSON.parse(fs.readFileSync(file, 'utf-8')) as { rules?: ProseRule[] };
    return (doc.rules ?? []).map((r) => {
      const patterns = r.patterns ?? [];
      // NAME THE DETECTION RATHER THAN ENUMERATE THE KNOWN ONES. Testing for `measured` by name and sending everything else to a pattern count published R19 -- an ENFORCED error detected by a heuristic over a whole paragraph, carrying no patterns -- as `advisory`, the one word that tells a reader a rule is not enforced. This mirrors
      // `prose_style.run_sync`, which had the identical bug and was fixed in the same change: the two are separate implementations of one decision over one rules file, which is the very shape the sibling-agreement test exists to catch.
      const detection =
        patterns.length > 0 ? `${patterns.length} pattern(s)` : (r.detection ?? 'advisory');
      const undetected = (r.examples ?? []).filter((e) => e.expect === 'undetected').length;
      return {
        key: r.id,
        cells: [
          r.id,
          r.title,
          r.severity,
          (r.scopes ?? ['all']).join(', '),
          detection,
          String(undetected),
        ],
      };
    });
  },
  missing: (root) => (fs.existsSync(path.join(root, PROSE_RULES)) ? [] : [PROSE_RULES]),
};

export const PROVIDERS: readonly Provider[] = [
  gatesProvider,
  gatesSummaryProvider,
  proseStyleProvider,
  hookGuardsProvider,
  hookSummaryProvider,
  suppressionsProvider,
  ciTreeProvider,
  policyProvider,
  testSplitProvider,
  bootstrapProvider,
  jobGraphProvider,
  mediaProvider,
  planRecordGrammarProvider,
  jsonInventoryProvider,
  envManifestProvider,
];

export const providerById = (id: string): Provider | undefined =>
  PROVIDERS.find((p) => p.id === id);
