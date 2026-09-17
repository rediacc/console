"""Put `.ci` on `sys.path` so an entry point in this directory can import `rediacc_ci`.

Imported for its SIDE EFFECT, once per entry point:

    import _cipath  # noqa: F401
    from rediacc_ci.docker import <mod>

THIS IS A SECOND COPY, AND THE COPY IS THE PATTERN. `.ci/scripts/quality/_cipath.py` is the first; this is the first one outside that directory, and it was measured to be the only other one before it was written. A shared import cannot work here, and the reason is the same one that makes the hop necessary at all: what a path invocation puts on `sys.path[0]` is THE SCRIPT'S OWN
DIRECTORY. For an entry point in `.ci/scripts/docker/` that is `.ci/scripts/docker`, so `import _cipath` can only ever resolve to a file sitting beside it. A module that could be imported from the quality directory would need `.ci` on the path already, which is exactly what has not happened yet.

WHY AN ENTRY POINT EXISTS AT ALL is different here from the quality copy, and worth stating rather than inheriting. There, the registry invokes a gate BY PATH and `check:ci-parity` cannot tokenize `python3 -m`. NONE OF THE THREE DOCKER SCRIPTS IS A GATE: they are workflow `run:` targets and a release-script forwarder, with no `package.json` script, no
`scripts/ci-runner/manifest.ts` entry, and no `gates.lock.json` row. The reason a file at a path is still needed is the call sites themselves -- a workflow step runs `.ci/scripts/docker/create-manifest.sh --image renet` today, and the cutover replaces that string with another path, not with a `python3 -m` invocation that would need `PYTHONPATH` set in every job that uses it.

WHY THE HOP IS NEEDED. Nothing puts `.ci` on `sys.path` for a path invocation. Run `python3 .ci/rediacc_ci/docker/retag_image.py` and it dies at `from rediacc_ci import log, proc` before doing any work. That `sys.path[0]` behaviour is switched off by `-P`, `-I` and `PYTHONSAFEPATH`; none of the three is used anywhere in this tree, and a script started under any of them would fail
loudly at this import rather than quietly skip work.

WHY AN IMPORT FOR SIDE EFFECT AND NOT A FUNCTION. Settled with ruff rather than
argued, in the quality copy, and reproduced here because the same `select =
["ALL"]` applies: a stdlib import placed after the hop is I001, the hop behind a helper call is E402, and `import _cipath` followed by `from rediacc_ci ...` is clean. A function call is a statement, and any import after a statement is E402.

WHY THE NUMBER IS CHECKED RATHER THAN NAMED. `parents[2]` is the same depth as the quality copy -- `.ci/scripts/docker/_cipath.py` is two directories below `.ci`, exactly as `.ci/scripts/quality/_cipath.py` is -- and the `raise` below buys the guarantee that a move says so: the reader gets a message naming the directory that was computed, instead of a `ModuleNotFoundError:
rediacc_ci` raised from a line that never mentions `_cipath` at all.

ANOTHER GATE READS THIS ASSIGNMENT. `check_python_gate_deps.py` resolves
`CI_DIR = ...parents[2]` to decide that `rediacc_ci` is a first-party import
rather than something a job forgot to `pip install`.
"""

import pathlib
import sys

CI_DIR = pathlib.Path(__file__).resolve().parents[2]

if not (CI_DIR / "rediacc_ci" / "__init__.py").is_file():
    raise RuntimeError(
        "_cipath computed %s as the .ci directory, but there is no rediacc_ci "
        "package in it. This file has moved: it must stay in .ci/scripts/docker/, "
        "two directories below .ci." % CI_DIR
    )

sys.path.insert(0, str(CI_DIR))
