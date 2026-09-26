"""Differential: `rediacc_ci.deploy.upload_to_r2` against its twin `.ci/scripts/deploy/upload-to-r2.sh`.

A RECORDING FAKE `aws` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches R2, and nothing here reads or writes the real checkout: every case builds a throwaway tree holding the twin, the two bash libraries it sources, the port, and a `dist/` of its own, then runs both sides against it. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real
production run" clause and says in as many words that a mocked parity ledger is separate, achievable work. This is that work.

WHY THE FIXTURE HAS TO BE A WHOLE TREE. Both sides resolve the repository root
from their OWN location (`common.sh`'s `../../..` and the port's `../../..`), and
the port additionally reads `write_once_guard` out of the twin's text at run time. Run either from a scratch directory and it would walk back to this checkout. `.ci/config/constants.sh` and `.devcontainer/toolchain.env` are copied too, because constants.sh `exit 1`s without the latter.

THE FAKE ECHOES ITS OWN ARGV ONTO STDERR, and that is not decoration. Every line this program prints goes through `log_step`/`log_info`, which the shadow-gate classifier treats as CHATTER before any `--finding-re` sees it, so a ledger built on message text would record `VACUOUS_BOTH_EMPTY` for every row. With the fake echoing `call: aws ...`, the compared finding set becomes the
literal set of external calls the run made, which is the observable that actually matters here. It also means the streams being compared below CARRY the call sequence, in order, interleaved with the script's own lines, so a port that made the right calls in the wrong order fails on stderr rather than needing a second artifact.

The file log is still kept, and it holds the one thing the stream cannot: the CONTENT written to `cli/<channel>/latest.json` and to `cli/versions.json`. Two implementations can make identical calls and upload a different retention list.

`aws s3 cp ... - 2>/dev/null` (`r2_get`) and `aws s3 rm ... 2>/dev/null` (`r2_rm`) discard stderr on BOTH sides, so those two calls appear in the file log and not on the stream. That is the twin's behaviour, not a gap in the harness, and `test_a_failed_tracker_read_is_silent_on_both_streams` pins it.
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
from rediacc_ci.deploy import upload_to_r2 as port
from rediacc_ci.deploy import write_once_guard_check as harness

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "upload-to-r2.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "upload_to_r2.py"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "release-state-validator.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-key-fixture",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret-fixture",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
}

ENDPOINT = BASE_ENV["CLOUDFLARE_R2_ENDPOINT"]

# The default `dist/` a case gets. Two binaries so ORDER is observable, a `manifest.json` so the channel-pointer branch runs, and both npm tarballs so the `rediacc-cli-latest.tgz` skip is exercised.
DEFAULT_TREE = {
    "dist/cli/rdc-linux-x64": "linux binary\n",
    "dist/cli/rdc-darwin-arm64": "darwin binary\n",
    "dist/cli/manifest.json": '{"schema":1}\n',
    "dist/npm/rediacc-cli-1.2.3.tgz": "versioned tarball\n",
    "dist/npm/rediacc-cli-latest.tgz": "latest tarball\n",
}

# `s3api head-object` is the sentinel probe and `s3api list-objects-v2` the binary count, both driven by the environment so a case can pose any release state. `s3 cp <src> -` is `r2_get`, the only call whose STDOUT the script consumes. Everything else logs and succeeds.
FAKE_AWS = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
stdin = ""
if len(argv) > 2 and argv[1] == "cp" and argv[2] == "-":
    stdin = sys.stdin.read()
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("aws\\t" + "\\t".join(argv) + "\\n")
    if stdin:
        fh.write("STDIN<<<" + stdin + ">>>\\n")

# The distinctly-prefixed line the shadow-gate ledger keys on. stderr, because
# stdout is DATA for `r2_get` and a marker there would corrupt the tracker.
sys.stderr.write("call: aws " + " ".join(argv) + "\\n")
sys.stderr.flush()

sub = " ".join(argv[:2])
if sub == "s3api head-object":
    if os.environ.get("SENTINEL_EXISTS", "false") == "true":
        sys.exit(0)
    sys.stderr.write(
        "An error occurred (404) when calling the HeadObject operation: Not Found\\n"
    )
    sys.exit(254)
if sub == "s3api list-objects-v2":
    if os.environ.get("FAKE_LIST_RC", "0") != "0":
        sys.stderr.write("An error occurred (AccessDenied) when calling ListObjectsV2\\n")
        sys.exit(int(os.environ["FAKE_LIST_RC"]))
    sys.stdout.write(os.environ.get("PREFIX_KEYCOUNT", "0") + "\\n")
    sys.exit(0)
if sub == "s3 cp" and len(argv) > 3 and argv[3] == "-":
    if os.environ.get("FAKE_GET_RC", "0") != "0":
        sys.stderr.write("fatal error: An error occurred (ExpiredToken)\\n")
        sys.exit(int(os.environ["FAKE_GET_RC"]))
    body = os.environ.get("FAKE_TRACKER", "")
    if body:
        sys.stdout.write(body)
        sys.exit(0)
    sys.stderr.write("download failed: no such key\\n")
    sys.exit(1)

rc = int(os.environ.get("FAKE_AWS_RC", "0"))
if rc:
    sys.stderr.write("upload failed: the bucket said no\\n")
    sys.exit(rc)
"""

# Every real binary either side reaches for, and nothing else, so a tool leaking in from the machine would show up as a behaviour change. `bash` is on the list because the PORT spawns it twice (the guard and the globs); `jq` because the twin pipes the tracker through it and `test_without_jq...` removes it.
PATH_MINIMUM = (
    "bash",
    "jq",
    "uname",
    "dirname",
    "basename",
    "mktemp",
    "sed",
    "grep",
    "rm",
    "cat",
    "wc",
    "find",
)


