#!/usr/bin/env tsx
/**
 * check:ci-doc-region-parity -- the committed bytes of every `gen-docs` region must equal
 * what the providers would emit RIGHT NOW, and every provider must still be used by one.
 *
 * WHY THIS EXISTS AT ALL, GIVEN gate-test:docs-gen ALREADY RUNS THE GENERATOR.
 *
 * `.ci/scripts/test/gates/test-docs-gen.sh` case A runs `gen-docs` in verify mode and then
 * asserts one thing about the result: `grep -q '^ok '`, i.e. AT LEAST ONE target was named.
 * That is a floor of one over a discovery scan. gen-docs discovers its targets by scanning
 * markdown for a marker line (scripts/gen-docs.ts:119-164) and refuses only when the target
 * list is EMPTY (scripts/gen-docs.ts:571-576). Put those two facts together and a document
 * that loses its markers -- a region replaced by a hand-typed table, a marker mangled by an
 * editor, a file renamed -- simply stops being a target. The generator reports success over
 * the documents that remain, the gate test finds its one `ok` line, and the number that just
 * went back to being hand-typed is green.
 *
 * That is rediacc/console#549 exactly: a generated artifact quietly stops being generated
 * and is believed. So this gate asks the question the generator structurally cannot ask
 * about itself: not "does every region I FOUND still match", but "is the set of regions
 * still the set it is supposed to be". Concretely, over the SET rather than a count:
 *
 *   1. every provider declared in scripts/lib/doc-providers.ts is used by >= 1 region,
 *   2. every provider yields >= 1 row (a provider that scans and finds nothing is broken,
 *      not a subject that is empty -- gen-docs only asserts this under `--list`, which no
 *      gate runs),
 *   3. every region's committed body equals the re-rendered body, attributed to the file,
 *      the provider and the opening marker's line,
 *   4. a line that LOOKS like a marker to a human but does not parse as one is a hard red,
 *      because that region is invisible to the generator and to this gate alike.
 *
 * THE SECOND IMPLEMENTATION IS DELIBERATE. `renderBody` below re-implements the region body
 * that scripts/gen-docs.ts `render()` emits, rather than importing it, for one blunt reason:
 * gen-docs.ts calls `process.exit(main(...))` at module scope with no import guard
 * (scripts/gen-docs.ts:607), so importing anything from it runs the whole generator inside
 * the importer. The duplication is not free and it is not hidden: if gen-docs changes its
 * render format, this gate reds with THE FRAME DIFFERS on every region at once, which reads
 * as "the gate no longer models the emitter" rather than as document drift. That is the
 * loud direction, and the selftest pins the exact emitted shape so it fails here first.
 *
 * ORDER IS LOAD-BEARING, so a MOVE is reported as a move. Every provider sorts its rows
 * deterministically (scripts/lib/doc-providers.ts:44-51 chose `byCodePoint` over
 * `localeCompare` precisely so two machines cannot disagree), and gen-docs states
 * determinism as a requirement rather than a nicety (scripts/gen-docs.ts:45-50). So a region
 * whose rows are the SAME SET in a DIFFERENT ORDER is not a documentation edit: it means a
 * provider's sort changed, or a human reordered generated rows by hand. Both are different
 * defects from a row appearing or vanishing, and the second is the one that is easy to miss
 * inside a 400-row table. Region order WITHIN a file is not generator-owned (an author
 * places the markers and `rewriteRegions` never moves them), so it is not compared.
 *
 * NO `paths:` ON THE MANIFEST ENTRY, DELIBERATELY. The providers scan the gates lock, the
 * hook wiring, every tracked file that carries a `BLOCKER:` and the whole `.ci` tree, so any
 * path list short of "the repository" would be wrong, and a half-populated one makes
 * `--changed` drop this gate silently. An entry without `paths` is always selected.
 *
 * NO `---- gate ----` HEADER, and that is a choice rather than an omission. This gate belongs
 * in quality-code, and .github/workflows/ci-quality.yml:894 records why the sibling gate
 * check:ci-gates-lock declares none either: quality-code HAS a gate-bind region, but 73 of its
 * gates still have hand-written steps outside it, so `gate-bind --write` would emit all 73 into
 * the region and leave the hand-written copies as duplicates. Declaring here would make it the
 * 74th. It joins the region in the W2.6 lane cutover, with the rest. Until then the four
 * registrations are hand-written and check:ci-parity is what proves they agree.
 *
 * The registration this expects, so a reader can check it in one place:
 *   package.json  "check:ci-doc-region-parity":
 *       "tsx scripts/gates/check-doc-region-parity.ts --selftest && tsx scripts/gates/check-doc-region-parity.ts"
 *   manifest      id check:ci-doc-region-parity, gate: true, no paths (see above),
 *                 leaves ['scripts/gates/check-doc-region-parity.ts'],
 *                 ci: step "Doc region parity" in quality-code
 *   workflow      a step named exactly "Doc region parity" in the quality-code job
 *   and the gate test .ci/scripts/test/gates/test-doc-region-parity.sh registered as
 *   gate-test:doc-region-parity, qualityGateTest: true, riding "Quality-gate unit tests".
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { refused } from '../lib/controls.js';
import {
  bootstrapPins,
  byCodePoint,
  ignoredMediaDirs,
  jobLevels,
  mediaPairs,
  PROVIDERS,
  type Provider,
  type ProviderRow,
  parseWorkflow,
  portedVerbs,
  providerById,
  pyConst,
  pyFunctionBody,
  topVerbs,
} from '../lib/doc-providers.js';
import { findRegions, OPEN_RE, type Region } from '../lib/doc-regions.js';

const HERE = import.meta.dirname;
const REPO = path.resolve(HERE, '..', '..');

/**
 * The provider module AS TEXT, resolved against this script and never against `--root`.
 *
 * The text scan below is an independent reading of the very module this file imported, so
 * it has to be the same file on disk. Resolving it under `--root` would compare the
 * imported providers against some other checkout's source and call the disagreement a
 * finding.
 */
