"""`rediacc_ci.core.env` against real files, and against the bash it replaces.

WHY THE COMPARISON IS AGAINST A LIVE `set -a; source` AND NOT A TABLE OF
EXPECTED STRINGS. The module's contract is "what bash would have read, minus
two named divergences". A table of hand-written expectations proves only that
the author's belief about bash matches the author's code; running bash proves
the belief. So the awkward cases go through `differential.bash_streams`, and the
two DELIBERATE divergences (an unquoted `#`, and whitespace around a value) are
the only places a case asserts a difference -- stated as a difference, with the
bash answer written down next to it.

EVERY CASE HERE CARRIES ITS OTHER DIRECTION. That is not a style preference:
a redaction test that only proves masking happens passes when the function
returns the empty string, and a CRLF test that only proves no carriage return
survives passes when the parser drops the value. Where the negative direction is
not obvious from the assertion it is a separate `..._control_...` case, named so
that deleting it is visible.
"""

import os
import re
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import env
from rediacc_ci.tests import differential as diff

# The awkward file. Every line here exists because some spelling of it is in a
# real .env or a real pins file in this tree: `export ` from a shell profile,
# quoted values from account.sh, `=` inside base64 from the crypto keys, blank
# and comment lines from account_env_add_if_missing's "\n# comment" writer.
AWKWARD = """\
# a leading comment

SIMPLE=plain
export EXPORTED=viaexport
exported=notaprefix
QUOTED_D="two words"
QUOTED_S='two words'
EQUALS=a=b=c
BASE64=aGVsbG8gd29ybGQ=
   INDENTED=indented
EMPTY=
DUPLICATE=first
DUPLICATE=second
"""

# The keys AWKWARD is expected to define. A SET, compared as a set, so the
# assertion fails both when a key stops parsing and when a new one appears --
# and so there is no hand-typed count anywhere in this file.
AWKWARD_KEYS = {
    "SIMPLE",
    "EXPORTED",
    "exported",
    "QUOTED_D",
    "QUOTED_S",
    "EQUALS",
    "BASE64",
    "INDENTED",
    "EMPTY",
    "DUPLICATE",
}


def _write(tmp_path, text: str, name: str = "dotenv", newline: str = "\n"):
    path = tmp_path / name
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def _bash_source(path) -> dict[str, str]:
    """What `set -a; source <path>` puts in the environment, as a mapping.

    The two-stage `env` diff is the reliable shape: bash's own variables are
    numerous and not all of them are stable, so the BEFORE set is subtracted
    rather than filtered by a name list that would go stale.
    """
    script = (
        "env | sort > /tmp/.rediacc_before.$$\n"
        "set -a\n"
        "source %s\n"
        "set +a\n"
        "env | sort > /tmp/.rediacc_after.$$\n"
        "comm -13 /tmp/.rediacc_before.$$ /tmp/.rediacc_after.$$\n"
        "rm -f /tmp/.rediacc_before.$$ /tmp/.rediacc_after.$$\n"
    ) % _q(str(path))
    rc, out, err = diff.bash_streams(script, env=diff.env_for())
    assert rc == 0, err
    pairs = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            pairs[key] = value
    return pairs


# ---------------------------------------------------------------------------
# the differential: what bash reads, this reads
# ---------------------------------------------------------------------------


def test_parse_agrees_with_bash_source_on_every_awkward_shape(tmp_path) -> None:
    """The port and `set -a; source` produce the same mapping for AWKWARD.

    The keys are compared as a SET first, so a parser that returned {} would
    fail here rather than trivially agreeing on an empty intersection.
    """
    path = _write(tmp_path, AWKWARD)
    ours = env.parse(AWKWARD)
    theirs = _bash_source(path)

    assert set(ours) == AWKWARD_KEYS
    assert set(theirs) >= AWKWARD_KEYS, "the fixture stopped exercising bash"
    for key in AWKWARD_KEYS:
        assert ours[key] == theirs[key], key


def test_control_the_differential_can_fail(tmp_path) -> None:
    """A PLANTED DEFECT must make the comparison above red.

    Without this, `test_parse_agrees_with_bash_source...` could be passing
    because both sides return the same wrong thing, or because the comparison
    loop iterates over nothing. The defect here is the classic one: split on the
    LAST `=` instead of the first.
    """
    path = _write(tmp_path, AWKWARD)
    theirs = _bash_source(path)
    broken = {}
    for line in AWKWARD.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.strip().rpartition("=")
            broken[key.removeprefix("export ")] = value
    assert theirs["EQUALS"] == "a=b=c"
    # The defect does not merely get the value wrong, it invents a KEY: the
    # left-hand side becomes everything before the LAST `=`. Both halves are
    # asserted, because a comparison that only checked the value would pass on a
    # mapping whose keys had all silently changed.
    assert "EQUALS" not in broken
    assert broken["EQUALS=a=b"] == "c"


