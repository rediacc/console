#!/usr/bin/env python3
"""A workflow job that READS submodule source must CHECK OUT the submodules.

WHY THIS EXISTS. `Tests + Infra / Unit` ran a suite that parses `private/renet/pkg/prune/datastore.go` while its checkout took no submodules at all. It failed with ENOENT on a file it had never fetched, cancelled 26 sibling jobs, and read as a broken test rather than a missing checkout -- so the next reader goes into the test instead of the workflow. Five sibling jobs in the same
file already had the checkout; this one was added without it and nothing noticed.

WHY NO EXISTING GATE CATCHES IT. Every gate here gets a tree where the submodules are present, so the dependency is invisible: the test passes locally, passes in the lane that does check them out, and fails only in the one job that does not. The dependency lives across two files that nothing reads together -- the workflow's checkout step and a test file three call levels away.

WHAT IT CHECKS. For every job in every workflow, it walks what that job can actually execute -- `run:` lines, the repo scripts they name, `npm run` keys resolved through package.json (root and workspaces), and, crucially, the TEST FILES a test runner would sweep. If anything reachable names a real submodule path and the job configures no submodule checkout, that is the finding.

The test-runner hop is the load-bearing one and the reason this is not a grep. The defect was not in `run-unit.sh`; it was in a test file that script runs. A gate that only read the step's own text would have looked right at this bug and reported nothing, which is the failure mode this repo keeps paying for.

WHAT IT DOES NOT DO. It does not check that a submodule checkout is NEEDED -- an unnecessary one costs fetch time, not correctness, and pruning those is a performance question with a different owner.

---- gate ----
step: Workflow submodule deps
needs: python-yaml
selftest: true
---- end gate ----
"""

import json
import os
import pathlib
import re
import shlex
import sys
import tempfile
from collections.abc import Iterable

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = REPO / ".github" / "workflows"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# A job running one of these sweeps a package's test files, so those files are reachable from the job even though no step names them.
TEST_RUNNERS = re.compile(r"\b(vitest|jest|playwright)\b")

# Bounded, because a cycle in npm scripts would otherwise spin forever.
MAX_DEPTH = 6

# How far an `npm run` key is followed. See the note at its use site.
NPM_RESOLVE_DEPTH = 1


def submodule_paths() -> list[str]:
    """Submodule paths from .gitmodules, never a hardcoded list.

    A hardcoded list is how the i18n gates went blind to 379 keys: the set moved and the gate did not.
    """
    gitmodules = REPO / ".gitmodules"
    if not gitmodules.exists():
        return []
    return re.findall(r"^\s*path\s*=\s*(\S+)", gitmodules.read_text(), re.MULTILINE)


def npm_scripts() -> dict[str, str]:
    """Every npm script key in the root package.json and each workspace."""
    out: dict[str, str] = {}
    for pkg in [REPO / "package.json", *sorted(REPO.glob("packages/*/package.json"))]:
        if not pkg.exists():
            continue
        try:
            data = json.loads(pkg.read_text())
        except json.JSONDecodeError:
            continue
        for key, cmd in (data.get("scripts") or {}).items():
            # Root wins on a collision: that is the one `npm run <key>` from the repo root resolves to, which is what a workflow step does.
            out.setdefault(key, cmd)
    return out


def package_test_files(workspace: str | None = None) -> list[pathlib.Path]:
    """Test files, scoped to one workspace when the command named one.

    `npm run test:unit -w @rediacc/cli` runs the CLI's tests and nothing else. Sweeping every package's tests for any job that mentions a runner made quality-static -- which runs shell linters and no tests at all -- inherit a dependency from a package it never touches.
    """
    root = f"packages/{workspace}" if workspace else "packages/*"
    return [
        path
        for pattern in (f"{root}/src/**/*.test.ts", f"{root}/src/**/*.test.tsx")
        for path in REPO.glob(pattern)
    ]


RUNNER_WORDS = {"run", "test", "vitest", "jest", "playwright", "npx", "npm", "exec", "--"}

