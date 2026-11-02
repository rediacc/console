"""Port of `.ci/scripts/test/gates/test-bws-map.sh`, retired in W7 P5.

Drives the REAL scan in `.ci/scripts/quality/check_bws_map.py` against fixture trees, which its internal `selftest()` cannot do.

WHY BOTH EXIST. `selftest()` proves the pure logic -- the request parser and every way of writing a bad exemption -- and it runs before any verdict, so a broken instrument never judges anything. What it CANNOT reach is assertions 5-9, which are defined over the tree: the map, the allowlist, the reachability record, the workflows and the deploy scripts. Those had no fixture coverage
at all, and they are about to be the sole guard on every credential once GitHub secrets go away. A gate whose only controls are internal is thinner than this repo's standard for far less load-bearing checks.

`BWS_MAP_ROOT` re-points every ROOT-derived path at a fixture. It is not an escape hatch: the anti-vacuity clauses fail on a tree that holds nothing, which the last case here proves.

THE FIXTURE IS A GIT REPOSITORY, and that is not scaffolding. The gate's corpus scan enumerates TRACKED files, so a fixture with an untracked map is a fixture the gate reads as empty -- and it would then fail every case for the wrong reason. `git init` plus one commit is the cheapest way to be a tree the subject can actually see.
"""

import importlib.util
import json

from rediacc_ci import paths
from rediacc_ci.core.bws_env import ARCHIVE_PATTERN, JSON_REQUIRED, PARKED_PATTERN
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_bws_map.py")

WORKFLOW = """jobs:
  j:
    steps:
      - uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ALPHA_TOKEN > BWS_ALPHA_TOKEN
      # SHADOW_NAMES is not decoration here: assertion 11 requires the three
      # spellings to name the same set, because the compare step derives GH_$n
      # and BWS_$n by concatenation. A leg with no SHADOW_NAMES entry is fetched
      # and never checked, which is a shadow that verifies nothing.
      - env:
          SHADOW_NAMES: ALPHA_TOKEN
          GH_ALPHA_TOKEN: ${{ secrets.ALPHA_TOKEN }}
        run: echo hi
      # A CUT-OVER CONSUMER, and it is not decoration either: assertion 13 refuses to
      # pass a tree with no `${{ env.BWS_* }}` read at all, because "nothing reads
      # Bitwarden" is what a scan that lost its subject looks like.
      - env:
          USED: ${{ env.BWS_ALPHA_TOKEN }}
        run: echo consumed
"""

SECRET_MAP = {
    "refreshed_at": "2099-01-01T00:00:00Z",
    "project": "p",
    "secrets": {
        "ALPHA_TOKEN": {"id": "aaaaaaaa-0000-4000-8000-000000000001"},
        "ORPHAN_TOKEN": {"id": "aaaaaaaa-0000-4000-8000-000000000002"},
        # PREFIX_EU must be mapped or exempt: the deploy module below builds it from its SUFFIXED_PREFIXES tuple and regions.json.
        "PREFIX_EU": {"id": "aaaaaaaa-0000-4000-8000-000000000003"},
    },
}

EXEMPTIONS = {
    "exemptions": {
        "ORPHAN_TOKEN": {"kind": "no-github-twin", "reason": "fixture"},
        "PREFIX_EU": {"kind": "no-github-twin", "reason": "built by SUFFIX expansion, no twin"},
    }
}

REACHABILITY = {
    "refreshed_at": "2099-01-01T00:00:00Z",
    "repos": {"console": {"ALPHA_TOKEN": {"reachable": True, "via": "org:all"}}},
}

# ASSERTION 14 READS .ci/config/secret-supply.json UNCONDITIONALLY and refuses when the `account-dev` profile binds no SELLER_* name, so the fixture carries a profile binding exactly the nine fields `bws_env.JSON_REQUIRED["SELLER_PROFILE_JSON"]` declares. Imported, not re-typed, for the same reason the gate imports them: a second copy here would test the fixture against itself.
SELLER_FIELDS = sorted(JSON_REQUIRED["SELLER_PROFILE_JSON"])


def supply(fields) -> dict:
    return {
        "consumers": {
            "account-dev": {
                "why": "fixture",
                "required": ["AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID"],
                "optional": list(fields),
            }
        }
    }


