"""I3: the Elite compose stack on one machine, a backup snapshot from another.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_elite_compose [--selftest] [--keep-work] [--keep-stack]
        [--elite <ip>] [--machine <ip>] [--image <ref>] [--plan <code>] [--ssh-user <u>] [--ssh-key <p>]

WHAT IT IS FOR. `rediacc_ci.drills.backup_onprem` boots `src/entry/on-premise.ts` straight from the tree, and the CI `Elite Run` job only waits for the stack's health check. Neither runs what an Elite customer runs, `private/elite/docker-compose.yml` with its standalone override, and neither has a machine OUTSIDE that stack's docker network back up into it. Box I3 of PLAN-backup-program is that configuration: the store published on the backup interface, presigned URLs signed for the published address (`ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT`), the licence renewal URL built from `PUBLIC_SITE_URL`, and an account server that actually starts inside the image.

WHAT IT DOES, one claim per row:
  1. An upstream (the dev gateway, `./run.sh account dev`) issues a delegation cert for a throwaway Ed25519 pair over `POST /portal/delegation-certs`.
  2. The elite VM runs `docker compose -f docker-compose.yml -f docker-compose.standalone.yml up -d` over the tree's own `private/elite` files, with a `.env` that enrols the box with that pair and cert, sets `SYSTEM_DOMAIN` and `RUSTFS_BIND` to the elite VM's address and `PUBLIC_SITE_URL` to its HTTP port. The server image is the one `PYTHONPATH=.ci python3 -m rediacc_ci.ops.build_server onprem` built on this host (`rediacc-server-onprem:dev`), shipped with `docker save` and `docker load` and tagged on the VM only; nothing is pulled from or pushed to a registry.
  3. From the machine VM: the account server answers `server-info` through nginx (so the enrolment variables reached it), and the published store answers 403 (up, wants credentials). Controls: a closed port on the same host answers nothing, and the machine cannot resolve `rediacc-rustfs`, so it really is outside the docker network and the internal endpoint could not have served it.
  4. The first registration on the box adopts the cert's subscription (the subscription id read back equals the cert's).
  5. The machine VM snapshots a fresh repository into the box, the manifest index lists it, the quota ledger equals the bytes uploaded, and the snapshot restores into a different repository byte for byte (`backup_roundtrip.Roundtrip`, with its account step replaced by the registration above, since the box has no `/test` seam).

COST. Two ops VMs (`<net>.11` as the elite box and `<net>.12` as the machine by default) with docker on the first and a renet built from this tree on the second (`npm run vm:check` installs one), the dev gateway on this host, and one server image of about a gigabyte copied to the elite VM. The stack goes down with its volumes at the end unless `--keep-stack`.

NOT PROVEN HERE, said plainly: HTTPS (the drill sets `ENABLE_HTTPS=false`, so no certificate is generated), `run.sh up` itself (the drill calls compose with the same two files and an `.env` it writes; `run.sh`'s credential generation is `private/elite/scripts/test-credentials.sh`'s), and a store bound to a dedicated backup network (the elite VM has one interface, so `RUSTFS_BIND` is its address on the VM network).

NO SECRET ON AN ARGV. The `.env` (store keys, signing key, cert) reaches the elite VM over ssh's stdin and is mode 0600 there; the cert mint and the registration are this process's own HTTP calls.
"""

from __future__ import annotations

import base64
import contextlib
import http.cookiejar
import json
import re
import secrets
import shlex
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.core import account
from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.drills import lib, vm_ssh

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

STEP_LABEL = "I3"
USAGE = (
    "Usage: ./run.sh drill backup-elite-compose [--selftest] [--keep-work] [--keep-stack] "
    "[--elite <ip>] [--machine <ip>] [--image <ref>] [--plan <code>] [--ssh-user <u>] [--ssh-key <p>]"
)
DEFAULT_IMAGE = "rediacc-server-onprem:dev"
# The compose file names the image `${DOCKER_REGISTRY}/server:${WEB_TAG}`; the shipped image carries these on the VM only.
DRILL_REGISTRY = "rediacc-drill"
DRILL_TAG = "elite-compose"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.standalone.yml")
HTTP_PORT = 8088
STORE_PORT = 9000
SERVER_INFO = "/account/api/v1/.well-known/server-info"
INTERNAL_STORE_HOST = "rediacc-rustfs"
HEALTH_TRIES = 60
HEALTH_INTERVAL_S = 5.0
CERT_VALID_DAYS = 7
LOGIN_PHRASE = (
    "EliteCompose123!"  # a throwaway account on a throwaway box, created and used only here
)
# What a value written into the `.env` may carry: neither compose's env-file reader nor a later `source .env` reads any of these specially.
ENV_SAFE = re.compile(r"^[A-Za-z0-9._~@%+=:,/-]*$")
CURL_NOTHING = "000"
# The ops fleet's network; `--elite` and `--machine` name any other pair.
VM_NET_BASE = "192.168.111"


