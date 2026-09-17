"""Differential: `rediacc_ci.security.workflow_gates` against its twin
`.ci/scripts/security/check-workflow-gates.sh` (`check:ci-workflow-gates`).

THE COMPARISON IS BYTE FOR BYTE ON BOTH STREAMS, and that is affordable here in
a way it usually is not: 788 of the twin's 1108 lines were ALREADY Python, sitting
in six `python3 - <<'PYEOF'` heredocs, so the port transcribes them rather than
rewording them. Anything short of byte equality would therefore be a
transcription error, not a legitimate rewrite. Two cases are exempted by name
below, each with its own test saying why.

WHY A FIXTURE TREE AND NOT ONLY THE REAL REPO. The real tree is green, and a
differential over two silent gates proves nothing (`scripts/lib/shadow-gate.ts`
calls that `VACUOUS_BOTH_EMPTY` and refuses it). Every case here builds a tree
that makes a specific check FAIL, and `test_the_real_repository_agrees` is the
one clean-tree case, kept because the six checks read seven different real
inputs there that no fixture reproduces.

WHY THE TWIN IS COPIED INTO THE FIXTURE. Both sides resolve the repository root
from their OWN location -- `${BASH_SOURCE[0]}/../../..` in the twin
(`check-workflow-gates.sh:57-58`), `paths.repo_root()` in the port -- and CHECKS
5 and 6 read `$ROOT_DIR` rather than `$WORKFLOWS_DIR`. Pointing only
`WORKFLOWS_DIR` at a fixture would leave those two checks running against the
REAL repository underneath every case. Copying both implementations to the same
relative paths inside the fixture is what makes all six checks fixture-scoped.

K=5 LEDGER: `.ci/shadow/w7p6-workflow-gates.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.security import workflow_gates

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/check-workflow-gates.sh"
PORT_REL = ".ci/rediacc_ci/security/workflow_gates.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

# The minimum of the package a path-invoked port needs. Deliberately short: the fixture must not become a second copy of the repository.
PACKAGE_FILES = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

WATCHDOG = """name: watchdog
on: push
jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Monitor jobs and cancel on failure
        run: echo monitoring
"""

BWS_JOB = """name: bws
on: push
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: |
            .github
            %s
      - uses: ./.github/actions/bws-secrets
        with:
          names: TOKEN
"""

SLIM_OK = """name: slim
on: push
jobs:
  j:
    runs-on: ubuntu-slim
    timeout-minutes: 14
    steps:
      - run: echo
"""

CALLEE = """name: callee
on:
  workflow_call:
    inputs:
      target:
        required: true
        type: string
    secrets:
      TOKEN:
        required: true
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.TOKEN }} ${{ inputs.target }}
"""

CALLER = """name: caller
on: push
jobs:
  call:
    uses: ./.github/workflows/callee.yml
    with:
      target: x
    secrets:
      TOKEN: ${{ secrets.TOKEN }}
"""

REGISTRY = """callers:
  - caller: private/acct/.github/workflows/review.yml
    repo: rediacc/account
    pinned_at: main
    calls: .github/workflows/callee.yml
    passes_inputs: [target]
    passes_secrets: [TOKEN]
"""

EXT_CALLER = """name: review
on: push
jobs:
  r:
    uses: rediacc/console/.github/workflows/callee.yml@main
    with:
      target: x
    secrets:
      TOKEN: ${{ secrets.TOKEN }}
"""


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree both implementations resolve as their own repository root.

    THE BASELINE IS GREEN, and that took a correction. The first version of this
    helper wrote only the two workflows a case needed, which left CHECK 3 blind
    (no ubuntu-slim job) and CHECK 4 blind (no registry) under EVERY case: both
    sides agreed, so `assert_same` passed, and every exit code was 1 for reasons
    that had nothing to do with the case. `test_the_baseline_fixture_is_green` is
    the control that keeps it honest, so a test asserting rc 0 or rc 1 is
    asserting something about its own subject.
    """
    fx = tmp_path / "tree"
    for rel in (TWIN_REL, *PACKAGE_FILES):
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    (fx / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    wf(fx, "watchdog-monitor.yml", WATCHDOG)  # CHECK 6's anchor
    wf(fx, "bws.yml", BWS_JOB % ".ci/config")  # CHECK 5's non-vacuous input
    wf(fx, "slim.yml", SLIM_OK)  # CHECK 3's coverage
    wf(fx, "callee.yml", CALLEE)  # CHECK 2's contract
    wf(fx, "caller.yml", CALLER)
    (fx / ".github" / "external-callers.yml").write_text(REGISTRY, encoding="utf-8")
    ext = fx / "private" / "acct" / ".github" / "workflows"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "review.yml").write_text(EXT_CALLER, encoding="utf-8")  # CHECK 4's caller
    return fx


