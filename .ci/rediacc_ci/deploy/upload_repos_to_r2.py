#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/upload-repos-to-r2.sh`.

Uploads the built package repositories (`apt`, `rpm`, `apk`, `archlinux`) and
the two channel install scripts to R2, then purges the Cloudflare cache for
every URL it touched.

WHY THE CACHE-CONTROL IS `no-cache` AND NOT `immutable`, carried over from the
twin's header because it is the reason this script exists in its own file:
package-manager channel paths reuse filenames across releases, so
`cli/edge/rdc-0.9.13.deb` can serve DIFFERENT bytes from one CI run to the next.
Marking those immutable let CF keep a previous run's body under a URL the next
run's APKINDEX points at with a different sha256, and `BAD signature` cascaded.
`no-cache` means CF never caches, so there is no stale body to go stale. Truly
versioned paths (`cli/v<semver>/`, `npm/<channel>/*.tgz`) keep their one-year
immutable policy and are `upload-to-r2.sh`'s business, not this file's.

NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST. `aws` and (through
`cf-purge-urls.sh`) `curl` are the two external tools that carry a credential,
so the differential (`.ci/rediacc_ci/tests/test_deploy_upload_repos_to_r2.py`)
puts RECORDING FAKES for both on a scratch PATH. The `aws` fake logs its exact
argv and, for a `cp`, the CONTENT of the file being uploaded. That content log is
load bearing: the install scripts are REWRITTEN on the way past (the default
channel is substituted), and two implementations can print an identical
`Repos uploaded to R2 channel: edge` while uploading a script that still points
at `stable`.

THREE EXTERNAL TOOLS ARE CALLED RATHER THAN REIMPLEMENTED, each for a measured
reason and not for symmetry:

  * `find`, because ITS ORDER IS THE PURGE ORDER. The twin walks
    `find <dir> -type f` and appends one URL per line, and find emits directory
    order, not sorted order. Driven 2026-09-13 on a fixture: `InRelease` comes
    out BEFORE `dists/stable/Packages.gz`. `os.walk` is free to disagree, and
    then the JSON body posted to Cloudflare differs while every printed line
    matches.
  * `sed`, because the two substitutions are REGEX with `|` delimiters and an
    unescaped `${CHANNEL}` on the replacement side. A channel containing `&` or
    `|` therefore does something specific in sed and something else in
    `str.replace`. The channel is `edge`, `stable` or `pr-<n>` today, so this is
    latent rather than live, and a port that quietly normalised it would be
    deciding a question the twin has not decided.
  * `mktemp`, so the temporary path has the same SHAPE (`/tmp/tmp.XXXXXXXXXX`,
    honouring TMPDIR) as the twin's. That path appears in the `aws s3 cp` argv,
    which is the thing the differential compares.

`cf-purge-urls.sh` IS INVOKED AS THE BASH SCRIPT THE TWIN INVOKES, deliberately,
even though `rediacc_ci.deploy.cf_purge_urls` exists and is itself a verified
port. The acceptance rule for this wave is agreement with the LIVE twin, and the
twin's observable behaviour includes that script's exact bytes; repointing a
call site is a cutover-box decision, not this one's. `PURGE_SCRIPT` names the
path once so the cutover is a one-line change when the box that owns it lands.

`get_repo_root` IS REPRODUCED BY LOCATION, NOT BY cwd. The twin does
`cd "$(get_repo_root)"`, and `get_repo_root` resolves `.ci/scripts/lib/../../..`
from `common.sh`'s own directory. This file sits at `.ci/rediacc_ci/deploy/`,
also three directories under the root, so the arithmetic is identical. It is
`abspath`, NOT `realpath`, on purpose: bash's `cd` is logical, so a checkout
reached through a symlink keeps the symlinked spelling on both sides.
`paths.repo_root()` is deliberately not used, because it resolves symlinks and
honours `$REDIACC_CI_ROOT`, and neither is a thing the twin does.

