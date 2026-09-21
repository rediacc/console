"""`rediacc_ci.docker.cleanup_staging`, driven against the bytes its bash twin produced.

THE TWIN IS STILL ON DISK, AND THAT IS THE ONE DIFFERENCE FROM ITS SIBLINGS. Every case below compares against `goldens/cleanup-staging/`, recorded from `.ci/scripts/docker/cleanup-staging.sh` exactly as if it had been deleted, so the deletion is a no-op for this file. It was not deleted because `check:ci-staging-tag-guard` is a live, currently-green gate whose default target IS
that path: it greps the twin for the `^staging-` rail and exits 1 with "not found -- nothing was verified" the moment the file goes. Repointing it at the port is not a one-line edit, and `.ci/scripts/docker/cleanup_staging.py`'s own header says so; the port's only `^staging-` is inside a docstring, so a repointed rail check would be verifying a comment.

The ledger `.ci/shadow/w7p6-cleanup-staging.observations.jsonl` recorded the differential over five distinct trees, every one of them EQUIVALENT; the row count is stated here from the file rather than carried forward.

RECORDING FAKES FOR `gh` ON A SCRATCH PATH, AND NOTHING ELSE REAL. No case names a credential, and the scratch PATH is built from an explicit list of symlinks, so a tool that is not listed is genuinely absent rather than inherited from the developer's shell. That precaution is not theoretical: an early probe for this port left `/usr/bin` on PATH, and the real `docker` binary on
this machine reached out to `ghcr.io/token` before the twin's first log line.

`jq` IS REAL, NOT FAKED, and deliberately. The port shells out to the same jq the twin did, so faking it would replace the thing under comparison with a stub and prove nothing about the filters. It is a pure data tool with no remote side. Its diagnostics never reach a recorded byte, so a jq version bump cannot move this corpus; the one case that makes jq fail discards its stderr,
which is itself one of the recorded defects.

THE CALL LOG IS THE PRIMARY EVIDENCE, so `--- calls ---` is part of the recorded shape. What this script does that matters is DELETE a GHCR package version, and the fake's stdout is fixed rather than derived from the argv it was handed, so a port that deleted the wrong version id or the wrong package would print identical bytes and exit 0. The control at the end of this file plants
exactly that.

ONE CASE IS RECORDED THROUGH A SINGLE PIPE, because the separate-stream comparison cannot see a CROSS-stream ordering divergence and there is a real one to see: Python block-buffers stdout against a pipe while bash's `echo` writes straight through, so without the port's `flush=True` its separators arrive several lines late with byte-identical content in each stream taken alone.

That case's recording carries the merged stream in the stdout section and nothing in stderr.

WHAT IS MASKED, and it is two spellings of one thing. `$0` reaches the usage line and bash's `set -u` message, and it is the subject's own path inside a scratch tree, so the tree becomes `<fx>` and the subject's relative path becomes `<SELF>`. Any OTHER absolute path leaking into a recorded byte is still compared.

THE TWO STALENESS ALARMS, SAID OUT LOUD RATHER THAN DROPPED. `test_the_constants_are_still_constants_shs` reads `.ci/config/constants.sh`, not the twin, so it survives a deletion untouched and still proves the port's restated `PUBLISH_IMAGES` and registry default match the file it copied them from.
The second alarm read the TWIN's line 26 and asserted it held `STAGING_TAG="$2"`, which a deletion would end; it is replaced by an assertion against the RECORDED BYTES, where bash itself names the line number in `<SELF>: line 26: $2: unbound variable`.

What is lost is the check that line 26 contains that exact assignment; what is gained is that the constant is now pinned to what the twin PRINTED rather than to what it read, which survives the file. The assignment text is recoverable from the blob sha every golden header carries.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.docker import cleanup_staging as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SLUG = "cleanup-staging"

TWIN_REL = ".ci/scripts/docker/cleanup-staging.sh"
PORT_REL = ".ci/rediacc_ci/docker/cleanup_staging.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
BASH = shutil.which("bash") or "/bin/bash"

CALLS_MARKER = "--- calls ---\n"
SELF = "<SELF>"
FX = "<fx>"

COPIED = (
    ".ci/scripts/lib/common.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    PORT_REL,
)

# What a BASH subject needed on top of that. Reached only by the one-shot recorder; the suite's subject is the port or a throwaway mutant of it.
TWIN_ONLY = (TWIN_REL,)

# THE FAKE'S STDOUT IS CONSTANT ON THE DELETE PATH. See the module docstring: that is what makes the recorded argv the only witness to WHICH version id was deleted. The list path answers from `FAKE_GH_MODE` so every branch of the response handling can be driven.
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
    # STDERR FIRST, THEN JSON. The twin captured `2>&1`, so this is the case
    # that distinguishes a real merge from concatenating two buffers.
    sys.stderr.write("gh: warning: API rate limit is low\n")
    sys.stderr.flush()
    sys.stdout.write(TAGGED + "\n")
elif mode == "notfound":
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
sys.exit(0)
"""

