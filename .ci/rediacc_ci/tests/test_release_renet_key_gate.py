"""`rediacc_ci.release.renet_key_gate`: the verdicts over fake `go version -m` output, the image path over a fake docker, and the cached-path ldflags carrying the key. Every key here is an arbitrary well-formed SPKI ED25519 key, never a real one."""

from __future__ import annotations

import base64
import hashlib
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.build import build_renet
from rediacc_ci.build import extract_renet_from_image as extract
from rediacc_ci.release import renet_key_gate as gate
from rediacc_ci.testrun import start_backup_plane as plane
from rediacc_ci.well_known import RENET_REPO

if TYPE_CHECKING:
    import pathlib


def spki(seed: bytes) -> str:
    return base64.b64encode(gate.SPKI_ED25519_HEADER + hashlib.sha256(seed).digest()).decode()


def fp(key: str) -> str:
    return hashlib.sha256(base64.b64decode(key)[-32:]).hexdigest()[:16]


PROD = spki(b"production")
DEV = spki(b"dev")
OTHER = spki(b"other")


def buildinfo(
    key: str | None, *, tags: str = "", version: str = "1.2.3", empty: bool = False
) -> str:
    """`go version -m` output shaped as a real renet build prints it. `empty` bakes `-X sym=` with no value."""
    ldflags = "-s -w -X main.Version=%s " % version
    if empty:
        ldflags += build_renet.KEY_SYMBOL
    elif key:
        ldflags += build_renet.KEY_SYMBOL + key
    lines = [
        "/r/renet: go1.26.6",
        "\tpath\tgithub.com/%s/cmd/renet" % RENET_REPO,
        "\tmod\tgithub.com/%s\t(devel)\t" % RENET_REPO,
        '\tbuild\t-ldflags="%s"' % ldflags,
    ]
    if tags:
        lines.append("\tbuild\t-tags=%s" % tags)
    lines += ["\tbuild\tCGO_ENABLED=0", "\tbuild\tGOOS=linux", ""]
    return "\n".join(lines)


def fake_go(outputs: dict[str, str]):
    """A `run` seam answering `go version -m <binary>` from `outputs`; an unknown binary fails like a non-Go file."""

    def run(argv, **_kw):
        assert argv[:3] == ["go", "version", "-m"]
        text = outputs.get(argv[3])
        if text is None:
            return subprocess.CompletedProcess(argv, 1, "", "could not read Go build info")
        return subprocess.CompletedProcess(argv, 0, text, "")

    return run


def verdict(info_text: str, dev: str | None = None) -> tuple[list[str], str | None]:
    return gate.refusals(gate.parse_build_info(info_text), fp(PROD), dev)


# --------------------------------------------------------------------------- The verdicts


def test_the_production_key_passes() -> None:
    reasons, have = verdict(buildinfo(PROD), fp(DEV))
    assert reasons == []
    assert have == fp(PROD)


def test_no_key_ldflag_is_refused() -> None:
    reasons, have = verdict(buildinfo(None), fp(DEV))
    assert reasons == ["no key ldflag"]
    assert have is None


def test_an_empty_key_is_refused() -> None:
    info = gate.parse_build_info(buildinfo(None, empty=True))
    assert info.key == ""
    reasons, _ = gate.refusals(info, fp(PROD), fp(DEV))
    assert reasons == ["empty key"]


def test_the_dev_key_is_refused_by_name() -> None:
    reasons, have = verdict(buildinfo(DEV), fp(DEV))
    assert reasons == ["DEV key"]
    assert have == fp(DEV)


def test_another_key_is_refused_with_both_fingerprints() -> None:
    reasons, _ = verdict(buildinfo(OTHER), fp(DEV))
    assert reasons == ["key %s is not the production key %s" % (fp(OTHER), fp(PROD))]


