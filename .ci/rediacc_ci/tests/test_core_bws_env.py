"""`rediacc_ci.core.bws_env` against the bytes `.ci/lib/bws-env.sh` printed.

THE TWIN HAS BEEN DELETED. It had zero production sourcers, a fact re-measured three times and recorded in the port's own header; `.ci/shadow/w7p5b-bws-env.observations.jsonl` holds 5 rows of equivalence over 5 distinct trees, and the file was removed on the strength of them. `goldens/bws-env/` holds the helper's OWN recorded bytes, captured on its last day in the tree by
driving it through the same `_drive` shell function this file used to run live, over the same ten fixtures. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

NO REAL STORE WAS EVER TOUCHED, AND STILL IS NOT. `bws` is faked on PATH, exactly as `.ci/rediacc_ci/tests/gates/test_gate_bws_env.py` fakes it and for the same reason its header gives: the fake is the point, not a limitation, because an empty stored value and a missing name cannot be produced on demand against a live store. The fake also REFUSES if the caller omits `--color no`,
so a port that dropped the flag fails here rather than in production against a bws that wraps its JSON in truecolor escapes.

THE PATH IS SCRUBBED, AND THAT IS NOT DECORATION. A real `bws` exists on the recording machine at `~/.local/bin/bws`. The first run of this differential compared a bash side that found the REAL binary through `command -v` against a Python side pinned to a fake path, and reported a stderr difference that looked like a port defect. It was an asymmetric harness. Every case below
builds the environment ONCE, and the recording was taken through that same builder.

THE FIXTURE ROOT IS THE ONLY MASKED TOKEN. A recording is compared against a tree built under a different temporary name, so `<root>` stands in for the fixture directory and nothing else is touched. Both streams stay separate throughout.

VALUES ARE NEVER COMPARED, NAMES ARE. Both drivers print the sorted NAMES that ended up resolved, which is the same assertion `test-bws-env.sh:72` made from the other side ("NEVER prints a value"). A differential that compared values would have to put them on a stream to compare them, and this repository is public.

THE ONE DELIBERATE DIVERGENCE IS PINNED, NOT PAPERED OVER. See `test_unparseable_listing_is_the_one_deliberate_divergence`: the twin leaked a Python traceback per name and then MISATTRIBUTED the failure to the store. The port refuses once and names the tool. Both behaviours are asserted against the recording, so a future reader cannot mistake the divergence for drift, and the
ledger deliberately does not carry that case.
"""

import json
import os
import pathlib
import shutil
import stat
import textwrap

import pytest

from rediacc_ci.core import bws_env
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

TWIN = ".ci/lib/bws-env.sh"
SLUG = "bws-env"

BOTH = json.dumps(
    [{"key": "ALPHA_TOKEN", "value": "a-val"}, {"key": "BETA_TOKEN", "value": "b-val"}]
)
BETA_EMPTY = json.dumps(
    [{"key": "ALPHA_TOKEN", "value": "a-val"}, {"key": "BETA_TOKEN", "value": ""}]
)
ONLY_ALPHA = json.dumps([{"key": "ALPHA_TOKEN", "value": "a-val"}])

MAP = '{ "project": "p", "secrets": { "ALPHA_TOKEN": { "id": "1" }, "BETA_TOKEN": { "id": "2" } } }'

# The TRACKED notice, read once. Every fixture below plants this exact text rather than a paraphrase: a fixture carrying its own wording would keep passing after the shipped file was emptied, which is the one regression the notice can suffer.
REAL_NOTICE = (pathlib.Path(bws_env.root({})) / bws_env.ROTATION_NOTICE_REL).read_text(
    encoding="utf-8"
)

# The driver the recording was taken through, kept verbatim: source the twin, load, then print the NAMES that are now set. `set +e` because the twin returned 1 on a partial load and the driver had to survive it to report anything at all.
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
        # The token FILE resolves under the fixture, never the operator's real `~/.config/rediacc/bws-access-token`: without this the no-token cases would find the real credential and pass for the wrong reason.
        "XDG_CONFIG_HOME": str(root / "xdg"),
    }
    if with_token:
        # The VALUE is irrelevant to every case here -- the fake `bws` never reads it -- so it is a literal rather than a parameter. Only its PRESENCE is under test, which is the twin's first precondition.
        overrides[bws_env.ACCESS_ENV] = "fixture-token-not-a-credential"
    return diff.env_for(**overrides)