# What the subject needs on PATH: `dirname` for SCRIPT_DIR in both the script and constants.sh, `uname`/`tr` for common.sh's detection helpers, `jq` for the two filters, and `python3` because the fake is Python. Anything not listed is ABSENT, which is the point.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "python3")

TAG = ["--tag", "staging-abc"]

# name -> how the case is wired. `args` is the argv, `env` adds to the environment, `drop` removes one tool from the scratch PATH, and `merged` records both streams through ONE pipe.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "help": {"args": ["--help"]},
    "short-help": {"args": ["-h"]},
    "no-tag": {"args": []},
    "a-tag-without-the-staging-prefix": {"args": ["--tag", "edge"]},
    "a-tag-that-merely-contains-staging": {"args": ["--tag", "v1-staging-abc"]},
    "an-unknown-option": {"args": ["--bogus"]},
    "a-bare-tag-flag": {"args": ["--tag"]},
    "the-last-tag-wins": {
        "args": ["--tag", "staging-first", "--tag", "staging-second", "--dry-run"]
    },
    "a-dry-run": {"args": [*TAG, "--dry-run"]},
    "the-happy-path": {"args": TAG},
    "a-404-from-the-list-call": {"args": TAG, "env": {"FAKE_GH_MODE": "notfound"}},
    "a-tag-no-version-carries": {"args": TAG, "env": {"FAKE_GH_MODE": "notag"}},
    "a-null-tag-list": {"args": TAG, "env": {"FAKE_GH_MODE": "nulltags"}},
    "a-failing-delete": {"args": TAG, "env": {"FAKE_GH_MODE": "delfail"}},
    "stderr-arriving-before-the-json": {"args": TAG, "env": {"FAKE_GH_MODE": "warnfirst"}},
    "a-missing-gh": {"args": TAG, "drop": "gh"},
    "two-versions-sharing-a-tag": {"args": TAG, "env": {"FAKE_GH_MODE": "dup"}},
    "a-quote-in-the-tag": {"args": ["--tag", 'staging-a"b']},
    "a-non-ghcr-registry": {
        "args": TAG,
        "env": {"PUBLISH_DOCKER_REGISTRY": "docker.io/rediacc"},
    },
    "the-merged-stream": {"args": TAG, "merged": True},
}

CASES = tuple(CASE_KW)


def stub_bin(root: pathlib.Path, *, drop: str = "") -> str:
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
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(0o755)
    return str(stub)


def build(tmp_path: pathlib.Path, subject_rel: str = PORT_REL) -> pathlib.Path:
    """A throwaway tree holding the subject and the libraries it resolves from its own location.

    THE SUBJECT IS COPIED IN rather than run from this checkout, because the twin resolved common.sh and constants.sh from its OWN location and constants.sh then resolves `.devcontainer/toolchain.env` from ITS own location. Running the real files would drive them against the real tree.
    """
    root = tmp_path / "repo"
    for rel in COPIED + (TWIN_ONLY if subject_rel.endswith(".sh") else ()):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    return root


def mask(text: str, root: pathlib.Path) -> str:
    masked = text.replace(str(root) + "/", FX + "/").replace(str(root), FX)
    for rel in (TWIN_REL, PORT_REL):
        masked = masked.replace(FX + "/" + rel, SELF)
    return masked


