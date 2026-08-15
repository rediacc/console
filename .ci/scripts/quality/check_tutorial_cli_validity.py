#!/usr/bin/env python3
"""Every `rdc` command a tutorial runs must exist, with the flags it passes.

WHY THIS EXISTS. The tutorials are executable documentation: CI runs the whole
sequence against real VMs, and a customer follows the same steps. When a command
or a flag is renamed, the tutorial keeps naming the old one and nothing says so
until the sequence runs, which is 20 minutes into a job that needs a provisioned
cluster.

WHAT IT DOES NOT COVER, stated plainly because the gap is the interesting part.
This finds a command or flag that does NOT EXIST. It cannot find one that exists
and is refused. The defect that motivated it was the second kind: the rclone arm
was retired, `rdc repo push my-app --to my-storage` still parses today because
`--to` is still a flag, and the engine refuses it only once the ARGUMENT resolves
to a storage remote. A flag-existence check goes green over that line. What
caught it was CI running the sequence end to end.

So this is not the gate for that defect. It is a cheaper gate for a neighbouring
class that nothing covered either, and pretending otherwise would make it the
kind of reassuring-but-blind check this repo keeps having to unlearn.

THE ORACLE is packages/cli/scripts/command-tree.json, the exported Commander
tree, not `rdc --help`. It needs no build, and check:ci-command-tree already
proves it matches the shipped CLI, so a stale tree is somebody else's red rather
than a silent pass here.
"""

import json
import pathlib
import re
import shlex
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
TUTORIALS = REPO / ".ci" / "tutorials"
TREE = REPO / "packages" / "cli" / "scripts" / "command-tree.json"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# A token carrying shell interpolation cannot be resolved statically. Skipping is
# correct; PRETENDING to check it would be the lie.
UNRESOLVABLE = re.compile(r"[$`]")


def flags_of(node):
    out = set()
    for opt in node.get("options") or []:
        for raw_piece in str(opt.get("flags") or "").split(","):
            piece = raw_piece.strip().split(" ")[0].split("=")[0]
            if piece.startswith("-"):
                out.add(piece)
    return out


def resolve(tree, words):
    """Walk the command path; returns (node, consumed) or (None, depth-reached)."""
    node, consumed = tree, 0
    for word in words:
        children = {c.get("name"): c for c in (node.get("subcommands") or [])}
        if word not in children:
            break
        node = children[word]
        consumed += 1
    return node, consumed


def invocations(text):
    """Every `rdc ...` command line in a script, already shell-unquoted."""
    found = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        # run_cmd "rdc ..." is the tutorials' own wrapper; bare `rdc ...` also
        # appears in setup blocks.
        found.extend(match.group(1) for match in re.finditer(r'run_cmd\s+"([^"]*)"', line))
        if re.match(r"^(sudo\s+)?rdc\s", line):
            found.append(line)
    return [f for f in found if re.search(r"(^|\s)rdc\s", f)]


def check(tree, scripts):
    """Returns (findings, checked_invocations)."""
    findings = []
    checked = 0
    global_flags = flags_of(tree)

    for path in scripts:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for raw_cmd in invocations(text):
            cmd = raw_cmd[raw_cmd.index("rdc") :]
            try:
                words = shlex.split(cmd)
            except ValueError:
                continue
            words = words[1:]  # drop `rdc`
            path_words = []
            for word in words:
                if word.startswith("-"):
                    break
                if UNRESOLVABLE.search(word):
                    break
                path_words.append(word)
            if not path_words:
                continue

            node, consumed = resolve(tree, path_words)
            if consumed == 0:
                findings.append((path.name, cmd, "no such command '%s'" % path_words[0]))
                continue

            # NAME THE RIGHT PROBLEM. A removed SUBCOMMAND otherwise surfaces as
            # a flag complaint: `rdc backup sync push --to x` resolves `backup`,
            # stops at the missing `sync`, and then reports "`backup` takes no
            # --to", which sends the reader to the flag instead of the verb that
            # no longer exists. A node that has subcommands and takes no
            # positional arguments cannot be receiving one, so an unconsumed word
            # there is a bad subcommand, not an argument.
            if (
                consumed < len(path_words)
                and (node.get("subcommands") or [])
                and not (node.get("arguments") or [])
            ):
                findings.append(
                    (
                        path.name,
                        cmd,
                        "`%s` has no subcommand '%s'"
                        % (" ".join(path_words[:consumed]), path_words[consumed]),
                    )
                )
                continue
            checked += 1

            allowed = flags_of(node) | global_flags
            for word in words:
                if not word.startswith("--") or UNRESOLVABLE.search(word):
                    continue
                flag = word.split("=")[0]
                if flag == "--":
                    continue
                if flag not in allowed:
                    findings.append(
                        (
                            path.name,
                            cmd,
                            "`%s` takes no %s" % (" ".join(path_words[:consumed]), flag),
                        )
                    )
    return findings, checked


