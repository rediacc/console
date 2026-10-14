"""Every freshness gate's failure names the one `npm run pins -- ...` command that fixes it (agent/plans/PLAN-pins-command.md Design 4, box T9).

The line is built in one place per language, `scripts/lib/pins/remedy.ts` and `rediacc_ci.core.pins` (`bump_remedy`, `lockfiles_remedy`), and each case here drives one gate RED through its own fixture seam, never the network and never a write to this tree, then finds its exact line:

  check:actions                     ACTIONS_API_BASE stub, actions/checkout one release ahead     bump actions
  check:ci-embed-asset-freshness    EMBED_FRESHNESS_FIXTURE, k3s ahead                           bump embed:k3s
  check:ci-devcontainer-pins        DEVCONTAINER_FRESHNESS_FIXTURE, bw ahead                     bump devcontainer:bw
  check:ci-real-provider-pins       REAL_PROVIDER_FRESHNESS_FIXTURE, the extension ahead         bump real-provider:bitwarden
  check:ci-ceph-image-pin           CEPH_IMAGE_PIN_ROOT, a copy of the pin with review= past      bump ceph-image
  check:ci-go-deps                  REDIACC_CI_ROOT plus a GOPROXY stub, a minor ahead           bump go-mod
  check:ci-lockfile                 REDIACC_CI_ROOT plus an `npx` stub that rewrites the lock    lockfiles <dir>
  renet_pkg_matrix OBS REBUILT      check_upstream with an upstream that moved                   bump os:opensuse-16.0-ceph
  check:ci-docker-image-freshness   DOCKER_FRESHNESS_ROOT and a DOCKER_HUB_API_BASE stub         the no-leaf line (below)

EACH CASE HAS ITS CONTROL: the same seam with nothing stale is green and prints no fix line, so a gate that printed the line unconditionally, or a case that asserted against the wrong stream, fails here.

A GATE THAT STOPS PRINTING ITS LINE IS RED HERE, which is the box's acceptance: each line is asserted with its leading indent and trailing newline, so a reworded or dropped line does not match.

THE DOCKER GATE IS THE ONE WITHOUT AN EXACT ID TODAY. Its FROM lines under packages/, workers/ and the submodules are members of the `docker` family scope, and no `docker` leaf claims them, so `npm run pins` has nothing to move; the gate says exactly that rather than naming a command that would refuse. The case pins that line, so the day a leaf claims a scanned Dockerfile the gate's exact `bump <id> --major` line takes its place through the same helper.

check:deps is not here: its failure line belongs to the npm driver (box T6), which owns scripts/gates/check-deps.ts.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import allowlist, pins
from rediacc_ci.infra import renet_pkg_matrix
from rediacc_ci.quality import lockfile
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.test_gate_go_deps_upstream import OSV_ROUTE, proxy_script
from rediacc_ci.tests.gates.test_gate_go_deps_upstream import run_gate as run_go_deps
from rediacc_ci.tests.gates.test_gate_real_provider_pin_freshness import (
    BITWARDEN,
    current_listing,
    release,
)
from rediacc_ci.tests.gates.test_gate_real_provider_pin_freshness import (
    run_gate as run_real_provider,
)
from rediacc_ci.tests.gates.upstream_stub import ok, stub_upstream

if TYPE_CHECKING:
    import pathlib

LONG_AGO = "2020-01-01T00:00:00Z"
REGISTRY = paths.from_root(".ci", "config", "pins.json")
GATES = paths.from_root("scripts", "gates")


def line(cmd: str) -> str:
    """The exact line a gate prints: two spaces, `fix:`, the command, and the line's end."""
    return "  fix: npm run pins -- %s\n" % cmd


def tsx(gate, script: str, env: dict[str, str]) -> harness.RunResult:
    subject = GATES / script
    if not subject.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    npx = harness.require_tool("npx", "install node; the gates are TypeScript driven through tsx")
    return harness.run([npx, "tsx", str(subject)], cwd=paths.repo_root(), env=env)


def entries() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["entries"]


def require(gate, path: pathlib.Path, why: str) -> None:
    if not path.is_file():
        gate.log_fail("%s is absent, so this case cannot run: %s" % (path, why))