# Runner flags that take the next word as their value. Any other flag is read as a boolean, so a bare word after it is a filter: reading an unknown flag as value-taking let `--silent src/utils` swallow the directory and narrow the sweep.
VALUE_FLAGS = {
    "-t",
    "-c",
    "-r",
    "-w",
    "--testNamePattern",
    "--reporter",
    "--config",
    "--project",
    "--root",
    "--dir",
    "--outputFile",
    "--shard",
    "--pool",
    "--environment",
    "--mode",
    "--workspace",
}


def _has_other_filter(cmd: str, names: list[str]) -> bool:
    """Whether the command also passes a directory, glob or name filter beside the test files it names.

    `vitest run src/a.test.ts src/utils` runs every test under `src/utils` as well, so narrowing the sweep to `a.test.ts` would leave those unswept. Read after the first named file: a bare word there that is not a flag, the value of a flag in `VALUE_FLAGS`, a shell operator or another named file is a filter. A command that cannot be split reads as filtered, which keeps the whole sweep.
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return True
    start = next((i for i, tok in enumerate(tokens) if tok in names), None)
    if start is None:
        return False
    after_flag = False
    for tok in tokens[start:]:
        if tok in {"&&", "||", ";", "|"}:
            break
        if tok.startswith("-"):
            after_flag = "=" not in tok and tok in VALUE_FLAGS
            continue
        if after_flag:
            after_flag = False
            continue
        if tok not in names and tok not in RUNNER_WORDS:
            return True
    return False


def named_test_files(cmd: str, workspaces: list[str], repo: pathlib.Path | None = None) -> list:
    """The test files a runner command names outright, or [] when it names none.

    `vitest run src/utils/__tests__/x.test.ts` runs that file and nothing else, so sweeping the whole workspace for it charged the job with every other test's reads (quality-secure-storage, 2026-10-13: a job that runs one file was told it reads private/renet through datastore-prune-parser.test.ts). Every named file must resolve under a workspace the job named (or any package when it named none); one that does not resolve gives [], and the caller sweeps as before, so a typo cannot shrink the sweep.
    """
    repo = repo or REPO
    names = re.findall(r"(?<![\w./-])([\w./-]+\.test\.tsx?)\b", cmd)
    if not names or _has_other_filter(cmd, names):
        return []
    found = []
    for name in names:
        roots = [repo / "packages" / ws for ws in workspaces] or sorted(
            (repo / "packages").glob("*")
        )
        hits = [root / name for root in roots if (root / name).is_file()]
        if not hits:
            return []
        found.extend(hits)
    return found


# Build OUTPUTS are not source. A bundler inlines the paths it read at build time, so dist/cli-bundle.cjs contains the string "private/renet/..." without the job ever opening that file. Flagging those would train a reader to ignore this gate, which is worse than not having it.
GENERATED = re.compile(r"(^|/)(dist|build|out|coverage|node_modules|\.cache)(/|$)")


def _referenced(text: str, repo: pathlib.Path | None = None) -> list[tuple[str, pathlib.Path]]:
    """`(token as written, its location in the repo)` for every script path named in a command that exists on disk with its LOCATION inside the repository."""
    root = repo or REPO
    out: list[tuple[str, pathlib.Path]] = []
    for token in re.findall(r"[\w./-]+\.(?:sh|ts|tsx|js|mjs|cjs|py)", text):
        # NOT lstrip("./"): that strips a CHARACTER SET, so ".ci/scripts/x.sh" became "ci/scripts/x.sh", resolved to nothing, and the whole reachability walk stopped at the step text. The gate then passed a replay of the very bug it was written for.
        rel = token.removeprefix("./")
        if GENERATED.search(rel):
            continue
        location = pathlib.Path(os.path.normpath(root / rel))
        if location.is_relative_to(root) and location.is_file():
            out.append((token, location))
    return out


def referenced_repo_files(text: str, repo: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Repo-relative paths named in a command that actually exist on disk, by their LOCATION inside the repository.

    A TOKEN IS JOINED ONTO THE REPO, AND A JOIN CAN LEAVE IT. `REPO / "/tmp/x.sh"` is `/tmp/x.sh` (pathlib drops the left side for an absolute right side), and `REPO / "../x.sh"` climbs out. Either one that happened to exist on disk was walked, and its label (`relative_to(REPO)`) raised `ValueError`, crashing the gate: hookcases.py names `/tmp/rediacc-guard-bashwrite/bash-side-suite.sh`, which the hook tests leave behind (2026-10-11).
    A file outside the repo is not a repo file a job reads, so it is not a candidate.

    THE LOCATION, NOT THE TARGET (review 79a0a35c.1). Containment is judged on the lexically normalised path (`os.path.normpath`), never the resolved one: a repo-internal symlink is a file the job references by a repo path, whatever it points at, and resolving first dropped one whose target lies outside the repo. Where a symlink LEADS is judged separately (`symlinked_reads`). `repo` is the root to read against (the repository by default; the controls pass their own).
    """
    return [location for _token, location in _referenced(text, repo)]


