"""policy_paths.py -- the Python twin of `scripts/lib/policy-paths.ts`.

WHY A TWIN AND NOT A CLIENT. `scripts/lib/policy-paths.ts` already answers
"where does a suppression policy file live", and it has a CLI, so a Python
caller could shell out to `tsx` for the answer. Three reasons it must not:

  1. COST. `go_deps.py`, `plan_housekeeping.py` and `profiler_coverage.py` need
     the path at module import. A node startup per gate, to join two strings,
     is the shape that made `test-policy-path.sh` the third-slowest gate in the
     quick lane before it was collapsed to one process.
  2. PURITY. `policy_path()` below does no filesystem access at all (rule 1
     over there, and it is the property `test-policy-path.sh:63-80` proves with
     an `rmdir`). A subprocess is filesystem access by definition, so a client
     could not have the property the twin is required to have.
  3. AVAILABILITY. A Python gate must answer on a tree where `node_modules` has
     not been installed. The TS CLI cannot.

SO THE LISTS ARE WRITTEN TWICE, AND THAT IS A LIABILITY. It is the liability
`check:ci-policy-inventory` exists to hold: it asserts three-way set equality
between this file's POLICY_FILES, the TypeScript file's POLICY_FILES, and the
`.ci/policy/` directory itself, in BOTH directions per pair. Divergence is not
prevented here, it is made loud there. That gate also carries the reason the
inventory is load-bearing rather than tidy: `.language-policy-allowlist` landed
on 2026-09-07 in the directory and in NEITHER list, reached by a hardcoded join
that bypassed both seams, and nothing was red for a day.

THE THREE RULES ARE THE TWIN'S, VERBATIM IN INTENT.

1. PURE JOIN, NO FILESYSTEM. `policy_path()` never calls stat, exists, iterdir
   or resolve. It answers the same string on a tree with no `.ci` directory at
   all, so a caller's failure to find the file is the CALLER's own ENOENT at
   the caller's own path, rather than this module quietly answering somewhere
   else. Proven the same way the bash test proves it for TypeScript, by
   `.ci/rediacc_ci/tests/gates/test_gate_policy_inventory.py`, which asks for a
   path under an EMPTY fixture root and then `rmdir`s that root: rmdir refuses
   a non-empty directory, so a helper that had created or cached anything would
   fail the line.

2. NO REGISTRY FILE. The valid names are the tuple below, in source. A registry
   read at runtime would need its own path, which is the problem this module
   solves, one level up.

3. NO TRANSITION FALLBACK. Exactly ONE location at a time, in POLICY_DIR. A
   helper that tried the new location and fell back to the old one is how a
   move half-lands with every gate still green. An unknown name RAISES, naming
   the valid set, rather than returning a plausible path that resolves to
   nothing -- which every consumer of these files reads as "no entries", which
   is indistinguishable from "nothing is suppressed".

EVERY ENVIRONMENT OVERRIDE STAYS IN FRONT OF THE SEAM. `LANGUAGE_POLICY_ALLOWLIST`,
`RUNNER_ADVICE_ALLOWLIST`, `PLAN_HK_ALLOWLIST` and `PROFILER_COVERAGE_ALLOWLIST`
are read by their gates and short-circuit the call; none of them is read here.
An override consulted INSIDE the seam would be a second live location, which is
rule 3 defeated by the back door, and it would also cost a `os.environ` read on
a function whose whole contract is that it reads nothing.
"""

import os
import pathlib

from rediacc_ci import paths

# The repository root, derived from the package's own location. `paths.CI_DIR`
# is `<root>/.ci`, computed once at import of that module; taking its parent
# here costs no filesystem call, whereas `paths.repo_root()` would `is_dir()` an override on every call and break rule 1.
_STATIC_ROOT = paths.CI_DIR.parent

# The directory, relative to the repository root, that holds the policy files. `.ci/policy` since W4 P2 (commit b80552370). MUST equal POLICY_DIR in
# scripts/lib/policy-paths.ts; check:ci-policy-inventory compares the two.
POLICY_DIR = ".ci/policy"

