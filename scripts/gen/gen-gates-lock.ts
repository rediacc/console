#!/usr/bin/env tsx
/**
 * check:ci-gates-lock -- emit `scripts/ci-runner/gates.lock.json` from the manifest, and
 * refuse when the committed lock and the manifest disagree.
 *
 * WHY A LOCK AT ALL. `scripts/ci-runner/manifest.ts` is TypeScript, and three things read
 * it as TEXT rather than as data because they are not TypeScript and cannot import it:
 * `.claude/hooks/stop/wl_reggate.py`, `.ci/scripts/quality/check-gate-id-convention.sh`
 * and `.ci/scripts/quality/check_test_file_orphans.py`. Every one of them re-implements a
 * fragment of a TS parser against a 5,700-line literal, and each fragment is wrong in its
 * own direction the first time an entry is written in a shape it did not anticipate. The
 * lock is the machine-readable projection those readers should have had: one file, one
 * parse, no regex archaeology.
 *
 * ORDER IS LOAD-BEARING, which is why this emits an ARRAY and never an object keyed by
 * id. `scripts/ci-runner/pool.ts` breaks scheduling ties on the array INDEX, so two gates
 * of equal cost run in manifest file order. Serialising to an object would preserve
 * insertion order in practice and lose it the first time anything sorted the keys --
 * silently, and visible only as a scheduling change nobody could attribute.
 *
 * WHY THE EMITTER AND ITS CHECKER ARE ONE FILE. Invariant 1: anything that becomes
 * generated takes its checker with it, in the same change. rediacc/console#549 is the
 * failure class -- a generated artifact whose regeneration nobody verified drifted from
 * its source and was believed for weeks. Default mode VERIFIES; `--write` regenerates.
 *
 * WHAT THIS DOES NOT DO YET, stated so a green is not read as more than it is: the three
 * text readers above still parse `manifest.ts`. This lands the artifact and the guarantee
 * that it is faithful; draining those readers onto it is W2.4 and is a separate change,
 * because each one needs its own both-direction control against the reader it replaces.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { GATES, type GateSpec } from '../ci-runner/manifest.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LOCK = 'scripts/ci-runner/gates.lock.json';

/**
 * ANTI-VACUITY, CORPUS-DERIVED. An empty or truncated `GATES` would serialise, compare
 * equal to an equally empty lock, and report success having verified nothing.
 *
 * THIS WAS A HAND-TYPED `MIN_ENTRIES = 300`, and it was wrong twice over: 120 below the
 * live count, so it could not fire on any realistic truncation, and its own comment had
 * already drifted (it said 410 while the lock held 420). Driver contract section 6 says a
 * floor must be set-based or corpus-derived and never a typed count, and a floor that
 * cannot fire is the exact thing this gate exists to refuse in others.
 *
 * The corpus is the manifest read as TEXT, which is a genuinely independent measure of
 * the same subject: the import could break while the file is intact, or the file could be
 * truncated while a stale module cache serves the old array. Requiring the two to agree
 * catches both, and needs no number.
 */
function manifestIdCount(): number {
  const text = fs.readFileSync(path.join(REPO, 'scripts/ci-runner/manifest.ts'), 'utf-8');
  return new Set(text.match(/^\s*id: '([^']+)'/gm) ?? []).size;
}

/** The lock's bytes for a given gate list. Pretty-printed, so a diff is readable. */
export function render(gates: readonly GateSpec[]): string {
  return `${JSON.stringify(gates, null, 2)}\n`;
}

/**
 * What a drift looks like, in the words a reader needs.
 *
 * ORDER-AWARE ON PURPOSE: an entry that merely MOVED is reported as a move, not as one
 * addition and one removal, because "the lock is stale" and "the schedule changed" are
 * different problems and the second is the one that is easy to miss.
 */
export function describeDrift(committed: string, fresh: string): string[] {
  if (committed === fresh) return [];
  const ids = (text: string): string[] => {
    try {
      const parsed: unknown = JSON.parse(text);
      return Array.isArray(parsed) ? parsed.map((g) => String((g as GateSpec).id)) : [];
    } catch {
      return [];
    }
  };
  const a = ids(committed);
  const b = ids(fresh);
  const setA = new Set(a);
  const setB = new Set(b);
  const out: string[] = [];
  const added = b.filter((id) => !setA.has(id));
  const removed = a.filter((id) => !setB.has(id));
  for (const id of added) out.push(`+ ${id} is in the manifest and not in the lock`);
  for (const id of removed) out.push(`- ${id} is in the lock and not in the manifest`);
  if (added.length === 0 && removed.length === 0) {
    const moved = a.filter((id, i) => b[i] !== id);
    if (moved.length > 0) {
      out.push(
        `~ same ${a.length} gate(s), different ORDER (${moved.length} moved, first: ${moved[0]}).`
      );
      out.push('  pool.ts breaks scheduling ties on the array index, so order is behaviour.');
    } else {
      out.push('~ same ids in the same order, so a FIELD changed inside one or more entries.');
    }
  }
  return out;
}

