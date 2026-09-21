"""Differential: `rediacc_ci.deploy.simulate_promotion` against its twin `.ci/scripts/deploy/simulate-promotion.sh`.

RECORDING FAKES FOR `aws`, `curl` AND `sleep` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches R2 or Cloudflare; every case pins a fixture endpoint, bucket and credential, and an on-disk directory stands in for the bucket. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity
ledger is a separate, achievable piece of work. This is that piece.

WHY `sleep` IS FAKED RATHER THAN WAITED ON, and why that is EVIDENCE rather than a shortcut. Both retry loops in the twin call `sleep` as an external program, and so does the port. Putting a recording fake on PATH turns the retry SCHEDULE into call-log lines, so `test_the_upload_retry_schedule_is_fifteen_thirty_forty_five_sixty` can assert `sleep 15`, `sleep 30`, `sleep 45`, `sleep
60` in order instead of waiting 150 seconds to observe the same thing less precisely. A port that used `time.sleep` would make the schedule invisible here, which is exactly why the port does not.

THE COPY ORDER IS NOT DETERMINISTIC ON EITHER SIDE. `xargs -P 8` and the port's `ThreadPoolExecutor(8)` both dispatch up to eight copies at once, so the call log's copy lines are compared as a MULTISET within each directory block. `_normalise` does that and nothing else: every non-copy line keeps its position, so a port that listed `apk` before `apt`, or purged before copying,
still diverges. Proven by the planted defect at the bottom, which moves only the DIRECTORY order and is caught.

`/tmp/config` IS A FIXED PATH IN THE TWIN, so these cases cannot be given a private scratch file. Two guards, and the second one repairs a MEASURED flake rather than a theoretical one:

  * an `xdist_group`, so nothing else in the same pytest invocation is writing
    it at the same time;
  * a machine-wide `flock` around every child and the snapshot of what it left
    behind, because `xdist_group` cannot see a SECOND pytest running the same
    suite in the same tree. See `FIXED_TMP_LOCK` for the run that proved it.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import simulate_promotion as port

if typing.TYPE_CHECKING:
    import pathlib

# `/tmp/config` is hard-coded in the twin; the group is what stops a concurrent
# case in another module writing it.
#
# AND THE GROUP DID NOT DO THAT, measured 2026-09-15. The claim above is what the group was believed to buy; what `--dist loadgroup` actually buys is that tests SHARING A GROUP NAME land on one worker. A different module with a DIFFERENT name is therefore not merely unprotected, it is actively placed on another worker -- the opposite of the invariant the line above asserts.
# `test_deploy_promote_r2_to_stable_hotfix.py` drives the same `/tmp/config` (its own docstring lists it as a fixed twin path) under the group name `deploy-promote-fixed-tmp`, so the two modules were scheduled CONCURRENTLY by construction. The failure that exposed it is the one this module's own comment at `FIXED_TMP_LOCK` predicts word for word: `/tmp/config` vanishing between the
# download that wrote it and the upload that reads it, surfacing as `HeadObject 404` and `exit diverged: 1 vs 0`. Serial in isolation: 50/50 pass. Under `-n <jobs> --dist loadgroup`: 4-5 fail, and NOT THE SAME 4-5 twice.
#
# ONE NAME ACROSS BOTH MODULES is the fix, because the name IS the mutex.
pytestmark = pytest.mark.xdist_group("deploy-fixed-tmp")

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "simulate-promotion.sh"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "simulate_promotion.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "CHANNEL": "pr-123",
    "AWS_ACCESS_KEY_ID": "akid-fixture",
    "AWS_SECRET_ACCESS_KEY": "secret-fixture",
    "AWS_DEFAULT_REGION": "auto",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# The bucket fixture, one object per format plus two that earn their place:
#
# * `apt/pr-123/dists/with space/InRelease` carries a SPACE, which is what the awk field-rejoin has to survive and what a naive `cut -d' ' -f4` would split into two bogus keys. * `rpm/pr-123/rediacc.repo` and `archlinux/pr-123/rediacc.conf` are the two files the sed-fix step rewrites, and both carry the source channel in a URL so the rewrite is visible in the uploaded bytes.
DEFAULT_BUCKET = {
    "apt/pr-123/rdc.deb": "deb bytes\n",
    "apt/pr-123/dists/Release": "release body\n",
    "apt/pr-123/dists/with space/InRelease": "inrelease body\n",
    "rpm/pr-123/rdc.rpm": "rpm bytes\n",
    "rpm/pr-123/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/pr-123/\n",
    "apk/pr-123/rdc.apk": "apk bytes\n",
    "apk/pr-123/APKINDEX.tar.gz": "apkindex body\n",
    "archlinux/pr-123/rdc.pkg.tar.zst": "pkg bytes\n",
    "archlinux/pr-123/rediacc.conf": (
        "[rediacc]\nServer = https://releases.rediacc.com/archlinux/pr-123/\n"
    ),
}

# A MODEL of the AWS CLI, not the AWS CLI. `aws` IS NOT INSTALLED IN THIS SANDBOX, so nothing here is checked against the real tool; the differential's evidence is independent of that, because both implementations go through the SAME fake and the argv, the streams and the exit codes are real evidence about the two callers.
#
# `FAKE_AWS_LS_EMPTY_EXITS` is the knob fact 3 needs: real `aws s3 ls` builds disagree about whether an empty prefix is an error, and the twin's floor is reachable only under the build that says it is not.
FAKE_AWS = r'''#!/usr/bin/python3
"""Recording fake for `aws`. See the test module docstring."""
import os
import shutil
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
root = os.environ["FAKE_S3_ROOT"]


def emit(text):
    with open(log, "a") as fh:
        fh.write(text)


emit("call: aws %s\n" % " ".join(argv))

with open(log) as fh:
    call_index = len([line for line in fh if line.startswith("call: aws ")])
fail_on = set(x for x in os.environ.get("FAKE_AWS_FAIL_ON_CALL", "").split(",") if x)
fail_key = os.environ.get("FAKE_AWS_FAIL_ON_KEY", "")
# `FAKE_AWS_FAIL_ON_UPLOAD` fails ONLY the `aws_s3_cp_retry` leg. It is keyed on
# `--cli-read-timeout`, which that helper adds and the plain download does not,
# so the sed-fix download still succeeds and the retry loop is actually reached.
fail_upload = os.environ.get("FAKE_AWS_FAIL_ON_UPLOAD") == "1" and "--cli-read-timeout" in argv
if str(call_index) in fail_on or fail_upload or (fail_key and fail_key in argv):
    sys.stderr.write("fatal error: An error occurred (AccessDenied)\n")
    sys.exit(1)

if argv[:2] == ["configure", "set"]:
    sys.exit(0)

if argv[:2] == ["s3", "ls"]:
    prefix = argv[2][len("s3://"):]
    bucket, _, key_prefix = prefix.partition("/")
    base = os.path.join(root, bucket)
    rows = []
    for dirpath, _dirs, files in os.walk(base):
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            key = os.path.relpath(full, base)
            if key.startswith(key_prefix):
                rows.append((key, os.path.getsize(full)))
    if not rows:
        if os.environ.get("FAKE_AWS_LS_EMPTY_EXITS") == "1":
            sys.stderr.write("\n")
            sys.exit(1)
        sys.exit(0)
    if os.environ.get("FAKE_AWS_LS_ROGUE") == "1":
        # A LISTING KEY OUTSIDE THE REQUESTED PREFIX. Real `aws s3 ls <prefix>`
        # cannot do this; the fake can, because it is the only way to reach the
        # doubled-destination guard, which is what the guard exists for.
        sys.stdout.write("2026-09-13 12:00:00        12 somewhere-else/stray\n")
        sys.exit(0)
    for key, size in sorted(rows):
        sys.stdout.write("2026-09-13 12:00:00 %10d %s\n" % (size, key))
    sys.exit(0)

if argv[:2] == ["s3api", "copy-object"]:
    def value(flag):
        return argv[argv.index(flag) + 1]

    dst = os.path.join(root, value("--bucket"), value("--key"))
    src = os.path.join(root, value("--copy-source"))
    if not os.path.isfile(src):
        sys.stderr.write("An error occurred (NoSuchKey) when calling CopyObject\n")
        sys.exit(1)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)
    emit("COPIED %s\n" % value("--key"))
    sys.stdout.write('{"CopyObjectResult": {}}\n')
    sys.exit(0)

if argv[:2] == ["s3", "cp"]:
    paths_ = [a for i, a in enumerate(argv[2:], start=2)
              if not a.startswith("-") and argv[i - 1] not in ("--endpoint-url",
                                                               "--cache-control",
                                                               "--cli-read-timeout")]
    src, dst = paths_[0], paths_[1]

    def local(p):
        return os.path.join(root, p[len("s3://"):]) if p.startswith("s3://") else p

    source_path = local(src)
    if not os.path.isfile(source_path):
        sys.stderr.write("fatal error: An error occurred (404) when calling HeadObject\n")
        sys.exit(1)
    target_path = local(dst)
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    shutil.copyfile(source_path, target_path)
    if dst.startswith("s3://"):
        with open(source_path) as fh:
            emit("UPLOAD %s<<<%s>>>\n" % (dst, fh.read()))
    sys.exit(0)

sys.stderr.write("fake aws: unmodelled command %r\n" % (argv,))
sys.exit(127)
'''

FAKE_CURL = """#!/usr/bin/python3
import json
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: curl " + " ".join(sys.argv[1:]) + "\\n")

