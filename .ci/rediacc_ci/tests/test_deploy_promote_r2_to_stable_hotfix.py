"""Differential: `rediacc_ci.deploy.promote_r2_to_stable_hotfix` against its twin `.ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`.

RECORDING FAKES FOR `aws` AND `curl` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches R2 or Cloudflare: the `aws` fake serves an on-disk directory standing in for the bucket, logs its exact argv, and logs the CONTENT of every uploaded file; the `curl` fake answers cf-purge-urls.sh from a constant. Every case pins a fixture endpoint, bucket and credential.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE. This script prints five `Promoting ...` lines and one closing line, none of which is derived from what actually moved, so two implementations can agree on every printed byte while copying different prefixes. The content log is load-bearing too: the channel-pointer files are REWRITTEN on the way past, and a port that skipped the rewrite would
print the same six lines while publishing an install script that still installs `edge`.

WHAT THE `aws` FAKE MODELS AND WHAT IT DOES NOT. It is a model of the AWS CLI, not the AWS CLI, and this file says so rather than letting a reader assume otherwise. `aws` IS NOT INSTALLED IN THIS SANDBOX (`command -v aws` is empty), so nothing here can be checked against the real tool. What the differential proves is INDEPENDENT of the model's fidelity: both implementations are
driven through the SAME fake, so the argv comparison, the exit code and the two streams are real evidence about the port. The modelled parts -- which local files a recursive copy moves, and the include/exclude semantics -- exist only to make the vacuity floor and the purge list realistic, and any statement about which files reached `stable/` is a statement about the model.

`/tmp/promote-<dir>`, `/tmp/config` AND `/tmp/script` ARE FIXED PATHS IN THE TWIN, so these cases cannot be given a private temporary directory: they clean those exact seven paths before every side of every case, and the module carries an `xdist_group` so the two promote differentials land on the SAME xdist worker and cannot run concurrently. Both facts are the twin's, not the
test's; see `STALE_TMP_IS_PROMOTED` in the port's docstring.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import promote_r2_to_stable_hotfix as port
from rediacc_ci.quality import python_env_registry

if typing.TYPE_CHECKING:
    import pathlib

# BOTH PROMOTE DIFFERENTIALS SHARE THIS GROUP, and the group is the only thing standing between them and each other's `/tmp/promote-cli`. `--dist loadgroup` is on `check_pytest.py`'s argv, so a static marker here is honoured.
#
# THE NAME IS NOW SHARED WITH test_deploy_simulate_promotion.py, and the widening is the fix rather than tidying. This module drives `/tmp/config` too -- the docstring above lists it among the twin's fixed paths -- and so does that one, which additionally holds a machine-wide flock for it. A lock ONE of two parties takes is not a lock: under the old split names `--dist loadgroup`
# put the two modules on different workers BY CONSTRUCTION, so this module's `/tmp/config` writes landed inside the other's critical section. Measured 2026-09-15: 50/50 pass serially, 4-5 fail under xdist, and not the same 4-5 on consecutive runs.
#
# RESIDUAL, named rather than left to be rediscovered: this module still does not take `FIXED_TMP_LOCK`. The shared group makes the two serial WITHIN a run; the lock is what would also protect against a SECOND pytest run in the same tree, and only the simulate module has it.
pytestmark = pytest.mark.xdist_group("deploy-fixed-tmp")

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "promote-r2-to-stable-hotfix.sh"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "promote_r2_to_stable_hotfix.py"
BASH = shutil.which("bash") or "/bin/bash"

# The exact paths the twin hard-codes. Named once so the cleanup below cannot drift from what the scripts use.
FIXED_TMP_PATHS = (
    *(port.TMP_PREFIX + d for d in port.CHANNEL_DIRS),
    port.CONFIG_SCRATCH,
    port.SCRIPT_SCRATCH,
)

BASE_ENV = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-key-fixture",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret-fixture",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# The bucket fixture. `apt` holds a file in a SUBDIRECTORY as well as one at the
# top, because `${f#"$TMP"/}` is a prefix strip rather than a basename and the
# two differ only on that file. The `*/stable/` entries exist because the twin's rewrite loops DOWNLOAD them back out of stable after the recursive copy has already overwritten them.
DEFAULT_BUCKET = {
    "cli/edge/rdc-linux-x64": "rdc binary bytes\n",
    "cli/edge/manifest.json": '{"version":"1.2.3"}\n',
    "cli/edge/latest.json": '{"latest":"1.2.3"}\n',
    "cli/edge/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/edge/install.ps1": '$c = if ($e) { "edge" } else { "edge" }\n',
    "apt/edge/rdc.deb": "deb bytes\n",
    "apt/edge/dists/stable/Packages.gz": "packages body\n",
    "apt/edge/InRelease": "inrelease body\n",
    "rpm/edge/rdc.rpm": "rpm bytes\n",
    "rpm/edge/repodata/repomd.xml": "repomd body\n",
    "rpm/edge/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/edge/\n",
    "apk/edge/rdc.apk": "apk bytes\n",
    "apk/edge/APKINDEX.tar.gz": "apkindex body\n",
    "archlinux/edge/rdc.pkg.tar.zst": "pkg bytes\n",
    "archlinux/edge/rediacc.conf": "[rediacc]\nServer = https://releases.rediacc.com/archlinux/edge/\n",
    "rpm/stable/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/edge/\n",
    "archlinux/stable/rediacc.conf": (
        "[rediacc]\nServer = https://releases.rediacc.com/archlinux/edge/\n"
    ),
    "cli/stable/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/stable/install.ps1": '$c = if ($e) { "edge" } else { "edge" }\n',
}

FAKE_AWS = r'''#!/usr/bin/python3
"""A MODEL of `aws s3 cp/sync`, not the AWS CLI. See the test module docstring.

Logs every argv. For an upload it logs the destination key and the file's
CONTENT, which is the only way the channel rewrites are visible. Serves and
stores objects under $FAKE_S3_ROOT/<bucket>/<key>.

