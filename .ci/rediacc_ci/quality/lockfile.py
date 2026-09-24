"""Validate EVERY package-lock.json in the tree, and that CI installs with the npm that wrote them.

Ported from `.ci/scripts/quality/check-lockfile.sh`, which W7 P5 batch C1 retired once `.ci/shadow/w7p2-lockfile.observations.jsonl` asserted equivalence over five distinct trees.

WHY THE TWIN WAS REWRITTEN, carried over from its header because the archaeology is the half of a gate that cannot be recovered from the code:

  It used to run lockfile-lint on `package-lock.json` -- the ROOT one, and only
  that one. Two consequences, both bad:

    1. The repo has NINE lockfiles (root, private/account{,/web,/e2e},
       workers/{account,mta-sts,www}, private/growth/*). All FOUR npm-11 pruning
       incidents happened in private/account* -- a file this gate had never
       opened. It was green through every one of them.
    2. The other eight were not supply-chain-validated AT ALL. A non-https or
       tampered resolved URL in any of them sailed straight through.

  And what it validated (--validate-https, --allowed-hosts,
  --validate-package-names, --validate-integrity) says NOTHING about whether npm
  can install the result. The name promised "lockfile"; the check delivered "the
  root lockfile has no malicious URLs".

WHAT THIS GATE PROVES, AND WHAT IT DOES NOT. Three properties per lockfile, and one about CI:

  A. SUPPLY CHAIN (lockfile-lint). Unchanged, applied to all of them.

  B. RESOLVABLE (`npm ci --dry-run`) under the ONE pinned npm, `NPM_VERSION` in `.devcontainer/toolchain.env`. This check IS that command, so it cannot be fooled by the shape of a diff.

  C. CANONICAL FORM. A scratch mirror of the lockfile, its `package.json`, its `.npmrc` and every workspace or `file:` manifest it names is rewritten with `npm install --package-lock-only --ignore-scripts` under the same pin, and any byte difference is a refusal. The committed file is never written. This is what ends the npm-10-vs-npm-11 oscillation for good: a lockfile written by any other npm (npm 10's 27 `"dev": true` lines under `node_modules/tsx/**`, or npm 10's nested `@esbuild/*` platform entries that npm 11 prunes) is refused with the one command that fixes it, instead of being accepted by one probe and argued with by the next.

  D. CI RUNS THAT npm. Node 22 bundles npm 10, so every `actions/setup-node` step installs with npm 10 unless something replaces it. The only permitted setup-node site is `.github/actions/setup-node-npm/action.yml`, which installs and verifies the pin; `NPM_VERSION` must be an exact 11.x; every Dockerfile stage (submodules included) that installs a project tree must first install `npm@${NPM_VERSION}`, every `ARG NPM_VERSION=` must equal the pin, and the devcontainer, where lockfiles get written, must install it too.

  WHY ONE npm, since 2026-09-24 (issue #587, operator: "full compatibility with npm 11 everywhere"). Until then this gate resolved every lockfile under npm 11 (the writer) AND npm 10 (CI's bundled installer), because the two disagreed about nested platform entries. Property D removes the disagreement at its source, so the npm 10 probe had nothing left to answer, and property C replaces it with the question that actually matters: did the pinned npm write this file.

  HONEST LIMIT: `--dry-run` does NOT run the reify peer check. A lockfile can
  pass this gate and still fail a REAL cold-cache `npm ci` with ERESOLVE --
  exactly what happened in round 9 of the 0707 campaign
  (wrangler/workers-types peer). So this gate proves "the pinned npm can
  RESOLVE this lockfile and would write it byte for byte", NOT "it can install
  it". A gate whose name overstates its coverage is the disease being cured
  here; the cure must not reintroduce it. For a real install check, run
  `npm ci --ignore-scripts` in a clean copy.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS PORT SHELLS OUT TO THE SAME TWO COMMANDS AND DOES NOT REIMPLEMENT EITHER.
That is the point of property B: the check IS `npm ci --dry-run`, so anything this module did instead of running it would be the heuristic the twin's header spends eleven lines rejecting. `npx` is invoked with the identical argv in the identical working directory.

THE DIFFERENTIAL FOR THIS PAIR IS RECORDED AGAINST A FIXTURE `npx`, AND THAT IS STATED OUT LOUD RATHER THAN LEFT TO BE DISCOVERED. Running the real thing costs a network round trip per probe, downloads two npm majors, and puts an installer next to eleven committed lockfiles whose byte form this repository has an entire CLAUDE.md section about (the 27-line `"dev": true` flip). So
the recorded trees put a deterministic stand-in for `npx` on PATH, INSIDE the fixture, and drive every branch through it: lint pass, lint fail, npm 11 fail, npm 10 fail, skip, and the no-lockfile refusal. What the ledger therefore proves is that both implementations DISCOVER the same lockfiles, INVOKE the same commands, and REACT identically to their exit codes. What it does not
prove is anything about npm itself, which is not this gate's subject either.

SINCE 2026-09-24 THE LEDGER DESCRIBES A RETIRED SHAPE. It was recorded while this gate still resolved under npm 10 as well; the npm-11-only gate adds the canonical-form rewrite and the CI-npm property, which the selftest and `.ci/rediacc_ci/tests/test_quality_lockfile.py` cover and the ledger does not.

THE DISCOVERY IS `find`, NOT `git ls-files`, and that is deliberate in the twin: "Discovered, never hardcoded: a hardcoded list is how this gate went stale in the first place, and a lockfile added tomorrow must be covered without anyone remembering to add it." The consequence is that an UNTRACKED lockfile is in scope, unlike most gates here. Preserved. The `-not -path
'*/node_modules/*'` exclusion is reproduced as "no path component is node_modules", which is the same set for every path `find` can produce. `.venv` is pruned too, since 2026-09-24: `private/generative/.venv` vendors gradio's own `package-lock.json` beside a `package.json`, and the gate was linting a Python wheel's build artifact as if this repository had written it.

`while read`, NOT `mapfile`, in the twin, and the reason is worth carrying even though Python has no such problem: mapfile/readarray are bash-4 builtins and are BANNED by `.ci/scripts/security/check-commands.sh`, which tracks what is actually available in the minimal CI images (and on macOS / Git Bash). The twin "was written to catch npm-10-vs-11 ENVIRONMENT DRIFT and was itself
defeated by environment drift -- it passed locally on bash 5 and failed in CI."

A SILENT SKIP IS THE FAILURE MODE THIS GATE ALREADY SURVIVED ONCE. The quality-security job checks out WITHOUT submodules, so `private/account*` and `private/growth*` legitimately do not exist there, and a lockfile with no `package.json` beside it is skipped -- LOUDLY, as a warning, listed again in a second warning at the end. The twin's own comment names the precedent: "a silent
skip is how test-embed-credits.sh went green while checking nothing (round 3, 0707 campaign)." Both warnings are carried, and `scripts/lib/shadow-gate.ts` classifies a `⚠` line as a FINDING, so a port that quietly downgraded either one to chatter would show up as a mismatch rather than as tidier output.

A HARNESS DEFECT FOUND WHILE RECORDING THIS PAIR, 2026-09-06, and it belongs here rather than in a report nobody re-reads. The advice line the twin prints when the CANONICAL writer fails begins "The canonical writer cannot read this lockfile", and `scripts/lib/shadow-gate.ts`'s REFUSAL vocabulary carries the term `CANNOT READ` matched case-INSENSITIVELY. So an ordinary sentence of
English advice is read as a gate refusing to report a verdict, the comparison is SUSPENDED, and the row lands as ERROR_REFUSAL even though both sides produced byte-identical output. The measured row: tree ce6f9586c98b8c00d6c23e8df690a5bb805c85d9, exit 1 on both sides, finding count 4 on both sides, fingerprint a2f5ffa94ca75e9a on BOTH sides, onlyOld and onlyNew both empty. Nothing
disagreed.

That matters more than it sounds, because `assertEquivalent` disqualifies a tree id UNCONDITIONALLY once any row against it is non-EQUIVALENT, and the id is the content of both implementations -- so a FALSE refusal can never be cleared by re-running, only by changing code that had nothing wrong with it. The row was archived verbatim and removed from the ledger rather than left to
poison the pair forever, and the recorded trees now exercise the CI-installer failure branch instead. The canonical-writer branch is still covered, by `--selftest` ("PLANT: the canonical writer failing to resolve reds") and by the pytest twin. Reported to the root driver; not fixed here, because `scripts/lib/shadow-gate.ts` is not this port's file.

ONE LOCKFILE, ONE FIRST FAILURE. The three per-lockfile properties run in order (supply chain, resolvable, canonical form) and the first failure ends that lockfile's checks: a lockfile npm cannot resolve has no meaningful rewrite to compare, and reporting both would bury the fix under a diff of the damage.

STREAMS. `common.sh`'s four loggers all write to stderr and gate colour on `[[ -t 2 ]]`, which is the one pre-existing variant that tests the stream it writes to -- so `rediacc_ci.log` matches it exactly and no stream moves in this port. The bare `echo` advice lines around a resolve failure are STDOUT in the twin and stay stdout here; they are data a reader copies, not messages.

ONE KNOWN DIVERGENCE, inherited from the logger and stated so nobody "fixes" it: `common.sh` logs with `echo -e`, which interprets backslash escapes IN THE MESSAGE. A lockfile path containing `\t` would be printed differently by the two implementations. No such path exists, and `rediacc_ci.log` formats the message as data on purpose; see its docstring.
"""

