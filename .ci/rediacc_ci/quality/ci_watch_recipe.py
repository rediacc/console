"""There is ONE way to read CI, and every surface points at it.

Ported from `.ci/scripts/quality/check-ci-watch-recipe.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

The twin's header, carried whole:

    Why this exists. On 2026-08-25, landing console#574, the hand-rolled
    CI-watch recipe was found in NINE places and had rotted in most of them. Two
    were worse than stale: block-long-sleep.sh explained that "attempt 2 lands on
    the SAME Console CI run" while printing a loop that could not survive it, and
    cancel-old-ci.sh recommended the very tool this repo rejects 4/4. Three of the
    nine were invisible to a manual sweep because they lived in hook SCRIPTS while
    the sweep grepped *.md.

    The fix was to stop distributing a recipe at all: .ci/scripts/ci/ci-trace.py
    is the only sanctioned reader, ad-hoc forms are refused by
    block-adhoc-sanctioned.sh, and a hand-rolled watch left running blocks the
    Stop hook. This gate keeps that true.

      A. The skill hands out the SCRIPT, not a loop.
      B. Every surface that instructs watching names the script.
      C. No doc or hook hands out a hand-rolled loop or a banned invocation.
         Since 2026-10-02 (PLAN-ci-verdict box C) C also refuses a doc that
         hands out a raw CI READ from the registry's `CI_READ_VERBS` table
         (`gh pr checks`, `gh run list/view`, `gh api` GETs on actions runs,
         jobs, logs, check-runs and annotations, GraphQL rollup queries): the
         pre-bash guard `block_raw_ci_read` refuses each one, so a doc teaching
         it hands the reader a refusal instead of the tracer verb.
      D. The sanctioned registry is self-consistent and its tools exist.
      E. The script's own --help works.
      F. The skill teaches --run for a DISPATCHED run, not --ref.

    (A former Check G here, "every CLI flag is taught in the skill," moved to
    check-cli-doc-coverage.sh 2026-08-27 and generalized to a second pair
    beyond ci-trace.py/SKILL.md -- see that file, not duplicated here.)

    Controls are built by CONSTRUCTION (fixtures written literally), never by
    pattern-substituting real source, so rewording a target cannot silently void
    them -- the failure check-control-vacuity.sh exists to catch.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SIGPIPE RACE THAT THIS GATE WAS BUILT AROUND CANNOT EXIST IN PYTHON, and that is worth stating precisely rather than deleting the paragraph that records it. The twin's comment, kept verbatim because it is the most expensive lesson in this file:

    NEVER `advice_only ... | grep -q` HERE. `grep -q` exits at its FIRST match
    and SIGPIPEs the upstream grep; under this file's own `set -o pipefail` that
    141 becomes the pipeline's status, so a genuine match reports FALSE. The
    verdict is then a race between grep -q exiting and the upstream finishing,
    decided by file size and machine load.

    Measured 2026-08-27 on .claude/hooks/test-hooks.sh, 1,644 lines then (match at
    line 692 of the filtered stream): 8/8 trips WITHOUT pipefail, 0/8 WITH it. The
    gate had been reporting "no hand-rolled watch in 124 scanned file(s)" over a
    real offender, and only surfaced under `npm run ci`'s parallel load, where the
    timing flipped the other way.

    The CONTROLS could not have caught it: they run on 2-line fixtures, where the
    upstream finishes long before grep -q exits. A control smaller than the thing
    it models is not a control. There is now a large-file one below.

    THE SUBJECT IS THE SIZE, NOT THAT FILE. It was 1,644 lines the day this was
    measured, 2,774 by 2026-09-09, and it is being ported out of bash into
    .claude/rediacc_hooks/tests/ -- so the citation is dated on purpose and the
    large-file control below is what keeps the measurement reproducible after the
    file it names is gone.

    Command substitution reads the producer to completion, so there is no signal
    to race.

This port reads each file into memory and filters it, which has no producer to kill. The LARGE-FILE CONTROL IS KEPT ANYWAY, at its full ~240 KB, because it is also a control on the DETECTOR and because deleting it would delete the record of why the detector is shaped this way. The twin's sizing note is kept with it.

CHECK D SHELLS OUT TO THE SAME HELPER, on purpose. `check_sanctioned_registry.py` already IS Python, and importing it here would mean re-implementing its argv contract and its module loading. The twin runs it as `python3 <path> <registry> <root>` and reads its combined output; so does this, which makes check D byte-identical by construction rather than by care.

CHECK E EXECUTES THE REAL SCRIPT, also on purpose. `[ -x "$TRACE" ]` is a PERMISSION test, not an existence test, and the twin's message says "missing or not executable" for that reason: a gate script whose executable bit was stripped in a rebase is exactly the failure this arm catches. The port keeps `os.access(path, os.X_OK)`.

GIT DOES THE ENUMERATION. `scan_files` is `git ls-files` with three pathspecs, run as a subprocess rather than re-implemented, because git's pathspec matching is not fnmatch: with no `:(glob)` magic, `*` crosses a `/`, so `.claude/**/*.md` is not the recursive glob it looks like. A hand-rolled walk would quietly scan a different set, and the count in the success line would still
read healthy.

THE `${actors:-none}`-STYLE DETAIL IN CHECK D: the twin interpolates the helper's
stdout into the pass line through `$(cat ...)`, which strips the trailing newline. Carried, because `ok D. registry: 3 row(s) self-consistent` is the line a reader recognises.
"""

