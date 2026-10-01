"""`rediacc_ci.ops.scrub_sentinel` against its bash twin `scripts/ops/scrub-sentinel.sh`, on the sealed fake-binary PATH of `ops_cf_harness` with a fake `aws` and `git`.

Differentials compare stdout, stderr (ANSI stripped) and exit code, and the recorded `aws` argv sequence. A `test_delta_*` case pins one Rule T difference, asserting the bash behaviour first as the control. The fake `aws` never reaches a network.
"""

from __future__ import annotations

import json
import shutil
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

FAKE_AWS = """#!{py}
import json, os, sys
argv = sys.argv[1:]
log = os.environ["FAKE_LOG"]
with open(log, "a") as fh:
    fh.write(json.dumps({{"tool": "aws", "argv": argv}}) + "\\n")
if argv[:2] == ["s3api", "head-object"]:
    sys.stderr.write(os.environ.get("FAKE_HEAD_ERR", ""))
    sys.exit(int(os.environ.get("FAKE_HEAD_RC", "0")))
if argv[:2] == ["s3api", "list-objects-v2"]:
    counter = log + ".count"
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(n + 1))
    if int(os.environ.get("FAKE_LS_RC", "0")):
        sys.stderr.write("ListFailed\\n")
        sys.exit(int(os.environ["FAKE_LS_RC"]))
    count = os.environ.get("FAKE_COUNT", "3") if n == 0 else os.environ.get("FAKE_COUNT_AFTER", "0")
    sys.stdout.write(count + "\\n")
    sys.exit(0)
if argv[:2] == ["s3", "rm"]:
    sys.stdout.write("delete: " + argv[2] + "x\\n")
    sys.exit(int(os.environ.get("FAKE_RM_RC", "0")))
sys.exit(0)
"""

FAKE_GIT = """#!{py}
import os, sys
sys.exit(0 if os.environ.get("FAKE_GIT_TAG") else 1)
"""

CREDS = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "secret",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
}
SUBJECT = "scripts/ops/scrub-sentinel.sh"
MODULE = "rediacc_ci.ops.scrub_sentinel"


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    w = h.World(tmp_path)
    py = sys.executable
    h.World._write_exec(w.bin / "aws", FAKE_AWS.format(py=py))
    h.World._write_exec(w.bin / "git", FAKE_GIT.format(py=py))
    for tool in ("sort", "mktemp", "rm", "tail", "wc"):
        real = shutil.which(tool)
        if real and not (w.bin / tool).exists():
            (w.bin / tool).symlink_to(real)
    src = paths.repo_root()
    for rel in (
        SUBJECT,
        ".ci/scripts/lib/release-state-validator.sh",
        ".ci/scripts/lib/blocker-validator.sh",
        ".ci/scripts/lib/emit-advisory.sh",
    ):
        dest = w.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dest)
    return w


def _aws_calls(world: h.World) -> list[list[str]]:
    return [c["argv"] for c in world.calls() if c["tool"] == "aws"]


def _run_both(world: h.World, args: list[str], stdin: str = "", **env: str):
    e = world.env(**{**CREDS, **env})
    b = world.bash(SUBJECT, args, e, stdin=stdin)
    calls_b = _aws_calls(world)
    world.reset_log()
    (world.root / "calls.jsonl.count").unlink(missing_ok=True)
    (world.log.parent / "calls.jsonl.count").unlink(missing_ok=True)
    p = world.port(MODULE, args, e, stdin=stdin)
    return b, p, calls_b, _aws_calls(world)


def _same(b: tuple, p: tuple) -> None:
    assert b[0] == p[0]
    assert h.strip(b[1]) == h.strip(p[1])
    assert h.strip(b[2]) == h.strip(p[2])


def test_dry_run_matches_bash(world: h.World) -> None:
    b, p, calls_b, calls_p = _run_both(world, ["v1.0.5"])
    _same(b, p)
    assert p[0] == 0
    assert "sentinel: PRESENT" in p[1]
    assert "objects: 3" in p[1]
    assert calls_b == calls_p
    assert not any(c[:2] == ["s3", "rm"] for c in calls_p)


def test_execute_matches_bash(world: h.World) -> None:
    b, p, calls_b, calls_p = _run_both(world, ["v1.0.5", "--execute", "--yes"])
    _same(b, p)
    assert p[0] == 0
    assert "scrubbed v1.0.5" in p[2]
    # The port lists once more after the delete (delta 2); the sequence up to the delete is the bash's.
    assert calls_p[: len(calls_b)] == calls_b
    assert calls_p[-1][:2] == ["s3api", "list-objects-v2"]


