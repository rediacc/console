#!/usr/bin/env python3
"""Security audit with allowlist support, ported from `.ci/scripts/security/audit.sh`.

THIS FILE IS THE GATE. It carries `check:ci-security-audit` outright: `package.json`, the `Audit` step in `.github/workflows/ci-quality.yml` and `scripts/ci-runner/manifest.ts` all name this path, and `.ci/scripts/security/audit.sh` was deleted in the same change (W7P5-b).

PORTED FROM `.ci/scripts/security/audit.sh` (541 lines). The licence for the deletion is `.ci/shadow/w7p6-audit.observations.jsonl`, a K=5 ledger reading EQUIVALENT over five distinct clean trees with five distinct finding sets, plus the differential in `.ci/rediacc_ci/tests/test_security_audit.py`, which agreed on both streams, the exit code and every external command's argv.

THE BASH LINE NUMBERS QUOTED THROUGHOUT THE COMMENTS BELOW ARE ARCHAEOLOGY. They point into the deleted twin, they are what each clause here was proved against, and they are kept so a future reader can find the same clause in git history rather than guess at it.

WHAT THE GATE DOES, in the order it does it, because the order is the contract:

  0. parse both allowlists, refuse any entry whose `# BLOCKER:` is missing or
     low-effort, then refuse any entry older than AGE_FAIL_DAYS.
  1. force npm to 11.x, then `npm audit signatures` with two retries and a TUF
     cache wipe between them. A bad signature is NOT allowlistable.
  2. pass 1, production dependencies: `npm audit --json --omit=dev`, zero
     tolerance except for `.audit-prod-allowlist`.
  3. pass 2, everything: `npm audit --json`, with `.audit-allowlist` applying to
     the dev-only remainder.
  4. pass 3, the strict stale sweep: an allowlisted advisory that now has a fix,
     or has stopped firing altogether, fails unless it carries a BLOCKER.

FOUR LIBRARIES ARE NOT RE-PORTED HERE, because they already are. The twin `source`s `emit-advisory.sh`, `blocker-validator.sh`, `release-age.sh` and `age-check.sh`; the last three are themselves SHIMS that shell out to `rediacc_ci.core.allowlist` / `.release_age` / `.age`, and the first has a port at `rediacc_ci.core.advisory`. So this file imports the same four modules the twin
ultimately reaches, and the differential measures THIS file rather than re-measuring them: `test_core_advisory.py`, `test_core_blocker_validator.py`, `test_core_release_age.py` and `test_core_age.py` own those.

--------------------------------------------------------------------------
DEFECT 1, MEASURED: AN EMPTY `npm audit` REPORT IS A PASS, NOT A REFUSAL
--------------------------------------------------------------------------
`run_audit` validates with `jq empty "$output"`, and `jq empty` on a ZERO-BYTE file exits 0, because a stream of no JSON values is a valid stream:

    $ : > empty.json && jq empty empty.json ; echo $?
    0
    $ jq '.metadata.vulnerabilities.total // 0' empty.json ; echo "[$?]"
    [0]                                   # NOTHING on stdout, exit 0

The empty output then flows into `prod_total=$(jq ...)`, which is the empty
string, and `[[ "" -gt 0 ]]` is bash arithmetic on an empty value, which is 0. Measured: the gate prints `No production vulnerabilities`, then `Security audit passed`, and exits 0 having audited nothing. Every way `npm audit --json` can produce an empty file (a killed child that wrote no bytes before the signal, a registry error handled quietly by a future npm, a full disk)
therefore reads as a clean tree. This port REPRODUCES it, and `test_security_audit.py` pins it as a fact about the twin rather than fixing it here: the fix belongs to the twin, and a port that refused where the twin passes would fail its own differential.

--------------------------------------------------------------------------
DEFECT 2, MEASURED: A NON-NUMERIC ALLOWLIST ENTRY KILLS THE GATE SILENTLY
--------------------------------------------------------------------------
`get_advisory_fix_info` interpolates the entry into `($id | tonumber)`, and `tonumber` on a non-numeric string is a RUNTIME error, which is jq exit 5:

    $ jq -c --arg id "GHSA-xxxx" '.a | select(. == ($id|tonumber))' x.json
    jq: error (at x.json:1): string ("GHSA-xxxx") cannot be parsed as a number
    $ echo $?
    5

The stderr is swallowed by the call's own `2>/dev/null`, and `set -o pipefail`
then hands the 5 to `info=$(get_advisory_fix_info ...)`. In
`should_defer_advisory` that is harmless, because the function is only ever reached as an `if` condition and `set -e` is suspended there. In `check_stale_entries` it is NOT: that function is called plainly at `audit.sh:528`, so `set -e` fires and the whole gate dies with exit 5, no message on either stream, at the very end of a run that has already done its network work. An
allowlist keyed by GHSA id rather than by npm advisory source id is the obvious way to arrive there, and the allowlist header only asks for "advisory source ID (from npm audit --json)" in a comment. Reproduced here, and driven on both sides by `test_a_non_numeric_allowlist_entry_kills_both_sides_with_exit_5`.

--------------------------------------------------------------------------
DEFECT 3, MEASURED: TAB IS IFS WHITESPACE, SO AN EMPTY FIELD SHIFTS THE REST
--------------------------------------------------------------------------
`load_advisory_details` reads three `@tsv` fields with
`IFS=$'\\t' read -r ADV_VULN_RANGE[$s] ADV_PATCHED_VERSION[$s] ADV_DESC_PREVIEW[$s]`,
and TAB IS IFS WHITESPACE in bash, so consecutive tabs collapse into one delimiter and leading tabs are stripped:

    $ IFS=$'\\t' read -r a b c <<< $'\\t1.2.3\\tdesc'; echo "a=[$a] b=[$b] c=[$c]"
    a=[1.2.3] b=[desc] c=[]

A GitHub advisory with an EMPTY `vulnerable_version_range` and a real `first_patched_version` -- which is what the Advisory Database returns for several npm entries -- therefore renders as `Affected: 1.2.3 -> Patched in: <the description>`. The patched version is printed as the affected range and the description as the patched version. Same collapse in `build_advisory_map` for an
advisory with an empty severity or url. `bash_read_fields` below reproduces the splitting rule exactly, so the port prints the same wrong line, and `test_an_empty_vulnerable_range_shifts_the_fields` pins it.

--------------------------------------------------------------------------
DEFECT 4: `No production vulnerabilities` PRINTS EVEN WHEN THERE ARE SOME
--------------------------------------------------------------------------
`log_success "No production vulnerabilities"` at `audit.sh:462` sits OUTSIDE the `if [[ "$prod_total" -gt 0 ]]` block, so a run that has just printed `Allowed production vulnerabilities: 10 (see .ci/policy/.audit-prod-allowlist)` follows it with a green line claiming there are none. Cosmetic, loud, and reproduced verbatim.

--------------------------------------------------------------------------
DEFECT 5: A WRONG-SHAPED (BUT VALID) REPORT IS A PASS WITH A jq ERROR ON stderr
--------------------------------------------------------------------------
`build_advisory_map` feeds its loop from a PROCESS SUBSTITUTION, `while ... done < <(jq -r '...' "$audit_json")`, whose exit status bash discards. A document that parses but has no `.vulnerabilities` object makes that jq exit 5
with `jq: error (at audit-prod.json:1): null (null) has no keys` on stderr, and
the run continues with an empty advisory map, `total // 0` supplying 0, and a green verdict. Reproduced, message and line number included; see `jq_error`.

--------------------------------------------------------------------------
DEFECT 6, MEASURED, AND THE WORST OF THE SIX: A FAILED `gh api` KILLS THE GATE
WITH A BARE EXIT 5 AND NOT ONE BYTE ON EITHER STREAM
--------------------------------------------------------------------------
Two faults compose, and neither is visible on its own.

FIRST, `xargs -I {}` SUBSTITUTES THE PLACEHOLDER INSIDE THE SCRIPT BODY.
`audit.sh:125-131` passes the worker as `bash -c '<script>' _ {}`, and the
script text is an INITIAL ARGUMENT, so every `{}` in it is replaced too --
including the `echo "{}" > "$out"` that is supposed to write an empty JSON
object when the fetch fails. Measured on GNU xargs 4.10.0:

    $ printf 'SLUG-A\n' | xargs -I {} bash -c 'echo "arg1=$1 literal={}"' _ {}
    arg1=SLUG-A literal=SLUG-A

so the fallback writes the BARE GHSA SLUG into `<cache>/<slug>.json`:

    $ cat .audit-advisory-cache/GHSA-zzzz-zzzz-zzzz.json
    GHSA-zzzz-zzzz-zzzz

SECOND, THAT FILE IS NOT JSON, AND THE READER IS UNGUARDED. `load_advisory_details`
does `details=$(jq -r '...' "$cache" 2>/dev/null)`; jq answers
`parse error: Invalid numeric literal` and exits 5, the `2>/dev/null` eats the message, and the assignment is a plain command under `set -e` in a function called plainly from `build_advisory_map`, which is called plainly from `main`. The gate exits 5 having printed nothing about it.

WHAT THAT COSTS, and it is not hypothetical: `gh api` fails for a 404 on an advisory the Advisory Database has not published under that slug, for any network fault, and -- exactly the case the gate header's BLOCKER is written about -- for the anonymous 60/hr rate limit when GH_TOKEN is absent. Any one of those turns the whole security audit into `exit 5`, silently, AFTER the two
`npm audit` round trips have already run. Measured end to end in the fixture: one advisory whose fetch fails, twin stops after `-> Auditing all dependencies (allowlist for dev-only)` with empty stderr and exit 5.

REPRODUCED ON BOTH COUNTS, and it is the single most uncomfortable thing in this
file: `_fetch_one` writes the slug rather than `{}`, and `load_advisory_details`
raises `Die(5)`. A port that quietly wrote `{}` would be a port that disagreed
with the live gate about whether the build passes.

--------------------------------------------------------------------------
WHAT DIVERGES, DELIBERATELY, AND WHERE THE DIFFERENTIAL SAYS SO
--------------------------------------------------------------------------
  * ITERATION ORDER. `check_stale_entries` and the two age loops walk
    `"${!ALLOWED_*[@]}"`, a bash hash order; a Python dict is insertion order.
    Neither is sorted and neither is part of the contract, so the differential
    compares bytes for single-entry cases and sorted multisets for the rest.
    This is the same ruling `core/blocker_validator.py` behaviour 4 records.
  * THE RUNNER MEMO inside `rediacc_ci.core.release_age`, which caches the
    node/tsx probe the twin re-runs per delegate call (that module's DEFECT 1).
    Visible in the fake `node` call log as fewer `--window-seconds` probes on
    the port's side, and asserted AS a divergence rather than smoothed over.
  * `sys.argv[0]` IN A `command not found`. Bash names the script it is running;
    so does this file. The two paths differ by construction and the differential
    normalises exactly that substring, nothing else.

WHAT IS SHELLED OUT AND WHAT IS RE-IMPLEMENTED, since the line is not obvious: `npm`, `gh`, `sleep` and `date` are SPAWNED, because the twin spawns them and three of the four are the thing under test. `jq` and `grep` are RE-IMPLEMENTED in Python, because they are pure text transforms with no side effects, and a port that shelled out to them would be measuring jq rather than this
gate. `test_security_audit.py` pins both re-implementations against the REAL tools on this host, so a jq or ugrep upgrade that changes an answer goes red here rather than silently at a call site.

`sleep` LOOKS ODD IN PYTHON AND IS THE RIGHT CALL. `time.sleep(10)` would be the obvious spelling and would hide the retry ladder from every observer: the twin's `sleep` is `/usr/bin/sleep`, so a recording fake on a scratch PATH sees it, and the differential can therefore assert that the port sleeps exactly as many times as the twin does, in the same places, without waiting 20 real
seconds to find out.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.core import advisory, age, blocker_validator, release_age
from rediacc_ci.policy_paths import policy_rel

# THE EM DASH IS BUILT, NEVER TYPED. Nine of the twin's messages carry U+2014 and byte equality is the whole claim of this file, but the repo's house rule bans the literal character from authored text and `check:ci-em-dash-surfaces` scans `.ci/**/*.py`. `core/allowlist.py:180` already resolves the same conflict the same way; this is that decision, not a new one.
EM = "\u2014"

# `ADVISORY_CACHE_DIR=".audit-advisory-cache"` (audit.sh:50). RELATIVE, and it
# stays relative: the twin `cd`s to the repo root first and .gitignore lists the path from the root.
ADVISORY_CACHE_DIR = ".audit-advisory-cache"

# The two reports, both written into the repo root and both gitignored. `audit-report.json` SURVIVES the run for the CI artifact upload; only the prod sidecar is removed (audit.sh:537-538).
PROD_REPORT = "audit-prod.json"
ALL_REPORT = "audit-report.json"

# The two allowlists, by the paths the twin passes -- which appear verbatim in error messages, so the STRING must not change.
#
# `policy_rel`, not `policy_path`: check:ci-policy-inventory refuses a hand-built policy path so the directory is written down once, and the seam satisfies that. But `policy_path` answers an ABSOLUTE path, which would rewrite every message these appear in and diverge from the twin -- the same reason manifest.ts's `paths:` selector is exempt by name. `policy_rel` is the
# repo-relative form, and it returns these three byte-for-byte (driven, not assumed).
PROD_ALLOWLIST = policy_rel(".audit-prod-allowlist")
DEV_ALLOWLIST = policy_rel(".audit-allowlist")
DEPS_BLOCKLIST = policy_rel(".deps-upgrade-blocklist")

# `npm install -g npm@11.17.0` (audit.sh:387). Pinned in the twin, pinned here;
# see the BLOCKER above it about npm 10's Sigstore client.
NPM_PIN = "npm@11.17.0"

# `while ((audit_sig_attempt < 3))` and `sleep 10` (audit.sh:394-404).
SIGNATURE_ATTEMPTS = 3
SIGNATURE_RETRY_SLEEP = "10"

# `xargs -P 8` (audit.sh:125). Eight concurrent `gh api` calls.
FETCH_PARALLELISM = 8

# The GHSA shape `[[ "$url" =~ (GHSA-...) ]]` looks for, lower-case only exactly
# as the twin spells it: a capital-letter GHSA slug does not match on either side, and neither side invents one.
GHSA_RE = re.compile(r"(GHSA-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)")

# `date -u -d "$t" +%s` / `date -u -d "@$epoch" +%Y-%m-%d`. Spawned rather than re-implemented: GNU date's parser accepts far more than ISO 8601 and a Python approximation would disagree with the twin on exactly the malformed input that matters. Same argument `release-age.sh:31` makes when it calls the round-up GNU-only.
DATE_BIN = "date"


class Die(Exception):  # noqa: N818 -- not an Error; it is bash's `set -e`, named for it
    """A `set -e` death: a plain command failed and bash exited with its status.

    NOT an error type of this gate. It is the twin's control flow made explicit, because Python has no `set -e` and the alternative -- returning a status from every helper and checking it -- is how a port loses one of them. `main` catches it and returns the status, which is what bash would have exited with.

    Every raise site names the twin's line number, so a reader can check the claim that the failure is unguarded there.
    """

    def __init__(self, status: int) -> None:
        super().__init__("set -e: exit %d" % status)
        self.status = status


# --------------------------------------------------------------------------- bash and jq primitives ---------------------------------------------------------------------------


def _flush() -> None:
    """stdout and stderr before every spawn that inherits them.

    Bash writes each `echo` with a syscall; Python buffers a pipe. Without this the child's output overtakes the `log_info` line that announced it, and the differential reports a reordering that exists only in the buffering.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _bash_reason(exc: OSError) -> str:
    """bash's wording for the two ways an exec fails."""
    if isinstance(exc, PermissionError):
        return "Permission denied"
    return "command not found"


