r"""Lint every tracked Python file with ruff, under the repo's root pyproject.toml.

Ported from `.ci/scripts/quality/check-python-lint.sh`, which W7P5-c DELETED on 2026-09-23 once its K=5 shadow ledger (`.ci/shadow/w7p2-python-lint.observations.jsonl`, 6 rows, 6 distinct trees, every one `EQUIVALENT`) licensed the retirement. The nine cases that used to execute it now compare against its own recorded bytes under
`.ci/rediacc_ci/tests/goldens/python-lint/`, whose provenance headers carry blob `471b915b87984c59aeaca380951aa3dd5bd3b702`.

WHY THIS EXISTS, in the twin's own words, because the incident is the design:

    This repo gated TypeScript, shell and Go and left Python entirely ungated,
    while 13 of its 15 tracked .py files are the Stop-hook program that gates
    every agent turn. The first run of this gate found a live NameError in
    wl_checks.guided_slice that both hook suites -- 584 and 118 assertions --
    passed straight over, because reaching that branch needs root=None and a
    plan-subagent triage at the same time. It then failed SOFT into a bare except
    that replaced the operator's whole worklist guide with an apology, so nothing
    ever surfaced it.

    TWO WAYS THIS GATE COULD BE GREEN WHILE PROVING NOTHING, and both are closed
    before a single real file is judged:

      1. AN EMPTY FILE LIST. `ruff check` with no paths exits 0. A gate whose
         input silently became empty -- a moved directory, a bad glob, a
         `git ls-files` run outside a repo -- would report success forever. So the
         list is counted against a floor, and the floor is a real number rather
         than 1: a glob that half-breaks is the interesting case.
      2. A LINTER THAT ISN'T LINTING. A wrong config path, a version that dropped
         a rule, a wrapper swallowing the exit code -- all look identical to a
         clean tree. So a synthetic defect is planted and the linter must report
         it. If the control cannot fire, this exits non-zero WITHOUT judging the
         real files, because a verdict from an instrument that cannot fail is
         worse than no verdict.
      3. AN UNTRACKED FILE, silently omitted. Found live 2026-08-09: this gate
         reported "27 files, All checks passed!" while wl_checklist.py, the newest
         and second-largest module of the Stop-hook program, was untracked and
         therefore never in the list. A format violation in it was caught only by
         running ruff by hand. The omission is invisible by construction: a
         shorter list still passes the floor, so nothing looks wrong. The list now
         includes untracked-but-not-ignored Python, and control 3 below plants an
         untracked file to prove the enumeration reaches it. Gitignored files stay
         excluded, which is what keeps venvs and build output out.

    The control plants F821 (undefined name) specifically, because that is the
    rule that caught the real bug. If a future config change disables it, this
    gate fails loudly rather than going quietly blind to the defect it was built
    for.

THE THREE-WAY CONTROL IS NOT BELT-AND-BRACES, and the measured table is the whole argument:

    The config moved from `ruff.toml` into the root pyproject.toml and the
    `--config` arguments came out, because both ruff and pytest DISCOVER a root
    pyproject.toml by walking up from the file they judge
    (docs/ci-overhaul/08-driver-contract.md section 2). Discovery is exactly the
    thing an explicit `--config` used to prove, so something else has to prove it
    now: F821 alone is reported under ruff's BUILT-IN defaults too, so a run with
    no configuration at all would satisfy the old control unchanged. ARG001 needs
    `select = ["ALL"]` and ANN001 is suppressed only by the `ignore` list, so
    requiring one present and the other absent pins that THIS repo's config is the
    one in force.

    Measured 2026-09-06 on the control file:

      ruff check --isolated              -> F821 only
      ruff check --isolated --select ALL -> F821 + ARG001 + ANN001 + E501 + D + INP + CPY
      ruff check (this repo's config)    -> F821 + ARG001

    so requiring F821 present, ARG001 present and ANN001 ABSENT pins all three
    facts at once: the linter runs, `select = ["ALL"]` is in force, and the
    `ignore` list is in force. Any one of them alone is satisfiable by the wrong
    config.

THE CONTROL FILE LIVES INSIDE THE REPO, and that is the whole of a later change:

    It used to live in `mktemp -d` with `--config "$REPO_ROOT/ruff.toml"` pointed
    at it, so it proved "that path parses". The config moved into the root
    pyproject.toml, both tools DISCOVER that by walking up from the file they are
    judging, and the `--config` arguments came out -- which means a control run
    outside the tree would now be linted with ruff's DEFAULTS and would happily
    report F821 while proving nothing about this repo's configuration at all.

    `.ci/cache/` is the right place for it: it is inside the repo, so ancestry
    discovery reaches the same pyproject.toml the real run uses, and it is
    gitignored, so a crashed run cannot leave a stray .py that `enumerate_py`
    (which includes untracked files) would pick up on the next pass. Ruff lints an
    explicitly-named path even when it is gitignored, which is what makes the two
    properties compatible.

EXIT 77 IS "COULD NOT RUN", AND THE DISTINCTION IS THE WHOLE POINT:

    exit 1 said `ruff found a problem`, which is false, and which made a pre-push
    lane refuse every push on a machine that simply lacks the tool. The ci-runner
    classifies 77 as BLOCKED -- counted, named with these very lines, recorded in
    the push receipt and WARNED about -- but not a verdict on the code.

    This is not a skip and it is not softer. Under CI the toolchain is present, so
    77 never fires there; if it ever did, the workflow sees a plain non-zero and
    the lane is broken, which is correct. The sentence above stays true: what
    changed is that "cannot run" is now SAYABLE.

THE INSTALL ADVICE IS ORDERED BY WHAT WORKS HERE, and the ordering was paid for:

    THE STANDALONE INSTALLER IS FIRST BECAUSE IT IS THE ONE THAT WORKS HERE.
    Measured 2026-08-27 in the devbox: `python3 -m pip` reports "No module named
    pip" and neither uv nor uvx nor pipx is on PATH, so BOTH of the options this
    message used to offer are dead ends on the machine most likely to be reading
    it. A session that trusts the message concludes the gate cannot be run locally
    and ships Python to CI unlinted -- which is exactly what happened, at one
    ~10-minute CI round for a one-word finding.

THE FORMAT FAILURE NAMES THE FILES THAT DIFFER, and the ANSI strip is why it can:

    Name the files that DIFFER, not the whole list. This used to print every
    tracked .py after "Run: ruff format", which read as "reformat the tree", and
    ruff 0.16 moved the path onto a `-->` line under "unformatted:", so the three
    real offenders were easy to miss among 80 names (2026-09-02).

    STRIP ANSI FIRST. ruff colours its output even through a pipe, so the `-->`
    lines arrive as `\e[1m\e[94m--> \e[0m<path>` and a plain anchored sed matches
    nothing -- which silently fell back to naming all 80 files, the very thing this
    block exists to stop. Same shape as the `bws` colour defect found the same
    day: a tool that does not test for a tty.

EXE001 IS INVISIBLE FROM HERE, so the property is checked directly:

    Measured 2026-08-28: CI failed `Python lint + format (ruff)` with two EXE001
    findings ("Shebang is present but file is not executable"), while THIS gate --
    same ruff 0.16.1, same config, same 66 files -- reported "All checks passed". A
    fresh 644 file carrying a shebang, placed in the repo and linted with an
    explicit `--select EXE`, still produced no finding on this machine. So the
    divergence is environmental and NOT something this gate can fix by arguing
    with ruff; the answer is to check the property ourselves.

    THE PROPERTY IS THE GIT MODE, NOT THE DISK MODE, and that distinction is the
    whole point: CI lints a fresh checkout, so what it sees is whatever git
    recorded. A file chmod +x on disk AFTER `git add` is 755 locally and 644 in CI,
    which is exactly how two files passed here and failed there.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PIN IS ASSIGNED TWICE IN THE TWIN AND THE SECOND ONE WINS. It sources `.ci/scripts/lib/toolchain.sh`, calls `toolchain_load` (which exports `RUFF_VERSION` from `.devcontainer/toolchain.env`), and then immediately writes
`RUFF_VERSION="0.16.1"` over it. Because `toolchain_pin_for ruff` reads the
CURRENT value of that variable, the literal is what `toolchain_check` compares against, not the pins file. The two agree today (`.devcontainer/toolchain.env:32`
says `RUFF_VERSION=0.16.1`), so the redundancy is invisible; the day someone bumps
the pins file and not this line, the gate keeps demanding the old version and says nothing about why. Reproduced, and reported as a defect rather than repaired.

`enumerate_py` IS ONE FUNCTION FOR A REASON, carried verbatim: "It is a function specifically so the control cannot drift from the thing it guards: an earlier draft of control 3 ran its own copy of this query, which meant editing the real enumeration left the control green -- a check that cannot fail, introduced by the very commit that was fixing one."

COLOUR HERE IS DECIDED BY `CI`, NOT BY isatty. The twin writes
`if [[ "${CI:-}" == "true" ]]; then RED="" ... else RED=$'\033[0;31m'`, so a
developer piping this gate into a file still gets escapes. That is one of the nine disagreeing colour conventions `rediacc_ci.log` documents, and it is reproduced rather than corrected: using the logger would change the bytes on every non-CI run and the differential would mismatch on every tree.

`ruff` IS RESOLVED, NOT ASSUMED, in the twin's three-rung order: `$RUFF_BIN`, then a PATH binary AT THE PIN, then `uvx ruff@<pin>`. The middle rung is the one with history: "This branch used to accept whatever `ruff` was on PATH, so a host carrying 0.5.0 linted with it while CI used the pinned version and the two disagreed silently -- the same defect already fixed for shfmt and
shellcheck, left behind here because the class was swept incompletely."

THE MODE SCAN READS `git ls-files -s` AND THEN `awk '{print $1, $4}'`, so a path
containing whitespace is truncated identically on both sides. Carried.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# "The floor is a real number, not 1. The interesting failure is a glob that half-breaks and still returns something. Raise it when the tree grows; a deliberate REMOVAL of Python from this repo should have to edit this line."
MIN_PY_FILES = 10

# The literal that overwrites the pins-file value. See the port notes.
RUFF_VERSION = "0.16.1"

# The twin's exit statuses. 77 is CANNOT RUN and is never a verdict.
EXIT_CANNOT_RUN = 77

# ruff colours its output even through a pipe; the `-->` lines arrive wrapped in escapes and an anchored match without this strip silently falls back to naming every file.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
UNFORMATTED = re.compile(r"^ *--> ([^:]*):.*$")

# The planted control file. Its three assertions pin three different facts; see the module docstring for the measured three-way table.
CONTROL_SOURCE = """def planted(unused_arg):
    # ARG001 on `unused_arg`: only reachable via `select = ["ALL"]`.
    # ANN001 on `unused_arg` too, and it must NOT be reported: the ignore list
    # switches the whole ANN set off, so seeing it means the list did not load.
    # F821: `undefined_on_purpose` is never bound anywhere.
    return undefined_on_purpose
