"""Port of `.ci/scripts/test/gates/test-gate-header.sh`, retired in W7 P5.

The per-gate DECLARATION parser in `scripts/lib/gate-header.ts`, proved in both directions.

WHY IT NEEDS ITS OWN GATE. That module is the single source the gate binder derives every registration from -- id, run command, lane, needs. A parser that silently returns `null` makes the binder emit NOTHING for that gate, which reads exactly like "this gate has no declaration yet" and is the vacuity shape this repo keeps paying
for. So the NEGATIVES matter as much as the positives: no block, an UNTERMINATED
block, and a block with no step must each be null for a STATED reason rather than by accident.

The two inference cases are the ones that cost CI time. `--recurse-submodules` in a gate placed in a lane without submodules is exactly how `check:ci-docker-npm-pins` lost the file it exists to scan (job 100870135489), and `check_syncpack_sources.py` carries the identical scar from its own first run.

THE PROBE IS THE TWIN'S, CHARACTER FOR CHARACTER, and it is embedded here rather than lifted out of the twin at runtime. Reading it from `test-gate-header.sh` would make this module stop working the day W7 P5 deletes that file, which is the one event the whole port exists to survive. The duplication is therefore deliberate and temporary, and it is why the checks below are on the
probe's OWN output rather than on a re-implementation of the parser: the port drives the same TypeScript against the same module and replays each verdict line as a control.

WHY `tsx -` READING STDIN RATHER THAN A TEMP FILE. The probe imports `./scripts/lib/gate-header.js`, a path relative to the CWD. Written to a temp file and run from there, that import resolves against the temp directory and the run dies before a single control executes -- the same failure mode the layout-overflow twin records from its own first draft. Fed on stdin with `cwd` at the
repo root, the relative import resolves exactly as it does for every other consumer.

THREE REFUSALS ARE KEPT, and each is a different way this could go quiet:
  1. no TOTAL line   -> the probe never reached its end, so nothing was asserted;
  2. TOTAL non-zero  -> the parser is wrong, and the failing labels are named;
  3. fewer than 13 verdict lines -> the probe has SHRUNK. This floor is the twin's,
     and its comment is worth keeping: the line used to read "13 assertion(s)" as a
     hard-coded count, and every case added to the probe made that a lie no gate
     could catch. The count is read back from what actually ran; the floor only
     stops the probe collapsing to nothing.

NO `xdist_group`. Both cases are one short-lived `npx tsx` subprocess reading two tracked files; nothing is written, nothing is bound, no module global is mutated.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MOD = paths.from_root("scripts", "lib", "gate-header.ts")

# The floor the twin spells `((ASSERTED < 13))`. Not a count of what the probe has today -- that is read back from the run -- only a refusal of a probe that has lost most of its cases.
MIN_VERDICTS = 13

PROBE_TS = r"""import {
  analyzeGateHeader,
  derivedId,
  derivedRun,
  headerError,
  inferredNeeds,
  parseGateHeader,
} from './scripts/lib/gate-header.js';

let bad = 0;
const ck = (label: string, ok: boolean, detail?: unknown): void => {
  console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
  if (!ok) {
    bad += 1;
    console.log(`\t\t${JSON.stringify(detail)}`);
  }
};

const py = [
  '# ---- gate ----',
  '# step: Dockerfile npm pins',
  '# needs: submodules, python-yaml',
  '# slow: true   # measured 7s',
  '# ---- end gate ----',
].join('\n');
const h = parseGateHeader(py);
ck(
  'a # header parses, and a trailing note is not part of the value',
  h?.step === 'Dockerfile npm pins' &&
    h?.slow === true &&
    h?.needs.join(',') === 'submodules,python-yaml',
  h
);
ck(
  'a docstring header parses too',
  parseGateHeader(' * ---- gate ----\n * step: X\n * ---- end gate ----')?.step === 'X'
);
ck(
  'a // header parses too',
  parseGateHeader('// ---- gate ----\n// step: X\n// ---- end gate ----')?.step === 'X'
);
ck('CONTROL: no block at all is null', parseGateHeader('print("hi")') === null);
ck(
  'an UNTERMINATED block is null, never read to EOF',
  parseGateHeader('# ---- gate ----\n# step: X\nprint("code")') === null
);
ck(
  'a block with no step is null',
  parseGateHeader('# ---- gate ----\n# needs: node\n# ---- end gate ----') === null
);
ck(
  'needs: none means no needs',
  parseGateHeader('# ---- gate ----\n# step: X\n# needs: none\n# ---- end gate ----')?.needs
    .length === 0
);

