r"""`rediacc_ci.quality.audit_coverage` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The decisions in this
gate are made by two greps whose semantics differ (`auditService\.recordOperation`
is a BRE with an escaped dot, `'cli\.[a-z._]+[a-z_]'` is an ERE), by a `case`
whose arm ORDER decides the mapping, and by a five-stage pipeline with a stage in
it that does nothing. A table of expected strings would be a table of what the
PORT does, asserted against itself.

The committed ledger `.ci/shadow/w7p2-audit-coverage.observations.jsonl` compares
the WHOLE gate over five distinct trees. It cannot isolate WHICH stage of the
phase-5 pipeline dropped a line, and it cannot show that the `grep -v 'audit.ts'`
stage is inert, because on any tree the twin and the port are inert together.
This file takes those seams one at a time.

THE FRAGMENTS BELOW ARE LIFTED FROM `.ci/scripts/quality/check-audit-coverage.sh`
lines 161-194 with the variables substituted and nothing else changed.
"""

import pathlib

import pytest

from rediacc_ci.quality import audit_coverage as ac
from rediacc_ci.tests import differential as diff

# ---------------------------------------------------------------------------
# Phase 5, stage 1: grep -oE "'cli\.[a-z._]+[a-z_]'" | sort -u
# ---------------------------------------------------------------------------

# Every shape the schema file can present, plus the ones that look like they
# should be event types and are not. The comment on each line is the property it
# is there for.
SCHEMA_CASES = [
    "'cli.repo.up',",  # the ordinary one
    "  'cli.repo.up',\n  'cli.repo.down',",  # two on two lines
    "['cli.repo.up', 'cli.sync.upload']",  # two on ONE line, so -o matters
    "'cli.repo.up' 'cli.repo.up'",  # a duplicate, collapsed by sort -u
    "'cli.a'",  # ONE char after the dot: the ERE needs two, so no match
    "'cli.ab'",  # two chars: matched
    "'cli.'",  # nothing after the dot
    "'cli'",  # no dot at all
    '"cli.repo.up"',  # double quotes: the ERE demands single ones
    "'CLI.repo.up'",  # upper case: the class is [a-z._]
    "'cli.repo.up2'",  # a digit: not in the class, so the match stops short
    "'cli.repo_up'",  # underscore IS in both classes
    "'cli..up'",  # a doubled dot is inside [a-z._]
    "type: 'cli.machine.status', // cli.machine.reboot",  # a comment on the line
    "no event types at all",  # the empty case
]


@pytest.mark.parametrize("text", SCHEMA_CASES)
def test_union_types_matches_grep_pipeline(tmp_path: pathlib.Path, text: str) -> None:
    """The ERE plus `sort -u` plus the four `${var//x/}` strips, end to end."""
    target = tmp_path / "event-schema.ts"
    target.write_text(text + "\n", encoding="utf-8")
    code, out, err = diff.bash_streams(
        """grep -oE "'cli\\.[a-z._]+[a-z_]'" event-schema.ts | sort -u | """
        """while IFS= read -r line; do """
        """t="${line//\\'/}"; t="${t//\\"/}"; t="${t//,/}"; t="${t// /}"; """
        """[[ -n "$t" ]] && echo "$t"; done; true""",
        cwd=str(tmp_path),
    )
    assert code == 0, err
    from_bash = [line for line in out.split("\n") if line != ""]
    assert ac.union_types(text) == sorted(set(from_bash))


# ---------------------------------------------------------------------------
# Phase 5, stage 2: the functionName pipeline, including the inert stage
# ---------------------------------------------------------------------------

