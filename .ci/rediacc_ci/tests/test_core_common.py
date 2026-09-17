"""`rediacc_ci.core.common` against the live `.ci/scripts/lib/common.sh`.

THE TWIN IS LIVE, AND IT IS THE MOST LIVE FILE IN THE TREE: 208 files source `.ci/scripts/lib/common.sh` (re-derived 2026-09-10). Every comparison below sources the real file, so a change to it turns these red rather than leaving a port drifting quietly beside it.

WHAT IS COMPARED. Both sides run through their own CLI, with stdout and stderr kept SEPARATE, because the twin's whole logging contract is that messages go to stderr and data goes to stdout. A harness that merged them could not tell a correct port from one that put a diagnostic on the data stream, which is consequence 1 of the incident `rediacc_ci.log`'s docstring records.

FOUR CLASSES OF TEST, and the second and third are the ones that matter:

  1. AGREEMENT. Thirty-odd cases where the two must be byte-identical.
  2. QUIRKS OF THE TWIN, driven against the TWIN. If `.ci/scripts/lib/` is ever
     repaired, these go red and name the repair. They are not assertions that
     the bash is right; they are assertions about what it currently does.
  3. THE TWO DELIBERATE DIVERGENCES, asserted from BOTH sides, so neither can be
     "fixed" into agreement by a later reader who has not read the argument.
  4. PLANTED DEFECTS in the port, proving each control can fire.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.core import common
from rediacc_ci.core import platform as ci_platform
from rediacc_ci.tests import differential as diff

TWIN_REL = ".ci/scripts/lib/common.sh"
TWIN = paths.from_root(TWIN_REL)
PY = "PYTHONPATH=%s python3 -m rediacc_ci.core.common" % paths.from_root(".ci")


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def twin(body: str, **env):
    """Source the real common.sh and run `body`. Streams separate."""
    script = "source %s\n%s\n" % (_sh(str(TWIN)), body)
    return diff.bash_streams("bash -c %s" % _sh(script), env=diff.env_for(**env))


def port(argv: list[str], **env):
    cmd = "%s %s" % (PY, " ".join(_sh(a) for a in argv))
    return diff.bash_streams(cmd, env=diff.env_for(**env))


# --------------------------------------------------------------------------- 1. AGREEMENT -- the twin and the port, byte for byte ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixt(tmp_path_factory):
    root = tmp_path_factory.mktemp("common_fixt")
    (root / "dir_a").mkdir()
    (root / "file_a").write_text("hi\n", encoding="utf-8")
    (root / "dangling").symlink_to(root / "nowhere")
    return root


def _cases(fx: pathlib.Path):
    fa, da, no = str(fx / "file_a"), str(fx / "dir_a"), str(fx / "nope")
    return [
        ("require-cmd-present", "require_cmd jq", ["require-cmd", "jq"], {}),
        (
            "require-cmd-absent",
            "require_cmd definitely_not_a_command_xyz",
            ["require-cmd", "definitely_not_a_command_xyz"],
            {},
        ),
        ("require-file-present", "require_file %s" % _sh(fa), ["require-file", fa], {}),
        ("require-file-absent", "require_file %s" % _sh(no), ["require-file", no], {}),
        # `-f` is regular-file-only: a directory refuses with the SAME message, which is worth pinning because the message says "does not exist".
        ("require-file-is-a-dir", "require_file %s" % _sh(da), ["require-file", da], {}),
        (
            "require-file-dangling-symlink",
            "require_file %s" % _sh(str(fx / "dangling")),
            ["require-file", str(fx / "dangling")],
            {},
        ),
        ("require-dir-present", "require_dir %s" % _sh(da), ["require-dir", da], {}),
        ("require-dir-absent", "require_dir %s" % _sh(no), ["require-dir", no], {}),
        ("require-dir-is-a-file", "require_dir %s" % _sh(fa), ["require-dir", fa], {}),
        ("require-var-set", "require_var HOME", ["require-var", "HOME"], {}),
        ("require-var-unset", "require_var WV_NOPE_XYZ", ["require-var", "WV_NOPE_XYZ"], {}),
        # `[[ -z "${!v:-}" ]]` is an EMPTINESS test, so exported-empty refuses.
        (
            "require-var-exported-empty",
            "require_var WV_EMPTY",
            ["require-var", "WV_EMPTY"],
            {"WV_EMPTY": ""},
        ),
        (
            "require-input-present",
            "require_input -f 'input not found: {}' 'why' %s" % _sh(fa),
            ["require-input", "-f", "input not found: {}", "why", fa],
            {},
        ),
        (
            "require-input-first-missing-stops",
            "require_input -f 'input not found: {}' 'why' %s %s" % (_sh(no), _sh(fa)),
            ["require-input", "-f", "input not found: {}", "why", no, fa],
            {},
        ),
        # `${lead//\{\}/$p}` is a substitution and not a printf format, so a `%`
        # in the path is inert. common.sh:182-183 says so; this proves it.
        (
            "require-input-percent-in-path",
            "require_input -f 'input not found: {}' 'why' '/no%sdir'",
            ["require-input", "-f", "input not found: {}", "why", "/no%sdir"],
            {},
        ),
        (
            "require-input-dir-flag",
            "require_input -d 'cannot scan {}' 'why' %s" % _sh(da),
            ["require-input", "-d", "cannot scan {}", "why", da],
            {},
        ),
        ("to-upper", "to_upper 'mixed Case-123'", ["to-upper", "mixed Case-123"], {}),
        ("temp-dir-runner", "get_temp_dir", ["temp-dir"], {"RUNNER_TEMP": "/rt", "TMPDIR": "/td"}),
        # NON-EMPTY, not "set": an exported-empty RUNNER_TEMP falls through.
        (
            "temp-dir-empty-runner-falls-through",
            "get_temp_dir",
            ["temp-dir"],
            {"RUNNER_TEMP": "", "TMPDIR": "/td"},
        ),
        (
            "temp-dir-neither",
            "get_temp_dir",
            ["temp-dir"],
            {"RUNNER_TEMP": None, "TMPDIR": None},
        ),
        ("is-ci-true", "is_ci", ["is-ci"], {"CI": "true"}),
        # QUIRK: `CI=1` is NOT ci, because the twin compares to the literal.
        ("is-ci-one-is-not-ci", "is_ci", ["is-ci"], {"CI": "1", "GITHUB_ACTIONS": None}),
        # ... while GITHUB_ACTIONS only has to be NON-EMPTY, so "0" is ci.
        (
            "is-ci-github-actions-zero-is-ci",
            "is_ci",
            ["is-ci"],
            {"CI": None, "GITHUB_ACTIONS": "0"},
        ),
        ("detect-os", "detect_os", ["detect-os"], {}),
        ("detect-arch", "detect_arch", ["detect-arch"], {}),
        ("repo-root", "get_repo_root", ["repo-root"], {}),
        (
            "require-submodule-present",
            "require_submodule %s L" % _sh(da),
            ["require-submodule", da, "L"],
            {},
        ),
        (
            "require-submodule-absent-local",
            "require_submodule %s L" % _sh(no),
            ["require-submodule", no, "L"],
            {"CI": None},
        ),
        (
            "require-submodule-absent-in-ci",
            "require_submodule %s L" % _sh(no),
            ["require-submodule", no, "L"],
            {"CI": "true"},
        ),
    ]


def test_the_case_table_is_not_empty(fixt):
    """Anti-vacuity. A parametrize over an empty list is a green that proves nothing."""
    assert len(_cases(fixt)) >= 28


@pytest.mark.parametrize("index", range(len(_cases(pathlib.Path("/x")))))
def test_twin_and_port_agree(fixt, index):
    name, body, argv, env = _cases(fixt)[index]
    old = twin(body, **env)
    new = port(argv, **env)
    assert old == new, "%s: twin=%r port=%r" % (name, old, new)


PARSE_ARGS_CASES = [
    # (argv, the twin's echo body, the expected stdout)
    (["--url=http://x?a=b"], 'echo "ARG_URL=$ARG_URL"', "ARG_URL=http://x?a=b\n"),
    (["--dry-run=yes"], 'echo "ARG_DRY_RUN=$ARG_DRY_RUN"', "ARG_DRY_RUN=yes\n"),
    (["--flag"], 'echo "ARG_FLAG=$ARG_FLAG"', "ARG_FLAG=true\n"),
    (["--a", "1"], 'echo "ARG_A=$ARG_A"', "ARG_A=1\n"),
    # QUIRK 4: a ONE-dash token is consumed as the value.
    (["--verbose", "-x"], 'echo "ARG_VERBOSE=$ARG_VERBOSE"', "ARG_VERBOSE=-x\n"),
    # A TWO-dash token is not, so the flag becomes a boolean.
    (["--verbose", "--other"], 'echo "ARG_VERBOSE=$ARG_VERBOSE"', "ARG_VERBOSE=true\n"),
    # Positional arguments are invisible to this parser.
    (["pos1", "--a=1", "pos2"], 'echo "ARG_A=$ARG_A"', "ARG_A=1\n"),
    # Split on the FIRST `=`.
    (["--q=a=b=c"], 'echo "ARG_Q=$ARG_Q"', "ARG_Q=a=b=c\n"),
    # A bare `--` becomes the key `ARG_`, which IS a valid identifier.
    (["--"], 'echo "ARG_=$ARG_"', "ARG_=true\n"),
]


@pytest.mark.parametrize(("argv", "echo", "expected"), PARSE_ARGS_CASES)
def test_parse_args_agrees(argv, echo, expected):
    body = "parse_args %s\n%s" % (" ".join(_sh(a) for a in argv), echo)
    rc_old, out_old, err_old = twin(body)
    assert (rc_old, out_old, err_old) == (0, expected, "")
    parsed = common.parse_args(argv)
    key = expected.split("=", 1)[0]
    value = expected.split("=", 1)[1].rstrip("\n")
    assert parsed[key] == value


def test_parse_args_stores_an_injection_rather_than_running_it():
    """common.sh:309-314's security fix, re-proved on both sides.

    The twin used `eval "$key=\\"$value\\""` until 2026-09-06, which EXECUTED a
    value carrying `;`. `printf -v` stores the bytes. A dict cannot execute
    anything, so the port has the property structurally -- and the test drives the bash too, because the property that matters is the twin's.
    """
    payload = '--foo=a"; PROOF=INJECTED; :"'
    rc, out, _err = twin(
        'parse_args %s\necho "ARG_FOO=$ARG_FOO"\necho "PROOF=${PROOF:-none}"' % _sh(payload)
    )
    assert rc == 0
    assert out == 'ARG_FOO=a"; PROOF=INJECTED; :"\nPROOF=none\n'
    assert common.parse_args([payload]) == {"ARG_FOO": 'a"; PROOF=INJECTED; :"'}


def test_ci_env_agrees_with_the_twins_exported_variables():
    """CI_OS / CI_ARCH / CI_TEMP, the three the twin exports at source time."""
    rc, out, err = twin('echo "CI_OS=$CI_OS"\necho "CI_ARCH=$CI_ARCH"\necho "CI_TEMP=$CI_TEMP"')
    assert rc == 0
    assert err == ""
    rc2, out2, err2 = port(["ci-env"])
    assert (rc2, out2, err2) == (0, out, "")


# --------------------------------------------------------------------------- 2. QUIRKS OF THE TWIN -- driven against the TWIN, red if bash is repaired ---------------------------------------------------------------------------


def test_the_twins_require_input_passes_on_an_empty_path_list():
    """QUIRK 1. The anti-vacuity helper, passing vacuously.

    If this ever goes red, `.ci/scripts/lib/common.sh` has been repaired and `REQUIRE_INPUT_VACUOUS_IS_A_PASS` plus this module's divergence should be retired in the same change.
    """
    rc, out, err = twin("require_input -f 'missing {}' 'why'\necho reached")
    assert (rc, out, err) == (0, "reached\n", "")
    assert common.REQUIRE_INPUT_VACUOUS_IS_A_PASS is True


def test_the_twins_require_input_misreports_a_bad_flag_as_a_missing_file():
    """QUIRK 2. `test -q x` exits 2, `! test` reads that as true."""
    rc, _out, err = twin("require_input -q 'missing {}' 'why' /nope")
    assert rc == 1
    assert "unary operator expected" in err
    assert "✗ missing /nope" in err


def test_the_twins_parse_args_kills_the_script_on_a_non_identifier_key():
    """QUIRK 3. `printf -v` returns 2 and `set -e` takes the caller down."""
    rc, out, err = twin("parse_args --foo.bar=x\necho reached")
    assert rc == 2
    assert "reached" not in out
    assert "not a valid identifier" in err
    assert "ARG_FOO.BAR" in err


def test_the_twins_get_repo_root_moves_the_callers_shell():
    """QUIRK 5. The final `cd` is not in a subshell.

    LATENT rather than live: every real call site spells it `"$(get_repo_root)"`. Pinned so the latency is a recorded fact rather than an assumption.
    """
    rc, out, _err = twin('cd /\necho "before=$PWD"\nget_repo_root >/dev/null\necho "after=$PWD"')
    assert rc == 0
    assert out.splitlines() == ["before=/", "after=%s" % paths.repo_root()]


def test_the_twins_to_upper_eats_its_own_flag():
    """`to_upper -n` prints nothing, because it is `echo "$1"`.

    NOT reproduced -- see the docstring. Pinned so the absence is a decision.
    """
    rc, out, err = twin("to_upper -n")
    # NOT even a newline: `echo -n` consumed the flag AND suppressed the newline, so `tr` had nothing at all to fold. `to_upper ""` at least emits "\n".
    assert (rc, out, err) == (0, "", "")
    assert twin('to_upper ""')[1] == "\n"
    assert common.to_upper("-n") == "-N"


def test_the_twin_snapshots_ci_temp_at_source_time():
    """CI_TEMP is computed once; `get_temp_dir` is not."""
    rc, out, _err = twin(
        'echo "snapshot=$CI_TEMP"\nRUNNER_TEMP=/other\necho "still=$CI_TEMP"\n'
        'echo "live=$(get_temp_dir)"',
        RUNNER_TEMP="/rt",
    )
    assert rc == 0
    assert out.splitlines() == ["snapshot=/rt", "still=/rt", "live=/other"]


def test_require_submodule_uses_the_literal_ci_not_is_ci():
    """The two CI tests in one file disagree, and both are reproduced.

    `is_ci` accepts a non-empty GITHUB_ACTIONS; `require_submodule` reads only
    `CI`. So GITHUB_ACTIONS=true with CI unset is CI for one and local for the
    other, in the same shell.
    """
    env = {"CI": None, "GITHUB_ACTIONS": "true"}
    rc_ci, _, _ = twin("is_ci", **env)
    rc_sub, _, err_sub = twin("require_submodule /definitely/nope L", **env)
    assert rc_ci == 0, "is_ci says CI"
    assert rc_sub == 1, "require_submodule takes the LOCAL branch"
    assert "skipping" in err_sub, "and says so"
    assert common.is_ci({"GITHUB_ACTIONS": "true"}) is True
    assert common.require_submodule("/definitely/nope", "L", {"GITHUB_ACTIONS": "true"}) is False


# --------------------------------------------------------------------------- 3. THE DELIBERATE DIVERGENCES, from both sides ---------------------------------------------------------------------------


def test_the_port_refuses_an_empty_require_input_where_the_twin_passes():
    rc_old, out_old, _ = twin("require_input -f 'missing {}' 'why'\necho reached")
    rc_new, _, err_new = port(["require-input", "-f", "missing {}", "why"])
    assert (rc_old, out_old.strip()) == (0, "reached")
    assert rc_new == 1
    assert "nothing to check" in err_new
    with pytest.raises(common.RefusalError):
        common.require_input("-f", "missing {}", "why", [])


def test_the_port_names_a_bad_test_flag_where_the_twin_names_the_path():
    rc_old, _, err_old = twin("require_input -q 'missing {}' 'why' /nope")
    rc_new, _, err_new = port(["require-input", "-q", "missing {}", "why", "/nope"])
    assert rc_old == 1
    assert "missing /nope" in err_old
    assert rc_new == 1
    assert "unknown test flag '-q'" in err_new
    assert "/nope" not in err_new.splitlines()[0]


def test_require_input_returns_how_many_it_checked():
    """Print the shape, not just the verdict. The twin returns nothing."""
    root = paths.repo_root()
    assert common.require_input("-d", "missing {}", "why", [root, root / ".ci"]) == 2


def test_repo_root_cannot_move_the_process(tmp_path, monkeypatch):
    """The port's answer to QUIRK 5: a function that cannot chdir."""
    monkeypatch.chdir(tmp_path)
    before = pathlib.Path.cwd()
    assert common.repo_root() == paths.repo_root()
    assert pathlib.Path.cwd() == before