import importlib.util
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The four subjects, repo-relative. Named once so a move re-keys one line.
SKILL_REL = ".claude/skills/ci-watch/SKILL.md"
EVIDENCE_FILE = ".claude/skills/ci-watch/incidents.md"
TRACE_REL = ".ci/scripts/ci/ci-trace.py"
REGISTRY_REL = ".claude/hooks/lib/sanctioned.py"
REGISTRY_CHECKER_REL = ".ci/scripts/quality/lib/check_sanctioned_registry.py"

# The three pathspecs check B and check C scan. Passed to git verbatim; see the port notes for why they are not re-implemented as a walk.
SCAN_PATHSPECS = (".claude/**/*.md", ".claude/**/*.sh", "docs/agent-reference/*.md")

# Lines that are DATA or ASSERTIONS, not advice. Both were real false positives: a worklist test carries a background task's command as a JSON value, and the hook suite asserts `check 2 ...` on the banned shape precisely BECAUSE it is banned. Flagging either would push someone to weaken the test to satisfy the gate, which is backwards.
ADVICE_EXCLUDE = re.compile(r'"(command|cmd)"[ \t]*:|^[ \t]*check [0-9]+ ')

# The shape a surface uses when it tells an agent to watch CI.
INSTRUCTS_WATCHING = re.compile(
    r"terminal-state watch|arm a watch|watch the console ci", re.IGNORECASE
)

# The banned invocation: `gh run watch` carrying --exit-status or --interval,
# with no shell separator in between (so a later pipeline stage is not swept in).
BANNED_INVOCATION = re.compile(r"gh run watch[^|;&]*--(exit-status|interval)")

# A hand-rolled loop's fingerprint: it reads `.status`, compares against `"completed"`, and never mentions `run_attempt` -- which is the field a correct reader needs to survive a re-run landing on the same run id.
STATUS_FIELD = re.compile(r"\.status")
COMPLETED = re.compile(r'"completed"')
RUN_ATTEMPT = re.compile(r"run_attempt")

# A raw CI read named in a doc: `gh` then one of the subcommands the `CI_READ_VERBS` rows cover, up to the end of the code span or shell statement. Each candidate is then judged by the registry's own classifier (`ci_read_match`), the one `block_raw_ci_read` uses, so this scan and the guard cannot disagree about what a raw read IS.
RAW_READ_CANDIDATE = re.compile(r"\bgh\s+(?:pr|run|api)\b[^`|;&\n]*")

