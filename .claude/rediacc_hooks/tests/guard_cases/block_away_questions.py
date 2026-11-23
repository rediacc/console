"""The test tables of `block_away_questions`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import json
import pathlib


def _flag_world(path):
    """A flag set long before any record, so every payload meets an away operator."""
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(path) / "away.json").write_text(
        json.dumps({"since": "2000-01-01T00:00:00.000000Z", "note": "fixture"})
    )
    return path


def _empty_world(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return path


FIXTURES = {"away-flag-set": _flag_world, "away-flag-none": _empty_world}


# Both worlds pin WL_AWAY_STATE: an unpinned one would read the live flag, and a session that ran `/awk` would flip every answer.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"WL_AWAY_STATE": "{FIXTURE:away-flag-none}"}, {}),
    ("away", {"WL_AWAY_STATE": "{FIXTURE:away-flag-set}"}, {}),
]


EDGE_CASES = [
    ("a design question", "Which bucket should the restore test use?"),
    ("a permission question", "Should the edge deploy take the live key?"),
]
