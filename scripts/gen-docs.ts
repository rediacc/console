/**
 * gen-docs -- documentation regions are DERIVED from the tree, never typed by hand.
 *
 * WHY THIS EXISTS, AND WHY IT IS PHASE 0 OF THE DOCS WORKSTREAM (W11).
 *
 * Documents in this repository quote registry numbers by hand, and a hand-typed number goes
 * stale in SILENCE. Three found and corrected in a single session on 2026-09-06:
 *
 *   - `.dead-bash-allowlist` said "the 17 gate scripts". There are 131.
 *   - scripts/check-ci-parity.ts said "runs 57 gate tests".
 *   - docs/agent-reference/ci-gates.md said "254 fast gates" against a live 312.
 *
 * Each was true when written. Nothing re-derived any of them, so each decayed into a confident
 * falsehood that the next reader inherits and does not re-check. A generated region cannot do
 * that: it is rewritten from the tree, and a region that has drifted is a hard red rather than
 * a sentence nobody questions.
 *
 * WHY THE SNAPSHOT IS A SET AND NOT A COUNT. This is the load-bearing decision of the whole
 * phase, so it is stated here and again in the snapshot file itself.
 *
 * A COUNT FLOOR CANNOT CATCH A SILENT DROP. Suppose the gate registry holds 388 entries and a
 * floor is set at 300. A port that loses 88 of them -- a glob that stopped matching, a
 * collapsed loop, a rename nobody chased -- leaves 300 entries and the floor still PASSES. The
 * report is green, the coverage is gone, and the only symptom arrives months later as a defect
 * nothing caught. Worse: a port that drops 88 and adds 88 different ones keeps the count
 * EXACTLY equal, so even an equality-on-count check passes.
 *
 * Only a recorded SET catches that, because it compares membership: it names the 88 keys that
 * vanished. And it must be recorded BEFORE the ports run, because after a port there is nothing
 * left to compare against -- the tree only ever knows what it currently is.
 *
 * `--selftest` proves exactly this, by construction: it builds a 388-key baseline and a 388-key
 * perturbation with 88 members swapped, asserts the count comparison sees no difference, and
 * asserts the set diff names all 88. A control that fires is the only reason to believe the
 * instrument.
 *
 * USAGE
 *   tsx scripts/gen-docs.ts            verify: exit non-zero if any region has drifted
 *   tsx scripts/gen-docs.ts --write    rewrite every discovered region
 *   tsx scripts/gen-docs.ts --list     provider row counts, nothing written
 *   tsx scripts/gen-docs.ts --selftest prove the generator can fail
 *   tsx scripts/gen-docs.ts --snapshot record the pre-port row SET (refuses to overwrite)
 *   tsx scripts/gen-docs.ts --diff-snapshot   compare live rows against that record
 *
 * DETERMINISM IS A REQUIREMENT, NOT A NICETY. Two `--write` runs on a clean tree must produce
 * byte-identical files, or verify mode reds on noise and everyone learns to ignore it. So:
 * every sort uses `byCodePoint` (UTF-16 code units) rather than `localeCompare` (host ICU
 * collation, which differs between machines), and NOTHING here embeds a timestamp, a duration,
 * a hostname or a run id.
 *
 * NO GATE HEADER, DELIBERATELY. scripts/gate-bind.ts treats a `---- gate ----` block as a
 * declaration that four registrations exist (package.json, the ci-runner manifest, the workflow
 * step, the npm key). Those four files have a single writer during this program and this phase
 * is not it, so declaring a header here would register a gate that does not exist and turn
 * check:ci-gate-bind red. Registration is reported to the root driver instead.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

import {
  byCodePoint,
  GATES_LOCK,
  PROVIDERS,
  type Provider,
  type ProviderRow,
  providerById,
  readGatesLock,
} from './lib/doc-providers.js';
import { findRegions, OPEN_RE, rewriteRegions } from './lib/doc-regions.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const SNAPSHOT = 'scripts/data/doc-registry-preport.json';

const RED = process.stdout.isTTY ? '\u001b[0;31m' : '';
const GREEN = process.stdout.isTTY ? '\u001b[0;32m' : '';
const NC = process.stdout.isTTY ? '\u001b[0m' : '';

/* ------------------------------------------------------------- rendering */

