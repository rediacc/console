#!/usr/bin/env python3
"""A workflow job that READS submodule source must CHECK OUT the submodules.

WHY THIS EXISTS. `Tests + Infra / Unit` ran a suite that parses
`private/renet/pkg/prune/datastore.go` while its checkout took no submodules at
all. It failed with ENOENT on a file it had never fetched, cancelled 26 sibling
jobs, and read as a broken test rather than a missing checkout -- so the next
reader goes into the test instead of the workflow. Five sibling jobs in the same
file already had the checkout; this one was added without it and nothing noticed.

WHY NO EXISTING GATE CATCHES IT. Every gate here gets a tree where the
submodules are present, so the dependency is invisible: the test passes locally,
passes in the lane that does check them out, and fails only in the one job that
does not. The dependency lives across two files that nothing reads together --
the workflow's checkout step and a test file three call levels away.

WHAT IT CHECKS. For every job in every workflow, it walks what that job can
actually execute -- `run:` lines, the repo scripts they name, `npm run` keys
resolved through package.json (root and workspaces), and, crucially, the TEST
FILES a test runner would sweep. If anything reachable names a real submodule
path and the job configures no submodule checkout, that is the finding.

The test-runner hop is the load-bearing one and the reason this is not a grep.
The defect was not in `run-unit.sh`; it was in a test file that script runs.
A gate that only read the step's own text would have looked right at this bug
and reported nothing, which is the failure mode this repo keeps paying for.

WHAT IT DOES NOT DO. It does not check that a submodule checkout is NEEDED --
an unnecessary one costs fetch time, not correctness, and pruning those is a
performance question with a different owner.
"""

import json
import pathlib
import re
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = REPO / ".github" / "workflows"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# A job running one of these sweeps a package's test files, so those files are
# reachable from the job even though no step names them.
TEST_RUNNERS = re.compile(r"\b(vitest|jest|playwright)\b")

# Bounded, because a cycle in npm scripts would otherwise spin forever.
MAX_DEPTH = 6

# How far an `npm run` key is followed. See the note at its use site.
NPM_RESOLVE_DEPTH = 1


