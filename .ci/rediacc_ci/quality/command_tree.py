"""The exported command tree must still match the live CLI.

Ported from `.ci/scripts/quality/check-command-tree.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live until a differential ledger row exists over K distinct trees. Its gate header registers it as step "Command tree", needs node, selftest true.

WHY THIS EXISTS, carried whole from the twin because the list of dependants IS the argument:

    Check that the exported command tree is up-to-date with the CLI.

    packages/cli/scripts/command-tree.json is the shipped snapshot of the live
    Commander tree, and NINE validators trust it as their model of the CLI:

      scripts/lib/positional-cli-detector.ts  (and, through it, the two ESLint rules
                                               no-positional-cli-syntax{,-source} and
                                               packages/www/scripts/validate-docs-cli-usage.js)
      scripts/gen/validate-cli-examples.ts
      scripts/gates/check-cli-docs.ts
      scripts/gates/check-design-tree.ts
      packages/cli/scripts/check-command-planes.ts

    Nothing regenerated it, and nothing checked it. A stale tree does not fail
    loudly: it fails OPEN. Every one of those validators would keep passing while
    describing a CLI that no longer exists -- a removed command stays "valid" in
    the docs, a new one is never checked at all, and the positional detector reds
    on correct syntax (which is exactly what happened when P4 gave leaves
    positional refs). contract.json has had a freshness gate all along; this is
    the same gate for its sibling.

    Usage:
      .ci/scripts/quality/check-command-tree.sh

    Exit codes:
      0 - Command tree is up-to-date
      1 - Stale command tree detected

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE COMPARISON IS OVER BYTES, NOT OVER PARSED JSON, and that is carried across deliberately even though the sibling port `regions_sync` does the opposite. The difference is what the file IS. `regions.json` is maintained by two humans and a reformat is not drift, so that gate compares parsed content. THIS file is written by ONE program, `export-command-tree.ts`, and re-run through
the same program a
minute later; if the bytes differ, the exporter's output differs, and that IS the
finding. Comparing parsed JSON here would hide a serialization change that every downstream reader of the file would see.

THE BUILD IS PART OF THE SUBJECT, not a precondition to be skipped. The twin's comment says why: "The exporter imports the live CLI, which resolves @rediacc/shared and @rediacc/provisioning through their dist builds." A port that skipped `npm run build:packages` to be fast would compare the committed tree against an exporter reading a stale dist, which is the same fail-open the
gate exists to close.

BOTH SUBPROCESSES KEEP THE TWIN'S STREAM SPLIT. `npm run build:packages >/dev/null` discards stdout and lets stderr through (which is why a run of this gate shows npm's `minimum-release-age` warnings and nothing else), and the same
for `npx tsx ... >/dev/null`. Reproduced exactly: stdout to DEVNULL, stderr
inherited. Capturing stderr instead would silence the one channel that says why a build failed.

THE DIFF IS PRODUCED BY `diff`, NOT BY difflib. The twin ends with `diff "$COMMITTED" "$TEMP" | head -40 | sed 's/^/ /'`, and difflib's formats (`unified_diff`, `ndiff`, `context_diff`) all render the same fact differently. The shadow comparator can be taught to read those indented lines as findings (`--finding-re`), and the moment it is, a difflib rendering makes the port disagree
with the twin about every line of a diff they both computed correctly. `head -40` and the four-space `sed` indent are carried as written.

`mktemp -d` AND ITS `trap 'rm -rf "$TEMP_DIR"' EXIT` become `tempfile.TemporaryDirectory()`, which is the same guarantee with the same lifetime and one fewer way to leak a directory when the script exits early.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. `log_step`, `log_error`, `log_info` and `get_repo_root` are the gate's only dependency on the shared bash library, which is what makes the twin cheap to retire.

THREE PLACES THIS IS DELIBERATELY STRONGER, all of them "the gate ran and verified nothing". None can fire on a tree where the exporter works, so none is
reachable from the differential ledger; they are stated here so the divergence is
on the record.

  1. THE EXPORTER PRODUCED NOTHING. `npx tsx ... --output X` that exits 0 having
     written no file leaves the twin diffing the committed tree against nothing.
     Measured 2026-09-06 rather than reasoned about: it prints
     "✗ packages/cli/scripts/command-tree.json is STALE." -- blaming the
     committed file for the exporter's failure -- then prints its Fix block and
     "Diff (committed vs live):", and then DIES. `diff` exits 2 on the missing
     operand, `set -euo pipefail` carries that out of the pipeline, and the gate
     exits 2 with the report cut off mid-sentence and `diff: ...: No such file or
     directory` on stderr. The author is sent to run `export:command-tree`, which
     would "fix" it by committing the empty tree. A zero-byte file takes the same
     path without the crash. This port refuses before any of it, and
     `tests/test_quality_command_tree.py` pins BOTH behaviours so the difference
     stays a decision.
  2. TWO EMPTY FILES COMPARE EQUAL. If the exporter and the committed file are
     both empty the twin is GREEN, over two broken files. There is a floor.
  3. A FAILING BUILD OR EXPORT IS NAMED. Under `set -e` the twin dies with the
     child's exit code and prints nothing of its own, so the failure reads as
     whatever npm last said. The port keeps the exit code and adds one line
     naming which of the two commands failed.

WHAT IT CANNOT SEE: whether the tree is CORRECT, only whether it is CURRENT. A CLI whose Commander definitions are wrong exports a tree that matches itself.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The committed snapshot, relative to the repo root. One spelling; it is both the
# subject and the thing the fix message tells the reader to regenerate.
COMMITTED_REL = "packages/cli/scripts/command-tree.json"

# The two child commands, as the twin spells them. Lists rather than strings because there is no shell here and nothing needs word splitting.
BUILD_CMD = ["npm", "run", "build:packages"]
EXPORT_CMD = ["npx", "tsx", "packages/cli/scripts/export-command-tree.ts", "--output"]

# `head -40` in the twin: enough of a diff to see what moved, short enough that a regenerated tree does not bury the fix instructions under 4000 lines.
DIFF_CAP = 40

# The four-space indent `sed 's/^/ /'` applies to every diff line.
DIFF_INDENT = "    "


def _run(argv: list[str], cwd: pathlib.Path) -> int:
    """Run a child with stdout DISCARDED and stderr INHERITED, as the twin does.

    `>/dev/null` on the twin's command line is stdout only. Stderr is the channel that says why a build failed, and capturing it here would mean the gate ate the only useful output on its worst day.
    """
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode


def diff_lines(committed: pathlib.Path, live: pathlib.Path) -> list[str]:
    """`diff a b | head -40 | sed 's/^/    /'`, byte for byte.

    Shelling out to `diff` rather than reaching for difflib is a decision, not an
    oversight; see the port notes. `diff` exits 1 when the files differ, which is
    the expected case here and is not an error.
    """
    completed = subprocess.run(
        ["diff", str(committed), str(live)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    out = completed.stdout or ""
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return ["%s%s" % (DIFF_INDENT, line) for line in lines[:DIFF_CAP]]


def node_count(path: pathlib.Path) -> int:
    """How many command nodes the tree declares. 0 when it is not a command tree.

    THE ANTI-VACUITY FLOOR'S EVIDENCE, and the reason the success line prints a
    number: two files that are both empty, or both `{}`, compare EQUAL, and a
    gate with no floor reports success over two broken ones.
    """

    def walk(node: object) -> int:
        if not isinstance(node, dict):
            return 0
        total = 1
        for child in node.get("subcommands") or []:
            total += walk(child)
        return total

    try:
        with path.open(encoding="utf-8") as handle:
            return walk(json.load(handle))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns the process exit code; never raises for a verdict."""
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    committed = root / COMMITTED_REL
    os.chdir(root)

    log.step("Building packages the CLI imports...")
    status = _run(BUILD_CMD, root)
    if status != 0:
        log.error(
            "command-tree: `%s` failed with exit %d, so NOTHING was verified. "
            "The exporter reads @rediacc/shared and @rediacc/provisioning through "
            "their dist builds; without them there is no live tree to compare against."
            % (" ".join(BUILD_CMD), status)
        )
        return status

    log.step("Re-exporting the command tree...")
    with tempfile.TemporaryDirectory() as tmp:
        live = pathlib.Path(tmp) / "command-tree.json"
        status = _run([*EXPORT_CMD, str(live)], root)
        if status != 0:
            log.error(
                "command-tree: `%s <tmp>` failed with exit %d, so NOTHING was verified."
                % (" ".join(EXPORT_CMD), status)
            )
            return status

        # ANTI-VACUITY, before any comparison. An exporter that wrote nothing leaves the twin diffing the committed tree against emptiness and blaming the committed tree.
        if not live.is_file() or live.stat().st_size == 0:
            log.error(
                "command-tree: the exporter exited 0 but wrote no tree, so its verdict "
                "would be meaningless. Do NOT regenerate the committed file from this "
                "run; fix packages/cli/scripts/export-command-tree.ts first."
            )
            return 1

        if not committed.is_file():
            log.error("%s is missing." % COMMITTED_REL)
            print("  Regenerate it with: npm run export:command-tree -w @rediacc/cli")
            return 1

        live_nodes = node_count(live)
        if live_nodes == 0:
            log.error(
                "command-tree: the freshly exported tree declares 0 command(s), so this "
                "comparison scanned nothing. Two empty trees compare EQUAL, which is how "
                "this gate would report success over a broken exporter."
            )
            return 1

        if committed.read_bytes() != live.read_bytes():
            log.error("%s is STALE." % COMMITTED_REL)
            print()
            print("  The committed tree no longer matches the live CLI. Every validator that")
            print("  reads it is now describing a CLI that does not exist, and each of them")
            print("  fails OPEN, they keep passing while checking nothing.")
            print()
            print("  Fix:")
            print("    npm run export:command-tree -w @rediacc/cli")
            print("    git add packages/cli/scripts/command-tree.json")
            print()
            print("  Diff (committed vs live):")
            for line in diff_lines(committed, live):
                print(line)
            return 1

        log.info("%s matches the shipped CLI (%d command(s))" % (COMMITTED_REL, live_nodes))
        return 0


