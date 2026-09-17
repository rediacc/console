"""No workflow may ask the GitHub App for the `administration` permission.

Ported from `.ci/scripts/quality/check-no-app-admin-perm.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live until a differential ledger row exists over K distinct trees. Its gate header registers it as step "App admin permission", id `check:ci-app-admin-perm`, lane quality-code.

WHY THIS EXISTS, carried from the twin because the rationale IS the gate:

    Assert that no workflow or composite action ever requests the
    `administration` permission on a `create-github-app-token` call.

    Per https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps
    `Administration: write` is the GitHub App permission that gates env CRUD
    (DELETE /repos/{owner}/{repo}/environments/{name}, deployment-branch-policies,
    deployment_protection_rules). The rediacc-ci-cd App is deliberately not
    granted this permission so a leaked App token cannot delete edge/stable.

    This gate fails loudly if any future workflow author tries to bypass that
    constraint by adding `permission-administration: write` (or read) to a
    create-github-app-token invocation. Adding the input would silently start
    requesting a permission the App may grant in the future, re-opening the
    blast-radius hole this audit closed.

    Usage: check-no-app-admin-perm.sh

    Exits 0 on clean, 1 on hit.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE OUTPUT SHAPE IS `grep -rn`, AND IT IS REPRODUCED RATHER THAN IMPROVED. `<path>:<lineno>:<line>` with the directory argument's trailing slash collapsed, because that is what the twin prints and because `scripts/lib/shadow-gate.ts` recognises exactly that shape as a finding (`PATH_LINE`) with no marker on it. A port that printed `path (line N)` would have every one of its
findings reclassified as chatter and would compare EQUIVALENT to the twin while agreeing about nothing.

ORDER IS NOT PRESERVED, AND DOES NOT NEED TO BE. GNU grep walks with fts in readdir order, so `.github/workflows/sub/y.yml` can precede `.github/workflows/x.yml` (measured 2026-09-06 on GNU grep 3.12). This module walks sorted, which is stable across machines. The shadow comparator compares a MULTISET, so a different order is not a different finding set, and a stable order is worth
more to a human diffing two runs than fidelity to readdir.

THE NEEDLE IS A LITERAL SUBSTRING, exactly as `grep "permission-administration"` is: no regex, no word boundary, case-sensitive. `permission-administration:` and `# permission-administration` both hit, and the comment case is a HIT on purpose -- a commented-out request is one uncomment away from being a real one, and this gate is about what the file says, not about what YAML
currently parses.

BINARY FILES. GNU grep prints `Binary file <path> matches` and suppresses the line for a file containing a NUL byte. Reproduced, because a workflow directory that acquires one should make the two implementations say the same thing rather than one of them dumping a control-character line into a CI log.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. `log_step`, `log_error`, `log_info` and `get_repo_root` are the gate's only dependency on the shared bash library, which is what makes the twin cheap to retire.

THE ONE PLACE THIS IS DELIBERATELY STRONGER, and it is the failure this whole programme is named after. `if grep -rn ... 2>/dev/null; then` cannot distinguish "no workflow requests the permission" from "there are no workflows". Rename `.github/workflows`, move the tree, run the gate from a fixture that copied the gate but not its subject, and grep exits 2 into a suppressed stderr
while the twin prints its green line. This port counts the files it read and REFUSES when that count is zero, so its green always carries evidence that it saw the tree. The count is printed on the success line for the same reason.
"""

import os
import pathlib
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The two directory arguments, in the twin's order, with their trailing slashes. The slash is carried because it is part of the twin's command line; it is stripped again when a finding is printed, which is what GNU grep does.
SCAN_DIRS = (".github/workflows/", ".github/actions/")

# The literal the whole gate is about. One spelling, used as both the needle and the message, because two spellings is how one of them stops being exercised.
NEEDLE = "permission-administration"


