"""Port of `.ci/scripts/test/gates/test-ci-trace-branch.sh`.

ci-trace must be able to read a branch that has NO open PR, and the read must stay OPT-IN. Measured 2026-08-25 against Console CI run 32903007256 (b4b5797e on main) while that run was still in_progress: a branch tracer that answered from the PR query alone reported nothing at all.

HERMETIC: `gh` is shimmed, so this gate never touches the network. A gate that needs GitHub to be up is a gate that gets skipped on somebody else's outage.

WHAT THIS GATE CANNOT SEE, carried over unchanged: it does not prove the GraphQL field selection is still valid against the live schema. A deprecation surfaces at runtime as `unreadable`, which at least says so, but this gate stays green through it.

THE FAKE `gh` IS THE TWIN'S. `with_fake_gh` in test-helpers.sh cats ONE file for every call, which cannot tell the PR query from the branch query, and telling them apart is the entire subject here. So the twin writes its own router and this module writes the same one from a template.

TWO PLACES WHERE `$0` HAD TO BECOME "THIS MODULE", and they are not cosmetic:

  * `test_control_a_blind_caller_is_detected` greps `$0` to prove the caller
    enumeration still asks for UNTRACKED files. `$0` is the file making the
    claim, so here it is THIS file, and the assertion reads this module's own
    source for the `--others --exclude-standard` argument it passes to git.
  * `test_every_caller_handles_the_no_pr_state` excludes the gate's own fixture
    file from the caller sweep, because it calls `ci_rollup` deliberately
    without handling the state. Two files do that now, the twin and this module,
    so both are excluded BY PATH and the exclusion is printed in the pass line.

THE SWEEP IS A READ, NEVER A WRITE. The twin records that an earlier version wrote a probe file under `.ci/scripts/quality/` to exercise the untracked half of
the enumeration and that check-pool-writer-safety correctly rejected it; the
probe lives in a temp directory here for the same reason.

NO `xdist_group`. Shims and probes are written into pytest's own `tmp_path`; the
tree is read (git ls-files, and the two subject files) and never written.
"""

import os
import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-ci-trace-branch.sh"

HOOKS_DIR = paths.from_root(".claude", "hooks", "stop")
WL_CI = HOOKS_DIR / "wl_ci.py"
TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")

# The two files that call `ci_rollup` as a FIXTURE rather than as a consumer.
SELF_EXCLUDED = (
    BASH_TWIN,
    ".ci/rediacc_ci/tests/gates/test_gate_ci_trace_branch.py",
)

FAKE_GH = """#!/bin/bash
q="$*"
case "$q" in
  *pullRequests*) cat <<'JSON'
{"data":{"repository":{"pullRequests":{"nodes":%(pr_nodes)s}}}}
JSON
  ;;
  *qualifiedName*) cat <<'JSON'
{"data":{"repository":{"ref":%(ref_json)s}}}
JSON
  ;;
  *) echo '{"data":{}}' ;;
esac
"""

ROLLUP_OK = (
    '{"target":{"oid":"b4b5797e00000000000000000000000000000000",'
    '"statusCheckRollup":{"state":"SUCCESS","contexts":{"totalCount":2,'
    '"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":['
    '{"__typename":"CheckRun","name":"Quality","status":"COMPLETED",'
    '"conclusion":"SUCCESS","databaseId":1,"detailsUrl":"",'
    '"checkSuite":{"workflowRun":{"databaseId":9}}},'
    '{"__typename":"CheckRun","name":"Build","status":"COMPLETED",'
    '"conclusion":"SUCCESS","databaseId":2,"detailsUrl":"",'
    '"checkSuite":{"workflowRun":{"databaseId":9}}}]}}}}'
)

