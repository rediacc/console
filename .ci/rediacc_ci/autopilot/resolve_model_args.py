"""Port of `.ci/scripts/autopilot/resolve-model-args.sh`.

Assembles one autopilot round's `claude_args` from validated inputs and prints
them one flag per line, plus an `args` heredoc entry in `$GITHUB_OUTPUT`.

ONE PLACE, because two hardcoded copies of an argument list drift: the review
pipeline paid for exactly that with a log line claiming a model the run had not
used. The gate has already constrained `--model` to its allowlist before this
runs, so nothing arbitrary reaches the flag from here and this script does NOT
re-validate the model. That is not an oversight to correct in a port: adding a
second allowlist here would put two lists in the tree that can disagree, which
is the failure this file was written to end.

EFFORT HAS TWO SOURCES AND THEY ANSWER DIFFERENT QUESTIONS, carried over from
the twin because the distinction is the whole design:

  --effort      the DISPATCH input: one human, one hard failure, this round
                only. Deliberately not recorded in the campaign.
  --effort-var  the AUTOPILOT_EFFORT repo VARIABLE: the standing setting for
                AUTONOMOUS rounds, which have no dispatcher to ask. Without it
                every unattended round ran at the model's own default and the
                operator's only lever was to dispatch each round by hand.

The dispatch input WINS when present, because a human aiming at one round knows
something the standing setting does not. An unrecognised value is IGNORED
LOUDLY (`::notice`) rather than passed through: `--effort banana` would fail the
round after paying for the runner, and a silent drop would leave the operator
believing a setting was in force that never was. The two notices are worded
differently on purpose -- one says "ignoring it", the other adds "and running at
the model's default effort" -- and both are reproduced verbatim, because a
workflow log is read by a human looking for exactly those words.

`default` IS NOT A MEMBER OF THE ALLOWLIST, and it must not become one. It is
the dispatch input's way of saying "do not pass the flag at all", so it is
tested for separately (`!= "default"`) before the membership test. A port that
folded it into the list would emit `--effort default` and fail the round.

THE `${x-}` VERSUS `${x:-}` COMMENT IN THE TWIN DESCRIBES A DISTINCTION THAT
DOES NOT EXIST HERE, and saying so is more useful than copying the comment.
`${ARG_EFFORT-}` yields the empty string for a variable that is unset AND for
one set to empty; `${ARG_EFFORT:-}` yields the empty string for both as well,
because the default given is itself empty. The two spellings are identical at
this call site. The comment is right about the INTENT (an explicitly empty
value must read as absent) and the code achieves it either way. This port reads
a dict that simply has no key, and the `if not effort` test below is the same
test.

WHERE THE OUTPUT GOES, and the hazard in it. `::notice` lines and the argument
list BOTH go to STDOUT, while the closing summary goes to stderr through
`log_info`. So `resolve-model-args.sh --effort banana` prints the notice and
the flags interleaved on one stream, and a caller that consumed stdout as the
argument list would feed `::notice::autopilot: ...` to the CLI as a flag.
Nothing does that today -- the workflow reads `$GITHUB_OUTPUT`, which carries
only the flags -- so this is a hazard rather than a live bug, and the port
reproduces the streams exactly rather than quietly moving the notice to stderr.

K=5 LEDGER: `.ci/shadow/w7p6-resolve-model-args.observations.jsonl`.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "resolve-model-args.py"

USAGE = (
    "usage: resolve-model-args.sh --model <id> --mode <mode> "
    "[--effort <dispatch>] [--effort-var <variable>]"
)

# The only efforts the CLI accepts, as one string rather than a list, because the twin interpolates this exact CSV into both notice messages and a reader greps the log for it.
EFFORT_ALLOWED = "low,medium,high,xhigh,max"

# The dispatch input's way of saying "do not pass --effort at all". NOT a member
# of EFFORT_ALLOWED; see the docstring.
EFFORT_DEFAULT = "default"

# Turn budgets. `fix` rounds get more because they iterate against CI; a
# review-response round answers a bounded list of threads.
TURNS_DEFAULT = 60
TURNS_FIX = 80
MODE_FIX = "fix"

# The GITHUB_OUTPUT heredoc marker. FIXED, unlike compose-prompt.sh's random one, and that asymmetry is correct rather than an oversight: nothing in this output is attacker-influenced. The values are a model id the gate already allowlisted, an integer this file chose, a constant, and an effort drawn from EFFORT_ALLOWED, so there is no text here an outsider can steer into producing
# the marker.
ARGS_DELIM = "AUTOPILOT_ARGS_EOF"


def in_csv(value: str, csv: str) -> bool:
    """`in_csv` from the twin (`IFS=',' read -ra` then compare each item).

    The empty item is excluded (`[[ -n "$item" && ... ]]`), so an allowlist with
    a stray comma cannot make the empty string a member. Reproduced because the
    guard is the only thing standing between `--effort ''` and a member test
    that says yes.
    """
    return any(item and item == value for item in csv.split(","))


def resolve_effort(effort: str, effort_var: str) -> tuple[str, str, list[str]]:
    """(resolved effort, where it came from, notices to print).

    PURE, and separated from `main` exactly so the differential can drive the
    whole input cross-product without a subprocess: two sources, each of which
    can be absent, empty, `default`, a member, or junk, is 25 combinations, and
    every one of them has a defined answer here.

    The notices are RETURNED rather than printed so the caller decides the
    stream. The twin puts them on stdout; see the docstring for why that is
    preserved rather than corrected.
    """
    notices: list[str] = []
    resolved = ""
    source_of = ""

    if effort and effort != EFFORT_DEFAULT:
        if in_csv(effort, EFFORT_ALLOWED):
            resolved = effort
            source_of = "the dispatch input"
        else:
            notices.append(
                "::notice::autopilot: dispatch effort '%s' is not one of %s; ignoring it"
                % (effort, EFFORT_ALLOWED)
            )

    # NOT `elif`. The twin re-tests `-z "$resolved_effort"`, which means a REJECTED dispatch effort falls through to the variable rather than suppressing it. That is the behaviour a human wants (a typo'd dispatch should not also disable the standing setting), and it is why both notices can appear in one run.
    if not resolved and effort_var and effort_var != EFFORT_DEFAULT:
        if in_csv(effort_var, EFFORT_ALLOWED):
            resolved = effort_var
            source_of = "the AUTOPILOT_EFFORT variable"
        else:
            notices.append(
                "::notice::autopilot: AUTOPILOT_EFFORT is '%s', which is not one of %s; "
                "ignoring it and running at the model's default effort"
                % (effort_var, EFFORT_ALLOWED)
            )

    return resolved, source_of, notices


def build_args(model: str, mode: str, resolved_effort: str) -> str:
    """The argument list, newline-separated, exactly as the twin builds it.

    `--disallowed-tools Task,Agent` is unconditional: an autopilot round must
    not spawn sub-agents, because the round's turn budget is the only thing
    bounding what it costs, and a sub-agent's turns are not counted against it.
    """
    turns = TURNS_FIX if mode == MODE_FIX else TURNS_DEFAULT
    parts = [f"--model {model}", f"--max-turns {turns}", "--disallowed-tools Task,Agent"]
    if resolved_effort:
        parts.append(f"--effort {resolved_effort}")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    model = args.get("ARG_MODEL", "")
    mode = args.get("ARG_MODE", "")
    effort = args.get("ARG_EFFORT", "")
    effort_var = args.get("ARG_EFFORT_VAR", "")

    if not (model and mode):
        log.error(USAGE)
        return 2

    resolved_effort, source_of, notices = resolve_effort(effort, effort_var)
    for notice in notices:
        # STDOUT, like the twin's bare `echo`. See the docstring's hazard note.
        print(notice, flush=True)

    args_text = build_args(model, mode, resolved_effort)
    print(args_text, flush=True)

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write("args<<%s\n" % ARGS_DELIM)
            fh.write("%s\n" % args_text)
            fh.write("%s\n" % ARGS_DELIM)

    turns = TURNS_FIX if mode == MODE_FIX else TURNS_DEFAULT
    if resolved_effort:
        log.info(
            "round args: model %s, %d turns, effort %s (from %s)"
            % (model, turns, resolved_effort, source_of)
        )
    else:
        log.info("round args: model %s, %d turns, the model's default effort" % (model, turns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