def test_an_absent_sentinel_matches_bash(world: h.World) -> None:
    b, p, _, _ = _run_both(
        world,
        ["v1.0.5"],
        FAKE_HEAD_RC="254",
        FAKE_HEAD_ERR="An error occurred (404) when calling HeadObject: Not Found",
    )
    _same(b, p)
    assert "sentinel: absent" in p[1]


@pytest.mark.parametrize(
    ("args", "want"),
    [([], 2), (["v1.0.5", "v1.0.6"], 2), (["--bogus"], 2), (["v1.0"], 2), (["v1.0.5x"], 2)],
)
def test_argument_errors_match_bash(world: h.World, args: list[str], want: int) -> None:
    b, p, _, _ = _run_both(world, args)
    _same(b, p)
    assert p[0] == want


def test_a_missing_variable_matches_bash(world: h.World) -> None:
    e = world.env(CLOUDFLARE_R2_ACCESS_KEY_ID="id")
    b = world.bash(SUBJECT, ["v1.0.5"], e)
    p = world.port(MODULE, ["v1.0.5"], e)
    _same(b, p)
    assert p[0] == 1
    assert "CLOUDFLARE_R2_SECRET_ACCESS_KEY" in p[2]


def test_a_live_tag_prompt_matches_bash(world: h.World) -> None:
    b, p, _, _ = _run_both(world, ["v1.0.5", "--execute"], stdin="no\n", FAKE_GIT_TAG="1")
    _same(b, p)
    assert p[0] == 1
    assert "git tag v1.0.5 exists" in p[2]
    assert "aborted" in p[2]


def test_the_confirmation_prompt_matches_bash(world: h.World) -> None:
    b, p, calls_b, calls_p = _run_both(world, ["v1.0.5", "--execute"], stdin="n\n")
    _same(b, p)
    assert p[0] == 1
    assert not any(c[:2] == ["s3", "rm"] for c in calls_p + calls_b)
    b, p, calls_b, calls_p = _run_both(world, ["v1.0.5", "--execute"], stdin="y\n")
    assert b[0] == p[0] == 0
    assert any(c[:2] == ["s3", "rm"] for c in calls_p)


def test_delta_an_unanswered_sentinel_probe_is_not_absent(world: h.World) -> None:
    denied = {"FAKE_HEAD_RC": "255", "FAKE_HEAD_ERR": "An error occurred (AccessDenied)"}
    b, p, _, _ = _run_both(world, ["v1.0.5"], **denied)
    assert b[0] == 0
    assert "sentinel: absent" in b[1]
    assert p[0] == 1
    assert "sentinel: UNKNOWN" in p[1]
    assert "sentinel: absent" not in p[1]
    assert "could not be established" in p[2]


def test_delta_an_unanswered_listing_is_not_zero_objects(world: h.World) -> None:
    b, p, _, _ = _run_both(world, ["v1.0.5"], FAKE_LS_RC="255")
    assert b[0] == 0
    assert "objects: 0" in b[1]
    assert p[0] == 1
    assert "objects: UNKNOWN" in p[1]


def test_delta_the_delete_is_verified(world: h.World) -> None:
    b, p, _, _ = _run_both(world, ["v1.0.5", "--execute", "--yes"], FAKE_COUNT_AFTER="2")
    assert b[0] == 0
    assert "scrubbed v1.0.5" in b[2]
    assert p[0] == 1
    assert "still lists 2 object(s)" in p[2]
    assert "scrubbed" not in p[2]


def test_delta_an_unanswered_prompt_aborts_with_a_message(world: h.World) -> None:
    b, p, _, _ = _run_both(world, ["v1.0.5", "--execute"], stdin="")
    assert b[0] == 1
    assert "aborted" not in b[2]
    assert p[0] == 1
    assert "aborted" in p[2]


def test_delta_a_failed_delete_exits_with_awss_status(world: h.World) -> None:
    b, p, _, _ = _run_both(world, ["v1.0.5", "--execute", "--yes"], FAKE_RM_RC="3")
    assert b[0] == p[0] == 3
    assert "aws s3 rm failed (exit 3)" in p[2]
    assert json.dumps(b[2]) is not None
