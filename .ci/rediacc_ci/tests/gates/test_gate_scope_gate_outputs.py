"""Port of `.ci/scripts/test/gates/test-scope-gate-outputs.sh`.

The scope gate's OUTPUT CONTRACT, driven end to end through the real
`.ci/scripts/ci/scope-shadow.sh`.

WHAT THIS GUARDS. Since 2026-07-31 that script no longer observes, it DECIDES:
ci.yml reads its `run_<key>=false` outputs and skips jobs on them. The safety
property is entirely in the encoding, and it is one sentence: a false line is the
ONLY thing that can shrink a run, so every failure path must emit zero of them.
That property is invisible to code reading, because every one of its failure paths
is an error path -- an engine that crashed, a plan that could not be written, an
operator override -- and error paths are exactly what unit tests over pure
functions never reach. So this drives the actual script, with a PATH-shimmed `gh`
and a real git repository, and reads the bytes it appends to `$GITHUB_OUTPUT`.

THE FIXTURE IS A WHOLE REPO, and it has to be. `scope-engine.cjs` resolves its repo
root from its own `__dirname` (`path.resolve(__dirname, '../../..')`), so pointing
the engine somewhere safe means copying `.ci/scripts/ci` into a fixture tree and
running the copy: git history, branch shape and merge parents then all belong to
the test. A symlink would NOT work, because node resolves a symlinked module to its
real path and `__dirname` would land back on this repository.

EVERY CASE CARRIES ITS CONTROL. An emitter that writes nothing at all passes cases
(b), (c) and (d) trivially, so case (a) pins the exact set of false lines a reduced
plan must produce, and cases (b) and (d) re-run the SAME fixture with the defect
removed and require the lines to come back.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `build_fixture` reads the real
`.ci/scripts/ci` tree wholesale and every case runs against that copy, so a battery
step rewriting `scope-shadow.sh`, `scope-map.cjs` or `skip-plan-reconcile.cjs`
mid-copy is a divergence that would be blamed on this port. `REAL_TREE_TWIN = True`
buys the serialisation, and it is honoured only because this module declares no
`XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

THE SUBJECT DOES NOT SELF-SCAN. `scope-shadow.sh` classifies a git delta inside the
fixture repository and never walks `.ci` looking for samples, so no fixture string
in this file needs the `%s` template treatment `test_gate_label_references.py` owes
its own self-scanning subject. Checked before any fixture was written, not assumed.

THE FIXTURE IS BUILT ONCE PER MODULE, where the twin builds it once per process.
Same shape: eight cases against one repository, each writing into its own
`out-<name>` directory. A function-scoped build would re-run `git init`, four
commits, a merge and two `node -e` calls eight times for no additional coverage.
All eight land on one xdist worker because the module is in `REAL_TREE_GROUP`.

TWO PORT-SPECIFIC NOTES ON THE ORDERING ASSERTION, both about the same trap.

  * `LC_ALL=C sort` in the twin becomes Python's `sorted()`, which is code-point
    order and therefore byte order for ASCII -- the same order node's
    `Array.prototype.sort()` (UTF-16 code UNIT order) produces for these keys. The
    twin's own comment records why the ambient locale is wrong here: glibc's
    en_US.UTF-8 collation ignores `=` and `_` at the primary level, so
    `run_e2e_k8s_ceph=false` collates before `run_e2e_k8s=false` while node puts
    the shorter prefix first. It was green in CI and red on every developer machine
    with a UTF-8 collating locale for 26 days. Python's `sorted()` has no locale
    rung at all, which removes the failure mode rather than re-encoding it.
  * The suffix is applied BEFORE the sort on both sides, deliberately, so the two
    are byte-order sorts over the SAME strings rather than two sorts that merely
    agree today.

ADDED BY THE PORT: `test_the_fixture_carries_a_real_engine`. Anti-vacuity on the
fixture itself. Every case below is a statement about a COPY of `.ci/scripts/ci`,
so a copy that silently landed empty or lost `scope-shadow.sh` would make each
`run_gate` fail for a reason that has nothing to do with the output contract. The
added case prints how many files the copy carries and names the three the other
cases execute.
"""