ck(
  'id derives for a python check',
  derivedId('.ci/scripts/quality/check_docker_npm_pins.py') === 'check:ci-docker-npm-pins',
  derivedId('.ci/scripts/quality/check_docker_npm_pins.py')
);
ck(
  'id derives for a gate-test',
  derivedId('.ci/scripts/test/gates/test-gate-anti-vacuity.sh') ===
    'gate-test:gate-anti-vacuity'
);
ck(
  // THE PORTED SPELLING, which the case above cannot reach: it passes a hyphenated
  // `.sh` name, so it is satisfied by an arm that does no underscore normalisation
  // at all. Every `gate-test:` id in the manifest is hyphenated, so a port that
  // derived `gate-test:gate_lanes` would match nothing and register nowhere.
  'a gate-test id normalises underscores, so a ported battery test still matches the manifest',
  derivedId('.ci/scripts/test/gates/test_gate_lanes.py') === 'gate-test:gate-lanes',
  derivedId('.ci/scripts/test/gates/test_gate_lanes.py')
);
ck(
  'run is the BARE PATH for py -- a python3 prefix breaks check:ci-parity',
  derivedRun('.ci/scripts/quality/check_x.py') === '.ci/scripts/quality/check_x.py'
);
ck(
  'run is tsx for ts, with the selftest leg when asked',
  derivedRun('scripts/check-x.ts', true) === 'tsx scripts/check-x.ts --selftest && tsx scripts/check-x.ts'
);

ck(
  'THE SHIPPED DEFECT: --recurse-submodules infers submodules',
  inferredNeeds('git ls-files --recurse-submodules').includes('submodules')
);
ck(
  'CONTROL: a gate naming no submodule infers none',
  !inferredNeeds('files = root.glob("*.yml")').includes('submodules')
);

// --- parser v2: the kind discriminant -------------------------------------------
// v1 required `step:`, which made every gate that does not OWN a step undeclarable:
// the 143 gate-tests all ride one battery step, and the 15 test/local-only entries
// have none at all. Each case below is one of the four shapes the manifest records.
const blk = (...body: string[]): string =>
  ['# ---- gate ----', ...body.map((l) => `# ${l}`), '# ---- end gate ----'].join('\n');