import contextlib
import difflib
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant
from rediacc_ci.core import toolchain

# The npm major every lockfile is written in and every lane installs with (issue #587). CLAUDE.md's npm section is the prose half of this constant; the exact version is `NPM_VERSION` in `.devcontainer/toolchain.env`, and this only bounds it.
NPM_MAJOR = "11"

# The file name discovered everywhere. Named once so the discovery and the messages cannot drift apart.
LOCK_NAME = "package-lock.json"

# The directory `find` is told to skip. A vendored tree's own lockfiles are not this repository's to validate.
EXCLUDED_DIR = "node_modules"

# Pruned on top of `paths.PRUNED_DIR_NAMES`. A Python virtualenv vendors other projects' JavaScript (gradio ships a `package-lock.json` beside a `package.json`), and none of it is this repository's to lint or rewrite.
EXTRA_PRUNED = (".venv",)

# The only file that may use `actions/setup-node`, repo-relative.
COMPOSITE = ".github/actions/setup-node-npm/action.yml"

# Where a setup-node step could hide. Workflows and every local composite action.
WORKFLOW_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/*/action.yml",
    ".github/actions/*/action.yaml",
)

# The devcontainer image is where lockfiles get written, so it must run the pin even though it installs no project tree.
DEVCONTAINER_DOCKERFILE = ".devcontainer/Dockerfile"

