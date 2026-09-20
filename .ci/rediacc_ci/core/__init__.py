"""rediacc_ci.core -- the modules that used to be `.ci` bash libraries.

WHY THIS SUBPACKAGE EXISTS AND THE FLAT MODULES DO NOT LIVE HERE. The package root already holds `paths`, `log`, `proc`, `gitx`, `controls` and `workflows`. Those are PRIMITIVES: they answer questions any program in this repository has (where is the root, how do I run a command, what does git say). They were never a bash library and they have no bash twin.

`core` is the other thing. Every module in here is the port of a specific file under `.ci/`, that file still exists, and it still works -- it delegates. The subpackage name is not decoration: `docs/ci-overhaul/08-driver-contract.md` arbitrates `rediacc_ci/core/env.py` as the home of `env_file_load` when W8 retargets `.ci/lib/local-common.sh`, and `.ci/rediacc_ci/__init__.py` names
`rediacc_ci.core.env` and `rediacc_ci.core.output` in its own roadmap. Putting the ported libraries anywhere else would have made that arbitration wrong on arrival.

THE SHIM CONTRACT, stated once here rather than in each module. For every module in this subpackage:

  1. The bash file KEEPS ITS PATH AND ITS FUNCTION NAMES *while it exists*.
     Roughly 150 scripts source `.ci/scripts/lib/`, and `.ci/lib/find-port.sh`
     was sourced by `devbox.sh`, `account.sh` and `service.sh` at
     container-start time. A port that renamed anything would be a flag day.
     THE SHIM STAGE IS NOT THE END STATE: W7P5-b deleted `find-port.sh`
     outright and retargeted those three callers onto `core.ports` directly,
     because a shim is a delay, not an exit. Clause 3 below is what governs
     WHEN that is allowed, not whether.
  2. The bash function BODY becomes one call into this package. Not a
     reimplementation kept in sync -- there is exactly one implementation and
     bash reaches it.
  3. The twin is NOT deleted. `08-driver-contract.md` section 3 names the
     conditions under which each bash file may finally go, and none of them is
     "the Python works".
  4. THE DELEGATION IS PROVED BY THE ORIGINAL CALLERS, driven end to end, not
     by a new test written alongside the port. `.ci/scripts/test/gates/
     test-age-check.sh` and `.ci/scripts/quality/check_setup_idempotency.py`
     already exercise these two libraries against real git fixtures and real
     port probes; they are the proof, and they had to keep passing unedited
     except where the port moved the line a planted-defect control mutates.

WHY EACH MODULE ALSO HAS A `python3 -m` ENTRY POINT. A bash function cannot
import Python; it can only run it. Every module here therefore ends with a tiny
argv dispatcher, and the shim calls `python3 -m rediacc_ci.core.<mod> <verb>`. That entry point is part of the contract the shim depends on, so it is covered by the same tests rather than being treated as a debugging convenience.

ONE PROCESS PER LOGICAL OPERATION, WHICH IS A DESIGN CONSTRAINT AND NOT A
DETAIL. `find_port_block` probes up to `slots x block` ports. Delegating the INNER probe would fork one interpreter per port and turn a millisecond into tens of seconds. So the shim delegates the OUTERMOST function it can, and the verbs below are shaped around that rather than around the bash call graph.
"""

__all__: list[str] = []
