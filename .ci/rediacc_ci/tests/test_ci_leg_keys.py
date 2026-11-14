"""No CI leg holds the production licence-signing key, and every leg that starts an account server builds the renet that verifies it.

agent/plans/PLAN-production-key-only.md D6 (operator ruling 2026-11-09): each leg that starts an account server signs with a keypair minted for that run, and builds renet with that run's public key after the server is up. Before it, the VM/E2E legs mapped the PRODUCTION `ACCOUNT_ED25519_PRIVATE_KEY` from Bitwarden into a public-PR job so that their licences would verify under one shared production-keyed renet artifact.

Two rules over every workflow under .github/workflows, read through YAML so a comment naming the key is not a mapping:

  1. No job mentions `ACCOUNT_ED25519_PRIVATE_KEY` (a bws-secrets line, an `env:` entry, a `secrets.` read), unless WORKER_SECRET_PUSHERS names it: the jobs that write the key into a deployed account Worker, which is the key's consumer. PENDING_CI_LEGS names the CI legs outside this box's files that still map it; each must still map it, so fixing one forces its entry out.
  2. A job that starts the per-run account server (`rediacc_ci.testrun.start_account` without `--emit-pair`) runs `rediacc_ci.infra.build_renet` in a later step, and never installs the shared `renet-test-binary` artifact, whose key is not this run's. RUNTIME_KEY_LEGS names the one job that starts a server and builds no binary, and such a job may not touch a renet binary at all.

Each rule is driven both ways on synthetic workflow text below.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows"
KEY = "ACCOUNT_ED25519_PRIVATE_KEY"
KEY_RE = re.compile(rf"(?<![A-Za-z0-9]){KEY}(?![A-Za-z0-9])")
START = "rediacc_ci.testrun.start_account"
BUILD = "rediacc_ci.infra.build_renet"
SHARED_RENET = "renet-test-binary"

# (workflow file, job id) -> why the job may hold the production key.
WORKER_SECRET_PUSHERS: dict[tuple[str, str], str] = {
    (
        "cd-deploy-worker.yml",
        "deploy",
    ): "pushes the www Worker's secrets, which still read the key; account Workers sign through LICENSE_SIGNER since PLAN-enterprise-isolation S4",
}

# (workflow file, job id) -> the CI leg outside this box's files that still maps the key. Shrink-only.
PENDING_CI_LEGS: dict[tuple[str, str], str] = {}

# (workflow file, job id) -> why the job starts an account server but builds no renet binary.
RUNTIME_KEY_LEGS: dict[tuple[str, str], str] = {
    (
        "ct-tests.yml",
        "test-renet-go",
    ): "leg 1's Go subscription system tests read the exported ACCOUNT_ED25519_PUBLIC_KEY at run time (private/renet/tests/system/subscription_e2e_test.go); no renet binary is built or installed",
}


def _jobs_of(text: str) -> dict[str, dict]:
    data = yaml.safe_load(text) or {}
    return {name: job for name, job in (data.get("jobs") or {}).items() if isinstance(job, dict)}


def _workflows() -> list[tuple[str, str]]:
    return [(path.name, path.read_text()) for path in sorted(WORKFLOWS.glob("*.yml"))]


def key_holders(text: str) -> list[str]:
    """The ids of the jobs whose parsed content names the production private key, plus `<workflow env>` for a top-level `env:` that does."""
    data = yaml.safe_load(text) or {}
    found = ["<workflow env>"] if KEY_RE.search(yaml.safe_dump(data.get("env") or {})) else []
    found += [name for name, job in _jobs_of(text).items() if KEY_RE.search(yaml.safe_dump(job))]
    return found


def _step_text(step: dict) -> str:
    return f"{step.get('uses', '')}\n{step.get('run', '')}"


def _starts_server(step: dict) -> bool:
    run = str(step.get("run", ""))
    return START in run and "--emit-pair" not in run


def leg_findings(name: str, job: dict, runtime_key: bool = False) -> list[str]:
    """Rule 2 for one job: [] when it starts no server, or starts one and builds renet after it (or, for a runtime-key leg, touches no renet binary)."""
    steps = [s for s in job.get("steps") or [] if isinstance(s, dict)]
    starts = [i for i, step in enumerate(steps) if _starts_server(step)]
    if not starts:
        return []
    findings = []
    if any(SHARED_RENET in _step_text(step) for step in steps):
        findings.append(
            f"{name}: installs the shared {SHARED_RENET} artifact, whose key is not this run's"
        )
    if runtime_key:
        if any("RENET_BINARY" in _step_text(step) or BUILD in _step_text(step) for step in steps):
            findings.append(f"{name}: listed as a runtime-key leg but touches a renet binary")
        return findings
    if not any(BUILD in _step_text(step) for step in steps[starts[0] + 1 :]):
        findings.append(f"{name}: starts the account server but builds no renet after it")
    return findings


# --- rule 1, live ---------------------------------------------------------------------------


def test_the_scan_reads_every_workflow() -> None:
    files = _workflows()
    assert len(files) >= 20
    assert sum(len(_jobs_of(text)) for _, text in files) >= 100


@pytest.mark.parametrize(
    ("file", "text"), _workflows(), ids=lambda v: v if v.endswith(".yml") else ""
)
def test_no_ci_leg_maps_the_production_private_key(file: str, text: str) -> None:
    allowed = {job for (f, job) in {**WORKER_SECRET_PUSHERS, **PENDING_CI_LEGS} if f == file}
    offenders = [job for job in key_holders(text) if job not in allowed]
    assert offenders == [], (
        f"{file}: {offenders} map {KEY}; a CI leg mints its own pair (PLAN-production-key-only D6)"
    )


@pytest.mark.parametrize(("file", "job"), sorted({**WORKER_SECRET_PUSHERS, **PENDING_CI_LEGS}))
def test_every_listed_holder_still_holds_the_key(file: str, job: str) -> None:
    """Shrink-only: an entry whose job no longer maps the key is stale and must leave the list."""
    assert job in key_holders((WORKFLOWS / file).read_text()), (
        f"{file} {job} no longer maps {KEY}; drop its entry"
    )


def test_no_workflow_asks_start_account_for_an_env_pair() -> None:
    assert [f for f, text in _workflows() if "--require-env-pair" in text] == []


# --- rule 2, live ---------------------------------------------------------------------------


def _server_jobs() -> list[tuple[str, str, dict]]:
    return [
        (file, name, job)
        for file, text in _workflows()
        for name, job in _jobs_of(text).items()
        if any(_starts_server(s) for s in job.get("steps") or [] if isinstance(s, dict))
    ]


def test_the_scan_sees_the_account_server_legs() -> None:
    assert len(_server_jobs()) >= 12


@pytest.mark.parametrize(
    ("file", "name", "job"), _server_jobs(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_a_leg_that_starts_the_account_server_builds_its_renet_after_it(
    file: str, name: str, job: dict
) -> None:
    assert leg_findings(f"{file} {name}", job, runtime_key=(file, name) in RUNTIME_KEY_LEGS) == []


@pytest.mark.parametrize(("file", "job"), sorted(RUNTIME_KEY_LEGS))
def test_every_runtime_key_leg_still_starts_a_server(file: str, job: str) -> None:
    assert any(_starts_server(s) for s in _jobs_of((WORKFLOWS / file).read_text())[job]["steps"]), (
        f"{file} {job}: stale entry"
    )


# --- controls -------------------------------------------------------------------------------

MAPPED = """
jobs:
  leg:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ACCOUNT_ED25519_PRIVATE_KEY > BWS_ACCOUNT_ED25519_PRIVATE_KEY
      - run: python3 -m rediacc_ci.testrun.start_account --port 4900
        env:
          ACCOUNT_ED25519_PRIVATE_KEY: ${{ env.BWS_ACCOUNT_ED25519_PRIVATE_KEY }}
