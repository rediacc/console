"""`rediacc_ci.quality.env_register`, the `npm run env:register` verb, against a fixture repository.

Every case points the verb at a tmp git repository through `REDIACC_CI_ROOT` and hands it a RECORDING runner, so the subprocess steps (the typed `--allow-new`, gen-docs, the three gates) are asserted by their exact argv and order and never run against the real tree. The authored files are real JSON in the fixture, and each refusal case asserts their bytes are unchanged, which is the "refused and writes nothing" half of the contract.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import env_manifest as em
from rediacc_ci.quality import env_register as er

FLAG_WHY = (
    "a fixture flag defaulting to on, so a misspelled name leaves it on: the fail-open direction"
)

HOOK_PY = 'import os\n\nNEW = os.environ.get("WORKLIST_NEW_FLAG", "on")\nOLD = os.environ.get("WORKLIST_OLD", "5")\n'
TOOL_PY = 'import os\n\nSEAM = "NEW_SEAM"\nVALUE = os.environ.get(SEAM)\n'
GATE_TS = "const ledger = process.env.WORKLIST_TS_ONLY || 'x';\n"
QUIET_PY = "X = 1\n"


def _manifest():
    shards: dict[str, list[str]] = {s: [] for s in em.ALL_SHARDS}
    shards["harness"] = ["WORKLIST_OLD"]
    shards["gate-seam"] = ["OLD_SEAM"]
    shards["tombstone"] = ["DEAD_NAME"]
    return {"_comment": ["fixture"], "shards": shards}


def _registry():
    return {
        "$why": ["fixture"],
        "sealed_modules": {},
        "exclusions": {"agent/": "fixture"},
        "kinds": {},
        "names": {"WORKLIST_OLD": {"kind": "tuning", "class": "harness", "defaults": ["'5'"]}},
        "foreign_reads": {},
    }


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    files = {
        em.MANIFEST_REL: json.dumps(_manifest(), indent=2) + "\n",
        ".ci/policy/worklist-env-registry.json": json.dumps(_registry(), indent=2) + "\n",
        em.PYTHON_ENV_REL: json.dumps(
            {"note": "fixture", "modules": {"src/hook.py": ["WORKLIST_OLD"]}}, indent=2
        )
        + "\n",
        "src/hook.py": HOOK_PY,
        "src/tool.py": TOOL_PY,
        "src/gate.ts": GATE_TS,
        "src/quiet.py": QUIET_PY,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    monkeypatch.setenv(paths.ROOT_ENV, str(root))
    return root


class Recorder:
    """The runner seam: records each argv and answers from a script of return codes."""

    def __init__(self, rcs=None):
        self.calls = []
        self.rcs = dict(rcs or {})

    def __call__(self, cmd, _cwd):
        self.calls.append([str(c) for c in cmd])
        for needle, rc in self.rcs.items():
            if any(needle in str(c) for c in cmd):
                return rc, "", "verdict line for %s" % needle
        return 0, "", "green"


def _snapshot(root):
    rels = (em.MANIFEST_REL, ".ci/policy/worklist-env-registry.json", em.PYTHON_ENV_REL)
    return {rel: (root / rel).read_bytes() for rel in rels}


def _json(root, rel):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def test_the_fixture_root_is_the_one_the_verb_sees(repo):
    assert paths.repo_root() == repo.resolve()


def test_a_new_worklist_flag_is_written_rendered_recorded_and_checked(repo):
    rec = Recorder()
    rc = er.main(
        [
            "src/hook.py",
            "WORKLIST_NEW_FLAG",
            "--class",
            "gate-seam",
            "--kind",
            "flag",
            "--default",
            "'on'",
            "--why",
            FLAG_WHY,
        ],
        runner=rec,
    )
    assert rc == 0
    entry = _json(repo, ".ci/policy/worklist-env-registry.json")["names"]["WORKLIST_NEW_FLAG"]
    assert entry == {"kind": "flag", "class": "gate-seam", "defaults": ["'on'"], "why": FLAG_WHY}
    shards = _json(repo, em.MANIFEST_REL)["shards"]
    assert shards["gate-seam"] == ["OLD_SEAM", "WORKLIST_NEW_FLAG"], "rendered into its class shard"
    assert shards["harness"] == ["WORKLIST_OLD"]
    # Steps 4, 5 and 6, in order, with the exact arguments.
    assert rec.calls[0][1:] == [
        str(repo / ".ci/scripts/quality/check_python_env_registry.py"),
        "--write-baseline",
        "--allow-new",
        "src/hook.py:WORKLIST_NEW_FLAG",
    ]
    assert rec.calls[1] == ["npm", "run", "-s", "gen:docs", "--", "--write"]
    assert [pathlib.PurePosixPath(c[1]).name for c in rec.calls[2:]] == list(er.GATES)
    assert len(rec.calls) == 5


def test_control_a_flag_with_no_why_is_refused_and_writes_nothing(repo):
    before = _snapshot(repo)
    rec = Recorder()
    rc = er.main(
        [
            "src/hook.py",
            "WORKLIST_NEW_FLAG",
            "--class",
            "harness",
            "--kind",
            "flag",
            "--default",
            "'on'",
        ],
        runner=rec,
    )
    assert rc == 2
    assert _snapshot(repo) == before, "a refusal must leave every authored file byte-identical"
    assert rec.calls == [], "and must run no step"


def test_control_a_reregistration_under_a_different_class_is_refused(repo):
    before = _snapshot(repo)
    rec = Recorder()
    rc = er.main(["src/hook.py", "WORKLIST_OLD", "--class", "gate-seam"], runner=rec)
    assert rc == 2
    assert _snapshot(repo) == before
    assert rec.calls == []


def test_a_reregistration_under_a_different_shard_is_refused_for_other_names_too(repo):
    before = _snapshot(repo)
    rc = er.main(["src/tool.py", "OLD_SEAM", "--class", "harness"], runner=Recorder())
    assert rc == 2
    assert _snapshot(repo) == before


def test_control_a_non_py_module_skips_allow_new(repo):
    rec = Recorder()
    rc = er.main(
        ["src/gate.ts", "WORKLIST_TS_ONLY", "--class", "gate-seam", "--why", FLAG_WHY], runner=rec
    )
    assert rc == 0
    assert not any("--allow-new" in c for call in rec.calls for c in call), rec.calls
    assert rec.calls[0] == ["npm", "run", "-s", "gen:docs", "--", "--write"]
    foreign = _json(repo, ".ci/policy/worklist-env-registry.json")["foreign_reads"]
    assert foreign == {
        "WORKLIST_TS_ONLY": {"class": "gate-seam", "reader": "src/gate.ts", "why": FLAG_WHY}
    }
    assert "WORKLIST_TS_ONLY" in _json(repo, em.MANIFEST_REL)["shards"]["gate-seam"]


def test_a_foreign_read_needs_a_why_and_takes_no_kind(repo):
    before = _snapshot(repo)
    assert (
        er.main(["src/gate.ts", "WORKLIST_TS_ONLY", "--class", "gate-seam"], runner=Recorder()) == 2
    )
    assert (
        er.main(
            [
                "src/gate.ts",
                "WORKLIST_TS_ONLY",
                "--class",
                "gate-seam",
                "--kind",
                "path",
                "--why",
                FLAG_WHY,
            ],
            runner=Recorder(),
        )
        == 2
    )
    assert _snapshot(repo) == before


def test_an_ordinary_name_goes_into_its_shard_and_is_recorded(repo):
    rec = Recorder()
    assert er.main(["src/tool.py", "NEW_SEAM", "--class", "gate-seam"], runner=rec) == 0
    assert _json(repo, em.MANIFEST_REL)["shards"]["gate-seam"] == ["NEW_SEAM", "OLD_SEAM"]
    assert rec.calls[0][-1] == "src/tool.py:NEW_SEAM", "a constant-indirected read is still typed"


def test_an_ordinary_name_refuses_worklist_only_flags(repo):
    before = _snapshot(repo)
    assert (
        er.main(
            ["src/tool.py", "NEW_SEAM", "--class", "gate-seam", "--kind", "path"], runner=Recorder()
        )
        == 2
    )
    assert _snapshot(repo) == before


def test_a_module_that_does_not_read_the_name_is_refused(repo):
    before = _snapshot(repo)
    rec = Recorder()
    assert er.main(["src/quiet.py", "NEVER_READ", "--class", "harness"], runner=rec) == 2
    assert (
        er.main(
            [
                "src/quiet.py",
                "WORKLIST_NEVER",
                "--class",
                "harness",
                "--kind",
                "tuning",
                "--default",
                "'1'",
            ],
            runner=rec,
        )
        == 2
    )
    assert _snapshot(repo) == before
    assert rec.calls == []


def test_a_default_spelling_the_module_does_not_use_is_refused(repo):
    before = _snapshot(repo)
    rc = er.main(
        [
            "src/hook.py",
            "WORKLIST_NEW_FLAG",
            "--class",
            "harness",
            "--kind",
            "flag",
            "--default",
            "on",
            "--why",
            FLAG_WHY,
        ],
        runner=Recorder(),
    )
    assert rc == 2, "the bare word is not the spelling the gate derives (\"'on'\")"
    assert _snapshot(repo) == before


def test_a_worklist_name_cannot_take_a_non_worklist_class(repo):
    before = _snapshot(repo)
    rc = er.main(
        [
            "src/hook.py",
            "WORKLIST_NEW_FLAG",
            "--class",
            "secret",
            "--kind",
            "flag",
            "--default",
            "'on'",
            "--why",
            FLAG_WHY,
        ],
        runner=Recorder(),
    )
    assert rc == 2
    assert _snapshot(repo) == before


def test_a_tombstone_is_not_resurrected_by_registration(repo):
    (repo / "src/dead.py").write_text('import os\nos.environ.get("DEAD_NAME")\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    before = _snapshot(repo)
    assert er.main(["src/dead.py", "DEAD_NAME", "--class", "harness"], runner=Recorder()) == 2
    assert _snapshot(repo) == before


def test_a_rerun_for_a_registered_recorded_name_writes_nothing(repo):
    """Idempotence: the authored files stay byte-identical and the typed addition is not re-run."""
    before = _snapshot(repo)
    rec = Recorder()
    assert er.main(["src/hook.py", "WORKLIST_OLD", "--class", "harness"], runner=rec) == 0
    assert _snapshot(repo) == before
    assert not any("--allow-new" in c for call in rec.calls for c in call)


@pytest.mark.usefixtures("repo")
def test_a_refused_allow_new_stops_before_the_docs():
    rec = Recorder({"check_python_env_registry.py": 1})
    rc = er.main(["src/tool.py", "NEW_SEAM", "--class", "gate-seam"], runner=rec)
    assert rc == 1
    assert len(rec.calls) == 1, "gen-docs and the gates do not run after a refused addition"


@pytest.mark.usefixtures("repo")
def test_a_red_gate_after_registration_is_exit_1():
    rec = Recorder({"check_env_manifest.py": 1})
    assert er.main(["src/tool.py", "NEW_SEAM", "--class", "gate-seam"], runner=rec) == 1
    assert len(rec.calls) == 5, "every gate still runs, so every verdict is printed"


@pytest.mark.parametrize(
    "argv",
    [
        ["src/tool.py", "NEW_SEAM"],
        ["src/tool.py", "NEW_SEAM", "--class"],
        ["src/tool.py", "NEW_SEAM", "--class", "harness", "--bogus", "x"],
        ["src/tool.py", "--class", "harness"],
        ["src/tool.py", "NEW_SEAM", "--class", "harness", "--class", "gate-seam"],
        ["src/missing.py", "NEW_SEAM", "--class", "harness"],
        ["src/tool.py", "not-a-name", "--class", "harness"],
    ],
)
def test_malformed_invocations_are_refused_and_write_nothing(repo, argv):
    before = _snapshot(repo)
    rec = Recorder()
    assert er.main(argv, runner=rec) == 2
    assert _snapshot(repo) == before
    assert rec.calls == []
