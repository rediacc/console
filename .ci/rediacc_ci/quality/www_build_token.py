"""Every www build in CI must pass GITHUB_TOKEN. All of them, not most of them.

Ported from `.ci/scripts/quality/check-www-build-token.sh`, retired in W7 P5;
see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

THE DEFECT, twice. `packages/www/src/pages/[lang]/downloads.astro` fetches the latest release from the GitHub API at BUILD time and deliberately THROWS rather than shipping a downloads page with nothing on it. Unauthenticated, that call is capped at 60/hour per runner IP -- which is SHARED -- so the build dies with

    latest-release: GitHub responded 403 rate limit exceeded

for reasons that have nothing to do with the commit under test.
`packages/www/src/utils/latest-release.ts:20-22` already sends the token as a Bearer header the moment it is set, and downloads.astro:35 prints "Set GITHUB_TOKEN if this is rate limiting" in the very error that fails the build. The fix is one line of `env:`.

WHY A GATE AND NOT A THIRD CAREFUL COMMENT. It was found and fixed twice, at ci-quality.yml and cd-deploy-worker.yml, each time with a thorough comment naming run 32223128728 -- and the THIRD call site, ci-build-docker.yml, was left behind both times and reddened job 99839065246 months later. Two prose comments did not find the third site. A rule that enumerates them does.

THE GENERAL SHAPE, and this repo hit it twice in one day: a fix applied at two of three call sites is a fix with a live hole. The nfpm checksum was the same story that morning (ci.yml verified before extracting; two siblings piped straight into tar).

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN CARRIES A DEAD FILTER, AND THE PORT CARRIES IT TOO. `find_sites` pipes its `grep -rnE` through `grep -v '^\\s*#'` and then through `grep -vE ':[0-9]+: *#'`. The first of those can never match anything: every line `grep -n` produces begins with the FILE PATH, so a `^\\s*#` test is asking whether a filename starts with a hash. Only the second filter does the job both were
written for -- dropping a call site that is inside a YAML comment. The dead one is reproduced here, as a predicate applied to the same composed `path:line:text` string, rather than dropped, for two reasons. It is a difference in behaviour nowhere and a difference in RECORD everywhere: deleting it would make the next reader believe the gate never tried to filter commented lines
twice. And a port whose first act is to remove a line it judged useless is a port whose verdict nobody can check against the original. It is reported as a finding instead of silently repaired.

THE MISSING LINES ARE NOT MARKED, AND THAT MATTERS TO THE COMPARATOR. The twin prints its findings as ` MISSING <file>:<line> builds www without GITHUB_TOKEN`
with no severity glyph, so `scripts/lib/shadow-gate.ts` classifies them as chatter
and a differential over this gate reports VACUOUS_BOTH_EMPTY -- both sides exit 1
with zero RECOGNISED findings. That is the comparator behaving correctly and
saying so: its VACUOUS message names both causes, "plant one" and "the finding extractor does not recognise this gate's output (pass --finding-re)". The differential for this pair therefore runs with `--finding-re '^ *MISSING '`. The text is kept byte-identical to the twin's precisely so that ONE `--finding-re` serves both sides.

THE FLOOR IS THE INTERESTING PART OF THIS GATE. Three call sites exist today, and finding none means the spellings moved -- at which point a green asserts nothing, which is the exact failure the gate is written against. The floor is carried at the same value with the same message. It is a hand-typed count and contract section 6 says a floor should be set-based or corpus-derived;
that is a real finding about this gate, and it is NOT fixed here, because changing the floor changes the verdict and a port that changes the verdict is not a port.
"""

import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The spellings a www build wears. Kept as a list because a fourth spelling is how a fourth call site would arrive unnoticed. Compiled once; the twin re-passes the same alternation to grep on every call.
#
# AND A FOURTH SPELLING IS EXACTLY WHAT ARRIVED, which is the second time this gate has been taught the same lesson. `c5cb6e8a6` ("80 workflow call sites run licensed Python ports instead of bash") repointed ci-build-docker.yml:123 from
#
#     - run: .ci/scripts/build/build-www.sh
#     + run: PYTHONPATH=.ci python3 -m rediacc_ci.build.build_www
#
# and `.ci/scripts/build/build-www.sh` was then deleted outright by the W7 P6 retirement. The third call site did not go away; its NAME did. From that commit until this one the gate scanned two sites, called them all of them, and would have waved through a dropped token on the very site whose comment block still says it was "THE THIRD CALL SITE, and it was the one left behind".
#
# THE FLOOR IS WHAT CAUGHT IT, and nothing else could have. Both surviving sites carry their token, so every other assertion in this gate was green. Only `total < MIN_SITES` had anything to say. This is the whole argument for a floor, written down as an observed event rather than as a principle.
#
# `build-www.sh` is retained in the alternation although the file is deleted. A dead alternative cannot produce a false positive here -- no workflow invokes a script that does not exist -- and if the path is ever restored the gate sees it on the first run rather than after the next floor breach.
SITE_RE = re.compile(
    r"build-www\.sh"
    r"|npm run build:www"
    r"|npm run build -w @rediacc/www"
    # Both spellings of the Python port: `-m rediacc_ci.build.build_www` as the workflow runs it today, and the direct `.../build_www.py` path that `.ci/scripts/ci/generate-tag.sh:217` names and a workflow could adopt.
    r"|rediacc_ci\.build\.build_www"
    r"|rediacc_ci/build/build_www\.py"
)

