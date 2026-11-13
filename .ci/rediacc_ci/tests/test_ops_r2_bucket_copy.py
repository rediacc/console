"""`rediacc_ci.ops.r2_bucket_copy`: endpoint and jurisdiction, the delta plan, parity, the summary, and the copy driven against a fake R2 (no live bucket call)."""

from __future__ import annotations

import datetime
import json

import pytest

from rediacc_ci.deploy import r2_promote
from rediacc_ci.ops import r2_bucket_copy as bc
from rediacc_ci.well_known import MEDIA_BUCKET

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
        bucket=MEDIA_BUCKET,
        src_bucket="rediacc-www-media",
        preserve_metadata=True,
    )
    assert argv[argv.index("--bucket") + 1] == MEDIA_BUCKET
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


def test_copy_source_carries_the_raw_key_for_aws_cli_to_encode() -> None:
    """botocore percent-encodes a string CopySource key itself; pre-encoding here would double-encode (`%2520`)."""
    for key in ("a+b.txt", "a%20b", "with space.txt", "café/日本.bin"):
        argv = r2_promote.copy_argv(key, key, "https://x", bucket="d", src_bucket="s")
        assert argv[argv.index("--copy-source") + 1] == "s/" + key
        assert argv[argv.index("--key") + 1] == key


def test_copy_refuses_a_key_that_aws_cli_would_read_as_a_version_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeR2({"src": {"a?versionId=abc": (1, T)}, "dst": {}})
    fake.install(monkeypatch)
    with pytest.raises(bc.CopyError, match="versionId"):
        bc.copy(BASE, "src", "dst")
    assert fake.copies == []


def test_parity_compares_single_part_etags_only() -> None:
    def tagged(etag: str) -> list[r2_promote.Obj]:
        return [r2_promote.Obj("a", 4, T, etag)]

    assert bc.parity(tagged("aa"), tagged("aa")) == []
    assert any("etag differs: a" in line for line in bc.parity(tagged("aa"), tagged("bb")))
    assert bc.parity(tagged("aa-3"), tagged("bb-3")) == []
    assert bc.parity(tagged(""), tagged("bb")) == []


def test_plan_copy_does_not_see_a_metadata_only_change() -> None:
    """The documented limit: same size and a newer destination is skipped."""
    assert bc.plan_copy([obj("a", 4, T)], [obj("a", 4, T + HOUR)]) == []


def test_plan_copy_recopies_a_same_size_change_with_a_different_single_part_etag() -> None:
    def pair(rel: str, src_tag: str, dst_tag: str) -> tuple[r2_promote.Obj, r2_promote.Obj]:
        return r2_promote.Obj(rel, 4, T, src_tag), r2_promote.Obj(rel, 4, T + HOUR, dst_tag)

    pairs = [pair("a", "aa", "bb"), pair("b", "aa-3", "bb-3"), pair("c", "aa", "aa")]
    assert [o.rel for o in bc.plan_copy([p[0] for p in pairs], [p[1] for p in pairs])] == ["a"]


def test_copy_argv_refuses_a_key_that_aws_cli_would_read_as_a_version_id() -> None:
    with pytest.raises(ValueError, match="versionId"):
        r2_promote.copy_argv("cli/x?versionId=abc", "cli/y", "https://e")


def test_parse_buckets_malformed_reply_is_a_copy_error() -> None:
    for bad in ("{not json", "[1, 2]", '{"Buckets": [{"x": 1}]}'):
        with pytest.raises(bc.CopyError, match="unreadable"):
            bc.parse_buckets(bad)


def test_main_logs_a_malformed_list_buckets_reply_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Proc:
        returncode = 0
        stdout = b"<html>"
        stderr = b""

    monkeypatch.setattr(bc.awscli, "run", lambda *_a, **_k: Proc())
    assert bc.main(["--inventory", "--endpoint", BASE]) == 1