def symlinked_reads(text: str, repo: pathlib.Path | None = None) -> list[str]:
    """The command once more for every symlinked script it names, with that symlink's TARGET written in its place (repo-relative when the target is inside the repository): `bash scripts/run.sh`, where `scripts/run.sh` links into `private/renet`, is read as `bash private/renet/...`. Scanned under the same access context as the command, so a job reaching submodule source through a link is seen (review 79a0a35c.1)."""
    root = repo or REPO
    resolved_root = root.resolve()
    out: list[str] = []
    for token, location in _referenced(text, repo):
        target = location.resolve()
        if target == location.absolute():
            continue
        shown = (
            str(target.relative_to(resolved_root))
            if target.is_relative_to(resolved_root)
            else str(target)
        )
        out.append(text.replace(token, shown))
    return out


def named_workspaces(commands: Iterable[str]) -> list[str]:
    """The workspace names (`-w X`, `--workspace X`, `--workspace=@scope/X`) the walked commands name, sorted, scope removed.

    EVERY workspace named, not the first one found. A caller's command set is a SET, so picking one was nondeterministic: run-unit.sh names @rediacc/shared and @rediacc/cli, and whenever the set yielded shared first the CLI's tests went unswept and the gate passed a replay of the exact bug it was written for.
    """
    return sorted(
        {
            m.group(1)
            for cmd in commands
            for m in re.finditer(r"(?:-w\s+|--workspace[=\s])(?:@[\w-]+/)?([\w-]+)", cmd)
        }
    )


