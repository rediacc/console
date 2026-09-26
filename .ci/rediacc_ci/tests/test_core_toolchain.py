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

THE DEFECT ALL OF IT IS ABOUT, restated because it is easy to lose. Measured 2026-08-26 on a fresh shell, recorded at `.ci/scripts/lib/toolchain.sh:98-105`: `toolchain_pin_for` returned "" with exit code 0, and the empty string reached a download URL as

    .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404

The 404 names GitHub rather than the missing pin. And the other half, at `.ci/config/constants.sh:49-58`: the Node floor used to be COMPOSED as
"${NODE_VERSION}.0.0", which silently read 22.0.0 while both manifests said
>=22.13.0, so a machine on Node 22.4 passed `./run.sh setup` and failed inside
npm. A default is what both look like on the day it is wrong, which is why `pin()` has none and why these cases assert the raise rather than a fallback.
"""

import hashlib
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

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

    READ, not restated. The whole value of this comparison is that it breaks when one side gains a tool the other does not; a hand-copied list here would be a third place to update and would agree with neither.
    """
    text = paths.from_root(SHIM).read_text(encoding="utf-8")
    body = text.split("toolchain_pin_for()", 1)[1].split("\n}", 1)[0]
    return dict(re.findall(r"^\s+(\w+)\)\s*key=([A-Z][A-Z0-9_]*)\s*;;", body, re.MULTILINE))


def _version_corpus() -> tuple[str, ...]:
    """The hand-written three-field corpus PLUS every pin that is a version.

    Corpus-derived rather than fixed: bumping a pin re-keys the comparison cases
    with the real numbers this repo compares, and a pin whose value is not a
    version (a checksum) drops out by failing to parse rather than by being listed.
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


# --------------------------------------------------------------------------- the path ---------------------------------------------------------------------------


def test_pins_file_is_the_file_the_bash_reads() -> None:
    """One pins file, reached two ways, or the whole single-source claim is false."""
    rc, out, err = _bash("%s; toolchain_pins_file" % SOURCE_SHIM)
    assert rc == 0, err
    assert out.strip() == str(toolchain.pins_file())


def test_pins_file_exists_and_is_readable() -> None:
    """The control for the case above: two equal paths to nothing would also pass."""
    assert toolchain.pins_file().is_file()


# --------------------------------------------------------------------------- the table ---------------------------------------------------------------------------


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

    A floor under a major that CI does not install is a floor nobody could satisfy. Both numbers are read from the pins file, so this is a real consistency check and not a restatement of either.
    """
    assert toolchain.same_major(toolchain.node_floor(), toolchain.node_major())


def test_node_floor_is_stricter_than_the_bare_major() -> None:
    """The 22.0.0 defect, asserted as a property rather than as a number.

    constants.sh used to COMPOSE the floor as "${NODE_VERSION}.0.0". If it ever
    does again, the floor becomes exactly the major with zeros and this fails -- without this file naming 22.13.0 anywhere.
    """
    floor = toolchain.node_floor()
    composed = "%s.0.0" % toolchain.node_major()
    assert toolchain.compare(floor, composed) > 0


# --------------------------------------------------------------------------- the refusals, each with its control ---------------------------------------------------------------------------


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
    """CONTROL. A repeated identical line is noise, not a contradiction, and raising on it would make the refusal above untestably broad."""
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


# --------------------------------------------------------------------------- normalisation ---------------------------------------------------------------------------

# The strip pipeline at toolchain.sh:88-93, frozen so the differential keeps working if that function is later reshaped. `head -1` and the per-tool awk are not part of it: this is only the normalising tail.
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
    # consecutive statements, not an either/or. This input is in the corpus because the first draft of `normalize_version` broke out of its loop after the first match, and this differential is what caught it.
    "vgo1.2",
    "1.2.3-rc1",
    "1.2.3 linux/arm64",
)


@pytest.mark.parametrize("text", NORMALIZE_CASES)
def test_normalize_matches_the_frozen_bash(text: str) -> None:
    rc, out, err = _bash("%s\nnormalize %s\n" % (FROZEN_NORMALIZE, _q(text)))
    assert rc == 0, err
    assert out == toolchain.normalize_version(text)


# `gov1.2` is here rather than above BECAUSE the two prefixes are ordered: `go` comes off and leaves `v1.2`, which starts with no digit. The bash refuses it and so must this, and the pair of corpora is where that ordering is pinned.
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