def spawn(
    argv: list[str], *, line: int | None, err_to_stdout: bool = False, **kwargs
) -> subprocess.CompletedProcess:
    """One external command, with bash's missing-binary behaviour.

    Returns a CompletedProcess whose returncode is 127 (or 126) when the binary could not be executed, which is what the shell would have handed back.

    `err_to_stdout` is for the ONE call site the twin writes as `npm audit signatures 2>&1`: the redirection is applied in the forked child BEFORE the failed exec, so bash's own `command not found` follows the redirection onto stdout. Printing it to stderr instead would be a one-line-on-the-wrong-stream difference of exactly the kind `differential.py` refuses to merge away.
    """
    _flush()
    try:
        return subprocess.run(argv, check=False, **kwargs)
    except OSError as exc:
        if line is not None:
            print(
                "%s: line %d: %s: %s" % (sys.argv[0], line, argv[0], _bash_reason(exc)),
                file=sys.stdout if err_to_stdout else sys.stderr,
                flush=True,
            )
        return subprocess.CompletedProcess(argv, 126 if isinstance(exc, PermissionError) else 127)


def capture(argv: list[str], *, line: int | None, quiet_err: bool) -> tuple[str, int]:
    """`$(cmd)`: stdout with EVERY trailing newline stripped, plus the status.

    `quiet_err` is the call site's `2>/dev/null`, and it also decides whether bash's own `command not found` is visible: bash writes that diagnostic in the forked child AFTER the redirections are applied, so the call site's own `2>/dev/null` eats it. Reproducing that silence matters more than the message, because a port that starts printing where the twin was quiet fails the
    differential on a line nobody asked for.
    """
    _flush()
    try:
        proc = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet_err else None,
            text=True,
        )
    except OSError as exc:
        if line is not None and not quiet_err:
            print(
                "%s: line %d: %s: %s" % (sys.argv[0], line, argv[0], _bash_reason(exc)),
                file=sys.stderr,
                flush=True,
            )
        return "", 126 if isinstance(exc, PermissionError) else 127
    return proc.stdout.rstrip("\n"), proc.returncode


