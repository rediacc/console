#!/usr/bin/env python3
"""A network fetch in an image build must be able to survive one bad minute.

WHY, measured 2026-09-01. `Build (Docker) / Devcontainer (amd64)` died on:

    curl: (22) The requested URL returned error: 500
    https://go.dev/dl/go1.26.6.linux-amd64.tar.gz

go.dev was briefly unwell; probed minutes later the same URL answered 302. Nothing was
wrong with the image, the pin or the checksum -- a ten-minute multi-arch build that gates
every PR simply had no second attempt. Two apt steps in that file carried hand-rolled
five-attempt retry loops while EIGHT other fetches had none, so the asymmetry, not the
outage, was the defect.

Fixed by hand across nine call sites. This gate is what stops a tenth landing bare, which
is the whole i18n lesson: the thing was fixed and nothing prevented its return.

NOT COVERED BY check_dockerfile_mirror_resilience.py, and that is deliberate on both
sides. Its own docstring says it checks that apt is not pinned to a single mirror and
explicitly NOT "a particular retry count". Retrying a dead mirror is its problem; not
retrying a live one that hiccuped is this one's.

SCOPED TO THE SHAPE, NOT THE FILE. The sibling gate learned this the hard way -- shipped
Dockerfile-only, then the same defect took down CI from a shell script hours later. So
this reuses its `tracked_files()` (Dockerfiles AND shell scripts) and its `run_blocks()`
rather than re-deriving either.

WHAT COUNTS AS RETRIED is deliberately generous, because the goal is a second attempt, not
a particular spelling: curl's own `--retry`, wget's `--tries`, a shared ARG carrying them,
or an enclosing hand-rolled loop. Any of those is a pass.
"""

import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# REUSED, NOT REWRITTEN: `run_blocks` joins backslash continuations so a multi-line RUN
# reads as one logical line, and `tracked_files` already settled the corpus question
# (Dockerfiles AND shell scripts, via git so an untracked scratch file cannot change the
# verdict). Copying either would be a second thing to drift.
import check_dockerfile_mirror_resilience as MIRROR

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# Below this the scan is broken rather than the tree being clean.
MIN_FILES = 20

# A fetch INVOCATION: the command at the start of a segment, not the word anywhere.
# `ca-certificates curl \` in an apt package list is not a fetch, and that false positive
# is live in `.ci/docker/web/Dockerfile` -- a crude `grep -c curl` reports it as an
# unretried download.
# `RUN` counts as a command position: run_blocks keeps the instruction word, so the very
# first command in a block sits after "RUN " rather than at the start of the string. The
# first cut omitted it and its own SANITY control failed -- which is what a sanity control
# is for, since every negative control below passes against a matcher that matches nothing.
FETCH = re.compile(
    r"(?:^|RUN\s+|[|;&]|&&|\|\||\$\(|`|\bthen\s+|\bdo\s+)\s*(curl|wget)\s+(?=-|https?://)"
)

# Any of these means a second attempt exists.
RETRIED = re.compile(r"--retry\b|--tries\b|\bCURL_RETRY\b|\bWGET_RETRY\b|for i in 1 2 3")

# A fetch that cannot fail transiently over the network.
LOCAL = re.compile(r"https?://(127\.0\.0\.1|localhost|\[::1\])")


def offences_in(text):
    """[(block_excerpt, tool)] for every unretried network fetch in one file."""
    out = []
    for block in MIRROR.run_blocks(text):
        # A comment is not an invocation.
        stripped = re.sub(r"(?m)^\s*#.*$", "", block)
        if RETRIED.search(stripped):
            continue
        for m in FETCH.finditer(stripped):
            seg_start = stripped.rfind("&&", 0, m.start())
            seg = stripped[max(seg_start, 0) : m.start() + 200]
            if LOCAL.search(seg):
                continue
            out.append((" ".join(stripped.split())[:110], m.group(1)))
            break
    return out


