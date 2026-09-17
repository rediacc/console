"""Port of `.ci/scripts/test/gates/test-releaseversion-tag-fetch.sh`.

Both-ways test for the tag-fetch block in `.ci/scripts/ci/initialize.sh`.

WHAT IT IS FOR. Tag-based versioning means the version IS the tag list. CI checks out shallow, so initialize.sh fetches tags with the app token right before it computes next_version.

WHAT WAS BROKEN. The fetch ended in `2>/dev/null || true`. A failed or rate-limited fetch left whatever tags the checkout happened to bring, resolve-version.sh cannot tell a stale tag list from a current one, and next_version came out three lines later looking perfectly plausible and being wrong. That is the WRONG-VALUE case, and it is the one assert-artifact-version.sh
structurally cannot catch: CD's label and CI's label both descend from this one command, so they agree with each other and disagree with reality.

The block is EXTRACTED FROM THE REAL SCRIPT by its own anchors and run in a throwaway git repo -- initialize.sh as a whole needs submodules, secrets and a GitHub token, none of which this behaviour depends on. If the block is rewritten the anchors stop matching and `test_block_is_extractable` fails, rather than the gate silently testing nothing.

THE ONE REAL DIFFERENCE, AND IT IS A DEFECT THE PORT DOES NOT INHERIT. The twin's cases share one `$WORK` directory and depend on each other through it: `test_failed_fetch_redacts_the_token` asserts on `$WORK/run.log` WITHOUT RUNNING ANYTHING -- it reads the log the previous case happened to leave -- and `test_planted_swallowed_fetch_continues` reuses the `bin-badgit` shim built
inside `test_failed_fetch_stops_the_run`. Run either one alone and it passes over an absent file or fails on a missing shim; reorder the two and the redaction case asserts against the wrong run. Each case here builds what it needs and drives its own run, which is why the redaction case is slower and why it is now actually testing the thing its name claims.
"""

import os
import re
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-releaseversion-tag-fetch.sh"

GATE = paths.from_root(".ci", "scripts", "ci", "initialize.sh")

BLOCK_START = 'TAG_FETCH_ERR="$(mktemp)"'
BLOCK_END = 'log_info "Latest tag: $LATEST_TAG"'

# NAMED `FAKE_APP_CREDENTIAL` AND NOT `TOKEN` ON PURPOSE. ruff's S105 flags any hardcoded string assigned to a name containing "token"/"secret"/"password", and it is right to: that heuristic is how a real credential gets caught. This one is a FIXTURE value the test plants so it can prove the subject REDACTS it, so the honest fix is a name that does not claim to be a credential, not
# a per-line suppression of the rule that would catch a real one in the file next door.
FAKE_APP_CREDENTIAL = "s3cr3t-app-token"
CREDENTIALED_URL = "https://x-access-token:%s@github.com/rediacc/console.git" % FAKE_APP_CREDENTIAL


def _git() -> str:
    return harness.require_tool("git", "install git; every fixture here is a real repository")


def extract_block(gate) -> str:
    """The twin's `extract_block`, awk range spelled as a scan.

    An EMPTY extraction is a REFUSAL and not an empty runner: a runner built from nothing exits 0 having done nothing, which would make four cases below pass
    for the wrong reason.
    """
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    lines = GATE.read_text(encoding="utf-8").splitlines(keepends=True)
    kept: list[str] = []
    started = False
    for line in lines:
        if not started and BLOCK_START in line:
            started = True
        if started:
            kept.append(line)
            if BLOCK_END in line:
                break
    if not kept:
        gate.log_fail(
            "the tag-fetch block could not be extracted from %s: no line contains %r. "
            "The anchors moved, so every case below would be driving an EMPTY script."
            % (paths.relative_to_root(GATE), BLOCK_START)
        )
    return "".join(kept)


