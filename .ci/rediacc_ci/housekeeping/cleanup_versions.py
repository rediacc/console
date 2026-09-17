#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/cleanup-versions.sh` (2055 lines, 14 phases).

The nightly reaper. It deletes GitHub releases, git tags, GHCR package versions,
deployment records, Cloudflare Pages preview deployments, per-PR preview Workers,
GitHub environments, D1 preview databases, per-PR Turnstile widgets, R2 orphans,
stale branches, workflow runs, workflow artifacts and Actions cache entries, in
that order, under one global delete budget.

Usage: cleanup_versions.py [--days N] [--versions N] [--dry-run]

-----------------------------------------------------------------------------
THE TWIN IS THE LIVE GATE. THIS IS THE VERIFIED-EQUIVALENT ALTERNATIVE.
-----------------------------------------------------------------------------
Nothing here is wired into `npm run ci`, the manifest, or any workflow. The bash
twin stays registered and stays the thing that runs nightly; this file exists so
the cutover, when a driver makes it, is a one-line change against a port whose
equivalence is already on the record.

    differential: `.ci/rediacc_ci/tests/test_housekeeping_cleanup_versions.py`
    K=5 ledger:   `.ci/shadow/w7p6-cleanup-versions.observations.jsonl`

-----------------------------------------------------------------------------
THE SEAM THAT MAKES ONE PHASE DRIVABLE, AND WHY IT IS SHAPED LIKE THIS
-----------------------------------------------------------------------------
The twin's own header says it: "The phase sequence lives in a function so a test
can source this file and drive ONE phase in isolation -- which is how Phase 9's
delete arm finally got executed anywhere." That seam is

    source .ci/scripts/housekeeping/cleanup-versions.sh --dry-run
    cleanup_stale_branches

and sourcing is what runs `parse_args`, the five `require_*` guards, and the
config block. The port mirrors it exactly:

    hk = Housekeeping(["--dry-run"])       # parse_args + require_* + config
    hk.cleanup_stale_branches()            # one phase, in isolation

`Housekeeping.__init__` therefore does everything the twin does at SOURCE time,
including the guards, and a phase method does everything one twin function does.
That is not decoration: the differential drives all 14 phases through it, one at
a time, against the same recording fakes.

-----------------------------------------------------------------------------
WHAT IS EXECUTED RATHER THAN REIMPLEMENTED
-----------------------------------------------------------------------------
`gh`, `curl`, `aws`, `date`, `sleep` and `sort -V` are EXECUTED, with the twin's
argv byte for byte. Three reasons, in descending order of how much they matter:

  1. The argv IS the behaviour. This program's whole output is a sequence of
     API calls; a port that issued a different call would be wrong even if every
     log line matched. The differential records argv per call and compares the
     log, which is only meaningful if both sides really shell out.
  2. `date -d "<anything>"` is a parser nobody should reimplement. The twin
     hands it unvalidated API strings and unvalidated `--days` values, and its
     answers on the strange ones (`--days ""`, an RFC3339 with a fractional
     second, a BSD fallback that fails on GNU) are free here.
  3. `sleep` resolves through PATH on both sides, so one stub answers for both
     and the retry schedule is testable without six real seconds per assertion.

`jq` IS REIMPLEMENTED, and that is the one large deliberate difference. The twin
runs jq roughly sixty times; every filter is one of a dozen shapes (`length`,
`.[]`, `sort_by(...)|reverse`, `[.[]|{...}]`, `group_by`, `add // 0`, a slice,
an `index($x) != null`, a `test("^pr-[0-9]+$")` select). Each one is a named
function in the JQ FILTERS section below, the twin's filter text is quoted in its
docstring, and `test_..._filters_agree_with_the_real_jq` drives every one of them
against the real `jq` binary over a corpus that includes the empty case, the
missing-key case and the null case. `require_cmd jq` still runs, on purpose:
dropping it would widen the set of hosts this runs on, and that is a cutover
decision, not a porting one.

THE ONE PLACE jq IS STILL EXECUTED is the failure path. When the twin feeds jq
something that is not JSON, jq prints its own diagnostic and exits 5, and `set
-e` takes the run down with that status. `_jq_or_die` reproduces that by handing
the offending bytes to the real jq and exiting with its status and its message,
rather than by inventing a Python-shaped traceback for a path the twin has a
byte-exact answer for.

-----------------------------------------------------------------------------
BASH ARITHMETIC IS EMULATED, INCLUDING THE OCTAL TRAP
-----------------------------------------------------------------------------
`[[ $index -lt $KEEP_VERSIONS ]]` and `$((...))` are arithmetic contexts, and
bash's integer literal rules are C's: a leading `0` means OCTAL. So

    cleanup-versions.sh --versions 010     keeps EIGHT versions, silently
    cleanup-versions.sh --versions 08      prints
        ...: line 211: [[: 08: value too great for base (error token is "08")
      and evaluates FALSE, i.e. the item is treated as outside the keep window

Both are the twin's live behaviour on an operator's own input (`--days` and
`--versions` are documented flags), and both are reproduced by `arith` rather
than papered over: a port that read these with `int()` would keep ten versions
where the twin keeps eight, which is a difference in what gets DELETED.

THE ONE NAMED DIVERGENCE IN THE WHOLE PORT is the text of that error. bash
prefixes it with the script path and the LINE NUMBER of the comparison; this port
cannot honestly claim a line in a file it is not. It prints the same sentence
under its own name and takes the same branch (false). Pinned, in both directions,
by `test_a_zero_padded_versions_value_is_octal_on_both_sides` and
`test_an_invalid_octal_versions_value_takes_the_same_branch_on_both_sides`.

-----------------------------------------------------------------------------
HAZARDS IN THE TWIN, REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
Every one of these is preserved byte for byte, because a port that improves the
thing it is being compared against cannot be compared against it. They are
listed so the cutover box has the list, and each is pinned by a test.

HAZARD 1 -- "COULD NOT LIST" READS AS "NOTHING TO DELETE", IN NINE PHASES.
`gh release list ... 2>/dev/null || echo "[]"` (Phase 1) and its eight siblings
turn an expired token, a 5xx, a rate limit and a genuinely empty account into
the same empty list, and the phase then reports `deleted 0 of 0` and returns 0.
Phase 5b is the one that gets this right, and its banner says why: it FAILS
CLOSED because its worst case is deleting a live preview. Phases 1, 2, 3, 4, 5,
6, 7, 7b, 9 and 11 all fail OPEN. Phase 10 is the only other one that says
anything at all ("No active workflows listed (API error?)").

HAZARD 2 -- PHASE 3 COUNTS A DRY-RUN DELETE AND PHASE 1 DOES NOT. Phase 1's
dry-run arm logs `[DRY-RUN] Would delete release` and leaves `deleted` alone, so
its summary always reads `would delete 0 of N`. Phase 3, 4, 6, 7, 7b, 9, 10, 11
and 12 all increment. So `--dry-run` under-reports exactly one phase, and it is
the first one in the run.

HAZARD 3 -- PHASE 5b NEVER CALLS `record_delete`. It deletes Workers through the
Cloudflare API and does not charge them to the global budget, so a run that
deletes 40 Workers still believes it has deleted zero. Every other destructive
arm in the file records. Pinned by
`test_phase_5b_does_not_charge_the_delete_budget`.

HAZARD 4 -- PHASE 6 CANNOT SUCCEED, BY DESIGN. Deleting an environment object
needs Administration:write, which `check-no-app-admin-perm.sh` forbids the App
from ever holding. The phase's own banner says so. It is ported unchanged,
including the `log_info` (not `log_warn`) on the 403 and the `break` that stops
after the first one.

HAZARD 5 -- PHASE 4's `for env in $environments` IS UNQUOTED, so an environment
name containing whitespace would split into two names and an environment name
containing a glob metacharacter would be pathname-expanded against the CWD.
Neither can happen with `pr-N`/`edge`/`stable`, and the port splits on
whitespace without globbing. Named because it is a difference, not because it is
reachable.

HAZARD 6 -- PHASE 9's DELETE FAILURE IS THE ONLY ONE THAT FAILS THE RUN.
`housekeeping_fail` is called from exactly two places: the Phase 8d drift arm and
the Phase 9 delete arm. Every other failed delete in the file is a `log_warn` and
the run still exits 0.

HAZARD 7 -- `should_retain` RE-DERIVES THE CUTOFF PER ITEM, so the twin forks
`date` twice for every release, tag, package version and Pages deployment it
looks at. Reproduced (the port shells out to `date` identically), and it is the
single biggest cost in the port's own runtime.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
Read directly at each call site, never through a `dict(os.environ)` alias:
GH_TOKEN, GITHUB_ACTIONS, DEBUG (through `rediacc_ci.log`), MAX_DELETES_PER_RUN,
BRANCH_MAX_AGE_DAYS, RELEASES_BUCKET, CLOUDFLARE_API_TOKEN,
CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_R2_ACCESS_KEY_ID,
CLOUDFLARE_R2_SECRET_ACCESS_KEY, CLOUDFLARE_R2_ENDPOINT, IN_FLIGHT_VERSION.

Exit: 0 on every path except a latched failure (1, from `run_all_phases` after
every phase has run), a `require_*` refusal (1), a `parse_args` refusal (2), and
whatever `jq` exits with when the twin's `set -e` would have died on it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.core import release_state_validator as rsv

# =============================================================================
# CONFIGURATION -- the twin's block at :21-124, constant for constant.
# =============================================================================

# `RETENTION_DAYS="${ARG_DAYS:-14}"` / `KEEP_VERSIONS="${ARG_VERSIONS:-20}"`.
# Held as STRINGS because that is what bash holds: they reach `date` as text and `[[ -lt ]]` as an arithmetic word, and both of those care about the spelling.
DEFAULT_RETENTION_DAYS = "14"
DEFAULT_KEEP_VERSIONS = "20"

GITHUB_ORG = "rediacc"
TAG_REPOS = ("console", "renet")
GHCR_PACKAGES = ("renet", "rdc", "server")
DEPLOYMENT_REPOS = ("console",)
BRANCH_REPOS = ("console", "renet", "account", "elite", "homebrew-tap", "sql")

# `BRANCH_MAX_AGE_DAYS="${BRANCH_MAX_AGE_DAYS:-30}"`. A TESTING SEAM, in the
# twin's own words: there is no workflow_dispatch input for it and there should not be one, because a gate cannot fabricate a 30-day-old branch.
DEFAULT_BRANCH_MAX_AGE_DAYS = "30"

RELEASE_REPO = "rediacc/console"
CF_PAGES_PROJECT = "rediacc"

# `R2_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"`. constants.sh has already
# defaulted RELEASES_BUCKET by the time the twin reads it, so the two `:-` defaults are the same value twice.
DEFAULT_R2_BUCKET = "rediacc-releases"
R2_RETENTION_DAYS = 7
R2_FORMAT_DIRS = ("cli", "npm", "apt", "rpm", "apk", "archlinux")
R2_ORPHAN_VERSION_AGE_DAYS = 14
R2_PR_MAX_AGE_DAYS = 3
R2_PACKAGE_KEEP_VERSIONS = 20

GH_RUNS_KEEP_PER_WORKFLOW = 100
GH_RUNS_RETENTION_DAYS = 30
GH_RUNS_RETENTION_DAYS_WATCHDOG = 7
WATCHDOG_PATH = ".github/workflows/watchdog-monitor.yml"
GH_RUNS_MAX_PAGES_PER_WORKFLOW = 10

GH_ARTIFACTS_RETENTION_DAYS = 14
GH_ARTIFACTS_MAX_PAGES = 30

GH_CACHE_KEEP_GB = 5

# `MAX_DELETES_PER_RUN="${MAX_DELETES_PER_RUN:-1500}"`. Same testing-seam status
# as BRANCH_MAX_AGE_DAYS; the twin's comment explains why 1500 and not 1000.
DEFAULT_MAX_DELETES_PER_RUN = "1500"

# The phase-3 pagination safety bound, `local max_pages=200`.
PACKAGE_MAX_PAGES = 200

# `keep_per_env=2` in Phase 4.
DEPLOYMENTS_KEEP_PER_ENV = 2

# Phase 7b's `grace_seconds=$((24 * 60 * 60))`.
TURNSTILE_GRACE_SECONDS = 24 * 60 * 60

# Phase 8e's `mpu_max_age=$((24 * 3600))`.
MULTIPART_MAX_AGE_SECONDS = 24 * 3600

# The consecutive-failure circuit breaker, spelled `-ge 5` in Phases 3, 10, 11 and 12.
CONSECUTIVE_FAILURE_LIMIT = 5


# =============================================================================
# BASH ARITHMETIC
# =============================================================================


class BashArithError(Exception):
    """A word bash's arithmetic evaluator refuses, e.g. `08` or `1x`.

    Carries the token bash would name in `(error token is "...")`, so the caller
    can print the same sentence.
    """

    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


def arith(word: object) -> int:
    """Evaluate one bash arithmetic WORD, with bash's integer literal rules.

    Only the shapes that can reach this program's comparisons are supported: an
    optional sign, then a literal in one of bash's bases. That is deliberate --
    a general `$((...))` evaluator would be a much larger thing to get wrong for
    inputs the twin's variables cannot hold, since every operand here comes from
    `date +%s`, a jq number, a loop counter, or an operator's flag value.

    THE RULES, from bash's `strtol`-shaped constant parser:

      * `""` (and an unset variable) is 0. This is why `[[ 0 -lt "" ]]` is
        false rather than a syntax error, which the probe in the test file
        confirms against the real bash.
      * `0x`/`0X` is hexadecimal, `0b`/`0B` is NOT (bash has no binary literal;
        `0b1` is an invalid octal digit).
      * A leading `0` with more digits is OCTAL. `010` is 8. This is the trap
        the module docstring opens with.
      * `base#digits` is that base. Reachable only from an operator flag, and
        supported because refusing it here would be a divergence in the
        direction of crashing.
      * Anything else -- `08`, `1x`, `abc` -- raises. bash prints
        `value too great for base` for a bad digit in a base it recognises and
        `syntax error` for a word it cannot lex at all; both take the FALSE
        branch in `[[ ]]`, which is what callers here act on, so the two are not
        distinguished.

    An int passes straight through: the phase code counts with real integers and
    only the values that came from outside need the bash reading.
    """
    if isinstance(word, int):
        return word
    text = str(word).strip()
    if text == "":
        return 0
    sign = 1
    if text[0] in "+-":
        if text[0] == "-":
            sign = -1
        text = text[1:]
    if text == "":
        raise BashArithError(str(word).strip())
    try:
        if "#" in text:
            base_text, _, digits = text.partition("#")
            return sign * int(digits, int(base_text))
        if text[:2].lower() == "0x":
            return sign * int(text, 16)
        if text[0] == "0" and len(text) > 1:
            return sign * int(text, 8)
        return sign * int(text, 10)
    except ValueError:
        raise BashArithError(str(word).strip()) from None


def _arith_report(token: str, context: str = "[[: ") -> None:
    """The diagnostic bash prints for a refused arithmetic word.

    THE ONE NAMED DIVERGENCE IN THE PORT. bash writes

        <script>: line <N>: [[: 08: value too great for base (error token is "08")

    for a comparison and the same line WITHOUT the `[[: ` for a `$(( ))`, and
    this writes the same two sentences under this file's own name, without a
    line number: claiming a line in `cleanup-versions.sh` from here would be a
    lie, and claiming one in this file would be a number the reader of a ported
    message cannot use. The BRANCH taken is identical either way, which is the
    part that decides what gets deleted.
    """
    sys.stderr.write(
        "cleanup_versions.py: %s%s: value too great for base "
        '(error token is "%s")\n' % (context, token, token)
    )
    sys.stderr.flush()


def arith_cmp(left: object, op: str, right: object) -> bool:
    """`[[ left -op right ]]`, including what bash does when a word is refused.

    bash evaluates the comparison, prints the diagnostic for the offending word,
    and returns 1 -- FALSE -- without aborting, because the `[[ ]]` sits in an
    `if` condition everywhere it appears here. Verified against the real bash by
    `test_bash_refuses_08_and_returns_false_without_aborting`.
    """
    try:
        a = arith(left)
        b = arith(right)
    except BashArithError as exc:
        _arith_report(exc.token)
        return False
    if op == "lt":
        return a < b
    if op == "le":
        return a <= b
    if op == "gt":
        return a > b
    if op == "ge":
        return a >= b
    if op == "eq":
        return a == b
    if op == "ne":
        return a != b
    raise ValueError("unknown comparison operator %r" % op)


# =============================================================================
# PROCESS HELPERS
# =============================================================================


def _capture(argv: list[str], *, stderr: int | None) -> tuple[int, str]:
    """One command inside `$( )`: returns its status and its stdout, denewlined.

    `$( )` strips ALL trailing newlines, not one, which matters for the several
    places the twin compares a captured value against the empty string.

    A MISSING BINARY IS 127 WITH BASH'S OWN SENTENCE. Every caller here is
    already `|| something`, so this only decides which arm runs; getting the
    number right keeps `retry_with_backoff`'s reporting honest.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=stderr, check=False)
    except FileNotFoundError:
        sys.stderr.write("%s: command not found\n" % argv[0])
        sys.stderr.flush()
        return 127, ""
    return proc.returncode, proc.stdout.decode("utf-8", "replace").rstrip("\n")


def capture(argv: list[str]) -> tuple[int, str]:
    """`$(cmd)` -- stderr is INHERITED, so the child's diagnostics are visible."""
    return _capture(argv, stderr=None)


def capture_quiet(argv: list[str]) -> tuple[int, str]:
    """`$(cmd 2>/dev/null)` -- the shape almost every `gh api` here uses."""
    with open(os.devnull, "wb") as null:
        return _capture(argv, stderr=null.fileno())


def capture_merged(argv: list[str]) -> tuple[int, str]:
    """`$(cmd 2>&1)` -- Phase 3's `api_output`, which is logged on failure."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    except FileNotFoundError:
        return 127, "%s: command not found" % argv[0]
    return proc.returncode, proc.stdout.decode("utf-8", "replace").rstrip("\n")


def run_silent(argv: list[str]) -> int:
    """`cmd >/dev/null 2>&1` -- status only, both streams discarded."""
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "wb") as null:
        try:
            return subprocess.run(argv, stdout=null, stderr=null, check=False).returncode
        except FileNotFoundError:
            return 127


def run_quiet_err(argv: list[str]) -> int:
    """`cmd 2>/dev/null` -- status only; stdout is INHERITED, stderr discarded.

    This is what `retry_with_backoff 3 2 gh api -X DELETE ... 2>/dev/null` runs,
    and the inherited stdout is not an accident: `gh api -X DELETE` prints its
    response body there, and the twin lets it through.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "wb") as null:
        try:
            return subprocess.run(argv, stderr=null, check=False).returncode
        except FileNotFoundError:
            return 127


def run_plain(argv: list[str]) -> int:
    """`cmd` with both streams inherited. Phase 1's `gh release delete`."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, check=False).returncode
    except FileNotFoundError:
        sys.stderr.write("%s: command not found\n" % argv[0])
        sys.stderr.flush()
        return 127


def retry_with_backoff(attempts: int, delay: int, argv: list[str], *, quiet: bool) -> bool:
    """`retry_with_backoff <max_attempts> <initial_delay> <command...>`.

    common.sh:218-240, transliterated. `quiet` is the CALL SITE's redirection,
    not an option of the bash function: four of the five call sites write

        retry_with_backoff 3 2 gh api -X DELETE "..." 2>/dev/null

    and that `2>/dev/null` covers the WHOLE function invocation, so it discards
    the command's stderr AND the `Attempt 1/3 failed...` lines the retry logic
    itself prints. Phase 1's call has no redirection, so its retries are visible.
    Getting this wrong would add or remove three log lines per failing delete.

    THE `sleep` IS THE `sleep` BINARY, resolved through PATH, for the reason the
    module docstring gives: one stub answers for both sides, so the differential
    does not pay six real seconds per failing retry.

    THE DELAYS ARE INTEGERS AND PRINT AS SUCH. bash's `delay=$((delay * 2))`
    gives `2s` then `4s`; a float would print `2.0s` and diverge on text alone.
    """
    runner = run_quiet_err if quiet else run_plain
    attempt = 1
    while attempt <= attempts:
        if runner(argv) == 0:
            return True
        if attempt < attempts:
            if not quiet:
                log.warn("Attempt %d/%d failed, retrying in %ds..." % (attempt, attempts, delay))
            run_silent(["sleep", str(delay)])
            delay = delay * 2
        attempt += 1
    if not quiet:
        log.error("Command failed after %d attempts" % attempts)
    return False


def date_epoch(spec: str) -> str:
    """`date -d "<spec>" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" ... || echo 0`.

    The three-arm chain `should_retain` uses, EXECUTED, returning the raw text
    the twin's variable would hold. On GNU the first arm answers; on BSD it fails
    and the second does; if both fail the twin's `echo 0` yields the literal
    `0`, which is the sentinel the caller tests for.
    """
    code, out = capture_quiet(["date", "-d", spec, "+%s"])
    if code == 0:
        return out
    code, out = capture_quiet(["date", "-jf", "%Y-%m-%dT%H:%M:%SZ", spec, "+%s"])
    if code == 0:
        return out
    return "0"


def date_epoch_utc(spec: str) -> str:
    """`date -u -d "<spec>" +%s 2>/dev/null || echo 0`.

    The two-arm form used in Phases 7b, 8a, 8b, 8d, 8f and 8e. No BSD fallback
    in the twin at these sites, so there is none here.
    """
    code, out = capture_quiet(["date", "-u", "-d", spec, "+%s"])
    return out if code == 0 else "0"


def now_epoch_utc() -> str:
    """`date -u +%s`. EXECUTED, so a faked `date` on PATH moves both sides."""
    return capture_quiet(["date", "-u", "+%s"])[1]


def now_epoch_local() -> str:
    """`date +%s` -- Phase 9's, which is the one site without `-u`.

    Identical output to the `-u` form (epoch seconds do not have a zone); kept
    separate because the argv is what the call log compares.
    """
    return capture_quiet(["date", "+%s"])[1]


# =============================================================================
# JQ FILTERS
#
# Every function here is one filter the twin applies to a SHELL VARIABLE. The filters the twin passes to `gh api --jq` are NOT here: those run inside gh, on both sides, because the port issues the same argv.
#
# `test_jq_filters_agree_with_the_real_jq` drives each of these against the real binary over a corpus that includes the empty stream, a missing key and a null, so the docstrings below are checked rather than believed.
# =============================================================================


class _Nothing:
    """jq's empty stream, which is not the same value as `null`."""

    def __repr__(self) -> str:  # pragma: no cover -- diagnostics only
        return "<jq empty>"


NOTHING = _Nothing()


def _jq_or_die(blob: str, filter_text: str) -> None:
    """Reproduce jq's own death on input it cannot parse, then exit as bash would.

    Reached only when `json_values` has already failed, i.e. exactly when the
    twin's `total="$(echo "$blob" | jq 'length')"` would have failed too. Under
    `set -e` that assignment ends the run with jq's status (5 for a parse error)
    and jq's message already on stderr, so the honest reproduction is to let the
    real jq say it.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(
            ["jq", filter_text],
            input=(blob + "\n").encode("utf-8"),
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write("jq: command not found\n")
        raise SystemExit(127) from None
    # A jq that somehow SUCCEEDED here would mean this port's parser is stricter than jq's, which is a defect in the port and must not be silently green.
    raise SystemExit(proc.returncode if proc.returncode != 0 else 5)


def json_values(blob: str, filter_text: str = "length") -> list:
    """The stream of JSON values `echo "$blob" | jq ...` would read.

    A STREAM, not a value: `gh api --paginate --jq '[...]'` emits ONE ARRAY PER
    PAGE with nothing between them, and the twin slurps that with `jq -s`. A
    parser that accepted only a single document would silently see page 1 and
    drop the rest, which is the exact shape of bug this whole port exists to not
    introduce.

    Whitespace-only input is the EMPTY stream and exits 0 with no output, which
    is why `total` can legitimately end up as the empty string.
    """
    decoder = json.JSONDecoder()
    out: list = []
    index = 0
    text = blob
    while True:
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index >= len(text):
            return out
        try:
            value, index = decoder.raw_decode(text, index)
        except ValueError:
            _jq_or_die(blob, filter_text)
        out.append(value)


def length_text(blob: str, filter_text: str = "length") -> str:
    """`jq 'length'` -- one line per value in the stream, so "" for none.

    Only ever applied to arrays here, so the array case is the only one
    implemented; a string or object would answer differently in jq and cannot
    reach these call sites (each blob is either `[]`, a `[...]` from a filter,
    or empty).
    """
    return "\n".join(
        str(len(v)) if isinstance(v, (list, dict, str)) else "1"
        for v in json_values(blob, filter_text)
    )


def blob_array(blob: str, filter_text: str = "length") -> list:
    """The single array a blob holds, or `[]` when the stream is empty.

    Mirrors `while IFS= read -r x; do ...; done < <(echo "$blob" | jq -c '.[]')`:
    an empty stream feeds the loop nothing.
    """
    values = json_values(blob, filter_text)
    if not values:
        return []
    return values[0] if isinstance(values[0], list) else []


def jq_text(value: object) -> str:
    """How `jq -r` renders one value.

    `null` and a MISSING KEY both render as the four characters `null`, and that
    is load-bearing: `tag_name="$(echo "$entry" | jq -r '.name')"` on an object
    without `.name` yields the string "null", which the twin then puts in a URL.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, separators=(",", ":"))


