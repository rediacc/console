"""Differential: `rediacc_ci.deploy.delete_r2_channel` against its twin `.ci/scripts/deploy/delete-r2-channel.sh`.

A RECORDING FAKE `aws` ON A SCRATCH PATH. Nothing here reaches R2: the fake logs its exact argv and answers from the environment, and every case pins a fixture bucket, endpoint and credential, so even a bypassed fake would not name a real bucket. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked
parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE EVIDENCE HERE, MORE THAN THE STREAMS, and the fake is built to make that true rather than to hide it: its stdout line is CONSTANT, not derived from the prefix it was handed. So a port that deleted `s3://bucket/cli/pr-1_promoted/` instead of `s3://bucket/cli/pr-1-promoted/` would produce identical stdout, identical stderr and an identical exit code, and only the
recorded argv catches it. `test_planted_defect_is_caught` plants exactly that and shows all three agreeing while the log does not.

THE VACUITY DEFECT IS PINNED. `test_defect_a_refused_delete_reads_as_deleted` drives an `aws` that fails every call and asserts the twin still prints "deleted from R2" and exits 0. Reproduced because agreement with the live twin is the deliverable; repaired, the test goes red and names the port that must follow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import delete_r2_channel as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "delete-r2-channel.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "delete_r2_channel.py"
BASH = shutil.which("bash") or "/bin/bash"

CHANNEL = "pr-fixture"
BUCKET = "bucket-fixture"
ENDPOINT = "https://r2.example.invalid"

# THE STDOUT LINE IS DELIBERATELY CONSTANT. See the module docstring: it is what makes the call log the only witness to WHICH prefix was removed.
FAKE_AWS = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("aws\\t" + "\\t".join(argv) + "\\n")
    fh.flush()
with open(os.environ["FAKE_CALL_LOG"]) as fh:
    call_index = len([line for line in fh if line.strip()])

fail_on = os.environ.get("FAKE_FAIL_ON_CALL")
if os.environ.get("FAKE_AWS_RC") or (fail_on and call_index == int(fail_on)):
    sys.stderr.write("fatal error: An error occurred (AccessDenied) calling ListObjectsV2\\n")
    sys.exit(int(os.environ.get("FAKE_AWS_RC") or "1"))

sys.stdout.write("delete: s3://redacted/object\\n")
"""

# common.sh needs `dirname` at source time (SCRIPT_DIR) and `uname`/`tr` in its detection helpers. Nothing else is on the scratch PATH, so a tool leaking in would be visible as a behaviour change rather than as a silent convenience.
PATH_MINIMUM = ("dirname", "uname", "tr")


def _bin(tmp_path: pathlib.Path, name: str, *, drop: str = "") -> str:
    stub = tmp_path / name
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
    else:
        assert shutil.which("aws", path=str(stub)) is None, "aws leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "CHANNEL": CHANNEL,
        "RELEASES_BUCKET": BUCKET,
        "CLOUDFLARE_R2_ENDPOINT": ENDPOINT,
        "AWS_ACCESS_KEY_ID": "akid-fixture",
        "AWS_SECRET_ACCESS_KEY": "secret-fixture",
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    old, old_calls = _run(TWIN, tmp_path, args, **kw)
    new, new_calls = _run(PORT, tmp_path, args, **kw)
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


def rm_call(prefix: str) -> str:
    return "aws\t" + "\t".join(port.aws_argv(prefix, ENDPOINT)[1:])


