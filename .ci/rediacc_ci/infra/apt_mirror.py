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

AZURE_HOST = "azure.archive.ubuntu.com"
GLOBAL_HOST = "archive.ubuntu.com"

# Files under the apt root that name a mirror.
GLOBS = ("apt-mirrors.txt", "sources.list", "sources.list.d/*.sources", "sources.list.d/*.list")


def hosted_runner(env: dict[str, str]) -> bool:
    return env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted"


def rewrite_text(text: str) -> str:
    """Replace the Azure host with the global archive, then drop the duplicate lines that makes in a mirror list.

    A duplicate is only collapsed in a line that is a bare mirror URL (apt-mirrors.txt entries, `http://host/ubuntu/ priority:N`), never in a `deb` or `URIs:` line, where a repeated line would change the file's meaning.
    """
    if AZURE_HOST not in text:
        return text
    lines = text.splitlines(keepends=True)
    bare = re.compile(r"\s*https?://")
    # Only a line the rewrite produced is dropped as a duplicate, of a line already there or of an earlier rewritten one, in any order; a duplicate already in the file is left as found.
    kept = {ln.strip() for ln in lines if bare.match(ln) and AZURE_HOST not in ln}
    out: list[str] = []
    for original in lines:
        line = original.replace(AZURE_HOST, GLOBAL_HOST)
        if AZURE_HOST in original and bare.match(line):
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


def main() -> int:
    env = dict(os.environ)
    if not hosted_runner(env):
        print("apt-mirror: not a GitHub-hosted runner; apt sources left alone")
        return 0
    changed = apply(pathlib.Path("/etc/apt"), env)
    if changed:
        print(
            f"apt-mirror: {AZURE_HOST} -> {GLOBAL_HOST} in: " + ", ".join(str(p) for p in changed)
        )
    else:
        print(f"apt-mirror: no {AZURE_HOST} entry under /etc/apt; nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
