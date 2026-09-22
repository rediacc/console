r"""Type-check every Python file this repo ships, under the root pyproject.toml, shrink-only.

THE GAP THIS CLOSES. `check:ci-python-lint` runs ruff with `select = ["ALL"]`, which is a lot of rules and ZERO type inference.
ruff knows an import is unused and a name is undefined; it does not know that `list[tuple[str, str]].append` was handed a three-tuple, that `re.match(...)` returns `Match | None` and the next line reads `.group(1)` off it, or that a function annotated `-> str` returns an int. Every TypeScript tree here has had `tsc --noEmit` from the beginning.
The Python side had no equivalent at all until this gate, across 1,126 tracked files of which the Stop-hook program that gates every agent turn is one.

The first run found 935 of them. They are FROZEN in `.ci/config/python-types-baseline.json` and the only thing refused is GROWTH; see THE BASELINE below for why the total is not the claim.

-----------------------------------------------------------------------------
WHY mypy AND NOT pyright, WHICH WAS TRIED FIRST AND MEASURED.
-----------------------------------------------------------------------------

pyright is the obvious pick for this repo: it is an npm package in an npm monorepo, `npm ci` already runs in every quality lane, and it is the same shape as the `npx tsc --noEmit` this repo already reads as "the type checker". It was installed at 1.1.414 and pointed at this tree, and it analysed THREE files out of 1,126:

    Auto-excluding **/.*
    Found 3 source files

The pyright CLI excludes every directory whose name begins with a dot, unconditionally. The switch exists (`useDefaultExcludes`) but only a language-server host can set it; there is no config key and no flag. Naming a file directly does not get past it either, and this is the part that disqualifies it rather than merely annoying:

    $ pyright .ci/rediacc_ci/paths.py
    No source files found.
    0 errors, 0 warnings, 0 informations          <- exit 0

Every line of Python in this repository is under `.ci/` or `.claude/`. So the npm-native option is a gate that exits 0 having read none of the tree, which is the exact failure this file's own CONTROL section exists to prevent.
Reproduced in isolation on a scratch tree (`.dotdir/a.py` with a planted `-> str: return x`) so the finding is about pyright and not about this repo's config. mypy has no such rule: it checks the file list it is handed.

-----------------------------------------------------------------------------
THE THREE WAYS THIS GATE COULD BE GREEN WHILE PROVING NOTHING.
-----------------------------------------------------------------------------

All three are closed before a single real finding is judged, and each one is a refusal rather than a warning.

  1. AN EMPTY FILE LIST. `mypy` with no arguments at all exits 2, but `mypy`
     handed an empty @file exits 0 saying nothing. A gate whose input silently
     collapsed -- a moved tree, a `git ls-files` run outside a repo, a pathspec
     that stopped matching -- would report success forever. So the corpus is
     counted against MIN_PY_FILES, and the floor is a real number rather than 1
     because the interesting case is a glob that half-breaks.

  2. A CHECKER THAT IS NOT CHECKING, or is checking under the wrong config. A
     mypy that failed to find `pyproject.toml` still runs, still exits 0 on a
     clean-looking subset, and reports a DIFFERENT finding set -- which against a
     shrink-only baseline looks like "everything was fixed", not like a broken
     instrument. So a fixture is planted and four facts are required of the
     output at once; see CONTROL below.

  3. A VERSION THAT IS NOT THE PINNED ONE. mypy's finding set is a function of
     its bundled typeshed, so 2.1 and 2.3 disagree about code nobody edited. A
     host running a different mypy would produce a baseline diff in both
     directions, and an honest response to that diff cannot be told apart from a
     real regression. The resolver therefore accepts a binary only AT THE PIN
     (.devcontainer/toolchain.env, MYPY_VERSION) and says so when it refuses.

-----------------------------------------------------------------------------
CONTROL: FOUR FACTS, PLANTED, AND EACH ONE PINS A DIFFERENT THING.
-----------------------------------------------------------------------------

The fixture is built by CONSTRUCTION (a file written from a literal), never by substituting into real source, which is what `check:ci-python-control-plants` requires and what stops the plant silently no-opping.

  attr-defined PRESENT      `check_untyped_defs = true` is in force. This is THE
                            key for this codebase: mypy's default skips the body
                            of any function with no annotations, and most
                            functions here have none. Without it the gate reads
                            1,126 files and finds almost nothing -- green because
                            it looked away. The planted function is deliberately
                            un-annotated so this fires only under our config.
  return-value PRESENT      the checker is running at all, on inference that
                            needs no configuration.
  no-untyped-def ABSENT     we are NOT running under `--strict`. Measured on the
                            same fixture: `--strict` adds exactly this code.
                            Strict would mean 1061 findings that are all "this
                            untyped program is untyped", and a baseline nobody
                            can drain.
  import-not-found ABSENT   `ignore_missing_imports = true` is in force. This is
                            the key that makes the verdict a TREE fact instead of
                            an ENVIRONMENT fact, so it is the one most worth
                            pinning: see THE BASELINE.

Refuted, not merely asserted: run from a cwd with no `pyproject.toml`, the same fixture yields `import-not-found` and NO `attr-defined`, so both directions of the control distinguish the config rather than describing mypy.

mypy discovers its config from the CURRENT DIRECTORY, not by walking up from the file it is judging, which is the opposite of ruff and is why this control may live in a temp directory while the ruff gate's must live inside the repo. The gate chdirs to the repo root before anything runs, so a control passing from a temp path is evidence about the repo's config.

-----------------------------------------------------------------------------
THE BASELINE, AND THE TWO TRAPS IT IS BUILT AROUND.
-----------------------------------------------------------------------------

NOT KEYED ON A LINE NUMBER. A finding's id is a hash of (file, error code, message). A line number churns the moment a paragraph is inserted above it, and a baseline that churns gets regenerated wholesale, which is precisely how a fresh finding gets absorbed without anybody reading it.

MULTIPLICITY IS A COUNT, NOT A ROW PER LINE. Four identical `"object" has no attribute "get"` findings in one file collapse to one id, so the id carries `count: 4` and the gate fails when that count GROWS. Storing one row per occurrence would have forced the line number back in as a tiebreak.

COMPOSITION IS THE CLAIM, NOT THE TOTAL. `--write-baseline` refuses outright if the new set contains an id the old one did not, or a count higher than the old one, EVEN WHEN THE TOTAL FALLS. A drain that removes 30 and adds 1 reads as progress in the totals and enshrines a violation created that hour.
This is the same rule `scripts/lib/shrink-only-baseline.ts` states, whose header records the real `2,189 -> 2,160` drain that did exactly that.

A FIXED FINDING FAILS THE GATE TOO, and that half is what keeps the set shrinking: a baselined finding that stops firing must be DRAINED with `--write-baseline`, not left in the file. Without that, the baseline records the debt of a year ago forever and a real regression can hide inside a stale row.

THE RE-KEYING PRICE, stated because it will happen: an id survives a MOVE and cannot survive a REWRITE. Change a variable's type and the message changes, so the old id reads as fixed and the new one as brand new.
That is correct -- a rewrite is exactly when a human should look again -- but the right response is to hand-edit the one line, NOT to run `--write-baseline`, which rewrites every entry and would absorb any other finding that appeared in the meantime.

-----------------------------------------------------------------------------
WHY THE CORPUS IS RUN IN GROUPS.
-----------------------------------------------------------------------------

mypy refuses a file list containing two files that resolve to the same module name, and exits 2 having checked nothing:

    .ci/scripts/quality/_cipath.py: error: Duplicate module named "_cipath"
    (also at ".ci/scripts/docker/_cipath.py")

There are four such collisions in this tree today (`_cipath`, and `sanctioned` / `wl_planfid` / `worklist`, which exist under both `.claude/hooks/` and `.claude/oracles/`). The obvious fixes are both wrong: `--exclude` drops real files from the corpus silently, and `--explicit-package-bases` cannot name a root whose directory begins with a dot.
So the corpus is PARTITIONED into the fewest groups in which no module name repeats, and every group is checked. Today that is two groups of 1,122 and 4. A new collision grows a group rather than dropping a file, and the file count is printed on the success line so the split is visible.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import toolchain

# THE CORPUS IS THE RUFF GATE'S CORPUS, IMPORTED RATHER THAN RE-SPELLED. Two enumerations of "the Python this repo ships" that are allowed to drift is one too many: the day one of them stops seeing a directory, the other keeps passing and nothing says the trees disagree.
# `enumerate_py` is already the ONE enumerator inside `python_lint` for exactly this reason (its own header records the 2026-08-09 run that reported "27 files, All checks passed!" while the newest module in the tree was untracked and invisible to it).
from rediacc_ci.quality.python_lint import enumerate_py

# THE COMPOSITION DECISION IS SHARED, NOT RE-DERIVED. `rediacc_ci.quality.shrink_only` holds the two halves every shrink-only baseline in this repo agrees on, and `gate-test:shrink-only-composition` requires a Python baseline writer to reach them. A third copy of the same twelve lines is what `check:ci-shape-duplication` exists to report, and the reason those lines are worth
# sharing at all is in that module's header: a reseed that drains thirty and absorbs one prints a smaller number while doing it.
from rediacc_ci.quality.shrink_only import baseline_additions, write_verdict

# The pins file key. Read, never restated: `check:ci-toolchain-pins` A1 refuses a pin value written down in two places, and a gate that hardcodes the version it demands keeps demanding the old one on the day the pin moves without saying why.
PIN_KEY = "MYPY_VERSION"

# "The floor is a real number, not 1. The interesting failure is a glob that half-breaks and still returns something." Measured 2026-09-22: 1,126 tracked and untracked .py files outside private/. 400 is far enough below that to survive a large port landing the other way and far enough above zero to catch a corpus that half-collapsed.
MIN_PY_FILES = 400

# 77 is CANNOT RUN and is never a verdict about the code, the same contract `python_lint` states: exit 1 would say "mypy found a problem", which is false, and a pre-push lane would then refuse every push on a host that simply lacks the tool. Under CI the acquire step installs it, so 77 never fires there.
EXIT_CANNOT_RUN = 77

BASELINE_LABEL = ".ci/config/python-types-baseline.json"

# One mypy diagnostic line. Notes are deliberately NOT parsed: a single overload mismatch emits a dozen of them, each one a full signature dump, and none is a finding of its own. `pretty` and `color_output` are off in pyproject.toml so this stays a line-oriented parse; see that file for why that is pinned there rather than passed as a flag here.
ERROR_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+): error: (?P<rest>.*)$")
CODE_RE = re.compile(r"^(?P<message>.*?)  \[(?P<code>[a-z][a-z0-9-]*)\]$")

# THE PLANTED FIXTURE. Four facts at once; see CONTROL in the module docstring. Written from this literal rather than substituted into anything, so it cannot silently fail to apply.
CONTROL_SOURCE = '''import definitely_not_a_real_module_xyz


def planted_untyped():
    """No annotations ANYWHERE, on purpose: mypy skips this body by default, so an attr-defined finding here proves check_untyped_defs is in force."""
    value = "a string"
    return value.this_attribute_does_not_exist


def planted_typed(x: int) -> str:
    """Plain inference, reported under any configuration and none."""
    return x
'''

NOTE = (
    "SHRINK-ONLY and GENERATED. Every mypy finding, keyed by (file, code, message) "
    "so an id survives a MOVE, with occurrences as `count`. Only LOSING members or "
    "shrinking a count is allowed: a NEW id is refused even when the total falls. "
    "Drain with `check:ci-python-types --write-baseline` after fixing something, "
    "never to clear a red."
)


class CannotRun(Exception):  # noqa: N818
    """The gate cannot reach a verdict. Exit 77, never a verdict either way."""


# --------------------------------------------------------------------------- Findings
#


class Finding:
    """One mypy diagnostic, stripped of its line number.

    THE LINE NUMBER IS READ AND THEN DROPPED, which looks wasteful and is not: it is what proves the parse consumed a real diagnostic rather than a note or a wrapped continuation. A regex that did not require it would happily key a finding off a summary line.
    """

    __slots__ = ("code", "file", "message")

    def __init__(self, file: str, code: str, message: str) -> None:
        self.file = file
        self.code = code
        self.message = message

    @property
    def id(self) -> str:
        """A stable id: sha256 of the three fields, NUL-joined, first 16 hex.

        NUL because a separator that can occur inside a field lets two different findings hash to one id. A mypy message contains spaces, colons, quotes and brackets; it cannot contain a NUL.
        """
        raw = f"{self.file}\x00{self.code}\x00{self.message}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def key(self) -> tuple[str, str, str]:
        """The human-readable triple behind the id, for sorting and printing."""
        return (self.file, self.code, self.message)

    def __repr__(self) -> str:
        """Debugging aid; nothing parses this."""
        return "Finding(%r, %r, %r)" % (self.file, self.code, self.message)


def parse_findings(text: str) -> list[Finding]:
    """Every `error:` line of mypy output, as Findings. Notes and chatter dropped.

    A diagnostic with NO `[code]` suffix keeps the whole message and takes the code `(none)`. That shape exists (a crash traceback header, a rule with no code) and dropping it would make the gate quietly blind to the one class of output that means something went wrong.
    """
    out: list[Finding] = []
    for line in text.split("\n"):
        match = ERROR_RE.match(line)
        if not match:
            continue
        rest = match.group("rest")
        coded = CODE_RE.match(rest)
        if coded:
            message, code = coded.group("message"), coded.group("code")
        else:
            message, code = rest, "(none)"
        out.append(Finding(match.group("file"), code, message))
    return out


def tally(findings: list[Finding]) -> dict[str, dict[str, object]]:
    """Findings folded to `{id: {file, code, message, count}}`.

    The fold is the multiplicity decision: four identical findings in one file are one id with `count: 4`, never four rows that would need a line number to tell apart.
    """
    out: dict[str, dict[str, object]] = {}
    for finding in findings:
        entry = out.get(finding.id)
        if entry is None:
            out[finding.id] = {
                "file": finding.file,
                "code": finding.code,
                "message": finding.message,
                "count": 1,
            }
        else:
            entry["count"] = int(str(entry["count"])) + 1
    return out


# --------------------------------------------------------------------------- The corpus
#


def module_name(root: pathlib.Path, rel: str) -> str:
    """The dotted module name mypy will derive for this path.

    The rule is mypy's own: walk UP from the file while each directory holds an `__init__.py`, and the module name is whatever that walk collected. A file in a flat directory of scripts is therefore just its stem, which is why `.ci/scripts/quality/_cipath.py` and `.ci/scripts/docker/_cipath.py` collide even though nothing about them is ambiguous to a human.
    """
    path = pathlib.Path(rel)
    parts = [path.stem]
    directory = path.parent
    while str(directory) not in (".", "") and (root / directory / "__init__.py").exists():
        parts.insert(0, directory.name)
        directory = directory.parent
    return ".".join(parts)


def partition(root: pathlib.Path, files: list[str]) -> list[list[str]]:
    """The fewest groups in which no module name repeats. Order is deterministic.

    Greedy and first-fit: a file goes into the first group that does not already hold its module name. With four collisions in a corpus of 1,126 that yields two groups, and the second holds exactly the four losers.

    EVERY FILE LANDS IN EXACTLY ONE GROUP. That is the property the caller asserts against the corpus count before trusting any verdict -- a partition that silently dropped a file would be the same vacuity as a bad glob, arriving by a different door.
    """
    groups: list[tuple[set[str], list[str]]] = []
    for rel in sorted(files):
        name = module_name(root, rel)
        for seen, members in groups:
            if name not in seen:
                seen.add(name)
                members.append(rel)
                break
        else:
            groups.append(({name}, [rel]))
    return [members for _seen, members in groups]


# --------------------------------------------------------------------------- Resolving mypy
#


def _run(argv: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    """Capture both streams separately, never inherit stdin."""
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, cwd=cwd, stdin=subprocess.DEVNULL
    )


def _which(name: str) -> str | None:
    """An executable on PATH, or None. No shutil import for one caller."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def version_of(argv: list[str]) -> str:
    """`mypy --version` reduced to its leading numeric version, or "".

    mypy answers `mypy 2.3.1 (compiled: yes)`, so the parenthetical has to go. A resolver that compared the whole string would reject a perfectly good binary that reports `(compiled: no)`, which is what a pip install from source gives.
    """
    probe = _run([*argv, "--version"])
    fields = (probe.stdout + probe.stderr).split()
    for field in fields:
        match = re.match(r"^v?([0-9]+(?:\.[0-9]+)*)$", field)
        if match:
            return match.group(1)
    return ""


