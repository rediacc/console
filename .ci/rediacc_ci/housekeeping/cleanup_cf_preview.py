#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/cleanup-cf-preview.sh`.

Deletes the Cloudflare Pages PREVIEW deployments belonging to one branch, which
is what runs on PR close so a merged branch does not leave its previews behind
forever.

Usage: cleanup_cf_preview.py --branch <branch_name> [--dry-run]

TWO CLOUDFLARE ENDPOINTS, AND NOTHING ELSE. Both are under
`https://api.cloudflare.com/client/v4`, both carry
`Authorization: Bearer $CLOUDFLARE_API_TOKEN` and `Content-Type: application/json`:

  GET    /accounts/<acct>/pages/projects/rediacc/deployments
             ?env=preview&per_page=25&page=<n>
  DELETE /accounts/<acct>/pages/projects/rediacc/deployments/<id>?force=true

The project name is the hard-coded literal `rediacc` (:21), not an argument, so
a caller cannot point this at another project by accident.

`jq` IS CALLED, NOT REIMPLEMENTED, AND THAT IS A DELIBERATE CHOICE. Every JSON
step here could be done with `json.loads`, and doing so would change observable
behaviour in three measured places, because none of the twin's `jq` pipelines is
guarded:

  * A NON-JSON BODY KILLS THE RUN. Driven 2026-09-13 with an HTML error page:
    `jq: parse error: Invalid numeric literal at line 2, column 0` on stderr and
    exit 5, straight through `set -e` on the failed assignment.
  * `{"success":true}` WITH NO `result` KEY ALSO KILLS IT, with
    `jq: error (at <stdin>:1): Cannot iterate over null (null)` and exit 5,
    because `[.result[] | ...]` runs before anything inspects the shape.
  * AN EMPTY BODY DOES NOT. `jq -r '.success // false'` over empty input emits
    nothing, `success` is the empty string, and the script takes the ordinary
    "CF API request failed on page N" warning branch.

Those are jq's own bytes and jq's own exit status, on a script whose caller is a
workflow log. Reproducing them from Python would mean emulating jq's
diagnostics, which is a much bigger thing to get wrong than shelling out to the
binary `require_cmd jq` already demands. So the port runs the SAME programs
against the SAME stdin, with stderr INHERITED exactly as the twin leaves it.

THE ARGUMENT PARSER IS NOT RE-IMPLEMENTED EITHER: `rediacc_ci.core.common.parse_args`
is the port of `parse_args` (common.sh:324-353) and carries its four rules and
both live quirks, including `--dry-run false` meaning NOT a dry run.

STREAMS: NOTHING THIS SCRIPT ITSELF WRITES GOES TO STDOUT. Every message is
`log_step` / `log_warn` / `log_info` / `log_debug`, all of which write to
stderr (common.sh:35-55). Only `jq`'s own diagnostics share that stream. A
successful deletion is `log_debug`, so the default-quiet run prints the step
lines and the tally and nothing per deployment.

THE DEFECT THIS PORT REPRODUCES, AND IT IS THE VACUITY CLASS. A LISTING THAT
NEVER SUCCEEDED IS REPORTED AS "NOTHING TO CLEAN UP", EXIT 0. The listing is
`response="$(cf_api GET ... 2>/dev/null || echo '{"result":[]}')"`; a curl that
cannot resolve the host, or a 403 whose body says `success: false`, both reach
`log_warn "CF API request failed on page 1"` and `break`, leaving
`all_deployments` at `[]`. The script then prints

    → Found 0 preview deployments for branch 'x'
    ✓ No preview deployments to clean up

and exits 0. Driven 2026-09-13. The warning is one line of stderr in the middle
of a green run: the caller sees a success, and a branch whose previews were
never enumerated is indistinguishable from a branch that had none.
`API_FAILURE_READS_AS_NOTHING_TO_DO` names it and the differential pins it in
both directions. Reproduced rather than repaired because the acceptance rule for
this wave is agreement with the live twin.

