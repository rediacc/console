r"""Audit-logging coverage for machine-level CLI operations.

Ported from `.ci/scripts/quality/check-audit-coverage.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live and for the phase-5
decision that retires the twin.

THE TWIN'S OWN HEADER, carried over because the list of invariants IS the gate:

  Check that all machine-level CLI operations have audit logging coverage.

  Verifies three invariants:
    1. localExecutorService.execute() contains auditService.recordOperation()
       (covers all SSH-based operations automatically)
    2. Edge-case files (SFTP sync, direct SSH term) contain
       auditService.recordOperation()
    3. No new direct SSH/SFTP execution paths exist without audit coverage

  This prevents adding new machine-level operations without audit logging.

  Exit codes:
    0 - All operations have audit logging coverage
    1 - One or more gaps detected

There are FIVE phases and only three invariants, which is not a contradiction:
phases 4 and 5 were added later and phase 4 is a WARNING that never sets ERRORS.
The header was not updated. Left as it stands, and reported.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

PHASE 4'S FILE ORDER IS NONDETERMINISTIC IN THE TWIN, AND SORTED HERE. The twin
builds that list with a bare `grep -rl ... "$CLI_SRC/commands/"` and never pipes
it through `sort`, unlike phases 5's two `sort -u`s. The `grep` on this host is
ugrep 7.8.4, which walks the tree with a thread pool, and six consecutive runs
over the same six-file fixture printed six DIFFERENT orders:

    commands/bravo.ts commands/alpha.ts commands/mike.ts commands/zeta.ts ...
    commands/alpha.ts commands/zeta.ts commands/mike.ts commands/bravo.ts ...
    commands/bravo.ts commands/sub/yankee.ts commands/alpha.ts ...

So there is no order to transliterate: two runs of the twin on ONE tree already
disagree with each other. This port sorts, which is the only reproducible choice
and is what phase 5 already does for its own two lists. `scripts/lib/shadow-gate.ts`
compares findings as a MULTISET and fingerprints a SORTED list, so the two sides
are ruled equivalent either way; the sorting is for the human reading a diff.
Reported as a defect in the twin rather than treated as an ordering preference.

THE `/commands/` FILTER IN PHASE 4 IS DEAD CODE. `grep -rl` is rooted at
`$CLI_SRC/commands/`, so every path it can possibly return already contains
`/commands/`, and the `if [[ "$rel" != *"/commands/"* ]]; then continue; fi`
guarding "Skip non-command files (services, utils)" can never fire. Carried,
because removing it would be a change to the twin under a port, and reported.

PHASE 5'S EXCLUSION OF THE AUDIT SERVICE DOES NOT WORK, and this is the one that
matters. The comment says the scan runs "excluding tests and the audit service
itself, where mappings are *defined*", and the pipeline is:

    grep -rhE "functionName: '[a-z_]+'" .../commands/ .../services/ \
        --include='*.ts' --exclude-dir=__tests__ 2>/dev/null |
      grep -v 'audit.ts' | ...

`-h` SUPPRESSES THE FILENAME PREFIX, so by the time `grep -v 'audit.ts'` runs
there are no filenames left in the stream: it filters LINES whose own text
contains `audit.ts`, which a `functionName: 'x'` line never does. Every
`functionName` literal inside `services/core/audit.ts` is therefore scanned,
including any the service defines as examples. Preserved exactly, because
"fixing" it would drop findings the twin reports, and reported.

`grep -v 'audit.ts'` IS A BRE, so the `.` matches any character and a line
mentioning `auditXts` would also be dropped. Reproduced with the same
permissiveness rather than with a literal match, since a port that was stricter
here could keep a line the twin discards.

PHASE 3 REPORTS A COUNT IT DID NOT CHECK. When an edge-case file is missing from
disk the twin logs a warning and `continue`s, then prints "All 2 edge-case files
have audit calls" using `${#EDGE_CASE_FILES[@]}` -- the length of the LIST, not
the number actually verified. One missing file and one good one still reads as
"All 2". Carried byte for byte, and reported.

THE ABSENT-INPUT PATHS ARE ASYMMETRIC, and that asymmetry is the twin's. Phases
1, 2 and 5 treat a missing file as an ERROR, which is right. Phases 4 and 5's
source scans treat a missing DIRECTORY as an empty result and pass: point this
gate at a tree with no `packages/cli/src/commands` at all and it reports no
unaudited paths and no missing event types. That is a vacuity hole in the twin,
preserved because closing it would change the verdict, and reported.

`grep -q 'auditService\.recordOperation'` IS A BRE WITH AN ESCAPED DOT, so it is
a plain substring test and is written as one here. `'cli\.[a-z._]+[a-z_]'` is an
ERE and is written as a regex. The two are not the same kind of pattern and are
not treated as if they were.
"""