def run_port(names: list[str], env: dict, root) -> tuple[int, str, str]:
    """The port, over one fixture, with the fixture root masked out of both streams."""
    args = " ".join("'%s'" % n for n in names)
    code, out, err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env names %s" % args, env=env
    )
    return code, frozen.mask_root(out, root), frozen.mask_root(err, root)


def recorded(case_id: str) -> tuple[int, str, str]:
    """One golden, split back into exit code, stdout and stderr."""
    body = frozen.read(SLUG, case_id)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err


CASES = [
    ("complete-store-every-name", BOTH, [], True, True),
    ("named-subset", BOTH, ["ALPHA_TOKEN"], True, True),
    ("empty-value-is-absent", BETA_EMPTY, [], True, True),
    ("name-missing-from-store", ONLY_ALPHA, [], True, True),
    ("unmapped-name-is-looked-up-anyway", BOTH, ["GAMMA_TOKEN"], True, True),
    ("no-bws-binary", BOTH, [], False, True),
]

# Recorded, but no longer an equivalence: see `test_no_access_token_is_the_third_deliberate_divergence`.
NO_BOOTSTRAP_CASE = "no-access-token"


# The three cases that are not in the parametrized table, each recorded under its own name because each needs a fixture the table cannot express: a removed map, a `bws` that exits 9, and a `bws` that exits 0 with bytes that are not JSON.
MAP_MISSING = "map-missing"
BWS_NON_ZERO = "bws-exits-non-zero"
UNPARSEABLE = "unparseable-listing"

GOLDEN_NAMES = {c[0] for c in CASES} | {MAP_MISSING, BWS_NON_ZERO, UNPARSEABLE, NO_BOOTSTRAP_CASE}


@pytest.mark.parametrize(
    ("case_id", "listing", "names", "with_bws", "with_token"), CASES, ids=[c[0] for c in CASES]
)
def test_port_matches_the_twins_recorded_output(
    tmp_path, case_id, listing, names, with_bws, with_token
) -> None:
    root = fixture(tmp_path / case_id, listing, with_bws=with_bws)
    old = recorded(case_id)
    new = run_port(names, env_for(root, with_token), root)
    assert old == new, "case %s: recorded %r vs python %r" % (case_id, old, new)


def test_map_missing(tmp_path) -> None:
    """Its own case because the refusal INTERPOLATES the path, which differs per run."""
    root = fixture(tmp_path / MAP_MISSING, BOTH)
    os.remove(root / ".ci" / "config" / "bws-secret-map.json")
    old = recorded(MAP_MISSING)
    new = run_port([], env_for(root), root)
    assert old == new
    assert "is missing; nothing can be resolved by name." in old[2]
    assert "<root>/.ci/config/bws-secret-map.json" in old[2], (
        "the interpolated path is the whole reason this case is recorded separately"
    )


def with_notice(root, text: str | None = None):
    """Put a rotation notice under the fixture root, so the emitter has one to read."""
    target = root / bws_env.ROTATION_NOTICE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    body = REAL_NOTICE if text is None else text
    target.write_text(body, encoding="utf-8")
    return target


