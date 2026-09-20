#!/usr/bin/env python3
"""A Python script a workflow RUNS must have its third-party imports installed.

WHY THIS EXISTS. check_workflow_submodule_deps.py imported PyYAML, ran green on the author's machine, and died on the runner with ModuleNotFoundError. The author's environment had the module; a clean Ubuntu runner does not. Nothing compared what a script imports against what its job installs, so the gap was invisible until the job crashed -- and it crashed in the commit that added
a gate against checks which silently do not run.

WHY A DOCUMENT WAS NOT ENOUGH. The obvious remedy is a line in TRAPS.md saying "install your dependencies". A document an agent can skip is not a control, and this repo has the receipts: the stop-hook suite's own setup() carried a comment recording that 30 cases were once lost to an inherited GITHUB_ACTIONS, and a new call site was still added without the pin. The lesson was
written down and then walked past. This asserts the property instead.

WHAT IT CHECKS. For every workflow step that runs a repo .py file, it reads that file's top-level imports, drops the standard library and the script's own neighbours, and requires anything left to be named by a `pip install` earlier in the same job.

WHAT IT DOES NOT DO. It does not follow imports transitively. A gate that runs its own helper module is one hop from this one, and the honest report of that limit belongs here rather than in a comment nobody reads: if a gate grows a helper with its own third-party import, this will not see it.

THE ONE HOP IT DOES FOLLOW, and only for sys.path, not for dependencies. A sibling module a script imports may be the thing that puts a directory on sys.path -- `.ci/scripts/quality/_cipath.py` is exactly that, extracted so eighty-one gate entry points stop repeating the insert. Its importers are read one hop deep for the DIRECTORIES they gain, which keeps `rediacc_ci` first-party.
What is NOT read one hop deep is the neighbour's own imports, so the limit in the paragraph above is unchanged.

---- gate ----
step: Python gate deps
needs: python-yaml
selftest: true
---- end gate ----
"""

import ast
import pathlib
import re
import sys
import tempfile

import _cipath  # noqa: F401
import yaml
from rediacc_ci import paths as ci_paths


