"""rediacc_ci.spikes.do_policy_spike: the three verbs and the verdict logic, against a fake wrangler and a fake Worker."""

import json
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest

from rediacc_ci.spikes import do_policy_spike as sp

FAKE_WRANGLER = """#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_LOG"]
args = sys.argv[1:]
open(log, "a").write(json.dumps(args) + "\\n")
state = os.environ["FAKE_APPS"]
apps = json.load(open(state)) if os.path.exists(state) else []
if args[0] == "deploy" and "--dry-run" in args:
    print("X [ERROR] max_instances is not supported for durable_object", file=sys.stderr)
    sys.exit(1)
if args[0] == "deploy":
    json.dump([{"id": "9e7ef1cfc0b94feeadd6707d63c8264a", "name": "rediacc-do-policy-spike-SpikeDO"}], open(state, "w"))
    print("Uploaded rediacc-do-policy-spike\\nhttps://rediacc-do-policy-spike.example.workers.dev\\nCurrent Version ID: v-abc")
elif args[:2] == ["containers", "list"]:
    rows = "".join("\u2502 %s \u2502 %s \u2502 ready \u2502 0 \u2502\\n" % (a["id"], a["name"]) for a in apps)
    print("\u250c ID \u2502 NAME \u2502 STATE \u2502\\n" + rows)
elif args[:2] == ["containers", "delete"] and os.environ.get("FAKE_STUCK") != "1":
    json.dump([], open(state, "w"))
"""


@pytest.fixture
def fake(tmp_path, monkeypatch):
    binary = tmp_path / "wrangler"
    binary.write_text(FAKE_WRANGLER)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("WRANGLER_BIN", str(binary))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("FAKE_APPS", str(tmp_path / "apps.json"))
    monkeypatch.setattr(sp, "COLD_STARTS", 2)
    monkeypatch.setattr(sp, "CALLS_PER_ORG", 3)
    return scratch, tmp_path


def calls(tmp_path):
    return [json.loads(line) for line in (tmp_path / "log").read_text().splitlines()]


def test_scratch_worker_is_policy_entry_without_max_instances(tmp_path):
    sp.write_scratch("v1", "k", True, tmp_path)
    toml = (tmp_path / "wrangler.toml").read_text()
    assert 'scheduling_policy = "durable_object"' in toml
    assert "max_instances" not in toml
    assert "instance_type" not in toml
    assert "[containers.images.executor]" in toml
    assert "workers/proxy/Dockerfile" in toml
    assert "executor" not in (sp.WRANGLER_TOML.format(name="n", version="v", key="k", executor=""))
    assert "max_instances = 25" in sp.PLANTED_MAX_INSTANCES


def test_deploy_records_url_and_never_prints_the_key(fake, capsys):
    scratch, _ = fake
    state = sp.deploy(scratch=scratch, key="sekrit-key")
    assert state["url"] == "https://rediacc-do-policy-spike.example.workers.dev"
    assert state["version_id"] == "v-abc"
    assert "sekrit-key" not in capsys.readouterr().out


def test_teardown_deletes_worker_and_apps_then_passes(fake, capsys):
    scratch, tmp = fake
    sp.deploy(scratch=scratch)
    assert sp.teardown(scratch) == 0
    verbs = [c[:2] if c[0] == "containers" else c[:1] for c in calls(tmp)]
    assert ["delete"] in verbs
    assert ["containers", "delete"] in verbs
    assert "remaining rediacc-do-policy-spike applications: 0" in capsys.readouterr().out
    assert not sp.deploy_state_path(scratch).exists()


def test_teardown_fails_while_an_application_remains(fake, monkeypatch):
    scratch, _ = fake
    sp.deploy(scratch=scratch)
    monkeypatch.setenv("FAKE_STUCK", "1")
    assert sp.teardown(scratch) == 1


def test_du6_reads_wrangler_refusal(fake):
    scratch, _ = fake
    assert sp.prove_du6(scratch)["outcome"] == "refused"


