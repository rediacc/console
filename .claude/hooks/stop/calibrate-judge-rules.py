#!/usr/bin/env python3
"""Live calibration for the two judged stop rules. NOT a gate; opt-in, costs money.

WHY IT IS SEPARATE FROM test-judge-schema.py. Those controls pin the SEAM: given
a judge answer, does the machinery fire, stay silent, and produce an actionable
order? They run offline and they are wired into `npm run ci`. They cannot answer
the other half of the question -- does haiku, reading a real session message,
actually recognise "I fixed block-x.sh" as one instance of a class? That needs
the model, a network, and about two cents a case, which is exactly what a CI
gate must not need.

So this exists, and it is run BY HAND when the rubric changes:

    python3 .claude/hooks/stop/calibrate-judge-rules.py --live

Each fixture is a real defect from this repo's own history (the five the
operator supplied for the class-sweep rule, and the four measured timid
defaults), paired with the answer the rule must give. A fixture that flips is
the rubric drifting, and the fix is the PROMPT, not the fixture.

WHAT A FAILURE HERE MEANS, and it is not the same as a red gate: an over-firing
rule is a rule that gets skimmed, so a SILENT fixture that fires is at least as
serious as a FIRE fixture that stays quiet.
"""

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_bravedefault as BD
import wl_classsweep as CS
import wl_judge
import wl_shapedup as SD
import worklist_messages as M

# -- the class-sweep corpus --------------------------------------------------
# (label, expected, fix-set commit subjects, the session's final message)
SWEEP_CASES = [
    (
        "guard matched a mention, not a target",
        "fire",
        ["fix(hooks): block-bash-write-to-running-script matched a mention, not a target"],
        (
            "Fixed block-bash-write-to-running-script.sh: it grepped for the script name "
            "anywhere on the command line, so a command that merely MENTIONED the script "
            "was blocked. It now anchors the name to the redirect target. Verified by "
            "running the guard against both shapes."
        ),
    ),
    (
        "GOPATH assumption in one CI script",
        "fire",
        ["fix(ci): format.sh died at exit 127 because go install writes to GOPATH/bin"],
        (
            "private/renet/.ci/scripts/quality/format.sh exited 127: it ran gofumpt straight "
            "after `go install`, which puts the binary in $(go env GOPATH)/bin, not on PATH. "
            "Added the PATH export at the top of format.sh. The script now runs green."
        ),
    ),
    (
        "one row of a routing table",
        "fire",
        ["fix(gates): the check:ci-actionlint routing entry pointed at the wrong runner"],
        (
            "The routing table sent check:ci-actionlint to the shell runner instead of the "
            "workflow runner, so it never ran. Corrected that entry and confirmed the gate "
            "now executes."
        ),
    ),
    (
        "two test cases hardcoded one machine's path",
        "fire",
        ["fix(tests): two agent-browser cases hardcoded /home/muhammed paths"],
        (
            "Two agent-browser cases failed on this machine because they hardcoded "
            "/home/muhammed/monorepo. Replaced both with $REPO_ROOT. Both cases pass now."
        ),
    ),
    (
        "guard false positive on one of its paths",
        "fire",
        ["fix(hooks): the write-guard false-fired on a python heredoc"],
        (
            "The guard treated a python heredoc containing the script's name as a write to "
            "it. Fixed the heredoc path so the name is only matched as a redirect target."
        ),
    ),
    (
        "CONTROL: a typo in one string",
        "silent",
        ["fix(cli): typo in the repo-not-found error message"],
        "The error message said 'reposiotry'. Fixed the spelling in that one string.",
    ),
    (
        "CONTROL: the class was swept, with a count",
        "silent",
        ["fix(ci): four quality scripts assumed go install lands on PATH"],
        (
            "format.sh exited 127 because `go install` writes to $(go env GOPATH)/bin. "
            "I grepped the whole directory for the same shape -- `grep -rln 'go install' "
            "private/renet/.ci/scripts/` -- and found FOUR scripts with it: format.sh, "
            "lint.sh, deadcode.sh and run-tests.sh. All four fixed and all four run green."
        ),
    ),
    (
        "CONTROL: searched, and it is the only instance",
        "silent",
        ["fix(hooks): the roundlog guard matched a mention, not a target"],
        (
            "Fixed block-roundlog-truncate.sh. I then grepped every guard under "
            "`.claude/hooks/pre-bash/` for the same unanchored-name pattern "
            "(`grep -rn 'basename' .claude/hooks/pre-bash/`) -- 38 guards, and this is the "
            "only other one; the rest already anchor on the redirect target."
        ),
    ),
]