# ---- the helper itself ------------------------------------------------------------------


def test_the_python_helper_builds_the_line_and_refuses_an_unknown_id(gate):
    gate.assert_eq(pins.bump_remedy("go-mod"), line("bump go-mod").rstrip("\n"), "the bump line")
    gate.assert_eq(
        pins.bump_remedy("embed:k3s", major=True),
        '  fix: npm run pins -- bump embed:k3s --major --reason "<why>"',
        "the major form",
    )
    gate.assert_eq(pins.lockfiles_remedy(""), line("lockfiles .").rstrip("\n"), "root is `.`")
    try:
        pins.bump_remedy("embed:nope")
    except pins.PinsError as exc:
        gate.assert_contains(str(exc), "embed:nope", "the refusal names the id")
    else:
        gate.log_fail("a remedy for an id the registry does not hold was built")
    gate.log_pass("the Python helper builds the line and refuses an unknown id")


def test_the_two_helpers_build_the_same_bytes(gate):
    """The TypeScript and Python helpers are one line spelled twice; drive both and compare."""
    npx = harness.require_tool("npx", "install node; the helper is TypeScript")
    probe = (
        "import { bumpRemedy } from './scripts/lib/pins/remedy.ts';\n"
        "let refused = '';\n"
        "try { bumpRemedy('embed:nope'); } catch (e) { refused = String(e); }\n"
        "process.stdout.write(JSON.stringify({ a: bumpRemedy('go-mod'),"
        " b: bumpRemedy('embed:k3s', { major: true }), refused }));"
    )
    result = harness.run([npx, "tsx", "--eval", probe], cwd=paths.repo_root())
    gate.assert_exit(0, result, "the TypeScript helper ran")
    got = json.loads(result.out.strip().splitlines()[-1])
    gate.assert_eq(got["a"], pins.bump_remedy("go-mod"), "the same bump line")
    gate.assert_eq(got["b"], pins.bump_remedy("embed:k3s", major=True), "the same major line")
    gate.assert_contains(got["refused"], "embed:nope", "the TypeScript side refuses it too")
    gate.log_pass("both helpers build the same bytes")


def test_the_blocklist_rejection_names_the_npm_bump(gate):
    """The deps blocklist's deferral rejection tells the author to TAKE the bump; that command is the pins one, held equal to the helper's here because allowlist.py may not read the registry."""
    gate.assert_eq(allowlist.DEPS_BUMP, pins.bump_command("npm"), "one spelling of the npm bump")
    rejection = allowlist.validate_reason(
        "pkg", "routine bump deferred to a dedicated dependency-bump PR", ".deps-upgrade-blocklist"
    )
    if rejection is None:
        gate.log_fail("a routine deferral was accepted as a BLOCKER reason")
        return
    gate.assert_eq(rejection.kind, "deferral", "a deferral is rejected")
    gate.assert_contains(
        rejection.message, "TAKE the bump ('npm run pins -- bump npm')", "and names the bump"
    )
    gate.assert_not_contains(rejection.message, "--upgrade", "not the deleted flag")
    gate.log_pass("the deps blocklist rejection names `npm run pins -- bump npm`")


# ---- check:actions ----------------------------------------------------------------------

OLD = {
    "tag_name": "v0.0.1",
    "html_url": "https://github.invalid/r",
    "target_commitish": "main",
    "published_at": LONG_AGO,
}
NEWER = dict(OLD, tag_name="v9999.0.0")
CHECKOUT = "/repos/actions/checkout/releases/latest"


def test_actions(gate):
    with stub_upstream({}, default=[ok(OLD)]) as stub:
        green = tsx(gate, "check-actions.ts", {"ACTIONS_API_BASE": stub.base})
    gate.assert_exit(0, green, "CONTROL: every action current")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    with stub_upstream({CHECKOUT: [ok(NEWER)]}, default=[ok(OLD)]) as stub:
        red = tsx(gate, "check-actions.ts", {"ACTIONS_API_BASE": stub.base})
    gate.assert_exit(1, red, "actions/checkout one release behind is red")
    gate.assert_contains(red.out, line("bump actions"), "the fix is the pins bump")
    gate.assert_not_contains(red.out, "xargs sed", "the sed recipe is gone")
    gate.log_pass("check:actions names `npm run pins -- bump actions`")


