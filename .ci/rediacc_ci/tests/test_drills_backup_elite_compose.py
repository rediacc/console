"""`rediacc_ci.drills.backup_elite_compose` (box I3): the pure helpers, the `.env` it writes for the elite stack, and the run's row logic against two scripted VMs, a scripted gateway and a scripted box.

The live run (two ops VMs, the dev gateway, a server image built by `rediacc_ci.ops.build_server onprem`) is the acceptance and belongs to the lead: `./run.sh drill backup-elite-compose`.
"""

from __future__ import annotations

import base64
import json
import pathlib
import shutil
import types

import pytest

from rediacc_ci.core import account, run_verbs
from rediacc_ci.drills import backup_elite_compose as ec
from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.drills import lib

ELITE = "192.168.111.11"
MACHINE = "192.168.111.12"
SUB = "sub-123"
REAL_ELITE = pathlib.Path(__file__).resolve().parents[3] / "private" / "elite"
KEYS = {
    "ed25519_priv": "ep",
    "ed25519_pub": "eu",
    "x25519_priv": "xp",
    "x25519_pub": "xu",
    "api_key": "k" * 32,
    "jwt": "j" * 32,
}


def signed_cert(sub: str = SUB) -> dict[str, str]:
    payload = base64.b64encode(json.dumps({"subscriptionId": sub}).encode()).decode()
    return {"payload": payload, "signature": "sig", "publicKeyId": "kid"}


# ---------------------------------------------------------------- pure helpers


def test_arguments_name_the_two_machines_and_refuse_one_host_for_both() -> None:
    opts = ec.parse_args(["--elite", "10.0.0.5", "--machine", "10.0.0.6", "--keep-stack"])
    assert (opts.elite_vm, opts.machine_vm, opts.keep_stack) == ("10.0.0.5", "10.0.0.6", True)
    default = ec.parse_args([])
    assert (default.elite_vm, default.machine_vm) == (ELITE, MACHINE)
    with pytest.raises(ValueError, match="same host"):
        ec.parse_args(["--elite", "10.0.0.5", "--machine", "10.0.0.5"])
    with pytest.raises(ValueError, match="needs a value"):
        ec.parse_args(["--image"])
    with pytest.raises(ValueError, match="Unknown option"):
        ec.parse_args(["--bogus"])


def test_the_env_publishes_the_store_on_the_elite_address_and_enrols_the_box() -> None:
    env = ec.elite_env(
        ELITE,
        keys=KEYS,
        cert_b64="Y2VydA==",
        store_access="a" * 32,
        store_secret="s" * 64,
        config_key="c=",
    )
    assert env["SYSTEM_DOMAIN"] == ELITE
    assert env["RUSTFS_BIND"] == ELITE
    assert env["PUBLIC_SITE_URL"] == "http://%s:%d" % (ELITE, ec.HTTP_PORT)
    assert env["ACCOUNT_ED25519_PRIVATE_KEY"] == "ep"
    assert env["DELEGATION_CERT_BASE64"] == "Y2VydA=="
    assert env["ENABLE_HTTPS"] == "false"
    # The standalone default of the public endpoint is the claim under test, so the drill never sets it.
    assert "ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT" not in env
    assert (
        "%s/server:%s" % (env["DOCKER_REGISTRY"], env["WEB_TAG"])
        == "rediacc-drill/server:elite-compose"
    )


def test_every_key_the_drill_sets_reaches_the_rendered_web_service() -> None:
    """The compose file passes only what it names: a drill key it drops would silently never reach the server."""
    both = "".join((REAL_ELITE / name).read_text(encoding="utf-8") for name in ec.COMPOSE_FILES)
    env = ec.elite_env(
        ELITE, keys=KEYS, cert_b64="x", store_access="a", store_secret="s", config_key="c"
    )
    missing = [key for key in env if "${%s" % key not in both]
    assert missing == []
    # Control: the same check names a key the files do not read.
    assert "${ON_PREMISE_PRIVATE_KEY" not in both


def test_the_env_text_is_quoted_and_refuses_a_value_it_cannot_hold() -> None:
    assert ec.env_text({"B": "2", "A": "x+/="}) == 'A="x+/="\nB="2"\n'
    with pytest.raises(ValueError, match="KEY carries") as caught:
        ec.env_text({"KEY": 'se"cret'})
    assert "se" not in str(caught.value).replace("KEY carries", "")