def _pyyaml_pin():
    """The PyYAML version, read from the ONE place it is defined.

    These strings are advice printed to a human, but a hardcoded version in advice is still a second definition: it drifts silently, and the person following it installs the wrong thing while believing the gate told them to.
    """
    pins = pathlib.Path(__file__).resolve().parents[3] / ".devcontainer" / "toolchain.env"
    try:
        for line in pins.read_text().splitlines():
            if line.startswith("PYYAML_VERSION="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "<see .devcontainer/toolchain.env>"


REPO = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = REPO / ".github" / "workflows"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", re.MULTILINE)
PIP_RE = re.compile(r"pip\s+install[^\n]*", re.IGNORECASE)


# Directory names a script puts on sys.path, so its cross-directory imports can be recognised as first-party. THE NAMED-VARIABLE FORM. `[^)]*?` could not cross the `)` of a nested call, so `sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))` matched NOTHING and the wl_* modules those five scripts import read as third-party dependencies the gate would demand somebody pip
# install. Same defect as PARENTS_RE's first draft, in the line right above it. `.*?` spans the call; the variable is still required to be an ALL-CAPS name, which is what keeps this from matching arbitrary text.
#
# TWO SPELLINGS, NOT ONE, since PRE-A1. `rediacc_ci.paths.on_sys_path(d)` is the canonical hop now and a bare `sys.path.insert` is the residue; both put a directory on the path and this gate has to read either. Leaving the resolver form out is not a cosmetic gap: the day `check_gate_reachability_coverage.py` and `check_agent_hint_liveness.py` were cut over, this gate reported their
# `wl_reggate` and `wl_agents` imports as third-party dependencies nobody could pip install, on a change that added no dependency at all.
HOP = r"(?:sys\.path\.(?:insert|append)|paths\.on_sys_path)"
SYS_PATH_RE = re.compile(HOP + r"\(.*?([A-Z_]+)\b")
# `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[N]))`, the inline form; the capture is N.
PARENTS_RE = re.compile(HOP + r"\(.*?parents\[(\d+)\]")
# `paths.hooks_stop_dir(ROOT)` -- a hop whose directory is named by a FUNCTION and so carries no literal and no ALL-CAPS variable for the two patterns above to find. The mapping from helper to directory is not copied here: the helper is CALLED, against this repo's root, so `paths.py` stays the one place the `.claude/hooks/stop` literal lives. That is the whole reason those call
# sites were moved onto it.
PATHS_HELPER_RE = re.compile(r"paths\.(\w*_dir)\(")
DIR_ASSIGN_RE = re.compile(r"^([A-Z_]+)\s*=\s*(.+)$", re.MULTILINE)


def _imported_roots(body: str) -> set[str]:
    """Top-level module names this source imports, read from the SYNTAX TREE.

    NOT a line regex, and the difference is not cosmetic. IMPORT_RE matches the word `import` or `from` at the start of ANY line, docstrings and comments included, so a sentence beginning "from the comparison" or "from one tail block" was read as an import of a module named `the` or `one`. Four such sentences were live in .ci/scripts/quality on 2026-09-08 and this gate reported all
    four as uninstalled dependencies, naming words that are not modules. A parser cannot make that mistake, and a gate whose findings are unbelievable stops being read.

    A FILE THAT DOES NOT PARSE FALLS BACK to the regex rather than going quiet. Returning an empty set on SyntaxError would turn a broken file into a silent pass here, which is the vacuity this estate has rules about; the over-reporting regex is the safer wrong answer.

    RELATIVE IMPORTS ARE SKIPPED (`node.level > 0`): `from . import x` is first-party by construction and has no top-level name to install.
    """
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return set(IMPORT_RE.findall(body))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _root_names(script: pathlib.Path, depth) -> set[str]:
    """Importable names sitting in `script`'s Nth parent directory.

    PACKAGES AS WELL AS MODULES: a `parents[N]` hop points at a directory whose children are packages (`rediacc_ci/`), not loose `.py` files, so a `glob("*.py")` alone finds nothing at all and the widening would be silent.
    """
    try:
        root = script.resolve().parents[int(depth)]
    except (IndexError, ValueError):
        return set()
    if not root.is_dir():
        return set()
    return {p.stem for p in root.glob("*.py")} | {
        d.name for d in root.iterdir() if (d / "__init__.py").is_file()
    }


def first_party_modules(script: pathlib.Path, body: str, _seen=None) -> set[str]:
    """Module names importable as FIRST-PARTY from this script.

    Its own directory, plus any directory it inserts into sys.path -- check_agent_hint_liveness.py imports wl_agents from .claude/hooks/stop that way, and a same-directory-only test called that a third-party dependency.

    Scanning the WHOLE repo instead was tried and is worse: three vendored .venv trees contain a yaml.py, which made PyYAML look first-party and broke this gate's own control. A first-party set that swallows the very module the control depends on is not a widening, it is a hole.
    """
    names = {p.stem for p in script.parent.glob("*.py")}
    # THE `/`-JOIN FORM, resolved from the sys.path LINE ITSELF rather than from a separate assignment: `sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))`. Five scripts write this and their wl_* imports still read as third-party after SYS_PATH_RE was widened, because DIR_ASSIGN_RE looks for the literals on the variable's ASSIGNMENT line and here they are on the insert
    # line.
    for line in body.split("\n"):
        if ("sys.path" not in line and "on_sys_path" not in line) or "/" not in line:
            continue
        parts = [a or b for a, b in re.findall(r'"([^"]+)"|\'([^\']+)\'', line)]
        if not parts:
            continue
        candidate = REPO.joinpath(*[part.strip("/") for part in parts])
        if candidate.is_dir():
            names |= {p.stem for p in candidate.glob("*.py")}

    for hint in SYS_PATH_RE.findall(body):
        for var, value in DIR_ASSIGN_RE.findall(body):
            if var != hint:
                continue
            # A `parents[N]` ON THE ASSIGNMENT LINE, which the literal scan below cannot see because PARENTS_RE has to reach from `sys.path.insert(` to `parents[` inside ONE line, and `.` does not cross a newline:
            #     CI_DIR = pathlib.Path(__file__).resolve().parents[2]
            # sys.path.insert(0, str(CI_DIR)) `_cipath.py` is written that way on purpose (the number is checked against the directory it lands on, right there in the file), and resolving the VALUE here is what keeps this gate from depending on one particular spelling of the same computation.
            #
            # NOT `elif`, and not a `continue`: an assignment can carry BOTH a `parents[N]` and path literals -- `ROOT.parents[3] / ".claude" / "hooks"` is the shape -- and taking only the first arm would drop a directory this function used to find. Everything here only ever ADDS names, which is what makes it safe to widen.
            depth = re.search(r"parents\[(\d+)\]", value)
            if depth:
                names |= _root_names(script, depth.group(1))
            # The literals are path PARTS to be joined, not alternatives.
            # HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
            # yields three fragments, and testing each alone finds no directory at all, so the import stayed unrecognised.
            parts = [a or b for a, b in re.findall(r'"([^"]+)"|\'([^\']+)\'', value)]
            if not parts:
                continue
            candidate = REPO.joinpath(*[part.strip("/") for part in parts])
            if candidate.is_dir():
                names |= {p.stem for p in candidate.glob("*.py")}

    # A HELPER NAMES THE DIRECTORY. `paths.on_sys_path(paths.hooks_stop_dir(ROOT))` has no literal and no directory variable, so every loop above finds nothing in it. The helper is called rather than tabulated, which is what keeps this arm
    # from becoming a second copy of paths.py that drifts from the first.
    #
    # `REPO`, not the helper's default root: this gate judges THIS tree, and `paths.repo_root()` would answer $REDIACC_CI_ROOT if a harness had set it.
    for helper in set(PATHS_HELPER_RE.findall(body)):
        fn = getattr(ci_paths, helper, None)
        if not callable(fn):
            continue
        try:
            candidate = pathlib.Path(fn(REPO))
        except TypeError:  # a `*_dir` helper that does not take a root
            continue
        if candidate.is_dir():
            names |= {p.stem for p in candidate.glob("*.py")}

    # THE INLINE BOOTSTRAP, which is the idiom this repo actually writes and which the named-variable path above cannot see: sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2])) A script that puts the package root on the path and then imports the package was being called a third-party dependency, with the gate demanding somebody `pip install rediacc_ci`. That is the
    # same hole the docstring above describes, one spelling further along.
    #
    # WHO STILL WRITES IT, since the count here used to say "eight scripts" and that number went to one the day the eighty-one gate entry points were cut over to `import _cipath`: `.ci/rediacc_ci/setup/tools.py`. The shim they were cut over to writes the named-variable form handled above, and is reached through the NEIGHBOUR loop at the bottom of this function.
    for depth in PARENTS_RE.findall(body):
        names |= _root_names(script, depth)

    # A NEIGHBOUR CAN BE THE HOP, which is one directory hop further than any loop above can see because every one of them reads only THIS script's body.
    #
    # MEASURED, NOT ANTICIPATED. `.ci/scripts/quality/_cipath.py` was extracted so that eighty-one gate entry points would stop repeating the insert above. The moment they stopped, each of them held `import _cipath` and no `parents[N]` of its own, `rediacc_ci` fell out of the first-party set, and this gate reported 69 findings on a change that added no dependency at all. The
    # extraction is the correct move and the blindness was here.
    #
    # ONE HOP, NOT TRANSITIVE. The neighbour has to be a sibling `.py` that this script actually imports, which is exactly the shape an extracted sys.path shim has. A full transitive walk is the thing the module docstring says this gate does not do, and saying it in one place and doing it in another is how a documented limit stops being true.
    seen = set() if _seen is None else _seen
    seen.add(script.resolve())
    for imported in sorted(_imported_roots(body) & names):
        neighbour = script.parent / (imported + ".py")
        if not neighbour.is_file() or neighbour.resolve() in seen:
            continue
        try:
            neighbour_body = neighbour.read_text(errors="replace")
        except OSError:
            continue
        names |= first_party_modules(neighbour, neighbour_body, seen)
    return names


def third_party_imports(script: pathlib.Path) -> set[str]:
    """Top-level module names that are neither stdlib nor a local neighbour."""
    try:
        body = script.read_text(errors="replace")
    except OSError:
        return set()
    names = _imported_roots(body)
    stdlib = set(sys.stdlib_module_names)
    # LOCAL means anywhere in this repo, not just the script's own folder. check_agent_hint_liveness.py lives in .ci/scripts/quality and imports wl_agents from .claude/hooks/stop via a sys.path insert, so a same-directory test called a first-party module third-party and demanded somebody pip install it.
    return {n for n in names if n not in stdlib and n not in first_party_modules(script, body)}


def scripts_a_step_runs(text: str) -> list[pathlib.Path]:
    out = []
    for token in re.findall(r"[\w./-]+\.py", text):
        candidate = REPO / token.removeprefix("./")
        if candidate.is_file():
            out.append(candidate)
    return out


def scan(workflow_files: list[pathlib.Path]):
    """Returns (findings, steps_scanned)."""
    findings = []
    steps_scanned = 0
    for wf in workflow_files:
        try:
            doc = yaml.safe_load(wf.read_text())
        except yaml.YAMLError as exc:
            findings.append((str(wf), "<unparseable>", f"cannot parse: {exc}"))
            continue
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            installed = ""
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                run = str(step.get("run") or "")
                if not run:
                    continue
                # A step may install and then use in one block, so its own pip lines count for itself. Order within a step is the author's problem; order across steps is what this checks.
                here = "\n".join(PIP_RE.findall(run))
                for script in scripts_a_step_runs(run):
                    steps_scanned += 1
                    for module in sorted(third_party_imports(script)):
                        haystack = (installed + "\n" + here).lower()
                        if module.lower() not in haystack:
                            findings.append(
                                (
                                    str(wf.relative_to(REPO))
                                    if wf.is_relative_to(REPO)
                                    else str(wf),
                                    job_name,
                                    f"{script.name} imports '{module}' and no pip install in this job names it",
                                )
                            )
                installed += "\n" + here
    return findings, steps_scanned


def run_controls() -> list[str]:
    """Prove the rule fires on a missing install and stays quiet on a present one."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        script = REPO / ".ci" / "scripts" / "quality" / "check_workflow_submodule_deps.py"
        if not script.is_file():
            return ["the control's example script is missing, so the rule was never exercised"]

        planted = tmpdir / "planted.yml"
        rel = script.relative_to(REPO)

        planted.write_text(f"jobs:\n  bad:\n    steps:\n      - run: {rel}\n")
        found, _ = scan([planted])
        if not found:
            failures.append(
                "a step running a script with an uninstalled third-party import was not flagged"
            )

        planted.write_text(
            "jobs:\n  good:\n    steps:\n"
            f'      - run: python3 -m pip install --user "PyYAML=={_pyyaml_pin()}"\n'
            f"      - run: {rel}\n"
        )
        found, _ = scan([planted])
        if found:
            failures.append("a step whose job installs the dependency was still flagged")

        planted.write_text("jobs:\n  unrelated:\n    steps:\n      - run: echo hello\n")
        found, _ = scan([planted])
        if found:
            failures.append("a step running no Python at all was flagged")

        # THE NEIGHBOUR HOP, pinned by a control because it was a real red. `check_npmrc.py` reaches `rediacc_ci` through `import _cipath`, a sibling module whose only job is the sys.path insert. Delete the neighbour loop in first_party_modules() and this control fires: measured at 69 findings across the real workflows, none of them a dependency anybody had to install. PROSE IS NOT
        # AN IMPORT, both directions, because the regex this replaced could not tell them apart and reported `the`, `one` and `its` as missing dependencies. The negative half alone would be satisfied by a parser that saw nothing at all, so the real import is asserted in the same breath.
        prose = (
            '"""A docstring that starts sentences the way this estate does.\n\n'
            "from the comparison. Found 2026-09-08 while cutting W7 P4 over.\n"
            "import one tail block, while the twin prints two.\n"
            '"""\n\nimport yaml\n'
        )
        roots = _imported_roots(prose)
        failures.extend(
            f"a docstring sentence was read as an import of '{word}'"
            for word in ("the", "one")
            if word in roots
        )
        if "yaml" not in roots:
            failures.append("a real import beside that prose was not seen at all")

        shim = REPO / ".ci" / "scripts" / "quality" / "_cipath.py"
        via_shim = REPO / ".ci" / "scripts" / "quality" / "check_npmrc.py"
        if not shim.is_file() or not via_shim.is_file():
            failures.append(
                "the sys.path shim or its example importer is missing, so the neighbour "
                "hop was never exercised"
            )
        else:
            planted.write_text(
                f"jobs:\n  shimmed:\n    steps:\n      - run: {via_shim.relative_to(REPO)}\n"
            )
            found, _ = scan([planted])
            if found:
                failures.append(
                    "a gate reaching rediacc_ci through its %s neighbour was reported as "
                    "needing a pip install: %s" % (shim.name, found)
                )

        # THE RESOLVER HOP, and it needs TWO subjects because PRE-A1 produced two shapes, read by two different arms of first_party_modules:
        #
        # paths.on_sys_path(HOOK_DIR) SYS_PATH_RE + DIR_ASSIGN_RE paths.on_sys_path(paths.hooks_stop_dir(ROOT)) PATHS_HELPER_RE
        #
        # ONE SUBJECT WAS TRIED FIRST AND IT WAS NOT A CONTROL. With only the `HOOK_DIR` file here, disabling the PATHS_HELPER_RE loop entirely left this gate green: measured, the helper arm is worth 43 first-party names to `check_plan_boxes.py` and 0 to `check_gate_reachability_coverage.py`. A control that passes with the code it guards deleted is a claim about the control.
        #
        # The positive halves alone would pass on a resolver that returned every name in the repository, so each subject also asserts that a module which is genuinely not on disk is still absent.
        resolver_subjects = (
            # file, spelling it must still write, module it must reach
            ("check_gate_reachability_coverage.py", "paths.on_sys_path(HOOK_DIR)", "wl_reggate"),
            ("check_plan_boxes.py", "paths.hooks_stop_dir(", "wl_planfid"),
        )
        for filename, spelling, reached in resolver_subjects:
            subject = REPO / ".ci" / "scripts" / "quality" / filename
            if not subject.is_file():
                failures.append(
                    "the resolver-hop subject %s is missing, so that arm of "
                    "first_party_modules was never exercised" % filename
                )
                continue
            body = subject.read_text(encoding="utf-8")
            if spelling not in body:
                failures.append(
                    "%s no longer writes `%s`, so this control is asserting nothing; "
                    "point it at a file that does" % (filename, spelling)
                )
            fp = first_party_modules(subject, body)
            if reached not in fp:
                failures.append(
                    "%s reaches %s through a resolver hop and it was NOT seen as "
                    "first-party; that spelling is unread again" % (filename, reached)
                )
            if "nonexistent_module_xyz" in fp:
                failures.append(
                    "the first-party set for %s claims a module that is not on disk, "
                    "so its positive half proves nothing" % filename
                )

    return failures


