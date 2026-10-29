#!/usr/bin/env python3
"""check:ci-config-server-key-constant -- the layer-3 dev key stays a TEST_MODE-only constant in one file.

WHY. Until agent/plans/PLAN-config-server-key.md, every account Worker sealed the server-recoverable org passphrase (`config_stores.server_recoverable_org_passphrase`) under a key printed in the source, because the code read an environment variable nothing set and fell back to the constant. K1 moved sealing to the per-Worker secret `ACCOUNT_CONFIG_SERVER_KEY` (`csk1.<kid>.` rows, AAD `csk1|<storeId>`), K4 rewrapped every database, and K6 deleted the last opener of the old untagged rows. The constant survives in exactly one place, as the key vitest and the dev gateway resolve under TEST_MODE. This gate keeps it there.

THE RULES.
- R1 confinement: the constant appears in no source file except `private/account/src/services/config-server-key.ts` and files under a `tests`/`test`/`__tests__` directory. Records and prose (`agent/`, `*.md`) are not source and are not scanned: the plan that retired the constant names it.
- R2 declaration: in that file it appears exactly once, as a non-exported `const NAME = '<constant>';`. An export would hand it to modules this gate does not shape-check.
- R3 guard: every other mention of NAME in that file is the line `if (<expr>.TEST_MODE) return NAME;` (the `resolveConfigServerKey` shape), and there is at least one. Any other use, or a guard on another flag, is a path to the constant outside TEST_MODE.

The Cloudflare entry pins TEST_MODE off (`pinDeployedEnv`, private/account/src/entry/cloudflare.ts), which `tests/unit/config-server-key.test.ts` covers; this gate covers the other half, that the constant is reachable through nothing else.

ANTI-VACUITY. The corpus is `git ls-files -co --exclude-standard` of the console and of every checked-out submodule. A scan that finds zero source files, or a tree without `private/account` checked out, is CANNOT RUN (exit 77), never a pass. The selftest plants every rule into a scratch git repository, including the negative controls (a tests directory, a markdown file) that must stay silent, before any verdict on the real tree is issued. The success line prints the corpus size so a collapse is visible.

Not covered, on purpose: the constant assembled from pieces at runtime. This gate itself spells it that way so its own file does not match.

---- gate ----
step: Config server key constant confined
lane: quality-security
needs: submodules
selftest: true
why: the old layer-3 key was a public constant every Worker used; it may live only in
     config-server-key.ts behind TEST_MODE, so no deployed path can fall back to it.
---- end gate ----
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

import _cipath
from rediacc_ci.controls import plant

CONSTANT = "rediacc-config-server-" + "dev-key"
HOME_REL = "private/account/src/services/config-server-key.ts"
HOME_REPO = "private/account"
EXIT_CANNOT_RUN = 77
# Floors for the REAL tree, measured 2026-10-28 at 7130 source files across 5 repos and 236 under private/account/src. A corpus that collapses below either one (a sparse checkout, an ls-files that lost a submodule) is VACUOUS and CANNOT RUN, never a pass. The selftest fixtures are a handful of files, so they scan with a floor of 1.
MIN_SOURCES = 2000
MIN_ACCOUNT_SRC = 80

# Source by suffix. Anything else (images, lockfiles' siblings, prose) is not where a key gets used.
SOURCE_SUFFIXES = (
    ".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx",
    ".py", ".sh", ".bash", ".go", ".rs", ".sql",
    ".json", ".jsonc", ".toml", ".yml", ".yaml", ".astro", ".vue", ".svelte",
)  # fmt: skip
TEST_DIRS = frozenset({"tests", "test", "__tests__"})
# Top-level directories that hold records and plans, not code: the plan that retired the constant names it there.
RECORD_DIRS = frozenset({"agent"})
MAX_BYTES = 4 * 1024 * 1024

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

DECL_RE = re.compile(
    r"^\s*(?P<export>export\s+)?const\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::\s*string\s*)?=\s*(?P<q>['\"])"
    + re.escape(CONSTANT)
    + r"(?P=q)\s*;?\s*$"
)


class CannotRunError(Exception):
    """The corpus could not be read; exit 77, never a verdict."""


def guard_re(name: str) -> re.Pattern[str]:
    return re.compile(
        r"^\s*if\s*\(\s*(?:[A-Za-z_$][\w$]*\.)*TEST_MODE\s*\)\s*return\s+"
        + re.escape(name)
        + r"\s*;\s*$"
    )


def is_source(rel: str) -> bool:
    return rel.endswith(SOURCE_SUFFIXES)


def is_test_path(rel: str) -> bool:
    return any(part in TEST_DIRS for part in rel.split("/")[:-1])


def is_record_path(rel: str) -> bool:
    return rel.split("/", 1)[0] in RECORD_DIRS


def _ls_files(repo: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", repo, "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise CannotRunError("git ls-files failed in %s: %s" % (repo, proc.stderr.strip()))
    return [p for p in proc.stdout.split("\0") if p]


def _submodules(repo: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", repo, "ls-files", "-s", "-z"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise CannotRunError("git ls-files -s failed in %s: %s" % (repo, proc.stderr.strip()))
    out = []
    for entry in proc.stdout.split("\0"):
        meta, _, path = entry.partition("\t")
        if meta.startswith("160000 "):
            out.append(path)
    return out


def corpus(root: str) -> tuple[list[str], list[str]]:
    """(every listed file, repo-relative to `root`; the submodules that are checked out). Raises CannotRunError when the constant's home repo is not checked out."""
    files = list(_ls_files(root))
    checked_out = []
    for sub in _submodules(root):
        if not os.path.exists(os.path.join(root, sub, ".git")):
            continue
        checked_out.append(sub)
        files.extend("%s/%s" % (sub, p) for p in _ls_files(os.path.join(root, sub)))
    if HOME_REPO not in checked_out and not os.path.isdir(os.path.join(root, HOME_REPO, "src")):
        raise CannotRunError(
            "%s is not checked out, so the constant's home cannot be read; run `git submodule update --init %s`"
            % (HOME_REPO, HOME_REPO)
        )
    return files, checked_out


