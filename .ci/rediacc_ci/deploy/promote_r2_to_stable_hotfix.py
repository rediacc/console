#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`, with the transfer made server-side (operator ruling 2026-09-26).

Copies every R2 release channel from `edge/` to `stable/` inline with the release, skipping the normal 7-day soak. This is the emergency lane `Release` takes with `publish_stable=true`. The soak-gated sibling is `rediacc_ci.deploy.promote_r2_to_stable`, which copies in two phases, metadata last; this lane copies each tree in one phase, as the twin's straight recursive copy did.

-----------------------------------------------------------------------------
THE BYTES NEVER LEAVE R2
-----------------------------------------------------------------------------
The twin downloads each `<dir>/edge/` tree to the runner and uploads it again with `aws s3 cp --recursive`. With about 67 GB of release history under the five trees (2026-09-25) that took 4+ hours and could outlive the job's minted R2 token (it did on 2026-09-24). This port copies server-side with one `aws s3api copy-object` per object; `r2_promote`'s docstring carries the plan, why `aws s3 cp s3://... s3://...` cannot do it on R2, the metadata the copies carry and R2's CopyObject size limit.

-----------------------------------------------------------------------------
THE CHANNEL POINTERS NEVER REACH STABLE UNSTAMPED
-----------------------------------------------------------------------------
The twin copied `rpm/rediacc.repo`, `archlinux/rediacc.conf`, `cli/install.sh` and `cli/install.ps1` raw, then downloaded them back out of `stable/`, rewrote them and put them back in two loops after every directory. A run that died in between left production installing edge (2026-09-24). Here those four are EXCLUDED from the copy, fetched from EDGE, stamped for stable (`channel_stamp`) and uploaded after the tree's copy (`r2_promote.POINTERS_GO_LAST` says why last). The twin's two re-bake loops, and the four duplicate purge URLs they appended, are gone.

-----------------------------------------------------------------------------
WHAT ELSE CHANGED AGAINST THE TWIN
-----------------------------------------------------------------------------
  * The purge list comes from the stable LISTING taken after the copy, not from a local `find`, and a promoted key missing from that listing refuses the run (`INCOMPLETE:`) with nothing purged. Its order is the edge listing's key order.
  * The `VACUOUS:` floor runs on the edge listing BEFORE anything is copied (the twin counted after uploading).
  * No fixed `/tmp/promote-<dir>`, `/tmp/config` or `/tmp/script`: nothing a failed run leaves behind can be promoted by the next one. The pointer stage is a fresh `mkdtemp`, removed on exit.
  * An object whose stable copy already has the same size and is not older is not copied again (`aws s3 sync`'s rule); the twin's `cp --recursive` re-sent every byte of history on every run.

`$EP` IS UNQUOTED IN THE TWIN, so bash word-splits it into `--endpoint-url` and the endpoint; `r2_promote.endpoint_args` reproduces the split.

-----------------------------------------------------------------------------
THREE `${VAR:?msg}` GUARDS, ONE DIVERGENCE
-----------------------------------------------------------------------------
bash's own refusal names the bash FILE and a bash LINE NUMBER and then the twin's message, which already begins with the script name:

    .../promote-r2-to-stable-hotfix.sh: line 46: CLOUDFLARE_R2_ACCESS_KEY_ID: \
promote-r2-to-stable-hotfix.sh: CLOUDFLARE_R2_ACCESS_KEY_ID must be set

This port prints the `VAR: msg` half, on the same stream, with the same exit status 1. The ORDER is kept, and `require_cmd aws` runs BEFORE all three. `:?` IS AN UNSET-OR-EMPTY TEST: `CLOUDFLARE_R2_ENDPOINT=` refuses exactly as an absent one does.

NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST: `.ci/rediacc_ci/tests/test_deploy_promote_r2_to_stable_hotfix.py` puts recording fakes for `aws` and `curl` on a scratch PATH over an on-disk bucket fixture.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.core import common
from rediacc_ci.deploy import channel_stamp, r2_promote

# The twin's own name, carried in its three guard messages. A literal, because the bytes must survive the port.
SELF = "promote-r2-to-stable-hotfix.sh"

# `for dir in cli apt rpm apk archlinux` (twin :64). ORDER MATTERS to the call log and the purge list.
CHANNEL_DIRS = ("cli", "apt", "rpm", "apk", "archlinux")

BUCKET = r2_promote.BUCKET
PUBLIC_HOST = r2_promote.PUBLIC_HOST
CC_MUTABLE = r2_promote.CC_MUTABLE

# One phase of everything: no filters, as the twin's recursive copy had none.
PHASES: tuple[tuple[str, ...], ...] = ((),)

# The stamps, shared with the soak-gated sibling through `channel_stamp`.
CONFIG_SED = channel_stamp.CHANNEL_SED
INSTALL_SED = channel_stamp.INSTALL_SED

# `"$SCRIPT_DIR/cf-purge-urls.sh"` (twin :117), where SCRIPT_DIR is `.ci/scripts/deploy`.
PURGE_SCRIPT_RELATIVE = ".ci/scripts/deploy/cf-purge-urls.sh"

# The three `${VAR:?msg}` guards (twin :47-49), in order, as (name, message).
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CLOUDFLARE_R2_ACCESS_KEY_ID", "%s: CLOUDFLARE_R2_ACCESS_KEY_ID must be set" % SELF),
    ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "%s: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
)