# The two filters, both carried. See the module docstring for why the first one cannot match and is kept anyway.
DEAD_COMMENT_FILTER = re.compile(r"^\s*#")
COMMENTED_SITE_FILTER = re.compile(r":[0-9]+: *#")

# A call site is covered when GITHUB_TOKEN appears in the 25 lines after it -- the env block belongs to that step, and no step in this repo is longer than that between `run:` and the end of its `env:`.
#
# COVER_MARKER, not COVER_MARKER: ruff's S105 reads any constant whose NAME contains "token" as a hardcoded credential. This one is a YAML key the gate
# greps for, and the repo's lint gate refuses a per-line noqa on principle, so
# the name moves rather than the rule.
COVER_WINDOW = 25
COVER_MARKER = "GITHUB_TOKEN:"

# FLOOR. Three call sites exist today. See the module docstring: this is a hand-typed count, which contract section 6 rules against, and it is carried unchanged because changing it would change the verdict.
MIN_SITES = 3

DEFAULT_WORKFLOWS = ".github/workflows"


def find_sites(directory: pathlib.Path) -> list[tuple[pathlib.Path, int, str]]:
    """Every www build invocation under `directory`, as (file, 1-based line, text).

    ONLY `*.yml`, matching the twin's `"$1"/*.yml` glob exactly. That glob is not recursive and does not match `.yaml`; both facts are behaviour, and a port that quietly widened either would report call sites the twin never saw and read as a regression in the workflows rather than in the gate.

    Files are visited in sorted order so two runs over one directory produce the
    findings in the same order. The shell's glob is already sorted under LC_ALL=C,
    which `scripts/lib/shadow-gate.ts` pins for exactly this reason.
    """
    out: list[tuple[pathlib.Path, int, str]] = []
    for path in sorted(directory.glob("*.yml")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # grep skips what it cannot read and says so on stderr; it does not abort the scan. Matching that is deliberate -- one unreadable file must not turn a coverage report into no report at all.
            continue
        for index, line in enumerate(text.split("\n"), start=1):
            if not SITE_RE.search(line):
                continue
            composed = "%s:%d:%s" % (path, index, line)
            if DEAD_COMMENT_FILTER.match(composed):
                continue
            if COMMENTED_SITE_FILTER.search(composed):
                continue
            out.append((path, index, line))
    return out


def covered(path: pathlib.Path, line: int) -> bool:
    """Does a GITHUB_TOKEN appear in this step's env block?

    `sed -n "L,L+25p"` is INCLUSIVE at both ends, so the window is 26 lines starting at the call site itself. Off by one here would make the gate disagree with its twin about a step whose `env:` sits exactly 25 lines down, which is the only place the two could ever differ, so the arithmetic is spelled out rather than left to a slice that reads naturally.
    """
    text = path.read_text(encoding="utf-8", errors="replace").split("\n")
    window = text[line - 1 : line + COVER_WINDOW]
    return any(COVER_MARKER in candidate for candidate in window)


def audit(directory: pathlib.Path) -> tuple[list[str], int, int]:
    """(missing lines, total call sites, uncovered count).

    The twin returns this as TEXT with a `__TOTAL__=n __BAD__=n` trailer parsed
    back out by parameter expansion, and its comment says why the parsing is not done with sed: `check:ci-control-vacuity` classifies any inline substitution as a control built by mutation and then demands proof the plant landed. That whole dance exists because bash has one return channel. A tuple has three, so the trailer, the parsing and the reason for avoiding sed all disappear
    together -- which is why this note exists, since the constraint that shaped the original is invisible in the result.
    """
    missing: list[str] = []
    total = 0
    for path, line, _text in find_sites(directory):
        total += 1
        if not covered(path, line):
            missing.append("  MISSING  %s:%d builds www without GITHUB_TOKEN" % (path, line))
    return missing, total, len(missing)


def run_controls() -> int:
    """CONTROL, before the real run. A gate that cannot fire is worse than no gate.

    Returns 0 when the controls hold, 1 when they do not. Built by CONSTRUCTION in a tempdir: two one-step workflows differing ONLY in the property under test.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workflows = pathlib.Path(tmp) / "wf"
        workflows.mkdir()
        bad = workflows / "bad.yml"
        good = workflows / "good.yml"
        bad.write_text(
            "jobs:\n  a:\n    steps:\n      - run: npm run build:www\n"
            "        env:\n          APP_VERSION: x\n",
            encoding="utf-8",
        )
        good.write_text(
            "jobs:\n  b:\n    steps:\n      - run: npm run build:www\n"
            "        env:\n          GITHUB_TOKEN: t\n",
            encoding="utf-8",
        )

        # THE FIXTURES MUST ACTUALLY DIFFER in the property under test. Without this the control is satisfied by two identical files, or by a write that silently did not land -- and a no-op plant looks exactly like a passing control. check:ci-control-vacuity exists because that has happened here before.
        if COVER_MARKER not in good.read_text(encoding="utf-8"):
            print(
                "CONTROL COULD NOT PLANT: good.yml has no token, so the pair proves nothing",
                file=sys.stderr,
            )
            return 1
        if COVER_MARKER in bad.read_text(encoding="utf-8"):
            print(
                "CONTROL COULD NOT PLANT: bad.yml HAS a token, so the pair proves nothing",
                file=sys.stderr,
            )
            return 1

        missing, _total, _bad = audit(workflows)
        joined = "\n".join(missing)
        if "bad.yml:4 builds www without GITHUB_TOKEN" not in joined:
            print(
                "CONTROL DID NOT FIRE: a call site with no token was not reported",
                file=sys.stderr,
            )
            return 1
        if "good.yml" in joined:
            print("CONTROL OVER-FIRED: a call site WITH the token was reported", file=sys.stderr)
            return 1

    print("\u2713 controls: an untokened call site is reported, a tokened one is not")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gate. `argv[0]` is the workflow directory, as in the twin."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    # The twin `cd`s to the repo root and then treats `$1` as given, so a relative argument is root-relative and an absolute one is itself. `/` in pathlib does exactly that, which is the one place the two agree by coincidence rather than by design, so it is written down.
    workflows = root / (args[0] if args else DEFAULT_WORKFLOWS)

    if run_controls() != 0:
        return 1

    missing, total, bad = audit(workflows)

    if total < MIN_SITES:
        print(
            "\u2717 found only %d www build call site(s); expected at least %d."
            % (total, MIN_SITES),
            file=sys.stderr,
        )
        print(
            "  The invocation spelling changed, or the scan is broken. Either way this",
            file=sys.stderr,
        )
        print("  green would assert nothing. Update find_sites().", file=sys.stderr)
        # THE SPELLINGS, PRINTED. This has fired once for real, when c5cb6e8a6 renamed the third site from `build-www.sh` to the Python port, and the count alone sent the reader into `git log -S` archaeology. Listing what was searched for turns that into a diff against `grep -rn` on the workflow directory.
        print(file=sys.stderr)
        print("  Searched %s/*.yml for any of:" % workflows, file=sys.stderr)
        for spelling in SITE_RE.pattern.split("|"):
            print("    %s" % spelling, file=sys.stderr)
        return 1

    if bad > 0:
        for line in missing:
            print(line, file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  downloads.astro fetches the latest release at build time and THROWS on a 403.",
            file=sys.stderr,
        )
        print("  Add to that step's env:  GITHUB_TOKEN: ${{ github.token }}", file=sys.stderr)
        return 1

    print("\u2713 all %d www build call site(s) pass GITHUB_TOKEN" % total)
    return 0


def selftest() -> int:
    """Plant a defect the gate must fire on, and its mirror it must stay quiet for.

    The gate's own inline controls already prove one direction against a constructed pair. This proves the DECISION function on top of them -- the floor, the uncovered branch, the window edge -- which the inline controls never reach because they only ever call `audit`.
    """
    ctl = Controls("www-build-token", floor=12, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def workflow(name: str) -> pathlib.Path:
            directory = base / name
            directory.mkdir(exist_ok=True)
            return directory

        def write(directory: pathlib.Path, name: str, body: str) -> None:
            (directory / name).write_text(body, encoding="utf-8")

        step = "jobs:\n  a:\n    steps:\n      - run: npm run build:www\n        env:\n%s"
        with_token = step % "          GITHUB_TOKEN: t\n"
        without = step % "          APP_VERSION: x\n"

        # Three covered sites: the floor is met and nothing is missing.
        clean = workflow("clean")
        for name in ("a.yml", "b.yml", "c.yml"):
            write(clean, name, with_token)
        missing, total, bad = audit(clean)
        ctl.check("CONTROL: three covered sites are found", total, 3)
        ctl.check("CONTROL: three covered sites report nothing missing", bad, 0)

        # THE PLANT: one of the three loses its token. Exactly the shape that shipped three times.
        planted = workflow("planted")
        write(planted, "a.yml", with_token)
        write(planted, "b.yml", without)
        write(planted, "c.yml", with_token)
        missing, total, bad = audit(planted)
        ctl.check("PLANT: the untokened site is the only finding", bad, 1)
        ctl.truthy("PLANT: the finding names b.yml", any("b.yml:4" in m for m in missing))

        # THE MIRROR the reviewer waves through: the gate must not fire when the
        # token is present. Proven above by bad == 0, and again here on the
        # WINDOW EDGE, which is where an off-by-one would show and nowhere else. The run line is line 4 and `sed -n "4,29p"` is INCLUSIVE at both ends, so line 29 is the last covered line. 23 filler lines put `env:` on 28 and the token on 29 -- exactly on the boundary. Written as arithmetic
        # from COVER_WINDOW rather than as the literal 23 so that changing the
        # window moves the fixture with it instead of silently un-testing the edge.
        edge = workflow("edge")
        filler = "\n".join("        # pad %d" % i for i in range(1, COVER_WINDOW - 1))
        write(
            edge,
            "a.yml",
            "jobs:\n  a:\n    steps:\n      - run: npm run build:www\n%s\n        env:\n          GITHUB_TOKEN: t\n"
            % filler,
        )
        write(edge, "b.yml", with_token)
        write(edge, "c.yml", with_token)
        _m, _t, bad = audit(edge)
        ctl.check("WINDOW: a token exactly at the last covered line still covers", bad, 0)

        # One line further out: the token now sits on line 30, one past the end of the window, and must NOT count. Edge and mirror differ by exactly one filler line, which is the only difference that proves the boundary.
        far = workflow("far")
        filler = "\n".join("        # pad %d" % i for i in range(1, COVER_WINDOW))
        write(
            far,
            "a.yml",
            "jobs:\n  a:\n    steps:\n      - run: npm run build:www\n%s\n        env:\n          GITHUB_TOKEN: t\n"
            % filler,
        )
        write(far, "b.yml", with_token)
        write(far, "c.yml", with_token)
        _m, _t, bad = audit(far)
        ctl.check("WINDOW MIRROR: a token beyond the window does not count", bad, 1)

        # A commented-out call site is not a call site. This is the filter that actually works; its dead sibling is documented in the module docstring.
        commented = workflow("commented")
        write(commented, "a.yml", "jobs:\n  a:\n    steps:\n      # - run: npm run build:www\n")
        _m, total, _b = audit(commented)
        ctl.check("FILTER: a commented call site is not counted", total, 0)

        # THE FLOOR. Two sites is below MIN_SITES, so the gate must refuse even though every site it did find is covered -- a green there would assert nothing about the third.
        short = workflow("short")
        write(short, "a.yml", with_token)
        write(short, "b.yml", with_token)
        ctl.check("FLOOR: two covered sites is a refusal", main([str(short)]), 1)
        ctl.check("FLOOR MIRROR: three covered sites is a pass", main([str(clean)]), 0)

        # EVERY LIVE SPELLING, BYTE FOR BYTE AS A WORKFLOW WRITES IT.
        # The gate went blind to the third call site for the whole life of `c5cb6e8a6` because the rename was invisible to a regex nobody re-read, and no selftest case here would have noticed: all nine of the cases above build their fixtures from `npm run build:www` alone, so the alternation was exercised on exactly one of its branches.
        # These pin the other branches to the real invocation text.
        spellings = workflow("spellings")
        live = (
            "npm run build:www",
            "npm run build -w @rediacc/www",
            "PYTHONPATH=.ci python3 -m rediacc_ci.build.build_www",
            "python3 .ci/rediacc_ci/build/build_www.py",
        )
        for index, invocation in enumerate(live):
            write(
                spellings,
                "s%d.yml" % index,
                "jobs:\n  a:\n    steps:\n      - run: %s\n        env:\n          GITHUB_TOKEN: t\n"
                % invocation,
            )
        _m, total, bad = audit(spellings)
        ctl.check("SPELLINGS: every live invocation text is seen as a call site", total, len(live))
        ctl.check("SPELLINGS: each of them counts as covered", bad, 0)

        # THE MIRROR. A regex loose enough to match any `python3 -m` line would make the count above pass while asserting nothing, so a neighbouring module and a neighbouring npm script must both stay invisible.
        decoys = workflow("decoys")
        write(
            decoys,
            "d.yml",
            "jobs:\n  a:\n    steps:\n"
            "      - run: PYTHONPATH=.ci python3 -m rediacc_ci.build.build_json\n"
            "      - run: npm run build:json\n"
            "      - run: npm run build -w @rediacc/cli\n",
        )
        _m, total, _b = audit(decoys)
        ctl.check("SPELLINGS MIRROR: a sibling build is not a www build", total, 0)

    return 0 if ctl.report() else 1