# -- the brave-default corpus ------------------------------------------------
# (label, expected, the remaining line as the judge sees it)
BRAVE_CASES = [
    (
        "MEASURED: keep carrying it",
        "fire",
        (
            "[?] - [?] (9d92) should the sweep rule ride this PR or its own branch? "
            "DEFAULT: keep carrying it."
        ),
    ),
    (
        "MEASURED: leave it on its branch",
        "fire",
        (
            "[?] - [?] (9d92) land the hook change on main or leave it? "
            "DEFAULT: leave it on its branch."
        ),
    ),
    (
        "MEASURED: hold until CI green",
        "fire",
        "[?] - [?] (9d92) flip the gate on now or wait? DEFAULT: hold until CI green.",
    ),
    (
        "MEASURED: hold and report the numbers",
        "fire",
        (
            "[?] - [?] (84f1) publish the regenerated teasers and locales when the pass "
            "finishes, or hold? Yours; DEFAULT: hold and report the numbers."
        ),
    ),
    (
        "CONTROL: a default that acts",
        "silent",
        (
            "[?] - [?] (9d92) which branch for the sweep rule? "
            "DEFAULT: land it on the open PR with the rest of the hook work."
        ),
    ),
    (
        "CONTROL: a hold justified by irreversibility",
        "silent",
        (
            "[?] - [?] (9d92) cut the v0.9.0 release from this green run? "
            "DEFAULT: do not release -- a published release cannot be withdrawn and only "
            "you can authorise one."
        ),
    ),
]


def sweep_extra(fixset):
    return M.REGGATE_PROMPT % {
        "fixset": "\n".join("  commit: " + s for s in fixset),
        "keys": "  check:ci-python-lint\n  check:ci-shell-lint\n  check:ci-hook-integrity",
    }


# The third rule's fixtures. Unlike the two above, this rule's TRIGGER is mechanical, so a
# fixture supplies the instances a counter would have measured and asks only the judged
# half: should these become one thing, and if not, what is the DIVERGENCE?
#
# THE NEGATIVE CASES ARE THE POINT. Every one of them is a real measurement from this repo:
# `run_gate()` genuinely is duplicated 23 times across three incompatible return contracts,
# and the findings-report block genuinely is ten distinct shapes across ten gates. A rubric
# that answers "yes, consolidate" to those is worse than no rubric, because it would push a
# session to delete exactly the lines that make a green mean something.
SHAPE_CASES = [
    (
        "the assertion closure, 12 files, 8 byte-identical",
        "fire",
        [
            "scripts/check-anchor-integrity.ts:235",
            "scripts/check-hydration-clean.ts:200",
            "scripts/check-layout-overflow.ts:267",
        ],
    ),
    (
        "28 hand-rolled mktemp+trap against an existing with_temp_dir",
        "fire",
        # COORDINATES CORRECTED 2026-09-02, and this is the THIRD fixture in this file
        # built from a survey table without opening the files. Two of the three pointed at
        # code that is not the shape they name: :44 in embed-asset-freshness is a heredoc
        # writing a JSON fixture (the real mktemp+trap is :29 and :32), and :21 in
        # ci-workflow-invariants is the `source test-helpers.sh` preamble (real pair at
        # :28-:29). Only the autopilot one was right.
        #
        # THE COST WAS MEASURABLE AND IT LOOKED LIKE SOMETHING ELSE. `wl_shapedup.prompt_
        # section` sends ONLY file:line, never the code, so the model had to open exactly
        # those lines -- and what it found was a heredoc, an import preamble and a trap,
        # which are genuinely NOT one shape. It answered `silent`, correctly, on the input
        # it was given. Across live runs the fixture then flip-flopped (MISS, OK, MISS),
        # and that noise was nearly diagnosed as rubric drift and "fixed" by rewriting
        # SHAPE_PROMPT -- which would have tuned the rubric to agree with wrong
        # coordinates. Worse, an import preamble is what the sibling gate's own control
        # calls "adoption, not duplication", so one coordinate was pointing at a span that
        # is legitimately shared.
        #
        # The rule above still stands -- when a fixture flips, the fix is the PROMPT --
        # but it assumes the fixture describes real code. VERIFY THE COORDINATES FIRST;
        # that check is one `sed -n` per line and it is the cheapest step here.
        [
            ".ci/scripts/test/gates/test-embed-asset-freshness.sh:29",
            ".ci/scripts/test/gates/test-ci-workflow-invariants.sh:28",
            ".ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh:29",
        ],
    ),
    # A THIRD FIRE FIXTURE WAS REMOVED RATHER THAN GUESSED AGAIN. It cited
    # check-em-dash-surfaces.ts:629 / check-dead-css.ts:181 / check-landmarks.ts:48 as one
    # "selftest verdict tail" cluster. Checked line by line, they are not one shape: :629
    # is a `main()` argv preamble, a different cluster entirely. The model answered
    # `already`, naming the real harness, with the divergence "em-dash-surfaces uses a
    # failures array, not a counter; belongs to a different cluster" -- correct, and the
    # fixture was wrong.
    #
    # That was the SECOND fixture here transcribed from a survey table without checking the
    # lines. Rather than transcribe a third, it is gone: two verified fire cases and three
    # verified controls are a calibration set, and a fixture built on unverified
    # coordinates is worse than no fixture, because it teaches the rubric to agree with a
    # mistake. Build any replacement from the counter's own output -- which is how the
    # line-numbering bug in 5607b136d was found.
    (
        "CONTROL: run_gate has three incompatible return contracts",
        "silent",
        [
            ".ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh:36",
            ".ci/scripts/test/gates/test-ci-workflow-invariants.sh:33",
            ".ci/scripts/test/gates/test-embed-asset-freshness.sh:80",
        ],
    ),
    (
        # THE FIRST VERSION OF THIS FIXTURE WAS WRONG, and the model caught it. It cited
        # check-dead-css.ts:187 / check-ssr-locale.ts:62 / check-svg-theme-reach.ts:60 as
        # "the findings report"; those three lines are in fact a byte-identical `check`
        # closure, so `consolidatable: yes` was the CORRECT answer and want=silent was the
        # error. A negative fixture pointing at real duplication does not test the rubric,
        # it tests whether the rubric will agree with a mistake. These lines are the actual
        # bespoke report prose.
        "CONTROL: the findings report is ten distinct shapes, not one",
        "silent",
        [
            "scripts/check-dead-css.ts:353",
            "scripts/check-landmarks.ts:130",
            "scripts/check-ssr-locale.ts:121",
        ],
    ),
    (
        "CONTROL: a generated file and its fixtures are copies on purpose",
        "silent",
        [
            "packages/www/src/data/video-manifest.json:1",
            "scripts/data/shape-duplication-seed.json:1",
            "packages/cli/src/__tests__/fixtures/config.json:1",
        ],
    ),
]


