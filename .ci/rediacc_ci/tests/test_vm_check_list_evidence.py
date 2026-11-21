"""`VmCheck.repo_list`, `VmCheck.record` and the K2 fork listing (`repo_resources._Live.fork`) against fake results, no VMs (vm:check run vmc-11100841-450cef, K2.6): a `repo list` that exits 0 without a list on stdout is a failed list the caller sees, a failed row's evidence is the stderr tail and the envelope's errors, not the CLI's startup lines at the head of stdout plus stderr, and the fork row re-reads the list a bounded number of times, names each re-read, and still fails after the last. Each failing case has a control that stays silent."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.drills import repo_resources as r
from rediacc_ci.drills import vm_check

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Mapping, Sequence

LISTING = json.dumps({"success": True, "data": [{"name": "vmcheck-base", "guid": "g-1"}]})


class FakeHost(vm_check.Host):
    """Answers every command from a queue of results and records each call and each sleep."""

    def __init__(self, results: list[vm_check.Result]) -> None:
        self.results = results
        self.argvs: list[list[str]] = []
        self.calls: list[tuple[list[str], dict[str, str], float | None]] = []
        self.slept: list[float] = []

    def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> vm_check.Result:
        self.argvs.append(list(argv))
        self.calls.append((list(argv), dict(env or {}), timeout))
        return self.results.pop(0)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class NoAccount:
    """The gateway these tests never reach."""

    def gateway_healthy(self) -> bool:
        raise AssertionError("no gateway here")

    def gateway_state(self) -> dict[str, Any]:
        raise AssertionError("no gateway here")

    def restart(self, log_path: pathlib.Path) -> None:
        raise AssertionError("no gateway to restart (log %s)" % log_path)

    def detach(self) -> None:
        raise AssertionError("no gateway here")

    def mint(self, password: str) -> str:
        raise AssertionError("no gateway to mint on (%d-char password)" % len(password))

    def subscription_note(self) -> str:
        raise AssertionError("no gateway here")

    def server_url(self, host: str) -> str:
        raise AssertionError("no gateway on %s" % host)


def make_ctx(tmp_path: pathlib.Path, results: list[vm_check.Result]) -> vm_check.VmCheck:
    """A VmCheck on machine vm11 whose every `./rdc.sh` call answers from `results`, in order."""
    ctx = vm_check.VmCheck(
        tmp_path,
        vm_check.Options(machine="vm11"),
        FakeHost(results),
        NoAccount(),
        tmp_path,
        vm_check.Lock(tmp_path / "vm-check.lock"),
        out=io.StringIO(),
        environ={},
    )
    ctx.run_id = "vmc-11100841-450cef"
    ctx.tags = ("vmc-11100841-450cef-a", "vmc-11100841-450cef-b")
    return ctx


def test_a_readable_list_passes_through(tmp_path: pathlib.Path) -> None:
    """CONTROL: an envelope with a data array, and a bare array, keep rc 0 and their entries."""
    res, entries = make_ctx(tmp_path, [vm_check.Result(0, LISTING, "", 6000)]).repo_list()
    assert res.rc == 0
    assert [e["name"] for e in entries] == ["vmcheck-base"]
    res, entries = make_ctx(tmp_path, [vm_check.Result(0, "[]", "", 6000)]).repo_list()
    assert (res.rc, entries) == (0, [])


@pytest.mark.parametrize(
    ("out", "why"),
    [
        ("", "stdout is empty"),
        ("   \n", "stdout is empty"),
        ("Listing repositories...\n", "stdout is not JSON"),
        (
            json.dumps({"success": True, "data": {"ticket": "t-1"}}),
            "stdout JSON carries no data array",
        ),
    ],
)
def test_a_list_without_a_list_on_stdout_fails(tmp_path: pathlib.Path, out: str, why: str) -> None:
    ctx = make_ctx(tmp_path, [vm_check.Result(0, out, "→ Listing repositories", 28343)])
    res, entries = ctx.repo_list()
    assert entries == []
    assert res.rc == vm_check.LIST_UNREADABLE_RC
    assert res.ms == 28343
    assert res.err.splitlines()[-1] == "repo list exited 0 but its %s" % why
    # Both evidence readers name the reason.
    assert why in vm_check.rdc_failure(res)
    assert why in vm_check.remote_evidence(res)


def test_a_failed_list_keeps_its_own_rc(tmp_path: pathlib.Path) -> None:
    """CONTROL: a list that exited non-zero is returned as the CLI gave it."""
    failed = vm_check.Result(1, "", "SSH connection error: EHOSTUNREACH", 900)
    res, entries = make_ctx(tmp_path, [failed]).repo_list()
    assert (res, entries) == (failed, [])


def test_list_problem() -> None:
    assert vm_check.list_problem(LISTING) == ""
    assert vm_check.list_problem("[]") == ""
    assert vm_check.list_problem("") == "stdout is empty"
    assert vm_check.list_problem("{") == "stdout is not JSON"
    assert vm_check.list_problem('{"success": false}') == "stdout JSON carries no data array"


STARTUP = "\n".join("→ startup line %d %s" % (i, "x" * 40) for i in range(12))


def test_a_failed_row_keeps_the_tail(tmp_path: pathlib.Path) -> None:
    ctx = make_ctx(tmp_path, [])
    res = vm_check.Result(1, "progress " * 40, STARTUP + "\nfatal: the decisive cause", 28343)
    ctx.check("K2", "a failing row", False, res)
    row = ctx.steps[-1]
    assert row["verdict"] == "FAIL"
    assert "fatal: the decisive cause" in row["evidence"], row
    assert row["evidence"].startswith("rc=1 stderr:"), row


def test_a_failed_row_names_the_envelope_errors(tmp_path: pathlib.Path) -> None:
    """Stderr holds only CLI startup lines, and the envelope's errors sit behind a long metrics block: the errors still reach the clipped evidence."""
    envelope = json.dumps(
        {
            "success": False,
            "metrics": {"phase_%d_ms" % i: 1000 + i for i in range(30)},
            "errors": [{"code": "E", "message": "repository is locked"}],
        }
    )
    ctx = make_ctx(tmp_path, [])
    ctx.check("K2", "a failing row", False, vm_check.Result(1, envelope, STARTUP))
    assert "repository is locked" in ctx.steps[-1]["evidence"]