/**
 * A markdown table cell.
 *
 * `|` ends a cell in GitHub-flavoured markdown, so an unescaped one in a value silently splits
 * the row and shifts every column after it. A newline would end the ROW. Both are neutralised
 * here rather than being assumed absent, because the values come from the tree and the tree
 * eventually contains everything.
 */
const cell = (s: string): string => s.replace(/\|/g, '\\|').replace(/[\r\n]+/g, ' ');

/** One region body: what the provider scans, the table, and the row count. */
export function render(p: Provider, rows: ProviderRow[]): string[] {
  const out: string[] = [''];
  out.push(`Scans: ${p.scans}.`);
  out.push('');
  out.push(`| ${p.columns.map(cell).join(' | ')} |`);
  out.push(`|${p.columns.map(() => '---').join('|')}|`);
  for (const r of rows) out.push(`| ${r.cells.map(cell).join(' | ')} |`);
  out.push('');
  out.push(
    `${rows.length} row(s). Generated by \`npx tsx scripts/gen-docs.ts --write\`; do not hand-edit.`
  );
  out.push('');
  return out;
}

/* --------------------------------------------------------------- targets */

/**
 * Every file that OPTS IN by carrying an opening marker.
 *
 * Tracked and untracked markdown both count. Untracked matters here specifically: this repo's
 * standing rule is that work stays uncommitted until the operator asks, so a document that
 * exists only in the working tree is the normal case, not the exception. Discovering targets by
 * scanning means adding a generated region to any document requires no edit to this file.
 */
function targets(root: string): string[] {
  const list = (args: string[]): string[] =>
    execFileSync('git', ['-C', root, 'ls-files', '-z', ...args], {
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    })
      .split('\0')
      .filter((f) => f !== '');

  const candidates = new Set([
    ...list(['--', '*.md']),
    ...list(['--others', '--exclude-standard', '--', '*.md']),
  ]);
  const found: string[] = [];
  for (const f of [...candidates].sort(byCodePoint)) {
    const abs = path.join(root, f);
    let st: fs.Stats;
    try {
      st = fs.statSync(abs);
    } catch {
      continue; // in the index, gone from the worktree -- see doc-providers.ts on section 5b
    }
    if (!st.isFile() || st.size > 4 * 1024 * 1024) continue;
    // A TARGET IS A FILE WITH A REAL MARKER LINE, not one that merely contains the string.
    //
    // The first version tested `text.includes('>>> gen-docs:')`, and the document that
    // DOCUMENTS this mechanism immediately became a target of it: 07-tooling-decisions.md
    // quotes the marker syntax inside a table cell, so the generator adopted it, found no
    // region in it, and reported `ok <file> ()` -- a target with an empty provider list,
    // which reads as success and is really "I scanned a file that was never mine". Any
    // future document explaining the idiom would have done the same.
    //
    // OPEN_RE is anchored to a whole line, so a quotation inside prose or a table cell is
    // not a marker and a marker is never a quotation. That is the same predicate
    // findRegions uses, which is the point: discovery and parsing must agree, or a file can
    // be adopted by one and refused by the other.
    if (
      fs
        .readFileSync(abs, 'utf-8')
        .split('\n')
        .some((l) => OPEN_RE.test(l))
    )
      found.push(f);
  }
  return found;
}

interface Rendered {
  file: string;
  current: string;
  next: string;
  providers: string[];
}

function build(root: string): { rendered: Rendered[] } | { errors: string[] } {
  const cache = new Map<string, string[]>();
  const renderProvider = (id: string): string[] | null => {
    const cached = cache.get(id);
    if (cached !== undefined) return cached;
    const p = providerById(id);
    if (p === undefined) return null;
    const body = render(p, p.rows(root));
    cache.set(id, body);
    return body;
  };

  const rendered: Rendered[] = [];
  const errors: string[] = [];
  for (const f of targets(root)) {
    const current = fs.readFileSync(path.join(root, f), 'utf-8');
    const res = rewriteRegions(current, renderProvider);
    if ('errors' in res) {
      for (const e of res.errors) errors.push(`${f}:${e.line}: ${e.message}`);
      continue;
    }
    rendered.push({ file: f, current, next: res.text, providers: res.providers });
  }
  return errors.length > 0 ? { errors } : { rendered };
}

