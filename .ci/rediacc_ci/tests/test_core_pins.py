"""`rediacc_ci.core.pins` against the real registry and against malformed copies of it.

the real file    loads, and the Leap entry names the three sites renet_pkg_matrix's OBS REBUILT finding lists, in that order.
the refusals     each malformed field is refused with its field path, and each has a control: the same registry with that one field intact loads, so a reader that refused everything would fail the controls.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.core import pins
from rediacc_ci.infra import renet_pkg_matrix

if TYPE_CHECKING:
    import pathlib

LEAP = "os:opensuse-16.0-ceph"


def test_the_real_registry_loads_and_names_the_leap_sites() -> None:
    reg = pins.load()
    assert len(reg.entries) > 10
    assert pins.site_labels(LEAP) == (
        'pkg/infra/cephpkg/cephpkg.go hostPins["opensuse-16.0"]',
        ".ceph-image-pin host.opensuse-16.0",
        "cmd/renet/ceph_install_profile_test.go",
    )


def test_renet_pkg_matrix_reads_its_pin_sites_from_the_registry() -> None:
    assert pins.site_labels(LEAP) == renet_pkg_matrix.PIN_SITES


def test_an_unknown_entry_is_refused_by_name() -> None:
    with pytest.raises(pins.PinsError, match="no entry 'os:nope'"):
        pins.site_labels("os:nope")


def _valid() -> dict[str, object]:
    return {
        "version": 1,
        "entries": [
            {
                "id": "os:x",
                "kind": "leaf",
                "name": "x",
                "driver": "os-ceph-host",
                "sites": [
                    {
                        "repo": ".",
                        "file": "a.go",
                        "role": "version",
                        "expect": 1,
                        "label": "a.go hostPins",
                    }
                ],
            }
        ],
    }


def _site(r: dict[str, object]) -> dict[str, object]:
    entries = r["entries"]
    assert isinstance(entries, list)
    site = entries[0]["sites"][0]
    assert isinstance(site, dict)
    return site


def _entry(r: dict[str, object]) -> dict[str, object]:
    entries = r["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    return entry


BREAKS = [
    ("version", lambda r: r.update(version=2), "version:"),
    ("entries", lambda r: r.update(entries=[]), "entries:"),
    ("id", lambda r: _entry(r).pop("id"), "entries[0].id:"),
    ("kind", lambda r: _entry(r).update(kind="tree"), "(os:x).kind:"),
    ("sites", lambda r: _entry(r).update(sites={}), "(os:x).sites:"),
    ("expect zero", lambda r: _site(r).update(expect=0), "sites[0].expect:"),
    ("expect bool", lambda r: _site(r).update(expect=True), "sites[0].expect:"),
    ("file", lambda r: _site(r).update(file=""), "sites[0].file:"),
    ("label", lambda r: _site(r).update(label=7), "sites[0].label:"),
]


def test_the_valid_fixture_parses_control() -> None:
    reg = pins.parse(_valid())
    assert reg.entry("os:x").sites[0].label == "a.go hostPins"


def test_a_label_defaults_to_the_file() -> None:
    raw = _valid()
    _site(raw).pop("label")
    assert pins.parse(raw).entry("os:x").sites[0].label == "a.go"


@pytest.mark.parametrize(("name", "mutate", "field"), BREAKS, ids=[b[0] for b in BREAKS])
def test_a_malformed_field_is_refused_by_its_path(name: str, mutate, field: str) -> None:
    raw = copy.deepcopy(_valid())
    mutate(raw)
    with pytest.raises(pins.PinsError) as exc:
        pins.parse(raw)
    assert field in str(exc.value), (name, str(exc.value))


def test_a_duplicate_id_is_refused() -> None:
    raw = _valid()
    entries = raw["entries"]
    assert isinstance(entries, list)
    entries.append(copy.deepcopy(entries[0]))
    with pytest.raises(pins.PinsError, match="is a duplicate"):
        pins.parse(raw)


def test_load_names_the_file_when_it_is_not_json(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "pins.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(pins.PinsError, match="not JSON"):
        pins.load(bad)
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_valid()), encoding="utf-8")
    assert pins.load(good).entry("os:x").id == "os:x"
