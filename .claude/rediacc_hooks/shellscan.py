#!/usr/bin/env python3
"""Shared command scanning for the gh-pr guardrail hooks (block-admin-merge, block-nondraft-pr-create, block-premature-ready).

The old inline approach (strip every quoted span, then anchor `gh pr <verb>` at a command position) had a review-found bypass class: stripping ALL quotes also erases a command hidden inside a shell-execution wrapper, so `sh -c 'gh pr merge --admin'`, `bash -c "..."`, `eval "..."`, variable
indirection (`X=--admin; gh pr merge $X`), and `--admin=true` all sailed past
the bans. The stripping exists to avoid PROSE false positives (`git commit -m "...gh pr merge --admin..."`), so it cannot simply be removed. This lib keeps the prose defense AND scans wrapper payloads.

scan_target builds the string the anchor runs against, from three parts:
  1. Heredoc bodies removed. A `<<MARKER ... MARKER` body is DATA, never
     executed, so dropping it is safe and kills the heredoc false positive
     (a worklist note mentioning the command used to fire the hook).
  2. Prose-stripped: quoted spans removed (multi-line aware) so quoted prose
     cannot trip the anchor.
  3. Wrapper payloads: the argument of a shell-execution wrapper
     (sh/bash/dash/zsh/ash/ksh -c, or eval) with its quotes turned to spaces,
     so the inner command lands at a command position and IS scanned.

flag_present matches a long flag in every form a shell accepts:
`--flag`, `--flag=value`, `--flag;`, and inside a quoted/assignment token,
so `--admin=true` and `X="--admin"` are caught. Combined with a
command-position verb match, over-blocking a command that both names the flag and runs the verb is the safe direction.

=============================================================================
THIS FILE IS A TRANSLITERATION, NOT A REWRITE
=============================================================================

The original is `.claude/hooks/pre-bash/lib/command-scan.sh`, and its comments record SIX separate rounds of bypass findings (rounds 39-40 flag shapes, 42 path-qualified shells, 44 quoted paths, 46 line-wide field scope, the
`FOO=bar ` env-prefix bypass of seven guards, and the `<<-` tab-indented
terminator). Those rounds are the specification: each one names a command that slipped past an earlier version, and none of them is visible in the behaviour of the current code alone. So every function below is ported line for line,
with its comment carried across in the same position relative to the code it
explains, and `tests/test_shellscan_differential.py` feeds the same corpus to both implementations and refuses any divergence.

ONE FUNCTION IN THE ORIGINAL IS DELIBERATELY NOT PORTED: `hook_read_payload`, added 2026-09-08. It reads the hook event body from stdin under a deadline, because `$(cat)` and a bare `jq` reading stdin bound nothing -- a stdin that stays open and silent blocks them forever, and in a PreToolUse hook that is not a slow check, it is a tool call that never returns.
`.claude/hooks/chain-head.sh` carries the measurement that settled it: with the interpreter hidden from PATH so the arm is actually reached and stdin held open by a writer that never writes, the unbounded form exits 124 under an external timeout against exit 2 in 0s once stdin is closed.

It has no Python counterpart and should not get one. This module is a SCANNER: callers hand it a command string they already read. Reading stdin is the caller's job, and the four bash entry points that do it (`hook_init` in the original, `block-pathspecless-git-commit.sh`, `cancel-old-ci.sh`, `refresh-pr-body.sh`) have Python siblings that receive their payload through
`rediacc_hooks.hookio` instead, which never had the unbounded form. The note lives here rather than nowhere because the differential above checks that the port keeps the original's dated evidence, and evidence for a function that is absent by design still has to be answerable.

WHERE THE PYTHON LOOKS UNIDIOMATIC, IT IS ON PURPOSE. Four bash behaviours have no natural Python spelling and are reproduced by hand rather than improved away:

  * `$(...)` strips EVERY trailing newline from a command's output, so a
    filter's raw stdout and the value a caller sees are different strings.
    `_command_substitution` is that difference, spelled out, because the
    original's `nohd`/`stripped`/`wrapped` locals all pass through it.
  * awk, sed and grep read RECORDS, not a string. A trailing newline is a
    terminator, not a separator, and an empty input has ZERO records rather
    than one empty one. `_records` is that rule; every filter below rebuilds
    its output the way its tool does (awk always terminates a record it
    prints, GNU sed preserves a missing final newline, grep always adds one).
  * POSIX EREs are leftmost-LONGEST; Python's `re` is leftmost-first with
    backtracking. For the patterns here the two agree, and that agreement is
    an empirical claim the differential checks rather than an assumption:
    every alternation below is either mutually exclusive on its first
    character or falls through to the same branch under backtracking.
  * awk arrays are 1-based and `split` on a REGEX separator does not trim, so
    a leading space yields an empty first field. The loops below keep the
    original's index arithmetic (`j < n` meaning "not the last field") rather
    than switching to Python's slicing, because the join it controls is where
    the wrapper payload's spacing comes from.

NAMES. The bash `hook_` prefix existed because bash has one namespace. Here the module supplies it: `hook_scan_target` is `shellscan.scan_target`, `_hook_wrapper_payload` is `shellscan._wrapper_payload`, and so on. The differential maps them pair by pair, so the mapping is checked and not merely asserted here.
"""

import ast
import glob
import itertools
import json
import os
import posixpath
import re
import subprocess
import typing

from rediacc_hooks.wellknown import GH_REPO

# `[[:space:]]` in the C locale, written out. Python's `\s` is Unicode-aware (it matches U+00A0 and friends), which would widen every anchor in this file against a command containing non-breaking space -- a silent behaviour change in the direction of matching MORE, which for a guard is the safe direction but is still not what the bash does.
SPACE = r" \t\n\v\f\r"
# The same class with the newline dropped, for the places where the tool works on one record at a time and a newline can therefore never be in the subject. Kept separate rather than reused so that a future edit to one is not silently a change to the other.
BLANK = r" \t\v\f\r"

SHELL_NAMES = ("sh", "bash", "dash", "zsh", "ash", "ksh")


def _records(text):
    """Split text the way awk, sed and grep read records.

    Returns `(records, terminated)`. `terminated` says whether the input's last record carried its newline, which is what GNU sed reproduces and awk does not. The empty string is ZERO records: `printf '%s' ""` gives a tool no input at all, so its main block never runs -- which is why an empty command produces an empty wrapper payload rather than an empty line.
    """
    if text == "":
        return [], False
    if text.endswith("\n"):
        return text[:-1].split("\n"), True
    return text.split("\n"), False


def _awk_out(records):
    """awk's `print` terminates every record it emits, input newline or not."""
    return "".join(record + "\n" for record in records)


def _sed_out(records, terminated):
    """GNU sed preserves a missing final newline instead of adding one."""
    if not records:
        return ""
    return "\n".join(records) + ("\n" if terminated else "")


def _grep_out(matches):
    """grep terminates every line it prints, including the last."""
    return "".join(match + "\n" for match in matches)


def _command_substitution(text):
    """`$(cmd)` strips EVERY trailing newline, not one."""
    return text.rstrip("\n")


def _here_string(text):
    """`<<<"$x"` feeds `x` plus one newline, so an empty subject is one empty record and not zero records. grep is then run over exactly one line."""
    return text + "\n"


def _tr(text, frm, to):
    """`tr` with two single characters: a 1:1 byte map, nothing else."""
    return text.replace(frm, to)


# Extract the payload of a shell-wrapper invocation (`<shell> [...anything...] -c <payload>` or `eval <payload>`) by SCANNING TOKENS for the token that actually selects -c mode, instead of enumerating flag shapes in a regex. Review findings (rounds 39-40) showed that a single regex chasing flag shapes is a losing game: bare `-c`, then bundled (`-lc`) and separate (`-eux -c`) short
# flags, then GNU long options (`--posix`, `--norc`) and value-taking short options (`-o pipefail`) each broke it in turn, and there will always be another shape. Token-scanning treats ANY intervening token as skippable and asks only "is THIS token the -c selector" -- a closed, enumerable question (`-c` exactly, or a single-dash bundle ending in `c`) -- so no flag syntax needs to
# be recognized at all. This also drops the old design's second failure mode: the extraction regex and a separate prefix-strip regex had to independently agree on the exact same shape, and small drift between the two was itself a bug source; this emits the payload directly, so there is nothing left to keep in sync.
#
# Round-42 review finding: the shell-name test required an EXACT, bare token match, so a path-qualified shell (`/bin/bash -c`, `./bash -c`) never matched -- the same enumeration trap the flag side already escaped, just moved to the shell-name side. Fixed the same way: match the BASENAME of the token (strip any leading `.*/`) rather than adding literal path prefixes as more
# alternatives. `env bash -c` was already fine (`env` isn't a shell name, so the scan naturally advances to the next bare `bash` token) -- only direct path-qualification broke it.
#
# Round-44 review finding: the basename strip alone left a QUOTED path broken -- `"/bin/bash"` has its last `/` INSIDE the quotes, so the greedy path-strip left `bash"` (trailing quote intact), which still failed the exact-match test. Fixed by also stripping quote characters from the name copy (either order works: quotes and the basename separator never overlap).
#
# A WRAPPER IS A COMMAND BASH RUNS, NOT A WORD THAT SPELLS ONE (#31ed6c5f). The token scan above splits on blanks, so it read `"sh` -- the opening of a quoted ARGUMENT, `echo "sh -c 'rm x'" "x .claude/settings.json | y"` -- as a shell, and handed every later token of the line to the scan as code: block_protected_files refused that echo (rc 2, 2026-10-09), and the session's own
# `worklist.py --add` quoting it. So a token is a wrapper only when it is the NAME of a command the walk found (`_Analysis.names`: a top-level or substituted command, or one a launcher there starts), and its payload stops where that command's words stop, so a later clause's prose is not lifted with it. A shell word with no `-c` among its own words falls through to the next candidate, as it always did. Every command a payload runs is still lifted by `lifted_commands`, which reads the command itself rather than this line.
def _wrapper_payload(text):
    records, _ = _records(text)
    for record in records:
        # awk: n = split($0, tok, /[ \t]+/). A REGEX separator, so unlike the
        # default " " separator it does NOT trim: a leading blank yields an empty tok[1], and that empty token is why the join below can emit a leading space. Python's re.split on "" would give one empty field where awk gives zero, hence the guard.
        tok = re.split(r"[ \t]+", record) if record != "" else []
        n = len(tok)
        names = _command_names(record, tok)
        for i in range(n):
            last = names.get(i)
            if last is None:
                continue
            if tok[i] == "eval":
                out = "".join(tok[j] + (" " if j < n - 1 else "") for j in range(i + 1, last + 1))
                # awk `print` then `exit`: one record, ORS appended, and the whole input abandoned -- later records are never read.
                return out + "\n"
            name = tok[i]
            name = re.sub(r"[\"']", "", name)
            # awk's sub(/.*\//) is greedy and leftmost-longest, so this strips through the LAST slash. Python's greedy `.*` lands in the same
            # place; count=1 keeps it a `sub` and not a `gsub`.
            name = re.sub(r".*/", "", name, count=1)
            if re.search(r"^(sh|bash|dash|zsh|ash|ksh)$", name):
                for j in range(i + 1, last + 1):
                    t = tok[j]
                    if t == "-c" or re.search(r"^-[^-].*c$", t):
                        out = "".join(
                            tok[m] + (" " if m < n - 1 else "") for m in range(j + 1, last + 1)
                        )
                        return out + "\n"
                # NO `exit` HERE, and that is load-bearing: a shell name whose token run carries no -c selector falls back to the OUTER loop, so `bash script.sh; sh -c 'gh pr merge'` still finds the second one.
    return ""


def _command_names(record, tok):
    """`{token index: index of the command's last token}` for every token of `record` that is, whole, the name of a command the walk of `record` found (`_Analysis.names`). A token that only begins a word (`"sh` of `"sh -c 'x'"`) is not one."""
    spans = []
    at = 0
    for word in tok:
        spans.append((at, at + len(word)))
        gap = _BLANKS.match(record, at + len(word))
        at = gap.end() if gap else at + len(word)
    first = {span: k for k, span in enumerate(spans)}
    out = {}
    for start, end, words_end in _analyse(record).names:
        k = first.get((start, end))
        if k is None:
            continue
        # The payload runs through the token holding the command's last word.
        out[k] = next((j for j in range(k, len(spans)) if spans[j][1] >= words_end), len(spans) - 1)
    return out


_BLANKS = re.compile(r"[ \t]+")


# Drop heredoc bodies: from a line introducing `<< [-] ['"]?MARKER['"]?` up to the line that is exactly MARKER (optionally tab-indented for <<-). Keeps the introducing line (which may itself hold the real command) and the rest.
#
# RULE T (PLAN-retire-bash-oracles A4, A0 L5 and S1/S2): THE HEREDOCS ARE NOW FOUND BY `_Lexer`, NOT BY A REGEX OVER EACH LINE. The regex `<<-?[ \t]*['"]?[A-Za-z_][A-Za-z0-9_]*['"]?` fired on three things that are not heredocs, and each one swallowed every later line as "body", so a real command after it was never scanned: a here-string `<<<x`, a `"<<EOF"` inside quotes, and a `# <<EOF` in a comment. Bash runs the lines after all three. The same regex also closed the body on `^[ \t]*M[ \t]*$`, which bash does not do for a plain `<<` (no indentation stripping at all) or for a trailing blank, and stopped the marker at a `-` (`<<END-X` closed at a line reading `END`); those two only ever over-scanned, the safe direction, and are corrected with the rest because the lexer reads the terminator the way bash does. The output format is the awk's: every kept record, newline-terminated.
def _strip_heredocs(text):
    records, _ = _records(text)
    if not records:
        return ""
    lexer = _Lexer(text)
    lexer.tokens()
    spans = sorted(
        (hd.body_start, hd.term_end) for hd in lexer.heredocs if hd.body_start is not None
    )
    kept = []
    last = 0
    for start, end in spans:
        if start < last:
            continue
        kept.append(text[last:start])
        last = end
    kept.append(text[last:])
    out, _ = _records("".join(kept))
    return _awk_out(out)


# Remove inline environment assignments sitting between a command position and the
# command itself: `FOO=bar git <verb>` becomes ` git <verb>`.
#
# WITHOUT THIS, ONE TOKEN BYPASSED SEVEN GUARDS. Every git guard here anchors its match at a command position, because prose about committing must not be treated as a commit. An assignment prefix puts a word between the anchor and `git`, so the anchor stops matching and the guard exits 0 having decided this is not a git
# command at all. Measured 2026-09-03, plain versus `FOO=bar `-prefixed, on the
# identical command -- every one of these went from refusing to permitting:
#
#   block-unverified-push          rc=2 -> rc=0
#   block-untagged-commit          rc=2 -> rc=0
#   block-destructive-git-restore  rc=2 -> rc=0
#   block-blanket-git-add          rc=2 -> rc=0
#   block-worktree-add             rc=2 -> rc=0
#
# The fix belongs HERE rather than in seven regexes: an assignment prefix is a property of shell syntax, which is what this file normalises, and a seventh copy of the anchor would have been a seventh chance to miss it. The assignments are dropped rather than kept because no guard matches on them; the one guard that needs their VALUES reads them from the RAW command for exactly that
# reason.
#
# RULE T (A0 L1): THE VALUE MAY NOT SWALLOW A SUBSTITUTION. The class used to be "anything but a blank or a separator", so in `x=$(git push --force origin main)` it ate `$(git ` as the value of `x`, the strip left ` push --force origin main)`, and the push was gone from the scan: `block_git_force_push` refused `git push --force origin main` (rc 2) and allowed the same push inside the assignment (rc 0), measured 2026-09-24. Bash runs the substitution. So a `$(` or a backtick ends the value: the assignment is then not stripped, the substitution stays where the `$(` anchor sees it, and a command behind a substitution-valued prefix (`X=$(date) git push`) is lifted by `lifted_commands` instead.
_ENV_PREFIX = re.compile(
    r"(^|[;&|(]|\$\(|`)(["
    + BLANK
    + r"]*)([A-Za-z_][A-Za-z0-9_]*=(?:[^"
    + BLANK
    + r";&|$`]|\$(?!\())*["
    + BLANK
    + r"]+)"
)


def _strip_env_prefix(text):
    records, terminated = _records(text)
    out = []
    for record in records:
        # The bash is `sed -E ':a; s/.../\1\2/g; ta'`, a label-and-branch loop. It exists because `^` matches only at the true start of the pattern
        # space even under `/g`, so `A=1 B=2 git` needs a SECOND pass before
        # `B=2 ` is at the start and can match. Python's `re.sub` without
        # MULTILINE has the identical `^` rule, so the loop ports one-for-one. It terminates because every substitution deletes a non-empty group 3.
        line = record
        while True:
            line, count = _ENV_PREFIX.subn(r"\1\2", line)
            if count == 0:
                break
        out.append(line)
    return _sed_out(out, terminated)


# The preamble every command guard repeats: read the command out of the hook event, bail when there is nothing to judge, and compute the normalised scan target.
#
# Extracted after check:ci-shape-duplication counted three identical copies (block-untagged-commit, block-unverified-push, block-unlinked-commit-author). The `source` line above cannot be extracted -- something has to load this file -- but everything after it can, and centralising it matters more here than the line count
# suggests: `scan_target` is where the `FOO=bar ` prefix bypass was fixed, and
# a guard that hand-rolls its own preamble is a guard that can drift away from that fix without anything noticing.
#
# Returns (CMD, SCAN), or None when there is no command -- the caller's whole preamble in bash was `hook_init || exit 0`, and here it is
# `state = hook_init(payload)` followed by `if state is None: return`.
#
# THE EMPTY-COMMAND CONTRACT IS NOT WHAT IT LOOKS LIKE. `jq -r` prints the four characters `null` for a key that is absent or JSON null, so a payload
# with no `.tool_input.command` yields the STRING "null", passes the `-z` test
# and is scanned as if someone had typed `null`. Only a jq FAILURE (malformed JSON, so nothing on stdout) or a genuinely empty string command returns 1. That asymmetry is behaviour 25 guards depend on, so it is preserved rather than tidied into `None`; the differential pins all four shapes.
def hook_init(payload):
    cmd = _jq_raw_command(payload)
    if cmd == "":
        return None
    scan = _command_substitution(scan_target(cmd))
    return cmd, scan


def _jq_raw_command(payload):
    """`CMD=$(jq -r '.tool_input.command' 2>/dev/null)`, without the fork.

    jq's contract, in the shapes a hook event can actually take:
      * unparseable input          -> jq exits non-zero, stdout empty  -> ""
      * `.tool_input` missing/null -> `null` printed by `-r`           -> "null"
      * command missing/null       -> `null`                           -> "null"
      * command is a string        -> the string, raw (no JSON quoting)
      * command is a non-string    -> its compact JSON form
    The trailing newline jq writes is removed by the command substitution, and so is any newline the command itself ends with.
    """
    try:
        doc = json.loads(payload)
    except (ValueError, TypeError):
        return ""
    if isinstance(doc, dict):
        inner = doc.get("tool_input")
    elif doc is None:
        # `null | .tool_input` is null in jq, not an error.
        inner = None
    else:
        # jq refuses to index a number, string or array with a key name and exits 5 with nothing on stdout.
        return ""
    if isinstance(inner, dict):
        value = inner.get("command")
    elif inner is None:
        value = None
    else:
        return ""
    if value is None:
        return _command_substitution("null\n")
    if isinstance(value, str):
        return _command_substitution(value + "\n")
    return _command_substitution(json.dumps(value, separators=(",", ":")) + "\n")


def scan_target(cmd):
    nohd = _command_substitution(_strip_heredocs(cmd))
    stripped = _command_substitution(
        _strip_env_prefix(
            _tr(
                _sed_strip_quoted_spans(_tr(nohd, "\n", "\001")),
                "\001",
                "\n",
            )
        )
    )
    # Extract the wrapper payload (see _wrapper_payload above), then turn its quotes to spaces so the inner command lands at a command position: `sh -c 'gh pr merge --admin'` -> `gh pr merge --admin `.
    wrapped = _command_substitution(
        _strip_env_prefix(_sed_quotes_to_spaces(_wrapper_payload(_tr(nohd, "\n", " "))))
    )
    view = "%s\n%s" % (stripped, wrapped)
    # RULE T (A0 L1-L11): every command bash runs that the two lines above do not show at a command position, one canonical line each (see `lifted_commands`). Appended only when there is one, so a command the old pipeline already read correctly keeps its byte-identical scan target.
    lifted = lifted_commands(cmd, view)
    if lifted:
        view = "%s\n%s" % (view, "\n".join(lifted))
    return view


def _sed_strip_quoted_spans(text):
    """`sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g'`, in that order.

    The order is not cosmetic: single-quoted spans go first, so a double quote living inside a single-quoted span is gone before the second expression can pair it with an unrelated quote later in the line. The caller has already mapped newlines to \\001, so "multi-line aware" means the whole command is ONE record here and a quoted span may cross what were lines.
    """
    records, terminated = _records(text)
    return _sed_out([_strip_quoted_left_to_right(record) for record in records], terminated)


def _strip_quoted_left_to_right(line):
    """Every quoted span removed in ONE left-to-right pass, the way bash reads quotes.

    Two passes (every '...' first, then every "...") pair the wrong quotes on the POSIX idiom for a literal apostrophe, `'it'"'"'s x; tool y'`: the first pass eats `'it'` and `'"'`, the second finds `"'s x; tool y'` unterminated, and `tool` surfaced at a command position. block_host_toolchain_run refused a commit whose message merely NAMED a missing tool that way (2026-09-27, #ecf56658). Here a single quote opens a span that only a single quote closes; a double quote opens one that only an unescaped double quote closes (a backslash escapes inside it, as in bash). An unterminated span keeps the rest of the line, exactly as the two-pass form did.
    """
    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "'":
            end = line.find("'", i + 1)
            if end < 0:
                out.append(line[i:])
                break
            i = end + 1
            continue
        if ch == '"':
            j = i + 1
            while j < n and line[j] != '"':
                j += 2 if line[j] == "\\" else 1
            if j >= n:
                out.append(line[i:])
                break
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _sed_quotes_to_spaces(text):
    """`sed -e "s/['\\"]/ /g"` -- every quote character becomes a space."""
    records, terminated = _records(text)
    return _sed_out([re.sub(r"['\"]", " ", record) for record in records], terminated)


# gh_pr_at_command_pos <scan-target> <verb>
# Command position = line start (covers wrapper-payload lines, now
# prefix-stripped), or after ; & | ( $( or a backtick.
def gh_pr_at_command_pos(scan, verb):
    # `verb` is interpolated into the ERE by the original, so it is a PATTERN and not a literal. Every caller passes a bare word (create, merge, ready, edit); re.escape here would be an improvement that changes what is matched, which is the one thing this port may not do.
    pattern = re.compile(
        r"(^|[;&|(]|\$\(|`)["
        + SPACE
        + r"]*gh["
        + SPACE
        + r"]+pr["
        + SPACE
        + r"]+"
        + verb
        + r"(["
        + SPACE
        + r"]|$)"
    )
    records, _ = _records(_here_string(scan))
    return any(pattern.search(record) for record in records)


# flag_present <raw-cmd> <flag-without-dashes>
def flag_present(cmd, flag):
    pattern = re.compile("--" + flag + r"([" + SPACE + r"=;&|)\"'`]|$)")
    records, _ = _records(_here_string(cmd))
    return any(pattern.search(record) for record in records)


# gh_pr_segment <scan-target> <verb> Print ONLY the command segment that actually invokes `gh pr <verb>`, so per-invocation fields (--repo, -R, the PR selector) are read from ONE invocation instead of from the whole bash line.
#
# Round-46 finding, hit live during a real merge: every field was parsed from the entire line, so when several gh commands shared it the repo of one was paired with the PR number of another --
#   gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account
# resolved as rediacc/renet#66 (a long-merged, unrelated PR) and blocked the merge on THAT PR's unresolved thread. Same class as the wrapper/flag/path findings the rest of this file records: a field read at the wrong scope. Splitting on command separators fixes the scope rather than special-casing the observed pairing. Prints EVERY such segment, one per line, so a caller checks
# each invocation on its own. The old line-wide parsing also silently checked only ONE of several same-verb invocations (the greedy selector regex took the last PR number, the repo grep took the first repo), so a second `gh pr merge` on the line went entirely unexamined; looping closes that too.
def gh_pr_segment(scan, verb):
    # `sed -e 's/[;&|()`]/\n/g'`: the separator is REPLACED by a newline, not split on, so the separator character itself never reaches the anchor.
    records, terminated = _records(scan)
    split = _sed_out([re.sub(r"[;&|()`]", "\n", record) for record in records], terminated)
    pattern = re.compile(
        r"^[" + SPACE + r"]*gh[" + SPACE + r"]+pr[" + SPACE + r"]+" + verb + r"([" + SPACE + r"]|$)"
    )
    grep_records, _ = _records(split)
    segs = _command_substitution(_grep_out([r for r in grep_records if pattern.search(r)]))
    # Fail closed: if the split finds nothing (a shape not anticipated here) hand back the WHOLE scan, i.e. the old behavior, never an empty scope that would silently resolve to defaults and skip the real check.
    return segs if segs != "" else scan


# A guard that has the walked call asks `gh_run_repo` (below) instead: this reads `--repo`/`-R` from quote-stripped TEXT, so `-R=x`, `-Rx` and `--repo 'x'` are invisible to it. It stays as the fallback for a command whose walk finds no `gh pr <verb>` call.
# target_repo <segment> <whole-scan> <cwd> Resolve the rediacc repo a `gh pr` invocation targets, in order: 1. --repo/-R in the SAME segment as the verb 2. a `cd`/`git -C` into private/<submodule> anywhere on the line (a cd applies to every later segment, so this one is deliberately line-wide) 3. the session cwd's origin remote 4. rediacc/console
#
# RULE T (A0 L12): "ANYWHERE ON THE LINE" WAS WRONG IN BOTH DIRECTIONS. A `cd` persists only in the shell that ran it: one inside `( ... )`, inside a pipeline stage, inside a `$(...)` or in a background job is gone by the next command, and a `git -C` names the directory of that ONE git command and no other. The line-wide grep read `git -C private/renet fetch; gh pr merge 3` as a renet merge and `gh pr merge 3 && cd private/renet` likewise. Step 2 now asks `_analyse` which directory THIS gh invocation actually runs in; only a line with no gh invocation the walk can find keeps the line-wide grep, since there is then no invocation to scope to.
def target_repo(seg, scan, cwd):
    repo = _command_substitution(
        _grep_out(
            [
                re.sub(r"^(--repo[= ]|-R )", "", m, count=1)
                for m in _grep_only(r"(--repo[= ]|-R )[A-Za-z0-9_./-]+", seg + "\n")[:1]
            ]
        )
    )
    if repo == "":
        sm = _gh_submodule(seg, scan)
        if sm is None:
            submodules = r"private/(renet|account|elite|homebrew-tap)"
            first = _grep_only(r"(cd |-C )[^;|&]*" + submodules, scan + "\n")
            second = _grep_only(submodules, _grep_out(first))
            sm = _command_substitution(_grep_out(second[:1]))
        if sm != "":
            # `${sm#private/}` removes the SHORTEST matching prefix, once.
            # `str.removeprefix` is exactly `${sm#private/}`: shortest prefix,
            # once, and a no-op when it is absent.
            repo = "rediacc/" + sm.removeprefix("private/")
    return repo if repo != "" else _origin_repo(cwd)


def _line_spans(text):
    """`(start, end)` of every line of `text`, newline excluded: the unit `_cut_through_last` reads, and what its work-count test counts."""
    start = 0
    while True:
        nl = text.find("\n", start)
        if nl < 0:
            yield start, len(text)
            return
        yield start, nl
        start = nl + 1


def _cut_through_last(record, needle):
    """`(text, 1)` with the first line holding `needle` cut from its start through the LAST `needle` on it and every blank after that, else `(record, 0)`.

    Exactly `re.subn(".*" + needle + "[" + SPACE + "]*", "", record, count=1)` (`.` stops at a newline, the blanks do not), read once per line. The regex tried every start position and backtracked from each to the line's end, so a long line naming no `gh pr` was quadratic: 36 s for a 200,000-character segment (measured 2026-10-11).
    """
    for start, end in _line_spans(record):
        at = record.rfind(needle, start, end)
        if at >= 0:
            # `SPACE` is regex class text (`\t` spelled as two characters), so the blanks are read by the class itself; an anchored match is linear.
            stop = at + len(needle)
            blanks = re.compile("[" + SPACE + "]*").match(record, stop)
            if blanks is not None:
                stop = blanks.end()
            return record[:start] + record[stop:], 1
    return record, 0


# pr_selector <segment> <verb> The PR selector (number/url/branch) belongs to the same invocation as the verb -- read it from the segment, never from the line.
def pr_selector(seg, verb):
    # `sed -n "s/.*gh pr ${verb}[[:space:]]*//p"`: `.*` is greedy, so on a
    # segment naming the verb twice this cuts at the LAST one, and `-n ... p` means non-matching lines are dropped rather than passed through. `_cut_through_last` is that substitution, read in one pass per line.
    records, _ = _records(_printf_line(seg))
    kept = []
    for record in records:
        new, count = _cut_through_last(record, "gh pr " + verb)
        if count:
            kept.append(new)
    for record in _records(_sed_out(kept, terminated=True))[0]:
        # awk's default FS is space/tab/newline with leading and trailing runs discarded -- NOT Python's str.split(), which also splits on \r and on Unicode separators and would therefore field a `\r` differently.
        fields = [f for f in re.split(r"[ \t]+", record.strip(" \t")) if f != ""]
        for field in fields:
            if not re.search(r"^-", field):
                # awk `print` then `exit`: the FIRST such field on the FIRST line that has one, and no further lines are read.
                return field + "\n"
    return ""


