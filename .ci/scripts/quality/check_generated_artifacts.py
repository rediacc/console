#!/usr/bin/env python3
"""check:ci-generated-artifacts -- the registry the pre-commit hook judges commits by must itself be able to fail.

WHY THIS EXISTS. `.ci/config/generated-artifacts.json` declares, for each generated-and-committed artifact, the globs it is generated from, the command that regenerates it and the check a commit is refused by (`.claude/rediacc_hooks/git/artifacts.py`). Every one of those declarations can rot into a check that passes without running: an input glob that matches no file never selects a commit, so the artifact is never checked and nothing says so; a generator command that does not exist is a refusal whose printed fix cannot be run; an enrolled entry whose control anchor has been reworded is a test that plants nothing. This gate reads the registry against the tracked tree and refuses each of those.

WHAT IS ASSERTED, per artifact:

  G1  THE REGISTRY PARSES, by the hook's own parser (loaded by file from `artifacts.py`, so there is one grammar): an enrolled entry carries a check, a budget under the ceiling and a control; an entry left out of the commit-time check carries its reason.
  G2  EVERY GLOB MATCHES A TRACKED FILE: each `inputs` and `outputs` glob, and each `inputs_exclude` glob, which must also remove at least one file the inputs would otherwise select (an exclusion that excludes nothing is dead text that reads as a decision).
  G3  THE GENERATOR EXISTS: `npm run <script>` names a script of the root package or of the `-w` workspace, and a path command names a tracked file. `hand-edited: ...` is admitted only on a `hand_reviewed` entry outside the commit-time check.
  G4  THE GATE EXISTS: `gate` is an id in `scripts/ci-runner/gates.lock.json`.
  G5  AN ENROLLED CHECK CAN RUN AND ITS CONTROL CAN PLANT: the checker script is tracked; `links` and `requires` name untracked paths (a tracked one would collide with the checkout of the commit's tree); a `replace` control names a tracked input that contains `old` exactly once; a `create` control names an untracked path that is an input.
  G6  THE CONTROLS ARE EXERCISED: `.claude/rediacc_hooks/tests/test_githook_generated_artifacts.py` is tracked and reads this registry, which is where each enrolled checker is proved able to refuse a real commit. This gate cannot prove that itself without running every checker twice, about 30 s; the test does.

ZERO IS A FAILURE: no tracked files, no artifacts, or no artifact enrolled at commit time exits 1, because a registry that enrols nothing makes the hook's silence mean nothing.

CONTROL FIRST. `--selftest` plants one defect per rule into a constructed registry and tree and requires the matching finding, and requires the clean fixture to stay silent. A real run executes the selftest before it reads the real tree, and a failed control exits 2.

Exit 0 clean, 1 findings or vacuous input, 2 a failed control.

---- gate ----
kind: step
step: Generated artifacts registry
lane: quality-code
why: A generated-artifact entry whose input glob matches nothing, whose generator does not exist or whose control cannot plant makes the commit-time check pass without running.
---- end gate ----
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shlex
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOK_MODULE_REL = ".claude/rediacc_hooks/git/artifacts.py"
LOCK_REL = "scripts/ci-runner/gates.lock.json"
TEST_REL = ".claude/rediacc_hooks/tests/test_githook_generated_artifacts.py"
HAND_PREFIX = "hand-edited:"
RUNNERS = ("python3", "node", "npx")


def load_hook_module(root: pathlib.Path):
    """`artifacts.py` as the hook loads it: by file, so this gate and the hook parse the registry with the same code."""
    path = root / HOOK_MODULE_REL
    spec = importlib.util.spec_from_file_location("githook_artifacts", path)
    if spec is None or spec.loader is None:
        msg = "cannot load %s" % path
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["githook_artifacts"] = module
    spec.loader.exec_module(module)
    return module


GA = load_hook_module(REPO_ROOT)


def glob_problems(artifact, tracked: list[str]) -> list[str]:
    """G2 for one artifact."""
    out: list[str] = []
    for kind, globs in (("inputs", artifact.inputs), ("outputs", artifact.outputs)):
        out.extend(
            "`%s`: the %s glob `%s` matches no tracked file, so it selects nothing and would never be noticed"
            % (artifact.id, kind, glob)
            for glob in globs
            if not any(GA.matches(path, (glob,)) for path in tracked)
        )
    for glob in artifact.inputs_exclude:
        removed = [p for p in tracked if GA.matches(p, (glob,)) and GA.matches(p, artifact.inputs)]
        if not removed:
            out.append(
                "`%s`: the inputs_exclude glob `%s` removes no file the inputs select; delete it or fix it"
                % (artifact.id, glob)
            )
    return out


def generator_problem(
    command: str, scripts: dict[str, dict], tracked: set[str], hand_ok: bool
) -> str:
    """G3: "" when `command` names something that exists, else why not. `scripts` maps a workspace name ("" for the root) to its package.json scripts."""
    if command.startswith(HAND_PREFIX):
        if hand_ok:
            return ""
        return (
            "is `%s ...` on an entry that is not `hand_reviewed` outside the commit-time check"
            % HAND_PREFIX
        )
    try:
        words = shlex.split(command)
    except ValueError as exc:
        return "does not parse as a command (%s)" % exc
    if not words:
        return "is empty"
    if words[:2] == ["npm", "run"] and len(words) >= 3:
        name = words[2]
        rest = words[3 : words.index("--")] if "--" in words[3:] else words[3:]
        workspace = ""
        if "-w" in rest and rest.index("-w") + 1 < len(rest):
            workspace = rest[rest.index("-w") + 1]
        if workspace not in scripts:
            return "names the workspace `%s`, and no package.json carries that name" % workspace
        if name not in scripts[workspace]:
            return "names the npm script `%s`, which %s does not define" % (
                name,
                "the workspace `%s`" % workspace if workspace else "the root package.json",
            )
        return ""
    if words[:2] == ["npx", "tsx"] and len(words) >= 3:
        return "" if words[2] in tracked else "runs `%s`, which is not a tracked file" % words[2]
    if words[0] in tracked:
        return ""
    return (
        "starts with `%s`, which is neither `npm run <script>`, `npx tsx <file>` nor a tracked file"
        % words[0]
    )


def check_script(check: tuple[str, ...]) -> str:
    """The script an enrolled check runs: the first argument that is not a flag, after the runner (and `tsx` under `npx`)."""
    words = [w for w in check[1:] if not w.startswith("-")]
    if check and check[0] == "npx" and words[:1] == ["tsx"]:
        words = words[1:]
    return words[0] if words else ""


def control_problem(artifact, control, tracked: set[str], read) -> str:
    """G5 for the control: "" when the declared plant can be applied to this tree, else why not. `read(rel)` returns a tracked file's text."""
    if not isinstance(control, dict):
        return "has no control"
    kind = control.get("kind")
    path = control.get("path")
    if not isinstance(path, str) or not path:
        return "its control names no `path`"
    if not GA.is_input(artifact, path):
        return (
            "its control path `%s` is not one of its inputs, so committing it would never run the checker"
            % path
        )
    if kind == "replace":
        old, new = control.get("old"), control.get("new")
        if not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
            return "its `replace` control needs differing non-empty `old` and `new`"
        if path not in tracked:
            return "its control path `%s` is not tracked" % path
        count = read(path).count(old)
        if count != 1:
            return (
                "its control anchor occurs %d time(s) in `%s`, not once; the text moved, re-point the control"
                % (count, path)
            )
        return ""
    if kind == "create":
        if not isinstance(control.get("content"), str) or not control["content"]:
            return "its `create` control has no `content`"
        if path in tracked:
            return "its `create` control path `%s` is already tracked" % path
        return ""
    return "its control `kind` is `%s`, not `replace` or `create`" % kind