# ---- check:ci-embed-asset-freshness ----------------------------------------------------


def embed_map(**ahead: str) -> dict:
    data = {
        e["id"].split(":", 1)[1]: {"version": "0.0.1"}
        for e in entries()
        if e["driver"] == "embed" and e["kind"] == "leaf"
    }
    for base, version in ahead.items():
        data[base] = {"version": version, "publishedAt": LONG_AGO}
    return data


def run_embed(gate, tmp: pathlib.Path, mapping: dict) -> harness.RunResult:
    require(gate, paths.from_root("private", "renet", "Dockerfile"), "renet's Dockerfile pins")
    (tmp / "embed.json").write_text(json.dumps(mapping), encoding="utf-8")
    (tmp / "embed-holds").write_text("# no holds\n", encoding="utf-8")
    return tsx(
        gate,
        "check-embed-asset-freshness.ts",
        {
            "EMBED_FRESHNESS_FIXTURE": str(tmp / "embed.json"),
            "EMBED_BLOCKLIST_FILE": str(tmp / "embed-holds"),
        },
    )


def test_embed_asset_freshness(gate, tmp_path):
    green = run_embed(gate, tmp_path, embed_map())
    gate.assert_exit(0, green, "CONTROL: every embed pin current")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    red = run_embed(gate, tmp_path, embed_map(k3s="9999.0.0"))
    gate.assert_exit(1, red, "k3s behind is red")
    gate.assert_contains(red.err, line("bump embed:k3s"), "the fix names the exact id")
    gate.assert_not_contains(red.combined, "--upgrade", "the retired --upgrade is not offered")
    gate.log_pass("check:ci-embed-asset-freshness names `npm run pins -- bump embed:k3s`")


# ---- check:ci-devcontainer-pins --------------------------------------------------------


def devcontainer_map(**ahead: str) -> dict:
    data = {}
    for e in entries():
        if "check:ci-devcontainer-pins" not in e["gates"]:
            continue
        arg = next(s["arg"] for s in e["sites"] if s["role"] == "version" and s.get("arg"))
        data[arg.removesuffix("_VERSION").lower()] = {"version": "0.0.1"}
    for base, version in ahead.items():
        data[base] = {"version": version, "publishedAt": LONG_AGO}
    return data


def run_devcontainer(gate, tmp: pathlib.Path, mapping: dict) -> harness.RunResult:
    (tmp / "dc.json").write_text(json.dumps(mapping), encoding="utf-8")
    (tmp / "dc-holds").write_text("# no holds\n", encoding="utf-8")
    shutil.copyfile(paths.from_root(".devcontainer", "Dockerfile"), tmp / "Dockerfile")
    return tsx(
        gate,
        "check-devcontainer-pin-freshness.ts",
        {
            "DEVCONTAINER_FRESHNESS_FIXTURE": str(tmp / "dc.json"),
            "DEVCONTAINER_BLOCKLIST_FILE": str(tmp / "dc-holds"),
            "DEVCONTAINER_DOCKERFILE": str(tmp / "Dockerfile"),
        },
    )


def test_devcontainer_pins(gate, tmp_path):
    green = run_devcontainer(gate, tmp_path, devcontainer_map())
    gate.assert_exit(0, green, "CONTROL: every devcontainer pin current")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    red = run_devcontainer(gate, tmp_path, devcontainer_map(bw="9999.1.0"))
    gate.assert_exit(1, red, "bw behind is red")
    gate.assert_contains(red.err, line("bump devcontainer:bw"), "the fix names the exact id")
    gate.assert_not_contains(red.combined, "--upgrade", "the retired --upgrade is not offered")
    gate.log_pass("check:ci-devcontainer-pins names `npm run pins -- bump devcontainer:bw`")


# ---- check:ci-real-provider-pins -------------------------------------------------------


def test_real_provider_pins(gate, tmp_path):
    green = run_real_provider(gate, tmp_path, current_listing())
    gate.assert_exit(0, green, "CONTROL: both pins current")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    listing = current_listing()
    listing[BITWARDEN].insert(0, release("browser-v2026.10.0"))
    red = run_real_provider(gate, tmp_path, listing)
    gate.assert_exit(1, red, "the extension behind is red")
    gate.assert_contains(
        red.err, line("bump real-provider:bitwarden"), "the fix names the exact id"
    )
    gate.log_pass(
        "check:ci-real-provider-pins names `npm run pins -- bump real-provider:bitwarden`"
    )


