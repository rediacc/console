#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/promote-r2-to-stable.sh`, with the transfer made server-side (operator ruling 2026-09-26).

The soak-gated promotion: copies every R2 release channel from `edge/` to `stable/` in two phases, metadata last. Driven by `promote-stable.yml` after the 7-day soak. The hotfix lane that skips the soak is `rediacc_ci.deploy.promote_r2_to_stable_hotfix`.

WHY TWO PHASES, carried over from the twin's header because it is the reason this file exists rather than a second copy of the hotfix: a package manager decides "there is a new version" from METADATA and then fetches the bytes that metadata names. Uploading everything at once lets a client see the new-version signal minutes before the binaries land, which surfaces as 404s and
"Mirror sync in progress?". Phase 1 uploads bytes; phase 2 uploads metadata, and within phase 2 the signing/hashing metadata goes AFTER the metadata it hashes, so a Release/InRelease hash can never disagree with the bytes on R2.
The port keeps that order with server-side copies in place of uploads, and each phase finishes before the next starts.

-----------------------------------------------------------------------------
THE BYTES NEVER LEAVE R2
-----------------------------------------------------------------------------
The twin downloads each `<dir>/edge/` tree to the runner and syncs it back up to `<dir>/stable/`. With about 67 GB of release history under the five trees (2026-09-25) that took hours and could outlive the job's minted R2 token. This port copies server-side with one `aws s3api copy-object` per object; `r2_promote`'s docstring carries the plan, the reason `aws s3 cp/sync` cannot do an s3-to-s3 copy on R2, the metadata the copies carry and R2's CopyObject size limit. The phase filters below are the twin's, evaluated with aws-cli's rule (`r2_promote.keep`) against the edge listing instead of being handed to `aws s3 sync`.

The four channel pointers (`cli/install.sh`, `cli/install.ps1`, `rpm/rediacc.repo`, `archlinux/rediacc.conf`) are excluded from every phase, fetched from edge, stamped for stable (`channel_stamp`) and uploaded AFTER phase 2 (`r2_promote.POINTERS_GO_LAST` says why). They are the only objects the runner downloads.

-----------------------------------------------------------------------------
WHAT CHANGED AGAINST THE TWIN, BY NAME
-----------------------------------------------------------------------------
  1. A FILE EXCLUDED IN PHASE 1 AND NAMED BY NO PHASE-2 INCLUDE IS STILL NEVER
     PROMOTED (`cli/edge/latest-linux.yml` against `--exclude 'latest*.yml'`,
     `rpm/edge/repodata/comps.xml` against `--exclude 'repodata/*'`). The twin
     purged such files anyway, because it built the purge list from its
     download. The port builds it from the stable LISTING taken after the copy,
     so it purges only what was promoted, and refuses (`INCOMPLETE:`) when a
     promoted key is missing from that listing.
     `PHASE_FILTERED_FILES_ARE_NEVER_PROMOTED` / `PURGE_LIST_IS_BUILT_FROM_THE_STABLE_LISTING`.
  2. The `VACUOUS:` floor runs on the edge listing BEFORE anything is copied (the twin counted after uploading).
  3. There is no fixed `/tmp/promote-<dir>` stage any more, so nothing a failed run leaves behind can be promoted by the next one. The pointer stage is a fresh `mkdtemp` per run, removed on exit.
  4. The purge order is the edge listing's key order, not `find`'s directory order.

`$EP` IS UNQUOTED IN THE TWIN, so bash word-splits it into `--endpoint-url` and the endpoint; `r2_promote.endpoint_args` reproduces the split.

-----------------------------------------------------------------------------
FOUR `${VAR:?msg}` GUARDS, ONE DIVERGENCE
-----------------------------------------------------------------------------
bash's own refusal names the bash FILE and a bash LINE NUMBER and then the twin's message, which already begins with the script name. This port prints the `VAR: msg` half, on the same stream, with the same exit status 1. The ORDER is kept, and `require_cmd aws` runs BEFORE all four.

`EDGE_VERSION` IS THE ODD ONE OUT: it is used only in the closing log line. A port that treated it as optional would print `edge v -> stable` on a run the twin refuses outright.

NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST: `.ci/rediacc_ci/tests/test_deploy_promote_r2_to_stable.py` puts recording fakes for `aws` and `curl` on a scratch PATH over an on-disk bucket fixture.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.core import common
from rediacc_ci.deploy import channel_stamp, r2_promote

# The twin's own name, carried in its four guard messages. A literal, because the bytes must survive the port.
SELF = "promote-r2-to-stable.sh"

