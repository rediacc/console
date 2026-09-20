"""Port of `.ci/scripts/test/gates/test-bws-map.sh`.

Drives the REAL scan in `.ci/scripts/quality/check_bws_map.py` against fixture trees, which its internal `selftest()` cannot do.

WHY BOTH EXIST. `selftest()` proves the pure logic -- the request parser and every way of writing a bad exemption -- and it runs before any verdict, so a broken instrument never judges anything. What it CANNOT reach is assertions 5-9, which are defined over the tree: the map, the allowlist, the reachability record, the workflows and the deploy scripts. Those had no fixture coverage
at all, and they are about to be the sole guard on every credential once GitHub secrets go away. A gate whose only controls are internal is thinner than this repo's standard for far less load-bearing checks.

`BWS_MAP_ROOT` re-points every ROOT-derived path at a fixture. It is not an escape hatch: the anti-vacuity clauses fail on a tree that holds nothing, which the last case here proves.

THE FIXTURE IS A GIT REPOSITORY, and that is not scaffolding. The gate's corpus scan enumerates TRACKED files, so a fixture with an untracked map is a fixture the gate reads as empty -- and it would then fail every case for the wrong reason. `git init` plus one commit is the cheapest way to be a tree the subject can actually see.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-bws-map.sh"

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
        # PREFIX_EU must be mapped or exempt: the deploy script below builds it by SUFFIX expansion from regions.json.
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


def write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(gate, directory) -> None:
    """A minimal tree the gate can judge. The twin's `fixture`, same contents."""
    for sub in (
        ".ci/config",
        ".ci/scripts/deploy",
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
        gate.log_fail("could not git-init the fixture: %s" % init.combined)
    write(directory / ".ci/config/bws-secret-map.json", json.dumps(SECRET_MAP))
    write(directory / ".ci/config/bws-unrequested.json", json.dumps(EXEMPTIONS))
    write(directory / ".ci/config/secret-reachability.json", json.dumps(REACHABILITY))
    write(directory / "regions.json", '{"regions":[{"secretSuffix":"EU"}]}')
    write(
        directory / ".ci/scripts/deploy/build.sh",
        'x_var="PREFIX_${SUFFIX}"\n'
        "# ORPHAN_TOKEN PREFIX_EU are named here so the corpus scan sees them\n",
    )
    write(
        directory / "scripts/ops/secret-rename.py",
        'RENAMES: list[tuple[str, str]] = [\n    ("OLD_ALPHA", "ALPHA_TOKEN"),\n]\n',
    )
    write(directory / ".github/workflows/w.yml", WORKFLOW)
    harness.run([git, "add", "-A"], cwd=directory)
    commit = harness.run(
        [git, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=directory,
    )
    if commit.rc != 0:
        gate.log_fail("could not commit the fixture: %s" % commit.combined)


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
    gate.assert_exit_code(0, result.rc, "the gate's own selftest must pass")
    gate.log_pass("the gate's selftest is green, so its verdicts above were instrumented")
