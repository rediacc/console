"""A pre-edit guard judges where a write LANDS, resolved the way the kernel resolves it: symlinks first, then `..` (review 9c6817f3.1-.5, .8).

THE DEFECT. Four guards each carried a copy of `_landing` that ran `normpath` before `realpath`. `normpath` removes `x/..` as text, so with `out/l` a symlink to a subdirectory of a guarded directory, `out/l/../FILE` was judged at `out/FILE` (out of scope, allowed) while the kernel wrote `<guarded>/FILE`. The other direction was wrong too: `<guarded>/esc/../FILE`, with `esc` a symlink out of the tree, was refused for a write that lands outside. `hookio.landing` is now the one reading, and every case below builds real symlinks.
"""

from __future__ import annotations

import json
import os
import pathlib
import typing

import pytest

from rediacc_hooks import dispatch, guards, hookio, shellscan


class _Landing(typing.NamedTuple):
    absolute: str
    judged: str
    shown: str


def _land(path, cwd, root):
    return _Landing(*hookio.landing(path, cwd, root))


def _world(tmp_path, guarded):
    """`guarded/sub`, a link `out/l` INTO it, and a link `guarded/esc` OUT of it."""
    root = tmp_path / "w"
    (root / guarded / "sub").mkdir(parents=True)
    (root / "out").mkdir()
    (root / "out" / "l").symlink_to(root / guarded / "sub", target_is_directory=True)
    (root / guarded / "esc").symlink_to(root / "out", target_is_directory=True)
    return root


def _write(stem, path, content, cwd):
    payload = {
        "tool_name": "Write",
        "cwd": str(cwd),
        "tool_input": {"file_path": str(path), "content": content},
    }
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    rc, _out, err = dispatch.run_one(stem, json.dumps(payload), env=env)
    return rc, err


def test_landing_resolves_the_link_before_the_dotdot(tmp_path):
    root = _world(tmp_path, "g")
    inward = _land(str(root / "out" / "l" / ".." / "f.md"), str(root), str(root))
    assert inward.absolute == str(root / "g" / "f.md")
    assert inward.judged == "g/f.md"
    assert "lands at %s" % (root / "g" / "f.md") in inward.shown
    outward = _land("g/esc/../f.md", str(root), str(root))
    assert outward.absolute == str(root / "f.md")
    assert outward.judged == "f.md"
    plain = _land("g/f.md", str(root), str(root))
    assert (plain.judged, plain.shown) == ("g/f.md", "g/f.md")
    outside = _land("/nonexistent-landing/x.md", str(root), str(root))
    assert outside.judged == "/nonexistent-landing/x.md"


def test_landing_never_raises_on_a_path_the_os_refuses(tmp_path):
    """Review 9c6817f3.5: `realpath` raises ValueError on an embedded NUL; such a path cannot be written either, so it is judged as typed."""
    got = _land("agent/plans/PLAN-a\x00.md", str(tmp_path), str(tmp_path))
    assert got.judged == "agent/plans/PLAN-a\x00.md"
    # Review 3c0094e0.2: never left relative, or a caller reads the hook process's directory.
    assert got.absolute == str(tmp_path / "agent/plans/PLAN-a\x00.md")
    assert _land("", str(tmp_path), str(tmp_path)).judged == ""


def _record_world(root):
    module = guards.load("block_compacted_plan_edit")
    (root / "agent" / "PLAN-a.md").write_text(module.RECORD_TEXT, encoding="utf-8")
    return "PLAN-a.md", "# rewritten\n"


def _roundlog_world(root):
    (root / "reports" / "pr-babysit-0831-1.md").write_text(
        "# wave\n\n## STATUS\n\nx\n", encoding="utf-8"
    )
    return "pr-babysit-0831-1.md", "x"


def _tasks_world(_root):
    return "PLAN-new-prose.md", guards.load("block_plan_without_tasks").PROSE_PLAN


def _state_world(_root):
    return "STATE.md", "tiny"


CASES = [
    ("block_agent_state_shape", "agent/s1", _state_world),
    ("block_compacted_plan_edit", "agent", _record_world),
    ("block_plan_without_tasks", "agent", _tasks_world),
    ("block_roundlog_write", "reports", _roundlog_world),
]


@pytest.mark.parametrize(("stem", "guarded", "build"), CASES, ids=[c[0] for c in CASES])
def test_a_link_then_dotdot_is_judged_where_the_kernel_writes(tmp_path, stem, guarded, build):
    root = _world(tmp_path, guarded)
    name, content = build(root)
    direct = root / guarded / name
    rc, err = _write(stem, direct, content, root)
    assert rc == 2, "the control on the control: the direct write must be refused (%s)" % err
    # INTO the guarded directory: lexically `out/<name>`, really `<guarded>/<name>`.
    inward = pathlib.Path(str(root / "out" / "l") + "/../" + name)
    assert os.path.realpath(inward) == str(direct)
    rc, err = _write(stem, inward, content, root)
    assert rc == 2, "a write that lands in the guarded directory was allowed"
    # OUT of it: lexically `<guarded>/<name>`, really `<root>/<name>`.
    outward = pathlib.Path(str(root / guarded / "esc") + "/../" + name)
    assert os.path.realpath(outward) == str(root / name)
    rc, err = _write(stem, outward, content, root)
    assert rc == 0, "a write that lands outside the guarded directory was refused: %s" % err


