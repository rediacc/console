"""`.ci/rediacc_ci/quality/gate_args.py`: the shared refusal of an argument a gate does not take.

THE FAILURE THIS GUARDS. `npm run check:ci-record-paths -- --update` exited 0 having done nothing, and 138 sibling entry points read `sys.argv` the same way: they ask about the flags they know and never look at what is left. The helper is the one place the contract lives, so these controls pin it in both directions: what must be refused (an unknown argument, a valued flag with no value, a value that is itself a flag, a bare argument where none is taken) and what must NOT be (every declared switch, valued flag, `--flag=value` spelling and positional).

A control that only refuses would pass a helper that refuses everything, and the adoption test next door would then see rc 2 from a gate that cannot run at all. The accepting half is the control for that.
"""

import importlib.util
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

HELPER = paths.repo_root() / ".ci" / "rediacc_ci" / "quality" / "gate_args.py"
#: The name the entry points under .ci/scripts/quality import it by.
ENTRY_ALIAS = paths.repo_root() / ".ci" / "scripts" / "quality" / "_gate_args.py"


def _load():
    name = "gate_args_under_test"
    spec = importlib.util.spec_from_file_location(name, HELPER)
    if spec is None or spec.loader is None:
        refusal = "cannot load %s: the helper under test is missing or unreadable" % HELPER
        raise ImportError(refusal)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GA = _load()


def test_an_unknown_argument_is_refused_by_name(gate):
    msg = GA.problem(["--update"], switches=("--selftest", "--write-baseline"))
    gate.assert_contains(msg, "unknown argument '--update'", "the offender is named")
    gate.assert_contains(msg, "--selftest, --write-baseline", "the accepted set is named")
    gate.log_pass("an unknown flag is named together with the accepted set")
    late = GA.problem(["--selftest", "--typo"], switches=("--selftest",))
    gate.assert_contains(late, "'--typo'", "an unknown flag after a known one is still refused")
    gate.log_pass("an unknown flag after a known flag is still refused")


def test_a_gate_that_takes_nothing_refuses_everything(gate):
    msg = GA.problem(["--selftest"])
    gate.assert_contains(msg, "accepted: no arguments", "an empty declaration says so")
    gate.assert_contains(GA.problem(["x"]), "unknown argument 'x'", "a bare argument is refused")
    gate.log_pass("an entry point declaring nothing refuses any argument")


def test_a_valued_flag_with_no_value_is_refused(gate):
    kwargs = {"switches": ("--selftest",), "valued": ("--root",)}
    msg = GA.problem(["--root"], **kwargs)
    gate.assert_contains(msg, "--root needs a value", "a trailing valued flag is refused")
    swallowed = GA.problem(["--root", "--selftest"], **kwargs)
    gate.assert_contains(
        swallowed, "--root needs a value", "a flag is not accepted as the value of another"
    )
    gate.log_pass("a valued flag without a value is refused, and never eats the next flag")


def test_the_declared_arguments_parse(gate):
    got = GA.scan(
        ["--selftest", "--root", "/tmp/x", "--lock=l.json", "a.md"],
        ("--selftest",),
        ("--root",),
        ("--lock",),
        "<path>",
    )
    gate.assert_eq(got[3], "", "no problem is reported for a declared set")
    gate.assert_eq(sorted(got[0]), ["--selftest"], "the switch is seen")
    gate.assert_eq(got[1], {"--root": "/tmp/x", "--lock": "l.json"}, "both value spellings parse")
    gate.assert_eq(got[2], ["a.md"], "the bare argument is a positional")
    gate.log_pass("switches, valued flags, the equals spelling and positionals all parse")
    gate.assert_eq(
        GA.problem([], switches=("--selftest",)), "", "no argument at all is always accepted"
    )
    gate.log_pass("the bare run is accepted")


def test_equals_is_refused_for_a_flag_that_only_reads_the_space_form(gate):
    msg = GA.problem(["--root=/x"], valued=("--root",))
    gate.assert_contains(msg, "unknown argument '--root=/x'", "--root=/x would be ignored")
    gate.log_pass("--flag=value is refused unless the module reads that spelling")


def test_a_positional_is_refused_unless_declared_and_a_dash_is_never_one(gate):
    gate.assert_contains(GA.problem(["a.md"]), "unknown argument 'a.md'", "undeclared positional")
    msg = GA.problem(["-x"], positional="<path>")
    gate.assert_contains(msg, "unknown argument '-x'", "a dashed word is not a positional")
    gate.log_pass("a positional needs its declaration, and an unknown flag never passes as one")


def test_parse_exits_2_on_stderr_and_returns_the_argv_otherwise(gate):
    probe = (
        "import sys; sys.path.insert(0, %r); from rediacc_ci.quality import gate_args as g; "
        "p = g.parse('check_x.py', sys.argv[1:], switches=('--selftest',)); print(p.argv)"
        % str(paths.repo_root() / ".ci")
    )
    refused = harness.run([sys.executable, "-c", probe, "--definitely-not-a-flag"])
    gate.assert_exit_code(2, refused.rc, "an unknown argument exits 2")
    gate.assert_contains(refused.err, "check_x.py: unknown argument", "the refusal is on stderr")
    gate.assert_eq(refused.out, "", "nothing is printed on stdout")
    gate.log_pass("parse exits 2 with the refusal on stderr and nothing on stdout")
    accepted = harness.run([sys.executable, "-c", probe, "--selftest"])
    gate.assert_exit_code(0, accepted.rc, "a declared switch exits 0")
    gate.assert_contains(accepted.out, "['--selftest']", "the argv comes back untouched")
    gate.log_pass("parse hands a valid argv back unchanged")


def test_a_variadic_flag_takes_every_value_up_to_the_next_flag(gate):
    kwargs = {"switches": ("--report",), "variadic": ("--paths",)}
    got = GA.scan(
        ["--paths", "a.py", "b/", "--report", "--paths", "c/*.sh"],
        ("--report",),
        (),
        (),
        None,
        ("--paths",),
    )
    gate.assert_eq(got[3], "", "a repeated variadic flag parses")
    gate.assert_eq(got[1], {"--paths": "c/*.sh"}, "the last occurrence is the one recorded")
    gate.log_pass("a variadic flag consumes bare values and stops at the next --flag")
    gate.assert_contains(
        GA.problem(["--paths", "--report"], **kwargs), "--paths needs a value", "needs one value"
    )
    gate.assert_contains(
        GA.problem(["stray", "--paths", "a"], **kwargs),
        "unknown argument 'stray'",
        "a bare word before it is not taken",
    )
    gate.log_pass("a variadic flag needs one value, and does not adopt an earlier bare word")


def test_the_entry_alias_imports_the_package_helper(gate):
    """An entry point that runs a module by path imports `_gate_args` beside `_cipath`; it must be the package helper, not a second copy."""
    probe = (
        "import sys; sys.path[:0] = [%r, %r]; import _gate_args, rediacc_ci.quality.gate_args as g; "
        "print(_gate_args.parse is g.parse and _gate_args.problem is g.problem)"
        % (str(ENTRY_ALIAS.parent), str(paths.repo_root() / ".ci"))
    )
    got = harness.run([sys.executable, "-c", probe])
    gate.assert_exit_code(0, got.rc, "the alias imports")
    gate.assert_eq(got.out.strip(), "True", "the alias re-exports the package functions")
    gate.assert_eq(
        (ENTRY_ALIAS.parent / "_cipath.py").is_file(), True, "the alias sits beside _cipath.py"
    )
    gate.log_pass("the entry alias is the package helper, on every entry point's sys.path[0]")
