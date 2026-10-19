"""The real-bash facts the hook scanner relies on, asked of bash itself (PLAN-retire-bash-oracles A0, kept by the operator's 2026-09-24 ruling).

WHY THIS SUITE EXISTS AFTER THE ORACLES ARE GONE. The differentials compared the Python port with the bash port it replaced, so they proved the two AGREED, never that either was RIGHT about bash; A0 measured fifteen fail-open shapes both got wrong together (agent/plans/PLAN-retire-bash-oracles.A0.md section 1). What is worth keeping from real-bash execution is therefore not a twin but the FACTS: how bash tokenises, quotes, expands and runs the command line a guard reasons about. Each row below is one such fact, run through a real `bash -c` (or `bash -n`, or a script file), and then asked of the scanner in-process. A bash upgrade that changes a fact fails the first test and names the Python that leans on it; a scanner change that stops agreeing with bash fails the second.

THE ENVIRONMENT IS BUILT, NEVER INHERITED. The interpreter is resolved once with `bash --norc --noprofile -c 'printf %s "$BASH"'` and called by absolute path, because `bash` on PATH may be a wrapper that re-execs the real one as a child (block_edit_of_running_script.py records the `bashcov-sup` wrapper that does exactly that on the host this was written on). Every run uses `--norc --noprofile`, `PATH=<stubs>:/usr/bin:/bin`, `LC_ALL=C` and a scratch `HOME`, with `BASH_ENV` and `ENV` removed, since either would source a profile into every non-interactive bash. The two stubs, `zzrun` (prints `RAN:` and its arguments joined by `|`) and `zzargv` (prints `<a><b>...`), are `#!/bin/sh` scripts so that `sh -c`, `eval` and nested shells see them too. Neither is named `gh` or `git`: no side effects, and no live pre-bash guard refuses a hand-run probe.

NOTHING HERE ASSERTS ON STDERR. Bash's diagnostic wording moves between versions (an unterminated heredoc's warning, the exit code of a syntax error), and no hook parses it. A bash-less host FAILS rather than skips: running bash is the whole point.

THE ROWS. The IDs follow A0 section 3's tables, with one rename: A0 numbers the separator table S1-S6, which collides with its S1-S3 safe-direction divergences, so those six are SEP1-SEP6 here. Q7 and X1/X2 carry several probes and are split into lettered rows. Every row whose A0 status was `contradicted:L<n>` is a plain passing row now, because A4 fixed L1-L15. The one remaining divergence, S3 (bash splits words on space, tab and newline only, while `shellscan.SPACE` also counts CR, VT and FF), is safe-direction and deliberately kept (see A0 and PLAN-retire-bash-oracles A4); row Q11 PINS it rather than xfailing it, because `check:ci-pytest` counts an xfail as a test that did not pass.
"""

from __future__ import annotations

import ast
import fnmatch
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import uuid
import zipfile
from dataclasses import dataclass, field

import pytest

from rediacc_hooks import dispatch, guards, hookio, shellscan
from rediacc_hooks.guards import block_roundlog_truncate as G

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
    # Review e085085d.1: what shellscan's loop frames (`_loop_word`) and `< <(...)` feed rest on, and so block_protected_files' loop refusals.
    Fact(
        "W21",
        "a redirect after done feeds the whole loop, condition and body",
        'while read f; do zzargv "$f"; done <<< a',
        "<a>\n",
        relies_on=((SS, "_loop_word"), (SS, "_redir_feed")),
        source="done <<< feed",
        check="fed_zzargv",
        extra={"feed": "a"},
    ),
    Fact(
        "W22",
        "< <(...) is a redirect whose target is a process substitution, read as the loop's stdin",
        'while read f; do zzargv "$f"; done < <(echo a)',
        "<a>\n",
        relies_on=((SS, "_procsub"), (SS, "_redir_feed")),
        source="done < <(...) feed",
        check="fed_zzargv",
        extra={"feed": "echo a"},
    ),
    Fact(
        "W23",
        "a loop on the consumer side of a pipe hands its stdin to the commands in its body",
        "echo a b | while true; do xargs zzargv; break; done",
        "<a><b>\n",
        relies_on=((SS, "_loop_word"), (SS, "_stage_feed")),
        source="piped loop body feed",
        check="fed_zzargv",
        extra={"feed": "echo a b"},
    ),
    Fact(
        "W24",
        "a for loop assigns its variable each word of its list in turn",
        'for f in a b; do zzargv "$f"; done',
        "<a>\n<b>\n",
        relies_on=((SS, "_loop_word"),),
        source="for list binding",
        check="loop_vars",
        extra={"loop_vars": {"f": ["a", "b"]}},
    ),
    # Review cac47d16.1: what `shellscan.run_copies` rests on for an xargs-fed copier.
    Fact(
        "W25",
        "xargs appends the fed words AFTER the command's own arguments",
        "echo d | xargs zzargv a",
        "<a><d>\n",
        relies_on=((SS, "run_copies"),),
        source="xargs appends",
    ),
    # An option's value is not the command (review cac47d16.1 sweep, `shellscan._prefix_option`): each of these walked as a command named by the VALUE before.
    Fact(
        "W26",
        "xargs's --max-procs takes the next word as its value",
        "echo a | xargs --max-procs 2 zzargv",
        "<a>\n",
        relies_on=((SS, "_prefix_option"), (SS, "_strip_prefixes")),
        source="xargs long value option",
        check="run_names",
        extra={"names": ["echo", "zzargv"]},
    ),
    Fact(
        "W27",
        "a bundle ending in a value letter takes the next word (-rP 2)",
        "echo a | xargs -rP 2 zzargv",
        "<a>\n",
        relies_on=((SS, "_prefix_option"),),
        source="xargs bundled value option",
        check="run_names",
        extra={"names": ["echo", "zzargv"]},
    ),
    Fact(
        "W28",
        "xargs resolves a unique prefix of a long option (--max-p)",
        "echo a | xargs --max-p 2 zzargv",
        "<a>\n",
        relies_on=((SS, "_prefix_option"),),
        source="xargs abbreviated option",
        check="run_names",
        extra={"names": ["echo", "zzargv"]},
    ),
    Fact(
        "W29",
        "an OPTIONAL value is only ever attached: xargs --max-lines 1 runs 1",
        "echo a | xargs --max-lines 1 zzargv",
        rc_nonzero=True,
        relies_on=((SS, "_prefix_option"),),
        source="xargs optional value",
        check="run_names",
        extra={"names": ["echo", "1"]},
    ),
    Fact(
        "W30",
        "stdbuf's --output takes the next word as its value",
        "stdbuf --output L zzargv a",
        "<a>\n",
        relies_on=((SS, "_prefix_option"),),
        source="stdbuf long value option",
        check="run_names",
        extra={"names": ["zzargv"]},
    ),
    Fact(
        "W31",
        "env --chdir runs the command in that directory",
        "env --chdir {T} sh -c 'zzargv \"$PWD\"'",
        "<{T}>\n",
        relies_on=((SS, "_PREFIX_CHDIR"),),
        source="env --chdir",
        check="chdir",
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
    elif fact.check == "fed_zzargv":
        fed = [r.feed for r in runs if r.name == "zzargv"]
        if not fed or any(f is None or fact.extra["feed"] not in f for f in fed):
            problems.append("zzargv feeds %r, want each to carry %r" % (fed, fact.extra["feed"]))
    elif fact.check == "chdir":
        if [r.cwd for r in runs[:1]] != [_subst("{T}", tmp)]:
            problems.append("the first run's directory %r" % [r.cwd for r in runs[:1]])
    elif fact.check == "run_names":
        if [r.name for r in runs] != fact.extra["names"]:
            problems.append("runs %r" % [r.name for r in runs])
    elif fact.check == "loop_vars":
        bound = [r.loop_vars for r in runs if r.name == "zzargv"]
        if bound != [fact.extra["loop_vars"]]:
            problems.append("zzargv loop variables %r" % bound)
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


# --------------------------------------------------------------------------- where a copy lands ---------------------------------------------------------------------------

# WHERE A COPY LANDS IS THE TOOL'S ANSWER (review cac47d16.1). `shellscan.copy_destination` ports each copier's own option parse, and two guards judge a copy by it. Each row runs the real tool in a scratch directory holding files `a`, `b`, a directory `d` and a directory `src` (with `src/f`), and the files that appear must be exactly where the port says each source lands: inside the destination when the command
# names it a directory (`into`, or a directory on disk), else the destination itself. `ln a` runs from `sub/`, where `.` is not where `a` lives.
COPIES = [
    "cp -t d a",
    "cp --target-directory=d a b",
    "cp --target d a",
    "cp --t d a",
    "cp -rt d src",
    "cp -at d a",
    "cp a d -S .bak",
    "cp -S .bak a e",
    "cp a b -t d",
    "cp --no-preserve mode a e",
    "cp -T a e",
    "cp -- a e",
    "mv -t d a",
    "mv a d -S x",
    "install -m 644 -t d a",
    "install -t d a b",
    "install -ma+r a e",
    "ln -t d a",
    "ln ../a",
    "ln -s a e",
    "rsync a d/ --exclude x",
    "rsync -t a e",
    "rsync -e ssh a e",
    "rsync -rt src d/",
]


@pytest.mark.parametrize("cmd", COPIES)
def test_copy_destination_matches_the_tool(tmp_path, cmd):
    argv = cmd.split()
    if shutil.which(argv[0]) is None:
        pytest.fail("%s is not installed; this row asks the real tool where a copy lands" % argv[0])
    world = tmp_path / "w"
    (world / "d").mkdir(parents=True)
    (world / "src").mkdir()
    (world / "sub").mkdir()
    for rel in ("a", "b", "src/f"):
        (world / rel).write_text(rel, encoding="utf-8")
    run_in = world / "sub" if cmd == "ln ../a" else world
    before = {p.relative_to(world) for p in world.rglob("*")}
    done = subprocess.run(argv, cwd=run_in, capture_output=True, text=True, check=False)
    assert done.returncode == 0, "%s: %s" % (cmd, done.stderr)
    new = {p.relative_to(world) for p in world.rglob("*")} - before
    landed = {p for p in new if not any(q != p and q in p.parents for q in new)}
    found = shellscan.copy_destination(argv[0], argv[1:])
    assert found is not None, "%s copies, and the port says it does not" % cmd
    sources, dest, into = found
    target = pathlib.Path(os.path.normpath(run_in / dest))
    want = {
        (
            target / pathlib.Path(s.rstrip("/")).name if into or target.is_dir() else target
        ).relative_to(world)
        for s in sources
    }
    assert landed == want, "%s landed %s; the port says %s" % (cmd, sorted(landed), sorted(want))


def test_copy_destination_reads_no_copy_where_there_is_none():
    """The other direction: `install -d` makes directories, a lone `cp` operand copies nothing, and a non-copier is not read."""
    assert shellscan.copy_destination("install", ["-d", "a", "b"]) is None
    assert shellscan.copy_destination("cp", ["a"]) is None
    assert shellscan.copy_destination("cat", ["a", "b"]) is None


# --------------------------------------------------------------------------- where an xargs-fed copy lands ---------------------------------------------------------------------------

# WHERE A FED WORD LANDS IS THE TOOL'S ANSWER TOO (#5077391c). xargs APPENDS what it reads to the command's own arguments, so under `-t` a fed word is a SOURCE and without it the last fed word is the destination. `shellscan.run_copies` once read every fed word as a destination, `-t` or not, and answered "into a directory" for a fed file. Each row runs the real pipeline in the world `test_copy_destination_matches_the_tool` builds, and
# `shellscan.copy_landings` must name exactly the files that appeared. The EXACT rows have a literal producer (an `echo`, a here-string) and an xargs that appends once, so the port places every word; the FAIL-SAFE rows (a `-n1` split, a producer whose output is not computed) must name every file that appeared, and may name more.
FED_EXACT = [
    "echo a | xargs cp -t d",
    "echo b | xargs cp -t d a",
    "echo e | xargs cp a",
    "echo b d | xargs cp a",
    "echo d | xargs cp a b",
    "echo a b | xargs -r cp -t d",
    "echo e | xargs mv a",
    "echo b | xargs mv -t d a",
    "echo b | xargs install -t d a",
    "echo e | xargs install -m 644 a",
    "xargs cp a <<< e",
    "xargs cp -t d <<< 'a b'",
    # Review 126f2a9f.4: `c` holds the same bytes as `a`, so only its stat shows this overwrite.
    "echo c | xargs cp a",
    # Review 126f2a9f.1: a heredoc body is not brace-, tilde- or glob-expanded, quoted delimiter or not, so these names reach cp as written.
    "xargs cp a <<'EOF'\n{e}\nEOF",
    "xargs cp a <<EOF\n{e,f}\nEOF",
    # Review 126f2a9f.3: a producer whose stdout goes to a file feeds xargs nothing.
    "echo e > /dev/null | xargs -r cp a",
]
FED_FAIL_SAFE = [
    "echo e f | xargs -n1 cp a",
    "printf '%s\\n' e | xargs cp a",
    "ls | grep -x b | xargs cp -t d",
    # Review 126f2a9f.1: bash expands these before xargs reads them, so their words are unknown here and read fail-safe.
    "echo {b,d} | xargs cp a",
    "echo ~/e | xargs cp a",
    "xargs cp a <<< ~/e",
    "echo /T/[w]/[d] | xargs cp a",
    # Review 8ae5b370.3: a relative glob is matched in the directory the producer runs in, here the `cd` before the pipeline.
    "cd src && echo f* | xargs cp ../a",
    # Review a165575f.1: the producer's own `cd`, inside its subshell, decides where its glob matches.
    "(cd src; echo f*) | xargs -I{} cp a src/{}",
    # Review a165575f.2: a failed `cd` leaves the shell where it was, and the glob matches there.
    "cd nosuch; echo b* | xargs cp a",
    # Review 8ae5b370.1/.2/.4: an unmatched `{` before a brace, a stepped range, a letter range.
    "echo x{y{d,e}x | xargs -n1 cp a",
    "echo {b..d..2} | xargs cp a",
]


def _fed_world(tmp_path):
    world = tmp_path / "w"
    (world / "d").mkdir(parents=True)
    (world / "src").mkdir()
    for rel in ("a", "b", "src/f"):
        (world / rel).write_text(rel, encoding="utf-8")
    (world / "c").write_text("a", encoding="utf-8")
    # Every seed starts at mtime 1ns, so a copy that rewrites a file with the bytes it already held still moves its stat (review 126f2a9f.4).
    for path in world.rglob("*"):
        if path.is_file():
            os.utime(path, ns=(1, 1))
    return world


def _stamp(path):
    st = path.stat()
    return st.st_ino, st.st_mtime_ns, path.read_bytes()


def _fed_landed(bash, world, cmd):
    """The files the real pipeline wrote, as paths relative to `world`: new ones, and old ones whose inode, mtime or bytes changed."""
    before = {p: _stamp(p) for p in world.rglob("*") if p.is_file()}
    done = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", cmd],
        cwd=world,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(world)},
        timeout=30,
    )
    assert done.returncode == 0, "%s: %s" % (cmd, done.stderr)
    return {
        p.relative_to(world)
        for p in world.rglob("*")
        if p.is_file() and (p not in before or _stamp(p) != before[p])
    }


def _fed_claimed(world, cmd):
    copier = [r for r in shellscan.every_run(cmd) if r.name in shellscan.COPIERS]
    assert len(copier) == 1, "%s: expected one copier run, the walk found %d" % (cmd, len(copier))
    # A claim outside the world (an unexpanded glob, a home directory elsewhere) names no file the pipeline could write here.
    return {
        pathlib.Path(path).relative_to(world)
        for path, _into in shellscan.copy_landings(copier[0], str(world))
        if pathlib.Path(path).is_relative_to(world)
    }


