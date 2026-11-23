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
]


@pytest.mark.parametrize(("label", "cmd"), SILENT, ids=[c[0] for c in SILENT])
def test_writes_is_silent(tmp_path, label, cmd):
    assert _hows(cmd, tmp_path) == [], label


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
