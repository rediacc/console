"""The truncated findings list in `scripts/lib/findings-report.ts`, proved in both directions.

WHY IT NEEDS ITS OWN CONTROL. Twenty-one gates print their failure lists through that one module, which makes it a shared point of failure in the way `runControls` is: if `truncatedLines` ever dropped its tail, every one of those gates would start truncating SILENTLY at once, and a truncated list that says nothing about the rest reads as the whole list. Six of the hand-rolled copies it replaced already did exactly that, so the tail is the property this file pins hardest.

THE BOUNDARY IS TESTED FROM BOTH SIDES. N items under a limit of N must print no tail (a tail there would be a false "more"), and N+1 must print exactly "... and 1 more". A test of only the far side (30 items, limit 25) would pass an off-by-one in either direction.

THE EXIT CODE IS A SEPARATE PROCESS, because `refuseFindings` calls `process.exit(1)` and would take the verdict probe down with it. That run also proves the report goes to STDERR and nothing reaches stdout: a red that lands on stdout is lost by any caller piping it somewhere.

WHY `tsx -` READING STDIN, for the reason `test_gate_gate_header.py` records: the probe imports a path relative to the CWD, and a temp file run from elsewhere would die on the import before a single control ran. Nothing is written into the tree.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MOD = paths.from_root("scripts", "lib", "findings-report.ts")

# A floor, not a count: the verdicts are read back from what ran. It only refuses a probe that has lost most of its cases.
MIN_VERDICTS = 12

PROBE_TS = r"""import {
  printTruncated,
  reportFindings,
  truncatedLines,
} from './scripts/lib/findings-report.js';

let bad = 0;
const ck = (label: string, ok: boolean, detail?: unknown): void => {
  console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
  if (!ok) {
    bad += 1;
    console.log(`\t\t${JSON.stringify(detail)}`);
  }
};
const items = (n: number) => Array.from({ length: n }, (_, i) => `item-${i}`);
const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const throws = (f: () => unknown) => {
  try {
    f();
    return false;
  } catch {
    return true;
  }
};

let got = truncatedLines(items(3), { limit: 3 });
ck('exactly N items under a limit of N: every item, and NO tail', eq(got, ['    item-0', '    item-1', '    item-2']), got);

got = truncatedLines(items(4), { limit: 3 });
ck('N+1 items: the first N, then exactly "... and 1 more"', eq(got, ['    item-0', '    item-1', '    item-2', '    ... and 1 more']), got);

got = truncatedLines(items(30), { limit: 25 });
ck('30 under 25: 25 items and a tail counting the 5 hidden', got.length === 26 && got[24] === '    item-24' && got[25] === '    ... and 5 more', got);

got = truncatedLines(items(2), { limit: 0 });
ck('a limit of 0 still says how many it hid', eq(got, ['    ... and 2 more']), got);

got = truncatedLines(items(40), { limit: Infinity });
ck('Infinity prints every item and no tail (an --all flag)', got.length === 40 && !got.some((l) => l.includes('more')), got.length);

got = truncatedLines([], { limit: 5 });
ck('an empty list is empty: no tail claiming a negative or zero remainder', eq(got, []), got);

got = truncatedLines([{ k: 'a' }, { k: 'b' }, { k: 'c' }], {
  limit: 2,
  indent: '  ',
  format: (x) => [`~ ${x.k}`, `  old: ${x.k}`],
  more: (n) => `... and ${n} more modified keys`,
});
ck(
  'indent, multi-line format and custom tail all apply, the tail indented like the items',
  eq(got, ['  ~ a', '    old: a', '  ~ b', '    old: b', '  ... and 1 more modified keys']),
  got
);

ck('a negative limit is refused, not read as slice(0, -n)', throws(() => truncatedLines(items(5), { limit: -2 })));
ck('a NaN limit is refused', throws(() => truncatedLines(items(5), { limit: Number.NaN })));
ck('a fractional limit is refused', throws(() => truncatedLines(items(5), { limit: 2.5 })));

const w: string[] = [];
printTruncated(items(3), { limit: 1, write: (l) => w.push(l) });
ck('printTruncated writes one line per call through the given writer', eq(w, ['    item-0', '    ... and 2 more']), w);

const r: string[] = [];
const code = reportFindings({
  header: ['HEADER one', 'HEADER two'],
  items: items(3),
  limit: 2,
  remedy: 'REMEDY',
  write: (l) => r.push(l),
});
ck(
  'reportFindings: header, truncated list, remedy, in that order, and returns 1',
  code === 1 && eq(r, ['HEADER one', 'HEADER two', '    item-0', '    item-1', '    ... and 1 more', 'REMEDY']),
  { code, r }
);

const e: string[] = [];
const ecode = reportFindings({ header: 'H', items: [], limit: 5, write: (l) => e.push(l) });
ck('reportFindings with NO findings still returns 1 and says it was handed nothing', ecode === 1 && e.length === 2 && e[1].includes('no findings'), { ecode, e });

console.log(`TOTAL\t${bad}`);
"""

EXIT_TS = r"""import { refuseFindings } from './scripts/lib/findings-report.js';
refuseFindings({ header: 'HEADER', items: ['a', 'b', 'c'], limit: 2, remedy: 'REMEDY' });
console.log('UNREACHABLE: refuseFindings returned');
"""


def _tsx(source: str) -> harness.RunResult:
    npx = harness.require_tool("npx", "install node; tsx is resolved through npx")
    return harness.run([npx, "tsx", "-"], cwd=paths.repo_root(), stdin=source)


def test_the_subject_is_present(gate):
    """A missing module would make every probe below die on its import, which is a red for the wrong reason."""
    if not MOD.is_file():
        gate.log_fail("%s is missing, so there is nothing to test" % MOD)
    gate.log_pass("findings-report.ts is present")


def test_truncation_both_directions(gate):
    result = _tsx(PROBE_TS)
    if result.rc != 0:
        gate.log_fail("the probe did not run (exit %d), so it asserted nothing" % result.rc, result)
    lines = result.out.splitlines()
    totals = [line for line in lines if line.startswith("TOTAL\t")]
    if not totals:
        gate.log_fail("the probe printed no TOTAL line: it never reached its end", result)
    verdicts = [line for line in lines if line.startswith(("PASS\t", "FAIL\t"))]
    if len(verdicts) < MIN_VERDICTS:
        gate.log_fail(
            "only %d verdict(s), below the floor of %d: the probe has shrunk"
            % (len(verdicts), MIN_VERDICTS),
            result,
        )
    failed = [line for line in lines if line.startswith("FAIL\t")]
    if failed or totals[0] != "TOTAL\t0":
        gate.log_fail("findings-report controls failed:\n%s" % result.out)
    gate.log_pass("%d truncation control(s) behaved" % len(verdicts))


def test_refuse_findings_exits_1_on_stderr(gate):
    result = _tsx(EXIT_TS)
    gate.assert_exit(1, result, "refuseFindings must exit 1")
    gate.assert_not_contains(
        result.out, "UNREACHABLE", "refuseFindings returned instead of exiting"
    )
    gate.assert_eq(result.out, "", "the report must not reach stdout")
    gate.assert_eq(
        result.err,
        "HEADER\n    a\n    b\n    ... and 1 more\nREMEDY\n",
        "the report on stderr must be the header, two items, the tail and the remedy",
    )
    gate.log_pass("refuseFindings exits 1 with the whole report on stderr")