const PROVIDER_SOURCE = path.join(HERE, '../lib', 'doc-providers.ts');
const PROVIDER_SOURCE_REL = 'scripts/lib/doc-providers.ts';

/** gen-docs skips anything larger; mirrored so the two agree on what a target is. */
const MAX_TARGET_BYTES = 4 * 1024 * 1024;

/* -------------------------------------------------------------- rendering */

/** Same escaping as scripts/gen-docs.ts: `|` ends a cell, a newline ends the row. */
const cell = (s: string): string => s.replace(/\|/g, '\\|').replace(/[\r\n]+/g, ' ');

/**
 * The body scripts/gen-docs.ts `render()` writes between the markers.
 *
 * SECOND IMPLEMENTATION, see the header. `selftest` pins this shape line by line, so a
 * change to the emitter's format fails there before it can be mistaken for doc drift.
 */
export function renderBody(p: Provider, rows: readonly ProviderRow[]): string[] {
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

/* ---------------------------------------------------------------- regions */

/** A comment line immediately after the opening marker is PROSE, and is preserved. */
const COMMENT_RE = /^<!--/;

/**
 * The half-open line range a generator owns inside one region.
 *
 * The leading run of comment lines is skipped by the same rule `rewriteRegions` uses
 * (scripts/lib/doc-regions.ts:129-132). Reimplementing that rule differently is how a gate
 * comes to compare a body against a body-plus-prose and call it drift.
 */
export function bodyRange(
  lines: readonly string[],
  region: Region
): { start: number; end: number } {
  let i = region.open + 1;
  while (i < region.close && COMMENT_RE.test(lines[i] ?? '')) i += 1;
  return { start: i, end: region.close };
}

/**
 * A line a human reads as a marker.
 *
 * WHOLE-LINE ON PURPOSE. docs/ci-overhaul/07-tooling-decisions.md:30 quotes the marker
 * syntax inside a table cell, and gen-docs already paid for treating that as a target
 * (scripts/gen-docs.ts:142-154). A quotation has text around it, so requiring the line to be
 * nothing but the comment keeps this from re-adopting the document that explains the idiom,
 * while still catching the dangerous case: a marker that is indented, or misspelt, or that
 * names a provider with a character `OPEN_RE` does not accept. Those are regions the
 * generator cannot see, and an unseen region is the whole failure class.
 */
const LOOKS_LIKE_MARKER = /^\s*<!--\s*>>>\s*gen-docs:.*-->\s*$/;

/** Lines that read as an opening marker but do not parse as one, 1-based. */
export function nearMissMarkers(text: string): { line: number; raw: string }[] {
  const out: { line: number; raw: string }[] = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i] ?? '';
    if (LOOKS_LIKE_MARKER.test(raw) && !OPEN_RE.test(raw)) out.push({ line: i + 1, raw });
  }
  return out;
}

/* ------------------------------------------------------------ row classify */

export interface BodyDelta {
  /** Table rows the tree supports that the document does not carry. */
  added: string[];
  /** Table rows the document carries that the tree no longer supports. */
  removed: string[];
  /** Rows present on both sides whose POSITION changed. */
  moved: string[];
  /** The non-row scaffolding: the `Scans:` line, the header, the separator, the count. */
  frameChanged: boolean;
  frameDisk: string[];
  frameDerived: string[];
  /** Same rows, different order, and nothing else touched. */
  pureMove: boolean;
  identical: boolean;
  /** How many data rows the DERIVED body carries, printed so a collapse is visible. */
  rows: number;
}

const SEPARATOR = /^\|\s*-{3}/;

/**
 * Split a region body into its table ROWS and the frame around them.
 *
 * The header row and the `|---|` separator are FRAME, not rows: they come from
 * `p.columns`, so a change there is a column change and reporting it as "a row was added
 * and another removed" would name the wrong defect. Everything after the separator that
 * starts with `|` is a data row.
 */
function split(lines: readonly string[]): { frame: string[]; rows: string[] } {
  const sep = lines.findIndex((l) => SEPARATOR.test(l));
  if (sep === -1) return { frame: [...lines], rows: [] };
  const frame = lines.slice(0, sep + 1);
  const rows: string[] = [];
  for (const l of lines.slice(sep + 1)) {
    if (l.startsWith('|')) rows.push(l);
    else frame.push(l);
  }
  return { frame, rows };
}

const counts = (xs: readonly string[]): Map<string, number> => {
  const m = new Map<string, number>();
  for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1);
  return m;
};

/**
 * How the committed body differs from the derived one, in the words a reader needs.
 *
 * ORDER-AWARE, for the reason in the header: a row that merely MOVED is reported as a move
 * and never as one addition plus one removal, because "the document is stale" and "the
 * provider's sort changed" are different problems.
 */
