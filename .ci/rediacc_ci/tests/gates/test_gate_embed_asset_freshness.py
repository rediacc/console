"""Port of `.ci/scripts/test/gates/test-embed-asset-freshness.sh`, retired in W7 P5.

Integration test for `scripts/gates/check-embed-asset-freshness.ts`.

Drives the gate through `EMBED_FRESHNESS_FIXTURE` (a JSON map of base -> latest version/date used instead of the network), so it runs offline and deterministically. Proves: it passes when nothing is behind, FIRES on a stale pin, DEFERS a just-released version (the shared soak), and FAILS SOFT when a source cannot be checked.

THE FIXTURE MAP IS DERIVED FROM THE SUBJECT'S OWN SOURCE LIST, not retyped. The twin hand-lists seven component keys in four separate heredocs; a component added upstream leaves all four short, and the gate's "not in fixture" branch quietly turns the new component into a could-not-check that FAILS SOFT -- so the twin would keep passing while covering one component less. Here the
keys are obtained by IMPORTING `EMBED_ASSET_SOURCES`, the same module the gate imports, and reading `.base` off each entry. That is behaviour rather than a regex over the source: a list that moves to another file, or changes shape, breaks this loudly instead of matching nothing and quietly producing an empty map.

`test_fixture_keys_are_corpus_derived` is the refusal that keeps that honest: zero keys read means every case below fed the gate an empty map, which is the fail-soft path, which is green.

THE SUBMODULE-ABSENT PATH IS A REFUSAL HERE, NOT A SILENT `exit 0`; see the same paragraph in `test_gate_embed_credits`.
"""

import datetime
import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

VALIDATOR = paths.from_root("scripts/gates", "check-embed-asset-freshness.ts")
SOURCES = paths.from_root("scripts", "lib", "embed-asset-sources.ts")
DOCKERFILE = paths.from_root("private", "renet", "Dockerfile")

PROBE = (
    "import { EMBED_ASSET_SOURCES } from './scripts/lib/embed-asset-sources.ts';\n"
    "process.stdout.write(JSON.stringify(EMBED_ASSET_SOURCES.map((s) => s.base)));"
)

# The gate keys its upstream map on the `base` of each source it knows about. Importing the list costs one tsx start-up, so it is paid once per pytest process rather than once per case. A ONE-SLOT DICT rather than a rebound module global: the value is memoised, not reassigned, so no `global` statement is needed.
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
    # `None` MEANS AN EMPTY BLOCKLIST, NOT THE REPOSITORY'S. Leaving EMBED_BLOCKLIST_FILE unset let the gate read the live `.ci/policy/.embed-assets-upgrade-blocklist`, and every upstream-map case here plants its staleness on k3s -- so the day k3s was first held (2026-09-16, branch 0914-1) `test_fires_when_stale` stopped being able to fire, and `test_twin_parity` reported the twin
    # passing while this port failed on the same tree.
    #
    # These cases are about the GATE, not about today's policy. The bash twin
    # `test-embed-asset-freshness.sh` carries the same fix and the same reason;
    # they were changed together, because a control isolated on one side of a differential and coupled on the other is exactly how a verdict diverges.
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
    gate.assert_exit(0, result, "nothing behind upstream should pass")
    gate.log_pass("current pins pass")


def test_fires_when_stale(gate, tmp_path):
    require_submodule(gate)
    stale = upstream_map(gate, k3s={"version": "9999.0.0", "publishedAt": "2020-01-01T00:00:00Z"})
    result = run_gate(tmp_path, stale)
    gate.assert_exit(1, result, "a pin behind upstream should fail")
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
    gate.assert_exit(0, result, "a just-released upstream version should be deferred, not failed")
    gate.assert_contains(
        result.combined, "deferred", "fresh release is reported as deferred (soak)"
    )
    gate.log_pass("fresh release is deferred by the soak")


def test_fails_soft_when_uncheckable(gate, tmp_path):
    require_submodule(gate)
    result = run_gate(tmp_path, {})
    gate.assert_exit(0, result, "sources that cannot be checked must not fail the build")
    gate.log_pass("uncheckable sources fail soft")


def test_blocklist_rejects_missing_reason(gate, tmp_path):
    """The blocklist is a BLOCKER-gated suppression list; a bare entry with no substantive reason must fail the gate, not silently hold the pin."""
    require_submodule(gate)
    result = run_gate(tmp_path, upstream_map(gate), blocklist="criu\n")
    gate.assert_exit(1, result, "a blocklist entry lacking a BLOCKER reason must fail the gate")
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
    gate.assert_exit(
        0, result, "a blocklist entry with a substantive BLOCKER reason must be accepted"
    )
    gate.log_pass("well-formed blocklist entry is accepted")