TWO VACUITY FACTS ABOUT THE TWIN, THE FIRST DELIBERATE AND THE SECOND NOT.
Neither is repaired here; this wave's acceptance rule is agreement with the live
twin.

  1. THE `VACUOUS:` GUARD IS SCOPED NARROWLY AND SAYS SO (twin :123-127). A
     MISSING `dist/repos/<dir>` is legitimate, because not every channel builds
     every package format, so it is skipped. A directory that EXISTS and holds
     nothing is refused, because the sync uploaded nothing and the run would
     still report success.
  2. AN ENTIRELY EMPTY `dist/` IS A GREEN RUN THAT MOVED NOTHING. With no
     `dist/repos/*` directory and neither install script present, every loop body
     is skipped, `PURGE_URLS` stays empty, no purge runs, and the script prints
     `Repos uploaded to R2 channel: <channel>` and exits 0. Driven 2026-09-13.
     That line is the only thing a workflow log shows, and it is false. The guard
     in (1) cannot see it, because its subject is one directory rather than the
     upload as a whole. `AN_EMPTY_DIST_REPORTS_SUCCESS` names it so the
     differential can pin it by name rather than by restating the sentence.

FIVE `${VAR:?msg}` GUARDS, ONE DIVERGENCE. bash's own refusal names the bash
FILE and a bash LINE NUMBER and then the twin's message, which already begins
with the script name:

    .ci/scripts/deploy/upload-repos-to-r2.sh: line 49: CHANNEL: upload-repos-to-r2.sh: CHANNEL must be set

This port prints the `VAR: msg` half, on the same stream, with the same exit
status 1. Identical ruling to `deploy/delete_r2_channel.py`. The ORDER of the
guards is kept, and `require_cmd aws` runs BEFORE all five, so a run missing both
the binary and every variable names the binary.

`:?` IS AN UNSET-OR-EMPTY TEST: `CHANNEL=` refuses exactly as an absent CHANNEL
does. Driven, because a port testing `"CHANNEL" in os.environ` would sail past it
and then sync every package format to `s3://rediacc-releases/apt//`.

