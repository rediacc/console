"""`rediacc_ci.drills.vm_check_winclient`: Tier B of vm:check (PLAN-windows-lane D14), driven through the fake fleet of test_drills_vm_check with a fake Windows client beside it, so no case reaches a VM.

`WinWorld` answers every ssh and scp the seam sends to the client: the probe, the run directory's creation and removal, each uploaded call script (whose `& <program> <args>` line it parses and answers as the Windows CLI would) and the sync fixture's round trip. The controls the box names: an unreachable client is NOT_VERIFIED, a failing `WC-` row is FAILED, and without the flag the Linux argv is unchanged.
"""

from __future__ import annotations

import json
import pathlib
import re
import secrets
import shutil
from typing import Any

import pytest

from rediacc_ci.drills import vm_check
from rediacc_ci.drills import vm_check_winclient as wc
from rediacc_ci.proof import vm_tier as receipt_mod
from rediacc_ci.tests.test_drills_vm_check import TOKEN, World, run_check

WIN = "192.168.111.31"
WIN_USER = wc.DEFAULT_USER
ALIAS = "rediacc-win-alias"
RENET_PATH = "/repo/private/renet/bin/renet"
# One `'literal'` (with `''` inside) or one `"$run\<rel>"` argument of a call script's invocation line.
SCRIPT_ARG = re.compile(r"'((?:[^']|'')*)'|\"\$run\\([^\"]*)\"")


class WinWorld(World):
    """The fake fleet plus a fake Windows client at WIN. Calls to the client stay out of `calls`, so the Linux argv of a Tier B run compares one to one with a plain run's."""

    def __init__(self, root: pathlib.Path, **over: Any) -> None:
        self.win_reachable = over.pop("win_reachable", True)
        # Answers by the routed call's first two arguments, e.g. ("doctor", "--output"): (rc, stdout, stderr).
        self.win_answers: dict[tuple[str, ...], tuple[int, str, str]] = dict(
            over.pop("win_answers", {})
        )
        self.win_corrupt = over.pop("win_corrupt", False)
        self.win_remove_rc = over.pop("win_remove_rc", 0)
        super().__init__(root, **over)
        self.win_home = root.parent / "win-home"
        self.win_home.mkdir(exist_ok=True)
        self.win_argvs: list[list[str]] = []
        self.win_calls: list[list[str]] = []
        self.win_programs: list[list[str]] = []
        self.win_scripts: list[str] = []
        # (target rel, source basename, text when the source is a small file) of each upload.
        self.win_uploads: list[tuple[str, str, str]] = []
        self.win_synced: dict[str, pathlib.Path] = {}
        self.win_removed = False

    def run(self, argv, env=None, timeout=None) -> vm_check.Result:
        argv = list(argv)
        if any(a.startswith("%s@%s" % (WIN_USER, WIN)) for a in argv):
            self.win_argvs.append(argv)
            return self._win(argv)
        return super().run(argv, env, timeout)

    # ------------------------------------------------------------------ the client

    def _win_path(self, rel: str) -> pathlib.Path:
        return self.win_home / rel.replace("\\", "/")

    def _win(self, argv: list[str]) -> vm_check.Result:
        if not self.win_reachable:
            return vm_check.Result(
                255, "", "ssh: connect to host %s port 22: No route to host\n" % WIN
            )
        if argv[0] == "scp":
            return self._scp(argv)
        command = argv[-1]
        if command == wc.PROBE:
            return vm_check.Result(0, "rediacc31\r\n")
        if "New-Item" in command:
            path = re.search(r"-Path '([^']+)'", command)
            assert path, command
            self._win_path(path.group(1)).mkdir(parents=True, exist_ok=True)
            return vm_check.Result(0)
        if "Remove-Item" in command:
            self.win_removed = self.win_remove_rc == 0
            return vm_check.Result(
                self.win_remove_rc, "", "access denied\n" * bool(self.win_remove_rc)
            )
        if " -File " in command:
            return self._script(self._win_path(command.split(" -File ", 1)[1]))
        return vm_check.Result(1, "", "unexpected client command %r" % command)

    @staticmethod
    def _operands(argv: list[str]) -> list[str]:
        out: list[str] = []
        skip = False
        for arg in argv[1:]:
            if skip:
                skip = False
            elif arg in ("-F", "-i", "-o"):
                skip = True
            elif not arg.startswith("-"):
                out.append(arg)
        return out

    def _scp(self, argv: list[str]) -> vm_check.Result:
        operands = self._operands(argv)
        *sources, target = operands
        if sources and sources[0].startswith("%s@" % WIN_USER):
            src = self._win_path(sources[0].split(":", 1)[1])
            shutil.copytree(src, target)
            return vm_check.Result(0)
        rel = target.split(":", 1)[1]
        dest = self._win_path(rel)
        for source in map(pathlib.Path, sources):
            if source.is_dir():
                shutil.copytree(source, dest)
                self.win_uploads.append((rel, source.name, ""))
                continue
            into = dest / source.name if rel.endswith("/") else dest
            into.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, into)
            text = source.read_text(errors="replace") if source.stat().st_size < 65536 else ""
            self.win_uploads.append((rel, source.name, text))
        return vm_check.Result(0)

    def _script(self, path: pathlib.Path) -> vm_check.Result:
        text = path.read_text()
        self.win_scripts.append(text)
        line = next(ln for ln in text.splitlines() if ln.startswith("& "))
        run = path.parent
        tokens = [
            str(run / m.group(2).replace("\\", "/"))
            if m.group(2) is not None
            else m.group(1).replace("''", "'")
            for m in SCRIPT_ARG.finditer(line)
        ]
        skip = 2 if tokens[0] == "node" else 1
        self.win_programs.append(tokens[:skip])
        args = tokens[skip:]
        self.win_calls.append(args)
        answer = self.win_answers.get(tuple(args[:2]))
        if answer is not None:
            return vm_check.Result(*answer)
        if args[:3] == ["repo", "sync", "upload"]:
            remote = args[args.index("--remote") + 1]
            kept = self.win_home.parent / "win-synced" / remote
            shutil.copytree(args[args.index("--local") + 1], kept)
            self.win_synced[remote] = kept
        elif args[:3] == ["repo", "sync", "download"]:
            local = pathlib.Path(args[args.index("--local") + 1])
            shutil.copytree(self.win_synced[args[args.index("--remote") + 1]], local)
            if self.win_corrupt:
                big = local / "big.bin"
                data = bytearray(big.read_bytes())
                data[0] ^= 0xFF
                big.write_bytes(bytes(data))
        elif args[:2] == ["vscode", "connect"]:
            return vm_check.Result(0, "%s%s/mnt/rediacc/mounts/x\n" % (vm_check.URI_PREFIX, ALIAS))
        elif args[:2] == ["term", "connect"]:
            return vm_check.Result(0, args[args.index("-c") + 1].removeprefix("echo ") + "\n")
        elif args[:1] == ["doctor"]:
            doc = {
                "Environment": [{"name": "node", "status": "ok"}],
                "Tools": [{"name": "rsync", "status": "warning"}],
            }
            return vm_check.Result(0, json.dumps(doc))
        return vm_check.Result(0)


