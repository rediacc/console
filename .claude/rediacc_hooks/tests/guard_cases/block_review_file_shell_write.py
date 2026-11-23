"""The test tables of `block_review_file_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

R = "agent/reviews/1231-9/" + "a" * 40 + ".md"


EDGE_CASES = [
    ("a redirect", "printf 'Resolution: fixed' > %s" % R),
    ("an append", "echo x >> %s" % R),
    ("an append to the clean ledger", "echo '{}' >> agent/reviews/1231-9/clean.jsonl"),
    ("a cat heredoc", "cat > %s <<'EOF'\n# Review\nEOF" % R),
    ("tee", "echo x | tee %s" % R),
    ("tee -a", "echo x | tee -a %s >/dev/null" % R),
    ("sed -i", "sed -i 's/\\[high\\]/[low]/' %s" % R),
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/1231-9/"),
    ("mv onto a review file", "mv /tmp/x.md %s" % R),
    ("cp -t names the directory", "cp -t agent/reviews/1231-9 /tmp/x.md"),
    # #5077391c: xargs appends its feed, so under `-t` a fed word is a source and without it the last one is the destination.
    # The fed word as the file an in-place editor, tee or truncate writes. Each was allowed before: the editor's own words named no review file.
    ("xargs feeds a review file to sed -i", "echo %s | xargs sed -i s/a/b/" % R),
    ("xargs -I feeds a review file to sed -i", "echo %s | xargs -I{} sed -i s/a/b/ {}" % R),
    ("xargs feeds a review file to tee", "echo %s | xargs tee" % R),
    ("xargs feeds a review file to truncate", "echo %s | xargs truncate -s 0" % R),
    (
        "xargs -I feeds a review directory to truncate",
        "echo agent/reviews/1231-9 | xargs -I{} truncate -s 0 {}/x.md",
    ),
    ("xargs feeds a review file to a reader", "echo %s | xargs cat" % R),
    ("xargs feeds another file to sed -i", "echo /tmp/x.md | xargs sed -i s/a/b/"),
    ("xargs feeds a review file to cp -t elsewhere", "echo %s | xargs cp -t /tmp" % R),
    (
        "xargs feeds cp -t the review directory a source",
        "echo /tmp/x.md | xargs cp -t agent/reviews/1231-9",
    ),
    ("xargs feeds cp a review file as its destination", "echo %s | xargs cp /tmp/x.md" % R),
    (
        "xargs feeds a review file then a destination elsewhere",
        "echo %s /tmp/out.md | xargs cp" % R,
    ),
    ("a copy OUT through cp -t", "cp -t /tmp %s" % R),
    ("truncate", "truncate -s 0 %s" % R),
    ("python -c open for write", "python3 -c \"open('%s','w').write('x')\"" % R),
    (
        "python heredoc write_text",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('x')\nEOF" % R,
    ),
    ("after cd", "cd agent/reviews/1231-9 && echo x > a.md"),
    ("inside sh -c", "sh -c 'echo x > %s'" % R),
    # allowed
    ("reading one", "cat %s" % R),
    ("grep over the directory", "grep -rn high agent/reviews/"),
    ("echo naming the path", "echo 'see agent/reviews/1231-9/'"),
    ("a commit that carries them", "git commit -F /tmp/m.txt -- agent/reviews/1231-9/"),
    ("git add", "git add -- agent/reviews/1231-9/%s.md" % ("a" * 40)),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 1231-9"),
    ("a copy OUT of the directory", "cp %s /tmp/x.md" % R),
    ("a python read", "python3 -c \"print(open('%s').read())\"" % R),
    (
        "python heredoc rewriting a URL that names the directory",
        (
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('t.py')\n"
            "p.write_text(p.read_text().replace('\"https://github.com/o/r/blob/h/agent/reviews/b/x.md\"', 'U'))\nEOF"
        ),
    ),
    ("an unrelated redirect", "echo x > /tmp/out.txt"),
    ("a sibling directory", "echo x > agent/reviews-old/x.md"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "sed -i launched by find under the directory",
        "find agent/reviews -name '*.md' -exec sed -i s/high/low/ {} +",
    ),
    (
        "a launched cp onto what find names",
        r"find agent/reviews -name '*.md' -exec cp /tmp/x.md {} \;",
    ),
    (
        "a launched copy OUT of the directory",
        r"find agent/reviews -name '*.md' -exec cp {} /tmp/ \;",
    ),
    # A Python program is judged by its write TARGETS: a review path in written content is data.
    (
        "a review path only in written content",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('/tmp/s/f.py')\ns = p.read_text().replace('X', 'agent/reviews/feat/%02d.md')\np.write_text(s)\nEOF",
    ),
    (
        "a target built from a review path",
        "python3 - <<'EOF'\nimport pathlib\nT = 'agent/reviews/feat/%02d.md'\npathlib.Path(T % 1).write_text('x')\nEOF",
    ),
    # e30f1ad1.1: pathlib's `.open` takes its mode first, `os.open` takes flags.
    ("Path.open for write", "python3 -c \"import pathlib; pathlib.Path('%s').open('w')\"" % R),
    ("Path.open for read", "python3 -c \"import pathlib; pathlib.Path('%s').open().read()\"" % R),
    ("os.open for write", "python3 -c \"import os; os.open('%s', os.O_WRONLY)\"" % R),
    # e30f1ad1.2: a command a program hands to a shell is judged as the shell line it is.
    ("os.system redirect", "python3 -c \"import os; os.system('echo x > %s')\"" % R),
    ("subprocess argv tee", "python3 -c \"import subprocess; subprocess.run(['tee', '%s'])\"" % R),
    ("node execSync redirect", "node -e \"require('child_process').execSync('echo x > %s')\"" % R),
    (
        "os.system reading the directory",
        "python3 -c \"import os; os.system('cat %s > /tmp/x')\"" % R,
    ),
]
