#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/profiler/panel.sh`.

Turn a sampler TSV into the job's summary panel and decide whether a degenerate profile is a warning or a failure. The aggregation itself stays in `.ci/scripts/ci/profiler/report.awk` and is INVOKED here exactly as the twin invokes it: awk is the one text tool guaranteed present on a 1-vCPU runner, the twin's own header says so, and reimplementing 439 lines of mawk-dialect
aggregation in Python would replace the thing under test with a second instrument rather than port the wrapper around it.

Everything policy-shaped lives here: the missing-profile panel, the 900 kB trim, the single `::notice` machine row, and the strict/non-strict split between `::error::` and `::warning::`.

Required env: `PROFILER_SAMPLE_FILE`. Optional env: `PROFILER_STRICT`, `PROFILER_WALL_S`, `PROFILER_TITLE`, `PROFILER_NOTE`, `PROFILER_DECLARED_S`, `PROFILER_HARD_S`, `PROFILER_MAX_PANEL_BYTES`, `GITHUB_JOB`, `GITHUB_STEP_SUMMARY`.

Exit: 0 clean or non-strict, 1 findings under strict, 2 usage error.

PORT NOTES -- the quirks below are REPRODUCED, not repaired. The acceptance for this port is agreement with the twin, and each of these is a place where the obvious Python would have disagreed.

`${VAR:-default}` TREATS EMPTY AS UNSET. `PROFILER_STRICT=` (exported empty) is
`false`, not `""`, and `GITHUB_STEP_SUMMARY=` is `/dev/stdout`. Plain
`os.environ.get(name, default)` returns the empty string in both cases and would have sent the panel to a file named `""`. `_env` below is the `:-` operator, and
`_plus` is `${TITLE:+: $TITLE}`.

THE SUMMARY IS A PATH THE TWIN OPENS IN APPEND MODE, including when that path is `/dev/stdout`. So this port opens it the same way rather than writing through `sys.stdout`: `>>` sets `O_APPEND`, which is what keeps the panel and the annotations that follow it in order on one fd. `sys.stdout` is flushed either side of every summary write, because Python fully buffers a pipe while a
second open file description does not, and out-of-order output would be a port defect invisible on a terminal.