# --- relocate across jurisdictions (PLAN-d1-eu-jurisdiction W2) ------------------------------------

EU = "https://abc123.eu.r2.cloudflarestorage.com"


class FakeEndpoints:
    """Buckets per (endpoint, bucket): key -> (bytes, get-object head, modified, etag). The listing, the GET and the PUT are faked at their seams."""

    def __init__(self, buckets: dict[tuple[str, str], dict[str, tuple]]) -> None:
        self.buckets = buckets
        self.puts: list[tuple[str, str, str, dict]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def list_tree(run: r2_promote.Transfers, _prefix: str) -> list[r2_promote.Obj]:
            objects = self.buckets[(run.endpoint, run.bucket)]
            return sorted(
                (r2_promote.Obj(k, len(v[0]), v[2], v[3]) for k, v in objects.items()),
                key=lambda o: o.rel,
            )

        def fetch_object(endpoint: str, bucket: str, key: str, path: str) -> dict:
            body, head, _m, _e = self.buckets[(endpoint, bucket)][key]
            with open(path, "wb") as handle:
                handle.write(body)
            return dict(head)

        def store_object(endpoint: str, bucket: str, key: str, path: str, head: dict) -> None:
            with open(path, "rb") as handle:
                body = handle.read()
            self.puts.append((endpoint, bucket, key, head))
            self.buckets[(endpoint, bucket)][key] = (body, dict(head), T + HOUR, "")

        monkeypatch.setattr(r2_promote.Transfers, "list_tree", list_tree)
        monkeypatch.setattr(bc, "fetch_object", fetch_object)
        monkeypatch.setattr(bc, "store_object", store_object)


class FakeSettingsApi:
    """The Cloudflare bucket-settings API per (jurisdiction, bucket); `ignore_writes` models an API that accepts a PUT and changes nothing."""

    def __init__(
        self, state: dict[tuple[str, str], dict[str, list]], *, ignore_writes: bool = False
    ) -> None:
        self.state = state
        self.ignore_writes = ignore_writes
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, method: str, url: str, headers, body):
        jur = headers.get(bc.JURISDICTION_HEADER, "default")
        path = url.split("/accounts/acct", 1)[1]
        self.calls.append((method, jur, path))
        parts = path.strip("/").split("/")
        bucket = parts[2]
        kind = parts[3] if parts[0] == "r2" else "notifications"
        empty = {"cors": [], "lifecycle": [], "notifications": []}
        current = self.state.setdefault((jur, bucket), empty)
        if method == "GET":
            if kind == "cors" and not current["cors"]:
                return 404, {"success": False}
            key = "queues" if kind == "notifications" else "rules"
            return 200, {"success": True, "result": {key: current[kind]}}
        if not self.ignore_writes:
            if method == "DELETE":
                current[kind] = []
            elif kind == "notifications":
                current["notifications"].append({"queueId": parts[5], "rules": body["rules"]})
            else:
                current[kind] = body["rules"]
        return 200, {"success": True, "result": {}}


HEAD = {"ContentType": "application/json", "CacheControl": "no-store", "Metadata": {"owner": "o1"}}
SOURCE_SETTINGS = {
    "cors": [{"allowed": {"origins": ["https://a"], "methods": ["GET"]}}],
    "lifecycle": [{"id": "abort", "enabled": True}],
    "notifications": [
        {
            "queueId": "q1",
            "rules": [
                {
                    "prefix": "p/",
                    "actions": ["PutObject", "CopyObject"],
                    "ruleId": "r1",
                    "createdAt": "x",
                }
            ],
        }
    ],
}


def relocate_fixture(monkeypatch: pytest.MonkeyPatch, *, dst_objects: dict | None = None):
    fake = FakeEndpoints(
        {
            (BASE, "configs-bench"): {
                "a.json": (b'{"a":1}', HEAD, T, "e1-2"),
                "dir/b.bin": (b"\x00\x01", {}, T, "e2-2"),
            },
            (EU, "configs-bench"): dict(dst_objects or {}),
        }
    )
    fake.install(monkeypatch)
    api = FakeSettingsApi({("default", "configs-bench"): json.loads(json.dumps(SOURCE_SETTINGS))})
    return fake, api, bc.Settings(api, {}, "acct")


