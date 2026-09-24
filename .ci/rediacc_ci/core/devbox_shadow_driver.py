#!/usr/bin/env python3
"""Both sides of the `core.devbox` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    PYTHONPATH=.ci python3 -m rediacc_ci.core.devbox_shadow_driver --side old --twin .ci/lib/devbox.sh --port .ci/rediacc_ci/core/devbox.py <scenario>
        drives the BASH: sources `.ci/lib/devbox.sh` through the same prelude `.ci/rediacc_ci/setup/bridge.py` uses, and calls the twin's own functions.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.devbox_shadow_driver --side new --twin .ci/lib/devbox.sh --port .ci/rediacc_ci/core/devbox.py <scenario>
        drives the PYTHON: `rediacc_ci.core.devbox`.

RUN AS A MODULE AND NEVER BY PATH, which is not a style choice. A by-path invocation puts `.ci/rediacc_ci/core` on `sys.path[0]` and nothing on it can find `rediacc_ci`, so the file would have to open with a hand-written `sys.path.insert`. `test_canonical_sys_path_hop.py` refuses exactly that, and `PYTHONPATH=.ci` plus `-m` removes the need rather than baselining it.

WHY THIS IS A THIRD DRIVER AND NOT A SCENARIO INSIDE `core/local_common_shadow_driver.py`. That file is the `core.local_common` differential and its ledger rows name it; a pair is one twin against one port, and folding a second twin into it would make `dead_python.py`'s shadow route admit both ports off either ledger.
One file per pair, on the `core/shadow_driver.py`, `rediacc_ci/dev`, `rediacc_ci/setup` and `rediacc_ci/docker` precedent.

ONE FILE AND NOT TWO, for the reason those files record: `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive only when it is named in a `.ci/shadow/*.jsonl` record, so a separate old-side module would be reported dead the day it landed. `--twin` and `--port` carry the two paths for the same reason, and BOTH are checked to exist before anything runs.

-----------------------------------------------------------------------------
NO SANDBOX, AND THAT IS THE POINT OF THE SUBJECT
-----------------------------------------------------------------------------
`core/local_common_shadow_driver.py` builds a temporary `CONSOLE_ROOT_DIR` with the checkout symlinked into it, because every function it drives reads or writes a real path and two of its scenarios MUTATE what they read.
Nothing here does. The three functions under comparison take strings and return strings, so the old side sources the library straight out of the checkout the tree id names, and the only temporary directory is the one holding the CORPUS FILES and the two capture files `probe` writes.
A driver that built a sandbox for a pure function would be adding a moving part whose failure would look like a divergence.

THE CORPUS IS BUILT IN PYTHON FOR BOTH SIDES and handed to bash as NUL-separated records.
Two hand-written corpora are two things that can drift, and an answer differing because the two inputs differed is a mismatch that says nothing about the port. NUL rather than newline because a slug argument may CONTAIN a newline, which is reproduced behaviour 3 and one of the cases most likely to be got wrong.

EVERY ANSWER IS COMPARED AS HEX.
`devbox_slugify` prints a bare newline for an empty answer, and `emit`-ing that directly would make an empty answer and a missing answer the same observation, which is the exact vacuity this campaign exists to stop. `hexfile` runs `od -An -v -tx1` over the capture file, so a trailing newline, a doubled newline and nothing at all are three different strings.

-----------------------------------------------------------------------------
THE SEVEN SCENARIOS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  slug-basic    the branch names a checkout really carries, plus the nine rows `test_gate_devbox_slug.py` pins: `feat//x` (the dash collapse), `Feature/ABC-123` (the lowering), `--lead-and-trail--` (both trims), an umlaut (multibyte as ONE dash), the empty string, `///` (everything sanitises away) and a 90-character name whose 40-character cut lands on a dash.
  slug-edge     the boundaries: 39, 40 and 41 characters, a cut landing on a dash and a cut landing just past one, a two-line argument, a leading newline, a trailing newline, a run of 60 dashes, a byte that is not valid UTF-8, a 4-byte emoji, a 3-byte CJK character, a control byte, and a 300-character argument.
  slug-fuzz     250 arguments from a deterministic generator, over an alphabet of ASCII letters, digits, dashes, slashes, spaces, dots, uppercase, a 2-byte, a 3-byte and a 4-byte character, a raw high byte and a newline. This is the scenario that would catch a rule that is right on every case somebody thought of.
  slug-utf8     the slug-basic corpus again with the SHELL under `LC_ALL=C.utf8` rather than `LC_ALL=C`. The twin forces `LC_ALL=C` on each stage of its own pipeline, and this is what proves it: the answers must be identical to slug-basic's, and the port has no locale at all.
  drift         all 27 combinations of three names over the empty string and two distinct values, plus every one-name and two-name arity, plus names carrying a space, a percent sign and a multibyte character.
  route-label   every code arm (000, 502, 404 and the catch-all) crossed with an empty and a non-empty hint and with every `routed` value including the empty string, which `${3:-unknown}` turns into `unknown`. Plus the codes that look like an arm and are not: `0`, `00`, `0000`, `4040`, a trailing space, a leading dash and a newline.
  arity         each function at 0, 1, 2, 3 and 4 arguments. Zero is the case worth the scenario: `devbox_slugify` answers the empty string because it is written `"${1:-}"`, while `devbox_slug_drift` and `devbox_route_label` die on `$1: unbound variable` under the `set -u` every sourcer runs with. Four arguments pins that the extra one is IGNORED rather than read.

WHAT IS NEVER DRIVEN HERE: the other thirty-nine functions in `.ci/lib/devbox.sh`. None of them is ported, and a ledger row is a claim of equivalence.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.core import devbox

# The prefix `shadow-gate --finding-re '^obs '` is pointed at. Deliberately not a cross or a FAIL: those already mean "a finding" to the comparator's marker table, and an observation that AGREES is not a failure.
OBS = "obs"

EXIT_CANNOT_RUN = 77

# The prelude `.ci/rediacc_ci/setup/bridge.py:35-39` runs before it dispatches anything, which is the real load path for this library: `run-legacy.sh` pulls in `constants.sh`, `toolchain.sh`, `local-common.sh` and `service.sh` and defines nothing else, and `devbox.sh` is sourced on top exactly as the `setup` arm does.
PRELUDE = r"""
set -euo pipefail
ROOT_DIR="$R"
source "$ROOT_DIR/.ci/legacy/run-legacy.sh"
source "$ROOT_DIR/.ci/lib/devbox.sh"

