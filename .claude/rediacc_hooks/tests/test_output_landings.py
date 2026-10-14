"""`shellscan.output_landings` reads a tool's own output spelling as a write, and every word of a command it does not list (worklist item ff3ab826).

THE DEFECT. block_review_file_shell_write read redirects, `tee`, in-place editors, copiers, `truncate`, `dd of=` and interpreter programs, so `sort -o <file>`, `curl -o <file>`, `git diff --output=<file>`, `find -fprint <file>`, `sed 'w <file>'`, `uniq <in> <file>` and `touch <file>` each wrote a review record and were allowed (rc 0, 2026-10-13). The reading is a table of NON-writers: a listed command writes only through the spellings its row names, and an unlisted one is read as writing any word it names.

Each rule below is pinned in both directions: the pair it must yield, and a control beside it that must yield nothing (a plain reader, the same option naming another file, a fed word that is only read). The guard's verdicts over the same shapes are rows of `test-block_review_file_edit.py` and `hookcases.py`.
"""

from __future__ import annotations

import pytest

from rediacc_hooks import shellscan

R = "agent/reviews/0930-1/a.md"
# The input operand of the awk rows below. A program that may redirect (`shellscan._awk_may_redirect`) makes every word that is neither an option nor a program a landing, so each such row ends with it, and each row is the reader's WHOLE answer, in its order (review fd4eda1a.2).
A = ("/tmp/a", "option")


def _landings(cmd, name, **kwargs):
    """`output_landings` for the one run of `cmd` named `name`. A command that walks to no such run, or to two, is a broken case and not an empty answer."""
    runs = [run for run in shellscan.every_run(cmd) if run.name == name]
    assert len(runs) == 1, "%r walks to %d runs named %r" % (cmd, len(runs), name)
    return shellscan.output_landings(runs[0], **kwargs)