TWO DIVERGENCES, BOTH IN REFUSAL TEXT NOBODY PARSES:

  1. A flag whose name is not a valid shell identifier (`--foo.bar=x`) is
     `printf -v`'s own error in the twin, prefixed with `common.sh` and a line
     number, exit 2. `parse_args` here raises `RefusalError(code=2)` carrying
     the same message without the prefix. Same stream, same exit code. Identical
     ruling to `housekeeping/cleanup_pr_environments.py`.
  2. common.sh logs through `echo -e`, which interprets backslash escapes IN
     THE MESSAGE. The one message here that interpolates remote text is
     `Could not delete <id>: <error_msg>`, so a Cloudflare error containing a
     literal backslash-n renders as a newline through the twin and as two
     characters here. `rediacc_ci.log` formats the message as data on purpose
     (see its module docstring); the differential asserts both directions.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-cf-preview.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

USAGE = "Usage: cleanup-cf-preview.sh --branch <branch_name> [--dry-run]"

# `true`, exactly -- see parse_args quirk 2. `--dry-run false` is NOT a dry run.
DRY_RUN_ON = "true"

# `CF_PAGES_PROJECT="rediacc"` (:21). A literal, not an argument.
CF_PAGES_PROJECT = "rediacc"

# `https://api.cloudflare.com/client/v4$endpoint` (:46).
CF_API_BASE = "https://api.cloudflare.com/client/v4"

# `per_page=25` in the query and `-lt 25` in the loop guard (:66, :80). ONE
# constant, because a page size that disagreed with the termination test would
# either stop after page 1 or never stop at all.
PAGE_SIZE = 25

# The two `|| echo` fallbacks (:66, :104). Note they are DIFFERENT shapes: the
# listing's has no `success` key at all (so `.success // false` is false), the
# delete's says so explicitly.
LIST_FALLBACK = '{"result":[]}'
DELETE_FALLBACK = '{"success":false}'

# The defect named in the module docstring, as a constant so a test can assert
# it by name instead of restating the sentence.
API_FAILURE_READS_AS_NOTHING_TO_DO = True


def deployments_path(account: str, page: int) -> str:
    """The listing endpoint (:66).

    NOT URL-ENCODED, deliberately -- `$CLOUDFLARE_ACCOUNT_ID` is interpolated
    raw, the same latent defect both `housekeeping` siblings already record. It
    is unreachable in practice because a Cloudflare account id is a hex string,
    and it is reproduced rather than hardened because hardening it here would
    make this port disagree with the live script about which URL was requested.
    """
    return "/accounts/%s/pages/projects/%s/deployments?env=preview&per_page=%d&page=%d" % (
        account,
        CF_PAGES_PROJECT,
        PAGE_SIZE,
        page,
    )


def delete_path(account: str, deployment_id: str) -> str:
    """The delete endpoint (:104).

    `force=true` is what makes Cloudflare remove a deployment that still has
    aliases pointing at it. The LATEST deployment per branch still cannot be
    deleted, which is the case the `Could not delete` branch exists for and the
    reason this script is written to keep going rather than to refuse.
    """
    return "/accounts/%s/pages/projects/%s/deployments/%s?force=true" % (
        account,
        CF_PAGES_PROJECT,
        deployment_id,
    )


def curl_argv(method: str, endpoint: str, token: str) -> list[str]:
    """`cf_api` (:42-50), as an argv. Exposed so a test can assert the request
    shape -- method, URL, and both headers -- without a network."""
    return [
        "curl",
        "-s",
        "-X",
        method,
        CF_API_BASE + endpoint,
        "-H",
        "Authorization: Bearer %s" % token,
        "-H",
        "Content-Type: application/json",
    ]


def _substitution(argv: list[str], fallback: str) -> str:
    """`$(cmd 2>/dev/null || echo <fallback>)`.

    Both halves write to the same captured stdout, so a command that printed
    something AND failed contributes both, exactly as bash concatenates them,
    and command substitution then strips every trailing newline.
    """
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False
        )
    except FileNotFoundError:
        # `require_cmd curl` ran first, so this is unreachable; a traceback here
        # would read as a crash rather than as the failed request it is.
        return fallback
    text = proc.stdout
    if proc.returncode != 0:
        text += fallback + "\n"
    return text.rstrip("\n")


class JqError(Exception):
    """One `jq` invocation that failed, carrying the status `set -e` uses.

    The twin has no handler for this: the assignment fails, `set -e` fires, and
    the run ends with jq's own status and jq's own message already on stderr.
    Modelled as an exception rather than a return code so every call site reads
    like the unguarded assignment it is porting.
    """

    def __init__(self, code: int) -> None:
        super().__init__("jq exited %d" % code)
        self.code = code


