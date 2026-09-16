"""`rediacc_ci.quality.npmrc` against the shell pipeline it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The interesting half of
this gate is a four-stage shell pipeline -- `grep -E | tail -n1 | sed -E | tr -d`
-- whose behaviour on the awkward inputs (a trailing comment, inner whitespace,
a key that appears twice, an empty value) is decided by POSIX character classes
and by sed's substitution order rather than by anything a reader could infer.
A table of expected strings would be a table of what the PORT does, asserted
against itself. Running the real pipeline under bash and comparing is the only
form of this test that can fail for the right reason.

The bash fragments below are lifted from `.ci/scripts/quality/check-npmrc.sh`
lines 44-69 with the variables substituted, and nothing else changed. They are
NOT the whole gate: the whole gate is what the committed shadow ledger
`.ci/shadow/w7p2-npmrc.observations.jsonl` compares over five distinct trees.
This file covers the seams that ledger cannot isolate.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import npmrc
from rediacc_ci.tests import differential as diff

# Every awkward shape the value pipeline has to survive. The comment on each
# line is the property it is there for; a case with no property is a case that
# will be deleted the first time someone tidies this file.
VALUE_CASES = [
    ("ignore-scripts=true\n", "ignore-scripts"),  # the ordinary one
    ("ignore-scripts = true \n", "ignore-scripts"),  # spaces around the =
    ("  ignore-scripts=true\n", "ignore-scripts"),  # leading indent
    ("ignore-scripts=true # hardening\n", "ignore-scripts"),  # trailing comment
    ("ignore-scripts=true#hardening\n", "ignore-scripts"),  # comment with no space
    ("ignore-scripts=\n", "ignore-scripts"),  # present but EMPTY
    ("ignore-scripts=#x\n", "ignore-scripts"),  # reduces to empty
    ("ignore-scripts=true false\n", "ignore-scripts"),  # inner whitespace is DELETED
    ("ignore-scripts=false\nignore-scripts=true\n", "ignore-scripts"),  # last one wins
    ("Ignore-Scripts=true\n", "ignore-scripts"),  # case SENSITIVE: no match
    ("registry=x\n", "ignore-scripts"),  # no matching line at all
    ("allow-git=none\n", "allow-git"),  # a key containing a hyphen
    ("minimum-release-age=1440\n", "minimum-release-age"),
]


@pytest.mark.parametrize(("content", "key"), VALUE_CASES)
def test_value_pipeline_matches_bash(tmp_path: pathlib.Path, content: str, key: str) -> None:
    target = tmp_path / ".npmrc"
    target.write_text(content, encoding="utf-8")
    script = (
        'grep -E "^[[:space:]]*%s[[:space:]]*=" .npmrc | '
        "tail -n1 | "
        'sed -E "s/^[[:space:]]*%s[[:space:]]*=[[:space:]]*//; s/[[:space:]]*#.*//" | '
        "tr -d '[:space:]' || true"
    ) % (key, key)
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    # `$( )` strips trailing newlines; the shell fragment above is what the twin
    # puts inside one, so the comparison is against the stripped form.
    assert npmrc.setting_value(content, key) == out.rstrip("\n")


FORBIDDEN_CASES = [
    "force=true\n",
    "legacy-peer-deps=true\n",
    "  force = 1\n",
    "Legacy-Peer-Deps=true\n",  # -i
    "FORCE=true\n",
    "force-cache=true\n",  # must NOT match: a longer key
    "#force=true\n",  # must NOT match: commented
    "myforce=true\n",  # must NOT match: not at line start
    "force\n",  # must NOT match: no `=`
    "ignore-scripts=true\nforce=true\nallow-git=none\n",  # line numbering
]


@pytest.mark.parametrize("content", FORBIDDEN_CASES)
def test_forbidden_scan_matches_bash(tmp_path: pathlib.Path, content: str) -> None:
    """`grep -niE`, numbers and all. BOTH directions live in this table."""
    target = tmp_path / ".npmrc"
    target.write_text(content, encoding="utf-8")
    script = 'grep -niE "^[[:space:]]*(legacy-peer-deps|force)[[:space:]]*=" .npmrc || true'
    code, out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0
    expected = "".join("%d:%s\n" % pair for pair in npmrc.forbidden_matches(content))
    assert expected == out


def test_the_forbidden_table_exercises_both_directions() -> None:
    """ANTI-VACUITY on the table above.

    A parametrized suite where every case matches would pass a scan that flags
    everything, and a suite where none matches would pass a scan that flags
    nothing. Both directions must be present, and that is asserted rather than
    eyeballed because a case is one edit away from being deleted.
    """
    hits = [c for c in FORBIDDEN_CASES if npmrc.forbidden_matches(c)]
    misses = [c for c in FORBIDDEN_CASES if not npmrc.forbidden_matches(c)]
    assert hits, "no case fires: the scan could be dead"
    assert misses, "every case fires: the scan could be flagging everything"


def test_required_keys_are_the_three_the_twin_declares() -> None:
    """The corpus, pinned. A silently shrinking REQUIRED is a silently weaker gate."""
    assert dict(npmrc.REQUIRED) == {
        "ignore-scripts": "true",
        "allow-git": "none",
        "minimum-release-age": "1440",
    }


def test_main_refuses_an_absent_npmrc(tmp_path: pathlib.Path, monkeypatch) -> None:
    """The subject missing is a FAILURE, not an abstention."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert npmrc.main([]) == 1


def test_main_passes_a_hardened_npmrc(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Its mirror: the gate must be capable of returning 0, or the line above
    proves only that it refuses everything."""
    (tmp_path / ".npmrc").write_text(
        "ignore-scripts=true\nallow-git=none\nminimum-release-age=1440\n", encoding="utf-8"
    )
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert npmrc.main([]) == 0


def test_selftest_is_green() -> None:
    """The gate's own plants, driven from pytest as well as from the flag."""
    assert npmrc.selftest() == 0


def test_the_real_tree_is_hardened() -> None:
    """The gate against the actual repository. A port that cannot run here is
    not a port, and this is the only case that touches the real `.npmrc`."""
    assert npmrc.main([]) == 0
