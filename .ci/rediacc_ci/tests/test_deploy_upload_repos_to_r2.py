"""Differential: `rediacc_ci.deploy.upload_repos_to_r2` against its twin `.ci/scripts/deploy/upload-repos-to-r2.sh`.

RECORDING FAKES FOR `aws` AND `curl` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches R2 or Cloudflare, and nothing here reads or writes the real checkout: every case builds a throwaway tree holding the twin, the port, the purge script it calls and a `dist/` of its own, then runs both sides against it. `.ci/shadow/w7p5a-status.json` records this path as blocked only
for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

WHY THE FIXTURE HAS TO BE A WHOLE TREE AND NOT A tmp_path WITH A `dist/` IN IT. The twin's second act is `cd "$(get_repo_root)"`, which resolves `.ci/scripts/lib/../../..` from `common.sh`'s own location, NOT from the caller's cwd. Run the real twin from a fixture directory and it would walk back to this checkout and read the real `dist/`. The port derives its root the same way,
from `.ci/rediacc_ci/deploy/../../..`, so the copy in the fixture is what makes both sides answer the fixture. `test_the_root_comes_from_the_script_location_not_cwd` drives both from a subdirectory to prove that is what is happening.

THREE THINGS ARE COMPARED, NOT ONE. The streams and the exit code, as everywhere in this campaign, plus THE CALL LOG: the observable effect of this program is a set of `aws s3` calls and one Cloudflare purge, and two implementations can print the same `Repos uploaded to R2 channel: edge` while syncing different prefixes, enumerating files in a different ORDER, or uploading an
install script that still points at the wrong channel. The `aws` fake therefore logs the CONTENT of every `cp` source as well as its argv.

THE TEMPORARY PATH IS MASKED IN THE CALL LOG AND NOWHERE ELSE. `mktemp` cannot
return the same name twice, so the two sides' `aws s3 cp` argv differ in exactly
that one field by construction. `_mask` replaces it and leaves everything else byte-exact, which is the narrowest mask that lets the comparison run.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import channel_snapshot, r2_promote
from rediacc_ci.deploy import upload_repos_to_r2 as port
from rediacc_ci.tests.wkloader import copy_loader
from rediacc_ci.well_known import CF_API_BASE, RELEASES_BUCKET, RELEASES_ORIGIN

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "upload-repos-to-r2.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "upload_repos_to_r2.py"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "CHANNEL": "edge",
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-key-fixture",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret-fixture",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# The default `dist/` a case gets: two package formats (so the loop is proved to skip the two that are absent) and both install scripts. `apt` holds a file in a
# SUBDIRECTORY as well as one at the top, because `${f#dist/repos/$dir/}` is a
# prefix strip rather than a basename and the two differ only on that file.
DEFAULT_TREE = {
    "dist/repos/apt/InRelease": "InRelease body\n",
    "dist/repos/apt/dists/stable/Packages.gz": "packages body\n",
    "dist/repos/apk/APKINDEX.tar.gz": "apkindex body\n",
    "dist/pages/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n',
    "dist/pages/install.ps1": '$c = if ($e) { "edge" } else { "stable" }\n',
}

FAKE_AWS = """#!/usr/bin/python3
import json
import os
import shutil
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("aws\\t" + "\\t".join(argv) + "\\n")
    if len(argv) > 2 and argv[1] == "cp" and not argv[2].startswith("s3://"):
        with open(argv[2]) as src:
            fh.write("CONTENT<<<" + src.read() + ">>>\\n")

rc = int(os.environ.get("FAKE_AWS_RC", "0"))
if rc:
    sys.stderr.write("upload failed: the bucket said no\\n")
    sys.exit(rc)

# THE BUCKET MODEL (the prune delta): `FAKE_S3_ROOT/<bucket>/<key>`. A sync and a cp land there, a listing and a read come from there, and a delete removes from there. The twin's calls behave exactly as before; only the port's prune reads anything back.
root = os.environ.get("FAKE_S3_ROOT", "")


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


if root and argv[:2] == ["s3", "sync"]:
    src, dst = argv[2], argv[3][5:]
    drop = os.environ.get("FAKE_AWS_DROP_SYNC_MATCH", "")
    for dirpath, _d, files in os.walk(src):
        for name in files:
            full = os.path.join(dirpath, name)
            if drop and drop in full:
                continue
            target = os.path.join(root, dst, os.path.relpath(full, src))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(full, target)
elif root and argv[:2] == ["s3", "cp"] and argv[2].startswith("s3://"):
    path = os.path.join(root, argv[2][5:])
    if not os.path.isfile(path):
        sys.stderr.write("fatal error: An error occurred (404) when calling the HeadObject operation: Key not found\\n")
        sys.exit(1)
    sys.stdout.write(open(path).read())
elif root and argv[:2] == ["s3", "cp"]:
    target = os.path.join(root, argv[3][5:])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(argv[2], target)
elif argv[:2] == ["s3api", "list-objects-v2"]:
    bucket, prefix = opt("--bucket"), opt("--prefix")
    base = os.path.join(root, bucket) if root else ""
    contents = []
    for dirpath, _d, files in (os.walk(base) if base else ()):
        for name in files:
            full = os.path.join(dirpath, name)
            key = os.path.relpath(full, base)
            if key.startswith(prefix):
                contents.append({"Key": key, "Size": os.path.getsize(full), "LastModified": "2026-10-06T00:00:00.000Z"})
    contents.sort(key=lambda c: c["Key"])
    print(json.dumps({"Contents": contents} if contents else {"Prefix": prefix}))
elif argv[:2] == ["s3api", "delete-objects"]:
    bucket = opt("--bucket")
    refuse = os.environ.get("FAKE_AWS_DELETE_ERROR_MATCH", "")
    errors = []
    with open(log, "a") as fh:
        for item in json.loads(opt("--delete"))["Objects"]:
            if refuse and refuse in item["Key"]:
                errors.append({"Key": item["Key"], "Code": "AccessDenied", "Message": "Access Denied"})
                continue
            path = os.path.join(root, bucket, item["Key"])
            if os.path.isfile(path):
                os.remove(path)
            fh.write("DELETE\\t" + item["Key"] + "\\n")
    if errors:
        print(json.dumps({"Errors": errors}))