# target_root <whole-scan> <this-root> The FILESYSTEM git root a command operates on, or "" when it is this one.
#
# DIFFERENT QUESTION FROM target_repo ABOVE, which resolves a GitHub repo NAME for a `gh pr` invocation. This resolves a working tree, for guards that read local git state -- a branch name, a HEAD sha, a gate-run stamp. Those guards are only correct when the tree they inspect is the tree the command touches.
#
# THIRD COPY, SO IT MOVED HERE. block-untagged-commit.sh:52-69 hand-rolled this and its comment records why: without it, `git -C <other-repo> commit` was "judged against CLAUDE_PROJECT_DIR/agent/pr/<console-branch>.md: wrong branch name, wrong epic snapshot, so every such commit was refused for a trailer no epic file could ever supply."
#
# Measured 2026-09-01, the same defect was live in a sibling: `git -C <scratch> push` was refused by block-unverified-push.sh because it compared the SCRATCH repo's push to the CONSOLE tree's gate-run stamp (reproduced: exit 2). warn-remote-drift.sh has the identical shape and is latent -- quiet today only because console's remote happens not to be ahead.
#
# A `cd` applies to every later segment of the SAME shell; until the Rule T fix in the docstring below this scan was line-wide, matching target_repo's convention, and that is exactly what A0 L12 measured failing. Prints "" when the command targets THIS root, when no hint is present, or when the hint does not resolve to a git repo -- so a caller can treat empty as "this repo, proceed" and never has to distinguish absent from same.
def target_root(scan, this_root, verb=None):
    """Rule T (A0 L12, and the tab defect PLAN-retire-bash-oracles A4 names at block_untagged_commit.py:142).

    The line-wide grep this replaces took the LAST `cd`/`-C` hint anywhere, so `(cd private/renet && git fetch); git status`, `cd private/renet | true; git status` and `git -C private/renet fetch; git status` all resolved to renet while bash ran `git status` in THIS tree, and a guard that stands down for another repo then stood down for a command in this one. Its `-C` strip also demanded a literal space, so `git -C<TAB>private/renet` resolved to nothing and the guard judged the wrong tree the other way.

    Now each git invocation's directory comes from `_analyse`: the `cd`s that persist to it (not those in a subshell, a pipeline stage, a substitution or a background job) with its own `-C` flags composed on top. `verb`, when a caller passes one, narrows that to the invocations running that subcommand; with none matching, every git invocation counts. The answer is a different root only when EVERY counted invocation resolves to that same root; any disagreement answers "" (judge this root), the direction every caller fails safe in. A scan with no git invocation at all falls back to the directory its last command runs in, which is what a `cd <dir> && <tool>` line means.
    """
    runs = _analyse(scan).runs
    gits = [r for r in runs if r.git_sub is not None]
    if verb is not None:
        gits = [r for r in gits if r.git_sub == verb] or gits
    # `git init -q /tmp/x && cd /tmp/x && git checkout -- .`: the `init` acts on `/tmp/x` while its own directory reads as this root, so it disagreed with every later invocation and sent the whole line back to this checkout (finding #5810a9f3). An `init` or `clone` is the line's own setup, never the command being judged, unless nothing else runs.
    gits = [r for r in gits if r.git_sub not in ("init", "clone")] or gits
    if gits:
        dirs = [r.git_dir for r in gits]
    elif runs:
        dirs = [runs[-1].cwd]
    else:
        dirs = []
    created = _created_dirs(runs, this_root)
    roots = set()
    for directory in dict.fromkeys(dirs):
        roots.add(_resolve_root(directory, this_root, created))
        if len(roots) > 1:
            return ""
    return roots.pop() if roots else ""


def _abs_dir(directory, this_root):
    """`directory` made absolute against this root, the way _resolve_root reads a hint."""
    return os.path.normpath(directory if directory.startswith("/") else this_root + "/" + directory)


def _created_dirs(runs, this_root):
    """The directories this same command creates before using them: the operand of `git init <dir>`, the destination of `git clone <url> <dir>`, and each `mkdir` operand, made absolute against the directory the creating command runs in."""
    created = set()
    for r in runs:
        base = r.git_dir if r.git_sub else r.cwd
        base = _abs_dir(base, this_root) if base else os.path.normpath(this_root)
        args = [a for a in (r.argv or []) if not a.startswith("-")]
        if r.git_sub in ("init", "clone"):
            sub = r.git_sub
            rest = args[args.index(sub) + 1 :] if sub in args else []
            # `init <dir>` creates its one operand; `clone <url> <dir>` creates its last, and a bare `clone <url>` names no directory here.
            if rest and (sub == "init" or len(rest) >= 2):
                created.add(_abs_dir(rest[-1], base))
        elif r.name == "mkdir":
            for a in args:
                created.add(_abs_dir(a, base))
    return created


def _resolve_root(directory, this_root, created=frozenset()):
    """The toplevel of the repository `directory` sits in, or "" when that is this root or nothing resolves.

    bash `case "$hint" in /*) ... ;; *) ...` -- a leading slash, nothing more elaborate. A `~` or a `$HOME` is NOT expanded here, so it never resolves.
    """
    if directory is None or directory in ("", "."):
        return ""
    abs_path = directory if directory.startswith("/") else this_root + "/" + directory
    target = _git_stdout(["-C", abs_path, "rev-parse", "--show-toplevel"], want_rc=True)
    if target is None:
        # A DIRECTORY OUTSIDE THIS CHECKOUT THAT IS NO REPOSITORY (YET) IS FOREIGN ONLY WHEN IT IS REAL. `git init -q /tmp/x && cd /tmp/x && git commit ...` is one command, so `/tmp/x` holds no repository when the hook runs; answering "" made every caller judge THIS checkout and refuse a fixture it has no business with (finding #5810a9f3). But a path that neither exists nor is created by this same command is a `cd` bash cannot perform, and after `cd /nonexistent; git push origin main` git runs in THIS checkout: treating that path as foreign would let the push past every guard. So it must exist on disk, or sit at or under a directory this command creates first. Anything else, and anything inside this root, keeps resolving to "".
        norm = os.path.normpath(abs_path)
        root_norm = os.path.normpath(this_root)
        outside = this_root and not (
            norm == root_norm or norm.startswith(root_norm.rstrip("/") + "/")
        )
        made = any(norm == c or norm.startswith(c.rstrip("/") + "/") for c in created)
        if outside and (os.path.isdir(norm) or made):
            return norm
        return ""
    target = _command_substitution(target)
    if target not in ("", this_root):
        return target
    return ""


def _gh_submodule(seg, scan):
    """The submodule the `gh` invocation named by `seg` runs in, "" for none, or None when the walk finds no gh invocation to ask about."""
    ghs = [r for r in _analyse(scan).runs if r.name.rsplit("/", 1)[-1] == "gh"]
    if not ghs:
        return None
    want = _collapse(seg)
    mine = [
        r
        for r in ghs
        if want.startswith(_collapse(r.canonical)) or _collapse(r.canonical).startswith(want)
    ]
    found = set()
    for run in mine or ghs:
        m = re.search(r"(^|/)private/(renet|account|elite|homebrew-tap)(/|$)", run.cwd or "")
        found.add("private/" + m.group(2) if m else "")
    return found.pop() if len(found) == 1 else ""


def _printf_line(text):
    """`printf '%s\\n' "$x"` -- exactly one newline appended, whatever `x` ends
    with. Not the same as a here-string only in name: both add one newline, and
    both are written out here so a reader does not have to remember which call site used which.
    """
    return text + "\n"


def _grep_only(pattern, text):
    """`grep -oE <pattern>` -- every non-overlapping match, in order, one per line, across every record. Python's finditer scans left to right and resumes after each match, which is GNU grep's rule too; what differs is leftmost-longest versus leftmost-first, and the module docstring records why the alternations here do not feel it."""
    compiled = re.compile(pattern)
    records, _ = _records(text)
    out = []
    for record in records:
        out.extend(m.group(0) for m in compiled.finditer(record))
    return out


def _git_stdout(args, want_rc=False):
    """Run git with stderr discarded.

    `want_rc=False` mirrors a pipeline whose exit status belongs to the LAST
    stage, so a git failure is just empty output. `want_rc=True` mirrors
    `target=$(git ...) || return 0`, where the failure itself is the branch.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
        )
    except OSError:
        # `git` absent behaves like `git` failing: bash sends the "command not found" message to the 2>/dev/null the caller already wrote.
        return None if want_rc else ""
    if want_rc and proc.returncode != 0:
        return None
    # Decoded by hand rather than with `encoding=`: text mode translates
    # universal newlines, so a \r would come back as \n and the value would differ from what the bash `$( )` captured. surrogateescape because a path is bytes, and refusing to decode one is not this function's job.
    return proc.stdout.decode("utf-8", "surrogateescape")


def repo_root_env(ev):
    """`CLAUDE_PROJECT_DIR` from the EVENT's environment, the root every guard passes as `this_root`.

    Not part of the bash lib -- each guard computes it itself -- but every caller of `target_root` needs the same answer, and a second spelling of it is exactly the drift `.ci/rediacc_ci/paths.py` was written to end.

    THE EVENT'S ENVIRONMENT, NOT `os.environ`, because `ev.env` is what every other guard reads the variable through. Reading the process's own made a guard judged through `dispatch.run_one(..., env=...)` take a different root from the event it was given: a suite run with the variable unset (CI, and the local `env -u` recipe) named the runner's checkout instead of the fixture's, and block_destructive_git_restore's foreign-cwd rule then read the fixture's own `git clean -fd` as foreign and allowed it. A live hook sees no difference, since `Event` defaults to `os.environ`.
    """
    # The checkout's own toplevel stands in when the harness did not export the variable (a test, a hand run), so a scope test against "" cannot silently pass everything through.
    return ev.env("CLAUDE_PROJECT_DIR") or _git_stdout(["rev-parse", "--show-toplevel"]).strip()


# =============================================================================
# THE LEXER: WHAT BASH ACTUALLY RUNS (PLAN-retire-bash-oracles A4, Rule T)
# =============================================================================
#
# EVERYTHING ABOVE IS A LINE-FOR-LINE PORT OF A SED/AWK PIPELINE, AND A0 MEASURED FIFTEEN PLACES WHERE THAT PIPELINE DISAGREES WITH BASH IN THE FAIL-OPEN DIRECTION (agent/plans/PLAN-retire-bash-oracles.A0.md section 1, L1-L15). The differential against `command-scan.sh` was blind to them by construction: the oracle carried the same bugs. Each one is a command bash runs that no anchor in any guard can see: `x=$(git push --force origin main)`, `"git" push --force origin main`, `{ git push --force origin main; }`, `bash -ce '...'`, `cat <<EOF` with a `$(...)` in its body, `bash <<'EOF'`, and so on.
#
# THE FIX IS ADDITIVE, NOT A REWRITE OF THE VIEW. The text every guard's regex already runs against (the prose-stripped line plus the first wrapper payload) keeps its exact bytes, because its shape IS the prose defence: a quoted span is deleted so that a commit message naming a command is not that command. What this section adds is a real tokenizer that walks the command the way bash's own grammar does and lists every simple command bash would execute, at any depth: substitutions (bare, inside double quotes, in an assignment value, in an unquoted heredoc body), subshells, brace groups, wrapper payloads (`sh -c`, every `-c` spelling bash accepts, and every wrapper on the line rather than only the first), `eval`, a shell reading a heredoc, a here-string or a pipe, and the command behind a reserved word, a prefix builtin or a leading redirect. Each one is rendered as a CANONICAL LINE: its command word with quoting removed, then its arguments with quoted spans dropped exactly as the view drops them.
#
# A canonical line is appended to the scan target ONLY WHEN THE VIEW DOES NOT ALREADY SHOW IT at a command position (`_visible`). So every case the old pipeline already handled produces the byte-identical scan target, and the goldens move only where a bypass is being closed.
#
# THE MODEL, AND ITS EDGE. A command is lifted when bash's grammar runs it. Text that only a runtime decision turns into code (a string computed and then `eval`'d, `base64 -d | sh`, a function body that is never called) is outside a static scanner's reach and is not claimed here; a function body IS lifted, because its definition cannot be told from its call without running the script, and over-reporting is the safe direction for a guard.

_OPERATORS = (";;&", ";;", ";&", "&&", "||", "|&", ";", "&", "|", "(", ")")
_REDIRECT = re.compile(r"(\d+|\{[A-Za-z_][A-Za-z0-9_]*\})?(&>>|<<<|<<-|&>|>>|>\||<>|<&|>&|<<|<|>)")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
_WORD_END = " \t\n;&|()<>"
_SEPARATORS = (";", "&", "&&", "||", "\n", ";;", ";&", ";;&")
# Reserved words that may stand in front of a command without being one. `{` and `}` are handled as structure, `for`/`select`/`case`/`function`/`[[` open a clause whose words are not a command.
_RESERVED_PREFIX = frozenset(
    ("!", "then", "do", "else", "elif", "if", "while", "until", "fi", "done", "esac", "}", "coproc")
)
_NOT_A_COMMAND = frozenset(("for", "select", "case", "function", "[[", "]]", "in"))
# Prefix commands that run the NEXT word as the command, with each one's options as its own parser reads them: `(short letters that take a value, {long option: "r" required value | "o" optional value | "n" none}, unique prefixes accepted)`. `command -v`/`-V` only prints, so it is handled apart.
# AN OPTION'S VALUE IS NOT THE COMMAND (review cac47d16.1 sweep). This table used to list the exact option words that take a value, so a value option it did not list, a bundle ending in a value letter, or an abbreviated long option left the VALUE read as the command: `xargs --max-procs 2 rm`, `xargs -rP 2 rm`, `xargs --max-p 2 rm`, `sudo --user root rm` and
# `stdbuf --output L rm` each walked as a command named `2`, `root` or `L`, and block_protected_files allowed every one of them fed or naming `.claude/settings.json` (rc 0, 2026-10-11) while the real tool ran `rm`. `_prefix_option` reads one option the way getopt_long does. An OPTIONAL value is only ever attached (`--eof=x`): measured, `xargs --max-lines 1 echo` runs `1`, so `--max-lines` is "o" whatever `--help` prints. The
# long tables are GNU findutils 4.10's and coreutils 9.7's `--help` merged with uutils 0.8.0's (the coreutils on this host), whose `timeout --sig KILL` also resolves an abbreviation; sudo's is its own `--help`. An option no table lists is read as taking no value.
_PREFIX_COMMANDS = {
    "command": ("", {}, False),
    "builtin": ("", {}, False),
    "exec": ("a", {}, False),
    "time": ("", {}, False),
    "nohup": ("", {"help": "n", "version": "n"}, True),
    "setsid": ("", {"ctty": "n", "fork": "n", "wait": "n", "help": "n", "version": "n"}, True),
    "env": (
        "uCSaf",
        {
            "ignore-environment": "n",
            "null": "n",
            "unset": "r",
            "chdir": "r",
            "split-string": "r",
            "argv0": "r",
            "file": "r",
            "block-signal": "o",
            "default-signal": "o",
            "ignore-signal": "o",
            "list-signal-handling": "n",
            "debug": "n",
            "help": "n",
            "version": "n",
        },
        True,
    ),
    "sudo": (
        "CDghprRtTuU",
        {
            "askpass": "n",
            "background": "n",
            "bell": "n",
            "chdir": "r",
            "chroot": "r",
            "close-from": "r",
            "command-timeout": "r",
            "edit": "n",
            "group": "r",
            "help": "n",
            "host": "r",
            "list": "n",
            "login": "n",
            "non-interactive": "n",
            "other-user": "r",
            "preserve-env": "o",
            "preserve-groups": "n",
            "prompt": "r",
            "remove-timestamp": "n",
            "reset-timestamp": "n",
            "role": "r",
            "set-home": "n",
            "shell": "n",
            "stdin": "n",
            "type": "r",
            "user": "r",
            "validate": "n",
            "version": "n",
        },
        True,
    ),
    "nice": ("n", {"adjustment": "r", "help": "n", "version": "n"}, True),
    "timeout": (
        "sk",
        {
            "signal": "r",
            "kill-after": "r",
            "foreground": "n",
            "preserve-status": "n",
            "verbose": "n",
            "help": "n",
            "version": "n",
        },
        True,
    ),
    "stdbuf": (
        "ioe",
        {"input": "r", "output": "r", "error": "r", "help": "n", "version": "n"},
        True,
    ),
    "xargs": (
        "aIdELnPs",
        {
            "null": "n",
            "arg-file": "r",
            "delimiter": "r",
            "eof": "o",
            "replace": "o",
            "max-lines": "o",
            "max-args": "r",
            "open-tty": "n",
            "max-procs": "r",
            "interactive": "n",
            "process-slot-var": "r",
            "no-run-if-empty": "n",
            "max-chars": "r",
            "show-limits": "n",
            "verbose": "n",
            "exit": "n",
            "help": "n",
            "version": "n",
        },
        True,
    ),
    # `sshpass` (#ec63ff8c): the password, its file, its descriptor and the prompt take the next word; `-e` reads SSHPASS and takes none, so it must not swallow the `ssh` after it. Stripped like `sudo`, because no guard judges an `sshpass` run by that name and both ssh guards need the `ssh` behind it.
    "sshpass": ("pfdP", {}, False),
}


# The prefix options that move the command (`env -C dir rm x` removes `dir/x`) or ARE the command (`env -S "rm x"` runs `rm x`).
_PREFIX_CHDIR = frozenset((("env", "C"), ("env", "chdir"), ("sudo", "D"), ("sudo", "chdir")))
_PREFIX_SPLIT = frozenset((("env", "S"), ("env", "split-string")))


def _prefix_option(name, vals, k):
    """`(words used, option, value)` for the option word `vals[k]` of prefix command `name`: `option` is a short letter or a canonical long name taking a value (None when nothing in the word does), `value` its value or None."""
    letters, longs, abbreviations = _PREFIX_COMMANDS[name]
    arg = vals[k]
    if arg.startswith("--"):
        key, eq, value = arg[2:].partition("=")
        full = key if key in longs else None
        if full is None and abbreviations:
            hits = [n for n in longs if n.startswith(key)]
            full = hits[0] if len(hits) == 1 else None
        kind = longs.get(full, "n") if full else "n"
        if eq:
            return 1, full, value
        if kind == "r" and k + 1 < len(vals):
            return 2, full, vals[k + 1]
        return 1, None, None
    for at, letter in enumerate(arg[1:], 1):
        if letter in letters:
            rest = arg[at + 1 :]
            if rest:
                return 1, letter, rest
            return (2, letter, vals[k + 1]) if k + 1 < len(vals) else (1, letter, None)
    return 1, None, None


# A prefix command that takes one positional operand before the command it runs.
_PREFIX_OPERAND = frozenset(("timeout",))
# LAUNCHERS (#ec63ff8c, 2026-10-09): `npx` (with `npm exec`, `npm exe` and `npm x`, #31ed6c5f) and `find -exec` run another command named in their own argv, and are NOT stripped like the prefixes above, because the launcher itself is a run other guards judge. `block_unscoped_formatter_run` reads `npx prettier --write` as an `npx` run and `block_host_toolchain_run` refuses `npx --yes ruff` on that shape, so `npx` has to stay the run's name.
# (`sshpass` has no such reader and is a plain prefix above.) The launched command is walked into an analysis of its own (`_Run.launched`): `lifted_commands` puts it on a line of its own, where every anchored text guard sees it at command position, while `_analyse(cmd).runs` stays the list it always was. Before this, three guards named `npx`, `sshpass` and `find -exec` inside their own anchors (`(npx[S]+)?`, `(sshpass ...)?`, `(find ... -exec ...)?`), three copies that still missed: `npx -y node packages/cli/dist/cli.js` and `find . -exec node cli-bundle.js \;` were both allowed (measured 2026-10-09).
# WHERE AN npm LAUNCH STARTS IS npm's OWN PARSE, PORTED (#31ed6c5f). `npx`, `npm exec`, `npm exe` and `npm x` all run the program named by the first operand npm's option parser leaves after `exec`, so the walk asks the same parser. Two lists of value options came before this one and both lost: a hand-picked seven missed `--loglevel` (#32e75fa4), and the complete table that replaced it could not see that npm's
# parser, `nopt`, accepts any unique PREFIX of an option name, so `npx --logl silent node packages/cli/dist/cli.js` read `silent` as the program and block_cli_bundle allowed it (rc 0, 2026-10-09; 442 `--` prefixes take a value). `npm exec -- node ...` and `npm x node ...` were not launchers at all (rc 0 the same day).
# So the port is of npm's two passes, not of their answers. `_npx_argv` is `bin/npx-cli.js`'s loop (it splices `--` in front of the first word it takes for the program, expanding shorthands and skipping a value it guesses at), and `_nopt` is `nopt`'s `parse` with npm's option types: unique-prefix abbreviations, shorthand bundles, `--no-`, `--key=value`, and the per-type rule for whether the next word is a value. The tables below are npm 11.20.0's, the version
# `.devcontainer/toolchain.env` pins. `tests/test_bash_semantics.py::test_npm_launch_matches_npm` asks that npm, with its `lib/cli.js` stubbed so nothing runs, what it would execute for every option spelling it accepts (every name, every unique prefix, one dash and two, `=value` and a separate word, behind `npx`, `npm exec` and `npm x`), and fails when the walk answers differently or when a table here and npm's own disagree.
# An option's type, as nopt reads it: "B" Boolean (a switch, which takes the next word only when that word is `true` or `false`), "S" String (it takes the next word unless that word looks like an option), "V" any other single type (it takes the next word whatever it is), and for a list of types "A" followed by "b" (Boolean: a switch that may still take a value), "n" (null: a following `false` makes it a switch), "s" (String), "N" (Number) and one "|x" per literal string x. `local-address` lists this machine's own addresses, which no table can carry, so it is spelled "|<address>" and any address-shaped word matches it.
_NPM_TYPES = {
    "B": (
        "all allow-same-version allow-scripts-pending allow-scripts-pin audit bin-links bypass-2fa "
        "commit-hooks dangerously-allow-all-scripts description dev diff-ignore-all-space "
        "diff-name-only diff-no-prefix diff-text dry-run engine-strict force foreground-scripts "
        "format-package-lock fund git-tag-version global global-style if-present ignore-scripts "
        "include-attestations include-staged include-workspace-root init-private install-links json "
        "legacy-bundling legacy-peer-deps link long offline omit-lockfile-registry-resolved "
        "package-lock package-lock-only packages-all parseable prefer-dedupe prefer-offline "
        "prefer-online progress provenance read-only rebuild-bundle save save-bundle save-dev "
        "save-exact save-optional save-peer save-prod shrinkwrap sign-git-commit sign-git-tag "
        "strict-allow-scripts strict-peer-deps strict-ssl timing unicode update-notifier usage "
        "version versions workspaces-update"
    ),
    "S": (
        "call diff-dst-prefix diff-src-prefix editor git heading init-author-email init-author-name "
        "init-license init-type init.author.email init.author.name init.license message "
        "pack-destination preid save-prefix scope searchexclude searchopts shell tag "
        "tag-version-prefix user-agent viewer"
    ),
    "V": (
        "cache cache-max cache-min cafile diff-unified fetch-retries fetch-retry-factor "
        "fetch-retry-maxtimeout fetch-retry-mintimeout fetch-timeout globalconfig init-module "
        "init-version init.module init.version logs-max maxsockets node-gyp prefix provenance-file "
        "registry searchlimit searchstaleness umask userconfig"
    ),
    "Ans": (
        "_auth ca cert cidr cpu key libc name node-options orgs os otp packages password scopes "
        "script-shell token-description"
    ),
    "As": "allow-scripts diff min-release-age-exclude noproxy package workspace",
    "Abn": "expect-results optional production workspaces yes",
    "AnN": "depth expect-result-count expires min-release-age which",
    "An": "before https-proxy logs-dir proxy",
    "A|all|none|root": "allow-directory allow-file allow-git allow-remote",
    "A|": "init-author-url init.author.url",
    "Abns": "browser",
    "Ab|always": "color",
    "An|<address>": "local-address",
    "An|1|2|3": "lockfile-version",
    "An|dev|development": "also",
    "An|info|low|moderate|high|critical|none": "audit-level",
    "An|prod|production": "only",
    "An|read-only|read-write|no-access": "orgs-permission",
    "An|read-only|read-write|read-write-stage-only|no-access": "packages-and-scopes-permission",
    "An|restricted|public|private": "access",
    "As|npmjs|never|always": "replace-registry-host",
    "A|cyclonedx|spdx": "sbom-format",
    "A|dev|optional|peer": "omit",
    "A|global|user|project": "location",
    "A|hoisted|nested|shallow|linked": "install-strategy",
    "A|legacy|web": "auth-type",
    "A|library|application|framework": "sbom-type",
    "A|prod|dev|optional|peer": "include",
    "A|silent|error|warn|notice|http|info|verbose|silly": "loglevel",
}  # fmt: skip
_NPM_SHORTHANDS = {
    "?": "--usage", "B": "--save-bundle", "C": "--prefix", "D": "--save-dev", "E": "--save-exact",
    "H": "--usage", "L": "--location", "O": "--save-optional", "P": "--save-prod", "S": "--save",
    "a": "--all", "c": "--call", "d": "--loglevel info", "dd": "--loglevel verbose", "ddd":
    "--loglevel silly", "desc": "--description", "enjoy-by": "--before", "f": "--force", "g":
    "--global", "h": "--usage", "help": "--usage", "iwr": "--include-workspace-root", "l": "--long",
    "local": "--no-global", "m": "--message", "n": "--no-yes", "no": "--no-yes", "p": "--parseable",
    "porcelain": "--parseable", "q": "--loglevel warn", "quiet": "--loglevel warn", "readonly":
    "--read-only", "reg": "--registry", "s": "--loglevel silent", "silent": "--loglevel silent",
    "v": "--version", "verbose": "--loglevel verbose", "w": "--workspace", "ws": "--workspaces",
    "y": "--yes",
}  # fmt: skip
_NPM_TYPE = {key: kind for kind, keys in _NPM_TYPES.items() for key in keys.split()}
_NPM_SHORT = {key: value.split() for key, value in _NPM_SHORTHANDS.items()}
# `bin/npx-cli.js`'s own sets: the options it removed (it drops them, and the value of a removed one), and the ones it always treats as taking the next word.
_NPX_REMOVED_SWITCHES = frozenset(("always-spawn", "ignore-existing", "shell-auto-fallback"))
_NPX_REMOVED_OPTS = frozenset(("npm", "node-arg", "n"))
_NPX_OPTS = frozenset(
    (*_NPX_REMOVED_OPTS, "package", "p", "cache", "userconfig", "call", "c", "shell")
)
_NPX_SWITCHES = frozenset(
    (
        *_NPX_REMOVED_SWITCHES,
        *(key for key, kind in _NPM_TYPE.items() if kind == "B" or kind.startswith("Ab")),
        *("no-install", "quiet", "q", "version", "v", "help", "h"),
    )
)
# The npm command words that resolve to `exec` (`lib/utils/cmd-list.js` `deref`: the command, its one unique abbreviation, its alias).
_NPM_EXEC_WORDS = frozenset(("exec", "exe", "x"))
# `find` actions whose operands up to a lone `;` or `+` are a command it runs, once per match.
_FIND_EXEC = frozenset(("-exec", "-execdir", "-ok", "-okdir"))
# `ssh` short options that take a value (OpenSSH 9, `ssh(1)` SYNOPSIS); every other letter is a flag. The value is either the rest of the bundle (`-p22`) or the next word.
_SSH_VALUE_LETTERS = frozenset("BbcDEeFIiJLlmOoPpQRSWw")


# npm options that run the command in ANOTHER package (#503f0ba8): an `npm run` it launches reads that package's scripts, and a `.` it names is that package's directory, not this cwd. Named as `_nopt` resolves them, so `-w`, `-C`, `--ws` and every abbreviation (`--workspa`) count.
_NPM_ELSEWHERE = frozenset(("workspace", "workspaces", "prefix"))
# The `find -exec` family members that run the command in each MATCH'S directory instead of find's own cwd.
_FIND_IN_MATCH_DIR = frozenset(("-execdir", "-okdir"))
# `find` options that come BEFORE its starting points; `-D` and `-O<n>` aside, they take no value.
_FIND_LEADING = frozenset(("-H", "-L", "-P"))


class Launch(typing.NamedTuple):
    """Where a launched command runs (#503f0ba8), on `_Run.launch` for every run a launcher started, and for every run nested under one.

    `launcher` is "npx" (also for `npm exec`, `npm exe` and `npm x`, which are the same launch) or "find". `action` is find's `-exec`/`-execdir`/`-ok`/`-okdir`, "" for npx. `starts` are find's starting points, quote-removed (`(".",)` when it names none), and () for npx: what `{}` stands for lies under them. `elsewhere` is True when the command does not run in the launcher's own cwd and package: `-execdir`/`-okdir` run it in each match's directory, and `npx -w/--workspace/--prefix/--workspaces` in another package. A guard that resolves a path or a package.json against `run.cwd` leaves an `elsewhere` run unjudged rather than judging it against the wrong directory.
    """

    launcher: str
    action: str
    starts: tuple
    elsewhere: bool


def _find_starts(argv):
    """find's starting points: the words after its leading options and before the first expression word."""
    k = 0
    while k < len(argv) and (argv[k] in _FIND_LEADING or argv[k].startswith("-O")):
        k += 1
    starts = []
    while k < len(argv):
        word = argv[k]
        if word == "-D":
            k += 2
            continue
        if word.startswith(("-", "(", "!", ")", ",")):
            break
        starts.append(word)
        k += 1
    return tuple(starts) or (".",)


def _js_abbrev(words):
    """The `abbrev` package nopt builds its tables with: every word maps to itself, and every prefix that starts exactly one of the words maps to that word."""
    counts: dict[str, int] = {}
    for word in words:
        for k in range(1, len(word)):
            counts[word[:k]] = counts.get(word[:k], 0) + 1
    out = {word[:k]: word for word in words for k in range(1, len(word)) if counts[word[:k]] == 1}
    out.update((word, word) for word in words)
    return out


_NPM_ABBREVS = _js_abbrev(sorted(_NPM_TYPE))
_NPM_SHORT_ABBREVS = _js_abbrev(sorted(_NPM_SHORT))
_NPM_SINGLES = frozenset(key for key in _NPM_SHORT if len(key) == 1)


def _nopt_short(arg):
    """nopt's `resolveShort`: the words an option spelling expands to, or None when it is an option name (or a prefix of one) and not a shorthand."""
    key = re.sub(r"^-+", "", arg)
    if _NPM_ABBREVS.get(key) == key:
        return None
    if key in _NPM_SHORT:
        return _NPM_SHORT[key]
    # A bundle of single-letter shorthands (`-gS`); the empty name is a bundle of none.
    if all(ch in _NPM_SINGLES for ch in key):
        return [word for ch in key for word in _NPM_SHORT[ch]]
    if key in _NPM_ABBREVS:
        return None
    return _NPM_SHORT.get(_NPM_SHORT_ABBREVS.get(key, key))


# JavaScript's `isNaN` is false for these strings (`Number(s)` is a number); `Number("")` is 0.
_JS_NUMBER = re.compile(
    r"[+-]?(Infinity|(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?)|0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+|"
)
_ADDRESS = re.compile(r"[0-9]+(\.[0-9]+){3}|[0-9A-Fa-f:]*:[0-9A-Fa-f:.%a-z]*")


def _nopt_listed_value(ahead, flags, literals):
    """Whether a switch whose type is a list takes `ahead` as its value: one of its literals, `null` when it is nullable, a number when it lists Number, any word not shaped like a short option when it lists String."""
    if ahead in literals or ("<address>" in literals and _ADDRESS.fullmatch(ahead)):
        return True
    if ahead == "null" and "n" in flags:
        return True
    if "N" in flags and not re.match(r"^-{2,}[^-]", ahead) and _JS_NUMBER.fullmatch(ahead.strip()):
        return True
    return "s" in flags and not re.match(r"^-[^-]", ahead)


def _nopt(args):
    """nopt's `parse` over `args`, a list of `(word, argv index)`: `(options, operands)`, `options` mapping each resolved option name to the values it got, `operands` the words left, each still carrying its index. Every branch below is one of `nopt-lib.js`'s, in its order."""
    args = list(args)
    data: dict[str, list] = {}
    remain: list = []
    i = 0
    while i < len(args):
        arg, at = args[i]
        if re.fullmatch(r"-{2,}", arg):
            remain.extend(args[i + 1 :])
            break
        if not (arg.startswith("-") and len(arg) > 1):
            remain.append(args[i])
            i += 1
            continue
        had_eq = "=" in arg
        if had_eq:
            arg, value = arg.split("=", 1)
            args[i : i + 1] = [(arg, at), (value, at)]
        expanded = _nopt_short(arg)
        if expanded is not None:
            args[i : i + 1] = [(word, at) for word in expanded]
            if not expanded or expanded[0] != arg:
                continue
        key = re.sub(r"^-+", "", arg)
        negated = None
        while key.lower().startswith("no-"):
            negated = not negated
            key = key[3:]
        key = _NPM_ABBREVS.get(key, key)
        kind = _NPM_TYPE.get(key)
        ahead = args[i + 1][0] if i + 1 < len(args) else None
        listed = kind is not None and kind[0] == "A"
        flags, *literals = kind[1:].split("|") if listed and kind else ("",)
        switch = (
            negated is not None
            or kind == "B"
            or "b" in flags
            or (kind is None and not had_eq)
            or (ahead == "false" and "n" in flags)
        )
        if switch:
            value = not negated
            if ahead in ("true", "false"):
                value = ahead == "true"
                ahead = None
                i += 1
            if listed and ahead and _nopt_listed_value(ahead, flags, literals):
                value = ahead
                i += 1
            data.setdefault(key, []).append(value)
            i += 1
            continue
        step = 2
        if kind == "S":
            if ahead is None:
                ahead = ""
            elif re.match(r"^-{1,2}[^-]+", ahead):
                ahead = ""
                step = 1
        if ahead is not None and re.fullmatch(r"-{2,}", ahead):
            ahead = None
            step = 1
        data.setdefault(key, []).append(True if ahead is None else ahead)
        i += step
    return data, remain


def _npx_argv(args):
    """`bin/npx-cli.js`'s loop over its own arguments (`(word, argv index)` pairs), before it hands them to `npm exec`: shorthands expanded, removed options dropped, and a `--` spliced in front of the first word it takes for the program."""
    args = list(args)
    i = 0
    while i < len(args):
        arg, at = args[i]
        if arg == "--":
            break
        if not arg.startswith("-"):
            args.insert(i, ("--", None))
            break
        key, *value = re.sub(r"^-+", "", arg).split("=")
        if key == "p":
            args[i] = ("=".join(["--package", *value]), at)
        elif key == "shell":
            args[i] = ("=".join(["--script-shell", *value]), at)
        elif key == "no-install":
            args[i] = ("--yes=false", at)
        elif key in _NPM_SHORT and key not in _NPX_REMOVED_SWITCHES | _NPX_REMOVED_OPTS:
            args[i : i + 1] = [
                (word, at) for word in [*_NPM_SHORT[key], *(["=".join(value)] if value else [])]
            ]
            continue
        removed = key in _NPX_REMOVED_SWITCHES | _NPX_REMOVED_OPTS
        if removed:
            del args[i]
            i -= 1
        ahead = args[i + 1][0] if 0 <= i + 1 < len(args) else "undefined"
        if (
            not value
            and key not in _NPX_SWITCHES
            and (key in _NPX_OPTS or not ahead.startswith("-"))
        ):
            if removed:
                del args[i + 1 : i + 2]
            else:
                i += 1
        i += 1
    return args


def _npm_launch(base, argv):
    """`(launched, Launch)` for an `npx` or `npm exec` argv, None when npm would run nothing: `launched` is `("text", call)` for `-c`/`--call`, else `("argv", words, span)`, `span` the argv indexes of the first and last word or None."""
    words = list(zip(argv, range(len(argv)), strict=True))
    if base == "npx":
        data, remain = _nopt([("exec", None), *_npx_argv(words)])
    else:
        data, remain = _nopt(words)
    if not remain or remain[0][0] not in _NPM_EXEC_WORDS:
        return None
    if base == "npx" and remain[0][1] is not None:
        return None
    elsewhere = any(
        value not in (False, "", None) for key in _NPM_ELSEWHERE for value in data.get(key, ())
    )
    launch = Launch("npx", "", (), elsewhere)
    call = data.get("call", [None])[-1]
    # nopt's `clean` turns a switch value given to a String option into text: `--no-call` is the call `false`.
    if isinstance(call, bool):
        call = "true" if call else "false"
    if isinstance(call, str) and call:
        return ("text", call), launch
    operands = remain[1:]
    if not operands:
        return None
    # A word npx itself inserted, or one a shorthand expanded to, has no place of its own in the argv.
    span = (operands[0][1], operands[-1][1])
    return ("argv", [word for word, _at in operands], None if None in span else span), launch


def _launches(base, argv):
    """The commands a launcher run starts, each with its `Launch`: a list of `(how, what, Launch, span)`, `how` "argv" (`what` a word list) or "text" (`what` a shell string), empty for anything that is not a launcher. `span` is `(first, last)`, the argv indexes of the launched words, None for a shell string."""
    if base in ("npx", "npm"):
        found = _npm_launch(base, argv)
        if found is None:
            return []
        launched, launch = found
        if launched[0] == "text":
            return [("text", launched[1], launch, None)]
        return [("argv", launched[1], launch, launched[2])]
    if base == "find":
        out = []
        starts = _find_starts(argv)
        k = 0
        while k < len(argv):
            if argv[k] not in _FIND_EXEC:
                k += 1
                continue
            action = argv[k]
            j = k + 1
            while j < len(argv) and argv[j] not in (";", "+"):
                j += 1
            if j > k + 1:
                launch = Launch("find", action, starts, action in _FIND_IN_MATCH_DIR)
                out.append(("argv", argv[k + 1 : j], launch, (k + 1, j - 1)))
            k = j + 1
        return out
    return []


def _launched(base, argv):
    """The commands a launcher run starts: a list of `("argv", [word, ...])` or `("text", payload)`, empty for anything that is not a launcher. `_launches` carries each one's `Launch` too."""
    return [(how, what) for how, what, _launch, _span in _launches(base, argv)]


def _ssh_remote(argv):
    """`(destination, remote command)` for an `ssh` argv, or None when it names no remote command (an interactive login, `-N`, a malformed line).

    ssh joins every word after the destination with single spaces and hands that string to the remote login shell, which parses it again. So `ssh h "docker ps"` and `ssh h docker ps` send the same command, and a quoted remote command is a shell PAYLOAD exactly as `sh -c '...'` is, not prose: the view drops it with every other quoted span, which is why `ssh prod-1 "docker ps"` was allowed (rc 0, 2026-10-09).
    """
    k, ended = _ssh_options(argv, 0)
    if k >= len(argv):
        return None
    destination = argv[k]
    # OpenSSH reads options AFTER the destination too, unless `--` came first: `ssh prod-1 -t docker ps` sends `docker ps`. The first word that is not an option opens the command, so in `ssh h ls -la` the `-la` is the remote command's.
    k = k + 1 if ended else _ssh_options(argv, k + 1)[0]
    if k >= len(argv):
        return None
    return destination, " ".join(argv[k:])


def _ssh_options(argv, k):
    """Skip ssh options from `argv[k]`: `(index of the first non-option, whether a `--` ended them)`. A bundle takes a value when a value letter is in it: the rest of the bundle (`-p22`), or the next word when the letter is last (`-vp 22`)."""
    while k < len(argv):
        arg = argv[k]
        if arg == "--":
            return k + 1, True
        if not (arg.startswith("-") and len(arg) > 1):
            break
        letters = arg[1:]
        for at, letter in enumerate(letters):
            if letter in _SSH_VALUE_LETTERS:
                if at == len(letters) - 1:
                    k += 1
                break
        k += 1
    return k, False


def _quote_argv(argv):
    """Words already quote-removed, re-quoted so a nested walk reads them as the SAME words: `{}` stays one argument, and a value holding a blank is not split."""
    return " ".join(
        a if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", a) else "'" + a.replace("'", "'\"'\"'") + "'"
        for a in argv
    )