def _shims(bin_dir: pathlib.Path, build_status: int, export_body: str) -> None:
    """Write the `npm` and `npx` the gate will find on PATH.

    FILES, not Python mocks: the subject resolves both through PATH exactly as the bash twin does, and the differential drives the twin with these same shims. A mock inside this process would prove nothing about that resolution.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    npm = bin_dir / "npm"
    npm.write_text("#!/bin/bash\nexit %d\n" % build_status, encoding="utf-8")
    npm.chmod(0o755)
    npx = bin_dir / "npx"
    # `--output <path>` is the LAST argument the twin passes, so the shim reads
    # "${@: -1}" rather than parsing flags. Written the way the caller calls it.
    npx.write_text('#!/bin/bash\nOUT="${@: -1}"\n%s\n' % export_body, encoding="utf-8")
    npx.chmod(0o755)


def selftest() -> int:
    """Plant a defect in BOTH directions and require the gate to notice."""
    # floor=17 rather than 0: the floor is the only thing that catches a selftest
    # whose cases stopped executing, and a default of zero is a floor that cannot fail. See rediacc_ci.controls for the five drifted copies that taught it.
    ctl = Controls("command-tree", floor=17, verbose=True)
    saved_cwd = os.getcwd()
    saved_env = dict(os.environ)

    tree_a = json.dumps({"name": "rdc", "subcommands": [{"name": "repo"}]}, indent=2) + "\n"
    tree_b = json.dumps({"name": "rdc", "subcommands": [{"name": "machine"}]}, indent=2) + "\n"

    def run(committed: str | None, exported: str | None, build_status: int = 0) -> int:
        """Drive main() over a fixture with shimmed npm and npx."""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            if committed is not None:
                target = root / COMMITTED_REL
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(committed, encoding="utf-8")
            if exported is None:
                body = "true"
            else:
                source = root / "exported.json"
                source.write_text(exported, encoding="utf-8")
                # `cat` is an external command, so the shim directory is PREPENDED to the real PATH rather than replacing it. Stated because the sibling port `peer_deps` replaces PATH outright and the two selftests would otherwise look inconsistent for no reason a reader could see.
                body = 'cat "%s" > "$OUT"' % source
            _shims(root / "bin", build_status, body)
            os.environ[paths.ROOT_ENV] = str(root)
            os.environ["PATH"] = "%s:%s" % (root / "bin", saved_env.get("PATH", ""))
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved_env)
                os.chdir(saved_cwd)

    ctl.check("CONTROL: an identical committed tree passes", run(tree_a, tree_a), 0)

    # THE PLANT, both directions of drift.
    ctl.check("PLANT: a committed tree that lost a command is STALE", run(tree_a, tree_b), 1)
    ctl.check("PLANT: a committed tree with an EXTRA command is STALE", run(tree_b, tree_a), 1)

    # Byte equality, not parsed equality: see the port notes. A reformat of the SAME content is a real finding here, and the mirror proves the gate is not comparing parsed JSON by accident.
    reformatted = json.dumps(json.loads(tree_a), indent=4) + "\n"
    ctl.check("BYTES: a reformatted but equivalent tree is STALE", run(tree_a, reformatted), 1)
    ctl.check(
        "BYTES MIRROR: byte-identical content with no reformat passes",
        run(tree_a, tree_a),
        0,
    )

    ctl.check("PLANT: a missing committed tree is refused", run(None, tree_a), 1)

    # VACUITY, four ways. Every one of these is a tree the twin calls STALE, or GREEN, having verified nothing.
    ctl.check("VACUITY: an exporter that writes nothing is refused", run(tree_a, None), 1)
    ctl.check("VACUITY: an exporter that writes an empty file is refused", run(tree_a, ""), 1)
    ctl.check("VACUITY: two EMPTY trees are refused, not called equal", run("", ""), 1)
    ctl.check(
        "VACUITY: an exported tree with 0 commands is refused",
        run("[]\n", "[]\n"),
        1,
    )
    # And the mirror, so the floor is not simply firing on everything: the smallest real tree, one command, is enough.
    smallest = json.dumps({"name": "rdc"}) + "\n"
    ctl.check("FLOOR MIRROR: a one-command tree is enough", run(smallest, smallest), 0)

    # A failing build must carry the child's exit code out, not be swallowed.
    ctl.check("PLANT: a failing build:packages exits with its own code", run(tree_a, tree_a, 3), 3)

    # The pure helpers, driven directly.
    ctl.check("HELPER: node_count walks subcommands", node_count_of(tree_a), 2)
    ctl.check("HELPER: node_count of a non-tree is 0", node_count_of("[]\n"), 0)

    with tempfile.TemporaryDirectory() as tmp:
        left = pathlib.Path(tmp) / "a.json"
        right = pathlib.Path(tmp) / "b.json"
        left.write_text("one\ntwo\n", encoding="utf-8")
        right.write_text("one\nTWO\n", encoding="utf-8")
        lines = diff_lines(left, right)
        ctl.check("HELPER: every diff line carries the four-space indent", lines[0], "    2c2")
        ctl.check(
            "HELPER: the diff body is diff(1)'s own",
            lines[1:],
            ["    < two", "    ---", "    > TWO"],
        )
        long_left = pathlib.Path(tmp) / "l.json"
        long_right = pathlib.Path(tmp) / "r.json"
        long_left.write_text("".join("%d\n" % i for i in range(100)), encoding="utf-8")
        long_right.write_text("".join("x%d\n" % i for i in range(100)), encoding="utf-8")
        ctl.check(
            "HELPER: the diff is capped at %d lines" % DIFF_CAP,
            len(diff_lines(long_left, long_right)),
            DIFF_CAP,
        )

    return 0 if ctl.report() else 1


def node_count_of(text: str) -> int:
    """`node_count` over a string, for the selftest. Writes a real file because
    `node_count` reads one, and a second parsing path would be a second thing to
    keep in agreement."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "t.json"
        path.write_text(text, encoding="utf-8")
        return node_count(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
