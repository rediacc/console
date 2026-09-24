#!/usr/bin/env python3
"""Both sides of the `core.devbox` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    PYTHONPATH=.ci python3 -m rediacc_ci.core.devbox_shadow_driver --side old --twin .ci/lib/devbox.sh --port .ci/rediacc_ci/core/devbox.py <scenario>
        drives the BASH: sources `.ci/lib/devbox.sh` through the same prelude `.ci/rediacc_ci/setup/bridge.py` uses, and calls the twin's own functions.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.devbox_shadow_driver --side new --twin .ci/lib/devbox.sh --port .ci/rediacc_ci/core/devbox.py <scenario>
        drives the PYTHON: `rediacc_ci.core.devbox`.

RUN AS A MODULE AND NEVER BY PATH, which is not a style choice. A by-path invocation puts `.ci/rediacc_ci/core` on `sys.path[0]` and nothing on it can find `rediacc_ci`, so the file would have to open with a hand-written `sys.path.insert`. `test_canonical_sys_path_hop.py` refuses exactly that, and `PYTHONPATH=.ci` plus `-m` removes the need rather than baselining it.

WHY THIS IS A THIRD DRIVER AND NOT A SCENARIO INSIDE `core/local_common_shadow_driver.py`. That file is the `core.local_common` differential and its ledger rows name it; a pair is one twin against one port, and folding a second twin into it would make `dead_python.py`'s shadow route admit both ports off either ledger.
ONE FILE AND NOT TWO: `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive only when it is named in a `.ci/shadow/*.jsonl` record, so a separate old-side module would be reported dead the day it landed. `--twin` and `--port` carry the two paths for the same reason, and BOTH are checked to exist before anything runs.
The STUBS are this module too (`main(["stub", ...])`): a stub is a three-line bash script in a temporary directory that execs this module, so there is no tracked stub file for `dead_python.py` or `check:ci-no-inline-python` to judge, and the answer table is data the scenario builds.

-----------------------------------------------------------------------------
THE STUB-FARM TRANSCRIPT DIFFERENTIAL, which is the technique this ledger licenses
-----------------------------------------------------------------------------
The pure three need no sandbox and get none. Every other function reaches docker, the network, the filesystem, git or the port allocator, and the earlier slice refused them for want of a way to compare a side effect. The way is this:

  ONE STUB FARM, BUILT IN PYTHON, USED BY BOTH SIDES. `build_stub_farm()` writes one executable per name in `STUBBED` into `<work>/stub/bin`. Each one appends its argv to `<work>/stub/transcript.jsonl` as ONE JSON array per call, BEFORE it answers, and then answers from `<work>/stub/table.json`: an ordered list of rules, the first match wins, each rule an argv pattern (a positional `fnmatch` prefix) and an answer (stdout, stderr, status).
  A rule may also require an ordinal (`nth`: this is the Nth call matching the rule's pattern) or a history (`after` / `before`: some earlier call did or did not match another pattern). An unmatched call answers status 0 with no output. The same table file drives both sides because the SAME stub executable answers both sides.

  THE STUBS SHADOW THE REAL TOOLS, AND THAT IS PROVED, NOT ASSUMED. The bash side prepends the farm to PATH only AFTER the prelude is sourced (so `run-legacy.sh`'s own load-time probes stay real), and the port side is handed the identical PATH string. `test_core_devbox.py::test_the_stub_farm_really_shadows_docker` resolves `docker` through that PATH and requires the stub. No real `docker` mutation is ever issued: `docker run`, `rm`, `stop`, `start`, `network create`, `build` and `pull` are all argv in a transcript.

  WHAT IS REAL. `git`, against a fixture repository built in Python with a fixed identity, fixed dates and `GIT_CONFIG_GLOBAL=/dev/null`, so both sides see the same commits. `python3 -m rediacc_ci.core.ports`, which the twin and the port both run as a child; its own `ss` probes land in the farm, so the port block it picks is decided by the table rather than by whatever the host has listening.
  `basename`, `head`, `cut`, `sed`, `tr`, `grep`, `id`, `rm` and `od` are real on the bash side and reimplemented (or, for `rm`, shelled out) on the port side; their EFFECT is observed even where their call is not.

  WHAT ONE OBSERVATION IS. For every call: the status, stdout as HEX, stderr line by line (bash source locations stripped), then every stub call it made IN ORDER as the JSON the stub wrote, then the state file's bytes as hex or `absent`. The transcript is what makes "the same answer" a claim about the same WORK: a port that skipped a `docker version`, reordered a `ps`, or quoted one `-e` differently diverges on a line that names the call.

  THE WORK DIRECTORY IS A FIXED PATH, `<tmp>/devbox-shadow/<scenario>`, rebuilt from scratch by each side under an exclusive `flock`. Not `mkdtemp`: the worktree path is HASHED by `derive-slot` into the container name and the port block, so two sides in two random directories would disagree on a number for a reason that is the harness. The lock serialises two runs of one scenario; different scenarios never share a directory.

-----------------------------------------------------------------------------
THE PURE SCENARIOS (the first slice's seven, unchanged)
-----------------------------------------------------------------------------
THE CORPUS IS BUILT IN PYTHON FOR BOTH SIDES and handed to bash as NUL-separated records, NUL rather than newline because a slug argument may CONTAIN a newline. EVERY ANSWER IS COMPARED AS HEX: `devbox_slugify` prints a bare newline for an empty answer, and `hexfile` makes a trailing newline, a doubled newline and nothing at all three different strings.

  slug-basic    the branch names a checkout really carries, plus the nine rows `test_gate_devbox_slug.py` pins: `feat//x` (the dash collapse), `Feature/ABC-123` (the lowering), `--lead-and-trail--` (both trims), an umlaut (multibyte as ONE dash), the empty string, `///` and a 90-character name whose 40-character cut lands on a dash.
  slug-edge     39, 40 and 41 characters, a cut landing on a dash and just past one, a two-line argument, leading and trailing newlines, a run of 60 dashes, a byte that is not valid UTF-8, a 4-byte emoji, a 3-byte CJK character, a control byte, and a 300-character argument.
  slug-fuzz     250 arguments from a deterministic generator over ASCII letters, digits, dashes, slashes, spaces, dots, uppercase, 2-, 3- and 4-byte characters, a raw high byte and a newline.
  slug-utf8     the slug-basic corpus again with the SHELL under `LC_ALL=C.utf8`. The twin forces `LC_ALL=C` on each stage of its own pipeline, and this is what proves it.
  drift         all 27 combinations of three names over the empty string and two distinct values, plus every one-name and two-name arity, plus names carrying a space, a percent sign and a multibyte character.
  route-label   every code arm crossed with an empty and a non-empty hint and with every `routed` value including the empty string, plus codes that look like an arm and are not.
  arity         each pure function at 0 to 4 arguments. Zero is the case worth the scenario: `devbox_slugify` answers the empty string, the other two die on `$1: unbound variable`.

-----------------------------------------------------------------------------
THE STUB-FARM SCENARIOS, and what each one would catch
-----------------------------------------------------------------------------
  identity           devbox_worktree, mount_root (relative `--git-common-dir`), branch, slug_basename, slug (with and without `DEVBOX_SLUG`, including one that sanitises away), container_name, all four `devbox_docker` answers including both sudo arms, the two bind lists, `_devbox_bind_if_present` present/absent/arity, and `devbox_url` explicit, defaulted, through sudo, and SURVIVING a failing `docker ps` because the death of twin defect 7 does not cross a command substitution.
  identity-worktree  a LINKED worktree: mount_root answers the MAIN checkout from an absolute common dir, and build_image finds no Dockerfile there.
  identity-detached  a detached HEAD in a directory whose name needs the basename fallback, under `LC_ALL=C`, plus `devbox_up` against a drifted container that must NOT be rehosted because the branch is empty.
  identity-utf8      the same fixture under `LC_ALL=C.utf8`: the fallback hostname changes with the locale (twin defect 10), and a `\\u` escape in a logged label encodes rather than printing `\\u00FC`.
  identity-gone      a worktree directory that does not exist: the literal-path fallback, the state file that cannot be written, and a port block from the allocator.
  state              devbox_state_write at every arity and with `REDIACC_GATE_LANE`, devbox_state_get over present, missing, empty, duplicate, `=`-bearing, unterminated and regex-shaped keys (twin defect 11), and devbox_base_port from the record, from an empty record, and from the allocator with a busy first block.
  docker-query       container_id, container_running, slug_active, slug_conflicts (twin defect 3), router_hosts and missing_binds over every answer shape the daemon can give, including a failing `docker ps` (twin defect 7).
  proxy              network_ensure, proxy_running, proxy_ensure through every exit (already running, leftover started, leftover that will not start, run failure, a late answer, the 30-round timeout, a failing network, a failing `sleep`) and proxy_stop.
  image              image_present, image_digest (including a failing inspect that printed something), ensure_image through pull, force, the private-registry fallback and a failing build, and build_image.
  lifecycle          devbox_stop, devbox_remove (the state file really goes), devbox_logs and devbox_shell, each with and without a container and with a failing daemon.
  exec               devbox_exec's one-argument and many-argument shapes, zero arguments (twin defect 5), forwarded environment, sudo, and its status; then the three probes and devbox_doctor, including the not-running identity probe that passes (twin defect 2).
  exec-quote         devbox_exec over a corpus of argv built to exercise every `printf %q` rule: the backslash set, `~` and `#` by position, ANSI-C quoting, the empty word, non-UTF-8 bytes.
  exec-quote-utf8    the same corpus under `LC_ALL=C.utf8`, where a printable multibyte character is no longer ANSI-C quoted.
  status             devbox_status stopped, missing, running with every route label, drifted, conflicted (with a label that `echo -e` mangles, twin defect 4), with the proxy down, through sudo, and dying when the label inspect fails (twin defect 8).
  up-existing        devbox_up against an existing container: already running, drifted with and without the opt-out (both spellings), rehosted into a full create, bind drift, stopped then started, a start that does not come up, a start that fails (twin defect 9), and a removal that fails.
  up-create          devbox_up's create path: success, the slug refusal, image and proxy failures, no free block, no docker group (twin defect 1), an odd group line, no kvm gid, `docker run` failing, the container exiting, the 60-round timeout, an octal base port (twin defect 6), force-pull, a manual slug and sudo.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import fnmatch
import io
import json
import os
import pathlib
import re
import shlex
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

    def __init__(self, work: pathlib.Path, repo: pathlib.Path, home: str | None = None) -> None:
        self.work = str(work)
        self.repo = str(repo)
        # The HOME the SIDE ran under, which is the one `norm` in the bash prelude replaces: the driver's own for a pure scenario, the fixture's for a stub-farm one.
        self.home = home or os.environ.get("HOME") or "/tmp"

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


def run_old(work: pathlib.Path, repo: pathlib.Path, env: dict[str, str], script_text: str) -> int:
    """Source the twin through `bridge.py`'s own prelude and run `script_text` on top of it.

    The script is written with `surrogateescape` so an argument that is not valid UTF-8 reaches bash as its own bytes, and bash's output is passed through as BYTES for the same reason. stdin is `/dev/null`, which is what the port side is handed too: `devbox_exec`'s `[[ -t 0 ]]` must see the same answer on both sides.
    """
    script = work / "driver.sh"
    script.write_bytes(script_text.encode("utf-8", "surrogateescape"))
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(repo),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    sys.stdout.flush()
    sys.stdout.buffer.write(proc.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(proc.stderr)
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


# --------------------------------------------------------------------------- the stub farm ---------------------------------------------------------------------------

# Every external a stub-farm scenario may reach that is not safe or not deterministic to run for real. `docker` and `sudo` mutate the host; `curl` and `ss` read the network; `sleep` costs wall time; `getent` and `stat` read host facts a scenario must be able to choose.
STUBBED = ("curl", "docker", "getent", "sleep", "ss", "stat", "sudo")

# The stub itself. `${0##*/}` rather than `basename "$0"`, so a stub never runs an external before it has recorded itself. PYTHONPATH and the interpreter are ABSOLUTE, baked in when the farm is built, because a stub runs under whatever cwd the caller has.
STUB_SCRIPT = """#!/bin/bash
PYTHONPATH=%(ci)s exec %(python)s -m rediacc_ci.core.devbox_shadow_driver stub %(stub)s "${0##*/}" "$@"
"""


def build_stub_farm(work: pathlib.Path, repo: pathlib.Path) -> pathlib.Path:
    """`<work>/stub/bin/<name>` for every name in `STUBBED`, plus an empty table and transcript. Returns the bin directory."""
    stub = work / "stub"
    bin_dir = stub / "bin"
    bin_dir.mkdir(parents=True)
    text = STUB_SCRIPT % {
        "ci": shlex.quote(str(repo / ".ci")),
        "python": shlex.quote(sys.executable),
        "stub": shlex.quote(str(stub)),
    }
    for name in STUBBED:
        path = bin_dir / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    (stub / "table.json").write_text("[]", encoding="utf-8")
    (stub / "transcript.jsonl").write_text("", encoding="utf-8")
    return bin_dir


def rule_matches(pattern: list[str], argv: list[str], exact: bool = False) -> bool:
    """A positional `fnmatch` PREFIX match: every pattern token matches the argv token at its position."""
    if len(argv) < len(pattern) or (exact and len(argv) != len(pattern)):
        return False
    return all(fnmatch.fnmatchcase(word, token) for word, token in zip(argv, pattern, strict=False))


def pick_rule(table: list[dict], argv: list[str], previous: list[list[str]]) -> dict | None:
    """The first rule in `table` that answers `argv`, given the calls already made in this step."""
    for entry in table:
        if not rule_matches(entry["argv"], argv, entry.get("exact", False)):
            continue
        if "nth" in entry:
            ordinal = 1 + sum(
                rule_matches(entry["argv"], old, entry.get("exact", False)) for old in previous
            )
            if ordinal != entry["nth"]:
                continue
        if "after" in entry and not any(rule_matches(entry["after"], old) for old in previous):
            continue
        if "before" in entry and any(rule_matches(entry["before"], old) for old in previous):
            continue
        return entry
    return None


def stub_main(stub_dir: str, name: str, args: list[str]) -> int:
    """One stub call: record it, THEN answer it. Recording first is what keeps a concurrent reader (a process substitution) from seeing an answer before its call is on the transcript."""
    stub = pathlib.Path(stub_dir)
    argv = [name, *args]
    transcript = stub / "transcript.jsonl"
    previous = [
        json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line
    ]
    handle = os.open(str(transcript), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(handle, (json.dumps(argv) + "\n").encode("ascii"))
    finally:
        os.close(handle)
    table = json.loads((stub / "table.json").read_text(encoding="utf-8"))
    entry = pick_rule(table, argv, previous) or {}
    sys.stdout.buffer.write(entry.get("out", "").encode("utf-8", "surrogateescape"))
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(entry.get("err", "").encode("utf-8", "surrogateescape"))
    sys.stderr.buffer.flush()
    return int(entry.get("rc", 0))


# --------------------------------------------------------------------------- scenario vocabulary ---------------------------------------------------------------------------


class Step:
    """One call in a stub-farm scenario, and everything that is set up before it.

    `rules` is the WHOLE table for this call (tables do not carry over); `state` is `KEEP`, `ABSENT` or the exact bytes the state file holds before the call; `env` is exported and `unset` unset before it, and both persist into later steps exactly as `export` does. The tokens `{W}`, `{WT}` and `{HOME}` in args and rules are the work directory, the resolved worktree and the fixture HOME.
    """

    def __init__(self, label, fn, args=(), rules=(), state=None, env=None, unset=()):
        self.label = label
        self.fn = fn
        self.args = tuple(args)
        self.rules = list(rules)
        self.state = KEEP if state is None else state
        self.env = dict(env or {})
        self.unset = tuple(unset)


KEEP = "keep"
ABSENT = "absent"


def rule(*argv, out="", err="", rc=0, nth=None, after=None, before=None, exact=False) -> dict:
    """One answer-table entry. See `pick_rule` for the order the conditions are applied in."""
    entry: dict = {"argv": list(argv), "out": out, "err": err, "rc": rc}
    if exact:
        entry["exact"] = True
    if nth is not None:
        entry["nth"] = nth
    if after is not None:
        entry["after"] = list(after)
    if before is not None:
        entry["before"] = list(before)
    return entry


CID = "c0ffee000001"
IMAGE = devbox.DEVBOX_IMAGE
PROXY = devbox.DEVBOX_PROXY_NAME
WORKTREE_LABEL = '{{index .Config.Labels "%s"}}' % devbox.DEVBOX_LABEL_KEY
SLUG_LABEL = '{{index .Config.Labels "%s"}}' % devbox.DEVBOX_SLUG_LABEL_KEY
SLUG = "feat-box-one"


class Rules:
    """The answers a scenario gives the daemon, bound to the command prefix `$d` expands to."""

    def __init__(self, prefix=("docker",)) -> None:
        self.d = list(prefix)

    def ps_self(self, out, **kw):
        return rule(
            *self.d, "ps", "-aq", "--filter", "label=%s=*" % devbox.DEVBOX_LABEL_KEY, out=out, **kw
        )

    def ps_slug(self, out, **kw):
        return rule(
            *self.d,
            "ps",
            "-aq",
            "--filter",
            "label=%s=*" % devbox.DEVBOX_SLUG_LABEL_KEY,
            out=out,
            **kw,
        )

    def running(self, value, cid=CID, **kw):
        return rule(*self.d, "inspect", "-f", "{{.State.Running}}", cid, out=value, **kw)

    def slug_label(self, value, cid=CID, **kw):
        return rule(*self.d, "inspect", "-f", SLUG_LABEL, cid, out=value, **kw)

    def wt_label(self, cid, value, **kw):
        return rule(*self.d, "inspect", "-f", WORKTREE_LABEL, cid, out=value, **kw)

    def labels(self, out, cid=CID, **kw):
        return rule(
            *self.d, "inspect", "-f", "{{range $k, $v := .Config.Labels}}*", cid, out=out, **kw
        )

    def mounts(self, out, cid=CID, **kw):
        return rule(*self.d, "inspect", "-f", "{{range .Mounts}}*", cid, out=out, **kw)

    def proxy(self, value, **kw):
        return self.running(value, cid=PROXY, **kw)

    def live(self):
        """A container this worktree owns, running."""
        return [self.ps_self(CID + "\n"), self.running("true\n")]

    def run_pattern(self):
        return [*self.d, "run", "-d", "--name", "rediacc-devbox-[0-9]*"]


DOCKER = Rules()
SUDO = Rules(("sudo", "docker"))
NO_DOCKER_GROUP = rule("docker", "version", rc=1)


def route_labels(slug: str, routes=("code", "account", "db", "term")) -> str:
    """The label VALUES `docker inspect` would list for a container `devbox_up` created with `slug`, for the routes named."""
    host = {"code": slug, "account": slug + "-account", "db": slug + "-db", "term": slug + "-term"}
    lines = ["traefik.enable=true", "traefik.docker.network=%s" % devbox.DEVBOX_NETWORK]
    lines += ["Host(`%s.%s`)" % (host[route], devbox.DEVBOX_DOMAIN) for route in routes]
    lines += ["{WT}", slug]
    return "".join(line + "\n" for line in lines)


def status_curl(host: str, code: str, rc: int = 0) -> dict:
    return rule(
        "curl",
        "-s",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        "3",
        "-H",
        "Host: %s.localhost" % host,
        out=code,
        rc=rc,
    )


# Every destination a fully bound container reports: the repo, the four scripts, and the three home files the fixture HOME holds.
ALL_MOUNTS = "".join(
    line + "\n"
    for line in (
        "{WT}",
        *(pair.split(":", 1)[1] for pair in devbox.SCRIPT_BINDS),
        "/home/vscode/.gitconfig",
        "/home/vscode/.config/gh",
        "/home/vscode/.claude.json",
    )
)


def create_rules(
    d: Rules = DOCKER, *, proxy_up: bool = True, running_after: str = "true\n"
) -> list[dict]:
    """The daemon a fresh `devbox_up` meets: nothing of this worktree's until its own `docker run`, then a running container."""
    after = d.run_pattern()
    out = [
        d.ps_self(CID + "\n", after=after),
        d.running(running_after, after=after),
        d.slug_label(SLUG + "\n"),
        d.labels(route_labels(SLUG)),
        d.mounts(ALL_MOUNTS),
        rule(
            *d.d, "image", "inspect", "--format", out="ghcr.io/rediacc/devcontainer@sha256:feed\n"
        ),
        rule("getent", "group", "docker", out="docker:x:999:vscode\n"),
        rule("stat", out="993\n"),
    ]
    if proxy_up:
        out.append(d.proxy("true\n"))
    return out


