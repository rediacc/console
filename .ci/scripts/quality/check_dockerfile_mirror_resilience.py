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

# Anti-vacuity floor. This repo has hundreds of tracked Dockerfiles and shell
# scripts; a scan finding none means the glob broke, not that the tree is clean.
MIN_SCANNED = 50


def tracked_files(root):
    """Every tracked Dockerfile AND shell script.

    SHELL SCRIPTS WERE ADDED THE HARD WAY, hours after the Dockerfile-only
    version shipped. The same single-mirror rewrite lived in
    `.ci/scripts/test/test-install-methods.sh`, which drives apt inside
    ubuntu:22.04 and ubuntu:24.04 containers, and it took down `Validate
    Promotion` in the very next CI run while this gate reported the tree clean.
    A gate scoped to the file where a defect was FOUND, rather than to the shape
    of the defect, sweeps the instance and misses the class.

    Uses git so an untracked scratch file cannot change the verdict either way.
    """
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "*Dockerfile",
                "*Dockerfile.*",
                "*.dockerfile",
                "*.sh",
            ],
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
    blocks = run_blocks(text)
    if not blocks and REWRITE.search(text):
        # A shell script, not a Dockerfile: there is no RUN instruction to scope
        # by, so the whole file is one scope. Coarser than the Dockerfile path on
        # purpose, and still decisive for the shape that matters: a file that
        # rewrites apt to exactly one host names one destination and nothing else.
        blocks = [re.sub(r"\\\s*\n", " ", text)]
    for block in blocks:
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
        elif guard is not None and last is None:
            # ANTI-VACUITY. Both sequencing checks above are guarded on having
            # parsed a number, so an edit that makes the loop unreadable would
            # skip them SILENTLY and the file would pass while nothing had been
            # verified. A conditional fallback whose loop cannot be parsed is
            # reported as unverifiable rather than waved through: this gate must
            # not be able to say "fine" when it means "I could not tell".
            bad.append(
                (
                    "fallback is guarded on iteration %d but the retry loop's bounds "
                    "cannot be parsed, so its reachability is unverifiable" % guard,
                    excerpt,
                )
            )
    return bad


# An iteration test against a literal, in the shapes shell actually uses.
#
# This started as `[ "$i" = "N" ]` only, and review caught the consequence: `[[ $i -eq N ]]`
# is a real idiom, used elsewhere in the very delta that added this gate, and a fallback
# guarded that way was INVISIBLE here. Both sequencing checks are conditioned on finding a
# guard, so not finding one meant reporting nothing, and the gate passed on exactly the
# defect it exists to catch. That is the vacuity class this file's own header warns about,
# so it is worth being explicit: `[` and `[[`, and `=`, `==` or `-eq`.
#
# Declared ONCE and shared by both readers below. They had identical copies, which is how
# a fix lands in one and not the other.
ITER_TEST = r'\[\[?\s*"?\$\{?\w+\}?"?\s*(?:==?|-eq)\s*"?(\d+)"?\s*\]\]?'


def giveup_iteration(block):
    """Iteration N of an iteration guard whose body EXITS.

    A fallback can be correctly placed relative to the loop bound and still never
    run, because an earlier iteration bails out first. Loop bound and fallback
    position are each fine in isolation; only their relation to the give-up point
    decides whether the fallback is reachable.
    """
    best = None
    for m in re.finditer(ITER_TEST, block):
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
    for m in re.finditer(ITER_TEST, block):
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
        # `% (detail,)`, NOT `% detail`. With a list or tuple detail the bare form treats
        # it as the argument LIST, so an empty list raises TypeError and a 2-element one
        # raises too. That turns a control FAILURE into a traceback, which is the worst
        # possible time to lose the message: found while mutation-testing this very file,
        # where a genuinely failing control crashed instead of printing what it wanted.
        print(
            "  %s  %s%s"
            % ("PASS" if cond else "FAIL", label, "" if cond else "  <- %r" % (detail,))
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

    # THE DOUBLE-BRACKET BLINDSPOT, found in review. The iteration test used to be
    # `[ "$i" = "N" ]` and NOTHING else, so a fallback guarded `[[ $i -eq N ]]` was
    # invisible: both sequencing checks are conditioned on finding a guard, so finding
    # none meant reporting none, and the gate passed on the very defect it exists to
    # catch. `[[ ... -eq ... ]]` is not hypothetical; it is already used elsewhere in the
    # delta that added this file. Each shape below is the SAME defect written a different
    # legal way, and every one must still be caught.
    for label, test in (
        ("[[ $i -eq N ]]", "[[ $i -eq 5 ]]"),
        ('[[ "$i" == "N" ]]', '[[ "$i" == "5" ]]'),
        ('[ "$i" -eq "N" ]', '[ "$i" -eq "5" ]'),
    ):
        variant = (
            "RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \\\n"
            "    && for i in 1 2 3 4 5; do apt-get update && break; \\\n"
            "        if %s; then \\\n"
            % test
            + "            sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
            "        fi; \\\n"
            "    done\n"
        )
        check(
            "a last-iteration fallback written %s is caught" % label,
            len(offenders(variant)) == 1 and "after the " in offenders(variant)[0][0],
            offenders(variant),
        )
    # CONTROL for the control: the same bracket shapes must NOT manufacture a finding
    # when the fallback is early, or the fix would just be "report more".
    early_dbl = (
        "RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \\\n"
        "    && for i in 1 2 3 4 5; do apt-get update && break; \\\n"
        "        if [[ $i -eq 1 ]]; then \\\n"
        "            sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
        "        fi; \\\n"
        "    done\n"
    )
    check(
        "an EARLY fallback written [[ -eq ]] still passes",
        offenders(early_dbl) == [] and fallback_iteration(early_dbl) == 1,
        (offenders(early_dbl), fallback_iteration(early_dbl)),
    )

    # ANTI-VACUITY. Both sequencing checks are guarded on having parsed a number,
    # so an unparseable loop would skip them silently and the file would pass
    # while NOTHING had been verified. That is the exact shape this repo calls a
    # gate that cannot fail, and it must be reported instead.
    unparseable = (
        "RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list \\\n"
        "    && while read -r attempt; do apt-get update && break; \\\n"
        '        if [ "$attempt" = "2" ]; then \\\n'
        "            sed -i -e 's|http://azure.archive.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \\\n"
        "        fi; \\\n"
        "    done < /tmp/attempts\n"
    )
    check("an unparseable loop yields no bound", last_attempt(unparseable) is None)
    check(
        "a guarded fallback with an unparseable loop is reported, not waved through",
        len(offenders(unparseable)) == 1,
        offenders(unparseable),
    )
    check(
        "and it says the reachability is unverifiable",
        "unverifiable" in offenders(unparseable)[0][0] if offenders(unparseable) else False,
        offenders(unparseable),
    )
    # A fallback applied EVERY iteration has no guard at all, so there is nothing
    # to sequence and nothing to be unverifiable about. It must stay legal.
    check(
        "an unconditional fallback needs no guard and still passes",
        fallback_iteration(both) is None and offenders(both) == [],
        (fallback_iteration(both), offenders(both)),
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

    files = tracked_files(root)
    if len(files) < MIN_SCANNED:
        print(
            "found %d tracked Dockerfile(s) and shell script(s), floor %d. The scan is broken, "
            "not the tree: "
            "a gate that inspects nothing reports success forever." % (len(files), MIN_SCANNED),
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
        "%d Dockerfile(s) and shell script(s) scanned; no apt source is pinned to a "
        "single mirror "
        "(controls fired in both directions)" % len(files)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
