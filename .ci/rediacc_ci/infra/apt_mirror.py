#!/usr/bin/env python3
"""Point a GitHub-hosted runner's apt at the global Ubuntu archive instead of the Azure mirror.

WHY. The hosted ubuntu images pull packages from azure.archive.ubuntu.com, and a runner sometimes stays pinned to a slow node of it that trickles (actions/runner-images#14823, open since 2026-09-30: 74.8 MB fetched at 61.5 kB/s over 20 minutes). apt's `Acquire::http::Timeout` only catches a total stall, so a trickle never fails over and the step runs out its budget. Observed on PR #601: `renet ops host setup` ("Setup KVM Host") stalled 7m30s
in every install attempt (ci-trace category pkg-install-stall) in runs 39766647743 and 39821300649, and the clang install hit a mirror error. From a non-runner host the same mirror is fast, so the fault is runner-side. apt has no minimum-speed option (only `Dl-Limit`, a maximum), so the lever is the mirror: archive.ubuntu.com is the global archive and is not the node that trickles.

WHAT IT TOUCHES. Only a GitHub-hosted runner (`GITHUB_ACTIONS=true` and `RUNNER_ENVIRONMENT=github-hosted`); anywhere else it prints one line and exits 0, so a self-hosted runner or a developer machine is never rewritten. Under `/etc/apt`: `apt-mirrors.txt` (the list behind `mirror+file:` sources), `sources.list`, `sources.list.d/*.sources` and `*.list`. A file that is absent is skipped. Idempotent: a second run finds no
azure host and writes nothing.

The per-attempt stall detection and retries stay where they are, in `renet ops host setup` (private/renet/cmd/renet/ops_host_apt.go); this only changes which host they talk to.
"""

import os
import pathlib
import re
import sys
import urllib.parse

from rediacc_ci import well_known


def _host(url: str) -> str:
    """The hostname of a well_known mirror URL; a constant with no host fails at import rather than rewriting against ''."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise ValueError(f"apt_mirror: no hostname in well_known mirror URL {url!r}")
    return host


AZURE_HOST = _host(well_known.UBUNTU_AZURE_MIRROR)
GLOBAL_HOST = _host(well_known.UBUNTU_ARCHIVE)

# The regional EC2 mirrors (`us-east-2.ec2.archive.ubuntu.com`) are a second stall source: PR #605 run 44442526107 stalled `Setup KVM Host` and `playwright install-deps` on one. They are rewritten to the global archive exactly like the Azure host.
EC2_REGIONAL = re.compile(r"\b[a-z0-9-]+\.ec2\.archive\.ubuntu\.com\b")


def has_stale_host(text: str) -> bool:
    return AZURE_HOST in text or EC2_REGIONAL.search(text) is not None


def swap_host(text: str) -> str:
    return EC2_REGIONAL.sub(GLOBAL_HOST, text.replace(AZURE_HOST, GLOBAL_HOST))


# Files under the apt root that name a mirror.
GLOBS = ("apt-mirrors.txt", "sources.list", "sources.list.d/*.sources", "sources.list.d/*.list")


def hosted_runner(env: dict[str, str]) -> bool:
    return env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted"


def rewrite_text(text: str) -> str:
    """Replace the Azure host and the regional EC2 hosts with the global archive, then drop the duplicate lines the replacement creates in a mirror list.

    A duplicate is only collapsed in a line that is a bare mirror URL (apt-mirrors.txt entries, `http://host/ubuntu/ priority:N`), never in a `deb` or `URIs:` line, where a repeated line would change the file's meaning.
    """
    if not has_stale_host(text):
        return text
    lines = text.splitlines(keepends=True)
    bare = re.compile(r"\s*https?://")
    # Only a line the rewrite produced is dropped as a duplicate, of a line already there or of an earlier rewritten one, in any order; a duplicate already in the file is left as found.
    kept = {ln.strip() for ln in lines if bare.match(ln) and not has_stale_host(ln)}
    out: list[str] = []
    for original in lines:
        line = swap_host(original)
        if has_stale_host(original) and bare.match(line):
            if line.strip() in kept:
                continue
            kept.add(line.strip())
        out.append(line)
    return "".join(out)


def apply(apt_root: pathlib.Path, env: dict[str, str]) -> list[pathlib.Path]:
    """Rewrite the mirror files under `apt_root`; return the files changed. A non-hosted environment changes nothing."""
    if not hosted_runner(env):
        return []
    changed: list[pathlib.Path] = []
    for pattern in GLOBS:
        for path in sorted(apt_root.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            new = rewrite_text(text)
            if new != text:
                path.write_text(new, encoding="utf-8")
                changed.append(path)
    return changed


RETRIES_FILE = "apt.conf.d/80ci-acquire-retries"
RETRIES_TEXT = 'Acquire::Retries "3";\n'


def ensure_retries(apt_root: pathlib.Path, env: dict[str, str]) -> bool:
    """Write apt's own `Acquire::Retries` drop-in on a hosted runner; True when it wrote. Every later apt call (renet's, playwright's) inherits it."""
    if not hosted_runner(env):
        return False
    path = apt_root / RETRIES_FILE
    if path.is_file() and path.read_text(encoding="utf-8") == RETRIES_TEXT:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(RETRIES_TEXT, encoding="utf-8")
    return True


def main() -> int:
    env = dict(os.environ)
    if not hosted_runner(env):
        print("apt-mirror: not a GitHub-hosted runner; apt sources left alone")
        return 0
    changed = apply(pathlib.Path("/etc/apt"), env)
    if ensure_retries(pathlib.Path("/etc/apt"), env):
        print(f"apt-mirror: wrote /etc/apt/{RETRIES_FILE} ({RETRIES_TEXT.strip()})")
    if changed:
        print(
            f"apt-mirror: {AZURE_HOST} -> {GLOBAL_HOST} in: " + ", ".join(str(p) for p in changed)
        )
    else:
        print(
            f"apt-mirror: no {AZURE_HOST} or ec2 regional entry under /etc/apt; nothing to change"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
