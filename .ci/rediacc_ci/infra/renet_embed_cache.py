#!/usr/bin/env python3
"""Decide whether a staged `private/renet/pkg/embed/assets` tree may be SAVED under the `renet-embed-assets-<lock hash>` cache key, and flag a restored entry that is not a real staging.

WHY THIS EXISTS. Every save site used `if: always() && steps.embed-cache.outputs.cache-hit != 'true'`. When an EARLIER step failed, the restore step was skipped, `cache-hit` was empty, and the save stored the checkout's skeleton (`.gitkeep` files, 1.15 KiB) under the real key. Measured on PR #591: job 109920400971 (run 36724524175) failed at "Install CLI Globally" and saved that skeleton at 2026-09-30T14:11:26Z. Cache keys are immutable and a PR-scope entry shadows the main-scope one, so every later E2E job on that PR restored the skeleton, reported a HIT, failed build.sh's receipt check, restaged the Docker builder (~690 s instead of ~20 s), and skipped the save because it had "hit". Run 36817363458 was cancelled by the per-job budget for exactly that.

The verdict is content-based, the same contract build.sh's `_embed_receipt_is_current` enforces: the receipt names the current lockfile's sha256, every listed asset is present with its recorded digest, no unlisted `.zst` sits beside them, and the list is not empty. A save is allowed only for a tree that passes it AND that this job staged itself (the restore ran and missed). Anything else (a skipped restore, a cancelled or failed staging, a restored entry) is never written back.

CLI (for jobs that build renet some other way, e.g. ci-build-renet.yml):

    RENET_EMBED_CACHE_HIT=<cache-hit output> python3 -m rediacc_ci.infra.renet_embed_cache verdict

writes `embed-cacheable=true|false` to `$GITHUB_OUTPUT` and exits 0.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

# The env var a workflow step sets from `steps.embed-cache.outputs.cache-hit`. ABSENT means "this step was not wired to a restore", which is never cacheable: a verdict that defaulted to true would recreate the skipped-restore poisoning this module exists to stop.
HIT_ENV = "RENET_EMBED_CACHE_HIT"

# The step output the save sites test.
OUTPUT_NAME = "embed-cacheable"


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def assets_dir(renet_src: pathlib.Path) -> pathlib.Path:
    return renet_src / "pkg" / "embed" / "assets"


def receipt_is_current(renet_src: pathlib.Path) -> bool:
    """The Python mirror of build.sh's `_embed_receipt_is_current`. True only for a tree a complete staging produced from the CURRENT lockfile."""
    assets = assets_dir(renet_src)
    try:
        data = json.loads((assets / ".staged.json").read_text(encoding="utf-8"))
        lock_sha = _sha256_file(renet_src / "embed-assets.lock.json")
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or data.get("lockfileSha256") != lock_sha:
        return False
    listed = data.get("assets")
    # A receipt listing nothing must never satisfy the check (build.sh's last line).
    if not isinstance(listed, dict) or not listed:
        return False
    for rel, entry in listed.items():
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        path = assets / rel
        if not isinstance(expected, str) or not path.is_file():
            return False
        if _sha256_file(path) != expected:
            return False
    # build.sh's EXTRA-FILE ARM: `find -mindepth 3 -maxdepth 3 -type f -name '*.zst'`.
    staged = [p for p in assets.glob("*/*/*.zst") if p.is_file()]
    return len(staged) == len(listed)


def cacheable(renet_src: pathlib.Path) -> bool:
    """True only when the restore RAN and MISSED (the env var is present and not "true") and the tree now carries a current receipt."""
    hit = os.environ.get(HIT_ENV)
    if hit is None or hit == "true":
        return False
    return receipt_is_current(renet_src)


def stale_hit_warning(renet_src: pathlib.Path) -> str | None:
    """A GitHub `::warning` line when a cache HIT restored a tree that is not a real staging, else None.

    The remedy is named because nothing in CI can repair it: the key is immutable, so every later job restages (~11 min) until the entry is deleted.
    """
    if os.environ.get(HIT_ENV) != "true" or receipt_is_current(renet_src):
        return None
    return (
        "::warning title=Stale renet-embed-assets cache entry::The restored "
        "pkg/embed/assets tree fails build.sh's receipt check, so build.sh restages "
        "every embedded asset (~11 min) and the immutable key is never rewritten. "
        "Delete the entry: gh cache list --key renet-embed-assets, then gh cache delete <id> "
        "for the one whose size is a few KiB."
    )


def write_verdict(renet_src: pathlib.Path) -> bool | None:
    """Append `embed-cacheable=<bool>` to `$GITHUB_OUTPUT` when that file is set; returns the verdict, or None when there is nowhere to write it."""
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if not github_output:
        return None
    verdict = cacheable(renet_src)
    with pathlib.Path(github_output).open("a", encoding="utf-8") as handle:
        handle.write("%s=%s\n" % (OUTPUT_NAME, "true" if verdict else "false"))
    return verdict


def main(argv: list[str]) -> int:
    if argv != ["verdict"]:
        sys.stderr.write("usage: python3 -m rediacc_ci.infra.renet_embed_cache verdict\n")
        return 2
    renet_src = pathlib.Path(__file__).resolve().parents[3] / "private" / "renet"
    verdict = write_verdict(renet_src)
    print("%s=%s" % (OUTPUT_NAME, "unset" if verdict is None else str(verdict).lower()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
