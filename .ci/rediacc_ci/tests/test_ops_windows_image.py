"""`rediacc_ci.ops.windows_image`: the refusals, the record and the verbs of the Windows lane's private bucket. No network, no bucket, no credentials that reach anything: the runner and the transport are fakes, and the bucket's objects live in a dict."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import windows_image as wi

if TYPE_CHECKING:
    from collections.abc import Mapping

SECRETS = {"R2_WINDOWS_IMAGE_ACCESS_KEY_ID": "id", "R2_WINDOWS_IMAGE_SECRET_ACCESS_KEY": "secret"}
EVAL_LABEL = "CENA_X64FREE_EN-US_DV9"
RETAIL_LABEL = "CCCOMA_X64FRE_EN-US_DV9"
GO_FILE = pathlib.Path("private/renet/pkg/infra/opsconfig/windows.go")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_iso(path: pathlib.Path, label: str, tail: bytes = b"") -> bytes:
    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[40:72] = label.encode().ljust(32)
    data = bytes(wi.PVD_OFFSET) + bytes(pvd) + tail
    path.write_bytes(data)
    return data


class FakeBucket:
    """Plays the aws CLI and tar: `cp` to s3:// stores the file's bytes, `cp` from s3:// writes them, tar writes a placeholder archive or unpacks a marker."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(self, argv: list[str], env: Mapping[str, str]) -> int:
        self.calls.append(list(argv))
        self.envs.append(dict(env))
        if argv[:3] == ["aws", "s3", "cp"]:
            src, dst = argv[3], argv[4]
            if dst.startswith("s3://"):
                self.objects[dst.split("/", 3)[3]] = pathlib.Path(src).read_bytes()
            else:
                pathlib.Path(dst).write_bytes(self.objects[src.split("/", 3)[3]])
            return 0
        if argv[:3] == ["tar", "--zstd", "-cf"]:
            pathlib.Path(argv[3]).write_bytes(b"packed:" + " ".join(argv[6:]).encode())
            return 0
        if argv[:3] == ["tar", "--zstd", "-xf"]:
            target = pathlib.Path(argv[argv.index("-C") + 1]) / wi.GOLDEN_DIR
            target.mkdir(parents=True, exist_ok=True)
            (target / "golden.qcow2").write_bytes(b"q")
            return 0
        return 0


def refuse_transport(method: str, url: str, headers: dict[str, str]) -> int:
    raise AssertionError("no request may be made: %s %s (%d headers)" % (method, url, len(headers)))


def write_record(tmp: pathlib.Path, **over) -> pathlib.Path:
    doc = json.loads((paths.repo_root() / wi.RECORD_REL).read_text(encoding="utf-8"))
    doc.update(over)
    path = tmp / "windows-image.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def inputs_for(iso: bytes, virtio: bytes) -> dict:
    return {
        "iso": {
            "key": "inputs/win11-eval/%s.iso" % sha(iso),
            "sha256": sha(iso),
            "bytes": len(iso),
            "file": "x.iso",
            "edition": EVAL_LABEL,
            "build": "26300.9457",
        },
        "virtio": {
            "key": "inputs/virtio-win/%s.iso" % sha(virtio),
            "sha256": sha(virtio),
            "bytes": len(virtio),
            "source": "s",
        },
    }


def call(
    record: pathlib.Path,
    argv: list[str],
    env: Mapping[str, str] | None = None,
    runner=None,
    transport=refuse_transport,
):
    out = io.StringIO()
    rc = wi.run(
        [*argv, "--record", str(record)],
        {**SECRETS, **(env or {})},
        runner or FakeBucket(),
        transport,
        out,
    )
    return rc, out.getvalue()


# ---- the committed record ---------------------------------------------------


def test_committed_record_shape() -> None:
    doc = wi.load_record(paths.repo_root() / wi.RECORD_REL)
    assert doc["schema"] == 1
    assert doc["bucket"] not in wi.PUBLIC_BUCKETS
    assert doc["warn_days"] == 14
    assert doc["rebake"] == "PYTHONPATH=.ci python3 -m rediacc_ci.ops.windows_image rebake"
    assert "inputs" in doc
    assert "image" in doc


