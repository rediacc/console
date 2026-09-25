"""Stamp the stable channel into a staged copy of an edge channel directory, BEFORE anything uploads it (#b22efec4).

`upload_repos_to_r2.py` bakes each channel's name into its copy of the installers (`REDIACC_CHANNEL:-<channel>` in install.sh, `} else { "<channel>" }` in install.ps1), and the rpm and archlinux channel configs carry the channel in their URLs. A promote that copies `edge/` to `stable/` byte for byte therefore publishes installers that default new installs to EDGE unless it rewrites them.

THE REWRITE MUST PRECEDE THE UPLOAD. The hotfix lane used to upload the raw edge bodies and fix them in a later loop; on 2026-09-24 a run died between the two (its minted R2 token expired) and `https://releases.rediacc.com/cli/stable/install.sh` was left defaulting to edge. Both promotes now call `stamp_stable` on the local staging directory right after the download, so no upload of a stable path ever carries the edge default, however far the run gets.

THE STAMP IS VERIFIED, because `sed` exits 0 when a pattern matches nothing. A template whose default is spelled some other way would pass through unchanged and reach stable still pointing at edge; `verify_stable` refuses that before any upload.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci.core import common

# The two installer substitutions, the shell default first, the PowerShell one second. The inverse of `upload_repos_to_r2.sed_argv`.
INSTALL_SED = (
    "s|REDIACC_CHANNEL:-edge|REDIACC_CHANNEL:-stable|g",
    's|} else { "edge" }|} else { "stable" }|g',
)
# The rpm/archlinux channel configs name the channel in their base URLs.
CHANNEL_SED = "s|/edge/|/stable/|g"

# Per channel directory, the files the stamp rewrites and the expressions it applies. A directory absent from this table carries nothing channel-specific (`apt`, `apk`).
REWRITES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "cli": (
        ("install.sh", INSTALL_SED),
        ("install.ps1", INSTALL_SED),
    ),
    "rpm": (("rediacc.repo", (CHANNEL_SED,)),),
    "archlinux": (("rediacc.conf", (CHANNEL_SED,)),),
}

# What a stamped file must contain, and must not. Keyed by file name.
MUST_CONTAIN: dict[str, str] = {
    "install.sh": "REDIACC_CHANNEL:-stable",
    "install.ps1": '} else { "stable" }',
}
MUST_NOT_CONTAIN: dict[str, str] = {
    "install.sh": "REDIACC_CHANNEL:-edge",
    "install.ps1": '} else { "edge" }',
    "rediacc.repo": "/edge/",
    "rediacc.conf": "/edge/",
}


class StampError(Exception):
    """A stamp that did not take. `status` is the exit code the caller should end with."""

    def __init__(self, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.status = status


def stamp_file(path: str, expressions: tuple[str, ...]) -> int:
    """Apply `expressions` to `path` in place through `sed_in_place`. Returns sed's status."""
    args: list[str] = []
    for expression in expressions:
        args += ["-e", expression]
    args.append(path)
    sys.stdout.flush()
    sys.stderr.flush()
    return common.sed_in_place(args)


def verify_stable(name: str, path: str) -> None:
    """Refuse a stamped file that still points at edge, or that lacks the stable default."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    good = MUST_CONTAIN.get(name)
    bad = MUST_NOT_CONTAIN.get(name)
    if bad is not None and bad in body:
        raise StampError(
            "%s still carries %r after the stable stamp; refusing to promote it" % (path, bad)
        )
    if good is not None and good not in body:
        raise StampError(
            "%s has no %r after the stable stamp (the edge default is spelled in a way the stamp does not "
            "recognise); refusing to promote it" % (path, good)
        )


def stamp_stable(dir_name: str, directory: str) -> None:
    """Stamp every channel-specific file of `dir_name` found under `directory`, then verify each.

    An ABSENT file is skipped, which is what both bash twins do (`[[ -f "$f" ]]`). Raises `StampError` on a sed failure or a stamp that did not take.
    """
    for name, expressions in REWRITES.get(dir_name, ()):
        target = os.path.join(directory, name)
        if not os.path.isfile(target):
            continue
        status = stamp_file(target, expressions)
        if status:
            raise StampError("sed failed on %s (exit %d)" % (target, status), status)
        verify_stable(name, target)