# `for dir in cli apt rpm apk archlinux` (twin :68). ORDER MATTERS to the call log and the purge list.
CHANNEL_DIRS = ("cli", "apt", "rpm", "apk", "archlinux")

BUCKET = r2_promote.BUCKET
PUBLIC_HOST = r2_promote.PUBLIC_HOST
CC_MUTABLE = r2_promote.CC_MUTABLE

# `META_EXCLUDES` (twin :95-105), flattened to the argv order the twin expands it into. EVERY PAIR AND ITS POSITION MATTERS: `r2_promote.keep` applies include and exclude rules in order with the last match winning, as aws-cli does, so a reordered list is a different filter even when the set is identical.
META_EXCLUDES: tuple[str, ...] = (
    "--exclude",
    "Packages*",
    "--exclude",
    "Release*",
    "--exclude",
    "InRelease",
    "--exclude",
    "repodata/*",
    "--exclude",
    "APKINDEX.tar.gz",
    "--exclude",
    "*.db.tar.gz",
    "--exclude",
    "*.files.tar.gz",
    "--exclude",
    "rediacc.db",
    "--exclude",
    "rediacc.files",
    "--exclude",
    "latest*.yml",
    "--exclude",
    "latest.json",
    "--exclude",
    "manifest.json",
    "--exclude",
    "install.sh",
    "--exclude",
    "install.ps1",
    "--exclude",
    "*.repo",
    "--exclude",
    "*.conf",
    "--exclude",
    "rediacc-cli-latest.tgz",
    "--exclude",
    "versions.json",
)

# Phase 2, per directory, as an ORDERED tuple of filter argv fragments (twin :112-158). One fragment is one phase, finished before the next starts, so the length of a directory's tuple is how many phase-2 steps it takes: `apt` and `rpm` make two because their signing metadata hashes their listing metadata, `apk`, `archlinux` and `cli` make one. A directory absent from this table would make none, and
# none is absent today.
PHASE_TWO: dict[str, tuple[tuple[str, ...], ...]] = {
    # 2a: Packages / Packages.gz (hashes of the .deb files phase 1 uploaded). 2b: Release / InRelease / Release.gpg (hashes of phase 2a).
    "apt": (
        ("--exclude", "*", "--include", "Packages*"),
        ("--exclude", "*", "--include", "Release*", "--include", "InRelease"),
    ),
    # 2a: primary / filelists / other (hashed by 2b's repomd). 2b: repomd.xml + signatures + rediacc.repo (the channel pointer).
    "rpm": (
        (
            "--exclude",
            "*",
            "--include",
            "repodata/primary*",
            "--include",
            "repodata/filelists*",
            "--include",
            "repodata/other*",
        ),
        ("--exclude", "*", "--include", "repodata/repomd.xml*", "--include", "*.repo"),
    ),
    # APKINDEX references the .apk files in the same directory (phase 1).
    "apk": (("--exclude", "*", "--include", "APKINDEX.tar.gz"),),
    # .db/.files reference the .pkg.tar.zst in the same directory (phase 1).
    "archlinux": (
        (
            "--exclude",
            "*",
            "--include",
            "*.db.tar.gz",
            "--include",
            "*.files.tar.gz",
            "--include",
            "rediacc.db",
            "--include",
            "rediacc.files",
            "--include",
            "*.conf",
        ),
    ),
    # manifest + latest.json + the re-baked install scripts.
    "cli": (
        (
            "--exclude",
            "*",
            "--include",
            "manifest.json",
            "--include",
            "latest.json",
            "--include",
            "install.sh",
            "--include",
            "install.ps1",
            "--include",
            "versions.json",
        ),
    ),
}

# The per-directory channel pointers and their stamps, shared with the hotfix sibling (#b22efec4). `cli` rewrites two files, `rpm` and `archlinux` one each, `apt` and `apk` none.
INSTALL_SED = channel_stamp.INSTALL_SED
CHANNEL_SED = channel_stamp.CHANNEL_SED
REWRITES = channel_stamp.REWRITES

# `"$SCRIPT_DIR/cf-purge-urls.sh"` (twin :180), where SCRIPT_DIR is `.ci/scripts/deploy`.
PURGE_SCRIPT_RELATIVE = ".ci/scripts/deploy/cf-purge-urls.sh"

# The four `${VAR:?msg}` guards (twin :58-61), in order, as (name, message).
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("AWS_ACCESS_KEY_ID", "%s: AWS_ACCESS_KEY_ID must be set" % SELF),
    ("AWS_SECRET_ACCESS_KEY", "%s: AWS_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
    ("EDGE_VERSION", "%s: EDGE_VERSION must be set" % SELF),
)

