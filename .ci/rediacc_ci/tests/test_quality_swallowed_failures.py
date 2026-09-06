"""`rediacc_ci.quality.swallowed_failures` against the awk scanner it replaces.

WHY A DIFFERENTIAL. This gate is one 150-line awk program with four rules, a
two-pass line folder and a 12-line lookahead window, and its own history is a
version that died on all 42 files while printing "OK: no gate captures a
probe...". Comparing the port against the real awk on the same input is the only
form of this test that can fail for the right reason.

The whole gate is covered by
`.ci/shadow/w7p2-swallowed-failures.observations.jsonl` over five distinct trees.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import swallowed_failures as mod

# The awk program, extracted from the twin at run time rather than copied. A
# copy would drift; extracting it means this test breaks LOUDLY when the twin's
# scanner is edited, which is exactly when it should be re-read.
TWIN = pathlib.Path(".ci/scripts/quality/check-swallowed-failures.sh")


def _awk_program() -> str:
    """The `awk -v file="$1" '<program>'` body, as text.

    Sliced between the two markers rather than by line number: a line number
    churns the day a paragraph moves above it, and this file's header is edited
    often.
    """
    text = TWIN.read_text(encoding="utf-8")
    start = text.index('    awk -v file="$1" \'')
    body_start = text.index("'", start + len('    awk -v file="$1" ')) + 1
    end = text.index('\n    \' "$1" >"$AWK_OUT"', body_start)
    return text[body_start:end]


# Every shape the scanner has to get right. The comment names the property.
BODIES = [
    (
        'outdated=$(go list -u -m -json all 2>/dev/null |\n    jq -rs "." 2>/dev/null || true)\n'
        'while IFS=" " read -r path current latest uptime; do :; done <<<"$outdated"\n'
    ),
    "rm -rf /tmp/x || true\n",  # a bare cleanup is not a capture
    'tree_all="$(npm ls --all || true)"\n',  # the quoted capture spelling
    "v=$(probe || :)\n",
    "v=$(probe || echo)\n",
    'v=$(probe || echo "")\n',
    'v=$(probe || echo "[]")\n',
    "v=$(probe || echo unavailable)\n",  # a real sentinel
    "v=$(probe || echo 000)\n",  # also a sentinel
    "v=$(probe)\n",  # no fallback
    "v=$(probe 2>&1 || true)\n",  # stderr folded in
    "v=$(grep -q x f || true)\n",  # an answer command
    "v=$(command -v jq || true)\n",
    "v=$(diff a b || true)\n",
    'v=$(probe || true)\nif [[ -z "$v" ]]; then\nlog_error "probe failed"\nfi\n',
    'v=$(probe || true)\nif [[ -z "$v" ]]; then\nexit 0\nfi\n',
    "v=$(probe || true)\necho done\n",
    'v=$(probe || true)\nif [[ -z "$other" ]]; then\nlog_error x\nfi\n',
    'v=$(probe || true)\nif ((v > 0)); then\nlog_error "bad"\nfi\n',
    'v=$(probe || true)\nif jq -e . <<<"$v"; then\nlog_error x\nfi\n',
    'f() {\nv=$(probe || true)\n}\ng() {\nlog_error "unrelated"\n}\n',
    (
        "# swallowed-failure-ok: a long enough reason to clear the blocker bar here\n"
        "v=$(probe || true)\n"
    ),
    "# swallowed-failure-ok: reason\n# an intervening comment\nv=$(probe || true)\n",
    "v=$(probe || true\n",  # an unterminated buffer through EOF
    "local v=$(probe || true)\necho x\n",
    "export V=$(probe || true)\necho x\n",
    "",  # empty file
]


@pytest.mark.parametrize("body", BODIES)
def test_scanner_matches_the_twins_awk(tmp_path: pathlib.Path, body: str) -> None:
    target = tmp_path / "subject.sh"
    target.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        ["awk", "-v", "file=%s" % target, _awk_program(), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", "a warning means the program running is not the one written"

    expected = []
    for line in proc.stdout.split("\n"):
        if line == "":
            continue
        fields = line.split("\t")
        expected.append((fields[0], fields[2], fields[3]))

    got = [(row.kind, str(row.line), row.var) for row in mod.scan_text(body, str(target))]
    assert got == expected


def test_the_blocker_bar_on_waiver_reasons() -> None:
    """A waiver reopens the hole this gate closes, so it meets the BLOCKER bar."""
    assert validate("the empty case genuinely means the same thing here") is True
    assert validate("todo") is False
    assert validate("it is fine really") is False
    assert validate("not needed by this change and we can revisit it later on") is False


def validate(reason: str) -> bool:
    return mod.validate_blocker_quality("x", reason, "f")


def test_an_empty_corpus_is_refused(tmp_path: pathlib.Path, monkeypatch) -> None:
    """A scan over nothing is the exact failure mode this gate polices."""
    monkeypatch.setenv(mod.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv(mod.DIRS_ENV, "nowhere")
    assert mod.main([]) == 1
