#!/usr/bin/env python3
"""Pre-places the bitwarden/sm-action binary where its own index.js looks first, with a retrying download and a pinned checksum.

Usage (from action.yml): python3 "$BWS_PREWARM"
Environment: RUNNER_WORKSPACE, RUNNER_OS, RUNNER_ARCH, GITHUB_OUTPUT.

It sits beside the action because callers sparse-check-out only `.github/actions` and `.ci/config`. Standard library only.

WHY THIS EXISTS, paid for on 2026-09-03 (run 33753814832, job "Initialize"). sm-action ships no binary: index.js downloads sm-action-<triple> from its own GitHub release on every job, ONCE, with no retry. That download timed out after 5.3s, and its fallback is `cargo build`, run with cwd = the WORKSPACE rather than the action directory, so it died on "could not find Cargo.toml" and could never have worked here. One five-second network blip therefore hard-fails the Initialize job, which every other job in the run depends on.
index.js:213-224 checks `<action_dir>/target/<triple>/release/sm-action` FIRST and returns it if present, so placing the file there skips its download entirely.

THE VERSION IS DERIVED, NOT PINNED, and that is the load-bearing choice. sm-action builds its URL from its own version.json, so pinning a version here would let a pin bump serve a STALE binary silently, which is worse than the flake. This reads the same version.json; a version whose checksums this file does not carry is a skip, not a guess.

EVERY FAILURE HERE IS A SKIP (a `::warning::` and exit 0), except a checksum mismatch. Skipping leaves sm-action doing exactly what it does without this step, so this step can slow a job down and cannot break one. A mismatch is the one loud case (`::error::`, exit 1): the bytes at a pinned release changed, and that is not a thing to route around.

On success, or when the binary is already present, `binary=<path>` is appended to GITHUB_OUTPUT; every skip leaves it unset.

Bumping the sm-action pin is a FOUR-place change: CHECKSUMS below, the `uses:` line in action.yml, the org action allowlist (see the action.yml header), and nothing else; the version and URL follow from version.json.
"""

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# Checksums of the v3.0.1 release assets, taken from the release itself.
CHECKSUMS = {
    "3.0.1": {
        "x86_64-unknown-linux-gnu": "fa998e9db775d5c7bdbc0fd8840ac6474a8348cdc989176c5ce24c3d09045752",
        "aarch64-unknown-linux-gnu": "35dde396e46be03c2b8f711d8ea4c3c75a3b42ab6681a260d614b17fca726989",
        "x86_64-apple-darwin": "9dfeab4d83b0347f9b5a04e8ca57f816c390b0f1c58a3d3bd7919ebfd3ab1124",
        "aarch64-apple-darwin": "a426480977db65e7ae0d50c5e0ba70508ff15bb1fc803a9b9048e5ccda8d1b73",
        "x86_64-pc-windows-msvc": "ae9cf1f9c400200cf889f17a44d7b3c9c525b9f462c0acd3cda76efab74e0174",
        "aarch64-pc-windows-msvc": "be716878c305707b7141e9581cdbf292c785f3aa3f7fbb42ac9c5e5460c09dba",
    }
}

TRIPLES = {
    ("Linux", "X64"): ("x86_64-unknown-linux-gnu", ""),
    ("Linux", "ARM64"): ("aarch64-unknown-linux-gnu", ""),
    ("macOS", "X64"): ("x86_64-apple-darwin", ""),
    ("macOS", "ARM64"): ("aarch64-apple-darwin", ""),
    ("Windows", "X64"): ("x86_64-pc-windows-msvc", ".exe"),
    ("Windows", "ARM64"): ("aarch64-pc-windows-msvc", ".exe"),
}

RETRIES = 5
RETRY_DELAY = 2


class SkipError(Exception):
    """Leave the binary unplaced; sm-action then downloads it once itself."""


class MismatchError(Exception):
    """The bytes at a pinned release changed."""


def find_checkout(workspace: str) -> pathlib.Path:
    """The sm-action checkout under `<workspace>/../_actions`, never inside the workspace."""
    actions_root = pathlib.Path(workspace + "/../_actions")
    for candidate in sorted(actions_root.glob("bitwarden/sm-action/*")):
        if candidate.is_dir():
            return candidate
    raise SkipError("sm-action checkout not found under _actions")


def read_version(directory: pathlib.Path) -> str:
    """The `version` of sm-action's own version.json."""
    try:
        text = (directory / "version.json").read_text(encoding="utf-8")
    except OSError:
        text = ""
    match = re.search(r'"version"\s*:\s*"([^"]*)"', text)
    if not match or not match.group(1):
        raise SkipError("cannot read a version from %s/version.json" % directory)
    return match.group(1)


def download(url: str, target: str) -> bool:
    """curl with its own retry, as the inline step ran it; True when the file is complete."""
    argv = [
        "curl",
        "-fsSL",
        "--retry",
        str(RETRIES),
        "--retry-all-errors",
        "--retry-delay",
        str(RETRY_DELAY),
        "--connect-timeout",
        "10",
        "--max-time",
        "180",
        "-o",
        target,
        url,
    ]
    try:
        return subprocess.run(argv, check=False).returncode == 0
    except OSError:
        return False


def prewarm(env: dict[str, str]) -> str:
    """Place the binary and return its path, or raise SkipError / MismatchError."""
    directory = find_checkout(env.get("RUNNER_WORKSPACE", ""))
    key = (env.get("RUNNER_OS", ""), env.get("RUNNER_ARCH", ""))
    if key not in TRIPLES:
        raise SkipError("unmapped runner %s/%s" % (key[0] or "?", key[1] or "?"))
    triple, ext = TRIPLES[key]

    dest = directory / "target" / triple / "release" / ("sm-action" + ext)
    if dest.is_file():
        print("sm-action binary already present; nothing to do")
        return str(dest)

    version = read_version(directory)
    want = CHECKSUMS.get(version, {}).get(triple, "")
    if not want:
        raise SkipError(
            "no pinned checksum for sm-action %s/%s (pin bumped without updating this table)"
            % (version, triple)
        )

    url = "https://github.com/bitwarden/sm-action/releases/download/v%s/sm-action-%s%s" % (
        version,
        triple,
        ext,
    )
    handle, tmp = tempfile.mkstemp()
    os.close(handle)
    try:
        if not download(url, tmp):
            raise SkipError(
                "download failed after %d retries. sm-action will now try ONCE itself; if that "
                "also fails it reports a Cargo.toml error, which is its broken source fallback, "
                "not a repo problem" % RETRIES
            )
        got = hashlib.sha256(pathlib.Path(tmp).read_bytes()).hexdigest()
        if got != want:
            raise MismatchError(
                "sm-action %s/%s checksum mismatch: got %s, pinned %s. The bytes at a pinned "
                "release changed; do not route around this." % (version, triple, got, want)
            )
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(tmp, str(dest))
            dest.chmod(0o755)
        except OSError:
            raise SkipError("could not install the binary at %s" % dest) from None
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("pre-placed sm-action %s/%s (sha256 verified)" % (version, triple))
    return str(dest)


def main() -> int:
    try:
        binary = prewarm(dict(os.environ))
    except SkipError as exc:
        print("::warning::bws-secrets prewarm skipped: %s" % exc)
        return 0
    except MismatchError as exc:
        print("::error::%s" % exc)
        return 1
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("binary=%s\n" % binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
