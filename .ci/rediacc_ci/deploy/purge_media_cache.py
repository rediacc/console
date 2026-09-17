#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/purge-media-cache.sh`.

One Cloudflare `purge_cache` request for the whole `media.rediacc.com` hostname.
The twin's header records why it exists: a new CORS policy or a republished file
does NOT retroactively fix an already-cached response, and the media objects are
served with `max-age=31536000`, so an object fetched once before a fix keeps
serving the stale response (including the ABSENCE of a header) for up to a year.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `curl` is the tool that carries the
credential, so the differential
(`.ci/rediacc_ci/tests/test_deploy_purge_media_cache.py`) puts a RECORDING FAKE
`curl` on a scratch PATH that logs its exact argv and answers from a fixture.
The zone id and the hostname are HARD-CODED in the twin, not arguments, so the
request shape is the whole contract and the log is compared as well as the two
streams.

`jq` IS CALLED, NOT REIMPLEMENTED, and here the reason is sharper than in the
sibling ports because the two jq call sites have DIFFERENT `set -e` exposure:

  * `if [[ "$(echo "$RESPONSE" | jq -r '.success')" != "true" ]]` is a
    substitution inside a CONDITIONAL, so a jq that dies leaves its parse error
    on stderr, yields the empty string, and the run continues into the failure
    branch.
  * `RESPONSE="$(curl -s ...)"` is an ASSIGNMENT, so a curl that cannot reach
    the host ends the run with CURL's status.

Driven 2026-09-13: an HTML body prints `jq: parse error: Invalid numeric literal
at line 2, column 0` TWICE (once for `.success`, once for `.errors` inside the
`log_error` argument) and exits 1 with `✗ Purge failed: ` and an empty tail; a
curl exiting 6 prints the step line and then nothing at all, exit 6. A
`json.loads` port would get the count of messages, the text, and one of the two
exit codes wrong.

`.success` HAS NO `// false` DEFAULT here, unlike the sibling
`housekeeping/cleanup_cf_preview.py`. A body of `{}` therefore yields the STRING
`null`, not `false`; both are `!= "true"` so the branch is the same, but the port
must not "tidy" the filter, because the filter is what the differential pins.

THE FAILURE THIS SCRIPT CANNOT REPORT, named because it is the vacuity class and
a reader should not have to rediscover it: A TRANSPORT FAILURE IS A SILENT
NON-ZERO. `curl -s` (no `-S`) suppresses curl's own error message, so an
unreachable API produces the step line, no diagnostic whatsoever, and exit 6.
The caller sees a failed step with no reason. Reproduced, not repaired:
`A_TRANSPORT_FAILURE_IS_SILENT` names it and the differential pins it.

K=5 LEDGER: `.ci/shadow/w7p6-purge-media-cache.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `ZONE_ID="9e802649c143c9cefd811d8fd671d31c" # rediacc.com` (:25) and
# `HOSTNAME="media.rediacc.com"` (:26). LITERALS, not arguments: a caller cannot
# point this at another zone or another hostname by accident, and that is the reason the script takes no options at all.
ZONE_ID = "9e802649c143c9cefd811d8fd671d31c"
PURGE_HOSTNAME = "media.rediacc.com"

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# `--data "{\"hosts\": [\"${HOSTNAME}\"]}"` (:43). Hand-built by the twin rather
# than by jq, SPACE AFTER THE COLON INCLUDED, so it is a literal here too: the fake curl records argv, and a body compacted differently is a different request even though Cloudflare would accept either.
PURGE_BODY = '{"hosts": ["%s"]}' % PURGE_HOSTNAME

# The two defects named in the module docstring, as constants so the tests can assert them by name rather than by restating the sentences.
A_TRANSPORT_FAILURE_IS_SILENT = True

# The one message that interpolates REMOTE text (:46). common.sh logs through `echo -e`, which interprets backslash escapes in the message, while `rediacc_ci.log` formats the message as data. A Cloudflare error containing a literal backslash-n therefore renders as a newline through the twin and as two characters here. The differential asserts BOTH directions so nobody "fixes" it.
PURGE_FAILED_PREFIX = "Purge failed: "


class BashExitError(Exception):
    """`set -e` firing on the failed `RESPONSE="$(curl ...)"` assignment."""

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def auth_headers(env: dict[str, str]) -> list[str] | None:
    """`AUTH_HEADERS` (:31-38). None means no usable credential.

    NOTE THE HEADER ORDER DIFFERS FROM `cf-purge-urls.sh`: this script emits
    `X-Auth-Key` BEFORE `X-Auth-Email`, its sibling emits them the other way
    round. Neither order matters to Cloudflare and both matter to a recorded
    argv, so each port carries its own twin's order rather than a shared helper's.
    """
    bearer = env.get("CLOUDFLARE_API_TOKEN", "")
    if bearer:
        return ["-H", "Authorization: Bearer %s" % bearer]
    key = env.get("CF_GLOBAL_API_KEY", "")
    email = env.get("CF_EMAIL", "")
    if key and email:
        return ["-H", "X-Auth-Key: %s" % key, "-H", "X-Auth-Email: %s" % email]
    return None


def curl_argv(headers: list[str]) -> list[str]:
    """The one request (:41-43), as an argv, so a test can pin its shape."""
    return [
        "curl",
        "-s",
        "-X",
        "POST",
        "%s/zones/%s/purge_cache" % (CF_API_BASE, ZONE_ID),
        *headers,
        "-H",
        "Content-Type: application/json",
        "--data",
        PURGE_BODY,
    ]


def _jq(args: list[str], stdin_text: str) -> str:
    """`echo "$x" | jq <args>` INSIDE A SUBSTITUTION THAT CANNOT KILL THE RUN.

    Both call sites in this twin are substitutions in a position `set -e`
    ignores (a `[[ ]]` test and an argument to `log_error`), so a failing jq
    contributes its stderr and an empty string, and the script carries on. jq's
    stderr is INHERITED for exactly that reason: it is the only trace left.
    """
    proc = subprocess.run(
        ["jq", *args],
        input=stdin_text,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stdout.rstrip("\n")  # command substitution strips trailing newlines


def _curl(argv: list[str]) -> str:
    """`RESPONSE="$(curl -s ...)"`: stdout captured, `set -e` armed on failure."""
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        # THE SILENT NON-ZERO. `-s` without `-S` means curl said nothing either.
        raise BashExitError(proc.returncode)
    return proc.stdout.rstrip("\n")


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    try:
        common.require_cmd("curl")
        common.require_cmd("jq")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    headers = auth_headers(dict(os.environ))
    if headers is None:
        log.error("Set CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL")
        return 1

    log.step("Purging Cloudflare cache for %s..." % PURGE_HOSTNAME)

    try:
        response = _curl(curl_argv(headers))
    except BashExitError as exc:
        return exc.code

    if _jq(["-r", ".success"], response + "\n") != "true":
        log.error(PURGE_FAILED_PREFIX + _jq(["-c", ".errors"], response + "\n"))
        return 1

    log.info("Purge complete. Cache repopulates on next request (cf-cache-status: MISS then HIT).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
