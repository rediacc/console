/**
 * The row providers behind `npx tsx scripts/gen-docs.ts`.
 *
 * A PROVIDER SCANS THE TREE. It never carries a hand-written list of the things it documents,
 * because a hand-written list is exactly the artifact this phase exists to abolish. Three
 * measured examples from one session: `.dead-bash-allowlist` said "the 17 gate scripts" when
 * there are 131, scripts/check-ci-parity.ts said "runs 57 gate tests", and
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
  // "IS a gate test", not "has one", and the distinction was got wrong once here before the
  // table was read against the lock. `qualityGateTest` marks an entry that IS one of the
  // on-disk gate tests -- manifest.ts says so outright, and every one of the 144 rows carrying
  // it has an id beginning `gate-test:`, with no `gate-test:` entry lacking it. A column headed
  // "Has a gate test" would have told every reader that 86 quality-code gates are untested,
  // which is a different and false claim.
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
        // The command is a shell line: `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"` or
        // `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/y.py" --flag`. Pull every hook path out
        // of it rather than assuming one shape, so a wrapper that runs two guards is not
        // silently reported as running one.
        for (const hit of (h.command ?? '').matchAll(/\.claude\/hooks\/([A-Za-z0-9_./-]+)/g)) {
          out.push({ event, matcher: m.matcher ?? '(any)', file: hit[1] ?? '' });
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
      text.set(rel, fs.readFileSync(path.join(root, '.claude/hooks', rel), 'utf-8'));
    } catch {
      text.set(rel, '');
    }
  }
  const reached = new Map<string, string>();
  for (const w of wired) reached.set(w, 'settings.json');
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
    'the `hooks` wiring in .claude/settings.json, closed transitively over the tracked files under .claude/hooks/',
  columns: ['Hook file', 'Events', 'Reached', 'Language'],
  rows: (root) => {
    const wired = wiredHooks(root);
    const events = new Map<string, Set<string>>();
    for (const w of wired) {
      const set = events.get(w.file) ?? new Set<string>();
      set.add(w.event);
      events.set(w.file, set);
    }

    const { present } = presentFiles(root, lsFiles(root, '.claude/hooks'));
    const members = present
      .filter((f) => /\.(sh|py)$/.test(f))
      .map((f) => f.slice('.claude/hooks/'.length))
      // State snapshots and byte-compiled caches are not hooks. Both are per-session litter that
      // would make this record differ between two machines looking at the same commit.
      .filter((f) => !f.startsWith('state/') && !f.includes('__pycache__'));

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
  missing: (root) => presentFiles(root, lsFiles(root, '.claude/hooks')).missing,
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

    const { present } = presentFiles(root, lsFiles(root, '.claude/hooks'));
    const members = present
      .filter((f) => /\.(sh|py)$/.test(f))
      .map((f) => f.slice('.claude/hooks/'.length))
      // Identical exclusions to hook-guards, and they must stay identical: state snapshots and
      // byte-compiled caches are per-session litter, so counting them here and not there would
      // make the summary and the reference disagree about the same tree.
      .filter((f) => !f.startsWith('state/') && !f.includes('__pycache__'));
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
        String(new Set(wired.map((w) => `${w.event} ${w.matcher}`)).size),
        String(new Set(wired.map((w) => w.file)).size),
      ],
    });
    rows.push({
      key: '(tracked hook files nothing reaches)',
      cells: ['(tracked hook files nothing reaches)', '-', String(unreached)],
    });
    return rows;
  },
  missing: (root) => presentFiles(root, lsFiles(root, '.claude/hooks')).missing,
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
 * 2026-09-06: a peer session staged scripts/check-package-key-budget.ts between one `--write`
 * and the next verify, and `git grep` (which searches TRACKED files) began returning it, so the
 * `package.json` row changed with no change to any suppression mechanism at all. A cell derived
 * from "who mentions this string anywhere" is volatile with respect to every unrelated edit in
 * the repository, and this record exists to be diffed across waves by a program that explicitly
 * warns the checkout is shared (08-driver-contract.md section 4). A column that churns on
 * unrelated work makes the diff unreadable and trains its reader to skip it.
 *
 * The reader mapping is genuinely useful and belongs in the phase that owns
 * docs/agent-reference/suppressions.md, where it can be pinned to a stable oracle -- the probe
 * table in scripts/check-suppression-liveness.ts already pairs each mechanism with its reader by
 * declaration rather than by grep. This is a deliberate omission, not an oversight; do not add
 * the grep back.
 */
const commentForm = (rel: string, text: string): string => {
  const lines = text.split('\n');
  // ORDER IS THE WHOLE ALGORITHM, and it was wrong on the first pass. A naive "does any quoted
  // string contain BLOCKER:" test classified `.runner-advice-allowlist` and
  // `.ci/breakpoint/.breakpoint-drift-accept` as JSON, because both are shell-comment files whose
  // HEADER PROSE quotes the format (`a "# BLOCKER: <reason>" comment block`). Real forms are
  // therefore tested first, from most specific anchor to least, and documentation-only mentions
  // fall through to a state that says so instead of being guessed at.
  if (lines.some((l) => /^\s*#\s*BLOCKER:/.test(l))) return '# comment';
  if (lines.some((l) => /^\s*\/\/\s*BLOCKER:/.test(l))) return '// comment';
  if (/\.jsonc?$/.test(rel) && lines.some((l) => /"[^"]*BLOCKER:/.test(l))) return 'JSON value';
  if (lines.some((l) => /^\s*[^#/\s].*#\s*BLOCKER:/.test(l))) return 'inline';
  // Every BLOCKER: in the file is in its own documentation, so nothing is suppressed through one
  // right now. An empty allowlist is a legitimate and desirable state -- `.breakpoint-drift-accept`
  // says outright that empty is correct for this repo -- and reporting it as a comment style
  // would hide that.
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
          // Count descending, then extension ascending: a stable total order, so two runs on
          // the same tree render the same string even when two extensions tie.
          .sort((a, b) => b[1] - a[1] || byCodePoint(a[0], b[0]))
          .map(([e, n]) => `${e} ${n}`)
          .join(', ');
        return { key: dir, cells: [dir, String(files.length), exts] };
      });
  },
  missing: (root) => presentFiles(root, lsFiles(root, '.ci')).missing,
};

/** Every provider, keyed by the id a marker region names. */
export const PROVIDERS: readonly Provider[] = [
  gatesProvider,
  gatesSummaryProvider,
  hookGuardsProvider,
  hookSummaryProvider,
  suppressionsProvider,
  ciTreeProvider,
];

export const providerById = (id: string): Provider | undefined =>
  PROVIDERS.find((p) => p.id === id);
