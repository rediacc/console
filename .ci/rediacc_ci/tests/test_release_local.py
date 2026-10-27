"""`rediacc_ci.release.local`: the release table's invariants, the dry run, the secret boundary and the launch form.

Nothing here publishes. The table tests read `STEPS` and `plan()` only. The dry-run and executor tests inject the runner, the gates and the internal rows, so no child touches a registry, R2 or GitHub. The canary test runs real `bws_env exec` children against a fake `bws` and proves a value reaches the child while never reaching this module's streams. The launch-form test runs the package.json script through `sh` and asks `release_run` itself whether the process it started is admissible.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.release import local
from rediacc_ci.security import ci_workflow_invariants as inv

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


TAG_UNIT = ["tag-create", "tag-record", "tag-push"]


def test_the_sentinel_is_immediately_followed_by_the_tag() -> None:
    order = ids(EDGE)
    seal = order.index("seal")
    assert order[seal + 1 : seal + 4] == TAG_UNIT


def test_the_seal_and_the_tag_cannot_fail_and_every_later_failable_step_follows_the_tag() -> None:
    order = ids(EDGE)
    seal, tag = order.index("seal"), order.index("tag-push")
    for i, step in enumerate(EDGE):
        if i > seal and step.can_fail:
            assert i > tag, "%s can fail between the seal and the tag" % step.id
    assert [s.id for s in EDGE if not s.can_fail] == ["seal", *TAG_UNIT]


def test_the_tag_is_created_recorded_then_pushed_by_its_object_id() -> None:
    order = ids(EDGE)
    create, record, push = (EDGE[order.index(i)] for i in TAG_UNIT)
    assert "--create-only" in create.argv[-1]
    assert create.capture == "tag_oid"
    assert record.kind == "tag-record"
    assert push.argv[push.argv.index("--push-oid") + 1] == "{tag_oid}"
    assert "rediacc_ci.release.tag" in push.argv


def test_the_release_order_gate_holds_on_the_real_table() -> None:
    findings, shape = inv.analyse_local_steps(local.STEPS)
    assert findings == []
    assert shape["tag"] == TAG_UNIT


def test_the_cli_publish_comes_before_every_account_deploy() -> None:
    order = ids(EDGE)
    deploys = [i for i, s in enumerate(order) if s.startswith("account-deploy-")]
    assert len(deploys) == len(REGIONS)
    for publish in ("upload-cli-r2", "assert-r2-sentinel", "seal", "tag-push"):
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
    assert order.index("clone-credential") < order.index("tag-push")
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

    internal = dict.fromkeys(("gates", "release-run", "stamp", "release-record"), ok_row)
    run = TakenRun(root, ctx, runner=runner, internal=internal)
    assert run.execute(local.plan(["eu"])) == 1
    assert run.failed == taken_at
    done = [r.id for r in run.results]
    assert not {"seal", *TAG_UNIT, "promote-renet", "github-release", "account-deploy-eu"} & set(
        done
    )
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
    supply = json.loads(pathlib.Path(os.environ["FAKE_BWS_SUPPLY"]).read_text())["consumers"]
    names = sorted({s.split(">")[0].strip() for p in supply.values() for s in p.get("required", []) + p.get("optional", [])})
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
        local.Step("canary-bind", "stage", ("python3", "-c", check % "AWS_SES_ACCESS_KEY_ID"), profiles=("release-local",), binds=("AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID",), cwd="root"),
        local.Step("canary-undeclared", "stage", ("python3", "-c", check % "AWS_SES_ACCESS_KEY_ID"), profiles=("r2-artifacts",), binds=("AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID",), cwd="root"),
    ]
    ctx = local.Context(channel="edge", version="9.9.9", sha="a" * 40, outcomes={}, regions=[])
    run = local.Run(root, ctx)
    rc = 0
    for step in steps:
        rc |= run.run_step(step) if step.id != "canary-undeclared" else 0
    undeclared = run.run_step(steps[-1])
    print("results", [(r.id, r.rc) for r in run.results])
    rc = rc if undeclared == 1 else 9
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
        FAKE_BWS_SUPPLY=str(ROOT / ".ci/config/secret-supply.json"),
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
    # A store name the step's profile does not declare is refused by _bind, never fetched around the profile.
    assert "('canary-undeclared', 1)" in proc.stdout
    assert "is not declared by profile(s) r2-artifacts" in proc.stderr
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
        FAKE_BWS_SUPPLY=str(ROOT / ".ci/config/secret-supply.json"),
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


# --------------------------------------------------------------------------- the gates verdict (review 7c25d047.1)


@pytest.mark.parametrize(
    ("rc", "lines", "workers_only", "want"),
    [
        (0, ["local-gates: admitted"], False, 0),
        (0, [], False, 0),
        # A child that crashed, or a bws refusal before any gate ran: no refusal line, still a refusal.
        (1, [], False, 1),
        (1, ["Traceback (most recent call last):"], True, 1),
        (2, [], False, 1),
        (0, ["local-gates: ci-quick: no receipt"], False, 1),
        (1, ["local-gates: lock: v9.9.9 is taken"], False, 1),
        # A workers-only run takes the lock as its premise, and only the lock.
        (1, ["local-gates: lock: v9.9.9 is taken"], True, 0),
        (1, ["local-gates: lock: v9.9.9 is taken", "local-gates: ci-quick: none"], True, 1),
        # rc 0 beside a refusal line is a contradiction (local_gates.main exits 1 whenever it prints one), so it refuses even when the line is the lock a workers-only run would take.
        (0, ["local-gates: lock: v9.9.9 is taken"], True, 1),
    ],
)
def test_any_nonzero_gates_exit_refuses(
    rc: int, lines: list[str], workers_only: bool, want: int
) -> None:
    assert local.gates_verdict(rc, lines, workers_only) == want


# --------------------------------------------------------------------------- binds through the profile


def test_every_bind_is_declared_by_the_profiles_of_its_step() -> None:
    supply = json.loads((ROOT / ".ci/config/secret-supply.json").read_text(encoding="utf-8"))[
        "consumers"
    ]
    checked = 0
    for step in local.STEPS:
        declared = {
            spec.split(">")[-1].strip()
            for p in step.profiles
            for spec in supply[p].get("required", []) + supply[p].get("optional", [])
        }
        for spec in step.binds:
            store = spec.split(">", 1)[0].strip()
            assert store in declared, "%s binds %s, which %s does not declare" % (
                step.id,
                store,
                step.profiles,
            )
            checked += 1
    assert checked >= 7, "the binds this test exists for are gone; it checked %d" % checked


def test_bind_refusals_names_an_undeclared_or_empty_store() -> None:
    env = {"REDIACC_BWS_PROFILES": "release-local", "STRIPE_SANDBOX_SECRET_KEY": "x"}
    assert local.bind_refusals(["STRIPE_SANDBOX_SECRET_KEY > STRIPE_SECRET_KEY"], env) == []
    (empty,) = local.bind_refusals(["AWS_SES_REGION_EU > AWS_SES_REGION"], env)
    assert "AWS_SES_REGION_EU" in empty
    assert "empty" in empty
    (undeclared,) = local.bind_refusals(["TURNSTILE_SITE_KEY > VITE_TURNSTILE_SITE_KEY"], env)
    assert "not declared" in undeclared
    assert local.bind_refusals(["A > B"], {})[0].startswith("no profile is carried")


def test_a_token_only_bind_needs_no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The profile-less `gh_env` rows (github-release, tag-submodules, ...) reach `_bind` with no carried profile and no spec; only a spec needs one."""
    token_only = [s.id for s in local.STEPS if s.gh_env and not s.profiles and not s.binds]
    assert "github-release" in token_only
    assert local.bind_refusals([], {}) == []
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    exec_seen: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        local.subprocess,
        "run",
        lambda argv, **_kw: subprocess.CompletedProcess(argv, 0, "gho_fixture\n", ""),
    )
    monkeypatch.setattr(
        local.child_proc,
        "exec_replace",
        lambda cmd, env: exec_seen.append((list(cmd), env.get("GH_TOKEN", ""))),
    )
    step = next(s for s in local.STEPS if s.id == "github-release")
    argv = local.child_argv(step, local.Context(version="9.9.9"))
    assert argv[:4] == ["python3", "-m", local.SELF, "_bind"]
    assert local.bind_main(argv[4:]) == 0
    assert exec_seen == [(argv[argv.index("--") + 1 :], "gho_fixture")]