def _read(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def home_findings(text: str) -> tuple[list[str], int]:
    """(R2 and R3 findings for the home file, the number of TEST_MODE-guarded uses)."""
    out: list[str] = []
    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines, 1) if CONSTANT in ln]
    if len(hits) != 1:
        out.append(
            "%s: the constant appears %d time(s); it must appear exactly once, as `const NAME = '<constant>';`"
            % (HOME_REL, len(hits))
        )
        return out, 0
    lineno = hits[0]
    m = DECL_RE.match(lines[lineno - 1])
    if not m:
        out.append(
            "%s:%d: the constant is not a plain `const NAME = '<constant>';` declaration: %s"
            % (HOME_REL, lineno, lines[lineno - 1].strip())
        )
        return out, 0
    if m.group("export"):
        out.append(
            "%s:%d: the constant is exported; keep it module-private so only resolveConfigServerKey can return it"
            % (HOME_REL, lineno)
        )
    name = m.group("name")
    word = re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")
    guard = guard_re(name)
    guarded = 0
    for i, ln in enumerate(lines, 1):
        if i == lineno or not word.search(ln):
            continue
        if guard.match(ln):
            guarded += 1
        else:
            out.append(
                "%s:%d: %s is used outside `if (<env>.TEST_MODE) return %s;`: %s"
                % (HOME_REL, i, name, name, ln.strip())
            )
    if guarded == 0 and not out:
        out.append(
            "%s: %s is declared but never returned under `if (<env>.TEST_MODE) return %s;`; the guard shape this gate checks is gone"
            % (HOME_REL, name, name)
        )
    return out, guarded


def scan(root: str, min_sources: int = 1, min_account_src: int = 1) -> dict:
    """The verdict data for one tree. Raises CannotRunError, including when the corpus is below either floor."""
    files, submodules = corpus(root)
    sources = [
        f
        for f in files
        if is_source(f) and not is_record_path(f) and os.path.isfile(os.path.join(root, f))
    ]
    if len(sources) < min_sources:
        raise CannotRunError(
            "VACUOUS: the scan found %d source file(s) under %s, floor %d; its green would mean nothing"
            % (len(sources), root, min_sources)
        )
    findings: list[str] = []
    exempt: list[str] = []
    home_text = None
    for rel in sources:
        text = _read(os.path.join(root, rel))
        if text is None:
            continue
        if rel == HOME_REL:
            home_text = text
            continue
        if CONSTANT not in text:
            continue
        if is_test_path(rel):
            exempt.append(rel)
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            if CONSTANT in ln:
                findings.append(
                    "%s:%d: the dev config server key appears outside %s: %s"
                    % (rel, i, HOME_REL, ln.strip()[:160])
                )
    guarded = 0
    if home_text is None:
        findings.append(
            "%s is missing: the constant's home moved or was deleted; update this gate's HOME_REL with it"
            % HOME_REL
        )
    else:
        more, guarded = home_findings(home_text)
        findings.extend(more)
    account_src = sum(1 for f in sources if f.startswith(HOME_REPO + "/src/"))
    if account_src < min_account_src:
        raise CannotRunError(
            "VACUOUS: %d source file(s) under %s/src, floor %d; the account code is not in the corpus"
            % (account_src, HOME_REPO, min_account_src)
        )
    return {
        "sources": len(sources),
        "repos": 1 + len(submodules),
        "account_src": account_src,
        "exempt": sorted(exempt),
        "guarded": guarded,
        "findings": findings,
    }