def bash_read_fields(line: str, count: int) -> list[str]:
    """`IFS=$'\\t' read -r a b c ...` over one line. See DEFECT 3.

    TAB IS IFS WHITESPACE, so this is NOT `line.split("\\t")`: leading and trailing tabs are stripped, runs of tabs delimit ONCE, and the last variable absorbs the remainder including any tabs inside it. Measured:

        $ IFS=$'\\t' read -r a b c <<< $'\\t1.2.3\\tdesc'
        a=[1.2.3] b=[desc] c=[]

    Missing fields are the empty string, which is what an unset `read` variable holds.
    """
    body = line.strip("\t")
    fields = [part for part in body.split("\t") if part != ""] if body else []
    # The last variable takes the rest, tabs and all. Rebuilding it from the ORIGINAL text rather than from the split parts is the only way to keep an interior run of tabs that belongs to the final field.
    if len(fields) > count:
        head = fields[: count - 1]
        rest = body
        for part in head:
            rest = rest[rest.index(part) + len(part) :].lstrip("\t")
        fields = [*head, rest]
    return [*fields, *([""] * (count - len(fields)))]


def tsv(fields: list[object]) -> str:
    """jq's `@tsv` for one row: null is empty, and four characters escape."""
    out = []
    for field in fields:
        if field is None:
            out.append("")
            continue
        text = field if isinstance(field, str) else jq_tostring(field)
        out.append(
            text.replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
    return "\t".join(out)


def jq_tostring(value: object) -> str:
    """How jq -r renders one value: strings raw, everything else as JSON.

    Integral floats print without a fractional part, which is jq's number formatting and NOT Python's: `json.dumps(10.0)` is `10.0` and jq prints `10`.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def jq_print(value: object) -> str:
    """How jq WITHOUT `-r` renders one value: a string keeps its quotes.

    Used for `jq '.metadata.vulnerabilities.total // 0'`, which the twin does not pass `-r`. Unreachable for a well-formed report, where the field is a number, and kept distinct anyway because `"10"` and `10` are different bytes in the `Allowed production vulnerabilities:` line.
    """
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return jq_tostring(value)


class JqError(Exception):
    """A jq RUNTIME error: the message jq writes and the exit 5 it returns.

    Carries the rendered message WITHOUT the `jq: error (at file:line): ` prefix, because the prefix needs the document's end line and that is known only where the document was read.
    """


def jq_type(value: object) -> str:
    """jq's `type`."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def jq_render(value: object) -> str:
    """The compact form jq puts in parentheses inside an error message."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def jq_iterate(value: object) -> list:
    """`.[]`. Objects yield VALUES, arrays yield elements, anything else errors."""
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return list(value)
    raise JqError("Cannot iterate over %s (%s)" % (jq_type(value), jq_render(value)))


def jq_index(value: object, key: str) -> object:
    """`.key`. null indexes to null; a non-object of any other type errors."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    raise JqError('Cannot index %s with string "%s"' % (jq_type(value), key))


def jq_alt(value: object, default: object) -> object:
    """jq's `//`. ONLY `null` and `false` are absent; `0` and `""` are not."""
    return default if value is None or value is False else value


def jq_index0(value: object) -> object:
    """`.[0]`. null stays null, an array indexes, EVERYTHING ELSE ERRORS.

    Split out from `jq_index` because an OBJECT is the interesting case: `.[0]`
    on `{"a":1}` is `Cannot index object with number`, not the object's first
    value. A port that reused the iterator here would silently succeed where jq fails, and the caller silences jq's stderr, so nobody would ever see it.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    raise JqError("Cannot index %s with number" % jq_type(value))


def jq_to_entries(value: object) -> list[tuple[str, object]]:
    """`to_entries`. The error wording differs from `.[]`'s; both are measured."""
    if isinstance(value, dict):
        return list(value.items())
    raise JqError("%s (%s) has no keys" % (jq_type(value), jq_render(value)))


def jq_sort_key(value: object) -> tuple:
    """jq's total order, far enough to sort advisory source ids.

    null < false < true < numbers < strings < arrays < objects. Only the number and string rungs are reachable from `.via[].source`; the rest are ordered so a surprising document sorts deterministically instead of raising.
    """
    if value is None:
        return (0,)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, list):
        return (4, jq_render(value))
    return (5, jq_render(value))


def jq_error(path: str, end_line: int, message: str) -> str:
    """`jq: error (at <file>:<line>): <message>`.

    THE LINE IS WHERE THE DOCUMENT ENDS, not where the fault is. Measured against jq 1.8.1 over a five-line object: the error names line 5. That is why `documents()` returns the end line with every value.
    """
    return "jq: error (at %s:%d): %s" % (path, end_line, message)