# The argv `exec-quote` hands `devbox_exec`, each list one call. Built to reach every `printf %q` rule: the whole backslash set, `~` and `#` first and elsewhere, `~` after `:` and `=`, ANSI-C for control bytes and for high bytes under the C locale, the empty word, a lone argument that must pass VERBATIM, and a byte that is not UTF-8 at all.
EXEC_QUOTE_CORPUS = (
    ("echo", "a b"),
    ("printf", "%s\\n", "$HOME"),
    ("x", "it's", 'dq"x'),
    ("", "a", ""),
    ("~x", "x~", "a=~b", "a:~c", "#x", "x#", "a=b"),
    ("tab\there", "nl\nhere", "cr\rhere"),
    ("\x01\x7f\x1b", "\a\b\f\v"),
    ("a,b", "{a,b}", "[x]", "*", "?", "^x"),
    ("back\\slash", "`cmd`", "$(x)", "!bang", "a|b", "a&b", "a;b", "<in", ">out", "(p)"),
    ("-n", "--", "-e"),
    ("é", "日本", "üx"),
    ("a\udcffb",),
    ("only one argument with 'quotes' && $vars",),
    ("two", "words and 'quotes'"),
    ("%q", "%%", "\\"),
)


def exec_quote_steps() -> list[Step]:
    return [
        Step("q-%d" % index, "devbox_exec", argv, rules=DOCKER.live())
        for index, argv in enumerate(EXEC_QUOTE_CORPUS)
    ]


