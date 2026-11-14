"""A word bash drops (an unset variable) holds no place in the expanded argv, so the walk reads the words after it at their own positions (review d95ab97d.1).

Before the fix `_operand_words` advanced its position in `xargv` past `$X` after `unset X`, so `$D/*.json` was never matched to its assigned value and was judged as typed text: with D unknown that is `<anything>/*.json`, which `.claude/settings.json` matches, and an innocent removal was refused. The controls keep the refusals that must stay.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

BPF = importlib.import_module("rediacc_hooks.guards.block_protected_files")
# The recursive-removal rows need the real tree to look inside.
CWD = str(pathlib.Path(__file__).resolve().parents[3])


@pytest.mark.parametrize(
    "cmd",
    [
        "unset X; D=agent/d; rm -r $X $D/*.json",
        "unset X; D=agent/d; rm $X $D/*.json",
        "X=; D=agent/d; rm $X $D/*.json",
        "D=agent/d; rm $D/*.json",
    ],
)
def test_a_dropped_word_does_not_hide_the_assigned_value_of_the_next(cmd):
    assert BPF.names_by_run(cmd, CWD) is False


@pytest.mark.parametrize(
    "cmd",
    [
        "unset X; D=.claude; rm $X $D/*.json",
        "unset X; D=.claude; rm -r $X $D/../.claude",
        "D=.claude; rm $D/*.json",
    ],
)
def test_control_a_protected_target_after_a_dropped_word_is_still_refused(cmd):
    assert BPF.names_by_run(cmd, CWD) is True
