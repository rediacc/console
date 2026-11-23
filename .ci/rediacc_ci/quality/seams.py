"""The one reader for a quality gate's test seams: a scan-root override and a lowered corpus floor.

WHY THIS EXISTS. A gate that reads `*_ROOT`, `*_DIR` or `*_MIN` from the environment lets any process that sets it make a plain gate run scan another tree, or accept an empty corpus, and pass. Review findings d31194f4.1 and e626e6ae.1 found the same shape in two gates; this module is the shared fix, so the rule lives once.

THE RULE. A seam is honoured only for a path inside the temp directory, which is where every test fixture lives. Anything else is ignored with one note on stderr, so a plain run scans the repository. A floor override is honoured only together with a honoured scratch root, and a floor below one is refused whatever it says: a zero-file corpus is the shape these gates exist to reject.

THE READ STAYS AT THE CALL SITE. This module reads no environment variable. The env registry (`python_env_registry`) derives `<module>:<NAME>` pairs from a literal `os.environ.get("NAME")`, so each caller keeps that spelling and passes the value in: `seams.scratch_root("X_ROOT", os.environ.get("X_ROOT"))`.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile


def _bases() -> set[pathlib.Path]:
    return {pathlib.Path(tempfile.gettempdir()).resolve(), pathlib.Path("/tmp").resolve()}


def inside_temp(path: str | pathlib.Path) -> bool:
    """Whether `path`, symlinks resolved, lies inside the temp directory."""
    resolved = pathlib.Path(path).resolve()
    return any(resolved.is_relative_to(base) for base in _bases())


def scratch_root(name: str, raw: str | None) -> pathlib.Path | None:
    """The resolved override when `raw` names a path inside the temp directory, else None.

    None means the variable is unset or was ignored; an ignored one is reported on stderr, naming the variable, so a plain run says what it scanned.
    """
    if not raw:
        return None
    if inside_temp(raw):
        return pathlib.Path(raw).resolve()
    print(
        "NOTE: %s=%s is outside the temp directory, so it is ignored and the repository is scanned."
        % (name, raw),
        file=sys.stderr,
    )
    return None


def floor(name: str, raw: str | None, default: int, *, honoured: bool) -> int:
    """A corpus floor: `raw` replaces `default` only when `honoured`, and the result is never below one.

    `honoured` is the caller's statement that a scratch root is in force. Without it a lowered floor is ignored with a note; a raised one needs no permission and is kept. A non-integer `raw` raises ValueError.
    """
    if default < 1:
        raise ValueError("%s: the default floor must be at least 1, got %d" % (name, default))
    if not raw:
        return default
    value = int(raw)
    if value >= default:
        return value
    if not honoured:
        print(
            "NOTE: %s=%s lowers the floor without a scratch root, so it is ignored (floor %d)."
            % (name, raw, default),
            file=sys.stderr,
        )
        return default
    return max(1, value)
