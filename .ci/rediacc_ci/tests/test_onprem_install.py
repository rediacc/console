"""`./run.sh onprem install|status` (PLAN-enterprise-tenants box P2) over fakes: no docker, no network, no bench login, no rdc.

Each refusal test has a CONTROL that runs the same scenario with the one fault removed and passes, so a refusal can only come from that fault. Each would FAIL BEFORE the module: there was no `onprem` verb to call.
"""

from __future__ import annotations

import base64
import json
import stat
import types

import pytest

from rediacc_ci.onprem import install as ob

SUB = "sub-111"
DOMAIN = "acme.rediacc.io"
KEY = "SPKI-PUB-OF-THIS-INSTALL"


def cert_answer(sub: str = SUB) -> dict:
    payload = base64.b64encode(json.dumps({"subscriptionId": sub}).encode()).decode()
    return {"cert": {"payload": payload, "signature": "sig"}, "id": "cert-1"}


class FakeRdc:
    def __init__(self, machine_out: str = '{"renet":"1.2"}', repo_exists: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.machine_out = machine_out
        self.repo_exists = repo_exists

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        verb = argv[2:]
        if verb[:3] == ["-o", "json", "machine"]:
            return 0, self.machine_out
        if verb[:3] == ["-o", "json", "repo"]:
            return (0, "{}") if self.repo_exists else (1, "")
        if verb[:2] == ["repo", "create"]:
            self.repo_exists = True
        return 0, ""

    def verbs(self) -> list[str]:
        out = []
        for call in self.calls:
            words = call[2:]
            if words[:2] == ["-o", "json"]:
                words = words[2:]
            out.append(" ".join(words[:2]))
        return out


class FakePortal:
    def __init__(self, active=()) -> None:
        self.bodies: list[object] = []
        self.active = list(active)
        self.calls: list[tuple[str, str]] = []

    def call(self, method, path, body=None):
        self.calls.append((method, path.split("?")[0]))
        self.bodies.append(body)
        if path == "/subscription":
            return {"id": SUB}
        if method == "GET":
            return {"items": self.active}
        return cert_answer(SUB)


class FakeBox:
    def __init__(self, sub: str = SUB) -> None:
        self.sub = sub
        self.bodies: list[object] = []
        self.calls: list[tuple[str, str]] = []

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        self.bodies.append(body)
        if path == "/portal/subscription":
            return {"id": self.sub}
        return {}

    def accept_terms(self):
        return True


def keys() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        ed25519_priv="edpriv",
        ed25519_pub=KEY,
        x25519_priv="xpriv",
        x25519_pub="xpub",
        api_key="apikey",
        jwt="jwtsecret",
    )


class FakeBws:
    """The bws store: entries by name, every write recorded. Values live only here."""

    def __init__(self, held=None) -> None:
        self.entries: dict[str, str] = dict(held or {})
        self.writes: list[tuple[str, str]] = []
        self.project = ""

    def read(self, names):
        return {n: self.entries[n] for n in names if n in self.entries}

    def create(self, name, value):
        self.writes.append(("create", name))
        self.entries[name] = value

    def edit(self, name, value):
        self.writes.append(("edit", name))
        self.entries[name] = value


class Harness:
    def __init__(self, tmp_path, **kw) -> None:
        self.rdc = FakeRdc(**{k: kw.pop(k) for k in ("machine_out", "repo_exists") if k in kw})
        self.portal = FakePortal(kw.pop("active", ()))
        self.box = FakeBox(kw.pop("box_sub", SUB))
        self.local_calls: list[list[str]] = []
        self.resolved = kw.pop("resolved", {"203.0.113.9"})
        self.health = kw.pop("health", (200, ["*.rediacc.io"]))
        self.cf_calls: list[tuple] = []
        self.keygen_calls = 0
        self.bws = FakeBws(kw.pop("held", None))
        kw.setdefault("bws_project", "proj-1")
        self.options = ob.Options(
            config=kw.pop("config", "eu-bench"),
            machine="hostinger",
            domain=DOMAIN,
            owner="boss@acme.example",
            public_ip="203.0.113.9",
            state_dir=tmp_path / "state",
            **kw,
        )
        self.deps = ob.Deps(
            rdc=self.rdc,
            local=self.local,
            resolve=lambda _host: set(self.resolved),
            cf=lambda: self.cf_calls.append(("cf",)) or (lambda *_a, **_k: {}),
            bws=self.open_bws,
            portal=lambda: self.portal,
            box_api=lambda _domain: self.box,
            health=lambda _domain: self.health,
            keygen=self.keygen,
            token=lambda: "t" * 40,
            sleep=lambda _s: None,
            now=lambda: 1_700_000_000.0,
        )
        self.said: list[str] = []

    def open_bws(self, project):
        self.bws.project = project
        return self.bws

    def local(self, argv):
        self.local_calls.append(list(argv))
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0
        if argv[:2] == ["docker", "save"]:
            target = argv[3]
            with open(target, "w", encoding="utf-8") as stream:
                stream.write("tar")
        return 0

    def keygen(self):
        self.keygen_calls += 1
        return keys()

    def install(self) -> ob.Install:
        return ob.Install(self.options, self.deps, say=self.said.append)


