"""`rediacc_ci.quality.autopilot_no_bypass` against the jq programs it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-autopilot-no-bypass.observations.jsonl` drives the whole gate over five distinct trees: an unset App id, a failed list call, no active branch ruleset, the unauthenticated (blind) payload, and a live bypass entry. What a ledger row cannot isolate is that the port's Python re-implements THREE jq programs, and a jq program
is not obvious:

  * `.[] | select(.target == "branch" and .enforcement == "active") | .id`
  * `.bypass_actors[] | select((.actor_id|tostring) == $id) | "\\(.actor_type)/\\(.bypass_mode)"`
  * `[.bypass_actors[] | "\\(.actor_type):\\(.actor_id)"] | join(", ")`

Each is run through the real jq below and compared, because the interesting cases are the ones where jq's behaviour is surprising: `-r` prints the four characters `null` for a missing key, `tostring` makes the id comparison a STRING comparison, and iterating a missing `.bypass_actors` is an ERROR rather than an empty sequence. That last one is the difference between a blind read
being caught and a blind read being reported as clean.
"""

import json
import shutil
import subprocess

import pytest

from rediacc_ci.quality import autopilot_no_bypass as anb

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


def _jq(program: str, payload: str, *args: str) -> tuple[int, str]:
    """Run the real jq. Returns (exit status, stdout), stderr deliberately dropped.

    The twin discards jq's stderr in the `hit` and `actors` queries and does NOT discard it in the two assignments, which is part of why an unparseable payload kills it. Only the status and the value are compared here.
    """
    proc = subprocess.run(
        ["jq", "-r", *args, program],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8").rstrip("\n")


RULESETS = json.dumps(
    [
        {"id": 1, "target": "branch", "enforcement": "active"},
        {"id": 2, "target": "branch", "enforcement": "evaluate"},
        {"id": 3, "target": "tag", "enforcement": "active"},
        {"id": 40, "target": "branch", "enforcement": "active"},
    ]
)

SELECT = '.[] | select(.target == "branch" and .enforcement == "active") | .id'
HIT = '.bypass_actors[] | select((.actor_id|tostring) == $id) | "\\(.actor_type)/\\(.bypass_mode)"'
ACTORS = '[.bypass_actors[] | "\\(.actor_type):\\(.actor_id)"] | join(", ")'


def test_ruleset_selection_matches_jq() -> None:
    """Both directions in one payload: two selected, two rejected."""
    code, out = _jq(SELECT, RULESETS)
    assert code == 0
    assert out.split("\n") == ["1", "40"]
    assert anb.active_branch_ruleset_ids(RULESETS) == out.split("\n")


def test_ruleset_selection_of_an_empty_list_matches_jq() -> None:
    """The mirror. An empty selection is not an error in jq, and it must not be here.

    It is also the input the gate must treat as a FAILURE rather than a pass, which is asserted at the gate level in the selftest.
    """
    code, out = _jq(SELECT, "[]")
    assert code == 0
    assert out == ""
    assert anb.active_branch_ruleset_ids("[]") == []


def test_the_hit_query_matches_jq_in_both_directions() -> None:
    """The App present, and a different App absent, against the same payload."""
    payload = json.dumps(
        {
            "bypass_actors": [
                {"actor_id": 7, "actor_type": "Team", "bypass_mode": "always"},
                {"actor_id": 42, "actor_type": "Integration", "bypass_mode": "pull_request"},
            ]
        }
    )
    parsed = json.loads(payload)
    for app_id, want in (("42", "Integration/pull_request"), ("43", "")):
        code, out = _jq(HIT, payload, "--arg", "id", app_id)
        assert code == 0
        assert out == want, (app_id, out)
        assert anb.bypass_hit(parsed, app_id) == out


def test_the_hit_query_is_a_string_comparison_like_tostring() -> None:
    """`(.actor_id|tostring) == $id` matches the integer 42 against the string "42".

    A port comparing integers would pass every case above and fail the moment an id arrived as a string, which is the class of change nobody notices.
    """
    payload = json.dumps({"bypass_actors": [{"actor_id": 42}]})
    code, out = _jq(HIT, payload, "--arg", "id", "42")
    assert code == 0
    assert out == "null/null"
    assert anb.bypass_hit(json.loads(payload), "42") == out


def test_a_missing_bypass_actors_key_is_an_error_in_jq_and_empty_here() -> None:
    """The blind read, and the reason presence is asserted BEFORE contents.

    jq exits 5 iterating a missing `.bypass_actors`, so the twin's `hit` assignment yields the empty string either way: an absent key and an empty list are indistinguishable downstream. That is exactly why the gate tests `has("bypass_actors")` first, and why this port's `bypass_hit` is allowed to
    return "" for both.
    """
    blind = json.dumps(dict.fromkeys(anb.UNAUTHENTICATED_KEYS, "x"))
    code, out = _jq(HIT, blind, "--arg", "id", "42")
    assert code != 0
    assert out == ""
    assert anb.bypass_hit(json.loads(blind), "42") == ""
    assert "bypass_actors" not in json.loads(blind)


def test_actor_summary_matches_jq() -> None:
    """The join, including the ', ' separator the success line prints."""
    payload = json.dumps(
        {
            "bypass_actors": [
                {"actor_id": 7, "actor_type": "Team"},
                {"actor_id": 42, "actor_type": "Integration"},
            ]
        }
    )
    code, out = _jq(ACTORS, payload)
    assert code == 0
    assert out == "Team:7, Integration:42"
    assert anb.actor_summary(json.loads(payload)) == out


def test_actor_summary_of_an_empty_list_matches_jq_and_becomes_none_upstream() -> None:
    """`join` of nothing is the empty string; `${actors:-none}` is what prints 'none'."""
    code, out = _jq(ACTORS, '{"bypass_actors":[]}')
    assert code == 0
    assert out == ""
    assert anb.actor_summary({"bypass_actors": []}) == ""


def test_jq_dash_r_prints_the_four_characters_null() -> None:
    """`jq -r '.name'` on a nameless ruleset, which the twin interpolates verbatim."""
    code, out = _jq(".name", "{}")
    assert code == 0
    assert out == "null"
    assert anb._jq_string(None) == out


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, with no network and no token."""
    assert anb.selftest() == 0
