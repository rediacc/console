#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/cf-purge-urls.sh`.

Purges a list of URLs from one Cloudflare zone's edge cache, in batches of 30,
after a release upload. The twin's own header explains why it exists and why it
is best-effort: the real defence against a stale `releases.rediacc.com` object
is the zone-level Cache Rule in `.ci/docs/r2-setup.md`, and this purge is depth
behind it.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `curl` is the only external tool that
carries a credential, and the differential
(`.ci/rediacc_ci/tests/test_deploy_cf_purge_urls.py`) puts a RECORDING FAKE
`curl` on a scratch PATH that logs its exact argv and answers from a fixture.
Both sides are driven through the same fake, so the request shape is compared as
well as the two streams.

`jq` IS CALLED, NOT REIMPLEMENTED, for the same measured reason
`housekeeping/cleanup_cf_preview.py` gives: the twin's jq pipelines are
unguarded, so jq's own diagnostics and jq's own exit status ARE the script's
behaviour on a body that is not what it assumed. Driven 2026-09-13 against the
fake:

  * AN HTML ERROR PAGE kills the run: `jq: parse error: Invalid numeric literal
    at line 2, column 0` on stderr, exit 5, straight through `set -e` on the
    failed `SUCCESS=$(...)` assignment.
  * AN EMPTY BODY does not. `jq -r '.success // false'` over empty input emits
    nothing, `SUCCESS` is the empty string, and the run takes the ordinary
    "CF purge failed" warning branch and exits 0.

A `json.loads` port would pass every happy-path case and differ on both.

THE HEADER'S "ALWAYS EXITS 0" CLAIM IS NOT TRUE, AND THE PORT REPRODUCES THE
UNTRUTH RATHER THAN REPAIRING IT. Lines 21-28 of the twin promise the script
"always exits 0 even on credential/auth/API failures". Two paths break that
promise, both driven 2026-09-13:

  * A TRANSPORT FAILURE. `RESPONSE=$(curl -sS ...)` is an assignment, so a curl
    that cannot resolve the host fails the assignment and `set -e` ends the run
    with CURL'S status (6), after the "purging N URL(s)" line and with nothing
    saying a purge was skipped.
  * A NON-JSON BODY. Exit 5, as above.

`ALWAYS_EXITS_ZERO_IS_FALSE` names it so a test can assert it by name. Both are
reproduced because the acceptance rule for this wave is agreement with the live
twin; repairing either is a cutover-box decision, not this one's.

TWO DIVERGENCES, BOTH IN TEXT THAT ONLY A HUMAN READS:

  1. `--zone` AS THE LAST ARGUMENT. The twin reads `"$2"` under `set -u`, so
     bash itself refuses with `<path>: line 38: $2: unbound variable`, exit 1.
     That message names the bash file and a bash line number; this port prints
     `MISSING_ZONE_VALUE` on stderr and exits 1. Same stream, same status. Same
     ruling as `deploy/wait_for_preview_worker.py` made for `${VAR:?}`.
  2. `--help` IS A LITERAL HERE, NOT AN EXTRACTION. The twin prints its own
     header with `sed -n '2,/^$/p' "$0" | sed 's/^# \\{0,1\\}//'`, which is a
     program reading its own source. A port cannot read the twin's source
     without depending on the twin still existing, so `HELP` carries the same
     bytes as a constant, and `test_help_matches_the_twins_header_extraction`
     recomputes the sed pipeline from the twin file and fails if the two ever
     drift.