OPTION_FORMS = [
    # (label, command, run name, the pairs)
    ("a separate value", "sort -o %s /tmp/a" % R, "sort", [(R, "option")]),
    ("an attached value", "sort -o%s /tmp/a" % R, "sort", [(R, "option")]),
    ("a bundle ending in the letter", "sort -uo%s /tmp/a" % R, "sort", [(R, "option")]),
    ("a bundle, then the value", "sort -uo %s /tmp/a" % R, "sort", [(R, "option")]),
    ("a long option with =", "sort --output=%s /tmp/a" % R, "sort", [(R, "option")]),
    ("a long option, then the value", "sort --output %s /tmp/a" % R, "sort", [(R, "option")]),
    ("a unique prefix of the long option", "sort --out %s /tmp/a" % R, "sort", [(R, "option")]),
    ("the option after the operands", "sort /tmp/a -o %s" % R, "sort", [(R, "option")]),
    ("the option naming another file", "sort -o /tmp/out %s" % R, "sort", [("/tmp/out", "option")]),
    ("a key= form", "dd if=%s of=/tmp/out" % R, "dd", [("/tmp/out", "option")]),
    ("uniq's second operand", "uniq /tmp/a %s" % R, "uniq", [(R, "option")]),
    ("uniq's value option is no operand", "uniq -f 2 /tmp/a %s" % R, "uniq", [(R, "option")]),
    ("find -fprint", "find /tmp -name a -fprint %s" % R, "find", [(R, "option")]),
    ("find -fprintf", "find /tmp -fprintf %s '%%p'" % R, "find", [(R, "option")]),
    ("find -delete", "find agent/reviews -name x -delete", "find", [("agent/reviews", "option")]),
    ("sed's w command", "sed -n 'w %s' /tmp/a" % R, "sed", [(R, "option")]),
    ("sed's w command after an address", "sed -n '/x/,$w %s' /tmp/a" % R, "sed", [(R, "option")]),
    ("sed's w flag", "sed -n 's/a/b/gw %s' /tmp/a" % R, "sed", [(R, "option")]),
    ("sed -e", "sed -n -e p -e 'W %s' /tmp/a" % R, "sed", [(R, "option")]),
    ("an awk redirect", "awk '{print > \"%s\"}' /tmp/a" % R, "awk", [(R, "option"), A]),
    (
        "an awk pipe",
        "awk '{print | \"tee %s\"}' /tmp/a" % R,
        "awk",
        [("tee %s" % R, "option"), ("tee", "option"), (R, "option"), A],
    ),
    # Review fd4eda1a.1: a program that redirects into a literal elsewhere still lands on the operand it reads, since the rule does not follow where a print goes. The guard refuses it over a review file and allows it over any other (rows of test-block_review_file_edit.py).
    (
        "an awk redirect elsewhere, reading a record",
        "awk '{print > \"x\"}' %s" % R,
        "awk",
        [("x", "option"), (R, "option")],
    ),
    ("an awk redirect elsewhere", "awk '{print > \"x\"}' /tmp/a", "awk", [("x", "option"), A]),
    ("an awk comparison beside a print", "awk '$3 > 5 {print}' %s" % R, "awk", [(R, "option")]),
    # Review fd4eda1a.3, an OVER-READ the lexical rule accepts: this program prints nothing, and the letters `print` beside a `|` are read as a program that may redirect.
    ("over-read: print inside a regex", "awk '/print|x/' %s" % R, "awk", [(R, "option")]),
    (
        "an awk redirect through -v",
        "awk -v out=%s '{print > out}' /tmp/a" % R,
        "awk",
        # The print goes into a variable, so every word that is neither an option nor a program is a landing too (review 660ec7a0.1).
        [(R, "option"), ("out=%s" % R, "option"), ("/tmp/a", "option")],
    ),
    # In place, every word that is not an option may be a file gawk rewrites: the reading does not rest on which word is the program (review 906a4d56.1).
    (
        "gawk in place",
        "gawk -i inplace '{print}' %s" % R,
        "gawk",
        [("inplace", "option"), ("{print}", "option"), (R, "option")],
    ),
    # Review 906a4d56.1: gawk's -o, -p and -d take a value only attached, so the word after them is the program. Each yielded nothing before.
    (
        "gawk -p, then the program",
        "gawk -p '{print > \"%s\"}' /tmp/a" % R,
        "gawk",
        [(R, "option"), A],
    ),
    (
        "gawk -d, then the program",
        "gawk -d '{print > \"%s\"}' /tmp/a" % R,
        "gawk",
        [(R, "option"), A],
    ),
    (
        "gawk -o, then the program",
        "gawk -o '{print > \"%s\"}' /tmp/a" % R,
        "gawk",
        [(R, "option"), A],
    ),
    (
        "gawk --profile, then the program",
        "gawk --profile '{print > \"%s\"}' /tmp/a" % R,
        "gawk",
        [(R, "option"), A],
    ),
    ("gawk -d with its file attached", "gawk -d%s '{print}' /tmp/a" % R, "gawk", [(R, "option")]),
    (
        "gawk --dump-variables= with its file",
        "gawk --dump-variables=%s '{print}' /tmp/a" % R,
        "gawk",
        [(R, "option")],
    ),
    (
        "an attached value elsewhere is the only landing",
        "gawk -p/tmp/prof '{print $1}' %s" % R,
        "gawk",
        [("/tmp/prof", "option")],
    ),
    # Review 906a4d56.2: -W takes a separate word in gawk and mawk, and hands gawk a long option.
    (
        "gawk -W, then the program",
        "gawk -W lint '{print > \"%s\"}' /tmp/a" % R,
        "gawk",
        # The value of -W is a word that is neither an option nor a program, so it is listed with the operand.
        [(R, "option"), ("lint", "option"), A],
    ),
    (
        "mawk -W, then the program",
        "mawk -W interactive '{print > \"%s\"}' /tmp/a" % R,
        "mawk",
        [(R, "option"), ("interactive", "option"), A],
    ),
    (
        "gawk -W dump-variables=",
        "gawk -W dump-variables=%s '{print}' /tmp/a" % R,
        "gawk",
        [(R, "option")],
    ),
    # The sweep of the same class: an option value placed where the tool does not place it.
    (
        "awk writing beside FILENAME",
        "awk '{print > (FILENAME \".bak\")}' %s" % R,
        "awk",
        [(".bak", "option"), (R, "option")],
    ),
    ("xxd -ps is one flag", "xxd -ps /tmp/in %s" % R, "xxd", [(R, "option")]),
    ("xxd -len takes the next word", "xxd -len 4 /tmp/in %s" % R, "xxd", [(R, "option")]),
    (
        "tree hands -o a later word",
        "tree -Lo 2 %s agent" % R,
        "tree",
        [("2", "option"), (R, "option"), ("agent", "option")],
    ),
]

