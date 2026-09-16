"""Port of `.ci/scripts/test/gates/test-embed-asset-freshness.sh`.

Integration test for `scripts/gates/check-embed-asset-freshness.ts`.

Drives the gate through `EMBED_FRESHNESS_FIXTURE` (a JSON map of base -> latest
version/date used instead of the network), so it runs offline and
deterministically. Proves: it passes when nothing is behind, FIRES on a stale pin,
DEFERS a just-released version (the shared soak), and FAILS SOFT when a source
cannot be checked.

THE FIXTURE MAP IS DERIVED FROM THE SUBJECT'S OWN SOURCE LIST, not retyped. The
twin hand-lists seven component keys in four separate heredocs; a component added
upstream leaves all four short, and the gate's "not in fixture" branch quietly
turns the new component into a could-not-check that FAILS SOFT -- so the twin would
keep passing while covering one component less. Here the keys are obtained by
IMPORTING `EMBED_ASSET_SOURCES`, the same module the gate imports, and reading
`.base` off each entry. That is behaviour rather than a regex over the source: a
list that moves to another file, or changes shape, breaks this loudly instead of
matching nothing and quietly producing an empty map.

`test_fixture_keys_are_corpus_derived` is the refusal that keeps that honest: zero
keys read means every case below fed the gate an empty map, which is the
fail-soft path, which is green.

THE SUBMODULE-ABSENT PATH IS A REFUSAL HERE, NOT A SILENT `exit 0`; see the same
paragraph in `test_gate_embed_credits`.
"""

import datetime
import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-embed-asset-freshness.sh"

VALIDATOR = paths.from_root("scripts/gates", "check-embed-asset-freshness.ts")
SOURCES = paths.from_root("scripts", "lib", "embed-asset-sources.ts")
DOCKERFILE = paths.from_root("private", "renet", "Dockerfile")

PROBE = (
    "import { EMBED_ASSET_SOURCES } from './scripts/lib/embed-asset-sources.ts';\n"
    "process.stdout.write(JSON.stringify(EMBED_ASSET_SOURCES.map((s) => s.base)));"
)

# The gate keys its upstream map on the `base` of each source it knows about.
# Importing the list costs one tsx start-up, so it is paid once per pytest process
# rather than once per case. A ONE-SLOT DICT rather than a rebound module global:
# the value is memoised, not reassigned, so no `global` statement is needed.
_BASES: dict[str, list[str]] = {}

SUBMODULE_FIX = (
    "git submodule update --init private/renet; the gate reads the real Dockerfile "
    "pins from there and has nothing to compare against without them"
)


def require_submodule(gate) -> None:
    if not DOCKERFILE.is_file():
        gate.log_fail(
            "%s is absent, so this case could not run at all. Fix: %s"
            % (paths.relative_to_root(DOCKERFILE), SUBMODULE_FIX)
        )


def source_bases(gate) -> list[str]:
    if "value" in _BASES:
        return _BASES["value"]
    for path in (VALIDATOR, SOURCES):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))
    npx = harness.require_tool(
        "npx", "install node; the source list is a TypeScript module read through tsx"
    )
    probe = harness.run(
        [
            npx,
            "tsx",
            "--eval",
            PROBE,
        ],
        cwd=paths.repo_root(),
    )
    found: list[str] = []
    if probe.rc == 0:
        try:
            found = [str(base) for base in json.loads(probe.out.strip().splitlines()[-1])]
        except (ValueError, IndexError):
            found = []
    if not found:
        gate.log_fail(
            "read ZERO source base(s) out of %s (rc=%d, stdout=%r, stderr=%r), so every "
            "fixture below would be an EMPTY map -- which the gate treats as "
            "could-not-check and fails SOFT on. That is a green that proves nothing. "
            "Either the list moved or EMBED_ASSET_SOURCES changed shape."
            % (paths.relative_to_root(SOURCES), probe.rc, probe.out, probe.err)
        )
    _BASES["value"] = found
    return found


def upstream_map(gate, **overrides) -> dict:
    """Every known source reported far OLDER than any real pin, then `overrides`."""
    data = {base: {"version": "0.0.1"} for base in source_bases(gate)}
    data.update(overrides)
    return data


