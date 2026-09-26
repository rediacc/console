<!-- A0 output (opus Plan agent, 2026-09-24) for PLAN-retire-bash-oracles.md task A0; saved verbatim by the lead. The fail-open bugs in section 1 are Rule T items for task A4. -->

# A0 design: `test_bash_semantics.py`, the kept real-bash facts, and the live bugs they expose
Depends-On: no-dep -- appendix of PLAN-retire-bash-oracles.md; carries no work of its own

Every probe below was checked against `/usr/bin/bash` 5.3.9 in this session, except where a row says otherwise. Nothing in the tree was modified.

## 1. Live bugs: things the Python assumes that bash does not do (listed first)

Each shape ran through both the Python scanner and the oracle `command-scan.sh`, and on the 19 shapes tried the two gave the same answer every time. So these bugs were copied from bash, not introduced by the port. A differential against the oracle could never have found them. They belong in A4 as category-(i) Rule T fixes.

**Fail-open (the guard lets the command through):**

1. **An assignment whose value is `$(...)` or a backtick gets eaten.** In `x=$(cmd)`, the env-prefix stripper's value class swallows `$(cmd ` (`.claude/rediacc_hooks/shellscan.py:195-203`, `:206-220`).
   - Bash runs `cmd`.
   - Measured: `block_git_force_push` gives rc 2 on `git push --force origin main`, but rc 0 on `x=$(git push --force origin main)`.
   - Reach: 33 guard modules call `scan_target` or `hook_init`.
2. **`$(...)` and backticks inside double quotes are executed.** `_sed_strip_quoted_spans` deletes the whole span (`.claude/rediacc_hooks/shellscan.py:305-306`), so `git commit -m "$(gh pr view 1)"` scans as `git commit -m `.
3. **The body of a heredoc with an unquoted delimiter expands substitutions.** `cat <<EOF\n$(cmd)\nEOF` runs `cmd`. It is dropped by `_strip_heredocs` (`.claude/rediacc_hooks/shellscan.py:157-177`) and by `_strip_cat_heredocs` (`.claude/rediacc_hooks/guards/block_git_amend.py:62-95`).
4. **A heredoc or here-string feeding an interpreter is executed.** Examples: `bash <<'EOF'`, `bash <<< '...'`.
   - The docstring at `.claude/rediacc_hooks/shellscan.py:9-10` says a heredoc body is "never executed". That is false for this case.
   - `.claude/rediacc_hooks/guards/block_git_amend.py:89` already models it correctly (the writer must be `cat` or `tee`; see its edge case "an INTERPRETER heredoc still executes"). `shellscan` does not.
5. **Things that look like a heredoc but are not swallow every later line.** The marker regex at `.claude/rediacc_hooks/shellscan.py:169` also fires on:
   - a here-string `<<<x`;
   - `"<<EOF"` inside quotes;
   - `# <<EOF` in a comment.
   
   In all three, bash runs the following lines.
