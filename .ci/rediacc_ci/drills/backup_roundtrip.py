#!/usr/bin/env python3
"""Chunk-store backup/restore round trip, end to end, against a LOCAL S3.

Ported from `programs/backup-storage/local-roundtrip.sh` (PLAN-retire-bash-oracles B5, W10).

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_local_plane      # first, in another shell
    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_roundtrip        # the proof, exit 0 = passed

What this proves that nothing else did: a MACHINE uploaded a real repository image to a real S3 endpoint and a DIFFERENT repository was reconstructed from it byte for byte. Suite 26's RESTORE tier automates the same claim but drives `rdc`; the drill (`rediacc_ci.drills.backup`) never creates a repo on a VM at all -- its leg `i` is not in the default LEGS list and needs a repo it did not make. So before this program the machine-level round trip had never run.

It deliberately does NOT use `./rdc.sh`, because rdc rebuilds and redeploys renet to whatever machine it touches. Everything here is renet on the VM plus the account API, so the binary under test is the one that was chosen.

THE THREE THINGS THAT MAKE IT WORK, none of them obvious:

1. THE HOST HEADER NAMES THE UNIVERSE. `renewalUrlFor` (private/account/src/routes/license.ts:36) derives the licence's renewalUrl from `envConfig.baseUrl`, which is `PUBLIC_SITE_URL ?? url.host` (app.ts:534). renet then derives the backup SESSION url from that renewalUrl by suffix swap (cmd/renet/backup_snapshot.go:540). Issue the licence over localhost and the VM gets a session URL it cannot dial. Every call below therefore goes to 192.168.111.254:4800, never localhost.

2. ONLY THE SERVER CAN MINT A USABLE LICENCE. `.ci/scripts/private/license-mint` cannot stand in: it never sets `grandGuid` (its payload literal has no such field), and `snapshotOneRepo` refuses a licence without one -- "repository license carries no grandGuid, so the object-key lineage is unknown". The lineage IS the object-key prefix, so there is nothing to upload under.

3. THE RESTORE TARGET NEEDS ITS OWN LICENCE. Without one, `resolveRestoreLicense` (cmd/renet/backup_restore.go:360) falls back to the FIRST installed licence carrying any renewalUrl, with no preference for one covering the lineage being restored. On a machine holding licences from an earlier session that is a DIFFERENT SUBSCRIPTION, and the restore dies on `404 BACKUP_MANIFEST_MISSING` -- an error that names the manifest, not the credential that was actually wrong. See docs/backup-storage/09-*.md.

Prerequisites: worker VM at 192.168.111.11 reachable as SSH_USER (default $USER) with SSH_KEY (default the renet-staged id_rsa), docker on the host, a renet built from this tree already installed on the VM, and the local plane running.

THE PROOF NEEDS THE VM, so it is run by an operator; the port's logic (ordering, the comparison, the control, the teardown, the exit status) is pinned in `test_drills_backup_roundtrip.py` against a scripted VM and a scripted account API.

DELIBERATE DELTAS FROM THE BASH (Rule T), each with a test that fails on the bash behaviour:

  * THE SOURCE LICENCE IS INSTALLED BEFORE `repository create`. The bash created the repo first (`local-roundtrip.sh:126` before `:133`), which only a nolicense renet accepts; an enforcing renet refuses a create with no installed licence for the guid.
  * SSH GOES AS THE PROVISIONED USER WITH THE STAGED KEY. The bash ssh'd to a hardcoded account with no identity file; the fleet provisions `$USER` and authorizes only `~/.renet/staging/.ssh/id_rsa` (`vm_ssh`).
  * AN SSH FAILURE IS NOT "renet missing". The bash's preflight read any non-zero exit, an auth refusal (255) included, as a missing binary.

  * THE TEARDOWN RUNS ON ANY FAILURE. The bash ran under `set -e` with the teardown as step 9, so a failing snapshot, restore, repo creation or API call exited the script mid-way and left two repos, their licences and `/tmp/rt_pass.txt` on the VM. Steps 1-8 now run under one `try` and step 9 is its `finally`.
  * A step that fails is a FAIL line and a non-zero exit. An unparseable snapshot output (the failure case) used to put a Python traceback where the verdict belongs, and the `SNAP=$(...)` assignment then killed the script before the teardown.
  * THE API TOKEN IS NOT ON ANY COMMAND LINE. The bash passed `Authorization: Bearer <token>` as a curl argument, visible in `ps` to every user on the host for the length of the run.
  * The licence file kept in the work directory is mode 0600; the bash left it world-readable in `/tmp`.
  * The exit status is `min(failures, 255)`, so 256 failures cannot read as success.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import well_known
from rediacc_ci.drills import vm_ssh

if TYPE_CHECKING:
    from collections.abc import Callable

SSH_TIMEOUT = 900
HTTP_ERROR_FLOOR = 400
SCOPES = [
    "license:read",
    "license:activate",
    "subscription:read",
    "backup:read",
    "backup:manage",
]
CLIENT_MACHINE_ID = pathlib.Path("/etc/machine-id")
LOGIN_PHRASE = "RoundTrip123!"  # a throwaway local-plane account, created and used only here


class StepError(Exception):
    """A step could not run to a verdict."""


class VmResult:
    """What one ssh command did."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def ssh_vm(user: str, key: str, vm: str, command: str, stdin_data: str | None = None) -> VmResult:
    """The real transport: `ssh -i <key> <user>@VM command` with exactly that one identity (`vm_ssh`), under the 900 second ceiling."""
    try:
        proc = subprocess.run(
            vm_ssh.ssh_argv(user, key, vm, command),
            input=stdin_data,
            stdin=None if stdin_data is not None else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=SSH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return VmResult(124, "", "ssh timed out after %ds" % SSH_TIMEOUT)
    except OSError as exc:
        return VmResult(127, "", str(exc))
    return VmResult(proc.returncode, proc.stdout, proc.stderr)


class Api:
    """The account API over HTTP: JSON in and out, the login cookie kept, a bearer token after.

    Plain `http.client` against the one host the proof uses, so the token travels in a header of this process and nowhere else.
    """

    def __init__(self, gateway: str) -> None:
        parts = urllib.parse.urlsplit(gateway)
        self.host = parts.hostname or ""
        self.port = parts.port or 80
        self.prefix = "/account/api/v1"
        self.cookies: dict[str, str] = {}
        self.token = ""

    def _request(self, method: str, path: str, body: bytes | None, timeout: int) -> tuple[int, str]:
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.cookies:
            headers["Cookie"] = "; ".join("%s=%s" % kv for kv in self.cookies.items())
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            for value in response.headers.get_all("Set-Cookie") or []:
                name, _, cookie = value.split(";", 1)[0].partition("=")
                self.cookies[name.strip()] = cookie.strip()
            return response.status, response.read().decode("utf-8", errors="replace")
        finally:
            conn.close()

    def call(self, method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            status, raw = self._request(method, self.prefix + path, data, timeout)
        except OSError as exc:
            raise StepError("%s %s -> %s" % (method, path, exc)) from exc
        if status >= HTTP_ERROR_FLOOR:
            raise StepError("%s %s -> HTTP %d" % (method, path, status))
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError as exc:
            raise StepError("%s %s -> not JSON: %s" % (method, path, raw[:80])) from exc

    def healthy(self) -> bool:
        try:
            status, _ = self._request("GET", "/health", None, 5)
        except OSError:
            return False
        return status < HTTP_ERROR_FLOOR


class Roundtrip:
    """One run. `vm` and `api` are the seams: the real ones talk to a machine, the tests' do not."""

    def __init__(
        self,
        vm: Callable[[str, str | None], VmResult],
        api: Api,
        work: pathlib.Path,
        datastore: str = well_known.DATASTORE_PATH,
        cell_bytes: str = "65536",
        net_src: str = "2880",
        say: Callable[[str], None] | None = None,
    ) -> None:
        self.vm = vm
        self.api = api
        self.work = work
        self.datastore = datastore
        self.cell_bytes = cell_bytes
        self.net_src = net_src
        self.say = say or print
        self.failures = 0
        self.created: list[str] = []

    # ---------------------------------------------------------------- reporting

    def step(self, title: str) -> None:
        self.say("\n=== %s ===" % title)

    def check(self, label: str, expected: str, actual: str) -> None:
        if expected == actual:
            self.say("PASS  %s" % label)
        else:
            self.say(
                "FAIL  %s\n        expected: %s\n        actual:   %s" % (label, expected, actual)
            )
            self.failures += 1

    def fail(self, message: str) -> None:
        self.say("FAIL  %s" % message)
        self.failures += 1

    def run_vm(self, command: str, stdin_data: str | None = None, must: bool = True) -> VmResult:
        result = self.vm(command, stdin_data)
        if must and result.returncode != 0:
            raise StepError(
                "VM command failed (%d): %s\n%s"
                % (result.returncode, command.strip().splitlines()[0][:120], result.stderr.strip())
            )
        return result

    # ---------------------------------------------------------------- the steps

    def account(self) -> str:
        """Step 1: account, subscription, API token. Returns the subscription id."""
        email = "backup-roundtrip-%d@rediacc.io" % int(time.time())
        creds = {"email": email, "password": LOGIN_PHRASE}
        self.api.call("POST", "/test/ensure-login", creds)
        sub = self.api.call(
            "POST", "/test/ensure-subscription", {"email": email, "planCode": "PROFESSIONAL"}
        )["subscriptionId"]
        self.api.call("POST", "/auth/login", creds)
        token = self.api.call(
            "POST",
            "/api-tokens",
            {"subscriptionId": sub, "name": "roundtrip", "scopes": SCOPES},
        )["token"]
        self.api.token = token
        # The login cookie only authorises the token mint; every later call carries the bearer token alone, as the bash did.
        self.api.cookies.clear()
        return sub

    def issue_license(self, guid: str, grand: str, kind: str) -> None:
        """Mint a licence server-side and install it where renet reads it.

        The filename is the blob's own publicKeyId, so licences from different account universes coexist instead of clobbering.
        """
        machine_id = self.run_vm("sudo -n renet machine-id").stdout.strip("\r\n")
        client_id = CLIENT_MACHINE_ID.read_text(encoding="utf-8").strip()
        license_doc = self.api.call(
            "POST",
            "/licenses/activate-repo",
            {
                "machineId": machine_id,
                "clientMachineId": client_id,
                "repositoryGuid": guid,
                "grandGuid": grand,
                "kind": kind,
                "requestedSizeGb": 1,
            },
        )["license"]
        blob = self.work / "lic.json"
        blob.write_text(json.dumps(license_doc, indent=2), encoding="utf-8")
        blob.chmod(0o600)
        target = "/var/lib/rediacc/license/repos/%s/%s.json" % (guid, license_doc["publicKeyId"])
        self.run_vm("cat > /tmp/rt-lic.json", blob.read_text(encoding="utf-8"))
        self.run_vm(
            "sudo -n mkdir -p /var/lib/rediacc/license/repos/%s && "
            "sudo -n cp /tmp/rt-lic.json %s && "
            "sudo -n chmod 640 %s && "
            "rm -f /tmp/rt-lic.json" % (guid, target, target)
        )

    def create_source(self, src: str) -> None:
        """Step 2: create the NEW repo `src` (its licence already installed) and plant known content."""
        ds = self.datastore
        passphrase = uuid.uuid4().hex + uuid.uuid4().hex
        luks = self.work / "luks.txt"
        luks.write_text(passphrase + "\n", encoding="utf-8")
        luks.chmod(0o600)
        self.run_vm("cat > /tmp/rt_pass.txt && chmod 600 /tmp/rt_pass.txt", passphrase + "\n")
        self.run_vm(
            "sudo -n sh -c 'cat /tmp/rt_pass.txt | renet repository create --name %s "
            "--network-id %s --size 256M --password-stdin --output json'" % (src, self.net_src)
        )
        self.run_vm(
            "sudo -n sh -c '\n"
            '  echo "marker: rediacc chunk-store round trip proof" > %(ds)s/mounts/%(s)s/marker.txt\n'
            "  head -c 8388608 /dev/urandom > %(ds)s/mounts/%(s)s/payload.bin\n"
            "  mkdir -p %(ds)s/mounts/%(s)s/nested/dir\n"
            '  printf "nested content 1234567890" > %(ds)s/mounts/%(s)s/nested/dir/deep.txt\n'
            "  sync'" % {"ds": ds, "s": src}
        )

    def source_status(self, src: str) -> str:
        listing = self.run_vm("sudo -n renet repository license-status --output json").stdout
        try:
            rows = json.loads(listing)
            row = next(r for r in rows if r["repositoryGuid"] == src)
            status = str(row["status"])
            return status if status == "valid" else "%s: %s" % (status, row.get("message", ""))
        except (ValueError, StopIteration, KeyError, TypeError):
            return "unreadable: %s" % listing.strip()[:80]

    def image_digest(self, guid: str, quiesce: bool = False) -> str:
        sync = "sync; " if quiesce else ""
        out = self.run_vm(
            "sudo -n sh -c '%ssha256sum %s/repositories/%s'" % (sync, self.datastore, guid)
        ).stdout
        return out.split()[0] if out.split() else ""

    def _json_result(self, result: VmResult) -> dict:
        self.say(result.stdout.rstrip("\n"))
        try:
            parsed = json.loads(result.stdout)
        except ValueError:
            why = (result.stderr.strip() or result.stdout.strip())[:120]
            return {"status": "unparseable: %s" % why}
        return parsed if isinstance(parsed, dict) else {"status": "unparseable: not an object"}

    def snapshot(self, src: str) -> dict:
        return self._json_result(
            self.run_vm(
                "sudo -n renet backup snapshot --datastore %s --repo %s --cell-bytes %s"
                % (self.datastore, src, self.cell_bytes),
                must=False,
            )
        )

    def restore(self, tgt: str, lineage: str, at: str, passphrase: str = "") -> dict:
        """`renet backup restore`; a `passphrase` goes over stdin, never onto a command line, and makes the verb test-open the image before placing it."""
        return self._json_result(
            self.run_vm(
                "sudo -n renet backup restore --datastore %s --repo %s --lineage %s --at %s%s"
                % (self.datastore, tgt, lineage, at, " --password-stdin" if passphrase else ""),
                passphrase + "\n" if passphrase else None,
                must=False,
            )
        )

    def passphrase(self) -> str:
        """The source repository's passphrase, which `create_source` kept in the work directory."""
        return (self.work / "luks.txt").read_text(encoding="utf-8").strip()

    def image_present(self, guid: str) -> bool:
        return (
            self.run_vm(
                "sudo -n test -e %s/repositories/%s" % (self.datastore, guid), must=False
            ).returncode
            == 0
        )

    def teardown(self) -> None:
        self.step("9. teardown")
        for guid in self.created:
            self.run_vm("sudo -n renet repository unmount --name %s" % guid, must=False)
            self.run_vm("sudo -n renet repository delete --name %s --force" % guid, must=False)
            self.run_vm("sudo -n rm -rf /var/lib/rediacc/license/repos/%s" % guid, must=False)
        self.run_vm("rm -f /tmp/rt_pass.txt", must=False)
        if self.created:
            self.say("removed repos %s and their licences" % " and ".join(self.created))
        else:
            self.say("no repos were created, nothing to remove")

    # ---------------------------------------------------------------- the run

    def run(self) -> int:
        try:
            self._prove()
        except StepError as exc:
            self.fail(str(exc))
        finally:
            self.teardown()
        verdict = (
            "ROUND TRIP PASSED" if self.failures == 0 else "ROUND TRIP FAILED (%d)" % self.failures
        )
        self.say("\n===== %s =====" % verdict)
        return min(self.failures, 255)

    def _prove(self) -> None:
        ds = self.datastore
        self.step("1. account, subscription, api token")
        self.say("subscription %s" % self.account())

        self.step("2. licence a NEW repo, create it, and plant known content")
        src = str(uuid.uuid4())
        self.created.append(src)
        # The licence comes FIRST: an enforcing renet refuses `repository create` for a guid with no installed licence (cmd/renet/repository_create.go, validateCreateSizeLimit).
        self.issue_license(src, src, "grand")
        self.create_source(src)
        self.check("source repo licence is valid", "valid", self.source_status(src))

        self.step("3. quiesce and record the source image digest")
        self.run_vm("sudo -n renet repository down --name %s" % src, must=False)
        self.run_vm("sudo -n renet repository unmount --name %s" % src)
        src_sha = self.image_digest(src, quiesce=True)
        self.say("source image sha256: %s" % src_sha)

        self.step("4. snapshot to the local S3")
        snap_doc = self.snapshot(src)
        self.check("snapshot stored", "stored", str(snap_doc.get("status", "")))
        if snap_doc.get("status") != "stored":
            raise StepError("no snapshot was stored, so there is nothing to restore")
        snap = str(snap_doc.get("snapshotId", ""))
        uploaded = str(snap_doc.get("bytesUploaded", ""))

        self.step("5. the manifest index lists it, and the quota ledger moved")
        listed = self.api.call("GET", "/backups/manifests").get("manifests") or []
        self.check(
            "manifest index carries the snapshot",
            snap,
            str(listed[0]["snapshotId"]) if listed else "",
        )
        usage = self.api.call("GET", "/backups/usage")
        self.check(
            "quota ledger equals bytes uploaded", uploaded, str(usage.get("storedBytes", ""))
        )

        self.step("6. restore as a DIFFERENT repo")
        tgt = str(uuid.uuid4())
        self.created.append(tgt)
        # The target's own licence. Skipping this is what makes resolveRestoreLicense reach for a stranger's; see the header.
        self.issue_license(tgt, src, "fork")
        # PROVE THE GATE. A wrong passphrase must end the restore with nothing placed, so the "opened" below can be false.
        refused = self.restore(tgt, src, snap, "not-" + self.passphrase())
        self.check("wrong passphrase: refused", "refused", str(refused.get("passphraseCheck", "")))
        self.check("wrong passphrase: places nothing", "False", str(self.image_present(tgt)))
        restored = self.restore(tgt, src, snap, self.passphrase())
        self.check("restore completed", "restored", str(restored.get("status", "")))
        self.check("the image opens", "opened", str(restored.get("passphraseCheck", "")))
        if restored.get("status") != "restored":
            raise StepError("the restore did not complete, so there is no image to compare")

        self.step("7. BYTE COMPARISON (the only step that proves anything)")
        tgt_sha = self.image_digest(tgt)
        self.say("source   %s" % src_sha)
        self.say("restored %s" % tgt_sha)
        self.check("restored image is byte-identical to the source", src_sha, tgt_sha)
        same = self.run_vm(
            "sudo -n cmp %s/repositories/%s %s/repositories/%s" % (ds, src, ds, tgt), must=False
        )
        if same.returncode == 0:
            self.say("PASS  cmp reports the two images identical")
        else:
            self.say("FAIL  cmp reports the two images differ")
            self.failures += 1

        # PROVE THE INSTRUMENT. A comparison that cannot fail is not evidence. Mutate one byte of the restored image and require the same cmp to notice.
        self.step("8. control: the comparison can detect a difference")
        self.run_vm(
            'sudo -n sh -c \'printf "\\x01" | dd of=%s/repositories/%s bs=1 seek=1048576 '
            "conv=notrunc status=none'" % (ds, tgt),
            must=False,
        )
        control = self.run_vm(
            "sudo -n cmp -s %s/repositories/%s %s/repositories/%s" % (ds, src, ds, tgt), must=False
        )
        if control.returncode == 0:
            self.say("FAIL  control did NOT fire: cmp still calls a mutated image identical")
            self.failures += 1
        else:
            self.say("PASS  control fired: cmp detects the planted one-byte difference")


def preflight_vm(vm: Callable[[str, str | None], VmResult], host: str, user: str, key: str) -> str:
    """'' when the VM answers over ssh and has renet on PATH; otherwise the refusal, naming which of the two failed. ssh's own failure (255) is an authentication or reachability problem, and reporting it as "renet missing" sends the operator to rebuild a binary that was never the cause."""
    probe = vm("command -v renet >/dev/null", None)
    if probe.returncode == vm_ssh.SSH_FAILED:
        why = probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else "no stderr"
        return (
            "cannot ssh to %s as %s with %s (exit 255: %s). The VMs authorize the key renet ops "
            "provisioned them with; set SSH_KEY / SSH_USER if this fleet was built with others."
            % (host, user, key, why)
        )
    if probe.returncode != 0:
        return "renet missing on %s (command -v renet exited %d)" % (host, probe.returncode)
    return ""


def main(argv: list[str] | None = None) -> int:
    del argv  # no arguments: every knob is an environment variable
    environ = os.environ
    vm_host = environ.get("VM") or "192.168.111.11"
    bridge = environ.get("BRIDGE_HOST") or "192.168.111.254"
    port = environ.get("GATEWAY_PORT") or str(well_known.ACCOUNT_DEV_PORT)
    work = pathlib.Path(environ.get("WORK") or "/tmp/backup-roundtrip")
    work.mkdir(parents=True, exist_ok=True)

    api = Api("http://%s:%s" % (bridge, port))
    print("\n=== 0. preflight ===")
    if not api.healthy():
        print(
            "no account gateway on %s:%s; run rediacc_ci.drills.backup_local_plane"
            % (bridge, port),
            file=sys.stderr,
        )
        return 1

    user, key = vm_ssh.default_user(environ), vm_ssh.default_key(environ)

    def vm(command: str, stdin_data: str | None = None) -> VmResult:
        return ssh_vm(user, key, vm_host, command, stdin_data)

    refusal = preflight_vm(vm, vm_host, user, key)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    return Roundtrip(
        vm,
        api,
        work,
        datastore=environ.get("DATASTORE") or well_known.DATASTORE_PATH,
        cell_bytes=environ.get("CELL_BYTES") or "65536",
        net_src=environ.get("NET_SRC") or "2880",
    ).run()


if __name__ == "__main__":
    sys.exit(main())