norm() {
    local s="$1"
    s="${s//$W/<work>}"
    s="${s//$R/<repo>}"
    s="${s//$HOME/<home>}"
    printf '%s' "$s"
}

emit() { printf 'obs %s\n' "$(norm "$1")"; }

# `<file>: line <N>: $1: unbound variable` names a line INSIDE the twin. The message is the twin's real behaviour and is compared; the file-and-line stamp in front of it is not reproducible by a port and is dropped on both sides. `[^ ]*` rather than `.*` so a message that itself contained the phrase could not eat the part being compared.
strip_loc() { printf '%s' "$1" | sed -E 's|^[^ ]*: line [0-9]+: ||'; }

# THE ANSWER IS COMPARED AS HEX, never as text. `devbox_slugify` prints a bare newline for an empty answer, and an observation carrying that directly would be indistinguishable from an observation carrying nothing. `-v` so a run of repeated bytes is not abbreviated to `*`.
hexfile() { LC_ALL=C od -An -v -tx1 <"$1" | LC_ALL=C tr -d ' \n'; }

# rc first, then stdout as hex, then stderr as text, so the two sides cannot differ on ORDER for a reason that is the harness rather than the subject. The subshell keeps a `set -u` death from taking this driver down with it, which is exactly what the `arity` scenario measures.
probe() {
    local name="$1"
    shift
    local rc l
    # NOT `if ( set -e; "$@" ); then`, and that spelling cost a wrong measurement in the `core.account` differential before it was fixed. A command in an `if` CONDITION runs with errexit suppressed, and the suppression propagates into a subshell created there, so the inner `set -e` is INERT: the trap `docs/agent-reference/TRAPS.md` calls errexit-rearmed-in-a-tested-command.
    set +e
    ( set -e; "$@" ) >"$W/.probe.out" 2>"$W/.probe.err"
    rc=$?
    set -e
    emit "$name rc=$rc out=$(hexfile "$W/.probe.out")"
    # `|| [[ -n "$l" ]]` IS NOT DECORATION. A bare `while IFS= read -r l` DROPS a final line that has no trailing newline, and without it the BASH side would under-report a message the twin really printed while the Python side reported it.
    while IFS= read -r l || [[ -n "$l" ]]; do emit "$name err| $(strip_loc "$l")"; done <"$W/.probe.err"
}
"""

# The prefix `strip_loc` removes above, applied identically on the port side, where it is a no-op because nothing in Python emits a bash source location.
BASH_LOCATION_RE = re.compile(r"^[^ ]*: line [0-9]+: ")

# A 90-character branch name, so the 40-character cut lands ON a dash and the second trim has something to do. `test_gate_devbox_slug.py:46` uses the same string.
LONG_BRANCH = (
    "feature/an-extremely-long-branch-name-that-nobody-would-ever-type-but-git-happily-accepts-x"
)

# The nine rows `test_gate_devbox_slug.py:49-59` pins, plus the branch shapes this repository really carries and the punctuation a shell argument can hold.
SLUG_BASIC = (
    "feat/x",
    "feat//x",
    "Feature/ABC-123",
    "--lead-and-trail--",
    "0826-2",
    "feat/über",
    "",
    "///",
    LONG_BRANCH,
    "main",
    "0914-1",
    "release/v1.2.3",
    "HEAD",
    "feat-x",
    "My Box/2",
    "dependabot/npm_and_yarn/zod-4.5.4",
    "user/Ünïcödé-brânch",
    "feature/ABC_123 and spaces",
    "-",
    "--",
    "a",
    "1",
    "z9",
    "UPPER",
    "MiXeD/CaSe",
    "trailing-",
    "-leading",
    "a--b",
    "a---b",
    "...",
    "a.b.c",
    "tab\there",
    "semi;colon",
    "quote'single",
    'double"quote',
    "back\\slash",
    "dollar$sign",
    "star*glob",
    "percent%s-and-%d",
    "brace{expansion}",
    "paren(s)",
    "at@sign",
    "plus+plus",
    "equals=sign",
    "tilde~home",
    "back`tick",
    "pipe|pipe",
    "amp&amp",
    "bang!bang",
    "hash#hash",
)

# The boundaries. A dash at index 39 makes the cut land on a dash; a dash at index 40 makes it land just past one, which is the pair that tells a 40-cap from a 41-cap.
SLUG_EDGE = (
    "a" * 39,
    "a" * 40,
    "a" * 41,
    "a" * 39 + "-bcd",
    "a" * 40 + "-bcd",
    "a" * 38 + "-" + "b" * 10,
    "a" * 20 + "/" + "b" * 30,
    "-" * 60,
    "a\nb",
    "\nleading-newline",
    "trailing-newline\n",
    "a\n\nb",
    "a\n\n\n",
    "\n",
    "\n\n",
    "-a\n-b-\nc-",
    "a" * 39 + "\n" + "b" * 39,
    "carriage\rreturn",
    "\x01\x02\x03",
    "a\x7fb",
    "ü",
    "üüü",
    "日本語",
    "a\U0001f389b",
    "\U0001f389",
    "\udcff",
    "a\udcffb",
    "\udcc3(",
    "İstanbul",
    "ıi",
    "ß",
    "x" * 300,
    "ab/" * 100,
    "ü" * 60,
)

# The deterministic generator for `slug-fuzz`. A hand-written LCG rather than `random`, because the corpus has to be the same bytes in five years: `random.Random`'s stream is stable within a Python version and is not promised across them, and a corpus that shifted would make an old ledger row describe inputs nothing can reproduce.
FUZZ_SEED = 0x5EED1234
FUZZ_COUNT = 250
FUZZ_MULTIPLIER = 6364136223846793005
FUZZ_INCREMENT = 1442695040888963407
FUZZ_MODULUS = 1 << 64
FUZZ_MAX_LENGTH = 50

# What the fuzz strings are built from. The three multibyte characters are 2, 3 and 4 bytes, the lone surrogate is a byte that is not valid UTF-8 at all, and the newline is here because `sed` trims PER LINE.
FUZZ_ALPHABET = (
    "a",
    "b",
    "z",
    "A",
    "Z",
    "0",
    "9",
    "-",
    "/",
    " ",
    ".",
    "_",
    "\t",
    "\n",
    "ü",
    "日",
    "\U0001f389",
    "\udcff",
)

# The three names `devbox_slug_drift` compares. The empty string is the live case (no container, or no state file), and the two distinct values are what a rename looks like.
DRIFT_VALUES = ("", "alpha", "beta")

# Names that are not plain identifiers, so a `printf` format confusion or a quoting slip in either side is visible.
DRIFT_ODD = ("a b", "100%s", "ümlaut", "-lead", "with\ttab")

# Every arm of `devbox_route_label`'s case, and the codes that LOOK like an arm and are not. A trailing space and a trailing newline both fall to the catch-all, which is what a port comparing numbers rather than strings would get wrong.
ROUTE_CODES = (
    "000",
    "502",
    "404",
    "200",
    "301",
    "0",
    "00",
    "0000",
    "4040",
    "40",
    "",
    " ",
    "404 ",
    " 404",
    "404\n",
    "-n",
    "-e",
    "*",
    "?",
    "[0-9][0-9][0-9]",
    "999",
)

# The hint is interpolated into the 502 arm through `${hint:+ -- $hint}`, so the empty one must make the suffix disappear entirely.
ROUTE_HINTS = ("", "./run.sh account dev (INSIDE the devbox)", "a -- b", "100%s", "two\nlines")

# The caller's claim about whether a router exists. The empty string is the one that matters: `${3:-unknown}` fires on it, so it is the UNKNOWN arm rather than a fourth case.
ROUTE_ROUTED = ("", "no", "yes", "unknown", "maybe", "YES", "No", "no ", "0", "1")

# The codes and hints the three-argument sweep crosses with every `routed` value. Kept short on purpose: the full cross of every code, hint and claim is 1,050 probes, and the arms that `routed` can change are these four.
ROUTE_TRIPLE_CODES = ("000", "502", "404", "200")
ROUTE_TRIPLE_HINTS = ("", "a hint")


class RefusalError(RuntimeError):
    """The driver cannot run, so its silence would not be evidence."""


# --------------------------------------------------------------------------- the corpus ---------------------------------------------------------------------------


def fuzz_corpus() -> list[str]:
    """`FUZZ_COUNT` arguments from the LCG above, lengths 0 to 49.

    The generator is written out rather than imported so the corpus is a function of this file alone. Length 0 is included deliberately: an empty argument is the case where the twin prints a bare newline, and a fuzz corpus that never produced one would leave reproduced behaviour 1 to the hand-written scenarios.
    """
    state = FUZZ_SEED
    out = []
    for _ in range(FUZZ_COUNT):
        state = (state * FUZZ_MULTIPLIER + FUZZ_INCREMENT) % FUZZ_MODULUS
        length = (state >> 33) % FUZZ_MAX_LENGTH
        characters = []
        for _ in range(length):
            state = (state * FUZZ_MULTIPLIER + FUZZ_INCREMENT) % FUZZ_MODULUS
            characters.append(FUZZ_ALPHABET[(state >> 33) % len(FUZZ_ALPHABET)])
        out.append("".join(characters))
    return out


def drift_cases() -> tuple[list[str], list[tuple[str, ...]], list[tuple[str, ...]]]:
    """The one-, two- and three-name calls, as three lists."""
    ones = [*DRIFT_VALUES, *DRIFT_ODD]
    twos: list[tuple[str, ...]] = [(one, two) for one in DRIFT_VALUES for two in DRIFT_VALUES]
    twos += [(odd, "alpha") for odd in DRIFT_ODD]
    threes: list[tuple[str, ...]] = [
        (one, two, three) for one in DRIFT_VALUES for two in DRIFT_VALUES for three in DRIFT_VALUES
    ]
    threes += [(odd, "alpha", "beta") for odd in DRIFT_ODD]
    threes += [("alpha", odd, "beta") for odd in DRIFT_ODD]
    threes += [("alpha", "beta", odd) for odd in DRIFT_ODD]
    return ones, twos, threes


def route_cases() -> tuple[list[str], list[tuple[str, ...]], list[tuple[str, ...]]]:
    """The one-, two- and three-argument calls, as three lists."""
    ones = list(ROUTE_CODES)
    twos: list[tuple[str, ...]] = [(code, hint) for code in ROUTE_CODES for hint in ROUTE_HINTS]
    threes: list[tuple[str, ...]] = [
        (code, hint, routed)
        for code in ROUTE_TRIPLE_CODES
        for hint in ROUTE_TRIPLE_HINTS
        for routed in ROUTE_ROUTED
    ]
    return ones, twos, threes


def slug_corpus(scenario: str) -> list[str]:
    """The arguments one slug scenario drives, in order."""
    if scenario in ("slug-basic", "slug-utf8"):
        return list(SLUG_BASIC)
    if scenario == "slug-edge":
        return list(SLUG_EDGE)
    if scenario == "slug-fuzz":
        return fuzz_corpus()
    raise RefusalError("scenario %r has no slug corpus" % scenario)


def write_records(path: pathlib.Path, fields: list[str]) -> None:
    """NUL-terminated fields, which is what the bash loops read.

    NUL rather than newline because an argument may CONTAIN a newline, and `surrogateescape` so a corpus entry that is not valid UTF-8 reaches bash as the byte it names rather than as a replacement character.
    """
    path.write_bytes(b"".join(field.encode("utf-8", "surrogateescape") + b"\0" for field in fields))


def build_fixtures(work: pathlib.Path, scenario: str) -> None:
    """Every input both sides read, built ONCE in Python. See the header."""
    if scenario.startswith("slug-"):
        write_records(work / "slug.bin", slug_corpus(scenario))
        return
    if scenario in ("drift", "route-label"):
        ones, twos, threes = drift_cases() if scenario == "drift" else route_cases()
        write_records(work / "one.bin", ones)
        write_records(work / "two.bin", [field for row in twos for field in row])
        write_records(work / "three.bin", [field for row in threes for field in row])
        return
    if scenario == "arity":
        return
    raise RefusalError("unknown scenario %r" % scenario)


# --------------------------------------------------------------------------- printing ---------------------------------------------------------------------------


def text_lines(text: str) -> list[str]:
    """The lines `while IFS= read -r` would see: none at all for empty text."""
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


class Printer:
    """The one emitter the new side goes through, matching the bash helpers above."""

    def __init__(self, work: pathlib.Path, repo: pathlib.Path) -> None:
        self.work = str(work)
        self.repo = str(repo)
        self.home = os.environ.get("HOME") or "/tmp"

    def norm(self, text: str) -> str:
        replaced = text.replace(self.work, "<work>").replace(self.repo, "<repo>")
        return replaced.replace(self.home, "<home>")

    def emit(self, text: str) -> None:
        print("%s %s" % (OBS, self.norm(text)))

    def probe(self, name: str, rc: int, out: str, err: str) -> None:
        """`probe`, in the same order and the same hex."""
        self.emit("%s rc=%d out=%s" % (name, rc, out.encode("utf-8", "surrogateescape").hex()))
        for line in text_lines(err):
            self.emit("%s err| %s" % (name, BASH_LOCATION_RE.sub("", line)))


def call(printer: Printer, name: str, fn) -> int:
    """Run one port call with its two streams captured, and print the same shape.

    The return-value mapping is the twin's: an `Outcome` carries both channels, a bare string is stdout with status 0, and a `DevboxError` carries the code bash's `set -u` death used and the message bash wrote to STDERR.
    That last part is the whole reason this is not a plain return value: a refusal that printed nothing would compare equal to a refusal that printed the wrong thing.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = fn()
        except devbox.DevboxError as exc:
            sys.stderr.write("%s\n" % exc)
            result = devbox.Outcome("", exc.code)
        if isinstance(result, devbox.Outcome):
            sys.stdout.write(result.out)
            rc = result.code
        elif isinstance(result, str):
            sys.stdout.write(result)
            rc = 0
        else:
            rc = int(result)
    printer.probe(name, rc, out.getvalue(), err.getvalue())
    return rc


