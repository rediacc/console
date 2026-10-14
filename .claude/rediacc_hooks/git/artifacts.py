"""The commit-time check of the generated artifacts declared in `.ci/config/generated-artifacts.json`.

WHY A REGISTRY. A generated file that is committed goes stale whenever one of its inputs is committed without it, and until this module each such miss was found by a later gate, or by CI. Three on 2026-10-13: 8dbb6066e reworded CLI messages and left the generated CLI contract stale for 40 minutes, until a pre-push run; `agent/plans/QUEUE.md` was regenerated in the working tree and never committed, so PR 600's run 38381096702 went red on bytes no local gate had read; and a new test file needed `gen-docs.ts --write`, which the gen-docs pre-commit check in `githooks.py` caught at the commit, with the fix in the message. The third is the model. This module is the same refusal for every artifact that declares its inputs, a checker and a generator command.

WHAT IT DOES, for a commit in a repository whose INDEX holds the registry:

  1. reads the registry from the commit's index, never the working tree, so another session's half-written entry cannot decide this commit;
  2. lists the paths the commit changes (`git diff --cached`, which reads the temporary index of a `git commit -- <paths>`);
  3. for each artifact enrolled at commit time, matches those paths against its `inputs` globs. NO MATCH IS THE COMMON CASE and costs two git calls;
  4. on a match, checks out the commit's index into a scratch tree (once per commit, 0.7 s), links in the untracked build products the entry declares (`links`), and runs the entry's `check` there under its `budget_s`;
  5. refuses when the checker exits with the entry's `stale_exit`, printing the staged inputs, the checker's own words, the generator command and the output paths to add.

THE COMMIT'S TREE, NOT THE WORKING TREE, for the reason `githooks.py` gives for gen-docs: `git commit -F <msg> -- <paths>` leaves a regeneration unstaged, and a working-tree check waves that through. The checker runs the scratch tree's OWN copy of itself, so the commit is judged by the code it carries.

UNKNOWN IS A REFUSAL. A registry that does not parse, a missing `requires` path, a checker that exits with anything but 0 or `stale_exit`, and a run that exceeds its budget are each reported as UNCHECKED and refused with the fix. There is no escape hatch here: the one override is `COMMIT_POLICY_OK=1`, the operator's, which `githooks.main` reads before anything in this file runs.

WHAT IT IS NOT. It is not the gate. An artifact whose check is too slow, not deterministic, or hand-reviewed stays `"when": "pre-push"` in the registry with the reason beside it, and `check:ci-generated-artifacts` refuses a registry whose globs match nothing or whose commands do not exist. Whether an enrolled checker can fail at all is proved by `.claude/rediacc_hooks/tests/test_githook_generated_artifacts.py`, which commits each entry's declared `control` through the real hook.

LOADED BY FILE from `githooks.py`, like `commit_policy.py`; it imports nothing from the package and adds no `sys.path` entry.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time

REGISTRY_REL = ".ci/config/generated-artifacts.json"
SCHEMA = 1
WHEN_COMMIT = "commit"
WHEN_DEDICATED = "commit-dedicated"
WHEN_PRE_PUSH = "pre-push"
WHENS = (WHEN_COMMIT, WHEN_DEDICATED, WHEN_PRE_PUSH)
# A budget above this is not a commit-time check any more; the entry belongs in the pre-push run.
BUDGET_CEILING_S = 120
CHECKOUT_TIMEOUT_S = 600
SHOWN_PATHS = 12
TAIL_CHARS = 1500

LABEL = "generated-artifacts pre-commit"


class RegistryError(Exception):
    """The registry cannot be used as written. Never a pass."""


@dataclasses.dataclass(frozen=True)
class Requirement:
    """An untracked path the checker needs in the working tree, and the command that creates it."""

    path: str
    fix: str


@dataclasses.dataclass(frozen=True)
class Artifact:
    """One registry entry. The commit-time fields are empty unless `when` is `commit`."""

    id: str
    title: str
    when: str
    inputs: tuple[str, ...]
    inputs_exclude: tuple[str, ...]
    outputs: tuple[str, ...]
    generator: str
    gate: str
    check: tuple[str, ...] = ()
    stale_exit: int = 1
    budget_s: int = 0
    links: tuple[str, ...] = ()
    requires: tuple[Requirement, ...] = ()
    env_remove: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Verdict:
    """What one checker run established: `kind` is `clean`, `stale` or `unchecked`."""

    artifact: Artifact
    kind: str
    hits: tuple[str, ...]
    seconds: float = 0.0
    detail: str = ""


def glob_rx(pattern: str) -> re.Pattern:
    """`**/` spans any number of directories (none included), `**` anything, `*` and `?` stay inside one. `commit_policy._glob_rx`'s grammar, restated here because this module is loaded alone by `check:ci-generated-artifacts`."""
    out = []
    k = 0
    while k < len(pattern):
        if pattern.startswith("**/", k):
            out.append("(?:.*/)?")
            k += 3
        elif pattern.startswith("**", k):
            out.append(".*")
            k += 2
        elif pattern[k] == "*":
            out.append("[^/]*")
            k += 1
        elif pattern[k] == "?":
            out.append("[^/]")
            k += 1
        else:
            out.append(re.escape(pattern[k]))
            k += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(glob_rx(p).match(path) for p in patterns)