def test_nolicense_is_refused_even_with_the_production_key() -> None:
    reasons, _ = verdict(buildinfo(PROD, tags="nolicense"), fp(DEV))
    assert reasons == ["tags=nolicense"]
    reasons, _ = verdict(buildinfo(PROD, tags="netgo,nolicense"), fp(DEV))
    assert reasons == ["tags=nolicense"]
    # Must NOT fire on another tag.
    reasons, _ = verdict(buildinfo(PROD, tags="netgo"), fp(DEV))
    assert reasons == []


def test_a_malformed_baked_key_is_refused_without_printing_it() -> None:
    reasons, have = verdict(buildinfo("bm90YWtleQ=="), fp(DEV))
    assert have is None
    assert len(reasons) == 1
    assert reasons[0].startswith("baked key unreadable")
    assert "bm90YWtleQ" not in reasons[0]


def test_the_last_key_ldflag_wins_as_in_the_linker() -> None:
    text = buildinfo(PROD).replace(
        "Version=1.2.3 ", "Version=1.2.3 %s%s " % (build_renet.KEY_SYMBOL, DEV)
    )
    assert gate.parse_build_info(text).key == PROD


def test_parse_reads_the_version() -> None:
    assert gate.parse_build_info(buildinfo(PROD, version="2.5.0")).version == "2.5.0"


def test_fingerprint_matches_renet_for_raw_and_spki_keys() -> None:
    raw = base64.b64encode(base64.b64decode(PROD)[-32:]).decode()
    assert gate.key_fingerprint(PROD) == gate.key_fingerprint(raw) == fp(PROD)
    with pytest.raises(gate.KeyGateError):
        gate.key_fingerprint("bm90IGEga2V5")


# --------------------------------------------------------------------------- The DEV fingerprint and the expected key


def test_dev_fingerprint_reads_the_public_key_cache(tmp_path: pathlib.Path) -> None:
    assert gate.dev_fingerprint(tmp_path) is None
    cache = tmp_path / gate.DEV_KEY_CACHE
    cache.parent.mkdir(parents=True)
    cache.write_text("ACCOUNT_X25519_PUBLIC_KEY=x\nACCOUNT_ED25519_PUBLIC_KEY=%s\n" % DEV)
    assert gate.dev_fingerprint(tmp_path) == fp(DEV)
    cache.write_text("ACCOUNT_ED25519_PUBLIC_KEY=\n")
    assert gate.dev_fingerprint(tmp_path) is None


def test_the_expected_key_must_be_set_and_not_the_dev_key() -> None:
    assert gate.expected_fingerprint(PROD, fp(DEV)) == fp(PROD)
    with pytest.raises(gate.KeyGateError, match="is not set"):
        gate.expected_fingerprint("", fp(DEV))
    with pytest.raises(gate.KeyGateError, match="DEV key"):
        gate.expected_fingerprint(DEV, fp(DEV))
    with pytest.raises(gate.KeyGateError):
        gate.expected_fingerprint("bm90IGEga2V5", None)


# --------------------------------------------------------------------------- main, end to end over the seams