A DOWNLOAD models the two aws-cli properties the resumable stage rests on (#a8d1d6d0, driven against aws-cli 2.36.40): a downloaded file is stamped with the object's mtime truncated to whole seconds, and a download-direction `sync` skips a same-size local file that is not newer than the object. $FAKE_GET_LOG, when set, receives one `GET` line per object actually fetched. $FAKE_AWS_BREAK_KEY breaks that key's read
for the first $FAKE_AWS_BREAK_TIMES fetches (counted in $FAKE_AWS_BREAK_COUNTER): the file is left absent, as aws leaves it, the other files still transfer, and the call exits 1.
"""
import fnmatch
import os
import shutil
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
root = os.environ["FAKE_S3_ROOT"]


def emit(text):
    with open(log, "a") as fh:
        fh.write(text)


emit("aws\t" + "\t".join(argv) + "\n")

with open(log) as fh:
    call_index = len([line for line in fh if line.startswith("aws\t")])
rc = int(os.environ.get("FAKE_AWS_RC", "0"))
fail_on = os.environ.get("FAKE_AWS_FAIL_ON_CALL", "")
# Every call from this index on fails: the shape of a credential that expires mid-run.
fail_from = int(os.environ.get("FAKE_AWS_FAIL_FROM_CALL", "0") or "0")
if rc or (fail_on and str(call_index) == fail_on) or (fail_from and call_index >= fail_from):
    sys.stderr.write(
        os.environ.get("FAKE_AWS_STDERR", "fatal error: An error occurred (AccessDenied)\n")
    )
    sys.exit(rc or 1)


def is_s3(path):
    return path.startswith("s3://")


def local(path):
    return os.path.join(root, path[5:]) if is_s3(path) else path


verb = argv[1] if len(argv) > 1 else ""
valued = {"--endpoint-url", "--cache-control", "--exclude", "--include"}
consumed = set()
rules = []
for i, a in enumerate(argv):
    if a in valued and i + 1 < len(argv):
        consumed.add(i + 1)
        if a in ("--exclude", "--include"):
            rules.append((a[2:], argv[i + 1]))
positional = [a for i, a in enumerate(argv[2:], start=2) if not a.startswith("-") and i not in consumed]
src, dst = positional[0], positional[1]
recursive = "--recursive" in argv or verb == "sync"
download = is_s3(src) and not is_s3(dst)
get_log = os.environ.get("FAKE_GET_LOG", "")
break_key = os.environ.get("FAKE_AWS_BREAK_KEY", "")
break_times = int(os.environ.get("FAKE_AWS_BREAK_TIMES", "0") or "0")
broken = []


def fetched(key, note=""):
    if get_log:
        with open(get_log, "a") as fh:
            fh.write("GET\t%s%s\n" % (key, note))


def breaks(key):
    if key != break_key:
        return False
    counter = os.environ["FAKE_AWS_BREAK_COUNTER"]
    done = int(open(counter).read()) if os.path.exists(counter) else 0
    if done >= break_times:
        return False
    with open(counter, "w") as fh:
        fh.write(str(done + 1))
    return True


def keep(full, base):
    """awscli joins each pattern to the source root and fnmatches the FULL path;
    the LAST matching rule wins and the default is include."""
    verdict = True
    for kind, pattern in rules:
        if fnmatch.fnmatch(full, os.path.join(base, pattern)):
            verdict = kind == "include"
    return verdict


def store(source_path, target_path):
    if download:
        key = source_path[len(root) + 1:]
        if verb == "sync" and os.path.isfile(target_path):
            have, want = os.stat(target_path), os.stat(source_path)
            if have.st_size == want.st_size and have.st_mtime <= want.st_mtime:
                return
        if breaks(key):
            fetched(key, "\tBROKEN")
            broken.append(key)
            sys.stderr.write(
                "download failed: s3://%s to %s ('Connection broken: IncompleteRead(4 bytes read, "
                "4 more expected)', IncompleteRead(4 bytes read, 4 more expected))\n"
                % (key, target_path)
            )
            return
        fetched(key)
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    shutil.copyfile(source_path, target_path)
    if download:
        stamp = int(os.stat(source_path).st_mtime)
        os.utime(target_path, (stamp, stamp))
    if is_s3(dst):
        with open(source_path) as fh:
            emit("UPLOAD\t%s\nCONTENT<<<%s>>>\n" % (target_path[len(root) + 1:], fh.read()))


if recursive:
    base = local(src).rstrip("/")
    if not os.path.isdir(base):
        # A LOCAL SOURCE THAT DOES NOT EXIST is an error; an S3 PREFIX with no
        # keys is not, it simply copies nothing and creates no directory.
        if is_s3(src):
            sys.exit(0)
        sys.stderr.write("fatal error: the user-provided path %s does not exist.\n" % src)
        sys.exit(1)
    pairs = []
    for dirpath, _dirs, files in os.walk(base):
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            pairs.append((full, os.path.relpath(full, base)))
    for full, rel in sorted(pairs, key=lambda pair: pair[1]):
        if rules and not keep(full, base):
            continue
        store(full, os.path.join(local(dst).rstrip("/"), rel))
    if broken:
        sys.exit(1)
else:
    source_path = local(src)
    if not os.path.isfile(source_path):
        sys.stderr.write("fatal error: An error occurred (404) when calling HeadObject\n")
        sys.exit(1)
    store(source_path, local(dst))
sys.exit(0)
'''

FAKE_CURL = """#!/usr/bin/python3
import json
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(sys.argv[1:]) + "\\n")

rc = int(os.environ.get("FAKE_CURL_RC", "0"))
if rc:
    sys.stderr.write("curl: (6) Could not resolve host: api.cloudflare.com\\n")
    sys.exit(rc)
