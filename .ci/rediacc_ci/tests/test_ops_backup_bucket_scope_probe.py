"""`rediacc_ci.ops.backup_bucket_scope_probe` against a fake S3 transport: no network.

Each failure test is the control for `test_all_legs_good_exits_0`: the same world with one answer changed, so a pass cannot come from a leg that never ran.
"""

from __future__ import annotations

import datetime
import io
import urllib.parse

import pytest

from rediacc_ci.ops import backup_bucket_scope_probe as probe_mod

SECRET = "s3cr3t-value-that-must-never-print"
KEY_ID = "key-id-that-must-never-print"
ENV = {
    "ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": KEY_ID,
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": SECRET,
}
NOW = datetime.datetime(2026, 10, 29, 12, 0, 0, tzinfo=datetime.UTC)


class FakeS3:
    """Stores what is PUT to own buckets; answers foreign LISTs with `foreign_list`. `override` maps (method, bucket) to a status or an exception."""

    def __init__(self, own: set[str], foreign_list: int = 403, override=None, corrupt=False):
        self.own = own
        self.foreign_list = foreign_list
        self.override = override or {}
        self.corrupt = corrupt
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict] = []

    def __call__(self, method, url, body, headers):
        parts = urllib.parse.urlsplit(url)
        bucket = parts.path.lstrip("/").split("/", 1)[0]
        self.calls.append((method, bucket))
        self.headers.append(headers)
        forced = self.override.get((method, bucket))
        if isinstance(forced, Exception):
            raise forced
        if forced is not None:
            return forced, b""
        if bucket not in self.own:
            return (self.foreign_list, b"") if method == "GET" else (403, b"")
        if method == "PUT":
            self.objects[parts.path] = body
            return 200, b""
        if method == "GET":
            data = self.objects.get(parts.path, b"")
            return 200, (b"x" + data if self.corrupt else data)
        if method == "DELETE":
            self.objects.pop(parts.path, None)
            return 204, b""
        return 500, b""


def _bench_targets():
    return probe_mod.targets("bench", None)


def _run(fake, environ=ENV, found=None):
    out = io.StringIO()
    rc = probe_mod.probe("bench", found or _bench_targets(), environ, fake, out=out, now=NOW)
    return rc, out.getvalue()


def _own_name():
    return _bench_targets()[0].own.name


def test_targets_bench_resolves_own_and_two_foreign_buckets():
    (t,) = _bench_targets()
    assert t.own.name == "rediacc-backups-bench"
    names = [b.name for b in t.foreign]
    assert "rediacc-configs-bench" in names
    assert len(names) == 2
    assert t.own.name not in names


def test_targets_stable_each_region_has_foreign_config_and_edge_backup():
    found = probe_mod.targets("stable", None)
    assert [t.region for t in found] == ["eu", "us", "asia"]
    for t in found:
        assert t.own.name.startswith("rediacc-backups-")
        assert {b.name for b in t.foreign} == {
            "rediacc-configs-%s" % t.region,
            "edge-rediacc-backups-%s" % t.region,
        }
    assert found[0].own.jurisdiction == "eu"


def test_all_legs_good_exits_0():
    fake = FakeS3({_own_name()})
    rc, out = _run(fake)
    assert rc == 0, out
    verbs = [m for m, _ in fake.calls]
    assert verbs == ["PUT", "GET", "DELETE", "GET", "GET"]
    assert out.count("PASS") == 5
    assert not fake.objects


def test_foreign_list_answering_200_exits_1():
    rc, out = _run(FakeS3({_own_name()}, foreign_list=200))
    assert rc == 1
    assert "a FOREIGN bucket answered the pair" in out


def test_own_put_403_exits_1():
    own = _own_name()
    rc, out = _run(FakeS3({own}, override={("PUT", own): 403}))
    assert rc == 1
    assert "FAIL" in out
    assert "PUT" in out


def test_get_bytes_differ_exits_1():
    rc, out = _run(FakeS3({_own_name()}, corrupt=True))
    assert rc == 1
    assert "bytes differ" in out


def test_transport_error_exits_2():
    own = _own_name()
    rc, out = _run(FakeS3({own}, override={("GET", own): OSError("connection reset")}))
    assert rc == 2
    assert "NO-VERDICT" in out
    assert "connection reset" not in out


def test_foreign_list_404_is_no_verdict_exits_2():
    rc, _ = _run(FakeS3({_own_name()}, foreign_list=404))
    assert rc == 2