def test_the_cert_is_carried_as_base64_json_and_its_subscription_read_back() -> None:
    b64 = ec.cert_base64(json.dumps({"cert": signed_cert()}))
    assert json.loads(base64.b64decode(b64))["publicKeyId"] == "kid"
    assert ec.cert_subscription(b64) == SUB
    assert ec.cert_subscription("bm90LWpzb24=") == ""
    with pytest.raises(ValueError, match="no cert"):
        ec.cert_base64(json.dumps({"error": "Subscription not found"}))
    with pytest.raises(ValueError, match="not JSON"):
        ec.cert_base64("<html>")


def test_compose_runs_both_elite_files_in_the_stack_directory() -> None:
    cmd = ec.compose_command("/tmp/s", "up", "-d")
    assert (
        cmd
        == "cd /tmp/s && sudo -n docker compose -f docker-compose.yml -f docker-compose.standalone.yml up -d"
    )


# ---------------------------------------------------------------- the run, scripted


class FakeVm:
    """A VM that answers by the first matching substring, and remembers every command and stdin."""

    def __init__(self, answers: list[tuple[str, rt.VmResult]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        self.calls.append((command, stdin_data))
        for needle, result in self.answers:
            if needle in command:
                return result
        return rt.VmResult(0, "", "")


class FakeApi:
    def __init__(self, base: str, sub: str = SUB) -> None:
        self.base = base
        self.sub = sub
        self.token = ""
        self.cookies: dict[str, str] = {"session": "x"}
        self.calls: list[tuple[str, str]] = []

    def call(self, method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
        del body, timeout
        self.calls.append((method, path))
        if path == "/portal/subscription":
            return {"id": self.sub}
        if path == "/api-tokens":
            return {"token": "tok"}
        return {}


class FakeTrip:
    def __init__(self, rc: int, seen: dict) -> None:
        self.rc = rc
        self.seen = seen

    def __call__(
        self, vm, api, work, *, say, subscription
    ):  # the factory signature EliteRoundtrip has
        del work, say
        self.seen.update(vm=vm, api=api, subscription=subscription)
        return self

    def run(self) -> int:
        return self.rc


def ok(out: str = "") -> rt.VmResult:
    return rt.VmResult(0, out, "")


@pytest.fixture
def harness(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "root"
    shutil.copytree(REAL_ELITE, root / "private" / "elite", ignore=shutil.ignore_patterns(".git"))
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(
        account,
        "generate_crypto_keys",
        lambda **_k: types.SimpleNamespace(
            ed25519_priv="ep",
            ed25519_pub="eu",
            x25519_priv="xp",
            x25519_pub="xu",
            api_key="k" * 32,
            jwt="j" * 32,
        ),
    )

    def go(
        *,
        machine_answers=None,
        elite_answers=None,
        ship_rc=0,
        trip_rc=0,
        box_sub=SUB,
        cert_sub=SUB,
        image_rc=0,
        keep_stack=False,
    ):
        drill = lib.Drill("backup-elite-compose", selftest=False, keep_work=False)
        drill.init()
        posts: list[tuple[str, dict]] = []
        drill.gateway_alive = lambda: True
        drill.account_ensure_login = lambda *_a: None
        drill.account_ensure_subscription = lambda *_a, **_k: None
        drill.account_session = lambda *_a: True
        drill.account_subscription_id = lambda _jar: cert_sub

        def api_post(path, body, jar=None):
            del jar
            posts.append((path, body))
            return json.dumps({"cert": signed_cert(cert_sub)})

        drill.api_post = api_post
        elite = FakeVm(elite_answers or [])
        machine = FakeVm(
            machine_answers
            if machine_answers is not None
            else [
                (ec.SERVER_INFO, ok("200")),
                (":%d/" % ec.STORE_PORT, ok("403")),
                ("curl", ok("000")),
                ("getent", rt.VmResult(2, "", "")),
            ]
        )
        seen: dict = {}
        apis: list[FakeApi] = []

        def api_factory(base: str) -> FakeApi:
            apis.append(FakeApi(base, box_sub))
            return apis[-1]

        opts = ec.parse_args(["--keep-stack"] if keep_stack else [])
        subject = ec.EliteCompose(
            drill,
            opts,
            elite=elite,
            machine=machine,
            ship=lambda: ship_rc,
            local=lambda _argv: image_rc,
            api_factory=api_factory,
            roundtrip_factory=FakeTrip(trip_rc, seen),
            sleep=lambda _s: None,
        )
        try:
            code = subject.run_all()
        except SystemExit as exc:
            code = 100 + int(exc.code or 0)
        finally:
            drill.teardown()
        return types.SimpleNamespace(
            code=code,
            drill=drill,
            elite=elite,
            machine=machine,
            posts=posts,
            seen=seen,
            apis=apis,
            subject=subject,
        )

    return go


def failed(run) -> list[str]:
    return [desc for _num, status, desc in run.drill.rows if status != "PASS"]


def test_a_healthy_stack_and_a_completed_snapshot_pass_every_row(harness) -> None:
    run = harness()
    assert failed(run) == []
    assert run.code == 0
    # The cert is minted for the box's own Ed25519 public key.
    assert run.posts == [
        (
            "/portal/delegation-certs",
            {"subscriptionId": SUB, "delegatedPublicKey": "eu", "validDays": ec.CERT_VALID_DAYS},
        )
    ]
    # The .env went over stdin, never on a command line, and enrols the box with that cert.
    env_writes = [stdin for cmd, stdin in run.elite.calls if cmd.endswith(("/.env'", "/.env"))]
    assert len(env_writes) == 1
    assert 'DELEGATION_CERT_BASE64="' in env_writes[0]
    assert all("ep" not in cmd.split() for cmd, _ in run.elite.calls)
    # Both compose files are the tree's own, byte for byte.
    shipped = {
        cmd.rsplit("/", 1)[-1]: stdin
        for cmd, stdin in run.elite.calls
        if stdin and "docker-compose" in cmd
    }
    assert shipped["docker-compose.yml"] == (REAL_ELITE / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    # The snapshot runs on the MACHINE VM against the box, under the adopted subscription, with the bearer and no cookie.
    assert run.seen["vm"] is run.machine
    assert run.seen["subscription"] == SUB
    assert run.apis[0].base == "http://%s:%d" % (ELITE, ec.HTTP_PORT)
    assert run.apis[0].token == "tok"
    assert run.apis[0].cookies == {}
    # The stack goes down with its volumes.
    assert any("down -v" in cmd for cmd, _ in run.elite.calls)


def test_an_unenrolled_server_fails_its_row_and_skips_the_snapshot(harness) -> None:
    run = harness(
        machine_answers=[
            (ec.SERVER_INFO, ok("502")),
            (":%d/" % ec.STORE_PORT, ok("403")),
            ("curl", ok("000")),
            ("getent", rt.VmResult(2, "", "")),
        ]
    )
    assert any("server-info" in desc for desc in failed(run))
    assert run.seen == {}
    assert run.code != 0


def test_a_store_on_loopback_only_fails_the_reach_row(harness) -> None:
    run = harness(
        machine_answers=[
            (ec.SERVER_INFO, ok("200")),
            ("curl", ok("000")),
            ("getent", rt.VmResult(2, "", "")),
        ]
    )
    assert any("published store answers 403" in desc for desc in failed(run))
    assert run.code != 0


def test_a_machine_inside_the_docker_network_fails_the_outside_control(harness) -> None:
    run = harness(
        machine_answers=[
            (ec.SERVER_INFO, ok("200")),
            (":%d/" % ec.STORE_PORT, ok("403")),
            ("curl", ok("000")),
            ("getent", ok("172.18.0.3 rediacc-rustfs")),
        ]
    )
    assert any("outside the docker network" in desc for desc in failed(run))


def test_a_failed_snapshot_fails_the_acceptance_row(harness) -> None:
    run = harness(trip_rc=2)
    assert failed(run) == [
        "a machine outside the docker network completes a snapshot and a byte-identical restore"
    ]
    assert run.code != 0


def test_a_box_that_did_not_adopt_the_cert_fails_its_row(harness) -> None:
    run = harness(box_sub="sub-other")
    assert any("delegation cert names" in desc for desc in failed(run))


def test_a_failed_compose_up_stops_the_run_and_still_tears_down(harness) -> None:
    run = harness(elite_answers=[(" up -d", rt.VmResult(1, "", "pull access denied"))])
    assert run.code == 101
    assert run.seen == {}
    assert any("down -v" in cmd for cmd, _ in run.elite.calls)


def test_keep_stack_leaves_the_stack_up(harness) -> None:
    run = harness(keep_stack=True)
    assert not any("down -v" in cmd for cmd, _ in run.elite.calls)


def test_a_missing_image_is_refused_before_any_machine_work(harness) -> None:
    run = harness(image_rc=1)
    assert run.code == 101
    assert run.posts == []
    assert not any("compose" in cmd and "up" in cmd for cmd, _ in run.elite.calls)


def test_the_drill_is_registered_with_the_run_sh_dispatcher() -> None:
    assert (
        run_verbs.DRILL_MODULES["backup-elite-compose"] == "rediacc_ci.drills.backup_elite_compose"
    )
    assert "backup-elite-compose" in run_verbs.DRILL_ARMS
