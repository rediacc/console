#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/promote-r2-to-stable.sh`.

The soak-gated promotion: copies every R2 release channel from `edge/` to `stable/` with a two-phase, metadata-last upload. Driven by `promote-stable.yml` after the 7-day soak. The hotfix lane that skips the soak is a different, single-phase script, ported beside this one as `rediacc_ci.deploy.promote_r2_to_stable_hotfix`.

WHY TWO PHASES, carried over from the twin's header because it is the reason this file exists rather than a second copy of the hotfix: a package manager decides "there is a new version" from METADATA and then fetches the bytes that metadata names. Uploading everything at once lets a client see the new-version signal minutes before the binaries land, which surfaces as 404s and
"Mirror sync in progress?". Phase 1 uploads bytes; phase 2 uploads metadata, and within phase 2 the signing/hashing metadata goes AFTER the metadata it hashes, so a Release/InRelease hash can never disagree with the bytes on R2.

-----------------------------------------------------------------------------
THE SIBLING SHARES REAL LOGIC WITH THIS FILE AND IT IS DELIBERATELY NOT
FACTORED OUT
-----------------------------------------------------------------------------
The full argument is in `promote_r2_to_stable_hotfix.py`'s docstring and is not repeated here. The short form: the two BASH twins share nothing but `common.sh`'s `require_cmd` and `sed_in_place`, there is no promote-specific bash library and `release-state-validator.sh` is reached by neither, so a shared Python helper would have no bash counterpart and would let an edit to one twin
silently change the other's port. The four near-identical blocks are the download leg, the `VACUOUS:` floor, the `find`-driven purge loop and the closing purge pipeline. Collapsing them belongs to the cutover box that deletes both bash files.