OPTION_CONTROLS = [
    # (label, command, run name): a listed command that only reads what it names.
    ("a plain reader", "cat %s" % R, "cat"),
    ("a reader with options", "grep -rn high agent/reviews/", "grep"),
    ("sort reading", "sort -u %s" % R, "sort"),
    ("-- ends sort's options", "sort -- -o %s" % R, "sort"),
    ("uniq with one operand", "uniq -c %s" % R, "uniq"),
    ("-- ends uniq's options", "uniq -- %s" % R, "uniq"),
    ("find walking the directory", "find agent/reviews -name '*.md' -print", "find"),
    ("sed printing a range", "sed -n 1,20p %s" % R, "sed"),
    ("sed substituting the path away", "sed 's|agent/reviews/||' /tmp/list", "sed"),
    ("sed with w in the pattern", "sed -n '/www\\/agent\\/reviews\\/x/p' /tmp/list", "sed"),
    ("sed reading a file", "sed '1r %s' /tmp/a" % R, "sed"),
    ("awk reading", "awk -F: '{print $2}' %s" % R, "awk"),
    ("awk comparing", "awk '$3 > 0' %s" % R, "awk"),
    ("awk printing the path", "awk '{print \"%s\"}' /tmp/a" % R, "awk"),
    ("awk printing FILENAME", "awk '{print FILENAME}' %s" % R, "awk"),
    ("awk splitting on a pipe", "awk -F'|' '{print $2}' %s" % R, "awk"),
    ("awk's own assignments are code", "awk '/^# /{p=0} /^# (a|b)/{p=1} p' %s" % R, "awk"),
    ("gawk -W, then a program that reads", "gawk -W lint '{print $1}' %s" % R, "gawk"),
    ("gawk -d, then a program that reads", "gawk -d '{print $1}' %s" % R, "gawk"),
    ("gawk -L, then a program that reads", "gawk -L '{print $1}' %s" % R, "gawk"),
    ("xxd -ps reading", "xxd -ps %s" % R, "xxd"),
    ("xxd with value options reading", "xxd -s 4 -l 16 %s" % R, "xxd"),
    ("xxd with an attached value reading", "xxd -l16 %s" % R, "xxd"),
    ("tree without -o", "tree -L 2 agent/reviews", "tree"),
    ("a kept verdict", "rm %s" % R, "rm"),
    ("a builtin's assignment", "export P=%s" % R, "export"),
]

UNREAD_FORMS = [
    # (label, command, run name, a pair it must hold)
    ("an operand", "touch %s" % R, "touch", (R, "unread")),
    ("a value after its option", "curl -o %s https://e.x/a" % R, "curl", (R, "unread")),
    ("an attached value", "curl -o%s https://e.x/a" % R, "curl", (R, "unread")),
    ("a bundle's tail", "tar -cf%s /tmp/a" % R, "tar", (R, "unread")),
    ("after the first =", "pandoc /tmp/a.md --output=%s" % R, "pandoc", (R, "unread")),
    ("after --", "prettier --write -- %s" % R, "prettier", (R, "unread")),
]


@pytest.mark.parametrize(
    ("_label", "cmd", "name", "want"), OPTION_FORMS, ids=[row[0] for row in OPTION_FORMS]
)
def test_a_listed_command_writes_through_its_own_spelling(_label, cmd, name, want):
    assert _landings(cmd, name) == want


MAY_REDIRECT = [
    # (program word, whether `_awk_may_redirect` answers yes)
    ('{print > "x"}', True),
    ("{print > ARGV[1]}", True),
    ('{printf "%s\\n", $1 | "sort"}', True),
    ('{system("date")}', True),
    ('{"date" | getline d}', True),
    ("$3 > 5 {print}", True),
    # The lexical over-reads (review fd4eda1a.3): neither program redirects, and each is read as one that may.
    ("/print|x/", True),
    ('$1 == "print" || $2 > 3', True),
    ("{print $1}", False),
    ("$3 > 5", False),
    ("/a|b/{p=1} p", False),
    ("{sprint = $1 > 2}", False),
    ("/tmp/a", False),
]


