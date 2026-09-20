"""Differential: `rediacc_ci.deploy.sync_media_to_r2` against its twin `.ci/scripts/deploy/sync-media-to-r2.sh`.

A RECORDING FAKE `aws` ON A SCRATCH PATH. Nothing here reaches Cloudflare R2: the fake logs its exact argv, answers from the environment, and the only real credential name in the file is an environment KEY, never a value. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

THE CALL LOG IS COMPARED AS WELL AS THE TWO STREAMS, and for an UPLOAD script it is the half that matters. What gets printed is three `Syncing ...` lines and a three-line closing recipe, none of it derived from what moved; the entire observable effect is which local directory went to which prefix, with which headers. A port that dropped `--cache-control` would print identical
output and exit 0 while publishing objects that expire in an hour instead of a year, and a port that appended `--delete` in the wrong position would look identical too. `test_planted_defect_is_caught` plants the first of those.

`--cache-control` IS ONE ARGV ELEMENT CONTAINING A SPACE, so the fake records argv tab-separated and echoes it `shlex.quote`d. A space-joined log cannot tell
`--cache-control 'public, max-age=31536000'` from `--cache-control public,`
followed by a stray `max-age=31536000`, and those are different calls.

EVERY RUN HAPPENS IN A COPIED TREE UNDER `tmp_path`, NEVER IN THE CHECKOUT. Both implementations derive `REPO_ROOT` from their OWN location (`<file>/../../..`), and the behaviour under test is precisely what happens when `packages/www/public/assets/...` is present, absent, or a file. None of those three states can be arranged in a shared checkout other sessions are working in.
Copying the eight files each side needs into `tmp_path` makes `REPO_ROOT` the fixture and removes any need for a machine-wide lock: `tmp_path` is unique per test, so two concurrent runs of this file in one checkout cannot collide.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import sync_media_to_r2 as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/deploy/sync-media-to-r2.sh"
PORT_REL = ".ci/rediacc_ci/deploy/sync_media_to_r2.py"
BASH = shutil.which("bash") or "/bin/bash"

# The eight files a fixture tree needs: the twin, the bash library it sources, and the Python package the port imports. Listed explicitly rather than copytree'd, so a new dependency shows up here as an edit instead of being dragged in silently by a wildcard.
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

# NAMED `SIGNING_KEY` RATHER THAN `SECRET_KEY`, and the reason is the linter rather than taste: ruff S105 keys on the NAME, so a constant spelled with "secret" in it is "a hardcoded password" even when its value is visibly a
# fixture. The gate's own message forbids buying past it with a per-line noqa,
# and `deploy/purge_media_cache`'s differential made the same rename for the same reason. Both values reach nothing but a Python script on a scratch PATH.
ACCESS_KEY = "fixture-access-key"
SIGNING_KEY = "fixture-signing-key"
ENDPOINT = "https://r2.example.invalid"

# The three legs, as the RELATIVE local paths the twin builds from REPO_ROOT.
TUTORIALS_DIR = "packages/www/public/assets/tutorials/video"
SOLUTIONS_DIR = "packages/www/public/assets/videos"
AUDIO_DIR = "packages/www/public/assets/tutorials/audio"
ALL_DIRS = (TUTORIALS_DIR, SOLUTIONS_DIR, AUDIO_DIR)

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

# `common.sh` needs `dirname` at source time and `uname`/`tr` in the detection helpers it runs there. Unlike the download twin this script never calls `mkdir`, and the harness does not put one on the PATH: if a port ever started creating the directory it skips, it would fail loudly here.
PATH_MINIMUM = ("dirname", "uname", "tr")


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

    Both implementations resolve `REPO_ROOT` three directories up from themselves, so placing them at `.ci/scripts/deploy/` and `.ci/rediacc_ci/deploy/` inside this directory makes `tmp_path/tree` the repository root for both, with no environment variable involved and no difference from how they resolve it in the real checkout.
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


def run_both(tmp_path: pathlib.Path, args: list[str], *, dirs: tuple[str, ...] = ALL_DIRS, **kw):
    tree = _tree(tmp_path)
    _layout(tree, dirs)
    old, old_calls = _run(TWIN_REL, tree, args, **kw)
    _layout(tree, dirs)
    new, new_calls = _run(PORT_REL, tree, args, **kw)
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


CLOSING = (
    "✓ Sync complete. Verify with:\n"
    "✓   aws s3 sync --dryrun <local-dir> s3://rediacc-www-media/<prefix>/ "
    "--endpoint-url $CLOUDFLARE_R2_MEDIA_ENDPOINT\n"
    "✓   curl -sI https://media.rediacc.com/<path>\n"
)


def test_the_default_run_uploads_three_prefixes_in_order(tmp_path: pathlib.Path) -> None:
    """THE WHOLE CONTRACT, PINNED AGAINST LITERAL BYTES rather than against the port's own helpers, so a change in both would still be caught. Three calls, in the twin's order, each carrying the endpoint, the one-year `Cache-Control` as a SINGLE argument, and `--no-progress`."""
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    tree = _tree(tmp_path)
    assert old.returncode == 0
    assert old_calls == [
        (
            f"aws\ts3\tsync\t{tree}/packages/www/public/assets/tutorials/video/\t"
            "s3://rediacc-www-media/tutorials/video/\t"
            f"--endpoint-url\t{ENDPOINT}\t"
            "--cache-control\tpublic, max-age=31536000\t--no-progress"
        ),
        (
            f"aws\ts3\tsync\t{tree}/packages/www/public/assets/videos/\t"
            "s3://rediacc-www-media/videos/\t"
            f"--endpoint-url\t{ENDPOINT}\t"
            "--cache-control\tpublic, max-age=31536000\t--no-progress"
        ),
        (
            f"aws\ts3\tsync\t{tree}/packages/www/public/assets/tutorials/audio/\t"
            "s3://rediacc-www-media/tutorials/audio/\t"
            f"--endpoint-url\t{ENDPOINT}\t"
            "--cache-control\tpublic, max-age=31536000\t--no-progress"
        ),
    ]
    assert old.stderr == (
        f"→ Syncing {tree}/packages/www/public/assets/tutorials/video/ -> s3://rediacc-www-media/tutorials/video/\n"
        f"→ Syncing {tree}/packages/www/public/assets/videos/ -> s3://rediacc-www-media/videos/\n"
        f"→ Syncing {tree}/packages/www/public/assets/tutorials/audio/ -> s3://rediacc-www-media/tutorials/audio/\n"
        + CLOSING
    )
    _assert_agree(old, new, "default", old_calls, new_calls)


def test_the_closing_recipe_does_not_interpolate_the_endpoint(tmp_path: pathlib.Path) -> None:
    """`\\$CLOUDFLARE_R2_MEDIA_ENDPOINT` is an ESCAPED dollar inside the twin's double quotes, so the closing line hands the reader a variable to paste, not the endpoint this run used. A port that interpolated it would leak the endpoint into a log that is routinely shared."""
    old, new, _oc, _nc = run_both(tmp_path, ["--tutorials-only"])
    assert "--endpoint-url $CLOUDFLARE_R2_MEDIA_ENDPOINT" in old.stderr
    assert ENDPOINT not in old.stderr.split("Sync complete")[1]
    assert old.stderr == new.stderr