K=5 LEDGER: `.ci/shadow/w7p6-cf-purge-urls.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

# The twin's own name, printed in every message it emits (:53, :66, :83, :104).
# A literal rather than argv[0], because the messages must stay byte-identical
# through the port and argv[0] here is a `.py` path.
SELF = "cf-purge-urls.sh"

# `${URLS[@]:$i:30}` (:88). The Cloudflare purge_cache endpoint accepts at most
# 30 files per request, which is why the loop exists at all.
BATCH_SIZE = 30

# `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache` (:91).
CF_API_BASE = "https://api.cloudflare.com/client/v4"

# The `$2: unbound variable` stand-in named in divergence 1 above.
MISSING_ZONE_VALUE = "cf-purge-urls.sh: --zone requires a value"

# The two paths that break the header's "always exits 0" promise. Named as a
# constant so the differential can assert the defect by name rather than by
# restating the sentence.
ALWAYS_EXITS_ZERO_IS_FALSE = True

# `sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'` over the twin: its comment block
# from line 2 to the first empty line, with one leading `# ` removed. Kept as
# bytes here; the differential recomputes the extraction and compares.
HELP = """Purge a list of URLs from Cloudflare cache.

Usage:
  cf-purge-urls.sh --zone <ZONE_ID> url1 url2 ...
  printf '%s\\n' url1 url2 url3 | cf-purge-urls.sh --zone <ZONE_ID>

Auth (in order tried):
  1. $CLOUDFLARE_API_TOKEN  -> Authorization: Bearer
  2. $CF_GLOBAL_API_KEY + $CF_EMAIL -> X-Auth-Key + X-Auth-Email (global key)

Why: releases.rediacc.com is an R2 bucket exposed via a CF custom domain.
Even when uploads now set Cache-Control: no-cache, any pre-existing CF
edge-cache entry from before the fix persists with its original (default)
TTL, so apt-get update fetches the fresh InRelease but the old cached
Packages.gz body, producing "File has unexpected size, Mirror sync in
progress?" errors. Purging the just-uploaded URLs after each upload
evicts those stale entries; the next request hits R2 origin (which now
returns no-cache) and CF will not re-cache.

Failure mode: purge is best-effort defence in depth -- the real fix
against stale CF cache on releases.rediacc.com is the zone-level
Cache Rule documented in .ci/docs/r2-setup.md. This script therefore
always exits 0 even on credential/auth/API failures, and logs a
::warning:: so the CI run surfaces the issue without failing the job.
If the Cache Rule is ever disabled, the purge returning API errors
will still be visible as a warning and investigation can begin from
there.

"""


