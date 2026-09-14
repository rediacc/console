"""Differential: `rediacc_ci.deploy.sync_media_from_r2` against its twin
`.ci/scripts/deploy/sync-media-from-r2.sh`.

A RECORDING FAKE `aws` ON A SCRATCH PATH. Nothing here reaches Cloudflare R2:
the fake logs its exact argv, answers from the environment, and the only real
credential name in the file is an environment KEY, never a value.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

THE CALL LOG IS COMPARED AS WELL AS THE TWO STREAMS, and for this script it is
the more important half. Everything the program prints is three `Restoring ...`
lines plus one closing line, none of it derived from what actually moved; the
whole observable effect is which prefixes were synced, into which directories,
with which flags. A port that dropped `--no-progress`, reordered the three legs
or pointed one at the wrong prefix would print identical output and exit 0.
`test_planted_defect_is_caught` plants exactly that.

EVERY RUN HAPPENS IN A COPIED TREE UNDER `tmp_path`, NEVER IN THE CHECKOUT, and
that is a correctness requirement rather than tidiness. Both implementations
derive `REPO_ROOT` from their OWN location (`<file>/../../..`), and the script's
one on-disk side effect is `mkdir -p` under `packages/www/public/assets/`. Run
from the real checkout it would create directories in a tree several other
sessions are working in, and the skip/no-skip behaviour of the upload twin could
not be exercised at all. Copying the eight files each side needs into `tmp_path`
makes `REPO_ROOT` the fixture, gives every test its own filesystem state, and
removes any need for a machine-wide lock: `tmp_path` is unique per test, so two
concurrent runs of this file in one checkout cannot collide.

BOTH SIDES ARE RE-RUN FROM THE SAME STARTING STATE. `restore_dir` creates
directories, so the second side would otherwise see a tree the first side built.
`run_both` rebuilds `packages/` before each side.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import sync_media_from_r2 as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/deploy/sync-media-from-r2.sh"
PORT_REL = ".ci/rediacc_ci/deploy/sync_media_from_r2.py"
BASH = shutil.which("bash") or "/bin/bash"

# The eight files a fixture tree needs: the twin, the bash library it sources,
# and the Python package the port imports. Listed explicitly rather than
# copytree'd, so a new dependency shows up here as an edit instead of being
# dragged in silently by a wildcard.
TREE_FILES = (
    TWIN_REL,
    ".ci/scripts/lib/common.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/deploy/__init__.py",
    PORT_REL,
)

# NAMED `SIGNING_KEY` RATHER THAN `SECRET_KEY`, and the reason is the linter
# rather than taste: ruff S105 keys on the NAME, so a constant spelled with
# "secret" in it is "a hardcoded password" even when its value is visibly a
# fixture. The gate's own message forbids buying past it with a per-line noqa,
# and `deploy/purge_media_cache`'s differential made the same rename for the
# same reason. Both values reach nothing but a Python script on a scratch PATH.
ACCESS_KEY = "fixture-access-key"
SIGNING_KEY = "fixture-signing-key"
ENDPOINT = "https://r2.example.invalid"

# The three legs, as the RELATIVE local paths the twin builds from REPO_ROOT.
LEG_DIRS = (
    "packages/www/public/assets/tutorials/video",
    "packages/www/public/assets/videos",
    "packages/www/public/assets/tutorials/audio",
)

FAKE_AWS = """#!/usr/bin/python3
import os
import shlex
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("aws\\t" + "\\t".join(argv) + "\\n")

