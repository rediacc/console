"""Make one command unreachable on a PATH, without disturbing any other.

WHY THIS EXISTS. Several cases in this suite exercise what a subject does when a
tool is MISSING -- `require_cmd aws` refusing, a forward stopping before it can
reach R2 -- and they established that condition by ASSUMING the host did not
have the tool. `test_release_backfill_write_sentinel.py` even said so out loud,
in a test whose only job was to check the assumption:

    assert shutil.which("aws") is None, (
        "aws is installed on this host; the DRY_RUN=false cases below assume it
         is absent so the forward stops before any R2 access. Re-derive them
         against a host without aws, or they are exercising a different path
         than documented."
    )

That assumption held on every developer machine here and is false on a GitHub
runner, which ships the AWS CLI at `/usr/local/bin/aws`. Measured in CI run
34970782616: three cases failed, and the honest reading is not that CI is wrong
but that the tests were never exercising the refusal they claim to -- they were
exercising whatever the host happened to make true.

A test that needs a tool absent should MAKE it absent. That is what this does.

WHY NOT JUST `PATH=/usr/bin:/bin`. It is the idiom used elsewhere in this tree
(`test_security_shfmt.py`'s scratch-cache case) and it works today only because
`aws` happens to live in `/usr/local/bin` on the runner. It is a guess about
where a tool is, and the next tool, or the next image, makes it wrong silently
-- which is the exact failure mode being fixed here. Masking by construction
cannot be wrong about that.

HOW. Every PATH entry that does NOT contain the tool is kept verbatim. An entry
that DOES is replaced by a scratch mirror: one symlink per name in that
directory, minus the tool. So everything else that directory provided still
resolves, and only the named command disappears.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil


def path_without(tool: str, scratch: pathlib.Path, base: str | None = None) -> str:
    """`base` (default: the ambient PATH) with `tool` unreachable.

    `scratch` is a directory this may create mirrors under -- a pytest
    `tmp_path` in practice. Returns the new PATH string.
    """
    entries = (base if base is not None else os.environ.get("PATH", "")).split(os.pathsep)
    out: list[str] = []
    for index, entry in enumerate(entries):
        if not entry:
            continue
        directory = pathlib.Path(entry)
        candidate = directory / tool
        # `exists()` follows symlinks, which is what PATH resolution does too; a
        # dangling link is not a command and does not need masking.
        if not candidate.exists():
            out.append(entry)
            continue
        mirror = scratch / ("pathmask-%02d-%s" % (index, directory.name or "root"))
        mirror.mkdir(parents=True, exist_ok=True)
        try:
            names = os.listdir(directory)
        except OSError:
            # Unreadable directory: it cannot be mirrored, and it is also the directory the tool was found in, so DROPPING it is the safe end of the trade -- keeping it would leave the tool reachable, which is the one thing the caller asked to prevent.
            continue
        for name in names:
            if name == tool:
                continue
            link = mirror / name
            if not link.exists():
                with contextlib.suppress(OSError):
                    link.symlink_to(directory / name)
        out.append(str(mirror))
    return os.pathsep.join(out)


def assert_absent(tool: str, path: str) -> None:
    """Refuse to proceed unless `tool` really is unreachable on `path`.

    THE POINT OF CALLING THIS is that a mask nobody checked is indistinguishable
    from a host that happened not to have the tool -- which is the bug this
    module exists to retire. Cheap, and it makes the precondition an assertion
    instead of a hope.
    """
    found = shutil.which(tool, path=path)
    if found is not None:
        # RAISED, not asserted: this module is not a test file, so `python -O` would strip an `assert` and turn the one check that makes the mask trustworthy into nothing at all.
        raise AssertionError("%s is still reachable at %s on the masked PATH" % (tool, found))
