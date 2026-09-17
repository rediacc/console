"""`rediacc_ci.quality.toolchain_pins` against the shell pipelines it replaces.

WHY A DIFFERENTIAL. A1's detector is a three-stage grep pipeline whose behaviour on a comment, on a line that READS the pin, and on a line that restates it is decided by grep's `-F`/`-v` semantics rather than by anything a reader could infer, and the twin's own comments record two false positives it produced. A6's detector is four chained greps with three exemptions, each added
after a measured false positive with a run id attached. Both are run for real here.

The whole gate is covered by `.ci/shadow/w7p2-toolchain-pins.observations.jsonl` over five distinct trees.
"""

import os
import pathlib

import pytest

from rediacc_ci.quality import toolchain_pins as mod
from rediacc_ci.tests import differential as diff

# The A1 pipeline's cases. The comment names the property each is here for.
A1_CASES = [
    'run: pip install "ruff==9.9.9"\n',  # a literal restatement
    'run: pip install "ruff==${RUFF_VERSION}"\n',  # READING the pin
    "# we bumped ruff to 9.9.9 last week\n",  # prose about the pin
    "    # indented prose about 9.9.9\n",  # an indented comment
    "nothing to see\n",  # never names the value
    "RUFF_VERSION=9.9.9\n",  # the definition itself names the key
    "url=https://x/9.9.9/ruff.tar # RUFF_VERSION\n",  # names both
]


@pytest.mark.parametrize("content", A1_CASES)
def test_restates_matches_the_grep_pipeline(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "subject.yml"
    target.write_text(content, encoding="utf-8")
    script = (
        "grep -F '9.9.9' subject.yml 2>/dev/null | "
        "grep -vE '^[[:space:]]*#' | grep -qvF 'RUFF_VERSION'"
    )
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert mod.restates(target, "RUFF_VERSION", "9.9.9") is (code == 0)


# A6's cases. Three of these are the exact false positives the twin's comments record, with their dates and run ids.
A6_CASES = [
    "shellcheck -S warning foo.sh\n",  # a real invocation
    "# run shellcheck here\n",  # a comment
    'echo "# shellcheck extended-analysis=false"\n',  # 2026-08-26, run 32907xxx
    "NPX_TOOLS=(ruff go shfmt shellcheck actionlint)\n",  # 2026-08-28, run 98854256844
    "echo x; shfmt -d .\n",  # the echo drop must not be a bypass
    "printf 'shfmt is a tool'\n",  # printf prose
    'BIN="$(toolchain_acquire shellcheck)"\n',  # a pinned acquisition
    "grep shfmt file\n",  # names the tool as an argument
    "",  # empty
]


@pytest.mark.parametrize("content", A6_CASES)
def test_invocation_detector_matches_the_grep_chain(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "gate.sh"
    target.write_text(content, encoding="utf-8")
    script = (
        "grep -vE '^[[:space:]]*#' gate.sh | "
        "grep -vE '^[[:space:]]*(echo|printf)[[:space:]][^;&|]*$' | "
        "grep -vE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=\\([^)]*\\)[[:space:]]*$' | "
        "grep -qE '(^|[;&|(]|[[:space:]])(shfmt|shellcheck|ruff|actionlint)[[:space:]]'"
    )
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert mod.invokes_gated_tool(mod.read_lines(target)) is (code == 0)


PIN_LINES = [
    "RUFF_VERSION=0.16.1\n",
    "# RUFF_VERSION=0.16.1\n",
    "ruff_version=0.16.1\n",  # lowercase is not a pin line
    "RUFF_VERSION=has a space\n",
    'RUFF_VERSION="quoted"\n',
    "RUFF_VERSION=$OTHER\n",
    "K=a=b\n",
]


@pytest.mark.parametrize("line", PIN_LINES)
def test_pin_line_and_unparseable_match_grep(tmp_path: pathlib.Path, line: str) -> None:
    target = tmp_path / "toolchain.env"
    target.write_text(line, encoding="utf-8")
    counted, _out, _err = diff.bash_streams(
        "grep -cE '^[A-Z][A-Z0-9_]*=' toolchain.env", cwd=str(tmp_path)
    )
    del counted
    code, out, _err = diff.bash_streams(
        "grep -cE '^[A-Z][A-Z0-9_]*=' toolchain.env || true", cwd=str(tmp_path)
    )
    assert code == 0
    expected_keys = int(out.strip())
    assert sum(1 for candidate in [line] if mod.PIN_LINE_RE.match(candidate)) == expected_keys

    bad_code, _bad_out, _bad_err = diff.bash_streams(
        """grep -qE '^[A-Z][A-Z0-9_]*=.*[ "'"'"'$]' toolchain.env""", cwd=str(tmp_path)
    )
    assert bool(mod.UNPARSEABLE_PIN_RE.match(line)) is (bad_code == 0)


def test_a9_executes_the_pin_rather_than_reading_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A1-A8 were all green while `toolchain_pin_for` returned "" with status 0.

    The empty value travelled into a download URL and produced a curl 404 naming GitHub, which is the wrong problem to go debugging. A9 exists because no textual assertion could have caught it.

    THE `*_VERSION` NAMES ARE CLEARED FIRST, and without that the mutant half of this test measures the ENVIRONMENT instead of the library. `pin_from_bare_
    source` shells out and inherits `os.environ`; a CI lane runs
    `.ci/scripts/lib/toolchain.sh --env >> "$GITHUB_ENV"`, which exports
    `SHELLCHECK_VERSION=0.10.0` into every later step. So the mutant -- a copy of
    the library with `toolchain_load` stubbed to a no-op, whose whole purpose is to resolve EMPTY -- happily resolved `0.10.0` from the ambient environment,
    and this assertion read `assert '0.10.0' == ''` in run 34970782616. On a
    developer shell nothing exports those names, so it passed for a reason that had nothing to do with the code under test.
    """
    for name in [key for key in os.environ if key.endswith("_VERSION")]:
        monkeypatch.delenv(name, raising=False)
    library = pathlib.Path(".ci/scripts/lib/toolchain.sh").resolve()
    assert mod.pin_from_bare_source(library, "shellcheck") != ""
    mutant = tmp_path / "toolchain.sh"
    mutant.write_text(
        library.read_text(encoding="utf-8") + "\ntoolchain_load() { return 0; }\n",
        encoding="utf-8",
    )
    assert mod.pin_from_bare_source(mutant, "shellcheck") == ""