# Every suppression policy file, by bare name. MUST equal POLICY_FILES in scripts/lib/policy-paths.ts, name for name.
#
# `.ci-trigger` is DELIBERATELY ABSENT and stays at the repository root: no entries, no BLOCKER lines, no parser anywhere in the tree, and its whole semantic is a root gesture a human performs by hand to force a full CI round. `.ci/policy/README.md` section 3 records that decision and its evidence.
POLICY_FILES: tuple[str, ...] = (
    ".actions-upgrade-blocklist",
    ".audit-allowlist",
    ".audit-prod-allowlist",
    ".ci-parity-exempt",
    ".cli-i18n-orphan-allowlist",
    ".dead-bash-allowlist",
    ".deps-upgrade-blocklist",
    ".devcontainer-upgrade-blocklist",
    ".e2e-coverage-allowlist",
    ".embed-assets-upgrade-blocklist",
    ".go-deps-upgrade-blocklist",
    ".language-policy-allowlist",
    ".plan-housekeeping-allowlist",
    ".profiler-coverage-allowlist",
    ".runner-advice-allowlist",
    ".unverified-download-allowlist",
    # D0, 2026-09-09. THE ONLY NON-DOTFILE AND THE ONLY .json IN THIS SET, and both are deliberate. It is a pinned MEASUREMENT of what the hook wiring costs, not a
    # list of exempted entries, so a name-per-line dotfile could not hold it; and it
    # is policy by the README's four-part predicate all the same, because every number in it is a claim about the world that a change to .claude/settings.json can stop being true. It is reached through policy_path() from .ci/rediacc_ci/quality/hook_exec_baseline.py and nowhere else.
    "hook-exec-baseline.json",
    # D2, 2026-09-09. The WORKLIST_* environment registry: 133 names across 60 files at 183 read sites, with no registry and no schema before this. A typo'd name reads as UNSET, which for a flag defaulting to `on` is the FAIL-OPEN direction. Reached through policy_path() from .ci/rediacc_ci/quality/worklist_env_registry.py and nowhere else. JSON for the same reason as the line
    # above: it holds a table, not a list of entries.
    "worklist-env-registry.json",
    ".w7p5a-real-run-blocklist",
    # T-SCHED W7P5-a Section 4, 2026-09-15. `.w7p5a-real-run-blocklist` BLOCKs an
    # entire path's port; this one BLOCKs only a `ledger`-status path's REAL-RUN leg,
    # which the box's acceptance ("dry-run parity plus one real run each") requires separately. The two must not share a file: the existing gate treats any allowlist entry whose path has graduated to "ledger" as STALE, so a path that is genuinely ledgered but real-run-blocked would misreport as a leftover.
    ".w7p5a-real-run-leg-blocklist",
)

_VALID = frozenset(POLICY_FILES)


class UnknownPolicyFileError(ValueError):
    """A name that is not one of POLICY_FILES.

    A distinct type, not a bare ValueError, so a caller's control can assert on
    the refusal without matching a message string -- the same argument
    `rediacc_ci.paths.RootError` makes one module over.
    """


def _refuse(name: str) -> None:
    raise UnknownPolicyFileError(
        'policy_path: "%s" is not a known policy file.\n'
        "  Known names (%d):\n%s\n"
        "  Add the name to POLICY_FILES in .ci/rediacc_ci/policy_paths.py, to"
        " POLICY_FILES in scripts/lib/policy-paths.ts, and to the list in"
        " .ci/policy/README.md, in the same change."
        % (name, len(POLICY_FILES), "\n".join("    %s" % n for n in POLICY_FILES))
    )


def is_policy_file_name(name: str) -> bool:
    """True when `name` is one of the policy files this module will resolve."""
    return name in _VALID


def policy_rel(name: str) -> str:
    """`.ci/policy/<name>` -- the REPO-RELATIVE path, as a string.

    For the callers that hold a relative path and join it themselves later
    (`root / BLOCKLIST_REL` in go_deps, `${VAR:-<rel>}` semantics in
    profiler_coverage) or print it in a message. Returning an absolute path to
    those would change what they write into fixtures and what they show a
    reader, for no gain.

    A pure string join, like everything else here. Raises on an unknown name.
    """
    if name not in _VALID:
        _refuse(name)
    return "%s/%s" % (POLICY_DIR, name)


def policy_path(name: str, root: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """Absolute path of one policy file. A PURE JOIN: no stat, no readdir.

    `root` defaults to the repository this package lives in. Tests pass a
    fixture root, and the join being pure is what lets that fixture be
    completely empty -- see this module's docstring, rule 1.

    Raises UnknownPolicyFileError on an unknown name, naming the valid set.
    """
    if name not in _VALID:
        _refuse(name)
    base = _STATIC_ROOT if root is None else pathlib.Path(root)
    # POLICY_DIR is split rather than joined as one segment so that a future value of "" degrades to the repository root instead of introducing an empty path component. Written as a comprehension, not an `if`, so there is no branch that today's literal makes dead.
    return base.joinpath(*[part for part in POLICY_DIR.split("/") if part], name)


__all__ = [
    "POLICY_DIR",
    "POLICY_FILES",
    "UnknownPolicyFileError",
    "is_policy_file_name",
    "policy_path",
    "policy_rel",
]
