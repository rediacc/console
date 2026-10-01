"""Port of `.ci/scripts/test/gates/test-releaseversion-tag-fetch.sh`, retired in W7 P5.

Both-ways test for the tag-fetch block of the Initialize step, `rediacc_ci.ci.initialize.fetch_latest_tag`.

WHAT IT IS FOR. Tag-based versioning means the version IS the tag list. CI checks out shallow, so initialize.sh fetches tags with the app token right before it computes next_version.

WHAT WAS BROKEN. The fetch ended in `2>/dev/null || true`. A failed or rate-limited fetch left whatever tags the checkout happened to bring, resolve-version.sh cannot tell a stale tag list from a current one, and next_version came out three lines later looking perfectly plausible and being wrong. That is the WRONG-VALUE case, and it is the one assert-artifact-version.sh
structurally cannot catch: CD's label and CI's label both descend from this one command, so they agree with each other and disagree with reality.

The block is DRIVEN AS A FUNCTION in a throwaway git repo -- the step as a whole needs submodules, secrets and a GitHub token, none of which this behaviour depends on. It used to be extracted by its anchors from `.ci/scripts/ci/initialize.sh` and run under bash; that file was retired under PLAN-retire-bash-oracles B3 (its answers, the fetch ladder included, are frozen in
`goldens/twins/ci.initialize.jsonl` and pinned by `test_ci_initialize.py`), and the port's `fetch_latest_tag` is the block now. If it is renamed or loses its fetch, `test_block_is_extractable` fails rather than the gate silently testing nothing.

THE ONE REAL DIFFERENCE, AND IT IS A DEFECT THE PORT DOES NOT INHERIT. The twin's cases share one `$WORK` directory and depend on each other through it: `test_failed_fetch_redacts_the_token` asserts on `$WORK/run.log` WITHOUT RUNNING ANYTHING -- it reads the log the previous case happened to leave -- and `test_planted_swallowed_fetch_continues` reuses the `bin-badgit` shim built
inside `test_failed_fetch_stops_the_run`. Run either one alone and it passes over an absent file or fails on a missing shim; reorder the two and the redaction case asserts against the wrong run. Each case here builds what it needs and drives its own run, which is why the redaction case is slower and why it is now actually testing the thing its name claims.
"""

import inspect
import os
import shutil
import stat
import sys

from rediacc_ci import paths
from rediacc_ci.ci import initialize
from rediacc_ci.tests.gates import harness
from rediacc_ci.well_known import GH_REPO

GATE = paths.from_root(".ci", "rediacc_ci", "ci", "initialize.py")

# The one line the planted control disarms: the refusal that acts on a failed fetch.
REFUSAL_GUARD = "    if not fetch_ok:\n"

# NAMED `FAKE_APP_CREDENTIAL` AND NOT `TOKEN` ON PURPOSE. ruff's S105 flags any hardcoded string assigned to a name containing "token"/"secret"/"password", and it is right to: that heuristic is how a real credential gets caught. This one is a FIXTURE value the test plants so it can prove the subject REDACTS it, so the honest fix is a name that does not claim to be a credential, not
# a per-line suppression of the rule that would catch a real one in the file next door.
FAKE_APP_CREDENTIAL = "s3cr3t-app-token"
CREDENTIALED_URL = (
    "https://x-access-token:%s@github.com/" + GH_REPO + ".git"
) % FAKE_APP_CREDENTIAL


def _git() -> str:
    return harness.require_tool("git", "install git; every fixture here is a real repository")


def extract_block(gate) -> str:
    """The block under test: `fetch_latest_tag`'s source.

    An EMPTY or fetch-less block is a REFUSAL and not an empty runner: a runner built from nothing exits 0 having done nothing, which would make four cases below pass for the wrong reason.
    """
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    fn = getattr(initialize, "fetch_latest_tag", None)
    if not callable(fn):
        gate.log_fail(
            "rediacc_ci.ci.initialize has no fetch_latest_tag, so every case below would be "
            "driving NOTHING. It was renamed or folded back into `run`."
        )
    assert callable(fn)  # log_fail raised above otherwise
    return inspect.getsource(fn)


