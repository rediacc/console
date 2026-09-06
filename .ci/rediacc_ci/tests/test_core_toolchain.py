"""`rediacc_ci.core.toolchain` against the bash that reads the same pins file.

WHAT EACH GROUP OF CASES GUARDS.

  the path        `pins_file()` and `toolchain_pins_file` must resolve to the
                  SAME file. Two readers of two different files is the exact
                  drift `.devcontainer/toolchain.env` exists to end, and it would
                  present as a version mismatch rather than as a path bug.
  the table       Every pin, and every tool -> key mapping, compared against the
                  live bash. The tool list is READ OUT OF the `toolchain_pin_for`
                  case arms rather than restated here, so a tool added to one
                  side and not the other is a red.
  the refusals    Missing key, empty value, unreadable file, comment-only file,
                  contradictory duplicate, unknown tool. Each with its control,
                  because a function that raised on EVERYTHING would pass every
                  one of them on its own.
  the comparison  Checked against `sort -V`, which is what the four bash callers
                  use today, over a corpus that INCLUDES the pins file's own
                  values. And then the same corpus is run through a string
                  compare, which must FAIL it -- the planted defect, so nobody
                  can pass this differential by writing `a < b`.
  the guard       A copy of the package with the empty-pin guard disabled must
                  print an empty pin and exit 0. That is what proves the guard is
                  the thing doing the work, rather than the file happening to
                  have no empty values in it today.

THE DEFECT ALL OF IT IS ABOUT, restated because it is easy to lose. Measured
2026-08-26 on a fresh shell, recorded at `.ci/scripts/lib/toolchain.sh:98-105`:
`toolchain_pin_for` returned "" with exit code 0, and the empty string reached a
download URL as

    .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404

The 404 names GitHub rather than the missing pin. And the other half, at
`.ci/config/constants.sh:49-58`: the Node floor used to be COMPOSED as
"${NODE_VERSION}.0.0", which silently read 22.0.0 while both manifests said
>=22.13.0, so a machine on Node 22.4 passed `./run.sh setup` and failed inside
npm. A default is what both look like on the day it is wrong, which is why
`pin()` has none and why these cases assert the raise rather than a fallback.
"""

import itertools
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.tests import differential as diff

SHIM = ".ci/scripts/lib/toolchain.sh"
CONSTANTS = ".ci/config/constants.sh"

# Sourcing the library is safe: its `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` guard
# (toolchain.sh:211) keeps the CLI block from running on a source.
SOURCE_SHIM = "source %s" % ("'" + str(paths.from_root(SHIM)) + "'")

# Versions that all carry three fields, so `sort -V` and `compare()` are being
# asked the same question. The zero-padding rule (`22` == `22.0.0` here, `22` <
# `22.0.0` under sort -V) is asserted separately and deliberately, below.
THREE_FIELD_CORPUS = (
    "0.9.0",
    "0.10.0",
    "0.16.1",
    "1.2.3",
    "1.2.30",
    "1.7.12",
    "1.26.6",
    "3.13.1",
    "9.1.1",
    "22.9.0",
    "22.13.0",
    "22.13.1",
    "22.23.2",
    "100.0.0",
)


def _q(value: str) -> str:
    """Single-quote for bash."""
    return "'" + value.replace("'", "'\\''") + "'"


def _bash(script: str, **env: str) -> tuple[int, str, str]:
    return diff.bash_streams(script, env=diff.env_for(**env))


def _live_pins() -> dict[str, str]:
    return toolchain.load_pins()


def _bash_tool_arms() -> dict[str, str]:
    """The tool -> key arms of `toolchain_pin_for`, read out of the bash source.

    READ, not restated. The whole value of this comparison is that it breaks when
    one side gains a tool the other does not; a hand-copied list here would be a
    third place to update and would agree with neither.
    """
    text = paths.from_root(SHIM).read_text(encoding="utf-8")
    body = text.split("toolchain_pin_for()", 1)[1].split("\n}", 1)[0]
    return dict(re.findall(r"^\s+(\w+)\)\s*key=([A-Z][A-Z0-9_]*)\s*;;", body, re.MULTILINE))