# ---- --upgrade moves every pin tied to a component -----------------------------------
#
# The tool used to rewrite only `ARG <BASE>_VERSION`. csi-provisioner 6.3.0 -> 6.4.0 left `ARG CSIPROVISIONER_COMMIT` at the 6.3.0 commit, so the Dockerfile's own clone check failed the build. These cases drive `--upgrade` against a FIXTURE renet tree (EMBED_RENET_DIR) with pins resolved from a fixture (EMBED_PIN_FIXTURE), never the network and never the real submodule.

OLD_SHA = "34c6fc2149a354cea116724d1836262516f83225"
NEW_SHA = "72f13ee46fb93c11a72ef91549e70158283c03af"
ZOT_OLD = {"amd64": "a" * 64, "arm64": "b" * 64}
ZOT_NEW = {"amd64": "c" * 64, "arm64": "d" * 64}
RSYNC_SHA = "e" * 64
SNAP_SHA = "f" * 40
SNAP_NEW_SHA = "9" * 40
ZOT_SUMS_URL = "https://github.com/project-zot/zot/releases/download/v2.2.0/checksums.sha256.txt"

FIXTURE_DOCKERFILE = f"""FROM golang:1.26 AS csi-builder
ARG CSIPROVISIONER_VERSION=6.3.0
ARG CSIPROVISIONER_COMMIT={OLD_SHA}
RUN [ "$actual" = "${{CSIPROVISIONER_COMMIT}}" ]
FROM ubuntu AS zot-amd64
ARG ZOT_VERSION=2.1.22
ARG ZOT_SHA256_AMD64={ZOT_OLD["amd64"]}
FROM ubuntu AS zot-arm64
ARG ZOT_VERSION=2.1.22
ARG ZOT_SHA256_ARM64={ZOT_OLD["arm64"]}
FROM golang AS snapshotter
ARG CSISNAPSHOTTER_VERSION=8.6.0
ARG SNAPSHOTCONTROLLER_VERSION=8.6.0
ARG CSISNAPSHOTTER_COMMIT={SNAP_SHA}
FROM ubuntu AS rsync
ARG RSYNC_VERSION=3.5.1
ARG RSYNC_SHA256={RSYNC_SHA}
"""

FIXTURE_LOCK = {
    "components": {
        "csiprovisioner": {
            "version": "6.3.0",
            "upstreamSourceUrl": "https://github.com/x/external-provisioner/archive/v6.3.0/external-provisioner-6.3.0.tar.gz",
            "plannedMirrorUrl": "https://releases.example/external-provisioner-6.3.0.tar.gz",
            "source": {"kind": "git", "tag": "v6.3.0", "commit": OLD_SHA},
            "notes": "attribution text naming v6.3.0 stays verbatim",
        },
        "csisnapshotter": {
            "version": "8.6.0",
            "upstreamSourceUrl": "https://github.com/x/external-snapshotter/archive/v8.6.0/s-8.6.0.tar.gz",
            "plannedMirrorUrl": "https://releases.example/s-8.6.0.tar.gz",
            "source": {"kind": "git", "tag": "v8.6.0", "commit": SNAP_SHA},
        },
        "snapshotcontroller": {
            "version": "8.6.0",
            "upstreamSourceUrl": "https://github.com/x/external-snapshotter/archive/v8.6.0/s-8.6.0.tar.gz",
            "plannedMirrorUrl": "https://releases.example/s-8.6.0.tar.gz",
            "source": {"kind": "git", "tag": "v8.6.0", "commit": SNAP_SHA},
        },
        "zot": {
            "version": "2.1.22",
            "upstreamSourceUrl": "https://github.com/project-zot/zot/archive/v2.1.22/zot-2.1.22.tar.gz",
            "plannedMirrorUrl": "https://releases.example/zot-2.1.22.tar.gz",
            "source": {"kind": "release-binary"},
            "arches": {
                arch: {
                    "url": f"https://github.com/project-zot/zot/releases/download/v2.1.22/zot-linux-{arch}",
                    "sha256": digest,
                }
                for arch, digest in ZOT_OLD.items()
            },
        },
        "rsync": {
            "version": "3.5.1",
            "upstreamSourceUrl": "https://example/rsync-3.5.1.tar.gz",
            "plannedMirrorUrl": "https://example/rsync-3.5.1.tar.gz",
            "source": {
                "kind": "tarball",
                "url": "https://example/rsync-3.5.1.tar.gz",
                "sha256": RSYNC_SHA,
            },
        },
    }
}