# ---------------------------------------------------------------------------
# the parsing rules, each with its opposite
# ---------------------------------------------------------------------------


def test_export_prefix_is_stripped_and_a_key_called_exported_is_not() -> None:
    """Both halves of the same regex, because a lazy one gets exactly this wrong."""
    pairs = env.parse(AWKWARD)
    assert pairs["EXPORTED"] == "viaexport"
    assert pairs["exported"] == "notaprefix"
    assert "ed" not in pairs


def test_equals_inside_a_value_survives_and_so_does_base64_padding() -> None:
    pairs = env.parse(AWKWARD)
    assert pairs["EQUALS"] == "a=b=c"
    assert pairs["BASE64"] == "aGVsbG8gd29ybGQ="


def test_the_last_assignment_wins() -> None:
    """`rdc.sh:247` spells this `tail -1`; the control is that both lines exist."""
    assert "DUPLICATE=first" in AWKWARD
    assert env.parse(AWKWARD)["DUPLICATE"] == "second"


def test_blank_and_comment_lines_produce_no_keys() -> None:
    """And the control: the comment's own text must not appear as a value."""
    pairs = env.parse(AWKWARD)
    assert "#" not in "".join(pairs)
    assert "a leading comment" not in "".join(pairs.values())


def test_quotes_are_stripped_and_the_inner_text_kept() -> None:
    pairs = env.parse(AWKWARD)
    assert pairs["QUOTED_D"] == "two words"
    assert pairs["QUOTED_S"] == "two words"
    assert '"' not in pairs["QUOTED_D"]


def test_single_quotes_keep_a_backslash_and_double_quotes_eat_one() -> None:
    """bash's rule, both directions in one case.

    Inside single quotes nothing is special. Inside double quotes a backslash is
    special before exactly `$`, a backtick, `"` and another backslash -- so
    `\\n` stays two characters and `\\"` becomes one.
    """
    pairs = env.parse('A=\'lit\\n\'\nB="esc\\n"\nC="q\\"uote"\nD="d\\\\d"\n')
    assert pairs["A"] == "lit\\n"
    assert pairs["B"] == "esc\\n"
    assert pairs["C"] == 'q"uote'
    assert pairs["D"] == "d\\d"


def test_an_unterminated_quote_is_taken_literally_not_raised() -> None:
    """The documented tolerance, and the control that a TERMINATED one is not."""
    assert env.parse('A="abc\n')["A"] == '"abc'
    assert env.parse('A="abc"\n')["A"] == "abc"


def test_a_hash_inside_an_unquoted_value_is_kept(tmp_path) -> None:
    """DIVERGENCE 1, asserted AS a divergence with bash's answer alongside.

    bash ends the assignment at the space-preceded `#`; this keeps the whole
    value. Writing the bash answer down here is what stops a future reader
    "fixing" the divergence back without knowing it was chosen.
    """
    text = "A=val#frag\nB=val # note\n"
    path = _write(tmp_path, text)
    theirs = _bash_source(path)
    ours = env.parse(text)

    assert ours["A"] == "val#frag"
    assert theirs["A"] == "val#frag", "bash agrees when the # is not space-preceded"
    assert theirs["B"] == "val", "bash truncates here"
    assert ours["B"] == "val # note", "and this deliberately does not"


def test_whitespace_around_a_value_is_stripped(tmp_path) -> None:
    """DIVERGENCE 2, and bash's real answer is worse than the docstring assumed.

    `A=  spaced  ` is not an assignment to bash at all. It is the command
    `spaced` with a TEMPORARY assignment prefix `A=`, so the variable exists
    only for that command's environment and the shell keeps nothing. Measured
    here rather than reasoned about, which is how the module docstring's claim
    ("bash reads it as an empty assignment followed by an attempt to run
    `value`") got its second half right and its first half wrong.

    The control is the key that IS in the bash mapping: without it, `"A" not in
    theirs` would also pass if `_bash_source` returned nothing at all.
    """
    text = "A=  spaced  \nB=kept\n"
    path = _write(tmp_path, text)
    theirs = _bash_source(path)
    assert env.parse(text)["A"] == "spaced"
    assert "A" not in theirs, "bash keeps nothing; the prefix assignment is temporary"
    assert theirs["B"] == "kept"