K=5 LEDGER: `.ci/shadow/w7p6-upload-repos-to-r2.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci.core import common

# The twin's own name, printed in its five guard messages and its one
# non-release-channel notice. A literal, because the bytes must survive the port.
SELF = "upload-repos-to-r2.sh"

# `for dir in apt rpm apk archlinux` (:114). ORDER MATTERS to both the call log
# and the purge list, which is how this port is proved equivalent.
FORMATS = ("apt", "rpm", "apk", "archlinux")

# `CC_MUTABLE="no-cache"` (:111). The whole subject of the header above.
CC_MUTABLE = "no-cache"

# The bucket and the public host, both hard-coded in the twin (:116, :135).
BUCKET = "rediacc-releases"
PUBLIC_HOST = "https://releases.rediacc.com"

# `.ci/scripts/deploy/cf-purge-urls.sh` (:162), relative to the repository root
# the twin cd's into. Named once so the cutover to `cf_purge_urls.py` is one
# line in the box that owns it.
PURGE_SCRIPT = ".ci/scripts/deploy/cf-purge-urls.sh"

# The two install scripts (:142), in order, relative to the repository root.
INSTALL_SCRIPTS = ("dist/pages/install.sh", "dist/pages/install.ps1")

# The five `${VAR:?msg}` guards (:49-53), in order, as (name, message). The
# messages are the twin's verbatim, each already prefixed with the script name.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CHANNEL", "%s: CHANNEL must be set" % SELF),
    ("CLOUDFLARE_R2_ACCESS_KEY_ID", "%s: CLOUDFLARE_R2_ACCESS_KEY_ID must be set" % SELF),
    ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "%s: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
    ("CLOUDFLARE_ZONE_ID", "%s: CLOUDFLARE_ZONE_ID must be set" % SELF),
)

# The `case` arms of `skip_release_requested` (:70-73). A SET, because the twin
# lists each spelling explicitly rather than lowercasing: `TrUe` and `Y` are NOT
# skip values, and a port using `.lower() in {...}` would skip a release the twin
# publishes. Sits between the two marker comments the gate test
# `.ci/scripts/test/gates/test-skip-release-channel-pointer.sh` splits the twin
# on; that test assembles its mutants from the twin's own text, so it is
# unaffected by this file, but the set has to stay in step with those lines.
SKIP_RELEASE_VALUES = frozenset({"true", "TRUE", "True", "1", "yes", "YES", "y", "on", "ON"})

# `if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]` (:77). A `pr-N`
# channel has no tag contract, so the bump-none refusal is scoped to these two.
RELEASE_CHANNELS = ("stable", "edge")

# Vacuity fact 2 in the module docstring, as a constant so a test can assert the
# defect by name instead of restating the sentence.
AN_EMPTY_DIST_REPORTS_SUCCESS = True


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    `aws s3 sync`, `aws s3 cp`, `sed` and the final purge pipeline are all
    unguarded, so the failing program's own stderr is the only explanation the
    caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def repo_root() -> str:
    """`cd "$(get_repo_root)"` (:105), by location rather than by cwd.

    `.ci/rediacc_ci/deploy/` is three directories under the root, exactly as
    `.ci/scripts/lib/` is. `abspath` and not `realpath`: see the module
    docstring.
    """
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The five guards, in the twin's order. Returns the five values.

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


def skip_release_requested(env: dict[str, str]) -> bool:
    """`skip_release_requested` (:69-74). Exact-match against the case arms."""
    return env.get("SKIP_RELEASE", "") in SKIP_RELEASE_VALUES


def skip_banner(channel: str) -> list[str]:
    """The bump-none refusal block (:78-96), as the lines it echoes to STDOUT.

    On stdout and not stderr, and exit 0: the twin's closing sentence says this
    is "the intended outcome of a bump-none merge, not an error", and a port that
    treated it as a warning would make a correct build look broken.
    """
    return [
        "",
        "================================================================",
        "  RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2",
        "================================================================",
        "  channel:  %s" % channel,
        "",
        "  The merged PR carried the 'bump-none' label, so no tag and no",
        "  GitHub Release exist for this build. The package repositories",
        "  and install scripts are channel pointers, so publishing them",
        "  would advertise a version nobody can install.",
        "",
        "  NOT written:",
        "    - apt/%s/  rpm/%s/  apk/%s/  archlinux/%s/" % (channel, channel, channel, channel),
        "    - cli/%s/install.sh  cli/%s/install.ps1" % (channel, channel),
        "    - no Cloudflare cache purge (nothing changed)",
        "",
        "  This is the intended outcome of a bump-none merge, not an error.",
        "================================================================",
        "",
    ]


def sync_argv(fmt: str, channel: str, endpoint: str) -> list[str]:
    """One `aws s3 sync dist/repos/<fmt> s3://.../<fmt>/<channel>/` (:116-118)."""
    return [
        "aws",
        "s3",
        "sync",
        "dist/repos/%s" % fmt,
        "s3://%s/%s/%s/" % (BUCKET, fmt, channel),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--quiet",
    ]


def cp_argv(source: str, channel: str, name: str, endpoint: str) -> list[str]:
    """One `aws s3 cp <tmp> s3://.../cli/<channel>/<name>` (:148-150)."""
    return [
        "aws",
        "s3",
        "cp",
        source,
        "s3://%s/cli/%s/%s" % (BUCKET, channel, name),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--quiet",
    ]