@pytest.mark.parametrize("cmd", FED_EXACT)
def test_fed_copy_lands_where_the_tool_puts_it(bash, tmp_path, cmd, monkeypatch):
    world = _fed_world(tmp_path)
    monkeypatch.setenv("HOME", str(world))
    claimed = _fed_claimed(world, cmd)
    landed = _fed_landed(bash, world, cmd)
    assert landed == claimed, "%s wrote %s; shellscan says %s" % (
        cmd,
        sorted(landed),
        sorted(claimed),
    )


@pytest.mark.parametrize("cmd", FED_FAIL_SAFE)
def test_fed_copy_fails_safe_where_the_words_are_unknown(bash, tmp_path, cmd, monkeypatch):
    world = _fed_world(tmp_path)
    # bash runs with HOME=<world> (`_fed_landed`), and the fail-safe reading expands `~` for the user the hook runs as.
    monkeypatch.setenv("HOME", str(world))
    cmd = cmd.replace("/T/", "%s/" % tmp_path)
    claimed = _fed_claimed(world, cmd)
    landed = _fed_landed(bash, world, cmd)
    assert landed <= claimed, "%s wrote %s; shellscan names only %s" % (
        cmd,
        sorted(landed),
        sorted(claimed),
    )


def _old_run_copies(run, argv=None, cwd=None):
    """The placement before #5077391c, kept only as the plant below: every fed word a destination, `-t` or not, and "into a directory" for the fed-only shape."""
    # The old reading matched no glob anywhere, so the directory `copy_landings` now hands over is set aside.
    del cwd
    name = run.name.rsplit("/", 1)[-1]
    if name not in shellscan.COPIERS:
        return None
    argv = list(run.argv if argv is None else argv)
    found = shellscan.copy_destination(name, argv)
    fed = run.feed.split() if run.feed and "xargs" in run.via else []
    if found is None:
        return ([a for a in argv if not a.startswith("-")], fed, True) if fed else None
    sources, dest, into = found
    if fed:
        return [*sources, dest], [dest, *fed], into
    return sources, [dest], into


def test_the_fed_copy_rows_can_fail(bash, tmp_path, monkeypatch):
    """The plant: the old feed placement put back, and the exact rows that read the feed through `-t` or a fed destination go red."""
    monkeypatch.setattr(shellscan, "run_copies", _old_run_copies)
    red = []
    for k, cmd in enumerate(
        ("echo b | xargs cp -t d a", "echo e | xargs cp a", "echo a | xargs cp -t d")
    ):
        world = _fed_world(tmp_path / str(k))
        if _fed_claimed(world, cmd) != _fed_landed(bash, world, cmd):
            red.append(cmd)
    assert len(red) == 3, "the old placement still matched the tool on: %s" % sorted(
        {"echo b | xargs cp -t d a", "echo e | xargs cp a", "echo a | xargs cp -t d"} - set(red)
    )


# WHEN THE FED WORDS COUNT AS EXACT (review 126f2a9f.1-.3). Exact only where bash expands nothing before xargs reads the text (the measurements above `_PLAIN_WORD` in shellscan), only from the stdin bash really connects (the command's own heredoc or here-string wins over the pipe, and one it cannot read leaves the feed unknown), and an `echo` whose stdout goes elsewhere feeds nothing.
FEED_WORDS = [
    ("echo b | xargs cp -t d", ["b"]),
    ("echo 'a b' | xargs cp -t d", ["a", "b"]),
    ("echo ~/x | xargs cp -t d", None),
    ("echo a=~/x | xargs cp -t d", None),
    ("echo {x,y} | xargs cp -t d", None),
    ("echo g* | xargs cp -t d", None),
    ("echo <(true) | xargs cp -t d", None),
    ("echo $HOME | xargs cp -t d", None),
    ("xargs cp -t d <<< ~/x", None),
    ("xargs cp -t d <<< a:~/x", None),
    ("xargs cp -t d <<'EOF'\n~/x {a,b} g*\nEOF", ["~/x", "{a,b}", "g*"]),
    ("xargs cp -t d <<EOF\n$HOME\nEOF", None),
    ("echo a | xargs cp -t d <<'EOF'\nb\nEOF", ["b"]),
    ("echo a | xargs cp -t d < list.txt", None),
    ("echo a | xargs cp -t d <<EOF", None),
    ("echo a > f | xargs cp -t d", []),
    ("echo a >&2 | xargs cp -t d", []),
    ("echo a &> f | xargs cp -t d", []),
    ("echo a 2>/dev/null | xargs cp -t d", ["a"]),
    ("echo a >&1 | xargs cp -t d", ["a"]),
]


@pytest.mark.parametrize(("cmd", "want"), FEED_WORDS)
def test_fed_words_are_exact_only_where_bash_expands_nothing(cmd, want):
    copier = [r for r in shellscan.every_run(cmd) if r.name == "cp"]
    assert len(copier) == 1, cmd
    assert copier[0].feed_words == want, "%s: feed_words %r, want %r" % (
        cmd,
        copier[0].feed_words,
        want,
    )


def _old_literal_word(raw):
    """The literal test before review 126f2a9f.1, kept only as the plant below: `~` and braces counted as literal."""
    return None if re.search(r"[$`*?\[\]'\"\\]", raw) else raw.strip("'\"").split()


def test_the_expansion_rows_can_fail(bash, tmp_path, monkeypatch):
    """The plant: the old literal test put back, and the brace and tilde rows under-claim (bash writes a file the walk does not name)."""
    monkeypatch.setattr(shellscan, "_literal_word", _old_literal_word)
    shellscan._ANALYSIS_CACHE.clear()
    red = []
    for k, cmd in enumerate(("echo {b,d} | xargs cp a", "echo ~/e | xargs cp a")):
        world = _fed_world(tmp_path / str(k))
        monkeypatch.setenv("HOME", str(world))
        if not _fed_landed(bash, world, cmd) <= _fed_claimed(world, cmd):
            red.append(cmd)
    shellscan._ANALYSIS_CACHE.clear()
    assert len(red) == 2, "the old literal test still covered: %s" % red


# BRACE EXPANSION, MEASURED (reviews 8ae5b370.1, .2, .4). Each word is expanded by the real bash (`printf '%s\\n' <word>`, empty words dropped as the shell drops them) and by `shellscan._brace_alternatives`, which must agree on the first `_FED_EXPANSION_CAP` words.
BRACE_WORDS = [
    "x{y{a,b}",
    "x{{a,b}",
    "{a,b",
    "{a,b}}",
    "x}{a,b}",
    "a{b}c",
    "{b}{x,y}",
    "{x{a,b}}",
    "{a,b}{1,2}",
    "{a,}x",
    "{,}",
    "x{a,b{c,d}}y",
    "a{1..3}b{x,y}",
    "{1..9..2}",
    "{9..1..3}",
    "{1..10..3}",
    "{1..3..-1}",
    "{1..2..0}",
    "{-2..2}",
    "{01..03}",
    "{001..10}",
    "{-01..2}",
    "{1..1}",
    "{a..e}",
    "{a..e..2}",
    "{e..a}",
    "{z..a..5}",
    "{a..a}",
    "{a..C}",
    "{1..a}",
    "{1...3}",
    "{ab..c}",
    "{1..200}",
    # Review a165575f.3: seventeen braces, more than the old depth limit of sixteen, still all expand.
    "{a,b}" * 17,
]


@pytest.mark.parametrize("word", BRACE_WORDS)
def test_brace_expansion_matches_bash(bash, word):
    done = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", "printf '%s\\n' " + word],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        timeout=30,
    )
    assert done.returncode == 0, done.stderr
    # Empty words dropped FIRST, then the cap, exactly as `_brace_expand` does (review a165575f.4).
    real = [w for w in done.stdout.split("\n")[:-1] if w != ""][: shellscan._FED_EXPANSION_CAP]
    assert shellscan._brace_alternatives(word) == real, word


def test_a_huge_brace_expansion_stays_capped(monkeypatch):
    """Review 8ae5b370.1: a range of ten billion, or several ranges in one word, produce at most the cap; the old code built the whole list first. Judged by the WORK done (review a165575f.5): every range iterator is counted as it is read, so the bound holds however loaded the machine is."""
    pulled = []
    real_range = shellscan._brace_range

    def counted(body):
        words = real_range(body)
        if words is None:
            return None

        def tally():
            for w in words:
                pulled.append(w)
                yield w

        return tally()

    monkeypatch.setattr(shellscan, "_brace_range", counted)
    shellscan._ANALYSIS_CACHE.clear()
    one = shellscan._brace_alternatives("{1..9999999999}")
    assert len(one) == shellscan._FED_EXPANSION_CAP
    assert one[:3] == ["1", "2", "3"]
    assert len(pulled) <= shellscan._FED_EXPANSION_CAP + 1
    pulled.clear()
    product = shellscan._brace_alternatives("{1..99999999}{1..99999999}{a..z}x")
    assert len(product) == shellscan._FED_EXPANSION_CAP
    assert product[0] == "11ax"
    assert len(pulled) <= 4 * (shellscan._FED_EXPANSION_CAP + 1)
    pulled.clear()
    cmd = "echo {1..9999999999} {1..9999999999} | xargs cp a b"
    copier = [r for r in shellscan.every_run(cmd) if r.name == "cp"]
    landed = shellscan.copy_landings(copier[0], "/nonexistent-root")
    assert landed, "the capped words still reach the copy reader"
    assert len(pulled) <= 4 * (shellscan._FED_EXPANSION_CAP + 1)
    shellscan._ANALYSIS_CACHE.clear()


def test_a_truncated_brace_expansion_falls_back_to_a_glob():
    """Review a165575f.3: when the cap leaves words unread, the fail-safe reading adds the word with every brace as `*`, and that glob's shape, rather than leaving later braces literal."""
    word = "{a,b}" * 17
    words, truncated = shellscan._brace_expand(word)
    assert truncated
    assert len(words) == shellscan._FED_EXPANSION_CAP
    assert "{" not in "".join(words)
    candidates = shellscan._fed_candidates([word], None)
    assert "*" * 17 in candidates
    assert "x" * 17 in candidates
    assert not any("{" in c for c in candidates)


def test_the_producer_directory_and_a_failed_cd(tmp_path):
    """Reviews a165575f.1, .2: a subshell's own `cd` is where its glob matches, and a `cd` to a directory that is not there leaves the shell in the starting one, read as uncertain so the shape fallback stays."""
    (tmp_path / "src").mkdir()
    sub = next(r for r in shellscan.every_run("(cd src; echo f*) | xargs cp a") if r.name == "cp")
    assert "src" in sub.feed_cwds
    directories, uncertain = shellscan._feed_directories(sub, str(tmp_path))
    assert str(tmp_path / "src") in directories
    failed = next(
        r for r in shellscan.every_run("cd nosuch; echo b* | xargs cp a") if r.name == "cp"
    )
    directories, uncertain = shellscan._feed_directories(failed, str(tmp_path))
    assert directories == [str(tmp_path)]
    assert uncertain
    assert "x" in shellscan._fed_candidates(["*"], directories, True)


def test_a_glob_in_an_unknown_directory_keeps_a_name_of_its_shape():
    """Review 8ae5b370.3: with the producer's directory unknown, the pattern stays and one name of its shape is added, so a guard that reads names (a round log's, a running script's) still sees one."""
    assert "pr-babysit-x.md" in shellscan._fed_candidates(["pr-babysit-*.md"], None)
    assert "rex" in shellscan._fed_candidates(["re*"], None)
    assert "rexet" in shellscan._fed_candidates(["[r]e?et"], None)
    assert "xx.sh" in shellscan._fed_candidates(["[!a]?.sh"], None)
    cmd = 'cd "$D" && echo pr-babysit-*.md | xargs cp /tmp/x.md'
    copier = [r for r in shellscan.every_run(cmd) if r.name == "cp"]
    names = {pathlib.Path(p).name for p, _into in shellscan.copy_landings(copier[0], "/tmp")}
    assert "pr-babysit-x.md" in names, names


