"""Differential: `rediacc_ci.docker.cleanup_staging` against its twin
`.ci/scripts/docker/cleanup-staging.sh`.

RECORDING FAKES FOR `gh` ON A SCRATCH PATH, AND NOTHING ELSE REAL. No case here names a credential, and the scratch PATH is built from an explicit list of symlinks, so a tool that is not listed is genuinely absent rather than inherited
from the developer's shell. That precaution is not theoretical: an early probe
for this port left `/usr/bin` on PATH, and the real `docker` binary on this
machine reached out to `ghcr.io/token` before the twin's first log line. Nothing in this file can do that.

`jq` IS REAL, NOT FAKED, and deliberately. The port shells out to the same jq the twin does (see the module docstring for why), so faking it would replace the thing under comparison with a stub on BOTH sides and prove nothing about the filters. It is a pure data tool with no remote side.

THE CALL LOG IS THE PRIMARY EVIDENCE. What this script does that matters is DELETE a GHCR package version, and the fake's stdout is fixed rather than derived from the argv it was handed, so a port that deleted the wrong version id or the wrong package would print identical bytes and exit 0. `test_planted_defect_is_caught_only_by_the_call_log` plants exactly that.

THREE OF THE TWIN'S DEFECTS ARE PINNED HERE RATHER THAN FIXED, because fixing a twin is a cutover-box decision: a missing `gh` reports success, two versions sharing one tag build one malformed URL, and a quote in the tag is swallowed. Each has its own `test_defect_*`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.docker import cleanup_staging as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "docker" / "cleanup-staging.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "docker" / "cleanup_staging.py"
BASH = shutil.which("bash") or "/bin/bash"

# THE FAKE'S STDOUT IS CONSTANT ON THE DELETE PATH. See the module docstring: that is what makes the recorded argv the only witness to WHICH version id was deleted. The list path answers from `FAKE_GH_MODE` so every branch of the twin's response handling can be driven.
FAKE_GH = r"""#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("gh\t" + "\t".join(argv) + "\n")

mode = os.environ.get("FAKE_GH_MODE", "ok")
is_delete = "-X" in argv and "DELETE" in argv

if is_delete:
    if mode == "delfail":
        sys.stderr.write("gh: HTTP 403: packages:write required\n")
        sys.exit(1)
    sys.stdout.write("DELETE-ACCEPTED\n")
    sys.exit(0)

TAGGED = '[{"id":111,"metadata":{"container":{"tags":["staging-abc","spare"]}}},' \
         '{"id":222,"metadata":{"container":{"tags":["other"]}}}]'
if mode in ("ok", "delfail"):
    sys.stdout.write(TAGGED + "\n")
elif mode == "notag":
    sys.stdout.write('[{"id":222,"metadata":{"container":{"tags":["other"]}}}]\n')
elif mode == "nulltags":
    sys.stdout.write('[{"id":111,"metadata":{"container":{"tags":null}}},{"id":222}]\n')
elif mode == "dup":
    sys.stdout.write(
        '[{"id":111,"metadata":{"container":{"tags":["staging-abc"]}}},'
        '{"id":222,"metadata":{"container":{"tags":["staging-abc"]}}}]\n'
    )
elif mode == "warnfirst":
    # STDERR FIRST, THEN JSON. The twin captures `2>&1`, so this is the case
    # that distinguishes a real merge from concatenating two buffers.
    sys.stderr.write("gh: warning: API rate limit is low\n")
    sys.stderr.flush()
    sys.stdout.write(TAGGED + "\n")