def win_world(tmp_path: pathlib.Path, **over: Any) -> WinWorld:
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    bundle = root / wc.BUNDLE
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text("// the CLI bundle\n")
    config = tmp_path / "home" / ".config" / "rediacc" / "dev.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"id": "c0ffee", "renetPath": RENET_PATH, "machines": {}}))
    return WinWorld(root, **over)


def tier_b(tmp_path: pathlib.Path, world: WinWorld, *extra: str) -> tuple[int, str, dict[str, Any]]:
    return run_check(tmp_path, world, "--windows-client", WIN, *extra)


def wc_rows(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in receipt["steps"] if r["id"].startswith(wc.PREFIX)]


# --------------------------------------------------------------------------- the three controls


def test_an_unreachable_client_is_not_verified_before_any_fleet_work(
    tmp_path: pathlib.Path,
) -> None:
    world = win_world(tmp_path, win_reachable=False)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["status"] == receipt_mod.NOT_VERIFIED
    assert receipt["reason"]["class"] == wc.UNREACHABLE
    assert "No route to host" in receipt["reason"]["detail"]
    assert "%s rc=255" % wc.PROBE in receipt["reason"]["detail"]
    assert len(world.win_argvs) == 1, "only the probe reaches for the client"
    assert world.rdc_calls() == [], "the preflight comes before any ./rdc.sh call"
    assert not wc_rows(receipt)
    assert not world.win_removed


def test_a_failing_wc_row_fails_the_run_and_still_tears_down(tmp_path: pathlib.Path) -> None:
    doctor = json.dumps({"Tools": [{"name": "renet", "status": "error"}]})
    world = win_world(tmp_path, win_answers={("doctor", "--output"): (2, doctor, "")})
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    assert receipt["status"] == receipt_mod.FAILED
    assert receipt["reason"]["class"] == "step-failed"
    assert wc.ROW_DOCTOR in receipt["reason"]["detail"]
    (row,) = [r for r in receipt["steps"] if r["id"] == wc.ROW_DOCTOR]
    assert row["verdict"] == "FAIL"
    assert "Tools/renet" in row["evidence"]
    assert world.win_removed
    assert world.forks_left() == []