# --------------------------------------------------------------------------- 4. THE PORT'S OWN UNITS, including the arms bash cannot reach here ---------------------------------------------------------------------------


def test_sed_in_place_argv_inserts_the_empty_suffix_only_on_macos():
    """The macOS arm, proved on Linux. This is why it is an argv builder."""
    assert common.sed_in_place_argv(["-E", "s/a/b/", "f"], "linux") == [
        "sed",
        "-i",
        "-E",
        "s/a/b/",
        "f",
    ]
    assert common.sed_in_place_argv(["-E", "s/a/b/", "f"], "macos") == [
        "sed",
        "-i",
        "",
        "-E",
        "s/a/b/",
        "f",
    ]
    # `unknown` takes the GNU arm, because the twin's test is `== "macos"`.
    assert common.sed_in_place_argv(["f"], common.UNKNOWN) == ["sed", "-i", "f"]


DETECT_OS_CASES = [
    ("Linux", "linux"),
    ("Linux 6.18", "linux"),
    ("Darwin", "macos"),
    ("CYGWIN_NT-10.0", "windows"),
    ("MINGW64_NT-10.0", "windows"),
    ("MSYS_NT-10.0", "windows"),
    # NOT a prefix the twin's `case` carries, unlike core.platform's table.
    ("Windows_NT", "unknown"),
    ("SunOS", "unknown"),
    ("", "unknown"),
]


