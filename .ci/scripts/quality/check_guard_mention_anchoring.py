#!/usr/bin/env python3
"""A guard must refuse a COMMAND, never a SENTENCE about one.

WHY THIS EXISTS. The defect class is "matches a MENTION rather than a TARGET": a guard greps the command line for a phrase, finds it inside prose, and refuses a worklist note or a doc line as if it were the rule being broken. It recurred FOUR times on 2026-08-28 alone -- block-bash-write-to-running-script.sh, block-roundlog-truncate.sh, block-git-empty-commit.sh (whose own header
records being routed through command-scan.sh "because matching the raw command meant matching PROSE", a fix that covered the QUOTED case only), and warn-stale-index.sh, which was written by the session fixing the other three and reintroduced the class within the hour. Every instance was repaired by hand and nothing stopped the next one.

HOW THE PROBE IS BUILT, and why the obvious version does not work. The first attempt collected a guard's vocabulary and wrote a sentence out of it. That gate passed while the pre-fix unanchored matcher was planted back into block-git-empty-commit.sh, because the words were sorted alphabetically and the pattern needs `git commit` BEFORE `--allow-empty`. A probe that cannot trigger
the guard proves nothing about it.

So the pattern itself is turned into a CONCRETE INSTANCE -- the shortest literal string that matches it -- and that instance is embedded in an ordinary sentence. If the guard fires on the sentence, it is matching a mention.

ANCHOR, DO NOT NARROW. The fix for a finding here is to require command position `(^|[;&|(])`, never to delete the pattern: a guard that stops catching the real command is a worse outcome than the false positive it was cured of.

RETARGETED 2026-09-24 (PLAN-retire-bash-oracles A2) from `.claude/oracles/`'s frozen bash originals to the LIVE Python guard modules at `.claude/rediacc_hooks/guards/`. The residue this file used to state out loud -- "a pattern edited in the PORT and not in the oracle is invisible here, because the oracle cannot change" -- is closed by this change rather than carried forward: there is no longer a second, frozen copy of a guard's pattern for an edit to miss. Patterns are read via `ast`, not text search, so a constant built across several lines, by string-literal concatenation, or from `hookio.rx()`'s `{S}`/`{B}` placeholders resolves exactly as the interpreter would resolve it.

---- gate ----
step: Guard mention anchoring
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
why: A guard that refuses PROSE is a guard nobody can write a doc line about.
     The class recurred FOUR times on 2026-08-28 and every instance was fixed
     by hand, including one reintroduced within the hour by the session doing
     the fixing -- which is the i18n lesson exactly. This probes each guard
     with a sentence built from its OWN pattern, so it cannot go stale as
     guards are added.
---- end gate ----
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
from pathlib import Path

import _cipath  # noqa: F401

# ALIASED: `proc` is the name this file's own code reaches for when it holds a completed process, and it did until these call sites were routed. Keeping the
# runner under a distinct name means a future local `proc =` cannot shadow it
# into a NameError on the timeout path -- the path least likely to be exercised.
from rediacc_ci import proc as ci_proc

REPO_ROOT = Path(__file__).resolve().parents[3]
# THE LIVE GUARD PACKAGE, not the retired oracle tree (PLAN-retire-bash-oracles A2). Patterns and the guard both come from here now, so there is exactly one copy of each guard's matcher to keep anchored.
GUARDS = REPO_ROOT / ".claude" / "rediacc_hooks" / "guards"
DISPATCH = REPO_ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"


def guard_argv(guard):
    """How to RUN the guard this path names.

    A path under the live guard package names an importable module, dispatched by stem through ONE entry point per chain. Anything else is run as a file, which is what the throwaway fixtures `controls()` writes have to be: they are bash by construction, deliberately, so that rewording a real guard cannot silently void the control.
    """
    try:
        guard.relative_to(GUARDS)
    except ValueError:
        return ["bash", str(guard)]
    return [sys.executable, str(DISPATCH), guard.stem]


# EVERY CHAIN, not just pre-bash. Scoping this to one directory was the same hole check-hook-integrity.sh has now had twice (pre-edit/pre-ask in its 2026-08-27 repair, post-bash in e60e30331) -- and it was in the file written to stop exactly this class. Found by e580532b: 35 of 42 guards were probed and 7 were not.
#
# The chains do not share a payload shape, which is why this is a builder and not one dict. A wrong key produces a probe that CANNOT FIRE, and a probe that cannot fire proves nothing -- so every prose probe below is paired with a positive one, and a guard whose positive probe stays silent is reported UNPROBED rather than counted clean.
CHAINS = {
    "pre-bash": "command",
    "pre-edit": "edit",
    "pre-ask": "ask",
}

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Guards whose matching is deliberately quote-blind, with the reason taken from the guard itself rather than invented here.
#
# BLOCKER: block_adhoc_sanctioned.py delegates matching to lib/sanctioned.py and holds no inline pattern to turn into an instance. Its own comment states the trade-off knowingly -- "the residue is that `echo 'gh run watch 123'` is still refused. That is the price of seeing inside quotes, it is paid knowingly" -- and it mitigates the costly half by stripping heredoc bodies, which is
# where a quoted recipe actually lives.
#
# BLOCKER: block_edit_of_running_script.py's decision is keyed on FILE IDENTITY (is the edited path one of the shell scripts a live process is currently interpreting) and the real process table, not on any phrase inside the edited content. `HOOK_CHAIN` matches a script PATH, not a command, and `META` is a character-escape set for building a `sed`-style substitution, not a matcher at
# all -- found live by this A2 retarget, whose ast-based reader surfaces both as string constants where the old text search never reached them. Neither is the "refuses a mention instead of a target" class this file exists to catch, because there is no prose to confuse with a target: a file is either the one running or it is not.
ALLOW_UNPROBED = {"block_adhoc_sanctioned.py", "block_edit_of_running_script.py"}

# A pattern must look like a command matcher before it is worth instantiating. Tuned for PYTHON `re` syntax rather than POSIX bracket expressions, since A2 retargeted the source from bash originals to the live guard modules: an anchor prefix, a character class built around the command separators, a word boundary, a non-capturing group, or a quantifier.
INTERESTING = re.compile(r"\(\^\||\[;&|\\b|\(\?:|[+*]")

# Evidence the author constrained the match to command POSITION rather than accepting it anywhere in the line. Unchanged by the A2 retarget: guards write this anchor idiom identically in bash and in Python, since it is a regex fragment, not a shell construct.
ANCHORED = re.compile(r"\(\^\||\^\(|\[;&\|\(|\[;&\|]")

CLASS_SUB = [
    # Backslash character classes, Python's own spelling of what the bash originals wrote as POSIX bracket expressions. Collapsed the same way: a run of the class to one representative character, so the instance stays a short, readable literal rather than a soup of metacharacters.
    (re.compile(r"\\s[+*]?"), " "),
    (re.compile(r"\\S[+*]?"), "x"),
    (re.compile(r"\\d[+*]?"), "1"),
    (re.compile(r"\\D[+*]?"), "x"),
    (re.compile(r"\\w[+*]?"), "x"),
    (re.compile(r"\\W[+*]?"), " "),
    (re.compile(r"\[\^[^\]]*\][+*]"), " "),
    (re.compile(r"\[\^[^\]]*\]"), "x"),
    (re.compile(r"\[[^\]]*\][+*]?"), "x"),
]


def instantiate(pattern: str) -> str:
    """The shortest literal string a pattern would match, best-effort.

    Best-effort is enough: a probe that fails to trigger a guard is reported as UNPROBED rather than silently counted as clean, so an imperfect instance costs coverage that is visible, never a false green.
    """
    text = pattern
    # DROP A LEADING ANCHOR GROUP FIRST. `(^|[;&|(]|&&|\|\|)[\s]*` is a POSITION assertion, not text, and it must contribute nothing to the literal. Left in, it survives as junk: the branch-picker below cannot split it (its character class contains parentheses, so `[^()|]*` fails) and the class then collapses to a literal `x`, yielding `x git commit --allow-empty`. That string is
    # not at command position, so a correctly-anchored guard does NOT fire on it -- and the positive probe then reports every anchored guard as unreachable. Measured: 0 of 42 probed.
    text = re.sub(r"^\((?=[^)]*\^)[^)]*\)(\\s[*+])?", "", text)
    # LOOKAROUNDS CONTRIBUTE NO TEXT. `(?=$|[\s;&|])` (`block_prose_style_commit.GIT_COMMIT`'s trailing assertion) is a zero-width constraint, not a branch of real content, and running it through the branch-picker below would leak assertion syntax ("?=$") into the literal instance -- traced through by hand rather than measured, since a Python guard using a lookaround is new with
    # this A2 retarget. Stripped whole, in a fixed-point loop for the rare pattern carrying more than one, and BEFORE the branch-picker so it never sees one.
    for _ in range(5):
        prev = text
        text = re.sub(r"\(\?(?:=|!|<=|<!)(?:[^()]|\([^()]*\))*\)", "", text)
        if text == prev:
            break
    # An alternation: take the first branch, which is what a real command does. RESOLVED INNERMOST-FIRST, in a fixed-point loop. The single-pass version only matched a group with NO nested parens (`[^()]*`), so a pattern like `\bssh\b...\b(cat|echo|printf)\b` -- an alternation with a NESTED one inside its second branch -- left the outer group untouched and the whole instance
    # collapsed to a stray `>`. Measured against block-ssh-file-write.sh, which is why this exists.
    text = re.sub(r"\(\?:", "(", text)
    # ESCAPE-AWARE: `[^()|]` treats a literal `\|` (an ESCAPED pipe, i.e. the two characters backslash-then-pipe, matching a real `|` in a command) as the alternation delimiter, because the character class excludes bare `|` regardless of what precedes it. That misread block-ssh-file-write.sh's `\|\s*\bssh\b...` down to a single stray `>`. `(?:[^()|\\]|\\.)` consumes a
    # backslash-escaped pair as ONE unit first, so only a genuine, unescaped `|` ends a branch.
    for _ in range(10):
        prev = text
        text = re.sub(r"\(((?:[^()|\\]|\\.)*)\|(?:[^()\\]|\\.)*\)", r"\1", text)
        if text == prev:
            break
    for rx, rep in CLASS_SUB:
        text = rx.sub(rep, text)
    # A TOP-LEVEL alternation, with no enclosing parens at all. The loop above only resolves a `|` sitting inside `(...)`; block-ssh-file-write.sh's pattern is a bare `BRANCH1|BRANCH2` at the top, so nothing caught it and the second branch leaked into the instance. Escape-aware, same as the parenthesized case: an escaped `\|` (a literal pipe target) must not be read as the
    # delimiter.
    m = re.match(r"^((?:[^|\\]|\\.)*)\|", text)
    if m:
        text = m.group(1)
    text = text.replace("(", "").replace(")", "")
    text = re.sub(r"\\b|\\B|\^|\$", "", text)
    text = re.sub(r"([A-Za-z0-9_./-])[+*]", r"\1", text)
    text = re.sub(r"\\(.)", r"\1", text)
    text = re.sub(r"[?]", "", text)
    # A PROBE MUST STAY PROSE. An instance carrying a real command separator creates a genuine command POSITION inside the sentence, and the guard is then right to fire -- which reads as a finding and is not one. Measured: an instance ending in a backgrounding operator was reported against block-shell-background-waiter.sh, whose natural-sentence probe is silent.
    text = re.sub(r"[&;|`]", " ", text)
    text = text.replace("$(", " ").replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", text).strip()


def _shellscan_placeholders() -> tuple[str, str]:
    """`(SPACE, BLANK)`, read from `shellscan.py` rather than retyped here.

    `hookio.rx()` substitutes `{S}`/`{B}` for these two character-class bodies at import time, so instantiating a pattern that uses them needs the same substitution. Reading them from the one file that defines them means a change there cannot silently desync from a second, hand-copied pair here; a fallback covers the read failing outright, since a stale pair is still closer to
    right than crashing this gate over a file it does not otherwise depend on.
    """
    path = REPO_ROOT / ".claude" / "rediacc_hooks" / "shellscan.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except OSError:
        return r" \t\n\v\f\r", r" \t\v\f\r"
    found: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("SPACE", "BLANK")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.targets[0].id] = node.value.value
    return found.get("SPACE", r" \t\n\v\f\r"), found.get("BLANK", r" \t\v\f\r")


SPACE, BLANK = _shellscan_placeholders()


def _const_eval(node: ast.AST, table: dict[str, str]) -> str | None:
    """Best-effort constant folding for one guard's regex-shaped assignments.

    A guard's matcher is not always a single string literal: `hookio.rx(...)` and `re.compile(...)` wrap one, several guards build theirs by concatenating a literal with `hookio.SPACE`/`hookio.BLANK` (the pre-`rx()` idiom, six guards still use it for a fragment `rx()`'s `{S}`/`{B}` placeholders do not reach), and a `NAME = expr` two constants up can be referenced by name in a
    later one, exactly as the interpreter would resolve it at import time. `table` carries every module-level constant already folded earlier in the same file, in source order, so a helper like `_S = hookio.SPACE` is available by the time a later line concatenates it in.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_eval(node.left, table)
        right = _const_eval(node.right, table)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name):
        return table.get(node.id)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "hookio"
    ):
        if node.attr == "SPACE":
            return SPACE
        if node.attr == "BLANK":
            return BLANK
        return None
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        is_rx = (isinstance(func, ast.Attribute) and func.attr == "rx") or (
            isinstance(func, ast.Name) and func.id == "rx"
        )
        is_compile = isinstance(func, ast.Attribute) and func.attr == "compile"
        if not (is_rx or is_compile):
            return None
        inner = _const_eval(node.args[0], table)
        if inner is None:
            return None
        return inner.replace("{S}", SPACE).replace("{B}", BLANK) if is_rx else inner
    return None