def resolve_mypy(want: str) -> list[str] | None:
    """The resolver, as an argv list. None means no mypy at the pin is reachable.

    EVERY RUNG IS "AT THE PIN", NOT "PRESENT", and that is not pedantry here: the finding set is a function of mypy's bundled typeshed, so a host one minor version behind produces a baseline diff in BOTH directions, and an honest response to it cannot be told apart from a real regression. `python_lint` records the same defect being fixed for ruff, shfmt and shellcheck in turn.

    The rungs, in order, and each one exists because a different environment has only that one:

      MYPY_BIN            an explicit escape hatch, trusted only after its
                          version is probed like any other.
      python3 -m mypy     what `pip install --user mypy==<pin>` leaves behind,
                          which is what the CI acquire step runs.
      mypy                a PATH binary, which is what `uv tool install` and a
                          distro package both leave behind.
      uvx mypy@<pin>      the host these gates were written on has no pip at all
                          (.ci/bootstrap.sh records the measurement), and uv is
                          what that host does have.
    """
    candidates: list[list[str]] = []
    explicit = os.environ.get("MYPY_BIN")
    if explicit:
        candidates.append([explicit])
    candidates.append([sys.executable or "python3", "-m", "mypy"])
    on_path = _which("mypy")
    if on_path is not None:
        candidates.append([on_path])
    for argv in candidates:
        if version_of(argv) == want:
            return argv
    uvx = _which("uvx") or _vendored_uvx()
    if uvx is not None:
        return [uvx, "mypy@%s" % want]
    return None


