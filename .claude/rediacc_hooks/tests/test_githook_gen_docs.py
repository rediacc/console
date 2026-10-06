"""The git-level `pre-commit` hook that refuses a commit leaving a generated doc region stale (`.claude/rediacc_hooks/git/githooks.py`, `pre_commit`).

WHY IT EXISTS. On branch 1006-1, 1fb9eefe7 edited `.ci/policy/.audit-prod-allowlist` and 7f2ece4c1 edited `.ci/config/env-manifest.json`, both inputs of `scripts/gen/gen-docs.ts`, and neither re-ran `--write`. Each miss surfaced only in the 17-minute pre-push, as check:ci-doc-region-parity plus three test_gate_docs_gen failures, and each needed a fix commit.

WHAT IS PROVED, with REAL git in a throwaway repository whose `core.hooksPath` points at the hooks:

  refused       a provider input staged without its regeneration.
  allowed       the same input staged WITH its regeneration, and the verify path visibly ran.
  partial       the input committed by pathspec while the regenerated file sits unstaged in the
                working tree: refused, because the hook judges the COMMIT's tree, not the disk.
  fast path     an unrelated path: allowed, and the hook says none of its paths is an input.
  stale inputs  a provider module staged with a read its `inputs` do not declare: refused,
                because a staged generator module makes the hook re-run the input trace.

THE CONTROL. Every case runs twice: against the real hooks, where it must pass, and against a copy whose `pre_commit` is planted to always allow, where it must FAIL. A case that still passes against an always-allow hook proves nothing about the hook, which is why the allowed and fast-path cases assert on the hook's own report and not only on the exit code.

THE FIXTURE IS THE REAL TREE AT HEAD, plus the working-tree copies of the files under test (the git hooks and the generator's import closure), so the cases exercise the hook as it stands in this checkout. Objects come through `alternates`, so nothing is copied but the checkout; nothing here touches this checkout's index, config or files.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS_REL = pathlib.Path(".claude/rediacc_hooks/git")
GEN = "scripts/gen/gen-docs.ts"
ENV_MANIFEST = ".ci/config/env-manifest.json"
REGISTRY = "scripts/data/doc-registry.md"
PROVIDERS = "scripts/lib/doc-providers.ts"
BRANCH = "0101-1"

# The planted defect: `pre_commit` allows everything. Asserted to apply exactly once, so a rename cannot turn the control into a copy of the real hook.
PLANT_OLD = "def pre_commit(_argv: list[str]) -> int:\n"
PLANT_NEW = PLANT_OLD + "    return 0\n"

TIMINGS: dict[str, float] = {}


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(**extra: str) -> dict[str, str]:
    drop = {
        "COMMIT_POLICY_OK",
        "GEN_DOCS_OVERRIDE_FILE",
        "GIT_INDEX_FILE",
        "GIT_DIR",
        "GIT_WORK_TREE",
    }
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    env.update(extra)
    return env


def _git(repo: pathlib.Path, *args: str, env: dict | None = None, check: bool = True):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env or _env(),
        check=False,
        timeout=600,
    )
    if check and proc.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), proc.stderr.strip()))
    return proc


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is not on PATH; install Node 24 (.devcontainer/toolchain.env pins it)")
    assert node is not None
    return node


def _gen(repo: pathlib.Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_node(), str(repo / GEN), *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
        timeout=600,
    )


def _closure(root: pathlib.Path) -> list[str]:
    """The generator and its relative imports, from the WORKING TREE (the overlay is what is under test)."""
    hooks = _load("githooks_for_closure", REPO_ROOT / HOOKS_REL / "githooks.py")
    seen: list[str] = []
    queue = [GEN]
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.append(rel)
        text = (root / rel).read_text(encoding="utf-8")
        for match in hooks._IMPORT_RE.finditer(text):
            base = os.path.normpath(os.path.join(os.path.dirname(rel), match.group(1)))
            hit = next(
                c
                for c in (base, base.removesuffix(".js") + ".ts", base + ".ts")
                if (root / c).is_file()
            )
            queue.append(hit)
    return sorted(seen)


class World:
    def __init__(self, base: pathlib.Path):
        self.base = base
        self.repo = base / "fx"
        self.real_hooks = self.repo / HOOKS_REL
        # Beside the real directory, inside the fixture: githooks.py loads ../commit_policy.py and roots itself two levels up, so the copy needs the same layout. Untracked, so no commit and no provider ever sees it.
        self.planted_hooks = self.repo / ".claude" / "rediacc_hooks" / "git-planted"

    def build(self) -> None:
        head = _git(REPO_ROOT, "rev-parse", "HEAD").stdout.strip()
        common = _git(
            REPO_ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
        _git(self.base, "init", "-q", "-b", BRANCH, str(self.repo))
        (self.repo / ".git" / "objects" / "info" / "alternates").write_text(
            os.path.join(common, "objects") + "\n", encoding="utf-8"
        )
        _git(self.repo, "read-tree", head)
        _git(self.repo, "-c", "checkout.workers=-1", "checkout-index", "-a", "-u")
        overlay = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted((REPO_ROOT / HOOKS_REL).iterdir())
            if p.is_file() and not p.name.endswith(".pyc")
        ] + _closure(REPO_ROOT)
        for rel in overlay:
            dst = self.repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dst)
        _git(self.repo, "add", "--", *overlay)
        wrote = _gen(self.repo, "--write")
        assert wrote.returncode == 0, wrote.stderr
        regenerated = re.findall(r"^wrote (\S+)", wrote.stdout, re.MULTILINE)
        if regenerated:
            _git(self.repo, "add", "--", *regenerated)
        _git(self.repo, "commit", "-q", "-m", "base", env=_env(COMMIT_POLICY_OK="1"))
        clean = _gen(self.repo)
        assert clean.returncode == 0, "the fixture's own regions are not clean:\n" + clean.stderr
        _git(self.repo, "config", "core.hooksPath", str(self.real_hooks))
        shutil.copytree(
            self.real_hooks, self.planted_hooks, ignore=shutil.ignore_patterns("__pycache__")
        )
        planted = self.planted_hooks / "githooks.py"
        text = planted.read_text(encoding="utf-8")
        assert text.count(PLANT_OLD) == 1, "the always-allow plant no longer applies"
        planted.write_text(text.replace(PLANT_OLD, PLANT_NEW), encoding="utf-8")

    def use(self, hooks: pathlib.Path) -> None:
        _git(self.repo, "config", "core.hooksPath", str(hooks))

    def head(self) -> str:
        return _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def reset(self, sha: str) -> None:
        """Back to `sha`, index and files, in the fixture only."""
        _git(self.repo, "reset", "-q", "--hard", sha)

    def commit(self, *paths: str, label: str, **extra: str) -> subprocess.CompletedProcess:
        msg = self.base / "msg"
        msg.write_text("test(fixture): %s\n" % label, encoding="utf-8")
        started = time.monotonic()
        proc = _git(
            self.repo, "commit", "-F", str(msg), "--", *paths, env=_env(**extra), check=False
        )
        TIMINGS.setdefault(label, time.monotonic() - started)
        return proc

    def plant_env_manifest_name(self) -> None:
        path = self.repo / ENV_MANIFEST
        text = path.read_text(encoding="utf-8")
        anchor = re.search(r'"shards"\s*:\s*\{\s*"[^"]+"\s*:\s*\[', text)
        assert anchor is not None, "the env-manifest shards anchor moved"
        path.write_text(
            text[: anchor.end()] + '\n      "ZZ_GEN_DOCS_HOOK_PROBE",' + text[anchor.end() :],
            encoding="utf-8",
        )


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    w = World(tmp_path_factory.mktemp("githook-gen-docs"))
    w.build()
    hooks = _load("githooks_under_test", w.real_hooks / "githooks.py")
    scratch = hooks.scratch_for(_git(w.repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    yield w
    shutil.rmtree(scratch, ignore_errors=True)
    print("\ntimings (s): " + ", ".join("%s %.2f" % (k, v) for k, v in TIMINGS.items()))


# --------------------------------------------------------------------------- the cases ---------------------------------------------------------------------------
# Each returns (passed, detail) instead of asserting, so the same case can be run against the planted hook and be required to FAIL there.


def case_refused(w: World, tag: str) -> tuple[bool, str]:
    head = w.head()
    w.plant_env_manifest_name()
    proc = w.commit(ENV_MANIFEST, label="refused" + tag)
    moved = w.head() != head
    w.reset(head)
    ok = (
        proc.returncode != 0
        and not moved
        and "leaves a generated doc region stale" in proc.stderr
        and REGISTRY in proc.stderr
        and "npx tsx scripts/gen/gen-docs.ts --write" in proc.stderr
        and "env-manifest" in proc.stderr
    )
    return ok, proc.stderr


def case_partial(w: World, tag: str) -> tuple[bool, str]:
    head = w.head()
    w.plant_env_manifest_name()
    assert _gen(w.repo, "--write").returncode == 0
    proc = w.commit(ENV_MANIFEST, label="partial" + tag)
    moved = w.head() != head
    w.reset(head)
    ok = proc.returncode != 0 and not moved and REGISTRY in proc.stderr
    return ok, proc.stderr


def case_allowed(w: World, tag: str) -> tuple[bool, str]:
    head = w.head()
    w.plant_env_manifest_name()
    assert _gen(w.repo, "--write").returncode == 0
    proc = w.commit(ENV_MANIFEST, REGISTRY, label="allowed" + tag)
    moved = w.head() != head
    w.reset(head)
    ok = proc.returncode == 0 and moved and "verified clean" in proc.stderr
    return ok, proc.stderr


def case_fast_path(w: World, tag: str) -> tuple[bool, str]:
    head = w.head()
    rel = "zz-unrelated-note.txt"
    (w.repo / rel).write_text("nothing any provider reads\n", encoding="utf-8")
    _git(w.repo, "add", "--", rel)
    proc = w.commit(rel, label="fast-path" + tag, GEN_DOCS_PRECOMMIT_VERBOSE="1")
    moved = w.head() != head
    w.reset(head)
    ok = (
        proc.returncode == 0
        and moved
        and "none read by any of" in proc.stderr
        and "verified clean" not in proc.stderr
    )
    return ok, proc.stderr


def case_stale_inputs(w: World, tag: str) -> tuple[bool, str]:
    head = w.head()
    path = w.repo / PROVIDERS
    text = path.read_text(encoding="utf-8")
    old = "    const m = readEnvManifest(root);\n"
    assert text.count(old) == 1, "the env-manifest provider's first line moved"
    path.write_text(
        text.replace(old, "    fs.readFileSync(path.join(root, 'package.json'), 'utf-8');\n" + old),
        encoding="utf-8",
    )
    proc = w.commit(PROVIDERS, label="stale-inputs" + tag)
    moved = w.head() != head
    w.reset(head)
    ok = (
        proc.returncode != 0
        and not moved
        and "UNDECLARED" in proc.stderr
        and "package.json" in proc.stderr
    )
    return ok, proc.stderr


CASES = [case_refused, case_partial, case_allowed, case_fast_path, case_stale_inputs]


@pytest.mark.parametrize("case", CASES, ids=[c.__name__ for c in CASES])
def test_case_against_the_real_hook(world, case):
    world.use(world.real_hooks)
    ok, detail = case(world, "")
    assert ok, "%s failed against the real hook:\n%s" % (case.__name__, detail[-2500:])


@pytest.mark.parametrize("case", CASES, ids=[c.__name__ for c in CASES])
def test_case_fails_against_an_always_allow_hook(world, case):
    """The control: a case that still passes when the hook allows everything is not testing the hook."""
    world.use(world.planted_hooks)
    try:
        ok, detail = case(world, " (planted)")
    finally:
        world.use(world.real_hooks)
    assert not ok, "%s PASSED against an always-allow hook, so it cannot detect one:\n%s" % (
        case.__name__,
        detail[-1500:],
    )


def test_a_repository_without_the_generator_is_left_alone(tmp_path):
    """A submodule or any other repository: the hook neither refuses nor reports, even when asked to be verbose."""
    repo = tmp_path / "plain"
    _git(tmp_path, "init", "-q", "-b", BRANCH, str(repo))
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base", env=_env(COMMIT_POLICY_OK="1"))
    _git(repo, "config", "core.hooksPath", str(REPO_ROOT / HOOKS_REL))
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    msg = tmp_path / "msg"
    msg.write_text("test(fixture): plain\n", encoding="utf-8")
    proc = _git(
        repo,
        "commit",
        "-F",
        str(msg),
        "--",
        "a.txt",
        env=_env(GEN_DOCS_PRECOMMIT_VERBOSE="1"),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "gen-docs" not in proc.stderr, "the hook judged a repository it has no generator for"


def _tiny_repo(tmp_path: pathlib.Path, generator: str) -> pathlib.Path:
    """A repository holding only a `scripts/gen/gen-docs.ts`, committed with the hooks off, then pointed at them."""
    repo = tmp_path / "tiny"
    _git(tmp_path, "init", "-q", "-b", BRANCH, str(repo))
    (repo / "scripts" / "gen").mkdir(parents=True)
    (repo / GEN).write_text(generator, encoding="utf-8")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "--", GEN, "a.txt")
    _git(repo, "commit", "-q", "-m", "base", env=_env(COMMIT_POLICY_OK="1"))
    _git(repo, "config", "core.hooksPath", str(REPO_ROOT / HOOKS_REL))
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    return repo


def _commit_a(repo: pathlib.Path, tmp_path: pathlib.Path) -> subprocess.CompletedProcess:
    msg = tmp_path / "msg"
    msg.write_text("test(fixture): tiny\n", encoding="utf-8")
    return _git(repo, "commit", "-F", str(msg), "--", "a.txt", check=False)


def test_a_committed_generator_without_affected_is_skipped_loudly(tmp_path):
    """The bootstrap case that blocked every commit on 2026-10-06: HEAD's generator has no `--affected` and imports with `.js`.

    Measured then: `ERR_MODULE_NOT_FOUND ... sel/scripts/lib/doc-providers.js`, an UNCHECKED refusal of a commit the hook had no declarations to judge by. Now: allowed, with a notice, and node never started (the notice is printed before node is looked up).
    """
    head_generator = _git(REPO_ROOT, "show", "84cfe4e55:" + GEN).stdout
    assert "'--affected'" not in head_generator, (
        "control setup: that commit's generator is the pre-hook one"
    )
    proc = _commit_a(_tiny_repo(tmp_path, head_generator), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "has no --affected mode yet; not checked" in proc.stderr
    assert "ERR_MODULE_NOT_FOUND" not in proc.stderr


def test_a_js_specifier_in_the_generator_is_named_not_crashed_on(tmp_path):
    """Plain node cannot map `.js` onto `.ts`; the hook must say which import, rather than relay a node stack trace."""
    generator = "import { x } from '../lib/doc-providers.js';\nif (process.argv.includes('--affected')) {}\n"
    repo = _tiny_repo(tmp_path, generator)
    (repo / "scripts" / "lib").mkdir()
    (repo / "scripts" / "lib" / "doc-providers.ts").write_text(
        "export const x = 1;\n", encoding="utf-8"
    )
    _git(repo, "add", "--", "scripts/lib/doc-providers.ts")
    _git(repo, "commit", "-q", "-m", "lib", env=_env(COMMIT_POLICY_OK="1"))
    proc = _commit_a(repo, tmp_path)
    assert proc.returncode != 0, "a generator whose imports cannot resolve was waved through"
    assert "spell it ../lib/doc-providers.ts" in proc.stderr, proc.stderr