def _bin(root: pathlib.Path, *, drop: str = "", aws_body: str = FAKE_AWS) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        link = stub / real_name
        if real_name == drop:
            if link.is_symlink() or link.exists():
                link.unlink()
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        if not link.exists():
            link.symlink_to(real)
    if drop != "aws":
        script = stub / "aws"
        script.write_text(aws_body, encoding="utf-8")
        script.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(tmp_path: pathlib.Path, tree: dict[str, str] | None = None) -> pathlib.Path:
    """A throwaway repository holding both implementations and a `dist/`."""
    root = tmp_path / "repo"
    for relative in (
        ".ci/scripts/deploy",
        ".ci/scripts/lib",
        ".ci/config",
        ".ci/rediacc_ci/deploy",
        ".devcontainer",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(VALIDATOR, root / ".ci" / "scripts" / "lib" / VALIDATOR.name)
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / CONSTANTS.name)
    shutil.copy2(TOOLCHAIN, root / ".devcontainer" / TOOLCHAIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "deploy" / PORT.name)

    for relative, body in (DEFAULT_TREE if tree is None else tree).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    # `dist/cli` and `dist/npm` must EXIST for the empty-directory cases to be about the loops rather than about the two `-d` tests above them.
    (root / "dist" / "cli").mkdir(parents=True, exist_ok=True)
    (root / "dist" / "npm").mkdir(parents=True, exist_ok=True)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    argv: tuple[str, ...] = ("--version", "1.2.3", "--channel", "edge"),
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    aws_body: str = FAKE_AWS,
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root, drop=drop, aws_body=aws_body),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        command = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name)]
    else:
        command = [sys.executable, str(root / ".ci" / "rediacc_ci" / "deploy" / PORT.name)]
    proc = subprocess.run(
        [*command, *argv],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, tree: dict[str, str] | None = None, **kw):
    """BOTH SIDES RUN AGAINST ONE TREE, which is a correctness requirement rather than a saving: the upload order is the SHELL'S GLOB ORDER over `dist/cli`, and two trees holding the same names can be enumerated differently. Neither side writes into `dist/`, and the two call logs have different names."""
    root = fixture(tmp_path, tree)
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: the call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def _cp(src: str, dest: str, cache: str) -> str:
    return (
        "aws\ts3\tcp\t%s\ts3://rediacc-releases/%s\t--endpoint-url\t%s\t--cache-control\t%s\t--no-progress\n"
        % (
            src,
            dest,
            ENDPOINT,
            cache,
        )
    )


IMMUTABLE = "public, max-age=31536000, immutable"


# --------------------------------------------------------------------------- The happy path, pinned against literal bytes ---------------------------------------------------------------------------


def test_a_full_upload_is_pinned_call_by_call(tmp_path: pathlib.Path) -> None:
    """THE WHOLE SEQUENCE ON A RELEASE CHANNEL: one sentinel probe, two immutable versioned copies, two mutable channel copies, the manifest, `latest.json` LAST, then the tracker read and write. The tracker's uploaded BYTES are asserted because they are jq's pretty-printer's, not `json.dumps`'s."""
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")
    assert old.returncode == 0
    assert old.stdout == ""

    cli = str(root / "dist" / "cli")
    npm = str(root / "dist" / "npm")
    assert old_calls == (
        "aws\ts3api\thead-object\t--bucket\trediacc-releases\t--key\tcli/v1.2.3/.released\t"
        "--endpoint-url\t%s\n"
        % ENDPOINT
        + _cp("%s/rdc-darwin-arm64" % cli, "cli/v1.2.3/rdc-darwin-arm64", IMMUTABLE)
        + _cp("%s/rdc-linux-x64" % cli, "cli/v1.2.3/rdc-linux-x64", IMMUTABLE)
        + _cp("%s/rdc-darwin-arm64" % cli, "cli/edge/rdc-darwin-arm64", "no-cache")
        + _cp("%s/rdc-linux-x64" % cli, "cli/edge/rdc-linux-x64", "no-cache")
        + _cp("%s/manifest.json" % cli, "cli/edge/manifest.json", "no-cache")
        + "aws\ts3\tcp\t-\ts3://rediacc-releases/cli/edge/latest.json\t--endpoint-url\t%s\t"
        "--content-type\tapplication/json\t--cache-control\tno-cache\t--no-progress\n"
        % ENDPOINT
        + 'STDIN<<<{"version":"1.2.3"}\n>>>\n'
        + "aws\ts3\tcp\ts3://rediacc-releases/cli/versions.json\t-\t--endpoint-url\t%s\n" % ENDPOINT
        + "aws\ts3\tcp\t-\ts3://rediacc-releases/cli/versions.json\t--endpoint-url\t%s\t"
        "--content-type\tapplication/json\t--cache-control\tno-cache\t--no-progress\n"
        % ENDPOINT
        + 'STDIN<<<[\n  "1.2.3"\n]\n>>>\n'
        + _cp("%s/rediacc-cli-1.2.3.tgz" % npm, "npm/edge/rediacc-cli-1.2.3.tgz", IMMUTABLE)
        + _cp("%s/rediacc-cli-latest.tgz" % npm, "npm/edge/rediacc-cli-latest.tgz", "no-cache")
    )
    assert "✓   Artifacts uploaded: 3\n" in old.stderr
    assert "✓   Bucket: rediacc-releases\n" in old.stderr
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_the_binary_order_is_the_shells_glob_order(tmp_path: pathlib.Path) -> None:
    """WHY THE PORT ASKS bash FOR THE GLOB. `for binary in "$CLI_DIR"/rdc-*` expands through `strcoll`, which is LOCALE dependent; `sorted(glob.glob())` is codepoint order. Under `C.UTF-8` here they agree, and the control below proves this fixture would notice if they did not: an uppercase name sorts BEFORE every lowercase one by codepoint and AFTER some of them under a
    dictionary collation, which is the disagreement a locale change produces."""
    tree = dict(DEFAULT_TREE)
    tree["dist/cli/rdc-Windows-x64.exe"] = "windows binary\n"
    tree["dist/cli/rdc-linux-x64.sha256"] = "checksum\n"
    old, new, old_calls, new_calls = run_both(tmp_path, tree)
    assert old.returncode == 0
    versioned = [
        line.split("\t")[4].rsplit("/", 1)[1]
        for line in old_calls.splitlines()
        if "s3://rediacc-releases/cli/v1.2.3/" in line
    ]
    assert versioned == [
        "rdc-Windows-x64.exe",
        "rdc-darwin-arm64",
        "rdc-linux-x64",
        "rdc-linux-x64.sha256",
    ], versioned
    assert versioned[0].startswith("rdc-W"), (
        "this fixture no longer holds a name whose case makes collation visible"
    )
    _assert_agree(old, new, "glob-order", old_calls, new_calls)


