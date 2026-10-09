"""The real-bash facts the hook scanner relies on, asked of bash itself (PLAN-retire-bash-oracles A0, kept by the operator's 2026-09-24 ruling).

WHY THIS SUITE EXISTS AFTER THE ORACLES ARE GONE. The differentials compared the Python port with the bash port it replaced, so they proved the two AGREED, never that either was RIGHT about bash; A0 measured fifteen fail-open shapes both got wrong together (agent/plans/PLAN-retire-bash-oracles.A0.md section 1). What is worth keeping from real-bash execution is therefore not a twin but the FACTS: how bash tokenises, quotes, expands and runs the command line a guard reasons about. Each row below is one such fact, run through a real `bash -c` (or `bash -n`, or a script file), and then asked of the scanner in-process. A bash upgrade that changes a fact fails the first test and names the Python that leans on it; a scanner change that stops agreeing with bash fails the second.

THE ENVIRONMENT IS BUILT, NEVER INHERITED. The interpreter is resolved once with `bash --norc --noprofile -c 'printf %s "$BASH"'` and called by absolute path, because `bash` on PATH may be a wrapper that re-execs the real one as a child (block_edit_of_running_script.py records the `bashcov-sup` wrapper that does exactly that on the host this was written on). Every run uses `--norc --noprofile`, `PATH=<stubs>:/usr/bin:/bin`, `LC_ALL=C` and a scratch `HOME`, with `BASH_ENV` and `ENV` removed, since either would source a profile into every non-interactive bash. The two stubs, `zzrun` (prints `RAN:` and its arguments joined by `|`) and `zzargv` (prints `<a><b>...`), are `#!/bin/sh` scripts so that `sh -c`, `eval` and nested shells see them too. Neither is named `gh` or `git`: no side effects, and no live pre-bash guard refuses a hand-run probe.

NOTHING HERE ASSERTS ON STDERR. Bash's diagnostic wording moves between versions (an unterminated heredoc's warning, the exit code of a syntax error), and no hook parses it. A bash-less host FAILS rather than skips: running bash is the whole point.

THE ROWS. The IDs follow A0 section 3's tables, with one rename: A0 numbers the separator table S1-S6, which collides with its S1-S3 safe-direction divergences, so those six are SEP1-SEP6 here. Q7 and X1/X2 carry several probes and are split into lettered rows. Every row whose A0 status was `contradicted:L<n>` is a plain passing row now, because A4 fixed L1-L15. The one remaining divergence, S3 (bash splits words on space, tab and newline only, while `shellscan.SPACE` also counts CR, VT and FF), is safe-direction and deliberately kept (see A0 and PLAN-retire-bash-oracles A4); row Q11 PINS it rather than xfailing it, because `check:ci-pytest` counts an xfail as a test that did not pass.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field

import pytest

from rediacc_hooks import dispatch, guards, hookio, shellscan

HOOKS = pathlib.Path(__file__).resolve().parents[1]

ZZRUN = "#!/bin/sh\nIFS='|'\nprintf 'RAN:%s\\n' \"$*\"\n"
ZZARGV = "#!/bin/sh\nfor a in \"$@\"; do printf '<%s>' \"$a\"; done\nprintf '\\n'\n"

# The pgrep token is built at RUNTIME, so no ancestor's argv (this pytest, the session that launched it) can already contain it: A0's first attempt at these rows was polluted exactly that way.
TOK = "zq" + uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class Fact:
    """One bash fact.

    `script` runs as `bash -c` (mode "c"), `bash -n -c` (mode "n", only the rc is judged) or as a script FILE (mode "file"). `{T}` in the script or the expectation is the row's scratch directory and `{TOK}` the pgrep token. `sees`/`misses` are command prefixes the scanner must (not) show at a command position in `scan_target(script)`; `check` names a custom scanner comparison in `CHECKS`. `relies_on` is `(file under .claude/rediacc_hooks, top-level name)`, verified by AST.
    """

    id: str
    fact: str
    script: str
    stdout: str | None = None
    rc: int | None = None
    rc_nonzero: bool = False
    mode: str = "c"
    relies_on: tuple = ()
    source: str = ""
    sees: tuple = ()
    misses: tuple = ()
    check: str = ""
    setup: str = ""
    extra: dict = field(default_factory=dict)


SS = "shellscan.py"

FACTS = [
    # -- shell wrappers and eval --------------------------------------------------------------
    Fact(
        "W1",
        "sh -c P runs P",
        "sh -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_wrapper_payload"), (SS, "_shell_payload")),
        source="corpus r39 bare; 11 guards' wrapper-payload rows",
        sees=("zzrun X",),
    ),
    Fact(
        "W2",
        "a short-flag bundle ending in c",
        "bash -ec 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_shell_payload"),),
        source="r39 bundled",
        sees=("zzrun X",),
    ),
    Fact(
        "W3",
        "separate flags before -c",
        "bash -eu -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_shell_payload"),),
        source="r40 separate",
        sees=("zzrun X",),
    ),
    Fact(
        "W4",
        "a value-taking option",
        "bash -o pipefail -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_shell_payload"),),
        source="r40 value-taking",
        sees=("zzrun X",),
    ),
    Fact(
        "W5",
        "long options",
        "bash --posix -c 'zzrun X'; bash --norc --noprofile -c 'zzrun Y'",
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_shell_payload"),),
        source="r40 long, --norc",
        sees=("zzrun X", "zzrun Y"),
    ),
    Fact(
        "W6",
        "a path-qualified or quoted shell name",
        "\"$BASH\" -c 'zzrun X'; '/bin/sh' -c 'zzrun Y'",
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_wrapper_payload"),),
        source="r42 abs/usr-bin, r44 x3",
        sees=("zzrun Y",),
    ),
    Fact(
        "W7",
        "env runs the shell",
        "env sh -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_strip_prefixes"),),
        source="r42 env bash",
        sees=("zzrun X",),
    ),
    Fact(
        "W8",
        "c anywhere in a bundle selects -c (A0 L10)",
        "bash -ce 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_shell_payload"),),
        source="A4 L10",
        sees=("zzrun X",),
    ),
    Fact(
        "W9",
        "options may follow -c (A0 L10)",
        "bash -c -e 'zzrun X'; bash -c -- 'zzrun Y'",
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_shell_payload"),),
        source="A4 L10",
        sees=("zzrun X", "zzrun Y"),
    ),
    Fact(
        "W10",
        "quote removal applies to -c (A0 L10)",
        "bash '-c' 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_shell_payload"),),
        source="A4 L10",
        sees=("zzrun X",),
    ),
    Fact(
        "W11",
        "eval runs its argument",
        "eval 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_wrapper_payload"),),
        source="eval payload; force_push, push_to_protected, ssh_docker eval rows",
        sees=("zzrun X",),
    ),
    Fact(
        "W12",
        "eval re-parses after expansion",
        'Y=--f; eval "zzrun X $Y"',
        "RAN:X|--f\n",
        relies_on=((SS, "_wrapper_payload"),),
        source="eval with assignment",
        sees=("zzrun X",),
    ),
    Fact(
        "W13",
        "a shell with no -c, then a wrapper",
        "sh /dev/null; sh -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_wrapper_payload"),),
        source="shell with no -c",
        sees=("zzrun X",),
    ),
    Fact(
        "W14",
        "an eval word as an argument does not stop a later wrapper (A0 L11)",
        "echo eval && sh -c 'zzrun X'",
        "eval\nRAN:X\n",
        relies_on=((SS, "lifted_commands"),),
        source="A4 L11",
        sees=("zzrun X",),
    ),
    Fact(
        "W15",
        "two wrappers on one line (A0 L11)",
        "sh -c true; sh -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "lifted_commands"),),
        source="A4 L11",
        sees=("zzrun X",),
    ),
    Fact(
        "W16",
        "a leading blank changes nothing",
        " sh -c 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_wrapper_payload"),),
        source="leading space before wrapper",
        sees=("zzrun X",),
    ),
    # -- env prefixes ---------------------------------------------------------------------------
    Fact(
        "E1",
        "a prefix is not the command",
        "FOO=bar zzrun X; true; FOO=b zzrun Y; true | FOO=c zzrun Z; (FOO=d zzrun W)",
        "RAN:X\nRAN:Y\nRAN:Z\nRAN:W\n",
        relies_on=((SS, "_ENV_PREFIX"), (SS, "_strip_env_prefix")),
        source="env prefix before git / after ; / after pipe / after paren",
        sees=("zzrun X", "zzrun Y", "zzrun Z", "zzrun W"),
    ),
    Fact(
        "E2",
        "several prefixes",
        "A=1 B=2 zzrun X",
        "RAN:X\n",
        relies_on=((SS, "_strip_env_prefix"),),
        source="two env prefixes",
        sees=("zzrun X",),
    ),
    Fact(
        "E3",
        "a prefix inside a substitution",
        'x=$(FOO=b zzrun X); y=`FOO=b zzrun Y`; printf \'%s\\n\' "$x" "$y"',
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_ENV_PREFIX"),),
        source="inside substitution / backticks",
        sees=("zzrun X", "zzrun Y"),
    ),
    Fact(
        "E4",
        "the value may contain =",
        'FOO=a=b sh -c \'printf "%s\\n" "$FOO"\'',
        "a=b\n",
        relies_on=((SS, "_ENV_PREFIX"),),
        source="value has an equals",
        sees=("sh -c",),
    ),
    Fact(
        "E5",
        "a bare assignment runs nothing",
        "FOO=bar",
        "",
        rc=0,
        relies_on=((SS, "_strip_prefixes"),),
        source="assignment with no command",
        check="no_runs",
    ),
    Fact(
        "E6",
        "a prefix reaches the child's environment",
        'FOO=bar sh -c \'printf "%s\\n" "$FOO"\'',
        "bar\n",
        relies_on=(
            (SS, "_strip_env_prefix"),
            ("guards/block_unlinked_commit_author.py", "ENV_FLAG"),
        ),
        source="env-prefix comment",
        sees=("sh -c",),
    ),
    Fact(
        "E7",
        "x=$(cmd) runs cmd (A0 L1)",
        'x=$(zzrun X); y=`zzrun Y`; printf \'%s\\n\' "$x" "$y"',
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_ENV_PREFIX"), (SS, "lifted_commands")),
        source="A4 L1",
        sees=("zzrun X", "zzrun Y"),
    ),
    # -- heredocs -------------------------------------------------------------------------------
    Fact(
        "H1",
        "a heredoc body with no substitution is data",
        "cat <<'EOF'\nzzrun X\nEOF\ncat <<EOF\nzzrun X\nEOF\ncat <<\"EOF\"\nzzrun X\nEOF",
        "zzrun X\nzzrun X\nzzrun X\n",
        relies_on=((SS, "_strip_heredocs"), ("guards/block_git_amend.py", "_strip_cat_heredocs")),
        source="heredoc x3; adhoc_sanctioned, git_amend, nonstandard_branch, ssh_docker, self_matching_pgrep heredoc rows",
        misses=("zzrun",),
    ),
    Fact(
        "H2",
        "an unquoted-delimiter body expands (A0 L3)",
        "cat <<EOF\n$(zzrun X)\nEOF",
        "RAN:X\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 L3",
        sees=("zzrun X",),
    ),
    Fact(
        "H3",
        "<<- closes on a tab-indented terminator",
        "cat <<-EOF\n\tb\n\tEOF\nzzrun X",
        "b\nRAN:X\n",
        relies_on=((SS, "_Lexer"), ("guards/block_git_amend.py", "_strip_cat_heredocs")),
        source="<<- tab row; git_amend tab row",
        sees=("zzrun X",),
    ),
    Fact(
        "H4",
        "plain << does not tab-strip (A0 S1)",
        "cat <<EOF\n\tEOF\nzzrun X\nEOF",
        "\tEOF\nzzrun X\n",
        relies_on=((SS, "_Lexer"),),
        source="plain << is not tab-stripped",
        misses=("zzrun",),
    ),
    Fact(
        "H5",
        "spaces or a trailing blank do not close (A0 S1)",
        "cat <<EOF\n  EOF\nEOF \nzzrun X\nEOF",
        "  EOF\nEOF \nzzrun X\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 S1",
        misses=("zzrun",),
    ),
    Fact(
        "H6",
        "an unterminated heredoc swallows the rest",
        "cat <<EOF\nzzrun X",
        "zzrun X\n",
        relies_on=((SS, "_strip_heredocs"),),
        source="never terminated",
        misses=("zzrun",),
    ),
    Fact(
        "H7",
        "two heredocs in sequence",
        "cat <<A\nx\nA\ncat <<B\ny\nB\nzzrun X",
        "x\ny\nRAN:X\n",
        relies_on=((SS, "_strip_heredocs"),),
        source="two heredocs",
        sees=("zzrun X",),
    ),
    Fact(
        "H8",
        "a marker with digits",
        "cat <<EOF2\nq\nEOF2\nzzrun X",
        "q\nRAN:X\n",
        relies_on=((SS, "_strip_heredocs"),),
        source="marker with digits",
        sees=("zzrun X",),
    ),
    Fact(
        "H9",
        "a marker with - is the whole word (A0 S2)",
        "cat <<END-X\nEND\nzzrun X\nEND-X",
        "END\nzzrun X\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 S2",
        misses=("zzrun",),
    ),
    Fact(
        "H10",
        "an interpreter heredoc runs (A0 L4)",
        "bash <<'EOF'\nzzrun X\nEOF",
        "RAN:X\n",
        relies_on=((SS, "_Walker"), ("guards/block_git_amend.py", "_strip_cat_heredocs")),
        source="interpreter heredoc; git_amend; bash_write python heredoc",
        sees=("zzrun X",),
    ),
    Fact(
        "H11",
        "a here-string into a shell runs (A0 L4)",
        "bash <<< 'zzrun X'",
        "RAN:X\n",
        relies_on=((SS, "_Walker"),),
        source="A4 L4",
        sees=("zzrun X",),
    ),
    Fact(
        "H12",
        "a here-string has no body (A0 L5)",
        "cat <<<x\nzzrun X",
        "x\nRAN:X\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 L5",
        sees=("zzrun X",),
    ),
    Fact(
        "H13",
        "<< inside quotes or a comment is not a heredoc (A0 L5)",
        'echo "<<EOF"\nzzrun X\ntrue # <<EOF\nzzrun Y',
        "<<EOF\nRAN:X\nRAN:Y\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 L5",
        sees=("zzrun X", "zzrun Y"),
    ),
    # -- quoting and words ----------------------------------------------------------------------
    Fact(
        "Q1",
        "a quoted span is one literal word",
        "echo 'zzrun X'; echo \"never zzrun Y\"",
        "zzrun X\nnever zzrun Y\n",
        relies_on=((SS, "_sed_strip_quoted_spans"),),
        source="single-quoted prose; prose in commit msg; ~10 guard quoted-prose rows",
        misses=("zzrun",),
    ),
    Fact(
        "Q2",
        '\' inside "..." is literal (A0 L6)',
        "echo \"it's\"; zzrun X; echo 'y'",
        "it's\nRAN:X\ny\n",
        relies_on=((SS, "_sed_strip_quoted_spans"), (SS, "lifted_commands")),
        source="A4 L6",
        sees=("zzrun X",),
    ),
    Fact(
        "Q3",
        '\\" inside "..." does not close it (A0 L6)',
        'echo "p \\" q"; zzrun X; echo "r"',
        'p " q\nRAN:X\nr\n',
        relies_on=((SS, "_sed_strip_quoted_spans"), (SS, "lifted_commands")),
        source="A4 L6",
        sees=("zzrun X",),
    ),
    Fact(
        "Q4",
        "a substitution inside double quotes runs (A0 L2)",
        'echo "$(zzrun X)"; echo "`zzrun Y`"',
        "RAN:X\nRAN:Y\n",
        relies_on=((SS, "_Lexer"),),
        source="adhoc_sanctioned banned half INSIDE quotes",
        sees=("zzrun X", "zzrun Y"),
    ),
    Fact(
        "Q5",
        "quote removal on the command word (A0 L7)",
        '"zzrun" X; zz"run" X; zz\\run X; \\zzrun X; $\'zzrun\' X',
        "RAN:X\n" * 5,
        relies_on=((SS, "_word_value"),),
        source="A4 L7; block_git_force_push.py FORCE_PUSH",
        sees=("zzrun X",),
    ),
    Fact(
        "Q6",
        "a backslash-newline joins (A0 L8)",
        "zzrun X \\\nY",
        "RAN:X|Y\n",
        relies_on=((SS, "_Lexer"),),
        source="A4 L8",
        sees=("zzrun X Y",),
    ),
    Fact(
        "Q7a",
        "an unbalanced single quote rejects the whole command",
        "echo 'zzrun X",
        rc_nonzero=True,
        mode="n",
        relies_on=((SS, "_sed_strip_quoted_spans"),),
        source="unbalanced single",
        misses=("zzrun",),
    ),
    Fact(
        "Q7b",
        "an unbalanced double quote rejects the whole command",
        'echo "zzrun X',
        rc_nonzero=True,
        mode="n",
        relies_on=((SS, "_sed_strip_quoted_spans"),),
        source="unbalanced double",
        misses=("zzrun",),
    ),
    Fact(
        "Q8",
        "nested quotes in a wrapper",
        "sh -c \"zzrun X 'y'\"",
        "RAN:X|y\n",
        relies_on=((SS, "_sed_quotes_to_spaces"),),
        source="nested quotes",
        sees=("zzrun X",),
    ),
    Fact(
        "Q9",
        "an unquoted variable delivers the flag",
        'X="--f"; zzrun a $X',
        "RAN:a|--f\n",
        relies_on=((SS, "flag_present"),),
        source="flag in an assignment",
        sees=("zzrun a",),
    ),
    Fact(
        "Q10",
        "a tab is a word separator",
        "zzrun\tX; zzargv -C\tp",
        "RAN:X\n<-C><p>\n",
        relies_on=((SS, "target_root"),),
        source="tab separated; -C with a tab (the A4 tab defect)",
        sees=("zzrun X",),
    ),
    Fact(
        "Q11",
        "CR, VT and FF are word characters (A0 S3, kept)",
        "zzargv X$'\\r'",
        "<X\r>\n",
        relies_on=((SS, "SPACE"),),
        source="carriage return",
        check="s3_pinned",
    ),
    # -- separators and command position ------------------------------------------------------------
    Fact(
        "SEP1",
        "each separator starts a command",
        'zzrun 1; zzrun 2 && zzrun 3 || zzrun 4; zzrun 5 | cat; (zzrun 6); x=$(zzrun 7); echo "$x"\nzzrun 8',
        "RAN:1\nRAN:2\nRAN:3\nRAN:5\nRAN:6\nRAN:7\nRAN:8\n",
        relies_on=((SS, "gh_pr_at_command_pos"), (SS, "gh_pr_segment")),
        source="after-a-separator rows (git_amend, git_empty_commit, worktree_add, protected_files, binary_deploy)",
        sees=("zzrun 1", "zzrun 2", "zzrun 3", "zzrun 5", "zzrun 6", "zzrun 7", "zzrun 8"),
    ),
    Fact(
        "SEP2",
        "reserved words and prefix builtins start a command (A0 L9)",
        "{ zzrun 1; }; ! zzrun 2; if :; then zzrun 3; fi; for i in 4; do zzrun $i; done; command zzrun 5; time zzrun 6; exec zzrun 7",
        "RAN:1\nRAN:2\nRAN:3\nRAN:4\nRAN:5\nRAN:6\nRAN:7\n",
        relies_on=((SS, "_strip_prefixes"), (SS, "lifted_commands")),
        source="A4 L9",
        sees=("zzrun 1", "zzrun 2", "zzrun 3", "zzrun $i", "zzrun 5", "zzrun 6", "zzrun 7"),
    ),
    Fact(
        "SEP3",
        "a redirect may precede the command (A0 L9)",
        "2>/dev/null zzrun X",
        "RAN:X\n",
        relies_on=((SS, "_Lexer"), (SS, "lifted_commands")),
        source="A4 L9",
        sees=("zzrun X",),
    ),
    Fact(
        "SEP4",
        "separators inside quotes are data",
        "echo \"a;zzrun X\"; echo 'b|zzrun Y'",
        "a;zzrun X\nb|zzrun Y\n",
        relies_on=((SS, "_sed_strip_quoted_spans"), (SS, "gh_pr_segment")),
        source="r46 scope",
        misses=("zzrun",),
    ),
    Fact(
        "SEP5",
        "arguments do not cross a separator",
        "zzargv view 94 --repo a; zzargv merge 66 --repo b",
        "<view><94><--repo><a>\n<merge><66><--repo><b>\n",
        relies_on=((SS, "gh_pr_segment"), (SS, "pr_selector")),
        source="r46 two gh / two merges",
        check="argvs",
        extra={"argvs": [["view", "94", "--repo", "a"], ["merge", "66", "--repo", "b"]]},
    ),
    Fact(
        "SEP6",
        "a separator ends ssh's argv",
        "zzargv h true; zzargv docker ps",
        "<h><true>\n<docker><ps>\n",
        relies_on=(("guards/block_ssh_docker.py", "SSH_DOCKER"),),
        source="ssh_docker separator ends the clause",
        check="argvs",
        extra={"argvs": [["h", "true"], ["docker", "ps"]]},
    ),
    # -- redirects -------------------------------------------------------------------------------
    Fact(
        "R1",
        "a redirect is not an argument",
        "zzargv add -A 2>/dev/null; zzargv add -A 3>&1",
        "<add><-A>\n<add><-A>\n",
        relies_on=(("guards/block_blanket_git_add.py", "END"),),
        source="blanket_git_add x3",
        check="argvs",
        extra={"argvs": [["add", "-A"], ["add", "-A"]]},
    ),
    Fact(
        "R2",
        "> and >> open for write",
        'echo x > "{T}/a.sh"; echo y >> "{T}/a.sh"; cat "{T}/a.sh"',
        "x\ny\n",
        relies_on=(
            (SS, "write_targets"),
            ("guards/block_bash_write_to_running_script.py", "TARGET_SPAN"),
        ),
        source="redirect onto running script; roundlog_truncate x2",
        check="writes",
        extra={"writes": ["{T}/a.sh", "{T}/a.sh"]},
    ),
    Fact(
        "R3",
        ">| truncates under noclobber (A0 L14)",
        'set -C; echo o > "{T}/f"; echo n >| "{T}/f"; cat "{T}/f"',
        "n\n",
        relies_on=(
            (SS, "write_targets"),
            ("guards/block_bash_write_to_running_script.py", "NOT_ARROW"),
        ),
        source="A4 L14",
        check="writes",
        extra={"writes": ["{T}/f", "{T}/f"]},
    ),
    Fact(
        "R4",
        "an unquoted -> is a redirect (A0 L14)",
        'echo x->"{T}/f.sh"; cat "{T}/f.sh"',
        "x-\n",
        relies_on=(
            (SS, "write_targets"),
            ("guards/block_bash_write_to_running_script.py", "NOT_ARROW"),
        ),
        source="A4 L14; the ASCII arrow row",
        check="writes",
        extra={"writes": ["{T}/f.sh"]},
    ),
    Fact(
        "R5",
        "redirect locality across ssh (A0 L13)",
        'zzrun h cat f > "{T}/o"; cat "{T}/o"; zzargv h \'cat > /etc/x\'',
        "RAN:h|cat|f\n<h><cat > /etc/x>\n",
        relies_on=(
            ("guards/block_ssh_file_write.py", "remote_write"),
            ("guards/block_ssh_file_write.py", "SSH_WRITE"),
        ),
        source="A4 L13; ssh_file_write x3",
        check="ssh_locality",
    ),
    # -- cd scope -------------------------------------------------------------------------------
    Fact(
        "C1",
        "cd persists across && and ;",
        "cd /tmp && pwd; pwd",
        "/tmp\n/tmp\n",
        relies_on=((SS, "target_root"), (SS, "target_repo")),
        source="cd into submodule; cd relative &&",
        check="cwds",
        extra={"cwds": ["/tmp", "/tmp"]},
    ),
    Fact(
        "C2",
        "the last cd wins",
        "cd /tmp; cd /; pwd",
        "/\n",
        relies_on=((SS, "target_root"),),
        source="two cds",
        check="cwds",
        extra={"cwds": ["/"]},
    ),
    Fact(
        "C3",
        "a failed cd skips the && branch",
        "cd /nonexistent-q 2>/dev/null && zzrun X; echo after",
        "after\n",
        relies_on=((SS, "_resolve_root"),),
        source="cd absolute nonexistent",
        check="unresolvable_cd",
    ),
    Fact(
        "C4",
        "a quoted path is unquoted",
        'cd "/tmp" && pwd',
        "/tmp\n",
        relies_on=((SS, "_word_value"),),
        source="cd quoted path",
        check="cwds",
        extra={"cwds": ["/tmp"]},
    ),
    Fact(
        "C5",
        "a subshell or pipeline cd does not persist (A0 L12)",
        "cd /; (cd /tmp); pwd; cd /tmp | true; pwd",
        "/\n/\n",
        relies_on=((SS, "_Walker"), (SS, "target_root")),
        source="A4 L12",
        check="cwds",
        extra={"cwds": ["/", "/"]},
    ),
    # -- processes, PATH and script reading ------------------------------------------------------------
    Fact(
        "P1",
        "$$ in $(...) is the parent shell",
        '[ "$$" = "$(echo $$)" ] && [ "$BASHPID" != "$(echo $BASHPID)" ] && echo same',
        "same\n",
        relies_on=(("guards/block_unsatisfiable_pid_wait.py", "_is_provably_always_alive"),),
        source="$$ fallback",
    ),
    Fact(
        "P2",
        "|| substitutes the fallback; && does not",
        'echo "[$(cat /nx 2>/dev/null || echo 1)]"; echo "[$(cat /nx 2>/dev/null && echo 1)]"',
        "[1]\n[]\n",
        relies_on=(("guards/block_unsatisfiable_pid_wait.py", "_split_top_level_or"),),
        source="minimal fire, &&-join, ;-join",
    ),
    Fact(
        "P3",
        "an unbalanced $( is a syntax error",
        "until ! [ -e /proc/$(cat x.pid || echo 1 ; do sleep 5; done",
        rc_nonzero=True,
        mode="n",
        relies_on=(("guards/block_unsatisfiable_pid_wait.py", "_extract_subst"),),
        source="unparseable substitution",
    ),
    Fact(
        "P4",
        "the waiting shell's argv holds the pattern",
        "pgrep -f {TOK} >/dev/null; echo $?",
        "0\n",
        relies_on=(("guards/block_self_matching_pgrep.py", "LOOP_WITH_PGREP"),),
        source="the self-matching loop; negation",
    ),
    Fact(
        "P5",
        "the bracket remedy does not match itself",
        "pgrep -f '[{TOK0}]{TOKREST}' >/dev/null; echo $?",
        "1\n",
        relies_on=(("guards/block_self_matching_pgrep.py", "_matches"),),
        source="the remedy",
    ),
    Fact(
        "P6",
        "a quoted pattern reaches pgrep unquoted",
        "pgrep -f '{TOK}' >/dev/null; echo $?",
        "0\n",
        relies_on=(("guards/block_self_matching_pgrep.py", "PATTERN_ARG"),),
        source="quoted / double-quoted pattern",
    ),
    Fact(
        "P7",
        "bash reads a script lazily, by byte offset",
        'printf \'printf "APPENDED\\\\n"\\n\' >> "$0"\n',
        "APPENDED\n",
        mode="file",
        relies_on=(
            ("proc.py", "pgrep_full"),
            ("runningscript.py", "live_shells"),
        ),
        source="both running-script guards' headers",
    ),
    Fact(
        "P8",
        "command -v prefers an executable later in PATH (A0 L15)",
        "PATH={T}/d1:{T}/d2 command -v zt; PATH={T}/d3:{T}/d2 command -v zd; echo rc=$?",
        "{T}/d2/zt\nrc=1\n",
        relies_on=(
            ("hookio.py", "command_v"),
            ("guards/block_host_toolchain_run.py", "_command_v"),
        ),
        source="A4 L15; toolchain :27 measurement",
        check="command_v",
        setup="path_dirs",
    ),
    # -- degenerate inputs --------------------------------------------------------------------------
    Fact(
        "X1a",
        "an empty command runs nothing",
        "",
        "",
        rc=0,
        relies_on=((SS, "hook_init"),),
        source="empty",
        check="no_runs",
    ),
    Fact(
        "X1b",
        "a blank command runs nothing",
        "  \t ",
        "",
        rc=0,
        relies_on=((SS, "_records"),),
        source="space, whitespace",
        check="no_runs",
    ),
    Fact(
        "X1c",
        "a newline-only command runs nothing",
        "\n",
        "",
        rc=0,
        relies_on=((SS, "_records"),),
        source="newline only",
        check="no_runs",
    ),
    Fact(
        "X2a",
        "trailing newlines are inert",
        "zzrun X\n\n",
        "RAN:X\n",
        relies_on=((SS, "_records"),),
        source="trailing newline(s)",
        sees=("zzrun X",),
    ),
    Fact(
        "X2b",
        "a blank line between commands is inert",
        "echo a\n\nzzrun X",
        "a\nRAN:X\n",
        relies_on=((SS, "_records"),),
        source="blank line",
        sees=("zzrun X",),
    ),
    # #ec63ff8c, 2026-10-09: the launchers shellscan walks and the stdin xargs turns into operands.
    Fact(
        "W17",
        "find runs every -exec command, each up to its own escaped semicolon",
        'find "{T}" -maxdepth 0 -exec zzrun X {} \\; -exec zzrun Y \\;',
        "RAN:X|{T}\nRAN:Y\n",
        relies_on=((SS, "_launched"), (SS, "lifted_commands")),
        source="find -exec",
        sees=("zzrun X", "zzrun Y"),
    ),
    Fact(
        "W18",
        "xargs turns the text on its stdin into the operands of the command it runs",
        "echo a b | xargs zzargv",
        "<a><b>\n",
        relies_on=((SS, "_stage_feed"),),
        source="xargs feed",
        check="xargs_feed",
        extra={"feed": "echo a b"},
    ),
    # #32e75fa4 (review 4aad4597.1): what block_protected_files' payload inheritance rests on.
    Fact(
        "W19",
        "xargs hands the fed words to a sh -c payload as $0, $1, ...",
        """echo a b | xargs sh -c 'zzargv "$0" "$@"'""",
        "<a><b>\n",
        relies_on=((SS, "_shell_payload"), (SS, "_stage_feed")),
        source="xargs sh -c feed",
    ),
    Fact(
        "W20",
        "a sh -c payload reads the shell's own stdin, so an xargs inside it gets the piped words",
        "echo a b | sh -c 'xargs zzargv'",
        "<a><b>\n",
        relies_on=((SS, "_shell_payload"), (SS, "_stage_feed")),
        source="sh -c stdin feed",
    ),
]


# --------------------------------------------------------------------------- the real bash ---------------------------------------------------------------------------


def _real_bash():
    found = shutil.which("bash")
    if found is None:
        pytest.fail("no bash on PATH: this suite exists to ask bash, so it fails rather than skips")
    assert found is not None
    proc = subprocess.run(
        [found, "--norc", "--noprofile", "-c", 'printf %s "$BASH"'],
        capture_output=True,
        check=False,
        env={k: v for k, v in os.environ.items() if k not in ("BASH_ENV", "ENV")},
    )
    path = proc.stdout.decode("utf-8", "surrogateescape")
    if proc.returncode != 0 or not os.path.isabs(path) or not os.access(path, os.X_OK):
        pytest.fail("could not resolve the real bash behind %s (got %r)" % (found, path))
    return path


@pytest.fixture(scope="module")
def bash():
    return _real_bash()


def _subst(text, tmp):
    return (
        text.replace("{T}", str(tmp))
        .replace("{TOK0}", TOK[0])
        .replace("{TOKREST}", TOK[1:])
        .replace("{TOK}", TOK)
    )


def _world(tmp, fact):
    """The row's scratch directory: the two stubs, and whatever its `setup` names."""
    stubs = tmp / "bin"
    stubs.mkdir(parents=True, exist_ok=True)
    for name, body in (("zzrun", ZZRUN), ("zzargv", ZZARGV)):
        (stubs / name).write_text(body, encoding="utf-8")
        (stubs / name).chmod(0o755)
    if fact.setup == "path_dirs":
        for d in ("d1", "d2", "d3/zd"):
            (tmp / d).mkdir(parents=True, exist_ok=True)
        (tmp / "d1" / "zt").write_text("", encoding="utf-8")
        (tmp / "d1" / "zt").chmod(0o600)
        (tmp / "d2" / "zt").write_text("#!/bin/sh\n", encoding="utf-8")
        (tmp / "d2" / "zt").chmod(0o755)
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": "%s:/usr/bin:/bin" % stubs, "LC_ALL": "C", "HOME": str(home), "T": str(tmp)}