# THE LEDGER LINE. shadow-gate.ts classifies every line starting with an arrow
# or a tick as CHATTER before any --finding-re is consulted, and this script
# reports through nothing else, so a message-text regex can never produce a
# finding and every ledger row would read VACUOUS_BOTH_EMPTY. Echoing argv under
# a distinct prefix makes the compared finding set the literal set of external
# calls. shlex.quote, not a plain space join: --cache-control carries one
# argument containing a space and a space-joined line cannot tell that from two.
sys.stdout.write("call: aws " + " ".join(shlex.quote(a) for a in argv) + "\\n")
sys.exit(int(os.environ.get("FAKE_AWS_RC") or 0))
"""

# `common.sh` needs `dirname` at source time and `uname`/`tr` in the detection
# helpers it runs there; `mkdir` is called by the SUBJECT on both sides and is
# deliberately the real binary, so a failing `mkdir` produces the same bytes
# through both implementations.
PATH_MINIMUM = ("dirname", "uname", "tr", "mkdir")


def _bin(tree: pathlib.Path, *, drop: str = "") -> str:
    stub = tree / "stub-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if drop != "aws":
        aws = stub / "aws"
        aws.write_text(FAKE_AWS, encoding="utf-8")
        aws.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature checkout whose root is `tmp_path/tree`.

    Both implementations resolve `REPO_ROOT` three directories up from
    themselves, so placing them at `.ci/scripts/deploy/` and
    `.ci/rediacc_ci/deploy/` inside this directory makes `tmp_path/tree` the
    repository root for both, with no environment variable involved and no
    difference from how they resolve it in the real checkout.
    """
    tree = tmp_path / "tree"
    if tree.exists():
        return tree
    for rel in TREE_FILES:
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    return tree


def _layout(tree: pathlib.Path, dirs: tuple[str, ...]) -> None:
    """Rebuild `packages/` from scratch, so each side starts identically."""
    shutil.rmtree(tree / "packages", ignore_errors=True)
    for rel in dirs:
        (tree / rel).mkdir(parents=True, exist_ok=True)


def _created(tree: pathlib.Path) -> list[str]:
    """Every directory under `packages/`, relative and sorted."""
    base = tree / "packages"
    if not base.is_dir():
        return []
    out = []
    for dirpath, _dirnames, _filenames in os.walk(base):
        out.append(os.path.relpath(dirpath, tree))
    return sorted(out)