-----------------------------------------------------------------------------
NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST
-----------------------------------------------------------------------------
`aws` and (through `cf-purge-urls.sh`) `curl` are the two external tools that carry a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_promote_r2_to_stable.py`) puts RECORDING FAKES for both on a scratch PATH, with an on-disk fixture standing in for the bucket. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says
in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE FOR THIS SCRIPT, more than for most. Everything it prints is five `Promoting ...` lines plus one closing line, none of which is derived from what moved; the ENTIRE observable effect is the twelve `aws` invocations and the exclude/include lists they carry. Two implementations can print identical stdout while uploading `Release*` before
`Packages*`, which is precisely the ordering the twin's design is about.

-----------------------------------------------------------------------------
`find` AND `sed` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`find` because ITS ORDER IS THE PURGE ORDER and it is DIRECTORY order, not sorted order (measured on the fixture 2026-09-13: `rdc-linux-x64, manifest.json, latest.json, install.sh, install.ps1` under `cli/`). `sed`, through `core.common.sed_in_place`, because the substitutions are regex with `|` delimiters. `cf-purge-urls.sh` is invoked as the bash script the twin invokes,
for the reason `upload_repos_to_r2.py` gives: agreement with the live twin
includes that script's exact bytes.

`$EP` IS UNQUOTED IN THE TWIN, so bash word-splits it into `--endpoint-url` and the endpoint. `endpoint_args` reproduces the split rather than hard-coding two elements; pathname expansion on that same unquoted word is not reproduced and is unreachable for an https URL. Same ruling and same wording as the sibling.

-----------------------------------------------------------------------------
FOUR FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL FOUR ARE REPRODUCED
-----------------------------------------------------------------------------
  1. A FILE EXCLUDED IN PHASE 1 AND NAMED BY NO PHASE-2 INCLUDE IS NEVER
     PROMOTED, AND IS STILL PURGED AS THOUGH IT HAD BEEN. The phase-1 exclude
     list is shared by all five directories, but each directory's phase 2
     re-includes only its OWN metadata. So `cli/edge/latest-linux.yml` matches
     the shared `--exclude 'latest*.yml'` and appears in none of `cli`'s phase-2
     includes (`manifest.json latest.json install.sh install.ps1
     versions.json`); `rpm/edge/repodata/comps.xml` matches `--exclude
     'repodata/*'` and none of rpm's two phase-2 arms. Driven 2026-09-13 against
     the fixture: both files stayed at `edge/`, both appeared in the Cloudflare
     purge body, and the run printed `R2 promotion complete` and exited 0. The
     hotfix lane, a straight recursive copy, promotes both. THE VACUITY FLOOR
     CANNOT SEE THIS, because it counts files in the LOCAL `$TMP` (everything
     downloaded) rather than files uploaded.
     `PHASE_FILTERED_FILES_ARE_PURGED_BUT_NEVER_UPLOADED` names it.
  2. THE PURGE LIST IS BUILT FROM WHAT WAS DOWNLOADED, NOT FROM WHAT WAS
     UPLOADED. That is the mechanism behind fact 1 and is worth naming on its
     own, because it means the URL count in the log is a count of the SOURCE
     channel, and a reader takes it for a count of the promotion.
  3. THE `VACUOUS:` FLOOR SITS AFTER THE UPLOADS IT IS MEANT TO GUARD. Download,
     phase 1, phase 2, THEN count. An empty `<dir>/edge/` has already been
     through `aws s3 sync` before anything checks, and what stops the run is
     whatever `aws` says about a local source directory that was never created.
     The floor is reachable when `$TMP` EXISTS and is empty, which fact 4 shows
     is a real state. `VACUITY_FLOOR_RUNS_AFTER_THE_UPLOAD` names it.
  4. `/tmp/promote-<dir>` IS A FIXED PATH AND IS ONLY REMOVED ON SUCCESS, so any
     early exit leaves it behind and THE NEXT RUN UPLOADS ITS CONTENTS TO
     PRODUCTION. Driven 2026-09-13 on the sibling, which shares the mechanism
     line for line: a stale `old-0.0.1.apk` left in `/tmp/promote-apk` reached
     `apk/stable/`, exit 0, no warning. `STALE_TMP_IS_PROMOTED` names it.

None is repaired here. This wave's acceptance rule is agreement with the live twin, and changing what the release promotion uploads is a cutover-box decision rather than a port's.

-----------------------------------------------------------------------------
`[[ -f "$f" ]] && sed_in_place ...` DOES NOT END THE RUN WHEN THE FILE IS
ABSENT, AND THAT WAS VERIFIED RATHER THAN ASSUMED
-----------------------------------------------------------------------------
Two of the three per-directory rewrites are written as AND-lists rather than as `if`. Under `set -e` a command that FAILS before the final `&&` is exempt, so a `rpm/edge/` with no `rediacc.repo` skips the rewrite and carries on. Driven 2026-09-13 with all three files removed from the fixture: exit 0, five directories promoted. Worth stating because the opposite reading is plausible
and would have made this port refuse a channel the twin publishes.

-----------------------------------------------------------------------------
FOUR `${VAR:?msg}` GUARDS, ONE DIVERGENCE
-----------------------------------------------------------------------------
bash's own refusal names the bash FILE and a bash LINE NUMBER and then the twin's message, which already begins with the script name. This port prints the `VAR: msg` half, on the same stream, with the same exit status 1. Identical ruling to `deploy/delete_r2_channel.py`, `deploy/upload_repos_to_r2.py` and the sibling. The ORDER is kept, and `require_cmd aws` runs BEFORE all four.

`EDGE_VERSION` IS THE ODD ONE OUT: it is `EDGE_VERSION="${EDGE_VERSION:?...}"`,
an assignment rather than a bare `:`, and it is used only in the closing log line. A port that treated it as optional would print `edge v -> stable` on a run the twin refuses outright.

K=5 LEDGER: `.ci/shadow/w7p6-promote-r2-to-stable.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci.core import common

# The twin's own name, carried in its four guard messages. A literal, because the bytes must survive the port.
SELF = "promote-r2-to-stable.sh"

# `for dir in cli apt rpm apk archlinux` (twin :68). ORDER MATTERS to both the call log and the purge list, which is how this port is proved equivalent.
CHANNEL_DIRS = ("cli", "apt", "rpm", "apk", "archlinux")

# `BUCKET="rediacc-releases"` (twin :64) and the public host (twin :168), both
# hard-coded in the twin.
BUCKET = "rediacc-releases"
PUBLIC_HOST = "https://releases.rediacc.com"