export function classifyBody(disk: readonly string[], derived: readonly string[]): BodyDelta {
  const a = split(disk);
  const b = split(derived);
  const inA = counts(a.rows);
  const inB = counts(b.rows);

  const added = b.rows.filter((r) => (inA.get(r) ?? 0) === 0);
  const removed = a.rows.filter((r) => (inB.get(r) ?? 0) === 0);

  // Compare the two sequences restricted to the rows they share. Any position that
  // disagrees there is a genuine reordering rather than a consequence of an add or a drop.
  const commonA = a.rows.filter((r) => (inB.get(r) ?? 0) > 0);
  const commonB = b.rows.filter((r) => (inA.get(r) ?? 0) > 0);
  const moved: string[] = [];
  for (let i = 0; i < Math.min(commonA.length, commonB.length); i++) {
    if (commonA[i] !== commonB[i]) moved.push(commonA[i] ?? '');
  }

  const frameChanged = a.frame.join('\n') !== b.frame.join('\n');
  return {
    added,
    removed,
    moved,
    frameChanged,
    frameDisk: a.frame,
    frameDerived: b.frame,
    pureMove: added.length === 0 && removed.length === 0 && moved.length > 0 && !frameChanged,
    identical: disk.join('\n') === derived.join('\n'),
    rows: b.rows.length,
  };
}

/* ------------------------------------------------------------ corpus floor */

export interface ProviderCorpus {
  /** `id: '...'` lines inside the provider objects. */
  ids: string[];
  /** `export const <name>Provider: Provider = {` declarations. */
  declared: string[];
  /** Names listed inside the exported `PROVIDERS` array. */
  registered: string[];
}

/**
 * Three independent TEXT readings of the module this file IMPORTED.
 *
 * NO NUMBER IS WRITTEN DOWN ANYWHERE IN THIS GATE, which is the point. A hand-typed floor
 * is the artifact the whole gen-docs phase exists to abolish, and scripts/gen-gates-lock.ts
 * records what a typed one is worth: its `MIN_ENTRIES = 300` sat 120 below the live count,
 * so it could not have fired on any realistic truncation, and its own comment had already
 * drifted. Cross-reading the same file three ways and demanding all three agree with the
 * imported array needs no constant, and catches the three ways this can go wrong: a
 * truncated file, a provider declared but never registered, and a stale module cache
 * serving an array the source no longer describes.
 */
export function providerCorpus(source: string): ProviderCorpus {
  const ids = [...source.matchAll(/^ {2}id: '([a-z0-9-]+)',?$/gm)].map((m) => m[1] ?? '');
  const declared = [...source.matchAll(/^export const (\w+Provider)\s*:\s*Provider\s*=/gm)].map(
    (m) => m[1] ?? ''
  );
  const arr = /^export const PROVIDERS\s*:[^=]*=\s*\[([^\]]*)\]/m.exec(source);
  const registered = [...(arr?.[1] ?? '').matchAll(/(\w+Provider)/g)].map((m) => m[1] ?? '');
  return { ids, declared, registered };
}

/* ---------------------------------------------------------------- targets */

/**
 * Every markdown file the generator could adopt, tracked and untracked.
 *
 * Mirrors scripts/gen-docs.ts:119-131 including the untracked leg: this repo's standing
 * rule is that work stays uncommitted, so a document that exists only in the working tree
 * is the normal case rather than the exception.
 */
function markdownFiles(root: string): string[] {
  const list = (args: string[]): string[] =>
    execFileSync('git', ['-C', root, 'ls-files', '-z', ...args], {
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    })
      .split('\0')
      .filter((f) => f !== '');
  return [
    ...new Set([
      ...list(['--', '*.md']),
      ...list(['--others', '--exclude-standard', '--', '*.md']),
    ]),
  ].sort(byCodePoint);
}

interface Finding {
  where: string;
  what: string;
  detail: string[];
}

/* --------------------------------------------------------------- the scan */

interface Audit {
  scanned: number;
  targets: string[];
  regions: { file: string; region: Region; delta: BodyDelta }[];
  findings: Finding[];
}

function audit(root: string): Audit {
  const findings: Finding[] = [];
  const targets: string[] = [];
  const regions: { file: string; region: Region; delta: BodyDelta }[] = [];
  const rowsCache = new Map<string, ProviderRow[]>();
  const bodyCache = new Map<string, string[]>();
  let scanned = 0;

  for (const rel of markdownFiles(root)) {
    const abs = path.join(root, rel);
    let st: fs.Stats;
    try {
      st = fs.statSync(abs);
    } catch {
      continue; // in the index, gone from the worktree; see doc-providers.ts on section 5b
    }
    if (!st.isFile()) continue;
    scanned += 1;
    const text = fs.readFileSync(abs, 'utf-8');

    for (const nm of nearMissMarkers(text)) {
      findings.push({
        where: `${rel}:${nm.line}`,
        what: 'a line reads as an opening marker but does not parse as one',
        detail: [
          `on disk: ${JSON.stringify(nm.raw)}`,
          'The generator will not see this region, so its contents are hand-typed and',
          'unchecked. The accepted form is exactly `<!-- >>> gen-docs: <provider> -->`',
          'with no indentation and a lower-case provider id.',
        ],
      });
    }

    const hasMarker = text.split('\n').some((l) => OPEN_RE.test(l));
    if (!hasMarker) continue;

    if (st.size > MAX_TARGET_BYTES) {
      findings.push({
        where: rel,
        what: `carries a marker but is ${st.size} bytes, over the ${MAX_TARGET_BYTES} limit`,
        detail: [
          'scripts/gen-docs.ts:141 skips files this large, so its regions are never',
          'rewritten and never verified. Split the document or move the region.',
        ],
      });
      continue;
    }
    targets.push(rel);

    const found = findRegions(text);
    if ('errors' in found) {
      for (const e of found.errors) {
        findings.push({ where: `${rel}:${e.line}`, what: e.message, detail: [] });
      }
      continue;
    }

    const lines = text.split('\n');
    for (const region of found.regions) {
      const p = providerById(region.provider);
      if (p === undefined) {
        findings.push({
          where: `${rel}:${region.open + 1}`,
          what: `no provider named "${region.provider}" exists`,
          detail: [`known providers: ${PROVIDERS.map((q) => q.id).join(', ')}`],
        });
        continue;
      }
      let rows = rowsCache.get(p.id);
      if (rows === undefined) {
        rows = p.rows(root);
        rowsCache.set(p.id, rows);
      }
      let body = bodyCache.get(p.id);
      if (body === undefined) {
        body = renderBody(p, rows);
        bodyCache.set(p.id, body);
      }
      const { start, end } = bodyRange(lines, region);
      regions.push({ file: rel, region, delta: classifyBody(lines.slice(start, end), body) });
    }
  }
  return { scanned, targets, regions, findings };
}