def test_explicit_evidence_and_a_passing_row_are_unchanged(tmp_path: pathlib.Path) -> None:
    """CONTROL: explicit evidence wins, and a passing row records none."""
    ctx = make_ctx(tmp_path, [])
    ctx.check("K2", "named", False, vm_check.Result(1, "", "fatal: cause"), "what the step said")
    assert ctx.steps[-1]["evidence"] == "what the step said"
    ctx.check("K2", "passed", True, vm_check.Result(0, "out", "err"))
    assert ctx.steps[-1]["evidence"] == ""


# --------------------------------------------------------------------------- K2 fork listing

FORK_GUID = "0f0e0d0c-1111-2222-3333-444455556666"


def fork_live(tmp_path: pathlib.Path, lists: list[vm_check.Result]) -> tuple[r._Live, FakeHost]:
    """A K2 `_Live` whose `repo fork` call passes and whose repo lists answer `lists` in turn."""
    ctx = make_ctx(tmp_path, [])
    host = ctx.host
    assert isinstance(host, FakeHost)
    host.results.extend([vm_check.Result(0, "", "", 9000), *lists])
    return r._Live(ctx, r.K2_ID), host


def fork_listing(ref: str, nid: object) -> vm_check.Result:
    """A readable list holding the grand and `ref`, whose network id is `nid` (None: no networkId key, the omitempty shape)."""
    entry: dict[str, object] = {"name": ref, "guid": FORK_GUID}
    if nid is not None:
        entry["networkId"] = nid
    data = [{"name": "vmcheck-base", "guid": "g-1", "networkId": 2816}, entry]
    return vm_check.Result(0, json.dumps({"success": True, "data": data}), "", 6000)


def lists_for(tmp_path: pathlib.Path, nids: list[object]) -> tuple[r._Live, FakeHost]:
    live, host = fork_live(tmp_path, [])
    ref = live.ctx.ref(live.tag_cf)
    host.results.extend(fork_listing(ref, n) for n in nids)
    return live, host