elif mode == "notfound":
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
sys.exit(0)
"""

# What the twin needs on PATH: `dirname` for SCRIPT_DIR in both the script and constants.sh, `uname`/`tr` for common.sh's detection helpers, `jq` for the two filters, and `python3` because the fakes are Python. Anything not listed is ABSENT, which is the point.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "python3")


def _bin(root: pathlib.Path, *, drop: str = "", gh_body: str = FAKE_GH) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, "%s is missing from this machine" % real_name
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    gh = stub / "gh"
    if drop == "gh":
        if gh.exists():
            gh.unlink()
        assert shutil.which("gh", path=str(stub)) is None, "gh leaked into the stub PATH"
    else:
        gh.write_text(gh_body, encoding="utf-8")
        gh.chmod(0o755)
    return str(stub)


def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway tree holding both implementations and the twin's libraries.

    BOTH SIDES ARE COPIED IN rather than run from this checkout, because the twin resolves common.sh and constants.sh from its OWN location and constants.sh then resolves `.devcontainer/toolchain.env` from ITS own location. Running the real files would drive them against the real tree.
    """
    root = tmp_path / "repo"
    for rel in (
        ".ci/scripts/docker",
        ".ci/scripts/lib",
        ".ci/config",
        ".devcontainer",
        ".ci/rediacc_ci/docker",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "docker" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / CONSTANTS.name)
    shutil.copy2(TOOLCHAIN, root / ".devcontainer" / TOOLCHAIN.name)
    shutil.copy2(PORT_FILE, root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    args: list[str],
    *,
    drop: str = "",
    gh_body: str = FAKE_GH,
    **extra: str,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root, drop=drop, gh_body=gh_body),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "docker" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)]
    proc = subprocess.run(
        [*argv, *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, args: list[str] | None = None, **kw):
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old", args or [], **kw)
    new, new_calls = _run(root, "new", args or [], **kw)
    return old, new, old_calls, new_calls


def _mask(text: str) -> str:
    """The ONE thing that cannot agree: `$0` in the usage line and in bash's
    `set -u` message. Masked by the two exact paths, so any OTHER absolute path leaking into the output is still compared.
    """
    masked = text.replace(".ci/scripts/docker/" + TWIN.name, "<SELF>")
    return masked.replace(".ci/rediacc_ci/docker/" + PORT_FILE.name, "<SELF>")


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """THE THREE STREAMS SEPARATELY, plus the call log.

    `2>&1` is the reflex and it destroys the defect class these tests exist for: a message moving between stdout and stderr is invisible once merged.
    """
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout) == _mask(old.stdout), "%s: stdout diverged:\n%r\n%r" % (
        label,
        old.stdout,
        new.stdout,
    )
    assert _mask(new.stderr) == _mask(old.stderr), "%s: stderr diverged:\n%r\n%r" % (
        label,
        old.stderr,
        new.stderr,
    )
    assert new_calls == old_calls, "%s: call log diverged:\n%s\n---\n%s" % (
        label,
        old_calls,
        new_calls,
    )


# --------------------------------------------------------------------------- Argument handling: every arm of the twin's `while` loop ---------------------------------------------------------------------------


