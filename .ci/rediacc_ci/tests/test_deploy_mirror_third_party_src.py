"""`rediacc_ci.deploy.mirror_third_party_src`: a fake `aws` on PATH (an object store in a directory) and fake downloads.

The module has two network seams, `fetch` and `fetch_debian_source`; both are replaced, so no test touches the network or a bucket.
"""

from __future__ import annotations

import hashlib
import json
import stat
import textwrap
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.deploy import mirror_third_party_src as mirror

if TYPE_CHECKING:
    import pathlib

FAKE_AWS = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import hashlib, json, os, pathlib, sys
    store = pathlib.Path(os.environ["FAKE_STORE"])
    args = sys.argv[1:]
    with open(store / "calls.log", "a") as log:
        log.write(" ".join(args) + "\\n")
    if args[:2] == ["s3api", "head-object"]:
        key = args[args.index("--key") + 1]
        meta = store / "objects" / key.replace("/", "__")
        if not meta.exists():
            sys.stderr.write("An error occurred (404) when calling the HeadObject operation: Not Found\\n")
            sys.exit(254)
        print(meta.read_text())
        sys.exit(0)
    if args[:2] == ["s3", "cp"]:
        dest = args[3].split("/", 3)[3]
        sha = args[args.index("--metadata") + 1].split("=", 1)[1]
        (store / "objects").mkdir(exist_ok=True)
        (store / "objects" / dest.replace("/", "__")).write_text(json.dumps({"Metadata": {"sha256": sha}}))
        sys.exit(0)
    sys.exit(2)
    """
)

DOCKERFILE = """\
# ============================================================================
# Stage 0: CRIU source
# ============================================================================
FROM debian:bookworm AS criu-source
RUN echo criu
# ============================================================================
# Stage 2a: rsync
# ============================================================================
FROM ubuntu:26.10 AS rsync-builder-amd64
RUN echo rsync
# ============================================================================
# Stage 3c: zot
# ============================================================================
FROM ubuntu:26.10 AS zot-downloader-amd64
RUN echo zot
"""

BODIES = {"https://up/criu.tar.gz": b"criu-bytes", "https://up/rsync.tar.gz": b"rsync-bytes"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lock_for(bodies: dict[str, bytes]) -> dict:
    return {
        "components": {
            "criu": {
                "name": "CRIU",
                "version": "1",
                "upstreamSourceUrl": "https://up/criu.tar.gz",
                "mirrorUrl": "https://releases.example/third-party-src/criu-1.tar.gz",
                "sourceSha256": sha(bodies["https://up/criu.tar.gz"]),
            },
            "rsync": {
                "name": "rsync",
                "version": "2",
                "upstreamSourceUrl": "https://up/rsync.tar.gz",
                "mirrorUrl": "https://releases.example/third-party-src/rsync-2.tar.gz",
                "source": {"kind": "tarball", "sha256": sha(bodies["https://up/rsync.tar.gz"])},
            },
        }
    }


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    aws = bindir / "aws"
    aws.write_text(FAKE_AWS)
    aws.chmod(aws.stat().st_mode | stat.S_IXUSR)
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("PATH", "%s:%s" % (bindir, __import__("os").environ["PATH"]))
    monkeypatch.delenv("AWS_BIN", raising=False)
    monkeypatch.setenv("FAKE_STORE", str(store))
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.example")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "s")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(DOCKERFILE)
    return {"tmp": tmp_path, "store": store, "dockerfile": dockerfile}


def patch_fetch(monkeypatch: pytest.MonkeyPatch, bodies: dict[str, bytes]) -> list[str]:
    seen: list[str] = []

    def fake(url: str, dest: pathlib.Path) -> None:
        seen.append(url)
        dest.write_bytes(bodies[url])

    monkeypatch.setattr(mirror, "fetch", fake)
    return seen


def run(env: dict, lock: dict, *extra: str) -> int:
    lockfile = env["tmp"] / "lock.json"
    lockfile.write_text(json.dumps(lock))
    return mirror.main(["--lock", str(lockfile), "--dockerfile", str(env["dockerfile"]), *extra])


def calls(env: dict) -> list[str]:
    log = env["store"] / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_first_run_uploads_sources_and_recipes_with_sha_metadata(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    assert run(env, lock_for(BODIES)) == 0
    objects = sorted(p.name for p in (env["store"] / "objects").iterdir())
    assert objects == [
        "third-party-src__criu-1-build.txt",
        "third-party-src__criu-1.tar.gz",
        "third-party-src__rsync-2-build.txt",
        "third-party-src__rsync-2.tar.gz",
    ]
    meta = json.loads((env["store"] / "objects" / "third-party-src__criu-1.tar.gz").read_text())
    assert meta["Metadata"]["sha256"] == sha(b"criu-bytes")


def test_an_existing_object_with_the_same_sha_is_skipped(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    assert run(env, lock_for(BODIES)) == 0
    first = len([c for c in calls(env) if c.startswith("s3 cp")])
    assert first == 4
    assert run(env, lock_for(BODIES)) == 0
    assert len([c for c in calls(env) if c.startswith("s3 cp")]) == first


def test_an_existing_object_with_a_different_sha_fails_and_writes_nothing(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    (env["store"] / "objects").mkdir()
    (env["store"] / "objects" / "third-party-src__rsync-2.tar.gz").write_text(
        json.dumps({"Metadata": {"sha256": "0" * 64}})
    )
    assert run(env, lock_for(BODIES)) == 1
    assert not [c for c in calls(env) if c.startswith("s3 cp")]


def test_an_existing_object_without_metadata_is_never_overwritten(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    (env["store"] / "objects").mkdir()
    (env["store"] / "objects" / "third-party-src__criu-1.tar.gz").write_text("{}")
    assert run(env, lock_for(BODIES)) == 1
    assert not [c for c in calls(env) if c.startswith("s3 cp")]


def test_a_download_that_differs_from_the_lockfile_fails_before_any_upload(
    env, monkeypatch
) -> None:
    bad = dict(BODIES)
    bad["https://up/rsync.tar.gz"] = b"tampered"
    patch_fetch(monkeypatch, bad)
    assert run(env, lock_for(BODIES)) == 1
    assert calls(env) == []


def test_a_component_without_a_recorded_sha_is_refused(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    lock = lock_for(BODIES)
    del lock["components"]["criu"]["sourceSha256"]
    assert run(env, lock) == 1
    assert calls(env) == []


def test_dry_run_downloads_and_verifies_but_makes_no_aws_call(env, monkeypatch) -> None:
    seen = patch_fetch(monkeypatch, BODIES)
    assert run(env, lock_for(BODIES), "--dry-run") == 0
    assert sorted(seen) == sorted(BODIES)
    assert calls(env) == []


def test_recipe_extraction_is_verbatim_and_limited_to_the_component() -> None:
    text = mirror.extract_recipe(DOCKERFILE, mirror.RECIPE_STAGES["rsync"])
    assert "FROM ubuntu:26.10 AS rsync-builder-amd64" in text
    assert text in DOCKERFILE
    assert "criu" not in text
    assert "zot" not in text


def test_the_real_dockerfile_yields_a_recipe_for_both_compiled_components() -> None:
    real = (mirror.paths.repo_root() / mirror.DOCKERFILE_REL).read_text(encoding="utf-8")
    criu = mirror.extract_recipe(real, mirror.RECIPE_STAGES["criu"])
    rsync = mirror.extract_recipe(real, mirror.RECIPE_STAGES["rsync"])
    assert "AS criu-builder-arm64" in criu
    assert "AS rsync-builder-arm64" in rsync


def test_static_library_sources_are_uploaded_from_the_manifest(env, monkeypatch) -> None:
    patch_fetch(monkeypatch, BODIES)
    asked: list[tuple[str, str]] = []

    def fake_source(source: str, version: str, dest: pathlib.Path) -> list[pathlib.Path]:
        asked.append((source, version))
        out = dest / ("%s_%s.dsc" % (source, version))
        out.write_text("dsc of %s" % source)
        return [out]

    monkeypatch.setattr(mirror, "fetch_debian_source", fake_source)
    manifest = env["tmp"] / "dpkg.tsv"
    manifest.write_text(
        "libpopt-dev\t1.19\tpopt\t1.19-2\nlibpopt0\t1.19\tpopt\t1.19-2\nzlib1g-dev\t1:1.3\tzlib\t1:1.3-1\n"
    )
    assert run(env, lock_for(BODIES), "--dpkg-manifest", str(manifest)) == 0
    assert asked == [("popt", "1.19-2"), ("zlib", "1:1.3-1")]
    names = {p.name for p in (env["store"] / "objects").iterdir()}
    assert "third-party-src__rsync-2-libsrc__popt_1.19-2.dsc" in names
    assert "third-party-src__rsync-2-libsrc__zlib_1:1.3-1.dsc" in names


def test_a_malformed_manifest_line_is_refused() -> None:
    with pytest.raises(mirror.MirrorError):
        mirror.parse_dpkg_manifest("only\ttwo\n")