def is_input(artifact: Artifact, path: str) -> bool:
    """Whether a changed `path` could make this artifact stale: one of its inputs and not excluded, or one of its outputs (a hand edit of a generated file is drift too)."""
    if matches(path, artifact.outputs):
        return True
    return matches(path, artifact.inputs) and not matches(path, artifact.inputs_exclude)


def _strings(raw: dict, key: str, where: str, problems: list[str], required: bool = False) -> tuple:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        problems.append("%s: `%s` must be a list of non-empty strings" % (where, key))
        return ()
    if required and not value:
        problems.append(
            "%s: `%s` is empty, so the entry declares nothing to judge by" % (where, key)
        )
    return tuple(value)


def _commit_fields(raw: dict, where: str, problems: list[str]) -> dict:
    """The `commit` block of an enrolled entry, validated. Every missing piece is a problem: an enrolled entry with no checker is a check that cannot fail."""
    block = raw.get("commit")
    if not isinstance(block, dict):
        problems.append("%s: `when` is `commit` and there is no `commit` block" % where)
        return {}
    check = _strings(block, "check", where, problems, required=True)
    budget = block.get("budget_s")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        problems.append("%s: `commit.budget_s` must be a positive integer of seconds" % where)
        budget = 0
    elif budget > BUDGET_CEILING_S:
        problems.append(
            "%s: `commit.budget_s` is %d, above the %d s ceiling; a check that slow belongs to the pre-push run (`when: pre-push` with the reason)"
            % (where, budget, BUDGET_CEILING_S)
        )
    stale_exit = block.get("stale_exit", 1)
    if not isinstance(stale_exit, int) or isinstance(stale_exit, bool) or stale_exit == 0:
        problems.append("%s: `commit.stale_exit` must be a non-zero integer" % where)
        stale_exit = 1
    requires = []
    for item in block.get("requires", []):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("fix"), str)
            or not item["path"]
            or not item["fix"]
        ):
            problems.append("%s: every `commit.requires` item needs a `path` and a `fix`" % where)
            continue
        requires.append(Requirement(item["path"], item["fix"]))
    if not isinstance(block.get("control"), dict):
        problems.append(
            "%s: `commit.control` is missing; without a planted control nothing proves this checker can fail"
            % where
        )
    return {
        "check": check,
        "budget_s": budget,
        "stale_exit": stale_exit,
        "links": _strings(block, "links", where, problems),
        "requires": tuple(requires),
        "env_remove": _strings(block, "env_remove", where, problems),
    }


def parse(text: str) -> tuple[list[Artifact], list[str]]:
    """(artifacts, problems) for the registry's text. Pure: no filesystem, no git."""
    try:
        doc = json.loads(text)
    except ValueError as exc:
        return [], ["%s is not JSON (%s)" % (REGISTRY_REL, exc)]
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return [], ["%s: `schema` must be %d" % (REGISTRY_REL, SCHEMA)]
    entries = doc.get("artifacts")
    if not isinstance(entries, list) or not entries:
        return [], ["%s: `artifacts` is empty, so the registry enrols nothing" % REGISTRY_REL]
    problems: list[str] = []
    out: list[Artifact] = []
    seen: set[str] = set()
    for n, raw in enumerate(entries):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            problems.append("artifact #%d: no `id`" % n)
            continue
        where = "artifact `%s`" % raw["id"]
        if raw["id"] in seen:
            problems.append("%s: declared twice" % where)
            continue
        seen.add(raw["id"])
        when = raw.get("when")
        if when not in WHENS:
            problems.append("%s: `when` must be one of %s" % (where, ", ".join(WHENS)))
            continue
        problems.extend(
            "%s: `%s` is missing" % (where, key)
            for key in ("title", "generator", "gate")
            if not isinstance(raw.get(key), str) or not raw[key]
        )
        if when != WHEN_COMMIT and (not isinstance(raw.get("reason"), str) or not raw["reason"]):
            problems.append(
                "%s: `when` is `%s` and there is no `reason`; an artifact left out of the commit-time check says why"
                % (where, when)
            )
        if when != WHEN_COMMIT and "commit" in raw:
            problems.append("%s: a `commit` block on an entry that is not `when: commit`" % where)
        fields = _commit_fields(raw, where, problems) if when == WHEN_COMMIT else {}
        out.append(
            Artifact(
                id=raw["id"],
                title=str(raw.get("title") or ""),
                when=when,
                inputs=_strings(raw, "inputs", where, problems, required=True),
                inputs_exclude=_strings(raw, "inputs_exclude", where, problems),
                outputs=_strings(raw, "outputs", where, problems, required=True),
                generator=str(raw.get("generator") or ""),
                gate=str(raw.get("gate") or ""),
                **fields,
            )
        )
    return out, problems