@pytest.mark.parametrize(("word", "want"), MAY_REDIRECT, ids=[row[0] for row in MAY_REDIRECT])
def test_whether_an_awk_word_may_redirect_is_lexical(word, want):
    assert shellscan._awk_may_redirect(word) is want


@pytest.mark.parametrize(
    ("_label", "cmd", "name"), OPTION_CONTROLS, ids=[row[0] for row in OPTION_CONTROLS]
)
def test_a_listed_command_that_only_reads_yields_nothing(_label, cmd, name):
    assert _landings(cmd, name) == []


@pytest.mark.parametrize(
    ("_label", "cmd", "name", "pair"), UNREAD_FORMS, ids=[row[0] for row in UNREAD_FORMS]
)
def test_every_word_of_an_unlisted_command_is_unread(_label, cmd, name, pair):
    assert pair in _landings(cmd, name)


def test_an_unlisted_command_yields_every_word_and_nothing_as_an_option():
    found = _landings("mytool --flag /tmp/a %s" % R, "mytool")
    assert found == [("--flag", "unread"), ("/tmp/a", "unread"), (R, "unread")]
    # The same words under a listed reader are not landings at all.
    assert _landings("cat --flag /tmp/a %s" % R, "cat") == []


def test_a_short_bundle_yields_each_tail():
    assert _landings("mytool -ab%s" % R, "mytool") == [
        ("-ab%s" % R, "unread"),
        *[(("b%s" % R)[k:], "unread") for k in range(len(R) + 1)],
    ]


def test_a_url_is_not_a_path():
    assert _landings("curl -o /tmp/out https://e.x/agent/reviews/a", "curl") == [
        ("-o", "unread"),
        ("/tmp/out", "unread"),
    ]
    assert _landings("sort -o https://e.x/agent/reviews/a /tmp/a", "sort") == []


def test_a_git_verb_is_parsed_after_its_global_options():
    assert _landings("git diff --output=%s HEAD~1" % R, "git") == [(R, "option")]
    assert _landings("git --no-pager -c a.b=c log --output %s -1" % R, "git") == [(R, "option")]
    # The global option's own value is not a landing, and a -C directory is where a relative output lands.
    assert _landings("git -C agent/reviews/0930-1 diff --output=a.md", "git") == [(R, "option")]
    assert _landings("git -C agent/reviews/0930-1 diff --stat", "git") == []
    assert _landings("git diff --output=/tmp/d -- agent/reviews/", "git") == [("/tmp/d", "option")]
    assert _landings("git log --oneline -- agent/reviews/", "git") == []
    assert _landings("git add -- %s" % R, "git") == []
    assert _landings("git checkout -- %s" % R, "git") == []


def test_an_unlisted_git_verb_is_unread():
    found = _landings("git format-patch -o agent/reviews/0930-1 -1", "git")
    assert ("agent/reviews/0930-1", "unread") in found
    assert all(how == "unread" for _word, how in found)


def test_exact_fed_words_complete_the_argv():
    """xargs appends: `echo F | xargs sort /tmp/a -o` runs `sort /tmp/a -o F`, and `echo F | xargs sort` reads F."""
    assert _landings("echo %s | xargs sort /tmp/a -o" % R, "sort") == [(R, "option")]
    assert _landings("echo %s | xargs sort" % R, "sort") == []
    assert _landings("echo %s | xargs sort -o /tmp/out" % R, "sort") == [("/tmp/out", "option")]
    assert _landings("echo %s | xargs uniq /tmp/a" % R, "uniq") == [(R, "option")]
    assert _landings("echo %s | xargs uniq" % R, "uniq") == []


def test_a_fed_word_takes_its_marker_place():
    cmd = "echo %s | xargs -I{} sort --output={} /tmp/a" % R
    assert _landings(cmd, "sort") == [("{}", "option"), (R, "option")]
    assert _landings("echo %s | xargs -I{} sort {}" % R, "sort") == []
    # Another marker, and a marker inside a longer word.
    cmd = "echo 0930-1 | xargs -I @ sort -o agent/reviews/@/a.md /tmp/a"
    assert ("agent/reviews/0930-1/a.md", "option") in _landings(cmd, "sort")