def _ord(value: object) -> tuple:
    """A sort key implementing jq's TOTAL ORDER over JSON values.

    `null < false < true < numbers < strings < arrays < objects`, arrays
    element-wise, objects by their SORTED KEY LIST first and then by the values
    in that order. Needed because half the values sorted here can be `null` (a
    deployment with no `created_at`, a Pages deployment with no branch), and
    Python refuses to compare `None` with `str` at all.
    """
    if value is None:
        return (0,)
    if value is False:
        return (1,)
    if value is True:
        return (2,)
    if isinstance(value, (int, float)):
        return (3, value)
    if isinstance(value, str):
        return (4, value)
    if isinstance(value, list):
        return (5, tuple(_ord(v) for v in value))
    keys = sorted(value)
    return (6, tuple(keys), tuple(_ord(value[k]) for k in keys))


def jq_sort_by(items: list, key) -> list:
    """`sort_by(f)`: jq's value order on the key, STABLE on ties.

    THE TIE-BREAK WAS MEASURED, NOT ASSUMED, and the first version of this
    function got it wrong. jq's `sort_by` is a stable merge sort over the key
    alone, so two tags cut in the same second keep their input order -- it does
    NOT fall back to comparing the whole element, which is what a reading of
    `_sort_by_impl(map([f]))` suggests. `test_jq_filters_agree_with_the_real_jq`
    carries a tie case in its corpus for exactly this reason, and it went red.

    That matters downstream: `sort_by(.date) | reverse` therefore REVERSES the
    input order of tied items, so the two tags are deleted in the opposite order
    from the one they arrived in, and the call log records it.
    """
    return sorted(items, key=lambda item: _ord(key(item)))


def jq_group_by(items: list, key) -> list:
    """`group_by(f)`: `sort_by(f)` then one group per run of equal keys."""
    groups: list[list] = []
    last = NOTHING
    for item in jq_sort_by(items, key):
        current = _ord(key(item))
        if not groups or current != last:
            groups.append([item])
            last = current
        else:
            groups[-1].append(item)
    return groups


def jq_unique(items: list) -> list:
    """`unique`: sorted, duplicates removed. jq sorts first, so the output is
    in jq order and not in input order."""
    out: list = []
    for item in sorted(items, key=_ord):
        if not out or _ord(out[-1]) != _ord(item):
            out.append(item)
    return out


def jq_flatten(items: list) -> list:
    """`flatten` with no argument: RECURSIVE, to any depth. Objects are not
    touched, only arrays."""
    out: list = []
    for item in items:
        if isinstance(item, list):
            out.extend(jq_flatten(item))
        else:
            out.append(item)
    return out


def jq_add(values: list) -> object:
    """`add` over a stream that has been slurped: array concatenation here.

    `add` on an EMPTY array is `null`, and the twin's Phase 3 would then feed
    null to `sort_by` and die -- unreachable, because the only path to that line
    guarantees at least one page. Preserved as `None` rather than `[]` so the
    unreachable case stays visibly unreachable.
    """
    if not values:
        return None
    out: list = []
    for value in values:
        out.extend(value)
    return out


def jq_get(value: object, *path: str) -> object:
    """`.a.b.c` -- a missing key, or a lookup into a non-object, is `null`.

    jq raises a TYPE ERROR for a lookup into a STRING or a NUMBER, and returns
    null only for a lookup into null or an object. That distinction is
    unreachable from every call site here (the twin only ever indexes into
    objects it built or the API returned) and is collapsed to null, which is the
    conservative direction: it cannot turn a crash into a deletion.
    """
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# =============================================================================
# SMALL SHELL SHAPES
#
# The one-liners the twin spells with `grep`, `awk`, `sed`, `sort` or a bash parameter expansion. Each carries the exact text it stands for.
# =============================================================================

# `[[ "$env" =~ ^pr-([0-9]+)$ ]]` (Phase 4) and the identical test in Phase 5b.
_PR_ENV_RE = re.compile(r"^pr-([0-9]+)$")

# `select(.name | test("^pr-[0-9]+$"))` (Phase 6). jq's `test` is a SEARCH with whatever anchors the pattern carries, which is why this is `.search` and not
# `.match`; the anchors are in the pattern.
_PR_NAME_RE = re.compile(r"^pr-[0-9]+$")

# `select(.name | test("^account-db-pr-[0-9]+$"))` (Phase 7).
_D1_NAME_RE = re.compile(r"^account-db-pr-[0-9]+$")

# `select(.name | test("^rediacc-console-pr-[0-9]+$"))` (Phase 7b).
_TURNSTILE_NAME_RE = re.compile(r"^rediacc-console-pr-[0-9]+$")

# `grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$'` (Phase 8d) and the `=~` beside it.
_STRICT_SEMVER_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# `[[ "$open_prs" =~ ^[0-9]+$ ]]` (Phase 9).
_DIGITS_RE = re.compile(r"^[0-9]+$")

# A word `arith` will read as a plain decimal, used to keep a `null` size out of the arithmetic in Phase 12. See `arith` for why a bare identifier is not one.
_INT_RE = re.compile(r"^[+-]?[0-9]+$")