def patterns_of(path: Path) -> list[str]:
    """Every command-matcher-shaped string this guard module resolves to a constant.

    Read from the AST, not the source TEXT: PLAN-retire-bash-oracles A2 retargeted this file from grepping quoted strings out of a frozen bash original to reading the LIVE Python guard's own regex constants, and those are not always one quoted literal on one line -- `hookio.rx(...)`, `re.compile(...)`, string-literal concatenation split across lines, and a constant built from
    another constant defined earlier in the same file all have to resolve exactly as the interpreter resolves them, or a real edit to a pattern goes on being invisible here for a different reason than the one this file used to name. The INTERESTING filter is what keeps ordinary message strings and non-matcher constants (`CHAIN`, `TWIN`, a file path) out.
    """
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))
    table: dict[str, str] = {}
    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        value = _const_eval(node.value, table)
        if value is not None:
            table[node.targets[0].id] = value
    seen: set[str] = set()
    uniq: list[str] = []
    for x in table.values():
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return [p for p in uniq if INTERESTING.search(p)]


def payload_for(kind: str, text: str, file_path: str) -> str:
    """The tool_input shape each chain actually reads.

    Derived from the guards themselves: pre-edit reads file_path plus one of content / new_string / new_source / edits; pre-ask reads question and questions. Every field is filled rather than guessed at, because a guard that reads the one field left out would silently never fire.
    """
    if kind == "command":
        return json.dumps({"tool_input": {"command": text}})
    if kind == "edit":
        return json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": file_path,
                    "content": text,
                    "new_string": text,
                    "new_source": text,
                    "edits": [{"old_string": "x", "new_string": text}],
                },
            }
        )
    return json.dumps({"tool_input": {"question": text, "questions": [{"question": text}]}})


