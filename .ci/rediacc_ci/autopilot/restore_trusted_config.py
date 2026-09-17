"""Port of `.ci/scripts/autopilot/restore-trusted-config.sh`.

WALL 4 MITIGATION (docs/ci-overhaul/03-v2-autonomy.md:112-138), and the wall is
worth restating because everything below is shaped by it: on `workflow_run` the
action's `restoreConfigFromBase` NEVER fires -- it is gated on
`isEntityContext`, and `workflow_run` is an automation event -- while
`.claude/hooks/**` still EXECUTE. A job that checks out PR head has therefore
handed arbitrary PR-authored hook code a shell. This script closes that:
snapshot the protected set from the TRUSTED ref before any PR-head checkout,
restore it over the checkout afterwards, and quarantine the branch's copies for
inspection AS DATA, never as executable config.

    snapshot   copy every protected entry that exists into `--snapshot`, and
               write `.protected-manifest` naming the ones that were captured.
    restore    move the checkout's protected entries into `--quarantine`, then
               copy the manifest's entries back from the snapshot.
    assert     the CONTROL. Exit 1 with `trusted-config-drift` when any
               protected entry in the checkout differs from the snapshot. Run
               it WITHOUT restore against a tampered checkout and it must go
               red, or the restore step proves nothing.

FAIL CLOSED IS THE DESIGN, twice over, and both refusals are preserved
verbatim: `restore` without a manifest is exit 1 ("no trusted baseline"), and
`assert` without a manifest is exit 1 ("nothing to assert against is itself a
failure"). Either could have been written as "nothing to do, carry on", and
either spelling would have been wall 4 reopened with a green tick on top.

-----------------------------------------------------------------------------
WHAT SHELLS OUT, AND WHY IT IS EXACTLY ONE THING
-----------------------------------------------------------------------------
`diff -r` IS STILL `diff -r`. It is the comparison the whole control rests on,
and its recursive semantics are not a detail anyone should re-derive: it
follows symlinks, it reports a name present on one side only, it reports a
directory facing a regular file, and it exits 2 rather than 1 when it cannot
read something -- which this script correctly treats as drift, since a
protected entry it cannot compare is not an entry it can vouch for.
`filecmp.dircmp` is NOT that function: its default comparison is `os.stat`
shallow (size and mtime), and `cp -a` PRESERVES mtime, so a shallow comparator
would call a tampered file identical whenever the tamper kept the size. That is
the precise shape of a control that cannot fail.

THE COPIES ARE PYTHON, AND HERE IS WHAT THAT COSTS. `shutil` preserves mode,
timestamps and symlinks-as-symlinks, which is everything this script's own
`assert` compares and everything a hook needs in order to execute. It does NOT
preserve ownership, xattrs, ACLs or SELinux context, and it does not keep hard
links shared inside a copied tree, all of which `cp -a` does. None of the four
is reachable from a CI job that runs as one unprivileged user over a git
checkout, and none is compared by `diff -r`, so the divergence is real,
documented, and outside the control's field of view rather than hidden from it.

-----------------------------------------------------------------------------
THE `cp`/`mv` QUIRK THAT SURVIVES A SECOND RUN, REPRODUCED ON PURPOSE
-----------------------------------------------------------------------------
`cp -a SRC DEST` and `mv SRC DEST` do NOT mean "make DEST look like SRC". When
DEST already exists AS A DIRECTORY they mean "put SRC INSIDE DEST". So running
`snapshot` twice into one `--snapshot` directory produces
`<snapshot>/.claude/.claude`, and running `restore` twice produces
`<quarantine>/.claude/.claude`. `copy_a` and `move` below implement the rule
rather than the intuition, because a port that quietly did the intuitive thing
would diverge from the twin on the second invocation.

AND THE SECOND SNAPSHOT IS NOT LITTER, IT IS A DEFECT. Driven on 2026-09-10
against the twin: `snapshot; assert` passes, and `snapshot; assert; snapshot;
assert` FAILS the second assert with

    trusted-config-drift: '.claude' differs from the pre-checkout snapshot
    trusted-config-drift: '.husky' differs from the pre-checkout snapshot

on a checkout nobody touched. The snapshot now holds `.claude/.claude`, which
the checkout does not, so `diff -r` is right and the message is pointing at the
wrong side. Every directory-valued protected entry is affected; the file-valued
ones are simply overwritten and stay correct. Any re-run of the snapshot step
-- a retried job, two jobs sharing one snapshot path, a workflow that snapshots
per matrix leg -- reds the control with a diagnosis that blames the branch. It
is REPRODUCED here rather than repaired: the twin stays live and registered
until cutover, and a port that silently disagreed with it would be a worse
outcome than a defect both implementations share. `test_defect_snapshotting_
twice_poisons_the_baseline` is the pin.

-----------------------------------------------------------------------------
TWO HAZARDS, REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
1. `restore` TRUSTS EVERY LINE OF THE MANIFEST, and the manifest is read as a
   list of paths that are joined to both `--snapshot` and `--checkout`. A line
   that is not one of `PROTECTED` -- `../../x`, say -- would be copied into the
   checkout without ever being quarantined, because the quarantine loop walks
   `PROTECTED` and the restore loop walks the manifest. It is not reachable
   from this script alone (`snapshot` only ever writes members of `PROTECTED`),
   and the snapshot directory is the TRUSTED side of the whole design, so an
   attacker who can write it has already won. Named because the asymmetry
   between the two loops is not obvious from either one.

2. `assert` IS NOT RUN BY `restore`. Restoring and then verifying is two
   invocations, and nothing in this script makes the second one happen. That is
   the caller's contract with itself.

3. A DANGLING SYMLINK AT A PROTECTED PATH IS INVISIBLE TO ALL THREE VERBS, and
   over a DIRECTORY entry it aborts the restore. `[[ -e ]]` follows symlinks,
   so `.claude -> /nonexistent` is not captured by `snapshot`, not moved by
   `restore`'s quarantine loop, and not reported by `assert`'s
   branch-introduced arm. The restore loop then tries to copy the snapshot's
   `.claude` directory onto that link and fails, exit 1, with the checkout
   PARTLY QUARANTINED: the entries already moved are gone and nothing has been
   restored. Fail-closed, since the step fails and the workflow stops, but the
   intermediate state is real. Driven on 2026-09-10; both implementations stop
   at the same entry with byte-identical trees, and only the diagnostic differs
   (coreutils' "cannot overwrite non-directory" against Python's errno), which
   `test_a_dangling_symlink_over_a_protected_directory_aborts_the_restore`
   compares by shape.

K=5 LEDGER: `.ci/shadow/w7p6-restore-trusted-config.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "restore-trusted-config.py"

# The set `restore-config.ts` protects on entity events (03-v2-autonomy.md:115). ORDER IS OUTPUT ORDER for the manifest and for every drift report.
PROTECTED = (
    ".claude",
    ".mcp.json",
    ".claude.json",
    ".gitmodules",
    ".ripgreprc",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".husky",
)

MANIFEST = ".protected-manifest"

USAGE = (
    "usage: restore-trusted-config.sh snapshot|restore|assert --checkout <dir> "
    "--snapshot <dir> [--quarantine <dir>]"
)
UNKNOWN_SUBCOMMAND = "unknown subcommand '%s' (snapshot|restore|assert)"


def manifest_path(snapshot: str) -> str:
    return "%s/%s" % (snapshot, MANIFEST)


def exists(path: str) -> bool:
    """`[[ -e "$path" ]]`: FOLLOWS symlinks, so a dangling link is False.

    That is not a detail: a branch that replaces `.claude` with a symlink to
    nowhere is invisible to `snapshot` and to the branch-introduced arm of
    `assert`, in the twin and therefore here.
    """
    return os.path.exists(path)


def read_manifest(snapshot: str) -> list[str]:
    """The manifest's lines, in file order, blank lines dropped.

    `while IFS= read -r entry; [[ -z "$entry" ]] && continue`, plus the detail
    that bash's `read` DISCARDS a final line with no newline. `: >file` then
    `echo >>` always terminates every line, so the two agree on everything this
    script writes; the difference only shows on a hand-edited manifest.
    """
    with open(manifest_path(snapshot), "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8", "surrogateescape")
    lines = text.split("\n")
    if lines and lines[-1] != "":
        lines.pop()  # `read` returns false on an unterminated final line
    return [line for line in lines if line]


def in_manifest(entry: str, snapshot: str) -> bool:
    """`grep -qxF "$entry" "$SNAPSHOT/$MANIFEST"`: whole line, fixed string.

    Deliberately NOT `read_manifest`, which drops empty lines: `-x` is an exact
    whole-line match on the raw file, and an unterminated final line DOES match
    for grep even though `read` would have dropped it.
    """
    try:
        with open(manifest_path(snapshot), "rb") as handle:
            raw = handle.read()
    except OSError:
        return False
    text = raw.decode("utf-8", "surrogateescape")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return entry in lines


def copy_a(src: str, dest: str) -> None:
    """`cp -a SRC DEST`, including the DEST-is-a-directory rule.

    Raises OSError or shutil.Error, which the caller turns into `set -e`'s exit
    1 the way the twin does.
    """
    if os.path.isdir(dest) and not os.path.islink(dest):
        dest = os.path.join(dest, os.path.basename(src.rstrip("/")))
    if os.path.islink(src):
        # `-a` implies `-d`: the LINK is copied, not what it points at.
        if os.path.lexists(dest):
            os.remove(dest)
        os.symlink(os.readlink(src), dest)
        shutil.copystat(src, dest, follow_symlinks=False)
        return
    if os.path.isdir(src):
        # `dirs_exist_ok`, because `cp -a` MERGES into an existing tree rather than refusing it.
        shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
        return
    shutil.copy2(src, dest, follow_symlinks=False)


def move(src: str, dest: str) -> None:
    """`mv SRC DEST`. `shutil.move` already implements the DEST-is-a-directory
    rule, which is the one behaviour of `mv` that surprises people."""
    shutil.move(src, dest)


def diff_r(left: str, right: str) -> int:
    """`diff -r "$left" "$right" >/dev/null 2>&1`. 0 identical, non-zero drift.

    Both streams are discarded, as the twin discards them: the report a human
    reads is this script's own `trusted-config-drift` line, naming the entry.
    A missing `diff` binary is exit 127 here, which counts as drift -- the safe
    direction, and the same thing the twin's `set -e`-free `if !` would do.
    """
    try:
        return subprocess.run(
            ["diff", "-r", left, right],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
    except OSError:
        return 127


def count_nonempty(path: str) -> str:
    """`$(grep -c . "$path" || true)`: non-empty lines, or "" if unreadable."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return ""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return str(sum(1 for line in lines if line))