def test_a_pr_channel_never_writes_the_versioned_prefix(tmp_path: pathlib.Path) -> None:
    """THE VERSIONED PREFIX IS SCOPED TO stable AND edge, and so are the sentinel probe and the retention tracker. A `pr-N` run makes neither `s3api` call."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "pr-9")
    )
    assert old.returncode == 0
    assert "s3api" not in old_calls, "a pr channel probed the release sentinel"
    assert "cli/v1.2.3/" not in old_calls, "a pr channel wrote the immutable prefix"
    assert "versions.json" not in old_calls, "a pr channel touched the retention tracker"
    assert "s3://rediacc-releases/cli/pr-9/latest.json" in old_calls
    assert (
        "✓ CLI: uploaded to cli/pr-9/ (versioned path skipped; not a release channel)\n"
        in old.stderr
    )
    _assert_agree(old, new, "pr-channel", old_calls, new_calls)


def test_dry_run_makes_no_call_at_all(tmp_path: pathlib.Path) -> None:
    """`--dry-run` short-circuits inside all four R2 primitives AND inside the guard, so the whole run is text. It also skips the credential check, which the next test pins from the other direction."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "edge", "--dry-run")
    )
    assert old.returncode == 0
    assert old_calls == "", "a dry run reached aws"
    assert (
        "✓ [DRY-RUN] sentinel-aware guard would check "
        "s3://rediacc-releases/cli/v1.2.3/ (cli v1.2.3)\n" in old.stderr
    )
    assert "✓ [DRY-RUN] Would update cli/versions.json\n" in old.stderr
    assert "✓   Artifacts uploaded: 3\n" in old.stderr, "the counter still counts in a dry run"
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_dry_run_skips_the_credential_check(tmp_path: pathlib.Path) -> None:
    """The three-variable loop is inside `if [[ "$DRY_RUN" == "false" ]]`, so a
    dry run on a laptop with no R2 credentials is a supported thing to do."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        argv=("--version", "1.2.3", "--channel", "edge", "--dry-run"),
        drop_env=tuple(BASE_ENV),
    )
    assert old.returncode == 0
    assert "Missing required environment variable" not in old.stderr
    _assert_agree(old, new, "dry-run-no-creds", old_calls, new_calls)


# --------------------------------------------------------------------------- The write-once guard, which is the twin's own bash function on both sides ---------------------------------------------------------------------------


def test_the_guard_the_port_runs_is_the_twins_own_text() -> None:
    """THE PORT DOES NOT REIMPLEMENT `write_once_guard`; IT EXTRACTS IT. Asserted against the gate harness that makes the same extraction, so the two cannot drift apart, and against the twin's text so an empty extraction is visible."""
    source = TWIN.read_text(encoding="utf-8")
    extracted = port.extract_guard(source)
    assert extracted == harness.extract_guard(source), (
        "the port and write_once_guard_check.py now extract different text"
    )
    assert extracted.startswith("write_once_guard() {\n")
    assert extracted.endswith("}\n")
    assert "rsv_sentinel_exists" in extracted
    assert "rsv_binary_count" in extracted
    assert "return 10" in extracted
    # NOT a Python reimplementation: nothing in the port spells the guard's logic.
    body = PORT.read_text(encoding="utf-8")
    assert "rsv_sentinel_exists" not in body.split('"""', 2)[2], (
        "the port's CODE names a validator function; the guard must stay bash"
    )


def test_the_guard_runner_preserves_the_twins_errexit_suppression() -> None:
    """`write_once_guard ... || guard_rc=$?` SUPPRESSES errexit inside the whole
    function body, and that suppression is what makes defect 2 reachable. A
    runner calling the function bare would abort where the twin continues, so the
    `|| rc=$?` is asserted rather than assumed."""
    runner = port.guard_runner_source("/c.sh", "/v.sh", "write_once_guard() { :; }\n")
    assert 'write_once_guard "$1" "$2" || rc=$?' in runner
    assert runner.startswith("source '/c.sh'\nsource '/v.sh'\n")
    assert runner.endswith("exit $rc\n")


def test_sealed_with_binaries_skips_the_prefix_but_still_moves_the_pointer(
    tmp_path: pathlib.Path,
) -> None:
    """GUARD ANSWER 10, an idempotent rerun of a published version. The immutable prefix is NOT rewritten (the immutable-URL promise) and the channel pointers still refresh, which is the whole reason the guard returns a code instead of aborting."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, SENTINEL_EXISTS="true", PREFIX_KEYCOUNT="16"
    )
    assert old.returncode == 0
    assert "s3://rediacc-releases/cli/v1.2.3/rdc-" not in old_calls, "a sealed prefix was rewritten"
    assert "s3://rediacc-releases/cli/edge/latest.json" in old_calls, (
        "the pointer stopped refreshing"
    )
    assert "✓ Idempotent: cli v1.2.3 is already sealed with 16 binary object(s).\n" in old.stderr
    assert "✓   Artifacts uploaded: 1\n" in old.stderr
    _assert_agree(old, new, "sealed-skip", old_calls, new_calls)


def test_sealed_but_empty_refuses_loudly_and_stops_the_run(tmp_path: pathlib.Path) -> None:
    """GUARD ANSWER `exit 1`. The guard's `exit` ends the SCRIPT, so nothing after it runs: no channel upload, no pointer, no npm, no summary."""
    old, new, old_calls, new_calls = run_both(tmp_path, SENTINEL_EXISTS="true", PREFIX_KEYCOUNT="0")
    assert old.returncode == 1
    assert (
        "✗ Corrupt release state: s3://rediacc-releases/cli/v1.2.3/ is SEALED "
        "(.released present) but has NO binaries.\n" in old.stderr
    )
    assert "scripts/ops/scrub-sentinel.sh v1.2.3 --execute" in old.stderr
    assert "R2 upload complete" not in old.stderr, "the run continued past the refusal"
    assert old_calls.count("aws\ts3\tcp") == 0
    _assert_agree(old, new, "sealed-empty", old_calls, new_calls)


def test_defect_an_unanswered_count_reads_as_sealed_but_empty(tmp_path: pathlib.Path) -> None:
    """DEFECT 2, PINNED. `rsv_binary_count` cannot answer (AccessDenied), says so, and returns non-zero WITHOUT printing a count, exactly so its caller aborts instead of acting on a fabricated 0 (`release-state-validator.sh:161-166`). The abort never happens, because the twin consumes the guard's status with
    `|| guard_rc=$?` and that suppresses errexit inside the function. The empty
    count then reads as zero and the operator is told to scrub the sentinel of a healthy sealed release.

    Reproduced rather than repaired: agreement with the live twin is this wave's deliverable, and the fix is a cutover-box decision. If it is ever repaired, this test goes red and names the port that must follow."""
    old, new, old_calls, new_calls = run_both(tmp_path, SENTINEL_EXISTS="true", FAKE_LIST_RC="255")
    assert old.returncode == 1
    assert "✗ rsv_binary_count: list-objects-v2 failed for" in old.stderr
    assert "is SEALED (.released present) but has NO binaries." in old.stderr, (
        "an unanswered probe stopped being reported as sealed-but-empty"
    )
    assert "scripts/ops/scrub-sentinel.sh v1.2.3 --execute" in old.stderr
    assert port.AN_UNANSWERED_COUNT_READS_AS_SEALED_BUT_EMPTY
    _assert_agree(old, new, "unanswered-count", old_calls, new_calls)


