"""The differential corpus: real commands, harvested from the real suite's recorded bytes.

WHY NOT A HAND-WRITTEN LIST. A port is judged by the inputs it was never imagined against. `.claude/hooks/test-hooks.sh` held 339 `bash_json` / `bash_bg_json` payloads, each one a command some guard was actually built or
repaired against -- heredocs that hid an amend, `sh -c` wrappers, `FOO=bar `
prefixes, quoted `/bin/bash` paths, multi-invocation `gh pr` lines. That file was the accumulated memory of every bypass this repo has paid for, so it is the corpus, and a list invented here would be a list of the cases the author of the port already had in mind. It was itself ported to pytest and deleted; its bytes are kept verbatim as a golden, and `suite_source()` below is
where that is arranged.

HOW THE PAYLOADS ARE RECOVERED. The suite writes them as shell words, so this module unquotes them the way bash would: single quotes literal, double quotes
with backslash escapes, `$'...'` ANSI-C escapes, and adjacent segments
concatenated. Two deliberate limits, both stated rather than hidden:

  * `$VAR` is NOT expanded, except when a payload is EXACTLY `$VAR` and the
    suite assigns it a constant nearby -- those twelve assignments are the
    multi-line heredoc payloads, which is precisely the material worth having.
    Everywhere else a `$VAR` stays literal, which is realistic input anyway:
    a scanner sees `$BW_TMP/x.sh` as text and must not guess what it expands
    to (a guard comment in block-bash-write-to-running-script.sh says exactly
    that about `$ver.sh`).
  * `$(...)` stays literal too, EXCEPT for `$(printf ...)`, which the suite
    uses purely to build strings carrying quotes and newlines. That one is
    emulated, without a shell, because refusing to would drop the heredoc
    cases the `<<-` finding was reported on.

Nothing here executes anything it harvests. The corpus is text handed to two implementations of a text scanner; the only requirement is that BOTH get the identical bytes, which is why every step above is deterministic.
"""

import pathlib
import re


# The repo root, found by looking for what only the root has, rather than by counting `parents[N]`. `.ci/rediacc_ci/paths.py` makes the argument at length: a depth constant still resolves after the file moves, silently, to the wrong tree. That module is not imported here on purpose -- these hooks run from `.claude/settings.json` with no pytest ini and no `pythonpath`, so a hook
# package that needs `.ci` on sys.path to find itself would be a new coupling.
def repo_root():
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude").is_dir() and (candidate / ".ci").is_dir():
            return candidate
    msg = "no repository root above %s (looked for a directory holding .claude and .ci)" % here
    raise RuntimeError(msg)


# THE SUITE IS A RECORDING NOW, not a live file, and the recipe is `frozen.py`'s: on the twin's last day in the tree its exact bytes were written to a golden under a `# twin <path> blob <sha>` header, so the corpus below is still harvested from the real tracked bytes rather than from a transcription of them. `git cat-file -p <sha>` retrieves the program those bytes came from.
#
# WHY THE HEADER IS STRIPPED RATHER THAN TOLERATED. `guardcorpus.harvest_cases` labels each recovered case with the LINE it sat on, and a header left in place would shift every one of them by one against every earlier record of the same corpus. Stripping the first line hands the parsers the original file exactly, byte for byte and line for line.
#
# `frozen.py` ITSELF IS NOT IMPORTED, for the reason the root finder states next door: this package is reachable from `.claude/settings.json` with no pytest ini and no `pythonpath`, so a hook module that needed `.ci` on sys.path to read one file would be a new coupling bought for four lines.
SUITE_GOLDEN = (
    repo_root()
    / ".ci"
    / "rediacc_ci"
    / "tests"
    / "goldens"
    / "claude-hooks"
    / "test-hooks.sh.golden"
)
SUITE_TWIN = ".claude/hooks/test-hooks.sh"
HEADER_PREFIX = "# twin "


def suite_source():
    """The retired twin's recorded bytes, with the provenance header removed.

    A MISSING OR UNHEADED GOLDEN IS LOUD. A silent fallback to empty text would hand every harvester a zero-length corpus, and the ratio floors below divide by a call-site count that would also be zero, so the differential would pass having compared nothing.
    """
    text = SUITE_GOLDEN.read_text(encoding="utf-8")
    if not text.startswith(HEADER_PREFIX):
        msg = "%s has no `%s` provenance header, so it is not a recording of %s" % (
            SUITE_GOLDEN,
            HEADER_PREFIX,
            SUITE_TWIN,
        )
        raise RuntimeError(msg)
    return text.split("\n", 1)[1]