# The supply-chain probe's argv after `npx`. Carried as a tuple so the order -- which is what a reader diffs against the twin -- cannot be reshuffled by an accidental edit.
LINT_ARGS = (
    "--no-install",
    "lockfile-lint",
    "--type",
    "npm",
    "--validate-https",
    "--allowed-hosts",
    "npm",
    "--validate-package-names",
    "--validate-integrity",
)

EXACT_VERSION_RE = re.compile(r"^(\d+)\.\d+\.\d+$")
SETUP_NODE_RE = re.compile(r"^\s*(-\s+)?uses:\s*['\"]?actions/setup-node@")
FROM_RE = re.compile(r"^\s*FROM\b", re.IGNORECASE)
ARG_PIN_RE = re.compile(r"^\s*ARG\s+NPM_VERSION=(\S+)")
SOURCES_PINS_RE = re.compile(r"(^|\s)(\.|source)\s+\S*toolchain\.env\b")
# `npm install -g npm@<spec>` in any quoting. The spec is what property D judges.
NPM_SELF_INSTALL_RE = re.compile(r"\bnpm\s+(?:install|i)\s+(?:-g|--global)\s+['\"]?npm@([^\s'\"]+)")
# `npm ci`, or an `npm install` with no package list and no -g: an install of the project tree itself.
NPM_INSTALL_RE = re.compile(r"\bnpm\s+(ci|install|i)\b([^&;|\n]*)")
PIN_SPECS = ("${NPM_VERSION}", "$NPM_VERSION")


def discover(root: pathlib.Path) -> list[str]:
    """`find . -name package-lock.json -not -path '*/node_modules/*' | sed | sort`, with `.venv` pruned too.

    Repo-relative paths, sorted. `sorted()` on `str` is code-point order, which is the C collation the twin's `sort` runs under in CI and in the differential harness.

    ZERO IS NOT A VERDICT HERE, and the caller enforces that: a tree with no lockfile at all is a refusal, because this gate would otherwise report success having opened nothing.
    """
    out: list[str] = []
    # `paths.walk_tree` prunes `node_modules` in place, which is what `-not -path '*/node_modules/*'` amounts to for every path `find` can produce, and is also why a lockfile sitting directly beside a node_modules is still found. It prunes `.claude/worktrees` too: a peer session's sibling checkout of this repository carries its own `package-lock.json` files, and this gate was
    # linting them as if they were ours.
    #
    # THE PRUNE IS NO LONGER SPELLED BY `EXCLUDED_DIR`. That constant now only builds the selftest fixture below, so editing it will NOT change what this walk skips; `paths.PRUNED_DIR_NAMES` and `EXTRA_PRUNED` are where that lives.
    for dirpath, _dirnames, filenames in paths.walk_tree(root, exclude_dirs=EXTRA_PRUNED):
        if LOCK_NAME in filenames:
            out.append(str(pathlib.Path(dirpath).relative_to(root) / LOCK_NAME))
    # `find`'s output starts `./`, which the twin's sed strips; a path directly at the root therefore has no directory prefix at all.
    return sorted(path.removeprefix("./") for path in out)


def discover_dockerfiles(root: pathlib.Path) -> list[str]:
    """Every file named `Dockerfile*`, repo-relative and sorted, submodules included when they are checked out.

    A walk rather than `git ls-files` for the same reason as `discover`: an untracked Dockerfile added today is in scope without anyone remembering to track it first.
    """
    out: list[str] = []
    for dirpath, _dirnames, filenames in paths.walk_tree(root, exclude_dirs=EXTRA_PRUNED):
        out.extend(
            str(pathlib.Path(dirpath).relative_to(root) / name)
            for name in filenames
            if name.startswith("Dockerfile")
        )
    return sorted(path.removeprefix("./") for path in out)


def npm_pin(root: pathlib.Path) -> str:
    """`NPM_VERSION` from the root's pins file. Raises `toolchain.PinError` when it is missing or empty."""
    return toolchain.pin_for("npm", toolchain.load_pins(toolchain.pins_file(root)))


def lint_argv(lock: str) -> list[str]:
    """The exact `npx --no-install lockfile-lint ...` argv for one lockfile."""
    return ["npx", "--no-install", "lockfile-lint", "--path", lock, *LINT_ARGS[2:]]


def resolve_argv(npm_spec: str) -> list[str]:
    """The exact `npx -y <npm@version> ci --dry-run --ignore-scripts` argv."""
    return ["npx", "-y", npm_spec, "ci", "--dry-run", "--ignore-scripts"]


def rewrite_argv(npm_spec: str) -> list[str]:
    """The exact `npx -y <npm@version> install --package-lock-only --ignore-scripts` argv: the command that writes the canonical form, and the one printed as the fix."""
    return ["npx", "-y", npm_spec, "install", "--package-lock-only", "--ignore-scripts"]