ROLLUP_PY = """
import sys, pathlib
sys.path.insert(0, sys.argv[1])
import wl_ci
state, info = wl_ci.ci_rollup(pathlib.Path("."), sys.argv[2], allow_branch=(sys.argv[3] == "1"))
if isinstance(info, dict):
    print("%s %s %s" % (state, info.get("source"), (info.get("sha") or "")[:8]))
else:
    print("%s - -" % state)
"""

# The `gh` the --run cases are driven against: one shim, four routed answers.
RUN_SHIM = """#!/bin/bash
case "$*" in
  *999999*) echo "failed to get run: HTTP 404: Not Found" >&2; exit 1 ;;
  *inflight*) echo '{"status":"in_progress","conclusion":null,"jobs":[{"name":"Tag & Release","conclusion":null}]}' ;;
  *redrun*)  echo '{"status":"completed","conclusion":"failure","jobs":[{"name":"Publish","conclusion":"failure"}]}' ;;
  *)         echo '{"status":"completed","conclusion":"success","jobs":[{"name":"Tag & Release","conclusion":"success"}]}' ;;
esac
"""

NUDGE_PY = """
import contextlib
import importlib.util
import io
import sys

spec = importlib.util.spec_from_file_location("t", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
base = {
    "verdict": "green", "detail": "d", "ref": "b", "source": "pr", "owner": "o",
    "name": "n", "head": "abc", "live": False, "waiting": 0, "failing": [],
    "soft": [], "cancelled": [], "truncated": False,
}


def emit(**kw):
    p = dict(base)
    p.update(kw)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m._emit(p, False)
    return "still a DRAFT" in buf.getvalue()


cases = [
    (dict(pr=1, draft=True), True),                        # the case it exists for
    (dict(pr=1, draft=False), False),                      # already flipped ready
    (dict(pr=None, draft=False, source="branch"), False),  # branch read, no PR at all
    (dict(pr=1, draft=True, verdict="red"), False),        # red is not the finish line
]
sys.exit(0 if all(emit(**k) == w for k, w in cases) else 1)
"""

# The mutation the --run control plants, by CONSTRUCTION rather than by sed over the live source.
MUTATE_PY = """
import io, sys
src, dst = sys.argv[1], sys.argv[2]
s = io.open(src, encoding="utf-8").read()
needle = 'if status == "completed":'
assert s.count(needle) == 1, "mutation anchor missing or ambiguous"
io.open(dst, "w", encoding="utf-8").write(s.replace(needle, "if True:", 1))
"""


def require_subjects(gate) -> None:
    for path in (WL_CI, TRACE):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))


def make_fake_gh(directory: pathlib.Path, pr_nodes: str, ref_json: str) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "gh"
    shim.write_text(FAKE_GH % {"pr_nodes": pr_nodes, "ref_json": ref_json}, encoding="utf-8")
    shim.chmod(0o755)
    return directory


def with_path(directory: pathlib.Path) -> dict:
    return {"PATH": "%s:%s" % (directory, os.environ.get("PATH", ""))}


def rollup_state(
    gate, bindir: pathlib.Path, ref: str, allow: str, module_dir: pathlib.Path | None = None
) -> str:
    """`rollup_state <ref> <allow_branch> [module_dir]` -> "<state> <source> <sha>"."""
    result = harness.run(
        [sys.executable, "-c", ROLLUP_PY, str(module_dir or HOOKS_DIR), ref, allow],
        env=with_path(bindir),
    )
    if result.rc != 0:
        gate.log_fail(
            "the ci_rollup probe did not run (rc=%d, stderr: %s)" % (result.rc, result.err.strip())
        )
    return result.out.strip()


def test_default_still_answers_no_pr(gate, tmp_path):
    gate.log_test("the DEFAULT must not silently become a branch read")
    require_subjects(gate)
    bindir = make_fake_gh(tmp_path / "bin", "[]", ROLLUP_OK)
    out = rollup_state(gate, bindir, "main", "0")
    gate.assert_eq("no-pr - -", out, "default allow_branch must yield no-pr, got: %s" % out)
    gate.log_pass("default is unchanged: no-pr")


