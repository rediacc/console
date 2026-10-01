"""Freeze or refresh the `.ci` twin goldens (PLAN-retire-bash-oracles B3).

    PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden <twin.sh>... --source bash|port --reason "<why>" [-k <expr>]

A MODULE, NOT A SCRIPT BY PATH: run this way `rediacc_ci` is importable without a hand-written `sys.path` hop (`check:ci-canonical-sys-path-hop` refuses those), and the re-exec under pytest's interpreter below uses the same `-m` form.

The `.ci` counterpart of `.claude/rediacc_hooks/tests/regolden.py`, writing the same JSONL format through the same `goldenio` (see `differential.py`, section "Goldens").

HOW IT RECORDS. It runs, in this process and serially (`-n 0`), every test module under `.ci/rediacc_ci/tests` that names one of the given twins, with `REDIACC_CI_REGOLDEN=<source>` set. Each `differential.twin_streams` call then answers from the live bash (`--source bash`, the freeze) or from the port (`--source port`, a Rule-T re-record after the twin is gone) and keeps the
answer; the goldens are written once pytest returns. A gate-test `BASH_TWIN` (`tests/gates/`) is frozen the same way through `test_twin_parity.py`, which is collected whenever a twin it drives is named.

REFUSES:
  * without `--reason`, unconditionally. It is stamped as `intentional: <reason>` on every record whose value moved; a first freeze moves nothing and writes no marker.
  * `--source bash` for a twin whose `.sh` is gone: there is nothing left to freeze from.
  * when the recording run is not green. A freeze taken from a red differential would enshrine the disagreement as the spec.
  * when no module names the twin, or the run recorded nothing for it: a regolden that touched no golden is not a regolden.

`-k <expr>` narrows a re-record to the cases a Rule-T fix moved, so the reason is stamped only where it is true; every unselected record is carried over byte-for-byte. Without `-k` a key the run never asked for is dropped (and counted), because the run covered every case there is.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import paths

HERE = pathlib.Path(__file__).resolve().parent
SEAM_RE = re.compile(r"\btwin_(?:streams|call|run)\(")
ROOT = paths.repo_root()
MODULE = "rediacc_ci.tests.regolden"


def modules_naming(twin: str) -> list[str]:
    """pytest targets that record `twin`: every module that names it AND routes through `twin_streams`, plus, for a gate test declaring it as its `BASH_TWIN`, that module's case in `gates/test_twin_parity.py` (the parity driver is what runs a gate-test twin; the gate module itself never does)."""
    base = os.path.basename(twin)
    found = []
    for path in sorted(HERE.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if (twin in text or base in text) and SEAM_RE.search(text):
            found.append(str(path))
        if 'BASH_TWIN = "%s"' % twin in text:
            found.append(
                "%s::test_port_and_twin_agree[%s]"
                % (HERE / "gates" / "test_twin_parity.py", path.stem)
            )
    return found


def _reexec_under_pytest() -> int:
    """Re-run this script under the interpreter that owns pytest.

    pytest is not on the system python here; the bootstrap installs it as a uv tool (`$PYTEST_BIN`, else `.ci/cache/toolchain/uv-tools/bin/pytest`), and that script's shebang names the interpreter whose site-packages hold it. A missing tool is a loud failure with the fix, never a traceback.
    """
    candidate = os.environ.get("PYTEST_BIN") or str(
        ROOT / ".ci/cache/toolchain/uv-tools/bin/pytest"
    )
    try:
        with open(candidate, encoding="utf-8") as fh:
            shebang = fh.readline().strip()
    except OSError:
        shebang = ""
    interpreter = shebang[2:].split()[0] if shebang.startswith("#!") else ""
    if not interpreter or not os.access(interpreter, os.X_OK) or interpreter == sys.executable:
        print(
            "regolden: pytest is not importable and no bootstrap pytest was found at %s.\n"
            "  fix: bash .ci/bootstrap.sh   (then re-run this command)" % candidate,
            file=sys.stderr,
        )
        return 77
    env = dict(os.environ, PYTHONPATH=str(ROOT / ".ci"))
    return subprocess.run(
        [interpreter, "-m", MODULE, *sys.argv[1:]], env=env, check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("twins", nargs="+", help="repo-relative path of each bash twin")
    parser.add_argument("--source", required=True, choices=("bash", "port"))
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "-k",
        dest="select",
        default=None,
        help="a pytest -k expression: re-record only the cases it selects; every other record is kept as it is",
    )
    args = parser.parse_args(argv)
    if not args.reason.strip():
        print("regolden: --reason is empty", file=sys.stderr)
        return 2

    os.chdir(ROOT)
    os.environ["REDIACC_CI_REGOLDEN"] = args.source
    # Imported only now: `differential` reads the mode per call, but its BASE_ENV is built at import.
    try:
        import pytest  # noqa: PLC0415
    except ModuleNotFoundError:
        return _reexec_under_pytest()

    from rediacc_ci.tests import differential as diff  # noqa: PLC0415

    files: list[str] = []
    for twin in args.twins:
        if args.source == "bash" and not (ROOT / twin).is_file():
            print(
                "regolden: %s does not exist; there is no bash left to freeze" % twin,
                file=sys.stderr,
            )
            return 2
        named = modules_naming(twin)
        if not named:
            print("regolden: no test module under %s names %s" % (HERE, twin), file=sys.stderr)
            return 2
        files += [p for p in named if p not in files]

    os.environ["REDIACC_CI_REGOLDEN_ONLY"] = ",".join(
        sorted(diff.golden_stem(t) for t in args.twins)
    )
    # The parity driver may reuse a recorded agreement without driving the twin at all; a recording run must drive it.
    os.environ["TWIN_PARITY_ALWAYS_DRIVE"] = "1"
    select = ["-k", args.select] if args.select else []
    rc = pytest.main(["-q", "-n", "0", "-p", "no:randomly", *select, *files])
    if rc != 0:
        print(
            "regolden: the recording run exited %d; nothing was written. A freeze of a red "
            "differential would make the disagreement the spec." % rc,
            file=sys.stderr,
        )
        return 1
    stems = {diff.golden_stem(t) for t in args.twins}
    missing = sorted(stems - set(diff.RECORDED))
    if missing:
        print("regolden: the run recorded nothing for %s" % ", ".join(missing), file=sys.stderr)
        return 1
    for line in diff.write_recorded(
        args.source, args.reason, only=stems, keep_unseen=bool(args.select)
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
