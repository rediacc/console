"""A caller may not hand cleanup-staging.sh a tag it will refuse.

Ported from `.ci/scripts/quality/check-staging-tag-guard.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live until a
differential ledger row exists over K distinct trees. Its gate header registers it as step "Staging tag guard", needs none, lane quality-security.

WHY THIS EXISTS, carried whole from the twin, dated incident included:

    cleanup-staging.sh deletes GHCR tags and guards itself with
    `[[ "$TAG" =~ ^staging- ]] || exit 1` -- deliberately, so a stray call cannot
    delete a real published tag. On 2026-09-06 cleanup-channel-docker-tags.sh was
    found calling it with CHANNEL (`edge`/`stable`), which the guard rejects EVERY
    TIME. It had done so on every release since it was written, and the step
    summary blamed a missing `delete:packages` scope -- sending readers to fix a
    token when the wrong tool was being called.

    The tempting "fix" is to widen the guard. That would remove the safety rail
    and is exactly what this gate is here to prevent. The other tempting fix is to
    drop the caller's own pre-check and try the call again, which restores the
    wrong diagnosis. Both are caught here.

    WHAT THIS DOES NOT DO, said plainly: it does not verify PROSE. "Headers
    describe behaviour correctly" is not mechanically checkable -- a gate over
    comments either cannot fail or fires on every paragraph. This checks the one
    thing that IS checkable and was the real defect: a call that cannot succeed.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TALLY IS REPRODUCED, NOT REPLACED BY `rediacc_ci.controls.Controls`, and this is the one decision in the file worth arguing about. The twin sources `.ci/scripts/lib/gate-controls.sh`, whose own header records why that file exists: "Extracted 2026-09-06 after check:ci-shape-duplication caught the same ~5 lines at three copies (check-release-key-canonical,
check-release-signing-coverage, check-staging-tag-guard) and was right to". The twin's line for it is "One copy of the tally, shared: check:ci-shape-duplication caught three."

`Controls` prints `FAIL  <label>: got <got!r>, wanted <want!r>`; gate-controls.sh
prints ` FAIL <label> (got '<got>' want '<want>')`. Both are findings to `scripts/lib/shadow-gate.ts` and their TEXT differs, so a port using `Controls`
for the gate's own output would disagree with the twin on every failing control
and the differential would read MISMATCH_FINDINGS for a port that is behaving correctly. The tally below is therefore a faithful transliteration of the bash one, and `Controls` is used only for `--selftest`, where nothing compares text.

That leaves a real duplication -- gate-controls.sh in bash and `_GateTally` here -- and the right home for it is a shared `rediacc_ci.gate_controls`, byte-compatible
with the bash file, so the next port of a gate-controls consumer (there are three)
does not make a third copy. That module is not created here because this change
owns four files and none of them is a new shared module; it is named so the next
writer does not have to rediscover it.

THE ENVIRONMENT SEAMS ARE THE TWIN'S, UNCHANGED. `STAGING_GUARD_ROOT` and `STAGING_GUARD_TARGET` keep their names so one harness drives either implementation with one pair of variables. The twin's default for ROOT is `git rev-parse --show-toplevel 2>/dev/null || echo .`, which is NOT `rediacc_ci.paths.repo_root()`: it falls back to the CURRENT DIRECTORY outside a work tree, where
`repo_root()` would answer with the package's own location. The twin's fallback is reproduced exactly, because a gate that silently judges a different tree than the operator is standing in is the failure the seam exists to avoid.

`set -uo pipefail` AND NOT `set -e`. The twin deliberately omits `-e`: every control must run even after one fails, or a single early failure hides the rest and the tally reports 1 of 1 instead of 1 of 3. Nothing here short-circuits either.

THE REGEXES ARE ERE, TRANSLITERATED, NOT REWRITTEN. `[[:space:]]` becomes an explicit class rather than `\\s`, because Python's `\\s` also matches unicode separators and the two would disagree on a file containing one. `\\^staging-` is an ESCAPED caret: a literal `^staging-` anywhere in the line, which is what
matches the `=~ ^staging-` in the subject.

`grep -c` COUNTS LINES, NOT MATCHES, and the twin compares that count against the string "1". Two lines carrying `^staging-` therefore FAIL the rail control. That strictness is carried across: a second copy of the rail means the guard was edited, and this gate is exactly the reader that should look.

TWO PLACES A PATHOLOGICAL PATH SPLITS THE TWO IMPLEMENTATIONS, both measured on 2026-09-06 by running the pair over generated trees rather than by reading them.
`${hit%%:*}` and `for f in $call_files` are the two lines involved, and neither
implementation is right about either case; what differs is how wrong they get.

  1. A COLON IN A SCANNED PATH. `.ci/scripts/release/a:b.sh` becomes the
     truncated `.../release/a` on BOTH sides, because both split the grep hit at
     its first colon. The twin then feeds that non-existent path to `grep -qE`,
     which prints `No such file or directory` and exits non-zero, so `guarded`
     stays 0 and the control FAILS by name. This port called `read_text` on it
     and died with an uncaught `FileNotFoundError`: no verdict at all, and a
     traceback that reads as flake. THAT IS FIXED, in `main` below: an unreadable
     call file reads as empty and fails its control, which is what `grep -q`
     failing means. The truncation itself is left alone deliberately -- it is the
     twin's, and changing it here would move the control's NAME and make every
     shadow row a false mismatch.

  2. A SPACE IN A SCANNED PATH. `.ci/scripts/release/with space/promote.sh`
     produces ONE control here and TWO in the twin, whose `for f in $call_files`
     word-splits the accumulated string and then reports two controls named after
     the fragments (`.../release/with` and `space/promote.sh`), both failing
     because neither path exists. This is NOT reproduced. Porting it would mean
     inventing findings that name paths which are not files, and the twin's own
     `grep:` errors on stderr say plainly that it did not read what it claims to
     have checked. The port names the real file once and rules on it. Neither
     path occurs in this repository today; both are recorded so the next reader
     of a shadow mismatch over such a tree knows which side to believe.

WHAT NEITHER IMPLEMENTATION CAN SEE: whether the guard's regex is CORRECT, and whether a caller computes its tag at runtime from something that only sometimes starts with `staging-`. A literal or a pre-check is the evidence available in the file, and that is all this rules on.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci.controls import Controls

# The seams, spelled exactly as the twin spells them.
ROOT_ENV = "STAGING_GUARD_ROOT"
TARGET_ENV = "STAGING_GUARD_TARGET"
DEFAULT_TARGET_REL = ".ci/scripts/docker/cleanup-staging.sh"

# The two trees scanned, and the two basename globs, from the twin's grep line.
SCAN_DIRS = (".ci", ".github")
SCAN_SUFFIXES = (".sh", ".yml")

# `.py` callers are scoped to `.ci/scripts` ONLY, not all of SCAN_DIRS, and this is NOT what agent/PLAN-w7p4w-docker-cutover.md §3 literally says ("widen the
# `grep --include` list to add `--include='*.py'`"). Doing that literally --
# scanning ALL of `.ci` for `.py` -- was tried first and turned 1 real call site into 18: `.ci/rediacc_ci` is this package's OWN implementation, tests and regex constants, and it is FULL of self-referential mentions of this exact needle (this module's own NEEDLE_RE/CALL_RE source, the synthetic caller fixtures in test_quality_staging_tag_guard.py, the `cleanup-staging.sh` mention
# in `cleanup_staging.py`'s own docstring, the cleanup_channel_docker_tags.py port's prose). That is the SAME "extension-shaped matcher" class of bug this gate's own header warns about, just for `.py` instead of `.sh`. `.ci/scripts` is the directory that actually holds executable entry points and release forwarders (mirroring what `.sh` already is for the twin), so `.py` scanning
# is scoped there and nowhere else in `.ci`.
PY_SCAN_DIR = ".ci/scripts"
PY_SUFFIX = ".py"

# The safety rail itself, as it appears in the subject: an escaped caret in ERE, so a LITERAL "^staging-" anywhere in the line.
RAIL_RE = re.compile(r"\^staging-")

# `grep -vE ':[0-9]+:[[:space:]]*#'` -- a grep hit whose matched line is a comment. Unanchored, exactly as the twin's is.
COMMENT_HIT_RE = re.compile(r":[0-9]+:[ \t\n\r\f\v]*#")

# `grep -E 'cleanup[-_]staging\.(sh|py)["\']?[[:space:]]+(--tag|"\$)'` -- an EXECUTING call, not a mention in prose. Widened to match either the bash twin's name or the Python port's, per agent/PLAN-w7p4w-docker-cutover.md §3.
CALL_RE = re.compile(r"cleanup[-_]staging\.(sh|py)[\"']?[ \t\n\r\f\v]+(--tag|\"\$)")

# `grep -qE '\^staging-|--tag[[:space:]]+["\']?staging-'` -- a caller proves it cannot pass a tag the guard rejects, either by testing the prefix itself or by passing a literal.
GUARDED_RE = re.compile(r"\^staging-|--tag[ \t\n\r\f\v]+[\"']?staging-")

# The needle the recursive scan looks for, `grep -rn 'cleanup[-_]staging\.(sh|py)'`.
NEEDLE_RE = re.compile(r"cleanup[-_]staging\.(sh|py)")

# `gate_finish 3` in the twin: the rail, the call-site floor, and at least one caller. A battery that did not run is not a green one.
MIN_CONTROLS = 3


class _GateTally:
    """`.ci/scripts/lib/gate-controls.sh`, transliterated byte for byte.

    Not `rediacc_ci.controls.Controls`: see the port notes. The strings below are the gate's OUTPUT CONTRACT and `scripts/lib/shadow-gate.ts` compares them against the bash twin's, so a nicer wording here is a false mismatch there.
    """

    def __init__(self) -> None:
        self.fails = 0
        self.count = 0

    def check(self, label: str, got: str, want: str) -> None:
        """`gate_check`: stdout on pass, stderr on failure, both indented two."""
        self.count += 1
        if got == want:
            print("  ok    %s" % label)
        else:
            self.fails += 1
            print("  FAIL  %s (got '%s' want '%s')" % (label, got, want), file=sys.stderr)

    def finish(self, minimum: int, subject: str) -> bool:
        """`gate_finish`: the floor, then the verdict. True when green."""
        if self.count < minimum:
            print(
                "FAIL  only %d control(s) ran; the battery is not being executed as written"
                % self.count,
                file=sys.stderr,
            )
            self.fails += 1
        if self.fails:
            print(
                "✗ %s: %d of %d control(s) failed" % (subject, self.fails, self.count),
                file=sys.stderr,
            )
            return False
        print("✓ %s: %d control(s) passed" % (subject, self.count))
        return True


def default_root() -> str:
    """`$(git rev-parse --show-toplevel 2>/dev/null || echo .)`.

    Reproduced rather than delegated to `rediacc_ci.paths.repo_root()`, which answers with the package's own location outside a work tree where this answers with the current directory. See the port notes.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    out = (completed.stdout or "").strip()
    return out if completed.returncode == 0 and out else "."


