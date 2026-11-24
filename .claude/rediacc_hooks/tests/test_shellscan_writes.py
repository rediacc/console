"""`shellscan.writes` and `hookio.Event.writes`: the one answer to "does this command write P?" (PLAN-tooling-code-reduction CR5, D5).

Every `how` has a case that must fire, and the reading shapes that must NOT (a quoted arrow, prose in a heredoc, a file only read) have controls beside them: a writes() that listed every word would pass the first half alone.
"""

import json

import pytest

from rediacc_hooks import hookio, shellscan


def _hows(cmd, cwd):
    return [(p.replace(str(cwd), "<CWD>"), how) for p, how in shellscan.writes(cmd, str(cwd))]


FIRES = [
    ("a redirect", "echo hi > out.txt", ("<CWD>/out.txt", "redirect")),
    ("an append", "echo hi >> log.txt", ("<CWD>/log.txt", "append")),
    ("a redirect after a cd", "cd sub && echo hi > x.md", ("<CWD>/sub/x.md", "redirect")),
    ("an expanded redirect target", "F=y.md; echo hi > $F", ("<CWD>/y.md", "redirect")),
    ("tee", "printf x | tee -a t.txt", ("<CWD>/t.txt", "tee")),
    ("sed in place", "sed -i 's/a/b/' s.py", ("<CWD>/s.py", "in-place")),
    ("perl in place", "perl -pi -e 's/a/b/' p.pl", ("<CWD>/p.pl", "in-place")),
    ("a copy", "cp /etc/hostname c.txt", ("<CWD>/c.txt", "copy")),
    ("a listed output option", "sort -o sorted.txt in.txt", ("<CWD>/sorted.txt", "option")),
    ("an expanded output option", "F=e.txt; sort -o $F in.txt", ("<CWD>/e.txt", "option")),
    ("an expanded word of an unlisted command", "F=u.txt; touch $F", ("<CWD>/u.txt", "unread")),
    ("an xargs-fed tee", "echo f.txt | xargs tee", ("<CWD>/f.txt", "tee")),
    ("an xargs-fed in-place edit", "echo i.py | xargs sed -i s/a/b/", ("<CWD>/i.py", "in-place")),
    ("a git pathspec", "git checkout -- g.py", ("<CWD>/g.py", "git")),
    ("a git -C pathspec", "git -C repo restore h.py", ("<CWD>/repo/h.py", "git")),
    (
        "a python program's write target",
        "python3 -c \"open('w.json', 'w').write('{}')\"",
        ("<CWD>/w.json", "interpreter"),
    ),
    (
        "a python write target through a name",
        "python3 - <<'EOF'\nimport pathlib\nP = 'n.txt'\npathlib.Path(P).write_text('x')\nEOF",
        ("<CWD>/n.txt", "interpreter"),
    ),
    (
        "a find -exec in-place edit lands under find's start",
        "find sub -name '*.py' -exec sed -i 's/a/b/' {} +",
        ("<CWD>/sub", "in-place"),
    ),
    ("dd's of= is an output key", "dd if=/dev/zero of=z.bin count=1", ("<CWD>/z.bin", "option")),
    ("truncate", "truncate -s 0 t.log", ("<CWD>/t.log", "truncate")),
    ("an expanded truncate operand", "F=x.log; truncate -s 0 $F", ("<CWD>/x.log", "truncate")),
    ("an rm operand", "rm -f gone.txt", ("<CWD>/gone.txt", "remove")),
    ("an xargs-fed rm", "echo fed.txt | xargs rm", ("<CWD>/fed.txt", "remove")),
    ("a find -exec rm lands under find's start", "find sub -exec rm {} +", ("<CWD>/sub", "remove")),
]


@pytest.mark.parametrize(("label", "cmd", "want"), FIRES, ids=[c[0] for c in FIRES])
def test_writes_fires(tmp_path, label, cmd, want):
    (tmp_path / "sub").mkdir()
    (tmp_path / "repo").mkdir()
    got = _hows(cmd, tmp_path)
    assert want in got, (label, got)


SILENT = [
    ("an echo to the terminal", "echo hi"),
    ("a quoted arrow is not a redirect", "echo 'a > b.txt'"),
    ("a file only read", "cat a.txt"),
    ("a search", "grep -rn needle src/"),
    ("a descriptor duplication", "make 2>&1"),
    ("the null device", "echo hi > /dev/null"),
    ("a heredoc's prose naming a path", "cat <<'EOF'\nthen run: echo x > q.txt\nEOF"),
    ("git add writes the index, not the file", "git add a.py"),
    ("a python program that only reads", "python3 -c \"print(open('r.txt').read())\""),
    ("an rm only echoed", "echo rm -f gone.txt"),
    ("an rm quoted in a search", "grep -rn 'rm -f gone.txt' src/"),
]