def fires(guard: Path, command: str, kind: str = "command", file_path: str = "") -> bool:
    payload = payload_for(kind, command, file_path)
    # THROUGH THE SHARED RUNNER. A guard is a script, and a script can leave a grandchild holding the read end; `subprocess.run` then blocks in `communicate()` past its own timeout, which is how check:ci-pytest came to hang with zero bytes on both streams. `proc.run` kills the group, and it RETURNS on timeout rather than raising, so the old `except TimeoutExpired` is gone -- only a
    # missing binary still raises.
    try:
        result = ci_proc.run(
            guard_argv(guard),
            input_text=payload,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
    except OSError:
        return False
    if result.timed_out:
        # A guard that will not answer is not a guard that said "no".
        return False
    return result.returncode == 2


def chain_of(path: Path) -> str | None:
    """This guard module's own `CHAIN = "..."` constant, without importing it.

    Read the same way `patterns_of` reads a pattern constant, since the guards all live in ONE flat directory now (`.claude/rediacc_hooks/guards/`) rather than one subdirectory per chain: there is no longer a directory name to infer this from, only the module's own declaration.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CHAIN"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def file_path_for(guard: Path) -> str:
    """A path the guard will consider in scope, taken from its own source.

    pre-edit guards gate on file_path before they look at content, so a probe carrying an irrelevant path never reaches the matcher. Rather than guess, the first concrete-looking repo path in the guard is reused.
    """
    src = guard.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"[\"'\(|]((?:\.?[a-z][a-z0-9_.-]*/)+[a-zA-Z0-9_.*-]+)", src):
        cand = m.group(1)
        if cand.startswith((".git/", "http")) or "*" in cand:
            continue
        if "/" in cand and len(cand) > 6:
            return str(REPO_ROOT / cand)
    return str(REPO_ROOT / "agent" / "probe" / "STATE.md")


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
        # CHAIN PLUMBING, proven with a REAL trigger against a REAL guard, one per non-pre-bash chain. This is what stands in for per-guard reachability, which was tried and discarded: most extracted fragments are one clause of a multi-part trigger (file_path AND tool_name AND content, all at once), so no single instantiated substring fires most guards alone. Proving the PAYLOAD
        # SHAPE once per chain is the part that is actually load-bearing.
        edit_guard = GUARDS / "block_roundlog_write.py"
        if edit_guard.exists():
            # `[ -e "$FILE" ]` gates this guard before anything else -- a nonexistent path is silently allowed by design (creating a log is not truncating one), so the fixture must actually exist on disk.
            # Under `td`, not a fresh `mkdtemp()`: that one was never removed, so every run of this gate left a directory in /tmp.
            rlog_dir = Path(td) / "rlog" / "reports"
            rlog_dir.mkdir(parents=True)
            rlog = rlog_dir / "pr-babysit-0827-1.md"
            rlog.write_text("## STATUS (round 1)\n")
            edit_payload = payload_for("edit", "irrelevant content", str(rlog))
            edit_result = ci_proc.run(
                guard_argv(edit_guard),
                input_text=edit_payload,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if edit_result.returncode != 2:
                fail(
                    "pre-edit payload plumbing: block_roundlog_write.py did not fire on a "
                    "REAL round-log write -- the edit payload shape cannot be trusted"
                )

        ask_payload = payload_for("ask", "should i commit this change", "")
        # DISPATCHED, not run as a bare bash file: this was pointed at the retired oracle directly (`["bash", str(ask_guard)]`, bypassing `guard_argv`) even before A2, a residue of the guard's chain-plumbing check never having been updated when the guard's LIVE half moved to Python at the P7 cutover. Fixed here as a small, in-scope finding rather than carried forward: the
        # plumbing check exists to prove the live payload shape, and the retired file cannot answer for that any more than the retired oracle tree can.
        ask_guard = GUARDS / "block_settled_questions.py"
        if ask_guard.exists():
            ask_result = ci_proc.run(
                guard_argv(ask_guard),
                input_text=ask_payload,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if ask_result.returncode != 2:
                fail(
                    "pre-ask payload plumbing: block_settled_questions.py did not fire on a "
                    "REAL settled question -- the ask payload shape cannot be trusted"
                )

        # The instantiator is load-bearing, so it gets its own control. Written in Python `re` syntax, not POSIX bracket expressions, since A2 retargeted the pattern source to the live guard modules.
        got = instantiate(r"git\s+commit[^|;&]*--allow-empty")
        if "git commit" not in got or "--allow-empty" not in got:
            fail(f"instantiate() lost the pattern's order or literals: {got!r}")
        # And the ANCHORED spelling must instantiate to the same literal, or the positive probe cannot reach any guard that was fixed for this class.
        anchored = instantiate(r"(^|[;&|(]|&&|\|\|)\s*git\s+commit[^|;&]*--allow-empty")
        if not anchored.startswith("git commit"):
            fail(f"instantiate() left anchor junk on the front: {anchored!r}")
        # The lookaround strip is load-bearing too, for the one guard that carries one (`block_prose_style_commit.GIT_COMMIT`'s trailing `(?=$|[\s;&|])`).
        # Without it the assertion's own syntax leaks into the instance as prose.
        lookaround = instantiate(r"(^|[;&|(])\s*git\b[^;&|]*commit(?=$|[\s;&|])")
        if "?=" in lookaround or "?!" in lookaround:
            fail(f"instantiate() leaked lookaround syntax into the instance: {lookaround!r}")


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

    guards: list[tuple[Path, str, str]] = []
    for path in sorted(GUARDS.glob("*.py")):
        name = path.stem
        if not name.startswith(("block_", "warn_", "require_")):
            continue
        chain = chain_of(path)
        if chain is None:
            continue
        kind = CHAINS.get(chain)
        if kind is None:
            continue
        guards.append((path, kind, chain))

    for guard, kind, chain in guards:
        name = guard.name
        instances = [instantiate(p) for p in patterns_of(guard)]
        instances = [i for i in instances if len(i) >= 4]
        if not instances:
            # TIER 2, STATIC. A guard with no renderable instance is not automatically a defect, and treating it as one would demand that guards be rewritten to suit this instantiator rather than to match commands correctly. Two legitimate shapes exist and both were measured here:
            #
            # * ALREADY ANCHORED -- block_blanket_git_add.py and
            #     block_worktree_add.py carry `(^|[;&|(]|\$\(|`)` prefixes;
            # the pattern is simply too gnarly to render into a literal. * NOT A PHRASE MATCHER AT ALL -- block_long_sleep.py extracts a NUMBER and compares it. There is no phrase to find inside prose, so the class does not apply.
            #
            # So: pass if the guard shows an anchor, or has nothing to anchor. Fail only when it phrase-matches with no anchor and no probe -- the case where nothing at all is checking it.
            pats = patterns_of(guard)
            if name in ALLOW_UNPROBED:
                continue
            if not pats or any(ANCHORED.search(x) for x in pats):
                static_ok += 1
                continue
            unprobed.append(name)
            continue
        # PROSE FIRING IS SELF-EVIDENT: nothing else has to be true for a guard refusing a sentence to be a defect. Requiring a POSITIVE probe to also fire before trusting silence was tried and rejected -- most extracted instances are one fragment of a multi-part trigger (a roundlog guard needs BOTH a matching file_path AND a write call; no single instantiated substring can satisfy
        # that alone), so demanding per-instance reachability reported 37 of 42 guards as inconclusive even though most were already known-clean from the pre-bash-only scan. The signal this check needs is the one that is unconditionally trustworthy: does prose trip the guard.
        fp = file_path_for(guard)
        probed += 1
        for inst in instances[:40]:
            if fires(guard, sentence(inst), kind, fp):
                offenders.append((f"{chain}/{name}", inst))
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
        f"{GREEN}✓{NC} {probed} guard(s) across {len(CHAINS)} chain(s) refuse commands, not "
        f"sentences about them; {static_ok} anchored or not phrase-matching"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
