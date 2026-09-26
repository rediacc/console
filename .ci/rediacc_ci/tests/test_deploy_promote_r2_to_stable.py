"""Differential: `rediacc_ci.deploy.promote_r2_to_stable` against its twin `.ci/scripts/deploy/promote-r2-to-stable.sh`.

RECORDING FAKES FOR `aws` AND `curl` ON A SCRATCH PATH, INSIDE A FIXTURE REPO, exactly as the hotfix sibling's differential does and for the same reasons. Nothing here reaches R2 or Cloudflare; every case pins a fixture endpoint, bucket and credential. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the
mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS ALMOST THE ONLY EVIDENCE FOR THIS SCRIPT. It prints five `Promoting ...` lines and one closing line, none of them derived from what moved. The ENTIRE observable effect is twelve `aws` invocations and the ordered exclude/include lists they carry, and the ORDER of those invocations is the whole design: metadata after bytes, signatures after the metadata they hash. Two
implementations can print identical stdout while uploading `Release*` before `Packages*`, so `test_the_phase_order_is_bytes_then_metadata_then_signatures` asserts the sequence directly rather than trusting the byte comparison to have covered it.

WHAT THE `aws` FAKE MODELS AND WHAT IT DOES NOT. It is a model of the AWS CLI, not the AWS CLI. `aws` IS NOT INSTALLED IN THIS SANDBOX (`command -v aws` is empty), so nothing here is checked against the real tool. The differential's evidence is independent of that: both implementations go through the SAME fake, so the argv, the exit code and the two streams are real evidence about
the port. The modelled part -- which local files each filtered sync moves -- exists to make the include/exclude arithmetic visible, and the one test that relies on it (`test_defect_phase_filtered_files_are_purged_but_never_uploaded`) says so in its own docstring and rests the load-bearing half on the argv rather than on the model.

`/tmp/promote-<dir>` IS A FIXED PATH IN THE TWIN, so these cases cannot be given a private temporary directory: they clean those exact five paths before every side of every case, and the module carries the same `xdist_group` as the hotfix differential so the two land on the SAME xdist worker and cannot run concurrently.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import promote_r2_to_stable as port
from rediacc_ci.quality import python_env_registry

if typing.TYPE_CHECKING:
    import pathlib

# SHARED WITH THE HOTFIX DIFFERENTIAL ON PURPOSE. Both drive scripts that hard-code `/tmp/promote-<dir>`; the group is what stops them colliding.
#
# WIDENED 2026-09-15 TO `deploy-fixed-tmp`, WHICH NOW ALSO COVERS test_deploy_simulate_promotion.py. Renaming only the other two modules would have split THIS pair and reintroduced, here, the exact collision being fixed there -- the group name is the mutex, so every module sharing a fixed /tmp path has to share one name. The three modules that do are this one, the hotfix
# differential (`/tmp/promote-<dir>`, `/tmp/config`, `/tmp/script`) and the simulate differential (`/tmp/config`).
pytestmark = pytest.mark.xdist_group("deploy-fixed-tmp")

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "promote-r2-to-stable.sh"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "promote_r2_to_stable.py"
BASH = shutil.which("bash") or "/bin/bash"

FIXED_TMP_PATHS = tuple(port.TMP_PREFIX + d for d in port.CHANNEL_DIRS)

BASE_ENV = {
    "AWS_ACCESS_KEY_ID": "akid-fixture",
    "AWS_SECRET_ACCESS_KEY": "secret-fixture",
    "AWS_DEFAULT_REGION": "auto",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "EDGE_VERSION": "1.2.3",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# The bucket fixture. Two entries are there specifically to drive fact 1 in the port's docstring: `cli/edge/latest-linux.yml` matches the shared phase-1 exclude `latest*.yml` and no `cli` phase-2 include, and `rpm/edge/repodata/comps.xml` matches `repodata/*` and no rpm phase-2 include.
DEFAULT_BUCKET = {
    "cli/edge/rdc-linux-x64": "rdc binary bytes\n",
    "cli/edge/manifest.json": '{"version":"1.2.3"}\n',
    "cli/edge/latest.json": '{"latest":"1.2.3"}\n',
    "cli/edge/latest-linux.yml": "version: 1.2.3\n",
    "cli/edge/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/edge/install.ps1": '$c = if ($e) { "edge" } else { "edge" }\n',
    "apt/edge/rdc.deb": "deb bytes\n",
    "apt/edge/InRelease": "inrelease body\n",
    "apt/edge/Packages.gz": "packages body\n",
    "rpm/edge/rdc.rpm": "rpm bytes\n",
    "rpm/edge/repodata/primary.xml.gz": "primary body\n",
    "rpm/edge/repodata/repomd.xml": "repomd body\n",
    "rpm/edge/repodata/comps.xml": "comps body\n",
    "rpm/edge/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/edge/\n",
    "apk/edge/rdc.apk": "apk bytes\n",
    "apk/edge/APKINDEX.tar.gz": "apkindex body\n",
    "archlinux/edge/rdc.pkg.tar.zst": "pkg bytes\n",
    "archlinux/edge/rediacc.db.tar.gz": "db body\n",
    "archlinux/edge/rediacc.conf": (
        "[rediacc]\nServer = https://releases.rediacc.com/archlinux/edge/\n"
    ),
}

# What `aws` printed on 2026-09-24 when a large .deb broke mid-read (M-live item 10): the transient class the retry exists for.
INCOMPLETE_READ = (
    "download failed: s3://rediacc-releases/apt/edge/pool/x.deb to /tmp/promote-apt/pool/x.deb "
    "('Connection broken: IncompleteRead(7540288 bytes read, 848320 more expected)', "
    "IncompleteRead(7540288 bytes read, 848320 more expected))\n"
)

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

PATH_MINIMUM = ("jq", "uname", "dirname", "basename", "tr", "find", "wc", "sed", "rm")


def _clean_fixed_tmp() -> None:
    """Remove the five paths the twin hard-codes.

    NOT TIDINESS. A leftover `/tmp/promote-apk` is promoted to `stable/` by the next run (`STALE_TMP_IS_PROMOTED`), so without this a failed case would silently change the meaning of every case after it.
    """
    for path in FIXED_TMP_PATHS:
        shutil.rmtree(path, ignore_errors=True)


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name, body in (("aws", FAKE_AWS), ("curl", FAKE_CURL)):
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
    """A throwaway repository holding both implementations, plus a bucket per side."""
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
    pre: typing.Callable[[], None] | None = None,
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    _clean_fixed_tmp()
    if pre is not None:
        pre()
    env = {
        "PATH": _bin(root, drop=drop),
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
    """BOTH SIDES RUN AGAINST ONE FIXTURE REPO but SEPARATE bucket copies, so the second side reads what the first side read rather than what it wrote."""
    root = fixture(tmp_path, bucket)
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    return root, old, new, old_calls, new_calls


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """THE THREE STREAMS ARE COMPARED SEPARATELY, plus the call log."""
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}\n"
        f"old stderr: {old.stderr!r}\nnew stderr: {new.stderr!r}"
    )
    assert new.stdout == old.stdout, f"{label}: stdout diverged:\n{old.stdout!r}\n{new.stdout!r}"
    assert new.stderr == old.stderr, f"{label}: stderr diverged:\n{old.stderr!r}\n{new.stderr!r}"
    expected = _with_the_resumable_download(old_calls)
    assert new_calls == expected, f"{label}: call log diverged:\n{expected}\n---\n{new_calls}"


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


def _aws(calls: str) -> list[list[str]]:
    return [line.split("\t")[1:] for line in calls.splitlines() if line.startswith("aws\t")]


def _urls(calls: str) -> list[str]:
    for line in calls.splitlines():
        if line.startswith("curl\t") and "--data" in line:
            fields = line.split("\t")
            return json.loads(fields[fields.index("--data") + 1])["files"]
    return []


# --------------------------------------------------------------------------- The happy path and the phase order ---------------------------------------------------------------------------


def test_happy_path_agrees_on_both_streams_and_every_call(tmp_path) -> None:
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "happy", old_calls, new_calls)

    assert old.returncode == 0, old.stderr
    assert old.stdout.splitlines()[:6] == [
        "Promoting cli/edge/ -> cli/stable/ (2-phase)",
        "Promoting apt/edge/ -> apt/stable/ (2-phase)",
        "Promoting rpm/edge/ -> rpm/stable/ (2-phase)",
        "Promoting apk/edge/ -> apk/stable/ (2-phase)",
        "Promoting archlinux/edge/ -> archlinux/stable/ (2-phase)",
        "R2 promotion complete: edge v1.2.3 -> stable",
    ], old.stdout
    assert old.stderr == ""

    # PRINT THE SHAPE: five downloads, five phase-1 syncs, seven phase-2 syncs (apt and rpm make two each), one purge. A collapse in any of those numbers is what a "they both printed the same six lines" comparison would miss.
    calls = _aws(old_calls)
    assert len(calls) == 17, calls
    assert len([c for c in calls if c[1] == "cp"]) == 5
    assert len([c for c in calls if c[1] == "sync"]) == 12
    assert len([line for line in old_calls.splitlines() if line.startswith("curl\t")]) == 1


def test_the_phase_order_is_bytes_then_metadata_then_signatures(tmp_path) -> None:
    """THE ENTIRE DESIGN OF THIS SCRIPT IS AN ORDER, so the order is asserted.

    A port that emitted the same twelve syncs in a different sequence would pass a stdout comparison and would reintroduce the exact race the twin's header describes: a client seeing `Release` before the `Packages` it hashes.
    """
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "phase-order", old_calls, new_calls)

    apt = [c for c in _aws(old_calls) if any(a == "s3://rediacc-releases/apt/stable/" for a in c)]
    assert len(apt) == 3, apt
    assert "--exclude" in apt[0]
    assert "Packages*" in apt[0]
    assert "--include" not in apt[0], "phase 1 must not re-include the metadata"
    assert apt[1][apt[1].index("--include") + 1] == "Packages*"
    assert apt[2][apt[2].index("--include") + 1] == "Release*"
    assert "InRelease" in apt[2]

    rpm = [c for c in _aws(old_calls) if any(a == "s3://rediacc-releases/rpm/stable/" for a in c)]
    assert len(rpm) == 3, rpm
    assert "repodata/primary*" in rpm[1]
    assert "repodata/repomd.xml*" in rpm[2]
    # THE SIGNING METADATA IS LAST, which is the property that cannot be reordered without breaking a repo mid-promotion.
    assert "repodata/repomd.xml*" not in rpm[1], "2a must not carry 2b's signing metadata"


def test_the_rewrites_happen_before_phase_two_uploads_them(tmp_path) -> None:
    """THE CONTENT LOG IS THE ONLY WITNESS. The twin rewrites the LOCAL copy and then uploads it once; a port that uploaded first and rewrote afterwards would print the same six lines and reintroduce the second race the header names.

    THE INVARIANT IS "BEFORE PHASE 2", NOT "BEFORE PHASE 1", and that was measured rather than assumed. Moving `_rewrite` to sit between phase 1 and phase 2 changes NOTHING observable, because all four rewrite targets (`install.sh`, `install.ps1`, `*.repo`, `*.conf`) are in the phase-1 exclude list and so were never going to be uploaded by phase 1. Driven 2026-09-13: that plant
    left all 25 cases green, and the plant that moves the rewrite past phase 2 reds eight of them. Written down because a reader could otherwise take this case for a guarantee about a position it does not constrain.
    """
    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "rewrites", old_calls, new_calls)

    assert 'CONTENT<<<#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n>>>' in old_calls
    assert 'CONTENT<<<$c = if ($e) { "edge" } else { "stable" }\n>>>' in old_calls
    assert "baseurl=https://releases.rediacc.com/rpm/stable/" in old_calls
    assert "Server = https://releases.rediacc.com/archlinux/stable/" in old_calls
    # AND THE EDGE SPELLING NEVER LEAVES: the rewritten body is the only one uploaded, which is what "before phase 2" means.
    assert "baseurl=https://releases.rediacc.com/rpm/edge/" not in old_calls


def test_an_installer_the_stamp_cannot_reach_is_refused_before_any_upload(tmp_path) -> None:
    """#b22efec4, swept to this sibling. A template whose default the substitution does not recognise would reach stable still pointing at edge, with sed exiting 0. The port refuses before any upload."""
    bucket = dict(DEFAULT_BUCKET)
    bucket["cli/edge/install.sh"] = '#!/bin/sh\n: "${REDIACC_CHANNEL:=edge}"\n'
    root = fixture(tmp_path, bucket)
    new, new_calls = _run(root, "new")
    assert new.returncode == 1, new.stderr
    assert "install.sh" in new.stderr, new.stderr
    assert "stable" in new.stderr, new.stderr
    assert "UPLOAD" not in new_calls, new_calls


