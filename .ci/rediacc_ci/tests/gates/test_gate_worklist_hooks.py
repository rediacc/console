"""Port of `.ci/scripts/test/gates/test-worklist-hooks.sh`.

CI wrapper for the Stop-hook harnesses under `.claude/hooks/stop/`.

WHY THIS EXISTS. Its sibling `test-claude-hooks.sh` wraps the PRE-BASH/PRE-EDIT guard
harness, and that asymmetry was invisible: the STOP hook -- which gates the end of
every turn, owns the worklist store, the deferral machinery and the judge subprocess
-- had a 431-case suite that ran only when somebody remembered to type it. A
regression in it could never turn CI red. That gap was found the way these always
are: a real Stop-gate defect shipped, and the test written to prevent its return had
nowhere to run. A fix whose test cannot execute in CI is a fix with no gate.

WHY IT TAKES A LIST. `test-report-inbox.sh` was created with the EXACT problem quoted
above: cases that ran only when somebody typed them. Rather than let the same gap
reopen under a second file name, this takes a list, so adding a third harness is one
entry and can never again mean "and a CI gate nobody remembered to write".

THE VACUITY GUARD IS THE POINT OF THE WRAPPER. A harness that silently ran ZERO cases
must FAIL here rather than report a pass, because "0 failed" and "nothing executed"
are the same exit code. So the summary line is parsed as well as the status.

THE STOP-HOOK SUITE IS DELEGATED, NOT DROPPED (2026-09-06).
`check:ci-hook-worklist-suite` runs the very same `test-worklist-v5.sh` as a
first-class manifest gate, and both were scheduled in the same full local run, so the
802-case suite executed TWICE per `npm run ci`. Measured by sampling the process
table: two top-level `test-worklist-v5.sh` processes alive for 775 seconds each.
A DELEGATION NOBODY CHECKS REOPENS THE HOLE THIS FILE WAS WRITTEN ABOUT the moment
the key is renamed, deleted, repointed, or flipped to `gate: false` -- every one of
those a silent, green-looking change -- so the delegate is verified on every run, in
four separate ways, each with its own diagnostic.

A FLAT TWIN, so the parity floor is its runtime `PASS:` count. Measured 2026-09-07:
the twin emits TWO lines matching `^PASS:` (the delegation control and the final
summary) and, separately, `PASS[report-inbox]:` and `PASS[stop-hook]:` lines that do
NOT match that anchor because of the bracket. This module records five controls, so
the floor is cleared with room; the count is stated here rather than left implicit
because a reader comparing the two files will otherwise wonder where the bracketed
lines went.

WHERE THIS REIMPLEMENTS grep, awk AND sed, AND WHY THE ANSWERS AGREE.

  `grep -F "\\"<key>\\":" package.json` is a FIXED-STRING line search, which is `in`
  over each line. No regex is involved on either side, which matters here: the needle
  contains `:` and `"` and nothing that a regex engine would treat specially, but
  relying on that would be relying on the needle never changing.

  `awk -v k="id: '<key>'," 'index($0, k) { f = 1 } f { print } f && /^  },$/ { exit }'`
  is: start at the first line CONTAINING that fixed string, print inclusively, and
  stop after the first line EQUAL to `  },`. `manifest_entry` below is the same
  three-part state machine. The terminator is bounded by the entry's own closing
  brace rather than a line count, because a fixed `grep -A <n>` window either misses
  a reordered field or bleeds into the NEXT entry and reads its `gate: true` as this
  one's. Two-space `  },` is the terminator `scripts/gate-bind.ts` itself relies on.

  `grep -oE 'passed=[0-9]+ failed=[0-9]+' | tail -1` takes the LAST match anywhere in
  the output, not the last matching LINE and not the first match. `re.findall(...)[-1]`
  is the same choice. The `tail -1` is load-bearing and the twin says why: with two
  harnesses printing into one buffer it would read only the last summary and report a
  red first harness as green. This module keeps each harness's output in its own
  string, which makes that impossible by construction rather than by care, and still
  takes the last match so the two agree on a harness that prints more than one.

  `sed -E 's/passed=([0-9]+).*/\\1/'` and `s/.*failed=([0-9]+)/\\1/` are the two capture
  groups of the same match, read directly here.

`XDIST_GROUP` IS DECLARED, and it is worth being precise about what it buys, because
the obvious reading of it is wrong. `test-report-inbox.sh` is the real harness for
the durable sub-agent report inbox: 131 cases, 54 seconds, and it drives the Stop
hook's inbox machinery for real. It IS fixture-isolated -- it captures one
`mktemp -d` base at startup and gives every case its own `TMPDIR` and
`CLAUDE_CONFIG_DIR` under it (test-report-inbox.sh:74-91) -- so two concurrent copies
cannot corrupt each other, and the declaration is about COST rather than correctness:
54 seconds of one core, doubled, is the same doubling this gate's own header records
having measured and removed once already.

WHAT IT DOES NOT BUY, said out loud rather than assumed: the group serialises this
module against anything else declaring the same name, and NOT against
`test_twin_parity.py`'s own `bash <twin>` invocation, which lives in a different
module with no group. That overlap is a property every port in this directory
already has, not something this declaration introduces or could fix from here.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-worklist-hooks.sh"

# The root conftest reads this attribute (rediacc_ci.xdist_groups.GROUP_ATTR) and turns it into the xdist group for every item in the module. A `pytestmark` would NOT do the same thing: the project's grouping is declaration-driven so that `group_for` can answer the same question the parity driver asks, from the module object rather than from a filename.
XDIST_GROUP = "stop-hook-harnesses"

ROOT = paths.repo_root()
PACKAGE_JSON = ROOT / "package.json"
MANIFEST = ROOT / "scripts" / "ci-runner" / "manifest.ts"

# name -> repo-relative harness path. Every one must end with
# "  passed=<n> failed=<m>".
HARNESSES = (("report-inbox", ".claude/hooks/stop/test-report-inbox.sh"),)

# name | npm key | repo-relative harness path. A harness this gate deliberately does NOT run because another REGISTERED gate already runs it.
DELEGATED = (
    ("stop-hook", "check:ci-hook-worklist-suite", ".claude/hooks/stop/test-worklist-v5.sh"),
)

SUMMARY_RE = re.compile(r"passed=([0-9]+) failed=([0-9]+)")

# The entry terminator the binder itself relies on (scripts/gate-bind.ts).
ENTRY_END = "  },"


def manifest_entry(source: str, key: str) -> str:
    """The manifest block for `key`, from its `id:` line through its closing `  },`."""
    needle = "id: '%s'," % key
    lines = source.splitlines()
    collected: list[str] = []
    started = False
    for line in lines:
        if not started and needle in line:
            started = True
        if not started:
            continue
        collected.append(line)
        if line == ENTRY_END:
            break
    return "\n".join(collected)


def delegation_problem(
    name: str, key: str, relative: str, package_json: pathlib.Path, manifest: pathlib.Path
) -> str | None:
    """None when all five hold, else the ONE that did not, as the twin's own message.

    RETURNS THE REASON RATHER THAN RAISING, so the control can observe a verdict. The
    twin gets the same property by running the function in a SUBSHELL and reading its
    exit status; here a value is cheaper and, unlike a caught exception, cannot be
    confused with a bug in the control itself.
    """
    if not (ROOT / relative).is_file():
        return "FAIL[%s]: %s does not exist, so nothing runs it anywhere." % (name, relative)

    matching = [
        line
        for line in package_json.read_text(encoding="utf-8").splitlines()
        if '"%s":' % key in line
    ]
    if not matching:
        return (
            'FAIL[%s]: package.json has no "%s" script, so the %s harness now runs '
            "NOWHERE -- this gate stopped running it on the strength of that key."
            % (name, key, name)
        )
    line = "\n".join(matching)
    if relative not in line:
        return 'FAIL[%s]: "%s" no longer runs %s. It runs:%s' % (name, key, relative, line)

    entry = manifest_entry(manifest.read_text(encoding="utf-8"), key)
    if not entry:
        return (
            "FAIL[%s]: scripts/ci-runner/manifest.ts has no entry with id '%s', so the "
            "npm key exists but nothing schedules it and the harness is unreachable." % (name, key)
        )
    if "gate: true" not in entry:
        return (
            "FAIL[%s]: manifest entry '%s' is not gate: true, so a full run never "
            "selects it." % (name, key)
        )
    if relative not in entry:
        return (
            "FAIL[%s]: manifest entry '%s' no longer declares %s among its leaves, so "
            "the parity oracle can no longer see that this harness is covered."
            % (name, key, relative)
        )
    return None


def test_the_delegation_assertion_fires_when_the_delegate_npm_key_is_removed(gate, tmp_path):
    # CONTROL, and in the twin it runs on every invocation rather than behind a flag. An assertion that cannot fail is worth exactly what no assertion is worth, and the failure being guarded against -- a harness that runs nowhere -- looks identical to a harness that ran and passed. So the SAME predicate is driven against a package.json with the delegate key stripped out, and a pass
    # there is itself a failure.
    name, key, relative = DELEGATED[0]
    original = PACKAGE_JSON.read_text(encoding="utf-8")
    doctored = tmp_path / "package.json"
    kept = [line for line in original.splitlines() if '"%s":' % key not in line]
    if len(kept) == len(original.splitlines()):
        gate.log_fail(
            'the control could not strip "%s" from package.json because no line '
            "carries it, so it would pass for the wrong reason" % key
        )
    doctored.write_text("\n".join(kept) + "\n", encoding="utf-8")

    problem = delegation_problem(name, key, relative, doctored, MANIFEST)
    if problem is None:
        gate.log_fail(
            "CONTROL FAILED: the delegation assertion PASSED against a package.json "
            "with %s removed, so it cannot detect the disappearance it exists to "
            "detect. Nothing this gate reports about delegation is meaningful." % key
        )
    gate.assert_contains(
        problem,
        "runs NOWHERE",
        "CONTROL FAILED: the assertion fired, but not for the reason planted -- it "
        "must name the missing key",
    )
    gate.log_pass("the delegation assertion fires when the delegate npm key is removed")


def test_the_manifest_entry_reader_stops_at_the_entrys_own_brace(gate):
    """ADDED CASE, not in the twin. The awk this reimplements is the one piece of the
    twin whose failure mode is SILENT: an extractor that ran past the closing brace
    would read the NEXT entry's `gate: true` as this one's and report a delegation
    that is not there. So the reader is shown both directions on the real manifest."""
    source = MANIFEST.read_text(encoding="utf-8")
    key = DELEGATED[0][1]
    entry = manifest_entry(source, key)
    if not entry:
        gate.log_fail(
            "the manifest entry reader found nothing for '%s'; every delegation claim "
            "below would then rest on an empty string" % key
        )
    gate.assert_contains(entry, "id: '%s'," % key, "the block must start at its own id")
    gate.assert_eq(
        entry.splitlines()[-1], ENTRY_END, "the block must stop at its own closing brace"
    )
    # AND IT MUST NOT HAVE BLED: exactly one `id:` line in the extracted block.
    ids = [line for line in entry.splitlines() if line.strip().startswith("id: '")]
    gate.assert_eq(
        len(ids),
        1,
        "the extracted block carries %d id lines, so it has run into a neighbouring "
        "entry and its `gate: true` would be read as this one's" % len(ids),
    )
    gate.log_pass(
        "the manifest reader returns exactly one entry, bounded by its own `%s`" % ENTRY_END
    )


def test_the_stop_hook_suite_is_delegated_to_a_registered_gate(gate):
    for name, key, relative in DELEGATED:
        problem = delegation_problem(name, key, relative, PACKAGE_JSON, MANIFEST)
        if problem:
            gate.log_fail(problem)
        gate.log_pass(
            "PASS[%s]: delegated to '%s' (gate: true), which runs %s" % (name, key, relative)
        )


def test_every_listed_harness_is_green_and_non_vacuous(gate):
    # ONE HARNESS PER INVOCATION, PARSED FROM ITS OWN OUTPUT. EVERY harness runs even after one fails, and the verdict is the OR: stopping at the first failure would hide a second broken harness behind the first for as long as the first stayed broken. `harness.log_fail` raises, so the loop collects and reports at the end.
    problems = []
    summaries = []
    for name, relative in HARNESSES:
        path = ROOT / relative
        if not path.is_file():
            problems.append(
                "FAIL[%s]: %s not found -- this gate has nothing to run, which is a "
                "failure rather than a pass: a vanished harness cannot be green." % (name, relative)
            )
            continue
        result = harness.run(["bash", str(path)], timeout=1800)
        if result.rc != 0:
            problems.append(
                "FAIL[%s]: harness exited nonzero (%d)\n%s" % (name, result.rc, result.combined)
            )
            continue
        # Parse the summary as WELL as the exit code: trusting the exit code alone is what lets a harness that executed nothing look identical to one that executed everything and passed.
        matches = SUMMARY_RE.findall(result.combined)
        if not matches:
            problems.append(
                "FAIL[%s]: could not find the harness summary line -- it may have "
                "changed shape, in which case this gate is no longer reading its "
                "result." % name
            )
            continue
        passed, failed = (int(value) for value in matches[-1])
        if failed != 0:
            problems.append("FAIL[%s]: harness reported %d failing case(s)" % (name, failed))
            continue
        if passed < 1:
            problems.append(
                "FAIL[%s]: harness ran ZERO cases -- a vacuous green, not a pass" % name
            )
            continue
        summaries.append("PASS[%s]: passed=%d failed=%d" % (name, passed, failed))

    for line in summaries:
        print(line)
    if problems:
        gate.log_fail("at least one stop-hook harness is red:\n%s" % "\n".join(problems))
    # ANTI-VACUITY on the LIST itself: an empty HARNESSES tuple would satisfy every line above without executing anything at all.
    if not HARNESSES:
        gate.log_fail("HARNESSES is empty, so this gate ran no harness and its green means nothing")
    gate.log_pass(
        "%d stop-hook harness(es) green, %d delegated and verified"
        % (len(HARNESSES), len(DELEGATED))
    )