def _vendored_uvx() -> str | None:
    """`.ci/bootstrap.sh`'s uv, if this worktree has been bootstrapped.

    The directory carries the uv version in its name, so this globs rather than composing a path from a pin it has no business reading. Deliberately the LAST rung: it exists so a developer on a pipless host gets a verdict instead of a 77, not so CI can depend on a gitignored cache directory.
    """
    cache = paths.repo_root() / ".ci" / "cache" / "toolchain"
    for candidate in sorted(cache.glob("uv-*/uvx")):
        if os.access(candidate, os.X_OK):
            return str(candidate)
    return None


# --------------------------------------------------------------------------- The control
#


def control_verdict(output: str) -> str:
    """The four assertions over the control run. "" means the control fired.

    Semicolon-joined in a fixed order, because the string is printed and a reader comparing two runs should not have to sort it first.
    """
    codes = {finding.code for finding in parse_findings(output)}
    bad: list[str] = []
    if "attr-defined" not in codes:
        bad.append(
            "attr-defined was NOT reported on a planted attribute error inside an "
            "UNANNOTATED function, so check_untyped_defs did not reach mypy and "
            "almost every function in this repo is going unchecked"
        )
    if "return-value" not in codes:
        bad.append(
            "return-value was NOT reported on a planted `-> str` returning an int, "
            "so mypy is not type-checking at all"
        )
    if "no-untyped-def" in codes:
        bad.append(
            "no-untyped-def WAS reported, so something turned --strict on; the "
            "baseline is not a strict-mode baseline and every entry in it would be "
            "wrong"
        )
    if "import-not-found" in codes:
        bad.append(
            "import-not-found WAS reported on a module that deliberately does not "
            "exist, so ignore_missing_imports did not reach mypy and this gate's "
            "verdict now depends on what the host has installed"
        )
    return "; ".join(bad)