RUNNER = """#!/usr/bin/env python3
import importlib.util, os, sys
sys.path.insert(0, %(ci)r)
spec = importlib.util.spec_from_file_location("initialize_under_test", %(module)r)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
# The retry backoff would otherwise cost 15 seconds per failing case.
m.FETCH_BACKOFF_SECONDS = 0
rc, latest = m.fetch_latest_tag(os.environ["FETCH_URL"], os.environ.get("GITHUB_PAT", ""))
if rc:
    sys.exit(rc)
print("REACHED_END latest=%%s" %% latest)
"""


def make_runner(gate, path, mutation=None) -> None:
    """A standalone program driving the real block (or, for the control, a planted copy of the module) with no backoff."""
    extract_block(gate)
    module = GATE
    if mutation is not None:
        source = GATE.read_text(encoding="utf-8")
        mutated = mutation(source)
        if mutated == source:
            gate.log_fail(
                "the planted mutation changed NOTHING in the module, so the control below "
                "would be running the fixed code and calling it the old behaviour. "
                "Re-point the mutation; do not delete the case."
            )
        module = path.with_suffix(".mutant.py")
        module.write_text(mutated, encoding="utf-8")
    path.write_text(
        RUNNER % {"ci": str(paths.from_root(".ci")), "module": str(module)}, encoding="utf-8"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_block(runner, workdir, url: str, extra_path=None) -> harness.RunResult:
    env = {"FETCH_URL": url, "GITHUB_PAT": FAKE_APP_CREDENTIAL}
    if extra_path is not None:
        env["PATH"] = "%s%s%s" % (extra_path, os.pathsep, os.environ.get("PATH", ""))
    return harness.run([sys.executable, str(runner)], cwd=workdir, env=env, timeout=120)


def seed_source_repo(gate, directory, tag: str = "") -> None:
    git = _git()
    directory.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        [
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "seed",
        ],
    ):
        result = harness.run([git, "-C", str(directory), *args])
        if result.rc != 0:
            gate.log_fail("git %s failed" % " ".join(args), result)
    if tag:
        result = harness.run([git, "-C", str(directory), "tag", tag])
        if result.rc != 0:
            gate.log_fail("could not tag the fixture", result)


def init_workdir(gate, directory):
    directory.mkdir(parents=True, exist_ok=True)
    result = harness.run([_git(), "-C", str(directory), "init", "-q"])
    if result.rc != 0:
        gate.log_fail("could not init the working fixture", result)
    return directory