def test_crlf_and_lf_files_parse_identically(tmp_path) -> None:
    """The CRLF requirement, with the LF file as its own control.

    A parser that dropped every value would satisfy "no carriage return
    survives"; it could not satisfy "identical to the LF answer, which is
    non-empty".
    """
    lf = env.read_pairs(_write(tmp_path, AWKWARD, "lf.env", newline="\n"))
    crlf = env.read_pairs(_write(tmp_path, AWKWARD, "crlf.env", newline="\r\n"))
    assert crlf == lf
    assert set(crlf) == AWKWARD_KEYS
    assert not any("\r" in value for value in crlf.values())
    assert crlf["SIMPLE"] == "plain"


def test_skipped_lines_on_a_crlf_file_carry_no_carriage_return() -> None:
    """CRLF reaches the DIAGNOSTIC path too, not just the values.

    `skipped` reports the text of a line, and a reported line ending in an
    invisible carriage return does not match what the reader sees in their
    editor. Values are covered by `test_crlf_and_lf_files_parse_identically`;
    this is the other consumer of `_lines`.

    WHAT THIS CASE MEASURED, since it changed the module. It was written to
    catch the deletion of a `rstrip` in `_lines` and it did not, because
    `str.splitlines()` had already consumed the carriage return: the rstrip was
    dead code and is now gone. The case is kept because it still fails against
    the mistake that is actually available -- reading lines with
    `text.split("\n")`, which keeps the CR -- and because it is the only case
    that looks at `skipped` on a Windows-written file at all.

    The LF file is the control: without it, an assertion that no CR appears
    would also pass on an empty result.
    """
    assert env.skipped("GOOD=1\nBAD LINE\n") == [(2, "BAD LINE")]
    assert env.skipped("GOOD=1\r\nBAD LINE\r\n") == [(2, "BAD LINE")]


def test_a_utf8_bom_does_not_rename_the_first_key(tmp_path) -> None:
    path = tmp_path / "bom.env"
    path.write_bytes(b"\xef\xbb\xbfFIRST=1\nSECOND=2\n")
    pairs = env.read_pairs(path)
    assert set(pairs) == {"FIRST", "SECOND"}
    assert pairs["FIRST"] == "1"


def test_skipped_lines_are_reported_and_a_clean_file_reports_none() -> None:
    """Both directions of the same function, which is the point of having it."""
    assert env.skipped(AWKWARD) == []
    reported = env.skipped("GOOD=1\nthis is not an assignment\n2BAD=x\n")
    assert [line for _lineno, line in reported] == ["this is not an assignment", "2BAD=x"]
    assert [lineno for lineno, _line in reported] == [2, 3]


# ---------------------------------------------------------------------------
# missing, unreadable, and the difference between them
# ---------------------------------------------------------------------------


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    assert env.read_pairs(tmp_path / "nope.env") == {}
    assert env.env_file_load(tmp_path / "nope.env", {}) == {}


def test_a_missing_file_is_an_error_when_the_caller_says_so(tmp_path) -> None:
    """The control for the case above: the tolerance is a choice, not an inability."""
    with pytest.raises(env.EnvFileError):
        env.read_pairs(tmp_path / "nope.env", missing_ok=False)


def test_a_directory_in_place_of_a_file_raises(tmp_path) -> None:
    """Unreadable, in the one spelling that is unreadable even to root.

    A chmod-000 case cannot fail for a process running as root, so the suite
    would go quietly vacuous in a container that runs as uid 0. A directory
    raises IsADirectoryError for everyone.
    """
    target = tmp_path / "adir"
    target.mkdir()
    with pytest.raises(env.EnvFileError):
        env.read_pairs(target)


def test_an_unreadable_file_raises_rather_than_reading_as_empty(tmp_path) -> None:
    """chmod 000. Guarded by an actual readability probe, never skipped.

    Skipping would be the easy answer and it is the wrong one: a skip in a suite
    whose whole subject is "absence must not be confused with failure" is itself
    an absence confused with a pass. So the root case asserts the OTHER
    invariant -- that a file root can read, this module also reads.
    """
    path = _write(tmp_path, "SECRETISH=value\n", "locked.env")
    path.chmod(0o000)
    try:
        try:
            with open(path, encoding="utf-8") as handle:
                handle.read()
            readable = True
        except OSError:
            readable = False
        if readable:
            assert env.read_pairs(path) == {"SECRETISH": "value"}
        else:
            with pytest.raises(env.EnvFileError):
                env.read_pairs(path)
    finally:
        path.chmod(0o600)