def reachable_text(commands: list[str], scripts: dict[str, str]) -> list[tuple[str, str, bool]]:
    """(label, text, scannable) for everything a job's commands can reach.

    scannable marks the entries whose CONTENT is evidence of a read: the commands a job runs, and the test files a runner sweeps. Script bodies are walked for further commands but not scanned, because naming a path is not reading one.
    """
    seen_cmds: set[str] = set()
    seen_files: set[pathlib.Path] = set()
    out: list[tuple[str, str, bool]] = []
    swept_whole = False
    swept_named: set[pathlib.Path] = set()

    # The queue carries the scannable flag with each entry. Without it a script BODY popped off the queue was relabelled "<step run:>" and scanned as though the job had typed it, which put every false positive straight back after they had just been removed.
    queue = [(c, 0, True) for c in commands]
    while queue:
        cmd, depth, scannable = queue.pop()
        if depth > MAX_DEPTH or cmd in seen_cmds:
            continue
        seen_cmds.add(cmd)
        out.append(("<step run:>" if scannable else "<script body>", cmd, scannable))

        # DEPTH-CAPPED. scripts/ci-runner/manifest.ts lists `npm run <key>` for every gate in the repo as DATA, so walking it once pulled in every gate and attributed account-config-auth to quality-static, which does not run it -- quality-go does, and that job checks out its submodules. A step and the script it runs are within two hops; a manifest reached through another script is
        # further out and is a catalogue, not a call.
        if depth <= NPM_RESOLVE_DEPTH:
            # An npm script IS executed, so its text is scannable -- BUT ONLY IF THE THING THAT NAMED IT WAS. `scannable`, not `True`, and the literal `True` here re-opened the exact hole the queue's own scannable flag was added to close.
            #
            # A referenced FILE body is queued non-scannable because naming a path is not reading one. It then arrived here and promoted every `npm run` inside it back to scannable, so a job that merely NAMES a script which happens to mention `npm run test:unit` was treated as running the tests. That triggered the whole-package test sweep and attributed
            # packages/cli/src/commands/__tests__/datastore-prune-parser.test.ts -- which really does read private/renet/pkg/prune/datastore.go -- to `quality-static`, a job that runs no tests at all. The test's own header names the lane it belongs to: L6 PACKAGES, which does check out submodules.
            #
            # The intended hop still works, because it starts scannable: a STEP running `npm run test:unit` reaches `vitest` with the flag True the whole way down.
            queue.extend(
                (scripts[key], depth + 1, scannable)
                for key in re.findall(r"npm run ([\w:.-]+)", cmd)
                if key in scripts
            )

        # A symlinked script is read where it LEADS as well as where it sits (`symlinked_reads`): judged under the command's own access context, and only when that command is one the job runs.
        if scannable:
            out.extend(
                ("<step run: via a symlink>", via, True)
                for via in symlinked_reads(cmd)
                if via not in seen_cmds
            )

        for path in referenced_repo_files(cmd):
            if path in seen_files:
                continue
            seen_files.add(path)
            try:
                body = path.read_text(errors="replace")
            except OSError:
                continue
            # WALKED, NOT SCANNED. A shell library names paths as constants and is sourced almost everywhere: .ci/config/constants.sh defines a private/renet Dockerfile path and is reachable from ten jobs that never open it. Treating a definition as a read produced ten false positives at once, and a gate that cries wolf gets ignored the one time it is right. Bodies are still WALKED
            # for further commands, which is how `npm run test:unit` reaches `vitest`, and that hop is what catches the real defect.
            out.append((str(path.relative_to(REPO)), body, False))
            queue.append((body, depth + 1, False))

        # THE HOP THAT MATTERS. A test runner reaches files no step names. Only a command the job RUNS triggers the sweep. Letting a walked script body trigger it made every job that transitively mentions vitest sweep all 227 test files, which flagged eight jobs that never run a test.
        if scannable and not swept_whole and TEST_RUNNERS.search(cmd):
            workspaces = named_workspaces(seen_cmds)
            named = named_test_files(cmd, workspaces)
            if named:
                # A command that names its files sweeps those, and ONLY those: a later whole-workspace runner command in the same job is still swept in full.
                sweep = [path for path in named if path not in swept_named]
                swept_named.update(sweep)
            else:
                swept_whole = True
                # No workspace named means every package, which package_test_files spells as None.
                scopes: list[str | None] = list(workspaces) or [None]
                sweep = [path for ws in scopes for path in package_test_files(ws)]
            for path in sweep:
                try:
                    # SCANNED: a test runner really does execute these.
                    out.append(
                        (str(path.relative_to(REPO)), path.read_text(errors="replace"), True)
                    )
                except OSError:
                    continue

    return out


# A path NAMED is not a path READ. check-locale-sources.ts explains itself with the sentence "the ONE deliberate copy: private/account/Dockerfile compiles this
# package in isolation", and nothing there opens anything. Flagging prose would
# make this gate noise, so a hit only counts when the same line also carries something that actually reaches the filesystem or executes the file.
ACCESS = re.compile(
    r"readFileSync|readFile|existsSync|statSync|createReadStream|"
    r"path\.resolve|path\.join|fileURLToPath|"
    r"\bopen\(|Path\(|\bcat\b|\bsource\b|"
    r"\btsx\b|\bnode\b|\bbash\b|\bsh\b|\bgo run\b|\bpython3?\b"
)


