"""`rediacc_ci.core.bws_env` against the live `.ci/lib/bws-env.sh`.

NO REAL STORE IS EVER TOUCHED. `bws` is faked on PATH, exactly as `.ci/scripts/test/gates/test-bws-env.sh` fakes it and for the same reason its header gives: the fake is the point, not a limitation, because an empty stored value and a missing name cannot be produced on demand against a live store. The fake also REFUSES if the caller omits `--color no`, so a port that dropped the
flag fails here rather than in production against a bws that wraps its JSON in truecolor escapes.

THE PATH IS SCRUBBED ON BOTH SIDES, AND THAT IS NOT DECORATION. A real `bws` exists on this machine at `~/.local/bin/bws`. The first run of this differential compared a bash side that found the REAL binary through `command -v` against a Python side pinned to a fake path, and reported a stderr difference that looked like a port defect. It was an asymmetric harness. Every case below
builds the environment ONCE and hands the identical mapping to both sides.

VALUES ARE NEVER COMPARED, NAMES ARE. Both drivers print the sorted NAMES that ended up resolved, which is the same assertion `test-bws-env.sh:72` makes from the other side ("NEVER prints a value"). A differential that compared values would have to put them on a stream to compare them, and this repository is public.

THE ONE DELIBERATE DIVERGENCE IS PINNED, NOT PAPERED OVER. See `test_unparseable_listing_is_the_one_deliberate_divergence`: the twin leaks a Python traceback per name and then MISATTRIBUTES the failure to the store. The port refuses once and names the tool. Both behaviours are asserted, so a future reader cannot mistake the divergence for drift, and the ledger deliberately does not
carry that case.
"""

import json
import os
import shutil
import stat
import textwrap

import pytest

from rediacc_ci.core import bws_env
from rediacc_ci.tests import differential as diff

TWIN = ".ci/lib/bws-env.sh"

BOTH = json.dumps(
    [{"key": "ALPHA_TOKEN", "value": "a-val"}, {"key": "BETA_TOKEN", "value": "b-val"}]
)
BETA_EMPTY = json.dumps(
    [{"key": "ALPHA_TOKEN", "value": "a-val"}, {"key": "BETA_TOKEN", "value": ""}]
)
ONLY_ALPHA = json.dumps([{"key": "ALPHA_TOKEN", "value": "a-val"}])

MAP = '{ "project": "p", "secrets": { "ALPHA_TOKEN": { "id": "1" }, "BETA_TOKEN": { "id": "2" } } }'

# The bash driver: source the twin, load, then print the NAMES that are now set. `set +e` because the twin returns 1 on a partial load and the driver has to survive it to report anything at all.
BASH_DRIVER = textwrap.dedent(
    """
    _drive() {
      set +e
      source "$BWS_TWIN"
      bws_env_load "$@"; local rc=$?
      local cand=()
      if [[ $# -gt 0 ]]; then cand=("$@"); else
        mapfile -t cand < <(python3 -c \\
          'import json,sys;print("\\n".join(sorted(json.load(open(sys.argv[1]))["secrets"])))' \\
          "$BWS_ENV_ROOT/.ci/config/bws-secret-map.json" 2>/dev/null)
      fi
      for n in "${cand[@]}"; do [[ -n "${!n:-}" ]] && echo "$n"; done | sort
      exit $rc
    }
    """
)


def fixture(root, listing: str, *, with_bws: bool = True, bws_body: str | None = None):
    """A fake `bws`, a two-name map, and a listing. The gate test's fixture."""
    binroot = root / "bin"
    binroot.mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / "listing.json").write_text(listing, encoding="utf-8")
    (root / ".ci" / "config" / "bws-secret-map.json").write_text(MAP, encoding="utf-8")
    if with_bws:
        body = bws_body or (
            "#!/bin/bash\n"
            "# the real bws wraps --output json in ANSI unless --color no is passed\n"
            'for a in "$@"; do [ "$a" = "--color" ] && seen=1; done\n'
            '[ -n "${seen:-}" ] || { echo "fake bws: caller did not pass --color" >&2; exit 3; }\n'
            'cat "%s"\n' % (root / "listing.json")
        )
        target = binroot / "bws"
        target.write_text(body, encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return root


def env_for(root, with_token: bool = True) -> dict:
    """ONE mapping, handed to BOTH sides. See the header.

    PATH puts the fixture's bin FIRST and then only the system directories, so the real `bws` on this machine is unreachable from either implementation.
    """
    overrides = {
        "PATH": "%s:/usr/local/bin:/usr/bin:/bin" % (root / "bin"),
        "BWS_ENV_ROOT": str(root),
    }
    if with_token:
        # The VALUE is irrelevant to every case here -- the fake `bws` never reads it -- so it is a literal rather than a parameter. Only its PRESENCE is under test, which is the twin's first precondition.
        overrides[bws_env.ACCESS_ENV] = "fixture-token-not-a-credential"
    return diff.env_for(**overrides)


def run_both(names: list[str], env: dict):
    args = " ".join("'%s'" % n for n in names)
    old = diff.bash_streams("%s\nBWS_TWIN=%s _drive %s" % (BASH_DRIVER, TWIN, args), env=env)
    new = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env names %s" % args, env=env
    )
    return old, new