def test_a_run_that_dies_after_the_cli_uploads_leaves_the_stable_default_in_place(tmp_path) -> None:
    """#b22efec4, swept to this sibling: calls 1-3 are cli's download and two syncs, call 4 (apt) and everything after fails. The stamp precedes every upload here, so cli/stable is right however far the run got."""
    root, old, new, _old_calls, _new_calls = run_both(
        tmp_path, FAKE_AWS_FAIL_FROM_CALL="4", PROMOTE_RETRY_DELAY_S="0"
    )
    assert old.returncode == new.returncode == 1, (old.stderr, new.stderr)
    for side in ("old", "new"):
        stable = root / f"{side}-s3" / "rediacc-releases" / "cli" / "stable"
        assert "REDIACC_CHANNEL:-stable" in (stable / "install.sh").read_text(encoding="utf-8")
        assert '} else { "stable" }' in (stable / "install.ps1").read_text(encoding="utf-8")


def test_an_absent_rewrite_target_does_not_end_the_run(tmp_path) -> None:
    """`[[ -f "$f" ]] && sed_in_place ...` IS EXEMPT FROM `set -e`.

    The opposite reading is plausible and would make this port refuse a channel the twin publishes, so it is driven rather than reasoned about. All three rewrite targets are removed from the bucket.
    """
    stripped = {
        k: v
        for k, v in DEFAULT_BUCKET.items()
        if os.path.basename(k) not in ("install.sh", "install.ps1", "rediacc.repo", "rediacc.conf")
    }
    _root, old, new, old_calls, new_calls = run_both(tmp_path, stripped)
    _agree(old, new, "no-rewrite-targets", old_calls, new_calls)
    assert old.returncode == 0, old.stderr
    assert old.stdout.splitlines()[5] == "R2 promotion complete: edge v1.2.3 -> stable"