def test_bws_exits_non_zero_is_the_second_deliberate_divergence(tmp_path) -> None:
    """THE ROTATION NOTICE, pinned exactly as the unparseable case below is pinned.

    The twin's second line named `.ci/config/bws-token-expiry.json`, a hand-maintained DATE that `agent/plans/PLAN-bws-rotation-on-failure.md` deletes outright: it was read by one script a human ran occasionally, it never warned CI, and no gate read it. What replaces it is not another prediction but the procedure, printed at the moment of the failure it belongs to.

    BOTH SIDES ARE ASSERTED, so a reader cannot mistake this for drift. The recording still names the file it named on the day it was made, and the port names the notice. Everything else about the case -- the exit code, the empty stdout, the first line of the refusal -- is unchanged, which is what makes this a divergence in ONE decision rather than a rewrite.
    """
    root = fixture(tmp_path / BWS_NON_ZERO, BOTH, bws_body="#!/bin/bash\nexit 9\n")
    with_notice(root)
    old = recorded(BWS_NON_ZERO)
    new = run_port([], env_for(root), root)

    assert old[0] == new[0] == 1, "both still fail; the exit code is not the divergence"
    assert old[1] == new[1] == "", "neither resolves a name"
    assert old[2].splitlines()[0] == new[2].splitlines()[0] == bws_env.LIST_FAILED[0], (
        "the first line of the refusal is the twin's, verbatim"
    )

    assert "bws-token-expiry.json" in old[2], "the recording names the file it named that day"
    assert "bws-token-expiry.json" not in new[2], (
        "the port must not name a file this plan deletes; that is the whole divergence"
    )
    assert "scripts/dev/bws-rotate.py" in new[2], (
        "the notice reached stderr and it names the one command that fixes this"
    )
    assert "DO NOT ask for the token in the conversation" in new[2]


def test_no_access_token_is_the_third_deliberate_divergence(tmp_path) -> None:
    """THE TOKEN MOVED OUT OF `private/account/.env` (agent/plans/PLAN-account-env-to-bws.md T1).

    The twin told a reader to put the token in `private/account/.env`, the file that plan retires. The port names the token FILE instead, which it now reads when the variable is unset. Everything else about the case is the twin's: exit 1, empty stdout, and the first sentence of the reason.
    """
    root = fixture(tmp_path / NO_BOOTSTRAP_CASE, BOTH)
    old = recorded(NO_BOOTSTRAP_CASE)
    new = run_port([], env_for(root, with_token=False), root)
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == ""
    assert "BWS_ACCESS_TOKEN is not set" in old[2]
    assert "BWS_ACCESS_TOKEN is not set" in new[2]
    assert "Put it in private/account/.env." in old[2], (
        "the recording names the file it named that day"
    )
    assert "private/account/.env" not in new[2], (
        "the port must not send a reader to the retired file"
    )
    assert "rediacc/bws-access-token" in new[2]
    assert new[2].splitlines() == bws_env.NO_TOKEN


def test_the_token_file_is_read_when_the_variable_is_unset(tmp_path) -> None:
    """T1: env, then BWS_ACCESS_TOKEN_FILE, then the XDG default. Both directions, and the mode refusal."""
    root = fixture(tmp_path / "tokfile", BOTH)
    env = env_for(root, with_token=False)
    target = pathlib.Path(bws_env.token_path(env))
    assert target == root / "xdg" / "rediacc" / "bws-access-token"
    assert bws_env.read_token(env) == "", "the control: no file, no token"
    target.parent.mkdir(parents=True, mode=0o700)
    target.write_text("from-the-file\n", encoding="utf-8")
    target.chmod(0o600)
    assert bws_env.read_token(env) == "from-the-file"
    assert bws_env.read_token(dict(env, **{bws_env.ACCESS_ENV: "from-env"})) == "from-env", (
        "the environment wins over the file"
    )
    pinned = tmp_path / "pinned"
    pinned.mkdir(mode=0o700)
    (pinned / "t").write_text("pinned-value", encoding="utf-8")
    (pinned / "t").chmod(0o600)
    assert (
        bws_env.read_token(dict(env, **{bws_env.BOOTSTRAP_FILE_ENV: str(pinned / "t")}))
        == "pinned-value"
    )
    code, out, _err = run_port([], env, root)
    assert code == 0
    assert "ALPHA_TOKEN" in out, "names resolves with only the file present"
    target.chmod(0o644)
    with pytest.raises(bws_env.RefusalError) as refused:
        bws_env.read_token(env)
    assert "mode 0644" in refused.value.lines[0]
    target.chmod(0o600)
    target.parent.chmod(0o755)
    with pytest.raises(bws_env.RefusalError):
        bws_env.read_token(env)
    target.parent.chmod(0o700)
    assert bws_env.read_token(env) == "from-the-file", "the control: modes restored, read again"