def identity_steps() -> list[Step]:
    return [
        Step("wt", "devbox_worktree"),
        Step("mount", "devbox_mount_root"),
        Step("branch", "devbox_branch"),
        Step("basename", "devbox_slug_basename"),
        Step("slug", "devbox_slug"),
        Step("slug-manual", "devbox_slug", env={"DEVBOX_SLUG": "Custom/Name_1"}),
        Step("slug-manual-empty", "devbox_slug", env={"DEVBOX_SLUG": "///"}),
        Step("slug-unset", "devbox_slug", unset=("DEVBOX_SLUG",)),
        Step("name", "devbox_container_name"),
        Step("docker", "devbox_docker"),
        Step("docker-sudo-n", "devbox_docker", rules=[NO_DOCKER_GROUP]),
        Step(
            "docker-sudo-prompt",
            "devbox_docker",
            rules=[NO_DOCKER_GROUP, rule("sudo", "-n", "docker", "version", rc=1)],
        ),
        Step("docker-none", "devbox_docker", rules=[NO_DOCKER_GROUP, rule("sudo", rc=1)]),
        Step("script-binds", "devbox_script_binds"),
        Step("home-binds", "devbox_home_binds"),
        Step(
            "bind-ro",
            "_devbox_bind_if_present",
            ("{HOME}/.gitconfig", "/home/vscode/.gitconfig", "ro"),
        ),
        Step(
            "bind-rw",
            "_devbox_bind_if_present",
            ("{HOME}/.config/gh", "/home/vscode/.config/gh", ""),
        ),
        Step(
            "bind-two",
            "_devbox_bind_if_present",
            ("{HOME}/.claude.json", "/home/vscode/.claude.json"),
        ),
        Step(
            "bind-absent", "_devbox_bind_if_present", ("{HOME}/.claude", "/home/vscode/.claude", "")
        ),
        Step("bind-0", "_devbox_bind_if_present"),
        Step("bind-1", "_devbox_bind_if_present", ("{HOME}/.gitconfig",)),
        Step("url-explicit", "devbox_url", ("", "named")),
        Step("url-suffix", "devbox_url", ("term", "named")),
        Step("url-default", "devbox_url"),
        Step("url-default-db", "devbox_url", ("db",)),
        Step(
            "url-container",
            "devbox_url",
            ("account",),
            rules=[DOCKER.ps_self(CID + "\n"), DOCKER.slug_label("baked-name\n")],
        ),
        Step(
            "url-sudo",
            "devbox_url",
            rules=[NO_DOCKER_GROUP, SUDO.ps_self(CID + "\n"), SUDO.slug_label("via-sudo\n")],
        ),
        Step(
            "url-ps-fails", "devbox_url", rules=[DOCKER.ps_self("", rc=1, err="Cannot connect\n")]
        ),
    ]


