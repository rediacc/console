#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/cleanup-stale-d1.sh`.

Delete orphaned `migration-test-*` D1 databases older than `--max-age` minutes.
The twin's header states the role: defence in depth for the migration-test CI
job, which normally cleans up through `trap EXIT`. It runs as a PRE-REAP step on
every migration-test job, so orphans left by an interrupted prior run are
cleared before the new run creates its own databases.

Usage: cleanup_stale_d1.py [--dry-run] [--max-age <minutes>]
Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.

-----------------------------------------------------------------------------
IT IS `npx wrangler`, NOT `wrangler`, AND THAT IS THE ARGV THAT MATTERS
-----------------------------------------------------------------------------
Both call sites shell out through npx:

    npx wrangler d1 list --json
    npx wrangler d1 delete "$db_name" --skip-confirmation

`require_cmd npx` is what the twin guards on, and there is no `require_cmd
wrangler` anywhere -- so on a host with npx and no wrangler the script gets past
its guards and fails inside the list call, which is caught by `|| true` and
reported as "No D1 databases found (or API unavailable)". A missing tool
therefore reads as a CLEAN CLOUDFLARE ACCOUNT. That is a green-when-unknown
shape and it is named in the hazard section below.

The differential stubs `npx` for exactly this reason: stubbing `wrangler` alone
would leave both sides resolving the real npx, which would try to install a
package over the network.

-----------------------------------------------------------------------------
WHAT IS EXECUTED RATHER THAN REIMPLEMENTED
-----------------------------------------------------------------------------
`date` IS RUN, both the `date --version` probe and the arithmetic, and the
reason is the same one `rediacc_ci.infra.docker_prepull` gives for executing `sleep`: the twin
resolves it through PATH, so one binary answers for both sides.

    if date --version >/dev/null 2>&1; then date -u -d "N minutes ago" +FMT
    else                                    date -u -v-NM +FMT

Reimplementing with `datetime` would have bought a divergence on every input the
twin does not validate. `--max-age abc` makes GNU date print `invalid date
'abc minutes ago'` and exit 1, and under `set -e` the command substitution takes
the script down with that status; `--max-age -30` reaches into the FUTURE and
selects everything. Executing `date` reproduces all of it for free, including
the BSD arm on a Mac, which no amount of Python could be differentially checked
against on this machine.

`jq` IS NOT RUN, and that is the one deliberate reimplementation. The twin uses
it three times -- `jq empty` to validate, `jq 'length'` to count, and a `jq -r`
filter to select -- and Python's `json` answers all three for the data wrangler
actually returns. `require_cmd jq` IS STILL CALLED, on purpose: dropping it
would silently widen the set of hosts the script runs on, which is a cutover
decision and not a porting one. So the guard fires identically and the parsing
is native. Three edges where jq and `json.loads` genuinely differ, none of them
reachable from wrangler output, all named rather than left to be discovered:

  * jq's parser accepts a STREAM of concatenated values (`[1] [2]`); json.loads
    accepts exactly one.
  * Python's `json.loads` accepts `NaN`, `Infinity` and `-Infinity`; jq does not.
  * `jq 'length'` on a non-array answers something (object key count, string
    length) where this port would not. Unreachable: the `sed` extraction below
    only ever hands over text starting with `[`.

-----------------------------------------------------------------------------
THE COMPARISON IS LEXICOGRAPHIC ON STRINGS, NOT ON TIMESTAMPS
-----------------------------------------------------------------------------
    select(.created_at < $cutoff)

is jq's STRING comparison, and the two operands are not the same shape: wrangler
returns `2026-09-13T12:00:00.000Z` (24 chars) while `$cutoff` is
`%Y-%m-%dT%H:%M:%S` (19 chars, no fraction, no zone). So when the first 19
characters are equal the created_at is LONGER and therefore GREATER, i.e. a
database created in the same second as the cutoff is NOT stale. Reproduced with
Python's `<` on `str`, which is the same ordering. A port that parsed both into
`datetime` would flip that boundary case, and would also start raising on any
`created_at` wrangler ever renders differently.

A DATABASE WITH NO `created_at` IS NOT SELECTED, on both sides: jq compares
`null < "..."`, and null sorts below every string, so `null` WOULD be selected.
This port matches that by treating a missing key as `None` and ordering it below
any string, rather than by skipping the row. Pinned by
`test_a_database_with_no_created_at_is_stale_on_both_sides`.

A DATABASE WITH NO `name` IS THE ONE SHAPE THAT DIVERGES, and it is named rather
than reproduced. `null | startswith("migration-test-")` is a jq TYPE ERROR, so
the twin's `set -e` ends the whole run with jq's status and jq's message; this
port skips the entry. Reproducing a type error to stay bug-compatible would mean
writing a jq error emulator into a reaper, and no wrangler response omits
`name`. Stated here so a future reader does not read the skip as an oversight.

