"""Port of `.ci/scripts/review/epic-context.sh`.

Hands a reviewer one epic's context in a single read: the worklist snapshot's own section for that epic, any `agent/PLAN-*.md` files it references (first 40 lines each), and the commits in this branch carrying its `PR-TASK:` trailer
with the files they touched. Read-only, never touches the network -- everything
printed comes from the checkout, matching the twin's own stated reason: a review action budgeted in turns cannot afford a failure that costs one to diagnose.

TWO EXTRACTORS, BOTH REPRODUCED WITH THEIR QUIRKS RATHER THAN CLEANED UP,
because the acceptance test for this port is agreement with the twin, not an improved twin. `_epic_section` mirrors the AWK that builds the printed body:
a `### ` heading line is never printed directly, only staged into `pending`;
it is emitted (heading, then a blank line) IMMEDIATELY BEFORE EACH LINE THAT MATCHES THE TRAILER, not once per section. A section with two matching trailer lines (two worklist items under one epic heading) prints that heading TWICE, once before each -- confirmed against the real `awk` before writing this, not inferred from reading it. That is almost certainly not what a human
skimming the source would expect the script to do, and it is exactly what it does, so the port does it too. `_epic_lines` (feeding the PLAN reference scan) is the simpler of the two: no staging, the trailer line itself and everything after it prints once, headings reset the section and are never printed.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

USAGE = """usage: epic-context.sh <epic-id> [branch]

Prints one epic's title, its worklist items with evidence, any plan file they
reference, and the commits carrying its PR-TASK trailer."""

PLAN_RE = re.compile(r"agent/PLAN-[A-Za-z0-9._-]+\.md")


def _epic_section(lines: list[str], epic: str) -> list[str]:
    """Mirror the first AWK block exactly, duplicate heading and all."""
    trailer = f"PR-TASK: {epic}"
    out: list[str] = []
    pending = ""
    insection = False
    for line in lines:
        if line.startswith("### "):
            insection = False
            pending = line
            continue  # the twin's `next`: no further rule sees this line
        if trailer in line:
            if pending != "":
                out.append(pending)
                out.append("")
            insection = True
        if insection:
            out.append(line)
    return out


def _epic_lines(lines: list[str], epic: str) -> list[str]:
    """Mirror the second AWK block: no staging, no duplication."""
    trailer = f"PR-TASK: {epic}"
    out: list[str] = []
    insection = False
    for line in lines:
        if line.startswith("### "):
            insection = False
        if trailer in line:
            insection = True
        if insection:
            out.append(line)
    return out


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(USAGE, file=sys.stderr)
        return 2

    epic = argv[0]
    repo_root = _git("rev-parse", "--show-toplevel").stdout.strip()
    branch = argv[1] if len(argv) > 1 else _git("branch", "--show-current").stdout.strip()
    branch_slug = branch.replace("/", "-")
    snap = pathlib.Path(repo_root) / "agent" / "pr" / f"{branch_slug}.md"

    if not snap.is_file():
        print(f"no snapshot at agent/pr/{branch_slug}.md; cannot describe {epic}", file=sys.stderr)
        return 1

    print("=" * 62)
    print(f"EPIC {epic}   (branch {branch})")
    print("=" * 62)
    print()

    lines = snap.read_text(encoding="utf-8").splitlines()
    for line in _epic_section(lines, epic):
        print(line)

    print()
    print("-------- plan files referenced by this epic ------------------")
    section = _epic_lines(lines, epic)
    plans = sorted({m.group(0) for text in section for m in PLAN_RE.finditer(text)})
    if not plans:
        print("(none referenced)")
    else:
        for f in plans:
            path = pathlib.Path(repo_root) / f
            if path.is_file():
                print(f"--- {f} (first 40 lines) ---")
                # Byte-for-byte `head -40`: write raw text, not `print()`, so a file missing its final trailing newline is not given one.
                with path.open("r", encoding="utf-8") as fh:
                    for _ in range(40):
                        chunk = fh.readline()
                        if chunk == "":
                            break
                        sys.stdout.write(chunk)
            else:
                print(f"--- {f}: referenced but NOT in this checkout ---")

    print()
    print(f"-------- commits carrying PR-TASK: {epic} ---------------------")
    base = os.environ.get("PR_BASE_REF") or "origin/main"
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", base],
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode == 0:
        grep = f"^PR-TASK: {epic}"
        shas = _git(
            "log", f"{base}..HEAD", "--no-merges", f"--grep={grep}", "--format=%H"
        ).stdout.splitlines()
        if len(shas) == 0:
            print(f"NO COMMITS carry this trailer in {base}..HEAD.")
            print("Either the epic has not been worked yet, or its commits are untagged,")
            print("in which case check:ci-pr-task-trailers is the gate that will say so.")
        else:
            subjects = _git(
                "log", f"{base}..HEAD", "--no-merges", f"--grep={grep}", "--format=%h %s"
            ).stdout.splitlines()
            for s in subjects:
                print(f"  {s}")
            print()
            print("  files touched:")
            files: set[str] = set()
            for sha in shas:
                shown = _git("show", "--name-only", "--format=", sha).stdout.splitlines()
                files.update(shown)
            for f in sorted(files):
                print(f"    {f}")
    else:
        print(f"base ref {base} is not resolvable in this checkout; commit list skipped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