# ---- selftest ------------------------------------------------------------------

HEALTHY_HOME = (
    "const TEST_MODE_DEV_KEY = '%s';\n"
    "export function resolveConfigServerKey(env) {\n"
    "  const configured = env.ACCOUNT_CONFIG_SERVER_KEY;\n"
    "  if (configured) return configured;\n"
    "  if (env.TEST_MODE) return TEST_MODE_DEV_KEY;\n"
    "  throw new Error('missing');\n"
    "}\n"
) % CONSTANT


def _fixture(tmp: str, files: dict[str, str]) -> str:
    root = os.path.join(tmp, "repo%d" % len(os.listdir(tmp)))
    os.makedirs(root)
    for rel, body in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    subprocess.run(["git", "init", "-q", root], check=True, capture_output=True)
    return root


# The fixture paths are assembled from these roots so no whole dead path literal sits in this file for `test_gate_paths_exist` to resolve against the real tree.
ACCOUNT_DIR = "private/account"
CLI_DIR = "packages/cli"


def _base() -> dict[str, str]:
    return {
        HOME_REL: HEALTHY_HOME,
        "private/account/src/services/config.service.ts": "export const x = 1;\n",
        "packages/cli/src/index.ts": "export {};\n",
    }


def controls_fired() -> list[str]:
    """Each plant against a scratch repo; returns the plants that did NOT behave. Any entry means no verdict on the real tree may be issued."""
    missed: list[str] = []

    def run_case(
        label: str, files: dict[str, str], expect: str | None, floors: tuple[int, int] = (1, 1)
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(tmp, files)
            try:
                result = scan(root, *floors)
            except CannotRunError:
                if expect != "cannot-run":
                    missed.append("%s: CANNOT RUN where a verdict was expected" % label)
                return
            if expect == "cannot-run":
                missed.append("%s: produced a verdict where CANNOT RUN was expected" % label)
            elif expect is None and result["findings"]:
                missed.append(
                    "%s: fired on a tree that must pass: %s" % (label, result["findings"])
                )
            elif expect is not None and not any(expect in f for f in result["findings"]):
                missed.append(
                    "%s: did not report %r (got %s)"
                    % (label, expect, result["findings"] or "nothing")
                )

    # CONTROL 0 first: the healthy fixture passes, or every red below is the fixture's doing.
    run_case("CONTROL 0 healthy tree", _base(), None)
    if missed:
        return missed

    files = _base()
    files[ACCOUNT_DIR + "/src/services/legacy.ts"] = "const K = '%s';\n" % CONSTANT
    run_case("R1 constant in another account source file", files, "appears outside")

    files = _base()
    files[CLI_DIR + "/src/key.py"] = 'KEY = "%s"\n' % CONSTANT
    run_case("R1 constant in a console source file", files, CLI_DIR + "/src/key.py:1")

    files = _base()
    files[ACCOUNT_DIR + "/tests/unit/k.test.ts"] = "const K = '%s';\n" % CONSTANT
    run_case("R1 negative: a tests directory is exempt", files, None)

    files = _base()
    files["docs/DESIGN.md"] = "The old key was `%s`.\n" % CONSTANT
    files["agent/plans/PLAN-x.json"] = '{"k": "%s"}\n' % CONSTANT
    run_case("R1 negative: prose and records are not source", files, None)

    files = _base()
    files[HOME_REL] = plant(
        HEALTHY_HOME, "const TEST_MODE_DEV_KEY", "export const TEST_MODE_DEV_KEY"
    )
    run_case("R2 exported constant", files, "is exported")

    files = _base()
    files[HOME_REL] = HEALTHY_HOME + "const SECOND = '%s';\n" % CONSTANT
    run_case("R2 second declaration", files, "appears 2 time(s)")

    files = _base()
    files[HOME_REL] = plant(
        HEALTHY_HOME,
        "const TEST_MODE_DEV_KEY = '%s';" % CONSTANT,
        "const TEST_MODE_DEV_KEY = ['%s'][0];" % CONSTANT,
    )
    run_case("R2 not a plain declaration", files, "not a plain")

    files = _base()
    files[HOME_REL] = plant(
        HEALTHY_HOME, "  throw new Error('missing');\n", "  return TEST_MODE_DEV_KEY;\n"
    )
    run_case("R3 unguarded fallback", files, "used outside")

    files = _base()
    files[HOME_REL] = plant(HEALTHY_HOME, "env.TEST_MODE", "env.LOCAL_DEV")
    run_case("R3 guard on another flag", files, "used outside")

    files = _base()
    files[HOME_REL] = plant(HEALTHY_HOME, "  if (env.TEST_MODE) return TEST_MODE_DEV_KEY;\n", "")
    run_case("R3 guard removed entirely", files, "never returned")

    files = _base()
    del files[HOME_REL]
    run_case("home file deleted", files, "is missing")

    run_case("anti-vacuity: no private/account checkout", {"README.md": "nothing\n"}, "cannot-run")
    run_case(
        "anti-vacuity: zero source files",
        {"README.md": "nothing\n", "private/account/src/.keep": ""},
        "cannot-run",
    )
    run_case(
        "anti-vacuity: no account source in the corpus",
        {"packages/cli/src/index.ts": "export {};\n", "private/account/src/.keep": ""},
        "cannot-run",
    )
    # The floors themselves: the healthy fixture (3 sources, 2 under the account src) is below each floor raised by one, so each must refuse on its own, and at its exact count it must not.
    run_case("anti-vacuity: below the source floor", _base(), "cannot-run", (4, 1))
    run_case("anti-vacuity: below the account source floor", _base(), "cannot-run", (1, 3))
    run_case("anti-vacuity negative: exactly at both floors", _base(), None, (3, 2))
    return missed


def selftest() -> int:
    missed = controls_fired()
    if missed:
        print(
            "%s✗%s config-server-key-constant selftest: controls did not behave:" % (RED, NC),
            file=sys.stderr,
        )
        for m in missed:
            print("  %s" % m, file=sys.stderr)
        return 1
    print(
        "%s✓%s config-server-key-constant selftest: every plant fired and every negative control stayed silent"
        % (GREEN, NC)
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true", help="run the planted controls only")
    parser.add_argument("--root", default=None, help="tree to scan (default: this repository)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    # Controls first on every real run too: a verdict from an instrument that cannot fail is refused.
    missed = controls_fired()
    if missed:
        print("%s✗%s controls did not fire, so no verdict is issued:" % (RED, NC), file=sys.stderr)
        for m in missed:
            print("  %s" % m, file=sys.stderr)
        return 1
    root = args.root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    # The floors describe THIS repository; a --root tree is a caller-built fixture of a handful of files, scanned at floor 1 like the selftest. CI never passes --root, so the real run keeps both floors.
    floors = (MIN_SOURCES, MIN_ACCOUNT_SRC) if args.root is None else (1, 1)
    try:
        result = scan(root, *floors)
    except CannotRunError as exc:
        print("%sCANNOT RUN%s config-server-key-constant: %s" % (YELLOW, NC, exc), file=sys.stderr)
        return EXIT_CANNOT_RUN
    if result["findings"]:
        print(
            "%s✗%s the dev config server key escaped its TEST_MODE-only home:" % (RED, NC),
            file=sys.stderr,
        )
        for f in result["findings"]:
            print("  %s" % f, file=sys.stderr)
        print(
            "\n  Seal and open layer 3 only through resolveConfigServerKey and the csk1 helpers in %s."
            " Delete the copy; there is no fallback key (agent/plans/PLAN-config-server-key.md K6)."
            % HOME_REL,
            file=sys.stderr,
        )
        return 1
    for rel in result["exempt"]:
        print("  exempt (tests directory): %s" % rel)
    print(
        "%s✓%s config server key constant: %d source file(s) across %d repo(s), %d under %s/src"
        " (floors %d and %d); 1 declaration, %d TEST_MODE-guarded return, %d test file(s) exempt"
        % (
            GREEN,
            NC,
            result["sources"],
            result["repos"],
            result["account_src"],
            HOME_REPO,
            floors[0],
            floors[1],
            result["guarded"],
            len(result["exempt"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