SUITE = SUITE_GOLDEN

# The floor the harvest must clear. Corpus-derived floors are the rule (driver contract section 6), and this one is: it is a fraction of the `bash_json` call sites counted in the same pass, so adding cases to the suite raises it and a broken parser that recovers three payloads reds instead of quietly proving the port against three inputs.
HARVEST_RATIO_FLOOR = 0.9
# Below this the suite itself has been gutted and the ratio above is meaningless -- the same base-case argument `.ci/rediacc_ci/check_pytest.py` makes for MIN_TESTS.
MIN_COMMANDS = 300

_ANSI_C = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0"}


def _read_single_quoted(src, i):
    end = src.index("'", i + 1)
    return src[i + 1 : end], end + 1


def _read_ansi_c(src, i):
    # $'...' -- backslash escapes ARE processed, unlike '...'
    i += 2
    out = []
    while i < len(src) and src[i] != "'":
        if src[i] == "\\" and i + 1 < len(src):
            out.append(_ANSI_C.get(src[i + 1], "\\" + src[i + 1]))
            i += 2
            continue
        out.append(src[i])
        i += 1
    return "".join(out), i + 1


def _skip_substitution(src, i):
    """Return the index just past a balanced `$( ... )`, quotes respected."""
    depth = 0
    while i < len(src):
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c == "'":
            i = src.index("'", i + 1)
        elif c == '"':
            i += 1
            while i < len(src) and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
        i += 1
    return i


def _expand_printf(text):
    """`$(printf FMT ARG...)` without a shell, or the literal text if it is anything else. The suite uses printf only to smuggle quotes and newlines into a payload, so `%s` and the usual backslash escapes are the whole surface -- and a `%d` or a `%*s` appearing later would come out as itself rather than being silently mis-rendered."""
    inner = text[2:-1]
    words = []
    i = 0
    while i < len(inner):
        if inner[i] in " \t\n":
            i += 1
            continue
        word, i = _read_word(inner, i, stop_at_paren=False)
        words.append(word)
    if not words or words[0] != "printf":
        return text
    fmt, args = words[1], list(words[2:])
    out = []
    j = 0
    while j < len(fmt):
        if fmt[j] == "\\" and j + 1 < len(fmt):
            out.append(_ANSI_C.get(fmt[j + 1], "\\" + fmt[j + 1]))
            j += 2
            continue
        if fmt[j : j + 2] == "%s":
            out.append(args.pop(0) if args else "")
            j += 2
            continue
        if fmt[j : j + 2] == "%%":
            out.append("%")
            j += 2
            continue
        out.append(fmt[j])
        j += 1
    return "".join(out)


