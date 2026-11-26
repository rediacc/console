"""No CI test job receives an AI provider secret (ruling C42, PLAN-console-ai-providers.md AP13).

CI runs on every push, so a real provider key in a test job spends money on each run; every CI test answers from the scripted provider in packages/shared/src/ai/scripted/ instead.

A job receives a secret through a `secrets.<NAME>` expression, a name in the `secrets:` input of the bws-secrets action, an env key, or a `bws_env exec --profile <p>` whose consumer in .ci/config/secret-supply.json names it. A job receiving an AI provider secret is refused unless it is an operational job: in an `ops-*` or `cd-*` workflow and running no test command. The PR review and the watchdog classifier call a model because calling one is their job, not to test anything; a `cd-*` deploy job only pushes a secret to a Worker (the read-only AI_GATEWAY_LOGS_TOKEN of the nightly credit reconcile), which spends nothing per run (operator ruling ASKED:2026-11-26T07:34Z).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import yaml

from rediacc_ci import paths

if TYPE_CHECKING:
    from pathlib import Path

WORKFLOWS = paths.from_root(".github", "workflows")
SECRET_SUPPLY = paths.from_root(".ci", "config", "secret-supply.json")

#: A secret or env name that carries an AI provider credential, matched as whole underscore-separated words.
AI_SECRET = re.compile(
    r"(?:^|_)(?:ANTHROPIC|OPENAI|AI_GATEWAY|CLAUDE_CODE_OAUTH|GEMINI|GOOGLE_GENERATIVE_AI|MISTRAL"
    r"|DEEPSEEK|OPENROUTER|VERCEL_AI|LITELLM|PORTKEY|CF_AIG|GROQ|XAI)(?:_|$)"
)

#: A run line that executes a test suite or the gate set.
TEST_COMMAND = re.compile(
    r"\b(?:vitest|pytest|playwright|npm (?:run )?test|npm run ci\b|ci:quick|run-account-e2e|go test)"
)

SECRETS_EXPR = re.compile(r"secrets\.([A-Za-z0-9_]+)")
PROFILE_ARG = re.compile(r"--profile[ =]+([A-Za-z0-9_.-]+)")


def _consumer_names() -> dict[str, set[str]]:
    consumers = json.loads(SECRET_SUPPLY.read_text(encoding="utf-8"))["consumers"]
    names: dict[str, set[str]] = {}
    for profile, spec in consumers.items():
        entries = [*spec.get("required", []), *spec.get("optional", [])]
        names[profile] = {part.strip() for entry in entries for part in entry.split(">")}
    return names


def _bws_names(step: dict) -> set[str]:
    if "bws-secrets" not in str(step.get("uses", "")):
        return set()
    listed = str((step.get("with") or {}).get("secrets", ""))
    return {
        part.strip() for line in listed.splitlines() for part in line.split(">") if part.strip()
    }


def received_secrets(workflow: dict, job: dict, consumers: dict[str, set[str]]) -> set[str]:
    """Every secret or env name a job can read."""
    text = json.dumps(job, default=str)
    names = set(SECRETS_EXPR.findall(text))
    names |= set((workflow.get("env") or {}).keys())
    names |= set((job.get("env") or {}).keys())
    for step in job.get("steps") or []:
        names |= set((step.get("env") or {}).keys())
        names |= _bws_names(step)
    for profile in PROFILE_ARG.findall(text):
        names |= consumers.get(profile, set())
    return names


def runs_tests(job: dict) -> bool:
    return any(TEST_COMMAND.search(str(step.get("run", ""))) for step in job.get("steps") or [])


def violations(name: str, workflow: dict, consumers: dict[str, set[str]]) -> list[str]:
    found = []
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        ai = sorted(n for n in received_secrets(workflow, job, consumers) if AI_SECRET.search(n))
        if not ai:
            continue
        operational = name.startswith(("ops-", "cd-")) and not runs_tests(job)
        if not operational:
            found.append("%s job %s receives %s" % (name, job_id, ", ".join(ai)))
    return found


def _load(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), "%s does not parse to a mapping" % path
    return loaded


def test_no_ci_test_job_receives_an_ai_provider_secret() -> None:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert len(files) > 10, "found only %d workflow files under %s" % (len(files), WORKFLOWS)
    consumers = _consumer_names()
    found = [v for path in files for v in violations(path.name, _load(path), consumers)]
    assert found == [], "AI provider secrets reach CI jobs (C42 refuses it):\n" + "\n".join(found)


CONTROL = """
name: control
on: push
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - run: npx vitest run
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
"""


def test_control_a_job_passed_anthropic_api_key_is_red() -> None:
    found = violations("ci-control.yml", yaml.safe_load(CONTROL), {})
    assert found == ["ci-control.yml job unit receives ANTHROPIC_API_KEY"]


def test_control_each_route_a_secret_takes_is_seen() -> None:
    consumers = {"ai-profile": {"OPENAI_API_KEY"}}
    workflow = yaml.safe_load(
        """
jobs:
  by-bws:
    steps:
      - uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            AI_GATEWAY_TOKEN > BWS_GW
  by-profile:
    steps:
      - run: python3 -m rediacc_ci.core.bws_env exec --profile ai-profile -- true
  by-expression:
    steps:
      - run: echo "${{ secrets.DEEPSEEK_KEY }}"
"""
    )
    assert violations("ct-control.yml", workflow, consumers) == [
        "ct-control.yml job by-bws receives AI_GATEWAY_TOKEN",
        "ct-control.yml job by-profile receives OPENAI_API_KEY",
        "ct-control.yml job by-expression receives DEEPSEEK_KEY",
    ]


def test_an_ops_job_that_runs_tests_is_not_operational() -> None:
    workflow = yaml.safe_load(CONTROL)
    assert violations("ops-control.yml", workflow, {}) == [
        "ops-control.yml job unit receives ANTHROPIC_API_KEY"
    ]
    workflow["jobs"]["unit"]["steps"][0]["run"] = "node classify.js"
    assert violations("ops-control.yml", workflow, {}) == []


def test_a_cd_deploy_job_is_operational_only_while_it_runs_no_tests() -> None:
    workflow = yaml.safe_load(CONTROL)
    workflow["jobs"]["unit"]["steps"][0]["run"] = "node push-secrets.js"
    assert violations("cd-control.yml", workflow, {}) == []
    workflow["jobs"]["unit"]["steps"][0]["run"] = "npx vitest run"
    assert violations("cd-control.yml", workflow, {}) == [
        "cd-control.yml job unit receives ANTHROPIC_API_KEY"
    ]


def test_names_that_only_resemble_a_provider_pass() -> None:
    for name in ("CLOUDFLARE_API_TOKEN", "BWS_ACCESS_TOKEN", "MAXAI_FLAG", "OPENAIRE"):
        assert not AI_SECRET.search(name), name
