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

import json
import os
import posixpath
import re
import subprocess
import typing

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
def _wrapper_payload(text):
    records, _ = _records(text)
    for record in records:
        # awk: n = split($0, tok, /[ \t]+/). A REGEX separator, so unlike the
        # default " " separator it does NOT trim: a leading blank yields an empty tok[1], and that empty token is why the join below can emit a leading space. Python's re.split on "" would give one empty field where awk gives zero, hence the guard.
        tok = re.split(r"[ \t]+", record) if record != "" else []
        n = len(tok)
        for i in range(n):
            if tok[i] == "eval":
                out = "".join(tok[j] + (" " if j < n - 1 else "") for j in range(i + 1, n))
                # awk `print` then `exit`: one record, ORS appended, and the whole input abandoned -- later records are never read.
                return out + "\n"
            name = tok[i]
            name = re.sub(r"[\"']", "", name)
            # awk's sub(/.*\//) is greedy and leftmost-longest, so this strips through the LAST slash. Python's greedy `.*` lands in the same
            # place; count=1 keeps it a `sub` and not a `gsub`.
            name = re.sub(r".*/", "", name, count=1)
            if re.search(r"^(sh|bash|dash|zsh|ash|ksh)$", name):
                for j in range(i + 1, n):
                    t = tok[j]
                    if t == "-c" or re.search(r"^-[^-].*c$", t):
                        out = "".join(tok[m] + (" " if m < n - 1 else "") for m in range(j + 1, n))
                        return out + "\n"
                # NO `exit` HERE, and that is load-bearing: a shell name whose token run carries no -c selector falls back to the OUTER loop, so `bash script.sh; sh -c 'gh pr merge'` still finds the second one.
    return ""


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
    out = []
    for record in records:
        line = re.sub(r"'[^']*'", "", record)
        line = re.sub(r'"[^"]*"', "", line)
        out.append(line)
    return _sed_out(out, terminated)


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
    if repo == "" and cwd != "":
        # The pipeline's exit status is sed's, never git's, so a failed git here is indistinguishable from a repo with no origin: both leave `repo` empty and fall through to the default below.
        url = _git_stdout(["-C", cwd, "remote", "get-url", "origin"])
        records, terminated = _records(url)
        out = []
        for record in records:
            line = re.sub(r"\.git$", "", record)
            line = re.sub(r".*[:/]([^/]+/[^/]+)$", r"\1", line)
            out.append(line)
        repo = _command_substitution(_sed_out(out, terminated))
    return repo if repo != "" else "rediacc/console"


# pr_selector <segment> <verb> The PR selector (number/url/branch) belongs to the same invocation as the verb -- read it from the segment, never from the line.
def pr_selector(seg, verb):
    # `sed -n "s/.*gh pr ${verb}[[:space:]]*//p"`: `.*` is greedy, so on a
    # segment naming the verb twice this cuts at the LAST one, and `-n ... p` means non-matching lines are dropped rather than passed through.
    cut = re.compile(r".*gh pr " + verb + r"[" + SPACE + r"]*")
    records, _ = _records(_printf_line(seg))
    kept = []
    for record in records:
        new, count = cut.subn("", record, count=1)
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
    if gits:
        dirs = [r.git_dir for r in gits]
    elif runs:
        dirs = [runs[-1].cwd]
    else:
        dirs = []
    roots = set()
    for directory in dict.fromkeys(dirs):
        roots.add(_resolve_root(directory, this_root))
        if len(roots) > 1:
            return ""
    return roots.pop() if roots else ""


def _resolve_root(directory, this_root):
    """The toplevel of the repository `directory` sits in, or "" when that is this root or nothing resolves.

    bash `case "$hint" in /*) ... ;; *) ...` -- a leading slash, nothing more elaborate. A `~` or a `$HOME` is NOT expanded here, so it never resolves.
    """
    if directory is None or directory in ("", "."):
        return ""
    abs_path = directory if directory.startswith("/") else this_root + "/" + directory
    target = _git_stdout(["-C", abs_path, "rev-parse", "--show-toplevel"], want_rc=True)
    if target is None:
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