import os
import pathlib
import re
import shutil
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The audit call every machine-level path must carry. A plain substring, because the twin's pattern `auditService\.recordOperation` is a BRE whose only metacharacter is an escaped dot.
AUDIT_CALL = "auditService.recordOperation"

# Files that execute machine operations OUTSIDE localExecutorService (SFTP sync and direct SSH terminal) and therefore need explicit audit calls.
EDGE_CASE_FILES = (
    "packages/cli/src/commands/repo-sync.ts",
    "packages/cli/src/commands/term.ts",
)

# Known files that legitimately import SFTPClient for machine operations. If a new file imports SFTPClient, it may need audit logging.
KNOWN_SFTP_COMMAND_FILES = (
    "packages/cli/src/commands/repo-sync.ts",
    "packages/cli/src/commands/storage.ts",
)

# The three needles phase 4 looks for, as the BRE alternation `A\|B\|C` spells them: three literals, no metacharacters.
SFTP_NEEDLES = ("SFTPClient", "sftpUploadDirectory", "sftpDownloadDirectory")

# Phase 5's two EREs, and the substring `grep -v` that is meant to drop the audit service and does not. See the port notes.
EVENT_TYPE_RE = re.compile(r"'cli\.[a-z._]+[a-z_]'")
FUNCTION_NAME_LINE_RE = re.compile(r"functionName: '[a-z_]+'")
FUNCTION_NAME_RE = re.compile(r"functionName: '([a-z_]+)'")
AUDIT_TS_LINE_RE = re.compile(r"audit.ts")  # BRE `.`: any character, not a dot

# The prefix rules `functionNameToEventType` in event-schema.ts applies, in the twin's `case` order. ORDER IS SIGNIFICANT because a shell `case` takes the FIRST arm that matches, so this is a tuple and not a dict.
PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("repository_", "cli.repo."),
    ("backup_", "cli.backup."),
    ("datastore_", "cli.datastore."),
    ("machine_", "cli.machine."),
    ("container_", "cli.container."),
)

# The three exact-match rules, after the prefixes and before the fallback.
EXACT_RULES = {
    "sync_upload": "cli.sync.upload",
    "sync_download": "cli.sync.download",
    "term_connect": "cli.term.session",
}


def function_name_to_event_type(fn: str) -> str:
    """`case "$fn" in ... esac` -- the twin's mapping, arm for arm.

    Keep this in sync with `functionNameToEventType` in event-schema.ts, which is
    what the twin's own comment asks of the next reader. It is duplicated logic
    in BOTH implementations and the duplication is the point: the gate exists to
    notice when the two drift.
    """
    for prefix, replacement in PREFIX_RULES:
        if fn.startswith(prefix):
            return replacement + fn[len(prefix) :]
    if fn in EXACT_RULES:
        return EXACT_RULES[fn]
    return "cli." + fn