def _stage_feed(stage, lexer):
    """The literal text a pipeline stage could write to its stdout: every word of it, quote-removed, plus the here-strings and heredoc bodies it reads. What the words PRINT is not known here, so all of them count."""
    out: list[str] = []
    if stage[0] in ("sub", "brace"):
        for item in stage[1]:
            if item[0] == "pipe":
                out.extend(_stage_feed(s, lexer) for s in item[1])
        return " ".join(out)
    for tok in stage[1]:
        if isinstance(tok, _Word):
            out.append(_word_value(tok))
        elif isinstance(tok, _Redir):
            out.append(_redir_feed(tok, lexer))
    return " ".join(o for o in out if o)


# WHEN THE WORDS ON xargs's STDIN ARE KNOWN EXACTLY (#5077391c, review 126f2a9f.1). Measured on bash 5.3 by piping each spelling into `xargs printf '[%s]'`:
#   an unquoted `echo` word expands `~` at its start and after `=` (`a=~/r`), braces (`{x,y}`, `{1..2}`), globs (`*`, `?`, `[ab]`), `$`, backticks and `<(...)`;
#   a here-string word expands `~` at its start and after `:` (`a:~/r`, but not `a=~/r`), `$`, backticks and `<(...)`, and neither braces nor globs;
#   a heredoc body expands only `$`, backticks and backslashes, so `~/r.sh`, `{x,y}` and `g*` reach xargs as written.
# Rather than port each rule, an unquoted word is exact only when it is made of characters none of them touches (`_PLAIN_WORD`: no `~`, brace, glob, `$`, backtick, parenthesis or `<`/`>`), and a single-quoted word, where bash expands nothing, is exact as its content. Either way a quote or a backslash left in the text is not exact, because xargs reads quotes and backslashes itself.
_PLAIN_WORD = re.compile(r"[A-Za-z0-9_./,+@%=:-]+")
_XARGS_QUOTING = re.compile(r"['\"\\]")
_EXPANDS_IN_HEREDOC = re.compile(r"[$`\\'\"]")
# The operators that point a producer's stdout somewhere other than the pipe. `>&` counts only when its target is not stdout itself.
_STDOUT_AWAY = frozenset((">", ">>", ">|", "&>", "&>>", ">&", "<>"))


def _literal_word(raw):
    """The words xargs reads from one shell word printed as written, or None when bash would expand it first."""
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        inner = raw[1:-1]
        return None if _XARGS_QUOTING.search(inner) else inner.split()
    return raw.split() if _PLAIN_WORD.fullmatch(raw) else None


def _stdout_away(redirs):
    """Does one of these redirects send the command's stdout away from the pipe (`echo a > f | xargs ...` feeds xargs nothing)?"""
    for redir in redirs:
        if redir.op not in _STDOUT_AWAY or redir.fd not in (None, "1"):
            continue
        target = _word_value(redir.target) if redir.target is not None else ""
        if redir.op == ">&" and target in ("1", ""):
            continue
        if redir.op == "<>" and redir.fd is None:
            continue
        return True
    return False


def _literal_feed(producers, redirs, lexer):
    """The exact words on a command's stdin (`_Run.feed_words`), or None. Its own stdin redirect wins over the pipe, as bash's redirection does, and any input redirect this cannot read exactly (a heredoc whose body was not found, a here-string with no word, a file, a descriptor) makes the feed unknown. Else the stage right in front must be an `echo` of literal words; one whose stdout goes elsewhere feeds nothing."""
    for redir in reversed(redirs):
        if redir.heredoc is not None:
            hd = redir.heredoc
            if hd.body_start is None:
                return None
            body = lexer.src[hd.body_start : hd.body_end]
            return None if _EXPANDS_IN_HEREDOC.search(body) else body.split()
        if redir.op == "<<<":
            if redir.target is None:
                return None
            return _literal_word(lexer.src[redir.target.start : redir.target.end])
        if redir.op in ("<", "<>", "<&") and redir.fd in (None, "0"):
            return None
    if not producers or producers[-1][0] != "cmd":
        return None
    stage = producers[-1][1]
    words, _ = _strip_prefixes([t for t in stage if isinstance(t, _Word)])
    if not words or _base(_word_value(words[0])) != "echo":
        return None
    if _stdout_away([t for t in stage if isinstance(t, _Redir)]):
        return []
    raw = [lexer.src[w.start : w.end] for w in words[1:]]
    while raw and re.fullmatch(r"-[neE]+", raw[0]):
        raw = raw[1:]
    out: list[str] = []
    for text in raw:
        got = _literal_word(text)
        if got is None:
            return None
        out.extend(got)
    return out


def _procsub(word):
    """The `<(...)`/`>(...)` part a word is made of alone, else None."""
    if word is not None and len(word.parts) == 1 and word.parts[0].kind == "procsub":
        return word.parts[0]
    return None


def _redir_feed(redir, lexer):
    """What a redirect hands a command on stdin as TEXT: a here-string's word, a heredoc's body, every word a `< <(...)` substitution's commands carry (what they print is not computed, as for a pipeline stage), nothing for a file."""
    if redir.heredoc is not None and redir.heredoc.body_start is not None:
        return lexer.src[redir.heredoc.body_start : redir.heredoc.body_end]
    if redir.op == "<<<" and redir.target is not None:
        return _word_value(redir.target)
    sub = _procsub(redir.target)
    if redir.op == "<" and sub is not None and sub.sub is not None:
        return " ".join(
            _stage_feed(stage, lexer)
            for item in _parse(sub.sub)
            if item[0] == "pipe"
            for stage in item[1]
        )
    return ""


# How deep substitutions and payloads may nest before the rest is treated as opaque. Real commands nest two or three deep; the cap only exists so that a pathological input cannot exhaust the interpreter's stack inside a guard.
_MAX_DEPTH = 24


class _Part:
    """One piece of a word: `lit`, `esc`, `sq`, `ansi`, `dq`, `subst`, `bq`, `procsub`, `arith` or `param`.

    `raw` is the source text, `value` what quote removal leaves, `sub` the token list of a command substitution, `parts` the pieces of a double-quoted string or of a `${...}` expansion.
    """

    __slots__ = ("kind", "parts", "raw", "sub", "value")

    def __init__(self, kind, raw, value="", sub=None, parts=None):
        self.kind = kind
        self.raw = raw
        self.value = value
        self.sub = sub
        self.parts = parts or []


class _Word:
    __slots__ = ("end", "parts", "start")

    def __init__(self, start, end, parts):
        self.start = start
        self.end = end
        self.parts = parts


class _Op:
    __slots__ = ("start", "text")

    def __init__(self, text, start):
        self.text = text
        self.start = start


class _Heredoc:
    """A `<<`/`<<-` redirect's body, once the lexer has read it."""

    __slots__ = ("body_end", "body_start", "delim", "quoted", "strip_tabs", "substs", "term_end")

    def __init__(self, delim, quoted, strip_tabs):
        self.delim = delim
        self.quoted = quoted
        self.strip_tabs = strip_tabs
        self.body_start = None
        self.body_end = None
        self.term_end = None
        self.substs = []


class _Redir:
    # `fd` is the descriptor written in front of the operator (`2` of `2>`, `{x}` of `{x}>`), None when there is none.
    __slots__ = ("fd", "heredoc", "op", "target")

    def __init__(self, op, target, heredoc=None, fd=None):
        self.op = op
        self.target = target
        self.heredoc = heredoc
        self.fd = fd


def _decode_ansi(body):
    """`$'...'` escapes, the subset bash documents. An unknown escape keeps its backslash, as bash does."""
    simple = {
        "n": "\n",
        "t": "\t",
        "r": "\r",
        "a": "\a",
        "b": "\b",
        "e": "\x1b",
        "E": "\x1b",
        "f": "\f",
        "v": "\v",
        "\\": "\\",
        "'": "'",
        '"': '"',
        "?": "?",
    }

    def one(m):
        seq = m.group(1)
        head = seq[0]
        if head in simple and len(seq) == 1:
            return simple[head]
        if head == "x" and len(seq) > 1:
            return chr(int(seq[1:], 16))
        if head in "uU" and len(seq) > 1:
            return chr(min(int(seq[1:], 16), 0x10FFFF))
        if head.isdigit():
            return chr(int(seq, 8) & 0xFF)
        if head == "c" and len(seq) == 2:
            return chr(ord(seq[1]) & 0x1F)
        return "\\" + seq

    return re.sub(
        r"\\(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}|c.|.)",
        one,
        body,
        flags=re.DOTALL,
    )


class _Lexer:
    """Tokenise one command string the way bash's parser does, closely enough to know what runs.

    It never raises and always terminates: an unterminated quote is read as a literal character (bash would reject the whole line and run nothing, so reading on is the over-reporting direction), an unterminated substitution runs to the end of the input, and nesting deeper than `_MAX_DEPTH` is left opaque.
    """

    def __init__(self, src, depth=0):
        self.src = src
        self.depth = depth
        self.pending: list = []
        self.heredocs: list = []

    def tokens(self):
        return self._list(0, len(self.src), None)[0]

    # -- the token stream --------------------------------------------------

    def _list(self, i, limit, closer):
        src = self.src
        toks: list = []
        parens = 0
        at_cmd = True
        while i < limit:
            c = src[i]
            if c in " \t":
                i += 1
                continue
            if c == "\\" and i + 1 < limit and src[i + 1] == "\n":
                i += 2
                continue
            if c == "#":
                # A comment runs to the end of the line and is never code. Its quote characters open nothing, which is half of A0's L6: `true # it's` followed by a command on the next line.
                j = src.find("\n", i, limit)
                i = limit if j < 0 else j
                continue
            if c == "\n":
                toks.append(_Op("\n", i))
                i += 1
                at_cmd = True
                if self.pending:
                    i = self._bodies(i, limit)
                continue
            if c == ")" and closer == ")" and parens == 0:
                return toks, i + 1
            if at_cmd and src.startswith("((", i):
                j = self._arith_end(i + 2, limit)
                if j > 0:
                    toks.append(_Word(i, j, [_Part("arith", src[i:j])]))
                    i = j
                    at_cmd = False
                    continue
            if c in "<>" and i + 1 < limit and src[i + 1] == "(":
                word, i = self._word(i, limit)
                toks.append(word)
                at_cmd = False
                continue
            m = _REDIRECT.match(src, i, limit)
            if m:
                i = self._redirect(m, limit, toks)
                continue
            op = next((o for o in _OPERATORS if src.startswith(o, i) and i + len(o) <= limit), None)
            if op is not None:
                if op == "(":
                    parens += 1
                elif op == ")" and parens:
                    parens -= 1
                toks.append(_Op(op, i))
                i += len(op)
                at_cmd = op != ")"
                continue
            word, i = self._word(i, limit)
            toks.append(word)
            at_cmd = _word_value(word) in _RESERVED_PREFIX or _word_value(word) == "{"
        return toks, limit

    def _redirect(self, m, limit, toks):
        src = self.src
        op = m.group(2)
        j = m.end()
        while j < limit and src[j] in " \t":
            j += 1
        target = None
        # A PROCESS SUBSTITUTION IS A TARGET (review e085085d.1): `done < <(echo x)` reads the substitution's output, so `<(...)` is the redirect's word, not an argument of the command. Read as an argument, `xargs rm < <(...)` handed `rm` the substitution's source text and the loop's feed was lost.
        procsub = op not in ("<<", "<<-") and src.startswith(("<(", ">("), j)
        if j < limit and (src[j] not in "\n;&|()<>" or procsub):
            target, j = self._word(j, limit)
        heredoc = None
        if op in ("<<", "<<-") and target is not None:
            quoted = any(p.kind in ("sq", "dq", "esc", "ansi") for p in target.parts)
            heredoc = _Heredoc(_word_value(target), quoted, op == "<<-")
            self.pending.append(heredoc)
            self.heredocs.append(heredoc)
        toks.append(_Redir(op, target, heredoc, m.group(1)))
        return j

    def _bodies(self, i, limit):
        """Read the bodies of every heredoc opened on the line that just ended, in order.

        THE TERMINATOR IS THE WHOLE LINE, COMPARED EXACTLY, which is what bash does and what the regex above did not (A0 S1, S2): a plain `<<` never strips indentation, a trailing blank keeps a line from closing the body, and `<<END-X` waits for `END-X` rather than `END`. Only `<<-` strips leading TABS, never spaces.
        """
        src = self.src
        for hd in self.pending:
            hd.body_start = i
            while True:
                if i >= limit:
                    hd.body_end = limit
                    hd.term_end = limit
                    break
                j = src.find("\n", i, limit)
                line_end = limit if j < 0 else j
                line = src[i:line_end]
                if (line.lstrip("\t") if hd.strip_tabs else line) == hd.delim:
                    hd.body_end = i
                    hd.term_end = limit if j < 0 else line_end + 1
                    i = hd.term_end
                    break
                i = limit if j < 0 else line_end + 1
            if not hd.quoted:
                hd.substs = self._scan_substs(hd.body_start, hd.body_end)
        self.pending = []
        return i

    # -- words ---------------------------------------------------------------

    def _word(self, i, limit):
        src = self.src
        start = i
        parts: list = []
        lit: list[str] = []

        def flush():
            if lit:
                text = "".join(lit)
                parts.append(_Part("lit", text, text))
                lit.clear()

        while i < limit:
            c = src[i]
            if c in _WORD_END:
                if c in "<>" and i == start and i + 1 < limit and src[i + 1] == "(":
                    toks, j = self._sub(i + 2, limit)
                    parts.append(_Part("procsub", src[i:j], src[i:j], sub=toks))
                    i = j
                    continue
                break
            if c == "\\":
                if i + 1 >= limit:
                    lit.append(c)
                    i += 1
                elif src[i + 1] == "\n":
                    i += 2
                else:
                    flush()
                    parts.append(_Part("esc", src[i : i + 2], src[i + 1]))
                    i += 2
                continue
            if c == "'":
                j = src.find("'", i + 1, limit)
                if j < 0:
                    lit.append(c)
                    i += 1
                    continue
                flush()
                parts.append(_Part("sq", src[i : j + 1], src[i + 1 : j]))
                i = j + 1
                continue
            if c == '"' or (c == "$" and i + 1 < limit and src[i + 1] == '"'):
                part, j = self._dq(i + (1 if c == "$" else 0), limit)
                if part is None:
                    lit.append(c)
                    i += 1
                    continue
                flush()
                part.raw = src[i:j]
                parts.append(part)
                i = j
                continue
            if c == "$" and i + 1 < limit and src[i + 1] == "'":
                j = self._ansi_end(i + 2, limit)
                if j < 0:
                    lit.append(c)
                    i += 1
                    continue
                flush()
                parts.append(_Part("ansi", src[i : j + 1], _decode_ansi(src[i + 2 : j])))
                i = j + 1
                continue
            special = self._special(i, limit)
            if special is not None:
                flush()
                parts.append(special[0])
                i = special[1]
                continue
            lit.append(c)
            i += 1
        flush()
        return _Word(start, i, parts), i

    def _special(self, i, limit):
        """A `$(...)`, `$((...))`, `${...}` or backtick starting at `i`, as `(part, end)`; None when there is none."""
        src = self.src
        c = src[i]
        if c == "`":
            j = self._bq_end(i + 1, limit)
            if j < 0:
                return None
            toks = self._nested(i + 1, j)
            return _Part("bq", src[i : j + 1], src[i : j + 1], sub=toks), j + 1
        if c != "$" or i + 1 >= limit:
            return None
        nxt = src[i + 1]
        if nxt == "(":
            if src.startswith("((", i + 1):
                j = self._arith_end(i + 3, limit)
                if j > 0:
                    return _Part("arith", src[i:j], src[i:j]), j
            toks, j = self._sub(i + 2, limit)
            return _Part("subst", src[i:j], src[i:j], sub=toks), j
        if nxt == "{":
            j, inner = self._brace_end(i + 2, limit)
            return _Part("param", src[i:j], src[i:j], parts=inner), j
        return None

    def _dq(self, i, limit):
        """A double-quoted string opening at `i`, as `(part, end)`, or `(None, i)` when it never closes.

        A0's L2 lives here: `$(...)` and backticks inside double quotes EXECUTE, so they are parsed rather than skipped. An unterminated string rolls back every heredoc the attempt registered, so a failed parse leaves no trace.
        """
        src = self.src
        mark = (len(self.pending), len(self.heredocs))
        j = i + 1
        parts: list = []
        lit: list[str] = []

        def flush():
            if lit:
                text = "".join(lit)
                parts.append(_Part("lit", text, text))
                lit.clear()

        while j < limit:
            c = src[j]
            if c == '"':
                flush()
                value = "".join(p.value for p in parts)
                return _Part("dq", src[i : j + 1], value, parts=parts), j + 1
            if c == "\\" and j + 1 < limit:
                nxt = src[j + 1]
                if nxt == "\n":
                    j += 2
                    continue
                if nxt in '$`"\\':
                    lit.append(nxt)
                    j += 2
                    continue
                lit.append(c)
                j += 1
                continue
            special = self._special(j, limit)
            if special is not None:
                flush()
                parts.append(special[0])
                j = special[1]
                continue
            lit.append(c)
            j += 1
        del self.pending[mark[0] :]
        del self.heredocs[mark[1] :]
        return None, i

    def _scan_substs(self, i, limit):
        """Every substitution in an unquoted heredoc body: the body is data, but these run (A0 L3)."""
        src = self.src
        found: list = []
        while i < limit:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            special = self._special(i, limit) if c in "$`" else None
            if special is not None:
                found.append(special[0])
                i = special[1]
                continue
            i += 1
        return found

    # -- spans ---------------------------------------------------------------

    def _sub(self, i, limit):
        """The tokens of a `$(`/`<(` body starting at `i`, and the index after its `)`."""
        if self.depth >= _MAX_DEPTH:
            return [], limit
        self.depth += 1
        try:
            return self._list(i, limit, ")")
        finally:
            self.depth -= 1

    def _nested(self, i, j):
        if self.depth >= _MAX_DEPTH:
            return []
        self.depth += 1
        try:
            return self._list(i, j, None)[0]
        finally:
            self.depth -= 1

    def _bq_end(self, i, limit):
        src = self.src
        while i < limit:
            if src[i] == "\\":
                i += 2
                continue
            if src[i] == "`":
                return i
            i += 1
        return -1

    def _ansi_end(self, i, limit):
        src = self.src
        while i < limit:
            if src[i] == "\\":
                i += 2
                continue
            if src[i] == "'":
                return i
            i += 1
        return -1

    def _arith_end(self, i, limit):
        """The index after the `))` closing an arithmetic span, or -1 when there is none (then `((` is two subshells)."""
        src = self.src
        depth = 0
        while i < limit:
            c = src[i]
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    return i + 2 if src.startswith("))", i) else -1
                depth -= 1
            i += 1
        return -1

    def _brace_end(self, i, limit):
        """`${...}`: the index after its `}`, and any substitution nested in it (`${x:-$(cmd)}` runs cmd)."""
        src = self.src
        depth = 0
        inner: list = []
        while i < limit:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            if c == "'":
                j = src.find("'", i + 1, limit)
                i = limit if j < 0 else j + 1
                continue
            special = self._special(i, limit) if c in "$`" else None
            if special is not None:
                inner.append(special[0])
                i = special[1]
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0:
                    return i + 1, inner
                depth -= 1
            i += 1
        return limit, inner


