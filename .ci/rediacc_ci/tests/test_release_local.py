"""`rediacc_ci.release.local`: the release table's invariants, the dry run, the secret boundary and the launch form.

Nothing here publishes. The table tests read `STEPS` and `plan()` only. The dry-run and executor tests inject the runner, the gates and the internal rows, so no child touches a registry, R2 or GitHub. The canary test runs real `bws_env exec` children against a fake `bws` and proves a value reaches the child while never reaching this module's streams. The launch-form test runs the package.json script through `sh` and asks `release_run` itself whether the process it started is admissible.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.release import local

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
REGIONS = list(local.read_regions(ROOT))
EDGE = local.plan(REGIONS)
WORKERS = local.plan(REGIONS, workers_only=True)
SCRIPT = (
    'PYTHONPATH="$PWD/.ci" PYTHONPYCACHEPREFIX=/dev/null /usr/bin/python3 -P -s -m '
    "rediacc_ci.release.local"
)


def no_prereqs(workers_only: bool) -> list[str]:
    del workers_only
    return []


def stub_release_run(root: pathlib.Path) -> type:
    del root
    return StubReleaseRun


def ok_row(step: local.Step, run: local.Run) -> int:
    del step, run
    return 0


def ids(steps: list[local.Step]) -> list[str]:
    return [s.id for s in steps]


# --------------------------------------------------------------------------- STEPS invariants


def test_the_sentinel_is_immediately_followed_by_the_tag() -> None:
    order = ids(EDGE)
    assert order[order.index("seal") + 1] == "tag"


def test_the_seal_and_the_tag_cannot_fail_and_every_later_failable_step_follows_the_tag() -> None:
    order = ids(EDGE)
    seal, tag = order.index("seal"), order.index("tag")
    assert not EDGE[seal].can_fail
    assert not EDGE[tag].can_fail
    for i, step in enumerate(EDGE):
        if i > seal and step.can_fail:
            assert i > tag, "%s can fail between the seal and the tag" % step.id
    assert [s.id for s in EDGE if not s.can_fail] == ["seal", "tag"]


def test_the_cli_publish_comes_before_every_account_deploy() -> None:
    order = ids(EDGE)
    deploys = [i for i, s in enumerate(order) if s.startswith("account-deploy-")]
    assert len(deploys) == len(REGIONS)
    for publish in ("upload-cli-r2", "assert-r2-sentinel", "seal", "tag"):
        assert all(order.index(publish) < i for i in deploys), publish


def test_every_account_deploy_is_behind_its_order_check_and_bracketed_by_records() -> None:
    for steps in (EDGE, WORKERS):
        order = ids(steps)
        for i, step_id in enumerate(order):
            if not step_id.startswith("account-deploy-"):
                continue
            region = step_id[len("account-deploy-") :]
            assert order.index("order-%s" % region) < i
            assert order.index("record-before-%s" % region) < i
            after = steps[order.index("record-after-%s" % region)]
            assert after.always
            assert after.arm == "record-before-%s" % region
            assert "--sink" in after.argv
            assert "r2" in after.argv
            order_step = steps[order.index("order-%s" % region)]
            assert order_step.argv[:3] == ("python3", "-m", "rediacc_ci.release.order")


def test_the_lock_is_judged_again_before_the_first_stage_write_and_right_before_the_seal() -> None:
    order = ids(EDGE)
    first_stage = next(i for i, s in enumerate(EDGE) if s.section == "stage")
    assert order[first_stage] == "lock-check-stage"
    assert order[order.index("seal") - 1] == "lock-check-seal"
    for step_id in ("lock-check-stage", "lock-check-seal"):
        step = EDGE[order.index(step_id)]
        assert step.profiles == ("r2-artifacts",)
        assert step.argv[2:4] == (local.SELF, "_lock-check")
    # Every write that publishes (a channel retag, an R2 upload, the seal) comes after the first recheck.
    for step_id in ("retag-renet", "upload-cli-r2", "upload-repos-r2", "seal"):
        assert order.index(step_id) > order.index("lock-check-stage")


def test_provenance_signs_before_anything_is_uploaded_and_rides_the_release() -> None:
    order = ids(EDGE)
    step = EDGE[order.index("provenance")]
    assert step.profiles == ("release-local",)
    assert order.index("linux-packages") < order.index("provenance") < order.index("upload-cli-r2")
    assert order.index("provenance") < order.index("github-release")


@pytest.mark.parametrize("steps", [EDGE, WORKERS], ids=["edge", "workers"])
def test_sections_run_in_the_declared_order(steps: list[local.Step]) -> None:
    ranks = [local.SECTIONS.index(s.section) for s in steps]
    assert ranks == sorted(ranks)
    assert steps[-1].id == "release-record"
    assert steps[-1].always


def test_the_gates_and_the_release_run_record_precede_every_build_and_publish() -> None:
    order = ids(EDGE)
    first_build = next(i for i, s in enumerate(EDGE) if s.section == "builds")
    assert order.index("gates") < order.index("release-run") < first_build


def test_workers_only_builds_seals_and_publishes_nothing() -> None:
    sections = {s.section for s in WORKERS}
    assert not sections & {"assist", "stage", "seal", "publish", "release"}
    assert ids(WORKERS)[0] == "channel-version"
    one = local.plan(["eu"], workers_only=True)
    assert not any(s.id.endswith(("-us", "-asia")) for s in one)


def test_every_module_and_profile_named_exists() -> None:
    supply = json.loads((ROOT / ".ci/config/secret-supply.json").read_text(encoding="utf-8"))[
        "consumers"
    ]
    vault = (ROOT / ".ci/config/bws-secret-map.json").read_text(encoding="utf-8")
    for step in local.STEPS:
        for profile in step.profiles:
            assert profile in supply, "%s names unknown profile %s" % (step.id, profile)
        for spec in step.binds:
            store, local_name = (p.strip() for p in spec.split(">", 1))
            assert '"%s"' % store in vault, "%s binds %s, not in the vault map" % (step.id, store)
            assert local_name
        words = list(step.argv)
        for i, word in enumerate(words[:-1]):
            if word == "-m" and words[i + 1].startswith("rediacc_ci."):
                module = ROOT / ".ci" / (words[i + 1].replace(".", "/") + ".py")
                assert module.is_file(), "%s runs missing module %s" % (step.id, words[i + 1])
        for word in words:
            for found in re.findall(r"-m (rediacc_ci\.[a-z_.]+)", word):
                assert (ROOT / ".ci" / (found.replace(".", "/") + ".py")).is_file(), found


def test_a_credentialed_step_runs_under_bws_env_exec_and_holds_no_value_itself() -> None:
    ctx = local.Context(version="9.9.9", sha="a" * 40, channel="edge", outcomes={})
    for step in EDGE:
        argv = local.child_argv(step, ctx)
        if step.profiles:
            assert argv[:4] == ["python3", "-m", "rediacc_ci.core.bws_env", "exec"], step.id
        if step.binds or step.gh_env:
            assert argv[argv.index(local.SELF) - 1 : argv.index(local.SELF) + 2] == [
                "-m",
                local.SELF,
                "_bind",
            ]


def test_the_www_secrets_bind_the_eu_ses_pair_under_the_unsuffixed_names() -> None:
    step = next(s for s in EDGE if s.id == "www-secrets")
    assert "AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID" in step.binds
    assert "AWS_SES_SECRET_ACCESS_KEY_EU > AWS_SES_SECRET_ACCESS_KEY" in step.binds
    assert "STRIPE_SANDBOX_SECRET_KEY > STRIPE_SECRET_KEY" in step.binds


def test_every_push_uses_the_session_github_token() -> None:
    order = ids(EDGE)
    cred = EDGE[order.index("clone-credential")]
    assert "gh auth git-credential" in cred.argv[-1]
    assert order.index("clone-credential") < order.index("tag")
    for step_id, name in (
        ("tag-submodules", "GITHUB_PAT"),
        ("homebrew", "GITHUB_PAT"),
        ("github-release", "GH_TOKEN"),
    ):
        assert name in EDGE[order.index(step_id)].gh_env, step_id
    assert not any("app-token" in " ".join(s.argv) for s in local.STEPS)


# --------------------------------------------------------------------------- the dry run


class FakeRunner:
    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.answers = answers or {}

    def __call__(
        self, argv: list[str], cwd: pathlib.Path, env: dict[str, str], capture: bool
    ) -> tuple[int, str]:
        del cwd, env, capture
        self.calls.append(argv)
        joined = " ".join(argv)
        for needle, answer in self.answers.items():
            if needle in joined:
                return 0, answer
        return 0, ""


VERSION_ANSWERS = {"detect_bump_type": "patch", "resolve_version": "9.9.9"}


def _gates(refusals: list[str]):
    def gates(root, version, ctx):
        del root, ctx
        assert version == "9.9.9"
        return local.GateResult(list(refusals), ["local-gates: clone: not judged under --dry-run"])

    return gates


def test_the_dry_run_prints_every_step_with_profiles_and_names_the_refusals(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local, "prereq_refusals", no_prereqs)
    runner = FakeRunner(VERSION_ANSWERS)
    before = (
        sorted((ROOT / local.CLONE_REL).glob("out-*")) if (ROOT / local.CLONE_REL).is_dir() else []
    )
    rc = local.main(
        ["--channel", "edge", "--dry-run"],
        runner=runner,
        gates=_gates(
            [
                "local-gates: ci-quick: no receipt",
                "local-gates: origin-main: HEAD is not origin/main",
            ]
        ),
    )
    out = capsys.readouterr().out
    assert rc == 1
    lines = out.splitlines()
    assert lines[0].startswith("release:local --channel edge (dry run)")
    assert "version: 9.9.9 (bump patch)" in lines
    assert "  local-gates: ci-quick: no receipt" in lines
    assert "steps (%d):" % len(EDGE) in lines
    for step in EDGE:
        assert re.search(
            r"^  \[%s\] %s  profile=" % (step.section, re.escape(step.id)), out, re.MULTILINE
        ), step.id
    assert lines[-1] == "refused: 2 refusal(s): ci-quick, origin-main"
    # Only the two read-only version rows ran; nothing else was started and no run directory was made.
    assert [c[2] for c in runner.calls] == [
        "rediacc_ci.version.detect_bump_type",
        "rediacc_ci.version.resolve_version",
    ]
    after = (
        sorted((ROOT / local.CLONE_REL).glob("out-*")) if (ROOT / local.CLONE_REL).is_dir() else []
    )
    assert after == before
    # Key names are printed for the profiles, never a value.
    assert "  release-local: ACCOUNT_ED25519_PUBLIC_KEY " in out


def test_a_green_dry_run_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local, "prereq_refusals", no_prereqs)
    rc = local.main(
        ["--channel", "edge", "--dry-run"], runner=FakeRunner(VERSION_ANSWERS), gates=_gates([])
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines()[-1].startswith("admitted: every gate passes")


def test_a_workers_only_dry_run_drops_the_lock_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local, "prereq_refusals", no_prereqs)
    monkeypatch.setattr(local, "internal_channel_version", _set_version)
    rc = local.main(
        ["--channel", "edge", "--dry-run", "--workers-only", "--regions", "eu"],
        runner=FakeRunner(),
        gates=_gates(
            ["local-gates: lock: the R2 sentinel cli/v9.9.9/.released exists: v9.9.9 is taken"]
        ),
    )
    assert rc == 0, capsys.readouterr().out


def _set_version(step: local.Step, run: local.Run) -> int:
    run.ctx[step.capture] = "9.9.9"
    return 0


def test_regions_needs_workers_only() -> None:
    with pytest.raises(SystemExit):
        local.parse(["--channel", "edge", "--regions", "eu"])


@pytest.mark.parametrize(
    "argv",
    [
        ["--channel", "stable"],
        ["--channel", "stable", "--dry-run"],
        ["--channel", "stable", "--workers-only", "--regions", "eu"],
        ["--channel", "stable", "--workers-only", "--dry-run"],
    ],
)
def test_stable_is_refused_locally(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    runner = FakeRunner(VERSION_ANSWERS)
    rc = local.main(argv, runner=runner, gates=_gates([]))
    err = capsys.readouterr().err
    assert rc == 2
    assert "promote-stable.yml" in err
    assert "ASKED:2026-10-27T09:45Z" in err
    assert runner.calls == []


@pytest.mark.parametrize("taken_at", ["lock-check-stage", "lock-check-seal"])
def test_a_version_taken_mid_run_stops_before_publishing(
    tmp_path: pathlib.Path, taken_at: str
) -> None:
    root = _tmp_root(tmp_path)
    ctx = local.base_context(root, ["eu"], False)
    ctx.update(version="9.9.9", out=str(tmp_path / "out"), run_id="t")
    seen: list[str] = []

    class TakenRun(local.Run):
        def run_step(self, step: local.Step) -> int:
            seen.append(step.id)
            return super().run_step(step)

    def runner(argv, cwd, env, capture):
        del cwd, env, capture
        return (1, "") if "_lock-check" in argv and seen[-1] == taken_at else (0, "")

    internal = dict.fromkeys(("gates", "release-run", "assist-await", "release-record"), ok_row)
    run = TakenRun(root, ctx, runner=runner, internal=internal)
    assert run.execute(local.plan(["eu"])) == 1
    assert run.failed == taken_at
    done = [r.id for r in run.results]
    assert not {"seal", "tag", "promote-renet", "github-release", "account-deploy-eu"} & set(done)
    if taken_at == "lock-check-stage":
        assert not {"retag-renet", "upload-cli-r2", "provenance"} & set(done)
    assert done[-1] == "release-record"


def test_provenance_writes_a_signed_sha256_manifest_of_every_release_asset(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("gpg") is None:
        pytest.skip("gpg is not installed")
    keyhome = tmp_path / "keyhome"
    keyhome.mkdir(mode=0o700)
    gpg = [
        "gpg",
        "--homedir",
        str(keyhome),
        "--batch",
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        "pw-7f3a",
    ]
    subprocess.run(
        [*gpg, "--quick-gen-key", "Release Test <t@example.invalid>", "ed25519", "sign", "never"],
        check=True,
        capture_output=True,
    )
    secret = subprocess.run(
        [*gpg, "--armor", "--export-secret-keys"], check=True, capture_output=True, text=True
    ).stdout
    tree = tmp_path / "clone"
    (tree / "dist" / "cli").mkdir(parents=True)
    (tree / "dist" / "packages").mkdir(parents=True)
    (tree / "dist" / "cli" / "rdc-linux-x64").write_bytes(b"binary")
    (tree / "dist" / "packages" / "rdc_9.9.9_amd64.deb").write_bytes(b"deb")
    monkeypatch.setenv("RELEASE_GPG_PRIVATE_KEY", secret)
    monkeypatch.setenv("RELEASE_GPG_PASSPHRASE", "pw-7f3a")
    assert local.provenance_main(["--root", str(tree)]) == 0
    sums = (tree / "dist" / "cli" / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert sums == [
        "%s  dist/cli/rdc-linux-x64" % hashlib.sha256(b"binary").hexdigest(),
        "%s  dist/packages/rdc_9.9.9_amd64.deb" % hashlib.sha256(b"deb").hexdigest(),
    ]
    verified = subprocess.run(
        [
            "gpg",
            "--homedir",
            str(keyhome),
            "--batch",
            "--verify",
            str(tree / "dist/cli/SHA256SUMS.asc"),
            str(tree / "dist/cli/SHA256SUMS"),
        ],
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0
    # A rerun regenerates the manifest without listing the manifest or its signature.
    assert local.provenance_main(["--root", str(tree)]) == 0
    assert len((tree / "dist" / "cli" / "SHA256SUMS").read_text(encoding="utf-8").splitlines()) == 2
    streams = capsys.readouterr()
    assert "pw-7f3a" not in streams.out + streams.err
    assert "PRIVATE KEY" not in streams.out + streams.err


# --------------------------------------------------------------------------- the executor


def _tmp_root(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "console"
    (root / ".ci" / "config").mkdir(parents=True)
    shutil.copy(ROOT / local.REGIONS_REL, root / local.REGIONS_REL)
    shutil.copy(ROOT / local.WELL_KNOWN_REL, root / local.WELL_KNOWN_REL)
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="F",
        GIT_AUTHOR_EMAIL="f@x.invalid",
        GIT_COMMITTER_NAME="F",
        GIT_COMMITTER_EMAIL="f@x.invalid",
    )
    for argv in (["init", "-q"], ["add", "."], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *argv], check=True, env=env, capture_output=True)
    return root


class StubReleaseRun:
    class RecordError(Exception):
        pass

    @staticmethod
    def entry_refusal(root, pid) -> str:
        del root, pid
        return ""


def test_a_refusal_from_the_gates_stops_before_any_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    root = _tmp_root(tmp_path)
    monkeypatch.setattr(local, "prereq_refusals", no_prereqs)
    monkeypatch.setattr(local, "_release_run_module", stub_release_run)
    ran: list[str] = []

    def handler(rc: int):
        def run(step: local.Step, run_: local.Run) -> int:
            del run_
            ran.append(step.id)
            return rc

        return run

    runner = FakeRunner(VERSION_ANSWERS)
    rc = local.main(
        ["--channel", "edge"],
        root=root,
        runner=runner,
        internal={
            "gates": handler(1),
            "release-run": handler(0),
            "release-record": handler(0),
        },
    )
    assert rc == 1
    assert [c[2] for c in runner.calls] == [
        "rediacc_ci.version.detect_bump_type",
        "rediacc_ci.version.resolve_version",
    ]
    # The gates refused; the release-run record was never written, and only the always-run release record followed.
    assert ran == ["gates", "release-record"]


def test_a_failed_deploy_rolls_back_its_armed_region_and_still_writes_the_records(
    tmp_path: pathlib.Path,
) -> None:
    root = _tmp_root(tmp_path)
    steps = local.plan(["eu", "us"], workers_only=True)
    ctx = local.base_context(root, ["eu", "us"], True)
    ctx.update(version="9.9.9", out=str(tmp_path / "out"), run_id="t")

    def runner(argv, cwd, env, capture):
        del cwd, env, capture
        return (1, "") if "rediacc_ci.deploy.deploy_account" in argv and "us" in argv else (0, "")

    internal = dict.fromkeys(("channel-version", "gates", "release-run", "release-record"), ok_row)
    run = local.Run(root, ctx, runner=runner, internal=internal)
    assert run.execute(steps) == 1
    done = [r.id for r in run.results]
    assert run.failed == "account-deploy-us"
    assert "proxy-deploy-eu" not in done  # the forward run stopped at the failure
    # Both regions recorded a before, so both roll back.
    assert "rollback-eu" in done
    assert "rollback-us" in done
    assert {"record-www", "record-after-eu", "record-after-us", "release-record"} <= set(done)
    assert done.index("rollback-us") < done.index("record-after-us")
    assert ctx["outcomes"]["account-deploy-us"] == "failure"
    # Every step carries its wall time for the release record.
    record = local.release_record(run)
    assert record["failed_step"] == "account-deploy-us"
    assert all(isinstance(s["seconds"], float) for s in record["steps"])


# --------------------------------------------------------------------------- the secret canary


FAKE_BWS = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, pathlib, sys
    pathlib.Path(os.environ["FAKE_BWS_MARK"]).write_text("called")
    names = ["CLOUDFLARE_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_ENDPOINT",
             "AWS_SES_ACCESS_KEY_ID_EU"]
    print(json.dumps([{"key": n, "value": "CANARY-%s-7f3a" % n} for n in names]))
    """
)