def main() -> int:
    print("Python scripts a workflow runs: are their imports installed?")
    print("=" * 60)

    control_failures = run_controls()
    if control_failures:
        for f in control_failures:
            print(f"{RED}x{NC} control: {f}")
        print(f"{RED}x{NC} the rule itself is broken, so no verdict it produces means anything.")
        return 1
    print(f"{GREEN}v{NC} control fired: a missing install is caught, a present one is not")

    workflow_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not workflow_files:
        print(
            f"{RED}x{NC} no workflow files found; checking nothing exits 0 exactly like checking everything"
        )
        return 1

    findings, steps_scanned = scan(workflow_files)

    # A rule that inspected no Python step passes forever.
    if steps_scanned < 3:
        print(
            f"{RED}x{NC} only {steps_scanned} Python step(s) inspected; the rule has been unhooked"
        )
        return 1

    if findings:
        for wf, job, why in findings:
            print(f"{RED}x{NC} {wf}: job '{job}': {why}")
        print()
        print(
            f"{RED}x{NC} {len(findings)} step(s) run a Python script whose imports the job never installs."
        )
        print("  It will die with ModuleNotFoundError on a clean runner while passing on any")
        print("  machine that happens to have the module. Install it in the job, pinned, and")
        print("  assert the version right after so a failed install surfaces as itself:")
        print(
            '      python3 -m pip install --user --disable-pip-version-check "PyYAML==%s"'
            % _pyyaml_pin()
        )
        print("      python3 -c \"import yaml; print('PyYAML', yaml.__version__)\"")
        return 1

    print(
        f"{GREEN}v{NC} {steps_scanned} Python step(s) across {len(workflow_files)} workflow(s): every import is installed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