def sed_argv(channel: str, source: str) -> list[str]:
    """The two channel substitutions (:145-147).

    The first rewrites the shell default (`REDIACC_CHANNEL:-stable`), the second
    the PowerShell one (`} else { "stable" }`), so a copy under `cli/<channel>/`
    installs from `<channel>` unless the caller says otherwise.
    """
    return [
        "sed",
        "-e",
        "s|REDIACC_CHANNEL:-stable|REDIACC_CHANNEL:-%s|g" % channel,
        "-e",
        's|} else { "stable" }|} else { "%s" }|g' % channel,
        source,
    ]


def purge_argv(zone: str) -> list[str]:
    """`.ci/scripts/deploy/cf-purge-urls.sh --zone "$CLOUDFLARE_ZONE_ID"` (:162)."""
    return [PURGE_SCRIPT, "--zone", zone]


def repo_url(fmt: str, channel: str, relative: str) -> str:
    """`https://releases.rediacc.com/<fmt>/<channel>/<path>` (:135).

    `relative` is `${f#dist/repos/$dir/}`, a PREFIX STRIP rather than a basename:
    `dists/stable/Packages.gz` keeps its two directories.
    """
    return "%s/%s/%s/%s" % (PUBLIC_HOST, fmt, channel, relative)


def install_url(channel: str, name: str) -> str:
    """`https://releases.rediacc.com/cli/<channel>/install.{sh,ps1}` (:152)."""
    return "%s/cli/%s/%s" % (PUBLIC_HOST, channel, name)


def strip_prefix(path: str, prefix: str) -> str:
    """`${f#<prefix>}`: remove it only when it is there, leave the rest alone.

    `removeprefix` and not a slice, because the two differ on exactly the case
    the twin cares about: `${f#x}` leaves a non-matching string untouched.
    """
    return path.removeprefix(prefix)