def _run(
    subject: str,
    tree: pathlib.Path,
    args: list[str],
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.endswith(".sh") else "new"
    call_log = tree / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tree, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(tree / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID": ACCESS_KEY,
        "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY": SIGNING_KEY,
        "CLOUDFLARE_R2_MEDIA_ENDPOINT": ENDPOINT,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if subject.endswith(".sh") else [sys.executable]
    proc = subprocess.run(
        [*runner, subject, *args],
        cwd=tree,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], *, dirs: tuple[str, ...] = (), **kw):
    tree = _tree(tmp_path)
    _layout(tree, dirs)
    old, old_calls = _run(TWIN_REL, tree, args, **kw)
    old_dirs = _created(tree)
    _layout(tree, dirs)
    new, new_calls = _run(PORT_REL, tree, args, **kw)
    new_dirs = _created(tree)
    assert new_dirs == old_dirs, (
        f"the two sides left different directories behind:\nold: {old_dirs}\nnew: {new_dirs}"
    )
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
            f"{label}: call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def _call(tree: pathlib.Path, remote_prefix: str, local_relative: str, *flags: str) -> str:
    local = os.path.join(str(tree), local_relative)
    argv = port.download_argv(
        remote_prefix, local, ["--endpoint-url", ENDPOINT, "--no-progress", *flags]
    )
    return "aws\t" + "\t".join(argv[1:])


def test_the_default_run_restores_three_prefixes_in_order(tmp_path: pathlib.Path) -> None:
    """THE WHOLE CONTRACT, PINNED AGAINST LITERAL BYTES rather than against the
    port's own helpers, so a change in both would still be caught. Three calls,
    in the twin's order, each with the endpoint and `--no-progress` and nothing
    else."""
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    tree = _tree(tmp_path)
    assert old.returncode == 0
    assert old_calls == [
        (
            "aws\ts3\tsync\ts3://rediacc-www-media/tutorials/video/\t"
            f"{tree}/packages/www/public/assets/tutorials/video/\t"
            f"--endpoint-url\t{ENDPOINT}\t--no-progress"
        ),
        (
            "aws\ts3\tsync\ts3://rediacc-www-media/videos/\t"
            f"{tree}/packages/www/public/assets/videos/\t"
            f"--endpoint-url\t{ENDPOINT}\t--no-progress"
        ),
        (
            "aws\ts3\tsync\ts3://rediacc-www-media/tutorials/audio/\t"
            f"{tree}/packages/www/public/assets/tutorials/audio/\t"
            f"--endpoint-url\t{ENDPOINT}\t--no-progress"
        ),
    ]
    assert old.stderr == (
        f"→ Restoring s3://rediacc-www-media/tutorials/video/ -> {tree}/packages/www/public/assets/tutorials/video/\n"
        f"→ Restoring s3://rediacc-www-media/videos/ -> {tree}/packages/www/public/assets/videos/\n"
        f"→ Restoring s3://rediacc-www-media/tutorials/audio/ -> {tree}/packages/www/public/assets/tutorials/audio/\n"
        "✓ Restore complete.\n"
    )
    assert "call: aws s3 sync s3://rediacc-www-media/videos/" in old.stdout
    _assert_agree(old, new, "default", old_calls, new_calls)


def test_dry_run_appends_dryrun_last_and_drops_the_closing_line(tmp_path: pathlib.Path) -> None:
    """`--dryrun` is APPENDED to `SYNC_ARGS`, so it TRAILS `--no-progress`. aws
    does not care about the position and the recorded argv does, which is the
    whole reason the flag order is asserted rather than the flag set."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--dry-run"])
    tree = _tree(tmp_path)
    assert old.returncode == 0
    assert old.stderr.startswith("✓ Dry run: nothing will be downloaded.\n")
    assert "Restore complete" not in old.stderr
    assert len(old_calls) == 3
    assert all(c.endswith("--no-progress\t--dryrun") for c in old_calls)
    assert old_calls[0] == _call(
        tree, "tutorials/video/", "packages/www/public/assets/tutorials/video/", "--dryrun"
    )
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_tutorials_only_restores_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tutorials-only"])
    assert old.returncode == 0
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/tutorials/video/" in old_calls[0]
    _assert_agree(old, new, "tutorials-only", old_calls, new_calls)


def test_solutions_only_restores_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--solutions-only"])
    assert old.returncode == 0
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/videos/" in old_calls[0]
    _assert_agree(old, new, "solutions-only", old_calls, new_calls)


def test_audio_only_restores_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--audio-only"])
    assert old.returncode == 0
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/tutorials/audio/" in old_calls[0]
    _assert_agree(old, new, "audio-only", old_calls, new_calls)


def test_the_only_flags_are_not_additive_and_the_last_one_wins(tmp_path: pathlib.Path) -> None:
    """Each `--*-only` arm assigns ALL THREE booleans, so the flags overwrite
    rather than accumulate. A port that OR-ed them would restore two prefixes
    where the twin restores one, and would still print a plausible log."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tutorials-only", "--audio-only"])
    assert old.returncode == 0
    assert len(old_calls) == 1, "the two flags accumulated instead of overwriting"
    assert "s3://rediacc-www-media/tutorials/audio/" in old_calls[0]
    _assert_agree(old, new, "last-only-wins", old_calls, new_calls)


