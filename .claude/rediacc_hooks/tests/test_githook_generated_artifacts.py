"""The git-level `pre-commit` check of the generated artifacts declared in `.ci/config/generated-artifacts.json` (`.claude/rediacc_hooks/git/artifacts.py`, called from `githooks.pre_commit`).

WHY IT EXISTS. Three stale generated files on 2026-10-13, each found late: the CLI contract after 76e708dae (40 minutes, a pre-push run), `agent/plans/QUEUE.md` (PR 600's CI, run 38381096702), and a gen-docs region, the one case caught at the commit. The registry makes the third the rule, and a rule that selects commits by declared globs and judges them with a declared checker has three ways to pass without running: the glob never matches, the checker never fails, or the hook never calls it. `check:ci-generated-artifacts` covers the first. This file covers the other two, with REAL git.

TWO HALVES.

  THE MECHANISM, in a tiny repository with a constructed registry and a Python checker that writes a marker file when it runs: refused, allowed, partial (the regeneration on disk and unstaged), a hand-edited output, an excluded input, a checker that exits with an unknown code, one that outruns its budget, a missing `requires` path, a registry that does not parse, a repository with no registry, and a linked build product that must survive the scratch tree's removal. "The checker did not run" is asserted by the marker's ABSENCE, never by timing.

  THE ENROLLED ARTIFACTS, one parametrised set per `when: commit` entry of the REAL registry, in the real tree at HEAD: the entry's own declared `control` is committed through the hook and must be refused naming the entry's `generator`; the same commit with the generator's output must pass with the hook's own "verified clean" line for that entry; a commit of an unrelated path must run no checker. A new entry is covered by being enrolled, with no edit here.

THE CONTROL. Every refusing case also runs against a copy of the hooks whose `pre_commit` is planted to always allow, where it must FAIL (`test_githook_gen_docs.py` states why; the fixture and the plant are that file's). A case that passes against an always-allow hook proves nothing about the hook.

WHAT THE REAL HALF NEEDS. The enrolled checkers run the repository's own generators, so the fixture links in the working tree's untracked build products the registry names (`links` and `requires`). One that is missing fails the test with the registry's own fix command; it is never skipped.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
REGISTRY_REL = ".ci/config/generated-artifacts.json"
STALE = "leaves a generated artifact stale"
LABEL = "generated-artifacts pre-commit"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GD = _load("githook_gen_docs_fixture", pathlib.Path(__file__).with_name("test_githook_gen_docs.py"))
GA = _load("githook_artifacts_under_test", HOOKS / "artifacts.py")


def _registry() -> dict:
    return json.loads((REPO_ROOT / REGISTRY_REL).read_text(encoding="utf-8"))


def _enrolled() -> list[dict]:
    return [a for a in _registry()["artifacts"] if a["when"] == "commit"]


def _literal(globs: list[str]) -> list[str]:
    return [g for g in globs if not any(ch in g for ch in "*?[") and (REPO_ROOT / g).is_file()]


def _planted_hooks(dest: pathlib.Path) -> pathlib.Path:
    """A copy of the hooks whose `pre_commit` always allows, laid out as `githooks.py` expects (`commit_policy.py` one level up)."""
    hooks = dest / ".claude" / "rediacc_hooks" / "git"
    shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(HOOKS.parent / "commit_policy.py", hooks.parent / "commit_policy.py")
    planted = hooks / "githooks.py"
    text = planted.read_text(encoding="utf-8")
    assert text.count(GD.PLANT_OLD) == 1, "the always-allow plant no longer applies"
    planted.write_text(text.replace(GD.PLANT_OLD, GD.PLANT_NEW), encoding="utf-8")
    return hooks


def test_the_registry_enrols_something():
    """Zero enrolled entries would make every parametrised case below collect nothing and pass."""
    artifacts, problems = GA.parse((REPO_ROOT / REGISTRY_REL).read_text(encoding="utf-8"))
    assert problems == [], problems
    ids = [a.id for a in GA.enrolled(artifacts)]
    assert "cli-contract" in ids, ids
    assert "plan-renders" in ids, ids


# --------------------------------------------------------------------------- the mechanism, in a tiny repository

CHECKER = """import pathlib
import sys
import time