sys.stdout.write(json.dumps({"success": True, "errors": []}) + "\\n")
"""

# `sleep` RECORDS AND RETURNS IMMEDIATELY. See the module docstring: this is what turns the retry schedule into evidence rather than into a slow test.
FAKE_SLEEP = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: sleep " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(0)
"""

# `awk`, `xargs`, `mktemp`, `sed` and `bash` are all reached by the twin, and `jq` by cf-purge-urls.sh.
PATH_MINIMUM = (
    "awk",
    "xargs",
    "mktemp",
    "sed",
    "jq",
    "cat",
    "tr",
    "rm",
    "uname",
    "dirname",
    "basename",
    "printf",
    "env",
    "bash",
)


# A CROSS-PROCESS LOCK, AND IT IS NOT BELT-AND-BRACES: IT REPAIRS A MEASURED FLAKE. `xdist_group` serialises these cases within ONE pytest invocation, and that is all it can do. `/tmp/config` is a MACHINE-WIDE path, so a SECOND pytest running the same suite in the same tree deletes the file this one is mid-way through using.
#
# Measured 2026-09-13, not theorised: a direct run of this file went red on three cases while another session's `check_pytest.py -n 8 --dist loadgroup` was live in the same checkout (`ps` confirmed pid 267264). The visible symptom was `fatal error: An error occurred (404) when calling HeadObject` from the archlinux upload, i.e. `/tmp/config` vanishing between the download that
# wrote it and the upload that reads it. The same three cases passed twice in a row once that run finished.
#
# `flock` turns that corruption into a WAIT. It cannot be avoided by giving the cases a private path, because the path is the TWIN'S and a port that changed it would not be a port.
FIXED_TMP_LOCK = "/tmp/rediacc-simulate-promotion-differential.lock"