def run_controls(tree):
    """Prove the rule fires on a bad flag and stays quiet on a good one.

    The controls write REAL files into a temp dir rather than faking a path
    object. A stub whose read_text signature merely resembles pathlib's is one
    refactor away from diverging from the thing it stands in for, and it forced
    an unused-argument suppression that this repo does not allow.
    """
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        def planted(body):
            path = tmpdir / "tutorial-planted.sh"
            path.write_text(body)
            return [path]

        found, _ = check(tree, planted('run_cmd "rdc repo list --not-a-real-flag"'))
        if not found:
            failures.append("an invented flag was not flagged")

        found, _ = check(tree, planted('run_cmd "rdc repo list --machine prod-1"'))
        if found:
            failures.append("a real flag was reported as invalid: %s" % found[0][2])

        found, _ = check(tree, planted('run_cmd "rdc nosuchverb thing"'))
        if not found:
            failures.append("an invented command was not flagged")

        # The message must name the VERB, not a flag. `backup sync push` was a
        # real command until this wave deleted it, and the first version of this
        # gate reported it as "`backup` takes no --to" -- true, useless, and
        # pointing at the wrong file to edit.
        found, _ = check(tree, planted('run_cmd "rdc backup sync push my-app --to my-storage"'))
        if not found:
            failures.append("a removed subcommand was not flagged")
        elif "subcommand" not in found[0][2]:
            failures.append("a removed subcommand was reported as a flag problem: %s" % found[0][2])

        found, _ = check(tree, planted('run_cmd "rdc repo list --machine $M"'))
        if found:
            failures.append("a shell-interpolated argument was treated as literal")

    return failures


def main() -> int:
    print("Tutorial rdc invocations: do the command and its flags exist?")
    print("=" * 62)

    if not TREE.is_file():
        print(
            f"{RED}x{NC} {TREE} is missing; regenerate with npm run export:command-tree -w @rediacc/cli"
        )
        return 1
    tree = json.loads(TREE.read_text())

    control_failures = run_controls(tree)
    if control_failures:
        for f in control_failures:
            print(f"{RED}x{NC} control: {f}")
        print(f"{RED}x{NC} the rule itself is broken, so no verdict it produces means anything.")
        return 1
    print(f"{GREEN}v{NC} control fired: an invented flag and command are caught, real ones are not")

    scripts = sorted(TUTORIALS.glob("tutorial-*.sh"))
    if not scripts:
        print(
            f"{RED}x{NC} no tutorial scripts found; checking nothing exits 0 exactly like checking everything"
        )
        return 1

    findings, checked = check(tree, scripts)

    # A rule that resolved no invocation passes forever.
    if checked < 20:
        print(
            f"{RED}x{NC} only {checked} invocation(s) resolved across {len(scripts)} script(s); the rule has been unhooked"
        )
        return 1

    if findings:
        for name, cmd, why in findings:
            print(f"{RED}x{NC} {name}: {why}")
            print(f"    {cmd}")
        print()
        print(
            f"{RED}x{NC} {len(findings)} tutorial invocation(s) name a command or flag the CLI does not have."
        )
        print("  CI runs these against real VMs and customers follow them by hand, so a rename")
        print("  that misses a tutorial fails 20 minutes into a provisioned job, or in public.")
        return 1

    print(
        f"{GREEN}v{NC} {checked} invocation(s) across {len(scripts)} tutorial(s): every command and flag exists"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