pathlib.Path({marker!r}).write_text("ran\\n", encoding="utf-8")
if not pathlib.Path("build/sentinel").is_file():
    print("the linked build product is not in the scratch tree", file=sys.stderr)
    sys.exit(4)
src = pathlib.Path("src/a.txt").read_text(encoding="utf-8")
if "EXIT3" in src:
    print("the checker could not run", file=sys.stderr)
    sys.exit(3)
if "SLEEP" in src:
    time.sleep(30)
out = pathlib.Path("out/gen.txt")
if out.is_file() and out.read_text(encoding="utf-8") == src.upper():
    sys.exit(0)
print("out/gen.txt is not the upper-case of src/a.txt", file=sys.stderr)
sys.exit(1)
"""

GENERATOR = """import pathlib

src = pathlib.Path("src/a.txt").read_text(encoding="utf-8")
pathlib.Path("out/gen.txt").write_text(src.upper(), encoding="utf-8")
"""


def _tiny_registry(**commit_over) -> str:
    commit = {
        "check": ["python3", "tools/check.py"],
        "budget_s": 20,
        "links": ["build"],
        "requires": [{"path": "build/sentinel", "fix": "make the-build-product"}],
        "control": {"kind": "replace", "path": "src/a.txt", "old": "alpha", "new": "beta"},
    }
    commit.update(commit_over)
    return json.dumps(
        {
            "schema": 1,
            "artifacts": [
                {
                    "id": "tiny",
                    "title": "Tiny artifact",
                    "when": "commit",
                    "inputs": ["src/**"],
                    "inputs_exclude": ["src/notes/**"],
                    "outputs": ["out/gen.txt"],
                    "generator": "python3 tools/gen.py",
                    "gate": "check:tiny",
                    "commit": commit,
                }
            ],
        }
    )


class Tiny:
    """A repository holding one enrolled artifact, the real hooks, and a planted always-allow copy beside it."""

    def __init__(self, base: pathlib.Path):
        self.base = base
        self.repo = base / "tiny"
        self.marker = base / "checker-ran.marker"
        self.planted = _planted_hooks(base / "planted")

    def build(self, registry: str | None = None) -> None:
        GD._git(self.base, "init", "-q", "-b", GD.BRANCH, str(self.repo))
        files = {
            REGISTRY_REL: registry if registry is not None else _tiny_registry(),
            "tools/check.py": CHECKER.format(marker=str(self.marker)),
            "tools/gen.py": GENERATOR,
            "src/a.txt": "alpha\n",
            "src/notes/n.txt": "a note no artifact reads\n",
            "out/gen.txt": "ALPHA\n",
            "other/z.txt": "unrelated\n",
            ".gitignore": "build/\n",
        }
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.repo / "build").mkdir()
        (self.repo / "build" / "sentinel").write_text("built\n", encoding="utf-8")
        GD._git(self.repo, "add", "--", *files)
        GD._git(self.repo, "commit", "-q", "-m", "base", env=GD._env(COMMIT_POLICY_OK="1"))
        self.use(HOOKS)

    def use(self, hooks: pathlib.Path) -> None:
        GD._git(self.repo, "config", "core.hooksPath", str(hooks))

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def generate(self) -> None:
        subprocess.run([sys.executable, "tools/gen.py"], cwd=self.repo, check=True, timeout=60)

    def commit(self, *paths: str) -> tuple[subprocess.CompletedProcess, bool, bool]:
        """(the commit, whether HEAD moved, whether the checker ran). The marker is cleared first and the repository is put back after."""
        self.marker.unlink(missing_ok=True)
        head = GD._git(self.repo, "rev-parse", "HEAD").stdout.strip()
        msg = self.base / "msg"
        msg.write_text("test(fixture): tiny\n", encoding="utf-8")
        GD._git(self.repo, "add", "--", *paths)
        proc = GD._git(
            self.repo,
            "commit",
            "-F",
            str(msg),
            "--",
            *paths,
            env=GD._env(GEN_DOCS_PRECOMMIT_VERBOSE="1"),
            check=False,
        )
        moved = GD._git(self.repo, "rev-parse", "HEAD").stdout.strip() != head
        ran = self.marker.is_file()
        GD._git(self.repo, "reset", "-q", "--hard", head)
        return proc, moved, ran


@pytest.fixture
def tiny(tmp_path):
    t = Tiny(tmp_path)
    t.build()
    hooks = _load("githooks_for_scratch", HOOKS / "githooks.py")
    scratch = hooks.scratch_for(GD._git(t.repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    yield t
    shutil.rmtree(scratch, ignore_errors=True)


def tiny_refused(t: Tiny) -> tuple[bool, str]:
    t.write("src/a.txt", "beta\n")
    proc, moved, ran = t.commit("src/a.txt")
    ok = (
        proc.returncode != 0
        and not moved
        and ran
        and STALE in proc.stderr
        and "Tiny artifact" in proc.stderr
        and "python3 tools/gen.py" in proc.stderr
        and "out/gen.txt" in proc.stderr
        and "src/a.txt" in proc.stderr
        and "not the upper-case" in proc.stderr
    )
    return ok, proc.stderr


def tiny_partial(t: Tiny) -> tuple[bool, str]:
    """The regeneration is on disk and NOT in the commit: a working-tree check would pass it."""
    t.write("src/a.txt", "beta\n")
    t.generate()
    proc, moved, ran = t.commit("src/a.txt")
    return proc.returncode != 0 and not moved and ran and STALE in proc.stderr, proc.stderr


def tiny_output_hand_edit(t: Tiny) -> tuple[bool, str]:
    """An output staged alone, edited by hand: no input moved, and the artifact is stale all the same."""
    t.write("out/gen.txt", "ALPHA, EDITED BY HAND\n")
    proc, moved, ran = t.commit("out/gen.txt")
    return proc.returncode != 0 and not moved and ran and STALE in proc.stderr, proc.stderr


def tiny_unknown_exit(t: Tiny) -> tuple[bool, str]:
    t.write("src/a.txt", "EXIT3\n")
    proc, moved, ran = t.commit("src/a.txt")
    ok = (
        proc.returncode != 0
        and not moved
        and ran
        and "UNCHECKED" in proc.stderr
        and "exited 3" in proc.stderr
        and STALE not in proc.stderr
    )
    return ok, proc.stderr


def tiny_missing_requirement(t: Tiny) -> tuple[bool, str]:
    shutil.rmtree(t.repo / "build")
    t.write("src/a.txt", "beta\n")
    try:
        proc, moved, ran = t.commit("src/a.txt")
    finally:
        (t.repo / "build").mkdir()
        (t.repo / "build" / "sentinel").write_text("built\n", encoding="utf-8")
    ok = (
        proc.returncode != 0
        and not moved
        and not ran
        and "UNCHECKED" in proc.stderr
        and "make the-build-product" in proc.stderr
    )
    return ok, proc.stderr


REFUSING = [
    tiny_refused,
    tiny_partial,
    tiny_output_hand_edit,
    tiny_unknown_exit,
    tiny_missing_requirement,
]


@pytest.mark.parametrize("case", REFUSING, ids=[c.__name__ for c in REFUSING])
def test_mechanism_refuses(tiny, case):
    ok, detail = case(tiny)
    assert ok, "%s failed against the real hook:\n%s" % (case.__name__, detail[-2500:])


@pytest.mark.parametrize("case", REFUSING, ids=[c.__name__ for c in REFUSING])
def test_mechanism_case_fails_against_an_always_allow_hook(tiny, case):
    """The control: each refusing case must stop passing when the hook allows everything."""
    tiny.use(tiny.planted)
    ok, detail = case(tiny)
    assert not ok, "%s PASSED against an always-allow hook:\n%s" % (case.__name__, detail[-1500:])


def test_mechanism_allows_the_regenerated_commit_and_says_what_it_ran(tiny):
    tiny.write("src/a.txt", "beta\n")
    tiny.generate()
    proc, moved, ran = tiny.commit("src/a.txt", "out/gen.txt")
    assert proc.returncode == 0, proc.stderr
    assert moved
    assert ran, "the commit was allowed without the checker running"
    assert "%s: tiny: 2 of 2 staged path(s) are its inputs" % LABEL in proc.stderr, proc.stderr
    assert "verified clean" in proc.stderr
    assert "of a 20s budget" in proc.stderr


def test_mechanism_clean_report_is_absent_from_an_always_allow_hook(tiny):
    """The control for every "allowed" assertion in this file: the same regenerated commit lands under the planted hook with no checker run and no report, so the report is evidence that the check ran."""
    tiny.use(tiny.planted)
    tiny.write("src/a.txt", "beta\n")
    tiny.generate()
    proc, moved, ran = tiny.commit("src/a.txt", "out/gen.txt")
    assert proc.returncode == 0, proc.stderr
    assert moved
    assert not ran, "the planted hook ran the checker, so it is not an always-allow hook"
    assert LABEL not in proc.stderr, proc.stderr


def test_mechanism_runs_no_checker_when_no_input_is_staged(tiny):
    """The fast path, proved by the marker's absence. The line it prints is the opposite control: the hook did look."""
    tiny.write("other/z.txt", "still unrelated\n")
    proc, moved, ran = tiny.commit("other/z.txt")
    assert proc.returncode == 0, proc.stderr
    assert moved
    assert not ran, "the checker ran for a commit that stages none of its inputs"
    assert "none an input of the 1 enrolled artifact(s)" in proc.stderr, proc.stderr


