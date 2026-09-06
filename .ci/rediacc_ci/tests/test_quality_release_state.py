"""`rediacc_ci.quality.release_state` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The library this port
carries is deliberately PURE -- its own header says callers "should usually feed
`rsv_assert_bijection` synthetic version lists rather than shimming AWS" -- so
the interesting half can be driven directly on both sides. What cannot be
inferred, and is measured below rather than reasoned:

  * `sort -uV` on `v1.0.9` and `v1.0.10` is NOT lexicographic, and the whole
    bijection depends on it. The port approximates version sort with a numeric
    key; every case here runs the real `sort -uV` beside it.
  * `sed -n 's/.*"version"...\\(...\\)".*/\\1/p' | head -1` is GREEDY, so a line
    with two `"version"` keys reports the SECOND. Reproducing that was a
    decision, not an accident.
  * `wc -l <<<"$x"` on the empty string is ONE, so a repository with zero tags
    is reported as `1 git tags`. The port prints the same wrong number on
    purpose; this file pins it so nobody "fixes" one side.
  * `${v:+N cli sentinels}${v:-none}` glues the count to the WHOLE version list.

They are NOT the whole gate: the whole gate is what the committed shadow ledger
`.ci/shadow/w7p2-release-state.observations.jsonl` compares over five distinct
trees, against a stub `aws` committed inside each fixture. This file covers the
seams that ledger cannot isolate.
"""

import os
import pathlib
import tempfile

import pytest

from rediacc_ci.quality import release_state as rs
from rediacc_ci.tests import differential as diff

SORT_CASES = [
    ["v1.0.2", "v1.0.9", "v1.0.10"],
    ["v1.0.10", "v1.0.9", "v1.0.2"],
    ["v1.0.0", "v1.0.0", "v1.0.1"],
    ["v2.0.0", "v10.0.0", "v1.0.0"],
    ["v1.10.0", "v1.9.0"],
    ["v0.9.0", "v1.0.0", "v1.0.0"],
    [],
    ["v1.0.0"],
]


@pytest.mark.parametrize("values", SORT_CASES)
def test_sort_unique_versions_matches_sort_uv(values: list[str]) -> None:
    """`sort -uV`, run for real. The one place lexicographic order is fatal."""
    if not values:
        assert rs.sort_unique_versions(values) == []
        return
    script = "printf '%%s\\n' %s | sort -uV" % " ".join(values)
    code, out, err = diff.bash_streams(script, env=diff.env_for())
    assert code == 0, err
    assert rs.sort_unique_versions(values) == [line for line in out.split("\n") if line != ""]


def test_the_sort_table_would_fail_under_lexicographic_order() -> None:
    """The control ON the table: at least one case must distinguish the two.

    Without this a later tidy could reduce the table to single-digit versions,
    where `sort -V` and `sort` agree, and the differential would prove nothing.
    """
    assert rs.sort_unique_versions(["v1.0.10", "v1.0.9"]) == ["v1.0.9", "v1.0.10"]
    assert sorted(["v1.0.10", "v1.0.9"]) == ["v1.0.10", "v1.0.9"]


POINTER_CASES = [
    '{"version": "1.3.1"}\n',
    '{"version":"v1.3.1"}\n',
    '{"version"  :   "1.3.1"}\n',
    '{"channel": "edge", "version": "1.3.1", "sha": "abc"}\n',
    '{"version": "1.0.0", "tool": {"version": "9.9.9"}}\n',  # GREEDY: the LAST wins
    '{\n  "version": "1.0.0"\n}\n{"version": "2.0.0"}\n',  # head -1: the FIRST LINE wins
    '{"version": ""}\n',
    "{}\n",
    "",
    "not json at all\n",
    '{"versions": ["1.0.0"]}\n',
]