def test_the_happy_path_runs_every_step_in_order_and_writes_no_secret_to_the_record(tmp_path):
    h = Harness(tmp_path)
    h.install().run()
    state = tmp_path / "state"
    ledger = json.loads((state / "ledger.json").read_text())
    assert list(ledger["steps"]) == list(ob.STEPS)
    assert h.rdc.verbs() == [
        "machine status",
        "repo status",
        "repo status",
        "repo create",
        "repo admin",
        "repo sync",
        "repo sync",
        "repo up",
    ]
    assert ("POST", "/delegation-certs") in h.portal.calls
    assert ("POST", "/auth/register") in h.box.calls
    record = (state / "install.json").read_text()
    for secret in ("edpriv", "xpriv", "jwtsecret", "apikey", "t" * 40):
        assert secret not in record
    secrets_env = (state / "stage" / "secrets.env").read_text()
    assert 'ELITE_DOMAIN="%s"' % DOMAIN in secrets_env
    assert 'ELITE_STORE_DOMAIN="acme-store.rediacc.io"' in secrets_env
    assert "DELEGATION_CERT_BASE64=" in secrets_env
    for name in ("ledger.json", "keys.json", "cert.b64", "owner.json"):
        assert stat.S_IMODE((state / name).stat().st_mode) == 0o600
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    uploads = [c for c in h.rdc.calls if c[2:5] == ["repo", "sync", "upload"]]
    assert all("--verify" in c for c in uploads)
    assert len(uploads) == 2


def test_a_rerun_skips_the_done_steps_and_a_failed_step_resumes_there(tmp_path):
    h = Harness(tmp_path, health=(503, []))
    with pytest.raises(ob.InstallError, match=r"wait: .*answered 503"):
        h.install().run()
    done = json.loads((tmp_path / "state" / "ledger.json").read_text())["steps"]
    assert "up" in done
    assert "wait" not in done
    first_calls = len(h.rdc.calls)
    created = h.keygen_calls
    h.health = (200, [DOMAIN])
    h.deps.health = lambda _domain: h.health
    h.said.clear()
    h.install().run()
    assert h.keygen_calls == created == 1
    assert [c for c in h.rdc.calls[first_calls:] if c[2:4] == ["repo", "up"]] == []
    assert "up: done earlier, skipped" in h.said
    control = json.loads((tmp_path / "state" / "ledger.json").read_text())["steps"]
    assert list(control) == list(ob.STEPS)


def test_eu_remote_is_refused_for_install_and_for_any_mutating_call(tmp_path):
    h = Harness(tmp_path, config="eu-remote")
    with pytest.raises(ob.InstallError, match="eu-remote"):
        h.install().run()
    assert h.rdc.calls == []
    with pytest.raises(ob.InstallError, match="mutating call"):
        h.install().rdc("repo", "up", "elite@hostinger")
    assert h.rdc.calls == []
    # control: a read through the same config goes out, and the write goes out through eu-bench
    assert h.install().rdc("-o", "json", "machine", "status", "m", mutating=False)[0] == 0
    ok = Harness(tmp_path / "ok")
    assert ok.install().rdc("repo", "up", "elite@hostinger")[0] == 0


def test_an_active_cert_for_another_key_is_refused_naming_the_revoke_route(tmp_path):
    other = {"id": "cert-9", "delegatedPublicKey": "SOMEONE-ELSES-KEY"}
    h = Harness(tmp_path, active=[other])
    with pytest.raises(ob.InstallError, match=r"another key.*delegation-certs/cert-9/revoke"):
        h.install().run()
    assert ("POST", "/delegation-certs") not in h.portal.calls
    assert "cert" not in json.loads((tmp_path / "state" / "ledger.json").read_text())["steps"]
    # control: no active cert at all issues one
    ok = Harness(tmp_path / "ok")
    ok.install().run()
    assert ("POST", "/delegation-certs") in ok.portal.calls


