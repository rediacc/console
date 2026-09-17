"""Port of `.ci/scripts/test/gates/test-bws-env.sh`.

Both-ways test for `.ci/lib/bws-env.sh`, the shared Bitwarden fetcher local
scripts use instead of reading `private/account/.env`.

WHY THIS CLASS NEEDS A TEST. Every failure mode of a credential fetcher is quiet
by nature: an empty value exports cleanly, a missing token looks like a network
blip, and a silent fallback to a local file makes a broken fetch work on the
author's machine and nowhere else. So the cases here are mostly REFUSALS, and
each is planted rather than described.

`bws` is faked on PATH. The real binary is never invoked and no live store is
touched -- the fake is the point, not a limitation: it lets the empty-value and
missing-name cases be tested at all, which a live store cannot do on demand.

THE FAKE ASSERTS ITS OWN CALLER. `bws 2.1.0` wraps `--output json` in truecolor
escapes unless `--color no` is passed, and no JSON parser survives that. A fake
that ignored the flag would let a regression in the caller go unnoticed, so this
one exits 3 with a message naming the omission.

WHY THE HELPER IS SOURCED IN A SUBPROCESS. `bws_env_load` EXPORTS into the shell
that sourced it; that is its entire purpose. A Python port cannot be that shell,
so each case runs one `bash -c` that sources the helper, calls it, and prints
`rc=<code>` on the last line -- which is exactly the shape the twin's `run_load`
produces, so the assertions transfer unchanged.
"""

import json
import os
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-bws-env.sh"

HELPER = paths.from_root(".ci", "lib", "bws-env.sh")

BOTH = json.dumps(
    [{"key": "ALPHA_TOKEN", "value": "a-val"}, {"key": "BETA_TOKEN", "value": "b-val"}]
)

MAP = '{ "project": "p", "secrets": { "ALPHA_TOKEN": { "id": "1" }, "BETA_TOKEN": { "id": "2" } } }'

# The bootstrap credential's variable name, held in a constant rather than written at each use. Not style: ruff's S105/S107 flag a literal assigned to anything whose NAME contains `token`, and this fixture value is a five-word string in a public repo. Naming the variable for what it is keeps the rule on
# for every real case instead of switching it off with a per-line suppression.
BOOTSTRAP_CREDENTIAL_ENV = "BWS_ACCESS_TOKEN"
FIXTURE_CREDENTIAL = "fixture-value-never-real"


def fixture(directory, listing: str) -> None:
    """A fake bws plus a map naming two secrets. The twin's `fixture`."""
    (directory / "bin").mkdir(parents=True, exist_ok=True)
    (directory / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (directory / "listing.json").write_text(listing, encoding="utf-8")
    fake = directory / "bin" / "bws"
    fake.write_text(
        "#!/bin/bash\n"
        'for a in "$@"; do [ "$a" = "--color" ] && seen=1; done\n'
        '[ -n "${seen:-}" ] || { echo "fake bws: caller did not pass --color" >&2; exit 3; }\n'
        'cat "%s"\n' % (directory / "listing.json"),
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (directory / ".ci" / "config" / "bws-secret-map.json").write_text(MAP, encoding="utf-8")


def run_load(gate, directory, *names: str, no_token: bool = False) -> str:
    """Source the helper, call `bws_env_load`, return output plus an `rc=` line.

    `no_token=True` is the missing-bootstrap-credential case, spelled as a FLAG
    rather than as `token=None`. A parameter literally named `token` carrying a
    string default is an S107 finding here, and the honest fix is that the two
    modes are a mode, not a value: nothing in this file ever needs a token that
    is not the fixture's.
    """
    if not HELPER.is_file():
        gate.log_fail("subject under test is missing: %s" % HELPER)
    script = 'source "$1"\nshift\nbws_env_load "$@" 2>&1\necho "rc=$?"\n'
    env = {
        "BWS_ENV_ROOT": str(directory),
        "BWS_BIN": str(directory / "bin" / "bws"),
        "PATH": "%s:%s" % (directory / "bin", os.environ.get("PATH", "")),
    }
    argv = ["bash", "-c", script, "bws-env-port", str(HELPER), *names]
    if no_token:
        # A REPLACED environment, not an overlay: the operator's own shell may legitimately export BWS_ACCESS_TOKEN, and inheriting it would make this
        # case silently assert the opposite of what it says.
        merged = dict(os.environ)
        merged.pop(BOOTSTRAP_CREDENTIAL_ENV, None)
        merged.update(env)
        return harness.run(argv, env=merged, env_replace=True).combined
    env[BOOTSTRAP_CREDENTIAL_ENV] = FIXTURE_CREDENTIAL
    return harness.run(argv, env=env).combined


def test_loads_both(gate, tmp_path):
    fixture(tmp_path, BOTH)
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "exported 2 secret(s)", "a complete store exports every mapped name")
    gate.assert_contains(out, "rc=0", "and succeeds")
    gate.assert_not_contains(out, "a-val", "NEVER prints a value")
    gate.log_pass("loads every mapped name, and prints no value")


def test_named_subset(gate, tmp_path):
    fixture(tmp_path, BOTH)
    out = run_load(gate, tmp_path, "ALPHA_TOKEN")
    gate.assert_contains(out, "exported 1 secret(s)", "an explicit list fetches only those")
    gate.log_pass("an explicit name list is honoured")


def test_empty_value_is_absent(gate, tmp_path):
    # The whole point: sm-action exports "" without complaint and zod strips an unknown key, so a blank ships a broken feature that still returns 200.
    fixture(
        tmp_path,
        json.dumps([{"key": "ALPHA_TOKEN", "value": ""}, {"key": "BETA_TOKEN", "value": "b"}]),
    )
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "ALPHA_TOKEN", "the empty name is reported")
    gate.assert_contains(out, "rc=1", "an empty value FAILS rather than exporting a blank")
    gate.log_pass("an empty stored value is treated as absent, and fails")