def run_shape_case(expected, instances):
    """A FRESH stop per fixture, same reason as run_case: a banked demand would
    silence the next fixture and make this harness measure itself."""
    for h in ("sh-cal",):
        SD.demand_for(h).clear()
    out, err = SD.ask(instances)
    if out is None:
        return "ERROR", err, None
    kind, _payload = SD.read_verdict(out)
    got = "fire" if kind == "fire" else ("silent" if kind == "silent" else kind)
    return ("OK" if got == expected else "MISS"), got, out.get("shape_dup")


def run_case(expected, extra, message, remaining):
    # Each fixture is a FRESH stop. Without this, the demand a firing fixture
    # banks would carry into the next one -- the class-sweep follow-up section
    # would be appended to a brave-default fixture, and the cap would silence
    # the fourth timid default. Cross-contamination between fixtures would make
    # this harness measure itself rather than the rubric.
    CS.clear_outstanding()
    BD.BRAVE_DEMAND.clear()
    verdict, err = wl_judge.run_judge(
        remaining, 0, message, 0, "none declared", citations=None, extra=extra
    )
    if err:
        return "ERROR", err, None
    if extra:
        kind, _payload = CS.read_verdict(verdict)
        obj = verdict.get("class_sweep")
    else:
        kind, _payload = BD.read_verdict(verdict)
        obj = verdict.get("brave_default")
    got = "fire" if kind == "fire" else ("silent" if kind == "silent" else kind)
    return ("OK" if got == expected else "MISS"), got, obj


def main():
    if "--live" not in sys.argv:
        print(__doc__)
        print("Refusing to run: this calls the real model and costs money. Pass --live.")
        return 0
    # A scratch TMPDIR so a calibration run never touches the demand markers of
    # the live session running it.
    tmp = tempfile.TemporaryDirectory()
    os.environ["TMPDIR"] = tmp.name
    # `--only <substring>` re-runs just the fixtures that missed. A rubric
    # change is judged by the fixture it was made for, and paying for all
    # fourteen to see two is how a calibration loop stops being run.
    only = ""
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    fails = 0
    for label, expected, fixset, message in SWEEP_CASES:
        if only and only not in label:
            continue
        status, got, obj = run_case(expected, sweep_extra(fixset), message, [])
        fails += status != "OK"
        print(
            "%-5s %-9s want=%-7s got=%-9s  %s" % (status, "sweep", expected, got, label),
            flush=True,
        )
        if status != "OK" and isinstance(obj, dict):
            print("      %s" % json.dumps(obj)[:400])
    for label, expected, line in BRAVE_CASES:
        if only and only not in label:
            continue
        status, got, obj = run_case(expected, "", "Status report; nothing else open.", [line])
        fails += status != "OK"
        print(
            "%-5s %-9s want=%-7s got=%-9s  %s" % (status, "brave", expected, got, label),
            flush=True,
        )
        if status != "OK" and isinstance(obj, dict):
            print("      %s" % json.dumps(obj)[:400])
    for label, expected, instances in SHAPE_CASES:
        if only and only not in label:
            continue
        status, got, obj = run_shape_case(expected, instances)
        fails += status != "OK"
        print(
            "%-5s %-9s want=%-7s got=%-9s  %s" % (status, "shapedup", expected, got, label),
            flush=True,
        )
        if status != "OK" and isinstance(obj, dict):
            print("      %s" % json.dumps(obj)[:400])
    total = sum(
        1
        for label in [c[0] for c in SWEEP_CASES]
        + [c[0] for c in BRAVE_CASES]
        + [c[0] for c in SHAPE_CASES]
        if not only or only in label
    )
    print("\n%d/%d fixtures matched" % (total - fails, total))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