/* --------------------------------------------------------------- snapshot */

interface Snapshot {
  format: number;
  why: string[];
  recorded_at_commit: string;
  providers: Record<string, { rows: number; keys: string[] }>;
}

const liveSets = (root: string): Record<string, { rows: number; keys: string[] }> => {
  const out: Record<string, { rows: number; keys: string[] }> = {};
  for (const p of PROVIDERS) {
    const keys = p
      .rows(root)
      .map((r) => r.key)
      .sort(byCodePoint);
    out[p.id] = { rows: keys.length, keys };
  }
  return out;
};

/**
 * The two verdicts a set diff produces, and why only one of them is fatal.
 *
 * MISSING is the dangerous direction: a key that was recorded and is now gone means the tree
 * lost something a port was supposed to carry across. ADDED is normal growth -- the manifest
 * gained two gates during the planning session itself -- so it is reported and not failed on.
 */
export function setDiff(
  before: string[],
  after: string[]
): { missing: string[]; added: string[]; countEqual: boolean } {
  const b = new Set(before);
  const a = new Set(after);
  return {
    missing: before.filter((k) => !a.has(k)).sort(byCodePoint),
    added: after.filter((k) => !b.has(k)).sort(byCodePoint),
    countEqual: before.length === after.length,
  };
}

function writeSnapshot(root: string, force: boolean): number {
  const abs = path.join(root, SNAPSHOT);
  if (fs.existsSync(abs) && !force) {
    console.error(`${RED}refusing to overwrite${NC} ${SNAPSHOT}`);
    console.error('  This file is the PRE-PORT record. Rewriting it destroys the only copy of');
    console.error('  what the sets looked like before the ports moved rows around, which is the');
    console.error('  single thing a later wave has to diff against. Pass --force only if you are');
    console.error('  deliberately re-baselining, and say so out loud when you do.');
    return 1;
  }
  let commit = 'unknown';
  try {
    commit = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf-8' }).trim();
  } catch {
    commit = 'unknown';
  }
  const snap: Snapshot = {
    format: 1,
    why: [
      'The PRE-PORT row SET of every gen-docs provider, recorded before the tooling',
      'transformation ports move rows between files.',
      '',
      'WHY A SET AND NOT A COUNT FLOOR. A floor of 300 over 388 gate entries still PASSES',
      'after 88 of them silently vanish, and a port that drops 88 while adding 88 different',
      'ones keeps the count exactly equal, so even count-equality passes. Membership is the',
      'only comparison that names what was lost. It has to be recorded BEFORE the ports run,',
      'because afterwards the tree only knows what it currently is.',
      '',
      'MISSING keys are fatal to `--diff-snapshot`; ADDED keys are reported as normal growth.',
      'Regenerate ONLY with `tsx scripts/gen-docs.ts --snapshot --force`, deliberately.',
    ],
    recorded_at_commit: commit,
    providers: liveSets(root),
  };
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, `${JSON.stringify(snap, null, 2)}\n`);
  console.log(`${GREEN}wrote${NC} ${SNAPSHOT} at ${commit}`);
  for (const p of PROVIDERS) console.log(`  ${p.id}: ${snap.providers[p.id]?.rows ?? 0} row(s)`);
  return 0;
}

export interface ProviderVerdict {
  id: string;
  before: number;
  after: number;
  missing: string[];
  added: string[];
  countEqual: boolean;
  /** Recorded in the snapshot, and no provider by that id exists any more. */
  gone: boolean;
}

/**
 * Every recorded provider compared against every live one, over the UNION of their ids.
 *
 * THE UNION IS THE FIX FOR A HOLE THIS FUNCTION USED TO HAVE, and it is worth naming because it
 * is the same failure the snapshot exists to prevent, one level up. The first draft looped over
 * the LIVE provider list, so a provider deleted from doc-providers.ts was never compared to its
 * recorded set at all: 411 gate rows would drop out of the record and `--diff-snapshot` would
 * print three cheerful `ok` lines and exit 0. An instrument that only inspects what still exists
 * cannot report a disappearance. Looping over the union means a vanished provider surfaces as
 * every one of its recorded rows missing, which is exactly what happened.
 */