-----------------------------------------------------------------------------
HAZARDS, REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
HAZARD 1 -- "COULD NOT REACH CLOUDFLARE" AND "NOTHING TO DO" ARE THE SAME EXIT.
`RAW_OUTPUT="$(npx wrangler d1 list --json 2>/dev/null || true)"` throws away
both the status and the stderr, so an expired token, a 5xx, a rate limit, an
npx that cannot resolve wrangler and a genuinely empty account all reach
`log_info "No D1 databases found (or API unavailable)"` and `exit 0`. The
message even names the ambiguity in parentheses and then exits green anyway. A
gate would have to fail here; this is a reaper, and a reaper that exits 0 leaves
the orphans it was scheduled to remove, silently, on every run. Preserved
exactly, and pinned by `test_an_unreachable_api_is_a_green_exit_on_both_sides`.

HAZARD 2 -- A FAILED DELETE IS A WARNING, AND THE FINAL LINE STILL READS LIKE
SUCCESS. `log_warn "Failed to delete: $db"` does not touch the exit status, so
the script ends 0 having deleted nothing, under a line that says
`Deleted 0 of 3 stale databases`. That line is at least honest about the count,
which is why this is a warning-shaped hazard rather than a lie. Preserved.

HAZARD 3 -- `--max-age` IS NEVER VALIDATED. It is interpolated straight into
`date` and into the log line. See the `date` note above for what each bad shape
does.

Exit: 0 on every path the twin reaches, including both early returns and a run
where every delete failed; `date`'s status when the cutoff cannot be computed;
1 from `require_cmd` / `require_var`; 2 from `parse_args` on a key that is not a
shell identifier.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-stale-d1.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `PREFIX="migration-test-"` (line 25). The trailing dash is part of it.
PREFIX = "migration-test-"

# `MAX_AGE_MINUTES="${ARG_MAX_AGE:-60}"` (line 24), as the STRING the twin holds:
# it is never arithmetic here, only interpolated into `date` and a log line.
DEFAULT_MAX_AGE = "60"

# `'+%Y-%m-%dT%H:%M:%S'` -- no fraction, no zone. See the comparison note above.
CUTOFF_FORMAT = "+%Y-%m-%dT%H:%M:%S"

NO_DATABASES = "No D1 databases found (or API unavailable)"
NO_STALE = "No stale migration-test databases found"
DRY_RUN_BANNER = "DRY-RUN mode: no deletions will be performed"


