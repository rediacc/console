/**
 * check:ci-fixture-event-timestamps -- a worklist event planted by a test
 * fixture derives its `at` from now, never from a literal date.
 *
 * WHY THIS EXISTS, and it has bitten twice in one wave. The store reader sorts
 * every event by timestamp before folding, which is what makes the union of two
 * machines' histories fold to the same state as one history. Append order
 * stopped being fold order the day the store became a directory.
 *
 * A fixture that plants `{"ev": "state", "s": "x", "at": "2026-08-05T00:00:00Z"}`
 * to close an item added today therefore folds its tick BEFORE the add, where it
 * does nothing at all -- and the case then fails claiming the CODE is wrong.
 * That is what happened to case 189c: it accused a phantom that had in fact been
 * closed, and the accusation was the fixture's own stale date.
 *
 * The sibling failure is expiry rather than ordering: a fixture whose constant
 * date drifts past a retention window makes `scan()` prune the very body it just
 * captured (the report-inbox suite's case 12, same wave). Both are one rule -- a
 * fixture that hard-codes a date is a bomb with a date on it.
 *
 * WHERE THE CORPUS LIVES, and it MOVED. The rule was written against bash: 26
 * case files under .claude/hooks/stop/worklist-cases/ plus the two test-*.sh
 * suites beside them. Commit 4cf6aba3d ported all 28 to pytest modules under
 * .claude/rediacc_hooks/tests/, and the gate's path was not repointed, so it
 * spent that time pointing at a directory that no longer existed. Both original
 * arms land in ONE directory now, which is why there is one path below.
 *
 * SCOPE. Only kinds the ITEM FOLD reads. A `report` or `read` event goes to a
 * different store, and a `bgwait` timestamp is a state-doc field, not an event;
 * policing those would be a false positive, and a guard whose usual outcome is a
 * false positive gets routed around.
 *
 * ---- gate ----
 * step: Fixture event timestamps
 * needs: node
 * selftest: true
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const CASES = path.join(ROOT, '.claude', 'rediacc_hooks', 'tests');

/**
 * Every ported suite, plus the shared harness, in one directory. The old
 * worklist-cases/ arm and the old test-*.sh arm both landed here, so the "scoped
 * to one directory and blind to its sibling" hole this gate carried is closed by
 * the move rather than re-opened by it.
 */
function fixtureFiles(): string[] {
  if (!fs.existsSync(CASES)) return [];
  return fs
    .readdirSync(CASES)
    .filter((n) => n.endsWith('.py') || n.endsWith('.sh'))
    .map((n) => path.join(CASES, n))
    .sort();
}

