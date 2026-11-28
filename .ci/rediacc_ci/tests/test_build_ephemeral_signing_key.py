"""`rediacc_ci.build.ephemeral_signing_key`: the throwaway pair a pull-request run of cd-stage.yml signs with.

REAL GPG, AND THE REAL CHECKS. The claim the module makes is that its pair passes the two fingerprint checks the packaging steps run (`build_pkg_repo._phase1_gpg` for the repository metadata, `build_linux_pkg._setup_gpg_signing` for each deb and rpm), and that those checks still refuse a mixed pair. Both are driven here unmocked with the generated files, so a pair the builders would reject cannot pass, and the refusal is pinned so nobody weakens the check to make a PR run green (agent/plans/PLAN-pr-path-ephemeral-credentials.md, Risks).
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_linux_pkg, build_pkg_repo
from rediacc_ci.build import ephemeral_signing_key as esk

ROOT = paths.repo_root()
RELEASE_PUBLIC = ROOT / ".ci" / "keys" / "gpg-public.asc"

_HOMES: set[str] = set()


@pytest.fixture(scope="module", autouse=True)
def _kill_agents():
    yield
    for home in sorted(_HOMES):
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            subprocess.run(
                ["gpgconf", "--homedir", home, "--kill", "gpg-agent"],
                capture_output=True,
                check=False,
                timeout=30,
            )
    _HOMES.clear()


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> esk.Pair:
    return esk.generate(tmp_path_factory.mktemp("pair-a") / esk.DIR_NAME)


@pytest.fixture(scope="module")
def other(tmp_path_factory: pytest.TempPathFactory) -> esk.Pair:
    return esk.generate(tmp_path_factory.mktemp("pair-b") / esk.DIR_NAME)


def parse_github_env(text: str) -> dict[str, str]:
    """The `$GITHUB_ENV` grammar GitHub reads: `NAME=value`, or `NAME<<DELIM` ... `DELIM`."""
    out: dict[str, str] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            continue
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            name, delim = line.split("<<", 1)
            body: list[str] = []
            while lines[i] != delim:
                body.append(lines[i])
                i += 1
            i += 1
            out[name] = "\n".join(body)
        else:
            name, value = line.split("=", 1)
            out[name] = value
    return out


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """Every env name the builders read or write, recorded so monkeypatch restores it; GNUPGHOME pointed at a private home."""
    for name in (
        "RELEASE_GPG_PRIVATE_KEY",
        "RELEASE_GPG_PASSPHRASE",
        "RELEASE_GPG_PUBLIC_KEY_FILE",
        "NFPM_RPM_KEY_FILE",
        "NFPM_DEB_KEY_FILE",
        "NFPM_RPM_PASSPHRASE",
        "NFPM_DEB_PASSPHRASE",
    ):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "gnupghome"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("GNUPGHOME", str(home))
    _HOMES.add(str(home))
    return home


def _sign_with(
    monkeypatch: pytest.MonkeyPatch, private: pathlib.Path, public: pathlib.Path
) -> None:
    monkeypatch.setenv("RELEASE_GPG_PRIVATE_KEY", private.read_text(encoding="utf-8"))
    monkeypatch.setenv("RELEASE_GPG_PASSPHRASE", "")
    monkeypatch.setenv("RELEASE_GPG_PUBLIC_KEY_FILE", str(public))


def _phase1(tmp_path: pathlib.Path) -> str:
    cleanup: list[str] = []
    try:
        return build_pkg_repo._phase1_gpg(
            str(tmp_path / "repos"),
            False,
            ["--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback"],
            cleanup,
        )
    finally:
        _HOMES.add(os.environ.get("GNUPGHOME", ""))
        _HOMES.update(cleanup)


def test_the_pair_is_a_signing_key_its_public_file_names(pair: esk.Pair) -> None:
    assert pair.private.read_text(encoding="utf-8").startswith(
        "-----BEGIN PGP PRIVATE KEY BLOCK-----"
    )
    assert pair.public.read_text(encoding="utf-8").startswith(
        "-----BEGIN PGP PUBLIC KEY BLOCK-----"
    )
    assert oct(pair.private.stat().st_mode & 0o777) == "0o600"
    assert len(pair.fingerprint) == 40
    assert esk.fingerprint_of(pair.public) == pair.fingerprint
    assert esk.fingerprint_of(RELEASE_PUBLIC) != pair.fingerprint


def test_a_second_call_reuses_the_pair_and_never_mints_another(pair: esk.Pair) -> None:
    # Packages and repository metadata are signed in two steps; two keys would publish rpms their own gpg.key rejects.
    again = esk.ensure(pair.private.parent)
    assert again == pair


def test_two_generations_are_two_different_keys(pair: esk.Pair, other: esk.Pair) -> None:
    assert pair.fingerprint != other.fingerprint


def test_the_env_block_round_trips_through_the_github_env_grammar(pair: esk.Pair) -> None:
    block = esk.env_block(pair)
    got = parse_github_env(block)
    assert got == {
        esk.ENV_PUBLIC_FILE: str(pair.public),
        esk.ENV_PRIVATE: pair.private.read_text(encoding="utf-8").strip("\n"),
        esk.ENV_UNLOCK: "",
    }


def test_main_appends_to_github_env_and_prints_only_the_fingerprint(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = tmp_path / "github_env"
    env_file.write_text("EARLIER=kept\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert esk.main([]) == 0
    first = capsys.readouterr().out
    assert esk.main([]) == 0
    second = capsys.readouterr().out
    fpr = first.strip()
    assert first == second == fpr + "\n"
    assert "PRIVATE KEY" not in first
    got = parse_github_env(env_file.read_text(encoding="utf-8"))
    assert got["EARLIER"] == "kept"
    assert got[esk.ENV_PUBLIC_FILE] == str(tmp_path / esk.DIR_NAME / esk.PUBLIC_NAME)
    assert esk.fingerprint_of(pathlib.Path(got[esk.ENV_PUBLIC_FILE])) == fpr


def test_main_without_github_env_is_a_usage_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert esk.main([]) == esk.EXIT_USAGE
    assert not (tmp_path / esk.DIR_NAME).exists()


def test_main_without_a_directory_is_a_usage_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    assert esk.main([]) == esk.EXIT_USAGE
    assert esk.main(["--bogus"]) == esk.EXIT_USAGE


def test_the_repository_builder_accepts_the_pair_and_publishes_its_public_half(
    pair: esk.Pair, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    _sign_with(monkeypatch, pair.private, pair.public)
    key_id = _phase1(tmp_path)
    assert key_id
    assert pair.fingerprint.endswith(key_id)
    for name in ("apt", "rpm"):
        assert (tmp_path / "repos" / name / "gpg.key").read_bytes() == pair.public.read_bytes()


def test_the_repository_builder_refuses_a_mixed_pair(
    pair: esk.Pair, other: esk.Pair, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    _sign_with(monkeypatch, pair.private, other.public)
    with pytest.raises(build_pkg_repo.RefusalError) as exc:
        _phase1(tmp_path)
    assert "is not the published public key" in str(exc.value)
    assert not (tmp_path / "repos" / "apt" / "gpg.key").exists()


def test_the_repository_builder_refuses_the_throwaway_key_against_the_release_public_key(
    pair: esk.Pair, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default public file is the release one: a throwaway key with RELEASE_GPG_PUBLIC_KEY_FILE unset must not publish.
    _isolate(monkeypatch, tmp_path)
    _sign_with(monkeypatch, pair.private, RELEASE_PUBLIC)
    with pytest.raises(build_pkg_repo.RefusalError) as exc:
        _phase1(tmp_path)
    assert "is not the published public key" in str(exc.value)


def test_the_package_builder_accepts_the_pair(
    pair: esk.Pair, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    _sign_with(monkeypatch, pair.private, pair.public)
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    build_linux_pkg._setup_gpg_signing("rpm", str(build_dir), ROOT)
    key_file = pathlib.Path(os.environ["NFPM_RPM_KEY_FILE"])
    assert key_file.parent == build_dir
    assert "NFPM_RPM_PASSPHRASE" not in os.environ


def test_the_package_builder_refuses_a_mixed_pair(
    pair: esk.Pair, other: esk.Pair, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    _sign_with(monkeypatch, pair.private, other.public)
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    with pytest.raises(build_linux_pkg.RefusalError) as exc:
        build_linux_pkg._setup_gpg_signing("deb", str(build_dir), ROOT)
    assert "is not the published public key" in str(exc.value)
    assert "NFPM_DEB_KEY_FILE" not in os.environ