def test_a_redirect_onto_a_glob_writes_the_one_file_it_matches(bash, tmp_path):
    """#e5b0540a: bash pathname-expands a redirect's target, so `> agent/pr-babysit-*.md` truncates the one log it matches. block_roundlog_truncate reads a redirect target through its expansions for this reason. With two matches bash refuses the redirect as ambiguous, and with none it creates the literal name."""
    (tmp_path / "agent").mkdir()
    log = tmp_path / "agent" / "pr-babysit-0831-1.md"
    log.write_text("history\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(tmp_path)}
    one = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", "echo x > agent/pr-babysit-*.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert one.returncode == 0, one.stderr
    assert log.read_text(encoding="utf-8") == "x\n"
    (tmp_path / "agent" / "pr-babysit-0831-2.md").write_text("other\n", encoding="utf-8")
    two = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", "echo y > agent/pr-babysit-*.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert two.returncode != 0
    assert log.read_text(encoding="utf-8") == "x\n"


def test_a_launched_run_reads_its_glob_by_shape_too(tmp_path):
    """Review 9ed30a8a.1: a run `find -exec` starts is uncertain (the shape reading is added beside its disk matches), and one started ELSEWHERE (`-execdir`, each match's own directory) names no directory at all."""
    (tmp_path / "src").mkdir()
    here = r"find . -maxdepth 0 -exec sh -c 'echo f* | xargs cp a' \;"
    there = r"find . -maxdepth 1 -execdir sh -c 'echo f* | xargs cp a' \;"
    plain = "echo f* | xargs cp a"
    for cmd, want_dirs, want_uncertain in (
        (here, [str(tmp_path)], True),
        (there, [], True),
        (plain, [str(tmp_path)], False),
    ):
        copier = next(r for r in shellscan.every_run(cmd) if r.name == "cp")
        assert shellscan._feed_directories(copier, str(tmp_path)) == (want_dirs, want_uncertain), (
            cmd
        )


LOG_NAME_CORPUS = [
    "pr-babysit-0831-1.md",
    "pr-babysit-1008-1.md",
    "pr-babysit-x.md",
    "pr-babysit-a.b-c_d.md",
    "pr-babysit-0831-1-briefing.md",
    "pr-babysit-.md",
    "pr-babysit-x.mdx",
    "notes-1.md",
    "x.md",
    "pr-babysit-x.txt",
]


@pytest.mark.parametrize(
    "glob_pattern",
    [
        "*.md",
        "pr-*",
        "p?-babysit-*",
        "[p]r-babysit-x.md",
        "pr-babysit-a*.md",
        "pr-babysit-?.md",
        "*-briefing.md",
        "pr-babysit-*.m?",
        "notes-*.md",
        "*.txt",
        "[!p]*.md",
        "pr-babysit-.md",
    ],
)
def test_the_roundlog_prefilter_meets_every_log_name_a_glob_can(glob_pattern):
    """Review 9ed30a8a.3: `_glob_meets_log` is the intersection of the glob and the round-log pattern, read from `RL` itself. Sound against every name in a corpus (a name both match forces True), and exact on the negatives the corpus cannot show."""
    witnessed = any(
        fnmatch.fnmatchcase(name, glob_pattern) and re.fullmatch(G.RL, name)
        for name in LOG_NAME_CORPUS
    )
    if witnessed:
        assert G._glob_meets_log(glob_pattern), glob_pattern
    if glob_pattern in ("notes-*.md", "*.txt", "[!p]*.md", "pr-babysit-.md"):
        assert not G._glob_meets_log(glob_pattern), glob_pattern


def test_the_roundlog_automaton_is_read_from_rl(monkeypatch):
    """Review 9ed30a8a.3: a change to `RL` that leaves `<prefix>[<class>]+<suffix>` raises at once rather than leaving the prefilter testing an old pattern; one that keeps the shape is read."""
    monkeypatch.setattr(G, "RL", r"round-log-(\d+)\.md")
    with pytest.raises(RuntimeError):
        G._log_automaton()
    monkeypatch.setattr(G, "RL", r"rl-[0-9]+\.txt")
    edges, accept = G._log_automaton()
    assert accept == ("S", 4)
    assert ("S", 0) not in edges or edges[("S", 0)][0][0] == frozenset(".")


# --------------------------------------------------------------------------- pr_selector's cut is linear (worklist #bc7d998c round) ---------------------------------------------------------------------------

# `pr_selector` cut each record with `re.subn(".*gh pr <verb>[<SPACE>]*", "", record, count=1)`. A line naming no `gh pr <verb>` made that regex try every start position and backtrack from each to the line's end: 0.29 s at 20,000 characters and 36 s at 200,000 (measured 2026-10-11). `shellscan._cut_through_last` reads one pass per line; these tests pin that it answers exactly as the regex did and that the WORK is one line span per
# line, whatever the line's length, rather than a wall clock.
_CUT_CASES = [
    "",
    "gh pr merge 12",
    "x gh pr merge 1 gh pr merge 2 tail",
    "gh pr merge\t\v 7",
    "no verb here",
    "first line\ngh pr merge 3\ngh pr merge 4",
    "gh pr merge\n  next line",
    "gh pr mergeX",
    "a\rgh pr merge\r 9",
]


@pytest.mark.parametrize("record", _CUT_CASES)
@pytest.mark.parametrize("verb", ["merge", "ready"])
def test_cut_through_last_answers_as_the_regex(record, verb):
    old = re.compile(r".*gh pr " + verb + r"[" + shellscan.SPACE + r"]*").subn("", record, count=1)
    assert shellscan._cut_through_last(record, "gh pr " + verb) == old


def test_cut_through_last_answers_as_the_regex_on_a_seeded_sample():
    pieces = ["gh pr merge", "gh pr ", "merge", " ", "\t", "\n", "\r", "\v", "x", "-", "t", "n"]
    rng = __import__("random").Random(11)
    for _ in range(5000):
        record = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        old = re.compile(r".*gh pr merge[" + shellscan.SPACE + r"]*").subn("", record, count=1)
        assert shellscan._cut_through_last(record, "gh pr merge") == old, repr(record)


def test_pr_selector_reads_each_line_once(monkeypatch):
    """The work is one line span per line, never one attempt per character: a 200,000-character line is one span."""
    spans = []
    real = shellscan._line_spans

    def counted(text):
        for span in real(text):
            spans.append(span)
            yield span

    monkeypatch.setattr(shellscan, "_line_spans", counted)
    assert shellscan.pr_selector("x" * 200000, "merge") == ""
    assert len(spans) == 1
    spans.clear()
    assert shellscan.pr_selector("y" * 100000 + " gh pr merge 42", "merge") == "42\n"
    assert len(spans) == 1


def test_pr_selector_never_scans_a_line_with_a_leading_dot_star(monkeypatch):
    """The quadratic shape itself: an unanchored scan (`search`, `sub`, `subn`, `findall`, `finditer`) of a pattern opening with `.*` restarts at every position. The cut may use an anchored `match` at one position, never that."""
    scans = []
    real_compile = re.compile

    class Recorded:
        def __init__(self, compiled):
            self._compiled = compiled

        def __getattr__(self, name):
            attr = getattr(self._compiled, name)
            unanchored = name in ("search", "sub", "subn", "findall", "finditer")
            if unanchored and self._compiled.pattern.startswith(".*"):
                scans.append((name, self._compiled.pattern))
            return attr

    monkeypatch.setattr(
        re, "compile", lambda pattern, flags=0: Recorded(real_compile(pattern, flags))
    )
    assert shellscan.pr_selector("x" * 2000 + " gh pr merge 42", "merge") == "42\n"
    assert shellscan.pr_selector("x" * 2000, "merge") == ""
    assert scans == []


@pytest.mark.parametrize(
    ("cmd", "bases"),
    [
        ('cd "$D" && cp a b', 2),
        ("cd ~ && cp a b", 2),
        ("cd - && cp a b", 2),
        ("cd nosuch-dir && cp a b", 2),
        ("cp a b", 1),
    ],
)
def test_an_unresolved_cd_lands_under_both_bases(tmp_path, cmd, bases):
    """Review 1d4e1754.2: `run.cwd` is None only when no `cd` ran (one base, the starting directory); an unresolved or failed `cd` leaves a path that is not on disk, and the copy is read under that path and under the starting directory."""
    copier = next(r for r in shellscan.every_run(cmd) if r.name == "cp")
    assert (copier.cwd is None) == (bases == 1)
    landed = [p for p, _into in shellscan.copy_landings(copier, str(tmp_path))]
    assert len(landed) == bases, landed
    assert str(tmp_path / "b") in landed


def test_a_nul_byte_in_an_argument_is_a_command_that_did_not_run(tmp_path):
    """subprocess raises ValueError for a NUL in argv or cwd; uncaught, it crashed the guard, and a crashed guard admits the command (2026-10-15)."""
    assert hookio.run_out(["git", "rev-parse", "--verify", "-q", "a\0b"], want_rc=True) is None
    assert hookio.run_out(["git", "rev-parse", "a\0b"]) == ""
    assert hookio.run_rc(["true", "a\0b"]) == 127
    assert hookio.git_out(["rev-parse", "HEAD"], cwd=str(tmp_path) + "\0x", want_rc=True) is None


@pytest.mark.parametrize(
    ("text", "sent"),
    [
        ("a\udcffb", b"a\xffb"),
        ("x\ud800y", b"x\xed\xa0\x80y"),
        ("\udcff\ud800", b"\xff\xed\xa0\x80"),
        ("plain é", "plain é".encode()),
    ],
)
def test_a_str_stdin_holding_a_lone_surrogate_reaches_the_command_as_bytes(text, sent):
    """Review 46b000ae.1/.2: a str stdin holding a lone surrogate raised UnicodeEncodeError out of run_out and crashed the guard, which admits the command; an escaped byte (U+DC80..U+DCFF) goes back to the byte it was decoded from, and any other lone surrogate goes as its surrogatepass bytes."""
    echo_hex = "import sys; sys.stdout.write(sys.stdin.buffer.read().hex())"
    assert hookio.run_out([sys.executable, "-c", echo_hex], stdin=text, want_rc=True) == sent.hex()


# Built with chr() so the file holds the two surrogate code points themselves, never a character an editor or a JSON layer joined on the way in.
_HIGH, _LOW = chr(0xD83D), chr(0xDE00)


@pytest.mark.parametrize(
    ("text", "sent"),
    [
        ("x" + _HIGH + _LOW, b"x\xf0\x9f\x98\x80"),
        (_HIGH + _LOW + chr(0xDCFF), b"\xf0\x9f\x98\x80\xff"),
        # Review 98777d8c.1: a low half in U+DC80..U+DCFF is an escaped byte, never the second half of a pair.
        (_HIGH + chr(0xDC80), b"\xed\xa0\xbd\x80"),
        (_HIGH + chr(0xDCFF), b"\xed\xa0\xbd\xff"),
        ("x" + _HIGH + chr(0xDCFF) + _HIGH + _LOW, b"x\xed\xa0\xbd\xff\xf0\x9f\x98\x80"),
        (_HIGH + chr(0xDC7F), b"\xf0\x9f\x91\xbf"),
        (_HIGH + chr(0xDD00), b"\xf0\x9f\x94\x80"),
        (_LOW + _HIGH, b"\xed\xb8\x80\xed\xa0\xbd"),
        (_HIGH + "a", b"\xed\xa0\xbda"),
    ],
)
def test_a_str_stdin_holding_a_surrogate_pair_reaches_the_command_as_its_code_point_review_2925782e(
    text, sent
):
    """Review 2925782e.2: `_stdin_bytes`' fallback encoded each half of a valid pair as a three-byte surrogatepass form, so U+D83D U+DE00 reached the command as six bytes and not the four of U+1F600. A pair in the wrong order and a high surrogate with no low one stay lone surrogates."""
    assert any(0xD800 <= ord(ch) <= 0xDFFF for ch in text), ascii(text)
    echo_hex = "import sys; sys.stdout.write(sys.stdin.buffer.read().hex())"
    assert hookio.run_out([sys.executable, "-c", echo_hex], stdin=text, want_rc=True) == sent.hex()


def test_a_pr_head_holding_a_nul_byte_is_refused_not_a_crash():
    """`gh pr create --head` with a NUL reached `git rev-parse` in block_unproven_bulk_transform._pr_head and crashed it, which admitted the create."""
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --head $'feat\\x00x' --title t --body b"},
            "cwd": str(hookio.repo_root()),
        }
    )
    rc, _out, err = dispatch.run_one("block_unproven_bulk_transform", payload)
    assert "Traceback" not in err, err
    assert "embedded null byte" not in err, err
    # _pr_head reads the NUL ref as one this checkout cannot resolve, and the caller refuses None.
    assert rc == 2, (rc, err)
    assert "no local or origin/ ref" in err, err


# THE DIRECTORY A `cd` SETS IS ITS EXPANDED OPERAND (#d0079b4e). At 9829a0b78 the walk read the operand of `cd` as typed, so after `D=lnk; cd $D` the run's directory was the literal `$D`, and `D=agent/revi; cd ${D}ews/x && tee x.md` was allowed by block_review_file_shell_write (rc 0) with no link at all.
# The same sweep found the walk ignoring OLDPWD (`cd -`), the directory stack (`popd`, `pushd` with no operand or `+N`), CDPATH, and the expansion of `env -C`/`sudo -D`/`git -C`. Each row below runs through a real bash in a scratch tree and compares the directory bash ends in (`pwd -P`, the last line printed) with the walk's directory for the same command, resolved on disk by `shellscan.write_directory`.
# `{P}` is the probe: `pwd -P` for bash, `true` for the walk, so the walk's last run sits exactly where bash prints.
DIRECTORY_ROWS = (
    ("D=a; cd $D && {P}", "a"),
    ('D=a; cd "$D"/x && {P}', "a/x"),
    ("O=-P; cd $O lnk/.. && {P}", "far"),
    ("E=; cd $E b && {P}", "b"),
    ("D=a; builtin cd $D && {P}", "a"),
    ("D=a; command cd $D && {P}", "a"),
    ("set -P; D=lnk/..; cd $D && {P}", "far"),
    ('D=a; eval "cd \\$D"; {P}', "a"),
    ("D=a; env -C $D {P}", "a"),
    # OLDPWD: set by every change, exported to a child shell, unset or cleared means no change.
    ("cd a; cd ../b; cd - && {P}", "a"),
    ("cd a; cd ../b; cd -- - && {P}", "a"),
    ("cd a; cd ../b; pushd - && {P}", "a"),
    ('cd a; cd ../b; eval "cd -"; {P}', "a"),
    ("cd a; (cd ../b); cd - && {P}", "."),
    ("cd a; cd ../b | true; cd - && {P}", "."),
    ("OLDPWD=b; cd - && {P}", "b"),
    ("cd a; unset OLDPWD; cd -; {P}", "a"),
    ('cd a; cd ..; bash -c "cd - && {P}"', "a"),
    ('cd a; cd ..; env -i bash -c "cd -; {P}"', "."),
    ("cd lnk; cd ..; cd -P - && cd .. && {P}", "far"),
    ("cd -P lnk; cd ..; cd - && {P}", "far/inner"),
    # The directory stack, from a fresh shell's.
    ("pushd a; pushd ../b; popd && {P}", "a"),
    ("pushd a; pushd ../b; pushd && {P}", "a"),
    ("pushd a; pushd ../b; pushd +1 && {P}", "a"),
    ("pushd a; pushd ../b; pushd +2 && {P}", "."),
    ("pushd a; pushd ../b; pushd -0 && {P}", "."),
    ("pushd a; pushd ../b; popd +1 && {P}", "b"),
    ("pushd a; pushd ../b; popd -2 && {P}", "a"),
    ("pushd a; pushd ../b; popd -n; popd && {P}", "."),
    ("pushd -n a; popd && {P}", "a"),
    ("pushd a; dirs -c; popd; {P}", "a"),
    ("pushd a; (popd); {P}", "a"),
    ("pushd a; eval popd; {P}", "."),
    ("pushd a; cd ../b; popd && {P}", "."),
    # CDPATH: the first entry holding the directory, then the directory itself.
    ("CDPATH=a; cd x && {P}", "a/x"),
    ("CDPATH=a cd x && {P}", "a/x"),
    ("CDPATH=a; cd b && {P}", "b"),
    ("CDPATH=cp1:a; cd x && {P}", "cp1/x"),
    ("CDPATH=nosuch:a; cd x && {P}", "a/x"),
    ("CDPATH=:a; cd x && {P}", "a/x"),
    # Past the old 16-choice cap (review 5dbdf567.1): forty missing entries, then the one holding x.
    ("CDPATH=%s:a; cd x && {P}" % ":".join("n%d" % i for i in range(40)), "a/x"),
    ("CDPATH=b; cd ./a && {P}", "a"),
    ("CDPATH=a; pushd x && {P}", "a/x"),
    ("CDPATH=a; pushd -n x; popd && {P}", "a/x"),
    ("CDPATH=a; OLDPWD=x; cd - && {P}", "a/x"),
    ("CDPATH=a; cd x; cd /; cd - && {P}", "a/x"),
    ("CDPATH=a; cd x; cd .. && {P}", "a"),
    ("CDPATH=a; cd b; cd .. && {P}", "."),
)


def _directory_tree(tmp_path):
    root = tmp_path / "w"
    for d in ("a/x", "b", "cp1/x", "far/inner", "home"):
        (root / d).mkdir(parents=True)
    (root / "lnk").symlink_to("far/inner", target_is_directory=True)
    return pathlib.Path(os.path.realpath(root))


def _bash_landing(bash, root, cmd):
    done = subprocess.run(
        [bash, "--norc", "--noprofile", "-c", cmd.replace("{P}", "pwd -P")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root / "home")},
        timeout=30,
    )
    lines = done.stdout.splitlines()
    assert lines, "%s printed nothing: %s" % (cmd, done.stderr)
    return lines[-1]


def _walk_landing(root, cmd):
    run = shellscan.every_run(cmd.replace("{P}", "true"))[-1]
    assert run.name == "true", (cmd, run.name)
    if run.cwd is None:
        return str(root)
    return os.path.realpath(os.path.join(root, shellscan.write_directory(run.cwd, str(root))))


@functools.cache
def _bash_cd_dash_searches_cdpath(bash_path) -> bool:
    """Whether this bash's `cd -` resolves OLDPWD through CDPATH (5.3 does; 5.2 fails `cd: x: No such file or directory`)."""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "a", "x"))
        done = subprocess.run(
            [str(bash_path), "-c", "CDPATH=a; OLDPWD=x; cd - >/dev/null 2>&1"],
            cwd=d,
            capture_output=True,
            check=False,
        )
    return done.returncode == 0


@pytest.mark.parametrize(("cmd", "landing"), DIRECTORY_ROWS)
def test_the_directory_a_change_sets_is_where_bash_lands_review_d0079b4e(
    bash, tmp_path, cmd, landing
):
    if "CDPATH=" in cmd and "cd -" in cmd and not _bash_cd_dash_searches_cdpath(bash):
        pytest.skip(
            "CANNOT RUN (1 of 1 requirement(s) missing): a bash whose `cd -` searches CDPATH "
            "(bash 5.3 does, 5.2 on ubuntu-24.04 does not); the walk models the newer bash"
        )
    root = _directory_tree(tmp_path)
    want = os.path.normpath(os.path.join(root, landing))
    assert _bash_landing(bash, root, cmd) == want, "the row's own landing is not bash's"
    assert _walk_landing(root, cmd) == want