def worktree_steps() -> list[Step]:
    return [
        Step("wt", "devbox_worktree"),
        Step("mount", "devbox_mount_root"),
        Step("branch", "devbox_branch"),
        Step("slug", "devbox_slug"),
        Step("basename", "devbox_slug_basename"),
        Step("name", "devbox_container_name"),
        Step("url", "devbox_url"),
        Step("build-no-dockerfile", "devbox_build_image"),
    ]


def detached_steps(utf8: bool) -> list[Step]:
    steps = [
        Step("wt", "devbox_worktree"),
        Step("branch", "devbox_branch"),
        Step("basename", "devbox_slug_basename"),
        Step("slug", "devbox_slug"),
        Step("name", "devbox_container_name"),
    ]
    if not utf8:
        steps += [
            Step("mount", "devbox_mount_root"),
            Step("slug-manual", "devbox_slug", env={"DEVBOX_SLUG": "x"}),
            Step(
                "up-drift-no-branch",
                "devbox_up",
                unset=("DEVBOX_SLUG",),
                rules=[
                    *DOCKER.live(),
                    DOCKER.slug_label("old-name\n"),
                    DOCKER.mounts(ALL_MOUNTS),
                    DOCKER.proxy("true\n"),
                ],
            ),
        ]
    else:
        steps.append(
            Step(
                "status-escape",
                "devbox_status",
                rules=[
                    *DOCKER.live(),
                    DOCKER.slug_label("x\n"),
                    DOCKER.ps_slug("o1\n"),
                    DOCKER.wt_label("o1", "/w\\u00fcx\\ty\\U0001F389z\n"),
                ],
            )
        )
    return steps


def gone_steps() -> list[Step]:
    return [
        Step("wt", "devbox_worktree"),
        Step("mount", "devbox_mount_root"),
        Step("branch", "devbox_branch"),
        Step("basename", "devbox_slug_basename"),
        Step("slug", "devbox_slug"),
        Step("name", "devbox_container_name"),
        Step("write", "devbox_state_write", ("17010", "n", "d", "1", "s")),
        Step("get", "devbox_state_get", ("base_port",)),
        Step("base", "devbox_base_port"),
        Step("cid", "devbox_container_id"),
    ]


def state_steps() -> list[Step]:
    return [
        Step("get-missing", "devbox_state_get", ("base_port",), state=ABSENT),
        Step(
            "write-5",
            "devbox_state_write",
            ("17010", "rediacc-devbox-7-repo", "sha256:abc", "999", SLUG),
        ),
        Step("get-base", "devbox_state_get", ("base_port",)),
        Step("get-slug", "devbox_state_get", ("slug",)),
        Step("get-image", "devbox_state_get", ("image",)),
        Step("get-nokey", "devbox_state_get", ("nosuch",)),
        Step("get-empty-key", "devbox_state_get", ("",)),
        Step("get-dot", "devbox_state_get", ("base.port",)),
        Step("get-star", "devbox_state_get", ("sl*ug",)),
        Step("get-bracket", "devbox_state_get", ("[bs]lug",)),
        Step("get-noarg", "devbox_state_get"),
        Step(
            "write-lane",
            "devbox_state_write",
            ("17020", "n", "d", "", "s"),
            env={"REDIACC_GATE_LANE": "ci"},
        ),
        Step(
            "write-4",
            "devbox_state_write",
            ("17030", "n2", "d2", "5"),
            unset=("REDIACC_GATE_LANE",),
        ),
        Step("write-3", "devbox_state_write", ("1", "2", "3")),
        Step("write-0", "devbox_state_write"),
        Step(
            "get-dup",
            "devbox_state_get",
            ("base_port",),
            state=b"base_port=1\nbase_port=2\nslug=a=b\nlast=no-newline",
        ),
        Step("get-eq", "devbox_state_get", ("slug",)),
        Step("get-last", "devbox_state_get", ("last",)),
        Step("base-saved", "devbox_base_port", state=b"base_port=17420\n"),
        Step("base-empty", "devbox_base_port", state=b"base_port=\n"),
        Step("base-none", "devbox_base_port", state=ABSENT),
        Step(
            "base-busy",
            "devbox_base_port",
            rules=[rule("ss", out="LISTEN 0 4096 *:1 *:*\n", nth=1)],
        ),
        Step("base-full", "devbox_base_port", rules=[rule("ss", out="LISTEN\n")]),
    ]


def docker_query_steps() -> list[Step]:
    d = DOCKER
    ps = d.ps_self(CID + "\n")
    return [
        Step("cid-none", "devbox_container_id"),
        Step("cid-one", "devbox_container_id", rules=[ps]),
        Step("cid-two", "devbox_container_id", rules=[d.ps_self("aaa\nbbb\n")]),
        Step("cid-nonl", "devbox_container_id", rules=[d.ps_self("abc")]),
        Step(
            "cid-fail", "devbox_container_id", rules=[d.ps_self("", rc=1, err="Cannot connect\n")]
        ),
        Step("running-none", "devbox_container_running"),
        Step("running-true", "devbox_container_running", rules=d.live()),
        Step("running-false", "devbox_container_running", rules=[ps, d.running("false\n")]),
        Step("running-ps-fails", "devbox_container_running", rules=[d.ps_self("", rc=1)]),
        Step("active-none", "devbox_slug_active"),
        Step("active-label", "devbox_slug_active", rules=[ps, d.slug_label("old-slug\n")]),
        Step("active-novalue", "devbox_slug_active", rules=[ps, d.slug_label("<no value>\n")]),
        Step("active-empty", "devbox_slug_active", rules=[ps, d.slug_label("")]),
        Step("active-inspect-fails", "devbox_slug_active", rules=[ps, d.slug_label("", rc=1)]),
        Step("active-ps-fails", "devbox_slug_active", rules=[d.ps_self("", rc=3)]),
        Step("conflicts-none", "devbox_slug_conflicts"),
        Step(
            "conflicts-mixed",
            "devbox_slug_conflicts",
            rules=[
                d.ps_slug("id1\nid2\nid3\n"),
                d.wt_label("id1", "/other/wt\n"),
                d.wt_label("id2", "<no value>\n"),
                d.wt_label("id3", "{WT}\n"),
            ],
        ),
        Step(
            "conflicts-nonl",
            "devbox_slug_conflicts",
            rules=[
                d.ps_slug("id1\nid4"),
                d.wt_label("id1", "/other/wt\n"),
                d.wt_label("id4", "/never/seen\n"),
            ],
        ),
        Step(
            "conflicts-blank",
            "devbox_slug_conflicts",
            rules=[d.ps_slug("  id1\t\n\n"), d.wt_label("id1", "/o\n")],
        ),
        Step(
            "conflicts-arg",
            "devbox_slug_conflicts",
            ("explicit",),
            rules=[d.ps_slug("id1\n"), d.wt_label("id1", "/o\n")],
        ),
        Step("conflicts-manual", "devbox_slug_conflicts", env={"DEVBOX_SLUG": "Manual Slug"}),
        Step(
            "conflicts-ps-fails",
            "devbox_slug_conflicts",
            unset=("DEVBOX_SLUG",),
            rules=[d.ps_slug("", rc=1)],
        ),
        Step("hosts-none", "devbox_router_hosts"),
        Step(
            "hosts-labels",
            "devbox_router_hosts",
            rules=[
                *d.live(),
                d.labels(
                    "traefik.enable=true\ntraefik.http.routers.x-code.rule=Host(`x.localhost`)\n"
                    "left Host(`a`) mid Host(`b`) end\ncom.rediacc.devbox.slug=x\n"
                ),
            ],
        ),
        Step(
            "hosts-nonl", "devbox_router_hosts", rules=[*d.live(), d.labels("Host(`y.localhost`)")]
        ),
        Step("hosts-fail", "devbox_router_hosts", rules=[*d.live(), d.labels("Host(`z`)\n", rc=1)]),
        Step("missing-none", "devbox_missing_binds"),
        Step("missing-fail", "devbox_missing_binds", rules=[ps, d.mounts("", rc=1)]),
        Step("missing-empty", "devbox_missing_binds", rules=[ps, d.mounts("")]),
        Step("missing-all", "devbox_missing_binds", rules=[ps, d.mounts(ALL_MOUNTS)]),
        Step(
            "missing-some",
            "devbox_missing_binds",
            rules=[ps, d.mounts("/usr/local/bin/devbox-entrypoint.sh\n{WT}\n")],
        ),
        Step("missing-ps-fails", "devbox_missing_binds", rules=[d.ps_self("", rc=2)]),
    ]


