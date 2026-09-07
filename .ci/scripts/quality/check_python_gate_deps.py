#!/usr/bin/env python3
"""A Python script a workflow RUNS must have its third-party imports installed.

WHY THIS EXISTS. check_workflow_submodule_deps.py imported PyYAML, ran green on
the author's machine, and died on the runner with ModuleNotFoundError. The
author's environment had the module; a clean Ubuntu runner does not. Nothing
compared what a script imports against what its job installs, so the gap was
invisible until the job crashed -- and it crashed in the commit that added a
gate against checks which silently do not run.

WHY A DOCUMENT WAS NOT ENOUGH. The obvious remedy is a line in TRAPS.md saying
"install your dependencies". A document an agent can skip is not a control, and
this repo has the receipts: the stop-hook suite's own setup() carried a comment
recording that 30 cases were once lost to an inherited GITHUB_ACTIONS, and a new
call site was still added without the pin. The lesson was written down and then
walked past. This asserts the property instead.

WHAT IT CHECKS. For every workflow step that runs a repo .py file, it reads that
file's top-level imports, drops the standard library and the script's own
neighbours, and requires anything left to be named by a `pip install` earlier in
the same job.

WHAT IT DOES NOT DO. It does not follow imports transitively. A gate that runs
its own helper module is one hop from this one, and the honest report of that
limit belongs here rather than in a comment nobody reads: if a gate grows a
helper with its own third-party import, this will not see it.

---- gate ----
step: Python gate deps
needs: python-yaml
selftest: true
---- end gate ----
"""

import pathlib
import re
import sys
import tempfile

import yaml


def _pyyaml_pin():
    """The PyYAML version, read from the ONE place it is defined.

    These strings are advice printed to a human, but a hardcoded version in
    advice is still a second definition: it drifts silently, and the person
    following it installs the wrong thing while believing the gate told them to.
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


# Directory names a script puts on sys.path, so its cross-directory imports can
# be recognised as first-party.
# THE NAMED-VARIABLE FORM. `[^)]*?` could not cross the `)` of a nested call, so
# `sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))` matched NOTHING and
# the wl_* modules those five scripts import read as third-party dependencies the
# gate would demand somebody pip install. Same defect as PARENTS_RE's first draft,
# in the line right above it. `.*?` spans the call; the variable is still required
# to be an ALL-CAPS name, which is what keeps this from matching arbitrary text.
SYS_PATH_RE = re.compile(r"sys\.path\.(?:insert|append)\(.*?([A-Z_]+)\b")
# `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[N]))`, the
# inline form; the capture is N.
PARENTS_RE = re.compile(r"sys\.path\.(?:insert|append)\(.*?parents\[(\d+)\]")
DIR_ASSIGN_RE = re.compile(r"^([A-Z_]+)\s*=\s*(.+)$", re.MULTILINE)


def first_party_modules(script: pathlib.Path, body: str) -> set[str]:
    """Module names importable as FIRST-PARTY from this script.

    Its own directory, plus any directory it inserts into sys.path --
    check_agent_hint_liveness.py imports wl_agents from .claude/hooks/stop that
    way, and a same-directory-only test called that a third-party dependency.

    Scanning the WHOLE repo instead was tried and is worse: three vendored
    .venv trees contain a yaml.py, which made PyYAML look first-party and broke
    this gate's own control. A first-party set that swallows the very module the
    control depends on is not a widening, it is a hole.
    """
    names = {p.stem for p in script.parent.glob("*.py")}
    # THE `/`-JOIN FORM, resolved from the sys.path LINE ITSELF rather than from a
    # separate assignment: `sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))`.
    # Five scripts write this and their wl_* imports still read as third-party after
    # SYS_PATH_RE was widened, because DIR_ASSIGN_RE looks for the literals on the
    # variable's ASSIGNMENT line and here they are on the insert line.
    for line in body.split("\n"):
        if "sys.path" not in line or "/" not in line:
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
            # The literals are path PARTS to be joined, not alternatives.
            # HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
            # yields three fragments, and testing each alone finds no directory
            # at all, so the import stayed unrecognised.
            parts = [a or b for a, b in re.findall(r'"([^"]+)"|\'([^\']+)\'', value)]
            if not parts:
                continue
            candidate = REPO.joinpath(*[part.strip("/") for part in parts])
            if candidate.is_dir():
                names |= {p.stem for p in candidate.glob("*.py")}

    # THE INLINE BOOTSTRAP, which is the idiom this repo actually writes and
    # which the named-variable path above cannot see:
    #     sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    # Eight scripts use it, and a script that puts the package root on the path
    # and then imports the package was being called a third-party dependency,
    # with the gate demanding somebody `pip install rediacc_ci`. That is the
    # same hole the docstring above describes, one spelling further along.
    #
    # PACKAGES AS WELL AS MODULES: `parents[N]` here points at a directory whose
    # children are packages (`rediacc_ci/`), not loose `.py` files, so a
    # `glob("*.py")` finds nothing at all and the widening would be silent.
    for depth in PARENTS_RE.findall(body):
        try:
            root = script.resolve().parents[int(depth)]
        except (IndexError, ValueError):
            continue
        if not root.is_dir():
            continue
        names |= {p.stem for p in root.glob("*.py")}
        names |= {d.name for d in root.iterdir() if (d / "__init__.py").is_file()}
    return names


def third_party_imports(script: pathlib.Path) -> set[str]:
    """Top-level module names that are neither stdlib nor a local neighbour."""
    try:
        body = script.read_text(errors="replace")
    except OSError:
        return set()
    names = set(IMPORT_RE.findall(body))
    stdlib = set(sys.stdlib_module_names)
    # LOCAL means anywhere in this repo, not just the script's own folder.
    # check_agent_hint_liveness.py lives in .ci/scripts/quality and imports
    # wl_agents from .claude/hooks/stop via a sys.path insert, so a
    # same-directory test called a first-party module third-party and demanded
    # somebody pip install it.
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
                # A step may install and then use in one block, so its own pip
                # lines count for itself. Order within a step is the author's
                # problem; order across steps is what this checks.
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