@pytest.fixture
def dev_cache(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    cache = tmp_path / gate.DEV_KEY_CACHE
    cache.parent.mkdir(parents=True)
    cache.write_text("ACCOUNT_ED25519_PUBLIC_KEY=%s\n" % DEV)
    monkeypatch.setattr(gate.paths, "repo_root", lambda: tmp_path)
    return tmp_path


def test_main_reports_every_binary_and_refuses_on_any(
    dev_cache, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    del dev_cache
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", PROD)
    run = fake_go(
        {
            "/b/prod": buildinfo(PROD),
            "/b/empty": buildinfo(None, empty=True),
            "/b/dev": buildinfo(DEV),
            "/b/nolicense": buildinfo(PROD, tags="nolicense"),
        }
    )
    code = gate.main(["/b/prod", "/b/empty", "/b/dev", "/b/nolicense", "/b/missing"], run)
    out = capsys.readouterr()
    assert code == 1
    assert "ok      /b/prod: production key %s, version 1.2.3" % fp(PROD) in out.out
    assert "REFUSED /b/empty: empty key" in out.out
    assert "REFUSED /b/dev: DEV key" in out.out
    assert "REFUSED /b/nolicense: tags=nolicense" in out.out
    assert "REFUSED /b/missing: cannot read the build info" in out.out
    for key in (PROD, DEV):
        assert key not in out.out + out.err


def test_main_passes_only_when_every_binary_passes(
    dev_cache, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    del dev_cache
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", PROD)
    assert (
        gate.main(["/b/a", "/b/b"], fake_go({"/b/a": buildinfo(PROD), "/b/b": buildinfo(PROD)}))
        == 0
    )
    assert PROD not in capsys.readouterr().out


def test_main_refuses_a_missing_or_dev_expected_key(
    dev_cache, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    del dev_cache
    monkeypatch.delenv("ACCOUNT_ED25519_PUBLIC_KEY", raising=False)
    assert gate.main(["/b/a"], fake_go({"/b/a": buildinfo(PROD)})) == 1
    assert "is not set" in capsys.readouterr().err
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", DEV)
    assert gate.main(["/b/a"], fake_go({"/b/a": buildinfo(DEV)})) == 1
    err = capsys.readouterr().err
    assert "is the DEV key" in err
    assert DEV not in err


def test_usage_errors_exit_2(capsys) -> None:
    assert gate.main([]) == 2
    assert gate.main(["--image"]) == 2
    assert gate.main(["--bogus"]) == 2
    capsys.readouterr()


def test_image_mode_copies_every_renet_and_removes_the_container(
    dev_cache, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    del dev_cache
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", PROD)
    docker: list[list[str]] = []
    copied: dict[str, str] = {}

    def run(argv, **_kw):
        if argv[0] == "docker":
            docker.append(argv[1:])
            if argv[1] == "create":
                return subprocess.CompletedProcess(argv, 0, "cid123\n", "")
            if argv[1] == "cp":
                inside = argv[2].split(":", 1)[1]
                if inside == "/opt/renet/renet-linux-arm64":
                    return subprocess.CompletedProcess(argv, 1, "", "no such file")
                copied[argv[3]] = buildinfo(PROD) if inside == "/app/renet" else buildinfo(DEV)
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return fake_go(copied)(argv)

    assert gate.main(["--image", "ghcr.io/x/renet:t"], run) == 1
    out = capsys.readouterr().out
    assert "ok      ghcr.io/x/renet:t:/app/renet: production key" in out
    assert "REFUSED ghcr.io/x/renet:t:/opt/renet/renet-linux-amd64: DEV key" in out
    assert "REFUSED ghcr.io/x/renet:t:/opt/renet/renet-linux-arm64: not in the image" in out
    assert docker[0] == ["create", "ghcr.io/x/renet:t"]
    assert docker[-1] == ["rm", "cid123"]


def test_start_backup_plane_uses_this_reader() -> None:
    assert plane.SPKI_ED25519_HEADER is gate.SPKI_ED25519_HEADER
    assert plane.key_fingerprint(PROD) == gate.key_fingerprint(PROD)


# --------------------------------------------------------------------------- The cached path's ldflags carry the key


def test_the_cached_path_ldflags_are_build_renets_and_pass_the_gate() -> None:
    """What `extract_renet_from_image` hands `go build` for darwin/windows is `build_renet.ldflags`, and a binary built with it reads back as the production key."""
    flags = build_renet.ldflags("2.5.0", PROD)
    assert flags.startswith("-ldflags=-s -w -X main.Version=2.5.0 ")
    text = buildinfo(None).replace(
        '-ldflags="-s -w -X main.Version=1.2.3 "', '-ldflags="%s"' % flags[len("-ldflags=") :]
    )
    info = gate.parse_build_info(text)
    assert info.key == PROD
    assert info.version == "2.5.0"
    assert gate.refusals(info, fp(PROD), fp(DEV))[0] == []
    # And the cached path refuses rather than build without either input.
    assert extract.cross_refusal("cross", "2.5.0", PROD) is None
    assert extract.cross_refusal("cross", "", PROD) is not None
    assert extract.cross_refusal("all", "2.5.0", "") is not None
