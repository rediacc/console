#!/usr/bin/env python3
"""An apt source rewritten to ONE mirror must carry a fallback to another.

WHY THIS EXISTS, from a defect that took down four consecutive CI attempts on
2026-08-19. `.devcontainer/Dockerfile` rewrote every apt source to
`azure.archive.ubuntu.com`, on a documented assumption written into the file: that
mirror sits in the same data centers as the runners and "effectively never loses
connectivity from them". It lost connectivity for over ninety minutes. Because ALL
sources pointed at that one host, the surrounding five-attempt retry loop hammered
the same dead mirror five times and could not help.

The retry loop was not the bug and was working exactly as designed. Retrying a
single point of failure is still a single point of failure.

WHY NO EXISTING GATE CAUGHT IT, which is the whole reason this file exists rather
than a comment in the Dockerfile. Every check in this repo that looks at retry
logic counts ATTEMPTS. None asked whether the attempts could ever reach a
DIFFERENT source. A loop with five retries and one host passes every existing
notion of "has retries" while being strictly equivalent to no retries at all when
that host is down. The fix was applied by hand; nothing prevented its return, and
a revert or a newly added single-mirror block would have been invisible.

WHAT IT REQUIRES. If a Dockerfile RUN block rewrites apt sources to a specific
mirror host, that same block must name at least TWO distinct hosts, so a failure
of the first can fall through to the second. It does not mandate a particular
mirror, a particular retry count, or a particular shape of fallback; it only
refuses the shape that has already cost this repo a night.

WHAT IT DELIBERATELY DOES NOT DO. It does not police Dockerfiles that never
rewrite apt sources. The stock `archive.ubuntu.com` is already a load-balanced
pool of many machines, so a file that leaves sources alone is not carrying the
single-point-of-failure this gate is about.
"""

import pathlib
import re
import subprocess
import sys

# A sed that rewrites an apt source URL to a specific host. The captured group is
# the DESTINATION host, which is what has to vary for a fallback to exist.
REWRITE = re.compile(r"s\|https?://[^|]*?ubuntu[^|]*?\|https?://([a-z0-9.-]+)/", re.IGNORECASE)

# Anti-vacuity floor. This repo has at least one Dockerfile; a scan finding none
# means the glob broke, not that the tree is clean.
MIN_DOCKERFILES = 1


def tracked_dockerfiles(root):
    """Every tracked Dockerfile. Uses git so an untracked scratch file cannot
    change the verdict in either direction."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "*Dockerfile", "*Dockerfile.*", "*.dockerfile"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return [root / p for p in out.stdout.split("\n") if p.strip()]


def run_blocks(text):
    """Each RUN instruction as one logical line, backslash continuations joined.

    A fallback lives in the SAME block as the rewrite it protects, because that is
    the only place it can run between two attempts of the same loop.
    """
    joined = re.sub(r"\\\s*\n", " ", text)
    return [ln for ln in joined.split("\n") if ln.lstrip().startswith("RUN ")]


def offenders(text):
    """[(host, block_excerpt)] for blocks that pin apt to exactly ONE host."""
    bad = []
    for block in run_blocks(text):
        hosts = {m.group(1).lower() for m in REWRITE.finditer(block)}
        if not hosts:
            continue  # this block does not rewrite apt sources at all
        if len(hosts) < 2:
            bad.append((min(hosts), re.sub(r"\s+", " ", block)[:120]))
    return bad


def selftest():
    """Controls, both directions. A gate that cannot fail is worse than none."""
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        if not cond:
            ok = False
        print(
            "  %s  %s%s" % ("PASS" if cond else "FAIL", label, "" if cond else "  <- %s" % detail)
        )

    single = (
        "RUN find /etc/apt -name 'sources.list' | xargs -r sed -i \\\n"
        "        -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\\n"
        "    && for i in 1 2 3 4 5; do apt-get update && break; sleep 30; done\n"
    )
    both = (
        "RUN find /etc/apt -name 'sources.list' | xargs -r sed -i \\\n"
        "        -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\\n"
        "    && for i in 1 2 3 4 5; do apt-get update && break; \\\n"
        "        sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
        "    done\n"
    )
    none = "RUN apt-get update && apt-get install -y curl\n"

    # THE INCIDENT ITSELF, as the positive control.
    check("a single-mirror rewrite is caught", len(offenders(single)) == 1, offenders(single))
    check(
        "it names the pinned host",
        offenders(single)[0][0] == "azure.archive.ubuntu.com" if offenders(single) else False,
    )
    # The fixed shape must pass, or the gate blocks the very remedy it demands.
    check("a rewrite WITH a fallback passes", offenders(both) == [], offenders(both))
    # Not everything is its business.
    check("a block that never rewrites apt is ignored", offenders(none) == [])
    check("an empty file is ignored", offenders("") == [])
    # Continuation joining is load-bearing: the rewrite and its fallback are on
    # different physical lines, so a scanner that reads line-by-line sees only the
    # rewrite and reports a false positive on correct code.
    check(
        "continuations are joined, so a multi-line block reads as one",
        len(run_blocks(both)) == 1,
        run_blocks(both),
    )
    print("  %s" % ("all mirror-resilience controls passed" if ok else "*** FAILURES ***"))
    return ok


def main(argv):
    root = pathlib.Path(__file__).resolve().parents[3]
    if "--selftest" in argv:
        return 0 if selftest() else 1
    if not selftest():
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    files = tracked_dockerfiles(root)
    if len(files) < MIN_DOCKERFILES:
        print(
            "found %d tracked Dockerfile(s), floor %d. The scan is broken, not the tree: "
            "a gate that inspects nothing reports success forever." % (len(files), MIN_DOCKERFILES),
            file=sys.stderr,
        )
        return 1

    found = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for host, excerpt in offenders(text):
            found.append((f.relative_to(root), host, excerpt))

    if found:
        print("Dockerfile apt sources pinned to a SINGLE mirror with no fallback:", file=sys.stderr)
        for path, host, excerpt in found:
            print(
                "  - %s\n      pins every apt source to %s\n      %s" % (path, host, excerpt),
                file=sys.stderr,
            )
        print(
            "\n  Retrying one host five times is still one host. On 2026-08-19 exactly this\n"
            "  shape took down four consecutive CI attempts when azure.archive.ubuntu.com\n"
            "  refused connections for ninety minutes.\n"
            "  Fix: inside the same RUN block, fall back to a second host after the first\n"
            "  failure. See .devcontainer/Dockerfile for the shape that satisfies this.",
            file=sys.stderr,
        )
        return 1

    print(
        "%d Dockerfile(s) scanned; no apt source is pinned to a single mirror "
        "(controls fired in both directions)" % len(files)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