def documents(path: str) -> list[tuple[object, int]]:
    """Every JSON value in a file, with the line each one ENDS on.

    jq reads a STREAM of values, not one document, which is why `jq empty` on a zero-byte file succeeds (DEFECT 1) and why a file holding two objects makes every later filter print two lines. Raises ValueError for text jq would reject, which is the only distinction `jq empty`'s caller needs.

    BOUNDARY, STATED: Python's parser accepts `NaN` and `Infinity`, which jq rejects. No `npm audit --json` output contains either, and no test claims agreement there.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    out: list[tuple[object, int]] = []
    index = 0
    while True:
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index >= len(text):
            return out
        value, end = decoder.raw_decode(text, index)
        out.append((value, text.count("\n", 0, end) + 1))
        index = end


def jq_empty(path: str) -> bool:
    """`jq empty "$file"`. True when jq would exit 0.

    AN EMPTY FILE IS TRUE. That is DEFECT 1, and it is reproduced rather than tightened: this function answers what jq answers.
    """
    try:
        documents(path)
    except (ValueError, OSError, UnicodeDecodeError):
        return False
    return True


# --------------------------------------------------------------------------- the twin's jq programs, one function each ---------------------------------------------------------------------------


def program_advisories(document: object) -> list[str]:
    """`[.vulnerabilities[].via[] | select(type=="object") | .source] | unique | .[]`."""
    sources: list[object] = []
    for entry in jq_iterate(jq_index(document, "vulnerabilities")):
        sources.extend(
            jq_index(via, "source")
            for via in jq_iterate(jq_index(entry, "via"))
            if isinstance(via, dict)
        )
    unique: list[object] = []
    for value in sorted(sources, key=jq_sort_key):
        if not unique or jq_sort_key(unique[-1]) != jq_sort_key(value):
            unique.append(value)
    return [jq_tostring(value) for value in unique]


def program_advisory_map(document: object) -> list[str]:
    """The `unique_by(.source) | @tsv` program at audit.sh:100-104.

    `unique_by` is `[group_by(f)[] | .[0]]`: sorted by the key, one row per distinct key, and the row kept is the FIRST in input order among equals -- which is why two `via` objects sharing a source (npm emits exactly that for a vulnerability reached through two packages) contribute one row and it is the earlier one.
    """
    rows: list[dict] = []
    for _key, entry in jq_to_entries(jq_index(document, "vulnerabilities")):
        rows.extend(
            {
                "source": jq_index(via, "source"),
                "url": jq_index(via, "url"),
                "title": jq_index(via, "title"),
                "severity": jq_index(via, "severity"),
            }
            for via in jq_iterate(jq_index(entry, "via"))
            if isinstance(via, dict)
        )
    picked: dict[tuple, dict] = {}
    for row in rows:
        key = jq_sort_key(row["source"])
        if key not in picked:
            picked[key] = row
    return [
        tsv([row["source"], row["severity"], row["url"], row["title"]])
        for key, row in sorted(picked.items(), key=lambda item: item[0])
    ]


def program_details(document: object) -> str:
    """The GHSA-detail program at audit.sh:144-149, as one `@tsv` row.

    The three `gsub`s are jq REGEX substitutions, so `\\n+` collapses a run of newlines to ONE space and `\\*\\*|##|\\`` deletes the three markdown noises. `.[0:240]` slices CODEPOINTS, which Python string slicing also does.
    """
    first = jq_index0(jq_index(document, "vulnerabilities"))
    vuln_range = jq_alt(jq_index(first, "vulnerable_version_range"), "")
    patched = jq_alt(jq_index(first, "first_patched_version"), "")
    description = jq_alt(jq_index(document, "description"), "")
    if not isinstance(description, str):
        description = jq_tostring(description)
    description = description.replace("\r", "")
    description = re.sub(r"\n+", " ", description)
    description = re.sub(r"\*\*|##|`", "", description)
    return tsv([vuln_range, patched, description[0:240]])


def program_fix_info(document: object, advisory_id: str) -> list[str]:
    """`get_advisory_fix_info`'s program, as the lines jq -c would print.

    `($id | tonumber)` is the one place a data-driven value reaches jq's arithmetic, and it is DEFECT 2: a non-numeric id raises here exactly as jq raises there.

    `select(.value.via[] | objects | select(.source == $n))` emits the entry ONCE
    PER MATCHING via object, because `select`'s condition is a stream and `if` iterates it. An entry whose via list matches twice therefore prints twice, and `head -1` keeps the first -- so the duplicate is invisible unless the two rows differ, which they cannot, being the same entry.
    """
    try:
        number = float(advisory_id) if advisory_id.strip() else None
        if number is None:
            raise ValueError(advisory_id)
    except ValueError:
        raise JqError('string ("%s") cannot be parsed as a number' % advisory_id) from None
    out = []
    for key, entry in jq_to_entries(jq_index(document, "vulnerabilities")):
        matches = 0
        for via in jq_iterate(jq_index(entry, "via")):
            if isinstance(via, dict) and _jq_equal(jq_index(via, "source"), number):
                matches += 1
        if not matches:
            continue
        fix = jq_index(entry, "fixAvailable")
        fix_type = jq_type(fix)
        record = {
            "pkg": key,
            "fixType": fix_type,
            "fixValue": jq_tostring(fix) if fix_type == "boolean" else None,
            "isMajor": (
                jq_tostring(jq_index(fix, "isSemVerMajor")) if fix_type == "object" else None
            ),
            "fixVersion": jq_index(fix, "version") if fix_type == "object" else None,
            "fixName": jq_index(fix, "name") if fix_type == "object" else None,
        }
        out.extend([json.dumps(record, separators=(",", ":"), ensure_ascii=False)] * matches)
    return out