@contextlib.contextmanager
def _fixed_tmp_guard():
    """Hold the machine-wide lock, and start from a clean `/tmp/config`.

    REMOVING THE FILE IS NOT TIDINESS. A leftover from a previous case is what the NEXT case's sed-fix step would rewrite and upload if its own download failed, which would make one case silently change the meaning of another.
    """
    with open(FIXED_TMP_LOCK, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(port.SED_FIX_SCRATCH)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
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
    for name, body in (("aws", FAKE_AWS), ("curl", FAKE_CURL), ("sleep", FAKE_SLEEP)):
        script = stub / name
        if name == drop:
            if script.exists():
                script.unlink()
            continue
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(tmp_path: pathlib.Path, bucket: dict[str, str] | None = None) -> pathlib.Path:
    """A throwaway repository holding the twin, cf-purge-urls.sh and common.sh, plus one bucket copy per side."""
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(PURGE, root / ".ci" / "scripts" / "deploy" / PURGE.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)

    for side in ("old", "new"):
        base = root / f"{side}-s3" / port.BUCKET
        base.mkdir(parents=True, exist_ok=True)
        for key, body in (DEFAULT_BUCKET if bucket is None else bucket).items():
            target = base / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")

    env = {
        "PATH": _bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_S3_ROOT": str(root / f"{side}-s3"),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name)]
    else:
        argv = [sys.executable, str(PORT_FILE)]
    # THE LOCK SPANS THE CHILD AND THE SNAPSHOT, not just the cleanup: the file the run LEAVES at `/tmp/config` is evidence, and reading it after releasing would read whatever the next process wrote.
    with _fixed_tmp_guard():
        proc = subprocess.run(
            argv,
            cwd=str(root.parent),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=180,
            input="",
        )
        scratch = root / f"{side}-scratch-left-behind"
        if os.path.isfile(port.SED_FIX_SCRATCH):
            shutil.copyfile(port.SED_FIX_SCRATCH, scratch)
        elif scratch.exists():
            scratch.unlink()
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, bucket: dict[str, str] | None = None, **kw):
    root = fixture(tmp_path, bucket)
    old = _run(root, "old", **kw)
    new = _run(root, "new", **kw)
    return root, old, new


def _normalise(log: str) -> str:
    """Sort each maximal run of parallel copy lines; leave everything else alone.

    THE COPIES ARE THE ONLY NON-DETERMINISTIC PART, and they are non-deterministic on BOTH sides. Every other line keeps its position, so directory order, the `s3 ls` that opens each block, the sed-fix downloads and uploads, the retries and the purge are all compared as a SEQUENCE.
    """
    out: list[str] = []
    block: list[str] = []
    for line in log.splitlines():
        if line.startswith(("call: aws s3api copy-object", "COPIED ")):
            block.append(line)
            continue
        if block:
            out += sorted(block)
            block = []
        out.append(line)
    out += sorted(block)
    return "\n".join(out) + ("\n" if log.endswith("\n") else "")


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the copy-normalised call log."""
    old_proc, old_calls = old
    new_proc, new_calls = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert sorted(new_proc.stdout.splitlines()) == sorted(old_proc.stdout.splitlines()), (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert sorted(new_proc.stderr.splitlines()) == sorted(old_proc.stderr.splitlines()), (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert _normalise(new_calls) == _normalise(old_calls), (
        f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"
    )


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


def _copied(log: str) -> set[str]:
    return {line[len("COPIED ") :] for line in log.splitlines() if line.startswith("COPIED ")}


def _purged(log: str) -> list[str]:
    for line in _calls(log):
        if line.startswith("curl ") and "--data" in line:
            fields = line.split()
            raw = line.split("--data", 1)[1].strip()
            del fields
            return json.loads(raw)["files"]
    return []


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_happy_path_agrees_on_both_streams_and_every_call(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "happy")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr

    # PRINT THE SHAPE: three `aws configure set`, four `s3 ls`, nine copy-objects (one per fixture key), two sed-fix downloads, two sed-fix uploads, one purge. A collapse in any of those numbers is what a "they both said Promotion simulated" comparison would miss.
    listing = _calls(calls)
    assert len([c for c in listing if c.startswith("aws configure set")]) == 3
    assert len([c for c in listing if c.startswith("aws s3 ls")]) == 4
    assert len([c for c in listing if c.startswith("aws s3api copy-object")]) == 9
    assert len([c for c in listing if c.startswith("aws s3 cp s3://")]) == 2
    assert len([c for c in listing if c.startswith("aws s3 cp --cli-read-timeout")]) == 2
    assert len([c for c in listing if c.startswith("curl ")]) == 1
    assert len([c for c in listing if c.startswith("sleep ")]) == 0

    assert "✓ Promotion simulated: pr-123 -> pr-123-promoted" in proc.stderr


def test_every_object_lands_under_the_promoted_prefix_and_none_is_doubled(tmp_path) -> None:
    """THE DESTINATION KEY IS THE WHOLE POINT of `copy_one_object`'s prefix guard: a strip that silently no-ops writes to `apk/pr-123-promoted/apt/pr-123/` and the install tests then read a channel nobody wrote."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "destinations")

    assert _copied(old[1]) == {
        "apt/pr-123-promoted/rdc.deb",
        "apt/pr-123-promoted/dists/Release",
        "apt/pr-123-promoted/dists/with space/InRelease",
        "rpm/pr-123-promoted/rdc.rpm",
        "rpm/pr-123-promoted/rediacc.repo",
        "apk/pr-123-promoted/rdc.apk",
        "apk/pr-123-promoted/APKINDEX.tar.gz",
        "archlinux/pr-123-promoted/rdc.pkg.tar.zst",
        "archlinux/pr-123-promoted/rediacc.conf",
    }
    assert not any("/pr-123/" in key for key in _copied(old[1])), "a destination was doubled"


def test_a_key_with_a_space_survives_the_awk_rejoin(tmp_path) -> None:
    """`aws s3 ls --recursive` prints date, time, size and then the key, and the key may contain spaces. A field-3 split would truncate it; the twin's awk rejoins fields 4..NF with OFS, and so does this port, because it runs the same awk."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "space-in-key")

    assert "apt/pr-123-promoted/dists/with space/InRelease" in _copied(old[1])
    assert "https://releases.rediacc.com/apt/pr-123-promoted/dists/with space/InRelease" in _purged(
        old[1]
    )


def test_the_directory_order_and_the_cache_control_are_the_twins(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "order")

    listed = [c for c in _calls(old[1]) if c.startswith("aws s3 ls")]
    assert [c.split()[3] for c in listed] == [
        "s3://rediacc-releases/apt/pr-123/",
        "s3://rediacc-releases/rpm/pr-123/",
        "s3://rediacc-releases/apk/pr-123/",
        "s3://rediacc-releases/archlinux/pr-123/",
    ], listed
    for call in _calls(old[1]):
        if call.startswith("aws s3api copy-object"):
            assert "--cache-control no-cache" in call, call
            # THE R2 CONSTRAINT, pinned: any tagging directive is refused by R2
            # with NotImplemented on every object.
            assert "--copy-props" not in call
            assert "--tagging-directive" not in call


def test_the_sed_fix_rewrites_the_channel_before_re_uploading(tmp_path) -> None:
    """THE UPLOADED BYTES ARE THE WITNESS. A port that uploaded first and rewrote afterwards would print the same lines and leave the source channel in the promoted config."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "sed-fix")

    calls = old[1]
    assert "baseurl=https://releases.rediacc.com/rpm/pr-123-promoted/" in calls
    assert "Server = https://releases.rediacc.com/archlinux/pr-123-promoted/" in calls
    uploads = [line for line in calls.splitlines() if line.startswith("UPLOAD ")]
    assert len(uploads) == 2, uploads
    assert not any("/rpm/pr-123/" in line for line in uploads), (
        "the source channel survived into an uploaded config"
    )
    assert "✓ Fixed channel in rpm/pr-123-promoted/rediacc.repo" in old[0].stderr
    assert "✓ Fixed channel in archlinux/pr-123-promoted/rediacc.conf" in old[0].stderr


def test_the_purge_list_is_the_copied_objects_plus_the_two_configs(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "purge-list")

    urls = _purged(old[1])
    assert len(urls) == 11, urls
    assert "https://releases.rediacc.com/rpm/pr-123-promoted/rediacc.repo" in urls
    assert "https://releases.rediacc.com/archlinux/pr-123-promoted/rediacc.conf" in urls
    # THE TWO CONFIGS APPEAR TWICE, once from the copy listing and once from the
    # sed-fix loop. 9 + 2 = 11, and the duplication is the twin's.
    assert urls.count("https://releases.rediacc.com/rpm/pr-123-promoted/rediacc.repo") == 2


def test_github_env_receives_the_promoted_channel_when_it_is_set(tmp_path) -> None:
    """AND NOTHING HAPPENS WHEN IT IS NOT, because the twin's line is an AND-list and a failing `[[ -n ... ]]` is exempt from `set -e`."""
    root = fixture(tmp_path)
    old_env = root / "old-github-env"
    new_env = root / "new-github-env"
    old_env.write_text("", encoding="utf-8")
    new_env.write_text("", encoding="utf-8")

    old = _run(root, "old", GITHUB_ENV=str(old_env))
    new = _run(root, "new", GITHUB_ENV=str(new_env))
    _agree(old, new, "github-env")
    assert old_env.read_text(encoding="utf-8") == "PROMOTED=pr-123-promoted\n"
    assert new_env.read_text(encoding="utf-8") == "PROMOTED=pr-123-promoted\n"

    _root2, old2, new2 = run_both(tmp_path / "b")
    _agree(old2, new2, "no-github-env")
    assert old2[0].returncode == 0


# --------------------------------------------------------------------------- The five named facts ---------------------------------------------------------------------------


def test_fact_the_access_key_message_names_a_different_variable(tmp_path) -> None:
    """THE TEST IS ON `AWS_ACCESS_KEY_ID`, THE MESSAGE NAMES
    `CLOUDFLARE_R2_ACCESS_KEY_ID`. Reproduced verbatim, not repaired."""
    assert port.THE_ACCESS_KEY_MESSAGE_NAMES_A_DIFFERENT_VARIABLE is True

    _root, old, new = run_both(tmp_path, drop_env=("AWS_ACCESS_KEY_ID",))
    _agree(old, new, "no-access-key")

    proc, calls = old
    assert proc.returncode == 1
    assert proc.stderr == "✗ CLOUDFLARE_R2_ACCESS_KEY_ID not set\n", repr(proc.stderr)
    assert calls == "", "a refused run still called aws"


def test_fact_the_secret_key_is_never_checked(tmp_path) -> None:
    """A RUN WITH NO SECRET GETS ALL THE WAY THROUGH under a fake aws, because nothing in the script tests it. Against a real endpoint it would fail at the first call, with aws's message rather than this script's."""
    assert port.THE_SECRET_KEY_IS_NEVER_CHECKED is True
    assert "AWS_SECRET_ACCESS_KEY" in TWIN.read_text(encoding="utf-8"), "header claim is gone"

    _root, old, new = run_both(tmp_path, drop_env=("AWS_SECRET_ACCESS_KEY",))
    _agree(old, new, "no-secret-key")
    assert old[0].returncode == 0
    assert "✓ Promotion simulated" in old[0].stderr


def test_fact_the_empty_channel_floor_sits_behind_pipefail(tmp_path) -> None:
    """TWO ENDINGS FOR ONE INPUT, and which one you get depends on `aws`.

    With an `aws s3 ls` that exits 0 on an empty prefix, the floor is reached and prints its sentence. With one that exits 1, `pipefail` ends the run one line earlier and the sentence never appears. BOTH are driven and BOTH agree, because the port reproduces the structure rather than guessing.
    """
    assert port.THE_EMPTY_CHANNEL_FLOOR_SITS_BEHIND_PIPEFAIL is True

    empty = {k: v for k, v in DEFAULT_BUCKET.items() if not k.startswith("apk/")}

    _root, old, new = run_both(tmp_path / "a", empty)
    _agree(old, new, "empty-ls-exits-zero")
    proc, calls = old
    assert proc.returncode == 1
    assert (
        "✗ no objects found under apk/pr-123/; refusing to promote an empty channel" in proc.stderr
    )
    assert "curl" not in calls, "an aborted promotion still purged"

    _root2, old2, new2 = run_both(tmp_path / "b", empty, FAKE_AWS_LS_EMPTY_EXITS="1")
    _agree(old2, new2, "empty-ls-exits-one")
    proc2, _calls2 = old2
    assert proc2.returncode == 1
    assert "no objects found under" not in proc2.stderr, proc2.stderr


def test_fact_the_sed_fix_scratch_path_is_fixed(tmp_path) -> None:
    """`/tmp/config` IS NEVER REMOVED, so the last downloaded config is left on the machine after a successful run. Asserted on the file itself rather than on the sentence."""
    assert port.THE_SED_FIX_SCRATCH_PATH_IS_FIXED is True
    assert port.SED_FIX_SCRATCH == "/tmp/config"

    root = fixture(tmp_path)
    old = _run(root, "old")
    assert old[0].returncode == 0, old[0].stderr
    # THE SNAPSHOT, taken inside the same lock the run held. Reading `/tmp/config` here instead would read whatever the next process wrote, which is the exact race the guard exists for.
    left_by_bash = (root / "old-scratch-left-behind").read_text(encoding="utf-8")

    new = _run(root, "new")
    assert new[0].returncode == 0, new[0].stderr
    left_by_python = (root / "new-scratch-left-behind").read_text(encoding="utf-8")

    assert left_by_bash == left_by_python
    # THE LAST FILE WINS, and the last file is the archlinux one.
    assert "Server = https://releases.rediacc.com/archlinux/pr-123-promoted/" in left_by_bash


def test_fact_an_unset_zone_is_an_unbound_variable_at_the_end(tmp_path) -> None:
    """THE PROMOTION HAS ALREADY HAPPENED when this fires, which is what makes it worth naming: every object is copied, both configs are rewritten, the `Promotion simulated` line is printed, and THEN the run exits 1."""
    assert port.AN_UNSET_ZONE_IS_AN_UNBOUND_VARIABLE_AT_THE_END is True

    root = fixture(tmp_path)
    old_proc, old_calls = _run(root, "old", drop_env=("CLOUDFLARE_ZONE_ID",))
    new_proc, new_calls = _run(root, "new", drop_env=("CLOUDFLARE_ZONE_ID",))

    # NOT `_agree`: this is the second named divergence, and it is the whole point of the case. bash prefixes its own path and line number, the port prefixes the script's name, and everything else about the two runs is identical, which is asserted line by line below rather than waved at.
    assert old_proc.returncode == 1
    assert new_proc.returncode == 1
    assert old_proc.stdout == new_proc.stdout
    assert _normalise(old_calls) == _normalise(new_calls)
    assert old_proc.stderr.splitlines()[:-1] == new_proc.stderr.splitlines()[:-1]
    assert old_proc.stderr.endswith(": CLOUDFLARE_ZONE_ID: unbound variable\n"), repr(
        old_proc.stderr
    )
    assert new_proc.stderr.endswith(
        "simulate-promotion.sh: CLOUDFLARE_ZONE_ID: unbound variable\n"
    ), repr(new_proc.stderr)

    # THE PROMOTION HAS ALREADY HAPPENED, on both sides.
    for calls, proc in ((old_calls, old_proc), (new_calls, new_proc)):
        assert "✓ Promotion simulated: pr-123 -> pr-123-promoted" in proc.stderr
        assert len(_copied(calls)) == 9, "the copies did not happen before the refusal"
        assert "curl" not in calls


# --------------------------------------------------------------------------- Refusals, retries and failures ---------------------------------------------------------------------------


def test_a_missing_channel_refuses_before_anything_runs(tmp_path) -> None:
    """THE ONE NAMED `${VAR:?}` DIVERGENCE, in text nobody parses."""
    root = fixture(tmp_path)
    old_proc, old_calls = _run(root, "old", drop_env=("CHANNEL",))
    new_proc, new_calls = _run(root, "new", drop_env=("CHANNEL",))

    assert old_proc.returncode == 1, old_proc.stderr
    assert new_proc.returncode == 1, new_proc.stderr
    assert old_calls == ""
    assert new_calls == ""
    tail = "CHANNEL: CHANNEL is required (the source channel, e.g. pr-123)\n"
    assert old_proc.stderr.endswith(tail), repr(old_proc.stderr)
    assert new_proc.stderr == tail, repr(new_proc.stderr)


def test_an_empty_channel_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST, so `CHANNEL=` refuses. A port that only
    tested for presence would promote `-promoted` from the bucket root."""
    root = fixture(tmp_path)
    old_proc, _ = _run(root, "old", CHANNEL="")
    new_proc, _ = _run(root, "new", CHANNEL="")
    assert old_proc.returncode == 1
    assert new_proc.returncode == 1
    tail = "CHANNEL: CHANNEL is required (the source channel, e.g. pr-123)\n"
    assert old_proc.stderr.endswith(tail)
    assert new_proc.stderr == tail


def test_a_missing_endpoint_refuses_after_the_channel(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, drop_env=("CLOUDFLARE_R2_ENDPOINT",))
    _agree(old, new, "no-endpoint")
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ CLOUDFLARE_R2_ENDPOINT not set\n", repr(old[0].stderr)


def test_a_missing_aws_refuses_before_the_channel_guard(tmp_path) -> None:
    """ORDER: `require_cmd aws` is BEFORE `${CHANNEL:?}`, so a run with neither
    names aws."""
    _root, old, new = run_both(tmp_path, drop="aws", drop_env=tuple(BASE_ENV))
    _agree(old, new, "no-aws")
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Required command 'aws' is not available\n", repr(old[0].stderr)


def test_a_key_outside_the_source_prefix_is_refused_rather_than_doubled(tmp_path) -> None:
    """A DOUBLED DESTINATION IS WORSE THAN A FAILED COPY, so the guard refuses.

    `${src_key#"$SRC_PREFIX"}` on a key that does not carry the prefix is a
    SILENT NO-OP, and the copy would then land at `apt/pr-123-promoted/somewhere-else/stray`. The install tests that follow would read a channel nobody wrote, so the run stops instead.

    THE GUARD CANNOT BE REACHED THROUGH A REAL LISTING, since `aws s3 ls <prefix>` only returns keys under that prefix. The fake supplies one anyway, which is the same thing `test_gate_simulate_promotion_serverside.py` does and for the same reason: an unreachable guard still has to be proved to work, or its port is unchecked.
    """
    _root, old, new = run_both(tmp_path, FAKE_AWS_LS_ROGUE="1")
    _agree(old, new, "rogue-key")

    proc, calls = old
    assert proc.returncode == 123, proc.stderr
    assert "key 'somewhere-else/stray' is not under expected prefix 'apt/pr-123/'" in proc.stderr
    assert _copied(calls) == set(), "a key outside the prefix was copied anyway"
    assert "curl" not in calls


def test_a_copy_that_keeps_failing_ends_the_run_with_xargs_status(tmp_path) -> None:
    """THREE ATTEMPTS, TWO SLEEPS, THEN 123.

    The status is 123, not 1: `xargs` reports "at least one invocation exited 1..125" that way and `set -e` passes it on. A port that returned 1 would look right to a reader and wrong to a caller that switches on the code.
    """
    _root, old, new = run_both(tmp_path, FAKE_AWS_FAIL_ON_KEY="apt/pr-123-promoted/rdc.deb")
    _agree(old, new, "copy-fails")

    proc, calls = old
    assert proc.returncode == 123, proc.stderr
    # THREE ATTEMPTS AND TWO SLEEPS, which is the retry contract.
    attempts = [c for c in _calls(calls) if "--key apt/pr-123-promoted/rdc.deb" in c]
    assert len(attempts) == 3, attempts
    assert [c for c in _calls(calls) if c.startswith("sleep ")] == ["sleep 5", "sleep 10"]
    assert "copy-object failed after 3 attempts: apt/pr-123/rdc.deb" in proc.stderr
    assert "curl" not in calls, "a failed promotion still purged"


def test_the_upload_retry_schedule_is_fifteen_thirty_forty_five_sixty(tmp_path) -> None:
    """`aws_s3_cp_retry` IS FIVE ATTEMPTS WITH 15/30/45/60-SECOND GAPS.

    Only readable because `sleep` is an external program on both sides. The fifth failure prints `aws s3 cp <args> failed after 5 attempts`, where `<args>` is `$*`: the arguments the FUNCTION was given, WITHOUT the `s3 cp --cli-read-timeout 0` prefix it adds. A port that echoed the full argv would print a different sentence and pass every other case here.
    """
    _root, old, new = run_both(tmp_path, FAKE_AWS_FAIL_ON_UPLOAD="1")
    _agree(old, new, "cp-retries")

    proc, calls = old
    assert proc.returncode == 1
    sleeps = [c for c in _calls(calls) if c.startswith("sleep ")]
    assert sleeps == ["sleep 15", "sleep 30", "sleep 45", "sleep 60"], sleeps
    assert "⚠ aws s3 cp attempt 1 failed, retrying in 15s..." in proc.stderr
    assert "⚠ aws s3 cp attempt 4 failed, retrying in 60s..." in proc.stderr
    assert (
        "✗ aws s3 cp /tmp/config s3://rediacc-releases/rpm/pr-123-promoted/rediacc.repo "
        "--endpoint-url https://r2.example.invalid --cache-control no-cache "
        "failed after 5 attempts" in proc.stderr
    )


def test_an_absent_sed_fix_target_is_skipped_in_silence(tmp_path) -> None:
    """`if aws s3 cp ... 2>/dev/null; then` IS THE CONDITION, so a config that is not in the channel skips the rewrite without a word. Both configs are removed here, so both are skipped and the run still succeeds."""
    stripped = {
        k: v
        for k, v in DEFAULT_BUCKET.items()
        if os.path.basename(k) not in ("rediacc.repo", "rediacc.conf")
    }
    _root, old, new = run_both(tmp_path, stripped)
    _agree(old, new, "no-sed-targets")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr
    assert "Fixed channel in" not in proc.stderr
    assert len([c for c in _calls(calls) if c.startswith("aws s3 cp --cli-read-timeout")]) == 0
    assert len(_purged(calls)) == 7


def test_a_failing_aws_configure_stops_before_anything_is_listed(tmp_path) -> None:
    """UNGUARDED UNDER `set -e`, and it is the FIRST thing that runs, so a misconfigured CLI never reaches the bucket."""
    _root, old, new = run_both(tmp_path, FAKE_AWS_FAIL_ON_CALL="1")
    _agree(old, new, "configure-fails")

    proc, calls = old
    assert proc.returncode == 1
    assert len(_calls(calls)) == 1
    assert "AccessDenied" in proc.stderr


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, and prove WHICH assertion fires.

    The plant reverses the directory order. Every object still lands in the right place, the same eleven URLs are purged, the exit code is 0 and every printed line is present, so a set-compared stdout sees nothing. Only the SEQUENCE of `s3 ls` calls in the normalised call log carries it, which is also the proof that `_normalise` is not sorting more than the copies.
    """
    root = fixture(tmp_path)
    old_proc, old_calls = _run(root, "old")

    planted_file = root / "planted_simulate_promotion.py"
    source = PORT_FILE.read_text(encoding="utf-8")
    mutant = source.replace(
        'CHANNEL_DIRS = ("apt", "rpm", "apk", "archlinux")',
        'CHANNEL_DIRS = ("archlinux", "apk", "rpm", "apt")',
    )
    assert mutant != source, "the plant did not apply; the control is broken, not the gate"
    planted_file.write_text(mutant, encoding="utf-8")

    call_log = root / "planted-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_S3_ROOT": str(root / "new-s3"),
        **BASE_ENV,
    }
    with _fixed_tmp_guard():
        new_proc = subprocess.run(
            [sys.executable, str(planted_file)],
            cwd=str(root.parent),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=180,
            input="",
        )
    new_calls = call_log.read_text(encoding="utf-8")

    assert new_proc.returncode == old_proc.returncode, "the plant changed the exit code"
    assert sorted(new_proc.stderr.splitlines()) == sorted(old_proc.stderr.splitlines()), (
        "the plant changed the SET of stderr lines; a weaker comparison would still catch it"
    )
    assert _copied(new_calls) == _copied(old_calls), "the plant moved an object; wrong plant"
    assert _normalise(new_calls) != _normalise(old_calls), (
        "THE CALL LOG DID NOT SEE IT: _normalise is sorting more than the copies"
    )


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_the_directory_list_is_the_twins_and_excludes_cli() -> None:
    """`cli` IS DELIBERATELY ABSENT: this script promotes only the
    package-manager repositories the install tests exercise. A port that added
    it would copy release binaries into a throwaway channel on every PR."""
    assert port.CHANNEL_DIRS == ("apt", "rpm", "apk", "archlinux")
    assert "cli" not in port.CHANNEL_DIRS