# --------------------------------------------------------------------------- argv binding, shared by both sides ---------------------------------------------------------------------------


def port_slugify(argv: list[str]) -> str:
    """`devbox_slugify "$@"` as the port, with bash's own `$1` binding.

    No arguments is `None` and NOT the empty string, because the two are different calls even though `"${1:-}"` makes them the same answer. Keeping them distinct here is what lets the `arity` scenario compare the case rather than assume it.
    """
    return devbox.slugify_stdout(argv[0] if argv else None)


def port_slug_drift(argv: list[str]) -> devbox.Outcome:
    """`devbox_slug_drift "$@"`, binding `$1`, `${2:-}` and `${3:-}`."""
    return devbox.slug_drift(
        argv[0] if len(argv) > 0 else None,
        argv[1] if len(argv) > 1 else "",
        argv[2] if len(argv) > 2 else "",
    )


def port_route_label(argv: list[str]) -> devbox.Outcome:
    """`devbox_route_label "$@"`, binding `$1`, `${2:-}` and `${3:-unknown}`.

    The third default is applied INSIDE the port as well, because `${3:-unknown}` fires on an empty third argument as well as on a missing one and both callers have to reproduce both.
    """
    return devbox.route_label(
        argv[0] if len(argv) > 0 else None,
        argv[1] if len(argv) > 1 else "",
        argv[2] if len(argv) > 2 else devbox.ROUTED_UNKNOWN,
    )


