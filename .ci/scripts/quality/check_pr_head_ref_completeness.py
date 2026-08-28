#!/usr/bin/env python3
"""Every script that PREFERS PR_HEAD_REF must be invoked by a step that SETS it.

WHY THIS EXISTS. `check-pr-epic-block.ts`, `check-pr-task-trailers.ts` and
`wl_git.py` all already preferred `PR_HEAD_REF` (falling back to
`GITHUB_HEAD_REF`, then a bare `git` derivation) before this repo's own
workflow steps caught up. The pattern was CORRECT at the reader; the gap was
always at the SETTER: a workflow step invoking one of these scripts without a
`PR_HEAD_REF` (or an explicit `GITHUB_HEAD_REF: ${{ github.head_ref }}`) in its
`env:` block. On this repo's `workflow_call` chain, the runner's own default
`GITHUB_HEAD_REF` does not reliably materialise, so an unset pair means the
script falls all the way to `git branch --show-current`, which is EMPTY on the
detached checkout every pull_request run uses -- silently skipping real work
(`check-pr-epic-block.ts`) or silently degrading to a coarser check
(`check-review-report-replies.sh`).

THIS RECURRED THREE TIMES IN ONE SESSION (2026-08-28: `891ff49db`,
`946e0e6da`, `74114a26b`), each found by hand-sweeping `grep -rn
PR_HEAD_REF`. A check-first gate that cannot fail is worth nothing, so this
checks BOTH directions with real fixtures below, not merely one reader against
one setter.

SCOPE. Only `.ci/scripts/**` and `scripts/**`, and only files that are not
themselves test fixtures (`test-*.sh`, `*.control.ts`, anything under a
`test/` or `__tests__/` directory) -- those set the variable to drive a
specific scenario, they are not a real CI caller needing a workflow setter.
`.claude/hooks/**` is out of scope entirely: those run as local git hooks, not
CI workflow steps, and have no `run:` line to resolve.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PACKAGE_JSON = REPO_ROOT / "package.json"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

SCAN_ROOTS = [".ci/scripts", "scripts"]
EXCLUDE_DIR_PARTS = {"test", "__tests__", "gates", "fixtures"}

BASH_PREFERENCE = re.compile(r"\$\{PR_HEAD_REF(?::-|\})")
TS_PREFERENCE = re.compile(r"process\.env\.PR_HEAD_REF")

# A reader that fails LOUD when the variable is unset (rather than silently
# falling through to git) has already solved the problem itself and does not
# need a workflow-level setter. Matched as "the reader's own text names both
# the variable and an explicit refusal", so a real future case is still
# caught if the loud-failure text ever drifts away from the variable.
LOUD_FAILURE = re.compile(r"PR_HEAD_REF[^\n]{0,80}(unset|refus|is required)", re.IGNORECASE)


def is_fixture_path(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIR_PARTS:
        return True
    return rel.name.startswith("test-") or rel.name.endswith(".control.ts")


def find_readers() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in (".sh", ".ts"):
                continue
            rel = path.relative_to(REPO_ROOT)
            if is_fixture_path(rel.relative_to(root)):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if BASH_PREFERENCE.search(text) or TS_PREFERENCE.search(text):
                if LOUD_FAILURE.search(text):
                    continue
                out.append(rel)
    return sorted(set(out))


def npm_script_map() -> dict[str, str]:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return dict(data.get("scripts", {}))


def step_invokes(step: dict, reader: Path, npm_map: dict[str, str]) -> bool:
    run = step.get("run")
    if not isinstance(run, str):
        return False
    rel_str = str(reader)
    if rel_str in run:
        return True
    for m in re.finditer(r"npm run ([a-zA-Z0-9:_-]+)", run):
        cmd = npm_map.get(m.group(1), "")
        if rel_str in cmd:
            return True
    return False


def step_sets_var(step: dict) -> bool:
    env = step.get("env")
    if not isinstance(env, dict):
        return False
    return "PR_HEAD_REF" in env or "GITHUB_HEAD_REF" in env


def find_invoking_steps(reader: Path, npm_map: dict[str, str]) -> list[tuple[str, str, str, bool]]:
    """(workflow_file, job_id, step_name, sets_var) for every step invoking reader."""
    hits: list[tuple[str, str, str, bool]] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        jobs = doc.get("jobs") or {}
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if step_invokes(step, reader, npm_map):
                    hits.append(
                        (wf.name, job_id, step.get("name", "(unnamed)"), step_sets_var(step))
                    )
    return hits


def fail(msg: str) -> None:
    print(f"{RED}✗ CONTROL FAILED{NC}: {msg}", file=sys.stderr)
    print("  A clean result below would mean nothing, so this gate refuses.", file=sys.stderr)
    sys.exit(1)


def controls() -> None:
    """Both directions, on a synthetic fixture, before anything real is judged."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        reader = tdp / "fake-reader.sh"
        reader.write_text('branch="${PR_HEAD_REF:-$(git branch --show-current)}"\n')

        missing_wf = tdp / "missing.yml"
        missing_wf.write_text(
            f"jobs:\n  j:\n    steps:\n      - name: runs it\n        run: bash {reader}\n"
        )
        present_wf = tdp / "present.yml"
        present_wf.write_text(
            "jobs:\n"
            "  j:\n"
            "    steps:\n"
            "      - name: runs it\n"
            f"        run: bash {reader}\n"
            "        env:\n"
            "          PR_HEAD_REF: x\n"
        )

        def hits_for(wf_dir: Path) -> list[tuple[str, str, str, bool]]:
            out = []
            for wf in wf_dir.glob("*.yml"):
                doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
                for job in (doc.get("jobs") or {}).values():
                    out.extend(
                        (wf.name, "j", step.get("name"), step_sets_var(step))
                        for step in job.get("steps") or []
                        if step_invokes(step, reader, {})
                    )
            return out

        missing_dir = tdp / "missing_only"
        missing_dir.mkdir()
        (missing_dir / "missing.yml").write_text(missing_wf.read_text())
        got_missing = hits_for(missing_dir)
        if not got_missing or got_missing[0][3] is not False:
            fail("a step invoking the reader WITHOUT PR_HEAD_REF was not detected as missing it")

        present_dir = tdp / "present_only"
        present_dir.mkdir()
        (present_dir / "present.yml").write_text(present_wf.read_text())
        got_present = hits_for(present_dir)
        if not got_present or got_present[0][3] is not True:
            fail("a step invoking the reader WITH PR_HEAD_REF was not detected as satisfying it")

        # The reader-detection regex itself: must fire on the bash form, and
        # a loud-failure reader must be exempt.
        if not BASH_PREFERENCE.search(reader.read_text()):
            fail("the bash preference pattern did not match its own fixture")
        loud = tdp / "loud.sh"
        loud.write_text(
            '[ -n "$PR_HEAD_REF" ] || { echo "PR_HEAD_REF is unset, refusing"; exit 1; }\n'
        )
        if not LOUD_FAILURE.search(loud.read_text()):
            fail("a reader that fails loud on a missing PR_HEAD_REF was not recognised as exempt")