# --------------------------------------------------------------------------- The baseline
#


def read_baseline(path: pathlib.Path) -> dict[str, dict[str, object]] | None:
    """The frozen set, or None when the file is absent (which is STRICT MODE).

    A MISSING baseline is not "no debt recorded", it is "every finding is new". That direction is deliberate and it is the safe one: deleting the file to escape the gate makes the gate louder, not quieter.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(
            "%s exists but cannot be read (%s). A corrupt baseline is not an empty\n"
            "  one: treating it as empty would report all of today's frozen findings as\n"
            "  brand new. Repair the JSON; do not delete the file." % (BASELINE_LABEL, exc)
        ) from exc
    rows = data.get("findings")
    if not isinstance(rows, list):
        raise CannotRun(
            "%s has no `findings` array. Refusing to guess what the frozen set was."
            % BASELINE_LABEL
        )
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            raise CannotRun(
                "%s holds a row with no `id`. Every row is keyed by a hash of "
                "(file, code, message); a row without one cannot be compared against "
                "anything." % BASELINE_LABEL
            )
        out[str(row["id"])] = {
            "file": str(row.get("file", "")),
            "code": str(row.get("code", "")),
            "message": str(row.get("message", "")),
            "count": int(row.get("count", 1)),
        }
    return out


def render_baseline(current: dict[str, dict[str, object]]) -> str:
    """The committed JSON, sorted by (file, code, message) so a diff reads."""
    rows = []
    for ident, entry in sorted(
        current.items(),
        key=lambda kv: (str(kv[1]["file"]), str(kv[1]["code"]), str(kv[1]["message"]), kv[0]),
    ):
        rows.append(
            {
                "id": ident,
                "file": entry["file"],
                "code": entry["code"],
                "count": entry["count"],
                "message": entry["message"],
            }
        )
    return json.dumps({"note": NOTE, "findings": rows}, indent=2, ensure_ascii=False) + "\n"


def compare(
    baseline: dict[str, dict[str, object]], current: dict[str, dict[str, object]]
) -> tuple[list[str], list[str], list[str]]:
    """(added, grown, drained) ids.

    `added`   an id the baseline never held. A brand new type error.
    `grown`   a baselined id whose occurrence count went UP. The same defect
              copy-pasted to another line of the same file, which a set-only
              comparison would wave straight through.
    `drained` a baselined id that is gone or has FEWER occurrences. Not a
              failure of the code, but a failure of the record: the baseline has
              to be rewritten or it freezes debt that no longer exists and gives
              a future regression somewhere to hide.
    """
    added = sorted(baseline_additions(list(baseline), list(current)))
    grown = sorted(
        ident
        for ident, entry in current.items()
        if ident in baseline and int(str(entry["count"])) > int(str(baseline[ident]["count"]))
    )
    drained = sorted(
        ident
        for ident, entry in baseline.items()
        if ident not in current or int(str(current[ident]["count"])) < int(str(entry["count"]))
    )
    return added, grown, drained


def growth(added: list[str], grown: list[str]) -> list[str]:
    """The two kinds of growth, as the ONE list the shared `write_verdict` judges.

    A NEW id and a HIGHER count are the same claim in different clothes: the set of findings this tree produces got bigger. The shared decision knows about one dimension because every other baseline in this repo has one; folding the second into it here keeps a single implementation of the rule rather than a second one that could drift from it.
    """
    return [*added, *grown]


# --------------------------------------------------------------------------- Running mypy
#


def run_mypy(argv: list[str], root: pathlib.Path, files: list[str]) -> tuple[str, int]:
    """One mypy invocation over one group. Returns (merged output, exit code).

    THE FILE LIST GOES IN A FILE, not on the command line. 1,122 paths is roughly 40 KB of argv, which is under Linux's limit today and is exactly the kind of thing that starts failing on a different host with a different environment size -- and it would fail as a confusing exec error rather than as anything a reader could act on. mypy's `@file` syntax exists for this.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(files) + "\n")
        listfile = handle.name
    try:
        proc = _run([*argv, "@%s" % listfile], cwd=str(root))
    finally:
        pathlib.Path(listfile).unlink(missing_ok=True)
    return proc.stdout + proc.stderr, proc.returncode


