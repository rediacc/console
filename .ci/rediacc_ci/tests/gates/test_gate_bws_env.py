"""Port of `.ci/scripts/test/gates/test-bws-env.sh`, retired in W7 P5.

Both-ways test for `rediacc_ci.core.bws_env`, the shared Bitwarden fetcher local scripts use instead of reading `private/account/.env`.

THE SUBJECT MOVED WHEN ITS BASH TWIN WENT. This file drove `.ci/lib/bws-env.sh` until that helper was retired: it had zero sourcers, its equivalence with the port is recorded over five distinct trees in `.ci/shadow/w7p5b-bws-env.observations.jsonl`, and the helper's own bytes are frozen under `goldens/bws-env/`. The assertions below are UNCHANGED, which is the point of naming
them after behaviour rather than after an implementation: every refusal, every count and every "rc=" line is the same string it was when a shell printed it.

WHY THIS CLASS NEEDS A TEST. Every failure mode of a credential fetcher is quiet by nature: an empty value exports cleanly, a missing token looks like a network blip, and a silent fallback to a local file makes a broken fetch work on the author's machine and nowhere else. So the cases here are mostly REFUSALS, and each is planted rather than described.

`bws` is faked on PATH. The real binary is never invoked and no live store is touched -- the fake is the point, not a limitation: it lets the empty-value and missing-name cases be tested at all, which a live store cannot do on demand.

THE FAKE ASSERTS ITS OWN CALLER. `bws 2.1.0` wraps `--output json` in truecolor escapes unless `--color no` is passed, and no JSON parser survives that. A fake that ignored the flag would let a regression in the caller go unnoticed, so this one exits 3 with a message naming the omission.

WHY THE SUBJECT IS DRIVEN IN A SUBPROCESS. `bws_env_load` EXPORTED into the shell that sourced it; that was its entire purpose, and a child process cannot mutate its parent's environment, so the port resolves and REPORTS instead. Each case runs one `bash -c` that invokes the port's `names` verb and prints `rc=<code>` on the last line -- which is exactly the shape the twin's
`run_load` produced, so the assertions transfer unchanged.
"""

import importlib.util
import json
import os
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.core import bws_env
from rediacc_ci.tests.gates import harness


def load_gate_module(name: str):
    """Load a `.ci/scripts/quality` script by PATH, without putting it on sys.path.

    BY PATH AND NOT BY A `sys.path` HOP, for two separate reasons. The tree has exactly one canonical way onto `sys.path`, guarded by `test_canonical_sys_path_hop.py`, so a hand-written hop here would be a finding in its own right.

    And a directory of forty gate scripts on `sys.path` makes every one of their module names importable from every test, which is how a test comes to depend on a neighbour it never meant to name.

    THE CANONICAL HOP IS STILL NEEDED, and that is not a contradiction of the paragraph above. These scripts open with `import _cipath`, which resolves only because running one from PATH puts its own directory on `sys.path[0]`; loading by path does no such thing, so without the hop the subject dies at its first import line.
    `paths.on_sys_path` is this repo's one sanctioned spelling for it, so the hop is declared rather than hand-written, and the by-path load still keeps the module name explicit.
    """
    paths.on_sys_path(paths.quality_dir())
    src = paths.from_root(".ci", "scripts", "quality", "%s.py" % name)
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUBJECT = paths.from_root(".ci", "rediacc_ci", "core", "bws_env.py")

