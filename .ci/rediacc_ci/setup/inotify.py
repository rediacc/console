"""Host inotify limits for `./run.sh setup` and `./run.sh setup --check`.

WHY. With `fs.inotify.max_user_instances` at the kernel default of 128, a busy dev host runs out: `timeout 2 tail -f /dev/null` printed "OS file watch limit reached", `scripts/ci-runner/run.ts --selftest` failed its kill-timer control, so every `npm run ci` exited 1 before any gate, and `wrangler dev` hit ENOSPC on its watchers. The floors below are what that host was raised to.

ADVISORY, NEVER FATAL. A host without sudo still gets a usable setup; it is told the exact command instead. The step writes `/etc/sysctl.d/60-rediacc-inotify.conf` and applies the values with `sysctl -w`, and does nothing when both the live values and the file are already right, so a second run changes nothing.
"""

from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .ctx import Ctx

FLOORS: dict[str, int] = {
    "fs.inotify.max_user_instances": 1024,
    "fs.inotify.max_user_watches": 524288,
}
CONF_PATH = pathlib.Path("/etc/sysctl.d/60-rediacc-inotify.conf")
PROC_ROOT = pathlib.Path("/proc/sys")


def conf_text() -> str:
    lines = [
        "# Written by ./run.sh setup: the dev host runs out of inotify instances at the kernel default (128)."
    ]
    lines += ["%s = %d" % (key, value) for key, value in FLOORS.items()]
    return "\n".join(lines) + "\n"


def current(proc_root: pathlib.Path = PROC_ROOT) -> dict[str, int | None]:
    """The live value of each sysctl, None when unreadable (not Linux, or hidden)."""
    out: dict[str, int | None] = {}
    for key in FLOORS:
        try:
            out[key] = int((proc_root / key.replace(".", "/")).read_text().strip())
        except (OSError, ValueError):
            out[key] = None
    return out


def below_floor(proc_root: pathlib.Path = PROC_ROOT) -> dict[str, int]:
    """Every sysctl whose live value is under its floor, with that value. Unreadable ones are skipped."""
    return {
        key: have
        for key, have in current(proc_root).items()
        if have is not None and have < FLOORS[key]
    }


def fix_command() -> str:
    pairs = " ".join("%s=%d" % (key, value) for key, value in FLOORS.items())
    return "sudo sysctl -w %s" % pairs


def check_row(
    proc_root: pathlib.Path = PROC_ROOT, conf: pathlib.Path = CONF_PATH
) -> tuple[str, bool]:
    """The `--check` row and whether it counts as pending. Reads only."""
    low = below_floor(proc_root)
    if low:
        have = ", ".join("%s=%d (floor %d)" % (k, v, FLOORS[k]) for k, v in low.items())
        return "  inotify     BELOW the floor: %s; fix: %s" % (have, fix_command()), True
    if all(v is None for v in current(proc_root).values()):
        return "  inotify     not readable here", False
    if not conf.exists():
        # NOT COUNTED: the live value is fine, only a reboot would lose it.
        return "  inotify     at the floor, not persisted (setup writes %s)" % conf, False
    return "  inotify     at the floor", False


def ensure(
    ctx: Ctx,
    proc_root: pathlib.Path = PROC_ROOT,
    conf: pathlib.Path = CONF_PATH,
) -> int:
    """Write the sysctl.d file and apply it. Always 0; a failure is warned with the command to run."""
    if all(v is None for v in current(proc_root).values()):
        return 0
    want = conf_text()
    try:
        file_ok = conf.read_text(encoding="utf-8") == want
    except OSError:
        file_ok = False
    if file_ok and not below_floor(proc_root):
        return 0
    ctx.step("Host inotify limits")
    sudo = [] if hasattr(os, "geteuid") and os.geteuid() == 0 else ["sudo"]
    if not file_ok:
        wrote = ctx.run([*sudo, "tee", str(conf)], stdin_text=want, timeout=120)
        if wrote.rc != 0:
            ctx.warn("could not write %s: %s" % (conf, wrote.err.strip()))
            ctx.say(fix_command())
            return 0
        ctx.info("wrote %s" % conf)
    if below_floor(proc_root):
        applied = ctx.run(
            [*sudo, "sysctl", "-w", *["%s=%d" % kv for kv in FLOORS.items()]], timeout=60
        )
        if applied.rc != 0:
            ctx.warn("could not apply the limits: %s" % applied.err.strip())
            ctx.say(fix_command())
            return 0
        ctx.info("applied: %s" % ", ".join("%s=%d" % kv for kv in FLOORS.items()))
    ctx.say()
    return 0