ck(
  'a header with no kind: is a step, so every v1 declaration keeps its meaning',
  parseGateHeader(blk('step: X'))?.kind === 'step'
);
ck(
  'kind: battery declares the shared step it RIDES',
  parseGateHeader(blk('kind: battery', 'step: Quality-gate unit tests'))?.step ===
    'Quality-gate unit tests'
);
ck(
  'kind: test declares its gate-test and its blocker, and no step',
  (() => {
    const h = parseGateHeader(blk('kind: test', 'test: .ci/x.sh', 'blocker: BLOCKER: why'));
    return h?.kind === 'test' && h?.step === undefined && h?.test === '.ci/x.sh';
  })()
);
ck(
  'kind: local-only declares a blocker and no step',
  parseGateHeader(blk('kind: local-only', 'blocker: BLOCKER: nothing invokes it'))?.step ===
    undefined
);
ck(
  'CONTROL: kind: battery with no step is refused -- it must name what it rides',
  parseGateHeader(blk('kind: battery')) === null &&
    headerError(blk('kind: battery'))?.includes('shared step it rides') === true
);
ck(
  'CONTROL: a stepless kind that names a step is refused',
  headerError(blk('kind: test', 'step: X', 'test: a', 'blocker: b'))?.includes(
    'has no workflow step'
  ) === true
);
ck(
  'CONTROL: kind: test with no test: is refused',
  headerError(blk('kind: test', 'blocker: b'))?.includes('naming the gate-test') === true
);
ck(
  'CONTROL: a non-emitting kind with no blocker is refused, so it cannot be mistaken for an unfinished registration',
  headerError(blk('kind: local-only'))?.includes('blocker') === true
);
ck(
  'CONTROL: an unknown kind is refused rather than defaulted to step',
  headerError(blk('kind: sometimes', 'step: X'))?.includes('is not one of') === true
);
ck(
  'THE INVISIBILITY DEFECT: a malformed block now EXPLAINS itself instead of reading as no header',
  headerError('# ---- gate ----\n# step: X')?.includes('never closes') === true &&
    headerError('print("hi")') === null
);
ck(
  'CONTROL: the `---- /gate ----` mis-close is named in the error, having voided a declaration twice',
  headerError('# ---- gate ----\n# step: X\n# ---- /gate ----')?.includes('/gate') === true
);
ck(
  'analyzeGateHeader separates all three outcomes: header, error, and no block',
  (() => {
    const a = analyzeGateHeader(blk('step: X'));
    const b = analyzeGateHeader('# ---- gate ----\n# step: X');
    return a !== null && !('error' in a) && b !== null && 'error' in b &&
      analyzeGateHeader('x = 1') === null;
  })()
);
console.log(`TOTAL\t${bad}`);
"""


def run_probe(gate) -> harness.RunResult:
    """The probe on stdin, from the repo root. Streams MERGED, as the twin captures them."""
    if not MOD.is_file():
        gate.log_fail(
            "gate-header.ts is missing at %s; the binder's source of truth is gone"
            % paths.relative_to_root(MOD)
        )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript module driven through tsx"
    )
    return harness.run([npx, "tsx", "-"], cwd=paths.repo_root(), stdin=PROBE_TS)


def verdicts(text: str) -> list[tuple[str, str]]:
    """`(verdict, label)` for every `PASS\\t...` / `FAIL\\t...` line the probe printed."""
    rows = []
    for line in text.splitlines():
        if line.startswith(("PASS\t", "FAIL\t")):
            word, _, label = line.partition("\t")
            rows.append((word, label))
    return rows


def total_line(text: str) -> str | None:
    """The probe's own failure count, or None if it never printed one."""
    for line in text.splitlines():
        if line.startswith("TOTAL\t"):
            return line.split("\t", 1)[1]
    return None


def test_the_subject_is_present(gate):
    gate.log_test("the binder's source of truth must exist before anything is asserted about it")
    gate.assert_eq(
        MOD.is_file(), True, "scripts/lib/gate-header.ts is the module every case below drives"
    )
    gate.log_pass("the parser module is on disk at %s" % paths.relative_to_root(MOD))


def test_gate_header_parser_both_directions(gate):
    """Every case in the twin's probe, replayed one control per verdict line."""
    gate.log_test("the declaration parser, in both directions, against the real module")
    result = run_probe(gate)
    rows = verdicts(result.combined)

    total = total_line(result.combined)
    if total is None:
        gate.log_fail("the probe printed no TOTAL line, so nothing was actually asserted", result)

    for word, label in rows:
        if word == "PASS":
            gate.log_pass(label)
        else:
            gate.log_fail("gate-header parser: %s" % label)

    gate.assert_eq(total, "0", "the probe must report zero failures")
    if len(rows) < MIN_VERDICTS:
        gate.log_fail(
            "only %d assertion(s) ran; the probe has lost cases (floor %d)"
            % (len(rows), MIN_VERDICTS)
        )
    gate.log_pass(
        "gate-header parser: %d assertion(s), both directions (floor %d)"
        % (len(rows), MIN_VERDICTS)
    )