PORT_FUNCTIONS = {
    "devbox_slugify": port_slugify,
    "devbox_slug_drift": port_slug_drift,
    "devbox_route_label": port_route_label,
}

# The arguments the `arity` scenario passes, in order. The fourth is here to pin that it is IGNORED: bash binds `$1`, `$2` and `$3` and never looks further, so a port that raised on an unexpected argument would diverge.
ARITY_ARGS = ("one", "two", "three", "four")
ARITY_MAX = len(ARITY_ARGS)


# --------------------------------------------------------------------------- the old side ---------------------------------------------------------------------------

SLUG_BODY = r"""
probe slug-noarg devbox_slugify
i=0
while IFS= read -r -d '' value; do
    probe "slug-$i" devbox_slugify "$value"
    i=$((i + 1))
done <"$W/slug.bin"
emit "count slug=$i"
"""

# One body for both three-argument functions: the loops are identical and only the name changes, so a second copy would be a second thing to keep in step.
CASE_BODY = r"""
probe %(fn)s-noargs %(fn)s
i=0
while IFS= read -r -d '' a; do
    probe "%(fn)s-1-$i" %(fn)s "$a"
    i=$((i + 1))
done <"$W/one.bin"
j=0
while IFS= read -r -d '' a && IFS= read -r -d '' b; do
    probe "%(fn)s-2-$j" %(fn)s "$a" "$b"
    j=$((j + 1))
done <"$W/two.bin"
k=0
while IFS= read -r -d '' a && IFS= read -r -d '' b && IFS= read -r -d '' c; do
    probe "%(fn)s-3-$k" %(fn)s "$a" "$b" "$c"
    k=$((k + 1))
done <"$W/three.bin"
emit "count one=$i two=$j three=$k"
"""