class Options:
    def __init__(self) -> None:
        self.selftest = False
        self.keep_work = False
        self.keep_stack = False
        self.elite_vm = VM_NET_BASE + ".11"
        self.machine_vm = VM_NET_BASE + ".12"
        self.image = DEFAULT_IMAGE
        self.plan = "PROFESSIONAL"
        self.ssh_user = vm_ssh.default_user()
        self.ssh_key = vm_ssh.default_key()


VALUED = {
    "--elite": "elite_vm",
    "--machine": "machine_vm",
    "--image": "image",
    "--plan": "plan",
    "--ssh-user": "ssh_user",
    "--ssh-key": "ssh_key",
}


def parse_args(argv: list[str]) -> Options:
    """The options, or `ValueError` naming the first bad argument."""
    opts = Options()
    opts.selftest, opts.keep_work, rest = lib.parse_common_args(argv)
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--keep-stack":
            opts.keep_stack = True
        elif arg in VALUED:
            if i + 1 >= len(rest) or not rest[i + 1] or rest[i + 1].startswith("--"):
                raise ValueError("%s needs a value" % arg)
            setattr(opts, VALUED[arg], rest[i + 1])
            i += 1
        else:
            raise ValueError("Unknown option: %s" % arg)
        i += 1
    if opts.elite_vm == opts.machine_vm:
        raise ValueError(
            "--elite and --machine are the same host (%s); the proof needs a machine outside the stack"
            % opts.elite_vm
        )
    return opts


def env_text(values: dict[str, str]) -> str:
    """The `.env` the stack reads, one `KEY="value"` line each in a stable order. A value compose or bash would read specially raises `ValueError` naming the key, never the value."""
    lines = []
    for key in sorted(values):
        if not ENV_SAFE.fullmatch(values[key]):
            raise ValueError("%s carries a character the .env cannot hold safely" % key)
        lines.append('%s="%s"' % (key, values[key]))
    return "\n".join(lines) + "\n"


def elite_env(
    elite_vm: str,
    *,
    keys: dict[str, str],
    cert_b64: str,
    store_access: str,
    store_secret: str,
    config_key: str,
) -> dict[str, str]:
    """What the drill's `.env` sets. `SYSTEM_DOMAIN` and `RUSTFS_BIND` are the elite VM's own address, so the standalone override publishes the store there and the server signs presigned URLs for `http://<elite>:9000`. `PUBLIC_SITE_URL` is the HTTP port the machine dials, which the licence's renewal URL (and from it renet's session URL) is built from. `ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT` is deliberately NOT set: its standalone default is the claim under test."""
    return {
        "TAG": DRILL_TAG,
        "WEB_TAG": DRILL_TAG,
        "DOCKER_REGISTRY": DRILL_REGISTRY,
        "SYSTEM_DOMAIN": elite_vm,
        "RUSTFS_BIND": elite_vm,
        "RUSTFS_PUBLIC_PORT": str(STORE_PORT),
        "HTTP_PORT": str(HTTP_PORT),
        "HTTPS_PORT": str(HTTP_PORT + 1),
        "ENABLE_HTTPS": "false",
        "PUBLIC_SITE_URL": "http://%s:%d" % (elite_vm, HTTP_PORT),
        "RUSTFS_ACCESS_KEY": store_access,
        "RUSTFS_SECRET_KEY": store_secret,
        "ACCOUNT_CONFIG_SERVER_KEY": config_key,
        "ACCOUNT_ED25519_PRIVATE_KEY": keys["ed25519_priv"],
        "ACCOUNT_ED25519_PUBLIC_KEY": keys["ed25519_pub"],
        "ACCOUNT_X25519_PRIVATE_KEY": keys["x25519_priv"],
        "ACCOUNT_X25519_PUBLIC_KEY": keys["x25519_pub"],
        "ACCOUNT_SERVER_API_KEY": keys["api_key"],
        "ACCOUNT_JWT_SECRET": keys["jwt"],
        "DELEGATION_CERT_BASE64": cert_b64,
        "BACKUP_MAINTENANCE_INTERVAL_MS": "0",
    }