# A NAME THE WALK CANNOT READ STAYS UNREAD (#d0079b4e sweep). A value it cannot expand keeps the typed operand, whose `$` every reader takes for an unread directory; a home directory or an unknown OLDPWD is never joined under the current directory (`cd sub && cd` read `sub/~`), and a `..` never pops such a name (`cd "$D" && cd ..` read the start).
UNREAD_ROWS = {
    "cd $D && true": "$D",
    'D="a b"; cd $D && true': "$D",
    "D=~; cd $D && true": "$D",
    "cd sub && cd && true": "~",
    "cd sub && cd ~/x && true": "~/x",
    "cd sub && cd - && true": None,
    "cd - && true": "-",
    'cd "$D" && cd .. && true': "$D/..",
    "cd ~ && cd .. && true": "~/..",
    "cd $D/x && cd ../.. && true": "$D/..",
    'cd sub && cd "~" && true': "sub/~",
    "pushd +1 && true": "~",
    "pushd && true": "~",
    # Past the entries this command pushed lies the session's stack, read as before; bash in a fresh shell refuses the index and stays in b.
    "pushd a; pushd ../b; pushd +3; true": "~",
    "popd && true": None,
    "pushd a; pushd -n +1; popd && true": "~",
    "pushd a; popd -- +1; true": "~",
    "pushd a; popd -n -- ; popd && true": "~",
    "env -C $D true": "$D",
}


def test_a_directory_the_walk_cannot_read_stays_unread_review_d0079b4e():
    got = {cmd: shellscan.every_run(cmd)[-1].cwd for cmd in UNREAD_ROWS}
    assert got == UNREAD_ROWS, {c: (got[c], w) for c, w in UNREAD_ROWS.items() if got[c] != w}
    # `git -C` reads its directory expanded too, and as typed when it cannot.
    assert shellscan.every_run("D=sub; git -C $D status")[-1].git_dir == "sub"
    assert shellscan.every_run("git -C $D status")[-1].git_dir == "$D"
    # OLDPWD's text is unresolved wherever it is expanded: the walk cannot spell bash's absolute path.
    assert shellscan.unresolved(shellscan.every_run("cd a; echo $OLDPWD")[-1].xargv[0])
    assert "OLDPWD" not in shellscan.every_run("cd a; printenv")[-1].env


def test_pushd_and_popd_read_their_words_as_bash_does_review_d0079b4e():
    assert shellscan._pushd_op([]) == ("swap",)
    assert shellscan._pushd_op(["-n"]) == ("error",)
    assert shellscan._pushd_op(["a", "b"]) == ("error",)
    assert shellscan._pushd_op(["+1x"]) == ("error",)
    assert shellscan._pushd_op(["-n", "+1"]) == ("rotate", "+", 1, True)
    assert shellscan._pushd_op(["-2"]) == ("rotate", "-", 2, False)
    assert shellscan._pushd_op(["--", "-P"]) == ("dir", "-P", False)
    assert shellscan._pushd_op(["-n", "x"]) == ("dir", "x", True)
    assert shellscan._popd_op([]) == ("pop", "+", 0, False)
    assert shellscan._popd_op(["-n"]) == ("pop", "+", 1, True)
    assert shellscan._popd_op(["-1"]) == ("pop", "-", 1, False)
    assert shellscan._popd_op(["x"]) == ("error",)
    assert shellscan._popd_op(["-x"]) == ("error",)
    assert shellscan._popd_op(["-n", "+1"]) == ("unknown", True)
    assert shellscan._popd_op(["+1", "+1"]) == ("unknown", False)
    assert shellscan._cdpath({}, []) is None
    assert shellscan._cdpath({"CDPATH": ("a:b", None)}, []) == "a:b"
    assert shellscan._cdpath({"CDPATH": ("a", None)}, [("unset", "CDPATH")]) is None
    assert shellscan._cdpath({}, [("set", "CDPATH", "c", False)]) == "c"
    assert shellscan._cdpath({"CDPATH": ("x" + shellscan._UNRESOLVED, None)}, []) is None


# THE GUARDS READ THE EXPANDED DIRECTORY (#d0079b4e), through dispatch.run_one in a scratch tree with no link anywhere. At 9829a0b78 plus the #816a7c93 guard change every `2` row below was allowed (rc 0), and `pushd agent/reviews/x; popd && tee y.md` was refused (rc 2) although bash writes the root's y.md: the walk ignored `popd`.
EXPANDED_DIRECTORY_GUARD_ROWS = (
    ("block_review_file_shell_write", "D=agent/revi; cd ${D}ews/x && tee x.md", 2),
    ("block_review_file_shell_write", "D=agent/revi; pushd ${D}ews/x && tee x.md", 2),
    ("block_review_file_shell_write", "D=ews; builtin cd agent/revi$D/x && echo x > x.md", 2),
    ("block_review_file_shell_write", "D=agent/revi; command cd ${D}ews/x && cp /tmp/a .", 2),
    ("block_review_file_shell_write", "O=-P D=agent/revi; cd $O ${D}ews/x && tee x.md", 2),
    ("block_review_file_shell_write", "cd agent/reviews/x; cd /tmp; cd - && tee y.md", 2),
    ("block_review_file_shell_write", "cd agent/reviews/x; cd /tmp; cd -- - && tee y.md", 2),
    ("block_review_file_shell_write", "pushd agent/reviews/x; pushd /tmp; popd && tee y.md", 2),
    ("block_review_file_shell_write", "pushd agent/reviews/x; pushd /tmp; pushd && tee y.md", 2),
    ("block_review_file_shell_write", "CDPATH=agent/reviews cd x && tee y.md", 2),
    ("block_review_file_shell_write", "CDPATH=agent/reviews; cd x && tee y.md", 2),
    ("block_review_file_shell_write", "D=agent/reviews/x; env -C $D tee y.md", 2),
    ("block_review_file_shell_write", 'cd agent/reviews/x; cd /tmp; bash -c "cd - && tee y.md"', 2),
    # CONTROLS: a read, a near miss, a plain directory, a step back out, a CDPATH entry that does not hold the directory, and an OLDPWD `env -i` cleared.
    ("block_review_file_shell_write", "D=agent/revi; cd ${D}ews/x && cat x.md", 0),
    ("block_review_file_shell_write", "D=agent/revi; cd ${D}ew && tee x.md", 0),
    ("block_review_file_shell_write", "D=plain; cd $D && tee x.md", 0),
    ("block_review_file_shell_write", "cd agent/reviews/x; cd /tmp; cd - && cat y.md", 0),
    ("block_review_file_shell_write", "pushd agent/reviews/x; popd && tee y.md", 0),
    ("block_review_file_shell_write", "CDPATH=agent/reviews cd plain && tee y.md", 0),
    (
        "block_review_file_shell_write",
        'cd agent/reviews/x; cd /tmp; env -i bash -c "cd - && tee y.md"',
        0,
    ),
    (
        "block_user_only_command_shell_write",
        'D=.claude/comm; cd ${D}ands/sub && echo "disable-model-invocation: true" | tee x.md',
        2,
    ),
    (
        "block_user_only_command_shell_write",
        'cd .claude/commands/sub; cd /tmp; cd - && echo "disable-model-invocation: true" | tee x.md',
        2,
    ),
    (
        "block_user_only_command_shell_write",
        'CDPATH=.claude/commands cd sub && echo "disable-model-invocation: true" | tee x.md',
        2,
    ),
    (
        "block_user_only_command_shell_write",
        'D=.claude/comm; cd ${D}ands/sub && echo "description: x" | tee x.md',
        0,
    ),
    (
        "block_user_only_command_shell_write",
        'D=plain; cd $D && echo "disable-model-invocation: true" | tee x.md',
        0,
    ),
)


def test_the_write_guards_read_the_expanded_directory_review_d0079b4e(tmp_path):
    root = os.path.realpath(tmp_path)
    for d in ("agent/reviews/x", ".claude/commands/sub", "plain", ".ci/config"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "model-invocation-exceptions.json").write_text(
        '{"exceptions": []}'
    )
    wrong = []
    for stem, command, want in EXPANDED_DIRECTORY_GUARD_ROWS:
        rc, _out, err = dispatch.run_one(
            stem,
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": root}),
        )
        if rc != want:
            wrong.append((stem, command, rc, want, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))
    # Both directions, through both guards: neither table half is vacuous.
    for stem in ("block_review_file_shell_write", "block_user_only_command_shell_write"):
        verdicts = [w for s, _c, w in EXPANDED_DIRECTORY_GUARD_ROWS if s == stem]
        assert 2 in verdicts, stem
        assert 0 in verdicts, stem


def test_a_cdpath_chain_past_the_search_cap_takes_the_fallback_review_4a08d9e8():
    """One searched cd keeps every CDPATH choice; a chain whose product passes `_SEARCH_CAP` takes the plain fallback, the reading every reader had before the walk knew CDPATH (review 4a08d9e8.2)."""
    entries = ":".join("n%d" % i for i in range(64))
    one = [r for r in shellscan.every_run("CDPATH=%s cd x && tee y" % entries) if r.name == "tee"]
    assert len(getattr(one[0].cwd, "choices", ())) == 65
    # Two chained searches multiply: 65 x 65 = 4225 choices, past the cap.
    chain = "export CDPATH=%s; cd x; cd y && tee w" % entries
    runs = [r for r in shellscan.every_run(chain) if r.name == "tee"]
    assert shellscan._SEARCH_CAP < 65 * 65
    assert not hasattr(runs[0].cwd, "choices"), "a product past the cap keeps a choice list"
    assert str(runs[0].cwd) == "x/y"


# --------------------------------------------------------------------------- what a launcher, a `-c` shell, eval and ssh are handed (#156caed2) ---------------------------------------------------------------------------

# THE INNER COMMAND IS READ FROM THE EXPANDED WORDS. bash expands every word once before the command runs, so in `B=q; npx node $B` node is handed `q`. Before #156caed2 the walk built a launched command from the words as typed (`_quote_argv(argv)`): the launched node run held the literal `$B`, a double-quoted `bash -c "node $B"` payload was read in the child shell where an unexported B is unknown, and `N=bash; $N -c ...` was never read as a shell.
# A word whose value the walk cannot know keeps its TYPED text (`_launch_words`), which block_unscoped_formatter_run leans on: it refuses `npx prettier --write $files` because the literal `$` survives. Each row is `(command, the run's name, the field read, the value it must hold)`; a field of "names" reads every run's name, "spans" the command-position text `_Analysis.names` records.
U = shellscan._UNRESOLVED
LAUNCHED_SHAPE_ROWS = [
    ("B=q; npx node $B", "node", "argv", ["q"]),
    ("B=q; npx node $B", "node", "launcher", "npx"),
    ("B=q; npm exec -- node $B", "node", "argv", ["q"]),
    ("B=q; npx -y node ${B}", "node", "argv", ["q"]),
    (r"B=q; find . -exec node $B {} \;", "node", "argv", ["q", "{}"]),
    (r"B=q; find . -exec node $B {} \;", "node", "launcher", "find"),
    (r"B=q; find . -execdir node $B \;", "node", "argv", ["q"]),
    (r"B=q; find . -ok node $B \;", "node", "argv", ["q"]),
    (r"D=x; find $D -exec rm {} \;", "rm", "starts", ("x",)),
    (r"E=-exec; find . $E node q \;", "node", "argv", ["q"]),
    ("B=; npx node $B z", "node", "argv", ["z"]),
    ("B=; npx node $B z", None, "spans", ["npx node $B z", "node $B z"]),
    ('B=q; bash -c "node $B"', "node", "xargv", ["q"]),
    ('B=q; sh -ec "node $B"', "node", "xargv", ["q"]),
    ("B=q; bash -c 'node $B'", "node", "xargv", [U]),
    ("N=bash; $N -c 'node x'", None, "names", ["bash", "node"]),
    ("N=/bin/bash; ${N} -c 'node x'", None, "names", ["/bin/bash", "node"]),
    ("O=-c; bash $O 'node x'", None, "names", ["bash", "node"]),
    ("\"$BASH\" -c 'node x'", None, "names", ["$BASH"]),
    ("G=git; $G push --force origin main", "git", "argv", ["push", "--force", "origin", "main"]),
    ("B=q; env -S node $B", "node", "argv", ["q"]),
    ("B=q; env -S node p $B", "node", "argv", ["p", "q"]),
    ('C="node q"; env -S "$C"', "node", "argv", ["q"]),
    ('B=q; npx -c "node $B"', "node", "xargv", ["q"]),
    ('B=q; bun exec "node $B"', "node", "xargv", ["q"]),
    ('B="x; rm f"; eval "echo $B"', "rm", "argv", ["f"]),
    ("C=docker; ssh prod-1 $C ps", "ssh", "remote", ("prod-1", "docker ps")),
    ("B=q; echo $B | xargs node", "node", "feed_words", ["q"]),
    ('B=q; echo "$B" | xargs node', "node", "feed_words", ["q"]),
    ("B=q; xargs node <<< $B", "node", "feed_words", ["q"]),
    ("B=q; xargs node <<EOF\n$B\nEOF", "node", "feed_words", ["q"]),
    ("B=q; echo $B | xargs node", "node", "feed", "echo $B q"),
    # The prefix commands were already right: the command after them is the run, and its operands are in `xargv`. Pinned so a change to the launcher path cannot move them.
    ("B=q; sudo node $B", "node", "xargv", ["q"]),
    ("B=q; timeout 5 node $B", "node", "xargv", ["q"]),
    ("B=q; nohup node $B", "node", "xargv", ["q"]),
    ("B=q; env node $B", "node", "xargv", ["q"]),
    # SOUND UNKNOWN: a value the walk cannot know stays as typed, never `_UNRESOLVED`, inside a launched command.
    ("npx prettier --write $files", "prettier", "argv", ["--write", "$files"]),
    ('npx eslint --fix "$@"', "eslint", "argv", ["--fix", "$@"]),
    ('B="a b"; npx node $B', "node", "argv", ["$B"]),
    ("B='*.js'; npx node $B", "node", "argv", ["$B"]),
    ("npx node $(cat f)", "node", "argv", ["$(cat f)"]),
    ("B=q; echo ~$B | xargs node", "node", "feed_words", None),
    ("echo $UNSET_Q | xargs node", "node", "feed_words", None),
    # THE NAME IS THE FIRST WORD LEFT AFTER EXPANSION (review a7b3a36f.1): a vanished name promotes the next word, a split one becomes the name plus leading arguments, and the prefix commands are stripped again in front of what is left.
    ('N=; $N bash -c "node q"', None, "names", ["bash", "node"]),
    ('N="bash -e"; $N -c "node q"', "bash", "argv", ["-e", "-c", "node q"]),
    ('N="bash -e"; $N -c "node q"', None, "names", ["bash", "node"]),
    ("N=; M=; $N $M env node q", None, "names", ["node"]),
    ("N=; sudo $N node q", None, "names", ["node"]),
    ('N=" "; $N node q', None, "names", ["node"]),
    ('N="env node"; $N q', "node", "argv", ["q"]),
    ("N=; $N node q", None, "spans", ["node q"]),
    # A SPLIT NAME'S PREFIX COMMANDS ARE ITS `via` (review 2e50ca28.1, refuted at d73b26844 and pinned here): the slice is taken over the rewritten words, so `env` and `xargs` that came out of `$N` are named.
    ('N="env node"; $N q', "node", "via", ("env",)),
    ('N="xargs rm"; echo a | $N', "rm", "via", ("xargs",)),
    ('N="sudo xargs rm"; echo a | $N', "rm", "via", ("sudo", "xargs")),
    # ONE TYPED WORD, ONE SPAN (review 2e50ca28.3): the first field takes `$N`, a later one an empty span at its end, so the text reads `$N` once. At d73b26844 both runs of the first row read `$N q`, and the second row's `$N q`.
    ('N="npx node"; $N q', None, "spans", ["$N q", " q"]),
    ('N="env node"; $N q', None, "spans", [" q"]),
    ('N="bash -e"; $N -c "node q"', None, "spans", ['$N -c "node q"']),
    # SOUND UNKNOWN: a glob, a field holding a `$`, a quoted name, an assigned IFS and a promoted word bash reads as a command name and not as an assignment all keep the typed name.
    ('N="a*"; $N -c "node q"', None, "names", ["$N"]),
    ("N='bash $X'; $N -c \"node q\"", None, "names", ["$N"]),
    ('N="bash -e"; "$N" -c "node q"', None, "names", ["$N"]),
    ('IFS=:; N="bash:-c"; $N "node q"', None, "names", ["$N"]),
    ("N=; $N X=1 node q", None, "names", ["$N"]),
    # THE SPLIT IS THE WALK'S IFS: an assigned IFS splits on its own characters (an empty one on none), an unset one is the default.
    ("IFS=:; B=a:b; npx node $B", "node", "argv", ["$B"]),
    ("IFS=; B='a b'; npx node $B", "node", "argv", ["a b"]),
    ("unset IFS; B=q; npx node $B", "node", "argv", ["q"]),
]