def _word_value(word):
    """The word after quote removal. A substitution keeps its source text: its RESULT is unknowable here, and its commands are walked separately."""
    return "".join(p.value for p in word.parts)


def _word_render(word):
    """The word as the prose-stripped view shows it: unquoted text and unquoted substitutions kept as written, every quoted span dropped. Matching the view is what lets `_visible` recognise a command the view already shows."""
    return "".join(p.raw for p in word.parts if p.kind not in ("sq", "dq", "ansi"))


# --------------------------------------------------------------------------- the parse ---------------------------------------------------------------------------


def _parse(toks):
    """Group a token list into `[("sep", op) | ("pipe", [element, ...])]`.

    An element is `("cmd", items)`, `("sub", list, redirs)` for `( ... )` or `("brace", list, redirs)` for `{ ...; }`. Only the structure that decides WHICH SHELL a command runs in is modelled -- a subshell, a pipeline stage, a background job -- because that is what decides whether a `cd` persists (A0 L12).
    """
    n = len(toks)
    pos = 0

    def is_word(t, text):
        return (
            isinstance(t, _Word)
            and len(t.parts) == 1
            and t.parts[0].kind == "lit"
            and t.parts[0].raw == text
        )

    def redirs():
        nonlocal pos
        out: list = []
        while pos < n and isinstance(toks[pos], _Redir):
            out.append(toks[pos])
            pos += 1
        return out

    def element(end):
        nonlocal pos
        t = toks[pos]
        if isinstance(t, _Op) and t.text == "(":
            pos += 1
            body = parse_list(")")
            return ("sub", body, redirs())
        if is_word(t, "{"):
            pos += 1
            body = parse_list("}")
            return ("brace", body, redirs())
        items: list = []
        while pos < n and not isinstance(toks[pos], _Op):
            t = toks[pos]
            if end == "}" and not items and is_word(t, "}"):
                break
            items.append(t)
            pos += 1
            # A reserved word stands at a command position, so a `(` or `{` right after one opens a group rather than ending this command.
            opens_group = pos < n and (
                (isinstance(toks[pos], _Op) and toks[pos].text == "(") or is_word(toks[pos], "{")
            )
            if (
                isinstance(t, _Word)
                and _word_value(t) in _RESERVED_PREFIX
                and len(items) == 1
                and opens_group
            ):
                break
        return ("cmd", items)

    def parse_list(end):
        nonlocal pos
        out: list = []
        while pos < n:
            t = toks[pos]
            if isinstance(t, _Op):
                if t.text == ")":
                    pos += 1
                    if end == ")":
                        return out
                    continue
                if t.text in _SEPARATORS:
                    out.append(("sep", t.text))
                    pos += 1
                    continue
                if t.text in ("|", "|&"):
                    pos += 1
                    continue
            if end == "}" and is_word(t, "}"):
                pos += 1
                return out
            stages = [element(end)]
            while pos < n and isinstance(toks[pos], _Op) and toks[pos].text in ("|", "|&"):
                pos += 1
                if pos < n and not (isinstance(toks[pos], _Op) and toks[pos].text != "("):
                    stages.append(element(end))
            out.append(("pipe", stages))
        return out

    return parse_list(None)


# --------------------------------------------------------------------------- the walk ---------------------------------------------------------------------------


class _Run:
    """One simple command bash would execute, as the walk found it."""

    __slots__ = (
        "argv",
        "canonical",
        "cwd",
        "env",
        "feed",
        "feed_cwds",
        "feed_words",
        "git_dir",
        "git_sub",
        "launch",
        "launched",
        "loop_vars",
        "name",
        "remote",
        "usage",
        "vars",
        "via",
        "writes",
        "xargs",
        "xargv",
    )

    def __init__(self, name, argv, canonical, cwd, env=None):
        self.name = name
        self.argv = argv
        self.canonical = canonical
        self.cwd = cwd
        # The variables this command's environment gets FROM THE COMMAND LINE, expanded (`_expand_word`): an `export`ed earlier statement, its own `NAME=value` prefix, an `env NAME=value` in front of it, with None for one `env -u` or `unset` removed and the `_CLEARED` key after `env -i`. What the hook's own process inherited is not here, so an absent name means "whatever the session's environment says". `gh_named_repo` reads `GH_REPO` from it (#d2d5f89d).
        self.env = env if env is not None else {}
        # The argv as bash hands it to the command (`_expand_word`): `$R` is the value an earlier statement of the same command gave R, `_UNRESOLVED` inside a word whose value cannot be known here, and an unquoted word that expands to nothing is gone. `argv` stays the quote-removed text every other reader matches on (#9de9a8e9).
        self.xargv = None
        # The walk's shell state when this command ran, `NAME -> (value, exported)` (see `_shell_builtin`); `gh_named_repo` reads it for a `GH_REPO` assigned but never exported.
        self.vars = {}
        self.git_dir = None
        self.git_sub = None
        # How the command's RESULT is consumed: "status" when its exit status decides something (`&&`, `||`, `if`/`while`/`until`/`!`, a `$?` in the next clause), "kill" when its output feeds a `kill` (`kill $(...)`, `| xargs kill`). `block_self_matching_pgrep` reads it: a self-matching `pgrep -f` only costs something when one of these is true.
        self.usage = set()
        # The files this command's own output redirects write, in order, quote-removed. `earlier_mutators` reads them: a `printf ... > msg` before a `git commit -F msg` changes what a guard judging the commit reads.
        self.writes = []
        # A LAUNCHER'S COMMANDS (#ec63ff8c): one `_Analysis` per command `npx` or `find -exec` starts (see `_launched`). Kept OFF `_Analysis.runs` so every guard walking the runs keeps reading `npx` as `npx`; `lifted_commands` and `every_run` descend into them.
        self.launched = []
        # WHERE A LAUNCHED COMMAND RUNS (#503f0ba8): a `Launch` when a launcher started this command (or one this command is nested under), else None.
        self.launch = None
        # `(destination, remote command)` when this is an `ssh` naming a remote command (`_ssh_remote`), else None. The remote command is NOT walked into `runs` or lifted into the view: it runs on another machine, and a guard judging this checkout's git or files must not read it as local. `ssh_remote_commands` hands it to the guards that police remote commands.
        self.remote = None
        # WHAT ARRIVES ON STDIN, AS TEXT (#ec63ff8c): the literal words of the pipeline stages before this command (`_stage_feed`) and its own here-string or heredoc body, None when there are none. For a command a `find -exec` runs, `find`'s own words, since `{}` is replaced by what they name. What a producer PRINTS is not computed, so every word counts. Policy stays with the guard: `xargs rm` turns this text into operands and `cat` only reads it.
        self.feed = None
        # THE WORDS xargs WOULD READ, EXACTLY, or None when they are not known (#5077391c). Only a literal producer is exact: the pipeline stage in front is an `echo` whose words carry no expansion, or the command reads its own here-string or heredoc with none. Any other producer (`find`, `git`, a group, a loop's feed) prints what this walk cannot compute, so its words are in `feed` alone, read in the fail-safe direction. Words holding a quote or a backslash are not exact either, because xargs reads quotes itself.
        self.feed_words = None
        # WHERE THE PIPE'S PRODUCER RAN (review a165575f.1): the `cwd` of every command in the stage right in front, as `cwd` reads (None for the starting directory), or None when the feed came from no such stage. `(cd src; echo f*) | xargs ...` matches `f*` in `src`, which the consumer's own `cwd` does not say.
        self.feed_cwds = None
        # The option words an `xargs` in front of this command was given, in order (`("-r",)`, `("-n", "1")`), or None when no xargs ran it. `-n`, `-L`, `-I`, `-d`, `-0` and the like change which words reach which invocation, so a reader placing the feed (`run_copies`) needs them.
        self.xargs = None
        # The prefix commands `_strip_prefixes` dropped in front of this command, in order (`("sudo", "xargs")`), plus `"find"` for a command a `find -exec` launched. A guard reads `"xargs" in run.via` to know the feed became arguments.
        self.via = ()
        # THE VARIABLES AN ENCLOSING `for`/`select` LOOP ASSIGNS (review e085085d.1 sweep): `NAME -> [word, ...]`, the list it walks, innermost loop first. `for f in .claude/settings.json; do rm "$f"; done` removes that path, and the shell state (`vars`) cannot say so, because the variable holds each word in turn. Empty outside a loop and for a loop over the positionals.
        self.loop_vars = {}


class _Analysis:
    """What one walk found: `runs` in execution order, `heredocs` read, and `writes`, every output redirect bash performs as `(operator, target)` with the target quote-removed."""

    __slots__ = ("heredocs", "names", "root", "runs", "writes")

    def __init__(self):
        self.runs: list = []
        self.heredocs: list = []
        self.writes: list = []
        # WHERE EACH RUN'S NAME SITS IN THE TEXT THAT WAS WALKED, for `_wrapper_payload` (#31ed6c5f): `(name start, name end, end of the run's last word)` for every command whose words the root lexer read (the top level and its substitutions), and for a command a launcher there starts. A run nested in a payload was lexed from another string, so it has no place in this one and is left out.
        self.names: list = []
        self.root = None


# The redirect operators that open their target for WRITING. `>|` is here because it truncates even under `set -C`, which is exactly when a guard might have assumed `>` could not (A0 L14); `>&` only when its target is a file rather than a descriptor, which `write_targets` decides.
_WRITE_OPS = frozenset((">", ">>", ">|", "&>", "&>>", "<>", ">&"))


def write_targets(cmd):
    """Every file an output redirect in `cmd` writes, in order, as bash reads it: quote-removed, and only where bash really redirects.

    A0 L14: `x->f.sh` IS a redirect in bash (the word is `x-`, then `>` opens `f.sh`), while an arrow inside a quoted span never is. A regex over the raw text can only choose one of those; the lexer knows which is which. Descriptor duplications (`2>&1`, `>&-`) are not files and are left out; `/dev/null` and friends are left in, since whether they count is the caller's policy, not grammar.
    """
    out: list[str] = []
    for op, target in _analyse(cmd).writes:
        if op == ">&" and re.match(r"^(\d+|-)$", target):
            continue
        out.append(target)
    return out


def _join_dir(cwd, arg):
    """Where `cd <arg>` lands from `cwd`, as a path string relative to the root the walk started in (None means that root)."""
    if arg.startswith("/"):
        return posixpath.normpath(arg)
    if cwd is None:
        return posixpath.normpath(arg)
    return posixpath.normpath(cwd + "/" + arg)


def _shell_payload(argv):
    """For `sh`/`bash`/... argv (the name excluded): `("c", payload)` for `-c`, `("stdin", None)` when the shell reads its script from stdin, `("file", None)` for a script operand.

    A0 L10: bash's `-c` is a FLAG, not a token that must end a bundle. It may sit anywhere in any single-dash bundle (`-ce`, `-ec`), other options may follow it (`-c -e`, `-c --`), and the payload is the first OPERAND after all of them. Quote removal has already happened by the time bash sees `'-c'`.
    """
    c_mode = False
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg in {"--", "-"}:
            k += 1
            break
        if arg.startswith("--"):
            if arg in ("--rcfile", "--init-file"):
                k += 1
            k += 1
            continue
        if len(arg) > 1 and arg[0] in "-+":
            letters = arg[1:]
            if "c" in letters and arg[0] == "-":
                c_mode = True
            if "o" in letters or "O" in letters:
                k += 1
            k += 1
            continue
        break
    if c_mode:
        return ("c", argv[k]) if k < len(argv) else ("c", None)
    if k < len(argv) and "s" not in "".join(
        a[1:] for a in argv[:k] if a.startswith("-") and not a.startswith("--")
    ):
        return ("file", None)
    return ("stdin", None)


def _strip_prefixes(words, found=None):
    """Drop reserved words, assignments and prefix commands from the front of a simple command.

    Returns `(words, prefixed)`; `words` is empty when nothing runs (a bare assignment, `command -v x`, a `for` clause). A0 L9: every one of these puts a word between the command position and the command, and every anchor in every guard stops there.

    `found`, a dict when given, receives what a prefix does to the command beyond naming it: `"chdir"`, the directory `env -C` or `sudo -D` runs it in, and `"split"`, the string `env -S` splits into the command itself (then the words returned are its trailing arguments).
    """
    prefixed = False
    k = 0
    while k < len(words) and _word_value(words[k]) in _RESERVED_PREFIX:
        prefixed = True
        k += 1
    if k < len(words) and _word_value(words[k]) == "time":
        prefixed = True
        k += 1
        while k < len(words) and _word_value(words[k]) in ("-p", "--"):
            k += 1
    while k < len(words) and _ASSIGNMENT.match(_word_value(words[k])):
        prefixed = True
        k += 1
    while k < len(words):
        name = _word_value(words[k])
        if name in _NOT_A_COMMAND:
            return [], prefixed
        if name not in _PREFIX_COMMANDS:
            break
        if name == "command" and any(_word_value(w) in ("-v", "-V") for w in words[k + 1 : k + 3]):
            return [], prefixed
        prefixed = True
        k += 1
        while k < len(words):
            arg = _word_value(words[k])
            if arg == "--":
                k += 1
                break
            if name == "env" and _ASSIGNMENT.match(arg):
                k += 1
                continue
            if arg.startswith("-") and len(arg) > 1:
                used, option, value = _prefix_option(
                    name, [_word_value(w) for w in words[k : k + 2]], 0
                )
                if found is not None and name == "xargs":
                    found.setdefault("xargs", []).extend(
                        _word_value(w) for w in words[k : k + used]
                    )
                if found is not None and value is not None:
                    if (name, option) in _PREFIX_CHDIR:
                        found["chdir"] = value
                    elif (name, option) in _PREFIX_SPLIT:
                        found["split"] = value
                k += used
                continue
            break
        if found is not None and name == "xargs":
            found.setdefault("xargs", [])
        if name in _PREFIX_OPERAND and k < len(words):
            k += 1
    return words[k:], prefixed


# --------------------------------------------------------------------------- the environment a command runs with (#d2d5f89d) ---------------------------------------------------------------------------
#
# A VARIABLE IN A COMMAND'S ENVIRONMENT CAN CHOOSE WHAT IT ACTS ON as surely as a flag can: `GH_REPO=rediacc/renet gh pr create` is a create on renet, exactly as `--repo rediacc/renet` is, and a guard that reads only the flag judged it as a console create (measured 2026-10-07, block_nondraft_pr_create rc=2 against the flag's rc=0). So the walk records, per command, the variables the
# command line itself hands it: a `NAME=value` prefix (that command only), `env NAME=value` / `env -u NAME` / `env -i` in front of it, and the statements that persist like a `cd` does: `export NAME=value`, `declare -x`/`typeset -x`, a bare `NAME=value` once NAME is exported, and `unset NAME`. A subshell, a pipeline stage or a substitution sees a copy; `sh -c` and a shell reading stdin see only the
# exported ones; `eval` shares the shell. The shell state is a dict `NAME -> (value, exported)` and is never mutated in place, so a copy is just the same reference in a new state list.
#
# WHAT A NAME ABSENT FROM THE STATE MEANS, and the three values that are not text (#9de9a8e9). Absent is "whatever the session's environment holds", which this walk cannot see. `None` is KNOWN unset (`unset NAME`, `env -u NAME`), so it shadows the session's value rather than deferring to it. `_INHERITED` is a name the command exported without giving it a value (`export GH_REPO`): the session's value, now exported. `exported` is
# True or False when the command line said so, and None when it never did (a bare `NAME=value` on a name the session may already export, as bash marks every inherited variable exported). A value containing `_UNRESOLVED` came from something this walk cannot evaluate: a `$(...)`, an unassigned `$NAME`, an expansion bash would split.
#
# WHAT A WORD EXPANDS TO. `-R $R` names the repository `$R` holds, and the quote-removed text is the three characters `$R`: measured 2026-10-07, `R=rediacc/renet; gh pr create -R $R -t x` was judged as a create on a repository called "$R", which no guard polices, so each of them let it through. `_expand_word` performs bash's parameter expansion over the walk's own state: `$NAME` and `${NAME}`, quoted or not, the value an earlier statement of the same
# command assigned. Everything it cannot know (a substitution, `${NAME:-x}`, a positional, a name assigned nowhere in the command) becomes `_UNRESOLVED`, so a caller can tell "names nothing" from "names something this hook cannot see" and refuse the second. Assignments expand left to right (`A=1 B=$A` gives B "1"), and a command's arguments expand BEFORE its own prefix assignments apply (`R=x gh -R $R` names the old R): both measured on bash 5.

_UNRESOLVED = "\x00unresolved\x00"
_INHERITED = "\x00inherited\x00"
# The key `env -i` leaves in a command's environment: an absent name then means "absent", not "the session's".
_CLEARED = ""
# What `gh_named_repo` answers for a repository it cannot know. Not an `OWNER/REPO`, so no glob of one matches it; every consumer says what it means for that guard (`tests/test_gh_flag_spellings.py::CONSUMERS`).
UNRESOLVED_REPO = "<unresolved>"