def test_opt_in_reads_the_branch(gate, tmp_path):
    gate.log_test("allow_branch=True reads the branch rollup")
    require_subjects(gate)
    bindir = make_fake_gh(tmp_path / "bin", "[]", ROLLUP_OK)
    out = rollup_state(gate, bindir, "main", "1")
    gate.assert_eq("ok branch b4b5797e", out, "opt-in must read the branch, got: %s" % out)
    gate.log_pass("opt-in reads the branch and labels its source")


def test_missing_ref_is_no_ref_not_silence(gate, tmp_path):
    gate.log_test("a ref that does not exist must answer no-ref")
    require_subjects(gate)
    bindir = make_fake_gh(tmp_path / "bin", "[]", "null")
    out = rollup_state(gate, bindir, "nope", "1")
    gate.assert_eq("no-ref - -", out, "missing ref must be no-ref, got: %s" % out)
    gate.log_pass("missing ref is distinguishable from a branch with no checks")


def test_control_default_flipped_is_caught(gate, tmp_path):
    gate.log_test("CONTROL: flip the default and the first assertion must go red")
    # Built by CONSTRUCTION -- a copied module plus an APPENDED override. A pattern substitution could silently no-op if the signature were reworded, and the control would then pass against unmutated source.
    require_subjects(gate)
    moddir = tmp_path / "mutant"
    moddir.mkdir(parents=True)
    for module in sorted(HOOKS_DIR.glob("*.py")):
        (moddir / module.name).write_text(module.read_text(encoding="utf-8"), encoding="utf-8")
    mutant = moddir / "wl_ci.py"
    with open(mutant, "a", encoding="utf-8") as handle:
        handle.write(
            "\n\n_orig_ci_rollup = ci_rollup\n\n\n"
            "def ci_rollup(root, ref, allow_branch=False):  # noqa: F811\n"
            "    return _orig_ci_rollup(root, ref, allow_branch=True)\n"
        )
    if "_orig_ci_rollup" not in mutant.read_text(encoding="utf-8"):
        gate.log_fail("control was not planted -- the mutant module is unmodified")

    bindir = make_fake_gh(tmp_path / "bin", "[]", ROLLUP_OK)
    out = rollup_state(gate, bindir, "main", "0", moddir)
    if out == "no-pr - -":
        gate.log_fail("control did not fire: mutant still answered no-pr")
    gate.assert_eq(
        "ok branch b4b5797e", out, "mutant should have leaked a branch read, got: %s" % out
    )
    gate.log_pass("control fires: a flipped default is detectable")


def test_trace_names_its_source(gate):
    gate.log_test("the emitted line must name which source answered")
    require_subjects(gate)
    source = TRACE.read_text(encoding="utf-8")
    if "branch %s @ %s (no PR)" not in source:
        gate.log_fail("ci-trace.py no longer distinguishes a branch read in its output")
    if "allow_branch = bool(args.ref)" not in source:
        gate.log_fail("ci-trace.py no longer restricts the fallback to an EXPLICIT --ref")
    gate.log_pass("output distinguishes source; fallback stays opt-in")