def jq(args: list[str], stdin_text: str) -> str:
    """`echo "$x" | jq <args>`, with jq's stderr INHERITED.

    `echo` appends a newline and never fails, so under `pipefail` the pipeline's
    status is jq's. jq's diagnostics are NOT redirected in the twin, which is
    the only explanation a workflow log gets when a body is not what the script
    assumed -- so they are not captured here either.
    """
    proc = subprocess.run(
        ["jq", *args],
        input=stdin_text + "\n",
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise JqError(proc.returncode)
    return proc.stdout.rstrip("\n")


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # DIVERGENCE 1: bash prefixes this with `common.sh: line 333:`.
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 2)

    branch = args.get("ARG_BRANCH", "")
    dry_run = args.get("ARG_DRY_RUN", "false")

    try:
        common.require_cmd("curl")
        common.require_cmd("jq")
        token = common.require_var("CLOUDFLARE_API_TOKEN")
        account = common.require_var("CLOUDFLARE_ACCOUNT_ID")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    if not branch:
        log.error(USAGE)
        return 1

    log.step("Cleaning up CF Pages preview deployments for branch: %s" % branch)
    if dry_run == DRY_RUN_ON:
        log.warn("DRY-RUN mode: no deletions will be performed")

    try:
        return _sweep(branch, dry_run, token, account)
    except JqError as exc:
        # `set -e` on a failed assignment. jq has already written its own
        # diagnostic to stderr; the twin adds nothing and neither does this.
        return exc.code


def _sweep(branch: str, dry_run: str, token: str, account: str) -> int:
    all_deployments = "[]"
    page = 1

    while True:
        response = _substitution(
            curl_argv("GET", deployments_path(account, page), token), LIST_FALLBACK
        )

        success = jq(["-r", ".success // false"], response)
        if success != "true":
            # THE DEFECT. This is one warning line on stderr, and the run
            # continues to a green "nothing to clean up". See the module
            # docstring.
            log.warn("CF API request failed on page %d" % page)
            break

        # Computed BEFORE the length below, which is why a `result`-less body
        # dies here rather than reporting zero.
        page_results = jq(
            [
                "--arg",
                "branch",
                branch,
                (
                    "[.result[] | select(.deployment_trigger.metadata.branch == $branch) "
                    "| {id: .id, created_on: .created_on}]"
                ),
            ],
            response,
        )
        all_results = jq([".result | length"], response)
        # The jq PROGRAM is built by interpolating one jq output into another,
        # exactly as the twin does at :78. Kept as string interpolation rather
        # than `--argjson` so a malformed accumulator fails the same way.
        all_deployments = jq([". + %s" % page_results], all_deployments)

        if int(all_results) < PAGE_SIZE:
            break
        page += 1

    total = int(jq(["length"], all_deployments))
    log.step("Found %d preview deployments for branch '%s'" % (total, branch))

    if total == 0:
        log.info("No preview deployments to clean up")
        return 0

    deleted = 0
    for deployment in jq(["-c", ".[]"], all_deployments).split("\n"):
        dep_id = jq(["-r", ".id"], deployment)
        created_on = jq(["-r", ".created_on"], deployment)

        if dry_run == DRY_RUN_ON:
            log.warn("[DRY-RUN] Would delete: %s (created: %s)" % (dep_id, created_on))
            deleted += 1
            continue

        del_response = _substitution(
            curl_argv("DELETE", delete_path(account, dep_id), token), DELETE_FALLBACK
        )
        del_success = jq(["-r", ".success // false"], del_response)

        if del_success == "true":
            log.debug("Deleted: %s" % dep_id)
            deleted += 1
        else:
            # "the latest deployment cannot be deleted" is the expected one, and
            # the script keeps going: a branch's newest preview is Cloudflare's
            # to hold, and refusing over it would leave the older ones behind.
            error_msg = jq(["-r", '.errors[0].message // "unknown error"'], del_response)
            log.warn("Could not delete %s: %s" % (dep_id, error_msg))

    if dry_run == DRY_RUN_ON:
        log.info("Would delete %d of %d deployments for branch '%s'" % (deleted, total, branch))
    else:
        log.info("Deleted %d of %d deployments for branch '%s'" % (deleted, total, branch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