import json
import os
import pathlib
import re
import shutil
import stat

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-scope-gate-outputs.sh"

# build_fixture copies the real .ci/scripts/ci and every case runs that copy.
# See the docstring.
REAL_TREE_TWIN = True

CI_SRC_REL = ".ci/scripts/ci"
CI_SRC = paths.from_root(*CI_SRC_REL.split("/"))

# The three files the cases below actually execute. A copy missing any of them
# turns every run_gate into a "command not found" with nothing to say about the
# output contract.
REQUIRED_ENGINE_FILES = ("scope-shadow.sh", "scope-map.cjs", "skip-plan-reconcile.cjs")

BASELINE_RUN_ID = 1111
CURRENT_RUN_ID = 999

FALSE_LINE_RE = re.compile(r"^run_[a-z0-9_]*=false$", re.MULTILINE)
SCOPE_MODE_RE = re.compile(r"^scope_mode=", re.MULTILINE)

# THE WORKFLOW CONTRACT, spelled out as literals on purpose.
#
# ci.yml's `initialize` job declares one output per name below and reads them out
# of $GITHUB_OUTPUT. An output emitted under a name that is not on this list is
# SILENTLY DROPPED by the outputs block: no error, no warning, and the job it was
# meant to skip simply runs. So a rename on either side is invisible at runtime and
# shows up only as "the scope engine stopped saving any time", which nobody notices
# for weeks.
#
# Deriving this list from scope-map would defeat the point. It is a second,
# independent copy of the spelling, and the case below asserts the two agree.
WORKFLOW_CONTRACT_KEYS = (
    "run_unit",
    "run_e2e_workers",
    "run_e2e_ceph",
    "run_e2e_ceph_workers",
    "run_e2e_k8s",
    "run_e2e_k8s_ceph",
    "run_e2e_k8s_multinode",
    "run_e2e_migrate",
    "run_fork_isolation",
    "run_renet",
    "run_license_enforcement",
    "run_account_e2e",
    "run_drills",
    "run_ops",
    "run_elite_run",
    "run_update_flow",
    "run_package_tests",
    "run_install_methods",
)


# ---------------------------------------------------------------------------
# tools


def require_tools() -> tuple[str, str]:
    """`git` and `node`, or a LOUD refusal carrying the fix.

    A missing binary is a FAILURE and never a skip: a case that could not run has
    not been checked, and unchecked folded into fine is the shape this directory
    refuses.
    """
    git = harness.require_tool("git", "install git; the fixture IS a real repository")
    node = harness.require_tool(
        "node", "install Node 22; scope-map.cjs and scope-engine.cjs are run by node"
    )
    return git, node


class FixtureError(harness.GateAssertionError):
    """A fixture that could not be built. Distinct so a reader can tell a broken
    fixture from a broken subject, which is the one distinction a failing
    end-to-end test most often loses."""


# ---------------------------------------------------------------------------
# the fixture


