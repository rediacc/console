#!/usr/bin/env python3
"""Port of `.ci/scripts/security/check-autopilot-workflow-invariants.sh`.

W7P6 wave 27. The bash twin stays the LIVE registered gate; this module is its VERIFIED-EQUIVALENT ALTERNATIVE, proved byte-for-byte on both streams by `.ci/rediacc_ci/tests/test_security_autopilot_workflow_invariants.py` and by the
K=5 shadow ledger
`.ci/shadow/w7p6-check-autopilot-workflow-invariants.observations.jsonl`. Nothing is repointed at this file. Cutover is a separate, later, driver-only step.

NAMING. `check_` is dropped to match `rediacc_ci.security.workflow_gates`, the nearest sibling in this package; see the same note in `ci_workflow_invariants`.

WHAT THE TWIN DOES. Static invariants over `.github/workflows/autopilot.yml`, the workflow that hands a model a shell over PR-authored code. Each invariant is a structural expression of a rule from `docs/ci-overhaul/03-v2-autonomy.md`, so a violation means the SECURITY design is broken rather than that a style rule is bent. The nine findings, and the twin's own one-line reason for
each:

  wall4-comment-missing        the WALL 4 comment must stay in the file
  trusted-checkout-not-first   a job's FIRST checkout must be rediacc/console@main
  persist-credentials          every checkout must set persist-credentials: false
  event-interpolation-in-run   no `github.event.` inside a run: block scalar
  harness-python-workspace-on-path
                               a harness `python3` invocation passes -P, so the PR-authored cwd cannot shadow the trusted module
  token-in-gate                the gate job decides with zero write capability
  token-before-model           no app-token step at or before the model step
  track-progress-armed         track_progress must stay the literal false
  cancel-in-progress-armed     cancel-in-progress must stay false
  model-without-state-guard    the model job's own if: must name AUTOPILOT_ALLOW_STATE
  submodule-checkout-pre-model no pre-model checkout may request submodules
  model-round-file-tools       the model round's allowlist must carry Edit/Write/Read

NO EXTERNAL PROCESS IS INVOLVED, ON EITHER SIDE. The twin shells out to `awk` (three separate programs) and `grep`, both of which are transcribed here; there is no `yq`, no `jq`, no `gh`, no network, and no YAML parser -- the twin walks the file as TEXT and this port must walk it the same way, because the invariants are partly about COMMENTS and about indentation, neither of which
survives a parse. That is why the differential needs no recording fakes and drives both sides over fixture YAML through `$WORKFLOW_FILE`, the seam the twin already exposes for its own gate test.

PORT NOTES -- unless an item says otherwise it is REPRODUCED, not repaired.

  * `for (j in array)` IS UNORDERED IN AWK, AND THAT IS THE ONE PLACE THE TWO
    SIDES CAN DISAGREE ON BYTES. The twin's END block iterates `first_token` and
    `submodule_checkout` with `for (j in ...)`, whose order POSIX leaves
    unspecified; gawk 5.3.2 answers in internal hash order, which is neither
    insertion nor sorted. Measured on this host:

        $ awk 'BEGIN{a["gate"]=1;a["model"]=2;a["zeta"]=3;a["alpha"]=4;
                     for(k in a) print k}'
        model
        gate
        alpha
        zeta

    It is stable run to run for the same key set, so the twin is not flaky; it
    is simply not reproducible from outside gawk. This port emits in INSERTION
    order (first line at which the job acquired the entry), which is the only
    order a reader can predict from the file. The blast radius is zero on any
    input with fewer than two offending jobs, and every real violation of these
    two invariants is a single job. `test_two_token_jobs_disagree_only_on_order`
    pins the divergence with both sides' actual bytes rather than leaving it to
    be rediscovered; every other case in the differential is byte-for-byte.

  * `length(seen_checkout)` COUNTS JOB HEADERS, NOT JOBS. The key is created by
    the job-header rule and also by `seen_checkout[job]++` on a checkout, so a
    checkout appearing before any `jobs:` header creates a `<top>` key and the
    "N jobs scanned" line counts it. Reproduced.

  * THE `-eq 0` VACUITY GUARD READS AWK'S OWN COUNT, not a re-derivation. The
    twin greps its own findings stream for the `scanned-jobs` row; this port
    keeps the row in the findings list for the same reason, so the two cannot
    drift apart on what "scanned" means.

  * `log_error` IS `echo -e`, SO IT INTERPRETS BACKSLASH ESCAPES IN THE MESSAGE.
    None of these messages contains one, and `$where` is drawn from workflow
    text that would have to contain a literal backslash sequence to differ.
    `rediacc_ci.log` formats the message as data (see `log.py`'s own docstring),
    which is the documented deliberate divergence of that module and is
    unreachable from any input this gate accepts.

ONE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours
`$REDIACC_CI_ROOT` and the twin's `${BASH_SOURCE[0]}/../../..` does not. The
differential never sets it, and both files sit three levels below the root.
"""