def enrolled(artifacts: list[Artifact]) -> list[Artifact]:
    return [a for a in artifacts if a.when == WHEN_COMMIT]


def select(artifacts: list[Artifact], changed: list[str]) -> list[tuple[Artifact, tuple[str, ...]]]:
    """Each enrolled artifact with the changed paths that are its inputs; artifacts with none are left out."""
    out = []
    for artifact in enrolled(artifacts):
        hits = tuple(p for p in changed if is_input(artifact, p))
        if hits:
            out.append((artifact, hits))
    return out


def _run(args: list[str], cwd: str, env: dict | None, timeout: int):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def changed_paths(repo: str, env: dict) -> list[str]:
    """The paths this commit changes against HEAD, from the commit's index. A first commit has no HEAD and git then lists every path, which is the right answer."""
    proc = _run(
        ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"], repo, env, timeout=60
    )
    if proc.returncode != 0:
        raise RegistryError(
            "`git diff --cached` exited %d: %s" % (proc.returncode, proc.stderr.strip()[-300:])
        )
    return sorted(p for p in proc.stdout.split("\0") if p)


def registry_text(repo: str, env: dict) -> str | None:
    """The registry as the commit's index holds it, or None when this repository carries none."""
    proc = _run(["git", "cat-file", "blob", ":" + REGISTRY_REL], repo, env, timeout=60)
    return proc.stdout if proc.returncode == 0 else None


def _argv(check: tuple[str, ...]) -> list[str]:
    """The checker's argv. `python3` means the interpreter running this hook, so the scratch run and the hook cannot disagree about the Python."""
    return [sys.executable if check[0] == "python3" else check[0], *check[1:]]


def link_products(repo: str, tree: str, artifact: Artifact) -> None:
    """Link the declared untracked build products of the working tree into the scratch tree. A product the working tree lacks is skipped: `requires` is the list that must exist."""
    for rel in artifact.links:
        src = os.path.join(repo, rel)
        dst = os.path.join(tree, rel)
        if not os.path.lexists(src) or os.path.lexists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.symlink(src, dst)


def run_check(
    repo: str, tree: str, env: dict, artifact: Artifact, hits: tuple[str, ...]
) -> Verdict:
    """Run one enrolled artifact's checker in the scratch tree and classify the result."""
    for need in artifact.requires:
        if not os.path.lexists(os.path.join(repo, need.path)):
            return Verdict(
                artifact,
                "unchecked",
                hits,
                detail="`%s` is missing from the working tree, and the checker needs it. Create it: %s"
                % (need.path, need.fix),
            )
    try:
        link_products(repo, tree, artifact)
    except OSError as exc:
        return Verdict(
            artifact, "unchecked", hits, detail="linking a build product failed: %s" % exc
        )
    run_env = {k: v for k, v in env.items() if k not in artifact.env_remove}
    started = time.monotonic()
    try:
        proc = _run(_argv(artifact.check), tree, run_env, artifact.budget_s)
    except subprocess.TimeoutExpired:
        return Verdict(
            artifact,
            "unchecked",
            hits,
            time.monotonic() - started,
            "`%s` exceeded its %d s budget (`commit.budget_s` in %s)"
            % (" ".join(artifact.check), artifact.budget_s, REGISTRY_REL),
        )
    except OSError as exc:
        return Verdict(
            artifact,
            "unchecked",
            hits,
            detail="`%s` could not start: %s" % (artifact.check[0], exc),
        )
    seconds = time.monotonic() - started
    said = ((proc.stderr or "") + (proc.stdout or "")).strip()[-TAIL_CHARS:]
    if proc.returncode == 0:
        return Verdict(artifact, "clean", hits, seconds)
    if proc.returncode == artifact.stale_exit:
        return Verdict(artifact, "stale", hits, seconds, said)
    return Verdict(
        artifact,
        "unchecked",
        hits,
        seconds,
        "`%s` exited %d, which is neither 0 nor its stale code %d:\n%s"
        % (" ".join(artifact.check), proc.returncode, artifact.stale_exit, said),
    )


