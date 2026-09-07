"""`python3 -m rediacc_ci` -- the package CLI, driven as a real command.

WHY THESE CASES RUN A PROCESS RATHER THAN CALLING `main()`. Three of the four
things this CLI promises are STREAM facts: help goes to stdout and exits 0, the
no-verb path writes stderr and exits non-zero, and neither of them is a
traceback. A combined capture cannot tell those apart -- a program printing its
usage error on stdout looks identical -- and this repository has been bitten by
exactly that shape more than once. So every case here reads stdout and stderr
SEPARATELY, from a real `python3 -m rediacc_ci`.

WHY THERE IS A FIXTURE PACKAGE. `rediacc_ci.__main__.VERBS` is empty and must
stay empty until a verb genuinely moves off bash (see the module docstring), so
there is no registered verb to dispatch and the argument-passthrough contract --
the one thing a future port depends on and cannot easily re-derive -- would be
untested. `_fixture` therefore builds a throwaway package around a COPY of the
real `__main__.py` with one probe verb planted in place of the empty tuple. The
copy is the production file byte for byte apart from that line, and the planting
is asserted to have happened, so a fixture that stopped registering anything
fails rather than passing on nothing.

THE CONTROLS PLANT DEFECTS IN THAT SAME COPY. `test_control_*` below break the
passthrough slice and the help stream and require the corresponding assertion to
notice. An assertion nobody has seen fail is not yet evidence of anything, and
these two are the ones whose failure mode is silence.
"""

import json
import pathlib
import shlex
import subprocess
import sys

import pytest

from rediacc_ci import __main__ as cli
from rediacc_ci import paths
from rediacc_ci.core import ports
from rediacc_ci.tests import differential as diff

REAL_MAIN = pathlib.Path(cli.__file__)

# The three lines the fixtures rewrite. Each is asserted to have matched, so a
# refactor that changes a spelling reds these tests instead of quietly turning
# them into a run of the unmodified file.
TABLE_LINE = "VERBS: tuple[Verb, ...] = ()"
PROBE_TABLE = 'VERBS: tuple[Verb, ...] = (Verb("probe", "print the argv it got", "probe"),)'
SLICE_LINE = "    rest = list(argv[1:])"
BROKEN_SLICE_LINE = "    rest = list(argv)"
HELP_LINE = "        print(format_help(registry))"
BROKEN_HELP_LINE = "        print(format_help(registry), file=sys.stderr)"

# The handler under test's microscope: it prints the argv list it was handed, as
# JSON, so the assertion is about a LIST and not about a re-split string. A
# space inside one element is the case that a naive `" ".join` proof would miss.
PROBE_SOURCE = """\
import json


def main(argv):
    print(json.dumps(argv))
    return 0
"""

WANT_ARGV = ["--flag", "a b"]


def _fixture(tmp_path, *, main_source: str | None = None) -> pathlib.Path:
    """A throwaway `rediacc_ci` package with one probe verb. Returns its parent.

    `main_source` defaults to the real file; the controls pass a broken variant.
    """
    source = REAL_MAIN.read_text(encoding="utf-8") if main_source is None else main_source
    planted = source.replace(TABLE_LINE, PROBE_TABLE)
    assert planted != source, (
        "the verb table's spelling changed; this fixture registered nothing and "
        "every dispatch case below would have run against an empty table"
    )

    root = tmp_path / "pkgroot"
    pkg = root / "rediacc_ci"
    pkg.mkdir(parents=True)
    # No re-exports, exactly like the real __init__: the fixture must not need
    # any module the real package happens to have.
    (pkg / "__init__.py").write_text("__all__: list[str] = []\n", encoding="utf-8")
    (pkg / "__main__.py").write_text(planted, encoding="utf-8")
    # `probe` is a TOP-LEVEL module, not `rediacc_ci.probe`: resolving it proves
    # the dotted name in the table is what gets imported, rather than something
    # the package would have pulled in anyway.
    (root / "probe.py").write_text(PROBE_SOURCE, encoding="utf-8")
    return root


