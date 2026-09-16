"""Port of `.ci/scripts/release/validate-stage-artifacts.sh`.

Counts the staged release artifacts under `dist/`, writes the run summary,
and fails the stage when anything expected is missing. Pure filesystem
inspection plus one shelled-out `du -sh` for the human-readable pages-bundle
size: no network, no wrangler/aws/gh/docker, nothing that mutates anything.

`du` IS SHELLED OUT TO, NOT REIMPLEMENTED, for the same reason `date` is in
`rediacc_ci.release.check_soak_period`: reproducing `du`'s human-readable
rounding (`52K` vs `53248`) in Python would be a second, silently-divergent
implementation of a contract the system binary already owns. `cut -f1` splits
on a literal TAB, confirmed directly (`du -sh <dir>/ | cat -A` prints
`52K^I<dir>/$`), so this port splits on `"\t"` rather than on whitespace.

REPO ROOT COMES FROM `rediacc_ci.paths.repo_root()`, not from a manual
`../../..` climb. Unlike the deploy-side forwarding shims in this box, this
port genuinely needs the twin's `cd "$(get_repo_root)"` behaviour (every
`dist/...` path is repo-root-relative), and `paths.repo_root()` is the
one program-wide answer to "where is the repo root" -- including its
`$REDIACC_CI_ROOT` override, which is what lets the differential test point
both sides at an isolated fixture instead of this checkout's real `dist/`.

`-type f` EXCLUDES SYMLINKS, and this port's file-counting walk does too:
`find -type f` reports a symlink's type as `l`, not `f`, even when the link
target is a regular file. `os.walk` alone does not make that distinction (a
symlink-to-file shows up in `filenames` either way), so every count here
explicitly skips `Path.is_symlink()` entries before testing `is_file()`.

`FIND ... 2>/dev/null | wc -l` NEVER RAISES; A MISSING DIRECTORY COUNTS AS
ZERO, matching the twin: this port returns 0 for any `dist/...` path that is
not a directory rather than raising, which is what lets an entirely absent
`dist/` tree fail loud through the vacuity checks below instead of crashing
before it gets there.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys

from rediacc_ci import paths

SELF = "validate-stage-artifacts.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def _count_files(base: str, pattern: str | None = None) -> int:
    """`find <base> [-name <pattern>] -type f | wc -l`, symlinks excluded."""
    if not os.path.isdir(base):
        return 0
    count = 0
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            if pattern is not None and not fnmatch.fnmatchcase(name, pattern):
                continue
            count += 1
    return count


def _pages_size(base: str) -> str:
    """`du -sh <base>/ 2>/dev/null | cut -f1`, empty string when `du` fails."""
    proc = subprocess.run(["du", "-sh", base + "/"], capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return ""
    first_line = proc.stdout.split("\n", 1)[0]
    return first_line.split("\t", 1)[0]


def main(argv: list[str]) -> int:
    del argv
    summary_path = _require("GITHUB_STEP_SUMMARY")
    output_path = _require("GITHUB_OUTPUT")
    event_name = _require("EVENT_NAME")

    mode = os.environ.get("MODE", "")
    next_version = os.environ.get("NEXT_VERSION", "")
    channel = os.environ.get("CHANNEL", "")

    root = str(paths.repo_root())
    dist = os.path.join(root, "dist")

    summary_lines: list[str] = []

    def summary(line: str) -> None:
        summary_lines.append(line)

    summary(f"## {mode}Stage Artifacts Results")
    summary("")

    cli_count = _count_files(os.path.join(dist, "cli"))
    pkg_count = _count_files(os.path.join(dist, "packages"))
    deb_count = _count_files(os.path.join(dist, "packages"), "*.deb")
    rpm_count = _count_files(os.path.join(dist, "packages"), "*.rpm")
    apk_count = _count_files(os.path.join(dist, "packages"), "*.apk")
    arch_count = _count_files(os.path.join(dist, "packages"), "*.pkg.tar.zst")
    pages_size = _pages_size(os.path.join(dist, "pages")) or "N/A"
    apt_files = _count_files(os.path.join(dist, "repos", "apt", "dists"))
    rpm_files = _count_files(os.path.join(dist, "repos", "rpm", "repodata"))

    summary("| Artifact | Count/Size |")
    summary("|----------|------------|")
    summary(f"| CLI artifacts | {cli_count} files |")
    summary(
        f"| Linux packages | {pkg_count} files "
        f"(deb:{deb_count} rpm:{rpm_count} apk:{apk_count} arch:{arch_count}) |"
    )
    summary(f"| Pages bundle | {pages_size} |")
    summary(f"| APT metadata | {apt_files} files |")
    summary(f"| RPM metadata | {rpm_files} files |")
    summary("")
    summary(f"**Version:** v{next_version}")
    summary(f"**Channel:** {channel}")

    failed = False

    if cli_count == 0:
        print("::error::VACUOUS: No CLI artifacts found under dist/cli")
        failed = True
    if pkg_count == 0:
        print("::error::No Linux packages found")
        failed = True
    if deb_count < 2:
        print(f"::error::Expected at least 2 DEB packages, found {deb_count}")
        failed = True
    if rpm_count < 2:
        print(f"::error::Expected at least 2 RPM packages, found {rpm_count}")
        failed = True
    if apk_count < 2:
        print(f"::error::Expected at least 2 APK packages, found {apk_count}")
        failed = True
    if arch_count < 2:
        print(f"::error::Expected at least 2 Archlinux packages, found {arch_count}")
        failed = True

    if channel:
        if apt_files == 0:
            print("::error::No APT metadata files found")
            failed = True
        if rpm_files == 0:
            print("::error::No RPM metadata files found")
            failed = True
    else:
        print(
            f"::notice::Channel is empty for event '{event_name}', so no "
            "package-repository metadata was built; skipping the APT/RPM "
            "metadata assertions."
        )
        summary("")
        summary(
            "> **APT/RPM metadata assertions skipped.** This run has no release "
            f"channel (event: `{event_name}`), so cd-stage.yml did not build "
            "package repositories. Every other artifact assertion above still applied."
        )

    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.writelines(line + "\n" for line in summary_lines)

    if failed:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n**Status:** Validation FAILED\n")
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write("passed=false\n")
        return 1

    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
        if event_name == "push":
            fh.write("**Status:** All validation passed. Ready for publish.\n")
        else:
            fh.write("**Status:** All validation passed.\n")
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write("passed=true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