def test_the_workflow_guard_judges_a_link_then_dotdot_where_it_lands(tmp_path):
    """Found by the extended sweep: block_inline_workflow_run matched its glob against the typed text. The payload is the guard's own first refused edge case, moved into a scratch world."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    case = _refused_case("block_inline_workflow_run", env)
    root = _world(tmp_path, ".github/workflows")

    def answer(path):
        spec = json.loads(json.dumps(case))
        spec["tool_input"]["file_path"] = str(path)
        spec["cwd"] = str(root)
        rc, _out, err = dispatch.run_one("block_inline_workflow_run", json.dumps(spec), env=env)
        return rc, err

    assert answer(root / ".github" / "workflows" / "ci.yml")[0] == 2
    inward = str(root / "out" / "l") + "/../ci.yml"
    rc, err = answer(inward)
    assert rc == 2
    # Review 0067b4c2.3: the refusal names what was typed AND where it lands, never the landing alone.
    assert inward in err
    assert "lands at %s" % (root / ".github" / "workflows" / "ci.yml") in err
    assert answer(str(root / ".github" / "workflows" / "esc") + "/../ci.yml")[0] == 0


def _refused_case(stem, env):
    """The guard's own first refused edge case; an empty answer would make the caller prove nothing."""
    module = guards.load(stem)
    refused = [
        spec
        for _label, spec in module.EDGE_CASES
        if isinstance(spec, dict)
        and (spec.get("tool_input") or {}).get("file_path")
        and dispatch.run_one(stem, json.dumps(spec), env=env)[0] == 2
    ]
    assert refused, "%s refuses none of its own edge cases; this test would prove nothing" % stem
    return refused[0]


def test_the_inline_python_guard_judges_the_suffix_of_the_landing(tmp_path):
    """Review 0067b4c2.1: the suffix that decides is the file's the edit lands in. A `.txt` link to a script is a script (allowed before the landing was read), and a `.ts` link to a text file is text."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_PROJECT_DIR", "REDIACC_ALLOW_INLINE_PYTHON")
    }
    case = _refused_case("block_inline_python", env)
    (tmp_path / "real.ts").write_text("export {}\n", encoding="utf-8")
    (tmp_path / "real.txt").write_text("notes\n", encoding="utf-8")
    (tmp_path / "notes.txt").symlink_to(tmp_path / "real.ts")
    (tmp_path / "alias.ts").symlink_to(tmp_path / "real.txt")

    def verdict(name):
        spec = json.loads(json.dumps(case))
        spec["tool_input"]["file_path"] = str(tmp_path / name)
        spec["cwd"] = str(tmp_path)
        return dispatch.run_one("block_inline_python", json.dumps(spec), env=env)[0]

    assert verdict("real.ts") == 2, "the control on the control: the direct edit must be refused"
    assert verdict("real.txt") == 0
    assert verdict("notes.txt") == 2, (
        "an edit that lands in a script through a .txt link was allowed"
    )
    assert verdict("alias.ts") == 0, (
        "an edit that lands in a text file through a .ts link was refused"
    )


def test_a_writer_with_no_expanded_argv_is_unknown_not_verbatim():
    """Review 094dea3b.6: `writer_text` never falls back to the typed words. Every walked run carries an expanded argv; one built without it is unknown."""
    cmd = "echo plain > /tmp/zz-landing-probe"
    run = next(r for r in shellscan.every_run(cmd) if r.name == "echo")
    assert run.xargv is not None
    assert shellscan.writer_text(run, cmd) == "plain"
    run.xargv = None
    try:
        assert shellscan.writer_text(run, cmd) is None
    finally:
        shellscan._ANALYSIS_CACHE.clear()


def _fed(cmd, name):
    run = next(r for r in shellscan.every_run(cmd) if r.name == name)
    return shellscan.stdin_text(run, cmd), shellscan.writer_text(run, cmd)


def test_stdin_text_is_the_feed_as_bash_hands_it_over():
    """Review 7837d22e.1: an unquoted heredoc is expanded with what the walk resolved, a quoted one is literal, and a part nobody can expand leaves the whole text unknown. Each expectation is what bash 5 prints for the same command."""
    assert _fed("M=x; cat <<EOF\na $M ${M}b\nEOF", "cat") == ("a x xb\n", "a x xb\n")
    assert _fed("M=x; cat <<'EOF'\na $M\nEOF", "cat")[0] == "a $M\n"
    assert _fed("M=x; cat <<EOF\na \\$M \\\\ \\`\nEOF", "cat")[0] == "a $M \\ `\n"
    assert _fed("cat <<EOF\none \\\ntwo\nEOF", "cat")[0] == "one two\n"
    assert _fed("cat <<EOF\ncosts 5$ a go\nEOF", "cat")[0] == "costs 5$ a go\n"
    # Unknown: a name only the session knows, a command substitution, a backtick, an operator expansion, a positional.
    for body in ("$HOME_OF_NOBODY", "$(date)", "`date`", "${M:-x}", "$1"):
        assert _fed("M=x; cat <<EOF\n%s\nEOF" % body, "cat") == (None, None), body
    # A `$` outside a heredoc is not expanded here: a here-string and the words of the stage in front.
    assert _fed('M=x; cat <<< "$M"', "cat")[0] is None
    assert _fed('M=x; echo "$M" | cat', "cat")[0] is None
    assert _fed("echo plain | cat", "cat")[0] == "echo plain"
