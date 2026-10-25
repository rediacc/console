#!/usr/bin/env python3
"""Licensing enforcement battery: prove that a release-shaped renet binary refuses unlicensed work and accepts a valid license, against a throwaway Ed25519 master key minted for this run only.

    PYTHONPATH=.ci python3 -m rediacc_ci.private.license_e2e

Port of `.ci/scripts/private/license-e2e.sh`, which is deleted. The module IS the local-dev entry point and exactly what CI runs (`ct-tests.yml`, License Enforcement job); there is no CI-only variant to drift from.

WHY IT NEEDS NO VM, NO BTRFS, NO LUKS, NO DOCKER. The license gate fires before any storage work: `repository create` checks it before the `--password-stdin` check, `repository up` before the repo lock, network detection and mount. An accepted license therefore shows up as "renet got past the gate and then failed at the SAME later point an unlicensed-build twin fails at", and every scenario is a sub-second binary invocation against an empty scratch directory.

WHAT NEEDS PRIVILEGE. Only installing the license files: `license.RepoLicenseDir` (`/var/lib/rediacc/license/repos`) is a hardcoded constant in renet with no env override, so the fixtures go there through `sudo -n` (`rm`, `mkdir`, `cp`, `chmod`, in the argv the bash used). renet itself runs unprivileged except for `repository license-status`, which persists chain state and runs under sudo. A pre-existing `chain-state.json` is backed up and restored, and only the battery's own repo directories are removed.

PROVING THE INSTRUMENT. The battery runs three times against three binaries built from the same source, and the two controls MUST fail: `enforcing` (baked with the ephemeral master key, every scenario passes), `nolicense` (built with `-tags nolicense`, S1 must FAIL) and `wrong-key` (baked with a stranger's public key, S2 must FAIL). A battery that cannot fail would be worthless.

ENVIRONMENT. `RENET_SRC` points the battery at another renet checkout (default `private/renet`); `LICENSE_E2E_MASTER_PUB` plus `LICENSE_E2E_MASTER_PRIV` (base64 SPKI/PKCS8) reuse a caller-supplied ephemeral pair; `TMPDIR` places the scratch directory.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_private_license_e2e.py`).

  1. A FAILED PREFLIGHT NO LONGER WIPES THE LICENSE STORE. The bash installed `trap cleanup EXIT` BEFORE `preflight` while `LICENSE_ROOT_PREEXISTED` still held its initial 0, so a preflight failure (a missing `go`, a missing embed tree, no passwordless sudo) ran the "the store did not exist before this run" arm and executed `sudo rm -rf /var/lib/rediacc/license`: every real repo license and the chain state on the machine. Cleanup now exists only once the store has been probed.
  2. NO `jq`. The bash needed it for four reads (the minted key pair, the key fingerprint and the `license-status` array); JSON is parsed in-process and the preflight no longer demands the tool.
  3. A FAILED RESTORE IS REPORTED. The cleanup ran under `set +e` and discarded every exit code, so a chain-state restore that failed left the operator's state replaced and said nothing; the failure is a warning naming the file.

SET -E SEMANTICS ARE KEPT. The bash ran `run_battery` inside `if`, where `set -e` is off, so a fixture install failing mid-battery was ignored there and fatal in `install_fixtures`. `_Battery.errexit` mirrors that: fatal outside the battery, ignored inside it.
"""

from __future__ import annotations

import contextlib
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING

from rediacc_ci import log

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

# U+2014 is spelled as an escape so no em dash is typed into a file under `.ci/rediacc_ci`; the log lines still carry the character, as the bash did.
EM_DASH = "\u2014"

KEYS_LDPATH = "github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey"

# Installed-license root. Hardcoded in renet; not overridable.
LICENSE_ROOT = "/var/lib/rediacc/license"
# How long a run waits for another battery on the same store before failing (each run measures about 15-55 s).
LOCK_WAIT_S = 600

# Repo identifiers owned by this battery. The create/up scenarios accept any name; the chain-state scenario goes through `repository license-status`, which only looks at datastore entries shaped like a GUID.
REPO_PREFIX = "license-e2e"
CHAIN_GUID = "1ce1ce2e-0000-0000-0000-000000000001"

# Wave-2 scenarios. All go through `repository license-status`, the only modeFull vehicle that needs no real repo, so they need GUID-shaped names. FORK_GUID is ONE guid used in TWO datastores: a datastore fork does not remint repository GUIDs, so a same-node fork really does put two live repos with the same guid on one host.
FORK_GUID = "1ce1ce2e-0000-0000-0000-000000000002"
SEQ_GUID_A = "1ce1ce2e-0000-0000-0000-00000000000a"
SEQ_GUID_B = "1ce1ce2e-0000-0000-0000-00000000000b"
FP_GUID = "1ce1ce2e-0000-0000-0000-00000000000f"

# Restore scenarios (S11). The target and its lineage are GUIDs because the verb refuses anything else before it reaches the license step. Neither has an image: restore judges the target first, and an absent image passes.
RESTORE_GUID = "1ce1ce2e-0000-0000-0000-0000000000c1"
RESTORE_LINEAGE = "1ce1ce2e-0000-0000-0000-0000000000c2"
RESTORE_SNAPSHOT = "snap-license-e2e"