def _version_corpus() -> tuple[str, ...]:
    """The hand-written three-field corpus PLUS every pin that is a version.

    Corpus-derived rather than fixed: bumping a pin re-keys the comparison cases
    with the real numbers this repo compares, and a pin whose value is not a
    version (a checksum) drops out by failing to parse rather than by being
    listed.
    """
    extra = []
    for value in _live_pins().values():
        try:
            fields = toolchain.parse_version(value)
        except toolchain.VersionError:
            continue
        if len(fields) == 3:
            extra.append(toolchain.normalize_version(value))
    return tuple(sorted(set(THREE_FIELD_CORPUS) | set(extra)))


def _pairs() -> list[tuple[str, str]]:
    corpus = _version_corpus()
    return [(a, b) for a, b in itertools.product(corpus, corpus)]


# ---------------------------------------------------------------------------
# the path
# ---------------------------------------------------------------------------


def test_pins_file_is_the_file_the_bash_reads() -> None:
    """One pins file, reached two ways, or the whole single-source claim is false."""
    rc, out, err = _bash("%s; toolchain_pins_file" % SOURCE_SHIM)
    assert rc == 0, err
    assert out.strip() == str(toolchain.pins_file())


def test_pins_file_exists_and_is_readable() -> None:
    """The control for the case above: two equal paths to nothing would also pass."""
    assert toolchain.pins_file().is_file()


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------


def test_load_pins_matches_toolchain_pairs_exactly() -> None:
    """Every KEY=value the bash enumerates, and no other."""
    rc, out, err = _bash("%s; toolchain_pairs" % SOURCE_SHIM)
    assert rc == 0, err
    expected = dict(line.split("=", 1) for line in out.splitlines() if line.strip())
    assert toolchain.load_pins() == expected


def test_load_pins_is_not_empty() -> None:
    """CONTROL. Two empty dicts compare equal, which would pass the case above."""
    assert _live_pins()


def test_tool_keys_match_the_bash_case_arms() -> None:
    """The mapping, as a set-to-set comparison against the source of the twin."""
    assert _bash_tool_arms() == toolchain.TOOL_KEYS


def test_every_tool_pin_matches_the_bash() -> None:
    """And the VALUES agree, tool by tool, driven by the bash's own tool list."""
    arms = _bash_tool_arms()
    assert arms, "no case arms parsed out of toolchain_pin_for; the shape has changed"
    for tool in sorted(arms):
        rc, out, err = _bash("%s; toolchain_pin_for %s" % (SOURCE_SHIM, tool))
        assert rc == 0, err
        assert out.strip(), "the bash returned an EMPTY pin for %s" % tool
        assert toolchain.pin_for(tool) == out.strip()


def test_node_floor_is_on_the_pinned_major() -> None:
    """The assertion `.ci/config/constants.sh:67` makes, made here too.

    A floor under a major that CI does not install is a floor nobody could
    satisfy. Both numbers are read from the pins file, so this is a real
    consistency check and not a restatement of either.
    """
    assert toolchain.same_major(toolchain.node_floor(), toolchain.node_major())


def test_node_floor_is_stricter_than_the_bare_major() -> None:
    """The 22.0.0 defect, asserted as a property rather than as a number.

    constants.sh used to COMPOSE the floor as "${NODE_VERSION}.0.0". If it ever
    does again, the floor becomes exactly the major with zeros and this fails --
    without this file naming 22.13.0 anywhere.
    """
    floor = toolchain.node_floor()
    composed = "%s.0.0" % toolchain.node_major()
    assert toolchain.compare(floor, composed) > 0


# ---------------------------------------------------------------------------
# the refusals, each with its control
# ---------------------------------------------------------------------------


def _write_env(tmp_path, text: str):
    target = tmp_path / "toolchain.env"
    target.write_text(text, encoding="utf-8")
    return target


def test_missing_key_raises(tmp_path) -> None:
    pins = toolchain.load_pins(_write_env(tmp_path, "SHFMT_VERSION=3.13.1\n"))
    with pytest.raises(toolchain.PinError, match="no pin named"):
        toolchain.pin("SHELLCHECK_VERSION", pins)


def test_missing_key_control_a_present_one_returns(tmp_path) -> None:
    """CONTROL. Without it, a `pin()` that raised unconditionally would pass."""
    pins = toolchain.load_pins(_write_env(tmp_path, "SHFMT_VERSION=3.13.1\n"))
    assert toolchain.pin("SHFMT_VERSION", pins) == "3.13.1"