sys.stdout.write(json.dumps({"success": True, "errors": []}) + "\\n")
"""

# Every real binary either side reaches for. `find` and `sed` are called by BOTH implementations (the port shells out to the same two, for the reasons in its docstring); `jq` belongs to cf-purge-urls.sh; `uname`, `dirname`, `basename` and `tr` are what the twin and common.sh need. Nothing else is on the scratch PATH, so a tool leaking in would show up as a behaviour change.
PATH_MINIMUM = ("jq", "uname", "dirname", "basename", "tr", "find", "wc", "sed", "rm")


def _clean_fixed_tmp() -> None:
    """Remove the seven paths the twin hard-codes.

    NOT TIDINESS. A leftover `/tmp/promote-apk` is promoted to `stable/` by the next run (`STALE_TMP_IS_PROMOTED`), so without this a failed case would silently change the meaning of every case after it, and the second side of a comparison would start from a different state than the first.
    """
    for path in FIXED_TMP_PATHS:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def _bin(root: pathlib.Path, *, drop: str = "", aws_body: str = FAKE_AWS) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name, body in (("aws", aws_body), ("curl", FAKE_CURL)):
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
    """A throwaway repository holding both implementations, plus a bucket.

    BOTH SIDES ARE COPIED IN rather than invoked from this checkout, because each resolves `cf-purge-urls.sh` from its own location. A test that ran the real files would drive them against the real tree.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "deploy").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(PURGE, root / ".ci" / "scripts" / "deploy" / PURGE.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(PORT_FILE, root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name)

    for side in ("old", "new"):
        base = root / f"{side}-s3" / port.BUCKET
        for key, body in (DEFAULT_BUCKET if bucket is None else bucket).items():
            target = base / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        base.mkdir(parents=True, exist_ok=True)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    aws_body: str = FAKE_AWS,
    pre: typing.Callable[[], None] | None = None,
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    _clean_fixed_tmp()
    if pre is not None:
        pre()
    env = {
        "PATH": _bin(root, drop=drop, aws_body=aws_body),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
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
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name)]
    proc = subprocess.run(
        argv,
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, bucket: dict[str, str] | None = None, **kw):
    """BOTH SIDES RUN AGAINST ONE FIXTURE REPO but SEPARATE bucket copies.

    Separate buckets because this script MUTATES what it reads: the rewrite loops download `cli/stable/install.sh` back out after the recursive copy overwrote it, so a shared bucket would hand the second side a body the first side had already rewritten and the comparison would be of two different inputs.
    """
    root = fixture(tmp_path, bucket)
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    return root, old, new, old_calls, new_calls


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """THE THREE STREAMS ARE COMPARED SEPARATELY, plus the call log.

    Never `2>&1`: a message moving between stdout and stderr is invisible once the two are merged, and that is the defect class these files exist for.
    """
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}\n"
        f"old stderr: {old.stderr!r}\nnew stderr: {new.stderr!r}"
    )
    assert new.stdout == old.stdout, f"{label}: stdout diverged:\n{old.stdout!r}\n{new.stdout!r}"
    assert new.stderr == old.stderr, f"{label}: stderr diverged:\n{old.stderr!r}\n{new.stderr!r}"
    expected = _with_the_stamp(_with_the_resumable_download(old_calls))
    assert new_calls == expected, f"{label}: call log diverged:\n{expected}\n---\n{new_calls}"


# RULE T DELTA (#b22efec4). The twin's recursive copy uploads the EDGE-defaulted installers and channel configs to `stable/` and only re-bakes them in a later loop, so a run that dies in between leaves production installing edge. The port stamps the staged copy BEFORE any upload. That is the ONE permitted difference in the call log: the CONTENT of these four keys' uploads, never an argv.
STABLE_POINTERS = {
    "rediacc-releases/cli/stable/install.sh": ("REDIACC_CHANNEL:-stable", "REDIACC_CHANNEL:-edge"),
    "rediacc-releases/cli/stable/install.ps1": ('} else { "stable" }', '} else { "edge" }'),
    "rediacc-releases/rpm/stable/rediacc.repo": ("/rpm/stable/", "/edge/"),
    "rediacc-releases/archlinux/stable/rediacc.conf": ("/archlinux/stable/", "/edge/"),
}

UPLOAD_RE = re.compile(r"UPLOAD\t(.*?)\nCONTENT<<<(.*?)>>>\n", re.DOTALL)

# What `aws` printed on 2026-09-24 when a large .deb broke mid-read (M-live item 10): the transient class the retry exists for.
INCOMPLETE_READ = (
    "download failed: s3://rediacc-releases/apt/edge/pool/x.deb to /tmp/promote-apt/pool/x.deb "
    "('Connection broken: IncompleteRead(7540288 bytes read, 848320 more expected)', "
    "IncompleteRead(7540288 bytes read, 848320 more expected))\n"
)


# RULE T DELTA (#a8d1d6d0), the one permitted ARGV difference: the twin stages each `<dir>/edge/` with `aws s3 cp --recursive`, the port with `port.DOWNLOAD_VERB` and no `--recursive`, so a retried download fetches only what is still missing. Each entry is (twin token, port token); `None` drops the token. Applied to the twin's call log before it is compared, and to nothing else.
RESUMABLE_DOWNLOAD_DELTA: tuple[tuple[str, str | None], ...] = (
    ("cp", port.DOWNLOAD_VERB),
    ("--recursive", None),
)


def _is_stage_download(fields: list[str]) -> bool:
    return (
        fields[:3] == ["aws", "s3", "cp"]
        and len(fields) > 4
        and fields[3].endswith("/edge/")
        and fields[4].startswith(port.TMP_PREFIX)
    )


def _with_the_resumable_download(calls: str) -> str:
    """The twin's call log with each staging download rewritten into the port's resumable form, per `RESUMABLE_DOWNLOAD_DELTA`."""
    lines = []
    for line in calls.split("\n"):
        fields = line.split("\t")
        if _is_stage_download(fields):
            for twin_token, port_token in RESUMABLE_DOWNLOAD_DELTA:
                at = fields.index(twin_token)
                if port_token is None:
                    del fields[at]
                else:
                    fields[at] = port_token
        lines.append("\t".join(fields))
    return "\n".join(lines)


def _gets(path: pathlib.Path, prefix: str) -> dict[str, int]:
    """How many times the fake FETCHED each key under `prefix` (a broken read counts)."""
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        key = line.split("\t")[1]
        if key.startswith(prefix):
            counts[key] = counts.get(key, 0) + 1
    return counts


