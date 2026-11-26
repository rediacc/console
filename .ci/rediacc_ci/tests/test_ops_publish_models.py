"""`rediacc_ci.ops.publish_models`: the order, headers, sequence and refusals of a model bundle publish. No network, no bucket, no signing key: the runner and the fetcher are fakes."""

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ops import publish_models as pm

if TYPE_CHECKING:
    from collections.abc import Mapping

SECRETS = {
    "MODEL_ED25519_PRIVATE_KEY": "k",
    "R2_PUBLIC_DATA_ACCESS_KEY_ID": "id",
    "R2_PUBLIC_DATA_SECRET_ACCESS_KEY": "secret",
}


class FakeRunner:
    """Records each command and writes the files the real pack and sign steps would."""

    def __init__(self, fail_on: str = "") -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.cwds: list[pathlib.Path | None] = []
        self.fail_on = fail_on

    def __call__(self, argv: list[str], env: Mapping[str, str], cwd: pathlib.Path | None) -> int:
        self.calls.append(list(argv))
        self.envs.append(dict(env))
        self.cwds.append(cwd)
        if self.fail_on and self.fail_on in argv:
            return 3
        if argv[1:3] == ["models", "pack"]:
            out = pathlib.Path(argv[argv.index("--out") + 1])
            version = argv[argv.index("--version") + 1]
            (out / "objects").mkdir(parents=True, exist_ok=True)
            (out / "manifests").mkdir(parents=True, exist_ok=True)
            (out / "objects" / "ab12").write_bytes(b"{}")
            (out / "manifests" / ("%s.json" % version)).write_bytes(b"{}")
        elif "sign" in argv and argv[-2:-1] == ["sign"]:
            pathlib.Path(argv[-1] + ".sig").write_bytes(b"s")
        elif "pointer" in argv:
            out = pathlib.Path(argv[argv.index("-out") + 1])
            out.write_bytes(b"{}")
            pathlib.Path(str(out) + ".sig").write_bytes(b"s")
        return 0


def fetcher(files: dict[str, bytes]):
    def get(url: str) -> bytes | None:
        return files.get(url)

    return get


BUCKET: dict[str, bytes] = {}
REAL_READER = pm.bucket_reader