def run_gate(tmp_path, mapping: dict, blocklist: str | None = None) -> harness.RunResult:
    fixture = tmp_path / "upstream.json"
    fixture.write_text(json.dumps(mapping), encoding="utf-8")
    env = {"EMBED_FRESHNESS_FIXTURE": str(fixture)}
    # `None` MEANS AN EMPTY BLOCKLIST, NOT THE REPOSITORY'S. Leaving
    # EMBED_BLOCKLIST_FILE unset let the gate read the live
    # `.ci/policy/.embed-assets-upgrade-blocklist`, and every upstream-map case
    # here plants its staleness on k3s -- so the day k3s was first held
    # (2026-09-16, branch 0914-1) `test_fires_when_stale` stopped being able to
    # fire, and `test_twin_parity` reported the twin passing while this port
    # failed on the same tree.
    #
    # These cases are about the GATE, not about today's policy. The bash twin
    # `test-embed-asset-freshness.sh` carries the same fix and the same reason;
    # they were changed together, because a control isolated on one side of a
    # differential and coupled on the other is exactly how a verdict diverges.
    path = tmp_path / "blocklist"
    path.write_text(
        blocklist
        if blocklist is not None
        else "# no holds; this fixture exists so the cases do not read live policy\n",
        encoding="utf-8",
    )
    env["EMBED_BLOCKLIST_FILE"] = str(path)
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(VALIDATOR)], cwd=paths.repo_root(), env=env)


def test_fixture_keys_are_corpus_derived(gate):
    """PORT-ONLY anti-vacuity: the fixtures below cover every source the gate has."""
    require_submodule(gate)
    bases = source_bases(gate)
    if "k3s" not in bases:
        gate.log_fail(
            "the stale and fresh cases below drive component 'k3s', which the subject no "
            "longer declares. Re-point them at a source that exists; a fixture naming a "
            "component the gate does not check cannot make it fire."
        )
    gate.log_pass(
        "%d upstream source(s) read out of the subject, k3s among them: %s"
        % (len(bases), ", ".join(bases))
    )


def test_passes_when_current(gate, tmp_path):
    require_submodule(gate)
    result = run_gate(tmp_path, upstream_map(gate))
    gate.assert_exit_code(0, result.rc, "nothing behind upstream should pass")
    gate.log_pass("current pins pass")


def test_fires_when_stale(gate, tmp_path):
    require_submodule(gate)
    stale = upstream_map(gate, k3s={"version": "9999.0.0", "publishedAt": "2020-01-01T00:00:00Z"})
    result = run_gate(tmp_path, stale)
    gate.assert_exit_code(1, result.rc, "a pin behind upstream should fail")
    gate.assert_contains(result.combined, "k3s", "error names the stale component")
    gate.assert_contains(result.combined, "--upgrade", "red output gives the --upgrade fix")
    gate.log_pass("stale pin fires")


def test_defers_fresh_release(gate, tmp_path):
    require_submodule(gate)
    recent = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(hours=1)
    fresh = upstream_map(
        gate,
        k3s={"version": "9999.0.0", "publishedAt": recent.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    result = run_gate(tmp_path, fresh)
    gate.assert_exit_code(
        0, result.rc, "a just-released upstream version should be deferred, not failed"
    )
    gate.assert_contains(
        result.combined, "deferred", "fresh release is reported as deferred (soak)"
    )
    gate.log_pass("fresh release is deferred by the soak")


def test_fails_soft_when_uncheckable(gate, tmp_path):
    require_submodule(gate)
    result = run_gate(tmp_path, {})
    gate.assert_exit_code(0, result.rc, "sources that cannot be checked must not fail the build")
    gate.log_pass("uncheckable sources fail soft")


def test_blocklist_rejects_missing_reason(gate, tmp_path):
    """The blocklist is a BLOCKER-gated suppression list; a bare entry with no
    substantive reason must fail the gate, not silently hold the pin.
    """
    require_submodule(gate)
    result = run_gate(tmp_path, upstream_map(gate), blocklist="criu\n")
    gate.assert_exit_code(
        1, result.rc, "a blocklist entry lacking a BLOCKER reason must fail the gate"
    )
    gate.assert_contains(result.combined, "invalid entries", "error names the malformed blocklist")
    gate.log_pass("blocklist entry without a BLOCKER reason fires")


def test_blocklist_accepts_valid_reason(gate, tmp_path):
    """A properly-reasoned blocklist entry is accepted (freshness itself passes here)."""
    require_submodule(gate)
    good = (
        "# BLOCKER: upstream criu 4.3 regressed cgroup-v2 restore; holding at 4.2 until "
        "fixed\ncriu\n"
    )
    result = run_gate(tmp_path, upstream_map(gate), blocklist=good)
    gate.assert_exit_code(
        0, result.rc, "a blocklist entry with a substantive BLOCKER reason must be accepted"
    )
    gate.log_pass("well-formed blocklist entry is accepted")