# The window is LINES, not one line, and that is the whole difference between a gate that works and one that ships green. The defect this exists for looks like
#     const RENET_PRUNE_GO = path.resolve(
# path.dirname(fileURLToPath(import.meta.url)), '../../../../../private/renet/pkg/prune/datastore.go'
#     );
# where the path literal sits alone on its line and every access verb is above it. A one-line window read straight past the real bug: replaying it against the gate was the only reason this was caught before shipping.
ACCESS_WINDOW = 4

# An existence check next to the read means the caller already handles absence.
GUARDED = re.compile(
    r"existsSync|\.exists\(|isFile\(|skipIf|skipUnless|"
    r"test -[fder]\b|\[ -[fder] |os\.path\.exists|pathlib\.Path\([^)]*\)\.exists"
)


LINE_COMMENT = re.compile(r"(^|\s)(//|#)\s.*$", re.MULTILINE)


def strip_comments(text: str) -> str:
    """Blank out line comments, keeping line COUNT so windows still line up.

    A comment that cites a file is documentation, not a dependency: datastore-relocate.test.ts explains an ordering rule by pointing at "private/renet/pkg/datastore/adopt.go:22-28" and never opens it. Treating a citation as a read punishes the habit of citing sources, which this repo wants more of, not less.
    """
    return LINE_COMMENT.sub(lambda m: m.group(1), text)


def first_read(text: str, sub_pattern: re.Pattern) -> re.Match | None:
    """The first submodule path used in a file-ACCESS context, if any."""
    text = strip_comments(text)
    lines = text.splitlines()
    starts = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1

    for hit in sub_pattern.finditer(text):
        idx = 0
        for i, start in enumerate(starts):
            if start > hit.start():
                break
            idx = i
        lo = max(0, idx - ACCESS_WINDOW)
        hi = min(len(lines), idx + ACCESS_WINDOW + 1)
        window = "\n".join(lines[lo:hi])
        # A GUARDED read is not a dependency. crypto.test.ts wraps its cross-language fixtures in describe.skipIf(!existsSync(...)) precisely so the suite still runs without the account submodule, and flagging that would punish the correct pattern. The datastore-prune test throws on purpose instead, and says so in its own comment, which is what makes it a real dependency rather
        # than an optional one.
        if GUARDED.search(window):
            continue
        if ACCESS.search(window):
            return hit
    return None


def job_takes_submodules(job: dict) -> bool:
    # A job may init its submodules with an explicit `git submodule update` instead of actions/checkout's flag, and housekeeping.yml does exactly that. Recognising only the actions/checkout form would report a job that is perfectly correct, and a gate that cries wolf gets ignored the one time it is right.
    for step in job.get("steps") or []:
        if isinstance(step, dict) and re.search(
            r"git submodule (update|init)", str(step.get("run") or "")
        ):
            return True
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        if "actions/checkout" not in uses:
            continue
        with_block = step.get("with") or {}
        value = str(with_block.get("submodules", "")).strip().lower()
        if value and value not in {"false", "none", ""}:
            return True
    return False


def job_commands(job: dict) -> list[str]:
    return [
        str(step["run"])
        for step in job.get("steps") or []
        if isinstance(step, dict) and step.get("run")
    ]


def scan(workflow_files: list[pathlib.Path], subs: list[str], scripts: dict[str, str]):
    """Returns (findings, jobs_scanned)."""
    findings = []
    jobs_scanned = 0
    # The lookbehind rejects a WORD character only. It must NOT reject a preceding slash: the defect this gate exists for names its file as '../../../../../private/renet/pkg/prune/datastore.go', and excluding a leading slash made the rule blind to every relative reference -- which is most of them. The gate ran green against a replay of the real bug until this was found, so the
    # replay, not the green, is what proved it.
    sub_pattern = (
        re.compile(r"(?<![\w])(" + "|".join(re.escape(s) for s in subs) + r")/[\w./-]+")
        if subs
        else None
    )
    if sub_pattern is None:
        return findings, jobs_scanned

    for wf in workflow_files:
        try:
            doc = yaml.safe_load(wf.read_text())
        except yaml.YAMLError as exc:
            # A workflow this gate cannot parse is a build failure elsewhere; do not let it pass as "no violations found".
            findings.append((str(wf), "<unparseable>", f"cannot parse: {exc}"))
            continue
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict) or not job.get("steps"):
                continue
            jobs_scanned += 1
            if job_takes_submodules(job):
                continue
            commands = job_commands(job)
            if not commands:
                continue
            for label, text, scannable in reachable_text(commands, scripts):
                if not scannable:
                    continue
                hit = first_read(text, sub_pattern)
                if hit:
                    # The controls scan a planted file outside the repo, so this must not assume the path is relative to it.
                    try:
                        where = str(wf.relative_to(REPO))
                    except ValueError:
                        where = str(wf)
                    findings.append((where, job_name, f"{label} reads {hit.group(0)}"))
                    break
    return findings, jobs_scanned