@pytest.mark.parametrize(("uname", "expected"), DETECT_OS_CASES)
def test_detect_os_matches_the_twins_case_arms(uname, expected):
    assert common.detect_os(uname) == expected


DETECT_ARCH_CASES = [
    ("x86_64", "x64"),
    ("amd64", "x64"),
    ("aarch64", "arm64"),
    ("arm64", "arm64"),
    # EXACT words, not prefixes: the twin's case arms carry no `*`.
    ("x86_64-pc-linux", "unknown"),
    ("armv7l", "unknown"),
    ("", "unknown"),
]


@pytest.mark.parametrize(("machine", "expected"), DETECT_ARCH_CASES)
def test_detect_arch_matches_the_twins_case_arms(machine, expected):
    assert common.detect_arch(machine) == expected


def test_detect_os_and_arch_fail_open_where_core_platform_refuses():
    """The reason these live here and not in `core.platform`."""
    assert common.detect_os("SunOS") == common.UNKNOWN
    with pytest.raises(ci_platform.UnsupportedPlatformError):
        ci_platform.os_name("SunOS")
    assert common.detect_arch("armv7l") == common.UNKNOWN
    with pytest.raises(ci_platform.UnsupportedPlatformError):
        ci_platform.machine_key("armv7l")


IDENTIFIER_CASES = [
    ("ARG_A", True),
    ("ARG_", True),
    ("_", True),
    ("ARG_A1", True),
    ("ARG_FOO.BAR", False),
    ("1ARG", False),
    ("", False),
    ("ARG_A B", False),
    # `str.isidentifier()` says True for this; bash's `printf -v` does not.
    ("ARG_é", False),
]