@pytest.mark.parametrize("payload", POINTER_CASES)
def test_pointer_version_matches_the_sed_pipeline(tmp_path: pathlib.Path, payload: str) -> None:
    """The three shell stages, verbatim, including the `v` that is stripped then
    re-added and the bare `v` the twin rewrites to the empty string."""
    (tmp_path / "p.json").write_text(payload, encoding="utf-8")
    script = (
        """v="v$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' p.json """
        """| head -1 | sed 's/^v//')"; [[ "$v" == "v" ]] && v=""; printf '%s' "$v" """
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code in (0, 1), err
    assert rs.pointer_version(payload) == out


def test_the_pointer_table_exercises_both_directions() -> None:
    parsed = [rs.pointer_version(p) for p in POINTER_CASES]
    assert any(parsed), "no payload parses"
    assert any(p == "" for p in parsed), "every payload parses; there are no negatives"


def test_the_greedy_match_is_deliberate() -> None:
    """Pinned separately because it looks like a bug and is a decision.

    BRE `.*` is greedy, so a nested `"version"` after the top-level one wins.
    A left-to-right search would be a DIFFERENT gate, and this assertion is what
    stops someone making the port that gate while the twin stays as it is.
    """
    assert rs.pointer_version('{"version": "1.0.0", "tool": {"version": "9.9.9"}}') == "v9.9.9"


BIJECTION_CASES = [
    (["v1.0.0", "v1.0.1"], ["v1.0.0", "v1.0.1"], "", "a clean bijection"),
    (["v1.0.0", "v1.0.1"], ["v1.0.0"], "", "a sentinel with no tag"),
    (["v1.0.0"], ["v1.0.0", "v1.0.1"], "", "a tag with no sentinel"),
    (["v1.0.0", "v1.0.9"], ["v1.0.0"], "v1.0.9", "the in-flight version is excluded"),
    (["v1.0.5"], ["v0.9.0", "v1.0.5"], "", "a tag BELOW the floor is grandfathered"),
    (["v1.0.5"], ["v1.0.5", "v1.0.6"], "", "a tag ABOVE the floor is not"),
    ([], ["v1.0.0"], "", "no sentinels: the contract is not in effect"),
    ([], [], "", "nothing at all"),
    (["v1.0.0", "v1.0.10"], ["v1.0.0", "v1.0.9"], "", "version order matters here"),
]


@pytest.mark.parametrize(("cli", "tags", "in_flight", "why"), BIJECTION_CASES)
def test_assert_bijection_matches_the_bash_function(
    tmp_path: pathlib.Path, cli: list[str], tags: list[str], in_flight: str, why: str
) -> None:
    """The real `rsv_assert_bijection`, sourced from the library it lives in.

    THE RATCHET IS PINNED AWAY ON BOTH SIDES. `rsv_pre_contract_floor`'s second
    candidate is `<lib>/../../config/release-contract-floor.txt`, which does not
    move when a caller passes a fixture root, so an unpinned run computes its
    floor from whatever version the REAL repository is on and grandfathers every
    case here. `RSV_FLOOR_FILE` pointing at a path that does not exist is how
    the library itself is told "no ratchet": the candidate search is skipped
    entirely when the variable is set.
    """
    nofloor = str(tmp_path / "no-such-floor.txt")
    # `|| rc=$?` IS LOAD-BEARING. `common.sh` sets `-euo pipefail`, so a bare
    # call to an assertion that returns 1 kills the harness before it can print
    # the exit code, and every drift case then looks like a broken test rather
    # than a caught defect. The `||` is what suspends errexit for that command.
    script = """
        source .ci/scripts/lib/common.sh
        source .ci/scripts/lib/release-state-validator.sh
        rc=0
        rsv_assert_bijection "$CLI" "$TAGS" "$INF" || rc=$?
        echo "rc=$rc"
    """
    env = diff.env_for(
        CLI="\n".join(cli),
        TAGS="\n".join(tags),
        INF=in_flight,
        RSV_FLOOR_FILE=nofloor,
    )
    code, out, err = diff.bash_streams(script, env=env)
    assert code == 0, err
    bash_lines = [line for line in out.split("\n") if line != "" and not line.startswith("rc=")]
    bash_rc = int(out.strip().split("rc=")[-1])

    saved = os.environ.get("RSV_FLOOR_FILE")
    os.environ["RSV_FLOOR_FILE"] = nofloor
    try:
        port_lines, port_rc = rs.assert_bijection(cli, tags, in_flight, tmp_path)
    finally:
        if saved is None:
            del os.environ["RSV_FLOOR_FILE"]
        else:
            os.environ["RSV_FLOOR_FILE"] = saved

    assert port_lines == bash_lines, why
    assert port_rc == bash_rc, why


def test_the_bijection_table_exercises_both_verdicts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        os.environ["RSV_FLOOR_FILE"] = str(root / "none.txt")
        try:
            codes = {
                rs.assert_bijection(cli, tags, inf, root)[1]
                for cli, tags, inf, _why in BIJECTION_CASES
            }
        finally:
            del os.environ["RSV_FLOOR_FILE"]
    assert codes == {0, 1}


POINTER_ASSERT_CASES = [
    ("edge", "v1.0.1", "v1.0.1", ["v1.0.0", "v1.0.1"], "", "consistent and tagged"),
    ("edge", "", "v1.0.1", ["v1.0.1"], "", "an unreadable latest.json"),
    ("edge", "v1.0.1", "", ["v1.0.1"], "", "an unreadable manifest.json"),
    ("edge", "", "", ["v1.0.1"], "", "both unreadable"),
    ("stable", "v1.0.1", "v1.0.0", ["v1.0.0", "v1.0.1"], "", "a torn write"),
    ("edge", "v1.3.1", "v1.3.1", ["v1.0.0"], "", "the #573/#574/#576 shape"),
    ("edge", "v1.0.2", "v1.0.2", ["v1.0.0"], "v1.0.2", "the in-flight version"),
    ("edge", "v1.0.2", "v1.0.1", ["v1.0.1"], "v1.0.2", "torn AND in-flight"),
]


@pytest.mark.parametrize(
    ("channel", "latest", "manifest", "tags", "in_flight", "why"), POINTER_ASSERT_CASES
)
def test_assert_channel_pointer_matches_the_bash_function(
    channel: str, latest: str, manifest: str, tags: list[str], in_flight: str, why: str
) -> None:
    # See the bijection case above for why `|| rc=$?` is not optional here.
    script = """
        source .ci/scripts/lib/common.sh
        source .ci/scripts/lib/release-state-validator.sh
        rc=0
        rsv_assert_channel_pointer_tagged "$CH" "$LAT" "$MAN" "$TAGS" "$INF" || rc=$?
        echo "rc=$rc"
    """
    env = diff.env_for(CH=channel, LAT=latest, MAN=manifest, TAGS="\n".join(tags), INF=in_flight)
    code, out, err = diff.bash_streams(script, env=env)
    assert code == 0, err
    bash_lines = [line for line in out.split("\n") if line != "" and not line.startswith("rc=")]
    bash_rc = int(out.strip().split("rc=")[-1])

    port_lines, port_rc = rs.assert_channel_pointer_tagged(
        channel, latest, manifest, tags, in_flight
    )
    assert port_lines == bash_lines, why
    assert port_rc == bash_rc, why


def test_the_pointer_assert_table_exercises_both_verdicts() -> None:
    codes = {
        rs.assert_channel_pointer_tagged(ch, lat, man, tags, inf)[1]
        for ch, lat, man, tags, inf, _why in POINTER_ASSERT_CASES
    }
    assert codes == {0, 1}


def test_zero_tags_is_reported_as_one_because_of_the_herestring() -> None:
    """The twin's count is wrong for the empty case, and the port matches it.

    `wc -l <<<""` is 1: a herestring of the empty string is one (empty) line.
    This is the one count a reader most needs to be right, and it is preserved
    because a port that fixed it would disagree with its twin on every clean
    fresh clone. Measured here so the claim is checked rather than asserted in
    a comment.
    """
    code, out, err = diff.bash_streams('x=""; wc -l <<<"$x"')
    assert code == 0, err
    assert out.strip() == "1"


def test_the_sentinel_count_line_glues_the_whole_list_to_the_count() -> None:
    """`${v:+N cli sentinels}${v:-none}` is the count AND the list, unseparated.

    Reproduced by the port and reported as a defect. Measured against bash so a
    reader does not have to trust the reading of the expansion.
    """
    script = """
        v="v1.0.0
v1.0.1"
        printf '%s' "  ${v:+$(wc -l <<<"$v") cli sentinels}${v:-none}"
    """
    code, out, err = diff.bash_streams(script)
    assert code == 0, err
    assert out == "  2 cli sentinelsv1.0.0\nv1.0.1"
    # The port's own formatting, spelled the way the module spells it, so the
    # two are compared rather than one being restated.
    versions = ["v1.0.0", "v1.0.1"]
    assert "  %d cli sentinels%s" % (len(versions), "\n".join(versions)) == out


def test_require_var_treats_an_empty_value_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 2026-09-05 shape: a deleted org secret resolves to "" and must fail.

    `[[ -z "${!var:-}" ]]` cannot tell unset from empty, and that is correct
    here: an empty credential is not a credential.
    """
    script = """
        source .ci/scripts/lib/common.sh
        require_var PROBE_VAR
        echo REACHED
    """
    code, out, err = diff.bash_streams(script, env=diff.env_for(PROBE_VAR=""))
    assert code == 1
    assert "REACHED" not in out
    assert "is not set" in err

    monkeypatch.setenv("PROBE_VAR", "")
    with pytest.raises(SystemExit) as excinfo:
        rs.require_var("PROBE_VAR")
    assert excinfo.value.code == 1

    monkeypatch.setenv("PROBE_VAR", "value")
    rs.require_var("PROBE_VAR")


def test_selftest_passes() -> None:
    assert rs.selftest() == 0
