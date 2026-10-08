"""wl_models loads the well-known reader lazily; a reader whose exec raises must not stay cached as a half-initialised module (bfadfd55.3)."""

from __future__ import annotations

import sys

import pytest

from rediacc_hooks.tests import wlfix

M = wlfix.import_wl("wl_models")


def test_a_failed_reader_import_leaves_no_module_in_the_cache(tmp_path, monkeypatch):
    bad = tmp_path / "well_known.py"
    bad.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setattr(M, "_reader_path", lambda: bad)
    monkeypatch.delitem(sys.modules, M._NAME, raising=False)
    with pytest.raises(RuntimeError, match="boom"):
        M._load()
    assert M._NAME not in sys.modules
    # the next call retries instead of returning the broken module
    with pytest.raises(RuntimeError, match="boom"):
        M._load()


def test_control_a_good_reader_is_cached(tmp_path, monkeypatch):
    good = tmp_path / "well_known.py"
    good.write_text("CLAUDE_HAIKU_MODEL = 'x'\n", encoding="utf-8")
    monkeypatch.setattr(M, "_reader_path", lambda: good)
    monkeypatch.delitem(sys.modules, M._NAME, raising=False)
    try:
        assert M._load().CLAUDE_HAIKU_MODEL == "x"
        assert M._NAME in sys.modules
    finally:
        sys.modules.pop(M._NAME, None)