def test_without_the_flag_the_linux_argv_is_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(secrets, "token_hex", lambda n=16: "ab" * n)

    def linux_argv(world: World) -> list[tuple[str, ...]]:
        # Sorted: the A1 suites run on a worker thread beside P0-P3, so their place in `calls` varies.
        root = str(world.root)
        return sorted(
            tuple(re.sub(r"rediacc-drill-vmcheck-[^/]+", "W", a.replace(root, "R")) for a in call)
            for call in world.calls
        )

    # Its own root, so the second run meets none of the first one's remote store.
    (tmp_path / "plain").mkdir()
    plain = World(tmp_path / "plain")
    rc, out, receipt = run_check(tmp_path, plain)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert not wc_rows(receipt)
    assert not any(call[0] == "scp" for call in plain.calls)
    assert not any("%s@" % WIN_USER in " ".join(call) for call in plain.calls)
    world = win_world(tmp_path)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert linux_argv(world) == linux_argv(plain)


def test_no_flag_parses_to_no_client() -> None:
    opts = vm_check.parse_args([], {})
    assert (opts.windows_client, opts.rdc_exe) == ("", "")


# --------------------------------------------------------------------------- the routed rows


def test_a_clean_tier_b_run_is_verified_with_every_wc_row(tmp_path: pathlib.Path) -> None:
    world = win_world(tmp_path)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    rows = wc_rows(receipt)
    assert len(rows) >= 5
    assert all(r["verdict"] == "ok" for r in rows), rows
    assert {r["id"] for r in rows} == set(wc.ROWS)
    verbs = [tuple(c[:2]) for c in world.win_calls]
    assert verbs[0] == ("machine", "scan-keys")
    assert ("repo", "sync") in verbs
    assert ("vscode", "connect") in verbs
    assert ("term", "connect") in verbs
    assert ("doctor", "--output") in verbs
    assert world.win_calls[-1] == ["vscode", "cleanup", "-c", ALIAS]
    assert all(p[0] == "node" and p[1].endswith(wc.BUNDLE.name) for p in world.win_programs)
    assert world.win_removed
    # WC-P3 follows the Linux P3, and the other rows follow V1.7.
    ids = [r["id"] for r in receipt["steps"]]
    assert ids.index(wc.ROW_P3) == ids.index("P3") + 1
    assert ids.index(wc.ROW_SYNC) > max(i for i, s in enumerate(ids) if s == "V1.7")


def test_the_minted_token_reaches_the_client_only_in_its_token_file(
    tmp_path: pathlib.Path,
) -> None:
    world = win_world(tmp_path)
    rc, out, _receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert not any(TOKEN in " ".join(argv) for argv in world.win_argvs)
    assert not any(TOKEN in script for script in world.win_scripts)
    assert [text for _rel, name, text in world.win_uploads if name == wc.CARRIER_FILE] == [TOKEN]
    assert all("REDIACC_CONFIG = 'dev'" in s for s in world.win_scripts)
    assert all("REDIACC_NO_PROVISION = '1'" in s for s in world.win_scripts)
    configs = [json.loads(text) for rel, name, text in world.win_uploads if name == "dev.json"]
    assert configs
    assert all("renetPath" not in c for c in configs)
    assert all(
        rel.endswith("/appdata/rediacc/")
        for rel, name, _t in world.win_uploads
        if name == "dev.json"
    )


def test_a_corrupt_round_trip_fails_wc_v15(tmp_path: pathlib.Path) -> None:
    world = win_world(tmp_path, win_corrupt=True)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    bad = [r for r in wc_rows(receipt) if r["verdict"] == "FAIL"]
    assert [r["id"] for r in bad] == [wc.ROW_SYNC]
    assert "big.bin" in bad[0]["evidence"]


def test_a_failing_scan_keys_fails_wc_p3(tmp_path: pathlib.Path) -> None:
    world = win_world(
        tmp_path, win_answers={("machine", "scan-keys"): (1, "", "no host keys returned\n")}
    )
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_FAILED, out
    (row,) = [r for r in receipt["steps"] if r["id"] == wc.ROW_P3]
    assert row["verdict"] == "FAIL"
    assert "no host keys returned" in row["evidence"]


def test_an_agent_refusal_on_the_client_is_agent_policy_refused(tmp_path: pathlib.Path) -> None:
    refusal = (1, "", "Agents cannot run this command\n")
    world = win_world(tmp_path, win_answers={("term", "connect"): refusal})
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "agent-policy-refused"
    assert world.win_removed