def run_bash(bash_path, fact, tmp):
    env = _world(tmp, fact)
    script = _subst(fact.script, tmp)
    if fact.mode == "file":
        path = tmp / "s.sh"
        path.write_text(script, encoding="utf-8")
        argv = [bash_path, "--norc", "--noprofile", str(path)]
    elif fact.mode == "n":
        argv = [bash_path, "--norc", "--noprofile", "-n", "-c", script]
    else:
        argv = [bash_path, "--norc", "--noprofile", "-c", script]
    proc = subprocess.run(argv, capture_output=True, check=False, env=env, cwd=str(tmp), timeout=30)
    return proc.returncode, proc.stdout.decode("utf-8", "surrogateescape")


def fact_mismatch(fact, rc, out, tmp):
    """Why bash's answer does not match the row, or "" when it does. Separate from the test so `test_the_suite_can_fail` can feed it a wrong row."""
    problems = []
    if fact.stdout is not None and out != _subst(fact.stdout, tmp):
        problems.append("stdout %r, row says %r" % (out, _subst(fact.stdout, tmp)))
    if fact.rc is not None and rc != fact.rc:
        problems.append("rc %d, row says %d" % (rc, fact.rc))
    if fact.rc_nonzero and rc == 0:
        problems.append("rc 0, row says non-zero")
    return "; ".join(problems)