# A line that NAMES a raw read without handing it out: a dated history entry, or a sentence saying the read is refused. It carries this marker in an HTML comment, so the exemption is visible in the source and greppable, never inferred from wording.
RAW_READ_OK = "raw-ci-read-ok"

# Check A's third test: a `until`/`while` loop driving `gh` inside the canonical block. `[^\n]*` in the twin's ERE is per-line, which is what this is.
CANONICAL_LOOP = re.compile(r"(until|while).*gh ")


def read_text(path: pathlib.Path) -> str:
    """A file's text, or the empty string. grep over a missing file finds nothing."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def bash_block(text: str) -> str:
    """The FIRST ```bash fenced block, body only.

        awk '/^```bash$/ { inblk=1; next } /^```$/ { if (inblk) exit } inblk { print }'

    `exit` on the closing fence, so a second block later in the file is never read. That is the twin's behaviour and it matters: the skill's canonical recipe is the first block, and a later example block must not be able to satisfy check A on its behalf.
    """
    out: list[str] = []
    in_block = False
    for line in text.split("\n"):
        if line == "```bash":
            in_block = True
            continue
        if line == "```":
            if in_block:
                break
            continue
        if in_block:
            out.append(line)
    return "".join(line + "\n" for line in out)


def advice_only(text: str) -> str:
    """`grep -vE '"(command|cmd)"[[:space:]]*:|^[[:space:]]*check [0-9]+ '`."""
    return "\n".join(line for line in text.split("\n") if not ADVICE_EXCLUDE.search(line))


def hands_out_loop(text: str) -> bool:
    """Does this file hand out a hand-rolled watch loop?

    Three conditions, all required, and the third is a NEGATIVE: a file that mentions `run_attempt` anywhere is exempt, because that is the field a correct reader uses and its presence means the author knew about the re-run problem. The `run_attempt` test is against the WHOLE file, not the filtered advice, exactly as the twin's `grep -q 'run_attempt' "$f"` is.
    """
    statuses = [line for line in advice_only(text).split("\n") if STATUS_FIELD.search(line)]
    if not statuses:
        return False
    if not any(COMPLETED.search(line) for line in statuses):
        return False
    return not RUN_ATTEMPT.search(text)


def hands_out_banned(text: str) -> bool:
    """Does this file hand out `gh run watch --exit-status` (or `--interval`)?"""
    return any(BANNED_INVOCATION.search(line) for line in advice_only(text).split("\n"))