def _jq_equal(value: object, number: float) -> bool:
    """jq's `==` between a `.source` and the number `tonumber` produced.

    `true == 1` is FALSE in jq, so a boolean source never matches; Python's
    `True == 1` is true, which is why the type is checked before the value.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return float(value) == number


# --------------------------------------------------------------------------- the gate ---------------------------------------------------------------------------


class Audit:
    """One run. The twin's shell globals, scoped to an object.

    ONE INSTANCE PER PROCESS in production, exactly as the twin has one shell, and a fresh one per test -- which is the capability bash cannot offer and the reason a second case cannot inherit the first's advisory map.
    """

    def __init__(self) -> None:
        # `declare -A ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA` plus the three enriched tables, held in the shape `core.advisory` reads them.
        self.adv = advisory.Advisories()
        # ADV_GHSA is read back by name (`"${ADV_GHSA[@]}"`, `"${!ADV_GHSA[@]}"`)
        # rather than only written, so it needs its own dict as well as its cell in the emitter's table.
        self.ghsa: dict[str, str] = {}
        # `DEFER_REASON`, a global the twin sets as an out-parameter.
        self.defer_reason = ""
        # `local stale_actionable=false` in main, written by check_stale_entries
        # through bash's dynamic scoping.
        self.stale_actionable = False
        # The freshness delegate. ONE instance for the process, matching the twin's shell-lifetime memo; see the module docstring's divergence list.
        self.release = release_age.ReleaseAge()

    # -- emission ----------------------------------------------------------

    def emit(self, level: str, ident: str, name: str, fix: str, action: str = "") -> None:
        """`emit_advisory`, bound to this run's metadata tables."""
        advisory.emit_advisory(level, ident, name, fix, action, advisories=self.adv)

    # -- audit plumbing ----------------------------------------------------

    def run_audit(self, output: str, *args: str) -> None:
        """`run_audit <output> [npm args...]` (audit.sh:57-77).

        The redirection happens BEFORE the exec, so a missing or exploding npm still leaves a zero-byte file behind -- which `jq empty` then accepts. That is DEFECT 1's delivery mechanism and it is reproduced by opening the file for writing before spawning.
        """
        with open(output, "w", encoding="utf-8") as handle:
            proc = spawn(["npm", "audit", "--json", *args], line=61, stdout=handle)
        audit_exit = proc.returncode

        if not jq_empty(output):
            # A KILLED AUDIT IS NOT A REGISTRY PROBLEM. 128+n means a signal, and the twin's older wording sent the reader to the network when the cause was a local timeout or OOM.
            if 128 < audit_exit < 160:
                advisory.log_error(
                    "npm audit was KILLED by signal %d (raw %d) before it finished writing JSON"
                    % (audit_exit - 128, audit_exit)
                )
                advisory.log_error(
                    "This is a local kill (timeout or OOM), NOT a registry or network fault"
                )
            else:
                advisory.log_error(
                    "npm audit failed to produce valid JSON (exit code: %d)" % audit_exit
                )
                advisory.log_error("This may indicate a network error or npm registry issue")
            raise Die(1)

    def get_advisories(self, path: str) -> list[str]:
        """`get_advisories` (audit.sh:80-82). Empty on ANY failure.

        `2>/dev/null || echo ""` means a jq runtime error produces one empty line on stdout, and the caller's `for advisory in $list` then iterates zero times -- indistinguishable from the empty-list success. Returning `[]` here is that same nothing, without inventing a blank word.

        THE RESULT IS WORD-SPLIT, not line-split, because both call sites are `for advisory in $prod_advisories_list` with the variable UNQUOTED. For the numeric ids npm emits the two are the same list; for a `.source` that was a string with a space in it they are not, and bash would see two advisories where the file has one. Reproduced rather than tidied.

        BOUNDARY, STATED: a MULTI-DOCUMENT report where one document errors and another does not. jq prints the good document's lines and still exits 0 (measured on jq 1.8.1), while this returns nothing for the whole file. `npm audit --json` writes exactly one document, and no test claims agreement there.
        """
        try:
            out: list[str] = []
            for document, _line in documents(path):
                out.extend(program_advisories(document))
            return "\n".join(out).split()
        except (JqError, ValueError, OSError, UnicodeDecodeError):
            return []

    def build_advisory_map(self, audit_json: str) -> None:
        """`build_advisory_map` (audit.sh:87-107).

        The jq here is NOT silenced and its failure is NOT fatal: it feeds the loop through a process substitution, so bash discards the status and the run continues with whatever the loop managed to read. See DEFECT 5.
        """
        lines: list[str] = []
        try:
            for document, end_line in documents(audit_json):
                try:
                    lines.extend(program_advisory_map(document))
                except JqError as exc:
                    # jq CONTINUES with the next input value after a runtime error rather than aborting the program; measured on jq 1.8.1 with a two-document file whose first document errored and whose second still printed.
                    print(jq_error(audit_json, end_line, str(exc)), file=sys.stderr, flush=True)
                    continue
        except (ValueError, OSError, UnicodeDecodeError):
            # `jq empty` already accepted this file, so a parse failure here means it changed underneath the run. The twin would print jq's parse diagnostic; both sides then read zero rows.
            lines = []

        for raw in lines:
            source, severity, url, title = bash_read_fields(raw, 4)
            # `[[ -z "$source" ]] && continue`: a row whose first field collapsed away is dropped rather than keyed on the empty string.
            if not source:
                continue
            self.adv.set("url", source, url)
            self.adv.set("title", source, title)
            self.adv.set("severity", source, severity)
            match = GHSA_RE.search(url)
            self.ghsa[source] = match.group(1) if match else ""
            self.adv.set("ghsa", source, self.ghsa[source])

        self.fetch_advisory_details_parallel()

    def fetch_advisory_details_parallel(self) -> None:
        """`fetch_advisory_details_parallel` (audit.sh:112-134).

        THE QUEUE IS NOT DEDUPLICATED, and that is the twin: the `-f` cache test runs over every value BEFORE any fetch starts, so two advisory ids sharing one GHSA (npm emits that whenever the same CVE is reached through two packages) queue the SAME slug twice and two `gh api` calls race to write the same file. Harmless, because both write the same bytes, and reproduced because
        the call log is part of what the differential compares.
        """
        os.makedirs(ADVISORY_CACHE_DIR, exist_ok=True)
        queue = []
        for slug in self.ghsa.values():
            if not slug:
                continue
            if os.path.isfile(os.path.join(ADVISORY_CACHE_DIR, "%s.json" % slug)):
                continue
            queue.append(slug)
        if not queue:
            self.load_advisory_details()
            return

        _flush()
        with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_PARALLELISM) as pool:
            list(pool.map(self._fetch_one, queue))

        self.load_advisory_details()

    def _fetch_one(self, slug: str) -> None:
        """One `xargs` worker: `gh api /advisories/<slug>`, `{}` on any failure.

        BOTH STREAMS ARE REDIRECTED at the twin's call site, so a missing `gh` binary is silent and lands in the same fallback as an HTTP 404 or a rate limit. That is the shape the gate header's BLOCKER is about: without GH_TOKEN the anonymous 60/hr limit turns most of these into the fallback.

        THE FALLBACK WRITES THE SLUG, NOT `{}`, AND THAT IS NOT A TYPO HERE. It
        is DEFECT 6: `xargs -I {}` rewrites the `{}` inside the worker script's
        own text, so `echo "{}" > "$out"` is `echo "<slug>" > "$out"` by the time
        bash sees it. The file is then not JSON, and `load_advisory_details`
        dies on it. Writing `{}` here would be a fix, and a fix here would make
        this port pass where the live gate fails.
        """
        out = os.path.join(ADVISORY_CACHE_DIR, "%s.json" % slug)
        try:
            with open(out, "w", encoding="utf-8") as handle:
                proc = subprocess.run(
                    ["gh", "api", "/advisories/%s" % slug],
                    check=False,
                    stdout=handle,
                    stderr=subprocess.DEVNULL,
                )
            failed = proc.returncode != 0
        except OSError:
            failed = True
        if failed:
            pathlib.Path(out).write_text("%s\n" % slug, encoding="utf-8")

    def load_advisory_details(self) -> None:
        """`load_advisory_details` (audit.sh:137-153).

        Reads three fields out of one `@tsv` row with the collapsing `read` of DEFECT 3, so an advisory whose vulnerable range is empty prints its patched version as the range.
        """
        for source, slug in list(self.ghsa.items()):
            if not slug:
                continue
            cache = os.path.join(ADVISORY_CACHE_DIR, "%s.json" % slug)
            if not os.path.isfile(cache):
                continue
            try:
                rendered = [program_details(document) for document, _ in documents(cache)]
                details = "\n".join(rendered)
            except (JqError, ValueError, OSError, UnicodeDecodeError) as exc:
                # THE UNGUARDED ASSIGNMENT, AND THE SECOND HALF OF DEFECT 6.
                # `details=$(jq -r '...' "$cache" 2>/dev/null)` is a plain
                # command in a function reached plainly from `main`, so jq's exit 5 IS the gate's exit 5. The `2>/dev/null` means nothing is printed, on either stream, about why.
                raise Die(5) from exc
            # `<<<"$details"` feeds `read` one line: the FIRST. A cache file holding two documents therefore contributes only its first row.
            first = details.split("\n")[0] if details else ""
            vuln_range, patched, desc = bash_read_fields(first, 3)
            self.adv.set("range", source, vuln_range)
            self.adv.set("patched", source, patched)
            self.adv.set("desc", source, desc)

    def get_advisory_fix_info(self, advisory_id: str, audit_json: str) -> dict | None:
        """`get_advisory_fix_info` (audit.sh:183-205). None when jq printed nothing.

        RAISES `Die(5)` FOR A NON-NUMERIC ID, which is DEFECT 2: jq exits 5, `pipefail` promotes it through `head -1`, and the caller decides whether `set -e` is live. `should_defer_advisory` catches it (the twin is inside an `if`); `check_stale_entries` does not (the twin is not).
        """
        try:
            for document, _line in documents(audit_json):
                rows = program_fix_info(document, advisory_id)
                if rows:
                    return json.loads(rows[0])
            return None
        except JqError:
            raise Die(5) from None
        except (ValueError, OSError, UnicodeDecodeError):
            return None

    # -- deferral ----------------------------------------------------------

    def deps_blocklist_has(self, pkg: str) -> bool:
        """`deps_blocklist_has` (audit.sh:220-224).

        `grep -qE "^${pkg//./\\.}([[:space:]]|$)"`: dots are escaped and NOTHING
        else is, so a package name carrying a regex metacharacter is matched as a
        pattern on both sides. `[[:space:]]` is the POSIX class, which for a one-line-at-a-time grep means space or tab (the newline is not part of the line).
        """
        if not pkg or not os.path.isfile(DEPS_BLOCKLIST):
            return False
        pattern = re.compile("^%s([ \t\v\f\r]|$)" % pkg.replace(".", "\\."))
        try:
            text = pathlib.Path(DEPS_BLOCKLIST).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        return any(pattern.search(line) for line in text.splitlines())

    def version_publish_epoch(self, pkg: str, version: str) -> str:
        """`version_publish_epoch` (audit.sh:229-239). Empty string on failure.

        An empty `version` asks for `.modified`, the package's most recent publish, which the twin uses as a proxy for the in-range patch behind a `fixAvailable: true`.
        """
        times, status = capture(["npm", "view", pkg, "time", "--json"], line=None, quiet_err=True)
        if status != 0:
            return ""
        try:
            document = json.loads(times) if times.strip() else None
        except ValueError:
            return ""
        stamp: object = None
        if isinstance(document, dict):
            stamp = document.get(version) if version else document.get("modified")
        if stamp is None or stamp == "":
            return ""
        text = stamp if isinstance(stamp, str) else jq_tostring(stamp)
        epoch, status = capture([DATE_BIN, "-u", "-d", text, "+%s"], line=None, quiet_err=True)
        if status != 0:
            return ""
        return epoch

    def should_defer_advisory(self, advisory_id: str, audit_json: str) -> bool:
        """`should_defer_advisory` (audit.sh:243-276). Sets `defer_reason`.

        `set -e` IS SUSPENDED FOR THIS WHOLE FUNCTION in the twin, because both call sites are `if should_defer_advisory ...`. The `Die` that `get_advisory_fix_info` raises for a non-numeric id is therefore caught here and turned back into "no info", which is what bash does with the failed assignment.
        """
        self.defer_reason = ""
        try:
            info = self.get_advisory_fix_info(advisory_id, audit_json)
        except Die:
            info = None
        if not info:
            return False
        fix_type = _field(info, "fixType")
        fix_version = _field(info, "fixVersion", empty=True)
        fix_name = _field(info, "fixName", empty=True)
        fix_value = _field(info, "fixValue", default="null")
        pkg = _field(info, "pkg", empty=True)
        fix_pkg = fix_name or pkg

        # Condition B: the only fix moves a package we deliberately hold back.
        if self.deps_blocklist_has(fix_pkg):
            self.defer_reason = "fix requires %s%s, held in %s" % (
                fix_pkg,
                "@%s" % fix_version if fix_version else "",
                DEPS_BLOCKLIST,
            )
            return True

        # Condition A: the fix version is still inside the freshness window.
        epoch = ""
        if fix_type == "object" and fix_version:
            epoch = self.version_publish_epoch(fix_pkg, fix_version)
        elif fix_type == "boolean" and fix_value == "true":
            epoch = self.version_publish_epoch(pkg, "")
        if epoch and self.release.is_release_deferred(epoch):
            when, _status = capture(
                [DATE_BIN, "-u", "-d", "@%s" % epoch, "+%Y-%m-%d"], line=272, quiet_err=False
            )
            self.defer_reason = (
                "fix published %s, within freshness window %s deferred until next UTC day"
                % (when, EM)
            )
            return True
        return False

    # -- the three passes --------------------------------------------------

    def check_stale_entries(
        self, allowlist_file: str, audit_json: str, allowed: dict, blocker: dict
    ) -> None:
        """`check_stale_entries` (audit.sh:281-331).

        THE ZERO-VULNERABILITY GUARD IS THE INTERESTING PART. With no vulnerabilities in the report the function says NOTHING about a missing advisory, because a genuinely clean tree and an audit that returned nothing useful look identical from here -- and condemning every entry at once on the second is how a whole allowlist gets deleted for an outage.
        """
        total_vulns = "0"
        try:
            rendered = []
            for document, _line in documents(audit_json):
                rendered.append(jq_tostring(_jq_length(jq_index(document, "vulnerabilities"))))
            total_vulns = "\n".join(rendered)
        except (JqError, ValueError, OSError, UnicodeDecodeError):
            total_vulns = "0"

        for advisory_id in list(allowed):
            info = self.get_advisory_fix_info(advisory_id, audit_json)
            if not info:
                # The COMMON form of staleness: the advisory is gone from the report entirely. This branch used to `continue` in silence, which is how 101 dead entries accumulated across the two lists.
                if _arith_gt(total_vulns, 0):
                    advisory.log_error(
                        "Stale allowlist entry: %s does not appear in %s"
                        % (advisory_id, audit_json)
                    )
                    advisory.log_error(
                        "  The advisory no longer fires %s delete %s (and its comment group if "
                        "it is the last id) from %s" % (EM, advisory_id, allowlist_file)
                    )
                    self.stale_actionable = True
                continue

            fix_type = _field(info, "fixType")
            is_major = _field(info, "isMajor", default="null")
            fix_version = _field(info, "fixVersion", empty=True)
            fix_value = _field(info, "fixValue", default="null")
            # A BARE `.pkg`, with no `//` fallback: jq -r prints `null` for a missing key, and that word would reach the advisory header.
            pkg = _field(info, "pkg", default="null")

            if fix_type == "boolean" and fix_value == "false":
                continue

            hint = describe_fix(fix_type, is_major, fix_version, fix_value)

            if blocker.get(advisory_id):
                self.emit(
                    "warn",
                    advisory_id,
                    pkg,
                    "%s %s BLOCKED: %s" % (hint, EM, blocker[advisory_id]),
                )
            else:
                self.emit(
                    "error",
                    advisory_id,
                    pkg,
                    hint,
                    "take the fix OR add '# BLOCKER: <reason>' above %s in %s"
                    % (advisory_id, allowlist_file),
                )
                self.stale_actionable = True

    def check_entry_age(self, file: str, entry: str, ident: str, name: str = "") -> bool:
        """`check_entry_age` (age-check.sh:107-127). False only for `error`.

        The twin shells out to `python3 -m rediacc_ci.core.age verdict` and reads a TAB-separated line back; this calls the same function. The two window values are read from the environment AT THE CALL SITE, because
        `age-check.sh` resolves `${AGE_WARN_DAYS:-180}` when it is sourced and an
        empty value means the default there too.
        """
        name = name or ident
        try:
            warn_days = int(os.environ.get("AGE_WARN_DAYS") or age.DEFAULT_WARN_DAYS)
            fail_days = int(os.environ.get("AGE_FAIL_DAYS") or age.DEFAULT_FAIL_DAYS)
        except ValueError:
            # A NON-INTEGER WINDOW IS A REFUSAL ON BOTH SIDES, WITH DIFFERENT BYTES, AND THAT IS SAID HERE RATHER THAN DISCOVERED. The twin runs the verdict in a SUBPROCESS, so `int("later")` there is a Python traceback on stderr, an exit 1, an empty line read back, and then the shim's own `unreadable verdict` refusal. This side cannot produce the traceback; it produces the refusal
            # and the same
            # `age_fail=1`, so the exit code and the loop behaviour match and
            # the stderr text does not. No differential case claims otherwise.
            print(
                "age-check.sh: unreadable verdict '' for %s/%s" % (file, entry),
                file=sys.stderr,
                flush=True,
            )
            return False
        in_ci = os.environ.get("CI", "") == "true"
        result = age.verdict(age.entry_age_days(file, entry), warn_days, fail_days, in_ci)
        if result.level in ("error", "warn"):
            self.emit(result.level, ident, name, result.message, result.remedy)
        return not result.failed

    def clean_tuf_cache(self) -> None:
        """`clean_tuf_cache` (audit.sh:366-372).

        Some CI images ship a stale Sigstore TUF cache without the newer npm registry signing keys, and the only cure is deleting it before verification.
        """
        npm_cache, status = capture(["npm", "config", "get", "cache"], line=None, quiet_err=True)
        if status != 0:
            npm_cache = os.path.join(os.environ.get("HOME", ""), ".npm")
        tuf = os.path.join(npm_cache, "_tuf")
        if os.path.isdir(tuf):
            shutil.rmtree(tuf, ignore_errors=True)

    def main(self) -> int:
        """`main` (audit.sh:333-539). Returns what the twin would exit with."""
        os.chdir(paths.repo_root())

        # -- allowlists ----------------------------------------------------
        advisory.log_info("Parsing allowlists")
        try:
            prod = blocker_validator.parse_blockered_list(PROD_ALLOWLIST)
            dev = blocker_validator.parse_blockered_list(DEV_ALLOWLIST)
        except blocker_validator.BrokenReaderError:
            # The twin's `parse_blockered_list` returns 1 having said so, and the call is unguarded, so `set -e` ends the run right here.
            return 1

        blockers_ok = 0
        if not blocker_validator.verify_all_blockers(PROD_ALLOWLIST, prod.blocker):
            blockers_ok = 1
        if not blocker_validator.verify_all_blockers(DEV_ALLOWLIST, dev.blocker):
            blockers_ok = 1
        if blockers_ok != 0:
            advisory.log_error(
                "Allowlist entries must include a quality '# BLOCKER: <reason>' %s strict gate "
                "enforced" % EM
            )
            return 1

        # -- age rot -------------------------------------------------------
        advisory.log_info("Checking allowlist entry ages")
        age_fail = 0
        for ident in list(prod.allowed):
            if not self.check_entry_age(PROD_ALLOWLIST, ident, ident, "audit-prod-allowlist entry"):
                age_fail = 1
        for ident in list(dev.allowed):
            if not self.check_entry_age(DEV_ALLOWLIST, ident, ident, "audit-allowlist entry"):
                age_fail = 1
        if age_fail != 0:
            advisory.log_error(
                "Allowlist entries older than %s days must be re-reviewed %s strict age gate "
                "enforced" % (os.environ.get("AGE_FAIL_DAYS") or age.DEFAULT_FAIL_DAYS, EM)
            )
            return 1

        # -- pass 0: signatures --------------------------------------------
        version, _status = capture(["npm", "--version"], line=385, quiet_err=False)
        if not version.startswith("11."):
            advisory.log_warn("Upgrading npm to 11.x for Sigstore attestation key compatibility")
            proc = spawn(["npm", "install", "-g", NPM_PIN, "--no-audit", "--no-fund"], line=387)
            if proc.returncode != 0:
                raise Die(proc.returncode)

        advisory.log_info("Verifying package signatures and provenance")
        attempt = 0
        signatures_ok = False
        self.clean_tuf_cache()
        while attempt < SIGNATURE_ATTEMPTS and not signatures_ok:
            # `npm audit signatures 2>&1`: the child's stderr joins the SCRIPT's stdout, so everything npm says lands on one stream.
            proc = spawn(
                ["npm", "audit", "signatures"],
                line=395,
                err_to_stdout=True,
                stderr=subprocess.STDOUT,
            )
            if proc.returncode == 0:
                signatures_ok = True
                continue
            attempt += 1
            if attempt < SIGNATURE_ATTEMPTS:
                advisory.log_warn(
                    "npm audit signatures failed (attempt %d); clearing TUF cache and retrying"
                    % attempt
                )
                self.clean_tuf_cache()
                slept = spawn(["sleep", SIGNATURE_RETRY_SLEEP], line=403)
                if slept.returncode != 0:
                    raise Die(slept.returncode)
        if not signatures_ok:
            advisory.log_error(
                "npm audit signatures failed %s at least one installed package has an invalid "
                "signature or missing provenance" % EM
            )
            advisory.log_error(
                "This indicates registry tampering, a poisoned lockfile, or a downgrade attack "
                "%s do NOT allowlist" % EM
            )
            return 1

        # -- pass 1: production --------------------------------------------
        advisory.log_info("Auditing production dependencies (no allowlist for new advisories)")
        self.run_audit(PROD_REPORT, "--omit=dev")
        self.build_advisory_map(PROD_REPORT)

        prod_total = self._metadata(PROD_REPORT, "total")
        prod_high = self._metadata(PROD_REPORT, "high")
        prod_critical = self._metadata(PROD_REPORT, "critical")

        if _arith_gt(prod_total, 0):
            prod_unallowed = [
                advisory_id
                for advisory_id in self.get_advisories(PROD_REPORT)
                if not prod.allowed.get(advisory_id)
            ]

            if prod_unallowed:
                # Partition: defer what no `npm audit fix` could install today, fail the rest.
                prod_failing = []
                for advisory_id in prod_unallowed:
                    if self.should_defer_advisory(advisory_id, PROD_REPORT):
                        info = self.get_advisory_fix_info(advisory_id, PROD_REPORT)
                        pkg = _field(info or {}, "pkg", default="unknown")
                        self.emit(
                            "warn", advisory_id, pkg, "deferred %s %s" % (EM, self.defer_reason)
                        )
                    else:
                        prod_failing.append(advisory_id)

                if prod_failing:
                    advisory.ci_error(
                        "Production vulnerabilities: %s critical, %s high, %s total"
                        % (prod_critical, prod_high, prod_total)
                    )
                    for advisory_id in prod_failing:
                        self._emit_failure(advisory_id, PROD_REPORT, PROD_ALLOWLIST)
                    return 1
                advisory.ci_warn(
                    "Deferred %d production advisory(ies): fix not yet installable "
                    "(minimum-release-age) or held in %s" % (len(prod_unallowed), DEPS_BLOCKLIST)
                )
            advisory.ci_warn(
                "Allowed production vulnerabilities: %s (see %s)" % (prod_total, PROD_ALLOWLIST)
            )

        # DEFECT 4: unconditional, even after the warning above.
        advisory.log_success("No production vulnerabilities")

        # -- pass 2: everything --------------------------------------------
        advisory.log_info("Auditing all dependencies (allowlist for dev-only)")
        self.run_audit(ALL_REPORT)
        self.build_advisory_map(ALL_REPORT)

        all_critical = self._metadata(ALL_REPORT, "critical")
        all_high = self._metadata(ALL_REPORT, "high")

        prod_advisories = self.get_advisories(PROD_REPORT)
        all_advisories = self.get_advisories(ALL_REPORT)
        dev_only = [
            advisory_id for advisory_id in all_advisories if advisory_id not in prod_advisories
        ]
        unallowed = [advisory_id for advisory_id in dev_only if not dev.allowed.get(advisory_id)]

        if unallowed:
            dev_failing = []
            for advisory_id in unallowed:
                if self.should_defer_advisory(advisory_id, ALL_REPORT):
                    info = self.get_advisory_fix_info(advisory_id, ALL_REPORT)
                    pkg = _field(info or {}, "pkg", default="unknown")
                    self.emit("warn", advisory_id, pkg, "deferred %s %s" % (EM, self.defer_reason))
                else:
                    dev_failing.append(advisory_id)

            if dev_failing:
                advisory.ci_error(
                    "New dev vulnerabilities: %s critical, %s high" % (all_critical, all_high)
                )
                for advisory_id in dev_failing:
                    self._emit_failure(advisory_id, ALL_REPORT, DEV_ALLOWLIST)
                return 1
            advisory.ci_warn(
                "Deferred %d dev advisory(ies): fix not yet installable (minimum-release-age) "
                "or held in %s" % (len(unallowed), DEPS_BLOCKLIST)
            )

        if len(dev_only) > 0:
            advisory.ci_warn(
                "Allowed dev vulnerabilities: %d (see %s)" % (len(dev_only), DEV_ALLOWLIST)
            )

        # -- pass 3: the strict stale sweep --------------------------------
        advisory.log_info(
            "Checking allowlist entries against available fixes (strict, BLOCKER-gated)"
        )

        self.stale_actionable = False
        self.check_stale_entries(PROD_ALLOWLIST, PROD_REPORT, prod.allowed, prod.blocker)
        self.check_stale_entries(DEV_ALLOWLIST, ALL_REPORT, dev.allowed, dev.blocker)

        if self.stale_actionable:
            advisory.log_error(
                "Allowlist problems found %s see errors above: an entry either has an available "
                "fix without a BLOCKER annotation, or is stale (the advisory no longer fires and "
                "the entry should be deleted)" % EM
            )
            return 1

        advisory.log_success("Security audit passed")
        # Keep audit-report.json for ci-quality.yml artifact upload; clean sidecar only.
        with contextlib.suppress(OSError):
            os.remove(PROD_REPORT)
        return 0

    # -- helpers used only by main ----------------------------------------

    def _metadata(self, path: str, field: str) -> str:
        """`jq '.metadata.vulnerabilities.<field> // 0' <path>` (audit.sh:418-420).

        NOT SILENCED and NOT GUARDED in the twin, so a jq runtime error prints and kills the run through `set -e`. Multiple documents print multiple lines, which is why this returns the joined TEXT rather than a number: the twin keeps a string too, and hands it to bash arithmetic later.
        """
        out = []
        try:
            for document, end_line in documents(path):
                try:
                    metadata = jq_index(document, "metadata")
                    vulns = jq_index(metadata, "vulnerabilities")
                    value = jq_index(vulns, field)
                except JqError as exc:
                    print(jq_error(path, end_line, str(exc)), file=sys.stderr, flush=True)
                    raise Die(5) from None
                out.append(jq_print(jq_alt(value, 0)))
        except (ValueError, OSError, UnicodeDecodeError):
            raise Die(5) from None
        return "\n".join(out)

    def _emit_failure(self, advisory_id: str, audit_json: str, allowlist_file: str) -> None:
        """The failing-advisory block shared by pass 1 and pass 2."""
        info = self.get_advisory_fix_info(advisory_id, audit_json) or {}
        pkg = _field(info, "pkg", default="unknown")
        fix_type = _field(info, "fixType")
        is_major = _field(info, "isMajor", default="null")
        fix_version = _field(info, "fixVersion", empty=True)
        fix_value = _field(info, "fixValue", default="null")
        hint = describe_fix(fix_type, is_major, fix_version, fix_value)
        self.emit(
            "error",
            advisory_id,
            pkg,
            hint,
            "fix by upgrading/overriding the affected package, OR add '# BLOCKER: <reason>' "
            "above %s in %s" % (advisory_id, allowlist_file),
        )