@pytest.mark.parametrize("fact", FACTS, ids=[f.id for f in FACTS])
def test_bash_fact(bash, tmp_path, fact):
    rc, out = run_bash(bash, fact, tmp_path)
    why = fact_mismatch(fact, rc, out, tmp_path)
    version = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", 'printf %s "$BASH_VERSION"'],
        capture_output=True,
        check=False,
    ).stdout.decode()
    assert why == "", "bash %s no longer holds %s: %s; re-examine %s (from %s)" % (
        version,
        fact.fact,
        why,
        fact.relies_on,
        fact.source,
    )


# --------------------------------------------------------------------------- the reliance is real ---------------------------------------------------------------------------


def _top_level_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


@pytest.mark.parametrize("fact", FACTS, ids=[f.id for f in FACTS])
def test_reliance_resolves(fact):
    """Each row names the Python that leans on its fact. The line numbers A0 cited are documentation; the NAME is what is checked, so a rename that orphans a row fails here."""
    assert fact.relies_on, "row %s names no Python that relies on it" % fact.id
    missing = [(f, n) for f, n in fact.relies_on if n not in _top_level_names(HOOKS / f)]
    assert not missing, "row %s relies on names that no longer exist: %s" % (fact.id, missing)


# --------------------------------------------------------------------------- the scanner agrees ---------------------------------------------------------------------------


