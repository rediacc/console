"""Resolve one leg of a committed shard manifest, shared by `e2e` and `account_e2e`.

Both bash runners carried the same node heredoc: read `<manifest>`, require `of` to equal the asked-for leg count, find the leg whose `index` matches, refuse an empty leg, print each id. This is that program in Python, with the same refusals and the same message text.

Deliberate difference (Rule T): a spec that is not `<index>/<of>` was split by `spec.split("/").map(Number)` in node, so `1/x` became NaN and surfaced as `asked for 1/NaN` after the manifest had been read. A malformed spec is now refused first, with its own message. Both exit 1, so no caller sees a verdict change. A manifest that is missing or not JSON was a node stack trace; it is one clear line here.
"""

import json
import pathlib
import re

SPEC_RE = re.compile(r"^(\d+)/(\d+)$")


class ShardError(Exception):
    """A leg could not be resolved. The message is the whole diagnostic."""


def parse_spec(spec: str) -> tuple[int, int]:
    """`"3/8"` -> `(3, 8)`."""
    match = SPEC_RE.match(spec)
    if not match:
        raise ShardError(f"--shard '{spec}' is not <index>/<of>, e.g. 1/8")
    return int(match.group(1)), int(match.group(2))


def leg_ids(manifest_path: str | pathlib.Path, spec: str) -> list[str]:
    """The unit ids of leg `spec` in the manifest at `manifest_path`."""
    want_index, want_of = parse_spec(spec)
    try:
        data = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShardError(
            f"shard manifest {manifest_path} cannot be read: {exc.strerror or exc}"
        ) from exc
    except ValueError as exc:
        raise ShardError(f"shard manifest {manifest_path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "legs" not in data:
        raise ShardError(f"shard manifest {manifest_path} has no legs")
    if data.get("of") != want_of:
        raise ShardError(
            f"shard manifest {manifest_path} has {data.get('of')} leg(s); asked for {want_index}/{want_of}"
        )
    for leg in data["legs"]:
        if leg.get("index") == want_index:
            ids = list(leg.get("ids") or [])
            if ids:
                return [str(i) for i in ids]
            break
    raise ShardError(f"shard manifest {manifest_path} has no non-empty leg {want_index}")