def test_rdc_exe_is_staged_and_run_instead_of_the_bundle(tmp_path: pathlib.Path) -> None:
    exe = tmp_path / "rdc-win-x64.exe"
    exe.write_bytes(b"MZ")
    world = win_world(tmp_path)
    rc, out, _receipt = tier_b(tmp_path, world, "--rdc-exe", str(exe))
    assert rc == vm_check.EXIT_VERIFIED, out
    assert any(
        rel.endswith("/" + wc.EXE_NAME) and name == exe.name for rel, name, _t in world.win_uploads
    )
    assert not any(name == wc.BUNDLE.name for _rel, name, _t in world.win_uploads)
    assert all(len(p) == 1 and p[0].endswith(wc.EXE_NAME) for p in world.win_programs)


def test_an_unreadable_config_is_windows_client_stage(tmp_path: pathlib.Path) -> None:
    world = win_world(tmp_path)
    (tmp_path / "home" / ".config" / "rediacc" / "dev.json").unlink()
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == wc.STAGE
    assert world.win_removed


def test_a_run_directory_left_on_the_client_is_a_teardown_leftover(tmp_path: pathlib.Path) -> None:
    world = win_world(tmp_path, win_remove_rc=1)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert receipt["reason"]["class"] == "teardown-failed"
    assert "Windows client run directory" in receipt["reason"]["detail"]


def test_tier_b_makes_the_renet_phase_required(tmp_path: pathlib.Path) -> None:
    world = win_world(tmp_path)
    rc, out, receipt = tier_b(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["phases"]["renet"]["required"] is True


def test_complete_refuses_a_run_missing_a_wc_row() -> None:
    ctx: Any = type("Ctx", (), {})()
    ctx.failures, ctx.reason = [], None
    ctx.steps = [{"id": r} for r in wc.ROWS if r != wc.ROW_TERM]
    client = wc.WindowsClient.__new__(wc.WindowsClient)
    client.ctx = ctx
    with pytest.raises(vm_check.NotVerifiedError) as caught:
        client.complete()
    assert caught.value.cls == wc.NOT_RUN
    assert wc.ROW_TERM in caught.value.detail
    ctx.failures = ["V1.1: planted"]
    client.complete()


# --------------------------------------------------------------------------- arguments


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--rdc-exe", "/bin/sh"], "needs --windows-client"),
        (["--windows-client", "win11.local"], "literal IPv4"),
        (["--windows-client", "fe80::1"], "literal IPv4"),
        (["--windows-client", WIN, "--changed"], "--changed"),
        (["--windows-client", WIN, "--only", "V1.3"], "--only"),
        (["--windows-client", WIN, "--rdc-exe", "/nonexistent/rdc.exe"], "names no file"),
    ],
)
def test_a_bad_tier_b_argument_is_a_usage_error(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        vm_check.parse_args(argv, {})
    assert message in capsys.readouterr().err


def test_the_client_address_and_exe_parse(tmp_path: pathlib.Path) -> None:
    exe = tmp_path / "rdc.exe"
    exe.write_bytes(b"MZ")
    opts = vm_check.parse_args(["--windows-client", WIN, "--rdc-exe", str(exe)], {})
    assert (opts.windows_client, opts.rdc_exe) == (WIN, str(exe))


# --------------------------------------------------------------------------- the script


def test_the_script_quotes_every_argument_and_reads_the_token_from_its_file() -> None:
    script = wc.call_script(
        ["node", wc.RemotePath("cli-bundle.cjs")],
        ["term", "connect", "a:b", "-c", "echo it's"],
        {"CLAUDECODE": "1"},
        "dev",
    )
    assert "& 'node' \"$run\\cli-bundle.cjs\" 'term' 'connect' 'a:b' '-c' 'echo it''s'" in script
    assert "$env:CLAUDECODE = '1'" in script
    assert "Get-Content -Raw -LiteralPath $tokenFile" in script
    assert script.endswith("exit $LASTEXITCODE\r\n")


@pytest.mark.parametrize("arg", ['say "hi"', wc.RemotePath("x$y"), wc.RemotePath("a`b")])
def test_an_argument_powershell_would_mangle_or_expand_is_refused(arg: str) -> None:
    with pytest.raises(ValueError, match="PowerShell"):
        wc.ps_arg(arg)


def test_doctor_errors_reads_the_json_envelope() -> None:
    assert wc.doctor_errors('{"A": [{"name": "x", "status": "ok"}]}') == (True, [])
    assert wc.doctor_errors('noise {"A": [{"name": "x", "status": "error"}]}') == (True, ["A/x"])
    assert wc.doctor_errors("not json") == (False, [])