export function diffAll(
  recorded: Record<string, { rows: number; keys: string[] }>,
  live: Record<string, { rows: number; keys: string[] }>
): ProviderVerdict[] {
  const ids = [...new Set([...Object.keys(recorded), ...Object.keys(live)])].sort(byCodePoint);
  return ids.map((id) => {
    const before = recorded[id]?.keys ?? [];
    const after = live[id]?.keys ?? [];
    const d = setDiff(before, after);
    return {
      id,
      before: before.length,
      after: after.length,
      missing: d.missing,
      added: d.added,
      countEqual: d.countEqual,
      gone: recorded[id] !== undefined && live[id] === undefined,
    };
  });
}

function diffSnapshot(root: string): number {
  const abs = path.join(root, SNAPSHOT);
  if (!fs.existsSync(abs)) {
    console.error(`${RED}no pre-port snapshot${NC} at ${SNAPSHOT}; run --snapshot first`);
    return 1;
  }
  const snap = JSON.parse(fs.readFileSync(abs, 'utf-8')) as Snapshot;
  const verdicts = diffAll(snap.providers, liveSets(root));
  let bad = 0;
  for (const v of verdicts) {
    if (v.missing.length === 0) {
      console.log(
        `${GREEN}ok${NC}   ${v.id}: ${v.before} recorded, ${v.after} live, +${v.added.length} added`
      );
      continue;
    }
    bad += 1;
    console.error(
      `${RED}DROPPED${NC} ${v.id}: ${v.missing.length} recorded row(s) are gone` +
        (v.gone ? ' -- THE WHOLE PROVIDER NO LONGER EXISTS' : '') +
        (v.countEqual ? ' (and the COUNT is unchanged, which is why a floor would pass)' : '')
    );
    for (const k of v.missing) console.error(`       - ${k}`);
  }
  return bad === 0 ? 0 : 1;
}

/* --------------------------------------------------------------- selftest */