def enrolled_problems(artifact, raw: dict, tracked: set[str], read) -> list[str]:
    """G5 for one entry enrolled at commit time."""
    out = []
    if artifact.check and artifact.check[0] not in RUNNERS:
        out.append(
            "`%s`: its check starts with `%s`; a commit-time check is run by one of %s"
            % (artifact.id, artifact.check[0], ", ".join(RUNNERS))
        )
    script = check_script(artifact.check)
    if script not in tracked:
        out.append(
            "`%s`: its check runs `%s`, which is not a tracked file, so the scratch checkout of a commit would not hold it"
            % (artifact.id, script or "(nothing)")
        )
    for field, paths in (
        ("links", artifact.links),
        ("requires", tuple(need.path for need in artifact.requires)),
    ):
        out.extend(
            "`%s`: `commit.%s` names `%s`, which is tracked; these are untracked build products of the working tree"
            % (artifact.id, field, path)
            for path in paths
            if path in tracked or any(t.startswith(path + "/") for t in tracked)
        )
    why = control_problem(artifact, (raw.get("commit") or {}).get("control"), tracked, read)
    if why:
        out.append("`%s`: %s" % (artifact.id, why))
    return out


def judge(text: str, tracked_list: list[str], scripts: dict[str, dict], gate_ids: set[str], read):
    """(problems, artifacts) for a registry `text` against a tree described by its tracked paths, npm scripts and gate ids. Pure apart from `read`."""
    artifacts, problems = GA.parse(text)
    problems = list(problems)
    if not artifacts:
        return problems, artifacts
    raw_by_id = {r.get("id"): r for r in json.loads(text)["artifacts"] if isinstance(r, dict)}
    tracked = set(tracked_list)
    for artifact in artifacts:
        raw = raw_by_id.get(artifact.id, {})
        problems.extend(glob_problems(artifact, tracked_list))
        hand_ok = raw.get("hand_reviewed") is True and artifact.when != GA.WHEN_COMMIT
        why = generator_problem(artifact.generator, scripts, tracked, hand_ok)
        if why:
            problems.append("`%s`: its generator `%s` %s" % (artifact.id, artifact.generator, why))
        if artifact.gate not in gate_ids:
            problems.append(
                "`%s`: its gate `%s` is not an id in %s" % (artifact.id, artifact.gate, LOCK_REL)
            )
        if artifact.when == GA.WHEN_COMMIT:
            problems.extend(enrolled_problems(artifact, raw, tracked, read))
    if not GA.enrolled(artifacts):
        problems.append(
            "no artifact is enrolled at commit time (`when: commit`), so the hook's silence would mean nothing"
        )
    if TEST_REL not in tracked:
        problems.append(
            "%s is not tracked, so no enrolled checker is proved able to refuse a commit" % TEST_REL
        )
    elif GA.REGISTRY_REL not in read(TEST_REL):
        problems.append(
            "%s does not read %s, so its cases are not the registry's" % (TEST_REL, GA.REGISTRY_REL)
        )
    return problems, artifacts