def main() -> int:
    controls()

    npm_map = npm_script_map()
    readers = find_readers()
    if len(readers) < 2:
        print(
            f"{RED}✗{NC} only {len(readers)} PR_HEAD_REF reader(s) found; the scan is likely broken, not the repo.",
            file=sys.stderr,
        )
        return 1

    offenders: list[str] = []
    unresolved: list[str] = []
    checked = 0

    for reader in readers:
        steps = find_invoking_steps(reader, npm_map)
        if not steps:
            # Not every reader is invoked from a workflow (e.g. a script only
            # ever run by hand or by another script). Nothing to check.
            unresolved.append(str(reader))
            continue
        checked += 1
        for wf_name, job_id, step_name, sets_var in steps:
            if not sets_var:
                offenders.append(
                    f"{reader}: {wf_name}#{job_id} step {step_name!r} sets neither PR_HEAD_REF nor GITHUB_HEAD_REF"
                )

    for line in offenders:
        print(f"{RED}✗{NC} {line}", file=sys.stderr)

    if offenders:
        print(
            f"\n{RED}✗{NC} {len(offenders)} step(s) invoke a PR_HEAD_REF-preferring script without setting it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{GREEN}✓{NC} {checked} PR_HEAD_REF reader(s) all have a setter in every invoking step "
        f"({len(unresolved)} not invoked from any workflow, nothing to check)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