def _uploads(calls: str) -> list[tuple[str, str]]:
    """Every (key, content) the fake stored, in upload order."""
    return UPLOAD_RE.findall(calls)


def _with_the_stamp(calls: str) -> str:
    """The twin's call log with the stable default stamped into the four channel-pointer uploads, which is what the port uploads instead."""

    def stamp(match: re.Match[str]) -> str:
        key, content = match.group(1), match.group(2)
        if key in STABLE_POINTERS:
            content = content.replace("REDIACC_CHANNEL:-edge", "REDIACC_CHANNEL:-stable")
            content = content.replace('} else { "edge" }', '} else { "stable" }')
            if key.endswith((".repo", ".conf")):
                content = content.replace("/edge/", "/stable/")
        return "UPLOAD\t%s\nCONTENT<<<%s>>>\n" % (key, content)

    return UPLOAD_RE.sub(stamp, calls)


def _urls(calls: str) -> list[str]:
    """The purge body, as the list of URLs it carried."""
    for line in calls.splitlines():
        if line.startswith("curl\t") and "--data" in line:
            fields = line.split("\t")
            return json.loads(fields[fields.index("--data") + 1])["files"]
    return []


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_happy_path_agrees_on_both_streams_and_every_call(tmp_path) -> None:
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "happy", old_calls, new_calls)

    assert old.returncode == 0, old.stderr
    assert old.stdout.splitlines()[:6] == [
        "Promoting cli/edge/ -> cli/stable/",
        "Promoting apt/edge/ -> apt/stable/",
        "Promoting rpm/edge/ -> rpm/stable/",
        "Promoting apk/edge/ -> apk/stable/",
        "Promoting archlinux/edge/ -> archlinux/stable/",
        "R2 promoted to stable",
    ], old.stdout
    assert old.stderr == ""

    # PRINT THE SHAPE: ten channel copies (two per directory), four config fetch/put pairs, and one purge. A collapse in any of those numbers is what a "they both printed the same six lines" comparison would miss.
    aws_calls = [line for line in old_calls.splitlines() if line.startswith("aws\t")]
    assert len(aws_calls) == 18, aws_calls
    assert len([line for line in old_calls.splitlines() if line.startswith("curl\t")]) == 1


def test_the_channel_rewrites_reach_the_uploaded_bytes(tmp_path) -> None:
    """THE CONTENT LOG IS THE ONLY WITNESS to the rewrites.

    Both sides print an identical six-line success whether or not the `sed` ran.
    """
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "rewrite", old_calls, new_calls)

    assert 'CONTENT<<<#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n>>>' in old_calls
    assert 'CONTENT<<<$c = if ($e) { "edge" } else { "stable" }\n>>>' in old_calls
    assert "baseurl=https://releases.rediacc.com/rpm/stable/" in old_calls
    assert "Server = https://releases.rediacc.com/archlinux/stable/" in old_calls


def test_no_upload_ever_carries_an_edge_default_to_stable(tmp_path) -> None:
    """#b22efec4: EVERY upload of a stable channel pointer carries the stable default, including the recursive copy's.

    The twin's recursive copy puts the edge body on `stable/` first and fixes it one loop later; that window is how production came to install edge.
    """
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "stamp", old_calls, new_calls)

    seen = set()
    for key, content in _uploads(new_calls):
        if key in STABLE_POINTERS:
            good, bad = STABLE_POINTERS[key]
            assert good in content, (key, content)
            assert bad not in content, (key, content)
            seen.add(key)
    assert seen == set(STABLE_POINTERS), seen
    # The twin's window, reproduced so the delta stays visible.
    assert any(
        k == "rediacc-releases/cli/stable/install.sh" and "REDIACC_CHANNEL:-edge" in c
        for k, c in _uploads(old_calls)
    )


def test_a_run_that_dies_after_the_cli_upload_leaves_the_stable_default_in_place(tmp_path) -> None:
    """THE 2026-09-24 INCIDENT. Call 1 downloads cli/edge, call 2 uploads cli/stable, call 3 (apt) and everything after fails: the credential expired.

    The twin leaves `cli/stable/install.sh` defaulting to edge, because the re-bake loop never runs. The port stamped before uploading, so what is on stable is right however far the run got.
    """
    root, old, new, _old_calls, _new_calls = run_both(
        tmp_path, FAKE_AWS_FAIL_FROM_CALL="3", PROMOTE_RETRY_DELAY_S="0"
    )
    assert old.returncode == new.returncode == 1, (old.stderr, new.stderr)
    stable = "rediacc-releases/cli/stable/"
    twin_sh = (root / "old-s3" / stable / "install.sh").read_text(encoding="utf-8")
    port_sh = (root / "new-s3" / stable / "install.sh").read_text(encoding="utf-8")
    port_ps1 = (root / "new-s3" / stable / "install.ps1").read_text(encoding="utf-8")
    assert "REDIACC_CHANNEL:-edge" in twin_sh, twin_sh
    assert "REDIACC_CHANNEL:-stable" in port_sh, port_sh
    assert '} else { "stable" }' in port_ps1, port_ps1


def test_an_installer_the_stamp_cannot_reach_is_refused_before_any_upload(tmp_path) -> None:
    """A template whose default the substitution does not recognise would reach stable still pointing at edge, with sed exiting 0. The port refuses instead."""
    bucket = dict(DEFAULT_BUCKET)
    bucket["cli/edge/install.sh"] = '#!/bin/sh\n: "${REDIACC_CHANNEL:=edge}"\n'
    root = fixture(tmp_path, bucket)
    new, new_calls = _run(root, "new")
    assert new.returncode == 1, new.stderr
    assert "install.sh" in new.stderr, new.stderr
    assert "stable" in new.stderr, new.stderr
    assert "UPLOAD" not in new_calls, new_calls


def test_a_nested_file_keeps_its_directories_in_the_purge_url(tmp_path) -> None:
    """`${f#"$TMP"/}` is a PREFIX STRIP, not a basename."""
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "nested", old_calls, new_calls)
    assert "https://releases.rediacc.com/apt/stable/dists/stable/Packages.gz" in _urls(old_calls), (
        _urls(old_calls)
    )