FUNCTION_LINE_CASES = [
    "functionName: 'repository_up',",  # the ordinary one
    "  await audit({ functionName: 'sync_upload' });",  # indented, inline
    "functionName: 'a', functionName: 'b'",  # TWO on one line: -o takes both
    "functionName: 'Repo_Up'",  # upper case: the class is [a-z_]
    "functionName: 'repo1'",  # a digit: not in the class
    "functionName:'repo_up'",  # no space after the colon: no match
    "functionName:  'repo_up'",  # two spaces: no match either
    'functionName: "repo_up"',  # double quotes: no match
    "// functionName: 'repo_up' in a comment",  # a comment IS matched: no filter
    "import x from './audit.ts';",  # no functionName at all
    "functionName: 'repo_up' // see audit.ts",  # the INERT stage's only live case
    "functionName: 'repo_up' // see auditXts",  # BRE `.`: also dropped
]


@pytest.mark.parametrize("line", FUNCTION_LINE_CASES)
def test_function_name_pipeline_matches_grep(tmp_path: pathlib.Path, line: str) -> None:
    """`grep -rhE | grep -v 'audit.ts' | grep -oE | sed | sort -u`, stage for stage.

    THE `grep -v` STAGE IS TESTED HERE AND NOWHERE ELSE. On a real tree it never
    fires, which is exactly the defect: it was written to exclude a FILE and it
    filters LINES. The last two cases in the table are the only inputs on which
    it does anything at all, and they are inputs a real source file would have to
    go out of its way to produce.
    """
    src = tmp_path / "src" / "commands"
    src.mkdir(parents=True)
    (src / "x.ts").write_text(line + "\n", encoding="utf-8")
    (tmp_path / "src" / "services").mkdir(parents=True, exist_ok=True)
    code, out, err = diff.bash_streams(
        """grep -rhE "functionName: '[a-z_]+'" src/commands/ src/services/ """
        """--include='*.ts' --exclude-dir=__tests__ 2>/dev/null | """
        """grep -v 'audit.ts' | grep -oE "functionName: '[a-z_]+'" | """
        """sed -E "s/functionName: '([a-z_]+)'/\\1/" | sort -u; true""",
        cwd=str(tmp_path),
    )
    assert code == 0, err
    from_bash = sorted({s for s in out.split("\n") if s != ""})
    assert ac.emitted_function_names(tmp_path / "src") == from_bash


def test_the_audit_service_exclusion_is_inert(tmp_path: pathlib.Path) -> None:
    """Pinned as a DECISION: `audit.ts`'s own literals ARE scanned.

    The twin's comment promises the scan runs "excluding tests and the audit
    service itself". `-h` has already removed the filenames, so the `grep -v`
    that was supposed to do it cannot. Asserted directly, so that a later
    "improvement" has to delete a named control rather than quietly dropping
    findings the twin reports.
    """
    services = tmp_path / "src" / "services" / "core"
    services.mkdir(parents=True)
    (tmp_path / "src" / "commands").mkdir(parents=True)
    (services / "audit.ts").write_text("functionName: 'machine_reboot'\n", encoding="utf-8")
    assert ac.emitted_function_names(tmp_path / "src") == ["machine_reboot"]

    # ITS MIRROR: a __tests__ directory really IS excluded, so the two exclusions
    # are not both broken -- only the one that was written as a text filter.
    tests = tmp_path / "src" / "commands" / "__tests__"
    tests.mkdir(parents=True)
    (tests / "y.test.ts").write_text("functionName: 'datastore_prune'\n", encoding="utf-8")
    assert ac.emitted_function_names(tmp_path / "src") == ["machine_reboot"]


def test_phase_four_does_not_exclude_tests_while_phase_five_does(tmp_path: pathlib.Path) -> None:
    """The two phases disagree about `__tests__`, and the live tree shows it.

    Phase 5 passes `--exclude-dir=__tests__`; phase 4's `grep -rl` does not. So a
    test fixture importing SFTPClient is reported as a "new command file that may
    need audit logging". That is not hypothetical: running the twin on this
    repository today warns about
    `packages/cli/src/commands/__tests__/repo-sync-dispatch.test.ts`.
    """
    cmds = tmp_path / "src" / "commands" / "__tests__"
    cmds.mkdir(parents=True)
    (cmds / "s.test.ts").write_text("import { SFTPClient } from 'x';\n", encoding="utf-8")
    assert ac.sftp_importers(tmp_path / "src", tmp_path) == ["src/commands/__tests__/s.test.ts"]
    assert ac.emitted_function_names(tmp_path / "src") == []


