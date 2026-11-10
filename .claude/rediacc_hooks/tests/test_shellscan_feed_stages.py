"""`_Run.feed_stages`: the feed one source at a time, nearest last, so a reader can find the stage that produces a command's input (#3661517d)."""

from rediacc_hooks import shellscan
from rediacc_hooks.shellscan import FeedStage


def _stages(cmd, name):
    """The `feed_stages` of the one run named `name` in `cmd`."""
    found = [r for r in shellscan.every_run(cmd) if r.name == name]
    assert len(found) == 1, [r.name for r in shellscan.every_run(cmd)]
    return found[0].feed_stages


def _stage(text):
    return FeedStage("stage", text)


def test_each_pipeline_stage_is_its_own_entry_nearest_last():
    got = _stages("grep -H x F | cut -d: -f1 | xargs sed -i s/a/b/", "sed")
    assert got == (_stage("grep -H x F"), _stage("cut -d: -f1"))


def test_the_flat_feed_is_unchanged():
    run = next(
        r for r in shellscan.every_run("grep -H x F | cut -d: -f1 | xargs rm") if r.name == "rm"
    )
    assert run.feed == "grep -H x F cut -d: -f1"


def test_the_first_stage_and_a_lone_command_are_fed_nothing():
    assert _stages("grep -H x F | cut -d: -f1", "grep") == ()
    assert _stages("ls", "ls") == ()


def test_a_stage_keeps_its_words_as_typed():
    got = _stages("grep -rl 'a b' \"$D\" $(echo agent) | xargs rm", "rm")
    assert got == (_stage("grep -rl 'a b' \"$D\" $(echo agent)"),)


def test_a_stage_lexes_back_into_its_own_command():
    (stage,) = _stages("grep -rl 'a b' agent/ 2>/dev/null | xargs rm", "rm")
    (run,) = list(shellscan.every_run(stage.text))
    assert (run.name, run.argv) == ("grep", ["-rl", "a b", "agent/"])


def test_a_subshell_keeps_its_separators_and_its_cd():
    (stage,) = _stages("(cd agent && grep -rl x .) | xargs rm", "rm")
    assert stage == _stage("( cd agent && grep -rl x . )")
    grep = [r for r in shellscan.every_run(stage.text) if r.name == "grep"]
    assert [r.cwd for r in grep] == ["agent"]


def test_a_brace_group_lexes_back():
    assert _stages("{ echo a; grep -rl x agent/; } | xargs rm", "rm") == (
        _stage("{ echo a ; grep -rl x agent/; }"),
    )
    assert _stages("{ a & } | xargs rm", "rm") == (_stage("{ a & }"),)
    names = [r.name for r in shellscan.every_run("{ echo a ; grep -rl x agent/; }")]
    assert names == ["echo", "grep"]


def test_a_here_string_and_a_heredoc_are_data_and_nearest():
    assert _stages("grep -rl x agent/ | xargs rm <<< README.md", "rm") == (
        _stage("grep -rl x agent/"),
        FeedStage("data", "README.md"),
    )
    assert _stages("xargs rm <<EOF\nagent/x\nEOF", "rm") == (FeedStage("data", "agent/x\n"),)


def test_a_producers_own_stdin_sits_in_front_of_it():
    got = _stages("cat <<EOF | xargs rm\nagent/x\nEOF", "rm")
    assert got == (FeedStage("data", "agent/x\n"), _stage("cat"))


def test_a_process_substitution_is_a_stage_of_its_commands():
    got = _stages("xargs rm < <(grep -rl x agent/ | sort)", "rm")
    assert got == (_stage("grep -rl x agent/ | sort"),)


def test_a_group_member_inherits_the_stages_in_front_of_the_group():
    got = _stages("echo z | ( grep -v q | xargs rm )", "rm")
    assert got == (_stage("echo z"), _stage("grep -v q"))


def test_a_loop_body_reads_the_loops_input_first():
    got = _stages("grep -rl x agent/ | while read f; do echo $f | xargs rm; done", "rm")
    assert got[0] == _stage("grep -rl x agent/")
    assert got[-1].kind == "stage"
    assert [r.name for r in shellscan.every_run(got[-1].text)] == ["echo"]
    assert len(got) == 2


def test_a_find_exec_command_is_fed_finds_words_as_data():
    assert _stages("find . -name x -exec rm {} +", "rm") == (
        FeedStage("data", ". -name x -exec rm {} +"),
    )