# Datastore identities. UUID-shaped because that is what `datastore create` mints and what the store's path-segment guard accepts.
PARENT_DS_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
FORK_DS_ID = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"

# The attribution line renet logs ONLY after a license validates. Its presence is the positive proof that the real validator ran and succeeded; a nolicense stub never emits it.
ATTRIBUTION = "Licensed to: license-e2e@rediacc.invalid"
# Where an accepted create/up lands instead: the same failure an unlicensed build reaches.
CREATE_TAIL = "--password-stdin is required"
UP_TAIL = "no password or keyfile provided"

_PAYLOAD_RE = re.compile(rb'\{"code".*\}')


class _AbortError(Exception):
    """A command failed where the bash ran under `set -e`: the script ends with that status."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


def _exec(cmd: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run` that turns a command that cannot start into the status bash gives it (127 not found, 126 not executable) after a one-line diagnostic, where Python would raise."""
    try:
        return subprocess.run(list(cmd), check=False, **kwargs)
    except PermissionError as exc:
        print("%s: %s" % (cmd[0], exc.strerror), file=sys.stderr, flush=True)
        return subprocess.CompletedProcess(list(cmd), 126, b"", b"")
    except OSError as exc:
        print("%s: %s" % (cmd[0], exc.strerror), file=sys.stderr, flush=True)
        return subprocess.CompletedProcess(list(cmd), 127, b"", b"")


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location (`parents[3]`), matching the bash `get_repo_root`."""
    # This file: <root>/.ci/rediacc_ci/private/license_e2e.py
    return pathlib.Path(__file__).resolve().parents[3]


def jq_raw(document: object, *keys: object) -> str:
    """`jq -r` over a path of keys or indexes: a missing value prints `null`, a string prints raw, anything else as JSON."""
    value: Any = document
    for key in keys:
        if isinstance(key, int) and isinstance(value, list):
            value = value[key] if -len(value) <= key < len(value) else None
        elif isinstance(key, str) and isinstance(value, dict):
            value = value.get(key)
        elif value is None:
            value = None
        else:
            raise ValueError("cannot index %s with %r" % (type(value).__name__, key))
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _payload(stderr: bytes) -> str:
    """`grep -o '{"code".*}' stderr || echo '<fallback>'`: every greedy match, one per matching line."""
    found = [m.group(0) for line in stderr.splitlines() if (m := _PAYLOAD_RE.search(line))]
    return b"\n".join(found).decode("utf-8", "replace")


def _head_flat(stderr: bytes) -> str:
    """`head -c 300 stderr | tr '\\n' ' '`: the first 300 bytes with newlines turned into spaces."""
    return stderr[:300].replace(b"\n", b" ").decode("utf-8", "replace")


class Battery:
    """One run of the battery: scratch tree, keys, three binaries and the scenario table."""

    def __init__(
        self,
        *,
        license_root: str = LICENSE_ROOT,
        environ: dict[str, str] | None = None,
        geteuid: int | None = None,
    ) -> None:
        self.env = dict(os.environ if environ is None else environ)
        self.console = console_root()
        self.license_root = license_root
        self.repo_license_root = license_root + "/repos"
        self.datastore_license_root = license_root + "/datastores"
        self.chain_state = license_root + "/chain-state.json"
        self.renet_src = self.env.get("RENET_SRC") or str(self.console / "private" / "renet")
        self.mint_src = str(self.console / ".ci" / "scripts" / "private" / "license-mint")
        euid = os.geteuid() if geteuid is None else geteuid
        self.sudo: list[str] = [] if euid == 0 else ["sudo", "-n"]

        self.work = ""
        self.preexisted = False
        self.chain_backup = ""
        self.chain_unbacked = False
        self.errexit = True
        self.label = ""
        self.failed: list[str] = []
        self.renet_code = 0
        self.mint_bin = ""
        self.master_pub = ""
        self.master_priv = ""
        self.stranger_priv = ""
        self.master_key_id = ""

    # ------------------------------------------------------------------ process helpers

    def _fatal(self, status: int) -> None:
        if status != 0 and self.errexit:
            raise _AbortError(status)

    def _sudo(self, *args: str) -> int:
        """`$SUDO <args>`, inheriting the streams. Fatal outside the battery, ignored inside it."""
        status = _exec([*self.sudo, *args]).returncode
        self._fatal(status)
        return status

    def _back_up_chain_state(self) -> None:
        """Copy the operator's chain state aside. `chain_backup` is set only once the copy exists, and `chain_unbacked` stays set until then, so a failed copy leaves the real file alone at cleanup instead of deleting it (review 797d99c0.1)."""
        if not (self.preexisted and os.path.isfile(self.chain_state)):
            return
        self.chain_unbacked = True
        backup = self.work + "/chain-state.backup.json"
        # cp -p, not a copy through Python: renet writes this file 0600 root-owned, and the restore has to put back the same mode.
        # Outside the battery a failed copy aborts the run (as the bash `set -e` did). Inside it `_sudo` returns the status instead, so the status is checked here: `chain_unbacked` stays set after a failed copy, which keeps cleanup from touching the real file.
        if self._sudo("cp", "-p", self.chain_state, backup) != 0:
            log.warn("Could not back up the existing chain state; it is left untouched at exit")
            return
        self.chain_backup = backup
        self.chain_unbacked = False
        log.info("Backed up the existing chain state; it is restored on exit")

    # ------------------------------------------------------------------ cleanup

    def cleanup(self) -> None:
        """The EXIT trap. The license store is restored BEFORE the scratch directory is removed: the chain-state backup lives inside it."""
        if not self.preexisted:
            _exec([*self.sudo, "rm", "-rf", self.license_root])
        else:
            repos = sorted(glob.glob(self.repo_license_root + "/" + REPO_PREFIX + "-*"))
            _exec(
                [
                    *self.sudo,
                    "rm",
                    "-rf",
                    *(repos or [self.repo_license_root + "/" + REPO_PREFIX + "-*"]),
                    self.repo_license_root + "/" + CHAIN_GUID,
                    self.repo_license_root + "/" + SEQ_GUID_A,
                    self.repo_license_root + "/" + SEQ_GUID_B,
                    self.repo_license_root + "/" + FP_GUID,
                    self.repo_license_root + "/" + RESTORE_GUID,
                ]
            )
            _exec(
                [
                    *self.sudo,
                    "rm",
                    "-rf",
                    self.datastore_license_root + "/" + PARENT_DS_ID,
                    self.datastore_license_root + "/" + FORK_DS_ID,
                ]
            )
            if self.chain_backup and os.path.isfile(self.chain_backup):
                restored = _exec(
                    [*self.sudo, "cp", "-p", self.chain_backup, self.chain_state]
                ).returncode
                if restored != 0:
                    log.warn(
                        "could not restore %s from %s (exit %d)"
                        % (self.chain_state, self.chain_backup, restored)
                    )
            elif self.chain_unbacked:
                log.warn("no backup of %s was made, so it is left as it is" % self.chain_state)
            else:
                _exec([*self.sudo, "rm", "-f", self.chain_state])
        if self.work:
            # Never leave an enforcing renet anywhere reachable.
            shutil.rmtree(self.work, ignore_errors=True)

    # ------------------------------------------------------------------ preflight and build

    def preflight(self) -> None:
        missing = False
        if shutil.which("go") is None:
            log.error("go is required but not on PATH")
            missing = True
        arch = self._goarch()
        if not os.path.isdir("%s/pkg/embed/assets/%s/base" % (self.renet_src, arch)):
            log.error(
                "renet embedded assets missing at pkg/embed/assets/%s/base %s run "
                "'cd private/renet && ./build.sh embed_assets'" % (arch, EM_DASH)
            )
            missing = True
        probe = _exec([*self.sudo, "true"], stderr=subprocess.DEVNULL)
        if probe.returncode != 0:
            log.error(
                "passwordless sudo is required to install licenses under %s "
                "(the path is hardcoded in renet)" % self.repo_license_root
            )
            missing = True
        if missing:
            raise _AbortError(1)

    @staticmethod
    def _goarch() -> str:
        """`go env GOARCH 2>/dev/null || echo amd64`."""
        try:
            proc = subprocess.run(
                ["go", "env", "GOARCH"], capture_output=True, text=True, check=False
            )
        except OSError:
            return "amd64"
        if proc.returncode != 0:
            return "amd64"
        return proc.stdout.rstrip("\n")

    def build_renet(self, out: str, pubkey: str, *extra: str) -> None:
        """Built with `go build` on purpose: the repo's build wrappers short-circuit on an existing output or bake a key this battery did not choose."""
        self._fatal(
            _exec(
                [
                    "go",
                    "build",
                    "-ldflags",
                    "-X %s=%s" % (KEYS_LDPATH, pubkey),
                    *extra,
                    "-o",
                    out,
                    "./cmd/renet",
                ],
                cwd=self.renet_src,
            ).returncode
        )

    # ------------------------------------------------------------------ fixtures

    def mint(self, repo: str, *flags: str) -> None:
        """Write `<keyId>.json` into a staging dir; the minter's stdout is discarded."""
        shutil.rmtree(self.work + "/stage", ignore_errors=True)
        status = _exec(
            [
                self.mint_bin,
                "-master-key",
                self.master_priv,
                "-out-dir",
                self.work + "/stage",
                "-repo",
                repo,
                *flags,
            ],
            stdout=subprocess.DEVNULL,
        ).returncode
        self._fatal(status)

    def _stage_files(self) -> list[str]:
        """`"$WORK"/stage/*.json` as bash expands it: sorted, and the literal pattern when nothing matches (so `cp` fails the same way)."""
        pattern = self.work + "/stage/*.json"
        return sorted(glob.glob(pattern)) or [pattern]

    def install_license(self, repo: str) -> None:
        """Move the staged blob into the real license store, scoped to this repo's own directory."""
        target = self.repo_license_root + "/" + repo
        self._sudo("rm", "-rf", target)
        self._sudo("mkdir", "-p", target)
        self._sudo("cp", *self._stage_files(), target + "/")
        # World-readable so the unprivileged renet invocations can read them, as a real install is. The two parents are made traversable NON-recursively so no other repo's contents are touched.
        self._sudo("chmod", "a+rX", self.license_root, self.repo_license_root)
        self._sudo("chmod", "-R", "a+rX", target)

    def install_scoped_license(self, ds_id: str, repo: str) -> None:
        """Install the staged blob into the DATASTORE-SCOPED population: `datastores/<dsId>/repos/<guid>/`."""
        target = "%s/%s/repos/%s" % (self.datastore_license_root, ds_id, repo)
        self._sudo("rm", "-rf", target)
        self._sudo("mkdir", "-p", target)
        self._sudo("cp", *self._stage_files(), target + "/")
        self._sudo(
            "chmod",
            "a+rX",
            self.license_root,
            self.datastore_license_root,
            "%s/%s" % (self.datastore_license_root, ds_id),
            "%s/%s/repos" % (self.datastore_license_root, ds_id),
        )
        self._sudo("chmod", "-R", "a+rX", target)

    def describe_datastore(self, path: str, ds_id: str) -> None:
        """Write the on-datastore descriptor that gives a datastore its identity."""
        os.makedirs(path + "/.rediacc", exist_ok=True)
        os.makedirs(path + "/repositories", exist_ok=True)
        with open(path + "/.rediacc/datastore.json", "w", encoding="utf-8") as fh:
            fh.write(
                '{\n  "name": "license-e2e",\n  "datastoreId": "%s",\n  "backend": "local"\n}\n'
                % ds_id
            )

    def install_fixtures(self) -> None:
        log.step("Minting and installing license fixtures...")
        # S1 deliberately has NO license installed.
        fixtures: list[tuple[str, tuple[str, ...]]] = [
            ("valid", ()),
            ("delegated", ("-delegate",)),
            # Signed by a stranger while still claiming the master key's fingerprint.
            ("forged", ("-forge-signer", self.stranger_priv, "-key-id", self.master_key_id)),
            # A delegation cert the master never signed.
            ("rogue-cert", ("-delegate", "-cert-signer", self.stranger_priv)),
            ("expired", ("-hard-expires", "-1h")),
            ("cert-expired", ("-delegate", "-cert-valid-from", "-48h", "-cert-valid-until", "-1h")),
            # Machine mismatch only bites once the 40-day grace from issuedAt has run out, so this one is backdated and its twin is not.
            ("wrong-machine", ("-machine", "not-this-machine", "-issued-at", "-1200h")),
            ("machine-grace", ("-machine", "not-this-machine", "-issued-at", "-24h")),
        ]
        for name, flags in fixtures:
            self.mint("%s-%s" % (REPO_PREFIX, name), *flags)
            self.install_license("%s-%s" % (REPO_PREFIX, name))

    # ------------------------------------------------------------------ assertions

    def record_pass(self, scenario: str, detail: str) -> None:
        log.info("[%s] %s PASS %s %s" % (self.label, scenario, EM_DASH, detail))

    def record_fail(self, scenario: str, detail: str) -> None:
        self.failed.append(scenario)
        log.error("[%s] %s FAIL %s %s" % (self.label, scenario, EM_DASH, detail))

    def run_renet(self, *cmd: str) -> bytes:
        """Drive the binary DIRECTLY, never through rdc: the CLI's exit-10 recovery framework would retry and rewrite the failure this battery asserts on. stdout and stderr are captured separately; the stderr bytes are returned."""
        stdout_path = self.work + "/stdout.txt"
        stderr_path = self.work + "/stderr.txt"
        with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
            try:
                self.renet_code = _exec(cmd, stdout=out, stderr=err).returncode
            except PermissionError as exc:
                err.write(("%s: %s\n" % (cmd[0], exc.strerror)).encode())
                self.renet_code = 126
            except OSError as exc:
                err.write(("%s: %s\n" % (cmd[0], exc.strerror)).encode())
                self.renet_code = 127
        with open(stderr_path, "rb") as fh:
            return fh.read()

    def assert_rejected(self, scenario: str, reason: str, *cmd: str) -> None:
        stderr = self.run_renet(*cmd)
        if self.renet_code != 10:
            self.record_fail(
                scenario,
                "expected exit 10, got %d; stderr: %s" % (self.renet_code, _head_flat(stderr)),
            )
            return
        if b'"reason":"%s"' % reason.encode() not in stderr:
            self.record_fail(
                scenario,
                "exit 10 but reason was not '%s': %s"
                % (reason, _payload(stderr) or "<no LICENSE_REQUIRED payload>"),
            )
            return
        self.record_pass(scenario, "exit 10, reason=%s" % reason)

    def assert_accepted(self, scenario: str, tail: str, *cmd: str) -> None:
        """Acceptance is three facts, not one: the gate did not fire, the validator positively reported success, and the command then failed at the SAME later point an unlicensed build reaches."""
        stderr = self.run_renet(*cmd)
        if self.renet_code == 10:
            self.record_fail(
                scenario,
                "license gate rejected a valid license: %s" % (_payload(stderr) or "<no payload>"),
            )
            return
        if b"LICENSE_REQUIRED" in stderr:
            self.record_fail(
                scenario, "LICENSE_REQUIRED surfaced despite exit %d" % self.renet_code
            )
            return
        if ATTRIBUTION.encode() not in stderr:
            self.record_fail(
                scenario,
                "validator never reported acceptance ('%s' absent) %s the license was not "
                "actually validated" % (ATTRIBUTION, EM_DASH),
            )
            return
        if tail.encode() not in stderr:
            self.record_fail(
                scenario,
                "accepted but did not reach the expected later failure '%s': %s"
                % (tail, _head_flat(stderr)),
            )
            return
        self.record_pass(scenario, "accepted (exit %d at '%s')" % (self.renet_code, tail))

    def license_status(self, binary: str, datastore: str | None = None) -> str:
        """`repository license-status`, the only modeFull vehicle that needs no real repo. Runs privileged because validation persists chain state under the license root. Returns what `jq -r '.[0].status'` printed (empty when jq printed nothing)."""
        ds = datastore or self.work + "/ds-chain"
        with open(self.work + "/stderr.txt", "wb") as err:
            proc = _exec(
                [
                    *self.sudo,
                    binary,
                    "repository",
                    "license-status",
                    "--datastore",
                    ds,
                    "--output",
                    "json",
                ],
                stdout=subprocess.PIPE,
                stderr=err,
            )
        try:
            document = json.loads(proc.stdout)
        except ValueError:
            return ""
        try:
            return jq_raw(document, 0, "status")
        except ValueError:
            return ""

    def assert_status(
        self, scenario: str, want: str, binary: str, datastore: str, description: str
    ) -> None:
        seen = self.license_status(binary, datastore)
        if seen != want:
            self.record_fail(
                scenario, "%s: expected status '%s', got '%s'" % (description, want, seen)
            )
            return
        self.record_pass(scenario, "%s (status=%s)" % (description, want))

    # ------------------------------------------------------------------ the battery

    def run_battery(self, binary: str, label: str) -> bool:
        """Every scenario against one binary. True when none failed. `set -e` is off for the whole run, as it was in the bash (`if run_battery`)."""
        self.errexit = False
        try:
            self._scenarios(binary, label)
        finally:
            self.errexit = True
        return not self.failed

    def assert_restore_refused_plainly(self, scenario: str, needle: str, *cmd: str) -> None:
        """A refusal that is NOT LICENSE_REQUIRED: exit 1 with `needle` in the message. Exit 10 here would send the CLI into a reissue that hands back the same license."""
        stderr = self.run_renet(*cmd)
        if self.renet_code == 10 or b"LICENSE_REQUIRED" in stderr:
            self.record_fail(
                scenario,
                "expected a plain refusal, got the typed license error (exit %d): %s"
                % (self.renet_code, _head_flat(stderr)),
            )
        elif self.renet_code != 1:
            self.record_fail(
                scenario,
                "expected exit 1, got %d; stderr: %s" % (self.renet_code, _head_flat(stderr)),
            )
        elif needle.encode() not in self.stdout_and(stderr):
            self.record_fail(
                scenario, "exit 1 but '%s' was not reported: %s" % (needle, _head_flat(stderr))
            )
        else:
            self.record_pass(scenario, "exit 1, refused without LICENSE_REQUIRED (%s)" % needle)

    def stdout_and(self, stderr: bytes) -> bytes:
        """The restore record on stdout carries the reason in prose; stderr carries the error line."""
        with open(self.work + "/stdout.txt", "rb") as fh:
            return fh.read() + stderr

    def _scenarios(self, binary: str, label: str) -> None:
        self.label = label
        self.failed = []
        work = self.work
        create = [
            binary,
            "repository",
            "create",
            "--network-id",
            "77",
            "--size",
            "1G",
            "--datastore",
            work + "/ds",
            "--skip-mount",
            "--name",
        ]
        up = [binary, "repository", "up", "--datastore", work + "/ds", "--name"]

        # S1: nothing installed at all.
        self.assert_rejected("S1", "missing", *create, REPO_PREFIX + "-absent")
        # S2: a license signed directly by the baked master key.
        self.assert_accepted("S2", CREATE_TAIL, *create, REPO_PREFIX + "-valid")
        # S3: signed by a delegated key, authorized by a master-signed cert; the file is named after the DELEGATED key, not the baked one.
        self.assert_accepted("S3", CREATE_TAIL, *create, REPO_PREFIX + "-delegated")
        # S4: a stranger's signature under the master key's name.
        self.assert_rejected("S4", "invalid_signature", *create, REPO_PREFIX + "-forged")
        # S4b: a delegation cert signed by someone who is not the master.
        self.assert_rejected("S4b", "cert_invalid", *create, REPO_PREFIX + "-rogue-cert")
        # S5: the tier split. An expired license cannot create, but must not stop a user operating data they already have.
        self.assert_rejected("S5a", "expired", *create, REPO_PREFIX + "-expired")
        self.assert_accepted("S5b", UP_TAIL, *up, REPO_PREFIX + "-expired")
        # S5c/S5d: the same split for the delegation cert's validity window.
        self.assert_rejected("S5c", "cert_expired", *create, REPO_PREFIX + "-cert-expired")
        self.assert_accepted("S5d", UP_TAIL, *up, REPO_PREFIX + "-cert-expired")

        # S6: sequence regression with the chain state on real disk. Asserted on the status field, because the full tier only wraps missing/expired into a LICENSE_REQUIRED error; every tamper reason reaches the caller as a plain exit 1.
        chain = ("-chain-hash", "-subscription", REPO_PREFIX + "-chain")
        self.mint(CHAIN_GUID, "-sequence", "2", *chain)
        self.install_license(CHAIN_GUID)
        seen = self.license_status(binary)
        if seen != "valid":
            self.record_fail("S6a", "sequence 2 should validate, got '%s'" % seen)
        else:
            self.record_pass("S6a", "sequence 2 accepted and recorded in chain state")
        self.mint(CHAIN_GUID, "-sequence", "1", *chain)
        self.install_license(CHAIN_GUID)
        seen = self.license_status(binary)
        if seen != "sequence_regression":
            self.record_fail("S6b", "rolling back to sequence 1 should be refused, got '%s'" % seen)
        else:
            self.record_pass("S6b", "sequence 1 refused after sequence 2 (sequence_regression)")

        # S8: FORK METERING through the datastore-scoped license store.
        self.mint(FORK_GUID, "-datastore-id", PARENT_DS_ID)
        self.install_scoped_license(PARENT_DS_ID, FORK_GUID)
        self.assert_status(
            "S8a",
            "valid",
            binary,
            work + "/ds-parent",
            "a repo in the parent datastore validates under the parent's scope",
        )
        # The fork: SAME repo guid, datastore identity reminted. Its scope is empty, so validation reports `missing`, which the CLI auto-recovers by reissuing; that reissue IS the metering event.
        self.assert_status(
            "S8b",
            "missing",
            binary,
            work + "/ds-fork",
            "the same guid in the FORKED datastore finds no license and must re-meter",
        )
        self.mint(FORK_GUID, "-datastore-id", FORK_DS_ID)
        self.install_scoped_license(FORK_DS_ID, FORK_GUID)
        self.assert_status(
            "S8c",
            "valid",
            binary,
            work + "/ds-fork",
            "a license issued for the fork validates in the fork",
        )
        self.assert_status(
            "S8d",
            "valid",
            binary,
            work + "/ds-parent",
            "the parent's license survived the fork's issuance",
        )
        # Hand-copying the PARENT's blob into the FORK's scoped directory: the payload's datastoreId defeats it, as identity_mismatch (fail-fast, never auto-reissued).
        self.mint(FORK_GUID, "-datastore-id", PARENT_DS_ID)
        self.install_scoped_license(FORK_DS_ID, FORK_GUID)
        self.assert_status(
            "S8e",
            "identity_mismatch",
            binary,
            work + "/ds-fork",
            "a license copied from the parent into the fork is refused as tampering",
        )

        # S9: PER-REPOSITORY chain scope. A -> B -> A is the exact repro of the false sequence_regression.
        multi = ("-chain-hash", "-subscription", REPO_PREFIX + "-multi")
        self.mint(SEQ_GUID_A, "-sequence", "5", *multi)
        self.install_license(SEQ_GUID_A)
        self.mint(SEQ_GUID_B, "-sequence", "9", *multi)
        self.install_license(SEQ_GUID_B)
        self.assert_status(
            "S9a", "valid", binary, work + "/ds-seq-a", "repo A (sequence 5) validates"
        )
        self.assert_status(
            "S9b", "valid", binary, work + "/ds-seq-b", "repo B (sequence 9) validates"
        )
        self.assert_status(
            "S9c",
            "valid",
            binary,
            work + "/ds-seq-a",
            "repo A still validates after repo B advanced the subscription ledger",
        )
        # Replay protection WITHIN a repo is unchanged.
        self.mint(SEQ_GUID_A, "-sequence", "2", *multi)
        self.install_license(SEQ_GUID_A)
        self.assert_status(
            "S9d",
            "sequence_regression",
            binary,
            work + "/ds-seq-a",
            "rolling repo A back to an older sequence is still refused",
        )

        # S10: the storage fingerprint actually FIRES.
        self.mint(
            FP_GUID, "-storage-fingerprint", "auto:%s/ds-fp/repositories/%s" % (work, FP_GUID)
        )
        self.install_license(FP_GUID)
        self.assert_status(
            "S10a",
            "valid",
            binary,
            work + "/ds-fp",
            "a fingerprint minted by the shared helper is recognised by the validator",
        )
        self.mint(FP_GUID, "-storage-fingerprint", "dir:1:2:3")
        self.install_license(FP_GUID)
        self.assert_status(
            "S10b",
            "identity_mismatch",
            binary,
            work + "/ds-fp",
            "a stale fingerprint is refused (the check is live, not dormant)",
        )

        # S7: a license minted for a different machine, past the 40-day grace.
        self.assert_rejected("S7", "machine_mismatch", *create, REPO_PREFIX + "-wrong-machine")
        # S7b: the same mismatch inside the grace window is deliberately tolerated, so a VM migration does not brick a repo.
        self.assert_accepted("S7b", CREATE_TAIL, *create, REPO_PREFIX + "-machine-grace")

        # S11: RESTORE. backup_restore is tier none (a lapsed license must never lock a customer out of disaster recovery), but the verb needs a license of the requested LINEAGE as the credential for its storage session. The retention window is enforced by the account server when the session is minted, so it is outside a battery that talks to no server.
        restore = [
            binary,
            "backup",
            "restore",
            "--datastore",
            work + "/ds-restore",
            "--repo",
            RESTORE_GUID,
            "--lineage",
            RESTORE_LINEAGE,
            "--at",
            RESTORE_SNAPSHOT,
        ]
        # S11a: no license of the lineage on the machine is the typed refusal the CLI's recovery path acts on.
        self._sudo("rm", "-rf", self.repo_license_root + "/" + RESTORE_GUID)
        self.assert_rejected("S11a", "missing", *restore)
        # S11b: the target's own license names another lineage (none, here). Reissuing would return the same blob, so this is a plain refusal.
        self.mint(RESTORE_GUID, "-renewal-url", "http://127.0.0.1:1/license/renew")
        self.install_license(RESTORE_GUID)
        self.assert_restore_refused_plainly("S11b", "belongs to lineage", *restore)

    def expect_control_failure(self, binary: str, label: str, required: str) -> bool:
        """Run the battery against a binary that MUST NOT pass it. False when it passes, or fails for the wrong reason."""
        if self.run_battery(binary, label):
            log.error(
                "CONTROL FAILED: the %s binary passed the battery. The battery cannot detect a "
                "broken build and is worthless as written." % label
            )
            return False
        if required not in self.failed:
            log.error(
                "CONTROL FAILED: the %s binary failed the battery, but %s passed. That scenario "
                "is what detects this defect class; failures were: %s"
                % (label, required, " ".join(self.failed))
            )
            return False
        log.info(
            "Control OK: %s fails the battery at %s (with %s)"
            % (label, required, " ".join(self.failed))
        )
        return True

    # ------------------------------------------------------------------ main

    def _mint_json(self, *args: str) -> object:
        """Run the minter, parse its stdout as JSON. A failed minter or unparsable output ends the run, as `$(... | jq)` did under `set -e`."""
        proc = _exec([self.mint_bin, *args], stdout=subprocess.PIPE)
        self._fatal(proc.returncode)
        try:
            return json.loads(proc.stdout)
        except ValueError as exc:
            raise _AbortError(2) from exc

    def run(self) -> int:
        """The whole script, from preflight to the closing verdict. Returns the exit status."""
        try:
            return self._run()
        except _AbortError as stop:
            return stop.status

    def _run(self) -> int:
        self.preflight()

        base = self.env.get("TMPDIR") or "/tmp"
        self.work = tempfile.mkdtemp(prefix="license-e2e.", dir=base)
        # The store is probed BEFORE anything can register cleanup: see Rule T 1 in the module docstring.
        self.preexisted = os.path.isdir(self.license_root)
        try:
            return self._battery_run()
        finally:
            self.cleanup()

    def _battery_run(self) -> int:
        work = self.work
        os.makedirs(work + "/ds", exist_ok=True)
        os.makedirs("%s/ds-chain/repositories/%s" % (work, CHAIN_GUID), exist_ok=True)
        # An initialized datastore carries the .immovable marker; $WORK/ds stands in for a formatted datastore, so it carries it too.
        pathlib.Path(work + "/ds/.immovable").touch()
        # S9/S10 use PLAIN datastores (no descriptor), so their repos stay in the legacy unscoped population.
        for sub in (
            "ds-seq-a/repositories/" + SEQ_GUID_A,
            "ds-seq-b/repositories/" + SEQ_GUID_B,
            "ds-fp/repositories/" + FP_GUID,
        ):
            os.makedirs("%s/%s" % (work, sub), exist_ok=True)
        # S8 uses two datastores that DO carry identities: a parent and its fork, holding the same repo guid.
        self.describe_datastore(work + "/ds-parent", PARENT_DS_ID)
        self.describe_datastore(work + "/ds-fork", FORK_DS_ID)
        os.makedirs("%s/ds-parent/repositories/%s" % (work, FORK_GUID), exist_ok=True)
        os.makedirs("%s/ds-fork/repositories/%s" % (work, FORK_GUID), exist_ok=True)
        os.makedirs(work + "/ds-restore/repositories", exist_ok=True)

        self._back_up_chain_state()

        log.step("Building license-mint...")
        self.mint_bin = work + "/license-mint"
        self._fatal(_exec(["go", "build", "-o", self.mint_bin, "."], cwd=self.mint_src).returncode)

        # The ephemeral master key. Never the production key: a build baked with a key this script also holds the private half of can only validate this script's own fixtures.
        supplied_pub = self.env.get("LICENSE_E2E_MASTER_PUB", "")
        supplied_priv = self.env.get("LICENSE_E2E_MASTER_PRIV", "")
        if supplied_pub and supplied_priv:
            self.master_pub = supplied_pub
            self.master_priv = supplied_priv
            log.info("Using the caller-supplied ephemeral master key")
        else:
            log.step("Generating an ephemeral master key...")
            keypair = self._mint_json("-gen-key")
            self.master_pub = jq_raw(keypair, "public")
            self.master_priv = jq_raw(keypair, "private")
        stranger = self._mint_json("-gen-key")
        stranger_pub = jq_raw(stranger, "public")
        self.stranger_priv = jq_raw(stranger, "private")

        probe = self._mint_json(
            "-master-key", self.master_priv, "-out-dir", work + "/fp", "-repo", "fingerprint-probe"
        )
        self.master_key_id = jq_raw(probe, "publicKeyId")
        shutil.rmtree(work + "/fp", ignore_errors=True)
        log.info("Ephemeral master key fingerprint: %s" % self.master_key_id)

        log.step("Building renet: enforcing, nolicense twin, wrong-key twin...")
        self.build_renet(work + "/renet-enforcing", self.master_pub)
        self.build_renet(work + "/renet-nolicense", self.master_pub, "-tags", "nolicense")
        self.build_renet(work + "/renet-wrongkey", stranger_pub)

        self.install_fixtures()

        log.step("Running the battery against the enforcing binary...")
        if not self.run_battery(work + "/renet-enforcing", "enforcing"):
            log.error("License enforcement battery FAILED: %s" % " ".join(self.failed))
            return 1
        log.info("Enforcing binary passed every scenario")

        log.step("Proving the instrument: the same battery must FAIL on a nolicense build...")
        if not self.expect_control_failure(work + "/renet-nolicense", "nolicense", "S1"):
            return 1

        log.step("Proving the instrument: the same battery must FAIL on a wrongly-baked key...")
        if not self.expect_control_failure(work + "/renet-wrongkey", "wrong-key", "S2"):
            return 1

        log.info("License enforcement battery passed, and both controls failed as required")
        return 0