CASES = [
    ("complete-store-every-name", BOTH, [], True, True),
    ("named-subset", BOTH, ["ALPHA_TOKEN"], True, True),
    ("empty-value-is-absent", BETA_EMPTY, [], True, True),
    ("name-missing-from-store", ONLY_ALPHA, [], True, True),
    ("unmapped-name-is-looked-up-anyway", BOTH, ["GAMMA_TOKEN"], True, True),
    ("no-access-token", BOTH, [], True, False),
    ("no-bws-binary", BOTH, [], False, True),
]


@pytest.mark.parametrize(
    ("case_id", "listing", "names", "with_bws", "with_token"), CASES, ids=[c[0] for c in CASES]
)
def test_port_matches_the_live_twin(
    tmp_path, case_id, listing, names, with_bws, with_token
) -> None:
    root = fixture(tmp_path / case_id, listing, with_bws=with_bws)
    old, new = run_both(names, env_for(root, with_token))
    assert old == new, "case %s: bash %r vs python %r" % (case_id, old, new)


def test_map_missing(tmp_path) -> None:
    """Its own case because the refusal INTERPOLATES the path, which differs per run."""
    root = fixture(tmp_path / "nomap", BOTH)
    os.remove(root / ".ci" / "config" / "bws-secret-map.json")
    old, new = run_both([], env_for(root))
    assert old == new
    assert "is missing; nothing can be resolved by name." in old[2]
    assert str(root) in old[2]


def test_bws_exits_non_zero(tmp_path) -> None:
    root = fixture(tmp_path / "rc9", BOTH, bws_body="#!/bin/bash\nexit 9\n")
    old, new = run_both([], env_for(root))
    assert old == new
    assert "bws secret list failed" in old[2]


def test_the_corpus_is_not_empty() -> None:
    assert len(CASES) >= 5, "the differential corpus collapsed to %d case(s)" % len(CASES)


def test_the_differential_can_fail(tmp_path) -> None:
    """One word changed in a refusal must turn the comparison red."""
    root = fixture(tmp_path / "canfail", BETA_EMPTY)
    old, new = run_both([], env_for(root))
    assert old == new
    assert old != (new[0], new[1], new[2].replace("absent or empty", "absent")), (
        "the comparison is not looking at stderr, where every refusal lives"
    )
    assert old != (new[0], new[1].replace("ALPHA_TOKEN", "ALPHA"), new[2]), (
        "the comparison is not looking at the resolved name list on stdout"
    )


def test_no_value_reaches_either_stream(tmp_path) -> None:
    """The twin's first stated rule, asserted against BOTH implementations."""
    root = fixture(tmp_path / "novalue", BOTH)
    old, new = run_both([], env_for(root))
    for stream in (old[1], old[2], new[1], new[2]):
        assert "a-val" not in stream
        assert "b-val" not in stream
    assert "ALPHA_TOKEN" in new[1], "the control: the NAME is present, so the check is live"


def test_the_fake_bws_refuses_without_color_no(tmp_path) -> None:
    """A CONTROL ON THE FIXTURE. If the fake stopped checking, dropping
    `--color no` from either implementation would go unnoticed."""
    root = fixture(tmp_path / "colour", BOTH)
    probe = diff.bash_streams(
        '"%s" secret list --output json' % (root / "bin" / "bws"), env=env_for(root)
    )
    assert probe[0] == 3
    assert "did not pass --color" in probe[2]


