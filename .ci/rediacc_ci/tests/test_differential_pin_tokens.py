"""`differential.pin_fold`/`pin_unfold`: a toolchain pin bump needs no golden edit (worklist #df210b76).

The 2.48.0 to 2.49.0 nfpm bump (08f98901) turned eight ensure-nfpm cases red because their retired-twin goldens froze the pin literally. The goldens now hold `<PIN:NFPM_VERSION>`, and these cases prove a fake bump to 9.9.9 reads back as 9.9.9 with no golden touched, and that the same golden without the fold would not.
"""

from __future__ import annotations

import pytest

from rediacc_ci.tests import differential as diff

NFPM_TWIN = ".ci/scripts/build/ensure-nfpm.sh"
NFPM_STEM = "build.ensure-nfpm"
TOKEN = diff.pin_token("NFPM_VERSION")


@pytest.fixture
def bumped(tmp_path, monkeypatch) -> None:
    """A `constants.sh` that says the nfpm pin is 9.9.9, standing in for the repo's."""
    constants = tmp_path / "constants.sh"
    constants.write_text('readonly OTHER="1"\nreadonly NFPM_VERSION="9.9.9"\n', encoding="utf-8")
    monkeypatch.setattr(diff, "CONSTANTS_SH", constants)


def _token_case() -> str:
    """The key of a real nfpm golden record whose stderr carries the pin token."""
    _header, _silent, records = diff.load_golden(NFPM_TWIN)
    for key, row in records.items():
        if TOKEN in row.get("err", ""):
            return key
    raise AssertionError(
        "no %s record holds %s: the goldens lost their pin token" % (NFPM_STEM, TOKEN)
    )


def test_the_nfpm_goldens_hold_the_token_not_a_version():
    for stem in ("build.ensure-nfpm", "test.proxies.proxy-ensure-nfpm"):
        text = (diff.GOLDEN_DIR / ("%s.jsonl" % stem)).read_text(encoding="utf-8")
        assert TOKEN in text
        assert diff.pin_values(("NFPM_VERSION",))["NFPM_VERSION"] not in text


@pytest.mark.usefixtures("bumped")
def test_a_fake_pin_bump_reads_the_golden_back_with_the_new_pin():
    _rc, _out, err = diff.golden_answer(NFPM_TWIN, _token_case())
    assert "ensure-nfpm: fetching nfpm 9.9.9 for x86_64" in err
    assert TOKEN not in err


@pytest.mark.usefixtures("bumped")
def test_control_without_the_fold_the_same_golden_does_not_match_the_bump(monkeypatch):
    monkeypatch.setattr(diff, "PIN_TOKENS", {})
    _rc, _out, err = diff.golden_answer(NFPM_TWIN, _token_case())
    assert "fetching nfpm 9.9.9" not in err
    assert TOKEN in err


@pytest.mark.usefixtures("bumped")
def test_record_folds_the_current_pin_and_compare_restores_it():
    recorded = diff.pin_fold(NFPM_STEM, "ensure-nfpm: fetching nfpm 9.9.9 for x86_64\n")
    assert recorded == "ensure-nfpm: fetching nfpm %s for x86_64\n" % TOKEN
    assert diff.pin_unfold(NFPM_STEM, recorded) == "ensure-nfpm: fetching nfpm 9.9.9 for x86_64\n"


def test_only_a_whole_version_folds():
    pins = {"NFPM_VERSION": "2.49.0"}
    text = "v2.49.0 '2.49.0' 12.49.0 2.49.0.1 2.49.01 2.49.0."
    assert diff.pin_fold(NFPM_STEM, text, pins) == "v%s '%s' 12.49.0 2.49.0.1 2.49.01 %s." % (
        TOKEN,
        TOKEN,
        TOKEN,
    )


@pytest.mark.usefixtures("bumped")
def test_a_stem_without_pins_is_never_rewritten():
    text = "nfpm 9.9.9 and %s" % TOKEN
    assert diff.pin_fold("ci.assert-job-succeeded", text) == text
    assert diff.pin_unfold("ci.assert-job-succeeded", text) == text


def test_a_listed_pin_missing_from_constants_is_an_error(tmp_path):
    constants = tmp_path / "constants.sh"
    constants.write_text('readonly OTHER="1"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="NFPM_VERSION"):
        diff.pin_values(("NFPM_VERSION",), constants)
