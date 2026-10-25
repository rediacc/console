#!/usr/bin/env python3
"""Port of `.ci/scripts/release/mark-production.sh`.

Records what is ACTUALLY in production. GitHub's "Latest release" badge tracks whatever was published most recently, which on this repo is the EDGE build, published on every release-worthy merge to main. Production is whatever survived the 7-day soak and was promoted, so this script writes two markers a human can trust: the MOVING lightweight tag `production` (a ref straight at the release commit; an annotated release tag is dereferenced first), and `--latest` on that
version's GitHub Release.

Usage: mark_production.py <version>, or `VERSION=<version>` in the environment.

"COULD NOT TELL" IS A FAILURE, NOT A PASS, and that is the whole reason this script has more code than two `gh` calls. The release lookup is verified rather than assumed, and a 403 or a network fault takes the distinct "the check did NOT run" branch instead of being folded into "no such release". Both branches are preserved here verbatim.

THE TAG IS RESOLVED THROUGH THE API, NOT THROUGH git, and the port keeps that. The caller (`promote-stable.yml`'s verify-stable job) does a sparse, shallow
checkout with no tags, where `git tag -f -a production "$VERSION^{commit}"`
fails with "unknown revision" on a perfectly good tag. An annotated tag's ref points at a TAG object, so the port also keeps the dereference step: without it, `production` would point at an annotation and `git show production` would print the message instead of the code.

ONE LOGGER. The twin had two (`common.sh`'s stderr loggers, and a private `echo` fallback that wrote info to STDOUT when the library was missing). `common.sh` is deleted, and so is the fallback: every line goes through `rediacc_ci.log` (W11-B, a Rule-T fix; the two fixture-without-lib goldens were re-recorded `--source port`).

THE ONE KNOWN DIVERGENCE, PINNED BY A TEST RATHER THAN HIDDEN. common.sh logs through `echo -e`, which interprets backslash escapes IN THE MESSAGE, and the error branches interpolate `gh`'s own output into the message. So a `gh` failure whose text contains a literal `\\n` prints a newline through the twin and two characters through this port. `rediacc_ci.log` formats the message as
data on purpose (see its module docstring); the differential asserts the two disagree there, so nobody later "fixes" the Python to re-interpret escapes.

K=5 LEDGER: `.ci/shadow/w7p6-mark-production.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import gh_retry
from rediacc_ci.well_known import GH_REPO

# `^v[0-9]+\.[0-9]+\.[0-9]+$`: a malformed version must NOT become a tag, because `production` is the thing humans will trust.
SEMVER_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# `${GITHUB_REPOSITORY:-rediacc/console}`.
DEFAULT_REPO = GH_REPO

# The two substrings that mean "this version was never published", as opposed to "the lookup itself failed". Everything else takes the did-NOT-run branch.
NOT_FOUND_MARKERS = ("release not found", "Not Found")


class _Loggers:
    """The logging world: `rediacc_ci.log`, glyphs, colour on a tty, STDERR for both levels.

    The twin also had a private `echo`-based fallback (info on STDOUT, bare) for a checkout without `common.sh`. That file is deleted (PLAN-retire-bash-oracles W11-B), so the fallback world is deleted with it (a Rule-T fix: it would have silently moved info lines to stdout with no glyph).
    """

    def info(self, message: str) -> None:
        log.info(message)

    def error(self, message: str) -> None:
        log.error(message)

    def require_cmd(self, cmd: str) -> bool:
        if shutil.which(cmd) is not None:
            return True
        self.error("Required command '%s' is not available" % cmd)
        return False


def normalise_version(raw: str) -> str:
    """`v${VERSION#v}`: add a leading `v`, and strip exactly ONE if present.

    `vv1.2.3` therefore stays `vv1.2.3` and is rejected by SEMVER_RE, and `1.2.3` becomes `v1.2.3`. Reproduced rather than tidied: the twin's normalisation is the thing that decides which strings reach the tag.
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
    """`out="$(cmd 2>&1)"` as a READ with transient retry: a 5xx or connection fault is retried (5 s, 15 s), a 404 or auth failure is not. On success the text is stdout; on failure it is both streams, so the caller's message carries gh's own diagnostic. Trailing newlines gone."""
    result = gh_retry.gh(args)
    text = result.stdout_raw if result.ok else result.stdout_raw + result.stderr
    return result.returncode, text.rstrip("\n")