def write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(gate, directory) -> None:
    """A minimal tree the gate can judge. The twin's `fixture`, same contents."""
    for sub in (
        ".ci/config",
        ".ci/rediacc_ci/deploy",
        ".github/workflows",
        ".github/actions",
        "scripts/ops",
    ):
        (directory / sub).mkdir(parents=True, exist_ok=True)
    git = harness.require_tool(
        "git",
        "install git; the fixture must be a REAL repository or the gate's "
        "tracked-file scan reads it as empty and every case below fails for the "
        "wrong reason",
    )
    init = harness.run([git, "init", "-q", "."], cwd=directory)
    if init.rc != 0:
        gate.log_fail("could not git-init the fixture", init)
    write(directory / ".ci/config/bws-secret-map.json", json.dumps(SECRET_MAP))
    write(directory / ".ci/config/bws-unrequested.json", json.dumps(EXEMPTIONS))
    write(directory / ".ci/config/secret-reachability.json", json.dumps(REACHABILITY))
    write(directory / ".ci/config/secret-supply.json", json.dumps(supply(SELLER_FIELDS)))
    write(directory / "regions.json", '{"regions":[{"secretSuffix":"EU"}]}')
    # The fan-in is a module-level SUFFIXED_PREFIXES tuple since the Worker-deploy bash twins were ported (ca8d42f5c); assertion 7 reads it there, not a `PREFIX_${SUFFIX}` line in a deploy .sh.
    write(
        directory / ".ci/rediacc_ci/deploy/build.py",
        'SUFFIXED_PREFIXES = ("PREFIX",)\n'
        "# ORPHAN_TOKEN PREFIX_EU are named here so the corpus scan sees them\n",
    )
    write(
        directory / "scripts/ops/secret-rename.py",
        'RENAMES: list[tuple[str, str]] = [\n    ("OLD_ALPHA", "ALPHA_TOKEN"),\n]\n',
    )
    # ASSERTION 15 reads the two files that pin the archive regex and refuses when either is unreadable or does not declare ARCHIVE_RE with bws_env.ARCHIVE_PATTERN, so the fixture carries a declaration in each, in the form the gate parses.
    write(
        directory / "private/account/scripts/rotation/consumers/bitwarden-sm.ts",
        "export const ARCHIVE_RE = /%s/\n" % ARCHIVE_PATTERN,
    )
    # ASSERTION 16 reads the same refresher for its PARKED_RE declaration, so the fixture declares both.
    write(
        directory / "scripts/ops/bws-map-refresh.py",
        'import re\n\nARCHIVE_RE = re.compile(r"%s")\nPARKED_RE = re.compile(r"%s")\n'
        % (ARCHIVE_PATTERN, PARKED_PATTERN),
    )
    write(directory / ".github/workflows/w.yml", WORKFLOW)
    harness.run([git, "add", "-A"], cwd=directory)
    commit = harness.run(
        [git, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=directory,
    )
    if commit.rc != 0:
        gate.log_fail("could not commit the fixture", commit)


def run_gate(gate, root) -> str:
    """The gate's merged output plus an `rc=` line, the twin's `run_gate` shape."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    python3 = harness.require_tool(
        "python3",
        "install python3; the subject IS a python3 program and the pytest running "
        "this file may be a uv tool carrying its own interpreter, so its presence "
        "proves nothing about the one the gate is invoked with",
    )
    result = harness.run(
        [python3, str(GATE)],
        env={"BWS_MAP_ROOT": str(root), "BWS_MIN_MAP_ENTRIES": "1", "BWS_MIN_CALLERS": "1"},
    )
    return "%s\nrc=%d" % (result.combined, result.rc)


def test_clean_fixture_passes(gate, tmp_path):
    fixture(gate, tmp_path)
    out = run_gate(gate, tmp_path)
    gate.assert_contains(
        out, "rc=0", "a coherent fixture tree must pass, or every case below proves nothing"
    )
    gate.log_pass("CONTROL: a coherent fixture tree passes")


def test_unexempted_orphan_reds(gate, tmp_path):
    fixture(gate, tmp_path)
    write(
        tmp_path / ".ci/config/bws-unrequested.json",
        '{ "exemptions": { "UNRELATED": { "kind": "no-github-twin", "reason": "x" } } }',
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, "ORPHAN_TOKEN", "assertion 5 names the unexempted mapped name")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 5: a mapped name nobody requests and nobody exempts fails")


def test_a_fan_in_the_map_lacks_reds_and_a_missing_fan_in_refuses(gate, tmp_path):
    """Assertion 7, both directions, through the whole gate: a SUFFIXED_PREFIXES entry whose built name is unmapped is named, and a deploy tree with no fan-in at all refuses rather than passing over nothing."""
    fixture(gate, tmp_path)
    write(
        tmp_path / ".ci/rediacc_ci/deploy/build.py", 'SUFFIXED_PREFIXES = ("PREFIX", "UNMAPPED")\n'
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, "UNMAPPED_EU", "assertion 7 names the built name the map lacks")
    gate.assert_contains(out, "rc=1", "and fails")
    (tmp_path / ".ci/rediacc_ci/deploy/build.py").unlink()
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, "the runtime-name scan lost its subject", "an empty fan-in refuses")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 7: an unmapped fan-in reds, and no fan-in at all refuses")


def test_twin_appearing_kills_the_exemption(gate, tmp_path):
    fixture(gate, tmp_path)
    path = tmp_path / ".ci/config/secret-reachability.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repos"]["console"]["ORPHAN_TOKEN"] = {"reachable": True, "via": "org:all"}
    path.write_text(json.dumps(data), encoding="utf-8")
    out = run_gate(gate, tmp_path)
    gate.assert_contains(
        out, "IS a console-reachable org secret", "the re-derivation notices the twin appeared"
    )
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("no-github-twin is RE-DERIVED: creating the org secret ends the exemption")


def test_a_non_literal_rename_table_refuses_with_a_message(gate, tmp_path):
    """RENAMES is read with ast.literal_eval; an element that is not a literal must end the gate with one line, not a traceback (881f37e4.1)."""
    fixture(gate, tmp_path)
    write(
        tmp_path / "scripts/ops/secret-rename.py",
        'RENAMES: list[tuple[str, str]] = [\n    ("OLD_" + "ALPHA", "ALPHA_TOKEN"),\n]\n',
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(
        out, "RENAMES must hold only literal strings", "the message names the table"
    )
    gate.assert_contains(out, "rc=1", "and fails")
    gate.assert_not_contains(out, "Traceback", "without a traceback")
    gate.log_pass("a non-literal RENAMES element is refused in one line")


def test_an_unhashable_rename_element_refuses_with_a_message(gate, tmp_path):
    """Review e7aa60fa.3: `{[1]: 2}` makes literal_eval raise TypeError, which escaped the ValueError handler as a traceback."""
    fixture(gate, tmp_path)
    write(
        tmp_path / "scripts/ops/secret-rename.py",
        'RENAMES: list[tuple[str, str]] = [\n    ({[1]: 2}, "ALPHA_TOKEN"),\n]\n',
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(
        out, "RENAMES must hold only literal strings", "the message names the table"
    )
    gate.assert_contains(out, "rc=1", "and fails")
    gate.assert_not_contains(out, "Traceback", "without a traceback")
    gate.log_pass("an unhashable RENAMES element is refused in one line")


def test_seller_field_dropped_from_profile_reds(gate, tmp_path):
    fixture(gate, tmp_path)
    dropped = SELLER_FIELDS[-1]
    write(
        tmp_path / ".ci/config/secret-supply.json",
        json.dumps(supply([f for f in SELLER_FIELDS if f != dropped])),
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, dropped, "assertion 14 names the SELLER field the profile lost")
    gate.assert_contains(out, "partial record", "and says why it matters")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 14: a profile missing one declared SELLER field fails")


def test_seller_fields_agree_on_the_real_tree(gate):
    """The live `account-dev` profile binds exactly the fields `bws_env` declares. The fixture cases prove the comparison can fail; this proves the committed tree is on the passing side of it."""
    python3 = harness.require_tool("python3", "install python3; the subject is a python3 program")
    probe = (
        "import sys; sys.path.insert(0, %r); import check_bws_map as g; "
        "p, n = g.seller_field_problems(); print('\\n'.join(p)); print('fields=%%d' %% n); "
        "sys.exit(1 if p else 0)" % str(GATE.parent)
    )
    result = harness.run([python3, "-c", probe])
    gate.assert_exit(
        0, result, "the real account-dev profile must bind every declared SELLER field"
    )
    gate.assert_contains(
        result.combined, "fields=%d" % len(SELLER_FIELDS), "and compare a non-empty set"
    )
    gate.log_pass("assertion 14: the real tree's SELLER fields agree with bws_env")


def test_a_mapped_parked_name_reds(gate, tmp_path):
    """Assertion 16 through the whole gate: a planted mapped `__X` is named and fails. The clean fixture (test_clean_fixture_passes) is the control."""
    fixture(gate, tmp_path)
    path = tmp_path / ".ci/config/bws-secret-map.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["secrets"]["__ALPHA_TOKEN_DEV"] = {"id": "aaaaaaaa-0000-4000-8000-000000000009"}
    path.write_text(json.dumps(data), encoding="utf-8")
    exempt = tmp_path / ".ci/config/bws-unrequested.json"
    ex = json.loads(exempt.read_text(encoding="utf-8"))
    ex["exemptions"]["__ALPHA_TOKEN_DEV"] = {"kind": "no-github-twin", "reason": "fixture"}
    exempt.write_text(json.dumps(ex), encoding="utf-8")
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, "'__ALPHA_TOKEN_DEV' is a parked entry", "assertion 16 names it")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 16: a mapped parked name fails")


def test_a_profile_bound_parked_name_reds(gate, tmp_path):
    fixture(gate, tmp_path)
    doc = supply(SELLER_FIELDS)
    doc["consumers"]["account-dev"]["required"].append("__ALPHA_TOKEN_DEV > ALPHA_TOKEN")
    write(tmp_path / ".ci/config/secret-supply.json", json.dumps(doc))
    out = run_gate(gate, tmp_path)
    gate.assert_contains(
        out, "consumers.account-dev binds '__ALPHA_TOKEN_DEV'", "assertion 16 names where"
    )
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 16: a profile binding a parked name fails")


def test_a_drifted_parked_pin_reds(gate, tmp_path):
    fixture(gate, tmp_path)
    write(
        tmp_path / "scripts/ops/bws-map-refresh.py",
        'import re\n\nARCHIVE_RE = re.compile(r"%s")\nPARKED_RE = re.compile(r"^__")\n'
        % ARCHIVE_PATTERN,
    )
    out = run_gate(gate, tmp_path)
    gate.assert_contains(out, "its PARKED_RE has drifted", "assertion 16 names the drifted pin")
    gate.assert_contains(out, "rc=1", "and fails")
    gate.log_pass("assertion 16: a refresher whose PARKED_RE drifted fails")


def test_empty_tree_is_not_a_pass(gate, tmp_path):
    (tmp_path / "empty").mkdir(parents=True, exist_ok=True)
    out = run_gate(gate, tmp_path / "empty")
    gate.assert_contains(out, "rc=1", "an empty tree must fail, or BWS_MAP_ROOT is an escape hatch")
    gate.log_pass("the fixture override cannot be used to pass vacuously")


def test_the_instrument_runs_before_any_verdict(gate):
    """PORT-ONLY. Every case above reads a VERDICT out of the gate, and a verdict is worth nothing if the instrument that produced it was never proven.

    `check_bws_map.py` runs its own `selftest()` ahead of every judgement (its `main` calls it and refuses when it fails), so this drives that path directly and requires it green. A gate whose pure logic is broken must never reach the tree at all, and this is the case that says so out loud rather than trusting the ordering to stay put.
    """
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    result = harness.run(
        [
            harness.require_tool("python3", "install python3; the subject is a python3 program"),
            str(GATE),
            "--selftest",
        ]
    )
    gate.assert_exit(0, result, "the gate's own selftest must pass")
    gate.log_pass("the gate's selftest is green, so its verdicts above were instrumented")


def test_the_refresher_drops_parked_names_and_leaves_archives_to_their_own_split():
    """bws-map-refresh's exclusion, driven directly: a `__NAME` entry is dropped and reported; a live name and an archive clone are not parked (the archive split runs first and owns clones)."""
    src = paths.from_root("scripts", "ops", "bws-map-refresh.py")
    spec = importlib.util.spec_from_file_location("bws_map_refresh", src)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = [
        {"key": "ALPHA", "id": "1", "projectId": "p"},
        {"key": "__ALPHA_DEV", "id": "2", "projectId": "p"},
        {"key": "__ALPHA__ROTATED_20260101T000000Z", "id": "3", "projectId": "p"},
    ]
    kept, parked = module.split_parked(entries)
    assert parked == ["__ALPHA_DEV"]
    assert [e["key"] for e in kept] == ["ALPHA", "__ALPHA__ROTATED_20260101T000000Z"]
    assert module.PARKED_RE.pattern == PARKED_PATTERN
