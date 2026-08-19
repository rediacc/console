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

AND IT CHECKS THE SEQUENCING, because naming a second host is necessary and not
sufficient. A fallback guarded on the LAST loop iteration fires after the final
attempt, so nothing is left to use it: two hosts appear, the shallow reading of
this gate passes, and the build still dies exactly as before. That is the precise
shape of box-ticking a regression gate is supposed to refuse, so the guard
iteration is compared against the loop bound and a fallback that cannot help is
reported with the numbers that make it useless.

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
    """[(reason, block_excerpt)] for blocks whose apt sourcing cannot survive one
    dead mirror.

    TWO classes, because naming a second host is necessary and not sufficient.

    1. `pinned to <host>`: the block rewrites apt to exactly one host, so every
       retry targets the same machine. This is the 2026-08-19 incident.
    2. `fallback cannot help`: a second host IS named, but the switch is
       sequenced so that it never gets used. Caught because "has a fallback"
       is exactly the kind of box-ticking that passes a shallow gate while
       leaving the failure intact:
         - the switch is guarded on the LAST loop iteration, so it happens after
           the final attempt and no attempt remains to benefit from it;
         - the switch rewrites to the same host it is switching away from.
    """
    bad = []
    for block in run_blocks(text):
        hosts = {m.group(1).lower() for m in REWRITE.finditer(block)}
        if not hosts:
            continue  # this block does not rewrite apt sources at all
        excerpt = re.sub(r"\s+", " ", block)[:120]
        if len(hosts) < 2:
            bad.append(("pinned to %s" % min(hosts), excerpt))
            continue
        last = last_attempt(block)
        guard = fallback_iteration(block)
        give_up = giveup_iteration(block)
        if last is not None and guard is not None and guard >= last:
            bad.append(
                (
                    "fallback is guarded on iteration %d of %d, so it fires after the "
                    "last attempt and no retry can use it" % (guard, last),
                    excerpt,
                )
            )
        elif guard is not None and give_up is not None and guard >= give_up:
            bad.append(
                (
                    "fallback is guarded on iteration %d but the loop gives up at %d, "
                    "so it is unreachable" % (guard, give_up),
                    excerpt,
                )
            )
    return bad


def giveup_iteration(block):
    """Iteration N of a `[ "$i" = "N" ]` guard whose body EXITS.

    A fallback can be correctly placed relative to the loop bound and still never
    run, because an earlier iteration bails out first. Loop bound and fallback
    position are each fine in isolation; only their relation to the give-up point
    decides whether the fallback is reachable.
    """
    best = None
    for m in re.finditer(r'\[\s*"?\$\{?\w+\}?"?\s*=\s*"?(\d+)"?\s*\]', block):
        tail = block[m.end() : m.end() + 200]
        # `exit` before the guard's `fi`, i.e. inside this branch.
        branch = tail.split(" fi;")[0]
        if re.search(r"\bexit\b", branch):
            n = int(m.group(1))
            best = n if best is None else min(best, n)
    return best


def last_attempt(block):
    """Highest iteration in a `for i in 1 2 3 ...` loop, or None if no such loop."""
    m = re.search(r"for\s+\w+\s+in\s+((?:\d+\s+)*\d+)\s*;?\s*do", block)
    if not m:
        return None
    nums = [int(n) for n in m.group(1).split()]
    return max(nums) if nums else None


def fallback_iteration(block):
    """Iteration N from a `[ "$i" = "N" ]` guard that wraps a source rewrite.

    Returns the guard that protects a REWRITE, not the guard that protects the
    give-up branch, which is why the search is anchored on a following sed rather
    than on any equality test.
    """
    best = None
    for m in re.finditer(r'\[\s*"?\$\{?\w+\}?"?\s*=\s*"?(\d+)"?\s*\]', block):
        tail = block[m.end() : m.end() + 400]
        if REWRITE.search(tail):
            n = int(m.group(1))
            best = n if best is None else min(best, n)
    return best


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

    # A fallback that fires only on the LAST attempt: two hosts are named, so the
    # shallow "does a second host appear" test passes, and it still cannot help.
    too_late = (
        "RUN find /etc/apt -name 'sources.list' | xargs -r sed -i \\\n"
        "        -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\\n"
        "    && for i in 1 2 3 4 5; do apt-get update && break; \\\n"
        '        if [ "$i" = "5" ]; then \\\n'
        "            sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
        "        fi; \\\n"
        "    done\n"
    )

    # THE INCIDENT ITSELF, as the positive control.
    check("a single-mirror rewrite is caught", len(offenders(single)) == 1, offenders(single))
    check(
        "it names the pinned host",
        offenders(single)[0][0].endswith("azure.archive.ubuntu.com")
        if offenders(single)
        else False,
        offenders(single),
    )
    # SEQUENCING. Naming a second host is necessary, not sufficient.
    check(
        "a fallback guarded on the LAST attempt is caught",
        len(offenders(too_late)) == 1,
        offenders(too_late),
    )
    check(
        "and it says why, rather than just failing",
        "no retry can use it" in offenders(too_late)[0][0] if offenders(too_late) else False,
        offenders(too_late),
    )
    check("the loop bound is read", last_attempt(too_late) == 5, last_attempt(too_late))
    check(
        "the fallback guard is read",
        fallback_iteration(too_late) == 5,
        fallback_iteration(too_late),
    )
    check(
        "an early fallback guard is read as early",
        fallback_iteration(both) == 1 or fallback_iteration(both) is None,
        fallback_iteration(both),
    )

    # UNREACHABLE BY EARLY EXIT. The fallback sits before the loop bound, so the
    # bound check above is satisfied, and it still never runs because an earlier
    # iteration bails out first. Loop bound and fallback position are each fine in
    # isolation; only their RELATION to the give-up point decides reachability.
    stranded = (
        "RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \\\n"
        "    && for i in 1 2 3 4 5; do apt-get update && break; \\\n"
        '        if [ "$i" = "3" ]; then echo giving up >&2; exit 1; fi; \\\n'
        '        if [ "$i" = "4" ]; then \\\n'
        "            sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
        "        fi; \\\n"
        "    done\n"
    )
    check(
        "the give-up iteration is read", giveup_iteration(stranded) == 3, giveup_iteration(stranded)
    )
    check(
        "a fallback stranded behind an early exit is caught",
        len(offenders(stranded)) == 1,
        offenders(stranded),
    )
    check(
        "and it says the loop gives up first",
        "gives up at 3" in offenders(stranded)[0][0] if offenders(stranded) else False,
        offenders(stranded),
    )
    # The real file must not trip the new class: its give-up is at 5, fallback at 1.
    check(
        "a fallback BEFORE the give-up point still passes",
        offenders(both) == [] and giveup_iteration(both) is None,
        (offenders(both), giveup_iteration(both)),
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