def test_go_pins_equal_recorded_inputs() -> None:
    """Once WL3's `opsconfig/windows.go` exists and the record has inputs, the Go file pins the same two hashes."""
    doc = wi.load_record(paths.repo_root() / wi.RECORD_REL)
    pins = wi.go_pins(paths.repo_root() / GO_FILE)
    if pins is None or doc["inputs"] is None:
        pytest.skip("opsconfig/windows.go or the recorded inputs do not exist yet")
    assert pins is not None
    want = {doc["inputs"]["iso"]["sha256"], doc["inputs"]["virtio"]["sha256"]}
    assert want <= pins, "windows.go pins %s, the record holds %s" % (sorted(pins), sorted(want))


def test_go_pins_reader(tmp_path: pathlib.Path) -> None:
    assert wi.go_pins(tmp_path / "absent.go") is None
    go = tmp_path / "windows.go"
    go.write_text(
        'const WindowsISOSHA256 = "%s"\nconst VirtioISOSHA256 = "%s"\n' % ("a" * 64, "b" * 64)
    )
    assert wi.go_pins(go) == {"a" * 64, "b" * 64}


# ---- refusals ---------------------------------------------------------------


@pytest.mark.parametrize("verb", [["probe"], ["fetch"], ["fetch", "--inputs"], ["publish"]])
def test_public_data_bucket_refused_by_name(tmp_path: pathlib.Path, verb: list[str]) -> None:
    runner = FakeBucket()
    rc, _ = call(write_record(tmp_path), [*verb, "--bucket", "rediacc-public-data"], runner=runner)
    assert rc == 1
    assert runner.calls == []


def test_public_data_bucket_refused_in_record(tmp_path: pathlib.Path, capsys) -> None:
    runner = FakeBucket()
    rc, _ = call(write_record(tmp_path, bucket="rediacc-public-data"), ["probe"], runner=runner)
    assert rc == 1
    assert "public by policy" in capsys.readouterr().err
    assert runner.calls == []


def test_upload_inputs_refuses_non_evaluation_label(tmp_path: pathlib.Path, capsys) -> None:
    make_iso(tmp_path / "26300.9457.x.iso", RETAIL_LABEL)
    make_iso(tmp_path / "virtio-win.iso", "virtio-win-0.1.302")
    runner = FakeBucket()
    record = write_record(tmp_path)
    rc, _ = call(
        record,
        ["upload-inputs", str(tmp_path / "26300.9457.x.iso"), str(tmp_path / "virtio-win.iso")],
        runner=runner,
    )
    assert rc == 1
    assert RETAIL_LABEL in capsys.readouterr().err
    assert runner.calls == []
    assert json.loads(record.read_text())["inputs"] is None


def test_upload_inputs_refuses_non_iso(tmp_path: pathlib.Path) -> None:
    (tmp_path / "a.iso").write_bytes(b"x" * 100)
    make_iso(tmp_path / "v.iso", "virtio")
    rc, _ = call(
        write_record(tmp_path),
        ["upload-inputs", str(tmp_path / "a.iso"), str(tmp_path / "v.iso"), "--build", "1.2"],
    )
    assert rc == 1


def test_missing_secrets_refused(tmp_path: pathlib.Path, capsys) -> None:
    rc = wi.run(
        ["probe", "--record", str(write_record(tmp_path))],
        {},
        FakeBucket(),
        refuse_transport,
        io.StringIO(),
    )
    assert rc == 1
    assert "bws_env exec --profile windows-image" in capsys.readouterr().err


# ---- upload-inputs ----------------------------------------------------------