def wf(fx: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = fx / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _env(fx: pathlib.Path, side: str, extra: dict[str, str]) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `REDIACC_CI_ROOT` is deliberately absent: it is the one seam the port has and
    the twin does not, and a differential that set it would be comparing two
    different roots.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if side == "new":
        env["PYTHONPATH"] = str(fx / ".ci")
    env.update(extra)
    return env


def run_both(
    fx: pathlib.Path, port_rel: str = PORT_REL, **envvars: str
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """Both implementations, same tree, same environment. Streams never merged."""
    results = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / port_rel)]),
    ):
        proc = subprocess.run(
            argv,
            env=_env(fx, side, envvars),
            cwd=str(fx),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        results.append(
            (
                proc.returncode,
                proc.stdout.replace(str(fx), "<fx>"),
                proc.stderr.replace(str(fx), "<fx>"),
            )
        )
    return results[0], results[1]


def assert_same(old: tuple[int, str, str], new: tuple[int, str, str]) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def test_the_baseline_fixture_is_green(tmp_path: pathlib.Path) -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE.

    Without it, a case that asserts exit 1 proves nothing: the tree might have
    been failing CHECK 3 and CHECK 4 for want of a slim job and a registry, which
    is exactly what the first version of this file did.
    """
    fx = build_fixture(tmp_path)
    old, new = run_both(fx)
    assert old[0] == 0, "the baseline fixture is not green:\n%s" % old[2]
    assert_same(old, new)


# --------------------------------------------------------------------------- The real repository ---------------------------------------------------------------------------


def test_the_real_repository_agrees() -> None:
    """The only clean-tree case, and the only one that reads all seven real inputs.

    `.github/workflows`, `.github/external-callers.yml`, `private/*/.github/
    workflows`, `.ci/breakpoint/workflow`, `watchdog-monitor.yml` and the two
    submodule caller files are none of them reproducible in a fixture. Both sides
    must agree on the info lines too, which carry the counts (`2 external caller
    call-site(s)`, `11 sparse Bitwarden-fetching job(s)`) that would collapse
    silently if a glob stopped matching.
    """
    results = []
    for side, argv in (
        ("old", ["bash", str(TWIN)]),
        ("new", ["python3", str(PORT)]),
    ):
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
        }
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        proc = subprocess.run(
            argv, env=env, cwd=str(ROOT), capture_output=True, text=True, check=False, timeout=300
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    assert_same(results[0], results[1])
    # Anti-vacuity for this test itself: it must have SEEN the counts, not just matched two empty strings.
    assert "external caller call-site(s) verified" in results[0][1]
    assert "sparse Bitwarden-fetching job(s) check out the map" in results[0][1]


def test_colour_is_emitted_when_ci_is_not_true(tmp_path: pathlib.Path) -> None:
    """`RED='\\033[0;31m'` + `echo -e`, so the real bytes are escape sequences.

    Driven with CI unset rather than `CI=true`, which is the branch every local
    run takes and the one a port that printed plain text would silently lose.
    Note `CI=""`: the twin tests `[[ "${CI:-}" == "true" ]]`, an equality against
    the string, so an exported-empty value keeps the colours ON.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "a.yml",
        "name: a\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo\n",
    )
    old, new = run_both(fx, CI="")
    assert "\033[0;32msuccess:" in old[1], "the twin did not colour its success line"
    assert_same(old, new)


# --------------------------------------------------------------------------- CHECK 1 ---------------------------------------------------------------------------


def test_check1_reports_a_needs_result_if_without_an_override(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "a.yml",
        "name: a\non: push\njobs:\n"
        "  one:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"
        "  two:\n    runs-on: ubuntu-latest\n"
        "    if: needs.one.result == 'success'\n    steps:\n      - run: echo\n",
    )
    old, new = run_both(fx)
    assert old[0] == 1
    assert "has if: without always()/!cancelled()" in old[2]
    assert_same(old, new)


def test_check1_accepts_every_documented_override(tmp_path: pathlib.Path) -> None:
    """The NEGATIVE control. A gate with only positive cases flags the whole tree."""
    fx = build_fixture(tmp_path)
    body = "name: a\non: push\njobs:\n  one:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"
    for i, override in enumerate(
        ("always()", "! cancelled()", "!cancelled()", "failure()", "success()")
    ):
        # DOUBLE-QUOTED, and that is not cosmetic: a bare `!` opens a YAML TAG, so `if: !cancelled() && ...` does not parse and CHECK 1 reports a yaml-error instead of the override it was meant to accept. The first version of this case did exactly that and looked like a port defect.
        body += (
            "  j%d:\n    runs-on: ubuntu-latest\n"
            "    if: \"%s && needs.one.result == 'success'\"\n"
            "    steps:\n      - run: echo\n" % (i, override)
        )
    wf(fx, "a.yml", body)
    old, new = run_both(fx)
    assert "always()/!cancelled() override" in old[1], "CHECK 1 did not pass"
    assert_same(old, new)