def load_registry(path: pathlib.Path):
    """The sanctioned registry module, loaded by path; None when it cannot be."""
    try:
        spec = importlib.util.spec_from_file_location("sanctioned", str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 -- reported by the caller as a failure, never silently passed
        return None
    return module if hasattr(module, "ci_read_match") else None


def raw_reads(text: str, registry) -> list[str]:
    """The `CI_READ_VERBS` row names of every raw CI read this file hands out, in order.

    Advice only (the same `advice_only` filter as the other detectors), and a line carrying `RAW_READ_OK` is skipped.
    """
    found: list[str] = []
    for line in advice_only(text).split("\n"):
        if RAW_READ_OK in line:
            continue
        for candidate in RAW_READ_CANDIDATE.findall(line):
            row, _ident = registry.ci_read_match(candidate)
            if row is not None:
                found.append(row["name"])
    return found


def instructs_watching(text: str) -> bool:
    """Does this surface tell an agent to watch CI at all?"""
    return bool(INSTRUCTS_WATCHING.search(text))


def assert_skill(text: str) -> str | None:
    """Check A over one skill file. None means it passes; a string is the reason."""
    block = bash_block(text)
    if block == "":
        return "no bash block found"
    if "ci-trace" not in block:
        return "the canonical block does not invoke %s" % TRACE_REL
    if any(CANONICAL_LOOP.search(line) for line in block.split("\n")):
        return "the canonical block still contains a hand-rolled loop"
    return None


def scan_files(root: pathlib.Path) -> list[str]:
    """The tracked surfaces checks B and C read, minus the evidence file.

    `git ls-files` with the twin's three pathspecs. See the port notes: git's pathspec matching is not fnmatch, so this is delegated rather than rewritten.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", *SCAN_PATHSPECS],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    lines = proc.stdout.decode("utf-8", "replace").split("\n")
    return [line for line in lines if line not in ("", EVIDENCE_FILE)]


# --------------------------------------------------------------------------- The fixtures every control is built from, written LITERALLY. ---------------------------------------------------------------------------

FIXTURE_LOOP_SKILL = """# fixture
```bash
R=1
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do :; done
```
"""

FIXTURE_MUTE = "Arm a watch on that run and wait for it.\n"

FIXTURE_BAD = (
    "Poll it with:\n"
    '`R=1; until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; '
    "do :; done`\n"
)

FIXTURE_GOOD = "Trace it with `.ci/scripts/ci/ci-trace.py --wait`.\n"

FIXTURE_RAW_READ = "Read the failure with `gh run view 123 --log-failed` and grep it.\n"

FIXTURE_RAW_CARVE_OUTS = (
    "Rerun with `gh run rerun 123 --failed`, fetch artifacts with `gh run download 123 -n x`,\n"
    "read the head with `gh api repos/o/r/pulls/5 --jq .head.sha`.\n"
    "On 2026-10-02 the lead ran `gh run view 123 --log` dozens of times. <!-- raw-ci-read-ok: history -->\n"
)

FIXTURE_DATA = (
    'BG=[{"command":"gh run watch 1 --exit-status"}]\n'
    'check 2 pre-bash/block-adhoc-sanctioned.sh "gh run watch 1 --exit-status" "refused"\n'
)


def fixture_big() -> str:
    """THE CONTROL THE OTHERS COULD NOT BE: a LARGE file with the hit EARLY.

    The twin's sizing note, carried because the first draft of this control was wrong in a way that looked right:

        IT MUST EXCEED THE PIPE BUFFER, IN BYTES -- not merely be "long". The
        first draft of this control was 2000 SHORT lines (~32 KB) and PASSED
        against a deliberately reverted detector: at that size the upstream grep
        writes everything into the 64 KB pipe and exits before `grep -q` closes
        it, so there is no SIGPIPE to race and the bug cannot appear. Only once
        the producer BLOCKS on a full pipe does grep -q's early exit kill it.

        So: the hit goes early, and ~240 KB of padding follows it. Verified by
        MUTATION -- revert hands_out_banned to the `| grep -q` form and this
        control goes red, which the 32 KB version did not.

    A Python detector has no pipe and cannot race, so this control can no longer fail for the original reason. It is kept at full size because it is still a control on the DETECTOR over a realistic file, and because a control deleted is a lesson deleted.
    """
    parts = ["padding %d\n" % i for i in range(1, 40)]
    parts.append("Poll it with `gh run watch 12345 --exit-status` until it finishes.\n")
    pad = "x" * 200
    parts.extend("padding %s\n" % pad for _ in range(1200))
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Run checks A to F with their controls. 0 clean, 1 on any failure."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    skill = root / SKILL_REL
    trace = root / TRACE_REL
    registry = root / REGISTRY_REL

    fails = 0

    def fail(*message: str) -> None:
        nonlocal fails
        print("✗ %s" % " ".join(message), file=sys.stderr)
        fails += 1

    def ok(message: str) -> None:
        print("ok   %s" % message)

    # ---- A. the skill hands out the script -------------------------------
    problem = assert_skill(read_text(skill))
    if problem is None:
        ok("A. the skill hands out %s, not a loop" % TRACE_REL)
    else:
        fail("A. %s" % problem)

    if assert_skill(FIXTURE_LOOP_SKILL) is None:
        fail("A CONTROL DID NOT FIRE: a skill handing out a loop passed, so A proves nothing")
    else:
        ok("A control: a skill handing out a loop is rejected")

    # ---- B. every watching surface names the script -----------------------
    files = scan_files(root)
    silent = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if not instructs_watching(text):
            continue
        if "ci-trace" not in text:
            silent.append(rel)

    if not silent:
        ok("B. every surface that instructs watching names %s" % TRACE_REL)
    else:
        fail("B. instruct watching but never name the script: %s" % " ".join(silent))

    if instructs_watching(FIXTURE_MUTE) and "ci-trace" not in FIXTURE_MUTE:
        ok("B control: a watching surface with no script mention is detectable")
    else:
        fail("B CONTROL DID NOT FIRE: the detector missed a fixture that instructs watching")

    # ---- C. nobody hands out a loop, a banned invocation or a raw CI read ---
    registry_module = load_registry(registry)
    if registry_module is None:
        fail(
            "C. the sanctioned registry could not be loaded, so no doc was scanned for raw CI reads"
        )
    offenders = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if hands_out_loop(text):
            offenders.append("%s (hand-rolled loop)" % rel)
        if hands_out_banned(text):
            offenders.append("%s (banned invocation)" % rel)
        if registry_module is not None:
            offenders.extend(
                "%s (raw CI read: %s)" % (rel, name)
                for name in sorted(set(raw_reads(text, registry_module)))
            )

    scanned = len(files)
    if scanned == 0:
        fail("C. scanned ZERO files -- the glob matched nothing, so this assertion is vacuous")
    elif not offenders:
        ok("C. no hand-rolled watch in %d scanned file(s)" % scanned)
    else:
        fail("C. these hand out a broken wake-up or a refused CI read: %s" % " ".join(offenders))

    if hands_out_loop(FIXTURE_BAD):
        ok("C control: a hand-rolled loop is detected")
    else:
        fail("C CONTROL DID NOT FIRE: a hand-rolled loop went undetected")

    if hands_out_loop(FIXTURE_GOOD) or hands_out_banned(FIXTURE_GOOD):
        fail("C IS OVER-BROAD: the sanctioned invocation was flagged")
    else:
        ok("C control: the sanctioned invocation is not flagged")

    if hands_out_banned(FIXTURE_DATA):
        fail("C IS OVER-BROAD: a JSON value and a test assertion were read as advice")
    else:
        ok("C control: data and test assertions are not advice")

    if registry_module is not None:
        if raw_reads(FIXTURE_RAW_READ, registry_module):
            ok("C control: a raw CI read handed out in a doc is detected")
        else:
            fail("C CONTROL DID NOT FIRE: a raw `gh run view --log-failed` went undetected")
        if raw_reads(FIXTURE_RAW_CARVE_OUTS, registry_module):
            fail(
                "C IS OVER-BROAD: a write, an artifact download, pulls/<n> or a marked history line was flagged"
            )
        else:
            ok("C control: writes, downloads, pulls/<n> and a marked history line are not flagged")

    if hands_out_banned(fixture_big()):
        ok("C control: an early hit in a LARGE file is still detected (no SIGPIPE race)")
    else:
        fail(
            "C CONTROL DID NOT FIRE: a banned invocation at line 40 of a 2000-line file "
            "went undetected -- the detector is racing its own pipe, so its green means "
            "nothing"
        )

    # ---- D. the registry is self-consistent -------------------------------
    if not registry.is_file():
        fail("D. sanctioned registry missing: %s" % registry)
    else:
        proc = subprocess.run(
            [sys.executable, str(root / REGISTRY_CHECKER_REL), str(registry), str(root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode == 0:
            ok("D. registry: %s" % out.rstrip("\n"))
        else:
            fail("D. registry inconsistent:")
            for line in out.rstrip("\n").split("\n"):
                print("     %s" % line, file=sys.stderr)

    # ---- E. the script's own --help works ---------------------------------
    if not (trace.is_file() and os.access(trace, os.X_OK)):
        fail("E. %s is missing or not executable" % TRACE_REL)
    else:
        proc = subprocess.run(
            [str(trace), "--help"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode == 0:
            if "exit codes:" in out:
                ok("E. %s --help works and documents its exit codes" % TRACE_REL)
            else:
                fail("E. --help works but documents no exit codes; a caller would have to guess")
        else:
            fail("E. %s --help exited non-zero" % TRACE_REL)

    # ---- F. the skill teaches --run for a DISPATCHED run ------------------ `--wait --ref main` cannot see a workflow_dispatch run's check runs at all -- a branch's statusCheckRollup structurally excludes them (incidents.md, 2026-08-26). That is not fixable in ci-trace.py itself; the only defense is that the taught recipe says to use --run for that case, and stays saying so.
    if not skill.is_file():
        fail("F. %s is missing" % skill)
    else:
        text = read_text(skill)
        if "--run" in text and re.search(r"workflow_dispatch|dispatched", text, re.IGNORECASE):
            ok("F. the skill teaches --run for a dispatched run")
        else:
            fail(
                "F. %s no longer teaches --run for a dispatched run -- this is exactly" % skill,
                "how the 2026-08-26 false-green (main read GREEN while a Release run was",
                "still tagging/deploying) would silently come back",
            )

    print()
    if fails == 0:
        print("✓ ci-watch: one reader, %d file(s) clean." % scanned)
        print("  Blind spot, stated so a green is not read as more than it is: this checks")
        print("  what agents are HANDED. It cannot see a watch an agent actually armed at")
        print("  runtime, nor whether GitHub's rollup semantics change under the script.")
        return 0
    print("✗ ci-watch: %d failure(s)." % fails)
    return 1


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions for every detector, over fixtures written by construction.

    The over-broad direction carries as much weight as the detection direction: three of the twin's own controls exist only to prove the detectors do NOT fire on the sanctioned invocation, on JSON data, or on a test assertion.
    """
    ctl = Controls("ci-watch-recipe", floor=27, verbose=True)

    # -- bash_block ---------------------------------------------------------
    ctl.check(
        "PLANT: the first bash block is extracted",
        bash_block("intro\n```bash\nrun me\n```\ntail\n"),
        "run me\n",
    )
    ctl.check(
        "MIRROR: a file with no bash block yields nothing",
        bash_block("just prose\n"),
        "",
    )
    ctl.check(
        "TWIN SHAPE: awk exits at the closing fence, so a SECOND block is never read",
        bash_block("```bash\nfirst\n```\n```bash\nsecond\n```\n"),
        "first\n",
    )

    # -- assert_skill, both directions --------------------------------------
    ctl.check(
        "MIRROR: a skill handing out the script passes",
        assert_skill("```bash\n.ci/scripts/ci/ci-trace.py --wait\n```\n"),
        None,
    )
    ctl.check(
        "PLANT: a skill with no bash block at all is rejected",
        assert_skill("prose only\n"),
        "no bash block found",
    )
    ctl.check(
        "PLANT: a block that never names the script is rejected",
        assert_skill("```bash\necho hi\n```\n"),
        "the canonical block does not invoke %s" % TRACE_REL,
    )
    ctl.check(
        "PLANT: the twin's own loop fixture is rejected",
        assert_skill(FIXTURE_LOOP_SKILL),
        "the canonical block does not invoke %s" % TRACE_REL,
    )
    ctl.check(
        "PLANT: a block naming the script AND looping is still rejected",
        assert_skill("```bash\n# ci-trace exists\nuntil gh run view; do :; done\n```\n"),
        "the canonical block still contains a hand-rolled loop",
    )

    # -- advice_only, both directions ---------------------------------------
    ctl.check(
        "PLANT: a JSON command value is dropped from advice",
        advice_only('BG=[{"command":"gh run watch 1"}]'),
        "",
    )
    ctl.check(
        "PLANT: a `check N ...` test assertion is dropped from advice",
        advice_only("  check 2 pre-bash/x.sh 'gh run watch 1'"),
        "",
    )
    ctl.check(
        "MIRROR: ordinary prose survives the filter",
        advice_only("run gh run watch yourself"),
        "run gh run watch yourself",
    )

    # -- hands_out_loop, both directions ------------------------------------
    ctl.check(
        "PLANT: the twin's bad fixture is a hand-rolled loop", hands_out_loop(FIXTURE_BAD), True
    )
    ctl.check(
        "MIRROR: the sanctioned invocation is not a loop", hands_out_loop(FIXTURE_GOOD), False
    )
    ctl.check(
        "MIRROR: a reader that knows about run_attempt is exempt",
        hands_out_loop(FIXTURE_BAD + "and check run_attempt too\n"),
        False,
    )
    ctl.check(
        'MIRROR: `.status` with no "completed" comparison is not a loop',
        hands_out_loop("read .status and print it\n"),
        False,
    )

    # -- hands_out_banned, both directions ----------------------------------
    ctl.check(
        "PLANT: `gh run watch --exit-status` is banned",
        hands_out_banned("run `gh run watch 1 --exit-status`\n"),
        True,
    )
    ctl.check(
        "PLANT: `--interval` is banned too",
        hands_out_banned("run `gh run watch 1 --interval 30`\n"),
        True,
    )
    ctl.check(
        "MIRROR: JSON data and a test assertion are not advice",
        hands_out_banned(FIXTURE_DATA),
        False,
    )
    ctl.check(
        "MIRROR: a shell separator ends the match, so a later flag is not swept in",
        hands_out_banned("gh run watch 1 | tee log --exit-status\n"),
        False,
    )
    ctl.check(
        "CONTROL: the LARGE fixture is still detected (the SIGPIPE-race control)",
        hands_out_banned(fixture_big()),
        True,
    )
    ctl.truthy(
        "CONTROL: and it really is large enough to have raced a pipe (>64 KB)",
        len(fixture_big()) > 64 * 1024,
    )

    # -- raw_reads, both directions -----------------------------------------
    registry = load_registry(paths.repo_root() / REGISTRY_REL)
    ctl.truthy(
        "CONTROL: the sanctioned registry loads and carries ci_read_match", registry is not None
    )
    if registry is not None:
        ctl.check(
            "PLANT: a raw `gh run view --log-failed` is a raw read",
            raw_reads(FIXTURE_RAW_READ, registry),
            ["gh-run-view-log"],
        )
        ctl.check(
            "PLANT: a raw read in a substitution inside prose is found",
            raw_reads("check it: `x=$(gh pr checks 591)`\n", registry),
            ["gh-pr-checks"],
        )
        ctl.check(
            "MIRROR: writes, downloads, pulls/<n> and a marked history line are not raw reads",
            raw_reads(FIXTURE_RAW_CARVE_OUTS, registry),
            [],
        )
        ctl.check(
            "MIRROR: the tracer verb is not a raw read",
            raw_reads("Use `.ci/scripts/ci/ci-trace.py --run 123 --why`.\n", registry),
            [],
        )

    # -- instructs_watching, both directions --------------------------------
    ctl.check("PLANT: the mute fixture instructs watching", instructs_watching(FIXTURE_MUTE), True)
    ctl.check(
        "PLANT: the detector is case-insensitive",
        instructs_watching("TERMINAL-STATE WATCH\n"),
        True,
    )
    ctl.check(
        "MIRROR: prose that does not instruct watching is not flagged",
        instructs_watching("this file is about something else\n"),
        False,
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
