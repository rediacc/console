"""The one loader for the guard fixture data files beside it.

Each `<stem>.json` holds the data tables of one guard (`EDGE_CASES`, `ENVS`) as JSON lists of rows. A row is `[name, payload]`; a bare `{"//": "text"}` object between rows is the comment the Python literal carried and is dropped on load, so a table keeps the explanation of its row groups without a reader having to read the code that consumes it.
"""

import json
import pathlib
import re

from rediacc_hooks import wellknown

DATA_DIR = pathlib.Path(__file__).resolve().parent

COMMENT_KEY = "//"

# A fixture names an owned value as `@WK_<NAME>@`, expanded on load to the registered value in .ci/config/well-known.env, so the data file holds no second copy of it (check:ci-literal-sources). `@~@` expands to nothing and splits a value that has no registry entry (a host the gate counts across files).
_MARKER = re.compile(r"@(WK_[A-Z0-9_]+|~)@")


def _expand_marker(match):
    name = match.group(1)
    return "" if name == "~" else str(getattr(wellknown, name[3:]))


def _expand(value):
    """`value` with every marker in every string, at any depth, replaced; an unknown name raises."""
    if isinstance(value, str):
        return _MARKER.sub(_expand_marker, value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def _is_comment(row):
    return isinstance(row, dict) and set(row) == {COMMENT_KEY}


def load_table(stem, name):
    """The rows of table `name` in `<stem>.json`, each row a tuple, comment markers removed.

    A missing file or a missing table is an error: an empty list would let a guard's differential pass over no cases.
    """
    path = DATA_DIR / ("%s.json" % stem)
    tables = json.loads(path.read_text(encoding="utf-8"))
    if name not in tables:
        raise KeyError("%s holds no table %r (has %s)" % (path.name, name, sorted(tables)))
    rows = [tuple(_expand(row)) for row in tables[name] if not _is_comment(row)]
    if not rows:
        raise ValueError("%s: table %r has no rows" % (path.name, name))
    return rows