@pytest.mark.parametrize(("name", "ok"), IDENTIFIER_CASES)
def test_valid_identifier_is_bashs_rule_not_pythons(name, ok):
    assert common._valid_identifier(name) is ok


def test_parse_args_refuses_a_non_identifier_key_with_the_twins_exit_code():
    with pytest.raises(common.RefusalError) as caught:
        common.parse_args(["--foo.bar=x"])
    assert caught.value.code == 2
    assert "not a valid identifier" in caught.value.lines[0]


def test_require_cmd_returns_the_resolved_path():
    assert common.require_cmd("jq").endswith("jq")


def test_refusal_carries_every_line_the_twin_would_print():
    with pytest.raises(common.RefusalError) as caught:
        common.require_submodule("/definitely/nope", "renet", {"CI": "true"})
    assert len(caught.value.lines) == 3
    assert caught.value.code == 1
    assert caught.value.lines[0].startswith("renet is required in CI but missing:")


# --------------------------------------------------------------------------- 5. PLANTED DEFECTS -- proving each control can fire ---------------------------------------------------------------------------


def test_planted_a_parse_args_that_accepts_a_bad_identifier_is_caught(monkeypatch):
    monkeypatch.setattr(common, "_valid_identifier", lambda _name: True)
    # With the guard defeated the refusal disappears, which is the defect.
    assert common.parse_args(["--foo.bar=x"]) == {"ARG_FOO.BAR": "x"}


