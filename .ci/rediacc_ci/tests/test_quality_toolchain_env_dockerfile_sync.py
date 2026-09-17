"""`rediacc_ci.quality.toolchain_env_dockerfile_sync` against its three extractors.

WHY A DIFFERENTIAL FOR TWO OF THEM AND NOT THE THIRD. `env_value` and `arg_value` are shell pipelines (`grep | head -1 | cut` and `grep -oP ... \\K`) whose edges are decided by the tools; they are run and compared. `engines_node` is deliberately NOT a pipeline in either implementation -- the twin shells out to `node -e` with a real JSON parse, for the reason its own comment gives:
a first-match grep would read a `volta` pin and send someone to edit the wrong number. It is compared against `node` here for exactly that reason.

The whole gate is covered by `.ci/shadow/w7p2-toolchain-sync.observations.jsonl` over five distinct trees.
"""

import pathlib

import pytest

from rediacc_ci.quality import toolchain_env_dockerfile_sync as mod
from rediacc_ci.tests import differential as diff

ENV_CASES = [
    ("GO_VERSION=1.26.6\n", "GO_VERSION"),  # the ordinary one
    ("GO_VERSION=1.0.0\nGO_VERSION=2.0.0\n", "GO_VERSION"),  # head -1: FIRST wins
    ("  GO_VERSION=1.0.0\n", "GO_VERSION"),  # indented: the grep is anchored
    ("K=a=b\n", "K"),  # cut -f2- keeps the rest
    ("GO_VERSION_EXTRA=9\n", "GO_VERSION"),  # a longer key is not this key
    ("NODE_VERSION=22\n", "GO_VERSION"),  # absent
    ("GO_VERSION=\n", "GO_VERSION"),  # present but empty
]


@pytest.mark.parametrize(("content", "key"), ENV_CASES)
def test_env_value_matches_the_shell_pipeline(
    tmp_path: pathlib.Path, content: str, key: str
) -> None:
    target = tmp_path / "toolchain.env"
    target.write_text(content, encoding="utf-8")
    script = 'grep -E "^%s=" toolchain.env 2>/dev/null | head -1 | cut -d= -f2-' % key
    code, out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    del code  # grep exits 1 when nothing matches; the twin ignores that.
    assert mod.env_value(key, target) == out.rstrip("\n")


ARG_CASES = [
    ("ARG GO_VERSION=1.26.6\n", "GO_VERSION"),
    ("ARG\tGO_VERSION=1.26.6\n", "GO_VERSION"),  # a tab is [[:space:]]
    ("ARG  GO_VERSION=1.26.6\n", "GO_VERSION"),  # two spaces
    ("  ARG GO_VERSION=1.26.6\n", "GO_VERSION"),  # indented: not read
    ("# ARG GO_VERSION=9.9.9\n", "GO_VERSION"),  # commented
    ("ARG GO_VERSION=1\nARG GO_VERSION=2\n", "GO_VERSION"),  # head -1
    ("FROM x\n", "GO_VERSION"),  # absent
]


@pytest.mark.parametrize(("content", "key"), ARG_CASES)
def test_arg_value_matches_grep_dash_p(tmp_path: pathlib.Path, content: str, key: str) -> None:
    target = tmp_path / "Dockerfile"
    target.write_text(content, encoding="utf-8")
    script = 'grep -oP "^ARG[[:space:]]+%s=\\K.*" Dockerfile 2>/dev/null | head -1' % key
    code, out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    del code
    assert mod.arg_value(key, target) == out.rstrip("\n")


MANIFESTS = [
    '{"engines":{"node":">=22.44.0"}}',
    '{"volta":{"node":"18.0.0"},"engines":{"node":">=22.44.0"}}',  # the decoy
    '{"devDependencies":{"@types/node":"^22"}}',  # one character away
    '{"engines":{}}',
    '{"name":"no-engines-here"}',
    "{ not json",  # malformed: "" and the caller calls that a failure
    "",
]


@pytest.mark.parametrize("content", MANIFESTS)
def test_engines_node_matches_the_node_parse(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "package.json"
    target.write_text(content, encoding="utf-8")
    script = (
        'node -e \'const fs=require("node:fs");let v="";'
        'try{v=(JSON.parse(fs.readFileSync(process.argv[1],"utf8")).engines||{}).node||"";}'
        "catch{}process.stdout.write(String(v));' package.json 2>/dev/null"
    )
    code, out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    del code
    assert mod.engines_node(target) == out


def test_a_range_that_merely_admits_the_pin_is_still_a_mismatch(
    tmp_path: pathlib.Path,
) -> None:
    """ ">=" is asserted, not parsed. Accepting ">=22" would BE the drift."""
    env_file = tmp_path / "floor.env"
    env_file.write_text("NODE_VERSION_MIN=22.44.0\n", encoding="utf-8")
    loose = tmp_path / "loose.json"
    loose.write_text('{"engines":{"node":">=22"}}', encoding="utf-8")
    report = mod.Report(colour={"RED": "", "GREEN": "", "NC": ""})
    mod.check_engines_pair(report, "NODE_VERSION_MIN", env_file, "T", loose)
    assert report.fails == 1
