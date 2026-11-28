r"""check:ci-env-registry -- every environment variable this repository reads, in one file, held by one gate.

ONE FILE, ONE GATE, ONE VERB (agent/plans/PLAN-tooling-code-reduction.md D3). Three registries used to hold one variable set, each with its own gate: the shard classification (`check:ci-env-manifest`), the AST-measured Python read set (`check:ci-python-env-registry`) and the WORKLIST_* registry (`check:ci-worklist-env-registry`). `env:register` already wrote all three in one pass. They are now three sections of `.ci/config/env-manifest.json` (`env_doc.py`), and this gate holds all three:

  `shards`        who supplies each name and who may read it: five readers derive
                  the corpus from tracked files and four set-arithmetic clauses hold
                  it against the classification (`env_manifest.py`)
  `python_reads`  every `module:NAME` pair a tracked Python module reads, shrink-only
                  and set-equal in both directions (`python_env_registry.py`)
  `worklist`      every WORKLIST_* name with its kind, class and pinned default
                  spellings, registered and read in both directions
                  (`worklist_env_registry.py`)

BOTH DIRECTIONS, IN EVERY SECTION. A read nobody registered is red (an undeclared input, or a typo that reads as unset), and so is a row nothing reads (a stale entry, or one banked for a read that never existed). The plant tests in `test_quality_env_manifest.py` drive this entry on the real tree with a tmp copy of the document (`ENV_REGISTRY_OVERRIDE_FILE`) and prove each red.

CONTROLS FIRST, ALL THREE. The three sections' selftests run before any verdict, every one of them even when an earlier one failed, so a broken instrument is named rather than hidden behind the first failure. Then every section's verdict prints, and the exit code is the worst of them: 1 for a finding, 2 for a refusal or a failed control.

A NAME IS ADDED with one command, `npm run env:register -- <module> <NAME> --class <shard>` (`env_register.py`), which writes the sections it must and runs this gate.

---- gate ----
step: Env registry
needs: none
lane: quality-static
selftest: true
slow: true
why: an environment variable is an undeclared input. One file says who supplies each
     name, which Python module reads it, and how a WORKLIST_* knob is spelled and
     defaulted; one gate holds all three sections against the tree in both directions,
     so a read nobody registered and a row nothing reads are both red
---- end gate ----
"""

from __future__ import annotations

import sys

from rediacc_ci import log
from rediacc_ci.controls import controls_first
from rediacc_ci.quality import env_doc
from rediacc_ci.quality import env_manifest as em
from rediacc_ci.quality import python_env_registry as per
from rediacc_ci.quality import worklist_env_registry as wer

SECTIONS = (
    (env_doc.SHARDS, em.selftest, em.check),
    (env_doc.PYTHON_READS, per.selftest, per.check),
    (env_doc.WORKLIST, wer.selftest, wer.check),
)


def selftest() -> bool:
    """True when any section's controls failed. Every section runs, so each failure is named."""
    failed = []
    for name, control, _check in SECTIONS:
        if control():
            failed.append(name)
    if failed:
        print("env registry: the controls of section(s) %s failed" % ", ".join(failed))
    return bool(failed)


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("env registry", selftest)
    if rc:
        return rc
    worst = 0
    verdicts = []
    for name, _control, check in SECTIONS:
        log.info("---- section `%s` of %s ----" % (name, env_doc.DOC_REL))
        code = check()
        verdicts.append("%s rc %d" % (name, code))
        worst = max(worst, code)
    if worst:
        log.error("env registry: %s; red." % ", ".join(verdicts))
        return worst
    log.success(
        "env registry: %d section(s) of %s green (%s)"
        % (len(SECTIONS), env_doc.DOC_REL, ", ".join(verdicts))
    )
    return 0


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse("env_registry", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(main(sys.argv[1:]))