def test_endpoint_args_is_two_elements_even_for_a_spaced_endpoint() -> None:
    """`"${EP[@]}"` IS QUOTED IN THIS TWIN, unlike `promote-r2-to-stable.sh`'s
    bare `$EP`. The two twins genuinely differ and so do the two ports."""
    assert port.endpoint_args("https://x") == ["--endpoint-url", "https://x"]
    assert port.endpoint_args("a b") == ["--endpoint-url", "a b"]


def test_copy_object_argv_names_no_tagging_flag() -> None:
    argv = port.copy_object_argv("dst", "src", "https://x")
    assert argv[:3] == ["aws", "s3api", "copy-object"]
    assert "--metadata-directive" in argv
    assert argv[argv.index("--metadata-directive") + 1] == "REPLACE"
    assert "--tagging-directive" not in argv
    assert "--copy-props" not in argv
    assert argv[argv.index("--copy-source") + 1] == "rediacc-releases/src"


def test_upload_argv_puts_the_read_timeout_before_the_paths() -> None:
    argv = port.upload_argv("rpm/x/rediacc.repo", "https://x")
    assert argv[:5] == ["aws", "s3", "cp", "--cli-read-timeout", "0"]
    assert argv[5] == "/tmp/config"
    assert argv[-2:] == ["--cache-control", "no-cache"]