def run_controls(subs: list[str], scripts: dict[str, str]) -> list[str]:
    """Prove the rule can FIRE and that it is not always firing.

    Both directions, because always-on and always-off are different bugs and a control that only checks one of them certifies half a gate.
    """
    failures: list[str] = []
    if not subs:
        return [".gitmodules named no submodules, so the rule matches nothing and passes forever"]

    # A runner command that names its files is swept as those files only, and a name that does not resolve falls back to the whole sweep.
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "repo"
        (root / "packages" / "cli" / "src").mkdir(parents=True)
        one = root / "packages" / "cli" / "src" / "one.test.ts"
        one.write_text("// one\n")
        if named_test_files("vitest run src/one.test.ts", ["cli"], root) != [one]:
            failures.append("a runner command naming one test file was not narrowed to that file")
        if named_test_files("vitest run src/missing.test.ts", ["cli"], root) != []:
            failures.append("a named test file that does not exist still narrowed the sweep")
        if named_test_files("vitest run", ["cli"], root) != []:
            failures.append("a runner command naming no file was narrowed")
        # A directory or name filter beside the file runs more than the file, so the sweep is not narrowed.
        if named_test_files("vitest run src/one.test.ts src/utils", ["cli"], root) != []:
            failures.append("a runner command that also passes a directory filter was narrowed")
        if named_test_files("vitest run src/one.test.ts -t 'a name'", ["cli"], root) != [one]:
            failures.append("a flag's value was read as a second filter")
        # A boolean flag between the file and the directory does not consume the directory.
        if named_test_files("vitest run src/one.test.ts --silent src/utils", ["cli"], root) != []:
            failures.append(
                "a boolean flag before a directory filter hid the filter, narrowing the sweep"
            )
    # Every spelling of a workspace flag is parsed, `--workspace=@scope/pkg` included.
    spelled = named_workspaces(["npm test -w @rediacc/shared", "npm test --workspace=@rediacc/cli"])
    if spelled != ["cli", "shared"]:
        failures.append(f"workspace flags were parsed as {spelled}, not ['cli', 'shared']")

    # A path OUTSIDE the repository is never a repo file, however it is spelled (2026-10-11: an absolute `/tmp/...sh` token that existed on disk crashed the gate). Planted outside a fake repo root that holds one real script, so the in-repo direction is asserted too.
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "inside.sh").write_text("echo in\n")
        outside = pathlib.Path(tmp) / "outside.sh"
        outside.write_text("echo out\n")
        named = f"bash {outside} && bash ../outside.sh && bash scripts/inside.sh"
        got = referenced_repo_files(named, root)
        if got != [root / "scripts" / "inside.sh"]:
            failures.append(
                "an absolute or `..` path outside the repo was read as a repo file, or the one "
                f"inside was missed: {[str(g) for g in got]}"
            )
        # A repo-internal SYMLINK whose target lies outside the repo is a file the job references by its repo location (review 79a0a35c.1): kept, by that location.
        (root / "scripts" / "linked.sh").symlink_to(outside)
        got = referenced_repo_files("bash scripts/linked.sh", root)
        if got != [root / "scripts" / "linked.sh"]:
            failures.append(
                "a repo symlink whose target lies outside the repo was dropped: "
                f"{[str(g) for g in got]}"
            )
        # ...and where a symlink LEADS is judged too: a link into a submodule is a read of submodule source under the naming command's own access context.
        if subs:
            target = root / subs[0] / "tool.sh"
            target.parent.mkdir(parents=True)
            target.write_text("echo tool\n")
            (root / "scripts" / "tool.sh").symlink_to(target)
            sub_rx = re.compile(r"(?<![\w])(" + re.escape(subs[0]) + r")/[\w./-]+")
            reads = symlinked_reads("bash scripts/tool.sh", root)
            if not any(first_read(r, sub_rx) for r in reads):
                failures.append(
                    f"a repo symlink into {subs[0]} was not read as submodule source: {reads}"
                )

    sub = subs[0]
    with tempfile.TemporaryDirectory() as tmp:
        planted = pathlib.Path(tmp) / "planted.yml"

        planted.write_text(
            "jobs:\n"
            "  bad:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v7\n"
            f"      - run: cat {sub}/some/file.go\n"
        )
        found, _ = scan([planted], subs, scripts)
        if not found:
            failures.append(
                "a job reading submodule source with NO submodule checkout was not flagged"
            )

        planted.write_text(
            "jobs:\n"
            "  good:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v7\n"
            "        with:\n"
            "          submodules: true\n"
            f"      - run: cat {sub}/some/file.go\n"
        )
        found, _ = scan([planted], subs, scripts)
        if found:
            failures.append(
                "a job WITH a submodule checkout was flagged; the rule would fire on everything"
            )

        planted.write_text(
            "jobs:\n"
            "  unrelated:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v7\n"
            "      - run: echo hello\n"
        )
        found, _ = scan([planted], subs, scripts)
        if found:
            failures.append("a job touching no submodule source was flagged")

    return failures


