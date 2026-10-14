"""The pin registry reader: `.ci/config/pins.json` for the Python side.

The registry is the one list of every pinned version and where each is written (agent/plans/PLAN-pins-command.md, Design 1). `scripts/lib/pins/registry.ts` is its loader for the TypeScript tools and carries the full field validation; `check:ci-pin-registry` runs that validation and the tree-wide completeness checks in CI.
This module reads the same file for Python callers and refuses, by field path, any part of an entry it hands out that is not the shape it needs, so a malformed edit fails at the caller rather than surfacing as a wrong label or an empty tuple.

First reader: `rediacc_ci.infra.renet_pkg_matrix.PIN_SITES`, the sites an `OBS REBUILT` finding tells the reader to move, which used to be a third hand-kept copy of the Leap pin's three files.
"""

from __future__ import annotations

import dataclasses
import functools
import json
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

REGISTRY_PARTS = (".ci", "config", "pins.json")


class PinsError(ValueError):
    """The registry is unreadable, or an entry is not the shape this reader needs; the message names the field."""


@dataclasses.dataclass(frozen=True)
class Site:
    repo: str
    file: str
    role: str
    expect: int
    label: str


@dataclasses.dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    name: str
    driver: str
    sites: tuple[Site, ...]


@dataclasses.dataclass(frozen=True)
class Registry:
    entries: tuple[Entry, ...]

    def entry(self, entry_id: str) -> Entry:
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise PinsError(f"no entry {entry_id!r} in the pin registry ({len(self.entries)} entries)")


def _str(obj: dict[str, object], key: str, field: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or value == "":
        raise PinsError(f"{field}.{key}: must be a non-empty string, got {value!r}")
    return value


def _site(raw: object, field: str) -> Site:
    if not isinstance(raw, dict):
        raise PinsError(f"{field}: must be an object")
    expect = raw.get("expect")
    if not isinstance(expect, int) or isinstance(expect, bool) or expect < 1:
        raise PinsError(f"{field}.expect: must be a positive integer, got {expect!r}")
    file = _str(raw, "file", field)
    label = raw.get("label", file)
    if not isinstance(label, str) or label == "":
        raise PinsError(f"{field}.label: must be a non-empty string, got {label!r}")
    return Site(
        repo=_str(raw, "repo", field),
        file=file,
        role=_str(raw, "role", field),
        expect=expect,
        label=label,
    )


def parse(raw: object) -> Registry:
    """A parsed pins.json, as the frozen records this module hands out."""
    if not isinstance(raw, dict):
        raise PinsError("(root): must be a JSON object")
    if raw.get("version") != 1:
        raise PinsError(f"version: must be 1, got {raw.get('version')!r}")
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PinsError("entries: must be a non-empty array")
    out: list[Entry] = []
    seen: set[str] = set()
    for i, e in enumerate(entries):
        field = f"entries[{i}]"
        if not isinstance(e, dict):
            raise PinsError(f"{field}: must be an object")
        entry_id = _str(e, "id", field)
        field = f"entries[{i}] ({entry_id})"
        if entry_id in seen:
            raise PinsError(f"{field}.id: is a duplicate")
        seen.add(entry_id)
        sites = e.get("sites")
        if not isinstance(sites, list):
            raise PinsError(f"{field}.sites: must be an array")
        kind = _str(e, "kind", field)
        if kind not in ("family", "leaf"):
            raise PinsError(f"{field}.kind: must be family or leaf, got {kind!r}")
        out.append(
            Entry(
                id=entry_id,
                kind=kind,
                name=_str(e, "name", field),
                driver=_str(e, "driver", field),
                sites=tuple(_site(s, f"{field}.sites[{j}]") for j, s in enumerate(sites)),
            )
        )
    return Registry(entries=tuple(out))


def registry_path(root: pathlib.Path | None = None) -> pathlib.Path:
    return paths.from_root(*REGISTRY_PARTS, root=root)


@functools.cache
def _load(path: pathlib.Path) -> Registry:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PinsError(f"cannot read the pin registry {path}: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PinsError(f"{path}: not JSON ({exc})") from exc
    try:
        return parse(raw)
    except PinsError as exc:
        raise PinsError(f"{path}: {exc}") from exc


def load(path: pathlib.Path | None = None) -> Registry:
    """The registry at `path` (default: the console's), parsed once per process."""
    return _load(path if path is not None else registry_path())


def site_labels(entry_id: str, path: pathlib.Path | None = None) -> tuple[str, ...]:
    """How a message names each site of one entry, in registry order (the `label`, or the file when there is none)."""
    entry = load(path).entry(entry_id)
    if not entry.sites:
        raise PinsError(f"{entry_id}: has no sites to name")
    return tuple(s.label for s in entry.sites)