# --------------------------------------------------------------------------- the comparison, and the planted defect it must survive ---------------------------------------------------------------------------


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

    Run as ONE case over the product rather than parametrized, because the corpus is derived from the pins file and a parametrized id list would be recomputed at collection time on every run of a suite that has hundreds of pairs.
    """
    disagreements = [
        (a, b)
        for a, b in _pairs()
        if (toolchain.compare(a, b) <= 0) is not _sort_v_says_ordered(a, b)
    ]
    assert disagreements == []


def test_the_corpus_would_catch_a_string_compare() -> None:
    """THE PLANTED DEFECT. The obvious wrong implementation must FAIL this corpus.

    Without this the differential above proves only that two implementations agree, not that the corpus can tell a right one from a wrong one. `22.13.0` vs `22.9.0` is the shape: '1' sorts before '9', so as strings the newer release reads as older, and a floor of 22.13.0 admits exactly what it was raised to exclude.
    """
    corpus = _version_corpus()
    caught = [(a, b) for a, b in _pairs() if (a <= b) is not (toolchain.compare(a, b) <= 0)]
    assert caught, (
        "the corpus %r cannot distinguish a version compare from a string "
        "compare, so the differential above proves nothing" % (corpus,)
    )
    # And every case it catches is one the real implementation gets right, which the sort -V differential above has already established for the same pairs.
    for a, b in caught:
        assert len(toolchain.parse_version(a)) == len(toolchain.parse_version(b))


def test_multi_digit_fields_order_by_value_not_by_character() -> None:
    """The one comparison this module exists for, stated as itself."""
    assert toolchain.compare("22.13.0", "22.9.0") > 0
    assert toolchain.at_least("22.13.0", "22.9.0")
    assert not toolchain.at_least("22.9.0", "22.13.0")


def test_missing_trailing_fields_are_zeros_not_unknown() -> None:
    """`22` == `22.0.0`, and the divergence from sort -V is deliberate.

    `sort -V` orders `22` BEFORE `22.0.0` (a shorter field list sorts first). For the question every caller actually asks -- `at_least(current, floor)` -- the
    two agree, because both directions of an equal pair satisfy `>=`. Treating
    them as equal is what lets NODE_VERSION, which is a bare major, be compared against a full version without every call site remembering to pad it.
    """
    assert toolchain.compare("22", "22.0.0") == 0
    assert toolchain.at_least("22", "22.0.0")
    assert toolchain.at_least("22.0.0", "22")
    assert toolchain.compare("22", "22.13.0") < 0


def test_same_major_is_the_node_branch() -> None:
    """toolchain.sh:147-151 compares only `${actual%%.*}` for node."""
    assert toolchain.same_major("22.23.2", "22")
    assert not toolchain.same_major("24.0.0", "22")


# --------------------------------------------------------------------------- the argv surface ---------------------------------------------------------------------------


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

    A diagnostic printed on stdout would be captured INTO the variable and then interpolated into whatever the value was for, which is the 404-naming-GitHub failure with extra steps.
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


# --------------------------------------------------------------------------- the guard, proved by disabling it ---------------------------------------------------------------------------


def test_the_empty_pin_guard_is_what_produces_the_refusal(tmp_path) -> None:
    """Disable the guard in a COPY and the empty pin walks straight through.

    This is the case that stops the refusal tests above from being satisfied by a pins file that simply has no empty values in it. Same shape as control C in `.ci/scripts/quality/check-setup-idempotency.sh` and as `test_shim_delegation_is_real_not_a_reimplementation` next door: mutate the implementation, and require the observable behaviour to change.
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
    `:?` is ever softened to `:-`, this module's Python guard would be the only thing left refusing, and the shell path -- which is what `./run.sh setup` and `rdc.sh` actually take -- would go back to defaulting.
    """
    text = paths.from_root(CONSTANTS).read_text(encoding="utf-8")
    assert "${NODE_VERSION_MIN:?" in text
    assert "${NODE_VERSION:?" in text


# ===========================================================================
# THE PROBING AND ACQUISITION HALF (W7P5-b, 2026-09-10)
#
# Everything above covers the W6P2 port: the pins file, the table, the refusals, the comparison. Everything below covers what W7P5-b added: `probe_version`, `check`, `lane`, `cache_dir`, `report`, `checksums`, `os_name`, `sha256_of`, the two URL builders and `acquire`.
#
# WHAT EACH GROUP GUARDS.
#
# the probes All EIGHT tools, each against real stub binaries that print the real banners, run on BOTH sides. Including the shapes that must yield NOTHING, because a normaliser that silently
#                   returns "" makes a comparison of ""=="" pass.
# check Nine tools x two PATHs, message text and exit code compared byte-for-byte, because `.ci/legacy/run-legacy.sh:406` pipes those messages straight to the operator. the environment `lane` and `cache_dir` over every branch of their `:-` chains, which are the two places an empty string and an unset variable must behave identically. the defects Two findings PINNED rather than
# fixed, because `.ci/scripts/lib/` is outside this workstream's write grant. the planted A mutated COPY of the module must make the probe differential FAIL, on a case the honest module passes.
# ===========================================================================

# Real `--version` output for every tool the twin has an arm for, plus the shapes that must produce NOTHING. The banners are the ones in the twin's own table at toolchain.sh:59-66, not invented ones.
PROBE_FIXTURES = {
    "shfmt": (
        'printf "v3.13.1\\n"',
        'printf "3.13.1\\n"',
        'printf "v3.13.1\\nsecond line\\n"',
        'echo "no version here"',
        "exit 3",
    ),
    "shellcheck": (
        (
            'printf "\\nShellCheck - shell script analysis tool\\nversion: 0.10.0\\n'
            'license: GPLv3\\n"'
        ),
        'printf "version:0.10.0\\n"',
        'printf "version:   0.9.0\\n"',
        'printf "version: 0.10.0\\nversion: 0.9.0\\n"',
        'printf "no banner at all\\n"',
    ),
    "ruff": (
        'printf "ruff 0.16.1\\n"',
        'printf "ruff 0.16.1 (abcdef 2026-01-01)\\n"',
        'printf "ruff\\n"',
        'printf "\\n"',
    ),
    "actionlint": ('printf "1.7.12\\n"', 'printf "v1.7.12\\ninstalled by go\\n"', 'printf "\\n"'),
    "go": (
        'printf "go version go1.26.6 linux/arm64\\n"',
        'printf "go version go1.2\\n"',
        'printf "go1.26.6\\n"',
        'printf "go version\\n"',
    ),
    "node": ('printf "v22.23.2\\n"', 'printf "22\\n"', 'printf "v22\\n"', 'printf "nope\\n"'),
    "uv": ('printf "uv 0.12.10\\n"', 'printf "uv\\n"'),
    "pytest": ('printf "pytest 9.1.1\\nrootdir: /x\\n"', 'printf "pytest\\n"'),
}

# /usr/bin:/bin holds the coreutils the twin needs (dirname, grep, awk) and NONE of the eight pinned tools, verified 2026-09-10. Anything smaller breaks the TWIN rather than the port, which is a control failure dressed as a finding: the first draft of this differential set PATH to the stub directory alone and the twin failed with `dirname: command not found` on every case.
SYSTEM_PATH = "/usr/bin:/bin"


def _stub_dir(tmp_path: pathlib.Path, tool: str, body: str) -> pathlib.Path:
    binary = tmp_path / "bin" / tool
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/bash\n%s\n" % body, encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _probe_cases() -> list[tuple[str, str]]:
    return [(tool, body) for tool, bodies in PROBE_FIXTURES.items() for body in bodies]


PROBE_CASES = _probe_cases()


@pytest.mark.parametrize(("tool", "body"), PROBE_CASES)
def test_probe_version_matches_the_twin(tmp_path: pathlib.Path, tool: str, body: str) -> None:
    """`toolchain_probe_version` and `probe_version` agree on stdout AND rc.

    Both sides are handed the SAME stub binary by absolute path, so the only thing under comparison is the extract-and-normalise pipeline.
    """
    binary = _stub_dir(tmp_path, tool, body)
    rc, out, _err = _bash(
        "%s; toolchain_probe_version %s %s" % (SOURCE_SHIM, _q(tool), _q(str(binary)))
    )
    answer = toolchain.probe_version(tool, str(binary))
    assert (out, rc) == ((answer or ""), (0 if answer else 1))


def test_the_probe_corpus_reaches_both_outcomes() -> None:
    """ANTI-VACUITY. Some fixtures must yield a version and some must yield none.

    A corpus in which every case refused would pass the differential above while proving only that both sides can say no.
    """
    answers = {"yes": 0, "no": 0}
    for _tool, body in PROBE_CASES:
        # Decided from the fixture text rather than by running it, so this case is independent of the differential it is guarding.
        silent = "no version" in body or "nope" in body or "exit 3" in body
        answers["no" if silent else "yes"] += 1
    assert answers["yes"] >= 20, answers
    assert answers["no"] >= 3, answers
    assert len(PROBE_CASES) >= 25


def test_probe_version_refuses_a_tool_it_has_no_arm_for() -> None:
    """`*) return 2 ;;` at toolchain.sh:86, as a raise rather than a code."""
    rc, out, _err = _bash("%s; toolchain_probe_version cargo /bin/true" % SOURCE_SHIM)
    assert (rc, out) == (2, "")
    with pytest.raises(toolchain.ToolError):
        toolchain.probe_version("cargo", "/bin/true")


CHECK_TOOLS = (*tuple(PROBE_FIXTURES), "cargo")


@pytest.mark.parametrize("tool", list(CHECK_TOOLS))
@pytest.mark.parametrize("present", [True, False])
def test_check_matches_the_twin(tmp_path: pathlib.Path, tool: str, present: bool) -> None:
    """`toolchain_check` and `check` agree on the binary, the message and the rc.

    The message text is compared VERBATIM, not just the exit code, because `.ci/legacy/run-legacy.sh:406` re-runs this purely to show the operator what it said.
    """
    if present and tool in PROBE_FIXTURES:
        _stub_dir(tmp_path, tool, PROBE_FIXTURES[tool][0])
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    path_env = "%s:%s" % (tmp_path / "bin", SYSTEM_PATH)
    rc, out, err = _bash("%s; PATH=%s toolchain_check %s" % (SOURCE_SHIM, _q(path_env), _q(tool)))
    result = toolchain.check(tool, path=path_env)
    assert out == (result.binary or "")
    assert err == "".join(m + "\n" for m in result.messages)
    assert rc == result.rc


def test_check_reaches_every_one_of_its_five_refusals(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the case above: all five refusal texts must be produced.

    Five distinct messages exist in the twin (:131, :135, :139, :143, :149/:153) and a differential that only ever saw one of them would be one case wearing a parametrize decorator.
    """
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    path_env = "%s:%s" % (tmp_path / "bin", SYSTEM_PATH)
    seen = set()

    seen.add(toolchain.check("cargo", path=path_env).messages[0].split("'")[0])
    seen.add(toolchain.check("shfmt", path=path_env).messages[0].split("(")[0])

    _stub_dir(tmp_path, "shfmt", 'printf "v0.0.1\\n"')
    seen.add("mismatch:" + toolchain.check("shfmt", path=path_env).messages[0].split(" ")[1])

    _stub_dir(tmp_path, "shellcheck", 'printf "no banner\\n"')
    seen.add("unreadable:" + toolchain.check("shellcheck", path=path_env).messages[0][:30])

    _stub_dir(tmp_path, "node", 'printf "v20.1.1\\n"')
    node = toolchain.check("node", path=path_env)
    assert node.messages[0].startswith("toolchain: node major 20 != pinned ")
    seen.add("node-major")

    empty = toolchain.check("shfmt", pins={"SHFMT_VERSION": ""}, path=path_env)
    assert empty.rc == 2
    assert empty.messages == ("toolchain: pin for 'shfmt' is empty -- did toolchain_load run?",)
    seen.add("empty-pin")

    assert len(seen) == 6, sorted(seen)


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"GITHUB_ACTIONS": "true"},
        {"GITHUB_ACTIONS": ""},
        {"REDIACC_NPM_RUNTIME": "devbox"},
        {"REDIACC_NPM_RUNTIME": "host"},
        {"REDIACC_NPM_RUNTIME": ""},
        {"GITHUB_ACTIONS": "true", "REDIACC_NPM_RUNTIME": "devbox"},
    ],
)
def test_lane_matches_the_twin(env: dict) -> None:
    """`toolchain_lane` (:174-182), over every branch including the empty ones.

    An EMPTY `$GITHUB_ACTIONS` is not `ci` and an empty `$REDIACC_NPM_RUNTIME`
    is not `devbox`; `[[ -n ... ]]` and `${x:-host}` both treat empty as unset,
    which is the distinction `os.environ.get(...) or ...` reproduces and a `in os.environ` test would not.
    """
    overrides = {"GITHUB_ACTIONS": None, "REDIACC_NPM_RUNTIME": None}
    overrides.update(env)
    shell_env = diff.env_for(**overrides)
    _rc, out, _err = diff.bash_streams("%s; toolchain_lane" % SOURCE_SHIM, env=shell_env)
    assert out == toolchain.lane(shell_env)


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"CI_TEMP": "/a"},
        {"RUNNER_TEMP": "/b"},
        {"TMPDIR": "/c"},
        {"CI_TEMP": "", "RUNNER_TEMP": "/b"},
        {"CI_TEMP": "/a", "RUNNER_TEMP": "/b", "TMPDIR": "/c"},
        {"CI_TEMP": "", "RUNNER_TEMP": "", "TMPDIR": ""},
    ],
)
def test_cache_dir_matches_the_twin(env: dict) -> None:
    """`toolchain_cache_dir` (:257-259): CI_TEMP, then RUNNER_TEMP, then TMPDIR."""
    overrides = {"CI_TEMP": None, "RUNNER_TEMP": None, "TMPDIR": None}
    overrides.update(env)
    shell_env = diff.env_for(**overrides)
    _rc, out, _err = diff.bash_streams("%s; toolchain_cache_dir" % SOURCE_SHIM, env=shell_env)
    assert out == str(toolchain.cache_dir(shell_env))