def submodule_paths() -> list[str]:
    """Submodule paths from .gitmodules, never a hardcoded list.

    A hardcoded list is how the i18n gates went blind to 379 keys: the set moved
    and the gate did not.
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
            # Root wins on a collision: that is the one `npm run <key>` from the
            # repo root resolves to, which is what a workflow step does.
            out.setdefault(key, cmd)
    return out


def package_test_files(workspace: str | None = None) -> list[pathlib.Path]:
    """Test files, scoped to one workspace when the command named one.

    `npm run test:unit -w @rediacc/cli` runs the CLI's tests and nothing else.
    Sweeping every package's tests for any job that mentions a runner made
    quality-static -- which runs shell linters and no tests at all -- inherit a
    dependency from a package it never touches.
    """
    root = f"packages/{workspace}" if workspace else "packages/*"
    return [
        path
        for pattern in (f"{root}/src/**/*.test.ts", f"{root}/src/**/*.test.tsx")
        for path in REPO.glob(pattern)
    ]


# Build OUTPUTS are not source. A bundler inlines the paths it read at build
# time, so dist/cli-bundle.cjs contains the string "private/renet/..." without
# the job ever opening that file. Flagging those would train a reader to ignore
# this gate, which is worse than not having it.
GENERATED = re.compile(r"(^|/)(dist|build|out|coverage|node_modules|\.cache)(/|$)")


def referenced_repo_files(text: str) -> list[pathlib.Path]:
    """Repo-relative paths named in a command that actually exist on disk."""
    out: list[pathlib.Path] = []
    for token in re.findall(r"[\w./-]+\.(?:sh|ts|tsx|js|mjs|cjs|py)", text):
        # NOT lstrip("./"): that strips a CHARACTER SET, so ".ci/scripts/x.sh"
        # became "ci/scripts/x.sh", resolved to nothing, and the whole
        # reachability walk stopped at the step text. The gate then passed a
        # replay of the very bug it was written for.
        rel = token.removeprefix("./")
        if GENERATED.search(rel):
            continue
        candidate = REPO / rel
        if candidate.is_file():
            out.append(candidate)
    return out


def reachable_text(commands: list[str], scripts: dict[str, str]) -> list[tuple[str, str, bool]]:
    """(label, text, scannable) for everything a job's commands can reach.

    scannable marks the entries whose CONTENT is evidence of a read: the commands
    a job runs, and the test files a runner sweeps. Script bodies are walked for
    further commands but not scanned, because naming a path is not reading one.
    """
    seen_cmds: set[str] = set()
    seen_files: set[pathlib.Path] = set()
    out: list[tuple[str, str]] = []
    swept_tests = False

    # The queue carries the scannable flag with each entry. Without it a script
    # BODY popped off the queue was relabelled "<step run:>" and scanned as
    # though the job had typed it, which put every false positive straight back
    # after they had just been removed.
    queue = [(c, 0, True) for c in commands]
    while queue:
        cmd, depth, scannable = queue.pop()
        if depth > MAX_DEPTH or cmd in seen_cmds:
            continue
        seen_cmds.add(cmd)
        out.append(("<step run:>" if scannable else "<script body>", cmd, scannable))

        # DEPTH-CAPPED. scripts/ci-runner/manifest.ts lists `npm run <key>` for
        # every gate in the repo as DATA, so walking it once pulled in every
        # gate and attributed account-config-auth to quality-static, which does
        # not run it -- quality-go does, and that job checks out its submodules.
        # A step and the script it runs are within two hops; a manifest reached
        # through another script is further out and is a catalogue, not a call.
        if depth <= NPM_RESOLVE_DEPTH:
            # An npm script IS executed, so its text is scannable.
            queue.extend(
                (scripts[key], depth + 1, True)
                for key in re.findall(r"npm run ([\w:.-]+)", cmd)
                if key in scripts
            )

        for path in referenced_repo_files(cmd):
            if path in seen_files:
                continue
            seen_files.add(path)
            try:
                body = path.read_text(errors="replace")
            except OSError:
                continue
            # WALKED, NOT SCANNED. A shell library names paths as constants and is
            # sourced almost everywhere: .ci/config/constants.sh defines a
            # private/renet Dockerfile path and is reachable from ten jobs that
            # never open it. Treating a definition as a read produced ten false
            # positives at once, and a gate that cries wolf gets ignored the one
            # time it is right. Bodies are still WALKED for further commands,
            # which is how `npm run test:unit` reaches `vitest`, and that hop is
            # what catches the real defect.
            out.append((str(path.relative_to(REPO)), body, False))
            queue.append((body, depth + 1, False))

        # THE HOP THAT MATTERS. A test runner reaches files no step names.
        # Only a command the job RUNS triggers the sweep. Letting a walked
        # script body trigger it made every job that transitively mentions
        # vitest sweep all 227 test files, which flagged eight jobs that never
        # run a test.
        if not swept_tests and scannable and TEST_RUNNERS.search(cmd):
            swept_tests = True
            # Scope to the workspace the job named, if it named one. The -w flag
            # may sit on the invoking command rather than the resolved script, so
            # look across everything walked so far.
            # EVERY workspace named, not the first one found. seen_cmds is a
            # SET, so picking one was nondeterministic: run-unit.sh names
            # @rediacc/shared and @rediacc/cli, and whenever the set yielded
            # shared first the CLI's tests went unswept and the gate passed a
            # replay of the exact bug it was written for.
            workspaces = sorted(
                {
                    m.group(1)
                    for cmd_seen in seen_cmds
                    for m in re.finditer(r"-w\s+(?:@[\w-]+/)?([\w-]+)", cmd_seen)
                }
            )
            sweep = [path for ws in (workspaces or [None]) for path in package_test_files(ws)]
            for path in sweep:
                try:
                    # SCANNED: a test runner really does execute these.
                    out.append(
                        (str(path.relative_to(REPO)), path.read_text(errors="replace"), True)
                    )
                except OSError:
                    continue

    return out


# A path NAMED is not a path READ. check-locale-sources.ts explains itself with
# the sentence "the ONE deliberate copy: private/account/Dockerfile compiles this
# package in isolation", and nothing there opens anything. Flagging prose would
# make this gate noise, so a hit only counts when the same line also carries
# something that actually reaches the filesystem or executes the file.
ACCESS = re.compile(
    r"readFileSync|readFile|existsSync|statSync|createReadStream|"
    r"path\.resolve|path\.join|fileURLToPath|"
    r"\bopen\(|Path\(|\bcat\b|\bsource\b|"
    r"\btsx\b|\bnode\b|\bbash\b|\bsh\b|\bgo run\b|\bpython3?\b"
)


# The window is LINES, not one line, and that is the whole difference between a
# gate that works and one that ships green. The defect this exists for looks like
#     const RENET_PRUNE_GO = path.resolve(
#       path.dirname(fileURLToPath(import.meta.url)),
#       '../../../../../private/renet/pkg/prune/datastore.go'
#     );
# where the path literal sits alone on its line and every access verb is above
# it. A one-line window read straight past the real bug: replaying it against
# the gate was the only reason this was caught before shipping.
ACCESS_WINDOW = 4

# An existence check next to the read means the caller already handles absence.
GUARDED = re.compile(
    r"existsSync|\.exists\(|isFile\(|skipIf|skipUnless|"
    r"test -[fder]\b|\[ -[fder] |os\.path\.exists|pathlib\.Path\([^)]*\)\.exists"
)


LINE_COMMENT = re.compile(r"(^|\s)(//|#)\s.*$", re.MULTILINE)


def strip_comments(text: str) -> str:
    """Blank out line comments, keeping line COUNT so windows still line up.

    A comment that cites a file is documentation, not a dependency:
    datastore-relocate.test.ts explains an ordering rule by pointing at
    "private/renet/pkg/datastore/adopt.go:22-28" and never opens it. Treating a
    citation as a read punishes the habit of citing sources, which this repo
    wants more of, not less.
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
        # A GUARDED read is not a dependency. crypto.test.ts wraps its
        # cross-language fixtures in describe.skipIf(!existsSync(...)) precisely
        # so the suite still runs without the account submodule, and flagging
        # that would punish the correct pattern. The datastore-prune test throws
        # on purpose instead, and says so in its own comment, which is what makes
        # it a real dependency rather than an optional one.
        if GUARDED.search(window):
            continue
        if ACCESS.search(window):
            return hit
    return None


