"""The proxy and console-executor steps of .github/workflows/cd-deploy-account.yml and the two workflows that call it (agent/plans/PLAN-proxy-cd-six-targets.md, Design item 9, box D2).

What this pins, read structurally through `rediacc_ci.workflows` (the repo's one dependency-free parser):
  - the forward order inside the per-region deploy job: record-before, bootstrap (only when the proxy Worker does not exist), the account deploy, the Worker secrets, the proxy deploy, the proxy smoke, the executor enable;
  - the enable condition, exactly `steps.proxy_smoke.outcome == 'success'` (ruling "Closed until smoke passes");
  - the rollback step: `failure()`, after the forward steps, running `deploy_record rollback`, whose own reverse order (executor, proxy, then the printed account and D1 commands) `test_deploy_deploy_record.py` drives;
  - the presence refusal: a release older than the proxy CD steps fails on every target instead of skipping the proxy steps;
  - the record written `always()` and uploaded;
  - the edge-only stage job with `actions: read`, which the deploy job waits on;
  - cd-v2.yml (edge and hotfix) and promote-stable.yml passing `version`, edge also `ci_run_id`;
  - no step in the three workflows echoing a secret value: a secret reaches a step only through `env:`, never as `${{ secrets.* }}` or `${{ env.BWS_* }}` inside `run:`, and no `echo`/`printf` line in a `run:` names a variable that carries one.
Each check carries a control that plants the violation in a copy of the parsed document and asserts the check sees it, so a check that cannot fail does not pass.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess

import pytest

from rediacc_ci import paths, workflows

WF = paths.from_root(".github", "workflows")
ACCOUNT = WF / "cd-deploy-account.yml"
CD = WF / "cd-v2.yml"
PROMOTE = WF / "promote-stable.yml"

FORWARD = [
    "Record before",
    "Bootstrap proxy Worker",
    "Deploy account Worker",
    "Set Worker secrets",
    "Deploy proxy Worker",
    "Proxy smoke",
    "Enable console executor",
]
TAIL = [
    "Roll back proxy and console executor",
    "Write the deploy record",
    "Upload the deploy record",
]
ENABLE_IF = "steps.proxy_smoke.outcome == 'success'"


def load(path):
    doc = workflows.load(path)
    assert isinstance(doc, dict), path
    return doc


def steps(doc: dict, job: str) -> list[dict]:
    return list(doc["jobs"][job]["steps"])


def base_name(step: dict) -> str:
    """A step name without its ` (${{ matrix.id }})` suffix."""
    return re.sub(r"\s*\(\$\{\{.*\}\}\)\s*$", "", str(step.get("name") or ""))


def index_of(stps: list[dict], name: str) -> int:
    found = [i for i, s in enumerate(stps) if base_name(s) == name]
    assert len(found) == 1, "%r appears %d times in the deploy job" % (name, len(found))
    return found[0]


def by_name(stps: list[dict], name: str) -> dict:
    return stps[index_of(stps, name)]


def order_problems(stps: list[dict]) -> list[str]:
    seq = FORWARD + TAIL
    at = [index_of(stps, n) for n in seq]
    return [
        "%r runs before %r" % (seq[i + 1], seq[i]) for i in range(len(at) - 1) if at[i] > at[i + 1]
    ]


@pytest.fixture(scope="module")
def account():
    return load(ACCOUNT)


@pytest.fixture(scope="module")
def deploy(account):
    return steps(account, "deploy")


# ---- inputs and the stage job -----------------------------------------------


def test_the_reusable_workflow_takes_a_required_version_and_an_optional_ci_run_id(account):
    inputs = account["on"]["workflow_call"]["inputs"]
    assert inputs["version"]["required"] is True
    assert inputs["version"]["type"] == "string"
    assert inputs["ci_run_id"]["required"] is False
    assert inputs["ci_run_id"]["default"] == ""


def test_the_stage_job_is_edge_only_reads_actions_and_gates_the_deploy(account):
    job = account["jobs"]["stage-executor"]
    assert "inputs.target == 'edge'" in job["if"]
    assert "inputs.ci_run_id != ''" in job["if"]
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    downloads = [
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/download-artifact@")
    ]
    assert [s["with"]["name"] for s in downloads] == [
        "cli-bundle-${{ inputs.ref }}",
        "renet-binaries-${{ inputs.ref }}",
    ]
    assert all(s["with"]["run-id"] == "${{ inputs.ci_run_id }}" for s in downloads)
    stage = [s for s in job["steps"] if "executor_artifacts stage" in str(s.get("run", ""))]
    assert len(stage) == 1
    assert "--version" in stage[0]["run"]
    deploy_job = account["jobs"]["deploy"]
    assert "stage-executor" in deploy_job["needs"]
    assert "needs.stage-executor.result == 'skipped'" in deploy_job["if"]
    # Only the stage job reads other runs' artifacts.
    for name, other in account["jobs"].items():
        if name != "stage-executor":
            assert "actions" not in (other.get("permissions") or {}), name


# ---- the forward order, the enable condition, the rollback -------------------


def test_the_deploy_job_runs_the_steps_in_design_order(deploy):
    assert order_problems(deploy) == []


def test_order_control_a_swapped_smoke_and_enable_is_seen(deploy):
    planted = copy.deepcopy(deploy)
    i, j = index_of(planted, "Proxy smoke"), index_of(planted, "Enable console executor")
    planted[i], planted[j] = planted[j], planted[i]
    assert order_problems(planted) == ["'Enable console executor' runs before 'Proxy smoke'"]


def test_record_before_runs_before_the_migrations_and_exposes_proxy_exists(deploy):
    rec = by_name(deploy, "Record before")
    assert rec["id"] == "record_before"
    assert "deploy_record before" in rec["run"]
    assert "--version" in rec["run"]
    # deploy_account applies the migrations; the bookmark must exist before it.
    assert "deploy_account" in by_name(deploy, "Deploy account Worker")["run"]


def test_the_bootstrap_runs_only_when_the_proxy_worker_does_not_exist(deploy):
    boot = by_name(deploy, "Bootstrap proxy Worker")
    assert boot["if"] == "steps.record_before.outputs.proxy_exists == 'false'"
    assert "deploy_record bootstrap" in boot["run"]


def test_the_proxy_deploy_and_smoke_are_deploy_proxy_with_record_then_smoke_only(deploy):
    dep = by_name(deploy, "Deploy proxy Worker")
    for flag in ("--target", "--region", "--version", "--record"):
        assert flag in dep["run"], flag
    assert "--smoke-only" not in dep["run"]
    smoke = by_name(deploy, "Proxy smoke")
    assert smoke["id"] == "proxy_smoke"
    assert "deploy_proxy" in smoke["run"]
    assert "--smoke-only" in smoke["run"]


def test_the_executor_opens_only_on_a_passing_smoke(deploy):
    enable = by_name(deploy, "Enable console executor")
    assert enable["if"] == ENABLE_IF
    assert "console_executor --enable" in enable["run"]
    # Nothing else in the job opens it.
    others = [
        s
        for s in deploy
        if s is not enable and "console_executor --enable" in str(s.get("run", ""))
    ]
    assert others == []


def test_the_rollback_runs_on_failure_after_the_forward_steps(deploy):
    rb = by_name(deploy, "Roll back proxy and console executor")
    assert "failure()" in rb["if"]
    assert "steps.record_before.outcome == 'success'" in rb["if"]
    assert "deploy_record rollback" in rb["run"]
    assert index_of(deploy, "Roll back proxy and console executor") > index_of(
        deploy, "Enable console executor"
    )


def test_the_record_is_written_always_and_uploaded(deploy):
    write = by_name(deploy, "Write the deploy record")
    assert write["if"].startswith("always()")
    assert "deploy_record after" in write["run"]
    assert write["env"]["ENABLE_OUTCOME"] == "${{ steps.enable.outcome }}"
    assert write["env"]["ROLLBACK_OUTCOME"] == "${{ steps.rollback.outcome }}"
    up = by_name(deploy, "Upload the deploy record")
    assert up["if"].startswith("always()")
    assert up["with"]["name"] == "deploy-record-${{ inputs.target }}-${{ matrix.id }}"
    assert up["with"]["if-no-files-found"] == "error"


def test_the_proxy_steps_get_the_deploy_proxy_profile_names_from_bitwarden(deploy):
    fetched = set()
    for s in deploy:
        if str(s.get("uses", "")) == "./.github/actions/bws-secrets":
            fetched |= {
                line.split(">")[0].strip()
                for line in s["with"]["secrets"].splitlines()
                if line.strip()
            }
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
    ):
        assert name in fetched, name
    dep = by_name(deploy, "Deploy proxy Worker")
    assert dep["env"]["AWS_ACCESS_KEY_ID"] == "${{ env.BWS_CLOUDFLARE_R2_ACCESS_KEY_ID }}"
    assert dep["env"]["AWS_SECRET_ACCESS_KEY"] == "${{ env.BWS_CLOUDFLARE_R2_SECRET_ACCESS_KEY }}"


# ---- callers ----------------------------------------------------------------


def callers(doc: dict) -> dict[str, dict]:
    return {
        name: job
        for name, job in doc["jobs"].items()
        if str(job.get("uses", "")) == "./.github/workflows/cd-deploy-account.yml"
    }


def test_cd_v2_edge_and_hotfix_and_promote_stable_pass_version():
    cd, promote = callers(load(CD)), callers(load(PROMOTE))
    assert sorted(cd) == ["deploy-account-edge", "deploy-account-stable"]
    assert sorted(promote) == ["deploy-account-stable"]
    assert cd["deploy-account-edge"]["with"]["version"] == "${{ needs.init.outputs.next_version }}"
    assert (
        cd["deploy-account-stable"]["with"]["version"] == "${{ needs.init.outputs.next_version }}"
    )
    assert (
        promote["deploy-account-stable"]["with"]["version"]
        == "${{ needs.promote.outputs.version }}"
    )
    assert "ci_run_id" in cd["deploy-account-edge"]["with"]
    assert "workers_only" in cd["deploy-account-edge"]["with"]["ci_run_id"]
    assert "ci_run_id" not in cd["deploy-account-stable"]["with"]
    for job in [*cd.values(), *promote.values()]:
        assert job["permissions"].get("actions") == "read"


# ---- no secret echoed -------------------------------------------------------

SECRET_REF = re.compile(r"\$\{\{\s*(secrets\.|env\.BWS_)")
PRINT_LINE = re.compile(r"^\s*(echo|printf)\b.*", re.MULTILINE)


def echo_problems(doc: dict, label: str) -> list[str]:
    """Every step that puts a secret value into a `run:` script, or prints a variable carrying one."""
    problems = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for st in job.get("steps") or []:
            run = str(st.get("run") or "")
            if not run:
                continue
            where = "%s:%s:%s" % (label, job_name, st.get("name") or st.get("id") or "?")
            if SECRET_REF.search(run):
                problems.append("%s interpolates a secret into run:" % where)
            carriers = [k for k, v in (st.get("env") or {}).items() if SECRET_REF.search(str(v))]
            for line in PRINT_LINE.finditer(run):
                text = line.group(0)
                problems.extend(
                    "%s prints $%s" % (where, name)
                    for name in carriers
                    if re.search(r"\$\{?%s\b" % re.escape(name), text)
                )
    return problems


@pytest.mark.parametrize("path", [ACCOUNT, CD, PROMOTE], ids=lambda p: p.name)
def test_no_step_echoes_a_secret_value(path):
    assert echo_problems(load(path), path.name) == []


def test_echo_control_both_plants_are_seen(account):
    planted = copy.deepcopy(account)
    stps = planted["jobs"]["deploy"]["steps"]
    enable = by_name(stps, "Enable console executor")
    enable["run"] = 'echo "token is $CLOUDFLARE_API_TOKEN"\n' + enable["run"]
    smoke = by_name(stps, "Proxy smoke")
    smoke["run"] = "curl -H 'x: ${{ secrets.BWS_ACCESS_TOKEN }}' https://x\n" + smoke["run"]
    found = echo_problems(planted, "planted")
    assert any("prints $CLOUDFLARE_API_TOKEN" in p for p in found), found
    assert any("Proxy smoke" in p and "interpolates" in p for p in found), found
    assert len(found) == 2, found


PRESENT = "Proxy CD steps present in"


def run_presence(step: dict, root, target: str) -> int:
    env = {
        **os.environ,
        "TARGET": target,
        "REGION": "eu",
        "REF": "v0.1.0",
        "GITHUB_OUTPUT": str(root / "out"),
        "GITHUB_STEP_SUMMARY": str(root / "summary"),
    }
    return subprocess.run(
        ["bash", "-e", "-c", step["run"]], cwd=root, env=env, capture_output=True, check=False
    ).returncode


@pytest.mark.parametrize("target", ["edge", "stable"])
def test_a_release_older_than_the_proxy_steps_fails_on_every_target(deploy, tmp_path, target):
    """Ruling 2026-10-26 "Fail those promotions": a stable promote of a pre-proxy release is refused, never skipped."""
    step = next(s for s in deploy if str(s.get("name") or "").startswith(PRESENT))
    assert run_presence(step, tmp_path, target) == 1
    mods = tmp_path / ".ci" / "rediacc_ci" / "deploy"
    mods.mkdir(parents=True)
    for name in ("deploy_record.py", "console_executor.py"):
        (mods / name).write_text("")
    assert run_presence(step, tmp_path, target) == 0


def test_no_proxy_step_is_skipped_on_a_presence_output(deploy):
    """The presence check refuses instead of gating: no later step may reference `proxy_cd` in any field (`if:`, `run:`, `env:` or `with:`), which is how the old stable skip worked."""
    assert [base_name(s) for s in deploy if "proxy_cd" in repr(s)] == []
