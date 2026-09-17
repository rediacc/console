#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`.

Copies every R2 release channel from `edge/` to `stable/` inline with the
release, skipping the normal 7-day soak. This is the emergency lane `Release`
takes with `publish_stable=true`. The soak-gated sibling is
`.ci/scripts/deploy/promote-r2-to-stable.sh`, ported beside this one as
`rediacc_ci.deploy.promote_r2_to_stable`; the twin's own header explains why
this lane does a straight recursive copy where that one does a two-phase,
metadata-last upload.

-----------------------------------------------------------------------------
THE SIBLING SHARES REAL LOGIC WITH THIS FILE AND IT IS DELIBERATELY NOT
FACTORED OUT, WHICH IS A RULING RATHER THAN AN OMISSION
-----------------------------------------------------------------------------
Four blocks are near-identical between the two twins: the `for dir in cli apt
rpm apk archlinux` download leg, the `VACUOUS:` floor, the `find`-driven purge
URL loop, and the closing `cf-purge-urls.sh` pipeline. THE BASH TWINS DO NOT
SHARE THEM. Both source `.ci/scripts/lib/common.sh` and take exactly two
functions from it, `require_cmd` and `sed_in_place`; there is no
promote-specific bash library, and `release-state-validator.sh` is reached by
neither. A Python helper holding those four blocks would therefore have no bash
counterpart, and the acceptance rule for this wave is agreement with the LIVE
twin: a shared module would mean one Python function standing in for two bash
blocks that are free to drift, and a later edit to one twin would silently
change the other's port. The same ruling was taken for
`infra/docker_prepull.py` and its near-twin. The duplication is named here so a
reader sees it was measured, and the cutover box that eventually deletes both
bash files is the right place to collapse it.

The blocks are NOT identical, which is the other half of the argument. This
lane uploads with `aws s3 cp --recursive` and rewrites the channel-pointer files
by DOWNLOADING THEM BACK from `stable/` afterwards; the sibling uploads with two
phases of `aws s3 sync` and rewrites the same files on the LOCAL copy before
phase 2. The purge lists that come out differ accordingly, and so does the
closing line.

-----------------------------------------------------------------------------
NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST
-----------------------------------------------------------------------------
`aws` and (through `cf-purge-urls.sh`) `curl` are the two external tools that
carry a credential, so the differential
(`.ci/rediacc_ci/tests/test_deploy_promote_r2_to_stable_hotfix.py`) puts
RECORDING FAKES for both on a scratch PATH, with an on-disk fixture standing in
for the bucket. Every case pins a fixture endpoint and credential, so even a
bypassed fake would not name real infrastructure.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

-----------------------------------------------------------------------------
TWO EXTERNAL TOOLS ARE CALLED RATHER THAN REIMPLEMENTED, each for a measured
reason
-----------------------------------------------------------------------------
  * `find`, because ITS ORDER IS THE PURGE ORDER. The twin walks
    `find "$TMP" -type f` and appends one URL per line, and find emits DIRECTORY
    order, not sorted order. Measured 2026-09-13 on the fixture: under `cli/`
    the list came out `rdc-linux-x64, manifest.json, latest.json, install.sh,
    install.ps1`, which is neither alphabetical nor reversed. `os.walk` is free
    to disagree, and then the JSON body posted to Cloudflare differs while every
    printed line matches.
  * `sed`, through `core.common.sed_in_place`, because the substitutions are
    REGEX with `|` delimiters. `str.replace` would differ the day a pattern
    grows a metacharacter, and a port that quietly normalised that would be
    deciding a question the twin has not decided.

`cf-purge-urls.sh` IS INVOKED AS THE BASH SCRIPT THE TWIN INVOKES, deliberately,
even though `rediacc_ci.deploy.cf_purge_urls` exists and is itself a verified
port. Agreement with the live twin includes that script's exact bytes;
repointing a call site is a cutover-box decision. `PURGE_SCRIPT_RELATIVE` names
the path once so the cutover is a one-line change.

-----------------------------------------------------------------------------
`$EP` IS UNQUOTED IN THE TWIN AND THAT IS WHY IT IS TWO ARGUMENTS
-----------------------------------------------------------------------------
`EP="--endpoint-url $CLOUDFLARE_R2_ENDPOINT"` then `aws ... $EP ...`. The
expansion is unquoted, so bash word-splits it on IFS into exactly the two
arguments `--endpoint-url` and the endpoint. `endpoint_args` reproduces the
split rather than hard-coding two elements, because an endpoint containing a
space really does become three arguments in the twin and a port that assumed two
would diverge silently. PATHNAME EXPANSION also applies to that unquoted word
and is NOT reproduced: a `*` or `?` in the endpoint would be globbed by bash
against the current directory, and would survive here. Unreachable in practice
(a glob only replaces the word when it MATCHES an existing path, and the value
is an https URL) and named rather than silently assumed away.