@pytest.mark.parametrize("path_env", ["STUBS", "EMPTY", "REAL"])
def test_report_matches_the_twin(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, path_env: str
) -> None:
    """`toolchain_report --verify` and `report(True)` agree on the table AND rc.

    The FUNCTION's rc is correct on both sides. What is broken is the twin's SCRIPT dispatch, which is pinned separately below.

    THE REAL $PATH IS TAKEN FROM `diff.BASE_ENV`, not from `os.environ`, and monkeypatch does the save-and-restore. Both choices are deliberate: reading `os.environ["PATH"]` here would add an undeclared environment input to a test module (`check:ci-python-env-registry` says so, and it is right), and a hand-rolled try/finally restore leaks the value on any exception raised before
    the finally arms.
    """
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    if path_env == "STUBS":
        for tool, bodies in PROBE_FIXTURES.items():
            _stub_dir(tmp_path, tool, bodies[0])
        value = "%s:%s" % (tmp_path / "bin", SYSTEM_PATH)
    elif path_env == "EMPTY":
        value = "%s:%s" % (tmp_path / "bin", SYSTEM_PATH)
    else:
        value = diff.BASE_ENV["PATH"]
    shell_env = diff.env_for(PATH=value)
    rc, out, _err = diff.bash_streams("%s; toolchain_report --verify" % SOURCE_SHIM, env=shell_env)
    monkeypatch.setenv("PATH", value)
    lines, prc = toolchain.report(True, env=shell_env)
    assert out == "".join(line + "\n" for line in lines)
    assert rc == prc