def test_every_caller_handles_the_no_pr_state(gate):
    gate.log_test("EVERY ci_rollup caller must handle no-pr, not let it propagate")
    # ci_rollup returns a STATE, and a caller that ignores it hands `info` -- a plain string, not the payload dict -- to code expecting a rollup.
    #
    # Enumerated, never hardcoded, and from BOTH tracked and untracked files: a caller added but not yet committed is exactly when this slips in.
    git = harness.require_tool("git", "install git")
    root = paths.repo_root()
    listed: set[str] = set()
    for extra in ([], ["--others", "--exclude-standard"]):
        result = harness.run(
            [git, "-C", str(root), "ls-files", *extra, "*.py", "*.sh"],
        )
        if result.rc != 0:
            gate.log_fail(
                "git ls-files failed, so the caller enumeration saw nothing: %s"
                % result.err.strip()
            )
        listed.update(line for line in result.out.splitlines() if line.strip())

    definition = re.compile(r"\bdef ci_rollup|^[ \t]*ci_rollup\(\)[ \t]*\{", re.MULTILINE)
    callers = []
    for rel in sorted(listed):
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "ci_rollup(" not in text:
            continue
        # A DEFINITION IS NOT A CALLER. Skipping by filename would need a new
        # hardcoded entry per stub; skipping by shape is self-maintaining.
        if definition.search(text):
            continue
        # This gate's own fixtures call it deliberately without the state.
        if rel in SELF_EXCLUDED:
            continue
        callers.append(rel)

    # Anti-vacuity: a scan that found no callers proves nothing. ci-trace.py is a caller by construction, so zero means the enumeration broke.
    if not callers:
        gate.log_fail("found ZERO ci_rollup callers -- the enumeration broke, not the code")

    bad = [rel for rel in callers if "no-pr" not in (root / rel).read_text(encoding="utf-8")]
    if bad:
        gate.log_fail("these call ci_rollup but never handle its no-pr state: %s" % " ".join(bad))
    gate.log_pass(
        "all %d external caller(s) handle no-pr (%d fixture file(s) excluded by path: %s)"
        % (len(callers), len(SELF_EXCLUDED), ", ".join(SELF_EXCLUDED))
    )


def test_control_a_blind_caller_is_detected(gate, tmp_path):
    gate.log_test("CONTROL: a caller that ignores the state must be caught")
    # By construction: a fresh file that calls ci_rollup and never mentions no-pr. WRITTEN TO tmp_path, NOT THE REAL TREE -- the twin records that an earlier version wrote under .ci/scripts/quality/ and that check-pool-writer-safety was right to reject it.
    victim = tmp_path / "_probe_caller.py"
    victim.write_text(
        'state, info = wl_ci.ci_rollup(root, ref)\nprint(info["verdict"])\n', encoding="utf-8"
    )
    text = victim.read_text(encoding="utf-8")
    hit = "ci_rollup(" in text and "no-pr" not in text
    if not hit:
        gate.log_fail("CONTROL DID NOT FIRE: a blind caller read as compliant")

    # The untracked half of the enumeration, asserted at the source rather than by writing into the tree. `$0` in the twin is the file making the claim, so it is THIS file here. This proves the enumeration ASKS for untracked files, not that it received any.
    own = pathlib.Path(__file__).read_text(encoding="utf-8")
    if '"--others", "--exclude-standard"' not in own:
        gate.log_fail(
            "the caller enumeration no longer covers UNTRACKED files, which is when a new "
            "caller slips in"
        )
    gate.log_pass("control: a blind caller is detectable; untracked coverage asserted at source")


def test_green_draft_names_the_finish_sequence(gate):
    gate.log_test("GREEN on a still-draft PR must name the finish sequence")
    # Green is not the finish line: the PR still has to be flipped ready, reviewed, and its threads resolved. Driven through the REAL _emit in four directions rather than grepping the source for the string, because a nudge that never renders is the failure here.
    require_subjects(gate)
    result = harness.run([sys.executable, "-c", NUDGE_PY, str(TRACE)])
    if result.rc != 0:
        gate.log_fail(
            "the green+draft nudge did not behave in all four directions (rc=%d, stderr: %s)"
            % (result.rc, result.err.strip())
        )
    gate.log_pass("green+draft names the next command; ready, branch and red stay quiet")


def test_default_signature_is_false(gate):
    gate.log_test("the signature default itself must remain False")
    require_subjects(gate)
    if "def ci_rollup(root, ref, allow_branch=False):" not in WL_CI.read_text(encoding="utf-8"):
        gate.log_fail("ci_rollup's allow_branch default is no longer False")
    gate.log_pass("signature default is False")