_PARAM_REF = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|[0-9@*#?$!-])")
_BRACED_NAME = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
# An unquoted expansion carrying one of these is split into several words or globbed against the filesystem; neither is a value this walk can name.
_SPLITS = " \t\n*?["


def unresolved(value):
    """Whether an expanded value carries something the walk could not evaluate."""
    return value is not None and _UNRESOLVED in value


def _append(old, value):
    """`NAME+=value` over an old value: an absent or inherited one is the session's, which this walk cannot know."""
    if old is None:
        return value
    if old == _INHERITED:
        return _UNRESOLVED + value
    return old + value


def _var(name, shell):
    value = shell.get(name, (_INHERITED, None))[0]
    if value is None:
        return ""
    if value == _INHERITED:
        return _UNRESOLVED
    return value


def _expand_text(text, shell, pieces):
    """`$NAME` references in literal text, each value also appended to `pieces`."""

    def one(m):
        value = _var(m.group(1), shell) if m.group(1) else _UNRESOLVED
        pieces.append(value)
        return value

    return _PARAM_REF.sub(one, text)


def _expand_param(raw, shell):
    m = _BRACED_NAME.match(raw)
    return _var(m.group(1), shell) if m else _UNRESOLVED


def _expand_word(word, shell, split=True):
    """What bash hands a command for `word` under the walk's shell state `shell`. None when an unquoted word expands to nothing and vanishes from the argv. With `split`, a word whose unquoted expansion bash would split or glob is `_UNRESOLVED`; an assignment (`split=False`) is neither split nor globbed."""
    pieces: list[str] = []
    out = []
    quoted = False
    for part in word.parts:
        kind = part.kind
        if kind in ("sq", "ansi", "esc"):
            quoted = True
            out.append(part.value)
        elif kind == "lit":
            out.append(_expand_text(part.value, shell, pieces))
        elif kind == "param":
            value = _expand_param(part.raw, shell)
            pieces.append(value)
            out.append(value)
        elif kind == "dq":
            quoted = True
            inner: list[str] = []
            # The lexer folds `\$` inside double quotes into the literal text, so a `$` there may be an escaped one; such a string is not expanded on a guess.
            escaped = "\\$" in part.raw
            for sub in part.parts:
                if sub.kind == "lit" and escaped and "$" in sub.value:
                    out.append(_UNRESOLVED)
                elif sub.kind == "lit":
                    out.append(_expand_text(sub.value, shell, inner))
                elif sub.kind == "esc":
                    out.append(sub.value)
                elif sub.kind == "param":
                    out.append(_expand_param(sub.raw, shell))
                else:
                    out.append(_UNRESOLVED)
        else:
            out.append(_UNRESOLVED)
    text = "".join(out)
    if split and any(ch in piece for piece in pieces for ch in _SPLITS):
        return _UNRESOLVED
    if split and text == "" and not quoted and pieces:
        return None
    return text


def _assignment(text):
    """`(name, value, append)` for a `NAME=value` / `NAME+=value` word, None for anything else (an array element `a[1]=x` included: it can never be exported)."""
    m = _ASSIGNMENT.match(text)
    if not m or m.group(1):
        return None
    head = text[: m.end()]
    return head.rstrip("+="), text[m.end() :], head.endswith("+=")


def _call_env(words, shell=None):
    """What a simple command's own words do to the environment of the command it runs: `(statement, ops)`.

    `ops` are `("set", name, value, append)`, `("unset", name)` and `("clear",)`, in order: the leading assignments, then those of an `env` prefix command (`env -u NAME`, `--unset=NAME`, `-i`). `statement` is True when the words are ONLY assignments, a bare `NAME=value` that sets a shell variable and runs nothing. Mirrors `_strip_prefixes`, which decides what the command is.

    With `shell` (the walk's state), each value is EXPANDED (`_expand_word`), the leading assignments left to right so a later one sees an earlier one, as bash assigns them; without it the values are the quote-removed text.
    """
    vals = [_word_value(w) for w in words]
    ops: list[tuple] = []
    k = 0
    while k < len(vals) and vals[k] in _RESERVED_PREFIX:
        k += 1
    if k < len(vals) and vals[k] == "time":
        k += 1
        while k < len(vals) and vals[k] in ("-p", "--"):
            k += 1
    start = k
    scope = dict(shell) if shell is not None else None
    while k < len(vals) and _ASSIGNMENT.match(vals[k]):
        hit = _assignment(vals[k] if scope is None else _expand_word(words[k], scope, split=False))
        if hit:
            ops.append(("set", *hit))
            if scope is not None:
                name, value, append = hit
                old, exp = scope.get(name, (_INHERITED, None))
                scope[name] = (_append(old, value) if append else value, exp)
        k += 1
    if k == len(vals):
        return k > start, ops
    while k < len(vals) and vals[k] in _PREFIX_COMMANDS:
        name = vals[k]
        k += 1
        while k < len(vals):
            arg = vals[k]
            if arg == "--":
                k += 1
                break
            if name == "env":
                hit = _assignment(
                    arg if shell is None else (_expand_word(words[k], shell, split=False) or "")
                )
                if hit:
                    ops.append(("set", *hit))
                    k += 1
                    continue
                if arg in ("-i", "--ignore-environment"):
                    ops.append(("clear",))
                    k += 1
                    continue
                if arg in ("-u", "--unset") and k + 1 < len(vals):
                    ops.append(("unset", vals[k + 1]))
                    k += 2
                    continue
                if arg.startswith("--unset="):
                    ops.append(("unset", arg[len("--unset=") :]))
                    k += 1
                    continue
                if re.match(r"^-[0iv]*u.", arg):
                    ops.append(("unset", arg.split("u", 1)[1]))
                    k += 1
                    continue
                if re.match(r"^-[0v]*i[0v]*$", arg):
                    ops.append(("clear",))
                    k += 1
                    continue
            if arg.startswith("-") and len(arg) > 1:
                k += _prefix_option(name, vals, k)[0]
                continue
            break
        if name in _PREFIX_OPERAND and k < len(vals):
            k += 1
    return False, ops


def _exported(shell):
    """`{NAME: value}` of what a child process inherits from the command line: the exported variables, and None for each KNOWN-unset one (it shadows the session's value as surely as an export does)."""
    return {n: v for n, (v, exp) in shell.items() if exp or v is None}


def _apply_env(env, ops):
    """`env` (a `{NAME: value}`) with `_call_env`'s ops applied, as a new dict. `env -i` leaves the `_CLEARED` key, so an absent name after it is absent rather than the session's."""
    out = dict(env)
    for op in ops:
        if op[0] == "clear":
            out = {_CLEARED: ""}
        elif op[0] == "unset":
            out[op[1]] = None
        else:
            _, name, value, append = op
            if append:
                old = out.get(name, "" if _CLEARED in out else _INHERITED)
                value = _append(old, value)
            out[name] = value
    return out


# Attributes after which a variable's value is not the text assigned: an array, a nameref, an integer.
_NOT_TEXT = frozenset("aAni")
# The builtins that set, export or unset a shell variable.
_DECLARING = frozenset(("export", "declare", "typeset", "local", "readonly", "unset"))


def _shell_builtin(base, argv, shell):
    """The shell state after `export`, `declare`/`typeset`/`local`/`readonly` or `unset` with `argv` (already expanded, `split=False`), as a new dict; `shell` itself when `base` is none of them.

    `export -n`, `declare +x` and `local` without `-x` leave a name unexported; `declare` and `readonly` without either keep its export state, which is None (unknown) for a name the command never exported. `unset NAME` records it KNOWN unset rather than forgetting it, so the session's value no longer stands behind it.
    """
    if base not in _DECLARING:
        return shell
    letters = "".join(a[1:] for a in argv if a.startswith("-") and len(a) > 1 and a != "--")
    plus = "".join(a[1:] for a in argv if a.startswith("+") and len(a) > 1)
    names = [a for a in argv if not (a[:1] in "-+" and len(a) > 1)]
    out = dict(shell)
    if base == "unset":
        if "f" in letters:
            return shell
        for name in names:
            out[name] = (None, False)
        return out
    if "f" in letters or "F" in letters:
        return shell
    if base == "export":
        exported = "n" not in letters
    elif "x" in letters:
        exported = True
    elif "x" in plus or base == "local":
        exported = False
    else:
        exported = None
    for arg in names:
        hit = _assignment(arg)
        if hit:
            name, value, append = hit
            old, was = out.get(name, (_INHERITED, None))
            if _NOT_TEXT & set(letters):
                value = _UNRESOLVED
            elif append:
                value = _append(old, value)
            out[name] = (value, was if exported is None else exported)
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", arg):
            old, was = out.get(arg, (_INHERITED, None))
            if base == "local":
                old = None
            out[arg] = (old, was if exported is None else exported)
    return out


# git's global options that take the NEXT word as their value (`git --help`, git.c `handle_options`, git 2.53.0). `--attr-source <tree>` was missing from both copies of this list until 2026-10-07 (#d5d33bee): `git --attr-source HEAD commit` commits, and the walk read `HEAD` as the subcommand, so no commit guard saw the commit. `--exec-path` without `=` prints a path and exits, so the word after it never runs.
GIT_GLOBAL_WITH_VALUE = frozenset(
    (
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--super-prefix",
        "--config-env",
        "--exec-path",
        "--attr-source",
    )
)


def _git_invocation(argv, cwd):
    """`(subcommand, directory)` for a `git` argv: every `-C` before the subcommand composes onto the current directory, the way git applies them."""
    here = cwd
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg == "-C" and k + 1 < len(argv):
            here = _join_dir(here, argv[k + 1])
            k += 2
            continue
        if arg in GIT_GLOBAL_WITH_VALUE and k + 1 < len(argv):
            k += 2
            continue
        if arg.startswith("-"):
            k += 1
            continue
        return arg, here
    return "", here


def _base(name):
    return name.rsplit("/", 1)[-1]


# A LOOP'S STDIN IS WHAT ITS `done` REDIRECTS, AND WHAT FEEDS THE LOOP FEEDS ITS BODY (review e085085d.1). `while read f; do rm "$f"; done <<< .claude/settings.json` deletes the file: bash applies the redirect after `done` to the whole compound command, condition and body. The parse keeps `while`, `do` and `done` as words in front of commands rather than as a structure, so that redirect sat on a
# command that runs nothing and reached no command's feed, and a loop on the consumer side of a pipe fed only its condition (`echo x | while true; do xargs rm; done` ran an unfed `xargs`). `_loop_word` reads the keywords a command starts with; `_Walker.items` opens a frame at each loop keyword and, at the matching `done`, hands every command walked inside it the frame's feed (the pipeline in front of the opener and the
# `done`'s own here-string, heredoc or `< <(...)`) and the variable a `for`/`select` assigns. A loop that never reaches its `done` is a syntax error bash runs nothing of, so an unclosed frame hands nothing on.
_LOOP_OPENERS = frozenset(("while", "until", "for", "select"))


def _loop_word(stage):
    """`[("open", binding) | ("close", None), ...]` for the loop keywords a pipeline stage starts with, in order. `binding` is `(name, [word, ...])` for `for NAME in WORDS`/`select NAME in WORDS`, else None."""
    if stage[0] != "cmd":
        return []
    words = [t for t in stage[1] if isinstance(t, _Word)]
    out: list = []
    for k, word in enumerate(words):
        value = _word_value(word)
        if value == "done":
            out.append(("close", None))
        elif value in ("for", "select"):
            rest = [_word_value(w) for w in words[k + 1 :]]
            binding = None
            if len(rest) >= 2 and rest[1] == "in":
                binding = (rest[0], rest[2:])
            out.append(("open", binding))
            break
        elif value in _LOOP_OPENERS:
            out.append(("open", None))
        elif value not in _RESERVED_PREFIX:
            break
    return out


def _runs_within(runs):
    for run in runs:
        yield run
        for sub in run.launched:
            yield from _every_run(sub)


def _reads_status(item):
    """Whether a parsed list item reads `$?` anywhere in its own words: the clause after `pgrep ...;` that tests what it returned."""
    if item[0] != "pipe":
        return False
    for stage in item[1]:
        if stage[0] != "cmd":
            continue
        for tok in stage[1]:
            if isinstance(tok, _Word) and "$?" in "".join(p.raw for p in tok.parts):
                return True
    return False


class _Walker:
    def __init__(self, analysis, depth):
        self.analysis = analysis
        self.depth = depth

    def text(self, src, cwd, persist, shell=None):
        """Walk a command string. `persist` says whether a `cd` or an `export` in it outlives it (an `eval` does; a `sh -c` does not). Returns `(cwd, shell)` as they stand after it.

        The walk's state is a two-slot list, `[cwd, shell]`: the directory (`cd`) and the shell variables (`_shell_builtin`), both of which a statement changes for the statements after it.
        """
        shell = shell if shell is not None else {}
        if self.depth >= _MAX_DEPTH or src == "":
            return cwd, shell
        lexer = _Lexer(src)
        toks = lexer.tokens()
        if self.depth == 0:
            self.analysis.root = lexer
        self.analysis.heredocs.extend(lexer.heredocs)
        inner = _Walker(self.analysis, self.depth + 1)
        state = [cwd, shell]
        inner.items(_parse(toks), state, lexer)
        return (state[0], state[1]) if persist else (cwd, shell)

    def items(self, items, state, lexer, inherited=None):
        """Walk a parsed list. `inherited` is the text a group's stdin carries (`echo x | (xargs rm)`), handed to every command in it."""
        runs = self.analysis.runs
        # The loops open at this level, innermost last: `[first run index, the feed in front of the opener, binding]`.
        loops: list = []
        for idx, item in enumerate(items):
            if item[0] == "sep":
                continue
            stages = item[1]
            background = idx + 1 < len(items) and items[idx + 1] == ("sep", "&")
            isolated = len(stages) > 1 or background
            # A pipeline's status is its LAST stage's, and it is consumed when an `&&`/`||` follows it or the next clause reads `$?`.
            follow = (
                items[idx + 1][1] if idx + 1 < len(items) and items[idx + 1][0] == "sep" else None
            )
            tested = follow in ("&&", "||") or (
                follow in (";", "\n") and idx + 2 < len(items) and _reads_status(items[idx + 2])
            )
            spans = []
            for pos, stage in enumerate(stages):
                own = [state[0], state[1]] if isolated else state
                start = len(runs)
                keywords = _loop_word(stage)
                for kind, binding in keywords:
                    if kind == "open":
                        before = [inherited or ""] + [_stage_feed(p, lexer) for p in stages[:pos]]
                        loops.append([start, " ".join(f for f in before if f), binding])
                self.element(
                    stage,
                    own,
                    lexer,
                    stages[pos - 1] if pos else None,
                    tested=tested and pos == len(stages) - 1,
                    producers=stages[:pos],
                    inherited=inherited,
                )
                for kind, _binding in keywords:
                    if kind == "close" and loops:
                        first, fed, binding = loops.pop()
                        own_feed = [
                            _redir_feed(t, lexer) for t in stage[1] if isinstance(t, _Redir)
                        ]
                        fed = " ".join(f for f in [fed, *own_feed] if f)
                        for inner in _runs_within(runs[first:start]):
                            if fed and fed not in (inner.feed or ""):
                                inner.feed = " ".join(f for f in (inner.feed, fed) if f)
                                inner.feed_words = None
                            if binding is not None:
                                inner.loop_vars.setdefault(binding[0], binding[1])
                spans.append((start, len(runs)))
            # The producer's directories reach every command of the stage it feeds, read where its globs are matched (`run_copies`).
            for pos in range(1, len(spans)):
                producer = tuple(
                    dict.fromkeys(r.cwd for r in runs[spans[pos - 1][0] : spans[pos - 1][1]])
                )
                for r in runs[spans[pos][0] : spans[pos][1]]:
                    if r.feed_cwds is None and producer:
                        r.feed_cwds = producer
            # `pgrep -f x | xargs kill`: a later stage that kills consumes every earlier stage's output as pids.
            for pos in range(1, len(spans)):
                if any(_base(r.name) == "kill" for r in runs[spans[pos][0] : spans[pos][1]]):
                    for r in runs[spans[0][0] : spans[pos][0]]:
                        r.usage.add("kill")

    def element(self, stage, state, lexer, upstream, tested=False, producers=(), inherited=None):
        kind = stage[0]
        if kind in ("sub", "brace"):
            # A GROUP'S STDIN IS EVERY MEMBER'S (#31ed6c5f). `echo .claude/settings.json | (xargs rm)` and `| { xargs rm; }` delete the file exactly as `| xargs rm` does, and the feed used to stop at the group, so both were allowed (rc 0, 2026-10-09). The earlier stages' words and the group's own here-string or heredoc reach every command inside it, whatever its own pipeline puts in front, the over-reading direction (what a stage prints is not computed).
            fed = " ".join(
                f
                for f in [inherited or ""]
                + [_stage_feed(p, lexer) for p in producers]
                + [_redir_feed(r, lexer) for r in stage[2]]
                if f
            )
            self.items(
                stage[1], [state[0], state[1]] if kind == "sub" else state, lexer, fed or None
            )
            self.redirs(stage[2], state, lexer)
            return
        words = [t for t in stage[1] if isinstance(t, _Word)]
        redirs = [t for t in stage[1] if isinstance(t, _Redir)]
        first_inner = len(self.analysis.runs)
        for word in words:
            self.parts(word.parts, state, lexer)
        first_write = len(self.analysis.writes)
        self.redirs(redirs, state, lexer)
        own_writes = [
            target
            for op, target in self.analysis.writes[first_write:]
            if not (op == ">&" and re.match(r"^(\d+|-)$", target))
        ]
        # `if pgrep ...`, `while ! pgrep ...`: a leading condition keyword means this command's status decides something.
        lead = []
        for word in words:
            value = _word_value(word)
            if value not in _RESERVED_PREFIX:
                break
            lead.append(value)
        # The state the words EXPAND under: a command's arguments are expanded before its own prefix assignments apply.
        before = state[1]
        statement, env_ops = _call_env(words, before)
        if statement:
            # A bare `NAME=value` sets a shell variable; it reaches a child's environment only when NAME is exported (or, export state unknown, when the session already exports it: `gh_named_repo`).
            shell = dict(before)
            for _, var, value, append in env_ops:
                old, exp = shell.get(var, (_INHERITED, None))
                shell[var] = (_append(old, value) if append else value, exp)
            state[1] = shell
        prefix_words = words
        found: dict = {}
        words, _prefixed = _strip_prefixes(words, found)
        if "split" in found:
            # `env -S "rm x" y` runs `rm x y`: the string is split into the command, the words after it are its arguments.
            rest = _quote_argv([_word_value(w) for w in words])
            self.nested(" ".join(f for f in (found["split"], rest) if f), state[0], False, state[1])
            return
        if not words:
            return
        via = tuple(
            _base(_word_value(w))
            for w in prefix_words[: len(prefix_words) - len(words)]
            if _base(_word_value(w)) in _PREFIX_COMMANDS
        )
        name = _word_value(words[0])
        if name == "" or any(ch in name for ch in " \t\n"):
            return
        argv = [_word_value(w) for w in words[1:]]
        rendered = [r for r in (_word_render(w) for w in words[1:]) if r != ""]
        run = _Run(
            name,
            argv,
            " ".join([name, *rendered]),
            _join_dir(state[0], found["chdir"]) if "chdir" in found else state[0],
            _apply_env(_exported(before), env_ops),
        )
        run.xargv = [x for x in (_expand_word(w, before) for w in words[1:]) if x is not None]
        run.vars = before
        run.writes = own_writes
        if tested or any(w in ("if", "elif", "while", "until", "!") for w in lead):
            run.usage.add("status")
        base = name.rsplit("/", 1)[-1]
        # `kill $(pgrep -f x)`: the substitutions in a kill's own words produced its pids.
        if base == "kill":
            for inner in self.analysis.runs[first_inner:]:
                inner.usage.add("kill")
        run.via = via
        feed = [
            f
            for f in [inherited or ""]
            + [_stage_feed(p, lexer) for p in producers]
            + [_redir_feed(r, lexer) for r in redirs]
            if f
        ]
        if feed:
            run.feed = " ".join(feed)
            if not inherited:
                run.feed_words = _literal_feed(producers, redirs, lexer)
        if "xargs" in found:
            run.xargs = tuple(found["xargs"])
        self.analysis.runs.append(run)
        at_root = lexer is self.analysis.root
        if at_root:
            self.analysis.names.append((words[0].start, words[0].end, words[-1].end))
        for how, launched, launch, span in _launches(base, argv):
            if at_root and span is not None:
                first, last = words[1 + span[0]], words[1 + span[1]]
                self.analysis.names.append((first.start, first.end, last.end))
            sub = _Analysis()
            src = launched if how == "text" else _quote_argv(launched)
            _Walker(sub, self.depth + 1).text(src, state[0], persist=False, shell=state[1])
            if base == "find":
                for inner_run in sub.runs:
                    inner_run.via = (*inner_run.via, "find")
                    inner_run.feed = " ".join(f for f in (inner_run.feed, " ".join(argv)) if f)
                    inner_run.feed_words = None
            # The innermost launcher names the run; an outer `elsewhere` still holds for everything nested under it (`find -execdir npx -c '...'`).
            for inner_run in _every_run(sub):
                if inner_run.launch is None:
                    inner_run.launch = launch
                elif launch.elsewhere and not inner_run.launch.elsewhere:
                    inner_run.launch = inner_run.launch._replace(elsewhere=True)
            run.launched.append(sub)
        if base == "ssh":
            run.remote = _ssh_remote(argv)
        if base in ("cd", "pushd"):
            operands = [a for a in argv if not (a.startswith("-") and len(a) > 1)]
            # `cd` with no operand, `cd -` and `cd ~` land somewhere this walk cannot name; an unresolvable directory makes every caller keep judging its own root, the direction the guards fail safe in.
            target = operands[0] if operands else "~"
            state[0] = _join_dir(state[0], target)
        elif base == "git":
            run.git_sub, run.git_dir = _git_invocation(argv, state[0])
        elif base == "eval":
            state[0], state[1] = self.nested(" ".join(argv), state[0], persist=True, shell=state[1])
        elif base in SHELL_NAMES:
            # A child shell inherits the environment, never the parent's unexported variables; a KNOWN-unset name stays known unset there.
            child = {n: (v, v is not None) for n, v in run.env.items()}
            mode, payload = _shell_payload(argv)
            if mode == "c" and payload is not None:
                self.nested(payload, state[0], persist=False, shell=child)
            elif mode == "stdin":
                self.stdin(redirs, lexer, [state[0], child], upstream)
        elif base in _DECLARING:
            declared = [_expand_word(w, before, split=False) or "" for w in words[1:]]
            state[1] = _shell_builtin(base, declared, state[1])

    def stdin(self, redirs, lexer, state, upstream):
        """A shell reading its script from stdin runs whatever arrives there (A0 L4): a heredoc body, a here-string, or the output of `cat <<EOF`/`echo` upstream in the pipe. `state` is the child shell's `[cwd, shell]`."""
        for redir in redirs:
            if redir.heredoc is not None and redir.heredoc.body_start is not None:
                hd = redir.heredoc
                self.nested(
                    lexer.src[hd.body_start : hd.body_end], state[0], persist=False, shell=state[1]
                )
            elif redir.op == "<<<" and redir.target is not None:
                self.nested(_word_value(redir.target), state[0], persist=False, shell=state[1])
        if upstream is None or upstream[0] != "cmd":
            return
        words, _ = _strip_prefixes([t for t in upstream[1] if isinstance(t, _Word)])
        if not words:
            return
        feeder = _word_value(words[0]).rsplit("/", 1)[-1]
        if feeder == "cat":
            ups = [t for t in upstream[1] if isinstance(t, _Redir)]
            for redir in ups:
                if redir.heredoc is not None and redir.heredoc.body_start is not None:
                    hd = redir.heredoc
                    self.nested(
                        lexer.src[hd.body_start : hd.body_end],
                        state[0],
                        persist=False,
                        shell=state[1],
                    )
                elif redir.op == "<<<" and redir.target is not None:
                    self.nested(_word_value(redir.target), state[0], persist=False, shell=state[1])
        elif feeder in ("echo", "printf"):
            args = [_word_value(w) for w in words[1:]]
            while args and feeder == "echo" and re.match(r"^-[neE]+$", args[0]):
                args = args[1:]
            self.nested(" ".join(args), state[0], persist=False, shell=state[1])

    def nested(self, src, cwd, persist, shell=None):
        return _Walker(self.analysis, self.depth + 1).text(src, cwd, persist, shell)

    def redirs(self, redirs, state, lexer):
        for redir in redirs:
            if redir.target is not None:
                self.parts(redir.target.parts, state, lexer)
                # `> >(tee x)` writes into a command, not a file; that command is walked like any other.
                if redir.op in _WRITE_OPS and _procsub(redir.target) is None:
                    self.analysis.writes.append((redir.op, _word_value(redir.target)))
            if redir.heredoc is not None:
                self.parts(redir.heredoc.substs, state, lexer)

    def parts(self, parts, state, lexer):
        """Every substitution inside a word runs, in a subshell of its own (so a `cd` inside it never persists).

        A substitution was tokenised by the SAME lexer as the text around it, so its heredoc offsets index `lexer.src` and a `bash <<EOF` inside a `$(...)` still finds its body.
        """
        for part in parts:
            if part.sub is not None and self.depth < _MAX_DEPTH:
                inner = _Walker(self.analysis, self.depth + 1)
                inner.items(_parse(part.sub), [state[0], state[1]], lexer)
            if part.parts:
                self.parts(part.parts, state, lexer)


_ANALYSIS_CACHE: dict = {}


def _analyse(cmd):
    """Walk `cmd` once and remember the answer: every guard in a chain asks about the same command, and the walk is a pure function of the string."""
    hit = _ANALYSIS_CACHE.get(cmd)
    if hit is not None:
        return hit
    analysis = _Analysis()
    _Walker(analysis, 0).text(cmd, None, persist=True)
    if len(_ANALYSIS_CACHE) > 64:
        _ANALYSIS_CACHE.clear()
    _ANALYSIS_CACHE[cmd] = analysis
    return analysis


# --------------------------------------------------------------------------- lifting ---------------------------------------------------------------------------

_ANCHOR_CHARS = ";&|(`"


def _collapse(text):
    return re.sub(r"[ \t]+", " ", text).strip(" \t")


def _anchored_segments(view):
    """Every tail of `view` that starts at a command position as the NARROWEST guard anchor sees one: a line start, or just after `;`, `&`, `|` or `(`.

    Narrowest on purpose, and the backtick is left out for that reason: `block_git_force_push` anchors on `(^|[;&|(])`, so a push reachable only behind a backtick (`` x=`git push --force` ``) is invisible to it and has to be lifted onto a line of its own.
    """
    out: list[str] = []
    for record in view.split("\n"):
        out.append(_collapse(record))
        out.extend(_collapse(record[m.end() :]) for m in re.finditer(r"[;&|(]", record))
    return out


def _visible(canonical, segments):
    cut = canonical
    for ch in _ANCHOR_CHARS:
        at = cut.find(ch)
        if at >= 0:
            cut = cut[:at]
    cut = _collapse(cut)
    if cut == "":
        return True
    for seg in segments:
        if seg.startswith(cut) and (len(seg) == len(cut) or seg[len(cut)] in " ;&|()`<>"):
            return True
    return False


def _every_run(analysis):
    for run in analysis.runs:
        yield run
        for sub in run.launched:
            yield from _every_run(sub)


def every_run(cmd):
    """`_analyse(cmd).runs` plus every command a launcher among them starts (`_Run.launched`), each right after its launcher: `npx node x.js` yields the `npx` run and then the `node` run. For a guard that wants the launched commands too; the plain `runs` list leaves them out on purpose (see `_launched`)."""
    return list(_every_run(_analyse(cmd)))


# --------------------------------------------------------------------------- where a copy lands (review cac47d16.1) ---------------------------------------------------------------------------
#
# A COPY'S DESTINATION IS getopt's ANSWER, NOT THE LAST WORD. Two guards read `operands[-1]` (at three sites) of a `cp`/`mv`/`install`/`ln`/`rsync` as the place it writes, with `operands` every word not starting with a dash. GNU's target option names the directory instead and makes every operand a source, so `cp -t .claude/commands src/x.md` left `src/x.md` last and a flagged copy into a command
# directory was allowed; GNU getopt also PERMUTES, so a value option written after the operands (`cp src .claude/commands/ -S .bak`) put its value last. `copy_destination` reads the argv the way each tool's own parser does: its value-taking short letters, its long options with their argument kind and getopt_long's unique-prefix rule, `--` ending options. The tables are
# coreutils 9.7's and rsync 3.4.1's `--help` (rsync parses with popt, which has no `-t` target option and no abbreviations; its `-t` keeps times). An option a table does not list is read as taking no value, so a word after it stays an operand and is still judged.
_COPY_SHORT_VALUES = {"cp": "St", "mv": "St", "install": "gmoSt", "ln": "St", "rsync": "BefTM@"}
_COPY_LONG = {
    "cp": {
        "no-preserve": "r",
        "sparse": "r",
        "suffix": "r",
        "target-directory": "r",
        "backup": "o",
        "context": "o",
        "preserve": "o",
        "reflink": "o",
        "update": "o",
        **dict.fromkeys(
            [
                "archive",
                "attributes-only",
                "copy-contents",
                "debug",
                "dereference",
                "force",
                "help",
                "interactive",
                "keep-directory-symlink",
                "link",
                "no-clobber",
                "no-dereference",
                "no-target-directory",
                "one-file-system",
                "parents",
                "recursive",
                "remove-destination",
                "strip-trailing-slashes",
                "symbolic-link",
                "verbose",
                "version",
            ],
            "n",
        ),
    },
    "mv": {
        "suffix": "r",
        "target-directory": "r",
        "backup": "o",
        "update": "o",
        **dict.fromkeys(
            [
                "context",
                "debug",
                "exchange",
                "force",
                "help",
                "interactive",
                "no-clobber",
                "no-copy",
                "no-target-directory",
                "strip-trailing-slashes",
                "verbose",
                "version",
            ],
            "n",
        ),
    },
    "install": {
        "group": "r",
        "mode": "r",
        "owner": "r",
        "strip-program": "r",
        "suffix": "r",
        "target-directory": "r",
        "backup": "o",
        "context": "o",
        **dict.fromkeys(
            [
                "compare",
                "directory",
                "help",
                "no-target-directory",
                "preserve-context",
                "preserve-timestamps",
                "strip",
                "unprivileged",
                "verbose",
                "version",
            ],
            "n",
        ),
    },
    "ln": {
        "suffix": "r",
        "target-directory": "r",
        "backup": "o",
        **dict.fromkeys(
            [
                "force",
                "help",
                "interactive",
                "logical",
                "no-dereference",
                "no-target-directory",
                "physical",
                "relative",
                "symbolic",
                "verbose",
                "version",
            ],
            "n",
        ),
    },
    "rsync": dict.fromkeys(
        [
            "info",
            "debug",
            "stderr",
            "backup-dir",
            "suffix",
            "chmod",
            "checksum-choice",
            "block-size",
            "rsh",
            "rsync-path",
            "max-delete",
            "max-size",
            "min-size",
            "max-alloc",
            "partial-dir",
            "usermap",
            "groupmap",
            "chown",
            "timeout",
            "contimeout",
            "modify-window",
            "temp-dir",
            "compare-dest",
            "copy-dest",
            "link-dest",
            "compress-choice",
            "compress-level",
            "skip-compress",
            "filter",
            "exclude",
            "exclude-from",
            "include",
            "include-from",
            "files-from",
            "copy-as",
            "address",
            "port",
            "sockopts",
            "outbuf",
            "remote-option",
            "out-format",
            "log-file",
            "log-file-format",
            "password-file",
            "early-input",
            "bwlimit",
            "stop-after",
            "stop-at",
            "write-batch",
            "only-write-batch",
            "read-batch",
            "protocol",
            "iconv",
            "checksum-seed",
        ],
        "r",
    ),
}
COPIERS = tuple(_COPY_SHORT_VALUES)


def _copy_long(table, name, abbreviations):
    """`(canonical name, argument kind)` for a long option as getopt_long resolves it: an exact name, else a unique prefix. An unknown or ambiguous name is read as taking no value."""
    if name in table:
        return name, table[name]
    if abbreviations:
        hits = [full for full in table if full.startswith(name)]
        if len(hits) == 1:
            return hits[0], table[hits[0]]
    return name, "n"


def copy_destination(name, argv):
    """`(sources, destination, into)` for a `cp`/`mv`/`install`/`ln`/`rsync` argv (the command name excluded), or None when the command copies nothing onto a path. `into` is True when the destination is a directory by the command's own spelling, so each source lands inside it under its own name.

    A target-directory option (`-t DIR`, `-tDIR`, a bundle ending in `t`, `--target-directory=DIR`, `--target-directory DIR`, or a unique prefix of it) names the destination, and then every operand is a source. Otherwise the destination is the last operand. `ln` with one operand links it into the current directory, so its destination is `.`. `install -d` creates directories and copies nothing.
    """
    base = name.rsplit("/", 1)[-1]
    if base not in _COPY_SHORT_VALUES:
        return None
    short_values = _COPY_SHORT_VALUES[base]
    table = _COPY_LONG[base]
    abbreviations = base != "rsync"
    operands: list[str] = []
    target = None
    creates_dirs = False
    k = 0
    while k < len(argv):
        arg = argv[k]
        k += 1
        if arg == "--":
            operands.extend(argv[k:])
            break
        if arg.startswith("--"):
            key, eq, value = arg[2:].partition("=")
            full, kind = _copy_long(table, key, abbreviations)
            if kind == "r" and not eq and k < len(argv):
                value = argv[k]
                k += 1
            if full == "target-directory":
                target = value
            elif full == "directory" and base == "install":
                creates_dirs = True
            continue
        if arg.startswith("-") and len(arg) > 1:
            for at, letter in enumerate(arg[1:], 1):
                if base == "install" and letter == "d":
                    creates_dirs = True
                if letter not in short_values:
                    continue
                value = arg[at + 1 :]
                if not value and k < len(argv):
                    value = argv[k]
                    k += 1
                if letter == "t" and base != "rsync":
                    target = value
                break
            continue
        operands.append(arg)
    if creates_dirs:
        return None
    if target:
        return operands, target, True
    if len(operands) >= 2:
        return operands[:-1], operands[-1], False
    if base == "ln" and len(operands) == 1:
        return operands, ".", True
    return None


# The xargs option words that leave one invocation with every fed word appended last: `-r` (run nothing on empty input), `-t` (print the command), `-x` (exit on an oversized line) and their long names. Anything else (`-n`, `-L`, `-I`, `-d`, `-0`, `-P`, `-s`, `-a`, `-E`) splits, replaces, re-reads or re-delimits the feed.
_XARGS_APPENDS_ONCE = frozenset(("-r", "--no-run-if-empty", "-t", "--verbose", "-x", "--exit"))


def _appends_once(options):
    return all(o in _XARGS_APPENDS_ONCE or re.fullmatch(r"-[rtx]+", o) is not None for o in options)


# How many words one fed word may stand for before the expansion below stops; a pathological brace cannot exhaust the hook.
_FED_EXPANSION_CAP = 64


# BRACE EXPANSION, AS BASH DOES IT (reviews 8ae5b370.1, .2, .4), measured on bash 5.3 with `printf '[%s]' <word>`:
#   an unmatched `{` is literal and a later brace still expands (`x{y{a,b}` -> x{ya x{yb), and so is a matched one with neither a comma nor a range (`{b}{x,y}` -> {b}x {b}y);
#   a range is `{m..n}` or `{m..n..step}` over integers or single letters; the step's sign is ignored and 0 counts as 1 (`{1..3..-1}`, `{1..2..0}` -> 1 2 3, 1 2), a letter range walks code points across case (`{a..C}` runs through `` ` `` and `[`), and an integer range pads to the wider operand when either is written with a leading zero (`{-01..2}` -> -01 000 001 002);
#   `{1...3}`, `{ab..c}` and `{1..a}` are literal.
# GENERATED LAZILY AND CAPPED: every alternative is produced on demand and `_brace_alternatives` takes the first `_FED_EXPANSION_CAP` of the whole product, so `{1..9999999999}` or several ranges in one word cost at most that many words, never the full list.
_RANGE = re.compile(r"(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?|([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?\d+))?")
# Deep enough for any word a command line holds (each level consumes one brace pair of the word), and far below the interpreter's recursion limit; the WORD cap below is what bounds the work (review a165575f.3).
_MAX_BRACE_DEPTH = 256


def _brace_range(body):
    """A lazy iterator over a range body's words, or None when `body` is not a range bash expands."""
    m = _RANGE.fullmatch(body)
    if m is None:
        return None
    if m.group(1) is not None:
        lo_text, hi_text, step_text = m.group(1), m.group(2), m.group(3)
        lo, hi = int(lo_text), int(hi_text)
        step = abs(int(step_text)) if step_text else 1
        step = step or 1
        padded = any(re.match(r"-?0\d", t) for t in (lo_text, hi_text))
        width = max(len(lo_text), len(hi_text)) if padded else 0
        numbers = range(lo, hi + 1, step) if hi >= lo else range(lo, hi - 1, -step)
        return ("%0*d" % (width, n) for n in numbers)
    lo, hi = ord(m.group(4)), ord(m.group(5))
    step = abs(int(m.group(6))) if m.group(6) else 1
    step = step or 1
    codes = range(lo, hi + 1, step) if hi >= lo else range(lo, hi - 1, -step)
    # A letter range that passes the backslash (code point 92) makes a word of one backslash, which quote removal then empties (`{a..C}`, measured).
    return ("" if n == 92 else chr(n) for n in codes)


def _first_brace(word, start=0):
    """`(open, close, alternatives)` for the first brace bash expands in `word` at or after `start`, else None. A `{` with no matching `}`, and a matched one holding neither a top-level comma nor a range, are literal; the scan moves past them."""
    i = word.find("{", start)
    while i >= 0:
        level = 0
        commas = []
        close = -1
        for k in range(i, len(word)):
            ch = word[k]
            if ch == "{":
                level += 1
            elif ch == "}":
                level -= 1
                if level == 0:
                    close = k
                    break
            elif ch == "," and level == 1:
                commas.append(k)
        if close >= 0:
            if commas:
                cuts = [i, *commas, close]
                return i, close, (word[cuts[n] + 1 : cuts[n + 1]] for n in range(len(cuts) - 1))
            words = _brace_range(word[i + 1 : close])
            if words is not None:
                return i, close, words
        i = word.find("{", i + 1)
    return None


def _brace_words(word, start=0, depth=0):
    """Every word bash's brace expansion makes of `word`, lazily, left to right."""
    found = _first_brace(word, start) if depth < _MAX_BRACE_DEPTH else None
    if found is None:
        yield word
        return
    i, close, alternatives = found
    head, tail = word[:i], word[close + 1 :]
    for part in alternatives:
        # The head holds no brace bash expands (the scan passed it), so the rescan starts where the part does: a nested brace in the part, and every later one in the tail, are still read.
        yield from _brace_words(head + part + tail, i, depth + 1)


def _brace_expand(word):
    """`(words, truncated)`: the first `_FED_EXPANSION_CAP` non-empty words bash's brace expansion makes of `word`, empty words dropped BEFORE the cap as bash drops them (`{a,}x` -> ax x, `{,}` -> nothing, review a165575f.4), and whether more words were left."""
    if "{" not in word:
        return [word], False
    nonempty = (w for w in _brace_words(word) if w != "")
    got = list(itertools.islice(nonempty, _FED_EXPANSION_CAP + 1))
    return got[:_FED_EXPANSION_CAP], len(got) > _FED_EXPANSION_CAP


def _brace_alternatives(word):
    """The first `_FED_EXPANSION_CAP` words bash's brace expansion makes of `word` (the word itself when it has none)."""
    return _brace_expand(word)[0]


def _brace_glob(word):
    """`word` with every brace bash expands turned into `*`, a glob that matches every word those braces make: what the fail-safe reading falls back to when the cap leaves words unread (review a165575f.3)."""
    out = word
    for _ in range(_MAX_BRACE_DEPTH):
        found = _first_brace(out)
        if found is None:
            break
        i, close, _alternatives = found
        out = out[:i] + "*" + out[close + 1 :]
    return out


# Bash's glob characters; a fed word holding one is a pattern bash matches against the directory the producer runs in.
_GLOB_CHARS = frozenset("*?[")


def _glob_shape(pattern):
    """One name in the pattern's shape, for when the directory it is matched in is unknown: `*` and `?` become `x`, a bracket class its first listed character (`x` for a negated one)."""
    out = re.sub(
        r"\[(!|\^)?([^]]?[^]]*)\]",
        lambda m: "x" if m.group(1) or not m.group(2) else m.group(2)[0],
        pattern,
    )
    return out.replace("*", "x").replace("?", "x")


def _glob_forms(form, directories, uncertain=False):
    """What bash's pathname expansion makes of `form`: its matches on disk, an absolute pattern as written and a relative one in each of `directories` (review 8ae5b370.3). One name in the pattern's shape is added whenever the match is empty or the directory is `uncertain` (unknown, missing, unreadable: review a165575f.2), so a guard reading names still sees a name of that shape."""
    if not any(ch in form for ch in _GLOB_CHARS):
        return []
    if form.startswith("/"):
        found = sorted(glob.glob(form))
    else:
        found = sorted({m for d in directories for m in glob.glob(form, root_dir=d)})
    found = found[:_FED_EXPANSION_CAP]
    if uncertain or not found:
        found.append(_glob_shape(form))
    return found


def _fed_candidates(words, directory=None, uncertain=None):
    """Every word an unknown producer's text may stand for, for the fail-safe reading: each word itself, its brace alternatives (and, when the cap leaves some unread, the glob `_brace_glob` makes of the word), its tilde forms (a leading `~`, or one after `=` or `:`, as `os.path.expanduser` reads them for the user this hook runs as, who is the user bash runs as), and what a glob matches (`_glob_forms`).

    `directory` is where the producer runs: an absolute path, a list of them, or None when unknown. `uncertain`, None by default, means "uncertain exactly when no directory is given". Adding words only widens what the fail-safe reading claims.
    """
    if directory is None:
        directories: list[str] = []
    elif isinstance(directory, str):
        directories = [directory]
    else:
        directories = list(directory)
    if uncertain is None:
        uncertain = not directories
    out: list[str] = []
    for word in words:
        alternatives, truncated = _brace_expand(word)
        if truncated:
            alternatives = [*alternatives, _brace_glob(word)]
        for alt in alternatives:
            forms = [alt]
            for sep in ("=", ":"):
                head, mark, rest = alt.partition(sep)
                if mark and rest.startswith("~"):
                    forms.append(head + sep + os.path.expanduser(rest))
            if alt.startswith("~"):
                forms.append(os.path.expanduser(alt))
            for form in list(forms):
                forms.extend(_glob_forms(form, directories, uncertain))
            out.extend(f for f in forms if f not in out)
    return out


def _directory_of(cwd_value, cwd):
    """`cwd_value` (a `_Run.cwd`) made absolute against the hook's `cwd`, or None when it cannot be read (`cd "$D"`, `cd ~`, `cd -`) or `cwd` is not given."""
    if cwd is None:
        return None
    if cwd_value is None:
        return os.path.normpath(cwd)
    if (
        cwd_value.startswith(("~", "-"))
        or any(ch in cwd_value for ch in "$`")
        or _UNRESOLVED in cwd_value
    ):
        return None
    return os.path.normpath(os.path.join(cwd, cwd_value))


def _run_directory(run, cwd):
    """The absolute directory `run` executes in, from the hook's `cwd` and the `cd`s that persist to it, or None when it cannot be read."""
    return _directory_of(run.cwd, cwd)


def _feed_directories(run, cwd):
    """`(directories, uncertain)` where the producer feeding `run` matched its globs: each producer command's directory (`_Run.feed_cwds`), else the run's own.

    A FAILED `cd` LEAVES THE SHELL WHERE IT WAS (review a165575f.2): `cd nosuch; echo f* | xargs cp a` runs the echo in the starting directory, while the walk's `cwd` says `nosuch`. A directory that is not on disk therefore adds the starting directory as a candidate too, and marks the reading uncertain, so the shape fallback stays.
    """
    values = run.feed_cwds or (run.cwd,)
    directories: list[str] = []
    uncertain = False
    # A LAUNCHED RUN (review 9ed30a8a.1): a command `find -exec` or `npx` starts is read where its launcher runs, which this walk can name, but bash's own word for where it executes is the launcher's, so its glob also gets the shape reading. One started ELSEWHERE (`find -execdir`, `npx -w`) runs in a directory this walk cannot name at all, so no directory is a candidate.
    if run.launch is not None:
        uncertain = True
        if run.launch.elsewhere:
            return [], True
    for value in values:
        resolved = _directory_of(value, cwd)
        if resolved is None:
            uncertain = True
            continue
        if not os.path.isdir(resolved):
            uncertain = True
            resolved = os.path.normpath(cwd)
        if resolved not in directories:
            directories.append(resolved)
    return directories, uncertain or not directories


def run_copies(run, argv=None, cwd=None):
    """`(sources, [destination, ...], into)` for a walked copier run, or None: `copy_destination` over its argv, with what the run's launcher or feed adds. `argv` replaces the run's own words (a caller passes `_Run.xargv` to read `$F` as bash expands it). `into` is True only when the command names its destination a directory (`-t`), never for a fed word.

    A `{}` destination is what a `find -exec` walks (`Launch.starts`). xargs APPENDS what it reads to the command's own arguments (measured with cp, mv and install, #5077391c), so where a fed word lands is the tool's own parse of `argv + fed`: under `-t` every fed word is a SOURCE, and without it the last one is the destination and the argv's own last operand a source. That is read exactly when the words are known (`_Run.feed_words`, a literal producer) and xargs appends them in one invocation (`_appends_once`).
    Otherwise what the producer prints is not computed, so the reading fails safe: under `-t` every fed word is a source, and without it every fed word may be the destination. Before #5077391c the fed words were destinations even under `-t`, so `echo /tmp/flagged.md | xargs cp -t .claude/commands` read the commands directory as the source, and the fed-only shape answered "into a directory" for what is a file.
    """
    name = run.name.rsplit("/", 1)[-1]
    if name not in COPIERS:
        return None
    argv = list(run.argv if argv is None else argv)
    fed_by_xargs = bool(run.feed) and "xargs" in run.via
    options = run.xargs if run.xargs is not None else ()
    if fed_by_xargs and run.feed_words is not None and _appends_once(options):
        found = copy_destination(name, [*argv, *run.feed_words])
        if found is None:
            return None
        sources, dest, into = found
        return sources, [dest], into
    found = copy_destination(name, argv)
    # `cwd`, when a caller knows it, is where the hook's command starts: a relative glob in the feed is matched in the directory this run executes in.
    fed = []
    if fed_by_xargs:
        directories, uncertain = _feed_directories(run, cwd)
        fed = _fed_candidates(run.feed.split(), directories, uncertain)
    # FAIL-SAFE: with the words unknown, any fed word may be a source as well as the destination (`echo {b,d} | xargs cp a` runs `cp a b d`, which copies `b` into `d`).
    if found is None:
        return ([a for a in argv if not a.startswith("-")] + fed, fed, False) if fed else None
    sources, dest, into = found
    dests = [dest]
    if run.launch is not None and run.launch.launcher == "find" and "{}" in dest:
        dests = list(run.launch.starts)
    if not fed:
        return sources, dests, into
    if into:
        # `-t DIR`: the fed words are more sources, unless `-I {}` puts them in the directory's place.
        if "{}" in dest:
            return sources, fed, into
        return [*sources, *fed], dests, into
    # `xargs -I {}`: a destination naming `{}` is that word with each fed word in its place (`xargs -I{} cp a src/{}`).
    placed = [d.replace("{}", w) for d in dests if "{}" in d for w in fed]
    return [*sources, dest, *fed], [d for d in dests if "{}" not in d] + fed + placed, into


def copy_landings(run, cwd, names=COPIERS, argv=None):
    """`(path, into a directory)` for every file a run of one of `names` writes, absolute, or [] for any other run.

    Placed by `run_copies` and then the way the tool places a file: a destination is a DIRECTORY when the command says so (`-t`), when it is written with a trailing slash, or when the filesystem says so, and then each source lands inside it under its own name; anything else is the file written. Relative paths are read from `cwd` joined with the run's own `cd`.

    THE WORDS ARE THE EXPANDED ONES BY DEFAULT (review 88362611.1): `argv` None reads `_Run.xargv`, so `F=<path>; cp /tmp/x $F` lands on `<path>`, as bash makes it. A word this walk cannot expand stays `_UNRESOLVED` and names no file.

    This function calls nothing in the guards; three guards call it: block_bash_write_to_running_script (`cp`/`mv` onto a running script), block_roundlog_truncate (`cp` onto a round log) and block_binary_deploy (every copier onto the installed renet).
    """
    if _base(run.name) not in names:
        return []
    if argv is None and run.xargv is not None:
        argv = run.xargv
    copies = run_copies(run, argv, cwd)
    if copies is None:
        return []
    sources, dests, into = copies
    base = cwd if run.cwd is None else os.path.join(cwd, run.cwd)
    # TWO CASES, ONE ANSWER (review 9ed30a8a.2). A `cd` to a directory that is not there fails and leaves the shell where it started (review a165575f.2); a `cd` whose target the walk cannot resolve (`cd "$D"`, `cd ~`) lands somewhere this walk cannot name. Either way the run's directory is not on disk here, and the starting directory is the one other place a relative destination can land, so both are candidates. `run.cwd` is None ONLY when no `cd` ran before this command, and then the starting directory is the one base; an unresolved `cd` leaves `run.cwd` as the unexpanded word (`$D`, `~`, `-`), which joins to a path that is not on disk and so takes this branch (review 1d4e1754.2, measured).
    bases = [base] if os.path.isdir(base) else [base, cwd]
    out: list[tuple[str, bool]] = []
    for base in bases:
        for dest in dests:
            dest_abs = os.path.normpath(os.path.join(base, dest))
            if into or dest.endswith("/") or os.path.isdir(dest_abs):
                out.extend(
                    (os.path.join(dest_abs, os.path.basename(src.rstrip("/"))), True)
                    for src in sources
                )
            elif (dest_abs, False) not in out:
                out.append((dest_abs, False))
    return out


# --------------------------------------------------------------------------- where a Python program writes ---------------------------------------------------------------------------
#
# A PYTHON PROGRAM IS JUDGED BY ITS WRITE TARGETS, NOT BY THE PATHS IT NAMES. block_review_file_shell_write learned it first (2026-10-09: a heredoc whose written CONTENT named a review path was refused). block_user_only_command_shell_write still refused any program that named the exception list and wrote anything anywhere, so a heredoc reading the list beside a scratch write was "a python3 program writing the exception
# list" (coordinator finding 2026-10-11, and this writer's own edit of the test corpus was refused that way the same day). The reading moved here so both guards share it: `python_write_targets` yields each write call's target expression, and `python_writes_to` answers whether one of them holds a string the caller's predicate accepts, directly or through a name bound to one, transitively. A mention, an open for read and a `json.load` are data.
_PY_WRITE_MODE = re.compile(r"[wax+]")
_PY_RECEIVER_WRITES = frozenset(
    ("write_text", "write_bytes", "unlink", "touch", "rmdir", "symlink_to", "hardlink_to")
)
_PY_RECEIVER_MOVES = frozenset(("rename", "replace"))
_PY_DEST_CALLS = frozenset(
    ("replace", "rename", "move", "copy", "copy2", "copyfile", "copytree", "link", "symlink")
)
_PY_REMOVE_CALLS = frozenset(("remove", "unlink", "rmtree", "truncate"))


def python_imports(tree):
    """Each imported local name -> what it names: `import subprocess as sp` gives `sp -> subprocess`, `from os import system` gives `system -> os.system`."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    names[a.asname] = a.name
                else:
                    head = a.name.split(".")[0]
                    names[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                names[a.asname or a.name] = "%s.%s" % (node.module, a.name)
    return names


def python_qualified(func, imports):
    """The dotted name a call's function spells after resolving import aliases (`sp.run` -> `subprocess.run`), or ""."""
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return ""
    parts.append(imports.get(func.id, func.id))
    return ".".join(reversed(parts))


# `os.open`'s flags: anything but these read-only bits (a write flag, a variable, a number with a write bit) can write.
_PY_READ_FLAGS = frozenset(
    (
        "os",
        "O_RDONLY",
        "O_CLOEXEC",
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "O_NONBLOCK",
        "O_NOCTTY",
        "O_BINARY",
        "O_PATH",
        "O_NOATIME",
        "O_LARGEFILE",
    )
)


def _py_flags_can_write(expr):
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id not in _PY_READ_FLAGS:
            return True
        if isinstance(n, ast.Attribute) and n.attr not in _PY_READ_FLAGS:
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value & 0o3:
            return True
    return False


def _py_mode_can_write(mode):
    """An `open` mode argument: absent is a read, a constant is read by its letters, and anything else (a variable, `*args`) is assumed to write."""
    if mode is None:
        return False
    if isinstance(mode, ast.Constant):
        return isinstance(mode.value, str) and _PY_WRITE_MODE.search(mode.value) is not None
    return True


def python_keyword(node, name):
    return next((k.value for k in node.keywords if k.arg == name), None)


def python_write_targets(tree, imports=None):
    """The target expressions of every write call in a Python tree.

    `open` has three shapes (e30f1ad1.1): the builtin and a module function (`io.open`, `codecs.open`, `gzip.open`) take the path first and the mode second; `os.open` takes FLAGS second; and a method on a path object (`Path(p).open('w')`) takes the mode FIRST, the receiver being the target.
    """
    imports = python_imports(tree) if imports is None else imports
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else ""
        )
        if attr == "open":
            qualified = python_qualified(func, imports)
            on_module = isinstance(func, ast.Name) or (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in imports
            )
            if qualified == "os.open":
                flags = node.args[1] if len(node.args) > 1 else python_keyword(node, "flags")
                path = node.args[0] if node.args else python_keyword(node, "path")
                if flags is not None and path is not None and _py_flags_can_write(flags):
                    yield path
            elif on_module:
                mode = node.args[1] if len(node.args) > 1 else python_keyword(node, "mode")
                path = node.args[0] if node.args else python_keyword(node, "file")
                if path is not None and _py_mode_can_write(mode):
                    yield path
            elif isinstance(func, ast.Attribute):
                mode = node.args[0] if node.args else python_keyword(node, "mode")
                if _py_mode_can_write(mode):
                    yield func.value
            continue
        # `os.replace(a, b)` and `str.replace(old, new)` share a name: a module call counts only when `os` or `shutil` qualifies it, and the receiver form only with Path's single argument.
        module = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in ("os", "shutil")
        )
        receiver_write = attr in _PY_RECEIVER_WRITES or (
            attr in _PY_RECEIVER_MOVES and len(node.args) == 1
        )
        if isinstance(func, ast.Attribute) and not module and receiver_write:
            yield func.value
            yield from node.args[:1] if attr in _PY_RECEIVER_MOVES else ()
        if module and attr in _PY_DEST_CALLS and len(node.args) > 1:
            if attr in ("replace", "rename", "move"):
                yield node.args[0]
            yield node.args[1]
        if module and attr in _PY_REMOVE_CALLS and node.args:
            yield node.args[0]