FIXTURE_UNITS = (
    "const (\n"
    '\tProvisionerVersion        = "v6.3.0"\n'
    '\tSnapshotterVersion        = "v8.6.0"\n'
    '\tSnapshotControllerVersion = "v8.6.0"\n'
    ")\n"
)
FIXTURE_GOLDEN = "[Unit]\nDescription=Rediacc CSI external-provisioner (v6.3.0, node-deployment)\n"
UNITS = "pkg/kube/csidriver/units.go"
GOLDEN = "pkg/kube/csidriver/testdata/rediacc-csi-provisioner.service"


def make_renet(tmp_path):
    renet = tmp_path / "renet"
    (renet / "pkg/kube/csidriver/testdata").mkdir(parents=True)
    (renet / "Dockerfile").write_text(FIXTURE_DOCKERFILE, encoding="utf-8")
    (renet / "embed-assets.lock.json").write_text(
        json.dumps(FIXTURE_LOCK, indent=2) + "\n", encoding="utf-8"
    )
    (renet / UNITS).write_text(FIXTURE_UNITS, encoding="utf-8")
    (renet / GOLDEN).write_text(FIXTURE_GOLDEN, encoding="utf-8")
    return renet


def run_upgrade(gate, tmp_path, renet, **overrides) -> harness.RunResult:
    pins = {
        "commits": {"kubernetes-csi/external-provisioner@v6.4.0": NEW_SHA},
        "texts": {
            ZOT_SUMS_URL: "".join(
                f"{digest}  zot-linux-{arch}\n" for arch, digest in ZOT_NEW.items()
            )
        },
    }
    pins.update(overrides.pop("pins", {}))
    pin_file = tmp_path / "pins.json"
    pin_file.write_text(json.dumps(pins), encoding="utf-8")
    fixture = tmp_path / "upstream.json"
    fixture.write_text(json.dumps(upstream_map(gate, **overrides)), encoding="utf-8")
    blocklist = tmp_path / "blocklist"
    blocklist.write_text("# no holds\n", encoding="utf-8")
    npx = harness.require_tool("npx", "install node; the subject is driven through tsx")
    return harness.run(
        [npx, "tsx", str(VALIDATOR), "--upgrade"],
        cwd=paths.repo_root(),
        env={
            "EMBED_FRESHNESS_FIXTURE": str(fixture),
            "EMBED_PIN_FIXTURE": str(pin_file),
            "EMBED_BLOCKLIST_FILE": str(blocklist),
            "EMBED_RENET_DIR": str(renet),
        },
    )


OLD_CSI = {"version": "6.4.0", "publishedAt": "2020-01-01T00:00:00Z"}


def test_upgrade_moves_the_commit_with_the_version(gate, tmp_path):
    """THE REGRESSION: the version moved and the commit pin stayed, so the Dockerfile could never build."""
    require_submodule(gate)
    renet = make_renet(tmp_path)
    result = run_upgrade(gate, tmp_path, renet, csiprovisioner=OLD_CSI)
    gate.assert_exit(0, result, "a resolvable csi-provisioner bump should succeed")
    dockerfile = (renet / "Dockerfile").read_text(encoding="utf-8")
    gate.assert_contains(dockerfile, "ARG CSIPROVISIONER_VERSION=6.4.0", "version moved")
    gate.assert_contains(dockerfile, "ARG CSIPROVISIONER_COMMIT=" + NEW_SHA, "commit moved with it")
    gate.assert_not_contains(dockerfile, OLD_SHA, "no stale commit left behind")
    gate.log_pass("the COMMIT pin moves with the VERSION pin")


def test_upgrade_moves_lockfile_and_go_constants(gate, tmp_path):
    require_submodule(gate)
    renet = make_renet(tmp_path)
    result = run_upgrade(gate, tmp_path, renet, csiprovisioner=OLD_CSI)
    gate.assert_exit(0, result, "bump should succeed")
    comp = json.loads((renet / "embed-assets.lock.json").read_text(encoding="utf-8"))["components"][
        "csiprovisioner"
    ]
    gate.assert_eq(comp["version"], "6.4.0", "lock version")
    gate.assert_eq(comp["source"]["tag"], "v6.4.0", "lock tag")
    gate.assert_eq(comp["source"]["commit"], NEW_SHA, "lock commit")
    gate.assert_contains(comp["upstreamSourceUrl"], "6.4.0", "lock source URL")
    gate.assert_contains(comp["plannedMirrorUrl"], "6.4.0", "lock mirror URL")
    gate.assert_contains(comp["notes"], "v6.3.0", "free-text attribution is NOT rewritten")
    gate.assert_contains((renet / UNITS).read_text(encoding="utf-8"), '"v6.4.0"', "Go constant")
    gate.assert_contains((renet / GOLDEN).read_text(encoding="utf-8"), "(v6.4.0,", "golden unit")
    gate.log_pass("lockfile entry, Go constant and golden move with the Dockerfile")


