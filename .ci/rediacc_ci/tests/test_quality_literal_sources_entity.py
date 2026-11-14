"""R6 of check:ci-literal-sources: the contracting entity's values, read from the projection at run time, are findings in code and prose alike."""

from __future__ import annotations

import pathlib
import unicodedata

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import literal_sources as ls

ROOT = pathlib.Path(paths.repo_root())


@pytest.fixture(scope="module")
def policy() -> ls.EntityPolicy:
    return ls.load_policy(ROOT).entity


@pytest.fixture(scope="module")
def entity(policy: ls.EntityPolicy) -> dict[str, str]:
    return ls.load_entity(ROOT, policy)


@pytest.fixture(scope="module")
def needles(entity: dict[str, str], policy: ls.EntityPolicy) -> list[ls.EntityNeedle]:
    return ls.entity_needles(entity, policy)


def test_every_identifying_field_is_a_needle(
    entity: dict[str, str], policy: ls.EntityPolicy, needles: list[ls.EntityNeedle]
) -> None:
    fields = {n.field for n in needles}
    assert set(ls.ENTITY_REQUIRED) <= fields
    assert fields - {"spelling"} == set(entity) - set(policy.skip_fields)
    assert set(policy.skip_fields) <= set(entity), "a skip_fields row names no projected field"


@pytest.mark.parametrize(
    "template",
    [
        '    "party": "Rediacc, registry code {code}",',  # a translation
        "| Vendors | (1) registry {code}, software licence |",  # a markdown post
        "export const code = '{code}';",  # a .ts string
        "# the registry code is {code}",  # a comment: prose counts
    ],
)
def test_registry_code_fires_in_every_context(
    template: str, entity: dict[str, str], needles: list[ls.EntityNeedle]
) -> None:
    line = template.format(code=entity["registryCode"])
    assert "registryCode" in ls.entity_fields_in(line, needles)


def test_registry_code_inside_a_longer_number_is_silent(
    entity: dict[str, str], needles: list[ls.EntityNeedle]
) -> None:
    assert ls.entity_fields_in("id 9%s1" % entity["registryCode"], needles) == []


def test_legal_name_spellings(entity: dict[str, str], needles: list[ls.EntityNeedle]) -> None:
    name = entity["legalName"]
    for spelling in ls.entity_spellings(name):
        assert "legalName" in ls.entity_fields_in("sold by %s." % spelling, needles), spelling
    assert unicodedata.normalize("NFD", name) in ls.entity_spellings(name)
    # flush against CJK text, as the ja/ko/zh catalogs write it
    assert "legalName" in ls.entity_fields_in("と%s（" % name, needles)


def test_french_ou_is_not_the_legal_form(
    entity: dict[str, str], needles: list[ls.EntityNeedle]
) -> None:
    brand = entity["legalName"].rsplit(" ", 1)[0]
    assert ls.entity_fields_in("%s ou Hetzner" % brand, needles) == []


def test_a_short_unskipped_value_is_refused(
    entity: dict[str, str], policy: ls.EntityPolicy
) -> None:
    with pytest.raises(ls.RefusalError, match="vatNumber"):
        ls.entity_needles({**entity, "vatNumber": "EE1"}, policy)


def test_a_projection_without_a_legal_name_is_refused(
    entity: dict[str, str], policy: ls.EntityPolicy
) -> None:
    with pytest.raises(ls.RefusalError, match="legalName"):
        ls.entity_needles({k: v for k, v in entity.items() if k != "legalName"}, policy)


def test_the_gate_source_carries_no_entity_value(needles: list[ls.EntityNeedle]) -> None:
    text = (ROOT / ".ci/rediacc_ci/quality/literal_sources.py").read_text(encoding="utf-8")
    hits = [
        (i, ls.entity_fields_in(line, needles))
        for i, line in enumerate(text.splitlines(), 1)
        if ls.entity_fields_in(line, needles)
    ]
    assert hits == []


def test_controls_pass() -> None:
    assert ls.selftest() is False


def test_a_value_past_column_20000_of_a_long_line_is_found(
    entity: dict[str, str], needles: list[ls.EntityNeedle]
) -> None:
    """238d8840.1: the record is scanned whole, so a minified bundle cannot hide the entity after a cut."""
    value = entity["registryCode"]
    raw = ("x" * 30000 + " registry %s " % value).encode()
    assert "registryCode" in ls.entity_fields_in_record(raw, needles)
    # Control: the same line without the value is clean.
    assert ls.entity_fields_in_record(b"x" * 30000, needles) == []


class _Grep:
    """A stand-in for the consumer grep: one `-z -n` record, path NUL line NUL text."""

    record = b""

    def __init__(self, _root: pathlib.Path, *_args: str) -> None:
        pass

    def result(self) -> bytes:
        return self.record


@pytest.mark.parametrize("carries", [True, False])
def test_entity_findings_reads_a_long_line_whole_at_the_call_site(
    monkeypatch: pytest.MonkeyPatch, entity: dict[str, str], carries: bool
) -> None:
    """c473373f.2: driven through `entity_findings`, so a `[:20000]` cut put back at its call site fails here. The control line, without the value, stays silent."""
    tail = (" registry %s " % entity["registryCode"]) if carries else " registry none "
    _Grep.record = b"src/minified.js\x001\x00" + ("x" * 30000 + tail).encode() + b"\n"
    monkeypatch.setattr(ls, "GitCall", _Grep)
    policy = ls.load_policy(ROOT)
    own = {policy.entity.source, *policy.entity.projections}
    findings, _stats = ls.entity_findings(ROOT, policy, own, set(), [])
    r6 = [f for f in findings if f.rule == "R6" and f.path == "src/minified.js"]
    assert bool(r6) is carries
    if carries:
        assert "registryCode" in r6[0].message
