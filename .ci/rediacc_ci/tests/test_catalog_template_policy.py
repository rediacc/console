"""Every catalog template must deploy under renet's Docker API privilege gate.

renet's dockerpolicy (private/renet/pkg/dockerpolicy, PLAN-dockerd-api-privilege-gate) hard-denies, in both the compose validator and the per-repo Docker API proxy and even with --unsafe: binds of `/`, `/proc`, `/sys`, `/dev` (except /dev/net/tun), the host runtime tree (`/run`, `/var/run`), the protected `/etc` trees, `/root`, the renet and docker state trees and the datastore; and `privileged`, `pid: host`, `ipc: host`, `uts: host`. A template that asks for any of these fails at deploy time. The catalog lifecycle suite that would deploy it is deliberately not run by CI (.ci/rediacc_ci/catalog/lifecycle.py docstring, packages/e2e-tests/README.md "Deliberately not in CI" item 9), so this static scan is the gate: the prometheus-grafana template's node-exporter shipped `/proc`, `/sys` and `/:/host:ro` binds until 5902719a8.

The scan is line-based on purpose (stdlib only, no YAML dependency): the short-form `- source:target[:mode]` volume entry and the `key: value` service options are what these compose files use. A long-form `type: bind` / `source:` mount is checked by its `source:` line.
"""

from __future__ import annotations

import pathlib
import re

from rediacc_ci import paths

TEMPLATES = paths.repo_root() / "packages" / "json" / "templates"

# Absolute host paths the gate refuses outright, with every descendant.
HARD_TREES = (
    "/proc",
    "/sys",
    "/run",
    "/var/run",
    "/etc/rediacc",
    "/etc/docker",
    "/etc/containerd",
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/ssh",
    "/root",
    "/var/lib/rediacc",
    "/var/lib/docker",
    "/var/lib/containerd",
    "/mnt/rediacc",
)
DEV_ALLOWED = ("/dev/net/tun",)
HARD_OPTIONS = {
    "privileged": ("true", "yes"),
    "pid": ("host",),
    "ipc": ("host",),
    "uts": ("host",),
}

_VOLUME_ITEM = re.compile(r"""^\s*-\s*["']?(/[^:"'\s]*)(?::|["']?\s*$)""")
_SOURCE_LINE = re.compile(r"""^\s*source:\s*["']?(/[^"'\s]*)""")
_OPTION_LINE = re.compile(r"""^\s*(privileged|pid|ipc|uts):\s*["']?([A-Za-z]+)""")


def _under(path: str, tree: str) -> bool:
    return path == tree or path.startswith(tree.rstrip("/") + "/")


def refusals(text: str) -> list[str]:
    """Every line of a compose file the privilege gate would hard-deny, as `line N: reason`."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = _VOLUME_ITEM.match(line) or _SOURCE_LINE.match(line)
        if m:
            src = m.group(1).rstrip("/") or "/"
            if src == "/":
                out.append("line %d: binds the host root" % n)
            elif _under(src, "/dev") and not any(_under(src, d) for d in DEV_ALLOWED):
                out.append("line %d: binds %s (only /dev/net/tun is allowed)" % (n, src))
            else:
                for tree in HARD_TREES:
                    if _under(src, tree) or _under(tree, src):
                        out.append("line %d: binds %s, which reaches %s" % (n, src, tree))
                        break
        o = _OPTION_LINE.match(line)
        if o and o.group(2).lower() in HARD_OPTIONS[o.group(1)]:
            out.append("line %d: %s: %s" % (n, o.group(1), o.group(2)))
    return out


def test_every_catalog_template_passes_the_privilege_gate() -> None:
    files = sorted(TEMPLATES.rglob("docker-compose.y*ml"))
    assert len(files) >= 20, "found only %d template compose files under %s" % (
        len(files),
        TEMPLATES,
    )
    bad = {
        str(f.relative_to(paths.repo_root())): r
        for f in files
        if (r := refusals(f.read_text(encoding="utf-8")))
    }
    assert not bad, "templates the privilege gate refuses:\n" + "\n".join(
        "  %s: %s" % (k, "; ".join(v)) for k, v in bad.items()
    )


def test_the_scan_catches_each_refused_shape() -> None:
    """Planted controls: each shape the gate refuses is reported, and the allowed ones are not."""
    planted = """
services:
  a:
    privileged: true
    pid: host
    volumes:
      - /proc:/host/proc:ro
      - "/sys:/host/sys:ro"
      - /:/host:ro
      - /var/run/docker.sock:/var/run/docker.sock
      - /etc:/hostetc:ro
      - /dev/sda:/dev/sda
    # privileged: true  (a comment is ignored)
  b:
    volumes:
      - ./data:/data
      - named:/var/lib/x
      - /dev/net/tun:/dev/net/tun
      - ${DOCKER_SOCKET}:/var/run/docker.sock
"""
    got = refusals(planted)
    assert len(got) == 8, got
    for needle in (
        "privileged",
        "pid: host",
        "/proc",
        "/sys",
        "host root",
        "/var/run",
        "/etc",
        "/dev/sda",
    ):
        assert any(needle in r for r in got), (needle, got)


def test_node_exporter_shape_from_before_5902719a8_is_refused() -> None:
    """The exact binds the prometheus-grafana node-exporter carried before the fix."""
    pre_fix = """
  node-exporter:
    image: prom/node-exporter:latest
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
"""
    assert len(refusals(pre_fix)) == 3


def test_templates_dir_exists() -> None:
    assert pathlib.Path(TEMPLATES).is_dir()