def proxy_steps() -> list[Step]:
    d = DOCKER
    gone = rule("docker", "inspect", PROXY, exact=True, rc=1)
    return [
        Step("net-exists", "devbox_network_ensure"),
        Step(
            "net-create",
            "devbox_network_ensure",
            rules=[rule("docker", "network", "inspect", rc=1)],
        ),
        Step(
            "net-create-fails",
            "devbox_network_ensure",
            rules=[
                rule("docker", "network", "inspect", rc=1),
                rule("docker", "network", "create", rc=1, err="boom\n"),
            ],
        ),
        Step("running-true", "devbox_proxy_running", rules=[d.proxy("true\n")]),
        Step("running-false", "devbox_proxy_running"),
        Step("running-odd", "devbox_proxy_running", rules=[d.proxy("True\n")]),
        Step("ensure-running", "devbox_proxy_ensure", rules=[d.proxy("true\n")]),
        Step("ensure-leftover", "devbox_proxy_ensure"),
        Step(
            "ensure-leftover-bad-start",
            "devbox_proxy_ensure",
            rules=[rule("docker", "start", PROXY, rc=1, err="cannot start\n")],
        ),
        Step(
            "ensure-run-fails",
            "devbox_proxy_ensure",
            rules=[gone, rule("docker", "run", rc=125, err="Conflict.\n")],
        ),
        Step(
            "ensure-late",
            "devbox_proxy_ensure",
            rules=[gone, rule("curl", rc=7, nth=1), rule("curl", rc=7, nth=2)],
        ),
        Step(
            "ensure-timeout",
            "devbox_proxy_ensure",
            rules=[gone, rule("curl", rc=7), rule("docker", "logs", out="traefik log\n")],
        ),
        Step(
            "ensure-sleep-fails",
            "devbox_proxy_ensure",
            rules=[gone, rule("curl", rc=7), rule("sleep", rc=1)],
        ),
        Step(
            "ensure-net-fails",
            "devbox_proxy_ensure",
            rules=[
                rule("docker", "network", "inspect", rc=1),
                rule("docker", "network", "create", rc=1),
            ],
        ),
        Step("stop-not-running", "devbox_proxy_stop"),
        Step("stop-ok", "devbox_proxy_stop", rules=[d.proxy("true\n")]),
        Step(
            "stop-fails",
            "devbox_proxy_stop",
            rules=[d.proxy("true\n"), rule("docker", "stop", rc=1, err="no such\n")],
        ),
    ]


def image_steps() -> list[Step]:
    absent = rule("docker", "image", "inspect", IMAGE, exact=True, rc=1)
    digest = ("docker", "image", "inspect", "--format")
    return [
        Step("present", "devbox_image_present"),
        Step("absent", "devbox_image_present", rules=[absent]),
        Step(
            "digest",
            "devbox_image_digest",
            rules=[rule(*digest, out="ghcr.io/rediacc/devcontainer@sha256:0123\n")],
        ),
        Step("digest-fail", "devbox_image_digest", rules=[rule(*digest, rc=1)]),
        Step("digest-partial", "devbox_image_digest", rules=[rule(*digest, out="partial\n", rc=1)]),
        Step("ensure-present", "devbox_ensure_image"),
        Step("ensure-debug", "devbox_ensure_image", env={"DEBUG": "true"}),
        Step("ensure-force", "devbox_ensure_image", ("true",), unset=("DEBUG",)),
        Step("ensure-force-other", "devbox_ensure_image", ("yes",)),
        Step("ensure-pull", "devbox_ensure_image", rules=[absent]),
        Step(
            "ensure-pull-fails",
            "devbox_ensure_image",
            rules=[absent, rule("docker", "pull", rc=1, err="denied\n")],
        ),
        Step(
            "ensure-build-fails",
            "devbox_ensure_image",
            rules=[
                absent,
                rule("docker", "pull", rc=1),
                rule("docker", "build", rc=1, err="build failed\n"),
            ],
        ),
        Step("build", "devbox_build_image"),
        Step("build-fails", "devbox_build_image", rules=[rule("docker", "build", rc=2)]),
    ]


def lifecycle_steps() -> list[Step]:
    d = DOCKER
    ps = d.ps_self(CID + "\n")
    return [
        Step("stop-none", "devbox_stop"),
        Step("stop-ok", "devbox_stop", rules=[ps]),
        Step("stop-fails", "devbox_stop", rules=[ps, rule("docker", "stop", rc=1, err="x\n")]),
        Step("stop-ps-fails", "devbox_stop", rules=[d.ps_self("", rc=2)]),
        Step("remove-none", "devbox_remove", state=b"base_port=1\n"),
        Step("remove-ok", "devbox_remove", rules=[ps]),
        Step(
            "remove-rm-fails",
            "devbox_remove",
            state=b"base_port=1\n",
            rules=[ps, rule("docker", "rm", rc=1, err="busy\n")],
        ),
        Step("logs-none", "devbox_logs"),
        Step(
            "logs-default",
            "devbox_logs",
            rules=[ps, rule("docker", "logs", out="line 1\nline 2\n")],
        ),
        Step("logs-arg", "devbox_logs", ("--since=1h", "ignored"), rules=[ps]),
        Step("logs-empty-arg", "devbox_logs", ("",), rules=[ps]),
        Step("shell-none", "devbox_shell"),
        Step("shell-stopped", "devbox_shell", rules=[ps, d.running("false\n")]),
        Step("shell-ok", "devbox_shell", rules=d.live()),
        Step("shell-rc", "devbox_shell", rules=[*d.live(), rule("docker", "exec", rc=130)]),
    ]