def scan(root: pathlib.Path) -> tuple[list[str], int]:
    """Every `grep -rn` hit under the scan dirs, and how many files were read.

    Returns (lines, files_read). The second value is the anti-vacuity evidence: a gate that read no files has proved nothing, and the twin cannot tell the difference. Pure and importable, so a test can assert the exact byte shape of a finding without a subprocess.
    """
    hits: list[str] = []
    files_read = 0
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.is_dir():
            # `2>/dev/null` in the twin: a missing directory is silent. It is not silent in the COUNT, which is what makes the silence detectable.
            continue
        prefix = scan_dir.rstrip("/")
        for dirpath, dirnames, filenames in paths.walk_tree(base):
            # Sorted, and sorted in place so the walk itself is deterministic. `paths.walk_tree` mutates this same list rather than replacing it, so sorting it here still steers the walk exactly as it did under `os.walk`. `follow_symlinks` stays False there, which is `grep -r` (not -R) semantics.
            dirnames.sort()
            for name in sorted(filenames):
                path = pathlib.Path(dirpath) / name
                try:
                    data = path.read_bytes()
                except OSError:
                    # grep reports and skips; the file was not read, so it is not counted either.
                    continue
                files_read += 1
                rel = path.relative_to(base).as_posix()
                shown = "%s/%s" % (prefix, rel)
                if b"\0" in data:
                    if NEEDLE.encode() in data:
                        hits.append("Binary file %s matches" % shown)
                    continue
                text = data.decode("utf-8", "replace")
                for number, line in enumerate(text.split("\n"), start=1):
                    if NEEDLE in line:
                        hits.append("%s:%d:%s" % (shown, number, line))
    return hits, files_read


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns the process exit code; never raises for a verdict."""
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    # The twin `cd`s to the repo root because its grep arguments are relative.
    os.chdir(root)

    log.step("Checking for permission-administration in workflows/actions...")

    hits, files_read = scan(root)

    # ANTI-VACUITY, before any verdict. Zero inputs is a FAILURE, never a pass: a gate that read nothing cannot have found nothing.
    if files_read == 0:
        log.error(
            "app-admin-perm: read 0 file(s) under %s -- this gate scanned nothing, so its "
            "verdict would be meaningless. Either the workflow tree moved or the gate is "
            "pointed at the wrong root." % " and ".join(d.rstrip("/") for d in SCAN_DIRS)
        )
        return 1

    if hits:
        # stdout, because it is grep's own output in the twin and a gate's stdout is DATA. The three log_error lines below land on stderr, as they do there, and the first of them says "above" precisely because of that split.
        for line in hits:
            print(line)
        log.error("Found permission-administration request above.")
        log.error("The rediacc-ci-cd App must not be granted administration:write.")
        log.error('See CLAUDE.md "App permission policy" for rationale.')
        return 1

    log.info("OK: no permission-administration requests found. (%d file(s) read)" % files_read)
    return 0


def _tree(base: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Build a fixture tree from {relative path: content} and return its root."""
    for rel, content in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return base