class BashExitError(Exception):
    """`set -e` firing on a failed assignment or pipeline.

    The twin has no handler for either: the command fails, the shell ends the
    run, and whatever the failing program already wrote to stderr is the only
    explanation. Modelled as an exception so each call site reads like the
    unguarded assignment it is porting.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


class HelpRequestedError(Exception):
    """`--help`: print the header, exit 0 (:41-44)."""


def parse_argv(argv: list[str]) -> tuple[str, list[str]]:
    """The `while [[ $# -gt 0 ]]` loop (:35-50). Returns (zone, urls).

    THREE RULES, all of them the twin's:
      * `--zone` consumes the NEXT token, whatever it looks like, and a later
        `--zone` overwrites an earlier one.
      * `--help` / `-h` wins the moment it is reached, even after other
        arguments, and is signalled here by returning the sentinel below.
      * EVERYTHING ELSE is a URL, including a token starting with `-`. There is
        no unknown-flag refusal, so `--dry-run` would be purged as a URL.

    Raises `BashExitError(1)` for a trailing `--zone`, which is bash's own `set -u`
    refusal on `"$2"` (divergence 1).
    """
    zone = ""
    urls: list[str] = []
    i = 0
    while i < len(argv):
        # NOT named `token`: ruff's S105 keys on the NAME and reads
        # `token == "--zone"` as a hardcoded credential comparison.
        word = argv[i]
        if word == "--zone":
            if i + 1 >= len(argv):
                print(MISSING_ZONE_VALUE, file=sys.stderr)
                raise BashExitError(1)
            zone = argv[i + 1]
            i += 2
        elif word in ("--help", "-h"):
            raise HelpRequestedError
        else:
            urls.append(word)
            i += 1
    return zone, urls


def stdin_urls(text: str) -> list[str]:
    """`while IFS= read -r line; do [[ -n "$line" ]] && URLS+=("$line"); done`.

    TWO BASH FACTS THAT A `for line in sys.stdin` PORT GETS WRONG:

      * A FINAL LINE WITH NO NEWLINE IS DROPPED. `read` stores it and then
        returns non-zero at EOF, so the loop body never runs for it. Python
        iteration would keep it, which would purge one URL the twin does not.
      * AN EMPTY LINE IS SKIPPED, and skipping it does NOT end the run under
        `set -e`: a failed test that is the LEFT side of an `&&` list is exempt.
    """
    if not text:
        return []
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()  # the empty tail split() leaves after a final newline
    else:
        lines.pop()  # the partial last line `read` never delivers
    return [line for line in lines if line]


def auth_headers(env: dict[str, str]) -> list[str] | None:
    """`AUTH_HEADERS` (:72-81). None means no usable credential.

    ORDER IS OBSERVABLE: a token wins over a global key even when both are set,
    and the global key needs BOTH halves. The header ORDER within each arm is
    the twin's too (`X-Auth-Email` before `X-Auth-Key`), because the fake curl
    records argv and a reordered pair is a different request.
    """
    bearer = env.get("CLOUDFLARE_API_TOKEN", "")
    if bearer:
        return ["-H", "Authorization: Bearer %s" % bearer]
    key = env.get("CF_GLOBAL_API_KEY", "")
    email = env.get("CF_EMAIL", "")
    if key and email:
        return ["-H", "X-Auth-Email: %s" % email, "-H", "X-Auth-Key: %s" % key]
    return None


def curl_argv(zone: str, headers: list[str], payload: str) -> list[str]:
    """The one request (:90-94), as an argv, so a test can pin its shape.

    `-sS`: silent except for errors, which is why a transport failure still puts
    curl's own message on stderr before `set -e` ends the run.
    """
    return [
        "curl",
        "-sS",
        "-X",
        "POST",
        "%s/zones/%s/purge_cache" % (CF_API_BASE, zone),
        *headers,
        "-H",
        "Content-Type: application/json",
        "--data",
        payload,
    ]


def batches(urls: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    """`i=0; while [[ $i -lt $TOTAL ]]; ... i=$((i + 30))` (:86-102)."""
    return [urls[i : i + size] for i in range(0, len(urls), size)]


def _jq(args: list[str], stdin_text: str) -> tuple[int, str]:
    """One `jq` run with its stderr INHERITED, as every twin pipeline leaves it.

    jq's diagnostics are the only explanation a workflow log gets when a body is
    not JSON, so they are not captured here either.
    """
    proc = subprocess.run(
        ["jq", *args],
        input=stdin_text,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def payload_for(batch: list[str]) -> str:
    """`printf '%s\\n' "${BATCH[@]}" | jq -R . | jq -sc '{files: .}'` (:89).

    `jq -R .` makes each LINE a JSON string, `jq -sc` slurps them into one array.
    Under `pipefail` the pipeline's status is the last command to fail, and the
    assignment then feeds `set -e`; that is why this raises rather than returns.
    """
    printed = "".join(url + "\n" for url in batch)
    rc_r, quoted = _jq(["-R", "."], printed)
    rc_s, payload = _jq(["-sc", "{files: .}"], quoted)
    status = rc_s or rc_r
    if status:
        raise BashExitError(status)
    return payload.rstrip("\n")  # command substitution strips trailing newlines


def _curl(argv: list[str]) -> str:
    """`RESPONSE=$(curl ...)`: stdout captured, stderr inherited, `set -e` armed."""
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        # THE FIRST HALF OF THE DEFECT NAMED IN THE DOCSTRING. The header promises
        # exit 0; this is curl's status ending the run instead.
        raise BashExitError(proc.returncode)
    return proc.stdout.rstrip("\n")


def main(argv: list[str]) -> int:
    try:
        zone, urls = parse_argv(argv)
    except HelpRequestedError:
        sys.stdout.write(HELP)
        return 0
    except BashExitError as exc:
        return exc.code

    if not zone:
        print("::error::%s: --zone <ZONE_ID> is required" % SELF, file=sys.stderr)
        return 1

    # `if [[ ! -t 0 ]]` (:58). A closed stdin is not a terminal either, and a
    # logger-style crash here would read as the script failing rather than as
    # there being nothing to read.
    try:
        piped = not sys.stdin.isatty()
    except (AttributeError, ValueError):
        piped = True
    if piped:
        urls = urls + stdin_urls(sys.stdin.read())

    total = len(urls)
    if total == 0:
        print("%s: no URLs to purge" % SELF)
        return 0

    headers = auth_headers(dict(os.environ))
    if headers is None:
        print(
            "::warning::%s: no Cloudflare credentials in env "
            "(set CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY+CF_EMAIL); skipping purge" % SELF,
            file=sys.stderr,
        )
        return 0

    print("%s: purging %d URL(s) from CF zone %s" % (SELF, total, zone))

    try:
        for index, batch in enumerate(batches(urls)):
            payload = payload_for(batch)
            response = _curl(curl_argv(zone, headers, payload))

            rc, success = _jq(["-r", ".success // false"], response + "\n")
            if rc:
                # THE SECOND HALF OF THE DEFECT: jq's status, not 0.
                raise BashExitError(rc)
            if success.rstrip("\n") != "true":
                print(
                    "::warning::CF purge failed for batch starting at index %d "
                    "(best-effort; Cache Rule makes this non-critical):" % (index * BATCH_SIZE),
                    file=sys.stderr,
                )
                # `echo "$RESPONSE" | jq -c '.errors' >&2`: jq's STDOUT is
                # redirected to stderr here, so the errors array lands on the
                # same stream as the warning above it.
                rc_err, errors = _jq(["-c", ".errors"], response + "\n")
                if rc_err:
                    raise BashExitError(rc_err)
                sys.stderr.write(errors)
                return 0
    except BashExitError as exc:
        return exc.code

    print("%s: purged %d URL(s) successfully" % (SELF, total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