ARITY_BODY = r"""
for fn in devbox_slugify devbox_slug_drift devbox_route_label; do
    probe "$fn-0" "$fn"
    probe "$fn-1" "$fn" one
    probe "$fn-2" "$fn" one two
    probe "$fn-3" "$fn" one two three
    probe "$fn-4" "$fn" one two three four
done
emit "count arity=15"
"""

BASH_SCENARIOS = {
    "slug-basic": SLUG_BODY,
    "slug-edge": SLUG_BODY,
    "slug-fuzz": SLUG_BODY,
    "slug-utf8": SLUG_BODY,
    "drift": CASE_BODY % {"fn": "devbox_slug_drift"},
    "route-label": CASE_BODY % {"fn": "devbox_route_label"},
    "arity": ARITY_BODY,
}

# The one scenario that runs the SHELL under a multibyte locale. The twin forces `LC_ALL=C` on each stage of its own pipeline, so the answers must be identical to `slug-basic`'s; the port has no locale at all, which is what makes the comparison worth recording.
SCENARIO_LOCALE = {"slug-utf8": "C.utf8"}


def sandbox_env(work: pathlib.Path, repo: pathlib.Path, scenario: str) -> dict[str, str]:
    """The environment both sides run under, built the same way for each.

    Deliberately short: the subject reads no environment variable at all, and a driver that passed the caller's whole environment through would make that claim untestable. `HOME` is here only because the prelude's `norm` interpolates it, and an empty one would make that expansion an empty pattern which matches everywhere.
    """
    locale = SCENARIO_LOCALE.get(scenario, "C")
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME") or "/tmp",
        "LC_ALL": locale,
        "LANG": locale,
        "CONSOLE_ROOT_DIR": str(repo),
        "REDIACC_CI_ROOT": str(repo),
        "PYTHONDONTWRITEBYTECODE": "1",
        "W": str(work),
        "R": str(repo),
    }