# --------------------------------------------------------------------------- The four named facts ---------------------------------------------------------------------------


def test_defect_phase_filtered_files_are_purged_but_never_uploaded(tmp_path) -> None:
    """A FILE EXCLUDED IN PHASE 1 AND NAMED BY NO PHASE-2 INCLUDE IS DROPPED.

    THE LOAD-BEARING HALF IS THE ARGV, NOT THE FAKE'S FILE MOVING. `cli`'s phase-1 call carries `--exclude latest*.yml` and its single phase-2 call carries `--exclude *` followed by five `--include`s, none of which is a `.yml`; `rpm`'s phase 1 carries `--exclude repodata/*` and neither phase-2 arm names `comps.xml`. Under ANY reading of the filter semantics those two files cannot
    be uploaded, and both are nonetheless in the purge body, which is built from the DOWNLOAD listing.
    """
    assert port.PHASE_FILTERED_FILES_ARE_PURGED_BUT_NEVER_UPLOADED is True
    assert port.PURGE_LIST_IS_BUILT_FROM_THE_DOWNLOAD is True

    _root, old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "phase-filtered", old_calls, new_calls)

    calls = _aws(old_calls)
    cli = [c for c in calls if any(a == "s3://rediacc-releases/cli/stable/" for a in c)]
    assert len(cli) == 2, cli
    assert "latest*.yml" in cli[0], "phase 1 no longer excludes it; this case is stale"
    assert "latest-linux.yml" not in " ".join(cli[1]), cli[1]

    rpm = [c for c in calls if any(a == "s3://rediacc-releases/rpm/stable/" for a in c)]
    assert "repodata/*" in rpm[0]
    assert "comps.xml" not in " ".join(rpm[1] + rpm[2])

    # BUT BOTH ARE PURGED, and the run says the promotion is complete.
    urls = _urls(old_calls)
    assert "https://releases.rediacc.com/cli/stable/latest-linux.yml" in urls
    assert "https://releases.rediacc.com/rpm/stable/repodata/comps.xml" in urls
    assert old.returncode == 0

    # And under the fake's model of the filters, neither file arrives.
    landed = {line.split("\t")[1] for line in old_calls.splitlines() if line.startswith("UPLOAD\t")}
    assert "rediacc-releases/cli/stable/latest-linux.yml" not in landed
    assert "rediacc-releases/rpm/stable/repodata/comps.xml" not in landed


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
    twin = _with_the_resumable_download(old_calls)
    twin = twin.replace(
        "UPLOAD\trediacc-releases/apk/stable/old-0.0.1.apk\nCONTENT<<<bytes from a run that died\n>>>\n",
        "",
    )
    twin = _without_url(twin, "https://releases.rediacc.com/apk/stable/old-0.0.1.apk")
    assert new_calls == twin, f"{twin}\n---\n{new_calls}"