def _oserror(prefix: str, exc: OSError) -> int:
    """One coreutils-shaped diagnostic plus `set -e`'s exit 1."""
    print(
        "%s: %s: %s" % (SELF, prefix, os.strerror(exc.errno) if exc.errno else str(exc)),
        file=sys.stderr,
        flush=True,
    )
    return 1


def do_snapshot(checkout: str, snapshot: str) -> int:
    try:
        os.makedirs(snapshot, exist_ok=True)
    except OSError as exc:
        return _oserror("cannot create directory '%s'" % snapshot, exc)
    try:
        with open(manifest_path(snapshot), "wb"):
            pass  # `: >"$SNAPSHOT/$MANIFEST"`
        captured: list[str] = []
        for entry in PROTECTED:
            source = "%s/%s" % (checkout, entry)
            if not exists(source):
                continue
            copy_a(source, "%s/%s" % (snapshot, entry))
            captured.append(entry)
        with open(manifest_path(snapshot), "wb") as handle:
            handle.write(("".join("%s\n" % name for name in captured)).encode("utf-8"))
    except OSError as exc:
        return _oserror("snapshot failed", exc)
    log.info(
        "snapshot: %s protected entries captured to %s"
        % (count_nonempty(manifest_path(snapshot)), snapshot)
    )
    return 0


