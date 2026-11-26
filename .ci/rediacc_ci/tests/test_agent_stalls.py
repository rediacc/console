"""agent_stalls: band waits, fast turns, deaths, concurrency and context buckets over fixture transcripts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rediacc_ci.ops import agent_stalls

if TYPE_CHECKING:
    from pathlib import Path

T0 = datetime(2026, 11, 25, 1, 0, 0, tzinfo=UTC)
SINCE = T0 - timedelta(hours=1)
UNTIL = T0 + timedelta(hours=2)
SESSION = "sess"


def _stamp(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _user(seconds: float) -> dict:
    return {
        "type": "user",
        "timestamp": _stamp(seconds),
        "message": {"role": "user", "content": "go"},
    }


def _assistant(
    seconds: float, ident: str, context: int = 1000, model: str = "claude-sonnet-5-5"
) -> dict:
    usage = {
        "input_tokens": 2,
        "cache_creation_input_tokens": context - 2,
        "cache_read_input_tokens": 0,
    }
    return {
        "type": "assistant",
        "timestamp": _stamp(seconds),
        "message": {"id": ident, "model": model, "usage": usage, "content": []},
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _writer(tmp_path: Path, name: str, rows: list[dict]) -> None:
    _write(tmp_path / SESSION / "subagents" / f"{name}.jsonl", rows)


def _report(tmp_path: Path) -> dict:
    files = agent_stalls.discover(tmp_path, SESSION)
    return agent_stalls.analyze(files, SINCE, UNTIL)["roles"]["writer"]


def test_band_wait_counts_as_a_stall(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(190, "m1")])
    total = _report(tmp_path)["total"]
    assert total["requests"] == 1
    assert total["band_waits"] == 1
    assert total["band_median_s"] == 190.0
    assert total["stall_rate"] == 1.0
    assert total["wait_hours"] == round(190 / 3600, 2)


def test_a_non_object_json_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / SESSION / "subagents" / "a.jsonl"
    _write(path, [_user(0), _assistant(190, "m1")])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("[]\n1\n")
    assert _report(tmp_path)["total"]["band_waits"] == 1


def test_fast_turn_is_not_a_stall(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(2, "m1"), _user(3), _assistant(5, "m2")])
    total = _report(tmp_path)["total"]
    assert total["requests"] == 2
    assert total["band_waits"] == 0
    assert total["stall_rate"] == 0.0
    assert total["band_median_s"] is None


def test_streamed_rows_of_one_message_are_one_request(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(190, "m1"), _assistant(191, "m1")])
    total = _report(tmp_path)["total"]
    assert total["requests"] == 1
    assert total["band_waits"] == 1


def test_a_wait_past_the_band_is_wait_time_but_not_a_band_stall(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(900, "m1")])
    total = _report(tmp_path)["total"]
    assert total["band_waits"] == 0
    assert total["wait_hours"] == 0.25


def test_death_is_a_transcript_ending_on_an_unanswered_user_row(tmp_path: Path) -> None:
    _writer(tmp_path, "dead", [_user(0), _assistant(2, "m1"), _user(3)])
    _writer(tmp_path, "alive", [_user(0), _assistant(2, "m2")])
    total = _report(tmp_path)["total"]
    assert total["deaths"] == 1
    assert total["transcripts"] == 2


def test_two_overlapping_writers_land_in_the_two_to_three_bucket(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(10, "a1"), _user(11), _assistant(200, "a2")])
    _writer(tmp_path, "b", [_user(5), _assistant(190, "b1")])
    buckets = _report(tmp_path)["by_concurrent_writers"]
    assert buckets["2-3"]["requests"] == 2
    assert buckets["2-3"]["band_waits"] == 1
    assert buckets["1"]["requests"] == 1


def test_a_lone_writer_is_concurrency_one(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(190, "a1")])
    buckets = _report(tmp_path)["by_concurrent_writers"]
    assert list(buckets) == ["1"]


def test_context_size_splits_large_from_small(tmp_path: Path) -> None:
    rows = [
        _user(0),
        _assistant(190, "big", context=150_000),
        _user(191),
        _assistant(193, "small", context=1_000),
    ]
    _writer(tmp_path, "a", rows)
    buckets = _report(tmp_path)["by_context"]
    assert buckets[">=100k"]["band_waits"] == 1
    assert buckets["<40k"]["band_waits"] == 0
    assert buckets["<40k"]["requests"] == 1


def test_models_are_reported_separately(tmp_path: Path) -> None:
    _writer(tmp_path, "a", [_user(0), _assistant(190, "m1", model="claude-opus-5-5")])
    _writer(tmp_path, "b", [_user(0), _assistant(2, "m2", model="claude-sonnet-5-5")])
    models = _report(tmp_path)["models"]
    assert models["claude-opus-5-5"]["band_waits"] == 1
    assert models["claude-sonnet-5-5"]["band_waits"] == 0


def test_requests_outside_the_window_are_ignored(tmp_path: Path) -> None:
    far = 10 * 3600
    _writer(tmp_path, "a", [_user(far), _assistant(far + 190, "late")])
    files = agent_stalls.discover(tmp_path, SESSION)
    assert agent_stalls.analyze(files, SINCE, UNTIL)["roles"]["writer"]["total"]["requests"] == 0


def test_main_prints_json(tmp_path: Path, capsys) -> None:
    _write(tmp_path / f"{SESSION}.jsonl", [_user(0), _assistant(2, "lead1")])
    _writer(tmp_path, "a", [_user(0), _assistant(190, "m1")])
    args = [
        "--since",
        SINCE.isoformat(),
        "--until",
        UNTIL.isoformat(),
        "--session",
        SESSION,
        "--project",
        str(tmp_path),
        "--json",
    ]
    assert agent_stalls.main(args) == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["roles"]["writer"]["total"]["band_waits"] == 1
    assert report["roles"]["lead"]["total"]["requests"] == 1
    assert out.err == ""


def test_main_rejects_an_inverted_window(tmp_path: Path, capsys) -> None:
    args = ["--since", UNTIL.isoformat(), "--until", SINCE.isoformat(), "--project", str(tmp_path)]
    assert agent_stalls.main(args) == 2
    assert "after --since" in capsys.readouterr().err