def test_empty_value_raises(tmp_path) -> None:
    """The pin that reached a download URL as `download/v/shellcheck-v...`."""
    pins = toolchain.load_pins(_write_env(tmp_path, "SHFMT_VERSION=\n"))
    with pytest.raises(toolchain.PinError, match="EMPTY"):
        toolchain.pin("SHFMT_VERSION", pins)


def test_empty_value_control_the_same_key_with_a_value(tmp_path) -> None:
    """CONTROL, on the SAME key in two states rather than on two keys."""
    pins = toolchain.load_pins(_write_env(tmp_path, "SHFMT_VERSION=3.13.1\n"))
    assert toolchain.pin("SHFMT_VERSION", pins) == "3.13.1"


def test_unreadable_file_raises(tmp_path) -> None:
    with pytest.raises(toolchain.PinError, match="missing or unreadable"):
        toolchain.load_pins(tmp_path / "does-not-exist.env")


def test_unreadable_file_control_a_real_one_loads(tmp_path) -> None:
    assert toolchain.load_pins(_write_env(tmp_path, "A_VERSION=1\n")) == {"A_VERSION": "1"}


def test_comment_only_file_raises(tmp_path) -> None:
    """The vacuity refusal: an empty table answers every lookup with 'no pin'."""
    text = "# a header\n\n  indented=not-a-pin\nlowercase=no\n"
    with pytest.raises(toolchain.PinError, match="no KEY=value pin at all"):
        toolchain.load_pins(_write_env(tmp_path, text))


def test_comment_only_control_one_real_pin_is_enough(tmp_path) -> None:
    """CONTROL: the same file plus ONE valid line must load."""
    text = "# a header\n\n  indented=not-a-pin\nlowercase=no\nA_VERSION=1\n"
    assert toolchain.load_pins(_write_env(tmp_path, text)) == {"A_VERSION": "1"}


def test_contradictory_duplicate_raises(tmp_path) -> None:
    with pytest.raises(toolchain.PinError, match="defined twice"):
        toolchain.load_pins(_write_env(tmp_path, "A_VERSION=1\nA_VERSION=2\n"))


def test_duplicate_control_the_same_value_twice_is_fine(tmp_path) -> None:
    """CONTROL. A repeated identical line is noise, not a contradiction, and
    raising on it would make the refusal above untestably broad."""
    assert toolchain.load_pins(_write_env(tmp_path, "A_VERSION=1\nA_VERSION=1\n")) == {
        "A_VERSION": "1"
    }


def test_unknown_tool_raises() -> None:
    with pytest.raises(toolchain.PinError, match="no pin defined for"):
        toolchain.pin_for("cargo")


def test_unknown_tool_control_a_known_one_answers() -> None:
    assert toolchain.pin_for("shfmt")


def test_unknown_tool_matches_the_bash_refusal() -> None:
    """The bash answers exit 2 for a tool it has no arm for; so must this."""
    rc, out, _ = _bash("%s; toolchain_pin_for cargo" % SOURCE_SHIM)
    assert rc == 2
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------

# The strip pipeline at toolchain.sh:88-93, frozen so the differential keeps
# working if that function is later reshaped. `head -1` and the per-tool awk are
# not part of it: this is only the normalising tail.
FROZEN_NORMALIZE = r"""
normalize() {
    local out="$1"
    out="${out#v}"
    out="${out#go}"
    out="$(printf '%s' "$out" | grep -oE '^[0-9]+(\.[0-9]+)*' || true)"
    [[ -n "$out" ]] || return 1
    printf '%s' "$out"
}
"""

NORMALIZE_CASES = (
    "v22.23.2",
    "go1.26.6",
    "3.13.1",
    "0.10.0",
    "1.7.12",
    "9.1.1",
    "22",
    "v22",
    # BOTH prefixes come off, in order: `${out#v}` then `${out#go}` are two
    # consecutive statements, not an either/or. This input is in the corpus
    # because the first draft of `normalize_version` broke out of its loop after
    # the first match, and this differential is what caught it.
    "vgo1.2",
    "1.2.3-rc1",
    "1.2.3 linux/arm64",
)


@pytest.mark.parametrize("text", NORMALIZE_CASES)
def test_normalize_matches_the_frozen_bash(text: str) -> None:
    rc, out, err = _bash("%s\nnormalize %s\n" % (FROZEN_NORMALIZE, _q(text)))
    assert rc == 0, err
    assert out == toolchain.normalize_version(text)


