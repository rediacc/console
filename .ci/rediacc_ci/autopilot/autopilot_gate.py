#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/autopilot-gate.sh`.

THE PRE-MODEL GATE. Every check that must pass before the model is invoked, so
a no-go costs zero model tokens (03-v2-autonomy.md section 2). The gate is
PURE: it consumes recorded fixture files and env, runs no network calls, and
prints exactly one decision JSON line on stdout.

Purity is what makes every branch offline-testable, and the twin says the thing
that makes this port's shape mandatory rather than tasteful:

    an untested branch in this file is an untested security decision

So the differential (`test_autopilot_gate.py`) walks EVERY refusal arm, in
order, and the port below is written to make that walk possible: each decision
is a straight-line transliteration of the twin's, in the twin's order, with the
same string on stderr and the same JSON line on stdout.

-----------------------------------------------------------------------------
THE SIXTEEN EXITS, ENUMERATED, because "I ported the script" is not a claim
anyone can check and "these sixteen arms are each pinned by a case" is
-----------------------------------------------------------------------------
Six of them are LOUD (exit 2 or 1, a wiring bug must never read as a quiet
no-go); ten print a decision line and exit 0.

  usage      1  `$1` is not `--classify`                      exit 2, 2 lines
             2  `--event` or `--pr` missing                   exit 2
             3  `--event` names no file                       exit 1 (require_file)
             4  `--pr` names no file                          exit 1 (require_file)
             5  the event payload is not JSON (`jq -e .`)     exit 2
             6  the pr fixture is not JSON                    exit 2
             7  the event lacks `.conclusion` or `.id`        exit 2
  no-go      8  stage-flag-disabled  AUTOPILOT_ENABLED != true
             9  fork-pr              the RUN's head repo is not the base repo
            10  fork-pr              the PR's head repo is not its base repo
            11  blocked-label        `autopilot-blocked` is applied
            12  not-armed            no label, no dispatch, no open campaign
            13  author-not-allowlisted
            14  applier-not-allowlisted / dispatch-actor-not-allowlisted
            15  already-handled      this (run_id, attempt) is in the ledger
            16  round-cap            the trusted ledger says the cap is reached
            17  watchdog-defer       a pending_rerun is held for this run
            18  stuck-signature      the same failed-job set, STUCK_LIMIT times
            19  superseded           the run's head is no longer the PR head
            20  cancelled-no-failure
            21  unhandled-conclusion
  go        22  fix                  ci-failure
            23  fix                  watchdog-kill (cancelled with failed jobs)
            24  rerun-review         review gate red, nothing to answer
            25  review-response      review gate red with threads / threads only
            26  ready-flip           success while draft
            27  done                 green, ready, reviewed, nothing outstanding

ORDER IS A SECURITY PROPERTY HERE, NOT A STYLE. Three orderings in particular
are load-bearing and are asserted rather than assumed:

  * `autopilot-blocked` is read BEFORE any arming path, so the escalation latch
    beats a fresh dispatch. Cancelling a run kills one round; the label kills
    the loop.
  * The author allowlist runs AFTER arming and BEFORE the arming-trust check,
    so a stranger's PR is refused with `author-not-allowlisted` rather than
    with whatever the applier check would have said.
  * The dedup and round-cap checks run AFTER trust, so an untrusted caller
    cannot learn the ledger's contents from which refusal it gets.

-----------------------------------------------------------------------------
WHY `jq`, `grep`, `sort` AND `state-comment.sh` ARE ALL STILL SPAWNED
-----------------------------------------------------------------------------
Same rule as `finish.py` and `update_state.py` in this directory: the twin's
observable behaviour on the paths a differential can reach INCLUDES the exit
codes and diagnostics of the programs it spawns, and a reimplementation has to
re-derive each of their rules correctly or change a decision.

  * `jq -e .` is not `json.loads`. It exits 1 when the LAST value is `null` or
    `false`, so a fixture whose whole content is `null` is "not valid JSON" to
    this gate (exit 2) even though Python parses it happily. And `jq -e
    '.labels // [] | index($l)'` returns index 0 for a label in first position,
    which is TRUTHY in jq and falsy in Python. Getting that backwards would
    make the `autopilot-blocked` latch fail open for the commonest case, a PR
    carrying that label alone.
  * `grep -qE "run <id>/<attempt>([^0-9]|$)"` alternates `$` with a negated
    class, which is exactly the shape CLAUDE.md records `grep -E` (ugrep 7.5.0
    here) returning SILENT FALSE ZEROS on. Whatever this machine's `grep -E`
    does with it, the twin and the port do the SAME thing, because it is the
    same binary on the same PATH.
  * `sort` decides the failure signature. `LC_ALL=C sort` is a byte-order sort
    over lines, and a Python `sorted()` over `str` is a code-point sort over
    decoded text; they agree until the input is not UTF-8, which a job display
    name from the GitHub API is not guaranteed to be. `sha256` is spawned in
    the twin and computed with `hashlib` here, because a digest is a digest.
  * `state-comment.sh fields` is the ONE reader of the state comment's metadata
    line, and the twin's own comment says why: "a second copy of the format in
    this file is how the two would drift apart silently". Re-implementing it
    here would create exactly the second copy it refuses.