function selftest(): number {
  let bad = 0;
  const ck = (label: string, ok: boolean, detail?: unknown): void => {
    console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
    if (!ok) {
      bad += 1;
      console.log(`\t\t${JSON.stringify(detail)}`);
    }
  };

  const P: Provider = {
    id: 'fixture',
    scans: 'a fixture',
    columns: ['A', 'B'],
    rows: () => [
      { key: 'b', cells: ['b', 'two'] },
      { key: 'a', cells: ['a', 'one'] },
    ],
  };
  const body = render(P, P.rows(''));
  const doc = [
    '# title',
    '',
    '<!-- >>> gen-docs: fixture -->',
    '<!-- explanatory prose -->',
    '| STALE | ROW |',
    '<!-- <<< gen-docs -->',
    '',
    'hand-written tail',
  ].join('\n');
  const rw = rewriteRegions(doc, (id) => (id === 'fixture' ? body : null));

  ck(
    'a region is rewritten, its prose kept, its stale body dropped',
    'text' in rw &&
      rw.text.includes('<!-- explanatory prose -->') &&
      !rw.text.includes('STALE') &&
      rw.text.includes('| a | one |') &&
      rw.text.includes('hand-written tail'),
    rw
  );
  ck(
    'rewriting is IDEMPOTENT -- a second pass changes nothing',
    'text' in rw &&
      (() => {
        const again = rewriteRegions(rw.text, (id) => (id === 'fixture' ? body : null));
        return 'text' in again && again.text === rw.text;
      })()
  );

  // --- planted defects. Each must be REFUSED, by line, rather than half-applied. ---
  const unterminated = ['<!-- >>> gen-docs: fixture -->', 'body'].join('\n');
  ck('planted: an unterminated region is refused', 'errors' in findRegions(unterminated));
  const nested = [
    '<!-- >>> gen-docs: fixture -->',
    '<!-- >>> gen-docs: other -->',
    '<!-- <<< gen-docs -->',
    '<!-- <<< gen-docs -->',
  ].join('\n');
  ck('planted: a nested region is refused', 'errors' in findRegions(nested));
  ck('planted: a close with no open is refused', 'errors' in findRegions('<!-- <<< gen-docs -->'));
  ck(
    'planted: an unknown provider is refused, NOT emptied',
    'errors' in rewriteRegions(doc, () => null)
  );
  ck(
    'planted: a perturbed row makes the rewrite differ from the file (verify goes red)',
    'text' in rw &&
      (() => {
        const perturbed = rw.text.replace('| a | one |', '| a | ONE |');
        const check = rewriteRegions(perturbed, (id) => (id === 'fixture' ? body : null));
        return 'text' in check && check.text !== perturbed && check.text === rw.text;
      })()
  );

  // --- determinism controls ---
  ck(
    'rows sort by CODE POINT, not by host collation',
    ['a', 'Z'].sort(byCodePoint).join(',') === 'Z,a'
  );
  ck(
    'a pipe in a cell is escaped, so it cannot shift every column after it',
    render({ ...P, rows: () => [{ key: 'x', cells: ['a|b', 'c'] }] }, [
      { key: 'x', cells: ['a|b', 'c'] },
    ]).some((l) => l.includes('a\\|b'))
  );
  ck(
    'no output embeds a timestamp, a duration or a run id',
    !render(P, P.rows(''))
      .join('\n')
      .match(/\d{4}-\d{2}-\d{2}|\bms\b|run[ -]?id/i)
  );

  // --- THE control this whole phase turns on: a count passes where a set fails. ---
  const before = Array.from({ length: 388 }, (_, i) => `gate-${String(i).padStart(3, '0')}`);
  const after = [...before.slice(88), ...Array.from({ length: 88 }, (_, i) => `new-${i}`)];
  const d = setDiff(before, after);
  ck(
    'a count floor of 300 PASSES over a tree that lost 88 of 388 rows',
    before.length >= 300 && after.length >= 300
  );
  ck('and count EQUALITY passes too, because 88 were swapped, not removed', d.countEqual);
  ck('but the SET diff names all 88 dropped rows', d.missing.length === 88, d.missing.slice(0, 3));
  ck('and reports the 88 additions separately', d.added.length === 88);

  // --- the union control: a provider that VANISHES must not be skipped ---
  const recorded = { gates: { rows: 2, keys: ['x', 'y'] }, gone: { rows: 1, keys: ['z'] } };
  const stillLive = { gates: { rows: 2, keys: ['x', 'y'] } };
  const verdicts = diffAll(recorded, stillLive);
  ck(
    'planted: a provider deleted from the code is still compared to its recorded set',
    verdicts.some((v) => v.id === 'gone' && v.gone && v.missing.join(',') === 'z'),
    verdicts
  );
  ck(
    'and a provider whose rows are unchanged is not accused',
    verdicts.some((v) => v.id === 'gates' && v.missing.length === 0)
  );

  // --- target discovery must not adopt a document that merely QUOTES the marker ---
  ck(
    'planted: a marker quoted inside prose or a table cell is NOT a marker',
    !OPEN_RE.test('| T-2 | scans for a `<!-- >>> gen-docs: fixture -->` marker | why |') &&
      !OPEN_RE.test('the opening form is <!-- >>> gen-docs: fixture --> and it opens a region')
  );
  ck(
    'and a real marker line, alone on its line, still IS one',
    OPEN_RE.test('<!-- >>> gen-docs: fixture -->')
  );
  ck(
    'discovery and parsing use the SAME predicate, so nothing is adopted then refused',
    targets(ROOT).every((f) => {
      const r = findRegions(fs.readFileSync(path.join(ROOT, f), 'utf-8'));
      return 'regions' in r && r.regions.length > 0;
    }),
    targets(ROOT)
  );

  // --- the gate catalogue's source is a FILE now, so prove it refuses a broken one ---
  const refuses = (label: string, body: string | null): void => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gen-docs-lock-'));
    try {
      if (body !== null) {
        fs.mkdirSync(path.join(dir, path.dirname(GATES_LOCK)), { recursive: true });
        fs.writeFileSync(path.join(dir, GATES_LOCK), body);
      }
      let threw = false;
      try {
        readGatesLock(dir);
      } catch {
        threw = true;
      }
      ck(label, threw);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  };
  refuses('planted: a MISSING gates lock is refused, not rendered as an empty catalogue', null);
  refuses('planted: an EMPTY gates lock is refused', '[]\n');
  refuses('planted: a gates lock that is an object, not an array, is refused', '{}\n');
  refuses('planted: a gates lock entry with no id is refused', '[{"ci":{"kind":"step"}}]\n');
  refuses('planted: a gates lock entry with no ci.kind is refused', '[{"id":"check:x"}]\n');
  refuses('planted: a gates lock that is not JSON is refused', 'not json\n');
  ck(
    'and the real lock is accepted, so the refusals above are not refusing everything',
    readGatesLock(ROOT).length > 0
  );

  // --- every provider must actually see the tree ---
  for (const p of PROVIDERS) {
    const rows = p.rows(ROOT);
    ck(`provider "${p.id}" is not vacuous (${rows.length} rows)`, rows.length > 0);
    ck(`provider "${p.id}" has unique keys`, new Set(rows.map((r) => r.key)).size === rows.length);
    ck(
      `provider "${p.id}" is stable across two calls`,
      JSON.stringify(p.rows(ROOT)) === JSON.stringify(rows)
    );
  }

  console.log(bad === 0 ? `${GREEN}selftest: all controls fired${NC}` : `${RED}${bad} failed${NC}`);
  return bad;
}