def test_mechanism_skips_an_excluded_input(tiny):
    tiny.write("src/notes/n.txt", "an edited note\n")
    proc, moved, ran = tiny.commit("src/notes/n.txt")
    assert proc.returncode == 0, proc.stderr
    assert moved
    assert not ran, "inputs_exclude did not keep the checker from running"


def test_mechanism_leaves_the_linked_build_product_in_place(tiny):
    """The scratch tree holds a LINK to the working tree's build product; removing the scratch tree must unlink it, never follow it."""
    tiny.write("src/a.txt", "beta\n")
    tiny.generate()
    proc, _moved, ran = tiny.commit("src/a.txt", "out/gen.txt")
    assert proc.returncode == 0, proc.stderr
    assert ran
    assert (tiny.repo / "build" / "sentinel").read_text(encoding="utf-8") == "built\n"


def test_mechanism_refuses_a_run_past_its_budget(tmp_path):
    t = Tiny(tmp_path)
    t.build(_tiny_registry(budget_s=1))
    t.write("src/a.txt", "SLEEP\n")
    proc, moved, ran = t.commit("src/a.txt")
    assert proc.returncode != 0, "a checker that outran its budget was waved through"
    assert not moved
    assert ran
    assert "UNCHECKED" in proc.stderr, proc.stderr
    assert "exceeded its 1 s budget" in proc.stderr