# A planted walk that raises on a row has turned that row.
_PLANT_CRASHES = (AttributeError, IndexError, KeyError, TypeError, ValueError)


def _launched_field(module, cmd, name, field):
    module._ANALYSIS_CACHE.clear()
    if field == "names":
        return [r.name for r in module.every_run(cmd)]
    if field == "spans":
        return [cmd[start:end] for start, _first_end, end in module._analyse(cmd).names]
    hits = [r for r in module.every_run(cmd) if r.name == name]
    if not hits:
        return "<no %s run>" % name
    run = hits[0]
    if field == "launcher":
        return run.launch.launcher if run.launch is not None else None
    if field == "starts":
        return run.launch.starts if run.launch is not None else None
    return getattr(run, field)


def _launched_wrong(module):
    wrong = []
    for cmd, name, what, want in LAUNCHED_SHAPE_ROWS:
        try:
            got = _launched_field(module, cmd, name, what)
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != want:
            wrong.append((cmd, what, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_launched_and_payload_runs_read_the_expanded_words_156caed2():
    wrong = _launched_wrong(shellscan)
    assert not wrong, "\n".join(map(repr, wrong))


# WHAT THE INNER PROGRAM RECEIVES, ASKED OF bash 5. Each script runs `zzargv` (prints `<a><b>...` per call) through a launcher, a `-c` shell, eval or xargs, and the walk's runs named zzargv must hand it the same words: `xargv` plus the exact fed words. `B='$Y'` is the pair that separates the two readings: a `-c` payload is parsed again by the inner shell (`<in>`), a `find -exec` argv is executed as it stands (`<$Y>`).
LAUNCHED_BASH_ROWS = [
    ('B=X; find "{T}" -maxdepth 0 -exec zzargv $B \\;', "<X>\n"),
    ('B=; find "{T}" -maxdepth 0 -exec zzargv $B z \\;', "<z>\n"),
    ('unset B; find "{T}" -maxdepth 0 -exec zzargv x $B y \\;', "<x><y>\n"),
    ('E=-exec; find "{T}" -maxdepth 0 $E zzargv X \\;', "<X>\n"),
    ("B='$Y'; export Y=in; find \"{T}\" -maxdepth 0 -exec zzargv $B \\;", "<$Y>\n"),
    ("B='$Y'; export Y=in; bash -c \"zzargv $B\"", "<in>\n"),
    ('B=X; bash -c "zzargv $B"', "<X>\n"),
    ("B='x y'; bash -c \"zzargv $B\"", "<x><y>\n"),
    ('B="a; zzargv Y"; bash -c "zzargv $B"', "<a>\n<Y>\n"),
    ('B="a; zzargv Y"; eval "zzargv $B"', "<a>\n<Y>\n"),
    ("N=bash; $N -c 'zzargv X'", "<X>\n"),
    ("O=-c; bash $O 'zzargv X'", "<X>\n"),
    ("B=X; env -S zzargv $B", "<X>\n"),
    # The first word after the `-S` string sits where `_bash_words` resolves a name, so a later one is what pins the `env -S` trailing words themselves.
    ("B=X; env -S zzargv Y $B", "<Y><X>\n"),
    ("B=X; echo $B | xargs zzargv", "<X>\n"),
    ('B=X; echo "$B" | xargs zzargv', "<X>\n"),
    ("B=X; xargs zzargv <<< $B", "<X>\n"),
    ("N=; $N zzargv X", "<X>\n"),
    ('N="bash -e"; $N -c "zzargv X"', "<X>\n"),
    ("N=; M=; $N $M env zzargv X", "<X>\n"),
    ('N="env zzargv"; $N X', "<X>\n"),
    ("IFS=; B='a b'; find \"{T}\" -maxdepth 0 -exec zzargv $B \\;", "<a b>\n"),
    ('N="xargs zzargv"; echo X | $N', "<X>\n"),
]

# Where the value is not knowable, bash's answer is not what the walk claims, and the walk must claim NO value: the word stays typed (`$...`) or `_UNRESOLVED`.
LAUNCHED_BASH_UNKNOWN_ROWS = [
    ("B=X; bash -c 'zzargv $B'", "\n"),
    ("B='a b'; find \"{T}\" -maxdepth 0 -exec zzargv $B \\;", "<a><b>\n"),
    ('set -- a \'b c\'; find "{T}" -maxdepth 0 -exec zzargv "$@" \\;', "<a><b c>\n"),
    ('IFS=:; B=a:b; find "{T}" -maxdepth 0 -exec zzargv $B \\;', "<a><b>\n"),
]


def _walk_hands_zzargv(module, script):
    module._ANALYSIS_CACHE.clear()
    lines = []
    for run in module.every_run(script):
        if run.name == "zzargv":
            words = [*(run.xargv or ()), *(run.feed_words or ())]
            lines.append("".join("<%s>" % w for w in words) + "\n")
    module._ANALYSIS_CACHE.clear()
    return "".join(lines)


def _launched_bash_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, want) in enumerate(LAUNCHED_BASH_ROWS):
        fact = Fact("L%d" % k, "launched argv", script, want)
        tmp = tmp_path / ("e%d" % k)
        tmp.mkdir()
        rc, out = run_bash(bash_path, fact, tmp)
        assert (rc, out) == (0, want), "bash no longer hands zzargv %r for %s (rc %d)" % (
            out,
            script,
            rc,
        )
        try:
            got = _walk_hands_zzargv(module, _subst(script, tmp))
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != out:
            wrong.append((script, got, out))
    return wrong


def test_the_launched_program_gets_the_argv_bash_hands_it_156caed2(bash, tmp_path):
    wrong = _launched_bash_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))


def test_an_unknowable_launched_word_claims_no_value_156caed2(bash, tmp_path):
    for k, (script, want) in enumerate(LAUNCHED_BASH_UNKNOWN_ROWS):
        fact = Fact("LU%d" % k, "launched argv, unknown", script, want)
        tmp = tmp_path / ("u%d" % k)
        tmp.mkdir()
        assert run_bash(bash, fact, tmp) == (0, want), script
        shellscan._ANALYSIS_CACHE.clear()
        zz = [r for r in shellscan.every_run(_subst(script, tmp)) if r.name == "zzargv"]
        assert zz, script
        for run in zz:
            words = run.xargv or []
            assert any("$" in w or shellscan.unresolved(w) for w in words), (script, words)


# THE PLANTS. Each puts one piece of the #156caed2 reading back the way it was (or breaks it the way a careless version would) in a copy of shellscan loaded from source, and must turn at least one row of the tables above red. A plant that turns none means the tables cannot see that piece.
LAUNCHED_PLANTS = [
    ("the launcher parses the typed words", "_launches(base, mixed)", "_launches(base, argv)"),
    ("the -c payload read as typed", "_shell_payload(mixed)", "_shell_payload(argv)"),
    (
        "the command name read as typed",
        "        words = _bash_words(words, before)\n",
        "",
    ),
    (
        "a vanished name kept as typed",
        "    if value is None:\n        return []\n    if _UNRESOLVED not in value:",
        "    if value is None:\n        return None\n    if _UNRESOLVED not in value:",
    ),
    (
        "a split name kept as typed",
        'elif "IFS" in shell or any(p.kind not in ("lit", "param") for p in word.parts):',
        "elif True:",
    ),
    (
        "prefixes not stripped in front of a resolved name",
        "        rest, _prefixed = _strip_prefixes(out)\n",
        "        rest = out[_lexical_end(out) :]\n",
    ),
    (
        "a promoted assignment read as an assignment",
        "            at == _lexical_end(out)\n",
        "            False\n",
    ),
    (
        "an assigned IFS ignored",
        '    if "IFS" not in shell:\n        return _SPLITS',
        "    if True:\n        return _SPLITS",
    ),
    (
        "an unknown word fed as _UNRESOLVED",
        "mixed.append(_word_value(word) if _UNRESOLVED in value else value)",
        "mixed.append(value)",
    ),
    (
        "a vanished word kept",
        "        if value is None:\n            continue\n        mixed.append(",
        "        if value is None:\n            value = ''\n        mixed.append(",
    ),
    (
        "the -c payload re-quoted",
        "                self.nested(\n                    payload,",
        "                self.nested(\n                    _quote_argv([payload]),",
    ),
    (
        "launched words not re-quoted",
        'src = launched if how == "text" else _quote_argv(launched)',
        'src = launched if how == "text" else " ".join(launched)',
    ),
    (
        "the span not mapped back through keep",
        "words[1 + keep[span[0]]], words[1 + keep[span[1]]]",
        "words[1 + span[0]], words[1 + span[1]]",
    ),
    (
        "eval reads the typed words",
        '                " ".join(mixed),',
        '                " ".join(argv),',
    ),
    ("ssh reads the typed words", "_ssh_remote(mixed)", "_ssh_remote(argv)"),
    (
        "env -S reads the typed words",
        "rest = _quote_argv(_launch_words(words, before)[1])",
        "rest = _quote_argv([_word_value(w) for w in words])",
    ),
    (
        "a fed word holding a variable is unknown",
        "got = _expanded_fed_word(word, shell, True)",
        "got = None",
    ),
]


def _planted_shellscan(old, new):
    src = (HOOKS / "shellscan.py").read_text(encoding="utf-8")
    assert src.count(old) == 1, "plant %r no longer applies to shellscan" % old
    module = types.ModuleType("planted_shellscan")
    module.__file__ = str(HOOKS / "shellscan.py")
    exec(compile(src.replace(old, new), module.__file__, "exec"), module.__dict__)
    return module


@pytest.mark.parametrize(
    ("label", "old", "new"), LAUNCHED_PLANTS, ids=[p[0] for p in LAUNCHED_PLANTS]
)
def test_each_launched_plant_turns_a_row_156caed2(bash, tmp_path, label, old, new):
    module = _planted_shellscan(old, new)
    turned = _launched_wrong(module) + _launched_bash_wrong(module, bash, tmp_path)
    assert turned, "plant %r turns no row: the tables cannot see it" % label


# THE GUARDS READ THE NAME BASH RUNS (review a7b3a36f.1). Through dispatch.run_one in a scratch tree; each `2` row was allowed (rc 0) at a7b3a36f6, where the walk ran each command under the typed name `$N` and never walked the payload or the command behind it. The `0` rows are a read and a print through the same spellings.
NAME_GUARD_ROWS = (
    ('N=; $N bash -c "rm .claude/settings.json"', 2),
    ('N="bash -e"; $N -c "rm .claude/settings.json"', 2),
    ("N=; M=; $N $M env rm .claude/settings.json", 2),
    ('N="env rm"; $N .claude/settings.json', 2),
    ("N=; sudo $N rm .claude/settings.json", 2),
    # review 2e50ca28.1: xargs out of a split name feeds rm the protected path (refused at d73b26844 too; pinned).
    ('N="xargs rm"; echo .claude/settings.json | $N', 2),
    ('N="xargs cat"; echo .claude/settings.json | $N', 0),
    ('N=; $N bash -c "cat .claude/settings.json"', 0),
    ('N="bash -e"; $N -c "echo rm .claude/settings.json"', 0),
    ('N="env cat"; $N .claude/settings.json', 0),
)


def test_block_protected_files_reads_the_name_bash_runs_a7b3a36f(tmp_path):
    root = os.path.realpath(tmp_path)
    wrong = []
    for command, want in NAME_GUARD_ROWS:
        rc, _out, err = dispatch.run_one(
            "block_protected_files",
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": root}),
        )
        if rc != want:
            wrong.append((command, rc, want, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))
    assert {w for _c, w in NAME_GUARD_ROWS} == {0, 2}


# A gh COMMAND SPELLED BY EXPANSION IS THAT COMMAND (review a7b3a36f.2 sweep): `gh_runs` reads the expanded words when every one is known, so `X=pr; gh $X merge` is a merge every gh guard judges, while a value it cannot know stays out.
GH_RUN_ROWS = (
    ("gh pr merge 42", 1),
    ("X=pr; gh $X merge 42", 1),
    ("V=merge; gh pr $V 42", 1),
    ("N=; $N gh pr merge 42", 1),
    ('X="pr merge"; gh $X 42', 0),
    ("gh $X merge 42", 0),
    ("X=pr; gh $X view 42", 0),
)


def test_gh_runs_read_the_expanded_command_a7b3a36f():
    shellscan._ANALYSIS_CACHE.clear()
    got = [(cmd, len(shellscan.gh_pr_runs(cmd, "merge"))) for cmd, _want in GH_RUN_ROWS]
    shellscan._ANALYSIS_CACHE.clear()
    assert got == [(cmd, want) for cmd, want in GH_RUN_ROWS]


# THE FEED IS EXPANDED ONCE (test_landing feed regression from a7b3a36f6). The expanded fed words appended to `feed` for the over-reading guards were read by `stdin_text` as more stdin, so `M=x; cat <<EOF` with a body `a $M ${M}b` handed over `a x xb\n x xb` where bash prints `a x xb\n`. Each row: (command, run, stdin_text, feed_words, feed). A `$` outside a heredoc leaves stdin_text unknown, as test_landing pins; a quoted heredoc stays literal.
FEED_ROWS = (
    ("M=x; cat <<EOF\na $M ${M}b\nEOF", "cat", "a x xb\n", ["a", "x", "xb"], "a $M ${M}b\n x xb"),
    ("B=q; xargs node <<EOF\n$B\nEOF", "node", "q\n", ["q"], "$B\n q"),
    ("B=q; xargs node <<'EOF'\n$B\nEOF", "node", "$B\n", None, "$B\n"),
    ("B=q; xargs node <<< $B", "node", None, ["q"], "$B q"),
    ("B=q; echo $B | xargs node", "node", None, ["q"], "echo $B q"),
    ('B=q; echo "$B" | xargs node', "node", None, ["q"], "echo $B q"),
    ("echo plain | xargs node", "node", "echo plain", ["plain"], "echo plain"),
)