# --------------------------------------------------------------------------- The three named facts ---------------------------------------------------------------------------


def test_defect_purge_list_contains_duplicates(tmp_path) -> None:
    """FOUR URLS ARE POSTED TWICE on the ordinary path.

    Each channel-pointer file is appended once by the `find` loop (the recursive copy carried it) and once by the rewrite loop that follows. Cloudflare batches at 30, so a duplicate is a slot spent twice. Reproduced, not repaired.
    """
    assert port.PURGE_LIST_CONTAINS_DUPLICATES is True

    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "duplicates", old_calls, new_calls)

    urls = _urls(old_calls)
    duplicated = sorted({u for u in urls if urls.count(u) > 1})
    assert duplicated == [
        "https://releases.rediacc.com/archlinux/stable/rediacc.conf",
        "https://releases.rediacc.com/cli/stable/install.ps1",
        "https://releases.rediacc.com/cli/stable/install.sh",
        "https://releases.rediacc.com/rpm/stable/rediacc.repo",
    ], duplicated
    assert len(urls) == len(set(urls)) + 4, urls


def _without_url(calls: str, url: str) -> str:
    """`calls` with `url` taken out of the purge body, re-serialised the way cf-purge-urls.sh's `jq -c` writes it."""
    lines = []
    for line in calls.split("\n"):
        if line.startswith("curl\t") and "--data" in line:
            fields = line.split("\t")
            at = fields.index("--data") + 1
            body = json.loads(fields[at])
            body["files"] = [u for u in body["files"] if u != url]
            fields[at] = json.dumps(body, separators=(",", ":"))
            lines.append("\t".join(fields))
            continue
        lines.append(line)
    return "\n".join(lines)


def test_defect_stale_tmp_is_promoted_by_the_twin_and_not_by_the_port(tmp_path) -> None:
    """A LEFTOVER `/tmp/promote-apk` REACHES `apk/stable/` ON THE TWIN'S NEXT RUN.

    `rm -rf "$TMP"` is the last statement of the loop body, so an early exit leaves the directory behind and the following run copies INTO it and then uploads the whole thing. Driven here by planting the leftover directly, which is the state a cancelled workflow or a failed `aws` leaves.

    RULE T DELTA (#a8d1d6d0): the port empties the stage before its first download, which its resumable `sync` needs (a same-size older leftover would otherwise be kept), so the leftover never reaches stable. Every other call and both streams still agree.
    """
    assert port.STALE_TMP_IS_PROMOTED is False

    def plant() -> None:
        stale = port.TMP_PREFIX + "apk"
        os.makedirs(stale, exist_ok=True)
        with open(os.path.join(stale, "old-0.0.1.apk"), "w", encoding="utf-8") as fh:
            fh.write("bytes from a run that died\n")

    _root, old, new, old_calls, new_calls = run_both(tmp_path, pre=plant)
    assert old.returncode == new.returncode == 0, (old.stderr, new.stderr)
    # The purge script counts the URLs it posts; the port posts one fewer, the leftover's.
    posted = len(_urls(old_calls))
    assert new.stdout == old.stdout.replace("%d URL(s)" % posted, "%d URL(s)" % (posted - 1))
    assert old.stderr == new.stderr
    assert "UPLOAD\trediacc-releases/apk/stable/old-0.0.1.apk" in old_calls
    assert "https://releases.rediacc.com/apk/stable/old-0.0.1.apk" in _urls(old_calls)
    assert "old-0.0.1.apk" not in new_calls, new_calls
    # Without the leftover's upload and URL, the two logs are the same.
    twin = _with_the_stamp(_with_the_resumable_download(old_calls))
    twin = twin.replace(
        "UPLOAD\trediacc-releases/apk/stable/old-0.0.1.apk\nCONTENT<<<bytes from a run that died\n>>>\n",
        "",
    )
    twin = _without_url(twin, "https://releases.rediacc.com/apk/stable/old-0.0.1.apk")
    assert new_calls == twin, f"{twin}\n---\n{new_calls}"


def test_defect_the_vacuity_floor_runs_after_the_upload(tmp_path) -> None:
    """THE FLOOR NEEDS A LEFTOVER EMPTY DIRECTORY TO BE REACHABLE AT ALL.

    Order is download, upload, then count. With `cli/edge/` empty the download creates nothing, so it is the UPLOAD that fails first and the floor's own sentence never prints. The floor fires only when `$TMP` exists and is empty, which the previous test shows is a real state. Both halves are driven and both agree.
    """
    assert port.VACUITY_FLOOR_RUNS_AFTER_THE_UPLOAD is False  # Rule T delta: the port counts first

    empty = {k: v for k, v in DEFAULT_BUCKET.items() if not k.startswith("cli/edge/")}

    # (a) no leftover: aws refuses the TWIN's upload and its floor never speaks; the port refuses by name before uploading.
    _root, old, new, old_calls, new_calls = run_both(
        tmp_path / "a", empty, PROMOTE_RETRY_DELAY_S="0"
    )
    assert old.returncode == new.returncode == 1
    assert "VACUOUS" not in old.stderr, old.stderr
    assert "does not exist" in old.stderr, old.stderr
    assert "VACUOUS: cli staged 0 file(s)" in new.stderr, new.stderr
    assert "cli/stable/" not in new_calls, new_calls

    # (b) an empty leftover: the upload succeeds having moved nothing, and the floor is what stops the run.
    def plant() -> None:
        os.makedirs(port.TMP_PREFIX + "cli", exist_ok=True)

    _root, old, new, old_calls, new_calls = run_both(tmp_path / "b", empty, pre=plant)
    # Same verdict and words; only the port skips the twin's empty upload.
    assert new.returncode == old.returncode
    assert new.stderr == old.stderr
    assert new.stdout == old.stdout
    assert "cli/stable/" in old_calls, old_calls
    assert "cli/stable/" not in new_calls, new_calls
    assert old.returncode == 1
    assert old.stderr == (
        "VACUOUS: cli staged 0 file(s) for promotion; refusing to report a "
        "promotion that moved nothing\n"
    ), repr(old.stderr)
    assert old.stdout == "Promoting cli/edge/ -> cli/stable/\n"