def grep_hits(root: pathlib.Path) -> tuple[list[str], int]:
    """`grep -rn 'cleanup-staging\\.sh' <root>/.ci <root>/.github --include=*.sh --include=*.yml`.

    Returns (hits, files_read). Each hit is `<abs path>:<lineno>:<line>`, which
    is the shape the twin's `${hit%%:*}` splits on. `files_read` is the
    anti-vacuity evidence the twin does not collect: it refuses when no CALL SITE is found, which cannot distinguish "the callers were fixed" from "the scan read nothing at all".
    """
    hits: list[str] = []
    files_read = 0
    py_scan_base = root / PY_SCAN_DIR
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.is_dir():
            continue  # `2>/dev/null`: a missing directory is silent to the twin
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix in SCAN_SUFFIXES:
                pass
            elif path.suffix == PY_SUFFIX:
                # Scoped to PY_SCAN_DIR regardless of which SCAN_DIRS entry this walk is under -- see PY_SCAN_DIR's own comment for why.
                try:
                    path.relative_to(py_scan_base)
                except ValueError:
                    continue
            else:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files_read += 1
            for number, line in enumerate(text.split("\n"), start=1):
                if NEEDLE_RE.search(line):
                    hits.append("%s:%d:%s" % (path, number, line))
    return hits, files_read