def test_help_prints_the_usage_and_names_the_images(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--help"])
    _agree(old, new, "help", old_calls, new_calls)
    assert old.returncode == 0
    assert old.stderr == ""
    assert "Images to clean: renet rdc" in old.stdout
    assert old_calls == "", "help must not call gh"


def test_short_help_is_the_same_as_long_help(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["-h"])
    _agree(old, new, "-h", old_calls, new_calls)
    assert old.returncode == 0


def test_no_tag_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    _agree(old, new, "no-tag", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --tag is required\n", repr(old.stderr)
    assert old.stdout == ""


def test_a_tag_without_the_staging_prefix_refuses_before_any_call(tmp_path) -> None:
    """THE SAFETY RAIL. `edge` is the value production actually passes through
    `cleanup-channel-docker-tags.sh`, so this branch is the common one.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "edge"])
    _agree(old, new, "bad-prefix", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ Tag must start with 'staging-' prefix for safety\n"
    assert old_calls == "", "a refused tag still reached gh"


def test_a_tag_that_merely_contains_staging_is_refused(tmp_path) -> None:
    """The NEGATIVE half of the anchor: the match is `^staging-`, not a substring."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "v1-staging-abc"])
    _agree(old, new, "not-anchored", old_calls, new_calls)
    assert old.returncode == 1
    assert old_calls == ""


def test_an_unknown_option_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--bogus"])
    _agree(old, new, "bogus", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ Unknown option: --bogus\n"


def test_a_bare_tag_flag_dies_the_way_set_u_dies(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag"])
    _agree(old, new, "unbound", old_calls, new_calls)
    assert old.returncode == 1
    # `$0` is the invoked path, which differs per side and per tmp dir; `_mask`
    # collapses exactly those two spellings and nothing else.
    assert _mask(old.stderr).endswith("<SELF>: line 26: $2: unbound variable\n"), repr(old.stderr)
    assert old.stdout == ""


def test_the_last_tag_wins(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-first", "--tag", "staging-second", "--dry-run"]
    )
    _agree(old, new, "last-wins", old_calls, new_calls)
    assert "staging-second" in old.stderr
    assert "staging-first" not in old.stderr


# --------------------------------------------------------------------------- The four outcomes of a real run ---------------------------------------------------------------------------


def test_dry_run_names_both_images_and_calls_nothing(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "staging-abc", "--dry-run"])
    _agree(old, new, "dry-run", old_calls, new_calls)
    assert old.returncode == 0
    assert old_calls == "", "a dry run reached gh"
    assert old.stderr.splitlines() == [
        "→ Cleaning up staging tags: staging-abc",
        "→ Deleting staging tag for renet: staging-abc",
        "✓ [DRY-RUN] Would delete: ghcr.io/rediacc/renet:staging-abc",
        "→ Deleting staging tag for rdc: staging-abc",
        "✓ [DRY-RUN] Would delete: ghcr.io/rediacc/rdc:staging-abc",
        "✓ Cleanup summary: 2 succeeded",
    ], old.stderr
    # THE SEPARATORS ARE STDOUT, the log lines are stderr. Merging the two would hide a stream swap, which is the class these files exist for.
    assert old.stdout == "\n\n", repr(old.stdout)


def test_the_happy_path_deletes_one_version_per_image(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "staging-abc"])
    _agree(old, new, "happy", old_calls, new_calls)
    assert old.returncode == 0
    # THE SHAPE, not just the verdict: list then delete, per image, id 111 both times, and the package name is the BARE image name under the org.
    assert old_calls.splitlines() == [
        "gh\tapi\t/orgs/rediacc/packages/container/renet/versions\t--paginate",
        "gh\tapi\t-X\tDELETE\t/orgs/rediacc/packages/container/renet/versions/111",
        "gh\tapi\t/orgs/rediacc/packages/container/rdc/versions\t--paginate",
        "gh\tapi\t-X\tDELETE\t/orgs/rediacc/packages/container/rdc/versions/111",
    ], old_calls
    assert "✓ Cleanup summary: 2 succeeded" in old.stderr


def test_an_unparseable_response_is_reported_as_a_missing_package(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="notfound"
    )
    _agree(old, new, "404", old_calls, new_calls)
    assert old.returncode == 0
    assert len(old_calls.splitlines()) == 2, "a 404 still tried the delete"
    assert "⚠ Package renet not found or not accessible" in old.stderr


def test_a_tag_no_version_carries_is_reported_as_already_deleted(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="notag"
    )
    _agree(old, new, "no-such-tag", old_calls, new_calls)
    assert old.returncode == 0
    assert "⚠ Staging tag not found for renet:staging-abc (may already be deleted)" in (old.stderr)


def test_a_null_tag_list_does_not_crash_the_filter(tmp_path) -> None:
    """jq's `index(...)` on `null` yields null, which `select` drops. A port that
    reimplemented the filter in Python with `.get("tags", [])` would agree here
    by luck and diverge on the `{"id":222}` entry with no metadata at all.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="nulltags"
    )
    _agree(old, new, "null-tags", old_calls, new_calls)
    assert old.returncode == 0
    assert len(old_calls.splitlines()) == 2


def test_a_failing_delete_makes_the_summary_red_and_the_exit_one(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="delfail"
    )
    _agree(old, new, "delete-fails", old_calls, new_calls)
    assert old.returncode == 1
    assert "✗ Cleanup summary: 0 succeeded, 2 failed" in old.stderr
    # AND THE REASON IS GONE. The twin's `2>/dev/null` on the delete swallows gh's "HTTP 403: packages:write required" entirely.
    assert "403" not in old.stderr, "the reason survived; this assertion is stale"


def test_stderr_arriving_before_the_json_is_merged_in_order(tmp_path) -> None:
    """`2>&1` INSIDE the substitution, not two buffers concatenated.

    The fake writes a warning to stderr and flushes before writing valid JSON to stdout. Under a true merge the warning lands FIRST and jq rejects the whole
    thing; under `stdout + stderr` the JSON would come first and jq would accept
    it. Both sides must reach the same verdict, and it is the reject.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="warnfirst"
    )
    _agree(old, new, "warn-first", old_calls, new_calls)
    assert old.returncode == 0
    assert "⚠ Package renet not found or not accessible" in old.stderr
    assert len(old_calls.splitlines()) == 2, old_calls


def test_the_delete_calls_own_stdout_is_inherited_and_interleaves(tmp_path) -> None:
    """`DELETE-ACCEPTED` reaches the caller's stdout between the two separators.

    Python block-buffers stdout against a pipe; without the port's `_flush` the
    two blank lines would arrive AFTER both children's output, byte-identical and in the wrong order. This is the only comparison that sees it.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "staging-abc"])
    _agree(old, new, "inherited-stdout", old_calls, new_calls)
    assert old.stdout == "\nDELETE-ACCEPTED\nDELETE-ACCEPTED\n\n", repr(old.stdout)


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_a_missing_gh_reports_two_successes_and_exits_zero(tmp_path) -> None:
    """UNKNOWN FOLDED INTO FINE. With no `gh` on PATH nothing is deleted, the
    staging tags survive, and the run prints `Cleanup summary: 2 succeeded` and exits 0. The `2>&1` capture turns `command not found` into an unparseable response, which the twin files under "package may not exist yet".
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "staging-abc"], drop="gh")
    _agree(old, new, "no-gh", old_calls, new_calls)
    assert old.returncode == 0, "the twin's behaviour changed; re-read this test"
    assert old_calls == ""
    assert "✓ Cleanup summary: 2 succeeded" in old.stderr