def test_an_unknown_argument_is_refused_before_any_credential_check(
    tmp_path: pathlib.Path,
) -> None:
    """The parse loop runs FIRST, so a typo is reported on a machine with no
    credentials and no `aws` at all. Driven with the access key removed as well,
    which would otherwise be the refusal."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--bogus"],
        drop="aws",
        drop_env=("CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID",),
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Unknown argument: --bogus\n"
    assert old_calls == []
    _assert_agree(old, new, "unknown-arg", old_calls, new_calls)


def test_an_empty_argument_is_refused_with_a_trailing_space(tmp_path: pathlib.Path) -> None:
    """`log_error "Unknown argument: $1"` with an empty `$1` renders a trailing
    space, and a port that stripped it would disagree on bytes for an input a
    caller reaches by writing `"$FLAG"` around an unset variable."""
    old, new, old_calls, new_calls = run_both(tmp_path, [""])
    assert old.returncode == 1
    assert old.stderr == "✗ Unknown argument: \n"
    _assert_agree(old, new, "empty-arg", old_calls, new_calls)


def test_an_empty_access_key_is_refused(tmp_path: pathlib.Path) -> None:
    """`require_var` tests EMPTINESS through indirect expansion, so exported-empty
    and unset are one outcome for the one variable it actually checks."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--audio-only"], CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=""
    )
    assert old.returncode == 1
    assert old.stderr == (
        "✗ Required environment variable 'CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID' is not set\n"
    )
    assert old_calls == []
    _assert_agree(old, new, "empty-access-key", old_calls, new_calls)


def test_an_unset_access_key_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID",)
    )
    assert old.returncode == 1
    assert old.stderr.startswith("✗ Required environment variable")
    _assert_agree(old, new, "unset-access-key", old_calls, new_calls)


def test_missing_aws_is_refused_after_the_access_key_and_before_the_secret(
    tmp_path: pathlib.Path,
) -> None:
    """THE ORDER OF THE REFUSALS IS THE CONTRACT. Driven with the secret ALSO
    unset, so the only thing that decides which message appears is the order:
    `require_cmd aws` sits above the `export`, and a port that validated
    credentials first would report the wrong problem on a fresh machine."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--audio-only"],
        drop="aws",
        drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",),
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n"
    assert old_calls == []
    _assert_agree(old, new, "missing-aws", old_calls, new_calls)


def test_defect_require_var_checks_only_its_first_argument(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED. The twin passes THREE names to `require_var` and
    `common.sh:131-137` reads `local var_name="$1"`, so two documented-as-required
    credentials are never checked. `set -u` catches them only when UNSET, so an
    EXPORTED-EMPTY secret and an EXPORTED-EMPTY endpoint sail straight through:
    `aws` is handed `--endpoint-url` followed by the empty string, the run prints
    `Restore complete.` and exits 0.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--audio-only"],
        CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY="",
        CLOUDFLARE_R2_MEDIA_ENDPOINT="",
    )
    assert old.returncode == 0, "the twin started validating the other two names"
    assert old.stderr.endswith("✓ Restore complete.\n")
    assert len(old_calls) == 1
    assert old_calls[0].endswith("--endpoint-url\t\t--no-progress"), (
        "the empty endpoint is no longer passed through verbatim"
    )
    assert port.REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT
    assert port.AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT
    _assert_agree(old, new, "empty-credentials", old_calls, new_calls)


def test_divergence_set_u_names_the_bash_file_and_line(tmp_path: pathlib.Path) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. An UNSET secret is caught by `set -u`, not by the
    script, so bash's own message names the bash FILE and a bash LINE NUMBER.
    The port carries the `NAME: unbound variable` half, on the same stream, with
    the same exit status. Same ruling as `deploy/promote_r2_to_stable.py` makes
    for its `${VAR:?msg}` guards."""
    tree = _tree(tmp_path)
    _layout(tree, ())
    old, old_calls = _run(
        TWIN_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",)
    )
    _layout(tree, ())
    new, new_calls = _run(
        PORT_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",)
    )
    assert old.returncode == new.returncode == 1
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == []
    assert old.stderr.endswith("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n")
    assert new.stderr == "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n"
    assert "sync-media-from-r2.sh: line " in old.stderr, "bash stopped naming the file and line"
    assert "line " not in new.stderr, "the port started inventing a bash line number"