def test_the_guard_refuses_loudly_when_the_twins_text_is_gone(tmp_path: pathlib.Path) -> None:
    """THE ONE STATE THE TWIN CANNOT BE IN, so there is nothing to diverge from: the port reads the guard out of the twin, so a missing twin means the guard cannot run. A `command not found` from bash would read as flake, so the refusal names the file and says why the function is not Python."""
    root = fixture(tmp_path)
    (root / ".ci" / "scripts" / "deploy" / TWIN.name).unlink()
    new, calls = _run(root, "new")
    assert new.returncode == 1
    assert "cannot run the write-once guard" in new.stderr
    assert "deliberately NOT reimplemented in Python" in new.stderr
    assert calls == "", "the run reached aws without a guard"


# --------------------------------------------------------------------------- The retention tracker ---------------------------------------------------------------------------


def test_the_retention_window_prunes_and_deletes(tmp_path: pathlib.Path) -> None:
    """22 known versions plus a new one: three fall out of the 20-entry window, and each pruned prefix gets one `aws s3 rm --recursive`. The tracker written back is jq's bytes, asserted in full because a `json.dumps` port would upload a different file while printing the same lines."""
    tracker = "[%s]" % ",".join('"9.9.%d"' % index for index in range(22))
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "stable"), FAKE_TRACKER=tracker
    )
    assert old.returncode == 0
    kept = '[\n  "1.2.3",\n' + "".join('  "9.9.%d",\n' % index for index in range(18))
    assert kept + '  "9.9.18"\n]' in old_calls
    assert "✓   Deleting cli/v9.9.19/\n" in old.stderr
    assert "✓   Deleting cli/v9.9.21/\n" in old.stderr
    assert old_calls.count("aws\ts3\trm") == 3
    assert (
        "aws\ts3\trm\ts3://rediacc-releases/cli/v9.9.19/\t--recursive\t--endpoint-url\t%s\n"
        % ENDPOINT
        in old_calls
    )
    _assert_agree(old, new, "prune", old_calls, new_calls)


def test_a_version_already_in_the_tracker_is_not_added_twice(tmp_path: pathlib.Path) -> None:
    """`if index($v) then . else [$v] + . end`: a re-release keeps its place rather than jumping to the front, which is what makes a stable promotion of an existing edge version a no-op for the window."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        argv=("--version", "1.2.3", "--channel", "stable"),
        FAKE_TRACKER='["9.9.1","1.2.3","9.9.0"]',
    )
    assert old.returncode == 0
    assert 'STDIN<<<[\n  "9.9.1",\n  "1.2.3",\n  "9.9.0"\n]\n>>>' in old_calls
    assert "Cleaning up" not in old.stderr
    _assert_agree(old, new, "no-duplicate", old_calls, new_calls)


def test_defect_a_failed_tracker_read_resets_the_retention_window(
    tmp_path: pathlib.Path,
) -> None:
    """DEFECT 3, PINNED. `r2_get` is `... 2>/dev/null || echo ""`, so an expired token and an absent object are one empty string. A 22-entry tracker comes back as a one-entry tracker, exit 0, no warning, and the 21 versions that vanished are never passed to `cleanup_old_versions`, so their prefixes are orphaned until the nightly sweep.

    Reproduced rather than repaired, for the reason in the docstring."""
    tracker = "[%s]" % ",".join('"9.9.%d"' % index for index in range(22))
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        argv=("--version", "1.2.3", "--channel", "stable"),
        FAKE_TRACKER=tracker,
        FAKE_GET_RC="255",
    )
    assert old.returncode == 0
    assert 'STDIN<<<[\n  "1.2.3"\n]\n>>>' in old_calls, "the window was not reset"
    assert "9.9." not in old.stderr, "the loss was announced"
    assert "aws\ts3\trm" not in old_calls, "the lost versions were pruned after all"
    assert port.A_FAILED_TRACKER_READ_RESETS_THE_WINDOW
    _assert_agree(old, new, "tracker-reset", old_calls, new_calls)


def test_a_failed_tracker_read_is_silent_on_both_streams(tmp_path: pathlib.Path) -> None:
    """`2>/dev/null` ON BOTH SIDES. aws's own explanation of the failure is discarded, which is why the fake's `call:` marker for `r2_get` appears in the file log and NOT on stderr. Asserted so a later reader does not mistake the absence for a hole in the harness."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "stable"), FAKE_GET_RC="255"
    )
    assert "ExpiredToken" not in old.stderr
    assert "call: aws s3 cp s3://rediacc-releases/cli/versions.json" not in old.stderr
    assert "aws\ts3\tcp\ts3://rediacc-releases/cli/versions.json\t-" in old_calls
    _assert_agree(old, new, "silent-get", old_calls, new_calls)


def test_defect_a_malformed_tracker_is_overwritten_with_an_empty_file(
    tmp_path: pathlib.Path,
) -> None:
    """DEFECT 4, PINNED, AND IT DESTROYS DATA. A `cli/versions.json` that is not valid JSON makes the first jq fail. Nothing stops: the three pipelines live
    inside `CLI_PRUNED=$(update_versions_tracker ...)`, and bash does not apply
    errexit inside a command substitution whose value is assigned. `updated` is empty, the next two jq calls on empty input succeed producing nothing, and the tracker is REPLACED WITH AN EMPTY BODY. One `jq: parse error` scrolls past, `R2 upload complete` prints, and the run exits 0.

    Reproduced rather than repaired, for the reason in the docstring. This is the test that would have gone red for a port that simply raised on a non-zero `jq`, which is what a careful reader writes first."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        argv=("--version", "1.2.3", "--channel", "stable"),
        FAKE_TRACKER="{ this is not json",
    )
    assert old.returncode == 0, "the malformed tracker stopped being survivable"
    assert "jq: parse error" in old.stderr
    assert "→ R2 upload complete\n" in old.stderr, "the run did not report success"
    assert "STDIN<<<\n>>>" in old_calls, "the tracker was not overwritten empty"
    assert old.stdout == "", "a failing jq leaked its partial output onto stdout"
    assert port.A_MALFORMED_TRACKER_IS_OVERWRITTEN_EMPTY
    _assert_agree(old, new, "bad-tracker", old_calls, new_calls)


def test_a_failing_tracker_write_does_still_abort_the_run(tmp_path: pathlib.Path) -> None:
    """THE OTHER HALF OF DEFECT 4, AND THE ASYMMETRY IS THE POINT. A command substitution takes the status of its LAST command, so the closing `r2_put` IS the assignment's status and errexit fires on it, while every jq above it is swallowed. Driven with an `aws` that fails everything, so the run dies at the first upload rather than the tracker; the narrower case is that the
    tracker write is the one command in that function whose failure is fatal."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "stable"), FAKE_AWS_RC="9"
    )
    assert old.returncode == 9
    _assert_agree(old, new, "tracker-write-fails", old_calls, new_calls)


