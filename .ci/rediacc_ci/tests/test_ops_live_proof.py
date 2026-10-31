"""`rediacc_ci.ops.live_proof`: `record` over a real fixture checkout with recording fakes for curl, wrangler, `go version -m` and rdc, and `verify` over the ledger.

The fixture is the console-with-two-submodules `World` of test_proof_surfaces plus a plan file with one LP box per check. The fakes answer by argv and record every call, so each case can say what ran and what did not. Every refusal case passes on a healthy control before its plant.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.ops import deploy_bench
from rediacc_ci.ops import live_proof as LP
from rediacc_ci.proof import live_tier as LT
from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S
from rediacc_ci.proof import vm_tier
from rediacc_ci.tests.test_proof_surfaces import World, _commit, _write
from rediacc_ci.tests.test_proof_vm_tier import make as make_vm
from rediacc_ci.well_known import BENCH_ORIGIN

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Sequence

UUID = "6b822ba9-1111-4222-8333-444455556666"
MOVED = "0b4e20ac-1111-4222-8333-444455556666"
PLAN_REL = "agent/plans/PLAN-demo.md"
PLAN = """# PLAN: demo

Status: approved
Depends-On: no-dep -- a fixture plan that stands alone for the recorder tests
Priority: P2 -- fixture
Concurrency: parallel
Owns: packages/cli/src/**, private/account/src/**, private/renet/cmd/**
Live-Proof: bench, hostinger -- the fixture proves the recorder end to end

## Tasks

- [ ] LP-bench [live] the cli on bench
  - Accept: live-proof bench cli-bench
- [ ] LP-bench [live] the account on bench
  - Accept: live-proof bench account-smoke
- [ ] LP-hostinger [live] renet on hostinger
  - Accept: live-proof hostinger renet-live
- [ ] LP-bench [live] the proxy on bench
  - Accept: live-proof bench proxy-ready
- [ ] LP-hostinger [live] renet on one alias
  - Accept: live-proof hostinger renet-live machine=hostinger
- [x] LP-bench [live] an already ticked box
  - Accept: live-proof bench cli-bench
"""
BIN = b"renet-binary-bytes"
BIN_SHA = hashlib.sha256(BIN).hexdigest()
ENVIRON = {
    "WORKLIST_SESSION_ID": "d778be9d",
    "CF_GLOBAL_API_KEY": "cf-global-key-value-1234567890",
    "CF_EMAIL": "ops@example.invalid",
}


class Fake:
    """Answers each argv by its first matching rule and records every call."""

    def __init__(self, renet_ptr: str) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.envs: list[dict[str, str] | None] = []
        self.answers: dict[str, LP.Result] = {
            "curl": LP.Result(0, '{"status":"ok"}\n', ""),
            "wrangler": LP.Result(0, self.deployments(UUID), ""),
            "subscription": LP.Result(0, "subscription: active\n", ""),
            "status": LP.Result(0, '{"machine":"hostinger","stale_binary":[]}\n', "hint\n"),
            "hash": LP.Result(0, BIN_SHA + "\n", ""),
            "version": LP.Result(0, "0.0.0-dev\n", ""),
            "deploy_proxy": LP.Result(0, "smoke ok\n", ""),
            "login": LP.Result(0, "eu-bench is logged in to %s\n" % BENCH_ORIGIN, ""),
        }
        # Per-key answers consumed in order before `answers` applies, for a step that fails once and then passes.
        self.queued: dict[str, list[LP.Result]] = {}
        self.build = (
            f"bin/renet: go1.24\n\tbuild\tvcs.revision={renet_ptr}\n\tbuild\tvcs.modified=false\n"
        )

    @staticmethod
    def deployments(version: str) -> str:
        return json.dumps(
            [
                {
                    "created_on": "2026-10-28T09:00:00Z",
                    "versions": [{"version_id": version, "percentage": 100}],
                }
            ]
        )

    def key(self, argv: Sequence[str]) -> str:
        if "login:bench" in argv:
            return "login"
        if argv[0] == "curl":
            return "curl"
        if "wrangler" in argv:
            return "wrangler"
        if "deploy_proxy" in " ".join(argv):
            return "deploy_proxy"
        for word in ("subscription", "status", "--version"):
            if word in argv:
                return word.lstrip("-")
        if "connect" in argv:
            return "hash"
        raise AssertionError(f"unexpected argv {argv}")

    def run(
        self,
        argv: Sequence[str],
        _cwd: pathlib.Path,
        _timeout: int,
        env: dict[str, str] | None = None,
    ) -> LP.Result:
        self.calls.append(tuple(argv))
        self.envs.append(env)
        queued = self.queued.get(self.key(argv))
        if queued:
            return queued.pop(0)
        return self.answers[self.key(argv)]

    def read_build(self, _binary: pathlib.Path) -> str | None:
        return self.build

    def ran(self, key: str) -> int:
        return sum(1 for c in self.calls if self.key(c) == key)


def _admits(_root: object, _tree: str, _inputs: object, _phases: object) -> R.Verdict:
    return R.Verdict(True, "ok", "fixture admits", {"runId": "vmc-fixture-1"})


def _refuses(_root: object, _tree: str, _inputs: object, _phases: object) -> R.Verdict:
    return R.Verdict(False, "no-receipt", "no vm:check receipt exists")


@dataclasses.dataclass
class Bed:
    world: World
    fake: Fake
    sigs: dict[str, str]

    @property
    def root(self) -> pathlib.Path:
        return self.world.root

    def lp_world(self, admit: Callable[..., R.Verdict] = _admits) -> LP.World:
        return LP.World(
            run=self.fake.run,
            read_build=self.fake.read_build,
            admit=admit,
            now=lambda: "2026-10-28T10:00:00Z",
            environ=dict(ENVIRON),
        )

    def request(self, check: str, target: str = "bench", **over: Any) -> LP.Request:
        box = {
            "cli-bench": self.sigs["the cli on bench"],
            "account-smoke": self.sigs["the account on bench"],
            "renet-live": self.sigs["renet on hostinger"],
            "proxy-ready": self.sigs["the proxy on bench"],
        }[check]
        return dataclasses.replace(LP.Request(PLAN_REL, box, target, check), **over)

    def record(self, req: LP.Request, **kw: Any) -> LP.Outcome:
        world = kw.pop("world", None) or self.lp_world(kw.pop("admit", _admits))
        return LP.record(self.root, req, world=world, **kw)

    def bench_json(self, **over: Any) -> None:
        record = {
            "version_id": UUID,
            "deployed_version_id": MOVED,
            **R.identity(self.root, deploy_bench.BENCH_SURFACES),
            "at": "2026-10-28T09:00:00Z",
        }
        record.update(over)
        _write(self.root, "/".join(deploy_bench.VERSION_RECORD), json.dumps(record))

    def ledger(self) -> list[dict[str, Any]]:
        return [e.row for e in LT.read_ledger(LT.ledger_path(self.root)) if e.row is not None]


@pytest.fixture
def bed(tmp_path: pathlib.Path) -> Bed:
    world = World(tmp_path / "console")
    _write(world.root, PLAN_REL, PLAN)
    _write(world.root, ".gitignore", ".ci/cache/\n")
    _commit(world.root, "plan")
    (world.sub / "bin").mkdir()
    (world.sub / "bin" / "renet").write_bytes(BIN)
    ptr = S.submodule_state(world.root, S.RENET_SUBMODULE)["pointer"]
    boxes = LP.D.plan_boxes(PLAN)
    sigs = {b.body.split("] ", 1)[1]: b.sig for b in boxes if not b.done}
    sigs["ticked"] = next(b.sig for b in boxes if b.done)
    return Bed(world, Fake(ptr), sigs)


# ------------------------------------------------------------------ healthy runs


def test_a_cli_run_is_verified_and_a_dry_run_writes_nothing(bed: Bed) -> None:
    out = bed.record(bed.request("cli-bench"))
    assert out.status == R.VERIFIED, out.message
    assert out.exit_code == 0
    assert not out.written
    assert bed.ledger() == []
    assert out.row is not None
    assert out.row["deploy"]["version_id"] == f"cli:{out.row['head']}"
    assert out.row["ladder"] == {"vm": None}
    assert out.log_path is not None
    assert out.log_path.read_text(encoding="utf-8").count("subscription: active") == 1


def test_write_appends_one_verified_row_that_verify_accepts(bed: Bed) -> None:
    out = bed.record(bed.request("cli-bench"), write=True)
    assert out.written
    rows = bed.ledger()
    assert len(rows) == 1
    assert rows[0] == out.row
    assert rows[0]["id"] == R.row_id(rows[0]), "the row id round-trips through the ledger"
    code, lines = LP.verify(bed.root, PLAN_REL)
    assert code == 0, lines
    assert lines[0].startswith(f"ok {rows[0]['id']}")


def test_an_account_run_reads_the_bench_record_and_confirms_it_through_wrangler(bed: Bed) -> None:
    bed.bench_json()
    out = bed.record(bed.request("account-smoke", region="eu"))
    assert out.status == R.VERIFIED, out.message
    assert out.row is not None
    assert out.row["deploy"]["version_id"] == UUID
    assert out.row["deploy"]["source"] == "bench-cache"
    assert out.row["ladder"] == {"vm": "vmc-fixture-1"}
    assert bed.fake.ran("curl") == 2
    assert bed.fake.ran("wrangler") == 1
    env = bed.fake.envs[[bed.fake.key(c) for c in bed.fake.calls].index("wrangler")]
    assert env is not None
    assert env["CLOUDFLARE_API_KEY"] == ENVIRON["CF_GLOBAL_API_KEY"]


def test_a_renet_run_rebuilds_provisions_and_compares_the_hash(bed: Bed) -> None:
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert out.status == R.VERIFIED, out.message
    assert out.row is not None
    ptr = out.row["submodules"]["private/renet"]["pointer"]
    assert out.row["deploy"]["version_id"] == f"renet:{ptr}@sha256:{BIN_SHA}"
    assert out.row["deploy"]["source"] == "rdc:eu-bench"
    assert out.row["renet"] == {"built": ptr, "modified": False, "sha256": BIN_SHA}
    assert [bed.fake.key(c) for c in bed.fake.calls] == ["status", "hash"]


def test_the_real_ladder_admits_a_verified_vm_receipt_of_the_same_tree(bed: Bed) -> None:
    ident = R.identity(
        bed.root, ["renet"], renet=lambda r: S.renet_identity(r, read_build=bed.fake.read_build)
    )
    tree = ident["tree"]
    vm_tier.write(
        bed.root,
        make_vm(
            tree=tree,
            head=ident["head"],
            inputs=S.inputs(bed.root, tree),
            submodules=ident["submodules"],
            renet=ident["renet"],
            runId="vmc-real-1",
        ),
    )
    out = bed.record(bed.request("renet-live", target="hostinger"), admit=vm_tier.admit)
    assert out.status == R.VERIFIED, out.message
    assert out.row is not None
    assert out.row["ladder"] == {"vm": "vmc-real-1"}


# ------------------------------------------------------------------ refusals that run nothing


def test_a_dirty_tree_refuses_before_any_step(bed: Bed) -> None:
    assert bed.record(bed.request("cli-bench")).status == R.VERIFIED
    bed.fake.calls.clear()
    _write(bed.root, "packages/cli/src/index.ts", "export {};\n")
    out = bed.record(bed.request("cli-bench"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.DIRTY_TREE)
    assert out.exit_code == 1
    assert bed.fake.calls == []
    assert bed.ledger() == [], "a refused run writes nothing"
    assert out.log_path is not None
    assert out.log_path.is_file(), "a refused run keeps its log"


def test_a_renet_run_with_no_admitting_vm_receipt_refuses_the_ladder(bed: Bed) -> None:
    assert bed.record(bed.request("renet-live", target="hostinger")).status == R.VERIFIED
    bed.fake.calls.clear()
    out = bed.record(bed.request("renet-live", target="hostinger"), admit=_refuses, write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, LP.CODE_LADDER)
    assert "no-receipt" in out.message
    assert bed.fake.calls == [], "no branch build reaches hostinger before the VMs pass it"
    assert bed.ledger() == []


def test_the_real_ladder_with_no_vm_receipt_refuses(bed: Bed) -> None:
    out = bed.record(bed.request("renet-live", target="hostinger"), admit=vm_tier.admit)
    assert (out.status, out.code) == (R.NOT_VERIFIED, LP.CODE_LADDER)


def test_a_modified_renet_build_refuses_modified_build(bed: Bed) -> None:
    assert bed.record(bed.request("renet-live", target="hostinger")).status == R.VERIFIED
    bed.fake.calls.clear()
    bed.fake.build = bed.fake.build.replace("vcs.modified=false", "vcs.modified=true")
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.MODIFIED_BUILD)
    assert [bed.fake.key(c) for c in bed.fake.calls] == ["version"], "one rebuild, then the refusal"


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"check": "true"}, "not in tiers.live.checks"),
        ({"check": "account-smoke", "target": "hostinger"}, "not 'hostinger'"),
        ({"machine": "prod-1"}, "not in tiers.live.targets.hostinger.machines"),
        ({"region": "mars"}, "--region"),
        ({"plan": "agent/plans/_done/PLAN-demo.md"}, "not a live plan"),
        ({"box": "ffffffff"}, "no box with signature"),
    ],
)
def test_a_request_outside_the_registry_or_the_plan_refuses_before_running(
    bed: Bed, over: dict[str, str], needle: str
) -> None:
    assert bed.record(bed.request("renet-live", target="hostinger")).status == R.VERIFIED
    bed.fake.calls.clear()
    req = dataclasses.replace(bed.request("renet-live", target="hostinger"), **over)
    with pytest.raises(LP.RequestError, match=needle):
        bed.record(req)
    assert bed.fake.calls == []


def test_a_box_whose_accept_line_names_another_check_refuses(bed: Bed) -> None:
    req = dataclasses.replace(bed.request("cli-bench"), box=bed.sigs["the account on bench"])
    with pytest.raises(LP.RequestError, match="accepts `live-proof bench account-smoke`"):
        bed.record(req)


def test_a_machine_narrowed_run_needs_the_box_that_accepts_it(bed: Bed) -> None:
    req = bed.request("renet-live", target="hostinger", machine="hostinger")
    with pytest.raises(LP.RequestError, match="machine=hostinger"):
        bed.record(req)
    narrowed = dataclasses.replace(req, box=bed.sigs["renet on one alias"])
    out = bed.record(narrowed)
    assert out.status == R.VERIFIED, out.message
    assert out.row is not None
    assert out.row["check"]["args"] == ["machine=hostinger"]


def test_a_ticked_box_refuses(bed: Bed) -> None:
    with pytest.raises(LP.RequestError, match="already ticked"):
        bed.record(dataclasses.replace(bed.request("cli-bench"), box=bed.sigs["ticked"]))


def test_a_target_the_plan_does_not_declare_refuses(bed: Bed) -> None:
    text = PLAN.replace("Live-Proof: bench, hostinger", "Live-Proof: hostinger")
    _write(bed.root, PLAN_REL, text)
    with pytest.raises(LP.RequestError, match="declares Live-Proof targets hostinger, not bench"):
        bed.record(bed.request("cli-bench"))


def test_a_check_covering_none_of_the_plan_surfaces_refuses(bed: Bed) -> None:
    text = PLAN.replace(
        "Owns: packages/cli/src/**, private/account/src/**, private/renet/cmd/**",
        "Owns: private/account/src/**",
    )
    _write(bed.root, PLAN_REL, text)
    with pytest.raises(LP.RequestError, match="none of them is both touched"):
        bed.record(bed.request("cli-bench"))


def test_no_session_refuses(bed: Bed) -> None:
    world = bed.lp_world()
    world.environ = {}
    with pytest.raises(LP.RequestError, match="--by"):
        bed.record(bed.request("cli-bench"), world=world)
    assert bed.record(bed.request("cli-bench", by="operator"), world=world).status == R.VERIFIED


# ------------------------------------------------------------------ refusals after a run


def test_a_failed_step_is_failed_and_writes_nothing(bed: Bed) -> None:
    bed.fake.answers["subscription"] = LP.Result(1, "", "not logged in\n")
    out = bed.record(bed.request("cli-bench"), write=True)
    assert (out.status, out.code) == (R.FAILED, LP.CODE_FAILED)
    assert out.exit_code == 1
    assert bed.ledger() == []
    assert out.log_path is not None
    assert "not logged in" in out.log_path.read_text(encoding="utf-8")


# The eu-bench login is the recorder's own step (operator order 2026-10-30), measured in .ci/cache/live-proof/lp-d70f12649b8f.log.
IP_REBIND = LP.Result(
    1,
    json.dumps(
        {
            "success": False,
            "errors": [
                {
                    "code": "GENERAL_ERROR",
                    "message": "The config token could not be renewed because this device's login is tied "
                    "to another network address. Your IP address changed, and this login only works from "
                    "the old one. To move it here, run any Rediacc CLI command in an interactive terminal "
                    "(for example `rdc subscription status`) and enter the code from your authenticator app.",
                }
            ],
        }
    ),
    "",
)


def test_an_ip_rebind_failure_runs_login_bench_once_and_retries_the_step(bed: Bed) -> None:
    bed.fake.queued["status"] = [IP_REBIND]
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert out.status == R.VERIFIED, out.message
    assert [bed.fake.key(c) for c in bed.fake.calls] == ["status", "login", "status", "hash"]
    assert ("npm", "run", "--silent", "login:bench") in bed.fake.calls
    assert out.row is not None
    assert len(out.row["check"]["argv"]) == 2, "the retry is one step in the row, not two"
    assert out.log_path is not None
    text = out.log_path.read_text(encoding="utf-8")
    assert "tied to another network address" in text
    assert "retry after login:bench" in text


def test_a_failing_login_bench_leaves_the_step_failed_and_names_the_remedy(bed: Bed) -> None:
    bed.fake.queued["status"] = [IP_REBIND]
    bed.fake.answers["login"] = LP.Result(1, "", "Logging eu-bench in failed (exit 1)\n")
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert (out.status, out.code) == (R.FAILED, LP.CODE_FAILED)
    assert "npm run login:bench" in out.message
    assert "never the operator" in out.message
    assert [bed.fake.key(c) for c in bed.fake.calls] == ["status", "login"]


def test_login_bench_runs_at_most_once_per_record(bed: Bed) -> None:
    bed.fake.queued["status"] = [IP_REBIND, IP_REBIND]
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert out.status == R.FAILED
    assert bed.fake.ran("login") == 1
    assert "npm run login:bench" in out.message


def test_an_unrelated_failure_does_not_run_login_bench(bed: Bed) -> None:
    """The control: a step that failed for another reason never triggers a login."""
    bed.fake.answers["subscription"] = LP.Result(1, "", "connection reset\n")
    out = bed.record(bed.request("cli-bench"))
    assert out.status == R.FAILED
    assert bed.fake.ran("login") == 0
    assert "login:bench" not in out.message


def test_a_not_logged_in_eu_bench_step_logs_in_and_retries(bed: Bed) -> None:
    bed.fake.queued["subscription"] = [
        LP.Result(1, "", "Not logged in. Humans should run `rdc subscription login`.\n")
    ]
    out = bed.record(bed.request("cli-bench"))
    assert out.status == R.VERIFIED, out.message
    assert [bed.fake.key(c) for c in bed.fake.calls] == ["subscription", "login", "subscription"]


def test_a_moved_bench_version_refuses_not_live(bed: Bed) -> None:
    bed.bench_json()
    assert bed.record(bed.request("account-smoke")).status == R.VERIFIED
    bed.fake.answers["wrangler"] = LP.Result(0, Fake.deployments(MOVED), "")
    out = bed.record(bed.request("account-smoke"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert MOVED in out.message
    assert bed.ledger() == []


def test_a_missing_or_foreign_bench_record_refuses_not_live(bed: Bed) -> None:
    out = bed.record(bed.request("account-smoke"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "no bench deploy record" in out.message
    bed.bench_json(head="9" * 40)
    out = bed.record(bed.request("account-smoke"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "not the head" in out.message
    bed.bench_json(dirty=True)
    assert "unclean tree" in bed.record(bed.request("account-smoke")).message
    assert bed.fake.ran("curl") == 0


def test_a_differing_remote_renet_hash_refuses_not_live(bed: Bed) -> None:
    bed.fake.answers["hash"] = LP.Result(0, "0" * 64 + "\n", "")
    out = bed.record(bed.request("renet-live", target="hostinger"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "remote renet hash" in out.message
    assert bed.ledger() == []


@pytest.mark.parametrize(
    "answer",
    [
        '{"stale_binary":[{"pid":1}]}',
        '{"stale_binary":null}',
        "{}",
        "not json",
    ],
)
def test_a_stale_binary_answer_that_is_not_empty_refuses(bed: Bed, answer: str) -> None:
    bed.fake.answers["status"] = LP.Result(0, answer, "")
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "stale_binary" in out.message
    assert bed.fake.ran("hash") == 0


def test_a_stale_entry_with_no_identifier_is_named_by_its_json_not_none() -> None:
    """Review dae87b66.3: an entry with none of unit, exe or pid used to read as the unit `None`."""
    text = LP._stale_text([{"detail": "x"}])
    assert "None" not in text, text
    assert '"detail": "x"' in text, text
    # Control: an entry that carries a unit is still named by it.
    assert "renet-a.service" in LP._stale_text([{"unit": "renet-a.service"}])


# The CLI's real envelope nests the answer under `data` (.ci/cache/live-proof/lp-4e32f5e0d079.log); reading the top level alone reported "stale_binary is null" for every hostinger run.
def _envelope(data: dict[str, Any]) -> str:
    return json.dumps({"success": True, "command": "machine status", "data": data}, indent=2)


def test_an_enveloped_empty_stale_binary_passes(bed: Bed) -> None:
    bed.fake.answers["status"] = LP.Result(
        0, _envelope({"machine": "hostinger", "stale_binary": []}), ""
    )
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert out.status == R.VERIFIED, out.message


def test_an_enveloped_stale_binary_list_names_its_count_and_units(bed: Bed) -> None:
    stale = [
        {
            "pid": 589867,
            "unit": "rediacc-docker-10176.service",
            "exe": "/usr/lib/rediacc/renet/current/renet (deleted)",
        },
        {
            "pid": 589901,
            "unit": "rediacc-docker-10240.service",
            "exe": "/usr/lib/rediacc/renet/current/renet (deleted)",
        },
    ]
    bed.fake.answers["status"] = LP.Result(
        0, _envelope({"machine": "hostinger", "stale_binary": stale}), ""
    )
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "2 process(es)" in out.message
    assert "rediacc-docker-10176.service" in out.message
    assert "rediacc-docker-10240.service" in out.message
    assert "null" not in out.message
    assert bed.fake.ran("hash") == 0


def test_an_envelope_without_the_key_is_still_refused(bed: Bed) -> None:
    bed.fake.answers["status"] = LP.Result(0, _envelope({"machine": "hostinger"}), "")
    out = bed.record(bed.request("renet-live", target="hostinger"))
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "stale_binary is null" in out.message


def test_an_unrecorded_deploy_is_never_verified(bed: Bed) -> None:
    text = PLAN.replace("private/renet/cmd/**", "private/renet/cmd/**, workers/proxy/src/**")
    _write(bed.root, PLAN_REL, text)
    _commit(bed.root, "proxy owns")
    out = bed.record(bed.request("proxy-ready"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, R.NOT_LIVE)
    assert "no deploy record" in out.message
    assert bed.ledger() == []


def test_a_planted_secret_in_the_tail_refuses(bed: Bed) -> None:
    assert bed.record(bed.request("cli-bench")).status == R.VERIFIED
    bed.fake.answers["subscription"] = LP.Result(0, "token ghp_" + "A" * 36 + "\n", "")
    out = bed.record(bed.request("cli-bench"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, LP.CODE_LEAK)
    assert "A" * 36 not in out.message, "the refusal names the shape, never the value"
    assert bed.ledger() == []


def test_a_secret_environment_value_is_masked_in_the_log(bed: Bed) -> None:
    bed.fake.answers["subscription"] = LP.Result(0, f"key {ENVIRON['CF_GLOBAL_API_KEY']}\n", "")
    out = bed.record(bed.request("cli-bench"))
    assert out.status == R.VERIFIED, out.message
    assert out.log_path is not None
    text = out.log_path.read_text(encoding="utf-8")
    assert ENVIRON["CF_GLOBAL_API_KEY"] not in text
    assert ENVIRON["CF_GLOBAL_API_KEY"] not in json.dumps(out.row)


def test_a_secret_value_the_scrub_missed_is_refused_by_refuse_secret_values(
    bed: Bed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BENCH_ROOT_PASSWORD", "hunter2-hunter2-hunter2")
    bed.fake.answers["subscription"] = LP.Result(0, "pw hunter2-hunter2-hunter2\n", "")
    out = bed.record(bed.request("cli-bench"), write=True)
    assert (out.status, out.code) == (R.NOT_VERIFIED, LP.CODE_LEAK)
    assert "BENCH_ROOT_PASSWORD" in out.message
    assert bed.ledger() == []


# ------------------------------------------------------------------ verify


def _append(bed: Bed, row: dict[str, Any]) -> None:
    path = LT.ledger_path(bed.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def test_verify_refuses_a_row_whose_log_digest_mismatches(bed: Bed) -> None:
    out = bed.record(bed.request("cli-bench"), write=True)
    assert LP.verify(bed.root)[0] == 0
    assert out.log_path is not None
    out.log_path.write_text("an edited log\n", encoding="utf-8")
    code, lines = LP.verify(bed.root)
    assert code == 1
    assert any("does not match check.log_sha256" in ln for ln in lines), lines


def test_verify_refuses_a_hand_written_row_with_a_recomputed_id(bed: Bed) -> None:
    out = bed.record(bed.request("cli-bench"))
    assert out.row is not None
    forged = dict(out.row)
    forged["check"] = {**forged["check"], "argv": [["./rdc.sh", "--help"]]}
    forged.pop("id")
    forged["id"] = R.row_id(forged)
    _append(bed, forged)
    code, lines = LP.verify(bed.root)
    assert code == 1
    assert any("registry's argv" in ln for ln in lines), lines


def test_verify_refuses_an_unparsable_line_and_an_empty_plan(bed: Bed) -> None:
    assert LP.verify(bed.root) == (0, ["0 row(s) judged, 0 invalid"])
    code, lines = LP.verify(bed.root, PLAN_REL)
    assert code == 1
    assert lines[-1] == f"no receipt row for {PLAN_REL}"
    path = LT.ledger_path(bed.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{torn\n", encoding="utf-8")
    assert LP.verify(bed.root)[0] == 1


def test_the_command_line_takes_no_retro_flag() -> None:
    with pytest.raises(SystemExit):
        LP._parser().parse_args(["record", "--retro"])
    assert "--retro" not in LP._parser().format_help()