def do_restore(checkout: str, snapshot: str, quarantine: str) -> int:
    if not quarantine:
        log.error("restore requires --quarantine")
        return 2
    # Fail closed: without a manifest there is no trusted baseline, and restoring nothing while reporting success would be wall 4 reopened.
    if not os.path.isfile(manifest_path(snapshot)):
        log.error(
            "restore-trusted-config: snapshot manifest missing at %s (fail closed: no "
            "trusted baseline, refusing to proceed)" % manifest_path(snapshot)
        )
        return 1
    try:
        os.makedirs(quarantine, exist_ok=True)
    except OSError as exc:
        return _oserror("cannot create directory '%s'" % quarantine, exc)
    try:
        for entry in PROTECTED:
            source = "%s/%s" % (checkout, entry)
            if exists(source):
                move(source, "%s/%s" % (quarantine, entry))
        for entry in read_manifest(snapshot):
            copy_a("%s/%s" % (snapshot, entry), "%s/%s" % (checkout, entry))
    except OSError as exc:
        return _oserror("restore failed", exc)
    log.info(
        "restore: protected set overwritten from snapshot; branch copies quarantined in "
        "%s (inspect as data only)" % quarantine
    )
    return 0


def do_assert(checkout: str, snapshot: str) -> int:
    if not os.path.isfile(manifest_path(snapshot)):
        log.error(
            "trusted-config-drift: snapshot manifest missing at %s (nothing to assert "
            "against is itself a failure)" % manifest_path(snapshot)
        )
        return 1
    drift = False
    for entry in PROTECTED:
        if in_manifest(entry, snapshot):
            if diff_r("%s/%s" % (snapshot, entry), "%s/%s" % (checkout, entry)) != 0:
                log.error(
                    "trusted-config-drift: '%s' differs from the pre-checkout snapshot" % entry
                )
                drift = True
        elif exists("%s/%s" % (checkout, entry)):
            log.error(
                "trusted-config-drift: '%s' exists in the checkout but not in the snapshot "
                "(branch-introduced config)" % entry
            )
            drift = True
    if drift:
        log.error(
            "assert: the checkout's protected set does not match the trusted snapshot; "
            "hooks from this tree must not run"
        )
        return 1
    log.info("assert: protected set matches the trusted snapshot")
    return 0


def main(argv: list[str]) -> int:
    # `cmd="${1:-}"; shift || true`, then the flags.
    cmd = argv[0] if argv else ""
    try:
        args = common.parse_args(argv[1:])
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    checkout = args.get("ARG_CHECKOUT", "")
    snapshot = args.get("ARG_SNAPSHOT", "")
    quarantine = args.get("ARG_QUARANTINE", "")

    # BOTH CHECKS RUN BEFORE THE SUBCOMMAND IS LOOKED AT, which is the twin's order: a bogus verb with no `--checkout` is a USAGE error, not an unknown subcommand, and a bogus verb with a missing checkout directory refuses
    # for the directory first.
    if not (checkout and snapshot):
        log.error(USAGE)
        return 2
    try:
        common.require_dir(checkout)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    if cmd == "snapshot":
        return do_snapshot(checkout, snapshot)
    if cmd == "restore":
        return do_restore(checkout, snapshot, quarantine)
    if cmd == "assert":
        return do_assert(checkout, snapshot)

    log.error(UNKNOWN_SUBCOMMAND % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