def _feed_wrong(module):
    wrong = []
    for cmd, name, text, words, feed in FEED_ROWS:
        module._ANALYSIS_CACHE.clear()
        run = next(r for r in module.every_run(cmd) if r.name == name)
        got = (module.stdin_text(run, cmd), run.feed_words, run.feed)
        if got != (text, words, feed):
            wrong.append((cmd, got, (text, words, feed)))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_the_feed_is_expanded_once_a7b3a36f():
    wrong = _feed_wrong(shellscan)
    assert not wrong, "\n".join(map(repr, wrong))


def test_the_feed_rows_see_the_appended_values_read_as_stdin_a7b3a36f():
    module = _planted_shellscan(
        "    if run.feed_values is not None:\n", "    if run.feed_values is not None and False:\n"
    )
    assert _feed_wrong(module), "the feed rows cannot see the expanded values read as stdin"


# A REDIRECT TARGET IS READ AS BASH EXPANDS IT (#4deea064). Each row runs in a fresh scratch directory under real bash and names the one file bash creates there (None for none), then `write_targets` must name that file, beside the typed text, and nothing the row lists as not written. At d73b26844 every known row named the typed `$D...` alone. bash expands a redirect like an argument and then needs ONE field, so a value that splits, globs or vanishes is "ambiguous redirect" and the walk keeps the typed word; a group's redirect is opened before its body runs, a command's before its own prefix assignments, and a bare assignment's after them.
REDIRECT_ROWS = [
    ("D=a; echo hi > $D.out", "a.out", ["$D.out", "a.out"]),
    ('mkdir a; D=a; echo hi >> "$D/y"', "a/y", ["$D/y", "a/y"]),
    ("D=x; echo hi > ${D}y", "xy", ["${D}y", "xy"]),
    ("D=a; { D=b; echo hi; } > $D.out", "a.out", ["$D.out", "a.out"]),
    ("D=a; ( D=b; echo hi ) > $D.out", "a.out", ["$D.out", "a.out"]),
    ("D=a; D=b echo hi > $D.out", "a.out", ["$D.out", "a.out"]),
    ("D=a; D=b > $D.out", "b.out", ["$D.out", "b.out"]),
    ('D="p q"; echo hi > $D', None, ["$D"]),
    ("E=; echo hi > $E", None, ["$E"]),
    ("IFS=:; D=p:q; echo hi > $D", None, ["$D"]),
    ('touch ab; D="a*"; echo hi > $D', "ab", ["$D"]),
    ("X=1; echo hi >&$X", None, []),
]


def _created(tmp):
    """The files a row's script left in its scratch directory, relative, beside the stubs and the home the harness builds."""
    return sorted(
        str(p.relative_to(tmp))
        for p in tmp.rglob("*")
        if p.is_file() and p.relative_to(tmp).parts[0] not in ("bin", "home")
    )


def _redirect_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, written, want) in enumerate(REDIRECT_ROWS):
        tmp = tmp_path / ("r%d" % k)
        tmp.mkdir()
        run_bash(bash_path, Fact("R%d" % k, "redirect target", script), tmp)
        created = [f for f in _created(tmp) if f != "ab" or written == "ab"]
        assert created == ([written] if written else []), "bash wrote %r for %s" % (created, script)
        module._ANALYSIS_CACHE.clear()
        try:
            got = module.write_targets(script)
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != want:
            wrong.append((script, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_redirect_target_is_read_as_bash_expands_it_4deea064(bash, tmp_path):
    wrong = _redirect_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))


def test_a_run_carries_its_expanded_redirects_4deea064():
    shellscan._ANALYSIS_CACHE.clear()
    run = next(r for r in shellscan.every_run("cd s && D=x; echo hi > $D/y") if r.name == "echo")
    assert (run.writes, run.xwrites, shellscan.redirect_targets(run)) == (
        ["$D/y"],
        ["x/y"],
        ["$D/y", "x/y"],
    )
    assert [
        m.target
        for m in shellscan.earlier_mutators("D=m; echo x > $D; git commit -F m", "git commit")
    ] == ["$D", "m"]


# AN IN-PLACE OPTION IS READ AS BASH EXPANDS IT (#4deea064). Each row edits `f` (holding `a`) under real bash; the run is in place exactly when bash changed the file, and then `f` is among the files it rewrites. At d73b26844 the first three read `$F` as the script and answered None.
IN_PLACE_ROWS = [
    ("printf 'a\\n' > f; F=-i; sed $F s/a/b/ f", "sed", True),
    ("printf 'a\\n' > f; F=-i.bak; sed $F s/a/b/ f", "sed", True),
    ("printf 'a\\n' > f; F=-pi; perl $F -e 's/a/b/' f", "perl", True),
    ("printf 'a\\n' > f; sed -i s/a/b/ f", "sed", True),
    ("printf 'a\\n' > f; F=-n; sed $F p f", "sed", False),
    ("printf 'a\\n' > f; F=-p; perl $F -e 's/a/b/' f", "perl", False),
]


def _in_place_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, name, edits) in enumerate(IN_PLACE_ROWS):
        tmp = tmp_path / ("i%d" % k)
        tmp.mkdir()
        run_bash(bash_path, Fact("I%d" % k, "in place", script), tmp)
        changed = (tmp / "f").read_text(encoding="utf-8") != "a\n"
        assert changed == edits, "bash %s f for %s" % ("edited" if changed else "left", script)
        module._ANALYSIS_CACHE.clear()
        try:
            run = next(r for r in module.every_run(script) if r.name == name)
            edit = module.in_place_edit(run)
            got: object = edit is not None and "f" in edit[1]
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != edits:
            wrong.append((script, got, edits))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_an_in_place_option_is_read_as_bash_expands_it_4deea064(bash, tmp_path):
    wrong = _in_place_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))
    # A run a caller builds without `xargv` is read as typed, as before.
    built = types.SimpleNamespace(name="sed", argv=["-i", "s/a/b/", "f"])
    assert shellscan.in_place_edit(built) == (["s/a/b/"], ["f"])


# A COPY CARRIES ITS SOURCE (#3ff3bb16). The scratch directory holds `src.py` (prints 1), `src2.py` and an empty `d/`; each row runs under real bash, which prints what the copied script prints, and `interpreter_program` must read the copy the interpreter runs as that text, or as unjudgeable where the copy's content is not knowable here. At d73b26844 the `file` rows were "unjudgeable" (the content of every copy was unknown) or, for a copy into a directory, `(None, None)`: the landing was never recorded, so the disk was read before the copy ran.
COPY_ROWS = [
    ("cp {T}/src.py {T}/dst.py && python3 {T}/dst.py", "1\n", "file"),
    ("cp {T}/src.py {T}/d/ && python3 {T}/d/src.py", "1\n", "file"),
    ("cp -t {T}/d {T}/src.py && python3 {T}/d/src.py", "1\n", "file"),
    ("S={T}/src.py; cp $S {T}/dst.py && python3 {T}/dst.py", "1\n", "file"),
    (
        "printf 'print(2)\\n' > {T}/w.py && cp {T}/w.py {T}/dst.py && python3 {T}/dst.py",
        "2\n",
        "file",
    ),
    ("cp -n {T}/src.py {T}/dst.py && python3 {T}/dst.py", "1\n", "unjudgeable"),
    ("cp {T}/src.py {T}/src2.py {T}/d/ && python3 {T}/d/src.py", "1\n", "unjudgeable"),
    ("cp {T}/missing.py {T}/dst.py; python3 {T}/dst.py", "", "unjudgeable"),
    # Review 0600a464.1: a directory the same command makes is a directory. The first, third and fourth read `n/src.py` from the disk at 2672ed8f6 (`(None, None)`, the copy recorded as a file named `n`), while bash ran the copied script; the second is the control, a destination nothing makes, which is the file.
    ("mkdir -p {T}/n && cp {T}/src.py {T}/n && python3 {T}/n/src.py", "1\n", "file"),
    ("cp {T}/src.py {T}/n && python3 {T}/n", "1\n", "file"),
    ("install -d {T}/n && cp {T}/src.py {T}/n && python3 {T}/n/src.py", "1\n", "file"),
    (
        'mkdir -p "$(echo {T}/n)" && cp {T}/src.py {T}/n && python3 {T}/n/src.py',
        "1\n",
        "unjudgeable",
    ),
    # Review 6238f04a.1: only an earlier run that may make or remove the directory leaves the answer unknown. The first two were "unjudgeable" at 8ef785864, any `git` or `rm` with an unexpandable word counting, while neither can make `n` a directory; the last two still may, and stay unjudgeable.
    ('git -C "$X" status 2>/dev/null; cp {T}/src.py {T}/n && python3 {T}/n', "1\n", "file"),
    ('rm -f -- "$X"; cp {T}/src.py {T}/n && python3 {T}/n', "1\n", "file"),
    (
        'git -C "$X" checkout 2>/dev/null; cp {T}/src.py {T}/n && python3 {T}/n',
        "1\n",
        "unjudgeable",
    ),
    ('rm -f "$X"; cp {T}/src.py {T}/n && python3 {T}/n', "1\n", "unjudgeable"),
]


def _copy_world(tmp):
    (tmp / "d").mkdir()
    (tmp / "src.py").write_text("print(1)\n", encoding="utf-8")
    (tmp / "src2.py").write_text("print(3)\n", encoding="utf-8")


def _copy_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, prints, kind) in enumerate(COPY_ROWS):
        tmp = tmp_path / ("c%d" % k)
        tmp.mkdir()
        _copy_world(tmp)
        command = _subst(script, tmp)
        _rc, out = run_bash(bash_path, Fact("C%d" % k, "copy", script), tmp)
        assert out == prints, "bash printed %r for %s" % (out, script)
        # The walk reads the world as it was before the command ran.
        for path in tmp.rglob("*"):
            rel = path.relative_to(tmp)
            if (
                path.is_file()
                and str(rel) not in ("src.py", "src2.py")
                and rel.parts[0] not in ("bin", "home")
            ):
                path.unlink()
        # A directory the command made is gone too, so the walk cannot read the answer off the disk.
        for path in tmp.iterdir():
            if path.is_dir() and path.name not in ("d", "bin", "home"):
                shutil.rmtree(path)
        module._ANALYSIS_CACHE.clear()
        try:
            run = [r for r in module.every_run(command) if r.name == "python3"][-1]
            text, got = module.interpreter_program(run, command, str(tmp))
            if got == "file" and "print(%s)" % prints.strip() not in (text or ""):
                got = "file holding %r" % text
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != kind:
            wrong.append((script, got, kind))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_copy_carries_its_source_3ff3bb16(bash, tmp_path):
    wrong = _copy_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))


# A FILE A TOOL WRITES THROUGH ITS OWN OUTPUT OPTION IS WRITTEN (#63109cf2). The scratch directory holds `src.py` (prints 1), `w.tar` holding `a.py` (prints 4) and an empty `o/`; each row runs under real bash, then the files and directories it made are removed and `w.tar` is rebuilt, so the walk reads the world as it was before the command ran. Every row names the kind the walk must give the script the last `python3` runs:
# - the first four, a `curl -o`, a `curl -O` and two extractions of w.tar, were `(None, None)` at 8ef785864, the script read as absent while bash ran it, and are "unjudgeable" now;
# - the fifth (review 6c9f6fd8.1) extracts a.py over an echoed a.py, which bash replaces, so the echoed text is not what runs;
# - the next two (review c988ab31.1) echo b.py beside an extraction of w.tar, which holds only a.py: bash runs the echoed b.py, and the walk lists w.tar and reads the echoed text, where c988ab31's drop of the whole directory read "unjudgeable";
# - the next four are extractions whose archive the walk does not list (fed on stdin twice, appended to by an earlier run, written by an earlier copy), so the whole directory is still dropped: bash runs the extracted a.py in the eighth, and in the ninth, tenth and eleventh an echoed or appended b.py, which the walk reads as "unjudgeable" by design;
# - the last two are controls whose script nothing in the line writes.
TOOL_OUTPUT_ROWS = [
    ("curl -s -o {T}/a.py file://{T}/src.py && python3 {T}/a.py", "1\n", "unjudgeable"),
    ("cd {T}/o && curl -sO file://{T}/src.py && python3 src.py", "1\n", "unjudgeable"),
    ("mkdir -p {T}/x && tar -xf {T}/w.tar -C {T}/x && python3 {T}/x/a.py", "4\n", "unjudgeable"),
    ("cd {T}/o && tar -xf {T}/w.tar && python3 a.py", "4\n", "unjudgeable"),
    # Review 6c9f6fd8.1: an extraction over a file an earlier run wrote replaces it, so the earlier echoed text is not what runs.
    (
        "cd {T}/o && echo 'print(1)' > a.py && tar -xf {T}/w.tar && python3 a.py",
        "4\n",
        "unjudgeable",
    ),
    ("cd {T}/o && echo 'print(1)' > b.py && tar -xf {T}/w.tar && python3 b.py", "1\n", "file"),
    (
        "echo 'print(1)' > {T}/o/b.py && tar -xf {T}/w.tar -C {T}/o && python3 {T}/o/b.py",
        "1\n",
        "file",
    ),
    ("cd {T}/o && tar -xf - < {T}/w.tar && python3 a.py", "4\n", "unjudgeable"),
    (
        "cd {T}/o && echo 'print(1)' > b.py && tar -xf - < {T}/w.tar && python3 b.py",
        "1\n",
        "unjudgeable",
    ),
    (
        "cd {T}/o && echo 'print(5)' > b.py && tar -rf {T}/w.tar b.py && echo 'print(2)' > b.py && tar -xf {T}/w.tar && python3 b.py",
        "5\n",
        "unjudgeable",
    ),
    (
        "cp {T}/w.tar {T}/m.tar && cd {T}/o && echo 'print(1)' > b.py && tar -xf {T}/m.tar && python3 b.py",
        "1\n",
        "unjudgeable",
    ),
    ("curl -s -o {T}/b.py file://{T}/src.py && python3 {T}/src.py", "1\n", "file"),
    ("tar -cf {T}/n.tar -C {T} src.py && python3 {T}/src.py", "1\n", "file"),
]


def _write_w_tar(tmp):
    """`w.tar` in `tmp`, holding only `a.py` (prints 4)."""
    (tmp / "a.py").write_text("print(4)\n", encoding="utf-8")
    with tarfile.open(tmp / "w.tar", "w") as archive:
        archive.add(tmp / "a.py", arcname="a.py")
    (tmp / "a.py").unlink()


