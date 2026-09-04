/**
 * check:ci-worklist-event-builders -- every worklist event that RECONSTRUCTS an
 * item's state must come from the one shared builder.
 *
 * ---- gate ----
 * step: Worklist event builders
 * needs: none
 * why: a second hand-rolled snapshot builder silently reopened finished work
 * ---- /gate ----
 *
 * WHY THIS EXISTS, and it is not hypothetical. `compact()` and the store
 * importer each built their own "minimal set of events that folds back to the
 * current state". The two copies diverged in the way that mattered: both
 * re-emitted a `lease` event for any item still carrying `until`/`worker`, and
 * the fold's lease arm sets state `">"` unconditionally -- so a DONE item that
 * had once been leased came back as in-flight. Measured on this repo's own
 * store on 2026-09-04: 39 of 189 items flipped `[x]` -> `[>]`, taking the open
 * count from 5 to 44. Every compaction of the event log had been quietly
 * reopening old work.
 *
 * WHAT MADE IT INVISIBLE, which is the part worth gating. Each path produced
 * individually plausible output, and the suite checked what each operation did
 * rather than that only one path exists to do it. A gate on outputs cannot see
 * this class; a gate on the STRUCTURE can.
 *
 * THE RULE. Inside .claude/hooks/stop, an object literal whose `ev` is a
 * state-bearing kind (`lease`, `add`, `state`, `md`) may be constructed only
 * inside a function on the allowlist below. Everything else must call
 * `snapshot_events()`. The allowlist is this file's own, not the code's, which
 * is what stops the gate re-asking a question the code already answers: adding
 * a new emitter means editing THIS file and saying why.
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIR = path.join(ROOT, '.claude', 'hooks', 'stop');

/** `ev` values that carry item STATE. A record that only reports (a brief, a
 *  request, a report) cannot resurrect an item, so it is out of scope. */
const STATEFUL = new Set(['lease', 'add', 'state', 'md']);

/**
 * The only functions permitted to construct a stateful event, each with the
 * reason it is not a rebuild. A rebuild -- reconstructing an item's state from
 * a fold -- belongs in snapshot_events and nowhere else.
 */
const ALLOWED: Record<string, string> = {
  snapshot_events: 'THE shared builder: the one place a fold becomes events again',
  load: 'the markdown mirror: its `md` event describes the FILE on disk, diffed against the store, never a fold rebuild',
  add_item: 'the --add verb: a genuinely new item, with a fresh id',
  set_state: 'the --tick/--defer verbs: one real state change to one named item',
  lease_item: 'the --lease verb: a real, newly created lease, not a re-emitted one',
  migrate_items:
    'the --migrate verb: its `add` is a NEW item and its `state` closes the original; both are real changes, not a reconstruction',
};

/** Floor for the corpus: see the VACUOUS refusal in main(). */
const MIN_EMISSIONS = 10;

interface Finding {
  file: string;
  line: number;
  fn: string;
  ev: string;
}

/** The enclosing `def name(` for a line, or "<module>". Python indentation makes
 *  this a backward scan for the nearest def at a lower indent. */
function enclosingFn(lines: string[], idx: number): string {
  const indentOf = (s: string): number => s.length - s.trimStart().length;
  let want = indentOf(lines[idx] ?? '');
  for (let i = idx; i >= 0; i -= 1) {
    const line = lines[i] ?? '';
    if (!line.trim()) continue;
    const ind = indentOf(line);
    if (ind < want) {
      const m = /^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/.exec(line);
      if (m) return m[1] as string;
      want = ind;
    }
  }
  return '<module>';
}