def run_old(work: pathlib.Path, repo: pathlib.Path, scenario: str, env: dict[str, str]) -> int:
    """Source the twin through `bridge.py`'s own prelude and call its functions."""
    script = work / "driver.sh"
    script.write_text("%s\n%s" % (PRELUDE, BASH_SCENARIOS[scenario]), encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


# --------------------------------------------------------------------------- the new side ---------------------------------------------------------------------------


def run_slug(printer: Printer, scenario: str) -> int:
    """The four slug scenarios on the port side, which differ only in their corpus."""
    call(printer, "slug-noarg", lambda: port_slugify([]))
    corpus = slug_corpus(scenario)
    for index, value in enumerate(corpus):
        call(printer, "slug-%d" % index, lambda value=value: port_slugify([value]))
    printer.emit("count slug=%d" % len(corpus))
    return 0


def run_cases(printer: Printer, name: str) -> int:
    """`drift` and `route-label` on the port side, over the same three lists."""
    function = PORT_FUNCTIONS[name]
    ones, twos, threes = drift_cases() if name == "devbox_slug_drift" else route_cases()
    call(printer, "%s-noargs" % name, lambda: function([]))
    for index, one in enumerate(ones):
        call(printer, "%s-1-%d" % (name, index), lambda one=one: function([one]))
    for index, row in enumerate(twos):
        call(printer, "%s-2-%d" % (name, index), lambda row=row: function(list(row)))
    for index, row in enumerate(threes):
        call(printer, "%s-3-%d" % (name, index), lambda row=row: function(list(row)))
    printer.emit("count one=%d two=%d three=%d" % (len(ones), len(twos), len(threes)))
    return 0


def run_arity(printer: Printer) -> int:
    """Every function at every arity from zero to four, on the port side."""
    for name, function in PORT_FUNCTIONS.items():
        for count in range(ARITY_MAX + 1):
            argv = list(ARITY_ARGS[:count])
            call(
                printer,
                "%s-%d" % (name, count),
                lambda function=function, argv=argv: function(argv),
            )
    printer.emit("count arity=%d" % (len(PORT_FUNCTIONS) * (ARITY_MAX + 1)))
    return 0


def run_new(scenario: str, printer: Printer) -> int:
    """Drive `rediacc_ci.core.devbox` through the same scenario."""
    if scenario.startswith("slug-"):
        return run_slug(printer, scenario)
    if scenario == "drift":
        return run_cases(printer, "devbox_slug_drift")
    if scenario == "route-label":
        return run_cases(printer, "devbox_route_label")
    if scenario == "arity":
        return run_arity(printer)
    raise RefusalError("unknown scenario %r" % scenario)


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="one side of the core.devbox differential")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True, help="the bash file under comparison")
    parser.add_argument("--port", required=True, help="the Python module under comparison")
    parser.add_argument("scenario", choices=sorted(BASH_SCENARIOS))
    args = parser.parse_args(argv)

    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "devbox_shadow_driver: the %s %s does not exist under %s. A ledger row "
                "naming a file that is not there attests to nothing.\n" % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN

    for tool in ("bash", "od", "sed", "tr"):
        if shutil.which(tool) is None:
            sys.stderr.write(
                "devbox_shadow_driver: %s is not installed, so the old side would fail before "
                "it reached the twin and the comparison would prove nothing.\n" % tool
            )
            return EXIT_CANNOT_RUN

    work = None
    try:
        work = pathlib.Path(tempfile.mkdtemp(prefix="devbox-shadow-"))
        env = sandbox_env(work, repo, args.scenario)
        build_fixtures(work, args.scenario)
        if args.side == "old":
            return run_old(work, repo, args.scenario, env)
        return run_new(args.scenario, Printer(work, repo))
    except RefusalError as exc:
        sys.stderr.write("devbox_shadow_driver: %s\n" % exc)
        return EXIT_CANNOT_RUN
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