"""


def colours() -> tuple[str, str, str]:
    """RED, GREEN, NC, decided by `CI` exactly as the twin decides them."""
    if os.environ.get("CI") == "true":
        return "", "", ""
    return "\033[0;31m", "\033[0;32m", "\033[0m"


def _run(argv: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, cwd=cwd, stdin=subprocess.DEVNULL
    )


def is_work_tree(root: str) -> bool:
    """`git rev-parse --is-inside-work-tree`, status only."""
    return _run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"]).returncode == 0


def enumerate_py(root: str) -> list[str]:
    """The ONE enumerator, used by the real list AND by control 3.

    `git ls-files --cached --others --exclude-standard -- '*.py' ':!:private/**'`, then `[ -e "$f" ]`: "a tracked file deleted in the working tree (rm without git rm) is still listed and would make ruff fail on a path that is not there."
    """
    proc = _run(
        [
            "git",
            "-C",
            root,
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
            ":!:private/**",
        ]
    )
    return [
        name for name in proc.stdout.split("\n") if name and (pathlib.Path(root) / name).exists()
    ]


def enumeration_reaches_untracked(root: str, enumerate_fn) -> tuple[bool, str]:
    """CONTROL 3's body: does `enumerate_fn` list a planted UNTRACKED `.py`?

    ON A TEMP WORK TREE, NEVER THE REAL ONE. The first form planted `enum_probe_<pid>_<ts>.py` at the repository root and deleted it in a `finally`, so for the length of every run the shared tree held an untracked file that `check:format`, the pool's other readers and a hard kill could all see (check:ci-gate-tree-writes V1). What the control proves -- that the enumerator includes untracked files -- needs A work tree, not THE work tree: a `git init` in a TemporaryDirectory carrying a copy of the real `.gitignore`, so `--exclude-standard` judges the probe by the same rules it judges the real files. The name stays runtime-keyed so a probe that an earlier crash left behind cannot satisfy it.
    """
    enum_probe = "enum_probe_%d_%d.py" % (os.getpid(), int(time.time()))
    with tempfile.TemporaryDirectory(prefix="python-lint-enum-") as tmp:
        if _run(["git", "-C", tmp, "init", "-q"]).returncode != 0:
            return False, enum_probe
        ignore = pathlib.Path(root) / ".gitignore"
        if ignore.is_file():
            shutil.copyfile(ignore, pathlib.Path(tmp) / ".gitignore")
        (pathlib.Path(tmp) / enum_probe).write_text("x = 1\n", encoding="utf-8")
        return enum_probe in enumerate_fn(tmp), enum_probe


def resolve_ruff() -> list[str] | None:
    """The three-rung resolver, as an argv list. None means neither ruff nor uvx.

    RUNG TWO IS "AT THE PIN", NOT "PRESENT". A host carrying 0.5.0 must not decide this repo's verdict; see the module docstring for the sibling tools where the same defect was already fixed.
    """
    explicit = os.environ.get("RUFF_BIN")
    if explicit:
        return [explicit]
    on_path = _which("ruff")
    if on_path is not None:
        probe = _run([on_path, "--version"])
        fields = probe.stdout.split()
        version = fields[1] if len(fields) > 1 else ""
        version = version.removeprefix("v")
        match = re.match(r"^[0-9]+(\.[0-9]+)*", version)
        if match and match.group(0) == RUFF_VERSION:
            return [on_path]
    if _which("uvx") is not None:
        return ["uvx", "ruff@%s" % RUFF_VERSION]
    return None


def _which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def control_verdict(output: str) -> str:
    """The three assertions over the control run's output. "" means the control fired.

    Returns the twin's own `control_bad` string, semicolon-joined in the same order, because that string is printed and therefore compared.
    """
    bad = ""
    if "F821" not in output:
        bad = "F821 was not reported on a planted undefined name"
    if "ARG001" not in output:
        extra = 'ARG001 was not reported, so select = ["ALL"] did not reach ruff'
        bad = "%s; %s" % (bad, extra) if bad else extra
    if "ANN001" in output:
        extra = "ANN001 WAS reported, so the ignore list did not reach ruff"
        bad = "%s; %s" % (bad, extra) if bad else extra
    return bad


def unformatted_paths(format_out: str) -> str:
    """The `-->` paths out of `ruff format --check`, ANSI stripped, sorted unique.

    Returns a SPACE-TERMINATED string, as `tr '\\n' ' '` produces, because the trailing space lands in the printed command and the differential compares it.
    """
    names: set[str] = set()
    for line in ANSI.sub("", format_out).split("\n"):
        match = UNFORMATTED.match(line)
        if match:
            names.add(match.group(1))
    return "".join("%s " % name for name in sorted(names))


def mode_findings(root: str) -> tuple[list[str], int]:
    """EXE001/EXE002 against the GIT MODE, not the disk mode.

    Returns (message lines, files seen). The count is the anti-vacuity half: "A scan that sees nothing cannot fail, so its silence proves nothing."
    """
    red, _green, nc = colours()
    proc = _run(["git", "-C", root, "ls-files", "-s", "--", "*.py", ":!:private/**"])
    out: list[str] = []
    seen = 0
    for line in proc.stdout.split("\n"):
        fields = line.split()
        if len(fields) < 4:
            continue
        # `awk '{print $1, $4}'` then `${mode_path%% *}` / `${mode_path#* }`. A
        # path containing whitespace is truncated identically on both sides.
        mode = fields[0]
        name = fields[3]
        path = pathlib.Path(root) / name
        if not path.is_file():
            continue
        seen += 1
        try:
            head = path.open("rb").read(2)
        except OSError:
            head = b""
        has_shebang = head == b"#!"
        if has_shebang and mode == "100644":
            out.append(
                "%s✗%s %s has a shebang but git mode is 100644 (EXE001 in CI)" % (red, nc, name)
            )
            out.append("    fix: git update-index --chmod=+x %s" % name)
        elif not has_shebang and mode == "100755":
            out.append(
                "%s✗%s %s is git mode 100755 but has no shebang (EXE002 in CI)" % (red, nc, name)
            )
            out.append("    fix: git update-index --chmod=-x %s" % name)
    return out, seen


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 findings or a failed control, 77 ruff is absent."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    red, green, nc = colours()
    root = str(paths.repo_root())
    os.chdir(root)

    if not is_work_tree(root):
        print(
            "%s✗ VACUOUS INPUT%s: %s is not a git work tree, so the" % (red, nc, root),
            file=sys.stderr,
        )
        print(
            "  file list cannot be enumerated at all. ruff exits 0 on an empty list,",
            file=sys.stderr,
        )
        print(
            "  which would read exactly like a clean tree. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1

    # ---- CONTROL 3: the ENUMERATION must reach an UNTRACKED file ---------- "Runs before the real list is built, because a list that omits files silently is not worth counting."
    seen, enum_probe = enumeration_reaches_untracked(root, enumerate_py)
    if not seen:
        print(
            "%s✗ CONTROL FAILED%s: the file enumeration did not return a planted" % (red, nc),
            file=sys.stderr,
        )
        print(
            "  UNTRACKED Python file (%s), so this gate is blind to exactly" % enum_probe,
            file=sys.stderr,
        )
        print(
            "  the case that shipped on 2026-08-09. Refusing to judge the real files.",
            file=sys.stderr,
        )
        return 1

    py_files = enumerate_py(root)
    count = len(py_files)
    if count < MIN_PY_FILES:
        print(
            "%s✗ VACUOUS INPUT%s: only %d Python file(s) found, expected at least %d."
            % (red, nc, count, MIN_PY_FILES),
            file=sys.stderr,
        )
        print(
            "  ruff exits 0 on an empty list, so a shrinking input reads exactly like",
            file=sys.stderr,
        )
        print("  a clean tree. Refusing to report a pass.", file=sys.stderr)
        for name in py_files:
            print("    %s" % name, file=sys.stderr)
        return 1

    # `toolchain_load || exit 1`, which the twin runs at check-python-lint.sh:137 -- AFTER the two vacuity refusals above and BEFORE the resolver below, so the order here is the twin's order and not a convenient one.
    #
    # WHY THE PORT NEEDED THIS AT ALL. The module notes above explain that the pins file's RUFF_VERSION is immediately overwritten by the literal, so the port skips reading the file for the VERSION and is right to. What it also skipped was `toolchain_load`'s REFUSAL: with the pins file gone the twin exits 1 having printed nothing else, and this port went on to lint with whatever
    # resolver it could find. That is an anti-vacuity refusal quietly dropped in a port, which is the shape this whole programme exists to catch. Found by the W7 P4 batch 8a cutover differential on a fixture tree that had no `.devcontainer/`: twin exit 1 with one line of stderr, port exit 0 with a full green report over 12 files.
    #
    # The early return on REDIACC_TOOLCHAIN_LOADED is `toolchain.sh:28`, kept because a caller that has already sourced the pins legitimately has no file to re-read.
    if not os.environ.get("REDIACC_TOOLCHAIN_LOADED"):
        pins = pathlib.Path(root) / ".devcontainer" / "toolchain.env"
        if not os.access(pins, os.R_OK):
            print("toolchain: pins file missing or unreadable: %s" % pins, file=sys.stderr)
            return 1

    ruff = resolve_ruff()
    if ruff is None:
        print("%serror%s: ruff is not available and neither is uvx." % (red, nc), file=sys.stderr)
        print("  install one of:", file=sys.stderr)
        print(
            "    curl -fsSL https://astral.sh/ruff/%s/install.sh | sh   # no pip needed"
            % RUFF_VERSION,
            file=sys.stderr,
        )
        print("    pip install ruff==%s" % RUFF_VERSION, file=sys.stderr)
        print("    uv tool install ruff@%s" % RUFF_VERSION, file=sys.stderr)
        print("  or point RUFF_BIN at an existing binary:", file=sys.stderr)
        print("    RUFF_BIN=/path/to/ruff npm run check:ci-python-lint", file=sys.stderr)
        print(
            "  NOT skipping: a linter that cannot run is a gate that cannot fail.", file=sys.stderr
        )
        return EXIT_CANNOT_RUN

    # ---- CONTROL: the linter must report a planted defect ------------------
    control_dir = (
        pathlib.Path(root)
        / ".ci"
        / "cache"
        / ("ruff-control-%d-%d" % (os.getpid(), int(time.time())))
    )
    control_dir.mkdir(parents=True, exist_ok=True)
    control_file = control_dir / "control.py"
    control_file.write_text(CONTROL_SOURCE, encoding="utf-8")
    try:
        proc = _run([*ruff, "check", "--no-cache", "--output-format", "concise", str(control_file)])
        control_out = proc.stdout + proc.stderr
        control_bad = control_verdict(control_out)
        if control_bad:
            print("%s✗ CONTROL FAILED%s: %s." % (red, nc, control_bad), file=sys.stderr)
            print(
                "  Either the linter is not running, the root pyproject.toml did not",
                file=sys.stderr,
            )
            print(
                "  resolve by ancestry, or a rule this control depends on has changed.",
                file=sys.stderr,
            )
            print(
                "  Any of those makes a clean result meaningless, so this gate refuses",
                file=sys.stderr,
            )
            print("  to judge the real files.", file=sys.stderr)
            print("  ruff said:", file=sys.stderr)
            for line in control_out.split("\n"):
                print("    %s" % line, file=sys.stderr)
            return 1

        print("info: linting %d Python file(s) with ruff %s" % (count, RUFF_VERSION))

        # NOT CAPTURED, and that is the difference between agreeing with the twin
        # and printing one line fewer. `$RUFF check --no-cache -- "${PY_FILES[@]}"`
        # is a bare command in the twin, so ruff writes straight to the gate's own streams -- INCLUDING its `All checks passed!` line on success. A port that captured the output in order to inspect it would swallow that line on the GREEN path, which is exactly the divergence a differential built only from red specimens never sees. Caught by the clean specimen.
        sys.stdout.flush()
        sys.stderr.flush()
        check = subprocess.run(
            [*ruff, "check", "--no-cache", "--", *py_files],
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if check.returncode != 0:
            print(file=sys.stderr)
            print(
                "%s✗%s ruff reported findings in Python this gate scans "
                "(tracked and untracked)." % (red, nc),
                file=sys.stderr,
            )
            print(
                "  Fix them. Do NOT add a per-line noqa to get past this gate: if a rule",
                file=sys.stderr,
            )
            print(
                "  is genuinely wrong for this repo it is disabled in pyproject.toml with a",
                file=sys.stderr,
            )
            print("  stated reason, where it is reviewable.", file=sys.stderr)
            return 1

        fmt = _run([*ruff, "format", "--check", "--no-cache", "--", *py_files])
        # `format_out="$($RUFF ... 2>&1)"`: both streams, merged, in the twin.
        format_out = fmt.stdout + fmt.stderr
        if fmt.returncode != 0:
            sys.stderr.write(format_out if format_out.endswith("\n") else format_out + "\n")
            differing = unformatted_paths(format_out)
            if not differing:
                # `${differing:-${PY_FILES[*]}}`: the fallback that used to fire on
                # every run because the ANSI escapes defeated the anchored match.
                differing = " ".join(py_files)
            print(file=sys.stderr)
            print(
                "%s✗%s Python formatting differs. Run: ruff format --no-cache -- %s"
                % (red, nc, differing),
                file=sys.stderr,
            )
            return 1
        print(format_out.rstrip("\n"))
    finally:
        _rmtree(control_dir)

    exe_bad, exe_seen = mode_findings(root)
    for line in exe_bad:
        print(line, file=sys.stderr)

    if exe_seen == 0:
        print(
            "%s✗%s the shebang/mode scan enumerated ZERO tracked Python files." % (red, nc),
            file=sys.stderr,
        )
        print(
            "  A scan that sees nothing cannot fail, so its silence proves nothing.",
            file=sys.stderr,
        )
        return 1

    if exe_bad:
        print(file=sys.stderr)
        print(
            "%s✗%s %d Python file(s) have a git mode CI will reject."
            % (red, nc, len(exe_bad) // 2),
            file=sys.stderr,
        )
        return 1

    print(
        "%s✓%s %d Python file(s) pass ruff lint and format (+ %d checked for shebang/mode "
        "agreement)" % (green, nc, count, exe_seen)
    )
    return 0


def _rmtree(path: pathlib.Path) -> None:
    """`rm -rf`, without importing shutil at module scope for one caller."""
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_dir():
            child.rmdir()
        else:
            child.unlink(missing_ok=True)
    path.rmdir()


def selftest() -> int:
    """Both directions on the control verdict, the format parser and the mode rule.

    THE CONTROL VERDICT IS THE PIECE MOST WORTH ASSERTING, because it is the thing that decides whether any other verdict means anything. All four of its states are exercised: fires on each missing rule, and stays SILENT on the exact output this repo's configuration produces.
    """
    verdict_cases = [
        ("this repo's config output is accepted", "a.py:1:1: F821 x\na.py:1:1: ARG001 y\n", ""),
        (
            "no F821 is refused",
            "a.py:1:1: ARG001 y\n",
            "F821 was not reported on a planted undefined name",
        ),
        (
            "no ARG001 is refused, naming select = ALL",
            "a.py:1:1: F821 x\n",
            'ARG001 was not reported, so select = ["ALL"] did not reach ruff',
        ),
        (
            "ANN001 PRESENT is refused, naming the ignore list",
            "a.py:1:1: F821 x\na.py:1:1: ARG001 y\na.py:1:1: ANN001 z\n",
            "ANN001 WAS reported, so the ignore list did not reach ruff",
        ),
        (
            "two failures are joined in the twin's order",
            "a.py:1:1: ANN001 z\n",
            (
                "F821 was not reported on a planted undefined name; ARG001 was not "
                'reported, so select = ["ALL"] did not reach ruff; ANN001 WAS reported, '
                "so the ignore list did not reach ruff"
            ),
        ),
    ]
    format_cases = [
        ("a plain --> line yields its path", "unformatted:\n  --> a/b.py:1:1\n", "a/b.py "),
        # THE ANSI CASE, which is the one that silently fell back to naming every file. ruff colours through a pipe.
        (
            "a coloured --> line yields its path too",
            "\x1b[1m\x1b[94m--> \x1b[0ma/b.py:1:1\n",
            "a/b.py ",
        ),
        ("two paths are sorted and space-terminated", "  --> z.py:1\n  --> a.py:1\n", "a.py z.py "),
        # THE NEGATIVE HALF: no `-->` line means no paths, which is what triggers the twin's whole-list fallback.
        ("output with no --> line yields nothing", "All checks passed!\n", ""),
    ]

    floor = len(verdict_cases) + len(format_cases) + 7
    ctl = Controls("python-lint", floor=floor)

    for label, output, want in verdict_cases:
        ctl.check("control: %s" % label, control_verdict(output), want)
    for label, output, want in format_cases:
        ctl.check("format: %s" % label, unformatted_paths(output), want)

    # CONTROL 3, BOTH DIRECTIONS, on its temp work tree: the real enumerator reaches the planted untracked file, and an enumerator that drops untracked files (`--cached` only, the shape that shipped on 2026-08-09) is caught.
    root = str(paths.repo_root())
    ctl.check(
        "control 3: the real enumerator reaches an untracked file",
        enumeration_reaches_untracked(root, enumerate_py)[0],
        True,
    )

    def tracked_only(r: str) -> list[str]:
        return [
            n
            for n in _run(["git", "-C", r, "ls-files", "--cached", "--", "*.py"]).stdout.split("\n")
            if n
        ]

    ctl.check(
        "control 3: a tracked-only enumerator is caught",
        enumeration_reaches_untracked(root, tracked_only)[0],
        False,
    )

    # THE FLOOR AND THE STATUSES ARE THE TWIN'S.
    ctl.check("the file floor is 10, not 1", MIN_PY_FILES, 10)
    ctl.check("cannot-run is 77, never 1", EXIT_CANNOT_RUN, 77)
    ctl.check("the pin the twin actually compares against", RUFF_VERSION, "0.16.1")

    # COLOUR IS DECIDED BY CI, NOT BY isatty. Both directions, because a port that used the logger would be byte-identical only when attached to a terminal.
    saved = os.environ.get("CI")
    try:
        os.environ["CI"] = "true"
        ctl.check("CI=true suppresses colour entirely", colours(), ("", "", ""))
        os.environ["CI"] = "false"
        ctl.check(
            "CI=false leaves the escapes in, even off a terminal",
            colours(),
            ("\033[0;31m", "\033[0;32m", "\033[0m"),
        )
        os.environ.pop("CI", None)
        ctl.check(
            "an unset CI leaves the escapes in too",
            colours(),
            ("\033[0;31m", "\033[0;32m", "\033[0m"),
        )
    finally:
        if saved is None:
            os.environ.pop("CI", None)
        else:
            os.environ["CI"] = saved

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
