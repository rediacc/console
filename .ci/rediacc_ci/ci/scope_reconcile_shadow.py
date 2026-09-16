#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/scope-reconcile-shadow.sh`.

Skip-plan reconciliation for `ci-complete`. Polarity depends on `SCOPE_MODE`:
when the scope step actually reduced this run (`SCOPE_MODE=reduced`), every
way of failing to verify that reduction against the run's real per-job
outcomes -- a missing plan artifact, an unreadable Jobs API, an absent `gh` or
`node`, a reconciler that times out or disagrees -- is a HARD FAILURE (exit
1). Otherwise the same gaps are reported as gaps and the script exits 0. See
the twin's own header for the measured argument for why this is safe across a
rerun (the Jobs API's default `latest` filter materializes a complete job list
per attempt) and for `PREEXISTING_CONDITIONS`.

REQUIRED ENV: `GH_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_RUN_ID`, `SCOPE_MODE`.
`GITHUB_STEP_SUMMARY` optional; falls back to stdout when running locally.

PORT NOTES.

NO `errexit` TO REPLICATE. The twin runs under `set -uo pipefail`, with NO
`-e`: every external call's success is checked EXPLICITLY (`if ! cmd; then
...`), so this port's control flow is a direct, mechanical transliteration --
there is no implicit "the script dies here" behaviour hiding in a bare
command the way there would be under `-e`.

`emit()` CAN DUPLICATE ITS OWN OUTPUT, and that is a property of the twin
being ported faithfully, not a port defect. `SUMMARY="${GITHUB_STEP_SUMMARY:-
/dev/stdout}"` and `emit` is `printf '%s\\n' "$@" | tee -a "$SUMMARY"`: `tee`
always writes once to its own inherited stdout AND appends to the file named
by `$SUMMARY`. When `GITHUB_STEP_SUMMARY` is unset (the documented local-run
case), `$SUMMARY` IS `/dev/stdout` -- the same fd -- so every `emit` call
writes its lines TWICE. Measured directly: `printf 'hello\\n' | tee -a
/dev/stdout` prints `hello` twice. `_emit`/`_tee_head` below reproduce this
by writing to real stdout unconditionally and then EITHER appending to the
summary file (when one is set) OR writing to stdout a second time (when it is
not), matching `tee`'s own behaviour rather than special-casing "local mode"
away.

`gap()` HAS EXACTLY ONE MEANING PER POLARITY, always: emit the caller's lines,
then either the hard-failure block and exit 1 (`HARD_GATE`), or the soft-gap
note and exit 0. Ported as a function that RETURNS the exit code rather than
calling `sys.exit` itself, so `main()` can `return gap(...)` from any call
site exactly where the twin would `gap ...` and fall off the end of the
script -- the twin's `gap` never returns to its caller (it always `exit`s),
and neither does a `return gap(...)` in `main`.

THE TOOL PROBE EXITS ON THE FIRST MISSING TOOL, checked `gh` then `node`, and
never checks the second if the first is already missing -- `gap` inside the
twin's `for tool in gh node; do ... done` loop calls `exit` directly, ending
the whole script, not just the loop. `return gap(...)` inside the `for tool in
("gh", "node")` loop reproduces that: `main` returns before the loop's next
iteration.

`_head_bytes` TRANSLITERATES `"$(head -c N "$file" 2>/dev/null)"` AS CAPTURED
INTO A SHELL ARGUMENT, which means ALL trailing newlines are stripped (command
substitution strips every trailing newline, not one), matching `emit`'s
subsequent `printf '%s\\n'` re-adding EXACTLY one. A missing file yields the
empty string on both sides (`head`'s own stderr is redirected away and a
`$(...)` around a command that printed nothing to stdout is simply `""`).

`_tee_head`, BY CONTRAST, TRANSLITERATES THE RAW-FILE PATH
(`head -c N "$file" 2>/dev/null | tee -a "$SUMMARY"`) with NO extra newline
added and NO trailing-newline stripping: whatever raw bytes `head` would
produce (including none, for a missing file) are written to stdout and to the
summary exactly as read, because this is a `cat`-shaped pipeline, not an
`emit` call.

`bounded()` WRAPS EVERY EXTERNAL CALL IN A TIMEOUT, matching the twin's
`timeout "$GH_TIMEOUT" "$@"`. `subprocess.run(..., timeout=...)` raising
`TimeoutExpired` is treated as returncode 124, `timeout(1)`'s own exit code
for "killed the child" -- the twin's `rc -eq 124` branch depends on that exact
number, not on some other characteristic of a timeout.