def test_missing_name_fails(gate, tmp_path):
    fixture(tmp_path, json.dumps([{"key": "ALPHA_TOKEN", "value": "a"}]))
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "BETA_TOKEN", "the missing name is named")
    gate.assert_contains(out, "rc=1", "a mapped name the store lacks fails")
    gate.log_pass("a mapped name absent from the store fails, naming it")


def test_no_token_refuses(gate, tmp_path):
    fixture(tmp_path, BOTH)
    out = run_load(gate, tmp_path, no_token=True)
    gate.assert_contains(out, "BWS_ACCESS_TOKEN is not set", "says which credential is missing")
    gate.assert_contains(out, "cannot come from Bitwarden", "and why it cannot be fetched")
    gate.assert_contains(out, "rc=1", "refuses")
    gate.log_pass("a missing bootstrap token refuses with the reason")


def test_bws_failure_is_not_silent(gate, tmp_path):
    fixture(tmp_path, BOTH)
    fake = tmp_path / "bin" / "bws"
    fake.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "secret list failed", "a failing bws is reported")
    gate.assert_contains(out, "expired", "and points at the likeliest cause")
    gate.assert_contains(out, "rc=1", "refuses")
    gate.log_pass("a failing bws call is named, not swallowed")


def test_never_falls_back_to_env(gate, tmp_path):
    # A silent fallback is how a fetch that stopped working keeps passing locally.
    fixture(tmp_path, json.dumps([{"key": "BETA_TOKEN", "value": "b"}]))
    (tmp_path / "private" / "account").mkdir(parents=True, exist_ok=True)
    (tmp_path / "private" / "account" / ".env").write_text(
        "ALPHA_TOKEN=from-dot-env\n", encoding="utf-8"
    )
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "rc=1", "an absent name still fails even when .env has it")
    gate.assert_not_contains(out, "from-dot-env", "and the local copy is never read")
    gate.log_pass("no silent fallback to .env")


def test_the_fake_bws_is_load_bearing(gate, tmp_path):
    """PORT-ONLY, and it is the control the twin implies without asserting.

    Every case above rests on a fake `bws` that REFUSES a caller which drops
    `--color no`. If the subject stopped passing that flag, `bws 2.1.0` would
    wrap `--output json` in truecolor escapes and no JSON parser would survive
    it -- so the flag is a real property, not tidiness. This asserts both halves:
    the subject still passes it, and the fake really does reject a caller that
    does not, which is what makes every green above mean something.
    """
    gate.assert_contains(
        HELPER.read_text(encoding="utf-8"),
        "--color no",
        "the subject stopped passing --color no; bws would wrap its JSON in escapes",
    )
    fixture(tmp_path, BOTH)
    fake = tmp_path / "bin" / "bws"
    naked = harness.run(["bash", str(fake), "secret", "list", "--output", "json"])
    gate.assert_exit_code(3, naked.rc, "the fake must refuse a caller that drops --color")
    gate.assert_contains(
        naked.combined, "did not pass --color", "and must say which flag was missing"
    )
    gate.log_pass("the fake bws refuses a colour-blind caller, so the cases above are real")