def test_compare_reports_match_mismatch_absent_and_local_empty(tmp_path) -> None:
    """T5: the read-back instrument. A planted mismatch, a planted absence, a quoted value, and no value on either stream."""
    listing = json.dumps(
        [
            {"key": "ALPHA_TOKEN", "value": "a-val"},
            {"key": "BETA_TOKEN", "value": "b-val"},
            {"key": "QUOTED", "value": "q v"},
            {"key": "STORE_ONLY_ALIAS", "value": "a-val"},
        ]
    )
    root = fixture(tmp_path / "cmp", listing)
    local = root / "local.env"
    local.write_text(
        'ALPHA_TOKEN=a-val\nBETA_TOKEN=planted-mismatch\nQUOTED="q v"\nGONE=x\nBLANK=\n',
        encoding="utf-8",
    )
    code, out, err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env compare '%s'" % local, env=env_for(root)
    )
    assert code == 1
    assert out.splitlines() == [
        "ALPHA_TOKEN MATCH",
        "BETA_TOKEN MISMATCH",
        "BLANK LOCAL-EMPTY",
        "GONE ABSENT",
        "QUOTED MATCH",
    ]
    for stream in (out, err):
        assert "a-val" not in stream
        assert "b-val" not in stream
        assert "planted-mismatch" not in stream
    code, out, _err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env compare '%s' 'STORE_ONLY_ALIAS > ALPHA_TOKEN'"
        % local,
        env=env_for(root),
    )
    assert (code, out) == (0, "ALPHA_TOKEN MATCH\n"), (
        "an alias compares the store name against the LOCAL name"
    )


def _supply(root, consumers: dict) -> None:
    (root / ".ci" / "config" / "secret-supply.json").write_text(
        json.dumps({"consumers": consumers}), encoding="utf-8"
    )


def _exec(env, profile_args: str, probe: str = "env") -> tuple[int, str, str]:
    return diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec %s -- %s" % (profile_args, probe),
        env=env,
    )


def test_exec_binds_exactly_the_profile_and_prints_no_value(tmp_path) -> None:
    """T6: the child env carries the requested LOCAL names, an alias binds LOCAL only, and no value reaches stdout or stderr from the verb itself."""
    listing = json.dumps(
        [
            {"key": "ALPHA_TOKEN", "value": "a-val"},
            {"key": "BETA_TOKEN_DEV", "value": "b-dev-val"},
            {"key": "UNREQUESTED", "value": "u-val"},
        ]
    )
    root = fixture(tmp_path / "exec", listing)
    _supply(
        root,
        {
            "p": {
                "required": ["ALPHA_TOKEN", "BETA_TOKEN_DEV > BETA_TOKEN"],
                "optional": ["NOT_THERE"],
            }
        },
    )
    env = env_for(root)
    probe = 'sh -c \'for n in ALPHA_TOKEN BETA_TOKEN BETA_TOKEN_DEV UNREQUESTED NOT_THERE REDIACC_BWS_PROFILES; do eval "v=\\${$n:-}"; [ -n "$v" ] && echo $n; done; [ "$BETA_TOKEN" = b-dev-val ] && echo BETA_IS_DEV\''
    code, out, err = _exec(env, "--profile p", probe)
    assert code == 0, err
    assert out.splitlines() == ["ALPHA_TOKEN", "BETA_TOKEN", "REDIACC_BWS_PROFILES", "BETA_IS_DEV"]
    assert "NOT_THERE" in err, "an absent OPTIONAL name is named, and does not fail the exec"
    for value in ("a-val", "b-dev-val", "u-val"):
        assert value not in err