from __future__ import annotations

import os
import re
import sys

from rediacc_ci import log, paths

# POSIX [[:space:]] under LC_ALL=C. Spelled out rather than reusing Python's
# `\s`, which also matches \x1c-\x1f and (under re.UNICODE, the default for str patterns) a long tail of Unicode separators that awk's C locale does not.
SP = "[ \t\n\v\f\r]"

# --- the one-pass walker's rules, in the twin's own order (`:75-155`) --------
RE_BLANK = re.compile("^" + SP + "*$")
RE_JOB_HEADER = re.compile("^  [A-Za-z_][A-Za-z0-9_-]*:" + SP + "*$")
RE_STEP_MARKER = re.compile("^" + SP + r"*-" + SP + "+(name|uses):")
RE_EVENT = re.compile(r"github\.event\.")
RE_HARNESS_PYTHONPATH = re.compile(r'PYTHONPATH="\$RUNNER_TEMP/')
RE_PYTHON_SAFE_PATH = re.compile("python3" + SP + "+-P" + SP)
RE_RUN_BLOCK = re.compile("^" + SP + "*run:" + SP + r"*[|>]")
RE_SUBMODULES = re.compile("^" + SP + "*submodules:" + SP + "*")
RE_SUBMODULES_FALSE = re.compile("submodules:" + SP + "*.?false.?" + SP + "*$")
RE_PERSIST_FALSE = re.compile("persist-credentials:" + SP + "*false")
RE_REPO_CONSOLE = re.compile("repository:" + SP + r"*rediacc/console")
RE_REF_MAIN = re.compile("ref:" + SP + "*main" + SP + "*$")
RE_CHECKOUT = re.compile(r"uses:.*actions/checkout@")
RE_APP_TOKEN = re.compile(r"uses:.*\.github/actions/app-token")
RE_MODEL_ACTION = re.compile(r"uses:.*claude-code-action@")
RE_TRACK_PROGRESS = re.compile("track_progress:")
RE_TRACK_PROGRESS_QUOTED_FALSE = re.compile("track_progress:" + SP + "*.false." + SP + "*$")
RE_TRACK_PROGRESS_BARE_FALSE = re.compile("track_progress:" + SP + "*false" + SP + "*$")
RE_CANCEL = re.compile("cancel-in-progress:")
RE_CANCEL_FALSE = re.compile("cancel-in-progress:" + SP + "*false" + SP + "*$")

# --- the two extraction passes (`:196-230`) ---------------------------------
RE_MODEL_JOB = re.compile("^  model:" + SP + "*$")
RE_ANY_JOB = re.compile("^  [A-Za-z_][A-Za-z0-9_-]*:")
RE_MODEL_IF = re.compile("^    if:")
RE_SETTINGS_PIPE = re.compile(r"settings: \|")