# ---- check:ci-ceph-image-pin -----------------------------------------------------------

CEPH_FILES = (
    ("private", "renet", ".ceph-image-pin"),
    ("private", "renet", "pkg", "infra", "ceph", "provisioner.go"),
    ("private", "renet", "pkg", "infra", "cephpkg", "cephpkg.go"),
)


def ceph_tree(gate, tmp: pathlib.Path, review: str | None) -> pathlib.Path:
    root = tmp / ("ceph-" + (review or "as-is"))
    for parts in CEPH_FILES:
        src = paths.from_root(*parts)
        require(gate, src, "the Ceph pin files live in the renet submodule")
        dst = root.joinpath(*parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    if review is not None:
        pin = root.joinpath(*CEPH_FILES[0])
        text, n = re.subn(r"(?m)^review=.*$", "review=%s" % review, pin.read_text("utf-8"))
        if n != 1:
            gate.log_fail("the pin file has %d review= lines, so the plant did not land" % n)
        pin.write_text(text, encoding="utf-8")
    return root


def test_ceph_image_pin(gate, tmp_path):
    green = tsx(
        gate,
        "check-ceph-image-pin.ts",
        {"CEPH_IMAGE_PIN_ROOT": str(ceph_tree(gate, tmp_path, None))},
    )
    gate.assert_exit(0, green, "CONTROL: the copied pin, as committed, is green")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    red = tsx(
        gate,
        "check-ceph-image-pin.ts",
        {"CEPH_IMAGE_PIN_ROOT": str(ceph_tree(gate, tmp_path, "2020-01-01"))},
    )
    gate.assert_exit(1, red, "a review date in the past is red")
    gate.assert_contains(red.err, "OVERDUE for review", "the finding is the overdue review")
    gate.assert_contains(red.err, line("bump ceph-image"), "the fix names the exact id")
    gate.log_pass("check:ci-ceph-image-pin names `npm run pins -- bump ceph-image`")


# ---- check:ci-go-deps ------------------------------------------------------------------


def test_go_deps(gate, tmp_path):
    with stub_upstream(proxy_script("v1.0.0")) as stub:
        green = run_go_deps(gate, tmp_path / "green", stub.base, stub.base)
    gate.assert_exit(0, green, "CONTROL: a current module is green")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    script = proxy_script("v1.0.0", "v1.1.0")
    script[OSV_ROUTE] = [ok({})]
    with stub_upstream(script) as stub:
        red = run_go_deps(gate, tmp_path / "red", stub.base, stub.base)
    gate.assert_exit(1, red, "a minor behind is red")
    gate.assert_contains(red.out, line("bump go-mod"), "the fix is the go-mod bump")
    gate.log_pass("check:ci-go-deps names `npm run pins -- bump go-mod`")


# ---- check:ci-lockfile -----------------------------------------------------------------

NPX_STUB = """#!/bin/bash
case "$*" in
  *--package-lock-only*) %s exit 0 ;;
esac
exit 0
"""


def run_lockfile(gate, tmp: pathlib.Path, rewrites: bool) -> harness.RunResult:
    root = tmp / ("lock-red" if rewrites else "lock-green")
    lockfile.scaffold(root)
    for rel in ("", "sub/"):
        (root / (rel + "package.json")).parent.mkdir(parents=True, exist_ok=True)
        (root / (rel + "package.json")).write_text("{}", encoding="utf-8")
        (root / (rel + "package-lock.json")).write_text("{}", encoding="utf-8")
    shim = tmp / ("shim-red" if rewrites else "shim-green")
    shim.mkdir()
    npx = shim / "npx"
    npx.write_text(NPX_STUB % ("echo drift >> package-lock.json;" if rewrites else ""), "utf-8")
    npx.chmod(0o755)
    entry = paths.from_root(".ci", "scripts", "quality", "check_lockfile.py")
    require(gate, entry, "the gate's entry point")
    return harness.run(
        [str(entry)],
        cwd=paths.repo_root(),
        env={
            paths.ROOT_ENV: str(root),
            "PATH": "%s:%s" % (shim, os.environ.get("PATH", "")),
        },
    )


def test_lockfile(gate, tmp_path):
    green = run_lockfile(gate, tmp_path, rewrites=False)
    gate.assert_exit(0, green, "CONTROL: lockfiles the pinned npm leaves alone are green")
    gate.assert_not_contains(green.combined, "fix: npm run pins", "no fix line when green")
    red = run_lockfile(gate, tmp_path, rewrites=True)
    gate.assert_exit(1, red, "a lockfile the pinned npm would rewrite is red")
    gate.assert_contains(red.out, line("lockfiles ."), "the root lockfile's fix")
    gate.assert_contains(red.out, line("lockfiles sub"), "the nested lockfile's fix")
    gate.assert_not_contains(red.out, "install --package-lock-only", "the hand recipe is gone")
    gate.log_pass("check:ci-lockfile names `npm run pins -- lockfiles <dir>` per lockfile")


# ---- renet_pkg_matrix OBS REBUILT ------------------------------------------------------


def test_obs_rebuilt(gate):
    pin = "19.2.3-lp160.2.98"
    green = renet_pkg_matrix.check_upstream(pin, "schedule", lambda: pin)
    gate.assert_eq(green.ok, True, "CONTROL: OBS serving the pin is green")
    gate.assert_not_contains(green.detail, "fix: npm run pins", "no fix line when green")
    red = renet_pkg_matrix.check_upstream(pin, "schedule", lambda: "19.2.3-lp160.2.99")
    gate.assert_eq(red.ok, False, "OBS serving another build is red on the nightly")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        renet_pkg_matrix.report("opensuse-16.0", [red])
    gate.assert_contains(
        out.getvalue(), line("bump os:opensuse-16.0-ceph"), "the fix prints as its own line"
    )
    gate.log_pass("OBS REBUILT names `npm run pins -- bump os:opensuse-16.0-ceph`")


# ---- check:ci-docker-image-freshness ---------------------------------------------------

NO_LEAF = (
    "  fix: none yet; no docker leaf of .ci/config/pins.json claims tools/Dockerfile, so "
    "`npm run pins` cannot move node:20-slim. Add the leaf (driver docker, a site on this FROM "
    'line), then run `npm run pins -- bump <its id> --major --reason "<why>"`.\n'
)


def docker_tree(tmp: pathlib.Path) -> pathlib.Path:
    root = tmp / "docker"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "Dockerfile").write_text("FROM node:20-slim\n", encoding="utf-8")
    (root / "scripts" / "data").mkdir(parents=True)
    (root / "scripts" / "data" / "docker-image-freshness-baseline.json").write_text(
        "[]\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def hub(*tags: str) -> list[tuple]:
    return [ok({"results": [{"name": t, "last_updated": LONG_AGO} for t in tags]})]


def test_docker_image_freshness(gate, tmp_path):
    root = docker_tree(tmp_path)
    env = {"DOCKER_FRESHNESS_ROOT": str(root)}
    with stub_upstream({}, default=hub("20-slim", "18-slim")) as stub:
        green = tsx(
            gate, "check-docker-image-freshness.ts", {**env, "DOCKER_HUB_API_BASE": stub.base}
        )
    gate.assert_exit(0, green, "CONTROL: nothing newer of the same shape is green")
    gate.assert_contains(green.out, "1 Docker Hub pin(s) checked", "the planted pin was compared")
    gate.assert_not_contains(green.combined, "fix:", "no fix line when green")
    with stub_upstream({}, default=hub("22-slim", "20-slim")) as stub:
        red = tsx(
            gate, "check-docker-image-freshness.ts", {**env, "DOCKER_HUB_API_BASE": stub.base}
        )
    gate.assert_exit(1, red, "a newer series of the same shape is red")
    gate.assert_contains(red.err, "newly stale", "the finding is a new staleness")
    gate.assert_contains(
        red.err, NO_LEAF, "the fix line says no leaf can move it, and how to add one"
    )
    gate.log_pass("check:ci-docker-image-freshness names the pins path for a pin no leaf claims")