"""

CLEAN = """
jobs:
  leg:
    runs-on: ubuntu-latest
    steps:
      # A comment naming ACCOUNT_ED25519_PRIVATE_KEY is not a mapping.
      - uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY
      - run: python3 -m rediacc_ci.testrun.start_account --port 4900
"""


def test_control_a_mapped_private_key_is_found() -> None:
    assert key_holders(MAPPED) == ["leg"]


def test_control_each_mapping_form_is_found_alone() -> None:
    fetch_only = MAPPED.split("      - run:", maxsplit=1)[0]
    env_only = CLEAN.replace(
        "--port 4900\n", "--port 4900\n        env:\n          ACCOUNT_ED25519_PRIVATE_KEY: x\n"
    )
    secrets_read = CLEAN.replace(
        "--port 4900\n", "--port 4900 ${{ secrets.ACCOUNT_ED25519_PRIVATE_KEY }}\n"
    )
    workflow_env = "env:\n  ACCOUNT_ED25519_PRIVATE_KEY: x\n" + CLEAN
    assert key_holders(fetch_only) == ["leg"]
    assert key_holders(env_only) == ["leg"]
    assert key_holders(secrets_read) == ["leg"]
    assert key_holders(workflow_env) == ["<workflow env>"]


def test_control_a_leg_without_the_mapping_passes() -> None:
    assert key_holders(CLEAN) == []


def _steps(*runs: str) -> dict:
    return {"steps": [{"uses": r[5:]} if r.startswith("uses:") else {"run": r} for r in runs]}


def test_control_a_server_with_a_later_build_passes() -> None:
    assert leg_findings("j", _steps(f"python3 -m {START} --port 4900", f"python3 -m {BUILD}")) == []


def test_control_a_build_before_the_server_fails() -> None:
    found = leg_findings("j", _steps(f"python3 -m {BUILD}", f"python3 -m {START} --port 4900"))
    assert found == ["j: starts the account server but builds no renet after it"]


def test_control_the_shared_artifact_fails_even_with_a_build() -> None:
    found = leg_findings(
        "j",
        _steps(
            f"python3 -m {START}", f"uses:./.github/actions/{SHARED_RENET}", f"python3 -m {BUILD}"
        ),
    )
    assert found == [f"j: installs the shared {SHARED_RENET} artifact, whose key is not this run's"]


def test_control_emit_pair_is_not_a_server_start() -> None:
    assert leg_findings("j", _steps(f'pair="$(python3 -m {START} --emit-pair)"')) == []


def test_control_a_runtime_key_leg_may_not_touch_a_binary() -> None:
    assert leg_findings("j", _steps(f"python3 -m {START}", "go test ./..."), runtime_key=True) == []
    found = leg_findings(
        "j",
        _steps(f"python3 -m {START}", 'sudo cp "$RENET_BINARY" /usr/bin/renet'),
        runtime_key=True,
    )
    assert found == ["j: listed as a runtime-key leg but touches a renet binary"]


def test_control_the_bws_prefixed_alias_is_found() -> None:
    aliased = CLEAN.replace(
        "ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY",
        "OTHER > BWS_ACCOUNT_ED25519_PRIVATE_KEY",
    )
    assert key_holders(aliased) == ["leg"]


def test_control_a_suffixed_key_name_is_found_and_a_longer_name_is_not() -> None:
    """The lookahead refuses only a following letter or digit, so `ACCOUNT_ED25519_PRIVATE_KEY_DEV` still counts as the key while `ACCOUNT_ED25519_PRIVATE_KEYS` does not."""
    suffixed = CLEAN.replace(
        "ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_ED25519_PRIVATE_KEY_DEV > BWS_X",
    )
    assert key_holders(suffixed) == ["leg"]
    longer = CLEAN.replace(
        "ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_ED25519_PRIVATE_KEYS > BWS_X",
    )
    assert key_holders(longer) == []