def _at_command_position(scan, prefix):
    words = prefix.split(" ")
    body = ("[" + shellscan.SPACE + "]+").join(re.escape(w) for w in words)
    pattern = (
        r"(^|[;&|(])[" + shellscan.SPACE + r"]*" + body + r"([" + shellscan.SPACE + r";&|)]|$)"
    )
    return re.search(pattern, scan, re.MULTILINE) is not None


def _check_ssh_locality(tmp):
    module = guards.load("block_ssh_file_write")
    remote = module.remote_write("ssh h 'cat > /etc/x' < f")
    local = module.remote_write('ssh h cat f > "%s/o"' % tmp)
    return "" if remote and not local else "remote=%s local=%s" % (remote, local)


def _check_command_v(tmp, monkeypatch):
    got = []
    for path, name in (("%s/d1:%s/d2" % (tmp, tmp), "zt"), ("%s/d3:%s/d2" % (tmp, tmp), "zd")):
        monkeypatch.setenv("PATH", path)
        got.append(hookio.command_v(name))
    want = ["%s/d2/zt" % tmp, ""]
    return "" if got == want else "command_v %r, bash %r" % (got, want)


def scanner_mismatch(fact, tmp, monkeypatch):
    script = _subst(fact.script, tmp)
    scan = shellscan._command_substitution(shellscan.scan_target(script))
    problems = [
        "%r not at a command position" % p for p in fact.sees if not _at_command_position(scan, p)
    ]
    problems += [
        "%r at a command position" % p for p in fact.misses if _at_command_position(scan, p)
    ]
    runs = shellscan._analyse(script).runs
    if fact.check == "no_runs" and runs:
        problems.append("runs %r" % [r.canonical for r in runs])
    elif fact.check == "argvs":
        got = [r.argv for r in runs]
        if got != fact.extra["argvs"]:
            problems.append("argvs %r" % got)
    elif fact.check == "writes":
        want = [_subst(w, tmp) for w in fact.extra["writes"]]
        got = [_subst(w, tmp).replace("$T", str(tmp)) for w in shellscan.write_targets(script)]
        if got != want:
            problems.append("write_targets %r, bash %r" % (got, want))
    elif fact.check == "cwds":
        got = [r.cwd for r in runs if r.name == "pwd"]
        if got != fact.extra["cwds"]:
            problems.append("pwd runs in %r" % got)
    elif fact.check == "unresolvable_cd":
        if shellscan.target_root("cd /nonexistent-q && git push", str(tmp)) != "":
            problems.append("a cd bash cannot perform resolved to a root")
    elif fact.check == "xargs_feed":
        fed = [(r.name, r.feed, r.via) for r in runs if r.feed is not None]
        if fed != [("zzargv", fact.extra["feed"], ("xargs",))]:
            problems.append("fed runs %r" % fed)
    elif fact.check == "ssh_locality":
        problems.append(_check_ssh_locality(tmp))
    elif fact.check == "command_v":
        problems.append(_check_command_v(tmp, monkeypatch))
    # THE KEPT DIVERGENCE, PINNED. Bash reads `X\r` as one word; `shellscan.SPACE` counts `\r` as a blank, so an anchor may split there. That only ever over-matches, and `SPACE` is the class forty guard regexes are written in, so it stays (PLAN-retire-bash-oracles A4). If this assertion flips, S3 was fixed: turn this row into an agreement.
    elif fact.check == "s3_pinned" and re.fullmatch("[" + shellscan.SPACE + "]", "\r") is None:
        problems.append(
            "S3 is no longer divergent: SPACE stopped counting CR; make Q11 an agreement row"
        )
    return "; ".join(p for p in problems if p)