def _indent(text: str, lines: int = 14) -> str:
    return "\n".join("    " + line for line in text.splitlines()[-lines:])


def _paths(hits: tuple[str, ...]) -> str:
    rows = ["    " + p for p in hits[:SHOWN_PATHS]]
    if len(hits) > SHOWN_PATHS:
        rows.append("    ... and %d more" % (len(hits) - SHOWN_PATHS))
    return "\n".join(rows)


def addable(outputs: tuple[str, ...]) -> str:
    """The output globs as pathspecs a shell passes to git unharmed: `dir/**` is the directory, any other glob is quoted so git expands it and the shell does not."""
    out = []
    for glob in outputs:
        spec = glob.removesuffix("/**")
        out.append("'%s'" % spec if any(ch in spec for ch in "*?[") else spec)
    return " ".join(out)


def stale_message(verdict: Verdict) -> str:
    a = verdict.artifact
    outputs = addable(a.outputs)
    return (
        "this commit leaves a generated artifact stale: %s (`%s`).\n\n"
        "  It stages what the artifact is generated from:\n%s\n\n"
        "  and its checker, run against the commit's own tree, reports:\n%s\n\n"
        "  Fix: regenerate, then commit the regenerated file(s) WITH the input(s):\n"
        "    %s\n"
        "    git commit -F <msg> -- <the same paths> %s\n"
        "  (or `git add -- %s` before a plain commit). If it is still refused after regenerating,\n"
        "  the working tree holds an unstaged edit to another input that this commit leaves out;\n"
        "  `git status` names it. The full verdict before a push is `npm run %s`."
        % (
            a.title,
            a.id,
            _paths(verdict.hits),
            _indent(verdict.detail),
            a.generator,
            outputs,
            outputs,
            a.gate,
        )
    )


def unchecked_message(verdict: Verdict) -> str:
    a = verdict.artifact
    return (
        "UNCHECKED: this commit stages inputs of a generated artifact, %s (`%s`), and the artifact\n"
        "could not be judged:\n%s\n\n"
        "  The staged inputs:\n%s\n\n"
        "An unknown is not a pass. Fix the cause; the generator is `%s` and the full verdict is\n"
        "`npm run %s`."
        % (a.title, a.id, _indent(verdict.detail, 24), _paths(verdict.hits), a.generator, a.gate)
    )


def clean_line(verdict: Verdict, staged: int) -> str:
    a = verdict.artifact
    return (
        "%s: %s: %d of %d staged path(s) are its inputs; the commit's tree verified clean (%.1fs of a %ds budget)\n"
        % (LABEL, a.id, len(verdict.hits), staged, verdict.seconds, a.budget_s)
    )


def checkout_tree(repo: str, tree: str, env: dict) -> None:
    """The commit's index, in full, under `tree`. Raises RegistryError when git cannot write it."""
    shutil.rmtree(tree, ignore_errors=True)
    proc = _run(
        ["git", "-c", "checkout.workers=-1", "checkout-index", "-a", "--prefix=%s/" % tree],
        repo,
        env,
        CHECKOUT_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RegistryError(
            "checking out the commit's tree failed: %s" % proc.stderr.strip()[-600:]
        )


def judge(repo: str, git_dir: str, env: dict, tree: str) -> tuple[list[Verdict], int, int]:
    """(verdicts, staged path count, enrolled artifact count) for the commit `env`'s index describes.

    No registry in the index answers ([], 0, 0): a submodule, a fixture, or a commit older than the registry. Stops at the first artifact that is not clean, since one refusal is enough to stop the commit and the next run costs seconds.
    """
    text = registry_text(repo, env)
    if text is None:
        return [], 0, 0
    artifacts, problems = parse(text)
    if problems:
        raise RegistryError(
            "the commit's %s has %d problem(s):\n%s\n`npm run check:ci-generated-artifacts` judges the registry"
            % (REGISTRY_REL, len(problems), "\n".join("  " + p for p in problems[:8]))
        )
    changed = changed_paths(repo, env)
    selected = select(artifacts, changed)
    verdicts: list[Verdict] = []
    if not selected:
        return verdicts, len(changed), len(enrolled(artifacts))
    try:
        checkout_tree(repo, tree, env)
        tree_env = dict(env, GIT_DIR=git_dir, GIT_WORK_TREE=tree)
        for artifact, hits in selected:
            verdict = run_check(repo, tree, tree_env, artifact, hits)
            verdicts.append(verdict)
            if verdict.kind != "clean":
                break
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    return verdicts, len(changed), len(enrolled(artifacts))