# --------------------------------------------------------------------------- Refusals and failures ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
    ],
)
def test_each_required_variable_refuses_with_the_same_status(tmp_path, missing) -> None:
    """THE ONE NAMED DIVERGENCE, and it is in text nobody parses.

    bash's `${VAR:?msg}` prefixes the message with the script path and a line
    number; the port prints the `VAR: msg` half. Same stream, same status, no call made. Both are asserted here rather than compared byte for byte.
    """
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old", drop_env=(missing,))
    new, new_calls = _run(root, "new", drop_env=(missing,))

    assert old.returncode == 1, old.stderr
    assert new.returncode == 1, new.stderr
    assert old.stdout == ""
    assert new.stdout == ""
    assert old_calls == "", "a refused run still called aws"
    assert new_calls == "", "a refused run still called aws"
    tail = "%s: %s: %s must be set\n" % (missing, port.SELF, missing)
    assert old.stderr.endswith(tail), repr(old.stderr)
    assert new.stderr == tail, repr(new.stderr)


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port checking `in os.environ` would sail past this and then hand `aws` an `--endpoint-url` with no value."""
    root = fixture(tmp_path)
    old, _ = _run(root, "old", CLOUDFLARE_R2_ENDPOINT="")
    new, _ = _run(root, "new", CLOUDFLARE_R2_ENDPOINT="")
    assert old.returncode == 1, old.stderr
    assert new.returncode == 1, new.stderr
    assert old.stderr.endswith(
        "CLOUDFLARE_R2_ENDPOINT: %s: CLOUDFLARE_R2_ENDPOINT must be set\n" % port.SELF
    )
    assert new.stderr == (
        "CLOUDFLARE_R2_ENDPOINT: %s: CLOUDFLARE_R2_ENDPOINT must be set\n" % port.SELF
    )


def test_a_missing_aws_refuses_before_the_variable_guards(tmp_path) -> None:
    """ORDER IS OBSERVABLE: a run missing both the binary and every variable names the binary."""
    root = fixture(tmp_path)
    kw = {"drop": "aws", "drop_env": tuple(BASE_ENV)}
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    _agree(old, new, "no-aws", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n", repr(old.stderr)


def test_one_transient_aws_failure_stops_the_twin_but_the_port_retries_through_it(tmp_path) -> None:
    """RULE T DELTA (#4175e786). Call 4 fails once. The twin, unguarded under `set -e`, stops half-done; the port repeats the idempotent transfer, says so on stderr, and completes."""
    _root, old, new, old_calls, _new_calls = run_both(
        tmp_path,
        FAKE_AWS_FAIL_ON_CALL="4",
        FAKE_AWS_STDERR=INCOMPLETE_READ,
        PROMOTE_RETRY_DELAY_S="0",
    )
    assert old.returncode == 1
    assert old.stderr == INCOMPLETE_READ
    assert old.stdout == (
        "Promoting cli/edge/ -> cli/stable/\nPromoting apt/edge/ -> apt/stable/\n"
    ), old.stdout
    assert "curl" not in old_calls, "a failed promotion still purged"
    assert new.returncode == 0, new.stderr
    assert "failed (exit 1), retrying (2/3)" in new.stderr, new.stderr


def test_a_persistent_aws_failure_stops_both_sides(tmp_path) -> None:
    """A transient failure the retry cannot outlast still stops the port, after three tries, with aws's status and nothing purged."""
    _root, old, new, old_calls, new_calls = run_both(
        tmp_path, FAKE_AWS_RC="1", FAKE_AWS_STDERR=INCOMPLETE_READ, PROMOTE_RETRY_DELAY_S="0"
    )
    assert old.returncode == new.returncode == 1
    assert new.stderr.count("retrying (") == 2, new.stderr
    assert "curl" not in old_calls
    assert "curl" not in new_calls


def test_access_denied_is_fatal_on_the_first_try(tmp_path) -> None:
    """#b22efec4: an expired or wrong credential does not heal in ten seconds, so retrying it only repeats the refusal and delays the verdict."""
    root = fixture(tmp_path)
    new, new_calls = _run(root, "new", FAKE_AWS_RC="1", PROMOTE_RETRY_DELAY_S="0")
    assert new.returncode == 1
    assert "retrying (" not in new.stderr, new.stderr
    assert "AccessDenied" in new.stderr, new.stderr
    assert "not retrying" in new.stderr, new.stderr
    assert len([ln for ln in new_calls.splitlines() if ln.startswith("aws\t")]) == 1, new_calls


def test_an_unset_zone_becomes_an_empty_argument_and_the_purge_refuses(tmp_path) -> None:
    """`--zone "${CLOUDFLARE_ZONE_ID:-}"` and NOT `:?`.

    The promotion has already happened by then, which the twin's header says is deliberate. The refusal is cf-purge-urls.sh's own, and under `pipefail` its status becomes this script's, AFTER the success line.
    """
    _root, old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("CLOUDFLARE_ZONE_ID",))
    _agree(old, new, "no-zone", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stdout.rstrip("\n").endswith("R2 promoted to stable")
    assert "--zone <ZONE_ID> is required" in old.stderr
    assert "curl" not in old_calls


def test_no_cloudflare_credential_warns_and_still_exits_zero(tmp_path) -> None:
    _root, old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("CLOUDFLARE_API_TOKEN",))
    _agree(old, new, "no-cf-cred", old_calls, new_calls)
    assert old.returncode == 0
    assert "no Cloudflare credentials in env" in old.stderr
    assert "curl" not in old_calls


# --------------------------------------------------------------------------- A retried download resumes (#a8d1d6d0) ---------------------------------------------------------------------------

BROKEN_KEY = "rediacc-releases/rpm/edge/rdc.rpm"