SCANNER_FACTS = [f for f in FACTS if f.sees or f.misses or f.check]


@pytest.mark.parametrize("fact", SCANNER_FACTS, ids=[f.id for f in SCANNER_FACTS])
def test_scanner_agrees(tmp_path, monkeypatch, fact):
    _world(tmp_path, fact)
    why = scanner_mismatch(fact, tmp_path, monkeypatch)
    assert why == "", "the scanner disagrees with bash on %s (%s): %s" % (fact.id, fact.fact, why)


# --------------------------------------------------------------------------- Rule T at the guard ---------------------------------------------------------------------------

# FAILING-FIRST, AT THE GUARD. Each row is a command A0 measured the guard ALLOWING (rc 0) before PLAN-retire-bash-oracles A4, now refused, followed by the prose, data or print-only twin that must stay allowed. The goldens record the same verdicts, but a golden is written FROM the fixed port and so cannot show that the old one failed; these assertions would have.
FORCE = "git push --force origin main"
VERDICTS = [
    ("L1", "block_git_force_push", "x=$(%s)" % FORCE, 2),
    ("L1", "block_git_force_push", "x=`%s`" % FORCE, 2),
    ("L2", "block_git_force_push", 'echo "$(%s)"' % FORCE, 2),
    ("L2 control", "block_git_force_push", 'git commit -m "never %s"' % FORCE, 0),
    ("L3", "block_git_force_push", "cat > R.md <<EOF\n$(%s)\nEOF" % FORCE, 2),
    ("L3", "block_git_amend", "cat > R.md <<EOF\n$(git commit --amend --no-edit)\nEOF", 2),
    (
        "L3 control",
        "block_git_amend",
        "cat > R.md <<'EOF'\n$(git commit --amend --no-edit)\nEOF",
        0,
    ),
    ("L4", "block_git_force_push", "bash <<'EOF'\n%s\nEOF" % FORCE, 2),
    ("L4", "block_git_force_push", "bash <<< '%s'" % FORCE, 2),
    ("L4 control", "block_git_force_push", "python3 - <<'EOF'\n%s\nEOF" % FORCE, 0),
    ("L5", "block_git_force_push", "cat <<<x\n%s" % FORCE, 2),
    ("L5", "block_git_force_push", "true # <<EOF\n%s" % FORCE, 2),
    ("L6", "block_git_force_push", "echo \"it's\"; %s; echo 'y'" % FORCE, 2),
    ("L7", "block_git_force_push", '"git" push --force origin main', 2),
    ("L7", "block_git_amend", '"git" commit --amend --no-edit', 2),
    ("L8", "block_git_force_push", "git push \\\n--force origin main", 2),
    ("L9", "block_git_force_push", "{ %s; }" % FORCE, 2),
    ("L9", "block_git_force_push", ">/dev/null %s" % FORCE, 2),
    ("L9", "block_worktree_add", "2>/dev/null git worktree add /tmp/wt main", 2),
    ("L9", "block_blanket_git_add", "if true; then git add -A; fi", 2),
    ("L9 control", "block_git_force_push", "command -v git push --force", 0),
    ("L10", "block_git_force_push", "bash -ce '%s'" % FORCE, 2),
    ("L11", "block_git_force_push", "sh -c true; sh -c '%s'" % FORCE, 2),
    ("L13", "block_ssh_file_write", "ssh prod-1 'cat > /etc/x' < f", 2),
    ("L13", "block_ssh_file_write", 'ssh prod-1 "echo hi > /etc/x"', 2),
    ("L13 control", "block_ssh_file_write", "echo \"ssh prod-1 'cat > /etc/x'\"", 0),
    ("L13 control", "block_ssh_file_write", "ssh prod-1 'journalctl 2>&1 >/dev/null'", 0),
    # #ec63ff8c, 2026-10-09: each refusal here was allowed before; each control was allowed before and after.
    ("ec63 ssh remote", "block_ssh_docker", 'ssh prod-1 "docker ps"', 2),
    ("ec63 ssh remote", "block_ssh_docker", 'sshpass -e ssh prod-1 "docker ps"', 2),
    ("ec63 ssh remote control", "block_ssh_docker", "ssh prod-1 'echo docker'", 0),
    ("ec63 xargs feed", "block_protected_files", "echo .claude/settings.json | xargs rm", 2),
    ("ec63 xargs feed control", "block_protected_files", "echo .claude/settings.json | cat", 0),
    # #32e75fa4 (review 4aad4597.1): the fed words are a `sh -c` payload's positional parameters (W19), so its rm deletes them.
    (
        "4aad xargs sh -c",
        "block_protected_files",
        """echo .claude/settings.json | xargs sh -c 'rm "$0"'""",
        2,
    ),
    (
        "4aad xargs sh -c control",
        "block_protected_files",
        """echo .claude/settings.json | xargs sh -c 'cat "$0"'""",
        0,
    ),
    # The payload's own commands read the shell's stdin (W20), so an xargs inside a piped sh -c is fed too.
    (
        "4aad sh -c stdin",
        "block_protected_files",
        "echo .claude/settings.json | sh -c 'xargs rm'",
        2,
    ),
    (
        "4aad sh -c stdin control",
        "block_protected_files",
        "echo .claude/settings.json | sh -c 'xargs cat'",
        0,
    ),
    ("ec63 launcher", "block_cli_bundle", "npx -y node packages/cli/dist/cli.js", 2),
    ("ec63 launcher", "block_git_force_push", "npx -c '%s'" % FORCE, 2),
    ("ec63 launcher", "block_git_force_push", "find . -maxdepth 0 -exec %s \\;" % FORCE, 2),
    (
        "ec63 launcher control",
        "block_git_force_push",
        "find . -name '*.md' -exec grep -l '%s' {} +" % FORCE,
        0,
    ),
    ("prose control", "block_git_force_push", "echo '%s'" % FORCE, 0),
    ("heredoc control", "block_git_force_push", "cat > R.md <<'EOF'\n%s\nEOF" % FORCE, 0),
]