def main() -> int:
    print("Workflow jobs that read submodule source: do they check it out?")
    print("=" * 62)

    subs = submodule_paths()
    scripts = npm_scripts()

    control_failures = run_controls(subs, scripts)
    if control_failures:
        for f in control_failures:
            print(f"{RED}x{NC} control: {f}")
        print(f"{RED}x{NC} the rule itself is broken, so no verdict it produces means anything.")
        return 1
    print(f"{GREEN}v{NC} control fired: a missing checkout is caught, a present one is not")

    workflow_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not workflow_files:
        print(
            f"{RED}x{NC} no workflow files found; linting nothing exits 0 exactly like linting everything"
        )
        return 1

    findings, jobs_scanned = scan(workflow_files, subs, scripts)

    # A rule that inspected no jobs passes forever.
    if jobs_scanned < 5:
        print(
            f"{RED}x{NC} only {jobs_scanned} job(s) inspected; the rule has been unhooked from the workflows"
        )
        return 1

    if findings:
        for wf, job, why in findings:
            print(f"{RED}x{NC} {wf}: job '{job}': {why}")
        print()
        print(f"{RED}x{NC} {len(findings)} job(s) read submodule source without checking it out.")
        print("  The job will fail on a file it never fetched, which reads as a broken test")
        print("  rather than a missing checkout. Add the app-token + submodule checkout that")
        print("  sibling jobs already use:")
        print("      - uses: ./.github/actions/bws-secrets")
        print("        with:")
        print("          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}")
        print("          secrets: |")
        print("            GITHUB_APP_PRIVATE_KEY > BWS_GITHUB_APP_PRIVATE_KEY")
        print("            GITHUB_APP_ID > BWS_APP_ID")
        print("      - uses: ./.github/actions/app-token")
        print("        id: app-token")
        print("        with:")
        print("          client-id: ${{ env.BWS_APP_ID }}")
        print("          private-key: ${{ env.BWS_GITHUB_APP_PRIVATE_KEY }}")
        print("          repositories: console,renet,account,elite,homebrew-tap")
        print("      - uses: actions/checkout@<pinned>")
        print("        with:")
        print("          submodules: true")
        print("          token: ${{ steps.app-token.outputs.token }}")
        return 1

    print(
        f"{GREEN}v{NC} {jobs_scanned} job(s) across {len(workflow_files)} workflow(s): every reader checks out its submodules"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
