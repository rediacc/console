"""`rediacc_ci.core.run_verbs`: the verbs `./run.sh` served from the deleted `.ci/legacy/run-legacy.sh`.

WHAT IS PINNED HERE, AND WHY IT IS NOT A DIFFERENTIAL. The bash dispatcher is gone, so there is no twin left to run. The parts that were right are pinned as GOLDEN TEXT lifted from the file before it was deleted (every `Usage:` line, the exit code of each refusal); the parts that were wrong are the five deliberate deltas named in the module docstring, each with a test that FAILS ON THE BASH BEHAVIOUR:

  D1  quality/fix/clean act on the repository root, not the caller's directory.
  D2  `quality deps` runs a gate that exists (the bash called a missing script, exit 127).
  D3  `fix shell` formats the files the gate checks (not `.ci/cache`, but `.claude` and `.github`).
  D4  `help` lists `setup` once.
  D5  `quality submodules` runs the live Python port.

The dispatch tables are exercised with the real arms replaced by recorders, so a case proves WHICH arm a spelling reaches without starting docker, npm or a devbox.
"""

import os
import pathlib

import pytest

from rediacc_ci import __main__ as entry
from rediacc_ci import paths
from rediacc_ci.core import run_verbs as rv
from rediacc_ci.quality import submodule_branches

# The `Usage:` lines of the deleted dispatcher, verbatim, one per verb that printed one.
GOLDEN_USAGE = {
    "service": "Usage: ./run.sh service [start|stop|status|logs]",
    "account": "Usage: ./run.sh account [dev|db|test|stop|reset|seed-demo|totp]",
    "devbox": (
        "Usage: ./run.sh devbox "
        "[up|status|url [term|account|db]|stop|proxy|remove|shell|exec|doctor|logs]"
    ),
    "quality": (
        "Usage: ./run.sh quality "
        "[lint|format|types|submodules|deps|actions|suppressions|dead-bash|audit|shell|all]"
    ),
    "fix": "Usage: ./run.sh fix [format|lint|shell|all]",
}
GOLDEN_DRILL_USAGE = "Usage: ./run.sh drill [universe|transfer|license|backup] [--selftest]"


def noting(log: list, item, result=0):
    """Record `item` in `log` and answer `result`: a stub that remembers its call."""
    log.append(item)
    return result


@pytest.fixture
def root(tmp_path, monkeypatch) -> pathlib.Path:
    """A scratch repository root, installed as `$REDIACC_CI_ROOT` so `paths.repo_root()` answers it."""
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    return tmp_path


# --------------------------------------------------------------------------- usage and unknown-subcommand refusals ---------------------------------------------------------------------------


def test_the_generated_usage_lines_are_the_ones_the_bash_printed() -> None:
    assert rv.usage_line("service", rv.SERVICE_ARMS) == GOLDEN_USAGE["service"]
    assert rv.usage_line("account", rv.ACCOUNT_ARMS) == GOLDEN_USAGE["account"]
    assert rv.usage_line("devbox", rv.DEVBOX_ARMS, rv.DEVBOX_NOTES) == GOLDEN_USAGE["devbox"]
    assert rv.usage_line("quality", rv.QUALITY_ARMS) == GOLDEN_USAGE["quality"]
    assert rv.usage_line("fix", rv.FIX_ARMS) == GOLDEN_USAGE["fix"]
    assert rv.usage_line("drill", rv.DRILL_ARMS) + " [--selftest]" == GOLDEN_DRILL_USAGE