def test_exec_lets_the_shell_win_and_skips_inherited_profiles(tmp_path) -> None:
    root = fixture(tmp_path / "shellwins", json.dumps([{"key": "ALPHA_TOKEN", "value": "a-val"}]))
    _supply(root, {"p": {"required": ["ALPHA_TOKEN"]}})
    env = {**env_for(root), "ALPHA_TOKEN": "from-shell"}
    code, out, _err = _exec(env, "--profile p", "printenv ALPHA_TOKEN")
    assert (code, out) == (0, "from-shell\n")
    # An inherited profile is not fetched again: a bws that fails proves no call was made.
    broken = fixture(tmp_path / "inherited", "[]", bws_body="#!/bin/bash\nexit 9\n")
    _supply(broken, {"p": {"required": ["ALPHA_TOKEN"]}})
    env = {**env_for(broken), "REDIACC_BWS_PROFILES": "p"}
    code, _out, _err = _exec(env, "--profile p", "true")
    assert code == 0
    code, _out, err = _exec(dict(env_for(broken)), "--profile p", "true")
    assert code == 1
    assert "secret list failed" in err, "the control: without the marker it does fetch"


def test_exec_refuses_an_unknown_profile_and_a_missing_required_name(tmp_path) -> None:
    root = fixture(tmp_path / "refuse", json.dumps([{"key": "ALPHA_TOKEN", "value": "a-val"}]))
    _supply(root, {"p": {"required": ["ALPHA_TOKEN"]}, "q": {"required": ["NOPE"]}})
    code, _out, err = _exec(env_for(root), "--profile typo", "true")
    assert code == 1
    assert "unknown profile(s): typo" in err
    code, _out, err = _exec(env_for(root), "--profile q", "true")
    assert code == 1
    assert "required name(s) absent or empty in the store: NOPE" in err
    code, _out, err = _exec(env_for(root, with_token=False), "--profile p", "true")
    assert code == 1
    assert err.splitlines() == bws_env.NO_TOKEN, "no token and a required name unset: refuse"
    code, _out, _err = _exec(
        {**env_for(root, with_token=False), "ALPHA_TOKEN": "x"}, "--profile p", "true"
    )
    assert code == 0, "no token, but every required name already set: proceed without a fetch"


def test_cache_to_accepts_a_paired_dev_alias_and_refuses_an_unpaired_one(tmp_path) -> None:
    """T15: the allowlist is on the LOCAL name; the store name must be one the pair table allows."""
    assert (
        bws_env.cache_refusal(["ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY"])
        is None
    )
    refused = bws_env.cache_refusal(
        ["ACCOUNT_ED25519_PRIVATE_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY"]
    )
    assert refused
    assert "outside the pair table" in refused[0]
    root = fixture(
        tmp_path / "cache",
        json.dumps([{"key": "ACCOUNT_ED25519_PUBLIC_KEY_DEV", "value": "pub-dev"}]),
    )
    target = root / "public-keys.env"
    code, _out, err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env cache-to '%s' "
        "'ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY'" % target,
        env=env_for(root),
    )
    assert code == 0, err
    assert target.read_text(encoding="utf-8") == "ACCOUNT_ED25519_PUBLIC_KEY=pub-dev\n"


def test_a_missing_notice_is_reported_and_never_swallowed(tmp_path) -> None:
    """The dangling pointer, out loud. An empty string here would read as "nothing more to say" at the exact moment there is a great deal more to say."""
    root = fixture(tmp_path / "no-notice", BOTH, bws_body="#!/bin/bash\nexit 9\n")
    new = run_port([], env_for(root), root)
    assert new[0] == 1
    assert "bws-rotation-notice.txt is missing or empty" in new[2]
    assert "The credential still needs rotating" in new[2]
    with_notice(root)
    again = run_port([], env_for(root), root)
    assert "is missing or empty" not in again[2], "the control: a present notice is read"


def test_the_real_notice_is_the_one_the_emitters_read() -> None:
    """ANTI-VACUITY on the fixture: every case above plants a COPY of the tracked file, so an emptied tracked file would leave them all passing against text nobody ships."""
    assert len(REAL_NOTICE.strip()) > 400, "the tracked notice is %d byte(s)" % len(REAL_NOTICE)
    assert bws_env.ROTATE_SCRIPT_REL.replace(os.sep, "/") in REAL_NOTICE, (
        "the notice must name the rotation script, or its one actionable line points nowhere"
    )