def run_lint(root: pathlib.Path, lock: str) -> int:
    """Run lockfile-lint, letting its own output through to both streams.

    NOT CAPTURED. The twin does not redirect it, so lockfile-lint's report is what an operator reads when this fails, and swallowing it would leave a finding with no evidence under it. `flush` first, because this process's buffered stdout would otherwise land AFTER the child's.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(lint_argv(lock), cwd=str(root), check=False).returncode


def run_resolve(directory: pathlib.Path, npm_spec: str) -> int:
    """`npm ci --dry-run` in `directory`, output DISCARDED. Returns the exit code.

    Discarded to match the twin's `>/dev/null 2>&1`: the first probe is a yes/no question and npm's success chatter is long. The failure path re-runs it with output kept; see `resolve_failure_detail`.
    """
    return subprocess.run(
        resolve_argv(npm_spec),
        cwd=str(directory),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def resolve_failure_detail(directory: pathlib.Path, npm_spec: str, limit: int = 25) -> list[str]:
    """The first `limit` lines of the failing command, each indented four spaces.

    `2>&1 | head -25 | sed 's/^/ /'` in the twin. Merging the streams is correct HERE and only here: this is a transcript being shown to a human, not a comparison, and the twin's own `|| true` says the re-run's exit code is not part of the verdict.
    """
    proc = subprocess.run(
        resolve_argv(npm_spec),
        cwd=str(directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    text = proc.stdout or ""
    lines = text.split("\n")
    # A trailing newline produces a final empty element that `head` never emits as a line; dropping it keeps the two transcripts identical.
    if lines and lines[-1] == "":
        lines.pop()
    return ["    " + line for line in lines[:limit]]


def _workspace_patterns(manifest: dict) -> list[str]:
    """`workspaces` as a list of globs, from either of the two shapes npm accepts."""
    spaces = manifest.get("workspaces") or []
    if isinstance(spaces, dict):
        spaces = spaces.get("packages") or []
    return [str(s) for s in spaces if isinstance(s, str)]


def mirror_inputs(root: pathlib.Path, lock: str) -> list[str]:
    """Every repo-relative file `npm install --package-lock-only` reads for this lockfile.

    The lockfile, its `package.json` and `.npmrc`, and the `package.json` of every workspace the manifest's `workspaces` globs match and of every non-`node_modules` path the lockfile itself names (workspaces again, plus `file:` targets such as private/account's `../../packages/shared`). Missing files are left out: npm then reports what it could not find, and that is the finding. Raises ValueError for a path that escapes the root, because the mirror cannot reproduce it.
    """
    directory = pathlib.PurePosixPath(lock).parent
    wanted = {lock, str(directory / "package.json"), str(directory / ".npmrc")}
    base = root / directory
    try:
        manifest = json.loads((base / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    for pattern in _workspace_patterns(manifest):
        for match in glob.glob(str(base / pattern)):
            wanted.add(os.path.relpath(os.path.join(match, "package.json"), root))
    try:
        packages = json.loads((root / lock).read_text(encoding="utf-8")).get("packages") or {}
    except (OSError, ValueError):
        packages = {}
    for key in packages:
        if not key or EXCLUDED_DIR in pathlib.PurePosixPath(key).parts:
            continue
        wanted.add(os.path.normpath(os.path.join(str(directory), key, "package.json")))
    out: list[str] = []
    for rel in sorted(os.path.normpath(w) for w in wanted):
        if rel.startswith(".."):
            raise ValueError("%s names %s, which is outside the repository" % (lock, rel))
        if (root / rel).is_file():
            out.append(rel)
    return out


def run_rewrite(directory: pathlib.Path, npm_spec: str) -> subprocess.CompletedProcess:
    """`npm install --package-lock-only` in `directory`, output captured. Only ever called on a scratch mirror."""
    return subprocess.run(
        rewrite_argv(npm_spec),
        cwd=str(directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def canonical_form_findings(
    root: pathlib.Path, lock: str, npm_spec: str, limit: int = 20
) -> list[str]:
    """Rewrite a mirror of `lock` with the pinned npm; [] when the bytes come back unchanged.

    A MIRROR, NEVER THE COMMITTED FILE. Rewriting in place and restoring would race any other session editing the same lockfile in this shared tree, and a crash between the two would leave the rewrite behind. The mirror is a temporary directory removed on every path out.
    """
    try:
        inputs = mirror_inputs(root, lock)
    except ValueError as exc:
        return [str(exc)]
    original = (root / lock).read_bytes()
    with tempfile.TemporaryDirectory(prefix="lockfile-canon-") as tmp:
        scratch = pathlib.Path(tmp)
        for rel in inputs:
            target = scratch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, target)
        proc = run_rewrite((scratch / lock).parent, npm_spec)
        if proc.returncode != 0:
            lines = (proc.stdout or "").rstrip("\n").split("\n")
            return ["%s could not rewrite it (exit %d):" % (npm_spec, proc.returncode)] + [
                "    " + line for line in lines[:limit]
            ]
        rewritten = (scratch / lock).read_bytes()
    if rewritten == original:
        return []
    diff = list(
        difflib.unified_diff(
            original.decode("utf-8", "replace").split("\n"),
            rewritten.decode("utf-8", "replace").split("\n"),
            "committed",
            "%s rewrite" % npm_spec,
            n=0,
            lineterm="",
        )
    )
    changed = sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))
    return ["%s would rewrite %d line(s); the first of them:" % (npm_spec, changed)] + [
        "    " + line for line in diff[: limit + 2]
    ]


def _code_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """(1-based number, text) for every line that is not a comment."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [
        (n, line)
        for n, line in enumerate(text.split("\n"), start=1)
        if not line.lstrip().startswith("#")
    ]


def _is_project_install(verb: str, args: str) -> bool:
    """True for `npm ci` and for an `npm install` with no package list and no -g."""
    if verb == "ci":
        return True
    tokens = [t for t in args.split() if t not in ("\\", "&&")]
    if any(t in ("-g", "--global") for t in tokens):
        return False
    return not any(not t.startswith("-") for t in tokens)