def test_mechanism_refuses_a_registry_it_cannot_parse(tmp_path):
    """An enrolled entry with no budget: the hook cannot know how long to wait, and a registry it cannot use is never a pass."""
    t = Tiny(tmp_path)
    t.build()
    broken = json.loads(_tiny_registry())
    del broken["artifacts"][0]["commit"]["budget_s"]
    t.write(REGISTRY_REL, json.dumps(broken))
    proc, moved, ran = t.commit(REGISTRY_REL)
    assert proc.returncode != 0, "a commit carrying a broken registry was waved through"
    assert not moved
    assert not ran
    assert "UNCHECKED" in proc.stderr, proc.stderr
    assert "budget_s" in proc.stderr


def test_a_repository_without_the_registry_is_left_alone(tmp_path):
    repo = tmp_path / "plain"
    GD._git(tmp_path, "init", "-q", "-b", GD.BRANCH, str(repo))
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    GD._git(repo, "add", "a.txt")
    GD._git(repo, "commit", "-q", "-m", "base", env=GD._env(COMMIT_POLICY_OK="1"))
    GD._git(repo, "config", "core.hooksPath", str(HOOKS))
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    msg = tmp_path / "msg"
    msg.write_text("test(fixture): plain\n", encoding="utf-8")
    proc = GD._git(
        repo,
        "commit",
        "-F",
        str(msg),
        "--",
        "a.txt",
        env=GD._env(GEN_DOCS_PRECOMMIT_VERBOSE="1"),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert LABEL not in proc.stderr, "the hook judged a repository that carries no registry"


# --------------------------------------------------------------------------- the enrolled artifacts, in the real tree


def _overlay() -> tuple[str, ...]:
    """The working-tree files under test here: the registry, each enrolled check script, and each enrolled input that is a single tracked file (the checkers' own code)."""
    out = [REGISTRY_REL]
    for entry in _enrolled():
        out += [w for w in entry["commit"]["check"] if (REPO_ROOT / w).is_file()]
        out += _literal(entry["inputs"])
    return tuple(dict.fromkeys(out))


def _link_build_products(repo: pathlib.Path) -> None:
    """Link the registry's `links` and `requires` paths from this checkout into the fixture. A required one that this checkout lacks fails the test with the registry's fix."""
    for entry in _enrolled():
        block = entry["commit"]
        for need in block.get("requires", []):
            if not os.path.lexists(REPO_ROOT / need["path"]):
                pytest.fail(
                    "`%s` needs `%s` in this checkout to run its checker; create it: %s"
                    % (entry["id"], need["path"], need["fix"])
                )
        for rel in [*block.get("links", []), *(n["path"] for n in block.get("requires", []))]:
            src, dst = REPO_ROOT / rel, repo / rel
            if os.path.lexists(dst) or not os.path.lexists(src):
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)


