"""Port of `.ci/scripts/test/gates/test-greenlight-closure-trace.sh`, retired in W7 P5.

Completeness gate for the cross-PR greenlight closure table, `.ci/scripts/ci/greenlight.cjs::CLOSURES`.

WHAT THIS GUARDS, and why it is a different question from `test-greenlight.sh`. That file proves the ENGINE obeys its rules and that every path the table declares still exists. Neither property notices the failure that actually ships: a workflow gains a step, the job starts consuming an input nobody added to the table, and the greenlight keeps firing on evidence that no longer
covers what the job runs. Every declared path still exists, every rule still holds, and a PR editing that new input inherits a green it did not earn. That is a WRONG SKIP, the one failure class this design must not risk.

THE PROPERTY. For each key, derive the set of repo paths its DEFINING workflow job block references, then assert the table COVERS every one of them, either as an exact entry or as an ancestor directory entry. The direction is one-way on purpose: derived must be a subset of declared.

THE CHECKER IS NOT REIMPLEMENTED, AND THAT IS THE WHOLE DESIGN DECISION HERE. The twin does not check anything itself: it writes a 222-line Node program to a temp file and drives it, twice over deliberately mutated tables. That program is a line-based YAML block extractor, a shell source/invoke sweeper and a directory-aware coverage walk, and every one of those is the kind of thing
that agrees with its twin TODAY and diverges the first time a job id or a `source` line moves. So the port carries the SAME PROGRAM, byte for byte, in `CHECKER_PATH`, and drives it the same four ways. What is ported is the harness, not the instrument.

THE COPY LIVES BESIDE THIS FILE RATHER THAN INSIDE IT, and that is not cosmetic. A heredoc's bytes are unambiguous; a Python string literal's are not, because the same program embedded as a literal would have to survive whatever quoting the literal imposes, and a port whose fidelity claim rests on nobody having mis-escaped a backslash is not making a fidelity claim.
`trace_checker.cjs.fixture` is copied out of the twin unmodified and read from disk, then MATERIALISED into `tmp_path` as `trace.cjs` before each run -- which is what the twin does too, into its own `mktemp -d`.

THE `.fixture` SUFFIX IS LOAD-BEARING AND WAS PAID FOR. Named plainly `trace_checker.cjs`, the file is JavaScript source of this repository and
`npm run lint` covers `.ci`: `npx eslint` on it reports
`89:33 error Unnecessary escape character` (`no-useless-escape`), measured 2026-09-07. That finding is real and is INVISIBLE today only because the program lives inside a bash heredoc where no linter looks. Fixing the escape would break the byte-identity this port's whole fidelity argument rests on, so the file is named for what it is -- a fixture, a frozen copy of somebody else's
bytes -- and node is handed a `.cjs` copy instead. Node refuses an unknown extension outright (`ERR_UNKNOWN_FILE_EXTENSION`), so the materialisation is not optional.

THERE IS NO SECOND COPY ANY MORE, WHICH IS WHY THE DRIFT CHECK IS GONE. While both files existed, `test_the_checker_is_byte_identical_to_the_twins` -- an ADDED case, not one of the twin's four -- extracted the twin's heredoc and required it to equal the file, and it was written to FAIL rather than skip if the twin vanished so the pairing could not be forgotten. W7 P5 census
batch A8 retired the twin, so that case was deleted in the same change: with one copy left there is nothing to compare, and a case comparing a file against nothing passes over nothing. `trace_checker.cjs.fixture` is now the only copy of the checker, and `write_checker` below is what refuses a run with the fixture missing, before any case can pass over nothing.

WHERE THIS REIMPLEMENTS awk AND grep, AND WHY THE ANSWERS AGREE. Only the assertions around the checker's own stdout, which is a fixed line grammar the checker writes itself (`DERIVED <key> <n>` and `UNCOVERED <key> <path> <why>`):

  `grep -c '^DERIVED '` counts LINES beginning with that literal, which is a per-line
  `startswith` count. Not a byte count and not a match count; the checker writes
  exactly one such line per key, so the two agree by construction.

  `awk '$1 == "DERIVED" && $3 < 2 { print $2, $3 }'` and its two siblings are
  whitespace-field lookups. `str.split()` splits on runs of whitespace exactly as
  awk's default FS does, so `$1`, `$2` and `$3` are fields 0, 1 and 2. The `< 2`
  comparison is NUMERIC in awk because both operands look numeric; `int()` makes that
  explicit rather than leaving it to a coercion rule.

`node` IS REQUIRED, and its absence is a loud failure carrying the fix rather than a skip. A case that could not run has not been checked.

NO `xdist_group`. Every mutated table is written under pytest's own `tmp_path`, and everything read from the checkout is read-only.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
ENGINE = ROOT / ".ci" / "scripts" / "ci" / "greenlight.cjs"
CHECKER_PATH = pathlib.Path(__file__).resolve().parent / "trace_checker.cjs.fixture"


def node(gate) -> str:  # noqa: ARG001 - `gate` keeps every caller uniform
    return harness.require_tool(
        "node",
        "install Node 22 (the version .devcontainer/toolchain.env pins), or run this "
        "under the devbox where it is already on PATH",
    )


def table_json(gate, directory: pathlib.Path) -> pathlib.Path:
    """CLOSURES as data, which is what makes the mutation controls possible without ever editing the engine."""
    result = harness.run(
        [
            node(gate),
            "-e",
            (
                "const { CLOSURES } = require(process.argv[1]);"
                "process.stdout.write(JSON.stringify(CLOSURES, null, 2));"
            ),
            str(ENGINE),
        ]
    )
    if result.rc != 0:
        gate.log_fail(
            "could not read CLOSURES out of %s, so there is no table to check: %s"
            % (ENGINE, result.err.strip())
        )
    path = directory / "table.json"
    path.write_text(result.out, encoding="utf-8")
    return path


def write_checker(gate, directory: pathlib.Path) -> pathlib.Path:
    """Materialise the frozen fixture as a runnable `.cjs`, exactly as the twin does.

    Node refuses to execute an unknown extension, so this is a requirement rather than a convenience. See the module docstring for why the stored copy is not itself called `.cjs`.
    """
    if not CHECKER_PATH.is_file():
        gate.log_fail(
            "%s is missing, so there is no checker to drive and every case in this "
            "module would pass over nothing" % CHECKER_PATH
        )
    path = directory / "trace.cjs"
    path.write_bytes(CHECKER_PATH.read_bytes())
    return path


def trace(gate, table: pathlib.Path) -> harness.RunResult:
    checker = write_checker(gate, table.parent)
    return harness.run([node(gate), str(checker), str(ROOT), str(table)], timeout=600)


def derived(text: str, index: int, key: str | None = None) -> list[str]:
    """Every `$<index+1>` from the `DERIVED` lines, optionally for one key."""
    out = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) <= index or fields[0] != "DERIVED":
            continue
        if key is not None and (len(fields) < 2 or fields[1] != key):
            continue
        out.append(fields[index])
    return out


def mutate_table(gate, source: pathlib.Path, target: pathlib.Path, program: str) -> None:
    """One of the twin's `node -e` table rewrites, driven the same way.

    THE MUTATION IS DONE IN NODE, not in Python's `json`, and that is deliberate: the table is produced by `JSON.stringify` and consumed by `JSON.parse`, so a rewrite in a third serializer would be a third opinion about the same bytes.
    """
    result = harness.run([node(gate), "-e", program, str(source), str(target)])
    if result.rc != 0:
        gate.log_fail(
            "the table mutation did not apply, so the control below would pass for the "
            "wrong reason: %s" % result.err.strip()
        )
    if not target.is_file():
        gate.log_fail("the table mutation wrote no file at %s" % target)


def test_derivation_is_not_vacuous(gate, tmp_path):
    # A checker that derives nothing passes every coverage assertion in this file, so the SIZE of the derived set is asserted BEFORE the coverage itself.
    table = table_json(gate, tmp_path)
    out = trace(gate, table).combined

    keys = len([line for line in out.splitlines() if line.startswith("DERIVED ")])
    gate.assert_eq(keys, 18, "every key in the table must have a defining site and be traced")

    # Every key must derive MORE than the defining workflow file it gets for free, or the job block was not found and the scan ran over nothing. The floor is 2 rather than something rounder because update_flow honestly derives exactly 2.
    thin = [
        "%s %s" % (line.split()[1], line.split()[2])
        for line in out.splitlines()
        if line.split()[:1] == ["DERIVED"] and int(line.split()[2]) < 2
    ]
    gate.assert_eq(thin, [], "no key may derive nothing beyond its own workflow file")

    # And the fat keys must actually be fat: e2e_workers walks a dozen step scripts plus their sourced libraries, so a derivation that collapsed to the workflow-plus-a-couple shape would still clear the floor above.
    workers = derived(out, 2, "e2e_workers")
    if not workers:
        gate.log_fail("e2e_workers derived no line at all, so its size cannot be judged")
    gate.assert_eq(
        1 if int(workers[0]) > 14 else 0,
        1,
        "e2e_workers must trace its whole step chain (%s paths)" % workers[0],
    )

    total = sum(int(n) for n in derived(out, 2))
    # 195 across the 18 keys as of 2026-08-08. The floor sits just under it so that any ONE key ceasing to derive drops the total through it, rather than being absorbed by slack.
    gate.assert_eq(
        1 if total > 190 else 0,
        1,
        "the whole trace must derive a substantial set (%d paths)" % total,
    )
    gate.log_pass(
        "the derivation produces a real requirement set for all 18 keys (%d paths)" % total
    )


def test_every_derived_path_is_covered(gate, tmp_path):
    # THE PROPERTY. Every derived path is covered by the declared closure.
    table = table_json(gate, tmp_path)
    result = trace(gate, table)
    if result.rc != 0:
        for line in result.combined.splitlines():
            if line.startswith("UNCOVERED "):
                gate.log_error(line)
    gate.assert_eq(result.rc, 0, "every path each job references must be covered by its closure")
    gate.assert_not_contains(
        result.combined, "UNCOVERED", "and no key may report an uncovered input"
    )
    gate.log_pass("every closure covers every input its job references (case 2)")


def test_a_missing_entry_is_caught(gate, tmp_path):
    # THE CONTROL. Delete ONE required entry from a copy of the table and the identical checker must go red, naming that key and that path. Two mutations, because they fail through different limbs: a path deletion exercises the coverage walk, and an emptied submodule list exercises the checkout implication.
    table = table_json(gate, tmp_path)

    # Mutation 1: e2e_workers loses run-e2e.sh, the script its final step runs.
    mutant = tmp_path / "mutant-path.json"
    mutate_table(
        gate,
        table,
        mutant,
        'const fs = require("fs");\n'
        'const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));\n'
        "t.e2e_workers.paths = t.e2e_workers.paths.filter("
        '(p) => p !== ".ci/scripts/test/run-e2e.sh");\n'
        "fs.writeFileSync(process.argv[2], JSON.stringify(t));\n",
    )
    result = trace(gate, mutant)
    gate.assert_eq(result.rc, 1, "a table missing one required path must FAIL the checker")
    gate.assert_contains(
        result.combined,
        "UNCOVERED e2e_workers .ci/scripts/test/run-e2e.sh not-in-closure",
        "naming the key and the exact path that went uncovered",
    )
    # And ONLY that key: the finding must be attributed, not smeared across the table by a checker that collapses on any error.
    hits = len([ln for ln in result.combined.splitlines() if ln.startswith("UNCOVERED ")])
    gate.assert_eq(hits, 1, "exactly one finding, so the failure is attributed to one key")

    # Mutation 2: renet keeps every path but stops pinning any submodule, while its job block still checks out with `submodules: true`.
    mutant = tmp_path / "mutant-pins.json"
    mutate_table(
        gate,
        table,
        mutant,
        'const fs = require("fs");\n'
        'const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));\n'
        "t.renet.submodules = [];\n"
        "fs.writeFileSync(process.argv[2], JSON.stringify(t));\n",
    )
    result = trace(gate, mutant)
    gate.assert_eq(result.rc, 1, "a key that checks out submodules and pins none must FAIL")
    gate.assert_contains(
        result.combined,
        "UNCOVERED renet - checks-out-submodules-but-pins-none",
        "named as the checkout implication, not as a missing path",
    )

    # CONTROL FOR THE CONTROL: the unmutated table through the same invocation exits 0, so the two reds above are the mutations and not a checker that fails on everything.
    gate.assert_eq(
        trace(gate, table).rc,
        0,
        "the unmutated table through the same checker still passes",
    )
    gate.log_pass("the checker provably fires: one deleted entry turns it red (case 3)")


def test_ancestor_coverage_respects_the_separator(gate, tmp_path):
    # Coverage is by exact entry OR by ancestor directory, and by nothing looser. A prefix match that ignored the separator would let `.ci/scripts/te` cover `.ci/scripts/test/run-e2e.sh`, which is the shape a careless `startsWith` takes.
    table = table_json(gate, tmp_path)

    mutant = tmp_path / "mutant-dir.json"
    mutate_table(
        gate,
        table,
        mutant,
        'const fs = require("fs");\n'
        'const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));\n'
        "t.e2e_workers.paths = t.e2e_workers.paths.map((p) =>\n"
        '  p === ".ci/scripts/test/run-e2e.sh" ? ".ci/scripts/test" : p\n'
        ");\n"
        "fs.writeFileSync(process.argv[2], JSON.stringify(t));\n",
    )
    gate.assert_eq(trace(gate, mutant).rc, 0, "a directory entry covers the files beneath it")

    mutant = tmp_path / "mutant-prefix.json"
    mutate_table(
        gate,
        table,
        mutant,
        'const fs = require("fs");\n'
        'const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));\n'
        "t.e2e_workers.paths = t.e2e_workers.paths.map((p) =>\n"
        '  p === ".ci/scripts/test/run-e2e.sh" ? ".ci/scripts/te" : p\n'
        ");\n"
        "fs.writeFileSync(process.argv[2], JSON.stringify(t));\n",
    )
    result = trace(gate, mutant)
    gate.assert_eq(result.rc, 1, "a bare string prefix must NOT be read as an ancestor")
    gate.assert_contains(
        result.combined,
        "UNCOVERED e2e_workers .ci/scripts/test/run-e2e.sh",
        "the path is still reported uncovered",
    )
    gate.log_pass("coverage follows directory boundaries, not string prefixes (case 4)")