ONE RESIDUAL DIVERGENCE, named rather than hidden, on the `GITHUB_STEP_SUMMARY`
UNSET path only. Measured directly on this host: when `$SUMMARY` falls back to
`/dev/stdout` AND the script's own stdout is redirected to a regular file
(`bash scope-reconcile-shadow.sh > out.txt`, the documented LOCAL RUN shape),
the twin's output is not a clean duplicate -- it is DETERMINISTICALLY
GARBLED (reproduced identically across three separate runs, byte for byte).
The cause is a kernel-level file-offset race, not script logic: each `emit`
spawns a fresh `tee -a /dev/stdout` process whose `-a` target reopens
`/dev/stdout` (`/proc/self/fd/1`) as a SEPARATE open file description with its
own `O_APPEND`-driven "seek to true end of file" on every write, while the
same `tee` process's OWN stdout is the ONE inherited, offset-sharing
descriptor threaded through every `emit` call across the whole script. Two
descriptions racing to extend the same regular file corrupts interleaving in
exactly the way observed. This port's `_dual_write` does NOT reproduce that:
writing twice through Python's single buffered `sys.stdout` produces a clean,
correctly-ordered duplicate (verified: the twin's corrupted output and the
port's clean output diverge on this one path). Not fixed and not chased
further, because production never takes it: `ci.yml:1781` runs this step
inside GitHub Actions, which ALWAYS sets `GITHUB_STEP_SUMMARY` to a real file,
so the fallback-to-`/dev/stdout` branch is unreachable in the wiring that
actually calls this script. Every differential case in this port's test file
therefore sets `GITHUB_STEP_SUMMARY` to a real path, matching production
exactly, and the unset-SUMMARY case is exercised once, separately, as a named
divergence rather than an equivalence claim.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys


def _console_root() -> pathlib.Path:
    # This file: <root>/.ci/rediacc_ci/ci/scope_reconcile_shadow.py
    return pathlib.Path(__file__).resolve().parents[3]


def _head_bytes(path: pathlib.Path, n: int) -> str:
    """`"$(head -c N "$path" 2>/dev/null)"` -- all trailing newlines stripped,
    empty string if the file cannot be read."""
    try:
        data = path.read_bytes()[:n]
    except OSError:
        return ""
    return data.decode("utf-8", errors="surrogateescape").rstrip("\n")


def main(argv: list[str]) -> int:
    del argv  # the twin takes no CLI arguments; everything is env-driven
    console_root = _console_root()
    reconciler = console_root / ".ci" / "scripts" / "ci" / "skip-plan-reconcile.cjs"
    summary_path_env = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_path = pathlib.Path(summary_path_env) if summary_path_env else None

    out_dir_env = os.environ.get("SCOPE_SHADOW_OUT")
    out_dir = (
        pathlib.Path(out_dir_env)
        if out_dir_env
        else console_root / ".ci" / "cache" / "scope-shadow"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    def _dual_write(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
        if summary_path is not None:
            with open(summary_path, "a", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(text)
        else:
            # SUMMARY defaults to /dev/stdout: `tee -a /dev/stdout` writes to
            # the SAME fd a second time, duplicating the output.
            sys.stdout.write(text)
            sys.stdout.flush()

    def emit(*lines: str) -> None:
        _dual_write("".join(line + "\n" for line in lines))

    def tee_head(path: pathlib.Path, n: int) -> None:
        try:
            data = path.read_bytes()[:n]
        except OSError:
            data = b""
        _dual_write(data.decode("utf-8", errors="surrogateescape"))

    gh_timeout_str = os.environ.get("SCOPE_SHADOW_TIMEOUT", "45")
    try:
        gh_timeout = float(gh_timeout_str)
    except ValueError:
        gh_timeout = 45.0

    def bounded(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(args, timeout=gh_timeout, check=False, **kwargs)  # type: ignore[arg-type]
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124)

    scope_mode = os.environ.get("SCOPE_MODE", "")
    hard_gate = scope_mode == "reduced"

    emit(
        f"### Skip-plan reconciliation (SCOPE_MODE={scope_mode or '<unset>'}, "
        f"hard gate: {'true' if hard_gate else 'false'})",
        "",
    )

    def gap(*lines: str) -> int:
        emit(*lines)
        if hard_gate:
            emit(
                "",
                "**RECONCILIATION FAILED.** This run SKIPPED work on the strength of a plan",
                "(scope_mode=reduced) and that plan could not be verified against what the run",
                "actually did. An unverifiable reduction is a skip nobody attested, so this is",
                "red rather than a note. Add the `full-ci` label and re-run for an",
                "unconditional round.",
                "",
            )
            return 1
        emit(
            "_(scope_mode is not 'reduced', so nothing was skipped on this plan's word and",
            "this is a gap in the evidence rather than a failure.)_",
            "",
        )
        return 0

    for tool in ("gh", "node"):
        if shutil.which(tool) is None:
            return gap(
                f"_**cannot reconcile**: `{tool}` is not available on this runner",
                "(ci-complete runs on ubuntu-slim). Fix by adding setup-node to ci-complete,",
                "or by moving this step to a job on ubuntu-latest._",
                "",
            )

    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")

    def download_plan() -> bool:
        for attempt in (1, 2):
            plan_dl = out_dir / "plan-dl"
            shutil.rmtree(plan_dl, ignore_errors=True)
            err_path = out_dir / "plan-dl.err"
            with open(err_path, "wb") as err_fh:
                result = bounded(
                    [
                        "gh",
                        "run",
                        "download",
                        run_id,
                        "--repo",
                        repository,
                        "-n",
                        "ci-skip-plan",
                        "-D",
                        str(plan_dl),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=err_fh,
                )
            if result.returncode == 0:
                return True
            if attempt == 1:
                emit("_(the plan download failed; retrying once)_")
        return False

    def read_jobs() -> bool:
        for attempt in (1, 2):
            jobs_json = out_dir / "jobs.json"
            jobs_err = out_dir / "jobs.err"
            with open(jobs_json, "wb") as out_fh, open(jobs_err, "wb") as err_fh:
                result = bounded(
                    [
                        "gh",
                        "api",
                        f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
                        "--paginate",
                    ],
                    stdout=out_fh,
                    stderr=err_fh,
                )
            if result.returncode == 0:
                return True
            if attempt == 1:
                emit("_(the jobs API call failed; retrying once)_")
        return False

    if not download_plan():
        return gap(
            "_no attested plan for this run: nothing to reconcile (expected on push-to-main,",
            "where the scope step does not run)._",
            "```",
            _head_bytes(out_dir / "plan-dl.err", 500),
            "```",
            "",
        )

    if not read_jobs():
        return gap(
            "_could not read the jobs API, so the run's actual per-job outcomes are",
            "unavailable._",
            "```",
            _head_bytes(out_dir / "jobs.err", 500),
            "```",
            "",
        )

    reconcile_out = out_dir / "reconcile.out"
    reconcile_err = out_dir / "reconcile.err"
    with open(reconcile_out, "wb") as out_fh, open(reconcile_err, "wb") as err_fh:
        result = bounded(
            [
                "node",
                str(reconciler),
                "--plan",
                str(out_dir / "plan-dl" / "plan.json"),
                "--jobs",
                str(out_dir / "jobs.json"),
                "--run-id",
                run_id,
            ],
            stdout=out_fh,
            stderr=err_fh,
        )
    rc = result.returncode

    final = 0
    if rc == 124:
        emit(
            f"_**cannot reconcile**: the reconciler exceeded {gh_timeout_str}s and was killed.",
            "This is a GAP IN THE EVIDENCE, not a verdict._",
            "",
        )
        if hard_gate:
            final = 1
    elif rc == 0:
        emit(
            "**reconciled** (exit 0). Check the `pre-existing skips` line below before",
            "banking it: a pass whose every key was excused by `full_suite`,",
            "`pointer_bump_only` or `is_bot` is a VACUOUS pass, and the counter that has to",
            "move is verified keys, not runs.",
            "",
        )
    else:
        emit(
            f"**reconcile FAILED** (exit {rc}). Read the reason before blaming the plan.",
            "`preexisting-claim-mismatch` means the plan's annotation disagrees with what",
            "its own recorded conditions imply, i.e. a tampered artifact or writer/reader",
            "drift, NOT a scope error.",
            "",
        )
        if hard_gate:
            final = 1

    emit("```")
    tee_head(reconcile_err, 3000)
    tee_head(reconcile_out, 1500)
    emit("```")

    if final != 0:
        emit(
            "",
            "**RECONCILIATION FAILED.** This run SKIPPED work on the strength of a plan",
            "(scope_mode=reduced) that does not describe what the run actually did. Add the",
            "`full-ci` label and re-run for an unconditional round.",
            "",
        )

    return final


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