-----------------------------------------------------------------------------
THREE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL THREE ARE REPRODUCED
-----------------------------------------------------------------------------
  1. THE PURGE LIST CONTAINS DUPLICATES, four of them on the ordinary path.
     `rpm/stable/rediacc.repo`, `archlinux/stable/rediacc.conf`,
     `cli/stable/install.sh` and `cli/stable/install.ps1` are each appended once
     by the `find` loop (they were copied recursively) and once by the rewrite
     loops that follow. Measured on the fixture: 21 URLs posted, 17 distinct.
     Cloudflare batches at 30, so a duplicate is a slot spent twice.
     `PURGE_LIST_CONTAINS_DUPLICATES` names it.
  2. THE `VACUOUS:` FLOOR SITS AFTER THE UPLOAD IT IS MEANT TO GUARD. The order
     is download, upload, THEN count. So a `<dir>/edge/` prefix that is empty
     has already been through `aws s3 cp "$TMP/" s3://...` before anything
     checks, and what stops the run is whatever `aws` says about a local source
     directory that was never created, not the floor's own sentence. The floor
     is reachable when `$TMP` EXISTS and is empty, which fact 3 shows is a real
     state. `VACUITY_FLOOR_RUNS_AFTER_THE_UPLOAD` names it.
  3. `/tmp/promote-<dir>` IS A FIXED PATH AND IS ONLY REMOVED ON SUCCESS. `rm
     -rf "$TMP"` is the last statement of the loop body, so any early exit (an
     `aws` failure, the floor firing, a cancelled workflow) leaves the directory
     behind, and THE NEXT RUN COPIES INTO IT AND THEN UPLOADS ITS CONTENTS TO
     PRODUCTION. Driven 2026-09-13: a stale `old-0.0.1.apk` left in
     `/tmp/promote-apk` reached `apk/stable/` on the following run, exit 0, no
     warning, and it was purged as though it had been promoted on purpose.
     `/tmp/config` and `/tmp/script` are never removed at all. Latent on a
     GitHub-hosted runner, whose `/tmp` is fresh per job; live on a self-hosted
     one and on a local run. `STALE_TMP_IS_PROMOTED` names it.

None is repaired here. This wave's acceptance rule is agreement with the live
twin, and changing what the emergency release lane uploads is a cutover-box
decision rather than a port's.

-----------------------------------------------------------------------------
THREE `${VAR:?msg}` GUARDS, ONE DIVERGENCE
-----------------------------------------------------------------------------
bash's own refusal names the bash FILE and a bash LINE NUMBER and then the
twin's message, which already begins with the script name:

    .../promote-r2-to-stable-hotfix.sh: line 46: CLOUDFLARE_R2_ACCESS_KEY_ID: \
promote-r2-to-stable-hotfix.sh: CLOUDFLARE_R2_ACCESS_KEY_ID must be set

This port prints the `VAR: msg` half, on the same stream, with the same exit
status 1. Identical ruling to `deploy/delete_r2_channel.py` and
`deploy/upload_repos_to_r2.py`. The ORDER is kept, and `require_cmd aws` runs
BEFORE all three, so a run missing both the binary and every variable names the
binary.

`:?` IS AN UNSET-OR-EMPTY TEST: `CLOUDFLARE_R2_ENDPOINT=` refuses exactly as an
absent one does. Driven, because a port testing `"X" in os.environ` would sail
past it and then hand `aws` an `--endpoint-url` with no value.

