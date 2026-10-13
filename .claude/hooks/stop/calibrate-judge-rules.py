#!/usr/bin/env python3
"""Live calibration for the two judged stop rules. NOT a gate; opt-in, costs money.

WHY IT IS SEPARATE FROM test-judge-schema.py. Those controls pin the SEAM: given a judge answer, does the machinery fire, stay silent, and produce an actionable order? They run offline and they are wired into `npm run ci`. They cannot answer the other half of the question -- does haiku, reading a real session message, actually recognise "I fixed block-x.sh" as one instance of a
class? That needs the model, a network, and about two cents a case, which is exactly what a CI gate must not need.

So this exists, and it is run BY HAND when the rubric changes:

    python3 .claude/hooks/stop/calibrate-judge-rules.py --live

Each fixture is a real defect from this repo's own history (the five the operator supplied for the class-sweep rule, and the four measured timid defaults), paired with the answer the rule must give. A fixture that flips is the rubric drifting, and the fix is the PROMPT, not the fixture.

HELD OUT FROM THE RUBRIC, since 2026-10-09 (review 18700a76.4). The rubrics teach by worked example, and those examples ARE the measured defects, so a fixture worded as its example is scored on whether the model can match a quoted sentence, not whether it applies the rule. The brave defaults and the typo control are therefore the same defects in different words, and `check:ci-rubric-calibration` refuses any fixture string that shares a five-word run with a calibrated rubric, so the next example added to a prompt cannot quietly become its own test.

ONE SAMPLE PER FIXTURE, ON PURPOSE. Production asks once: wl_judge.run_judge and wl_shapedup.ask each make a single call and retry only when no verdict arrived at all, never to vote. A majority over N samples here would score a rule production does not run, so a fixture that flips between runs is read as a boundary the rubric or the fixture leaves open, and the fix is to close it, not to average it away.

WHAT A FAILURE HERE MEANS, and it is not the same as a red gate: an over-firing rule is a rule that gets skimmed, so a SILENT fixture that fires is at least as serious as a FIRE fixture that stays quiet.
"""

import importlib.util
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_bravedefault as BD
import wl_classsweep as CS
import wl_judge
import wl_shapedup as SD
import worklist_messages as M

