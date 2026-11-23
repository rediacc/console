"""The test tables of `block_worktree_add`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

EDGE_CASES = [
    ("the plain shape", "git worktree add /tmp/wt main"),
    ("a -C flag between git and the verb", "git -C private/renet worktree add /tmp/wt"),
    ("after a separator", "true; git worktree add /tmp/wt"),
    # The wrapper the second arm exists for, in three spellings.
    ("the run.sh wrapper", "./run.sh worktree create 0901-1"),
    ("the run.sh wrapper through an interpreter", "bash run.sh worktree create x"),
    ("the run.sh wrapper by absolute path", "/home/x/console/run.sh worktree create x"),
    # The Python port the wrapper reaches, in every spelling that skips run.sh.
    ("the package entry", "PYTHONPATH=.ci python3 -m rediacc_ci worktree create x"),
    ("the port's module", "PYTHONPATH=.ci python3 -m rediacc_ci.dev.worktree create x"),
    ("the port by path", "python3 .ci/rediacc_ci/dev/worktree.py create x"),
    ("the port under a venv interpreter", "uv run python -m rediacc_ci.dev.worktree create"),
    ("control: the port's list is allowed", "python3 -m rediacc_ci.dev.worktree list"),
    ("control: the package's worktree list is allowed", "python3 -m rediacc_ci worktree list"),
    (
        "control: reading the port is not running it",
        "grep -n create .ci/rediacc_ci/dev/worktree.py",
    ),
    ("the port inside sh -c", "sh -c 'python3 -m rediacc_ci worktree create x'"),
    ("the port behind timeout", "timeout 60 python3 .ci/rediacc_ci/dev/worktree.py create"),
    ("the port with an interpreter option first", "python3 -X dev -m rediacc_ci worktree create"),
    (
        "control: a sentence naming the port is not running it",
        "echo the docs say never to run rediacc_ci.dev.worktree create here",
    ),
    # Reads are none of this hook's business.
    ("listing worktrees is allowed", "git worktree list"),
    ("removing a worktree is allowed", "git worktree remove /tmp/wt"),
    ("a variable script path naming the words", "python3 $G/test-block_worktree_add.py"),
    ("control: a variable script path, no words", "python3 $G/unrelated.py"),
    ("control: an assigned script path, no such file", "G=/no/such; python3 $G/unrelated.py"),
    (
        "a script this command writes through a variable",
        "G=/d; printf 'git worktree add x' > $G/x.py; python3 $G/x.py",
    ),
    ("control: a bare name in another checkout", "git -C /other/repo worktree remove w2-proof"),
    ("run.sh doing something else", "./run.sh setup --check"),
    # A lease tree leaves only through GC (Design 6): the verbs on its path are refused, the lease tool and the same verbs on any other path are not.
    ("the lease tool is allowed", "./run.sh worktree lease"),
    ("the lease listing is allowed", "./run.sh worktree leases --json"),
    ("the landing tree verb is allowed", "./run.sh worktree landing"),
    ("the landing tree verb by path is allowed", "/home/x/console/run.sh worktree landing"),
    ("removing a lease tree", "git worktree remove .claude/worktrees/x"),
    ("force-removing a lease tree", "git worktree remove --force /r/.claude/worktrees/x"),
    ("unlocking a lease tree", "git worktree unlock .claude/worktrees/x"),
    ("moving a lease tree", "git worktree move .claude/worktrees/x /tmp/x"),
    ("a lease tree joined to -C", "git -C .claude worktree remove worktrees/x"),
    ("a lease tree as the run's directory", "git -C .claude/worktrees/x worktree remove ."),
    ("a lease tree joined to cd", "cd .claude/worktrees && git worktree lock x"),
    (
        "a lease tree in a python argv",
        (
            "python3 -c \"import subprocess; subprocess.run(['git','worktree','remove',"
            "'.claude/worktrees/x'])\""
        ),
    ),
    (
        "a lease tree in a perl argv",
        'perl -e \'system("git","worktree","unlock",".claude/worktrees/x")\'',
    ),
    ("control: a bare prune names no tree", "git worktree prune"),
    ("control: a look-alike directory", "git worktree remove .claude/worktrees-old/x"),
    ("control: a sentence naming the verb", "echo git worktree remove .claude/worktrees/x"),
    ("control: listing the lease root", "ls .claude/worktrees"),
    ("prose is stripped before the scan", "echo 'git worktree add /tmp/wt'"),
    # RULE T (PLAN-retire-bash-oracles A4, A0 L9): GIT_AT_CMD's anchor is the copied `(^|[;&|(]|\$\(|`)`, which misses every reserved word, prefix builtin and leading redirect. These ran with rc 0 until `shellscan.lifted_commands`; the heredoc twin below them is data and stays allowed.
    ("L9 a brace group", "{ git worktree add /tmp/wt main; }"),
    ("L9 a leading redirect", "2>/dev/null git worktree add /tmp/wt main"),
    ("L7 a quoted command word", '"git" worktree add /tmp/wt main'),
    (
        "control: a quoted heredoc naming the command is data",
        "cat > n.md <<'EOF'\ngit worktree add /tmp/wt main\nEOF",
    ),
    # The interpreter arm: a program text handed to python, node, perl or ruby, through -c/-e, a heredoc, a here-string or a pipe.
    (
        "python -c with a git argv list",
        "python3 -c \"import subprocess; subprocess.run(['git','worktree','add','/tmp/x'])\"",
    ),
    (
        "python -c calling the port in-process",
        "python3 -c 'from rediacc_ci.dev import worktree; worktree.main([\"create\"])'",
    ),
    (
        "python reading a heredoc",
        "python3 - <<'EOF'\nimport os\nos.system('git worktree add /tmp/x')\nEOF",
    ),
    (
        "python reading a here-string",
        "python3 - <<< 'import os; os.system(\"git worktree add /tmp/x\")'",
    ),
    (
        "python fed by a piped cat heredoc",
        "cat <<'EOF' | python3\nimport os; os.system('git worktree add x')\nEOF",
    ),
    ("node -e", 'node -e \'require("child_process").execSync("git worktree add /tmp/x")\''),
    ("perl -e with an argv list", 'perl -e \'system("git", "worktree", "add", "/tmp/x")\''),
    (
        "control: python -c listing worktrees",
        "python3 -c \"import subprocess; subprocess.run(['git','worktree','list'])\"",
    ),
    (
        "control: python printing a sentence",
        "python3 -c 'print(\"never run git worktree add here\")'",
    ),
    (
        "control: python reading the port's source",
        "python3 - <<'EOF'\nprint(open('.ci/rediacc_ci/dev/worktree.py').read().count('create'))\nEOF",
    ),
    (
        "control: python reading the port's docstring",
        "python3 -c 'from rediacc_ci.dev import worktree; print(worktree.cmd_create.__doc__)'",
    ),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "the port launched by find -exec",
        r"find . -maxdepth 0 -exec python3 -m rediacc_ci.dev.worktree create x \;",
    ),
    (
        "a python program launched by npx -c",
        'npx -c "python3 -c \\"import os; os.system(\'git worktree add /tmp/x\')\\""',
    ),
    (
        "control: prose naming a launched create",
        "echo find . -exec python3 -m rediacc_ci.dev.worktree create x",
    ),
    # fa5d11be.1-.4: option values, attached -e code, a program too deep for ast, quote-like literals.
    ("perl -I value then -e", 'perl -I lib -e \'system("git","worktree","add","x")\''),
    ("control: words after perl's script", "perl -I lib script.pl git worktree add x"),
    ("perl -e with attached code", "perl '-esystem(\"git worktree add x\")'"),
    (
        "a deep program read by regex",
        "python3 -c \"import os; os.system('git worktree add /tmp/x'); x = %s1\"" % ("-" * 10000),
    ),
    ("control: a deep program running nothing", 'python3 -c "x = %s1"' % ("-" * 10000)),
    ("a perl qw() word list", "perl -e 'system qw(git worktree add x)'"),
    ("control: a qw() sentence", "perl -e 'print qw(never run git worktree add here)'"),
]
