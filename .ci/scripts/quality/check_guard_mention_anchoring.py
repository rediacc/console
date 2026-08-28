#!/usr/bin/env python3
"""A guard must refuse a COMMAND, never a SENTENCE about one.

WHY THIS EXISTS. The defect class is "matches a MENTION rather than a TARGET":
a guard greps the command line for a phrase, finds it inside prose, and refuses
a worklist note or a doc line as if it were the rule being broken. It recurred
FOUR times on 2026-08-28 alone -- block-bash-write-to-running-script.sh,
block-roundlog-truncate.sh, block-git-empty-commit.sh (whose own header records
being routed through command-scan.sh "because matching the raw command meant
matching PROSE", a fix that covered the QUOTED case only), and
warn-stale-index.sh, which was written by the session fixing the other three and
reintroduced the class within the hour. Every instance was repaired by hand and
nothing stopped the next one.

HOW THE PROBE IS BUILT, and why the obvious version does not work. The first
attempt collected a guard's vocabulary and wrote a sentence out of it. That gate
passed while the pre-fix unanchored matcher was planted back into
block-git-empty-commit.sh, because the words were sorted alphabetically and the
pattern needs `git commit` BEFORE `--allow-empty`. A probe that cannot trigger
the guard proves nothing about it.

So the pattern itself is turned into a CONCRETE INSTANCE -- the shortest literal
string that matches it -- and that instance is embedded in an ordinary sentence.
If the guard fires on the sentence, it is matching a mention.

ANCHOR, DO NOT NARROW. The fix for a finding here is to require command position
`(^|[;&|(])`, never to delete the pattern: a guard that stops catching the real
command is a worse outcome than the false positive it was cured of.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD_DIR = REPO_ROOT / ".claude" / "hooks" / "pre-bash"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Guards whose matching is deliberately quote-blind, with the reason taken from
# the guard itself rather than invented here.
#
# BLOCKER: block-adhoc-sanctioned.sh delegates matching to lib/sanctioned.py and
# holds no inline pattern to turn into an instance. Its own comment states the
# trade-off knowingly -- "the residue is that `echo 'gh run watch 123'` is still
# refused. That is the price of seeing inside quotes, it is paid knowingly" --
# and it mitigates the costly half by stripping heredoc bodies, which is where a
# quoted recipe actually lives.
ALLOW_UNPROBED = {"block-adhoc-sanctioned.sh"}

# A pattern must look like a command matcher before it is worth instantiating.
INTERESTING = re.compile(r"\[\[:|\\\||\|\||\+|\*")

# Evidence the author constrained the match to command POSITION rather than
# accepting it anywhere in the line.
ANCHORED = re.compile(r"\(\^\||\^\(|\[;&\|\(|\[;&\|]")

CLASS_SUB = [
    (re.compile(r"\[\[:space:\]\][+*]"), " "),
    (re.compile(r"\[\[:alnum:\]\][+*]?"), "x"),
    (re.compile(r"\[\[:alpha:\]\][+*]?"), "x"),
    (re.compile(r"\[\[:digit:\]\][+*]?"), "1"),
    (re.compile(r"\[\^[^\]]*\][+*]"), " "),
    (re.compile(r"\[\^[^\]]*\]"), "x"),
    (re.compile(r"\[[^\]]*\][+*]?"), "x"),
]


def instantiate(pattern: str) -> str:
    """The shortest literal string a pattern would match, best-effort.

    Best-effort is enough: a probe that fails to trigger a guard is reported as
    UNPROBED rather than silently counted as clean, so an imperfect instance
    costs coverage that is visible, never a false green.
    """
    text = pattern
    # An alternation: take the first branch, which is what a real command does.
    text = re.sub(r"\(([^()|]*)\|[^()]*\)", r"\1", text)
    text = re.sub(r"\(\?:", "(", text)
    for rx, rep in CLASS_SUB:
        text = rx.sub(rep, text)
    text = text.replace("(", "").replace(")", "")
    text = re.sub(r"\\b|\\B|\^|\$", "", text)
    text = re.sub(r"([A-Za-z0-9_./-])[+*]", r"\1", text)
    text = re.sub(r"\\(.)", r"\1", text)
    text = re.sub(r"[?]", "", text)
    # A PROBE MUST STAY PROSE. An instance carrying a real command separator
    # creates a genuine command POSITION inside the sentence, and the guard is
    # then right to fire -- which reads as a finding and is not one. Measured:
    # an instance ending in a backgrounding operator was reported against
    # block-shell-background-waiter.sh, whose natural-sentence probe is silent.
    text = re.sub(r"[&;|`]", " ", text)
    text = text.replace("$(", " ").replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", text).strip()


def patterns_of(path: Path) -> list[str]:
    """Every quoted string in the guard that looks like a command matcher.

    NOT just the ones on a `grep` line. Eight guards keep their patterns in an
    array or a variable and interpolate later (`grep -qE "$pat"`), so a
    grep-line-only reader left them UNPROBED -- and an unprobed guard's silence
    proves nothing, which is the failure this whole gate exists to prevent. The
    INTERESTING filter is what keeps ordinary prose strings out.
    """
    src = path.read_text(encoding="utf-8", errors="replace")
    out: list[str] = []
    # GREP-LINE PATTERNS FIRST. Broadening the reader to every quoted string in
    # the file (needed for guards that keep patterns in arrays) buried the real
    # matcher behind message text and helper strings, and the probe cap then cut
    # it off. Measured: planting the pre-fix unanchored matcher back into
    # block-git-empty-commit.sh was NOT caught, because its `--allow-empty`
    # pattern sorted past the window. Priority is not cosmetic here; it is what
    # makes the probe reach the thing that matters.
    for rx in (
        r"grep -q[a-zA-Z]*\s+(?:--\s+)?'([^'\n]{4,})'",
        r'grep -q[a-zA-Z]*\s+(?:--\s+)?"([^"\n]{4,})"',
        r"'([^'\n]{4,})'",
        r'"([^"\n]{4,})"',
    ):
        out.extend(m.group(1) for m in re.finditer(rx, src))
    # A comment line is prose about a pattern, never a pattern. Reading one
    # would manufacture a finding out of the guard's own documentation.
    body = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    joined = "\n".join(body)
    out = [p for p in out if p in joined]
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return [p for p in uniq if INTERESTING.search(p)]


def fires(guard: Path, command: str) -> bool:
    payload = json.dumps({"tool_input": {"command": command}})
    try:
        proc = subprocess.run(
            ["bash", str(guard)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
            check=False,  # a guard's exit 2 IS the signal; raising would lose it
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 2


def sentence(instance: str) -> str:
    return f"echo the docs say never to run {instance} in this repo"


def controls() -> None:
    """A detector that cannot fire would pass the whole file silently."""
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "unanchored.sh"
        good = Path(td) / "anchored.sh"
        bad.write_text(
            "#!/usr/bin/env bash\n"
            "CMD=$(jq -r '.tool_input.command' 2>/dev/null)\n"
            "printf '%s' \"$CMD\" | grep -qE 'frobnicate[[:space:]]+widgets' && exit 2\n"
            "exit 0\n"
        )
        good.write_text(
            "#!/usr/bin/env bash\n"
            "CMD=$(jq -r '.tool_input.command' 2>/dev/null)\n"
            "printf '%s' \"$CMD\" | grep -qE '(^|[;&|(])[[:space:]]*frobnicate[[:space:]]+widgets' && exit 2\n"
            "exit 0\n"
        )
        probe = sentence("frobnicate widgets")
        if not fires(bad, probe):
            fail("an UNANCHORED fixture was not caught; the detector cannot fire")
        if fires(good, probe):
            fail("an ANCHORED fixture was reported as firing; the detector flags everything")
        if not fires(good, "frobnicate widgets --now"):
            fail(
                "the anchored fixture missed the REAL command; anchoring must narrow prose, not the target"
            )
        # The instantiator is load-bearing, so it gets its own control.
        got = instantiate(r"git[[:space:]]+commit[^|;&]*--allow-empty")
        if "git commit" not in got or "--allow-empty" not in got:
            fail(f"instantiate() lost the pattern's order or literals: {got!r}")


def fail(msg: str) -> None:
    print(f"{RED}✗ CONTROL FAILED{NC}: {msg}", file=sys.stderr)
    print("  A clean result below would mean nothing, so this gate refuses.", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    controls()

    probed = 0
    static_ok = 0
    unprobed: list[str] = []
    offenders: list[tuple[str, str]] = []

    for guard in sorted(GUARD_DIR.glob("*.sh")):
        name = guard.name
        if name.startswith("test-"):
            continue
        instances = [instantiate(p) for p in patterns_of(guard)]
        instances = [i for i in instances if len(i) >= 4]
        if not instances:
            # TIER 2, STATIC. A guard with no renderable instance is not
            # automatically a defect, and treating it as one would demand that
            # guards be rewritten to suit this instantiator rather than to
            # match commands correctly. Two legitimate shapes exist and both
            # were measured here:
            #
            #   * ALREADY ANCHORED -- block-blanket-git-add.sh and
            #     block-worktree-add.sh carry `(^|[;&|(]|\$\(|`)` prefixes;
            #     the pattern is simply too gnarly to render into a literal.
            #   * NOT A PHRASE MATCHER AT ALL -- block-long-sleep.sh extracts a
            #     NUMBER (`grep -oE 'sleep +[0-9]+'`) and compares it. There is
            #     no phrase to find inside prose, so the class does not apply.
            #
            # So: pass if the guard shows an anchor, or has nothing to anchor.
            # Fail only when it phrase-matches with no anchor and no probe --
            # the case where nothing at all is checking it.
            pats = patterns_of(guard)
            if name in ALLOW_UNPROBED:
                continue
            if not pats or any(ANCHORED.search(x) for x in pats):
                static_ok += 1
                continue
            unprobed.append(name)
            continue
        probed += 1
        for inst in instances[:40]:
            if fires(guard, sentence(inst)):
                offenders.append((name, inst))
                break

    if probed < 20:
        print(
            f"{RED}✗{NC} only {probed} guard(s) were probed; the enumeration or the",
            file=sys.stderr,
        )
        print(
            "  instantiator is broken, not the guards. A scan this small cannot fail.",
            file=sys.stderr,
        )
        return 1

    for name, inst in offenders:
        print(f"{RED}✗{NC} {name} refuses PROSE, not a command.", file=sys.stderr)
        print(f"    sentence: {sentence(inst)}", file=sys.stderr)
        print(
            "    Anchor the match to command position -- (^|[;&|(]) and friends --", file=sys.stderr
        )
        print("    rather than deleting or narrowing the pattern.", file=sys.stderr)

    for name in unprobed:
        print(
            f"{RED}✗{NC} {name}: no pattern could be instantiated, so it cannot be", file=sys.stderr
        )
        print("    probed and its silence proves nothing. Give it an inline grep", file=sys.stderr)
        print("    pattern, or add it to ALLOW_UNPROBED with a BLOCKER reason.", file=sys.stderr)

    if offenders or unprobed:
        print(
            f"\n{RED}✗{NC} {len(offenders)} guard(s) refuse prose; {len(unprobed)} could not be probed.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{GREEN}✓{NC} {probed} pre-bash guard(s) probed with a live sentence and refuse "
        f"commands, not sentences about them; {static_ok} more are anchored or do not "
        f"phrase-match"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