def is_scratch_store(license_root: str) -> bool:
    """True when `license_root` is not the machine's real store, compared by realpath so a trailing slash or a symlink naming the real store still counts as the real store."""
    return os.path.realpath(license_root) != os.path.realpath(LICENSE_ROOT)


def run(argv: Sequence[str], *, license_root: str = LICENSE_ROOT) -> int:
    """Run the battery. Arguments are ignored, as the bash ignored them; `license_root` exists so a test can point the in-process path checks at a scratch tree."""
    del argv
    battery = Battery(license_root=license_root)

    def _terminate(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _terminate)
    # ONE BATTERY PER LICENSE STORE AT A TIME. The store is machine-global, and two runs interleave its backup, fixtures and restore: on 2026-10-19 one pre-push ran check:ci-proxy-license-e2e beside check:ci-pytest's real-tree port of the same subject, one run's cleanup removed the other's repo directory mid-battery (`chmod: cannot access .../repos/1ce1ce2e-...`), and S6b/S8d/S9c/S10b read 'missing'. A lock keyed by the store path serializes exactly the runs that share it, across processes and worktrees, and leaves a test's scratch store unblocked.
    # The lock lives in /tmp itself, never TMPDIR, so every environment on the host names the same file; it is opened read-only (flock needs no write access, so another user's readable file still serves; an unreadable one or a symlink fails the run with its reason) and never through a symlink. The wait is bounded: a holder that hangs makes this run fail with its reason instead of stalling the gate.
    key = hashlib.sha256(os.path.realpath(license_root).encode()).hexdigest()[:16]
    lock_path = f"/tmp/rediacc-license-e2e-{key}.lock"
    # A scratch store (a test's tree) has its lock file removed by the run that held it, so a waiter can wake on an unlinked inode: after taking the flock, the fd must still be the file at lock_path, or the run reopens and waits again (otherwise a waiter on the old inode and a newcomer on a fresh file would hold the store at once, review 37ecbdd5.2).
    is_scratch = is_scratch_store(license_root)
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            fd = os.open(lock_path, os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        except OSError as exc:
            log.error(
                f"cannot open the license-store lock {lock_path} ({exc.strerror}); a symlink or another user's unreadable file sits there"
            )
            return 1
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            try:
                current = os.stat(lock_path, follow_symlinks=False).st_ino
            except OSError:
                current = None
            if current == os.fstat(fd).st_ino:
                break
        # Busy, or the locked inode is no longer the file at lock_path: either way the next try waits and the deadline holds (review 768f6e50.3: a stat that keeps failing must not loop past LOCK_WAIT_S).
        os.close(fd)
        if time.monotonic() >= deadline:
            log.error(
                f"another license battery still holds the store {license_root} after {LOCK_WAIT_S}s; not running beside it"
            )
            return 1
        time.sleep(1)
    try:
        return battery.run()
    finally:
        # The scratch store's lock file goes while the lock is still held, so the next opener creates a fresh file and a waiter on this inode sees the mismatch above; without removal every test run left one file in /tmp (2,066 by 2026-10-24). The real store, compared by realpath so a trailing slash or a symlink still names it (review 37ecbdd5.1), keeps its single fixed file.
        if is_scratch:
            with contextlib.suppress(OSError):
                os.unlink(lock_path)
        os.close(fd)


def main(argv: list[str]) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