def dockerfile_findings(rel: str, lines: list[tuple[int, str]], pin: str) -> list[str]:
    """Property D for one Dockerfile. Pure, so the selftest drives it on literal text."""
    out: list[str] = []
    has_arg = any(ARG_PIN_RE.match(line) for _n, line in lines)
    sources_pins = any(SOURCES_PINS_RE.search(line) for _n, line in lines)
    pinned_in_stage = False
    installs_pin = False
    for number, line in lines:
        where = "%s:%d" % (rel, number)
        if FROM_RE.match(line):
            pinned_in_stage = False
            continue
        arg = ARG_PIN_RE.match(line)
        if arg and arg.group(1) != pin:
            out.append("%s: ARG NPM_VERSION=%s, but the pin is %s" % (where, arg.group(1), pin))
        self_install = NPM_SELF_INSTALL_RE.search(line)
        if self_install:
            spec = self_install.group(1)
            if spec not in PIN_SPECS:
                out.append(
                    '%s: installs npm@%s; install "npm@${NPM_VERSION}" instead' % (where, spec)
                )
            elif not (has_arg or sources_pins):
                out.append(
                    "%s: uses ${NPM_VERSION} with no `ARG NPM_VERSION=%s` and no toolchain.env"
                    % (where, pin)
                )
            else:
                pinned_in_stage = True
                installs_pin = True
        if not pinned_in_stage:
            out.extend(
                '%s: `npm %s` runs the base image\'s bundled npm; install "npm@${NPM_VERSION}" earlier in this stage'
                % (where, match.group(1))
                for match in NPM_INSTALL_RE.finditer(line)
                if _is_project_install(match.group(1), match.group(2))
            )
    if rel == DEVCONTAINER_DOCKERFILE and not installs_pin:
        out.append(
            '%s: the devcontainer writes lockfiles, so it must install "npm@${NPM_VERSION}"' % rel
        )
    return out


def composite_findings(root: pathlib.Path) -> list[str]:
    """The composite must exist, call setup-node, and install and verify the pin."""
    path = root / COMPOSITE
    if not path.is_file():
        return ["%s is missing, so no workflow can get npm %s" % (COMPOSITE, NPM_MAJOR)]
    code = "\n".join(line for _n, line in _code_lines(path))
    out: list[str] = []
    for needle, why in (
        ("actions/setup-node@", "no longer runs actions/setup-node"),
        ("toolchain_pin_for npm", "no longer reads the pin through toolchain.sh"),
        ("npm install -g", "no longer installs the pinned npm"),
        ("npm --version", "no longer verifies the installed npm"),
    ):
        if needle not in code:
            out.append("%s %s" % (COMPOSITE, why))
    return out


def ci_npm_findings(root: pathlib.Path, pin: str) -> list[str]:
    """Property D over the whole tree: the pin's shape, every setup-node site, the composite, every Dockerfile."""
    out: list[str] = []
    shape = EXACT_VERSION_RE.match(pin)
    if not shape:
        out.append("NPM_VERSION=%s is not an exact X.Y.Z version" % pin)
    elif shape.group(1) != NPM_MAJOR:
        out.append("NPM_VERSION=%s is not npm %s" % (pin, NPM_MAJOR))

    workflow_files = sorted(
        {p for pattern in WORKFLOW_GLOBS for p in glob.glob(str(root / pattern))}
    )
    if not workflow_files:
        out.append(
            "no workflow or composite action found under .github/, so no setup-node site was checked"
        )
    for name in workflow_files:
        rel = os.path.relpath(name, root)
        if rel == COMPOSITE:
            continue
        for number, line in _code_lines(pathlib.Path(name)):
            if SETUP_NODE_RE.match(line):
                out.append(
                    "%s:%d: uses actions/setup-node directly, which installs with Node's bundled npm; use ./%s"
                    % (rel, number, os.path.dirname(COMPOSITE))
                )
    out.extend(composite_findings(root))

    dockerfiles = discover_dockerfiles(root)
    if DEVCONTAINER_DOCKERFILE not in dockerfiles:
        out.append(
            "%s is missing, so the lockfile writer's npm was not checked" % DEVCONTAINER_DOCKERFILE
        )
    for rel in dockerfiles:
        out.extend(dockerfile_findings(rel, _code_lines(root / rel), pin))
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    lockfiles = discover(root)

    # THE VACUITY CASE, AND THE TWIN SAYS IT IN ONE SENTENCE. A repository with no lockfile anywhere has not been validated; it has been missed.
    if not lockfiles:
        log.error("No package-lock.json found anywhere. That cannot be right.")
        return 1

    try:
        pin = npm_pin(root)
    except toolchain.PinError as exc:
        log.error("No npm pin: %s" % exc)
        return 1
    npm_spec = "npm@%s" % pin

    failed: list[str] = []
    skipped: list[str] = []

    log.step("CI installs with %s (setup-node sites, Dockerfiles, devcontainer)..." % npm_spec)
    ci_findings = ci_npm_findings(root, pin)
    for finding in ci_findings:
        log.error(finding)
    if ci_findings:
        failed.append("CI npm (%d finding(s))" % len(ci_findings))

    for lock in lockfiles:
        directory = (root / lock).parent
        rel_dir = str(pathlib.Path(lock).parent)
        fix = "    cd %s && npx -y %s install --package-lock-only --ignore-scripts" % (
            rel_dir,
            npm_spec,
        )

        # SKIP LOUDLY. The quality-security job checks out WITHOUT submodules, so private/account* and private/growth* legitimately do not exist there. A silent skip is how a gate goes green while checking nothing.
        if not (directory / "package.json").is_file():
            log.warn("SKIP %s - no package.json beside it (submodule not checked out?)" % lock)
            skipped.append(lock)
            continue

        log.step("[%s] supply chain (lockfile-lint)..." % lock)
        if run_lint(root, lock) != 0:
            log.error("[%s] FAILED supply-chain validation" % lock)
            failed.append("%s (supply chain)" % lock)
            continue

        log.step("[%s] resolvable by %s..." % (lock, npm_spec))
        if run_resolve(directory, npm_spec) != 0:
            log.error("[%s] %s CANNOT RESOLVE this lockfile." % (lock, npm_spec))
            print()
            print("  Rewrite it with the pinned npm, then commit the result:")
            print()
            print(fix)
            print()
            print("  The failure, in full:")
            for line in resolve_failure_detail(directory, npm_spec):
                print(line)
            failed.append("%s (%s cannot resolve)" % (lock, npm_spec))
            continue

        log.step("[%s] written by %s (canonical form)..." % (lock, npm_spec))
        drift = canonical_form_findings(root, lock, npm_spec)
        if drift:
            log.error("[%s] is not in %s's form: %s" % (lock, npm_spec, drift[0]))
            for line in drift[1:]:
                print(line)
            print()
            print("  Another npm wrote this file. Rewrite it with the pinned one:")
            print()
            print(fix)
            print()
            failed.append("%s (not written by %s)" % (lock, npm_spec))
            continue

        log.info("[%s] OK" % lock)

    if skipped:
        log.warn(
            "Skipped %d lockfile(s) whose package.json is absent: %s"
            % (len(skipped), " ".join(skipped))
        )

    if failed:
        log.error("Lockfile check FAILED for: %s" % " ".join(failed))
        return 1

    # THE SHAPE, NOT JUST THE VERDICT: the count and the pin are named, so a reader notices when the number collapses or the pin quietly moves.
    log.info(
        "All %d lockfile(s): supply-chain clean, resolvable by %s and byte-identical to its "
        "rewrite; CI and every image install %s" % (len(lockfiles), npm_spec, npm_spec)
    )
    # THE LIMIT IS PRINTED ON THE SUCCESS PATH, as a WARNING, on purpose: a gate whose name overstates its coverage is the disease this file was written to cure, so the cure says out loud what it did not check.
    log.warn(
        "Note the limit: --dry-run does NOT run the reify peer check. This proves %s "
        "can RESOLVE these lockfiles, not that it can install them (round-9 ERESOLVE, see "
        "docs/agent-reference/ci-gates.md)." % npm_spec
    )
    return 0