def compose_command(stack_dir: str, *verb: str) -> str:
    """`sudo docker compose` over the two elite files in `stack_dir`, the way `run.sh` runs a standalone box."""
    files = " ".join("-f %s" % name for name in COMPOSE_FILES)
    return "cd %s && sudo -n docker compose %s %s" % (
        shlex.quote(stack_dir),
        files,
        " ".join(shlex.quote(v) for v in verb),
    )


def curl_status_command(url: str) -> str:
    """The HTTP status `curl` reads for `url`, `000` when nothing answered. It always exits 0, so the printed status is the verdict."""
    return "curl -s -o /dev/null -m 10 -w '%%{http_code}' %s || true" % shlex.quote(url)


def cert_base64(answer: str) -> str:
    """The base64 of the `cert` JSON a `POST /portal/delegation-certs` answer carries, or `ValueError` naming what was missing."""
    try:
        doc = json.loads(answer)
    except ValueError as exc:
        raise ValueError("the delegation-cert answer is not JSON: %s" % answer[:120]) from exc
    cert = doc.get("cert") if isinstance(doc, dict) else None
    if not cert:
        raise ValueError("the delegation-cert answer carries no cert: %s" % answer[:200])
    text = cert if isinstance(cert, str) else json.dumps(cert, separators=(",", ":"))
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def cert_subscription(cert_b64: str) -> str:
    """The `subscriptionId` a cert names, read the way the loader reads it: the base64 of the signed cert JSON, whose `payload` is itself base64 JSON. Empty when absent or unreadable."""
    try:
        doc = json.loads(base64.b64decode(cert_b64))
    except ValueError:
        return ""
    payload = doc.get("payload") if isinstance(doc, dict) else None
    if isinstance(payload, str):
        try:
            payload = json.loads(base64.b64decode(payload))
        except ValueError:
            return ""
    if isinstance(payload, dict) and payload.get("subscriptionId"):
        return str(payload["subscriptionId"])
    return ""


class EliteRoundtrip(rt.Roundtrip):
    """The machine-level round trip against the elite box. The box has no `/test` seam, so the account step is the registration this drill already did, and the subscription it returns is the adopted one."""

    def __init__(
        self,
        vm: Callable[[str, str | None], rt.VmResult],
        api: rt.Api,
        work: pathlib.Path,
        *,
        say: Callable[[str], None],
        subscription: str,
    ) -> None:
        super().__init__(vm, api, work, say=say)
        self.subscription = subscription

    def account(self) -> str:
        return self.subscription


def ssh_runner(user: str, key: str, host: str) -> Callable[[str, str | None], rt.VmResult]:
    def run(command: str, stdin_data: str | None = None) -> rt.VmResult:
        return rt.ssh_vm(user, key, host, command, stdin_data)

    return run


def ship_image(user: str, key: str, host: str, image: str, work: pathlib.Path) -> int:
    """`docker save <image>` into the work directory, then `sudo docker load` on `host` from that file over ssh's stdin. The first non-zero exit, or 0."""
    tarball = work / "server-image.tar"
    saved = subprocess.run(["docker", "save", "-o", str(tarball), image], check=False)
    if saved.returncode != 0:
        return saved.returncode
    try:
        with tarball.open("rb") as stream:
            loaded = subprocess.run(
                vm_ssh.ssh_argv(user, key, host, "sudo -n docker load"),
                stdin=stream,
                stdout=subprocess.DEVNULL,
                check=False,
            )
        return loaded.returncode
    finally:
        with contextlib.suppress(OSError):
            tarball.unlink()


def local_rc(argv: list[str]) -> int:
    return subprocess.run(argv, capture_output=True, check=False).returncode