# ---------------------------------------------------------------------------
# precedence
# ---------------------------------------------------------------------------


def test_the_shell_wins_over_the_file(tmp_path) -> None:
    path = _write(tmp_path, "PORT=3000\nOTHER=file\n")
    merged = env.env_file_load(path, {"PORT": "4900"})
    assert merged["PORT"] == "4900"
    assert merged["OTHER"] == "file"
    assert env.overridden(path, {"PORT": "4900"}) == ["PORT"]


def test_control_the_file_wins_when_the_shell_is_silent(tmp_path) -> None:
    """Without this, "shell wins" would also pass if the file were never read."""
    path = _write(tmp_path, "PORT=3000\n")
    assert env.env_file_load(path, {})["PORT"] == "3000"
    assert env.overridden(path, {}) == []


def test_an_empty_shell_value_does_not_win(tmp_path) -> None:
    """`.ci/lib/bws-env.sh:100-104`: empty is ABSENT. Non-empty is the control."""
    path = _write(tmp_path, "PORT=3000\n")
    assert env.env_file_load(path, {"PORT": ""})["PORT"] == "3000"
    assert env.env_file_load(path, {"PORT": "1"})["PORT"] == "1"


def test_apply_assigns_only_what_the_environment_lacks(tmp_path) -> None:
    path = _write(tmp_path, "A=1\nB=2\nC=3\n")
    target = {"B": "kept"}
    assigned = env.apply(path, target)
    assert assigned == ["A", "C"]
    assert target == {"A": "1", "B": "kept", "C": "3"}


def test_apply_with_names_takes_only_those(tmp_path) -> None:
    """The rdc.sh posture: a process that needs two values does not take forty-nine."""
    path = _write(tmp_path, "WANTED=yes\nSECRET_ONE=no\nSECRET_TWO=no\n")
    target: dict[str, str] = {}
    assert env.apply(path, target, names=["WANTED"]) == ["WANTED"]
    assert set(target) == {"WANTED"}


def test_env_file_load_returns_only_the_files_keys(tmp_path) -> None:
    """Not a merged copy of the environment. The control is the extra key."""
    path = _write(tmp_path, "A=1\n")
    assert set(env.env_file_load(path, {"A": "x", "UNRELATED": "y"})) == {"A"}


# ---------------------------------------------------------------------------
# the argv dispatch, driven as bash drives it
# ---------------------------------------------------------------------------


def _module(script: str, environ=None):
    full = "PYTHONPATH=%s\nexport PYTHONPATH\n%s" % (_q(str(paths.ci_dir())), script)
    return diff.bash_streams(full, env=diff.env_for(**(environ or {})))


def test_keys_verb_prints_names_in_file_order_and_no_values(tmp_path) -> None:
    path = _write(tmp_path, "ZED=zvalue\nALPHA=avalue\n")
    rc, out, err = _module("python3 -m rediacc_ci.core.env keys %s" % _q(str(path)))
    assert rc == 0, err
    assert out.split() == ["ZED", "ALPHA"]
    assert "zvalue" not in out
    assert "avalue" not in out


def test_get_verb_prints_the_value_and_exits_one_when_absent(tmp_path) -> None:
    """Both directions, because the exit code is the half rdc.sh:247 could not get."""
    path = _write(tmp_path, "REDIACC_ACCOUNT_SERVER=http://localhost:4800\n")
    rc, out, err = _module(
        "python3 -m rediacc_ci.core.env get %s REDIACC_ACCOUNT_SERVER" % _q(str(path))
    )
    assert rc == 0, err
    assert out.strip() == "http://localhost:4800"

    rc, out, _err = _module("python3 -m rediacc_ci.core.env get %s NOPE" % _q(str(path)))
    assert rc == 1
    assert out.strip() == ""


def test_export_verb_round_trips_through_eval(tmp_path) -> None:
    """The `set -a; source` replacement, proved by USING it.

    A value with a space, a single quote and a `$` is the shape that breaks a
    naive emitter, and the round trip is the only assertion that catches all
    three at once.
    """
    path = _write(tmp_path, "A=plain\nB='has space'\nC=\"do$notexpand\"\n")
    rc, out, err = _module(
        'eval "$(python3 -m rediacc_ci.core.env export %s)"\n'
        'printf "%%s\\n" "$A" "$B" "$C"' % _q(str(path))
    )
    assert rc == 0, err
    assert out.splitlines() == ["plain", "has space", "do$notexpand"]