def test_check1_walks_and_check3_does_not(tmp_path: pathlib.Path) -> None:
    """The twin's own divergence: `os.walk` at :164 against `os.listdir` at :527.

    A workflow in a SUBDIRECTORY is audited for the always() rule and invisible
    to the slim-timeout rule. Blast radius on the real tree is zero -- GitHub
    itself only reads `.github/workflows/*.yml`, and `find .github/workflows
    -mindepth 1 -type d` counts 0 -- so this is reachable only through a fixture,
    and it is pinned rather than repaired because repairing it means editing a
    registered gate.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "top.yml",
        "name: t\non: push\njobs:\n  a:\n    runs-on: ubuntu-slim\n"
        "    timeout-minutes: 10\n    steps:\n      - run: echo\n",
    )
    nested = fx / ".github" / "workflows" / "nested"
    nested.mkdir()
    (nested / "deep.yml").write_text(
        "name: d\non: push\njobs:\n  b:\n    runs-on: ubuntu-slim\n"
        "    if: needs.a.result == 'success'\n    steps:\n      - run: echo\n",
        encoding="utf-8",
    )
    old, new = run_both(fx)
    assert "nested/deep.yml: job 'b' has if:" in old[2], "CHECK 1 did not descend"
    assert "deep.yml: job 'b' runs on ubuntu-slim without timeout-minutes" not in old[2], (
        "CHECK 3 descended after all; the divergence this test pins is gone"
    )
    assert_same(old, new)


def test_check1_refuses_an_empty_workflow_tree(tmp_path: pathlib.Path) -> None:
    """Zero inputs is a failure. Exit 3 inside, exit 1 out, and it says why."""
    fx = build_fixture(tmp_path)
    for stale in (fx / ".github" / "workflows").glob("*.yml"):
        stale.unlink()
    old, new = run_both(fx)
    assert old[0] == 1
    assert "no workflow YAML parsed -- this check is blind" in old[2]
    assert_same(old, new)


def test_a_missing_workflow_directory_is_a_failure(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    old, new = run_both(fx, WORKFLOWS_DIR=str(fx / "nowhere"))
    assert old[0] == 1
    assert "this check is blind" in old[2]
    assert_same(old, new)


# --------------------------------------------------------------------------- CHECK 2 ---------------------------------------------------------------------------


def test_check2_a_reading_an_undeclared_secret(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(fx, "callee.yml", CALLEE.replace("${{ inputs.target }}", "${{ secrets.GHOST }}"))
    wf(fx, "caller.yml", CALLER)
    old, new = run_both(fx)
    assert "reads secrets.GHOST but does not declare it" in old[2]
    assert_same(old, new)


def test_check2_a_comment_is_not_a_use(tmp_path: pathlib.Path) -> None:
    """`:256-258`. A whole-line `# ... secrets.X ...` must not count as a read.

    The negative control for `strip_comment_lines`: with the comment counted as a
    use, CHECK 2 would demand a declaration for something nothing reads.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "callee.yml",
        CALLEE.replace(
            "jobs:", "# retired 2026-01-01: secrets.GHOST is no longer read here\njobs:"
        ),
    )
    wf(fx, "caller.yml", CALLER)
    old, new = run_both(fx)
    assert "secrets.GHOST" not in old[2], "the comment counted as a use"
    assert_same(old, new)


def test_check2_a_trailing_comment_still_counts_as_a_use(tmp_path: pathlib.Path) -> None:
    """The other half, and it is the twin's real behaviour, not an oversight.

    Only `lstrip().startswith('#')` is blanked, so `run: echo  # secrets.GHOST`
    is still a read. Pinned so a port that blanked from the first `#` onward
    would be caught.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "callee.yml",
        CALLEE.replace(
            "      - run: echo ${{ secrets.TOKEN }} ${{ inputs.target }}",
            "      - run: echo ${{ secrets.TOKEN }} ${{ inputs.target }}  # secrets.GHOST",
        ),
    )
    wf(fx, "caller.yml", CALLER)
    old, new = run_both(fx)
    assert "reads secrets.GHOST" in old[2], "a trailing comment stopped counting as a use"
    assert_same(old, new)


def test_check2_a2_declaring_a_secret_nothing_reads(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "callee.yml",
        CALLEE.replace("    secrets:\n", "    secrets:\n      UNREAD:\n        required: false\n"),
    )
    wf(fx, "caller.yml", CALLER)
    old, new = run_both(fx)
    assert "declares secret UNREAD under workflow_call but never reads it" in old[2]
    assert_same(old, new)


def test_check2_b_a_caller_omitting_a_required_secret(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(fx, "callee.yml", CALLEE)
    wf(fx, "caller.yml", CALLER.replace("      TOKEN: ${{ secrets.TOKEN }}\n", "      OTHER: x\n"))
    old, new = run_both(fx)
    assert "does not pass required secret TOKEN" in old[2]
    assert "passes secret OTHER, which callee.yml never declares" in old[2]
    assert_same(old, new)


def test_check2_c_a_caller_passing_a_dead_input(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(fx, "callee.yml", CALLEE)
    wf(fx, "caller.yml", CALLER.replace("      target: x\n", "      target: x\n      ghost: y\n"))
    old, new = run_both(fx)
    assert "passes input ghost, which callee.yml never declares" in old[2]
    assert_same(old, new)


def test_check2_calling_a_workflow_that_does_not_exist(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(fx, "caller.yml", CALLER.replace("callee.yml", "gone.yml"))
    old, new = run_both(fx)
    assert "calls ./.github/workflows/gone.yml, which does not exist" in old[2]
    assert_same(old, new)


def test_check2_secrets_inherit_skips_the_secret_arm(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control: `secrets: inherit` must not be read as a mapping."""
    fx = build_fixture(tmp_path)
    wf(fx, "callee.yml", CALLEE)
    wf(
        fx,
        "caller.yml",
        CALLER.replace(
            "    secrets:\n      TOKEN: ${{ secrets.TOKEN }}\n", "    secrets: inherit\n"
        ),
    )
    old, new = run_both(fx)
    assert "does not pass required secret" not in old[2]
    assert_same(old, new)