# The three awk line filters in Phase 8. `[[:space:]]` and the literal `PRE` are
# the twin's; `aws s3 ls` prints `                           PRE <name>/`.
_PRE_DRYRUN_RE = re.compile(r"^[ \t]*PRE[ \t]dryrun-")
_PRE_PR_RE = re.compile(r"^[ \t]*PRE[ \t]pr-[0-9]+/")
_PRE_VERSION_RE = re.compile(r"^[ \t]*PRE[ \t]v[0-9]+\.")

# `if (fname !~ /^rediacc-cli[-_]/)` and the semver match in the 8f awk program.
_CLI_ARTIFACT_RE = re.compile(r"^rediacc-cli[-_]")
_LEADING_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+")


class ExpansionAbortError(Exception):
    """bash's unwind on an arithmetic EXPANSION error, which is not an exit.

    Measured, not assumed. With `BRANCH_MAX_AGE_DAYS=08`:

        $ bash -c 'set -euo pipefail; B=08
                   f(){ echo before; local m=$((B * 86400)); echo after; }
                   g(){ echo g; f; echo "g after f"; }
                   g || echo "g failed"; echo alive'
        g
        before
        <file>: line N: 08: value too great for base (error token is "08")
        alive

    Note what is MISSING: `after`, `g after f`, and `g failed`. bash abandoned
    both function frames and did NOT run the `||` arm, but it did not exit
    either -- it resumed at the next TOP-LEVEL command, which is why `alive`
    printed and that script ended 0.

    THE EXIT STATUS DEPENDS ON WHAT FOLLOWS, and for this script nothing does:
    `run_all_phases` is the last top-level command, so the shell ends carrying
    the failed expansion's own status, 1. Measured both ways (probe with and
    without a trailing `echo`).

    Applied to the real thing, `BRANCH_MAX_AGE_DAYS=08` means Phase 9 stops
    where it stands, Phases 10, 11 and 12 and the whole final summary never run,
    and the only evidence is one line of bash arithmetic diagnostics. That is
    HAZARD 8. HAZARD 9 reaches the same unwind from an ordinary API failure; see
    `cleanup_actions_cache`.
    """


def bash_div(numerator: int, denominator: int) -> int:
    """`$((a / b))`: C division, TRUNCATED TOWARD ZERO, not floored.

    Only visible on a negative numerator, which happens when a timestamp is in
    the future -- an API clock skew, or the `created_on` of a widget made in the
    same second. Python's `//` floors, so `-1 // 3600` is -1 where bash says 0.
    """
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def _blank() -> None:
    """`echo ""` -- an empty line on STDOUT, between phases."""
    print()
    sys.stdout.flush()


def _grep_qx(needle: str, haystack: str) -> bool:
    """`grep -qx "$needle" <<<"$haystack"`: a WHOLE-LINE match.

    `-x` anchors both ends, and the needle is still a BASIC REGULAR EXPRESSION,
    not a literal (that would be `-F`). Every needle here is a PR number matched
    against a list of PR numbers, so the distinction cannot bite; it is
    reproduced with an anchored search anyway because a port that quietly became
    stricter than its twin is still a divergence.
    """
    return any(line == needle for line in records(haystack))


def _stream_lines(text: str) -> list[str]:
    """The lines a `while read` over a PROCESS SUBSTITUTION sees.

    Different from `records`: a stream has no phantom final record, because
    there is no here-string appending a newline. An empty stream is zero
    iterations, and a final line without a trailing newline is still one.
    """
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _capture_raw(argv: list[str]) -> tuple[int, str]:
    """stdout EXACTLY as written, newlines and all, stderr discarded.

    For the two places the twin feeds a command's output to a `while read` loop
    through a process substitution instead of capturing it in `$( )`.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "wb") as null:
        try:
            proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=null, check=False)
        except FileNotFoundError:
            return 127, ""
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _capture_stderr(argv: list[str]) -> tuple[int, str]:
    """`$(cmd 2>&1 >/dev/null)`: STDERR captured, stdout binned.

    The order of the two redirections is the whole trick, and Phase 9 is the one
    place in this file that uses it: `2>&1` first points stderr at the pipe the
    substitution is reading, and `>/dev/null` then moves stdout away.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "wb") as null:
        try:
            proc = subprocess.run(argv, stdout=null, stderr=subprocess.PIPE, check=False)
        except FileNotFoundError:
            return 127, "%s: command not found" % argv[0]
    return proc.returncode, proc.stderr.decode("utf-8", "replace").rstrip("\n")


def _pipe_grep(argv: list[str], pattern) -> tuple[int, str]:
    """`$(cmd 2>/dev/null | grep -E '<pattern>' || true)`.

    The `|| true` is what keeps grep's exit-1-on-no-match from tripping
    `pipefail`, and it is also what hides a failure of `cmd`. Both are the
    twin's, so both are here.
    """
    code, out = capture_quiet(argv)
    kept = [line for line in _stream_lines(out + "\n") if pattern.search(line)]
    return code, "\n".join(kept)