def _relocate(settings: bc.Settings, *, write: bool) -> int:
    return bc.relocate(
        BASE, "configs-bench", EU, "configs-bench", settings, (None, "eu"), write=write
    )


def test_relocate_without_write_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, api, settings = relocate_fixture(monkeypatch)
    assert _relocate(settings, write=False) == 0
    out = capsys.readouterr().out
    assert fake.puts == []
    assert [c for c in api.calls if c[0] != "GET"] == []
    assert "2 of 2 object(s) to move" in out
    assert "bucket settings differ: cors (source 1, destination 0)" in out
    assert "dry run, nothing written" in out


def test_relocate_streams_every_object_with_its_metadata_and_copies_the_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, api, settings = relocate_fixture(monkeypatch)
    assert _relocate(settings, write=True) == 0, capsys.readouterr().err
    assert [(p[0], p[1], p[2]) for p in fake.puts] == [
        (EU, "configs-bench", "a.json"),
        (EU, "configs-bench", "dir/b.bin"),
    ]
    assert fake.puts[0][3] == HEAD
    assert fake.buckets[(EU, "configs-bench")]["dir/b.bin"][0] == b"\x00\x01"
    assert ("PUT", "eu", "/r2/buckets/configs-bench/cors") in api.calls
    assert ("PUT", "eu", "/event_notifications/r2/configs-bench/configuration/queues/q1") in (
        api.calls
    )
    assert not [c for c in api.calls if c[0] != "GET" and c[1] != "eu"], "the source is not written"
    assert "bucket settings equal" in capsys.readouterr().out
    # Re-runnable: a second run moves nothing and writes no settings.
    fake.puts.clear()
    api.calls.clear()
    assert _relocate(settings, write=True) == 0
    assert fake.puts == []
    assert [c for c in api.calls if c[0] != "GET"] == []


def test_relocate_exits_1_when_the_settings_do_not_read_back_equal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, _api, _settings = relocate_fixture(monkeypatch)
    deaf = FakeSettingsApi(
        {("default", "configs-bench"): json.loads(json.dumps(SOURCE_SETTINGS))}, ignore_writes=True
    )
    assert _relocate(bc.Settings(deaf, {}, "acct"), write=True) == 1
    assert "bucket settings differ: cors" in capsys.readouterr().err
    assert len(fake.puts) == 2


def test_an_empty_source_cors_deletes_the_destination_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake, api, settings = relocate_fixture(monkeypatch)
    api.state[("default", "configs-bench")]["cors"] = []
    api.state[("eu", "configs-bench")] = {"cors": [{"x": 1}], "lifecycle": [], "notifications": []}
    assert _relocate(settings, write=True) == 0
    assert ("DELETE", "eu", "/r2/buckets/configs-bench/cors") in api.calls


def test_settings_compare_without_server_made_rule_fields() -> None:
    other = json.loads(json.dumps(SOURCE_SETTINGS))
    other["notifications"][0]["rules"][0].update(
        ruleId="r9", createdAt="y", actions=["CopyObject", "PutObject"]
    )
    assert bc.settings_differences(SOURCE_SETTINGS, other) == []
    other["lifecycle"] = []
    assert bc.settings_differences(SOURCE_SETTINGS, other) == [
        "bucket settings differ: lifecycle (source 1, destination 0)"
    ]