@pytest.mark.parametrize(
    ("item", "stem", "cmd", "want"),
    VERDICTS,
    ids=["%s|%s|%d" % (v[0], v[1], i) for i, v in enumerate(VERDICTS)],
)
def test_rule_t_verdict(item, stem, cmd, want):
    rc, _out, err = dispatch.run_one(
        stem, json.dumps({"tool_input": {"command": cmd}}), cwd=str(HOOKS.parents[1])
    )
    assert rc == want, "%s: %s answered %d on %r, want %d (%s)" % (
        item,
        stem,
        rc,
        cmd,
        want,
        err[:200],
    )


# A COMMENT THAT SORTS ROWS IS A CLAIM ABOUT VERDICTS (#32e75fa4, review 4aad4597.3). block_ssh_docker's EDGE_CASES once headed a run of rows "what the payload reading must not refuse" while three of them were refused, so a reader trusting the heading would take a deny for a regression. Each heading below names the verdict of every row up to the next comment line.
_SSH_DOCKER_GROUPS = (
    ("# ... and the argv shapes ssh_remote_commands has to parse", 2),
    ("# What the payload reading must NOT refuse", 0),
)


def test_ssh_docker_edge_case_headings_match_verdicts():
    path = HOOKS / "guards" / "block_ssh_docker.py"
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    rows = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "EDGE_CASES" for t in node.targets)
    )
    assert isinstance(rows, ast.List)
    checked = 0
    for heading, want in _SSH_DOCKER_GROUPS:
        start = next(
            (i + 1 for i, line in enumerate(lines) if line.strip().startswith(heading)), None
        )
        assert start is not None, "block_ssh_docker.py lost the heading %r" % heading
        end = next(
            (i + 1 for i, line in enumerate(lines) if i >= start and line.strip().startswith("#")),
            len(lines) + 1,
        )
        group = [row for row in rows.elts if start < row.lineno < end]
        assert group, "no EDGE_CASES row under %r" % heading
        for row in group:
            assert isinstance(row, ast.Tuple)
            name, cmd = (ast.literal_eval(e) for e in row.elts)
            rc, _out, _err = dispatch.run_one(
                "block_ssh_docker",
                json.dumps({"tool_input": {"command": cmd}}),
                cwd=str(HOOKS.parents[1]),
            )
            assert rc == want, "%r sits under %r, which says rc %d; the guard answers %d" % (
                name,
                heading,
                want,
                rc,
            )
            checked += 1
    assert checked >= 10, "only %d rows sat under the headings" % checked