def test_an_inexact_feed_lands_only_where_the_argv_leaves_room():
    """`-n1` runs the command once per word, so every fed word in turn is the value of a write option left waiting, and none is when the option already has its value."""
    assert _landings("echo /tmp/x %s | xargs -n1 sort -o" % R, "sort") == [
        ("/tmp/x", "option"),
        (R, "option"),
    ]
    assert _landings("echo /tmp/x %s | xargs -n1 sort -o /tmp/out" % R, "sort") == [
        ("/tmp/out", "option")
    ]
    assert _landings("echo /tmp/x %s | xargs -n1 sort" % R, "sort") == []
    assert (R, "option") in _landings("git ls-files | xargs -n1 uniq /tmp/a %s" % R, "uniq")
    assert ("agent/reviews", "option") in _landings("find agent/reviews | xargs sort -o", "sort")


def test_an_unlisted_command_is_fed_every_word():
    assert (R, "unread") in _landings("echo %s | xargs touch" % R, "touch")
    assert ("agent/reviews/0930-1/x.md", "unread") in _landings(
        "echo 0930-1 | xargs -I{} touch agent/reviews/{}/x.md", "touch"
    )


def test_find_exec_braces_stand_for_the_starting_points():
    cmd = r"find agent/reviews -name '*.md' -exec sort -o {} /tmp/a \;"
    assert _landings(cmd, "sort") == [("agent/reviews", "option")]
    cmd = r"find agent/reviews -name '*.md' -exec sort -o /tmp/out {} \;"
    assert _landings(cmd, "sort") == [("/tmp/out", "option")]
    cmd = r"find agent/reviews -name '*.md' -exec touch {} \;"
    assert ("agent/reviews", "unread") in _landings(cmd, "touch")
    cmd = r"find agent/reviews -name '*.md' -exec wc -l {} \;"
    assert _landings(cmd, "wc") == []


def test_argv_replaces_the_runs_own_words():
    """A caller passes the expanded words (`_Run.xargv`) to read `$F` as bash expands it."""
    (run,) = [r for r in shellscan.every_run("F=%s; sort -o $F /tmp/a" % R) if r.name == "sort"]
    assert shellscan.output_landings(run) == [("$F", "option")]
    assert shellscan.output_landings(run, run.xargv) == [(R, "option")]


JUDGED_ELSEWHERE = [
    ("a copier", "cp /tmp/a %s" % R, "cp"),
    ("tee", "echo x | tee %s" % R, "tee"),
    ("truncate", "truncate -s 0 %s" % R, "truncate"),
    ("an interpreter", "python3 /tmp/s.py %s" % R, "python3"),
    ("a shell handed -c", "bash -c 'cat /x/%s'" % R, "bash"),
    ("npx, whose command is a run of its own", "npx prettier --write %s" % R, "npx"),
]


@pytest.mark.parametrize(
    ("_label", "cmd", "name"), JUDGED_ELSEWHERE, ids=[row[0] for row in JUDGED_ELSEWHERE]
)
def test_a_command_another_reading_judges_yields_nothing(_label, cmd, name):
    assert _landings(cmd, name) == []


def test_what_a_skipped_launcher_starts_is_still_read():
    """The control for the skip above: `npx` yields nothing because the command it starts is a run of its own, and a shell with no `-c` is an unlisted command."""
    assert (R, "unread") in _landings("npx prettier --write %s" % R, "prettier")
    assert (R, "unread") in _landings("bash /tmp/s.sh %s" % R, "bash")


def test_the_table_lists_every_command_the_rows_above_call_a_reader():
    """A reader dropped from the table turns its row above from [] into unread words; this names the table as the cause when one does."""
    readers = {name for _label, _cmd, name in OPTION_CONTROLS}
    assert len(readers) >= 8
    missing = sorted(name for name in readers if name not in shellscan._NON_WRITERS)
    assert not missing, "not in shellscan._NON_WRITERS: %s" % ", ".join(missing)