def test_defect_the_vacuity_floor_runs_after_the_uploads(tmp_path) -> None:
    """THE FLOOR NEEDS A LEFTOVER EMPTY DIRECTORY TO BE REACHABLE AT ALL.

    Order is download, rewrite, phase 1, phase 2, THEN count. With `cli/edge/` empty the download creates nothing and phase 1 is what fails; the floor's own sentence never prints. Both halves are driven and both agree.
    """
    assert port.VACUITY_FLOOR_RUNS_AFTER_THE_UPLOAD is False  # Rule T delta: the port counts first

    empty = {k: v for k, v in DEFAULT_BUCKET.items() if not k.startswith("cli/edge/")}

    _root, old, new, old_calls, new_calls = run_both(
        tmp_path / "a", empty, PROMOTE_RETRY_DELAY_S="0"
    )
    assert old.returncode == new.returncode == 1
    assert "VACUOUS" not in old.stderr, old.stderr
    assert "does not exist" in old.stderr, old.stderr
    # The port refuses by name, before any upload, where the twin fell into aws's own error.
    assert "VACUOUS: cli staged 0 file(s)" in new.stderr, new.stderr
    assert "cli/stable/" not in new_calls, new_calls

    def plant() -> None:
        os.makedirs(port.TMP_PREFIX + "cli", exist_ok=True)

    _root, old, new, old_calls, new_calls = run_both(tmp_path / "b", empty, pre=plant)
    # Same verdict and words on both sides; only the port skips the two empty syncs the twin makes first.
    assert new.returncode == old.returncode
    assert new.stderr == old.stderr
    assert new.stdout == old.stdout
    assert old_calls.count("\ts3://rediacc-releases/cli/stable/") == 2, old_calls
    assert "cli/stable/" not in new_calls, new_calls
    assert old.returncode == 1
    assert old.stderr == (
        "VACUOUS: cli staged 0 file(s) for promotion; refusing to report a "
        "promotion that moved nothing\n"
    ), repr(old.stderr)
    assert old.stdout == "Promoting cli/edge/ -> cli/stable/ (2-phase)\n"