def test_unparseable_listing_is_the_one_deliberate_divergence(tmp_path) -> None:
    """A DEFECT IN THE TWIN, reproduced here and NOT reproduced in the port.

    `bws` exiting 0 with output that is not JSON is exactly what `--color no` exists to prevent, so it is the live failure mode if bws ever changes its escaping again. The twin's per-name `python3 -c` then dies, its command substitution fails, and the name is filed as `absent or empty in the store`:

      * 36 lines of Python TRACEBACK on stderr, two full copies, one per name
      * `bws-env: 2 name(s) absent or empty in the store: ALPHA_TOKEN BETA_TOKEN`
      * `bws-env: exported 0 secret(s)`

    All of which sends the reader to Bitwarden to look for two secrets that are sitting there perfectly. The port refuses ONCE with the twin's own `bws secret list failed` wording, which names the tool.

    BOTH SIDES ARE ASSERTED so this is a pinned decision and not drift, and the shadow ledger deliberately omits this case: a ledger row is a claim of EQUIVALENCE and there is none to claim here.
    """
    root = fixture(tmp_path / "garbage", "not json at all")
    old, new = run_both([], env_for(root))

    assert old[0] == new[0] == 1, "both still fail; the exit code is not the divergence"
    assert old[1] == new[1] == "", "neither resolves a name"
    assert "Traceback (most recent call last)" in old[2]
    assert "absent or empty in the store: ALPHA_TOKEN BETA_TOKEN" in old[2]
    assert old[2].count("Traceback") == 2, "one traceback per name, both leaked"

    assert "Traceback" not in new[2]
    assert "absent or empty" not in new[2]
    assert new[2].splitlines() == bws_env.LIST_FAILED


# -- the helpers, exercised directly -----------------------------------------


def test_pick_takes_the_first_duplicate() -> None:
    rows = [{"key": "K", "value": "first"}, {"key": "K", "value": "second"}]
    assert bws_env.pick(rows, "K") == "first"
    assert bws_env.pick(rows, "ABSENT") == ""


def test_pick_treats_a_null_value_as_empty() -> None:
    """`r.get("value") or ""` in the twin. A JSON null must not become "None"."""
    assert bws_env.pick([{"key": "K", "value": None}], "K") == ""
    assert bws_env.pick([{"key": "K"}], "K") == ""
    assert bws_env.pick([{"key": "K", "value": "x"}], "K") == "x"


def test_root_prefers_the_override(tmp_path) -> None:
    assert bws_env.root({"BWS_ENV_ROOT": str(tmp_path)}) == str(tmp_path)
    assert os.path.isdir(bws_env.root({}))


def test_binary_refuses_a_non_executable_bws_bin(tmp_path) -> None:
    """`-x` on a caller-supplied path. Both directions."""
    dead = tmp_path / "not-executable"
    dead.write_text("#!/bin/bash\n", encoding="utf-8")
    assert bws_env.binary({"BWS_BIN": str(dead)}) == ""
    dead.chmod(0o755)
    assert bws_env.binary({"BWS_BIN": str(dead)}) == str(dead)


def test_mapped_names_are_sorted(tmp_path) -> None:
    path = tmp_path / "m.json"
    path.write_text('{"secrets": {"Z": {}, "A": {}, "M": {}}}', encoding="utf-8")
    assert bws_env.mapped_names(str(path)) == ["A", "M", "Z"]


def test_the_module_exposes_no_verb_that_prints_a_value() -> None:
    """The rule at `.ci/lib/bws-env.sh:16-18`, enforced against the port's OWN API.

    An `export` verb is the obvious next feature and it is the one thing this module must not grow without an owner saying so. The check is on the USAGE text and the verb table rather than on a grep of the source, because that is what a caller can actually reach.
    """
    assert "export" not in bws_env.USAGE.split("There is deliberately")[0]
    assert bws_env.main(["export"]) == 2
    assert bws_env.main(["map"]) == 0, "the control: a real verb still works"


def test_map_verb_refuses_an_empty_map(tmp_path, monkeypatch) -> None:
    """Anti-vacuity: a map with zero secrets resolves nothing and must not pass."""
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "bws-secret-map.json").write_text(
        '{"secrets": {}}', encoding="utf-8"
    )
    monkeypatch.setenv("BWS_ENV_ROOT", str(tmp_path))
    assert bws_env.main(["map"]) == 1
    (tmp_path / ".ci" / "config" / "bws-secret-map.json").write_text(MAP, encoding="utf-8")
    assert bws_env.main(["map"]) == 0, "the control: a populated map is accepted"


def test_bash_and_python_read_the_same_default_name_list() -> None:
    """The REAL map, not a fixture: 0 names would make every case above vacuous."""
    names = bws_env.mapped_names(bws_env.map_path({}))
    assert len(names) > 10, "the real bws-secret-map.json lists only %d name(s)" % len(names)
    assert names == sorted(names)
    assert shutil.which("python3") is not None
