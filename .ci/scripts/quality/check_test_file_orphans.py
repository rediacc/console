#!/usr/bin/env python3
"""Every test/control file must be REACHED by something that CI runs.

THE DEFECT THIS CLOSES, paid for on 2026-08-23. `.claude/hooks/stop/
test-teammate-idle.py` was added with 20 controls, passed 20/20 when invoked by
hand, was committed, and ran NOWHERE. Its only mention anywhere else in the tree
was inside a code comment. Both existing wiring gates were green throughout:

  * `check-ci-parity.ts` compares the MANIFEST against the CI workflow surface.
    A file absent from the manifest is absent from both sides, so the two agree
    and it reports success.
  * `check_gate_reachability_coverage.py` asks whether every MANIFEST
    registration is reachable. It cannot ask about a file that never registered.

Both answer "is what we declared wired up?". Neither answers "is there anything
here we forgot to declare?" -- and that second question is the one an orphan
fails. A test nobody runs is worse than no test: it reports 20/20 to whoever
runs it by hand, and it is counted as coverage in review.

WHAT COUNTS AS REACHED, deliberately generous. This gate is not trying to model
the runner; it is trying to catch a file with NO path to CI at all. So a file is
reached if its basename appears anywhere outside itself in a shell script, a
manifest, a workflow, or package.json. That admits a reference from an
unreachable caller -- but a caller that is itself unreachable is a manifest
problem, which is precisely what the other two gates DO see. The gaps are
complementary on purpose.

ANTI-VACUITY. Zero discovered files is a failure, not a pass: a glob that stops
matching would otherwise report success having checked nothing. The success line
prints the counts so a collapse is visible rather than silent.
"""

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]

# Where test/control files live. Kept explicit rather than globbing the whole
# tree: node_modules and vendored fixtures are full of test-*.js that this gate
# has no business ruling on.
SEARCH_DIRS = (
    ".claude/hooks",
    ".ci/scripts/test/gates",
)
NAME_RE = re.compile(r"^test[-_].*\.(py|sh|ts)$")

# Files that legitimately run only by hand, each with a stated reason. Adding to
# this list is a deliberate act; forgetting to wire a NEW test file is not,
# which is the asymmetry that makes this gate work.
EXEMPT = {
    # <basename>: reason
}

# Where a reference would live if the file were wired. DIRECTORIES, not globs.
# `.claude/hooks/**/*.sh` was the first spelling and it silently missed
# `.claude/hooks/test-hooks.sh` -- the single most likely caller in the tree --
# because `**/` requires at least one intermediate directory and that file sits
# at depth 1. The gate reported the freshly-wired file as an orphan, which is
# how the bug was caught: a pathspec that is wrong in the narrowing direction
# produces FALSE POSITIVES here, so it announced itself. Had it been wrong the
# other way it would have gone quiet instead.
REF_DIRS = (
    ".claude/hooks",
    ".ci/scripts",
    ".github/workflows",
    "scripts/ci-runner",
    "package.json",
)
REF_SUFFIXES = (".sh", ".yml", ".yaml", ".ts", ".json")


def discover():
    out = []
    for d in SEARCH_DIRS:
        base = REPO / d
        if not base.is_dir():
            continue
        out.extend(p for p in base.rglob("*") if p.is_file() and NAME_RE.match(p.name))
    return sorted(out)


def referencing_files(name):
    """Files that mention `name`, excluding the file itself.

    `git grep -l` rather than a Python walk: it honours .gitignore, so a stale
    copy in an untracked scratch directory cannot make an orphan look reached.
    """
    try:
        r = subprocess.run(
            ["git", "grep", "-l", "--fixed-strings", name, "--", *REF_DIRS],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None  # cannot tell; the caller treats this as a failure, not a pass
    return [ln for ln in r.stdout.splitlines() if ln.strip() and ln.endswith(REF_SUFFIXES)]


def main():
    files = discover()
    if not files:
        print(
            "✗ discovered ZERO test files under %s -- the glob is broken, and a"
            % ", ".join(SEARCH_DIRS)
        )
        print("  green here would mean nothing. Fix the discovery before trusting this gate.")
        return 1

    orphans, checked, exempted = [], 0, 0
    for f in files:
        rel = f.relative_to(REPO).as_posix()
        if f.name in EXEMPT:
            exempted += 1
            continue
        checked += 1
        refs = referencing_files(f.name)
        if refs is None:
            print("✗ could not run git grep for %s -- reporting UNCHECKED rather than fine" % rel)
            return 1
        # A mention inside the file itself proves nothing.
        outside = [r for r in refs if r != rel]
        # A mention only in a comment is not a call. Cheap heuristic: require at
        # least one reference line that is not comment-only.
        real = []
        for r in outside:
            try:
                text = (REPO / r).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if f.name in line and not line.lstrip().startswith(("#", "//", "*")):
                    real.append(r)
                    break
        if not real:
            orphans.append((rel, outside))

    if orphans:
        print("✗ test file(s) that nothing CI runs reaches:\n")
        for rel, outside in orphans:
            print("  %s" % rel)
            if outside:
                print("      mentioned only in comments, by: %s" % ", ".join(outside))
            else:
                print("      mentioned nowhere else in the tree at all")
        print("\n  A test nobody runs is worse than no test: it reports green to whoever")
        print("  runs it by hand and is counted as coverage in review.")
        print("\n  Wire it, by whichever of these fits:")
        print("    - invoke it from a suite CI already runs (e.g. .claude/hooks/test-hooks.sh),")
        print("    - or register it in scripts/ci-runner/manifest.ts with its CI step.")
        print("  Do NOT add it to EXEMPT to get past this; that list is for files that")
        print("  genuinely must not run in CI, and each entry states why.")
        return 1

    print(
        "✓ all %d test file(s) are reached by something CI runs (%d exempt)" % (checked, exempted)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