def exec_steps() -> list[Step]:
    d = DOCKER
    live = d.live()
    forwarded = {
        "TERM": "xterm-256color",
        "GH_TOKEN": "t0k",
        "CI": "true",
        "NO_COLOR": "1",
        "GITHUB_TOKEN": "",
    }
    return [
        Step("not-running", "devbox_exec", ("true",)),
        Step("one", "devbox_exec", ("npm run -s check:x && echo ok",), rules=live),
        Step("many", "devbox_exec", ("bash", "-c", "npm run -s check:ci-shell-lint"), rules=live),
        Step("zero", "devbox_exec", rules=live),
        Step("env", "devbox_exec", ("env",), rules=live, env=forwarded),
        # TERM is EMPTIED rather than unset: `unset TERM` mid-script removes a variable bash would otherwise have defaulted to `dumb` at startup, which is a state no environment handed to a fresh shell can produce, so it is not a state the port is asked to reproduce. An empty TERM is, and it is not forwarded.
        Step(
            "env-cleared",
            "devbox_exec",
            ("env",),
            rules=live,
            unset=("CI", "NO_COLOR", "GH_TOKEN", "GITHUB_TOKEN"),
            env={"TERM": ""},
        ),
        Step("sudo", "devbox_exec", ("id",), rules=[NO_DOCKER_GROUP, *SUDO.live()]),
        Step(
            "rc",
            "devbox_exec",
            ("false",),
            rules=[*live, rule("docker", "exec", out="partial\n", err="boom\n", rc=3)],
        ),
        Step("mount-ok", "devbox_mount_ok", rules=live),
        Step(
            "mount-bad",
            "devbox_mount_ok",
            rules=[*live, rule("docker", "exec", rc=1, err="no run.sh\n")],
        ),
        Step(
            "identity-clean",
            "devbox_identity_ok",
            rules=[*live, rule("docker", "exec", out=" M file\n")],
        ),
        Step(
            "identity-dubious",
            "devbox_identity_ok",
            rules=[
                *live,
                rule(
                    "docker",
                    "exec",
                    err="fatal: detected dubious ownership in repository at '/x'\n",
                    rc=128,
                ),
            ],
        ),
        Step("identity-not-running", "devbox_identity_ok", rules=[d.ps_self(CID + "\n")]),
        Step("writable-ok", "devbox_writable_ok", rules=live),
        Step("writable-bad", "devbox_writable_ok", rules=[*live, rule("docker", "exec", rc=1)]),
        Step("doctor-ok", "devbox_doctor", rules=live),
        Step(
            "doctor-mount-bad", "devbox_doctor", rules=[*live, rule("docker", "exec", rc=1, nth=1)]
        ),
        Step(
            "doctor-dubious",
            "devbox_doctor",
            rules=[*live, rule("docker", "exec", nth=2, err="dubious ownership\n", rc=128)],
        ),
        Step("doctor-not-running", "devbox_doctor", rules=[d.ps_self(CID + "\n")]),
    ]


def status_steps() -> list[Step]:
    d = DOCKER
    base = [*d.live(), d.slug_label(SLUG + "\n"), d.labels(route_labels(SLUG)), d.proxy("true\n")]
    codes = [
        status_curl(SLUG, "200"),
        status_curl(SLUG + "-account", "502"),
        status_curl(SLUG + "-db", "404"),
        status_curl(SLUG + "-term", "000", rc=7),
    ]
    return [
        Step("none", "devbox_status", state=ABSENT),
        Step("stopped", "devbox_status", rules=[d.ps_self(CID + "\n"), d.running("false\n")]),
        Step(
            "running",
            "devbox_status",
            state=b"base_port=17010\nslug=%s\n" % SLUG.encode(),
            rules=[*codes, *base],
        ),
        Step(
            "no-router",
            "devbox_status",
            rules=[
                status_curl(SLUG + "-db", "404"),
                status_curl(SLUG + "-account", "404"),
                *d.live(),
                d.slug_label(SLUG + "\n"),
                d.labels(route_labels(SLUG, ("code",))),
                d.proxy("true\n"),
            ],
        ),
        Step(
            "drift",
            "devbox_status",
            state=b"base_port=17010\nslug=older\n",
            rules=[
                *d.live(),
                d.slug_label("old-name\n"),
                d.labels(route_labels("old-name")),
                d.proxy("true\n"),
            ],
        ),
        Step(
            "conflict",
            "devbox_status",
            rules=[
                *base,
                d.ps_slug("o1\no2\n"),
                d.wt_label("o1", "/other/x\\ty\\u00fcz\n"),
                d.wt_label("o2", "/cut\\chere\n"),
            ],
        ),
        Step(
            "proxy-down",
            "devbox_status",
            rules=[*d.live(), d.slug_label(SLUG + "\n"), d.labels(route_labels(SLUG))],
        ),
        Step("empty-code", "devbox_status", rules=[rule("curl", rc=28), *base]),
        Step(
            "sudo",
            "devbox_status",
            rules=[
                NO_DOCKER_GROUP,
                *SUDO.live(),
                SUDO.slug_label(SLUG + "\n"),
                SUDO.labels(route_labels(SLUG)),
                SUDO.proxy("true\n"),
            ],
        ),
        Step(
            "hosts-fail",
            "devbox_status",
            rules=[*d.live(), d.slug_label(SLUG + "\n"), d.labels("", rc=1)],
        ),
        Step("no-state", "devbox_status", state=ABSENT, rules=base),
    ]


def up_existing_steps() -> list[Step]:
    d = DOCKER
    removed = ("docker", "rm")
    started = ("docker", "start")
    settled = [d.running("true\n"), d.labels(route_labels(SLUG)), d.proxy("true\n")]
    drifted = [d.ps_self(CID + "\n"), d.slug_label("old-name\n"), d.mounts(ALL_MOUNTS), *settled]
    record = b"base_port=17010\nslug=old-name\n"
    after_run = d.run_pattern()
    rehost = [
        d.ps_self(CID + "\n", before=removed),
        d.ps_self(CID + "\n", after=after_run),
        d.slug_label("old-name\n", before=removed),
        d.slug_label(SLUG + "\n"),
        d.mounts(ALL_MOUNTS),
        *settled,
        rule("getent", "group", "docker", out="docker:x:999:vscode\n"),
        rule("stat", out="993\n"),
    ]
    return [
        Step(
            "running",
            "devbox_up",
            state=b"base_port=17010\nslug=%s\n" % SLUG.encode(),
            rules=[
                d.ps_self(CID + "\n"),
                d.slug_label(SLUG + "\n"),
                d.mounts(ALL_MOUNTS),
                *settled,
            ],
        ),
        Step("drift-no-rehost", "devbox_up", ("false", "--no-rehost"), state=record, rules=drifted),
        Step("drift-no", "devbox_up", ("false", "no"), rules=drifted),
        Step("drift-env", "devbox_up", env={"DEVBOX_NO_REHOST": "1"}, rules=drifted),
        Step("drift-env-true", "devbox_up", env={"DEVBOX_NO_REHOST": "true"}, rules=drifted),
        Step("drift-rehost", "devbox_up", unset=("DEVBOX_NO_REHOST",), state=record, rules=rehost),
        Step(
            "bind-drift-no-rehost",
            "devbox_up",
            ("false", "--no-rehost"),
            state=record,
            rules=[
                d.ps_self(CID + "\n"),
                d.slug_label(SLUG + "\n"),
                d.mounts("/usr/local/bin/devbox-entrypoint.sh\n"),
                *settled,
            ],
        ),
        Step(
            "bind-drift-rehost",
            "devbox_up",
            state=record,
            rules=[
                d.ps_self(CID + "\n", before=removed),
                d.ps_self(CID + "\n", after=after_run),
                d.slug_label(SLUG + "\n"),
                d.mounts("/usr/local/bin/devbox-entrypoint.sh\n", before=removed),
                d.mounts(ALL_MOUNTS),
                *settled,
                rule("getent", "group", "docker", out="docker:x:999:vscode\n"),
                rule("stat", out="993\n"),
            ],
        ),
        Step(
            "stopped-comes-up",
            "devbox_up",
            state=record,
            rules=[
                d.ps_self(CID + "\n"),
                d.slug_label(SLUG + "\n"),
                d.mounts(ALL_MOUNTS),
                d.running("false\n", before=started),
                *settled,
            ],
        ),
        Step(
            "stopped-stays-down",
            "devbox_up",
            rules=[
                d.ps_self(CID + "\n"),
                d.slug_label(SLUG + "\n"),
                d.mounts(ALL_MOUNTS),
                d.running("false\n"),
            ],
        ),
        Step(
            "start-fails",
            "devbox_up",
            rules=[
                d.ps_self(CID + "\n"),
                d.slug_label(SLUG + "\n"),
                d.mounts(ALL_MOUNTS),
                d.running("false\n"),
                rule("docker", "start", CID, rc=1, err="Error: cannot start\n"),
            ],
        ),
        Step(
            "remove-fails", "devbox_up", rules=[*drifted, rule("docker", "rm", rc=1, err="busy\n")]
        ),
    ]


