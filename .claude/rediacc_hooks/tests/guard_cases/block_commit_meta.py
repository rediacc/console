"""The test tables of `block_commit_meta`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import pathlib

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# A body file reached ONLY through an inherited variable (#378c645c). The differential's `_base_env` passes the runner's real HOME, where these files do not exist, so the `home-bodies` variant points HOME at this fixture instead: the same `$HOME/...` payloads are admitted under `default` (no file to read) and judged on their bytes here. The footer is assembled so no source line is itself one.
HOME_BODIES = ".commit-meta-bodies"


def _home_fixture(path):
    bodies = pathlib.Path(path) / HOME_BODIES
    bodies.mkdir(parents=True)
    footer = "\U0001f916 " + "Generated" + " with [Claude Code](u)"
    (bodies / "footer.md").write_text("prose\n\n%s\n" % footer, encoding="utf-8")
    (bodies / "clean.md").write_text("prose\n\nConsole PR: x.\n", encoding="utf-8")
    session = "Claude-" + "Session: https://claude" + ".ai/code/session_01AbCd"
    (bodies / "session.md").write_text("prose\n\n%s\n" % session, encoding="utf-8")
    return path


FIXTURES = {"commit-meta-home": _home_fixture}


# `default` first and with no extras, so every record it already froze keeps its key.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {}, {}),
    ("home-bodies", {"HOME": "{FIXTURE:commit-meta-home}"}, {}),
]


EDGE_CASES = load_table("block_commit_meta", "EDGE_CASES")