def test_upload_inputs_writes_record(tmp_path: pathlib.Path) -> None:
    iso = make_iso(tmp_path / "26300.9457.260913-1737.eval.iso", EVAL_LABEL, b"iso")
    virtio = make_iso(tmp_path / "virtio-win.iso", "virtio-win-0.1.302", b"virtio")
    runner = FakeBucket()
    record = write_record(tmp_path)
    rc, _ = call(
        record,
        [
            "upload-inputs",
            str(tmp_path / "26300.9457.260913-1737.eval.iso"),
            str(tmp_path / "virtio-win.iso"),
        ],
        runner=runner,
    )
    assert rc == 0
    doc = json.loads(record.read_text())
    assert doc["inputs"]["iso"] == {
        "key": "inputs/win11-eval/%s.iso" % sha(iso),
        "sha256": sha(iso),
        "bytes": len(iso),
        "file": "26300.9457.260913-1737.eval.iso",
        "edition": EVAL_LABEL,
        "build": "26300.9457",
    }
    assert doc["inputs"]["virtio"]["sha256"] == sha(virtio)
    assert "virtio-win-0.1.302" in doc["inputs"]["virtio"]["source"]
    assert set(runner.objects) == {doc["inputs"]["iso"]["key"], doc["inputs"]["virtio"]["key"]}
    assert all(c[4].startswith("s3://windows-ci-images/") for c in runner.calls)
    assert runner.envs[0]["AWS_ACCESS_KEY_ID"] == "id"


# ---- fetch --inputs ---------------------------------------------------------


def test_fetch_inputs_verifies_and_places(tmp_path: pathlib.Path) -> None:
    iso, virtio = b"iso-bytes", b"virtio-bytes"
    inputs = inputs_for(iso, virtio)
    runner = FakeBucket({inputs["iso"]["key"]: iso, inputs["virtio"]["key"]: virtio})
    data = tmp_path / "data"
    rc, _ = call(
        write_record(tmp_path, inputs=inputs),
        ["fetch", "--inputs"],
        {"RENET_DATA_DIR": str(data)},
        runner,
    )
    assert rc == 0
    assert (data / "images" / wi.ISO_NAME).read_bytes() == iso
    assert (data / "images" / wi.VIRTIO_NAME).read_bytes() == virtio


def test_fetch_inputs_sha_mismatch_refused(tmp_path: pathlib.Path, capsys) -> None:
    inputs = inputs_for(b"iso-bytes", b"virtio-bytes")
    runner = FakeBucket(
        {inputs["iso"]["key"]: b"TAMPERED", inputs["virtio"]["key"]: b"virtio-bytes"}
    )
    data = tmp_path / "data"
    rc, _ = call(
        write_record(tmp_path, inputs=inputs),
        ["fetch", "--inputs"],
        {"RENET_DATA_DIR": str(data)},
        runner,
    )
    assert rc == 1
    assert "sha256 mismatch" in capsys.readouterr().err
    assert not (data / "images" / wi.ISO_NAME).exists()
    assert not (data / "images" / ("%s.part" % wi.ISO_NAME)).exists()


def test_windows_iso_set_skips_iso_download(tmp_path: pathlib.Path) -> None:
    iso, virtio = b"iso-bytes", b"virtio-bytes"
    inputs = inputs_for(iso, virtio)
    local = tmp_path / "mine.iso"
    local.write_bytes(iso)
    runner = FakeBucket({inputs["virtio"]["key"]: virtio})
    rc, out = call(
        write_record(tmp_path, inputs=inputs),
        ["fetch", "--inputs"],
        {"RENET_DATA_DIR": str(tmp_path / "d"), "WINDOWS_ISO": str(local)},
        runner,
    )
    assert rc == 0
    assert "WINDOWS_ISO" in out
    downloaded = [c[3] for c in runner.calls if c[3].startswith("s3://")]
    assert downloaded == ["s3://windows-ci-images/%s" % inputs["virtio"]["key"]]


def test_windows_iso_override_must_match_record(tmp_path: pathlib.Path) -> None:
    inputs = inputs_for(b"iso-bytes", b"virtio-bytes")
    local = tmp_path / "mine.iso"
    local.write_bytes(b"other")
    rc, _ = call(
        write_record(tmp_path, inputs=inputs),
        ["fetch", "--inputs"],
        {"RENET_DATA_DIR": str(tmp_path), "WINDOWS_ISO": str(local), "VIRTIO_ISO": str(local)},
    )
    assert rc == 1