def executing_calls(hits: list[str], target: pathlib.Path) -> tuple[list[str], int]:
    """The twin's two filter greps plus its dedupe loop.

    Returns (files in first-seen order, number of hits). The TARGET is skipped: `cleanup-staging.sh` mentioning its own name in its usage header is not a caller of itself.
    """
    files: list[str] = []
    n_calls = 0
    for hit in hits:
        if COMMENT_HIT_RE.search(hit):
            continue
        if not CALL_RE.search(hit):
            continue
        path = hit.split(":", 1)[0]  # `${hit%%:*}`
        if path == str(target):
            continue
        n_calls += 1
        if path not in files:
            files.append(path)
    return files, n_calls


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns the process exit code; never raises for a verdict."""
    if argv and argv[0] == "--selftest":
        return selftest()

    root = pathlib.Path(os.environ.get(ROOT_ENV) or default_root())
    target = pathlib.Path(os.environ.get(TARGET_ENV) or str(root / DEFAULT_TARGET_REL))

    if not target.is_file():
        print("✗ %s not found -- nothing was verified" % target, file=sys.stderr)
        return 1

    tally = _GateTally()

    # The safety rail itself. If this goes, every assertion below is meaningless. `grep -c` counts LINES, and the twin wants exactly one.
    rail_lines = sum(
        1
        for line in target.read_text(encoding="utf-8", errors="replace").split("\n")
        if RAIL_RE.search(line)
    )
    tally.check("cleanup-staging.sh still refuses a non-staging tag", str(rail_lines), "1")

    hits, files_read = grep_hits(root)
    call_files, n_calls = executing_calls(hits, target)

    # PRINT THE SHAPE, NOT JUST THE VERDICT, and print it as CHATTER. The twin says nothing about how much tree it read, so "no call site found" cannot be told apart from "the scan read nothing". This line is the difference, and the `→` prefix is what keeps it out of the compared finding set.
    print(
        "→ staging tag guard: scanned %d file(s) under %s" % (files_read, " and ".join(SCAN_DIRS)),
        file=sys.stderr,
    )

    # ANTI-VACUITY. A rename or a moved tree would find zero call sites and this gate would pass having checked nothing at all.
    tally.check("at least one executing call site was found", "1" if n_calls >= 1 else "0", "1")
    if n_calls < 1:
        print(
            "✗ VACUOUS: no executing call site of cleanup-staging.sh found under .ci or .github.",
            file=sys.stderr,
        )
        print(
            "  Either it is genuinely unused, or this scan broke. Check before trusting the tick.",
            file=sys.stderr,
        )
        return 1

    # Each caller must prove it cannot pass a tag the guard rejects: either it passes a literal `staging-` value, or it tests for the prefix itself before calling.
    for path in call_files:
        rel = path[len(str(root)) + 1 :] if path.startswith(str(root) + "/") else path
        # A CALL FILE THAT CANNOT BE READ IS UNGUARDED, NOT A CRASH. `${hit%%:*}`
        # strips at the FIRST colon, so a scanned path containing one -- say `.ci/scripts/release/a:b.sh` -- yields the truncated `.../release/a`, which exists in neither implementation's tree. The twin hands that to `grep -qE ... "$f"`, grep prints `No such file or directory` and exits non-zero, `guarded` stays 0, and the gate still reaches a VERDICT. This port called `read_text`
        # on it and died with an uncaught FileNotFoundError: same exit status by accident, no verdict, and a traceback that reads as environmental flake rather than as the control failure it replaced.
        # Measured 2026-09-06 on a fixture whose only caller was `a:b.sh`; the
        # twin reported `.ci/scripts/release/a guards its call ... (got '0' want '1')` and this port reported a stack trace. `grep -q`'s failure is the contract, so an unreadable file reads as empty and fails its control.
        try:
            body = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        guarded = "1" if GUARDED_RE.search(body) else "0"
        tally.check("%s guards its call against a non-staging tag" % rel, guarded, "1")

    # THE SUBJECT LINE IS THE TWIN'S, WORD FOR WORD, AND THAT COST ONE MISMATCH. `gate_finish` interpolates it into BOTH verdicts, and the failing one -- "✗ <subject>: N of M control(s) failed" -- carries the ✗ marker, so it is a FINDING and not chatter. This port first read "(%d call site(s) across %d file(s) scanned)" here, on the assumption that a verdict line is banner text a
    # port may reword. The shadow differential refused all three trees
    # with MISMATCH_FINDINGS on 2026-09-06 and named the line; the rows are in
    # `.ci/shadow/w7p2-stagingtag.observations.jsonl` and those tree ids stay disqualified. The scanned-file count, which is genuinely worth printing, now goes out above as its own `→` line, where `shadow-gate.ts` classifies it as chatter and a port is allowed to say more than its twin.
    subject = "staging tag guard (%d call site(s))" % n_calls
    if not tally.finish(MIN_CONTROLS, subject):
        print(
            "  A caller that passes a non-staging tag can NEVER succeed, and the failure",
            file=sys.stderr,
        )
        print(
            "  reads as a token-scope problem. Guard the call; do not widen the rail.",
            file=sys.stderr,
        )
        return 1
    return 0


# The subject, reduced to the one line this gate rules on. Used to build fixture
# trees in the selftest; the real file is 100+ lines of GHCR plumbing that has
# nothing to do with the assertion.
RAIL_LINE = '[[ "$TAG" =~ ^staging- ]] || exit 1\n'


def selftest() -> int:
    """Plant a defect in BOTH directions and require the gate to notice."""
    # floor=16 rather than 0: the floor is the only thing that catches a selftest
    # whose cases stopped executing, and a default of zero is a floor that cannot fail. See rediacc_ci.controls for the five drifted copies that taught it. It tracks the case count below (16), so deleting a case reds the gate.
    ctl = Controls("staging-tag-guard", floor=16, verbose=True)
    saved_env = dict(os.environ)

    guarded_caller = (
        "#!/bin/bash\n"
        'if [[ "$CHANNEL" =~ ^staging- ]]; then\n'
        '  "$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"\n'
        "fi\n"
    )
    literal_caller = (
        '#!/bin/bash\n"$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag staging-abc123\n'
    )
    unguarded_caller = '#!/bin/bash\n"$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"\n'

    def run(files: dict[str, str], rail: str = RAIL_LINE, target: str | None = None) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            if target is None:
                subject = root / DEFAULT_TARGET_REL
                subject.parent.mkdir(parents=True, exist_ok=True)
                subject.write_text(
                    "#!/bin/bash\n# usage: cleanup-staging.sh --tag X\n" + rail, encoding="utf-8"
                )
            for rel, content in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            os.environ[ROOT_ENV] = str(root)
            if target is not None:
                os.environ[TARGET_ENV] = str(root / target)
            else:
                os.environ.pop(TARGET_ENV, None)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved_env)

    ctl.check(
        "CONTROL: a caller that pre-checks the prefix passes",
        run({".ci/scripts/release/cleanup-channel-docker-tags.sh": guarded_caller}),
        0,
    )
    ctl.check(
        "CONTROL: a caller passing a LITERAL staging- tag passes",
        run({".ci/scripts/release/x.sh": literal_caller}),
        0,
    )

    # THE PLANT. The 2026-09-06 defect itself: a call with CHANNEL and no pre-check, which the rail rejects every time.
    ctl.check(
        "PLANT: an unguarded call is the 2026-09-06 defect",
        run({".ci/scripts/release/cleanup-channel-docker-tags.sh": unguarded_caller}),
        1,
    )
    ctl.check(
        "PLANT: one guarded and one unguarded caller still fails",
        run(
            {
                ".ci/scripts/release/ok.sh": guarded_caller,
                ".ci/scripts/release/bad.sh": unguarded_caller,
            }
        ),
        1,
    )
    ctl.check(
        "PLANT: an unguarded call from a workflow .yml is found too",
        run({".github/workflows/release.yml": unguarded_caller}),
        1,
    )

    # The rail itself, both directions. Widening the guard is the tempting "fix" this gate exists to refuse.
    ctl.check(
        "PLANT: the rail removed from cleanup-staging.sh fails",
        run({".ci/scripts/release/ok.sh": guarded_caller}, rail=""),
        1,
    )
    ctl.check(
        "PLANT: the rail DUPLICATED fails (grep -c counts lines, want exactly 1)",
        run({".ci/scripts/release/ok.sh": guarded_caller}, rail=RAIL_LINE + RAIL_LINE),
        1,
    )

    # VACUITY, which is the shape the twin was written to refuse.
    ctl.check("VACUITY: no call site at all is refused, not passed", run({}), 1)
    ctl.check(
        "VACUITY: a mention in a COMMENT is not an executing call site",
        run({".ci/scripts/release/doc.sh": '# cleanup-staging.sh --tag "$CHANNEL" would fail\n'}),
        1,
    )
    ctl.check(
        "VACUITY: a mention in prose with no --tag is not a call site",
        run({".ci/scripts/release/doc.sh": 'echo "see cleanup-staging.sh for details"\n'}),
        1,
    )
    ctl.check(
        "VACUITY: a call in a NON-scanned extension is not seen",
        run({"docs/agent-reference/release.md": unguarded_caller}),
        1,
    )
    ctl.check(
        "PLANT: a missing cleanup-staging.sh refuses rather than passing",
        run({".ci/scripts/release/ok.sh": guarded_caller}, target="nowhere/cleanup-staging.sh"),
        1,
    )
    # A VERDICT, NOT A TRACEBACK. Both sides truncate this caller's path at its first colon and then look for a file that is not there. Before 2026-09-06 this raised FileNotFoundError out of main(), which exits 1 for the wrong reason and prints a stack trace where the twin prints a failing control.
    ctl.check(
        "PLANT: a colon in a caller's path fails its control, never a traceback",
        run({".ci/scripts/release/a:b.sh": unguarded_caller}),
        1,
    )

    # The pure helpers, driven directly, so the two filter greps are pinned.
    target = pathlib.Path("/repo/.ci/scripts/docker/cleanup-staging.sh")
    hits = [
        '/repo/.ci/scripts/release/a.sh:66:  "$D/cleanup-staging.sh" --tag "$CHANNEL"',
        '/repo/.ci/scripts/release/a.sh:15:# cleanup-staging.sh --tag "$CHANNEL" is refused',
        "/repo/.ci/scripts/release/a.sh:20:echo see cleanup-staging.sh for why",
        "%s:6:#   cleanup-staging.sh --tag staging-abc123" % target,
    ]
    files, n_calls = executing_calls(hits, target)
    ctl.check("HELPER: only the executing call counts", n_calls, 1)
    ctl.check("HELPER: the file is named once", files, ["/repo/.ci/scripts/release/a.sh"])
    ctl.check(
        "HELPER: the target's own usage header is not a call site",
        executing_calls(["%s:7:  cleanup-staging.sh --tag staging-x" % target], target),
        ([], 0),
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