# The named facts in the module docstring, as constants so a test can assert each by name.
PURGE_LIST_CONTAINS_DUPLICATES = False
PURGE_LIST_IS_BUILT_FROM_THE_STABLE_LISTING = True
EDGE_DEFAULT_REACHES_STABLE_BEFORE_THE_REBAKE = False
BULK_IS_SERVER_SIDE = r2_promote.BULK_IS_SERVER_SIDE


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    The failing program's own stderr, or the refusal this port prints, is the explanation; its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def script_dir() -> str:
    """`SCRIPT_DIR` (twin :44), by location rather than by cwd.

    The twin resolves `.ci/scripts/deploy` from its own `BASH_SOURCE`; this file sits at `.ci/rediacc_ci/deploy/`, three directories under the same root, so the arithmetic is identical and neither side depends on the caller's cwd. `abspath`, NOT `realpath`: bash's `cd` is logical, so a checkout reached through a symlink keeps the symlinked spelling on both sides.
    `paths.repo_root()` is deliberately not used, because it resolves symlinks and honours `$REDIACC_CI_ROOT`, and neither is a thing the twin does.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, os.path.dirname(PURGE_SCRIPT_RELATIVE))


def environment() -> dict[str, str]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`, AND THE DIFFERENCE IS A GATE RATHER THAN A STYLE. `check:ci-python-env-registry` derives a module's declared inputs by walking its AST for literal `os.environ` subscripts and `.get` calls; a read that goes through a materialised copy or a local alias is INVISIBLE to it, and the module then reports zero inputs while depending on four. Measured 2026-09-13
    against the gate's own `derive`: with `dict(os.environ)` here this file contributed only `CLOUDFLARE_ZONE_ID`, the one name read at its own call site; with this function it contributes all four.

    `require_env` still takes a dict, so the guard logic stays a pure helper the differential can drive without an environment.
    """
    return {
        "CLOUDFLARE_R2_ACCESS_KEY_ID": os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", ""),
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", ""),
        "CLOUDFLARE_R2_ENDPOINT": os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        # `${CLOUDFLARE_ZONE_ID:-}` (twin :117): unset and empty are one argument.
        "CLOUDFLARE_ZONE_ID": os.environ.get("CLOUDFLARE_ZONE_ID", ""),
        # Seconds between transfer retries; tests set 0. Not in the twin (Rule T retry, #4175e786).
        "PROMOTE_RETRY_DELAY_S": os.environ.get("PROMOTE_RETRY_DELAY_S", "10"),
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
    """`$EP` unquoted (twin :59)."""
    return r2_promote.endpoint_args(endpoint)


def purge_argv(zone: str) -> list[str]:
    """`"$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"` (twin :117).

    `:-` and not `:?`, so an UNSET zone becomes an EMPTY ARGUMENT rather than a refusal here. cf-purge-urls.sh then refuses on its own account, and under `pipefail` that status is this script's, AFTER the promotion has already happened. That is the twin's stated design ("the purge is best-effort and is the last thing this script does, so a missing/void credential cannot leave the
    promotion half-done"), not an oversight, and it is reproduced.
    """
    return [os.path.join(script_dir(), os.path.basename(PURGE_SCRIPT_RELATIVE)), "--zone", zone]


def channel_url(dir_name: str, relative: str) -> str:
    """`https://releases.rediacc.com/<dir>/stable/<relative>` (twin :81)."""
    return r2_promote.channel_url(dir_name, relative)


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS. bash `echo` writes through immediately; Python block-buffers stdout when it is a pipe and flushes at exit, so without this the `Promoting ...` lines land after the purge script's output instead of before it, on the same stream, with byte-identical content in a different order. The call log is identical and both exits are 0; only
    a byte comparison of stdout sees it.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _promote_dirs(endpoint: str) -> list[str]:
    """The `for dir in cli apt rpm apk archlinux` loop. Returns the purge URLs."""
    run = r2_promote.Transfers(SELF, endpoint, float(environment()["PROMOTE_RETRY_DELAY_S"] or "0"))
    stage_root = tempfile.mkdtemp(prefix="promote-pointers-")
    urls: list[str] = []
    try:
        for dir_name in CHANNEL_DIRS:
            print("Promoting %s/edge/ -> %s/stable/" % (dir_name, dir_name))
            _flush()
            urls += r2_promote.promote_tree(dir_name, PHASES, stage_root, run)
    except r2_promote.PromoteError as exc:
        raise BashExitError(exc.status) from exc
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (twin :115-118).

    Guarded by `${#PURGE_URLS[@]} -gt 0` in the twin, which is why an empty list
    makes no call at all rather than a call with empty stdin. Under `pipefail` the pipeline's status is the purge script's, since `printf` cannot fail here.
    """
    payload = "".join(url + "\n" for url in urls)
    argv = purge_argv(zone)
    try:
        status = _run(argv, input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself, with its own line number and status 127; Python raises. Same stream, same
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
