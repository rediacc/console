#!/usr/bin/env python3
"""Translates the requested secret NAMES into the `UUID > ENV_NAME` mapping sm-action reads.

Usage (from action.yml): python3 "$BWS_RESOLVE"
Environment: REQUESTED (one `NAME` or `NAME > ENV_NAME` per line, `#` comments allowed), MAP (path of .ci/config/bws-secret-map.json), GITHUB_OUTPUT.

It sits beside the action because callers sparse-check-out only `.github/actions` and `.ci/config`, so `.ci/rediacc_ci` is not guaranteed to exist. Standard library only, which also removes the old `jq` dependency (ubuntu-slim does not ship it).

Output: `mapping` is appended to GITHUB_OUTPUT as a heredoc, one `<uuid> > <env_name>` per line. A missing map, a malformed line, a name absent from the map and an empty request each print an `::error::` annotation and exit 1, so nothing reaches sm-action. An empty request is a wiring mistake: a fetch that fetches nothing.
"""

import json
import os
import re
import sys

NAME_RE = re.compile(r"[A-Za-z0-9_.=:-]+")
ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ResolveError(Exception):
    """A request the action must refuse; the message is the annotation text."""


def parse_line(raw: str) -> tuple[str, str] | None:
    """`(name, env_name)` for one request line, None for a blank or comment line."""
    line = raw.split("#", 1)[0].strip()
    if not line:
        return None
    name, sep, rest = line.partition(">")
    name = name.rstrip()
    env_name = rest.lstrip() if sep else name
    if not (NAME_RE.fullmatch(name) and ENV_RE.fullmatch(env_name)):
        raise ResolveError("malformed secrets line: '%s' (want NAME or NAME > ENV_NAME)" % raw)
    return name, env_name


def resolve(requested: str, secrets: dict) -> list[str]:
    """The `<uuid> > <env_name>` lines for a request, or a ResolveError."""
    lines: list[str] = []
    for raw in requested.splitlines():
        parsed = parse_line(raw)
        if parsed is None:
            continue
        name, env_name = parsed
        uuid = (secrets.get(name) or {}).get("id") or ""
        if not uuid:
            raise ResolveError(
                "secret '%s' is not in .ci/config/bws-secret-map.json. "
                "Add it to ci-shared and regenerate the map." % name
            )
        lines.append("%s > %s" % (uuid, env_name))
    if not lines:
        raise ResolveError(
            "no secrets requested -- a fetch that fetches nothing is a wiring mistake"
        )
    return lines


def main() -> int:
    map_path = os.environ.get("MAP", "")
    try:
        if not os.path.isfile(map_path):
            raise ResolveError("bws-secret-map.json not found at %s" % map_path)
        with open(map_path, encoding="utf-8") as handle:
            secrets = json.load(handle).get("secrets") or {}
        lines = resolve(os.environ.get("REQUESTED", ""), secrets)
    except ResolveError as exc:
        print("::error::%s" % exc)
        return 1
    print("resolved %d secret(s)" % len(lines))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("mapping<<BWS_EOF\n%sBWS_EOF\n" % "".join(line + "\n" for line in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