# The named facts in the module docstring, as constants so a test can assert each by name.
PHASE_FILTERED_FILES_ARE_NEVER_PROMOTED = True
PURGE_LIST_IS_BUILT_FROM_THE_STABLE_LISTING = True
BULK_IS_SERVER_SIDE = r2_promote.BULK_IS_SERVER_SIDE


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """A run that ends with `code`, its explanation already printed."""

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def script_dir() -> str:
    """`SCRIPT_DIR` (twin :56), by location rather than by cwd. `abspath`, NOT `realpath`: bash's `cd` is logical."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, os.path.dirname(PURGE_SCRIPT_RELATIVE))


def environment() -> dict[str, str]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`: `check:ci-python-env-registry` derives a module's declared inputs from literal `os.environ` reads in its AST, and a materialised copy is invisible to it.
    """
    return {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        "CLOUDFLARE_R2_ENDPOINT": os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        "EDGE_VERSION": os.environ.get("EDGE_VERSION", ""),
        # `${CLOUDFLARE_ZONE_ID:-}` (twin :180): unset and empty are one argument.
        "CLOUDFLARE_ZONE_ID": os.environ.get("CLOUDFLARE_ZONE_ID", ""),
        # Seconds between transfer retries; tests set 0. Not in the twin (Rule T retry, #4175e786).
        "PROMOTE_RETRY_DELAY_S": os.environ.get("PROMOTE_RETRY_DELAY_S", "10"),
    }


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The four guards, in the twin's order. Raises on the FIRST missing or empty one."""
    values: dict[str, str] = {}
    for name, message in REQUIRED_ENV:
        value = env.get(name, "")
        if not value:
            raise MissingEnvError(name, message)
        values[name] = value
    return values


def endpoint_args(endpoint: str) -> list[str]:
    """`$EP` unquoted (twin :65)."""
    return r2_promote.endpoint_args(endpoint)


def phases(dir_name: str) -> tuple[tuple[str, ...], ...]:
    """Phase 1 (`META_EXCLUDES`) then the directory's phase-2 arms, in order."""
    return (META_EXCLUDES, *PHASE_TWO.get(dir_name, ()))


def purge_argv(zone: str) -> list[str]:
    """`"$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"` (twin :180). An UNSET zone is an EMPTY ARGUMENT, and cf-purge-urls.sh refuses it after the promotion has happened, which is the twin's stated design."""
    return [os.path.join(script_dir(), os.path.basename(PURGE_SCRIPT_RELATIVE)), "--zone", zone]


def channel_url(dir_name: str, relative: str) -> str:
    """`https://releases.rediacc.com/<dir>/stable/<relative>` (twin :168)."""
    return r2_promote.channel_url(dir_name, relative)


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor, so `Promoting ...` lands before the child's output."""
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One command with BOTH streams inherited."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _promote_dirs(endpoint: str) -> list[str]:
    """The `for dir in cli apt rpm apk archlinux` loop. Returns the purge URLs."""
    run = r2_promote.Transfers(SELF, endpoint, float(environment()["PROMOTE_RETRY_DELAY_S"] or "0"))
    stage_root = tempfile.mkdtemp(prefix="promote-pointers-")
    urls: list[str] = []
    try:
        for dir_name in CHANNEL_DIRS:
            print("Promoting %s/edge/ -> %s/stable/ (2-phase)" % (dir_name, dir_name))
            _flush()
            urls += r2_promote.promote_tree(dir_name, phases(dir_name), stage_root, run)
    except r2_promote.PromoteError as exc:
        raise BashExitError(exc.status) from exc
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (twin :178-181)."""
    payload = "".join(url + "\n" for url in urls)
    argv = purge_argv(zone)
    try:
        status = _run(argv, input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT: bash would report it with status 127.
        print("%s: %s: %s" % (SELF, argv[0], exc.strerror), file=sys.stderr)
        raise BashExitError(127) from exc
    if status:
        raise BashExitError(status)


def main(argv: list[str]) -> int:
    del argv  # the twin takes no argv, and says so at :30-31

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    env = environment()

    try:
        values = require_env(env)
    except MissingEnvError as exc:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print("%s: %s" % (exc.name, exc.message), file=sys.stderr)
        return 1

    try:
        purge_urls = _promote_dirs(values["CLOUDFLARE_R2_ENDPOINT"])
    except BashExitError as exc:
        return exc.code

    print("R2 promotion complete: edge v%s -> stable" % values["EDGE_VERSION"])

    if purge_urls:
        try:
            _purge(purge_urls, env["CLOUDFLARE_ZONE_ID"])
        except BashExitError as exc:
            return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
