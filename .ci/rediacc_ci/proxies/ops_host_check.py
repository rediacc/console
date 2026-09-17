"""Port of `.ci/scripts/test/proxies/proxy-ops-host-check.sh`.

Local proxy for the `renet ops host check` leg of
`.github/workflows/ci-ops-test.yml`, wired as the registered gate
`check:ci-proxy-ops-host-check` (`package.json:389`).

WHY THE TWIN EXISTS AT ALL, kept because it is the finding.
`ci-ops-test.yml:573-575` is `run: $RENET_BINARY ops host check || true`, so
that step cannot fail on any platform for any reason, and the only real
assertion on the command's output in the whole workflow is Windows-only
(`ci-ops-test.yml:584-589`). On Linux and macOS the command's CONTRACT -- that
it emits parseable JSON with a populated check list at all -- has never been
asserted anywhere. This proxy asserts the SHAPE of the report and deliberately
NOT the health of the host; the per-status tally is PRINTED instead, so a
reader can see the composition and notice when it collapses.

-----------------------------------------------------------------------------
A jq ERROR USED TO BE FOLDED INTO "NO FINDINGS". FIXED 2026-09-10, BOTH SIDES
-----------------------------------------------------------------------------
`:93-108` computes every per-entry rule in ONE jq program. jq aborts the WHOLE
program on the first type error, prints nothing (or a truncated prefix) on
stdout and exits 5. The old code read

    bad="$(printf '%s' "$json" | jq -r '(.checks // []) | to_entries[] | ...'
           2>/dev/null)"
    [[ -n "$bad" ]] && findings+="$bad"

with the status UNREAD, so `$bad` was empty and that scored as "no per-entry
findings". The entire body of the contract this gate exists to assert
evaporated on exactly the malformed input it is meant to catch. Measured
against the twin's own `validate_report` BEFORE the fix:

    checks:[1,2,3]    -> RC=0, no findings   (should be: entries have no
                                              name/value/status)
    checks:"nope"     -> RC=0, no findings   (jq `length` of a 4-char string is
                                              4, so the empty-checks rule did
                                              not fire either, and `to_entries`
                                              on a string errored into silence)
    checks:[null]     -> RC=1, 3 findings    (jq's `null.name` is null, not an
                                              error, so this one case survived)

THE FIX: the status is read into `bad_rc`, jq's stderr is kept in a temp file
rather than sent to /dev/null, and a non-zero status becomes a NAMED refusal
carrying jq's own first diagnostic line -- never the empty finding set it used
to be read as. Partial stdout from a program that then aborted is DISCARDED
rather than reported as if it were the whole finding set. The same three
reports now measure:

    checks:[1,2,3]    -> RC=1, VACUOUS ... jq said: jq: error (at <stdin>:0):
                                 Cannot index number with string "name"
    checks:"nope"     -> RC=1, VACUOUS ... jq said: jq: error (at <stdin>:0):
                                 string ("nope") has no keys
    checks:[null]     -> RC=1, 3 findings    (UNCHANGED, and that is the
                                              must-not-fire direction)

jq's runtime-error status is 5 on jq-1.8.1, measured; `_bad_entries` raising
is rendered with that literal here because the twin interpolates whatever jq
returned. A jq that ever returned something else for a runtime error would
show up as a byte divergence in the differential, which is the right place for
it to show up.

BLAST RADIUS, measured not estimated. The subject is a Go binary and
`private/renet/cmd/renet/ops_host.go:29` declares `Checks []HostCheckResult`,
so `encoding/json` can only ever emit an array of objects or `null` -- and
`null` is handled correctly by `(.checks // [])`. Live paths today: ZERO, both
before and after. Override-reachable paths: ONE, `:172`'s
`RENET_BINARY="${RENET_BINARY:-...}"`, which is honoured with no validation of
what the binary is, so before the fix any other program's JSON was certified
by this gate. That override is the path the differential actually drives:
`test_proxies_ops_host_check.py::test_a_checks_array_of_non_objects_is_now_a_
named_refusal` and `::test_checks_as_a_string_is_now_a_named_refusal` point
`RENET_BINARY` at a shim, and
`::test_a_null_entry_is_still_read_field_by_field` is the must-NOT-fire
control beside them. The twin's own `--selftest` grew a tenth case for the
same reason.

-----------------------------------------------------------------------------
A SECOND, COSMETIC ONE: MULTIPLE CONTRACT VIOLATIONS RENDER AS ONE BULLET
-----------------------------------------------------------------------------
`:178` is `printf '  - %s\\n' "$FINDINGS"` -- QUOTED, so a multi-line
`$FINDINGS` becomes a single `  - ` bullet with raw newlines inside it, unlike
`proxy-go-unit.sh:92` which leaves the same construct unquoted on purpose.
Reproduced.

-----------------------------------------------------------------------------
jq SEMANTICS ARE IMPLEMENTED, NOT SHELLED OUT TO
-----------------------------------------------------------------------------
`jq` stays a declared REQUIREMENT (`:146`) because the twin needs it and the
preflight must still say cannot-run without it, but the validator's logic is
Python here, the same way the twin's `grep` pipelines are Python in the sibling
ports. That means jq's own rules are reproduced deliberately:

  * `a // b` yields `b` when `a` is null OR FALSE, which is why a check whose
    `.value` is the boolean `false` is reported as "has no value" (verified
    against the twin) while a `.value` of `0` is not.
  * `jq -r` prints a string raw and anything else as compact JSON, which is
    what `\\(...)` interpolation does too.
  * `length` is element count for an array, key count for an object, CHARACTER
    count for a string, 0 for null.
  * indexing a non-object non-null with a string is an error carrying the type
    name, and `:61-63` do NOT discard stderr, so those three diagnostics reach
    the proxy's stderr verbatim. `_jq_index` re-emits them byte for byte.

ONE NAMED DIVERGENCE, not reproduced: jq reads a STREAM of JSON values and
`json.loads` reads exactly one, so `{"a":1} {"b":2}` on the subject's stdout
would make the twin evaluate the pair and this port report "not parseable
JSON". Unreachable from a Go `json.Marshal`, which emits one document, and
pinned as still-real by
`test_proxies_ops_host_check.py::test_a_two_document_stream_is_the_one_named_
divergence`.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-ops-host-check.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import platform as _platform
import shutil
import subprocess
import sys
from typing import Any

from rediacc_ci.core import proxyx

DEFAULT_BINARY_REL = "private/renet/bin/renet"


class _JqError(Exception):
    """One jq runtime error. Carries the message jq itself would print."""


def _jq_type(value: Any) -> str:
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


def _jq_index(value: Any, key: str) -> Any:
    """`.<key>`: null passes through, an object looks up, anything else errors."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    raise _JqError(f'Cannot index {_jq_type(value)} with string "{key}"')