def test_the_twelve_calls_are_asserted_in_full(tmp_path: pathlib.Path) -> None:
    """THE WHOLE CALL SEQUENCE, PINNED AGAINST LITERAL BYTES rather than against the port's own helpers, so a change in both would still be caught: six formats, each with its channel prefix and its `-promoted` twin, in order."""
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 0
    assert old_calls == [
        (
            "aws\ts3\trm\ts3://bucket-fixture/cli/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/cli/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/npm/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/npm/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/apt/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/apt/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/rpm/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/rpm/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/apk/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/apk/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/archlinux/pr-fixture/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
        (
            "aws\ts3\trm\ts3://bucket-fixture/archlinux/pr-fixture-promoted/\t--recursive"
            "\t--endpoint-url\thttps://r2.example.invalid"
        ),
    ]
    assert old_calls == [rm_call(p) for p in port.prefixes(BUCKET, CHANNEL)]
    assert old.stderr == (
        "✓ Cleaning up R2 channel: pr-fixture...\n"
        "✓ Channel 'pr-fixture' (+ promoted) deleted from R2\n"
    )
    assert old.stdout == "delete: s3://redacted/object\n" * 12, (
        "aws's own stdout must reach the caller unchanged"
    )
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_aws_stderr_is_discarded(tmp_path: pathlib.Path) -> None:
    """`2>/dev/null` on every call. The fake writes a loud `fatal error` line and NONE of it may appear: a port that let it through would change what a PR-close workflow log says on every failed clean-up."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_AWS_RC="1")
    assert "fatal error" not in old.stderr
    assert "AccessDenied" not in old.stderr
    _assert_agree(old, new, "stderr-discarded", old_calls, new_calls)


def test_defect_a_refused_delete_reads_as_deleted(tmp_path: pathlib.Path) -> None:
    """THE VACUITY DEFECT, PINNED. Every one of the twelve deletes is refused, and the run is indistinguishable from a clean-up that worked: same two log lines, same exit 0. The header justifies `|| true` with "a channel that was never created is not an error", which is true and does not distinguish that case
    from a credential that stopped working.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_AWS_RC="1")
    assert old.returncode == 0, "the twin now fails on a refused delete"
    assert old.stderr == (
        "✓ Cleaning up R2 channel: pr-fixture...\n"
        "✓ Channel 'pr-fixture' (+ promoted) deleted from R2\n"
    )
    assert old.stdout == "", "a refused delete prints nothing, so the run looks quiet"
    assert len(old_calls) == 12, "the sweep stopped at the first refusal"
    assert port.A_REFUSED_DELETE_READS_AS_DELETED
    _assert_agree(old, new, "all-refused", old_calls, new_calls)


def test_one_refused_delete_does_not_stop_the_sweep(tmp_path: pathlib.Path) -> None:
    """`|| true` per call, not per run: the remaining eleven formats are still cleaned up. Driven separately from the all-refused case because a port using a single try/except around the loop would pass that one and fail this."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_FAIL_ON_CALL="3")
    assert old.returncode == 0
    assert len(old_calls) == 12
    assert old.stdout == "delete: s3://redacted/object\n" * 11
    _assert_agree(old, new, "one-refused", old_calls, new_calls)


def test_a_missing_aws_binary_is_refused_first(tmp_path: pathlib.Path) -> None:
    """`require_cmd aws` runs BEFORE the five env guards, so a run missing both the binary and every variable names the BINARY. Order is observable."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        drop="aws",
        drop_env=("CHANNEL", "RELEASES_BUCKET", "CLOUDFLARE_R2_ENDPOINT"),
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n"
    assert old.stdout == ""
    assert old_calls == []
    _assert_agree(old, new, "missing-aws", old_calls, new_calls)


def test_divergence_the_env_guards_are_bashs_own_diagnostic(tmp_path: pathlib.Path) -> None:
    """THE ONE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE "FIXED" BY
    ACCIDENT. `: "${VAR:?msg}"` is bash refusing, so the twin's line carries the
    bash FILE and a bash LINE NUMBER. The port prints the `VAR: msg` half alone, on the same stream, with the same exit status, and makes no calls."""
    for name, message in port.REQUIRED_ENV:
        old, new, old_calls, new_calls = run_both(tmp_path, [], drop_env=(name,))
        assert old.returncode == new.returncode == 1, name
        assert old.stderr.endswith("%s: %s\n" % (name, message)), old.stderr
        assert new.stderr == "%s: %s\n" % (name, message), new.stderr
        assert old.stderr != new.stderr, name
        assert old.stderr.startswith(str(TWIN)), "the twin stopped naming its own path"
        assert old.stdout == new.stdout == ""
        assert old_calls == new_calls == []