def test_dry_run_appends_dryrun_and_drops_the_closing_recipe(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--dry-run"])
    assert old.returncode == 0
    assert old.stderr.startswith("✓ Dry run: no objects will be uploaded or deleted.\n")
    assert "Sync complete" not in old.stderr
    assert all(c.endswith("--no-progress\t--dryrun") for c in old_calls)
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_delete_warns_and_appends_delete_last(tmp_path: pathlib.Path) -> None:
    """The warning is a `⚠` line, not a prompt: `--delete` removes remote objects
    with no local counterpart and asks nothing. The flag is APPENDED, so it
    trails `--no-progress`."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--delete"])
    assert old.returncode == 0
    assert old.stderr.startswith(
        "⚠ Delete mode: remote objects with no local counterpart will be removed.\n"
    )
    assert all(c.endswith("--no-progress\t--delete") for c in old_calls)
    _assert_agree(old, new, "delete", old_calls, new_calls)


def test_dry_run_and_delete_keep_their_order_in_both_the_log_and_the_argv(
    tmp_path: pathlib.Path,
) -> None:
    """TWO ORDERINGS AT ONCE, and neither is arbitrary. On stderr the dry-run line precedes the delete warning because the twin's two `if` blocks are in that order; in the argv `--dryrun` precedes `--delete` for the same reason. A port that emitted either pair the other way round would be reporting a different program."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--delete", "--dry-run"])
    assert old.returncode == 0
    assert old.stderr.startswith(
        "✓ Dry run: no objects will be uploaded or deleted.\n"
        "⚠ Delete mode: remote objects with no local counterpart will be removed.\n"
    )
    assert all(c.endswith("--no-progress\t--dryrun\t--delete") for c in old_calls)
    _assert_agree(old, new, "dry-run+delete", old_calls, new_calls)


def test_tutorials_only_uploads_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tutorials-only"])
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/tutorials/video/" in old_calls[0]
    _assert_agree(old, new, "tutorials-only", old_calls, new_calls)


def test_solutions_only_uploads_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--solutions-only"])
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/videos/" in old_calls[0]
    _assert_agree(old, new, "solutions-only", old_calls, new_calls)


def test_audio_only_uploads_one_prefix(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--audio-only"])
    assert len(old_calls) == 1
    assert "s3://rediacc-www-media/tutorials/audio/" in old_calls[0]
    _assert_agree(old, new, "audio-only", old_calls, new_calls)


def test_the_only_flags_are_not_additive_and_the_last_one_wins(tmp_path: pathlib.Path) -> None:
    """Each `--*-only` arm assigns ALL THREE booleans, so the flags overwrite rather than accumulate. A port that OR-ed them would upload two prefixes where the twin uploads one, and would still print a plausible log."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--audio-only", "--solutions-only"])
    assert len(old_calls) == 1, "the two flags accumulated instead of overwriting"
    assert "s3://rediacc-www-media/videos/" in old_calls[0]
    _assert_agree(old, new, "last-only-wins", old_calls, new_calls)


def test_an_unknown_argument_is_refused_before_any_credential_check(
    tmp_path: pathlib.Path,
) -> None:
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
    old, new, old_calls, new_calls = run_both(tmp_path, [""])
    assert old.returncode == 1
    assert old.stderr == "✗ Unknown argument: \n"
    _assert_agree(old, new, "empty-arg", old_calls, new_calls)


def test_an_empty_access_key_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--audio-only"], CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=""
    )
    assert old.returncode == 1
    assert old.stderr == (
        "✗ Required environment variable 'CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID' is not set\n"
    )
    assert old_calls == []
    _assert_agree(old, new, "empty-access-key", old_calls, new_calls)


def test_missing_aws_is_refused_after_the_access_key_and_before_the_secret(
    tmp_path: pathlib.Path,
) -> None:
    """THE ORDER OF THE REFUSALS IS THE CONTRACT. Driven with the secret ALSO unset, so the only thing that decides which message appears is the order: `require_cmd aws` sits above the `export`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--audio-only"],
        drop="aws",
        drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",),
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n"
    _assert_agree(old, new, "missing-aws", old_calls, new_calls)


def test_defect_require_var_checks_only_its_first_argument(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED, and it is the shape of the 2026-08-28 incident this repository's pre-bash hook still warns about. The twin passes THREE names to
    `require_var` and `common.sh:131-137` reads `local var_name="$1"`, so two
    documented-as-required credentials are never checked. `set -u` catches them only when UNSET, so an EXPORTED-EMPTY secret and an EXPORTED-EMPTY endpoint sail through: `aws` is handed `--endpoint-url` followed by the empty string, the closing recipe prints, and the run exits 0.

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
    assert old.stderr.endswith(CLOSING)
    assert len(old_calls) == 1
    assert "\t--endpoint-url\t\t--cache-control\t" in old_calls[0], (
        "the empty endpoint is no longer passed through verbatim"
    )
    assert port.REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT
    assert port.AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT
    _assert_agree(old, new, "empty-credentials", old_calls, new_calls)


def test_divergence_set_u_names_the_bash_file_and_line(tmp_path: pathlib.Path) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. An UNSET secret is caught by `set -u`, not by the script, so bash's own message names the bash FILE and a bash LINE NUMBER. The port carries the `NAME: unbound variable` half, on the same stream, with the same exit status. Same ruling as `deploy/promote_r2_to_stable.py` makes
    for its `${VAR:?msg}` guards."""
    tree = _tree(tmp_path)
    _layout(tree, ALL_DIRS)
    old, old_calls = _run(
        TWIN_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",)
    )
    _layout(tree, ALL_DIRS)
    new, new_calls = _run(
        PORT_REL, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY",)
    )
    assert old.returncode == new.returncode == 1
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == []
    assert old.stderr.endswith("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n")
    assert new.stderr == "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n"
    assert "sync-media-to-r2.sh: line " in old.stderr, "bash stopped naming the file and line"
    assert "line " not in new.stderr, "the port started inventing a bash line number"


def test_an_unset_endpoint_is_reported_after_the_secret(tmp_path: pathlib.Path) -> None:
    """The secret is expanded three lines above the endpoint, so with BOTH unset the secret is the one named."""
    tree = _tree(tmp_path)
    for subject, expect_prefix in ((TWIN_REL, True), (PORT_REL, False)):
        _layout(tree, ALL_DIRS)
        proc, _calls = _run(
            subject, tree, ["--audio-only"], drop_env=("CLOUDFLARE_R2_MEDIA_ENDPOINT",)
        )
        assert proc.returncode == 1
        assert proc.stderr.endswith("CLOUDFLARE_R2_MEDIA_ENDPOINT: unbound variable\n")
        assert ("sync-media-to-r2.sh: line " in proc.stderr) is expect_prefix

        _layout(tree, ALL_DIRS)
        both, _calls = _run(
            subject,
            tree,
            ["--audio-only"],
            drop_env=("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_MEDIA_ENDPOINT"),
        )
        assert both.stderr.endswith("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable\n")


def test_a_failing_aws_ends_the_run_with_its_status_and_no_further_legs(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` on the unguarded `aws s3 sync`: the first failure is the last call, the closing recipe never prints, and the script's status is aws's."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_AWS_RC="4")
    assert old.returncode == 4
    assert len(old_calls) == 1, "the run continued past a failed leg"
    assert "Sync complete" not in old.stderr
    _assert_agree(old, new, "aws-fails", old_calls, new_calls)


def test_a_missing_directory_is_a_warning_and_the_other_legs_still_run(
    tmp_path: pathlib.Path,
) -> None:
    """`sync_dir` answers a missing local directory with `return 0`, so one absent prefix does not stop the other two. The warning names the LOCAL path, which is the only place the reader learns which leg was skipped."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], dirs=(TUTORIALS_DIR, AUDIO_DIR))
    tree = _tree(tmp_path)
    assert old.returncode == 0
    assert len(old_calls) == 2
    assert f"⚠ Skipping {tree}/{SOLUTIONS_DIR}/ (not present locally)\n" in old.stderr
    assert all("s3://rediacc-www-media/videos/" not in c for c in old_calls)
    _assert_agree(old, new, "one-missing-leg", old_calls, new_calls)


def test_defect_a_run_that_uploads_nothing_still_says_complete(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED, AND IT IS THE VACUITY CLASS IN A SCRIPT WHOSE ONLY JOB
    IS TO MOVE BYTES. With none of the three directories present the run makes ZERO `aws` calls, prints three warnings and then `Sync complete. Verify
    with:` plus its two recipe lines, and exits 0. Nothing counts the skips, so
    "it said complete" is not evidence that anything was published.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, [], dirs=())
    assert old.returncode == 0, "the twin started refusing a no-op run"
    assert old_calls == [], "something was uploaded from an empty tree"
    assert old.stderr.count("⚠ Skipping ") == 3
    assert old.stderr.endswith(CLOSING)
    assert port.A_RUN_THAT_UPLOADS_NOTHING_STILL_SAYS_COMPLETE
    _assert_agree(old, new, "uploads-nothing", old_calls, new_calls)


def test_defect_a_file_where_a_directory_belongs_is_reported_as_absent(
    tmp_path: pathlib.Path,
) -> None:
    """`[[ ! -d ]]` cannot tell a regular file from an absent path, so a half-finished write at `packages/www/public/assets/videos` produces `(not present locally)`. Fails closed, with a diagnosis that names the wrong thing; `os.path.isdir` reproduces it exactly."""
    tree = _tree(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        _layout(tree, ())
        (tree / "packages/www/public/assets").mkdir(parents=True, exist_ok=True)
        (tree / SOLUTIONS_DIR).write_text("not a directory", encoding="utf-8")
        proc, calls = _run(subject, tree, ["--solutions-only"])
        assert proc.returncode == 0
        assert calls == []
        assert proc.stderr.startswith(f"⚠ Skipping {tree}/{SOLUTIONS_DIR}/ (not present locally)\n")
    assert port.A_FILE_IN_A_DIRECTORYS_PLACE_IS_REPORTED_AS_ABSENT


def test_a_symlink_to_a_directory_is_synced_not_skipped(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE HALF OF THE PREVIOUS CONTROL. `[[ -d ]]` and `os.path.isdir` both FOLLOW symlinks, so a checkout whose media directory is a symlink to a scratch disk is uploaded rather than silently skipped. Without this, a port
    that answered `Path.is_dir(follow_symlinks=False)` would pass every other
    test in this file."""
    tree = _tree(tmp_path)
    real = tmp_path / "elsewhere-videos"
    real.mkdir(exist_ok=True)
    for subject in (TWIN_REL, PORT_REL):
        _layout(tree, ())
        (tree / "packages/www/public/assets").mkdir(parents=True, exist_ok=True)
        (tree / SOLUTIONS_DIR).symlink_to(real, target_is_directory=True)
        proc, calls = _run(subject, tree, ["--solutions-only"])
        assert proc.returncode == 0
        assert len(calls) == 1, "a symlinked media directory was skipped"
        assert "s3://rediacc-www-media/videos/" in calls[0]


def test_pure_helpers() -> None:
    """The exported helpers, driven directly. Both directions on the parse loop: something that must be refused, and flag combinations that must NOT be."""
    assert port.BUCKET == "rediacc-www-media"
    assert port.CACHE_CONTROL == "public, max-age=31536000"
    assert port.TUTORIALS == ("packages/www/public/assets/tutorials/video/", "tutorials/video/")
    assert port.SOLUTIONS == ("packages/www/public/assets/videos/", "videos/")
    assert port.AUDIO == ("packages/www/public/assets/tutorials/audio/", "tutorials/audio/")
    assert port.CLOSING_LINES[0] == "Sync complete. Verify with:"
    assert port.CLOSING_LINES[1].startswith("  aws s3 sync --dryrun <local-dir> ")
    assert port.CLOSING_LINES[1].endswith("--endpoint-url $CLOUDFLARE_R2_MEDIA_ENDPOINT")
    assert port.CLOSING_LINES[2] == "  curl -sI https://media.rediacc.com/<path>"

    default = port.parse_args([])
    assert (default.tutorials, default.solutions, default.audio) == (True, True, True)
    assert (default.dry_run, default.delete) == (False, False)
    assert default.selected() == [port.TUTORIALS, port.SOLUTIONS, port.AUDIO]
    assert port.parse_args(["--audio-only"]).selected() == [port.AUDIO]
    assert port.parse_args(["--audio-only", "--solutions-only"]).selected() == [port.SOLUTIONS]
    assert port.parse_args(["--delete"]).delete is True
    assert port.parse_args(["--delete"]).dry_run is False
    assert port.parse_args(["--dry-run"]).delete is False

    for bad in ["--force", "-n", "videos", "", "--delete=1"]:
        with pytest.raises(port.UnknownArgumentError) as caught:
            port.parse_args([bad])
        assert caught.value.argument == bad
        assert str(caught.value) == "Unknown argument: %s" % bad

    base = ["--endpoint-url", "EP", "--cache-control", "public, max-age=31536000", "--no-progress"]
    assert port.sync_args("EP", dry_run=False, delete=False) == base
    assert port.sync_args("EP", dry_run=True, delete=False) == [*base, "--dryrun"]
    assert port.sync_args("EP", dry_run=False, delete=True) == [*base, "--delete"]
    assert port.sync_args("EP", dry_run=True, delete=True) == [*base, "--dryrun", "--delete"]
    assert port.upload_argv("/x/y/", "videos/", ["--no-progress"]) == [
        "aws",
        "s3",
        "sync",
        "/x/y/",
        "s3://rediacc-www-media/videos/",
        "--no-progress",
    ]

    assert port.require_secret_key({port.SIGNING_KEY_ENV: ""}) == ""
    with pytest.raises(port.UnboundVariableError) as caught:
        port.require_secret_key({port.SIGNING_KEY_ENV: None})
    assert str(caught.value) == "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable"

    # `--audio-only` selects the audio leg and NOT the other two: the negative half of the control, without which a helper that returned all three legs
    # for every input would still pass everything above.
    assert port.SOLUTIONS not in port.parse_args(["--audio-only"]).selected()
    assert port.TUTORIALS not in port.parse_args(["--audio-only"]).selected()


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on `CACHE_CONTROL` -- the one value that decides how long media.rediacc.com serves an object before revalidating, and whose corruption leaves both streams, the exit code and the call COUNT completely unchanged while every uploaded object gets the wrong header. Driven red, then the source is confirmed byte-identical and green."""
    original = (ROOT / PORT_REL).read_text(encoding="utf-8")
    mutated = original.replace(
        'CACHE_CONTROL = "public, max-age=31536000"',
        'CACHE_CONTROL = "public, max-age=60"',
        1,
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    tree = _tree(tmp_path)
    mutant = ".ci/rediacc_ci/deploy/mutant.py"
    (tree / mutant).write_text(mutated, encoding="utf-8")

    _layout(tree, ALL_DIRS)
    old, old_calls = _run(TWIN_REL, tree, [])
    _layout(tree, ALL_DIRS)
    bad, bad_calls = _run(mutant, tree, [])
    assert bad.returncode == old.returncode == 0, "the plant is invisible in the exit code"
    assert bad.stderr == old.stderr, "the plant is invisible on stderr"
    assert len(bad_calls) == len(old_calls) == 3, "the plant even keeps the call COUNT"
    assert bad_calls != old_calls, "the mutant still sent the one-year Cache-Control"
    assert all("max-age=60" in c for c in bad_calls)

    _layout(tree, ALL_DIRS)
    good, good_calls = _run(PORT_REL, tree, [])
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
