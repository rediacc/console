"""FORWARDER to `.claude/hooks/stop/wl_planfid.py`. See README.md beside this file.

`oracles/pre-edit/block-plan-without-tasks.sh` puts this directory first on `sys.path` and then `import wl_planfid as P`, reading `MIN_PLAN_CHARS`, `CHECKBOX_RE` and `plan_tasks` off it.

`exec` INTO THIS NAMESPACE, not a star import, and the reason was measured on the sibling forwarder: with this directory leading `sys.path`, an `import wl_planfid` inside this file resolves to this file, which is half-initialised, so the star
import binds nothing -- and the guard's `except Exception: sys.exit(0)` turns that
into a silent allow on every input. The differential caught exactly that shape once already and it is not repeated here.
"""

import pathlib
import sys

_LIVE_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
if str(_LIVE_DIR) not in sys.path:
    sys.path.append(str(_LIVE_DIR))  # APPEND: this dir must stay first for the guard
_LIVE = _LIVE_DIR / "wl_planfid.py"
exec(compile(_LIVE.read_text(encoding="utf-8"), str(_LIVE), "exec"), globals())  # noqa: S102
