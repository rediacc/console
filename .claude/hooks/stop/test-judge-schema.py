#!/usr/bin/env python3
"""Controls for wl_judge.judge_schema_for -- when the judge MUST return a regression_gate.

Why this exists. The fix-signal is a separate prompt section (M.REGGATE_PROMPT, appended
as `extra`), while v7 deliberately shipped ONE schema in which `regression_gate` is
optional at the top level. Those two facts together let the model satisfy the schema while
omitting the object, after which wl_reggate reports

    regression_gate missing or incomplete: None

and the stop hook blocks by the no-escape-hatch rule. The block is correct; what is wrong
is that the session is blocked by a JUDGE error rather than by anything it did. Observed
live on 2026-08-28, on a turn whose fix was already gated.

Every control is a PAIR, because asserting that the signal makes the field required proves
nothing on its own: a builder that always required it would pass that half and would break
every ordinary stop. The paired assertion is that WITHOUT the signal it stays optional.

The third pair is the one that matters most and is easiest to get wrong: the builder must
not mutate the module-level JUDGE_SCHEMA. A dict returned by reference would make the
first fix-signal stop poison every later call in the same process.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_judge


class Tally:
    """A counter object rather than module globals: ruff's PLW0603 is right that a
    `global` statement here buys nothing, and the sibling test files already use this
    shape."""

    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got == want:
        return
    Tally.fails += 1
    print(f"  FAIL {label}: got {got!r}, want {want!r}", file=sys.stderr)


SIGNAL = "\n\nA FIX LANDED THIS TURN, so ALSO fill the `regression_gate` object.\n"

plain = wl_judge.judge_schema_for("")
signalled = wl_judge.judge_schema_for(SIGNAL)

# 1. The pair: required only when the prompt actually asks for it.
control(
    "no fix-signal leaves regression_gate optional", "regression_gate" in plain["required"], False
)
control(
    "a fix-signal makes regression_gate required", "regression_gate" in signalled["required"], True
)

# 2. Nothing else about the schema may drift, or a passing judge call starts failing
#    for reasons that have nothing to do with this switch.
control(
    "the base fields stay required", plain["required"][:3], ["verdict", "reason", "next_action"]
)
control(
    "the signalled schema keeps them too",
    signalled["required"][:3],
    ["verdict", "reason", "next_action"],
)

# 3. THE MUTATION PAIR. Ask for the signalled schema first, then the plain one: if the
#    builder handed back the module constant and appended to it, the plain schema would
#    now carry regression_gate and every ordinary stop would fail closed.
wl_judge.judge_schema_for(SIGNAL)
control(
    "the module constant is not mutated",
    "regression_gate" in wl_judge.JUDGE_SCHEMA["required"],
    False,
)
control(
    "a later plain call is unaffected",
    "regression_gate" in wl_judge.judge_schema_for("")["required"],
    False,
)

# 4. The marker is matched as a substring of a larger prompt, which is how it arrives.
control(
    "the signal is found inside surrounding prompt text",
    "regression_gate" in wl_judge.judge_schema_for("preamble\n" + SIGNAL + "\ntrailer")["required"],
    True,
)
control(
    "CONTROL: unrelated prompt text does not trip it",
    "regression_gate"
    in wl_judge.judge_schema_for("a fix landed, lowercase and different")["required"],
    False,
)

if Tally.fails:
    print(f"FAIL: {Tally.fails} of {Tally.count} control(s) failed", file=sys.stderr)
    sys.exit(1)
print(f"{Tally.count} control(s) passed")