def bad_git_shim(directory):
    """A `git` that fails every fetch and LEAKS the credentialed URL on stderr.

    Every other subcommand goes to the REAL git by ABSOLUTE PATH. Resolving it through PATH would find this shim again and recurse forever.
    """
    real_git = shutil.which("git")
    if not real_git:
        harness.require_tool("git", "install git; the shim delegates to the real binary")
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "git"
    shim.write_text(
        "#!/bin/bash\n"
        'if [[ "${1:-}" == "fetch" ]]; then\n'
        "    echo \"fatal: unable to access '%s/'\" >&2\n"
        "    exit 128\n"
        "fi\n"
        'exec "%s" "$@"\n' % (CREDENTIALED_URL, real_git),
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return directory


def failing_fetch_run(gate, tmp_path) -> harness.RunResult:
    """The shared body of the two failure cases: a real block, a broken fetch."""
    shim = bad_git_shim(tmp_path / "bin-badgit")
    work = init_workdir(gate, tmp_path / "work-bad")
    runner = tmp_path / "runner.py"
    make_runner(gate, runner)
    return run_block(runner, work, CREDENTIALED_URL, shim)


def test_block_is_extractable(gate):
    gate.log_test("the tag-fetch block is still where the anchors say")
    block = extract_block(gate)
    gate.assert_contains(block, '"fetch", "--tags", "--force"', "the block must carry the fetch")
    gate.assert_contains(block, REFUSAL_GUARD, "the block must carry the success accounting")
    gate.assert_contains(block, "latest_tag", "the block must reach the tag read")
    gate.log_pass("block found in the port (%d line(s))" % len(block.splitlines()))


def test_successful_fetch_yields_the_tag(gate, tmp_path):
    gate.log_test("a working fetch produces the latest tag")
    seed_source_repo(gate, tmp_path / "src-tagged", "v1.2.17")
    work = init_workdir(gate, tmp_path / "work-ok")
    runner = tmp_path / "runner.py"
    make_runner(gate, runner)
    result = run_block(runner, work, str(tmp_path / "src-tagged"))
    gate.assert_eq(result.rc, 0, "a healthy fetch must succeed")
    gate.assert_contains(
        result.combined, "REACHED_END latest=v1.2.17", "the fetched tag must be the one used"
    )
    gate.log_pass("fetch succeeds and v1.2.17 is read")


def test_failed_fetch_stops_the_run(gate, tmp_path):
    """THE DEFECT: the fetch fails. Before the fix this was swallowed and the script went on to compute a version from a tag list it could not refresh."""
    gate.log_test("a failing fetch stops the run instead of guessing")
    result = failing_fetch_run(gate, tmp_path)
    gate.assert_eq(result.rc, 1, "a failing fetch must not produce a version")
    gate.assert_contains(
        result.combined, "Could not fetch tags after 3 attempts", "the failure must be explicit"
    )
    gate.assert_not_contains(
        result.combined, "REACHED_END", "the run must not continue past the failed fetch"
    )
    gate.log_pass("a failing fetch fails the run")


def test_failed_fetch_redacts_the_token(gate, tmp_path):
    """The twin reads the PREVIOUS case's log here. This one drives its own run, so the assertion is about a fetch that happened rather than about a file."""
    gate.log_test("the failure output does not leak the app token")
    result = failing_fetch_run(gate, tmp_path)
    gate.assert_contains(result.combined, "***", "git's stderr must be redacted, not suppressed")
    gate.assert_not_contains(
        result.combined, FAKE_APP_CREDENTIAL, "the app token must never reach the log"
    )
    gate.log_pass("token redacted, diagnostics preserved")


def test_no_tags_after_a_good_fetch_stops_the_run(gate, tmp_path):
    gate.log_test("a successful fetch that yields no tags stops the run")
    seed_source_repo(gate, tmp_path / "src-untagged")
    work = init_workdir(gate, tmp_path / "work-untagged")
    runner = tmp_path / "runner.py"
    make_runner(gate, runner)
    result = run_block(runner, work, str(tmp_path / "src-untagged"))
    gate.assert_eq(result.rc, 1, "no tags means no version, so the run must stop")
    gate.assert_contains(result.combined, "no v* tag exists", "the failure must say why")
    gate.log_pass("an untagged repository fails instead of inventing a version")


def test_planted_swallowed_fetch_continues(gate, tmp_path):
    """THE CONTROL. Plant the pre-fix behaviour -- fetch failure swallowed, tag list used regardless -- and prove the same failing fetch sails through. Without this, `test_failed_fetch_stops_the_run` might be red for some unrelated reason."""
    gate.log_test("control: with the failure swallowed, the run continues on a stale tag list")
    seed_source_repo(gate, tmp_path / "src-stale", "v0.0.9")
    work = init_workdir(gate, tmp_path / "work-stale")
    git = _git()
    # Give the working tree an old tag, then break the fetch: exactly the shape that shipped a wrong version.
    harness.run(
        [
            git,
            "-C",
            str(work),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "old",
        ]
    )
    harness.run([git, "-C", str(work), "tag", "v0.0.9"])
    shim = bad_git_shim(tmp_path / "bin-badgit")
    runner = tmp_path / "runner-old.py"
    make_runner(gate, runner, lambda source: source.replace(REFUSAL_GUARD, "    if False:\n", 1))
    result = run_block(runner, work, str(tmp_path / "does-not-exist.git"), shim)
    gate.assert_eq(
        result.rc, 0, "planted swallowed fetch must continue (else the control proves nothing)"
    )
    gate.assert_contains(
        result.combined,
        "REACHED_END latest=v0.0.9",
        "planted version comes from the stale local tag",
    )
    gate.log_pass("the run goes red only because the fetch failure is acted on")