@pytest.mark.parametrize(("label", "cmd"), SILENT, ids=[c[0] for c in SILENT])
def test_writes_is_silent(tmp_path, label, cmd):
    assert _hows(cmd, tmp_path) == [], label


def test_truncate_reads_its_size_and_reference_as_values_not_files(tmp_path):
    """SILENT CONTROL for the truncate reading: `-s SIZE` and `-r REF` are values; only the operand is resized."""
    got = _hows("truncate -r ref.txt -s 0 t.txt", tmp_path)
    assert got == [("<CWD>/t.txt", "truncate")], got


def _records(cmd, cwd):
    return [
        (w.path.replace(str(cwd), "<CWD>"), w.how, w.word, w.word_index, w.append)
        for w in shellscan.write_records(cmd, str(cwd))
    ]


RECORDS = [
    (
        "a redirect is no word of the run",
        "echo hi > o.txt",
        ("<CWD>/o.txt", "redirect", "o.txt", None, False),
    ),
    (
        "an append keeps the file",
        "echo hi >> o.txt",
        ("<CWD>/o.txt", "append", "o.txt", None, True),
    ),
    ("tee -a keeps the file", "printf x | tee -a t.txt", ("<CWD>/t.txt", "tee", "t.txt", 1, True)),
    (
        "tee --append keeps the file",
        "printf x | tee --append t.txt",
        ("<CWD>/t.txt", "tee", "t.txt", 1, True),
    ),
    ("a plain tee replaces it", "printf x | tee t.txt", ("<CWD>/t.txt", "tee", "t.txt", 0, False)),
    (
        "a tee bundle holding a keeps the file",
        "printf x | tee -ia t.txt",
        ("<CWD>/t.txt", "tee", "t.txt", 1, True),
    ),
    (
        "the a in --output-error=warn is no append",
        "printf x | tee --output-error=warn t.txt",
        ("<CWD>/t.txt", "tee", "t.txt", 1, False),
    ),
    (
        "the typed word of an expanded redirect",
        "F=y.md; echo hi > $F",
        ("<CWD>/$F", "redirect", "$F", None, False),
    ),
    (
        "the expanded word of an expanded redirect",
        "F=y.md; echo hi > $F",
        ("<CWD>/y.md", "redirect", "y.md", None, False),
    ),
    (
        "an rm operand carries its argv index",
        "rm -f a.txt b.txt",
        ("<CWD>/b.txt", "remove", "b.txt", 2, False),
    ),
    (
        "dd of= is indexed at the operand carrying it",
        "dd if=a of=z.bin",
        ("<CWD>/z.bin", "option", "z.bin", 1, False),
    ),
    (
        "a word placed under the run's cd keeps its typed word",
        "cd sub && rm x.md",
        ("<CWD>/sub/x.md", "remove", "x.md", 0, False),
    ),
]


@pytest.mark.parametrize(("label", "cmd", "want"), RECORDS, ids=[c[0] for c in RECORDS])
def test_write_records_carry_word_index_and_append(tmp_path, label, cmd, want):
    (tmp_path / "sub").mkdir()
    got = _records(cmd, tmp_path)
    assert want in got, (label, got)


def test_writes_is_the_pair_view_of_write_records(tmp_path):
    """`writes` is derived, never a second walk: the pairs of `write_records`, each once, in order. A typed and an expanded word landing on one path are two records and one pair."""
    cmd = "F=a.txt; echo x > a.txt; echo y > $F; rm a.txt; printf z | tee -a a.txt"
    records = shellscan.write_records(cmd, str(tmp_path))
    pairs = shellscan.writes(cmd, str(tmp_path))
    want = []
    for w in records:
        if (w.path, w.how) not in want:
            want.append((w.path, w.how))
    assert pairs == want
    assert len(records) > len(pairs)


def test_an_unreadable_program_is_unknown_not_silent(tmp_path):
    """Unknown is never folded into "writes nothing": a program fetched from a URL cannot be read, so it is reported as an unknown write."""
    cmd = "deno run https://example.invalid/gen.ts"
    assert ("", "unknown") in shellscan.writes(cmd, str(tmp_path))


def test_an_unlisted_command_is_unread_so_its_words_count(tmp_path):
    """A command the tables do not list may write any word it is handed; writes() keeps it (the caller decides), it never drops it as a read."""
    got = _hows("frobnicate --out z.bin", tmp_path)
    assert ("<CWD>/z.bin", "unread") in got