def _alt(value: Any, fallback: Any) -> Any:
    """`a // b`: the fallback when `a` is null OR false, not merely when absent."""
    if value is None or value is False:
        return fallback
    return value


def _jq_raw(value: Any) -> str:
    """`jq -r` / `\\(...)`: a string prints raw, anything else as compact JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _jq_err_repr(value: Any) -> str:
    r"""How jq renders a value INSIDE a diagnostic: always JSON, never raw.

    `Cannot iterate over string ("nope")` keeps the quotes, unlike `\(...)`
    interpolation which prints a string raw. Getting these two the same way
    round is a real byte difference and the ledger's variant 5 caught it.
    """
    return json.dumps(value, separators=(",", ":"))


def _jq_length(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise _JqError(f"{_jq_type(value)} ({_jq_err_repr(value)}) has no length")
    if isinstance(value, (list, dict, str)):
        return len(value)
    return abs(int(value))


def _jq_entries(value: Any) -> list[tuple[Any, Any]]:
    """`to_entries[]`. An array keys on the index, an object on the key string.

    The error wording is `to_entries`\' own and differs from `.[]`\'s, measured
    on jq-1.8.1: `printf \'"ab"\' | jq to_entries` says `string ("ab") has no
    keys` where `jq .[]` says `Cannot iterate over string ("ab")`. Both used to
    be invisible here because both sides discarded them; the fix of 2026-09-10
    puts this one in a FINDING, so the two wordings can no longer be conflated.
    """
    if isinstance(value, list):
        return list(enumerate(value))
    if isinstance(value, dict):
        return list(value.items())
    raise _JqError(f"{_jq_type(value)} ({_jq_err_repr(value)}) has no keys")


def _jq_iterate(value: Any) -> list[Any]:
    """`.[]`: an array yields its elements, an object its VALUES, else an error."""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    raise _JqError(f"Cannot iterate over {_jq_type(value)} ({_jq_err_repr(value)})")


def _jq_lineno(fed: str) -> int:
    """jq reports `<stdin>:N` where N is the NEWLINES it consumed, measured.

        printf '[1]'        | jq .platform  ->  <stdin>:0
        printf '[1]\n'      | jq .platform  ->  <stdin>:1
        printf '[\n  1\n]\n' | jq .platform  ->  <stdin>:3

    So the two call sites in the twin report DIFFERENT line numbers for the
    same document: `validate_report` is fed `printf '%s' "$json"` where
    `json="$(cat)"` has already stripped the trailing newline, while the tally
    block at `:183-192` reads `<"$OUT"` with the newline still on it.
    """
    return fed.count("\n")


def _bad_entries(checks: Any) -> list[str]:
    """`:93-101`, and it RAISES rather than returning silence.

    A `_JqError` anywhere in the walk aborts the whole program, exactly as jq
    does, and everything collected so far is discarded with it -- the twin
    discards its own partial stdout the same way. The caller turns the
    exception into a named finding; see this module's docstring for the hole
    that was.
    """
    out: list[str] = []
    for key, entry in _jq_entries(checks):
        k = _jq_raw(key)
        name = _alt(_jq_index(entry, "name"), "")
        value = _alt(_jq_index(entry, "value"), "")
        status = _alt(_jq_index(entry, "status"), "")
        hint = _alt(_jq_index(entry, "hint"), "")
        label = _jq_raw(_alt(_jq_index(entry, "name"), "?"))
        if name == "":
            out.append(f"checks[{k}] has no name")
        if value == "":
            out.append(f"checks[{k}] ({label}) has no value")
        if status == "":
            out.append(f"checks[{k}] ({label}) has no status")
        if status not in ("ok", "warn", "fail", ""):
            out.append(
                f'checks[{k}] ({label}) has unknown status "{_jq_raw(_jq_index(entry, "status"))}"'
            )
        if status in ("warn", "fail") and hint == "":
            out.append(
                f"checks[{k}] ({label}) is {_jq_raw(status)} with no hint; "
                "a failing probe must name its fix"
            )
    return out


def _bash_arith(text: str) -> int:
    """`[[ "$n" -eq 0 ]]` on a captured string: "" and non-numerals are 0."""
    try:
        return int(text)
    except ValueError:
        return 0


def validate_report(want_platform: str, report: str) -> tuple[str, int]:
    """The twin's pure `validate_report` (`:50-94`).

    Returns the findings it would print on STDOUT plus its return code. jq's
    own diagnostics go to stderr here, exactly as `:61-63` let them.
    """
    # `json="$(cat)"` strips the trailing newlines, which is also what makes
    # jq report `<stdin>:0` here where the tally block reports `<stdin>:1`.
    report = report.rstrip("\n")
    lineno = _jq_lineno(report)

    try:
        doc = json.loads(report)
    except (ValueError, RecursionError):
        return ("stdout is not parseable JSON", 1)
    # `jq -e .` exits non-zero when the last output is false or null.
    if doc is None or doc is False:
        return ("stdout is not parseable JSON", 1)

    findings: list[str] = []

    def _read(key: str) -> Any:
        try:
            return _jq_index(doc, key)
        except _JqError as exc:
            print(f"jq: error (at <stdin>:{lineno}): {exc}", file=sys.stderr)
            return "ERROR"

    raw_platform = _read("platform")
    raw_backend = _read("backend")
    raw_checks = _read("checks")

    # `$( )` of a jq run that errored captures the empty string.
    p_val = "" if raw_platform == "ERROR" else _jq_raw(_alt(raw_platform, ""))
    b_val = "" if raw_backend == "ERROR" else _jq_raw(_alt(raw_backend, ""))
    # The THIRD jq process is one program, `(.checks // []) | length`, so an index error and a length error both leave the capture empty.
    if raw_checks == "ERROR":
        n_text = ""
    else:
        try:
            n_text = str(_jq_length(_alt(raw_checks, [])))
        except _JqError as exc:
            print(f"jq: error (at <stdin>:{lineno}): {exc}", file=sys.stderr)
            n_text = ""

    if not p_val:
        findings.append(".platform is missing or empty")
    if want_platform and p_val and p_val != want_platform:
        findings.append(f'.platform is "{p_val}" but this host is "{want_platform}"')
    if not b_val:
        findings.append(".backend is missing or empty")

    # ZERO CHECKS IS A FAILURE, NEVER A PASS. An empty list would satisfy every per-entry rule below by matching nothing at all. (:71-75)
    if _bash_arith(n_text) == 0:
        findings.append(
            ".checks is empty; the report enumerated nothing, so its green would mean nothing"
        )

    # :93-108. A FOURTH jq PROCESS, and it re-derives `(.checks // [])` itself rather than reusing the length run's value -- so on a non-object document it fails with its OWN copy of the diagnostic, which lands INSIDE the finding instead of on stderr like the first three. A jq that could not FINISH is a named refusal, never a silence.
    try:
        findings.extend(_bad_entries(_alt(_jq_index(doc, "checks"), [])))
    except _JqError as exc:
        findings.append(
            "VACUOUS: the per-entry contract check could not run -- jq exited 5 on "
            "this report, so NOTHING about checks[].{name,value,status,hint} was "
            f"asserted. jq said: jq: error (at <stdin>:{lineno}): {exc}"
        )

    if findings:
        # `printf '%s' "$findings" | grep -v '^$'`
        return ("\n".join(line for line in findings if line != ""), 1)
    return ("", 0)


# --------------------------------------------------------------------------- The twin's own selftest (:96-130). BOTH directions, because a validator with only positive controls will happily accept anything. ---------------------------------------------------------------------------

_GOOD = (
    '{"platform":"linux","arch":"amd64","backend":"kvm","checks":'
    '[{"name":"a","value":"v","status":"ok"},'
    '{"name":"b","value":"v","status":"fail","hint":"do the thing"}]}'
)

SELFTEST_CASES: list[tuple[int, str, str]] = [
    # MUST NOT fire. A validator with only positive controls flags the whole tree.
    (0, "a well-formed report is accepted", _GOOD),
    (
        0,
        "a warn entry with a hint is accepted",
        '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"warn","hint":"h"}]}',
    ),
    # MUST fire.
    (1, "non-JSON stdout is rejected", "not json at all"),
    (1, "an empty .checks array is rejected", '{"platform":"linux","backend":"kvm","checks":[]}'),
    (
        1,
        "a missing .backend is rejected",
        '{"platform":"linux","checks":[{"name":"a","value":"v","status":"ok"}]}',
    ),
    (
        1,
        "a platform that disagrees with the host is rejected",
        '{"platform":"windows","backend":"hyperv","checks":[{"name":"a","value":"v","status":"ok"}]}',
    ),
    (
        1,
        "an unknown status word is rejected",
        '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"okish"}]}',
    ),
    (
        1,
        "a fail entry with no hint is rejected",
        '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"fail"}]}',
    ),
    (
        1,
        "an entry with no name is rejected",
        '{"platform":"linux","backend":"kvm","checks":[{"value":"v","status":"ok"}]}',
    ),
    # The regression control for the jq-abort hole closed on 2026-09-10: this
    # case used to be ACCEPTED, because the type error emptied the finding set.
    (
        1,
        "a checks entry that is not an object is rejected, not silently skipped",
        '{"platform":"linux","backend":"kvm","checks":[1]}',
    ),
]


def selftest(colour: bool) -> int:
    green = proxyx.GREEN if colour else ""
    red = proxyx.RED if colour else ""
    off = proxyx.OFF if colour else ""
    fails = 0
    for want, label, body in SELFTEST_CASES:
        # `>/dev/null 2>&1`: both streams of the validator are discarded here.
        try:
            _, rc = validate_report("linux", body)
        except _JqError:
            rc = 2
        if rc == want:
            print(f"{green}PASS:{off} selftest {label}")
        else:
            print(
                f"{red}FAIL:{off} selftest {label}: expected rc {want}, got {rc}", file=sys.stderr
            )
            fails += 1
    if fails > 0:
        print(
            f"proxy ops-host-check selftest: {fails} of {len(SELFTEST_CASES)} case(s) FAILED",
            file=sys.stderr,
        )
        return 1
    print(f"proxy ops-host-check selftest: {len(SELFTEST_CASES)} case(s) passed")
    return proxyx.run_selftest()


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:40-41)."""
    return pathlib.Path(__file__).resolve().parents[3]