K=5 LEDGER: `.ci/shadow/w7p6-promote-r2-to-stable-hotfix.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci.core import common

# The twin's own name, carried in its three guard messages. A literal, because the bytes must survive the port.
SELF = "promote-r2-to-stable-hotfix.sh"

# `for dir in cli apt rpm apk archlinux` (twin :64). ORDER MATTERS to both the call log and the purge list, which is how this port is proved equivalent.
CHANNEL_DIRS = ("cli", "apt", "rpm", "apk", "archlinux")

# `BUCKET="rediacc-releases"` (twin :61) and the public host (twin :81), both
# hard-coded in the twin.
BUCKET = "rediacc-releases"
PUBLIC_HOST = "https://releases.rediacc.com"

# `CC_MUTABLE="no-cache"` (twin :63). The whole subject of the twin's
# Cache-Control paragraph: channel paths reuse filenames across releases, so a cached body under the same URL breaks APKINDEX/Release signatures.
CC_MUTABLE = "no-cache"

# `TMP="/tmp/promote-${dir}"` (twin :67). A FIXED path, which is fact 3 in the
# module docstring. Named here so the differential can assert the shape rather than restating it, and so the cutover box has one place to change.
TMP_PREFIX = "/tmp/promote-"

# The two scratch files the rewrite loops reuse (twin :90, :105). Neither is ever removed.
CONFIG_SCRATCH = "/tmp/config"
SCRIPT_SCRATCH = "/tmp/script"

# The mutable channel-pointer configs, in the twin's order (twin :89).
CONFIG_FILES = ("rpm/stable/rediacc.repo", "archlinux/stable/rediacc.conf")

# The two install scripts re-baked back to `stable` (twin :103).
INSTALL_FILES = ("cli/stable/install.sh", "cli/stable/install.ps1")

# `sed_in_place 's|/edge/|/stable/|g'` (twin :91).
CONFIG_SED = "s|/edge/|/stable/|g"

# The two install-script substitutions (twin :107-108), in the twin's order: the shell default first, the PowerShell one second.
INSTALL_SED = (
    "s|REDIACC_CHANNEL:-edge|REDIACC_CHANNEL:-stable|g",
    's|} else { "edge" }|} else { "stable" }|g',
)

# `"$SCRIPT_DIR/cf-purge-urls.sh"` (twin :117), where SCRIPT_DIR is `.ci/scripts/deploy`. Relative to the repository root so the cutover to `cf_purge_urls.py` is a one-line change in the box that owns it.
PURGE_SCRIPT_RELATIVE = ".ci/scripts/deploy/cf-purge-urls.sh"

# The three `${VAR:?msg}` guards (twin :47-49), in order, as (name, message).
# The messages are the twin's verbatim, each already prefixed with the script name.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CLOUDFLARE_R2_ACCESS_KEY_ID", "%s: CLOUDFLARE_R2_ACCESS_KEY_ID must be set" % SELF),
    ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "%s: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
)

# The three facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
PURGE_LIST_CONTAINS_DUPLICATES = True
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

    Every `aws s3 cp`, every `sed`, the floor's own `exit 1` and the final purge
    pipeline are all unguarded, so the failing program's own stderr is the only
    explanation the caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def script_dir() -> str:
    """`SCRIPT_DIR` (twin :44), by location rather than by cwd.

    The twin resolves `.ci/scripts/deploy` from its own `BASH_SOURCE`; this file
    sits at `.ci/rediacc_ci/deploy/`, three directories under the same root, so
    the arithmetic is identical and neither side depends on the caller's cwd.
    `abspath`, NOT `realpath`: bash's `cd` is logical, so a checkout reached
    through a symlink keeps the symlinked spelling on both sides.
    `paths.repo_root()` is deliberately not used, because it resolves symlinks
    and honours `$REDIACC_CI_ROOT`, and neither is a thing the twin does.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, os.path.dirname(PURGE_SCRIPT_RELATIVE))


def environment() -> dict[str, str]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`, AND THE DIFFERENCE IS A GATE RATHER THAN A STYLE.
    `check:ci-python-env-registry` derives a module's declared inputs by walking
    its AST for literal `os.environ` subscripts and `.get` calls; a read that
    goes through a materialised copy or a local alias is INVISIBLE to it, and
    the module then reports zero inputs while depending on four. Measured
    2026-09-13 against the gate's own `derive`: with `dict(os.environ)` here this
    file contributed only `CLOUDFLARE_ZONE_ID`, the one name read at its own call
    site; with this function it contributes all four.

    `require_env` still takes a dict, so the guard logic stays a pure helper the
    differential can drive without an environment.
    """
    return {
        "CLOUDFLARE_R2_ACCESS_KEY_ID": os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", ""),
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", ""),
        "CLOUDFLARE_R2_ENDPOINT": os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        # `${CLOUDFLARE_ZONE_ID:-}` (twin :117): unset and empty are one argument.
        "CLOUDFLARE_ZONE_ID": os.environ.get("CLOUDFLARE_ZONE_ID", ""),
    }


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The three guards, in the twin's order. Returns the three values.

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
    """`$EP` unquoted (twin :59, used at :68-70 and below).

    See the module docstring: the twin builds ONE string and lets bash split it,
    so this splits the same string rather than returning a fixed pair.
    """
    return ("--endpoint-url %s" % endpoint).split()


def download_argv(dir_name: str, tmp: str, endpoint: str) -> list[str]:
    """`aws s3 cp s3://<bucket>/<dir>/edge/ <tmp>/ $EP --recursive --quiet` (twin :68)."""
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


def upload_argv(dir_name: str, tmp: str, endpoint: str) -> list[str]:
    """`aws s3 cp <tmp>/ s3://<bucket>/<dir>/stable/ $EP --recursive --quiet \
--cache-control no-cache` (twin :69-70)."""
    return [
        "aws",
        "s3",
        "cp",
        tmp + "/",
        "s3://%s/%s/stable/" % (BUCKET, dir_name),
        *endpoint_args(endpoint),
        "--recursive",
        "--quiet",
        "--cache-control",
        CC_MUTABLE,
    ]


def fetch_argv(key: str, target: str, endpoint: str) -> list[str]:
    """`aws s3 cp s3://<bucket>/<key> <target> $EP --quiet` (twin :90, :105)."""
    return [
        "aws",
        "s3",
        "cp",
        "s3://%s/%s" % (BUCKET, key),
        target,
        *endpoint_args(endpoint),
        "--quiet",
    ]


def put_argv(source: str, key: str, endpoint: str) -> list[str]:
    """`aws s3 cp <source> s3://<bucket>/<key> $EP --quiet --cache-control no-cache`
    (twin :92-93, :110-111)."""
    return [
        "aws",
        "s3",
        "cp",
        source,
        "s3://%s/%s" % (BUCKET, key),
        *endpoint_args(endpoint),
        "--quiet",
        "--cache-control",
        CC_MUTABLE,
    ]


def purge_argv(zone: str) -> list[str]:
    """`"$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"` (twin :117).

    `:-` and not `:?`, so an UNSET zone becomes an EMPTY ARGUMENT rather than a
    refusal here. cf-purge-urls.sh then refuses on its own account, and under
    `pipefail` that status is this script's, AFTER the promotion has already
    happened. That is the twin's stated design ("the purge is best-effort and is
    the last thing this script does, so a missing/void credential cannot leave
    the promotion half-done"), not an oversight, and it is reproduced.
    """
    return [os.path.join(script_dir(), os.path.basename(PURGE_SCRIPT_RELATIVE)), "--zone", zone]


def channel_url(dir_name: str, relative: str) -> str:
    """`https://releases.rediacc.com/<dir>/stable/<relative>` (twin :81).

    `relative` is `${f#"$TMP"/}`, a PREFIX STRIP rather than a basename, so a
    file in a subdirectory keeps its directories.
    """
    return "%s/%s/stable/%s" % (PUBLIC_HOST, dir_name, relative)


def key_url(key: str) -> str:
    """`https://releases.rediacc.com/<key>` (twin :94, :112)."""
    return "%s/%s" % (PUBLIC_HOST, key)


def strip_prefix(path: str, prefix: str) -> str:
    """`${f#"$TMP"/}`: remove it only when it is there, leave the rest alone.

    `removeprefix` and not a slice, because the two differ on exactly the case
    the twin cares about. The `"$TMP"` is QUOTED inside the expansion, so it is a
    literal prefix and not a pattern.
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


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS. bash `echo` writes through
    immediately; Python block-buffers stdout when it is a pipe and flushes at
    exit, so without this the `Promoting ...` lines land after the purge
    script's output instead of before it, on the same stream, with
    byte-identical content in a different order. The call log is identical and
    both exits are 0; only a byte comparison of stdout sees it.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _find_files(directory: str) -> tuple[str, int]:
    """`find <dir> -type f`, and `... | wc -l` over the same output.

    THE TWIN RUNS `find` TWICE, once into `wc -l` for the vacuity floor and once
    into the URL loop, and this returns both answers from ONE run. That is the
    single deliberate consolidation in this file, and it is safe in the direction
    that matters: two runs can only disagree if the directory changes between
    them, and if it did, the twin would report a count that does not match the
    URLs it then builds. On the path where the count is 0 the twin exits before
    its second `find`, so the ONE find here also matches how many times find's
    own stderr (`find: '<dir>': No such file or directory`) is emitted.

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


def _promote_dirs(endpoint: str) -> list[str]:
    """The `for dir in cli apt rpm apk archlinux` loop (twin :64-87). Returns URLs."""
    urls: list[str] = []
    for dir_name in CHANNEL_DIRS:
        print("Promoting %s/edge/ -> %s/stable/" % (dir_name, dir_name))
        tmp = TMP_PREFIX + dir_name

        status = _run(download_argv(dir_name, tmp, endpoint))
        if status:
            raise BashExitError(status)
        status = _run(upload_argv(dir_name, tmp, endpoint))
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

        urls += [channel_url(dir_name, strip_prefix(f, tmp + "/")) for f in read_lines(listing)]

        # `rm -rf "$TMP"`. Only reached on the success path, which is fact 3 in the module docstring. `ignore_errors` is `-f`.
        shutil.rmtree(tmp, ignore_errors=True)
    return urls


def _rewrite_configs(endpoint: str) -> list[str]:
    """The channel-pointer rewrite loop (twin :89-95). Returns URLs.

    Downloads each config back out of `stable/` (the recursive copy above has
    already put the `edge`-flavoured body there), rewrites it in place, and puts
    it back. `/tmp/config` is reused by both iterations and never removed.
    """
    urls: list[str] = []
    for key in CONFIG_FILES:
        status = _run(fetch_argv(key, CONFIG_SCRATCH, endpoint))
        if status:
            raise BashExitError(status)
        _flush()
        status = common.sed_in_place([CONFIG_SED, CONFIG_SCRATCH])
        if status:
            raise BashExitError(status)
        status = _run(put_argv(CONFIG_SCRATCH, key, endpoint))
        if status:
            raise BashExitError(status)
        urls.append(key_url(key))
    return urls


def _rebake_install_scripts(endpoint: str) -> list[str]:
    """The install-script re-bake loop (twin :101-113). Returns URLs.

    WHY IT EXISTS, in the twin's words: `cd-stage.yml` baked `edge` into
    `cli/edge/install.{sh,ps1}`, and the raw recursive copy above carried that
    into `cli/stable/`. This rewrites it back.
    """
    urls: list[str] = []
    for key in INSTALL_FILES:
        status = _run(fetch_argv(key, SCRIPT_SCRATCH, endpoint))
        if status:
            raise BashExitError(status)
        _flush()
        status = common.sed_in_place(["-e", INSTALL_SED[0], "-e", INSTALL_SED[1], SCRIPT_SCRATCH])
        if status:
            raise BashExitError(status)
        status = _run(put_argv(SCRIPT_SCRATCH, key, endpoint))
        if status:
            raise BashExitError(status)
        urls.append(key_url(key))
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (twin :115-118).

    Guarded by `${#PURGE_URLS[@]} -gt 0` in the twin, which is why an empty list
    makes no call at all rather than a call with empty stdin. Under `pipefail`
    the pipeline's status is the purge script's, since `printf` cannot fail here.
    """
    payload = "".join(url + "\n" for url in urls)
    argv = purge_argv(zone)
    try:
        status = _run(argv, input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself, with
        # its own line number and status 127; Python raises. Same stream, same
        # status, different sentence, which is the ruling the `${VAR:?}` guards
        # get too.
        print("%s: %s: %s" % (SELF, argv[0], exc.strerror), file=sys.stderr)
        raise BashExitError(127) from exc
    if status:
        raise BashExitError(status)


def main(argv: list[str]) -> int:
    del argv  # the twin takes no argv, and says so at :22-23

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

    # `export`ed (twin :51-53), so the `aws` child sees them. R2 speaks S3, and the twin's header names the mapping because a missing bridge surfaces as an unhelpful credentials error rather than as a missing variable.
    os.environ["AWS_ACCESS_KEY_ID"] = values["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = values["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    endpoint = values["CLOUDFLARE_R2_ENDPOINT"]

    try:
        purge_urls = _promote_dirs(endpoint)
        purge_urls += _rewrite_configs(endpoint)
        purge_urls += _rebake_install_scripts(endpoint)
    except BashExitError as exc:
        return exc.code

    print("R2 promoted to stable")

    if purge_urls:
        try:
            # `${CLOUDFLARE_ZONE_ID:-}`: unset and empty are the same argument.
            _purge(purge_urls, env["CLOUDFLARE_ZONE_ID"])
        except BashExitError as exc:
            return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
