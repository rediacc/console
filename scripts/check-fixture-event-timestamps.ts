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
 * That is what happened to 18-identity.sh case 189c: it accused a phantom that
 * had in fact been closed, and the accusation was the fixture's own stale date.
 *
 * The sibling failure is expiry rather than ordering: a fixture whose constant
 * date drifts past a retention window makes `scan()` prune the very body it just
 * captured (test-report-inbox.sh case 12, same wave). Both are one rule -- a
 * fixture that hard-codes a date is a bomb with a date on it.
 *
 * SCOPE. Only kinds the ITEM FOLD reads, in the worklist case files. A `report`
 * event goes to a different store, and a `bgwait` timestamp is a state-doc
 * field, not an event; policing those would be a false positive, and a guard
 * whose usual outcome is a false positive gets routed around.
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const CASES = path.join(ROOT, '.claude', 'hooks', 'stop', 'worklist-cases');

/** Event kinds the item fold reads. `report` is deliberately absent. */
const FOLDED = ['state', 'lease', 'add', 'md', 'update', 'unlease', 'tomb', 'triage'];
const LITERAL_AT = /["']at["']\s*:\s*["'](\d{4}-\d{2}-\d{2}T[^"']*)["']/;

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
      // The kind may sit on this line or the one before it: these literals are
      // wrapped by the formatter, and reading only one line missed exactly the
      // shape that bit 189c.
      const ctx = `${lines[i - 1] ?? ''}\n${line}`;
      const ev = /["']ev["']\s*:\s*["']([a-z_]+)["']/.exec(ctx);
      if (!ev || !FOLDED.includes(ev[1] as string)) return;
      out.push({ file: path.relative(ROOT, f), line: i + 1, ev: ev[1] as string, at: at[1] as string });
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

  // THE PLANT: the exact 189c defect.
  const bad = w('bad.sh', 'fh.write(json.dumps({"ev": "state", "id": i, "at": "2026-08-05T00:00:00Z"}))\n');
  const b = scan([bad]);
  if (b.length !== 1 || b[0]?.ev !== 'state') {
    console.error(`  FAIL  a literal-dated state event was not caught: ${JSON.stringify(b)}`);
    process.exit(1);
  }
  console.log('  PASS  a literal-dated fold event is caught, and named');

  // Wrapped across two lines, which is how the formatter leaves them.
  const wrapped = w('wrap.sh', '{"ev": "lease", "id": i,\n "at": "2026-01-01T00:00:00Z"}\n');
  if (scan([wrapped]).length !== 1) {
    console.error('  FAIL  the wrapped form was missed, so the matcher is line-blind');
    process.exit(1);
  }
  console.log('  PASS  it reads the kind from the previous line too');

  // CONTROL: derived from now is the correct shape and must pass.
  const good = w('good.sh', 'now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")\nfh.write(json.dumps({"ev": "state", "at": now}))\n');
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
    console.log('check-fixture-event-timestamps: selftest ok (4 controls)');
    return;
  }
  if (!fs.existsSync(CASES)) {
    console.error(`✗ ${path.relative(ROOT, CASES)} does not exist, so this gate checked NOTHING`);
    process.exit(1);
  }
  const files = fs
    .readdirSync(CASES)
    .filter((n) => n.endsWith('.sh'))
    .map((n) => path.join(CASES, n));
  if (files.length === 0) {
    console.error('✗ no case files found; refusing a verdict');
    process.exit(1);
  }
  // ANTI-VACUITY: the corpus must actually contain event literals, or the
  // matcher is broken rather than the fixtures being clean.
  const literals = files.reduce(
    (n, f) => n + (fs.readFileSync(f, 'utf-8').match(/["']ev["']\s*:\s*["'][a-z_]+["']/g) ?? []).length,
    0,
  );
  if (literals === 0) {
    console.error('✗ found no event literals in the case files; the matcher is broken');
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
        '  window makes the capture prune its own body. Same rule, same fix.)',
    );
    process.exit(1);
  }
  console.log(
    `✓ fixture event timestamps: ${literals} event literal(s) across ${files.length} case file(s); ` +
      'every folded one derives its date from now',
  );
}

main();