def _tool_output_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, prints, kind) in enumerate(TOOL_OUTPUT_ROWS):
        tmp = tmp_path / ("t%d" % k)
        (tmp / "o").mkdir(parents=True)
        (tmp / "src.py").write_text("print(1)\n", encoding="utf-8")
        _write_w_tar(tmp)
        command = _subst(script, tmp)
        _rc, out = run_bash(bash_path, Fact("O%d" % k, "tool output", script), tmp)
        assert out == prints, "bash printed %r for %s" % (out, script)
        for path in list(tmp.rglob("*")):
            rel = path.relative_to(tmp)
            if path.is_file() and str(rel) != "src.py" and rel.parts[0] not in ("bin", "home"):
                path.unlink()
        _write_w_tar(tmp)
        for path in tmp.iterdir():
            if path.is_dir() and path.name not in ("o", "bin", "home"):
                shutil.rmtree(path)
        module._ANALYSIS_CACHE.clear()
        try:
            run = [r for r in module.every_run(command) if r.name == "python3"][-1]
            _text, got = module.interpreter_program(run, command, str(tmp))
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != kind:
            wrong.append((script, got, kind))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_tool_output_option_writes_its_file_63109cf2(bash, tmp_path):
    wrong = _tool_output_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))
    # The options each tool spells, read without running it: wget is not driven against a URL here.
    shellscan._ANALYSIS_CACHE.clear()
    outputs = {
        cmd: shellscan._tool_outputs(next(iter(shellscan.every_run(cmd))))
        for cmd in (
            "wget -qO a.py https://x.invalid/y",
            "wget --output-document=a.py https://x.invalid/y",
            "wget -nv -P d https://x.invalid/s/a.py",
            "wget -r https://x.invalid/",
            "curl -sSLo a.py https://x.invalid/y",
            "curl --output-dir d -O https://x.invalid/s/a.py?v=1",
            "unzip -q x.zip -d d",
            "unzip -l x.zip",
            "tar -czf x.tgz d",
            "curl -o - https://x.invalid/y",
            "curl --output-dir d -o a.py https://x.invalid/y",
            "curl -O example.invalid/s/a.py",
            "wget example.invalid/s/a.py",
        )
    }
    assert outputs == {
        "wget -qO a.py https://x.invalid/y": (["a.py"], []),
        "wget --output-document=a.py https://x.invalid/y": (["a.py"], []),
        "wget -nv -P d https://x.invalid/s/a.py": (["d/a.py"], []),
        "wget -r https://x.invalid/": (["index.html"], ["."]),
        "curl -sSLo a.py https://x.invalid/y": (["a.py"], []),
        "curl --output-dir d -O https://x.invalid/s/a.py?v=1": (["d/a.py"], []),
        "unzip -q x.zip -d d": ([], ["d"]),
        "unzip -l x.zip": ([], []),
        "tar -czf x.tgz d": ([], []),
        "curl -o - https://x.invalid/y": ([], []),
        # Reviews 6c9f6fd8.2, .3: --output-dir applies to -o, and a schemeless operand is a URL to curl and wget.
        "curl --output-dir d -o a.py https://x.invalid/y": (["d/a.py"], []),
        "curl -O example.invalid/s/a.py": (["a.py"], []),
        "wget example.invalid/s/a.py": (["a.py"], []),
    }


TOOL_OUTPUT_PLANTS = [
    (
        "a tool's own output files not recorded",
        "        for target in files:\n            record(target, run.cwd, None)\n",
        "",
    ),
    (
        "an extraction's directory not recorded",
        "        out.unpacked.extend(new_dirs)\n",
        "",
    ),
    (
        "an extraction leaves an earlier write's text in place (review 6c9f6fd8.1)",
        "                dict.__setitem__(out, key, None)\n",
        "                pass\n",
    ),
    (
        "every extraction drops its whole directory (review c988ab31.1)",
        "        listed = _archive_members(run, cwd, out, seen[:-1]) if dirs else None\n",
        "        listed = None\n",
    ),
    (
        "an archive an earlier run names is listed off the disk (review c988ab31.1)",
        "            if name in word or _unexpanded_word(word):\n",
        "            if False:\n",
    ),
    (
        "a listed member keeps an earlier write's text (review c988ab31.1)",
        "                record(os.path.join(listed[0], member), run.cwd, None)\n",
        "                pass\n",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new"), TOOL_OUTPUT_PLANTS, ids=[p[0] for p in TOOL_OUTPUT_PLANTS]
)
def test_each_tool_output_plant_turns_a_row_63109cf2(bash, tmp_path, label, old, new):
    assert _tool_output_wrong(_planted_shellscan(old, new), bash, tmp_path), (
        "plant %r turns no row: the table cannot see it" % label
    )


# A LONG OPTION'S VALUE IS NOT A URL (review ff2ccadb.1). Each curl row runs under real bash and curl 8.18.0 against `file://` in an empty scratch directory, and the files curl made there must be exactly the files `_tool_outputs` names. At the base the `--user bob`, `--header`, `--referer`, `--cookie` and `--stderr` rows read the option's value as a URL and named an `index.html` download curl never made (and missed the `--stderr` file); `--user=bob`, `--url`, a boolean with a dot in it, `--silent` and `--` are controls that were right there.
# The table below is read without running a tool (wget has no `file://`, and an option curl does not know makes it refuse). At the base the unknown curl option, the wget `--header` value, the unique prefixes `--output-doc` and `--directory-pre`, the ambiguous `--re` and `--save-cookies` each named a download that is not one; `--no-silent`, `--user-agent=ua`, `--quiet`, `--no-recursive` and `--` are controls.
CURL_OPTION_ROWS = [
    "curl -sO --user bob file://{T}/src.py",
    "curl -sO --header X-A:b file://{T}/src.py",
    "curl -sO --referer r file://{T}/src.py",
    "curl -sO --cookie c file://{T}/src.py",
    "curl -s --stderr e.log -O file://{T}/src.py",
    "curl -s --url file://{T}/src.py -O",
    "curl -s --http1.1 -O file://{T}/src.py",
    "curl -O --silent file://{T}/src.py",
    "curl -sO -- file://{T}/src.py",
]
LONG_OPTION_ROWS: dict[str, tuple[list[str], list[str]]] = {
    # The `--long=value` spelling, pinned statically: curl 8.5 (ubuntu-24.04, CI) refuses it as an unknown option, so real curl decides it only where test_a_curl_long_equals_value_matches_real_curl can run.
    "curl -sO --user=bob https://x.invalid/a.py": (["a.py"], []),
    "curl -O --frobnicate bob https://x.invalid/a.py": (["a.py"], []),
    "curl --no-silent -O https://x.invalid/a.py": (["a.py"], []),
    "wget --header X https://x.invalid/a.py": (["a.py"], []),
    "wget --user-agent=ua https://x.invalid/a.py": (["a.py"], []),
    "wget --output-doc a.py https://x.invalid/y": (["a.py"], []),
    "wget --directory-pre d https://x.invalid/s/a.py": (["d/a.py"], []),
    "wget --re x https://x.invalid/a.py": (["a.py"], []),
    "wget --save-cookies c.txt https://x.invalid/a.py": (["c.txt", "a.py"], []),
    "wget --quiet https://x.invalid/a.py": (["a.py"], []),
    "wget --no-recursive https://x.invalid/a.py": (["a.py"], []),
    "wget -- https://x.invalid/a.py": (["a.py"], []),
}


def _long_option_wrong(module, bash_path, tmp_path):
    wrong: list[tuple] = []
    for k, script in enumerate(CURL_OPTION_ROWS):
        tmp = tmp_path / ("c%d" % k)
        (tmp / "o").mkdir(parents=True)
        (tmp / "src.py").write_text("print(1)\n", encoding="utf-8")
        _rc, _out = run_bash(
            bash_path, Fact("L%d" % k, "long option", "cd {T}/o && " + script), tmp
        )
        made = sorted(p.name for p in (tmp / "o").iterdir())
        module._ANALYSIS_CACHE.clear()
        got = sorted(module._tool_outputs(next(iter(module.every_run(_subst(script, tmp)))))[0])
        if got != made:
            wrong.append((script, got, made))
    for cmd, want in LONG_OPTION_ROWS.items():
        module._ANALYSIS_CACHE.clear()
        got = module._tool_outputs(next(iter(module.every_run(cmd))))
        if got != want:
            wrong.append((cmd, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_long_option_value_is_not_a_url_ff2ccadb(bash, tmp_path):
    wrong = _long_option_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))


@functools.cache
def _curl_takes_long_equals() -> bool:
    """Whether this host's curl reads `--user=value`, the exact form the test drives (curl 8.5 on ubuntu-24.04 refuses every `--long=value` spelling as an unknown option)."""
    try:
        done = subprocess.run(
            ["curl", "--user=probe", "--version"], capture_output=True, check=False
        )
    except OSError:
        return False
    return done.returncode == 0


def test_a_curl_long_equals_value_matches_real_curl(bash, tmp_path):
    """Real curl decides `--user=bob`: the value is not a URL, so the one download is src.py."""
    if not _curl_takes_long_equals():
        pytest.skip(
            "CANNOT RUN (1 of 1 requirement(s) missing): a curl that reads --long=value "
            "(this host's curl refuses it as an unknown option); LONG_OPTION_ROWS pins the walk"
        )
    script = "curl -sO --user=bob file://{T}/src.py"
    (tmp_path / "o").mkdir()
    (tmp_path / "src.py").write_text("print(1)\n", encoding="utf-8")
    run_bash(bash, Fact("LE", "long equals", "cd {T}/o && " + script), tmp_path)
    made = sorted(p.name for p in (tmp_path / "o").iterdir())
    shellscan._ANALYSIS_CACHE.clear()
    got = sorted(
        shellscan._tool_outputs(next(iter(shellscan.every_run(_subst(script, tmp_path)))))[0]
    )
    assert made == ["src.py"], "real curl did not download: %r" % made
    assert got == made


LONG_OPTION_PLANTS = [
    (
        "a curl long option's value read as a URL",
        "key, takes = _long_option(key, _CURL_LONG_VALUED, _CURL_LONG_FLAGS, False)",
        "takes = False",
    ),
    (
        "a wget long option's value read as a URL",
        "key, takes = _long_option(key, _WGET_LONG_VALUED, _WGET_LONG_FLAGS, True)",
        "takes = False",
    ),
    ("an unknown long option takes no value", "    return key, None\n", "    return key, False\n"),
    ("a wget prefix left unresolved", "    if prefixes:\n", "    if False:\n"),
]


@pytest.mark.parametrize(
    ("label", "old", "new"), LONG_OPTION_PLANTS, ids=[p[0] for p in LONG_OPTION_PLANTS]
)
def test_each_long_option_plant_turns_a_row_ff2ccadb(bash, tmp_path, label, old, new):
    assert _long_option_wrong(_planted_shellscan(old, new), bash, tmp_path), (
        "plant %r turns no row: the table cannot see it" % label
    )


def test_a_listable_zip_replaces_only_its_members_c988ab31(tmp_path):
    """Review c988ab31.1 for `unzip`, which this machine does not carry, so the walk alone is read: w.zip holds only a.py, so an echoed b.py beside it keeps its text and an echoed a.py is replaced; a zip the walk cannot list (missing) still drops the directory."""
    with zipfile.ZipFile(tmp_path / "w.zip", "w") as archive:
        archive.writestr("a.py", "print(4)\n")
    cwd = str(tmp_path)
    rows = {
        "echo 'print(1)' > b.py && unzip -q w.zip && python3 b.py": "file",
        "echo 'print(1)' > a.py && unzip -o w.zip && python3 a.py": "unjudgeable",
        "echo 'print(1)' > b.py && unzip -q gone.zip && python3 b.py": "unjudgeable",
        "echo 'print(1)' > d/b.py && unzip w.zip -d d && python3 d/b.py": "file",
        "echo 'print(1)' > d/a.py && unzip w.zip -d d && python3 d/a.py": "unjudgeable",
    }
    got = {}
    for cmd in rows:
        shellscan._ANALYSIS_CACHE.clear()
        run = [r for r in shellscan.every_run(cmd) if r.name == "python3"][-1]
        got[cmd] = shellscan.interpreter_program(run, cmd, cwd)[1]
    shellscan._ANALYSIS_CACHE.clear()
    assert got == rows


def test_a_zip_past_the_unpacked_cap_drops_the_directory_57688c33(tmp_path):
    """Review 57688c33.3: a zip under the file-size cap whose members unpack past _ARCHIVE_UNPACKED_MAX is not listed, so the whole directory drops as for tar."""
    with zipfile.ZipFile(tmp_path / "big.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("a.py", "print(4)\n")
        archive.writestr("pad.bin", b"\0" * (shellscan._ARCHIVE_UNPACKED_MAX + 1))
    assert (tmp_path / "big.zip").stat().st_size < 4 << 20
    cmd = "echo 'print(1)' > b.py && unzip -q big.zip && python3 b.py"
    shellscan._ANALYSIS_CACHE.clear()
    run = [r for r in shellscan.every_run(cmd) if r.name == "python3"][-1]
    kind = shellscan.interpreter_program(run, cmd, str(tmp_path))[1]
    shellscan._ANALYSIS_CACHE.clear()
    assert kind == "unjudgeable"


def test_a_scheme_url_after_an_unknown_long_option_is_a_download_57688c33():
    """Reviews 57688c33.1, .2: an option in neither set does not swallow a scheme URL that follows it; a bare word after it stays a possible value."""
    rows: dict[str, tuple[list[str], list[str]]] = {
        "curl -O --frobnicate https://x.invalid/a.py": (["a.py"], []),
        "wget --unknown-flag https://x.invalid/a.py": (["a.py"], []),
        "curl -O --frobnicate bob https://x.invalid/a.py": (["a.py"], []),
    }
    got = {}
    for cmd in rows:
        shellscan._ANALYSIS_CACHE.clear()
        got[cmd] = shellscan._tool_outputs(next(iter(shellscan.every_run(cmd))))
    shellscan._ANALYSIS_CACHE.clear()
    assert got == rows


# THE PLANTS for #4deea064, #3ff3bb16 and review 2e50ca28.1/.3. Each puts one piece back the way it was at d73b26844 (or the way the review feared) in a copy of shellscan loaded from source and must turn at least one row of the tables above.
EXPANDED_WRITE_PLANTS = [
    (
        "a redirect target kept as typed",
        "    if value is None or _UNRESOLVED in value:\n        return typed\n    return value\n",
        "    return typed\n",
    ),
    (
        "a split redirect value claimed",
        "    if value is None or _UNRESOLVED in value:\n        return typed\n",
        "    if value is None:\n        return typed\n",
    ),
    (
        "a group redirect read after its body",
        "self.redirs(stage[2], state, lexer, outer)",
        "self.redirs(stage[2], state, lexer)",
    ),
    (
        "a bare assignment's redirect read before it",
        "                self.analysis.xwrites[at] = (op, _redirect_value(target, shell))\n",
        "                pass\n",
    ),
    (
        "in place read as typed only",
        "    if xargv is not None and list(xargv) != argv:\n        readings.append",
        "    if False:\n        readings.append",
    ),
    (
        "a copy writes unknown content",
        "text = _copied_text(sources[0], run.cwd, cwd, written) if plain else None",
        "text = None",
    ),
    (
        "a copy into a directory recorded as the directory",
        '        directory = True if into or dest.endswith("/") else None\n        if directory is None:\n            directory = _directory_answer(_script_path(dest, run.cwd, cwd), earlier, cwd)\n',
        "        directory = False\n",
    ),
    (
        "a copy's directory read off the disk (0600a464.1)",
        "            directory = _directory_answer(_script_path(dest, run.cwd, cwd), earlier, cwd)\n",
        "            directory = os.path.isdir(_script_path(dest, run.cwd, cwd))\n",
    ),
    (
        "any directory-touching tool with an unexpandable word counts (6238f04a.1)",
        "        if not _may_touch_directories(run):\n",
        "        if _base(run.name) not in _DIR_TOUCHERS:\n",
    ),
    (
        "a git status counted as making directories (6238f04a.1)",
        "        return run.git_sub not in _GIT_TREE_KEEPERS\n",
        "        return True\n",
    ),
    (
        "via sliced from the typed words (2e50ca28.1)",
        "        prefix_words = words\n",
        "        prefix_words = [t for t in stage[1] if isinstance(t, _Word)]\n",
    ),
    (
        "every field takes the typed span (2e50ca28.3)",
        "_Word(head.start if k == 0 else head.end, head.end,",
        "_Word(head.start, head.end,",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new"), EXPANDED_WRITE_PLANTS, ids=[p[0] for p in EXPANDED_WRITE_PLANTS]
)
def test_each_expanded_write_plant_turns_a_row(bash, tmp_path, label, old, new):
    module = _planted_shellscan(old, new)
    for part in ("r", "i", "c"):
        (tmp_path / part).mkdir()
    turned = (
        _redirect_wrong(module, bash, tmp_path / "r")
        + _in_place_wrong(module, bash, tmp_path / "i")
        + _copy_wrong(module, bash, tmp_path / "c")
        + _launched_wrong(module)
    )
    assert turned, "plant %r turns no row: the tables cannot see it" % label


# A VARIABLE ASSIGNED ANY OTHER WAY THAN `NAME=value` IS NOT THE OLD VALUE (#97ed76a7). Each row runs under real bash in a fresh scratch directory and names the files bash creates there; `write_targets` must then name each of them, or the typed word alone where the walk cannot know the value, and never a file bash did not write. The fourth column is what 2672ed8f6 answered, measured: a stale value for most rows (`other.md` after a `for`, a `read` or a `printf -v` that had assigned `src`, `.md` after a `${D:=src}`), and `a.in` for the body of a piped loop whose `read` had assigned `src`.
ASSIGN_ROWS = [
    # (script, the files bash writes, write_targets, what 2672ed8f6 answered where it differs)
    (
        "D=other; for D in src; do echo x > $D.md; done",
        ["src.md"],
        ["$D.md"],
        ["$D.md", "other.md"],
    ),
    ("D=other; read D <<< src; echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", "other.md"]),
    ("D=other; printf -v D src; echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", "other.md"]),
    ("D=other; mapfile -t D <<< src; echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", "other.md"]),
    ("O=other; getopts a O -a; echo x > $O.md", ["a.md"], ["$O.md"], ["$O.md", "other.md"]),
    ("D=1; let D=2; echo x > $D.md", ["2.md"], ["$D.md"], ["$D.md", "1.md"]),
    ("D=1; (( D = 2 )); echo x > $D.md", ["2.md"], ["$D.md"], ["$D.md", "1.md"]),
    ("D=1; : $((D=2)); echo x > $D.md", ["2.md"], ["$D.md"], ["$D.md", "1.md"]),
    ("unset D; : ${D:=src}; echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", ".md"]),
    # A builtin's heredoc is expanded in the shell itself (an external command's in its child, where the assignment stays).
    ("unset D; : <<EOF\n${D:=src}\nEOF\necho x > $D.md", ["src.md"], ["$D.md"], ["$D.md", ".md"]),
    ("D=other; f() { D=src; }; f; echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", "src.md"]),
    ("D=other; f() { echo x > $D.md; }; D=src; f", ["src.md"], ["$D.md"], ["$D.md", "other.md"]),
    (
        "D=other; declare -n R=D; R=src; echo x > $D.md",
        ["src.md"],
        ["$D.md"],
        ["$D.md", "other.md"],
    ),
    ("D=(src b); echo x > $D.md", ["src.md"], ["$D.md"], ["$D.md", ".md"]),
    (
        "echo D=src > e.sh; D=other; . ./e.sh; echo x > $D.md",
        ["e.sh", "src.md"],
        ["e.sh", "$D.md"],
        ["e.sh", "$D.md", "other.md"],
    ),
    # A loop body is walked again with what its first pass assigned unknown: the second iteration writes `b.l`.
    ("D=a; for i in 1 2; do echo x > $D.l; D=b; done", ["a.l", "b.l"], ["$D.l"], ["$D.l", "a.l"]),
    # A compound command's redirect is expanded before its body runs.
    ("D=a; for x in 1; do D=b; done > $D.out", ["a.out"], ["$D.out", "a.out"], ["$D.out", "b.out"]),
    ("D=a; if true; then D=b; fi > $D.out", ["a.out"], ["$D.out", "a.out"], ["$D.out", "b.out"]),
    # A loop in a pipeline runs in a subshell: its condition's `read` reaches its body, and nothing reaches the line after it.
    (
        "D=a; echo src | while read D; do echo x > $D.in; done; echo x > $D.md",
        ["a.md", "src.in"],
        ["$D.in", "$D.md", "a.md"],
        ["$D.in", "a.in", "$D.md", "a.md"],
    ),
    # Controls: an expansion or a builtin that assigns nothing keeps the value.
    ("D=1; : ${D:-2} $((D+1)); echo x > $D.md", ["1.md"], ["$D.md", "1.md"], None),
    ("D=1; read -r E <<< x; printf -v F y; echo x > $D.md", ["1.md"], ["$D.md", "1.md"], None),
    ("D=1; f() { E=2; }; f; echo x > $D.md", ["1.md"], ["$D.md", "1.md"], None),
    # Review 6238f04a.2: only a parameter expansion's subscript and substring offset and length are arithmetic. The first two were `["$a.md"]` at 8ef785864, `a=2` in a default or a trimmed pattern read as an assignment; the last two still assign.
    ("a=1; : ${D:-a=2}; echo x > $a.md", ["1.md"], ["$a.md", "1.md"], ["$a.md"]),
    ("a=1; : ${D#a=2}; echo x > $a.md", ["1.md"], ["$a.md", "1.md"], ["$a.md"]),
    ("D=xyz; a=1; : ${D:a=2}; echo x > $a.md", ["2.md"], ["$a.md"], None),
    ("a=1; R=(p q); : ${R[a=0]}; echo x > $a.md", ["0.md"], ["$a.md"], None),
]