CANARY_DRIVER = textwrap.dedent(
    """\
    import pathlib, sys
    from rediacc_ci.release import local
    root = pathlib.Path(sys.argv[1])
    check = "import os,sys; sys.exit(0 if os.environ.get(%r,'').startswith('CANARY-') else 3)"
    steps = [
        local.Step("canary-profile", "stage", ("python3", "-c", check % "CLOUDFLARE_R2_ACCESS_KEY_ID"), profiles=("r2-artifacts",), cwd="root"),
        local.Step("canary-bind", "stage", ("python3", "-c", check % "AWS_SES_ACCESS_KEY_ID"), profiles=("r2-artifacts",), binds=("AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID",), cwd="root"),
    ]
    ctx = local.Context(channel="edge", version="9.9.9", sha="a" * 40, outcomes={}, regions=[])
    run = local.Run(root, ctx)
    rc = run.execute(steps)
    print("results", [(r.id, r.rc) for r in run.results])
    print("record", local.release_record.__name__)
    sys.exit(rc)
    """
)


def test_a_secret_from_bws_reaches_the_child_and_never_this_modules_streams(
    tmp_path: pathlib.Path,
) -> None:
    fake = tmp_path / "bws"
    fake.write_text(FAKE_BWS, encoding="utf-8")
    fake.chmod(0o755)
    mark = tmp_path / "called"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLOUDFLARE_", "AWS_", "REDIACC_BWS", "PYTHON"))
    }
    env.update(
        BWS_BIN=str(fake),
        BWS_ACCESS_TOKEN="fake-token",
        FAKE_BWS_MARK=str(mark),
        PYTHONPATH=str(ROOT / ".ci"),
    )
    proc = subprocess.run(
        [sys.executable, "-c", CANARY_DRIVER, str(ROOT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert mark.exists(), "the fake bws was never asked, so nothing was proven"
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "('canary-profile', 0)" in proc.stdout
    assert "('canary-bind', 0)" in proc.stdout
    assert "CANARY" not in proc.stdout
    assert "CANARY" not in proc.stderr


def test_the_dry_run_never_asks_bws(tmp_path: pathlib.Path) -> None:
    fake = tmp_path / "bws"
    fake.write_text(FAKE_BWS, encoding="utf-8")
    fake.chmod(0o755)
    mark = tmp_path / "called"
    driver = textwrap.dedent(
        """\
        import sys
        from rediacc_ci.release import local
        local.prereq_refusals = lambda _workers_only: []
        def gates(root, version, ctx):
            return local.GateResult([], [])
        class R:
            def __call__(self, argv, cwd, env, capture):
                return 0, {"detect_bump_type": "patch"}.get(argv[2].rsplit(".", 1)[-1], "9.9.9")
        sys.exit(local.main(["--channel", "edge", "--dry-run"], runner=R(), gates=gates))
        """
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("REDIACC_BWS", "PYTHON"))}
    env.update(
        BWS_BIN=str(fake),
        BWS_ACCESS_TOKEN="fake-token",
        FAKE_BWS_MARK=str(mark),
        PYTHONPATH=str(ROOT / ".ci"),
    )
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not mark.exists()
    assert "CANARY" not in proc.stdout + proc.stderr


# --------------------------------------------------------------------------- the launch form


def _package_script() -> str:
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"][
        "release:local"
    ]


def _launch(script: str) -> subprocess.CompletedProcess[str]:
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "LD_")) and k != "PWD"
    }
    return subprocess.run(
        ["sh", "-c", script + " _launch-probe"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_npm_script_is_the_launch_form() -> None:
    assert _package_script() == SCRIPT


@pytest.mark.skipif(not os.path.exists("/proc/self/exe"), reason="release_run reads /proc")
def test_the_npm_script_launches_what_entry_refusal_admits() -> None:
    proc = _launch(_package_script())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == "ok", proc.stdout + proc.stderr
    # Controls: each launch-form element, removed, is refused by release_run itself.
    for broken in (
        SCRIPT.replace(" PYTHONPYCACHEPREFIX=/dev/null", ""),
        SCRIPT.replace(" -P -s", " -s"),
        SCRIPT.replace('PYTHONPATH="$PWD/.ci"', "PYTHONPATH=/tmp:$PWD/.ci"),
    ):
        bad = _launch(broken)
        assert bad.returncode != 0, broken
        assert bad.stdout.strip() != "ok", broken