def test_without_jq_version_tracking_is_skipped_with_a_warning(tmp_path: pathlib.Path) -> None:
    """`command -v jq &>/dev/null` guards the whole tracker update, so a machine without jq still uploads and still refreshes the pointers. The port uses `shutil.which`, which differs from `command -v` only for a shell FUNCTION or alias named jq, and a script bash spawns cannot inherit either."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "stable"), drop="jq"
    )
    assert old.returncode == 0
    assert "⚠ jq not available, skipping version tracking for cli\n" in old.stderr
    assert "aws\ts3\tcp\t-\ts3://rediacc-releases/cli/versions.json" not in old_calls
    assert "aws\ts3\tcp\ts3://rediacc-releases/cli/versions.json\t-" in old_calls, (
        "the tracker READ happens before the jq check and is wasted; that is the twin's order"
    )
    _assert_agree(old, new, "no-jq", old_calls, new_calls)


# --------------------------------------------------------------------------- bump-none ---------------------------------------------------------------------------


def test_the_bump_none_banner_is_pinned_on_stdout(tmp_path: pathlib.Path) -> None:
    """THE REFUSAL BLOCK, byte for byte, on STDOUT and with exit 0: the twin's own closing sentence says this is the intended outcome, not an error. Nothing is written and the guard is never even probed."""
    for channel in port.RELEASE_CHANNELS:
        case = tmp_path / f"skip-{channel}"
        old, new, old_calls, new_calls = run_both(
            case, argv=("--version", "1.2.3", "--channel", channel, "--skip-release")
        )
        assert old.returncode == 0
        assert old.stderr == ""
        assert old.stdout == "\n".join(port.skip_banner("1.2.3", channel)) + "\n"
        assert "RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2" in old.stdout
        assert "    - cli/v1.2.3/              (versioned, immutable path)" in old.stdout
        assert old_calls == "", "a skipped release still wrote to R2"
        _assert_agree(old, new, f"skip-{channel}", old_calls, new_calls)


def test_skip_release_on_a_pr_channel_uploads_as_usual(tmp_path: pathlib.Path) -> None:
    """SCOPED TO THE RELEASE CHANNELS: a `pr-N` channel has no tag contract, so the flag is announced and ignored. The notice precedes the first `log_step`, which is the ordering a port could easily get wrong."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "pr-9", "--skip-release")
    )
    assert old.returncode == 0
    assert old.stderr.startswith(
        "✓ --skip-release ignored on channel 'pr-9': not a release channel, uploading as usual\n"
        "→ Uploading v1.2.3 to R2 channel: pr-9\n"
    )
    assert "s3://rediacc-releases/cli/pr-9/latest.json" in old_calls
    _assert_agree(old, new, "skip-pr", old_calls, new_calls)


@pytest.mark.parametrize("spelling", ["true", "ON", "y", "1"])
def test_the_env_spellings_that_do_skip(tmp_path: pathlib.Path, spelling: str) -> None:
    """`SKIP_RELEASE` IS THE SAME SWITCH AS `--skip-release`, read from the environment before the parser runs."""
    old, new, old_calls, new_calls = run_both(tmp_path, SKIP_RELEASE=spelling)
    assert old.returncode == 0
    assert "RELEASE SKIPPED" in old.stdout, spelling
    assert old_calls == ""
    _assert_agree(old, new, f"skip-env-{spelling}", old_calls, new_calls)


@pytest.mark.parametrize("spelling", ["TrUe", "Y", "false", "", "0"])
def test_the_env_spellings_that_do_not_skip(tmp_path: pathlib.Path, spelling: str) -> None:
    """THE `case` ARMS ARE SPELLINGS, NOT A PREDICATE. A port using
    `.lower() in {...}` would suppress a release the twin publishes, and one
    testing truthiness would suppress `0`. Both directions are driven."""
    old, new, old_calls, new_calls = run_both(tmp_path, SKIP_RELEASE=spelling)
    assert old.returncode == 0
    assert "RELEASE SKIPPED" not in old.stdout, f"{spelling!r} was treated as a skip"
    assert "s3://rediacc-releases/cli/edge/latest.json" in old_calls
    _assert_agree(old, new, f"no-skip-env-{spelling}", old_calls, new_calls)


# --------------------------------------------------------------------------- Vacuity, credentials, and the shapes of `dist/` ---------------------------------------------------------------------------


def test_defect_an_empty_cli_dir_publishes_a_channel_pointer(tmp_path: pathlib.Path) -> None:
    """DEFECT 1, PINNED. `dist/cli/` exists and holds nothing. No binary and no manifest is uploaded, and `latest.json` is written anyway, so every installer on the channel resolves to a version with zero bytes behind it. The summary prints `Artifacts uploaded: 0` on the next line and nothing acts on it.

    Reproduced rather than repaired, for the reason in the docstring. This is the same harm the bump-none block at the top of the twin prevents, arriving by a different door."""
    old, new, old_calls, new_calls = run_both(tmp_path, tree={})
    assert old.returncode == 0
    assert 'STDIN<<<{"version":"1.2.3"}\n>>>' in old_calls, "no pointer, so there is no defect"
    assert "rdc-" not in old_calls, "a binary was uploaded after all"
    assert "✓ CLI: uploaded to cli/v1.2.3/ + cli/edge/\n" in old.stderr
    assert "✓   Artifacts uploaded: 0\n" in old.stderr
    assert port.AN_EMPTY_CLI_DIR_PUBLISHES_A_POINTER
    _assert_agree(old, new, "empty-cli-dir", old_calls, new_calls)


def test_the_uploaded_counter_ignores_every_channel_upload(tmp_path: pathlib.Path) -> None:
    """`((UPLOADED++))` SITS ONLY IN THE TWO IMMUTABLE LOOPS. A `pr-N` run that uploads two binaries, a manifest, a pointer and two tarballs reports `Artifacts uploaded: 1`. Not a divergence, a property of the twin, and pinned because a port that "fixed" the count would look more correct and be wrong."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "pr-9")
    )
    assert old_calls.count("aws\ts3\tcp") == 6
    assert "✓   Artifacts uploaded: 1\n" in old.stderr
    _assert_agree(old, new, "undercount", old_calls, new_calls)


def test_a_missing_cli_directory_warns_and_a_missing_npm_directory_informs(
    tmp_path: pathlib.Path,
) -> None:
    """DIFFERENT LEVELS FOR THE TWO ABSENCES, and the twin means it: a missing `dist/cli` is a warning because a release without binaries is odd, a missing `dist/npm` is an info because not every build makes a tarball."""
    root = fixture(tmp_path, tree={})
    (root / "dist" / "cli").rmdir()
    (root / "dist" / "npm").rmdir()
    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")
    assert old.returncode == 0
    assert "⚠ CLI directory not found: %s/dist/cli\n" % root in old.stderr
    assert "✓ npm directory not found: %s/dist/npm (skipping)\n" % root in old.stderr
    assert old_calls == "", "nothing existed and something was still uploaded"
    assert "✓   Artifacts uploaded: 0\n" in old.stderr
    _assert_agree(old, new, "absent-dirs", old_calls, new_calls)