@pytest.mark.parametrize("verb", ["service", "account", "quality", "fix"])
def test_an_unknown_subcommand_is_error_blank_usage_and_exit_1(verb, capsys) -> None:
    table = {
        "service": rv.SERVICE_ARMS,
        "account": rv.ACCOUNT_ARMS,
        "quality": rv.QUALITY_ARMS,
        "fix": rv.FIX_ARMS,
    }[verb]
    rc = rv.dispatch(verb, table, ["definitely-not-a-subcommand"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == "\n%s\n" % GOLDEN_USAGE[verb]
    assert "Unknown %s command: definitely-not-a-subcommand" % verb in captured.err


def test_no_subcommand_is_unknown_for_service_and_account_but_a_default_for_quality_and_fix(
    capsys,
) -> None:
    """The bash had `all | "")` arms for quality and fix and no empty arm for service or account."""
    assert rv.dispatch("service", rv.SERVICE_ARMS, []) == 1
    assert rv.dispatch("account", rv.ACCOUNT_ARMS, []) == 1
    capsys.readouterr()
    seen: list[list[str]] = []
    arms = {"all": lambda rest: noting(seen, rest)}
    assert rv.dispatch("quality", arms, [], default="all") == 0
    assert seen == [[]]


def test_the_drill_refusal_names_the_drill_and_keeps_selftest_in_the_usage(capsys) -> None:
    assert rv.drill_main(["nope"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "\n%s\n" % GOLDEN_DRILL_USAGE
    assert "Unknown drill: nope" in captured.err


# --------------------------------------------------------------------------- which arm a spelling reaches ---------------------------------------------------------------------------


def test_account_spellings_reach_the_ports_that_serve_them(monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(rv.account_lifecycle, "main", lambda argv: noting(calls, ("lc", argv)))
    monkeypatch.setattr(rv.account, "db", lambda argv: noting(calls, ("db", argv)))
    monkeypatch.setattr(rv.account, "stop", lambda: noting(calls, ("stop",)))
    monkeypatch.setattr(rv.account, "totp", lambda email: noting(calls, ("totp", email)))
    for argv in (
        ["dev"],
        ["db", "--port", "9"],
        ["test"],
        ["test", "e2e", "--grep", "x"],
        ["stop"],
        ["reset"],
        ["seed-demo", "a@b.c"],
        ["totp"],
        ["totp", "x@y.z"],
    ):
        assert rv.account_main(argv) == 0
    assert calls == [
        ("lc", ["dev"]),
        ("db", ["--port", "9"]),
        ("lc", ["test"]),
        ("lc", ["test", "e2e", "--grep", "x"]),
        ("stop",),
        ("lc", ["reset"]),
        ("lc", ["seed-demo", "a@b.c"]),
        ("totp", None),
        ("totp", "x@y.z"),
    ]


def test_service_spellings_reach_service_main(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(rv.service, "main", lambda argv: noting(calls, argv))
    for argv in (["start", "9090", "--no-build"], ["stop"], ["status"], ["logs", "web"]):
        assert rv.service_main(argv) == 0
    assert calls == [["start", "9090", "--no-build"], ["stop"], ["status"], ["logs", "web"]]


class FakeBox:
    """The slice of `Devbox` the verb touches: `invoke` and `log`."""

    def __init__(self) -> None:
        self.invoked: list[tuple] = []
        self.logged: list[tuple] = []
        self.answers: dict[str, int] = {}

    def invoke(self, name, argv=()):
        self.invoked.append((name, list(argv)))
        return self.answers.get(name, 0)

    def log(self, level, message):
        self.logged.append((level, message))


@pytest.fixture
def box(monkeypatch) -> FakeBox:
    fake = FakeBox()
    monkeypatch.setattr(rv.devbox, "Devbox", lambda: fake)
    monkeypatch.setattr(rv, "_with_docker_group", lambda _args: None)
    return fake


def test_devbox_spellings_reach_the_function_the_bash_called(box) -> None:
    for argv in (
        [],
        ["status"],
        ["up"],
        ["up", "--no-rehost"],
        ["url"],
        ["url", "term"],
        ["stop"],
        ["remove"],
        ["shell"],
        ["exec", "--", "echo", "hi"],
        ["exec", "echo", "hi"],
        ["doctor"],
        ["logs"],
        ["logs", "--tail=5"],
        ["proxy", "up"],
        ["proxy", "stop"],
    ):
        assert rv.devbox_main(argv) == 0
    assert box.invoked == [
        ("devbox_status", []),
        ("devbox_status", []),
        ("devbox_up", ["false", ""]),
        ("devbox_up", ["false", "--no-rehost"]),
        ("devbox_url", [""]),
        ("devbox_url", ["term"]),
        ("devbox_stop", []),
        ("devbox_remove", []),
        ("devbox_shell", []),
        ("devbox_exec", ["echo", "hi"]),
        ("devbox_exec", ["echo", "hi"]),
        ("devbox_doctor", []),
        ("devbox_logs", []),
        ("devbox_logs", ["--tail=5"]),
        ("devbox_proxy_ensure", []),
        ("devbox_proxy_stop", []),
    ]


def test_devbox_exec_with_no_command_and_an_unknown_subcommand_refuse_with_1(box) -> None:
    assert rv.devbox_main(["exec", "--"]) == 1
    assert box.logged[-1] == (
        "error",
        "devbox exec needs a command: ./run.sh devbox exec -- <cmd>",
    )
    assert rv.devbox_main(["nope"]) == 1
    assert box.logged[-2:] == [
        ("error", "Unknown devbox command: nope"),
        ("info", GOLDEN_USAGE["devbox"]),
    ]
    assert box.invoked == []


def test_devbox_proxy_status_reports_both_states_and_an_unknown_proxy_command_fails(box) -> None:
    assert rv.devbox_main(["proxy"]) == 0
    assert box.logged[-1] == ("info", "Proxy running on :%d" % rv.devbox.DEVBOX_PROXY_PORT)
    box.answers["devbox_proxy_running"] = 1
    assert rv.devbox_main(["proxy", "status"]) == 1
    assert box.logged[-1] == ("warn", "Proxy is not running")
    assert rv.devbox_main(["proxy", "zz"]) == 1
    assert box.logged[-1] == ("error", "Unknown devbox proxy command: zz")


# --------------------------------------------------------------------------- quality: lane routing and the arms ---------------------------------------------------------------------------


def stub_lane(monkeypatch, route: int):
    monkeypatch.setattr(rv, "_with_docker_group", lambda _args: None)
    ran: list[list[str]] = []
    monkeypatch.setattr(rv.local_common, "gate_lane_should_route", lambda: route)
    monkeypatch.setattr(rv.local_common, "gate_lane_run", lambda args: noting(ran, args, 7))
    return ran


def test_a_routed_quality_run_hands_the_whole_argv_to_the_lane(monkeypatch) -> None:
    ran = stub_lane(monkeypatch, 0)
    assert rv.quality_main(["actions"]) == 7
    assert ran == [["quality", "actions"]]


def test_an_unusable_devbox_refuses_with_2_and_never_runs_on_the_host(monkeypatch) -> None:
    stub_lane(monkeypatch, 2)
    monkeypatch.setattr(rv, "quality_all", lambda: pytest.fail("ran on the host"))
    assert rv.quality_main([]) == 2


def test_the_host_lane_dispatches_every_quality_arm(monkeypatch) -> None:
    stub_lane(monkeypatch, 1)
    reached: list[str] = []
    for name in ("lint", "format", "types", "submodules", "deps", "audit", "shell", "all"):
        monkeypatch.setattr(rv, "quality_" + name, lambda name=name: noting(reached, name))
    monkeypatch.setattr(rv, "quality_ts_gate", lambda name: noting(reached, name))
    # The arms hold lambdas over the module globals, so a rebuilt table sees the stubs.
    arms = {
        "lint": lambda _rest: rv.quality_lint(),
        "format": lambda _rest: rv.quality_format(),
        "types": lambda _rest: rv.quality_types(),
        "submodules": lambda _rest: rv.quality_submodules(),
        "deps": lambda _rest: rv.quality_deps(),
        "audit": lambda _rest: rv.quality_audit(),
        "shell": lambda _rest: rv.quality_shell(),
        "all": lambda _rest: rv.quality_all(),
    }
    monkeypatch.setattr(rv, "QUALITY_ARMS", arms)
    for sub in arms:
        assert rv.quality_main([sub]) == 0
    assert rv.quality_main([]) == 0
    assert reached == [*arms, "all"]


def test_quality_all_is_red_when_the_shell_gates_cannot_run(monkeypatch, capsys) -> None:
    """The vacuous green: a missing pinned shfmt used to be a warning and a success."""
    monkeypatch.setattr(rv, "_node_ok", lambda: True)
    monkeypatch.setattr(rv, "_npm", lambda *_args: 0)
    monkeypatch.setattr(rv, "quality_shell", lambda: pytest.fail("ran the shell gates"))
    verdict = rv.toolchain.CheckResult("shfmt", None, 1, ("toolchain: shfmt is not on PATH",))
    monkeypatch.setattr(rv.toolchain, "check", lambda _tool: verdict)
    assert rv.quality_all() == 1
    err = capsys.readouterr().err
    assert "shell gates cannot run here" in err
    assert "    toolchain: shfmt is not on PATH" in err


def test_quality_all_stops_at_the_first_failing_npm_run(monkeypatch) -> None:
    monkeypatch.setattr(rv, "_node_ok", lambda: True)
    monkeypatch.setattr(rv, "_npm", lambda *_args: 3)
    monkeypatch.setattr(rv.toolchain, "check", lambda _tool: pytest.fail("asked about shfmt"))
    assert rv.quality_all() == 3


# --------------------------------------------------------------------------- D1: the repository root, not the caller's directory ---------------------------------------------------------------------------


def test_d1_npm_runs_in_the_repository_root_whatever_the_callers_directory(
    root, monkeypatch
) -> None:
    """The bash ran `npm run lint` where the caller stood, so `cd packages/cli && ./run.sh quality lint` linted one package. FAILS ON THE BASH BEHAVIOUR."""
    nested = root / "packages" / "cli"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    seen: list[tuple[list[str], str]] = []

    def fake_call(argv, cwd=None):
        seen.append((argv, cwd))
        return 0

    monkeypatch.setattr(rv.subprocess, "call", fake_call)
    monkeypatch.setattr(rv, "_node_ok", lambda: True)
    assert rv.quality_format() == 0
    assert rv.quality_types() == 0
    assert rv.fix_main(["lint"]) == 0
    assert seen == [
        (["npm", "run", "check:format"], str(root)),
        (["npm", "run", "typecheck"], str(root)),
        (["npm", "run", "fix:lint"], str(root)),
    ]


@pytest.mark.usefixtures("root")
def test_d1_quality_lint_runs_both_scripts_and_stops_at_the_first_failure(monkeypatch) -> None:
    calls: list[list[str]] = []
    results = iter([0, 0])
    monkeypatch.setattr(rv, "_node_ok", lambda: True)
    monkeypatch.setattr(
        rv.subprocess, "call", lambda argv, **_kw: noting(calls, argv, next(results))
    )
    assert rv.quality_lint() == 0
    assert calls == [
        ["npm", "run", "lint", "--", "--max-warnings", "0"],
        ["npm", "run", "lint:unused"],
    ]
    calls.clear()
    results = iter([5, 0])
    monkeypatch.setattr(
        rv.subprocess, "call", lambda argv, **_kw: noting(calls, argv, next(results))
    )
    assert rv.quality_lint() == 5
    assert calls == [["npm", "run", "lint", "--", "--max-warnings", "0"]]


def test_d1_clean_removes_the_roots_build_output_and_only_that(root, monkeypatch) -> None:
    """The bash ran `rm -rf dist/ ...` in the caller's directory. FAILS ON THE BASH BEHAVIOUR: from `packages/cli` it removed that directory's `dist/` and left the root's."""
    (root / "dist").mkdir()
    (root / "dist" / "bundle.js").write_text("x")
    (root / "node_modules" / ".vite").mkdir(parents=True)
    (root / "node_modules" / "keep.txt").write_text("x")
    for package in ("cli", "shared"):
        (root / "packages" / package / "dist").mkdir(parents=True)
        (root / "packages" / package / "src").mkdir()
        (root / "packages" / package / "src" / "a.ts").write_text("x")
    nested = root / "packages" / "cli"
    monkeypatch.chdir(nested)
    assert rv.clean_main([]) == 0
    assert not (root / "dist").exists()
    assert not (root / "node_modules" / ".vite").exists()
    assert not (root / "packages" / "cli" / "dist").exists()
    assert not (root / "packages" / "shared" / "dist").exists()
    assert (root / "node_modules" / "keep.txt").exists()
    assert (root / "packages" / "cli" / "src" / "a.ts").exists()
    assert (root / "packages" / "shared" / "src" / "a.ts").exists()


@pytest.mark.usefixtures("root")
def test_clean_with_nothing_to_clean_succeeds() -> None:
    assert rv.clean_main([]) == 0


# --------------------------------------------------------------------------- D2: quality deps runs a gate that exists ---------------------------------------------------------------------------


def test_d2_quality_deps_runs_the_check_deps_gate(monkeypatch) -> None:
    """The bash called `.ci/scripts/quality/check-deps.sh`, which does not exist (exit 127). FAILS ON THE BASH BEHAVIOUR."""
    missing = paths.from_root(".ci", "scripts", "quality", "check-deps.sh")
    assert not missing.exists()
    seen: list[list[str]] = []
    monkeypatch.setattr(rv, "_node_ok", lambda: True)
    monkeypatch.setattr(rv, "_run", lambda argv, **_kw: noting(seen, argv))
    assert rv.quality_deps() == 0
    assert seen == [["npx", "tsx", str(rv.root() / "scripts/gates/check-deps.ts")]]
    assert (rv.root() / "scripts/gates/check-deps.ts").is_file()


@pytest.mark.parametrize("name", sorted(rv.QUALITY_TS_GATES))
def test_every_ts_quality_gate_names_a_script_that_exists(name) -> None:
    script, announcement = rv.QUALITY_TS_GATES[name]
    assert (rv.root() / script).is_file(), script
    assert announcement.endswith("...")


# --------------------------------------------------------------------------- D3: fix shell formats what the gate checks ---------------------------------------------------------------------------


def test_d3_fix_shell_formats_the_gates_files_and_not_the_cache(root, monkeypatch) -> None:
    """The bash ran `find .ci -name '*.sh' -exec shfmt -w`, which rewrote third-party scripts under the gitignored `.ci/cache/`, and skipped `.claude` and `.github`, which `security.shfmt` checks. FAILS ON THE BASH BEHAVIOUR."""
    for relative in (
        ".ci/a.sh",
        ".ci/lib/b.sh",
        ".ci/cache/toolchain/uv-cache/vendored/libyaml.sh",
        ".claude/hooks/c.sh",
        ".github/actions/d.sh",
        "scripts/dev/e.sh",
        "scripts/ops/f.sh",
        "scripts/other/g.sh",
        "run.sh",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/bash\n")
    seen: list[list[str]] = []
    monkeypatch.setattr(rv.toolchain, "acquire", lambda _tool: ("/pinned/shfmt", []))
    monkeypatch.setattr(rv, "_run", lambda argv, **_kw: noting(seen, argv))
    assert rv.fix_shell() == 0
    (argv,) = seen
    assert argv[:5] == ["/pinned/shfmt", "-i", "4", "-ci", "-w"]
    targets = {pathlib.Path(path).relative_to(root).as_posix() for path in argv[5:]}
    assert targets == {
        ".ci/a.sh",
        ".ci/lib/b.sh",
        ".claude/hooks/c.sh",
        ".github/actions/d.sh",
        "scripts/dev/e.sh",
        "scripts/ops/f.sh",
        "run.sh",
    }
    assert "-d" not in argv


def test_fix_shell_refuses_when_the_pinned_shfmt_cannot_be_had(monkeypatch, capsys) -> None:
    """The fixer must use the binary the gate verifies with, or fail: a bare PATH shfmt can format into a state the gate rejects."""
    monkeypatch.setattr(rv.toolchain, "acquire", lambda _tool: (None, ["toolchain: shfmt absent"]))
    monkeypatch.setattr(rv, "_run", lambda _argv, **_kw: pytest.fail("formatted anyway"))
    assert rv.fix_shell() == 1
    err = capsys.readouterr().err
    assert "toolchain: shfmt absent" in err
    assert "shfmt is unusable, so formatting would not match the gate" in err


# --------------------------------------------------------------------------- D4, help ---------------------------------------------------------------------------


def test_d4_help_documents_setup_once_and_every_verb_the_package_serves() -> None:
    text = rv.help_text()
    setup_lines = [line for line in text.splitlines() if line.startswith("  setup ")]
    assert len(setup_lines) == 1
    assert "Interactive setup: npm deps" not in text
    for name in entry.names():
        assert "\n  %s " % name in text or "\n  %s\n" % name in text, name
    for name in ("provision", "www"):
        assert "  %s " % name in text


def test_help_carries_the_pinned_node_major() -> None:
    major = rv.toolchain.node_major()
    assert "Node.js v%s.x" % major in rv.help_text()


def test_help_main_prints_the_text_and_succeeds(capsys) -> None:
    assert rv.help_main([]) == 0
    assert capsys.readouterr().out == rv.help_text()


def test_the_front_door_serves_help_for_no_verb_dash_h_and_double_dash_help(capsys) -> None:
    for argv in ([], ["-h"], ["--help"], ["help"]):
        assert entry.main(argv) == 0
        assert capsys.readouterr().out == rv.help_text()


def test_an_unknown_verb_is_error_blank_help_and_exit_1(capsys) -> None:
    assert entry.main(["definitely-not-a-verb"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: definitely-not-a-verb" in captured.err
    assert captured.out == "\n" + rv.help_text()


# --------------------------------------------------------------------------- D5, submodules ---------------------------------------------------------------------------


def test_d5_quality_submodules_runs_the_python_port(monkeypatch, capsys) -> None:
    monkeypatch.setattr(submodule_branches, "main", lambda _argv: 9)
    assert rv.quality_submodules() == 9
    assert "Checking submodule branch alignment" in capsys.readouterr().err


# --------------------------------------------------------------------------- exec arms: worktree and drill ---------------------------------------------------------------------------


def test_the_drills_and_worktree_import_their_module_and_pass_their_argv_through(
    monkeypatch,
) -> None:
    seen: list[tuple[str, list[str]]] = []

    class Fake:
        def __init__(self, name: str) -> None:
            self.name = name

        def main(self, argv: list[str]) -> int:
            seen.append((self.name, argv))
            return 7

    monkeypatch.setattr(rv.importlib, "import_module", Fake)
    assert rv.drill_main(["universe", "--keep-work"]) == 7
    assert rv.drill_main(["transfer", "--selftest"]) == 7
    assert rv.drill_main(["license"]) == 7
    assert rv.drill_main(["backup", "--selftest"]) == 7
    assert rv.worktree_main(["list"]) == 7
    assert seen == [
        ("rediacc_ci.drills.universe", ["--keep-work"]),
        ("rediacc_ci.drills.transfer", ["--selftest"]),
        ("rediacc_ci.drills.license", []),
        ("rediacc_ci.drills.backup", ["--selftest"]),
        ("rediacc_ci.dev.worktree", ["list"]),
    ]


def test_every_ported_drill_module_exists_with_a_main() -> None:
    for module in rv.DRILL_MODULES.values():
        assert callable(rv.importlib.import_module(module).main), module


def test_the_real_exec_targets_exist_and_are_executable() -> None:
    for script in (rv.WORKTREE_SCRIPT,):
        path = paths.from_root(script)
        assert path.is_file(), script
        assert os.access(path, os.X_OK), script


# --------------------------------------------------------------------------- the table and the introspection ---------------------------------------------------------------------------


def test_every_registered_verb_resolves_to_a_callable() -> None:
    for verb in entry.VERBS:
        assert callable(entry._resolve(verb)), verb.name


def test_arms_lists_every_row_and_every_table_key() -> None:
    lines = set(rv.arms())
    assert {"TOP " + name for name in entry.names()} <= lines
    for verb, table in rv.SUBCOMMAND_TABLES.items():
        assert {"SUB %s/%s" % (verb, sub) for sub in table} <= lines


def test_rotation_delegates_with_the_whole_argv(monkeypatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(rv.account, "rotation", lambda argv: noting(seen, argv))
    assert rv.rotation_main(["rotate", "slug"]) == 0
    assert seen == [["rotate", "slug"]]


def test_with_docker_group_scopes_the_entrypoint_variable_to_the_call(root, monkeypatch) -> None:
    monkeypatch.delenv("SCRIPT_ENTRYPOINT", raising=False)
    inside: list[str | None] = []

    def fake(_args):
        inside.append(os.environ.get("SCRIPT_ENTRYPOINT"))
        return True

    monkeypatch.setattr(rv.local_common, "reexec_with_docker_group", fake)
    rv._with_docker_group(["devbox", "status"])
    assert inside == [str(root / "run.sh")]
    assert "SCRIPT_ENTRYPOINT" not in os.environ
