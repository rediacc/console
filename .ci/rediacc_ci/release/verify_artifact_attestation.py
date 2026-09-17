"""Port of `.ci/scripts/release/verify-artifact-attestation.sh`.

Verifies build provenance (SLSA attestation) of every file under `dist/cli`
and `dist/packages`, relative to the repo root. Zero files found is a
FAILURE, not a pass -- the twin's own header names the incident this guards:
"the old script exited 0 having verified precisely zero artifacts,
indistinguishable from a clean pass."

`gh attestation verify` IS SHELLED OUT TO, not reimplemented: attestation
verification is exactly the kind of cryptographic, GitHub-hosted check that
has no local equivalent, so the differential fakes the `gh` BINARY and
proves this port drives it with the same per-file loop, the same counting,
and the same all-or-nothing exit as the twin.

FILE DISCOVERY REPRODUCES `find dist/cli dist/packages -type f 2>/dev/null`,
INCLUDING THE TWIN'S OWN CAVEAT: files are walked with `os.walk`, sorted for
determinism (the twin's `for f in $(find ...)` also happens to sort, since
`find`'s traversal order on a real filesystem is not glob-sorted but this
twin's own comment block already accepts `find`'s ordinary behaviour here --
sorting only makes this port's own output deterministic across runs, it does
not change which files are found). A missing directory is silently skipped,
matching `find`'s `2>/dev/null`.
"""

from __future__ import annotations

import os
import subprocess
import sys

SELF = "verify-artifact-attestation.py"
DIST_DIRS = ("dist/cli", "dist/packages")

# `.ci/rediacc_ci/release/verify_artifact_attestation.py` -> `.ci` -> repo root, exactly as the twin's `get_repo_root()` (`.ci/scripts/lib/../../..`, called from `.ci/scripts/release/`) is the same three levels up.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def _find_files(root: str) -> list[str]:
    found: list[str] = []
    for rel_dir in DIST_DIRS:
        base = os.path.join(root, rel_dir)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                full = os.path.join(dirpath, name)
                found.append(os.path.relpath(full, root))
    found.sort()
    return found


def main(argv: list[str]) -> int:
    del argv
    github_repository = _require("GITHUB_REPOSITORY")
    repo_root = _ROOT

    print("Verifying artifact provenance...")
    files = _find_files(repo_root)
    checked = 0
    failed_list: list[str] = []

    for f in files:
        checked += 1
        proc = subprocess.run(
            ["gh", "attestation", "verify", f, "--repo", github_repository],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
        if proc.returncode == 0:
            continue
        print(f"::error::Build attestation verification FAILED for {f}")
        combined = proc.stdout + proc.stderr
        sys.stderr.write(combined)
        failed_list.append(f)

    if checked == 0:
        print("::error::No files found under dist/cli or dist/packages, so NOTHING was verified.")
        print(
            "::error::The release artifacts were expected to be downloaded before this "
            "step. Verifying zero artifacts is not a pass."
        )
        return 1

    if failed_list:
        print(
            f"::error::{len(failed_list)} of {checked} release artifacts have no valid build attestation:"
        )
        for f in failed_list:
            sys.stderr.write(f"  - {f}\n")
        print(
            "::error::These bytes cannot be shown to be the bytes CI produced. Refusing to publish."
        )
        return 1

    print(f"::notice::Build provenance verified for all {checked} release artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