# The three tools the model round's allowlist must carry, in the twin's order. `grep -qF`, so these are fixed strings including their quotes.
REQUIRED_TOOLS = ('"Edit"', '"Write"', '"Read"')


def records(text: str) -> list[str]:
    """The file as awk sees it: RS='\\n', and a final newline yields no empty record.

    `text.splitlines()` would be wrong twice over -- it also splits on \\x0b, \\x0c, \\x1c-\\x1e and U+2028/U+2029, none of which awk treats as a record separator, so a workflow containing a form feed inside a run block would be walked with different line NUMBERS by the two sides.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def walk(text: str) -> list[tuple[str, str, str]]:
    """`:75-171`, the single awk pass, as (kind, line, where) triples.

    Exported so the selftest can drive every rule without a subprocess. The last triple is always the twin's `scanned-jobs` row, kept in the list rather than returned separately because the twin's vacuity guard reads it back out of the same stream.
    """
    out: list[tuple[str, str, str]] = []
    job = "<top>"
    current_step = ""
    marker_indent = 0
    in_jobs = False
    in_run = False
    run_indent = 0
    # awk's uninitialised scalars are "" / 0, which is falsy in a boolean test.
    pending = False
    checkout_line = 0
    checkout_job = ""
    checkout_first = False
    has_persist = False
    has_repo = False
    has_main = False
    step_ind = 0
    seen_checkout: dict[str, int] = {}
    first_token: dict[str, int] = {}
    model_line: dict[str, int] = {}
    submodule_checkout: dict[str, int] = {}

    def stepname() -> str:
        return "%s/%s" % (job, current_step or "<unnamed>")

    for nr, raw in enumerate(records(text), start=1):
        line = re.sub(r"\r$", "", raw)
        indent = len(line) - len(line.lstrip(" "))
        stripped = line[indent:]
        is_comment = stripped[:1] == "#"

        # Leaving a run block scalar: any line at or above the run: key indent.
        if in_run and not RE_BLANK.match(line) and indent <= run_indent:
            in_run = False

        # Track the current job (2-space keys under jobs:) and step name.
        if line.startswith("jobs:"):
            in_jobs = True
        elif in_jobs and RE_JOB_HEADER.match(line) and not is_comment:
            job = re.sub(r":.*", "", stripped, count=1)
            current_step = ""
            seen_checkout[job] = 0
        if not is_comment and RE_STEP_MARKER.match(line):
            current_step = stripped
            marker_indent = indent

        # Inside a run: block, payload interpolation is the injection surface.
        if in_run and not is_comment and RE_EVENT.search(line):
            out.append(("event-interpolation-in-run", str(nr), stepname()))

        # The model job runs the harness with cwd = the PR-AUTHORED workspace, so a bare `python3 -m` puts that workspace at the head of sys.path and a branch-supplied rediacc_ci/ at the repo root shadows the trusted copy PYTHONPATH names. `-P` is what switches that off.
        # Not gated on in_run: the hazard is the invocation, whether or not it sits in a block scalar.
        if (
            not is_comment
            and RE_HARNESS_PYTHONPATH.search(line)
            and "python3" in line
            and not RE_PYTHON_SAFE_PATH.search(line)
        ):
            out.append(("harness-python-workspace-on-path", str(nr), stepname()))
        if not is_comment and RE_RUN_BLOCK.match(line):
            in_run = True
            run_indent = indent

        # A checkout that asks for submodules needs a credential for four PRIVATE repos. This sits BEFORE the pending-checkout block on purpose: that block `next`s over every line of a with-block, so a check placed after it never sees the inputs it is meant to police.
        if (
            not is_comment
            and RE_SUBMODULES.match(line)
            and not RE_SUBMODULES_FALSE.search(line)
            and job not in submodule_checkout
        ):
            submodule_checkout[job] = nr

        # A pending checkout is judged the moment its STEP ends: any new step marker, or any dedent to at or above the marker indent.
        if pending and not RE_BLANK.match(line) and not is_comment:
            if indent > step_ind and not stripped.startswith("- "):
                if RE_PERSIST_FALSE.search(line):
                    has_persist = True
                if RE_REPO_CONSOLE.search(line):
                    has_repo = True
                if RE_REF_MAIN.search(line):
                    has_main = True
                continue  # awk's `next`
            if not has_persist:
                out.append(("persist-credentials", str(checkout_line), checkout_job))
            if checkout_first and not (has_repo and has_main):
                out.append(("trusted-checkout-not-first", str(checkout_line), checkout_job))
            pending = False

        # Checkout steps: first one per job must be the trusted ref, and every one must carry persist-credentials: false within its with-block.
        if not is_comment and RE_CHECKOUT.search(line):
            seen_checkout[job] = seen_checkout.get(job, 0) + 1
            checkout_line = nr
            checkout_job = job
            checkout_first = seen_checkout[job] == 1
            has_persist = has_repo = has_main = False
            pending = True
            step_ind = marker_indent
            continue  # awk's `next`

        # Token ordering: record where app-token and the model action appear.
        if not is_comment and RE_APP_TOKEN.search(line) and job not in first_token:
            first_token[job] = nr
        if not is_comment and RE_MODEL_ACTION.search(line) and job not in model_line:
            model_line[job] = nr

        # track_progress: only the quoted or bare literal false is tolerable.
        if (
            not is_comment
            and RE_TRACK_PROGRESS.search(line)
            and not RE_TRACK_PROGRESS_QUOTED_FALSE.search(line)
            and not RE_TRACK_PROGRESS_BARE_FALSE.search(line)
        ):
            out.append(("track-progress-armed", str(nr), stepname()))
        if not is_comment and RE_CANCEL.search(line) and not RE_CANCEL_FALSE.search(line):
            out.append(("cancel-in-progress-armed", str(nr), job))

    # --- END ---------------------------------------------------------------
    if pending:
        if not has_persist:
            out.append(("persist-credentials", str(checkout_line), checkout_job))
        if checkout_first and not (has_repo and has_main):
            out.append(("trusted-checkout-not-first", str(checkout_line), checkout_job))
    # INSERTION order, not gawk's hash order; see the module docstring.
    for j, tok in first_token.items():
        if j == "gate":
            out.append(("token-in-gate", str(tok), j))
        if j in model_line and tok < model_line[j]:
            out.append(("token-before-model", str(tok), j))
    for j, sub in submodule_checkout.items():
        if j in model_line and sub < model_line[j]:
            out.append(("submodule-checkout-pre-model", str(sub), j))
    out.append(("scanned-jobs", "0", str(len(seen_checkout))))
    return out


def model_if_block(text: str) -> list[str]:
    """`:196-204`: the model job's JOB-LEVEL `if:`, and nothing else.

    Extracted as its own pass rather than folded into `walk` because it is a claim about one specific key's contents. A grep over the whole file would pass on the state-write STEP that already mentions the flag, which is precisely the substitute this invariant must not accept.
    """
    out: list[str] = []
    inmodel = False
    inif = False
    for line in records(text):
        if RE_MODEL_JOB.match(line):
            inmodel = True
            continue
        if inmodel and RE_ANY_JOB.match(line):
            inmodel = False
        if inmodel and RE_MODEL_IF.match(line):
            inif = True
            out.append(line)
            continue
        if inif:
            if line.startswith("      "):
                out.append(line)
                continue
            inif = False
    return out


def model_settings_block(text: str) -> list[str]:
    """`:223-230`: the `settings: |` scalar of the step named `Model round`.

    Scoped to that block rather than the whole file: a mention of `"Edit"` anywhere else must not satisfy the requirement.
    """
    out: list[str] = []
    instep = False
    insettings = False
    for line in records(text):
        if "name: Model round" in line:
            instep = True
        if instep and RE_SETTINGS_PIPE.search(line):
            insettings = True
            continue
        if insettings:
            if not line.startswith("          "):
                insettings = False
                instep = False
                continue
            out.append(line)
    return out


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments and parses none

    root_dir = str(paths.repo_root())
    workflow_file = os.environ.get("WORKFLOW_FILE") or os.path.join(
        root_dir, ".github", "workflows", "autopilot.yml"
    )

    # Anti-vacuity: a missing workflow means the gate checked nothing, and that must never read as green.
    if not os.path.isfile(workflow_file):
        log.error(
            "INVARIANT-FAIL: workflow-missing: no file at %s (nothing to check cannot pass)"
            % workflow_file
        )
        return 1

    failed = 0

    def fail(message: str) -> None:
        nonlocal failed
        log.error("INVARIANT-FAIL: %s" % message)
        failed = 1

    # `awk` reads bytes; a workflow with invalid UTF-8 must not raise here where the twin would simply walk the bytes. "surrogateescape" round-trips them.
    with open(workflow_file, encoding="utf-8", errors="surrogateescape") as handle:
        text = handle.read()

    findings = walk(text)

    scanned = ""
    for kind, _line, where in findings:
        if kind == "scanned-jobs":
            scanned = where
    if not scanned or int(scanned) == 0:
        fail("workflow-missing: no jobs parsed from %s (a blind scan cannot pass)" % workflow_file)

    for kind, line, where in findings:
        if not kind or kind == "scanned-jobs":
            continue
        fail("%s: %s:%s (%s)" % (kind, workflow_file, line, where))

    # The Wall 4 comment is required IN the file: the trusted-first-checkout rule above must stay explained at the point of use, not by folklore.
    if "WALL 4" not in text:
        fail(
            "wall4-comment-missing: no 'WALL 4' comment explains the trusted checkout (%s)"
            % workflow_file
        )

    model_if = model_if_block(text)
    if not model_if:
        # Anti-vacuity: an unfindable `if:` means this invariant checked nothing, which must never read as green.
        fail(
            "model-without-state-guard: no job-level 'if:' found for the model job in %s "
            "(an unparsed guard cannot pass)" % workflow_file
        )
    elif not any("AUTOPILOT_ALLOW_STATE" in candidate for candidate in model_if):
        fail(
            "model-without-state-guard: the model job's if: does not require "
            "AUTOPILOT_ALLOW_STATE (%s); a round that cannot record itself breaks the round "
            "counter" % workflow_file
        )

    # ----------------------------------------------------------------------- model-round-file-tools: the handoff CONTRACT requires the model to edit files and write handoff.json, and with a permissions allowlist present everything unlisted is DENIED. The first two live rounds (2026-08-09) burned 41 turns with 21 permission denials because Edit/Write were simply absent, an OMISSION
    # every other permission check passes by construction. -----------------------------------------------------------------------
    model_settings = model_settings_block(text)
    if not model_settings:
        fail(
            "model-round-file-tools: could not locate the Model round settings block in %s "
            "(an unparsed allowlist cannot pass)" % workflow_file
        )
    else:
        blob = "\n".join(model_settings)
        for tool in REQUIRED_TOOLS:
            if tool not in blob:
                fail(
                    "model-round-file-tools: the model round's permission allowlist omits %s; "
                    "the handoff contract requires the model to edit files and write "
                    "handoff.json, and an allowlist denies everything unlisted (live proof: 21 "
                    "denials across runs 31321211521/31326053280)" % tool
                )

    if failed != 0:
        log.error(
            "autopilot workflow invariants FAILED (docs/ci-overhaul/03-v2-autonomy.md is the "
            "design source)"
        )
        return 1
    log.info(
        "autopilot workflow invariants hold: %s jobs scanned, trusted checkouts first, no "
        "pre-model token, no event interpolation in run blocks" % scanned
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