def job_takes_submodules(job: dict) -> bool:
    # A job may init its submodules with an explicit `git submodule update`
    # instead of actions/checkout's flag, and housekeeping.yml does exactly that.
    # Recognising only the actions/checkout form would report a job that is
    # perfectly correct, and a gate that cries wolf gets ignored the one time it
    # is right.
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
    # The lookbehind rejects a WORD character only. It must NOT reject a
    # preceding slash: the defect this gate exists for names its file as
    # '../../../../../private/renet/pkg/prune/datastore.go', and excluding a
    # leading slash made the rule blind to every relative reference -- which is
    # most of them. The gate ran green against a replay of the real bug until
    # this was found, so the replay, not the green, is what proved it.
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
            # A workflow this gate cannot parse is a build failure elsewhere; do
            # not let it pass as "no violations found".
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
                    # The controls scan a planted file outside the repo, so this
                    # must not assume the path is relative to it.
                    try:
                        where = str(wf.relative_to(REPO))
                    except ValueError:
                        where = str(wf)
                    findings.append((where, job_name, f"{label} reads {hit.group(0)}"))
                    break
    return findings, jobs_scanned


def run_controls(subs: list[str], scripts: dict[str, str]) -> list[str]:
    """Prove the rule can FIRE and that it is not always firing.

    Both directions, because always-on and always-off are different bugs and a
    control that only checks one of them certifies half a gate.
    """
    failures: list[str] = []
    if not subs:
        return [".gitmodules named no submodules, so the rule matches nothing and passes forever"]

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
        print("      - uses: ./.github/actions/app-token")
        print("        id: app-token")
        print("        with:")
        print("          client-id: ${{ vars.APP_ID }}")
        print("          private-key: ${{ secrets.APP_PRIVATE_KEY }}")
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