def test_the_guards_fire_in_the_twins_order(tmp_path: pathlib.Path) -> None:
    """All five missing at once names CHANNEL, because `${VAR:?}` ends the shell
    at the first one. A port that validated them all and reported the set would print four extra lines."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        drop_env=(
            "CHANNEL",
            "RELEASES_BUCKET",
            "CLOUDFLARE_R2_ENDPOINT",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ),
    )
    assert old.returncode == new.returncode == 1
    assert old.stderr.count("\n") == 1
    assert new.stderr == "CHANNEL: CHANNEL is required (e.g. pr-123)\n"
    assert old_calls == new_calls == []


def test_an_empty_channel_is_refused_not_treated_as_a_prefix(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. This is the case that matters most: an empty CHANNEL would make the prefix `s3://bucket/cli//`, the parent of every channel, and `--recursive` would take all of them. Both sides refuse."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], CHANNEL="")
    assert old.returncode == new.returncode == 1
    assert new.stderr == "CHANNEL: CHANNEL is required (e.g. pr-123)\n"
    assert old_calls == new_calls == [], "an empty channel reached aws"


def test_an_empty_secret_is_refused_too(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], AWS_SECRET_ACCESS_KEY="")
    assert old.returncode == new.returncode == 1
    assert new.stderr.startswith("AWS_SECRET_ACCESS_KEY: ")
    assert old_calls == new_calls == []


def test_a_channel_with_a_space_is_one_argument_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The prefix is interpolated into a quoted word in the twin and passed as one argv element here, so a channel name with a space stays ONE path rather than becoming two arguments to `aws s3 rm`."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], CHANNEL="pr 1")
    assert old.returncode == 0
    assert old_calls[0] == rm_call("s3://bucket-fixture/cli/pr 1/")
    assert "✓ Cleaning up R2 channel: pr 1...\n" in old.stderr
    _assert_agree(old, new, "channel-with-space", old_calls, new_calls)


def test_extra_arguments_are_ignored_by_both(tmp_path: pathlib.Path) -> None:
    """The twin parses nothing at all, so `--dry-run` is NOT a dry run: it is silently ignored and the deletes happen. Driven so a port cannot invent a flag the callers do not have."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--dry-run", "extra"])
    assert old.returncode == 0
    assert len(old_calls) == 12, "an ignored flag became a dry run"
    _assert_agree(old, new, "extra-args", old_calls, new_calls)


def test_divergence_common_sh_interprets_backslash_escapes_in_the_channel(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. Both log lines interpolate `$CHANNEL`, which comes from the environment, and common.sh logs through `echo -e`. A channel name holding a literal backslash-n therefore renders as a newline through the twin and as two characters here, while the `aws` argv stays identical on both sides because that path is data rather than a format string. `rediacc_ci.log`
    formats the message as data on purpose (see its docstring)."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], CHANNEL="pr\\n1")
    assert old.returncode == new.returncode == 0
    assert "channel: pr\n1..." in old.stderr, "the twin no longer interprets escapes"
    assert "channel: pr\\n1..." in new.stderr, "the port started interpreting escapes"
    assert old.stderr != new.stderr
    assert new_calls == old_calls, "the deleted prefixes must still agree exactly"
    assert old_calls[0] == rm_call("s3://bucket-fixture/cli/pr\\n1/")


def test_pure_helpers() -> None:
    assert port.FORMATS == ("cli", "npm", "apt", "rpm", "apk", "archlinux")
    assert port.PROMOTED_SUFFIX == "-promoted"
    assert [name for name, _ in port.REQUIRED_ENV] == [
        "CHANNEL",
        "RELEASES_BUCKET",
        "CLOUDFLARE_R2_ENDPOINT",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ]

    prefixes = port.prefixes("B", "C")
    assert len(prefixes) == 12
    assert prefixes[0] == "s3://B/cli/C/"
    assert prefixes[1] == "s3://B/cli/C-promoted/"
    assert prefixes[-1] == "s3://B/archlinux/C-promoted/"
    assert all(p.endswith("/") for p in prefixes), "a prefix without its trailing slash is a key"

    assert port.aws_argv("s3://B/cli/C/", "https://e") == [
        "aws",
        "s3",
        "rm",
        "s3://B/cli/C/",
        "--recursive",
        "--endpoint-url",
        "https://e",
    ]

    assert port.require_env(dict.fromkeys([n for n, _ in port.REQUIRED_ENV], "x")) == {
        name: "x" for name, _ in port.REQUIRED_ENV
    }


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the `-promoted` suffix -- the one character whose loss leaves the promotion-simulation artifacts in the bucket forever while both streams and the exit code stay IDENTICAL. Driven red, then the source is confirmed byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('PROMOTED_SUFFIX = "-promoted"', 'PROMOTED_SUFFIX = "_promoted"', 1)
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    old, old_calls = _run(TWIN, tmp_path, [])
    bad, bad_calls = _run(mutant, tmp_path, [])
    assert bad.returncode == old.returncode, "the plant is invisible in the exit code"
    assert bad.stdout == old.stdout, "the plant is invisible on stdout"
    assert bad.stderr == old.stderr, "the plant is invisible on stderr"
    assert len(bad_calls) == len(old_calls), "the plant even keeps the call COUNT"
    assert bad_calls != old_calls, "the mutant still deleted the -promoted prefixes"
    assert any("pr-fixture_promoted" in c for c in bad_calls)
    assert not any("pr-fixture_promoted" in c for c in old_calls)

    good, good_calls = _run(PORT, tmp_path, [])
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
