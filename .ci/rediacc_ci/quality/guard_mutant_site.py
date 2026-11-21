"""The redirect behind check:ci-guard-mutations' hook arm: load a planted copy of one guard in place of the real module.

The gate (scripts/gates/check-guard-mutations.ts) copies this file to `<scratch>/site/sitecustomize.py` and puts that directory first on PYTHONPATH for one run of a guard's `test-<stem>.py` suite. Every interpreter the suite starts then compiles the guard from `GUARD_MUTANT_SOURCE` (the planted copy in the gate's scratch directory) whenever it would have compiled `GUARD_MUTANT_TARGET` (the real guard), and appends one line to `GUARD_MUTANT_LOG`. The real guard file is never written.

THE SEAM is `SourceFileLoader.get_code`, which every route into the module passes through: `importlib.import_module` (guards.load, dispatch.py) and `spec_from_file_location(<any name>, GUARD)` both build a SourceFileLoader. A suite that instead reads the guard's TEXT and execs it (the suites' own DEFECT/MUTANT runners do this) still sees the real text, which is what keeps those internal controls applicable: only the live guard is broken. The code object keeps the real path as its filename, so `__file__`-relative lookups inside the guard behave exactly as they do unplanted.

THE LOG is the anti-vacuity half: a run whose log is empty never loaded the planted copy, so its verdict says nothing about the plant, and the gate reports it as UNREACHED rather than reading green as "undetected" or red as "caught".

CHAINING. This environment already ships a sitecustomize on PYTHONPATH (.claude/hooks/profile/py, the resource recorder, which itself re-exports the distro one). Shadowing it would silently drop that recorder from every suite process, so the next `sitecustomize.py` on sys.path is executed after the redirect is installed.

SEPARATE FROM guard_mutants.py ON PURPOSE. This runs at the start of every interpreter a suite spawns, which is thousands per run, so it imports only what interpreter startup has already loaded (os, sys, importlib), never ast, json or pathlib. Never print. An exception raised here is caught and reported by `site` itself without aborting the interpreter, and an uninstalled redirect shows up as an empty log, which the gate refuses.
"""

import os
import sys
from importlib import machinery, util


def install_redirect() -> bool:
    """Compile GUARD_MUTANT_SOURCE wherever GUARD_MUTANT_TARGET would be compiled. True when installed."""
    target = os.environ.get("GUARD_MUTANT_TARGET", "")
    source = os.environ.get("GUARD_MUTANT_SOURCE", "")
    log = os.environ.get("GUARD_MUTANT_LOG", "")
    if not (target and source and log):
        return False
    real = os.path.realpath(target)
    name = os.path.basename(real)
    original = machinery.SourceFileLoader.get_code

    def get_code(self: machinery.SourceFileLoader, fullname: str) -> object:
        # The basename test first: realpath costs syscalls, and this runs for every source module every suite process imports.
        if os.path.basename(self.path) != name or os.path.realpath(self.path) != real:
            return original(self, fullname)
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, ("%d %s\n" % (os.getpid(), fullname)).encode())
        finally:
            os.close(fd)
        return compile(text, self.path, "exec", dont_inherit=True)

    type.__setattr__(machinery.SourceFileLoader, "get_code", get_code)
    return True


def chain_next_sitecustomize() -> None:
    """Run the next `sitecustomize.py` on sys.path after this one, so the redirect shadows nothing."""
    here = os.path.dirname(os.path.realpath(__file__))
    for entry in sys.path:
        if not entry or os.path.realpath(entry) == here:
            continue
        candidate = os.path.join(entry, "sitecustomize.py")
        if os.path.isfile(candidate):
            spec = util.spec_from_file_location("_guard_mutants_chained_sitecustomize", candidate)
            if spec is not None and spec.loader is not None:
                spec.loader.exec_module(util.module_from_spec(spec))
            return


if __name__ == "sitecustomize":
    install_redirect()
    chain_next_sitecustomize()