class FakeWorker(BaseHTTPRequestHandler):
    """Echoes props per org; `leak` makes org-b answer with org-a's props."""

    leak = False
    rot: ClassVar[dict] = {}
    boot = "b1"
    version = "v1"

    def log_message(self, *a):
        pass

    def reply(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")
            return
        _, _, name, op = url.path.split("/")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        org = q.get("org", name)
        base = {
            "boot": self.boot,
            "version": self.version,
            "containerId": "id-" + org,
            "ctorRunning": True,
        }
        if op == "start":
            self.rot[org] = int(q.get("rot", 0))
            self.reply(
                {
                    **base,
                    "accepted": q.get("size") != "basic",
                    "ready": q.get("size") != "basic",
                    "ready_ms": 100,
                }
            )
        elif op == "reregister":
            self.rot[org] = int(q.get("rot", 0))
            self.reply({**base, "reregistered": True})
        elif op == "call":
            who = "org-a" if (self.leak and org == "org-b") else org
            props = {"orgId": who, "containerId": "id-" + who, "rot": self.rot.get(org, 0)}
            self.reply({**base, "result": [{"status": 200, "body": {"props": props}}]})
        elif op == "tcp":
            self.reply({**base, "result": {"banner": "SSH-2.0-x"}})
        elif op == "fetch":
            self.reply({**base, "result": {"status": 200, "text": "pong"}})
        elif op == "exec-mem":
            self.reply({**base, "stdout": "%d\n%d\n" % (100 * 2**20, 150 * 2**20), "exitCode": 0})
        else:
            self.reply({**base, "running": True})


@pytest.fixture
def server():
    FakeWorker.leak = False
    FakeWorker.rot = {}
    FakeWorker.boot = "b1"
    FakeWorker.version = "v1"
    httpd = HTTPServer(("127.0.0.1", 0), FakeWorker)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_port
    httpd.shutdown()
    httpd.server_close()


def redeployed():
    FakeWorker.boot, FakeWorker.version = "b2", "v2"
    return {}


def seed(scratch, url):
    sp.deploy_state_path(scratch).write_text(
        json.dumps({"url": url, "key": "k", "executor_image": True})
    )


def test_run_records_go_verdict_with_zero_cross_answers(fake, server, monkeypatch):
    scratch, tmp = fake
    seed(scratch, server)
    monkeypatch.setattr(sp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(sp, "deploy", lambda **_kw: redeployed())
    record = tmp / "result.json"
    result = sp.run(record, scratch=scratch, skip_dev=True)
    saved = json.loads(record.read_text())
    assert saved["cross_answers"] == 0
    assert saved["verdict"] == "GO"
    assert result["du"]["DU1"]["rotated_props_seen"] is True
    assert result["du"]["DU3"]["sizes"]["basic"]["accepted"] is False
    assert result["du"]["DU3"]["executor_under_lite"]["idle_peak_mib"] == 150.0
    assert result["du"]["DU7"]["reachable"] is True
    assert result["du"]["DU6"]["outcome"] == "refused"
    assert result["light"].startswith("custom")


def test_run_counts_a_cross_answer_and_refuses_go(fake, server, monkeypatch):
    scratch, tmp = fake
    seed(scratch, server)
    FakeWorker.leak = True
    monkeypatch.setattr(sp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(sp, "deploy", lambda **_kw: redeployed())
    result = sp.run(tmp / "r.json", scratch=scratch, skip_dev=True)
    assert result["cross_answers"] > 0
    assert result["verdict"] == "FALLBACK-1"


def test_decide_without_interception_picks_c_or_stop():
    du = {
        "DU1": {"answered": 0, "calls": 6},
        "public_route": {"reachable": True},
        "DU3": {
            "sizes": {"lite": {}, "custom": {"accepted": True}, "standard-1": {}},
            "executor_under_lite": {},
        },
    }
    assert sp.decide(du)["verdict"] == "FALLBACK-2"
    du["public_route"] = {"reachable": False}
    assert sp.decide(du)["verdict"] == "STOP"


def test_spike_apps_parses_the_table_and_flags_unparsed_mentions():
    table = "\u2502 9e7ef1cfc0b94feeadd6707d63c8264a \u2502 rediacc-do-policy-spike-spikedo \u2502 ready \u2502\n\u2502 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \u2502 other-app \u2502 ready \u2502"
    assert [a["id"] for a in sp.spike_apps(table)] == ["9e7ef1cfc0b94feeadd6707d63c8264a"]
    assert sp.spike_apps("no apps here") == []
    assert sp.spike_apps("a new format naming rediacc-do-policy-spike") == [{"unparsed": True}]


def test_spike_apps_fails_when_one_row_parses_and_another_does_not():
    good = "\u2502 9e7ef1cfc0b94feeadd6707d63c8264a \u2502 rediacc-do-policy-spike-spikedo \u2502 ready \u2502"
    odd = "\u2502 not-an-id \u2502 rediacc-do-policy-spike-other \u2502 ready \u2502"
    got = sp.spike_apps(good + "\n" + odd)
    assert {"unparsed": True} in got
    assert len(got) == 2


def test_spike_apps_json_without_result_list_is_a_failure():
    assert sp.spike_apps('{"apps": []}') == [{"unparsed": True}]
    assert sp.spike_apps('{"result": "x"}') == [{"unparsed": True}]
    assert sp.spike_apps('{"result": []}') == []
    assert sp.spike_apps("[]") == []


def du_for_decide(du2):
    du = {
        "DU1": {
            "answered": 6,
            "calls": 6,
            "cross_answers": 0,
            "missing_props": 0,
            "distinct_container_ids": 2,
            "rotated_props_seen": True,
        },
        "public_route": {"reachable": True},
        "DU3": {
            "sizes": {"lite": {}, "custom": {"accepted": True}, "standard-1": {}},
            "executor_under_lite": {},
        },
    }
    if du2 is not None:
        du["DU2"] = du2
    return du


def test_decide_go_needs_a_live_intercept_after_the_redeploy():
    alive = {"intercept_survived_without_reregister": True, "reregister_needed_and_works": None}
    fixed = {"intercept_survived_without_reregister": False, "reregister_needed_and_works": True}
    dead = {"intercept_survived_without_reregister": False, "reregister_needed_and_works": False}
    assert sp.decide(du_for_decide(alive))["verdict"] == "GO"
    assert sp.decide(du_for_decide(fixed))["verdict"] == "GO"
    assert sp.decide(du_for_decide(dead))["verdict"] == "FALLBACK-1"
    assert sp.decide(du_for_decide(None))["verdict"] == "FALLBACK-1"


def test_main_reexecs_under_the_profile_even_with_wrangler_bin_set(monkeypatch):
    seen: list[list[str]] = []

    def fake_reexec(argv: list[str]) -> int:
        seen.append(argv)
        return 7

    monkeypatch.setattr(sp, "reexec", fake_reexec)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv(sp.PROFILES_ENV, raising=False)
    monkeypatch.setenv("WRANGLER_BIN", "/usr/bin/true")
    assert sp.main(["teardown"]) == 7
    assert seen == [["teardown"]]


def test_main_runs_in_process_when_a_token_is_present(monkeypatch):
    monkeypatch.setattr(sp, "reexec", lambda _argv: pytest.fail("re-executed with a token set"))
    monkeypatch.setattr(sp, "teardown", lambda: 5)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "present")
    assert sp.main(["teardown"]) == 5


def always_failing_call(_self, _name, op, **_params):
    return {"containerId": "id", "ready": True} if op == "start" else {"result": []}


def test_du1_counts_only_the_retries_actually_made(monkeypatch):
    monkeypatch.setattr(sp, "CALLS_PER_ORG", 2)
    monkeypatch.setattr(sp.Worker, "call", always_failing_call)
    got = sp.prove_du1(sp.Worker("http://127.0.0.1:1", "k"))
    # 2 orgs x 2 calls, each tried TRANSIENT_RETRIES times: the first try plus (n - 1) retries.
    assert got["transient_retries"] == 4 * (sp.TRANSIENT_RETRIES - 1)
    assert got["missing_props"] == 4