# --------------------------------------------------------------------------- the tag record


class RecordingReleaseRun:
    writes: typing.ClassVar[list[list[dict[str, str]]]] = []

    class RecordError(Exception):
        pass

    @classmethod
    def write_release_run(cls, root, run_id, *, tree, version, channel, pushes):
        del tree, version, channel
        cls.writes.append([dict(p) for p in pushes])
        return root / ("run-%s.json" % run_id)


def test_the_record_lists_no_push_until_the_tag_object_exists_then_exactly_its_oid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    RecordingReleaseRun.writes = []
    monkeypatch.setattr(local, "_release_run_module", lambda _root: RecordingReleaseRun)
    ctx = local.Context(
        version="9.9.9", sha="a" * 40, tree="t" * 40, run_id="r1", clone=str(tmp_path / "clone")
    )
    run = local.Run(tmp_path, ctx)
    step = next(s for s in local.STEPS if s.id == "tag-record")
    assert local.internal_release_run(step, run) == 0
    assert RecordingReleaseRun.writes == [[]]
    first_path = ctx["release_run"]
    # tag-create printed something that is not an object id: refused, nothing written.
    ctx["tag_oid"] = "Created tag v9.9.9"
    assert local.internal_tag_record(step, run) == 1
    assert len(RecordingReleaseRun.writes) == 1
    oid = "b" * 40
    ctx["tag_oid"] = oid
    assert local.internal_tag_record(step, run) == 0
    assert RecordingReleaseRun.writes[-1] == [
        {
            "toplevel": str(tmp_path / "clone"),
            "remote": "origin",
            "remote_ref": "refs/tags/v9.9.9",
            "oid": oid,
        }
    ]
    assert ctx["release_run"] == first_path, "REDIACC_RELEASE_RUN must not move"