def _read_word(src, i, stop_at_paren=True):
    """One shell word, unquoted the way bash would unquote it."""
    out = []
    n = len(src)
    while i < n:
        c = src[i]
        if c in " \t\n":
            break
        if c == ")" and stop_at_paren:
            break
        if c == "'":
            piece, i = _read_single_quoted(src, i)
            out.append(piece)
        elif c == "$" and i + 1 < n and src[i + 1] == "'":
            piece, i = _read_ansi_c(src, i)
            out.append(piece)
        elif c == "$" and i + 1 < n and src[i + 1] == "(":
            end = _skip_substitution(src, i + 1)
            out.append(_expand_printf(src[i:end]))
            i = end
        elif c == '"':
            i += 1
            while i < n and src[i] != '"':
                if src[i] == "$" and i + 1 < n and src[i + 1] == "(":
                    end = _skip_substitution(src, i + 1)
                    out.append(_expand_printf(src[i:end]))
                    i = end
                    continue
                if src[i] == "\\" and i + 1 < n and src[i + 1] in '"\\$`':
                    out.append(src[i + 1])
                    i += 2
                    continue
                if src[i] == "\\" and i + 1 < n and src[i + 1] == "\n":
                    i += 2
                    continue
                out.append(src[i])
                i += 1
            i += 1
        elif c == "\\" and i + 1 < n:
            out.append(src[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out), i


def _assignments(src):
    """`NAME=<word>` at the start of a line, for the twelve payloads the suite
    builds once and passes by name. Only line-anchored assignments count: an
    inline `FOO=bar cmd` prefix inside a payload is DATA (it is the env-prefix
    bypass this whole file exists around) and must not be harvested as one.
    """
    found = {}
    for m in re.finditer(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)=", src):
        value, _ = _read_word(src, m.end())
        found[m.group(1)] = value
    return found


def harvest():
    """Every distinct `bash_json` / `bash_bg_json` payload in the suite.

    Returns `(commands, stats)`; `stats` carries the call-site count and the recovery ratio so the floor above can be checked against the same pass that produced the corpus.
    """
    src = suite_source()
    names = _assignments(src)
    call_sites = 0
    commands = []
    for m in re.finditer(r"\b(bash_json|bash_bg_json)[ \t]+", src):
        call_sites += 1
        word, _ = _read_word(src, m.end())
        bare = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", word)
        if bare and bare.group(1) in names:
            word = names[bare.group(1)]
        if word == "":
            continue
        # The differential streams results back framed by these two control characters, so a payload containing one would corrupt the frame rather than fail a comparison. None does today; the check is here so that a future one is dropped loudly instead of silently mis-parsed.
        if "\x1e" in word or "\x1f" in word:
            continue
        commands.append(word)
    distinct = sorted(set(commands))
    stats = {
        "call_sites": call_sites,
        "recovered": len(commands),
        "distinct": len(distinct),
        "source": str(SUITE),
    }
    return distinct, stats


# The cases the six rounds of findings in command-scan.sh's header describe, plus the empty-command contract. These are the ones most likely to diverge, because each one is a shape the bash was CHANGED to handle -- so a port that reproduced only the current code's obvious behaviour would fail here first. They are labelled, and the labels name the round, so a failure report says
# which finding regressed rather than only which string differed.
EDGE_CASES = [
    # -- rounds 39-40: the -c selector is a token, not a flag shape --------
    ("r39 bare -c", "sh -c 'gh pr merge --admin'"),
    ("r39 bundled short flags", "bash -lc 'gh pr merge 42 --admin'"),
    ("r40 separate short flags", "bash -eux -c 'gh pr merge 42 --admin'"),
    ("r40 GNU long option", "bash --posix -c 'gh pr merge 42 --admin'"),
    ("r40 value-taking short option", "bash -o pipefail -c 'gh pr merge --admin'"),
    ("r40 --norc", "bash --norc --noprofile -c 'gh pr ready 7'"),
    ("eval payload", "eval 'gh pr merge 42 --admin'"),
    ("eval with assignment", 'X=--admin; eval "gh pr merge $X"'),
    # -- round 42: the shell name is a basename ---------------------------
    ("r42 absolute path shell", "/bin/bash -c 'gh pr merge --admin'"),
    ("r42 relative path shell", "./bash -c 'gh pr merge --admin'"),
    ("r42 env bash", "env bash -c 'gh pr merge --admin'"),
    ("r42 usr bin sh", "/usr/bin/sh -c 'gh pr ready 42'"),
    # -- round 44: a quoted path's slash is inside the quotes -------------
    ("r44 quoted absolute shell", "\"/bin/bash\" -c 'gh pr merge 531 --admin'"),
    ("r44 single-quoted shell", "'/bin/bash' -c 'gh pr merge 531 --admin'"),
    ("r44 quoted relative shell", '"./bash" -c "gh pr create"'),
    # -- round 46: fields belong to one invocation ------------------------
    (
        "r46 two gh commands one line",
        "gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account",
    ),
    (
        "r46 two merges one line",
        "gh pr merge 12 --repo rediacc/console && gh pr merge 34 --repo rediacc/renet",
    ),
    ("r46 repo with equals", "gh pr merge 5 --repo=rediacc/elite"),
    ("r46 -R short form", "gh pr ready -R rediacc/homebrew-tap 9"),
    # -- the env-prefix bypass that beat seven guards ---------------------
    ("env prefix before git", "FOO=bar git commit -m x"),
    ("env prefix after semicolon", "echo hi; FOO=bar git push"),
    ("two env prefixes", "A=1 B=2 git push origin main"),
    ("env prefix inside substitution", "x=$(FOO=bar git rev-parse HEAD)"),
    ("env prefix inside backticks", "x=`FOO=bar git rev-parse HEAD`"),
    ("env prefix after pipe", "true | FOO=bar gh pr merge 1 --admin"),
    ("env prefix after open paren", "(FOO=bar gh pr ready 3)"),
    ("assignment with no command after", "FOO=bar"),
    ("assignment whose value has an equals", "FOO=a=b git status"),
    # -- heredocs: body is data, terminator shapes ------------------------
    ("heredoc body is data", "cat > R.md <<'EOF'\ngh pr merge --admin\nEOF"),
    ("heredoc unquoted marker", "cat > R.md <<EOF\ngh pr merge --admin\nEOF"),
    ("heredoc double-quoted marker", 'cat > R.md <<"EOF"\ngh pr merge --admin\nEOF'),
    (
        "<<- tab-indented terminator does not hide the next command",
        "cat <<-EOF\n\tbody\n\tEOF\ngh pr merge 1 --admin",
    ),
    (
        "plain << is not tab-stripped",
        "cat > R.md <<'EOF'\n\tgh pr merge --admin\nEOF",
    ),
    ("heredoc never terminated", "cat <<EOF\ngh pr merge --admin"),
    ("two heredocs", "cat <<A\nx\nA\ncat <<B\ngh pr merge --admin\nB\ngh pr ready 4"),
    ("heredoc marker with digits", "cat <<EOF2\ngh pr merge\nEOF2\ngh pr ready 1"),
    ("interpreter heredoc still runs", "bash <<'EOF'\ngh pr merge --admin\nEOF"),
    # -- quoting and prose ------------------------------------------------
    ("prose in a commit message", 'git commit -m "never run gh pr merge --admin"'),
    ("single-quoted prose", "echo 'gh pr merge --admin'"),
    ("unbalanced single quote", "echo 'gh pr merge --admin"),
    ("unbalanced double quote", 'echo "gh pr merge --admin'),
    ("nested quotes", "sh -c \"gh pr merge --admin 'x'\""),
    ("flag equals value", "gh pr merge 42 --admin=true"),
    ("flag in an assignment", 'X="--admin"; gh pr merge 42 $X'),
    ("flag at end of line", "gh pr merge 42 --admin"),
    ("body-file is not body", "gh pr create --draft --body-file b.md"),
    # -- cd / -C targets ---------------------------------------------------
    ("cd into a submodule", "cd private/account && gh pr merge 3"),
    ("git -C into a submodule", "git -C private/renet push"),
    ("-C with a tab", "git -C\tprivate/renet push"),
    ("cd quoted path", 'cd "/tmp" && git status'),
    ("cd relative with &&", "cd packages/cli && npm test"),
    ("two cds, last wins", "cd /tmp; cd /var; git status"),
    ("cd absolute nonexistent", "cd /nonexistent-xyz && git commit -m x"),
    # -- degenerate inputs -------------------------------------------------
    ("empty command", ""),
    ("single space", " "),
    ("only whitespace", "   \t  "),
    ("leading space before wrapper", " sh -c 'gh pr merge --admin'"),
    ("newline only", "\n"),
    ("trailing newline", "gh pr merge 1 --admin\n"),
    ("two trailing newlines", "gh pr merge 1 --admin\n\n"),
    ("blank line between commands", "echo a\n\ngh pr ready 2"),
    ("shell with no -c", "bash script.sh; sh -c 'gh pr merge --admin'"),
    ("wrapper with nothing after -c", "bash -c"),
    ("eval with nothing after", "eval"),
    ("carriage return", "gh pr merge 1 --admin\r"),
    ("tab separated", "gh\tpr\tmerge\t1\t--admin"),
    # -- Rule T (PLAN-retire-bash-oracles A4): A0's fail-open list, each a command bash RUNS that the sed/awk pipeline could not see. Every one reads pos:merge=0 now; each is followed by the prose or data twin that must stay unseen. --
    ("L1 assignment value runs its substitution", "x=$(gh pr merge 1 --admin)"),
    ("L1 assignment value runs its backticks", "x=`gh pr merge 1 --admin`"),
    ("L1 a substitution-valued prefix", "X=$(date) gh pr merge 1 --admin"),
    ("L2 a substitution inside double quotes runs", 'git commit -m "$(gh pr merge 1 --admin)"'),
    ("L2 control: double-quoted prose is not run", 'git commit -m "never gh pr merge 1 --admin"'),
    ("L3 an unquoted heredoc body expands", "cat > R.md <<EOF\n$(gh pr merge 1 --admin)\nEOF"),
    (
        "L3 control: a quoted heredoc body is data",
        "cat > R.md <<'EOF'\n$(gh pr merge 1 --admin)\nEOF",
    ),
    ("L4 a here-string into a shell runs", "bash <<< 'gh pr merge 1 --admin'"),
    ("L4 a heredoc piped into a shell runs", "cat <<'EOF' | sh\ngh pr merge 1 --admin\nEOF"),
    (
        "L4 control: a heredoc into python is not shell",
        "python3 - <<'EOF'\ngh pr merge 1 --admin\nEOF",
    ),
    ("L5 a here-string has no body", "cat <<<x\ngh pr merge 1 --admin"),
    ("L5 a quoted marker is not a heredoc", 'echo "<<EOF"\ngh pr merge 1 --admin'),
    ("L5 a commented marker is not a heredoc", "true # <<EOF\ngh pr merge 1 --admin"),
    ("L6 an apostrophe inside double quotes", "echo \"it's\"; gh pr merge 1 --admin; echo 'y'"),
    ("L6 an escaped double quote", 'echo "p \\" q"; gh pr merge 1 --admin; echo "r"'),
    ("L7 a quoted command word", '"gh" pr merge 1 --admin'),
    ("L7 a partly quoted command word", 'g"h" pr merge 1 --admin'),
    ("L7 an escaped command word", "\\gh pr merge 1 --admin"),
    ("L7 an ANSI-C quoted command word", "$'gh' pr merge 1 --admin"),
    ("L8 a backslash-newline joins the command", "gh pr \\\nmerge 1 --admin"),
    ("L9 a brace group", "{ gh pr merge 1 --admin; }"),
    ("L9 a negation", "! gh pr merge 1 --admin"),
    (
        "L9 then and do",
        "if true; then gh pr merge 1 --admin; fi; while false; do gh pr ready 2; done",
    ),
    ("L9 time and command", "time gh pr merge 1 --admin; command gh pr ready 2"),
    ("L9 a leading redirect", ">/dev/null gh pr merge 1 --admin"),
    ("L9 a leading descriptor redirect", "2>&1 gh pr merge 1 --admin"),
    ("L9 control: command -v only prints", "command -v gh pr merge"),
    ("L10 c inside a bundle", "bash -ce 'gh pr merge 1 --admin'"),
    ("L10 options after -c", "bash -c -e 'gh pr merge 1 --admin'"),
    ("L10 a quoted -c", "bash '-c' 'gh pr merge 1 --admin'"),
    ("L11 an eval word as an argument", "echo eval && sh -c 'gh pr merge 1 --admin'"),
    ("L11 two wrappers on one line", "sh -c true; sh -c 'gh pr merge 1 --admin'"),
    ("L12 a subshell cd does not persist", "(cd private/renet && git fetch); git status"),
    ("L12 a pipeline cd does not persist", "cd private/renet | true; git status"),
    ("L12 a -C names one git command", "git -C private/renet fetch; git status"),
    ("L12 a gh after a -C is not in the submodule", "git -C private/renet fetch; gh pr merge 3"),
    ("S1 a space-indented marker does not close", "cat <<EOF\n  EOF\ngh pr merge 1 --admin\nEOF"),
    ("S2 a marker with a dash is the whole word", "cat <<END-X\nEND\ngh pr merge 1 --admin\nEND-X"),
]


# TWO CASES THAT MUST BE BUILT, NOT WRITTEN DOWN, and the reason is an anti-vacuity one rather than a convenience. `hook_target_root` only returns a non-empty answer when a hint resolves to a git worktree that is NOT the root it was handed, and no payload in the suite carries an absolute `cd` into a real checkout. Measured over the whole corpus before these were added: the field
# comparing `target_root` against a deliberately absent root took exactly ONE value, the empty string, on every one of 385 cases -- a comparison that could not have failed. These two give it something to disagree about.
def _absolute_cd_cases():
    root = repo_root()
    cases = [("absolute cd into this checkout", "cd %s && git status" % root)]
    submodule = root / "private" / "renet"
    if (submodule / ".git").exists():
        cases.append(("absolute cd into a submodule", "cd %s && git log -1" % submodule))
    return cases


EDGE_CASES.extend(_absolute_cd_cases())

# `hook_init` payloads. The interesting half is not the happy path: `jq -r` prints the four characters `null` for an absent key, so three of these produce a scan of the literal string "null" rather than the early return a reader expects. See shellscan.hook_init's comment.
JSON_PAYLOADS = [
    ("plain command", '{"tool_input":{"command":"gh pr merge 1 --admin"}}'),
    ("empty command", '{"tool_input":{"command":""}}'),
    ("missing command key", '{"tool_input":{}}'),
    ("missing tool_input", "{}"),
    ("null command", '{"tool_input":{"command":null}}'),
    ("null tool_input", '{"tool_input":null}'),
    ("malformed json", "{not json"),
    ("empty input", ""),
    ("top-level null", "null"),
    ("top-level number", "42"),
    ("numeric command", '{"tool_input":{"command":42}}'),
    ("boolean command", '{"tool_input":{"command":true}}'),
    ("multi-line command", '{"tool_input":{"command":"echo a\\ngh pr ready 2"}}'),
    ("command with trailing newline", '{"tool_input":{"command":"gh pr ready 2\\n"}}'),
    ("background flag", '{"tool_input":{"command":"sleep 600","run_in_background":true}}'),
]
