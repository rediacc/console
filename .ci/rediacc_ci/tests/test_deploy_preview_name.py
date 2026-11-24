"""Tests for `rediacc_ci.deploy.preview_name` (PLAN-preview-signer N1)."""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.deploy import preview_name as pn

if TYPE_CHECKING:
    from pathlib import Path

KEY_A = base64.b64encode(bytes(range(32))).decode()
KEY_B = base64.b64encode(bytes(range(1, 33))).decode()


def key(b64: str) -> bytes:
    return pn.load_key({pn.KEY_ENV: b64})


def test_word_list_invariants() -> None:
    words = pn.load_words()
    assert len(words) == 2048
    assert len(set(words)) == 2048
    for w in words:
        assert re.fullmatch(r"[a-z]+", w)
        assert not any(o != w and o.startswith(w) for o in words)


def test_name_shape_and_stability() -> None:
    first = pn.preview_name(123, key(KEY_A))
    assert first == pn.preview_name(123, key(KEY_A))
    assert pn.is_preview_worker(first)
    assert pn.is_preview_worker(first + "-signer")
    assert not pn.is_preview_worker("signer-eu")
    assert not pn.is_preview_worker("signer-bench-eu")
    assert not pn.is_preview_worker("pr-123")


def test_different_name_per_pr() -> None:
    names = {pn.preview_name(n, key(KEY_A)) for n in range(1, 500)}
    assert len(names) == 499


def test_different_name_per_key() -> None:
    assert pn.preview_name(7, key(KEY_A)) != pn.preview_name(7, key(KEY_B))


def test_match() -> None:
    k = key(KEY_A)
    name = pn.preview_name(42, k)
    assert pn.match_worker(name, [1, 42], k) == 42
    assert pn.match_worker(name + "-signer", [1, 42], k) == 42
    assert pn.match_worker(name, [1, 2], k) is None


@pytest.mark.parametrize("bad", ["", "not base64!", base64.b64encode(b"short").decode()])
def test_bad_key_refused(bad: str) -> None:
    with pytest.raises(pn.PreviewNameError):
        pn.load_key({pn.KEY_ENV: bad})


def test_missing_key_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(pn.KEY_ENV, raising=False)
    assert pn.main(["--pr", "5"]) == 1
    assert pn.KEY_ENV in capsys.readouterr().err


def test_cli_pr_and_match(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(pn.KEY_ENV, KEY_A)
    assert pn.main(["--pr", "9"]) == 0
    name = capsys.readouterr().out.strip()
    assert pn.main(["--match", name, "--open-prs", "9", "10"]) == 0
    assert capsys.readouterr().out.strip() == "9"
    assert pn.main(["--match", name + "-signer", "--open-prs", "10"]) == 1
    assert pn.main(["--match", "signer-eu", "--open-prs", "9"]) == 2


def test_match_key_error_exits_three_but_a_non_preview_name_exits_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(pn.KEY_ENV, raising=False)
    assert pn.main(["--match", "pv-a-b-c", "--open-prs", "9"]) == 3
    assert pn.main(["--match", "signer-eu", "--open-prs", "9"]) == 2
    monkeypatch.setenv(pn.KEY_ENV, "not-base64-32-bytes")
    assert pn.main(["--match", "pv-a-b-c", "--open-prs", "9"]) == 3


def test_a_trailing_newline_is_not_a_preview_worker() -> None:
    assert pn.is_preview_worker("pv-a-b-c")
    assert not pn.is_preview_worker("pv-a-b-c\n")


def test_an_unreadable_word_list_is_a_preview_name_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pn.load_words.cache_clear()
    monkeypatch.setattr(pn, "WORDS_FILE", tmp_path / "missing.txt")
    try:
        with pytest.raises(pn.PreviewNameError):
            pn.load_words()
        monkeypatch.setenv(pn.KEY_ENV, KEY_A)
        assert pn.main(["--match", "pv-a-b-c", "--open-prs", "9"]) == 3
    finally:
        pn.load_words.cache_clear()