def test_a_sealed_untagged_run_names_the_recovery() -> None:
    run = local.Run(
        ROOT, local.Context(version="9.9.9", sha="a" * 40, clone="/c", outcomes={}), backoff=()
    )
    assert local.sealed_untagged(run) == []
    run.ctx["outcomes"].update({"seal": "success", "tag-push": "failure"})
    lines = local.sealed_untagged(run)
    assert lines[0].startswith("SEALED WITHOUT A TAG: cli/v9.9.9/.released")
    assert "rediacc_ci.release.tag --version 9.9.9 --sha " + "a" * 40 in lines[-1]
    run.ctx["outcomes"]["tag-push"] = "success"
    assert local.sealed_untagged(run) == []


def test_a_no_fail_row_is_retried_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(local.time, "sleep", slept.append)
    calls: list[int] = []

    def runner(argv, cwd, env, capture):
        del argv, cwd, env, capture
        calls.append(1)
        return (0, "") if len(calls) == 3 else (1, "")

    ctx = local.Context(version="9.9.9", sha="a" * 40, clone="/c", outcomes={})
    run = local.Run(ROOT, ctx, runner=runner)
    seal = next(s for s in local.STEPS if s.id == "seal")
    assert run.run_step(dataclasses_replace(seal, profiles=())) == 0
    assert slept == list(local.RETRY_BACKOFF)
    assert run.results[-1].attempts == 3


def dataclasses_replace(step: local.Step, **kw: typing.Any) -> local.Step:
    return dataclasses.replace(step, **kw)


# --------------------------------------------------------------------------- the assist exchange


def test_the_assist_is_staged_before_dispatch_and_fetched_before_anything_is_signed() -> None:
    order = ids(EDGE)
    assert (
        order.index("renet-key-gate")
        < order.index("assist-stage-in")
        < order.index("assist-dispatched-at")
        < order.index("assist-dispatch")
        < order.index("assist-fetch")
        < order.index("cli-manifest")
        < order.index("provenance")
    )
    assert order.index("upload-cli-r2") < order.index("assist-clean") < order.index("seal")
    for step_id in ("assist-stage-in", "assist-fetch", "assist-clean"):
        assert EDGE[order.index(step_id)].profiles == ("r2-artifacts",)
    assert EDGE[order.index("assist-fetch")].capture == "assist_run"


class _FailAt(local.Run):
    """A run whose rows only record their id, the row named `fail_at` failing."""

    fail_at: str = ""
    seen: typing.ClassVar[list[str]] = []

    def run_step(self, step: local.Step) -> int:
        self.seen.append(step.id)
        rc = 1 if step.id == self.fail_at else 0
        self.ctx["outcomes"][step.id] = "success" if rc == 0 else "failure"
        return rc


def _clean_runs(fail_at: str) -> list[str]:
    """The assist-clean rows a run of the real table up to the seal executes when `fail_at` fails."""
    order = ids(EDGE)
    steps = [
        s
        for s in EDGE
        if order.index(s.id) <= order.index("seal") or s.id == "assist-clean-on-stop"
    ]
    _FailAt.seen = []
    run = _FailAt(ROOT, local.Context(version="9.9.9", sha="a" * 40, clone="/c", outcomes={}))
    run.fail_at = fail_at
    run.execute(steps)
    return [i for i in _FailAt.seen if i.startswith("assist-clean")]


@pytest.mark.parametrize("fail_at", ["assist-fetch", "validate-stage", "seal"])
def test_a_stop_after_the_stage_in_still_empties_the_assist_prefix(fail_at: str) -> None:
    assert "assist-clean-on-stop" in _clean_runs(fail_at)