def up_create_steps() -> list[Step]:
    d = DOCKER
    saved = b"base_port=17010\n"
    create = create_rules()
    fresh = rule(*d.run_pattern(), rc=125, err="docker: Error response from daemon\n")
    return [
        Step("ok", "devbox_up", state=saved, rules=create),
        Step(
            "conflict",
            "devbox_up",
            state=saved,
            rules=[d.ps_slug("zz\n"), d.wt_label("zz", "/elsewhere/wt\n"), *create],
        ),
        Step(
            "image-fails",
            "devbox_up",
            state=saved,
            rules=[
                rule("docker", "image", "inspect", IMAGE, exact=True, rc=1),
                rule("docker", "pull", rc=1),
                rule("docker", "build", rc=1),
                *create,
            ],
        ),
        Step(
            "proxy-fails",
            "devbox_up",
            state=saved,
            rules=[
                rule("docker", "inspect", PROXY, exact=True, rc=1),
                rule("docker", "run", "-d", "--name", PROXY, rc=125),
                *create_rules(proxy_up=False),
            ],
        ),
        Step("no-port", "devbox_up", state=ABSENT, rules=[rule("ss", out="LISTEN\n"), *create]),
        Step(
            "no-group",
            "devbox_up",
            state=saved,
            rules=[rule("getent", "group", "docker", rc=2), *create],
        ),
        Step(
            "odd-group",
            "devbox_up",
            state=saved,
            rules=[rule("getent", "group", "docker", out="docker:x\nweird\n"), *create],
        ),
        Step("no-kvm-gid", "devbox_up", state=saved, rules=[rule("stat", out=""), *create]),
        Step("run-fails", "devbox_up", state=saved, rules=[fresh, *create]),
        Step(
            "exited",
            "devbox_up",
            state=saved,
            rules=[
                rule("curl", "-fsS", rc=7),
                rule("docker", "logs", out="entrypoint crashed\n"),
                *create_rules(running_after="false\n"),
            ],
        ),
        Step(
            "timeout",
            "devbox_up",
            state=saved,
            rules=[
                rule("curl", "-fsS", rc=7),
                rule("docker", "logs", out="still booting\n"),
                *create,
            ],
        ),
        Step("octal", "devbox_up", state=b"base_port=017000\n", rules=create),
        Step("force", "devbox_up", ("true",), state=saved, rules=create),
        Step("manual-slug", "devbox_up", state=saved, env={"DEVBOX_SLUG": "My Name"}, rules=create),
        Step(
            "sudo",
            "devbox_up",
            state=saved,
            unset=("DEVBOX_SLUG",),
            rules=[NO_DOCKER_GROUP, *create_rules(SUDO)],
        ),
    ]


# (fixture, locale, steps) per stub-farm scenario. The fixtures are built by `build_fixture` below.
STUB_SCENARIOS = {
    "identity": ("main", "C", identity_steps),
    "identity-worktree": ("worktree", "C", worktree_steps),
    "identity-detached": ("detached", "C", lambda: detached_steps(False)),
    "identity-utf8": ("detached", "C.utf8", lambda: detached_steps(True)),
    "identity-gone": ("gone", "C", gone_steps),
    "state": ("main", "C", state_steps),
    "docker-query": ("main", "C", docker_query_steps),
    "proxy": ("main", "C", proxy_steps),
    "image": ("main", "C", image_steps),
    "lifecycle": ("main", "C", lifecycle_steps),
    "exec": ("main", "C", exec_steps),
    "exec-quote": ("main", "C", exec_quote_steps),
    "exec-quote-utf8": ("main", "C.utf8", exec_quote_steps),
    "status": ("main", "C", status_steps),
    "up-existing": ("main", "C", up_existing_steps),
    "up-create": ("main", "C", up_create_steps),
}

# Every scenario the driver offers, pure and stub-farm alike.
SCENARIOS = sorted([*BASH_SCENARIOS, *STUB_SCENARIOS])


# --------------------------------------------------------------------------- fixtures ---------------------------------------------------------------------------

# The detached fixture's directory name: an uppercase letter, an underscore, a dot, a two-byte character and a digit, so the basename fallback has something to sanitise and twin defect 10 has something to disagree about.
DETACHED_DIR = "My_Box.Ü-9"

# A fixed git identity and clock, so the fixture's commits are the same objects on both sides and on every run.
GIT_FIXED = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "shadow",
    "GIT_AUTHOR_EMAIL": "shadow@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "shadow",
    "GIT_COMMITTER_EMAIL": "shadow@example.invalid",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