# --------------------------------------------------------------------------- Refusals and failures ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_ENDPOINT", "EDGE_VERSION"],
)
def test_each_required_variable_refuses_with_the_same_status(tmp_path, missing) -> None:
    """THE ONE NAMED DIVERGENCE, and it is in text nobody parses.

    `EDGE_VERSION` is included deliberately: it is used only in the closing log line, so a port that treated it as optional would print `edge v -> stable` on a run the twin refuses outright.
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
    """`:?` IS AN UNSET-OR-EMPTY TEST."""
    root = fixture(tmp_path)
    old, _ = _run(root, "old", EDGE_VERSION="")
    new, _ = _run(root, "new", EDGE_VERSION="")
    assert old.returncode == 1, old.stderr
    assert new.returncode == 1, new.stderr
    tail = "EDGE_VERSION: %s: EDGE_VERSION must be set\n" % port.SELF
    assert old.stderr.endswith(tail)
    assert new.stderr == tail


def test_a_missing_aws_refuses_before_the_variable_guards(tmp_path) -> None:
    root = fixture(tmp_path)
    kw = {"drop": "aws", "drop_env": tuple(BASE_ENV)}
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    _agree(old, new, "no-aws", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n", repr(old.stderr)


def test_one_transient_aws_failure_stops_the_twin_but_the_port_retries_through_it(tmp_path) -> None:
    """RULE T DELTA (#4175e786). Call 5 is `apt`'s phase-1 sync. The twin, unguarded under `set -e`, stops there with `cli` promoted and `apt` half-done. The port repeats the idempotent transfer, says so on stderr, and completes, as M-live item 9 needed twice on 2026-09-24."""
    _root, old, new, old_calls, _new_calls = run_both(
        tmp_path,
        FAKE_AWS_FAIL_ON_CALL="5",
        FAKE_AWS_STDERR=INCOMPLETE_READ,
        PROMOTE_RETRY_DELAY_S="0",
    )
    assert old.returncode == 1
    assert old.stderr == INCOMPLETE_READ
    assert old.stdout.splitlines() == [
        "Promoting cli/edge/ -> cli/stable/ (2-phase)",
        "Promoting apt/edge/ -> apt/stable/ (2-phase)",
    ], old.stdout
    assert "curl" not in old_calls, "a failed promotion still purged"
    assert new.returncode == 0, new.stderr
    assert "sync of apt/stable failed (exit 1), retrying (2/3)" in new.stderr
    assert (
        new.stdout.rstrip("\n").splitlines()[-1].startswith("cf-purge")
        or "R2 promotion complete" in new.stdout
    )


def test_a_persistent_aws_failure_stops_both_sides_with_awss_status(tmp_path) -> None:
    """A failure the retry cannot outlast still stops the port, after TRANSFER_ATTEMPTS tries, with aws's own status and nothing purged."""
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
    """The promotion has already happened by then, which the twin's header says is deliberate."""
    _root, old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("CLOUDFLARE_ZONE_ID",))
    _agree(old, new, "no-zone", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stdout.rstrip("\n").endswith("R2 promotion complete: edge v1.2.3 -> stable")
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


def _upload_keys(calls: str) -> list[str]:
    return sorted(line.split("\t")[1] for line in calls.splitlines() if line.startswith("UPLOAD\t"))


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
        _upload_keys(old_calls),
        _upload_keys(new_calls),
    )