# --------------------------------------------------------------------------- npm's own argument parse ---------------------------------------------------------------------------

# WHERE AN npm LAUNCH STARTS IS npm's ANSWER, NOT A LIST'S (#32e75fa4, review 4aad4597.2; #31ed6c5f). `shellscan._launches` finds the program `npx`, `npm exec`, `npm exe` and `npm x` run by porting npm's two argument passes (`_npx_argv`, `_nopt`) over npm's option table. Two lists came before it: seven value options that missed `--loglevel`, then the full table, which still read `silent` as the program in
# `npx --logl silent node packages/cli/dist/cli.js` because nopt accepts any unique prefix of an option name (442 `--` prefixes take a value). Both were allowed by block_cli_bundle (rc 0, 2026-10-09), and so was `npm exec -- node packages/cli/dist/cli.js`, which was no launcher at all.
# The oracle is the pinned npm itself, with `lib/cli.js` stubbed so nothing runs. For `npx`, `bin/npx-cli.js` rewrites its argv to `npm exec <options> -- <program> ...` and calls the stub; for `npm`, the argv goes to the stub as it stands. Either way `nopt` then parses it with npm's own option types, as `@npmcli/config` does, and `lib/utils/cmd-list.js` resolves the command word: what runs is the operands after
# `exec`, or the `--call` string. Every spelling npm accepts is asked: every option name, shorthand and unique prefix, with one dash and two, with its value as the next word, after `=`, as `true`/`false`, and as a word that looks like an option, behind `npx`, `npm exec` and `npm x`, and with the option in front of `exec`.
_NPM_ORACLE_JS = r"""
const fs = require('fs')
const path = require('path')
const target = process.argv[1]
const from = { paths: [path.dirname(target)] }
const src = fs.readFileSync(target, 'utf8')
const words = (name) => {
  const m = src.match(new RegExp('const ' + name + ' = new Set\\(\\[([\\s\\S]*?)\\]\\)'))
  if (!m) { process.stderr.write('npx-cli.js no longer declares ' + name + '\n'); process.exit(3) }
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1])
}
const defs = require(require.resolve('@npmcli/config/lib/definitions', from))
const configPath = require.resolve('@npmcli/config', from)
const config = require(configPath)
const nopt = require(require.resolve('nopt', { paths: [configPath] }))
const abbrev = require(require.resolve('abbrev', { paths: [require.resolve('nopt', { paths: [configPath] })] }))
const cmdList = require(path.join(path.dirname(target), '..', 'lib', 'utils', 'cmd-list.js'))
const { types } = config.getTypesFromDefinitions(defs.definitions)
// The table shellscan carries, in its own spelling: "B" Boolean, "S" String, "V" any other single type, and for a list of types "A" then "b" (Boolean), "n" (null), "s" (String), "N" (Number) and "|literal" for each literal string.
const kind = (t) => {
  if (Array.isArray(t) && t.length === 1) t = t[0]
  if (t === Boolean) return 'B'
  if (t === String) return 'S'
  if (!Array.isArray(t)) {
    if (t === null) throw new Error('a lone null type, which shellscan does not model')
    return 'V'
  }
  const has = (x, f) => (t.includes(x) ? f : '')
  return 'A' + has(Boolean, 'b') + has(null, 'n') + has(String, 's') + has(Number, 'N') + t.filter((x) => typeof x === 'string').map((x) => '|' + x).join('')
}
const table = {}
for (const key of Object.keys(types)) table[key] = kind(types[key])
// `local-address` lists this machine's own addresses; shellscan spells them "|<address>".
table['local-address'] = table['local-address'].replace(/\|.*/, '|<address>')
const shorthands = {}
for (const key of Object.keys(defs.shorthands)) shorthands[key] = defs.shorthands[key].join(' ')
const commandWords = [...new Set([...Object.keys(abbrev(cmdList.commands.concat(Object.keys(cmdList.aliases)))), ...Object.keys(cmdList.aliases)])]
const execWords = commandWords.filter((w) => cmdList.deref(w) === 'exec')
const npx = { removedSwitches: words('removedSwitches'), removedOpts: words('removedOpts'), opts: words('opts') }
const switchExtras = words('switches')
const cliPath = require.resolve(path.join(path.dirname(target), '..', 'lib', 'cli.js'))
let got = null
require.cache[cliPath] = { id: cliPath, filename: cliPath, loaded: true, exports: (proc) => { got = proc.argv.slice(2) } }
const run = (argv) => {
  const conf = nopt(types, defs.shorthands, argv, 0)
  const remain = conf.argv.remain
  if (!remain.length || cmdList.deref(remain[0]) !== 'exec') return null
  if (typeof conf.call === 'string' && conf.call) return { call: conf.call }
  return remain.length > 1 ? { argv: remain.slice(1) } : null
}
const spellings = new Set([
  ...Object.keys(abbrev(Object.keys(types))), ...Object.keys(abbrev(Object.keys(defs.shorthands))),
  ...npx.opts, ...npx.removedOpts, ...npx.removedSwitches, ...switchExtras,
])
const answers = []
for (const key of spellings) {
  for (const dash of ['-', '--']) {
    const opt = dash + key
    const samples = [
      [opt, 'zzval', 'zzprog', 'zzarg'], [opt + '=zzval', 'zzprog', 'zzarg'],
      [opt, 'false', 'zzprog'], [opt, '-zzdash', 'zzprog'], ['--no-' + key, 'zzval', 'zzprog'],
    ]
    for (const sample of samples) {
      process.argv = [process.argv[0], target, ...sample]
      delete require.cache[require.resolve(target)]
      got = null
      require(target)
      answers.push(['npx', sample, got ? run(got) : null])
      answers.push(['npm', ['exec', ...sample], run(['exec', ...sample])])
    }
    answers.push(['npm', ['x', opt, 'zzval', 'zzprog'], run(['x', opt, 'zzval', 'zzprog'])])
    answers.push(['npm', [opt, 'zzval', 'exec', 'zzprog'], run([opt, 'zzval', 'exec', 'zzprog'])])
  }
}
process.stdout.write(JSON.stringify({ table, shorthands, execWords, npx, switchExtras, answers }) + '\n')
"""