def drive(
    root: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    """One subject, once, over an already-built tree."""
    kw = CASE_KW[name]
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_bin(root, drop=kw.get("drop", "")),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(kw.get("env") or {})
    runner = BASH if subject_rel.endswith(".sh") else sys.executable
    common = {
        "cwd": str(root),
        "text": True,
        "env": env,
        "timeout": 120,
        "input": "",
    }
    if kw.get("merged"):
        proc = subprocess.run(
            [runner, str(root / subject_rel), *kw["args"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            **common,
        )
        out, err = proc.stdout, ""
    else:
        proc = subprocess.run(
            [runner, str(root / subject_rel), *kw["args"]],
            capture_output=True,
            check=False,
            **common,
        )
        out, err = proc.stdout, proc.stderr
    calls = mask(call_log.read_text(encoding="utf-8"), root).splitlines()
    return proc.returncode, mask(out, root), mask(err, root), calls


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    return drive(build(tmp_path, subject_rel), name, subject_rel=subject_rel)


def render(code: int, stdout: str, stderr: str, calls: list[str]) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), CALLS_MARKER, "\n".join(calls))


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls.rstrip("\n").splitlines(),
    )


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the gh calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path_or_a_credential() -> None:
    """The scratch tree's path is masked and nothing here has ever held a token; a golden carrying either would be one that reds on another machine or leaks."""
    for name in CASES:
        _code, stdout, stderr, calls = recorded(name)
        blob = "\n".join([stdout, stderr, *calls])
        assert str(ROOT) not in blob, name
        assert "/tmp/" not in blob, name
        assert "ghp_" not in blob, name
        assert "GH_TOKEN" not in blob, name


# --------------------------------------------------------------------------- Argument handling: every arm of the twin's `while` loop ---------------------------------------------------------------------------


def test_help_prints_the_usage_and_names_the_images() -> None:
    code, stdout, stderr, calls = recorded("help")
    assert code == 0
    assert stderr == ""
    assert "Images to clean: renet rdc" in stdout
    assert calls == [], "help must not call gh"
    assert recorded("short-help") == recorded("help"), "-h and --help diverged"


def test_no_tag_refuses() -> None:
    code, stdout, stderr, _ = recorded("no-tag")
    assert code == 1
    assert stderr == "✗ --tag is required\n", repr(stderr)
    assert stdout == ""


def test_a_tag_without_the_staging_prefix_refuses_before_any_call() -> None:
    """THE SAFETY RAIL. `edge` is the value production actually passes through `cleanup-channel-docker-tags.sh`, so this branch is the common one."""
    code, _, stderr, calls = recorded("a-tag-without-the-staging-prefix")
    assert code == 1
    assert stderr == "✗ Tag must start with 'staging-' prefix for safety\n"
    assert calls == [], "a refused tag still reached gh"


def test_a_tag_that_merely_contains_staging_is_refused() -> None:
    """The NEGATIVE half of the anchor: the match is `^staging-`, not a substring."""
    code, _, _, calls = recorded("a-tag-that-merely-contains-staging")
    assert code == 1
    assert calls == []


def test_an_unknown_option_refuses() -> None:
    code, _, stderr, _ = recorded("an-unknown-option")
    assert code == 1
    assert stderr == "✗ Unknown option: --bogus\n"


def test_a_bare_tag_flag_dies_the_way_set_u_dies() -> None:
    code, stdout, stderr, _ = recorded("a-bare-tag-flag")
    assert code == 1
    assert stdout == ""
    assert stderr.endswith("%s: line 26: $2: unbound variable\n" % SELF), repr(stderr)


def test_the_unbound_line_number_still_names_the_assignment() -> None:
    """THE SECOND STALENESS ALARM, rewritten to survive the twin. See the module docstring.

    `UNBOUND_LINE_TAG` is quoted into a user-visible message, so a number that drifts must red here rather than travel into a diagnostic that names the wrong line. The recorded bytes are where bash itself said it, which is a claim that outlives the file the old alarm read.
    """
    stderr = recorded("a-bare-tag-flag")[2]
    match = re.search(r"%s: line (\d+): \$2: unbound variable" % re.escape(SELF), stderr)
    assert match is not None, repr(stderr)
    assert int(match.group(1)) == port.UNBOUND_LINE_TAG


def test_the_last_tag_wins() -> None:
    stderr = recorded("the-last-tag-wins")[2]
    assert "staging-second" in stderr
    assert "staging-first" not in stderr


# --------------------------------------------------------------------------- The outcomes of a real run ---------------------------------------------------------------------------