def _per_tree(gets: dict[str, int]) -> dict[str, dict[str, int]]:
    """The fetch counts grouped by channel directory, so a failure names the tree that moved more."""
    trees: dict[str, dict[str, int]] = {d: {} for d in port.CHANNEL_DIRS}
    for key, count in gets.items():
        trees[key.split("/")[1]][key] = count
    return trees


def test_the_port_fetches_and_uploads_exactly_what_the_twin_does(tmp_path) -> None:
    """THE 2026-09-25 QUESTION: does the port move more than the bash twin? Per tree, the same objects, each fetched once, and the same uploads.

    Both sides stage `<dir>/edge/` and nothing else. The live hotfix runs took hours on BOTH sides because that tree is the whole release history, not because a port reads more of it.
    """
    old, new, old_gets, new_gets, old_puts, new_puts = _transfer_plan(tmp_path)
    assert old.returncode == 0, old.stderr
    assert new.returncode == 0, new.stderr
    assert _per_tree(new_gets) == _per_tree(old_gets)
    edge = {"%s/%s" % (port.BUCKET, key) for key in DEFAULT_BUCKET if "/edge/" in key}
    assert set(old_gets) == edge, sorted(set(old_gets) ^ edge)
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

    The plant reverses the two `apt` phase-2 arms, which is the ONE defect this script exists to prevent: `Release`/`InRelease` uploaded before the `Packages` they hash, so a client fetching in the window gets a signature over bytes that are not there yet. Every printed byte and the exit code are unchanged.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    plant = source.replace(
        '        ("--exclude", "*", "--include", "Packages*"),\n'
        '        ("--exclude", "*", "--include", "Release*", "--include", "InRelease"),\n',
        '        ("--exclude", "*", "--include", "Release*", "--include", "InRelease"),\n'
        '        ("--exclude", "*", "--include", "Packages*"),\n',
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(plant, encoding="utf-8")

    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert new.stdout == old.stdout, "the plant changed stdout; wrong plant"
    assert new.stderr == old.stderr, "the plant changed stderr; wrong plant"
    assert new_calls != _with_the_resumable_download(old_calls), (
        "THE CALL LOG DID NOT SEE THE SWAP: this gate cannot fail"
    )

    apt_new = [
        c for c in _aws(new_calls) if any(a == "s3://rediacc-releases/apt/stable/" for a in c)
    ]
    assert apt_new[1][apt_new[1].index("--include") + 1] == "Release*"


# --------------------------------------------------------------------------- Pure helpers and the filter tables, exercised directly ---------------------------------------------------------------------------


def test_the_directory_order_is_the_twins() -> None:
    assert port.CHANNEL_DIRS == ("cli", "apt", "rpm", "apk", "archlinux")


def test_every_channel_directory_has_a_phase_two_arm() -> None:
    """A DIRECTORY MISSING FROM THE TABLE WOULD UPLOAD ITS BYTES AND NONE OF ITS
    METADATA, silently, and the closing line would still say complete."""
    assert set(port.PHASE_TWO) == set(port.CHANNEL_DIRS)
    assert [len(v) for v in (port.PHASE_TWO[d] for d in port.CHANNEL_DIRS)] == [1, 2, 2, 1, 1]


def test_the_phase_one_excludes_are_the_twins_list_in_the_twins_order() -> None:
    """A REORDERED LIST IS A DIFFERENT FILTER even when the set is identical, because aws applies the rules in order with the last match winning."""
    excludes = [
        port.META_EXCLUDES[i + 1]
        for i in range(0, len(port.META_EXCLUDES), 2)
        if port.META_EXCLUDES[i] == "--exclude"
    ]
    assert excludes == [
        "Packages*",
        "Release*",
        "InRelease",
        "repodata/*",
        "APKINDEX.tar.gz",
        "*.db.tar.gz",
        "*.files.tar.gz",
        "rediacc.db",
        "rediacc.files",
        "latest*.yml",
        "latest.json",
        "manifest.json",
        "install.sh",
        "install.ps1",
        "*.repo",
        "*.conf",
        "rediacc-cli-latest.tgz",
        "versions.json",
    ]
    assert len(port.META_EXCLUDES) == 2 * len(excludes)


def test_the_rewrite_table_matches_the_twins_case_arms() -> None:
    assert set(port.REWRITES) == {"cli", "rpm", "archlinux"}
    assert [name for name, _ in port.REWRITES["cli"]] == ["install.sh", "install.ps1"]
    assert port.REWRITES["rpm"] == (("rediacc.repo", (port.CHANNEL_SED,)),)
    assert port.REWRITES["archlinux"] == (("rediacc.conf", (port.CHANNEL_SED,)),)


def test_endpoint_args_reproduces_the_unquoted_word_split() -> None:
    assert port.endpoint_args("https://x") == ["--endpoint-url", "https://x"]
    assert port.endpoint_args("a b") == ["--endpoint-url", "a", "b"]


def test_sync_argv_puts_the_filters_last_and_the_cache_control_first(tmp_path) -> None:
    del tmp_path
    argv = port.sync_argv("apt", "/tmp/promote-apt", "https://x", ("--exclude", "*"))
    assert argv[:5] == [
        "aws",
        "s3",
        "sync",
        "/tmp/promote-apt/",
        "s3://rediacc-releases/apt/stable/",
    ]
    assert argv[-4:] == ["--cache-control", "no-cache", "--exclude", "*"]


def test_strip_prefix_and_read_lines_follow_bash_rather_than_python() -> None:
    assert port.strip_prefix("/tmp/promote-cli/a/b", "/tmp/promote-cli/") == "a/b"
    assert port.strip_prefix("/elsewhere/a", "/tmp/promote-cli/") == "/elsewhere/a"
    assert port.read_lines("a\nb\n") == ["a", "b"]
    assert port.read_lines("a\nb") == ["a"]
    assert port.read_lines("") == []


def test_the_purge_script_is_still_the_bash_one_and_still_exists() -> None:
    assert port.PURGE_SCRIPT_RELATIVE == ".ci/scripts/deploy/cf-purge-urls.sh"
    assert PURGE.is_file()
    assert port.purge_argv("z")[-2:] == ["--zone", "z"]


def test_every_variable_is_read_with_a_literal_os_environ_get() -> None:
    """THE DIRECT-READ DISCIPLINE, ASSERTED RATHER THAN REMEMBERED.

    `check:ci-python-env-registry` derives a module's inputs from its AST, and a read routed through `dict(os.environ)` or a local alias is invisible to it. Both directions: every name `environment()` returns must appear as a literal `os.environ.get("NAME"` in the source, and there must be no extra ones.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    names = set(port.environment())
    assert names == {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
        "EDGE_VERSION",
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