def sed_from_first_bracket(text: str) -> str:
    """`sed -n '/^\\[/,$p'` (line 44), which is the twin's JSON extractor.

    Wrangler prints banners before its JSON, so the twin takes everything from
    the FIRST line beginning with `[` to the end of the stream. Two properties
    that a "find the JSON" helper would get wrong and this does not:

      * it is anchored at the START of a line, so a `[` mid-line does not open
        the range;
      * the range ends at `$`, the end of input, so trailing banner text AFTER
        the JSON is INCLUDED and then fails validation, which sends the whole
        run down the "No D1 databases found" path.

    `sed -n` prints each selected line with a newline, and the command
    substitution around it strips trailing newlines. Both are reproduced.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("["):
            return "\n".join(lines[i:]).rstrip("\n")
    return ""


def parse_databases(blob: str) -> list[dict] | None:
    """`jq empty` then `jq 'length'`. None means "not JSON", i.e. the exit-0 path.

    Returns the decoded list so the caller counts it once instead of shelling
    out twice, which is the only structural difference from the twin here.
    """
    if not blob:
        return None
    try:
        value = json.loads(blob)
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, list):
        # Unreachable through `sed_from_first_bracket`, which guarantees a
        # leading `[`. Answered rather than asserted: a crash in a reaper is
        # worse than the twin's behaviour on input neither can receive.
        return None
    return value


def _sort_key(created_at: object) -> tuple[int, str]:
    """jq's ordering of `null` against a string: null sorts BELOW every string.

    Returned as a tuple so a missing `created_at` compares less than any cutoff
    without a special case at the call site.
    """
    if isinstance(created_at, str):
        return (1, created_at)
    return (0, "")


def stale_names(databases: list[dict], cutoff: str) -> list[str]:
    """The `jq -r` filter (lines 63-64), in the twin's order.

    `.[] | select(.name | startswith($prefix)) | select(.created_at < $cutoff)
     | .name`

    ORDER IS PRESERVED, not sorted: jq emits in array order and the delete loop
    reads that order, so a port that sorted would delete in a different sequence
    and the call log would diverge even though the SET agreed.
    """
    out = []
    for entry in databases:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name.startswith(PREFIX):
            continue
        if _sort_key(entry.get("created_at")) < _sort_key(cutoff):
            out.append(name)
    return out


def compute_cutoff(max_age: str) -> tuple[str | None, int]:
    """Lines 53-59, EXECUTED. Returns (cutoff, exit status).

    A `None` cutoff means `date` failed and the twin's `set -e` would have ended
    the run there, with date's own status and date's own message already on
    stderr -- which is why stderr is INHERITED rather than captured.
    """
    with open(os.devnull, "wb") as null:
        try:
            gnu = subprocess.run(
                ["date", "--version"], stdout=null, stderr=null, check=False
            ).returncode
        except OSError:
            print("date: command not found", file=sys.stderr, flush=True)
            return None, 127
    if gnu == 0:
        argv = ["date", "-u", "-d", "%s minutes ago" % max_age, CUTOFF_FORMAT]
    else:
        # BSD/macOS. `-v-30M`, with the value glued to the flag exactly as the
        # twin writes it.
        argv = ["date", "-u", "-v-%sM" % max_age, CUTOFF_FORMAT]
    sys.stdout.flush()
    proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return None, proc.returncode
    # `$(...)` strips trailing newlines.
    return proc.stdout.decode("utf-8", errors="replace").rstrip("\n"), 0


def list_databases() -> str:
    """`npx wrangler d1 list --json 2>/dev/null || true`.

    STDERR IS DISCARDED AND THE STATUS IS THROWN AWAY. That is hazard 1, and it
    is reproduced rather than improved: a port that surfaced the error would
    take a branch the twin cannot take.
    """
    sys.stdout.flush()
    with open(os.devnull, "wb") as null:
        try:
            proc = subprocess.run(
                ["npx", "wrangler", "d1", "list", "--json"],
                stdout=subprocess.PIPE,
                stderr=null,
                check=False,
            )
        except OSError:
            return ""
    return proc.stdout.decode("utf-8", errors="replace")


def delete_database(name: str) -> bool:
    """`npx wrangler d1 delete "$db" --skip-confirmation 2>/dev/null`.

    STDOUT IS NOT REDIRECTED in the twin, only stderr, so wrangler's own
    confirmation text lands on this script's stdout. Inherited here for the same
    reason.
    """
    sys.stdout.flush()
    with open(os.devnull, "wb") as null:
        try:
            code = subprocess.run(
                ["npx", "wrangler", "d1", "delete", name, "--skip-confirmation"],
                stderr=null,
                check=False,
            ).returncode
        except OSError:
            return False
    return code == 0


def main(argv: list[str]) -> int:
    env = dict(os.environ)

    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    dry_run = (args.get("ARG_DRY_RUN") or "false") == "true"
    max_age = args.get("ARG_MAX_AGE") or DEFAULT_MAX_AGE

    # THE GUARD ORDER IS THE TWIN'S (lines 31-34) and it is observable: a host
    # with no jq and no CLOUDFLARE_API_TOKEN is told about jq, not about the
    # token. `require_cmd jq` stays even though this port parses JSON natively;
    # see the module docstring.
    try:
        common.require_cmd("jq")
        common.require_cmd("npx")
        common.require_var("CLOUDFLARE_API_TOKEN", env)
        common.require_var("CLOUDFLARE_ACCOUNT_ID", env)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    log.step("Listing D1 databases...")

    databases = parse_databases(sed_from_first_bracket(list_databases()))
    if databases is None:
        log.info(NO_DATABASES)
        return 0

    log.info("Found %d total D1 databases" % len(databases))

    cutoff, code = compute_cutoff(max_age)
    if cutoff is None:
        return code
    log.info("Cutoff: %s (databases older than %sm)" % (cutoff, max_age))

    stale = stale_names(databases, cutoff)
    if not stale:
        log.info(NO_STALE)
        return 0

    log.step("Found %d stale database(s)" % len(stale))

    if dry_run:
        log.warn(DRY_RUN_BANNER)

    deleted = 0
    for name in stale:
        if dry_run:
            log.warn("[DRY-RUN] Would delete: %s" % name)
            deleted += 1
        else:
            log.info("Deleting: %s" % name)
            if delete_database(name):
                deleted += 1
            else:
                # HAZARD 2: a warning, and the exit status is untouched.
                log.warn("Failed to delete: %s" % name)

    if dry_run:
        log.info("Would delete %d of %d stale databases" % (deleted, len(stale)))
    else:
        log.info("Deleted %d of %d stale databases" % (deleted, len(stale)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