def python_bindings(tree):
    """`{name: [value expression, ...]}` for every assignment, annotated or augmented assignment and walrus in a Python tree."""
    bound: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        bound.setdefault(n.id, []).append(node.value)
        elif isinstance(node, ast.NamedExpr):
            bound.setdefault(node.target.id, []).append(node.value)
    return bound


def python_holds(expr, holds, names):
    """Whether `expr` carries a string constant `holds` accepts, or one of `names`."""
    for n in ast.walk(expr):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and holds(n.value):
            return True
        if isinstance(n, ast.Name) and n.id in names:
            return True
    return False


def python_matching_names(bound, holds):
    """The names bound, transitively, to an expression carrying a string `holds` accepts."""
    names: set = set()
    changed = True
    while changed:
        changed = False
        for name, values in bound.items():
            if name not in names and any(python_holds(v, holds, names) for v in values):
                names.add(name)
                changed = True
    return names


def python_writes_to(program, holds):
    """True or False for a Python program that parses: does a write target hold a string `holds` accepts? None when it does not parse, so the caller's text reading answers instead."""
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    names = python_matching_names(python_bindings(tree), holds)
    return any(python_holds(t, holds, names) for t in python_write_targets(tree))


def ssh_remote_commands(cmd, depth=0):
    """`(destination, remote command)` for every `ssh` that `cmd` runs with a remote command, behind any prefix (`sshpass -p x ssh ...`) or launcher, and the hops inside each remote command after it (`ssh a "ssh b docker ps"` yields both).

    The remote command is a shell string the far side parses again, so a guard policing what runs THERE walks it with `every_run(remote)`.
    """
    out: list[tuple[str, str]] = []
    if depth >= _MAX_DEPTH:
        return out
    for run in every_run(cmd):
        if run.remote is None:
            continue
        out.append(run.remote)
        out.extend(ssh_remote_commands(run.remote[1], depth + 1))
    return out


def lifted_commands(cmd, view):
    """The canonical line of every command bash runs in `cmd` that `view` does not already show at a command position.

    `view` is whatever text the caller's regexes run over. `scan_target` passes its own prose-stripped line plus wrapper payload; `block_git_amend`, which builds its own view, passes that. The lines come back in the order bash would run the commands, each once. A launcher's commands (`npx`, `find -exec`, see `_launched`) are lifted too, right after the launcher's own line.
    """
    segments = _anchored_segments(view)
    out: list[str] = []
    for run in _every_run(_analyse(cmd)):
        line = run.canonical
        if line in out or _visible(line, segments):
            continue
        out.append(line)
    return out


# --------------------------------------------------------------------------- same-command state (PLAN-stop-hook-retro-20260924 #3, R20260924.22) ---------------------------------------------------------------------------
#
# EVERY PRE-BASH GUARD RUNS ONCE, BEFORE THE FIRST CLAUSE. A guard judging `git commit` or `git push` reads the index, HEAD, a message file or an epic snapshot as they are at that instant, and an earlier clause of the same command (`git add`, `git commit`, `printf > msg`, `npm run ci:quick`, `worklist.py --publish`) may be about to change exactly that. Four refusals in one hour on
# 2026-09-24 judged such a world and said nothing about it, so the session spent calls working out why a correct command was refused. These helpers let a guard SAY so. They never turn a refusal into an allow: the guard still fails closed, it just names the clause to split off.


class Mutator(typing.NamedTuple):
    """One earlier clause that writes something a guard reads: its `kind`, a `label` to print, and the file `target` of a redirect (else None)."""

    kind: str
    label: str
    target: str | None


# The files nobody's verdict depends on.
_NOT_A_FILE = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")


def _verb_matches(run, verb):
    words = verb.split()
    if _base(run.name) != words[0]:
        return False
    if words[0] == "git":
        return run.git_sub == words[1]
    return run.argv[: len(words) - 1] == words[1:]


def _mutators_of(run):
    base = _base(run.name)
    out: list[Mutator] = []
    for target in run.writes:
        if target in _NOT_A_FILE or target.startswith("/dev/fd/"):
            continue
        out.append(Mutator("redirect", "%s > %s" % (base, target), target))
    argv = run.argv
    if base == "git" and run.git_sub == "commit":
        out.append(Mutator("commit", "git commit", None))
    elif base == "git" and run.git_sub in ("add", "rm", "mv"):
        out.append(Mutator("stage", "git %s" % run.git_sub, None))
    elif base == "npm" and argv[:1] in (["run"], ["run-script"]) and len(argv) > 1:
        if argv[1] == "ci" or argv[1].startswith("ci:"):
            out.append(Mutator("ci", "npm run %s" % argv[1], None))
    elif "--publish" in argv and (
        base == "worklist.py" or any(_base(a) == "worklist.py" for a in argv[:1])
    ):
        out.append(Mutator("publish", "worklist.py --publish", None))
    return out


def earlier_mutators(cmd, verb, kinds=None):
    """The clauses of `cmd` that run BEFORE its first `verb` and write something a guard judging `verb` reads, in execution order.

    `verb` is `"git commit"`, `"git push"` or `"gh pr create"`. `kinds` narrows the answer to what one guard actually reads, out of: `stage` (`git add|rm|mv`), `commit`, `ci` (`npm run ci`, `npm run ci:*`), `publish` (`worklist.py --publish`) and `redirect` (an output redirect to a real file; `target` carries the path). A command that never runs `verb` has nothing before it, and neither has a clause AFTER the verb, which cannot have changed what the guard read.
    """
    runs = _analyse(cmd).runs
    idx = next((i for i, run in enumerate(runs) if _verb_matches(run, verb)), None)
    if idx is None:
        return []
    out: list[Mutator] = []
    for run in runs[:idx]:
        out.extend(m for m in _mutators_of(run) if kinds is None or m.kind in kinds)
    return out


V_SPLIT = """BLOCKED: nothing in this command ran, including `%(mutator)s`.

Every pre-bash guard runs ONCE, before the first clause. This one judged
%(judged)s as it was BEFORE `%(mutator)s`, an earlier clause of this same
command that changes it, so the finding below is about that earlier state.

Run `%(mutator)s` as its own call, then `%(verb)s`.%(more)s

"""


def split_refusal(mutators, verb, judged):
    """The `V_SPLIT` preamble a guard prints above its own refusal, or "" when no earlier clause changes what it judged."""
    if not mutators:
        return ""
    labels = []
    for m in mutators:
        if m.label not in labels:
            labels.append(m.label)
    more = ""
    if len(labels) > 1:
        more = "\nOther earlier clauses that change it: %s." % ", ".join(
            "`%s`" % label for label in labels[1:]
        )
    return V_SPLIT % {"mutator": labels[0], "judged": judged, "verb": verb, "more": more}


def assignments_before(cmd, verb):
    """`{NAME: value}` for every plain `NAME=value` statement at the top level of `cmd` before its first `verb`, quote-removed, later assignments winning.

    ONLY A STATEMENT COUNTS. `P=x git commit -- $P` does not count: bash expands `$P` BEFORE that prefix assignment applies, so the old value is the one used, and this cannot know it. `export NAME=value` counts. A substitution inside the value is kept as its source text (`$(ls x/*.json)`), for the caller to expand or to refuse to.
    """
    words = verb.split()
    out: dict[str, str] = {}
    cur: list = []

    def finish():
        values = [_word_value(w) for w in cur]
        if not values:
            return False
        if values[0] == "export":
            values = values[1:]
        if values and all(_ASSIGNMENT.match(v) for v in values):
            for v in values:
                match = _ASSIGNMENT.match(v)
                if match is None:
                    continue
                name = match.group(0)
                append = name.endswith("+=")
                key = name.rstrip("+=").split("[", 1)[0]
                value = v[len(name) :]
                out[key] = (out.get(key, "") + value) if append else value
            return False
        rest = [v for v in values if not _ASSIGNMENT.match(v)]
        return bool(rest) and _base(rest[0]) == words[0] and all(w in rest[1:] for w in words[1:])

    for tok in _Lexer(cmd).tokens():
        if isinstance(tok, _Op):
            if finish():
                return out
            cur = []
            continue
        if isinstance(tok, _Word):
            cur.append(tok)
    return out


# A redirect or `tee` that writes a file: the shapes a same-command message file is produced by (`printf ... > $S/msg`, `cat > $S/msg <<'EOF'`, `... | tee $S/msg`).
_WRITE_TARGET = re.compile(r"""(?:>>?|\btee(?:\s+-a)?)\s*["']?([^\s"';|&<>]+)""")


def writes_file(cmd, *names):
    """Does `cmd` itself write any of `names` (a redirect or `tee` target), spelled as given?

    A PreToolUse guard runs BEFORE the command, so a message file the same command writes still holds whatever an EARLIER command left there. On 2026-09-27 `printf ... > $S/ps.txt; git commit -F $S/ps.txt` was judged on a stale ps.txt and refused for 28 findings that were never in the message; the same shape passes a bad message as easily (#9ec22810). A caller that gets True treats the message as unreadable, its existing fail-open.
    """
    wanted = {n for n in names if n}
    return any(target in wanted for target in _WRITE_TARGET.findall(cmd or ""))


# --------------------------------------------------------------------------- gh's flags, read the way gh reads them (#8ed364fe) ---------------------------------------------------------------------------
#
# A GUARD THAT READS A FLAG BY REGEX SEES ONLY THE SPELLINGS ITS REGEX NAMES, and gh (pflag under cobra) accepts many more for each one: `--repo x`, `--repo=x`, `-R x`, `-Rx`, `-R=x`, and a bundle of boolean shorthands ending in it (`-dR x`); a value-taking flag swallows the next word whatever it looks like (`--title --draft` titles a PR "--draft"); `--draft=false` is not a
# draft; and a `pr`-level flag may sit BEFORE the verb (`gh pr -R x create`). Measured 2026-10-07 through the real dispatcher: `gh pr create -R=rediacc/renet -t x` was refused as a console create while `--repo=rediacc/renet` passed, `-dH <name>` cut a remote branch past block_second_branch, `gh api ... -XPATCH -Fbody=@f` walked past the PATCH arm the long spelling is refused by,
# and `git commit -qF <file>` was never read. 28801da09 fixed the body flags of one guard with a parser over the walked argv; this is that parser, shared, for every gh flag a guard asks about.
#
# `gh_args` parses ONE walked argv (`run.argv`, the words after `gh`). It never reads command text, so a quoted value is the value (`--repo 'rediacc/renet'`), and prose naming a flag is never a flag.

# Every flag of the gh commands a guard judges, `gh <cmd> --help` on gh 2.98.0: long name -> (shorthand or "", takes a value). `help` is inherited by all of them and `repo` by every `pr` command.
_GH_INHERITED = {"help": ("h", False)}
_GH_PR_INHERITED = {"repo": ("R", True)}
GH_FLAGS = {
    ("pr", "create"): {
        "assignee": ("a", True),
        "base": ("B", True),
        "body": ("b", True),
        "body-file": ("F", True),
        "draft": ("d", False),
        "dry-run": ("", False),
        "editor": ("e", False),
        "fill": ("f", False),
        "fill-first": ("", False),
        "fill-verbose": ("", False),
        "head": ("H", True),
        "label": ("l", True),
        "milestone": ("m", True),
        "no-maintainer-edit": ("", False),
        "project": ("p", True),
        "recover": ("", True),
        "reviewer": ("r", True),
        "template": ("T", True),
        "title": ("t", True),
        "web": ("w", False),
    },
    ("pr", "edit"): {
        "add-assignee": ("", True),
        "add-label": ("", True),
        "add-project": ("", True),
        "add-reviewer": ("", True),
        "base": ("B", True),
        "body": ("b", True),
        "body-file": ("F", True),
        "milestone": ("m", True),
        "remove-assignee": ("", True),
        "remove-label": ("", True),
        "remove-milestone": ("", False),
        "remove-project": ("", True),
        "remove-reviewer": ("", True),
        "title": ("t", True),
    },
    ("pr", "merge"): {
        "admin": ("", False),
        "author-email": ("A", True),
        "auto": ("", False),
        "body": ("b", True),
        "body-file": ("F", True),
        "delete-branch": ("d", False),
        "disable-auto": ("", False),
        "match-head-commit": ("", True),
        "merge": ("m", False),
        "rebase": ("r", False),
        "squash": ("s", False),
        "subject": ("t", True),
    },
    ("pr", "ready"): {"undo": ("", False)},
    ("pr", "view"): {
        "comments": ("c", False),
        "jq": ("q", True),
        "json": ("", True),
        "template": ("t", True),
        "web": ("w", False),
    },
    ("pr", "list"): {
        "app": ("", True),
        "assignee": ("a", True),
        "author": ("A", True),
        "base": ("B", True),
        "draft": ("d", False),
        "head": ("H", True),
        "jq": ("q", True),
        "json": ("", True),
        "label": ("l", True),
        "limit": ("L", True),
        "search": ("S", True),
        "state": ("s", True),
        "template": ("t", True),
        "web": ("w", False),
    },
    ("pr", "comment"): {
        "body": ("b", True),
        "body-file": ("F", True),
        "create-if-none": ("", False),
        "delete-last": ("", False),
        "edit-last": ("", False),
        "editor": ("e", False),
        "web": ("w", False),
        "yes": ("", False),
    },
    ("pr", "close"): {"comment": ("c", True), "delete-branch": ("d", False)},
    ("pr", "review"): {
        "approve": ("a", False),
        "body": ("b", True),
        "body-file": ("F", True),
        "comment": ("c", False),
        "request-changes": ("r", False),
    },
    ("api",): {
        "allow-escape-sequences": ("", False),
        "cache": ("", True),
        "field": ("F", True),
        "header": ("H", True),
        "hostname": ("", True),
        "include": ("i", False),
        "input": ("", True),
        "jq": ("q", True),
        "method": ("X", True),
        "paginate": ("", False),
        "preview": ("p", True),
        "raw-field": ("f", True),
        "silent": ("", False),
        "slurp": ("", False),
        "template": ("t", True),
        "verbose": ("", False),
    },
}

# strconv.ParseBool's false spellings, which pflag applies to `--draft=<v>` and `-d=<v>`.
_GH_FALSE = frozenset(("0", "f", "F", "false", "FALSE", "False"))


class ParsedArgs:
    """One gh (or git subcommand) invocation, parsed: `command` (`("pr", "create")`, `("api",)`, ...), `flags` as `(long name, value)` in order (a boolean's value is "true" unless spelled `=<v>`), and `operands`, the positional words.

    `known` is False for a command the tables do not describe; its flags are then read with the inherited table only, and an unknown flag ends the parse, as it ends gh's.

    `problems` (git mode only) lists `("ambiguous", spelling)` and `("unknown", spelling)` for each option git itself would refuse: `git commit --fi x` is ambiguous between `--file` and `--fixup`, and git exits 129 and runs nothing. The parse READS ON past one rather than stopping, so a later `--file f` is still seen; a caller that wants to refuse such a command outright can.
    """

    __slots__ = ("command", "flags", "known", "operands", "problems")

    def __init__(self, command, flags, operands, known, problems=None):
        self.command = command
        self.flags = flags
        self.operands = operands
        self.known = known
        self.problems = problems if problems is not None else []

    def values(self, name):
        """Every value `name` was given, in order."""
        return [v for n, v in self.flags if n == name]

    def last(self, name):
        """The value gh uses for a single-valued flag (the last one wins), None when it is absent."""
        found = self.values(name)
        return found[-1] if found else None

    def on(self, name):
        """Is the boolean flag `name` set? `--draft=false` is not."""
        value = self.last(name)
        return value is not None and value not in _GH_FALSE


