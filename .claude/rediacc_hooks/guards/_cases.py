"""A guard's test tables live in `tests/guard_cases/<stem>.py`; this forwards them back onto the guard module on demand.

WHY THEY MOVED (PLAN-tooling-code-reduction CR5, D5). Every hook call runs `dispatch.run_chain`, and that imports EVERY guard module of the package. Before the move about 7,500 of the package's lines were EDGE_CASES rows, fixture-world builders and their `ENVS`, unmarshalled on each call and read by nothing but the tests. The tables are test data, so they sit beside the tests.

WHY A FORWARDER AND NOT A NEW LOOKUP. The tables are read as module attributes in many places: the golden differential (`getattr(module, "EDGE_CASES", [])`, `FIXTURES`, `ENVS`), the guards' own `test-<stem>.py` suites (`G.FIXTURES[name]`), `.ci` tests, and `from rediacc_hooks.guards.<stem> import <helper>`. A module-level `__getattr__` (PEP 562) answers all of them unchanged, and it runs only for a name the module does not define, so a hook call never reaches it.

THE NAMES ARE LISTED, NOT GUESSED. `lazy("<stem>", "EDGE_CASES", ...)` forwards exactly the names that moved; any other missing attribute raises AttributeError at once, without importing the table. That keeps the registry's own probes (`getattr(module, "OWN_SUITE", False)`, the differential's `datetime` check) from importing test data, and it makes a typo an error instead of a silent fallback.
"""

import importlib

TABLES = "rediacc_hooks.tests.guard_cases"


def lazy(stem, *names):
    """A module `__getattr__` for the guard `stem` that serves `names` from `tests/guard_cases/<stem>.py`.

    The stem is written out in the guard rather than derived from `__name__`, so the guard's text names the module it imports from: a reader (and the hook-reach closure in scripts/lib/doc-providers.ts, which follows names) finds the table from the guard.
    """
    module_name = "rediacc_hooks.guards.%s" % stem
    wanted = frozenset(names)

    def forward(attr):
        if attr not in wanted:
            raise AttributeError("module %r has no attribute %r" % (module_name, attr))
        table = importlib.import_module("%s.%s" % (TABLES, stem))
        return getattr(table, attr)

    return forward