def test_check2_on_parsed_as_the_boolean_true(tmp_path: pathlib.Path) -> None:
    """YAML 1.1 turns a bare `on:` key into `True`; `workflow_call` looks under both.

    NO `import yaml` HERE. pyyaml is not installed for the interpreter running
    pytest (`.ci/bootstrap.sh doctor` resolves pytest out of a uv tool
    environment), while the `python3` both sides are spawned as does have it.
    Importing it at test level turned this case into a `ModuleNotFoundError`
    that read like a port defect. The boolean fold is asserted through the real
    parse, in the subprocess, by proving the contract arms fired at all.
    """
    fx = build_fixture(tmp_path)
    old, new = run_both(fx)
    assert "does not pass required" not in old[2]
    # The contract arms only run when `workflow_call` RESOLVED, which for this callee is only possible through the `doc.get(True)` branch.
    assert workflow_gates.workflow_call({True: {"workflow_call": {"secrets": {}}}}) == {
        "secrets": {}
    }
    assert_same(old, new)


# --------------------------------------------------------------------------- CHECK 3 ---------------------------------------------------------------------------


def _slim(fx: pathlib.Path, extra: str) -> None:
    wf(
        fx,
        "slim.yml",
        "name: s\non: push\njobs:\n  j:\n    runs-on: ubuntu-slim\n%s"
        "    steps:\n      - run: echo\n" % extra,
    )