# `_lookup`'s answer for a git abbreviation that fits more than one option.
_AMBIGUOUS = ("", None, False)


def _git_spellings(table, noneg):
    """Every `--<spelling>` git's parse-options accepts for `table`, mapped to the `(long name, negated)` meanings it may have: each name, `no-<name>` unless the option is in `noneg`, and for a name that itself starts `no-` its bare remainder (`--verify` is the negation of `--no-verify`, and `--no-no-verify` is too: measured on git 2.53.0)."""
    out: dict[str, set] = {}
    for name in table:
        out.setdefault(name, set()).add((name, False))
    for name in table:
        if name in noneg:
            continue
        out.setdefault("no-" + name, set()).add((name, True))
        if name.startswith("no-"):
            out.setdefault(name[3:], set()).add((name, True))
    return out


def _lookup(name, table, git, noneg=frozenset()):
    """`(long name, spec, negated)` for a `--name` spelling; None for an unknown one, `_AMBIGUOUS` for an abbreviation git refuses.

    pflag takes exact names only. git (parse-options.c `parse_long_opt`) also takes a `--no-` negation and a unique PREFIX of any spelling, an exact spelling winning over a longer one it prefixes (`--allow-empty` is not an abbreviation of `--allow-empty-message`). Unique means one MEANING: two spellings of the same option are not a conflict. Measured on git 2.53.0 `git commit`: `--fil` is `--file`, `--no-veri` is `--no-verify`, `--no-e` is `--no-edit`; `--fi` (file, fixup), `--ver` (verbose, verify), `--no-ver` (no-verify, no-verbose) and `--al` exit 129.
    """
    if name in table:
        return name, table[name], False
    if not git:
        return None
    spellings = _git_spellings(table, noneg)
    meanings = spellings.get(name)
    if meanings is None:
        meanings = set()
        for spelling, means in spellings.items():
            if name and spelling.startswith(name):
                meanings |= means
    if not meanings:
        return None
    if len(meanings) > 1:
        return _AMBIGUOUS
    long, negated = next(iter(meanings))
    return long, table[long], negated


def _gh_parse(words, table, stop_at_operand, git=False, noneg=frozenset(), problems=None):
    """pflag (or, with `git`, git's parse-options) over `words` with `table`. Returns `(flags, operands, rest)`: `rest` is what follows the first operand when `stop_at_operand`, else [].

    A spec's second field is True for a flag that takes a value, False for a boolean, and "opt" for git's optional value (`-n5`, `--column=x`), which is never taken from the next word. The two dialects differ in three more places: git's `-F=x` names the file `=x` where pflag's names `x`; git accepts the abbreviations and negations `_lookup` describes (a negated boolean is recorded as `(name, "false")`, a negated value-taking option as nothing); and git mode READS ON past an option git would refuse, recording it in `problems`, where gh mode stops. git refuses such a command and runs nothing, so reading on can only over-report, and a table one option short of a newer git must not hide the `-F` after it.
    """
    shorts = {spec[0]: name for name, spec in table.items() if spec[0]}
    if problems is None:
        problems = []
    flags = []
    operands = []
    i = 0
    while i < len(words):
        arg = words[i]
        i += 1
        if arg == "--" or (git and arg == "--end-of-options"):
            # git 2.53.0: `git commit -m x --end-of-options --no-verify` read `--no-verify` as a pathspec and ran the hooks.
            operands.extend(words[i:])
            break
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            found = _lookup(name, table, git, noneg)
            if found is None or found is _AMBIGUOUS:
                if not git:
                    # gh refuses an unknown flag and runs nothing; reading on would only guess.
                    break
                problems.append(("unknown" if found is None else "ambiguous", arg))
                continue
            name, spec, negated = found
            if negated:
                if spec[1] is not True:
                    flags.append((name, "false"))
                continue
            if spec[1] == "opt":
                value = value if eq else ""
            elif spec[1] and not eq:
                if i >= len(words):
                    break
                value = words[i]
                i += 1
            elif not spec[1] and not eq:
                value = "true"
            flags.append((name, value))
            continue
        if not arg.startswith("-") or arg == "-":
            if stop_at_operand:
                return flags, [arg], words[i:]
            operands.append(arg)
            continue
        letters = arg[1:]
        for pos, letter in enumerate(letters):
            name = shorts.get(letter)
            if name is None:
                if git:
                    problems.append(("unknown", "-" + letter))
                    continue
                return flags, operands, []
            rest = letters[pos + 1 :]
            if table[name][1] == "opt":
                flags.append((name, rest))
                break
            if not table[name][1]:
                if rest.startswith("=") and not git:
                    flags.append((name, rest[1:]))
                    break
                flags.append((name, "true"))
                continue
            if rest.startswith("=") and not git:
                value = rest[1:]
            elif rest:
                value = rest
            elif i < len(words):
                value = words[i]
                i += 1
            else:
                return flags, operands, []
            flags.append((name, value))
            break
    return flags, operands, []


def gh_args(argv):
    """`ParsedArgs` for one walked `gh` invocation; `argv` is the words AFTER `gh` (`run.argv`).

    A `pr`-level flag before the verb is read too, as gh reads it: `gh pr -R x create -t y` is a create on `x`.
    """
    if not argv:
        return ParsedArgs((), [], [], False)
    if argv[0] == "api":
        table = dict(_GH_INHERITED, **GH_FLAGS[("api",)])
        flags, operands, _ = _gh_parse(argv[1:], table, False)
        return ParsedArgs(("api",), flags, operands, True)
    if argv[0] != "pr":
        return ParsedArgs((argv[0],), [], list(argv[1:]), False)
    pr_table = dict(_GH_INHERITED, **_GH_PR_INHERITED)
    leading, verb, rest = _gh_parse(argv[1:], pr_table, True)
    if not verb:
        return ParsedArgs(("pr",), leading, [], False)
    command: tuple[str, ...] = ("pr", verb[0])
    known = command in GH_FLAGS
    table = dict(pr_table, **GH_FLAGS.get(command, {}))
    flags, operands, _ = _gh_parse(rest, table, False)
    return ParsedArgs(command, leading + flags, operands, known)


# `git tag -h` on git 2.53.0, complete, because a git abbreviation is unique only against the whole set.
GIT_TAG_FLAGS = {
    "list": ("l", False),
    "delete": ("d", False),
    "verify": ("v", False),
    "annotate": ("a", False),
    "message": ("m", True),
    "file": ("F", True),
    "trailer": ("", True),
    "edit": ("e", False),
    "sign": ("s", False),
    "cleanup": ("", True),
    "local-user": ("u", True),
    "force": ("f", False),
    "create-reflog": ("", False),
    "column": ("", "opt"),
    "contains": ("", True),
    "no-contains": ("", True),
    "merged": ("", True),
    "no-merged": ("", True),
    "omit-empty": ("", False),
    "sort": ("", True),
    "points-at": ("", True),
    "format": ("", True),
    "color": ("", "opt"),
    "ignore-case": ("i", False),
    "n": ("n", "opt"),
    # Hidden aliases of `--contains`/`--no-contains`: listed so `--wi` is as ambiguous here as it is to git.
    "with": ("", True),
    "without": ("", True),
}


# The `git tag` options git does not let `--no-` negate (`git tag --git-completion-helper-all` on git 2.53.0 lists every negation it does accept).
GIT_TAG_NONEG = frozenset(
    (
        "list",
        "delete",
        "verify",
        "message",
        "trailer",
        "contains",
        "no-contains",
        "merged",
        "no-merged",
        "with",
        "without",
    )
)


def git_tag_args(args):
    """`ParsedArgs` for the words after `git tag` (`commit_policy.git_split(run.argv)[2]`), git's parse-options rules: `-F f`, `-Ff`, `-aF f`, `--file=f`, `--fil f`."""
    problems: list = []
    flags, operands, _ = _gh_parse(
        list(args), GIT_TAG_FLAGS, False, git=True, noneg=GIT_TAG_NONEG, problems=problems
    )
    return ParsedArgs(("tag",), flags, operands, True, problems)


# `git commit --git-completion-helper-all` on git 2.53.0, hidden options (`--allow-empty`, `--allow-empty-message`) included, because a git abbreviation is unique only against the WHOLE set: leave one out and `--al` stops being ambiguous here while git still refuses it. Long name -> (shorthand or "", takes a value); "opt" is an optional value that is only ever attached (`-Skey`, `--gpg-sign=key`, `-uno`).
GIT_COMMIT_FLAGS = {
    "quiet": ("q", False),
    "verbose": ("v", False),
    "file": ("F", True),
    "author": ("", True),
    "date": ("", True),
    "message": ("m", True),
    "reedit-message": ("c", True),
    "reuse-message": ("C", True),
    "fixup": ("", True),
    "squash": ("", True),
    "reset-author": ("", False),
    "trailer": ("", True),
    "signoff": ("s", False),
    "template": ("t", True),
    "edit": ("e", False),
    "cleanup": ("", True),
    "status": ("", False),
    "gpg-sign": ("S", "opt"),
    "all": ("a", False),
    "include": ("i", False),
    "interactive": ("", False),
    "patch": ("p", False),
    "unified": ("U", True),
    "inter-hunk-context": ("", True),
    "only": ("o", False),
    "no-verify": ("n", False),
    "dry-run": ("", False),
    "short": ("", False),
    "branch": ("", False),
    "ahead-behind": ("", False),
    "porcelain": ("", False),
    "long": ("", False),
    "null": ("z", False),
    "amend": ("", False),
    "no-post-rewrite": ("", False),
    "untracked-files": ("u", "opt"),
    "pathspec-from-file": ("", True),
    "pathspec-file-nul": ("", False),
    "allow-empty": ("", False),
    "allow-empty-message": ("", False),
}
# The ones the same listing offers no `--no-` form of.
GIT_COMMIT_NONEG = frozenset(("trailer", "unified", "inter-hunk-context"))


def git_commit_args(args):
    """`ParsedArgs` for the words after `git commit` (`commit_policy.git_split(run.argv)[2]`), git's parse-options rules: `-F f`, `-Ff`, `-qF f`, `--file=f`, `--fil f`, `--no-veri`, `--verify` undoing an earlier `-n` (the last one wins, measured on git 2.53.0). Options and pathspecs may interleave, as git permutes them; everything after `--` is a pathspec."""
    problems: list = []
    flags, operands, _ = _gh_parse(
        list(args), GIT_COMMIT_FLAGS, False, git=True, noneg=GIT_COMMIT_NONEG, problems=problems
    )
    return ParsedArgs(("commit",), flags, operands, True, problems)


# `git checkout` and `git switch`, `--git-completion-helper-all` plus `-h` on git 2.53.0, for the branch a guard asks either one to create (`commit_policy._git_creations`). `-b`, `-B` and `-l` have no long name, so they sit under their letter, which `--`-spelling can only reach exactly. "opt" options never take the next word.
GIT_CHECKOUT_FLAGS = {
    "b": ("b", True),
    "B": ("B", True),
    "l": ("l", False),
    "guess": ("", False),
    "overlay": ("", False),
    "quiet": ("q", False),
    "recurse-submodules": ("", "opt"),
    "progress": ("", False),
    "merge": ("m", False),
    "conflict": ("", True),
    "detach": ("d", False),
    "track": ("t", "opt"),
    "force": ("f", False),
    "orphan": ("", True),
    "overwrite-ignore": ("", False),
    "ignore-other-worktrees": ("", False),
    "ours": ("2", False),
    "theirs": ("3", False),
    "patch": ("p", False),
    "unified": ("U", True),
    "inter-hunk-context": ("", True),
    "ignore-skip-worktree-bits": ("", False),
    "pathspec-from-file": ("", True),
    "pathspec-file-nul": ("", False),
}
GIT_CHECKOUT_NONEG = frozenset(("b", "B", "l", "ours", "theirs", "unified", "inter-hunk-context"))
GIT_SWITCH_FLAGS = {
    "create": ("c", True),
    "force-create": ("C", True),
    "guess": ("", False),
    "discard-changes": ("", False),
    "quiet": ("q", False),
    "recurse-submodules": ("", "opt"),
    "progress": ("", False),
    "merge": ("m", False),
    "conflict": ("", True),
    "detach": ("d", False),
    "track": ("t", "opt"),
    "force": ("f", False),
    "orphan": ("", True),
    "overwrite-ignore": ("", False),
    "ignore-other-worktrees": ("", False),
}
GIT_SWITCH_NONEG: frozenset = frozenset()


def git_checkout_args(args):
    """`ParsedArgs` for the words after `git checkout`: `-b x`, `-qb x`, `-bx`, `--orph=x` (git 2.53.0 created the branch for each)."""
    problems: list = []
    flags, operands, _ = _gh_parse(
        list(args), GIT_CHECKOUT_FLAGS, False, git=True, noneg=GIT_CHECKOUT_NONEG, problems=problems
    )
    return ParsedArgs(("checkout",), flags, operands, True, problems)


def git_switch_args(args):
    """`ParsedArgs` for the words after `git switch`: `-c x`, `-qc x`, `--cr x`, `--create=x` (git 2.53.0 created the branch for each)."""
    problems: list = []
    flags, operands, _ = _gh_parse(
        list(args), GIT_SWITCH_FLAGS, False, git=True, noneg=GIT_SWITCH_NONEG, problems=problems
    )
    return ParsedArgs(("switch",), flags, operands, True, problems)


# The verbs whose hooks `--no-verify` skips, and `git push`'s refspec reading (#9de9a8e9). Each table is `git <verb> --git-completion-helper-all` plus `-h` on git 2.53.0, complete for the same reason GIT_COMMIT_FLAGS is: an abbreviation is unique only against the whole set (`--no-ver` is ambiguous on push and commit, `--no-veri` on merge, and unique on push, am and rebase). A name starting `no-` is
# negated by its bare remainder, so `--verify` and `--no-no-verify` both undo `--no-verify` and the last one wins. Measured in a scratch repository with every hook writing a marker: `push --no-verify --verify`, `merge --no-verify --no-no-verify`, `rebase --no-verify --verify` and `am -n --verify` all ran their hooks; `push --no-veri`, `rebase --no-veri`, `am -n`, `am -3n` and `am --no-veri` skipped them; `merge --no-veri` and
# `push --no-ver` exited 129. `-n` is `--no-verify` on commit and am only: it is `--dry-run` on push and `--no-stat` on merge and rebase. `git push -n --no-dry-run` and `git push --tags --no-tags origin main:x` both created the remote branch.
GIT_PUSH_FLAGS = {
    "verbose": ("v", False),
    "quiet": ("q", False),
    "repo": ("", True),
    "all": ("", False),
    "branches": ("", False),
    "mirror": ("", False),
    "delete": ("d", False),
    "tags": ("", False),
    "dry-run": ("n", False),
    "porcelain": ("", False),
    "force": ("f", False),
    "force-with-lease": ("", "opt"),
    "force-if-includes": ("", False),
    "recurse-submodules": ("", True),
    "thin": ("", False),
    "receive-pack": ("", True),
    "exec": ("", True),
    "set-upstream": ("u", False),
    "progress": ("", False),
    "prune": ("", False),
    "no-verify": ("", False),
    "follow-tags": ("", False),
    "signed": ("", "opt"),
    "atomic": ("", False),
    "push-option": ("o", True),
    "ipv4": ("4", False),
    "ipv6": ("6", False),
}
GIT_PUSH_NONEG = frozenset(("ipv4", "ipv6"))
GIT_MERGE_FLAGS = {
    "n": ("n", False),
    "stat": ("", False),
    "summary": ("", False),
    "compact-summary": ("", False),
    "log": ("", "opt"),
    "squash": ("", False),
    "commit": ("", False),
    "edit": ("e", False),
    "cleanup": ("", True),
    "ff": ("", False),
    "ff-only": ("", False),
    "rerere-autoupdate": ("", False),
    "verify-signatures": ("", False),
    "strategy": ("s", True),
    "strategy-option": ("X", True),
    "message": ("m", True),
    "file": ("F", True),
    "into-name": ("", True),
    "verbose": ("v", False),
    "quiet": ("q", False),
    "abort": ("", False),
    "quit": ("", False),
    "continue": ("", False),
    "allow-unrelated-histories": ("", False),
    "progress": ("", False),
    "gpg-sign": ("S", "opt"),
    "autostash": ("", False),
    "overwrite-ignore": ("", False),
    "signoff": ("", False),
    "no-verify": ("", False),
}
GIT_MERGE_NONEG = frozenset(("n", "ff-only", "file"))
GIT_AM_FLAGS = {
    "interactive": ("i", False),
    "no-verify": ("n", False),
    "binary": ("b", False),
    "3way": ("3", False),
    "quiet": ("q", False),
    "signoff": ("s", False),
    "utf8": ("u", False),
    "keep": ("k", False),
    "keep-non-patch": ("", False),
    "message-id": ("m", False),
    "keep-cr": ("", False),
    "scissors": ("c", False),
    "quoted-cr": ("", True),
    "whitespace": ("", True),
    "ignore-space-change": ("", False),
    "ignore-whitespace": ("", False),
    "directory": ("", True),
    "exclude": ("", True),
    "include": ("", True),
    "C": ("C", True),
    "p": ("p", True),
    "patch-format": ("", True),
    "reject": ("", False),
    "resolvemsg": ("", True),
    "continue": ("", False),
    "resolved": ("r", False),
    "skip": ("", False),
    "abort": ("", False),
    "quit": ("", False),
    "show-current-patch": ("", "opt"),
    "retry": ("", False),
    "allow-empty": ("", False),
    "committer-date-is-author-date": ("", False),
    "ignore-date": ("", False),
    "rerere-autoupdate": ("", False),
    "gpg-sign": ("S", "opt"),
    "empty": ("", True),
    "rebasing": ("", False),
}
GIT_AM_NONEG = frozenset(
    (
        "quoted-cr",
        "C",
        "p",
        "continue",
        "resolved",
        "skip",
        "abort",
        "quit",
        "show-current-patch",
        "retry",
        "allow-empty",
        "empty",
    )
)
GIT_REBASE_FLAGS = {
    "onto": ("", True),
    "keep-base": ("", False),
    "no-verify": ("", False),
    "quiet": ("q", False),
    "verbose": ("v", False),
    "no-stat": ("n", False),
    "signoff": ("", False),
    "committer-date-is-author-date": ("", False),
    "reset-author-date": ("", False),
    "ignore-date": ("", False),
    "C": ("C", True),
    "ignore-whitespace": ("", False),
    "whitespace": ("", True),
    "force-rebase": ("f", False),
    "no-ff": ("", False),
    "continue": ("", False),
    "skip": ("", False),
    "abort": ("", False),
    "quit": ("", False),
    "edit-todo": ("", False),
    "show-current-patch": ("", False),
    "apply": ("", False),
    "merge": ("m", False),
    "interactive": ("i", False),
    "preserve-merges": ("p", False),
    "rerere-autoupdate": ("", False),
    "empty": ("", True),
    "keep-empty": ("k", False),
    "autosquash": ("", False),
    "update-refs": ("", False),
    "gpg-sign": ("S", "opt"),
    "autostash": ("", False),
    "exec": ("x", True),
    "allow-empty-message": ("", False),
    "rebase-merges": ("r", "opt"),
    "fork-point": ("", False),
    "strategy": ("s", True),
    "strategy-option": ("X", True),
    "root": ("", False),
    "reschedule-failed-exec": ("", False),
    "reapply-cherry-picks": ("", False),
}
GIT_REBASE_NONEG = frozenset(
    (
        "C",
        "continue",
        "skip",
        "abort",
        "quit",
        "edit-todo",
        "show-current-patch",
        "apply",
        "merge",
        "interactive",
        "empty",
    )
)
# `git branch -h` plus `--git-completion-helper-all` on git 2.53.0, hidden `--with`/`--without`/`--set-upstream` included (#d5d33bee). `-D`, `-M` and `-C` have no long name of their own. `--contains`, `--merged` and their `no-` twins take the next word unless they are last; they put `git branch` in list mode either way, so reading the next word as theirs never creates a branch here that git would not.
GIT_BRANCH_FLAGS = {
    "verbose": ("v", False),
    "quiet": ("q", False),
    "track": ("t", "opt"),
    "set-upstream": ("", False),
    "set-upstream-to": ("u", True),
    "unset-upstream": ("", False),
    "color": ("", "opt"),
    "remotes": ("r", False),
    "contains": ("", True),
    "no-contains": ("", True),
    "with": ("", True),
    "without": ("", True),
    "abbrev": ("", "opt"),
    "all": ("a", False),
    "delete": ("d", False),
    "D": ("D", False),
    "move": ("m", False),
    "M": ("M", False),
    "omit-empty": ("", False),
    "copy": ("c", False),
    "C": ("C", False),
    "list": ("l", False),
    "show-current": ("", False),
    "create-reflog": ("", False),
    "edit-description": ("", False),
    "force": ("f", False),
    "merged": ("", True),
    "no-merged": ("", True),
    "column": ("", "opt"),
    "sort": ("", True),
    "points-at": ("", True),
    "ignore-case": ("i", False),
    "recurse-submodules": ("", False),
    "format": ("", True),
}
GIT_BRANCH_NONEG = frozenset(
    (
        "remotes",
        "contains",
        "no-contains",
        "with",
        "without",
        "all",
        "D",
        "M",
        "C",
        "merged",
        "no-merged",
    )
)
# `git worktree add -h` on git 2.53.0 (#d5d33bee): `-b` and `-B` have no long name.
GIT_WORKTREE_ADD_FLAGS = {
    "force": ("f", False),
    "b": ("b", True),
    "B": ("B", True),
    "orphan": ("", False),
    "detach": ("d", False),
    "checkout": ("", False),
    "lock": ("", False),
    "reason": ("", True),
    "quiet": ("q", False),
    "track": ("", False),
    "guess-remote": ("", False),
    "relative-paths": ("", False),
}
GIT_WORKTREE_ADD_NONEG = frozenset(("b", "B"))
# `git add -h` and `git rm -h` plus `--git-completion-helper-all` on git 2.53.0, hidden `--warn-embedded-repo` included (#e8be3092). `--ignore-removal` is `--no-all` and its negation is `--all`; the reader keeps both names so the last one wins across them.
GIT_ADD_FLAGS = {
    "dry-run": ("n", False),
    "verbose": ("v", False),
    "interactive": ("i", False),
    "patch": ("p", False),
    "unified": ("U", True),
    "inter-hunk-context": ("", True),
    "edit": ("e", False),
    "force": ("f", False),
    "update": ("u", False),
    "renormalize": ("", False),
    "intent-to-add": ("N", False),
    "all": ("A", False),
    "ignore-removal": ("", False),
    "refresh": ("", False),
    "ignore-errors": ("", False),
    "ignore-missing": ("", False),
    "sparse": ("", False),
    "chmod": ("", True),
    "warn-embedded-repo": ("", False),
    "pathspec-from-file": ("", True),
    "pathspec-file-nul": ("", False),
}
GIT_ADD_NONEG = frozenset(("unified", "inter-hunk-context"))
GIT_RM_FLAGS = {
    "dry-run": ("n", False),
    "quiet": ("q", False),
    "cached": ("", False),
    "force": ("f", False),
    "r": ("r", False),
    "ignore-unmatch": ("", False),
    "sparse": ("", False),
    "pathspec-from-file": ("", True),
    "pathspec-file-nul": ("", False),
}
GIT_RM_NONEG = frozenset(("r",))
# `git config`, its legacy action options and its subcommands' options together (`git config -h`, `git config set -h` on git 2.53.0, #e8be3092): the guard reading it needs every spelling that writes, and an option of one mode beside the other's is a usage error git refuses, so the union over-reads only commands that run nothing.
GIT_CONFIG_FLAGS = {
    "global": ("", False),
    "system": ("", False),
    "local": ("", False),
    "worktree": ("", False),
    "file": ("f", True),
    "blob": ("", True),
    "get": ("", False),
    "get-all": ("", False),
    "get-regexp": ("", False),
    "get-urlmatch": ("", False),
    "replace-all": ("", False),
    "add": ("", False),
    "unset": ("", False),
    "unset-all": ("", False),
    "rename-section": ("", False),
    "remove-section": ("", False),
    "list": ("l", False),
    "edit": ("e", False),
    "get-color": ("", False),
    "get-colorbool": ("", False),
    "null": ("z", False),
    "name-only": ("", False),
    "show-origin": ("", False),
    "show-scope": ("", False),
    "show-names": ("", False),
    "type": ("t", True),
    "bool": ("", False),
    "int": ("", False),
    "bool-or-int": ("", False),
    "bool-or-str": ("", False),
    "path": ("", False),
    "expiry-date": ("", False),
    "default": ("", True),
    "comment": ("", True),
    "fixed-value": ("", False),
    "includes": ("", False),
    "all": ("", False),
    "value": ("", True),
    "append": ("", False),
    "regexp": ("", False),
    "url": ("", True),
}
GIT_CONFIG_NONEG = frozenset(
    (
        "get",
        "get-all",
        "get-regexp",
        "get-urlmatch",
        "replace-all",
        "add",
        "unset",
        "unset-all",
        "rename-section",
        "remove-section",
        "list",
        "edit",
        "get-color",
        "get-colorbool",
        "bool",
        "int",
        "bool-or-int",
        "bool-or-str",
        "path",
        "expiry-date",
    )
)
# `git clean -h` plus `--git-completion-helper-all` on git 2.53.0 (#e8be3092): `-d`, `-x` and `-X` have no long name.
GIT_CLEAN_FLAGS = {
    "quiet": ("q", False),
    "dry-run": ("n", False),
    "force": ("f", False),
    "interactive": ("i", False),
    "d": ("d", False),
    "exclude": ("e", True),
    "x": ("x", False),
    "X": ("X", False),
}
GIT_CLEAN_NONEG = frozenset(("d", "exclude", "x", "X"))
GIT_VERBS = {
    "clean": (GIT_CLEAN_FLAGS, GIT_CLEAN_NONEG),
    "config": (GIT_CONFIG_FLAGS, GIT_CONFIG_NONEG),
    "add": (GIT_ADD_FLAGS, GIT_ADD_NONEG),
    "rm": (GIT_RM_FLAGS, GIT_RM_NONEG),
    "branch": (GIT_BRANCH_FLAGS, GIT_BRANCH_NONEG),
    "worktree-add": (GIT_WORKTREE_ADD_FLAGS, GIT_WORKTREE_ADD_NONEG),
    "commit": (GIT_COMMIT_FLAGS, GIT_COMMIT_NONEG),
    "tag": (GIT_TAG_FLAGS, GIT_TAG_NONEG),
    "checkout": (GIT_CHECKOUT_FLAGS, GIT_CHECKOUT_NONEG),
    "switch": (GIT_SWITCH_FLAGS, GIT_SWITCH_NONEG),
    "push": (GIT_PUSH_FLAGS, GIT_PUSH_NONEG),
    "merge": (GIT_MERGE_FLAGS, GIT_MERGE_NONEG),
    "am": (GIT_AM_FLAGS, GIT_AM_NONEG),
    "rebase": (GIT_REBASE_FLAGS, GIT_REBASE_NONEG),
}


def git_args(verb, args):
    """`ParsedArgs` for the words after `git <verb>`, for any verb in `GIT_VERBS`, git's parse-options rules: a bundle, a unique prefix, `--no-X`, the last spelling winning, `--` and `--end-of-options` ending the options."""
    table, noneg = GIT_VERBS[verb]
    problems: list = []
    flags, operands, _ = _gh_parse(
        list(args), table, False, git=True, noneg=noneg, problems=problems
    )
    return ParsedArgs((verb,), flags, operands, True, problems)


def git_push_args(args):
    """`ParsedArgs` for the words after `git push`. The first operand is the repository whatever `--repo` says (`--repo=origin main:x` pushed to a repository called "main:x" on git 2.53.0); `--repo` names it only when there is no operand."""
    return git_args("push", args)


def gh_repo_name(value):
    """Lowercase `OWNER/REPO` for any `--repo` spelling gh accepts: `OWNER/REPO`, `HOST/OWNER/REPO`, or a URL (`https://github.com/o/r.git`, `git@github.com:o/r`). GitHub matches both names case-insensitively, so `Rediacc/Console` is the console. Anything else comes back as given."""
    text = (value or "").strip()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = re.sub(r"^[^@/]+@([^:/]+):", r"\1/", text)
    text = re.sub(r"\.git$", "", text.rstrip("/"))
    parts = [p for p in text.split("/") if p]
    return "/".join(parts[-2:]).lower() if len(parts) >= 2 else (value or "")


def gh_runs(cmd, command):
    """Every walked `gh` call in `cmd` whose `gh_args(...).command` is `command` (`("pr", "create")`, `("api",)`), in execution order, a `sh -c` payload and an `eval` included."""
    return [
        r
        for r in _analyse(cmd).runs
        if _base(r.name) == "gh" and gh_args(r.argv).command == tuple(command)
    ]


def gh_pr_runs(cmd, verb):
    """Every walked `gh pr <verb>` in `cmd`, whatever `pr`-level flags precede the verb."""
    return gh_runs(cmd, ("pr", verb))


def _origin_repo(cwd):
    """`OWNER/REPO` of the origin remote of `cwd`, else rediacc/console: `target_repo`'s last two steps."""
    repo = ""
    if cwd != "":
        # The pipeline's exit status is sed's, never git's, so a failed git here is indistinguishable from a repo with no origin: both leave `repo` empty and fall through to the default below.
        url = _git_stdout(["-C", cwd, "remote", "get-url", "origin"])
        records, terminated = _records(url)
        out = []
        for record in records:
            line = re.sub(r"\.git$", "", record)
            line = re.sub(r".*[:/]([^/]+/[^/]+)$", r"\1", line)
            out.append(line)
        repo = _command_substitution(_sed_out(out, terminated))
    return repo if repo != "" else GH_REPO