def read_lines(text: str) -> list[str]:
    """`while IFS= read -r f; do ... done < <(find ...)`.

    A FINAL LINE WITH NO NEWLINE IS DROPPED, because `read` stores it and then
    returns non-zero at EOF so the loop body never runs for it. find always
    terminates its last line, so this cannot bite on real input; it is written
    the bash way anyway, because the day it does bite the two would disagree
    about a URL rather than about a count.
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return lines


def _find_files(directory: str) -> tuple[str, int]:
    """`find <dir> -type f`, and `... | wc -l` over the same output.

    THE TWIN RUNS `find` TWICE, once into `wc -l` for the vacuity floor (:128)
    and once into the URL loop (:136), and this returns both answers from ONE
    run. That is the single deliberate consolidation in this file, and it is
    safe in the direction that matters: two runs can only disagree if the
    directory changes between them, and if it did, the twin would report a count
    that does not match the URLs it then builds.

    The count is NEWLINES, which is what `wc -l` counts. find's status is
    DISCARDED, exactly as `|| true` discards it: a find that fails still leaves
    `wc` printing a number, and the twin acts on the number.
    """
    _flush()
    proc = subprocess.run(
        ["find", directory, "-type", "f"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stdout, proc.stdout.count("\n")


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS, measured 2026-09-13. bash
    `echo` writes through immediately; Python block-buffers stdout when it is a
    pipe and flushes at exit. Without this, `Repos uploaded to R2 channel: edge`
    landed AFTER the purge script's two lines instead of before them, on the
    same stream, with byte-identical content in a different order. The call log
    was identical, both exits were 0, and only a byte comparison of stdout saw
    it. Every spawn goes through here for that reason.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _mktemp() -> str:
    """`tmp="$(mktemp)"` (:144). The binary, not `tempfile`: see the docstring."""
    _flush()
    proc = subprocess.run(["mktemp"], stdout=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        raise BashExitError(proc.returncode)
    return proc.stdout.rstrip("\n")


def _upload_repos(channel: str, endpoint: str) -> list[str]:
    """The `for dir in apt rpm apk archlinux` loop (:114-137). Returns the URLs."""
    urls: list[str] = []
    for fmt in FORMATS:
        directory = "dist/repos/%s" % fmt
        # `[[ -d ... ]] || continue`: a format this channel does not build is
        # legitimate, and is vacuity fact 1 in the module docstring.
        if not os.path.isdir(directory):
            continue

        status = _run(sync_argv(fmt, channel, endpoint))
        if status:
            raise BashExitError(status)

        listing, count = _find_files(directory)
        if count == 0:
            print(
                "VACUOUS: %s exists but holds 0 file(s); refusing to report an "
                "upload that moved nothing" % directory,
                file=sys.stderr,
            )
            raise BashExitError(1)

        urls += [
            repo_url(fmt, channel, strip_prefix(f, directory + "/")) for f in read_lines(listing)
        ]
    return urls


def _upload_install_scripts(channel: str, endpoint: str) -> list[str]:
    """The install-script loop (:142-153). Returns the URLs."""
    urls: list[str] = []
    for source in INSTALL_SCRIPTS:
        if not os.path.isfile(source):
            continue

        tmp = _mktemp()
        # `sed ... "$f" > "$tmp"`. A sed failure ends the run under `set -e`
        # with sed's status, and the temporary file is NOT removed -- the `rm`
        # is the next statement and never runs. Reproduced, leak included.
        with open(tmp, "w", encoding="utf-8") as handle:
            status = _run(sed_argv(channel, source), stdout=handle)
        if status:
            raise BashExitError(status)

        name = os.path.basename(source)
        status = _run(cp_argv(tmp, channel, name, endpoint))
        if status:
            raise BashExitError(status)

        # `rm -f "$tmp"`: -f, so a temporary that has already gone is not an error.
        if os.path.exists(tmp):
            os.remove(tmp)

        urls.append(install_url(channel, name))
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (:160-163).

    Guarded by `${#PURGE_URLS[@]} -gt 0` in the twin, which is why an empty list
    makes no call at all rather than a call with empty stdin. Under `pipefail`
    the pipeline's status is the purge script's, since printf cannot fail here.
    """
    payload = "".join(url + "\n" for url in urls)
    try:
        status = _run(purge_argv(zone), input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself, with
        # its own line number and status 127; Python raises. Same stream, same
        # status, different sentence -- the same ruling the `${VAR:?}` guards get.
        print("%s: %s: %s" % (SELF, PURGE_SCRIPT, exc.strerror), file=sys.stderr)
        raise BashExitError(127) from exc
    if status:
        raise BashExitError(status)


def main(argv: list[str]) -> int:
    del argv  # the twin takes no argv, and says so at :62

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        values = require_env(dict(os.environ))
    except MissingEnvError as exc:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print("%s: %s" % (exc.name, exc.message), file=sys.stderr)
        return 1

    channel = values["CHANNEL"]
    endpoint = values["CLOUDFLARE_R2_ENDPOINT"]

    if skip_release_requested(dict(os.environ)):
        if channel in RELEASE_CHANNELS:
            for line in skip_banner(channel):
                print(line)
            return 0
        print(
            "%s: SKIP_RELEASE ignored on channel '%s': not a release channel, "
            "uploading as usual" % (SELF, channel)
        )

    # The dist/ paths and the purge call below are repo-relative, exactly as they
    # were in the workflow step this came from.
    os.chdir(repo_root())

    # `export`ed, so the `aws` child sees them. R2 speaks S3, and the twin's
    # header names the mapping because a missing bridge surfaces as an
    # unhelpful credentials error rather than as a missing variable.
    os.environ["AWS_ACCESS_KEY_ID"] = values["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = values["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    try:
        purge_urls = _upload_repos(channel, endpoint)
        purge_urls += _upload_install_scripts(channel, endpoint)
    except BashExitError as exc:
        return exc.code

    # UNCONDITIONAL, and vacuity fact 2: this prints even when nothing moved.
    print("Repos uploaded to R2 channel: %s" % channel)

    if purge_urls:
        try:
            _purge(purge_urls, values["CLOUDFLARE_ZONE_ID"])
        except BashExitError as exc:
            return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