def repo_root_env():
    """`CLAUDE_PROJECT_DIR`, the root every guard passes as `this_root`.

    Not part of the bash lib -- each guard computes it itself -- but every caller of `target_root` needs the same answer, and a second spelling of it is exactly the drift `.ci/rediacc_ci/paths.py` was written to end.
    """
    return os.environ.get("CLAUDE_PROJECT_DIR", "")


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
# Prefix commands that run the NEXT word as the command, with the options each one takes a value for. `command -v`/`-V` only prints, so it is handled apart.
_PREFIX_COMMANDS = {
    "command": frozenset(),
    "builtin": frozenset(),
    "exec": frozenset(("-a",)),
    "time": frozenset(),
    "nohup": frozenset(),
    "setsid": frozenset(),
    "env": frozenset(("-u", "--unset", "-C", "--chdir", "-S", "--split-string")),
    "sudo": frozenset(("-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "-R")),
    "nice": frozenset(("-n", "--adjustment")),
    "timeout": frozenset(("-s", "--signal", "-k", "--kill-after")),
    "stdbuf": frozenset(("-i", "-o", "-e")),
    "xargs": frozenset(
        ("-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a", "--max-args", "--delimiter")
    ),
}
# A prefix command that takes one positional operand before the command it runs.
_PREFIX_OPERAND = frozenset(("timeout",))
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
    __slots__ = ("heredoc", "op", "target")

    def __init__(self, op, target, heredoc=None):
        self.op = op
        self.target = target
        self.heredoc = heredoc


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
        if j < limit and src[j] not in "\n;&|()<>":
            target, j = self._word(j, limit)
        heredoc = None
        if op in ("<<", "<<-") and target is not None:
            quoted = any(p.kind in ("sq", "dq", "esc", "ansi") for p in target.parts)
            heredoc = _Heredoc(_word_value(target), quoted, op == "<<-")
            self.pending.append(heredoc)
            self.heredocs.append(heredoc)
        toks.append(_Redir(op, target, heredoc))
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

    __slots__ = ("argv", "canonical", "cwd", "git_dir", "git_sub", "name", "usage", "writes")

    def __init__(self, name, argv, canonical, cwd):
        self.name = name
        self.argv = argv
        self.canonical = canonical
        self.cwd = cwd
        self.git_dir = None
        self.git_sub = None
        # How the command's RESULT is consumed: "status" when its exit status decides something (`&&`, `||`, `if`/`while`/`until`/`!`, a `$?` in the next clause), "kill" when its output feeds a `kill` (`kill $(...)`, `| xargs kill`). `block_self_matching_pgrep` reads it: a self-matching `pgrep -f` only costs something when one of these is true.
        self.usage = set()
        # The files this command's own output redirects write, in order, quote-removed. `earlier_mutators` reads them: a `printf ... > msg` before a `git commit -F msg` changes what a guard judging the commit reads.
        self.writes = []


class _Analysis:
    """What one walk found: `runs` in execution order, `heredocs` read, and `writes`, every output redirect bash performs as `(operator, target)` with the target quote-removed."""

    __slots__ = ("heredocs", "runs", "writes")

    def __init__(self):
        self.runs: list = []
        self.heredocs: list = []
        self.writes: list = []


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


def _strip_prefixes(words):
    """Drop reserved words, assignments and prefix commands from the front of a simple command.

    Returns `(words, prefixed)`; `words` is empty when nothing runs (a bare assignment, `command -v x`, a `for` clause). A0 L9: every one of these puts a word between the command position and the command, and every anchor in every guard stops there.
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
        takes = _PREFIX_COMMANDS[name]
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
                k += 2 if arg in takes else 1
                continue
            break
        if name in _PREFIX_OPERAND and k < len(words):
            k += 1
    return words[k:], prefixed


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
        if arg in (
            "-c",
            "--git-dir",
            "--work-tree",
            "--namespace",
            "--super-prefix",
            "--config-env",
            "--exec-path",
        ) and k + 1 < len(argv):
            k += 2
            continue
        if arg.startswith("-"):
            k += 1
            continue
        return arg, here
    return "", here


def _base(name):
    return name.rsplit("/", 1)[-1]


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

    def text(self, src, cwd, persist):
        """Walk a command string. `persist` says whether a `cd` in it outlives it (an `eval` does; a `sh -c` does not)."""
        if self.depth >= _MAX_DEPTH or src == "":
            return cwd
        lexer = _Lexer(src)
        toks = lexer.tokens()
        self.analysis.heredocs.extend(lexer.heredocs)
        inner = _Walker(self.analysis, self.depth + 1)
        state = [cwd]
        inner.items(_parse(toks), state, lexer)
        return state[0] if persist else cwd

    def items(self, items, state, lexer):
        runs = self.analysis.runs
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
                own = [state[0]] if isolated else state
                start = len(runs)
                self.element(
                    stage,
                    own,
                    lexer,
                    stages[pos - 1] if pos else None,
                    tested=tested and pos == len(stages) - 1,
                )
                spans.append((start, len(runs)))
            # `pgrep -f x | xargs kill`: a later stage that kills consumes every earlier stage's output as pids.
            for pos in range(1, len(spans)):
                if any(_base(r.name) == "kill" for r in runs[spans[pos][0] : spans[pos][1]]):
                    for r in runs[spans[0][0] : spans[pos][0]]:
                        r.usage.add("kill")

    def element(self, stage, state, lexer, upstream, tested=False):
        kind = stage[0]
        if kind == "sub":
            self.items(stage[1], [state[0]], lexer)
            self.redirs(stage[2], state, lexer)
            return
        if kind == "brace":
            self.items(stage[1], state, lexer)
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
        words, _prefixed = _strip_prefixes(words)
        if not words:
            return
        name = _word_value(words[0])
        if name == "" or any(ch in name for ch in " \t\n"):
            return
        argv = [_word_value(w) for w in words[1:]]
        rendered = [r for r in (_word_render(w) for w in words[1:]) if r != ""]
        run = _Run(name, argv, " ".join([name, *rendered]), state[0])
        run.writes = own_writes
        if tested or any(w in ("if", "elif", "while", "until", "!") for w in lead):
            run.usage.add("status")
        base = name.rsplit("/", 1)[-1]
        # `kill $(pgrep -f x)`: the substitutions in a kill's own words produced its pids.
        if base == "kill":
            for inner in self.analysis.runs[first_inner:]:
                inner.usage.add("kill")
        self.analysis.runs.append(run)
        if base in ("cd", "pushd"):
            operands = [a for a in argv if not (a.startswith("-") and len(a) > 1)]
            # `cd` with no operand, `cd -` and `cd ~` land somewhere this walk cannot name; an unresolvable directory makes every caller keep judging its own root, the direction the guards fail safe in.
            target = operands[0] if operands else "~"
            state[0] = _join_dir(state[0], target)
        elif base == "git":
            run.git_sub, run.git_dir = _git_invocation(argv, state[0])
        elif base == "eval":
            state[0] = self.nested(" ".join(argv), state[0], persist=True)
        elif base in SHELL_NAMES:
            mode, payload = _shell_payload(argv)
            if mode == "c" and payload is not None:
                self.nested(payload, state[0], persist=False)
            elif mode == "stdin":
                self.stdin(redirs, lexer, state, upstream)

    def stdin(self, redirs, lexer, state, upstream):
        """A shell reading its script from stdin runs whatever arrives there (A0 L4): a heredoc body, a here-string, or the output of `cat <<EOF`/`echo` upstream in the pipe."""
        for redir in redirs:
            if redir.heredoc is not None and redir.heredoc.body_start is not None:
                hd = redir.heredoc
                self.nested(lexer.src[hd.body_start : hd.body_end], state[0], persist=False)
            elif redir.op == "<<<" and redir.target is not None:
                self.nested(_word_value(redir.target), state[0], persist=False)
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
                    self.nested(lexer.src[hd.body_start : hd.body_end], state[0], persist=False)
                elif redir.op == "<<<" and redir.target is not None:
                    self.nested(_word_value(redir.target), state[0], persist=False)
        elif feeder in ("echo", "printf"):
            args = [_word_value(w) for w in words[1:]]
            while args and feeder == "echo" and re.match(r"^-[neE]+$", args[0]):
                args = args[1:]
            self.nested(" ".join(args), state[0], persist=False)

    def nested(self, src, cwd, persist):
        return _Walker(self.analysis, self.depth + 1).text(src, cwd, persist)

    def redirs(self, redirs, state, lexer):
        for redir in redirs:
            if redir.target is not None:
                self.parts(redir.target.parts, state, lexer)
                if redir.op in _WRITE_OPS:
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
                inner.items(_parse(part.sub), [state[0]], lexer)
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


def lifted_commands(cmd, view):
    """The canonical line of every command bash runs in `cmd` that `view` does not already show at a command position.

    `view` is whatever text the caller's regexes run over. `scan_target` passes its own prose-stripped line plus wrapper payload; `block_git_amend`, which builds its own view, passes that. The lines come back in the order bash would run the commands, each once.
    """
    segments = _anchored_segments(view)
    out: list[str] = []
    for run in _analyse(cmd).runs:
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