def _sort_v_first(left: str, right: str) -> str:
    """`printf '%s\\n%s\\n' "$a" "$b" | sort -V | head -1`.

    `sort -V` IS EXECUTED. GNU version sort has its own rules for suffixes and
    leading zeros, and the two inputs here are a floor and a version that a
    human may have written by hand into `release-contract-floor.txt`.
    """
    sys.stdout.flush()
    try:
        proc = subprocess.run(
            ["sort", "-V"],
            input=("%s\n%s\n" % (left, right)).encode("utf-8"),
            stdout=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return left
    lines = _stream_lines(proc.stdout.decode("utf-8", "replace"))
    return lines[0] if lines else ""


def _awk_pre_field(line: str, pattern) -> str:
    """`awk '/<pattern>/ {print $2}'` over ONE line.

    awk's default field splitting is on runs of whitespace with leading
    whitespace ignored, so `                           PRE dryrun-x/` has $1
    `PRE` and $2 `dryrun-x/`. A matching line with fewer than two fields prints
    an empty line, which the caller's `[[ -z ]]` then skips.
    """
    if not pattern.search(line):
        return ""
    fields = line.split()
    return fields[1] if len(fields) > 1 else ""


def _awk_channel_listing(raw: str) -> str:
    """The 8f awk program, which turns `aws s3 ls --recursive` into `ts|semver|is_dev|key`.

        n = split($4, p, "/"); fname = p[n];
        if (fname !~ /^rediacc-cli[-_]/) next
        rest = fname; sub(/^rediacc-cli[-_]/, "", rest);
        if (match(rest, /^[0-9]+\\.[0-9]+\\.[0-9]+/)) { ... }

    `$4` IS THE FOURTH WHITESPACE FIELD, so a key containing a space is
    TRUNCATED at the space and the tail is lost. Reproduced rather than fixed:
    no release artifact has ever had a space in its name, and a port that
    handled one would delete a key the twin would not.
    """
    out = []
    for line in _stream_lines(raw):
        fields = line.split()
        key = fields[3] if len(fields) > 3 else ""
        fname = key.split("/")[-1] if key != "" else ""
        if not _CLI_ARTIFACT_RE.match(fname):
            continue
        rest = _CLI_ARTIFACT_RE.sub("", fname, count=1)
        match = _LEADING_SEMVER_RE.match(rest)
        if not match:
            continue
        semver = match.group(0)
        after = rest[len(semver) :]
        is_dev = 1 if (semver == "0.0.0" and after.startswith("-dev")) else 0
        stamp = "%sT%sZ" % (fields[0], fields[1] if len(fields) > 1 else "")
        out.append("%s|%s|%d|%s" % (stamp, semver, is_dev, key))
    return "\n".join(out)


def _top_versions(listing: str, keep: int) -> str:
    """`awk -F'|' '$3 == 0 {print $2}' | sort -u -V -r | head -n <keep>`.

    `$3 == 0` is a NUMERIC comparison in awk, so the field's `0`/`1` text is
    converted. `sort` is executed for the same reason as in `_sort_v_first`.
    """
    non_dev = []
    for line in _stream_lines(listing + "\n"):
        fields = line.split("|")
        if len(fields) > 2 and fields[2].strip() in ("0", "0.0", "+0", "-0"):
            non_dev.append(fields[1])
    if not non_dev:
        return ""
    sys.stdout.flush()
    try:
        proc = subprocess.run(
            ["sort", "-u", "-V", "-r"],
            input=("\n".join(non_dev) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return "\n".join(_stream_lines(proc.stdout.decode("utf-8", "replace"))[:keep])


def _success_text(blob: str) -> str:
    """`jq -r '.success // false'`.

    `//` is jq's ALTERNATIVE operator, which fires on `false` as well as on
    `null`, so a response with `"success": false` and one with no `success` key
    at all both answer `false`. The caller compares against the literal `true`.
    """
    out = []
    for value in json_values(blob, ".success // false"):
        current = jq_get(value, "success") if isinstance(value, dict) else None
        out.append("false" if current is None or current is False else jq_text(current))
    return "\n".join(out)


def _iterate_result(blob: str) -> list:
    """`.result[]` -- a jq TYPE ERROR when `.result` is not an array.

    That error is fatal in the twin (it is inside a command substitution under
    errexit), so it is fatal here too, through the real jq. The alternative --
    quietly yielding nothing -- would turn a run-ending misconfiguration into a
    silent no-op, which is the failure mode this whole file is a monument to.
    """
    out: list = []
    for value in json_values(blob, ".result[]"):
        current = jq_get(value, "result") if isinstance(value, dict) else None
        if not isinstance(current, list):
            _jq_or_die(blob, "[.result[]]")
        out.extend(current)
    return out


def _iterate_result_optional(blob: str) -> list:
    """`.result[]?` -- the `?` swallows the type error and yields nothing."""
    out: list = []
    for value in json_values(blob, ".result[]?"):
        current = jq_get(value, "result") if isinstance(value, dict) else None
        if isinstance(current, list):
            out.extend(current)
    return out


def _soft_length_text(blob: str) -> str:
    """`jq 'length'` inside the twin's `set +e` region: a failure is an EMPTY
    string, not a dead run.

    `aws --query 'Uploads[]...'` renders `null` when there are no uploads, and
    `null | length` is a jq error. The twin's `mpu_count` is then empty, and
    `[[ "" -eq 0 ]]` is true, so the phase reports "no ongoing multipart
    uploads". Getting this wrong in either direction changes what an empty
    bucket prints.
    """
    values = try_json_values(blob)
    if values is None:
        return ""
    out = []
    for value in values:
        if isinstance(value, (list, dict, str)):
            out.append(str(len(value)))
        else:
            return ""
    return "\n".join(out)


def _upload_rows(blob: str) -> str:
    """`jq -r '.[] | "\\(.Key)\\t\\(.UploadId)\\t\\(.Initiated)"' 2>/dev/null`.

    String interpolation renders each value the way `jq -r` would, so a missing
    key becomes the four characters `null` and lands in the loop's variable as
    such. Errors are discarded (`2>/dev/null`) and produce no rows.
    """
    values = try_json_values(blob)
    if values is None:
        return ""
    rows = []
    for value in values:
        if not isinstance(value, list):
            return ""
        rows.extend(
            "%s\t%s\t%s"
            % (
                jq_text(jq_get(item, "Key")),
                jq_text(jq_get(item, "UploadId")),
                jq_text(jq_get(item, "Initiated")),
            )
            for item in value
        )
    return "".join(row + "\n" for row in rows)


def _sum_sizes(entries: list) -> int:
    """`jq '[.[].size] | add // 0'` over ONE array.

    `add` over an empty array is `null`, which `// 0` turns into 0. `add` also
    treats `null` as the identity, so an entry with no `size` contributes
    nothing rather than making the whole sum null.
    """
    total = 0
    for entry in entries:
        size = jq_get(entry, "size")
        if isinstance(size, bool) or size is None:
            continue
        if isinstance(size, (int, float)):
            total += int(size)
    return total


def _arith_expand(word: object) -> int:
    """`$((word))` -- a refused word ABORTS, it does not evaluate to false.

    The difference from `arith_cmp` is the whole of HAZARD 8: inside `[[ ]]` bash
    prints and continues, inside `$(( ))` it prints and unwinds every enclosing
    function.
    """
    try:
        return arith(word)
    except BashArithError as exc:
        _arith_report(exc.token, context="")
        raise ExpansionAbortError from None


def records(text: str) -> list[str]:
    """The lines a `while IFS= read -r x; do ...; done <<<"$text"` loop sees.

    A here-string always appends a newline, so an EMPTY string yields exactly
    one empty record -- which is why every such loop in the twin opens with
    `[[ -z "$x" ]] && continue`. Reproduced, rather than returning `[]`, because
    two of those loops count the records they skip.
    """
    return text.split("\n")


def try_json_values(blob: str) -> list | None:
    """`json_values` that ANSWERS instead of dying. `None` means "not JSON".

    Phase 3's `jq -e 'type == "array"'` sits inside an `if !` with both streams
    discarded, so malformed bytes there are a soft "page not usable" rather than
    the run-ending parse error every other blob would cause.
    """
    decoder = json.JSONDecoder()
    out: list = []
    index = 0
    while True:
        while index < len(blob) and blob[index] in " \t\r\n":
            index += 1
        if index >= len(blob):
            return out
        try:
            value, index = decoder.raw_decode(blob, index)
        except ValueError:
            return None
        out.append(value)


class Housekeeping:
    """The twin's SOURCE-TIME state: parsed args, config, guards, counters.

    Constructing one is `source cleanup-versions.sh <args>`; calling a method is
    calling the function of that name. See the module docstring for why the seam
    is shaped this way.
    """

    def __init__(self, argv: list[str]) -> None:
        # `parse_args "$@"` (:19). Refusals propagate: the twin exits 2 from parse_args on a flag that is not a shell identifier, and `main` turns the exception back into that exit code.
        args = common.parse_args(argv)

        # :21-23. `${ARG_X:-default}` -- EMPTY falls back too, which is why this
        # is `or` and not `args.get(k, default)`.
        self.retention_days = args.get("ARG_DAYS") or DEFAULT_RETENTION_DAYS
        self.keep_versions = args.get("ARG_VERSIONS") or DEFAULT_KEEP_VERSIONS
        self.dry_run_text = args.get("ARG_DRY_RUN") or "false"

        # :58, :49, :124. Read HERE because the twin reads them here, at source time: a caller that exports one of these after sourcing gets the old value in bash, and must get the old value here too.
        self.r2_bucket = os.environ.get("RELEASES_BUCKET") or DEFAULT_R2_BUCKET
        self.branch_max_age_days = (
            os.environ.get("BRANCH_MAX_AGE_DAYS") or DEFAULT_BRANCH_MAX_AGE_DAYS
        )
        self.max_deletes = os.environ.get("MAX_DELETES_PER_RUN") or DEFAULT_MAX_DELETES_PER_RUN

        # :130-134, IN THE TWIN'S ORDER, which is observable: a host with no `aws` and no GH_TOKEN is told about aws, not about the token.
        common.require_cmd("gh")
        common.require_cmd("jq")
        common.require_cmd("curl")
        common.require_cmd("aws")
        common.require_var("GH_TOKEN")

        # :142 and :147.
        self.deletes_this_run = 0
        self.housekeeping_failed = 0

    # -- shared helpers -----------------------------------------------------

    @property
    def dry_run(self) -> bool:
        """`[[ "$DRY_RUN" == "true" ]]` -- the string, compared exactly."""
        return self.dry_run_text == "true"

    def deletes_budget_ok(self) -> bool:
        """`[[ $DELETES_THIS_RUN -lt $MAX_DELETES_PER_RUN ]]` (:151-153).

        THE RIGHT-HAND SIDE IS AN OPERATOR-SUPPLIED STRING and is read with
        bash's arithmetic rules, so `MAX_DELETES_PER_RUN=0100` is SIXTY-FOUR and
        `MAX_DELETES_PER_RUN=08` is a diagnostic plus a permanently false
        budget -- i.e. every phase reports its backlog deferred and nothing is
        ever deleted again. Both are the twin's behaviour; see `arith`.
        """
        return arith_cmp(self.deletes_this_run, "lt", self.max_deletes)

    def record_delete(self) -> None:
        """`DELETES_THIS_RUN=$((DELETES_THIS_RUN + 1))` (:157-159)."""
        self.deletes_this_run += 1

    def housekeeping_fail(self, title: str, message: str) -> None:
        """The run-spanning failure latch (:179-189). ALWAYS RETURNS NONE.

        The annotation goes to STDOUT (`echo`), while `log_error` goes to
        stderr, and the two streams are never merged by this port for the reason
        `differential.py` gives at length: a stream swap is exactly the defect
        this whole comparison exists to catch.
        """
        self.housekeeping_failed = 1
        log.error(message)
        if os.environ.get("GITHUB_ACTIONS", ""):
            print("::error title=%s::%s" % (title, message))
            sys.stdout.flush()

    def cf_api(self, method: str, endpoint: str, *extra: str) -> tuple[int, str]:
        """`cf_api <method> <endpoint> [curl args...]` (:193-201).

        The argv is the twin's, in the twin's order, including the two headers
        it always sends. Every call site wraps this in `$( ... 2>/dev/null || echo
        '{"success":false}')`, so the status is returned rather than acted on
        here.

        `$CLOUDFLARE_API_TOKEN` IS UNGUARDED IN THE TWIN -- under `set -u` an
        unset token would abort the whole run inside this function. Every caller
        checks it first, so the path is unreachable; the port reads it with a
        `""` default rather than reproducing an abort nothing can trigger.
        """
        return capture_quiet(
            [
                "curl",
                "-s",
                "-X",
                method,
                "https://api.cloudflare.com/client/v4%s" % endpoint,
                "-H",
                "Authorization: Bearer %s" % os.environ.get("CLOUDFLARE_API_TOKEN", ""),
                "-H",
                "Content-Type: application/json",
                *extra,
            ]
        )

    def _cutoff_epoch(self) -> str:
        """`date -d "$RETENTION_DAYS days ago" +%s || date -v-${D}d +%s`, both quiet.

        THERE IS NO `|| echo 0` ON THIS ONE, unlike the created_at parse two
        lines above it, so when BOTH arms fail the twin's variable holds the
        EMPTY STRING and the assignment's non-zero status is swallowed -- errexit
        is suspended for the whole call because `should_retain` is always invoked
        as an `if` condition. Verified against the real bash rather than assumed;
        the empty string then reads as 0 in the `-gt` below, so an unparseable
        `--days` value RETAINS EVERYTHING (every real epoch is greater than 0)
        rather than deleting it. That is the safe direction, and it is luck
        rather than design, so it is stated here.

        `date -v-${RETENTION_DAYS}d` IS UNQUOTED in the twin, so a value with
        whitespace becomes several arguments. Reproduced with a whitespace split.
        """
        code, out = capture_quiet(["date", "-d", "%s days ago" % self.retention_days, "+%s"])
        if code == 0:
            return out
        code, out = capture_quiet(["date", *("-v-%sd" % self.retention_days).split(), "+%s"])
        if code == 0:
            return out
        return ""

    def should_retain(self, created_at: str, index: int) -> bool:
        """`should_retain <created_at_iso> <index_from_newest>` (:206-233).

        True = keep. The two conditions are OR: inside the newest
        `KEEP_VERSIONS`, or inside the retention window. An UNDATABLE item is
        kept and says so.
        """
        if arith_cmp(index, "lt", self.keep_versions):
            return True
        created_epoch = date_epoch(created_at)
        cutoff_epoch = self._cutoff_epoch()
        if arith_cmp(created_epoch, "eq", 0):
            log.warn("Could not parse date '%s' - retaining item" % created_at)
            return True
        return arith_cmp(created_epoch, "gt", cutoff_epoch)

    # -- PHASE 1: GITHUB RELEASES ------------------------------------------

    def cleanup_releases(self) -> None:
        """`cleanup_releases` (:239-292).

        HAZARD 2 LIVES HERE: the dry-run arm does NOT increment `deleted`, so a
        dry run of this phase always ends `would delete 0 of N` no matter how
        many releases it named. Every other phase's dry-run arm counts.
        """
        log.step("Phase 1: Cleaning up GitHub releases (%s)" % RELEASE_REPO)

        code, releases = capture_quiet(
            [
                "gh",
                "release",
                "list",
                "--repo",
                RELEASE_REPO,
                "--limit",
                "200",
                "--json",
                "tagName,createdAt,isDraft,isPrerelease",
                "--jq",
                "sort_by(.createdAt) | reverse",
            ]
        )
        if code != 0:
            releases = "[]"

        total = length_text(releases)
        log.debug("Found %s releases" % total)

        deleted = 0

        # `index` is the twin's `index=$((index + 1))` at the tail of the loop.
        # It is `enumerate` here and not a counter because the only other exit is `break`, which the twin also takes before incrementing. Phase 5 keeps a hand-rolled counter: it increments in two places and is not this shape.
        for index, release in enumerate(blob_array(releases)):
            tag = jq_text(jq_get(release, "tagName"))
            created_at = jq_text(jq_get(release, "createdAt"))

            if self.should_retain(created_at, index):
                log.debug("Keeping release: %s (index=%d)" % (tag, index))
            else:
                if not self.deletes_budget_ok():
                    log.warn(
                        "Phase 1: hit MAX_DELETES_PER_RUN=%s; remaining releases "
                        "deferred to next run" % self.max_deletes
                    )
                    break
                if self.dry_run:
                    log.warn("[DRY-RUN] Would delete release: %s (created: %s)" % (tag, created_at))
                elif retry_with_backoff(
                    3,
                    2,
                    ["gh", "release", "delete", tag, "--repo", RELEASE_REPO, "--yes"],
                    quiet=False,
                ):
                    log.debug("Deleted release: %s" % tag)
                    deleted += 1
                    self.record_delete()
                    # Best-effort tag cleanup (may already be gone).
                    run_quiet_err(
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            "repos/%s/git/refs/tags/%s" % (RELEASE_REPO, tag),
                        ]
                    )
                else:
                    log.warn("Failed to delete release: %s" % tag)

        if self.dry_run:
            log.info("Releases: would delete %d of %s" % (deleted, total))
        else:
            log.info("Releases: deleted %d of %s" % (deleted, total))

    # -- PHASE 2: GIT TAGS --------------------------------------------------

    def cleanup_tags(self) -> None:
        """`cleanup_tags` (:298-392). Two repos, up to four API calls per tag.

        THE COST IS THE POINT OF THE CALL LOG. Dating one tag takes one call for
        the ref, one for the tag object when it is annotated, one more for the
        tag object's target, and one for the commit -- and the twin issues them
        for EVERY tag, including the ones it is about to keep. A port that
        memoised would be faster and would no longer be the same program.
        """
        log.step("Phase 2: Cleaning up git tags")

        for repo in TAG_REPOS:
            full_repo = "%s/%s" % (GITHUB_ORG, repo)
            log.step("  Processing tags for %s" % full_repo)

            code, tags = capture_quiet(
                ["gh", "api", "repos/%s/tags" % full_repo, "--paginate", "--jq", ".[].name"]
            )
            if code != 0:
                tags = ""

            if tags == "":
                log.debug("  No tags found for %s" % full_repo)
                continue

            tag_data: list = []
            for tag_name in records(tags):
                if tag_name == "":
                    continue

                code, ref_data = capture_quiet(
                    ["gh", "api", "repos/%s/git/ref/tags/%s" % (full_repo, tag_name)]
                )
                if code != 0:
                    ref_data = ""
                if ref_data == "":
                    continue

                ref_values = json_values(ref_data, ".object.type")
                ref = ref_values[0] if ref_values else None
                obj_type = jq_text(jq_get(ref, "object", "type"))
                obj_sha = jq_text(jq_get(ref, "object", "sha"))

                tag_date = ""
                if obj_type == "tag":
                    code, tag_date = capture_quiet(
                        [
                            "gh",
                            "api",
                            "repos/%s/git/tags/%s" % (full_repo, obj_sha),
                            "--jq",
                            ".tagger.date",
                        ]
                    )
                    if code != 0:
                        tag_date = ""

                if tag_date == "":
                    commit_sha = obj_sha
                    if obj_type == "tag":
                        code, out = capture_quiet(
                            [
                                "gh",
                                "api",
                                "repos/%s/git/tags/%s" % (full_repo, obj_sha),
                                "--jq",
                                ".object.sha",
                            ]
                        )
                        commit_sha = out if code == 0 else obj_sha
                    code, tag_date = capture_quiet(
                        [
                            "gh",
                            "api",
                            "repos/%s/git/commits/%s" % (full_repo, commit_sha),
                            "--jq",
                            ".committer.date",
                        ]
                    )
                    if code != 0:
                        tag_date = ""

                if tag_date != "":
                    tag_data.append({"name": tag_name, "date": tag_date})

            # `sort_by(.date) | reverse`.
            tag_data = list(reversed(jq_sort_by(tag_data, lambda e: e.get("date"))))
            total = len(tag_data)

            deleted = 0

            for index, entry in enumerate(tag_data):
                tag_name = jq_text(entry.get("name"))
                tag_date = jq_text(entry.get("date"))

                if self.should_retain(tag_date, index):
                    log.debug("  Keeping tag: %s" % tag_name)
                else:
                    if not self.deletes_budget_ok():
                        log.warn(
                            "  Phase 2: hit MAX_DELETES_PER_RUN=%s; remaining tags "
                            "deferred to next run" % self.max_deletes
                        )
                        break
                    if self.dry_run:
                        log.warn("  [DRY-RUN] Would delete tag: %s (%s)" % (tag_name, tag_date))
                    elif retry_with_backoff(
                        3,
                        2,
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            "repos/%s/git/refs/tags/%s" % (full_repo, tag_name),
                        ],
                        quiet=True,
                    ):
                        log.debug("  Deleted tag: %s" % tag_name)
                        deleted += 1
                        self.record_delete()
                    else:
                        log.warn("  Failed to delete tag: %s" % tag_name)

            if self.dry_run:
                log.info("  Tags (%s): would delete %d of %d" % (full_repo, deleted, total))
            else:
                log.info("  Tags (%s): deleted %d of %d" % (full_repo, deleted, total))

    # -- PHASE 3: GHCR PACKAGE VERSIONS ------------------------------------

    def cleanup_packages(self) -> None:
        """`cleanup_packages` (:398-522).

        THE PAGINATION IS THE FIX FOR A REAL VACUOUS GREEN, in the twin's own
        comment: a single-page fetch only ever saw the newest 100 versions, all
        of them inside the retention window, so the phase deleted 0 every day
        while `elite/web` accumulated 8.7k versions behind page 1.
        """
        log.step("Phase 3: Cleaning up GHCR package versions")

        for package_name in GHCR_PACKAGES:
            # `sed 's|/|%2F|g'`.
            encoded_package = package_name.replace("/", "%2F")

            log.step("  Processing package: %s" % package_name)

            pages: list = []
            page = 1
            page_ok = True
            while True:
                code, raw_page = capture_quiet(
                    [
                        "gh",
                        "api",
                        "orgs/%s/packages/container/%s/versions?per_page=100&page=%d"
                        % (GITHUB_ORG, encoded_package, page),
                    ]
                )
                if code != 0:
                    raw_page = ""

                # `[[ -z ... ]] || ! jq -e 'type == "array"'` -- both streams of
                # the jq are discarded, so malformed bytes are a soft failure here and nowhere else in the file.
                parsed = try_json_values(raw_page) if raw_page != "" else None
                if parsed is None or len(parsed) != 1 or not isinstance(parsed[0], list):
                    page_ok = False
                    break

                trimmed = [
                    {
                        "id": jq_get(v, "id"),
                        "tags": jq_get(v, "metadata", "container", "tags"),
                        "created": jq_get(v, "created_at"),
                    }
                    for v in parsed[0]
                ]
                page_count = len(trimmed)
                pages.append(trimmed)

                if page_count < 100:
                    break
                if page >= PACKAGE_MAX_PAGES:
                    log.warn(
                        "  Pagination stopped at %d pages for %s; versions beyond that "
                        "are picked up on later runs as deletions shrink the list"
                        % (PACKAGE_MAX_PAGES, package_name)
                    )
                    break
                page += 1

            if not page_ok and page == 1:
                log.warn(
                    "  Skipping %s: package not accessible (app token may lack "
                    "org-level packages permission)" % package_name
                )
                continue
            if not page_ok:
                log.warn(
                    "  Page %d fetch failed for %s; proceeding with the %d page(s) "
                    "already fetched" % (page, package_name, page - 1)
                )

            # `jq -s 'add | sort_by(.created) | reverse'`.
            versions = list(reversed(jq_sort_by(jq_add(pages) or [], lambda v: v.get("created"))))
            total = len(versions)
            log.debug("  Found %d versions for %s" % (total, package_name))

            deleted = 0
            consecutive_failures = 0

            for index, version in enumerate(versions):
                version_id = jq_text(version.get("id"))
                created_at = jq_text(version.get("created"))
                # `.tags // [] | join(", ")`.
                raw_tags = version.get("tags")
                tag_list = raw_tags if isinstance(raw_tags, list) else []
                tags = ", ".join("" if t is None else jq_text(t) for t in tag_list)

                if self.should_retain(created_at, index):
                    log.debug("  Keeping version: %s (tags: %s)" % (version_id, tags))
                else:
                    if not self.deletes_budget_ok():
                        log.warn(
                            "  Phase 3: hit MAX_DELETES_PER_RUN=%s; remaining versions "
                            "deferred to next run" % self.max_deletes
                        )
                        break
                    if self.dry_run:
                        log.warn(
                            "  [DRY-RUN] Would delete version: %s (tags: %s, created: %s)"
                            % (version_id, tags, created_at)
                        )
                        deleted += 1
                    else:
                        api_exit, api_output = capture_merged(
                            [
                                "gh",
                                "api",
                                "-X",
                                "DELETE",
                                "orgs/%s/packages/container/%s/versions/%s"
                                % (GITHUB_ORG, encoded_package, version_id),
                            ]
                        )

                        if api_exit == 0:
                            log.debug("  Deleted version: %s (tags: %s)" % (version_id, tags))
                            deleted += 1
                            self.record_delete()
                            consecutive_failures = 0
                        else:
                            consecutive_failures += 1
                            log.warn(
                                "  Could not delete version %s (tags: %s): %s"
                                % (version_id, tags, api_output)
                            )
                            if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                                log.warn(
                                    "  Skipping remaining versions for %s after %d "
                                    "consecutive failures" % (package_name, consecutive_failures)
                                )
                                break

            if self.dry_run:
                log.info(
                    "  Package %s: would delete %d of %d versions" % (package_name, deleted, total)
                )
            else:
                log.info("  Package %s: deleted %d of %d versions" % (package_name, deleted, total))

    # -- PHASE 4: GITHUB DEPLOYMENTS ---------------------------------------

    def cleanup_deployments(self) -> None:
        """`cleanup_deployments` (:528-627).

        FAILS OPEN ON THE OPEN-PR LOOKUP, and the twin explains why: its worst
        case is retaining too much history, so an API blip must not wipe an open
        PR's preview record. Phase 5b, whose worst case is deleting a live
        preview, fails CLOSED instead. The asymmetry is deliberate on both sides.
        """
        log.step("Phase 4: Cleaning up GitHub deployments")
        keep_per_env = DEPLOYMENTS_KEEP_PER_ENV

        for repo in DEPLOYMENT_REPOS:
            full_repo = "%s/%s" % (GITHUB_ORG, repo)
            log.step("  Processing deployments for %s" % full_repo)

            open_prs_ok = True
            code, open_prs = capture_quiet(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    full_repo,
                    "--state",
                    "open",
                    "--limit",
                    "200",
                    "--json",
                    "number",
                    "--jq",
                    ".[].number",
                ]
            )
            if code != 0:
                open_prs_ok = False
                log.warn(
                    "  Could not list open PRs; pr-* deployments fall back to keep-%d"
                    % keep_per_env
                )

            code, deployments_blob = capture_quiet(
                [
                    "gh",
                    "api",
                    "repos/%s/deployments?per_page=100" % full_repo,
                    "--paginate",
                    "--jq",
                    "[.[] | {id: .id, environment: .environment, created_at: .created_at}]",
                ]
            )
            if code != 0:
                deployments_blob = "[]"

            # `jq -s 'flatten | sort_by(.created_at) | reverse'`.
            deployments = list(
                reversed(
                    jq_sort_by(
                        jq_flatten(json_values(deployments_blob, "flatten")),
                        lambda d: jq_get(d, "created_at"),
                    )
                )
            )
            total = len(deployments)
            log.debug("  Found %d deployments" % total)

            # `jq -r '[.[].environment] | unique | .[]'`, then an UNQUOTED `for env in $environments`. See HAZARD 5.
            environments_text = "\n".join(
                jq_text(v) for v in jq_unique([jq_get(d, "environment") for d in deployments])
            )
            environment_words = environments_text.split()

            deleted = 0
            budget_exhausted = False
            for env in environment_words:
                env_deps = [d for d in deployments if jq_get(d, "environment") == env]
                env_count = len(env_deps)

                env_keep = keep_per_env
                match = _PR_ENV_RE.match(env)
                if match:
                    pr_number = match.group(1)
                    if open_prs_ok and not _grep_qx(pr_number, open_prs):
                        env_keep = 0

                if env_count <= env_keep:
                    log.debug("  %s: %d deployment(s), all retained" % (env, env_count))
                    continue

                for dep in env_deps[env_keep:]:
                    if not self.deletes_budget_ok():
                        log.warn(
                            "  Phase 4: hit MAX_DELETES_PER_RUN=%s; remaining "
                            "deployments deferred to next run" % self.max_deletes
                        )
                        budget_exhausted = True
                        break
                    dep_id = jq_text(jq_get(dep, "id"))
                    created_at = jq_text(jq_get(dep, "created_at"))

                    if self.dry_run:
                        log.warn(
                            "  [DRY-RUN] Would delete: %s (%s, %s)" % (dep_id, env, created_at)
                        )
                        deleted += 1
                    else:
                        run_silent(
                            [
                                "gh",
                                "api",
                                "repos/%s/deployments/%s/statuses" % (full_repo, dep_id),
                                "-X",
                                "POST",
                                "-f",
                                "state=inactive",
                            ]
                        )
                        if retry_with_backoff(
                            3,
                            2,
                            [
                                "gh",
                                "api",
                                "-X",
                                "DELETE",
                                "repos/%s/deployments/%s" % (full_repo, dep_id),
                            ],
                            quiet=True,
                        ):
                            log.debug("  Deleted: %s (%s)" % (dep_id, env))
                            deleted += 1
                            self.record_delete()
                if budget_exhausted:
                    # `break 2`: out of the deployment loop AND the env loop.
                    break

            log.info(
                "  Deployments (%s): deleted %d of %d (keeping %d per environment, "
                "0 for closed-PR pr-*)" % (full_repo, deleted, total, keep_per_env)
            )

    # -- PHASE 5: CLOUDFLARE PAGES PREVIEW DEPLOYMENTS ---------------------

    def cleanup_cf_pages(self) -> None:
        """`cleanup_cf_pages` (:633-739).

        THE LATEST DEPLOYMENT PER BRANCH IS UNDELETABLE at the Cloudflare end, so
        the phase computes that set first and skips it, counting the skips into
        the summary line rather than into `deleted`. `group_by` SORTS, so
        `.[0].id` is the newest only because `all_deployments` was reversed into
        newest-first immediately above -- reproduced with the same ordering, not
        with a max().
        """
        log.step("Phase 5: Cleaning up Cloudflare Pages preview deployments")

        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not os.environ.get("CLOUDFLARE_API_TOKEN", "") or not account:
            log.warn(
                "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping CF Pages cleanup"
            )
            return

        project = CF_PAGES_PROJECT
        log.step("  Processing CF Pages project: %s" % project)

        all_deployments: list = []
        page = 1

        while True:
            code, response = self.cf_api(
                "GET",
                "/accounts/%s/pages/projects/%s/deployments?env=preview&per_page=25&page=%d"
                % (account, project, page),
            )
            if code != 0:
                response = '{"result":[]}'

            if _success_text(response) != "true":
                log.warn("  CF API request failed on page %d" % page)
                break

            page_results = [
                {
                    "id": jq_get(d, "id"),
                    "created_on": jq_get(d, "created_on"),
                    "branch": jq_get(d, "deployment_trigger", "metadata", "branch"),
                }
                for d in _iterate_result(response)
            ]

            count = len(page_results)
            all_deployments = all_deployments + page_results

            if count < 25:
                break
            page += 1

        all_deployments = list(
            reversed(jq_sort_by(all_deployments, lambda d: jq_get(d, "created_on")))
        )

        branch_latest = [
            group[0].get("id")
            for group in jq_group_by(all_deployments, lambda d: jq_get(d, "branch"))
        ]

        total = len(all_deployments)
        log.debug("  Found %d preview deployments" % total)

        deleted = 0
        skipped_latest = 0
        index = 0

        for deployment in all_deployments:
            dep_id = jq_text(deployment.get("id"))
            created_on = jq_text(deployment.get("created_on"))
            branch = jq_text(deployment.get("branch"))

            # `jq --arg id "$dep_id" 'index($id) != null'`: `$id` is always a
            # STRING, so a numeric id in the array would not match. jq equality, not Python's.
            is_branch_latest = any(_ord(v) == _ord(dep_id) for v in branch_latest)

            if is_branch_latest:
                log.debug("  Skipping (latest for branch '%s'): %s" % (branch, dep_id))
                skipped_latest += 1
                index += 1
                continue

            if self.should_retain(created_on, index):
                log.debug("  Keeping deployment: %s (branch: %s)" % (dep_id, branch))
            else:
                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 5: hit MAX_DELETES_PER_RUN=%s; remaining CF Pages "
                        "deployments deferred to next run" % self.max_deletes
                    )
                    break
                if self.dry_run:
                    log.warn(
                        "  [DRY-RUN] Would delete CF deployment: %s (branch: %s, "
                        "created: %s)" % (dep_id, branch, created_on)
                    )
                else:
                    code, del_response = self.cf_api(
                        "DELETE",
                        "/accounts/%s/pages/projects/%s/deployments/%s?force=true"
                        % (account, project, dep_id),
                    )
                    if code != 0:
                        del_response = '{"success":false}'

                    if _success_text(del_response) == "true":
                        log.debug("  Deleted CF deployment: %s (branch: %s)" % (dep_id, branch))
                        deleted += 1
                        self.record_delete()
                    else:
                        log.warn(
                            "  Failed to delete CF deployment: %s (branch: %s)" % (dep_id, branch)
                        )

            index += 1

        verb = "would delete" if self.dry_run else "deleted"
        log.info(
            "  CF Pages (%s): %s %d of %d preview deployments (%d latest-per-branch, "
            "skipped)" % (project, verb, deleted, total, skipped_latest)
        )

    # -- PHASE 5b: ORPHANED PER-PR PREVIEW WORKERS -------------------------

    def cleanup_preview_workers(self) -> None:
        """`cleanup_preview_workers` (:957-1016).

        FAILS CLOSED. An unreadable open-PR list SKIPS the phase, because the
        worst case here is deleting a live preview and that cannot be undone by
        the next run. The twin's banner says so at length, and names the run that
        made it necessary: `Cleanup PR Preview` 32903006150 died on GitHub's own
        internal DNS before checkout, leaking a Worker with nothing to notice.

        HAZARD 3 IS HERE: no `record_delete` on the success arm, so Workers are
        deleted without being charged to the global budget.
        """
        log.step("Phase 5b: Cleaning up orphaned per-PR preview Workers")

        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not os.environ.get("CLOUDFLARE_API_TOKEN", "") or not account:
            log.warn(
                "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping Worker cleanup"
            )
            return

        code, open_prs = capture_quiet(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                RELEASE_REPO,
                "--state",
                "open",
                "--limit",
                "200",
                "--json",
                "number",
                "--jq",
                ".[].number",
            ]
        )
        if code != 0:
            log.warn(
                "  Could not list open PRs; SKIPPING Worker cleanup rather than "
                "deleting on incomplete data"
            )
            return

        code, response = self.cf_api("GET", "/accounts/%s/workers/scripts" % account)
        if code != 0:
            response = '{"success":false}'

        if _success_text(response) != "true":
            log.warn("  Worker list API request failed, skipping Worker cleanup")
            return

        # `jq -r '.result[]?.id // empty'`: the `?` swallows a non-iterable `.result`, and `// empty` drops an id that is null or false.
        names_list = []
        for entry in _iterate_result_optional(response):
            value = jq_get(entry, "id") if isinstance(entry, dict) else None
            if value is None or value is False:
                continue
            names_list.append(jq_text(value))
        names = "\n".join(names_list)

        seen = 0
        deleted = 0
        for name in records(names):
            if name == "":
                continue
            seen += 1
            match = _PR_ENV_RE.match(name)
            if not match:
                continue
            pr_number = match.group(1)
            if _grep_qx(pr_number, open_prs):
                continue

            if not self.deletes_budget_ok():
                log.warn(
                    "  Phase 5b: hit MAX_DELETES_PER_RUN=%s; remaining Workers "
                    "deferred to next run" % self.max_deletes
                )
                break

            if self.dry_run:
                log.warn("  [DRY-RUN] Would delete Worker: %s (PR #%s closed)" % (name, pr_number))
                deleted += 1
                continue

            code, delete_response = self.cf_api(
                "DELETE", "/accounts/%s/workers/scripts/%s?force=true" % (account, name)
            )
            if code != 0:
                delete_response = '{"success":false}'
            if _success_text(delete_response) == "true":
                log.info("  Deleted Worker: %s (PR #%s closed)" % (name, pr_number))
                deleted += 1
            else:
                log.warn("  Failed to delete Worker: %s" % name)

        log.info(
            "  Workers: %d script(s) seen, %d orphan(s) %sdeleted"
            % (seen, deleted, "would be " if self.dry_run else "")
        )

    # -- PHASE 6: GITHUB ENVIRONMENTS --------------------------------------

    def cleanup_environments(self) -> None:
        """`cleanup_environments` (:766-839). HAZARD 4: IT CANNOT SUCCEED.

        Deleting an environment OBJECT needs Administration:write, and
        `check-no-app-admin-perm.sh` is a BLOCKING gate that forbids granting it
        to the App -- so the 403 arm is the designed outcome, which is why it
        logs at INFO and stops after the first one rather than warning per
        environment. Ported exactly, including that choice.
        """
        log.step("Phase 6: Cleaning up stale GitHub preview environments")

        for repo in DEPLOYMENT_REPOS:
            full_repo = "%s/%s" % (GITHUB_ORG, repo)
            log.step("  Processing environments for %s" % full_repo)

            code, environments_blob = capture_quiet(
                [
                    "gh",
                    "api",
                    "repos/%s/environments" % full_repo,
                    "--jq",
                    (
                        "[.environments[] | {name: .name, created: .created_at, "
                        "updated: .updated_at}]"
                    ),
                ]
            )
            if code != 0:
                environments_blob = "[]"

            pr_envs = [
                e
                for e in blob_array(environments_blob, "[.[] | select(...)]")
                if isinstance(jq_get(e, "name"), str) and _PR_NAME_RE.search(jq_get(e, "name"))
            ]

            total = len(pr_envs)
            log.debug("  Found %d pr-* environments" % total)

            if total == 0:
                log.info("  No stale preview environments to clean up")
                continue

            deleted = 0

            for env_entry in pr_envs:
                env_name = jq_text(jq_get(env_entry, "name"))
                # `sed 's/^pr-//'`.
                pr_number = env_name.removeprefix("pr-")

                code, pr_state = capture_quiet(
                    [
                        "gh",
                        "pr",
                        "view",
                        pr_number,
                        "--repo",
                        full_repo,
                        "--json",
                        "state",
                        "--jq",
                        ".state",
                    ]
                )
                if code != 0:
                    pr_state = "UNKNOWN"

                if pr_state == "OPEN":
                    log.debug("  Keeping environment: %s (PR #%s is open)" % (env_name, pr_number))
                    continue

                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 6: hit MAX_DELETES_PER_RUN=%s; remaining environments "
                        "deferred to next run" % self.max_deletes
                    )
                    break
                if self.dry_run:
                    log.warn(
                        "  [DRY-RUN] Would delete environment: %s (PR #%s state: %s)"
                        % (env_name, pr_number, pr_state)
                    )
                    deleted += 1
                elif (
                    run_silent(
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            "repos/%s/environments/%s" % (full_repo, env_name),
                        ]
                    )
                    == 0
                ):
                    log.debug(
                        "  Deleted environment: %s (PR #%s state: %s)"
                        % (env_name, pr_number, pr_state)
                    )
                    deleted += 1
                    self.record_delete()
                else:
                    log.info(
                        "  Environment %s left in place (by design: the App is "
                        "barred from Administration:write). Reap with a manual gh "
                        "sweep." % env_name
                    )
                    break

            if self.dry_run:
                log.info(
                    "  Environments (%s): would delete %d of %d pr-* environments"
                    % (full_repo, deleted, total)
                )
            else:
                log.info(
                    "  Environments (%s): deleted %d of %d pr-* environments"
                    % (full_repo, deleted, total)
                )

    # -- PHASE 7: CLOUDFLARE D1 PREVIEW DATABASES --------------------------

    def cleanup_d1_databases(self) -> None:
        """`cleanup_d1_databases` (:845-927).

        The one phase whose successful delete logs at INFO rather than DEBUG, so
        a nightly with no DEBUG still shows which databases went.
        """
        log.step("Phase 7: Cleaning up orphaned D1 preview databases")

        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not os.environ.get("CLOUDFLARE_API_TOKEN", "") or not account:
            log.warn("  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping D1 cleanup")
            return

        code, response = self.cf_api("GET", "/accounts/%s/d1/database?per_page=100" % account)
        if code != 0:
            response = '{"success":false}'

        if _success_text(response) != "true":
            log.warn("  D1 list API request failed, skipping D1 cleanup")
            return

        pr_databases = [
            {"name": jq_get(d, "name"), "uuid": jq_get(d, "uuid")}
            for d in _iterate_result(response)
            if isinstance(jq_get(d, "name"), str) and _D1_NAME_RE.search(jq_get(d, "name"))
        ]

        total = len(pr_databases)

        if total == 0:
            log.info("  No pr-* D1 databases found")
            return

        log.debug("  Found %d pr-* D1 databases" % total)

        deleted = 0
        skipped = 0

        for db_entry in pr_databases:
            db_name = jq_text(db_entry.get("name"))
            db_uuid = jq_text(db_entry.get("uuid"))
            # `${db_name#account-db-pr-}`.
            prefix = "account-db-pr-"
            pr_number = db_name.removeprefix(prefix)

            code, pr_state = capture_quiet(
                [
                    "gh",
                    "pr",
                    "view",
                    pr_number,
                    "--repo",
                    RELEASE_REPO,
                    "--json",
                    "state",
                    "--jq",
                    ".state",
                ]
            )
            if code != 0:
                pr_state = "UNKNOWN"

            if pr_state == "OPEN":
                log.debug("  Keeping D1 database: %s (PR #%s is open)" % (db_name, pr_number))
                skipped += 1
                continue

            if not self.deletes_budget_ok():
                log.warn(
                    "  Phase 7: hit MAX_DELETES_PER_RUN=%s; remaining D1 databases "
                    "deferred to next run" % self.max_deletes
                )
                break
            if self.dry_run:
                log.warn(
                    "  [DRY-RUN] Would delete D1 database: %s (PR #%s state: %s)"
                    % (db_name, pr_number, pr_state)
                )
                deleted += 1
            else:
                code, del_response = self.cf_api(
                    "DELETE", "/accounts/%s/d1/database/%s" % (account, db_uuid)
                )
                if code != 0:
                    del_response = '{"success":false}'

                if _success_text(del_response) == "true":
                    log.info(
                        "  Deleted D1 database: %s (PR #%s state: %s)"
                        % (db_name, pr_number, pr_state)
                    )
                    deleted += 1
                    self.record_delete()
                else:
                    log.warn("  Failed to delete D1 database: %s" % db_name)

        verb = "would delete" if self.dry_run else "deleted"
        log.info(
            "  D1 databases: %s %d of %d (%d open PRs, skipped)" % (verb, deleted, total, skipped)
        )

    # -- PHASE 7b: ORPHAN PER-PR TURNSTILE WIDGETS -------------------------

    def cleanup_orphan_turnstile_widgets(self) -> None:
        """`cleanup_orphan_turnstile_widgets` (:1028-1125).

        A 24h GRACE WINDOW so the explicit `cleanup-preview` path always wins the
        race, and the hold message counts the remaining hours by rounding UP
        (`(remaining + 3599) / 3600` in integer arithmetic).
        """
        log.step("Phase 7b: Cleaning up orphan per-PR Turnstile widgets")

        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not os.environ.get("CLOUDFLARE_API_TOKEN", "") or not account:
            log.warn(
                "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping "
                "Turnstile cleanup"
            )
            return

        code, response = self.cf_api(
            "GET", "/accounts/%s/challenges/widgets?per_page=100" % account
        )
        if code != 0:
            response = '{"success":false}'

        if _success_text(response) != "true":
            log.warn("  Turnstile widget list API request failed, skipping Turnstile cleanup")
            return

        pr_widgets = [
            {
                "name": jq_get(w, "name"),
                "sitekey": jq_get(w, "sitekey"),
                "created_on": jq_get(w, "created_on"),
            }
            for w in _iterate_result(response)
            if isinstance(jq_get(w, "name"), str) and _TURNSTILE_NAME_RE.search(jq_get(w, "name"))
        ]

        total = len(pr_widgets)

        if total == 0:
            log.info("  No per-PR Turnstile widgets found")
            return

        log.debug("  Found %d per-PR Turnstile widgets" % total)

        deleted = 0
        skipped = 0
        now_epoch = now_epoch_utc()
        grace_seconds = TURNSTILE_GRACE_SECONDS

        for widget_entry in pr_widgets:
            widget_name = jq_text(widget_entry.get("name"))
            widget_sitekey = jq_text(widget_entry.get("sitekey"))
            created_on = jq_text(widget_entry.get("created_on"))
            prefix = "rediacc-console-pr-"
            pr_number = widget_name.removeprefix(prefix)

            code, pr_state = capture_quiet(
                [
                    "gh",
                    "pr",
                    "view",
                    pr_number,
                    "--repo",
                    RELEASE_REPO,
                    "--json",
                    "state",
                    "--jq",
                    ".state",
                ]
            )
            if code != 0:
                pr_state = "UNKNOWN"

            if pr_state == "OPEN":
                log.debug(
                    "  Keeping Turnstile widget: %s (PR #%s is open)" % (widget_name, pr_number)
                )
                skipped += 1
                continue

            created_epoch = date_epoch_utc(created_on)
            age_seconds = arith(now_epoch) - arith(created_epoch)
            if arith_cmp(age_seconds, "lt", grace_seconds):
                remain_hrs = bash_div(grace_seconds - age_seconds + 3599, 3600)
                log.debug(
                    "  Holding Turnstile widget: %s (PR #%s %s, only %dh old; %dh "
                    "grace remaining)"
                    % (
                        widget_name,
                        pr_number,
                        pr_state,
                        bash_div(age_seconds, 3600),
                        remain_hrs,
                    )
                )
                skipped += 1
                continue

            if not self.deletes_budget_ok():
                log.warn(
                    "  Phase 7b: hit MAX_DELETES_PER_RUN=%s; remaining Turnstile "
                    "widgets deferred to next run" % self.max_deletes
                )
                break
            if self.dry_run:
                log.warn(
                    "  [DRY-RUN] Would delete Turnstile widget: %s (PR #%s state: %s)"
                    % (widget_name, pr_number, pr_state)
                )
                deleted += 1
            else:
                code, del_response = self.cf_api(
                    "DELETE",
                    "/accounts/%s/challenges/widgets/%s" % (account, widget_sitekey),
                )
                if code != 0:
                    del_response = '{"success":false}'

                if _success_text(del_response) == "true":
                    log.info(
                        "  Deleted Turnstile widget: %s (PR #%s state: %s)"
                        % (widget_name, pr_number, pr_state)
                    )
                    deleted += 1
                    self.record_delete()
                else:
                    log.warn("  Failed to delete Turnstile widget: %s" % widget_name)

        verb = "would delete" if self.dry_run else "deleted"
        log.info(
            "  Turnstile widgets: %s %d of %d (%d open or in grace, skipped)"
            % (verb, deleted, total, skipped)
        )

    # -- PHASE 8: R2 ORPHANS ------------------------------------------------

    def r2_ls_prefix(self, prefix: str) -> str:
        """`aws s3 ls "s3://$R2_BUCKET/$prefix" --endpoint-url ... 2>/dev/null || true`.

        Returns the RAW stdout, newlines included, because two callers want
        different things from it: `while read` over a process substitution (line
        by line, no trailing strip) and `[[ -n "$(...)" ]]` (which strips).
        """
        _code, out = _capture_raw(
            [
                "aws",
                "s3",
                "ls",
                "s3://%s/%s" % (self.r2_bucket, prefix),
                "--endpoint-url",
                os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
            ]
        )
        # The status is DISCARDED, exactly as `|| true` discards it: an unreachable bucket and an empty prefix are the same empty listing to every caller. That is HAZARD 1's shape again, in R2 rather than GitHub.
        return out

    def r2_prefix_last_modified(self, prefix: str) -> str:
        """LastModified of the first object under a prefix; "" when empty/unreadable.

        `list-objects-v2`, NOT `aws s3 ls --recursive`, and the twin says why:
        the latter exits 1 on an empty prefix, which under `set -eo pipefail`
        would abort the whole housekeeping run silently. The literal `None` that
        `--output text` prints for a missing key is treated as empty.
        """
        code, stamp = capture_quiet(
            [
                "aws",
                "s3api",
                "list-objects-v2",
                "--bucket",
                self.r2_bucket,
                "--prefix",
                prefix,
                "--max-items",
                "1",
                "--endpoint-url",
                os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                "--query",
                "Contents[0].LastModified",
                "--output",
                "text",
            ]
        )
        if code != 0:
            stamp = ""
        if stamp in {"None", ""}:
            return ""
        return stamp

    def r2_rm_recursive(self, prefix: str, label: str = "") -> None:
        """Delete a prefix recursively, or log the intent in dry-run.

        ONE `record_delete` FOR THE WHOLE PREFIX even though `--recursive` may
        remove many keys: the budget exists to protect GitHub's REST quota, and
        R2 deletes do not spend it.
        """
        suffix = " (%s)" % label if label != "" else ""
        if self.dry_run:
            log.warn("  [DRY-RUN] Would delete s3://%s/%s%s" % (self.r2_bucket, prefix, suffix))
            return
        run_quiet_err(
            [
                "aws",
                "s3",
                "rm",
                "s3://%s/%s" % (self.r2_bucket, prefix),
                "--recursive",
                "--endpoint-url",
                os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                "--quiet",
            ]
        )
        self.record_delete()
        log.info("  Deleted s3://%s/%s%s" % (self.r2_bucket, prefix, suffix))

    def cleanup_r2(self) -> None:
        """`cleanup_r2` (:1187-1553). Six sub-phases, in the twin's ORDER OF
        EXECUTION, which is 8a, 8b, 8c, 8d, 8f, 8e -- 8f really does run before
        8e in the file, and the labels really are out of order.

        `set +e` FOR THE WHOLE PHASE, restored at the end. The twin relaxes
        errexit here because several `aws | awk` pipes have SIGPIPE edges that
        would otherwise kill the job silently; every destructive call carries its
        own guard. The port has no errexit to relax, and the one place the
        difference shows is 8e's `jq 'length'` over an `aws` response of `null`,
        which is a soft failure here and a soft failure there.
        """
        log.step("Phase 8: Cleaning up R2 orphans")

        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
        endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
        if not access_key or not secret_key or not endpoint:
            log.warn(
                "  CLOUDFLARE_R2_ACCESS_KEY_ID / CLOUDFLARE_R2_SECRET_ACCESS_KEY / "
                "CLOUDFLARE_R2_ENDPOINT not set, skipping R2 cleanup"
            )
            return

        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
        os.environ["AWS_DEFAULT_REGION"] = "auto"

        now_epoch = arith(now_epoch_utc())
        dryrun_max_age = R2_RETENTION_DAYS * 86400
        orphan_ver_max_age = R2_ORPHAN_VERSION_AGE_DAYS * 86400

        # -- 8a. Dryrun reaper ---------------------------------------------
        log.step("  8a: dryrun-*/ older than %dd" % R2_RETENTION_DAYS)
        dryrun_deleted = 0
        budget_out = False
        for directory in R2_FORMAT_DIRS:
            for line in _stream_lines(self.r2_ls_prefix("%s/" % directory)):
                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 8a: hit MAX_DELETES_PER_RUN=%s; remaining R2 dryrun "
                        "prefixes deferred to next run" % self.max_deletes
                    )
                    budget_out = True
                    break
                sub = _awk_pre_field(line, _PRE_DRYRUN_RE)
                if sub == "":
                    continue
                prefix = "%s/%s" % (directory, sub)
                last = self.r2_prefix_last_modified(prefix)
                if last == "":
                    continue
                last_epoch = arith(date_epoch_utc(last))
                if last_epoch == 0:
                    continue
                if now_epoch - last_epoch > dryrun_max_age:
                    self.r2_rm_recursive(
                        prefix, "dryrun %dd old" % bash_div(now_epoch - last_epoch, 86400)
                    )
                    dryrun_deleted += 1
            if budget_out:
                break
        log.info(
            "  8a: processed %d format dirs, deleted %d dryrun prefix(es)"
            % (len(R2_FORMAT_DIRS), dryrun_deleted)
        )

        # -- 8b. PR channel reaper -----------------------------------------
        log.step("  8b: pr-N/ closed or older than %dd" % R2_PR_MAX_AGE_DAYS)
        pr_deleted = 0
        pr_age_max = R2_PR_MAX_AGE_DAYS * 86400
        budget_out = False
        for directory in R2_FORMAT_DIRS:
            for line in _stream_lines(self.r2_ls_prefix("%s/" % directory)):
                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 8b: hit MAX_DELETES_PER_RUN=%s; remaining R2 PR "
                        "prefixes deferred to next run" % self.max_deletes
                    )
                    budget_out = True
                    break
                sub = _awk_pre_field(line, _PRE_PR_RE)
                if sub == "":
                    continue
                pr_num = sub.removeprefix("pr-")
                pr_num = pr_num.removesuffix("/")
                prefix = "%s/%s" % (directory, sub)
                last = self.r2_prefix_last_modified(prefix)
                if last == "":
                    continue
                last_epoch = arith(date_epoch_utc(last))
                if last_epoch == 0:
                    continue
                age = now_epoch - last_epoch
                reason = ""
                if age > pr_age_max:
                    reason = "stale %dd" % bash_div(age, 86400)
                else:
                    code, state = capture_quiet(
                        [
                            "gh",
                            "pr",
                            "view",
                            pr_num,
                            "--repo",
                            RELEASE_REPO,
                            "--json",
                            "state",
                            "--jq",
                            ".state",
                        ]
                    )
                    if code != 0:
                        state = "UNKNOWN"
                    if state != "OPEN":
                        reason = "PR #%s %s" % (pr_num, state)
                if reason != "":
                    self.r2_rm_recursive(prefix, reason)
                    pr_deleted += 1
            if budget_out:
                break
        log.info("  8b: deleted %d PR channel prefix(es)" % pr_deleted)

        # -- 8c. Legacy dead prefixes --------------------------------------
        log.step("  8c: legacy dead prefixes")
        for dead in ("staging/", "packages/", "cli/latest/"):
            if self.r2_ls_prefix(dead).rstrip("\n") != "":
                self.r2_rm_recursive(dead, "legacy")

        # -- 8d. Sentinel-aware orphan sweep + drift detection --------------
        log.step("  8d: sentinel-aware orphan sweep + drift detection")
        drift_count = 0
        orphan_ver_deleted = 0
        code, tags_text = _pipe_grep(
            [
                "gh",
                "api",
                "repos/%s/tags" % RELEASE_REPO,
                "--paginate",
                "--jq",
                ".[].name",
            ],
            _STRICT_SEMVER_RE,
        )
        tag_set = {t for t in records(tags_text) if t != ""}

        cli_sentinels_list = rsv.list_sentinels("cli")
        pre_contract_floor = rsv.pre_contract_floor(cli_sentinels_list)
        if pre_contract_floor != "":
            log.info(
                "  8d: pre-contract floor = %s (versions below this are grandfathered)"
                % pre_contract_floor
            )
        else:
            log.info(
                "  8d: no cli sentinels yet; bijection contract not in effect, all "
                "versions in scope"
            )

        directory = "cli"
        # The twin calls `rsv_list_sentinels "$dir"` a SECOND time here rather than reusing the list it just fetched, which is a second aws call per run. Reproduced: the call log is part of the comparison.
        sentinel_set = {s for s in rsv.list_sentinels(directory) if s != ""}

        for line in _stream_lines(self.r2_ls_prefix("%s/" % directory)):
            sub = _awk_pre_field(line, _PRE_VERSION_RE)
            if sub == "":
                continue
            if not self.deletes_budget_ok():
                log.warn(
                    "  Phase 8d: hit MAX_DELETES_PER_RUN=%s; remaining orphan "
                    "versioned prefixes deferred to next run" % self.max_deletes
                )
                break
            ver = sub.removesuffix("/")
            if not _STRICT_SEMVER_RE.match(ver):
                continue

            # In-flight short-circuit, BEFORE any classification.
            in_flight = os.environ.get("IN_FLIGHT_VERSION", "")
            if in_flight != "" and ver == in_flight:
                continue

            has_sentinel = ver in sentinel_set
            has_tag = ver in tag_set

            if has_sentinel and has_tag:
                continue
            if not has_sentinel and not has_tag:
                last = self.r2_prefix_last_modified("%s/%s/" % (directory, ver))
                last_epoch = arith(date_epoch_utc(last))
                if last_epoch == 0 or now_epoch - last_epoch <= orphan_ver_max_age:
                    # The twin's line carries a U+2014 EM DASH. Spelled as an escape so this file holds no em dash byte (house rule)
                    # while the OUTPUT stays byte-identical, which is the whole
                    # point of the comparison.
                    log.info(
                        "  orphan %s/%s: skipping (younger than %dd or undatable "
                        "\u2014 may be an in-flight release)"
                        % (directory, ver, R2_ORPHAN_VERSION_AGE_DAYS)
                    )
                    continue
                self.r2_rm_recursive(
                    "%s/%s/" % (directory, ver),
                    "orphan %s/%s (no .released sentinel, no git tag, >%dd old)"
                    % (directory, ver, R2_ORPHAN_VERSION_AGE_DAYS),
                )
                orphan_ver_deleted += 1
                continue

            if pre_contract_floor not in ("", ver):
                oldest = _sort_v_first(pre_contract_floor, ver)
                if oldest != pre_contract_floor:
                    continue

            if has_sentinel:
                log.error(
                    "drift: %s/%s/.released exists but git tag %s missing" % (directory, ver, ver)
                )
                log.error(
                    "  remediation: re-run CD to tag/release %s, or scrub via "
                    "scripts/dev/scrub-sentinel.sh %s --execute" % (ver, ver)
                )
            else:
                log.error(
                    "drift: git tag %s exists but %s/%s/.released missing" % (ver, directory, ver)
                )
                log.error("  remediation: re-run CI for %s, or delete tag %s" % (ver, ver))
            drift_count += 1

        log.info(
            "  8d: deleted %d orphan versioned prefix(es); found %d drift finding(s)"
            % (orphan_ver_deleted, drift_count)
        )
        if drift_count > 0:
            self.housekeeping_fail(
                "Release-state drift",
                "8d: %d release-state drift finding(s); housekeeping refuses to "
                "auto-heal. See the drift lines above for per-version remediation." % drift_count,
            )

        # -- 8f. Channel artifact retention ---------------------------------
        log.step(
            "  8f: channel artifact retention (keep top %d semvers; zap 0.0.0-dev)"
            % R2_PACKAGE_KEEP_VERSIONS
        )
        pkg_deleted = 0
        budget_out = False
        for fmt in ("apt", "rpm", "apk", "archlinux", "npm"):
            if budget_out:
                break
            for channel in ("stable", "edge"):
                channel_root = "%s/%s/" % (fmt, channel)
                if self.r2_ls_prefix(channel_root).rstrip("\n") == "":
                    continue
                code, raw = _capture_raw(
                    [
                        "aws",
                        "s3",
                        "ls",
                        "s3://%s/%s" % (self.r2_bucket, channel_root),
                        "--recursive",
                        "--endpoint-url",
                        os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                    ]
                )
                # Same discard as `r2_ls_prefix`: the twin pipes `aws ... 2>/dev/null` straight into awk and never looks at the status.
                listing = _awk_channel_listing(raw)
                if listing == "":
                    continue
                top_versions = _top_versions(listing, R2_PACKAGE_KEEP_VERSIONS)
                for record in records(listing):
                    fields = record.split("|")
                    # `IFS='|' read -r ts semver is_dev key`: a key containing a
                    # `|` would land in `key` whole, because read assigns the REMAINDER to the last name.
                    ts = fields[0] if len(fields) > 0 else ""
                    semver = fields[1] if len(fields) > 1 else ""
                    is_dev = fields[2] if len(fields) > 2 else ""
                    key = "|".join(fields[3:]) if len(fields) > 3 else ""
                    if key == "":
                        continue
                    if not self.deletes_budget_ok():
                        log.warn(
                            "  Phase 8f: hit MAX_DELETES_PER_RUN=%s; remaining R2 "
                            "stale package files deferred to next run" % self.max_deletes
                        )
                        budget_out = True
                        break
                    ts_epoch = arith(date_epoch_utc(ts))
                    age = now_epoch - ts_epoch
                    if is_dev == "1":
                        tag = "0.0.0-dev pollution, %dd" % bash_div(age, 86400)
                        self._r2_rm_object(key, tag)
                        pkg_deleted += 1
                        continue
                    if semver in records(top_versions):
                        continue
                    tag = "v%s, outside top-%d" % (semver, R2_PACKAGE_KEEP_VERSIONS)
                    self._r2_rm_object(key, tag)
                    pkg_deleted += 1
                if budget_out:
                    break
        log.info(
            "  8f: deleted %d stale artifact(s) across apt/rpm/apk/archlinux/npm" % pkg_deleted
        )

        # -- 8e. Abort abandoned multipart uploads --------------------------
        log.step("  8e: abort multipart uploads older than 24h")
        code, uploads = capture_quiet(
            [
                "aws",
                "s3api",
                "list-multipart-uploads",
                "--bucket",
                self.r2_bucket,
                "--endpoint-url",
                os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                "--query",
                "Uploads[].{Key:Key,UploadId:UploadId,Initiated:Initiated}",
                "--output",
                "json",
            ]
        )
        if code != 0:
            uploads = "[]"
        # SOFT `jq 'length'`: this is inside the twin's `set +e` region, and the `--query` above renders `null` when there are no uploads, which jq cannot take a length of. The twin's variable ends up EMPTY and the `-eq 0` below reads it as zero.
        mpu_count = _soft_length_text(uploads)
        if arith_cmp(mpu_count, "eq", 0):
            log.info("  8e: no ongoing multipart uploads")
        else:
            mpu_aborted = 0
            mpu_max_age = MULTIPART_MAX_AGE_SECONDS
            for row in _stream_lines(_upload_rows(uploads)):
                parts = row.split("\t")
                key = parts[0] if parts else ""
                upload_id = parts[1] if len(parts) > 1 else ""
                initiated = "\t".join(parts[2:]) if len(parts) > 2 else ""
                if key == "":
                    continue
                init_epoch = arith(date_epoch_utc(initiated))
                if init_epoch == 0:
                    continue
                if now_epoch - init_epoch <= mpu_max_age:
                    continue
                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 8e: hit MAX_DELETES_PER_RUN=%s; remaining multipart "
                        "uploads deferred to next run" % self.max_deletes
                    )
                    break
                if self.dry_run:
                    log.warn(
                        "  [DRY-RUN] Would abort multipart: %s (age %dh)"
                        % (key, bash_div(now_epoch - init_epoch, 3600))
                    )
                    mpu_aborted += 1
                    continue
                if (
                    run_quiet_err(
                        [
                            "aws",
                            "s3api",
                            "abort-multipart-upload",
                            "--bucket",
                            self.r2_bucket,
                            "--key",
                            key,
                            "--upload-id",
                            upload_id,
                            "--endpoint-url",
                            os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                        ]
                    )
                    != 0
                ):
                    continue
                self.record_delete()
                log.info("  Aborted multipart: %s" % key)
                mpu_aborted += 1
            log.info(
                "  8e: aborted %d of %s (held %d under 24h grace)"
                % (mpu_aborted, mpu_count, arith(mpu_count) - mpu_aborted)
            )

    def _r2_rm_object(self, key: str, tag: str) -> None:
        """The single-object delete 8f uses twice, identically. Not a twin
        function: the twin repeats the five lines, and repeating them here would
        only invite the two copies to drift."""
        if self.dry_run:
            log.warn("  [DRY-RUN] Would delete s3://%s/%s (%s)" % (self.r2_bucket, key, tag))
            return
        run_quiet_err(
            [
                "aws",
                "s3",
                "rm",
                "s3://%s/%s" % (self.r2_bucket, key),
                "--endpoint-url",
                os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
                "--quiet",
            ]
        )
        self.record_delete()
        log.info("  Deleted %s (%s)" % (key, tag))

    # -- PHASE 9: STALE BRANCHES -------------------------------------------

    def cleanup_stale_branches(self) -> None:
        """`cleanup_stale_branches` (:1562-1664). Six repos, two calls per branch.

        THE DRY-RUN COUNTER IS SEPARATE, and the twin's comment says why: it used
        to increment `deleted`, so a dry run ended with "deleted 7" having
        deleted nothing, indistinguishable in the log from a run that really
        removed seven branches.

        THIS IS THE ONLY DELETE FAILURE IN THE FILE THAT FAILS THE RUN
        (`housekeeping_fail`, latched, reported once at the end), and the twin's
        comment explains that too: a 403 from a token without contents:write
        would otherwise be a `log_warn` nobody reads under a phase reporting a
        clean sweep it never performed.
        """
        log.step(
            "Phase 9: Cleaning up stale branches (>%s days, no open PR)" % self.branch_max_age_days
        )

        now_epoch = arith(now_epoch_local())
        # `local max_age_seconds=$((BRANCH_MAX_AGE_DAYS * 86400))`. A refused word
        # here does not just skip the phase: bash unwinds the whole call stack out to the top level, so Phases 10, 11 and 12 and the final summary never run and the script still exits 0. See HAZARD 8 in the module
        # docstring; `ExpansionAbortError` reproduces the unwind.
        try:
            max_age_seconds = arith(self.branch_max_age_days) * 86400
        except BashArithError as exc:
            _arith_report(exc.token, context="")
            raise ExpansionAbortError from None

        for repo_name in BRANCH_REPOS:
            full_repo = "%s/%s" % (GITHUB_ORG, repo_name)

            log.step("  Processing branches for %s" % full_repo)

            code, branches = capture_quiet(
                [
                    "gh",
                    "api",
                    "repos/%s/branches?per_page=100" % full_repo,
                    "--paginate",
                    "--jq",
                    ".[].name",
                ]
            )
            if code != 0:
                branches = ""

            if branches == "":
                log.debug("  No branches found (or API error)")
                continue

            deleted = 0
            kept = 0
            would_delete = 0

            for branch in records(branches):
                if branch == "":
                    continue
                if branch == "main":
                    continue

                code, open_prs = capture_quiet(
                    [
                        "gh",
                        "api",
                        "repos/%s/pulls?head=%s:%s&state=open&per_page=1"
                        % (full_repo, GITHUB_ORG, branch),
                        "--jq",
                        "length",
                    ]
                )
                if code != 0:
                    open_prs = "0"
                # `[[ "$open_prs" =~ ^[0-9]+$ ]] || open_prs=0` -- a 403 body
                # leaks to stdout even though gh exits non-zero, and the `-gt` below would blow up on it in a tight loop.
                if not _DIGITS_RE.match(open_prs):
                    open_prs = "0"

                if arith_cmp(open_prs, "gt", 0):
                    log.debug("    Keeping %s (has open PR)" % branch)
                    kept += 1
                    continue

                code, last_commit_date = capture_quiet(
                    [
                        "gh",
                        "api",
                        "repos/%s/branches/%s" % (full_repo, branch),
                        "--jq",
                        ".commit.commit.committer.date",
                    ]
                )
                if code != 0:
                    last_commit_date = ""

                if last_commit_date == "":
                    log.debug("    Keeping %s (cannot determine age)" % branch)
                    kept += 1
                    continue

                code, commit_epoch_text = capture_quiet(["date", "-d", last_commit_date, "+%s"])
                if code != 0:
                    commit_epoch_text = "0"
                age_seconds = now_epoch - arith(commit_epoch_text)

                if age_seconds < max_age_seconds:
                    log.debug(
                        "    Keeping %s (%d days old)" % (branch, bash_div(age_seconds, 86400))
                    )
                    kept += 1
                    continue

                age_days = bash_div(age_seconds, 86400)

                if not self.deletes_budget_ok():
                    log.warn(
                        "    Phase 9: hit MAX_DELETES_PER_RUN=%s; remaining stale "
                        "branches deferred to next run" % self.max_deletes
                    )
                    break
                if self.dry_run:
                    log.warn(
                        "    [DRY-RUN] Would delete %s (%d days old, no open PR)"
                        % (branch, age_days)
                    )
                    would_delete += 1
                else:
                    # `2>&1 >/dev/null`: stderr into the capture, stdout binned.
                    code, delete_err = _capture_stderr(
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            "repos/%s/git/refs/heads/%s" % (full_repo, branch),
                        ]
                    )
                    if code == 0:
                        log.info("    Deleted %s (%d days old)" % (branch, age_days))
                        deleted += 1
                        self.record_delete()
                    else:
                        self.housekeeping_fail(
                            "Stale-branch delete failed",
                            "Phase 9: could not delete %s@%s (%d days old): %s"
                            % (
                                full_repo,
                                branch,
                                age_days,
                                delete_err if delete_err != "" else "no error output from gh",
                            ),
                        )

            if self.dry_run:
                log.info(
                    "  Branches (%s): would delete %d, kept %d" % (repo_name, would_delete, kept)
                )
            else:
                log.info("  Branches (%s): deleted %d, kept %d" % (repo_name, deleted, kept))

    # -- PHASE 10: WORKFLOW RUNS -------------------------------------------

    def cleanup_workflow_runs(self) -> None:
        """`cleanup_workflow_runs` (:1673-1813).

        THE VACUOUS-GREEN CHECK at the end is the reason this phase is worth
        reading twice. It deleted nothing for `watchdog-monitor.yml` for months
        and reported success, because the scan window (MAX_PAGES x 100 runs)
        never reached back as far as the retention threshold. The warning fires
        only when the window was TRUNCATED (`page` exceeded the cap), so a young
        low-volume workflow with nothing to reap stays quiet.
        """
        log.step("Phase 10: Cleaning up completed workflow runs")

        code, workflows_blob = capture_quiet(
            [
                "gh",
                "api",
                "repos/%s/actions/workflows?per_page=100" % RELEASE_REPO,
                "--jq",
                (
                    '[.workflows[] | select(.state == "active") | '
                    "{id: .id, name: .name, path: .path}]"
                ),
            ]
        )
        if code != 0:
            workflows_blob = "[]"

        workflows = blob_array(workflows_blob)
        wf_count = len(workflows)

        if wf_count == 0:
            log.warn("  No active workflows listed (API error?); skipping phase")
            return

        now_epoch = arith(now_epoch_utc())

        total_seen = 0
        total_deleted = 0

        budget_out = False
        for wf in workflows:
            wf_id = jq_text(jq_get(wf, "id"))
            wf_name = jq_text(jq_get(wf, "name"))
            # Keyed by PATH, never by name: the watchdog's display name is generated per run, so a name match is unwritable.
            wf_path_value = jq_get(wf, "path")
            wf_path = jq_text(wf_path_value) if wf_path_value is not None else ""
            wf_retention_days = GH_RUNS_RETENTION_DAYS
            if wf_path == WATCHDOG_PATH:
                wf_retention_days = GH_RUNS_RETENTION_DAYS_WATCHDOG
            wf_retention_seconds = wf_retention_days * 86400

            log.step("  Workflow: %s (id=%s)" % (wf_name, wf_id))

            page = 1
            wf_index = 0
            wf_deleted = 0
            wf_seen = 0
            oldest_seen_epoch = 0
            consecutive_failures = 0

            while page <= GH_RUNS_MAX_PAGES_PER_WORKFLOW:
                code, runs_blob = capture_quiet(
                    [
                        "gh",
                        "api",
                        "repos/%s/actions/workflows/%s/runs?status=completed&per_page=100&page=%d"
                        % (RELEASE_REPO, wf_id, page),
                        "--jq",
                        (
                            "[.workflow_runs[] | {id: .id, created_at: .created_at, "
                            "conclusion: .conclusion}]"
                        ),
                    ]
                )
                if code != 0:
                    runs_blob = "[]"

                runs = blob_array(runs_blob)
                page_count = len(runs)
                if page_count == 0:
                    break

                stop_workflow = False
                for run in runs:
                    if not self.deletes_budget_ok():
                        log.warn(
                            "  Phase 10: hit MAX_DELETES_PER_RUN=%s; remaining workflow "
                            "runs deferred to next run" % self.max_deletes
                        )
                        budget_out = True
                        break
                    run_id = jq_text(jq_get(run, "id"))
                    created_at = jq_text(jq_get(run, "created_at"))
                    wf_seen += 1

                    if wf_index < GH_RUNS_KEEP_PER_WORKFLOW:
                        wf_index += 1
                        continue

                    created_epoch = arith(date_epoch(created_at))
                    oldest_seen_epoch = created_epoch
                    if created_epoch == 0 or now_epoch - created_epoch < wf_retention_seconds:
                        wf_index += 1
                        continue

                    if self.dry_run:
                        log.warn(
                            "  [DRY-RUN] Would delete run: %s (%s, %s)"
                            % (run_id, wf_name, created_at)
                        )
                        wf_deleted += 1
                    elif retry_with_backoff(
                        3,
                        2,
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            "repos/%s/actions/runs/%s" % (RELEASE_REPO, run_id),
                        ],
                        quiet=True,
                    ):
                        log.debug("  Deleted run: %s (%s)" % (run_id, wf_name))
                        wf_deleted += 1
                        self.record_delete()
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        log.warn("  Failed to delete run: %s (%s)" % (run_id, wf_name))
                        if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                            log.warn(
                                "  Skipping remaining runs for %s after %d "
                                "consecutive failures" % (wf_name, consecutive_failures)
                            )
                            stop_workflow = True
                            break
                    wf_index += 1

                if budget_out or stop_workflow:
                    break
                if page_count < 100:
                    break
                page += 1

            if (
                wf_deleted == 0
                and oldest_seen_epoch > 0
                and page > GH_RUNS_MAX_PAGES_PER_WORKFLOW
                and now_epoch - oldest_seen_epoch < wf_retention_seconds
            ):
                span_days = bash_div(now_epoch - oldest_seen_epoch, 86400)
                log.warn(
                    "  %s: scan window reaches only %dd but retention is %dd --"
                    % (wf_name, span_days, wf_retention_days)
                )
                log.warn(
                    "    nothing here can EVER be reaped. Raise GH_RUNS_MAX_PAGES_PER_WORKFLOW"
                )
                log.warn(
                    "    (currently %d) or give this workflow its own retention."
                    % GH_RUNS_MAX_PAGES_PER_WORKFLOW
                )
            total_seen += wf_seen
            total_deleted += wf_deleted

            if wf_deleted > 0:
                verb = "would delete" if self.dry_run else "deleted"
                log.info(
                    "  %s: %s %d of %d (kept top %d + within %dd)"
                    % (
                        wf_name,
                        verb,
                        wf_deleted,
                        wf_seen,
                        GH_RUNS_KEEP_PER_WORKFLOW,
                        GH_RUNS_RETENTION_DAYS,
                    )
                )

            if budget_out:
                break

        verb = "would delete" if self.dry_run else "deleted"
        log.info(
            "  Workflow runs: %s %d of %d (across %d workflows)"
            % (verb, total_deleted, total_seen, wf_count)
        )

    # -- PHASE 11: WORKFLOW ARTIFACTS --------------------------------------

    def cleanup_workflow_artifacts(self) -> None:
        """`cleanup_workflow_artifacts` (:1823-1900)."""
        log.step("Phase 11: Cleaning up workflow artifacts")

        now_epoch = arith(now_epoch_utc())
        retention_seconds = GH_ARTIFACTS_RETENTION_DAYS * 86400

        page = 1
        seen = 0
        deleted = 0
        expired_count = 0
        consecutive_failures = 0

        while page <= GH_ARTIFACTS_MAX_PAGES:
            code, artifacts_blob = capture_quiet(
                [
                    "gh",
                    "api",
                    "repos/%s/actions/artifacts?per_page=100&page=%d" % (RELEASE_REPO, page),
                    "--jq",
                    (
                        "[.artifacts[] | {id: .id, created_at: .created_at, "
                        "expired: .expired, size: .size_in_bytes}]"
                    ),
                ]
            )
            if code != 0:
                artifacts_blob = "[]"

            artifacts = blob_array(artifacts_blob)
            page_count = len(artifacts)
            if page_count == 0:
                break

            stop = False
            for artifact in artifacts:
                if not self.deletes_budget_ok():
                    log.warn(
                        "  Phase 11: hit MAX_DELETES_PER_RUN=%s; remaining artifacts "
                        "deferred to next run" % self.max_deletes
                    )
                    stop = True
                    break
                artifact_id = jq_text(jq_get(artifact, "id"))
                created_at = jq_text(jq_get(artifact, "created_at"))
                expired = jq_text(jq_get(artifact, "expired"))
                seen += 1

                should_delete = False
                if expired == "true":
                    should_delete = True
                    expired_count += 1
                else:
                    created_epoch = arith(date_epoch(created_at))
                    if created_epoch != 0 and now_epoch - created_epoch >= retention_seconds:
                        should_delete = True

                if not should_delete:
                    continue

                if self.dry_run:
                    log.warn(
                        "  [DRY-RUN] Would delete artifact: %s (created: %s, expired: %s)"
                        % (artifact_id, created_at, expired)
                    )
                    deleted += 1
                elif retry_with_backoff(
                    3,
                    2,
                    [
                        "gh",
                        "api",
                        "-X",
                        "DELETE",
                        "repos/%s/actions/artifacts/%s" % (RELEASE_REPO, artifact_id),
                    ],
                    quiet=True,
                ):
                    log.debug("  Deleted artifact: %s" % artifact_id)
                    deleted += 1
                    self.record_delete()
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    log.warn("  Failed to delete artifact: %s" % artifact_id)
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        log.warn(
                            "  Stopping artifact cleanup after %d consecutive "
                            "failures" % consecutive_failures
                        )
                        stop = True
                        break

            if stop:
                break
            if page_count < 100:
                break
            page += 1

        verb = "would delete" if self.dry_run else "deleted"
        log.info(
            "  Artifacts: %s %d of %d (%d already expired, retention: %dd)"
            % (verb, deleted, seen, expired_count, GH_ARTIFACTS_RETENTION_DAYS)
        )

    # -- PHASE 12: ACTIONS CACHE -------------------------------------------

    def cleanup_actions_cache(self) -> None:
        """`cleanup_actions_cache` (:1910-1993). LRU eviction toward a 5 GB floor.

        THE KEY IS TRUNCATED TO 40 CHARACTERS in the dry-run line
        (`${key:0:40}...`), and bash's substring expansion on a SHORTER key
        yields the whole key with the three dots still appended. Reproduced.
        """
        log.step("Phase 12: Cleaning up Actions cache (target <= %d GB)" % GH_CACHE_KEEP_GB)

        code, caches_blob = capture_quiet(
            [
                "gh",
                "api",
                "--paginate",
                "repos/%s/actions/caches?per_page=100&sort=last_accessed_at&direction=asc"
                % RELEASE_REPO,
                "--jq",
                (
                    ".actions_caches[] | {id: .id, key: .key, ref: .ref, "
                    "size: .size_in_bytes, last_accessed_at: .last_accessed_at}"
                ),
            ]
        )
        # `gh ... | jq -s 'sort_by(...)' || echo "[]"`. THE `||` COVERS THE WHOLE PIPELINE under pipefail, and `echo` APPENDS to whatever the pipeline already wrote -- so a gh that fails AFTER emitting rows leaves the variable holding TWO json values: the sorted array, then an empty one. Every downstream jq then answers twice ("3\n0"), which is why `total` and `total_bytes` are
        # carried as TEXT here and read through the bash arithmetic rules rather than as Python ints. A port that collapsed this to `[]` would take a completely different branch from the twin on the one input where gh half-fails.
        stream = [
            jq_sort_by(
                json_values(caches_blob, "sort_by(.last_accessed_at)"),
                lambda c: jq_get(c, "last_accessed_at"),
            )
        ]
        if code != 0:
            stream.append([])
        total_text = "\n".join(str(len(value)) for value in stream)
        caches = [entry for value in stream for entry in value]

        if arith_cmp(total_text, "eq", 0):
            log.info("  No Actions cache entries found")
            return

        # `jq '[.[].size] | add // 0'`, once per value in the stream.
        total_bytes_text = "\n".join(str(_sum_sizes(value)) for value in stream)
        ceiling_bytes = GH_CACHE_KEEP_GB * 1024 * 1024 * 1024

        log.debug(
            "  Total: %s entries, %d MB"
            % (total_text, bash_div(_arith_expand(total_bytes_text), 1024 * 1024))
        )

        if arith_cmp(total_bytes_text, "le", ceiling_bytes):
            log.info(
                "  Actions cache: %d MB <= ceiling, nothing to evict"
                % bash_div(_arith_expand(total_bytes_text), 1024 * 1024)
            )
            return

        running = _arith_expand(total_bytes_text)
        deleted = 0
        freed = 0
        consecutive_failures = 0

        for entry in caches:
            if not self.deletes_budget_ok():
                log.warn(
                    "  Phase 12: hit MAX_DELETES_PER_RUN=%s; remaining cache entries "
                    "deferred to next run" % self.max_deletes
                )
                break
            if running <= ceiling_bytes:
                break

            entry_id = jq_text(jq_get(entry, "id"))
            key = jq_text(jq_get(entry, "key"))
            ref = jq_text(jq_get(entry, "ref"))
            size_text = jq_text(jq_get(entry, "size"))
            last = jq_text(jq_get(entry, "last_accessed_at"))
            size = arith(size_text) if _INT_RE.match(size_text) else 0

            if self.dry_run:
                log.warn(
                    "  [DRY-RUN] Would delete cache: id=%s size=%dMB last_accessed=%s "
                    "ref=%s key=%s..."
                    % (entry_id, bash_div(size, 1024 * 1024), last, ref, key[:40])
                )
                deleted += 1
                freed += size
                running -= size
            elif retry_with_backoff(
                3,
                2,
                [
                    "gh",
                    "api",
                    "-X",
                    "DELETE",
                    "repos/%s/actions/caches/%s" % (RELEASE_REPO, entry_id),
                ],
                quiet=True,
            ):
                log.debug(
                    "  Deleted cache: id=%s (%d MB)" % (entry_id, bash_div(size, 1024 * 1024))
                )
                deleted += 1
                freed += size
                running -= size
                self.record_delete()
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                log.warn("  Failed to delete cache: id=%s" % entry_id)
                if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                    log.warn(
                        "  Stopping cache cleanup after %d consecutive failures"
                        % consecutive_failures
                    )
                    break

        # THE TWO BRANCHES DIFFER BY MORE THAN THE VERB: the dry-run arm says "freeING", the real arm says "freeD". Spelled out in full rather than assembled from a verb variable, because the first version of this port did assemble it and printed "freed" in a dry run. The differential
        # caught it; a reader would not have.
        if self.dry_run:
            log.info(
                "  Actions cache: would delete %d of %s, freeing ~%d MB "
                "(surviving: ~%d MB / ceiling %d GB)"
                % (
                    deleted,
                    total_text,
                    bash_div(freed, 1024 * 1024),
                    bash_div(running, 1024 * 1024),
                    GH_CACHE_KEEP_GB,
                )
            )
        else:
            log.info(
                "  Actions cache: deleted %d of %s, freed ~%d MB "
                "(surviving: ~%d MB / ceiling %d GB)"
                % (
                    deleted,
                    total_text,
                    bash_div(freed, 1024 * 1024),
                    bash_div(running, 1024 * 1024),
                    GH_CACHE_KEEP_GB,
                )
            )

    # -- MAIN ---------------------------------------------------------------

    def run_all_phases(self) -> int:
        """`run_all_phases` (:2004-2051), in the twin's order, blank lines and all.

        THE BLANK LINES GO TO STDOUT (`echo ""`) while every log line goes to
        stderr, so the two streams interleave differently and a comparison that
        merged them would not notice if one moved.

        ONE EXIT POINT for every latched failure, AFTER every phase has had its
        run. Returning non-zero out of a phase instead is what once disabled
        Phase 8f and unset errexit for Phases 9-12.
        """
        log.step("Housekeeping: cleanup-versions")
        log.step(
            "  Retention: %s days OR last %s versions" % (self.retention_days, self.keep_versions)
        )
        if self.dry_run:
            log.warn("  DRY-RUN mode: no deletions will be performed")
        _blank()

        self.cleanup_releases()
        _blank()
        self.cleanup_tags()
        _blank()
        self.cleanup_packages()
        _blank()
        self.cleanup_deployments()
        _blank()
        self.cleanup_cf_pages()
        _blank()
        self.cleanup_preview_workers()
        _blank()
        self.cleanup_environments()
        _blank()
        self.cleanup_d1_databases()
        _blank()
        self.cleanup_orphan_turnstile_widgets()
        _blank()
        self.cleanup_r2()
        _blank()
        self.cleanup_stale_branches()
        _blank()
        self.cleanup_workflow_runs()
        _blank()
        self.cleanup_workflow_artifacts()
        _blank()
        self.cleanup_actions_cache()

        _blank()
        log.info("Total deletes this run: %d / %s" % (self.deletes_this_run, self.max_deletes))
        log.info("Housekeeping complete")

        if self.housekeeping_failed:
            log.error(
                "Housekeeping FAILED: see the ::error annotations above. Phases still "
                "ran to completion; nothing was auto-healed."
            )
            return 1
        return 0

    def run_phase(self, name: str) -> int:
        """Drive ONE phase, the way `source ...; cleanup_stale_branches` does.

        The names are the twin's function names. Anything else is a caller
        error and says so rather than silently running nothing, because a typo
        that ran zero phases and exited 0 is precisely the vacuous green this
        differential exists to prevent.
        """
        method = getattr(self, name, None)
        if method is None or not name.startswith(("cleanup_", "run_all")):
            sys.stderr.write("cleanup_versions.py: no such phase: %s\n" % name)
            return 2
        result = method()
        return result if isinstance(result, int) else 0


def main(argv: list[str]) -> int:
    """`if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then run_all_phases; fi`."""
    try:
        housekeeping = Housekeeping(argv)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    try:
        return housekeeping.run_all_phases()
    except ExpansionAbortError:
        # bash unwinds to the top level on an expansion error, abandoning every
        # function frame, and then looks for the NEXT top-level command. In this
        # script `run_all_phases` is the last one, so the shell ends carrying the failed expansion's status, which is 1. Measured, both ways: with a trailing `echo` after the call the same script exits 0, because the echo succeeded. See HAZARD 8.
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
