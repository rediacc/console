"""Every path a greenlight closure names must exist on disk AND be tracked by git.

Ported from `.ci/scripts/quality/check-greenlight-closures.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__`; the committed differential ledger under `.ci/shadow/` is what licensed the retirement.

WHY THE TWIN EXISTS, AND IT IS NOT THE OBVIOUS REASON. Carried over from its header, because the archaeology is the half of a gate that cannot be recovered
from the code:

  greenlight decides whether a previous green run still covers this one by
  hashing the CONTENTS of a declared closure of paths. It reads the candidate
  side out of the REMOTE commit, which
  `.ci/scripts/test/gates/test-greenlight.sh` models with `git ls-tree HEAD`.

  So a closure path that is present on disk but NOT COMMITTED resolves to
  nothing on the candidate side: greenlight throws its named refusal, emits no
  `run_<key>=false`, and gate-test:greenlight goes red -- with an error that
  blames the key, not the path. That is exactly what happened on 2026-09-02 when
  `.github/actions/bws-secrets` was added to eighteen closures before the action
  itself was committed, and it cost real time to diagnose because the symptom
  names the wrong thing. See TRAPS.md, trap-id
  uncommitted-file-reds-a-remote-fake.

  The same check catches the duller and more common cases: a typo in a closure
  path, and a path left behind after the file it names moved or was deleted.
  Both silently shrink what greenlight protects, because a path that resolves to
  nothing contributes nothing to the hash.

  WHAT IT DELIBERATELY DOES NOT ASSERT: presence in HEAD. Staged-but-uncommitted
  is still invisible to the candidate side, but demanding HEAD-presence would red
  on every new file in an uncommitted working tree -- the state this repo works
  in by standing order. Tracked is the strongest invariant that is true
  continuously.

  Exit 1 on any offender, 2 on setup error.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE CLOSURE LIST COMES FROM NODE, AND IT HAS TO. `.ci/scripts/ci/greenlight.cjs`
is a CommonJS program whose `CLOSURES` object is built by executing JavaScript;
there is no data file to read. So both implementations shell out to `node -e`
with the same three-line extractor, and a port that "simplified" this into a
regex over the .cjs source would silently miss any path the file computes rather than writes as a literal. The extractor is carried verbatim.

WHAT HAPPENS WHEN NODE IS ABSENT, and this is a defect being preserved. The twin
writes `paths="$(node -e '...')" || return 2`, so a missing node makes `scan`
return 2. But the main path calls it as `out="$(scan)" || { ...; exit 1; }`,
which cannot distinguish 2 from 1: the header comment promises "exit 1 on any offender, 2 on setup error" and the setup error exits 1 anyway. The operator then reads "greenlight closure paths (see above)" with nothing above it. The port keeps the exit code identical, because the verdict is what a port must preserve, and ADDS one unmarked diagnostic line naming the missing binary
and the fix. An unmarked, unindented line is chatter to `scripts/lib/shadow-gate.ts`, so it cannot change the compared finding set -- which is exactly why it is safe to add and why it is not a finding.

`(see above)` IS A LIE IN BOTH IMPLEMENTATIONS. `scan`'s offender lines are captured into `$out` by the command substitution, so they are printed AFTER the header that points at them, not above it. Preserved, because moving them changes the output a human diff is read against, and reported.

THE `-e` TEST FOLLOWS SYMLINKS, so a closure path that is a symlink to a deleted target reads as ON DISK and is then judged only on tracked-ness. That is the twin's behaviour and it is left alone; `Path.exists()` follows symlinks too, so the two agree by construction rather than by care.

ONE `git ls-files` PER PATH, NOT ONE BATCHED CALL. The obvious optimisation -- read the whole index once and test membership in Python -- changes the answer
for a closure path that names a DIRECTORY. `git ls-files --error-unmatch --
<dir>` succeeds when the directory contains tracked files, because the pathspec matched something; a set-membership test on file paths would report the directory as untracked. Eighteen closures name `.github/actions/bws-secrets`, which is a directory, so this is the shape of the very incident the gate exists
for.

THE COLOUR IS DECIDED BY `CI` ALONE in the twin -- `if [[ "${CI:-}" == "true" ]];
then RED="" ...` -- with no tty test and no NO_COLOR test, which is the 9-file
variant `rediacc_ci.log`'s docstring measures. So a developer piping this gate into `less` gets escape sequences. The port uses the house logger, which tests the stream it writes to and honours NO_COLOR. Reported, not reproduced; ANSI is stripped before the differential compares, so no verdict moves.

THE ANTI-VACUITY BRANCH IS THE ONE TO PROTECT. `[[ $n -gt 0 ]] || { echo "  no
closure paths found -- this check is blind"; return 1; }` is what stops an empty
closure set from reading as success, and it is carried with its wording intact because the wording is what stops the next reader from deleting it.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# Where the closure definitions live, relative to the repository root.
GREENLIGHT_CJS = ".ci/scripts/ci/greenlight.cjs"

# The twin's node extractor, byte for byte. Every closure's `paths` array, de-duplicated through a Set and sorted, joined by newlines with no trailing one -- which is why the reader below drops empty lines rather than trusting the shape.
NODE_EXTRACTOR = """
          const { CLOSURES } = require(process.argv[1]);
          const out = new Set();
          for (const c of Object.values(CLOSURES)) for (const p of c.paths || []) out.add(p);
          process.stdout.write([...out].sort().join("\\n"));
        """

# The two environment seams the twin uses to point its own control at a fixture. Kept by name so `--scan` behaves identically when driven the twin's way.
ROOT_ENV_VAR = "GL_ROOT"
PATHS_ENV_VAR = "GL_CLOSURE_PATHS"


class ScanError(RuntimeError):
    """The closure list could not be obtained at all. The twin's `return 2`.

    A distinct type rather than a magic number so the caller can tell "this gate found offenders" from "this gate could not run", which is the distinction the twin's own header promises and its main path then loses.
    """


def closure_paths(root: pathlib.Path) -> list[str]:
    """Every path named by any closure, sorted and de-duplicated, via node.

    Raises ScanError when node cannot produce the list. The twin turns that into `return 2`; see the port notes for what its caller then does with it.
    """
    cjs = root / GREENLIGHT_CJS
    try:
        proc = subprocess.run(
            ["node", "-e", NODE_EXTRACTOR, str(cjs)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        # A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, not a traceback that reads as flake. The message is raised rather than printed so main() decides the stream.
        raise ScanError(
            "node is not on PATH, so the closure list could not be read from %s. "
            "Install Node 22 (the version every workflow pins) and re-run." % GREENLIGHT_CJS
        ) from exc
    if proc.returncode != 0:
        raise ScanError(
            "node could not read the closure list from %s (exit %d): %s"
            % (GREENLIGHT_CJS, proc.returncode, proc.stderr.strip() or "no stderr")
        )
    return [line for line in proc.stdout.split("\n") if line]


def is_tracked(root: pathlib.Path, rel: str) -> bool:
    """`git -C <root> ls-files --error-unmatch -- <rel>` succeeded.

    One call per path; see the port notes for why the batched form is wrong for a closure path that names a directory.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def scan(root: pathlib.Path, path_list: list[str]) -> tuple[int, list[str], int]:
    """Judge `path_list` against `root`. Returns (exit code, lines, count).

    `lines` are the offender lines the twin echoes, in the twin's order and with the twin's two-space indent, because that indent is what makes `scripts/lib/shadow-gate.ts` fold them into the finding above. The count is what the success message interpolates.

    ZERO PATHS IS A FAILURE, NEVER A PASS. A closure set that shrank to nothing would otherwise read as "every declared path is fine", which is true and worthless.
    """
    lines: list[str] = []
    bad = 0
    n = 0
    for rel in path_list:
        if not rel:
            continue
        n += 1
        if not (root / rel).exists():
            lines.append("  %s -- named by a closure but NOT ON DISK" % rel)
            bad += 1
            continue
        if not is_tracked(root, rel):
            lines.append(
                "  %s -- on disk but NOT TRACKED; the candidate side reads the remote" % rel
            )
            lines.append("      commit, so it resolves to nothing there and greenlight refuses")
            bad += 1
    if n == 0:
        lines.append("  no closure paths found -- this check is blind")
        return 1, lines, 0
    if bad != 0:
        return 1, lines, n
    return 0, lines, n