# ---- pack, publish, fetch ---------------------------------------------------


def golden_dir(root: pathlib.Path, iso_sha: str = "", virtio_sha: str = "") -> pathlib.Path:
    golden = root / "images" / wi.GOLDEN_DIR
    (golden / "tpm").mkdir(parents=True)
    (golden / "golden.qcow2").write_bytes(b"q")
    (golden / "OVMF_VARS.fd").write_bytes(b"v")
    meta = {
        "build": "26300.9457",
        "installed_at": "2026-11-27T10:00:00Z",
        "expires_at": "2027-02-25T10:00:00Z",
    }
    if iso_sha:
        meta.update(iso_sha256=iso_sha, virtio_iso_sha256=virtio_sha)
    (golden / wi.GUEST_META).write_text(json.dumps(meta))
    return golden


def test_pack_publish_fetch_round_trip(tmp_path: pathlib.Path) -> None:
    inputs = inputs_for(b"iso-bytes", b"virtio-bytes")
    record = write_record(tmp_path, inputs=inputs)
    data = tmp_path / "data"
    golden_dir(data, inputs["iso"]["sha256"], inputs["virtio"]["sha256"])
    runner = FakeBucket()
    env = {"RENET_DATA_DIR": str(data)}
    assert call(record, ["pack"], env, runner)[0] == 0
    tar = data / "images" / wi.TAR_NAME
    side = json.loads(pathlib.Path("%s.json" % tar).read_text())
    assert side["sha256"] == sha(tar.read_bytes())
    assert call(record, ["publish"], env, runner)[0] == 0
    image = json.loads(record.read_text())["image"]
    assert image["key"] == "images/win11/26300.9457-2026-11-27/golden.tar.zst"
    assert image["iso_sha256"] == inputs["iso"]["sha256"]
    assert image["expires_at"] == "2027-02-25T10:00:00Z"
    assert image["expiry_source"] == wi.EXPIRY_SOURCE
    second = tmp_path / "second"
    assert call(record, ["fetch"], {"RENET_DATA_DIR": str(second)}, runner)[0] == 0
    assert (second / "images" / wi.GOLDEN_DIR / "golden.qcow2").exists()
    assert not (second / "images" / ("%s.part" % wi.TAR_NAME)).exists()


def test_pack_refuses_image_naming_no_inputs(tmp_path: pathlib.Path, capsys) -> None:
    data = tmp_path / "data"
    golden_dir(data)
    rc, _ = call(write_record(tmp_path), ["pack"], {"RENET_DATA_DIR": str(data)})
    assert rc == 1
    assert "iso_sha256" in capsys.readouterr().err


def test_publish_refuses_input_hash_mismatch(tmp_path: pathlib.Path, capsys) -> None:
    inputs = inputs_for(b"iso-bytes", b"virtio-bytes")
    record = write_record(tmp_path, inputs=inputs)
    data = tmp_path / "data"
    golden_dir(data, "c" * 64, inputs["virtio"]["sha256"])
    runner = FakeBucket()
    assert call(record, ["pack"], {"RENET_DATA_DIR": str(data)}, runner)[0] == 0
    rc, _ = call(record, ["publish"], {"RENET_DATA_DIR": str(data)}, runner)
    assert rc == 1
    assert "differs from inputs.iso.sha256" in capsys.readouterr().err
    assert runner.objects == {}
    assert json.loads(record.read_text())["image"] is None


def test_publish_refuses_without_recorded_inputs(tmp_path: pathlib.Path) -> None:
    data = tmp_path / "data"
    golden_dir(data, "c" * 64, "d" * 64)
    record = write_record(tmp_path)
    runner = FakeBucket()
    assert call(record, ["pack"], {"RENET_DATA_DIR": str(data)}, runner)[0] == 0
    assert call(record, ["publish"], {"RENET_DATA_DIR": str(data)}, runner)[0] == 1


