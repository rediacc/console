#!/usr/bin/env python3
"""Entry point for the dead-Python scanner. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.dead_python`, which pytest and the gate's own `--selftest` import directly.

NEW GATE, 2026-09-08 (U4). It has no bash twin and never had one: Go has `deadcode`, TypeScript has knip, bash has `scripts/gates/check-dead-bash.ts`, and the 592 Python files in this tree had nothing at all. The instrument the tooling transformation needs is specifically the one that notices a PORT that shadowed green and was then forgotten: the shadow protocol lands the new side
before the old side is deleted, so between those two commits a file can stop being run by anything while every other gate stays green, because the bash twin is still registered and still passes.

WHY THE BASH GATE'S PREDICATE COULD NOT SIMPLY BE COPIED. `check-dead-bash.ts` asks "is this basename mentioned by any other tracked file", which is adequate
for shell because a shell script is only ever reached by being NAMED. Python is
also reached by being imported, collected, globbed and re-executed, and it is MENTIONED constantly by prose that reaches nothing: `agent/` alone names hundreds of Python paths in plans. So the routes are enumerated instead, prose is not one of them, and the reasoning is in the module docstring.

DRIVEN ON THE REAL TREE, both streams captured separately, before and after a planted violation:

    clean            -> exit 0, "593 file(s) scanned, every one reached --
                        44 glob, 128 imported, 1 manual, 36 mentioned,
                        234 pytest, 150 wired"
    plant one file   -> exit 1, naming exactly the planted path
    plant removed    -> exit 0 again, same shape line

THE FIRST PLANT DID NOT FIRE, AND THE CONTROL WAS WRONG, NOT THE GATE. The probe was given a FIXED name and that name was written into this docstring and into the gate test, so the file the control planted was mentioned by two reached files before it ever existed and the gate correctly admitted it by the `mentioned` route: 596 scanned, `mentioned` up from 37 to 38, exit 0. The
second plant took its name from `secrets.token_hex` at run time, which nothing in the tree can vouch for, and the gate reported it immediately. The name is therefore deliberately NOT recorded here: writing it down is what broke the first attempt. The tree was left byte-identical afterwards, verified by comparing `git status --porcelain` before and after.

NOT REGISTERED BY THIS WRITER. `package.json`, `scripts/ci-runner/manifest.ts` and `.github/workflows/ci-quality.yml` are driver-only, so the registration fragment travels in the report instead. Until it lands, this gate reaches CI through nothing and is run locally only, which is the one-sided shape the programme exists to prevent and is called out rather than left in a diff.

---- gate ---- step: Dead Python needs: none lane: quality-static selftest: true why: a Python file no execution route reaches is dead code sitting beside live
     gates, and the specific case this tree keeps producing is a bash-to-Python
     port that shadowed EQUIVALENT, was never registered, and whose twin was
     later deleted; nothing else in the estate can see that file stop running
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import dead_python

if __name__ == "__main__":
    raise SystemExit(dead_python.main(sys.argv[1:]))