def control() -> str | None:
    """Both directions, planted against a throwaway repository. None means green.

    A missing path and an untracked path must EACH be reported, and a clean pair must be silent. Without the silent case a checker that reported everything would pass its own controls, which is the failure mode this whole function exists to refuse.

    Returns the twin's own "CONTROL FAILED: ..." string so main can print it on the same stream the twin does.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        try:
            subprocess.run(["git", "init", "-q", "."], cwd=tmp, check=True, capture_output=True)
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=t@t",
                    "-c",
                    "user.name=t",
                    "commit",
                    "-qm",
                    "x",
                ],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            # The twin's `|| return 1` on the whole fixture-building subshell.
            return "CONTROL FAILED: a bad fixture passed"

        code, lines, _ = scan(root, ["tracked.txt", "untracked.txt", "no-such-file.txt"])
        text = "\n".join(lines)
        if code == 0:
            return "CONTROL FAILED: a bad fixture passed"
        if "no-such-file.txt" not in text:
            return "CONTROL FAILED: missing path unreported"
        if "untracked.txt" not in text:
            return "CONTROL FAILED: untracked path unreported"

        code, _, _ = scan(root, ["tracked.txt"])
        if code != 0:
            return "CONTROL FAILED: a clean fixture was reported"
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 offender, 2 control failure.

    `--selftest` is intercepted BEFORE any real scan. `--scan` is the twin's own internal re-entry point, kept by name and honouring the same two environment seams, so a caller that drives the bash form can drive this one unchanged.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    if args and args[0] == "--scan":
        override_root = os.environ.get(ROOT_ENV_VAR)
        scan_root = pathlib.Path(override_root) if override_root else root
        override_paths = os.environ.get(PATHS_ENV_VAR, "")
        if override_paths:
            path_list = override_paths.split("\n")
        else:
            try:
                path_list = closure_paths(root)
            except ScanError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        code, lines, n = scan(scan_root, path_list)
        for line in lines:
            print(line)
        if code == 0:
            print(n)
        return code

    # CONTROL FIRST. Every verdict below is meaningless if the instrument cannot tell a bad fixture from a good one, so the instrument is proven before the tree is judged rather than after.
    failure = control()
    if failure is not None:
        # STDOUT for the control's own line, matching the twin: `control` echoes it and its caller only adds the banner.
        print(failure)
        log.error("instrument control failed; every verdict below would be meaningless")
        return 2

    try:
        path_list = closure_paths(root)
    except ScanError as exc:
        # UNMARKED AND UNINDENTED, so `scripts/lib/shadow-gate.ts` reads it as chatter and the compared finding set is unchanged. This is the one line the port adds; see the port notes for the defect it names.
        print(str(exc), file=sys.stderr)
        path_list = []
        code, lines, n = 1, ["  no closure paths found -- this check is blind"], 0
    else:
        code, lines, n = scan(root, path_list)

    if code != 0:
        log.error("greenlight closure paths (see above)")
        for line in lines:
            print(line, file=sys.stderr)
        print(
            "  Fix: commit the file, correct the path, or drop it from the closure in",
            file=sys.stderr,
        )
        print(
            "  .ci/scripts/ci/greenlight.cjs. A path that resolves to nothing silently",
            file=sys.stderr,
        )
        print("  shrinks what greenlight protects.", file=sys.stderr)
        return 1

    # THE SHAPE, NOT JUST THE VERDICT: the count is printed so a reader notices when it collapses, and the residue paragraph names what is NOT covered. STDOUT, AND DELIBERATELY NOT `log.info`. The house logger writes to stderr, which would split ONE paragraph across TWO streams: the headline on stderr and its own indented continuation lines below on stdout. A reader piping stdout
    # would see six dangling continuation lines under no heading. The twin echoes all seven to stdout, `battery_clean_tree` does the same for the same reason, and the control branch above already states the rule ("STDOUT for the control's own line, matching the twin"). The `\u2713` is written out rather than delegated because `log.info` is what prefixes it.
    print("\u2713 greenlight closures: all %d declared path(s) exist and are tracked" % n)
    print("  (controls: a missing path and an untracked path each reported, a clean pair silent)")
    print("  Residue, stated because it is NOT covered: TRACKED is not IN HEAD. A path that is")
    print("  staged but uncommitted still resolves to nothing on the candidate side, so")
    print("  gate-test:greenlight can be red while this passes. Asserting HEAD-presence instead")
    print("  would red on every new file in an uncommitted tree, which is this repo's normal")
    print("  state, and a gate that is always red gets switched off. See TRAPS.md,")
    print("  uncommitted-file-reds-a-remote-fake.")
    return 0


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. The mirrors -- a tracked file, a tracked DIRECTORY, a clean list -- are the half that proves this gate does not simply report everything, and the directory case is the one the batched-lookup optimisation would break.
    """
    ctl = Controls("greenlight-closures", floor=20, verbose=True)

    # The instrument's own control, run first for the same reason the gate runs it first: everything below is a claim about an instrument.
    ctl.check("CONTROL: the instrument's own control passes", control(), None)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", "."], cwd=tmp, check=True, capture_output=True)
        (root / "tracked.txt").write_text("t\n", encoding="utf-8")
        (root / "untracked.txt").write_text("u\n", encoding="utf-8")
        (root / "dir").mkdir()
        (root / "dir" / "inside.txt").write_text("i\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "tracked.txt", "dir/inside.txt"],
            cwd=tmp,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
            cwd=tmp,
            check=True,
            capture_output=True,
        )

        # -- THE VACUITY CASE, first and loudest ----------------------------
        code, lines, n = scan(root, [])
        ctl.check("VACUITY: an empty closure list exits non-zero", code, 1)
        ctl.check(
            "VACUITY: it says the check is blind",
            lines,
            ["  no closure paths found -- this check is blind"],
        )
        ctl.check("VACUITY: the counted total is zero", n, 0)
        # A list of nothing but empty strings is the same vacuity wearing a
        # different shape: `while IFS= read -r p; [[ -n "$p" ]] || continue`.
        code, _, n = scan(root, ["", "", ""])
        ctl.check("VACUITY: a list of empty strings is also blind", (code, n), (1, 0))

        # -- MIRRORS: the shapes that must stay silent -----------------------
        ctl.check("MIRROR: a tracked file passes", scan(root, ["tracked.txt"]), (0, [], 1))
        ctl.check(
            "MIRROR: a tracked DIRECTORY passes (the bws-secrets shape)",
            scan(root, ["dir"]),
            (0, [], 1),
        )
        ctl.check(
            "MIRROR: two tracked paths pass and are counted",
            scan(root, ["tracked.txt", "dir"])[2],
            2,
        )

        # -- PLANTS ---------------------------------------------------------
        code, lines, _ = scan(root, ["no-such-file.txt"])
        ctl.check("PLANT: a path not on disk reds", code, 1)
        ctl.check(
            "PLANT: and names it as NOT ON DISK",
            lines,
            ["  no-such-file.txt -- named by a closure but NOT ON DISK"],
        )
        code, lines, _ = scan(root, ["untracked.txt"])
        ctl.check("PLANT: an untracked path reds", code, 1)
        ctl.check("PLANT: and names it as NOT TRACKED", "NOT TRACKED" in lines[0], True)
        ctl.check("PLANT: the untracked case prints its two-line explanation", len(lines), 2)
        # THE INCIDENT'S OWN SHAPE: an untracked DIRECTORY. On disk, so the first test passes; not in the index, so the second catches it. This is `.github/actions/bws-secrets` on 2026-09-02.
        (root / "newdir").mkdir()
        (root / "newdir" / "action.yml").write_text("x\n", encoding="utf-8")
        code, lines, _ = scan(root, ["newdir"])
        ctl.check("PLANT: an untracked DIRECTORY reds (the 2026-09-02 incident)", code, 1)
        ctl.check(
            "PLANT: and it is reported as NOT TRACKED, not as absent",
            "NOT TRACKED" in lines[0],
            True,
        )

        # A mixed list must report BOTH offenders and still count every path.
        code, lines, n = scan(root, ["tracked.txt", "untracked.txt", "no-such-file.txt"])
        ctl.check("PLANT: a mixed list reds", code, 1)
        ctl.check("PLANT: a mixed list counts every path, offenders included", n, 3)
        ctl.check("PLANT: a mixed list reports both offenders", len(lines), 3)

        # -- the whole gate, through main ------------------------------------
        def run() -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # No greenlight.cjs in this fixture, so the closure list cannot be read. THAT MUST BE A FAILURE, not a clean tree with nothing to check.
        ctl.check("VACUITY: an unreadable closure source is refused", run(), 1)

        # `--scan` with the twin's two environment seams, which is how the twin drives its own control. Kept working so a bash caller can be pointed at the port without changing its invocation.
        saved_root = os.environ.get(ROOT_ENV_VAR)
        saved_paths = os.environ.get(PATHS_ENV_VAR)
        os.environ[ROOT_ENV_VAR] = str(root)
        os.environ[PATHS_ENV_VAR] = "tracked.txt"
        try:
            ctl.check("--scan: the twin's env seams still drive a clean list", main(["--scan"]), 0)
            os.environ[PATHS_ENV_VAR] = "tracked.txt\nno-such-file.txt"
            ctl.check("--scan: and a dirty one reds", main(["--scan"]), 1)
        finally:
            for name, value in ((ROOT_ENV_VAR, saved_root), (PATHS_ENV_VAR, saved_paths)):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