def _named(value):
    """`OWNER/REPO` for a non-empty `GH_REPO`/`--repo` value, `UNRESOLVED_REPO` for one the walk could not evaluate, None for an empty one (gh ignores it)."""
    if value is None or value == "":
        return None
    if unresolved(value) or value == _INHERITED:
        return UNRESOLVED_REPO
    return gh_repo_name(value)


def gh_named_repo(run, inherited=None):
    """The repository one walked `gh` call NAMES, as lowercase `OWNER/REPO`: its own `--repo`/`-R` in any spelling, else a non-empty `GH_REPO` in its environment, else the session's own `GH_REPO` (`inherited`). None when it names none of them, and its directory decides. `UNRESOLVED_REPO` when it names one this walk cannot evaluate (`-R $R` with R assigned nowhere in the command, `GH_REPO=$(...)`): each caller refuses or judges the strictest case, in its own guard's terms.

    gh's own order (pkg/cmd/factory `BaseRepo`): the flag overrides the variable, which overrides the git remotes; an empty `GH_REPO` is ignored. Measured 2026-10-07 through dispatch.py: `GH_REPO=rediacc/renet gh pr create -t x` was judged as a console create (rc=2) where `--repo rediacc/renet` was not (rc=0), in every guard that read the repo (#d2d5f89d). The flag and the variable are read EXPANDED (`run.xargv`, `run.env`), so `R=x; gh pr create -R $R` names x (#9de9a8e9).

    THE SESSION'S ENVIRONMENT, `inherited`, and why it is observable at all (#9de9a8e9). A caller passes `ev.env("GH_REPO")`, the hook process's own. Claude Code starts both the hook and the Bash tool's shell from its own environment: measured 2026-10-07, the Bash tool's shell is `bash -c 'source <shell snapshot> && <command>'` under the `claude` process, every variable name in that process's environment is also in the shell's (the shell only adds: `CLAUDECODE`, `BASH_ENV`, `PYTHONPATH` and a dozen more), and the snapshot exports nothing but PATH. An `export GH_REPO=x` in one Bash call does NOT reach the next (measured: a variable exported in one call read back unset in the next), so a command can only change it on its own line, which the walk reads. The one source that stays invisible is a `GH_REPO` exported by a profile the snapshot sources but this hook never runs; the snapshot exports PATH alone today.

    THE PRECEDENCE BELOW THE FLAG, in bash's terms. A `GH_REPO` in `run.env` (a prefix, `env NAME=`, an export, a known `unset`/`env -u`, which is None) is final. After `env -i` the command inherits nothing. A `GH_REPO` the command assigned without ever saying whether it is exported (`GH_REPO=x; gh ...`) reaches gh only if the session already exports it, as bash marks every inherited variable exported. Otherwise the session's own value stands.
    """
    argv = run.xargv if getattr(run, "xargv", None) is not None else run.argv
    flagged = gh_args(argv).last("repo")
    if flagged:
        return _named(flagged)
    env = getattr(run, "env", None) or {}
    if "GH_REPO" in env:
        value = env["GH_REPO"]
        return _named(inherited) if value == _INHERITED else _named(value)
    if _CLEARED in env:
        return None
    shadow = (getattr(run, "vars", None) or {}).get("GH_REPO")
    if shadow is not None:
        value, exported = shadow
        if exported is None and inherited:
            return _named(inherited) if value == _INHERITED else _named(value)
        return None
    return _named(inherited)


def gh_run_repo(run, cwd, inherited=None):
    """The repository one walked `gh` call targets: what it names (`gh_named_repo`: `--repo`/`-R` in any spelling, then `GH_REPO`, then the session's `inherited` one), then the private/<submodule> it runs in (its `cd`), then `cwd`'s origin, then rediacc/console. `target_repo`'s order, read from the call instead of from a text segment. `UNRESOLVED_REPO` passes through: the caller decides what an unknowable repo means."""
    named = gh_named_repo(run, inherited)
    if named:
        return named
    m = re.search(r"(^|/)private/(renet|account|elite|homebrew-tap)(/|$)", run.cwd or "")
    if m:
        return "rediacc/" + m.group(2)
    return _origin_repo(cwd)


def gh_api_method(parsed):
    """The HTTP method a parsed `gh api` call sends: `-X` in any spelling, else POST when it carries a field or `--input`, else GET (gh's own default)."""
    method = parsed.last("method")
    if method:
        return method.upper()
    if parsed.values("field") or parsed.values("raw-field") or parsed.values("input"):
        return "POST"
    return "GET"


def gh_api_endpoint(parsed, repo=None):
    """The endpoint operand of a parsed `gh api` call as a bare path (`repos/o/r/pulls/5`): a scheme and host (`https://api.github.com/`), the query string and the leading and trailing slashes dropped; "" when there is none.

    With `repo` (`OWNER/REPO`, from `gh_run_repo`), gh's `{owner}` and `{repo}` placeholders are filled from it, as gh fills them from the same `--repo`/`GH_REPO`/remote order.
    """
    if not parsed.operands:
        return ""
    path = re.sub(r"^https?://[^/]+/", "", parsed.operands[0]).split("?", 1)[0]
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        path = path.replace("{owner}", owner).replace("{repo}", name)
    return path.strip("/")


# --------------------------------------------------------------------------- the program an interpreter runs (worklist #c4542b69) ---------------------------------------------------------------------------
#
# A SCRIPT RUN BY PATH IS A PROGRAM, LIKE A HEREDOC (#f3f36655, #c4542b69). Three shell-write guards read an interpreter's program to judge what it writes, and each spelled "the program" its own way: the `-c` value, the heredoc bodies when it reads stdin, and (block_suppressions_shell_write only) a script passed by path. So `python3 scratch/edit.py` wrote a review file or a model-invocation key that
# the same program through `python3 - <<EOF` was refused for (rc 0 against rc 2, 2026-10-11). `interpreter_program` is the one reading. A script TRACKED by the checkout holding it AND unchanged from HEAD is not read: its text is reviewed code the CI gates already judge, and reading it would refuse every run of a tool that names the thing it guards (`worklist.py` carries 50 lint markers and writes files); an edited tracked script is read (review b922f15c.3).
# A script an earlier run of the SAME command writes is judged by what that run writes (`_written_scripts`, review b922f15c.1), and one written from a source this walk cannot read, or larger than `_SCRIPT_MAX`, is "unjudgeable", which each guard refuses once its pre-filter has matched (b922f15c.4). Only a script that does not exist at all FAILS OPEN: the interpreter fails on it, and the CI gates read the tree either way. `interpreter_scripts` is the cheap form a guard's pre-filter reads: it starts the lexer only when an interpreter is named, and runs one `git status` per script.
INTERPRETER_NAMES = ("python", "node", "perl", "ruby", "deno", "bun", "tsx")
# Why an "unjudgeable" program is refused, in the words each guard prints.
UNJUDGEABLE_REASON = (
    "the same command writes the script from a source this hook cannot read, or the script is "
    "larger than the hook reads; write it in one step and run it in the next, or use a heredoc"
)
# THE INTERPRETER'S OWN OPTIONS, PARSED AS IT PARSES THEM (review 63ee61e3.1). The first reading looked for `-c`, `-e` or `-E` anywhere in the argv, so python's `-E` (ignore PYTHON* variables, a plain flag) read as perl's inline program and `python3 -E scratch.py` wrote its marker unread, a `-c` among the SCRIPT's own arguments read as the interpreter's, and `-X dev` handed `dev` over as the script. Each family below
# is `(inline letters, module letters, letters taking a value, letters taking only an ATTACHED value, long options taking a value, long options that are the program)`, and the parse stops at the first operand, which is the script. Measured 2026-10-11 on Python 3.13, node v24.21.0 and perl 5.40.1: python `-E -I -B -u -q -s -P -OO` are flags, `-W`/`-X` take a value attached or as the next word; node takes the next word for every string option `node --help` lists with
# `=...` (a V8 flag such as `--stack-size` needs `=`); perl's `-I`/`-M`/`-m` take the next word and `-0 -l -i -F -C -x -d -D` only an attached one. Ruby's table is from its documentation (no ruby on this host); deno, bun and tsx skip a leading `run` and otherwise read like node.
_NODE_VALUE_LONG = frozenset(
    [
        "allow-fs-read",
        "allow-fs-write",
        "build-snapshot-config",
        "conditions",
        "cpu-prof-dir",
        "cpu-prof-interval",
        "cpu-prof-name",
        "diagnostic-dir",
        "disable-proto",
        "disable-warning",
        "dns-result-order",
        "env-file",
        "env-file-if-exists",
        "experimental-config-file",
        "experimental-loader",
        "loader",
        "experimental-package-map",
        "experimental-sea-config",
        "experimental-test-tag-filter",
        "heap-prof-dir",
        "heap-prof-interval",
        "heap-prof-name",
        "heapsnapshot-near-heap-limit",
        "heapsnapshot-signal",
        "icu-data-dir",
        "import",
        "input-type",
        "inspect-publish-uid",
        "localstorage-file",
        "max-http-header-size",
        "max-old-space-size-percentage",
        "network-family-autoselection-attempt-timeout",
        "openssl-config",
        "redirect-warnings",
        "report-dir",
        "report-filename",
        "report-signal",
        "require",
        "run",
        "secure-heap",
        "secure-heap-min",
        "snapshot-blob",
        "test-concurrency",
        "test-coverage-branches",
        "test-coverage-exclude",
        "test-coverage-functions",
        "test-coverage-include",
        "test-coverage-lines",
        "test-global-setup",
        "test-isolation",
        "test-name-pattern",
        "test-random-seed",
        "test-reporter",
        "test-reporter-destination",
        "test-rerun-failures",
        "test-shard",
        "test-skip-pattern",
        "test-timeout",
        "title",
        "tls-cipher-list",
        "tls-keylog",
        "trace-event-categories",
        "trace-event-file-pattern",
        "trace-require-module",
        "unhandled-rejections",
        "use-largepages",
        "v8-pool-size",
        "watch-kill-signal",
        "watch-path",
    ]
)
# The seventh field is the letters whose attached value is DIGITS only, after which the bundle goes on: perl's `-l0e` and `-0777e` run the program after `e` (measured).
_PROGRAM_OPTIONS = {
    "python": ("c", "m", "WX", "", frozenset(("check-hash-based-pycs",)), frozenset(), ""),
    "node": ("ep", "", "rC", "", _NODE_VALUE_LONG, frozenset(("eval", "print")), ""),
    "perl": ("eE", "", "IMm", "iFCxdD", frozenset(), frozenset(), "0l"),
    "ruby": (
        "e",
        "",
        "IrCEF",
        "xK",
        frozenset(("encoding", "external-encoding", "internal-encoding")),
        frozenset(),
        "0WT",
    ),
}
_RUNNERS = ("deno", "bun", "tsx")
# The largest script read whole (review b922f15c.4): a bigger one is UNJUDGEABLE, never skipped.
_SCRIPT_MAX = 16 << 20


def _program_parse(base, argv):
    """`(kind, value)` for an interpreter's argv as the interpreter reads it: ("inline", program), ("module", None), ("stdin", None) or ("file", script path)."""
    family = next((f for f in _PROGRAM_OPTIONS if base.startswith(f)), "node")
    inline, module, value, attached, value_long, inline_long, digits = _PROGRAM_OPTIONS[family]
    k = 0
    if base.startswith(_RUNNERS) and argv[:1] == ["run"]:
        k = 1
    while k < len(argv):
        arg = argv[k]
        k += 1
        if arg == "--":
            break
        if arg == "-":
            return "stdin", None
        if arg.startswith("--"):
            name, eq, given = arg[2:].partition("=")
            if name in inline_long:
                return "inline", given if eq else (argv[k] if k < len(argv) else "")
            if name in value_long and not eq:
                k += 1
            continue
        if arg.startswith("-") and len(arg) > 1:
            at = 1
            while at < len(arg):
                letter = arg[at]
                rest = arg[at + 1 :]
                at += 1
                if letter in digits:
                    while at < len(arg) and arg[at].isdigit():
                        at += 1
                    continue
                if letter in inline:
                    return "inline", rest or (argv[k] if k < len(argv) else "")
                if letter in module:
                    return "module", None
                if letter in value:
                    k += 0 if rest else 1
                    break
                if letter in attached:
                    break
            continue
        k -= 1
        break
    if k >= len(argv):
        return "stdin", None
    return "file", argv[k]


def _script_path(path, run_cwd, cwd):
    base = cwd or os.getcwd()
    if run_cwd is not None:
        base = os.path.join(base, run_cwd)
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))


# Asked once per file per process: a chain runs every guard in one process and the user-only guard asks three times. Keyed by the file's mtime and size, so an edit is asked again; a commit that leaves the file untouched keeps the older answer, which only ever reads a script it could have skipped.
_TRACKED_CACHE: dict = {}


def _tracked_unchanged(target):
    """True only when a checkout tracks `target` AND its working copy matches HEAD (review b922f15c.3): `git status --porcelain --ignored` prints nothing for exactly that file, and prints `??`, `!!`, ` M` or `M ` for an untracked, ignored, edited or staged one. Outside any checkout git fails, which is False."""
    stat = os.stat(target)
    key = (target, stat.st_mtime_ns, stat.st_size)
    if key not in _TRACKED_CACHE:
        done = subprocess.run(
            # Literal (review fc3f376a.1): measured on git 2.53.0, a glob pathspec still reports an untracked `s[1].py` by its exact name, but it also matches an edited `s1.py` beside it, which denied the exemption to an unchanged tracked script.
            [
                "git",
                "--literal-pathspecs",
                "status",
                "--porcelain",
                "--ignored",
                "--",
                os.path.basename(target),
            ],
            cwd=os.path.dirname(target) or ".",
            capture_output=True,
            check=False,
        )
        _TRACKED_CACHE[key] = done.returncode == 0 and not done.stdout.strip()
    return _TRACKED_CACHE[key]


def _script_file_text(path, run_cwd, cwd):
    """`(text, state)` for a script an interpreter runs by path: "read", "exempt" (tracked and unchanged), "missing" (no such file, or unreadable) or "unjudgeable" (larger than `_SCRIPT_MAX`)."""
    target = _script_path(path, run_cwd, cwd)
    try:
        if not os.path.isfile(target):
            return None, "missing"
        if _tracked_unchanged(target):
            return None, "exempt"
        if os.path.getsize(target) > _SCRIPT_MAX:
            return None, "unjudgeable"
        with open(target, encoding="utf-8", errors="replace") as handle:
            return handle.read(), "read"
    except OSError:
        return None, "missing"


# A SCRIPT THE SAME COMMAND WRITES IS JUDGED BY WHAT IT WRITES (review b922f15c.1). `cat > /tmp/s.py <<'EOF' ... EOF; python3 /tmp/s.py` ran a program no guard read: the file did not exist when the hook ran, so the read found nothing and failed open, while the same program as a heredoc was refused. `_written_scripts` walks the runs BEFORE the interpreter and records each file they write: a redirect or `tee` from a writer
# (`cat` with no file operand, `echo`, `printf`, `tee`) writes the run's feed (its heredoc, here-string or piped words) and its arguments, every write adding to the record; anything else written there (a copy, `sed -i`, `dd of=`, `cat other.py >`, any other command's output) is UNKNOWN, and a program read from an unknown write is "unjudgeable", which each guard refuses once its own pre-filter has matched the command.
_TEXT_WRITERS = ("echo", "printf", "cat", "tee")


_HEREDOC_EXPANSION = re.compile(
    r"\\\n|\\([$`\\])|\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)|\$[({0-9@*#?$!-]|`"
)


def _expand_heredoc(body, shell):
    """An UNQUOTED heredoc's body as bash hands it over under the walk's shell state, or None when a part of it cannot be known here: `$NAME` and `${NAME}` are the value an earlier statement gave, `\\$`, a backslashed backtick and `\\\\` are the character, a backslash before a newline joins the lines, and a `$(...)`, a backtick, a `${...}` with an operator, a positional or special parameter, or a name only the session's environment knows is unknown."""
    unknown: list[str] = []

    def one(m):
        if m.group(0) == "\\\n":
            return ""
        if m.group(1):
            return m.group(1)
        name = m.group(2) or m.group(3)
        value = _var(name, shell) if name else _UNRESOLVED
        if _UNRESOLVED in value:
            unknown.append(m.group(0))
        return value

    out = _HEREDOC_EXPANSION.sub(one, body)
    return None if unknown else out


# The escapes `printf` reads in its format (and `echo -e` in its words), bash 5: `\\xHH`, `\\NNN` and `\\0NNN` octal, `\\uHHHH`, `\\UHHHHHHHH`, and the one-letter ones.
_PRINTED_ESCAPE = re.compile(
    r"\\(?:x([0-9A-Fa-f]{1,2})|(0[0-7]{0,3}|[0-7]{1,3})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([abefnrtv\\\"']))"
)
_ONE_LETTER = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}


def printed_escapes(text):
    """`text` with the backslash escapes a printing command turns into characters turned into them (review 13505e0b.1): `printf '\\x23 x'` prints `# x`, and read as typed the `#` was never there to judge. The text a guard judges is the decoded one, in place of the typed one. A word `printf` would print untouched (a `%s` argument, an `echo` without `-e`) is decoded too when it sits beside one that is; that reads a character the command would not print, the direction that refuses rather than allows."""

    def one(m):
        if m.group(1):
            return chr(int(m.group(1), 16))
        if m.group(2):
            return chr(int(m.group(2), 8) & 0xFF)
        code = m.group(3) or m.group(4)
        if code:
            value = int(code, 16)
            return chr(value) if value < 0x110000 else m.group(0)
        return _ONE_LETTER.get(m.group(5), m.group(5))

    return _PRINTED_ESCAPE.sub(one, text) if "\\" in text else text


def stdin_text(run, cmd):
    """What arrives on a run's stdin (`_Run.feed`), as bash hands it over, or None when any of it is unknown (review 7837d22e.1).

    A QUOTED heredoc's body is literal. An UNQUOTED one is expanded by bash, so it is expanded here with what the walk resolved (`_expand_heredoc`): `M=x; prog <<EOF` with a body line `$M` hands over `x`, where the raw body read `$M`. A `$` or a backtick anywhere else in the feed (a here-string, the words of the stage in front) is not expanded here and leaves the text unknown.

    THE STAGE IN FRONT IS READ AS ITS WORDS, NOT ITS OUTPUT (`_Run.feed`): what a producer prints is not computed. One thing its words say about its output is read all the same: EVERY backslash escape outside a heredoc is turned into the character it names (`printed_escapes`, review 13505e0b.1), since `printf '\\x23 ...' | prog` hands over a `#` that the typed words never held. That is every one, not only a `printf`'s or an `echo -e`'s (648366c8.2): the feed is text with no record of which command typed which word, and any producer may print its escapes (`python3 -c 'print("\\x23 ...")' | prog`), so an `echo` without `-e` and a here-string are decoded as well. For those two the decoded character is one the command would not print, which can refuse a feed that is marker-free as printed and can never allow one that is not. A heredoc's backslashes are bash's own and are left as `_expand_heredoc` gives them.
    """
    feed = run.feed or ""
    if "$" not in feed and "`" not in feed and "\\" not in feed:
        return feed
    kept: list[str] = []
    rest = feed
    for doc in _analyse(cmd).heredocs:
        if doc.body_start is None or doc.body_end is None:
            continue
        body = cmd[doc.body_start : doc.body_end]
        if not body or body not in rest:
            continue
        text = body if doc.quoted else _expand_heredoc(body, run.vars)
        if text is None:
            return None
        rest = rest.replace(body, "\x00%d\x00" % len(kept), 1)
        kept.append(text)
    if "$" in rest or "`" in rest:
        return None
    rest = printed_escapes(rest)
    for k, text in enumerate(kept):
        rest = rest.replace("\x00%d\x00" % k, text, 1)
    return rest


def writer_text(run, cmd):
    """The text a writer run (`echo`, `printf`, `tee`, or `cat` with no file operand) puts out, as bash hands it over, or None when it is not one, or when any of it is unexpanded (review fc3f376a.2).

    Its words are read expanded (`xargv`: `F=x; echo "$F"` puts out `x`), never as typed: recorded verbatim, `echo "$F" > s.py` was the four characters `"$F"`, so the program it wrote ran unjudged. Its feed (a heredoc, a here-string, the words of the pipeline in front of it) is read as `stdin_text` gives it: a quoted heredoc literal, an unquoted one expanded with what the walk resolved, and unknown when a `$` or a backtick is left anywhere else. A `printf`'s own words, and an `echo -e`'s, are read with their backslash escapes printed (`printed_escapes`). Anything the walk could not expand makes the whole text None, which a guard reads as unjudgeable.
    """
    base = run.name.rsplit("/", 1)[-1]
    argv = list(run.argv)
    if base not in _TEXT_WRITERS or (base == "cat" and any(not a.startswith("-") for a in argv)):
        return None
    # No expanded argv means no expansion was done; the typed words are then not what bash writes, so the text is unknown, never the typed words (review 094dea3b.6). `_Walker.element` sets `xargv` on every run it builds, so this is the fail-closed answer for a run built any other way.
    if run.xargv is None:
        return None
    words = run.xargv
    if any(_UNRESOLVED in w for w in words):
        return None
    feed = stdin_text(run, cmd)
    if feed is None:
        return None
    # What `printf` prints for an escape in its format, and `echo -e` for one in its words, is the character (review 13505e0b.1 sweep: `printf '\\x23 ...' >> a.py` was judged as the typed four characters).
    own = " ".join(words)
    if base == "printf" or (
        base == "echo" and any(re.fullmatch(r"-[neE]*e[neE]*", w) for w in words)
    ):
        own = printed_escapes(own)
    return "\n".join(f for f in [feed, own] if f)


def _written_scripts(cmd, until, cwd):
    """`{absolute path: text or None}` for every file the runs of `cmd` before `until` write; None is a write whose content this walk cannot read."""
    out: dict = {}

    def record(path, run_cwd, text):
        target = _script_path(path, run_cwd, cwd)
        if text is None or (target in out and out[target] is None):
            out[target] = None
        else:
            out[target] = (out.get(target) or "") + text + "\n"

    for run in every_run(cmd):
        if run is until:
            break
        base = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        text = writer_text(run, cmd)
        for target in run.writes:
            record(target, run.cwd, text)
        if base == "tee":
            for target in [a for a in argv if not (a.startswith("-") and len(a) > 1)]:
                record(target, run.cwd, text)
        copies = run_copies(run)
        for dest in copies[1] if copies is not None else []:
            record(dest, run.cwd, None)
        edit = in_place_edit(run)
        for target in edit[1] if edit is not None else []:
            record(target, run.cwd, None)
        if base == "dd":
            for a in argv:
                if a.startswith("of="):
                    record(a[3:], run.cwd, None)
    return out


def interpreter_program(run, cmd, cwd=None):
    """`(text, kind)` for the program an interpreter run executes, or `(None, None)`.

    `kind` is "inline" (`-c`/`-e` and their spellings), "stdin" (every heredoc body of `cmd`, when the run reads its program from stdin: no operand, or `-`), "file" (a script passed by path: what an earlier run of the same command wrote into it, else the file on disk, under the rules above) or "unjudgeable" (`(None, "unjudgeable")`: an earlier run wrote the script from a source this walk cannot read, or the file is larger than `_SCRIPT_MAX`). A module run (`python -m x`), a tracked and unchanged script, and one that does not exist are `(None, None)`. `cwd` is the directory the command runs in; a run that `cd`'d is resolved from its own `run.cwd` under it.
    """
    if not run.name.rsplit("/", 1)[-1].startswith(INTERPRETER_NAMES):
        return None, None
    kind, value = _program_parse(run.name.rsplit("/", 1)[-1], list(run.argv))
    if kind == "inline":
        return value, "inline"
    if kind == "module":
        return None, None
    if kind == "stdin":
        analysis = _analyse(cmd)
        bodies = [
            cmd[doc.body_start : doc.body_end]
            for doc in analysis.heredocs
            if doc.body_start is not None and doc.body_end is not None
        ]
        return "\n".join(bodies), "stdin"
    written = _written_scripts(cmd, run, cwd)
    target = _script_path(value, run.cwd, cwd)
    if target in written:
        return (written[target], "file") if written[target] is not None else (None, "unjudgeable")
    text, state = _script_file_text(value, run.cwd, cwd)
    if state == "read":
        return text, "file"
    if state == "unjudgeable":
        return None, "unjudgeable"
    return None, None


def interpreter_scripts(cmd, cwd=None):
    """The text of every script `cmd` runs BY PATH (`interpreter_program`'s "file" kind), for a guard's pre-filter: a command naming no interpreter never starts the lexer."""
    if not re.search(r"python|node|perl|ruby|deno|bun|tsx", cmd):
        return []
    out = []
    for run in every_run(cmd):
        text, kind = interpreter_program(run, cmd, cwd)
        if kind == "file":
            out.append(text)
    return out


# --------------------------------------------------------------------------- is this sed or perl editing in place (review 3f53e99e.2) ---------------------------------------------------------------------------
#
# IN PLACE IS THE TOOL'S OWN OPTION PARSE, NOT A WORD TEST. Five guards asked "is this sed/perl in place" as `a == "-i" or a.startswith("-i")`, so the bundles both tools accept were read as not in place: `sed -Ei`, `sed -ni` and `perl -pi -e` rewrote the model-invocation key into a command file unrefused (2026-10-11). Two others read any `i` in a bundle, which also caught the `i` inside an attached `-e` script. `in_place_edit` reads the argv the way each tool does,
# measured on GNU sed 4.9 and perl 5.40.1: sed's `i` takes the REST of its bundle as a backup suffix (`-ie` is in place with suffix `e`, and the next word is the script), `-e`/`-f`/`-l` take the rest or the next word, a long option resolves by unique prefix (`--in` is `--in-place`), and with no `-e`/`-f` the first operand is the script; perl's `-i` also takes the rest of its bundle, `-e`/`-E` take the rest or the next word and
# switch parsing goes on after them, `-0`/`-l`/`-C` take digits and the bundle continues (`-l0pi` is in place), `-I`/`-M`/`-m` take the rest or the next word, `-D`/`-d`/`-F`/`-x` the rest, and without `-e` the first operand is the program file.
_SED_LONG = {
    "in-place": "o",
    "expression": "r",
    "file": "r",
    "line-length": "r",
    **dict.fromkeys(
        [
            "null-data",
            "zero-terminated",
            "separate",
            "posix",
            "debug",
            "sandbox",
            "regexp-extended",
            "quiet",
            "silent",
            "unbuffered",
            "follow-symlinks",
            "binary",
            "help",
            "version",
        ],
        "n",
    ),
}


def _sed_in_place(argv):
    in_place = False
    scripts: list[str] = []
    script_files = False
    operands: list[str] = []
    k = 0
    while k < len(argv):
        arg = argv[k]
        k += 1
        if arg == "--":
            operands.extend(argv[k:])
            break
        if arg.startswith("--"):
            key, eq, value = arg[2:].partition("=")
            hits = [n for n in _SED_LONG if n == key] or [n for n in _SED_LONG if n.startswith(key)]
            name = hits[0] if len(hits) == 1 else key
            if _SED_LONG.get(name) == "r" and not eq and k < len(argv):
                value = argv[k]
                k += 1
            if name == "in-place":
                in_place = True
            elif name == "expression":
                scripts.append(value)
            elif name == "file":
                script_files = True
            continue
        if arg.startswith("-") and len(arg) > 1:
            for at, letter in enumerate(arg[1:], 1):
                rest = arg[at + 1 :]
                if letter == "i":
                    in_place = True
                    break
                if letter in "efl":
                    value = rest
                    if not value and k < len(argv):
                        value = argv[k]
                        k += 1
                    if letter == "e":
                        scripts.append(value)
                    elif letter == "f":
                        script_files = True
                    break
            continue
        operands.append(arg)
    if not scripts and not script_files and operands:
        scripts.append(operands.pop(0))
    return in_place, scripts, operands


def _perl_in_place(argv):
    in_place = False
    programs: list[str] = []
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg == "--":
            k += 1
            break
        if not arg.startswith("-") or len(arg) == 1:
            break
        k += 1
        at = 1
        while at < len(arg):
            letter = arg[at]
            rest = arg[at + 1 :]
            at += 1
            if letter in "0lC":
                while at < len(arg) and arg[at].isdigit():
                    at += 1
                continue
            if letter == "i":
                in_place = True
                break
            if letter in "eEIMm":
                value = rest
                if not value and k < len(argv):
                    value = argv[k]
                    k += 1
                if letter in "eE":
                    programs.append(value)
                break
            if letter in "DdFx":
                break
    operands = list(argv[k:])
    if not programs and operands:
        operands.pop(0)  # the program file
    return in_place, programs, operands


def in_place_edit(run):
    """`(scripts, files)` for a sed or perl run that edits files IN PLACE, or None for any other run. `scripts` are the sed scripts or perl `-e` programs written on the command line; `files` the operands it rewrites."""
    base = run.name.rsplit("/", 1)[-1]
    argv = list(run.argv)
    if base in ("sed", "gsed"):
        in_place, scripts, files = _sed_in_place(argv)
    elif base.startswith("perl"):
        in_place, scripts, files = _perl_in_place(argv)
    else:
        return None
    return (scripts, files) if in_place else None
