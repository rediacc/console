#!/usr/bin/env python3
"""check:ci-language-policy -- the bash surface under .ci and .claude may only shrink.

WHY THIS EXISTS. docs/ci-overhaul/04-decisions.md ruling 7 (2026-09-06) settled one
language per folder: Python in `.ci` and `.claude`, TypeScript in `scripts/`,
JavaScript in `eslint-rules/`, and bash only as an allowlisted shim carrying a
BLOCKER reason. Until this file, NOTHING ENFORCED THAT. An audit on 2026-09-07 ran
`grep -rin 'language.policy'` across every tracked .ts/.py/.sh/.json and found no
gate, no baseline, no allowlist and no POLICY_FILES slot. Two plan boxes were
already written against a gate that did not exist: W1 P6 flips this policy strict
("no baseline file at all, only allowlisted bash remains") and W10 P5 hands the
BLOCKER strings to W1, which owns the gate. Neither had anything to act on.

WHAT IT IS TODAY: ADVISORY AND SHRINK-ONLY, NOT A CLEAN-TREE DEMAND. Measured
2026-09-07, 520 tracked bash files under the covered trees are NOT exempt. A gate
demanding zero would red the entire tree on the day it landed, and a gate that reds
everything gets suppressed within a day -- which is the precise failure mode
docs/agent-reference/suppressions.md exists to prevent. So the existing 520 are
frozen as a SET and the only thing refused is GROWTH. The port then drains the set,
and W1 P6 deletes the baseline file, at which point this same gate is strict with no
code change (see STRICT MODE below).

THE FLOOR IS A SET, NEVER A COUNT, and that is a programme requirement rather than a
preference: "floors must be set-based or corpus-derived, never hand-typed counts".
A count lets through the one change that matters most here -- delete one bash file
and add another in the same commit, and the total is unchanged while the surface has
grown a file nobody decided on. Composition is the claim; sizes are not that claim.
The same reasoning is why `--write-baseline` refuses a reseed that would ABSORB a new
path even when the total shrinks: see scripts/lib/shrink-only-baseline.ts, the
TypeScript twin of the guard reimplemented below, whose header records a real drain
that printed `2,189 -> 2,160` while quietly enshrining a violation created that hour.

STRICT MODE, which is W1 P6 and needs no edit here. A MISSING baseline file is not
"no debt recorded"; it is the strict state. Every non-exempt bash file is then a
finding. That direction is deliberate and it is also the safe one: deleting the
baseline to escape the gate makes the gate louder, not quieter.

WHERE THE TWO DATA FILES LIVE, AND WHY THEY ARE NOT IN THE SAME PLACE.
`.ci/policy/README.md` gives a four-clause predicate for what belongs in
`.ci/policy/`, and the two files land on opposite sides of clause 1 ("it is a
DECISION, not data") and clause 2 ("it is BLOCKER-gated"):

  * `.ci/policy/.language-policy-allowlist` PASSES all four. Every entry is a
    decision that a file stays bash forever, each carries a BLOCKER reason, this
    script parses it, and nothing discovers it by root path.
  * `.ci/config/language-policy-baseline.json` FAILS clauses 1 and 2. It is
    GENERATED from the tree by `--write-baseline`; its entries are measurements,
    not choices, and a per-entry BLOCKER would be a reason invented for a file
    nobody decided about. It sits beside the repo's other generated freezes
    (`.ci/config/secret-scope-baseline.json`,
    `.ci/config/tracked-credentials-baseline.json`), which is where a shrink-only
    baseline belongs here.

Putting the baseline in `.ci/policy/` would have looked tidier and would have made
520 unreviewed paths indistinguishable from three reviewed exemptions.

WHAT COUNTS AS BASH, and why it is not just `*.sh`. A rule keyed on the extension is
evaded by dropping the extension, so a shebang naming bash/sh/zsh counts too.
Measured 2026-09-07 that widening adds 4 files to the corpus (three tutorial
Rediaccfiles and .ci/breakpoint/breakpoint.conf) and ZERO to the non-exempt set, so
it costs nothing today and closes the hole before somebody finds it.

THIS GATE'S OWN TEST IS IN THE BASELINE, and that is worth stating rather than
hoping nobody notices. `.ci/scripts/test/gates/test-language-policy.sh` is bash, in a
tree this gate says should be Python, and it was written on the same day. It is there
because the battery that runs gate tests in CI discovers `test-*.sh` by glob
(.ci/scripts/test/run-all.sh:89 and .ci/rediacc_ci/battery.py), so a Python gate test
would not run in CI at all -- and a test that does not run is worth less than one
written in the wrong language. It drains when the battery's port finishes, like every
other entry, and it is deliberately NOT allowlisted: an allowlist entry would claim it
stays bash forever, which is not true.

THE BLOCKER VALIDATOR IS CALLED, NOT REIMPLEMENTED. The rule "a BLOCKER reason must
be substantive" already has three implementations in this tree and
`.ci/scripts/test/gates/test-blocker-golden-corpus.sh` exists to hold them to one
behaviour while they collapse into one. A fourth, in a fourth language, would make
that collapse harder for no gain, so this gate shells out to the canonical
`.ci/scripts/lib/blocker-validator.sh` and prints what it says.

Exit 0 clean, 1 on a finding or a vacuous corpus, 2 on a failed control, 77 when the
gate CANNOT RUN (no git, no bash, no validator). 77 is never a verdict.

---- gate ----
step: Language policy
needs: none
lane: quality-static
selftest: true
why: ruling 7 makes .ci and .claude Python; the bash surface there may shrink, never grow
---- end gate ----
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

import _cipath  # noqa: F401
from rediacc_ci.controls import Controls
from rediacc_ci.core import allowlist
from rediacc_ci.policy_paths import policy_path

ROOT = pathlib.Path(
    os.environ.get("LANGUAGE_POLICY_ROOT") or pathlib.Path(__file__).resolve().parents[3]
)
BASELINE = pathlib.Path(
    os.environ.get("LANGUAGE_POLICY_BASELINE")
    or ROOT / ".ci" / "config" / "language-policy-baseline.json"
)
# THROUGH THE SEAM (W4 P4a), with the environment override still in FRONT of it.
# The hardcoded join this replaces is the one that let `.language-policy-allowlist`
# land in `.ci/policy/` on 2026-09-07 while both POLICY_FILES lists stayed at
# fifteen names, with nothing red for a day: a reader that does not go through the
# seam cannot be counted by the inventory that checks the seam.
ALLOWLIST = pathlib.Path(
    os.environ.get("LANGUAGE_POLICY_ALLOWLIST") or policy_path(".language-policy-allowlist", ROOT)
)
# ANCHORED ON THIS FILE, NOT ON `ROOT`, and the difference is the whole point of the
# seam. `ROOT` is the tree being JUDGED and a test points it at a fixture; the
# validator is part of the INSTRUMENT and travels with the gate. Written the other way
# it read the fixture's non-existent copy and answered every fixture run with exit 77,
# which is a cannot-run that is really a bug in the gate. Caught 2026-09-07 by the
# gate test's very first case.
VALIDATOR = pathlib.Path(
    os.environ.get("LANGUAGE_POLICY_VALIDATOR")
    or pathlib.Path(__file__).resolve().parents[3]
    / ".ci"
    / "scripts"
    / "lib"
    / "blocker-validator.sh"
)

# The trees ruling 7 assigns to Python. Not configurable: a gate whose scope can be
# narrowed by an environment variable has a scope nobody can state.
COVERED_ROOTS = (".ci", ".claude")

KEY = "bashFiles"

# The BASELINE label used in prose. Held once so the refusal text and the drain
# instruction cannot drift apart.
BASELINE_LABEL = ".ci/config/language-policy-baseline.json"

# A `shim:` entry claims ONE line. Ruling 7's words are "one-line shims", so the
# constant is the ruling and not a tuning knob.
SHIM_MAX_LINES = 1

# THE THIRD KIND, ADDED 2026-09-09 FOR W7P6's NAMED PRECONDITION.
# `tree:` exempts a directory and `shim:` exempts a one-line file, so a file that is
# permanently bash, multi-line, and ALONE in its directory had nowhere to go: the two
# candidates for `.ci/bootstrap.sh` were `tree:.ci/` (which exempts the entire port
# backlog) and moving the file into a directory invented to hold it (which churns 34
# referencing files to satisfy a grammar). `file:` is the narrow one: ONE exact path,
# no line cap, and strictly narrower than the `tree:` entry it replaces.
#
# IT IS DELIBERATELY THE WEAKEST ORACLE, so the gate refuses it wherever a stronger
# one applies: a `file:` entry naming a ONE-LINE body is rejected by name and told to
# be a `shim:`, because `shim:` dies when the file grows and `file:` cannot. Without
# that rule `file:` is a superset of `shim:` and every future author picks the one
# that never complains, which retires a live check by accident.
KINDS = ("tree", "shim", "file")

SHEBANG_SHELLS = (b"bash", b"/sh", b" sh", b"zsh")


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


class CannotRun(Exception):  # noqa: N818
    """The gate cannot reach a verdict. Exit 77, never a verdict either way."""


def git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run git, turning "git is not installed" into a CANNOT RUN rather than a crash.

    EVERY git call in this file goes through here, the selftest's own fixture included.
    That is not tidiness: the fixture called subprocess.run directly for one revision,
    and on a machine with no git the gate answered with a 25-line Python traceback and
    exit 1 -- which reads as a real finding, or as flake, and in neither case tells the
    reader to install git. Caught 2026-09-07 by the gate test's missing-toolchain case,
    which is the only reason it is not still there.
    """
    try:
        return subprocess.run(["git", *args], capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CannotRun(
            "git is not on PATH, so the tracked-file enumeration this gate is built on\n"
            "  cannot run at all. Install git, or run this gate from a checkout."
        ) from exc


def _looks_like_bash(path: pathlib.Path) -> bool:
    """Read the first line and decide whether it names a shell.

    Deliberately generous about WHICH shell: `sh`, `bash` and `zsh` are all bash in
    the sense ruling 7 means (a shell script in a tree that is meant to be Python),
    and a gate that argued about dialects would be arguing about the wrong thing.
    """
    try:
        with path.open("rb") as handle:
            first = handle.readline(256)
    except OSError:
        return False
    if not first.startswith(b"#!"):
        return False
    return any(token in first for token in SHEBANG_SHELLS)


def is_bash(root: pathlib.Path, rel: str) -> bool:
    """Is this tracked path a shell script?

    Extension first because it is free and covers 579 of the 584 files measured on
    2026-09-07; the shebang probe is what stops the rule being evaded by renaming.
    """
    if rel.endswith((".sh", ".bash")):
        return True
    return _looks_like_bash(root / rel)


def tracked_files(root: pathlib.Path) -> list[str]:
    """Every tracked path under the covered roots, in git's own words.

    `git ls-files` and not a filesystem walk, because the policy is about what the
    repository SHIPS. An untracked scratch script is not a language-policy problem,
    and counting one would make the gate red on a colleague's working tree.

    NOT `--recurse-submodules`: ruling 7 is about `.ci` and `.claude`, which are in
    this repository. A submodule has its own CI and its own rules.
    """
    proc = git(["-C", str(root), "ls-files", "-z", "--", *COVERED_ROOTS])
    if proc.returncode != 0:
        raise CannotRun(
            "`git ls-files` failed in %s (exit %d). Without it there is no corpus, and a\n"
            "  gate with no corpus must not report anything.\n"
            "  git said: %s"
            % (root, proc.returncode, proc.stderr.decode("utf-8", "replace").strip() or "(nothing)")
        )
    return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]