def _download_with_one_broken_read(
    tmp_path, *, revert_to_cp: bool
) -> tuple[typing.Any, dict[str, int]]:
    """Run the port with `rpm/edge/rdc.rpm`'s first read broken, and return what the fake fetched under `rpm/edge/`.

    `revert_to_cp` plants the pre-#a8d1d6d0 download (`cp ... --recursive`) into the fixture's copy of the port: the mutation control.
    """
    root = fixture(tmp_path)
    if revert_to_cp:
        target = root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name
        source = target.read_text(encoding="utf-8")
        plant = source.replace("        DOWNLOAD_VERB,\n", '        "cp",\n', 1).replace(
            '        tmp + "/",\n        *endpoint_args(endpoint),\n        "--only-show-errors",\n    ]',
            '        tmp + "/",\n        *endpoint_args(endpoint),\n        "--recursive",\n'
            '        "--only-show-errors",\n    ]',
            1,
        )
        assert plant.count('"--recursive"') == source.count('"--recursive"') + 1, (
            "the plant did not apply; the control is broken, not the test"
        )
        target.write_text(plant, encoding="utf-8")
    gets = root / "gets.log"
    new, _calls = _run(
        root,
        "new",
        PROMOTE_RETRY_DELAY_S="0",
        FAKE_GET_LOG=str(gets),
        FAKE_AWS_BREAK_KEY=BROKEN_KEY,
        FAKE_AWS_BREAK_TIMES="1",
        FAKE_AWS_BREAK_COUNTER=str(root / "breaks"),
    )
    assert new.returncode == 0, new.stderr
    assert "download of rpm/edge failed (exit 1), retrying (2/3)" in new.stderr, new.stderr
    return new, _gets(gets, "rediacc-releases/rpm/edge/")


def _only_the_broken_file_was_fetched_again(gets: dict[str, int]) -> bool:
    others = {k: n for k, n in gets.items() if k != BROKEN_KEY}
    return gets.get(BROKEN_KEY) == 2 and len(others) >= 2 and set(others.values()) == {1}


def test_a_retried_download_fetches_only_what_the_broken_attempt_left_missing(tmp_path) -> None:
    """THE 2026-09-25 FAILURE. `rpm/edge` failed 3/3 because every retry fetched the whole directory again and drew a fresh broken read. The port's second attempt fetches the one file the first left absent and nothing else."""
    assert port.DOWNLOAD_IS_RESUMABLE is True
    _new, gets = _download_with_one_broken_read(tmp_path, revert_to_cp=False)
    assert _only_the_broken_file_was_fetched_again(gets), gets