def git_run(cwd: pathlib.Path, args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RefusalError(
            "the git fixture could not be built: `git %s` exited %d: %s"
            % (" ".join(args), proc.returncode, proc.stderr.strip())
        )


def init_repo(path: pathlib.Path, env: dict[str, str], dockerfile: bool) -> None:
    path.mkdir(parents=True)
    (path / "run.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    if dockerfile:
        (path / ".devcontainer").mkdir()
        (path / ".devcontainer" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    git_run(path, ["init", "-q", "-b", "main"], env)
    git_run(path, ["add", "-A"], env)
    git_run(path, ["commit", "-q", "-m", "fixture"], env)


def build_fixture(work: pathlib.Path, fixture: str, env: dict[str, str]) -> pathlib.Path:
    """The checkout `CONSOLE_ROOT_DIR` names, built once per side. Returns its path (which may not exist: `gone`)."""
    home = work / "home"
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".gitconfig").write_text("[user]\n\tname = shadow\n", encoding="utf-8")
    (home / ".claude.json").write_text("{}\n", encoding="utf-8")
    if fixture == "main":
        repo = work / "repo"
        init_repo(repo, env, dockerfile=True)
        git_run(repo, ["checkout", "-q", "-b", "feat/Box-One"], env)
        return repo
    if fixture == "worktree":
        main = work / "main"
        init_repo(main, env, dockerfile=False)
        git_run(main, ["worktree", "add", "-q", "-b", "feat/two", str(main / "wt-Two")], env)
        return main / "wt-Two"
    if fixture == "detached":
        repo = work / DETACHED_DIR
        init_repo(repo, env, dockerfile=True)
        git_run(repo, ["checkout", "-q", "--detach"], env)
        return repo
    if fixture == "gone":
        return work / "gone-Tree"
    raise RefusalError("unknown fixture %r" % fixture)


def expand(text: str, tokens: dict[str, str]) -> str:
    for token, value in tokens.items():
        text = text.replace(token, value)
    return text


def expand_rule(entry: dict, tokens: dict[str, str]) -> dict:
    out = dict(entry)
    out["argv"] = [expand(word, tokens) for word in entry["argv"]]
    out["out"] = expand(entry.get("out", ""), tokens)
    out["err"] = expand(entry.get("err", ""), tokens)
    return out


def resolved_steps(scenario: str, tokens: dict[str, str]) -> list[Step]:
    """The scenario's steps with every token expanded, identical for both sides."""
    steps = STUB_SCENARIOS[scenario][2]()
    for step in steps:
        step.args = tuple(expand(arg, tokens) for arg in step.args)
        step.rules = [expand_rule(entry, tokens) for entry in step.rules]
    labels = [step.label for step in steps]
    if len(set(labels)) != len(labels):
        raise RefusalError("scenario %s repeats a step label" % scenario)
    return steps


def stub_env(
    work: pathlib.Path, repo: pathlib.Path, scenario: str, root: pathlib.Path, bin_dir: pathlib.Path
) -> dict[str, str]:
    """The environment a stub-farm scenario runs under. `PATH` is the ORIGINAL one; the farm goes in front only after the prelude."""
    locale = STUB_SCENARIOS[scenario][1]
    base_path = os.environ.get("PATH", "/usr/bin:/bin")
    return {
        **GIT_FIXED,
        "PATH": base_path,
        "BASE_PATH": base_path,
        "FAKEBIN": str(bin_dir),
        "HOME": str(work / "home"),
        "LC_ALL": locale,
        "LANG": locale,
        "CONSOLE_ROOT_DIR": str(root),
        "REDIACC_CI_ROOT": str(repo),
        "GIT_CEILING_DIRECTORIES": str(work),
        "PYTHONDONTWRITEBYTECODE": "1",
        "W": str(work),
        "R": str(repo),
    }


def prepare_stub(
    work: pathlib.Path, repo: pathlib.Path, scenario: str
) -> tuple[dict[str, str], list[Step]]:
    """Build the farm, the fixture, and every per-step table and state file. Both sides call this and nothing else to set up."""
    bin_dir = build_stub_farm(work, repo)
    fixture = STUB_SCENARIOS[scenario][0]
    git_env = {
        **os.environ,
        **GIT_FIXED,
        "HOME": str(work / "home"),
        "GIT_CEILING_DIRECTORIES": str(work),
    }
    root = build_fixture(work, fixture, git_env)
    env = stub_env(work, repo, scenario, root, bin_dir)
    worktree = os.path.realpath(root) if root.is_dir() else str(root)
    tokens = {"{WT}": worktree, "{HOME}": str(work / "home"), "{W}": str(work)}
    steps = resolved_steps(scenario, tokens)
    (work / "tables").mkdir()
    (work / "states").mkdir()
    for index, step in enumerate(steps):
        (work / "tables" / ("%d.json" % index)).write_text(json.dumps(step.rules), encoding="utf-8")
        if isinstance(step.state, bytes):
            (work / "states" / str(index)).write_bytes(step.state)
    return env, steps


# --------------------------------------------------------------------------- the stub-farm old side ---------------------------------------------------------------------------

# Put the farm in front of PATH once the prelude has been sourced, and observe one call: `probe`'s status, stdout and stderr, then the transcript in order, then the state file.
STUB_PRELUDE = r"""
export PATH="$FAKEBIN:$BASE_PATH"
T="$W/stub/transcript.jsonl"

sprobe() {
    local name="$1"
    shift
    : >"$T"
    probe "$name" "$@"
    local line
    while IFS= read -r line || [[ -n "$line" ]]; do emit "$name call| $line"; done <"$T"
    if [[ -e "$DEVBOX_STATE_FILE" ]]; then
        emit "$name file| $(hexfile "$DEVBOX_STATE_FILE")"
    else
        emit "$name file| absent"
    fi
}
"""


def stub_body(steps: list[Step]) -> str:
    """The bash that replays `steps`: the table, the state file and the environment for each, then `sprobe`."""
    lines = [STUB_PRELUDE]
    for index, step in enumerate(steps):
        lines.append('cp -- "$W/tables/%d.json" "$W/stub/table.json"' % index)
        if step.state == ABSENT:
            lines.append('rm -f -- "$DEVBOX_STATE_FILE"')
        elif isinstance(step.state, bytes):
            lines.append('cp -- "$W/states/%d" "$DEVBOX_STATE_FILE"' % index)
        lines.extend("unset %s" % name for name in step.unset)
        lines.extend(
            "export %s=%s" % (name, shlex.quote(value)) for name, value in step.env.items()
        )
        lines.append(
            " ".join(
                [
                    "sprobe",
                    shlex.quote(step.label),
                    step.fn,
                    *(shlex.quote(arg) for arg in step.args),
                ]
            )
        )
    lines.append('emit "count steps=%d"' % len(steps))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- the stub-farm new side ---------------------------------------------------------------------------


def run_stub_new(
    work: pathlib.Path, repo: pathlib.Path, env: dict[str, str], steps: list[Step], printer: Printer
) -> int:
    """The same steps through `rediacc_ci.core.devbox`, observed the same way."""
    current = dict(env)
    current["PATH"] = env["FAKEBIN"] + ":" + env["BASE_PATH"]
    state_file = pathlib.Path(current["CONSOLE_ROOT_DIR"]) / devbox.DEVBOX_STATE_NAME
    transcript = work / "stub" / "transcript.jsonl"
    for index, step in enumerate(steps):
        shutil.copyfile(work / "tables" / ("%d.json" % index), work / "stub" / "table.json")
        if step.state == ABSENT:
            with contextlib.suppress(FileNotFoundError):
                state_file.unlink()
        elif isinstance(step.state, bytes):
            shutil.copyfile(work / "states" / str(index), state_file)
        for name in step.unset:
            current.pop(name, None)
        current.update(step.env)
        transcript.write_text("", encoding="utf-8")
        out_path, err_path = work / ".probe.out", work / ".probe.err"
        with (
            open(out_path, "wb", buffering=0) as out,
            open(err_path, "wb", buffering=0) as err,
            open(os.devnull, "rb") as stdin,
        ):
            status = devbox.Devbox(
                current, cwd=str(repo), stdout=out, stderr=err, stdin=stdin
            ).invoke(step.fn, step.args)
        printer.probe(
            step.label,
            status,
            out_path.read_bytes().decode("utf-8", "surrogateescape"),
            err_path.read_bytes().decode("utf-8", "surrogateescape"),
        )
        for line in text_lines(transcript.read_text(encoding="utf-8")):
            printer.emit("%s call| %s" % (step.label, line))
        if state_file.exists():
            printer.emit("%s file| %s" % (step.label, state_file.read_bytes().hex()))
        else:
            printer.emit("%s file| absent" % step.label)
    printer.emit("count steps=%d" % len(steps))
    return 0


# --------------------------------------------------------------------------- one side of one scenario ---------------------------------------------------------------------------


@contextlib.contextmanager
def work_dir(scenario: str):
    """`<tmp>/devbox-shadow/<scenario>`, emptied and held under an exclusive lock for the run. See the header for why the path is fixed."""
    base = pathlib.Path(tempfile.gettempdir()) / "devbox-shadow"
    base.mkdir(parents=True, exist_ok=True)
    with open(base / (scenario + ".lock"), "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        work = base / scenario
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()
        try:
            yield work
        finally:
            shutil.rmtree(work, ignore_errors=True)


def run_side(side: str, scenario: str, repo: pathlib.Path) -> int:
    """Build everything, then drive one side, printing its observations to stdout."""
    with work_dir(scenario) as work:
        if scenario in STUB_SCENARIOS:
            env, steps = prepare_stub(work, repo, scenario)
            if side == "old":
                return run_old(work, repo, env, "%s\n%s" % (PRELUDE, stub_body(steps)))
            return run_stub_new(work, repo, env, steps, Printer(work, repo, env["HOME"]))
        env = sandbox_env(work, repo, scenario)
        build_fixtures(work, scenario)
        if side == "old":
            return run_old(work, repo, env, "%s\n%s" % (PRELUDE, BASH_SCENARIOS[scenario]))
        return run_new(scenario, Printer(work, repo))


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if argv[:1] == ["stub"]:
        return stub_main(argv[1], argv[2], argv[3:])
    parser = argparse.ArgumentParser(description="one side of the core.devbox differential")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True, help="the bash file under comparison")
    parser.add_argument("--port", required=True, help="the Python module under comparison")
    parser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args(argv)

    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "devbox_shadow_driver: the %s %s does not exist under %s. A ledger row "
                "naming a file that is not there attests to nothing.\n" % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN

    for tool in ("bash", "od", "sed", "tr", "git"):
        if shutil.which(tool) is None:
            sys.stderr.write(
                "devbox_shadow_driver: %s is not installed, so the old side would fail before "
                "it reached the twin and the comparison would prove nothing.\n" % tool
            )
            return EXIT_CANNOT_RUN

    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="surrogateescape")
    try:
        return run_side(args.side, args.scenario, repo)
    except RefusalError as exc:
        sys.stderr.write("devbox_shadow_driver: %s\n" % exc)
        return EXIT_CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