-----------------------------------------------------------------------------
BASH ARITHMETIC IS NOT `int()`, AND THE DIFFERENCE CHANGES DECISIONS
-----------------------------------------------------------------------------
Every numeric comparison in the twin is `((...))`, which parses a leading zero
as OCTAL. `AUTOPILOT_MAX_ROUNDS=012` is validated by `^[0-9]{1,4}$`, reaches
`((ROUNDS_DONE >= MAX_ROUNDS))` as TEN, and reaches `jq --argjson rounds_max
012` as TWELVE (measured against jq 1.8.1, which accepts the leading zero). So
the twin ENFORCES a cap of ten while REPORTING twelve, and a port using `int()`
would enforce twelve and agree with its own report -- a different gate.
`bash_int` below reproduces bash's rule, and the reported value stays jq's,
because jq is still jq. The same split reaches `((pr_threads == 0))` through a
`unresolved_threads` that arrives as the JSON STRING "012".

  MEASURED, NOT ASSUMED, and the first guess was wrong: the CAMPAIGN's
  `rounds_max` cannot carry an octal, because `state-comment.sh fields` passes
  it through `jq --argjson`, which prints 12 for the input 012. So the value the
  gate reads back is already decimal and only the env var and the dispatch input
  reach `((...))` with a leading zero intact. Written down because a test
  aimed at the campaign path passes for the wrong reason -- it proves jq
  laundered the value, not that the port got bash's grammar right.

  AN ERROR IS FALSE, NOT ZERO, AND THE DIFFERENTIAL IS WHAT TAUGHT THIS FILE SO.
  `((10 >= 08))` is a bash ERROR ("value too great for base") and an erroring
  `((...))` returns FALSE -- so a malformed round cap FAILS OPEN and the round
  runs. The first draft of this port read `08` as the number 0, computed
  `10 >= 0`, and refused the round: a port that turned a fail-open hazard into a
  refusal, on an input the twin's own validator admits. `bash_cmp` is the fix,
  and `bash_arith` returns `None` rather than 0 so no future call site can make
  the same mistake by accident.

  THE ONE DIVERGENCE IN THIS FILE, NAMED RATHER THAN HIDDEN. bash reports that
  error on stderr as
  `<script>: line <n>: ((: 08: value too great for base (error token is "08")`.
  The script path and line number are not reproducible from Python, so
  `bash_arith` prints the same sentence with this module's own prefix. Exit
  code, stdout and the DECISION are identical; one stderr line differs in its
  prefix.
  `test_an_invalid_octal_round_cap` pins that, compares everything else byte for
  byte, and is the reason this paragraph is a measurement rather than a hope.

-----------------------------------------------------------------------------
TWO HAZARDS IN THE TWIN, REPORTED AND PRESERVED
-----------------------------------------------------------------------------
1. `--state`, `--failed-jobs` and `--watchdog` are all tested with `[[ -n && -s ]]`
   and never with `require_file`. A MISTYPED PATH IS THEREFORE SILENT: a
   misspelled `--state` reads as "no state comment yet", which resets the round
   counter to 1 and re-arms a campaign the cap had already ended, and a
   misspelled `--watchdog` drops the deferral that stops the gate racing the
   watchdog. Both fail OPEN, which is the wrong direction for this file, and
   both are the same asymmetry `update_state.py` records for its `--verdict`.
   Fixing it changes a live workflow step's contract, so it is the cutover
   box's call and not this one's. Pinned by
   `test_a_mistyped_state_path_is_silently_no_state`.

2. `in_csv_allowlist` strips ALL whitespace from each entry rather than trimming
   the ends, so an allowlist of `a b, c` matches the login `ab`. GitHub logins
   cannot contain a space, so this cannot admit a real account today; it is
   recorded because it is a membership test guarding a model invocation, and
   "cannot happen" is a property of GitHub's naming rules rather than of this
   code. Pinned by `test_the_allowlist_strips_interior_whitespace`.