# -- the class-sweep corpus -------------------------------------------------- (label, expected, fix-set commit subjects, the files git shows the fix-set touched, the session's final message)
#
# THE FILE LIST IS PRODUCTION'S INPUT, and it was missing here until 2026-10-09. wl_checks hands run_judge `fixset_files` (git's own list, rendered as M.FIXSET_GROUND_TRUTH), and SWEEP_PROMPT anchors its search to "the ACTUAL FILES list ... or, when that list is empty, a change the message explicitly quotes". Without the list, a fire fixture whose message names a guard but quotes no line gave the model a rubric-sanctioned way out: five runs on 2026-10-09 scored "guard false positive on one of its paths" 3/5 and "guard matched a mention, not a target" 4/5, and each miss said the file list was empty and nothing could be anchored. Calibration has to judge the prompt production builds.
SWEEP_CASES = [
    (
        "guard matched a mention, not a target",
        "fire",
        ["fix(hooks): block-bash-write-to-running-script matched a mention, not a target"],
        [".claude/hooks/block-bash-write-to-running-script.sh"],
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
        ["private/renet/.ci/scripts/quality/format.sh"],
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
        ["scripts/ci-runner/gates.lock.json"],
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
        ["packages/e2e-tests/tests/agent-browser.test.ts"],
        (
            "Two agent-browser cases failed on this machine because they hardcoded "
            "/home/muhammed/monorepo. Replaced both with $REPO_ROOT. Both cases pass now."
        ),
    ),
    (
        "guard false positive on one of its paths",
        "fire",
        ["fix(hooks): the write-guard false-fired on a python heredoc"],
        [".claude/hooks/block-bash-write-to-running-script.sh"],
        (
            "The guard treated a python heredoc containing the script's name as a write to "
            "it. Fixed the heredoc path so the name is only matched as a redirect target."
        ),
    ),
    # ADDED 2026-10-09 for review 18700a76.1. SWEEP_PROMPT's two-paths example says a guard's siblings are its OTHER INPUT PATHS as well as the other guards, and until this fixture nothing asked the judge to apply the first half: every guard fixture either searched nothing or searched both. This one reports a real search across the other guards and none inside its own guard, so the redirect, tee and cp paths of the same script are left unexamined, and the rubric says that is not a sweep.
    (
        "guard: the other guards searched, its own other paths not",
        "fire",
        ["fix(hooks): the write-guard false-fired on a python heredoc"],
        [".claude/hooks/block-bash-write-to-running-script.sh"],
        (
            "The guard treated a python heredoc containing the script's name as a write to "
            "it. Fixed the heredoc branch so the name only counts as a write target there. "
            "Then grepped every other guard for the same unanchored-name idiom "
            "(`grep -rln 'basename' .claude/rediacc_hooks/guards/`): 51 searched, none had it."
        ),
    ),
    # HELD OUT FROM THE RUBRIC 2026-10-09 (review 18700a76.4's class). It used to be the operator's own worked example, which SWEEP_PROMPT quotes word for word ("The error message said 'reposiotry'..."), so the fixture could pass by matching the example rather than by applying the rule. It is now a different misspelling with the same mechanism-free shape, and check:ci-rubric-calibration refuses any fixture that shares a five-word run with a calibrated rubric.
    (
        "CONTROL: a typo in one string",
        "silent",
        ["fix(cli): typo in the machine usage line"],
        ["packages/cli/src/i18n/locales/en.json"],
        "The usage line for `rdc machine` read 'machien'. Corrected that one word.",
    ),
    (
        "CONTROL: the class was swept, with a count",
        "silent",
        ["fix(ci): four quality scripts assumed go install lands on PATH"],
        [
            "private/renet/.ci/scripts/quality/deadcode.sh",
            "private/renet/.ci/scripts/quality/format.sh",
            "private/renet/.ci/scripts/quality/lint.sh",
            "private/renet/.ci/scripts/quality/run-tests.sh",
        ],
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
        [".claude/rediacc_hooks/guards/block_roundlog_truncate.py"],
        (
            # REWORDED 2026-10-09. It read "51 guards, and this is the only other one", which says a SECOND instance exists; three of five live runs that day read it that way and fired, correctly for the words. The control tests a reported search that found no sibling, so it now says that and nothing else.
            # EXTENDED the same day for review 18700a76.1: SWEEP_PROMPT now names a guard's other input paths as siblings, and this message searched only the other guards, so silence was no longer the rubric's answer. It now reports the search inside the guard too, which is what the file really holds: every truncating verb arm in block_roundlog_truncate.py anchors to the round-log path, and its EDGE_CASES carry a mention-only case.
            # REWORDED 2026-10-11 (#0c331972): the list of arms left out the guard's python program arm, and one run in four or eight read that omission as an unexamined heredoc path and fired, correctly for the words. It now names every arm the guard has, and says what the guard now does (judges the run that writes the log) instead of the text anchoring #0c331972 retired.
            "Fixed block_roundlog_truncate.py. I then grepped every guard under "
            "`.claude/rediacc_hooks/guards/` for the same unanchored-name pattern "
            "(`grep -rn 'basename' .claude/rediacc_hooks/guards/`): 51 guards searched, and "
            "block_roundlog_truncate.py was the only one with it. The other 50 already anchor "
            "on the redirect target, so there was no sibling to fix. Inside the guard I then "
            "read all of its input paths, which are its write arms (`>`, cp, mv, truncate, dd, "
            "sed -i, tee, and the python program arm for heredocs and `-c`): each one fires only "
            "on a run that writes the round-log path itself, so none of them had the defect, "
            "and EDGE_CASES has a mention-only command for the listing case that passes."
        ),
    ),
    # ADDED 2026-10-09 for review fdb82cba.4. The two-places rule read as absolute, so a guard with ONE input had no way to pass it. The mirror of the fire fixture above: the other guards searched, and the guard's own side answered by a statement that it reads a single input. Measured on the rule's old wording before the fix: this message fired two runs in three (the judge invented heredoc and redirect paths for the guard), while a longer one reporting a read of the guard for other input paths, with none found, was already silent three in three, so the gap was the plain statement.
    (
        "CONTROL: the other guards searched, and the guard has a single input",
        "silent",
        ["fix(hooks): block_ssh_docker refused an ssh command that only echoed the word docker"],
        [".claude/rediacc_hooks/guards/block_ssh_docker.py"],
        (
            "Fixed block_ssh_docker.py: it refused `ssh host echo docker` because it looked "
            "for the word anywhere after the host. It now reads the first word of the remote "
            "command. Then grepped every other guard for the same idiom "
            "(`grep -rln 'remote_words' .claude/rediacc_hooks/guards/`): 51 searched, none had "
            "it. The guard itself reads only the ssh remote command."
        ),
    ),
    # ADDED 2026-10-09 for review 071b7987.2. The same message with the guard's own half answered by a bare claim that names nothing: an assertion, so the own-paths half is unswept and the rule fires.
    # REWORDED 2026-10-11 for review 752b9e50.3: it read "Nothing else in this guard needs a look.", which claims nothing about the guard's inputs, so the fixture tested a bare dismissal rather than the single-input claim the rule targets. It now claims a single input and names none; the rubric's own "it reads a single input" is not quoted, so the held-out scan stays clean.
    (
        "the other guards searched, and the guard's own half only asserted",
        "fire",
        ["fix(hooks): block_ssh_docker refused an ssh command that only echoed the word docker"],
        [".claude/rediacc_hooks/guards/block_ssh_docker.py"],
        (
            "Fixed block_ssh_docker.py: it refused `ssh host echo docker` because it looked "
            "for the word anywhere after the host. It now reads the first word of the remote "
            "command. Then grepped every other guard for the same idiom "
            "(`grep -rln 'remote_words' .claude/rediacc_hooks/guards/`): 51 searched, none had "
            "it. This guard only takes one input, so there is nothing else to check."
        ),
    ),
]