def test_a_stop_before_the_stage_in_or_a_clean_run_leaves_the_on_stop_row_idle() -> None:
    assert _clean_runs("renet-key-gate") == []
    assert _clean_runs("no-such-row") == ["assist-clean"]
    row = next(s for s in EDGE if s.id == "assist-clean-on-stop")
    assert row.on_failure
    assert row.arm == "assist-stage-in"
    assert row.argv == next(s for s in EDGE if s.id == "assist-clean").argv


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("a" * 40 + " 123\n", None),
        ("a" * 40 + " 1234", None),
        ("b" * 40 + " 123", "names sha"),
        # A version-substring or prefix never matches: the sha is compared whole.
        ("a" * 39 + " 123", "names sha"),
        ("a" * 40, "not `<sha> <run id>`"),
        ("a" * 40 + " x12", "not `<sha> <run id>`"),
    ],
)
def test_the_marker_is_matched_by_exact_fields(text: str, error: str | None) -> None:
    if error is None:
        assert local.parse_marker(text, "a" * 40) == text.split()[1]
    else:
        with pytest.raises(local.AssistError, match=re.escape(error)):
            local.parse_marker(text, "a" * 40)


def _sums(folder: pathlib.Path, files: dict[str, bytes], sums_name: str, lie: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, body in files.items():
        (folder / name).write_bytes(body)
        digest = hashlib.sha256(body + (b"x" if name == lie else b"")).hexdigest()
        lines.append("%s  %s\n" % (digest, name))
    (folder / sums_name).write_text("".join(lines), encoding="utf-8")


def test_checksum_refusals_both_directions(tmp_path: pathlib.Path) -> None:
    _sums(tmp_path, {"renet-linux-amd64": b"1", "renet-linux-arm64": b"2"}, "checksums.sha256")
    sums = tmp_path / "checksums.sha256"
    assert local.checksum_refusals(tmp_path, sums, ["renet-linux-amd64"]) == []
    assert "not listed" in local.checksum_refusals(tmp_path, sums, ["renet-darwin-amd64"])[0]
    (tmp_path / "renet-linux-arm64").write_bytes(b"tampered")
    assert "does not match" in local.checksum_refusals(tmp_path, sums, ["renet-linux-arm64"])[0]
    assert "missing" in local.checksum_refusals(tmp_path, tmp_path / "nope", ["x"])[0]


class FakeAws:
    """Answers `_aws` from a dict of key -> body standing in for the bucket; records every call."""

    def __init__(self, marker_after: int, marker: str, seas: dict[str, bytes]) -> None:
        self.calls: list[list[str]] = []
        self.marker_after = marker_after
        self.marker = marker
        self.seas = seas
        self.polls = 0

    def __call__(self, args, endpoint, env):
        del endpoint, env
        self.calls.append(list(args))
        if args[:2] == ["s3", "cp"] and args[-1] == "-":
            self.polls += 1
            if self.polls > self.marker_after:
                return subprocess.CompletedProcess(args, 0, self.marker, "")
            return subprocess.CompletedProcess(args, 1, "", "An error occurred (404) Not Found")
        if args[:3] == ["s3", "cp", "--recursive"]:
            dist = pathlib.Path(args[-1])
            dist.mkdir(parents=True, exist_ok=True)
            for name, body in self.seas.items():
                (dist / name).write_bytes(body)
                (dist / (name + ".sha256")).write_text(
                    "%s  %s\n" % (hashlib.sha256(body).hexdigest(), name), encoding="utf-8"
                )
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")


SHA = "c" * 40


def _assist_env(monkeypatch: pytest.MonkeyPatch, aws: FakeAws, view: object, failed: str = ""):
    monkeypatch.setattr(local, "_assist_r2", lambda _root: ("bucket", "https://r2", {}))
    monkeypatch.setattr(local, "_aws", aws)
    monkeypatch.setattr(local, "assist_failed_run", lambda _sha, _since: failed)
    monkeypatch.setattr(local, "_gh_json", lambda _args: view)
    monkeypatch.setattr(local.time, "sleep", lambda _s: None)


def test_assist_fetch_waits_for_the_marker_and_fetches_the_four_seas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    seas = {name: name.encode() for name in local.ASSIST_SEAS}
    aws = FakeAws(2, SHA + " 4242\n", seas)
    _assist_env(monkeypatch, aws, {"workflowName": local.ASSIST_NAME, "headSha": SHA})
    assert local.assist_fetch("9.9.9", SHA, "2026-10-27T10:00:00Z", tmp_path, poll=0) == "4242"
    assert aws.polls == 3
    for name in local.ASSIST_SEAS:
        assert (tmp_path / "dist" / "cli" / name).read_bytes() == name.encode()
    fetch = next(c for c in aws.calls if "--recursive" in c)
    assert "s3://bucket/staging/local-release/v9.9.9/cli/" in fetch
    assert ".complete" in fetch[fetch.index("--exclude") + 1]


@pytest.mark.parametrize(
    ("view", "seas", "failed", "error"),
    [
        ({"workflowName": "CI", "headSha": SHA}, None, "", "not Local Release Assist"),
        ({"workflowName": "Local Release Assist", "headSha": "d" * 40}, None, "", "not Local"),
        (None, None, "", "unproven"),
        (
            {"workflowName": "Local Release Assist", "headSha": SHA},
            {"rdc-mac-arm64": b"1"},
            "",
            "not provably whole",
        ),
    ],
)
def test_assist_fetch_refuses_an_unproven_marker_or_a_partial_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    view: object,
    seas: dict[str, bytes] | None,
    failed: str,
    error: str,
) -> None:
    aws = FakeAws(0, SHA + " 4242", seas or {n: n.encode() for n in local.ASSIST_SEAS})
    _assist_env(monkeypatch, aws, view, failed)
    with pytest.raises(local.AssistError, match=re.escape(error)):
        local.assist_fetch("9.9.9", SHA, "2026-10-27T10:00:00Z", tmp_path, poll=0)