def selftest() -> int:
    """Plant a defect in BOTH directions and require the gate to notice.

    Built by CONSTRUCTION in a tempdir, never by mutating `.github/`: a control built by in-place substitution has to additionally prove the plant landed, and the cheaper answer is to not build controls that way.
    """
    # floor=14 rather than 0: the floor is the only thing that catches a selftest
    # whose cases stopped executing, and a default of zero is a floor that cannot fail. See rediacc_ci.controls for the five drifted copies that taught it.
    ctl = Controls("app-admin-perm", floor=14, verbose=True)
    saved_cwd = os.getcwd()
    saved_env = dict(os.environ)

    clean_workflow = "name: ci\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
    request = (
        "      - uses: actions/create-github-app-token@v1\n"
        "        with:\n"
        "          permission-administration: write\n"
    )

    def run(files: dict[str, str]) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(pathlib.Path(tmp), files)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved_env)
                os.chdir(saved_cwd)

    both_dirs = {
        ".github/workflows/ci.yml": clean_workflow,
        ".github/actions/app-token/action.yml": "name: app token\n",
    }

    ctl.check("CONTROL: a clean workflow tree passes", run(both_dirs), 0)

    # THE PLANT, in each of the two scanned trees. Both must fire, or half the gate's stated scope is decoration.
    planted_workflow = dict(both_dirs)
    planted_workflow[".github/workflows/ci.yml"] = clean_workflow + request
    ctl.check("PLANT: a request in a workflow is found", run(planted_workflow), 1)

    planted_action = dict(both_dirs)
    planted_action[".github/actions/app-token/action.yml"] = "name: app token\n" + request
    ctl.check("PLANT: a request in a composite action is found", run(planted_action), 1)

    nested = dict(both_dirs)
    nested[".github/workflows/reusable/deep/inner.yml"] = request
    ctl.check("PLANT: a request nested three deep is found", run(nested), 1)

    commented = dict(both_dirs)
    commented[".github/workflows/ci.yml"] = clean_workflow + "#   permission-administration: read\n"
    ctl.check("PLANT: a COMMENTED-OUT request still fires", run(commented), 1)

    # The mirrors. A gate that fires on everything is as useless as one that never fires, and this is the direction a reviewer waves through.
    neighbour = dict(both_dirs)
    neighbour[".github/workflows/ci.yml"] = clean_workflow + "          permission-contents: read\n"
    ctl.check("MIRROR: a DIFFERENT permission input does not fire", run(neighbour), 0)

    outside = dict(both_dirs)
    outside[".github/README.md"] = "we never ask for %s\n" % NEEDLE
    ctl.check("MIRROR: a hit outside the two scanned dirs does not fire", run(outside), 0)

    sibling = dict(both_dirs)
    sibling["docs/agent-reference/ci-gates.md"] = "%s: write\n" % NEEDLE
    ctl.check("MIRROR: a hit elsewhere in the repo does not fire", run(sibling), 0)

    # VACUITY, three ways, and all three are trees the twin reports as CLEAN.
    ctl.check("VACUITY: no .github at all is refused, not passed", run({"README.md": "x\n"}), 1)
    ctl.check(
        "VACUITY: the dirs present but EMPTY is refused",
        _run_empty_dirs(saved_cwd, saved_env),
        1,
    )

    # The finding text itself, asserted rather than assumed. This is the byte shape `shadow-gate.ts` classifies as a finding; get it wrong and every finding silently becomes chatter.
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(
            pathlib.Path(tmp),
            {
                ".github/workflows/ci.yml": clean_workflow + request,
                ".github/actions/a/action.yml": "  %s: read\n" % NEEDLE,
            },
        )
        hits, files_read = scan(root)
        ctl.check(
            "SHAPE: a hit is grep -rn's <path>:<line>:<text>",
            hits[0],
            ".github/workflows/ci.yml:8:          permission-administration: write",
        )
        ctl.check(
            "SHAPE: the action dir keeps its own prefix",
            hits[1],
            ".github/actions/a/action.yml:1:  permission-administration: read",
        )
        ctl.check("SHAPE: both hits, and only those two", len(hits), 2)
        ctl.check("SHAPE: the file count is every file read", files_read, 2)

    return 0 if ctl.report() else 1


def _run_empty_dirs(saved_cwd: str, saved_env: dict[str, str]) -> int:
    """The scan dirs exist and hold nothing. `mkdir` cannot be expressed as a file map, so this case builds the tree itself."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for scan_dir in SCAN_DIRS:
            (root / scan_dir).mkdir(parents=True, exist_ok=True)
        os.environ[paths.ROOT_ENV] = str(root)
        try:
            return main([])
        finally:
            os.environ.clear()
            os.environ.update(saved_env)
            os.chdir(saved_cwd)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