/** Event kinds the item fold reads. `report` is deliberately absent. */
const FOLDED = ['state', 'lease', 'add', 'md', 'update', 'unlease', 'tomb', 'triage'];
const LITERAL_AT = /["']at["']\s*:\s*["'](\d{4}-\d{2}-\d{2}T[^"']*)["']/;

/** Floor for the corpus: see the VACUOUS refusal in main(). */
const MIN_LITERALS = 30;

/**
 * How far back the enclosing literal's `"ev"` may sit. In bash the whole event
 * was one line, or two after the formatter wrapped it, so a one-line lookback
 * was enough. In the ported pytest fixtures the same event is a `json.dumps({`
 * block with one key per line, and `"at"` commonly sits two to five lines under
 * `"ev"`. A one-line window over THIS corpus finds zero folded events and the
 * gate goes green having seen nothing, which is the failure it exists to name.
 */
const LOOKBACK = 8;

/**
 * The nearest `"ev"` above `i` that is still inside the SAME literal. A `}` ends
 * the walk: a sibling dict's kind is not this one's, and reading across the
 * boundary would attach a folded kind to an out-of-scope event.
 */
export function kindFor(lines: string[], i: number): string | null {
  for (let j = i; j >= 0 && i - j <= LOOKBACK; j--) {
    const line = lines[j] ?? '';
    const ev = /["']ev["']\s*:\s*["']([a-z_]+)["']/.exec(line);
    if (ev) return ev[1] as string;
    if (j < i && line.includes('}')) return null;
  }
  return null;
}

interface Finding {
  file: string;
  line: number;
  ev: string;
  at: string;
}

function scan(files: string[]): Finding[] {
  const out: Finding[] = [];
  for (const f of files) {
    const lines = fs.readFileSync(f, 'utf-8').split('\n');
    lines.forEach((line, i) => {
      if (line.trimStart().startsWith('#')) return; // prose about the rule
      const at = LITERAL_AT.exec(line);
      if (!at) return;
      const ev = kindFor(lines, i);
      if (ev === null || !FOLDED.includes(ev)) return;
      out.push({
        file: path.relative(ROOT, f),
        line: i + 1,
        ev,
        at: at[1] as string,
      });
    });
  }
  return out;
}

function selftest(): void {
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'fxts-'));
  const w = (n: string, b: string): string => {
    const p = path.join(tmp, n);
    fs.writeFileSync(p, b);
    return p;
  };

  // EVERY DECLARED VARIANT, not a sample. The plant is the exact 189c defect, but running it for `state` alone leaves the other seven kinds in FOLDED untested -- and a kind added to that set later would arrive with no control at all. Looping over the set itself makes the set the test plan.
  for (const kind of FOLDED) {
    const bad = w(
      `bad-${kind}.sh`,
      `fh.write(json.dumps({"ev": "${kind}", "id": i, "at": "2026-08-05T00:00:00Z"}))\n`
    );
    const b = scan([bad]);
    if (b.length !== 1 || b[0]?.ev !== kind) {
      console.error(`  FAIL  a literal-dated "${kind}" event was not caught: ${JSON.stringify(b)}`);
      process.exit(1);
    }
  }
  console.log(
    `  PASS  a literal-dated fold event is caught for all ${FOLDED.length} declared kind(s)`
  );

  // Wrapped across two lines, which is how the formatter leaves them.
  const wrapped = w('wrap.sh', '{"ev": "lease", "id": i,\n "at": "2026-01-01T00:00:00Z"}\n');
  if (scan([wrapped]).length !== 1) {
    console.error('  FAIL  the wrapped form was missed, so the matcher is line-blind');
    process.exit(1);
  }
  console.log('  PASS  it reads the kind from the previous line too');

  // THE SHAPE THE REAL CORPUS IS IN: a json.dumps block, one key per line, with `"ev"` several lines above `"at"`. This is the control that would have been red for the whole time the gate pointed at the deleted bash directory.
  const block = w(
    'block.py',
    'handle.write(\n    json.dumps(\n        {\n            "ev": "add",\n            "id": "aaaaaaaa",\n            "by": "deadbeef",\n            "at": "2020-01-01T00:00:00Z",\n        }\n    )\n)\n'
  );
  const blockFound = scan([block]);
  if (blockFound.length !== 1 || blockFound[0]?.ev !== 'add') {
    console.error(
      `  FAIL  the multi-line python block was missed, so the gate is blind on its own corpus: ${JSON.stringify(blockFound)}`
    );
    process.exit(1);
  }
  console.log('  PASS  it reads the kind across a multi-line python literal');

  // CONTROL: the walk stops at `}`, so a folded kind in the PRECEDING literal is never attached to an out-of-scope event that follows it.
  const sibling = w(
    'sibling.py',
    '[\n    {\n        "ev": "add",\n        "at": now,\n    },\n    {\n        "ev": "report",\n        "at": "2026-08-05T10:00:00Z",\n    },\n]\n'
  );
  if (scan([sibling]).length !== 0) {
    console.error('  FAIL  CONTROL: the lookback leaked across a sibling literal boundary');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: the lookback stops at the end of the previous literal');

  // CONTROL: derived from now is the correct shape and must pass.
  const good = w(
    'good.sh',
    'now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")\nfh.write(json.dumps({"ev": "state", "at": now}))\n'
  );
  if (scan([good]).length !== 0) {
    console.error('  FAIL  CONTROL: a now-derived timestamp was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a now-derived timestamp is accepted');

  // CONTROL: a report event lives in a different store and is out of scope.
  const rep = w('rep.sh', '{"ev": "report", "id": "x", "at": "2026-08-05T10:00:00Z"}\n');
  if (scan([rep]).length !== 0) {
    console.error('  FAIL  CONTROL: a report event was policed');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a report event is out of scope');
  fs.rmSync(tmp, { recursive: true, force: true });
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-fixture-event-timestamps: selftest ok (6 controls)');
    return;
  }
  if (!fs.existsSync(CASES)) {
    console.error(`✗ ${path.relative(ROOT, CASES)} does not exist, so this gate checked NOTHING`);
    process.exit(1);
  }
  const files = fixtureFiles();
  if (files.length === 0) {
    console.error('✗ no case files found; refusing a verdict');
    process.exit(1);
  }
  // ANTI-VACUITY: the corpus must actually contain event literals, or the matcher is broken rather than the fixtures being clean.
  const literals = files.reduce(
    (n, f) =>
      n + (fs.readFileSync(f, 'utf-8').match(/["']ev["']\s*:\s*["'][a-z_]+["']/g) ?? []).length,
    0
  );
  // A NAMED FLOOR, not merely "> 0": the quiet collapse is a matcher that
  // still finds a handful after a rename hid the rest. The floor sits well
  // under the real count (89 at the time of writing).
  if (literals < MIN_LITERALS) {
    console.error(
      `✗ VACUOUS: found only ${literals} event literal(s), below the floor of ${MIN_LITERALS}. ` +
        'The matcher is broken, not the tree.'
    );
    process.exit(1);
  }

  const findings = scan(files);
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} fixture event(s) carrying a literal date:\n`);
    for (const f of findings) {
      console.error(`  ${f.file}:${f.line}  "ev": "${f.ev}" with "at": "${f.at}"`);
    }
    console.error(
      '\n  The store reader SORTS by timestamp before folding, so append order is not\n' +
        '  fold order: a tick dated in the past folds before the item it closes and does\n' +
        '  nothing, and the case then blames the code. Derive `at` from now.\n' +
        '  (The sibling failure is expiry: a constant date that drifts past a retention\n' +
        '  window makes the capture prune its own body. Same rule, same fix.)'
    );
    process.exit(1);
  }
  console.log(
    `✓ fixture event timestamps: ${literals} event literal(s) across ${files.length} case file(s); ` +
      'every folded one derives its date from now'
  );
}

main();
