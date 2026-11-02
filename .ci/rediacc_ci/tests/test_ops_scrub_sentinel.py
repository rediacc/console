"""`rediacc_ci.ops.scrub_sentinel` against its bash twin `scripts/ops/scrub-sentinel.sh`, on the sealed fake-binary PATH of `ops_cf_harness` with a fake `aws` and `git`.

Differentials compare stdout, stderr (ANSI stripped) and exit code, and the recorded `aws` argv sequence. A `test_delta_*` case pins one Rule T difference, asserting the bash behaviour first as the control. The fake `aws` never reaches a network.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import types

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import scrub_sentinel as port
from rediacc_ci.tests import ops_cf_harness as h

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
if "ls-remote" in sys.argv:
    remote = os.environ.get("FAKE_GIT_REMOTE_TAG", os.environ.get("FAKE_GIT_TAG", ""))
    sys.exit(int(os.environ.get("FAKE_GIT_REMOTE_RC", "0" if remote else "2")))
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
        ".ci/config/well-known.env",
    ):
        if not (src / rel).is_file():  # a retired twin: only a re-freeze from bash runs it
            continue
        dest = w.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dest)
    return w


def _aws_calls(world: h.World) -> list[list[str]]:
    return [c["argv"] for c in world.calls() if c["tool"] == "aws"]


def _run_both(world: h.World, args: list[str], stdin: str = "", **env: str):
    e = world.env(**{**CREDS, **env})
    b = world.twin_run(SUBJECT, args, e, stdin=stdin)
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
    if not args:
        # ONE DECLARED DELTA (the missing-version case only): the usage line names the module the way it is run now. The bash script it named was deleted (363a35892), so the golden's line is mapped before the comparison, and the golden is asserted to carry it so the mapping cannot go vacuous.
        usage_bash = "usage: scrub-sentinel.sh "
        usage_port = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel "
        assert usage_bash in h.strip(b[2]), b[2]
        b = (b[0], b[1], h.strip(b[2]).replace(usage_bash, usage_port))
    _same(b, p)
    assert p[0] == want


def test_a_missing_variable_matches_bash(world: h.World) -> None:
    e = world.env(CLOUDFLARE_R2_ACCESS_KEY_ID="id")
    b = world.twin_run(SUBJECT, ["v1.0.5"], e)
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


def _port(world: h.World, args: list[str], **env: str):
    return world.port(MODULE, args, world.env(**{**CREDS, **env}))


def test_delta_a_tag_only_the_local_clone_holds_is_not_live(world: h.World) -> None:
    """Rule T 5: the bash warned from the local tag list; the port asks origin, so a tag origin deleted draws no live-tag warning, while the same tag on origin still does (the control)."""
    p = _port(world, ["v1.0.5"], FAKE_GIT_TAG="1", FAKE_GIT_REMOTE_TAG="")
    assert p[0] == 0
    assert "git tag v1.0.5 exists" not in p[2]
    control = _port(world, ["v1.0.5"], FAKE_GIT_TAG="1", FAKE_GIT_REMOTE_TAG="1")
    assert "git tag v1.0.5 exists" in control[2]


def test_delta_an_origin_that_cannot_answer_counts_as_a_live_tag(world: h.World) -> None:
    """Rule T 5: an unanswered ls-remote is not a no; the port names it and warns as for a live tag."""
    p = _port(world, ["v1.0.5"], FAKE_GIT_REMOTE_RC="128")
    assert "could not ask origin" in p[2]
    assert "git tag v1.0.5 exists" in p[2]


def test_the_origin_probe_cannot_prompt_and_gives_up_at_its_bound(tmp_path, monkeypatch) -> None:
    """Rule T 5: the probe runs git with GIT_TERMINAL_PROMPT=0, in a session of its own with stdin closed (no terminal for ssh to prompt on), passes `-c credential.helper=` to empty the unscoped helper list, drops DISPLAY and forces SSH_ASKPASS_REQUIRE=never, leaves a caller's GIT_SSH_COMMAND untouched, and an origin slower than ORIGIN_TIMEOUT_S answers None (reviews b232b7b3.1, ada48848.1-.2, 4e8ed4db.1-.2, 32290b26.1, cc80defa.1-.2, e94f58c2.1, 1c71291b.1-.3, ed6787c8.1)."""
    seen = tmp_path / "env.json"
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys, time\n"
        f"open({str(seen)!r} + '.argv', 'w').write(json.dumps(sys.argv[1:]))\n"
        f"open({str(seen)!r}, 'w').write(json.dumps({{**{{k: os.environ.get(k) for k in ('GIT_TERMINAL_PROMPT', 'GIT_SSH_COMMAND', 'SSH_ASKPASS_REQUIRE', 'DISPLAY')}}, 'leader': os.getsid(0) == os.getpid(), 'stdin': sys.stdin.read()}}))\n"
        "if os.environ.get('FAKE_GIT_SLEEP'):\n"
        "    import subprocess\n"
        "    helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"    open({str(seen)!r} + '.helper.tmp', 'w').write(str(helper.pid))\n"
        f"    os.replace({str(seen)!r} + '.helper.tmp', {str(seen)!r} + '.helper')\n"
        "time.sleep(float(os.environ.get('FAKE_GIT_SLEEP', '0')))\n"
        "sys.exit(2)\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    monkeypatch.setenv("GIT_SSH_COMMAND", "plink -batch")
    monkeypatch.setenv("SSH_ASKPASS_REQUIRE", "force")
    monkeypatch.setenv("DISPLAY", ":0")
    assert port._tag_exists(tmp_path, "v1.0.5") is False
    env = json.loads(seen.read_text())
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_SSH_COMMAND"] == "plink -batch"
    assert env["SSH_ASKPASS_REQUIRE"] == "never"
    assert env["DISPLAY"] is None
    argv = json.loads((tmp_path / "env.json.argv").read_text())
    assert argv[argv.index("-c") + 1] == "credential.helper="
    assert env["leader"] is True
    assert env["stdin"] == ""
    marker = tmp_path / "env.json.helper"

    class HelperFirstPopen(subprocess.Popen):
        """Starts the probe's bound only once the fake git has recorded its helper, so a slow runner cannot fire the bound first (reviews 371ac8ec.4, edca7a05.1, 491107ff.1); the fake writes the pid to a temporary name and renames it, so the marker never exists empty (review e7b86ad4.2); a fake that never records one is a failure, not a skip."""

        def wait(self, timeout=None):
            ready = time.monotonic() + 30
            while not marker.exists():
                if time.monotonic() > ready:
                    raise AssertionError("the fake git never started its helper within 30 s")
                time.sleep(0.02)
            return super().wait(timeout)

    # Only the probe module sees the gated Popen: a namespace standing in for `subprocess` inside port, never the stdlib module the rest of the test process shares (review e7b86ad4.1).
    monkeypatch.setattr(
        port, "subprocess", types.SimpleNamespace(**{**vars(subprocess), "Popen": HelperFirstPopen})
    )
    monkeypatch.setattr(port, "ORIGIN_TIMEOUT_S", 0.5)
    monkeypatch.setenv("FAKE_GIT_SLEEP", "5")
    assert port._tag_exists(tmp_path, "v1.0.5") is None
    # The timeout ends the helper git started too, not only git (review ed6787c8.1).
    helper = int(marker.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _dead(helper):
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"helper {helper} outlived the probe's timeout")


def _dead(pid: int) -> bool:
    """Gone, or a zombie nobody has reaped yet (an init that does not reap, as in some containers): either way it runs no more (review 371ac8ec.3). The zombie reading needs Linux /proc; elsewhere an unreaped zombie reads as alive (review edca7a05.2), and the suite runs on Linux hosts and runners."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def test_a_git_that_cannot_start_reads_as_cannot_tell(tmp_path, monkeypatch) -> None:
    """With no git on PATH the probe answers None (cannot tell, treated as live) instead of raising (review 371ac8ec.2)."""
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    assert port._tag_exists(tmp_path, "v1.0.5") is None