K=5 LEDGER: `.ci/shadow/w7p6-autopilot-gate.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "autopilot-gate.py"

USAGE = (
    "usage: autopilot-gate.sh --classify --event <file> --pr <file> "
    "[--state <file>] [--failed-jobs <file>] [--watchdog <file>]"
)
USAGE_WHY = (
    "the gate is fixtures-only by design; the calling workflow gathers the fixtures (see header)"
)

# The only models a round may be dispatched with. An unknown value is a TYPO,
# not an instruction: it falls back to the default rather than reaching
# claude_args, where it would fail the round after paying for the runner.
DEFAULT_MODEL = "claude-sonnet-5"
MODEL_ALLOWED = "claude-sonnet-5,claude-opus-5"

# The third consecutive round facing an unchanged failed-job set is the one that
# refuses: two distinct fixes have already failed to move it.
STUCK_LIMIT = 3

DEFAULT_MAX_ROUNDS = "25"
DEFAULT_LABEL = "autopilot"
BLOCKED_LABEL = "autopilot-blocked"

# The default `state-comment.sh fields` answer when there is no state comment.
# NOTE THE THREE KEYS: the twin's literal carries `campaign`, `model` and
# `rounds_max` and NOT `last_sig` or `sig_count`, so on a first round those two
# read back as the STRING "null" (jq -r of a missing key). Nothing matches
# "null" -- `SIG` is eight lowercase hex or the word `none` -- so the stuck
# counter starts at 1, which is the intent. Reproduced verbatim rather than
# tidied, because "tidying" it to five keys would make `campaign_sig_count` the
# number 0 and change nothing, and a port that changes nothing is still a port
# that changed the twin.
NO_STATE_FIELDS = '{"campaign":"none","model":"none","rounds_max":0}'

# The emit program, byte for byte from the twin. Key ORDER is the contract with
# the workflow step that reads this line, and jq prints keys in program order.
EMIT_PROGRAM = """{decision: $decision, mode: $mode, reason: $reason, round: $round, push_allowed: $push_allowed,
          armed_by: $armed_by, model: $model, rounds_max: $rounds_max, campaign: $campaign,
          dispatch_trusted: $dispatch_trusted, sig: $sig, sig_count: $sig_count}"""

# The ledger line shape, from the twin's two greps. The first counts rounds; the
# second is the (run_id, attempt) dedup and is built per invocation.
LEDGER_ROUND_RE = r"^r[0-9]+ \| run "


class Decided:
    """What `emit`/`no_go` reach `exit 0` WITH: an exit code and the line to print.

    The twin's `emit` ends in `exit 0` inside a function, which ends the whole
    script. A Python helper cannot do that without `sys.exit`, which is
    untestable without catching `SystemExit`.

    NOT AN EXCEPTION, DELIBERATELY, and this is the second draft: `RefusalError`
    next door is one because a `require_*` is called from a dozen places that
    each have to unwind. Here every caller is a `return` in one straight-line
    function, so an exception would add a control-flow mechanism nothing needs
    and would make "did this arm decide?" invisible in the signature. The value
    is RETURNED, `_classify` is typed as returning it, and a missing `return`
    is then a type error rather than a silently skipped decision.
    """

    __slots__ = ("code", "payload")

    def __init__(self, code: int, payload: bytes = b"") -> None:
        self.code = code
        self.payload = payload


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`: `.ci/scripts/autopilot`.

    From THIS file's location, matching `cd "$(dirname "${BASH_SOURCE[0]}")"`.
    `rediacc_ci.paths.repo_root()` is deliberately NOT used, for the reason
    `update_state.py:108-115` gives: it honours `$REDIACC_CI_ROOT` and the twin
    honours nothing, so a port built on it would follow an env var the twin
    ignores and could spawn a DIFFERENT `state-comment.sh` than the twin does.
    """
    return pathlib.Path(__file__).resolve().parents[3] / ".ci" / "scripts" / "autopilot"


def bash_arith(text: str) -> int | None:
    """`$((text))` for a bare token. `None` means bash raised an ERROR.

    Bash's arithmetic literal grammar, and only the parts a value reaching this
    gate can exhibit:

        ""        0     an empty or unset variable is zero
        "0"       0
        "012"    10     LEADING ZERO IS OCTAL
        "0x1f"   31
        "08"   None     an invalid octal digit is an ERROR
        "abc"     0     a bare word is a variable name; unset names are zero

    A negative literal cannot arrive: every value is either `grep -c` output or
    has already passed `^[0-9]{1,4}$` or `^[0-9]+$`.

    THE `None` IS NOT A DETAIL, IT IS THE WHOLE REASON THIS RETURNS AN OPTION.
    An erroring `((...))` returns FALSE, and false is not "compare against
    zero". `((10 >= 08))` is FALSE, so a malformed round cap FAILS OPEN and the
    round runs; a port that read `08` as `0` would compute `10 >= 0`, which is
    TRUE, and would refuse the round instead. That divergence was found by the
    differential rather than by reading, which is why `bash_cmp` exists at all
    instead of `bash_arith(a) >= bash_arith(b)`.
    """
    token = text.strip()
    if token == "":
        return 0
    negative = False
    if token[0] in "+-":
        negative = token[0] == "-"
        token = token[1:]
    if token == "":
        return 0
    try:
        if token[:2].lower() == "0x":
            value = int(token, 16)
        elif token[0] == "0" and len(token) > 1:
            value = int(token[1:], 8)
        else:
            value = int(token, 10)
    except ValueError:
        if token.isdigit() or token[:2].lower() == "0x":
            # bash: `((: 08: value too great for base (error token is "08")`.
            # The twin's copy of this line carries the script path and line
            # number; see the module docstring for why this prefix differs and
            # nothing else does.
            print(
                '%s: ((: %s: value too great for base (error token is "%s")' % (SELF, token, token),
                file=sys.stderr,
                flush=True,
            )
            return None
        # A bare word is a variable name. Nothing sets it, so it is zero.
        return 0
    return -value if negative else value


def bash_int(text: str) -> int:
    """`$((text))` where the twin uses the VALUE rather than a comparison.

    An error is zero here, which is not bash's behaviour: bash would abort the
    assignment and, under `set -e`, the script. Both call sites (`ROUND=$((
    ROUNDS_DONE + 1 ))` and `SIG_COUNT=$((campaign_sig_count + 1))`) are fed
    values that CANNOT error -- `grep -c` output and a `jq --argjson` number --
    so the abort path is unreachable and reproducing it would add an exit code
    no input can produce. Named rather than left implicit.
    """
    value = bash_arith(text)
    return 0 if value is None else value


def bash_cmp(left: str, op: str, right: str) -> bool:
    """`((left OP right))`, including "an error is FALSE".

    Bash evaluates left to right and stops at the first bad token, so only one
    diagnostic is printed even when both operands are malformed. Reproduced,
    because the diagnostics are on stderr and the differential counts them.
    """
    a = bash_arith(left)
    if a is None:
        return False
    b = bash_arith(right)
    if b is None:
        return False
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "==":
        return a == b
    raise ValueError("unsupported arithmetic operator %r" % op)


def in_csv_allowlist(value: str, csv: str) -> bool:
    """`in_csv_allowlist <value> <csv>`: exact-name membership.

    TWO BASH BEHAVIOURS THAT A NAIVE `csv.split(",")` LOSES, both preserved:

    1. `IFS=',' read -ra items <<<"$csv"` reads ONE LINE. A multi-line value is
       truncated at the first newline, so `A\\nB` allowlists only `A`. That is
       fail-CLOSED (fewer names admitted), which is the right direction, and it
       matters because a repo variable pasted from a wrapped list arrives that
       way.
    2. `item="${item//[[:space:]]/}"` deletes EVERY whitespace character rather
       than trimming the ends. See hazard 2 in the module docstring.

    An empty allowlist admits nobody, by construction: there is no item, so the
    loop ends and the answer is False. The twin's step 4 comment leans on that,
    and it is the whole fail-closed story for `AUTOPILOT_AUTHOR_ALLOWLIST`
    being unset.
    """
    line = csv.split("\n", 1)[0]
    for item in line.split(","):
        stripped = "".join(ch for ch in item if not ch.isspace())
        if stripped and stripped == value:
            return True
    return False


def _run(args: list[str], *, capture_err: bool = False, env: dict | None = None):
    """Spawn, capturing stdout, with stderr INHERITED unless asked otherwise.

    Inherited stderr is what an unredirected command in the twin does, and it
    is why jq's own parse errors reach fd 2 in the same order.
    """
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if capture_err else None,
        stdin=subprocess.DEVNULL,
        check=False,
        env=env,
    )


def jq_capture(args: list[str]) -> tuple[int, str]:
    """`x="$(jq ...)"`: stdout with trailing newlines stripped, plus jq's code.

    `set -e` makes a non-zero code end the script, so every caller checks it.
    """
    proc = _run(["jq", *args])
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def jq_test(args: list[str], *, quiet: bool = False) -> bool:
    """`jq -e ... >/dev/null`: the exit status only.

    `quiet` is the twin's `2>&1` on the dispatch probe, which is the ONE jq
    call whose diagnostics are deliberately swallowed (an absent
    `.autopilot_dispatch` key is the normal workflow_run path, not an error).
    """
    return _run(["jq", *args], capture_err=quiet).returncode == 0


def sha256_hex(data: bytes) -> str:
    """`sha256_hex`: the twin's `sha256sum | cut -d' ' -f1`, as a digest.

    The twin branches to `shasum -a 256` on macOS. Both print the same 64 hex
    characters for the same bytes, so there is nothing here to choose between.
    """
    return hashlib.sha256(data).hexdigest()


def failure_signature(path: str) -> tuple[int, str]:
    """`LC_ALL=C sort "$FAILED_JOBS" | sha256_hex | cut -c1-8`.

    Returns (exit code, signature). `sort` is SPAWNED (see the module
    docstring), and `pipefail` means its status is the pipeline's, so a
    unreadable file ends the twin's run rather than yielding a signature over
    nothing. That is the correct direction: a signature computed over a failed
    read would collide with every other failed read and read as "stuck".
    """
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    proc = subprocess.run(
        ["sort", path],
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        return proc.returncode, ""
    return 0, sha256_hex(proc.stdout or b"")[:8]


def grep_count(pattern_args: list[str], path: str) -> str:
    """`$(grep -c ... file || true)`: the count as the twin's shell sees it.

    A STRING, not an int, because `|| true` turns grep's "no match, exit 1"
    into an EMPTY capture on some grep failures and `0` on the ordinary
    no-match, and the difference travels into `$((...))` where both are zero.
    Returning the string keeps that faithful instead of guessing.
    """
    proc = _run(["grep", *pattern_args, path])
    return (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def non_empty_file(path: str) -> bool:
    """`[[ -n "$p" && -s "$p" ]]`, the twin's test for every optional fixture.

    NOT `require_file`. See hazard 1 in the module docstring: this is the test
    that makes a mistyped path silent.
    """
    if not path:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        # `-s` is false for anything it cannot stat, including a directory it
        # can (a directory has a size, and bash's `-s` is true for it, which is
        # reproduced by getsize succeeding).
        return False


class Gate:
    """The gate's mutable state, in the twin's variable order.

    A class rather than a pile of locals because `emit` reads eight of them and
    the twin reads them as globals; passing eight arguments through every
    refusal would be the place a port drops one.
    """

    def __init__(self) -> None:
        self.round = 1
        self.push_allowed = "false"
        self.resolved_model = DEFAULT_MODEL
        self.campaign_state = "none"
        self.armed_by = "none"
        self.dispatch_trusted = "false"
        self.max_rounds = DEFAULT_MAX_ROUNDS
        self.sig = "none"
        self.sig_count = 0

    def emit(self, decision: str, mode: str, reason: str) -> Decided:
        """`emit <decision> <mode> <reason>`, including the campaign hand-off.

        THE CAMPAIGN VALUE IS THE NEXT WRITE'S, NOT THIS ROUND'S. A
        dispatch-armed go OPENS the campaign; reaching mode `done` CLOSES one
        that exists; everything else carries the current value forward
        untouched, so a label-armed round never closes a campaign it knows
        nothing about. Three arms, and the middle one has a guard that is easy
        to miss: `done` with campaign `none` stays `none` rather than becoming
        `closed`, because there was nothing to close.
        """
        campaign_next = self.campaign_state
        if mode == "done":
            if self.campaign_state != "none":
                campaign_next = "closed"
        elif decision == "go" and self.armed_by == "dispatch":
            campaign_next = "open"
        code, line = jq_capture(
            [
                "-cn",
                "--arg",
                "decision",
                decision,
                "--arg",
                "mode",
                mode,
                "--arg",
                "reason",
                reason,
                "--argjson",
                "round",
                str(self.round),
                "--argjson",
                "push_allowed",
                self.push_allowed,
                "--arg",
                "armed_by",
                self.armed_by,
                "--arg",
                "model",
                self.resolved_model,
                "--argjson",
                "rounds_max",
                self.max_rounds,
                "--arg",
                "campaign",
                campaign_next,
                "--argjson",
                "dispatch_trusted",
                self.dispatch_trusted,
                "--arg",
                "sig",
                self.sig,
                "--argjson",
                "sig_count",
                str(self.sig_count),
                EMIT_PROGRAM,
            ]
        )
        if code != 0:
            # `set -e` on the jq in `emit`: the `exit 0` after it is never
            # reached and jq's own status ends the run, with jq's own message
            # already on stderr.
            return Decided(code)
        # `$( )` stripped jq's newline; `jq -cn` printed exactly one.
        return Decided(0, line.encode("utf-8", "surrogateescape") + b"\n")

    def no_go(self, reason: str) -> Decided:
        """`no_go <reason>`: `emit "no-go" "none" "$1"`."""
        return self.emit("no-go", "none", reason)


def _classify(args: dict[str, str], gate: Gate) -> Decided:
    """Everything after the fixtures are validated. Raises nothing; returns.

    Deliberately ONE function despite its length. The twin is one straight-line
    script and its order IS the specification; splitting it into per-check
    helpers would let a future edit move a check without the move being visible
    as a diff of this file's control flow.
    """
    event = args.get("ARG_EVENT", "")
    pr = args.get("ARG_PR", "")
    state = args.get("ARG_STATE", "")
    failed_jobs = args.get("ARG_FAILED_JOBS", "")
    watchdog = args.get("ARG_WATCHDOG", "")

    environ = os.environ

    max_rounds = environ.get("AUTOPILOT_MAX_ROUNDS", "") or DEFAULT_MAX_ROUNDS
    if not _is_small_int(max_rounds):
        max_rounds = DEFAULT_MAX_ROUNDS
    gate.max_rounds = max_rounds
    label = environ.get("AUTOPILOT_LABEL", "") or DEFAULT_LABEL
    if environ.get("AUTOPILOT_ALLOW_PUSH", "") == "true":
        gate.push_allowed = "true"

    # Round number this invocation would become: ledger entries + 1. The ledger
    # in the trusted-author state comment is the ONLY round counter (wall 3: the
    # cap must be enforced by the harness, never by the model). A round counter
    # the model could write to is a cap the model can lift.
    rounds_done_text = "0"
    if non_empty_file(state):
        rounds_done_text = grep_count(["-cE", LEDGER_ROUND_RE], state)
    rounds_done = bash_int(rounds_done_text)
    gate.round = rounds_done + 1

    # 1. Master stage flag: absent is off, and only the literal "true" arms.
    if environ.get("AUTOPILOT_ENABLED", "") != "true":
        return gate.no_go(
            "stage-flag-disabled: AUTOPILOT_ENABLED is not 'true' (absent means off, fail closed)"
        )

    # Event facts (all read via jq, never shell-interpolated from the payload).
    code, conclusion = jq_capture(["-r", ".workflow_run.conclusion // empty", event])
    if code != 0:
        return Decided(code)
    code, run_id = jq_capture(["-r", ".workflow_run.id // empty", event])
    if code != 0:
        return Decided(code)
    code, run_attempt = jq_capture(["-r", ".workflow_run.run_attempt // 1", event])
    if code != 0:
        return Decided(code)
    code, event_head_sha = jq_capture(["-r", ".workflow_run.head_sha // empty", event])
    if code != 0:
        return Decided(code)
    code, event_repo = jq_capture(["-r", ".repository.full_name // empty", event])
    if code != 0:
        return Decided(code)
    code, event_head_repo = jq_capture(
        ["-r", ".workflow_run.head_repository.full_name // empty", event]
    )
    if code != 0:
        return Decided(code)
    if not conclusion or not run_id:
        log.error("event payload lacks workflow_run.conclusion or .id")
        return Decided(2)

    code, pr_author = jq_capture(["-r", ".author // empty", pr])
    if code != 0:
        return Decided(code)
    code, pr_draft = jq_capture(["-r", ".draft // false", pr])
    if code != 0:
        return Decided(code)
    code, pr_applier = jq_capture(["-r", ".label_applier // empty", pr])
    if code != 0:
        return Decided(code)
    code, pr_head_repo = jq_capture(["-r", ".head_repo // empty", pr])
    if code != 0:
        return Decided(code)
    code, pr_base_repo = jq_capture(["-r", ".base_repo // empty", pr])
    if code != 0:
        return Decided(code)
    code, pr_head_sha = jq_capture(["-r", ".head_sha // empty", pr])
    if code != 0:
        return Decided(code)
    code, pr_threads = jq_capture(["-r", ".unresolved_threads // 0", pr])
    if code != 0:
        return Decided(code)
    if not _is_digits(pr_threads):
        pr_threads = "0"
    code, pr_review_red = jq_capture(["-r", ".review_gate_red // false", pr])
    if code != 0:
        return Decided(code)

    # Dispatch facts. The key is absent on the workflow_run path, so
    # `is_dispatch` is false there without the gate needing to know the event
    # name twice.
    is_dispatch = jq_test(["-e", ".autopilot_dispatch", event], quiet=True)
    code, dispatch_actor = jq_capture(["-r", ".autopilot_dispatch.actor // empty", event])
    if code != 0:
        return Decided(code)
    code, dispatch_pr = jq_capture(["-r", ".autopilot_dispatch.pr_input // empty", event])
    if code != 0:
        return Decided(code)
    code, dispatch_model = jq_capture(["-r", ".autopilot_dispatch.model // empty", event])
    if code != 0:
        return Decided(code)
    code, dispatch_rounds = jq_capture(["-r", ".autopilot_dispatch.max_rounds // empty", event])
    if code != 0:
        return Decided(code)

    # Is the DISPATCHER trusted? Reported separately from the arming decision
    # because the workflow gates its hold-open debug session on it, and that
    # session is a human shell on the runner. Arming can succeed by label (whose
    # trust check is the label APPLIER, a different person) while the actor who
    # pressed Run workflow is nobody in particular, so "this round is armed" is
    # not the same claim as "this dispatcher may open a shell here".
    applier_allowlist = environ.get("AUTOPILOT_APPLIER_ALLOWLIST", "") or environ.get(
        "AUTOPILOT_AUTHOR_ALLOWLIST", ""
    )
    if is_dispatch and in_csv_allowlist(dispatch_actor, applier_allowlist):
        gate.dispatch_trusted = "true"

    # Campaign fields, read back through state-comment.sh rather than parsed
    # here. The metadata line therefore has exactly ONE writer and ONE reader; a
    # second copy of the format in this file is how the two would drift apart
    # silently. Every value it returns is already normalized there.
    campaign_fields = NO_STATE_FIELDS
    if non_empty_file(state):
        proc = _run([str(script_dir() / "state-comment.sh"), "fields", "--body", state])
        if proc.returncode != 0:
            # `set -e` on a command substitution: state-comment.sh's own status.
            return Decided(proc.returncode)
        campaign_fields = (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")

    # FIVE SEPARATE `jq -r` CALLS, exactly as the twin makes them, and NOT one
    # `json.loads`. The default literal above has only three of these five keys,
    # so `.last_sig` and `.sig_count` come back as the STRING "null" on a first
    # round -- which is what the twin's shell variables hold, and what the
    # comparisons below are written against.
    values = []
    for program in (".campaign", ".model", ".rounds_max", ".last_sig", ".sig_count"):
        code, value = _jq_stdin(["-r", program], campaign_fields)
        if code != 0:
            return Decided(code)
        values.append(value)
    campaign_model, campaign_rounds, campaign_last_sig, campaign_sig_count = values[1:]
    gate.campaign_state = values[0]

    # Failure signature: sorted, so the same set of red jobs hashes the same
    # regardless of the order the jobs API happened to return them in. An empty
    # or absent list is 'none' and never matches a previous signature -- a green
    # run must not look like a repeat of the last red one.
    if non_empty_file(failed_jobs):
        code, sig = failure_signature(failed_jobs)
        if code != 0:
            return Decided(code)
        gate.sig = sig
    gate.sig_count = 1
    if gate.sig != "none" and gate.sig == campaign_last_sig:
        gate.sig_count = bash_int(campaign_sig_count) + 1

    # Model resolution, in the design's order: the dispatch input beats the
    # campaign's recorded model, which beats the default. An unrecognised value
    # at either level degrades to the default rather than failing the round.
    if is_dispatch and dispatch_model:
        gate.resolved_model = dispatch_model
    elif campaign_model != "none":
        gate.resolved_model = campaign_model
    if not in_csv_allowlist(gate.resolved_model, MODEL_ALLOWED):
        log.warn(
            "model '%s' is not one of %s; falling back to %s"
            % (gate.resolved_model, MODEL_ALLOWED, DEFAULT_MODEL)
        )
        gate.resolved_model = DEFAULT_MODEL

    # Round-cap resolution, same order, with the repo variable as the third
    # fallback (already loaded into MAX_ROUNDS above) and 25 as the fourth.
    if is_dispatch and _is_small_int(dispatch_rounds) and bash_cmp(dispatch_rounds, ">", "0"):
        gate.max_rounds = dispatch_rounds
    elif bash_cmp(campaign_rounds, ">", "0"):
        gate.max_rounds = campaign_rounds

    # 2. Fork guard, in both records: the run's head repo and the PR's head repo
    # must both equal the base repo. The autopilot never touches fork-sourced
    # heads (03-v2-autonomy.md section 2, check 2). BOTH records are checked
    # because they come from different API calls and a mismatch between them is
    # itself a reason to stop.
    if event_head_repo and event_head_repo != event_repo:
        return gate.no_go(
            "fork-pr: workflow_run head repository '%s' is not the base repo" % event_head_repo
        )
    if not pr_head_repo or pr_head_repo != pr_base_repo:
        return gate.no_go(
            "fork-pr: PR head repo '%s' is not the base repo '%s'" % (pr_head_repo, pr_base_repo)
        )

    # 3. Arming. The blocked label is the escalation latch and is checked FIRST,
    # so it beats every arming path including a fresh dispatch: cancelling a run
    # kills one round, `autopilot-blocked` kills the loop.
    if jq_test(["-e", "--arg", "l", BLOCKED_LABEL, ".labels // [] | index($l)", pr]):
        return gate.no_go(
            "blocked-label: '%s' is applied; a human must clear the escalation first"
            % BLOCKED_LABEL
        )
    if jq_test(["-e", "--arg", "l", label, ".labels // [] | index($l)", pr]):
        gate.armed_by = "label"
    elif is_dispatch and dispatch_pr:
        # The dispatch IS the arming act (03-v2-autonomy.md section 2, corrected
        # 2026-08-05): round 1 runs straight off it, and the state-comment write
        # at the end of that round records the campaign so the workflow_run
        # rounds that follow can continue without a label ever existing.
        gate.armed_by = "dispatch"
    elif gate.campaign_state == "open" and bash_cmp(str(rounds_done), "<", gate.max_rounds):
        # The campaign path. Trust comes from the state comment's AUTHORSHIP,
        # already enforced upstream by state-comment.sh select (bot author +
        # exact header), so there is deliberately no applier/actor check below
        # for it: an outsider cannot post a comment this gate would read at all.
        gate.armed_by = "campaign"
    else:
        return gate.no_go(
            "not-armed: no '%s' label, no dispatch with a PR number, and no open campaign with "
            "rounds remaining (campaign: %s, rounds done: %s/%s)"
            % (label, gate.campaign_state, rounds_done, gate.max_rounds)
        )

    # 4. Author allowlist: the autopilot never babysits a stranger's PR. An
    # empty allowlist allows nobody (fail closed), by construction of the
    # membership test above.
    if not in_csv_allowlist(pr_author, environ.get("AUTOPILOT_AUTHOR_ALLOWLIST", "")):
        return gate.no_go(
            "author-not-allowlisted: PR author '%s' is not in AUTOPILOT_AUTHOR_ALLOWLIST"
            % pr_author
        )

    # 5. Arming trust, per path. Anyone with triage can apply a label on a
    # public repo and anyone with write can dispatch a workflow, so whoever
    # performed the ARMING ACT is a separate trust decision from the PR author.
    # Same allowlist for both: the act is the same delegation either way.
    # Two independent `if`s rather than one `if/elif` nest: `armed_by` holds
    # exactly one value here, so at most one can fire, and flattening keeps each
    # arm readable beside the message it produces.
    if gate.armed_by == "label" and not in_csv_allowlist(pr_applier, applier_allowlist):
        return gate.no_go(
            "applier-not-allowlisted: label applier '%s' is not allowlisted" % pr_applier
        )
    if gate.armed_by == "dispatch" and not in_csv_allowlist(dispatch_actor, applier_allowlist):
        return gate.no_go(
            "dispatch-actor-not-allowlisted: dispatching actor '%s' is not allowlisted"
            % dispatch_actor
        )
    # `campaign)` is an EMPTY case arm in the twin, and it is empty on purpose:
    # see the arming block, authorship of the state comment is the check.

    # 6. Dedup by (run_id, attempt): a queued duplicate of an already-handled
    # event must exit without a round (concurrency is cancel-in-progress:false,
    # so duplicates are expected, not exceptional).
    if non_empty_file(state) and _grep_quiet(
        ["-qE", "run %s/%s([^0-9]|$)" % (run_id, run_attempt)], state
    ):
        return gate.no_go("already-handled: run %s/%s is in the ledger" % (run_id, run_attempt))

    # 7. Round cap, from the trusted ledger only. This is also what ends a
    # campaign the operator never stops: the arming path above will not re-arm
    # on a campaign once the cap is reached, and a label-armed PR dies here with
    # the reason spelled out instead of a bare "not armed".
    if bash_cmp(str(rounds_done), ">=", gate.max_rounds):
        return gate.no_go(
            "round-cap: %s rounds recorded, cap is %s; escalating to the operator is the "
            "design working" % (rounds_done, gate.max_rounds)
        )

    # 8. Watchdog deferral: while a pending_rerun is held the watchdog owns this
    # run's classification; acting now would race it.
    if non_empty_file(watchdog):
        return gate.no_go(
            "watchdog-defer: a pending_rerun is held for this run; the gate defers so the two "
            "cannot race"
        )

    failed_count = "0"
    if non_empty_file(failed_jobs):
        failed_count = grep_count(["-c", "."], failed_jobs)

    # 9. Mode selection (03-v2-autonomy.md section 2, check 6, in its order).
    if conclusion == "failure":
        # Flapping bound before the fix round, not after: by the time the same
        # failed-job set arrives for the STUCK_LIMIT-th time, two distinct fixes
        # have already been spent on it and a third is a worse bet than the
        # operator's attention.
        if gate.sig != "none" and gate.sig_count >= STUCK_LIMIT:
            return gate.no_go(
                "stuck-signature: failed-job set %s is unchanged after %d fix round(s); "
                "escalating rather than burning the round cap" % (gate.sig, gate.sig_count - 1)
            )
        return gate.emit("go", "fix", "ci-failure: run %s concluded failure" % run_id)

    if conclusion == "cancelled":
        if bash_cmp(failed_count, ">", "0"):
            return gate.emit(
                "go", "fix", "watchdog-kill: cancelled with %s failed job(s)" % failed_count
            )
        if event_head_sha and pr_head_sha and event_head_sha != pr_head_sha:
            return gate.no_go(
                "superseded: run head %s is no longer the PR head %s"
                % (event_head_sha, pr_head_sha)
            )
        return gate.no_go(
            "cancelled-no-failure: cancelled with zero failed jobs and no newer head; nothing "
            "to act on"
        )

    if conclusion == "success":
        if pr_review_red == "true":
            # A red Review Gate with NOTHING outstanding to answer is the review
            # pipeline needing to run again, not the model needing to think: the
            # deterministic rerun costs zero model tokens (03-v2-autonomy.md
            # section 9 lists review-gate rerun among the zero-cost paths). With
            # threads open there IS something to answer, so that case still buys
            # a round.
            if bash_cmp(pr_threads, "==", "0"):
                return gate.emit(
                    "go",
                    "rerun-review",
                    "review-gate-red-no-threads: the Review Gate is red with nothing "
                    "outstanding to answer; deterministic rerun, no model",
                )
            return gate.emit(
                "go",
                "review-response",
                "review-gate-red: CI green, the Review Gate is red, and %s thread(s) are "
                "outstanding" % pr_threads,
            )
        if pr_draft == "true":
            return gate.emit(
                "go", "ready-flip", "success-while-draft: deterministic ready-flip, no model"
            )
        if bash_cmp(pr_threads, ">", "0"):
            return gate.emit(
                "go",
                "review-response",
                "unresolved-threads: %s review thread(s) outstanding" % pr_threads,
            )
        return gate.emit(
            "go", "done", "done-conditions: green, ready, reviewed, no outstanding threads"
        )

    return gate.no_go("unhandled-conclusion: '%s' is not an actionable run conclusion" % conclusion)


def _jq_stdin(args: list[str], text: str) -> tuple[int, str]:
    """`jq -r '<program>' <<<"$value"`, with the herestring's trailing newline."""
    proc = subprocess.run(
        ["jq", *args],
        input=text.encode("utf-8", "surrogateescape") + b"\n",
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def _grep_quiet(args: list[str], path: str) -> bool:
    """`grep -q ... file`: the exit status only, stderr inherited."""
    return _run(["grep", *args, path]).returncode == 0


def _is_small_int(text: str) -> bool:
    """`[[ "$x" =~ ^[0-9]{1,4}$ ]]`."""
    return 1 <= len(text) <= 4 and text.isdigit() and text.isascii()


def _is_digits(text: str) -> bool:
    """`[[ "$x" =~ ^[0-9]+$ ]]`."""
    return bool(text) and text.isdigit() and text.isascii()


def main(argv: list[str]) -> int:
    # `MODE_ARG="${1:-}"`: the mode is positional and is NOT a flag, so it never
    # reaches parse_args. With no arguments at all it is the empty string, which
    # lands in the usage arm -- LOUD (exit 2), never a quiet no-go.
    mode_arg = argv[0] if argv else ""
    if mode_arg != "--classify":
        log.error(USAGE)
        log.error(USAGE_WHY)
        return 2
    try:
        args = common.parse_args(argv[1:])
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    event = args.get("ARG_EVENT", "")
    pr = args.get("ARG_PR", "")
    if not (event and pr):
        log.error("--event and --pr are required")
        return 2
    for path in (event, pr):
        try:
            common.require_file(path)
        except common.RefusalError as exc:
            exc.report()
            return exc.code
    # `jq -e .` on each: valid JSON AND not `null`/`false`, which is jq's rule
    # and not `json.loads`'. A fixture whose whole body is `null` is refused
    # here rather than producing a decision over nothing.
    if not jq_test(["-e", ".", event]):
        log.error("event payload is not valid JSON: %s" % event)
        return 2
    if not jq_test(["-e", ".", pr]):
        log.error("pr fixture is not valid JSON: %s" % pr)
        return 2

    decided = _classify(args, Gate())
    if decided.payload:
        sys.stdout.buffer.write(decided.payload)
        sys.stdout.buffer.flush()
    return decided.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