def _read(path: pathlib.Path) -> str:
    """A file's text, or "" when it cannot be read.

    grep sends its complaint to the stderr the twin redirects to /dev/null and
    lists nothing, so an unreadable file contributes nothing rather than raising
    in the middle of a failure report.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _walk_files(
    root: pathlib.Path, suffix: str | None = None, exclude_dirs: tuple[str, ...] = ()
) -> list[pathlib.Path]:
    """`grep -r` over `root`, as a SORTED path list.

    Sorted, unlike the twin's phase 4; see the port notes for the six runs that
    produced six orders. `exclude_dirs` is `--exclude-dir`, which prunes by
    directory NAME at any depth, matching grep rather than matching a path
    prefix. `paths.walk_tree` applies it, and adds this package's standing prune
    of `.git`, `node_modules` and `.claude/worktrees` on top -- the last of which
    is a peer's sibling checkout of this same repository, invisible to git and
    not to a raw `os.walk`.
    """
    out: list[pathlib.Path] = []
    if not root.is_dir():
        return out
    for dirpath, _dirnames, filenames in paths.walk_tree(root, exclude_dirs=exclude_dirs):
        for name in filenames:
            if suffix is not None and not name.endswith(suffix):
                continue
            out.append(pathlib.Path(dirpath) / name)
    return sorted(out, key=lambda p: str(p).encode("utf-8", "surrogateescape"))


def sftp_importers(cli_src: pathlib.Path, repo_root: pathlib.Path) -> list[str]:
    """Phase 4: command files importing SFTPClient that are not on the known list.

    Returns repo-relative paths. The `/commands/` filter the twin applies is dead
    code (the grep is rooted there) and is not reproduced as a live branch; see
    the port notes.
    """
    out: list[str] = []
    for path in _walk_files(cli_src / "commands"):
        text = _read(path)
        if not any(needle in text for needle in SFTP_NEEDLES):
            continue
        rel = _relative(path, repo_root)
        if rel in KNOWN_SFTP_COMMAND_FILES:
            continue
        out.append(rel)
    return out


def _relative(path: pathlib.Path, repo_root: pathlib.Path) -> str:
    """`${file#"$REPO_ROOT"/}` -- a PREFIX STRIP, not a path computation.

    A file that is not under the root keeps its whole name, which is what the
    parameter expansion does and is the harmless case.
    """
    return str(path).removeprefix(str(repo_root).rstrip("/") + "/")


def union_types(schema_text: str) -> list[str]:
    """Phase 5's declared event types: `grep -oE ... | sort -u`, then unquoted.

    The four `${var//x/}` substitutions the twin applies afterwards (strip `'`,
    `"`, `,`, then every space) are folded into one pass, because on the output
    of THIS regex they can only ever remove the two surrounding quotes: the
    pattern admits no comma, no double quote and no space. Stated rather than
    left as an unexplained simplification.
    """
    found = {m.group(0) for m in EVENT_TYPE_RE.finditer(schema_text)}
    cleaned = {t.replace("'", "").replace('"', "").replace(",", "").replace(" ", "") for t in found}
    return sorted(t for t in cleaned if t)


def emitted_function_names(cli_src: pathlib.Path) -> list[str]:
    """Phase 5's emitted names: the `grep -rhE | grep -v | grep -oE | sed | sort -u`.

    THE `grep -v 'audit.ts'` STAGE FILTERS NOTHING, because `-h` has already
    stripped the filenames. It is reproduced faithfully, filtering LINES whose
    own text matches, so the audit service's own literals are counted exactly as
    the twin counts them. See the port notes.
    """
    names: set[str] = set()
    for root in (cli_src / "commands", cli_src / "services"):
        for path in _walk_files(root, suffix=".ts", exclude_dirs=("__tests__",)):
            for line in _read(path).split("\n"):
                if not FUNCTION_NAME_LINE_RE.search(line):
                    continue
                # `grep -v 'audit.ts'` on the LINE, not on the filename.
                if AUDIT_TS_LINE_RE.search(line):
                    continue
                for m in FUNCTION_NAME_RE.finditer(line):
                    names.add(m.group(1))
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 one or more gaps.

    Long and branchy on purpose: the twin is five sequential phases sharing one
    ERRORS counter, and splitting it into five functions that each return a
    partial verdict would make the ORDER of the output an accident of the
    caller. The order is part of what the differential compares.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    repo_root = paths.repo_root()
    cli_src = repo_root / "packages" / "cli" / "src"
    local_executor = cli_src / "services" / "executor" / "local-executor.ts"
    audit_service = cli_src / "services" / "core" / "audit.ts"

    errors = 0

    # -- Phase 1: Verify audit service exists ------------------------------
    log.step("Checking audit service exists...")

    if not audit_service.is_file():
        log.error("Audit service not found: %s" % audit_service)
        errors += 1
    else:
        log.info("Audit service exists")

    # -- Phase 2: Verify localExecutorService hook -------------------------
    log.step("Checking localExecutorService.execute() audit hook...")

    if not local_executor.is_file():
        log.error("Local executor not found: %s" % local_executor)
        errors += 1
    elif AUDIT_CALL not in _read(local_executor):
        log.error("localExecutorService.execute() does not contain auditService.recordOperation()")
        log.error("All SSH-based operations must be audit-logged via the executor hook.")
        log.error("File: %s" % local_executor)
        errors += 1
    else:
        log.info("localExecutorService.execute() has audit hook")

    # -- Phase 3: Verify edge-case files -----------------------------------
    log.step("Checking edge-case files for audit calls...")

    missing_edge: list[str] = []
    for rel in EDGE_CASE_FILES:
        full_path = repo_root / rel
        if not full_path.is_file():
            log.warn("Edge-case file not found (may have been moved): %s" % rel)
            continue
        if AUDIT_CALL not in _read(full_path):
            missing_edge.append(rel)

    if missing_edge:
        log.error("Edge-case files missing auditService.recordOperation():")
        for rel in missing_edge:
            log.error("  - %s" % rel)
        log.error("")
        log.error("These files execute machine operations via SFTP/SSH (not localExecutorService)")
        log.error("and require explicit audit calls.")
        errors += 1
    else:
        # THE COUNT IS THE LIST'S LENGTH, NOT THE NUMBER VERIFIED. A file missing
        # from disk is warned about above and then counted here. See the port
        # notes; this is carried, not repaired.
        log.info("All %d edge-case files have audit calls" % len(EDGE_CASE_FILES))

    # -- Phase 4: Detect unaudited execution paths -------------------------
    log.step("Scanning for unaudited execution paths...")

    importers = sftp_importers(cli_src, repo_root)
    if importers:
        log.warn("New command files with SFTP imports detected (may need audit logging):")
        for rel in importers:
            log.warn("  - %s" % rel)
        log.warn(
            "If these files perform machine-level operations, add auditService.recordOperation()"
        )
        log.warn("and add them to the EDGE_CASE_FILES list in this script.")
        # This is a warning, not an error: new SFTP usage might be internal/utility.

    # -- Phase 5: Event-type union completeness ----------------------------
    log.step("Checking event-type union covers every functionName emitted...")

    event_schema = repo_root / "packages" / "shared" / "src" / "audit" / "event-schema.ts"
    if not event_schema.is_file():
        log.error("Shared audit event schema missing: %s" % event_schema)
        errors += 1
    else:
        # Extract literal event-type strings from the schema file. The schema declares them as 'cli.X.Y' inside ALL_EVENT_TYPES via the per-group
        # const arrays -- grep is sufficient because the file is purely
        # declarative.
        types = union_types(_read(event_schema))

        if not types:
            log.error("Could not parse any event types from %s" % event_schema)
            log.error("Expected literal strings like 'cli.repo.up'. Has the schema format changed?")
            errors += 1

        # A ZERO-TYPE UNION DOES NOT STOP PHASE 5. The twin counts the parse failure and then runs the coverage loop anyway, against an empty union, so every emitted functionName is additionally reported as missing. That is loud rather than wrong, and it is preserved.
        known = set(types)
        missing_types: list[str] = []
        for fn in emitted_function_names(cli_src):
            event_type = function_name_to_event_type(fn)
            if event_type not in known:
                missing_types.append("%s -> %s" % (fn, event_type))

        if missing_types:
            log.error("These functionName values map to event types not in the schema union:")
            for entry in missing_types:
                log.error("  - %s" % entry)
            log.error("")
            log.error("Add the missing literals to ALL_EVENT_TYPES in %s," % event_schema)
            log.error("or remove the recordOperation() call if the event is not auditable.")
            errors += 1
        else:
            log.info("Event-type union covers all %d declared types" % len(types))

    # -- Results -----------------------------------------------------------
    if errors > 0:
        log.error("")
        log.error("Audit coverage check failed with %d error(s)" % errors)
        log.error("")
        log.error("To fix:")
        log.error(
            "  1. Ensure auditService.recordOperation() is called in local-executor.ts execute()"
        )
        log.error("  2. Ensure edge-case files (sync, term) have explicit audit calls")
        log.error("  3. See packages/cli/src/services/core/audit.ts for the audit service API")
        return 1

    log.info("Audit logging coverage check passed")
    return 0


def _seed_clean(root: pathlib.Path) -> None:
    """A tree that satisfies every phase. The base every plant below mutates.

    Asserted CLEAN first in `selftest`: without that, each plant would "fire"
    against a fixture that was already failing and the suite would be green
    while testing nothing.
    """
    cli = root / "packages" / "cli" / "src"
    (cli / "services" / "core").mkdir(parents=True, exist_ok=True)
    (cli / "services" / "executor").mkdir(parents=True, exist_ok=True)
    (cli / "commands").mkdir(parents=True, exist_ok=True)
    (cli / "services" / "core" / "audit.ts").write_text(
        "export const auditService = {};\n", encoding="utf-8"
    )
    (cli / "services" / "executor" / "local-executor.ts").write_text(
        "await auditService.recordOperation({ functionName: 'repository_up' });\n",
        encoding="utf-8",
    )
    for rel in EDGE_CASE_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "auditService.recordOperation({ functionName: 'sync_upload' });\n", encoding="utf-8"
        )
    schema = root / "packages" / "shared" / "src" / "audit"
    schema.mkdir(parents=True, exist_ok=True)
    (schema / "event-schema.ts").write_text(
        "export const ALL_EVENT_TYPES = ['cli.repo.up', 'cli.sync.upload'] as const;\n",
        encoding="utf-8",
    )


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will
    happily flag a correct tree, and the mirrors below are the half that proves
    it does not.
    """
    ctl = Controls("audit-coverage", floor=22, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "tree"

        def run() -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        def fresh() -> pathlib.Path:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True)
            _seed_clean(root)
            return root

        fresh()
        ctl.check("CONTROL: a fully covered tree passes", run(), 0)

        # PLANT 1: phase 1. The audit service itself is gone.
        r = fresh()
        (r / "packages/cli/src/services/core/audit.ts").unlink()
        ctl.check("PLANT: a missing audit service is caught", run(), 1)

        # PLANT 2: phase 2, both arms -- the file is gone, and the hook is gone.
        r = fresh()
        (r / "packages/cli/src/services/executor/local-executor.ts").unlink()
        ctl.check("PLANT: a missing local executor is caught", run(), 1)
        r = fresh()
        (r / "packages/cli/src/services/executor/local-executor.ts").write_text(
            "await ssh.run(cmd);\n", encoding="utf-8"
        )
        ctl.check("PLANT: an executor with no audit hook is caught", run(), 1)

        # PLANT 3: phase 3. An edge-case file that exists but does not audit.
        for rel in EDGE_CASE_FILES:
            r = fresh()
            (r / rel).write_text("export function x() {}\n", encoding="utf-8")
            ctl.check("PLANT: %s without an audit call is caught" % rel, run(), 1)

        # ITS MIRROR, AND THE DEFECT IT EXPOSES. A MISSING edge-case file is only a warning, so the gate still passes -- and still says "All 2". The control names the behaviour so a later reader cannot mistake it for an accident.
        r = fresh()
        (r / EDGE_CASE_FILES[1]).unlink()
        ctl.check("PRESERVED DEFECT: a MISSING edge-case file only warns", run(), 0)

        # PLANT 4: phase 5. The schema file is gone.
        r = fresh()
        (r / "packages/shared/src/audit/event-schema.ts").unlink()
        ctl.check("PLANT: a missing event schema is caught", run(), 1)

        # PLANT 5: phase 5. The schema parses to nothing.
        r = fresh()
        (r / "packages/shared/src/audit/event-schema.ts").write_text(
            "export const ALL_EVENT_TYPES = [] as const;\n", encoding="utf-8"
        )
        ctl.check("PLANT: an unparseable event schema is caught", run(), 1)

        # PLANT 6: phase 5. A functionName whose event type is not in the union.
        r = fresh()
        (r / "packages/cli/src/commands/new.ts").write_text(
            "auditService.recordOperation({ functionName: 'machine_reboot' });\n",
            encoding="utf-8",
        )
        ctl.check("PLANT: an uncovered functionName is caught", run(), 1)

        # ITS MIRROR: the same name WITH its literal in the union passes.
        r = fresh()
        (r / "packages/cli/src/commands/new.ts").write_text(
            "auditService.recordOperation({ functionName: 'machine_reboot' });\n",
            encoding="utf-8",
        )
        (r / "packages/shared/src/audit/event-schema.ts").write_text(
            "export const ALL = ['cli.repo.up', 'cli.sync.upload', 'cli.machine.reboot'];\n",
            encoding="utf-8",
        )
        ctl.check("MIRROR: the same name with its literal declared passes", run(), 0)

        # MIRROR: a __tests__ directory is excluded, so a fixture's functionName is not a finding. This is the direction that would silently invert if someone dropped --exclude-dir.
        r = fresh()
        (r / "packages/cli/src/commands/__tests__").mkdir(parents=True)
        (r / "packages/cli/src/commands/__tests__/x.test.ts").write_text(
            "functionName: 'machine_reboot'\n", encoding="utf-8"
        )
        ctl.check("MIRROR: __tests__ is excluded from the functionName scan", run(), 0)

        # MIRROR: a non-.ts file carrying the literal is not scanned.
        r = fresh()
        (r / "packages/cli/src/commands/x.md").write_text(
            "functionName: 'machine_reboot'\n", encoding="utf-8"
        )
        ctl.check("MIRROR: a non-.ts file is not in the functionName corpus", run(), 0)

        # PLANT 7: phase 4's warning. It must APPEAR and must NOT change the exit code, which is the whole distinction between phase 4 and the others.
        r = fresh()
        (r / "packages/cli/src/commands/blob.ts").write_text(
            "import { SFTPClient } from '../remote/sftp';\n", encoding="utf-8"
        )
        ctl.check("PLANT: a new SFTP importer warns but does not fail", run(), 0)
        ctl.check(
            "PLANT: and it is the one reported",
            sftp_importers(r / "packages/cli/src", r),
            ["packages/cli/src/commands/blob.ts"],
        )
        # ITS MIRROR: a KNOWN importer is not reported.
        r = fresh()
        (r / "packages/cli/src/commands/storage.ts").write_text(
            "import { SFTPClient } from '../remote/sftp';\n", encoding="utf-8"
        )
        ctl.check(
            "MIRROR: a known SFTP importer is not reported",
            sftp_importers(r / "packages/cli/src", r),
            [],
        )

        # THE VACUITY HOLE, asserted so it cannot be mistaken for a passing tree.
        # An empty repository satisfies phases 4 and 5 by having nothing to scan;
        # phases 1, 2 and 5's schema check are what stop it being a clean green.
        r = fresh()
        shutil.rmtree(r / "packages" / "cli")
        ctl.check("VACUITY: a tree with no CLI source is REFUSED by phases 1 and 2", run(), 1)

        # -- the pure helpers, driven directly ----------------------------
        ctl.check(
            "map: an unprefixed name falls through to cli.<name>",
            function_name_to_event_type("login"),
            "cli.login",
        )
        ctl.check(
            "map: repository_ becomes cli.repo.",
            function_name_to_event_type("repository_up"),
            "cli.repo.up",
        )
        ctl.check(
            "map: term_connect becomes cli.term.session",
            function_name_to_event_type("term_connect"),
            "cli.term.session",
        )
        ctl.check(
            "map: the prefix arms are tried BEFORE the exact ones",
            function_name_to_event_type("machine_status"),
            "cli.machine.status",
        )
        ctl.check(
            "parse: a one-character tail is NOT matched, because the ERE needs two",
            union_types("['cli.a', 'cli.ab']"),
            ["cli.ab"],
        )
        ctl.check(
            "parse: duplicates collapse, exactly as `sort -u` does",
            union_types("'cli.repo.up' 'cli.repo.up' 'cli.repo.down'"),
            ["cli.repo.down", "cli.repo.up"],
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