def test_dry_run_names_both_images_and_calls_nothing() -> None:
    code, stdout, stderr, calls = recorded("a-dry-run")
    assert code == 0
    assert calls == [], "a dry run reached gh"
    assert stderr.splitlines() == [
        "→ Cleaning up staging tags: staging-abc",
        "→ Deleting staging tag for renet: staging-abc",
        "✓ [DRY-RUN] Would delete: ghcr.io/rediacc/renet:staging-abc",
        "→ Deleting staging tag for rdc: staging-abc",
        "✓ [DRY-RUN] Would delete: ghcr.io/rediacc/rdc:staging-abc",
        "✓ Cleanup summary: 2 succeeded",
    ], stderr
    # THE SEPARATORS ARE STDOUT, the log lines are stderr. Merging the two would hide a stream swap, which is the class this file exists for.
    assert stdout == "\n\n", repr(stdout)


def test_the_happy_path_deletes_one_version_per_image() -> None:
    code, stdout, stderr, calls = recorded("the-happy-path")
    assert code == 0
    # THE SHAPE, not just the verdict: list then delete, per image, id 111 both times, and the package name is the BARE image name under the org.
    assert calls == [
        "gh\tapi\t/orgs/rediacc/packages/container/renet/versions\t--paginate",
        "gh\tapi\t-X\tDELETE\t/orgs/rediacc/packages/container/renet/versions/111",
        "gh\tapi\t/orgs/rediacc/packages/container/rdc/versions\t--paginate",
        "gh\tapi\t-X\tDELETE\t/orgs/rediacc/packages/container/rdc/versions/111",
    ], calls
    assert "✓ Cleanup summary: 2 succeeded" in stderr
    # `DELETE-ACCEPTED` reaches the caller's stdout BETWEEN the two separators. Python block-buffers stdout against a pipe; without the port's flush the separators would arrive after both children's output, byte-identical and in the wrong order.
    assert stdout == "\nDELETE-ACCEPTED\nDELETE-ACCEPTED\n\n", repr(stdout)


def test_a_version_carrying_a_second_tag_is_deleted_whole() -> None:
    """The fixture's id 111 carries `staging-abc` AND `spare`. GHCR has no delete-one-tag call, so `spare` disappears with it. Recorded, not repaired."""
    calls = recorded("the-happy-path")[3]
    assert "gh\tapi\t-X\tDELETE\t/orgs/rediacc/packages/container/renet/versions/111" in calls


def test_an_unparseable_response_is_reported_as_a_missing_package() -> None:
    code, _, stderr, calls = recorded("a-404-from-the-list-call")
    assert code == 0
    assert len(calls) == 2, "a 404 still tried the delete"
    assert "⚠ Package renet not found or not accessible" in stderr


def test_a_tag_no_version_carries_is_reported_as_already_deleted() -> None:
    code, _, stderr, _ = recorded("a-tag-no-version-carries")
    assert code == 0
    assert "⚠ Staging tag not found for renet:staging-abc (may already be deleted)" in stderr


def test_a_null_tag_list_does_not_crash_the_filter() -> None:
    """jq's `index(...)` on `null` yields null, which `select` drops. A port that reimplemented the filter in Python with `.get("tags", [])` would agree here by luck and diverge on the `{"id":222}` entry with no metadata at all."""
    code, _, _, calls = recorded("a-null-tag-list")
    assert code == 0
    assert len(calls) == 2


def test_a_failing_delete_makes_the_summary_red_and_the_exit_one() -> None:
    code, _, stderr, _ = recorded("a-failing-delete")
    assert code == 1
    assert "✗ Cleanup summary: 0 succeeded, 2 failed" in stderr
    # AND THE REASON IS GONE. The `2>/dev/null` on the delete swallows gh's "HTTP 403: packages:write required" entirely.
    assert "403" not in stderr, "the reason survived; this assertion is stale"


def test_stderr_arriving_before_the_json_is_merged_in_order() -> None:
    """`2>&1` INSIDE the substitution, not two buffers concatenated.

    The fake writes a warning to stderr and flushes before writing valid JSON to stdout. Under a true merge the warning lands FIRST and jq rejects the whole thing; under `stdout + stderr` the JSON would come first and jq would accept it. The recorded verdict is the reject.
    """
    code, _, stderr, calls = recorded("stderr-arriving-before-the-json")
    assert code == 0
    assert "⚠ Package renet not found or not accessible" in stderr
    assert len(calls) == 2, calls


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_a_missing_gh_reports_two_successes_and_exits_zero() -> None:
    """UNKNOWN FOLDED INTO FINE. With no `gh` on PATH nothing is deleted, the staging tags survive, and the run prints `Cleanup summary: 2 succeeded` and exits 0. The `2>&1` capture turns `command not found` into an unparseable response, which is filed under "package may not exist yet"."""
    code, _, stderr, calls = recorded("a-missing-gh")
    assert code == 0, "the behaviour changed; re-read this case"
    assert calls == []
    assert "✓ Cleanup summary: 2 succeeded" in stderr