def test_defect_two_versions_sharing_a_tag_build_one_malformed_url(tmp_path) -> None:
    """jq returns TWO ids, command substitution keeps the newline, and the twin
    splices the whole `"111\\n222"` into a single URL. The port reproduces the malformed call rather than picking one id, because picking would change WHICH version gets deleted.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], FAKE_GH_MODE="dup"
    )
    _agree(old, new, "two-ids", old_calls, new_calls)
    assert "/versions/111\n222" in old_calls, old_calls
    assert old.returncode == 0, "the fake accepts it; a real gh would 404"


def test_defect_a_quote_in_the_tag_is_swallowed_as_already_deleted(tmp_path) -> None:
    """The tag is interpolated into the jq PROGRAM unquoted, so a `"` is a jq
    syntax error, jq's stderr is discarded and the empty result reads as "may already be deleted". Nothing warns that the filter never ran.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", 'staging-a"b'])
    _agree(old, new, "quote-in-tag", old_calls, new_calls)
    assert old.returncode == 0
    assert "may already be deleted" in old.stderr
    assert len(old_calls.splitlines()) == 2, old_calls


def test_defect_a_non_ghcr_registry_yields_the_host_as_the_org(tmp_path) -> None:
    """`${REG#ghcr.io/}` only strips the GHCR prefix, so `docker.io/rediacc`
    leaves `docker.io` and `%%/*` then returns `docker.io` as the ORG. The API path becomes `/orgs/docker.io/...`, which is nobody's org.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--tag", "staging-abc"], PUBLISH_DOCKER_REGISTRY="docker.io/rediacc"
    )
    _agree(old, new, "non-ghcr", old_calls, new_calls)
    assert "/orgs/docker.io/packages/container/renet/versions" in old_calls, old_calls


def test_a_version_carrying_a_second_tag_is_deleted_whole(tmp_path) -> None:
    """The fixture's id 111 carries `staging-abc` AND `spare`. GHCR has no
    delete-one-tag call, so `spare` disappears with it. Recorded, not repaired.
    """
    old, _new, old_calls, _n = run_both(tmp_path, ["--tag", "staging-abc"])
    assert "DELETE\t/orgs/rediacc/packages/container/renet/versions/111" in old_calls
    assert old.returncode == 0


# --------------------------------------------------------------------------- The planted defect: three streams agree, the call log does not ---------------------------------------------------------------------------


def test_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, AND PROVE WHICH ASSERTION FIRES.

    The plant deletes the version under the WRONG package (`renet` for both images). Every printed byte and the exit code are unchanged by it, so this also demonstrates that a streams-only comparison would have blessed it.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    plant = source.replace(
        '    return "%s/%s" % (versions_path(org, package), version_id)',
        '    return "%s/%s" % (versions_path(org, "renet"), version_id)',
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(plant, encoding="utf-8")

    old, old_calls = _run(root, "old", ["--tag", "staging-abc"])
    new, new_calls = _run(root, "new", ["--tag", "staging-abc"])

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert _mask(new.stdout) == _mask(old.stdout), "the plant changed stdout; wrong plant"
    assert _mask(new.stderr) == _mask(old.stderr), "the plant changed stderr; wrong plant"
    assert new_calls != old_calls, "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    assert "container/rdc/versions/111" not in new_calls


def _run_merged(root, side: str, args: list[str], **extra: str):
    """ONE PIPE FOR BOTH STREAMS, which is what a CI log actually is.

    The separate-stream comparison above cannot see a CROSS-stream ordering divergence, and there is a real one to see: Python block-buffers stdout against a pipe while bash's `echo` writes straight through, so without the
    port's `flush=True` its `echo ""` separators arrive several lines late with
    byte-identical content in each stream taken alone. Measured before the flush was added, not imagined.
    """
    call_log = root / ("%s-merged-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "docker" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)]
    return subprocess.run(
        [*argv, *args],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )


def test_the_merged_stream_keeps_the_twins_line_order(tmp_path) -> None:
    root = fixture(tmp_path)
    old = _run_merged(root, "old", ["--tag", "staging-abc"])
    new = _run_merged(root, "new", ["--tag", "staging-abc"])
    assert new.returncode == old.returncode
    assert _mask(new.stdout) == _mask(old.stdout), "merged order diverged:\nold:\n%s\nnew:\n%s" % (
        old.stdout,
        new.stdout,
    )
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would pass this
    # for free, so the case is one that writes to BOTH streams.
    assert old.stdout.count("\n") >= 8, old.stdout


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_org_of_strips_the_ghcr_prefix_and_keeps_the_first_segment() -> None:
    assert port.org_of("ghcr.io/rediacc") == "rediacc"
    assert port.org_of("ghcr.io/rediacc/sub/deep") == "rediacc"
    # The NEGATIVE half, which is the defect above stated as a unit fact.
    assert port.org_of("docker.io/rediacc") == "docker.io"


def test_is_staging_tag_is_anchored() -> None:
    assert port.is_staging_tag("staging-abc") is True
    assert port.is_staging_tag("staging-") is True
    assert port.is_staging_tag("edge") is False
    assert port.is_staging_tag("v1-staging-abc") is False
    assert port.is_staging_tag("Staging-abc") is False


def test_the_two_api_paths_are_built_the_twins_way() -> None:
    assert port.versions_path("rediacc", "renet") == (
        "/orgs/rediacc/packages/container/renet/versions"
    )
    assert port.version_delete_path("rediacc", "renet", "111") == (
        "/orgs/rediacc/packages/container/renet/versions/111"
    )


def test_tag_filter_interpolates_the_tag_unquoted() -> None:
    assert port.tag_filter("staging-abc") == (
        '.[] | select(.metadata.container.tags | index("staging-abc")) | .id'
    )


def test_dry_run_is_the_string_true_and_nothing_else(monkeypatch) -> None:
    """`[[ "$DRY_RUN" == "true" ]]`: `1` and `yes` are NOT dry runs, and a port
    using `bool(os.environ.get(...))` would turn `DRY_RUN=0` into a preview.
    """
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert port.dry_run_default() == "false"
    monkeypatch.setenv("DRY_RUN", "")
    assert port.dry_run_default() == "false"
    monkeypatch.setenv("DRY_RUN", "1")
    assert port.dry_run_default() == "1"
    monkeypatch.setenv("DRY_RUN", "true")
    assert port.dry_run_default() == "true"


def test_the_registry_default_is_taken_on_unset_and_on_empty(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_DOCKER_REGISTRY", raising=False)
    assert port.registry() == "ghcr.io/rediacc"
    monkeypatch.setenv("PUBLISH_DOCKER_REGISTRY", "")
    assert port.registry() == "ghcr.io/rediacc"
    monkeypatch.setenv("PUBLISH_DOCKER_REGISTRY", "ghcr.io/other")
    assert port.registry() == "ghcr.io/other"


# --------------------------------------------------------------------------- Staleness alarms: the restated constants and the quoted line number ---------------------------------------------------------------------------


def test_the_constants_are_still_constants_shs() -> None:
    """The port restates `PUBLISH_IMAGES` and the registry default rather than
    sourcing constants.sh (which hard-requires `.devcontainer/toolchain.env`). This is the alarm that makes the copy safe.
    """
    text = CONSTANTS.read_text(encoding="utf-8")
    images = re.search(r"^readonly PUBLISH_IMAGES=\((.*)\)$", text, re.MULTILINE)
    assert images is not None, "PUBLISH_IMAGES is no longer a one-line array in constants.sh"
    assert tuple(images.group(1).replace('"', "").split()) == port.PUBLISH_IMAGES

    registry = re.search(
        r'^PUBLISH_DOCKER_REGISTRY="\$\{PUBLISH_DOCKER_REGISTRY:-([^}]*)\}"$', text, re.MULTILINE
    )
    assert registry is not None, "the registry default moved in constants.sh"
    assert registry.group(1) == port.REGISTRY_DEFAULT


def test_the_unbound_line_number_still_names_the_assignment() -> None:
    """`UNBOUND_LINE_TAG` is quoted into a user-visible message, so a twin edit
    that moves the line must red here rather than drift silently.
    """
    lines = TWIN.read_text(encoding="utf-8").splitlines()
    assert lines[port.UNBOUND_LINE_TAG - 1].strip() == 'STAGING_TAG="$2"'