def _assign_wrong(module, bash_path, tmp_path):
    wrong = []
    for k, (script, written, want, _was) in enumerate(ASSIGN_ROWS):
        tmp = tmp_path / ("a%d" % k)
        tmp.mkdir()
        run_bash(bash_path, Fact("A%d" % k, "assignment", script), tmp)
        assert _created(tmp) == written, "bash wrote %r for %s" % (_created(tmp), script)
        module._ANALYSIS_CACHE.clear()
        try:
            got = module.write_targets(script)
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != want:
            wrong.append((script, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_variable_assigned_without_name_equals_value_97ed76a7(bash, tmp_path):
    wrong = _assign_wrong(shellscan, bash, tmp_path)
    assert not wrong, "\n".join(map(repr, wrong))
    # Every concrete target the walk names is one bash wrote.
    for script, written, want, _was in ASSIGN_ROWS:
        assert all("$" in t or t in written for t in want), script


# A COMPOUND COMMAND'S REDIRECT IS ON THE RUNS INSIDE IT (#97ed76a7). At 2672ed8f6 `{ ...; } > f`, `( ... ) > f`, `done > f`, `fi > f` and `esac > f` were in `write_targets` and on no run, so a reader of `run.writes`/`redirect_targets` (earlier_mutators, `_written_scripts`, wl_roster.bash_write_paths, every guard walking runs) never saw them. A run that changed directory first is left out: bash opened the file where the group started.
COMPOUND_ROWS = [
    ("{ echo x; } > g.md", {"echo": ["g.md"]}),
    ("( echo x ) > g.md", {"echo": ["g.md"]}),
    ("while false; do echo x; done > w.md", {"false": ["w.md"], "echo": ["w.md"]}),
    ("if true; then echo x; fi > i.md", {"true": ["i.md"], "echo": ["i.md"]}),
    ("case a in a) echo x;; esac > c.md", {"echo": ["c.md"]}),
    ("D=g; { echo x; } > $D.md", {"echo": ["$D.md", "g.md"]}),
    ("mkdir -p s; { cd s; echo x; } > g.md", {"mkdir": [], "cd": ["g.md"], "echo": []}),
    ("{ echo x; } 2>&1", {"echo": []}),
]


def _compound_wrong(module):
    wrong = []
    for script, want in COMPOUND_ROWS:
        module._ANALYSIS_CACHE.clear()
        got: object
        try:
            got = {r.name: module.redirect_targets(r) for r in module.every_run(script)}
        except _PLANT_CRASHES as exc:
            got = "<raised %s>" % type(exc).__name__
        if got != want:
            wrong.append((script, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_a_compound_redirect_is_on_the_runs_inside_it_97ed76a7():
    wrong = _compound_wrong(shellscan)
    assert not wrong, "\n".join(map(repr, wrong))
    # `earlier_mutators` reads it: a message file a group writes before the commit changes what the commit reads.
    assert [
        m.target
        for m in shellscan.earlier_mutators("{ printf x; } > m; git commit -F m", "git commit")
    ] == ["m"]


def test_assignments_before_reads_the_walk_97ed76a7():
    reads = shellscan.assignments_before
    assert reads("P=a; git commit -- $P", "git commit") == {"P": "a"}
    assert reads("P=a; for P in b; do :; done; git commit -- $P", "git commit") == {}
    assert reads("P=a; read P <<< b; git commit -- $P", "git commit") == {}
    assert reads('P="$(ls x/*.json)"; git commit -- $P', "git commit") == {"P": "$(ls x/*.json)"}
    assert reads("P=a; if true; then P=b; fi; git commit -- $P", "git commit") == {"P": "b"}


def test_function_bodies_and_loops_are_still_walked_97ed76a7():
    # `function f { ...; }` was read as words of `function f`, so the commands in its body were never walked.
    shellscan._ANALYSIS_CACHE.clear()
    assert [r.name for r in shellscan.every_run("function f { rm x; }")] == ["rm"]
    # An array's elements are not a command, and a substitution inside them still runs.
    assert [r.name for r in shellscan.every_run("D=(a b)")] == []
    assert [r.name for r in shellscan.every_run("D=( $(rm y) )")] == ["rm"]
    # A loop walked twice still reports each of its runs once.
    assert [r.name for r in shellscan.every_run("D=a; for i in 1 2; do rm $D; D=b; done")] == ["rm"]


# THE PLANTS for #97ed76a7. Each puts one piece back the way it was at 2672ed8f6 in a copy of shellscan and must turn at least one row above.
ASSIGN_PLANTS = [
    (
        "a parameter expansion's whole body read as arithmetic (6238f04a.2)",
        "                names.update(_arith_names(_param_arith_text(p.raw)))\n",
        '                names.update(_arith_names(p.raw[2:-1]) if p.raw.startswith("${") else ())\n',
    ),
    (
        "a parameter expansion's subscript not read as arithmetic (6238f04a.2)",
        '    if rest.startswith("["):\n',
        "    if False:\n",
    ),
    (
        "a builtin's assignment ignored",
        "        self.effects = _builtin_assigns(words, before)\n",
        "        self.effects = (set(), False, set())\n",
    ),
    (
        "an expansion's assignment ignored",
        "        state[1] = _clobber(state[1], _expansion_assigns(stage[1]))\n",
        "        pass\n",
    ),
    (
        "a loop body walked once",
        '                    if frame["family"] == "loop" and frame["item"] not in rewalked:\n',
        "                    if False:\n",
    ),
    (
        "a function body read under the definition's state",
        "                function = (function[0], idx, state[1])\n                state[1] = _opaque(state[1])\n",
        "                function = (function[0], idx, state[1])\n",
    ),
    (
        "a closer's redirect read after the body",
        '                            _redirect_value(word, frame["origin"][1]),\n',
        "                            analysis.xwrites[at][1],\n",
    ),
    (
        "a subshell loop's state kept",
        '                        state[:] = frame["origin"]\n',
        "                        pass\n",
    ),
    (
        "an array assignment read as a subshell",
        '                if head.endswith("=") and _ASSIGNMENT.match(head):\n',
        "                if False:\n",
    ),
    (
        "an assignment through a nameref ignored",
        "        if watched and any(shell.get(n) != start.get(n) for n in watched - set(watch)):\n",
        "        if False:\n",
    ),
    (
        "a compound redirect on no run",
        "        for run in self.analysis.runs[first:end]:\n            if run.cwd == cwd:\n",
        "        for run in ():\n            if run.cwd == cwd:\n",
    ),
    (
        "a compound redirect on a run that changed directory",
        "        for run in self.analysis.runs[first:end]:\n            if run.cwd == cwd:\n",
        "        for run in self.analysis.runs[first:end]:\n            if True:\n",
    ),
]


@pytest.mark.parametrize(("label", "old", "new"), ASSIGN_PLANTS, ids=[p[0] for p in ASSIGN_PLANTS])
def test_each_assignment_plant_turns_a_row_97ed76a7(bash, tmp_path, label, old, new):
    module = _planted_shellscan(old, new)
    turned = _assign_wrong(module, bash, tmp_path) + _compound_wrong(module)
    assert turned, "plant %r turns no row: the tables cannot see it" % label


def test_git_runs_that_can_run_programs_touch_directories_6c9f6fd8():
    """Review 6c9f6fd8.4: commit and push run hooks, and a run pointing core.fsmonitor or core.hooksPath at a program lets later index reads run it; a plain status still keeps the tree."""
    shellscan._ANALYSIS_CACHE.clear()

    def touches(cmd):
        return shellscan._may_touch_directories(next(iter(shellscan.every_run(cmd))))

    assert touches("git commit -m x")
    assert touches("git push origin main")
    assert touches("git config core.fsmonitor ./mon")
    assert touches("git -c core.hooksPath=h status")
    assert not touches("git status")
    assert not touches('git -C "$X" log')


# A RUN TOUCHES ONLY WHEN IT SETS A PROGRAM KEY (review ff2ccadb.2). Every False row but `--list --show-origin` was True at the base, a word naming the key enough; that row and every True row (a run that points a key at a value that can name a program) are controls the base already answered.
GIT_PROGRAM_ROWS = {
    "git -c core.fsmonitor=false status": False,
    "git -c core.hooksPath= status": False,
    "git -c core.fsmonitor=off status": False,
    "git config --get core.hooksPath": False,
    "git config --unset core.fsmonitor": False,
    "git config --get core.hooksPath h": False,
    "git config --unset core.fsmonitor ./mon": False,
    "git config --local --unset-all core.hooksPath": False,
    "git config get core.hooksPath": False,
    "git config core.hooksPath": False,
    "git config core.fsmonitor 0": False,
    "git config --list --show-origin": False,
    "git -c core.fsmonitor=./mon status": True,
    "git -c core.hooksPath status": True,
    "git config core.fsmonitor ./mon": True,
    "git config --global core.hooksPath /x/hooks": True,
    "git config set core.hooksPath h": True,
    "git config --file f core.hooksPath h": True,
    'git config core.hooksPath "$H"': True,
    "git --config-env=core.hooksPath=H status": True,
}


def _git_program_wrong(module):
    wrong = []
    for cmd, want in GIT_PROGRAM_ROWS.items():
        module._ANALYSIS_CACHE.clear()
        got = module._may_touch_directories(next(iter(module.every_run(cmd))))
        if got != want:
            wrong.append((cmd, got, want))
    module._ANALYSIS_CACHE.clear()
    return wrong


def test_only_a_program_key_set_touches_directories_ff2ccadb():
    wrong = _git_program_wrong(shellscan)
    assert not wrong, "\n".join(map(repr, wrong))


GIT_PROGRAM_PLANTS = [
    (
        "any word naming a program key counts",
        "        if _git_sets_program_key(list(words)):\n",
        '        if any(re.search(r"(?i)\\bcore\\.(?:fsmonitor|hookspath)\\b", w) for w in words):\n',
    ),
    (
        "an off value counts",
        "or value.strip().lower() not in _GIT_OFF_VALUES",
        "or True",
    ),
    (
        "a reading git config counts",
        '        if word in _GIT_CONFIG_READERS and (word.startswith("-") or not operands):\n            return False\n',
        "",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new"), GIT_PROGRAM_PLANTS, ids=[p[0] for p in GIT_PROGRAM_PLANTS]
)
def test_each_git_program_plant_turns_a_row_ff2ccadb(label, old, new):
    assert _git_program_wrong(_planted_shellscan(old, new)), (
        "plant %r turns no row: the table cannot see it" % label
    )