# `CC_MUTABLE="no-cache"` (twin :67).
CC_MUTABLE = "no-cache"

# `TMP="/tmp/promote-${dir}"` (twin :71). A FIXED path, which is fact 4 in the
# module docstring.
TMP_PREFIX = "/tmp/promote-"

# `META_EXCLUDES` (twin :95-105), flattened to the argv order the twin expands it into. EVERY PAIR AND ITS POSITION IS OBSERVABLE: aws applies include and exclude rules in order with the last match winning, so a reordered list is a different filter even when the set is identical.
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

# Phase 2, per directory, as an ORDERED tuple of filter argv fragments (twin :112-158). One fragment is one `aws s3 sync` call, so the length of a directory's tuple is how many phase-2 calls it makes: `apt` and `rpm` make two because their signing metadata hashes their listing metadata, `apk`, `archlinux` and `cli` make one. A directory absent from this table would make none, and
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

# The per-directory channel rewrites (twin :74-92), applied to the LOCAL copy before phase 2. `cli` rewrites two files with two expressions each; `rpm` and `archlinux` rewrite one file with one expression. A directory absent from this table rewrites nothing, which is `apt` and `apk`.
INSTALL_SED = (
    "s|REDIACC_CHANNEL:-edge|REDIACC_CHANNEL:-stable|g",
    's|} else { "edge" }|} else { "stable" }|g',
)
CHANNEL_SED = "s|/edge/|/stable/|g"
REWRITES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "cli": (
        ("install.sh", INSTALL_SED),
        ("install.ps1", INSTALL_SED),
    ),
    "rpm": (("rediacc.repo", (CHANNEL_SED,)),),
    "archlinux": (("rediacc.conf", (CHANNEL_SED,)),),
}

# `"$SCRIPT_DIR/cf-purge-urls.sh"` (twin :180), where SCRIPT_DIR is `.ci/scripts/deploy`. Relative to the repository root so the cutover to `cf_purge_urls.py` is a one-line change in the box that owns it.
PURGE_SCRIPT_RELATIVE = ".ci/scripts/deploy/cf-purge-urls.sh"

# The four `${VAR:?msg}` guards (twin :58-61), in order, as (name, message).
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("AWS_ACCESS_KEY_ID", "%s: AWS_ACCESS_KEY_ID must be set" % SELF),
    ("AWS_SECRET_ACCESS_KEY", "%s: AWS_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
    ("EDGE_VERSION", "%s: EDGE_VERSION must be set" % SELF),
)