def test_the_corpus_is_not_empty() -> None:
    assert len(CASES) >= 5, "the differential corpus collapsed to %d case(s)" % len(CASES)


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, GOLDEN_NAMES)


def test_the_comparison_can_fail(tmp_path) -> None:
    """One word changed in a refusal must turn the comparison red."""
    case_id = "empty-value-is-absent"
    root = fixture(tmp_path / case_id, BETA_EMPTY)
    old = recorded(case_id)
    new = run_port([], env_for(root), root)
    assert old == new
    assert old != (new[0], new[1], new[2].replace("absent or empty", "absent")), (
        "the comparison is not looking at stderr, where every refusal lives"
    )
    assert old != (new[0], new[1].replace("ALPHA_TOKEN", "ALPHA"), new[2]), (
        "the comparison is not looking at the resolved name list on stdout"
    )


def test_no_value_reaches_either_stream(tmp_path) -> None:
    """The twin's first stated rule, asserted against the recording AND the port."""
    case_id = "complete-store-every-name"
    root = fixture(tmp_path / case_id, BOTH)
    old = recorded(case_id)
    new = run_port([], env_for(root), root)
    for stream in (old[1], old[2], new[1], new[2]):
        assert "a-val" not in stream
        assert "b-val" not in stream
    assert "ALPHA_TOKEN" in new[1], "the control: the NAME is present, so the check is live"


def test_the_fake_bws_refuses_without_color_no(tmp_path) -> None:
    """A CONTROL ON THE FIXTURE. If the fake stopped checking, dropping `--color no` from either implementation would go unnoticed."""
    root = fixture(tmp_path / "colour", BOTH)
    probe = diff.bash_streams(
        '"%s" secret list --output json' % (root / "bin" / "bws"), env=env_for(root)
    )
    assert probe[0] == 3
    assert "did not pass --color" in probe[2]


def test_unparseable_listing_is_the_one_deliberate_divergence(tmp_path) -> None:
    """A DEFECT IN THE TWIN, reproduced here and NOT reproduced in the port.

    `bws` exiting 0 with output that is not JSON is exactly what `--color no` exists to prevent, so it is the live failure mode if bws ever changes its escaping again. The twin's per-name `python3 -c` then died, its command substitution failed, and the name was filed as `absent or empty in the store`:

      * 36 lines of Python TRACEBACK on stderr, two full copies, one per name
      * `bws-env: 2 name(s) absent or empty in the store: ALPHA_TOKEN BETA_TOKEN`
      * `bws-env: exported 0 secret(s)`

    All of which sends the reader to Bitwarden to look for two secrets that are sitting there perfectly. The port refuses ONCE with the twin's own `bws secret list failed` wording, which names the tool.

    BOTH SIDES ARE ASSERTED so this is a pinned decision and not drift, and the shadow ledger deliberately omits this case: a ledger row is a claim of EQUIVALENCE and there is none to claim here.
    """
    root = fixture(tmp_path / UNPARSEABLE, "not json at all")
    old = recorded(UNPARSEABLE)
    new = run_port([], env_for(root), root)

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


def test_classify_failure_answers_all_three_verdicts() -> None:
    """The ONE classifier, driven directly, in every direction it has.

    BOTH DIRECTIONS ARE REQUIRED HERE. A classifier with only ROTATION cases would be indistinguishable from `return ROTATION`, which is exactly what it looks like at a glance -- and the two branches that are NOT rotations are the two that cost something when they are wrong.
    """
    assert bws_env.classify_failure(0, "") == bws_env.CLEAN
    assert bws_env.classify_failure(0, "anything at all") == bws_env.CLEAN
    assert bws_env.classify_failure(1, "Missing access token") == bws_env.WIRING
    assert bws_env.classify_failure(1, "") == bws_env.ROTATION
    assert bws_env.classify_failure(1, "a string nobody has ever seen") == bws_env.ROTATION
    assert bws_env.classify_failure(-1, "") == bws_env.ROTATION, "a timeout is a failed read"
    for marker in bws_env.ROTATION_MARKERS:
        assert bws_env.classify_failure(1, "error: %s" % marker) == bws_env.ROTATION, marker