def selftest():
    """Controls, both directions. A gate that cannot fail is worse than none."""
    ok = True

    def check(label, cond):
        nonlocal ok
        if cond:
            print("  PASS  %s" % label)
        else:
            ok = False
            print("  FAIL  %s" % label, file=sys.stderr)

    check(
        "SANITY: a bare curl download is an offence",
        len(offences_in("RUN curl -fsSL -o /tmp/x.tgz https://example.com/x.tgz")) == 1,
    )
    check(
        "CONTROL: the same fetch with --retry is fine",
        len(offences_in("RUN curl -fsSL --retry 5 -o /tmp/x.tgz https://example.com/x.tgz")) == 0,
    )
    check(
        "CONTROL: a shared ARG carrying the flags counts",
        len(offences_in("RUN curl -fsSL $CURL_RETRY -o /tmp/x.tgz https://example.com/x.tgz")) == 0,
    )
    check(
        "CONTROL: an enclosing hand-rolled retry loop counts",
        len(
            offences_in(
                "RUN for i in 1 2 3 4 5; do curl -fsSL https://example.com/x || sleep 1; done"
            )
        )
        == 0,
    )
    # THE FALSE POSITIVE THAT IS LIVE IN THE TREE: `.ci/docker/web/Dockerfile` lists curl
    # as an apt PACKAGE. A crude `grep -c curl` reports it as an unretried download.
    check(
        "CONTROL: curl as an apt package name is not a fetch",
        len(
            offences_in(
                "RUN apt-get install -y --no-install-recommends ca-certificates curl libnss3"
            )
        )
        == 0,
    )
    check(
        "CONTROL: a commented-out fetch is not an invocation",
        len(offences_in("RUN echo hi\n# curl -fsSL https://example.com/x.tgz")) == 0,
    )
    check(
        "CONTROL: a loopback fetch cannot fail over the network",
        len(offences_in("RUN curl -fsS http://127.0.0.1:8080/health")) == 0,
    )
    check(
        "wget is judged the same way, and --tries is its spelling",
        len(offences_in("RUN wget -q https://example.com/x.tgz")) == 1
        and len(offences_in("RUN wget -q --tries=5 https://example.com/x.tgz")) == 0,
    )
    check(
        "CONTROL: a piped installer still needs a retry",
        len(offences_in("RUN curl -fsSL https://example.com/install.sh | bash")) == 1,
    )
    check("CONTROL: a file with no fetch yields nothing", len(offences_in("RUN echo hi")) == 0)
    return ok


def main():
    if "--selftest" in sys.argv[1:]:
        return 0 if selftest() else 1
    if not selftest():
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    # tracked_files returns pathlib.Path objects and wants a Path root.
    files = MIRROR.tracked_files(pathlib.Path(ROOT))
    if len(files) < MIN_FILES:
        print(
            "scanned %d file(s), floor %d. The scan is broken, not the tree."
            % (len(files), MIN_FILES),
            file=sys.stderr,
        )
        return 1

    findings = []
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for excerpt, tool in offences_in(text):
            findings.append((path, tool, excerpt))

    if findings:
        print("\n%d network fetch(es) with no retry:\n" % len(findings), file=sys.stderr)
        for path, tool, excerpt in findings:
            print("  %s  (%s)" % (os.path.relpath(path, ROOT), tool), file=sys.stderr)
            print("    %s" % excerpt, file=sys.stderr)
        print(
            "\n  One bad minute upstream should not kill a ten-minute image build. Add\n"
            "  `--retry` (curl) or `--tries` (wget), or the shared ARG the devcontainer\n"
            "  Dockerfile uses. Measured: go.dev answered 500 once and took the whole\n"
            "  Devcontainer build with it; the same URL answered 302 minutes later.",
            file=sys.stderr,
        )
        return 1

    print(
        "fetch retry: %d file(s) scanned; every network fetch can survive one bad minute"
        % len(files)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