def _stdout_devnull(args: list[str]) -> int:
    """`cmd >/dev/null`: stderr is INHERITED, so gh's own diagnostic still reaches the caller when a mutation fails, which is the only explanation anyone gets before `set -e` ends the run."""
    return subprocess.run(["gh", *args], stdout=subprocess.DEVNULL, check=False).returncode


def _inherit(args: list[str]) -> int:
    """`cmd` with NO redirection: `gh release edit` writes its confirmation to the script's own stdout, which is the only thing this script ever puts there."""
    return subprocess.run(["gh", *args], check=False).returncode


def main(argv: list[str]) -> int:
    out = _Loggers()

    if not out.require_cmd("gh"):
        return 1

    # `VERSION="${1:-${VERSION:-}}"`: argv[1] if it is non-empty, else $VERSION.
    version = argv[0] if argv and argv[0] else os.environ.get("VERSION", "")
    if not version:
        out.error("rediacc_ci.release.mark_production: no version given (argv[1] or $VERSION)")
        return 1

    version = normalise_version(version)
    if not is_semver(version):
        out.error(
            "rediacc_ci.release.mark_production: '%s' is not strict semver (expected vX.Y.Z)"
            % version
        )
        return 1

    rc, text = _capture_merged(["release", "view", version, "--json", "tagName"])
    if rc != 0:
        if looks_missing(text):
            out.error(
                "rediacc_ci.release.mark_production: no GitHub Release for %s; refusing to mark a version "
                "that was never published" % version
            )
        else:
            out.error(
                "rediacc_ci.release.mark_production: could not read the release for %s, so the check did "
                "NOT run: %s" % (version, text)
            )
        return 1

    out.info("rediacc_ci.release.mark_production: %s is a published release" % version)

    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO

    rc, sha = _capture_merged(["api", ref_path(repo, version), "--jq", ".object.sha"])
    if rc != 0:
        out.error(
            "rediacc_ci.release.mark_production: could not resolve %s to a commit: %s"
            % (version, sha)
        )
        return 1

    rc, obj_type = _capture_merged(["api", ref_path(repo, version), "--jq", ".object.type"])
    if rc != 0:
        out.error(
            "rediacc_ci.release.mark_production: could not resolve %s's object type: %s"
            % (version, obj_type)
        )
        return 1

    if obj_type == "tag":
        rc, sha = _capture_merged(["api", tag_object_path(repo, sha), "--jq", ".object.sha"])
        if rc != 0:
            out.error(
                "rediacc_ci.release.mark_production: could not dereference the annotated tag object for "
                "%s: %s" % (version, sha)
            )
            return 1

    probe = gh_retry.gh(["api", production_ref_path(repo)])
    if not probe.ok and gh_retry.is_transient(probe.stderr):
        # A probe that failed TRANSIENTLY did not say the tag is absent. Falling to POST would try to create a ref that exists (422) or, worse, act on a wrong picture; the twin's one-shot `||` branch did exactly that. Refuse and let the run retry.
        out.error(
            "rediacc_ci.release.mark_production: could not tell whether the 'production' tag exists, so it was "
            "NOT moved: %s" % probe.stderr.strip()
        )
        return 1
    if probe.ok:
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
        # The failing call is NAMED (worklist #ae671b8f): gh's own text says only "Resource not accessible by integration (HTTP 403)", and with no line of ours the release lookup, the tag move and the release edit were indistinguishable in runs 38408143720 and 38556650310. A 403 here usually means the token lacks workflows:write for a commit range that touches .github/workflows.
        out.error(
            "rediacc_ci.release.mark_production: %s of the 'production' tag to %s failed (exit %d)"
            % ("moving" if probe.ok else "creating", sha, rc)
        )
        return rc

    out.info(
        "rediacc_ci.release.mark_production: moved the 'production' tag to %s (%s)" % (version, sha)
    )

    rc = _inherit(["release", "edit", version, "--latest"])
    if rc != 0:
        return rc

    out.info("rediacc_ci.release.mark_production: marked %s as the latest GitHub Release" % version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