def test_mutation_control_a_cp_recursive_download_refetches_everything(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: the same run with the download reverted to `cp --recursive` fetches every `rpm/edge` file twice, and the resume check rejects it."""
    _new, gets = _download_with_one_broken_read(tmp_path, revert_to_cp=True)
    assert not _only_the_broken_file_was_fetched_again(gets), gets
    assert set(gets.values()) == {2}, gets


# --------------------------------------------------------------------------- The transfer plan is the twin's ---------------------------------------------------------------------------

# PRODUCTION'S SHAPE, which the default fixture lacks: every `<dir>/stable/` already holds the release history (on 2026-09-25 about 67 GB across the five trees, a ~400 MB package per old version). A download prefix wider than `<dir>/edge/` would fetch that history too, and the default fixture has nothing outside `edge/` for it to find.
HISTORY_KEYS = tuple("%s/stable/history-0.0.1.pkg" % d for d in port.CHANNEL_DIRS)
HISTORY_BUCKET = {**DEFAULT_BUCKET, **dict.fromkeys(HISTORY_KEYS, "old release bytes\n")}

# The only non-edge objects the twin fetches: the four channel pointers its rewrite loops download back out of `stable/`.
POINTER_KEYS = tuple(
    "%s/%s" % (port.BUCKET, key) for key in (*port.CONFIG_FILES, *port.INSTALL_FILES)
)


def _transfer_plan(tmp_path, *, widen: bool = False):
    """Both sides against the history bucket, returning (old, new, old_gets, new_gets, old_puts, new_puts).

    `widen` plants the regression this pins: the stage download reading `<dir>/` instead of `<dir>/edge/`.
    """
    root = fixture(tmp_path, HISTORY_BUCKET)
    if widen:
        target = root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name
        source = target.read_text(encoding="utf-8")
        plant = source.replace(
            '"s3://%s/%s/edge/" % (BUCKET, dir_name)', '"s3://%s/%s/" % (BUCKET, dir_name)', 1
        )
        assert plant != source, "the plant did not apply; the control is broken, not the test"
        target.write_text(plant, encoding="utf-8")
    old_log, new_log = root / "old-gets.log", root / "new-gets.log"
    old, old_calls = _run(root, "old", FAKE_GET_LOG=str(old_log))
    new, new_calls = _run(root, "new", PROMOTE_RETRY_DELAY_S="0", FAKE_GET_LOG=str(new_log))
    bucket = port.BUCKET + "/"
    return (
        old,
        new,
        _gets(old_log, bucket),
        _gets(new_log, bucket),
        sorted(key for key, _ in _uploads(old_calls)),
        sorted(key for key, _ in _uploads(new_calls)),
    )


def _per_tree(gets: dict[str, int]) -> dict[str, dict[str, int]]:
    """The fetch counts grouped by channel directory, so a failure names the tree that moved more."""
    trees: dict[str, dict[str, int]] = {d: {} for d in port.CHANNEL_DIRS}
    for key, count in gets.items():
        trees[key.split("/")[1]][key] = count
    return trees


def test_the_port_fetches_and_uploads_exactly_what_the_twin_does(tmp_path) -> None:
    """THE 2026-09-25 QUESTION: does the port move more than the bash twin? Per tree, the same objects, each fetched once, and the same uploads.

    Both sides stage `<dir>/edge/` and nothing else, plus the four pointers the rewrite loops read back. The live runs took hours on BOTH sides (the twin 4h12m on 2026-09-24) because that tree is the whole release history, not because the port reads more of it.
    """
    old, new, old_gets, new_gets, old_puts, new_puts = _transfer_plan(tmp_path)
    assert old.returncode == 0, old.stderr
    assert new.returncode == 0, new.stderr
    assert _per_tree(new_gets) == _per_tree(old_gets)
    edge = {"%s/%s" % (port.BUCKET, key) for key in DEFAULT_BUCKET if "/edge/" in key}
    assert set(old_gets) == edge | set(POINTER_KEYS), sorted(
        set(old_gets) ^ (edge | set(POINTER_KEYS))
    )
    assert set(old_gets.values()) == {1}, old_gets
    assert not any(key.endswith(HISTORY_KEYS) for key in new_gets), new_gets
    assert new_puts == old_puts


def test_mutation_control_a_widened_download_prefix_is_caught(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: a stage download of `<dir>/` fetches `<dir>/stable/` history the twin never reads."""
    _old, _new, old_gets, new_gets, _old_puts, _new_puts = _transfer_plan(tmp_path, widen=True)
    assert _per_tree(new_gets) != _per_tree(old_gets)
    assert "%s/cli/stable/history-0.0.1.pkg" % port.BUCKET in new_gets, new_gets
    assert not any(key.endswith(HISTORY_KEYS) for key in old_gets), old_gets


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, and prove WHICH assertion fires.

    The plant drops `--cache-control no-cache` from the channel upload, which is the mistake the twin's whole Cache-Control paragraph exists to prevent: a cached body under a reused filename breaks APKINDEX and Release signatures. Every printed byte and the exit code are unchanged by it.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    plant = source.replace(
        '        "--recursive",\n        "--only-show-errors",\n        "--cache-control",\n'
        "        CC_MUTABLE,\n",
        '        "--recursive",\n        "--only-show-errors",\n',
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(plant, encoding="utf-8")

    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert new.stdout == old.stdout, "the plant changed stdout; wrong plant"
    assert new.stderr == old.stderr, "the plant changed stderr; wrong plant"
    assert new_calls != _with_the_stamp(_with_the_resumable_download(old_calls)), (
        "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    )
    assert old_calls.count("--cache-control") == new_calls.count("--cache-control") + 5


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_the_directory_order_is_the_twins() -> None:
    assert port.CHANNEL_DIRS == ("cli", "apt", "rpm", "apk", "archlinux")
    assert port.CONFIG_FILES == ("rpm/stable/rediacc.repo", "archlinux/stable/rediacc.conf")
    assert port.INSTALL_FILES == ("cli/stable/install.sh", "cli/stable/install.ps1")


def test_endpoint_args_reproduces_the_unquoted_word_split() -> None:
    assert port.endpoint_args("https://r2.example.invalid") == [
        "--endpoint-url",
        "https://r2.example.invalid",
    ]
    # THE CASE A HARD-CODED PAIR WOULD GET WRONG: bash splits on IFS, so a value
    # with a space really is two more arguments in the twin.
    assert port.endpoint_args("a b") == ["--endpoint-url", "a", "b"]


def test_the_argv_builders_carry_the_twins_flags_in_the_twins_order() -> None:
    ep = "https://r2.example.invalid"
    # RULE T DELTA (#a8d1d6d0): `sync` where the twin says `cp ... --recursive`; see RESUMABLE_DOWNLOAD_DELTA.
    assert port.download_argv("cli", "/tmp/promote-cli", ep) == [
        "aws",
        "s3",
        "sync",
        "s3://rediacc-releases/cli/edge/",
        "/tmp/promote-cli/",
        "--endpoint-url",
        ep,
        "--only-show-errors",
    ]
    assert port.upload_argv("cli", "/tmp/promote-cli", ep)[-2:] == ["--cache-control", "no-cache"]
    assert port.fetch_argv("rpm/stable/rediacc.repo", "/tmp/config", ep)[3] == (
        "s3://rediacc-releases/rpm/stable/rediacc.repo"
    )
    assert port.put_argv("/tmp/config", "rpm/stable/rediacc.repo", ep)[3] == "/tmp/config"


def test_strip_prefix_and_read_lines_follow_bash_rather_than_python() -> None:
    assert port.strip_prefix("/tmp/promote-cli/a/b", "/tmp/promote-cli/") == "a/b"
    # `${f#x}` LEAVES A NON-MATCHING STRING ALONE rather than slicing it.
    assert port.strip_prefix("/elsewhere/a", "/tmp/promote-cli/") == "/elsewhere/a"
    # `read` DROPS a final line with no newline, and Python iteration would not.
    assert port.read_lines("a\nb\n") == ["a", "b"]
    assert port.read_lines("a\nb") == ["a"]
    assert port.read_lines("") == []


def test_the_purge_script_is_still_the_bash_one_and_still_exists() -> None:
    """The cutover has NOT happened, and this is what would notice if it did silently. `PURGE_SCRIPT_RELATIVE` is the one place a cutover box edits."""
    assert port.PURGE_SCRIPT_RELATIVE == ".ci/scripts/deploy/cf-purge-urls.sh"
    assert PURGE.is_file()
    assert port.purge_argv("z")[-2:] == ["--zone", "z"]


def test_every_variable_is_read_with_a_literal_os_environ_get() -> None:
    """THE DIRECT-READ DISCIPLINE, ASSERTED RATHER THAN REMEMBERED.

    `check:ci-python-env-registry` derives a module's inputs from its AST, and a read routed through `dict(os.environ)` or a local alias is invisible to it: the module then declares nothing while depending on four variables. This pins the shape the gate can actually see, in both directions -- every name `environment()` returns must appear as a literal `os.environ.get("NAME"` in the
    source, and there must be no extra ones.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    names = set(port.environment())
    assert names == {
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
        "CLOUDFLARE_ZONE_ID",
        "PROMOTE_RETRY_DELAY_S",
    }
    for name in names:
        assert 'os.environ.get("%s"' % name in source, name

    # THE STRONG HALF: ask THE GATE'S OWN SCANNER, not a substring search. If `check:ci-python-env-registry` cannot derive a name, registering it would be a STALE entry and leaving it out would be an undeclared input, so the two sets must be equal in both directions.
    tree = ast.parse(source, filename=str(PORT_FILE))
    derived = python_env_registry.scan_module(
        str(PORT_FILE),
        tree,
        {str(PORT_FILE): python_env_registry.module_constants(tree)},
        {},
    )
    assert derived == names, f"the gate would derive {sorted(derived)}, not {sorted(names)}"