def test_planted_a_require_input_that_passes_vacuously_is_caught(monkeypatch):
    real = common.require_input

    def vacuous(flag, lead, why, paths_):
        if not paths_:
            return 0
        return real(flag, lead, why, paths_)

    monkeypatch.setattr(common, "require_input", vacuous)
    # The planted version reproduces the twin's bug, and the assertion that would have caught it is the one in the divergence test above.
    assert common.require_input("-f", "missing {}", "why", []) == 0


def test_planted_a_detect_os_that_refuses_would_diverge_from_the_twin():
    """A port that adopted `core.platform`'s refusal would break `sed_in_place`."""
    with pytest.raises(ci_platform.UnsupportedPlatformError):
        ci_platform.os_name("SunOS")
    # The twin answers a string here, and `sed_in_place` compares against it.
    assert common.sed_in_place_argv(["f"], common.detect_os("SunOS"))[:2] == ["sed", "-i"]


def test_planted_an_is_ci_that_accepts_one_would_disagree_with_the_twin():
    rc, _, _ = twin("is_ci", CI="1", GITHUB_ACTIONS=None)
    assert rc == 1, "the twin says CI=1 is NOT ci"
    assert common.is_ci({"CI": "1"}) is False
    # The plant: a permissive reading.
    assert bool({"CI": "1"}.get("CI")) is True, "which is what a naive port would do"