# The nine fields of one company record, and the one deliberately left out of the fixture in B8. Named here rather than inline so the "which key is missing" assertion cannot accidentally assert the presence of the key it removed.
SELLER_FIELDS = (
    "SELLER_ADDRESS_LINE1",
    "SELLER_ADDRESS_LINE2",
    "SELLER_CITY",
    "SELLER_COUNTRY",
    "SELLER_EMAIL",
    "SELLER_NAME",
    "SELLER_POSTAL_CODE",
    "SELLER_REGISTRATION_NUMBER",
    "SELLER_VAT_NUMBER",
)
OMITTED_FIELD = "SELLER_CITY"

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
    string default is an S107 finding here, and the honest fix is that the two modes are a mode, not a value: nothing in this file ever needs a token that is not the fixture's.
    """
    if not SUBJECT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUBJECT)
    script = 'python3 -m rediacc_ci.core.bws_env names "$@" 2>&1\necho "rc=$?"\n'
    env = {
        "BWS_ENV_ROOT": str(directory),
        "BWS_BIN": str(directory / "bin" / "bws"),
        "PATH": "%s:%s" % (directory / "bin", os.environ.get("PATH", "")),
        "PYTHONPATH": str(paths.from_root(".ci")),
    }
    argv = ["bash", "-c", script, "bws-env-port", *names]
    if no_token:
        # A REPLACED environment, not an overlay: the operator's own shell may legitimately export BWS_ACCESS_TOKEN, and inheriting it would make this
        # case silently assert the opposite of what it says.
        merged = dict(os.environ)
        merged.pop(BOOTSTRAP_CREDENTIAL_ENV, None)
        merged.update(env)
        return harness.run(argv, env=merged, env_replace=True).combined
    env[BOOTSTRAP_CREDENTIAL_ENV] = FIXTURE_CREDENTIAL
    return harness.run(argv, env=env).combined


def run_verb(gate, directory, *argv: str) -> str:
    """`run_load` for any verb. Same fake `bws`, same fixture credential, same `rc=` tail.

    A SECOND ENTRY POINT RATHER THAN A FLAG ON `run_load`, because `run_load` pins the verb `names` and every case above reads better for it. The environment is built once here and shared, so a case that forgot BWS_ENV_ROOT could not silently reach the real repository's map.
    """
    if not SUBJECT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUBJECT)
    script = 'python3 -m rediacc_ci.core.bws_env "$@" 2>&1\necho "rc=$?"\n'
    env = {
        "BWS_ENV_ROOT": str(directory),
        "BWS_BIN": str(directory / "bin" / "bws"),
        "PATH": "%s:%s" % (directory / "bin", os.environ.get("PATH", "")),
        "PYTHONPATH": str(paths.from_root(".ci")),
        BOOTSTRAP_CREDENTIAL_ENV: FIXTURE_CREDENTIAL,
    }
    return harness.run(["bash", "-c", script, "bws-env-port", *argv], env=env).combined


def single_entry(name: str, value: str) -> str:
    """A one-row listing plus the matching map, for the cases that fetch one entry."""
    return json.dumps([{"key": name, "value": value}])


def one_name_fixture(directory, name: str, value: str) -> None:
    fixture(directory, single_entry(name, value))
    (directory / ".ci" / "config" / "bws-secret-map.json").write_text(
        json.dumps({"project": "p", "secrets": {name: {"id": "1"}}}), encoding="utf-8"
    )


def test_the_shim_really_shadows_any_real_bws(gate, tmp_path):
    """THE PRECONDITION EVERY CASE BELOW RESTS ON, and it was missing until now.

    `agent/plans/PLAN-env-to-bitwarden-v2.md` Part 5 calls this mandatory and says why in one sentence: "without it a broken shim silently tests the real CLI against the real org".
    The file pinned `BWS_BIN` directly, which is a stronger guarantee for the SUBJECT and no guarantee at all for anything the subject shells out to, or for a future case that drops the pin and relies on PATH alone.

    Both halves are asserted. That `command -v bws` under the case environment resolves INSIDE the shim directory -- not merely that it resolves -- and that the thing it resolves to is the fake, by asking it to prove it is the fake. A real `bws` answering here would mean every refusal below was measured against somebody's live Bitwarden organisation.
    """
    fixture(tmp_path, BOTH)
    shim = tmp_path / "bin"
    env = {
        "PATH": "%s:%s" % (shim, os.environ.get("PATH", "")),
        BOOTSTRAP_CREDENTIAL_ENV: FIXTURE_CREDENTIAL,
    }
    found = harness.run(["bash", "-c", "command -v bws"], env=env).out.strip()
    gate.assert_eq(
        found,
        str(shim / "bws"),
        "`bws` on PATH is not the shim; the cases below would hit the real CLI",
    )
    naked = harness.run(["bash", str(shim / "bws"), "secret", "list", "--output", "json"])
    gate.assert_exit_code(3, naked.rc, "what PATH resolved to does not behave like the fake")
    gate.log_pass("the shim shadows any real bws, so no case below can reach a live store")


def test_a_real_bws_is_not_required(gate):
    """The other half of the precondition: this file must not need the real tool.

    A gate test that silently needs a binary the environment may lack is a gate test that turns into an environmental flake, and the fix gets recorded as "CI is flaky". Asserting the absence is fine and the presence is fine; what must be true is that neither changes the verdict, which is exactly what pinning BWS_BIN to the shim buys.
    """
    real = shutil.which("bws")
    gate.log_info("real bws on PATH: %s" % (real or "absent, which is also fine"))
    gate.assert_contains(
        SUBJECT.read_text(encoding="utf-8"),
        'environ.get("BWS_BIN", "")',
        "the subject stopped honouring BWS_BIN, so the shim can no longer be pinned",
    )
    gate.log_pass("the suite pins BWS_BIN and so never depends on a real bws being installed")


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

    Every case above rests on a fake `bws` that REFUSES a caller which drops `--color no`. If the subject stopped passing that flag, `bws 2.1.0` would wrap `--output json` in truecolor escapes and no JSON parser would survive it -- so the flag is a real property, not tidiness.
    This asserts both halves: the subject still passes it, and the fake really does reject a caller that does not, which is what makes every green above mean something.
    """
    gate.assert_contains(
        SUBJECT.read_text(encoding="utf-8"),
        '"--color", "no"',
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


def test_b4_a_hostile_value_binds_verbatim_and_executes_nothing(gate, tmp_path):
    """B4. A value carrying `$(...)`, backticks, a newline and `-----BEGIN` runs nothing.

    THE CONTROL IS A FILE THAT MUST NOT EXIST AFTERWARDS, not an exit code. An `eval`-based implementation of this same fetch would bind the variable correctly, exit 0, and create the sentinel on the way past -- so every assertion about the binding would pass while the process had already run attacker-chosen code.
    The plan spells the control out for exactly this reason: "assert `$SENTINEL` does not exist".

    The port cannot `eval` by construction (it is Python and there is no shell in the path from `bws` to the mapping), which is the whole argument for route 2 in the module docstring. That argument is worth an assertion anyway: it is a property of the current implementation, and the next person to add a convenience verb is the reader this case is written for.
    """
    sentinel = tmp_path / "SENTINEL-B4-must-not-exist"
    hostile = "$(touch %s)\n`touch %s`\n-----BEGIN OPENSSH PRIVATE KEY-----\n$SHELL;rm -rf /" % (
        sentinel,
        sentinel,
    )
    one_name_fixture(tmp_path, "ALPHA_TOKEN", hostile)
    out = run_load(gate, tmp_path)
    gate.assert_contains(out, "exported 1 secret(s)", "the hostile value still resolves")
    gate.assert_contains(out, "rc=0", "and is not itself an error")
    # `log_fail` AND NOT `no`, and the difference is not stylistic. `gate.no()` records a failure and KEEPS GOING; it only turns into a verdict if `tally_finish()` is called, which this file never does. Written with `no()` this assertion printed FAIL and the test passed -- caught by planting an eval-based `load` and watching the case stay green.
    if sentinel.exists():
        gate.log_fail("the sentinel exists: the value was EVALUATED, not bound")
    gate.ok("nothing was executed: the sentinel was never created")
    gate.assert_not_contains(out, "BEGIN OPENSSH", "and the value never reaches a stream")
    gate.log_pass("a value full of shell metacharacters binds verbatim and executes nothing")


def test_b6_the_alias_grammar_binds_the_local_name_only(gate, tmp_path):
    """B6. `NAME > LOCAL` binds LOCAL and leaves NAME unbound.

    This is the `AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID` collapse that `.github/workflows/ci.yml` already performs, expressed in the fetch instead of by renaming either side.
    A helper that bound BOTH names would look correct in every test that only checks the local one, and would quietly put a regional key under an unsuffixed name in every consumer that iterates what it was given.
    """
    fixture(tmp_path, BOTH)
    out = run_verb(gate, tmp_path, "names", "ALPHA_TOKEN > LOCAL_ALPHA")
    gate.assert_contains(out, "LOCAL_ALPHA", "the local name is bound")
    gate.assert_not_contains(out, "ALPHA_TOKEN", "and the store name is NOT also bound")
    gate.assert_contains(out, "exported 1 secret(s)", "one binding, not two")
    gate.assert_contains(out, "rc=0", "and it succeeds")
    gate.log_pass("the alias grammar binds the local name and only the local name")


def test_b6b_an_aliased_name_absent_from_the_store_names_the_store_name(gate, tmp_path):
    """The half of B6 that decides where a reader goes looking.

    When `MISSING_IN_STORE > LOCAL` fails, the thing that is absent is an entry in Bitwarden. Reporting `LOCAL` would send a reader to search the store for a name that was never meant to be there, which is a five-minute detour built into every alias.
    """
    fixture(tmp_path, BOTH)
    out = run_verb(gate, tmp_path, "names", "NOT_IN_STORE > LOCAL_NAME")
    gate.assert_contains(out, "NOT_IN_STORE", "the STORE name is the one reported absent")
    gate.assert_not_contains(out, "LOCAL_NAME", "not the local alias, which the store never had")
    gate.assert_contains(out, "rc=1", "and it fails")
    gate.log_pass("an absent aliased name is reported by its STORE name")


def test_b7_grammar_parity_with_the_gate_that_reads_the_same_blocks(gate):
    """B7. The fetch and `check_bws_map.parse_requests` parse one grammar identically.

    TWO PARSERS FOR ONE GRAMMAR IS A GRAMMAR THAT MEANS TWO THINGS. The gate reads the `secrets: |` blocks in every workflow and asserts each requested name is in the map; the fetch reads the same shape from a caller.
    If one strips `#` comments and the other does not, the gate blesses a request the fetch would silently drop, and the failure surfaces as a missing environment variable in a deploy rather than as a red check.

    The alias set is down to three names, which makes this MORE important and not less: three is few enough that a broken alias parser still looks like it works on the other fifty-odd.

    The fixture deliberately includes every edge the two must agree on: a bare name, an alias, an alias with ragged spacing, a full-line comment, a trailing comment, a blank line, and a line that is nothing but whitespace.
    """
    check_bws_map = load_gate_module("check_bws_map")
    lines = [
        "ALPHA_TOKEN",
        "BETA_TOKEN > LOCAL_BETA",
        "  GAMMA_TOKEN   >   LOCAL_GAMMA  ",
        "# a whole-line comment",
        "DELTA_TOKEN  # a trailing comment",
        "",
        "   ",
        "EPSILON_TOKEN>NOSPACE",
    ]
    # TWELVE SPACES, AND THE FIRST DRAFT USED SIX. `parse_requests` reads the indent of the `secrets:` key itself as the base and stops at the first line indented no further, so a block indented LESS than its key parses as zero requests -- and this parity assertion would then have compared two empty lists and gone green. That is what the length assertion below is for.
    block = "\n".join("            " + line if line.strip() else line for line in lines)
    yaml_text = (
        "jobs:\n  j:\n    steps:\n      - uses: ./.github/actions/bws-secrets\n"
        "        with:\n          secrets: |\n" + block + "\n      - name: next\n"
    )
    theirs = [(name, env) for _line, name, env in check_bws_map.parse_requests(yaml_text)]
    ours = bws_env.parse_specs(lines)
    gate.assert_eq(ours, theirs, "the fetch and the gate disagree about the request grammar")
    # ANTI-VACUITY: two empty lists are equal. If the fixture stopped reaching either parser this would pass while proving nothing, which is the exact shape this repo refuses.
    gate.assert_eq(len(ours), 5, "the fixture stopped reaching the parsers; parity proves nothing")
    gate.assert_contains(str(ours), "LOCAL_GAMMA", "ragged spacing around `>` is still an alias")
    gate.log_pass("both parsers agree on all 8 fixture lines, and 5 of them are real requests")


def test_b8_json_expansion_refuses_a_partial_record_by_name(gate, tmp_path):
    """B8. Nine `SELLER_*` bind from one object; a record missing one fails, naming it.

    THE PLANTED DEFECT IS A HELPER THAT BINDS THE EIGHT IT FOUND AND RETURNS 0. That is not a hypothetical shape, it is the natural one: iterate the object, bind each key, report success. It ships an invoice with a blank city, and nothing anywhere is red.
    """
    record = {k: "v-%s" % k for k in SELLER_FIELDS}
    one_name_fixture(tmp_path, "SELLER_PROFILE_JSON", json.dumps(record))
    out = run_verb(gate, tmp_path, "json", "SELLER_PROFILE_JSON")
    gate.assert_contains(out, "expanded to 9 binding(s)", "a whole record binds all nine fields")
    gate.assert_contains(out, "rc=0", "and succeeds")
    for field in SELLER_FIELDS:
        gate.assert_contains(out, field, "%s was not bound" % field)
    gate.assert_not_contains(out, "v-SELLER_CITY", "and no VALUE reaches the stream")

    partial = {k: v for k, v in record.items() if k != OMITTED_FIELD}
    one_name_fixture(tmp_path, "SELLER_PROFILE_JSON", json.dumps(partial))
    out = run_verb(gate, tmp_path, "json", "SELLER_PROFILE_JSON")
    gate.assert_contains(out, OMITTED_FIELD, "the refusal must NAME the missing field")
    gate.assert_contains(out, "rc=1", "a partial company record is a failure, not eight bindings")
    gate.log_pass("a whole record expands to nine; a record missing one fails naming it")


def test_b9_json_refuses_a_non_object_and_an_illegal_key(gate, tmp_path):
    """B9. A JSON string, a JSON list and a key with a dash are each refused.

    Two different planted defects, and they fail differently. A helper that iterates a STRING binds one variable per character; one that iterates a LIST binds integers. A helper that `declare -g`s `not-an-identifier` creates a variable no shell can export and no consumer can read, which is strictly worse than absent because absent is loud.
    """
    for label, payload in (
        ("a JSON string", json.dumps("just-a-string")),
        ("a JSON list", json.dumps(["a", "b"])),
        ("a JSON number", json.dumps(42)),
    ):
        one_name_fixture(tmp_path, "BLOB", payload)
        out = run_verb(gate, tmp_path, "json", "BLOB")
        gate.assert_contains(out, "not an object", "%s was not refused as a non-object" % label)
        gate.assert_contains(out, "rc=1", "%s must fail" % label)
        gate.ok("refused %s" % label)

    one_name_fixture(tmp_path, "BLOB", json.dumps({"ok_key": "1", "not-an-identifier": "2"}))
    out = run_verb(gate, tmp_path, "json", "BLOB")
    gate.assert_contains(out, "not-an-identifier", "the illegal key must be NAMED")
    gate.assert_contains(out, "rc=1", "an illegal key must fail the whole expansion")
    gate.assert_not_contains(out, "expanded to", "and must not report a partial success")
    gate.log_pass("a non-object and an illegal key are each refused, by name")


def test_b10_cache_to_refuses_a_private_key_and_writes_no_file(gate, tmp_path):
    """B10. `cache-to` outside the three-name public allowlist refuses AND writes nothing.

    THE SECOND HALF IS THE ONE THAT MATTERS AND THE PLAN SAYS SO: "assert the target path does not exist afterwards, not merely that the exit code is non-zero". A helper that fetches, writes, then notices the name was not allowed and exits 1 satisfies every exit-code assertion while leaving a private key on disk at 0644 for whoever reads next.

    The positive control is here too. An allowlist that refuses EVERYTHING also passes the refusal half, and a `cache-to` that never writes is a `cache-to` that quietly sends four build-time readers back to `.env` -- the silent second source of truth this verb exists to remove.
    """
    target = tmp_path / "public-keys.env"
    private_name = "ACCOUNT_ED25519_PRIVATE_KEY"
    one_name_fixture(tmp_path, private_name, "PRIVATE-KEY-MATERIAL-MUST-NOT-BE-WRITTEN")
    out = run_verb(gate, tmp_path, "cache-to", str(target), private_name)
    gate.assert_contains(out, "outside the public allowlist", "the refusal names what it refused")
    gate.assert_contains(out, private_name, "and names the offending key")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.assert_not_contains(out, "PRIVATE-KEY-MATERIAL", "and never puts the value on a stream")
    # THE HALF THE PLAN CALLS THE ONE THAT MATTERS, so it must RAISE. See the note in B4: `gate.no()` would print FAIL and let this test pass, which would leave a private key on disk with a green check over it.
    if target.exists():
        gate.log_fail("cache-to WROTE %s for a private key; exit code alone is not enough" % target)
    gate.ok("no file was written for a refused name")

    public_name = "ACCOUNT_ED25519_PUBLIC_KEY"
    one_name_fixture(tmp_path, public_name, "ssh-ed25519-AAAA-public")
    out = run_verb(gate, tmp_path, "cache-to", str(target), public_name)
    gate.assert_contains(out, "rc=0", "CONTROL: an allowlisted public key IS cached")
    gate.assert_contains(out, "mode 0644", "and says so, including the mode a reader needs")
    gate.assert_eq(
        target.read_text(encoding="utf-8"),
        "%s=ssh-ed25519-AAAA-public\n" % public_name,
        "the cache file's contents are not the NAME=value line four readers sed",
    )
    gate.assert_eq(
        stat.S_IMODE(target.stat().st_mode),
        0o644,
        "the cache is not 0644, so a build may not read it",
    )
    gate.log_pass("cache-to refuses a private key and writes nothing; a public key IS written 0644")


def test_b10b_a_partial_cache_is_never_written(gate, tmp_path):
    """The failure that would send every build-time reader back to `.env`.

    All three names are allowlisted, so the refusal above does not fire; one of them is simply absent from the store. A cache holding two of three keys is worse than no cache, because the four readers at `agent/plans/PLAN-env-to-bitwarden-v2.md` 0.4 each fall back to `.env` for the one they cannot find and the second source of truth is back without anyone deciding to restore it.
    """
    target = tmp_path / "public-keys.env"
    fixture(tmp_path, json.dumps([{"key": "ACCOUNT_ED25519_PUBLIC_KEY", "value": "one"}]))
    out = run_verb(
        gate,
        tmp_path,
        "cache-to",
        str(target),
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PUBLIC_KEY",
    )
    gate.assert_contains(out, "partial cache", "the refusal says what it declined to do")
    gate.assert_contains(out, "rc=1", "and fails")
    if target.exists():
        gate.log_fail("a partial cache was written to %s" % target)
    gate.ok("no partial cache file exists")
    gate.log_pass("an incomplete fetch writes no cache at all")