# `gov1.2` is here rather than above BECAUSE the two prefixes are ordered: `go`
# comes off and leaves `v1.2`, which starts with no digit. The bash refuses it
# and so must this, and the pair of corpora is where that ordering is pinned.
@pytest.mark.parametrize("text", ["", "none", "shellcheck", "v", "go", "-1.2", "gov1.2"])
def test_unparseable_version_raises_and_the_bash_agrees(text: str) -> None:
    """BOTH DIRECTIONS on the case the bash's own comment calls out.

    "a normaliser that silently yields '' would make a comparison of ''==''
    pass -- vacuity inside the very check meant to prevent it."
    """
    rc, out, _ = _bash("%s\nnormalize %s\n" % (FROZEN_NORMALIZE, _q(text)))
    assert rc == 1
    assert out == ""
    with pytest.raises(toolchain.VersionError):
        toolchain.normalize_version(text)


# ---------------------------------------------------------------------------
# the comparison, and the planted defect it must survive
# ---------------------------------------------------------------------------


def _sort_v_says_ordered(a: str, b: str) -> bool:
    """`printf '%s\\n%s\\n' a b | sort -V -C`, the predicate the bash uses today.

    Exit 0 means "already sorted", i.e. a <= b. Three call sites ask exactly this
    question: `.ci/lib/local-common.sh:429`, `.ci/lib/setup.sh:57` and `:351`.
    """
    rc, _, err = _bash("printf '%%s\\n%%s\\n' %s %s | sort -V -C" % (_q(a), _q(b)))
    assert rc in (0, 1), err
    return rc == 0


def test_compare_agrees_with_sort_v_over_the_whole_corpus() -> None:
    """The differential. Every ordered pair, against GNU sort's version compare.

    Run as ONE case over the product rather than parametrized, because the corpus
    is derived from the pins file and a parametrized id list would be recomputed
    at collection time on every run of a suite that has hundreds of pairs.
    """
    disagreements = [
        (a, b)
        for a, b in _pairs()
        if (toolchain.compare(a, b) <= 0) is not _sort_v_says_ordered(a, b)
    ]
    assert disagreements == []


def test_the_corpus_would_catch_a_string_compare() -> None:
    """THE PLANTED DEFECT. The obvious wrong implementation must FAIL this corpus.

    Without this the differential above proves only that two implementations
    agree, not that the corpus can tell a right one from a wrong one. `22.13.0`
    vs `22.9.0` is the shape: '1' sorts before '9', so as strings the newer
    release reads as older, and a floor of 22.13.0 admits exactly what it was
    raised to exclude.
    """
    corpus = _version_corpus()
    caught = [(a, b) for a, b in _pairs() if (a <= b) is not (toolchain.compare(a, b) <= 0)]
    assert caught, (
        "the corpus %r cannot distinguish a version compare from a string "
        "compare, so the differential above proves nothing" % (corpus,)
    )
    # And every case it catches is one the real implementation gets right, which
    # the sort -V differential above has already established for the same pairs.
    for a, b in caught:
        assert len(toolchain.parse_version(a)) == len(toolchain.parse_version(b))


def test_multi_digit_fields_order_by_value_not_by_character() -> None:
    """The one comparison this module exists for, stated as itself."""
    assert toolchain.compare("22.13.0", "22.9.0") > 0
    assert toolchain.at_least("22.13.0", "22.9.0")
    assert not toolchain.at_least("22.9.0", "22.13.0")


def test_missing_trailing_fields_are_zeros_not_unknown() -> None:
    """`22` == `22.0.0`, and the divergence from sort -V is deliberate.

    `sort -V` orders `22` BEFORE `22.0.0` (a shorter field list sorts first). For
    the question every caller actually asks -- `at_least(current, floor)` -- the
    two agree, because both directions of an equal pair satisfy `>=`. Treating
    them as equal is what lets NODE_VERSION, which is a bare major, be compared
    against a full version without every call site remembering to pad it.
    """
    assert toolchain.compare("22", "22.0.0") == 0
    assert toolchain.at_least("22", "22.0.0")
    assert toolchain.at_least("22.0.0", "22")
    assert toolchain.compare("22", "22.13.0") < 0


def test_same_major_is_the_node_branch() -> None:
    """toolchain.sh:147-151 compares only `${actual%%.*}` for node."""
    assert toolchain.same_major("22.23.2", "22")
    assert not toolchain.same_major("24.0.0", "22")


