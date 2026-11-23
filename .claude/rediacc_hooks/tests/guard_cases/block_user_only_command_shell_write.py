"""The test tables of `block_user_only_command_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

_K = "disable-model-invocation"


_C = ".claude/commands/x.md"


EDGE_CASES = [
    ("a heredoc writing the key", "cat > %s <<'EOF'\n---\n%s: true\n---\nEOF" % (_C, _K)),
    ("an append of another spelling", "echo 'Disable_Model_Invocation: yes' >> %s" % _C),
    (
        "tee into a skill",
        "printf -- '---\\n%s: false\\n---\\n' | tee .claude/skills/s/SKILL.md" % _K,
    ),
    ("sed -i adding the key", "sed -i 's/^description:/%s: true\\ndescription:/' %s" % (_K, _C)),
    ("sed -i appending the key", "sed -i '1a %s: true' %s" % (_K, _C)),
    # #5077391c: xargs appends its feed, so under `-t` a fed word is a SOURCE (the commands directory once read as the source here, and a flagged command copied into a skill passed).
    (
        "xargs feeds a flagged command to cp -t a skill",
        "echo .claude/commands/handoff.md | xargs cp -t .claude/skills/demo",
    ),
    (
        "xargs feeds a flagged command to cp -t elsewhere",
        "echo .claude/commands/handoff.md | xargs cp -t /tmp",
    ),
    (
        "xargs feeds the exception list to cp -t elsewhere",
        "echo .ci/config/model-invocation-exceptions.json | xargs cp -t /tmp",
    ),
    (
        "xargs feeds cp the exception list as its destination",
        "echo /tmp/x.json .ci/config/model-invocation-exceptions.json | xargs cp",
    ),
    (
        "python writing the key",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('---\\n%s: true\\n---\\n')\nEOF"
        % (_C, _K),
    ),
    ("after cd", "cd .claude/commands && echo '%s: on' >> x.md" % _K),
    ("inside sh -c", "sh -c \"echo '%s: 1' >> %s\"" % (_K, _C)),
    ("cp -t names where the copy lands", "cp -t .claude/skills .claude/commands/handoff.md"),
    # CONTROLS.
    ("sed -i deleting the key line", "sed -i '/^%s:/d' %s" % (_K, _C)),
    ("sed -i substituting the key away", "sed -i 's/^%s: true$//' %s" % (_K, _C)),
    ("echo to the terminal", "echo '%s: true is banned'" % _K),
    ("grep for the key", "grep -rn '%s' .claude/commands" % _K),
    ("a heredoc into a doc", "cat > docs/x.md <<'EOF'\n%s: true\nEOF" % _K),
    (
        "a commit message heredoc naming the key",
        "git commit -F - <<'EOF'\nfix: drop %s: true\nEOF" % _K,
    ),
    ("a command file without the key", "printf -- '---\\ndescription: x\\n---\\n' > %s" % _C),
    ("an unrelated redirect", "echo hello > /tmp/out.txt"),
    ("cp -t copies a command out", "cp -t /tmp .claude/commands/handoff.md"),
    # The exception list itself.
    (
        "a redirect into the exception list",
        "echo '{}' > .ci/config/model-invocation-exceptions.json",
    ),
    ("reading the exception list", "cat .ci/config/model-invocation-exceptions.json"),
]