/* --------------------------------------------------------------- selftest */

const P = (id: string, rows: ProviderRow[]): Provider => ({
  id,
  scans: 'a fixture',
  columns: ['A', 'B'],
  rows: () => rows,
});

function selftest(): number {
  let bad = 0;
  const ck = (label: string, ok: boolean, detail?: unknown): void => {
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${label}\n`);
    if (!ok) {
      bad += 1;
      process.stdout.write(`        ${JSON.stringify(detail)}\n`);
    }
  };

  const row = (k: string, v: string): ProviderRow => ({ key: k, cells: [k, v] });
  const p = P('fixture', [row('a', 'one'), row('b', 'two'), row('c', 'three')]);
  const body = renderBody(p, p.rows(''));

  // --- the emitted SHAPE, pinned line by line. This is what makes the second
  // --- implementation honest: if scripts/gen-docs.ts render() changes, this fails HERE,
  // --- rather than surfacing as every region in the tree drifting at once.
  ck(
    'the rendered body has the exact shape gen-docs writes',
    body[0] === '' &&
      body[1] === 'Scans: a fixture.' &&
      body[2] === '' &&
      body[3] === '| A | B |' &&
      body[4] === '|---|---|' &&
      body[5] === '| a | one |' &&
      body[body.length - 3] === '' &&
      body[body.length - 2] ===
        '3 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.' &&
      body[body.length - 1] === '',
    body
  );
  ck(
    'a pipe inside a cell is escaped, so it cannot shift every column after it',
    renderBody(p, [{ key: 'x', cells: ['a|b', 'c'] }]).some((l) => l.includes('a\\|b'))
  );

  // --- BOTH DIRECTIONS on the comparison itself ---
  ck('CONTROL: an unchanged body reports no difference', classifyBody(body, body).identical);
  ck(
    'CONTROL: a body that differs only in trailing prose OUTSIDE the region is not our business',
    classifyBody(body, body).added.length === 0 && classifyBody(body, body).removed.length === 0
  );

  const perturbed = body.map((l) => (l === '| a | one |' ? '| a | ONE |' : l));
  const d1 = classifyBody(perturbed, body);
  ck(
    'a hand-edited row is reported as one added and one removed row',
    !d1.identical &&
      d1.added.join('|') === '| a | one |' &&
      d1.removed.join('|') === '| a | ONE |' &&
      !d1.pureMove,
    d1
  );

  // THE CONTROL THIS GATE TURNS ON. Same rows, different order: every count is equal, every
  // set is equal, and only an order-aware comparison can see it.
  const reordered = renderBody(p, [row('b', 'two'), row('a', 'one'), row('c', 'three')]);
  const d2 = classifyBody(reordered, body);
  ck(
    'REORDERED rows are reported as a MOVE, not as an add plus a remove',
    !d2.identical && d2.pureMove && d2.added.length === 0 && d2.removed.length === 0,
    d2
  );
  ck('and the moved rows are named', d2.moved.length === 2, d2.moved);
  ck(
    'CONTROL: the counts a naive check would compare are EQUAL across that move',
    split(reordered).rows.length === split(body).rows.length &&
      new Set(split(reordered).rows).size === new Set(split(body).rows).size
  );

  const dropped = renderBody(p, [row('a', 'one'), row('c', 'three')]);
  const d3 = classifyBody(dropped, body);
  ck(
    'a row the document lost is reported as ADDED by the tree, and no move is invented',
    d3.added.join('|') === '| b | two |' && d3.removed.length === 0 && d3.moved.length === 0,
    d3
  );
  const extra = renderBody(p, [...p.rows(''), row('z', 'ghost')]);
  const d4 = classifyBody(extra, body);
  ck(
    'a row the tree no longer supports is reported as REMOVED',
    d4.removed.join('|') === '| z | ghost |' && d4.added.length === 0,
    d4
  );
  const recolumned = renderBody({ ...p, columns: ['A', 'CHANGED'] }, p.rows(''));
  const d5 = classifyBody(recolumned, body);
  ck(
    'a COLUMN change is reported as the frame, not as every row being added and removed',
    d5.frameChanged && d5.added.length === 0 && d5.removed.length === 0,
    d5
  );
  const recounted = body.map((l) => (l.includes('row(s).') ? '99 row(s). Generated by x' : l));
  ck(
    'a hand-edited row COUNT line is caught even though every row matches',
    classifyBody(recounted, body).frameChanged
  );

  // --- region parsing and the body range ---
  const doc = [
    '# title',
    '',
    '<!-- >>> gen-docs: fixture -->',
    '<!-- explanatory prose that belongs to the author -->',
    ...body,
    '<!-- <<< gen-docs -->',
    '',
    'hand-written tail',
  ];
  const parsed = findRegions(doc.join('\n'));
  ck('a region is found in a document that carries one', 'regions' in parsed);
  if ('regions' in parsed) {
    const r = parsed.regions[0];
    const range = r === undefined ? { start: 0, end: 0 } : bodyRange(doc, r);
    ck(
      'the body range starts AFTER the preserved prose, exactly as rewriteRegions does',
      doc[range.start] === '' && doc[range.start + 1] === 'Scans: a fixture.',
      { range, at: doc[range.start] }
    );
    ck(
      'and the sliced body compares identical to the derived one',
      classifyBody(doc.slice(range.start, range.end), body).identical
    );
  }
  ck(
    'planted: an unterminated region is refused',
    'errors' in findRegions('<!-- >>> gen-docs: fixture -->\nbody')
  );
  ck(
    'planted: a nested region is refused',
    'errors' in
      findRegions(
        [
          '<!-- >>> gen-docs: fixture -->',
          '<!-- >>> gen-docs: other -->',
          '<!-- <<< gen-docs -->',
          '<!-- <<< gen-docs -->',
        ].join('\n')
      )
  );

  // --- near-miss markers: the ones a human reads and the generator cannot ---
  ck(
    'planted: an INDENTED marker is a near miss, because the generator will not see it',
    nearMissMarkers('  <!-- >>> gen-docs: fixture -->').length === 1
  );
  ck(
    'planted: a marker naming an UPPER-CASE provider is a near miss',
    nearMissMarkers('<!-- >>> gen-docs: Fixture -->').length === 1
  );
  ck(
    'CONTROL: a real marker is NOT reported as a near miss',
    nearMissMarkers('<!-- >>> gen-docs: fixture -->').length === 0
  );
  // The document that DOCUMENTS the marker must not be adopted or accused. gen-docs paid
  // for this one already (scripts/gen-docs.ts:142-154); both predicates have to agree.
  ck(
    'CONTROL: a marker QUOTED inside a table cell is neither a marker nor a near miss',
    nearMissMarkers('| T-2 | scans for a `<!-- >>> gen-docs: fixture -->` marker | why |')
      .length === 0 &&
      !OPEN_RE.test('| T-2 | scans for a `<!-- >>> gen-docs: fixture -->` marker | why |')
  );
  ck(
    'CONTROL: a marker quoted mid-sentence is neither',
    nearMissMarkers('the opening form is <!-- >>> gen-docs: fixture --> and it opens a region')
      .length === 0
  );

  // --- the corpus reading of the provider source ---
  const fakeSource = [
    'export const oneProvider: Provider = {',
    "  id: 'one',",
    '};',
    'export const twoProvider: Provider = {',
    "  id: 'two',",
    '};',
    'export const PROVIDERS: readonly Provider[] = [oneProvider, twoProvider];',
  ].join('\n');
  const fc = providerCorpus(fakeSource);
  ck(
    'the corpus scan reads ids, declarations and registrations out of a source',
    fc.ids.join(',') === 'one,two' &&
      fc.declared.join(',') === 'oneProvider,twoProvider' &&
      fc.registered.join(',') === 'oneProvider,twoProvider',
    fc
  );
  const orphan = providerCorpus(fakeSource.replace(', twoProvider]', ']'));
  ck(
    'planted: a provider DECLARED but never registered is visible as a shortfall',
    orphan.declared.length === 2 && orphan.registered.length === 1,
    orphan
  );
  const truncated = providerCorpus(fakeSource.split('\n').slice(0, 3).join('\n'));
  ck(
    'planted: a truncated source reads as fewer ids than the import exports',
    truncated.ids.length === 1 && truncated.registered.length === 0,
    truncated
  );
  ck(
    'planted: an EMPTY source yields nothing, which the floor treats as fatal',
    providerCorpus('').ids.length === 0
  );

  // ------------------------------------------------------------------ W11 P5a
  //
  // THE FOUR PROVIDERS ADDED IN W11 P5a PARSE FOREIGN LANGUAGES: two bash
  // dispatchers, two workflow YAMLs, two sync scripts and a Python module. A
  // parser is where a provider goes silently wrong, because a scan that matches
  // NOTHING renders as a shorter table rather than as an error, and a shorter
  // table reads as a smaller subject. These controls exercise the exported
  // helpers directly, in BOTH directions: something that must be found, and
  // something that must NOT be.

  /**
   * The refusal fired. A parser that returns an EMPTY answer where it should throw is the
   * failure mode these controls exist for, so every refusal is asserted rather than assumed.
   */
  const refusesToParse = (f: () => unknown): boolean => {
    try {
      f();
      return false;
    } catch {
      return true;
    }
  };

  const DISPATCH = [
    'main() {',
    '    case "${1:-}" in',
    '        provision) exec x ;;',
    '        setup | --setup) do_setup ;;',
    '        devbox)',
    '            case "$2" in',
    '                1) inner ;;',
    '                shell) do_shell ;;',
    '            esac',
    '            ;;',
    '        # commented) not a verb',
    '        "") show_help ;;',
    '        *) fallback ;;',
    '    esac',
    '}',
  ].join('\n');
  const verbs = topVerbs(DISPATCH);
  ck(
    'topVerbs reads the top-level arms of a dispatcher, aliases included',
    verbs.join(',') === 'devbox,provision,setup',
    verbs
  );
  // The trap .ci/scripts/test/gates/test-run-sh.sh:177-179 names: an inner `case`
  // whose arms sit at the SAME indent as a real subcommand. An indentation rule
  // reports `1` and `shell` as verbs; a depth rule cannot.
  ck('CONTROL: an INNER case arm is not a top-level verb', !verbs.includes('shell'), verbs);
  ck('CONTROL: a numeric inner arm is not a verb', !verbs.includes('1'), verbs);
  ck('CONTROL: a commented arm is not a verb', !verbs.includes('commented'), verbs);
  ck(
    'CONTROL: the fallback and the bare-verb default are not verbs',
    !verbs.includes('*') && !verbs.includes('') && !verbs.includes('--setup'),
    verbs
  );
  ck(
    'planted: a dispatcher with no main() is refused',
    refusesToParse(() => topVerbs('case x in\nesac'))
  );

  ck(
    'portedVerbs reads a multi-line table and skips its comments',
    portedVerbs('PORTED_VERBS=(\n    setup # ported W6\n    # quality is next\n    test\n)').join(
      ','
    ) === 'setup,test'
  );
  // ZERO IS NOT A FAILURE HERE, and this control is the reason the provider has no
  // floor. `PORTED_VERBS` is empty until the first verb moves (run.sh:37-39 says
  // so), and a floor would have been red for the whole programme.
  ck(
    'CONTROL: an EMPTY ported table is zero rows, not a refusal',
    portedVerbs('PORTED_VERBS=()').length === 0
  );
  ck(
    'planted: no PORTED_VERBS table at all is refused',
    refusesToParse(() => portedVerbs('nothing here'))
  );

  ck(
    'bootstrapPins keeps only the *_VERSION a pin file actually defines',
    bootstrapPins('uses ${UV_VERSION} and $GHOST_VERSION', 'UV_VERSION=1.2\nOTHER_VERSION=9\n')
      .map(([k, v]) => `${k}=${v}`)
      .join(',') === 'UV_VERSION=1.2'
  );

  const WF = [
    'on:',
    '  push:',
    '  workflow_dispatch:',
    'jobs:',
    '  init:',
    '    runs-on: ubuntu-latest',
    '  quality:',
    '    needs: [init]',
    '    uses: ./.github/workflows/ci-quality.yml',
    '  build:',
    '    needs:',
    '      - init',
    '      - quality',
    '  # needs: [ghost]',
    '  done:',
    '    needs: build',
  ].join('\n');
  const wf = parseWorkflow('w.yml', WF);
  ck(
    'parseWorkflow finds every job and its triggers',
    wf.jobs.length === 4 && wf.triggers.join(',') === 'push,workflow_dispatch',
    wf
  );
  ck(
    'parseWorkflow reads inline, block and scalar `needs:` alike',
    JSON.stringify(wf.jobs.map((j) => j.needs)) === '[[],["init"],["init","quality"],["build"]]',
    wf.jobs
  );
  ck(
    'parseWorkflow records the reusable workflow a job calls',
    wf.jobs[1]?.uses === '.github/workflows/ci-quality.yml'
  );
  ck('CONTROL: a COMMENTED needs is not an edge', !JSON.stringify(wf.jobs).includes('ghost'));
  const lv = jobLevels(wf);
  ck(
    'jobLevels turns `needs:` back into the stage chain',
    [...lv.entries()].map(([k, v]) => `${k}=${v}`).join(',') === 'init=0,quality=1,build=2,done=3',
    [...lv.entries()]
  );
  ck(
    'planted: a needs naming a job that does not exist is refused',
    refusesToParse(() => jobLevels(parseWorkflow('w.yml', 'jobs:\n  a:\n    needs: [nope]\n')))
  );
  ck(
    'planted: a needs cycle is refused rather than rendered at an invented stage',
    refusesToParse(() =>
      jobLevels(parseWorkflow('w.yml', 'jobs:\n  a:\n    needs: [b]\n  b:\n    needs: [a]\n'))
    )
  );

  const push = mediaPairs('    sync_dir "$REPO_ROOT/packages/www/public/x/" "x/"\n', true);
  const pull = mediaPairs('    restore_dir "x/" "$REPO_ROOT/packages/www/public/x/"\n', false);
  ck(
    'mediaPairs reads both argument orders to the same pair',
    push.get('packages/www/public/x') === 'x' && pull.get('packages/www/public/x') === 'x',
    [[...push], [...pull]]
  );
  ck(
    'ignoredMediaDirs takes directory excludes and nothing else',
    ignoredMediaDirs('public/a/\n!public/b/\n*.debug/\npublic/c.txt\n# note\n').join(',') ===
      'packages/www/public/a'
  );

  const PY = [
    'CONST = 42',
    '',
    'def render(rec):',
    '    lines.append("## Why")',
    '',
    'def other():',
    '    pass',
  ].join('\n');
  ck(
    'pyFunctionBody stops at the next top-level def',
    !pyFunctionBody(PY, 'render').includes('pass')
  );
  ck('pyConst reads a module-level assignment', pyConst(PY, 'CONST') === '42');
  ck(
    'planted: a renamed function is refused',
    refusesToParse(() => pyFunctionBody(PY, 'gone'))
  );
  ck(
    'planted: a renamed constant is refused',
    refusesToParse(() => pyConst(PY, 'GONE'))
  );

  // --- the corpus scan must work on the REAL module it imported ---
  const real = providerCorpus(fs.readFileSync(PROVIDER_SOURCE, 'utf-8'));
  ck(
    `the real ${PROVIDER_SOURCE_REL} reads back the ids the import exports`,
    real.ids.length > 0 &&
      real.ids.slice().sort(byCodePoint).join(',') ===
        PROVIDERS.map((q) => q.id)
          .slice()
          .sort(byCodePoint)
          .join(','),
    { text: real.ids, imported: PROVIDERS.map((q) => q.id) }
  );
  ck(
    'and its declarations and registrations agree with that count',
    real.declared.length === PROVIDERS.length && real.registered.length === PROVIDERS.length,
    real
  );

  process.stdout.write(
    bad === 0
      ? `  ${PROVIDERS.length} provider(s) known; all controls fired.\n`
      : `  ${bad} control(s) FAILED.\n`
  );
  return bad;
}

/* ------------------------------------------------------------------- main */

function usageRoot(argv: string[]): string {
  const i = argv.indexOf('--root');
  if (i === -1) return REPO;
  const v = argv[i + 1];
  if (v === undefined || v.startsWith('--')) {
    process.stderr.write('--root needs a directory\n');
    process.exit(1);
  }
  return path.resolve(v);
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) {
    const bad = selftest();
    process.stdout.write(
      `${bad === 0 ? 'OK' : 'FAILED'}  check-doc-region-parity selftest: ${bad} failure(s)\n`
    );
    return bad === 0 ? 0 : 1;
  }

  // Controls before the verdict, same order and same reason as scripts/gen-gates-lock.ts:
  // a report from an instrument that cannot fail is worse than no report.
  if (selftest() !== 0) {
    return refused(
      'CONTROL FAILED: this gate cannot detect drift, so it refuses to rule on the docs.'
    );
  }

  const root = usageRoot(argv);
  const out: string[] = [];
  const pass = (line: string): void => {
    out.push(`  PASS  ${line}`);
  };
  const fail: string[] = [];

  process.stdout.write(`check:ci-doc-region-parity  root=${root}\n`);

  // 1. THE FLOOR, corpus-derived. Four readings of one module, no typed number.
  const corpus = providerCorpus(fs.readFileSync(PROVIDER_SOURCE, 'utf-8'));
  const importedIds = PROVIDERS.map((p) => p.id);
  if (
    corpus.ids.length === 0 ||
    corpus.declared.length !== importedIds.length ||
    corpus.registered.length !== importedIds.length ||
    corpus.ids.slice().sort(byCodePoint).join(',') !==
      importedIds.slice().sort(byCodePoint).join(',')
  ) {
    return refused(
      `VACUOUS: ${PROVIDER_SOURCE_REL} does not read back as the module this gate imported.`,
      `  imported PROVIDERS : ${importedIds.length} [${importedIds.join(', ')}]`,
      `  id: lines in text  : ${corpus.ids.length} [${corpus.ids.join(', ')}]`,
      `  declared in text   : ${corpus.declared.length} [${corpus.declared.join(', ')}]`,
      `  registered in text : ${corpus.registered.length} [${corpus.registered.join(', ')}]`,
      '  These are independent readings of one file and they must agree. A shortfall means',
      '  the file was truncated, a provider was declared and never registered, or a stale',
      '  module is being served. Any of those makes a green here mean nothing.'
    );
  }
  pass(
    `provider corpus agrees four ways: ${importedIds.length} imported, ` +
      `${corpus.declared.length} declared, ${corpus.registered.length} registered, ` +
      `${corpus.ids.length} id line(s) in ${PROVIDER_SOURCE_REL}`
  );

  const a = audit(root);

  /**
   * The structural findings ride along with EVERY refusal below, not only with the verdict.
   *
   * They were reported last at first, and the fixture in the gate test showed what that costs:
   * indenting one marker made the only region unparseable, so the run refused with "no region
   * parsed" and swallowed the line that explained WHY. A refusal that withholds the cause reads
   * as a broken gate rather than a broken document.
   */
  const dumpFindings = (): void => {
    for (const f of a.findings) {
      process.stderr.write(`  ${f.where}: ${f.what}\n`);
      for (const d of f.detail) process.stderr.write(`    ${d}\n`);
    }
  };

  // 2. ANTI-VACUITY on the scan itself. Zero of anything here is a broken instrument, never
  //    an empty subject: a repository with no markdown, or no generated region, is not this
  //    repository, and a green over nothing is exactly the shape this gate exists to refuse.
  if (a.scanned === 0) {
    return refused(
      `VACUOUS: no markdown file was read under ${root}.`,
      '  The gate is not seeing the tree, so its green would mean nothing.'
    );
  }
  if (a.targets.length === 0) {
    process.stderr.write(
      `VACUOUS: ${a.scanned} markdown file(s) were read and NONE carries a gen-docs marker.\n` +
        '  Either every generated region was lost, or discovery is broken. Both are the\n' +
        '  failure this gate exists for, so neither is a pass.\n'
    );
    dumpFindings();
    return 1;
  }
  if (a.regions.length === 0) {
    process.stderr.write(
      `VACUOUS: ${a.targets.length} target(s) carry a marker but no region parsed.\n`
    );
    dumpFindings();
    return 1;
  }
  pass(
    `${a.scanned} markdown file(s) read, ${a.targets.length} carry a marker, ` +
      `${a.regions.length} region(s) parsed`
  );

  // 3. EVERY PROVIDER IS STILL USED. This is the check gen-docs cannot make about itself:
  //    it verifies the regions it FINDS, so a document that loses its markers stops being
  //    checked rather than failing.
  const used = new Set(a.regions.map((r) => r.region.provider));
  const unused = importedIds.filter((id) => !used.has(id));
  if (unused.length > 0) {
    fail.push(
      `${unused.length} provider(s) are defined and used by NO region: ${unused.join(', ')}\n` +
        '    Either a document lost its markers, in which case the numbers it used to\n' +
        '    generate are now hand-typed and unchecked, or the provider is dead and should\n' +
        `    be deleted from ${PROVIDER_SOURCE_REL}. Do not leave it half-wired.`
    );
  } else {
    pass(`every provider is used by a region: ${importedIds.join(', ')}`);
  }

  // 4. EVERY PROVIDER STILL SEES SOMETHING. gen-docs asserts this only under `--list`,
  //    which no gate runs, so an empty provider would render an empty table and verify
  //    clean against it forever.
  const empties: string[] = [];
  const shape: string[] = [];
  for (const p of PROVIDERS) {
    const n = p.rows(root).length;
    shape.push(`${p.id} ${n}`);
    if (n === 0) empties.push(p.id);
  }
  if (empties.length > 0) {
    fail.push(
      `${empties.length} provider(s) scanned the tree and found NOTHING: ${empties.join(', ')}\n` +
        '    An empty provider renders an empty table, and an empty table verifies clean\n' +
        '    against a document that quotes it. Fix the provider, do not accept the zero.'
    );
  } else {
    pass(`every provider yields rows: ${shape.join(', ')}`);
  }

  // 5. Structural findings: near-miss markers, unknown providers, unterminated regions.
  for (const f of a.findings) {
    fail.push(`${f.where}: ${f.what}${f.detail.map((d) => `\n    ${d}`).join('')}`);
  }

  // 6. PARITY, region by region, order-aware.
  for (const { file, region, delta } of a.regions) {
    const at = `${file}:${region.open + 1}`;
    if (delta.identical) {
      pass(`${at}  region \`${region.provider}\` matches (${delta.rows} row(s))`);
      continue;
    }
    const lines: string[] = [];
    if (delta.pureMove) {
      lines.push(
        `    MOVED ${delta.moved.length} row(s): the same rows in a different ORDER.`,
        '    This is not a stale document. Either a provider stopped sorting the way it',
        '    used to, or generated rows were reordered by hand. Both are worth reading,',
        '    which is why this is not reported as an add plus a remove.',
        `    first moved row: ${delta.moved[0] ?? ''}`
      );
    } else {
      if (delta.frameChanged) {
        const i = delta.frameDisk.findIndex((l, n) => l !== delta.frameDerived[n]);
        lines.push(
          '    THE FRAME DIFFERS (the `Scans:` line, the columns, or the row count):',
          `      on disk:  ${JSON.stringify(delta.frameDisk[i] ?? '(end of region)')}`,
          `      derived:  ${JSON.stringify(delta.frameDerived[i] ?? '(end of region)')}`
        );
      }
      for (const r of delta.added.slice(0, 10))
        lines.push(`    + the tree has, the doc lacks: ${r}`);
      if (delta.added.length > 10) lines.push(`    + ...and ${delta.added.length - 10} more`);
      for (const r of delta.removed.slice(0, 10))
        lines.push(`    - the doc has, the tree lacks: ${r}`);
      if (delta.removed.length > 10) lines.push(`    - ...and ${delta.removed.length - 10} more`);
      for (const r of delta.moved.slice(0, 5)) lines.push(`    ~ also MOVED: ${r}`);
    }
    fail.push(
      `${at}  region \`${region.provider}\` does not match what gen-docs would emit\n` +
        lines.join('\n') +
        '\n    Fix: npx tsx scripts/gen-docs.ts --write, in the SAME change as the edit that' +
        '\n    moved it. Do not hand-edit between the markers.'
    );
  }

  for (const line of out) process.stdout.write(`${line}\n`);
  if (fail.length > 0) {
    process.stderr.write(`\n${fail.length} finding(s):\n\n`);
    for (const f of fail) process.stderr.write(`  ${f}\n\n`);
    return 1;
  }

  // The shape, not just the verdict, so a reader can see when a number collapses.
  process.stdout.write(
    `OK  ${a.regions.length} region(s) in ${a.targets.length} file(s) match what gen-docs ` +
      `would emit; ${importedIds.length}/${importedIds.length} provider(s) used; ` +
      `${a.scanned} markdown file(s) scanned.\n`
  );
  process.stdout.write(`    targets: ${a.targets.join(', ')}\n`);
  process.stdout.write(`    rows per provider: ${shape.join(', ')}\n`);
  process.stdout.write(
    '    Blind spot, stated so the green is not read as more than it is: this proves the\n' +
      '    documents match the PROVIDERS, not that a provider measures the right thing.\n'
  );
  return 0;
}

// THE IMPORT GUARD. This module exports its helpers so a control can drive them directly.
// Without the guard, importing one would run the whole gate inside the importer and exit,
// which is what scripts/gen-docs.ts:607 does today and why this file cannot import it.
if (path.resolve(process.argv[1] ?? '') === path.resolve(import.meta.filename)) {
  process.exit(main(process.argv.slice(2)));
}