# ---------------------------------------------------------------------------
# the argv surface
# ---------------------------------------------------------------------------


def _module(*args: str, root: str | None = None, pypath: str | None = None):
    env = diff.env_for()
    env["PYTHONPATH"] = str(paths.ci_dir()) if pypath is None else pypath
    if root is not None:
        env["REDIACC_CI_ROOT"] = root
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.toolchain", *args],
        cwd=diff.repo(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_value_prints_the_pin() -> None:
    result = _module("value", toolchain.NODE_FLOOR_KEY)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == toolchain.node_floor()


def test_cli_value_refuses_an_absent_key_with_nothing_on_stdout() -> None:
    """The contract a bash caller depends on: `v="$(...)" || die` must see "".

    A diagnostic printed on stdout would be captured INTO the variable and then
    interpolated into whatever the value was for, which is the 404-naming-GitHub
    failure with extra steps.
    """
    result = _module("value", "NO_SUCH_VERSION")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "NO_SUCH_VERSION" in result.stderr


def test_cli_at_least_answers_in_the_exit_code() -> None:
    assert _module("at-least", "22.13.0", "22.9.0").returncode == 0
    assert _module("at-least", "22.9.0", "22.13.0").returncode == 1


def test_cli_at_least_cannot_tell_is_two_not_one() -> None:
    """An unparseable version must not read as "too old"; 1 is a verdict, 2 is not."""
    result = _module("at-least", "none", "22.13.0")
    assert result.returncode == 2
    assert result.stdout == ""


def test_cli_pairs_is_safe_for_github_env() -> None:
    """$GITHUB_ENV rejects anything that is not KEY=value, so no line may be prose."""
    result = _module("pairs")
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line]
    assert lines
    assert all(toolchain.PAIR_RE.match(line) for line in lines)


# ---------------------------------------------------------------------------
# the guard, proved by disabling it
# ---------------------------------------------------------------------------


def test_the_empty_pin_guard_is_what_produces_the_refusal(tmp_path) -> None:
    """Disable the guard in a COPY and the empty pin walks straight through.

    This is the case that stops the refusal tests above from being satisfied by
    a pins file that simply has no empty values in it. Same shape as control C in
    `.ci/scripts/quality/check-setup-idempotency.sh` and as
    `test_shim_delegation_is_real_not_a_reimplementation` next door: mutate the
    implementation, and require the observable behaviour to change.
    """
    root = tmp_path / "fixture-root"
    (root / ".ci").mkdir(parents=True)
    (root / ".devcontainer").mkdir()
    shutil.copytree(paths.from_root(".ci/rediacc_ci"), root / ".ci" / "rediacc_ci")
    (root / ".devcontainer" / "toolchain.env").write_text(
        "SHFMT_VERSION=\nGO_VERSION=1.26.6\n", encoding="utf-8"
    )
    pypath = str(root / ".ci")

    intact = _module("value", "SHFMT_VERSION", root=str(root), pypath=pypath)
    assert intact.returncode == 1
    assert intact.stdout == ""
    assert "EMPTY" in intact.stderr

    target = root / ".ci" / "rediacc_ci" / "core" / "toolchain.py"
    text = target.read_text(encoding="utf-8")
    anchor = "    value = table[key].strip()\n    if not value:"
    assert anchor in text, "the line the control mutates has moved"
    target.write_text(
        text.replace(anchor, "    value = table[key].strip()\n    if False:"),
        encoding="utf-8",
    )

    broken = _module("value", "SHFMT_VERSION", root=str(root), pypath=pypath)
    assert broken.returncode == 0, "the guard is not what refuses; something else is"
    assert broken.stdout.strip() == "", "an empty pin was printed as a value"


def test_constants_sh_still_refuses_an_unset_floor() -> None:
    """The bash half of the same contract, asserted against the live file.

    `${NODE_VERSION_MIN:?...}` is the reason an unset pin is fatal there. If that
    `:?` is ever softened to `:-`, this module's Python guard would be the only
    thing left refusing, and the shell path -- which is what `./run.sh setup` and
    `rdc.sh` actually take -- would go back to defaulting.
    """
    text = paths.from_root(CONSTANTS).read_text(encoding="utf-8")
    assert "${NODE_VERSION_MIN:?" in text
    assert "${NODE_VERSION:?" in text