def test_the_fork_row_names_its_list_on_the_first_read(tmp_path: pathlib.Path) -> None:
    """CONTROL: the entry is there on the first read: one list, no sleep, the row's desc as before."""
    live, host = lists_for(tmp_path, [3200])
    assert live.fork(live.tag_cf, live.ctx.ref(live.tag_c))
    row = live.ctx.steps[-1]
    assert row["desc"].endswith("listed with a guid and network id"), row
    assert row["evidence"].startswith("reads=1 list rc=0 ms=6000 parsed=yes entries=2 listed"), row
    assert "guid=%s networkId=3200" % FORK_GUID in row["evidence"], row
    assert row["log"].endswith("K2-fork-%s-list-1.log" % live.tag_cf), row
    assert (tmp_path / row["log"]).read_text().startswith("$ repo list -m vm11 -o json\nrc=0")
    assert host.slept == []
    assert live.nid[live.tag_cf] == 3200


def test_the_fork_row_rereads_a_list_without_its_network_id(tmp_path: pathlib.Path) -> None:
    live, host = lists_for(tmp_path, [None, 3200])
    assert live.fork(live.tag_cf, live.ctx.ref(live.tag_c))
    row = live.ctx.steps[-1]
    assert row["verdict"] == "ok"
    assert row["desc"].endswith("(listed after 2 reads)"), row
    assert row["evidence"].startswith("reads=2 "), row
    assert host.slept == [r.FORK_REREAD_S]
    out = live.ctx.out.getvalue()
    assert "list read 1 (rc=0, 6000 ms) has no guid and network id for it" in out, out


def test_the_fork_row_still_fails_after_the_last_read(tmp_path: pathlib.Path) -> None:
    live, host = lists_for(tmp_path, [None, 0, None, None, 3200])
    assert not live.fork(live.tag_cf, live.ctx.ref(live.tag_c))
    row = live.ctx.steps[-1]
    assert row["verdict"] == "FAIL"
    assert row["desc"].endswith("(not listed after 4 reads)"), row
    assert row["evidence"].startswith("reads=4 list rc=0 ms=6000 parsed=yes entries=2 listed"), row
    assert "guid=%s networkId=<none>" % FORK_GUID in row["evidence"], row
    assert len(host.slept) == r.FORK_LIST_READS - 1
    # The fifth list was never asked for.
    assert len(host.results) == 1
    assert live.tag_cf not in live.nid


def test_the_fork_row_names_an_unreadable_list(tmp_path: pathlib.Path) -> None:
    empty = vm_check.Result(0, "", "→ Starting CLI", 28343)
    live, _host = fork_live(tmp_path, [empty] * r.FORK_LIST_READS)
    assert not live.fork(live.tag_cf, live.ctx.ref(live.tag_c))
    evidence = live.ctx.steps[-1]["evidence"]
    assert evidence.startswith(
        "reads=4 list rc=%d ms=28343 parsed=no entries=0 absent guid=<none> networkId=<none>"
        % vm_check.LIST_UNREADABLE_RC
    ), evidence
    assert "repo list exited 0 but its stdout is empty" in evidence, evidence


def test_fork_ids() -> None:
    entry = {"name": "p:t", "guid": "g"}
    assert r.fork_ids([{**entry, "networkId": 3200}], "p:t") == (True, "g", 3200)
    assert r.fork_ids([{**entry, "network_id": "3200"}], "p:t") == (True, "g", 3200)
    # Zero is the omitted id of a fork whose first up has not persisted one.
    assert r.fork_ids([{**entry, "networkId": 0}], "p:t") == (True, "g", None)
    assert r.fork_ids([{**entry, "networkId": "0"}], "p:t") == (True, "g", None)
    assert r.fork_ids([entry], "p:t") == (True, "g", None)
    assert r.fork_ids([entry], "p:u") == (False, "", None)


def test_fork_reads_note() -> None:
    assert r.fork_reads_note(True, 1) == ""
    assert r.fork_reads_note(False, 1) == ""
    assert r.fork_reads_note(True, 3) == " (listed after 3 reads)"
    assert r.fork_reads_note(False, 4) == " (not listed after 4 reads)"