# The four facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
PHASE_FILTERED_FILES_ARE_PURGED_BUT_NEVER_UPLOADED = True
PURGE_LIST_IS_BUILT_FROM_THE_DOWNLOAD = True
VACUITY_FLOOR_RUNS_AFTER_THE_UPLOAD = True
STALE_TMP_IS_PROMOTED = True


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    Every `aws s3 cp`/`sync`, every `sed`, the floor's own `exit 1` and the final purge pipeline are all unguarded, so the failing program's own stderr is the only explanation the caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def script_dir() -> str:
    """`SCRIPT_DIR` (twin :56), by location rather than by cwd.

    The twin resolves `.ci/scripts/deploy` from its own `BASH_SOURCE`; this file sits at `.ci/rediacc_ci/deploy/`, three directories under the same root, so the arithmetic is identical and neither side depends on the caller's cwd. `abspath`, NOT `realpath`: bash's `cd` is logical, so a checkout reached through a symlink keeps the symlinked spelling on both sides.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, os.path.dirname(PURGE_SCRIPT_RELATIVE))


def environment() -> dict[str, str]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`, AND THE DIFFERENCE IS A GATE RATHER THAN A STYLE. `check:ci-python-env-registry` derives a module's declared inputs by walking its AST for literal `os.environ` subscripts and `.get` calls; a read that goes through a materialised copy or a local alias is INVISIBLE to it, and the module then reports zero inputs while depending on five. Measured 2026-09-13
    against the gate's own `derive`: with `dict(os.environ)` here this file contributed only `CLOUDFLARE_ZONE_ID`, the one name read at its own call site; with this function it contributes all five.

    `require_env` still takes a dict, so the guard logic stays a pure helper the differential can drive without an environment.
    """
    return {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        "CLOUDFLARE_R2_ENDPOINT": os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        "EDGE_VERSION": os.environ.get("EDGE_VERSION", ""),
        # `${CLOUDFLARE_ZONE_ID:-}` (twin :180): unset and empty are one argument.
        "CLOUDFLARE_ZONE_ID": os.environ.get("CLOUDFLARE_ZONE_ID", ""),
    }


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The four guards, in the twin's order. Returns the four values.

    Raises on the FIRST missing or empty one, because `: "${VAR:?}"` ends the
    shell there and the later guards never run.
    """
    values: dict[str, str] = {}
    for name, message in REQUIRED_ENV:
        value = env.get(name, "")
        if not value:
            raise MissingEnvError(name, message)
        values[name] = value
    return values


def endpoint_args(endpoint: str) -> list[str]:
    """`$EP` unquoted (twin :65). See the module docstring."""
    return ("--endpoint-url %s" % endpoint).split()


def download_argv(dir_name: str, tmp: str, endpoint: str) -> list[str]:
    """`aws s3 cp s3://<bucket>/<dir>/edge/ <tmp>/ $EP --recursive --quiet` (twin :72)."""
    return [
        "aws",
        "s3",
        "cp",
        "s3://%s/%s/edge/" % (BUCKET, dir_name),
        tmp + "/",
        *endpoint_args(endpoint),
        "--recursive",
        "--quiet",
    ]


def sync_argv(dir_name: str, tmp: str, endpoint: str, filters: tuple[str, ...]) -> list[str]:
    """One `aws s3 sync <tmp>/ s3://<bucket>/<dir>/stable/ ...` (twin :108-158).

    Phase 1 passes `META_EXCLUDES`; each phase-2 arm passes its own fragment. The two are the SAME call shape with a different filter tail, which is why they share a builder here even though the twin writes them out separately: the difference between the phases is entirely the tail, and a reader comparing the call log should see that.
    """
    return [
        "aws",
        "s3",
        "sync",
        tmp + "/",
        "s3://%s/%s/stable/" % (BUCKET, dir_name),
        *endpoint_args(endpoint),
        "--quiet",
        "--cache-control",
        CC_MUTABLE,
        *filters,
    ]


def purge_argv(zone: str) -> list[str]:
    """`"$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"` (twin :180).

    `:-` and not `:?`, so an UNSET zone becomes an EMPTY ARGUMENT rather than a refusal here. cf-purge-urls.sh then refuses on its own account, and under `pipefail` that status is this script's, AFTER the promotion has already happened. That is the twin's stated design, not an oversight.
    """
    return [os.path.join(script_dir(), os.path.basename(PURGE_SCRIPT_RELATIVE)), "--zone", zone]


def channel_url(dir_name: str, relative: str) -> str:
    """`https://releases.rediacc.com/<dir>/stable/<relative>` (twin :168).

    `relative` is `${f#"$TMP"/}`, a PREFIX STRIP rather than a basename, so a
    file in a subdirectory keeps its directories.
    """
    return "%s/%s/stable/%s" % (PUBLIC_HOST, dir_name, relative)


def strip_prefix(path: str, prefix: str) -> str:
    """`${f#"$TMP"/}`: remove it only when it is there, leave the rest alone.

    The `"$TMP"` is QUOTED inside the expansion, so it is a literal prefix and not a pattern.
    """
    return path.removeprefix(prefix)


def read_lines(text: str) -> list[str]:
    """`while IFS= read -r f; do ... done < <(find ...)`.

    A FINAL LINE WITH NO NEWLINE IS DROPPED, because `read` stores it and then returns non-zero at EOF so the loop body never runs for it.
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return lines


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS. bash `echo` writes through immediately; Python block-buffers stdout when it is a pipe and flushes at exit, so without this the `Promoting ...` lines land after the purge script's output instead of before it, on the same stream, with byte-identical content in a different order.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _find_files(directory: str) -> tuple[str, int]:
    """`find <dir> -type f`, and `... | wc -l` over the same output.

    THE TWIN RUNS `find` TWICE, once into `wc -l` for the vacuity floor (twin
    :166) and once into the URL loop (twin :167), and this returns both answers
    from ONE run. Safe in the direction that matters: two runs can only disagree
    if the directory changes between them, and if it did, the twin would report
    a count that does not match the URLs it then builds. On the path where the count is 0 the twin exits before its second `find`, so the ONE find here also matches how many times find's own stderr is emitted.

    The count is NEWLINES, which is what `wc -l` counts. find's status is DISCARDED, exactly as `|| true` discards it.
    """
    _flush()
    proc = subprocess.run(
        ["find", directory, "-type", "f"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stdout, proc.stdout.count("\n")


def _rewrite(dir_name: str, tmp: str) -> None:
    """The per-directory `case` rewrites (twin :74-92), on the LOCAL copy.

    `[[ -f "$f" ]] || continue` for `cli`, and `[[ -f ... ]] && sed_in_place ...`
    for the other two. An absent file is skipped by both spellings and does NOT
    end the run; see the module docstring, where that was driven rather than assumed.
    """
    for name, expressions in REWRITES.get(dir_name, ()):
        target = os.path.join(tmp, name)
        if not os.path.isfile(target):
            continue
        args: list[str] = []
        for expression in expressions:
            args += ["-e", expression]
        args.append(target)
        _flush()
        status = common.sed_in_place(args)
        if status:
            raise BashExitError(status)


def _promote_dirs(endpoint: str) -> list[str]:
    """The `for dir in cli apt rpm apk archlinux` loop (twin :68-176). Returns URLs."""
    urls: list[str] = []
    for dir_name in CHANNEL_DIRS:
        print("Promoting %s/edge/ -> %s/stable/ (2-phase)" % (dir_name, dir_name))
        tmp = TMP_PREFIX + dir_name

        status = _run(download_argv(dir_name, tmp, endpoint))
        if status:
            raise BashExitError(status)

        _rewrite(dir_name, tmp)

        # Phase 1: binaries and packages, no metadata.
        status = _run(sync_argv(dir_name, tmp, endpoint, META_EXCLUDES))
        if status:
            raise BashExitError(status)

        # Phase 2: the metadata that flips a client's view to the new version.
        for filters in PHASE_TWO.get(dir_name, ()):
            status = _run(sync_argv(dir_name, tmp, endpoint, filters))
            if status:
                raise BashExitError(status)

        listing, count = _find_files(tmp)
        if count == 0:
            print(
                "VACUOUS: %s staged 0 file(s) for promotion; refusing to report a "
                "promotion that moved nothing" % dir_name,
                file=sys.stderr,
            )
            raise BashExitError(1)

        # FACT 2: this is the DOWNLOAD listing, not the upload's.
        urls += [channel_url(dir_name, strip_prefix(f, tmp + "/")) for f in read_lines(listing)]

        # `rm -rf "$TMP"`. Only reached on the success path, which is fact 4.
        shutil.rmtree(tmp, ignore_errors=True)
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (twin :178-181).

    Guarded by `${#PURGE_URLS[@]} -gt 0` in the twin, which is why an empty list
    makes no call at all rather than a call with empty stdin. Under `pipefail` the pipeline's status is the purge script's, since `printf` cannot fail here.
    """
    payload = "".join(url + "\n" for url in urls)
    argv = purge_argv(zone)
    try:
        status = _run(argv, input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself, with its own line number and status 127; Python raises. Same stream, same status, different sentence.
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

    endpoint = values["CLOUDFLARE_R2_ENDPOINT"]

    try:
        purge_urls = _promote_dirs(endpoint)
    except BashExitError as exc:
        return exc.code

    print("R2 promotion complete: edge v%s -> stable" % values["EDGE_VERSION"])

    if purge_urls:
        try:
            # `${CLOUDFLARE_ZONE_ID:-}`: unset and empty are the same argument.
            _purge(purge_urls, env["CLOUDFLARE_ZONE_ID"])
        except BashExitError as exc:
            return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