def test_the_latest_tarball_is_uploaded_mutable_and_never_versioned(
    tmp_path: pathlib.Path,
) -> None:
    """`rediacc-cli-latest.tgz` IS SKIPPED BY THE LOOP AND HANDLED AFTER IT, with the mutable policy, because its filename carries no version and its URL does serve different bytes over time."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    # ONE LINE, not one occurrence: the source path and the destination key both carry the name, so counting substrings would report two for one upload.
    uploads = [line for line in old_calls.splitlines() if "rediacc-cli-latest.tgz" in line]
    assert len(uploads) == 1, uploads
    assert (
        "\ts3://rediacc-releases/npm/edge/rediacc-cli-latest.tgz\t--endpoint-url\t%s\t"
        "--cache-control\tno-cache\t" % ENDPOINT in old_calls
    )
    _assert_agree(old, new, "npm-latest", old_calls, new_calls)


@pytest.mark.parametrize("missing", list(port.REQUIRED_CREDENTIALS))
def test_the_credentials_are_named_one_at_a_time_in_the_twins_order(
    tmp_path: pathlib.Path, missing: str
) -> None:
    """THE FIRST MISSING ONE WINS, and the loop's order is what selects it. Each
    case drops exactly one variable, so the message names that one."""
    old, new, old_calls, new_calls = run_both(tmp_path / missing, drop_env=(missing,))
    assert old.returncode == 1
    assert old.stderr.endswith("✗ Missing required environment variable: %s\n" % missing)
    assert old_calls == "", "a run with no credentials still reached aws"
    _assert_agree(old, new, f"no-{missing}", old_calls, new_calls)


def test_an_empty_credential_refuses_exactly_as_an_absent_one_does(
    tmp_path: pathlib.Path,
) -> None:
    """`[[ -z "${!var:-}" ]]` IS AN UNSET-OR-EMPTY TEST. A port checking
    membership in the environment would sail past this and hand aws an empty key, which fails much later and much less clearly."""
    old, new, old_calls, new_calls = run_both(tmp_path, CLOUDFLARE_R2_ENDPOINT="")
    assert old.returncode == 1
    assert "✗ Missing required environment variable: CLOUDFLARE_R2_ENDPOINT\n" in old.stderr
    _assert_agree(old, new, "empty-credential", old_calls, new_calls)


def test_the_r2_credentials_are_bridged_into_the_aws_names(tmp_path: pathlib.Path) -> None:
    """`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION=auto`
    are EXPORTED for the child, not passed as arguments, so a port that set them on itself without exporting would look identical from the outside."""
    reporter = (
        "#!/usr/bin/python3\n"
        "import os\n"
        'with open(os.environ["FAKE_CALL_LOG"], "a") as fh:\n'
        '    fh.write("env\\t%s\\t%s\\t%s\\n" % (\n'
        '        os.environ.get("AWS_ACCESS_KEY_ID", "-"),\n'
        '        os.environ.get("AWS_SECRET_ACCESS_KEY", "-"),\n'
        '        os.environ.get("AWS_DEFAULT_REGION", "-"),\n'
        "    ))\n"
    )
    root = fixture(tmp_path)
    for side in ("old", "new"):
        proc, calls = _run(
            root, side, ("--version", "1.2.3", "--channel", "pr-9"), aws_body=reporter
        )
        assert proc.returncode == 0, calls
        assert "env\tr2-key-fixture\tr2-secret-fixture\tauto\n" in calls, side
        assert calls.count("env\t") == 6, side


def test_the_bucket_is_read_from_the_environment(tmp_path: pathlib.Path) -> None:
    """`RELEASES_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"` in constants.sh.
    The port does not source constants.sh, so this proves the override still reaches BOTH the four R2 primitives and the bash guard's child."""
    old, new, old_calls, new_calls = run_both(tmp_path, RELEASES_BUCKET="other-bucket")
    assert old.returncode == 0
    assert "s3://other-bucket/cli/edge/latest.json" in old_calls
    assert "--bucket\tother-bucket\t" in old_calls, "the guard child kept the default bucket"
    assert "✓   Bucket: other-bucket\n" in old.stderr
    _assert_agree(old, new, "bucket-override", old_calls, new_calls)


def test_the_npm_directory_is_read_from_the_environment(tmp_path: pathlib.Path) -> None:
    """`NPM_DIR="${NPM_DIR:-$REPO_ROOT/dist/npm}"`, resolved AFTER the CLI section
    and therefore after `latest.json` has already been written."""
    root = fixture(tmp_path, tree={"alt/rediacc-cli-9.9.9.tgz": "alt tarball\n"})
    old, old_calls = _run(root, "old", NPM_DIR=str(root / "alt"))
    new, new_calls = _run(root, "new", NPM_DIR=str(root / "alt"))
    assert old.returncode == 0
    assert "s3://rediacc-releases/npm/edge/rediacc-cli-9.9.9.tgz" in old_calls
    _assert_agree(old, new, "npm-dir-override", old_calls, new_calls)


def test_an_unguarded_aws_failure_ends_the_run_with_its_status(tmp_path: pathlib.Path) -> None:
    """`r2_cp` IS UNGUARDED, so `set -e` ends the run with aws's status and aws's own stderr is the only explanation. The loop does not continue to the second binary and no summary is printed."""
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_AWS_RC="7")
    assert old.returncode == 7
    assert old.stderr.endswith("upload failed: the bucket said no\n")
    assert old_calls.count("aws\ts3\tcp") == 1, "the loop continued past a failed upload"
    assert "R2 upload complete" not in old.stderr
    _assert_agree(old, new, "aws-fails", old_calls, new_calls)


# --------------------------------------------------------------------------- Argument parsing, including the two divergences ---------------------------------------------------------------------------