def test_verify_deep_catches_same_size_bytes_a_listing_cannot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    drifted = {
        "a.json": (b'{"a":2}', HEAD, T, "x-2"),
        "dir/b.bin": (b"\x00\x01", {}, T, "e2-2"),
    }
    relocate_fixture(monkeypatch, dst_objects=drifted)
    args = (BASE, "configs-bench", EU, "configs-bench", None, (None, "eu"))
    # The control: multipart ETags hide the drift from the listing.
    assert bc.verify_across(*args, deep=False) == 0
    assert bc.verify_across(*args, deep=True) == 1
    assert "sha256 differs: a.json" in capsys.readouterr().err


def test_put_object_argv_carries_the_head_and_the_metadata() -> None:
    head = {**HEAD, "ContentLength": 7, "ETag": '"e"', "Expires": "Thu, 01 Jan 2099 00:00:00 GMT"}
    argv = bc.put_object_argv(EU, "configs-bench", "a.json", "/t/o", head)
    assert argv[2:9] == [
        "put-object",
        "--bucket",
        "configs-bench",
        "--key",
        "a.json",
        "--body",
        "/t/o",
    ]
    assert argv[argv.index("--content-type") + 1] == "application/json"
    assert argv[argv.index("--cache-control") + 1] == "no-store"
    assert argv[argv.index("--expires") + 1] == "Thu, 01 Jan 2099 00:00:00 GMT"
    assert json.loads(argv[argv.index("--metadata") + 1]) == {"owner": "o1"}
    assert argv[argv.index("--endpoint-url") + 1] == EU
    assert "--content-length" not in argv
    bare = bc.put_object_argv(EU, "b", "k", "/t/o", {})
    assert "--metadata" not in bare
    assert "--content-type" not in bare
    get = bc.get_object_argv(BASE, "configs-bench", "a.json", "/t/o")
    assert get[2:8] == ["get-object", "--bucket", "configs-bench", "--key", "a.json", "/t/o"]


RELOCATE_ARGV = [
    "--relocate",
    "--from",
    "configs-bench",
    "--from-jurisdiction",
    "default",
    "--to",
    "configs-bench",
    "--to-jurisdiction",
    "eu",
    "--endpoint",
    BASE,
]


def test_main_relocate_reads_both_endpoints(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, api, _settings = relocate_fixture(monkeypatch)
    env = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
    assert bc.main(RELOCATE_ARGV, env=env, transport=api) == 0
    assert fake.puts == []
    assert bc.main([*RELOCATE_ARGV, "--write"], env=env, transport=api) == 0
    assert len(fake.puts) == 2
    capsys.readouterr()
    assert bc.main(["--verify", *RELOCATE_ARGV[1:], "--deep"], env=env, transport=api) == 0
    assert "sha256 equal per key, bucket settings equal" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--relocate", "--from", "a-b", "--to", "a-b", "--endpoint", BASE],
        [*RELOCATE_ARGV, "--jurisdiction", "eu"],
        ["--copy", *RELOCATE_ARGV[1:]],
        [*RELOCATE_ARGV[:7], "--endpoint", BASE],
    ],
)
def test_main_relocate_needs_both_jurisdictions_and_no_other(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        bc.main(argv, env={})


def test_relocate_needs_a_cloudflare_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, _api, _settings = relocate_fixture(monkeypatch)
    assert bc.main([*RELOCATE_ARGV, "--write"], env={}) == 1
    assert fake.puts == []


def test_the_same_bucket_on_the_same_endpoint_is_refused() -> None:
    with pytest.raises(bc.CopyError, match="same bucket"):
        bc.verify_across(BASE, "b-1", BASE, "b-1", None, (None, None), deep=True)


def test_a_failed_get_is_a_copy_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        returncode = 255
        stdout = b""
        stderr = b"An error occurred (NoSuchKey)"

    monkeypatch.setattr(bc.awscli, "run", lambda *_a, **_k: Proc())
    monkeypatch.setattr(bc.transfer_retry, "retried", lambda run, *_a, **_k: run()[0])
    with pytest.raises(bc.CopyError, match="get of b/k failed"):
        bc.fetch_object(EU, "b", "k", "/nonexistent/o")