def _event(cmd, cwd):
    return hookio.Event(json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd)}))


def test_event_writes_parses_once_per_event(tmp_path, monkeypatch):
    """The cache: a guard that asks twice pays once. Without it the count is 2."""
    calls = []
    real = shellscan.writes

    def counting(cmd, cwd):
        calls.append(cmd)
        return real(cmd, cwd)

    monkeypatch.setattr(shellscan, "writes", counting)
    ev = _event("echo hi > a.txt", tmp_path)
    first = ev.writes()
    second = ev.writes()
    assert first == second == [(str(tmp_path / "a.txt"), "redirect")]
    assert len(calls) == 1


def test_a_new_event_reads_the_disk_again(tmp_path, monkeypatch):
    """SILENT CONTROL for the cache: it is per Event, never per command text. `writes` reads the disk (a copy into a directory, a script by path), so two events with the same command must each compute, or a long-lived process would answer from a stale world."""
    calls = []
    real = shellscan.writes

    def counting(cmd, cwd):
        calls.append(cmd)
        return real(cmd, cwd)

    monkeypatch.setattr(shellscan, "writes", counting)
    cmd = "cp /etc/hostname d"
    assert _event(cmd, tmp_path).writes() == [(str(tmp_path / "d"), "copy")]
    (tmp_path / "d").mkdir()
    assert _event(cmd, tmp_path).writes() == [(str(tmp_path / "d" / "hostname"), "copy")]
    assert len(calls) == 2


def test_event_writes_with_no_command_is_empty(tmp_path):
    ev = hookio.Event(json.dumps({"tool_input": {"file_path": "x"}, "cwd": str(tmp_path)}))
    assert ev.writes() == []
    assert shellscan.event_write_records(ev) == []


def test_event_write_records_walks_once_per_event(tmp_path, monkeypatch):
    """The record cache: a guard that asks twice pays once, and a new Event walks again (the records read the disk, as `Event.writes` does). Without the hold the count is 3."""
    calls = []
    real = shellscan.write_records

    def counting(cmd, cwd):
        calls.append(cmd)
        return real(cmd, cwd)

    monkeypatch.setattr(shellscan, "write_records", counting)
    ev = _event("rm -f a.txt", tmp_path)
    first = shellscan.event_write_records(ev)
    assert [(w.path, w.how, w.word) for w in first] == [
        (str(tmp_path / "a.txt"), "remove", "a.txt")
    ]
    assert shellscan.event_write_records(ev) is first
    assert len(calls) == 1
    shellscan.event_write_records(_event("rm -f a.txt", tmp_path))
    assert len(calls) == 2


def _run_of(cmd, name):
    return next(r for r in shellscan.every_run(cmd) if r.name == name)


def _word_writes(run, words, cwd, fed=()):
    return shellscan.run_word_writes(run, words, cwd, fed)


def test_run_word_writes_reads_the_reading_it_is_handed(tmp_path):
    """`run_word_writes` reads the words it is handed, not the run's own: a guard's reading of a word the walk could not expand (`$D` read as `sub`) is asked of it the way the typed and the expanded words are."""
    run = _run_of("tee $D/y.md", "tee")
    assert _word_writes(run, ["sub/y.md"], str(tmp_path)) == [("sub/y.md", "tee", False)]
    assert _word_writes(run, list(run.argv), str(tmp_path)) == [("$D/y.md", "tee", False)]


def test_run_word_writes_without_a_directory_reads_a_copy_by_its_destination(tmp_path):
    """`cwd` None (a command a program hands to a shell, which runs wherever that program does) reads a copy's destination word as typed; with `cwd` known it is placed the way the tool places it, inside a destination that is a directory."""
    (tmp_path / "d").mkdir()
    run = _run_of("cp /etc/hostname d", "cp")
    assert _word_writes(run, list(run.argv), None) == [("d", "copy", False)]
    assert _word_writes(run, list(run.argv), str(tmp_path)) == [
        (str(tmp_path / "d" / "hostname"), "copy", False)
    ]


def test_run_word_writes_adds_fed_words_to_operands_only(tmp_path):
    """`fed` words arrive as operands: a tee writes them, while a copy's destination is its own parse and does not take them (the SILENT half)."""
    tee = _run_of("tee a.txt", "tee")
    assert ("fed.md", "tee", False) in _word_writes(tee, list(tee.argv), str(tmp_path), ("fed.md",))
    cp = _run_of("cp /etc/hostname c.txt", "cp")
    got = _word_writes(cp, list(cp.argv), str(tmp_path), ("fed.md",))
    assert got, "the copy itself is read"
    assert all(w != "fed.md" for w, _how, _a in got), got