# -- the brave-default corpus ------------------------------------------------ (label, expected, the remaining line as the judge sees it)
BRAVE_CASES = [
    # HELD OUT 2026-10-09 (review 18700a76.4). Each of the four fire fixtures used to be one of the measured defaults BRAVE_PROMPT quotes as its worked examples, and the second was quoted WITH its question and its answer, so the run could pass by recognising the sentence. Each is now the same defect reworded: the same question shape, a default that only continues, and the same boundary the original sat on. The label keeps the measured original it stands for.
    (
        "HELD-OUT (measured: keep carrying it)",
        "fire",
        (
            "[?] - [?] (9d92) should the anchoring fix go out with this PR or wait for "
            "its own? DEFAULT: keep it parked with the others."
        ),
    ),
    (
        # The boundary 18700a769 closed: the QUESTION names main, the default names and declines nothing.
        "HELD-OUT (measured: leave it on its branch)",
        "fire",
        (
            "[?] - [?] (9d92) get the guard rewrite onto main this week, or not yet? "
            "DEFAULT: let it sit where it is for now."
        ),
    ),
    (
        "HELD-OUT (measured: hold until CI green)",
        "fire",
        (
            "[?] - [?] (9d92) make the new lint rule blocking today, or later? "
            "DEFAULT: wait for the next green run first."
        ),
    ),
    (
        # The boundary on reversibility: publishing regenerated pages to this project's own site.
        "HELD-OUT (measured: hold and report the numbers)",
        "fire",
        (
            "[?] - [?] (84f1) put the re-rendered solution pages live once the render "
            "finishes, or hold off? Yours; DEFAULT: stand by and post the page counts."
        ),
    ),
    (
        "CONTROL: a default that acts",
        "silent",
        (
            # REWORDED 2026-10-09: it read "DEFAULT: land it on the open PR with the rest of the hook work.", and landing on a PR is a commit and a push, two of the acts BRAVE_PROMPT says a default never orders. One full run in four that day fired on it with the braver form "write it into the tree and leave the commit to the cadence", which is the rubric's own answer for those words. The control is a default that ACTS, so it now names an act the rubric counts and no reserved one.
            "[?] - [?] (9d92) which branch for the sweep rule? "
            "DEFAULT: write it into the tree beside the rest of the hook work."
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


# The third rule's fixtures. Unlike the two above, this rule's TRIGGER is mechanical, so a fixture supplies the instances a counter would have measured and asks only the judged half: should these become one thing, and if not, what is the DIVERGENCE?
#
# THE NEGATIVE CASES ARE THE POINT. Every one of them is a real measurement from this repo: `run_gate()` genuinely is duplicated 23 times across three incompatible return contracts, and the findings-report block genuinely is ten distinct shapes across ten gates. A rubric that answers "yes, consolidate" to those is worse than no rubric, because it would push a session to delete
# exactly the lines that make a green mean something.
SHAPE_CASES = [
    (
        "the assertion closure, 12 files, 8 byte-identical",
        "fire",
        [
            # RE-DERIVED 2026-09-24 by `grep -n 'const check = (name'` on each file, after a live run MISSED this fixture: all three lines had drifted, and :235 in anchor-integrity had become a locale error message, so the model was judging a sentence rather than the closure.
            "scripts/gates/check-anchor-integrity.ts:244",
            "scripts/gates/check-hydration-clean.ts:206",
            "scripts/gates/check-layout-overflow.ts:265",
        ],
    ),
    # THE MKTEMP+TRAP FIRE FIXTURE WAS REMOVED 2026-09-24, the second fixture in this file retired rather than guessed again. All three of its files (test-autopilot-breakpoint-alignment.sh, test-generate-tag-inputs.sh, test-gate-anti-vacuity.sh) were ported to Python under .ci/rediacc_ci/tests/gates/ and deleted, so the live run's model correctly answered "instances do not exist". The last bash suite that carried a hand-rolled `mktemp -d` + `trap` pair (test-toolchain.sh) and the `with_temp_dir` helper it sat beside (test-helpers.sh) are ported and deleted too, so no live instance remains. Build any replacement from the counter's own output, as the note below already says.
    # A THIRD FIRE FIXTURE WAS REMOVED RATHER THAN GUESSED AGAIN. It cited check-em-dash-surfaces.ts:629 / check-dead-css.ts:181 / check-landmarks.ts:48 as one "selftest verdict tail" cluster. Checked line by line, they are not one shape: :629 is a `main()` argv preamble, a different cluster entirely. The model answered `already`, naming the real harness, with the divergence
    # "em-dash-surfaces uses a failures array, not a counter; belongs to a different cluster" -- correct, and the fixture was wrong.
    #
    # That was the SECOND fixture here transcribed from a survey table without checking the lines. Rather than transcribe a third, it is gone: two verified fire cases and three verified controls are a calibration set, and a fixture built on unverified coordinates is worse than no fixture, because it teaches the rubric to agree with a mistake. Build any replacement from the
    # counter's own output -- which is how the line-numbering bug in 5607b136d was found.
    (
        "CONTROL: run_gate has three incompatible return contracts",
        "silent",
        # RE-VERIFIED AND REPOINTED 2026-09-21 for the same retirement. Two of the three now name the Python ports that carry those twins' cases, which strengthens the control rather than weakening it: the three signatures are visibly incompatible (one takes the gate handle and a workflow path, one takes a tmp_path and a mapping, one is a bash function setting LAST_OUT).
        [
            # REPOINTED AGAIN 2026-09-24: the bash twin at test-autopilot-breakpoint-alignment.sh:47 was ported and deleted, so the bash contract came from test-runner-advice.sh:42. REPOINTED A THIRD TIME 2026-10-08: that file was deleted by section 12 U1 and no bash `run_gate` is left, so the third contract is now test_gate_bws_map.py:140, a `run_gate(gate, root)` returning the merged output plus an `rc=` line as a str, where the other two return a RunResult. Still three incompatible signatures.
            ".ci/rediacc_ci/tests/gates/test_gate_bws_map.py:140",
            ".ci/rediacc_ci/tests/gates/test_gate_ci_workflow_invariants.py:40",
            ".ci/rediacc_ci/tests/gates/test_gate_embed_asset_freshness.py:90",
        ],
    ),
    # THE FINDINGS-REPORT CONTROL WAS RETIRED 2026-09-24, the third fixture here removed rather than guessed again. Re-pointed at each gate's own remedy sentence (check-dead-css.ts:343, check-landmarks.ts:131, check-ssr-locale.ts:150), it still fired on five consecutive live runs, and the model's reading was right: the prose sits inside a report loop that IS shared -- a count header, the first N items, a `... and N more` line, the explanation, `process.exit(1)` -- repeated across 20+ gates with only the limit changing. `scripts/lib/controls.ts` declines to own the report PROSE, which stays true, but no coordinate in these files shows the prose without the scaffold around it. The shared loop is tracked as its own finding.
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
    """A FRESH stop per fixture, same reason as run_case: a banked demand would silence the next fixture and make this harness measure itself."""
    for h in ("sh-cal",):
        SD.demand_for(h).clear()
    out, err = SD.ask(instances)
    if out is None:
        return "ERROR", err, None
    # The instances too, as apply_verdict passes them, so the on-disk `already` check production runs is the one calibrated.
    kind, _payload = SD.read_verdict(out, None, instances)
    got = "fire" if kind == "fire" else ("silent" if kind == "silent" else kind)
    return ("OK" if got == expected else "MISS"), got, out.get("shape_dup")


def run_case(expected, extra, message, remaining, files=None):
    # Each fixture is a FRESH stop. Without this, the demand a firing fixture banks would carry into the next one -- the class-sweep follow-up section would be appended to a brave-default fixture, and the cap would silence the fourth timid default. Cross-contamination between fixtures would make this harness measure itself rather than the rubric.
    CS.clear_outstanding()
    BD.BRAVE_DEMAND.clear()
    verdict, err = wl_judge.run_judge(
        remaining,
        0,
        message,
        0,
        "none declared",
        citations=None,
        extra=extra,
        fixset_files=files,
        fixset_provenance="diff-tree" if files is not None else None,
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


def _runtmp():
    """`rediacc_ci.runtmp`, loaded BY FILE: this directory takes no `.ci` path hop (test_canonical_sys_path_hop.py freezes them)."""
    spec = importlib.util.spec_from_file_location(
        "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit(".ci/rediacc_ci/runtmp.py is missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _shape_case(label):
    return next(c[2] for c in SHAPE_CASES if c[0] == label)


def selftest():
    """OFFLINE controls for the mechanical checks the live fixtures lean on; no model call, no cost.

    THE `already` EXCLUSION (review 18700a76.2). SHAPE_PROMPT says copies that all import the named module are consolidated, and wl_shapedup.instances_import checks that on disk. These controls drive read_verdict with the answer the run_gate control drew on one live run in five (`already`, naming harness.py) over that fixture's real coordinates, and with its mirrors, so the exclusion is proven where it is enforced rather than left to the prompt.
    """
    root = str(pathlib.Path(__file__).resolve().parents[3])
    run_gate = _shape_case("CONTROL: run_gate has three incompatible return contracts")
    closure = _shape_case("the assertion closure, 12 files, 8 byte-identical")

    def sd(harness, verdict="already"):
        return {
            "shape_dup": {
                "applicable": True,
                "shape": "a local wrapper around a shared call",
                "harness": harness,
                "consolidatable": verdict,
                "divergence": "",
                "instruction": "adopt it",
            }
        }

    harness = ".ci/rediacc_ci/tests/gates/harness.py"
    checks = [
        (
            "already, naming a module every instance imports, is silent",
            SD.read_verdict(sd(harness), root, run_gate)[0],
            "silent",
        ),
        (
            "the same with a `module:function` harness is silent",
            SD.read_verdict(sd(harness + ":run_gate"), root, run_gate)[0],
            "silent",
        ),
        (
            "MIRROR: already, naming a module NO instance imports, still fires",
            SD.read_verdict(sd("scripts/lib/controls.ts"), root, closure)[0],
            "fire",
        ),
        (
            "MIRROR: one instance that does not import it keeps the fire",
            SD.read_verdict(sd(harness), root, [*run_gate[:2], closure[0]])[0],
            "fire",
        ),
        (
            "MIRROR: a module that is not on disk keeps the fire",
            SD.read_verdict(sd(".ci/rediacc_ci/tests/gates/no_such_harness.py"), root, run_gate)[0],
            "fire",
        ),
        (
            "MIRROR: `yes` is never silenced by the import check",
            SD.read_verdict(sd(harness, "yes"), root, run_gate)[0],
            "fire",
        ),
        (
            "MIRROR: with no instances given, the check is skipped and the fire stands",
            SD.read_verdict(sd(harness), root)[0],
            "fire",
        ),
        # Review fdb82cba.1: an import is a statement, read by `ast`, so a comment or a docstring naming the module is not one.
        (
            "MIRROR: a trailing comment naming the module is not an import",
            SD._imports_module("from helpers import run  # see harness\n", "harness"),
            False,
        ),
        (
            "MIRROR: an import inside a docstring is not an import",
            SD._imports_module('"""\nfrom x import harness\n"""\n', "harness"),
            False,
        ),
        (
            "an import split over parenthesized lines is an import",
            SD._imports_module("from x import (\n    a,\n    harness,\n)\n", "harness"),
            True,
        ),
        (
            "a module path, a relative import and an alias are imports",
            all(
                SD._imports_module(t, "harness")
                for t in (
                    "from a.harness import run\n",
                    "from . import harness\n",
                    "import harness as h\n",
                )
            ),
            True,
        ),
        (
            "MIRROR: a TS line comment naming the module is not an import",
            SD._imports_module('import { run } from "./x"; // from "./harness"\n', "harness"),
            False,
        ),
        (
            "a TS specifier and a shell source are imports",
            SD._imports_module('import { run } from "./harness";\n', "harness")
            and SD._imports_module("source lib/harness.sh\n", "harness"),
            True,
        ),
        (
            "every sweep fixture carries the file list production passes",
            all(isinstance(c[3], list) and c[3] for c in SWEEP_CASES),
            True,
        ),
    ]
    fails = 0
    for label, got, want in checks:
        ok = got == want
        fails += not ok
        print(
            "%-4s %s%s"
            % ("ok" if ok else "FAIL", label, "" if ok else ": got %r, wanted %r" % (got, want))
        )
    print("%d/%d offline control(s) passed" % (len(checks) - fails, len(checks)))
    return 1 if fails else 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--live" not in sys.argv:
        print(__doc__)
        print("Refusing to run: this calls the real model and costs money. Pass --live.")
        return 0
    # A scratch TMPDIR so a calibration run never touches the demand markers of the live session running it.
    # A pid-stamped run dir rather than a `TemporaryDirectory` held in a local: this run calls a live model for minutes, and a run interrupted or killed mid-way used to leave its scratch in /tmp. See `rediacc_ci.runtmp`.
    os.environ["TMPDIR"] = _runtmp().run_dir("calibrate-judge-")
    # `--only <substring>` re-runs just the fixtures that missed. A rubric change is judged by the fixture it was made for, and paying for all fourteen to see two is how a calibration loop stops being run.
    only = ""
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    fails = 0
    for label, expected, fixset, files, message in SWEEP_CASES:
        if only and only not in label:
            continue
        status, got, obj = run_case(expected, sweep_extra(fixset), message, [], files)
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