def test_fetch_sha_mismatch_refused(tmp_path: pathlib.Path, capsys) -> None:
    image = {"key": "images/win11/x/golden.tar.zst", "sha256": sha(b"good")}
    runner = FakeBucket({image["key"]: b"bad"})
    data = tmp_path / "data"
    rc, _ = call(
        write_record(tmp_path, image=image), ["fetch"], {"RENET_DATA_DIR": str(data)}, runner
    )
    assert rc == 1
    assert "sha256 mismatch" in capsys.readouterr().err
    assert not any(c[:3] == ["tar", "--zstd", "-xf"] for c in runner.calls)
    assert not (data / "images" / ("%s.part" % wi.TAR_NAME)).exists()


def test_rebake_order(tmp_path: pathlib.Path) -> None:
    iso, virtio = b"iso-bytes", b"virtio-bytes"
    inputs = inputs_for(iso, virtio)
    data = tmp_path / "data"
    golden_dir(data)
    runner = FakeBucket({inputs["iso"]["key"]: iso, inputs["virtio"]["key"]: virtio})
    record = write_record(tmp_path, inputs=inputs)
    rc, _ = call(record, ["rebake"], {"RENET_DATA_DIR": str(data)}, runner)
    assert rc == 0
    heads = [" ".join(c[:4]) if c[0] == "renet" else " ".join(c[:3]) for c in runner.calls]
    assert heads == [
        "aws s3 cp",
        "aws s3 cp",
        "renet ops windows bake",
        "tar --zstd -cf",
        "aws s3 cp",
    ]
    assert json.loads(record.read_text())["image"]["iso_sha256"] == inputs["iso"]["sha256"]


# ---- probe ------------------------------------------------------------------


def test_probe_statuses(tmp_path: pathlib.Path) -> None:
    seen: list[tuple[str, bool]] = []

    def transport(method: str, url: str, headers: dict[str, str]) -> int:
        assert method == "GET"
        signed = "Authorization" in headers
        seen.append((url.split("/", 4)[3].split("?", maxsplit=1)[0], signed))
        if not signed:
            return 403
        return 200 if "windows-ci-images" in url else 403

    rc, out = call(write_record(tmp_path), ["probe"], transport=transport)
    assert rc == 0, out
    assert seen == [
        ("windows-ci-images", True),
        ("rediacc-public-data", True),
        ("windows-ci-images", False),
    ]
    assert "secret" not in out


def test_probe_fails_when_public_data_answers(tmp_path: pathlib.Path) -> None:
    rc, _ = call(write_record(tmp_path), ["probe"], transport=lambda *_: 200)
    assert rc == 1


# ---- dry run ----------------------------------------------------------------


@pytest.mark.parametrize(
    "verb",
    [["probe"], ["fetch"], ["fetch", "--inputs"], ["rebake"], ["publish"]],
)
def test_dry_run_makes_no_request(tmp_path: pathlib.Path, verb: list[str]) -> None:
    inputs = inputs_for(b"iso-bytes", b"virtio-bytes")
    image = {"key": "images/win11/x/golden.tar.zst", "sha256": "e" * 64}
    data = tmp_path / "data"
    golden_dir(data, inputs["iso"]["sha256"], inputs["virtio"]["sha256"])
    tar = data / "images" / wi.TAR_NAME
    pathlib.Path("%s.json" % tar).write_text(
        json.dumps(
            {
                "build": "1",
                "installed_at": "2026-11-27T00:00:00Z",
                "expires_at": "2027-01-01T00:00:00Z",
                "iso_sha256": inputs["iso"]["sha256"],
                "virtio_iso_sha256": inputs["virtio"]["sha256"],
            }
        )
    )
    record = write_record(tmp_path, inputs=inputs, image=image)
    before = record.read_text()

    def refuse_runner(argv, env):
        raise AssertionError("dry run ran %s with %d env names" % (argv, len(env)))

    out = io.StringIO()
    rc = wi.run(
        [*verb, "--dry-run", "--record", str(record)],
        {"RENET_DATA_DIR": str(data)},
        refuse_runner,
        refuse_transport,
        out,
    )
    assert rc == 0, out.getvalue()
    assert "DRY-RUN" in out.getvalue()
    assert record.read_text() == before
    assert not (data / "images" / wi.ISO_NAME).exists()