"""

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

# Every real binary either side reaches for. `find`, `sed` and `mktemp` are called by BOTH implementations (the port shells out to the same three, for the reasons in its docstring); `jq` and `python3` (the registry loader, env_file_load) belong to cf-purge-urls.sh; `uname`, `dirname`, `basename`, `rm` and `wc` are what the twin and common.sh need. Nothing else is on the scratch PATH, so a tool leaking in would show up as a
# behaviour change.
PATH_MINIMUM = (
    "python3",
    "jq",
    "uname",
    "dirname",
    "basename",
    "find",
    "wc",
    "mktemp",
    "sed",
    "rm",
)

TMP_RE = re.compile(r"/\S*/tmp\.[A-Za-z0-9]{10}")


def _mask(calls: str) -> str:
    """The one masked field: `mktemp` cannot answer the same twice."""
    return TMP_RE.sub("<tmp>", calls)


# THE PRUNE DELTA'S CALLS, which the twin never makes: a listing, a read of one object to stdout, a batched delete, and the fake's own `DELETE` records. `_without_prune` removes exactly these from the port's call log, and `_without_prune_lines` the port's `Pruned`/`Prune keeps` lines from its stdout, so every differential case still compares the twin's behaviour byte for byte. The delta itself is pinned by the `test_prune_*` cases.
_PRUNE_CALL_RE = re.compile(
    r"^(aws\ts3api\tlist-objects-v2\t.*|aws\ts3api\tdelete-objects\t.*"
    r"|aws\ts3\tcp\ts3://\S+\t-\t--endpoint-url\t.*|DELETE\t.*)\n",
    re.MULTILINE,
)


def _without_prune(calls: str) -> str:
    return _PRUNE_CALL_RE.sub("", calls)


def _without_prune_lines(stdout: str) -> str:
    return "".join(
        line
        for line in stdout.splitlines(keepends=True)
        if not line.startswith(("Pruned ", "Prune keeps "))
    )


def _bin(root: pathlib.Path, *, drop: str = "", aws_body: str = FAKE_AWS) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name, body in (("aws", aws_body), ("curl", FAKE_CURL)):
        if name == drop:
            continue
        script = stub / name
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(tmp_path: pathlib.Path, tree: dict[str, str] | None = None) -> pathlib.Path:
    """A throwaway repository holding both implementations and a `dist/`.

    BOTH SIDES ARE COPIED IN rather than invoked from this checkout, because each resolves the repository root from its own location. A test that ran the real files would drive them against the real tree.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "deploy").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(PURGE, root / ".ci" / "scripts" / "deploy" / PURGE.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.env", root / ".ci" / "config" / "well-known.env"
    )
    # common.sh sources the generated shell form of the same constants (another writer's change, 2026-10-01); the fixture tree has to carry it or the twin dies before it starts.
    generated = ROOT / ".ci" / "config" / "well-known.generated.sh"
    if generated.is_file():
        shutil.copy2(generated, root / ".ci" / "config" / generated.name)
    copy_loader(root)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "deploy" / PORT.name)

    for rel, body in (DEFAULT_TREE if tree is None else tree).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    # An empty `dist/` still has to EXIST for the empty-tree case to be about the loops rather than about a missing directory.
    (root / "dist").mkdir(parents=True, exist_ok=True)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    cwd: pathlib.Path | None = None,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    aws_body: str = FAKE_AWS,
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    (root / f"{side}-s3").mkdir(exist_ok=True)
    env = {
        "FAKE_S3_ROOT": str(root / f"{side}-s3"),
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
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "deploy" / PORT.name)]
    proc = subprocess.run(
        argv,
        cwd=str(root if cwd is None else cwd),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, _mask(call_log.read_text(encoding="utf-8"))


def run_both(tmp_path: pathlib.Path, tree: dict[str, str] | None = None, **kw):
    """BOTH SIDES RUN AGAINST ONE TREE, and that is a correctness requirement rather than a saving. The URL list this script builds is `find`'s order, which is DIRECTORY order: two trees holding the same five files can enumerate them differently, and the comparison would then report a divergence that is the fixture's and not the port's. Measured on the first run of this file, where
    `dists/stable/Packages.gz` came out before `InRelease` in one tree. Neither side writes into `dist/`, and the two call logs have different names.
    """
    root = fixture(tmp_path, tree)
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    return old, new, old_calls, new_calls


def find_urls(root: pathlib.Path, channel: str = "edge") -> list[str]:
    """The purge URLs THIS tree must produce, in `find`'s own order.

    Derived by running the same `find` the twin runs, so the expectation is the filesystem's answer rather than a second implementation of the port's walk.
    """
    urls: list[str] = []
    for fmt in port.FORMATS:
        directory = root / "dist" / "repos" / fmt
        if not directory.is_dir():
            continue
        listing = subprocess.run(
            ["find", "dist/repos/%s" % fmt, "-type", "f"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        urls.extend(
            (RELEASES_ORIGIN + "/%s/%s/%s") % (fmt, channel, path[len("dist/repos/%s/" % fmt) :])
            for path in listing.splitlines()
        )
    urls.extend(
        (RELEASES_ORIGIN + "/cli/%s/%s") % (channel, name)
        for name in ("install.sh", "install.ps1")
        if (root / "dist" / "pages" / name).is_file()
    )
    return urls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    new_stdout = _without_prune_lines(new.stdout)
    assert new_stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new_stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert _without_prune(new_calls) == old_calls, (
            f"{label}: the call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def test_a_full_upload_is_pinned_call_by_call(tmp_path: pathlib.Path) -> None:
    """THE HAPPY PATH, PINNED AGAINST LITERAL BYTES. Two syncs (the two formats that exist), two rewritten install scripts with their CONTENT, and one purge carrying all five URLs.

    THE FIVE URLS ARE ASSERTED AS A SET HERE and as an ORDER in the next test, because their order is the filesystem's rather than this file's: hard-coding it would pin the fixture's directory layout, which is not the subject.
    """
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")
    assert old.returncode == 0
    assert old.stdout == (
        "Repos uploaded to R2 channel: edge\n"
        "cf-purge-urls.sh: purging 5 URL(s) from CF zone zone-fixture\n"
        "cf-purge-urls.sh: purged 5 URL(s) successfully\n"
    )
    assert old.stderr == ""

    head, _sep, purge = old_calls.partition("curl\t")
    assert head == (
        "aws\ts3\tsync\tdist/repos/apt\ts3://"
        + RELEASES_BUCKET
        + "/apt/edge/\t"
        + "--cache-control\tno-cache\t--endpoint-url\thttps://r2.example.invalid\t--only-show-errors\n"
        + "aws\ts3\tsync\tdist/repos/apk\ts3://"
        + RELEASES_BUCKET
        + "/apk/edge/\t"
        + "--cache-control\tno-cache\t--endpoint-url\thttps://r2.example.invalid\t--only-show-errors\n"
        + "aws\ts3\tcp\t<tmp>\ts3://"
        + RELEASES_BUCKET
        + "/cli/edge/install.sh\t"
        + "--cache-control\tno-cache\t--endpoint-url\thttps://r2.example.invalid\t--only-show-errors\n"
        + 'CONTENT<<<#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n>>>\n'
        + "aws\ts3\tcp\t<tmp>\ts3://"
        + RELEASES_BUCKET
        + "/cli/edge/install.ps1\t"
        + "--cache-control\tno-cache\t--endpoint-url\thttps://r2.example.invalid\t--only-show-errors\n"
        + 'CONTENT<<<$c = if ($e) { "edge" } else { "edge" }\n>>>\n'
    )
    argv = purge.rstrip("\n").split("\t")
    assert argv[:-1] == [
        "-sS",
        "-X",
        "POST",
        (CF_API_BASE + "/zones/zone-fixture/purge_cache"),
        "-H",
        "Authorization: Bearer tok-fixture",
        "-H",
        "Content-Type: application/json",
        "--data",
    ]
    assert sorted(json.loads(argv[-1])["files"]) == [
        (RELEASES_ORIGIN + "/apk/edge/APKINDEX.tar.gz"),
        (RELEASES_ORIGIN + "/apt/edge/InRelease"),
        (RELEASES_ORIGIN + "/apt/edge/dists/stable/Packages.gz"),
        (RELEASES_ORIGIN + "/cli/edge/install.ps1"),
        (RELEASES_ORIGIN + "/cli/edge/install.sh"),
    ]
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_the_purge_list_is_finds_order_not_sorted_order(tmp_path: pathlib.Path) -> None:
    """WHY THE PORT SHELLS OUT TO `find`. The twin appends one URL per line of `find -type f`, which is DIRECTORY order, and this fixture's directory order is not sorted order: measured here, `dists/stable/Packages.gz` comes out before `InRelease`, which `sorted()` would reverse. The expectation is computed by running the same `find`, so it is the filesystem's answer rather
    than a second implementation of the walk. Nothing on either stream would show a port that reordered this."""
    root = fixture(tmp_path)
    expected = find_urls(root)
    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")
    body = json.loads(old_calls.rpartition("--data\t")[2].rstrip("\n"))
    assert body["files"] == expected

    # THE CONTROL FOR THIS CONTROL. The assertion above only bites while the expected order and sorted order genuinely differ, and INTRA-directory order is the filesystem's whim -- two trees holding the same two files answered differently on this machine. What is NOT whim is the FORMAT order: the twin walks `apt rpm apk archlinux`, so `apt/...` precedes `apk/...` in the real list
    # while `sorted()` would put `apk` first. That is what makes a sorting port detectable here on every filesystem, and it is asserted rather than assumed.
    assert expected != sorted(expected), (
        "this fixture no longer distinguishes find order from sorted order, so a "
        "port that sorted the purge list would pass; restore a tree with files in "
        "two package formats whose names sort against the twin's format order"
    )
    _assert_agree(old, new, "find-order", old_calls, new_calls)


def test_a_nested_file_keeps_its_directories_in_the_url(tmp_path: pathlib.Path) -> None:
    """`${f#dist/repos/$dir/}` IS A PREFIX STRIP, NOT A BASENAME. A port using
    `os.path.basename` would purge `.../apt/edge/Packages.gz`, a URL that does not exist, and leave the real one cached."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert (RELEASES_ORIGIN + "/apt/edge/dists/stable/Packages.gz") in old_calls
    _assert_agree(old, new, "prefix-strip", old_calls, new_calls)


def test_the_install_scripts_are_rewritten_to_the_channel(tmp_path: pathlib.Path) -> None:
    """BOTH SUBSTITUTIONS, on a channel that is neither `edge` nor `stable`, so a port that only rewrote one of the two is visible."""
    old, new, old_calls, new_calls = run_both(tmp_path, CHANNEL="pr-42")
    assert 'CONTENT<<<#!/bin/sh\n: "${REDIACC_CHANNEL:-pr-42}"\n>>>' in old_calls
    assert 'CONTENT<<<$c = if ($e) { "edge" } else { "pr-42" }\n>>>' in old_calls
    assert ("s3://" + RELEASES_BUCKET + "/cli/pr-42/install.ps1") in old_calls
    _assert_agree(old, new, "install-rewrite", old_calls, new_calls)


def test_a_format_with_no_directory_is_skipped_silently(tmp_path: pathlib.Path) -> None:
    """VACUITY FACT 1: not every channel builds every package format, so a MISSING `dist/repos/<fmt>` is legitimate and produces no call and no line."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, tree={"dist/repos/rpm/rediacc.rpm": "rpm body\n"}
    )
    assert old.returncode == 0
    assert old_calls.count("aws\ts3\tsync") == 1
    assert ("s3://" + RELEASES_BUCKET + "/rpm/edge/") in old_calls
    assert "apt" not in old_calls
    _assert_agree(old, new, "absent-format", old_calls, new_calls)


def test_a_format_directory_holding_nothing_is_refused(tmp_path: pathlib.Path) -> None:
    """VACUITY FACT 1, the other half. A directory that EXISTS and holds no files means the sync moved nothing, so the run is refused rather than reported as an upload. Note the sync HAS already run when the refusal fires."""
    root = fixture(tmp_path, tree={})
    (root / "dist" / "repos" / "apt").mkdir(parents=True)
    old, old_calls = _run(root, "old")
    new, new_calls = _run(root, "new")
    assert old.returncode == 1
    assert old.stderr == (
        "VACUOUS: dist/repos/apt exists but holds 0 file(s); refusing to report "
        "an upload that moved nothing\n"
    )
    assert old.stdout == ""
    assert old_calls.count("aws\ts3\tsync") == 1, "the refusal fires AFTER the sync"
    assert "curl" not in old_calls, "a refused run still purged"
    _assert_agree(old, new, "vacuous-dir", old_calls, new_calls)


def test_defect_an_entirely_empty_dist_reports_a_successful_upload(
    tmp_path: pathlib.Path,
) -> None:
    """VACUITY FACT 2, PINNED. With no `dist/repos/*` and no install script, every loop body is skipped, nothing is uploaded, nothing is purged, and the script prints `Repos uploaded to R2 channel: edge` and exits 0. The per-directory guard above cannot see it, because its subject is one directory rather than the upload as a whole.

    Reproduced rather than repaired: agreement with the live twin is this wave's deliverable, and the fix is a cutover-box decision. If it is ever repaired, this test goes red and names the port that must follow."""
    old, new, old_calls, new_calls = run_both(tmp_path, tree={})
    assert old.returncode == 0
    assert old.stdout == "Repos uploaded to R2 channel: edge\n"
    assert old.stderr == ""
    assert old_calls == "", "nothing was uploaded and nothing was purged"
    assert port.AN_EMPTY_DIST_REPORTS_SUCCESS
    _assert_agree(old, new, "empty-dist", old_calls, new_calls)


def test_missing_aws_refuses_before_the_environment_is_read(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE: `require_cmd aws` runs before the five guards, so a run missing both the binary and every variable names the binary."""
    old, new, old_calls, new_calls = run_both(tmp_path, drop="aws", drop_env=tuple(BASE_ENV.keys()))
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n"
    assert old.stdout == ""
    _assert_agree(old, new, "no-aws", old_calls, new_calls)


def test_divergence_each_of_the_five_guards_is_bashs_own_unbound_variable(
    tmp_path: pathlib.Path,
) -> None:
    """THE ONE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS FOR ALL FIVE GUARDS. bash prints its own FILE and LINE NUMBER before the twin's message, and the twin's message already begins with the script name. The port prints the `VAR: message` half. Same stream, same status 1, no call from either side, and the ORDER of the guards is identical: the first missing one wins."""
    for index, (name, message) in enumerate(port.REQUIRED_ENV):
        case = tmp_path / f"guard-{name}"
        # Drop this one and everything after it, so the FIRST missing variable is the one under test and the guard order is what selects the message.
        dropped = tuple(n for n, _m in port.REQUIRED_ENV[index:])
        old, new, old_calls, new_calls = run_both(case, drop_env=dropped)
        assert old.returncode == new.returncode == 1, name
        assert old.stderr.rstrip("\n").endswith("%s: %s" % (name, message)), old.stderr
        assert ": line " in old.stderr, "bash stopped naming a line; re-read this divergence"
        assert new.stderr == "%s: %s\n" % (name, message)
        assert old.stdout == new.stdout == ""
        assert old_calls == new_calls == ""


def test_an_empty_channel_refuses_exactly_as_an_absent_one_does(
    tmp_path: pathlib.Path,
) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port testing `"CHANNEL" in os.environ` would sail past this and sync every format to `s3://rediacc-releases/apt//`, which is every channel's parent prefix."""
    old, new, old_calls, new_calls = run_both(tmp_path, CHANNEL="")
    assert old.returncode == new.returncode == 1
    assert new.stderr == "CHANNEL: upload-repos-to-r2.sh: CHANNEL must be set\n"
    assert old_calls == new_calls == "", "an empty channel still reached aws"


def test_skip_release_on_a_release_channel_writes_nothing(tmp_path: pathlib.Path) -> None:
    """THE BUMP-NONE BANNER, byte for byte, on STDOUT and with exit 0: the twin's own closing sentence says this is the intended outcome, not an error."""
    for channel in port.RELEASE_CHANNELS:
        case = tmp_path / f"skip-{channel}"
        old, new, old_calls, new_calls = run_both(case, CHANNEL=channel, SKIP_RELEASE="true")
        assert old.returncode == 0
        assert old.stderr == ""
        assert old.stdout == "\n".join(port.skip_banner(channel)) + "\n"
        assert "RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2" in old.stdout
        assert f"    - apt/{channel}/  rpm/{channel}/" in old.stdout
        assert old_calls == "", "a skipped release still wrote to R2"
        _assert_agree(old, new, f"skip-{channel}", old_calls, new_calls)


def test_skip_release_on_a_pr_channel_uploads_as_usual(tmp_path: pathlib.Path) -> None:
    """SCOPED TO THE RELEASE CHANNELS: a `pr-N` channel has no tag contract, so the flag is announced and ignored rather than obeyed."""
    old, new, old_calls, new_calls = run_both(tmp_path, CHANNEL="pr-9", SKIP_RELEASE="yes")
    assert old.returncode == 0
    assert old.stdout.startswith(
        "upload-repos-to-r2.sh: SKIP_RELEASE ignored on channel 'pr-9': "
        "not a release channel, uploading as usual\n"
    )
    assert ("s3://" + RELEASES_BUCKET + "/apt/pr-9/") in old_calls
    _assert_agree(old, new, "skip-pr", old_calls, new_calls)


def test_the_skip_values_are_an_exact_list_not_a_lowercase_test(
    tmp_path: pathlib.Path,
) -> None:
    """THE `case` ARMS ARE SPELLINGS, NOT A PREDICATE. `TrUe` and `Y` are NOT skip
    values, so a port using `.lower() in {...}` would refuse a release the twin
    publishes. Driven for one accepted spelling and two rejected ones."""
    accepted, _new, accepted_calls, _nc = run_both(
        tmp_path / "on", CHANNEL="edge", SKIP_RELEASE="ON"
    )
    assert accepted.returncode == 0
    assert accepted_calls == ""
    assert "RELEASE SKIPPED" in accepted.stdout

    for spelling in ("TrUe", "Y", "false", ""):
        case = tmp_path / f"reject-{spelling or 'empty'}"
        old, new, old_calls, new_calls = run_both(case, CHANNEL="edge", SKIP_RELEASE=spelling)
        assert old.returncode == 0, spelling
        assert "RELEASE SKIPPED" not in old.stdout, f"{spelling!r} was treated as a skip"
        assert "aws\ts3\tsync" in old_calls, f"{spelling!r} suppressed the upload"
        _assert_agree(old, new, f"skip-value-{spelling!r}", old_calls, new_calls)


def test_a_failed_sync_ends_the_run_with_awss_status(tmp_path: pathlib.Path) -> None:
    """`aws s3 sync` IS UNGUARDED, so `set -e` ends the run with its status and aws's own stderr is the only explanation. The second format is never reached and nothing is purged."""
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_AWS_RC="2")
    assert old.returncode == 2
    assert old.stderr == "upload failed: the bucket said no\n"
    assert old.stdout == ""
    assert old_calls.count("aws") == 1, "the loop continued past a failed sync"
    _assert_agree(old, new, "sync-fails", old_calls, new_calls)


def test_a_failed_purge_ends_the_run_with_the_purge_scripts_status(
    tmp_path: pathlib.Path,
) -> None:
    """THE FINAL PIPELINE IS UNGUARDED TOO, under `pipefail`. A curl transport failure inside cf-purge-urls.sh exits 6, and that becomes this script's status AFTER `Repos uploaded to R2 channel: edge` has already printed."""
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_CURL_RC="6")
    assert old.returncode == 6
    assert old.stdout.startswith("Repos uploaded to R2 channel: edge\n")
    assert old.stderr == "curl: (6) Could not resolve host: api.cloudflare.com\n"
    _assert_agree(old, new, "purge-fails", old_calls, new_calls)


def test_the_root_comes_from_the_script_location_not_cwd(tmp_path: pathlib.Path) -> None:
    """`cd "$(get_repo_root)"`, PROVEN. Both sides are invoked from a subdirectory of the fixture that holds no `dist/` at all; if either resolved its paths from cwd, its loops would find nothing and it would print the empty-upload line instead of uploading five URLs."""
    old_root = fixture(tmp_path / "old")
    new_root = fixture(tmp_path / "new")
    for root in (old_root, new_root):
        (root / "sub" / "deeper").mkdir(parents=True)
    old, old_calls = _run(old_root, "old", cwd=old_root / "sub" / "deeper")
    new, new_calls = _run(new_root, "new", cwd=new_root / "sub" / "deeper")
    assert old.returncode == 0
    assert "purging 5 URL(s)" in old.stdout
    assert old_calls.count("aws\ts3\tsync") == 2
    _assert_agree(old, new, "cwd-independence", old_calls, new_calls)


def test_the_r2_credentials_are_bridged_into_the_aws_names(tmp_path: pathlib.Path) -> None:
    """`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION=auto`
    are EXPORTED for the child, not passed as arguments. Asserted through a fake that reports the three variables it was HANDED, because a port that set them on itself without exporting would look identical from the outside, and the twin's sibling `delete-r2-channel.sh` records that a missing R2 -> AWS bridge surfaces as an unhelpful credentials error rather than as a missing
    variable."""
    reporter = FAKE_AWS.replace(
        "argv = sys.argv[1:]\n",
        "argv = sys.argv[1:]\n"
        'with open(os.environ["FAKE_CALL_LOG"], "a") as fh:\n'
        '    fh.write("env\\t%s\\t%s\\t%s\\n" % (\n'
        '        os.environ.get("AWS_ACCESS_KEY_ID", "-"),\n'
        '        os.environ.get("AWS_SECRET_ACCESS_KEY", "-"),\n'
        '        os.environ.get("AWS_DEFAULT_REGION", "-"),\n'
        "    ))\n",
        1,
    )
    assert reporter != FAKE_AWS, "the reporter plant did not apply"
    root = fixture(tmp_path)
    for side in ("old", "new"):
        proc, calls = _run(root, side, aws_body=reporter)
        assert proc.returncode == 0, calls
        assert "env\tr2-key-fixture\tr2-secret-fixture\tauto\n" in calls, side
        reports = calls.count("env\t")
        assert reports == calls.count("aws\t"), "one report per aws call"
        assert calls.count("env\tr2-key-fixture\tr2-secret-fixture\tauto\n") == reports, side
        assert _without_prune(calls).count("aws\t") == 4, (
            "two syncs and two cps, plus the prune's own calls"
        )


def test_pure_helpers() -> None:
    assert port.SELF == "upload-repos-to-r2.sh"
    assert port.FORMATS == ("apt", "rpm", "apk", "archlinux")
    assert port.CC_MUTABLE == "no-cache"
    assert port.PURGE_SCRIPT == ".ci/scripts/deploy/cf-purge-urls.sh"

    assert port.sync_argv("apt", "edge", "https://e") == [
        "aws",
        "s3",
        "sync",
        "dist/repos/apt",
        ("s3://" + RELEASES_BUCKET + "/apt/edge/"),
        "--cache-control",
        "no-cache",
        "--endpoint-url",
        "https://e",
        "--only-show-errors",
    ]
    assert port.cp_argv("/tmp/x", "edge", "install.sh", "https://e")[4] == (
        "s3://" + RELEASES_BUCKET + "/cli/edge/install.sh"
    )
    assert port.sed_argv("pr-1", "dist/pages/install.sh")[2] == (
        "s|REDIACC_CHANNEL:-stable|REDIACC_CHANNEL:-pr-1|g"
    )
    assert port.purge_argv("Z") == [".ci/scripts/deploy/cf-purge-urls.sh", "--zone", "Z"]

    assert port.repo_url("apt", "edge", "dists/stable/P.gz") == (
        RELEASES_ORIGIN + "/apt/edge/dists/stable/P.gz"
    )
    assert port.install_url("edge", "install.ps1") == (RELEASES_ORIGIN + "/cli/edge/install.ps1")
    assert port.strip_prefix("dist/repos/apt/a/b", "dist/repos/apt/") == "a/b"
    assert port.strip_prefix("elsewhere/x", "dist/repos/apt/") == "elsewhere/x"

    # `read` semantics: a final line with no newline is dropped.
    assert port.read_lines("a\nb\n") == ["a", "b"]
    assert port.read_lines("a\nb") == ["a"]
    assert port.read_lines("") == []

    for value in ("true", "TRUE", "True", "1", "yes", "YES", "y", "on", "ON"):
        assert port.skip_release_requested({"SKIP_RELEASE": value}), value
    for value in ("TrUe", "Y", "false", "no", "0", ""):
        assert not port.skip_release_requested({"SKIP_RELEASE": value}), value
    assert not port.skip_release_requested({})

    banner = port.skip_banner("edge")
    assert banner[0] == ""
    assert banner[-1] == ""
    assert banner[2] == "  RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2"
    assert len(banner) == 19


def test_the_guard_list_is_the_twins_guard_list() -> None:
    """STALENESS ALARM. `REQUIRED_ENV` is a copy of the twin's five `${VAR:?msg}`
    guards, re-derived here from the twin's source, in order and with messages."""
    source = TWIN.read_text(encoding="utf-8")
    found = re.findall(r'^: "\$\{(\w+):\?([^}]*)\}"', source, re.MULTILINE)
    assert found, "the guard shape changed; this alarm is no longer reading anything"
    assert [(name, msg) for name, msg in found] == list(port.REQUIRED_ENV)


def test_the_skip_values_are_the_twins_case_arms() -> None:
    """STALENESS ALARM for the `case` arms, which sit between the two markers the gate test `test_gate_skip_release_channel_pointer.py` splits the twin on."""
    source = TWIN.read_text(encoding="utf-8")
    arm = re.search(r"case \"\$\{SKIP_RELEASE:-\}\" in\n\s*([^)]*)\) return 0", source)
    assert arm is not None, "the case shape changed; this alarm reads nothing"
    assert {value.strip() for value in arm.group(1).split("|")} == set(port.SKIP_RELEASE_VALUES)


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the CACHE-CONTROL header, which is the one field whose loss caused the incident this script's header is written about: an `immutable` policy let CF serve a previous run's body under a URL the new APKINDEX points at, and apt-get reported `BAD signature`. Nothing on either stream carries it, both exits are 0, and only the call log sees it. Driven
    red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('CC_MUTABLE = "no-cache"', 'CC_MUTABLE = "immutable"', 1)
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    old_root = fixture(tmp_path / "old")
    bad_root = fixture(tmp_path / "bad")
    (bad_root / ".ci" / "rediacc_ci" / "deploy" / PORT.name).write_text(mutated, encoding="utf-8")

    old, old_calls = _run(old_root, "old")
    bad, bad_calls = _run(bad_root, "new")
    assert bad.returncode == old.returncode == 0, (
        "the plant is invisible in the exit code, which is why the calls are compared"
    )
    assert _without_prune_lines(bad.stdout) == old.stdout, "the plant is invisible on stdout"
    assert bad.stderr == old.stderr, "the plant is invisible on stderr too"
    assert "--cache-control\timmutable" in bad_calls
    assert _without_prune(bad_calls) != old_calls, "the mutant's calls matched the twin's"

    good_root = fixture(tmp_path / "good")
    _good, good_calls = _run(good_root, "new")
    assert _without_prune(good_calls) == old_calls, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


# --------------------------------------------------------------------------- Rule T: a transient R2 failure is retried, a refusal is not (#4175e786) ---------------------------------------------------------------------------

INCOMPLETE_READ = (
    "upload failed: dist/repos/apt/InRelease to s3://%s/apt/edge/InRelease "
    "('Connection broken: IncompleteRead(7540288 bytes read, 848320 more expected)', "
    "IncompleteRead(7540288 bytes read, 848320 more expected))\n" % RELEASES_BUCKET
)

# Fails the first `FAKE_AWS_FAIL_TIMES` calls with `FAKE_AWS_FAIL_STDERR`, then succeeds. The counter lives in a file because every call is its own process.
FLAKY_AWS = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("aws\\t" + "\\t".join(sys.argv[1:]) + "\\n")
counter = log + ".n"
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
if n < int(os.environ["FAKE_AWS_FAIL_TIMES"]):
    sys.stderr.write(os.environ["FAKE_AWS_FAIL_STDERR"])
    sys.exit(1)
"""


def _drive_port_in_process(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    *,
    fail_times: int,
    fail_stderr: str,
) -> tuple[int, str, list[str]]:
    """`port.main()` over a fixture tree with a flaky `aws`, no sleeping, and the delay between attempts zeroed.

    In process because the delay is a module constant and a test that slept it for real would pay seconds per case; everything the port mutates (cwd, environment) is registered with monkeypatch first so it is restored.
    """
    root = fixture(tmp_path, {"dist/repos/apt/InRelease": "InRelease body\n"})
    stub = pathlib.Path(_bin(root, aws_body=FLAKY_AWS))
    purge = root / "purge.sh"
    purge.write_text("#!/usr/bin/python3\nimport sys\n\nsys.stdin.read()\n", encoding="utf-8")
    purge.chmod(0o755)
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")

    monkeypatch.chdir(root)
    monkeypatch.setattr(port, "repo_root", lambda: str(root))
    monkeypatch.setattr(port, "PURGE_SCRIPT", str(purge))
    monkeypatch.setattr(port, "RETRY_DELAY_S", 0.0)
    # These cases are about the transfer retry; FLAKY_AWS models no bucket, so the prune (pinned by the `test_prune_*` cases) is switched off here rather than fed a fake listing.
    monkeypatch.setattr(port, "_prune_trees", lambda *_args: None)
    for name, value in {
        **BASE_ENV,
        "PATH": str(stub),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_AWS_FAIL_TIMES": str(fail_times),
        "FAKE_AWS_FAIL_STDERR": fail_stderr,
        "AWS_ACCESS_KEY_ID": "x",
        "AWS_SECRET_ACCESS_KEY": "x",
        "AWS_DEFAULT_REGION": "x",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SKIP_RELEASE", raising=False)

    status = port.main([])
    captured = capfd.readouterr()
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return status, captured.err, calls


def test_delta_a_broken_read_on_the_sync_is_retried_through(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """INTENTIONAL DELTA (Rule T, #4175e786). The twin ran each `aws s3 sync` / `cp` once under `set -e`, so ONE transient R2 `IncompleteRead` ended a release upload half-way. The port retries the transient class (3 attempts), says so on stderr, and still shows aws's own message each time. A fake that fails once, then succeeds."""
    status, err, calls = _drive_port_in_process(
        tmp_path, monkeypatch, capfd, fail_times=1, fail_stderr=INCOMPLETE_READ
    )
    assert status == 0, err
    assert len([c for c in calls if c.startswith("aws\ts3\tsync")]) == 2
    assert "IncompleteRead" in err
    assert "retrying (2/3)" in err


def test_delta_a_persistent_broken_read_still_fails_and_names_the_cause(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Bounded: three attempts, then the run fails with aws's own status and a line naming the cause. A fake that always fails."""
    status, err, calls = _drive_port_in_process(
        tmp_path, monkeypatch, capfd, fail_times=99, fail_stderr=INCOMPLETE_READ
    )
    assert status == 1
    assert len([c for c in calls if c.startswith("aws\ts3\tsync")]) == 3
    assert "after 3 attempts" in err
    assert "IncompleteRead" in err
    assert "Repos uploaded" not in err


@pytest.mark.parametrize(
    "refusal",
    [
        "An error occurred (AccessDenied) when calling the PutObject operation\n",
        "An error occurred (NoSuchBucket) when calling the PutObject operation\n",
        "upload failed: the bucket said no\n",
    ],
)
def test_delta_a_refusal_is_never_retried(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    refusal: str,
) -> None:
    status, err, calls = _drive_port_in_process(
        tmp_path, monkeypatch, capfd, fail_times=99, fail_stderr=refusal
    )
    assert status == 1
    assert len([c for c in calls if c.startswith("aws\ts3\tsync")]) == 1
    assert "retrying (" not in err
    assert refusal in err


# --------------------------------------------------------------------------- The prune delta: each package tree keeps only what its index lists (operator ruling 2026-10-06) ---------------------------------------------------------------------------


# A build of v1.2.0: apt and rpm, rpm with its content-hashed repodata. `repomd.xml` names `ccc-primary.xml.gz`.
PRUNE_TREE = {
    "dist/repos/apt/pool/main/rdc_1.2.0_amd64.deb": "deb 1.2.0\n",
    "dist/repos/apt/dists/stable/InRelease": "inrelease 1.2.0\n",
    "dist/repos/apt/gpg.key": "key\n",
    "dist/repos/rpm/rdc-1.2.0-1.x86_64.rpm": "rpm 1.2.0\n",
    "dist/repos/rpm/repodata/ccc-primary.xml.gz": "primary 1.2.0\n",
    "dist/repos/rpm/repodata/repomd.xml": "repomd naming ccc-primary.xml.gz\n",
    "dist/repos/rpm/rediacc.repo": "[rediacc]\n",
    "dist/pages/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n',
}

# What a previous release left in the bucket: the old version's packages, stale rpm repodata, and trees the prune must never touch.
PRUNE_SEED = {
    "apt/edge/pool/main/rdc_1.0.0_amd64.deb": "deb 1.0.0\n",
    "apt/edge/pool/main/rdc_1.1.0_amd64.deb": "deb 1.1.0\n",
    "apt/edge/dists/stable/InRelease": "inrelease 1.1.0\n",
    "rpm/edge/rdc-1.1.0-1.x86_64.rpm": "rpm 1.1.0\n",
    "rpm/edge/repodata/aaa-primary.xml.gz": "primary 1.0.0\n",
    "rpm/edge/repodata/bbb-primary.xml.gz": "primary 1.1.0\n",
    # Never touched: other channels, cli/, npm/, an un-built format, and the snapshots.
    "apt/stable/pool/main/rdc_0.9.0_amd64.deb": "deb 0.9.0\n",
    "apt/edge-promoted/pool/main/rdc_1.1.0_amd64.deb": "deb 1.1.0\n",
    "apt/edgeX/old.deb": "other channel sharing a prefix\n",
    "apk/edge/rdc-1.1.0.apk": "apk 1.1.0\n",
    "cli/edge/rdc-linux-x64": "rdc\n",
    "cli/v1.1.0/rdc-linux-x64": "rdc 1.1.0\n",
    "npm/edge/rediacc-cli-1.1.0.tgz": "tgz\n",
}

UNTOUCHED = (
    "apt/stable/pool/main/rdc_0.9.0_amd64.deb",
    "apt/edge-promoted/pool/main/rdc_1.1.0_amd64.deb",
    "apt/edgeX/old.deb",
    "apk/edge/rdc-1.1.0.apk",
    "cli/edge/rdc-linux-x64",
    "cli/v1.1.0/rdc-linux-x64",
    "npm/edge/rediacc-cli-1.1.0.tgz",
)

PRUNE_REMOVE = (
    "apt/edge/pool/main/rdc_1.0.0_amd64.deb",
    "apt/edge/pool/main/rdc_1.1.0_amd64.deb",
    "rpm/edge/rdc-1.1.0-1.x86_64.rpm",
    "rpm/edge/repodata/aaa-primary.xml.gz",
    "rpm/edge/repodata/bbb-primary.xml.gz",
)

PLANT_NO_PRUNE = (
    "        _prune_trees(channel, endpoint, snapshot_version)\n",
    "        pass\n",
)
PLANT_PRUNE_BEFORE_THE_UPLOAD = (
    "        purge_urls = _upload_repos(channel, endpoint)\n",
    (
        "        _prune_trees(channel, endpoint, snapshot_version)\n"
        "        purge_urls = _upload_repos(channel, endpoint)\n"
    ),
)
PLANT_NO_CANDIDATES = (
    "            r2_promote.prune_tree(fmt, channel, built[fmt] | extra.get(fmt, set()), listed, run)\n",
    "            r2_promote.prune_tree(fmt, channel, built[fmt], listed, run)\n",
)


def _marker(version: str, packages: dict[str, int]) -> str:
    return channel_snapshot.marker_body(version, ["apt/dists/stable/InRelease"], packages)


def _prune_run(
    tmp_path: pathlib.Path,
    *,
    tree: dict[str, str] | None = None,
    seed: dict[str, str] | None = None,
    plant: tuple[str, str] | None = None,
    **extra: typing.Any,
):
    root = fixture(tmp_path, PRUNE_TREE if tree is None else tree)
    for key, body in (PRUNE_SEED if seed is None else seed).items():
        target = root / "new-s3" / RELEASES_BUCKET / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    if plant is not None:
        port_copy = root / ".ci" / "rediacc_ci" / "deploy" / PORT.name
        source = port_copy.read_text(encoding="utf-8")
        assert source.count(plant[0]) == 1, "the plant did not apply; the control is broken"
        port_copy.write_text(source.replace(plant[0], plant[1], 1), encoding="utf-8")
    proc, calls = _run(root, "new", **extra)
    base = root / "new-s3" / RELEASES_BUCKET
    keys = {str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()}
    return proc, calls, keys


def _prune_problems(keys: set[str]) -> list[str]:
    """The contract, as sentences; empty when it holds: the build is all there, every stale package and repodata file is gone, and nothing outside apt/edge/ and rpm/edge/ moved."""
    problems = []
    for rel in PRUNE_TREE:
        if rel.startswith("dist/repos/"):
            fmt, _, tail = rel[len("dist/repos/") :].partition("/")
            if "%s/edge/%s" % (fmt, tail) not in keys:
                problems.append("current file missing: %s/edge/%s" % (fmt, tail))
    problems += ["stale file kept: %s" % key for key in PRUNE_REMOVE if key in keys]
    problems += ["outside the tree, deleted: %s" % key for key in UNTOUCHED if key not in keys]
    return problems


def test_prune_deletes_the_old_versions_and_stale_repodata_and_keeps_the_build(
    tmp_path: pathlib.Path,
) -> None:
    proc, _calls, keys = _prune_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _prune_problems(keys) == []
    # The files repomd.xml names are kept; the hashes of earlier builds are not.
    assert "rpm/edge/repodata/ccc-primary.xml.gz" in keys
    assert "rpm/edge/repodata/repomd.xml" in keys
    assert "Pruned apt/edge/: 2 stale object(s) deleted, 3 kept\n" in proc.stdout
    assert "Pruned rpm/edge/: 3 stale object(s) deleted, 4 kept\n" in proc.stdout
    assert port.KEEPS_ONLY_WHAT_THE_INDEX_LISTS is True


def test_mutation_control_the_old_sync_without_a_prune_is_caught(tmp_path: pathlib.Path) -> None:
    """PLANT THE OLD BEHAVIOUR: no prune, as the twin's `aws s3 sync` without `--delete` ran. The contract test must see every stale file."""
    proc, _calls, keys = _prune_run(tmp_path, plant=PLANT_NO_PRUNE)
    assert proc.returncode == 0, proc.stderr
    assert sorted(_prune_problems(keys)) == sorted("stale file kept: %s" % k for k in PRUNE_REMOVE)


def test_prune_runs_after_every_upload_and_the_purge(tmp_path: pathlib.Path) -> None:
    """UPLOAD FIRST, DELETE SECOND: every delete in the call log comes after the last sync, the last cp and the purge."""
    proc, calls, _keys = _prune_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = calls.splitlines()
    deletes = [i for i, line in enumerate(lines) if line.startswith("aws\ts3api\tdelete-objects")]
    writes = [
        i
        for i, line in enumerate(lines)
        if line.startswith(("aws\ts3\tsync", "aws\ts3\tcp\t<tmp>", "curl\t"))
    ]
    assert deletes
    assert writes
    assert min(deletes) > max(writes), calls


def test_mutation_control_a_prune_before_the_upload_deletes_nothing(tmp_path: pathlib.Path) -> None:
    """PLANT a prune that runs BEFORE the upload: the listing does not yet hold the build, so the INCOMPLETE floor refuses with nothing deleted. That is the floor that keeps a delete from ever racing the upload it depends on."""
    proc, calls, keys = _prune_run(tmp_path, plant=PLANT_PRUNE_BEFORE_THE_UPLOAD)
    assert proc.returncode == 1
    assert "INCOMPLETE: " in proc.stderr
    assert "delete-objects" not in calls
    assert all(key in keys for key in PRUNE_REMOVE)


def test_prune_refuses_when_the_listing_lacks_a_file_it_just_uploaded(
    tmp_path: pathlib.Path,
) -> None:
    proc, calls, keys = _prune_run(tmp_path, FAKE_AWS_DROP_SYNC_MATCH="ccc-primary")
    assert proc.returncode == 1
    assert (
        "INCOMPLETE: 1 file(s) of dist/repos/rpm are not listed under rpm/edge/ after the upload"
        in proc.stderr
    )
    assert "rpm/edge/repodata/aaa-primary.xml.gz" in keys
    assert not any(line.startswith("DELETE\trpm/") for line in calls.splitlines())


def test_prune_keeps_the_packages_of_a_promotion_candidate(tmp_path: pathlib.Path) -> None:
    """Stable is at v1.0.0 and v1.1.0 has a sealed snapshot, so `check_soak_period` may still select v1.1.0 and its promote copies its packages from apt/edge/: they stay. v1.0.0's do not (not newer than stable), and v1.1.0's metadata is not kept (the snapshot holds its own copy)."""
    seed = {
        **PRUNE_SEED,
        "cli/stable/manifest.json": '{"version":"1.0.0"}\n',
        "snapshots/v1.1.0/.complete": _marker(
            "1.1.0",
            {"apt/pool/main/rdc_1.1.0_amd64.deb": 10, "rpm/rdc-1.1.0-1.x86_64.rpm": 10},
        ),
        "snapshots/v1.0.0/.complete": _marker("1.0.0", {"apt/pool/main/rdc_1.0.0_amd64.deb": 10}),
    }
    proc, _calls, keys = _prune_run(tmp_path, seed=seed)
    assert proc.returncode == 0, proc.stderr
    assert "apt/edge/pool/main/rdc_1.1.0_amd64.deb" in keys
    assert "rpm/edge/rdc-1.1.0-1.x86_64.rpm" in keys
    assert "apt/edge/pool/main/rdc_1.0.0_amd64.deb" not in keys
    assert "rpm/edge/repodata/bbb-primary.xml.gz" not in keys
    assert (
        "Prune keeps v1.1.0's packages: a promotion candidate, newer than stable v1.0.0\n"
        in proc.stdout
    )
    assert "v1.0.0's packages" not in proc.stdout


def test_mutation_control_a_keep_set_without_candidates_is_caught(tmp_path: pathlib.Path) -> None:
    seed = {
        **PRUNE_SEED,
        "cli/stable/manifest.json": '{"version":"1.0.0"}\n',
        "snapshots/v1.1.0/.complete": _marker("1.1.0", {"apt/pool/main/rdc_1.1.0_amd64.deb": 10}),
    }
    proc, _calls, keys = _prune_run(tmp_path, seed=seed, plant=PLANT_NO_CANDIDATES)
    assert proc.returncode == 0, proc.stderr
    assert "apt/edge/pool/main/rdc_1.1.0_amd64.deb" not in keys, "the candidate's package went"


def test_prune_keeps_every_candidate_when_the_stable_manifest_is_unreadable(
    tmp_path: pathlib.Path,
) -> None:
    seed = {
        **PRUNE_SEED,
        "snapshots/v1.0.0/.complete": _marker("1.0.0", {"apt/pool/main/rdc_1.0.0_amd64.deb": 10}),
    }
    proc, _calls, keys = _prune_run(tmp_path, seed=seed)
    assert proc.returncode == 0, proc.stderr
    assert "apt/edge/pool/main/rdc_1.0.0_amd64.deb" in keys
    assert "the stable version is unknown (cli/stable/manifest.json unreadable)" in proc.stdout


def test_prune_refuses_when_a_candidates_marker_cannot_be_read(tmp_path: pathlib.Path) -> None:
    seed = {
        **PRUNE_SEED,
        "cli/stable/manifest.json": '{"version":"1.0.0"}\n',
        "snapshots/v1.1.0/.complete": "not json\n",
    }
    proc, calls, keys = _prune_run(tmp_path, seed=seed)
    assert proc.returncode == 1
    assert "prune refused, nothing deleted" in proc.stderr
    assert "delete-objects" not in calls
    assert all(key in keys for key in PRUNE_REMOVE)


def test_prune_ignores_snapshots_on_a_pr_channel(tmp_path: pathlib.Path) -> None:
    seed = {
        "apt/pr-7/pool/main/rdc_1.1.0_amd64.deb": "deb 1.1.0\n",
        "snapshots/v1.1.0/.complete": _marker("1.1.0", {"apt/pool/main/rdc_1.1.0_amd64.deb": 10}),
    }
    proc, calls, keys = _prune_run(tmp_path, seed=seed, CHANNEL="pr-7")
    assert proc.returncode == 0, proc.stderr
    assert "apt/pr-7/pool/main/rdc_1.1.0_amd64.deb" not in keys
    assert "--prefix\tsnapshots/" not in calls


def test_prune_deletes_nothing_for_an_empty_build_directory(tmp_path: pathlib.Path) -> None:
    """THE FLOOR: `dist/repos/apt` exists and holds nothing. The upload's own VACUOUS guard refuses before any write, so nothing is listed and nothing deleted."""
    root = fixture(tmp_path, {"dist/pages/install.sh": "x\n"})
    (root / "dist" / "repos" / "apt").mkdir(parents=True)
    target = root / "new-s3" / RELEASES_BUCKET / "apt" / "edge" / "old.deb"
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    proc, calls = _run(root, "new")
    assert proc.returncode == 1
    assert "VACUOUS: dist/repos/apt exists but holds 0 file(s)" in proc.stderr
    assert "list-objects-v2" not in calls
    assert "delete-objects" not in calls
    assert target.is_file()


def test_prune_deletes_nothing_for_a_format_that_was_not_built(tmp_path: pathlib.Path) -> None:
    proc, calls, keys = _prune_run(
        tmp_path, tree={"dist/pages/install.sh": "x\n"}, seed={"apt/edge/old.deb": "old\n"}
    )
    assert proc.returncode == 0, proc.stderr
    assert "apt/edge/old.deb" in keys
    assert "list-objects-v2" not in calls
    assert "delete-objects" not in calls


def test_prune_fails_the_run_on_a_per_key_delete_error(tmp_path: pathlib.Path) -> None:
    """`delete-objects` exits 0 when a key fails; the reply's `Errors` are read and fail the run."""
    proc, _calls, _keys = _prune_run(tmp_path, FAKE_AWS_DELETE_ERROR_MATCH="rdc_1.0.0")
    assert proc.returncode == 1
    assert "delete failed: apt/edge/pool/main/rdc_1.0.0_amd64.deb: AccessDenied" in proc.stderr


def test_prune_tree_refuses_anything_outside_a_package_tree() -> None:
    run = r2_promote.Transfers("t", "https://e", 0.0)
    for dir_name, channel in (("cli", "edge"), ("npm", "edge"), ("apt", "edge/x"), ("apt", "")):
        with pytest.raises(r2_promote.PromoteError):
            r2_promote.prune_tree(dir_name, channel, {"a"}, [], run)
    with pytest.raises(r2_promote.PromoteError):
        r2_promote.prune_tree("apt", "edge", set(), [], run)


def test_delete_argv_batches_stay_under_the_single_argument_limit() -> None:
    keys = ["rpm/edge/repodata/%s-filelists.sqlite.bz2" % ("f" * 64)] * r2_promote.DELETE_BATCH
    argv = r2_promote.delete_argv(keys, "https://e")
    assert argv[:3] == ["aws", "s3api", "delete-objects"]
    assert max(len(a.encode()) for a in argv) < 128 * 1024
    assert json.loads(argv[argv.index("--delete") + 1])["Quiet"] is True
    assert r2_promote.delete_errors("") == []
    assert r2_promote.delete_errors('{"Errors":[{"Key":"k","Code":"C","Message":"m"}]}') == [
        "k: C m"
    ]