class Fixture:
    """`build_fixture` from the twin, as an object so `run_gate` can be a method.

    A repository whose branch shape makes a REDUCED round the correct answer, plus
    the three `gh` responses the baseline walk needs.

        main:  B ------------------- M
        pr:     \\-- C1 --- C2 ------/

    The engine walks first-parent from head (C2) fenced at M^1 (B), so C1 is the
    only candidate. C1's run is green and carries an attested FULL plan, which makes
    it a usable baseline, and the NET delta C1..C2 touches docs plus packages/www
    only. Of the 18 job surfaces exactly one (`unit`) consumes www, so the correct
    plan runs `unit` and skips the other seventeen. That asymmetry is the point: an
    emitter that skips everything, or nothing, fails.
    """

    def __init__(self, work: pathlib.Path) -> None:
        self.work = work
        self.repo = work / "repo"
        self.ci_dir = self.repo / ".ci" / "scripts" / "ci"
        self.bin = work / "bin"
        self.git, self.node = require_tools()
        self._copy_engine()
        self._build_history()
        self._write_gh_responses()
        self._write_gh_shim()
        self.expected_false = self._expected_false()

    # -- construction ------------------------------------------------------

    def _run(self, argv: list[str], *, cwd: pathlib.Path | None = None) -> harness.RunResult:
        result = harness.run(argv, cwd=cwd or self.repo, timeout=180)
        if result.rc != 0:
            raise FixtureError(
                "fixture step failed (rc=%s): %s\n--- stdout ---\n%s\n--- stderr ---\n%s"
                % (harness.describe_exit(result.rc), " ".join(argv), result.out, result.err)
            )
        return result

    def _copy_engine(self) -> None:
        if not CI_SRC.is_dir():
            raise FixtureError(
                "%s is missing, so there is no engine to copy and every case below would "
                "be a statement about an empty directory." % CI_SRC_REL
            )
        self.ci_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(CI_SRC, self.ci_dir)
        missing = [n for n in REQUIRED_ENGINE_FILES if not (self.ci_dir / n).is_file()]
        if missing:
            raise FixtureError(
                "the engine copy is missing %s. Every run_gate below would fail as "
                '"command not found" and say nothing about the output contract.'
                % ", ".join(missing)
            )

    def _git(self, *args: str) -> harness.RunResult:
        return self._run([self.git, "-C", os.fspath(self.repo), *args])

    def _rev_parse(self, ref: str) -> str:
        return self._git("rev-parse", ref).out.strip()

    def _build_history(self) -> None:
        self.repo.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "scope-gate-test@example.invalid")
        self._git("config", "user.name", "Scope Gate Test")

        (self.repo / "docs").mkdir(parents=True, exist_ok=True)
        (self.repo / "packages" / "www" / "src").mkdir(parents=True, exist_ok=True)
        (self.repo / "docs" / "a.md").write_text("base\n", encoding="utf-8")
        self._git("add", "docs")
        self._git("commit", "-q", "-m", "base")
        self.base_sha = self._rev_parse("HEAD")

        self._git("checkout", "-q", "-b", "pr")
        with open(self.repo / "docs" / "a.md", "a", encoding="utf-8") as handle:
            handle.write("c1\n")
        self._git("add", "docs")
        self._git("commit", "-q", "-m", "c1")
        self.c1_sha = self._rev_parse("HEAD")

        (self.repo / "docs" / "b.md").write_text("c2\n", encoding="utf-8")
        (self.repo / "packages" / "www" / "src" / "index.astro").write_text(
            "<p>c2</p>\n", encoding="utf-8"
        )
        self._git("add", "docs", "packages")
        self._git("commit", "-q", "-m", "c2")
        self.c2_sha = self._rev_parse("HEAD")

        self._git("checkout", "-q", "main")
        self._git("merge", "-q", "--no-ff", "-m", "merge pr", "pr")
        self.merge_sha = self._rev_parse("HEAD")

    def _node_eval(self, script: str, *args: str) -> str:
        return self._run([self.node, "-e", script, *args]).out

    def _write_gh_responses(self) -> None:
        # The baseline plan C1's run attested. Built THROUGH the real buildPlan so
        # its 18 keys cannot drift from scope-map's; a hand-written key list here
        # would silently stop being a full plan the day a surface is added, and the
        # test would then pass for the wrong reason.
        self.baseline_plan = self.work / "baseline-plan.json"
        self._node_eval(
            """
const { buildPlan } = require(process.argv[1]);
const plan = buildPlan({ modules: new Set(), reasons: [], mode: "full", full_reasons: ["seed"] });
plan.run_id = Number(process.argv[2]);
plan.base_sha = process.argv[3];
plan.head_sha = process.argv[4];
plan.conditions = {};
require("fs").writeFileSync(process.argv[5], JSON.stringify(plan, null, 2));
""",
            os.fspath(self.ci_dir / "scope-map.cjs"),
            str(BASELINE_RUN_ID),
            self.base_sha,
            self.c1_sha,
            os.fspath(self.baseline_plan),
        )

        # The per-job outcomes attestPlan reconciles that plan against, generated
        # from the reconciler's OWN name table for the same anti-drift reason.
        # Every job succeeded, so the strict reconcile the baseline reader performs
        # passes and C1 becomes usable.
        self.jobs_json = self.work / "jobs.json"
        self._node_eval(
            """
const { EXPECTED_JOB_NAMES } = require(process.argv[1]);
const jobs = Object.values(EXPECTED_JOB_NAMES)
  .flat()
  .map((name) => ({ name, conclusion: "success" }));
require("fs").writeFileSync(
  process.argv[2],
  JSON.stringify({ total_count: jobs.length, jobs }, null, 2),
);
""",
            os.fspath(self.ci_dir / "skip-plan-reconcile.cjs"),
            os.fspath(self.jobs_json),
        )

        self.runs_json = self.work / "runs.json"
        self.runs_json.write_text(
            '{"workflow_runs":[{"id":%d,"name":"Console CI","head_sha":"%s",'
            '"status":"completed","conclusion":"success"}]}\n' % (BASELINE_RUN_ID, self.c1_sha),
            encoding="utf-8",
        )

    def _write_gh_shim(self) -> None:
        """The `gh` shim. `SCOPE_GH_FAIL=1` turns every call into a failure, which
        is how the engine-failure case breaks the engine without touching its
        source."""
        self.bin.mkdir(parents=True, exist_ok=True)
        shim = self.bin / "gh"
        shim.write_text(
            """#!/bin/bash
set -uo pipefail
if [[ "${SCOPE_GH_FAIL:-}" == "1" ]]; then
    echo "gh: simulated API failure" >&2
    exit 1
fi
if [[ "${1:-}" == "run" && "${2:-}" == "download" ]]; then
    dir=""
    while (( $# > 0 )); do
        [[ "$1" == "-D" ]] && dir="${2:-}"
        shift
    done
    [[ -n "$dir" ]] || exit 1
    mkdir -p "$dir"
    cp "%s" "$dir/plan.json"
    exit 0
fi
if [[ "${1:-}" == "api" ]]; then
    case "${2:-}" in
        */jobs\\?*) cat "%s"; exit 0 ;;
        *actions/runs\\?head_branch*) cat "%s"; exit 0 ;;
    esac
fi
echo "gh shim: unhandled invocation: $*" >&2
exit 1
"""
            % (self.baseline_plan, self.jobs_json, self.runs_json),
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _expected_false(self) -> str:
        """The seventeen keys a correct reduced plan must mark false, derived from
        the real surface table rather than listed by hand.

        Sorted AFTER the `run_<k>=false` suffix is applied, so this side and the
        Python sort in the case below are byte-order sorts over the SAME strings
        rather than two sorts that merely agree today. Sorting the bare keys first
        is not equivalent in general: `=` is 0x3D, below `_` (0x5F) and letters but
        ABOVE the digits, so a future key pair like `foo` / `foo0bar` would
        transpose between the two forms.
        """
        text = self._node_eval(
            """
const { JOB_SURFACES } = require(process.argv[1]);
process.stdout.write(
  Object.keys(JOB_SURFACES)
    .filter((k) => !JOB_SURFACES[k].includes("www"))
    .map((k) => `run_${k}=false`)
    .sort()
    .join("\\n"),
);
""",
            os.fspath(self.ci_dir / "scope-map.cjs"),
        )
        if not text.strip():
            raise FixtureError(
                "scope-map's JOB_SURFACES yielded ZERO out-of-scope keys, so the reduced "
                "plan below would be compared against an empty expectation and would pass "
                "having asserted nothing."
            )
        return text

    def surface_keys(self) -> list[str]:
        text = self._node_eval(
            """
const { JOB_SURFACES } = require(process.argv[1]);
process.stdout.write(Object.keys(JOB_SURFACES).map((k) => `run_${k}`).join("\\n"));
""",
            os.fspath(self.ci_dir / "scope-map.cjs"),
        )
        return text.split("\n") if text else []

    def engine_file_count(self) -> int:
        return len([p for p in self.ci_dir.rglob("*") if p.is_file()])

    # -- driving the subject -----------------------------------------------

    def out_dir(self, name: str) -> pathlib.Path:
        return self.work / ("out-%s" % name)

    def run_gate(
        self,
        name: str,
        *,
        env: dict[str, str] | None = None,
        unset: tuple[str, ...] = (),
    ) -> "GateRun":
        """`run_gate <case-name> [env-args...]`: the real script, its rc, its bytes.

        The twin passes extra environment as `env "$@" bash scope-shadow.sh`, so a
        token is either `NAME=value` or `-u NAME`. Those two shapes become the `env`
        and `unset` arguments here rather than being parsed back out of a string,
        which is the one place a port can silently drop a seam.
        """
        outdir = self.out_dir(name)
        outfile = outdir / "github-output"
        outdir.mkdir(parents=True, exist_ok=True)
        outfile.write_text("", encoding="utf-8")
        merged = {
            "PATH": "%s%s%s" % (self.bin, os.pathsep, os.environ.get("PATH", "")),
            "SCOPE_SHADOW_OUT": os.fspath(outdir),
            "OUTPUT_FILE": os.fspath(outfile),
            "MERGE_SHA": self.merge_sha,
            "HEAD_SHA": self.c2_sha,
            "GITHUB_REPOSITORY": "rediacc/console",
            "GITHUB_RUN_ID": str(CURRENT_RUN_ID),
            "GITHUB_HEAD_REF": "pr",
            "GITHUB_STEP_SUMMARY": os.fspath(outdir / "summary.md"),
        }
        merged.update(env or {})
        environment = dict(os.environ)
        environment.update(merged)
        for key in unset:
            environment.pop(key, None)
        bash = harness.require_tool("bash", "install bash; the subject IS a bash script")
        result = harness.run(
            [bash, os.fspath(self.ci_dir / "scope-shadow.sh")],
            cwd=self.repo,
            env=environment,
            env_replace=True,
            timeout=300,
        )
        # The twin redirects `>gate.log 2>&1`; keeping the file means a failure
        # message can point a reader at bytes on disk rather than only at a string.
        (outdir / "gate.log").write_text(result.combined, encoding="utf-8")
        return GateRun(result.rc, outdir, outfile, result.combined)


class GateRun:
    """One `run_gate` invocation: its rc, its output directory, its emitted bytes."""

    def __init__(self, rc: int, outdir: pathlib.Path, outfile: pathlib.Path, log: str) -> None:
        self.rc = rc
        self.outdir = outdir
        self.outfile = outfile
        self.log = log

    @property
    def emitted(self) -> str:
        return self.outfile.read_text(encoding="utf-8") if self.outfile.is_file() else ""

    @property
    def false_lines(self) -> list[str]:
        """`count_false` / the grep the twin sorts. Anchored per line, as there."""
        return FALSE_LINE_RE.findall(self.emitted)

    def count_false(self) -> int:
        return len(self.false_lines)

    def plan(self) -> dict:
        return json.loads((self.outdir / "plan.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    """`build_fixture`, once. See the module docstring for why once and not eight
    times; the shape is the twin's, which also builds it a single time."""
    return Fixture(tmp_path_factory.mktemp("scope-gate-outputs"))


# ---------------------------------------------------------------------------
# The cases, in the twin's CALL order so the two files can be read side by side.


def test_the_fixture_carries_a_real_engine(gate, fixture):
    """ADDED BY THE PORT. Anti-vacuity on the fixture rather than on the subject.

    Every case below is a statement about a COPY of `.ci/scripts/ci`. A copy that
    landed empty, or lost `scope-shadow.sh`, would make each `run_gate` fail as
    "no such file" -- red, but saying nothing about the output contract, and
    sending the reader to look at the emitter. Discovering zero files here is a
    FAILURE, and the count is PRINTED so a collapse is visible rather than silent.
    """
    count = fixture.engine_file_count()
    if count == 0:
        gate.log_fail(
            "the engine copy at %s holds ZERO files, so nothing below is driving the "
            "subject and its green would mean nothing." % fixture.ci_dir
        )
    for name in REQUIRED_ENGINE_FILES:
        if not (fixture.ci_dir / name).is_file():
            gate.log_fail("the engine copy is missing %s, which the cases below execute" % name)
    gate.assert_eq(len(fixture.expected_false.split("\n")), 17, "17 out-of-scope keys expected")
    gate.log_pass(
        "the fixture carries %d file(s) copied from %s, including %s, and 17 expected "
        "false keys" % (count, CI_SRC_REL, ", ".join(REQUIRED_ENGINE_FILES))
    )


def test_emitted_names_match_the_workflow_contract(gate, fixture):
    """The emitter can only ever produce `run_<key>` for a key in scope-map's
    JOB_SURFACES, so comparing that table to the literal list above is the whole
    contract: same 18 names, same spelling. A key added to scope-map without a
    matching ci.yml output would be emitted and dropped on the floor; a key renamed
    in ci.yml without scope-map would be read as empty forever, which reads as "run
    it" and is safe but silently free of any saving at all."""
    from_map = fixture.surface_keys()
    gate.assert_eq(
        "\n".join(from_map),
        "\n".join(WORKFLOW_CONTRACT_KEYS),
        "the emitter's key set must match ci.yml's 18 declared outputs exactly, in name "
        "and spelling",
    )

    # CONTROL: the comparison is over a non-empty set. An empty JOB_SURFACES and an
    # empty literal list would compare equal and assert nothing.
    gate.assert_eq(
        len([k for k in WORKFLOW_CONTRACT_KEYS if k]),
        18,
        "the contract list must hold all 18 keys, or the comparison above is vacuous",
    )
    gate.log_pass("the 18 emitted output names match ci.yml's declared outputs byte for byte")


def test_reduced_plan_emits_exactly_the_out_of_scope_keys(gate, fixture):
    """(a) THE POSITIVE CASE THE OTHERS ARE MEASURED AGAINST."""
    run = fixture.run_gate("reduced")
    gate.assert_exit_code(0, run.rc, "the gate must always exit 0")

    # CONTROL, and it runs BEFORE anything reads the lines. An emitter that writes
    # nothing would satisfy every other case in this file, so if a reduced plan
    # produces no false line at all, nothing below is evidence of anything.
    n = run.count_false()
    if n == 0:
        gate.log_fail(
            "a reduced plan emitted ZERO run_*=false lines -- the emitter is dead, and "
            "every other case here would still pass.\n--- gate.log ---\n%s" % run.log
        )

    # `sorted()` is code-point order, which is byte order for these ASCII keys and
    # the same order node's sort produced for EXPECTED_FALSE. It has no locale rung,
    # which is what removes the collation trap the twin's `LC_ALL=C` guards against;
    # see the module docstring.
    gate.assert_eq(
        "\n".join(sorted(run.false_lines)),
        fixture.expected_false,
        "a reduced plan must mark exactly the out-of-scope keys false",
    )
    gate.assert_not_contains(
        run.emitted,
        "run_unit=false",
        "the one key whose surface the delta touches must NOT be marked false",
    )
    gate.assert_not_contains(
        run.emitted, "=true", "the gate must never write a run_<key>=true line"
    )
    gate.assert_eq(len(SCOPE_MODE_RE.findall(run.emitted)), 1, "exactly one scope_mode line")
    gate.assert_contains(run.emitted, "scope_mode=reduced", "and it must say reduced")
    gate.log_pass(
        "a reduced plan emits false for exactly the %d out-of-scope keys, and "
        "scope_mode=reduced" % n
    )


def test_quiet_wire_values_do_not_trip_the_kill_switch(gate, fixture):
    """THE EXACT STRINGS ci.yml PRODUCES ON AN ORDINARY PR. `vars.FULL_CI` is the
    EMPTY STRING when the repository variable is unset, and the label check
    `contains(...)` renders the literal 'false', never an empty value. Both must
    read as "not forced". Comparing against 'true' rather than testing for
    non-emptiness is what makes that work, and this case exists so nobody can later
    relax it to `[[ -n "$FORCE_FULL_CI" ]]` and make every PR full while the engine
    looks perfectly healthy."""
    run = fixture.run_gate("quietwire", env={"FORCE_FULL_CI": "", "FULL_CI_LABEL": "false"})
    gate.assert_exit_code(0, run.rc, "the gate must always exit 0")
    gate.assert_contains(
        run.emitted,
        "scope_mode=reduced",
        "an empty FORCE_FULL_CI and a literal 'false' label must NOT force full",
    )
    n = run.count_false()
    if n == 0:
        gate.log_fail(
            "the quiet wire values suppressed every false line -- the kill switch is "
            "firing on an ordinary PR.\n--- gate.log ---\n%s" % run.log
        )
    gate.assert_eq(n, 17, "and the reduction must be the same one an unset environment produces")
    gate.log_pass("the empty-string and literal-'false' wire values leave the kill switch disarmed")


def test_the_deciding_plan_is_the_baseline_plan(gate, fixture):
    """The reduction above can only come from `--resolve-baseline`: the merge-base
    classify over B..C2 also touches docs/a.md, and would classify identically here,
    so the two are told apart by WHICH artifact plan.json was built from. plan.json
    carries the baseline walk's own fields; a plan.json written from
    scope-classify.json cannot have them."""
    run = fixture.run_gate("deciding")
    gate.assert_exit_code(0, run.rc, "the gate must always exit 0")
    plan = run.plan()
    gate.assert_eq(
        str((plan.get("baseline") or {}).get("sha")),
        fixture.c1_sha,
        "plan.json must be the BASELINE plan (it carries the resolved baseline sha), not "
        "the merge-base classify",
    )
    gate.assert_eq(
        str(plan.get("run_id")),
        str(CURRENT_RUN_ID),
        "and it must name THIS run, or the reconciler refuses it as substituted evidence",
    )
    gate.log_pass("the plan that gates jobs is the plan the reconciler will audit")


def test_engine_failure_emits_no_false_line(gate, fixture):
    """(b) THE SAFETY PROPERTY. An engine that cannot reach the API must not shrink
    the run by a single job."""
    run = fixture.run_gate("enginefail", env={"SCOPE_GH_FAIL": "1"})
    gate.assert_exit_code(0, run.rc, "an engine failure must still exit 0")
    gate.assert_eq(
        run.count_false(), 0, "an engine that cannot reach the API must not skip a single job"
    )
    gate.assert_contains(
        run.emitted,
        "scope_mode=full",
        "and must say so as full, so the reconcile step stays tolerant",
    )

    # CONTROL: the same fixture, same command, working shim. If this did not produce
    # false lines, the assertion above would be measuring the fixture rather than
    # the failure.
    control = fixture.run_gate("enginefail-control")
    gate.assert_exit_code(0, control.rc, "the control run must exit 0")
    n = control.count_false()
    if n == 0:
        gate.log_fail(
            "CONTROL FAILED: the same fixture with a working gh shim also emitted zero "
            "false lines, so the failure case proves nothing.\n--- gate.log ---\n%s" % control.log
        )
    gate.log_pass(
        "an engine failure emits zero false lines (control: the same fixture emits %d)" % n
    )


def test_operator_override_forces_full_without_running_the_engine(gate, fixture):
    """(c) BOTH KILL SWITCHES, and the half that makes them worth having."""
    for switch in ("FORCE_FULL_CI", "FULL_CI_LABEL"):
        run = fixture.run_gate("override-%s" % switch, env={switch: "true"})
        gate.assert_exit_code(0, run.rc, "%s must still exit 0" % switch)
        gate.assert_eq(run.count_false(), 0, "%s must not skip a single job" % switch)
        gate.assert_contains(run.emitted, "scope_mode=full", "%s must report full" % switch)

        # The override must be legible in the artifact, not just in the outputs: a
        # later run reads this plan as a baseline candidate and an operator reads it
        # to find out why a round was full.
        plan = run.plan()
        reasons = json.dumps(plan.get("full_reasons")) + "|" + str(plan.get("mode"))
        gate.assert_contains(
            reasons,
            "operator-forced-full",
            "%s must name itself in the plan's full_reasons" % switch,
        )
        gate.assert_contains(reasons, "|full", "%s must produce a full plan" % switch)

        # THE ENGINE MUST NOT HAVE RUN. An operator forcing a full round must not
        # depend on the engine being healthy enough to answer, and must not wait on
        # a baseline walk. No scope-baseline.json means neither happened.
        if (run.outdir / "scope-baseline.json").exists():
            gate.log_fail(
                "%s ran the baseline walk anyway -- the kill switch is downstream of the "
                "thing it exists to bypass" % switch
            )
    gate.log_pass("both kill switches force full, name themselves in the plan, and skip the engine")


def test_plan_write_failure_emits_nothing_and_still_exits_zero(gate, fixture):
    """(d) AN UNWRITABLE PLAN. A DIRECTORY where the writer expects a file."""
    outdir = fixture.out_dir("planfail")
    (outdir / "plan.json").mkdir(parents=True, exist_ok=True)
    run = fixture.run_gate("planfail")
    gate.assert_exit_code(0, run.rc, "an unwritable plan must not fail the job")
    gate.assert_eq(
        len(run.emitted.splitlines()),
        0,
        "an unwritable plan must emit NO output at all, not even scope_mode",
    )
    gate.assert_contains(
        run.log,
        "plan writer FAILED",
        "and must say so loudly rather than looking like a clean full round",
    )

    # CONTROL: the same case name without the planted directory emits lines.
    shutil.rmtree(outdir)
    control = fixture.run_gate("planfail")
    gate.assert_exit_code(0, control.rc, "the control run must exit 0")
    n = control.count_false()
    if n == 0:
        gate.log_fail(
            "CONTROL FAILED: the same run without the planted directory also emitted "
            "nothing.\n--- gate.log ---\n%s" % control.log
        )
    gate.log_pass(
        "a plan-write failure emits nothing and exits 0 (control: the same run emits %d)" % n
    )


def test_unset_output_file_decides_nothing(gate, fixture):
    """The old shadow behaviour, kept reachable: a local run has no `$GITHUB_OUTPUT`
    and must neither crash nor invent one. It must still write the plan, which is
    what makes `SCOPE_SHADOW_OUT=... scope-shadow.sh` a usable way to see what a
    change WOULD scope to."""
    run = fixture.run_gate("nooutput", unset=("OUTPUT_FILE",))
    gate.assert_exit_code(0, run.rc, "a run with no OUTPUT_FILE must exit 0")
    gate.assert_eq(len(run.emitted.splitlines()), 0, "and must write nothing anywhere")
    plan_path = run.outdir / "plan.json"
    if not (plan_path.is_file() and plan_path.stat().st_size > 0):
        gate.log_fail(
            "a run with no OUTPUT_FILE must still write the plan, or the local diagnostic "
            "path is gone"
        )
    gate.log_pass("an unset OUTPUT_FILE decides nothing but still writes the plan")