# ---------------------------------------------------------------------------
# The functionName -> event type mapping
# ---------------------------------------------------------------------------

# The twin's `case`, arm for arm, so the ORDER of the arms is under test and not
# just the individual answers.
_CASE = r"""
fn="$1"
case "$fn" in
    repository_*) type="cli.repo.${fn#repository_}" ;;
    backup_*) type="cli.backup.${fn#backup_}" ;;
    datastore_*) type="cli.datastore.${fn#datastore_}" ;;
    machine_*) type="cli.machine.${fn#machine_}" ;;
    container_*) type="cli.container.${fn#container_}" ;;
    sync_upload) type="cli.sync.upload" ;;
    sync_download) type="cli.sync.download" ;;
    term_connect) type="cli.term.session" ;;
    *) type="cli.$fn" ;;
esac
echo "$type"
"""

MAP_CASES = [
    "repository_up",
    "repository_",  # the prefix and nothing else
    "backup_run",
    "datastore_prune",
    "machine_status",
    "container_logs",
    "sync_upload",  # an EXACT arm, reached only because no prefix matched
    "sync_download",
    "term_connect",  # renamed, not just re-prefixed
    "sync_something",  # not an exact arm: falls through to cli.<name>
    "term_other",
    "login",  # the fallback
    "repositor",  # nearly a prefix
    "machine",  # the prefix with no underscore
]


@pytest.mark.parametrize("fn", MAP_CASES)
def test_event_type_mapping_matches_case(tmp_path: pathlib.Path, fn: str) -> None:
    (tmp_path / "m.sh").write_text(_CASE, encoding="utf-8")
    code, out, err = diff.bash_streams(
        'bash m.sh "$FN"', cwd=str(tmp_path), env=diff.env_for(FN=fn)
    )
    assert code == 0, err
    assert ac.function_name_to_event_type(fn) == out.strip()


# ---------------------------------------------------------------------------
# The BRE substring test in phases 2 and 3
# ---------------------------------------------------------------------------

AUDIT_CALL_CASES = [
    "auditService.recordOperation({});",  # the call
    "await auditService.recordOperation(x);",  # awaited
    "  auditService.recordOperation",  # indented, bare
    "// auditService.recordOperation is described here",  # a COMMENT still counts
    "auditServiceXrecordOperation",  # the dot is ESCAPED, so this must NOT match
    "auditService.record",  # a prefix
    "recordOperation",  # the tail on its own
    "nothing at all",
]


@pytest.mark.parametrize("text", AUDIT_CALL_CASES)
def test_audit_call_substring_matches_grep_q(tmp_path: pathlib.Path, text: str) -> None:
    r"""`grep -q 'auditService\.recordOperation'`: a BRE whose dot is escaped.

    The `auditServiceXrecordOperation` row is the one that matters. An unescaped
    dot would match it, and a port that used `re.search("auditService.record...")`
    would silently accept a file that never calls the audit service.
    """
    target = tmp_path / "f.ts"
    target.write_text(text + "\n", encoding="utf-8")
    code, out, err = diff.bash_streams(
        "grep -q 'auditService\\.recordOperation' f.ts; echo $?", cwd=str(tmp_path)
    )
    assert code == 0, err
    assert (ac.AUDIT_CALL in text) == (out.strip() == "0")


# ---------------------------------------------------------------------------
# The gate as a whole
# ---------------------------------------------------------------------------


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that
    fails the pytest suite when a control is deleted, which is the failure mode
    the flag on its own cannot catch (nobody runs it).
    """
    assert ac.selftest() == 0
