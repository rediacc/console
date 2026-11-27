"""A throwaway package-signing key for a pull-request run of cd-stage.yml, so PR-controlled build code never holds the release key.

WHY THIS EXISTS. `rediacc/console` is public, and on a `pull_request` event GitHub runs `.github/workflows/cd-stage.yml` and every script under `.ci/` from the PR's merge commit. The two packaging steps there sign with `RELEASE_GPG_PRIVATE_KEY`; step scoping (PLAN-scope-bws-signing-key-to-consuming-step.md) narrows WHICH steps see that key, not WHETHER a PR run does, because the consuming step executes PR code. agent/plans/PLAN-pr-path-ephemeral-credentials.md D1 gives the PR run a key nobody else trusts instead: cd-stage.yml's `signing: ephemeral` input skips both release-key fetches and runs this module before each packaging step.

WHAT IT DOES. The first call generates an unprotected RSA signing key in a fresh, private GNUPGHOME, exports the armored secret half to `<dir>/private.asc` (0600) and the public half to `<dir>/public.asc`, and removes the keyring. Every call, the first included, then appends to `$GITHUB_ENV`:

  RELEASE_GPG_PUBLIC_KEY_FILE   <dir>/public.asc, the file both builders compare the signing key against and publish as apt/gpg.key and rpm/gpg.key
  BWS_RELEASE_GPG_PRIVATE_KEY   the armored secret half (a delimited multi-line value)
  BWS_RELEASE_GPG_PASSPHRASE    empty: the key carries no protection

THE BWS_ NAMES ARE DELIBERATE. The packaging steps read `env.BWS_RELEASE_GPG_PRIVATE_KEY`, and the `bws-scrub` step after each one blanks exactly those names. Writing the same names keeps one consuming path for both inputs and lets the existing scrub close the throwaway window too, rather than adding a fallback expression to the release path.

A SECOND CALL REUSES THE PAIR, never mints a new one. cd-stage signs the packages in one step and the repository metadata in a later one, and dnf verifies every rpm against the repository's own gpg.key: two different throwaway keys would publish a channel whose packages fail their own repository's check. So the files persist in `$RUNNER_TEMP` for the job and each window re-exports them.

THE FINGERPRINT CHECKS STAY. `build_pkg_repo._phase1_gpg` and `build_linux_pkg._setup_gpg_signing` compare the signing key against `RELEASE_GPG_PUBLIC_KEY_FILE` and refuse a mismatch; this module changes which pair they compare, not whether they compare. `RELEASE_SIGNING_REQUIRED` stays `1` on both paths, so an absent key is still a failure. `.ci/rediacc_ci/tests/test_build_ephemeral_signing_key.py` drives both real checks with the generated pair and pins the refusal of a mixed one.

Usage: PYTHONPATH=.ci python3 -m rediacc_ci.build.ephemeral_signing_key [--dir <dir>]
  <dir> defaults to $RUNNER_TEMP/ephemeral-signing-key. $GITHUB_ENV must be set.
Exit 0 written; 1 gpg failed or the files are unreadable; 2 usage (no $GITHUB_ENV, no directory).
Stdout carries one line, the fingerprint; the key itself is printed nowhere.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile

from rediacc_ci import log

DIR_NAME = "ephemeral-signing-key"
PRIVATE_NAME = "private.asc"
PUBLIC_NAME = "public.asc"

ENV_PUBLIC_FILE = "RELEASE_GPG_PUBLIC_KEY_FILE"
ENV_PRIVATE = "BWS_RELEASE_GPG_PRIVATE_KEY"
ENV_UNLOCK = "BWS_RELEASE_GPG_PASSPHRASE"

KEY_PARAMS = (
    "%no-protection\n"
    "Key-Type: RSA\n"
    "Key-Length: 3072\n"
    "Key-Usage: sign\n"
    "Name-Real: Rediacc pull-request channel (throwaway, untrusted)\n"
    "Name-Email: pr-channel@rediacc.invalid\n"
    "Expire-Date: 2d\n"
    "%commit\n"
)

GPG_TIMEOUT = 120
EXIT_FAIL = 1
EXIT_USAGE = 2


class SigningKeyError(Exception):
    """gpg could not produce or read the pair; the message says which call."""


@dataclasses.dataclass(frozen=True)
class Pair:
    private: pathlib.Path
    public: pathlib.Path
    fingerprint: str


def _gpg(home: pathlib.Path, *args: str, stdin: bytes | None = None) -> bytes:
    env = dict(os.environ)
    env["GNUPGHOME"] = str(home)
    try:
        proc = subprocess.run(
            ["gpg", "--batch", "--no-tty", *args],
            input=stdin,
            env=env,
            capture_output=True,
            check=False,
            timeout=GPG_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = "gpg %s could not run (%s)" % (args[0] if args else "", exc)
        raise SigningKeyError(msg) from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        msg = "gpg %s exited %d: %s" % (args[0] if args else "", proc.returncode, " | ".join(tail))
        raise SigningKeyError(msg)
    return proc.stdout


def _kill_agent(home: pathlib.Path) -> None:
    # gpg starts an agent per home and it outlives the call; one left per run is a leak on a self-hosted runner.
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
            capture_output=True,
            check=False,
            timeout=30,
        )


def fingerprint_of(public: pathlib.Path) -> str:
    """The primary key fingerprint of an armored public key file, read by gpg itself."""
    with tempfile.TemporaryDirectory(prefix="ephemeral-gpg-show-") as tmp:
        home = pathlib.Path(tmp)
        out = _gpg(home, "--with-colons", "--with-fingerprint", "--show-keys", str(public))
        _kill_agent(home)
    for line in out.decode("utf-8", errors="replace").splitlines():
        fields = line.split(":")
        if fields[0] == "fpr" and len(fields) > 9 and fields[9]:
            return fields[9]
    msg = "%s holds no readable public key" % public
    raise SigningKeyError(msg)


def generate(directory: pathlib.Path) -> Pair:
    """A fresh unprotected signing pair under `directory`; the keyring that made it is removed."""
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    with tempfile.TemporaryDirectory(prefix="ephemeral-gpg-") as tmp:
        home = pathlib.Path(tmp)
        os.chmod(home, 0o700)
        try:
            _gpg(home, "--pinentry-mode", "loopback", "--gen-key", stdin=KEY_PARAMS.encode())
            listed = _gpg(home, "--with-colons", "--list-secret-keys")
            fpr = ""
            for line in listed.decode("utf-8", errors="replace").splitlines():
                fields = line.split(":")
                if fields[0] == "fpr" and len(fields) > 9 and fields[9]:
                    fpr = fields[9]
                    break
            if not fpr:
                msg = "gpg generated a key but lists no fingerprint"
                raise SigningKeyError(msg)
            secret = _gpg(
                home, "--pinentry-mode", "loopback", "--armor", "--export-secret-keys", fpr
            )
            public = _gpg(home, "--armor", "--export", fpr)
        finally:
            _kill_agent(home)
    private_path = directory / PRIVATE_NAME
    public_path = directory / PUBLIC_NAME
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(secret)
    public_path.write_bytes(public)
    return Pair(private_path, public_path, fpr)


def ensure(directory: pathlib.Path) -> Pair:
    """The pair under `directory`: reused when both files exist, generated otherwise."""
    private_path = directory / PRIVATE_NAME
    public_path = directory / PUBLIC_NAME
    if private_path.is_file() and public_path.is_file():
        return Pair(private_path, public_path, fingerprint_of(public_path))
    return generate(directory)


def env_block(pair: Pair) -> str:
    """The `$GITHUB_ENV` lines for `pair`, the multi-line secret under a delimiter it cannot contain."""
    private = pair.private.read_text(encoding="utf-8").strip("\n")
    delim = "EPHEMERAL_GPG_%s" % secrets.token_hex(16)
    while delim in private:
        delim = "EPHEMERAL_GPG_%s" % secrets.token_hex(16)
    return "%s=%s\n%s<<%s\n%s\n%s\n%s=\n" % (
        ENV_PUBLIC_FILE,
        pair.public,
        ENV_PRIVATE,
        delim,
        private,
        delim,
        ENV_UNLOCK,
    )


def _parse(argv: list[str]) -> pathlib.Path | None:
    rest = list(argv)
    directory = ""
    while rest:
        flag = rest.pop(0)
        if flag == "--dir" and rest:
            directory = rest.pop(0)
        else:
            return None
    if directory:
        return pathlib.Path(directory)
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    return pathlib.Path(runner_temp) / DIR_NAME if runner_temp else None


def main(argv: list[str]) -> int:
    directory = _parse(argv)
    github_env = os.environ.get("GITHUB_ENV", "")
    if directory is None or not github_env:
        log.error(
            "usage: GITHUB_ENV=<file> PYTHONPATH=.ci python3 -m rediacc_ci.build.ephemeral_signing_key "
            "[--dir <dir>] (the directory defaults to $RUNNER_TEMP/%s)" % DIR_NAME
        )
        return EXIT_USAGE
    try:
        pair = ensure(directory)
        block = env_block(pair)
    except (SigningKeyError, OSError) as exc:
        log.error("throwaway signing key: %s" % exc)
        return EXIT_FAIL
    with open(github_env, "a", encoding="utf-8") as handle:
        handle.write(block)
    log.info(
        "throwaway signing key %s exported for the next step (public half %s); "
        "the release key was not fetched" % (pair.fingerprint, pair.public)
    )
    print(pair.fingerprint, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
