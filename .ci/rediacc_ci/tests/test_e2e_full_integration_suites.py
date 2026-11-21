"""The E2E Full Integration job's suite lists, as three hand-kept matrix `suites:` lists.

Invariant (review 99a1416d.1): every full-integration suite runs exactly once per distro. 23a and 23b run on ubuntu-24.04 only (the CLI routing logic is distro-agnostic); 12a, 12b, 12d and 13b run on each distro. A suite dropped from a list, or doubled within a distro, fails here rather than going unnoticed until a leg is missing from a run.
"""

import collections
import copy
import pathlib

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ct-tests.yml"
JOB = "test-e2e-full-integration"

UBUNTU = "ubuntu-24.04"
EXPECTED = {
    UBUNTU: {
        "23a-cli-migrate-routing.test.ts",
        "23b-cli-migrate-ordering.test.ts",
        "12a-full-integration-repository.test.ts",
        "12b-full-integration-checkpoint.test.ts",
        "12d-full-integration-multi-machine.test.ts",
        "13b-live-fork-checkpoint.test.ts",
    },
    "fedora-43": {
        "12a-full-integration-repository.test.ts",
        "12b-full-integration-checkpoint.test.ts",
        "12d-full-integration-multi-machine.test.ts",
        "13b-live-fork-checkpoint.test.ts",
    },
}


def suites_per_distro(workflow: dict) -> dict[str, collections.Counter]:
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for leg in workflow["jobs"][JOB]["strategy"]["matrix"]["include"]:
        out[leg["os-image"]].update(leg["suites"].split())
    return out


def problems(workflow: dict) -> list[str]:
    found = []
    got = suites_per_distro(workflow)
    for distro in sorted(set(EXPECTED) | set(got)):
        counts = got.get(distro, collections.Counter())
        want = EXPECTED.get(distro, set())
        found += [f"{distro}: {s} is missing" for s in sorted(want - set(counts))]
        found += [f"{distro}: {s} is not expected" for s in sorted(set(counts) - want)]
        found += [f"{distro}: {s} runs {n} times" for s, n in sorted(counts.items()) if n > 1]
    return found


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_every_suite_runs_exactly_once_per_distro():
    assert problems(load()) == []


def test_a_dropped_suite_is_found():
    wf = copy.deepcopy(load())
    leg = wf["jobs"][JOB]["strategy"]["matrix"]["include"][0]
    leg["suites"] = leg["suites"].replace("12a-full-integration-repository.test.ts", "")
    assert problems(wf) == [f"{UBUNTU}: 12a-full-integration-repository.test.ts is missing"]


def test_a_doubled_suite_is_found():
    wf = copy.deepcopy(load())
    wf["jobs"][JOB]["strategy"]["matrix"]["include"][1]["suites"] += (
        " 23a-cli-migrate-routing.test.ts"
    )
    assert problems(wf) == [f"{UBUNTU}: 23a-cli-migrate-routing.test.ts runs 2 times"]
