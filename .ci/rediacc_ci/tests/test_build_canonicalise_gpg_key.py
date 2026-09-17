"""Differential: `rediacc_ci.build.canonicalise_gpg_key` against its twin `.ci/scripts/build/canonicalise-gpg-key.sh`.

REAL GPG, NEVER REIMPLEMENTED, on both sides -- same argument as `rediacc_ci.quality.release_key_canonical`'s own header: a Python OpenPGP library would answer a different question than "what does the real gpg binary do to these bytes", and the whole point of this module is that question. One throwaway RSA key (module-scoped: key generation is the slow part, ~2-3s, and nothing here
needs more than one) is generated with `%no-protection` OFF, i.e. genuinely passphrase-protected, because that is the shape the twin's own comment says it is designed for (`PASSPHRASE`, `--pinentry-mode loopback`).

WHY THE FINAL FILE CONTENT IS NOT COMPARED BYTE FOR BYTE. gpg re-encrypts a passphrase-protected secret key with fresh salt on every `--export-secret-keys` call, so the SAME twin run twice on the SAME input produces two different outputs (verified manually: `cmp` disagrees at byte 413 on two successive real runs). A byte comparison between the twin's output and the port's output
would therefore fail even for a port with zero bugs. Equivalence here means: same exit code, same stdout, same stderr, and -- on the two paths that mutate the file -- the resulting file still imports under the same passphrase and still
carries a body whose longest non-armor-marker line is <= 64 columns (i.e. it is
itself canonical, regardless of which implementation produced it).

USAGE-ERROR TEXT IS NOT COMPARED. See `canonicalise_gpg_key`'s own docstring:
the twin's `${1:?msg}` diagnostic embeds bash's own script path and interpreter
line number, which `scripts/lib/shadow-gate.ts` classifies as CHATTER (no `::error::`/`✗`/`ERROR:` marker, no `path:line` shape), and which this port does not attempt to reproduce. Exit code 1 is the ported behaviour.

K=5 LEDGER: `.ci/shadow/w7p6-canonicalise-gpg-key.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "canonicalise-gpg-key.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "canonicalise_gpg_key.py"

PASSPHRASE = "test-pass-w7p6"  # noqa: S105 -- not a secret, a throwaway fixture value
WRONG_PASSPHRASE = "not-the-right-one"  # noqa: S105 -- ditto


def _gpg(
    gnupghome: pathlib.Path, *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GNUPGHOME"] = str(gnupghome)
    return subprocess.run(
        ["gpg", *args],
        env=env,
        capture_output=True,
        text=True,
        input=input_text,
        check=False,
        timeout=60,
    )


@pytest.fixture(scope="module")
def real_key(tmp_path_factory: pytest.TempPathFactory) -> str:
    """One throwaway, genuinely passphrase-protected RSA secret key, armored."""
    gnupghome = tmp_path_factory.mktemp("gpg-real")
    os.chmod(gnupghome, 0o700)
    batch = gnupghome / "genkey.batch"
    batch.write_text(
        "Key-Type: RSA\n"
        "Key-Length: 1024\n"
        "Subkey-Type: RSA\n"
        "Subkey-Length: 1024\n"
        "Name-Real: W7P6 Throwaway\n"
        "Name-Email: w7p6-throwaway@example.invalid\n"
        "Expire-Date: 0\n"
        f"Passphrase: {PASSPHRASE}\n"
        "%commit\n",
        encoding="utf-8",
    )
    gen = _gpg(gnupghome, "--batch", "--pinentry-mode", "loopback", "--gen-key", str(batch))
    assert gen.returncode == 0, f"key generation failed: {gen.stderr}"

    listed = _gpg(gnupghome, "--list-secret-keys", "--with-colons")
    fpr = ""
    for line in listed.stdout.splitlines():
        fields = line.split(":")
        if fields and fields[0] == "fpr" and len(fields) > 9:
            fpr = fields[9]
            break
    assert fpr, f"no fingerprint after generation: {listed.stdout!r}"

    exported = _gpg(
        gnupghome,
        "--batch",
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        PASSPHRASE,
        "--armor",
        "--export-secret-keys",
        fpr,
    )
    assert exported.returncode == 0, "export of the throwaway key failed"
    assert exported.stdout, "export of the throwaway key failed"
    return exported.stdout


def _weld(armored: str) -> str:
    """Join armor lines 5 and 6 (1-indexed) without a newline, the exact welding the twin's own header describes: two Bitwarden halves concatenated raw."""
    lines = armored.split("\n")
    return "\n".join([*lines[:4], lines[4] + lines[5], *lines[6:]])


