"""`.ci/scripts/quality/_gate_args.py`: the shared refusal of an argument a gate does not take.

THE FAILURE THIS GUARDS. `npm run check:ci-record-paths -- --update` exited 0 having done nothing, and 138 sibling entry points read `sys.argv` the same way: they ask about the flags they know and never look at what is left. The helper is the one place the contract lives, so these controls pin it in both directions: what must be refused (an unknown argument, a valued flag with no value, a value that is itself a flag, a bare argument where none is taken) and what must NOT be (every declared switch, valued flag, `--flag=value` spelling and positional).

A control that only refuses would pass a helper that refuses everything, and the adoption test next door would then see rc 2 from a gate that cannot run at all. The accepting half is the control for that.
"""

import importlib.util
import pathlib
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

HELPER = paths.repo_root() / ".ci" / "scripts" / "quality" / "_gate_args.py"


def _load():
    spec = importlib.util.spec_from_file_location("gate_args_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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
        "import sys; sys.path.insert(0, %r); import _gate_args as g; "
        "p = g.parse('check_x.py', sys.argv[1:], switches=('--selftest',)); print(p.argv)"
        % str(HELPER.parent)
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


def test_the_helper_file_is_where_the_entry_points_import_it_from(gate):
    gate.assert_eq(
        pathlib.Path(HELPER).is_file(), True, "the helper sits beside _cipath.py in the entry dir"
    )
    gate.assert_eq(
        (HELPER.parent / "_cipath.py").is_file(), True, "the sibling it is modelled on exists"
    )
    gate.log_pass("the helper lives beside _cipath.py, on every entry point's sys.path[0]")