def _npm_oracle():
    npx = shutil.which("npx")
    node = shutil.which("node")
    if npx is None or node is None:
        pytest.fail(
            "no npx/node on PATH: this test asks the pinned npm where an npm launch starts. "
            "fix: install npm at NPM_VERSION from .devcontainer/toolchain.env"
        )
    assert npx is not None
    assert node is not None
    cli = pathlib.Path(npx).resolve()
    if cli.name != "npx-cli.js":
        pytest.fail("npx on PATH resolves to %s, not npm's bin/npx-cli.js" % cli)
    # The table is npm's at the PINNED version: another npm's answer would quietly re-key it.
    env_file = HOOKS.parents[1] / ".devcontainer" / "toolchain.env"
    pin = re.search(r"^NPM_VERSION=(\S+)$", env_file.read_text(), re.MULTILINE)
    assert pin is not None, "%s no longer pins NPM_VERSION" % env_file
    meta = json.loads((cli.parents[1] / "package.json").read_text())
    if meta.get("version") != pin.group(1):
        pytest.fail(
            "npx on PATH is npm %s, the pin is %s (%s). fix: npm install -g npm@%s"
            % (meta.get("version"), pin.group(1), env_file, pin.group(1))
        )
    proc = subprocess.run(
        [node, "-e", _NPM_ORACLE_JS, str(cli)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, "the npm oracle failed (rc %d): %s" % (
        proc.returncode,
        proc.stderr[-400:],
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def npm_oracle():
    return _npm_oracle()


def test_npm_tables_match_npm(npm_oracle):
    table = dict(shellscan._NPM_TYPE)
    assert npm_oracle["table"] == table, (
        "shellscan._NPM_TYPES differs from npm's option types: %s"
        % sorted(set(table.items()) ^ set(npm_oracle["table"].items()))
    )
    assert npm_oracle["shorthands"] == shellscan._NPM_SHORTHANDS
    assert set(npm_oracle["execWords"]) == shellscan._NPM_EXEC_WORDS
    npx = npm_oracle["npx"]
    assert set(npx["removedSwitches"]) == shellscan._NPX_REMOVED_SWITCHES
    assert set(npx["removedOpts"]) == shellscan._NPX_REMOVED_OPTS
    assert set(npx["opts"]) == shellscan._NPX_OPTS
    npm_switches = {k for k, v in table.items() if v == "B" or v.startswith("Ab")}
    want = npm_switches | set(npx["removedSwitches"]) | set(npm_oracle["switchExtras"])
    assert want == shellscan._NPX_SWITCHES


def test_npm_launch_matches_npm(npm_oracle):
    answers = npm_oracle["answers"]
    # Anti-vacuity: npm's whole option table was asked, and every kind of answer occurs in it.
    assert len(answers) > 20000, "the npm oracle asked about only %d argvs" % len(answers)
    programs = {a[2]["argv"][0] for a in answers if a[2] and "argv" in a[2]}
    assert {"zzval", "zzprog"} <= programs, (
        "the oracle never ran one of the two words: %r" % programs
    )
    assert any(a[2] and "call" in a[2] for a in answers), "the oracle never ran a --call string"
    assert any(a[2] is None for a in answers), "the oracle always ran something"
    assert [
        "npx",
        ["--logl", "zzval", "zzprog", "zzarg"],
        {"argv": ["zzprog", "zzarg"]},
    ] in answers, "the oracle cannot see the abbreviation the review found"
    wrong = []
    for base, argv, want in answers:
        got = shellscan._launches(base, argv)
        if want is None:
            ok = got == []
        elif "call" in want:
            ok = len(got) == 1 and got[0][0] == "text" and got[0][1] == want["call"]
        else:
            ok = len(got) == 1 and got[0][0] == "argv" and got[0][1] == want["argv"]
        if not ok:
            wrong.append((base, argv, want, [(g[0], g[1]) for g in got]))
    assert wrong == [], "%d of %d argvs launch something other than npm runs, first: %r" % (
        len(wrong),
        len(answers),
        wrong[:5],
    )


def _git(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, env=env)


def test_rule_t_l12_cd_scope(tmp_path, monkeypatch):
    """A0 L12 against REAL repositories, where the old line-wide hint really stood the guard down.

    `block_blanket_git_add` stands down only for a command whose target resolves OUTSIDE the project. Before A4, the last `cd`/`-C` anywhere on the line was that target, so a sweep of THIS tree behind a subshell `cd`, a pipeline `cd` or another command's `-C` was allowed.
    """
    project = tmp_path / "project"
    foreign = tmp_path / "foreign"
    for repo in (project, foreign):
        repo.mkdir()
        _git(repo, "init", "-q")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    cases = [
        ("cd %s && git add -A" % foreign, 0),
        ("git -C %s add -A" % foreign, 0),
        ("(cd %s && git status); git add -A" % foreign, 2),
        ("cd %s | true; git add -A" % foreign, 2),
        ("git -C %s status; git add -A" % foreign, 2),
    ]
    got = []
    for cmd, _want in cases:
        rc, _out, _err = dispatch.run_one(
            "block_blanket_git_add", json.dumps({"tool_input": {"command": cmd}}), cwd=str(project)
        )
        got.append(rc)
    assert got == [w for _, w in cases], list(zip([c for c, _ in cases], got, strict=True))
    scan = shellscan._command_substitution(shellscan.scan_target("git -C\t%s add -A" % foreign))
    assert shellscan.target_root(scan, str(project)) == str(foreign), (
        "a TAB after -C is a blank like any other (the A4 tab defect)"
    )


def test_rule_t_l15_command_v(tmp_path, monkeypatch):
    """A0 L15: a directory is never a command, and a non-executable file wins only when nothing executable exists."""
    (tmp_path / "a" / "tool").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "tool").write_text("", encoding="utf-8")
    (tmp_path / "b" / "tool").chmod(0o644)
    monkeypatch.setenv("PATH", "%s/a:%s/b" % (tmp_path, tmp_path))
    assert hookio.command_v("tool") == "%s/b/tool" % tmp_path
    assert hookio.have("tool") is True
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "tool").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "c" / "tool").chmod(0o755)
    monkeypatch.setenv("PATH", "%s/a:%s/b:%s/c" % (tmp_path, tmp_path, tmp_path))
    assert hookio.command_v("tool") == "%s/c/tool" % tmp_path
    monkeypatch.setenv("PATH", "%s/a" % tmp_path)
    assert hookio.have("tool") is False


# --------------------------------------------------------------------------- anti-vacuity ---------------------------------------------------------------------------


def test_the_suite_can_fail(bash, tmp_path, monkeypatch):
    """Both comparisons must be able to go red: a row with a wrong expectation, and a scanner claim the scanner does not make."""
    row = FACTS[0]
    rc, out = run_bash(bash, row, tmp_path)
    assert fact_mismatch(row, rc, out, tmp_path) == ""
    wrong = Fact(row.id, row.fact, row.script, "RAN:Y\n", relies_on=row.relies_on)
    assert fact_mismatch(wrong, rc, out, tmp_path) != ""
    claim = Fact("Q1x", "prose", "echo 'zzrun X'", sees=("zzrun X",), relies_on=row.relies_on)
    assert scanner_mismatch(claim, tmp_path, monkeypatch) != ""


def test_the_rows_are_unique_and_cover_the_tables():
    ids = [f.id for f in FACTS]
    assert len(ids) == len(set(ids)), "duplicate row ids"
    tables = {re.sub(r"\d+[a-z]?$", "", i) for i in ids}
    assert tables == {"W", "E", "H", "Q", "SEP", "R", "C", "P", "X"}, tables