# --------------------------------------------------------------------------- main
#


def _refuse_vacuous(message: list[str]) -> int:
    """Print the VACUOUS INPUT refusal in the shape the meta-gate registry pins."""
    print("✗ VACUOUS INPUT: %s" % message[0], file=sys.stderr)
    for line in message[1:]:
        print("  %s" % line, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 findings or a failed control, 77 mypy is absent."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()
    write = "--write-baseline" in args
    first_seed = "--first-seed" in args
    unknown = [a for a in args if a not in ("--write-baseline", "--first-seed")]
    if unknown:
        print("error: unknown argument(s): %s" % " ".join(unknown), file=sys.stderr)
        print("  usage: check_python_types.py [--selftest]", file=sys.stderr)
        print("         check_python_types.py --write-baseline [--first-seed]", file=sys.stderr)
        return 2

    root = paths.repo_root()
    os.chdir(root)
    baseline_path = root / ".ci" / "config" / "python-types-baseline.json"

    try:
        return _main(root, baseline_path, write=write, first_seed=first_seed)
    except CannotRun as exc:
        print("✗ CANNOT RUN: %s" % exc, file=sys.stderr)
        return EXIT_CANNOT_RUN


def _main(root: pathlib.Path, baseline_path: pathlib.Path, *, write: bool, first_seed: bool) -> int:
    """The gate proper, with every refusal in the order that makes it meaningful."""
    # ---- ANTI-VACUITY 1: the corpus ---------------------------------------
    py_files = enumerate_py(str(root))
    count = len(py_files)
    if count < MIN_PY_FILES:
        return _refuse_vacuous(
            [
                "only %d Python file(s) found, expected at least %d." % (count, MIN_PY_FILES),
                "mypy handed an empty file list exits 0 and says nothing, so a corpus",
                "that collapsed reads exactly like a clean tree. Refusing to report a pass.",
            ]
        )

    groups = partition(root, py_files)
    grouped = sum(len(g) for g in groups)
    if grouped != count:
        return _refuse_vacuous(
            [
                "the module partition holds %d file(s) but the corpus has %d." % (grouped, count),
                "A file that fell out of the partition is a file nobody type-checks, and",
                "the gate would still print a green over everything that remained.",
            ]
        )

    # ---- ANTI-VACUITY 3: the version --------------------------------------
    try:
        want = toolchain.pin(PIN_KEY)
    except toolchain.PinError as exc:
        raise CannotRun(
            "the %s pin could not be read (%s).\n"
            "  Without it this gate cannot tell a correct mypy from one whose typeshed\n"
            "  disagrees about code nobody edited, and the baseline diff of a wrong\n"
            "  version is indistinguishable from a real regression." % (PIN_KEY, exc)
        ) from exc

    mypy = resolve_mypy(want)
    if mypy is None:
        print("error: no mypy %s is reachable." % want, file=sys.stderr)
        print("  install one of:", file=sys.stderr)
        print("    python3 -m pip install --user mypy==%s" % want, file=sys.stderr)
        print("    uv tool install mypy@%s" % want, file=sys.stderr)
        print("    bash .ci/bootstrap.sh        # provisions uv on a pipless host", file=sys.stderr)
        print("  or point MYPY_BIN at an existing binary AT THAT VERSION:", file=sys.stderr)
        print("    MYPY_BIN=/path/to/mypy npm run check:ci-python-types", file=sys.stderr)
        print(
            "  NOT skipping: a type checker that cannot run is a gate that cannot fail.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_RUN

    # ---- ANTI-VACUITY 2: the control --------------------------------------
    with tempfile.TemporaryDirectory(prefix="python-types-control-") as box:
        control_file = pathlib.Path(box) / "control.py"
        control_file.write_text(CONTROL_SOURCE, encoding="utf-8")
        # cwd is the repo root, which is where mypy reads pyproject.toml from.
        control_out, control_code = run_mypy(mypy, root, [str(control_file)])
    if control_code not in (0, 1):
        raise CannotRun(
            "mypy exited %d on the planted control fixture rather than judging it.\n"
            "  That is a crash or a configuration error, not a verdict, so nothing is\n"
            "  said about the real files. mypy said:\n%s"
            % (control_code, "\n".join("    %s" % line for line in control_out.split("\n")))
        )
    control_bad = control_verdict(control_out)
    if control_bad:
        print("✗ CONTROL FAILED: %s." % control_bad, file=sys.stderr)
        print(
            "  A clean result from an instrument in this state means nothing, so this",
            file=sys.stderr,
        )
        print("  gate refuses to judge the real files. mypy said:", file=sys.stderr)
        for line in control_out.split("\n"):
            print("    %s" % line, file=sys.stderr)
        return 1

    print(
        "info: type-checking %d Python file(s) in %d group(s) with mypy %s (%s)"
        % (count, len(groups), want, " ".join(mypy))
    )
    # FLUSHED, because every finding below goes to stderr and stdout is block-buffered when this gate is piped into a file or a CI log collector. Without the flush the shape line arrives AFTER the findings it describes, which is how a reader concludes the counts belong to a different run. Observed on the very first red run of this gate.
    sys.stdout.flush()

    # ---- the real run -----------------------------------------------------
    findings: list[Finding] = []
    for index, group in enumerate(groups):
        output, code = run_mypy(mypy, root, group)
        if code not in (0, 1):
            raise CannotRun(
                "mypy exited %d on group %d of %d (%d file(s)) rather than judging it.\n"
                "  Exit 2 is a crash or a usage error, never a finding, so treating it as\n"
                "  'no findings' would silently retire this whole group. mypy said:\n%s"
                % (
                    code,
                    index + 1,
                    len(groups),
                    len(group),
                    "\n".join("    %s" % line for line in output.split("\n")[:20]),
                )
            )
        findings.extend(parse_findings(output))

    current = tally(findings)
    baseline = read_baseline(baseline_path)

    if write:
        return _write(baseline_path, baseline, current, first_seed=first_seed)

    if baseline is None:
        print(
            "✗ %s is MISSING, so every one of the %d finding(s) below is new."
            % (BASELINE_LABEL, len(current)),
            file=sys.stderr,
        )
        print(
            "  A missing baseline is STRICT MODE, not an empty one: deleting the file",
            file=sys.stderr,
        )
        print("  must make this gate louder, never quieter.", file=sys.stderr)
        return 1

    added, grown, drained = compare(baseline, current)

    if added or grown:
        print(file=sys.stderr)
        for ident in added:
            entry = current[ident]
            print(
                "✗ NEW type error in %s [%s]" % (entry["file"], entry["code"]),
                file=sys.stderr,
            )
            print("    %s" % entry["message"], file=sys.stderr)
        for ident in grown:
            entry = current[ident]
            print(
                "✗ MORE of a known type error in %s [%s]: %s -> %s occurrence(s)"
                % (entry["file"], entry["code"], baseline[ident]["count"], entry["count"]),
                file=sys.stderr,
            )
            print("    %s" % entry["message"], file=sys.stderr)
        print(file=sys.stderr)
        print(
            "%d new and %d grown finding(s). Fix them. Do NOT add them to %s -- the"
            % (len(added), len(grown), BASELINE_LABEL),
            file=sys.stderr,
        )
        print(
            "  baseline is the debt that existed when this gate landed, and it only shrinks.",
            file=sys.stderr,
        )
        return 1

    if drained:
        print(file=sys.stderr)
        for ident in drained[:20]:
            entry = baseline[ident]
            was = int(str(entry["count"]))
            now = int(str(current[ident]["count"])) if ident in current else 0
            print(
                "✗ FIXED (and still baselined): %s [%s] %d -> %d occurrence(s)"
                % (entry["file"], entry["code"], was, now),
                file=sys.stderr,
            )
        if len(drained) > 20:
            print("    ... and %d more" % (len(drained) - 20), file=sys.stderr)
        print(file=sys.stderr)
        print("%d baselined finding(s) no longer fire. Drain them:" % len(drained), file=sys.stderr)
        print("    npm run check:ci-python-types -- --write-baseline", file=sys.stderr)
        print(
            "  A baseline that keeps rows nobody can reproduce freezes last year's debt",
            file=sys.stderr,
        )
        print("  and gives a real regression somewhere to hide.", file=sys.stderr)
        return 1

    print(
        "✓ %d Python file(s) type-check with mypy %s: %d finding(s), all frozen in "
        "the baseline (%d entries, 0 new, 0 grown, 0 drainable)"
        % (count, want, sum(int(str(e["count"])) for e in current.values()), len(baseline))
    )
    return 0


def _write(
    baseline_path: pathlib.Path,
    baseline: dict[str, dict[str, object]] | None,
    current: dict[str, dict[str, object]],
    *,
    first_seed: bool,
) -> int:
    """`--write-baseline`, with the composition refusal in front of the write."""
    exists = baseline is not None
    previous = baseline or {}
    added, grown, drained = compare(previous, current) if exists else ([], [], [])
    verdict = write_verdict(
        baseline_exists=exists, first_seed=first_seed, additions=growth(added, grown)
    )
    if verdict == "missing-baseline":
        print(
            "✗ Refusing to write the baseline: %s does not exist." % BASELINE_LABEL,
            file=sys.stderr,
        )
        print(
            "  With no previous baseline there is nothing to compare against, so all %d"
            % len(current),
            file=sys.stderr,
        )
        print(
            "  finding(s) would be frozen with no check on what is among them, which makes",
            file=sys.stderr,
        )
        print(
            "  DELETING the file the cheapest way to defeat this rule. If this really is a",
            file=sys.stderr,
        )
        print(
            "  first seed, say so: --write-baseline --first-seed. Otherwise restore the file.",
            file=sys.stderr,
        )
        return 1
    if verdict == "would-grow":
        print(
            "✗ Refusing to write the baseline: it would GAIN %d finding(s) the current "
            "one does not hold." % (len(added) + len(grown)),
            file=sys.stderr,
        )
        for ident in added:
            entry = current[ident]
            print(
                "    NEW   %s [%s] %s" % (entry["file"], entry["code"], entry["message"]),
                file=sys.stderr,
            )
        for ident in grown:
            entry = current[ident]
            print(
                "    GREW  %s [%s] %s -> %s"
                % (entry["file"], entry["code"], previous[ident]["count"], entry["count"]),
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print(
            "  The baseline shrinks; it never grows. A reseed that drains %d and adds %d"
            % (len(drained), len(added) + len(grown)),
            file=sys.stderr,
        )
        print(
            "  still LOOKS like progress in the totals, which is exactly how a violation",
            file=sys.stderr,
        )
        print("  created this hour becomes permanent invisible debt.", file=sys.stderr)
        print("  Fix the finding instead. Do NOT add it to %s." % BASELINE_LABEL, file=sys.stderr)
        return 1

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(render_baseline(current), encoding="utf-8")
    print(
        "baseline written: %d entries (%d before, %d drained, 0 added, 0 grown)"
        % (len(current), len(previous), len(drained))
    )
    return 0


# --------------------------------------------------------------------------- Controls
#


def selftest() -> int:
    """Both directions on every rule. A gate proven only to fire will flag the tree.

    The floor is what catches a suite that stopped executing: a file whose controls silently vanish prints nothing and exits 0, which reads exactly like a clean run.
    """
    controls = Controls("python types", floor=34)

    # -- the parser ---------------------------------------------------------
    sample = (
        'a/b.py:12: error: "str" has no attribute "nope"  [attr-defined]\n'
        "a/b.py:12: note:     def run(args: str) -> None\n"
        'a/b.py:40: error: "str" has no attribute "nope"  [attr-defined]\n'
        "c/d.py:3: error: something with no code at all\n"
        "Found 3 errors in 2 files (checked 900 source files)\n"
    )
    parsed = parse_findings(sample)
    controls.check("three error lines are parsed", len(parsed), 3)
    controls.check(
        "CONTROL: a note line is NOT a finding", [f.code for f in parsed].count("note"), 0
    )
    controls.check("the summary line is NOT a finding", parsed[-1].file, "c/d.py")
    controls.check(
        "a coded message keeps only the message",
        parsed[0].message,
        '"str" has no attribute "nope"',
    )
    controls.check("a coded message keeps its code", parsed[0].code, "attr-defined")
    controls.check("an UNCODED error is kept, not dropped", parsed[2].code, "(none)")
    controls.check(
        "an uncoded message is kept whole", parsed[2].message, "something with no code at all"
    )

    # -- the id and the fold ------------------------------------------------
    controls.check(
        "the SAME finding at a DIFFERENT line has the SAME id", parsed[0].id, parsed[1].id
    )
    controls.check(
        "CONTROL: a different FILE is a different id",
        Finding("x.py", "c", "m").id == Finding("y.py", "c", "m").id,
        False,
    )
    controls.check(
        "CONTROL: a different CODE is a different id",
        Finding("x.py", "c", "m").id == Finding("x.py", "d", "m").id,
        False,
    )
    controls.check(
        "CONTROL: a different MESSAGE is a different id, which is the re-key price",
        Finding("x.py", "c", "m").id == Finding("x.py", "c", "n").id,
        False,
    )
    # THE NUL SEPARATOR. Without it these two collide: ("a", "b|c", "d") and ("a|b", "c", "d") join to the same string under any printable separator.
    controls.check(
        "CONTROL: fields that would collide under a printable separator do not",
        Finding("a", "b|c", "d").id == Finding("a|b", "c", "d").id,
        False,
    )
    folded = tally(parsed)
    controls.check("the fold collapses duplicates to one id", len(folded), 2)
    controls.check("the fold counts the duplicates", folded[parsed[0].id]["count"], 2)
    controls.check("a singleton counts 1", folded[parsed[2].id]["count"], 1)

    # -- the module partition ----------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        box = pathlib.Path(tmp)
        (box / "pkg").mkdir()
        (box / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (box / "pkg" / "thing.py").write_text("", encoding="utf-8")
        (box / "flat_a").mkdir()
        (box / "flat_a" / "thing.py").write_text("", encoding="utf-8")
        (box / "flat_b").mkdir()
        (box / "flat_b" / "thing.py").write_text("", encoding="utf-8")

        controls.check(
            "a file inside a package gets a dotted module name",
            module_name(box, "pkg/thing.py"),
            "pkg.thing",
        )
        controls.check(
            "CONTROL: a file in a flat directory is just its stem, which is the collision",
            module_name(box, "flat_a/thing.py"),
            "thing",
        )
        groups = partition(box, ["pkg/thing.py", "flat_a/thing.py", "flat_b/thing.py"])
        controls.check("two colliding names force a second group", len(groups), 2)
        controls.check(
            "the packaged file does NOT collide with the flat one",
            sorted(groups[0]),
            ["flat_a/thing.py", "pkg/thing.py"],
        )
        controls.check("every file lands somewhere", sum(len(g) for g in groups), 3)
        controls.check(
            "CONTROL: no collision means ONE group", len(partition(box, ["pkg/thing.py"])), 1
        )

    # -- the control verdict, all five states ------------------------------
    good = (
        'c.py:6: error: "str" has no attribute "x"  [attr-defined]\n'
        "c.py:10: error: Incompatible return value type  [return-value]\n"
    )
    controls.check("CONTROL: the expected control output is ACCEPTED", control_verdict(good), "")
    controls.truthy(
        "no attr-defined is refused, naming check_untyped_defs",
        "check_untyped_defs" in control_verdict("c.py:10: error: x  [return-value]\n"),
    )
    controls.truthy(
        "no return-value is refused, naming type-checking at all",
        "not type-checking at all" in control_verdict("c.py:6: error: x  [attr-defined]\n"),
    )
    controls.truthy(
        "no-untyped-def PRESENT is refused, naming --strict",
        "--strict" in control_verdict(good + "c.py:4: error: x  [no-untyped-def]\n"),
    )
    controls.truthy(
        "import-not-found PRESENT is refused, naming ignore_missing_imports",
        "ignore_missing_imports"
        in control_verdict(good + "c.py:1: error: x  [import-not-found]\n"),
    )

    # -- the shrink-only comparison ----------------------------------------
    base: dict[str, dict[str, object]] = {
        "aa": {"file": "f", "code": "c", "message": "m", "count": 2}
    }
    controls.check(
        "an unchanged set is (no added, no grown, no drained)",
        compare(base, {"aa": dict(base["aa"])}),
        ([], [], []),
    )
    controls.check(
        "a NEW id is an addition",
        compare(
            base,
            {
                "aa": dict(base["aa"]),
                "bb": {"file": "g", "code": "c", "message": "m", "count": 1},
            },
        )[0],
        ["bb"],
    )
    controls.check(
        "CONTROL: the same defect COPIED is growth, which a set comparison misses",
        compare(base, {"aa": {"file": "f", "code": "c", "message": "m", "count": 3}})[1],
        ["aa"],
    )
    controls.check("a fixed finding is drainable, not silently fine", compare(base, {})[2], ["aa"])
    controls.check(
        "PARTIALLY fixed is drainable too",
        compare(base, {"aa": {"file": "f", "code": "c", "message": "m", "count": 1}})[2],
        ["aa"],
    )

    # -- the write verdict --------------------------------------------------
    controls.check(
        "a drain-only reseed is allowed",
        write_verdict(baseline_exists=True, first_seed=False, additions=growth([], [])),
        None,
    )
    controls.check(
        "CONTROL: a reseed that ADDS is refused even though the total may fall",
        write_verdict(baseline_exists=True, first_seed=False, additions=growth(["x"], [])),
        "would-grow",
    )
    controls.check(
        "CONTROL: a reseed that GROWS a count is refused too",
        write_verdict(baseline_exists=True, first_seed=False, additions=growth([], ["x"])),
        "would-grow",
    )
    controls.check(
        "a missing baseline refuses to be seeded by accident",
        write_verdict(baseline_exists=False, first_seed=False, additions=growth([], [])),
        "missing-baseline",
    )
    controls.check(
        "a missing baseline CAN be seeded when the author says so",
        write_verdict(baseline_exists=False, first_seed=True, additions=growth([], [])),
        None,
    )

    # -- the version probe --------------------------------------------------
    controls.check(
        "a version is extracted from mypy's parenthetical banner",
        version_of([sys.executable or "python3", "-c", "print('mypy 2.3.1 (compiled: yes)')"]),
        "2.3.1",
    )
    controls.check(
        "CONTROL: a command that prints no version yields nothing, so no rung accepts it",
        version_of([sys.executable or "python3", "-c", "print('command not found')"]),
        "",
    )

    # -- the constants ------------------------------------------------------
    controls.check("cannot-run is 77, never 1", EXIT_CANNOT_RUN, 77)
    controls.truthy("the corpus floor is a real number, not 1", MIN_PY_FILES > 1)

    return 0 if controls.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