def _run(args, *, root: pathlib.Path | None = None, cwd=None):
    """`python3 -m rediacc_ci <args>`; returns (rc, stdout, stderr) separately.

    A list argv, so nothing here depends on shell quoting -- the bash spelling
    gets its own case below, which is where quoting is the thing under test.
    """
    pythonpath = str(paths.ci_dir()) if root is None else str(root)
    env = diff.env_for(PYTHONPATH=pythonpath, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd is not None else str(paths.repo_root()),
        timeout=diff.DEFAULT_TIMEOUT,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# the table is data, and it is introspectable
# ---------------------------------------------------------------------------


def test_the_verb_table_is_data_with_a_name_accessor() -> None:
    """`VERBS` is a tuple of `Verb` rows and `names()` derives from it."""
    assert isinstance(cli.VERBS, tuple)
    for verb in cli.VERBS:
        assert isinstance(verb, cli.Verb)
        assert verb.name
        assert verb.module
        assert verb.entry
    assert cli.names() == [verb.name for verb in cli.VERBS]
    # The accessor reads the table it is GIVEN, which is what makes the fixture
    # and every dispatch case below possible.
    row = cli.Verb("probe", "s", "probe")
    assert cli.names((row,)) == ["probe"]


def test_help_is_derived_from_the_table_not_written_twice() -> None:
    """Every registered name appears in the help; an empty table says so."""
    rc, out, err = _run(["--help"])
    assert rc == 0, err
    assert err == "", "help must not write to stderr"
    assert "usage:" in out
    for verb in cli.VERBS:
        assert verb.name in out, verb.name
    if not cli.VERBS:
        # Vacuity guard for the loop above: with an empty table it asserts
        # nothing, so the empty state has to be asserted explicitly.
        assert "none yet" in out
    assert (
        cli.format_help((cli.Verb("probe", "print the argv it got", "probe"),)).count("probe") >= 1
    )


def test_h_is_the_same_help_on_the_same_stream() -> None:
    rc_long, out_long, err_long = _run(["--help"])
    rc_short, out_short, err_short = _run(["-h"])
    assert (rc_long, err_long) == (0, "")
    assert (rc_short, err_short) == (0, "")
    assert out_short == out_long


# ---------------------------------------------------------------------------
# the two error paths: a message, a stream, an exit code, and no traceback
# ---------------------------------------------------------------------------


def test_no_verb_is_a_usage_error_on_stderr_and_not_a_traceback() -> None:
    rc, out, err = _run([])
    assert rc != 0
    assert rc == cli.EXIT_USAGE
    assert out == "", "a usage error must not land on stdout"
    assert "no verb given" in err
    assert "--help" in err
    assert "Traceback" not in err


def test_an_unknown_verb_names_the_verb_and_the_known_ones() -> None:
    rc, out, err = _run(["definitely-not-a-verb"])
    assert rc != 0
    assert rc == cli.EXIT_USAGE
    assert out == ""
    assert "definitely-not-a-verb" in err
    assert "Traceback" not in err
    for verb in cli.VERBS:
        assert verb.name in err, verb.name
    if not cli.VERBS:
        assert "no verbs are registered" in err


def test_an_unknown_verb_lists_the_registered_ones(tmp_path) -> None:
    """The other direction of the case above, against a NON-empty table."""
    root = _fixture(tmp_path)
    rc, out, err = _run(["nope"], root=root, cwd=tmp_path)
    assert rc == cli.EXIT_USAGE
    assert out == ""
    assert "nope" in err
    assert "known verbs: probe" in err


# ---------------------------------------------------------------------------
# argument passthrough: the contract every future port depends on
# ---------------------------------------------------------------------------


def test_argv_reaches_the_handler_exactly(tmp_path) -> None:
    """`<verb> -- --flag "a b"` arrives as ['--flag', 'a b'] -- the LIST."""
    root = _fixture(tmp_path)
    rc, out, err = _run(["probe", "--", "--flag", "a b"], root=root, cwd=tmp_path)
    assert rc == 0, err
    assert err == ""
    assert json.loads(out) == WANT_ARGV


def test_the_separator_is_optional_and_only_the_first_one_is_eaten(tmp_path) -> None:
    """One `--` right after the verb is this dispatcher's; the rest are argv."""
    root = _fixture(tmp_path)
    _rc, without, _err = _run(["probe", "--flag", "a b"], root=root, cwd=tmp_path)
    assert json.loads(without) == WANT_ARGV

    _rc, nested, _err = _run(["probe", "--", "--", "-x", ""], root=root, cwd=tmp_path)
    assert json.loads(nested) == ["--", "-x", ""]


def test_the_shell_spelling_delivers_the_same_list(tmp_path) -> None:
    """The run.sh path: a real bash command line, quotes and all.

    `run.sh` forwards `"$@"`, so the argv this program sees is whatever bash
    built. A case that only ever calls `subprocess` with a list would pass while
    the quoted element was being re-split somewhere in between.
    """
    root = _fixture(tmp_path)
    script = "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=%s python3 -m rediacc_ci probe -- --flag %s" % (
        shlex.quote(str(root)),
        shlex.quote("a b"),
    )
    rc, out, err = diff.bash_streams(script, env=diff.env_for(), cwd=str(tmp_path))
    assert rc == 0, err
    assert json.loads(out) == WANT_ARGV


def test_the_handler_is_resolved_lazily_by_dotted_name(capsys) -> None:
    """A row pointing at a REAL module in this package dispatches to it.

    `rediacc_ci.core.ports derive-slot` is a genuine argv handler with a
    deterministic answer, so this exercises resolution against production code
    rather than against another fixture.
    """
    row = cli.Verb("ports", "port helpers", "rediacc_ci.core.ports")
    rc = cli.main(["ports", "derive-slot", "a-key"], table=(row,))
    assert rc == 0
    assert capsys.readouterr().out.strip() == str(ports.derive_slot("a-key"))


def test_a_handler_returning_none_is_a_success() -> None:
    row = cli.Verb("quiet", "returns nothing", "rediacc_ci.tests.test_main", "_returns_none")
    assert cli.main(["quiet"], table=(row,)) == 0


def test_a_handler_returning_a_non_code_is_refused(capsys) -> None:
    row = cli.Verb("weird", "returns a string", "rediacc_ci.tests.test_main", "_returns_a_string")
    rc = cli.main(["weird"], table=(row,))
    assert rc == 1
    assert "not an exit code" in capsys.readouterr().err


def test_a_broken_registration_raises_rather_than_reporting_a_typo() -> None:
    """An unimportable module is the table's bug, not the user's.

    Reported as a usage error it would read as "unknown verb" and send whoever
    typed it looking for a spelling mistake that does not exist.
    """
    row = cli.Verb("ghost", "points nowhere", "rediacc_ci.no_such_module")
    with pytest.raises(ImportError):
        cli.main(["ghost"], table=(row,))
    row = cli.Verb("ghost", "points at no entry", "rediacc_ci.tests.test_main", "_no_such_entry")
    with pytest.raises(AttributeError):
        cli.main(["ghost"], table=(row,))


def _returns_none(argv):  # noqa: ARG001 -- the handler signature is the point
    return None


def _returns_a_string(argv):  # noqa: ARG001 -- the handler signature is the point
    return "fine"


# ---------------------------------------------------------------------------
# CONTROLS. Each plants one defect and requires an assertion above to fire.
# ---------------------------------------------------------------------------


def test_control_the_fixture_really_runs_the_copy(tmp_path) -> None:
    """The probe verb exists ONLY in the fixture, never in the real package."""
    root = _fixture(tmp_path)
    _rc, fixture_help, _err = _run(["--help"], root=root, cwd=tmp_path)
    assert "probe" in fixture_help
    _rc, real_help, _err = _run(["--help"])
    assert "probe" not in real_help
    assert "probe" not in cli.names()


def test_control_the_passthrough_assertion_can_fail(tmp_path) -> None:
    """Forward the WHOLE argv and the exactness check must notice."""
    source = REAL_MAIN.read_text(encoding="utf-8")
    broken = source.replace(SLICE_LINE, BROKEN_SLICE_LINE)
    assert broken != source, "the slice line's spelling changed; this control planted nothing"

    root = _fixture(tmp_path, main_source=broken)
    rc, out, err = _run(["probe", "--", "--flag", "a b"], root=root, cwd=tmp_path)
    assert rc == 0, err
    # The exact wrong answer, not merely "different": this names how a broken
    # dispatcher fails, so the control cannot pass because of some third fault.
    assert json.loads(out) == ["probe", "--", "--flag", "a b"]
    assert json.loads(out) != WANT_ARGV


def test_control_the_help_stream_assertion_can_fail(tmp_path) -> None:
    """Print the help on stderr and the stream check must notice."""
    source = REAL_MAIN.read_text(encoding="utf-8")
    broken = source.replace(HELP_LINE, BROKEN_HELP_LINE)
    assert broken != source, "the help print's spelling changed; this control planted nothing"

    root = _fixture(tmp_path, main_source=broken)
    rc, out, err = _run(["--help"], root=root, cwd=tmp_path)
    assert rc == 0
    assert out == "", "the planted defect did not move the help off stdout"
    assert "usage:" in err