def test_defect_two_versions_sharing_a_tag_build_one_malformed_url() -> None:
    """jq returns TWO ids, command substitution keeps the newline, and the whole `"111\\n222"` is spliced into a single URL. The port reproduces the malformed call rather than picking one id, because picking would change WHICH version gets deleted."""
    code, _, _, calls = recorded("two-versions-sharing-a-tag")
    assert any(line.endswith("/versions/111") for line in calls), calls
    assert "222" in "\n".join(calls), calls
    assert code == 0, "the fake accepts it; a real gh would 404"


def test_defect_a_quote_in_the_tag_is_swallowed_as_already_deleted() -> None:
    """The tag is interpolated into the jq PROGRAM unquoted, so a `"` is a jq syntax error, jq's stderr is discarded and the empty result reads as "may already be deleted". Nothing warns that the filter never ran."""
    code, _, stderr, calls = recorded("a-quote-in-the-tag")
    assert code == 0
    assert "may already be deleted" in stderr
    assert len(calls) == 2, calls


def test_defect_a_non_ghcr_registry_yields_the_host_as_the_org() -> None:
    """`${REG#ghcr.io/}` only strips the GHCR prefix, so `docker.io/rediacc` leaves `docker.io` and `%%/*` then returns `docker.io` as the ORG. The API path becomes `/orgs/docker.io/...`, which is nobody's org."""
    calls = recorded("a-non-ghcr-registry")[3]
    assert "gh\tapi\t/orgs/docker.io/packages/container/renet/versions\t--paginate" in calls, calls


def test_the_merged_stream_keeps_the_twins_line_order() -> None:
    """ONE PIPE FOR BOTH STREAMS, which is what a CI log actually is."""
    code, stdout, stderr, _ = recorded("the-merged-stream")
    assert code == 0
    assert stderr == "", "the merged recording puts everything in the stdout section"
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would satisfy this for free, so the case is one that writes to BOTH streams.
    assert stdout.count("\n") >= 8, stdout
    assert "DELETE-ACCEPTED" in stdout


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
    """`[[ "$DRY_RUN" == "true" ]]`: `1` and `yes` are NOT dry runs, and a port using `bool(os.environ.get(...))` would turn `DRY_RUN=0` into a preview."""
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


def test_the_constants_are_still_constants_shs() -> None:
    """THE FIRST STALENESS ALARM, UNCHANGED, and it reads `constants.sh` rather than the twin, so a deletion does not touch it.

    The port restates `PUBLISH_IMAGES` and the registry default rather than sourcing constants.sh (which hard-requires `.devcontainer/toolchain.env`). This is the alarm that makes the copy safe.
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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_wrong_package_is_caught_only_by_the_call_log(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Delete the version under the WRONG package.

    The plant sends both images' deletes to `renet`, so `rdc:staging-abc` survives and a version of `renet` that nobody asked about is destroyed. Every printed byte and the exit code are unchanged by it, because the fake's stdout is fixed rather than derived from the argv, so this also demonstrates that a streams-only recording would have blessed it. `--- calls ---` is the only
    section that sees it, and an irreversible `gh api --method DELETE` is what it is watching.

    THE MUTANT LIVES AT THE PORT'S OWN PATH INSIDE THE THROWAWAY TREE, because the subject resolves its libraries from its own location; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '    return "%s/%s" % (versions_path(org, package), version_id)'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, '    return "%s/%s" % (versions_path(org, "renet"), version_id)'
    )

    name = "the-happy-path"
    want = recorded(name)
    root = build(tmp_path / "planted")
    (root / PORT_REL).write_text(mutated, encoding="utf-8")
    got = drive(root, name)

    assert got[:3] == want[:3], "the plant changed a stream or the exit code; wrong plant"
    assert got[3] != want[3], "THE CALL LOG DID NOT SEE IT: this corpus cannot fail"
    assert "container/rdc/versions/111" not in "\n".join(got[3])

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