def test_version_is_required_before_channel(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE: a run missing BOTH names `--version`, because its check sits above the `REPO_ROOT` block and the channel check sits below."""
    old, new, old_calls, new_calls = run_both(tmp_path, argv=())
    assert old.returncode == 1
    assert old.stderr == "✗ --version is required\n"
    _assert_agree(old, new, "no-version", old_calls, new_calls)


def test_channel_is_required_and_an_empty_one_counts_as_absent(
    tmp_path: pathlib.Path,
) -> None:
    """`[[ -z "$CHANNEL" ]]`, so `--channel ''` refuses rather than uploading to `cli//`, which is every channel's parent prefix."""
    for argv in (("--version", "1.2.3"), ("--version", "1.2.3", "--channel", "")):
        case = tmp_path / ("empty" if len(argv) > 2 else "absent")
        old, new, old_calls, new_calls = run_both(case, argv=argv)
        assert old.returncode == 1
        assert old.stderr == "✗ --channel is required\n"
        assert old_calls == ""
        _assert_agree(old, new, "no-channel", old_calls, new_calls)


def test_an_unknown_option_names_itself(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, argv=("--bogus", "--version", "1.2.3"))
    assert old.returncode == 1
    assert old.stderr == "✗ Unknown option: --bogus\n"
    _assert_agree(old, new, "unknown-option", old_calls, new_calls)


def test_a_deprecated_packages_dir_still_consumes_its_value(tmp_path: pathlib.Path) -> None:
    """`--packages-dir` is DEPRECATED and its value is never read, but it still takes one: dropping the arm would make the path fall through to `Unknown option` and break a caller that still passes it."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, argv=("--version", "1.2.3", "--channel", "edge", "--packages-dir", "/nowhere")
    )
    assert old.returncode == 0
    assert "/nowhere" not in old.stderr
    _assert_agree(old, new, "packages-dir", old_calls, new_calls)


def test_divergence_help_prints_the_path_it_was_invoked_by(tmp_path: pathlib.Path) -> None:
    """DIVERGENCE 1, ASSERTED IN BOTH DIRECTIONS. `Usage: $0` names the file that is running, so the twin names a `.sh` and the port names a `.py`. Everything after the path is byte-identical, and that is what is compared."""
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old", ("--help",))
    new, new_calls = _run(root, "new", ("-h",))
    assert old.returncode == new.returncode == 0
    assert old.stderr == new.stderr == ""
    assert old_calls == new_calls == ""

    tail = (
        " --version VERSION --channel CHANNEL [--cli-dir DIR] [--packages-dir DIR] "
        "[--skip-release] [--dry-run]\n"
    )
    assert old.stdout == "Usage: %s%s" % (root / ".ci/scripts/deploy/upload-to-r2.sh", tail)
    assert new.stdout == "Usage: %s%s" % (root / ".ci/rediacc_ci/deploy/upload_to_r2.py", tail)
    assert old.stdout.split(" ", 2)[2] == new.stdout.split(" ", 2)[2]


@pytest.mark.parametrize("flag", ["--version", "--channel", "--cli-dir", "--packages-dir"])
def test_divergence_a_flag_without_a_value_is_bashs_unbound_variable(
    tmp_path: pathlib.Path, flag: str
) -> None:
    """DIVERGENCE 2, ASSERTED IN BOTH DIRECTIONS FOR ALL FOUR VALUE FLAGS. bash prints its own FILE and LINE NUMBER (the number differs per flag) ahead of `$2: unbound variable`; the port prints the message half. Same stream, same status 1, no call from either side."""
    old, new, old_calls, new_calls = run_both(tmp_path / flag.strip("-"), argv=(flag,))
    assert old.returncode == new.returncode == 1
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == ""
    assert old.stderr.endswith(": $2: unbound variable\n"), old.stderr
    assert ": line " in old.stderr, "bash stopped naming a line; re-read this divergence"
    assert new.stderr == "$2: unbound variable\n"


# --------------------------------------------------------------------------- Staleness alarms: every constant restated from the twin, re-derived ---------------------------------------------------------------------------


def test_the_constants_are_the_twins_constants() -> None:
    """`BUCKET_DEFAULT` and `MAX_RELEASE_VERSIONS` are copies of `.ci/config/constants.sh`, which the port deliberately does not source. They are re-derived here so a change there turns this red instead of silently pointing the port at a different bucket."""
    source = CONSTANTS.read_text(encoding="utf-8")
    bucket = re.search(
        r'^readonly RELEASES_BUCKET="\$\{RELEASES_BUCKET:-([^}]*)\}"', source, re.MULTILINE
    )
    maximum = re.search(r"^readonly R2_MAX_RELEASE_VERSIONS=(\d+)", source, re.MULTILINE)
    assert bucket is not None, "constants.sh no longer spells RELEASES_BUCKET this way"
    assert maximum is not None, "constants.sh no longer spells R2_MAX_RELEASE_VERSIONS this way"
    assert bucket.group(1) == port.BUCKET_DEFAULT
    assert int(maximum.group(1)) == port.MAX_RELEASE_VERSIONS


def test_the_cache_control_policies_are_the_twins() -> None:
    """The immutable policy is legitimate on `cli/v<V>/` and was an INCIDENT on a
    package-manager channel path (see `upload_repos_to_r2.py`'s header). The two
    strings are re-derived so the two files cannot drift into each other."""
    source = TWIN.read_text(encoding="utf-8")
    found = dict(re.findall(r'^readonly (CACHE_CONTROL_\w+)="([^"]*)"', source, re.MULTILINE))
    assert found == {
        "CACHE_CONTROL_MUTABLE": port.CACHE_CONTROL_MUTABLE,
        "CACHE_CONTROL_IMMUTABLE": port.CACHE_CONTROL_IMMUTABLE,
    }


def test_the_skip_values_are_the_twins_case_arms() -> None:
    """STALENESS ALARM for the `case` arms, which sit between the two markers the gate test `test_gate_skip_release_channel_pointer.py` splits the twin on to build its mutants."""
    source = TWIN.read_text(encoding="utf-8")
    arm = re.search(r"case \"\$\{SKIP_RELEASE:-\}\" in\n\s*([^)]*)\) return 0", source)
    assert arm is not None, "the case shape changed; this alarm reads nothing"
    assert {value.strip() for value in arm.group(1).split("|")} == set(port.SKIP_RELEASE_VALUES)


def test_the_credential_list_is_the_twins() -> None:
    source = TWIN.read_text(encoding="utf-8")
    loop = re.search(r"^    for var in ([^\n;]*); do", source, re.MULTILINE)
    assert loop is not None, "the credential loop changed shape; this alarm reads nothing"
    assert tuple(loop.group(1).split()) == port.REQUIRED_CREDENTIALS


def test_the_skip_release_markers_still_bracket_the_guard() -> None:
    """The gate test assembles its mutants by splitting the twin on these two markers. They are not this port's, and a wave that removed them would break that gate silently, so their presence is asserted from here too."""
    source = TWIN.read_text(encoding="utf-8")
    assert source.count("SKIP_RELEASE_GUARD_BEGIN") == 1
    assert source.count("SKIP_RELEASE_GUARD_END") == 1
    begin = source.index("SKIP_RELEASE_GUARD_BEGIN")
    end = source.index("SKIP_RELEASE_GUARD_END")
    assert begin < source.index("skip_release_requested()") < end


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_pure_helpers() -> None:
    assert port.SELF == "upload-to-r2.sh"
    assert port.RELEASE_CHANNELS == ("stable", "edge")
    assert port.releases_bucket() in (port.BUCKET_DEFAULT, os.environ.get("RELEASES_BUCKET"))

    assert port.cp_argv("/a", "s3://b/c", "https://e", "no-cache") == [
        "aws",
        "s3",
        "cp",
        "/a",
        "s3://b/c",
        "--endpoint-url",
        "https://e",
        "--cache-control",
        "no-cache",
        "--no-progress",
    ]
    assert port.put_argv("s3://b/c", "https://e", "application/json")[:5] == [
        "aws",
        "s3",
        "cp",
        "-",
        "s3://b/c",
    ]
    # The content type is the caller's; the cache policy never is.
    assert port.put_argv("s3://b/c", "https://e", "text/plain")[5:] == [
        "--endpoint-url",
        "https://e",
        "--content-type",
        "text/plain",
        "--cache-control",
        "no-cache",
        "--no-progress",
    ]
    assert port.rm_argv("s3://b/p/", "https://e") == [
        "aws",
        "s3",
        "rm",
        "s3://b/p/",
        "--recursive",
        "--endpoint-url",
        "https://e",
    ]
    assert port.get_argv("s3://b/p", "https://e") == [
        "aws",
        "s3",
        "cp",
        "s3://b/p",
        "-",
        "--endpoint-url",
        "https://e",
    ]
    assert port.r2_path("cli", "edge", "latest.json") == "cli/edge/latest.json"

    for value in ("true", "TRUE", "True", "1", "yes", "YES", "y", "on", "ON"):
        assert port.skip_release_requested(value), value
    for value in ("TrUe", "Y", "false", "no", "0", "", "ON "):
        assert not port.skip_release_requested(value), value

    banner = port.skip_banner("1.2.3", "edge")
    assert banner[0] == ""
    assert banner[-1] == ""
    assert banner[4] == "  version:  v1.2.3"
    assert banner[5] == "  channel:  edge"
    assert len(banner) == 22

    # A sed range RE-ARMS, so a second definition is appended rather than ignored.
    twice = "write_once_guard() {\n  :\n}\nnoise\nwrite_once_guard() {\n  x\n}\n"
    assert port.extract_guard(twice).count("write_once_guard() {") == 2
    assert port.extract_guard("nothing here\n") == ""
    # `^}` is anchored: an indented brace does not close the range.
    assert port.extract_guard("write_once_guard() {\n  if x; then\n  }\n}\n").count("\n") == 4


def test_parse_args_is_the_twins_parser() -> None:
    parsed = port.parse_args(["--version", "1.2.3", "--channel", "edge"], "prog")
    assert parsed["version"] == "1.2.3"
    assert parsed["channel"] == "edge"
    assert parsed["dry_run"] == "false"

    parsed = port.parse_args(["--dry-run", "--skip-release", "--cli-dir", "/d"], "prog")
    assert parsed["dry_run"] == "true"
    assert parsed["skip_release"] == "true"
    assert parsed["cli_dir"] == "/d"

    assert port.parse_args(["--help"], "prog")["help"].startswith("Usage: prog --version")
    # `-h` short-circuits, so a later bad flag is never seen.
    assert port.parse_args(["-h", "--bogus"], "prog")["help"]

    with pytest.raises(port.UsageError) as unknown:
        port.parse_args(["--bogus"], "prog")
    assert unknown.value.message == "Unknown option: --bogus"
    assert unknown.value.logged

    with pytest.raises(port.UsageError) as unbound:
        port.parse_args(["--channel"], "prog")
    assert unbound.value.message == "$2: unbound variable"
    assert not unbound.value.logged

    # An empty argument is not a flag, so it lands in the catch-all arm.
    with pytest.raises(port.UsageError) as empty:
        port.parse_args([""], "prog")
    assert empty.value.message == "Unknown option: "


def test_bash_glob_is_bashs_answer_including_the_literal_miss(tmp_path: pathlib.Path) -> None:
    """WITHOUT `nullglob` AN UNMATCHED PATTERN EXPANDS TO ITSELF, and the twin relies on it: `[[ -f "$binary" ]] || continue` is what discards the literal. `glob.glob` returns `[]`, so a port using it would agree by accident here and disagree the day someone adds a `shopt`."""
    (tmp_path / "rdc-b").write_text("b", encoding="utf-8")
    (tmp_path / "rdc-a").write_text("a", encoding="utf-8")
    (tmp_path / "other").write_text("o", encoding="utf-8")
    assert port.bash_glob(str(tmp_path), "rdc-*") == [
        str(tmp_path / "rdc-a"),
        str(tmp_path / "rdc-b"),
    ]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert port.bash_glob(str(empty), "rdc-*") == [str(empty / "rdc-*")]


# --------------------------------------------------------------------------- Anti-vacuity: the differential must be able to fail ---------------------------------------------------------------------------


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """PLANTED ON THE IMMUTABLE CACHE-CONTROL, the field whose loss is invisible on both streams and in both exit codes: a versioned binary served with `no-cache` costs every installer a full origin fetch, and nothing says so. Driven red, then the source is confirmed byte-identical and green again."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"',
        'CACHE_CONTROL_IMMUTABLE = "no-cache"',
        1,
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    old_root = fixture(tmp_path / "old")
    bad_root = fixture(tmp_path / "bad")
    (bad_root / ".ci" / "rediacc_ci" / "deploy" / PORT.name).write_text(mutated, encoding="utf-8")

    old, old_calls = _run(old_root, "old")
    bad, bad_calls = _run(bad_root, "new")
    assert bad.returncode == old.returncode == 0, "the plant is invisible in the exit code"
    assert bad.stdout == old.stdout, "the plant is invisible on stdout"
    assert bad_calls.replace(str(bad_root), "<root>") != old_calls.replace(
        str(old_root), "<root>"
    ), "the mutant's calls matched the twin's"
    assert IMMUTABLE not in bad_calls

    good_root = fixture(tmp_path / "good")
    _good, good_calls = _run(good_root, "new")
    # The three fixtures live under three roots, and the source path of every upload names its own. That one field is masked and nothing else is.
    assert good_calls.replace(str(good_root), "<root>") == old_calls.replace(
        str(old_root), "<root>"
    ), "the restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


def test_the_harness_sees_a_non_trivial_tree(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY FOR THE HARNESS ITSELF. Every comparison above would pass trivially against a `dist/` that does not exist, so the default tree's shape is asserted once: five files, two of them binaries the glob must find."""
    root = fixture(tmp_path)
    assert len(DEFAULT_TREE) == 5
    assert sorted(p.name for p in (root / "dist" / "cli").iterdir()) == [
        "manifest.json",
        "rdc-darwin-arm64",
        "rdc-linux-x64",
    ]
    _old, calls = _run(root, "old")
    assert calls.count("aws\t") >= 9, "the twin made almost no calls; the fixture is not loaded"
