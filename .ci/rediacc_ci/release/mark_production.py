#!/usr/bin/env python3
"""Port of `.ci/scripts/release/mark-production.sh`.

Records what is ACTUALLY in production. GitHub's "Latest release" badge tracks
whatever was published most recently, which on this repo is the EDGE build,
published on every release-worthy merge to main. Production is whatever
survived the 7-day soak and was promoted, so this script writes two markers a
human can trust: the MOVING annotated tag `production`, and `--latest` on that
version's GitHub Release.

Usage: mark_production.py <version>, or `VERSION=<version>` in the environment.

"COULD NOT TELL" IS A FAILURE, NOT A PASS, and that is the whole reason this
script has more code than two `gh` calls. The release lookup is verified rather
than assumed, and a 403 or a network fault takes the distinct "the check did
NOT run" branch instead of being folded into "no such release". Both branches
are preserved here verbatim.

THE TAG IS RESOLVED THROUGH THE API, NOT THROUGH git, and the port keeps that.
The caller (`promote-stable.yml`'s verify-stable job) does a sparse, shallow
checkout with no tags, where `git tag -f -a production "$VERSION^{commit}"`
fails with "unknown revision" on a perfectly good tag. An annotated tag's ref
points at a TAG object, so the port also keeps the dereference step: without
it, `production` would point at an annotation and `git show production` would
print the message instead of the code.

TWO LOGGERS, BECAUSE THE TWIN HAS TWO. `source common.sh 2>/dev/null || { ... }`
means the script runs with common.sh's stderr loggers when the library is
present and with a private `echo`-based fallback when it is not -- and the
fallback's `log_info` writes to STDOUT, not stderr, with no glyph. That is a
stream difference, not a cosmetic one, so `_Loggers.for_root()` picks the same
pair off the same single input (does `<root>/.ci/scripts/lib/common.sh` exist),
and the differential drives BOTH by copying each subject into a fixture tree
with no lib directory. A port that only implemented the common.sh path would be
byte-identical in CI and wrong on any machine where the library is missing,
which is precisely the case the fallback exists for.

ROOT IS DERIVED FROM THIS FILE'S OWN LOCATION, matching the twin's
`SCRIPT_DIR/../../..`. This module sits one directory deeper than the twin, so
it is `parents[3]` here against the twin's `parents[2]`, and both land on the
repository root. `rediacc_ci.paths.repo_root()` is deliberately NOT used: it
honours `$REDIACC_CI_ROOT`, the twin has no such override, and a fixture that
moved one and not the other would diverge for a reason that has nothing to do
with this script.

THE ONE KNOWN DIVERGENCE, PINNED BY A TEST RATHER THAN HIDDEN. common.sh logs
through `echo -e`, which interprets backslash escapes IN THE MESSAGE, and the
error branches interpolate `gh`'s own output into the message. So a `gh` failure
whose text contains a literal `\\n` prints a newline through the twin and two
characters through this port. `rediacc_ci.log` formats the message as data on
purpose (see its module docstring); the differential asserts the two disagree
there, so nobody later "fixes" the Python to re-interpret escapes.

K=5 LEDGER: `.ci/shadow/w7p6-mark-production.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import log

# `^v[0-9]+\.[0-9]+\.[0-9]+$`: a malformed version must NOT become a tag, because `production` is the thing humans will trust.
SEMVER_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# `${GITHUB_REPOSITORY:-rediacc/console}`.
DEFAULT_REPO = "rediacc/console"

# The two substrings that mean "this version was never published", as opposed to "the lookup itself failed". Everything else takes the did-NOT-run branch.
NOT_FOUND_MARKERS = ("release not found", "Not Found")


class _Loggers:
    """The twin's two logging worlds, chosen the way the twin chooses them.

    `common` is common.sh's: glyph, colour on a tty, STDERR for both levels.
    `fallback` is the inline `log_info() { echo "$*"; }` /
    `log_error() { echo "$*" >&2; }` pair, which puts info on STDOUT bare.
    """

    def __init__(self, *, common_sh: bool) -> None:
        self.common_sh = common_sh

    @classmethod
    def for_root(cls, root: pathlib.Path) -> _Loggers:
        return cls(common_sh=(root / ".ci" / "scripts" / "lib" / "common.sh").is_file())

    def info(self, message: str) -> None:
        if self.common_sh:
            log.info(message)
        else:
            print(message, flush=True)

    def error(self, message: str) -> None:
        if self.common_sh:
            log.error(message)
        else:
            print(message, file=sys.stderr, flush=True)

    def require_cmd(self, cmd: str) -> bool:
        """Both worlds print the same words; only the decoration differs."""
        if shutil.which(cmd) is not None:
            return True
        self.error("Required command '%s' is not available" % cmd)
        return False


def console_root() -> pathlib.Path:
    # This file: <root>/.ci/rediacc_ci/release/mark_production.py
    return pathlib.Path(__file__).resolve().parents[3]


def normalise_version(raw: str) -> str:
    """`v${VERSION#v}`: add a leading `v`, and strip exactly ONE if present.

    `vv1.2.3` therefore stays `vv1.2.3` and is rejected by SEMVER_RE, and
    `1.2.3` becomes `v1.2.3`. Reproduced rather than tidied: the twin's
    normalisation is the thing that decides which strings reach the tag.
    """
    return "v" + raw.removeprefix("v")


def is_semver(version: str) -> bool:
    return SEMVER_RE.match(version) is not None


def looks_missing(text: str) -> bool:
    """The `case` in the twin: which failure means "never published"."""
    return any(marker in text for marker in NOT_FOUND_MARKERS)


def ref_path(repo: str, version: str) -> str:
    return "repos/%s/git/ref/tags/%s" % (repo, version)


def tag_object_path(repo: str, sha: str) -> str:
    return "repos/%s/git/tags/%s" % (repo, sha)


def production_ref_path(repo: str) -> str:
    return "repos/%s/git/refs/tags/production" % repo


def refs_path(repo: str) -> str:
    return "repos/%s/git/refs" % repo


def _capture_merged(args: list[str]) -> tuple[int, str]:
    """`out="$(cmd 2>&1)"`: both streams into one string, trailing newlines gone."""
    proc = subprocess.run(
        ["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
    )
    return proc.returncode, proc.stdout.rstrip("\n")


def _quiet(args: list[str]) -> int:
    """`cmd >/dev/null 2>&1`."""
    return subprocess.run(
        ["gh", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode


def _stdout_devnull(args: list[str]) -> int:
    """`cmd >/dev/null`: stderr is INHERITED, so gh's own diagnostic still reaches
    the caller when a mutation fails, which is the only explanation anyone gets
    before `set -e` ends the run."""
    return subprocess.run(["gh", *args], stdout=subprocess.DEVNULL, check=False).returncode


def _inherit(args: list[str]) -> int:
    """`cmd` with NO redirection: `gh release edit` writes its confirmation to
    the script's own stdout, which is the only thing this script ever puts
    there."""
    return subprocess.run(["gh", *args], check=False).returncode


def main(argv: list[str]) -> int:
    root = console_root()
    out = _Loggers.for_root(root)

    if not out.require_cmd("gh"):
        return 1

    # `VERSION="${1:-${VERSION:-}}"`: argv[1] if it is non-empty, else $VERSION.
    version = argv[0] if argv and argv[0] else os.environ.get("VERSION", "")
    if not version:
        out.error("mark-production: no version given (argv[1] or $VERSION)")
        return 1

    version = normalise_version(version)
    if not is_semver(version):
        out.error("mark-production: '%s' is not strict semver (expected vX.Y.Z)" % version)
        return 1

    rc, text = _capture_merged(["release", "view", version, "--json", "tagName"])
    if rc != 0:
        if looks_missing(text):
            out.error(
                "mark-production: no GitHub Release for %s; refusing to mark a version "
                "that was never published" % version
            )
        else:
            out.error(
                "mark-production: could not read the release for %s, so the check did "
                "NOT run: %s" % (version, text)
            )
        return 1

    out.info("mark-production: %s is a published release" % version)

    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO

    rc, sha = _capture_merged(["api", ref_path(repo, version), "--jq", ".object.sha"])
    if rc != 0:
        out.error("mark-production: could not resolve %s to a commit: %s" % (version, sha))
        return 1

    rc, obj_type = _capture_merged(["api", ref_path(repo, version), "--jq", ".object.type"])
    if rc != 0:
        out.error("mark-production: could not resolve %s's object type: %s" % (version, obj_type))
        return 1

    if obj_type == "tag":
        rc, sha = _capture_merged(["api", tag_object_path(repo, sha), "--jq", ".object.sha"])
        if rc != 0:
            out.error(
                "mark-production: could not dereference the annotated tag object for "
                "%s: %s" % (version, sha)
            )
            return 1

    if _quiet(["api", production_ref_path(repo)]) == 0:
        rc = _stdout_devnull(
            [
                "api",
                "--method",
                "PATCH",
                production_ref_path(repo),
                "-f",
                "sha=%s" % sha,
                "-F",
                "force=true",
            ]
        )
    else:
        rc = _stdout_devnull(
            [
                "api",
                "--method",
                "POST",
                refs_path(repo),
                "-f",
                "ref=refs/tags/production",
                "-f",
                "sha=%s" % sha,
            ]
        )
    if rc != 0:
        # `set -e`: the script dies HERE, with the failing command's status and without the "moved the tag" line. No message of its own is invented.
        return rc

    out.info("mark-production: moved the 'production' tag to %s (%s)" % (version, sha))

    rc = _inherit(["release", "edit", version, "--latest"])
    if rc != 0:
        return rc

    out.info("mark-production: marked %s as the latest GitHub Release" % version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