def test_failure_notice_is_empty_unless_it_is_a_rotation() -> None:
    assert bws_env.failure_notice(0, "") == []
    assert bws_env.failure_notice(1, "Missing access token") == []
    lines = bws_env.failure_notice(1, "")
    assert lines, "the default direction is ON; an unrecognised failure must print the notice"
    assert any("bws-rotate.py" in line for line in lines)


def test_the_classifier_never_relays_the_bytes_it_read() -> None:
    """`bws`'s stderr is a place values turn up. It is matched and then dropped."""
    poison = "bws-secret-value-that-must-not-be-relayed"
    verdict = bws_env.classify_failure(1, "[400] %s" % poison)
    assert verdict == bws_env.ROTATION
    for line in bws_env.failure_notice(1, "[400] %s" % poison):
        assert poison not in line


def test_client_fingerprint_digests_the_identifier_and_nothing_else() -> None:
    """The computation MOVED out of `warn_if_token_expiring()`, asserted on its own.

    The secret half is varied while the client id is held fixed, and the digest must not move. That is the property that makes printing it safe, and it is not provable by hashing one token and comparing the result with itself.
    """
    one = bws_env.client_fingerprint("0.fixture-client-id.secret-one:key-one")
    two = bws_env.client_fingerprint("0.fixture-client-id.secret-two:key-two")
    assert one == two, "the digest moved when only the SECRET half changed"
    assert len(one) == 16
    assert all(c in "0123456789abcdef" for c in one)
    assert bws_env.client_fingerprint("0.other-client-id.secret-one:key-one") != one
    assert bws_env.client_fingerprint("") == ""
    assert bws_env.client_fingerprint("not-a-token") == ""
    assert bws_env.client_fingerprint("0.only-one-dot") == ""


def test_the_rotation_notice_verb_carries_its_verdict_in_the_exit_code(tmp_path) -> None:
    """The door `scripts/ops/bws-map-refresh.py` uses, driven exactly as it drives it."""
    root = fixture(tmp_path / "verb", BOTH)
    with_notice(root)
    env = env_for(root)

    code, out, err = diff.bash_streams(
        "printf '%s' '' | PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env rotation-notice 1",
        env=env,
    )
    assert code == 0, err
    assert "bws-rotate.py" in out, "a rotation prints the notice on STDOUT"

    code, out, _err = diff.bash_streams(
        "printf 'Missing access token' | PYTHONPATH=.ci python3 -m "
        "rediacc_ci.core.bws_env rotation-notice 1",
        env=env,
    )
    assert code == 3, "a wiring fault has its own exit code"
    assert out == "", "and prints nothing at all"

    code, out, _err = diff.bash_streams(
        "printf '' | PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env rotation-notice 0", env=env
    )
    assert code == 4, "a clean run is not a rotation"
    assert out == "", "and it prints nothing"


def test_the_fingerprint_verb_reads_the_environment_and_never_argv(tmp_path) -> None:
    root = fixture(tmp_path / "fp", BOTH)
    # Token-SHAPED and not a credential: the digest is over the client id, so the shape has to be real for the verb to have anything to hash. No part of this string exists in any store.
    shaped = "0.fixture-client-id.not-a-secret:not-a-key"
    env = dict(env_for(root), **{bws_env.ACCESS_ENV: shaped})
    code, out, _err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env fingerprint", env=env
    )
    assert code == 0
    assert out.strip() == bws_env.client_fingerprint(shaped)
    code, out, err = diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env fingerprint",
        env={k: v for k, v in env.items() if k != bws_env.ACCESS_ENV},
    )
    assert code == 1, "the control: no token, no digest"
    assert out == "", "and nothing on stdout"
    assert "is absent or is not shaped like" in err


def test_bash_and_python_read_the_same_default_name_list() -> None:
    """The REAL map, not a fixture: 0 names would make every case above vacuous."""
    names = bws_env.mapped_names(bws_env.map_path({}))
    assert len(names) > 10, "the real bws-secret-map.json lists only %d name(s)" % len(names)
    assert names == sorted(names)
    assert shutil.which("python3") is not None