def test_an_active_cert_for_the_same_key_is_reused_only_from_its_saved_copy(tmp_path):
    same = {"id": "cert-1", "delegatedPublicKey": KEY}
    h = Harness(tmp_path, active=[same])
    h.install().step_keys()
    with pytest.raises(ob.InstallError, match="no copy is saved"):
        h.install().step_cert()
    ob.write_private(tmp_path / "state" / "cert.b64", "c2F2ZWQ=")
    h.install().step_cert()
    assert ("POST", "/delegation-certs") not in h.portal.calls
    assert (tmp_path / "state" / "cert.b64").read_text() == "c2F2ZWQ="


def test_an_owner_subscription_that_is_not_the_certs_is_refused(tmp_path):
    h = Harness(tmp_path, box_sub="sub-STOLEN")
    with pytest.raises(ob.InstallError, match=r"owner: .*sub-STOLEN.*another account registered"):
        h.install().run()
    done = json.loads((tmp_path / "state" / "ledger.json").read_text())["steps"]
    assert "owner" not in done
    assert "record" not in done
    # control: the same box answering the cert's subscription passes
    ok = Harness(tmp_path / "ok")
    ok.install().run()
    assert "record" in json.loads((tmp_path / "ok" / "state" / "ledger.json").read_text())["steps"]


def test_a_certificate_that_does_not_cover_the_domain_fails_the_wait(tmp_path):
    h = Harness(tmp_path, health=(200, ["other.example.com"]))
    with pytest.raises(ob.InstallError, match=r"certificate covers other\.example\.com"):
        h.install().run()
    ok = Harness(tmp_path / "ok", health=(200, ["*.rediacc.io"]))
    ok.install().run()


def test_preflight_refuses_a_machine_without_renet_and_a_repo_that_is_not_ours(tmp_path):
    with pytest.raises(ob.InstallError, match="names no renet"):
        Harness(tmp_path, machine_out="{}").install().run()
    with pytest.raises(ob.InstallError, match="not created by this install"):
        Harness(tmp_path / "b", repo_exists=True).install().run()
    # control: the same repo is ours once the ledger says this install created it
    h = Harness(tmp_path / "c", repo_exists=True)
    inst = h.install()
    inst.ledger.fact("repo_created", "1")
    inst.step_preflight()


def test_dns_verifies_by_resolution_and_writes_only_what_does_not_resolve(tmp_path):
    h = Harness(tmp_path)
    h.install().step_dns()
    assert h.cf_calls == []
    wrong = Harness(tmp_path / "w", resolved={"198.51.100.1"})
    with pytest.raises(ob.InstallError, match=r"resolves to 198\.51\.100\.1, not 203\.0\.113\.9"):
        wrong.install().step_dns()
    foreign = Harness(tmp_path / "f", resolved=set())
    foreign.options.domain = "acme.customer-zone.test"
    foreign.options.store_domain = "acme-store.customer-zone.test"
    with pytest.raises(
        ob.InstallError, match=r"create A acme\.customer-zone\.test -> 203\.0\.113\.9"
    ):
        foreign.install().step_dns()
    assert foreign.cf_calls == []


def test_image_builds_only_when_missing_and_skips_with_an_image_ref(tmp_path):
    h = Harness(tmp_path)
    h.install().step_image()
    assert [c[:2] for c in h.local_calls] == [["docker", "image"], ["docker", "save"]]
    assert (tmp_path / "state" / "stage" / "images" / "server.tar").is_file()
    pulled = Harness(tmp_path / "p", image_ref="registry.example.com/server:1.0")
    pulled.install().step_image()
    assert pulled.local_calls == []
    assert 'ELITE_IMAGE="registry.example.com/server:1.0"' in _secrets(pulled)


def _secrets(h: Harness) -> str:
    inst = h.install()
    inst.step_keys()
    ob.write_private(inst.ledger.secret("cert.b64"), base64.b64encode(b"{}").decode())
    return inst.secrets_text()


def test_the_template_secrets_carry_the_variables_the_elite_template_requires(tmp_path):
    text = _secrets(Harness(tmp_path))
    names = {line.split("=", 1)[0] for line in text.splitlines()}
    template = (
        ob.paths.repo_root() / "packages/cli/templates/elite/secrets.env.example"
    ).read_text()
    wanted = {
        line.split("=", 1)[0]
        for line in template.splitlines()
        if line and not line.startswith(("#", " "))
    }
    optional = {
        "UPSTREAM_URL",
        "UPSTREAM_API_KEY",
        "UPSTREAM_PUBLIC_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
    }
    assert wanted - optional <= names