# --------------------------------------------------------------------------- the real tree


def tracked_files(root: pathlib.Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        msg = "`git ls-files` exited %d: %s" % (proc.returncode, proc.stderr.strip())
        raise RuntimeError(msg)
    return sorted(p for p in proc.stdout.split("\0") if p)


def npm_scripts(root: pathlib.Path, tracked: list[str]) -> dict[str, dict]:
    """{workspace name: scripts}, the root under "". Every tracked package.json one or two levels down is a candidate workspace."""
    out: dict[str, dict] = {}
    for rel in tracked:
        parts = rel.split("/")
        if parts[-1] != "package.json" or len(parts) > 3:
            continue
        try:
            doc = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = "" if len(parts) == 1 else doc.get("name")
        if isinstance(name, str) and isinstance(doc.get("scripts"), dict):
            out[name] = doc["scripts"]
    return out


def real_tree(root: pathlib.Path) -> int:
    try:
        tracked = tracked_files(root)
    except (OSError, RuntimeError) as exc:
        print("✗ generated artifacts: cannot list the tracked files (%s)" % exc, file=sys.stderr)
        return 1
    if not tracked:
        print(
            "✗ generated artifacts: git lists 0 tracked files; the gate is not seeing the tree and its green would mean nothing",
            file=sys.stderr,
        )
        return 1
    try:
        text = (root / GA.REGISTRY_REL).read_text(encoding="utf-8")
        gate_ids = {g["id"] for g in json.loads((root / LOCK_REL).read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            "✗ generated artifacts: cannot read the registry or %s (%s)" % (LOCK_REL, exc),
            file=sys.stderr,
        )
        return 1
    scripts = npm_scripts(root, tracked)

    def read(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8", errors="replace")

    problems, artifacts = judge(text, tracked, scripts, gate_ids, read)
    by_when = {w: [a for a in artifacts if a.when == w] for w in GA.WHENS}
    shape = (
        "%d artifact(s): %d checked at commit time (%s), %d by a dedicated commit-time path, %d left to the pre-push run; %d glob(s) over %d tracked file(s), %d workspace(s), %d gate id(s)"
        % (
            len(artifacts),
            len(by_when[GA.WHEN_COMMIT]),
            ", ".join(a.id for a in by_when[GA.WHEN_COMMIT]) or "none",
            len(by_when[GA.WHEN_DEDICATED]),
            len(by_when[GA.WHEN_PRE_PUSH]),
            sum(len(a.inputs) + len(a.outputs) + len(a.inputs_exclude) for a in artifacts),
            len(tracked),
            len(scripts),
            len(gate_ids),
        )
    )
    if problems:
        print(
            "✗ generated artifacts: %d problem(s) in %s:" % (len(problems), GA.REGISTRY_REL),
            file=sys.stderr,
        )
        for p in problems:
            print("    " + p, file=sys.stderr)
        print(
            "\n  Each of these makes the commit-time check pass without running, or print a fix that\n"
            "  cannot be run. Fix the entry in %s; do not delete the artifact to get past this.\n  %s"
            % (GA.REGISTRY_REL, shape),
            file=sys.stderr,
        )
        return 1
    print(
        "✓ generated artifacts: %s. Every glob matches, every generator and gate exists, every enrolled control can plant."
        % shape
    )
    return 0


# --------------------------------------------------------------------------- CONTROL FIRST

_FIXTURE_TRACKED = [
    "package.json",
    "packages/cli/package.json",
    "src/in/a.txt",
    "src/in/skip/b.txt",
    "src/out/gen.json",
    "tools/check.py",
    "tools/gen.py",
    TEST_REL,
]
_FIXTURE_SCRIPTS = {"": {"gen": "x"}, "@fx/cli": {"gen:cli": "x"}}
_FIXTURE_GATES = {"check:fx"}
_FIXTURE_FILES = {"src/in/a.txt": "one anchor here\n", TEST_REL: "reads %s\n" % GA.REGISTRY_REL}


def _entry(**over) -> dict:
    entry = {
        "id": "fx",
        "title": "Fixture",
        "when": "commit",
        "inputs": ["src/in/**"],
        "inputs_exclude": ["src/in/skip/**"],
        "outputs": ["src/out/*.json"],
        "generator": "npm run gen",
        "gate": "check:fx",
        "commit": {
            "check": ["python3", "tools/check.py", "--fast"],
            "budget_s": 30,
            "links": ["node_modules"],
            "requires": [{"path": "node_modules/tsx", "fix": "npm install"}],
            "control": {"kind": "replace", "path": "src/in/a.txt", "old": "anchor", "new": "moved"},
        },
    }
    entry.update(over)
    return entry


def _commit(**over) -> dict:
    block = dict(_entry()["commit"])
    block.update(over)
    return block


def _problems(*entries: dict, tracked=None, files=None) -> list[str]:
    text = json.dumps({"schema": 1, "artifacts": list(entries)})
    held = dict(_FIXTURE_FILES if files is None else files)
    found, _artifacts = judge(
        text,
        list(_FIXTURE_TRACKED if tracked is None else tracked),
        _FIXTURE_SCRIPTS,
        _FIXTURE_GATES,
        lambda rel: held.get(rel, ""),
    )
    return found


def selftest() -> int:
    """One planted defect per rule, each required to produce its finding, and the clean fixture required to stay silent. Returns the number of failed controls."""
    bad = 0
    ran = 0

    def ck(label: str, ok: bool, detail: object = "") -> None:
        nonlocal bad, ran
        ran += 1
        print("  %s  %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            bad += 1
            print("        %s" % (detail,))

    def fires(label: str, found: list[str], needle: str) -> None:
        ck(label, any(needle in p for p in found), found)

    clean = _problems(_entry())
    ck("CONTROL: a well-formed enrolled entry is silent", clean == [], clean)
    pre_push = _entry(id="later", when="pre-push", reason="too slow")
    del pre_push["commit"]
    ck(
        "CONTROL: a pre-push entry with a reason is silent beside it",
        _problems(_entry(), pre_push) == [],
    )

    fires(
        "G1: an enrolled entry with no commit block",
        _problems({k: v for k, v in _entry().items() if k != "commit"}),
        "no `commit` block",
    )
    fires(
        "G1: an enrolled entry with no check",
        _problems(_entry(commit=_commit(check=[]))),
        "`check` is empty",
    )
    fires(
        "G1: an enrolled entry with no budget",
        _problems(_entry(commit={k: v for k, v in _commit().items() if k != "budget_s"})),
        "budget_s",
    )
    fires(
        "G1: a budget above the ceiling belongs to the pre-push run",
        _problems(_entry(commit=_commit(budget_s=GA.BUDGET_CEILING_S + 1))),
        "ceiling",
    )
    fires(
        "G1: an enrolled entry with no control",
        _problems(_entry(commit={k: v for k, v in _commit().items() if k != "control"})),
        "nothing proves this checker can fail",
    )
    no_reason = dict(pre_push)
    del no_reason["reason"]
    fires("G1: a pre-push entry with no reason", _problems(_entry(), no_reason), "no `reason`")
    fires("G1: a duplicate id", _problems(_entry(), _entry()), "declared twice")
    fires("G1: an unknown `when`", _problems(_entry(when="sometimes")), "`when` must be one of")
    fires("G1: an empty registry", _problems(), "enrols nothing")
    fires(
        "G1: only pre-push entries enrol nothing",
        _problems(pre_push),
        "no artifact is enrolled at commit time",
    )

    fires(
        "G2: an input glob that matches nothing",
        _problems(_entry(inputs=["src/in/**", "src/gone/**"])),
        "`src/gone/**` matches no tracked file",
    )
    fires(
        "G2: an output glob that matches nothing",
        _problems(_entry(outputs=["src/out/*.yaml"])),
        "outputs glob `src/out/*.yaml`",
    )
    fires(
        "G2: an exclusion that excludes nothing",
        _problems(_entry(inputs_exclude=["src/out/**"])),
        "removes no file the inputs select",
    )
    ck(
        "G2 CONTROL: `*` stays inside one directory",
        not GA.matches("src/in/skip/b.txt", ("src/in/*",))
        and GA.matches("src/in/a.txt", ("src/in/*",)),
    )
    ck(
        "G2 CONTROL: `**/` spans zero directories too",
        GA.matches("a.md", ("**/*.md",)) and GA.matches("x/y/a.md", ("**/*.md",)),
    )

    fires(
        "G3: an npm script that does not exist",
        _problems(_entry(generator="npm run gen:missing")),
        "does not define",
    )
    fires(
        "G3: a workspace that does not exist",
        _problems(_entry(generator="npm run gen:cli -w @fx/gone")),
        "no package.json carries that name",
    )
    ck(
        "G3 CONTROL: a workspace script resolves in its own package",
        _problems(_entry(generator="npm run gen:cli -w @fx/cli")) == [],
    )
    fires(
        "G3: a root script is not a workspace's",
        _problems(_entry(generator="npm run gen -w @fx/cli")),
        "does not define",
    )
    ck(
        "G3 CONTROL: arguments after `--` are not read as the workspace",
        _problems(_entry(generator="npm run gen -- -w @fx/gone")) == [],
    )
    ck(
        "G3 CONTROL: a tracked script path is a generator",
        _problems(_entry(generator="tools/gen.py --write")) == [],
    )
    fires(
        "G3: an untracked script path",
        _problems(_entry(generator="tools/gone.py --write")),
        "neither `npm run <script>`",
    )
    fires(
        "G3: `npx tsx` of an untracked file",
        _problems(_entry(generator="npx tsx tools/gone.ts --write")),
        "not a tracked file",
    )
    fires(
        "G3: hand-edited on an enrolled entry",
        _problems(_entry(generator="hand-edited: drain it", hand_reviewed=True)),
        "not `hand_reviewed` outside",
    )
    hand = dict(pre_push, generator="hand-edited: drain it", hand_reviewed=True)
    ck(
        "G3 CONTROL: hand-edited on a hand-reviewed pre-push entry is silent",
        _problems(_entry(), hand) == [],
    )

    fires(
        "G4: a gate id the lock does not hold",
        _problems(_entry(gate="check:gone")),
        "is not an id in",
    )

    fires(
        "G5: a checker script that is not tracked",
        _problems(_entry(commit=_commit(check=["python3", "tools/gone.py"]))),
        "not a tracked file",
    )
    ck(
        "G5 CONTROL: `npx tsx <file>` names the file, not tsx",
        check_script(("npx", "tsx", "tools/gen.ts", "--x")) == "tools/gen.ts",
    )
    fires(
        "G5: a check run by something else",
        _problems(_entry(commit=_commit(check=["bash", "tools/check.py"]))),
        "a commit-time check is run by one of",
    )
    fires(
        "G5: a tracked path under links",
        _problems(_entry(commit=_commit(links=["src/in"]))),
        "`commit.links` names `src/in`, which is tracked",
    )
    fires(
        "G5: a tracked path under requires",
        _problems(_entry(commit=_commit(requires=[{"path": "tools/gen.py", "fix": "x"}]))),
        "`commit.requires` names",
    )
    fires(
        "G5: a control anchor that is gone",
        _problems(_entry(), files={**_FIXTURE_FILES, "src/in/a.txt": "reworded\n"}),
        "occurs 0 time(s)",
    )
    fires(
        "G5: a control anchor that is ambiguous",
        _problems(_entry(), files={**_FIXTURE_FILES, "src/in/a.txt": "anchor anchor\n"}),
        "occurs 2 time(s)",
    )
    fires(
        "G5: a control on an excluded path never runs the checker",
        _problems(
            _entry(
                commit=_commit(
                    control={"kind": "replace", "path": "src/in/skip/b.txt", "old": "a", "new": "b"}
                )
            )
        ),
        "is not one of its inputs",
    )
    fires(
        "G5: a create control over a tracked path",
        _problems(
            _entry(
                commit=_commit(control={"kind": "create", "path": "src/in/a.txt", "content": "x"})
            )
        ),
        "already tracked",
    )
    ck(
        "G5 CONTROL: a create control on a new input path is silent",
        _problems(
            _entry(
                commit=_commit(control={"kind": "create", "path": "src/in/new.txt", "content": "x"})
            )
        )
        == [],
    )
    ck(
        "G5 CONTROL: a hand edit of an OUTPUT is an input of the check",
        GA.is_input(
            GA.parse(json.dumps({"schema": 1, "artifacts": [_entry()]}))[0][0], "src/out/gen.json"
        ),
    )

    fires(
        "G6: the test file is not tracked",
        _problems(_entry(), tracked=[p for p in _FIXTURE_TRACKED if p != TEST_REL]),
        "no enrolled checker is proved able to refuse",
    )
    fires(
        "G6: the test file does not read the registry",
        _problems(_entry(), files={**_FIXTURE_FILES, TEST_REL: "unrelated\n"}),
        "its cases are not the registry's",
    )

    print("  %d control(s), %d failed" % (ran, bad))
    return bad


def main(argv: list[str]) -> int:
    print("generated artifacts: controls first, then the registry")
    if selftest():
        print("✗ a control failed; every verdict below would be meaningless", file=sys.stderr)
        return 2
    if "--selftest" in argv:
        print("✓ selftest only; the real registry was not judged")
        return 0
    return real_tree(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