def test_delete_403_is_a_note_with_lifecycle_read_exits_0():
    own = _own_name()
    fake = FakeS3({own}, override={("DELETE", own): 403})
    rc, out = _run(fake)
    assert rc == 0, out
    assert "left behind" in out
    assert "LIFECYCLE" in out


def test_missing_env_exits_2(capsys):
    rc = probe_mod.main(["--channel", "bench"], transport=FakeS3(set()), environ={})
    assert rc == 2
    assert "unset" in capsys.readouterr().err


def test_suffixed_name_present_exits_2(capsys):
    env = dict(ENV, ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE="other")
    rc = probe_mod.main(["--channel", "bench"], transport=FakeS3(set()), environ=env)
    assert rc == 2
    assert "refusing" in capsys.readouterr().err


def test_region_with_bench_exits_2():
    assert probe_mod.main(["--channel", "bench", "--region", "eu"], environ=ENV) == 2


def test_unknown_region_exits_2():
    assert probe_mod.main(["--channel", "stable", "--region", "mars"], environ=ENV) == 2


@pytest.mark.parametrize(
    "fake_args",
    [
        {},
        {"foreign_list": 200},
        {"corrupt": True},
    ],
)
def test_no_secret_or_signature_in_output(capsys, fake_args):
    fake = FakeS3({_own_name()}, **fake_args)
    rc = probe_mod.main(["--channel", "bench"], transport=fake, environ=ENV)
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert rc in (0, 1)
    assert SECRET not in text
    assert KEY_ID not in text
    assert "acct.r2" not in text
    for headers in fake.headers:
        assert headers["Authorization"].split("Signature=")[1] not in text


def test_sigv4_uses_jurisdiction_endpoint_for_eu():
    found = probe_mod.targets("stable", ["eu"])
    urls = []

    def transport(_method, url, body, _headers):
        urls.append(url)
        return (403, b"") if "configs" in url or "edge-" in url else (200, body)

    out = io.StringIO()
    probe_mod.probe("stable", found, ENV, transport, out=out, now=NOW)
    assert urls
    assert all(".eu.r2.cloudflarestorage.com/" in u for u in urls)


def test_lifecycle_transport_error_does_not_change_the_exit():
    own = _own_name()
    fake = FakeS3({own}, override={("DELETE", own): 403})

    def transport(method, url, body, headers):
        if url.endswith("?lifecycle"):
            raise OSError("reset")
        return fake(method, url, body, headers)

    rc, out = _run(transport)
    assert rc == 0, out
    assert "LIFECYCLE" in out
    assert "NO-VERDICT" not in out


def test_unreadable_regions_json_is_a_config_error(tmp_path):
    (tmp_path / "regions.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(probe_mod.ConfigError):
        probe_mod.targets("stable", None, root=tmp_path)
    with pytest.raises(probe_mod.ConfigError):
        probe_mod.targets("stable", None, root=tmp_path / "absent")


@pytest.mark.parametrize("channel", ["stable", "edge"])
def test_region_without_bucket_entry_is_a_config_error(tmp_path, channel):
    (tmp_path / "regions.json").write_text(
        '{"regions": [{"id": "eu", "r2": {"name": "a"}}]}', encoding="utf-8"
    )
    if channel == "stable":
        (tmp_path / "regions.json").write_text('{"regions": [{"id": "eu"}]}', encoding="utf-8")
    with pytest.raises(probe_mod.ConfigError):
        probe_mod.targets(channel, ["eu"], root=tmp_path)


def test_main_maps_config_errors_to_exit_2(monkeypatch):
    monkeypatch.setattr(
        probe_mod, "targets", lambda *_a, **_k: (_ for _ in ()).throw(probe_mod.ConfigError("x"))
    )
    assert probe_mod.main(["--channel", "stable"], environ=ENV) == 2


def test_bench_config_bucket_without_name_is_a_config_error(tmp_path):
    worker = tmp_path.joinpath(*probe_mod.pbc.WORKER_DIR)
    worker.mkdir(parents=True)
    (worker / probe_mod.pbc.BENCH_CONFIG).write_text(
        '[[r2_buckets]]\nbinding = "CONFIG_BUCKET"\n', encoding="utf-8"
    )
    with pytest.raises(probe_mod.ConfigError, match="no bucket_name"):
        probe_mod._bench_config_bucket(tmp_path)
    with pytest.raises(probe_mod.ConfigError):
        probe_mod._bench_config_bucket(tmp_path / "absent")