def test_an_unset_endpoint_is_reported_after_the_secret(tmp_path: pathlib.Path) -> None:
    """The secret is expanded three lines above the endpoint, so with BOTH unset
    the secret is the one named. Driven with only the endpoint unset to show the
    second half of the same ordering."""
    tree = _tree(tmp_path)
    _layout(tree, ())
    old, _oc = _run(TWIN_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_ENDPOINT",))
    _layout(tree, ())
    new, _nc = _run(PORT_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_ENDPOINT",))
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith("CLOUDFLARE_R2_MEDIA_ENDPOINT: unbound variable\n")
    assert new.stderr == "CLOUDFLARE_R2_MEDIA_ENDPOINT: unbound variable\n"

    _layout(tree, ())
    both_old, _ = _run(
        TWIN_REL,
        tree,
        ["--audio-only"],
        drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_MEDIA_ENDPOINT"),
    )
    _layout(tree, ())
    both_new, _ = _run(
        PORT_REL,
        tree,
        ["--audio-only"],
        drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_MEDIA_ENDPOINT"),
    )
    assert both_old.stderr.endswith("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n")
    assert both_new.stderr == "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n"


def test_a_failing_aws_ends_the_run_with_its_status_and_no_further_legs(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` on the unguarded `aws s3 sync`: the first failure is the last
    call, the closing line never prints, and the script's status is aws's."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_AWS_RC="3")
    assert old.returncode == 3
    assert len(old_calls) == 1, "the run continued past a failed leg"
    assert "Restore complete" not in old.stderr
    _assert_agree(old, new, "aws-fails", old_calls, new_calls)


def test_defect_dry_run_still_creates_the_local_directories(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED. `mkdir -p "$local_dir"` sits above the `aws` call in
    `restore_dir` and is not conditioned on `DRY_RUN`, so the flag documented as
    "download nothing" writes three directories into the working copy. Harmless
    in a git sense and still a write from a read-only flag.

    `run_both` already asserts the two sides leave the SAME directories behind;
    this names what those directories are, so the shared assertion cannot pass
    by both sides creating nothing.
    """
    tree = _tree(tmp_path)
    _layout(tree, ())
    assert _created(tree) == [], "the fixture started dirty"
    old, old_calls = _run(TWIN_REL, tree, ["--dry-run"])
    old_dirs = _created(tree)
    _layout(tree, ())
    new, new_calls = _run(PORT_REL, tree, ["--dry-run"])
    new_dirs = _created(tree)

    assert old.returncode == new.returncode == 0
    for leg in LEG_DIRS:
        assert leg in old_dirs, f"--dry-run stopped creating {leg}"
    assert new_dirs == old_dirs
    assert port.DRY_RUN_STILL_CREATES_THE_LOCAL_DIRECTORIES
    _assert_agree(old, new, "dry-run-creates-dirs", old_calls, new_calls)


def test_a_failing_mkdir_stops_before_the_step_line(tmp_path: pathlib.Path) -> None:
    """`mkdir` IS THE REAL BINARY ON BOTH SIDES, which is why its bytes agree.
    A regular file where `tutorials/video/` belongs makes `mkdir -p` fail, and
    because it runs ABOVE `log_step` the caller learns the run died without ever
    learning which prefix it died on. `os.makedirs` would print a traceback and
    a different status here."""
    tree = _tree(tmp_path)
    _layout(tree, ())
    (tree / "packages/www/public/assets/tutorials").mkdir(parents=True, exist_ok=True)
    (tree / "packages/www/public/assets/tutorials/video").write_text("", encoding="utf-8")
    old, old_calls = _run(TWIN_REL, tree, ["--tutorials-only"])
    new, new_calls = _run(PORT_REL, tree, ["--tutorials-only"])
    assert old.returncode != 0
    assert old.stderr.startswith("mkdir:"), f"mkdir no longer explains itself: {old.stderr!r}"
    assert "Restoring" not in old.stderr, "the step line printed despite the mkdir failure"
    assert old_calls == [], "aws ran on a directory that could not be created"
    _assert_agree(old, new, "mkdir-fails", old_calls, new_calls)


def test_pure_helpers() -> None:
    """The exported helpers, driven directly. Both directions on the parse loop:
    something that must be refused, and flag combinations that must NOT be."""
    assert port.BUCKET == "rediacc-www-media"
    assert port.TUTORIALS == ("tutorials/video/", "packages/www/public/assets/tutorials/video/")
    assert port.SOLUTIONS == ("videos/", "packages/www/public/assets/videos/")
    assert port.AUDIO == ("tutorials/audio/", "packages/www/public/assets/tutorials/audio/")

    default = port.parse_args([])
    assert (default.tutorials, default.solutions, default.audio, default.dry_run) == (
        True,
        True,
        True,
        False,
    )
    assert default.selected() == [port.TUTORIALS, port.SOLUTIONS, port.AUDIO]
    assert port.parse_args(["--audio-only"]).selected() == [port.AUDIO]
    assert port.parse_args(["--audio-only", "--tutorials-only"]).selected() == [port.TUTORIALS]
    assert port.parse_args(["--dry-run"]).selected() == [port.TUTORIALS, port.SOLUTIONS, port.AUDIO]
    assert port.parse_args(["--dry-run", "--dry-run"]).dry_run is True

    for bad in ["--delete", "-n", "tutorials", "", "--dry_run"]:
        with pytest.raises(port.UnknownArgumentError) as caught:
            port.parse_args([bad])
        assert caught.value.argument == bad
        assert str(caught.value) == "Unknown argument: %s" % bad

    assert port.sync_args("EP", dry_run=False) == ["--endpoint-url", "EP", "--no-progress"]
    assert port.sync_args("EP", dry_run=True) == [
        "--endpoint-url",
        "EP",
        "--no-progress",
        "--dryrun",
    ]
    assert port.download_argv("videos/", "/x/y/", ["--no-progress"]) == [
        "aws",
        "s3",
        "sync",
        "s3://rediacc-www-media/videos/",
        "/x/y/",
        "--no-progress",
    ]

    assert port.require_secret_key({port.SIGNING_KEY_ENV: ""}) == ""
    with pytest.raises(port.UnboundVariableError) as caught:
        port.require_secret_key({port.SIGNING_KEY_ENV: None})
    assert str(caught.value) == "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable"

    # `--audio-only` selects the audio leg and NOT the other two: the negative
    # half of the control, without which a helper that returned all three legs
    # for every input would still pass everything above.
    assert port.SOLUTIONS not in port.parse_args(["--audio-only"]).selected()
    assert port.TUTORIALS not in port.parse_args(["--audio-only"]).selected()


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on `--no-progress` -- a flag whose absence changes
    NOTHING a reader can see through this harness (the fake aws prints the same
    line either way, the exit code is 0 either way, and the call COUNT is
    unchanged) while changing what the real `aws` writes to the terminal on
    every one of the three legs. Driven red, then the source is confirmed
    byte-identical and green.
    """
    original = (ROOT / PORT_REL).read_text(encoding="utf-8")
    mutated = original.replace(
        'args = ["--endpoint-url", endpoint, "--no-progress"]',
        'args = ["--endpoint-url", endpoint]',
        1,
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    tree = _tree(tmp_path)
    mutant = ".ci/rediacc_ci/deploy/mutant.py"
    (tree / mutant).write_text(mutated, encoding="utf-8")

    _layout(tree, ())
    old, old_calls = _run(TWIN_REL, tree, [])
    _layout(tree, ())
    bad, bad_calls = _run(mutant, tree, [])
    assert bad.returncode == old.returncode == 0, "the plant is invisible in the exit code"
    assert bad.stderr == old.stderr, "the plant is invisible on stderr"
    assert len(bad_calls) == len(old_calls) == 3, "the plant even keeps the call COUNT"
    assert bad_calls != old_calls, "the mutant still passed --no-progress"
    assert all("--no-progress" not in c for c in bad_calls)

    _layout(tree, ())
    good, good_calls = _run(PORT_REL, tree, [])
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