def describe_fix(fix_type: str, is_major: str, fix_version: str, fix_value: str) -> str:
    """`describe_fix` (audit.sh:156-180). Pure, so the tests drive it directly.

    The four arms are the four shapes `fixAvailable` takes in `npm audit --json`: absent (null), a boolean, an object naming the upgrade, and -- the arm that exists because npm has changed this field's type before -- anything else.
    """
    if fix_type == "null":
        return "no fix information in npm audit output"
    if fix_type == "boolean":
        if fix_value == "true":
            return (
                "transitive fix path exists (try 'npm update <pkg>' or add a root overrides entry)"
            )
        return "no fix available upstream"
    if fix_type == "object":
        suffix = " (to %s)" % fix_version if fix_version else ""
        if is_major == "true":
            return "major upgrade required%s" % suffix
        return "non-breaking upgrade available%s" % suffix
    return "unknown fix type: %s" % fix_type


def _field(info: dict, name: str, *, default: str = "", empty: bool = False) -> str:
    """One `echo "$info" | jq -r '.<name> // <fallback>'`.

    `// empty` yields the empty string in a command substitution; `// "null"` yields the four characters `null`; a bare `.pkg` yields `null` on a missing key, because `jq -r` renders null as the word. The default is therefore spelled at every call site rather than guessed here.

    ONLY `null` AND `false` ARE ABSENT, which is jq's rule and not Python's: an EMPTY STRING is truthy in jq, so `"" // "unknown"` is the empty string. A port that used `or` here would print `unknown` for a package literally named the empty string, which is unreachable but is also not what the twin does.
    """
    value = info.get(name)
    if value is None or value is False:
        return "" if empty else default
    return value if isinstance(value, str) else jq_tostring(value)


def _jq_length(value: object) -> int:
    """`length`: null is 0, a collection is its size, a string is its codepoints."""
    if value is None:
        return 0
    if isinstance(value, (dict, list, str)):
        return len(value)
    raise JqError("%s (%s) has no length" % (jq_type(value), jq_render(value)))


def _arith_gt(text: str, floor: int) -> bool:
    """`[[ "$text" -gt <floor> ]]`, for the values jq can actually produce.

    THE EMPTY STRING IS ZERO. That is not a convenience: it is the mechanism of DEFECT 1, where an empty audit report makes `prod_total` empty and the gate concludes there are no vulnerabilities.

    BOUNDARY, STATED: bash would evaluate a non-numeric value as an ARITHMETIC EXPRESSION (a bare word is a variable name, `0x10` is 16). No jq output reaching this function can be either, and no test claims agreement there.
    """
    stripped = text.strip()
    if not stripped:
        return False
    try:
        return int(stripped) > floor
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    """`main "$@"`, which ignores its arguments exactly as the twin does."""
    del argv
    try:
        return Audit().main()
    except Die as death:
        return death.status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