def bash_corpus(root: pathlib.Path) -> list[str]:
    """Every tracked shell script under the covered roots, sorted."""
    return sorted(rel for rel in tracked_files(root) if is_bash(root, rel))


def effective_lines(root: pathlib.Path, rel: str) -> int:
    """How many lines of a shell script actually DO something.

    The shebang, blank lines, comments and a bare `set -euo pipefail` are not the
    program; a shim that is one line of work plus five lines of preamble is still a
    one-line shim. This is the oracle behind a `shim:` allowlist entry, so it errs
    toward counting MORE: anything it is unsure about is a line.
    """
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return SHIM_MAX_LINES + 1
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.split(" ")[0] == "set" and line.startswith("set -"):
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------


def parse_allowlist(text: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Parse the BLOCKER-gated allowlist into (kind, value, reason) triples.

    THE GROUPING IS NOT REIMPLEMENTED HERE ANY MORE. It used to be, on the
    argument that the bash reader returns through a nameref into an associative
    array with no useful subprocess encoding. That argument expired when the
    grammar moved into `rediacc_ci.core.allowlist`, which is Python, importable,
    and proved byte-compatible with both shared readers over a frozen corpus of
    every real list in this tree.

    THREE THINGS THE LOCAL COPY GOT WRONG, none of which had fired:

      * it split with `str.splitlines()`, which also breaks on \r, \x0b, \x0c,
        \x1c-\x1e, \x85, \u2028 and \u2029. None of those is a line boundary to
        either shared reader, so a reason carrying one parsed into more entries
        here than anywhere else.
      * `line.lstrip("#")` armed a reason from `## BLOCKER:`, which the shared
        grammar does not recognise. An entry under one would have been read as
        reasoned here and unreasoned everywhere else.
      * it had no inline `entry  # BLOCKER: reason` branch, so an entry written in
        the documented inline form parsed with an empty reason.

    What stays here is the part that IS this gate's: the `tree:`/`shim:` shape,
    and naming a malformed entry rather than dropping it. A dropped entry is an
    exemption that stops exempting, which surfaces as a mystery finding about a
    file nobody touched.
    """
    entries: list[tuple[str, str, str]] = []
    problems: list[str] = []
    for record in allowlist.parse_text(text):
        line = record.entry
        kind, _, value = line.partition(":")
        if kind not in KINDS or not value:
            problems.append(
                "%s:%d: %r is not an allowlist entry. Entries are `tree:<prefix>/`, "
                "`shim:<path>` or `file:<path>`; anything else is a typo that would "
                "silently exempt nothing." % (ALLOWLIST.name, record.line, line)
            )
            continue
        if kind == "tree" and not value.endswith("/"):
            problems.append(
                "%s:%d: `tree:%s` must end in a slash. Without it the prefix matches "
                "sibling directories that merely start with the same characters, which is "
                "how an exemption silently widens." % (ALLOWLIST.name, record.line, value)
            )
            continue
        entries.append((kind, value, record.blocker))
    return entries, problems


def blocker_quality_problem(entry: str, reason: str) -> str | None:
    """Ask the CANONICAL validator whether this reason is substantive.

    Shelled out on purpose. `.ci/scripts/lib/blocker-validator.sh` holds the
    30-character floor and the banned-phrase list, its TypeScript twin holds the same
    rule, and .ci/scripts/test/gates/test-blocker-golden-corpus.sh exists to keep them
    agreeing while they collapse into one implementation. A fourth copy, in Python,
    would be one more thing for that collapse to reconcile and one more place for the
    banned list to lose a phrase without anything breaking.
    """
    if not reason:
        return (
            "%s is missing a '# BLOCKER: <reason>' line above it. An exemption with no "
            "stated reason is indistinguishable from one nobody decided on." % entry
        )
    if not VALIDATOR.is_file():
        raise CannotRun(
            "the canonical BLOCKER validator is missing at %s, so no exemption reason in\n"
            "  %s can be judged. Restore the file; do not lower the bar to get past this."
            % (VALIDATOR, ALLOWLIST.name)
        )
    try:
        proc = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; validate_blocker_quality "$2" "$3" "$4"',
                "bash",
                str(VALIDATOR),
                entry,
                reason,
                str(ALLOWLIST),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CannotRun(
            "bash is not on PATH, so the canonical BLOCKER validator\n"
            "  (.ci/scripts/lib/blocker-validator.sh) cannot be consulted and no exemption\n"
            "  reason can be judged. Install bash, or run this gate where bash exists."
        ) from exc
    # Exit 2 is the library refusing to LOAD (its bash 4.3 precondition), which is a
    # cannot-run rather than a verdict about the reason. Exit 1 is a real rejection.
    if proc.returncode not in {0, 1}:
        raise CannotRun(
            "the BLOCKER validator exited %d rather than judging the reason for %s.\n"
            "  Its bash 4.3 precondition is the usual cause; a validator that fails to\n"
            "  load parses every allowlist as EMPTY, which is why this is not a pass.\n"
            "  It said: %s" % (proc.returncode, entry, (proc.stdout + proc.stderr).strip())
        )
    if proc.returncode == 0:
        return None
    return (proc.stdout + proc.stderr).strip()


def exemption_for(rel: str, entries: list[tuple[str, str, str]]) -> tuple[str, str] | None:
    """The allowlist entry covering this path, or None."""
    for kind, value, _ in entries:
        if kind == "tree" and rel.startswith(value):
            return (kind, value)
        if kind in {"shim", "file"} and rel == value:
            return (kind, value)
    return None


def dead_entries(
    entries: list[tuple[str, str, str]], corpus: list[str], root: pathlib.Path
) -> list[str]:
    """Allowlist entries that suppress nothing, which is how a list outlives its reasons.

    IN-GATE LIVENESS, on the `.runner-advice-allowlist` and
    `syncpack-source-exclusions.json` precedent recorded in
    docs/agent-reference/suppressions.md: the oracle (does this entry still cover a
    real bash file?) IS the comparison the gate already performs, so a separate probe
    in scripts/gates/check-suppression-liveness.ts would be a second implementation of the
    same question.

    The `shim:` oracle has a second half that matters more than the first. An entry
    whose file still exists but has GROWN past one line is dead in the way that
    counts: "it is a one-line shim" was the entire justification, and it stopped
    being true without the file ever being deleted.

    The `file:` oracle has a second half too, pointing the OTHER way: an entry whose
    file SHRANK to one line is refused and told to become a `shim:`, because at that
    point the stronger oracle applies and declining it is a choice to be watched less
    closely.
    """
    problems: list[str] = []
    for kind, value, _ in entries:
        if kind == "tree":
            if not any(rel.startswith(value) for rel in corpus):
                problems.append(
                    "tree:%s covers no bash file in the tree. Either the port finished and "
                    "the entry should be deleted, or the prefix is wrong and every file it "
                    "was meant to exempt is now being judged." % value
                )
            continue
        if value not in corpus:
            problems.append(
                "%s:%s is not a tracked bash file. Delete the entry -- an exemption that "
                "suppresses nothing is how a list outlives its reasons." % (kind, value)
            )
            continue
        lines = effective_lines(root, value)
        if kind == "file":
            # THE DOWNGRADE REFUSAL. See KINDS. A `file:` entry over a one-line body
            # buys nothing a `shim:` entry does not, and throws away the only oracle
            # that notices a shim turning into a program.
            if lines <= SHIM_MAX_LINES:
                problems.append(
                    "file:%s has %d effective line(s), so it is a one-line shim and must "
                    "be written `shim:%s`. The `file:` kind has no line oracle at all; "
                    "using it here would retire the check that notices this file growing "
                    "into a program." % (value, lines, value)
                )
            continue
        if lines > SHIM_MAX_LINES:
            problems.append(
                "shim:%s has %d effective lines, not %d. Its exemption says 'one-line shim', "
                "and that is the whole of its justification; a shim that grew into a program "
                "is a port that has to happen, not an entry to widen."
                % (value, lines, SHIM_MAX_LINES)
            )
    return problems


# ---------------------------------------------------------------------------
# The shrink-only guard
# ---------------------------------------------------------------------------
#
# This is a faithful port of the DECISION half of scripts/lib/shrink-only-baseline.ts
# (`baselineAdditions` and `writeBaselineVerdict`), kept in Python because ruling 7
# puts this gate in `.ci`. There is no Python binding for that module today and
# building one under `.ci/rediacc_ci/` would collide with the port that is in flight
# there this hour; see the report accompanying this gate, which names the resulting
# coverage gap in gate-test:shrink-only-composition out loud rather than leaving it
# to be discovered.
#
# ORDER IS LOAD-BEARING in `write_verdict`, exactly as it is in the twin: the missing
# baseline is decided FIRST, because every later rule reads the old set and with no
# file there is no old set. Deleting the baseline is otherwise the cheapest way to
# switch the whole rule off.


def baseline_additions(old: list[str], new: list[str]) -> list[str]:
    """Ids in the new set that are not in the old one, i.e. the set GREW."""
    known = set(old)
    return [entry for entry in new if entry not in known]


def write_verdict(*, baseline_exists: bool, first_seed: bool, additions: list[str]) -> str | None:
    """The complete `--write-baseline` decision. None means the write is allowed."""
    if not baseline_exists and not first_seed:
        return "missing-baseline"
    if not baseline_exists:
        return None
    return "would-grow" if additions else None


def render_refusal(verdict: str, added: list[str], previous: int, current: int) -> str:
    if verdict == "missing-baseline":
        return (
            "Refusing to write the baseline: %s does not exist.\n"
            "  With no previous baseline there is nothing to compare against, so all %d "
            "path(s)\n  would be recorded as debt with no check on what is among them, and "
            "DELETING the\n  file is therefore the cheapest way to defeat this rule. If this "
            "really is a first\n  seed, say so: --write-baseline --first-seed. If it is not, "
            "restore the file and\n  drain it instead." % (BASELINE_LABEL, current)
        )
    return (
        "Refusing to write the baseline: it would GAIN %d bash file(s) not in the current "
        "one.\n%s\n\n"
        "  The baseline shrinks. It never grows. A reseed that drains 30 and adds 1 still\n"
        "  LOOKS like progress in the totals (%d -> %d), which is exactly how a brand new\n"
        "  violation gets enshrined as permanent, invisible debt.\n\n"
        "  Port the file instead. Do NOT add it to %s."
        % (
            len(added),
            "\n".join("    %s" % a for a in added),
            previous,
            current,
            BASELINE_LABEL,
        )
    )


def read_baseline(path: pathlib.Path) -> list[str] | None:
    """The frozen set, or None when the file is absent (which is STRICT MODE)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(
            "%s exists but cannot be read (%s). A corrupt baseline is not an empty one:\n"
            "  treating it as empty would report every frozen path as a brand new finding.\n"
            "  Repair the JSON; do not delete the file." % (BASELINE_LABEL, exc)
        ) from exc
    value = data.get(KEY)
    if not isinstance(value, list):
        raise CannotRun(
            "%s has no `%s` array. Refusing to guess what the frozen set was."
            % (BASELINE_LABEL, KEY)
        )
    return sorted(str(v) for v in value)


NOTE = (
    "SHRINK-ONLY, AND GENERATED -- do not hand-edit. Tracked bash files under .ci and "
    ".claude that ruling 7 (docs/ci-overhaul/04-decisions.md) says should be Python, "
    "minus the permanent exemptions in .ci/policy/.language-policy-allowlist. This list "
    "may only lose members. A NEW path here is refused by "
    ".ci/scripts/quality/check_language_policy.py even when the total shrinks, because "
    "composition is the claim and a total is not. The goal state is that this FILE does "
    "not exist: W1 P6 deletes it, and its absence is what makes the gate strict. Drain it "
    "with `.ci/scripts/quality/check_language_policy.py --write-baseline` in the same "
    "commit that ports files, and never to make a red go away."
)


def write_baseline(current: list[str], *, first_seed: bool) -> int:
    previous_or_none = read_baseline(BASELINE)
    exists = previous_or_none is not None
    previous = previous_or_none or []
    verdict = write_verdict(
        baseline_exists=exists,
        first_seed=first_seed,
        additions=baseline_additions(previous, current) if exists else [],
    )
    if verdict is not None:
        print(
            "\n✗ %s"
            % render_refusal(
                verdict,
                baseline_additions(previous, current) if exists else [],
                len(previous),
                len(current),
            ),
            file=sys.stderr,
        )
        return 1
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({"note": NOTE, KEY: current}, indent=2) + "\n", encoding="utf-8")
    drained = len([p for p in previous if p not in set(current)])
    print(
        "baseline written: %d path(s) (%d before, %d drained, 0 added)"
        % (len(current), len(previous), drained)
    )
    return 0


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions on every rule. A gate proven only to fire will flag the tree.

    The floor is what catches a battery that stopped executing: a file whose controls
    silently vanish otherwise prints nothing and exits 0, which reads exactly like a
    clean run. `rediacc_ci.controls.Controls` is used rather than a hand-rolled tally
    for that reason and because five copies of the hand-rolled one had already drifted
    (see .ci/rediacc_ci/controls.py's header).
    """
    controls = Controls("language policy", floor=32)
    # THE TREE UNDER TEST, not the one this file happens to live in. Anchoring on
    # __file__ here made the controls assert against the real repository even when the
    # caller had pointed the gate at a fixture, which is a coupling in the one place
    # that must not have one: it left a mutated COPY of this gate unable to reach its
    # own controls at all.
    here = ROOT

    # THE FIXTURES ARE BUILT, NOT BORROWED FROM THE TREE. An earlier draft asserted
    # against three real files (a .sh, a Rediaccfile with a shebang, the one-line
    # shim). Every one of those is a coupling that reds THIS gate when somebody edits
    # an unrelated file, and a control that fires on innocent edits is the fastest
    # route to a control being deleted. The one real-tree control kept below is the
    # anti-vacuity one, which has to be real or it asserts nothing.
    with tempfile.TemporaryDirectory() as tmp:
        box = pathlib.Path(tmp)
        (box / "plain.sh").write_text("echo hi\n", encoding="utf-8")
        (box / "Rediaccfile").write_text("#!/bin/bash\nup() { :; }\n", encoding="utf-8")
        (box / "tool.py").write_text("#!/usr/bin/env python3\nprint(1)\n", encoding="utf-8")
        (box / "shim.sh").write_text(
            '#!/usr/bin/env bash\n# a note\nset -euo pipefail\n\nexec other "$@"\n',
            encoding="utf-8",
        )
        (box / "program.sh").write_text("#!/usr/bin/env bash\nset -e\nfoo\nbar\n", encoding="utf-8")

        # -- what counts as bash ----------------------------------------------
        controls.check("a .sh file is bash", is_bash(box, "plain.sh"), True)
        controls.check("CONTROL: a .py file is NOT bash", is_bash(box, "tool.py"), False)
        controls.check(
            "a shebang'd file with no extension is bash", is_bash(box, "Rediaccfile"), True
        )
        controls.check(
            "CONTROL: a file that does not exist is not bash", is_bash(box, "nope/nope"), False
        )

        # -- the one-line shim oracle -----------------------------------------
        controls.check(
            "a shebang, a comment, `set -e` and one command is a ONE-line shim",
            effective_lines(box, "shim.sh"),
            1,
        )
        controls.check(
            "CONTROL: two commands is not a one-line shim, whatever the preamble says",
            effective_lines(box, "program.sh"),
            2,
        )

    # -- exemption matching ---------------------------------------------------
    entries = [
        ("tree", ".ci/media/", "r"),
        ("shim", ".ci/x/one.sh", "r"),
        ("file", ".ci/boot.sh", "r"),
    ]
    controls.truthy(
        "a tree: entry covers a file beneath it",
        exemption_for(".ci/media/tools/x.sh", entries),
    )
    controls.check(
        "CONTROL: a tree: entry does NOT cover a sibling with the same prefix",
        exemption_for(".ci/media-archive/x.sh", entries),
        None,
    )
    controls.truthy("a shim: entry covers its exact path", exemption_for(".ci/x/one.sh", entries))
    controls.check(
        "CONTROL: a shim: entry covers nothing else in its directory",
        exemption_for(".ci/x/two.sh", entries),
        None,
    )
    controls.truthy("a file: entry covers its exact path", exemption_for(".ci/boot.sh", entries))
    controls.check(
        "CONTROL: a file: entry is exact, not a prefix -- it does not cover a sibling",
        exemption_for(".ci/boot.sh.bak", entries),
        None,
    )

    # -- allowlist parsing ----------------------------------------------------
    parsed, problems = parse_allowlist(
        "# BLOCKER: because of a stated and sufficiently long reason\ntree:.ci/media/\n"
    )
    controls.check("a BLOCKER above an entry arms it", parsed[0][2][:7], "because")
    controls.check("a well-formed allowlist parses without problems", problems, [])
    parsed, _ = parse_allowlist(
        "# BLOCKER: a reason that is long enough to be substantive\n\ntree:.ci/media/\n"
    )
    controls.check("CONTROL: a blank line DISARMS the reason", parsed[0][2], "")
    parsed, _ = parse_allowlist(
        "# BLOCKER: a reason that is long enough to be substantive\n# an ordinary note\ntree:.ci/x/\n"
    )
    controls.truthy("an ordinary comment leaves the reason armed", parsed[0][2])
    parsed, problems = parse_allowlist(
        "# BLOCKER: a reason that is long enough to be substantive\nfile:.ci/bootstrap.sh\n"
    )
    controls.check(
        "the file: kind is a recognised entry, not a typo", (parsed[0][0], problems), ("file", [])
    )
    _, problems = parse_allowlist("junk:.ci/x/\n")
    controls.check("an unknown entry kind is a named problem", len(problems), 1)
    _, problems = parse_allowlist("tree:.ci/media\n")
    controls.check("CONTROL: a tree: entry with no trailing slash is refused", len(problems), 1)

    # -- allowlist liveness ---------------------------------------------------
    corpus = [".ci/media/a.sh", ".ci/other/b.sh"]
    controls.check(
        "a tree: entry covering a real file is live",
        dead_entries([("tree", ".ci/media/", "r")], corpus, here),
        [],
    )
    controls.check(
        "CONTROL: a tree: entry covering nothing is reported dead",
        len(dead_entries([("tree", ".ci/gone/", "r")], corpus, here)),
        1,
    )
    controls.check(
        "CONTROL: a shim: entry naming an untracked path is reported dead",
        len(dead_entries([("shim", ".ci/gone/x.sh", "r")], corpus, here)),
        1,
    )
    controls.check(
        "CONTROL: a file: entry naming an untracked path is reported dead",
        len(dead_entries([("file", ".ci/gone/boot.sh", "r")], corpus, here)),
        1,
    )
    with tempfile.TemporaryDirectory() as tmp:
        box = pathlib.Path(tmp)
        (box / ".ci").mkdir()
        (box / ".ci" / "boot.sh").write_text(
            "#!/usr/bin/env bash\nset -eu\nfoo\nbar\n", encoding="utf-8"
        )
        (box / ".ci" / "one.sh").write_text(
            "#!/usr/bin/env bash\nset -eu\nexec other\n", encoding="utf-8"
        )
        controls.check(
            "a file: entry over a MULTI-line tracked bash file is live",
            dead_entries([("file", ".ci/boot.sh", "r")], [".ci/boot.sh"], box),
            [],
        )
        controls.check(
            "CONTROL: a file: entry over a ONE-line body is refused and told to be a shim:",
            len(dead_entries([("file", ".ci/one.sh", "r")], [".ci/one.sh"], box)),
            1,
        )
        controls.truthy(
            "and the refusal names shim: as the kind to use instead",
            "shim:.ci/one.sh"
            in dead_entries([("file", ".ci/one.sh", "r")], [".ci/one.sh"], box)[0],
        )

    # -- the shrink-only guard, both halves -----------------------------------
    old = ["a.sh", "b.sh", "c.sh"]
    controls.check("a genuine shrink adds nothing", baseline_additions(old, ["a.sh", "c.sh"]), [])
    controls.check("an identical reseed adds nothing", baseline_additions(old, old), [])
    controls.check(
        "THE COMPOSITION TRAP: draining two and adding one is caught though the TOTAL shrinks",
        baseline_additions(old, ["a.sh", "new.sh"]),
        ["new.sh"],
    )
    controls.check(
        "the write path refuses a growing set",
        write_verdict(baseline_exists=True, first_seed=False, additions=["new.sh"]),
        "would-grow",
    )
    controls.check(
        "CONTROL: the write path ALLOWS a shrink, or the backlog would freeze forever",
        write_verdict(baseline_exists=True, first_seed=False, additions=[]),
        None,
    )
    controls.check(
        "a missing baseline is refused without --first-seed",
        write_verdict(baseline_exists=False, first_seed=False, additions=[]),
        "missing-baseline",
    )
    controls.check(
        "CONTROL: --first-seed permits a missing baseline",
        write_verdict(baseline_exists=False, first_seed=True, additions=[]),
        None,
    )
    controls.check(
        "CONTROL: --first-seed is not a blanket override when the baseline IS present",
        write_verdict(baseline_exists=True, first_seed=True, additions=["new.sh"]),
        "would-grow",
    )
    controls.truthy(
        "the refusal names the composition trap rather than just the count",
        "LOOKS like progress" in render_refusal("would-grow", ["new.sh"], 30, 29),
    )

    # -- the enumeration itself, on a repository built for the purpose ---------
    #
    # NOT AN ASSERTION ABOUT THE REAL TREE, deliberately. An earlier draft asserted
    # `len(bash_corpus(ROOT)) > 0` here, which is true of the repository and ALSO true
    # of the question `run()` already answers with a better message. Under a caller
    # that pointed the gate at an empty tree it fired first, so the reader got
    # "control failed, exit 2" instead of the VACUOUS refusal that names the cause.
    # The corpus floor belongs to the verdict; what belongs here is proof that the
    # ENUMERATION can tell a tree with bash in it from one without.
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp)
        (repo / ".ci").mkdir()
        (repo / ".ci" / "x.sh").write_text("echo x\n", encoding="utf-8")
        (repo / ".ci" / "notes.md").write_text("prose\n", encoding="utf-8")
        (repo / "elsewhere.sh").write_text("echo not covered\n", encoding="utf-8")
        git(["-C", str(repo), "init", "-q"])
        git(["-C", str(repo), "add", "-A", "--", "."])
        controls.check(
            "the enumeration finds tracked bash under a covered root",
            bash_corpus(repo),
            [".ci/x.sh"],
        )
        controls.check(
            "CONTROL: and ignores bash OUTSIDE the covered roots, and prose inside them",
            [rel for rel in bash_corpus(repo) if rel != ".ci/x.sh"],
            [],
        )
    controls.check(
        "CONTROL: a directory that is not a checkout raises CannotRun, it does not "
        "return a clean corpus",
        isinstance(_corpus_error(pathlib.Path("/nonexistent-checkout")), CannotRun),
        True,
    )

    ok = controls.report()
    return 0 if ok else 1


def _corpus_error(root: pathlib.Path) -> object:
    """Run the enumeration and hand back whatever it raised, for the control above."""
    try:
        return bash_corpus(root)
    except CannotRun as exc:
        return exc


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def run() -> int:
    corpus = bash_corpus(ROOT)
    if not corpus:
        print(
            "✗ VACUOUS: the enumeration found ZERO bash files under %s in %s.\n"
            "  Measured 2026-09-07 there were 584. Zero means the scan did not see the\n"
            "  tree, not that the port is finished, and its silence would mean nothing.\n"
            "  Check LANGUAGE_POLICY_ROOT and that this is a checkout of the console repo."
            % (", ".join(COVERED_ROOTS), ROOT),
            file=sys.stderr,
        )
        return 1

    if not ALLOWLIST.is_file():
        print(
            "✗ the exemption allowlist is missing at %s.\n"
            "  Without it every frozen tree (.ci/media, .ci/breakpoint, .ci/tutorials)\n"
            "  becomes a finding, so an absent file is refused rather than read as\n"
            "  'nothing is exempt'." % ALLOWLIST,
            file=sys.stderr,
        )
        return 1

    entries, problems = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    for kind, value, reason in entries:
        bad = blocker_quality_problem("%s:%s" % (kind, value), reason)
        if bad:
            problems.append(bad)
    problems.extend(dead_entries(entries, corpus, ROOT))
    if problems:
        print("✗ language policy: %d allowlist problem(s):" % len(problems), file=sys.stderr)
        for problem in problems:
            print("    %s" % problem, file=sys.stderr)
        return 1

    exempt = [rel for rel in corpus if exemption_for(rel, entries)]
    covered = [rel for rel in corpus if not exemption_for(rel, entries)]

    baseline = read_baseline(BASELINE)

    if baseline is None:
        # STRICT MODE. This is W1 P6, reached by DELETING the baseline file rather
        # than by editing this gate, which is why the plan box can be executed as
        # written.
        if covered:
            print(
                "✗ STRICT: %d bash file(s) under %s are neither exempt nor baselined,\n"
                "  and there is no baseline file. Ruling 7 makes these trees Python; the\n"
                "  only bash that survives is an allowlisted shim with a BLOCKER reason.\n"
                "  If the baseline was DELETED by accident, restore it. Do not reseed it to\n"
                "  make this quiet -- a reseed with no previous set records everything as\n"
                "  permanent debt with nothing checking what is among it."
                % (len(covered), ", ".join(COVERED_ROOTS)),
                file=sys.stderr,
            )
            for rel in covered[:20]:
                print("    %s" % rel, file=sys.stderr)
            if len(covered) > 20:
                print("    ... and %d more" % (len(covered) - 20), file=sys.stderr)
            return 1
        print(
            "✓ language policy STRICT: %d bash file(s) under %s, all %d of them "
            "allowlisted with a stated reason. No baseline file exists, which is the "
            "goal state." % (len(corpus), ", ".join(COVERED_ROOTS), len(exempt))
        )
        return 0

    added = baseline_additions(baseline, covered)
    if added:
        print(
            "✗ %d NEW bash file(s) under %s. Ruling 7 (2026-09-06) makes these trees\n"
            "  Python; the surface may shrink and may never grow:"
            % (len(added), ", ".join(COVERED_ROOTS)),
            file=sys.stderr,
        )
        for rel in added:
            print("    %s" % rel, file=sys.stderr)
        print(
            "\n  Write it in Python instead. If it genuinely must stay bash forever, add it\n"
            "  to %s with a BLOCKER reason\n"
            "  that says why. Do NOT add it to %s -- that file is the port's backlog and it\n"
            "  only shrinks." % (ALLOWLIST, BASELINE_LABEL),
            file=sys.stderr,
        )
        return 1

    drained = [rel for rel in baseline if rel not in set(covered)]
    if drained:
        print(
            "✗ %d baselined bash file(s) are gone from the tree. Ratchet the baseline\n"
            "  in the same commit, or the next author inherits a set that no longer\n"
            "  describes anything:" % len(drained),
            file=sys.stderr,
        )
        for rel in drained[:20]:
            print("    %s" % rel, file=sys.stderr)
        if len(drained) > 20:
            print("    ... and %d more" % (len(drained) - 20), file=sys.stderr)
        print(
            "\n  Run: .ci/scripts/quality/check_language_policy.py --write-baseline",
            file=sys.stderr,
        )
        return 1

    print(
        "✓ language policy: %d bash file(s) under %s -- %d frozen (shrink-only, "
        "none added), %d exempt by name across %d allowlist entr(ies)."
        % (len(corpus), ", ".join(COVERED_ROOTS), len(covered), len(exempt), len(entries))
    )
    for kind, value, _ in entries:
        n = len([rel for rel in corpus if exemption_for(rel, entries) == (kind, value)])
        print("    exempt %s:%s (%d file(s))" % (kind, value, n))
    print(
        "  Blind spot: this counts the SURFACE, not the port's quality. A bash file\n"
        "  rewritten as a Python file that shells out to bash leaves this gate green."
    )
    return 0


def main(argv: list[str]) -> int:
    # THE CANNOT-RUN HANDLER WRAPS THE CONTROLS TOO, not just the verdict. The
    # controls touch the real tree (they need a corpus that is really there), so on a
    # machine with no git the FIRST thing that fails is a control, and without this
    # placement the gate answered a missing binary with a Python traceback. A missing
    # tool has to read as "cannot run, here is the fix", never as a crash that the
    # next reader files as flake.
    try:
        if "--selftest" in argv:
            return selftest()

        # CONTROLS FIRST, ALWAYS, not only under --selftest. A gate whose controls run
        # in a separate invocation is a gate whose controls can be skipped by
        # registering the invocation without them, which has happened in this repo.
        print("language policy: controls first, then the verdict")
        if selftest() != 0:
            print(
                "✗ instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2

        if "--write-baseline" in argv:
            corpus = bash_corpus(ROOT)
            if not corpus:
                print(
                    "✗ VACUOUS: refusing to write a baseline from an empty enumeration.",
                    file=sys.stderr,
                )
                return 1
            if not ALLOWLIST.is_file():
                print(
                    "✗ refusing to write a baseline with no allowlist at %s: every\n"
                    "  exempt file would be frozen as debt." % ALLOWLIST,
                    file=sys.stderr,
                )
                return 1
            entries, problems = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
            if problems:
                print(
                    "✗ refusing to write a baseline while the allowlist has %d "
                    "problem(s); fix them first." % len(problems),
                    file=sys.stderr,
                )
                for problem in problems:
                    print("    %s" % problem, file=sys.stderr)
                return 1
            covered = [rel for rel in corpus if not exemption_for(rel, entries)]
            return write_baseline(covered, first_seed="--first-seed" in argv)
        return run()
    except CannotRun as exc:
        print(
            "⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc,
            file=sys.stderr,
        )
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