6. **The quote-strip order is wrong for `'` inside `"..."` and for `\"`.** On `echo "it's"; cmd; echo 'y'` and `echo "p \" q"; cmd; echo "r"`, bash runs `cmd` but the scan loses it (`.claude/rediacc_hooks/shellscan.py:297-308`; the ordering claim is at `:300`).
7. **Quote removal on the command word.** `"gh"`, `g"h"`, `g\h`, `\gh` and `$'gh'` all run `gh`, but the anchors look for a literal `gh` or `git` (`.claude/rediacc_hooks/shellscan.py:323`; copied into guard regexes such as `.claude/rediacc_hooks/guards/block_git_force_push.py:28`). Measured: `"git" push --force origin main` gives rc 0.
8. **A backslash-newline joins two lines into one command.** The anchors run per record (`.claude/rediacc_hooks/shellscan.py:335`), so `gh pr \`+newline+`merge` is never seen as one command.
9. **The list of command positions is incomplete.** The anchor `(^|[;&|(]|\$\(|`)` at `.claude/rediacc_hooks/shellscan.py:323` is copied into `.claude/rediacc_hooks/guards/block_worktree_add.py:30`, `.claude/rediacc_hooks/guards/block_blanket_git_add.py:42` and `.claude/rediacc_hooks/guards/block_git_force_push.py:28`. It misses:
   - `{ cmd; }`, `! cmd`, `then`/`do`/`else`, `time`, `command`, `exec`, `coproc`;
   - a redirect in front of the command: `>/dev/null cmd`, `2>&1 cmd`.
   
   Measured: `{ git push --force …; }` and `>/dev/null git push --force …` both give rc 0.
10. **The `-c` selector test is too narrow.** Bash runs the payload for `bash -ce 'P'`, `bash -c -e 'P'`, `bash -c -- 'P'` and `bash '-c' 'P'`. The Python accepts only a bundle ending in `c` and takes the very next token as the payload (`.claude/rediacc_hooks/shellscan.py:149-150`, with the claim at `:121-122`).
11. **An earlier `eval` or `-c` hides a later wrapper.**
    - `echo eval && sh -c 'P'`: the Python returns at the first `eval` token (`:137-140`).
    - `sh -c 'true'; sh -c 'P'`: the first payload absorbs the rest of the line, so the second `P` is not at a command position (`:150-151`).
    - Bash runs `P` in both.
12. **Where a `cd` or `-C` applies.** `target_root` takes the last hint anywhere on the line (`.claude/rediacc_hooks/shellscan.py:429-430`), and `target_repo` does the same (`:377`). Measured: all of these resolve to `private/renet`:
    - `(cd private/renet && git fetch); git status`
    - `cd private/renet | true; git status`
    - `git -C private/renet fetch; git status`
    
    But bash's `(cd /tmp); pwd` and `cd /tmp | true; pwd` both stay in `/`. The guard then judges the wrong working tree, which can fail open in `block_unverified_push`.
13. **`block_ssh_file_write` has the redirect locality backwards** (`.claude/rediacc_hooks/guards/block_ssh_file_write.py:29` plus the quote strip).
    - `ssh h cat f > /etc/x` writes a LOCAL file, and the guard blocks it.
    - `ssh h 'cat > /etc/x' < f` and `ssh h "echo hi > /etc/x"` are the real remote writes, and the guard allows both (rc 0, measured).
14. **Two redirect forms are missed** (`.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:45,52,67,141`).
    - `>|` truncates even under noclobber, but `[^|…]` in the target classes excludes it, so the guard misses it.
    - An unquoted `x->f.sh` IS a redirect in bash (`echo x->/dev/null` printed nothing). `NOT_ARROW` gives this up on purpose. The lead should decide whether that stays a documented policy choice or becomes a bug.
15. **PATH lookup does not match `command -v`.** `_command_v` (`.claude/rediacc_hooks/guards/block_host_toolchain_run.py:217-236`; the claim is at `:27`) returns the first PATH entry that exists, including directories and non-executable files. Bash returns the first executable, and falls back to a non-executable file only when no executable exists. Measured with `PATH=/etc:/usr/bin`:

    | Name | bash `command -v` | Python |
    |---|---|---|
    | `passwd` | `/usr/bin/passwd` | `/etc/passwd`, then `_have_executable` = False |
    | `ssh` | `/usr/bin/ssh` | `/etc/ssh` (a directory), then `_have_executable` = True |
    | `hosts` | `/etc/hosts` (rc 0) | `hookio.have("hosts")` = False |

    `hookio.have` (`.claude/rediacc_hooks/hookio.py:417-425`) calls itself `command -v` but is not.

**Safe direction (the scanner looks at more than bash runs, so it over-blocks):**

- **S1.** The heredoc terminator test `^[ \t]*M[ \t]*$` (`.claude/rediacc_hooks/shellscan.py:165`) closes plain `<<` on a tab-indented, space-indented or trailing-blank terminator. Bash does not close on any of those.
- **S2.** The marker stops at `-` (`:169`). For `<<END-X` it closes at a line reading `END`; bash waits for `END-X`.
- **S3.** `SPACE` (`.claude/rediacc_hooks/shellscan.py:70`) treats `\r`, `\v` and `\f` as separators. Bash splits words only on space, tab and newline: `cmd X\r` passes the argument `X\r`.

**Bash-version-sensitive diagnostics:** no hook Python reproduces or parses bash's diagnostic text. The only place that does is `.ci/rediacc_ci/core/bash_dialect.py` (commits `ce37d8515`, `04da2b7f7`, `a964e09c5`), which is Phase B scope and already asks bash at runtime. So the new suite has no diagnostic-text rows, and it must never assert on stderr. Two examples of why:
- An unterminated heredoc prints `warning: here-document … (wanted `EOF')` on stderr, and that wording is version-sensitive.
- Syntax-error exit codes were not even stable between shapes: `bash -n -c` gave 2 for an unbalanced quote and 127 for an unbalanced `$(`.

## 2. Design: `.claude/rediacc_hooks/tests/test_bash_semantics.py`

- **Which bash it runs.** Resolve the real interpreter once with `bash --norc --noprofile -c 'printf %s "$BASH"'` and call it by absolute path. On this host `bash` on PATH is a `bashcov-sup` wrapper that re-execs the interpreter as a child (`.claude/rediacc_hooks/guards/block_edit_of_running_script.py:90`), and that pollutes the process table for the pgrep rows. If no bash is found, the suite fails rather than skips, because running bash is its whole purpose.
- **Environment.** Every run uses `--norc --noprofile` and `env = {PATH: <stubdir>:/usr/bin:/bin, LC_ALL: C, HOME: tmp}`. `BASH_ENV` and `ENV` are removed explicitly; otherwise `.claude/hooks/profile/bash_env.sh` would be sourced into every non-interactive bash.
- **Stubs.** In `tmp_path/bin`, two `#!/bin/sh` scripts so that `sh -c`, dash and `eval` children can see them:
  - `zzrun` prints `RAN:` followed by its arguments joined with `|`;
  - `zzargv` prints `<a><b>…`.
  
  Never use the real `gh` or `git` names. That avoids side effects, and it stops the live pre-bash guards from refusing a hand-run probe; this session was refused on its first attempt that used `gh pr merge --admin`.
- **pgrep rows.** Build the token at runtime (a uuid) so that no ancestor's argv contains it; this session's first attempt was polluted that way. Assert only that the self-match happens (rc 0) and that the bracketed form does not match (rc 1). Never assert a count.
- **Case record.** `Fact(id, fact, script, stdin=None, expect_stdout=None, expect_rc=None, mode="c"|"n"|"file", relies_on=[("shellscan.py","_strip_heredocs"),…], lines=".claude/rediacc_hooks/shellscan.py:157-177", source="corpus r39 …", status="honoured"|"contradicted:<A4 item>"|"safe-divergence")`.
- **Tests:**
  - `test_bash_fact[id]` runs bash and compares stdout and/or rc. The failure message is: `bash <BASH_VERSION> no longer <fact>; re-examine <relies_on> (<lines>), from <source>`.
  - `test_reliance_resolves[id]` checks by AST that each named function or constant still exists in the named file. The line numbers are documentation; the name is what gets checked.
  - `test_scanner_agrees[id]` is optional but recommended. It runs in-process with no twin: for example, `gh_pr_at_command_pos(_command_substitution(scan_target(cmd)), verb)` must equal what bash did. For `contradicted:*` rows it is `xfail(strict=True, reason=<A4 item>)`, so an A4 fix turns it into XPASS, which then forces the marker to be removed.
  - `test_the_suite_can_fail` feeds one row a wrong expectation and asserts the comparison fires.
- **Cost.** About 55 bash runs, well under 5 s. It needs no `XDIST_GROUP` and no oracle path.
- **Knock-on change.** Check the MIN_TESTS floor in `.ci/rediacc_ci/check_pytest.py`, because the oracle deletion lowers the test count.

## 3. Case list

Stub names are `zzrun` (Z) and `zzargv` (A). `$T` is `tmp_path`. `[L#]` points to the live bug above and is marked `contradicted`; `[S#]` is a safe-direction divergence. "Rows" means edge-case rows.

**Shell wrappers and eval**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| W1 | `sh -c P` runs P | `sh -c 'zzrun X'` | `RAN:X` | `.claude/rediacc_hooks/shellscan.py:129,149` `_wrapper_payload` | corpus r39 bare; guard "wrapper payload" rows (11 guards) |
| W2 | a short-flag bundle ending in c | `bash -ec 'zzrun X'` | `RAN:X` | `:149` | r39 bundled (`-lc`; using `-ec` avoids the login profile) |
| W3 | separate flags before -c | `bash -eu -c 'zzrun X'` | `RAN:X` | `:147-151` | r40 separate |
| W4 | value-taking option | `bash -o pipefail -c 'zzrun X'` | `RAN:X` | `:147-151` | r40 value-taking |
| W5 | long options | `bash --posix -c 'zzrun X'`; `bash --norc --noprofile -c 'zzrun Y'` | `RAN:X` then `RAN:Y` | `:147-151` | r40 long, --norc |
| W6 | path-qualified or quoted shell name | `"$BASH" -c 'zzrun X'; '/bin/sh' -c 'zzrun Y'` | `RAN:X`, `RAN:Y` | `:142-146` | r42 abs/usr-bin, r44 x3 |
| W7 | `env` runs the shell | `env sh -c 'zzrun X'` | `RAN:X` | `:136-146` | r42 env bash |
| W8 | `c` anywhere in a bundle selects -c | `bash -ce 'zzrun X'` | `RAN:X` | `:149` [L10] | new |
| W9 | options may follow -c | `bash -c -e 'zzrun X'; bash -c -- 'zzrun Y'` | `RAN:X`, `RAN:Y` | `:150` [L10] | new |
| W10 | quote removal applies to `-c` | `bash '-c' 'zzrun X'` | `RAN:X` | `:149` [L10] | new |
| W11 | eval runs its argument | `eval 'zzrun X'` | `RAN:X` | `:137-140` | eval payload; force_push, push_to_protected, ssh_docker eval rows |
| W12 | eval re-parses after expansion | `Y=--f; eval "zzrun X $Y"` | `RAN:X\|--f` | `:137` | eval with assignment |
| W13 | a shell with no -c, then a wrapper | `sh /dev/null; sh -c 'zzrun X'` | `RAN:X` | `:152` fall-through | shell with no -c |
| W14 | an `eval` word as an argument does not stop a later wrapper | `echo eval && sh -c 'zzrun X'` | `eval`, `RAN:X` | `:137-140` [L11] | new |
| W15 | two wrappers on one line | `sh -c true; sh -c 'zzrun X'` | `RAN:X` | `:150-151` [L11] | new |
| W16 | a leading blank changes nothing | ` sh -c 'zzrun X'` | `RAN:X` | `:134` (empty first token) | leading space before wrapper |

**Env prefixes**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| E1 | a prefix is not the command | `FOO=bar zzrun X; true; FOO=b zzrun Y; true \| FOO=c zzrun Z; (FOO=d zzrun W)` | 4 RAN lines | `:195-203,206` | env prefix before git / after ; / after pipe / after paren |
| E2 | several prefixes | `A=1 B=2 zzrun X` | `RAN:X` | `:215-218` loop | two env prefixes |
| E3 | a prefix inside a substitution | ``x=$(FOO=b zzrun X); y=`FOO=b zzrun Y`; printf '%s\n' "$x" "$y"`` | `RAN:X`, `RAN:Y` | `:196` | inside substitution / backticks |
| E4 | the value may contain `=` | `FOO=a=b sh -c 'printf "%s\n" "$FOO"'` | `a=b` | `:198` | value has an equals |
| E5 | a bare assignment runs nothing | `FOO=bar` | stdout empty, rc 0 | `:206` | assignment with no command |
| E6 | a prefix reaches the child's environment | `FOO=bar sh -c 'printf "%s\n" "$FOO"'` | `bar` | `.claude/rediacc_hooks/shellscan.py:193`; `.claude/rediacc_hooks/guards/block_unlinked_commit_author.py:199` | env-prefix comment |
| E7 | `x=$(cmd)` runs cmd | ``x=$(zzrun X); y=`zzrun Y`; printf '%s\n' "$x" "$y"`` | `RAN:X`, `RAN:Y` | `:198-200` [L1] | new |

**Heredocs**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| H1 | a quoted-delimiter body is data | `cat <<'EOF'\nzzrun X\nEOF` (also `<<EOF`, `<<"EOF"` with a plain body) | `zzrun X` | `:157-177`; `.claude/rediacc_hooks/guards/block_git_amend.py:62` | heredoc x3; adhoc_sanctioned, git_amend, nonstandard_branch, ssh_docker, self_matching_pgrep heredoc rows |
| H2 | an unquoted-delimiter body expands | `cat <<EOF\n$(zzrun X)\nEOF` | `RAN:X` | `:157-177` [L3] | new |
| H3 | `<<-` closes on a tab-indented terminator | `cat <<-EOF\n\tb\n\tEOF\nzzrun X` | `b`, `RAN:X` | `:165`; `.claude/rediacc_hooks/guards/block_git_amend.py:83-84` | `<<-` tab row; git_amend tab row |
| H4 | plain `<<` does not tab-strip | `cat <<EOF\n\tEOF\nzzrun X\nEOF` | `\tEOF`, `zzrun X` | `:165` [S1] | plain << is not tab-stripped |
| H5 | spaces or trailing blanks do not close | `cat <<EOF\n  EOF\nEOF \nzzrun X\nEOF` | 3 literal lines | `:165` [S1] | new |
| H6 | an unterminated heredoc swallows the rest | `cat <<EOF\nzzrun X` | stdout `zzrun X` (stderr not asserted) | `:163-167` | never terminated |
| H7 | two heredocs in sequence | `cat <<A\nx\nA\ncat <<B\ny\nB\nzzrun X` | `x`, `y`, `RAN:X` | `:162-175` | two heredocs |
| H8 | a marker with digits | `cat <<EOF2\nq\nEOF2\nzzrun X` | `q`, `RAN:X` | `:169` | marker with digits |
| H9 | a marker with `-` is the whole word | `cat <<END-X\nEND\nzzrun X\nEND-X` | `END`, `zzrun X` | `:169` [S2] | new |
| H10 | an interpreter heredoc runs | `bash <<'EOF'\nzzrun X\nEOF` | `RAN:X` | `:9-10,157` [L4]; `.claude/rediacc_hooks/guards/block_git_amend.py:89` honours it | interpreter heredoc; git_amend; bash_write python heredoc |
| H11 | a here-string into a shell runs | `bash <<< 'zzrun X'` | `RAN:X` | `:169` [L4] | new |
| H12 | a here-string has no body | `cat <<<x\nzzrun X` | `x`, `RAN:X` | `:169` [L5] | new |
| H13 | `<<` inside quotes or a comment is not a heredoc | `echo "<<EOF"\nzzrun X` and `true # <<EOF\nzzrun Y` | `<<EOF`, `RAN:X`; `RAN:Y` | `:169` [L5] | new |

**Quoting and words**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| Q1 | a quoted span is one literal word | `echo 'zzrun X'; echo "never zzrun Y"` | 2 literal lines | `:297-308` | single-quoted prose; prose in commit msg; about 10 guard "quoted prose" rows |
| Q2 | `'` inside `"..."` is literal | `echo "it's"; zzrun X; echo 'y'` | `it's`, `RAN:X`, `y` | `:300,305` [L6] | new |
| Q3 | `\"` inside `"..."` does not close it | `echo "p \" q"; zzrun X; echo "r"` | `RAN:X` among the lines | `:306` [L6] | new |
| Q4 | a substitution inside `"..."` runs | ``echo "$(zzrun X)"; echo "`zzrun Y`"`` | `RAN:X`, `RAN:Y` | `:306` [L2] | adhoc_sanctioned "banned half INSIDE quotes" |
| Q5 | quote removal on the command word | `"zzrun" X; zz"run" X; zz\run X; \zzrun X; $'zzrun' X` | 5 x `RAN:X` | `:323`; `.claude/rediacc_hooks/guards/block_git_force_push.py:28` [L7] | new |
| Q6 | backslash-newline joins | `zzrun X \`+newline+`Y` | `RAN:X\|Y` | `:335` [L8] | new |
| Q7 | an unbalanced quote rejects the whole command | mode n: `echo 'zzrun X` and `echo "zzrun X` | rc != 0; with -c, stdout empty | `:305-306` (the unstripped span is scanned) | unbalanced single/double |
| Q8 | nested quotes in a wrapper | `sh -c "zzrun X 'y'"` | `RAN:X\|y` | `:311` | nested quotes |
| Q9 | an unquoted variable delivers the flag | `X="--f"; zzrun a $X` | `RAN:a\|--f` | `:340` `flag_present` | flag in an assignment |
| Q10 | a tab is a word separator | `zzrun`+TAB+`X; zzargv -C`+TAB+`p` | `RAN:X`, `<-C><p>` | `:434` (tab defect, A4) | tab separated; -C with a tab |
| Q11 | CR, VT and FF are word characters | `zzargv X$'\r'` | `<X\r>` | `:70` `SPACE` [S3] | carriage return |

**Separators and command position**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| S1 | each separator starts a command | `zzrun 1; zzrun 2 && zzrun 3 \|\| zzrun 4; zzrun 5 \| cat; (zzrun 6); x=$(zzrun 7); echo "$x"`, then a newline and `zzrun 8` | RAN 1,2,3,5,6,7,8 | `:323`, `:355` | after-a-separator rows (git_amend, git_empty_commit, worktree_add, protected_files, binary_deploy) |
| S2 | reserved words and prefix builtins start a command | `{ zzrun 1; }; ! zzrun 2; if :; then zzrun 3; fi; for i in 4; do zzrun $i; done; command zzrun 5; time zzrun 6; exec zzrun 7` | RAN 1-7 | `:323`; every copied anchor [L9] | new |
| S3 | a redirect may precede the command | `2>/dev/null zzrun X` | `RAN:X` | `:323`; `.claude/rediacc_hooks/guards/block_git_force_push.py:28` [L9] | new |
| S4 | separators inside quotes are data | `echo "a;zzrun X"; echo 'b\|zzrun Y'` | 2 literal lines | `:297-308,355` | r46 scope |
| S5 | arguments do not cross a separator | `zzargv view 94 --repo a; zzargv merge 66 --repo b` | 2 separate argv lines | `:352-362` | r46 two gh / two merges |
| S6 | a separator ends ssh's argv | `zzargv h true; zzargv docker ps` | `<h><true>`, `<docker><ps>` | `.claude/rediacc_hooks/guards/block_ssh_docker.py:20` | ssh_docker "separator ends the clause" |

**Redirects**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| R1 | a redirect is not an argument | `zzargv add -A 2>/dev/null; zzargv add -A 3>&1` | `<add><-A>` x2 | `.claude/rediacc_hooks/guards/block_blanket_git_add.py:47` | blanket_git_add x3 |
| R2 | `>` and `>>` open for write | `echo x > "$T/a.sh"; echo y >> "$T/a.sh"; cat "$T/a.sh"` | `x`, `y` | `.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:67` | redirect onto running script; roundlog_truncate x2 |
| R3 | `>|` truncates under noclobber | `set -C; echo o > "$T/f"; echo n >\| "$T/f"; cat "$T/f"` | `n` | `:52,67` [L14] | new (clobber half verified on /dev/null only) |
| R4 | an unquoted `->` is a redirect | `echo x->"$T/f.sh"; cat "$T/f.sh"` | `x-` | `:45` [L14, deliberate] | "ASCII arrow" row |
| R5 | redirect locality across ssh | `zzrun h cat f > "$T/o"; cat "$T/o"; zzargv h 'cat > /etc/x'` | `RAN:h\|cat\|f`, `<h><cat > /etc/x>` | `.claude/rediacc_hooks/guards/block_ssh_file_write.py:29` [L13] | ssh_file_write x3 |

**cd scope**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| C1 | cd persists across `&&` and `;` | `cd /tmp && pwd; pwd` | `/tmp` x2 | `:377,429` | cd into submodule; cd relative && |
| C2 | the last cd wins | `cd /tmp; cd /; pwd` | `/` | `:430` | two cds |
| C3 | a failed cd skips the `&&` branch | `cd /nonexistent-q 2>/dev/null && zzrun X; echo after` | `after` | `:443-445` | cd absolute nonexistent |
| C4 | a quoted path is unquoted | `cd "/tmp" && pwd` | `/tmp` | `:436-437` | cd quoted path |
| C5 | a subshell or pipeline cd does not persist; `-C` is per-command | `cd /; (cd /tmp); pwd; cd /tmp \| true; pwd` | `/`, `/` | `:429-430`, `:377` [L12] | new |

**Processes, PATH and script reading**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| P1 | `$$` in `$(...)` is the parent shell | `[ "$$" = "$(echo $$)" ] && [ "$BASHPID" != "$(echo $BASHPID)" ] && echo same` | `same` | `.claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py:182-186` | $$ fallback (untwinned) |
| P2 | `\|\|` substitutes the fallback; `;` and `&&` do not | `echo "[$(cat /nx 2>/dev/null \|\| echo 1)]"; echo "[$(cat /nx 2>/dev/null && echo 1)]"` | `[1]`, `[]` | `:189,215` | minimal fire, &&-join, ;-join |
| P3 | an unbalanced `$(` is a syntax error | mode n: `until ! [ -e /proc/$(cat x.pid \|\| echo 1 ; do sleep 5; done` | rc != 0 | `:189` (None means allow) | unparseable substitution |
| P4 | the waiting shell's argv holds the pattern | `pgrep -f TOK >/dev/null; echo $?` (TOK built at runtime) | `0` | `.claude/rediacc_hooks/guards/block_self_matching_pgrep.py:38,52` | the self-matching loop; negation |
| P5 | the bracket remedy does not match itself | `pgrep -f '[z]TOK' >/dev/null; echo $?` | `1` | `:10,30` | the remedy |
| P6 | a quoted pattern reaches pgrep unquoted | `pgrep -f 'TOK' >/dev/null; echo $?` | `0` | `:52` | quoted / double-quoted pattern |
| P7 | bash reads a script lazily, by byte offset | file `$T/s.sh` = `printf 'printf "APPENDED\\n"\n' >> "$0"`; run `bash "$T/s.sh"` | `APPENDED` | `.claude/rediacc_hooks/proc.py:4`; `.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:6`; `.claude/rediacc_hooks/guards/block_edit_of_running_script.py:7` | both guards' headers (NOT run here: needs a file) |
| P8 | `command -v` prefers an executable later in PATH | in `$T`: `d1/zt` mode 600, `d2/zt` mode 755, `d3/zd/` a directory; `PATH=$T/d1:$T/d2 command -v zt; PATH=$T/d3:$T/d2 command -v zd` | `$T/d2/zt`; not found | `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:217-236`; `.claude/rediacc_hooks/hookio.py:417` [L15] | toolchain :27 measurement |

**Degenerate inputs**

| ID | Fact | Probe (bash -c unless noted) | Expected | Python that relies on it | Source |
|---|---|---|---|---|---|
| X1 | an empty, blank or newline-only command runs nothing | `''`, `'  \t '`, `$'\n'` | rc 0, stdout empty | `.claude/rediacc_hooks/shellscan.py:235-240` | empty, space, whitespace, newline only |
| X2 | trailing newlines and blank lines are inert | `zzrun X\n\n`; `echo a\n\nzzrun X` | `RAN:X`; `a`, `RAN:X` | `:77-86` | trailing newline(s); blank line |

That is 58 rows. 29 pass today with the Python agreeing. The 29 others are either `contradicted` rows (bash contradicts the Python: the live bugs in section 1) or safe-direction divergences (`[S#]`); the table marks each one.

## 4. Counts and the mechanical rule

**Oracle cases today:**

| Differential | Cases |
|---|---|
| `test_shellscan_differential` | 401 command cases (333 harvested + 68 `corpus.EDGE_CASES`) + 15 JSON = 416 |
| `test_guards_differential` (default build) | 6,047 |
| `test_post_bash_differential` | 18 |
| **Total** | **6,481** |

That total is 100 percent retired from twin execution. The README figure of 5,844 is stale.

**Kept as bash facts:** 103 labelled oracle cases (58 of the 68 `corpus.EDGE_CASES`, plus 45 twinned-guard `EDGE_CASES`). Add 8 cases from untwinned guards (`block_unsatisfiable_pid_wait` 6, `block_prose_style_commit` 1, `block_push_to_protected_branch` 1). Together they collapse into the 58 probes above. The other 6,378 go to goldens only.

**Rule (apply case by case, in order):**

1. **Only labelled cases can be kept.** A case can be KEEP only if it is an entry in `corpus.EDGE_CASES` or in a guard module's `EDGE_CASES`. These are always DROP: harvested `harvest-NNN`, cross-fed, `DEGENERATE_PAYLOADS`, `JSON_PAYLOADS` (jq facts, not bash) and every post-bash case.
2. **It must use a bash construct.** Its command string must contain at least one of: a heredoc or here-string, a quote, `$(`, a backtick, a shell wrapper (`sh`/`bash`/… with `-c`) or `eval`, a `NAME=` prefix, a separator (`;` `&` `|` `(` newline), a redirect (`>` `<`), `cd` or `-C`, `$$`, `pgrep -f`, or a leading or trailing blank.
3. **Its label must be about bash.** The label, or the comment directly above it, must claim how BASH parses or runs the JUDGED command. Label words that qualify: data, executes, still runs, closes, terminator, wrapper, payload, separator, redirection, prefix, quoted, scope, fallback, unparseable.
   - The label is policy, so DROP, when it states the guard's ruling. Examples: "quoted prose still fires, and that is the ruling", "a pipe between them is not the separator this matches", anything about gh's or git's own flag parsing (`--repo=`, `-R`, `--body-file`, `=true`, `git -C`), or a bash usage error (`bash -c` with nothing after it).
4. **The fact must be about the judged command, not the twin's own script.** Always DROP PORT NOTE facts about the twin's own bash:
   - `$(...)` newline stripping (`.claude/rediacc_hooks/shellscan.py:106`); here-string and `printf '%s\n'` newlines (`:111`, `:452`);
   - IFS splitting and globbing in the twin's loops (`.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:19`, `.claude/rediacc_hooks/guards/block_nonstandard_branch_name.py:14`, `.claude/rediacc_hooks/guards/block_agent_browser_repo_output.py:20`);
   - `sort -u` under `LC_ALL=C` (`.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:22`, `.claude/rediacc_hooks/guards/warn_stale_index.py:19`);
   - `[[ =~ ]]` anchors (`.claude/rediacc_hooks/guards/block_agent_state_shape.py:27`, `.claude/rediacc_hooks/guards/block_roundlog_write.py:21`);
   - `${x%% *}` (`.claude/rediacc_hooks/guards/block_plan_without_tasks.py:40`); `10#` arithmetic (`.claude/rediacc_hooks/guards/block_long_sleep.py:86`);
   - associative-array hash order (`.claude/rediacc_hooks/guards/block_host_toolchain_run.py:16`); jq `null` (`.claude/rediacc_hooks/hookio.py:16`); `${#x}` locale (`.claude/rediacc_hooks/guards/block_compacted_plan_edit.py:38`).
   
   Once the twin is deleted no bash runs those lines. The goldens freeze their byte-level effect, and Rule T is allowed to change them.
5. **Keep one probe per fact, not one per case.** Several KEEP cases share one row; list them all in the row's `source`.

When the writer applies this rule, they should record the resulting source list in PLAN §3 A0 before A3 deletes anything.

### Critical Files for Implementation
- /home/developer/console/.claude/rediacc_hooks/shellscan.py
- /home/developer/console/.claude/rediacc_hooks/tests/corpus.py
- /home/developer/console/.claude/rediacc_hooks/tests/test_shellscan_differential.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_git_amend.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_host_toolchain_run.py