def test_check3_a_slim_job_without_a_timeout(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    _slim(fx, "")
    old, new = run_both(fx)
    assert "runs on ubuntu-slim without timeout-minutes" in old[2]
    assert_same(old, new)


def test_check3_a_slim_job_above_the_ceiling(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    _slim(fx, "    timeout-minutes: 20\n")
    old, new = run_both(fx)
    assert "above the 14-minute ceiling" in old[2]
    assert_same(old, new)


def test_check3_a_non_literal_timeout(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    _slim(fx, "    timeout-minutes: ${{ matrix.t }}\n")
    old, new = run_both(fx)
    assert "has a non-literal timeout-minutes" in old[2]
    assert_same(old, new)


def test_check3_a_slim_job_under_the_ceiling_passes(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control, and it also proves CHECK 3 saw a slim job at all."""
    fx = build_fixture(tmp_path)
    _slim(fx, "    timeout-minutes: 14\n")
    old, new = run_both(fx)
    assert "Every ubuntu-slim job declares timeout-minutes <= 14" in old[1]
    assert_same(old, new)


def test_check3_a_list_runs_on_containing_slim(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "slim.yml",
        "name: s\non: push\njobs:\n  j:\n    runs-on: [self-hosted, ubuntu-slim]\n"
        "    steps:\n      - run: echo\n",
    )
    old, new = run_both(fx)
    assert "runs on ubuntu-slim without timeout-minutes" in old[2]
    assert_same(old, new)


def test_check3_no_slim_job_is_blind_when_coverage_is_required(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    (fx / ".github" / "workflows" / "slim.yml").unlink()  # the baseline supplies one
    old, new = run_both(fx, SLIM_TIMEOUT_REQUIRE_COVERAGE="true")
    assert "-- this check is blind" in old[2]
    assert_same(old, new)


def test_check3_the_ceiling_is_overridable(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    _slim(fx, "    timeout-minutes: 14\n")
    old, new = run_both(fx, SLIM_TIMEOUT_MAX="10")
    assert "above the 10-minute ceiling" in old[2]
    assert_same(old, new)


def test_a_non_numeric_ceiling_is_a_traceback_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The one exit-code-only case, and the divergence is NAMED not hidden.

    `int(sys.argv[2])` at `:520` has no guard, so `SLIM_TIMEOUT_MAX=abc` kills
    the heredoc with a `ValueError` and bash then blames "ubuntu-slim timeout
    violations" for what is a configuration error. Both sides do exactly that;
    only the traceback's own file and line differ, which they must, so this case
    compares the exit code and the bash-level lines and asserts the traceback
    exists on both rather than pretending it is the same text.
    """
    fx = build_fixture(tmp_path)
    _slim(fx, "    timeout-minutes: 14\n")
    old, new = run_both(fx, SLIM_TIMEOUT_MAX="abc")
    assert old[0] == new[0] == 1
    assert old[1] == new[1], "stdout must still agree"
    for side in (old, new):
        assert "ValueError: invalid literal for int() with base 10: 'abc'" in side[2]
        assert "error: ubuntu-slim timeout violations (see above)." in side[2]
    # Everything OUTSIDE the traceback must match byte for byte.
    assert _without_traceback(old[2]) == _without_traceback(new[2])


def _without_traceback(text: str) -> str:
    keep, skipping = [], False
    for line in text.split("\n"):
        if line.startswith("Traceback (most recent call last)"):
            skipping = True
            continue
        if skipping:
            if (
                line.startswith(("  ", "\t"))
                or line == ""
                or re.match(r"^\S+(Error|Exception):", line)
            ):
                continue
            skipping = False
        keep.append(line)
    return "\n".join(keep)


# --------------------------------------------------------------------------- CHECK 4 ---------------------------------------------------------------------------


def ec_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """The baseline already carries a registry and one external caller."""
    return build_fixture(tmp_path)


def run_ec(fx: pathlib.Path, **extra: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """CHECK 4 with everything resolved explicitly.

    The baseline tree would derive the same three values, but naming them here
    keeps the CHECK 4 cases readable and exercises the override seam the twin
    documents at `:104-119`.
    """
    return run_both(
        fx,
        EXTERNAL_CALLERS_FILE=str(fx / ".github" / "external-callers.yml"),
        EXTERNAL_CALLERS_ROOT=str(fx),
        REAL_WORKFLOW_TREE="true",
        **extra,
    )


def test_check4_a_matching_registry_passes(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control, and it prints the count that proves it verified something."""
    fx = ec_fixture(tmp_path)
    old, new = run_ec(fx)
    assert "info: 1 external caller call-site(s) verified" in old[1]
    assert_same(old, new)


def test_check4_pin_drift(tmp_path: pathlib.Path) -> None:
    fx = ec_fixture(tmp_path)
    path = fx / "private" / "acct" / ".github" / "workflows" / "review.yml"
    path.write_text(EXT_CALLER.replace("@main", "@v2"), encoding="utf-8")
    old, new = run_ec(fx)
    assert "pins .github/workflows/callee.yml@v2, registry says @main" in old[2]
    assert_same(old, new)


def test_check4_an_unregistered_external_caller(tmp_path: pathlib.Path) -> None:
    fx = ec_fixture(tmp_path)
    ext = fx / "private" / "acct" / ".github" / "workflows"
    (ext / "other.yml").write_text(EXT_CALLER, encoding="utf-8")
    old, new = run_ec(fx)
    assert "is not declared in external-callers.yml" in old[2]
    assert_same(old, new)


def test_check4_a_missing_required_field(tmp_path: pathlib.Path) -> None:
    fx = ec_fixture(tmp_path)
    (fx / ".github" / "external-callers.yml").write_text(
        REGISTRY.replace("    pinned_at: main\n", ""), encoding="utf-8"
    )
    old, new = run_ec(fx)
    assert "caller #0 is missing pinned_at" in old[2]
    assert_same(old, new)


def test_check4_an_empty_registry_is_blind(tmp_path: pathlib.Path) -> None:
    fx = ec_fixture(tmp_path)
    (fx / ".github" / "external-callers.yml").write_text("callers: []\n", encoding="utf-8")
    old, new = run_ec(fx)
    assert "declares no callers" in old[2]
    assert_same(old, new)


def test_check4_stands_down_on_a_fixture_tree_with_no_registry(tmp_path: pathlib.Path) -> None:
    """`:110-119`: the registry is derived ONLY when WORKFLOWS_DIR is the default.

    So the directory has to be a genuinely different one; passing the default
    path explicitly still takes the real-tree branch, which is what the first
    version of this case did.
    """
    fx = build_fixture(tmp_path)
    alt = fx / "elsewhere" / "workflows"
    alt.mkdir(parents=True)
    (alt / "a.yml").write_text(
        "name: a\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo\n",
        encoding="utf-8",
    )
    old, new = run_both(fx, WORKFLOWS_DIR=str(alt))
    assert "Skipping external-caller contract check (fixture tree: no registry)" in old[1]
    assert_same(old, new)


# --------------------------------------------------------------------------- CHECK 5 ---------------------------------------------------------------------------


def test_check5_a_cone_without_the_map(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(fx, "bws.yml", BWS_JOB % ".github/actions")
    old, new = run_both(fx)
    assert "sparse checkout does not include .ci/config" in old[2]
    assert_same(old, new)


def test_check5_is_vacuous_and_therefore_fails(tmp_path: pathlib.Path) -> None:
    """No Bitwarden job at all is a FAILURE, not a pass. `:935-947`."""
    fx = build_fixture(tmp_path)
    (fx / ".github" / "workflows" / "bws.yml").unlink()
    old, new = run_both(fx)
    assert "CHECK 5 asserted nothing" in old[2]
    assert_same(old, new)


def test_check5_ignores_a_yaml_extension(tmp_path: pathlib.Path) -> None:
    """`:894` globs `*.yml` only, while CHECKS 1/2/3 accept both extensions.

    Measured: 0 `.yaml` files under `.github/workflows` or
    `.ci/breakpoint/workflow` today, so the hole is latent rather than live --
    and GitHub does accept `.yaml`, so it is a hole. Pinned, not repaired.
    """
    fx = build_fixture(tmp_path)
    (fx / ".github" / "workflows" / "bws.yml").rename(fx / ".github" / "workflows" / "bws.yaml")
    old, new = run_both(fx)
    assert "CHECK 5 asserted nothing" in old[2], "CHECK 5 started seeing .yaml files"
    assert_same(old, new)


def test_check5_also_reads_the_breakpoint_workflow_dir(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    (fx / ".github" / "workflows" / "bws.yml").unlink()
    bp = fx / ".ci" / "breakpoint" / "workflow"
    bp.mkdir(parents=True)
    (bp / "breakpoint.yml").write_text(BWS_JOB % ".github/actions", encoding="utf-8")
    old, new = run_both(fx)
    assert "breakpoint.yml: job 'fetch'" in old[2]
    assert_same(old, new)


def test_check5_ignores_a_full_checkout(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control: the rule fires only when a sparse checkout EXISTS."""
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "bws.yml",
        "name: bws\non: push\njobs:\n  fetch:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: ./.github/actions/bws-secrets\n",
    )
    old, new = run_both(fx)
    assert "CHECK 5 asserted nothing" in old[2], "a full checkout was counted"
    assert_same(old, new)


# --------------------------------------------------------------------------- CHECK 6 ---------------------------------------------------------------------------


def test_check6_an_optional_step_before_the_monitor(tmp_path: pathlib.Path) -> None:
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - name: Shadow-secret compare\n        run: echo\n      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert "runs 'Shadow-secret compare' BEFORE" in old[2]
    assert_same(old, new)


def test_check6_prereqs_and_harmless_steps_are_allowed(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control for all three exemption routes at once."""
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - name: Fetch secrets from Bitwarden\n        run: echo\n"
            "      - name: Attempt cap (deterministic backstop)\n        run: echo\n"
            "      - name: Something optional\n        continue-on-error: true\n"
            "        timeout-minutes: 5\n        run: echo\n"
            "      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert "nothing optional precedes the watchdog's monitor step" in old[1]
    assert_same(old, new)


def test_check6_continue_on_error_alone_is_not_enough(tmp_path: pathlib.Path) -> None:
    """`harmless` needs BOTH properties; a step with no timeout can still HANG."""
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - name: Slow thing\n        continue-on-error: true\n        run: echo\n"
            "      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert "runs 'Slow thing' BEFORE" in old[2]
    assert_same(old, new)


def test_check6_a_named_checkout_is_exempt(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to pin the defect.

    The exemption used to read the step's NAME: the name list was built as
    `step.get("name") or str(step.get("uses"))`, so a checkout step lost the
    exemption the moment it carried a `name:` that did not itself contain the
    string `actions/checkout`. Measured on the real tree at the time: of the 144
    `actions/checkout` steps under `.github/workflows`, 139 are unnamed (exempt by
    the `uses:` fallback) and 5 are named (not exempt). `watchdog-monitor.yml`'s own
    checkout is one of the 139, which is the only reason the gate was green: a single
    ordinary edit (`name: Checkout`) turned this registered gate red on the one
    workflow it exists to guard, with a message telling the author to move the
    checkout AFTER the monitor, which would leave the monitor's own scripts off disk.

    Both sides now decide on `uses:` and nothing else, so the named form passes.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - uses: actions/checkout@v4",
            "      - name: Checkout\n        uses: actions/checkout@v4",
        ),
    )
    old, new = run_both(fx)
    assert old[0] == 0, "a named checkout still fires CHECK 6:\n%s" % old[2]
    assert "nothing optional precedes the watchdog's monitor step" in old[1]
    assert_same(old, new)


def test_check6_an_unnamed_checkout_is_exempt(tmp_path: pathlib.Path) -> None:
    """The other half of the pair above: the unnamed form must still pass too."""
    fx = build_fixture(tmp_path)
    old, new = run_both(fx)
    assert "nothing optional precedes the watchdog's monitor step" in old[1]
    assert_same(old, new)


def test_check6_a_name_that_merely_says_checkout_is_not_exempt(
    tmp_path: pathlib.Path,
) -> None:
    """THE NEGATIVE CONTROL FOR THE FIX, and the reason it is a fix and not a widening.

    A `run:` step called "actions/checkout" satisfied the OLD substring test and
    walked straight through the exemption. It has no `uses:` at all, so it cannot
    put anything on disk and it is exactly the sort of step the check exists to
    catch. Now it is caught.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - name: actions/checkout\n        run: echo not really\n      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert old[0] == 1, "a fake checkout name walked through the exemption"
    assert "runs 'actions/checkout' BEFORE" in old[2]
    assert_same(old, new)


def test_check6_a_non_checkout_uses_is_not_exempt(tmp_path: pathlib.Path) -> None:
    """`uses:` is not a blanket pass. A local action before the monitor still fires."""
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - uses: ./.github/actions/bws-secrets\n      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert old[0] == 1
    assert "runs './.github/actions/bws-secrets' BEFORE" in old[2]
    assert_same(old, new)


def test_check6_a_non_string_step_name(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10 in BOTH SIDES: `name: 5` used to be a TypeError.

    YAML gives back an int, the old code put it in the name list unconverted, and
    `"actions/checkout" in name` raised `TypeError: argument of type 'int' is not a
    container or iterable`. The heredoc died, bash saw a non-zero exit and printed
    "move the step after the monitor" -- ordering advice for a crash. The step is now
    labelled '5' and reported as the ordinary offender it is.
    """
    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - name: Monitor",
            "      - name: 5\n        run: echo\n      - name: Monitor",
        ),
    )
    old, new = run_both(fx)
    assert old[0] == 1
    assert "runs '5' BEFORE" in old[2]
    assert "Traceback" not in old[2], "the twin still crashes on a non-string name"
    assert_same(old, new)


def test_check2_a_workflow_that_is_not_a_mapping(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10: an UNRECORDED DIVERGENCE, found while testing CHECK 6.

    CHECK 2's (b)/(c) loop guarded with `(doc or {})`, which covers an EMPTY file and
    not one whose YAML parses to a scalar. The twin died with `AttributeError: 'str'
    object has no attribute 'get'` and then printed "Reusable-workflow contract
    violations (see above)" about a crash; the port already carried an `isinstance`
    guard and passed. Two implementations, two different answers, and no case in this
    file exercised it. The twin now carries the same guard.

    CHECK 6 still fails the run, because watchdog-monitor.yml is the file being
    mangled; the subject here is that CHECK 2 agrees and neither side tracebacks.
    """
    fx = build_fixture(tmp_path)
    wf(fx, "watchdog-monitor.yml", "not a mapping")
    old, new = run_both(fx)
    assert "Reusable-workflow secret/input contracts hold" in old[1]
    assert "Traceback" not in old[2], "the twin still crashes on a scalar workflow doc"
    assert_same(old, new)


def test_check6_an_unparseable_watchdog_says_so_instead_of_crashing(
    tmp_path: pathlib.Path,
) -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to pin the traceback.

    `doc = yaml.safe_load(...)` was followed straight by `doc.get("jobs")` with no
    `None` guard and no `isinstance` guard (CHECK 5 has had both all along), and the
    load itself was unprotected. Of the five ways the monitor anchor can go missing,
    THREE ended in a traceback -- empty document and non-mapping document raised
    `AttributeError`, a syntax error raised `yaml.YAMLError` -- and only two (a dict
    with no jobs, a renamed step) reached the check's own message. Bash printed its
    generic fix line on top of each, so the operator was told to reorder a step in a
    file that has no steps.

    All three now report their cause and still exit 1, and because neither side
    tracebacks any more this case can be compared with the ordinary `assert_same`
    rather than through `_without_traceback`: the two tracebacks quoted different
    files and different line numbers, so the strict comparison was unreachable here.
    """
    fx = build_fixture(tmp_path)
    shapes = [
        ("", "did not parse as a YAML mapping (got NoneType); CHECK 6 cannot report"),
        ("# only a comment\n", "did not parse as a YAML mapping (got NoneType)"),
        ("- a\n- b\n", "did not parse as a YAML mapping (got list)"),
        ("jobs: [\n", "is not parseable YAML (while parsing a flow node"),
    ]
    for body, expected in shapes:
        wf(fx, "watchdog-monitor.yml", body)
        old, new = run_both(fx)
        assert old[0] == 1, "shape %r stopped being a failure" % body
        assert expected in old[2], "shape %r said:\n%s" % (body, old[2])
        assert "the watchdog lost its monitor" not in old[2]
        assert "Traceback" not in old[2], "shape %r still crashes the twin" % body
        assert_same(old, new)


def test_check6_a_renamed_monitor_does_reach_the_vacuity_message(
    tmp_path: pathlib.Path,
) -> None:
    """The two-of-five case that works, so the finding above is exact."""
    fx = build_fixture(tmp_path)
    wf(fx, "watchdog-monitor.yml", WATCHDOG.replace("Monitor jobs and cancel on failure", "Watch"))
    old, new = run_both(fx)
    assert "the watchdog lost its monitor" in old[2]
    assert_same(old, new)


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_strip_comment_lines_blanks_the_line_and_keeps_the_count() -> None:
    text = "a\n  # secrets.X\nb # secrets.Y\n"
    assert workflow_gates.strip_comment_lines(text) == "a\n\nb # secrets.Y\n"


def test_workflow_call_reads_both_on_keys() -> None:
    assert workflow_gates.workflow_call({"on": {"workflow_call": {"secrets": {}}}}) == {
        "secrets": {}
    }
    assert workflow_gates.workflow_call({True: {"workflow_call": {"inputs": {}}}}) == {"inputs": {}}
    assert workflow_gates.workflow_call({"on": "push"}) == {}
    assert workflow_gates.workflow_call({"on": {"workflow_call": None}}) == {}
    assert workflow_gates.workflow_call(None) == {}
    assert workflow_gates.workflow_call(["a"]) == {}


def test_use_re_ignores_a_filename_and_finds_a_reference() -> None:
    """The lookbehind at `:229`: `set-account-worker-secrets.sh` is not a use."""
    assert workflow_gates.USE_RE.findall("uses: ./scripts/set-worker-secrets.sh") == []
    assert workflow_gates.USE_RE.findall("${{ secrets.TOKEN }}") == ["TOKEN"]
    assert workflow_gates.USE_RE.findall("a.secrets.TOKEN") == []


def test_harmless_requires_both_literals() -> None:
    assert workflow_gates.harmless({"continue-on-error": True, "timeout-minutes": 5})
    assert not workflow_gates.harmless({"continue-on-error": True, "timeout-minutes": 6})
    assert not workflow_gates.harmless({"continue-on-error": True, "timeout-minutes": 0})
    assert not workflow_gates.harmless({"continue-on-error": True})
    assert not workflow_gates.harmless({"continue-on-error": "${{ true }}", "timeout-minutes": 1})
    assert not workflow_gates.harmless({"timeout-minutes": 1})


def test_is_checkout_reads_uses_and_never_the_name() -> None:
    """The unit half of the CHECK 6 fix. Exported so it can be driven directly."""
    assert workflow_gates.is_checkout({"uses": "actions/checkout@v4"})
    assert workflow_gates.is_checkout({"name": "Checkout", "uses": "actions/checkout@v4"})
    assert workflow_gates.is_checkout(
        {"uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"}
    )
    # NOT a checkout: the name says so and the `uses:` does not.
    assert not workflow_gates.is_checkout({"name": "actions/checkout", "run": "echo"})
    assert not workflow_gates.is_checkout({"uses": "./.github/actions/bws-secrets"})
    assert not workflow_gates.is_checkout({"uses": "someone/actions/checkout@v4"})
    assert not workflow_gates.is_checkout({"run": "echo"})
    assert not workflow_gates.is_checkout({"uses": 5})


def test_step_label_survives_every_shape_yaml_can_hand_back() -> None:
    assert workflow_gates.step_label({"name": "Monitor"}) == "Monitor"
    assert workflow_gates.step_label({"uses": "actions/checkout@v4"}) == "actions/checkout@v4"
    assert workflow_gates.step_label({"name": "N", "uses": "u"}) == "N"
    # An empty or null name falls back to `uses:`, which is what the old inline `s.get("name") or ...` did and the only part of it worth keeping.
    assert workflow_gates.step_label({"name": "", "uses": "u"}) == "u"
    assert workflow_gates.step_label({"name": None, "uses": "u"}) == "u"
    # The shapes that used to raise TypeError one line later.
    assert workflow_gates.step_label({"name": 5}) == "5"
    assert workflow_gates.step_label({"name": ["a"], "uses": "u"}) == "u"
    assert workflow_gates.step_label({"run": "echo"}) == ""


def test_env_treats_an_exported_empty_value_as_unset() -> None:
    os.environ["WFG_PROBE"] = ""
    try:
        assert workflow_gates._env("WFG_PROBE", "fallback") == "fallback"
        os.environ["WFG_PROBE"] = "set"
        assert workflow_gates._env("WFG_PROBE", "fallback") == "set"
    finally:
        os.environ.pop("WFG_PROBE", None)


def test_the_exemption_list_is_a_list_not_a_set_literal() -> None:
    """`:302-306`: drained to `{}` a set literal becomes an empty DICT.

    The endgame for `DECLARED_UNUSED_OK` is empty, so the empty form has to be
    the safe one. This asserts the shape survives, in the port and in the twin.
    """
    assert isinstance(workflow_gates._DECLARED_UNUSED_OK, list)
    body = TWIN.read_text(encoding="utf-8")
    assert "_DECLARED_UNUSED_OK = [" in body
    assert "DECLARED_UNUSED_OK = set(_DECLARED_UNUSED_OK)" in body


# --------------------------------------------------------------------------- A PLANTED DEFECT, on a throwaway copy, never on the file on disk ---------------------------------------------------------------------------


def test_a_planted_regression_of_the_checkout_exemption_is_caught(
    tmp_path: pathlib.Path,
) -> None:
    """Plant the OLD defect back into the port and prove the comparison sees it.

    Until 2026-09-10 this test ran the other way round: it planted the obvious
    REPAIR (exempt on `uses:`) and proved the port then diverged from a twin that
    matched on the name. The bug is fixed in both sides now, so the tempting change
    is the reverse one -- somebody "restoring" the old substring test -- and that is
    what is planted here. Either way the claim is the same: a port may reword, never
    change which things it objects to.

    The real file is hashed before and after; the mutation lives only in the
    fixture's copy.
    """
    before = PORT.read_bytes()
    source = PORT.read_text(encoding="utf-8")
    anchor = "            if name in PREREQS or is_checkout(step) or harmless(step):\n"
    assert source.count(anchor) == 1, "the CHECK 6 exemption moved; this plant is stale"
    planted = source.replace(
        anchor,
        '            if name in PREREQS or "actions/checkout" in name or harmless(step):\n',
        1,
    )

    fx = build_fixture(tmp_path)
    wf(
        fx,
        "watchdog-monitor.yml",
        WATCHDOG.replace(
            "      - uses: actions/checkout@v4",
            "      - name: Checkout\n        uses: actions/checkout@v4",
        ),
    )
    (fx / PORT_REL).write_text(planted, encoding="utf-8")
    old, new = run_both(fx)
    assert old[0] == 0, "the control is broken: the twin fired on a named checkout"
    assert new[0] == 1, "the plant did not change the port's verdict"
    assert new[2] != old[2], "the plant produced identical stderr"

    after = PORT.read_bytes()
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest(), (
        "the real port file changed; the mutation escaped the fixture"
    )


def test_a_planted_recursive_check3_is_caught(tmp_path: pathlib.Path) -> None:
    """The second tempting repair: make CHECK 3 walk like CHECK 1.

    Same argument. `os.walk` there would be a better gate and a worse port.
    """
    before = PORT.read_bytes()
    source = PORT.read_text(encoding="utf-8")
    anchor = (
        "    names = sorted(f for f in os.listdir(workflows_dir) "
        'if f.endswith((".yml", ".yaml")))\n'
    )
    assert source.count(anchor) == 1, "CHECK 3's listing moved; this plant is stale"
    planted = source.replace(
        anchor,
        "    names = sorted(\n"
        "        os.path.relpath(os.path.join(r, f), workflows_dir)\n"
        "        for r, _d, fs in os.walk(workflows_dir)\n"
        "        for f in fs\n"
        '        if f.endswith((".yml", ".yaml"))\n'
        "    )\n",
        1,
    )

    fx = build_fixture(tmp_path)
    nested = fx / ".github" / "workflows" / "nested"
    nested.mkdir()
    (nested / "deep.yml").write_text(
        "name: d\non: push\njobs:\n  b:\n    runs-on: ubuntu-slim\n    steps:\n      - run: echo\n",
        encoding="utf-8",
    )
    (fx / PORT_REL).write_text(planted, encoding="utf-8")
    old, new = run_both(fx)
    assert "without timeout-minutes" not in old[2], "the control is broken: the twin descended"
    assert "without timeout-minutes" in new[2], "the plant did not change the port's findings"

    after = PORT.read_bytes()
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest()