def want_platform_for(uname_s: str) -> str:
    """`case "$(uname -s)"` (:150-155). An unrecognised kernel yields ""."""
    if uname_s == "Linux":
        return "linux"
    if uname_s == "Darwin":
        return "darwin"
    if uname_s.startswith(("MINGW", "MSYS", "CYGWIN")):
        return "windows"
    return ""


def run() -> int:
    root = _proxy_root()

    p = proxyx.Proxy(
        "ops-host-check",
        "renet ops host check --json (ci-ops-test.yml 'Test: renet ops host check')",
    )

    renet_bin = os.environ.get("RENET_BINARY") or str(root / DEFAULT_BINARY_REL)

    p.need_cmd("jq", "sudo apt-get install -y jq")
    p.need_exec(
        renet_bin, ".ci/scripts/infra/build-renet.sh, or export RENET_BINARY=/path/to/renet"
    )
    p.preflight()

    want = want_platform_for(_platform.uname().system)

    sys.stdout.flush()
    proc = subprocess.run(
        [renet_bin, "ops", "host", "check", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    rc = proc.returncode

    # CI writes `|| true` here. This proxy does not, which is the whole point.
    if rc == 0:
        p.ok("renet ops host check --json exited 0")
    else:
        p.bad(
            f"renet ops host check --json exited {rc} "
            "(CI masks this with '|| true'; this proxy does not)"
        )
        print("  --- stderr ---", file=sys.stderr)
        sys.stderr.write(proc.stderr)

    findings, _ = validate_report(want, proc.stdout)
    if not findings:
        p.ok(
            f"the report satisfies the JSON contract (.platform={want}, .backend, "
            ".checks[].{name,value,status,hint})"
        )
    else:
        p.bad("the report violates its JSON contract:")
        # QUOTED in the twin, so every finding shares ONE bullet. See docstring.
        print(f"  - {findings}", file=sys.stderr)

    # PRINT THE SHAPE, not just the verdict (:181-194).
    #
    # FOUR SEPARATE jq PROCESSES, and that is the whole reason this block is written out rather than computed once. Each one fails INDEPENDENTLY: against `checks:[1,2,3]` the `length` run succeeds and prints 3 while the
    # three `select(.status==...)` runs each abort on the first element, so the
    # twin emits three diagnostics and a line reading `3 probe(s) reported -- ok, warn, fail`. A port that computed the four numbers in one pass would print `0 ok, 0 warn, 0 fail` and no
    # diagnostics; that is exactly what the first draft of this file did, and
    # the ledger's variant 4 caught it.
    doc: Any = None
    parsed = False
    try:
        doc = json.loads(proc.stdout)
        parsed = not (doc is None or doc is False)
    except ValueError:
        parsed = False
    if parsed:
        lineno = _jq_lineno(proc.stdout)

        def _jq(compute) -> str:
            """One jq process: its value, or "" plus its diagnostic on stderr."""
            try:
                return str(compute())
            except _JqError as exc:
                print(f"jq: error (at <stdin>:{lineno}): {exc}", file=sys.stderr)
                return ""

        def _checks() -> Any:
            return _alt(_jq_index(doc, "checks"), [])

        def _tally(status: str):
            def inner() -> int:
                return sum(1 for c in _jq_iterate(_checks()) if _jq_index(c, "status") == status)

            return inner

        n = _jq(lambda: _jq_length(_checks()))
        ok_n = _jq(_tally("ok"))
        warn_n = _jq(_tally("warn"))
        fail_n = _jq(_tally("fail"))

        print(
            f"proxy ops-host-check: {n} probe(s) reported -- {ok_n} ok, {warn_n} warn, "
            f"{fail_n} fail on this host"
        )
        print("  (host health is deliberately NOT a verdict here; only the contract is)")
        # `[[ "$FAILN" -gt 0 ]]` on a possibly-empty capture: "" is 0.
        if _bash_arith(fail_n) > 0:
            print("  failing probes on this host, named so the debt is not forgotten:")
            try:
                for c in _jq_iterate(_checks()):
                    if _jq_index(c, "status") == "fail":
                        hint = _jq_raw(_alt(_jq_index(c, "hint"), "no hint"))
                        name = _jq_raw(_alt(_jq_index(c, "name"), None))
                        value = _jq_raw(_alt(_jq_index(c, "value"), None))
                        print(f"    - {name}: {value} -- {hint}")
            except _JqError as exc:
                print(f"jq: error (at <stdin>:{lineno}): {exc}", file=sys.stderr)

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        if shutil.which("jq") is None:
            print(
                "proxy ops-host-check: jq is not on PATH, the selftest cannot run", file=sys.stderr
            )
            print("  fix: sudo apt-get install -y jq", file=sys.stderr)
            return 77
        return selftest(sys.stdout.isatty())
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
