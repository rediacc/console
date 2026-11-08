"""`rediacc_ci.ops.r2_bucket_copy`: endpoint and jurisdiction, the delta plan, parity, the summary, and the copy driven against a fake R2 (no live bucket call)."""

from __future__ import annotations

import datetime
import json

import pytest

from rediacc_ci.deploy import r2_promote
from rediacc_ci.ops import r2_bucket_copy as bc

T = datetime.datetime(2026, 11, 8, 12, 0, tzinfo=datetime.UTC)
HOUR = datetime.timedelta(hours=1)
BASE = "https://abc123.r2.cloudflarestorage.com"


def obj(rel: str, size: int = 1, at: datetime.datetime = T) -> r2_promote.Obj:
    return r2_promote.Obj(rel, size, at)


def test_endpoint_for_inserts_the_jurisdiction_segment() -> None:
    assert bc.endpoint_for(BASE, None) == BASE
    assert bc.endpoint_for(BASE, "eu") == "https://abc123.eu.r2.cloudflarestorage.com"
    with pytest.raises(bc.CopyError):
        bc.endpoint_for("https://abc123.eu.r2.cloudflarestorage.com", "eu")
    with pytest.raises(bc.CopyError):
        bc.endpoint_for("https://example.com", "eu")


def test_check_bucket_rejects_odd_names() -> None:
    assert bc.check_bucket("configs-eu") == "configs-eu"
    with pytest.raises(bc.CopyError):
        bc.check_bucket("Bad/Name")


def test_plan_copy_is_the_delta() -> None:
    src = [obj("a"), obj("b", 2), obj("c")]
    dst = [obj("a", 1, T + HOUR), obj("b", 3), obj("c", 1, T - HOUR)]
    assert [o.rel for o in bc.plan_copy(src, dst)] == ["b", "c"]
    assert bc.plan_copy(src, src) == []


def test_parity_reports_count_size_and_keys() -> None:
    same = [obj("a", 2), obj("b", 3)]
    assert bc.parity(same, list(same)) == []
    text = "\n".join(bc.parity(same, [obj("a", 9), obj("z", 3)]))
    assert "missing in destination: b" in text
    assert "extra in destination: z" in text
    assert "size differs: a" in text
    assert "total size" in text
    assert bc.parity(same, [obj("a", 2)])[0].startswith("object count")


def test_summarize_reports_objects_over_the_copy_limit() -> None:
    big = obj("big.bin", r2_promote.COPY_OBJECT_MAX_BYTES + 1)
    summary = bc.summarize("b", [obj("a", 5), big])
    assert summary["objects"] == 2
    assert summary["over_copy_limit"] == [{"key": "big.bin", "bytes": big.size}]
    assert summary["largest"] == {"key": "big.bin", "bytes": big.size}
    assert bc.summarize("e", [])["largest"] is None


def test_parse_buckets() -> None:
    assert bc.parse_buckets(json.dumps({"Buckets": [{"Name": "b"}, {"Name": "a"}]})) == ["a", "b"]
    assert bc.parse_buckets("") == []


def test_copy_argv_preserves_metadata_and_names_both_buckets() -> None:
    argv = r2_promote.copy_argv(
        "k.mp4",
        "k.mp4",
        "https://x",
        bucket="media",
        src_bucket="rediacc-www-media",
        preserve_metadata=True,
    )
    assert argv[argv.index("--bucket") + 1] == "media"
    assert argv[argv.index("--copy-source") + 1] == "rediacc-www-media/k.mp4"
    assert argv[argv.index("--metadata-directive") + 1] == "COPY"
    assert "--cache-control" not in argv
    assert "--content-type" not in argv


def test_promote_argv_defaults_are_unchanged() -> None:
    argv = r2_promote.copy_argv("a/edge/x.json", "a/stable/x.json", "https://x")
    assert argv[argv.index("--bucket") + 1] == r2_promote.BUCKET
    assert argv[argv.index("--metadata-directive") + 1] == "REPLACE"
    listing = r2_promote.list_argv("p/", "https://x")
    assert listing[listing.index("--bucket") + 1] == r2_promote.BUCKET
    other = r2_promote.list_argv("p/", "https://x", "other")
    assert other[other.index("--bucket") + 1] == "other"


class FakeR2:
    """Buckets as dicts of key -> (size, modified); `Transfers` is faked at its listing and copy seams."""

    def __init__(self, buckets: dict[str, dict[str, tuple[int, datetime.datetime]]]) -> None:
        self.buckets = buckets
        self.copies: list[tuple[str, str, str, bool]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def list_tree(run: r2_promote.Transfers, _prefix: str) -> list[r2_promote.Obj]:
            return sorted(
                (r2_promote.Obj(k, s, m) for k, (s, m) in self.buckets[run.bucket].items()),
                key=lambda o: o.rel,
            )

        def copy_all(run: r2_promote.Transfers, pairs: list[tuple[str, str]]) -> None:
            for src_key, dst_key in pairs:
                assert run.src_bucket is not None
                self.copies.append((run.src_bucket, run.bucket, dst_key, run.preserve_metadata))
                size = self.buckets[run.src_bucket][src_key][0]
                self.buckets[run.bucket][dst_key] = (size, T + HOUR)

        monkeypatch.setattr(r2_promote.Transfers, "list_tree", list_tree)
        monkeypatch.setattr(r2_promote.Transfers, "copy_all", copy_all)


def test_copy_is_rerunnable_and_copies_only_the_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeR2({"src": {"a": (1, T), "b": (2, T)}, "dst": {"a": (1, T + 2 * HOUR)}})
    fake.install(monkeypatch)
    assert bc.copy(BASE, "src", "dst") == 0
    assert fake.copies == [("src", "dst", "b", True)]
    assert bc.copy(BASE, "src", "dst") == 0
    assert len(fake.copies) == 1


def test_dry_run_copies_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeR2({"src": {"a": (1, T)}, "dst": {}})
    fake.install(monkeypatch)
    assert bc.copy(BASE, "src", "dst", dry_run=True) == 0
    assert fake.copies == []


def test_copy_refuses_an_empty_source_and_an_oversize_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeR2({"src": {}, "dst": {}}).install(monkeypatch)
    with pytest.raises(bc.CopyError, match="VACUOUS"):
        bc.copy(BASE, "src", "dst")
    fake = FakeR2({"src": {"big": (r2_promote.COPY_OBJECT_MAX_BYTES + 1, T)}, "dst": {}})
    fake.install(monkeypatch)
    with pytest.raises(r2_promote.PromoteError):
        bc.copy(BASE, "src", "dst")
    assert fake.copies == []


def test_verify_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeR2({"src": {"a": (1, T)}, "dst": {"a": (1, T)}}).install(monkeypatch)
    assert bc.verify(BASE, "src", "dst") == 0
    FakeR2({"src": {"a": (1, T)}, "dst": {}}).install(monkeypatch)
    assert bc.verify(BASE, "src", "dst") == 1


def test_same_bucket_is_refused() -> None:
    with pytest.raises(bc.CopyError):
        bc.verify(BASE, "x", "x")


def test_main_inventory_with_jurisdiction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    FakeR2({"configs-eu": {"a": (4, T)}}).install(monkeypatch)
    argv = ["--inventory", "--bucket", "configs-eu", "--jurisdiction", "eu", "--endpoint", BASE]
    assert bc.main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["endpoint"] == "https://abc123.eu.r2.cloudflarestorage.com"
    assert report["buckets"][0]["bytes"] == 4


def test_main_needs_from_and_to() -> None:
    with pytest.raises(SystemExit):
        bc.main(["--copy", "--endpoint", BASE])