function scan(files: string[]): Finding[] {
  const out: Finding[] = [];
  for (const f of files) {
    const lines = fs.readFileSync(f, 'utf-8').split('\n');
    lines.forEach((line, i) => {
      // `"ev": "lease"` and `"ev":"lease"`, the two spellings this tree uses.
      const m = /["']ev["']\s*:\s*["']([a-z_]+)["']/.exec(line);
      if (!m) return;
      const ev = m[1] as string;
      if (!STATEFUL.has(ev)) return;
      const fn = enclosingFn(lines, i);
      if (fn in ALLOWED) return;
      out.push({ file: path.relative(ROOT, f), line: i + 1, fn, ev });
    });
  }
  return out;
}

function selftest(): void {
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'wleb-'));
  const clean = path.join(tmp, 'clean.py');
  fs.writeFileSync(
    clean,
    [
      'def snapshot_events(fold):',
      '    out = []',
      '    out.append({"ev": "lease", "id": 1})',
      '    return out',
      '',
    ].join('\n')
  );
  if (scan([clean]).length !== 0) {
    console.error('  FAIL  CONTROL: the shared builder itself was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: an emission inside the shared builder is allowed');

  // EVERY DECLARED VARIANT, not a sample. The plant is the exact defect -- a
  // second rebuild path of its own -- but running it for `lease` alone leaves
  // the rest of STATEFUL untested, and a kind added to that set later would
  // arrive with no control. The set is the test plan.
  for (const kind of STATEFUL) {
    const planted = path.join(tmp, `planted-${kind}.py`);
    fs.writeFileSync(
      planted,
      [
        'def some_other_rebuild(fold):',
        '    out = []',
        '    for r in fold.items:',
        `        out.append({"ev": "${kind}", "id": r["id"]})`,
        '    return out',
        '',
      ].join('\n')
    );
    const found = scan([planted]);
    if (found.length !== 1 || found[0]?.fn !== 'some_other_rebuild' || found[0]?.ev !== kind) {
      console.error(
        `  FAIL  the planted "${kind}" builder was NOT caught: ${JSON.stringify(found)}`
      );
      process.exit(1);
    }
  }
  console.log(
    `  PASS  a second hand-rolled builder is caught for all ${STATEFUL.size} stateful kind(s)`
  );

  // A non-stateful event must not be policed: over-blocking teaches people to
  // route around the gate, which is how a guard dies.
  const brief = path.join(tmp, 'brief.py');
  fs.writeFileSync(
    brief,
    ['def anything(x):', '    return {"ev": "brief", "by": x}', ''].join('\n')
  );
  if (scan([brief]).length !== 0) {
    console.error('  FAIL  CONTROL: a non-stateful event was policed');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a report-only event is out of scope');
  fs.rmSync(tmp, { recursive: true, force: true });
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-worklist-event-builders: selftest ok (3 controls)');
    return;
  }
  if (!fs.existsSync(DIR)) {
    console.error(`✗ ${path.relative(ROOT, DIR)} does not exist, so this gate checked NOTHING`);
    process.exit(1);
  }
  const files = fs
    .readdirSync(DIR)
    .filter((n) => n.endsWith('.py'))
    .map((n) => path.join(DIR, n));

  // ANTI-VACUITY: no inputs is a failure, not a pass. A gate that scanned an
  // empty set and said nothing is the shape this repo keeps paying for.
  if (files.length === 0) {
    console.error('✗ no python sources found under .claude/hooks/stop; refusing a verdict');
    process.exit(1);
  }
  const emissions = files.reduce((n, f) => {
    const src = fs.readFileSync(f, 'utf-8');
    return n + (src.match(/["']ev["']\s*:\s*["'][a-z_]+["']/g) ?? []).length;
  }, 0);
  // A NAMED FLOOR, not merely "> 0": the quiet collapse is a matcher that
  // still finds a handful after a rename hid the rest. The floor sits well
  // under the real count (26 at the time of writing).
  if (emissions < MIN_EMISSIONS) {
    console.error(
      `✗ VACUOUS: found only ${emissions} event emission(s), below the floor of ${MIN_EMISSIONS}. ` +
        'The matcher is broken, not the tree.'
    );
    process.exit(1);
  }

  const findings = scan(files);
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} event emission(s) outside the shared builder:\n`);
    for (const f of findings) {
      console.error(`  ${f.file}:${f.line}  ${f.fn}() constructs an "${f.ev}" event`);
    }
    console.error(
      '\n  A function that reconstructs item state from a fold must call snapshot_events().\n' +
        '  Two copies of that shape already diverged once: both re-emitted a lease for an\n' +
        '  item carrying until/worker, and the fold reads a lease as ">", so finished work\n' +
        '  came back as in-flight (39 of 189 items, 2026-09-04).\n' +
        '  If this really is a new legitimate emitter, add it to ALLOWED in\n' +
        '  scripts/check-worklist-event-builders.ts with the reason it is not a rebuild.'
    );
    process.exit(1);
  }
  console.log(
    `✓ worklist event builders: ${emissions} emission(s) across ${files.length} file(s); ` +
      `every stateful one is inside ${Object.keys(ALLOWED).length} allowed function(s)`
  );
}

main();