THE MESSAGE TEXT STILL SAYS `panel.sh:`. Two of the three refusals name the
script in their own text; changing them to `profiler_panel.py:` would change
which strings a log scraper (or this port's differential) sees, so the twin's wording is kept verbatim until the cutover renames both sides at once.

`while IFS= read -r line` DROPS AN UNTERMINATED FINAL LINE. `read` returns
non-zero at EOF, so the loop body never runs for a last line with no `\n`, and that finding is silently not annotated. `_read_lines` reproduces it by keeping only newline-terminated records. Unreachable in production -- `report.awk` writes findings with `print`, which always terminates -- and reproduced anyway, because "the port emits one more annotation than the twin" is exactly
the class of drift a differential exists to catch.

ONE NAMED, DELIBERATELY-NOT-REPRODUCED DIVERGENCE. With a non-numeric `PROFILER_MAX_PANEL_BYTES`, the twin's `[ "$SIZE" -gt "$MAX_PANEL_BYTES" ]` makes bash print `<path>: line 154: [: <value>: integer expected` on stderr (measured, not quoted from memory) and evaluate FALSE (an `if` condition is exempt from `set -e`). This port matches the observable decision -- no trim -- and
does not forge a bash diagnostic carrying the twin's own path and line number. Pinned by `test_non_numeric_budget_is_a_bash_diagnostic_only` in the differential, which asserts the twin still emits it, so the divergence stays a recorded fact rather than a silent one.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

REPORT_AWK = paths.from_root(".ci", "scripts", "ci", "profiler", "report.awk")

# 1 MiB is a hard platform limit and the failure mode is an unhelpful upload error, so the panel is trimmed well short of it.
DEFAULT_MAX_PANEL_BYTES = "900000"

MISSING_REASON = "the sampler did not start, or wrote nothing before the job ended"


def _env(name: str, default: str = "") -> str:
    """`${name:-default}`: an EMPTY value takes the default, as `:-` does."""
    value = os.environ.get(name, "")
    return value if value != "" else default


def _plus(value: str, alternative: str) -> str:
    """`${value:+alternative}`: the alternative only when value is non-empty."""
    return alternative if value != "" else ""


def _read_lines(path: pathlib.Path) -> list[str]:
    """`while IFS= read -r line; do ... done <file`, unterminated tail and all."""
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    records = text.split("\n")
    # The final element is "" for a newline-terminated file and the unterminated remainder otherwise. `read` fails on that remainder, so the twin drops it.
    return records[:-1]


def escape_workflow_command(s: str) -> str:
    """A workflow command's message is line-oriented and `%` starts an escape."""
    s = s.replace("%", "%25")
    s = s.replace("\r", "%0D")
    return s.replace("\n", "%0A")


def emit_finding_annotations(path: pathlib.Path, strict: str) -> None:
    for line in _read_lines(path):
        if line == "":
            continue
        if strict == "true":
            print("::error::profiler: %s" % line, flush=True)
        else:
            print("::warning::profiler: %s" % line, flush=True)


def _append(summary: str, text: str) -> None:
    """`>>"$SUMMARY"`, including the `/dev/stdout` case."""
    sys.stdout.flush()
    with open(summary, "a", encoding="utf-8", errors="surrogateescape") as handle:
        handle.write(text)
        handle.flush()
    sys.stdout.flush()


def _gt(size: int, budget: str) -> bool:
    """`[ "$SIZE" -gt "$MAX_PANEL_BYTES" ]`, minus the bash diagnostic."""
    try:
        return size > int(budget.strip())
    except ValueError:
        return False


def main(argv: list[str]) -> int:  # noqa: ARG001 -- the twin ignores its arguments
    sample_file = _env("PROFILER_SAMPLE_FILE")
    strict = _env("PROFILER_STRICT", "false")
    wall_s = _env("PROFILER_WALL_S", "0")
    title = _env("PROFILER_TITLE")
    note = _env("PROFILER_NOTE")
    summary = _env("GITHUB_STEP_SUMMARY", "/dev/stdout")
    max_panel_bytes = _env("PROFILER_MAX_PANEL_BYTES", DEFAULT_MAX_PANEL_BYTES)

    if sample_file == "":
        print("panel.sh: PROFILER_SAMPLE_FILE must be set", file=sys.stderr)
        return 2
    if not os.access(REPORT_AWK, os.R_OK):
        print("panel.sh: missing aggregator: %s" % REPORT_AWK, file=sys.stderr)
        return 2

    sample = pathlib.Path(sample_file)
    # `[ ! -s "$SAMPLE_FILE" ]`: absent OR empty. A missing profile and a zero profile look identical in a log and mean opposite things.
    if not (sample.is_file() and sample.stat().st_size > 0):
        _append(
            summary,
            "".join(
                line + "\n"
                for line in (
                    "",
                    "## Runner Profile%s" % _plus(title, ": %s" % title),
                    "",
                    "**Samples:** none - no sample file was produced.",
                    "**Reason:** %s" % (note if note != "" else MISSING_REASON),
                    "",
                    "> No profile was collected. Nothing about this job's CPU or memory",
                    "> footprint can be concluded from this run.",
                    "",
                )
            ),
        )
        tail = "no sample file at %s (%s)" % (
            sample_file,
            note if note != "" else "sampler produced nothing",
        )
        if strict == "true":
            print("::error::profiler: %s" % tail, flush=True)
            return 1
        print("::warning::profiler: %s" % tail, flush=True)
        return 0

    work = pathlib.Path(tempfile.mkdtemp())
    try:
        panel = work / "panel.md"
        findings = work / "findings.txt"
        machine = work / "machine.txt"
        findings.write_bytes(b"")

        awk_args = [
            "-v",
            "wall_s=%s" % wall_s,
            "-v",
            "findings_file=%s" % findings,
            "-v",
            "title=%s" % title,
            "-v",
            "machine_file=%s" % machine,
            "-v",
            "job=%s" % _env("GITHUB_JOB"),
        ]
        # Passing `-v declared_s=` would set it to the empty string, which
        # report.awk reads as "unset" and replaces with its default anyway -- but relying on that would make the defaults live in two places.
        declared_s = _env("PROFILER_DECLARED_S")
        if declared_s != "":
            awk_args += ["-v", "declared_s=%s" % declared_s]
        hard_s = _env("PROFILER_HARD_S")
        if hard_s != "":
            awk_args += ["-v", "hard_s=%s" % hard_s]

        sys.stdout.flush()
        with open(panel, "wb") as out:
            try:
                rc = subprocess.run(
                    ["awk", *awk_args, "-f", str(REPORT_AWK), sample_file],
                    stdout=out,
                    check=False,
                ).returncode
            except OSError:
                # No awk on PATH. The twin gets bash's `command not found` and
                # RC=127, which its own `-gt 1` turns into the named refusal
                # below; a Python traceback here would read as flake instead.
                print("panel.sh: awk not found on PATH", file=sys.stderr)
                rc = 127
        if rc > 1:
            print("panel.sh: aggregator failed with exit %d" % rc, file=sys.stderr)
            return 2

        body = panel.read_bytes()
        size = len(body)
        if _gt(size, max_panel_bytes):
            body = body[: int(max_panel_bytes.strip())] + (
                "\n**Panel trimmed:** %d bytes exceeded the %s-byte budget "
                "(platform limit is 1 MiB per step summary).\n" % (size, max_panel_bytes)
            ).encode("utf-8")

        if note != "":
            body += ("**Note:** %s\n\n" % note).encode("utf-8")
        panel.write_bytes(body)

        sys.stdout.flush()
        with open(summary, "ab") as handle:
            handle.write(body)
            handle.flush()
        sys.stdout.flush()

        # Exactly ONE notice per job. report.awk writes the row only when it produced a verdict, so a run it refused to advise on emits no annotation at all rather than an unusable one.
        if machine.is_file() and machine.stat().st_size > 0:
            advisory = ""
            for line in body.decode("utf-8", errors="surrogateescape").split("\n"):
                if line.startswith("**Advisory:** "):
                    advisory = line[len("**Advisory:** ") :]
                    break
            # The advisory is read back out of the panel, and the panel can have been trimmed above. Say so rather than emitting a notice that opens
            # with nothing; the row after it is the part a machine reads either way.
            if advisory == "":
                advisory = "(advisory text unavailable: the panel was trimmed)"
            # `$(head -n 1 "$MACHINE")`, which is NOT `read`: head prints an unterminated final line, and command substitution then strips only trailing newlines. Using `_read_lines` here would drop exactly the row report.awk writes when its last `print` is the only one.
            row = machine.read_text(encoding="utf-8", errors="surrogateescape").split("\n")[0]
            print(
                "::notice title=Runner sizing (profiler)::%s | %s"
                % (escape_workflow_command(advisory), escape_workflow_command(row)),
                flush=True,
            )

        if findings.stat().st_size > 0:
            emit_finding_annotations(findings, strict)
            if strict == "true":
                return 1
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