# The fixture's pin and the composite it needs, written by CONSTRUCTION so rewording the real files cannot void a control.
FIXTURE_PIN = "11.20.0"
FIXTURE_COMPOSITE = (
    "runs:\n  using: composite\n  steps:\n"
    "    - uses: actions/setup-node@0000000000000000000000000000000000000000\n"
    "    - shell: bash\n      run: |\n"
    "        . .ci/scripts/lib/toolchain.sh\n"
    '        pin="$(toolchain_pin_for npm)"\n'
    '        npm install -g "npm@${pin}"\n'
    '        [[ "$(npm --version)" == "$pin" ]]\n'
)
FIXTURE_DEVCONTAINER = (
    "FROM base\nCOPY toolchain.env /etc/rediacc/toolchain.env\n"
    'RUN . /etc/rediacc/toolchain.env && npm install -g "npm@${NPM_VERSION}"\n'
)


def scaffold(root: pathlib.Path, pin: str = FIXTURE_PIN) -> None:
    """A minimal tree that satisfies property D: the pins file, the composite, a workflow using it, the devcontainer."""
    files = {
        ".devcontainer/toolchain.env": "NODE_VERSION=22\nNPM_VERSION=%s\n" % pin,
        COMPOSITE: FIXTURE_COMPOSITE,
        ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - uses: ./.github/actions/setup-node-npm\n",
        DEVCONTAINER_DOCKERFILE: FIXTURE_DEVCONTAINER,
    }
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    NO REAL npm RUNS HERE EITHER. `npx` is stubbed on PATH by a tiny script this
    function writes, for the reasons in the port notes; the subject under test is
    the discovery, the skip rule, the probe order, the mirror, property D and the exit code, all of which are this module's own logic. The stub's exit code, and whether it appends to the mirrored lockfile, are the only things npm contributes to the verdict, and those are exactly what is varied.
    """
    ctl = Controls("lockfile", floor=40, verbose=True)
    pin = FIXTURE_PIN

    # -- discovery, driven directly ------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ctl.check("VACUITY: an empty tree discovers nothing", discover(root), [])
        (root / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: the root lockfile has no directory prefix", discover(root), [LOCK_NAME]
        )
        (root / "pkg").mkdir()
        (root / "pkg" / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: a nested lockfile is found and the list is SORTED",
            discover(root),
            [LOCK_NAME, "pkg/%s" % LOCK_NAME],
        )
        nm = root / "pkg" / EXCLUDED_DIR / "dep"
        nm.mkdir(parents=True)
        (nm / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: MIRROR a lockfile under node_modules is excluded",
            discover(root),
            [LOCK_NAME, "pkg/%s" % LOCK_NAME],
        )
        venv = root / "tool" / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: a lockfile vendored under .venv is excluded",
            discover(root),
            [LOCK_NAME, "pkg/%s" % LOCK_NAME],
        )
        # And the exclusion is by COMPONENT, not by substring: a directory whose name merely contains the word is not node_modules.
        near = root / "my_node_modules_backup"
        near.mkdir()
        (near / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: MIRROR a lookalike directory name is NOT excluded",
            "my_node_modules_backup/%s" % LOCK_NAME in discover(root),
            True,
        )

    # -- the mirror's inputs --------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "packages" / "a").mkdir(parents=True)
        (root / "packages" / "a" / "package.json").write_text("{}", encoding="utf-8")
        (root / "shared").mkdir()
        (root / "shared" / "package.json").write_text("{}", encoding="utf-8")
        (root / "app").mkdir()
        (root / "package.json").write_text('{"workspaces": ["packages/*"]}', encoding="utf-8")
        (root / ".npmrc").write_text("ignore-scripts=true\n", encoding="utf-8")
        (root / LOCK_NAME).write_text(
            '{"packages": {"": {}, "node_modules/x": {}}}', encoding="utf-8"
        )
        (root / "app" / "package.json").write_text("{}", encoding="utf-8")
        (root / "app" / LOCK_NAME).write_text(
            '{"packages": {"": {}, "../shared": {}, "node_modules/y": {}}}', encoding="utf-8"
        )
        ctl.check(
            "mirror: the root lockfile brings its manifest, .npmrc and workspace manifests",
            mirror_inputs(root, LOCK_NAME),
            [".npmrc", "package-lock.json", "package.json", "packages/a/package.json"],
        )
        ctl.check(
            "mirror: a file: target outside the lockfile's directory is carried",
            mirror_inputs(root, "app/%s" % LOCK_NAME),
            ["app/package-lock.json", "app/package.json", "shared/package.json"],
        )
        (root / "app" / LOCK_NAME).write_text('{"packages": {"../../x": {}}}', encoding="utf-8")
        ctl.raises(
            "mirror: a path escaping the repository is refused",
            ValueError,
            mirror_inputs,
            root,
            "app/%s" % LOCK_NAME,
        )

    # -- property D on literal Dockerfiles ------------------------------------
    def dock(text: str, rel: str = "Dockerfile") -> list[str]:
        return dockerfile_findings(
            rel,
            [(n, s) for n, s in enumerate(text.split("\n"), 1) if not s.lstrip().startswith("#")],
            pin,
        )

    good = (
        'ARG NPM_VERSION=%s\nFROM node\nARG NPM_VERSION\nRUN npm install -g "npm@${NPM_VERSION}"\nRUN npm ci --ignore-scripts\n'
        % pin
    )
    ctl.check(
        "docker: CONTROL a stage that installs the pin before npm ci is clean", dock(good), []
    )
    ctl.check(
        "docker: PLANT npm ci with the bundled npm reds",
        len(dock("FROM node\nRUN npm ci --ignore-scripts\n")),
        1,
    )
    ctl.check(
        "docker: PLANT the pin installed in an EARLIER stage does not cover a later one",
        len(dock(good + "FROM node AS second\nRUN npm install --omit=dev\n")),
        1,
    )
    ctl.check(
        "docker: PLANT a literal npm version reds",
        len(dock("FROM node\nRUN npm install -g npm@12.0.2 && npm install\n")) >= 1,
        True,
    )
    ctl.check(
        "docker: PLANT an ARG that disagrees with the pin reds",
        len(dock(plant(good, "ARG NPM_VERSION=%s" % pin, "ARG NPM_VERSION=11.0.0"))),
        1,
    )
    ctl.check(
        "docker: MIRROR a global tool install is not a project install",
        dock("FROM node\nRUN npm install -g agent-browser@1.2.3\n"),
        [],
    )
    ctl.check(
        "docker: PLANT the devcontainer without the pin reds",
        len(dock("FROM base\nRUN echo hi\n", DEVCONTAINER_DOCKERFILE)),
        1,
    )

    # -- argv construction ---------------------------------------------------
    ctl.check(
        "argv: the lint probe names the lockfile with --path",
        lint_argv("a/b.json")[:5],
        ["npx", "--no-install", "lockfile-lint", "--path", "a/b.json"],
    )
    ctl.check("argv: and validates integrity", "--validate-integrity" in lint_argv("x"), True)
    ctl.check(
        "argv: the resolve probe is `npx -y <npm@pin> ci --dry-run --ignore-scripts`",
        resolve_argv("npm@%s" % pin),
        ["npx", "-y", "npm@%s" % pin, "ci", "--dry-run", "--ignore-scripts"],
    )
    ctl.check(
        "argv: the rewrite is `npx -y <npm@pin> install --package-lock-only --ignore-scripts`",
        rewrite_argv("npm@%s" % pin),
        ["npx", "-y", "npm@%s" % pin, "install", "--package-lock-only", "--ignore-scripts"],
    )

    # -- the whole gate, with a stubbed npx ----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        binpath = root / "stub-bin"
        binpath.mkdir()
        stub = binpath / "npx"

        def set_stub(
            lint_code: int, resolve_code: int, rewrite_code: int, rewrites: bool = False
        ) -> None:
            """Write an `npx` whose exit code is decided per probe; `rewrites` makes the rewrite change the lockfile."""
            stub.write_text(
                "#!/bin/bash\n"
                'case "$*" in\n'
                "  *lockfile-lint*) echo 'lockfile-lint transcript'; exit %d ;;\n"
                "  *' ci '*) echo 'resolve transcript'; exit %d ;;\n"
                "  *--package-lock-only*) %s echo 'rewrite transcript'; exit %d ;;\n"
                "esac\nexit 0\n"
                % (
                    lint_code,
                    resolve_code,
                    "echo drift >> package-lock.json;" if rewrites else "",
                    rewrite_code,
                ),
                encoding="utf-8",
            )
            stub.chmod(0o755)

        @contextlib.contextmanager
        def stubbed():
            """Point PATH at the stub and REDIACC_CI_ROOT at the fixture.

            EVERY probe in this selftest runs inside this, without exception. A call that escaped it would reach the REAL npx, download npm, and put an installer next to this repository's committed lockfiles -- which is the one thing this port is under orders never to do.
            """
            saved_root = os.environ.get(paths.ROOT_ENV)
            saved_path = os.environ.get("PATH", "")
            os.environ[paths.ROOT_ENV] = str(root)
            os.environ["PATH"] = "%s:%s" % (binpath, saved_path)
            try:
                yield
            finally:
                os.environ["PATH"] = saved_path
                if saved_root is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved_root

        def run() -> int:
            with stubbed():
                return main([])

        # THE VACUITY CASE FIRST: no lockfile anywhere is a refusal, and it must not be reachable by deleting files until the gate goes quiet.
        set_stub(0, 0, 0)
        ctl.check("VACUITY: no lockfile anywhere is refused", run(), 1)

        (root / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check("PLANT: no npm pin at all is refused", run(), 1)
        scaffold(root)

        # Still no package.json beside it: the SKIP path. It exits 0, which is the twin's behaviour, and says so twice in warnings.
        ctl.check("SKIP: a lockfile with no package.json beside it is skipped, loudly", run(), 0)

        (root / "package.json").write_text("{}", encoding="utf-8")
        ctl.check("CONTROL: a clean lockfile passes", run(), 0)

        set_stub(1, 0, 0)
        ctl.check("PLANT: a supply-chain failure reds", run(), 1)

        set_stub(0, 1, 0)
        ctl.check("PLANT: the pinned npm failing to resolve reds", run(), 1)

        set_stub(0, 0, 0, rewrites=True)
        ctl.check("PLANT: a lockfile the pinned npm would rewrite reds", run(), 1)
        ctl.check(
            "CONTROL: and the committed lockfile was not touched by the rewrite",
            (root / LOCK_NAME).read_text(encoding="utf-8"),
            "{}",
        )

        set_stub(0, 0, 3)
        ctl.check("PLANT: a rewrite that fails reds", run(), 1)

        # PROPERTY D through the whole gate: a bare setup-node step in a workflow.
        set_stub(0, 0, 0)
        wf = root / ".github" / "workflows" / "ci.yml"
        clean_wf = wf.read_text(encoding="utf-8")
        wf.write_text(clean_wf + "      - uses: actions/setup-node@abc  # v7\n", encoding="utf-8")
        ctl.check("PLANT: a setup-node step outside the composite reds", run(), 1)
        wf.write_text(clean_wf + "      # - uses: actions/setup-node@abc\n", encoding="utf-8")
        ctl.check("MIRROR: a commented-out setup-node step does not", run(), 0)
        wf.write_text(clean_wf, encoding="utf-8")

        composite = root / COMPOSITE
        composite.write_text(
            plant(FIXTURE_COMPOSITE, '        npm install -g "npm@${pin}"\n', ""), encoding="utf-8"
        )
        ctl.check("PLANT: a composite that stops installing the pin reds", run(), 1)
        composite.write_text(FIXTURE_COMPOSITE, encoding="utf-8")

        scaffold(root, pin="10.9.8")
        ctl.check("PLANT: an npm 10 pin reds", run(), 1)
        scaffold(root, pin="11")
        ctl.check("PLANT: a pin that is not an exact version reds", run(), 1)
        scaffold(root)
        ctl.check("CONTROL: the restored tree is clean again", run(), 0)

        # A SECOND LOCKFILE, whose own package.json is absent, must be SKIPPED while the first is still judged. A skip that suppressed the rest of the run would look identical to a clean tree.
        (root / "sub").mkdir()
        (root / "sub" / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check("MIRROR: one skipped lockfile does not stop the others", run(), 0)
        set_stub(1, 0, 0)
        ctl.check("PLANT: and the judged one still reds beside a skipped one", run(), 1)

        # A NESTED lockfile WITH its package.json is judged, not skipped. Two directions, because "everything is skipped" and "everything is judged" are both single-branch bugs that a one-sided control cannot tell apart.
        (root / "sub" / "package.json").write_text("{}", encoding="utf-8")
        set_stub(0, 0, 0)
        ctl.check("MIRROR: a nested lockfile with a package.json passes", run(), 0)
        set_stub(1, 0, 0)
        ctl.check("PLANT: and the nested one is really judged (lint fails)", run(), 1)

        # THE STUB ITSELF IS CONTROLLED. Without this, every case above could be passing because `npx` was never reached at all, and a gate whose probe never ran is the vacuity this whole exercise exists to refuse.
        set_stub(0, 7, 0)
        with stubbed():
            ctl.check(
                "CONTROL: the stub is what `npx` resolves to, and its exit code reaches the gate",
                run_resolve(root, "npm@%s" % pin),
                7,
            )
            # The transcript helper indents by four and truncates at the limit.
            ctl.check(
                "detail: the transcript is indented four spaces",
                resolve_failure_detail(root, "npm@%s" % pin, limit=1),
                ["    resolve transcript"],
            )
            ctl.check(
                "detail: MIRROR the limit truncates to nothing",
                resolve_failure_detail(root, "npm@%s" % pin, limit=0),
                [],
            )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