def _prefetch_main_plans() -> int:
    """Make every `agent/plans` blob of origin/main present in this checkout, and return how many were absent.

    The fixture reaches this checkout's objects through alternates and has no promisor remote of its own, so in a blobless clone (CI's `filter: blob:none`) a plan blob of origin/main that was never fetched is unreadable there: `git show origin/main:<plan>` fails, `check_plan_record.main_view` returns None, and RF refuses every fully ticked plan instead of warning (run 41318476899). One batched fetch by oid, which a full clone never needs."""
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "origin/main", "--", "agent/plans"],
        capture_output=True,
        text=True,
        check=False,
    )
    oids = [row.split()[2] for row in listed.stdout.splitlines() if len(row.split()) >= 3]
    if not oids:
        return 0
    checked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="\n".join(oids) + "\n",
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    missing = [r.split()[0] for r in checked.stdout.splitlines() if r.endswith(" missing")]
    if missing:
        # A slow or failed fetch must not error the module-scoped fixture: the plan-renders case alone depends on these blobs, and its own failure names them.
        try:
            got = subprocess.run(
                [
                    "git",
                    "-C",
                    str(REPO_ROOT),
                    "fetch",
                    "-q",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "origin",
                    *missing,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            if got.returncode != 0:
                print("plan blob prefetch failed: %s" % got.stderr.strip(), file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("plan blob prefetch timed out", file=sys.stderr)
    return len(missing)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    _prefetch_main_plans()
    w = GD.World(tmp_path_factory.mktemp("githook-artifacts"), extra_overlay=_overlay())
    w.build()
    _link_build_products(w.repo)
    hooks = _load("githooks_for_world", w.real_hooks / "githooks.py")
    scratch = hooks.scratch_for(GD._git(w.repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    yield w
    shutil.rmtree(scratch, ignore_errors=True)


def _plant(w, entry: dict) -> str:
    """Apply the entry's declared control in the fixture and return the path to commit."""
    control = entry["commit"]["control"]
    path = w.repo / control["path"]
    if control["kind"] == "replace":
        text = path.read_text(encoding="utf-8")
        assert text.count(control["old"]) == 1, (
            "the control anchor of `%s` occurs %d time(s) in %s; check:ci-generated-artifacts names the fix"
            % (entry["id"], text.count(control["old"]), control["path"])
        )
        path.write_text(text.replace(control["old"], control["new"]), encoding="utf-8")
    else:
        assert not path.exists(), "the create control's path already exists: %s" % control["path"]
        path.write_text(control["content"], encoding="utf-8")
        GD._git(w.repo, "add", "--", control["path"])
    return control["path"]


def _changed(w) -> list[str]:
    out = GD._git(w.repo, "status", "--porcelain", "--untracked-files=all", "-z").stdout
    return [row[3:] for row in out.split("\0") if row]


def enrolled_refused(w, entry: dict, tag: str) -> tuple[bool, str]:
    head = w.head()
    rel = _plant(w, entry)
    proc = w.commit(rel, label="%s refused%s" % (entry["id"], tag))
    moved = w.head() != head
    w.reset(head)
    ok = (
        proc.returncode != 0
        and not moved
        and STALE in proc.stderr
        and "(`%s`)" % entry["id"] in proc.stderr
        and entry["generator"] in proc.stderr
        and rel in proc.stderr
    )
    return ok, proc.stderr


def enrolled_allowed(w, entry: dict, tag: str) -> tuple[bool, str]:
    """Resets the fixture to its starting commit even when an assertion fires midway: the module-scoped world is shared, so a planted control left behind made the next case fail on `the create control's path already exists`."""
    head = w.head()
    try:
        return _enrolled_allowed(w, entry, tag)
    finally:
        w.reset(head)


def _enrolled_allowed(w, entry: dict, tag: str) -> tuple[bool, str]:
    """The same control, then the entry's own generator, then the commit of both. When the doc-region check refuses first, because the artifact is itself a provider input (the gate lock is), the regions are regenerated and the commit is made again with them."""
    head = w.head()
    rel = _plant(w, entry)
    made = subprocess.run(
        shlex.split(entry["generator"]),
        cwd=w.repo,
        capture_output=True,
        text=True,
        env=GD._env(),
        check=False,
        timeout=600,
    )
    assert made.returncode == 0, "`%s` failed in the fixture:\n%s" % (
        entry["generator"],
        (made.stderr or made.stdout)[-2000:],
    )
    outputs = [p for p in _changed(w) if GA.matches(p, tuple(entry["outputs"]))]
    assert outputs, (
        "`%s` changed none of its declared outputs, so the control plants nothing"
        % (entry["generator"])
    )
    GD._git(w.repo, "add", "--", *outputs)
    proc = w.commit(rel, *outputs, label="%s allowed%s" % (entry["id"], tag))
    if proc.returncode != 0 and "leaves a generated doc region stale" in proc.stderr:
        wrote = GD._gen(w.repo, "--write")
        assert wrote.returncode == 0, wrote.stderr
        docs = re.findall(r"^wrote (\S+)", wrote.stdout, re.MULTILINE)
        assert docs, "the doc-region check refused and gen-docs --write wrote nothing"
        GD._git(w.repo, "add", "--", *docs)
        proc = w.commit(rel, *outputs, *docs, label="%s allowed%s" % (entry["id"], tag))
    moved = w.head() != head
    w.reset(head)
    ok = (
        proc.returncode == 0
        and moved
        and "%s: %s: " % (LABEL, entry["id"]) in proc.stderr
        and "verified clean" in proc.stderr
    )
    return ok, proc.stderr


ENROLLED = _enrolled()
ENROLLED_CASES = [enrolled_refused, enrolled_allowed]


@pytest.mark.parametrize("entry", ENROLLED, ids=[e["id"] for e in ENROLLED])
@pytest.mark.parametrize("case", ENROLLED_CASES, ids=[c.__name__ for c in ENROLLED_CASES])
def test_enrolled_artifact_against_the_real_hook(world, entry, case):
    world.use(world.real_hooks)
    ok, detail = case(world, entry, "")
    assert ok, "%s of `%s` failed against the real hook:\n%s" % (
        case.__name__,
        entry["id"],
        detail[-3000:],
    )


@pytest.mark.parametrize("entry", ENROLLED, ids=[e["id"] for e in ENROLLED])
def test_enrolled_refusal_fails_against_an_always_allow_hook(world, entry):
    """The control, per entry. `enrolled_allowed` needs none of its own: it passes only on the hook's own "verified clean" line naming the entry, which an always-allow hook never prints (the mechanism half proves that against the planted copy)."""
    world.use(world.planted_hooks)
    try:
        ok, detail = enrolled_refused(world, entry, " (planted)")
    finally:
        world.use(world.real_hooks)
    assert not ok, "the refusal of `%s` PASSED against an always-allow hook:\n%s" % (
        entry["id"],
        detail[-1500:],
    )


def test_no_enrolled_checker_runs_for_an_unrelated_path(world):
    world.use(world.real_hooks)
    head = world.head()
    rel = "zz-unrelated-note.txt"
    (world.repo / rel).write_text("nothing any artifact is generated from\n", encoding="utf-8")
    GD._git(world.repo, "add", "--", rel)
    proc = world.commit(rel, label="unrelated", GEN_DOCS_PRECOMMIT_VERBOSE="1")
    moved = world.head() != head
    world.reset(head)
    assert proc.returncode == 0, proc.stderr
    assert moved
    assert "none an input of the %d enrolled artifact(s)" % len(ENROLLED) in proc.stderr, (
        proc.stderr
    )
    for entry in ENROLLED:
        assert "%s: %s: " % (LABEL, entry["id"]) not in proc.stderr, proc.stderr