def test_status_reads_the_ledger_and_the_live_health(tmp_path, capsys):
    h = Harness(tmp_path, health=(503, []))
    with pytest.raises(ob.InstallError):
        h.install().run()
    argv = ["status", "--domain", DOMAIN, "--state-dir", str(tmp_path / "state")]
    assert ob.main(argv, h.deps) == 0
    out = capsys.readouterr().out
    assert "preflight" in out
    assert "wait       pending" in out
    assert "health     503" in out
    assert ob.main(["status", "--domain", "nobody.example.com"], h.deps) == 0
    assert "no install ledger" in capsys.readouterr().out


def test_usage_errors_exit_2_and_a_failed_step_exits_1(tmp_path, capsys):
    assert ob.main(["install", "--domain", DOMAIN]) == ob.EXIT_USAGE
    assert "missing --config" in capsys.readouterr().err
    assert ob.main(["bogus"]) == ob.EXIT_USAGE
    assert ob.main(["install", "--nope"]) == ob.EXIT_USAGE
    h = Harness(tmp_path, config="eu-remote")
    argv = [
        "install",
        "--config",
        "eu-remote",
        "--machine",
        "m",
        "--domain",
        DOMAIN,
        "--owner",
        "a@b.example",
        "--state-dir",
        str(tmp_path / "s"),
    ]
    assert ob.main(argv, h.deps) == 1
    assert "eu-remote" in capsys.readouterr().err


def _names() -> dict[str, str]:
    return {ob.backup_name(DOMAIN, key): field for field, key in ob.BACKUP_KEYS.items()}


def test_backup_stores_every_secret_once_under_opaque_names(tmp_path, capsys):
    h = Harness(tmp_path)
    h.install().run()
    assert sorted(n for _, n in h.bws.writes) == sorted(_names())
    assert {op for op, _ in h.bws.writes} == {"create"}
    assert h.bws.project == "proj-1"
    held = keys().__dict__
    for name, field in _names().items():
        if field in held:
            assert h.bws.entries[name] == held[field]
        assert ob.BACKUP_NAME.fullmatch(name)
        assert "acme" not in name.lower()
    assert h.bws.entries[ob.backup_name(DOMAIN, "ACCOUNT_ED25519_PUBLIC_KEY")] == KEY
    seen = capsys.readouterr()
    for secret in ("edpriv", "xpriv", "jwtsecret", "apikey", "t" * 20):
        assert secret not in seen.out + seen.err + " ".join(h.said)


def test_backup_rerun_is_a_no_op_and_a_changed_value_is_refused(tmp_path):
    h = Harness(tmp_path)
    inst = h.install()
    inst.step_keys()
    inst.step_backup()
    first = len(h.bws.writes)
    inst.step_backup()
    assert len(h.bws.writes) == first
    target = ob.backup_name(DOMAIN, "ACCOUNT_CONFIG_SERVER_KEY")
    h.bws.entries[target] = "someone-elses-value"
    with pytest.raises(ob.InstallError, match=r"ACCOUNT_CONFIG_SERVER_KEY.*--rotate") as err:
        inst.step_backup()
    assert "someone-elses-value" not in str(err.value)
    assert h.bws.entries[target] == "someone-elses-value"
    # control: with --rotate the same entry is replaced
    h.options.rotate = True
    inst.step_backup()
    assert h.bws.entries[target] != "someone-elses-value"
    assert ("edit", target) in h.bws.writes


def test_no_bws_skips_the_step_and_a_missing_project_is_refused_up_front(tmp_path):
    h = Harness(tmp_path, no_bws=True, bws_project="")
    h.install().run()
    assert h.bws.writes == []
    assert any("skipped (--no-bws)" in line for line in h.said)
    assert (tmp_path / "state" / "keys.json").is_file()
    bare = Harness(tmp_path / "b", bws_project="")
    with pytest.raises(ob.InstallError, match="--bws-project"):
        bare.install().run()
    assert bare.rdc.calls == []


def test_the_command_line_takes_the_bws_flags():
    verb, values = ob.parse(
        [
            *("install", "--config", "c", "--machine", "m", "--domain", DOMAIN),
            *("--owner", "o@x.test", "--bws-project", "p1", "--rotate", "--no-bws"),
        ]
    )
    assert verb == "install"
    assert values["bws_project"] == "p1"
    assert values["rotate"] is True
    assert values["no_bws"] is True