def test_an_in_place_script_is_not_a_file_it_writes(tmp_path):
    """SILENT CONTROL for the in-place reading: the sed script is the program, never an operand, so a script whose text reads like a path (`docs/*/*/f.md`) lands nowhere. The edited file still does."""
    got = _hows("sed -i 's#docs/*/*/f.md#x#' notes.md", tmp_path)
    assert got == [("<CWD>/notes.md", "in-place")], got


def test_a_copy_is_listed_as_typed_and_as_expanded(tmp_path):
    """A copy's destination is read over the typed and the expanded words, as every other word reading is: `F=c.txt; cp x $F` lands on `c.txt`, and the typed `$F` is a record of its own."""
    got = _hows("F=c.txt; cp /etc/hostname $F", tmp_path)
    assert ("<CWD>/c.txt", "copy") in got, got
    assert ("<CWD>/$F", "copy") in got, got


def test_a_word_the_walk_cannot_expand_is_an_unknown_record(tmp_path):
    """Unknown is never dropped: `rm "$D"x.txt` with D unknown removes a file no path here names, so its expanded word is an "unknown" record (path "", the word with its unexpanded part marked, the argv index kept). Before CR5 step 2 it was left out."""
    got = [
        (w.path, w.how, w.word, w.word_index)
        for w in shellscan.write_records('rm "$D"x.txt', str(tmp_path))
        if w.how == "unknown"
    ]
    assert got == [("", "unknown", shellscan._UNRESOLVED + "x.txt", 0)], got


def test_an_expanded_word_is_no_unknown_record(tmp_path):
    """SILENT CONTROL: a word the walk expands is a record of its reading, never an unknown one."""
    records = shellscan.write_records("D=sub; rm $D/x.txt", str(tmp_path))
    assert [w.how for w in records] == ["remove", "remove"], records


def test_a_git_pathspec_is_read_as_typed_too(tmp_path):
    """A git pathspec is read over the typed and the expanded words, as every other word reading is: the typed `$(echo d)/g.py` keeps the substitution's text, which the expanded word (unknown) has lost."""
    got = [
        (w.how, w.word)
        for w in shellscan.write_records("git restore $(echo d)/g.py", str(tmp_path))
    ]
    assert ("git", "$(echo d)/g.py") in got, got
    assert ("unknown", shellscan._UNRESOLVED + "/g.py") in got, got


_PROTECTED = __import__("rediacc_hooks.guards.block_protected_files", fromlist=["_"])


@pytest.mark.parametrize(
    ("cmd", "refused"),
    [
        ('rm "$D"settings*', True),
        ('git rm "$D"settings.json', True),
        ('rm "$D"x.txt', False),
    ],
)
def test_protected_files_judges_an_unknown_word_as_a_pattern(tmp_path, cmd, refused):
    """block_protected_files reads its operands from the records, and an unknown record is load-bearing: the typed `"$D"settings*` is `$Dsettings*` after quote removal (a variable named `Dsettings`), so only the unknown record keeps the boundary bash sees (review 094dea3b.4). The plant drops the unknown records and the refusals turn allowed; the allowed row stays allowed either way."""
    records = shellscan.write_records(cmd, str(tmp_path))
    assert _PROTECTED.names_by_run(cmd, str(tmp_path), records) is refused
    dropped = [w for w in records if w.how != "unknown"]
    assert _PROTECTED.names_by_run(cmd, str(tmp_path), dropped) is False


@pytest.mark.parametrize(
    ("cmd", "refused"),
    [
        ("find . -name '*.pyc' -exec rm -rf {} +", False),
        ("find . -name x.tmp | xargs rm -rf", False),
        ("rm -rf .claude", True),
        ("git -C . restore .claude/settings.json", True),
    ],
)
def test_protected_files_takes_only_the_words_a_run_holds(cmd, refused):
    """A find start in a `{}`'s place and a word xargs feeds are records (`write_records` over-reads them on purpose) but no operand of the rm: the find removes what it matched, and the feed is `fed_by_stdin`'s, read from its own text. Taking them refused both innocent cleanups from the repository root (measured while moving the guard onto the records). The refusals are the controls: a recursive rm of a directory holding a protected file, and a git pathspec joined onto its `-C` (no word of the run, still taken)."""
    root = str(hookio.repo_root())
    assert _PROTECTED.names_by_run(cmd, root) is refused
