"""The test tables of `block_protected_files`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("a restore of the settings file", "git restore .claude/settings.json"),
    ("a checkout of the settings file", "git checkout .claude/settings.json"),
    ("an rm of the pre-commit script", "rm scripts/pre-commit-check.sh"),
    ("rm after a separator", "true; rm .claude/settings.json"),
    # The over-block the clause fix exists for.
    (
        "checking out a branch then READING the file",
        "git checkout main && cat .claude/settings.json",
    ),
    ("reading the file on its own", "cat .claude/settings.json"),
    ("a restore of an unprotected path", "git restore packages/cli/src/x.ts"),
    ("a wrapper payload is still scanned", "sh -c 'git restore .claude/settings.json'"),
    # Command position on every arm: these sentences were refused before 2026-10-09.
    (
        "a sentence naming the restore is not running it",
        "echo the docs say never to run git restore .claude/settings.json in this repo",
    ),
    ("a sentence naming rm is not running it", "echo never rm .claude/settings.json here"),
    ("git global flags before the verb", "git -C . restore .claude/settings.json"),
    ("a prefix command still reaches rm", "sudo rm .claude/settings.json"),
    (
        "find -exec is a launcher shellscan walks",
        r"find . -exec rm .claude/settings.json \;",
    ),
    (
        "every find -exec is walked, not only the first",
        r"find . -name x -exec true {} \; -exec rm .claude/settings.json \;",
    ),
    # The path on the producer side of a pipe into xargs (#ec63ff8c): each was allowed before 2026-10-09.
    ("xargs rm fed the path on stdin", "echo .claude/settings.json | xargs rm"),
    (
        "xargs git restore fed the path on stdin",
        "printf '%s' scripts/pre-commit-check.sh | xargs git restore",
    ),
    ("xargs -I with the path on stdin", "echo .claude/settings.json | xargs -I{} rm -f {}"),
    (
        "an earlier stage of the pipe feeds xargs too",
        "echo .claude/settings.json | sort | xargs git checkout --",
    ),
    # ... and the consumer has to be destructive, and fed by THIS pipe.
    ("piping the path to cat reads it", "echo .claude/settings.json | cat"),
    ("xargs cat reads it", "echo .claude/settings.json | xargs cat"),
    ("xargs rm of an unprotected path", "echo packages/cli/src/x.ts | xargs rm"),
    ("a separator ends the pipe before xargs", "echo .claude/settings.json; ls | xargs rm"),
    ("xargs behind sudo", "echo .claude/settings.json | sudo xargs rm"),
    ("xargs git rm", "git ls-files .claude/settings.json | xargs git rm"),
    ("a tee between the producer and xargs", "echo .claude/settings.json | tee /tmp/l | xargs rm"),
    (
        "git reads its pathspec from stdin",
        "echo .claude/settings.json | git restore --pathspec-from-file=-",
    ),
    ("a heredoc fed to xargs", "cat <<'EOF' | xargs rm\n.claude/settings.json\nEOF"),
    ("inside a wrapper payload", "sh -c 'echo .claude/settings.json | xargs rm'"),
    ("find -exec rm of the path find names", r"find .claude/settings.json -exec rm {} \;"),
    ("xargs echo prints it", "grep -n .claude/settings.json docs/x.md | xargs echo"),
    ("xargs ls lists it", "echo .claude/settings.json | xargs ls -l"),
    ("find -exec cat reads it", r"find .claude/settings.json -exec cat {} \;"),
    (
        "git restore of stdin with no protected path",
        "echo packages/x.ts | git restore --pathspec-from-file=-",
    ),
    # A shell payload xargs or find -exec launches inherits the feed (#32e75fa4): each refusal was allowed before.
    (
        "an xargs-fed sh -c payload removes $0",
        """echo .claude/settings.json | xargs sh -c 'rm "$0"'""",
    ),
    (
        "an xargs-fed bash -c payload removes $@",
        """echo .claude/settings.json | xargs bash -c 'rm "$@"' _""",
    ),
    ("xargs -I into a sh -c payload", "echo .claude/settings.json | xargs -I{} sh -c 'rm {}'"),
    (
        "a nested shell inside the fed payload",
        """echo .claude/settings.json | xargs sh -c 'bash -c "git checkout -- \\"\\$0\\"" "$0"'""",
    ),
    ("find -exec sh -c removes $0", r"""find .claude/settings.json -exec sh -c 'rm "$0"' {} \;"""),
    (
        "an xargs-fed sh -c payload that only reads",
        """echo .claude/settings.json | xargs sh -c 'cat "$0"'""",
    ),
    (
        "an xargs-fed sh -c rm of an unprotected path",
        """echo packages/x.ts | xargs sh -c 'rm "$0"'""",
    ),
    (
        "a piped sh -c payload names no fed command",
        """echo .claude/settings.json | sh -c 'rm -f /tmp/x'""",
    ),
    (
        "a piped sh -c payload's xargs rm reads its stdin",
        "echo .claude/settings.json | sh -c 'xargs rm'",
    ),
    ("through cat inside the payload", "echo .claude/settings.json | bash -c 'cat | xargs rm'"),
    (
        "a piped sh -c payload's xargs only reads",
        "echo .claude/settings.json | bash -c 'xargs cat'",
    ),
    # A group's stdin is every member's, and a read loop turns the feed into a variable (#31ed6c5f): each refusal was allowed before.
    ("a subshell consumer is fed", "echo .claude/settings.json | (xargs rm)"),
    ("a brace-group consumer is fed", "echo .claude/settings.json | { xargs rm; }"),
    ("a here-string on a subshell feeds it", "(xargs rm) <<< .claude/settings.json"),
    (
        "a read loop removes the read variable",
        'echo .claude/settings.json | while read f; do rm "$f"; done',
    ),
    (
        "a read loop restores REPLY",
        'echo .claude/settings.json | while read; do git restore "${REPLY}"; done',
    ),
    (
        "a read loop that only reads",
        'echo .claude/settings.json | while read -r f; do cat "$f"; done',
    ),
    ("a subshell consumer fed an unprotected path", "echo packages/x.ts | (xargs rm)"),
    (
        "a read loop removing another path",
        "echo .claude/settings.json | while read f; do rm /tmp/x; done",
    ),
    # A loop fed through `done` feeds its body (review e085085d.1): each refusal was allowed before, the first pinned as a KNOWN GAP.
    (
        "a read loop fed through done <<<",
        'while read f; do rm "$f"; done <<< .claude/settings.json',
    ),
    (
        "a read loop fed through done < <(...)",
        'while read f; do rm "$f"; done < <(echo .claude/settings.json)',
    ),
    ("a piped loop's body is fed", "echo .claude/settings.json | while true; do xargs rm; done"),
    (
        "a loop fed through done that only reads",
        'while read f; do cat "$f"; done <<< .claude/settings.json',
    ),
    # The path in a shape the prose view drops (e085085d.1 sweep): each refusal was allowed before.
    ("a quoted path", 'rm ".claude/settings.json"'),
    ("a variable holding the path", 'f=.claude/settings.json; rm "$f"'),
    ("a for list holding the path", 'for f in scripts/pre-commit-check.sh; do rm "$f"; done'),
    ("a path relative to a cd", "cd scripts && rm pre-commit-check.sh"),
    ("a recursive rm above the path", "rm -rf .claude"),
    ("a recursive rm beside the path", "rm -rf .claude/tmp-scratch"),
    ("a variable holding the path, read", 'f=.claude/settings.json; cat "$f"'),
    # A wrapper is a command the walk found, not a quoted word that spells one (#31ed6c5f): both were refused before.
    (
        "a quoted sh -c is an echo argument",
        """echo "sh -c 'rm x'" "x .claude/settings.json | y\"""",
    ),
    ("a quoted eval is an echo argument", """echo "eval rm" ".claude/settings.json\""""),
    (
        "a real sh -c after a quoted mention",
        """echo "sh -c 'rm x'"; sh -c 'rm .claude/settings.json'""",
    ),
    # #c9c8c18e: a glob under a variable the same command set to a literal is judged as that literal (allowed); unset, set from a substitution, or set into a protected root, it is still refused.
    (
        "a glob under a variable this command set",
        "D=agent/d778be9d/b6-replay; git rm -q -- $D/*.py $D/*.json",
    ),
    ("a glob under a variable never set", "rm $D/*.json"),
    ("a glob under a variable set to .claude", "D=.claude; git rm -q -- $D/*.json"),
    ("a glob under a variable set by a substitution", "D=$(echo .claude); rm $D/*.json"),
    ("a glob under a variable set then unset", "D=agent/x; unset D; rm $D/*.json"),
    # acc34f73.1/.2: a `$D` that bash does not expand (single quotes, an escaped dollar) names a literal directory `$D`, so the typed text is judged, not the assigned value.
    ("a single-quoted variable under a recursive rm", "D=agent/x; rm -r '$D/../.claude'"),
    ("an escaped dollar in double quotes", 'D=agent/x; rm -r "\\$D/../.claude"'),
    ("an escaped braced dollar in double quotes", 'D=agent/x; rm -r "\\${D}/../.claude"'),
    ("a variable that bash expands under a recursive rm", "D=agent/x; rm -r $D/../.claude"),
    # 335d582f.1: an empty expansion shifts `xargv` out of line with `argv`; the assigned reading still holds for an expanded word and the typed one for a quoted word.
    ("misaligned argv, an expanded variable", "E=; D=agent/x; rm -r $E $D/../.claude"),
    ("misaligned argv, a single-quoted variable", "E=; D=agent/x; rm -r $E '$D/../.claude'"),
    (
        "misaligned argv, a single-quoted twin of an expanded word (review a62c7d11.1)",
        "E=; D=agent/x; rm -r $E $D/../.claude '$D/../.claude'",
    ),
    (
        "a glob under a variable set only on one branch",
        "D=agent/x; [ -n y ] && D=.claude; rm $D/*.json",
    ),
]