function selftest(): number {
  let bad = 0;
  const ck = (label: string, ok: boolean, detail?: unknown): void => {
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${label}\n`);
    if (!ok) {
      bad += 1;
      process.stdout.write(`        ${JSON.stringify(detail)}\n`);
    }
  };

  const g = (id: string): GateSpec => ({ id, run: 'true', gate: true }) as GateSpec;
  const base = render([g('a'), g('b'), g('c')]);

  ck('an unchanged lock reports no drift', describeDrift(base, base).length === 0);
  ck(
    'a gate added to the manifest is named as an addition',
    describeDrift(base, render([g('a'), g('b'), g('c'), g('d')]))
      .join('|')
      .includes('+ d')
  );
  ck(
    'a gate removed from the manifest is named as a removal',
    describeDrift(base, render([g('a'), g('b')]))
      .join('|')
      .includes('- c')
  );
  // THE CONTROL THAT MATTERS. Reordering changes no id and no field, so a set-based comparison reports "no difference" -- while pool.ts schedules differently.
  ck(
    'REORDERING is caught, and reported as order rather than as add+remove',
    describeDrift(base, render([g('a'), g('c'), g('b')]))
      .join('|')
      .includes('different ORDER')
  );
  ck(
    'a changed FIELD inside an entry is caught even though the ids match',
    describeDrift(base, render([g('a'), g('b'), { ...g('c'), slow: true } as GateSpec]))
      .join('|')
      .includes('a FIELD changed')
  );
  ck(
    'CONTROL: render is deterministic, so a no-op regeneration cannot report drift',
    render([g('a'), g('b')]) === render([g('a'), g('b')])
  );
  ck(
    'CONTROL: the renderer emits an ARRAY, never an id-keyed object that would lose order',
    render([g('a')])
      .trimStart()
      .startsWith('[')
  );
  return bad;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) {
    const bad = selftest();
    process.stdout.write(`${bad === 0 ? '✓' : '✗'} gen-gates-lock selftest: ${bad} failure(s)\n`);
    return bad === 0 ? 0 : 1;
  }

  // Controls before the verdict, same order and same reason as every other gate here: a report from an instrument that cannot fail is worse than no report.
  if (selftest() !== 0) {
    process.stderr.write(
      'CONTROL FAILED: gen-gates-lock cannot detect drift, so it refuses to rule on the lock.\n'
    );
    return 1;
  }

  const inText = manifestIdCount();
  if (GATES.length !== inText) {
    process.stderr.write(
      `✗ VACUOUS: the manifest EXPORTS ${GATES.length} gate(s) but its text declares ` +
        `${inText} id(s).\n` +
        '  These are two independent readings of one file and they must agree. A shortfall\n' +
        '  means the import broke or a stale module is being served; an excess means the\n' +
        '  text scan is blind to a shape it should see. Either way the lock about to be\n' +
        '  written would not describe the manifest, and a green here would mean nothing.\n'
    );
    return 1;
  }
  if (inText === 0) {
    process.stderr.write(
      '✗ VACUOUS: the manifest text declares no ids at all, so agreement proves nothing.\n'
    );
    return 1;
  }

  const fresh = render(GATES);
  const abs = path.join(REPO, LOCK);

  if (argv.includes('--write')) {
    const before = fs.existsSync(abs) ? fs.readFileSync(abs, 'utf-8') : '';
    if (before === fresh) {
      process.stdout.write(`gen-gates-lock: ${LOCK} already matches (${GATES.length} gate(s))\n`);
      return 0;
    }
    fs.writeFileSync(abs, fresh);
    process.stdout.write(
      `gen-gates-lock: wrote ${LOCK} (${GATES.length} gate(s) in manifest file order)\n`
    );
    return 0;
  }

  if (!fs.existsSync(abs)) {
    process.stderr.write(
      `✗ ${LOCK} does not exist. Generate it with \`npm run gen:gates-lock\`.\n` +
        '  It is committed on purpose: the readers that cannot parse TypeScript need a\n' +
        '  file that is there on a fresh checkout, not one produced by a build step.\n'
    );
    return 1;
  }

  const committed = fs.readFileSync(abs, 'utf-8');
  const drift = describeDrift(committed, fresh);
  if (drift.length > 0) {
    process.stderr.write(`✗ ${LOCK} disagrees with scripts/ci-runner/manifest.ts:\n\n`);
    for (const line of drift) process.stderr.write(`    ${line}\n`);
    process.stderr.write(
      '\n  The manifest is the source. Run `npm run gen:gates-lock` to regenerate,\n' +
        '  and commit the lock in the SAME change as the manifest edit that moved it.\n'
    );
    return 1;
  }

  process.stdout.write(`✓ ${LOCK} matches the manifest: ${GATES.length} gate(s), same order.\n`);
  process.stdout.write(
    '  Blind spot: this proves the lock is a faithful PROJECTION of the manifest, not that\n' +
      '  the manifest is right. All three former text readers now read this file instead\n' +
      '  (drained 2026-09-06); the note that said otherwise outlived the work it described.\n'
  );
  return 0;
}

// THE IMPORT GUARD. This module exports `render` and `describeDrift` so the lock's consumers and its tests can use them; without the guard, importing either would run the whole gate and `process.exit` inside the importer.
if (path.resolve(process.argv[1] ?? '') === path.resolve(fileURLToPath(import.meta.url))) {
  process.exit(main(process.argv.slice(2)));
}