def test_assist_fetch_stops_early_on_a_red_dispatch_and_times_out_on_silence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    aws = FakeAws(10**6, "", {})
    _assist_env(monkeypatch, aws, None, failed="777")
    with pytest.raises(local.AssistError, match="run 777"):
        local.assist_fetch("9.9.9", SHA, "2026-10-27T10:00:00Z", tmp_path, poll=0)
    aws = FakeAws(10**6, "", {})
    _assist_env(monkeypatch, aws, None)
    with pytest.raises(local.AssistError, match=r"no s3://bucket/.*after 0s"):
        local.assist_fetch("9.9.9", SHA, "x", tmp_path, timeout=0, poll=0)


def test_assist_stage_in_empties_the_prefix_then_uploads_a_checked_renet_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "private" / "bin"
    files = {name: name.encode() for name in local.ASSIST_RENET}
    _sums(folder, {**files, "criu-linux-amd64": b"c"}, "checksums.sha256")
    (folder / "unrelated.txt").write_text("no")
    aws = FakeAws(0, "", {})
    _assist_env(monkeypatch, aws, None)
    local.assist_stage_in("9.9.9", tmp_path)
    assert aws.calls[0][:3] == ["s3", "rm", "--recursive"]
    uploaded = sorted(c[-1].rsplit("/", 1)[-1] for c in aws.calls[1:])
    assert uploaded == sorted([*files, "criu-linux-amd64", "checksums.sha256"])
    # A renet that does not match its checksum stops the staging before anything is touched.
    _sums(folder, files, "checksums.sha256", lie="renet-darwin-arm64")
    aws = FakeAws(0, "", {})
    _assist_env(monkeypatch, aws, None)
    with pytest.raises(local.AssistError, match="renet-darwin-arm64 does not match"):
        local.assist_stage_in("9.9.9", tmp_path)
    assert aws.calls == []


def test_assist_failed_run_names_only_a_red_dispatch_of_this_sha_since_the_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    since = "2026-10-27T10:00:00Z"
    rows = [
        {
            "databaseId": 1,
            "headSha": SHA,
            "status": "completed",
            "conclusion": "failure",
            "createdAt": "2026-10-27T09:59:59Z",
        },
        {
            "databaseId": 2,
            "headSha": "d" * 40,
            "status": "completed",
            "conclusion": "failure",
            "createdAt": since,
        },
        {
            "databaseId": 3,
            "headSha": SHA,
            "status": "in_progress",
            "conclusion": "",
            "createdAt": since,
        },
        {
            "databaseId": 4,
            "headSha": SHA,
            "status": "completed",
            "conclusion": "success",
            "createdAt": since,
        },
    ]
    monkeypatch.setattr(local, "_gh_json", lambda _args: rows)
    assert local.assist_failed_run(SHA, since) == ""
    rows.append(
        {
            "databaseId": 5,
            "headSha": SHA,
            "status": "completed",
            "conclusion": "cancelled",
            "createdAt": since,
        }
    )
    assert local.assist_failed_run(SHA, since) == "5"
    monkeypatch.setattr(local, "_gh_json", lambda _args: None)
    assert local.assist_failed_run(SHA, since) == ""
