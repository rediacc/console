"""The test tables of `block_suppressions_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

_NQ = "# noq" + "a"


_TSI = "@ts-ignor" + "e"


_SC = "# shellcheck disabl" + "e"


EDGE_CASES = [
    (
        "a heredoc writing a python file with a marker",
        "cat > /r/x.py <<'EOF'\nimport os  %s: F401\nEOF" % _NQ,
    ),
    ("an append to a shell script", "echo '%s=SC2086' >> scripts/x.sh" % _SC),
    ("tee into a TS file", "printf '// %s\\n' | tee src/a.ts" % _TSI),
    ("sed -i adding a marker", "sed -i 's/x = 1/x = 1  %s: B010/' a.py" % _NQ),
    ("sed -i appending a marker line", "sed -i '/^import/a %s: E402' a.py" % _NQ),
    (
        "python -c writing a marker",
        "python3 -c \"open('a.py','a').write('x = 1  %s: B010')\"" % _NQ,
    ),
    (
        "python heredoc writing a marker",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('a.py').write_text('x = 1  %s: B010\\n')\nEOF"
        % _NQ,
    ),
    ("inside sh -c", "sh -c \"echo 'x = 1  %s: B010' >> a.py\"" % _NQ),
    # CONTROLS.
    ("sed -i removing a marker", "sed -i 's/  %s: B010//' a.py" % _NQ),
    ("echo to the terminal", "echo 'never write %s: B010'" % _NQ),
    (
        "a commit message heredoc naming the marker",
        "git commit -F - <<'EOF'\nfix: drop the %s: B010 swaps\nEOF" % _NQ,
    ),
    (
        "a heredoc into a Markdown file",
        "cat > docs/x.md <<'EOF'\nNever write `%s: B010`.\nEOF" % _NQ,
    ),
    ("grep for markers", "grep -rnP '%s' .ci" % _NQ),
    (
        "a python program that only reads",
        "python3 -c \"print(open('a.py').read().count('%s'))\"" % _NQ,
    ),
    ("an unrelated redirect", "echo hello > /tmp/out.txt"),
    ("a heredoc python file with no marker", "cat > /r/x.py <<'EOF'\nimport os\nEOF"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "sed -i launched by find -exec on the *.py it names",
        "find . -name '*.py' -exec sed -i 's/$/  %s: E501/' {} +" % _NQ,
    ),
    ("a launched grep only reads", "find . -name '*.py' -exec grep -n '%s' {} +" % _NQ),
]