def test_strip_prefix_and_read_lines_follow_bash_rather_than_python() -> None:
    assert port.strip_prefix("apt/pr-1/a", "apt/pr-1/") == "a"
    assert port.strip_prefix("other/a", "apt/pr-1/") == "other/a"
    assert port.read_lines("a\nb\n") == ["a", "b"]
    assert port.read_lines("a\nb") == ["a"]
    assert port.read_lines("a\n\nb\n") == ["a", "b"]
    assert port.read_lines("") == []


def test_the_purge_script_is_still_the_bash_one_and_still_exists() -> None:
    assert port.PURGE_SCRIPT_RELATIVE == ".ci/scripts/deploy/cf-purge-urls.sh"
    assert PURGE.is_file()
    assert port.purge_argv("z")[-2:] == ["--zone", "z"]


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    """A STALENESS GUARD, quoting the twin."""
    text = TWIN.read_text(encoding="utf-8")
    assert "for dir in apt rpm apk archlinux; do" in text
    assert "xargs -P 8 -I{} bash -c 'copy_one_object \"$@\"' _ {}" in text
    assert 'log_error "CLOUDFLARE_R2_ACCESS_KEY_ID not set"' in text
    assert '--zone "$CLOUDFLARE_ZONE_ID"' in text
    assert "${CLOUDFLARE_ZONE_ID:-}" not in text
    assert "aws configure set default.s3.max_concurrent_requests 3" in text
