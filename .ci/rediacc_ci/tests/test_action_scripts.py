"""The step scripts that sit beside composite actions (app-token, bws-scrub, bws-secrets, free-disk-space).

They live next to their action.yml because callers sparse-check-out only the actions directory, so they cannot import `rediacc_ci`; the tests load them by path. Each case has a refusal and its control.
"""

import importlib.util
import types

import pytest

from rediacc_ci import paths

ACTIONS = paths.from_root(".github", "actions")


def load(rel: str) -> types.ModuleType:
    path = ACTIONS / rel
    assert path.is_file(), "action script missing: %s" % path
    spec = importlib.util.spec_from_file_location("action_" + path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preset_cd_grants_workflows_and_housekeeping_does_not() -> None:
    perms = load("app-token/perms.py")
    assert "perm-workflows=write" in perms.resolve("cd")
    assert "perm-workflows=write" not in perms.resolve("housekeeping")
    assert perms.resolve("  READONLY ") == ["perm-contents=read"]


@pytest.mark.parametrize("preset", ["ci", "push", "", "cd extra"])
def test_unknown_or_retired_presets_are_refused(preset: str) -> None:
    assert load("app-token/perms.py").resolve(preset) is None


def test_scrub_accepts_names_and_names_the_first_bad_line() -> None:
    scrub = load("bws-scrub/scrub.py")
    assert scrub.parse("BWS_A\n\n  BWS_B_1  \n") == (["BWS_A", "BWS_B_1"], None)
    assert scrub.parse("BWS_A\nbws_b\nBWS_C") == (["BWS_A"], "bws_b")
    assert scrub.parse("") == ([], None)


def test_resolve_maps_names_and_rejects_the_rest() -> None:
    resolve = load("bws-secrets/resolve.py")
    secrets = {"A": {"id": "uuid-a"}, "B": {"id": ""}}
    assert resolve.resolve("A\nA > A_EU # note\n\n", secrets) == [
        "uuid-a > A",
        "uuid-a > A_EU",
    ]
    for bad, text in (("absent", "NOPE"), ("empty id", "B"), ("malformed", "a b"), ("none", "")):
        with pytest.raises(resolve.ResolveError):
            resolve.resolve(text, secrets)
        assert bad


def test_prewarm_checksum_table_covers_every_triple_it_can_select() -> None:
    prewarm = load("bws-secrets/prewarm.py")
    selectable = {triple for triple, _ext in prewarm.TRIPLES.values()}
    for version, table in prewarm.CHECKSUMS.items():
        assert set(table) == selectable, version
        assert all(len(sha) == 64 for sha in table.values())


def test_free_disk_space_rejects_a_missing_mode(capsys: pytest.CaptureFixture[str]) -> None:
    fds = load("free-disk-space/free_disk_space.py")
    assert fds.main([]) == 2
    assert fds.main(["bogus"]) == 2
    assert "usage" in capsys.readouterr().out