def test_export_verb_skips_what_the_environment_already_carries(tmp_path) -> None:
    """Shell wins, all the way out through the shim. Control: the other key IS emitted."""
    path = _write(tmp_path, "TAKEN=fromfile\nFREE=fromfile\n")
    rc, out, err = _module(
        "python3 -m rediacc_ci.core.env export %s" % _q(str(path)),
        {"TAKEN": "fromshell"},
    )
    assert rc == 0, err
    assert "TAKEN" not in out
    assert "fromfile" in out
    assert "FREE" in out


def test_export_verb_with_names_emits_only_those(tmp_path) -> None:
    path = _write(tmp_path, "WANTED=yes\nACCOUNT_JWT_SECRET=leaky\n")
    rc, out, err = _module("python3 -m rediacc_ci.core.env export %s WANTED" % _q(str(path)))
    assert rc == 0, err
    assert "WANTED" in out
    assert "leaky" not in out
    assert "ACCOUNT_JWT_SECRET" not in out


def test_an_unknown_verb_and_a_missing_argument_both_refuse() -> None:
    rc, _out, err = _module("python3 -m rediacc_ci.core.env nonsense")
    assert rc == 2
    assert "unknown verb" in err
    rc, _out, err = _module("python3 -m rediacc_ci.core.env get")
    assert rc == 2
    assert "more arguments" in err


# ---------------------------------------------------------------------------
# the corpus: a real pins file, against the real bash that reads it
# ---------------------------------------------------------------------------


def test_the_real_toolchain_pins_agree_with_toolchain_pairs() -> None:
    """No fixture, no hand-typed floor: the live file and the live bash function.

    `.ci/scripts/lib/toolchain.sh:44` defines the ONLY lines it considers valid
    pins as `grep -E '^[A-Z][A-Z0-9_]*='`. This module must find at least those
    keys with those values -- and the assertion that the corpus is non-empty is
    what stops the whole case passing on a file that failed to load.
    """
    pins = paths.from_root(".devcontainer/toolchain.env")
    ours = env.read_pairs(pins, missing_ok=False)

    result = subprocess.run(
        [
            "bash",
            "-c",
            "source %s; toolchain_pairs" % _q(str(paths.from_root(".ci/scripts/lib/toolchain.sh"))),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(paths.repo_root()),
        env=diff.env_for(),
    )
    theirs = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        theirs[key] = value

    assert theirs, "toolchain_pairs produced nothing; the corpus is gone"
    assert set(theirs) <= set(ours), sorted(set(theirs) - set(ours))
    for key, value in theirs.items():
        assert ours[key] == value.strip(), key


def test_the_real_pins_file_has_no_unparsable_lines() -> None:
    """A live file is the strongest control there is on the line classifier."""
    text = paths.from_root(".devcontainer/toolchain.env").read_text(encoding="utf-8")
    assert env.skipped(text) == []
    assert env.parse(text), "the pins file parsed to nothing"


def test_control_the_pins_corpus_is_a_real_env_file() -> None:
    """Guards the two cases above against a corpus that quietly became empty.

    Derived from the file, not typed: every key the bash grep accepts must also
    match this module's own key pattern. A zero-key file fails the first line.
    """
    text = paths.from_root(".devcontainer/toolchain.env").read_text(encoding="utf-8")
    found = set(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=", text))
    assert found, "the pins corpus is empty"
    assert found <= set(env.parse(text))


def test_apply_defaults_to_the_process_environment(tmp_path) -> None:
    """`environ=None` means os.environ, and the assignment is real. Undone after."""
    path = _write(tmp_path, "REDIACC_TEST_ENV_APPLY=applied\n")
    assert "REDIACC_TEST_ENV_APPLY" not in os.environ
    try:
        assert env.apply(path) == ["REDIACC_TEST_ENV_APPLY"]
        assert os.environ["REDIACC_TEST_ENV_APPLY"] == "applied"
    finally:
        os.environ.pop("REDIACC_TEST_ENV_APPLY", None)


def test_unredacted_value_is_the_only_value_returning_helper() -> None:
    """The naming rule, asserted rather than trusted to review.

    Every public name in the module is checked against the one that is allowed
    to hand back a value. This is set-based: a NEW value-returning helper added
    without the word `unredacted` in its name fails here.
    """
    public = {name for name in dir(env) if not name.startswith("_")}
    value_returning = {name for name in public if "value" in name.lower()}
    assert value_returning == {"unredacted_value"}


def _q(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