def test_upgrade_moves_published_sha256_pins(gate, tmp_path):
    require_submodule(gate)
    renet = make_renet(tmp_path)
    result = run_upgrade(
        gate, tmp_path, renet, zot={"version": "2.2.0", "publishedAt": "2020-01-01T00:00:00Z"}
    )
    gate.assert_exit(0, result, "zot publishes checksums.sha256.txt, so the bump resolves")
    dockerfile = (renet / "Dockerfile").read_text(encoding="utf-8")
    for arch, digest in ZOT_NEW.items():
        gate.assert_contains(
            dockerfile, f"ARG ZOT_SHA256_{arch.upper()}={digest}", f"{arch} digest"
        )
    gate.assert_not_contains(dockerfile, ZOT_OLD["amd64"], "no stale digest left behind")
    lock = json.loads((renet / "embed-assets.lock.json").read_text(encoding="utf-8"))
    gate.assert_eq(
        lock["components"]["zot"]["arches"]["arm64"]["sha256"], ZOT_NEW["arm64"], "lock digest"
    )
    gate.log_pass("SHA256 pins move with the version")


def test_upgrade_refuses_an_unresolvable_commit(gate, tmp_path):
    require_submodule(gate)
    renet = make_renet(tmp_path)
    result = run_upgrade(gate, tmp_path, renet, csiprovisioner=OLD_CSI, pins={"commits": {}})
    gate.assert_exit(1, result, "an unresolvable commit pin must refuse, not half-upgrade")
    gate.assert_contains(result.combined, "REFUSED", "the refusal is named")
    gate.assert_eq(
        (renet / "Dockerfile").read_text(encoding="utf-8"),
        FIXTURE_DOCKERFILE,
        "Dockerfile untouched",
    )
    gate.log_pass("an unresolvable commit pin refuses and leaves the tree alone")


def test_upgrade_refuses_a_pin_with_no_published_checksum(gate, tmp_path):
    """rsync publishes no checksum file; its digest is verified by a GPG signature a human checks."""
    require_submodule(gate)
    renet = make_renet(tmp_path)
    result = run_upgrade(
        gate, tmp_path, renet, rsync={"version": "9.0.0", "publishedAt": "2020-01-01T00:00:00Z"}
    )
    gate.assert_exit(1, result, "an rsync bump cannot resolve its sha256 and must refuse")
    gate.assert_contains(result.combined, "sha256 pin cannot be resolved", "reason names the pin")
    gate.assert_eq(
        (renet / "Dockerfile").read_text(encoding="utf-8"),
        FIXTURE_DOCKERFILE,
        "Dockerfile untouched",
    )
    gate.log_pass("a digest with no published source refuses instead of going stale")


def test_upgrade_refuses_half_of_the_shared_snapshotter_clone(gate, tmp_path):
    """snapshotter and snapshot-controller build from ONE clone guarded by ONE commit ARG. Moving only one of them leaves the clone unbuildable, so the run refuses, writes NOTHING (the resolvable csi-provisioner bump beside it included) and does not report any of it as done."""
    require_submodule(gate)
    renet = make_renet(tmp_path)
    snap = "kubernetes-csi/external-snapshotter@v8.7.0"
    result = run_upgrade(
        gate,
        tmp_path,
        renet,
        csiprovisioner=OLD_CSI,
        csisnapshotter={"version": "8.7.0", "publishedAt": "2020-01-01T00:00:00Z"},
        pins={
            "commits": {
                "kubernetes-csi/external-provisioner@v6.4.0": NEW_SHA,
                snap: SNAP_NEW_SHA,
            }
        },
    )
    gate.assert_exit(1, result, "bumping only one of the shared-clone pair must refuse")
    gate.assert_contains(result.combined, "bump them together", "the pair is named")
    gate.assert_contains(result.combined, "Nothing written", "the discard is stated")
    gate.assert_not_contains(result.combined, "\u2191", "no component is reported as upgraded")
    gate.assert_eq(
        (renet / "Dockerfile").read_text(encoding="utf-8"),
        FIXTURE_DOCKERFILE,
        "Dockerfile untouched",
    )
    gate.assert_eq(
        (renet / UNITS).read_text(encoding="utf-8"), FIXTURE_UNITS, "Go constants untouched"
    )
    lock = json.loads((renet / "embed-assets.lock.json").read_text(encoding="utf-8"))
    gate.assert_eq(lock, FIXTURE_LOCK, "lockfile untouched")
    gate.log_pass("half of the shared clone refuses, writes nothing and reports nothing as done")