class EliteCompose:
    """One run. `elite`, `machine`, `ship`, `local`, `api_factory`, `roundtrip_factory` and `sleep` are the seams: the real ones reach VMs, docker and HTTP, the tests' are scripted."""

    def __init__(
        self,
        drill: lib.Drill,
        opts: Options,
        *,
        elite: Callable[[str, str | None], rt.VmResult] | None = None,
        machine: Callable[[str, str | None], rt.VmResult] | None = None,
        ship: Callable[[], int] | None = None,
        local: Callable[[list[str]], int] | None = None,
        api_factory: Callable[[str], rt.Api] | None = None,
        roundtrip_factory: Callable[..., rt.Roundtrip] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.d = drill
        self.o = opts
        self.elite = elite or ssh_runner(opts.ssh_user, opts.ssh_key, opts.elite_vm)
        self.machine = machine or ssh_runner(opts.ssh_user, opts.ssh_key, opts.machine_vm)
        self.ship = ship or self._ship
        self.local = local or local_rc
        self.api_factory = api_factory or rt.Api
        self.roundtrip_factory = roundtrip_factory or EliteRoundtrip
        self.sleep = sleep or time.sleep
        self.stack_dir = "/tmp/rediacc-elite-drill-%s" % uuid.uuid4().hex[:8]
        self.stack_up = False
        self.cert_b64 = ""
        self.base_url = "http://%s:%d" % (opts.elite_vm, HTTP_PORT)

    def _ship(self) -> int:
        o = self.o
        return ship_image(o.ssh_user, o.ssh_key, o.elite_vm, o.image, self.work)

    @property
    def work(self) -> pathlib.Path:
        if self.d.work is None:
            raise RuntimeError("Drill.init() must run first")
        return self.d.work

    # ------------------------------------------------------------------ preflight

    def preflight(self) -> None:
        d, o = self.d, self.o
        d.step(
            "%s preflight: both machines, docker on the elite VM, renet on the machine VM, the image here"
            % STEP_LABEL
        )
        problems = [
            "private/elite/%s is missing (private/elite is not checked out)" % name
            for name in COMPOSE_FILES
            if not (d.root / "private" / "elite" / name).is_file()
        ]
        if self.local(["docker", "image", "inspect", o.image]) != 0:
            problems.append(
                "image %s is not on this host; build it with "
                "PYTHONPATH=.ci python3 -m rediacc_ci.ops.build_server onprem" % o.image
            )
        probes = (
            (
                "elite",
                o.elite_vm,
                self.elite,
                "sudo -n docker compose version >/dev/null",
                "docker compose",
            ),
            (
                "machine",
                o.machine_vm,
                self.machine,
                "command -v renet >/dev/null && command -v curl >/dev/null",
                "renet and curl",
            ),
        )
        for role, host, run, command, what in probes:
            result = run(command, None)
            if result.returncode == vm_ssh.SSH_FAILED:
                problems.append(
                    "ssh to the %s VM %s failed as %s with %s: %s"
                    % (
                        role,
                        host,
                        o.ssh_user,
                        o.ssh_key,
                        result.stderr.strip()[-200:] or "no stderr",
                    )
                )
            elif result.returncode != 0:
                problems.append("the %s VM %s lacks %s" % (role, host, what))
        if problems:
            for line in problems:
                log.error(line)
            raise SystemExit(1)

    # ------------------------------------------------------------------ row 1: the upstream cert

    def mint_cert(self, ed25519_pub: str) -> None:
        d, o = self.d, self.o
        d.step(
            "%s: the upstream (dev gateway) issues a delegation cert for the box's key" % STEP_LABEL
        )
        if not d.gateway_alive():
            d.restart_gateway()
        email = "elite-compose-%s@rediacc.io" % uuid.uuid4().hex[:8]
        d.account_ensure_login(email, LOGIN_PHRASE)
        d.account_ensure_subscription(email, o.plan)
        jar = http.cookiejar.CookieJar()
        if not d.account_session(email, LOGIN_PHRASE, jar):
            raise SystemExit(1)
        sub = d.account_subscription_id(jar)
        answer = d.api_post(
            "/portal/delegation-certs",
            {
                "subscriptionId": sub,
                "delegatedPublicKey": ed25519_pub,
                "validDays": CERT_VALID_DAYS,
            },
            jar,
        )
        d.last_cmd = "POST /portal/delegation-certs"
        try:
            self.cert_b64 = cert_base64(answer)
        except ValueError as exc:
            d.assert_equal("a cert", "none", str(exc))
            raise SystemExit(1) from exc
        d.assert_equal(
            sub,
            cert_subscription(self.cert_b64),
            "the upstream issued a delegation cert naming subscription %s" % sub,
        )

    # ------------------------------------------------------------------ row 2: the stack

    def put_file(self, path: str, text: str) -> None:
        result = self.elite("umask 077 && cat > %s" % shlex.quote(path), text)
        if result.returncode != 0:
            log.error("writing %s on the elite VM failed: %s" % (path, result.stderr.strip()))
            raise SystemExit(1)

    def stack_up_row(self, env: dict[str, str]) -> None:
        d, o = self.d, self.o
        d.step("%s: elite compose up on %s" % (STEP_LABEL, o.elite_vm))
        made = self.elite("mkdir -p %s" % shlex.quote(self.stack_dir), None)
        if made.returncode != 0:
            log.error("mkdir %s on the elite VM failed: %s" % (self.stack_dir, made.stderr.strip()))
            raise SystemExit(1)
        for name in COMPOSE_FILES:
            text = (d.root / "private" / "elite" / name).read_text(encoding="utf-8")
            self.put_file("%s/%s" % (self.stack_dir, name), text)
        self.put_file("%s/.env" % self.stack_dir, env_text(env))
        d.last_cmd = "docker save %s | ssh %s sudo docker load" % (o.image, o.elite_vm)
        d.assert_equal("0", str(self.ship()), "the server image is loaded on the elite VM")
        tag = self.elite(
            "sudo -n docker tag %s %s/server:%s"
            % (shlex.quote(o.image), DRILL_REGISTRY, DRILL_TAG),
            None,
        )
        d.last_cmd = "docker tag on the elite VM"
        d.assert_equal("0", str(tag.returncode), "the image carries the tag the compose file names")
        self.stack_up = True
        command = compose_command(self.stack_dir, "up", "-d")
        up = self.elite(command, None)
        d.last_cmd = command
        if up.returncode != 0:
            log.error(up.stderr.strip()[-2000:])
        d.assert_equal("0", str(up.returncode), "docker compose up -d with the elite files")
        if up.returncode != 0:
            raise SystemExit(1)

    # ------------------------------------------------------------------ row 3: reach from the machine

    def await_server(self) -> str:
        """The status the machine VM reads for `server-info`, polled until 200 or the wait runs out."""
        status = CURL_NOTHING
        for _ in range(HEALTH_TRIES):
            status = self.machine(
                curl_status_command(self.base_url + SERVER_INFO), None
            ).stdout.strip()
            if status == "200":
                return status
            self.sleep(HEALTH_INTERVAL_S)
        return status

    def reach_rows(self) -> bool:
        """True when the account server answered; the snapshot rows need it."""
        d, o = self.d, self.o
        d.step("%s: what the machine VM %s reaches on the elite VM" % (STEP_LABEL, o.machine_vm))
        status = self.await_server()
        d.last_cmd = "machine: curl %s%s" % (self.base_url, SERVER_INFO)
        d.assert_equal(
            "200",
            status,
            "the account server answers server-info through nginx (the box is enrolled)",
        )
        if status != "200":
            logs = self.elite(compose_command(self.stack_dir, "logs", "--tail", "60", "web"), None)
            log.error(logs.stdout.strip()[-4000:])
        store = "http://%s:%d/" % (o.elite_vm, STORE_PORT)
        got = self.machine(curl_status_command(store), None).stdout.strip()
        d.last_cmd = "machine: curl %s" % store
        d.assert_equal(
            "403",
            got,
            "the published store answers 403 (up, wants credentials) from outside the stack",
        )
        closed = "http://%s:%d/" % (o.elite_vm, lib.free_port())
        got = self.machine(curl_status_command(closed), None).stdout.strip()
        d.last_cmd = "machine: curl %s" % closed
        d.assert_equal(
            CURL_NOTHING,
            got,
            "planted control: a closed port on the same host answers nothing, so the 403 above is the store",
        )
        resolved = self.machine("getent hosts %s" % INTERNAL_STORE_HOST, None)
        d.last_cmd = "machine: getent hosts %s" % INTERNAL_STORE_HOST
        d.assert_equal(
            "2",  # getent's "key not found"; an ssh failure (255) or a missing getent (127) is no answer
            str(resolved.returncode),
            "control: the machine cannot resolve %s, so it is outside the docker network and only "
            "the public endpoint can serve it" % INTERNAL_STORE_HOST,
        )
        return status == "200"

    # ------------------------------------------------------------------ rows 4 and 5: register, snapshot

    def register(self) -> tuple[rt.Api, str]:
        """The first registration adopts the cert's subscription. Returns the API, its bearer set, and that subscription id."""
        d = self.d
        d.step("%s: register on the box; the root org adopts the cert's subscription" % STEP_LABEL)
        api = self.api_factory(self.base_url)
        email = "elite-owner-%s@rediacc.io" % uuid.uuid4().hex[:8]
        creds = {"email": email, "password": LOGIN_PHRASE}
        api.call("POST", "/auth/register", creds)
        api.call("POST", "/auth/login", creds)
        sub = str(api.call("GET", "/portal/subscription").get("id", ""))
        d.last_cmd = "GET /portal/subscription on the box"
        d.assert_equal(
            cert_subscription(self.cert_b64),
            sub,
            "the box's subscription is the one the delegation cert names",
        )
        token = api.call(
            "POST",
            "/api-tokens",
            {"subscriptionId": sub, "name": "elite-compose-drill", "scopes": rt.SCOPES},
        ).get("token", "")
        if not token:
            raise rt.StepError("the box minted no API token")
        api.token = str(token)
        # The login cookie only authorises the token mint; every later call carries the bearer alone.
        api.cookies.clear()
        return api, sub

    def snapshot_rows(self) -> None:
        d = self.d
        try:
            api, sub = self.register()
        except rt.StepError as exc:
            d.last_cmd = "register on the box"
            d.assert_equal("registered", "failed", str(exc))
            return
        d.step(
            "%s: the machine VM snapshots into the box and restores (backup_roundtrip)" % STEP_LABEL
        )
        trip = self.roundtrip_factory(self.machine, api, self.work, say=d.note, subscription=sub)
        rc = trip.run()
        d.last_cmd = "backup_roundtrip against %s from %s" % (self.base_url, self.o.machine_vm)
        d.assert_equal(
            "0",
            str(rc),
            "a machine outside the docker network completes a snapshot and a byte-identical restore",
        )

    # ------------------------------------------------------------------ teardown and main

    def teardown(self) -> None:
        o = self.o
        if o.keep_stack:
            self.d.note(
                "--keep-stack: the stack stays up in %s on %s" % (self.stack_dir, o.elite_vm)
            )
            return
        if self.stack_up:
            self.elite(compose_command(self.stack_dir, "down", "-v", "--remove-orphans"), None)
            self.elite("sudo -n docker image rm %s/server:%s" % (DRILL_REGISTRY, DRILL_TAG), None)
        self.elite("rm -rf %s" % shlex.quote(self.stack_dir), None)

    def run_all(self) -> int:
        d = self.d
        d.selftest_probe()
        if d.selftest:
            d.note("selftest mode: stopping before any machine, gateway or store work")
            return d.summary()
        self.preflight()
        crypto = account.generate_crypto_keys(strict=True)
        keys = {
            "ed25519_priv": crypto.ed25519_priv,
            "ed25519_pub": crypto.ed25519_pub,
            "x25519_priv": crypto.x25519_priv,
            "x25519_pub": crypto.x25519_pub,
            "api_key": crypto.api_key,
            "jwt": crypto.jwt,
        }
        self.mint_cert(keys["ed25519_pub"])
        env = elite_env(
            self.o.elite_vm,
            keys=keys,
            cert_b64=self.cert_b64,
            store_access=secrets.token_hex(16),
            store_secret=secrets.token_hex(32),
            config_key=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        )
        try:
            self.stack_up_row(env)
            if self.reach_rows():
                self.snapshot_rows()
        finally:
            self.teardown()
        return d.summary()


def main(argv: list[str]) -> int:
    try:
        opts = parse_args(argv)
    except ValueError as exc:
        log.error(str(exc))
        print(USAGE, file=sys.stderr)
        return 2
    drill = lib.Drill("backup-elite-compose", selftest=opts.selftest, keep_work=opts.keep_work)
    drill.init()
    rc = 1
    try:
        rc = EliteCompose(drill, opts).run_all()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except (OSError, ValueError) as exc:
        log.error(str(exc))
        rc = 1
    finally:
        drill.teardown()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