def test_report_without_verify_is_information_and_never_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[[ "$strict" == "--verify" ]] || return 0` at :207, on both sides."""
    shell_env = diff.env_for(PATH=SYSTEM_PATH)
    rc, out, _err = diff.bash_streams("%s; toolchain_report" % SOURCE_SHIM, env=shell_env)
    monkeypatch.setenv("PATH", SYSTEM_PATH)
    lines, prc = toolchain.report(False, env=shell_env)
    assert (rc, prc) == (0, 0)
    assert "MISMATCH" in out, "the control is broken: nothing mismatched, so rc 0 proves nothing"
    assert out == "".join(line + "\n" for line in lines)


# --------------------------------------------------------------------------- Checksums, the OS, and the URLs ---------------------------------------------------------------------------


def test_constants_file_is_the_one_the_twin_computes() -> None:
    """`_toolchain_need_checksums` builds the same path from BASH_SOURCE (:251)."""
    _rc, out, _err = _bash(
        '%s; printf "%%s" "$(cd "$(dirname %s)/../../.." && pwd)/.ci/config/constants.sh"'
        % (SOURCE_SHIM, _q(str(paths.from_root(SHIM))))
    )
    assert out == str(toolchain.constants_file())


def test_checksums_reads_the_live_constants_file() -> None:
    """Both SHA families, both operating systems, resolved out of constants.sh.

    ANTI-VACUITY: an empty table would satisfy "every key matches the pattern", so the count and the specific keys are asserted.
    """
    table = toolchain.checksums(env={})
    for key in (
        "SHFMT_SHA256_LINUX_AMD64",
        "SHFMT_SHA256_LINUX_ARM64",
        "SHFMT_SHA256_DARWIN_AMD64",
        "SHFMT_SHA256_DARWIN_ARM64",
        "SHELLCHECK_SHA256_LINUX_X86_64",
        "SHELLCHECK_SHA256_LINUX_AARCH64",
        "SHELLCHECK_SHA256_DARWIN_X86_64",
        "SHELLCHECK_SHA256_DARWIN_AARCH64",
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", table[key]), key
    assert len(table) == 8, sorted(table)


def test_checksums_agree_with_what_bash_resolves() -> None:
    """The values, read the other way: source constants.sh and print them.

    Two parsers of one file is the drift this compares away. A regex that quietly stopped matching would give an empty table here and a full one in bash, and the acquisition would then refuse with "no checksum for ..." for a constant that is plainly present.
    """
    for key, value in sorted(toolchain.checksums(env={}).items()):
        rc, out, _err = _bash(
            'source %s; printf "%%s" "${%s:-}"' % (_q(str(paths.from_root(CONSTANTS))), key)
        )
        assert (rc, out) == (0, value), key


def test_the_checksum_short_circuit_is_the_twins() -> None:
    """Exporting either probe key suppresses the constants.sh read ENTIRELY.

    That is `_toolchain_need_checksums:249` and it is odd enough to be worth a
    case: one family's linux key blocks the file read for BOTH families.
    """
    for probe in toolchain.CHECKSUM_PROBE_KEYS:
        table = toolchain.checksums(env={probe: "f" * 64})
        assert table == {probe: "f" * 64}, probe
    # And the control: without either probe key, the file IS read.
    assert len(toolchain.checksums(env={"SHFMT_SHA256_DARWIN_ARM64": "e" * 64})) == 8


@pytest.mark.parametrize(("system", "expected"), [("Linux", "linux"), ("Darwin", "darwin")])
def test_os_name_matches_the_twin(system: str, expected: str) -> None:
    rc, out, _err = _bash('%s; uname() { printf "%s\\n"; }; _toolchain_os' % (SOURCE_SHIM, system))
    assert (rc, out) == (0, expected)
    assert toolchain.os_name(system) == expected


def test_os_name_refuses_an_unsupported_system() -> None:
    """No pinned build exists for it, so there is nothing to fall back to."""
    rc, _out, err = _bash('%s; uname() { printf "SunOS\\n"; }; _toolchain_os' % SOURCE_SHIM)
    assert rc == 1
    assert "unsupported OS 'SunOS'" in err
    with pytest.raises(toolchain.ToolError, match="unsupported OS 'SunOS'"):
        toolchain.os_name("SunOS")


def test_sha256_of_agrees_with_the_shell(tmp_path: pathlib.Path) -> None:
    """`hashlib` against `_toolchain_sha256sum`, on real bytes.

    This is the function whose bash counterpart needed a two-branch portability shim because macOS has no `sha256sum`. Proving the two agree is what lets that shim die rather than be translated.
    """
    sample = tmp_path / "blob"
    sample.write_bytes(b"the quick brown fox\n" * 5000)
    rc, out, _err = _bash("%s; _toolchain_sha256sum %s" % (SOURCE_SHIM, _q(str(sample))))
    assert rc == 0
    assert out.split()[0] == toolchain.sha256_of(sample)
    assert toolchain.sha256_of(sample) == hashlib.sha256(sample.read_bytes()).hexdigest()


def test_the_download_urls_are_the_twins() -> None:
    """The two asset URLs, built by bash and by Python from the same inputs.

    A URL is the one thing in the acquisition path that cannot be unit-tested by running it, so it is compared against the string the twin interpolates.
    """
    for want, os_key, arch in (
        ("3.13.1", "linux", "amd64"),
        ("3.13.1", "darwin", "arm64"),
    ):
        _rc, out, _err = _bash(
            "%s; want=%s; os=%s; arch=%s; "
            'printf "%%s" "https://github.com/mvdan/sh/releases/download/v${want}/'
            'shfmt_v${want}_${os}_${arch}"' % (SOURCE_SHIM, _q(want), _q(os_key), _q(arch))
        )
        assert out == toolchain.shfmt_url(want, os_key, arch)
    for want, os_key, arch in (
        ("0.10.0", "linux", "x86_64"),
        ("0.10.0", "darwin", "aarch64"),
    ):
        _rc, out, _err = _bash(
            "%s; want=%s; os=%s; arch=%s; "
            'printf "%%s" "https://github.com/koalaman/shellcheck/releases/download/v${want}/'
            'shellcheck-v${want}.${os}.${arch}.tar.xz"'
            % (SOURCE_SHIM, _q(want), _q(os_key), _q(arch))
        )
        assert out == toolchain.shellcheck_url(want, os_key, arch)


def test_the_arch_tables_disagree_because_the_upstreams_do() -> None:
    """shfmt publishes amd64/arm64; shellcheck publishes x86_64/aarch64.

    Collapsing the two tables would 404 on one of the two projects, and the 404 would name GitHub rather than the wrong arch spelling.
    """
    assert toolchain.SHFMT_ARCH["x86_64"] == "amd64"
    assert toolchain.SHELLCHECK_ARCH["x86_64"] == "x86_64"
    assert toolchain.SHFMT_ARCH["aarch64"] == "arm64"
    assert toolchain.SHELLCHECK_ARCH["aarch64"] == "aarch64"
    text = paths.from_root(SHIM).read_text(encoding="utf-8")
    assert "x86_64 | amd64) arch=amd64 ;;" in text
    assert "x86_64 | amd64) arch=x86_64 ;;" in text


def test_download_shfmt_refuses_rather_than_downloading_unverified(
    tmp_path: pathlib.Path,
) -> None:
    """No checksum for this os/arch means REFUSE, and name the constant to add.

    THE MESSAGE NAMES THE CONSTANT, not the arch, because that is the difference between something a reader can act on and something they have to decode.
    """
    binary, messages = toolchain.download_shfmt(
        "3.13.1",
        tmp_path / "cache",
        tmp_path / "cache" / "shfmt",
        env={"SHFMT_SHA256_LINUX_AMD64": "0" * 64},
        machine="riscv64",
        system="Linux",
    )
    assert binary is None
    assert messages == [
        (
            "toolchain: no pinned shfmt checksum for riscv64; add one rather than "
            "downloading unverified"
        )
    ]
    assert not (tmp_path / "cache").exists(), "it created a cache before refusing"

    binary, messages = toolchain.download_shfmt(
        "3.13.1",
        tmp_path / "cache",
        tmp_path / "cache" / "shfmt",
        env={"SHFMT_SHA256_LINUX_AMD64": "0" * 64},
        machine="arm64",
        system="Darwin",
    )
    assert binary is None
    assert messages == [
        (
            "toolchain: no shfmt checksum for darwin/arm64 -- define "
            "SHFMT_SHA256_DARWIN_ARM64 in .ci/config/constants.sh (and source it) "
            "rather than downloading unverified"
        )
    ]


def test_download_shfmt_refuses_a_checksum_mismatch(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MISMATCH branch, with a real digest in the `actual` line.

    DEFECT 2 in the module docstring is exactly that the twin can print this headline with an EMPTY `actual` when there is no hashing tool at all. `hashlib` cannot be absent, so `actual` is always a real digest here, and this case pins that.
    """

    def fake_curl(_url: str, target: pathlib.Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not the real binary")
        return True

    monkeypatch.setattr(toolchain, "_curl", fake_curl)
    cache = tmp_path / "cache"
    binary = cache / "shfmt"
    got, messages = toolchain.download_shfmt(
        "3.13.1",
        cache,
        binary,
        env={"SHFMT_SHA256_LINUX_AMD64": "0" * 64},
        machine="x86_64",
        system="Linux",
    )
    assert got is None
    assert messages[0] == "toolchain: shfmt checksum MISMATCH -- refusing to install"
    assert messages[1] == "  expected " + "0" * 64
    assert re.fullmatch(r"  actual   [0-9a-f]{64}", messages[2]), messages[2]
    assert messages[2].split()[-1] == hashlib.sha256(b"not the real binary").hexdigest()
    assert not binary.exists()
    # ASSERT ON THE DIRECTORY, NOT ON ONE NAME. This used to read `not binary.with_name("shfmt.tmp").exists()`, which was exact while the temp path was the fixed `$bin.tmp`. The concurrency fix gives every process a `mktemp` name, and that assertion would then have passed for the only bad reason there is -- it names a file that can no longer exist under any behaviour, so it could
    # not fail. An empty cache is the claim that was always meant, and it is strictly stronger.
    assert sorted(p.name for p in cache.iterdir()) == [], "the rejected download was left behind"


def test_download_shfmt_installs_a_matching_download(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CONTROL for the case above: a correct hash must install and chmod +x.

    Without this, a `download_shfmt` that refused unconditionally would pass every refusal case in this file.
    """
    payload = b"#!/bin/sh\necho v3.13.1\n"

    def fake_curl(_url: str, target: pathlib.Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return True

    monkeypatch.setattr(toolchain, "_curl", fake_curl)
    cache = tmp_path / "cache"
    binary = cache / "shfmt"
    got, messages = toolchain.download_shfmt(
        "3.13.1",
        cache,
        binary,
        env={"SHFMT_SHA256_LINUX_AMD64": hashlib.sha256(payload).hexdigest()},
        machine="x86_64",
        system="Linux",
    )
    assert (got, messages) == (str(binary), [])
    assert os.access(str(binary), os.X_OK)
    assert binary.read_bytes() == payload


# --------------------------------------------------------------------------- concurrent acquisition ---------------------------------------------------------------------------
#
# THE PYTEST SUITE ITSELF IS THE CONCURRENT CALLER. It runs under xdist with several workers, and more than one of its modules shells out to a gate that acquires shfmt, so a cold cache is hit by many processes at once. Both download helpers wrote to ONE fixed temp path, which made that data corruption rather than redundant work: `curl -o` truncates, so the racers interleaved writes
# into a single inode, and the winner's `mv` renamed it out
# from under the losers mid-verify. The losers then reported
# "checksum MISMATCH -- refusing to install" with an EMPTY `actual` -- a race accusing the download of being tampered with -- and the losers' curls kept writing into the now-installed inode, so the binary at the final path could be torn while already executable. CI job 104650234908 is that: `shfmt.sh: line 63: .../shfmt: cannot execute`, from a gate whose tool had just been
# "installed".
#
# Measured before the fix, 8 racers into a cold cache: 7 failed. After: 8/8.

_RACERS = 8

# A curl that writes its payload in CHUNKS. The window between "started writing" and "finished writing" has to be wide enough to race DELIBERATELY, or this
# case would only fail on an unlucky day and would prove nothing on a good one.
_CHUNK = b"payload-"
_CHUNKS = 12
_PAYLOAD = _CHUNK * _CHUNKS

_STUB_CURL = """#!/usr/bin/env bash
out=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o)
            out="$2"
            shift 2
            ;;
        *) shift ;;
    esac
done
: >"$out"
for ((i = 0; i < %d; i++)); do
    printf '%%s' '%s' >>"$out"
    sleep 0.02
done
""" % (_CHUNKS, _CHUNK.decode())

# The OLD shape, kept verbatim as a planted regression. Racing it must FAIL, or the harness above is not actually producing a window and the real case below would pass for no reason.
_OLD_SHAPE = """
old_shape() {
    local cache="$1" bin="$2"
    curl -fsSL -o "$bin.tmp" http://stub/shfmt || return 1
    echo "$WANT_SHA  $bin.tmp" | sha256sum -c - >/dev/null 2>&1 || {
        rm -f "$bin.tmp"
        return 1
    }
    chmod +x "$bin.tmp" && mv "$bin.tmp" "$bin" || return 1
}
"""


def _race(tmp_path: pathlib.Path, body: str) -> tuple[list[int], pathlib.Path]:
    """Run `body` in `_RACERS` concurrent subshells; return exit codes and the cache."""
    stub = tmp_path / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    (stub / "curl").write_text(_STUB_CURL, encoding="utf-8")
    (stub / "curl").chmod(0o755)
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    rc_file = tmp_path / "rcs"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        'set -u\nsource "$TOOLCHAIN_SH"\n%s\n'
        "for ((i = 0; i < %d; i++)); do\n"
        '    ( %s >/dev/null 2>&1; echo "$?" >>"$RC" ) &\n'
        "done\nwait\n" % (_OLD_SHAPE, _RACERS, body),
        encoding="utf-8",
    )
    sha = hashlib.sha256(_PAYLOAD).hexdigest()
    env = diff.env_for()
    env["PATH"] = "%s:%s" % (stub, env.get("PATH", ""))
    env["TOOLCHAIN_SH"] = str(paths.from_root(".ci/scripts/lib/toolchain.sh"))
    env["RC"] = str(rc_file)
    env["CACHE"] = str(cache)
    env["WANT_SHA"] = sha
    # Both arches, so the case does not silently skip its own subject on arm64.
    env["SHFMT_SHA256_LINUX_AMD64"] = sha
    env["SHFMT_SHA256_LINUX_ARM64"] = sha
    subprocess.run(["bash", str(driver)], env=env, check=True, timeout=300)
    codes = [int(line) for line in rc_file.read_text(encoding="utf-8").split()]
    assert len(codes) == _RACERS, codes
    return codes, cache


def test_a_fixed_temp_path_loses_the_race(tmp_path: pathlib.Path) -> None:
    """CONTROL, and it must come first: the planted OLD shape has to break here.

    If this passes, the harness is not producing a real window and the case below proves nothing.
    """
    codes, _ = _race(tmp_path, 'old_shape "$CACHE" "$CACHE/shfmt"')
    assert any(rc != 0 for rc in codes), (
        "the shared-temp shape survived %d concurrent downloads; the window is gone "
        "and this control can no longer fire" % _RACERS
    )


def test_concurrent_downloads_all_succeed_and_install_an_intact_binary(
    tmp_path: pathlib.Path,
) -> None:
    """The real helper, raced the same way: every caller succeeds, bytes intact."""
    codes, cache = _race(tmp_path, '_toolchain_download_shfmt 3.13.1 "$CACHE" "$CACHE/shfmt"')
    assert codes == [0] * _RACERS, codes
    binary = cache / "shfmt"
    assert binary.read_bytes() == _PAYLOAD, "the installed binary is torn"
    assert os.access(str(binary), os.X_OK)
    assert binary.stat().st_mode & 0o777 == 0o755
    assert sorted(p.name for p in cache.iterdir()) == ["shfmt"], "a temp file leaked"


def test_acquire_returns_a_path_binary_at_the_pin_without_installing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PATH binary AT THE PIN always wins, so nothing is downloaded.

    That is what makes a developer's own install honoured and stops CI re-downloading on every invocation.
    """
    binary = _stub_dir(tmp_path, "shfmt", 'printf "v%s\\n"' % toolchain.pin_for("shfmt"))
    monkeypatch.setenv("PATH", "%s:%s" % (binary.parent, SYSTEM_PATH))

    def explode(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("acquire tried to download a tool that was already at the pin")

    monkeypatch.setattr(toolchain, "_curl", explode)
    got, messages = toolchain.acquire("shfmt")
    assert (got, messages) == (str(binary), [])


def test_acquire_refuses_a_tool_with_no_pin() -> None:
    """`toolchain_acquire cargo` is rc 2 and silent, on both sides."""
    rc, out, err = _bash("%s; toolchain_acquire cargo" % SOURCE_SHIM)
    assert (rc, out, err) == (2, "", "")
    got, messages = toolchain.acquire("cargo")
    assert (got, messages) == (None, [])


def test_acquire_refuses_an_empty_pin() -> None:
    """The guard duplicated from `check`; its ABSENCE here was the 404 defect.

    `.ci/scripts/lib/toolchain.sh:451-457` records it: one entry point refused
    while the other interpolated the empty string into a download URL.
    """
    got, messages = toolchain.acquire("shfmt", pins={"SHFMT_VERSION": ""})
    assert got is None
    assert messages == ["toolchain: pin for 'shfmt' is empty -- the pins file did not load"]


# --------------------------------------------------------------------------- The twin's defects, pinned so they cannot rot ---------------------------------------------------------------------------


def test_defect_1_toolchain_sh_verify_cannot_fail() -> None:
    """DRIVEN, not read: six MISMATCH rows and exit 0. See the module docstring.

    RED WHEN THE TWIN IS FIXED. Adding `exit` to the `--verify` arm (or moving the dispatch block to the end of the file) makes this case fail, which is when the finding closes with evidence rather than being forgotten.
    """
    shell_env = diff.env_for(PATH=SYSTEM_PATH)
    rc, out, _err = diff.bash_streams(
        "bash %s --verify" % _q(str(paths.from_root(SHIM))), env=shell_env
    )
    assert out.count("MISMATCH") == 6, out
    assert rc == 0, "toolchain.sh --verify now fails on a mismatch; delete this pin"
    # And the FUNCTION, which is correct, so the finding is localised to the dispatch rather than smeared over the whole file.
    frc, _fout, _ferr = diff.bash_streams(
        "%s; toolchain_report --verify" % SOURCE_SHIM, env=shell_env
    )
    assert frc == 1, "the function's rc was already right; re-derive the finding"


def test_defect_1_has_a_live_variant_on_env() -> None:
    """`--env` with no pins file: exit 0 and ZERO bytes, into $GITHUB_ENV.

    Two live call sites, `.github/workflows/ci-quality.yml:171` and `:1897`. Run against a COPY of the library under a fake root, so the real pins file is never touched.
    """
    with tempfile.TemporaryDirectory() as scratch:
        fake = pathlib.Path(scratch, ".ci", "scripts", "lib")
        fake.mkdir(parents=True)
        copy = fake / "toolchain.sh"
        copy.write_bytes(paths.from_root(SHIM).read_bytes())
        rc, out, err = diff.bash_streams("bash %s --env" % _q(str(copy)))
        assert rc == 0, "the --env arm now exits non-zero; delete this pin"
        assert out == "", out
        assert "No such file or directory" in err
    # THE CALL SITES, so the finding's blast radius is asserted and not claimed.
    workflow = paths.from_root(".github/workflows/ci-quality.yml").read_text(encoding="utf-8")
    assert workflow.count('.ci/scripts/lib/toolchain.sh --env >> "$GITHUB_ENV"') == 2


def test_defect_1_the_port_does_not_reproduce_the_always_zero_exit() -> None:
    """`... core.toolchain verify` MUST exit 1 where the twin exits 0.

    The defect is in the twin's SCRIPT DISPATCH, not in the library function, and this module is the library. Reproducing an always-green exit here would be porting a vacuity into the replacement.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.toolchain", "verify"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.from_root(".ci")),
        env={**os.environ, "PATH": SYSTEM_PATH, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.stdout.count("MISMATCH") == 6, proc.stdout
    assert proc.returncode == 1


def test_defect_2_both_checksum_call_sites_still_swallow_the_helpers_message() -> None:
    """`| _toolchain_sha256sum -c - >/dev/null 2>&1` at :344 and :429.

    The helper exists so that "a verifier that cannot run must not read as a verifier that failed" (:264-265), and both callers discard the message that would say which of the two it was.
    """
    text = paths.from_root(SHIM).read_text(encoding="utf-8")
    swallowed = re.findall(r"\| _toolchain_sha256sum -c - >/dev/null 2>&1", text)
    assert len(swallowed) == 2, "the call-site count moved: %d" % len(swallowed)
    assert "no sha256 tool on PATH" in text, "the helper's message is gone; re-derive"


def test_defect_2_the_headline_still_says_mismatch_with_no_verifier(
    tmp_path: pathlib.Path,
) -> None:
    """DRIVEN with neither `sha256sum` nor `shasum` reachable.

    The distinguishing line survives only via the SECOND, unredirected call inside the `actual` line, so it lands out of order and `actual` is empty
    while the headline still says MISMATCH.
    """
    sandbox = tmp_path / "bin"
    sandbox.mkdir()
    # `mktemp` joined this list when the download helpers stopped sharing one fixed temp path between concurrent acquirers. It is coreutils, the same tier as `cut` and `tr` already here; without it the helper fails CLOSED ("mktemp: command not found", rc 1, nothing installed), which is the right behaviour but not the one this control is driving at.
    needed = (
        "mkdir",
        "chmod",
        "mv",
        "rm",
        "cut",
        "tr",
        "uname",
        "dirname",
        "grep",
        "sed",
        "mktemp",
    )
    for name in needed:
        found = shutil.which(name)
        if found:
            (sandbox / name).symlink_to(found)
    if not all((sandbox / n).exists() for n in ("mkdir", "rm", "tr", "uname", "cut", "mktemp")):
        pytest.skip("this host does not have the coreutils this control needs")
    (sandbox / "curl").write_text(
        '#!/bin/bash\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; '
        '*) shift;; esac; done\nprintf "junk" > "$out"\n',
        encoding="utf-8",
    )
    (sandbox / "curl").chmod(0o755)
    assert shutil.which("sha256sum", path=str(sandbox)) is None
    assert shutil.which("shasum", path=str(sandbox)) is None

    cache = tmp_path / "cache"
    cache.mkdir()
    script = "set -uo pipefail\n%s\nexport PATH=%s\n_toolchain_download_shfmt 3.13.1 %s %s\n" % (
        SOURCE_SHIM,
        _q(str(sandbox)),
        _q(str(cache)),
        _q(str(cache / "shfmt")),
    )
    rc, _out, err = _bash(script)
    assert rc != 0
    assert "checksum MISMATCH -- refusing to install" in err
    assert "no sha256 tool on PATH" in err
    assert re.search(r"^  actual   *$", err, re.MULTILINE), err


def test_defect_3_the_darwin_comments_are_stale() -> None:
    """Both constants the twin's comments tell a reader to ADD already exist.

    Documentation only: no behaviour is wrong. Pinned so that whoever rewrites the comments can see that this case was the reason.
    """
    twin = paths.from_root(SHIM).read_text(encoding="utf-8")
    assert "Only the LINUX_* pair exists in constants.sh today" in twin
    assert "adding the two DARWIN_*" in twin
    constants = paths.from_root(CONSTANTS).read_text(encoding="utf-8")
    for key in (
        "SHFMT_SHA256_DARWIN_AMD64",
        "SHFMT_SHA256_DARWIN_ARM64",
        "SHELLCHECK_SHA256_DARWIN_X86_64",
        "SHELLCHECK_SHA256_DARWIN_AARCH64",
    ):
        assert "readonly %s=" % key in constants, key


# --------------------------------------------------------------------------- The planted defect: this differential must be able to FAIL ---------------------------------------------------------------------------

ACQ_MUTATIONS = (
    (
        "the go probe reads the wrong field",
        '        index = 2 if tool == "go" else 1',
        "        index = 1",
    ),
    (
        "the version prefixes stop being stripped",
        "    for prefix in VERSION_PREFIXES:\n        raw = raw.removeprefix(prefix)\n    matched = [",
        "    for prefix in ():\n        raw = raw.removeprefix(prefix)\n    matched = [",
    ),
    (
        "a node major mismatch becomes a pass",
        '        major = actual.split(".", 1)[0]\n        if major != pin_value:',
        '        major = actual.split(".", 1)[0]\n        if major == pin_value and False:',
    ),
)


@pytest.mark.parametrize(
    ("name", "find", "replace"), list(ACQ_MUTATIONS), ids=[m[0] for m in ACQ_MUTATIONS]
)
def test_a_planted_defect_makes_the_probe_differential_fail(
    tmp_path: pathlib.Path, name: str, find: str, replace: str
) -> None:
    """A MUTATED COPY must disagree with the twin on a case the real one passes.

    THE REAL FILE IS NEVER TOUCHED: the whole package is copied under `tmp_path`, mutated there, run in a child interpreter, and the real file's sha256 is re-asserted at the end.
    """
    real = paths.from_root(".ci/rediacc_ci/core/toolchain.py")
    before = hashlib.sha256(real.read_bytes()).hexdigest()

    package = tmp_path / "pkg" / "rediacc_ci"
    shutil.copytree(
        paths.from_root(".ci/rediacc_ci"),
        package,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    (package / "tests").mkdir()
    (package / "tests" / "__init__.py").write_text("", encoding="utf-8")
    target = package / "core" / "toolchain.py"
    text = target.read_text(encoding="utf-8")
    assert text.count(find) == 1, "the mutation anchor %r moved" % name
    target.write_text(text.replace(find, replace), encoding="utf-8")

    # One stub per tool, plus a node at the WRONG major so the third mutation has a case to be wrong about.
    for tool, bodies in PROBE_FIXTURES.items():
        _stub_dir(tmp_path, tool, bodies[0])
    _stub_dir(tmp_path, "node", 'printf "v20.1.1\\n"')
    path_env = "%s:%s" % (tmp_path / "bin", SYSTEM_PATH)

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "from rediacc_ci.core import toolchain as m\n"
        "tools, path_env = json.load(sys.stdin)\n"
        "out = {}\n"
        "for tool in tools:\n"
        "    answer = m.probe_version(tool, %r + '/' + tool)\n"
        "    result = m.check(tool, path=path_env)\n"
        "    out[tool] = [answer, result.binary, result.rc, list(result.messages)]\n"
        "json.dump(out, sys.stdout)\n" % (str(tmp_path / "pkg"), str(tmp_path / "bin")),
        encoding="utf-8",
    )
    tools = sorted(PROBE_FIXTURES)
    proc = subprocess.run(
        [sys.executable, str(probe)],
        input=json.dumps([tools, path_env]),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    mutant = json.loads(proc.stdout)

    honest_agrees = 0
    mutant_disagrees = 0
    for tool in tools:
        binary = str(tmp_path / "bin" / tool)
        brc, bout, _berr = _bash(
            "%s; toolchain_probe_version %s %s" % (SOURCE_SHIM, _q(tool), _q(binary))
        )
        crc, cout, cerr = _bash(
            "%s; PATH=%s toolchain_check %s" % (SOURCE_SHIM, _q(path_env), _q(tool))
        )
        honest = toolchain.probe_version(tool, binary)
        honest_check = toolchain.check(tool, path=path_env)
        if (bout, brc) == ((honest or ""), (0 if honest else 1)):
            honest_agrees += 1
        assert (cout, cerr, crc) == (
            honest_check.binary or "",
            "".join(m + "\n" for m in honest_check.messages),
            honest_check.rc,
        ), "the UNMUTATED check already disagrees on %s" % tool
        got_probe, got_bin, got_rc, got_msgs = mutant[tool]
        if (bout, brc) != ((got_probe or ""), (0 if got_probe else 1)):
            mutant_disagrees += 1
        if (cout, cerr, crc) != (got_bin or "", "".join(m + "\n" for m in got_msgs), got_rc):
            mutant_disagrees += 1

    assert honest_agrees == len(tools), "the UNMUTATED module already disagrees; fix that first"
    assert mutant_disagrees > 0, "the mutation %r changed nothing the differential can see" % name
    assert hashlib.sha256(real.read_bytes()).hexdigest() == before, "the real port was modified"
    assert real.read_text(encoding="utf-8").count(find) == 1


# --------------------------------------------------------------------------- The CLI verbs the acquisition half added ---------------------------------------------------------------------------


def _module_cli(args: list[str], **env: str) -> subprocess.CompletedProcess:
    """`python3 -m rediacc_ci.core.toolchain <args>` with an EXPLICIT environment.

    The environment is replaced rather than extended, for the reason `differential.env_for` gives: a case that inherits the developer's shell passes or fails depending on whether they happen to export $CI_TEMP.
    """
    base = {
        "PATH": SYSTEM_PATH,
        "HOME": diff.BASE_ENV["HOME"],
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    base.update(env)
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.toolchain", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.from_root(".ci")),
        env=base,
    )


def test_cli_lane_and_cache_dir_agree_with_the_functions() -> None:
    """Both verbs are read with `v="$(...)"`, so stdout must carry only a value."""
    lane = _module_cli(["lane"])
    assert (lane.returncode, lane.stderr) == (0, "")
    assert lane.stdout.strip() in ("ci", "devbox", "host")

    cache = _module_cli(["cache-dir"], CI_TEMP="/fixture-temp")
    assert (cache.returncode, cache.stderr) == (0, "")
    assert cache.stdout.strip() == "/fixture-temp/rediacc-toolchain"


def test_cli_check_puts_the_path_on_stdout_and_the_refusal_on_stderr() -> None:
    """`bin="$(... check X)" || die` must never capture a diagnostic as a value."""
    absent = _module_cli(["check", "shfmt"])
    assert absent.returncode == 1
    assert absent.stdout == ""
    assert absent.stderr.startswith("toolchain: shfmt is not on PATH (pinned at ")

    unknown = _module_cli(["check", "cargo"])
    assert unknown.returncode == 2
    assert unknown.stdout == ""
    assert unknown.stderr == "toolchain: no pin defined for 'cargo'\n"


def test_cli_probe_reports_a_tool_with_no_arm_as_2_not_1(tmp_path: pathlib.Path) -> None:
    """1 is "it would not say a version"; 2 is "I have no probe for that at all"."""
    binary = _stub_dir(tmp_path, "shfmt", 'printf "v3.13.1\\n"')
    good = _module_cli(["probe", "shfmt", str(binary)])
    assert (good.returncode, good.stdout.strip()) == (0, "3.13.1")

    silent = _stub_dir(tmp_path, "actionlint", 'printf "no version\\n"')
    quiet = _module_cli(["probe", "actionlint", str(silent)])
    assert (quiet.returncode, quiet.stdout) == (1, "")

    unknown = _module_cli(["probe", "cargo", "/bin/true"])
    assert unknown.returncode == 2
    assert "no version probe" in unknown.stderr


def test_cli_report_refuses_rather_than_printing_a_table_of_blanks(
    tmp_path: pathlib.Path,
) -> None:
    """A missing pins file is rc 2, matching `toolchain_load || return 2` at :186.

    Driven against a COPY of the package under a fake root, so the real pins file is never moved. `$REDIACC_CI_ROOT` is the same seam `paths` documents
    for exactly this.
    """
    root = tmp_path / "fakeroot"
    shutil.copytree(
        paths.from_root(".ci/rediacc_ci"),
        root / ".ci" / "rediacc_ci",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    (root / ".ci" / "rediacc_ci" / "tests").mkdir()
    (root / ".ci" / "rediacc_ci" / "tests" / "__init__.py").write_text("", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.toolchain", "report"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root / ".ci"),
        env={
            "PATH": SYSTEM_PATH,
            "HOME": diff.BASE_ENV["HOME"],
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "REDIACC_CI_ROOT": str(root),
        },
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert proc.stdout == "", "a refusal printed a table"
    assert "toolchain" in proc.stderr
    # AND THE CONTROL: the same invocation against the REAL root prints a table.
    real = _module_cli(["report"])
    assert real.returncode == 0
    assert "lane: " in real.stdout


def test_the_temp_name_mask_hides_the_temp_and_nothing_else() -> None:
    """`differential.mask_toolchain_tmp` is load-bearing in two differentials.

    It is the one token those comparisons deliberately stop checking, so it has to be narrow. The second half is the control: a mask that swallowed the version, the URL or the real binary's name would make both differentials pass on a genuine divergence, which is worse than the drift it was added to absorb.
    """
    assert (
        diff.mask_toolchain_tmp("/c/rediacc-toolchain/shfmt-3.13.1/shfmt.1R2NkECK")
        == "/c/rediacc-toolchain/shfmt-3.13.1/shfmt.<tmp>"
    )
    assert (
        diff.mask_toolchain_tmp("/c/shellcheck-0.10.0/sc.wlea__5l/sc.tar.xz")
        == "/c/shellcheck-0.10.0/sc.<tmp>/sc.tar.xz"
    )
    # Both alphabets, because the two sides do not share one.
    assert diff.mask_toolchain_tmp("/x/shfmt.abcdefgh") == "/x/shfmt.<tmp>"
    assert (
        diff.mask_toolchain_tmp("/c/actionlint-1.7.12/al.WxWibLSj/actionlint.tar.gz")
        == "/c/actionlint-1.7.12/al.<tmp>/actionlint.tar.gz"
    )
    assert diff.mask_toolchain_tmp("/x/shfmt.AB90_xyz") == "/x/shfmt.<tmp>"

    for untouched in (
        "/c/rediacc-toolchain/shfmt-3.13.1/shfmt",  # the installed binary
        ".ci/scripts/security/shfmt.sh",  # the twin itself
        "https://github.com/mvdan/sh/releases/download/v3.13.1/shfmt_v3.13.1_linux_amd64",
        "/x/shfmt.short",  # 5 chars, not a mktemp suffix
        "/x/shfmt.toooolong9",  # 10 chars
        "shfmt.1R2NkECK",  # no leading separator: not a path component we emit
    ):
        assert diff.mask_toolchain_tmp(untouched) == untouched, untouched