def _max_body_line_length(armored: str) -> int:
    m = 0
    for line in armored.split("\n"):
        if "-----" in line:
            continue
        m = max(m, len(line))
    return m


def _run(
    subject: pathlib.Path, key_file: pathlib.Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    full_env = dict(os.environ) if env is None else env
    return subprocess.run(
        [*runner, str(subject), str(key_file), *args],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
        timeout=60,
    )


def _assert_same_shape(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str], label: str
) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}\nold stderr: {old.stderr}\nnew stderr: {new.stderr}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def test_no_arguments(tmp_path: pathlib.Path) -> None:
    dummy = tmp_path / "unused"
    old = subprocess.run(
        ["bash", str(TWIN)], capture_output=True, text=True, check=False, timeout=30
    )
    new = subprocess.run(
        ["python3", str(PORT)], capture_output=True, text=True, check=False, timeout=30
    )
    assert old.returncode == 1
    assert new.returncode == 1
    del dummy


def test_missing_file(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does-not-exist.asc"
    old = _run(TWIN, missing)
    new = _run(PORT, missing)
    _assert_same_shape(old, new, "missing-file")
    assert "is missing or empty" in old.stderr


def test_empty_file(tmp_path: pathlib.Path) -> None:
    empty = tmp_path / "empty.asc"
    empty.write_text("", encoding="utf-8")
    old = _run(TWIN, empty)
    new = _run(PORT, empty)
    _assert_same_shape(old, new, "empty-file")
    assert "is missing or empty" in old.stderr


def test_gpg_not_installed(tmp_path: pathlib.Path) -> None:
    """PATH carries `bash`/`python3` (symlinked in, so the RUNNER can still be found) but nothing else -- deliberately not `/usr/bin` wholesale, which would put the real `gpg` right back on PATH and defeat the test."""
    key = tmp_path / "some.asc"
    key.write_text("not a real key but non-empty\n", encoding="utf-8")
    bin_dir = tmp_path / "bin-without-gpg"
    bin_dir.mkdir()
    for tool in ("bash", "python3"):
        found = shutil.which(tool)
        assert found, f"{tool} must be resolvable to build this fixture"
        (bin_dir / tool).symlink_to(found)
    env = {"PATH": str(bin_dir)}
    old = _run(TWIN, key, env=env)
    new = _run(PORT, key, env=env)
    _assert_same_shape(old, new, "gpg-not-installed")
    assert "gpg is not installed" in old.stderr


def test_garbage_key_cannot_import(tmp_path: pathlib.Path) -> None:
    key = tmp_path / "garbage.asc"
    key.write_text("this is not a pgp key\n", encoding="utf-8")
    old = _run(TWIN, key, PASSPHRASE)
    new = _run(PORT, key, PASSPHRASE)
    _assert_same_shape(old, new, "garbage-key")
    assert "gpg could not import the key" in old.stderr


def test_public_key_only_has_no_secret_key(tmp_path: pathlib.Path, real_key: str) -> None:
    # Build a public-only export from the same throwaway key.
    gnupghome = tmp_path / "gpghome"
    gnupghome.mkdir()
    os.chmod(gnupghome, 0o700)
    imp = _gpg(
        gnupghome,
        "--batch",
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        PASSPHRASE,
        "--import",
        "-",
        input_text=real_key,
    )
    assert imp.returncode == 0
    listed = _gpg(gnupghome, "--list-secret-keys", "--with-colons")
    fpr = next(f.split(":")[9] for f in listed.stdout.splitlines() if f.split(":")[0] == "fpr")
    pub = _gpg(gnupghome, "--armor", "--export", fpr)
    assert pub.returncode == 0
    assert pub.stdout

    key_old = tmp_path / "pub-old.asc"
    key_old.write_text(pub.stdout, encoding="utf-8")
    key_new = tmp_path / "pub-new.asc"
    key_new.write_text(pub.stdout, encoding="utf-8")

    old = _run(TWIN, key_old, PASSPHRASE)
    new = _run(PORT, key_new, PASSPHRASE)
    _assert_same_shape(old, new, "public-key-only")
    assert "no secret key after import" in old.stderr


def test_wrong_passphrase_export_fails(tmp_path: pathlib.Path, real_key: str) -> None:
    key_old = tmp_path / "wrong-old.asc"
    key_old.write_text(real_key, encoding="utf-8")
    key_new = tmp_path / "wrong-new.asc"
    key_new.write_text(real_key, encoding="utf-8")

    old = _run(TWIN, key_old, WRONG_PASSPHRASE)
    new = _run(PORT, key_new, WRONG_PASSPHRASE)
    _assert_same_shape(old, new, "wrong-passphrase")
    assert "re-export produced nothing" in old.stderr


def test_clean_key_is_untouched_in_substance(tmp_path: pathlib.Path, real_key: str) -> None:
    assert _max_body_line_length(real_key) <= 64, "fixture itself is not canonical; test is wrong"

    key_old = tmp_path / "clean-old.asc"
    key_old.write_text(real_key, encoding="utf-8")
    key_new = tmp_path / "clean-new.asc"
    key_new.write_text(real_key, encoding="utf-8")

    old = _run(TWIN, key_old, PASSPHRASE)
    new = _run(PORT, key_new, PASSPHRASE)
    _assert_same_shape(old, new, "clean-key")
    assert old.returncode == 0

    for out in (key_old, key_new):
        text = out.read_text(encoding="utf-8")
        assert _max_body_line_length(text) <= 64
        gnupghome = tmp_path / f"verify-{out.name}"
        gnupghome.mkdir()
        os.chmod(gnupghome, 0o700)
        imp = _gpg(
            gnupghome,
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            PASSPHRASE,
            "--import",
            str(out),
        )
        assert imp.returncode == 0, f"{out.name}: re-exported key no longer imports"


def test_welded_key_is_repaired(tmp_path: pathlib.Path, real_key: str) -> None:
    welded = _weld(real_key)
    assert _max_body_line_length(welded) > 64, "fixture did not actually weld; test is wrong"

    key_old = tmp_path / "welded-old.asc"
    key_old.write_text(welded, encoding="utf-8")
    key_new = tmp_path / "welded-new.asc"
    key_new.write_text(welded, encoding="utf-8")

    old = _run(TWIN, key_old, PASSPHRASE)
    new = _run(PORT, key_new, PASSPHRASE)
    _assert_same_shape(old, new, "welded-key")
    assert old.returncode == 10, "fixture stopped exercising the repair path; test is wrong"

    for out in (key_old, key_new):
        text = out.read_text(encoding="utf-8")
        assert _max_body_line_length(text) <= 64, f"{out.name}: still welded after repair"


def test_planted_defect_is_caught() -> None:
    """ANTI-VACUITY. Flip the repair boundary from `> 64` to `>= 64` (an
    off-by-one on the exact column RFC 4880 wraps at) and confirm the differential rejects it on the CLEAN-key case, whose longest line sits exactly on that boundary. Driven red, then the source is restored byte-identical and re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "repaired = _max_body_line_length(key_file) > 64",
        "repaired = _max_body_line_length(key_file) >= 64",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    gnupghome = pathlib.Path(tempfile.mkdtemp())
    try:
        os.chmod(gnupghome, 0o700)
        batch = gnupghome / "genkey.batch"
        batch.write_text(
            "Key-Type: RSA\nKey-Length: 1024\nSubkey-Type: RSA\nSubkey-Length: 1024\n"
            "Name-Real: W7P6 Plant\nName-Email: w7p6-plant@example.invalid\nExpire-Date: 0\n"
            f"Passphrase: {PASSPHRASE}\n%commit\n",
            encoding="utf-8",
        )
        gen = _gpg(gnupghome, "--batch", "--pinentry-mode", "loopback", "--gen-key", str(batch))
        assert gen.returncode == 0
        listed = _gpg(gnupghome, "--list-secret-keys", "--with-colons")
        fpr = next(f.split(":")[9] for f in listed.stdout.splitlines() if f.split(":")[0] == "fpr")
        exported = _gpg(
            gnupghome,
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            PASSPHRASE,
            "--armor",
            "--export-secret-keys",
            fpr,
        )
        assert exported.returncode == 0
        clean_key = exported.stdout
        assert _max_body_line_length(clean_key) == 64, (
            "fixture no longer sits on the boundary; plant is untested"
        )

        with tempfile.TemporaryDirectory() as td:
            mutant_path = pathlib.Path(td) / "mutant.py"
            mutant_path.write_text(mutated, encoding="utf-8")
            key_old = pathlib.Path(td) / "plant-old.asc"
            key_old.write_text(clean_key, encoding="utf-8")
            key_new = pathlib.Path(td) / "plant-new.asc"
            key_new.write_text(clean_key, encoding="utf-8")

            old = _run(TWIN, key_old, PASSPHRASE)
            new = _run(mutant_path, key_new, PASSPHRASE)
            assert old.returncode == 0, "twin must treat the boundary case as already-canonical"
            assert new.returncode == 10, (
                "the mutant did not misclassify the boundary; plant did not fire"
            )
            assert new.returncode != old.returncode, (
                "planted defect was not caught by exit-code comparison"
            )
    finally:
        shutil.rmtree(gnupghome, ignore_errors=True)

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