def run_shim_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    shim = tmp_path / "runshim"
    shim.mkdir(parents=True, exist_ok=True)
    binary = shim / "gh"
    binary.write_text(RUN_SHIM, encoding="utf-8")
    binary.chmod(0o755)
    return shim


def test_dispatched_run_is_traced_by_id(gate, tmp_path):
    gate.log_test("--run reads a dispatched run, which a branch rollup CANNOT see")
    # WHY THIS EXISTS, measured 2026-08-26 on Release run 32968110599 (head 1c006e53). A branch's statusCheckRollup does NOT contain a workflow_dispatch run's check runs, so `--wait --ref main` printed GREEN and exited 0 while the release was mid-flight, twice, and /pr-merge step 5 instructed exactly that.
    #
    # The four exit codes below are the whole contract. `in_progress -> 2` is the
    # one that was broken; `unreadable -> 2` matters just as much, because a run
    # nobody could read must never read as a pass.
    require_subjects(gate)
    shim = run_shim_dir(tmp_path)
    expected = (
        ("inflight", 2, "an IN-FLIGHT dispatched run must exit 2 (the false-green that shipped)"),
        ("okrun", 0, "a completed/success run must exit 0"),
        ("redrun", 1, "a run with a failed job must exit 1"),
        ("999999", 2, "an UNREADABLE run must exit 2, never 0"),
    )
    for run, code, message in expected:
        result = harness.run([str(TRACE), "--run", run], env=with_path(shim))
        gate.assert_exit_code(code, result.rc, message)
    gate.log_pass("--run: in-flight=2, success=0, failed-job=1, unreadable=2")


def test_control_run_reader_can_fail(gate, tmp_path):
    gate.log_test("CONTROL: a --run reader that ignores status must be detectable")
    # Built BY CONSTRUCTION, not by sed over the live source: copy ci-trace, replace the status test so `in_progress` falls through to the green path, and require the in-flight case to stop being reported as in-flight.
    require_subjects(gate)
    shim = run_shim_dir(tmp_path)
    mutant = tmp_path / "ci-trace-mut.py"
    built = harness.run([sys.executable, "-c", MUTATE_PY, str(TRACE), str(mutant)])
    if built.rc != 0:
        gate.log_fail(
            "the mutant could not be built, so the control never ran: %s" % built.err.strip()
        )
    result = harness.run([sys.executable, str(mutant), "--run", "inflight"], env=with_path(shim))
    # The assertion is `!= 2`, not `== 0`, and the difference is the control
    # being honest. Deleting the status test does NOT make the in-flight run green: it falls through to the terminal branch, where conclusion is null, which is not in (success, skipped), so it reports RED (1). Either way the run has stopped being reported as in-flight, which is the property under test.
    if result.rc == 2:
        gate.log_fail(
            "CONTROL DID NOT FIRE: the mutated reader still reported the in-flight run as "
            "in-flight (rc=%d), so the real assertion proves nothing" % result.rc
        )
    gate.log_pass(
        "control fires: without the status test, in-flight stops being reported (rc=%d, not 2)"
        % result.rc
    )


def test_ci_nonblocking_contexts_selftest(gate):
    gate.log_test("ci-trace.py's own CI_NONBLOCKING_CONTEXTS fixture controls")
    # Review-found live on PR #579: --run reads a run's jobs endpoint DIRECTLY, a completely separate path from wl_ci.ci_classify's GraphQL contexts, so the fix landed on the branch-tracing path and never touched this one.
    require_subjects(gate)
    result = harness.run([sys.executable, str(TRACE), "--selftest"])
    if result.rc != 0:
        gate.log_fail(
            "ci-trace.py --selftest failed (rc=%d): %s" % (result.rc, result.combined.strip())
        )
    gate.log_pass("ci-trace.py --selftest: 3/3")