@pytest.fixture(autouse=True)
def _bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bucket reader serves `BUCKET`, never a real `aws`."""
    BUCKET.clear()
    monkeypatch.setattr(pm, "bucket_reader", lambda _env, _endpoint: BUCKET.get)


def args(*extra: str):
    return pm.parse_args(["--renet", "/bin/renet", *extra])


def uploads(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[1:3] == ["s3", "cp"]]


def test_publish_orders_objects_manifest_then_pointer() -> None:
    runner = FakeRunner()
    get = fetcher({})
    code = pm.run(
        args("--channel", "edge", "--percent", "10", "--version", "7"),
        SECRETS,
        runner=runner,
        get=get,
    )
    assert code == 0
    keys = [c[4].split("/models/", 1)[1] for c in uploads(runner.calls)]
    assert keys == [
        "objects/ab12",
        "manifests/7.json",
        "manifests/7.json.sig",
        "channels/edge.json.sig",
        "channels/edge.json",
    ]
    assert runner.calls[0][1:3] == ["models", "pack"]


def test_headers_follow_the_bundle_format() -> None:
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    by_key = {
        c[4].split("/models/", 1)[1]: c[c.index("--cache-control") + 1]
        for c in uploads(runner.calls)
    }
    assert by_key["objects/ab12"] == pm.IMMUTABLE
    assert by_key["manifests/7.json"] == pm.IMMUTABLE
    assert by_key["channels/edge.json"] == "public, max-age=60"
    assert by_key["channels/edge.json.sig"] == "public, max-age=60"


def test_sequence_is_one_above_the_origin_pointer() -> None:
    runner = FakeRunner()
    BUCKET[pm.pointer_key("edge")] = json.dumps({"seq": 41}).encode()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    pointer_call = next(c for c in runner.calls if "pointer" in c)
    assert pointer_call[pointer_call.index("-seq") + 1] == "42"


def test_missing_pointer_starts_at_one_and_explicit_seq_wins() -> None:
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    first = next(c for c in runner.calls if "pointer" in c)
    assert first[first.index("-seq") + 1] == "1"
    runner = FakeRunner()
    pm.run(
        args("--channel", "edge", "--version", "7", "--seq", "9"),
        SECRETS,
        runner=runner,
        get=fetcher({}),
    )
    again = next(c for c in runner.calls if "pointer" in c)
    assert again[again.index("-seq") + 1] == "9"


def test_promote_signs_stable_from_the_edge_manifest_without_repacking() -> None:
    base = "%s/models" % pm.PUBLIC_DATA_ORIGIN
    BUCKET[pm.pointer_key("edge")] = json.dumps({"seq": 5, "version": 12}).encode()
    BUCKET[pm.pointer_key("stable")] = json.dumps({"seq": 2}).encode()
    get = fetcher(
        {
            base + "/manifests/12.json": b"{}",
            base + "/manifests/12.json.sig": b"s",
        }
    )
    runner = FakeRunner()
    pm.run(args("--channel", "stable", "--promote"), SECRETS, runner=runner, get=get)
    assert not any(c[1:3] == ["models", "pack"] for c in runner.calls)
    pointer_call = next(c for c in runner.calls if "pointer" in c)
    assert pointer_call[pointer_call.index("-channel") + 1] == "stable"
    assert pointer_call[pointer_call.index("-seq") + 1] == "3"
    assert pointer_call[pointer_call.index("-percent") + 1] == "100"
    keys = [c[4].split("/models/", 1)[1] for c in uploads(runner.calls)]
    assert keys == ["channels/stable.json.sig", "channels/stable.json"]


def test_promote_never_signs_the_downloaded_manifest() -> None:
    """5dc50111.2: a promote that re-signed the edge manifest would sign whatever the bucket held."""
    base = "%s/models" % pm.PUBLIC_DATA_ORIGIN
    BUCKET[pm.pointer_key("edge")] = json.dumps({"seq": 5, "version": 12}).encode()
    get = fetcher({base + "/manifests/12.json": b"{}", base + "/manifests/12.json.sig": b"s"})
    runner = FakeRunner()
    pm.run(args("--channel", "stable", "--promote"), SECRETS, runner=runner, get=get)
    assert not any(c[-2:-1] == ["sign"] for c in runner.calls)
    assert any("pointer" in c for c in runner.calls)


def test_publish_still_signs_its_own_manifest() -> None:
    """Control for the promote test: a publish signs the manifest it packed."""
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    assert sum(1 for c in runner.calls if c[-2:-1] == ["sign"]) == 1


def test_the_sequence_comes_from_the_bucket_not_the_cached_origin() -> None:
    """5dc50111.3: the origin serves a pointer from a 60 second cache, so a stale seq repeats."""
    BUCKET[pm.pointer_key("edge")] = json.dumps({"seq": 41}).encode()
    stale = {"%s/models/channels/edge.json" % pm.PUBLIC_DATA_ORIGIN: b'{"seq": 3}'}
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher(stale))
    pointer_call = next(c for c in runner.calls if "pointer" in c)
    assert pointer_call[pointer_call.index("-seq") + 1] == "42"


def test_the_bucket_reader_maps_a_missing_key_to_none_and_other_errors_to_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = [
        subprocess.CompletedProcess([], 0, b"{}", b""),
        subprocess.CompletedProcess([], 1, b"", b"An error occurred (404) when calling HeadObject"),
        subprocess.CompletedProcess([], 1, b"", b"AccessDenied"),
        subprocess.CompletedProcess([], 1, b"", b"InternalError request id 4041 try later"),
    ]
    monkeypatch.setattr(pm.awscli, "run", lambda *_a, **_k: outcomes.pop(0))
    read = REAL_READER({}, "https://e")
    assert read("models/x") == b"{}"
    assert read("models/x") is None
    with pytest.raises(pm.PublishError, match="AccessDenied"):
        read("models/x")
    with pytest.raises(pm.PublishError, match="request id 4041"):
        read("models/x")


def test_promote_without_an_edge_pointer_is_refused() -> None:
    with pytest.raises(pm.PublishError, match="no edge pointer"):
        pm.run(
            args("--channel", "stable", "--promote"), SECRETS, runner=FakeRunner(), get=fetcher({})
        )


def test_missing_secrets_are_refused_before_any_command() -> None:
    runner = FakeRunner()
    with pytest.raises(pm.PublishError, match="MODEL_ED25519_PRIVATE_KEY"):
        pm.run(args("--channel", "edge", "--version", "7"), {}, runner=runner, get=fetcher({}))
    assert runner.calls == []


def test_signing_runs_inside_the_renet_tree() -> None:
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    signing = [
        cwd
        for call, cwd in zip(runner.calls, runner.cwds, strict=True)
        if "./cmd/modelsign" in call
    ]
    assert signing
    assert all(cwd == pm.renet_dir() for cwd in signing)


def test_credentials_reach_the_children_under_the_aws_names() -> None:
    runner = FakeRunner()
    pm.run(args("--channel", "edge", "--version", "7"), SECRETS, runner=runner, get=fetcher({}))
    assert runner.envs[0]["AWS_ACCESS_KEY_ID"] == "id"
    assert runner.envs[0]["AWS_SECRET_ACCESS_KEY"] == "secret"


def test_a_failed_step_stops_the_run_before_the_pointer_uploads() -> None:
    class Failing(FakeRunner):
        def __call__(
            self, argv: list[str], env: Mapping[str, str], cwd: pathlib.Path | None
        ) -> int:
            if argv[1:3] == ["s3", "cp"] and "objects/ab12" in argv[4]:
                self.calls.append(list(argv))
                return 1
            return super().__call__(argv, env, cwd)

    failing = Failing()
    with pytest.raises(pm.PublishError, match="upload objects"):
        pm.run(
            args("--channel", "edge", "--version", "7"), SECRETS, runner=failing, get=fetcher({})
        )
    assert not any("channels/" in c[4] for c in uploads(failing.calls))


def test_dry_run_runs_nothing_and_needs_no_secrets() -> None:
    runner = FakeRunner()

    def no_network(url: str) -> bytes | None:
        raise AssertionError("dry run fetched %s" % url)

    code = pm.run(args("--channel", "edge", "--dry-run"), {}, runner=runner, get=no_network)
    assert code == 0
    assert runner.calls == []


def test_percent_and_promote_flags_are_validated() -> None:
    with pytest.raises(SystemExit):
        args("--channel", "edge", "--percent", "101")
    with pytest.raises(SystemExit):
        args("--channel", "edge", "--promote")
    with pytest.raises(SystemExit):
        args("--channel", "stable", "--promote", "--rollback")