def make_runner(gate, path, mutation=None) -> None:
    """A standalone script wrapping the real block with logging stubs and a no-op sleep (the retry backoff would otherwise cost 15 seconds per failing case)."""
    block = extract_block(gate)
    if mutation is not None:
        mutated = mutation(block)
        if mutated == block:
            gate.log_fail(
                "the planted mutation changed NOTHING in the extracted block, so the "
                "control below would be running the fixed code and calling it the old "
                "behaviour. Re-point the mutation; do not delete the case."
            )
        block = mutated
    path.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'log_info() { echo "INFO: $*"; }\n'
        'log_warn() { echo "WARN: $*"; }\n'
        'log_error() { echo "ERROR: $*" >&2; }\n'
        "sleep() { :; }\n" + block + 'echo "REACHED_END latest=$LATEST_TAG"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_block(runner, workdir, url: str, extra_path=None) -> harness.RunResult:
    env = {"FETCH_URL": url, "GITHUB_PAT": FAKE_APP_CREDENTIAL}
    if extra_path is not None:
        env["PATH"] = "%s%s%s" % (extra_path, os.pathsep, os.environ.get("PATH", ""))
    return harness.run([str(runner)], cwd=workdir, env=env, timeout=120)


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
            gate.log_fail("git %s failed: %s" % (" ".join(args), result.combined))
    if tag:
        result = harness.run([git, "-C", str(directory), "tag", tag])
        if result.rc != 0:
            gate.log_fail("could not tag the fixture: %s" % result.combined)


def init_workdir(gate, directory):
    directory.mkdir(parents=True, exist_ok=True)
    result = harness.run([_git(), "-C", str(directory), "init", "-q"])
    if result.rc != 0:
        gate.log_fail("could not init the working fixture: %s" % result.combined)
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
    runner = tmp_path / "runner.sh"
    make_runner(gate, runner)
    return run_block(runner, work, CREDENTIALED_URL, shim)


def test_block_is_extractable(gate):
    gate.log_test("the tag-fetch block is still where the anchors say")
    block = extract_block(gate)
    gate.assert_contains(block, "git fetch --tags --force", "extraction must capture the fetch")
    gate.assert_contains(block, "TAG_FETCH_OK", "extraction must capture the success accounting")
    gate.assert_contains(block, "LATEST_TAG", "extraction must reach the tag read")
    gate.log_pass("block extracted from the real script (%d line(s))" % len(block.splitlines()))


def test_successful_fetch_yields_the_tag(gate, tmp_path):
    gate.log_test("a working fetch produces the latest tag")
    seed_source_repo(gate, tmp_path / "src-tagged", "v1.2.17")
    work = init_workdir(gate, tmp_path / "work-ok")
    runner = tmp_path / "runner.sh"
    make_runner(gate, runner)
    result = run_block(runner, work, str(tmp_path / "src-tagged"))
    gate.assert_eq(result.rc, 0, "a healthy fetch must succeed")
    gate.assert_contains(
        result.combined, "REACHED_END latest=v1.2.17", "the fetched tag must be the one used"
    )
    gate.log_pass("fetch succeeds and v1.2.17 is read")


def test_failed_fetch_stops_the_run(gate, tmp_path):
    """THE DEFECT: the fetch fails. Before the fix this was swallowed and the script went on to compute a version from a tag list it could not refresh.
    """
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
    runner = tmp_path / "runner.sh"
    make_runner(gate, runner)
    result = run_block(runner, work, str(tmp_path / "src-untagged"))
    gate.assert_eq(result.rc, 1, "no tags means no version, so the run must stop")
    gate.assert_contains(result.combined, "no v* tag exists", "the failure must say why")
    gate.log_pass("an untagged repository fails instead of inventing a version")


def test_planted_swallowed_fetch_continues(gate, tmp_path):
    """THE CONTROL. Plant the pre-fix behaviour -- fetch failure swallowed, tag list used regardless -- and prove the same failing fetch sails through. Without this, `test_failed_fetch_stops_the_run` might be red for some unrelated reason.
    """
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
    runner = tmp_path / "runner-old.sh"
    make_runner(
        gate,
        runner,
        lambda block: re.sub(
            r'if \[\[ "\$TAG_FETCH_OK" != "true" \]\]; then', "if false; then", block
        ),
    )
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