/* ------------------------------------------------------------------- main */

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest() === 0 ? 0 : 1;
  if (argv.includes('--snapshot')) return writeSnapshot(ROOT, argv.includes('--force'));
  if (argv.includes('--diff-snapshot')) return diffSnapshot(ROOT);

  if (argv.includes('--list')) {
    // A provider that yields nothing is a BROKEN provider, not an empty subject. Every one of
    // the four scans a part of the tree that cannot legitimately be empty: a repository with no
    // gates, no hooks, no BLOCKER mechanism and no `.ci` directory is not this repository. So
    // `--list` reporting `gates 0` and exiting 0 would be a green that means the opposite of
    // what it says, which is the whole shape TRAPS.md is about. Refuse instead.
    let vacuous = 0;
    for (const p of PROVIDERS) {
      const rows = p.rows(ROOT);
      console.log(`${p.id}\t${rows.length}\t${p.scans}`);
      if (rows.length === 0) {
        vacuous += 1;
        console.error(
          `  ${RED}VACUOUS:${NC} provider "${p.id}" scanned the tree and found nothing`
        );
      }
      for (const m of p.missing?.(ROOT) ?? []) {
        console.error(`  ${RED}in the index, absent from the worktree:${NC} ${m}`);
      }
    }
    return vacuous === 0 ? 0 : 1;
  }

  const built = build(ROOT);
  if ('errors' in built) {
    for (const e of built.errors) console.error(`${RED}✗${NC} ${e}`);
    return 1;
  }
  if (built.rendered.length === 0) {
    // A generator with nothing to generate reports success it never earned. Refuse.
    console.error(`${RED}✗${NC} no document carries a \`>>> gen-docs:\` marker.`);
    console.error('  Nothing was checked, so a pass here would mean nothing.');
    return 1;
  }

  const write = argv.includes('--write');
  const drifted: string[] = [];
  for (const r of built.rendered) {
    if (r.next === r.current) {
      if (!write) console.log(`${GREEN}ok${NC}   ${r.file} (${r.providers.join(', ')})`);
      continue;
    }
    if (write) {
      fs.writeFileSync(path.join(ROOT, r.file), r.next);
      console.log(`${GREEN}wrote${NC} ${r.file} (${r.providers.join(', ')})`);
      continue;
    }
    drifted.push(r.file);
    const cur = r.current.split('\n');
    const nxt = r.next.split('\n');
    const i = cur.findIndex((l, n) => l !== nxt[n]);
    console.error(`${RED}DRIFT${NC} ${r.file} first differs at line ${i + 1}`);
    console.error(`       on disk:  ${JSON.stringify(cur[i] ?? '(end of file)')}`);
    console.error(`       derived:  ${JSON.stringify(nxt[i] ?? '(end of file)')}`);
  }
  if (drifted.length > 0) {
    console.error(
      `\n${RED}${drifted.length} file(s) drifted.${NC} Run: npx tsx scripts/gen-docs.ts --write`
    );
    return 1;
  }
  return 0;
}

process.exit(main(process.argv.slice(2)));
